"""Pytest configuration and fixtures."""

from datetime import datetime
from typing import Any
from unittest.mock import Mock

import pytest

from agent.config import AgentConfig


@pytest.fixture
def test_config() -> AgentConfig:
    """Provide test configuration."""
    return AgentConfig(
        organization="test-org",
        repositories=["test-repo1", "test-repo2"],
        github_token="test_token_123",
    )


@pytest.fixture
def mock_github_issue() -> Mock:
    """Create a mock GitHub issue object."""
    issue = Mock()
    issue.number = 42
    issue.title = "Test Issue"
    issue.body = "This is a test issue body"
    issue.state = "open"

    # Create proper label mocks
    label1 = Mock()
    label1.name = "bug"
    label2 = Mock()
    label2.name = "priority:high"
    issue.labels = [label1, label2]

    # Create proper assignee mocks
    assignee1 = Mock()
    assignee1.login = "testuser"
    issue.assignees = [assignee1]

    issue.created_at = datetime(2025, 1, 6, 10, 0, 0)
    issue.updated_at = datetime(2025, 1, 6, 12, 0, 0)
    issue.html_url = "https://github.com/test-org/test-repo1/issues/42"
    issue.comments = 3

    # Create proper user mock
    user = Mock()
    user.login = "issueauthor"
    issue.user = user

    issue.pull_request = None  # Not a PR
    return issue


@pytest.fixture
def mock_github_repo(mock_github_issue: Mock) -> Mock:
    """Create a mock GitHub repository object."""
    repo = Mock()
    repo.full_name = "test-org/test-repo1"
    repo.name = "test-repo1"

    # Mock get_issues to return our mock issue
    repo.get_issues.return_value = [mock_github_issue]

    # Mock get_issue to return specific issue
    repo.get_issue.return_value = mock_github_issue

    # Mock create_issue
    repo.create_issue.return_value = mock_github_issue

    return repo


@pytest.fixture
def mock_github_client(mock_github_repo: Mock) -> Mock:
    """Create a mock GitHub client."""
    client = Mock()
    client.get_repo.return_value = mock_github_repo

    # Mock search
    client.search_issues.return_value = []

    return client


@pytest.fixture
def mock_github(monkeypatch: Any, mock_github_client: Mock) -> Mock:
    """Mock the Github class constructor."""

    def mock_github_constructor(*args: Any, **kwargs: Any) -> Mock:
        return mock_github_client

    monkeypatch.setattr("agent.github.base.Github", mock_github_constructor)
    return mock_github_client


@pytest.fixture
def mock_github_pr() -> Mock:
    """Create a mock GitHub pull request object."""
    pr = Mock()
    pr.number = 123
    pr.title = "Test Pull Request"
    pr.body = "This is a test PR body"
    pr.state = "open"
    pr.draft = False
    pr.merged = False
    pr.mergeable = True
    pr.mergeable_state = "clean"

    # Base and head refs
    base = Mock()
    base.ref = "main"
    pr.base = base

    head = Mock()
    head.ref = "feature/test"
    pr.head = head

    # Labels and assignees
    label1 = Mock()
    label1.name = "enhancement"
    pr.labels = [label1]

    assignee1 = Mock()
    assignee1.login = "testuser"
    pr.assignees = [assignee1]

    # Timestamps
    pr.created_at = datetime(2025, 1, 6, 10, 0, 0)
    pr.updated_at = datetime(2025, 1, 6, 12, 0, 0)
    pr.merged_at = None

    # URLs and counts
    pr.html_url = "https://github.com/test-org/test-repo1/pull/123"
    pr.comments = 2
    pr.review_comments = 1
    pr.commits = 3
    pr.changed_files = 5
    pr.additions = 150
    pr.deletions = 50

    # User
    user = Mock()
    user.login = "prauthor"
    pr.user = user

    # Mock methods
    pr.as_issue = Mock()
    pr.create_issue_comment = Mock()
    pr.edit = Mock()
    pr.merge = Mock()

    return pr


@pytest.fixture
def mock_github_repo_with_pr(mock_github_repo: Mock, mock_github_pr: Mock) -> Mock:
    """Enhance mock repository with PR support."""
    mock_github_repo.get_pulls.return_value = [mock_github_pr]
    mock_github_repo.get_pull.return_value = mock_github_pr
    mock_github_repo.create_pull.return_value = mock_github_pr
    return mock_github_repo


