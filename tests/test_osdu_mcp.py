"""Tests for OSDU MCP integration."""

from unittest.mock import AsyncMock, patch

import pytest

from agent.config import AgentConfig
from agent.mcp import OsduMCPManager


@pytest.fixture
def config():
    """Create config for testing."""
    return AgentConfig()


@pytest.fixture
def mock_env_vars(monkeypatch):
    """Mock required environment variables."""
    monkeypatch.setenv("OSDU_MCP_SERVER_URL", "https://test.osdu.org")
    monkeypatch.setenv("OSDU_MCP_SERVER_DATA_PARTITION", "test-partition")
    monkeypatch.setenv("AZURE_TENANT_ID", "test-tenant")
    monkeypatch.setenv("AZURE_CLIENT_ID", "test-client")


class TestOsduMCPManager:
    """Test OSDU MCP Manager."""

    def test_init(self, config):
        """Test initialization."""
        manager = OsduMCPManager(config)
        assert manager.config == config
        assert manager.mcp_tool is None
        assert manager._validated is False

    @patch("agent.mcp.osdu_mcp.shutil.which")
    def test_validate_prerequisites_success(self, mock_which, config):
        """Test successful prerequisite validation."""
        mock_which.return_value = "/usr/local/bin/uvx"
        manager = OsduMCPManager(config)

        result = manager.validate_prerequisites()

        assert result is True
        assert manager._validated is True
        mock_which.assert_called_once_with("uvx")

    @patch("agent.mcp.osdu_mcp.shutil.which")
    def test_validate_prerequisites_failure(self, mock_which, config):
        """Test failed prerequisite validation."""
        mock_which.return_value = None
        manager = OsduMCPManager(config)

        result = manager.validate_prerequisites()

        assert result is False
        assert manager._validated is False
        mock_which.assert_called_once_with("uvx")

    def test_validate_required_env_vars_all_present(self, config, mock_env_vars):
        """Test environment variable validation with all vars present."""
        manager = OsduMCPManager(config)

        all_present, missing = manager.validate_required_env_vars()

        assert all_present is True
        assert missing == []

    def test_validate_required_env_vars_missing_url(self, config, monkeypatch):
        """Test environment variable validation with missing URL."""
        # Ensure URL is not set
        monkeypatch.delenv("OSDU_MCP_SERVER_URL", raising=False)
        monkeypatch.setenv("OSDU_MCP_SERVER_DATA_PARTITION", "test-partition")
        monkeypatch.setenv("AZURE_TENANT_ID", "test-tenant")
        monkeypatch.setenv("AZURE_CLIENT_ID", "test-client")

        manager = OsduMCPManager(config)
        all_present, missing = manager.validate_required_env_vars()

        assert all_present is False
        assert "OSDU_MCP_SERVER_URL" in missing

    def test_validate_required_env_vars_missing_partition(self, config, monkeypatch):
        """Test environment variable validation with missing partition."""
        monkeypatch.setenv("OSDU_MCP_SERVER_URL", "https://test.osdu.org")
        monkeypatch.delenv("OSDU_MCP_SERVER_DATA_PARTITION", raising=False)
        monkeypatch.setenv("AZURE_TENANT_ID", "test-tenant")
        monkeypatch.setenv("AZURE_CLIENT_ID", "test-client")

        manager = OsduMCPManager(config)
        all_present, missing = manager.validate_required_env_vars()

        assert all_present is False
        assert "OSDU_MCP_SERVER_DATA_PARTITION" in missing

    def test_validate_required_env_vars_missing_azure_creds(self, config, monkeypatch):
        """Test environment variable validation with missing Azure credentials."""
        monkeypatch.setenv("OSDU_MCP_SERVER_URL", "https://test.osdu.org")
        monkeypatch.setenv("OSDU_MCP_SERVER_DATA_PARTITION", "test-partition")
        monkeypatch.delenv("AZURE_TENANT_ID", raising=False)
        monkeypatch.delenv("AZURE_CLIENT_ID", raising=False)

        manager = OsduMCPManager(config)
        all_present, missing = manager.validate_required_env_vars()

        assert all_present is False
        assert "AZURE_TENANT_ID" in missing
        assert "AZURE_CLIENT_ID" in missing

    def test_validate_required_env_vars_empty_string(self, config, monkeypatch):
        """Test environment variable validation treats empty strings as missing."""
        monkeypatch.setenv("OSDU_MCP_SERVER_URL", "")
        monkeypatch.setenv("OSDU_MCP_SERVER_DATA_PARTITION", "test-partition")
        monkeypatch.setenv("AZURE_TENANT_ID", "test-tenant")
        monkeypatch.setenv("AZURE_CLIENT_ID", "test-client")

        manager = OsduMCPManager(config)
        all_present, missing = manager.validate_required_env_vars()

        assert all_present is False
        assert "OSDU_MCP_SERVER_URL" in missing

    @pytest.mark.asyncio
    @patch("agent.mcp.osdu_mcp.shutil.which")
    async def test_context_manager_prerequisites_not_met(self, mock_which, config):
        """Test context manager when prerequisites not met."""
        mock_which.return_value = None
        manager = OsduMCPManager(config)

        async with manager as m:
            assert m.mcp_tool is None
            assert m.tools == []
            assert m.is_available is False

    @pytest.mark.asyncio
    @patch("agent.mcp.osdu_mcp.shutil.which")
    async def test_context_manager_missing_env_vars(self, mock_which, config, monkeypatch):
        """Test context manager when environment variables are missing."""
        mock_which.return_value = "/usr/local/bin/uvx"
        # Remove all required env vars
        monkeypatch.delenv("OSDU_MCP_SERVER_URL", raising=False)
        monkeypatch.delenv("OSDU_MCP_SERVER_DATA_PARTITION", raising=False)
        monkeypatch.delenv("AZURE_TENANT_ID", raising=False)
        monkeypatch.delenv("AZURE_CLIENT_ID", raising=False)

        manager = OsduMCPManager(config)

        async with manager as m:
            assert m.mcp_tool is None
            assert m.tools == []
            assert m.is_available is False

    @pytest.mark.asyncio
    @patch("agent.mcp.osdu_mcp.shutil.which")
    @patch("agent.mcp.osdu_mcp.QuietMCPStdioTool")
    async def test_context_manager_success(
        self, mock_mcp_tool_class, mock_which, config, mock_env_vars
    ):
        """Test successful context manager initialization."""
        mock_which.return_value = "/usr/local/bin/uvx"
        mock_tool_instance = AsyncMock()
        mock_mcp_tool_class.return_value = mock_tool_instance

        manager = OsduMCPManager(config)

        async with manager as m:
            assert m.mcp_tool == mock_tool_instance
            assert len(m.tools) == 1
            assert m.is_available is True
            mock_tool_instance.__aenter__.assert_called_once()

        mock_tool_instance.__aexit__.assert_called_once()

    @pytest.mark.asyncio
    @patch("agent.mcp.osdu_mcp.shutil.which")
    @patch("agent.mcp.osdu_mcp.QuietMCPStdioTool")
    async def test_context_manager_file_not_found(
        self, mock_mcp_tool_class, mock_which, config, mock_env_vars
    ):
        """Test context manager when MCP server not found."""
        mock_which.return_value = "/usr/local/bin/uvx"
        mock_tool_instance = AsyncMock()
        mock_tool_instance.__aenter__.side_effect = FileNotFoundError("osdu-mcp-server not found")
        mock_mcp_tool_class.return_value = mock_tool_instance

        manager = OsduMCPManager(config)

        async with manager as m:
            assert m.mcp_tool is None
            assert m.tools == []
            assert m.is_available is False

    @pytest.mark.asyncio
    @patch("agent.mcp.osdu_mcp.shutil.which")
    @patch("agent.mcp.osdu_mcp.QuietMCPStdioTool")
    async def test_context_manager_general_error(
        self, mock_mcp_tool_class, mock_which, config, mock_env_vars
    ):
        """Test context manager with general error."""
        mock_which.return_value = "/usr/local/bin/uvx"
        mock_tool_instance = AsyncMock()
        mock_tool_instance.__aenter__.side_effect = Exception("Connection error")
        mock_mcp_tool_class.return_value = mock_tool_instance

        manager = OsduMCPManager(config)

        async with manager as m:
            assert m.mcp_tool is None
            assert m.tools == []
            assert m.is_available is False

    @pytest.mark.asyncio
    @patch("agent.mcp.osdu_mcp.shutil.which")
    @patch("agent.mcp.osdu_mcp.QuietMCPStdioTool")
    async def test_context_manager_cleanup_error(
        self, mock_mcp_tool_class, mock_which, config, mock_env_vars
    ):
        """Test context manager cleanup with error."""
        mock_which.return_value = "/usr/local/bin/uvx"
        mock_tool_instance = AsyncMock()
        mock_tool_instance.__aexit__.side_effect = Exception("Cleanup error")
        mock_mcp_tool_class.return_value = mock_tool_instance

        manager = OsduMCPManager(config)

        # Should not raise exception even if cleanup fails
        async with manager:
            pass

    def test_tools_property_no_tool(self, config):
        """Test tools property when no tool initialized."""
        manager = OsduMCPManager(config)
        assert manager.tools == []

    @pytest.mark.asyncio
    @patch("agent.mcp.osdu_mcp.shutil.which")
    @patch("agent.mcp.osdu_mcp.QuietMCPStdioTool")
    async def test_tools_property_with_tool(
        self, mock_mcp_tool_class, mock_which, config, mock_env_vars
    ):
        """Test tools property when tool is initialized."""
        mock_which.return_value = "/usr/local/bin/uvx"
        mock_tool_instance = AsyncMock()
        mock_mcp_tool_class.return_value = mock_tool_instance

        manager = OsduMCPManager(config)

        async with manager:
            assert len(manager.tools) == 1
            assert manager.tools[0] == mock_tool_instance

    def test_is_available_false(self, config):
        """Test is_available property when not available."""
        manager = OsduMCPManager(config)
        assert manager.is_available is False

    @pytest.mark.asyncio
    @patch("agent.mcp.osdu_mcp.shutil.which")
    @patch("agent.mcp.osdu_mcp.QuietMCPStdioTool")
    async def test_is_available_true(self, mock_mcp_tool_class, mock_which, config, mock_env_vars):
        """Test is_available property when available."""
        mock_which.return_value = "/usr/local/bin/uvx"
        mock_tool_instance = AsyncMock()
        mock_mcp_tool_class.return_value = mock_tool_instance

        manager = OsduMCPManager(config)

        async with manager:
            assert manager.is_available is True


