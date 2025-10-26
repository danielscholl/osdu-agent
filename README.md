# OSDU Agent

AI-powered GitHub & GitLab management for OSDU services. Chat with your repositories using natural language.

[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)

## Overview

OSDU Agent provides a conversational interface for managing **GitHub** and **GitLab** repositories across OSDU services. Manage Issues, Pull/Merge Requests, Workflows/Pipelines, Code Scanning, and more. With Maven MCP integration, gain powerful **dependency management** and **security scanning** capabilities. Perform comprehensive multi-platform repository operations without leaving your terminal.

**GitHub:**
- **Issues**: List, read, create, update, comment, search, assign to Copilot
- **Pull Requests**: List, read, create, update, merge, comment
- **Workflows**: List, monitor runs, trigger, cancel, detect approval required
- **Code Scanning**: List security alerts, get vulnerability details

**GitLab** (optional):
- **Issues**: List, read, create, update, add notes, search
- **Merge Requests**: List, read, create, update, merge, add notes
- **Pipelines**: List, monitor, trigger, cancel, retry, get jobs

**Common:**
- **File System**: List files, read contents, search patterns, parse POMs, find dependency versions
- **Maven Dependencies** (optional): Version checks, dependency updates, vulnerability scanning, triage analysis

```bash
You: List all open issues in partition
Agent: I found 1 open issue in partition:

• #2: Configure MCP Server for GitHub Copilot Agent [human-required]

You: Tell me about issue #2
Agent: Here are the details for the open issue in azure/partition:

• Issue: #2 — Configure MCP Server for GitHub Copilot Agent
• State: open
• Author: github-actions[bot]
• Labels: human-required
• Created / Updated: 2025-10-06T20:21:31+00:00

You: Look at https://github.com/azure/partition/security/code-scanning/5
Agent: 🔴 Code Scanning Alert #5: SQL Injection Vulnerability
       State: Open | Severity: High
       File: src/api/query.js:42-45

       Unsanitized user input flows into SQL query construction...

       Would you like me to create a tracking issue for this security finding?

You: /fork partition
Agent: -- Custom workflow results --

You: /status legal
Agent: -- Custom workflow results --

You: /test partition
Agent: -- Maven test results --

You: /depends partition
Agent: -- Dependency update analysis results --

You: The latest os-core-lib-azure version is 2.2.6. Locate services that aren't at the latest version.
Agent: Found 3 reference(s) to org.opengroup.osdu:os-core-lib-azure:

       Service: file
         repos/file/providers/azure/pom.xml
           Version: ${os-core-lib-azure.version} → 2.2.5
           Location: dependencies

       Service: partition
         repos/partition/providers/azure/pom.xml
           Version: 2.2.6
           Location: dependencies

       Service: legal
         repos/legal/providers/azure/pom.xml
           Version: 2.2.4
           Location: dependencies

       Services not at version 2.2.6: file (2.2.5), legal (2.2.4)
```

## Prerequisites

