"""OSDU MCP Server integration for OSDU platform operations."""

import logging
import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from agent_framework import MCPStdioTool

from agent.config import AgentConfig
from agent.copilot.config import log_dir
from agent.mcp.maven_mcp import QuietMCPStdioTool

logger = logging.getLogger(__name__)


class OsduMCPManager:
    """
    Manages OSDU MCP server lifecycle and integration.

    Provides OSDU platform capabilities including:
    - Core operations (health checks, entitlements)
    - Partition management (list, get, create, update, delete)
    - Legal tag administration (CRUD, batch ops, search)
    - Schema operations (discovery, search, management)
    - Search and discovery (Elasticsearch queries)
    - Data storage (CRUD with versioning, bulk operations)

    Features (via FastMCP):
    - 31 tools across 6 OSDU service domains
    - 3 guided prompts for common workflows
    - 4 template resources for reference

    This is an experimental feature controlled by ENABLE_OSDU_MCP_SERVER env var.
    """

    # Required environment variables for OSDU MCP server
    REQUIRED_ENV_VARS = [
        "OSDU_MCP_SERVER_URL",
        "OSDU_MCP_SERVER_DATA_PARTITION",
        "AZURE_TENANT_ID",
        "AZURE_CLIENT_ID",
    ]

    # Optional environment variables (have defaults in MCP server)
    OPTIONAL_ENV_VARS = [
        "OSDU_MCP_SERVER_DOMAIN",
        "OSDU_MCP_PARTITION_ALLOW_WRITE",
        "OSDU_MCP_ENABLE_WRITE_MODE",
        "OSDU_MCP_ENABLE_DELETE_MODE",
    ]

    def __init__(self, config: AgentConfig):
        """
        Initialize OSDU MCP Manager.

        Args:
            config: Agent configuration with OSDU MCP settings
        """
        self.config = config
        self.mcp_tool: Optional[MCPStdioTool] = None
        self._validated = False

    def validate_prerequisites(self) -> bool:
        """
        Validate that required commands are available.

        Returns:
            True if prerequisites met, False otherwise
        """
        # Check if command exists
        command_path = shutil.which(self.config.osdu_mcp_command)
        if not command_path:
            logger.warning(
                f"OSDU MCP disabled: '{self.config.osdu_mcp_command}' command not found. "
                f"Install with: pip install uv"
            )
            return False

        self._validated = True
        return True

    def validate_required_env_vars(self) -> tuple[bool, list[str]]:
        """
        Validate that required environment variables are set.

        Returns:
            Tuple of (all_present, missing_vars)
            - all_present: True if all required vars are set
            - missing_vars: List of missing variable names
        """
        missing = []
        for var_name in self.REQUIRED_ENV_VARS:
            value = os.getenv(var_name)
            if not value or not value.strip():
                missing.append(var_name)

        all_present = len(missing) == 0
        return all_present, missing

    async def __aenter__(self) -> "OsduMCPManager":
        """
        Async context manager entry.

        Returns:
            Self with initialized MCP tool
        """
        if not self.validate_prerequisites():
            logger.warning("OSDU MCP prerequisites not met, continuing without OSDU tools")
            return self

        # Validate required environment variables before attempting to start server
        env_valid, missing_vars = self.validate_required_env_vars()
        if not env_valid:
            logger.warning(
                f"OSDU MCP disabled: Missing required environment variables: {', '.join(missing_vars)}"
            )
            logger.info(
                "OSDU MCP requires: OSDU_MCP_SERVER_URL, OSDU_MCP_SERVER_DATA_PARTITION, "
                "AZURE_TENANT_ID, AZURE_CLIENT_ID"
            )
            return self

        try:
            # Build subprocess environment - pass all OSDU env vars
            subprocess_env = os.environ.copy()

            # Determine stderr log path
            stderr_log_path: Optional[Path] = None
            if log_dir is not None:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                stderr_log_path = log_dir / f"osdu_mcp_{timestamp}.log"
            else:
                # Logging disabled - redirect to null device
                stderr_log_path = Path(os.devnull)

            # Initialize QuietMCPStdioTool with stderr redirection
            # This prevents MCP server output from interfering with Rich Live display
            self.mcp_tool = QuietMCPStdioTool(
                name="osdu-mcp-server",
                command=self.config.osdu_mcp_command,
                args=self.config.osdu_mcp_args,
                env=subprocess_env,
                stderr_log_path=stderr_log_path,
            )

            # Enter the MCP tool's context
            await self.mcp_tool.__aenter__()

            logger.info("OSDU MCP server initialized successfully")
            logger.info(f"Available capabilities: {len(self.tools)} tool(s)")

        except FileNotFoundError as e:
            logger.error(
                f"OSDU MCP server not found: {e}. " f"Install with: uvx osdu-mcp-server==1.0.0"
            )
            self.mcp_tool = None
        except Exception as e:
            logger.error(f"Failed to initialize OSDU MCP server: {e}")
            self.mcp_tool = None

        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """
        Async context manager exit.

        Args:
            exc_type: Exception type if any
            exc_val: Exception value if any
            exc_tb: Exception traceback if any
        """
        if self.mcp_tool:
            try:
                await self.mcp_tool.__aexit__(exc_type, exc_val, exc_tb)
                logger.info("OSDU MCP server cleaned up successfully")
            except Exception as e:
                logger.error(f"Error cleaning up OSDU MCP server: {e}")

    @property
    def tools(self) -> List:
        """
        Get OSDU MCP tools for agent integration.

        Returns:
            List containing MCP tool if available, empty list otherwise
        """
        if self.mcp_tool:
            return [self.mcp_tool]
        return []

    @property
    def is_available(self) -> bool:
        """
        Check if OSDU MCP is available.

        Returns:
            True if OSDU MCP tools are available
        """
        return self.mcp_tool is not None