@pytest.fixture
def mock_workflow() -> Mock:
    """Create a mock GitHub workflow object."""
    workflow = Mock()
    workflow.id = 12345678
    workflow.name = "Build and Test"
    workflow.path = ".github/workflows/build.yml"
    workflow.state = "active"
    workflow.created_at = datetime(2025, 1, 1, 10, 0, 0)
    workflow.updated_at = datetime(2025, 1, 6, 10, 0, 0)
    workflow.html_url = "https://github.com/test-org/test-repo1/actions/workflows/build.yml"
    workflow.create_dispatch = Mock(return_value=True)
    workflow.get_runs = Mock()
    return workflow


@pytest.fixture
def mock_workflow_run() -> Mock:
    """Create a mock GitHub workflow run object."""
    run = Mock()
    run.id = 987654321
    run.name = "Build and Test"
    run.workflow_id = 12345678
    run.status = "completed"
    run.conclusion = "success"
    run.head_branch = "main"
    run.head_sha = "abc123def456"
    run.event = "push"
    run.created_at = datetime(2025, 1, 6, 10, 0, 0)
    run.updated_at = datetime(2025, 1, 6, 10, 5, 0)
    run.run_started_at = datetime(2025, 1, 6, 10, 0, 15)
    run.html_url = "https://github.com/test-org/test-repo1/actions/runs/987654321"

    # Actor
    actor = Mock()
    actor.login = "testuser"
    run.actor = actor

    # Mock jobs
    job1 = Mock()
    job1.name = "lint"
    job1.status = "completed"
    job1.conclusion = "success"

    job2 = Mock()
    job2.name = "test"
    job2.status = "completed"
    job2.conclusion = "success"

    jobs_paginated = Mock()
    jobs_paginated.__iter__ = Mock(return_value=iter([job1, job2]))
    jobs_paginated.totalCount = 2

    run.get_jobs = Mock(return_value=jobs_paginated)
    run.cancel = Mock(return_value=True)

    return run


@pytest.fixture
def mock_github_repo_with_workflows(
    mock_github_repo: Mock, mock_workflow: Mock, mock_workflow_run: Mock
) -> Mock:
    """Enhance mock repository with workflow support."""
    mock_github_repo.get_workflows.return_value = [mock_workflow]
    mock_github_repo.get_workflow.return_value = mock_workflow
    mock_github_repo.get_workflow_runs.return_value = [mock_workflow_run]
    mock_github_repo.get_workflow_run.return_value = mock_workflow_run
    return mock_github_repo


@pytest.fixture
def mock_code_scanning_alert() -> dict[str, Any]:
    """Create a mock code scanning alert response from GitHub API."""
    return {
        "number": 5,
        "state": "open",
        "dismissed_reason": None,
        "dismissed_comment": None,
        "dismissed_by": None,
        "dismissed_at": None,
        "created_at": "2025-01-06T10:00:00Z",
        "updated_at": "2025-01-06T12:00:00Z",
        "html_url": "https://github.com/test-org/test-repo1/security/code-scanning/5",
        "rule": {
            "id": "js/sql-injection",
            "name": "SQL Injection",
            "description": "Unsanitized user input flows into a SQL query",
            "severity": "error",
            "security_severity_level": "high",
            "tags": ["security", "external/cwe/cwe-89"],
        },
        "tool": {
            "name": "CodeQL",
            "version": "2.15.0",
        },
        "most_recent_instance": {
            "ref": "refs/heads/main",
            "state": "open",
            "commit_sha": "abc123def456789",
            "analysis_key": ".github/workflows/codeql.yml:analyze",
            "message": {
                "text": "This SQL query depends on a user-provided value.",
            },
            "location": {
                "path": "src/api/query.js",
                "start_line": 42,
                "end_line": 45,
                "start_column": 10,
                "end_column": 30,
            },
        },
    }


