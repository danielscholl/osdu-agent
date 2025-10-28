"""Report workflow for GitLab contribution analysis."""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import List, Optional, Tuple

from rich.console import Console

from agent.config import AgentConfig
from agent.gitlab.analytics import GitLabContributionAnalyzer
from agent.gitlab.direct_client import GitLabDirectClient
from agent.gitlab.models import ReportMode
from agent.gitlab.report_formatter import ReportFormatter
from agent.observability import record_workflow_run, tracer
from agent.workflows import WorkflowResult, get_result_store

logger = logging.getLogger(__name__)


def _parse_report_arguments(args_string: str) -> Tuple[ReportMode, int, int]:
    """
    Parse report command arguments.

    Supports formats:
    - "" -> (COMPARISON, 30, 1)
    - "60" -> (COMPARISON, 60, 1)
    - "adr" -> (ADR, 30, 1)
    - "compare 14 periods=3" -> (COMPARISON, 14, 3)
    - "trends" -> (TRENDS, 30, 1)

    Args:
        args_string: Argument string from command

    Returns:
        Tuple of (mode, days, periods)
    """
    # Default values
    mode = ReportMode.COMPARISON
    days = 30
    periods = 1

    if not args_string:
        return (mode, days, periods)

    # Split arguments
    parts = args_string.strip().split()

    # Check for mode keywords
    if "adr" in parts:
        mode = ReportMode.ADR
        parts.remove("adr")
    elif "trends" in parts:
        mode = ReportMode.TRENDS
        parts.remove("trends")
    elif "contributions" in parts:
        mode = ReportMode.CONTRIBUTIONS
        parts.remove("contributions")
    elif "compare" in parts:
        mode = ReportMode.COMPARISON
        parts.remove("compare")

    # Extract days (any standalone number)
    for part in parts[:]:
        if part.isdigit():
            days = int(part)
            parts.remove(part)
            break

    # Extract periods (periods=N or --periods N)
    for i, part in enumerate(parts):
        if part.startswith("periods="):
            periods_str = part.split("=")[1]
            if periods_str.isdigit():
                periods = int(periods_str)
        elif part == "--periods" and i + 1 < len(parts):
            if parts[i + 1].isdigit():
                periods = int(parts[i + 1])

    return (mode, days, periods)


def _calculate_period_dates(days: int, num_periods: int) -> List[Tuple[datetime, datetime]]:
    """
    Calculate start/end dates for multiple periods.

    Args:
        days: Number of days per period
        num_periods: Number of periods to calculate (including current)

    Returns:
        List of (start_date, end_date) tuples, current period first
    """
    from datetime import timezone

    periods = []
    end_date = datetime.now(timezone.utc)

    for i in range(num_periods):
        period_end = end_date - timedelta(days=i * days)
        period_start = period_end - timedelta(days=days)
        periods.append((period_start, period_end))

    return periods


