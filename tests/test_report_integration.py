"""Integration tests for report workflow with mocked GitLab API."""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent.gitlab.analytics import GitLabContributionAnalyzer
from agent.gitlab.models import ReportMode
from agent.workflows.report_workflow import (
    _generate_adr_report,
    _generate_comparison_report,
    _generate_contributions_report,
    _generate_trends_report,
    run_report_workflow,
)


# Sample GitLab data fixtures
@pytest.fixture
def sample_merge_requests():
    """Sample MR data for testing."""
    now = datetime.now(timezone.utc)
    return [
        {
            "iid": 1,
            "title": "Fix authentication bug",
            "state": "merged",
            "author": "alice",
            "created_at": (now - timedelta(days=5)).isoformat(),
            "merged_at": (now - timedelta(days=3)).isoformat(),
            "approved_by": ["bob", "charlie"],
        },
        {
            "iid": 2,
            "title": "Add new feature",
            "state": "opened",
            "author": "bob",
            "created_at": (now - timedelta(days=10)).isoformat(),
            "merged_at": None,
            "approved_by": [],
        },
        {
            "iid": 3,
            "title": "Refactor code",
            "state": "merged",
            "author": "charlie",
            "created_at": (now - timedelta(days=15)).isoformat(),
            "merged_at": (now - timedelta(days=12)).isoformat(),
            "approved_by": ["alice"],
        },
    ]


@pytest.fixture
def sample_discussions():
    """Sample discussion data for testing."""
    return [
        {"id": 1, "author": "bob", "body": "LGTM", "system": False},
        {"id": 2, "author": "charlie", "body": "Looks good", "system": False},
        {"id": 3, "author": "alice", "body": "Great work", "system": False},
    ]


@pytest.fixture
def sample_adrs():
    """Sample ADR issue data for testing."""
    now = datetime.now(timezone.utc)
    return [
        {
            "iid": 100,
            "title": "ADR: Use PostgreSQL for data storage",
            "state": "opened",
            "labels": ["ADR", "ADR::Proposed"],
            "author": "alice",
            "assignees": ["bob"],
            "user_notes_count": 5,
            "created_at": (now - timedelta(days=7)).isoformat(),
            "web_url": "https://gitlab.com/project/issues/100",
        },
        {
            "iid": 101,
            "title": "ADR: API versioning strategy",
            "state": "closed",
            "labels": ["ADR", "ADR::Approved"],
            "author": "bob",
            "assignees": ["alice", "charlie"],
            "user_notes_count": 12,
            "created_at": (now - timedelta(days=20)).isoformat(),
            "web_url": "https://gitlab.com/project/issues/101",
        },
    ]


@pytest.mark.asyncio
async def test_analyze_contributions_with_mock_data(sample_merge_requests, sample_discussions):
    """Test contribution analysis with mocked GitLab data."""
    # Create mock config and client
    mock_config = MagicMock()
    mock_client = MagicMock()

    # Mock client methods
    mock_client.get_merge_requests_for_period = AsyncMock(return_value=sample_merge_requests)
    mock_client.get_merge_request_discussions = AsyncMock(return_value=sample_discussions)
    mock_client.get_merge_request_approvals = AsyncMock(
        side_effect=[["bob", "charlie"], [], ["alice"]]
    )

    # Create analyzer
    analyzer = GitLabContributionAnalyzer(mock_config, mock_client)

    # Analyze contributions
    start_date = datetime.now(timezone.utc) - timedelta(days=30)
    end_date = datetime.now(timezone.utc)
    result = await analyzer.analyze_contributions(["test/project"], start_date, end_date)

    # Verify results
    assert result.contributions.total_mrs == 3
    assert result.contributions.merged_mrs == 2
    assert result.contributions.open_mrs == 1
    assert result.contributions.approvals == 3  # bob, charlie, alice
    assert result.contributions.comments == 9  # 3 discussions per MR
    assert result.contributions.active_contributors > 0


@pytest.mark.asyncio
async def test_analyze_adrs_with_mock_data(sample_adrs):
    """Test ADR analysis with mocked GitLab data."""
    # Create mock config and client
    mock_config = MagicMock()
    mock_client = MagicMock()

    # Mock client methods
    mock_client.get_issues_by_labels = AsyncMock(return_value=sample_adrs)

    # Create analyzer
    analyzer = GitLabContributionAnalyzer(mock_config, mock_client)

    # Analyze ADRs
    start_date = datetime.now(timezone.utc) - timedelta(days=30)
    end_date = datetime.now(timezone.utc)
    result = await analyzer.analyze_adrs(["test/project"], start_date, end_date)

    # Verify results
    assert result.total_adrs == 2
    assert result.open_adrs == 1
    assert result.approved_adrs == 1
    assert result.participants == 3  # alice, bob, charlie
    assert result.comments_count == 17  # 5 + 12


