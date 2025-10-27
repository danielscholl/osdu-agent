"""Abstract base class for all copilot runners."""

import os
import subprocess
from abc import ABC, abstractmethod
from collections import deque
from datetime import datetime
from importlib.resources.abc import Traversable
from pathlib import Path
from typing import TYPE_CHECKING, List, Optional, Union

from rich.console import Console
from rich.layout import Layout
from rich.panel import Panel
from rich.text import Text

from agent.copilot.config import log_dir

if TYPE_CHECKING:
    # Import BaseTracker for type hints only (used in line 60) to avoid circular imports
    from agent.copilot.base.tracker import BaseTracker


class _OutputPanelRenderable:
    """Rich renderable that rebuilds the output panel on each render."""

    def __init__(self, runner: "BaseRunner"):
        self.runner = runner

    def __rich__(self):
        return self.runner.get_output_panel()


console = Console(legacy_windows=False)
MIN_VISIBLE_OUTPUT_LINES = 12
MAX_VISIBLE_OUTPUT_LINES = 80
TERMINAL_PADDING_LINES = 2
DEFAULT_VISIBLE_OUTPUT_LINES = 40


class BaseRunner(ABC):
    """Abstract base class for all OSDU Agent automation workflow runners."""

    def __init__(
        self,
        prompt_file: Union[Path, Traversable],
        services: List[str],
    ):
        """Initialize base runner.

        Args:
            prompt_file: Path to the prompt template file
            services: List of service names to process
        """
        self.prompt_file = prompt_file
        self.services = services
        self.output_lines: deque[str] = deque(
            maxlen=200
        )  # Keep last 200 lines (supports multi-service output)
        self.full_output: List[str] = []  # Keep all output for logging
        self.tracker: Optional["BaseTracker"] = None  # Must be set by subclass
        self._output_panel_renderable = _OutputPanelRenderable(self)

        # Generate log file path only if logging is enabled
        # Subclasses should override log_prefix
        if log_dir is not None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            self.log_file = log_dir / f"{self.log_prefix}_{timestamp}.log"
        else:
            self.log_file = None

    @property
    @abstractmethod
    def log_prefix(self) -> str:
        """Return log file prefix for this runner type."""
        pass

    @abstractmethod
    def load_prompt(self) -> str:
        """Load and augment prompt with arguments.

        Returns:
            The augmented prompt string
        """
        pass

    @abstractmethod
    def parse_output(self, line: str) -> None:
        """Parse a line of copilot output for status updates.

        Args:
            line: Output line to parse
        """
        pass

    @abstractmethod
    def get_results_panel(self, return_code: int) -> Panel:
        """Generate final results panel.

        Args:
            return_code: Process return code

        Returns:
            Rich Panel with results display
        """
        pass

    def create_layout(self) -> Layout:
        """Create split layout with status and output.

        Returns:
            Layout with status and output panels
        """
        layout = Layout()
        layout.split_row(Layout(name="status", ratio=1), Layout(name="output", ratio=2))
        layout["output"].update(self._output_panel_renderable)
        return layout

    def _determine_visible_output_lines(self) -> int:
        """Calculate how many lines of agent output to render in the live panel."""
        env_value = os.getenv("OSDU_AGENT_VISIBLE_OUTPUT_LINES")

        if env_value:
            try:
                parsed = int(env_value)
                return max(MIN_VISIBLE_OUTPUT_LINES, min(parsed, MAX_VISIBLE_OUTPUT_LINES))
            except ValueError:
                # Fall back to console-based sizing
                pass

        try:
            terminal_height = console.size.height
        except Exception:  # pragma: no cover - terminal size lookup may fail
            terminal_height = 0

        if terminal_height and terminal_height > TERMINAL_PADDING_LINES + MIN_VISIBLE_OUTPUT_LINES:
            recommended = terminal_height - TERMINAL_PADDING_LINES
            return max(MIN_VISIBLE_OUTPUT_LINES, min(recommended, MAX_VISIBLE_OUTPUT_LINES))

        return DEFAULT_VISIBLE_OUTPUT_LINES

    def get_output_panel(self) -> Panel:
        """Create panel with scrolling output.

        Returns:
            Rich Panel with formatted output
        """
        visible_lines = self._determine_visible_output_lines()
        target_lines = min(
            max(visible_lines or DEFAULT_VISIBLE_OUTPUT_LINES, MIN_VISIBLE_OUTPUT_LINES),
            MAX_VISIBLE_OUTPUT_LINES,
        )
        panel_height = target_lines + 2  # account for panel border

        total_lines = 0

        if not self.output_lines:
            output_text = Text("Waiting for output...", style="dim")
        else:
            # Join lines and create text
            output_text = Text()
            lines = list(self.output_lines)
            total_lines = len(lines)

            if total_lines > target_lines:
                truncated = total_lines - target_lines
                plural = "s" if truncated != 1 else ""
                if self.log_file is not None:
                    output_text.append(
                        f"... ({truncated} earlier line{plural} hidden; full log saved to {self.log_file.name})\n",
                        style="dim",
                    )
                else:
                    output_text.append(
                        f"... ({truncated} earlier line{plural} hidden)\n",
                        style="dim",
                    )
                lines = lines[-target_lines:]

            len(lines) if lines else 1

            for line in lines:
                line_lower = line.lower()

                # Add color coding for common patterns
                if line.startswith("$"):
                    output_text.append(line + "\n", style="cyan")
                elif line.startswith("✓") or "success" in line_lower:
                    output_text.append(line + "\n", style="green")
                elif line.startswith("✗") or "error" in line_lower or "failed" in line_lower:
                    output_text.append(line + "\n", style="red")
                elif line.startswith("●"):
                    output_text.append(line + "\n", style="yellow")
                # Highlight tool executions
                elif "executed:" in line_lower or "_tool" in line_lower:
                    output_text.append(line + "\n", style="cyan bold")
                # Highlight summaries and scan results
                elif "summary" in line_lower or "scan result" in line_lower:
                    output_text.append(line + "\n", style="yellow bold")
                # Highlight starting messages
                elif "starting" in line_lower and "analysis" in line_lower:
                    output_text.append(line + "\n", style="cyan")
                else:
                    output_text.append(line + "\n", style="white")

        return Panel(output_text, title="Agent Output", border_style="blue", height=panel_height)

    @abstractmethod
    def show_config(self) -> None:
        """Display run configuration."""
        pass

    # Note: run() method intentionally not implemented in base class
    # Each runner implements its own run() or run_direct() method:
    # - VulnsRunner.run() - Uses Agent with Azure OpenAI
    # - DependsRunner.run() - Uses Agent with Azure OpenAI
    # - DirectTestRunner.run() - Direct Maven execution
    # - CopilotRunner.run_direct() - Direct GitHub API
    # - StatusRunner.run_direct() - Direct GitHub/GitLab API

    def _save_log(self, return_code: int):
        """Save execution log to file.

        Args:
            return_code: Process return code
        """
        # Skip logging if log directory is not configured
        if self.log_file is None:
            return

        try:
            with open(self.log_file, "w") as f:
                f.write(f"{'='*70}\n")
                f.write(f"OSDU Agent {self.log_prefix.title()} Execution Log\n")
                f.write(f"{'='*70}\n")
                f.write(f"Timestamp: {datetime.now().isoformat()}\n")
                f.write(f"Services: {', '.join(self.services)}\n")
                f.write(f"Exit Code: {return_code}\n")
                f.write(f"{'='*70}\n\n")
                f.write("\n".join(self.full_output))
        except Exception as e:
            console.print(f"[dim]Warning: Could not save log: {e}[/dim]")


# Global process reference for signal handling
current_process: Optional[subprocess.Popen] = None