@pytest.fixture
def mock_code_scanning_alert_dismissed() -> dict[str, Any]:
    """Create a mock dismissed code scanning alert."""
    return {
        "number": 10,
        "state": "dismissed",
        "dismissed_reason": "false positive",
        "dismissed_comment": "This is actually safe due to input validation",
        "dismissed_by": {"login": "securityteam"},
        "dismissed_at": "2025-01-07T10:00:00Z",
        "created_at": "2025-01-05T10:00:00Z",
        "updated_at": "2025-01-07T10:00:00Z",
        "html_url": "https://github.com/test-org/test-repo1/security/code-scanning/10",
        "rule": {
            "id": "js/path-injection",
            "name": "Path Injection",
            "description": "User input flows into file path construction",
            "severity": "warning",
            "security_severity_level": "medium",
            "tags": ["security", "external/cwe/cwe-22"],
        },
        "tool": {
            "name": "CodeQL",
            "version": "2.15.0",
        },
        "most_recent_instance": {
            "ref": "refs/heads/main",
            "state": "dismissed",
            "commit_sha": "xyz789abc123",
            "analysis_key": ".github/workflows/codeql.yml:analyze",
            "message": {
                "text": "This path construction depends on untrusted data.",
            },
            "location": {
                "path": "src/utils/files.js",
                "start_line": 15,
                "end_line": 15,
                "start_column": 5,
                "end_column": 50,
            },
        },
    }


@pytest.fixture
def mock_code_scanning_alert_with_nulls() -> dict[str, Any]:
    """Create a mock code scanning alert with None values (edge case)."""
    return {
        "number": 15,
        "state": "fixed",
        "dismissed_reason": None,
        "dismissed_comment": None,
        "dismissed_by": None,
        "dismissed_at": None,
        "created_at": "2025-01-01T10:00:00Z",
        "updated_at": "2025-01-08T10:00:00Z",
        "html_url": "https://github.com/test-org/test-repo1/security/code-scanning/15",
        "rule": {
            "id": "js/unused-variable",
            "name": "Unused Variable",
            "description": None,  # Can be None
            "severity": "warning",
            "security_severity_level": None,  # Can be None!
            "tags": None,  # Can be None
        },
        "tool": {
            "name": "ESLint",
            "version": None,  # Can be None
        },
        "most_recent_instance": None,  # Can be None for fixed alerts!
    }


@pytest.fixture
def mock_github_repo_with_code_scanning(
    mock_github_repo: Mock, mock_code_scanning_alert: dict[str, Any]
) -> Mock:
    """Enhance mock repository with code scanning support."""
    # Mock the _requester for direct API calls
    mock_requester = Mock()

    # Mock list alerts endpoint
    mock_requester.requestJsonAndCheck = Mock(
        return_value=(
            {},  # headers
            [mock_code_scanning_alert],  # data
        )
    )

    mock_github_repo._requester = mock_requester
    mock_github_repo.url = "https://api.github.com/repos/test-org/test-repo1"

    return mock_github_repo


# ========== GitLab Fixtures ==========


@pytest.fixture
def gitlab_config() -> AgentConfig:
    """Provide test configuration with GitLab settings."""
    return AgentConfig(
        organization="test-org",
        repositories=["test-repo1"],
        gitlab_url="https://gitlab.example.com",
        gitlab_token="test_gitlab_token",
        gitlab_default_group="test-group",
    )


@pytest.fixture
def mock_gitlab_issue() -> Mock:
    """Create a mock GitLab issue object."""
    issue = Mock()
    issue.iid = 42
    issue.id = 142
    issue.title = "Test GitLab Issue"
    issue.description = "This is a test GitLab issue description"
    issue.state = "opened"
    issue.labels = ["bug", "priority::high"]
    issue.assignees = [{"username": "testuser"}]
    issue.author = {"username": "issueauthor"}
    issue.created_at = "2025-01-06T10:00:00Z"
    issue.updated_at = "2025-01-06T12:00:00Z"
    issue.web_url = "https://gitlab.example.com/test-group/test-project/-/issues/42"
    issue.upvotes = 5
    issue.downvotes = 0
    return issue


@pytest.fixture
def mock_gitlab_note() -> Mock:
    """Create a mock GitLab note/comment object."""
    note = Mock()
    note.id = 1
    note.body = "This is a test note"
    note.author = {"username": "noteauthor"}
    note.created_at = "2025-01-06T11:00:00Z"
    note.updated_at = "2025-01-06T11:00:00Z"
    note.system = False
    return note


