"""Tests for report workflow."""

from datetime import datetime

from agent.gitlab.models import ReportMode
from agent.workflows.report_workflow import (
    _calculate_period_dates,
    _parse_report_arguments,
)


def test_parse_report_arguments_default():
    """Test default argument parsing."""
    mode, days, periods = _parse_report_arguments("")
    assert mode == ReportMode.COMPARISON
    assert days == 30
    assert periods == 1


def test_parse_report_arguments_days_only():
    """Test parsing with only days specified."""
    mode, days, periods = _parse_report_arguments("60")
    assert mode == ReportMode.COMPARISON
    assert days == 60
    assert periods == 1


def test_parse_report_arguments_adr_mode():
    """Test ADR mode parsing."""
    mode, days, periods = _parse_report_arguments("adr")
    assert mode == ReportMode.ADR
    assert days == 30
    assert periods == 1


def test_parse_report_arguments_adr_with_days():
    """Test ADR mode with custom days."""
    mode, days, periods = _parse_report_arguments("adr 60")
    assert mode == ReportMode.ADR
    assert days == 60
    assert periods == 1


def test_parse_report_arguments_compare_mode():
    """Test compare mode parsing."""
    mode, days, periods = _parse_report_arguments("compare")
    assert mode == ReportMode.COMPARISON
    assert days == 30
    assert periods == 1


def test_parse_report_arguments_compare_with_periods():
    """Test compare mode with periods."""
    mode, days, periods = _parse_report_arguments("compare 14 periods=3")
    assert mode == ReportMode.COMPARISON
    assert days == 14
    assert periods == 3


def test_parse_report_arguments_periods_flag():
    """Test periods flag with equals."""
    mode, days, periods = _parse_report_arguments("periods=4")
    assert mode == ReportMode.COMPARISON
    assert days == 30
    assert periods == 4


def test_parse_report_arguments_trends_mode():
    """Test trends mode parsing."""
    mode, days, periods = _parse_report_arguments("trends")
    assert mode == ReportMode.TRENDS
    assert days == 30
    assert periods == 1


def test_parse_report_arguments_contributions_mode():
    """Test contributions mode parsing."""
    mode, days, periods = _parse_report_arguments("contributions")
    assert mode == ReportMode.CONTRIBUTIONS
    assert days == 30
    assert periods == 1


def test_calculate_period_dates_single():
    """Test calculating single period."""
    periods = _calculate_period_dates(30, 1)
    assert len(periods) == 1

    start, end = periods[0]
    assert isinstance(start, datetime)
    assert isinstance(end, datetime)

    # Check period is approximately 30 days
    delta = (end - start).days
    assert delta == 30


def test_calculate_period_dates_multiple():
    """Test calculating multiple periods."""
    periods = _calculate_period_dates(30, 3)
    assert len(periods) == 3

    # Check all periods are sequential
    for i in range(len(periods) - 1):
        current_start, current_end = periods[i]
        next_start, next_end = periods[i + 1]

        # Current period should be more recent than next
        assert current_end > next_end
        assert current_start > next_start


def test_calculate_period_dates_custom_days():
    """Test calculating periods with custom days."""
    periods = _calculate_period_dates(7, 2)
    assert len(periods) == 2

    start, end = periods[0]
    delta = (end - start).days
    assert delta == 7