async def run_report_workflow(
    args_string: str = "", services: Optional[List[str]] = None
) -> WorkflowResult:
    """
    Run report workflow for GitLab contributions.

    Args:
        args_string: Argument string (e.g., "compare 30 periods=3")
        services: Optional list of services (auto-detected if None)

    Returns:
        WorkflowResult with report data
    """
    workflow_start = datetime.now()
    start_time = asyncio.get_event_loop().time()

    # Parse arguments
    mode, days, num_periods = _parse_report_arguments(args_string)

    logger.info(f"Report workflow: mode={mode.value}, days={days}, periods={num_periods}")

    # Create console and formatter
    console = Console()
    formatter = ReportFormatter(console)

    with tracer.start_as_current_span("report_workflow") as span:
        span.set_attribute("mode", mode.value)
        span.set_attribute("days", days)
        span.set_attribute("periods", num_periods)

        try:
            # Load config
            config = AgentConfig()

            # Auto-detect services if not provided
            if services is None:
                formatter.print_info("Auto-detecting available services...")
                from agent.copilot.runners.status_runner import StatusRunner

                runner = StatusRunner(None, [], None)
                services = await runner._detect_services_from_config(config)

                if not services:
                    formatter.print_error("No services found in configuration")
                    return WorkflowResult(
                        workflow_type="report",
                        timestamp=workflow_start,
                        services=[],
                        status="error",
                        summary="No services found in configuration",
                        detailed_results={},
                    )

            span.set_attribute("service_count", len(services))

            # Display report header
            formatter.format_report_header(
                services=services,
                mode=mode.value,
                days=days,
                periods=num_periods,
            )

            formatter.print_info(f"Analyzing {len(services)} services...")

            # Initialize GitLab client and analyzer
            gitlab_client = GitLabDirectClient(config)
            analyzer = GitLabContributionAnalyzer(config, gitlab_client)

            # Get project paths from services
            project_paths = []
            for service in services:
                # Get upstream URL
                upstream_url = await gitlab_client._get_upstream_url(service)
                if upstream_url:
                    project_path = gitlab_client._parse_project_path(upstream_url)
                    if project_path:
                        project_paths.append(project_path)

            if not project_paths:
                formatter.print_error("No valid GitLab projects found")
                return WorkflowResult(
                    workflow_type="report",
                    timestamp=workflow_start,
                    services=services or [],
                    status="error",
                    summary="No valid GitLab projects found",
                    detailed_results={},
                )

            formatter.print_info(f"Found {len(project_paths)} GitLab projects")

            # Generate report based on mode
            if mode == ReportMode.COMPARISON:
                result_data = await _generate_comparison_report(
                    analyzer, formatter, project_paths, days, num_periods
                )
            elif mode == ReportMode.ADR:
                result_data = await _generate_adr_report(analyzer, formatter, project_paths, days)
            elif mode == ReportMode.TRENDS:
                result_data = await _generate_trends_report(
                    analyzer, formatter, project_paths, months=12
                )
            elif mode == ReportMode.CONTRIBUTIONS:
                result_data = await _generate_contributions_report(
                    analyzer, formatter, project_paths, days
                )
            else:
                formatter.print_error(f"Unknown report mode: {mode}")
                return WorkflowResult(
                    workflow_type="report",
                    timestamp=workflow_start,
                    services=services or [],
                    status="error",
                    summary=f"Unknown report mode: {mode}",
                    detailed_results={},
                )

            # Create workflow result
            duration = asyncio.get_event_loop().time() - start_time
            result = WorkflowResult(
                workflow_type="report",
                timestamp=workflow_start,
                services=services or [],
                status="success",
                summary=f"Generated {result_data.get('mode', 'report')} report",
                detailed_results=result_data,
            )

            # Store result
            store = get_result_store()
            await store.store(result)

            # Record metrics
            record_workflow_run("report", True, duration)

            formatter.print_success(f"Report generated in {duration:.2f}s")
            return result

        except Exception as e:
            logger.error(f"Report workflow error: {e}", exc_info=True)
            formatter.print_error(f"Report generation failed: {str(e)}")

            duration = asyncio.get_event_loop().time() - start_time
            record_workflow_run("report", False, duration)

            return WorkflowResult(
                workflow_type="report",
                timestamp=workflow_start,
                services=services or [],
                status="error",
                summary=f"Report generation failed: {str(e)}",
                detailed_results={"error": str(e)},
            )


async def _generate_comparison_report(
    analyzer: GitLabContributionAnalyzer,
    formatter: ReportFormatter,
    project_paths: List[str],
    days: int,
    num_periods: int,
) -> dict:
    """Generate period-over-period comparison report."""
    formatter.print_info(f"Analyzing {num_periods} periods of {days} days each...")

    # Calculate period dates
    period_dates = _calculate_period_dates(days, num_periods)

    # Analyze all periods
    period_stats_list = await analyzer.analyze_trends(project_paths, period_dates)

    if not period_stats_list:
        formatter.print_error("No data available for specified periods")
        return {}

    # Display executive summary
    current_period = period_stats_list[0]
    previous_period = period_stats_list[1] if len(period_stats_list) > 1 else None
    formatter.format_executive_summary(current_period, previous_period)

    # Display comparison table
    if len(period_stats_list) > 1:
        formatter.format_comparison_table(period_stats_list)

    # Display contributor leaderboard
    formatter.format_contributor_leaderboard(current_period.contributions, limit=10)

    # Display project breakdown
    formatter.format_project_breakdown(current_period)

    # Analyze ADRs for current period
    adr_stats = await analyzer.analyze_adrs(
        project_paths, current_period.start_date, current_period.end_date
    )
    if adr_stats.total_adrs > 0:
        formatter.format_adr_details(adr_stats, limit=10)

    return {
        "mode": "comparison",
        "periods": num_periods,
        "days_per_period": days,
        "current_period": {
            "total_mrs": current_period.contributions.total_mrs,
            "merged_mrs": current_period.contributions.merged_mrs,
            "active_contributors": current_period.contributions.active_contributors,
        },
    }


