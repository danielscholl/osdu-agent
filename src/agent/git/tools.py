"""Git repository management tools for local OSDU service repositories."""

import logging
import re
import subprocess
from pathlib import Path
from typing import Annotated, List, Optional, Tuple

from pydantic import Field

from agent.config import AgentConfig

logger = logging.getLogger(__name__)


class SecurityError(Exception):
    """Raised when a security violation is detected (e.g., path traversal attempt)."""

    pass


class GitRepositoryTools:
    """
    Tools for git operations on local repositories.

    All operations are strictly sandboxed to the repos/ directory for security.
    """

    def __init__(self, config: AgentConfig):
        """
        Initialize git repository tools.

        Args:
            config: Agent configuration
        """
        self.config = config
        # Use absolute path for security validation
        self.repos_dir = config.repos_root.resolve()
        logger.debug(f"Git tools initialized with repos_dir: {self.repos_dir}")

    def _sanitize_service_name(self, service: str) -> str:
        """
        Sanitize service name to prevent path traversal attacks.

        Only allows alphanumeric characters, hyphens, and underscores.
        Rejects path separators and parent directory references.

        Args:
            service: Service name to sanitize

        Returns:
            Sanitized service name

        Raises:
            ValueError: If service name contains invalid characters
        """
        service = service.strip()

        # Reject empty names
        if not service:
            raise ValueError("Service name cannot be empty")

        # Reject path traversal attempts
        if ".." in service or "/" in service or "\\" in service:
            raise ValueError(
                f"Invalid service name '{service}': contains path separators or parent directory references"
            )

        # Only allow alphanumeric, hyphens, underscores
        if not re.match(r"^[a-zA-Z0-9_-]+$", service):
            raise ValueError(
                f"Invalid service name '{service}': only alphanumeric characters, hyphens, and underscores are allowed"
            )

        return service

    def _validate_repo_path_is_sandboxed(self, repo_path: Path) -> bool:
        """
        Validate that a repository path is within the repos/ directory sandbox.

        This is a critical security function that prevents operations outside
        the repos/ directory, including on the osdu-agent project directory itself.

        Args:
            repo_path: Path to validate

        Returns:
            True if path is within sandbox

        Raises:
            SecurityError: If path is outside the repos/ directory
        """
        try:
            # Resolve both paths to absolute to handle symlinks and relative paths
            repo_abs = repo_path.resolve()
            repos_abs = self.repos_dir.resolve()

            # Check if repo_path is within repos_dir
            # is_relative_to() returns True if the path is a child of repos_dir
            if not repo_abs.is_relative_to(repos_abs):
                logger.error(
                    f"SECURITY: Path traversal attempt detected - "
                    f"tried to access '{repo_abs}' outside sandbox '{repos_abs}'"
                )
                raise SecurityError(
                    f"Access denied: Path '{repo_path}' is outside the repos/ directory. "
                    f"All git operations are restricted to the repos/ directory for security."
                )

            logger.debug(f"Path validation passed: {repo_abs} is within {repos_abs}")
            return True

        except ValueError as e:
            # is_relative_to can raise ValueError in some edge cases
            logger.error(f"SECURITY: Path validation error for '{repo_path}': {e}")
            raise SecurityError(f"Path validation failed for '{repo_path}': {e}")

    def _get_repo_path(self, service: str) -> Path:
        """
        Construct and validate repository path for a service.

        Args:
            service: Service name (will be sanitized)

        Returns:
            Validated Path object for the repository

        Raises:
            ValueError: If service name is invalid
            SecurityError: If resulting path is outside sandbox
        """
        # First sanitize the service name
        safe_service = self._sanitize_service_name(service)

        # Construct path
        repo_path = self.repos_dir / safe_service

        # Validate it's within sandbox
        self._validate_repo_path_is_sandboxed(repo_path)

        return repo_path

    def _validate_repository(self, repo_path: Path) -> Tuple[bool, str]:
        """
        Validate that a directory is a valid git repository.

        Args:
            repo_path: Path to repository (must already be sandboxed)

        Returns:
            Tuple of (is_valid, error_message)
        """
        # Ensure path is sandboxed (defensive check)
        try:
            self._validate_repo_path_is_sandboxed(repo_path)
        except SecurityError as e:
            return False, str(e)

        # Check if directory exists
        if not repo_path.exists():
            return False, f"Repository directory does not exist: {repo_path}"

        if not repo_path.is_dir():
            return False, f"Path is not a directory: {repo_path}"

        # Check if it's a git repository
        git_dir = repo_path / ".git"
        if not git_dir.exists():
            return False, f"Not a git repository (no .git directory): {repo_path}"

        return True, ""

    def _execute_git_command(
        self, repo_path: Path, command: List[str], timeout: int = 30
    ) -> Tuple[int, str, str]:
        """
        Execute a git command in a specific repository.

        CRITICAL: Always uses explicit cwd parameter to isolate operations.
        Never changes the process working directory.

        Args:
            repo_path: Repository path (must be sandboxed)
            command: Command as list (e.g., ['git', 'status'])
            timeout: Command timeout in seconds

        Returns:
            Tuple of (return_code, stdout, stderr)

        Raises:
            SecurityError: If repo_path is not sandboxed
        """
        # Critical security check before ANY git command
        self._validate_repo_path_is_sandboxed(repo_path)

        try:
            logger.debug(f"Executing git command in {repo_path}: {' '.join(command)}")

            result = subprocess.run(
                command,
                cwd=repo_path,  # CRITICAL: Never use os.chdir(), always use cwd
                capture_output=True,
                text=True,
                timeout=timeout,
            )

            return result.returncode, result.stdout, result.stderr

        except subprocess.TimeoutExpired:
            return 1, "", f"Command timed out after {timeout} seconds"
        except Exception as e:
            return 1, "", f"Error executing git command: {str(e)}"

    def list_local_repositories(self) -> str:
        """
        List all cloned repositories in the repos/ directory.

        Shows repository name, current branch, and basic status.
        Only operates within the repos/ directory sandbox.

        Returns:
            Formatted string with repository information
        """
        try:
            # Check if repos directory exists
            if not self.repos_dir.exists():
                return (
                    "No repositories found. The repos/ directory does not exist.\n"
                    "Use the fork workflow to clone repositories first."
                )

            # Find all subdirectories in repos/
            subdirs = [d for d in self.repos_dir.iterdir() if d.is_dir()]

            if not subdirs:
                return (
                    f"No repositories found in {self.repos_dir}\n"
                    f"Use the fork workflow to clone repositories first."
                )

            # Check each directory to see if it's a valid git repo
            repositories = []
            for repo_dir in subdirs:
                # Validate path is sandboxed
                try:
                    self._validate_repo_path_is_sandboxed(repo_dir)
                except SecurityError:
                    logger.warning(f"Skipping directory outside sandbox: {repo_dir}")
                    continue

                is_valid, error = self._validate_repository(repo_dir)
                if is_valid:
                    # Get current branch
                    returncode, stdout, stderr = self._execute_git_command(
                        repo_dir, ["git", "branch", "--show-current"]
                    )
                    branch = stdout.strip() if returncode == 0 else "unknown"

                    # Get status summary
                    returncode, stdout, stderr = self._execute_git_command(
                        repo_dir, ["git", "status", "--porcelain"]
                    )
                    clean = len(stdout.strip()) == 0 if returncode == 0 else None

                    repositories.append({"name": repo_dir.name, "branch": branch, "clean": clean})

            if not repositories:
                return (
                    f"No valid git repositories found in {self.repos_dir}\n"
                    f"Found {len(subdirs)} directories but none are git repositories."
                )

            # Format output
            output_lines = [f"Found {len(repositories)} local repository(ies):\n\n"]

            for repo in sorted(repositories, key=lambda r: r["name"]):
                status = (
                    "clean"
                    if repo["clean"]
                    else "modified" if repo["clean"] is not None else "unknown"
                )
                output_lines.append(
                    f"  {repo['name']:<20} (branch: {repo['branch']:<15} status: {status})\n"
                )

            output_lines.append(f"\nAll repositories are in: {self.repos_dir}\n")

            return "".join(output_lines)

        except Exception as e:
            logger.error(f"Error listing repositories: {e}", exc_info=True)
            return f"Error listing repositories: {str(e)}"

    def get_repository_status(
        self,
        service: Annotated[
            str,
            Field(
                description="Service name (e.g., 'partition', 'legal', 'storage'). "
                "This identifies which repository in repos/ to check."
            ),
        ],
    ) -> str:
        """
        Get detailed git status for a specific repository.

        Shows current branch, tracking information, and working tree status.

        Args:
            service: Service name to check status for

        Returns:
            Formatted string with detailed git status
        """
        try:
            # Get and validate repository path
            repo_path = self._get_repo_path(service)

            # Validate it's a git repository
            is_valid, error = self._validate_repository(repo_path)
            if not is_valid:
                return f"Error: {error}"

            output_lines = [f"Git status for {service}:\n\n"]

            # Get current branch
            returncode, stdout, stderr = self._execute_git_command(
                repo_path, ["git", "branch", "--show-current"]
            )
            if returncode == 0 and stdout.strip():
                branch = stdout.strip()
                output_lines.append(f"Branch: {branch}\n")
            else:
                # Detached HEAD or error
                returncode, stdout, stderr = self._execute_git_command(
                    repo_path, ["git", "rev-parse", "--short", "HEAD"]
                )
                commit = stdout.strip() if returncode == 0 else "unknown"
                output_lines.append(f"HEAD detached at {commit}\n")
                branch = None

            # Get tracking information
            if branch:
                returncode, stdout, stderr = self._execute_git_command(
                    repo_path, ["git", "rev-parse", "--abbrev-ref", f"{branch}@{{upstream}}"]
                )
                if returncode == 0:
                    upstream = stdout.strip()
                    output_lines.append(f"Tracking: {upstream}\n")

                    # Get ahead/behind info
                    returncode, stdout, stderr = self._execute_git_command(
                        repo_path,
                        ["git", "rev-list", "--left-right", "--count", f"HEAD...{upstream}"],
                    )
                    if returncode == 0:
                        parts = stdout.strip().split()
                        if len(parts) == 2:
                            ahead, behind = parts
                            if ahead != "0" or behind != "0":
                                output_lines.append(f"Ahead: {ahead}, Behind: {behind}\n")
                else:
                    output_lines.append("No upstream tracking branch\n")

            output_lines.append("\n")

            # Get working tree status
            returncode, stdout, stderr = self._execute_git_command(
                repo_path, ["git", "status", "--porcelain"]
            )

            if returncode != 0:
                output_lines.append(f"Error getting status: {stderr}\n")
            elif not stdout.strip():
                output_lines.append("Working tree clean - no changes\n")
            else:
                # Parse porcelain output
                lines = stdout.strip().split("\n")
                staged = []
                unstaged = []
                untracked = []

                for line in lines:
                    if len(line) < 3:
                        continue

                    status_code = line[:2]
                    file_path = line[3:]

                    if status_code[0] != " " and status_code[0] != "?":
                        staged.append((status_code[0], file_path))
                    if status_code[1] != " " and status_code[1] != "?":
                        unstaged.append((status_code[1], file_path))
                    if status_code == "??":
                        untracked.append(file_path)

                if staged:
                    output_lines.append(f"Staged changes ({len(staged)}):\n")
                    for code, path in staged[:10]:
                        output_lines.append(f"  {code} {path}\n")
                    if len(staged) > 10:
                        output_lines.append(f"  ... and {len(staged) - 10} more\n")
                    output_lines.append("\n")

                if unstaged:
                    output_lines.append(f"Unstaged changes ({len(unstaged)}):\n")
                    for code, path in unstaged[:10]:
                        output_lines.append(f"  {code} {path}\n")
                    if len(unstaged) > 10:
                        output_lines.append(f"  ... and {len(unstaged) - 10} more\n")
                    output_lines.append("\n")

                if untracked:
                    output_lines.append(f"Untracked files ({len(untracked)}):\n")
                    for path in untracked[:10]:
                        output_lines.append(f"  {path}\n")
                    if len(untracked) > 10:
                        output_lines.append(f"  ... and {len(untracked) - 10} more\n")

            return "".join(output_lines)

        except ValueError as e:
            return f"Error: {str(e)}"
        except SecurityError as e:
            return f"Security Error: {str(e)}"
        except Exception as e:
            logger.error(f"Error getting repository status: {e}", exc_info=True)
            return f"Error getting repository status: {str(e)}"

    def reset_repository(
        self,
        service: Annotated[
            str,
            Field(
                description="Service name (e.g., 'partition', 'legal', 'storage') to reset. "
                "This will clean untracked files from the repository."
            ),
        ],
        clean_ignored: Annotated[
            bool,
            Field(
                description="If True, also remove ignored files (git clean -fdx). "
                "If False (default), only remove files ignored by .gitignore (git clean -fdX). "
                "WARNING: This operation cannot be undone."
            ),
        ] = False,
    ) -> str:
        """
        Reset repository by cleaning untracked files.

        WARNING: This operation removes files and cannot be undone.
        Only operates within repos/ directory - never affects osdu-agent project.

        By default uses 'git clean -fdX' (removes only ignored files).
        With clean_ignored=True uses 'git clean -fdx' (removes ALL untracked files).

        Args:
            service: Service name to reset
            clean_ignored: Whether to also clean ignored files

        Returns:
            Formatted string with reset operation results
        """
        try:
            # Get and validate repository path
            repo_path = self._get_repo_path(service)

            # Validate it's a git repository
            is_valid, error = self._validate_repository(repo_path)
            if not is_valid:
                return f"Error: {error}"

            # Construct git clean command
            if clean_ignored:
                # Remove ALL untracked files including ignored ones
                clean_cmd = ["git", "clean", "-fdx"]
                description = "Removing all untracked files (including ignored files)"
            else:
                # Remove only ignored files
                clean_cmd = ["git", "clean", "-fdX"]
                description = "Removing ignored files only"

            output_lines = [f"Resetting repository: {service}\n", f"{description}\n\n"]

            # First do a dry run to see what would be removed
            dry_run_cmd = clean_cmd + ["--dry-run"]
            returncode, stdout, stderr = self._execute_git_command(repo_path, dry_run_cmd)

            if returncode != 0:
                return f"Error during dry run: {stderr}"

            if not stdout.strip():
                return f"Repository {service} is already clean - no files to remove"

            # Show what will be removed
            files_to_remove = stdout.strip().split("\n")
            output_lines.append(f"Files to be removed ({len(files_to_remove)}):\n")
            for file_line in files_to_remove[:15]:
                output_lines.append(f"  {file_line}\n")
            if len(files_to_remove) > 15:
                output_lines.append(f"  ... and {len(files_to_remove) - 15} more\n")
            output_lines.append("\n")

            # Execute actual clean
            returncode, stdout, stderr = self._execute_git_command(repo_path, clean_cmd)

            if returncode != 0:
                output_lines.append(f"Error during clean: {stderr}\n")
            else:
                output_lines.append(f"Successfully cleaned {service} repository\n")

            return "".join(output_lines)

        except ValueError as e:
            return f"Error: {str(e)}"
        except SecurityError as e:
            return f"Security Error: {str(e)}"
        except Exception as e:
            logger.error(f"Error resetting repository: {e}", exc_info=True)
            return f"Error resetting repository: {str(e)}"

    def fetch_repository(
        self,
        service: Annotated[
            str,
            Field(
                description="Service name (e.g., 'partition', 'legal', 'storage') to fetch updates for"
            ),
        ],
        remote: Annotated[
            str,
            Field(description="Remote name to fetch from (default: 'origin')"),
        ] = "origin",
        prune: Annotated[
            bool,
            Field(
                description="Remove remote-tracking references that no longer exist on remote (default: True)"
            ),
        ] = True,
    ) -> str:
        """
        Fetch latest changes from remote repository without merging.

        This updates remote-tracking branches but does not modify your working tree.

        Args:
            service: Service name to fetch
            remote: Remote name (default: origin)
            prune: Whether to prune deleted remote branches

        Returns:
            Formatted string with fetch results
        """
        try:
            # Get and validate repository path
            repo_path = self._get_repo_path(service)

            # Validate it's a git repository
            is_valid, error = self._validate_repository(repo_path)
            if not is_valid:
                return f"Error: {error}"

            # Construct fetch command
            fetch_cmd = ["git", "fetch", remote]
            if prune:
                fetch_cmd.append("--prune")

            output_lines = [f"Fetching updates for {service} from remote '{remote}'...\n\n"]

            # Execute fetch
            returncode, stdout, stderr = self._execute_git_command(repo_path, fetch_cmd, timeout=60)

            if returncode != 0:
                # Check if it's a network error or remote doesn't exist
                if "Could not resolve host" in stderr or "unable to access" in stderr:
                    output_lines.append("Network error: Cannot reach remote repository\n")
                    output_lines.append(f"Details: {stderr}\n")
                elif f"'{remote}' does not appear to be a git repository" in stderr:
                    output_lines.append(f"Error: Remote '{remote}' does not exist\n")
                    output_lines.append(f"Details: {stderr}\n")
                else:
                    output_lines.append(f"Error fetching: {stderr}\n")
            else:
                # Fetch successful
                if stderr.strip():
                    # Git fetch outputs to stderr even on success
                    output_lines.append("Fetch completed successfully\n")
                    output_lines.append(f"\n{stderr}\n")
                else:
                    output_lines.append("Fetch completed - repository is up to date\n")

            return "".join(output_lines)

        except ValueError as e:
            return f"Error: {str(e)}"
        except SecurityError as e:
            return f"Security Error: {str(e)}"
        except Exception as e:
            logger.error(f"Error fetching repository: {e}", exc_info=True)
            return f"Error fetching repository: {str(e)}"

    def pull_repository(
        self,
        service: Annotated[
            str,
            Field(
                description="Service name (e.g., 'partition', 'legal', 'storage') to pull updates for"
            ),
        ],
        remote: Annotated[
            str,
            Field(description="Remote name to pull from (default: 'origin')"),
        ] = "origin",
        branch: Annotated[
            Optional[str],
            Field(
                description="Branch name to pull (default: current branch). "
                "If not specified, pulls the current branch."
            ),
        ] = None,
    ) -> str:
        """
        Pull latest changes from remote and merge into current branch.

        This fetches and merges changes in one operation.

        Args:
            service: Service name to pull
            remote: Remote name (default: origin)
            branch: Branch to pull (default: current branch)

        Returns:
            Formatted string with pull results
        """
        try:
            # Get and validate repository path
            repo_path = self._get_repo_path(service)

            # Validate it's a git repository
            is_valid, error = self._validate_repository(repo_path)
            if not is_valid:
                return f"Error: {error}"

            # If branch not specified, get current branch
            if branch is None:
                returncode, stdout, stderr = self._execute_git_command(
                    repo_path, ["git", "branch", "--show-current"]
                )
                if returncode != 0 or not stdout.strip():
                    return "Error: Could not determine current branch (detached HEAD?)"
                branch = stdout.strip()

            output_lines = [f"Pulling {service} from {remote}/{branch}...\n\n"]

            # Construct pull command
            pull_cmd = ["git", "pull", remote, branch]

            # Execute pull
            returncode, stdout, stderr = self._execute_git_command(repo_path, pull_cmd, timeout=60)

            if returncode != 0:
                # Check for common error scenarios
                if "Your local changes to the following files would be overwritten" in stderr:
                    output_lines.append("Error: Local changes would be overwritten by pull\n")
                    output_lines.append("Please commit or stash your changes before pulling.\n")
                    output_lines.append(f"\nDetails: {stderr}\n")
                elif "CONFLICT" in stdout or "CONFLICT" in stderr:
                    output_lines.append("Merge conflicts detected!\n")
                    output_lines.append("Please resolve conflicts manually.\n")
                    output_lines.append(f"\n{stdout}\n")
                elif "no tracking information" in stderr:
                    output_lines.append(
                        f"Error: Branch '{branch}' has no upstream tracking information\n"
                    )
                    output_lines.append(f"Details: {stderr}\n")
                elif "Could not resolve host" in stderr or "unable to access" in stderr:
                    output_lines.append("Network error: Cannot reach remote repository\n")
                    output_lines.append(f"Details: {stderr}\n")
                else:
                    output_lines.append(f"Error during pull: {stderr}\n")
            else:
                # Pull successful
                if "Already up to date" in stdout or "Already up-to-date" in stdout:
                    output_lines.append("Already up to date - no changes\n")
                elif "Fast-forward" in stdout:
                    output_lines.append("Fast-forward merge completed successfully\n")
                    output_lines.append(f"\n{stdout}\n")
                else:
                    output_lines.append("Pull completed successfully\n")
                    output_lines.append(f"\n{stdout}\n")

            return "".join(output_lines)

        except ValueError as e:
            return f"Error: {str(e)}"
        except SecurityError as e:
            return f"Security Error: {str(e)}"
        except Exception as e:
            logger.error(f"Error pulling repository: {e}", exc_info=True)
            return f"Error pulling repository: {str(e)}"

    def pull_all_repositories(
        self,
        remote: Annotated[
            str,
            Field(description="Remote name to pull from for all repositories (default: 'origin')"),
        ] = "origin",
    ) -> str:
        """
        Pull latest changes for all local repositories.

        Continues processing all repositories even if some fail.
        Provides a summary of successes and failures.

        Args:
            remote: Remote name to pull from

        Returns:
            Formatted string with summary of all pull operations
        """
        try:
            # Get list of repositories
            if not self.repos_dir.exists():
                return "No repositories found. The repos/ directory does not exist."

            subdirs = [d for d in self.repos_dir.iterdir() if d.is_dir()]

            if not subdirs:
                return "No repositories found in repos/ directory"

            # Validate and collect valid repos
            valid_repos = []
            for repo_dir in subdirs:
                try:
                    self._validate_repo_path_is_sandboxed(repo_dir)
                    is_valid, _ = self._validate_repository(repo_dir)
                    if is_valid:
                        valid_repos.append(repo_dir.name)
                except SecurityError:
                    continue

            if not valid_repos:
                return "No valid git repositories found"

            output_lines = [f"Pulling latest changes for {len(valid_repos)} repository(ies)...\n\n"]

            # Track results
            results = []

            for service in sorted(valid_repos):
                output_lines.append(f"Processing {service}...\n")

                # Pull this repository
                result = self.pull_repository(service, remote=remote)

                # Determine if it was successful
                # Check for various error indicators (case-insensitive for "error")
                result_lower = result.lower()
                success = "error" not in result_lower and "CONFLICT" not in result

                # Extract meaningful error message for failed repos
                error_message = result.split("\n")[0]  # Default to first line
                if not success:
                    # Look for lines starting with Error:, Security Error:, or containing CONFLICT
                    for line in result.split("\n"):
                        line = line.strip()
                        if (
                            line.startswith("Error:")
                            or line.startswith("Security Error:")
                            or "CONFLICT" in line
                        ):
                            error_message = line
                            break
                        # Also check for specific error descriptions
                        if (
                            line.startswith("Merge conflicts")
                            or line.startswith("Network error")
                            or line.startswith("Local changes would")
                        ):
                            error_message = line
                            break

                results.append({"service": service, "success": success, "message": error_message})

                output_lines.append(f"  {result}\n")

            # Add summary
            successes = sum(1 for r in results if r["success"])
            failures = len(results) - successes

            output_lines.append(f"\n{'='*60}\n")
            output_lines.append(f"Summary: {successes} succeeded, {failures} failed\n")
            output_lines.append(f"{'='*60}\n\n")

            if failures > 0:
                output_lines.append("Failed repositories:\n")
                for r in results:
                    if not r["success"]:
                        output_lines.append(f"  - {r['service']}: {r['message']}\n")

            return "".join(output_lines)

        except Exception as e:
            logger.error(f"Error pulling all repositories: {e}", exc_info=True)
            return f"Error pulling all repositories: {str(e)}"

    def create_branch(
        self,
        service: Annotated[
            str,
            Field(
                description="Service name (e.g., 'partition', 'legal', 'storage') to create branch in"
            ),
        ],
        branch_name: Annotated[
            str,
            Field(
                description="Name of the new branch to create (e.g., 'feature-auth', 'fix-bug-123')"
            ),
        ],
        from_branch: Annotated[
            Optional[str],
            Field(
                description="Source branch to create from (default: current branch). "
                "If specified, the new branch will be created from this branch."
            ),
        ] = None,
        checkout: Annotated[
            bool,
            Field(description="Whether to checkout the new branch after creation (default: True)"),
        ] = True,
    ) -> str:
        """
        Create a new branch in a repository.

        By default, creates and checks out the new branch from the current HEAD.
        Can optionally create from a specific branch.

        Args:
            service: Service name to create branch in
            branch_name: Name of new branch
            from_branch: Optional source branch (default: current branch)
            checkout: Whether to checkout after creation

        Returns:
            Formatted string with branch creation results
        """
        try:
            # Get and validate repository path
            repo_path = self._get_repo_path(service)

            # Validate it's a git repository
            is_valid, error = self._validate_repository(repo_path)
            if not is_valid:
                return f"Error: {error}"

            # Validate branch name format
            branch_name = branch_name.strip()
            if not branch_name:
                return "Error: Branch name cannot be empty"

            # Check if branch name is valid using git check-ref-format
            returncode, stdout, stderr = self._execute_git_command(
                repo_path, ["git", "check-ref-format", "--branch", branch_name]
            )
            if returncode != 0:
                return f"Error: Invalid branch name '{branch_name}'"

            output_lines = [f"Creating branch '{branch_name}' in {service}...\n\n"]

            # Check if branch already exists
            returncode, stdout, stderr = self._execute_git_command(
                repo_path, ["git", "rev-parse", "--verify", f"refs/heads/{branch_name}"]
            )
            if returncode == 0:
                return f"Error: Branch '{branch_name}' already exists in {service}"

            # If from_branch specified, verify it exists
            if from_branch:
                returncode, stdout, stderr = self._execute_git_command(
                    repo_path, ["git", "rev-parse", "--verify", f"refs/heads/{from_branch}"]
                )
                if returncode != 0:
                    return f"Error: Source branch '{from_branch}' does not exist"

                output_lines.append(f"Creating from branch: {from_branch}\n")

            # Construct branch creation command
            if checkout:
                # Create and checkout in one command
                if from_branch:
                    branch_cmd = ["git", "checkout", "-b", branch_name, from_branch]
                else:
                    branch_cmd = ["git", "checkout", "-b", branch_name]
            else:
                # Create without checkout
                if from_branch:
                    branch_cmd = ["git", "branch", branch_name, from_branch]
                else:
                    branch_cmd = ["git", "branch", branch_name]

            # Execute branch creation
            returncode, stdout, stderr = self._execute_git_command(repo_path, branch_cmd)

            if returncode != 0:
                output_lines.append(f"Error creating branch: {stderr}\n")
            else:
                if checkout:
                    output_lines.append(
                        f"Successfully created and checked out branch '{branch_name}'\n"
                    )
                else:
                    output_lines.append(f"Successfully created branch '{branch_name}'\n")
                    output_lines.append("(Branch was not checked out - current branch unchanged)\n")

            return "".join(output_lines)

        except ValueError as e:
            return f"Error: {str(e)}"
        except SecurityError as e:
            return f"Security Error: {str(e)}"
        except Exception as e:
            logger.error(f"Error creating branch: {e}", exc_info=True)
            return f"Error creating branch: {str(e)}"

    def list_remotes(
        self,
        service: Annotated[
            str,
            Field(
                description="Service name (e.g., 'partition', 'legal', 'storage'). "
                "This identifies which repository in repos/ to list remotes for."
            ),
        ],
    ) -> str:
        """
        List all configured git remotes for a repository.

        Shows remote names with their fetch and push URLs.
        All operations are restricted to the repos/ directory sandbox.

        Args:
            service: Service name to list remotes for

        Returns:
            Formatted string with remote names and URLs
        """
        try:
            # Get and validate repository path
            repo_path = self._get_repo_path(service)

            # Validate it's a git repository
            is_valid, error = self._validate_repository(repo_path)
            if not is_valid:
                return f"Error: {error}"

            # Execute git remote -v
            returncode, stdout, stderr = self._execute_git_command(
                repo_path, ["git", "remote", "-v"]
            )

            if returncode != 0:
                return f"Error listing remotes: {stderr}"

            # Parse output
            if not stdout.strip():
                return f"No remotes configured for repository '{service}'."

            # Format output
            output_lines = [f"Remotes for repository '{service}':\n\n"]

            # Parse remote output (format: "name url (fetch/push)")
            remotes = {}
            for line in stdout.strip().split("\n"):
                parts = line.split()
                if len(parts) >= 3:
                    name = parts[0]
                    url = parts[1]
                    remote_type = parts[2].strip("()")

                    if name not in remotes:
                        remotes[name] = {}
                    remotes[name][remote_type] = url

            # Display remotes
            for name in sorted(remotes.keys()):
                output_lines.append(f"  {name}:\n")
                if "fetch" in remotes[name]:
                    output_lines.append(f"    Fetch: {remotes[name]['fetch']}\n")
                if "push" in remotes[name]:
                    output_lines.append(f"    Push:  {remotes[name]['push']}\n")
                output_lines.append("\n")

            return "".join(output_lines)

        except ValueError as e:
            return f"Error: {str(e)}"
        except SecurityError as e:
            return f"Security Error: {str(e)}"
        except Exception as e:
            logger.error(f"Error listing remotes: {e}", exc_info=True)
            return f"Error listing remotes: {str(e)}"

    def add_remote(
        self,
        service: Annotated[
            str,
            Field(
                description="Service name (e.g., 'partition', 'legal', 'storage'). "
                "This identifies which repository in repos/ to add remote to."
            ),
        ],
        remote_name: Annotated[
            str,
            Field(
                description="Name for the remote (e.g., 'upstream', 'gitlab'). "
                "Must contain only alphanumeric characters, hyphens, and underscores."
            ),
        ],
        remote_url: Annotated[
            str,
            Field(
                description="Git URL for the remote (e.g., 'https://gitlab.com/org/repo.git' or 'git@gitlab.com:org/repo.git'). "
                "Must be a valid git URL."
            ),
        ],
    ) -> str:
        """
        Add a new remote to a git repository.

        Validates the remote name and URL before adding.
        All operations are restricted to the repos/ directory sandbox.

        Args:
            service: Service name to add remote to
            remote_name: Name for the new remote
            remote_url: URL for the remote repository

        Returns:
            Formatted string with operation results
        """
        try:
            # Get and validate repository path
            repo_path = self._get_repo_path(service)

            # Validate it's a git repository
            is_valid, error = self._validate_repository(repo_path)
            if not is_valid:
                return f"Error: {error}"

            # Validate remote name
            remote_name = remote_name.strip()
            if not remote_name:
                return "Error: Remote name cannot be empty"

            # Only allow alphanumeric, hyphens, underscores
            if not re.match(r"^[a-zA-Z0-9_-]+$", remote_name):
                return (
                    f"Error: Invalid remote name '{remote_name}'. "
                    "Only alphanumeric characters, hyphens, and underscores are allowed."
                )

            # Validate remote URL format
            remote_url = remote_url.strip()
            if not remote_url:
                return "Error: Remote URL cannot be empty"

            # Basic URL validation - must be http(s):// or git@ URL
            if not (
                remote_url.startswith("http://")
                or remote_url.startswith("https://")
                or remote_url.startswith("git@")
                or remote_url.startswith("ssh://")
            ):
                return (
                    f"Error: Invalid remote URL '{remote_url}'. "
                    "URL must start with http://, https://, ssh://, or git@"
                )

            # Check if remote already exists
            returncode, stdout, stderr = self._execute_git_command(
                repo_path, ["git", "remote", "get-url", remote_name]
            )

            if returncode == 0:
                existing_url = stdout.strip()
                return (
                    f"Error: Remote '{remote_name}' already exists with URL: {existing_url}\n"
                    f"Use a different remote name or remove the existing remote first."
                )

            # Add the remote
            returncode, stdout, stderr = self._execute_git_command(
                repo_path, ["git", "remote", "add", remote_name, remote_url]
            )

            if returncode != 0:
                return f"Error adding remote: {stderr}"

            return (
                f"Successfully added remote '{remote_name}' to repository '{service}':\n"
                f"  URL: {remote_url}"
            )

        except ValueError as e:
            return f"Error: {str(e)}"
        except SecurityError as e:
            return f"Security Error: {str(e)}"
        except Exception as e:
            logger.error(f"Error adding remote: {e}", exc_info=True)
            return f"Error adding remote: {str(e)}"

    def remove_remote(
        self,
        service: Annotated[
            str,
            Field(
                description="Service name (e.g., 'partition', 'legal', 'storage'). "
                "This identifies which repository in repos/ to remove remote from."
            ),
        ],
        remote_name: Annotated[
            str,
            Field(description="Name of the remote to remove (e.g., 'upstream', 'gitlab')."),
        ],
    ) -> str:
        """
        Remove a remote from a git repository.

        Includes safety warnings when removing 'origin' remote.
        All operations are restricted to the repos/ directory sandbox.

        Args:
            service: Service name to remove remote from
            remote_name: Name of the remote to remove

        Returns:
            Formatted string with operation results
        """
        try:
            # Get and validate repository path
            repo_path = self._get_repo_path(service)

            # Validate it's a git repository
            is_valid, error = self._validate_repository(repo_path)
            if not is_valid:
                return f"Error: {error}"

            # Validate remote name
            remote_name = remote_name.strip()
            if not remote_name:
                return "Error: Remote name cannot be empty"

            # Check if remote exists
            returncode, stdout, stderr = self._execute_git_command(
                repo_path, ["git", "remote", "get-url", remote_name]
            )

            if returncode != 0:
                return f"Error: Remote '{remote_name}' does not exist in repository '{service}'."

            remote_url = stdout.strip()

            # Safety warning for removing 'origin'
            warning = ""
            if remote_name == "origin":
                # Check if there are tracking branches
                returncode, stdout, stderr = self._execute_git_command(
                    repo_path, ["git", "branch", "-vv"]
                )
                if returncode == 0 and "origin/" in stdout:
                    warning = (
                        "\nWARNING: You are removing the 'origin' remote which has tracking branches.\n"
                        "This may affect your ability to push/pull.\n\n"
                    )

            # Remove the remote
            returncode, stdout, stderr = self._execute_git_command(
                repo_path, ["git", "remote", "remove", remote_name]
            )

            if returncode != 0:
                return f"Error removing remote: {stderr}"

            return (
                f"{warning}"
                f"Successfully removed remote '{remote_name}' from repository '{service}'.\n"
                f"  (URL was: {remote_url})"
            )

        except ValueError as e:
            return f"Error: {str(e)}"
        except SecurityError as e:
            return f"Security Error: {str(e)}"
        except Exception as e:
            logger.error(f"Error removing remote: {e}", exc_info=True)
            return f"Error removing remote: {str(e)}"

    def configure_upstream_remote(
        self,
        service: Annotated[
            str,
            Field(
                description="Service name (e.g., 'partition', 'legal', 'storage'). "
                "This identifies which repository to configure upstream for."
            ),
        ],
        remote_name: Annotated[
            str,
            Field(description="Name for the upstream remote (default: 'upstream')"),
        ] = "upstream",
        fetch_after_add: Annotated[
            bool,
            Field(description="Whether to fetch from upstream after adding (default: True)"),
        ] = True,
    ) -> str:
        """
        Automatically configure upstream remote from GitHub repository variable.

        This orchestrates multiple operations:
        1. Retrieves UPSTREAM_REPO_URL from GitHub Actions repository variables
        2. Validates the URL format
        3. Adds the remote if not already present
        4. Optionally fetches from the upstream to verify connectivity

        This enables GitHub forks to maintain connections with their GitLab upstream sources.

        Args:
            service: Service name to configure upstream for
            remote_name: Name for the upstream remote (default: 'upstream')
            fetch_after_add: Whether to fetch after adding remote

        Returns:
            Formatted string with configuration results
        """
        try:
            # Get and validate repository path
            repo_path = self._get_repo_path(service)

            # Validate it's a git repository
            is_valid, error = self._validate_repository(repo_path)
            if not is_valid:
                return f"Error: {error}"

            output_lines = [f"Configuring upstream remote for '{service}'...\n\n"]

            # Import RepositoryVariableTools to get UPSTREAM_REPO_URL
            from agent.github.variables import RepositoryVariableTools

            variables_tool = RepositoryVariableTools(self.config)

            # Get UPSTREAM_REPO_URL variable
            result = variables_tool.get_repository_variable(service, "UPSTREAM_REPO_URL")

            # Parse the result to extract the URL
            if "Error" in result or "not found" in result:
                output_lines.append(f"Failed to retrieve UPSTREAM_REPO_URL:\n{result}\n\n")
                output_lines.append(
                    "To configure upstream manually, use:\n"
                    f"  add_remote(service='{service}', remote_name='{remote_name}', remote_url='<url>')"
                )
                return "".join(output_lines)

            # Extract URL from result (format: "UPSTREAM_REPO_URL: <url>")
            if ":" in result:
                upstream_url = result.split(":", 1)[1].strip()
            else:
                return f"Error: Unexpected format from variable retrieval: {result}"

            output_lines.append(f"Retrieved UPSTREAM_REPO_URL: {upstream_url}\n\n")

            # Validate URL format
            if not (
                upstream_url.startswith("http://")
                or upstream_url.startswith("https://")
                or upstream_url.startswith("git@")
                or upstream_url.startswith("ssh://")
            ):
                return (
                    f"Error: Invalid upstream URL format: {upstream_url}\n"
                    "URL must start with http://, https://, ssh://, or git@"
                )

            # Check if remote already exists
            returncode, stdout, stderr = self._execute_git_command(
                repo_path, ["git", "remote", "get-url", remote_name]
            )

            if returncode == 0:
                existing_url = stdout.strip()
                if existing_url == upstream_url:
                    output_lines.append(
                        f"Remote '{remote_name}' is already configured with the correct URL.\n"
                        f"  URL: {existing_url}\n"
                    )
                    # Still fetch if requested
                    if fetch_after_add:
                        output_lines.append(f"\nFetching from '{remote_name}'...\n")
                        returncode, stdout, stderr = self._execute_git_command(
                            repo_path, ["git", "fetch", remote_name], timeout=60
                        )
                        if returncode == 0:
                            output_lines.append("Fetch successful.\n")
                        else:
                            output_lines.append(f"Fetch failed: {stderr}\n")
                    return "".join(output_lines)
                else:
                    output_lines.append(
                        f"WARNING: Remote '{remote_name}' exists but with a different URL:\n"
                        f"  Existing: {existing_url}\n"
                        f"  Expected: {upstream_url}\n\n"
                        f"Manual intervention required. You can:\n"
                        f"  1. Remove the existing remote: remove_remote(service='{service}', remote_name='{remote_name}')\n"
                        f"  2. Add upstream with a different name: add_remote(...)\n"
                    )
                    return "".join(output_lines)

            # Add the remote
            output_lines.append(f"Adding remote '{remote_name}'...\n")
            returncode, stdout, stderr = self._execute_git_command(
                repo_path, ["git", "remote", "add", remote_name, upstream_url]
            )

            if returncode != 0:
                return f"Error adding remote: {stderr}"

            output_lines.append(f"Successfully added remote '{remote_name}'.\n")

            # Fetch if requested
            if fetch_after_add:
                output_lines.append(f"\nFetching from '{remote_name}'...\n")
                returncode, stdout, stderr = self._execute_git_command(
                    repo_path, ["git", "fetch", remote_name], timeout=60
                )
                if returncode == 0:
                    output_lines.append("Fetch successful.\n")
                else:
                    output_lines.append(f"WARNING: Fetch failed: {stderr}\n")
                    output_lines.append("Remote was added but may not be accessible.\n")

            output_lines.append(
                f"\nUpstream remote configured for '{service}':\n"
                f"  Remote: {remote_name}\n"
                f"  URL: {upstream_url}\n"
            )

            return "".join(output_lines)

        except ValueError as e:
            return f"Error: {str(e)}"
        except SecurityError as e:
            return f"Security Error: {str(e)}"
        except Exception as e:
            logger.error(f"Error configuring upstream remote: {e}", exc_info=True)
            return f"Error configuring upstream remote: {str(e)}"

    def configure_all_upstream_remotes(
        self,
        remote_name: Annotated[
            str,
            Field(description="Name for the upstream remote (default: 'upstream')"),
        ] = "upstream",
        fetch_after_add: Annotated[
            bool,
            Field(
                description="Whether to fetch from upstream after adding (default: False for batch)"
            ),
        ] = False,
    ) -> str:
        """
        Configure upstream remotes for all local repositories.

        Batch operation that iterates through all repositories in repos/ directory
        and attempts to configure upstream for each one.

        Args:
            remote_name: Name for the upstream remote (default: 'upstream')
            fetch_after_add: Whether to fetch after adding (default: False to speed up batch)

        Returns:
            Summary of batch configuration results
        """
        try:
            # Check if repos directory exists
            if not self.repos_dir.exists():
                return (
                    "No repositories found. The repos/ directory does not exist.\n"
                    "Use the fork workflow to clone repositories first."
                )

            # Find all subdirectories in repos/
            subdirs = [d for d in self.repos_dir.iterdir() if d.is_dir()]

            if not subdirs:
                return (
                    f"No repositories found in {self.repos_dir}\n"
                    "Use the fork workflow to clone repositories first."
                )

            output_lines = ["Configuring upstream remotes for all local repositories...\n\n"]

            successes = []
            failures = []
            skipped = []

            for repo_dir in subdirs:
                service = repo_dir.name

                # Validate path is sandboxed
                try:
                    self._validate_repo_path_is_sandboxed(repo_dir)
                except SecurityError:
                    logger.warning(f"Skipping directory outside sandbox: {repo_dir}")
                    skipped.append((service, "Outside sandbox"))
                    continue

                # Check if it's a valid git repository
                is_valid, error = self._validate_repository(repo_dir)
                if not is_valid:
                    skipped.append((service, "Not a git repository"))
                    continue

                # Attempt to configure upstream
                output_lines.append(f"Processing '{service}'...\n")
                result = self.configure_upstream_remote(service, remote_name, fetch_after_add)

                # Determine success/failure
                if "Error" in result or "Failed" in result or "WARNING" in result:
                    # Extract first line of error for summary
                    error_summary = result.split("\n")[0]
                    failures.append((service, error_summary))
                    output_lines.append("  FAILED\n\n")
                elif "already configured" in result:
                    successes.append((service, "Already configured"))
                    output_lines.append("  Already configured\n\n")
                else:
                    successes.append((service, "Configured successfully"))
                    output_lines.append("  SUCCESS\n\n")

            # Summary
            output_lines.append("=" * 60 + "\n")
            output_lines.append("BATCH CONFIGURATION SUMMARY\n")
            output_lines.append("=" * 60 + "\n\n")

            total = len(subdirs)
            output_lines.append(f"Total repositories processed: {total}\n")
            output_lines.append(f"  Successful: {len(successes)}\n")
            output_lines.append(f"  Failed: {len(failures)}\n")
            output_lines.append(f"  Skipped: {len(skipped)}\n\n")

            if successes:
                output_lines.append("Successful configurations:\n")
                for service, status in successes:
                    output_lines.append(f"  ✓ {service}: {status}\n")
                output_lines.append("\n")

            if failures:
                output_lines.append("Failed configurations:\n")
                for service, error in failures:
                    output_lines.append(f"  ✗ {service}: {error}\n")
                output_lines.append("\n")

            if skipped:
                output_lines.append("Skipped:\n")
                for service, reason in skipped:
                    output_lines.append(f"  - {service}: {reason}\n")
                output_lines.append("\n")

            return "".join(output_lines)

        except Exception as e:
            logger.error(f"Error in batch upstream configuration: {e}", exc_info=True)
            return f"Error in batch upstream configuration: {str(e)}"
