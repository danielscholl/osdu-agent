"""Tests for triage functionality (VulnsRunner, VulnsTracker)."""

from unittest.mock import AsyncMock, Mock, patch

import pytest

from agent.copilot import VulnsRunner, VulnsTracker


class TestVulnsTracker:
    """Tests for VulnsTracker class."""

    def test_initialization(self):
        """Test VulnsTracker initialization."""
        services = ["partition", "legal"]
        tracker = VulnsTracker(services)

        assert len(tracker.services) == 2
        assert "partition" in tracker.services
        assert "legal" in tracker.services

        # Check initial state
        for service in services:
            assert tracker.services[service]["status"] == "pending"
            assert tracker.services[service]["critical"] == 0
            assert tracker.services[service]["high"] == 0
            assert tracker.services[service]["medium"] == 0
            assert tracker.services[service]["dependencies"] == 0
            assert tracker.services[service]["report_id"] == ""
            assert tracker.services[service]["icon"] == "⏸"

    def test_update_basic_status(self):
        """Test updating service status."""
        tracker = VulnsTracker(["partition"])
        tracker.update("partition", "analyzing", "Analyzing dependencies")

        assert tracker.services["partition"]["status"] == "analyzing"
        assert tracker.services["partition"]["details"] == "Analyzing dependencies"
        assert tracker.services["partition"]["icon"] == "▶"

    def test_update_with_vulnerability_counts(self):
        """Test updating with vulnerability counts."""
        tracker = VulnsTracker(["partition"])
        tracker.update(
            "partition",
            "complete",
            "Analysis complete",
            critical=3,
            high=5,
            medium=12,
        )

        assert tracker.services["partition"]["critical"] == 3
        assert tracker.services["partition"]["high"] == 5
        assert tracker.services["partition"]["medium"] == 12

    def test_update_with_dependencies(self):
        """Test updating with dependency count."""
        tracker = VulnsTracker(["partition"])
        tracker.update(
            "partition",
            "scanning",
            "Scanning vulnerabilities",
            dependencies=87,
        )

        assert tracker.services["partition"]["dependencies"] == 87

    def test_update_with_report_id(self):
        """Test updating with report ID."""
        tracker = VulnsTracker(["partition"])
        tracker.update(
            "partition",
            "complete",
            "Report generated",
            report_id="partition-triage-2025-10-14",
        )

        assert tracker.services["partition"]["report_id"] == "partition-triage-2025-10-14"

    def test_get_summary(self):
        """Test getting summary of all vulnerability counts."""
        tracker = VulnsTracker(["partition", "legal", "storage"])
        tracker.update("partition", "complete", "Done", critical=3, high=5, medium=12)
        tracker.update("legal", "complete", "Done", critical=0, high=2, medium=8)
        tracker.update("storage", "error", "Failed")

        summary = tracker.get_summary()

        assert summary["total_services"] == 3
        assert summary["completed_services"] == 2
        assert summary["error_services"] == 1
        assert summary["critical"] == 3
        assert summary["high"] == 7
        assert summary["medium"] == 20

    def test_get_table(self):
        """Test generating Rich table."""
        tracker = VulnsTracker(["partition", "legal"])
        tracker.update("partition", "complete", "Analysis complete", critical=3, high=5, medium=12)
        tracker.update("legal", "scanning", "Scanning for vulnerabilities")

        table = tracker.get_table()

        assert table.title == "[italic]Service Status[/italic]"
        assert len(table.columns) == 5  # Service, Status, Critical, High, Medium

    def test_status_icons(self):
        """Test that different statuses have correct icons."""
        tracker = VulnsTracker(["partition"])

        status_icon_map = {
            "pending": "⏸",
            "analyzing": "▶",
            "scanning": "▶",
            "reporting": "▶",
            "complete": "✓",
            "success": "✓",
            "error": "✗",
        }

        for status, expected_icon in status_icon_map.items():
            tracker.update("partition", status, f"Testing {status}")
            assert tracker.services["partition"]["icon"] == expected_icon