@pytest.fixture
def mock_gitlab_mr() -> Mock:
    """Create a mock GitLab merge request object."""
    mr = Mock()
    mr.iid = 123
    mr.id = 223
    mr.title = "Test Merge Request"
    mr.description = "This is a test MR description"
    mr.state = "opened"
    mr.draft = False
    mr.merged_at = None
    mr.source_branch = "feature/test"
    mr.target_branch = "main"
    mr.labels = ["enhancement"]
    mr.assignees = [{"username": "testuser"}]
    mr.author = {"username": "mrauthor"}
    mr.created_at = "2025-01-06T10:00:00Z"
    mr.updated_at = "2025-01-06T12:00:00Z"
    mr.web_url = "https://gitlab.example.com/test-group/test-project/-/merge_requests/123"
    mr.merge_status = "can_be_merged"
    mr.has_conflicts = False
    mr.changes_count = "5"
    mr.upvotes = 3
    mr.downvotes = 0
    return mr


@pytest.fixture
def mock_gitlab_pipeline() -> Mock:
    """Create a mock GitLab pipeline object."""
    pipeline = Mock()
    pipeline.id = 987654
    pipeline.iid = 42
    pipeline.status = "success"
    pipeline.ref = "main"
    pipeline.sha = "abc123def456789"
    pipeline.created_at = "2025-01-06T10:00:00Z"
    pipeline.updated_at = "2025-01-06T10:05:00Z"
    pipeline.started_at = "2025-01-06T10:00:15Z"
    pipeline.finished_at = "2025-01-06T10:05:00Z"
    pipeline.duration = 285
    pipeline.web_url = "https://gitlab.example.com/test-group/test-project/-/pipelines/987654"
    pipeline.user = {"username": "testuser"}
    return pipeline


@pytest.fixture
def mock_gitlab_job() -> Mock:
    """Create a mock GitLab pipeline job object."""
    job = Mock()
    job.id = 123456
    job.name = "test-job"
    job.status = "success"
    job.stage = "test"
    job.ref = "main"
    job.created_at = "2025-01-06T10:00:00Z"
    job.started_at = "2025-01-06T10:00:30Z"
    job.finished_at = "2025-01-06T10:02:00Z"
    job.duration = 90
    job.web_url = "https://gitlab.example.com/test-group/test-project/-/jobs/123456"
    job.user = {"username": "testuser"}
    return job


@pytest.fixture
def mock_gitlab_project(
    mock_gitlab_issue: Mock, mock_gitlab_mr: Mock, mock_gitlab_pipeline: Mock
) -> Mock:
    """Create a mock GitLab project object."""
    project = Mock()
    project.id = 1
    project.name = "test-project"
    project.path_with_namespace = "test-group/test-project"

    # Mock issues manager
    project.issues = Mock()
    project.issues.list = Mock(return_value=[mock_gitlab_issue])
    project.issues.get = Mock(return_value=mock_gitlab_issue)
    project.issues.create = Mock(return_value=mock_gitlab_issue)

    # Mock merge requests manager
    project.mergerequests = Mock()
    project.mergerequests.list = Mock(return_value=[mock_gitlab_mr])
    project.mergerequests.get = Mock(return_value=mock_gitlab_mr)
    project.mergerequests.create = Mock(return_value=mock_gitlab_mr)

    # Mock pipelines manager
    project.pipelines = Mock()
    project.pipelines.list = Mock(return_value=[mock_gitlab_pipeline])
    project.pipelines.get = Mock(return_value=mock_gitlab_pipeline)
    project.pipelines.create = Mock(return_value=mock_gitlab_pipeline)

    return project


@pytest.fixture
def mock_gitlab_client(mock_gitlab_project: Mock) -> Mock:
    """Create a mock GitLab client."""
    client = Mock()

    # Mock projects manager
    client.projects = Mock()
    client.projects.get = Mock(return_value=mock_gitlab_project)

    # Mock users manager
    mock_user = Mock()
    mock_user.id = 1
    mock_user.username = "testuser"
    client.users = Mock()
    client.users.list = Mock(return_value=[mock_user])

    # Mock issues manager (for global search)
    client.issues = Mock()
    client.issues.list = Mock(return_value=[])

    # Mock auth
    client.auth = Mock()

    return client


@pytest.fixture
def mock_gitlab(monkeypatch: Any, mock_gitlab_client: Mock) -> Mock:
    """Mock the GitLab class constructor."""

    def mock_gitlab_constructor(*args: Any, **kwargs: Any) -> Mock:
        return mock_gitlab_client

    monkeypatch.setattr("agent.gitlab.base.gitlab.Gitlab", mock_gitlab_constructor)
    return mock_gitlab_client
