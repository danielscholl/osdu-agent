"""Tests for copilot module (TestRunner, TestTracker, TriageRunner, TriageTracker)."""

from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from agent.copilot import SERVICES, TestTracker, parse_services
from agent.copilot.runners.copilot_runner import CopilotRunner


class TestParseServices:
    """Tests for parse_services function."""

    def test_parse_single_service(self):
        """Test parsing a single service name."""
        result = parse_services("partition")
        assert result == ["partition"]

    def test_parse_multiple_services(self):
        """Test parsing comma-separated services."""
        result = parse_services("partition,legal,schema")
        assert result == ["partition", "legal", "schema"]

    def test_parse_all_services(self):
        """Test parsing 'all' keyword."""
        result = parse_services("all")
        assert result == list(SERVICES.keys())
        assert len(result) == 10

    def test_parse_services_with_spaces(self):
        """Test parsing services with extra whitespace."""
        result = parse_services("partition , legal , schema")
        assert result == ["partition", "legal", "schema"]


class TestTestTracker:
    """Tests for TestTracker class."""

    def test_initialization(self):
        """Test TestTracker initialization."""
        services = ["partition", "legal"]
        tracker = TestTracker(services)

        assert len(tracker.services) == 2
        assert "partition" in tracker.services
        assert "legal" in tracker.services

        # Check initial state
        for service in services:
            assert tracker.services[service]["status"] == "pending"
            assert tracker.services[service]["phase"] is None
            assert tracker.services[service]["tests_run"] == 0
            assert tracker.services[service]["tests_failed"] == 0
            assert tracker.services[service]["coverage_line"] == 0
            assert tracker.services[service]["coverage_branch"] == 0
            assert tracker.services[service]["icon"] == "⏸"

    def test_update_basic_status(self):
        """Test updating service status."""
        tracker = TestTracker(["partition"])
        tracker.update("partition", "compiling", "Compiling source code")

        assert tracker.services["partition"]["status"] == "compiling"
        assert tracker.services["partition"]["details"] == "Compiling source code"
        assert tracker.services["partition"]["icon"] == "▶"

    def test_update_with_phase(self):
        """Test updating service with phase."""
        tracker = TestTracker(["partition"])
        tracker.update("partition", "testing", "Running tests", phase="test")

        assert tracker.services["partition"]["status"] == "testing"
        assert tracker.services["partition"]["phase"] == "test"
        assert tracker.services["partition"]["icon"] == "▶"

    def test_update_with_test_results(self):
        """Test updating with test results."""
        tracker = TestTracker(["partition"])
        tracker.update(
            "partition",
            "testing",
            "Tests running",
            tests_run=42,
            tests_failed=2,
        )

        assert tracker.services["partition"]["tests_run"] == 42
        assert tracker.services["partition"]["tests_failed"] == 2

    def test_update_with_coverage(self):
        """Test updating with coverage data."""
        tracker = TestTracker(["partition"])
        tracker.update(
            "partition",
            "coverage",
            "Generating coverage",
            coverage_line=78,
            coverage_branch=65,
        )

        assert tracker.services["partition"]["coverage_line"] == 78
        assert tracker.services["partition"]["coverage_branch"] == 65
        assert tracker.services["partition"]["icon"] == "▶"

    def test_update_invalid_service(self):
        """Test updating non-existent service does not error."""
        tracker = TestTracker(["partition"])
        # Should not raise error
        tracker.update("nonexistent", "testing", "Should be ignored")

        # Original service should be unchanged
        assert tracker.services["partition"]["status"] == "pending"

    def test_get_table(self):
        """Test generating Rich table."""
        tracker = TestTracker(["partition", "legal"])
        tracker.update("partition", "testing", "Running tests", tests_run=10, tests_failed=2)
        tracker.update("legal", "compile_success", "Compilation successful")

        table = tracker.get_table()

        assert table.title == "[italic]Service Status[/italic]"
        assert len(table.columns) == 4  # Service, Provider, Status, Details

    def test_status_icons(self):
        """Test that different statuses have correct icons."""
        tracker = TestTracker(["partition"])

        status_icon_map = {
            "pending": "⏸",
            "compiling": "▶",
            "testing": "▶",
            "coverage": "▶",
            "compile_success": "✓",
            "test_success": "✓",
            "compile_failed": "✗",
            "test_failed": "✗",
            "error": "✗",
        }

        for status, expected_icon in status_icon_map.items():
            tracker.update("partition", status, f"Testing {status}")
            assert tracker.services["partition"]["icon"] == expected_icon


