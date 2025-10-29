"""Workflow result store for maintaining context across agent interactions.

This module provides structured storage for workflow outputs, enabling the agent
to access detailed results from slash commands executed in interactive mode.
"""

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class WorkflowResult:
    """Result from a workflow execution.

    Attributes:
        workflow_type: Type of workflow (vulns, test, status, fork, depends)
        timestamp: When the workflow was executed
        services: List of services processed
        status: Overall status (success, error, partial)
        summary: Brief summary of the workflow results
        detailed_results: Full structured data from workflow execution
        vulnerabilities: Vulnerability counts by service (vulns-specific)
        cve_analysis: CVE analysis report (vulns-specific)
        test_results: Test execution results (test-specific)
        pr_status: Pull request status information (status-specific)
        fork_status: Fork operation status (fork-specific)
        dependency_updates: Dependency update counts by service (depends-specific)
        dependency_analysis: Dependency update analysis report (depends-specific)
    """

    workflow_type: str
    timestamp: datetime
    services: List[str]
    status: str
    summary: str
    detailed_results: Dict[str, Any]

    # Vulns-specific fields
    vulnerabilities: Optional[Dict[str, Dict[str, int]]] = None
    cve_analysis: Optional[str] = None

    # Test-specific fields
    test_results: Optional[Dict[str, Dict[str, Any]]] = None

    # Status-specific fields
    pr_status: Optional[Dict[str, Dict[str, Any]]] = None

    # Fork-specific fields
    fork_status: Optional[Dict[str, str]] = None

    # Depends-specific fields
    dependency_updates: Optional[Dict[str, Dict[str, int]]] = None
    dependency_analysis: Optional[str] = None


