"""Status runner for gathering GitHub/GitLab repository information using direct API calls."""

import logging
import os
from datetime import datetime
from importlib.resources.abc import Traversable
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Union

from rich.panel import Panel
from rich.table import Table

from agent.copilot.base import BaseRunner
from agent.copilot.base.runner import console
from agent.copilot.constants import SERVICES

logger = logging.getLogger(__name__)


class StatusRunner(BaseRunner):
    """Direct API client for gathering GitHub/GitLab status

    Args:
        prompt_file: Optional prompt file path (not used in direct API mode)
        services: List of service names to check
        providers: Optional provider filters for GitLab (e.g., ["Azure", "Core"])
        show_actions: Whether to show detailed workflow/pipeline action table (default: False)
    """

    def __init__(
        self,
        prompt_file: Optional[Union[Path, Traversable]],
        services: List[str],
        providers: Optional[List[str]] = None,
        show_actions: bool = False,
    ):
        self.providers = providers  # Optional providers for GitLab filtering (must be set before super().__init__)
        self.show_actions = show_actions  # Control display of detailed workflow/pipeline table
        # Pass dummy path since we don't use prompts in direct API mode (cross-platform null device)
        super().__init__(prompt_file or Path(os.devnull), services)

    @property
    def log_prefix(self) -> str:
        """Return log file prefix for this runner type."""
        # Use status-glab prefix if providers specified (GitLab mode)
        if self.providers:
            return "status-glab"
        return "status"

    def load_prompt(self) -> str:
        """Load prompt (not used in direct API mode)."""
        return ""

    def parse_output(self, line: str) -> None:
        """Parse output (not used in direct API mode)."""
        pass

    def get_results_panel(self, return_code: int) -> Panel:
        """Generate results panel (not used in direct API mode)."""
        return Panel(
            "Status displayed above",
            title="✓ Status Complete" if return_code == 0 else "✗ Status Failed",
            border_style="green" if return_code == 0 else "red",
        )

    def display_status(self, data: Dict[str, Any]) -> None:
        """Display GitHub/GitLab status in beautiful Rich format"""

        if not data:
            console.print("[red]Error:[/red] No status data received", style="bold red")
            return

        # Handle different possible structures
        # GitLab uses "projects", GitHub uses "services"
        if "services" in data:
            services_data = data["services"]
            data.get("timestamp", datetime.now().isoformat())
            is_gitlab = False
        elif "projects" in data:
            services_data = data["projects"]
            data.get("timestamp", datetime.now().isoformat())
            is_gitlab = True
        elif all(key in SERVICES for key in data.keys() if key != "timestamp"):
            # Data is structured as {service_name: {...}, service_name: {...}}
            services_data = {k: v for k, v in data.items() if k != "timestamp"}
            data.get("timestamp", datetime.now().isoformat())
            is_gitlab = False
        else:
            console.print(
                f"[red]Error:[/red] Unexpected data structure. Keys found: {list(data.keys())}",
                style="bold red",
            )
            console.print(f"[dim]Data preview: {str(data)[:500]}...[/dim]")
            return

        # For GitLab: Collect pipelines from each MR (new structure)
        # Pipelines are now stored per-MR instead of globally
        mr_pipelines = {}  # service_name -> list of (mr_iid, pipeline) tuples
        if is_gitlab:
            for service_name, service_data in services_data.items():
                pipelines_list = []
                prs = service_data.get("merge_requests", {}).get("items", [])
                for pr in prs:
                    mr_iid = pr.get("iid")
                    mr_pipelines_data = pr.get("pipelines", [])
                    for pipeline in mr_pipelines_data:
                        pipelines_list.append((mr_iid, pipeline))
                mr_pipelines[service_name] = pipelines_list

        # Summary Table
        table_title = "[italic]Service Status[/italic]"
        summary_table = Table(title=table_title, expand=True)
        summary_table.add_column("Service", style="cyan", no_wrap=True)
        summary_table.add_column("Issues", style="yellow")

        if is_gitlab:
            summary_table.add_column("MRs", style="magenta")
            summary_table.add_column("Pipelines", style="blue")
        else:
            summary_table.add_column("PRs", style="magenta")
            summary_table.add_column("Workflows", style="blue")

        summary_table.add_column("Last Update", style="dim")

        for service_name, service_data in services_data.items():
            # GitHub has "repo" key, GitLab now just has direct data
            if not is_gitlab:
                repo_or_project = service_data.get("repo", {})
                if not repo_or_project.get("exists", False):
                    summary_table.add_row(
                        f"✗ {service_name}",
                        "[dim]N/A[/dim]",
                        "[dim]N/A[/dim]",
                        "[dim]N/A[/dim]",
                        "[red]Not found[/red]",
                    )
                    continue
            else:
                # For GitLab, if service is in output, it exists
                repo_or_project = {"exists": True}

            issues_count = service_data.get("issues", {}).get("count", 0)
            prs_count = service_data.get(
                "merge_requests" if is_gitlab else "pull_requests", {}
            ).get("count", 0)

            # Workflow/Pipeline status - check recent runs
            if is_gitlab:
                # For GitLab: Use pipelines from MRs (already collected)
                workflows = [p for _, p in mr_pipelines.get(service_name, [])]
            else:
                # For GitHub: Use global workflows list
                workflows = service_data.get("workflows", {}).get("recent", [])

            if workflows:
                if is_gitlab:
                    # GitLab pipelines - status field only (no conclusion)
                    running = sum(
                        1 for w in workflows if w.get("status") in ["running", "pending", "created"]
                    )
                    failed = sum(1 for w in workflows if w.get("status") == "failed")
                    success = sum(1 for w in workflows if w.get("status") == "success")
                    canceled = sum(
                        1 for w in workflows if w.get("status") in ["canceled", "skipped"]
                    )

                    if running > 0:
                        workflow_display = f"[yellow]▶ {running} running[/yellow]"
                    elif failed > 0:
                        workflow_display = f"[red]✗ {failed} failed[/red]"
                    elif success > 0:
                        workflow_display = f"[green]✓ {success} ok[/green]"
                    elif canceled > 0:
                        workflow_display = f"[yellow]⊘ {canceled} canceled[/yellow]"
                    else:
                        workflow_display = f"[dim]{len(workflows)} runs[/dim]"
                else:
                    # GitHub workflows - status + conclusion
                    # Note: action_required is a CONCLUSION, not a status
                    needs_approval = sum(
                        1 for w in workflows if w.get("conclusion") == "action_required"
                    )
                    running = sum(
                        1
                        for w in workflows
                        if w.get("status") in ["in_progress", "queued", "waiting"]
                    )
                    completed = sum(
                        1
                        for w in workflows
                        if w.get("status") == "completed" and w.get("conclusion") == "success"
                    )
                    failed = sum(
                        1
                        for w in workflows
                        if w.get("status") == "completed"
                        and w.get("conclusion") in ["failure", "cancelled"]
                    )

                    if needs_approval > 0:
                        workflow_display = f"[red]⊙ {needs_approval} need approval[/red]"
                    elif running > 0:
                        workflow_display = f"[yellow]▶ {running} running[/yellow]"
                    elif failed > 0:
                        workflow_display = f"[red]✗ {failed} failed[/red]"
                    elif completed > 0:
                        workflow_display = f"[green]✓ {completed} ok[/green]"
                    else:
                        workflow_display = f"[dim]{len(workflows)} runs[/dim]"
            else:
                workflow_display = "[dim]None[/dim]"

            # Last update - GitHub has it in repo, GitLab doesn't have it in simplified structure
            if not is_gitlab:
                updated_at = repo_or_project.get("updated_at", "")
                if updated_at:
                    try:
                        update_time = datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
                        now = datetime.now(update_time.tzinfo)
                        delta = now - update_time
                        if delta.seconds < 3600:
                            time_ago = f"{delta.seconds // 60}m ago"
                        else:
                            time_ago = f"{delta.seconds // 3600}h ago"
                    except Exception:
                        time_ago = "recently"
                else:
                    time_ago = "unknown"
            else:
                # GitLab simplified structure doesn't include last_activity_at
                time_ago = "N/A"

            summary_table.add_row(
                f"✓ {service_name}",
                f"{issues_count} open" if issues_count > 0 else "[dim]0[/dim]",
                f"{prs_count}" if prs_count > 0 else "[dim]0[/dim]",
                workflow_display,
                time_ago,
            )

        console.print(summary_table)
        console.print()

        # Open Issues with grouping (MOVED BEFORE PRs)
        issue_groups = {}  # Group issues by title to detect duplicates
        for service_name, service_data in services_data.items():
            issues = service_data.get("issues", {}).get("items", [])
            for issue in issues:
                title = issue.get("title", "")
                if title not in issue_groups:
                    # Handle both GitHub (number) and GitLab (iid) field names
                    issue_number = issue.get("iid" if is_gitlab else "number")
                    issue_groups[title] = {
                        "number": issue_number,
                        "labels": issue.get("labels", []),
                        "assignees": issue.get("assignees", []),
                        "url": issue.get(
                            "html_url", issue.get("web_url", "")
                        ),  # GitHub uses html_url, GitLab uses web_url
                        "services": [],
                    }
                issue_groups[title]["services"].append(service_name)

        if issue_groups:
            issue_content = []
            for title, data in issue_groups.items():
                labels = ", ".join(data["labels"]) if data["labels"] else ""
                services = ", ".join(data["services"])
                assignees = ", ".join(data["assignees"]) if data["assignees"] else "Unassigned"

                # Highlight human-required issues
                url = data["url"]
                if "human-required" in data["labels"]:
                    issue_content.append(
                        f"[link={url}][bold red]#{data['number']}[/bold red][/link] {title}"
                    )
                    issue_content.append("   [red]⚠ Requires manual intervention[/red]")
                else:
                    issue_content.append(
                        f"[link={url}][yellow]#{data['number']}[/yellow][/link] {title}"
                    )

                if len(data["services"]) > 1:
                    issue_content.append(f"   Affects: [cyan]{services}[/cyan]")
                else:
                    issue_content.append(f"   Service: [cyan]{services}[/cyan]")

                # Show assignees
                if data["assignees"]:
                    # Highlight Copilot assignments
                    if "Copilot" in assignees or "copilot-swe-agent" in assignees:
                        issue_content.append(f"   Assigned: [blue]🤖 {assignees}[/blue]")
                    else:
                        issue_content.append(f"   Assigned: [dim]{assignees}[/dim]")
                else:
                    issue_content.append("   Assigned: [dim]None[/dim]")

                if labels:
                    issue_content.append(f"   Labels: [dim]{labels}[/dim]")
                issue_content.append("")

            console.print(
                Panel("\n".join(issue_content), title="Open Issues", border_style="yellow")
            )
            console.print()

        # Open PRs/MRs Panel - Show all open PRs/MRs with details
        all_prs = []
        release_prs = []  # Track release PRs separately for "Next Steps"
        for service_name, service_data in services_data.items():
            prs_key = "merge_requests" if is_gitlab else "pull_requests"
            prs = service_data.get(prs_key, {}).get("items", [])
            for pr in prs:
                all_prs.append((service_name, pr))
                if pr.get("is_release", False):
                    release_prs.append((service_name, pr))

        if all_prs:
            pr_content = []
            for service_name, pr in all_prs:
                # Handle both GitHub (number, is_draft) and GitLab (iid, draft) field names
                if is_gitlab:
                    pr_number = pr.get("iid")
                    is_draft = pr.get("draft", False)
                    branch = pr.get("source_branch", "unknown")
                else:
                    pr_number = pr.get("number")
                    is_draft = pr.get("is_draft", False)
                    branch = pr.get("headRefName", "unknown")

                title = pr.get("title", "")
                state = pr.get("state", "unknown").upper()
                is_release = pr.get("is_release", False)
                author = pr.get("author", "unknown")
                pr_url = pr.get("html_url", pr.get("web_url", ""))

                # Detect Copilot authorship
                is_copilot_pr = "copilot" in branch.lower() or author == "app/copilot-swe-agent"

                # Format title with state indicator
                # Use ! prefix for GitLab MRs, # for GitHub PRs
                pr_prefix = "!" if is_gitlab else "#"
                if is_draft:
                    pr_content.append(
                        f"[link={pr_url}][yellow]{pr_prefix}{pr_number}[/yellow][/link] [dim](Draft)[/dim] {title}"
                    )
                elif is_release:
                    pr_content.append(
                        f"[link={pr_url}][magenta]{pr_prefix}{pr_number}[/magenta][/link] [bold]{title}[/bold]"
                    )
                else:
                    pr_content.append(
                        f"[link={pr_url}][cyan]{pr_prefix}{pr_number}[/cyan][/link] {title}"
                    )

                # Show author for all PRs
                if is_copilot_pr:
                    pr_content.append("   Author: [blue]🤖 Copilot[/blue]")
                else:
                    pr_content.append(f"   Author: [dim]{author}[/dim]")

                # Show state and branch
                state_display = (
                    f"[yellow]{state}[/yellow]" if is_draft else f"[green]{state}[/green]"
                )
                pr_content.append(f"   State: {state_display} | Branch: [dim]{branch}[/dim]")

                # Show review and merge status (GitHub only - has this data)
                if not is_gitlab:
                    mergeable_state = pr.get("mergeable_state")
                    approved_count = pr.get("approved_count", 0)
                    changes_requested = pr.get("changes_requested", False)

                    # Build merge status line
                    status_parts = []

                    # Review status
                    if changes_requested:
                        status_parts.append("[red]✗ Changes requested[/red]")
                    elif approved_count > 0:
                        status_parts.append(f"[green]✓ {approved_count} approval(s)[/green]")
                    else:
                        status_parts.append("[dim]⊙ No reviews[/dim]")

                    # Mergeable status
                    if mergeable_state == "blocked":
                        status_parts.append("[red]⊘ Blocked[/red]")
                    elif mergeable_state == "dirty":
                        status_parts.append("[red]⚠ Conflicts[/red]")
                    elif mergeable_state == "unstable":
                        status_parts.append("[yellow]⚠ Checks failing[/yellow]")
                    elif mergeable_state == "clean":
                        status_parts.append("[green]✓ Ready[/green]")

                    if status_parts:
                        pr_content.append(f"   Merge: {' | '.join(status_parts)}")

                # ONLY show workflow status for Copilot PRs (they require approval)
                if is_copilot_pr:
                    pr_head_sha = pr.get("headRefOid")
                    workflows = service_data.get("workflows", {}).get("recent", [])

                    # Match workflows to this specific PR by commit SHA
                    if pr_head_sha:
                        pr_workflows = [w for w in workflows if w.get("headSha") == pr_head_sha]

                        if pr_workflows:
                            needs_approval = sum(
                                1 for w in pr_workflows if w.get("conclusion") == "action_required"
                            )
                            running = sum(
                                1
                                for w in pr_workflows
                                if w.get("status") in ["in_progress", "queued", "waiting"]
                            )
                            passed = sum(
                                1
                                for w in pr_workflows
                                if w.get("status") == "completed"
                                and w.get("conclusion") == "success"
                            )

                            if needs_approval > 0:
                                pr_content.append(
                                    f"   Workflows: [red bold]⊙ {needs_approval} need approval[/red bold]"
                                )
                            elif running > 0:
                                pr_content.append(
                                    f"   Workflows: [yellow]▶ {running} running[/yellow]"
                                )
                            elif passed > 0:
                                pr_content.append(f"   Workflows: [green]✓ {passed} passed[/green]")

                pr_content.append("")

            panel_title = "Open Merge Requests" if is_gitlab else "Open Pull Requests"
            console.print(Panel("\n".join(pr_content), title=panel_title, border_style="magenta"))
            console.print()

        # Workflow/Pipeline Details Section
        # Note: mr_pipelines is already collected earlier for GitLab (line 256-268)

        # Check if there are any workflows/pipelines to display
        if is_gitlab:
            # For GitLab, check if there are any MR pipelines
            has_workflows = any(
                len(mr_pipelines.get(service_name, [])) > 0 for service_name in services_data.keys()
            )
        else:
            # For GitHub, check if there are any workflows
            has_workflows = any(
                len(service_data.get("workflows", {}).get("recent", [])) > 0
                for service_data in services_data.values()
            )

        if has_workflows and self.show_actions:
            table_title = "MR Pipeline Runs" if is_gitlab else "[italic]Action Status[/italic]"
            workflow_table = Table(title=table_title, expand=True)
            workflow_table.add_column("Service", style="cyan", no_wrap=True)
            workflow_table.add_column("Workflow", style="white")
            workflow_table.add_column("Status", style="magenta")
            if not is_gitlab:
                workflow_table.add_column("PR", style="dim", no_wrap=True)
            workflow_table.add_column("When", style="dim")

            for service_name, service_data in services_data.items():
                # Get workflows/pipelines
                if is_gitlab:
                    # For GitLab: Use MR-specific pipelines (already collected)
                    mr_pipeline_tuples = mr_pipelines.get(service_name, [])
                    workflows = [p for _, p in mr_pipeline_tuples]
                    # Create mapping of pipeline to MR IID for display
                    pipeline_to_mr = {p.get("id"): mr_iid for mr_iid, p in mr_pipeline_tuples}
                else:
                    # For GitHub: Use global workflows list
                    workflows = service_data.get("workflows", {}).get("recent", [])
                    pipeline_to_mr = {}

                    # Create mapping of workflow head_branch to PR number
                    branch_to_pr = {}
                    prs = service_data.get("pull_requests", {}).get("items", [])
                    for pr in prs:
                        head_branch = pr.get("headRefName")  # Direct client uses headRefName
                        pr_number = pr.get("number")
                        if head_branch and pr_number:
                            branch_to_pr[head_branch] = pr_number

                if workflows:
                    for idx, workflow in enumerate(
                        workflows[:10]
                    ):  # Show up to 10 MR-related pipelines
                        created = workflow.get("created_at", "")

                        if is_gitlab:
                            # GitLab pipelines - simpler status (no conclusion)
                            pipeline_id = workflow.get("id", "Unknown")

                            # Show which MR this pipeline belongs to
                            mr_iid = pipeline_to_mr.get(pipeline_id)
                            mr_indicator = f" (MR !{mr_iid})" if mr_iid else ""

                            name = f"Pipeline #{pipeline_id}{mr_indicator}"
                            status = workflow.get("status", "unknown")

                            if status == "success":
                                status_display = "[green]✓ success[/green]"
                            elif status == "failed":
                                status_display = "[red]✗ failed[/red]"
                            elif status in ["running", "pending", "created"]:
                                status_display = f"[yellow]▶ {status}[/yellow]"
                            elif status in ["canceled", "skipped"]:
                                status_display = f"[yellow]⊘ {status}[/yellow]"
                            else:
                                status_display = f"[dim]{status}[/dim]"
                        else:
                            # GitHub workflows - status + conclusion
                            name = workflow.get("name", "Unknown")
                            status = workflow.get("status", "unknown")
                            conclusion = workflow.get("conclusion", "")
                            head_branch = workflow.get("head_branch", "")

                            # Get PR number for this workflow's branch
                            pr_number = branch_to_pr.get(head_branch)
                            pr_display = f"#{pr_number}" if pr_number else ""

                            # Format status
                            # Note: action_required is a CONCLUSION, not a status
                            if conclusion == "action_required":
                                status_display = "[red bold]⊙ action_required[/red bold]"
                            elif status == "completed":
                                if conclusion == "success":
                                    status_display = "[green]✓ success[/green]"
                                elif conclusion == "failure":
                                    status_display = "[red]✗ failed[/red]"
                                elif conclusion == "cancelled":
                                    status_display = "[yellow]⊘ cancelled[/yellow]"
                                elif conclusion == "skipped":
                                    status_display = "[dim]⊘ skipped[/dim]"
                                else:
                                    status_display = f"[dim]{conclusion or 'completed'}[/dim]"
                            elif status in ["in_progress", "queued", "waiting"]:
                                status_display = f"[yellow]▶ {status}[/yellow]"
                            else:
                                status_display = f"[dim]{status}[/dim]"

                        # Format time
                        try:
                            created_time = datetime.fromisoformat(created.replace("Z", "+00:00"))
                            now = datetime.now(created_time.tzinfo)
                            delta = now - created_time
                            if delta.seconds < 3600:
                                time_str = f"{delta.seconds // 60}m ago"
                            elif delta.seconds < 86400:
                                time_str = f"{delta.seconds // 3600}h ago"
                            else:
                                time_str = f"{delta.days}d ago"
                        except Exception:
                            time_str = "recently"

                        if is_gitlab:
                            workflow_table.add_row(
                                service_name if idx == 0 else "", name, status_display, time_str
                            )
                        else:
                            workflow_table.add_row(
                                service_name if idx == 0 else "",
                                name,
                                status_display,
                                pr_display,
                                time_str,
                            )

            console.print(workflow_table)

        # Failed Pipeline Jobs Section (GitLab only)
        if is_gitlab and self.show_actions:
            # Collect all failed pipelines with jobs
            failed_pipeline_jobs = []
            for service_name in services_data.keys():
                mr_pipeline_tuples = mr_pipelines.get(service_name, [])
                for mr_iid, pipeline in mr_pipeline_tuples:
                    if pipeline.get("status") == "failed" and pipeline.get("jobs"):
                        failed_pipeline_jobs.append(
                            {"service": service_name, "mr_iid": mr_iid, "pipeline": pipeline}
                        )

            if failed_pipeline_jobs:
                # Display failed pipeline jobs grouped by stage
                for item in failed_pipeline_jobs:
                    service_name = item["service"]
                    mr_iid = item["mr_iid"]
                    pipeline = item["pipeline"]
                    pipeline_id = pipeline.get("id")
                    jobs = pipeline.get("jobs", [])

                    # Create job table grouped by stage
                    job_table = Table(
                        title=f"❌ Failed Jobs - {service_name} Pipeline #{pipeline_id} (MR !{mr_iid})",
                        expand=True,
                    )
                    job_table.add_column("Stage", style="cyan", no_wrap=True)
                    job_table.add_column("Job Name", style="white")
                    job_table.add_column("Status", style="magenta", justify="center")
                    job_table.add_column("Duration", style="dim", justify="right")

                    # Group jobs by stage and sort
                    stage_order = [
                        "review",
                        "build",
                        "csp-build",
                        "coverage",
                        "containerize",
                        "scan",
                        "deploy",
                        "integration",
                        "acceptance",
                        "publish",
                    ]
                    jobs_by_stage: Dict[str, List[Any]] = {}
                    for job in jobs:
                        stage = job.get("stage", "unknown")
                        if stage not in jobs_by_stage:
                            jobs_by_stage[stage] = []
                        jobs_by_stage[stage].append(job)

                    # Sort stages by predefined order, with unknown stages at end
                    sorted(
                        jobs_by_stage.keys(),
                        key=lambda s: stage_order.index(s) if s in stage_order else 999,
                    )

                    # Separate parent and downstream jobs
                    parent_jobs = [j for j in jobs if not j.get("is_downstream", False)]
                    downstream_jobs = [j for j in jobs if j.get("is_downstream", False)]

                    # Display parent jobs first
                    if parent_jobs:
                        # Group parent jobs by stage
                        parent_by_stage: Dict[str, List[Any]] = {}
                        for job in parent_jobs:
                            stage = job.get("stage", "unknown")
                            if stage not in parent_by_stage:
                                parent_by_stage[stage] = []
                            parent_by_stage[stage].append(job)

                        sorted_parent_stages = sorted(
                            parent_by_stage.keys(),
                            key=lambda s: stage_order.index(s) if s in stage_order else 999,
                        )

                        for stage_idx, stage in enumerate(sorted_parent_stages):
                            stage_jobs = parent_by_stage[stage]
                            for job_idx, job in enumerate(stage_jobs):
                                job_name = job.get("name", "Unknown")
                                status = job.get("status", "unknown")
                                duration = job.get("duration", 0)
                                allow_failure = job.get("allow_failure", False)

                                # Format status
                                if status == "success":
                                    status_display = "[green]✓ success[/green]"
                                elif status == "failed":
                                    # If allow_failure is True, show as warning instead of failure
                                    if allow_failure:
                                        status_display = "[yellow]⚠ warning[/yellow]"
                                    else:
                                        status_display = "[red]✗ failed[/red]"
                                elif status == "canceled":
                                    status_display = "[yellow]⊘ canceled[/yellow]"
                                elif status == "skipped":
                                    status_display = "[dim]⊘ skipped[/dim]"
                                elif status in ["running", "pending"]:
                                    status_display = f"[yellow]▶ {status}[/yellow]"
                                else:
                                    status_display = f"[dim]{status}[/dim]"

                                # Format duration
                                if duration:
                                    duration_int = int(duration)  # Convert float to int
                                    if duration_int < 60:
                                        duration_str = f"{duration_int}s"
                                    elif duration_int < 3600:
                                        duration_str = f"{duration_int // 60}m {duration_int % 60}s"
                                    else:
                                        duration_str = f"{duration_int // 3600}h {(duration_int % 3600) // 60}m"
                                else:
                                    duration_str = "-"

                                stage_display = stage if job_idx == 0 else ""

                                job_table.add_row(
                                    stage_display, job_name, status_display, duration_str
                                )

                    # Add separator and downstream jobs if present
                    if downstream_jobs:
                        # Add a visual separator
                        job_table.add_row(
                            "[cyan]───[/cyan]",
                            "[cyan]Downstream Pipeline Jobs ───────────────────[/cyan]",
                            "[cyan]───[/cyan]",
                            "[cyan]───[/cyan]",
                        )

                        # Group downstream jobs by stage
                        downstream_by_stage: Dict[str, List[Any]] = {}
                        for job in downstream_jobs:
                            stage = job.get("stage", "unknown")
                            if stage not in downstream_by_stage:
                                downstream_by_stage[stage] = []
                            downstream_by_stage[stage].append(job)

                        sorted_downstream_stages = sorted(
                            downstream_by_stage.keys(),
                            key=lambda s: stage_order.index(s) if s in stage_order else 999,
                        )

                        for stage_idx, stage in enumerate(sorted_downstream_stages):
                            stage_jobs = downstream_by_stage[stage]
                            for job_idx, job in enumerate(stage_jobs):
                                job_name = "  " + job.get(
                                    "name", "Unknown"
                                )  # Indent downstream jobs
                                status = job.get("status", "unknown")
                                duration = job.get("duration", 0)
                                allow_failure = job.get("allow_failure", False)

                                # Format status
                                if status == "success":
                                    status_display = "[green]✓ success[/green]"
                                elif status == "failed":
                                    # If allow_failure is True, show as warning instead of failure
                                    if allow_failure:
                                        status_display = "[yellow]⚠ warning[/yellow]"
                                    else:
                                        status_display = "[red]✗ failed[/red]"
                                elif status == "canceled":
                                    status_display = "[yellow]⊘ canceled[/yellow]"
                                elif status == "skipped":
                                    status_display = "[dim]⊘ skipped[/dim]"
                                elif status in ["running", "pending"]:
                                    status_display = f"[yellow]▶ {status}[/yellow]"
                                else:
                                    status_display = f"[dim]{status}[/dim]"

                                # Format duration
                                if duration:
                                    duration_int = int(duration)  # Convert float to int
                                    if duration_int < 60:
                                        duration_str = f"{duration_int}s"
                                    elif duration_int < 3600:
                                        duration_str = f"{duration_int // 60}m {duration_int % 60}s"
                                    else:
                                        duration_str = f"{duration_int // 3600}h {(duration_int % 3600) // 60}m"
                                else:
                                    duration_str = "-"

                                stage_display = stage if job_idx == 0 else ""

                                job_table.add_row(
                                    stage_display, job_name, status_display, duration_str
                                )

                    console.print(job_table)
                    console.print()

        # Display condensed summary when workflows exist but show_actions is False
        elif has_workflows and not self.show_actions:
            # Collect workflows by service and status
            workflows_by_service: Dict[str, List[Any]] = {}
            running_workflows: Dict[str, List[Any]] = {}  # Track running workflows per service
            failed_workflows: Dict[str, List[Any]] = {}  # Track failed workflows per service

            for service_name, service_data in services_data.items():
                if is_gitlab:
                    mr_pipeline_tuples = mr_pipelines.get(service_name, [])
                    workflows = [p for _, p in mr_pipeline_tuples]
                else:
                    workflows = service_data.get("workflows", {}).get("recent", [])

                workflows_by_service[service_name] = workflows

                # Track running and failed workflows for detailed view
                if is_gitlab:
                    running_list = [
                        w for w in workflows if w.get("status") in ["running", "pending", "created"]
                    ]
                    failed_list = [w for w in workflows if w.get("status") == "failed"]
                else:
                    running_list = [
                        w
                        for w in workflows
                        if w.get("status") in ["in_progress", "queued", "waiting"]
                    ]
                    failed_list = [
                        w
                        for w in workflows
                        if w.get("status") == "completed"
                        and w.get("conclusion") in ["failure", "cancelled"]
                    ]

                if running_list:
                    running_workflows[service_name] = running_list
                if failed_list:
                    failed_workflows[service_name] = failed_list

            # Collect all workflows for total counts
            all_workflows = [w for workflows in workflows_by_service.values() for w in workflows]

            if all_workflows:
                # Initialize counters
                needs_approval_count = 0

                # Count by status
                if is_gitlab:
                    failed_count = sum(1 for w in all_workflows if w.get("status") == "failed")
                    running_count = sum(
                        1
                        for w in all_workflows
                        if w.get("status") in ["running", "pending", "created"]
                    )
                else:
                    failed_count = sum(
                        1
                        for w in all_workflows
                        if w.get("status") == "completed"
                        and w.get("conclusion") in ["failure", "cancelled"]
                    )
                    running_count = sum(
                        1
                        for w in all_workflows
                        if w.get("status") in ["in_progress", "queued", "waiting"]
                    )
                    needs_approval_count = sum(
                        1 for w in all_workflows if w.get("conclusion") == "action_required"
                    )

                # Build status-focused summary (not statistics)
                # Philosophy: Show current state and problems, not success counts
                summary_parts = []

                if is_gitlab:
                    # Failures and running are actionable
                    if failed_count > 0:
                        summary_parts.append(f"[red]{failed_count} failed[/red]")
                    if running_count > 0:
                        summary_parts.append(f"[yellow]{running_count} running[/yellow]")

                    # If nothing actionable, show healthy status
                    if not summary_parts:
                        summary = "[green]✓ All pipelines healthy[/green]"
                    else:
                        summary = f"⚠ {', '.join(summary_parts)}"
                else:
                    # Approval needed is critical
                    if needs_approval_count > 0:
                        summary_parts.append(
                            f"[red bold]{needs_approval_count} need approval[/red bold]"
                        )
                    # Failures are important
                    if failed_count > 0:
                        summary_parts.append(f"[red]{failed_count} failed[/red]")
                    # Running is informational
                    if running_count > 0:
                        summary_parts.append(f"[yellow]{running_count} running[/yellow]")

                    # If nothing actionable, show healthy status
                    if not summary_parts:
                        summary = "[green]✓ All workflows healthy[/green]"
                    elif running_count > 0 and not (needs_approval_count or failed_count):
                        # Only running, everything else healthy
                        summary = f"[green]✓ All healthy[/green] ([yellow]{running_count} running[/yellow])"
                    else:
                        summary = f"⚠ {', '.join(summary_parts)}"

                # Build detailed view for running/failed workflows (tree-style)
                content_lines = [summary]

                # Show running workflows by service (minimal, actionable)
                if running_workflows:
                    content_lines.append("")
                    for service_name, svc_running in sorted(running_workflows.items()):
                        # Show only workflow names, keep it minimal
                        workflow_names = [
                            w.get("name", f"Pipeline #{w.get('id')}") for w in svc_running[:3]
                        ]  # Max 3 per service

                        if len(svc_running) == 1:
                            content_lines.append(
                                f"  [yellow]▶[/yellow] {service_name}: {workflow_names[0]}"
                            )
                        elif len(svc_running) <= 3:
                            content_lines.append(f"  [yellow]▶[/yellow] {service_name}:")
                            for name in workflow_names:
                                content_lines.append(f"      ↳ {name}")
                        else:
                            content_lines.append(
                                f"  [yellow]▶[/yellow] {service_name}: {len(svc_running)} running"
                            )

                # Show failed workflows by service (minimal, actionable)
                if failed_workflows:
                    content_lines.append("")
                    for service_name, svc_failed in sorted(failed_workflows.items()):
                        workflow_names = [
                            w.get("name", f"Pipeline #{w.get('id')}") for w in svc_failed[:2]
                        ]  # Max 2 per service

                        if len(svc_failed) == 1:
                            content_lines.append(
                                f"  [red]✗[/red] {service_name}: {workflow_names[0]}"
                            )
                        elif len(svc_failed) <= 2:
                            content_lines.append(f"  [red]✗[/red] {service_name}:")
                            for name in workflow_names:
                                content_lines.append(f"      ↳ {name}")
                        else:
                            content_lines.append(
                                f"  [red]✗[/red] {service_name}: {len(svc_failed)} failed"
                            )

                content_lines.append("")
                content_lines.append("[dim]Use --actions flag to see all workflow runs[/dim]")

                # Display condensed summary panel
                console.print(
                    Panel(
                        "\n".join(content_lines),
                        title="Workflows Summary" if not is_gitlab else "Pipelines Summary",
                        border_style="blue",
                    )
                )
                console.print()

        # Next Steps / Quick Actions
        next_steps = []

        # Check for non-existent repositories (GitHub only)
        missing_repos = []
        if not is_gitlab:
            for service_name, service_data in services_data.items():
                repo_or_project = service_data.get("repo", {})
                if not repo_or_project.get("exists", False):
                    missing_repos.append(service_name)

        if missing_repos:
            next_steps.append(
                f"[yellow]⚠[/yellow] {len(missing_repos)} service(s) not found: {', '.join(missing_repos)}"
            )
            next_steps.append(f"  Run: /fork {','.join(missing_repos)} to initialize")

        # Check for human-required issues
        human_required = (
            [
                (title, data)
                for title, data in issue_groups.items()
                if "human-required" in data.get("labels", [])
            ]
            if issue_groups
            else []
        )

        if human_required:
            for title, data in human_required:
                services_str = ", ".join(data["services"])
                next_steps.append(f"[red]⚠[/red] Review issue #{data['number']}: {title[:50]}...")
                next_steps.append(f"  Services: {services_str}")

        # Check for release PRs
        if release_prs:
            next_steps.append(
                f"[yellow]⚠[/yellow] Review {len(release_prs)} release PR(s) for merging"
            )

        # Check for workflows/pipelines needing attention

        if is_gitlab:
            # GitLab pipelines - check for failed pipelines (from MR-specific data)
            failed_pipelines: Dict[str, int] = {}
            failed_jobs_summary: Dict[str, Set[str]] = {}
            running_count = 0

            for service_name in services_data.keys():
                mr_pipeline_tuples = mr_pipelines.get(service_name, [])
                pipelines = [p for _, p in mr_pipeline_tuples]

                svc_failed_pipes = [p for p in pipelines if p.get("status") == "failed"]
                if svc_failed_pipes:
                    failed_pipelines[service_name] = len(svc_failed_pipes)

                    # Collect failed job stages for actionable guidance
                    for pipeline in svc_failed_pipes:
                        if pipeline.get("jobs"):
                            for job in pipeline.get("jobs", []):
                                if job.get("status") == "failed":
                                    stage = job.get("stage", "unknown")
                                    if service_name not in failed_jobs_summary:
                                        failed_jobs_summary[service_name] = set()
                                    failed_jobs_summary[service_name].add(stage)

                svc_running_pipes = [
                    p for p in pipelines if p.get("status") in ["running", "pending", "created"]
                ]
                running_count += len(svc_running_pipes)

            if failed_pipelines:
                # Provide stage-specific guidance instead of generic message
                if failed_jobs_summary:
                    for service, stages in failed_jobs_summary.items():
                        stages_str = ", ".join(sorted(stages))
                        next_steps.append(
                            f"[red]✗[/red] Review failed {stages_str} stage(s) in {service}"
                        )
                else:
                    # Fallback to generic message if no job details available
                    total_failed = sum(failed_pipelines.values())
                    services_list = ", ".join(failed_pipelines.keys())
                    next_steps.append(f"[red]✗ {total_failed} failed MR pipeline(s)[/red]")
                    next_steps.append(f"  Services: {services_list}")

            if running_count > 0:
                next_steps.append(
                    f"[yellow]▶[/yellow] {running_count} MR pipeline(s) still running"
                )
            elif not failed_pipelines:
                next_steps.append("[green]✓[/green] All MR pipelines completed successfully")
        else:
            # GitHub workflows - check for approval needed
            approval_needed = {}
            for service_name, service_data in services_data.items():
                workflows = service_data.get("workflows", {}).get("recent", [])
                # Note: action_required is a CONCLUSION, not a status
                needs_approval = sum(
                    1 for w in workflows if w.get("conclusion") == "action_required"
                )
                if needs_approval > 0:
                    approval_needed[service_name] = needs_approval

            if approval_needed:
                total_approval = sum(approval_needed.values())
                services_list = ", ".join(approval_needed.keys())
                next_steps.append(
                    f"[red bold]⊙ {total_approval} workflow(s) need approval[/red bold]"
                )
                next_steps.append(f"  Services: {services_list}")

            # Check for running workflows
            total_running = sum(
                sum(
                    1
                    for w in service_data.get("workflows", {}).get("recent", [])
                    if w.get("status") in ["in_progress", "queued", "waiting"]
                )
                for service_data in services_data.values()
            )
            if total_running > 0:
                next_steps.append(f"[yellow]▶[/yellow] {total_running} workflow(s) still running")
            elif not approval_needed and not missing_repos:
                next_steps.append("[green]✓[/green] All workflows completed")

        # Only show Next Steps for GitHub (not useful for GitLab - jobs table is clearer)
        if next_steps and not is_gitlab:
            console.print(Panel("\n".join(next_steps), title="Next Steps", border_style="blue"))
            console.print()

    def show_config(self) -> None:
        """Display run configuration"""
        if self.providers:
            # GitLab mode
            config = f"""[cyan]Projects:[/cyan]   {', '.join(self.services)}
[cyan]Providers:[/cyan]  {', '.join(self.providers)}
[cyan]Gathering:[/cyan]  Issues, Merge Requests, Pipelines"""
            title = "🔍 GitLab Status Check"
        else:
            # GitHub mode
            config = f"""[cyan]Services:[/cyan]   {', '.join(self.services)}
[cyan]Gathering:[/cyan]  Issues, PRs, Workflows"""
            title = "🔍 GitHub Status Check"

        console.print(Panel(config, title=title, border_style="blue"))
        console.print()

    async def run_direct(self) -> int:
        """Execute direct Python API calls for fast status gathering."""
        from agent.config import AgentConfig

        # Determine which platform based on providers
        is_gitlab = self.providers is not None

        if is_gitlab:
            from agent.gitlab.direct_client import GitLabDirectClient

            spinner_msg = "[bold blue]Fetching GitLab data...[/bold blue]"
        else:
            from agent.github.direct_client import GitHubDirectClient

            spinner_msg = "[bold blue]Fetching GitHub data...[/bold blue]"

        self.show_config()

        # Create appropriate direct client and fetch status
        agent_config = AgentConfig()

        try:
            # Fetch all status data in parallel (fast!)
            with console.status(spinner_msg, spinner="dots"):
                if is_gitlab:
                    gitlab_client = GitLabDirectClient(agent_config)
                    status_data = await gitlab_client.get_all_status(
                        self.services, self.providers or ["Azure", "Core"]
                    )
                else:
                    github_client = GitHubDirectClient(agent_config)
                    status_data = await github_client.get_all_status(self.services)

            console.print()

            # Display the results using existing display method
            self.display_status(status_data)

            return 0

        except Exception as e:
            console.print(f"[red]Error:[/red] {e}", style="bold red")
            logger.error(f"Direct mode error: {e}", exc_info=True)
            return 1