**Azure Requirements**
- [Azure Foundry OpenAI](https://learn.microsoft.com/en-us/azure/ai-foundry/quickstarts/get-started-code?tabs=azure-ai-foundry)
- [Github Copilot CLI](https://github.com/github/copilot-cli)

**Required**
- Python 3.12+
- [uv](https://docs.astral.sh/uv/getting-started/installation/) package manager
- [GitHub CLI](https://github.com/cli/cli#installation) + `gh auth login`

**Optional (for Maven dependency management)**
- [trivy](https://trivy.dev) for security vulnerability scanning



## Install

Install `osdu-agent` globally using `uv`:

```bash
# Install from GitHub
uv tool install --prerelease=allow git+https://github.com/danielscholl/osdu-agent.git

# Upgrade to latest version
uv tool upgrade osdu-agent
```

The agent requires environment variables for Azure OpenAI access. Configure these in your system's environment:

**Required Environment Variables:**

| Variable | Description | Example |
|----------|-------------|---------|
| `AZURE_OPENAI_ENDPOINT` | Your Azure OpenAI resource URL | `https://my-resource.cognitiveservices.azure.com/` |
| `AZURE_OPENAI_DEPLOYMENT_NAME` | Model deployment name | `gpt-4o-mini` |
| `AZURE_OPENAI_VERSION` | API version | `2025-03-01-preview` |
| `AZURE_OPENAI_API_KEY` | API key (falls back to `az login` if not set) | `your_api_key` |

**Optional Environment Variables:**

| Variable | Default | Description |
|----------|---------|-------------|
| `OSDU_AGENT_ORGANIZATION` | `azure` | GitHub organization to manage |
| `OSDU_AGENT_REPOSITORIES` | `partition,legal,entitlements,schema,file,storage,indexer,indexer-queue,search,workflow` | Comma-separated repository list |
| `GITLAB_URL` | `https://gitlab.com` | GitLab instance URL (for self-hosted instances) |
| `GITLAB_TOKEN` | *(none)* | GitLab personal access token (enables GitLab integration) |
| `GITLAB_DEFAULT_GROUP` | *(none)* | Default GitLab group/namespace for projects |
| `APPLICATIONINSIGHTS_CONNECTION_STRING` | *(none)* | Azure Application Insights for observability |
| `MAVEN_MCP_VERSION` | `mvn-mcp-server==2.3.0` | Override Maven MCP Server version |
| `OSDU_AGENT_HOSTED_TOOLS_ENABLED` | `false` | Enable Microsoft Agent Framework hosted tools |
| `OSDU_AGENT_HOSTED_TOOLS_MODE` | `complement` | Hosted tools mode (`complement`, `replace`, `fallback`) |

**Platform-specific setup:**

```bash
# macOS/Linux - Add to shell profile (~/.zshrc, ~/.bashrc, ~/.zshenv)
export AZURE_OPENAI_ENDPOINT="https://..."
export AZURE_OPENAI_API_KEY="your_api_key"

# Windows PowerShell - Add to profile ($PROFILE)
$env:AZURE_OPENAI_ENDPOINT="https://..."
$env:AZURE_OPENAI_API_KEY="your_api_key"

# Windows CMD - Set system environment variables via GUI or:
setx AZURE_OPENAI_ENDPOINT "https://..."
setx AZURE_OPENAI_API_KEY "your_api_key"
```


## Usage

Start the interactive chat interface:

```bash
osdu
```

The agent provides conversational access to GitHub operations and Maven dependency management. Use natural language to manage issues, pull requests, workflows, and security scanning across your OSDU repositories.

**Maven dependency scanning** is automatically available via the [Maven MCP Server](https://github.com/danielscholl/mvn-mcp-server) (v2.3.0, auto-installed). For security vulnerability scanning, install [Trivy](https://trivy.dev) (optional).

For command-line options:
```bash
osdu --help
```

## Development & Testing

For local development and testing, clone the repository and install in editable mode:

```bash
# Clone the repository
git clone https://github.com/danielscholl/osdu-agent.git
cd osdu-agent

# Configure environment variables (optional - uses shell profile by default)
cp .env.example .env
# Edit .env with your values if preferred over shell profile

# Install in editable mode with dev dependencies
uv pip install -e ".[dev]" --prerelease=allow

# Run tests
uv run pytest

# Run with coverage report
uv run pytest --cov=src/agent --cov-report=term-missing

# Run specific test file
uv run pytest tests/test_agent.py -v
```

**Note:** The `.env` file is provided for convenience during development. The agent still reads from `os.getenv()`, so ensure your shell environment variables are set or use a tool like `python-dotenv` if needed.


## License

Apache License 2.0 - See LICENSE file for details

## Acknowledgments

- Built with [Microsoft Agent Framework](https://github.com/microsoft/agent-framework)
- Powered by [Azure AI Foundry](https://azure.microsoft.com/en-us/products/ai-services/ai-studio)
- Workflow automation via [GitHub Copilot CLI](https://www.npmjs.com/package/@github/copilot)
