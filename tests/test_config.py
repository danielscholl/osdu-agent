"""Tests for configuration module."""

import os
from unittest.mock import patch

import pytest

from agent.config import AgentConfig


def test_config_defaults():
    """Test default configuration values with current variable names."""
    with patch.dict(
        os.environ,
        {
            "GITHUB_SPI_ORGANIZATION": "test-org",
            "OSDU_AGENT_REPOSITORIES": "repo1,repo2",
        },
        clear=True,
    ):
        config = AgentConfig()
        assert config.organization == "test-org"
        assert config.repositories == ["repo1", "repo2"]


def test_config_backwards_compatibility_organization():
    """Test backwards compatibility with old OSDU_AGENT_ORGANIZATION variable name."""
    with patch.dict(
        os.environ,
        {
            "OSDU_AGENT_ORGANIZATION": "old-org",
            "OSDU_AGENT_REPOSITORIES": "repo1,repo2",
        },
        clear=True,
    ):
        config = AgentConfig()
        assert config.organization == "old-org"
        assert config.repositories == ["repo1", "repo2"]


def test_config_organization_name_precedence():
    """Test that GITHUB_SPI_ORGANIZATION takes precedence over OSDU_AGENT_ORGANIZATION."""
    with patch.dict(
        os.environ,
        {
            "GITHUB_SPI_ORGANIZATION": "new-org",
            "OSDU_AGENT_ORGANIZATION": "old-org",
            "OSDU_AGENT_REPOSITORIES": "repo1,repo2",
        },
        clear=True,
    ):
        config = AgentConfig()
        assert config.organization == "new-org"  # GITHUB_SPI_ORGANIZATION takes precedence
        assert config.repositories == ["repo1", "repo2"]


def test_config_custom_values():
    """Test configuration with custom values."""
    config = AgentConfig(organization="custom-org", repositories=["custom-repo"])

    assert config.organization == "custom-org"
    assert config.repositories == ["custom-repo"]


def test_config_validation_empty_org():
    """Test configuration validation fails with empty organization."""
    with pytest.raises(ValueError, match="organization is required"):
        AgentConfig(organization="", repositories=["repo1"])


def test_config_validation_empty_repos():
    """Test configuration validation fails with empty repositories."""
    with pytest.raises(ValueError, match="repositories list cannot be empty"):
        AgentConfig(organization="test-org", repositories=[])


def test_get_repo_full_name():
    """Test getting full repository name."""
    config = AgentConfig(organization="test-org", repositories=["test-repo"])

    assert config.get_repo_full_name("test-repo") == "test-org/test-repo"
    assert config.get_repo_full_name("another-repo") == "test-org/another-repo"


def test_config_strips_whitespace():
    """Test that repository names are stripped of whitespace."""
    config = AgentConfig(organization="test-org", repositories=["repo1 ", " repo2", "  repo3  "])

    assert config.repositories == ["repo1", "repo2", "repo3"]


def test_config_from_env_var_parsing():
    """Test parsing repositories from environment variable with whitespace."""
    with patch.dict(
        os.environ,
        {"OSDU_AGENT_REPOSITORIES": "partition, legal , entitlements"},
        clear=True,
    ):
        config = AgentConfig()
        assert config.repositories == ["partition", "legal", "entitlements"]


def test_config_maven_mcp_defaults():
    """Test Maven MCP default configuration values."""
    with patch.dict(os.environ, {}, clear=True):
        config = AgentConfig()
        assert config.maven_mcp_command == "uvx"
        assert config.maven_mcp_args == ["--quiet", "mvn-mcp-server==2.3.0"]


def test_config_maven_mcp_version_override():
    """Test Maven MCP version can be overridden via environment variable."""
    with patch.dict(os.environ, {"MAVEN_MCP_VERSION": "mvn-mcp-server==2.3.0"}, clear=True):
        config = AgentConfig()
        assert config.maven_mcp_args == ["--quiet", "mvn-mcp-server==2.3.0"]

    # Test unpinned version
    with patch.dict(os.environ, {"MAVEN_MCP_VERSION": "mvn-mcp-server"}, clear=True):
        config = AgentConfig()
        assert config.maven_mcp_args == ["--quiet", "mvn-mcp-server"]


def test_github_token_from_cli():
    """Test GitHub token retrieval from gh CLI."""
    from unittest.mock import MagicMock
    from agent.config import _get_github_token

    with patch("agent.config.subprocess.run") as mock_run:
        with patch.dict(os.environ, {}, clear=True):
            # Mock successful gh auth token command
            mock_result = MagicMock()
            mock_result.returncode = 0
            mock_result.stdout = "ghp_test_token_from_cli\n"
            mock_run.return_value = mock_result

            token = _get_github_token()

            assert token == "ghp_test_token_from_cli"
            mock_run.assert_called_once()


def test_github_token_from_env_var():
    """Test GitHub token fallback to environment variable."""
    from agent.config import _get_github_token

    with patch("agent.config.subprocess.run") as mock_run:
        with patch.dict(os.environ, {"GITHUB_TOKEN": "ghp_env_token"}, clear=True):
            # Mock gh CLI not available
            mock_run.side_effect = FileNotFoundError()

            token = _get_github_token()

            assert token == "ghp_env_token"


def test_gitlab_token_from_cli():
    """Test GitLab token retrieval from glab CLI."""
    from unittest.mock import MagicMock
    from agent.config import _get_gitlab_token

    with patch("agent.config.subprocess.run") as mock_run:
        with patch.dict(os.environ, {}, clear=True):
            # Mock successful glab auth status --show-token command
            mock_result = MagicMock()
            mock_result.returncode = 0
            mock_result.stderr = "✓ Logged in\n  ✓ Token found: glpat_test_token_from_cli\n"
            mock_result.stdout = ""
            mock_run.return_value = mock_result

            token = _get_gitlab_token()

            assert token == "glpat_test_token_from_cli"
            mock_run.assert_called_once()


def test_gitlab_token_from_env_var():
    """Test GitLab token fallback to environment variable."""
    from agent.config import _get_gitlab_token

    with patch("agent.config.subprocess.run") as mock_run:
        with patch.dict(os.environ, {"GITLAB_TOKEN": "glpat_env_token"}, clear=True):
            # Mock glab CLI not available
            mock_run.side_effect = FileNotFoundError()

            token = _get_gitlab_token()

            assert token == "glpat_env_token"


def test_gitlab_token_multi_instance_with_failure():
    """Test GitLab token detection with multiple instances where one fails (exit code 1)."""
    from unittest.mock import MagicMock
    from agent.config import _get_gitlab_token

    with patch("agent.config.subprocess.run") as mock_run:
        with patch.dict(os.environ, {}, clear=True):
            # Mock glab auth status with multi-instance output
            # Exit code 1 because one instance failed, but another has a valid token
            mock_result = MagicMock()
            mock_result.returncode = 1
            mock_result.stderr = """gitlab.com
  x API call failed: 401 Unauthorized
  ! No token found
community.opengroup.org
  ✓ Logged in as danielscholl
  ✓ Token found: glpat_multi_instance_token

ERROR: could not authenticate to one or more instances
"""
            mock_result.stdout = ""
            mock_run.return_value = mock_result

            token = _get_gitlab_token()

            # Token should still be extracted despite returncode == 1
            assert token == "glpat_multi_instance_token"
            mock_run.assert_called_once()