class TestCopilotRunner:
    """Tests for CopilotRunner class (fork command)."""

    @pytest.fixture
    def mock_prompt_file(self, tmp_path):
        """Create a mock prompt file."""
        prompt_file = tmp_path / "fork.md"
        prompt_file.write_text(
            "Fork prompt template\n{{ORGANIZATION}}\nARGUMENTS:\nSERVICES: {{services}}\nBRANCH: {{branch}}"
        )
        return prompt_file

    def test_service_in_line_exact_match(self):
        """Test _service_in_line with exact service name match."""
        runner = CopilotRunner(["partition"], branch="main")

        # Should match exact service name
        assert runner._service_in_line("partition", "partition service completed") is True
        assert (
            runner._service_in_line(
                "partition", "✅ Successfully completed workflow for partition service"
            )
            is True
        )

    def test_service_in_line_no_substring_match(self):
        """Test _service_in_line does NOT match when service is substring of another word."""
        runner = CopilotRunner(["indexer", "indexer-queue"], branch="main")

        # "indexer" should NOT match within "indexer-queue"
        assert (
            runner._service_in_line(
                "indexer", "✅ Successfully completed workflow for indexer-queue service"
            )
            is False
        )

        # "indexer-queue" should match exactly
        assert (
            runner._service_in_line(
                "indexer-queue", "✅ Successfully completed workflow for indexer-queue service"
            )
            is True
        )

    def test_service_in_line_hyphenated_names(self):
        """Test _service_in_line with hyphenated service names."""
        runner = CopilotRunner(["indexer-queue"], branch="main")

        # Should match complete hyphenated name
        assert runner._service_in_line("indexer-queue", "indexer-queue service is ready") is True
        assert runner._service_in_line("indexer-queue", "the indexer-queue repository") is True

        # Should NOT match partial hyphenated name
        assert runner._service_in_line("indexer", "indexer-queue service is ready") is False

    def test_service_in_line_word_boundaries(self):
        """Test _service_in_line respects word boundaries."""
        runner = CopilotRunner(["legal", "partition"], branch="main")

        # Should match at word boundaries
        assert runner._service_in_line("legal", "legal service completed") is True
        assert runner._service_in_line("legal", "the legal repository") is True
        assert runner._service_in_line("legal", "✓ legal: done") is True

        # Should NOT match within other words
        assert runner._service_in_line("legal", "illegally parsed") is False

    def test_parse_output_indexer_queue_completion(self):
        """
        Regression test: Verify indexer-queue completion is parsed correctly.

        This test ensures that when the line "✅ Successfully completed workflow for indexer-queue service"
        is parsed, only the indexer-queue service status is updated, NOT the indexer service.

        Bug: Previously, "indexer" would match within "indexer-queue" due to substring matching,
        causing the wrong service to be marked as complete.
        """
        runner = CopilotRunner(
            ["partition", "indexer", "indexer-queue", "search"], branch="main"
        )

        # Initially all services are pending
        assert runner.tracker.services["indexer"]["status"] == "pending"
        assert runner.tracker.services["indexer-queue"]["status"] == "pending"

        # Parse the indexer-queue completion line
        runner.parse_output("✅ Successfully completed workflow for indexer-queue service")

        # indexer-queue should be marked as success
        assert runner.tracker.services["indexer-queue"]["status"] == "success"
        assert runner.tracker.services["indexer-queue"]["details"] == "Completed successfully"

        # indexer should still be pending (NOT updated by mistake)
        assert runner.tracker.services["indexer"]["status"] == "pending"

        # Other services should remain pending
        assert runner.tracker.services["partition"]["status"] == "pending"
        assert runner.tracker.services["search"]["status"] == "pending"

    def test_parse_output_indexer_completion(self):
        """Test that indexer service completion is parsed correctly."""
        runner = CopilotRunner(["indexer", "indexer-queue"], branch="main")

        # Parse the indexer completion line (not indexer-queue)
        runner.parse_output("✅ Successfully completed workflow for indexer service")

        # indexer should be marked as success
        assert runner.tracker.services["indexer"]["status"] == "success"

        # indexer-queue should still be pending
        assert runner.tracker.services["indexer-queue"]["status"] == "pending"

    def test_parse_output_multiple_hyphenated_services(self):
        """Test parsing with multiple hyphenated service names."""
        runner = CopilotRunner(
            ["partition", "file", "storage", "indexer", "indexer-queue", "workflow"],
            branch="main",
        )

        # Test workflow completion (workflow is also a common word in output)
        runner.parse_output("✅ Successfully completed workflow for workflow service")
        assert runner.tracker.services["workflow"]["status"] == "success"
        assert runner.tracker.services["indexer"]["status"] == "pending"

        # Test partition completion
        runner.parse_output("✅ Successfully completed workflow for partition service")
        assert runner.tracker.services["partition"]["status"] == "success"

    def test_parse_output_service_order_independence(self):
        """
        Test that service matching is independent of service order.

        Previously, the bug would occur because services were checked in order,
        and "indexer" appeared before "indexer-queue" in the list, causing
        early substring match and break.
        """
        # Test with indexer-queue before indexer
        runner1 = CopilotRunner(["indexer-queue", "indexer"], branch="main")
        runner1.parse_output("✅ Successfully completed workflow for indexer-queue service")
        assert runner1.tracker.services["indexer-queue"]["status"] == "success"
        assert runner1.tracker.services["indexer"]["status"] == "pending"

        # Test with indexer before indexer-queue (original bug scenario)
        runner2 = CopilotRunner(["indexer", "indexer-queue"], branch="main")
        runner2.parse_output("✅ Successfully completed workflow for indexer-queue service")
        assert runner2.tracker.services["indexer-queue"]["status"] == "success"
        assert runner2.tracker.services["indexer"]["status"] == "pending"

    def test_parse_output_task_markers_with_indexer_queue(self):
        """Test that task completion markers correctly identify indexer-queue."""
        runner = CopilotRunner(["indexer", "indexer-queue"], branch="main")

        # Test task marker for indexer-queue
        runner.parse_output("✓ Create indexer-queue repo from template")
        assert runner.tracker.services["indexer-queue"]["status"] == "running"
        assert "Creating repository" in runner.tracker.services["indexer-queue"]["details"]

        # indexer should not be affected
        assert runner.tracker.services["indexer"]["status"] == "pending"