class WorkflowResultStore:
    """Thread-safe store for workflow results.

    This store maintains recent workflow execution results, allowing the agent
    to access detailed information about slash commands executed in interactive mode.

    The store automatically limits the number of stored results to prevent
    unbounded memory growth.
    """

    def __init__(self, max_results_per_type: int = 10):
        """Initialize the workflow result store.

        Args:
            max_results_per_type: Maximum number of results to keep per workflow type
        """
        self._results: List[WorkflowResult] = []
        self._lock = asyncio.Lock()
        self._max_results_per_type = max_results_per_type

    async def store(self, result: WorkflowResult) -> None:
        """Store a workflow result.

        Args:
            result: WorkflowResult to store
        """
        async with self._lock:
            self._results.append(result)
            logger.debug(
                f"Stored {result.workflow_type} workflow result for services: {', '.join(result.services)}"
            )

            # Cleanup old results
            self._cleanup()

    async def get_recent(
        self, workflow_type: Optional[str] = None, limit: int = 5
    ) -> List[WorkflowResult]:
        """Get recent workflow results.

        Args:
            workflow_type: Filter by workflow type (None for all types)
            limit: Maximum number of results to return

        Returns:
            List of WorkflowResult objects, most recent first
        """
        async with self._lock:
            results = self._results

            # Filter by workflow type if specified
            if workflow_type:
                results = [r for r in results if r.workflow_type == workflow_type]

            # Sort by timestamp (most recent first) and limit
            return sorted(results, key=lambda r: r.timestamp, reverse=True)[:limit]

    async def get_context_summary(self, limit: int = 3) -> str:
        """Generate a context summary for agent injection.

        This creates a markdown-formatted summary of recent workflow results
        that can be injected into the agent's context via middleware.

        Args:
            limit: Maximum number of recent results to include

        Returns:
            Markdown-formatted context summary
        """
        recent = await self.get_recent(limit=limit)

        logger.debug(f"[Context Summary] Found {len(recent)} recent workflow results")

        if not recent:
            return ""

        lines = ["## Recent Workflow Results"]
        lines.append("")
        lines.append("*The following workflow results are available for your reference:*")
        lines.append("")

        for result in recent:
            # Format timestamp
            time_str = result.timestamp.strftime("%H:%M:%S")

            lines.append(f"### {result.workflow_type.title()} - {time_str}")
            lines.append(f"**Services:** {', '.join(result.services)}")
            lines.append(f"**Status:** {result.status}")
            lines.append(f"**Summary:** {result.summary}")

            # Add workflow-specific details
            # Handle both "vulns" and "triage" (legacy name) for vulnerability workflows
            if result.workflow_type in ("vulns", "triage") and result.vulnerabilities:
                lines.append("")
                lines.append("**Vulnerabilities Found:**")
                for svc, counts in result.vulnerabilities.items():
                    critical = counts.get("critical", 0)
                    high = counts.get("high", 0)
                    medium = counts.get("medium", 0)
                    lines.append(f"- {svc}: {critical} critical, {high} high, {medium} medium")

                # Include CVE analysis if available
                if result.cve_analysis:
                    lines.append("")
                    lines.append("**CVE Analysis Summary:**")
                    # Extract critical/high CVE details and remediation steps
                    analysis_lines = result.cve_analysis.split("\n")

                    # Find service-specific CVE section (most actionable)
                    in_cve_section = False
                    cve_section_lines = []
                    for line in analysis_lines:
                        if "SERVICE-SPECIFIC CRITICAL/HIGH CVEs" in line:
                            in_cve_section = True
                        elif "### 3. IMMEDIATE ACTION ITEMS" in line:
                            # Also include action items
                            in_cve_section = True
                        elif line.startswith("###") and in_cve_section and "SERVICE-SPECIFIC" not in line and "IMMEDIATE ACTION" not in line:
                            # End of relevant sections
                            break

                        if in_cve_section:
                            cve_section_lines.append(line)

                    # Include CVE section if found (up to 50 lines), otherwise first 20 lines
                    if cve_section_lines:
                        for line in cve_section_lines[:50]:
                            if line.strip():
                                lines.append(f"  {line}")
                        if len(cve_section_lines) > 50:
                            lines.append("  *(Full analysis available in detailed results)*")
                    else:
                        # Fallback: show first 20 lines
                        for line in analysis_lines[:20]:
                            if line.strip():
                                lines.append(f"  {line}")
                        if len(analysis_lines) > 20:
                            lines.append("  *(Full analysis available in detailed results)*")

            elif result.workflow_type == "test" and result.test_results:
                lines.append("")
                lines.append("**Test Results:**")
                for svc, results in result.test_results.items():
                    total_tests = results.get("total_tests", 0)
                    results.get("passed", 0)
                    failed = results.get("failed", 0)
                    coverage_line = results.get("coverage_line", 0)
                    coverage_branch = results.get("coverage_branch", 0)
                    quality_grade = results.get("quality_grade")

                    # Build result line with grade and coverage
                    result_parts = [f"{total_tests} tests"]
                    if failed > 0:
                        result_parts.append(f"{failed} failed")

                    if coverage_line > 0:
                        result_parts.append(
                            f"coverage: {coverage_line}% line / {coverage_branch}% branch"
                        )

                    if quality_grade:
                        result_parts.append(f"**Grade: {quality_grade}**")

                    lines.append(f"- {svc}: {', '.join(result_parts)}")

            elif result.workflow_type == "depends" and result.dependency_updates:
                lines.append("")
                lines.append("**Dependency Updates:**")
                for svc, counts in result.dependency_updates.items():
                    major = counts.get("major_updates", 0)
                    minor = counts.get("minor_updates", 0)
                    patch = counts.get("patch_updates", 0)
                    total = counts.get("total_dependencies", 0)
                    outdated = counts.get("outdated_dependencies", 0)
                    lines.append(f"- {svc}: {major}M / {minor}m / {patch}p updates ({outdated}/{total} outdated)")

                # Include dependency analysis if available (first 30 lines for patch recommendations)
                if result.dependency_analysis:
                    lines.append("")
                    lines.append("**Dependency Analysis Summary:**")
                    # Extract patch updates section and other key parts
                    analysis_lines = result.dependency_analysis.split("\n")

                    # Find and include patch updates section (most relevant for low-risk fixes)
                    in_patch_section = False
                    patch_lines = []
                    for line in analysis_lines:
                        if "## PATCH UPDATES" in line or "PATCH UPDATES" in line:
                            in_patch_section = True
                        elif line.startswith("##") and in_patch_section:
                            # End of patch section
                            break

                        if in_patch_section:
                            patch_lines.append(line)

                    # Include patch section if found, otherwise first 30 lines
                    if patch_lines:
                        for line in patch_lines[:40]:  # Limit to 40 lines
                            if line.strip():
                                lines.append(f"  {line}")
                        if len(patch_lines) > 40:
                            lines.append("  *(Full analysis available in detailed results)*")
                    else:
                        # Fallback: show first 30 lines
                        for line in analysis_lines[:30]:
                            if line.strip():
                                lines.append(f"  {line}")
                        if len(analysis_lines) > 30:
                            lines.append("  *(Full analysis available in detailed results)*")

            elif result.workflow_type == "status" and result.pr_status:
                lines.append("")
                lines.append("**Status Information:**")

                # Track unique workflows needing attention across all services
                actionable_workflows = {}  # {workflow_name: filename}

                for svc, status in result.pr_status.items():
                    open_prs = status.get("open_prs", 0)
                    open_issues = status.get("open_issues", 0)
                    workflows_needing_approval = status.get("workflows_needing_approval", 0)

                    status_line = f"- {svc}: {open_prs} open PRs, {open_issues} open issues"
                    if workflows_needing_approval > 0:
                        status_line += f", {workflows_needing_approval} workflows need approval"
                    lines.append(status_line)

                    # Extract actionable workflows from detailed results
                    status_data = result.detailed_results.get("status_data", {})
                    service_data = status_data.get("services", {}).get(svc, {})
                    workflows_data = service_data.get("workflows", {}).get("recent", [])

                    for workflow in workflows_data:
                        conclusion = workflow.get("conclusion")
                        if conclusion in ["action_required", "failure", "cancelled"]:
                            workflow_name = workflow.get("name")
                            workflow_path = workflow.get("path", "")
                            # Extract just the filename (e.g., "codeql.yml" from ".github/workflows/codeql.yml")
                            workflow_filename = (
                                workflow_path.split("/")[-1] if workflow_path else None
                            )
                            if workflow_name and workflow_filename:
                                actionable_workflows[workflow_name] = workflow_filename

                # Add workflow name→filename mapping (only if there are actionable workflows)
                if actionable_workflows:
                    lines.append("")
                    lines.append("**Workflow Reference** (for triggering):")
                    for name, filename in sorted(actionable_workflows.items()):
                        lines.append(f"  - '{name}' → `{filename}`")
                    lines.append("")

                # Move back to the service loop for PR/issue details
                for svc, status in result.pr_status.items():
                    pr_details = status.get("pr_details", [])
                    issue_details = status.get("issue_details", [])

                    # Get full PR data from detailed results for merge/review status
                    status_data = result.detailed_results.get("status_data", {})
                    service_data = status_data.get("services", {}).get(svc, {})
                    full_prs = service_data.get("pull_requests", {}).get("items", [])

                    # Create lookup by PR number for enrichment
                    pr_lookup = {pr.get("number"): pr for pr in full_prs}

                    # Include details about ALL PRs (not just ones with pending workflows)
                    if pr_details:
                        for pr in pr_details:
                            pr_num = pr.get("number")
                            pr_title = pr.get("title", "")
                            pr.get("state", "").upper()
                            is_draft = pr.get("is_draft", False)
                            workflows_pending = pr.get("workflows_pending", 0)

                            # Get enriched PR data
                            full_pr = pr_lookup.get(pr_num, {})
                            approved_count = full_pr.get("approved_count", 0)
                            changes_requested = full_pr.get("changes_requested", False)
                            mergeable_state = full_pr.get("mergeable_state", "unknown")
                            is_release = full_pr.get("is_release", False)

                            # Build PR description
                            pr_desc = f"  - PR #{pr_num}"
                            if is_draft:
                                pr_desc += " (DRAFT)"
                            if is_release:
                                pr_desc += " [RELEASE]"
                            pr_desc += f": {pr_title[:60]}"

                            # Add review status
                            if changes_requested:
                                pr_desc += " ⚠ changes requested"
                            elif approved_count > 0:
                                pr_desc += f" ✓ {approved_count} approval(s)"
                            else:
                                pr_desc += " ⊙ no reviews"

                            # Add merge status
                            if mergeable_state == "blocked":
                                pr_desc += " | ⊘ blocked"
                            elif mergeable_state == "clean":
                                pr_desc += " | ✓ ready to merge"
                            elif mergeable_state in ["unstable", "dirty"]:
                                pr_desc += f" | ⚠ {mergeable_state}"

                            # Add workflow status if relevant
                            if workflows_pending > 0:
                                pr_desc += f" | {workflows_pending} workflows pending"

                            lines.append(pr_desc)

                    # Include issue details with labels and assignees
                    if issue_details:
                        for issue in issue_details:
                            issue_num = issue.get("number")
                            issue_title = issue.get("title", "")
                            labels = issue.get("labels", [])
                            assignees = issue.get("assignees", [])

                            # Build issue description
                            issue_desc = f"  - Issue #{issue_num}: {issue_title[:60]}"

                            # Add important labels
                            if "human-required" in labels:
                                issue_desc += " [HUMAN-REQUIRED]"

                            # Add assignee info
                            if assignees:
                                if "Copilot" in assignees or "copilot-swe-agent" in assignees:
                                    issue_desc += " (Assigned: Copilot)"
                                else:
                                    issue_desc += f" (Assigned: {', '.join(assignees)})"

                            lines.append(issue_desc)

            elif result.workflow_type == "fork" and result.fork_status:
                lines.append("")
                lines.append("**Fork Status:**")
                for svc, status in result.fork_status.items():
                    lines.append(f"- {svc}: {status}")

            lines.append("")
            lines.append("---")
            lines.append("")

        # Add usage note
        lines.append("*You can reference these results when answering user questions.*")
        lines.append("")

        return "\n".join(lines)

    def _cleanup(self) -> None:
        """Remove old results to prevent unbounded memory growth.

        Keeps at most max_results_per_type results for each workflow type.
        This method should be called while holding the lock.
        """
        # Group results by workflow type
        by_type: Dict[str, List[WorkflowResult]] = {}
        for result in self._results:
            if result.workflow_type not in by_type:
                by_type[result.workflow_type] = []
            by_type[result.workflow_type].append(result)

        # Keep only the most recent N results per type
        kept_results = []
        for workflow_type, results in by_type.items():
            sorted_results = sorted(results, key=lambda r: r.timestamp, reverse=True)
            kept_results.extend(sorted_results[: self._max_results_per_type])

        # Update the results list
        self._results = kept_results

        logger.debug(f"Cleanup: Kept {len(kept_results)} workflow results")

    async def clear(self, workflow_type: Optional[str] = None) -> None:
        """Clear workflow results.

        Args:
            workflow_type: Clear only results of this type (None clears all)
        """
        async with self._lock:
            if workflow_type:
                self._results = [r for r in self._results if r.workflow_type != workflow_type]
                logger.info(f"Cleared {workflow_type} workflow results")
            else:
                self._results.clear()
                logger.info("Cleared all workflow results")

    async def get_stats(self) -> Dict[str, Any]:
        """Get statistics about stored results.

        Returns:
            Dictionary with result statistics
        """
        async with self._lock:
            by_type: Dict[str, int] = {}
            for result in self._results:
                by_type[result.workflow_type] = by_type.get(result.workflow_type, 0) + 1

            return {
                "total_results": len(self._results),
                "by_type": by_type,
                "oldest_timestamp": (
                    min(r.timestamp for r in self._results) if self._results else None
                ),
                "newest_timestamp": (
                    max(r.timestamp for r in self._results) if self._results else None
                ),
            }
