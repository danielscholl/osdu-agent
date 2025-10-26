"""Tests for DirectTestRunner class."""

import xml.etree.ElementTree as ET
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

import pytest

from agent.copilot.runners.direct_test_runner import DirectTestRunner
from agent.copilot.trackers import TestTracker


class TestDirectTestRunner:
    """Tests for DirectTestRunner class."""

    def test_initialization(self):
        """Test DirectTestRunner initialization."""
        services = ["partition", "legal"]
        runner = DirectTestRunner(services, provider="azure")

        assert runner.services == services
        assert runner.provider == "azure"
        assert isinstance(runner.tracker, TestTracker)
        assert runner.profiles == ["azure"]
        assert runner.current_module is None

    def test_initialization_with_default_provider(self):
        """Test initialization with default provider."""
        runner = DirectTestRunner(["partition"])

        assert runner.provider == "core,azure"
        assert runner.profiles == ["core", "azure"]

    def test_parse_provider_to_profiles_single(self):
        """Test parsing single provider."""
        runner = DirectTestRunner(["partition"], provider="azure")

        assert runner.profiles == ["azure"]

    def test_parse_provider_to_profiles_multiple(self):
        """Test parsing multiple comma-separated providers."""
        runner = DirectTestRunner(["partition"], provider="core,azure,aws")

        assert runner.profiles == ["core", "azure", "aws"]

    def test_parse_provider_to_profiles_all(self):
        """Test parsing 'all' provider."""
        runner = DirectTestRunner(["partition"], provider="all")

        assert runner.profiles == ["core", "core-plus", "azure", "aws", "gc", "ibm"]

    def test_parse_provider_to_profiles_with_spaces(self):
        """Test parsing providers with spaces."""
        runner = DirectTestRunner(["partition"], provider=" azure , aws ")

        assert runner.profiles == ["azure", "aws"]

    def test_extract_profile_from_module_azure(self):
        """Test extracting azure profile from module name."""
        runner = DirectTestRunner(["partition"])

        profile = runner._extract_profile_from_module("partition-azure")
        assert profile == "azure"

        profile = runner._extract_profile_from_module("os-partition-azure")
        assert profile == "azure"

    def test_extract_profile_from_module_aws(self):
        """Test extracting aws profile from module name."""
        runner = DirectTestRunner(["partition"])

        profile = runner._extract_profile_from_module("partition-aws")
        assert profile == "aws"

    def test_extract_profile_from_module_core(self):
        """Test extracting core profile from module name."""
        runner = DirectTestRunner(["partition"])

        profile = runner._extract_profile_from_module("partition-core")
        assert profile == "core"

        profile = runner._extract_profile_from_module("os-core")
        assert profile == "core"

    def test_extract_profile_from_module_core_plus(self):
        """Test extracting core-plus profile from module name."""
        runner = DirectTestRunner(["partition"])

        profile = runner._extract_profile_from_module("partition-core-plus")
        assert profile == "core-plus"

        profile = runner._extract_profile_from_module("partition-coreplus")
        assert profile == "core-plus"

    def test_extract_profile_from_module_gc(self):
        """Test extracting gc/gcp profile from module name."""
        runner = DirectTestRunner(["partition"])

        profile = runner._extract_profile_from_module("partition-gc")
        assert profile == "gc"

        profile = runner._extract_profile_from_module("partition-gcp")
        assert profile == "gc"

    def test_extract_profile_from_module_ibm(self):
        """Test extracting ibm profile from module name."""
        runner = DirectTestRunner(["partition"])

        profile = runner._extract_profile_from_module("partition-ibm")
        assert profile == "ibm"

    def test_extract_profile_from_module_none(self):
        """Test extracting profile from non-provider module."""
        runner = DirectTestRunner(["partition"])

        profile = runner._extract_profile_from_module("partition-testing")
        assert profile is None

    def test_parse_maven_output_building_module(self):
        """Test parsing Maven 'Building' line."""
        runner = DirectTestRunner(["partition"])

        runner._parse_maven_output("partition", "[INFO] Building partition-azure 1.0.0")
        assert runner.current_module == "partition-azure"

        runner._parse_maven_output("partition", "[INFO] Building os-partition-core 2.0.0")
        assert runner.current_module == "os-partition-core"

    def test_count_tests_from_surefire_empty(self, tmp_path):
        """Test counting tests when no surefire reports exist."""
        runner = DirectTestRunner(["partition"])

        tests_run, tests_failed = runner._count_tests_from_surefire("partition", tmp_path)

        assert tests_run == 0
        assert tests_failed == 0

    def test_count_tests_from_surefire_single_file(self, tmp_path):
        """Test counting tests from single surefire XML report."""
        runner = DirectTestRunner(["partition"])

        # Create mock surefire report
        surefire_dir = tmp_path / "target" / "surefire-reports"
        surefire_dir.mkdir(parents=True)

        xml_content = """<?xml version="1.0" encoding="UTF-8"?>
<testsuite tests="42" failures="2" errors="1" skipped="3" name="TestSuite">
</testsuite>"""
        (surefire_dir / "TEST-TestSuite.xml").write_text(xml_content)

        tests_run, tests_failed = runner._count_tests_from_surefire("partition", tmp_path)

        assert tests_run == 42
        assert tests_failed == 3  # failures + errors

    def test_count_tests_from_surefire_multiple_files(self, tmp_path):
        """Test counting tests from multiple surefire XML reports."""
        runner = DirectTestRunner(["partition"])

        surefire_dir = tmp_path / "target" / "surefire-reports"
        surefire_dir.mkdir(parents=True)

        # Create multiple test reports
        xml1 = """<?xml version="1.0" encoding="UTF-8"?>
<testsuite tests="20" failures="1" errors="0" skipped="2" name="Suite1">
</testsuite>"""
        (surefire_dir / "TEST-Suite1.xml").write_text(xml1)

        xml2 = """<?xml version="1.0" encoding="UTF-8"?>
<testsuite tests="30" failures="0" errors="2" skipped="1" name="Suite2">
</testsuite>"""
        (surefire_dir / "TEST-Suite2.xml").write_text(xml2)

        tests_run, tests_failed = runner._count_tests_from_surefire("partition", tmp_path)

        assert tests_run == 50  # 20 + 30
        assert tests_failed == 3  # 1 + 2

    def test_count_tests_from_surefire_nested_modules(self, tmp_path):
        """Test counting tests from nested provider modules."""
        runner = DirectTestRunner(["partition"], provider="azure")

        # Create module structure
        provider_module = tmp_path / "provider" / "azure"
        surefire_dir = provider_module / "target" / "surefire-reports"
        surefire_dir.mkdir(parents=True)

        xml_content = """<?xml version="1.0" encoding="UTF-8"?>
<testsuite tests="15" failures="1" errors="0" skipped="0" name="AzureTests">
</testsuite>"""
        (surefire_dir / "TEST-AzureTests.xml").write_text(xml_content)

        tests_run, tests_failed = runner._count_tests_from_surefire("partition", tmp_path)

        assert tests_run == 15
        assert tests_failed == 1

    def test_show_config_single_profile(self):
        """Test config display with single profile."""
        runner = DirectTestRunner(["partition", "legal"], provider="azure")

        with patch("agent.copilot.runners.direct_test_runner.console.print") as mock_print:
            runner.show_config()

            # Verify console.print was called
            assert mock_print.call_count >= 1

    def test_show_config_multiple_profiles(self):
        """Test config display with multiple profiles."""
        runner = DirectTestRunner(["partition"], provider="core,azure")

        with patch("agent.copilot.runners.direct_test_runner.console.print") as mock_print:
            runner.show_config()

            # Verify console.print was called
            assert mock_print.call_count >= 1

    @pytest.mark.asyncio
    async def test_run_maven_command_success(self, tmp_path):
        """Test successful Maven command execution."""
        runner = DirectTestRunner(["partition"])

        mock_process = AsyncMock()
        mock_process.stdout = AsyncMock()
        mock_process.stdout.__aiter__.return_value = [
            b"[INFO] Building partition\n",
            b"[INFO] BUILD SUCCESS\n",
        ]
        mock_process.wait = AsyncMock(return_value=0)
        mock_process.returncode = 0

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            return_code, output = await runner._run_maven_command(
                ["mvn", "test"], tmp_path, "partition", "test"
            )

        assert return_code == 0
        assert "[INFO] Building partition" in output
        assert "[INFO] BUILD SUCCESS" in output

    @pytest.mark.asyncio
    async def test_run_maven_command_failure(self, tmp_path):
        """Test failed Maven command execution."""
        runner = DirectTestRunner(["partition"])

        mock_process = AsyncMock()
        mock_process.stdout = AsyncMock()
        mock_process.stdout.__aiter__.return_value = [
            b"[ERROR] Build failed\n",
        ]
        mock_process.wait = AsyncMock(return_value=1)
        mock_process.returncode = 1

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            return_code, output = await runner._run_maven_command(
                ["mvn", "test"], tmp_path, "partition", "test"
            )

        assert return_code == 1
        assert "[ERROR] Build failed" in output

    @pytest.mark.asyncio
    async def test_run_maven_command_exception(self, tmp_path):
        """Test Maven command exception handling."""
        runner = DirectTestRunner(["partition"])

        with patch(
            "asyncio.create_subprocess_exec", side_effect=Exception("Test exception")
        ):
            return_code, output = await runner._run_maven_command(
                ["mvn", "test"], tmp_path, "partition", "test"
            )

        assert return_code == -1
        assert "Test exception" in output

    def test_map_profile_to_modules_direct(self, tmp_path):
        """Test mapping profile to direct module directory."""
        runner = DirectTestRunner(["partition"], provider="azure")

        # Create direct module: partition-azure/
        direct_module = tmp_path / "partition-azure"
        direct_module.mkdir()

        modules = runner._map_profile_to_modules("partition", tmp_path, "azure")

        assert len(modules) == 1
        assert modules[0] == direct_module

    def test_map_profile_to_modules_provider_dir(self, tmp_path):
        """Test mapping profile to provider subdirectory."""
        runner = DirectTestRunner(["partition"], provider="azure")

        # Create provider structure: provider/azure/
        provider_dir = tmp_path / "provider" / "azure"
        provider_dir.mkdir(parents=True)

        modules = runner._map_profile_to_modules("partition", tmp_path, "azure")

        assert len(modules) >= 1
        assert provider_dir in modules

    def test_map_profile_to_modules_providers_dir(self, tmp_path):
        """Test mapping profile to providers (plural) subdirectory."""
        runner = DirectTestRunner(["partition"], provider="azure")

        # Create providers structure: providers/azure/
        providers_dir = tmp_path / "providers" / "azure"
        providers_dir.mkdir(parents=True)

        modules = runner._map_profile_to_modules("partition", tmp_path, "azure")

        assert len(modules) >= 1
        assert providers_dir in modules

    def test_tracker_integration(self):
        """Test that DirectTestRunner properly integrates with TestTracker."""
        services = ["partition", "legal"]
        runner = DirectTestRunner(services, provider="azure")

        # Verify tracker was created with correct services
        assert isinstance(runner.tracker, TestTracker)
        assert "partition" in runner.tracker.services
        assert "legal" in runner.tracker.services

    def test_profiles_stored_in_tracker(self):
        """Test that profiles are stored in tracker for multi-profile runs."""
        runner = DirectTestRunner(["partition"], provider="core,azure,aws")

        # Multi-profile run should store profiles in tracker
        assert runner.tracker.profiles == ["core", "azure", "aws"]

    def test_single_profile_not_stored_in_tracker(self):
        """Test that single profile is not stored in tracker."""
        runner = DirectTestRunner(["partition"], provider="azure")

        # Single profile run should not store profiles in tracker
        assert runner.tracker.profiles == []
