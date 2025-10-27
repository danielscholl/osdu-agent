"""Git repository management tools package."""

from typing import List

from agent.config import AgentConfig
from agent.git.tools import GitRepositoryTools


def create_git_tools(config: AgentConfig) -> List:
    """
    Create git repository tool functions for the agent.

    Args:
        config: Agent configuration

    Returns:
        List of 12 bound tool methods for git repository operations:
        - Repository Management (7 tools): list, status, reset, fetch, pull, pull_all, create_branch
        - Remote Management (3 tools): list_remotes, add_remote, remove_remote
        - Upstream Configuration (2 tools): configure_upstream, configure_all_upstreams
    """
    tools = GitRepositoryTools(config)

    return [
        # Repository Management (7 tools)
        tools.list_local_repositories,
        tools.get_repository_status,
        tools.reset_repository,
        tools.fetch_repository,
        tools.pull_repository,
        tools.pull_all_repositories,
        tools.create_branch,
        # Remote Management (3 tools)
        tools.list_remotes,
        tools.add_remote,
        tools.remove_remote,
        # Upstream Configuration (3 tools)
        tools.configure_upstream_remote,
        tools.configure_all_upstream_remotes,
    ]


__all__ = [
    "GitRepositoryTools",
    "create_git_tools",
]
