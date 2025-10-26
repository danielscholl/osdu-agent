"""Integration tests for GitLab status command."""

from agent.copilot import parse_services


def test_parse_services_all():
    """Test parsing 'all' projects."""
    projects = parse_services("all")
    assert len(projects) > 0
    assert "partition" in projects


def test_parse_services_single():
    """Test parsing single project."""
    projects = parse_services("partition")
    assert projects == ["partition"]


def test_parse_services_multiple():
    """Test parsing multiple projects."""
    projects = parse_services("partition,legal,entitlements")
    assert len(projects) == 3
    assert "partition" in projects
    assert "legal" in projects
    assert "entitlements" in projects


def test_status_runner_with_providers(tmp_path):
    """Test StatusRunner can be initialized with providers."""
    from agent.copilot.runners import StatusRunner

    # Create a mock prompt file
    prompt_file = tmp_path / "status-glab.md"
    prompt_file.write_text("Test prompt for {{ORGANIZATION}}")

    # StatusRunner should accept providers argument (explicit parameter passing)
    runner = StatusRunner(prompt_file, ["partition"], providers=["azure", "core"])
    assert runner.services == ["partition"]
    assert runner.providers == ["azure", "core"]
    assert runner.show_actions is False  # Verify default value


def test_status_runner_without_providers(tmp_path):
    """Test StatusRunner works without providers (GitHub mode)."""
    from agent.copilot.runners import StatusRunner

    prompt_file = tmp_path / "status.md"
    prompt_file.write_text("Test prompt for {{ORGANIZATION}}")

    # StatusRunner should work without providers
    runner = StatusRunner(prompt_file, ["partition"])
    assert runner.services == ["partition"]
    assert runner.providers is None

    # Verify prompt doesn't include providers
    prompt = runner.load_prompt()
    assert "PROVIDERS:" not in prompt
