"""Configuration management for OSDU Agent."""

import logging
import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Literal, Optional, cast

from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

logger = logging.getLogger(__name__)


def _get_github_token() -> Optional[str]:
    """
    Get GitHub token from CLI or environment variable.

    Priority:
    1. GitHub CLI (`gh auth token`) - if installed and authenticated
    2. GITHUB_TOKEN environment variable - fallback

    Returns:
        Optional[str]: GitHub token string if available via CLI or environment variable,
                      None if no token is configured (agent will use unauthenticated GitHub API)
    """
    # Try GitHub CLI first
    try:
        result = subprocess.run(
            ["gh", "auth", "token"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0 and result.stdout and result.stdout.strip():
            gh_token = result.stdout.strip()
            logger.debug("Using GitHub token from gh CLI")
            return gh_token
    except (FileNotFoundError, subprocess.TimeoutExpired):
        # gh CLI not installed or timeout
        pass
    except Exception as e:
        logger.debug(f"Failed to get token from gh CLI: {e}")

    # Fall back to environment variable
    env_token: Optional[str] = os.getenv("GITHUB_TOKEN")
    if env_token:
        logger.debug("Using GitHub token from GITHUB_TOKEN env var")
    else:
        logger.debug("No GitHub token configured (will use unauthenticated API)")
    return env_token


def _get_gitlab_token() -> Optional[str]:
    """
    Get GitLab token from CLI or environment variable.

    Priority:
    1. GitLab CLI (`glab auth status --show-token`) - if installed and authenticated
    2. GITLAB_TOKEN environment variable - fallback

    Returns:
        Optional[str]: GitLab token string if available via CLI or environment variable,
                      None if no token is configured (GitLab features will be unavailable)
    """
    # Try GitLab CLI first
    try:
        result = subprocess.run(
            ["glab", "auth", "status", "--show-token"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        # Parse output even if returncode != 0 (handles multi-instance failures)
        # glab writes to stderr (not stdout!)
        # Output format: "  ✓ Token found: glpat-xxxxxxxxxxxxx"
        if result.stderr:
            for line in result.stderr.split("\n"):
                if "Token found:" in line:
                    # Extract token after "Token found: "
                    token = line.split("Token found:")[-1].strip()
                    if token and len(token) > 10:  # Sanity check
                        logger.debug("Using GitLab token from glab CLI")
                        return token

    except (FileNotFoundError, subprocess.TimeoutExpired):
        # glab CLI not installed or timeout
        pass
    except Exception as e:
        logger.debug(f"Failed to get token from glab CLI: {e}")

    # Fall back to environment variable
    env_token: Optional[str] = os.getenv("GITLAB_TOKEN")
    if env_token:
        logger.debug("Using GitLab token from GITLAB_TOKEN env var")
    else:
        logger.debug("No GitLab token configured")
    return env_token


def _get_github_username() -> Optional[str]:
    """
    Get GitHub username from CLI or environment variable.

    Priority:
    1. GitHub CLI (`gh api user`) - if installed and authenticated
    2. GITHUB_USERNAME environment variable - fallback

    Returns:
        Optional[str]: GitHub username if available, None otherwise
    """
    # Try GitHub CLI first
    try:
        result = subprocess.run(
            ["gh", "api", "user", "--jq", ".login"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0 and result.stdout and result.stdout.strip():
            username = result.stdout.strip()
            logger.debug(f"Using GitHub username from gh CLI: {username}")
            return username
    except (FileNotFoundError, subprocess.TimeoutExpired):
        # gh CLI not installed or timeout
        pass
    except Exception as e:
        logger.debug(f"Failed to get username from gh CLI: {e}")

    # Fall back to environment variable
    env_username: Optional[str] = os.getenv("GITHUB_USERNAME")
    if env_username:
        logger.debug(f"Using GitHub username from GITHUB_USERNAME env var: {env_username}")
    else:
        logger.debug("No GitHub username configured")
    return env_username


def _get_gitlab_username() -> Optional[str]:
    """
    Get GitLab username from CLI or environment variable.

    Priority:
    1. GitLab CLI (`glab auth status`) - if installed and authenticated
    2. GITLAB_USERNAME environment variable - fallback

    Returns:
        Optional[str]: GitLab username if available, None otherwise
    """
    # Try GitLab CLI first using auth status (more reliable than API call)
    try:
        result = subprocess.run(
            ["glab", "auth", "status"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        # Parse output for "Logged in to ... as <username>"
        # Example: "✓ Logged in to community.opengroup.org as danielscholl (GITLAB_TOKEN)"
        if result.stderr:
            for line in result.stderr.split("\n"):
                if "Logged in to" in line and " as " in line:
                    # Extract username between " as " and the next space or "("
                    parts = line.split(" as ")
                    if len(parts) >= 2:
                        # Get everything after " as " and before the next space or "("
                        username_part = parts[1].split()[0].strip()
                        # Remove trailing parenthesis or other punctuation
                        username = username_part.rstrip("(),")
                        if username and len(username) > 0:
                            logger.debug(f"Using GitLab username from glab CLI: {username}")
                            return username
    except (FileNotFoundError, subprocess.TimeoutExpired):
        # glab CLI not installed or timeout
        pass
    except Exception as e:
        logger.debug(f"Failed to get username from glab CLI: {e}")

    # Fall back to environment variable
    env_username: Optional[str] = os.getenv("GITLAB_USERNAME")
    if env_username:
        logger.debug(f"Using GitLab username from GITLAB_USERNAME env var: {env_username}")
    else:
        logger.debug("No GitLab username configured")
    return env_username


@dataclass
class AgentConfig:
    """
    Configuration for OSDU Agent.

    Attributes:
        organization: GitHub organization name
        repositories: List of repository names to manage
        repos_root: Root directory for cloned repositories
        github_token: GitHub personal access token (optional, can use env var)
        github_username: GitHub username (fetched from gh CLI or env var)
        gitlab_url: GitLab instance URL (optional, defaults to https://gitlab.com)
        gitlab_token: GitLab personal access token (optional)
        gitlab_username: GitLab username (fetched from glab CLI or env var)
        gitlab_default_group: Default GitLab group/namespace (optional)
        azure_openai_endpoint: Azure OpenAI endpoint URL
        azure_openai_deployment: Azure OpenAI deployment/model name
        azure_openai_api_version: Azure OpenAI API version
        azure_openai_api_key: Azure OpenAI API key (optional if using Azure CLI auth)
        default_platform: Default platform for status command ('github' or 'gitlab', env: OSDU_AGENT_PLATFORM)
        client_type: Type of Azure client to use ('openai' or 'ai_agent')
        hosted_tools_enabled: Enable Microsoft Agent Framework hosted tools
        hosted_tools_mode: How to integrate hosted tools ('complement', 'replace', 'fallback')
    """

    organization: str = field(
        default_factory=lambda: (
            os.getenv("GITHUB_SPI_ORGANIZATION")
            or os.getenv("OSDU_AGENT_ORGANIZATION")
            or "azure"  # Final default
        )
    )

    repositories: List[str] = field(
        default_factory=lambda: os.getenv(
            "OSDU_AGENT_REPOSITORIES",
            "partition,legal,entitlements,schema,file,storage,indexer,indexer-queue,search,workflow",
        ).split(",")
    )

    repos_root: Path = field(
        default_factory=lambda: (
            Path(env_val).resolve()
            if (env_val := os.getenv("OSDU_AGENT_REPOS_ROOT"))
            else (Path.cwd() / "repos").resolve()
        )
    )

    github_token: Optional[str] = field(default_factory=_get_github_token)
    github_username: Optional[str] = field(default_factory=_get_github_username)

    # GitLab Configuration
    gitlab_url: Optional[str] = field(
        default_factory=lambda: os.getenv("GITLAB_URL", "https://gitlab.com")
    )

    gitlab_token: Optional[str] = field(default_factory=_get_gitlab_token)
    gitlab_username: Optional[str] = field(default_factory=_get_gitlab_username)

    gitlab_default_group: Optional[str] = field(
        default_factory=lambda: os.getenv("GITLAB_DEFAULT_GROUP")
    )

    azure_openai_endpoint: Optional[str] = field(
        default_factory=lambda: os.getenv("AZURE_OPENAI_ENDPOINT")
    )

    azure_openai_deployment: str = field(
        default_factory=lambda: os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-5-mini")
    )

    azure_openai_api_version: str = field(
        default_factory=lambda: os.getenv("AZURE_OPENAI_API_VERSION")
        or os.getenv("AZURE_OPENAI_VERSION")
        or "2025-03-01-preview"
    )

    azure_openai_api_key: Optional[str] = field(
        default_factory=lambda: os.getenv("AZURE_OPENAI_API_KEY")
    )

    # Internal Maven MCP configuration
    maven_mcp_command: str = "uvx"
    maven_mcp_args: List[str] = field(
        default_factory=lambda: [
            "--quiet",  # Suppress uvx output
            # Uses latest version by default (no pinning)
            # Pin to specific version via MAVEN_MCP_VERSION env var (e.g., "mvn-mcp-server==2.3.0")
            # Latest version includes per-module vulnerability tracking and severity filtering
            os.getenv("MAVEN_MCP_VERSION", "mvn-mcp-server"),
            # Note: stderr is redirected to logs/maven_mcp_*.log by QuietMCPStdioTool
        ]
    )

    # OSDU MCP Configuration (experimental - feature flagged)
    # Environment variables for OSDU MCP server are passed directly to subprocess
    # and validated by OsduMCPManager (not stored in config)
    osdu_mcp_enabled: bool = field(
        default_factory=lambda: os.getenv("ENABLE_OSDU_MCP_SERVER", "false").lower() == "true"
    )

    osdu_mcp_command: str = "uvx"
    osdu_mcp_args: List[str] = field(
        default_factory=lambda: [
            "--quiet",  # Suppress uvx output
            # Uses latest version by default (no pinning)
            # Pin to specific version via OSDU_MCP_VERSION env var (e.g., "osdu-mcp-server==1.0.0")
            # Latest version provides 31 tools, 3 prompts, 4 resources via FastMCP
            os.getenv("OSDU_MCP_VERSION", "osdu-mcp-server"),
            # Note: stderr is redirected to logs/osdu_mcp_*.log by QuietMCPStdioTool
        ]
    )

    # Default Platform Configuration
    default_platform: Literal["github", "gitlab"] = field(
        default_factory=lambda: cast(
            Literal["github", "gitlab"],
            (
                os.getenv("OSDU_AGENT_PLATFORM", "gitlab")
                if os.getenv("OSDU_AGENT_PLATFORM", "gitlab") in ("github", "gitlab")
                else "gitlab"
            ),
        )
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