@pytest.mark.asyncio
async def test_generate_comparison_report_with_mocks(sample_merge_requests, sample_discussions):
    """Test comparison report generation with mocked data."""
    from io import StringIO

    from rich.console import Console

    from agent.gitlab.report_formatter import ReportFormatter

    # Create mocks
    mock_config = MagicMock()
    mock_client = MagicMock()
    mock_client.get_merge_requests_for_period = AsyncMock(return_value=sample_merge_requests)
    mock_client.get_merge_request_discussions = AsyncMock(return_value=sample_discussions)
    mock_client.get_merge_request_approvals = AsyncMock(
        side_effect=[["bob", "charlie"], [], ["alice"]]
    )

    # Create analyzer with mocked client
    analyzer = GitLabContributionAnalyzer(mock_config, mock_client)

    # Create formatter with string buffer
    string_buffer = StringIO()
    console = Console(file=string_buffer, force_terminal=True, width=120)
    formatter = ReportFormatter(console)

    # Generate report
    result = await _generate_comparison_report(
        analyzer=analyzer,
        formatter=formatter,
        project_paths=["test/project"],
        days=30,
        num_periods=1,
    )

    # Verify result structure
    assert result["mode"] == "comparison"
    assert result["days_per_period"] == 30
    assert result["current_period"]["total_mrs"] == 3

    # Verify output was generated
    output = string_buffer.getvalue()
    assert "Executive Summary" in output
    assert "Top" in output  # Top contributors table


@pytest.mark.asyncio
async def test_generate_adr_report_with_mocks(sample_adrs):
    """Test ADR report generation with mocked data."""
    from io import StringIO

    from rich.console import Console

    from agent.gitlab.report_formatter import ReportFormatter

    # Create mocks
    mock_config = MagicMock()
    mock_client = MagicMock()
    mock_client.get_issues_by_labels = AsyncMock(return_value=sample_adrs)

    # Create analyzer
    analyzer = GitLabContributionAnalyzer(mock_config, mock_client)

    # Create formatter
    string_buffer = StringIO()
    console = Console(file=string_buffer, force_terminal=True, width=120)
    formatter = ReportFormatter(console)

    # Generate report
    result = await _generate_adr_report(
        analyzer=analyzer, formatter=formatter, project_paths=["test/project"], days=30
    )

    # Verify result
    assert result["mode"] == "adr"
    assert result["days"] == 30
    assert result["total_adrs"] == 2

    # Verify output
    output = string_buffer.getvalue()
    assert "ADR Summary" in output


@pytest.mark.asyncio
async def test_generate_contributions_report_with_mocks(
    sample_merge_requests, sample_discussions
):
    """Test contributions report generation with mocked data."""
    from io import StringIO

    from rich.console import Console

    from agent.gitlab.report_formatter import ReportFormatter

    # Create mocks
    mock_config = MagicMock()
    mock_client = MagicMock()
    mock_client.get_merge_requests_for_period = AsyncMock(return_value=sample_merge_requests)
    mock_client.get_merge_request_discussions = AsyncMock(return_value=sample_discussions)
    mock_client.get_merge_request_approvals = AsyncMock(
        side_effect=[["bob", "charlie"], [], ["alice"]]
    )

    # Create analyzer
    analyzer = GitLabContributionAnalyzer(mock_config, mock_client)

    # Create formatter
    string_buffer = StringIO()
    console = Console(file=string_buffer, force_terminal=True, width=120)
    formatter = ReportFormatter(console)

    # Generate report
    result = await _generate_contributions_report(
        analyzer=analyzer, formatter=formatter, project_paths=["test/project"], days=30
    )

    # Verify result
    assert result["mode"] == "contributions"
    assert result["total_mrs"] == 3


@pytest.mark.asyncio
async def test_generate_trends_report_with_mocks(sample_merge_requests, sample_discussions):
    """Test trends report generation with mocked data."""
    from io import StringIO

    from rich.console import Console

    from agent.gitlab.report_formatter import ReportFormatter

    # Create mocks
    mock_config = MagicMock()
    mock_client = MagicMock()
    mock_client.get_merge_requests_for_period = AsyncMock(return_value=sample_merge_requests)
    mock_client.get_merge_request_discussions = AsyncMock(return_value=sample_discussions)
    mock_client.get_merge_request_approvals = AsyncMock(return_value=[])

    # Create analyzer
    analyzer = GitLabContributionAnalyzer(mock_config, mock_client)

    # Create formatter
    string_buffer = StringIO()
    console = Console(file=string_buffer, force_terminal=True, width=120)
    formatter = ReportFormatter(console)

    # Generate report
    result = await _generate_trends_report(
        analyzer=analyzer, formatter=formatter, project_paths=["test/project"], months=3
    )

    # Verify result
    assert result["mode"] == "trends"
    assert result["months"] == 3


