"""Configuration management for Copilot CLI wrapper."""

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
