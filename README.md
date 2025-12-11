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

**Optional (simplifies authentication):**
- [Azure CLI](https://learn.microsoft.com/cli/azure/install-azure-cli) - auth via `az login` + observability auto-fetch
- [GitHub CLI](https://github.com/cli/cli#installation) - auth via `gh auth login` + connection status
- [GitLab CLI](https://gitlab.com/gitlab-org/cli) - auth via `glab auth login` (if using GitLab features)
- [Trivy](https://trivy.dev) - for vulnerability scanning

## Quick Setup

```bash
# 1. Install
uv tool install --prerelease=allow git+https://github.com/danielscholl/osdu.git

# Upgrade
uv tool upgrade osdu

# 2. Configure required credentials
cp .env.example .env
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

## Usage

```bash
# Interactive chat mode
osdu

# Single query
osdu -p "List issues in partition"

# Get help
osdu --help
```

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup, code quality guidelines, and contribution workflow.

## License

Apache License 2.0 - See LICENSE file for details

## Acknowledgments

- Built with [Microsoft Agent Framework](https://github.com/microsoft/agent-framework)
- Powered by [Azure AI Foundry](https://azure.microsoft.com/en-us/products/ai-services/ai-studio)
