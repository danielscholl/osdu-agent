"""Configuration management for OSDU Agent."""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Literal, Optional

from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


@dataclass
class AgentConfig:
    """
    Configuration for OSDU Agent.

    Attributes:
        organization: GitHub organization name
        repositories: List of repository names to manage
        repos_root: Root directory for cloned repositories
        github_token: GitHub personal access token (optional, can use env var)
        gitlab_url: GitLab instance URL (optional, defaults to https://gitlab.com)
        gitlab_token: GitLab personal access token (optional)
        gitlab_default_group: Default GitLab group/namespace (optional)
        azure_openai_endpoint: Azure OpenAI endpoint URL
        azure_openai_deployment: Azure OpenAI deployment/model name
        azure_openai_api_version: Azure OpenAI API version
        azure_openai_api_key: Azure OpenAI API key (optional if using Azure CLI auth)
        client_type: Type of Azure client to use ('openai' or 'ai_agent')
        hosted_tools_enabled: Enable Microsoft Agent Framework hosted tools
        hosted_tools_mode: How to integrate hosted tools ('complement', 'replace', 'fallback')
    """

    organization: str = field(default_factory=lambda: os.getenv("OSDU_AGENT_ORGANIZATION", "azure"))

    repositories: List[str] = field(
        default_factory=lambda: os.getenv(
            "OSDU_AGENT_REPOSITORIES",
            "partition,legal,entitlements,schema,file,storage,indexer,indexer-queue,search,workflow",
        ).split(",")
    )

    repos_root: Path = field(
        default_factory=lambda: Path(os.getenv("OSDU_AGENT_REPOS_ROOT", Path.cwd() / "repos"))
    )

    github_token: Optional[str] = field(default_factory=lambda: os.getenv("GITHUB_TOKEN"))

    # GitLab Configuration
    gitlab_url: Optional[str] = field(
        default_factory=lambda: os.getenv("GITLAB_URL", "https://gitlab.com")
    )

    gitlab_token: Optional[str] = field(default_factory=lambda: os.getenv("GITLAB_TOKEN"))

    gitlab_default_group: Optional[str] = field(
        default_factory=lambda: os.getenv("GITLAB_DEFAULT_GROUP")
    )

    azure_openai_endpoint: Optional[str] = field(
        default_factory=lambda: os.getenv("AZURE_OPENAI_ENDPOINT")
    )

    azure_openai_deployment: str = field(
        default_factory=lambda: os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-4")
    )

    azure_openai_api_version: str = field(
        default_factory=lambda: os.getenv("AZURE_OPENAI_API_VERSION")
        or os.getenv("AZURE_OPENAI_VERSION")
        or "2024-12-01-preview"
    )

    azure_openai_api_key: Optional[str] = field(
        default_factory=lambda: os.getenv("AZURE_OPENAI_API_KEY")
    )

    # Internal Maven MCP configuration
    maven_mcp_command: str = "uvx"
    maven_mcp_args: List[str] = field(
        default_factory=lambda: [
            "--quiet",  # Suppress uvx output
            # Pin to specific version for reproducibility
            # v2.3.0 includes per-module vulnerability tracking and severity filtering
            # Can override via MAVEN_MCP_VERSION env var
            os.getenv("MAVEN_MCP_VERSION", "mvn-mcp-server==2.3.0"),
            # Note: stderr is redirected to logs/maven_mcp_*.log by QuietMCPStdioTool
        ]
    )

    # Hosted Tools Configuration
    client_type: Literal["openai", "ai_agent"] = field(
        default_factory=lambda: os.getenv("OSDU_AGENT_CLIENT_TYPE", "openai")  # type: ignore
    )

    hosted_tools_enabled: bool = field(
        default_factory=lambda: os.getenv("OSDU_AGENT_HOSTED_TOOLS_ENABLED", "false").lower()
        == "true"
    )

    hosted_tools_mode: Literal["complement", "replace", "fallback"] = field(
        default_factory=lambda: os.getenv("OSDU_AGENT_HOSTED_TOOLS_MODE", "complement")  # type: ignore
    )

    # Azure AI Foundry Configuration (for ai_agent client type)
    azure_ai_project_endpoint: Optional[str] = field(
        default_factory=lambda: os.getenv("AZURE_AI_PROJECT_ENDPOINT")
    )

    azure_ai_project_connection_string: Optional[str] = field(
        default_factory=lambda: os.getenv("AZURE_AI_PROJECT_CONNECTION_STRING")
    )

    def validate(self) -> None:
        """Validate configuration and raise ValueError if invalid."""
        if not self.organization:
            raise ValueError("organization is required")

        if not self.repositories or len(self.repositories) == 0:
            raise ValueError("repositories list cannot be empty")

        # Clean up repository names (strip whitespace)
        self.repositories = [repo.strip() for repo in self.repositories if repo.strip()]

        # Validate hosted tools configuration
        if self.client_type not in ["openai", "ai_agent"]:
            raise ValueError(
                f"client_type must be 'openai' or 'ai_agent', got '{self.client_type}'"
            )

        if self.hosted_tools_mode not in ["complement", "replace", "fallback"]:
            raise ValueError(
                f"hosted_tools_mode must be 'complement', 'replace', or 'fallback', got '{self.hosted_tools_mode}'"
            )

    def get_repo_full_name(self, repo: str) -> str:
        """Get full repository name (org/repo)."""
        return f"{self.organization}/{repo}"

    def get_gitlab_project_path(self, project: str) -> str:
        """
        Get full GitLab project path (group/project).

        For OSDU services, fetches the upstream GitLab URL from GitHub and parses the path.
        Otherwise, uses gitlab_default_group or assumes full path provided.

        Args:
            project: Project name or full path

        Returns:
            Full project path for GitLab API
        """
        if "/" in project:
            # Already a full path (e.g., "osdu/platform/system/partition")
            return project

        # Try to fetch upstream URL from GitHub for OSDU services
        try:
            import subprocess
            from urllib.parse import urlparse

            repo = f"{self.organization}/{project}"
            result = subprocess.run(
                [
                    "gh",
                    "api",
                    f"repos/{repo}/actions/variables/UPSTREAM_REPO_URL",
                    "--jq",
                    ".value",
                ],
                capture_output=True,
                text=True,
                timeout=10,
            )

            if result.returncode == 0 and result.stdout.strip():
                upstream_url = result.stdout.strip()
                # Parse project path from URL
                # E.g., "https://community.opengroup.org/osdu/platform/system/partition.git"
                # -> "osdu/platform/system/partition"
                parsed = urlparse(upstream_url)
                path = parsed.path.lstrip("/").rstrip(".git")
                if path:
                    return path

        except Exception:
            pass  # Fall through to default logic

        if self.gitlab_default_group:
            # Use default group (e.g., "osdu/partition")
            return f"{self.gitlab_default_group}/{project}"

        # No group specified, return project name as-is
        return project

    def __post_init__(self) -> None:
        """Post-initialization validation."""
        self.validate()