class TestOsduMCPConfig:
    """Test OSDU MCP configuration in AgentConfig."""

    def test_osdu_mcp_disabled_by_default(self):
        """Test OSDU MCP is disabled by default."""
        config = AgentConfig()
        assert config.osdu_mcp_enabled is False

    def test_osdu_mcp_enabled_via_env_var(self, monkeypatch):
        """Test OSDU MCP can be enabled via environment variable."""
        monkeypatch.setenv("ENABLE_OSDU_MCP_SERVER", "true")
        config = AgentConfig()
        assert config.osdu_mcp_enabled is True

    def test_osdu_mcp_explicitly_disabled_via_env_var(self, monkeypatch):
        """Test OSDU MCP explicitly disabled."""
        monkeypatch.setenv("ENABLE_OSDU_MCP_SERVER", "false")
        config = AgentConfig()
        assert config.osdu_mcp_enabled is False

    def test_osdu_mcp_default_command(self):
        """Test OSDU MCP default command."""
        config = AgentConfig()
        assert config.osdu_mcp_command == "uvx"

    def test_osdu_mcp_default_args(self):
        """Test OSDU MCP default args."""
        config = AgentConfig()
        assert "--quiet" in config.osdu_mcp_args
        assert any("osdu-mcp-server==1.0.0" in arg for arg in config.osdu_mcp_args)

    def test_osdu_mcp_version_override(self, monkeypatch):
        """Test OSDU MCP version can be overridden."""
        monkeypatch.setenv("OSDU_MCP_VERSION", "osdu-mcp-server==2.0.0")
        config = AgentConfig()
        assert any("osdu-mcp-server==2.0.0" in arg for arg in config.osdu_mcp_args)