async def _generate_adr_report(
    analyzer: GitLabContributionAnalyzer,
    formatter: ReportFormatter,
    project_paths: List[str],
    days: int,
) -> dict:
    """Generate ADR analysis report."""
    formatter.print_info(f"Analyzing ADRs for last {days} days...")

    # Calculate date range (use UTC to match GitLab API timezone)
    from datetime import timezone

    end_date = datetime.now(timezone.utc)
    start_date = end_date - timedelta(days=days)

    # Analyze ADRs
    adr_stats = await analyzer.analyze_adrs(project_paths, start_date, end_date)

    if adr_stats.total_adrs == 0:
        formatter.print_info("No ADRs found in specified period")
        return {}

    # Display summary panel
    console = formatter.console
    console.print()
    console.print(
        f"[bold cyan]ADR Summary[/bold cyan] ({start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')})"
    )
    console.print(f"Total ADRs: [bold]{adr_stats.total_adrs}[/bold]")
    console.print(
        f"Open: [yellow]{adr_stats.open_adrs}[/yellow] | Approved: [green]{adr_stats.approved_adrs}[/green]"
    )
    console.print(f"Participants: [blue]{adr_stats.participants}[/blue]")
    console.print(f"Comments: [magenta]{adr_stats.comments_count}[/magenta]")
    console.print()

    # Display ADR details
    formatter.format_adr_details(adr_stats, limit=20)

    return {
        "mode": "adr",
        "days": days,
        "total_adrs": adr_stats.total_adrs,
        "open_adrs": adr_stats.open_adrs,
        "approved_adrs": adr_stats.approved_adrs,
    }


async def _generate_trends_report(
    analyzer: GitLabContributionAnalyzer,
    formatter: ReportFormatter,
    project_paths: List[str],
    months: int = 12,
) -> dict:
    """Generate trends report over multiple months."""
    formatter.print_info(f"Analyzing trends over last {months} months...")

    # Calculate monthly periods (use UTC)
    from datetime import timezone

    period_dates = []
    for i in range(months):
        end_date = datetime.now(timezone.utc) - timedelta(days=i * 30)
        start_date = end_date - timedelta(days=30)
        period_dates.append((start_date, end_date))

    # Analyze trends
    period_stats_list = await analyzer.analyze_trends(project_paths, period_dates)

    if not period_stats_list:
        formatter.print_error("No trend data available")
        return {}

    # Extract values for charts
    labels = [f"Month -{i}" for i in range(len(period_stats_list))]
    labels[0] = "Current"

    total_mrs_values = [p.contributions.total_mrs for p in period_stats_list]
    contributors_values = [p.contributions.active_contributors for p in period_stats_list]

    # Display trend charts
    formatter.format_trend_chart("Total MRs", total_mrs_values, labels)
    formatter.format_trend_chart("Active Contributors", contributors_values, labels)

    return {
        "mode": "trends",
        "months": months,
        "periods_analyzed": len(period_stats_list),
    }


async def _generate_contributions_report(
    analyzer: GitLabContributionAnalyzer,
    formatter: ReportFormatter,
    project_paths: List[str],
    days: int,
) -> dict:
    """Generate basic contributions report."""
    formatter.print_info(f"Analyzing contributions for last {days} days...")

    # Calculate date range (use UTC)
    from datetime import timezone

    end_date = datetime.now(timezone.utc)
    start_date = end_date - timedelta(days=days)

    # Analyze contributions
    period_stats = await analyzer.analyze_contributions(project_paths, start_date, end_date)

    # Display summary (without comparison)
    formatter.format_executive_summary(period_stats, previous_period=None)

    # Display contributor leaderboard
    formatter.format_contributor_leaderboard(period_stats.contributions, limit=15)

    # Display project breakdown
    formatter.format_project_breakdown(period_stats)

    return {
        "mode": "contributions",
        "days": days,
        "total_mrs": period_stats.contributions.total_mrs,
        "active_contributors": period_stats.contributions.active_contributors,
    }
