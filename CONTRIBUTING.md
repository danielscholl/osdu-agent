# Contributing to OSDU Agent

Thank you for your interest in contributing to the OSDU Agent!

## Development Setup

### Prerequisites

- Python 3.12 or higher
- [uv](https://github.com/astral-sh/uv) package manager
- Git
- GitHub CLI (`gh`) for testing GitHub integrations (optional)
- GitLab CLI (`glab`) for testing GitLab integrations (optional)

### Initial Setup

1. Clone the repository:
   ```bash
   git clone https://github.com/danielscholl-osdu/osdu-agent.git
   cd osdu-agent
   ```

2. Install dependencies:
   ```bash
   uv sync --frozen
   uv pip install -e .[dev]
   ```

3. Verify installation:
   ```bash
   uv run osdu --help
   ```

### Environment Configuration

Create a `.env` file from the example:

```bash
cp .env.example .env
```

Configure required environment variables:

```bash
# Required
GITHUB_SPI_ORGANIZATION=your-github-org
OSDU_AGENT_REPOSITORIES=partition,legal,entitlements

# Azure OpenAI (for AI features)
AZURE_OPENAI_ENDPOINT=https://your-endpoint.openai.azure.com/
AZURE_OPENAI_DEPLOYMENT=your-deployment-name

# Optional: GitLab integration
GITLAB_TOKEN=your-gitlab-token
```

## Code Quality

### Quality Checks

Before submitting a pull request, ensure all quality checks pass:

```bash
# Auto-fix formatting and linting
uv run black src/ tests/
uv run ruff check --fix src/ tests/

# Verify checks pass
uv run black --check src/
uv run ruff check src/
uv run mypy src/
uv run pytest --cov=src/agent --cov-fail-under=60
```

### CI Pipeline

Our GitHub Actions CI runs the following checks:

1. **Black**: Code formatting (strict)
2. **Ruff**: Linting and code quality
3. **MyPy**: Type checking (excluded for `tests/`, `repos/`, `copilot/`, `workflows/`, `display/`, `mcp/`)
4. **PyTest**: Test suite with 60% minimum coverage

All checks must pass for PRs to be merged.

### Type Checking

We use type checking with MyPy for core modules:

```toml
# pyproject.toml
[tool.mypy]
python_version = "3.12"
disallow_untyped_defs = false
check_untyped_defs = true
exclude = ["^repos/", "^tests/", "^src/agent/copilot/", "^src/agent/workflows/", "^src/agent/display/", "^src/agent/mcp/"]
```

**Guidelines:**
- Add type hints to all function parameters and return types
- Use `Optional[T]` for nullable parameters (no implicit optionals)
- Use `# type: ignore[error-code]` sparingly for third-party library issues
- Import types with `from typing import TYPE_CHECKING` to avoid circular imports

### Testing

#### Run All Tests

```bash
# Full test suite
uv run pytest

# With verbose output
uv run pytest -v

# Stop on first failure
uv run pytest -x
```

#### Run Specific Tests

```bash
# Test a specific file
uv run pytest tests/test_agent.py

# Test a specific class
uv run pytest tests/test_github_tools.py::TestIssueTools

# Test a specific function
uv run pytest tests/test_github_tools.py::test_list_issues_success

# Run with verbose traceback
uv run pytest tests/test_agent.py -vv
```

#### Coverage

```bash
# Run with coverage report
uv run pytest --cov=src/agent --cov-report=term-missing --cov-fail-under=60

# Generate HTML coverage report
uv run pytest --cov=src/agent --cov-report=html
open htmlcov/index.html
```

#### Test Organization

Tests are organized by module:
- `tests/test_agent.py` - Core agent functionality
- `tests/test_github_tools.py` - GitHub API integrations
- `tests/test_gitlab_tools.py` - GitLab API integrations
- `tests/test_copilot.py` - Copilot workflow runners
- `tests/test_direct_test_runner.py` - Maven test execution
- `tests/test_workflows.py` - Workflow orchestration

## Commit Guidelines

This project uses [Conventional Commits](https://www.conventionalcommits.org/) with [Release Please](https://github.com/googleapis/release-please) for automated versioning and changelog generation.

### Commit Format

```
<type>(<scope>): <description>

[optional body]

[optional footer]
```

### Commit Types

- `feat`: New feature (triggers minor version bump)
- `fix`: Bug fix (triggers patch version bump)
- `docs`: Documentation changes
- `style`: Code style changes (formatting, etc.)
- `refactor`: Code refactoring
- `test`: Test additions or modifications
- `chore`: Maintenance tasks
- `ci`: CI/CD changes
- `perf`: Performance improvements

### Breaking Changes

For breaking changes, add `!` after type or add `BREAKING CHANGE:` in footer:

```
feat!: redesign CLI interface

BREAKING CHANGE: The --service flag is now required for all commands.
Removed deprecated --repo flag.
```

### Examples

```bash
feat(github): add code scanning alert integration
fix(cli): handle missing .env file gracefully
docs(readme): update installation instructions
test(gitlab): add merge request approval tests
chore(deps): update agent-framework to 1.0.0b251007
```

## Architecture

The agent follows a modular architecture:

### Core Components

#### Agent Layer (`src/agent/`)
- **agent.py**: Main Agent class with Azure OpenAI integration
- **config.py**: Configuration management via environment variables
- **cli.py**: Command-line interface and interactive chat mode

#### Platform Integration (`src/agent/github/`, `src/agent/gitlab/`)
- Specialized tool classes organized by domain:
  - Issues, Pull/Merge Requests, Workflows/Pipelines
  - Code scanning, Variables
- Direct API clients for high-performance data fetching
- Fork clients for repository initialization

#### Copilot Workflows (`src/agent/copilot/`)
- **runners/**: Workflow execution engines
  - `CopilotRunner`: Fork and clone repositories
  - `StatusRunner`: Check repository status (GitHub/GitLab)
  - `DirectTestRunner`: Execute Maven tests
  - `VulnsRunner`: Security vulnerability scanning
  - `DependsRunner`: Dependency update analysis
- **trackers/**: Real-time status tracking for concurrent operations
- **prompts/**: System prompts for OSDU AI assistant

#### File System & Git (`src/agent/filesystem/`, `src/agent/git/`)
- Hybrid file operations (local + MCP)
- Git repository management
- POM file parsing for Maven projects

#### MCP Integration (`src/agent/mcp/`)
- Maven MCP Server integration
- Tool argument normalization
- Server lifecycle management

#### Display & Observability
- **display/**: Rich console UI with execution trees
- **observability.py**: OpenTelemetry metrics and tracing
- **middleware.py**: Logging and context management

### Workflow Design

The agent supports both:

1. **Interactive Chat Mode**: Natural language queries with slash commands
2. **CLI Mode**: Direct command execution (`osdu status --service partition`)

Slash commands are implemented as workflows that can be called from both modes.

## Development Workflows

### Adding a New GitHub Tool

1. Create tool method in appropriate class (`src/agent/github/issues.py`, etc.)
2. Add type hints to all parameters
3. Add docstring with parameter descriptions
4. Add unit tests in `tests/test_github_tools.py`
5. Expose via `GitHubTools` wrapper in `src/agent/github/__init__.py`

### Adding a New Slash Command

1. Add command handler in `src/agent/cli.py::handle_slash_command()`
2. Create workflow function in `src/agent/workflows/`
3. Add command to completer in `_create_slash_command_completer()`
4. Add tests in `tests/test_workflows.py`
5. Update help text in CLI

### Adding a New Copilot Runner

1. Create runner class in `src/agent/copilot/runners/` extending `BaseRunner`
2. Create tracker class in `src/agent/copilot/trackers/` extending `BaseTracker`
3. Implement required abstract methods
4. Add type hints (must pass strict MyPy)
5. Add comprehensive tests
6. Register in `src/agent/copilot/__init__.py`

## Pull Request Process

1. **Create a branch** from `main`:
   ```bash
   git checkout -b feat/your-feature-name
   ```

2. **Make your changes** following code style guidelines

3. **Run quality checks**:
   ```bash
   uv run black src/ tests/
   uv run ruff check --fix src/ tests/
   uv run mypy src/
   uv run pytest
   ```

4. **Commit with conventional commit format**:
   ```bash
   git add .
   git commit -m "feat(scope): add new feature"
   ```

5. **Push and create PR**:
   ```bash
   git push -u origin feat/your-feature-name
   gh pr create --title "feat: add new feature" --body "Description of changes"
   ```

6. **Address review comments** and ensure CI passes

### Code Review Checklist

Reviewers will verify:

- [ ] All CI checks pass (Black, Ruff, MyPy, PyTest)
- [ ] Test coverage ≥ 60%
- [ ] Type hints on all public functions
- [ ] Docstrings for public APIs
- [ ] Conventional commit format
- [ ] No breaking changes without `BREAKING CHANGE:` footer
- [ ] Documentation updated if needed

## Project-Specific Guidelines

### OSDU AI Assistant

When modifying the system prompt (`src/agent/copilot/prompts/system.md`):
- Keep instructions concise and actionable
- Use markdown formatting
- Version is auto-updated by Release Please
- Test with multiple service scenarios

### GitHub Copilot Integration

The project supports GitHub Copilot Workspace:
- `.github/workflows/copilot-assign.yml`: Auto-assigns Copilot to labeled issues
- `.github/workflows/copilot-setup-steps.yml`: Environment setup for Copilot

When creating issues for Copilot:
- Use `copilot` label
- Keep issue descriptions clear and actionable
- Follow the issue creation guidelines in `system.md`

### Error Handling

- Use specific exception types
- Provide actionable error messages
- Log errors with context using `logger.error()`
- Return formatted error strings to users (don't raise in tool methods)

### Performance

- Use `asyncio.gather()` for concurrent operations
- Limit concurrent tasks with `Semaphore` (typically 2-3)
- Cache expensive operations (Git, API calls)
- Use direct API clients for status checks (avoid AI when possible)

## Troubleshooting

### Tests Failing

```bash
# Clear pytest cache
rm -rf .pytest_cache/
rm -rf __pycache__/

# Reinstall dependencies
uv sync --frozen
uv pip install -e .[dev]

# Run tests with verbose output
uv run pytest -xvs
```

### MyPy Errors

```bash
# Check specific file
uv run mypy src/agent/agent.py

# Ignore third-party library issues (use sparingly)
# Add: # type: ignore[error-code]
```

### Import Errors

```bash
# Reinstall in development mode
uv pip install -e .

# Verify package installed
uv run python -c "import agent; print(agent.__file__)"
```

## Getting Help

- **Issues**: Report bugs or request features via [GitHub Issues](https://github.com/danielscholl-osdu/osdu-agent/issues)
- **Discussions**: Ask questions in [GitHub Discussions](https://github.com/danielscholl-osdu/osdu-agent/discussions)
- **Security**: Report vulnerabilities privately via GitHub Security Advisories

## License

By contributing, you agree that your contributions will be licensed under the [Apache License 2.0](LICENSE).
