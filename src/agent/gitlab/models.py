"""Data models for GitLab reporting and analytics."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional


class ReportMode(str, Enum):
    """Report mode types for different analysis views."""

    COMPARISON = "compare"
    ADR = "adr"
    TRENDS = "trends"
    CONTRIBUTIONS = "contributions"


@dataclass
class ContributionStats:
    """Statistics for GitLab contributions in a given period.

    Attributes:
        total_mrs: Total number of merge requests
        open_mrs: Number of open merge requests
        merged_mrs: Number of merged merge requests
        closed_mrs: Number of closed (not merged) merge requests
        approvals: Number of formal approvals given (identifies maintainers)
        comments: Number of discussion comments (code review engagement)
        active_contributors: Number of unique contributors
        contributors: Detailed contributor data mapping username to stats
    """

    total_mrs: int = 0
    open_mrs: int = 0
    merged_mrs: int = 0
    closed_mrs: int = 0
    approvals: int = 0
    comments: int = 0
    active_contributors: int = 0
    contributors: Dict[str, Dict[str, int]] = field(default_factory=dict)


@dataclass
class ADRStats:
    """Statistics for Architecture Decision Records (ADRs).

    Attributes:
        total_adrs: Total number of ADRs
        open_adrs: Number of open/proposed ADRs
        approved_adrs: Number of approved ADRs
        participants: Number of unique ADR participants
        authored_count: Number of ADRs authored
        comments_count: Number of comments on ADRs
        adr_details: List of ADR issues with details
    """

    total_adrs: int = 0
    open_adrs: int = 0
    approved_adrs: int = 0
    participants: int = 0
    authored_count: int = 0
    comments_count: int = 0
    adr_details: List[Dict[str, any]] = field(default_factory=list)


@dataclass
class ProjectStats:
    """Statistics for a single project/repository.

    Attributes:
        project_name: Name of the project
        project_path: GitLab project path
        contributions: Contribution statistics for this project
        adrs: ADR statistics for this project
    """

    project_name: str
    project_path: str
    contributions: ContributionStats = field(default_factory=ContributionStats)
    adrs: ADRStats = field(default_factory=ADRStats)


@dataclass
class PeriodStats:
    """Statistics for a specific time period.

    Attributes:
        start_date: Period start date
        end_date: Period end date
        contributions: Aggregated contribution statistics
        adrs: Aggregated ADR statistics
        project_breakdown: Per-project statistics
        days: Number of days in period
    """

    start_date: datetime
    end_date: datetime
    contributions: ContributionStats = field(default_factory=ContributionStats)
    adrs: ADRStats = field(default_factory=ADRStats)
    project_breakdown: Dict[str, ProjectStats] = field(default_factory=dict)
    days: int = 0


@dataclass
class TrendIndicator:
    """Trend indicator with percentage change calculation.

    Attributes:
        value: Current value
        previous_value: Previous period value
        percent_change: Percentage change from previous to current
        indicator_symbol: Visual trend indicator (↑↑ ↑ → ↓ ↓↓)
    """

    value: float
    previous_value: Optional[float] = None
    percent_change: Optional[float] = None
    indicator_symbol: str = "→"

    def __post_init__(self):
        """Calculate percent change and indicator symbol."""
        if self.previous_value is not None and self.previous_value != 0:
            self.percent_change = ((self.value - self.previous_value) / self.previous_value) * 100
            self.indicator_symbol = self._calculate_indicator()
        elif self.previous_value == 0 and self.value > 0:
            self.percent_change = 100.0
            self.indicator_symbol = "↑↑"
        elif self.previous_value is None:
            self.percent_change = None
            self.indicator_symbol = "→"

    def _calculate_indicator(self) -> str:
        """Calculate trend indicator based on percent change.

        Returns:
            Trend symbol: ↑↑ (>20%), ↑ (>5%), → (±5%), ↓ (<-5%), ↓↓ (<-20%)
        """
        if self.percent_change is None:
            return "→"

        if self.percent_change > 20:
            return "↑↑"
        elif self.percent_change > 5:
            return "↑"
        elif self.percent_change < -20:
            return "↓↓"
        elif self.percent_change < -5:
            return "↓"
        else:
            return "→"


@dataclass
class ComparisonReport:
    """Multi-period comparison report data.

    Attributes:
        current_period: Statistics for current period
        previous_periods: List of statistics for previous periods
        trends: Mapping of metric names to trend indicators
        summary: Executive summary text
    """

    current_period: PeriodStats
    previous_periods: List[PeriodStats] = field(default_factory=list)
    trends: Dict[str, TrendIndicator] = field(default_factory=dict)
    summary: str = ""
