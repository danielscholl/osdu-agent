"""Tests for hosted tools integration."""

import pytest
from unittest.mock import Mock, MagicMock, patch

from agent.config import AgentConfig
from agent.hosted_tools import (
    HostedToolsManager,
    detect_available_hosted_tools,
    detect_hosted_tools_support,
    is_client_compatible,
)
from agent.hosted_tools.compatibility import get_client_type_name
from agent.filesystem import create_hybrid_filesystem_tools


class TestCompatibilityDetection:
    """Test suite for compatibility detection utilities."""

    def test_detect_hosted_tools_support_available(self):
        """Test detection when hosted tools are available."""
        # This should return True since we have agent_framework v1.0.0b251007
        result = detect_hosted_tools_support()
        assert isinstance(result, bool)
        # Should be True in current environment
        assert result is True

    def test_detect_available_hosted_tools(self):
        """Test detection of available hosted tool types."""
        tools = detect_available_hosted_tools()
        assert isinstance(tools, list)

        # Should include at least file_search, code_interpreter, web_search
        expected_tools = {"file_search", "code_interpreter", "web_search"}
        assert expected_tools.issubset(set(tools))

    @patch("agent.hosted_tools.compatibility.hasattr")
    def test_detect_hosted_tools_support_unavailable(self, mock_hasattr):
        """Test detection when hosted tools are not available."""
        # Mock hasattr to return False for all hosted tools
        mock_hasattr.return_value = False

        result = detect_hosted_tools_support()
        assert isinstance(result, bool)
        # Should return False when hosted tools are not available
        assert result is False

    def test_is_client_compatible_with_openai_client(self):
        """Test client compatibility check with AzureOpenAIResponsesClient."""
        from agent_framework.azure import AzureOpenAIResponsesClient

        # Create a mock client (don't need real credentials for compatibility check)
        mock_client = Mock(spec=AzureOpenAIResponsesClient)

        result = is_client_compatible(mock_client)
        assert isinstance(result, bool)
        # OpenAI Responses client is not the AI Agent client
        assert result is False

    def test_get_client_type_name(self):
        """Test client type name extraction."""
        mock_client = Mock()
        mock_client.__class__.__name__ = "AzureOpenAIResponsesClient"

        name = get_client_type_name(mock_client)
        assert name == "AzureOpenAIResponses"


class TestHostedToolsManager:
    """Test suite for HostedToolsManager class."""

    def test_manager_initialization_disabled(self):
        """Test manager when hosted tools are disabled in config."""
        config = AgentConfig()
        config.hosted_tools_enabled = False

        manager = HostedToolsManager(config)

        assert manager.is_available is False
        assert len(manager.tools) == 0
        assert manager.available_tool_types == []

    def test_manager_initialization_enabled(self):
        """Test manager when hosted tools are enabled."""
        config = AgentConfig()
        config.hosted_tools_enabled = True

        # Create mock client
        mock_client = Mock()

        manager = HostedToolsManager(config, chat_client=mock_client)

        # Should detect framework support
        assert isinstance(manager.is_available, bool)

        # Since framework supports hosted tools, should be available
        assert manager.is_available is True

        # Should have tools initialized
        tools = manager.tools
        assert isinstance(tools, list)
        # With a Mock client (not AzureAIAgentClient), only code_interpreter is available
        # Other tools require specific client types
        assert len(tools) >= 1

    def test_manager_get_status_summary(self):
        """Test status summary generation."""
        config = AgentConfig()
        config.hosted_tools_enabled = True
        config.hosted_tools_mode = "complement"

        manager = HostedToolsManager(config)
        status = manager.get_status_summary()

        assert isinstance(status, dict)
        assert "enabled" in status
        assert "available" in status
        assert "tool_count" in status
        assert "mode" in status
        assert status["enabled"] is True
        assert status["mode"] == "complement"

    def test_manager_repr(self):
        """Test string representation."""
        config = AgentConfig()
        manager = HostedToolsManager(config)

        repr_str = repr(manager)
        assert "HostedToolsManager" in repr_str
        assert "available=" in repr_str
        assert "tools=" in repr_str


class TestConfiguration:
    """Test suite for hosted tools configuration."""

    def test_config_defaults(self):
        """Test default configuration values."""
        config = AgentConfig()

        assert config.client_type == "openai"
        assert config.hosted_tools_enabled is False
        assert config.hosted_tools_mode == "complement"

    def test_config_validation_valid(self):
        """Test config validation with valid values."""
        config = AgentConfig()
        config.client_type = "openai"
        config.hosted_tools_mode = "replace"

        # Should not raise
        config.validate()

    def test_config_validation_invalid_client_type(self):
        """Test config validation with invalid client type."""
        config = AgentConfig()
        config.client_type = "invalid"  # type: ignore

        with pytest.raises(ValueError, match="client_type must be"):
            config.validate()

    def test_config_validation_invalid_mode(self):
        """Test config validation with invalid mode."""
        config = AgentConfig()
        config.hosted_tools_mode = "invalid"  # type: ignore

        with pytest.raises(ValueError, match="hosted_tools_mode must be"):
            config.validate()


