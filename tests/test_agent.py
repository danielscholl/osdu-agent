"""Tests for agent module."""

from unittest.mock import AsyncMock, Mock, patch

import pytest

from agent.agent import Agent
from agent.config import AgentConfig


@pytest.fixture
def test_agent(test_config: AgentConfig) -> Agent:
    """Create a test agent instance with mocked dependencies."""
    with (
        patch("agent.agent.AzureOpenAIResponsesClient"),
        patch("agent.agent.create_github_tools") as mock_github_tools,
        patch("agent.agent.create_hybrid_filesystem_tools") as mock_fs_tools,
        patch("agent.agent.create_git_tools") as mock_git_tools,
        patch("agent.agent.ChatAgent") as mock_chat_agent,
    ):

        # Mock GitHub, filesystem, and git tools
        mock_github_tools.return_value = []
        mock_fs_tools.return_value = []
        mock_git_tools.return_value = []

        # Mock ChatAgent
        mock_agent_instance = Mock()
        mock_agent_instance.run = AsyncMock(return_value="Mocked agent response")
        mock_chat_agent.return_value = mock_agent_instance

        agent = Agent(config=test_config)
        agent.agent = mock_agent_instance  # Replace with mock

        return agent


def test_agent_initialization():
    """Test agent initialization with default config."""
    with (
        patch("agent.agent.AzureOpenAIResponsesClient"),
        patch("agent.agent.create_github_tools"),
        patch("agent.agent.create_hybrid_filesystem_tools"),
        patch("agent.agent.create_git_tools"),
        patch("agent.agent.ChatAgent"),
    ):
        agent = Agent()

        assert agent.config is not None
        assert agent.github_tools is not None
        assert agent.filesystem_tools is not None
        assert agent.git_tools is not None
        assert agent.agent is not None


def test_agent_initialization_with_custom_config(test_config: AgentConfig):
    """Test agent initialization with custom config."""
    with (
        patch("agent.agent.AzureOpenAIResponsesClient"),
        patch("agent.agent.create_github_tools"),
        patch("agent.agent.create_hybrid_filesystem_tools"),
        patch("agent.agent.create_git_tools"),
        patch("agent.agent.ChatAgent"),
    ):
        agent = Agent(config=test_config)

        assert agent.config.organization == "test-org"
        assert "test-repo1" in agent.config.repositories


@pytest.mark.asyncio
async def test_agent_run(test_agent: Agent):
    """Test running agent with a query."""
    response = await test_agent.run("List issues in test-repo1")

    assert response == "Mocked agent response"
    test_agent.agent.run.assert_called_once_with("List issues in test-repo1")


@pytest.mark.asyncio
async def test_agent_run_handles_errors(test_agent: Agent):
    """Test agent run handles exceptions gracefully."""
    test_agent.agent.run.side_effect = Exception("Test error")

    response = await test_agent.run("Test query")

    assert "Error running agent" in response
    assert "Test error" in response


def test_agent_instructions_include_repos(test_config: AgentConfig):
    """Test that agent instructions include repository information."""
    with (
        patch("agent.agent.AzureOpenAIResponsesClient"),
        patch("agent.agent.create_github_tools"),
        patch("agent.agent.create_hybrid_filesystem_tools"),
        patch("agent.agent.create_git_tools"),
        patch("agent.agent.ChatAgent"),
    ):
        agent = Agent(config=test_config)

        # Verify instructions mention the organization and repos
        assert "test-org" in agent.instructions
        assert "test-repo1" in agent.instructions or "test-repo2" in agent.instructions


def test_agent_has_required_tools():
    """Test that agent is initialized with GitHub, filesystem, and git tools."""
    with (
        patch("agent.agent.AzureOpenAIResponsesClient"),
        patch("agent.agent.create_github_tools") as mock_create_github_tools,
        patch("agent.agent.create_hybrid_filesystem_tools") as mock_create_fs_tools,
        patch("agent.agent.create_git_tools") as mock_create_git_tools,
        patch("agent.agent.create_gitlab_tools") as mock_create_gitlab_tools,
        patch("agent.agent.ChatAgent") as mock_chat_agent,
    ):

        # Mock tools
        github_tools = [Mock(), Mock(), Mock()]
        fs_tools = [Mock(), Mock()]
        git_tools = [Mock(), Mock()]
        gitlab_tools = []  # No GitLab tools for this test
        mock_create_github_tools.return_value = github_tools
        mock_create_fs_tools.return_value = fs_tools
        mock_create_git_tools.return_value = git_tools
        mock_create_gitlab_tools.return_value = gitlab_tools

        Agent()

        # Verify ChatAgent was called with combined tools
        mock_chat_agent.assert_called_once()
        call_kwargs = mock_chat_agent.call_args[1]

        assert call_kwargs["tools"] == github_tools + fs_tools + git_tools + gitlab_tools
        assert call_kwargs["name"] == "OSDU Agent"


def test_agent_with_mcp_tools():
    """Test that agent can be initialized with MCP tools."""
    with (
        patch("agent.agent.AzureOpenAIResponsesClient"),
        patch("agent.agent.create_github_tools") as mock_create_github_tools,
        patch("agent.agent.create_hybrid_filesystem_tools") as mock_create_fs_tools,
        patch("agent.agent.create_git_tools") as mock_create_git_tools,
        patch("agent.agent.create_gitlab_tools") as mock_create_gitlab_tools,
        patch("agent.agent.ChatAgent") as mock_chat_agent,
    ):

        # Mock GitHub, filesystem, git, GitLab, and MCP tools
        github_tools = [Mock(), Mock()]
        fs_tools = [Mock()]
        git_tools = [Mock()]
        gitlab_tools = []  # No GitLab tools for this test
        mcp_tools = [Mock()]
        mock_create_github_tools.return_value = github_tools
        mock_create_fs_tools.return_value = fs_tools
        mock_create_git_tools.return_value = git_tools
        mock_create_gitlab_tools.return_value = gitlab_tools

        Agent(mcp_tools=mcp_tools)

        # Verify ChatAgent was called with combined tools
        mock_chat_agent.assert_called_once()
        call_kwargs = mock_chat_agent.call_args[1]

        # Should have GitHub, filesystem, git, GitLab, and MCP tools
        assert len(call_kwargs["tools"]) == 5
        assert (
            call_kwargs["tools"] == github_tools + fs_tools + git_tools + gitlab_tools + mcp_tools
        )


def test_agent_instructions_include_maven_capabilities(test_config: AgentConfig):
    """Test that agent instructions include Maven MCP capabilities."""
    with (
        patch("agent.agent.AzureOpenAIResponsesClient"),
        patch("agent.agent.create_github_tools"),
        patch("agent.agent.create_hybrid_filesystem_tools"),
        patch("agent.agent.create_git_tools"),
        patch("agent.agent.ChatAgent"),
    ):
        agent = Agent(config=test_config)

        # Verify instructions mention Maven capabilities
        assert "MAVEN DEPENDENCY MANAGEMENT" in agent.instructions
        assert "Check single dependency version" in agent.instructions
        assert "Scan Java projects for security vulnerabilities" in agent.instructions
        assert "triage" in agent.instructions.lower()
        assert "plan" in agent.instructions.lower()
