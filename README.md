# OSDU Agent

Conversational DevOps for OSDU. AI-powered engineering system management.

[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)

## Overview

AI agent for managing Azure SPI Layers and OSDU Community repositories. Use natural language to manage issues, pull requests, workflows, code scanning, and Maven dependencies.

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

Supports issues, PRs, workflows, code scanning. Includes Maven dependency analysis and security vulnerability scanning.

## Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/getting-started/installation/) package manager
- [GitHub CLI](https://github.com/cli/cli#installation) authenticated with `gh auth login`
- [GitHub Copilot CLI](https://github.com/github/copilot-cli) for workflow automation
- [Azure OpenAI](https://learn.microsoft.com/en-us/azure/ai-foundry/quickstarts/get-started-code) endpoint and API key

Optional: [Trivy](https://trivy.dev) for vulnerability scanning, GitLab token for GitLab integration

## Install

```bash
# Install globally
uv tool install --prerelease=allow git+https://github.com/danielscholl/osdu-agent.git

# Configure environment
cp .env.example .env
# Edit .env with your Azure OpenAI credentials
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

Maven dependency scanning is available via [Maven MCP Server](https://github.com/danielscholl/mvn-mcp-server) (auto-installed). For vulnerability scanning, install [Trivy](https://trivy.dev) (optional).

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup, code quality guidelines, and contribution workflow.

## License

Apache License 2.0 - See LICENSE file for details

## Acknowledgments

- Built with [Microsoft Agent Framework](https://github.com/microsoft/agent-framework)
- Powered by [Azure AI Foundry](https://azure.microsoft.com/en-us/products/ai-services/ai-studio)
