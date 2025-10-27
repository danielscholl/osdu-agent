"""Copilot fork runner for repository initialization."""

import asyncio
import logging
import re
from pathlib import Path
from typing import Any, List

from rich.panel import Panel

from agent.copilot.base import BaseRunner
from agent.copilot.base.runner import console
from agent.copilot.config import config
from agent.copilot.trackers import ServiceTracker

logger = logging.getLogger(__name__)


class CopilotRunner(BaseRunner):
    """Direct API client for forking and initializing repositories"""

    def __init__(
        self,
        services: List[str],
        branch: str | None = None,
    ):
        # Pass dummy path since we don't use prompts in direct API mode
        super().__init__(Path("/dev/null"), services)
        self.branch = branch if branch is not None else config.default_branch
        self.tracker: ServiceTracker = ServiceTracker(services)  # Override type from BaseRunner

    @property
    def log_prefix(self) -> str:
        """Return log file prefix for this runner type."""
        return "fork"

    def _service_in_line(self, service: str, line: str) -> bool:
        """
        Check if a service name appears as a complete word in a line using word-boundary matching.

        This prevents false matches where one service name is a substring of another
        (e.g., "indexer" matching within "indexer-queue").

        Args:
            service: The service name to search for
            line: The line of text to search in (should be lowercased)

        Returns:
            True if service name appears as a complete word in the line
        """
        # Escape special regex characters in service name
        escaped_service = re.escape(service)

        # Create pattern with word boundaries that respect hyphens
        # We need to ensure the service name is not part of a larger hyphenated word
        # Use negative lookbehind/lookahead to ensure no alphanumeric or hyphen characters surround the match
        pattern = r"(?<![a-zA-Z0-9\-])" + escaped_service + r"(?![a-zA-Z0-9\-])"

        # Search for the pattern (case-insensitive, though lines are typically already lowercased)
        return bool(re.search(pattern, line, re.IGNORECASE))

    def load_prompt(self) -> str:
        """Load and augment prompt with arguments"""
        prompt = self.prompt_file.read_text(encoding="utf-8")

        # Replace organization placeholder with actual value from config
        prompt = prompt.replace("{{ORGANIZATION}}", config.organization)

        # Inject arguments into prompt
        services_arg = ",".join(self.services)
        augmented = f"{prompt}\n\nARGUMENTS:\nSERVICES: {services_arg}\nBRANCH: {self.branch}"
        return augmented

    def show_config(self) -> None:
        """Display run configuration"""
        # Show full repo path for single service, org + services list for multiple
        if len(self.services) == 1:
            config_text = f"""[cyan]Repository:[/cyan] {config.organization}/{self.services[0]}
[cyan]Branch:[/cyan]     {self.branch}
[cyan]Template:[/cyan]   azure/osdu-spi"""
        else:
            config_text = f"""[cyan]Organization:[/cyan] {config.organization}
[cyan]Services:[/cyan]     {', '.join(self.services)}
[cyan]Branch:[/cyan]       {self.branch}
[cyan]Template:[/cyan]     azure/osdu-spi"""

        console.print(Panel(config_text, title="Fork", border_style="blue"))
        console.print()

    def parse_output(self, line: str) -> None:
        """Parse copilot output for status updates"""
        line_lower = line.lower()
        line_stripped = line.strip()

        # Detect service-specific section headers (markdown style)
        # Pattern: "### ✅ Partition Service" or "### ✅ Legal Service"
        for service in self.services:
            # Check for completion headers
            if f"✅ {service}" in line or f"✓ {service}" in line:
                if "service" in line_lower:
                    self.tracker.update(service, "success", "Completed successfully")
                    continue
            # Check for section headers mentioning service
            elif (
                line_stripped.startswith("###")
                and self._service_in_line(service, line_lower)
                and "service" in line_lower
            ):
                if "✅" in line or "✓" in line:
                    self.tracker.update(service, "success", "Completed successfully")
                    continue

        # Detect global completion messages (multiple patterns)
        completion_patterns = [
            "successfully completed repository initialization",
            "all repositories are now:",
            "repository status:",
        ]
        if any(pattern in line_lower for pattern in completion_patterns):
            # Mark all pending/running services as success
            for service in self.services:
                status = self.tracker.services[service]["status"]
                if status not in ["success", "skipped", "error"]:
                    self.tracker.update(service, "success", "Completed successfully")

        # Detect per-service completion message using flexible keyword matching
        # AI-generated messages may vary, so we use a scoring approach:
        # - Must contain service name + "service" keyword (for specificity)
        # - Must contain 2+ success/completion keywords (for confidence)
        # - Must NOT contain exclusion words (to avoid false positives)

        success_keywords = ["success", "successfully", "completed", "complete", "finished"]
        exclusion_keywords = ["waiting", "starting", "initiated", "checking", "attempting", "not"]

        for service in self.services:
            # Check if line mentions this service with the word "service"
            # This ensures we're talking about the service itself, not just using the word in context
            service_mentioned = (
                self._service_in_line(service, line_lower) and "service" in line_lower
            )

            if service_mentioned:
                # Count success keywords present
                success_count = sum(1 for keyword in success_keywords if keyword in line_lower)

                # Check for exclusion words (mid-process indicators)
                has_exclusion = any(keyword in line_lower for keyword in exclusion_keywords)

                # Score-based detection: 2+ success keywords AND no exclusions = completion
                if success_count >= 2 and not has_exclusion:
                    self.tracker.update(service, "success", "Completed successfully")
                    break  # Only one service per line

        # Find currently active service (first non-completed service)
        active_service = None
        for service in self.services:
            status = self.tracker.services[service]["status"]
            if status not in ["success", "skipped"]:
                active_service = service
                break

        # Detect copilot's task completion markers (highest priority)
        # First, check if this task mentions a specific service
        target_service = None
        for service in self.services:
            if self._service_in_line(service, line_lower):
                target_service = service
                break

        # Use target_service if found, otherwise fall back to active_service
        service_to_update = target_service or active_service

        if service_to_update and line_stripped.startswith("✓"):
            # Extract the task description for context
            task_desc = line_stripped[1:].strip().lower()
            current_status = self.tracker.services[service_to_update]["status"]
            current_details = self.tracker.services[service_to_update]["details"].lower()

            # Map specific tasks to status updates
            if "check if" in task_desc and "repository already exists" in task_desc:
                # Don't update yet - waiting for result
                pass
            elif "create" in task_desc and ("repository" in task_desc or "repo" in task_desc):
                self.tracker.update(service_to_update, "running", "Creating repository")
            elif "wait" in task_desc or "workflow" in task_desc:
                self.tracker.update(service_to_update, "waiting", "Waiting for workflow")
            elif "read" in task_desc and "issue" in task_desc:
                self.tracker.update(service_to_update, "running", "Reading initialization issue")
            elif "comment" in task_desc:
                self.tracker.update(service_to_update, "running", "Commenting on issue")
            elif "pull" in task_desc or (
                "clone" in task_desc and "finalization" not in current_details
            ):
                # Distinguish between initial clone and final pull
                if (
                    current_status == "waiting"
                    or "workflow" in current_details
                    or "verifying" in current_details
                ):
                    self.tracker.update(
                        service_to_update, "running", "Finalizing - pulling updates"
                    )
                else:
                    self.tracker.update(service_to_update, "running", "Syncing repository")
            elif "check" in task_desc and (
                "branch" in task_desc
                or "commit" in task_desc
                or "issue" in task_desc
                or "closed" in task_desc
            ):
                self.tracker.update(service_to_update, "running", "Verifying workflow results")
            elif "verify" in task_desc or "view" in task_desc:
                self.tracker.update(service_to_update, "running", "Final verification")

        # Detect copilot's error markers
        elif service_to_update and line_stripped.startswith("✗"):
            task_desc = line_stripped[1:].strip()
            self.tracker.update(service_to_update, "error", f"Failed: {task_desc[:30]}")

        # Global response patterns (copilot's narrative)
        # Prefer service_to_update (if service mentioned), else use active_service
        service_for_narrative = service_to_update or active_service

        if service_for_narrative:
            # Key decision points and outcomes
            if "doesn't exist yet" in line_lower or "repo_not_found" in line_lower:
                self.tracker.update(
                    service_for_narrative, "running", "Repository not found - creating"
                )
            elif "good!" in line_lower and "repository is cloned locally" in line_lower:
                self.tracker.update(service_for_narrative, "running", "Repository synced")
            elif "excellent!" in line_lower:
                if "created and cloned" in line_lower:
                    self.tracker.update(service_for_narrative, "running", "Repository created")
                elif "successfully updated" in line_lower:
                    self.tracker.update(service_for_narrative, "success", "Completed successfully")
            elif "perfect!" in line_lower:
                if "workflow has completed successfully" in line_lower:
                    self.tracker.update(service_for_narrative, "running", "Workflow completed")
                else:
                    self.tracker.update(service_for_narrative, "running", "Verification complete")
            elif "great!" in line_lower and "found the issue" in line_lower:
                self.tracker.update(service_for_narrative, "running", "Found initialization issue")

        # Service-specific updates
        for service in self.services:
            if self._service_in_line(service, line_lower):
                current_status = self.tracker.services[service]["status"]

                # Only mark as skipped if workflow explicitly terminates
                if (
                    "terminate workflow" in line_lower or "do not continue" in line_lower
                ) and "success" in line_lower:
                    self.tracker.update(service, "skipped", "Already exists")
                # Permission/access errors
                elif (
                    "permission denied" in line_lower
                    or "could not request permission" in line_lower
                ):
                    self.tracker.update(service, "error", "Permission denied")

    async def run_direct(self) -> int:
        """Execute direct API fork operations for fast execution with parallel processing."""
        from agent.config import AgentConfig
        from agent.github.fork_client import ForkDirectClient
        from rich.live import Live

        self.show_config()

        # Create fork client
        agent_config = AgentConfig()
        fork_client = ForkDirectClient(agent_config)

        # Create Live display reference (will be assigned in context manager)
        live_display = None

        # Create status callback to update tracker AND live display
        def status_callback(service: str, status: str, details: str) -> None:
            """Callback for fork_client to update service status."""
            self.tracker.update(service, status, details)
            # Update live display with fresh table
            if live_display is not None:
                live_display.update(self.tracker.get_table())

        async def fork_service_with_updates(service: str) -> Any:
            """Fork a single service with live status updates."""
            try:
                # Fork the service with status callback
                result = await fork_client.fork_service(
                    service, self.branch, status_callback=status_callback
                )

                # Update tracker based on final result
                if result["status"] == "success":
                    self.tracker.update(service, "success", "Completed successfully")
                elif result["status"] == "skipped":
                    self.tracker.update(service, "skipped", result["message"])
                else:
                    self.tracker.update(service, "error", result["message"])

                # Update live display after final status
                if live_display is not None:
                    live_display.update(self.tracker.get_table())

                return result

            except Exception as e:
                error_msg = f"Exception: {str(e)}"
                logger.error(f"Error forking {service}: {e}", exc_info=True)
                self.tracker.update(service, "error", error_msg)
                # Update live display on error
                if live_display is not None:
                    live_display.update(self.tracker.get_table())
                return {"service": service, "status": "error", "message": error_msg}

        try:
            # Display only the status table (no split layout)
            with Live(self.tracker.get_table(), console=console, refresh_per_second=4) as live:
                # Assign to nonlocal variable so callback can access it
                live_display = live

                # Process all services in parallel
                tasks = [fork_service_with_updates(service) for service in self.services]
                await asyncio.gather(*tasks, return_exceptions=True)

                # Final table update
                live.update(self.tracker.get_table())

            # Post-processing outside Live context
            console.print()

            # Check if all succeeded or skipped
            all_ok = all(
                self.tracker.services[s]["status"] in ["success", "skipped"] for s in self.services
            )
            return_code = 0 if all_ok else 1

            # Print the final results panel
            console.print(self.get_results_panel(return_code))

            return return_code

        except Exception as e:
            console.print(f"[red]Error:[/red] {e}", style="bold red")
            logger.error(f"Direct fork error: {e}", exc_info=True)
            return 1

    def get_results_panel(self, return_code: int) -> Panel:
        """Generate final results panel with clean table layout"""
        from rich.table import Table

        # Create table for results
        table = Table(expand=True, show_header=True, header_style="bold cyan")
        table.add_column("Service", style="cyan", no_wrap=True)
        table.add_column("Branch", style="blue", no_wrap=True)
        table.add_column("Status", style="yellow", no_wrap=True)
        table.add_column("Result", style="white", ratio=2)

        # Count statuses for footer
        status_counts = {"success": 0, "error": 0, "skipped": 0, "pending": 0}

        for service, data in self.tracker.services.items():
            status = data["status"]
            status_counts[status] = status_counts.get(status, 0) + 1

            # Determine status display and color
            status_display = ""

            if status == "success":
                status_display = "✓ Initialized"
                status_style = "green"
            elif status == "skipped":
                status_display = "⊘ Skipped"
                status_style = "yellow"
            elif status == "error":
                status_display = "✗ Failed"
                status_style = "red"
            elif status == "pending":
                status_display = "⏸ Pending"
                status_style = "dim"
            else:
                status_display = f"{data['icon']} {status.title()}"
                status_style = "dim"

            # Format result/details
            details = data.get("details", "")

            # Add repository URL for successful/skipped services
            if status in ["success", "skipped"]:
                repo_url = f"https://github.com/{config.organization}/{service}"
                result = f"{details}\n[link={repo_url}][dim]github.com/{config.organization}/{service}[/dim][/link]"
            else:
                result = details

            table.add_row(
                service, self.branch, f"[{status_style}]{status_display}[/{status_style}]", result
            )

        # Add footer row with summary
        table.add_section()
        summary_text = (
            f"[green]✓ {status_counts['success']} Success[/green]  "
            f"[yellow]⊘ {status_counts['skipped']} Skipped[/yellow]  "
            f"[red]✗ {status_counts['error']} Errors[/red]  "
            f"[dim]⏸ {status_counts['pending']} Pending[/dim]"
        )
        table.add_row("", "", "", summary_text, style="dim")

        # Determine panel style based on return code
        border_style = "green" if return_code == 0 else "red"
        title_emoji = "✓" if return_code == 0 else "✗"

        return Panel(table, title=f"{title_emoji} Fork Results", border_style=border_style)
