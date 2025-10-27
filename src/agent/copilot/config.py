"""Configuration management for OSDU Agent automation workflows."""

import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict


class CopilotConfig(BaseSettings):
    """Configuration for copilot wrapper"""

    model_config = SettingsConfigDict(env_file=".env", env_prefix="COPILOT_", extra="ignore")

    organization: str = "azure"
    template_repo: str = "azure/osdu-spi"
    default_branch: str = "main"
    log_directory: Optional[str] = None

    def __init__(self, **kwargs):
        """Initialize with support for GITHUB_SPI_* variables (preferred over COPILOT_*)."""
        super().__init__(**kwargs)

        # Override with GITHUB_SPI_* variables if set (takes precedence)
        if os.getenv("GITHUB_SPI_ORGANIZATION"):
            self.organization = os.getenv("GITHUB_SPI_ORGANIZATION")

        if os.getenv("GITHUB_SPI_REPO"):
            self.template_repo = os.getenv("GITHUB_SPI_REPO")

        if os.getenv("GITHUB_SPI_BRANCH"):
            self.default_branch = os.getenv("GITHUB_SPI_BRANCH")


# Load environment variables from .env if it exists
env_file = Path(__file__).parent.parent.parent / ".env"
if env_file.exists():
    load_dotenv(env_file)

# Initialize configuration
config = CopilotConfig()

# Only create log directory if configured
log_dir: Optional[Path] = None
if config.log_directory:
    log_dir = Path(config.log_directory)
    log_dir.mkdir(exist_ok=True)
