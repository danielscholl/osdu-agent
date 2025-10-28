"""Tests for GitLab data models."""

from datetime import datetime

from agent.gitlab.models import (
    ContributionStats,
    ADRStats,
    PeriodStats,
    ProjectStats,
    TrendIndicator,
    ReportMode,
    ComparisonReport,
)


def test_contribution_stats_defaults():
    """Test ContributionStats default values."""
    stats = ContributionStats()
    assert stats.total_mrs == 0
    assert stats.open_mrs == 0
    assert stats.merged_mrs == 0
    assert stats.closed_mrs == 0
    assert stats.approvals == 0
    assert stats.comments == 0
    assert stats.active_contributors == 0
    assert stats.contributors == {}


def test_adr_stats_defaults():
    """Test ADRStats default values."""
    stats = ADRStats()
    assert stats.total_adrs == 0
    assert stats.open_adrs == 0
    assert stats.approved_adrs == 0
    assert stats.participants == 0
    assert stats.authored_count == 0
    assert stats.comments_count == 0
    assert stats.adr_details == []


def test_trend_indicator_increase():
    """Test TrendIndicator with increase."""
    trend = TrendIndicator(value=100, previous_value=80)
    assert trend.percent_change == 25.0
    assert trend.indicator_symbol == "↑↑"


def test_trend_indicator_decrease():
    """Test TrendIndicator with decrease."""
    trend = TrendIndicator(value=60, previous_value=100)
    assert trend.percent_change == -40.0
    assert trend.indicator_symbol == "↓↓"


def test_trend_indicator_stable():
    """Test TrendIndicator with small change."""
    trend = TrendIndicator(value=102, previous_value=100)
    assert trend.percent_change == 2.0
    assert trend.indicator_symbol == "→"


def test_trend_indicator_from_zero():
    """Test TrendIndicator with previous value of zero."""
    trend = TrendIndicator(value=50, previous_value=0)
    assert trend.percent_change == 100.0
    assert trend.indicator_symbol == "↑↑"


def test_trend_indicator_no_previous():
    """Test TrendIndicator with no previous value."""
    trend = TrendIndicator(value=50)
    assert trend.percent_change is None
    assert trend.indicator_symbol == "→"


def test_report_mode_enum():
    """Test ReportMode enum values."""
    assert ReportMode.COMPARISON.value == "compare"
    assert ReportMode.ADR.value == "adr"
    assert ReportMode.TRENDS.value == "trends"
    assert ReportMode.CONTRIBUTIONS.value == "contributions"


def test_project_stats_creation():
    """Test ProjectStats creation."""
    stats = ProjectStats(project_name="test-project", project_path="osdu/platform/test-project")
    assert stats.project_name == "test-project"
    assert stats.project_path == "osdu/platform/test-project"
    assert isinstance(stats.contributions, ContributionStats)
    assert isinstance(stats.adrs, ADRStats)


def test_period_stats_creation():
    """Test PeriodStats creation."""
    start = datetime(2025, 1, 1)
    end = datetime(2025, 1, 31)
    stats = PeriodStats(start_date=start, end_date=end, days=30)

    assert stats.start_date == start
    assert stats.end_date == end
    assert stats.days == 30
    assert isinstance(stats.contributions, ContributionStats)
    assert isinstance(stats.adrs, ADRStats)
    assert stats.project_breakdown == {}


def test_comparison_report_creation():
    """Test ComparisonReport creation."""
    start = datetime(2025, 1, 1)
    end = datetime(2025, 1, 31)
    current = PeriodStats(start_date=start, end_date=end, days=30)

    report = ComparisonReport(current_period=current)
    assert report.current_period == current
    assert report.previous_periods == []
    assert report.trends == {}
    assert report.summary == ""


def test_trend_indicator_thresholds():
    """Test TrendIndicator threshold values."""
    # Strong increase (>20%)
    trend = TrendIndicator(value=130, previous_value=100)
    assert trend.indicator_symbol == "↑↑"

    # Moderate increase (>5%, <=20%)
    trend = TrendIndicator(value=110, previous_value=100)
    assert trend.indicator_symbol == "↑"

    # Stable (±5%)
    trend = TrendIndicator(value=103, previous_value=100)
    assert trend.indicator_symbol == "→"

    # Moderate decrease (<-5%, >=-20%)
    trend = TrendIndicator(value=90, previous_value=100)
    assert trend.indicator_symbol == "↓"

    # Strong decrease (<-20%)
    trend = TrendIndicator(value=70, previous_value=100)
    assert trend.indicator_symbol == "↓↓"