class TestHybridToolRegistration:
    """Test suite for hybrid filesystem tool registration."""

    def test_hybrid_tools_disabled(self):
        """Test hybrid registration when hosted tools disabled."""
        config = AgentConfig()
        config.hosted_tools_enabled = False

        tools = create_hybrid_filesystem_tools(config, hosted_tools_manager=None)

        assert isinstance(tools, list)
        # Should have 5 custom tools (list_files, read_file, search_in_files,
        # parse_pom_dependencies, find_dependency_versions)
        assert len(tools) == 5

    def test_hybrid_tools_enabled_complement_mode(self):
        """Test hybrid registration in complement mode."""
        config = AgentConfig()
        config.hosted_tools_enabled = True
        config.hosted_tools_mode = "complement"

        # Create manager
        manager = HostedToolsManager(config)

        tools = create_hybrid_filesystem_tools(config, hosted_tools_manager=manager)

        assert isinstance(tools, list)

        if manager.is_available:
            # Should have hosted tools + all custom tools
            # With default client (no AI Agent client), only code_interpreter is available
            # So: 1 hosted + 5 custom = 6 tools
            assert len(tools) >= 6
        else:
            # Fallback to custom tools only
            assert len(tools) == 5

    def test_hybrid_tools_enabled_replace_mode(self):
        """Test hybrid registration in replace mode."""
        config = AgentConfig()
        config.hosted_tools_enabled = True
        config.hosted_tools_mode = "replace"

        manager = HostedToolsManager(config)

        tools = create_hybrid_filesystem_tools(config, hosted_tools_manager=manager)

        assert isinstance(tools, list)

        if manager.is_available:
            # Should have hosted tools + specialized custom tools
            # With default client: 1 hosted + 2 specialized = 3 tools
            assert len(tools) >= 3
        else:
            # Fallback to all custom tools
            assert len(tools) == 5

    def test_hybrid_tools_enabled_fallback_mode(self):
        """Test hybrid registration in fallback mode."""
        config = AgentConfig()
        config.hosted_tools_enabled = True
        config.hosted_tools_mode = "fallback"

        manager = HostedToolsManager(config)

        tools = create_hybrid_filesystem_tools(config, hosted_tools_manager=manager)

        assert isinstance(tools, list)

        if manager.is_available:
            # Should have all custom tools + hosted tools
            # With default client: 5 custom + 1 hosted = 6 tools
            assert len(tools) >= 6
        else:
            # Fallback to custom tools only
            assert len(tools) == 5

    def test_hybrid_tools_specialized_always_included(self):
        """Test that specialized tools are always included regardless of mode."""
        config = AgentConfig()
        config.hosted_tools_enabled = True

        for mode in ["complement", "replace", "fallback"]:
            config.hosted_tools_mode = mode
            manager = HostedToolsManager(config)

            tools = create_hybrid_filesystem_tools(config, hosted_tools_manager=manager)

            # Check that specialized tool names are present
            # Note: Tools are functions, so we check their names
            tool_names = [getattr(tool, "__name__", str(tool)) for tool in tools]

            # Specialized tools should always be present
            assert any("parse_pom" in str(name) for name in tool_names)
            assert any("find_dependency" in str(name) for name in tool_names)


class TestAgentIntegration:
    """Test suite for agent integration with hosted tools."""

    @pytest.fixture
    def mock_github_tools(self):
        """Mock GitHub tools to avoid network calls."""
        with patch("agent.agent.create_github_tools") as mock:
            mock.return_value = []
            yield mock

    @pytest.fixture
    def mock_credentials(self):
        """Mock Azure credentials."""
        with patch("agent.agent.AzureCliCredential") as mock:
            mock.return_value = MagicMock()
            yield mock

    def test_agent_initialization_with_hosted_tools_disabled(
        self, mock_github_tools, mock_credentials
    ):
        """Test agent initializes correctly with hosted tools disabled."""
        from agent.agent import Agent

        config = AgentConfig()
        config.hosted_tools_enabled = False

        with patch.dict(
            "os.environ",
            {
                "AZURE_OPENAI_ENDPOINT": "https://test.openai.azure.com",
                "AZURE_OPENAI_DEPLOYMENT_NAME": "gpt-4",
            },
        ):
            agent = Agent(config=config)

            assert agent.hosted_tools_manager is not None
            assert agent.hosted_tools_manager.is_available is False
            assert isinstance(agent.filesystem_tools, list)

    def test_agent_initialization_with_hosted_tools_enabled(
        self, mock_github_tools, mock_credentials
    ):
        """Test agent initializes correctly with hosted tools enabled."""
        from agent.agent import Agent

        config = AgentConfig()
        config.hosted_tools_enabled = True
        config.hosted_tools_mode = "complement"

        with patch.dict(
            "os.environ",
            {
                "AZURE_OPENAI_ENDPOINT": "https://test.openai.azure.com",
                "AZURE_OPENAI_DEPLOYMENT_NAME": "gpt-4",
            },
        ):
            agent = Agent(config=config)

            assert agent.hosted_tools_manager is not None
            # Should have tools available (framework supports it)
            assert agent.hosted_tools_manager.is_available is True
            assert isinstance(agent.filesystem_tools, list)
            # Should have more tools due to hosted + custom
            assert len(agent.filesystem_tools) >= 5