@pytest.mark.asyncio
async def test_run_report_workflow_integration():
    """Test full report workflow with service list."""
    with patch("agent.workflows.report_workflow.GitLabDirectClient") as mock_client_class:
        with patch("agent.workflows.report_workflow.AgentConfig") as mock_config_class:
            # Setup mocks
            mock_config = MagicMock()
            mock_config_class.return_value = mock_config

            mock_client = MagicMock()
            mock_client_class.return_value = mock_client

            # Mock GitLab URL and project path
            mock_client._get_upstream_url = AsyncMock(
                return_value="https://gitlab.com/test/project"
            )
            mock_client._parse_project_path = MagicMock(return_value="test/project")

            # Mock empty data (no MRs)
            mock_client.get_merge_requests_for_period = AsyncMock(return_value=[])
            mock_client.get_issues_by_labels = AsyncMock(return_value=[])

            # Run workflow
            result = await run_report_workflow(
                args_string="compare 7", services=["test-service"]
            )

            # Verify workflow completed
            assert result.workflow_type == "report"
            assert result.status == "success"
            assert "mode" in result.detailed_results


@pytest.mark.asyncio
async def test_report_formatter_methods():
    """Test report formatter methods with sample data."""
    from io import StringIO

    from rich.console import Console

    from agent.gitlab.models import ADRStats, ContributionStats, PeriodStats
    from agent.gitlab.report_formatter import ReportFormatter

    # Create formatter with string buffer
    string_buffer = StringIO()
    console = Console(file=string_buffer, force_terminal=True, width=120)
    formatter = ReportFormatter(console)

    # Test header
    formatter.format_report_header(
        services=["partition", "legal"], mode="compare", days=30, periods=2
    )

    # Test executive summary
    start = datetime.now(timezone.utc) - timedelta(days=30)
    end = datetime.now(timezone.utc)
    current = PeriodStats(start_date=start, end_date=end, days=30)
    current.contributions.total_mrs = 10
    current.contributions.merged_mrs = 8
    current.contributions.active_contributors = 5
    current.contributions.comments = 20
    current.contributions.approvals = 3

    formatter.format_executive_summary(current, previous_period=None)

    # Test with previous period for comparison
    previous = PeriodStats(
        start_date=start - timedelta(days=30), end_date=start, days=30
    )
    previous.contributions.total_mrs = 8
    previous.contributions.merged_mrs = 6
    previous.contributions.active_contributors = 4
    previous.contributions.comments = 15
    previous.contributions.approvals = 2

    formatter.format_executive_summary(current, previous)

    # Test comparison table
    formatter.format_comparison_table([current, previous])

    # Test contributor leaderboard
    current.contributions.contributors = {
        "alice": {"mrs": 3, "comments": 5, "approvals": 2},
        "bob": {"mrs": 2, "comments": 10, "approvals": 0},
        "charlie": {"mrs": 5, "comments": 5, "approvals": 1},
    }
    formatter.format_contributor_leaderboard(current.contributions, limit=3)

    # Test project breakdown
    from agent.gitlab.models import ProjectStats

    project = ProjectStats(project_name="test-project", project_path="test/project")
    project.contributions.total_mrs = 10
    project.contributions.merged_mrs = 8
    current.project_breakdown["test/project"] = project
    formatter.format_project_breakdown(current)

    # Test trend chart
    formatter.format_trend_chart("Total MRs", [10, 8, 12, 6], ["Current", "Month -1", "Month -2", "Month -3"])

    # Verify output was generated
    output = string_buffer.getvalue()
    assert len(output) > 100
    assert "Report Execution" in output
    assert "Executive Summary" in output


@pytest.mark.asyncio
async def test_analyze_trends_multiple_periods(sample_merge_requests, sample_discussions):
    """Test multi-period trend analysis."""
    # Create mocks
    mock_config = MagicMock()
    mock_client = MagicMock()
    mock_client.get_merge_requests_for_period = AsyncMock(return_value=sample_merge_requests)
    mock_client.get_merge_request_discussions = AsyncMock(return_value=sample_discussions)
    mock_client.get_merge_request_approvals = AsyncMock(return_value=["alice"])

    # Create analyzer
    analyzer = GitLabContributionAnalyzer(mock_config, mock_client)

    # Create 3 periods
    now = datetime.now(timezone.utc)
    periods = [
        (now - timedelta(days=30), now),
        (now - timedelta(days=60), now - timedelta(days=30)),
        (now - timedelta(days=90), now - timedelta(days=60)),
    ]

    # Analyze trends
    result = await analyzer.analyze_trends(["test/project"], periods)

    # Verify all periods analyzed
    assert len(result) == 3
    for period_stats in result:
        assert period_stats.contributions.total_mrs == 3
        assert period_stats.days == 30


