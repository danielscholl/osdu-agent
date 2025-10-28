"""Main OSDU Agent implementation."""

import logging
from importlib import resources
from typing import Optional

from agent_framework import ChatAgent
from agent_framework.azure import AzureOpenAIResponsesClient, AzureAIAgentClient
from azure.identity import AzureCliCredential, DefaultAzureCredential

from agent.config import AgentConfig
from agent.filesystem import create_hybrid_filesystem_tools
from agent.git import create_git_tools
from agent.github import create_github_tools
from agent.gitlab import create_gitlab_tools
from agent.hosted_tools import HostedToolsManager
from agent.middleware import (
    logging_chat_middleware,
    logging_function_middleware,
    workflow_context_agent_middleware,
)

logger = logging.getLogger(__name__)


class Agent:
    """
    AI-powered repository management agent for OSDU services.

    This agent uses Microsoft Agent Framework with Azure OpenAI to provide
    a natural language interface for GitHub and GitLab repository management,
    including issues, pull/merge requests, workflows/pipelines, and more.
    """

    def __init__(self, config: Optional[AgentConfig] = None, mcp_tools: Optional[list] = None):
        """
        Initialize OSDU Agent.

        Args:
            config: Agent configuration. If None, uses defaults from environment.
            mcp_tools: Optional list of MCP tools to integrate with agent
        """
        self.config = config or AgentConfig()
        self.github_tools = create_github_tools(self.config)
        self.mcp_tools = mcp_tools or []

        # Create GitLab tools if token configured
        # (URL is hardcoded to community.opengroup.org for all OSDU services)
        if self.config.gitlab_token:
            self.gitlab_tools = create_gitlab_tools(self.config)
            logger.info(f"GitLab tools initialized: {len(self.gitlab_tools)} tools available")
        else:
            self.gitlab_tools = []
            logger.info("GitLab token not configured - skipping GitLab tools")

        # Load agent instructions from system prompt
        self.instructions = self._load_system_prompt()

        # Initialize Azure client based on client_type
        if self.config.client_type == "ai_agent":
            # Azure AI Foundry Agent Client
            logger.info("Using Azure AI Foundry Agent Client")

            # Parse connection string if provided
            project_endpoint = self.config.azure_ai_project_endpoint
            if not project_endpoint and self.config.azure_ai_project_connection_string:
                # Parse: "region.api.azureml.ms;subscription_id;resource_group;workspace_name"
                parts = self.config.azure_ai_project_connection_string.split(";")
                if len(parts) >= 1:
                    project_endpoint = f"https://{parts[0]}"
                    logger.info(
                        f"Parsed project endpoint from connection string: {project_endpoint}"
                    )

            if not project_endpoint:
                raise ValueError(
                    "Azure AI Foundry client requires AZURE_AI_PROJECT_ENDPOINT or "
                    "AZURE_AI_PROJECT_CONNECTION_STRING environment variable"
                )

            # Create AI Agent client
            chat_client = AzureAIAgentClient(
                project_endpoint=project_endpoint,
                model_deployment_name=self.config.azure_openai_deployment,
                async_credential=DefaultAzureCredential(),  # type: ignore[arg-type]
            )
            logger.info(f"Azure AI Agent client initialized with endpoint: {project_endpoint}")
        else:
            # Azure OpenAI Responses Client (default/current)
            logger.info("Using Azure OpenAI Responses Client")
            client_params = {
                "credential": AzureCliCredential(),
            }

            # Add required parameters
            if self.config.azure_openai_endpoint:
                client_params["endpoint"] = self.config.azure_openai_endpoint  # type: ignore[assignment]

            if self.config.azure_openai_deployment:
                client_params["deployment_name"] = self.config.azure_openai_deployment  # type: ignore[assignment]

            if self.config.azure_openai_api_version:
                client_params["api_version"] = self.config.azure_openai_api_version  # type: ignore[assignment]

            # Handle authentication
            if self.config.azure_openai_api_key:
                # If API key provided, don't use credential
                client_params.pop("credential", None)
                client_params["api_key"] = self.config.azure_openai_api_key  # type: ignore[assignment]

            # Create chat client
            chat_client = AzureOpenAIResponsesClient(**client_params)  # type: ignore[assignment, arg-type]

        # Initialize hosted tools manager
        self.hosted_tools_manager = HostedToolsManager(self.config, chat_client=chat_client)

        # Log hosted tools status
        if self.hosted_tools_manager.is_available:
            status = self.hosted_tools_manager.get_status_summary()
            logger.info(
                f"Hosted tools enabled: {status['tool_count']} tools available (mode: {status['mode']})"
            )
        elif self.config.hosted_tools_enabled:
            logger.info("Hosted tools requested but not available - using custom tools")

        # Create hybrid filesystem tools (combines hosted + custom based on config)
        self.filesystem_tools = create_hybrid_filesystem_tools(
            self.config, self.hosted_tools_manager
        )

        # Create git repository management tools
        self.git_tools = create_git_tools(self.config)

        # Combine GitHub tools, file system tools, git tools, GitLab tools, and MCP tools
        all_tools = (
            self.github_tools
            + self.filesystem_tools
            + self.git_tools
            + self.gitlab_tools
            + self.mcp_tools
        )

        # Create agent with all available tools and middleware
        # Note: Thread-based memory is built-in - agent remembers within a session
        # Middleware levels:
        # - Agent middleware: Intercepts agent.run() calls (workflow context injection)
        # - Function middleware: Intercepts tool calls (logging)
        # - Chat middleware: Intercepts LLM calls (logging)

        # Combine all middleware into a single list for the new agent framework API
        # (agent-framework 1.0.0b251016+ uses unified middleware parameter)
        all_middleware = [
            workflow_context_agent_middleware,
            logging_function_middleware,
            logging_chat_middleware,
        ]

        self.agent = ChatAgent(
            chat_client=chat_client,
            instructions=self.instructions,
            tools=all_tools,
            name="OSDU Agent",
            model=self.config.azure_openai_deployment,  # Explicit model name for telemetry
            middleware=all_middleware,  # type: ignore[arg-type]
        )

    def _load_system_prompt(self) -> str:
        """Load system prompt from prompts directory."""
        try:
            # Load system prompt file
            prompt_files = resources.files("agent.copilot.prompts")
            system_prompt = (prompt_files / "system.md").read_text(encoding="utf-8")

            # Replace placeholders
            system_prompt = system_prompt.replace("{{ORGANIZATION}}", self.config.organization)
            system_prompt = system_prompt.replace(
                "{{REPOSITORIES}}", ", ".join(self.config.repositories)
            )
            system_prompt = system_prompt.replace(
                "{{REPOS_ROOT}}", str(self.config.repos_root)
            )

            return system_prompt
        except Exception:
            # Fallback to basic instructions if file not found
            return f"""You are Betty, an AI assistant for managing GitHub repositories for OSDU services.
Organization: {self.config.organization}
Managed Repositories: {', '.join(self.config.repositories)}
(System prompt file not found - using fallback)"""

    async def run(self, query: str) -> str:
        """
        Run agent with a natural language query.

        Args:
            query: Natural language query about GitHub issues

        Returns:
            Agent's response as string
        """
        try:
            response = await self.agent.run(query)
            return response  # type: ignore[return-value]
        except Exception as e:
            return f"Error running agent: {str(e)}"

    async def run_interactive(self) -> None:
        """
        Run agent in interactive mode (REPL).

        Allows continuous conversation with the agent.
        """
        print("=== OSDU Agent ===")
        print(f"Organization: {self.config.organization}")
        print(f"Repositories: {', '.join(self.config.repositories)}")
        print("\nType 'exit' or 'quit' to end the session.\n")

        while True:
            try:
                query = input("You: ").strip()

                if not query:
                    continue

                if query.lower() in ["exit", "quit", "q"]:
                    print("Goodbye!")
                    break

                response = await self.run(query)
                print(f"\nAgent: {response}\n")

            except KeyboardInterrupt:
                print("\n\nGoodbye!")
                break
            except Exception as e:
                print(f"Error: {e}\n")