class TestVulnsRunner:
    """Tests for VulnsRunner class."""

    @pytest.fixture
    def mock_prompt_file(self, tmp_path):
        """Create a mock prompt file."""
        prompt_file = tmp_path / "triage.md"
        prompt_file.write_text(
            "Triage prompt template\n{{ORGANIZATION}}\nARGUMENTS:\nSERVICES: {{services}}"
        )
        return prompt_file

    @pytest.fixture
    def mock_agent(self):
        """Create a mock agent."""
        agent = Mock()
        agent.agent = Mock()
        agent.agent.get_new_thread = Mock(return_value=Mock())
        agent.agent.run = AsyncMock(
            return_value="partition: Analysis complete - 3 critical, 5 high, 12 medium vulnerabilities"
        )
        return agent

    def test_initialization(self, mock_prompt_file, mock_agent):
        """Test VulnsRunner initialization."""
        services = ["partition", "legal"]
        runner = VulnsRunner(
            mock_prompt_file,
            services,
            mock_agent,
            create_issue=False,
            severity_filter=["critical", "high"],
        )

        assert runner.services == services
        assert runner.agent == mock_agent
        assert runner.create_issue is False
        assert runner.severity_filter == ["critical", "high"]
        assert isinstance(runner.tracker, VulnsTracker)
        # log_file may be None if OSDU_AGENT_LOG_DIRECTORY (or COPILOT_LOG_DIRECTORY) is not set
        if runner.log_file is not None:
            assert runner.log_file.name.startswith("vulns_")

    def test_initialization_with_defaults(self, mock_prompt_file, mock_agent):
        """Test VulnsRunner initialization with defaults."""
        runner = VulnsRunner(
            mock_prompt_file,
            ["partition"],
            mock_agent,
        )

        assert runner.create_issue is False
        assert runner.severity_filter is None  # None = all severities
        assert runner.providers == ["azure"]  # Default provider

    def test_load_prompt(self, mock_prompt_file, mock_agent):
        """Test prompt loading and augmentation."""
        with patch("agent.copilot.runners.vulns_runner.config") as mock_config:
            mock_config.organization = "test-org"

            runner = VulnsRunner(
                mock_prompt_file,
                ["partition"],
                mock_agent,
                create_issue=True,
                severity_filter=["critical", "high"],
            )
            prompt = runner.load_prompt()

            assert "test-org" in prompt
            assert "SERVICES: partition" in prompt
            assert "SEVERITY_FILTER: critical,high" in prompt
            assert "CREATE_ISSUE: True" in prompt

    def test_parse_agent_response_with_counts(self, mock_prompt_file, mock_agent):
        """Test parsing agent response with vulnerability counts."""
        runner = VulnsRunner(mock_prompt_file, ["partition"], mock_agent)

        # Use the expected format: Critical: X, High: Y, Medium: Z
        response = "partition: Analysis complete - Critical: 3, High: 5, Medium: 12 vulnerabilities"
        runner.parse_agent_response("partition", response)

        assert runner.tracker.services["partition"]["critical"] == 3
        assert runner.tracker.services["partition"]["high"] == 5
        assert runner.tracker.services["partition"]["medium"] == 12

    def test_parse_agent_response_with_dependencies(self, mock_prompt_file, mock_agent):
        """Test parsing agent response with dependency count."""
        runner = VulnsRunner(mock_prompt_file, ["partition"], mock_agent)

        response = "Scanned 87 dependencies for partition service"
        runner.parse_agent_response("partition", response)

        assert runner.tracker.services["partition"]["dependencies"] == 87

    def test_parse_agent_response_with_report_id(self, mock_prompt_file, mock_agent):
        """Test parsing agent response with report ID."""
        runner = VulnsRunner(mock_prompt_file, ["partition"], mock_agent)

        response = "Report-ID: partition-triage-2025-10-14"
        runner.parse_agent_response("partition", response)

        assert runner.tracker.services["partition"]["report_id"] == "partition-triage-2025-10-14"

    def test_parse_agent_response_no_vulnerabilities(self, mock_prompt_file, mock_agent):
        """Test parsing agent response with no vulnerabilities."""
        runner = VulnsRunner(mock_prompt_file, ["partition"], mock_agent)

        response = "Analysis complete - 0 critical, 0 high, 0 medium vulnerabilities"
        runner.parse_agent_response("partition", response)

        assert runner.tracker.services["partition"]["critical"] == 0
        assert runner.tracker.services["partition"]["high"] == 0
        assert runner.tracker.services["partition"]["medium"] == 0
        # Status should be "complete" when vulnerabilities are found (even if 0)
        assert runner.tracker.services["partition"]["status"] in ["complete", "success"]

    def test_get_results_panel(self, mock_prompt_file, mock_agent):
        """Test results panel generation."""
        runner = VulnsRunner(mock_prompt_file, ["partition", "legal"], mock_agent)

        # Set up some results
        runner.tracker.update(
            "partition", "complete", "Analysis complete", critical=3, high=5, medium=12
        )
        runner.tracker.update(
            "legal", "complete", "Analysis complete", critical=0, high=2, medium=8
        )

        panel = runner.get_results_panel(0)

        # Panel should be security assessment panel
        assert panel.title == "Security Assessment"
        # With 3 critical total, border should be red
        assert panel.border_style == "red"

    def test_get_results_panel_high_only(self, mock_prompt_file, mock_agent):
        """Test results panel with only high severity vulns."""
        runner = VulnsRunner(mock_prompt_file, ["partition"], mock_agent)

        runner.tracker.update(
            "partition", "complete", "Analysis complete", critical=0, high=5, medium=12
        )

        panel = runner.get_results_panel(0)

        # Panel should be security assessment panel
        assert panel.title == "Security Assessment"
        # With no critical but 5 high (< 20), border should be blue
        assert panel.border_style == "blue"

    def test_get_results_panel_clean(self, mock_prompt_file, mock_agent):
        """Test results panel with no vulnerabilities."""
        runner = VulnsRunner(mock_prompt_file, ["partition"], mock_agent)

        runner.tracker.update(
            "partition", "complete", "Analysis complete", critical=0, high=0, medium=0
        )

        panel = runner.get_results_panel(0)

        # Panel should be security assessment panel
        assert panel.title == "Security Assessment"
        # With no vulnerabilities, grade should be A, green border
        assert panel.border_style == "green"

    def test_log_file_naming(self, mock_prompt_file, mock_agent):
        """Test log file naming uses timestamp only (no service names)."""
        import re

        # Single service
        runner1 = VulnsRunner(mock_prompt_file, ["partition"], mock_agent)
        # log_file may be None if OSDU_AGENT_LOG_DIRECTORY (or COPILOT_LOG_DIRECTORY) is not set
        if runner1.log_file is not None:
            log_name = str(runner1.log_file)
            assert "vulns_" in log_name
            assert re.search(r"vulns_\d{8}_\d{6}\.log$", log_name)
            assert "partition" not in log_name

        # Multiple services - still no service names in filename
        runner2 = VulnsRunner(mock_prompt_file, ["partition", "legal", "schema"], mock_agent)
        if runner2.log_file is not None:
            log_name = str(runner2.log_file)
            assert "vulns_" in log_name
            assert re.search(r"vulns_\d{8}_\d{6}\.log$", log_name)
            assert "partition" not in log_name
            assert "legal" not in log_name

        # Many services - still no service names in filename
        runner3 = VulnsRunner(
            mock_prompt_file,
            ["partition", "legal", "schema", "file", "storage"],
            mock_agent,
        )
        if runner3.log_file is not None:
            log_name = str(runner3.log_file)
            assert "vulns_" in log_name
            assert re.search(r"vulns_\d{8}_\d{6}\.log$", log_name)

    def test_show_config(self, mock_prompt_file, mock_agent):
        """Test configuration display."""
        runner = VulnsRunner(
            mock_prompt_file,
            ["partition"],
            mock_agent,
            create_issue=True,
            severity_filter=["critical", "high"],
        )

        # Should not raise error - it actually prints to console
        runner.show_config()
        # Just verify it doesn't crash

    @pytest.mark.asyncio
    async def test_run_vulns_for_service_success(self, mock_prompt_file, mock_agent):
        """Test running triage for a single service."""
        runner = VulnsRunner(mock_prompt_file, ["partition"], mock_agent)

        # Mock agent response using the expected format (Critical: X, High: Y, Medium: Z)
        mock_agent.agent.run.return_value = (
            "partition: Analysis complete - Critical: 3, High: 5, Medium: 12 vulnerabilities found"
        )

        # Mock layout and live objects
        mock_layout = Mock()
        mock_layout.__getitem__ = Mock(return_value=Mock())
        mock_live = Mock()

        response = await runner.run_vulns_for_service("partition", mock_layout, mock_live)

        assert "Critical: 3" in response
        # The parse_agent_response method is called inside run_vulns_for_service
        # and should have extracted the vulnerability counts
        assert runner.tracker.services["partition"]["critical"] == 3
        assert runner.tracker.services["partition"]["high"] == 5
        assert runner.tracker.services["partition"]["medium"] == 12
        mock_agent.agent.run.assert_called_once()

    @pytest.mark.asyncio
    async def test_run_vulns_for_service_error(self, mock_prompt_file, mock_agent):
        """Test handling errors during triage."""
        runner = VulnsRunner(mock_prompt_file, ["partition"], mock_agent)

        # Mock agent error
        mock_agent.agent.run.side_effect = Exception("MCP connection failed")

        # Mock layout and live objects
        mock_layout = Mock()
        mock_layout.__getitem__ = Mock(return_value=Mock())
        mock_live = Mock()

        response = await runner.run_vulns_for_service("partition", mock_layout, mock_live)

        assert "Error analyzing partition" in response
        assert runner.tracker.services["partition"]["status"] == "error"

    def test_extract_cve_details_with_package_header(self, mock_prompt_file, mock_agent):
        """Ensure CVE details parser handles package names after em dash."""
        runner = VulnsRunner(mock_prompt_file, ["partition"], mock_agent)

        response = """
1) CVE-2022-22965 — org.springframework:spring-beans (installed: 5.2.7.RELEASE)
   - Severity: Critical
   - Affected package: org.springframework:spring-beans
   - Installed version (example location): 5.2.7.RELEASE (partition/pom.xml)
   - Scanner recommendation: upgrade to 5.2.20.RELEASE or 5.3.18
   - Reference: https://nvd.nist.gov/vuln/detail/CVE-2022-22965

2) CVE-2025-55163 — io.netty:netty-codec-http2 (installed: 4.1.99.Final)
   - Severity: High
   - Affected artifact: io.netty:netty-codec-http2
   - Installed versions found: 4.1.99.Final, 4.1.90.Final
   - Fix / recommended version: 4.1.124.Final
   - Reference: https://nvd.nist.gov/vuln/detail/CVE-2025-55163
"""

        cves = runner._extract_cve_details(response)

        assert len(cves) == 2
        assert cves[0]["cve_id"] == "CVE-2022-22965"
        assert cves[0]["severity"] == "Critical"
        assert cves[0]["package"] == "org.springframework:spring-beans"
        assert cves[1]["cve_id"] == "CVE-2025-55163"
        assert cves[1]["severity"] == "High"
        assert cves[1]["package"] == "io.netty:netty-codec-http2"