@pytest.mark.asyncio
async def test_merge_contribution_stats():
    """Test merging contribution statistics."""
    from agent.gitlab.analytics import GitLabContributionAnalyzer
    from agent.gitlab.models import ContributionStats

    # Create analyzer (config/client not needed for this test)
    analyzer = GitLabContributionAnalyzer(MagicMock(), MagicMock())

    # Create two stats to merge
    stats1 = ContributionStats()
    stats1.total_mrs = 5
    stats1.merged_mrs = 4
    stats1.approvals = 3
    stats1.comments = 10
    stats1.contributors = {"alice": {"mrs": 3, "comments": 5, "approvals": 2}}

    stats2 = ContributionStats()
    stats2.total_mrs = 3
    stats2.merged_mrs = 2
    stats2.approvals = 1
    stats2.comments = 5
    stats2.contributors = {
        "alice": {"mrs": 1, "comments": 2, "approvals": 0},
        "bob": {"mrs": 2, "comments": 3, "approvals": 1},
    }

    # Merge
    merged = analyzer._merge_contribution_stats(stats1, stats2)

    # Verify merged results
    assert merged.total_mrs == 8
    assert merged.merged_mrs == 6
    assert merged.approvals == 4
    assert merged.comments == 15
    assert merged.active_contributors == 2
    assert merged.contributors["alice"]["mrs"] == 4
    assert merged.contributors["bob"]["mrs"] == 2


@pytest.mark.asyncio
async def test_report_workflow_error_handling():
    """Test report workflow error handling."""
    # Test with empty services list
    result = await run_report_workflow(args_string="", services=[])

    assert result.workflow_type == "report"
    # Should handle gracefully (either error or success with no data)
    assert result.status in ["error", "success"]


@pytest.mark.asyncio
async def test_adr_details_formatting():
    """Test ADR details table formatting."""
    from io import StringIO

    from rich.console import Console

    from agent.gitlab.models import ADRStats
    from agent.gitlab.report_formatter import ReportFormatter

    # Create formatter
    string_buffer = StringIO()
    console = Console(file=string_buffer, force_terminal=True, width=120)
    formatter = ReportFormatter(console)

    # Create ADR stats with details
    adr_stats = ADRStats()
    adr_stats.total_adrs = 2
    adr_stats.adr_details = [
        {
            "iid": 100,
            "title": "ADR: Use PostgreSQL",
            "state": "opened",
            "labels": ["ADR::Proposed"],
            "author": "alice",
        },
        {
            "iid": 101,
            "title": "ADR: API Versioning",
            "state": "closed",
            "labels": ["ADR::Approved"],
            "author": "bob",
        },
    ]

    # Format ADR details
    formatter.format_adr_details(adr_stats, limit=10)

    # Verify output
    output = string_buffer.getvalue()
    assert "Recent ADRs" in output
    assert "#100" in output
    assert "#101" in output


@pytest.mark.asyncio
async def test_empty_project_breakdown():
    """Test project breakdown with no projects."""
    from io import StringIO

    from rich.console import Console

    from agent.gitlab.models import PeriodStats
    from agent.gitlab.report_formatter import ReportFormatter

    # Create formatter
    string_buffer = StringIO()
    console = Console(file=string_buffer, force_terminal=True, width=120)
    formatter = ReportFormatter(console)

    # Create empty period stats
    start = datetime.now(timezone.utc) - timedelta(days=30)
    end = datetime.now(timezone.utc)
    period = PeriodStats(start_date=start, end_date=end, days=30)

    # Should not crash with empty breakdown
    formatter.format_project_breakdown(period)

    # Should not crash with empty contributors
    formatter.format_contributor_leaderboard(period.contributions, limit=10)


@pytest.mark.asyncio
async def test_info_and_error_messages():
    """Test formatter info and error messages."""
    from io import StringIO

    from rich.console import Console

    from agent.gitlab.report_formatter import ReportFormatter

    # Create formatter
    string_buffer = StringIO()
    console = Console(file=string_buffer, force_terminal=True, width=120)
    formatter = ReportFormatter(console)

    # Test messages
    formatter.print_info("Testing info message")
    formatter.print_error("Testing error message")
    formatter.print_success("Testing success message")

    # Verify output
    output = string_buffer.getvalue()
    assert "Testing info message" in output
    assert "Testing error message" in output
    assert "Testing success message" in output
