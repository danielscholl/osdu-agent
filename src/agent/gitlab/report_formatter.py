"""Report formatting with Rich console output for GitLab analytics."""

from typing import List, Optional, Tuple

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from agent.gitlab.models import ADRStats, ContributionStats, PeriodStats, TrendIndicator


class ReportFormatter:
    """Formatter for GitLab contribution reports with Rich console output."""

    def __init__(self, console: Optional[Console] = None):
        """
        Initialize formatter with console.

        Args:
            console: Rich Console instance (creates new one if None)
        """
        self.console = console or Console()

    def format_report_header(
        self,
        services: List[str],
        mode: str,
        days: int,
        periods: int = 1,
    ) -> None:
        """
        Format and display report execution header panel.

        Args:
            services: List of service names being analyzed
            mode: Report mode (compare, adr, trends, contributions)
            days: Number of days per period
            periods: Number of previous periods for comparison
        """
        # Build header lines
        header_lines = []
        header_lines.append(f"[bold]Services:[/bold]   {', '.join(services)}")
        header_lines.append(f"[bold]Mode:[/bold]       {mode}")
        header_lines.append(f"[bold]Period:[/bold]     {days} days")

        if mode == "compare" and periods > 1:
            header_lines.append(f"[bold]Comparison:[/bold] Current vs {periods} previous periods")
        elif mode == "trends":
            header_lines.append("[bold]Trends:[/bold]     12 months")

        # Display panel
        panel = Panel(
            "\n".join(header_lines),
            title="[bold white]Report Execution[/bold white]",
            border_style="cyan",
            padding=(1, 2),
        )
        self.console.print()
        self.console.print(panel)
        self.console.print()

    def format_executive_summary(
        self, current_period: PeriodStats, previous_period: Optional[PeriodStats] = None
    ) -> None:
        """
        Format and display executive summary panel.

        Args:
            current_period: Current period statistics
            previous_period: Previous period statistics for comparison
        """
        # Calculate trend indicators
        trends = {}
        if previous_period:
            trends["total_mrs"] = TrendIndicator(
                current_period.contributions.total_mrs, previous_period.contributions.total_mrs
            )
            trends["merged_mrs"] = TrendIndicator(
                current_period.contributions.merged_mrs, previous_period.contributions.merged_mrs
            )
            trends["active_contributors"] = TrendIndicator(
                current_period.contributions.active_contributors,
                previous_period.contributions.active_contributors,
            )
            trends["comments"] = TrendIndicator(
                current_period.contributions.comments, previous_period.contributions.comments
            )
            trends["approvals"] = TrendIndicator(
                current_period.contributions.approvals, previous_period.contributions.approvals
            )

        # Build summary text
        summary_lines = []
        summary_lines.append(
            f"[bold]Period:[/bold] {current_period.start_date.strftime('%Y-%m-%d')} to {current_period.end_date.strftime('%Y-%m-%d')} ({current_period.days} days)"
        )
        summary_lines.append("")

        # Key metrics
        contrib = current_period.contributions
        summary_lines.append(f"[bold cyan]Total MRs:[/bold cyan] {contrib.total_mrs}")
        if "total_mrs" in trends:
            summary_lines.append(
                f"  {trends['total_mrs'].indicator_symbol} {trends['total_mrs'].percent_change:+.1f}% from previous period"
            )

        summary_lines.append(
            f"[bold green]Merged:[/bold green] {contrib.merged_mrs} | [bold yellow]Open:[/bold yellow] {contrib.open_mrs} | [bold red]Closed:[/bold red] {contrib.closed_mrs}"
        )
        if "merged_mrs" in trends:
            summary_lines.append(
                f"  {trends['merged_mrs'].indicator_symbol} Merged {trends['merged_mrs'].percent_change:+.1f}%"
            )

        summary_lines.append("")
        summary_lines.append(
            f"[bold cyan]Active Contributors:[/bold cyan] {contrib.active_contributors}"
        )
        if "active_contributors" in trends:
            summary_lines.append(
                f"  {trends['active_contributors'].indicator_symbol} {trends['active_contributors'].percent_change:+.1f}%"
            )

        summary_lines.append(
            f"[bold cyan]Comments:[/bold cyan] {contrib.comments} | [bold cyan]Approvals:[/bold cyan] {contrib.approvals}"
        )
        if "comments" in trends:
            summary_lines.append(
                f"  {trends['comments'].indicator_symbol} Comments {trends['comments'].percent_change:+.1f}%"
            )
        if "approvals" in trends:
            summary_lines.append(
                f"  {trends['approvals'].indicator_symbol} Approvals {trends['approvals'].percent_change:+.1f}%"
            )

        # ADR summary if available
        if current_period.adrs and current_period.adrs.total_adrs > 0:
            summary_lines.append("")
            summary_lines.append(
                f"[bold magenta]ADRs:[/bold magenta] {current_period.adrs.total_adrs} total | {current_period.adrs.open_adrs} open | {current_period.adrs.approved_adrs} approved"
            )

        # Display panel
        panel = Panel(
            "\n".join(summary_lines),
            title="[bold white]Executive Summary[/bold white]",
            border_style="cyan",
            padding=(1, 2),
        )
        self.console.print(panel)
        self.console.print()

    def format_comparison_table(self, periods: List[PeriodStats]) -> None:
        """
        Format and display period-over-period comparison table.

        Args:
            periods: List of PeriodStats (current first, then previous periods)
        """
        if len(periods) < 2:
            return

        table = Table(title="Period-over-Period Comparison", show_header=True, header_style="bold")
        table.add_column("Metric", style="cyan", no_wrap=True)

        # Add column for each period
        for i, period in enumerate(periods):
            if i == 0:
                table.add_column("Current", justify="right", style="bold green")
            else:
                table.add_column(f"Period -{i}", justify="right")

        # Add rows for each metric
        metrics = [
            ("Total MRs", "total_mrs"),
            ("Merged MRs", "merged_mrs"),
            ("Open MRs", "open_mrs"),
            ("Closed MRs", "closed_mrs"),
            ("Active Contributors", "active_contributors"),
            ("Comments", "comments"),
            ("Approvals", "approvals"),
        ]

        for metric_name, metric_attr in metrics:
            row = [metric_name]
            values = []

            for period in periods:
                value = getattr(period.contributions, metric_attr)
                values.append(value)
                row.append(str(value))

            # Add trend indicator to current value
            if len(values) >= 2:
                trend = TrendIndicator(values[0], values[1])
                row[1] = f"{values[0]} {trend.indicator_symbol}"

            table.add_row(*row)

        self.console.print(table)
        self.console.print()

    def format_contributor_leaderboard(
        self, contributions: ContributionStats, limit: int = 10
    ) -> None:
        """
        Format and display top contributors leaderboard.

        Args:
            contributions: Contribution statistics
            limit: Maximum number of contributors to show
        """
        if not contributions.contributors:
            return

        # Sort contributors by total activity
        # Weight approvals higher (2x) as they identify maintainers
        sorted_contributors = sorted(
            contributions.contributors.items(),
            key=lambda x: x[1].get("mrs", 0)
            + x[1].get("comments", 0)
            + x[1].get("approvals", 0) * 2,
            reverse=True,
        )

        table = Table(title=f"Top {limit} Contributors", show_header=True, header_style="bold")
        table.add_column("Contributor", style="cyan")
        table.add_column("MRs", justify="right", style="green")
        table.add_column("Comments", justify="right", style="blue")
        table.add_column("Approvals", justify="right", style="magenta")

        for username, stats in sorted_contributors[:limit]:
            table.add_row(
                username,
                str(stats.get("mrs", 0)),
                str(stats.get("comments", 0)),
                str(stats.get("approvals", 0)),
            )

        self.console.print(table)
        self.console.print()

    def format_project_breakdown(self, period_stats: PeriodStats) -> None:
        """
        Format and display project-level breakdown.

        Args:
            period_stats: Period statistics with project breakdown
        """
        if not period_stats.project_breakdown:
            return

        table = Table(title="Project Breakdown", show_header=True, header_style="bold")
        table.add_column("Project", style="cyan")
        table.add_column("Total MRs", justify="right")
        table.add_column("Merged", justify="right", style="green")
        table.add_column("Open", justify="right", style="yellow")
        table.add_column("Contributors", justify="right", style="blue")

        for project_path, project_stats in period_stats.project_breakdown.items():
            contrib = project_stats.contributions
            table.add_row(
                project_stats.project_name,
                str(contrib.total_mrs),
                str(contrib.merged_mrs),
                str(contrib.open_mrs),
                str(contrib.active_contributors),
            )

        self.console.print(table)
        self.console.print()

    def format_adr_analysis(self, adr_stats_list: List[Tuple[str, ADRStats]]) -> None:
        """
        Format and display ADR analysis table.

        Args:
            adr_stats_list: List of (period_name, ADRStats) tuples
        """
        if not adr_stats_list:
            return

        table = Table(title="ADR Analysis", show_header=True, header_style="bold")
        table.add_column("Period", style="cyan")
        table.add_column("Total ADRs", justify="right")
        table.add_column("Open", justify="right", style="yellow")
        table.add_column("Approved", justify="right", style="green")
        table.add_column("Participants", justify="right", style="blue")
        table.add_column("Comments", justify="right", style="magenta")

        for period_name, adr_stats in adr_stats_list:
            table.add_row(
                period_name,
                str(adr_stats.total_adrs),
                str(adr_stats.open_adrs),
                str(adr_stats.approved_adrs),
                str(adr_stats.participants),
                str(adr_stats.comments_count),
            )

        self.console.print(table)
        self.console.print()

    def format_adr_details(self, adr_stats: ADRStats, limit: int = 10) -> None:
        """
        Format and display detailed ADR list.

        Args:
            adr_stats: ADR statistics with details
            limit: Maximum number of ADRs to show
        """
        if not adr_stats.adr_details:
            return

        table = Table(
            title=f"Recent ADRs (showing {min(limit, len(adr_stats.adr_details))})",
            show_header=True,
            header_style="bold",
        )
        table.add_column("IID", style="cyan", no_wrap=True)
        table.add_column("Title", style="white")
        table.add_column("State", justify="center")
        table.add_column("Author", style="blue")

        for adr in adr_stats.adr_details[:limit]:
            # Color code state
            state = adr.get("state", "unknown")
            labels = adr.get("labels", [])

            if "ADR::Approved" in labels:
                state_text = "[green]Approved[/green]"
            elif "ADR::Proposed" in labels:
                state_text = "[yellow]Proposed[/yellow]"
            elif state == "opened":
                state_text = "[yellow]Open[/yellow]"
            else:
                state_text = f"[dim]{state}[/dim]"

            table.add_row(
                f"#{adr.get('iid', '?')}",
                adr.get("title", ""),
                state_text,
                adr.get("author", "unknown"),
            )

        self.console.print(table)
        self.console.print()

    def format_trend_chart(self, metric_name: str, values: List[int], labels: List[str]) -> None:
        """
        Format and display ASCII bar chart for trend visualization.

        Args:
            metric_name: Name of the metric being charted
            values: List of values (one per period)
            labels: List of labels for each period
        """
        if not values or len(values) != len(labels):
            return

        # Calculate max value for scaling
        max_value = max(values) if values else 1
        bar_width = 40  # Max width of bars in characters

        self.console.print(f"[bold]{metric_name} Trend[/bold]")
        self.console.print()

        for label, value in zip(labels, values):
            # Calculate bar length
            if max_value > 0:
                bar_length = int((value / max_value) * bar_width)
            else:
                bar_length = 0

            # Create bar with color based on value
            if value > max_value * 0.7:
                bar_color = "green"
            elif value > max_value * 0.4:
                bar_color = "yellow"
            else:
                bar_color = "red"

            bar = "█" * bar_length
            bar_colored = f"[{bar_color}]{bar}[/{bar_color}]"

            # Print label and bar
            self.console.print(f"{label:15} {bar_colored} {value}")

        self.console.print()

    def print_error(self, message: str) -> None:
        """
        Print error message.

        Args:
            message: Error message to display
        """
        self.console.print(f"[bold red]Error:[/bold red] {message}")

    def print_info(self, message: str) -> None:
        """
        Print info message.

        Args:
            message: Info message to display
        """
        self.console.print(f"[cyan]{message}[/cyan]")

    def print_success(self, message: str) -> None:
        """
        Print success message.

        Args:
            message: Success message to display
        """
        self.console.print(f"[bold green]✓[/bold green] {message}")
