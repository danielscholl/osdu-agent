# OSDU Agent

Conversational DevOps for OSDU. AN AI-powered engineering system management agent.

[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)

## Overview

Manage Azure SPI Layers and OSDU Community repositories and interact with them using natural language to manage issues, pull requests, workflows, code scanning, and dependencies.

```bash
# Start interactive chat
osdu

You: List open issues in partition
Agent: Found 2 open issues in azure/partition...

You: What's the latest os-core-lib-azure version across services?
Agent: Found 3 references to org.opengroup.osdu:os-core-lib-azure:
       partition: 2.2.6, file: 2.2.5, legal: 2.2.4

You: Create an issue in partition to update dependencies
Agent: Created issue #15: Update os-core-lib-azure to 2.2.6...
```

Supports issues, PRs, workflows, code scanning. Includes dependency analysis and security vulnerability scanning.

## Prerequisites

### Azure Resources (Cloud)

**Required:**
- [Azure OpenAI](https://learn.microsoft.com/azure/ai-services/openai/how-to/create-resource) deployment with a model (e.g., gpt-4, gpt-35-turbo)

**Optional (for observability):**
- [Azure AI Foundry](https://ai.azure.com) project with linked Application Insights

### Local Tools (Client)

**Required:**
- Python 3.12+
- [uv](https://docs.astral.sh/uv/getting-started/installation/) package manager

**Optional (enhances experience):**
- [GitHub CLI](https://github.com/cli/cli#installation) - for auth, connection status, and assigning issues to Copilot Workspace
- [GitLab CLI](https://gitlab.com/gitlab-org/cli) - for auth and connection status (if using GitLab features)
- [Azure CLI](https://learn.microsoft.com/cli/azure/install-azure-cli) - for auth and observability auto-fetch
- [Trivy](https://trivy.dev) - for vulnerability scanning

## Quick Setup

```bash
# 1. Install
uv tool install --prerelease=allow git+https://github.com/danielscholl/osdu-agent.git

# 2. Configure required credentials
cp .env.example .env
```

**Edit `.env` with required settings:**

```bash
# Azure OpenAI (Required)
AZURE_OPENAI_ENDPOINT=https://your-endpoint.openai.azure.com/
AZURE_OPENAI_DEPLOYMENT_NAME=gpt-5-mini

# Observability (Optional - auto-fetch from Azure AI Foundry)
# AZURE_AI_PROJECT_CONNECTION_STRING=eastus.api.azureml.ms;sub-id;resource-group;workspace-name
```

**Authenticate with CLI tools** (recommended):
```bash
az login      # For Azure OpenAI
gh auth login # For GitHub (optional - increases rate limits)
glab auth login # For GitLab (optional - only if using GitLab features)
```

**OR use API keys** (if CLI not available):
```bash
# AZURE_OPENAI_API_KEY=your-key
# GITHUB_TOKEN=your-token
# GITLAB_TOKEN=your-token
```

**Authentication priority:**
- GitHub: `gh auth token` → `GITHUB_TOKEN` env var → unauthenticated
- GitLab: `glab auth status --show-token` → `GITLAB_TOKEN` env var

```bash
# 3. Run
osdu
```

## Usage

```bash
# Interactive chat mode
osdu

# Single query
osdu -p "List issues in partition"

# Get help
osdu --help
```

Maven dependency scanning available via [Maven MCP Server](https://github.com/danielscholl/mvn-mcp-server) (auto-installed). For vulnerability scanning, install [Trivy](https://trivy.dev) (optional).

## Observability (Optional)

Enable Application Insights telemetry to track agent operations, LLM calls, and tool executions.

**Setup:** Add to `.env`:
```bash
AZURE_AI_PROJECT_CONNECTION_STRING=eastus.api.azureml.ms;sub-id;resource-group;workspace-name
```

The agent automatically fetches the Application Insights connection string from your Azure AI Foundry workspace (requires `az login` and Reader access).

**View traces:**
- **Azure AI Foundry**: https://ai.azure.com → Tracing (enhanced UI for AI agents)
- **Application Insights**: Azure Portal → Transaction search (traditional APM)

Every trace includes: user ID, session ID, token usage, and operation details.

For complete setup guide, see [`docs/OBSERVABILITY.md`](docs/OBSERVABILITY.md)

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup, code quality guidelines, and contribution workflow.

## License

Apache License 2.0 - See LICENSE file for details

## Acknowledgments

- Built with [Microsoft Agent Framework](https://github.com/microsoft/agent-framework)
- Powered by [Azure AI Foundry](https://azure.microsoft.com/en-us/products/ai-services/ai-studio)
