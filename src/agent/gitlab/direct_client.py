"""Direct GitLab API client for fast status gathering without AI prompts."""

import asyncio
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

import gitlab
from gitlab.exceptions import GitlabError

from agent.config import AgentConfig

logger = logging.getLogger(__name__)

# Provider name to GitLab label mapping
# Maps logical provider names (used in CLI) to actual GitLab label names
PROVIDER_LABEL_MAPPING = {
    "Core": ["Common Code", "Core"],  # Core maps to "Common Code" label (with fallback to "Core")
    "Azure": ["Azure"],
    "AWS": ["AWS"],
    "GCP": ["GCP"],
    "IBM": ["IBM"],
}


class GitLabDirectClient:
    """
    Direct async client for GitLab API calls.

    Provides fast, reliable data gathering without AI prompts.
    Uses python-gitlab library with async/await for parallel API calls.
    """

    def __init__(self, config: AgentConfig):
        """
        Initialize GitLab direct client.

        Args:
            config: Agent configuration with GitLab settings
        """
        self.config = config

        # All OSDU services use community.opengroup.org
        gitlab_url = "https://community.opengroup.org"

        # Initialize GitLab client
        if config.gitlab_token:
            self.gitlab = gitlab.Gitlab(
                url=gitlab_url,
                private_token=config.gitlab_token,
            )
            try:
                self.gitlab.auth()
                logger.info(f"Authenticated to {gitlab_url}")
            except GitlabError as e:
                logger.warning(f"GitLab authentication warning: {e}")
        else:
            # Try without authentication (public projects only)
            self.gitlab = gitlab.Gitlab(url=gitlab_url)
            logger.info(f"Using {gitlab_url} without authentication")

    async def get_all_status(self, services: List[str], providers: List[str]) -> Dict[str, Any]:
        """
        Get GitLab status for all services in parallel.

        Args:
            services: List of service names
            providers: List of provider labels to filter by

        Returns:
            Dictionary with structure matching StatusResponse model
        """
        # Create tasks for all services
        tasks = [self._get_service_status(service, providers) for service in services]

        # Run all service queries in parallel
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Build response structure
        projects = {}
        for service, result in zip(services, results):
            if isinstance(result, Exception):
                logger.error(f"Error getting status for {service}: {result}")
                projects[service] = {"error": str(result)}
            else:
                projects[service] = result  # type: ignore[assignment]

        return {"timestamp": datetime.utcnow().isoformat() + "Z", "projects": projects}

    async def _get_service_status(self, service: str, providers: List[str]) -> Dict[str, Any]:
        """
        Get status for a single service.

        Args:
            service: Service name (e.g., "partition")
            providers: Provider labels to filter by

        Returns:
            Service status dictionary
        """
        # Get upstream GitLab URL from GitHub variable
        upstream_url = await self._get_upstream_url(service)
        if not upstream_url:
            return {"error": "No upstream URL found"}

        # Parse GitLab project path from URL
        project_path = self._parse_project_path(upstream_url)
        if not project_path:
            return {"error": f"Invalid upstream URL: {upstream_url}"}

        try:
            # Get GitLab project
            project = await asyncio.to_thread(self.gitlab.projects.get, project_path)

            # Fetch issues and MRs in parallel
            issues_task = self._get_issues(project, providers)
            mrs_task = self._get_merge_requests(project, providers)

            issues_data, mrs_data = await asyncio.gather(issues_task, mrs_task)

            return {"upstream_url": upstream_url, "issues": issues_data, "merge_requests": mrs_data}

        except GitlabError as e:
            logger.error(f"GitLab API error for {service}: {e}")
            return {"error": f"GitLab API error: {str(e)}"}

    async def _get_upstream_url(self, service: str) -> Optional[str]:
        """
        Get upstream GitLab URL from GitHub repository variable.

        Args:
            service: Service name

        Returns:
            Upstream GitLab URL or None
        """
        repo = f"{self.config.organization}/{service}"
        cmd = ["gh", "api", f"repos/{repo}/actions/variables/UPSTREAM_REPO_URL", "--jq", ".value"]

        try:
            result = await asyncio.create_subprocess_exec(
                *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL
            )
            stdout, _ = await result.communicate()

            if result.returncode == 0:
                url = stdout.decode().strip()
                # Remove .git suffix if present
                return url.rstrip(".git") if url else None

        except Exception as e:
            logger.error(f"Error getting upstream URL for {service}: {e}")

        return None

    def _parse_project_path(self, upstream_url: str) -> Optional[str]:
        """
        Parse GitLab project path from upstream URL.

        Args:
            upstream_url: Full GitLab URL

        Returns:
            Project path (e.g., "osdu/platform/system/partition")
        """
        try:
            parsed = urlparse(upstream_url)
            # Remove leading slash and .git suffix
            path = parsed.path.lstrip("/").rstrip(".git")
            return path
        except Exception as e:
            logger.error(f"Error parsing project path from {upstream_url}: {e}")
            return None

    async def _get_issues(self, project: Any, providers: List[str]) -> Dict[str, Any]:
        """
        Get issues filtered by provider labels.

        Args:
            project: GitLab project object
            providers: Provider labels to filter by

        Returns:
            Issues data dictionary
        """
        all_issues = []
        seen_iids = set()

        # Query for each provider label
        for provider in providers:
            try:
                # Get mapped labels for this provider (or use provider name if no mapping)
                mapped_labels = PROVIDER_LABEL_MAPPING.get(provider, [provider])

                # Try each mapped label
                for label_name in mapped_labels:
                    # Try different case variants (GitLab labels are case-sensitive)
                    for label_variant in [label_name, label_name.capitalize(), label_name.upper()]:
                        issues = await asyncio.to_thread(
                            project.issues.list, labels=[label_variant], state="opened", per_page=10
                        )

                        # Add issues, avoiding duplicates
                        for issue in issues:
                            if issue.iid not in seen_iids:
                                seen_iids.add(issue.iid)
                                all_issues.append(self._format_issue(issue))

                        if issues:  # Found issues with this label variant
                            break

                    if issues:  # Found issues with this mapped label
                        break

            except GitlabError as e:
                logger.warning(f"Error fetching issues for label {provider}: {e}")

        return {"count": len(all_issues), "items": all_issues}

    async def _get_merge_requests(self, project: Any, providers: List[str]) -> Dict[str, Any]:
        """
        Get merge requests filtered by provider labels, with pipelines.

        Args:
            project: GitLab project object
            providers: Provider labels to filter by

        Returns:
            Merge requests data dictionary
        """
        all_mrs = []
        seen_iids = set()

        # Query for each provider label
        for provider in providers:
            try:
                # Get mapped labels for this provider (or use provider name if no mapping)
                mapped_labels = PROVIDER_LABEL_MAPPING.get(provider, [provider])

                # Try each mapped label
                for label_name in mapped_labels:
                    # Try different case variants (GitLab labels are case-sensitive)
                    for label_variant in [label_name, label_name.capitalize(), label_name.upper()]:
                        mrs = await asyncio.to_thread(
                            project.mergerequests.list,
                            labels=[label_variant],
                            state="opened",
                            per_page=10,
                        )

                        # Add MRs, avoiding duplicates
                        for mr in mrs:
                            if mr.iid not in seen_iids:
                                seen_iids.add(mr.iid)
                                mr_data = self._format_merge_request(mr)

                                # Fetch pipelines for this MR
                                mr_data["pipelines"] = await self._get_mr_pipelines(project, mr)

                                all_mrs.append(mr_data)

                        if mrs:  # Found MRs with this label variant
                            break

                    if mrs:  # Found MRs with this mapped label
                        break

            except GitlabError as e:
                logger.warning(f"Error fetching MRs for label {provider}: {e}")

        return {"count": len(all_mrs), "items": all_mrs}

    async def _get_mr_pipelines(self, project: Any, mr: Any) -> List[Dict[str, Any]]:
        """
        Get pipelines for a merge request.

        Args:
            project: GitLab project object
            mr: Merge request object

        Returns:
            List of pipeline dictionaries
        """
        try:
            # Get pipelines for the MR's source branch
            pipelines = await asyncio.to_thread(
                project.pipelines.list,
                ref=mr.source_branch,
                per_page=10,
                order_by="updated_at",
                sort="desc",
            )

            pipeline_data = []
            for pipeline in pipelines[:5]:  # Limit to 5 most recent
                p_data = self._format_pipeline(pipeline)

                # If pipeline failed, get jobs
                if pipeline.status == "failed":
                    p_data["jobs"] = await self._get_pipeline_jobs(project, pipeline)

                pipeline_data.append(p_data)

            return pipeline_data

        except GitlabError as e:
            logger.warning(f"Error fetching pipelines for MR !{mr.iid}: {e}")
            return []

    async def _get_pipeline_jobs(self, project: Any, pipeline: Any) -> List[Dict[str, Any]]:
        """
        Get jobs for a failed pipeline, including downstream jobs.

        Args:
            project: GitLab project object
            pipeline: Pipeline object

        Returns:
            List of job dictionaries (parent + downstream)
        """
        try:
            # Get parent pipeline jobs
            jobs = await asyncio.to_thread(pipeline.jobs.list, per_page=100)

            job_data = [self._format_job(job) for job in jobs]

            # Check if there's a trigger job
            has_trigger = any(job.get("name", "").startswith("trigger-") for job in job_data)

            if has_trigger:
                # Get downstream pipeline jobs
                downstream_jobs = await self._get_downstream_jobs(project, pipeline)
                job_data.extend(downstream_jobs)

            return job_data

        except GitlabError as e:
            logger.warning(f"Error fetching jobs for pipeline {pipeline.id}: {e}")
            return []

    async def _get_downstream_jobs(
        self, project: Any, parent_pipeline: Any
    ) -> List[Dict[str, Any]]:
        """
        Get jobs from downstream pipeline (triggered by parent).

        Args:
            project: GitLab project object
            parent_pipeline: Parent pipeline object

        Returns:
            List of downstream job dictionaries
        """
        try:
            # Find downstream pipelines by matching SHA
            downstream_pipelines = await asyncio.to_thread(
                project.pipelines.list, sha=parent_pipeline.sha, source="pipeline", per_page=5
            )

            if not downstream_pipelines:
                return []

            # Get jobs from the first downstream pipeline
            downstream = downstream_pipelines[0]
            jobs = await asyncio.to_thread(downstream.jobs.list, per_page=100)

            # Format jobs and mark as downstream
            job_data = []
            for job in jobs:
                j_data = self._format_job(job)
                j_data["is_downstream"] = True
                j_data["downstream_pipeline_id"] = downstream.id
                job_data.append(j_data)

            return job_data

        except GitlabError as e:
            logger.warning(f"Error fetching downstream jobs: {e}")
            return []

    def _format_issue(self, issue: Any) -> Dict[str, Any]:
        """Format GitLab issue to dictionary."""
        return {
            "iid": issue.iid,
            "title": issue.title,
            "labels": issue.labels if hasattr(issue, "labels") else [],
            "state": issue.state,
            "assignees": [
                a.get("username", "unknown")
                for a in (issue.assignees if hasattr(issue, "assignees") else [])
            ],
            "author": (
                issue.author.get("username", "unknown")
                if hasattr(issue, "author") and issue.author
                else "unknown"
            ),
            "created_at": issue.created_at,
            "web_url": issue.web_url,
        }

    def _format_merge_request(self, mr: Any) -> Dict[str, Any]:
        """Format GitLab merge request to dictionary."""
        return {
            "iid": mr.iid,
            "title": mr.title,
            "labels": mr.labels if hasattr(mr, "labels") else [],
            "state": mr.state,
            "draft": mr.draft if hasattr(mr, "draft") else False,
            "source_branch": mr.source_branch,
            "target_branch": mr.target_branch,
            "author": (
                mr.author.get("username", "unknown")
                if hasattr(mr, "author") and mr.author
                else "unknown"
            ),
            "created_at": mr.created_at,
            "web_url": mr.web_url,
        }

    def _format_pipeline(self, pipeline: Any) -> Dict[str, Any]:
        """Format GitLab pipeline to dictionary."""
        return {
            "id": pipeline.id,
            "status": pipeline.status,
            "ref": pipeline.ref,
            "sha": pipeline.sha if hasattr(pipeline, "sha") else "unknown",
            "created_at": pipeline.created_at if hasattr(pipeline, "created_at") else None,
            "duration": pipeline.duration if hasattr(pipeline, "duration") else None,
            "web_url": pipeline.web_url,
        }

    def _format_job(self, job: Any) -> Dict[str, Any]:
        """Format GitLab job to dictionary."""
        return {
            "id": job.id,
            "name": job.name,
            "stage": job.stage,
            "status": job.status,
            "allow_failure": job.allow_failure if hasattr(job, "allow_failure") else False,
            "duration": job.duration if hasattr(job, "duration") else None,
            "web_url": job.web_url if hasattr(job, "web_url") else None,
        }

    # ========== Contribution Analysis Methods ==========

    async def get_merge_requests_for_period(
        self, project_path: str, start_date: datetime, end_date: datetime
    ) -> List[Dict[str, Any]]:
        """
        Get merge requests for a project within a specific date range.

        Args:
            project_path: GitLab project path (e.g., "osdu/platform/system/partition")
            start_date: Period start date
            end_date: Period end date

        Returns:
            List of formatted merge request dictionaries
        """
        try:
            project = await asyncio.to_thread(self.gitlab.projects.get, project_path)

            # Format dates for GitLab API (ISO 8601)
            start_str = start_date.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
            end_str = end_date.strftime("%Y-%m-%dT%H:%M:%S.%fZ")

            # Fetch merge requests created in the period
            mrs = await asyncio.to_thread(
                project.mergerequests.list,
                created_after=start_str,
                created_before=end_str,
                per_page=100,
                get_all=True,
            )

            return [self._format_merge_request_detailed(mr) for mr in mrs]

        except GitlabError as e:
            logger.error(f"Error fetching MRs for {project_path}: {e}")
            return []

    async def get_merge_request_discussions(
        self, project_path: str, mr_iid: int
    ) -> List[Dict[str, Any]]:
        """
        Get discussions (reviews and comments) for a merge request.

        Args:
            project_path: GitLab project path
            mr_iid: Merge request IID

        Returns:
            List of discussion/comment dictionaries
        """
        try:
            project = await asyncio.to_thread(self.gitlab.projects.get, project_path)
            mr = await asyncio.to_thread(project.mergerequests.get, mr_iid)

            # Fetch discussions
            discussions = await asyncio.to_thread(mr.discussions.list, get_all=True)

            formatted_discussions = []
            for discussion in discussions:
                for note in discussion.attributes.get("notes", []):
                    formatted_discussions.append(
                        {
                            "id": note.get("id"),
                            "author": note.get("author", {}).get("username", "unknown"),
                            "body": note.get("body", ""),
                            "created_at": note.get("created_at"),
                            "type": note.get("type", "DiscussionNote"),
                            "system": note.get("system", False),
                        }
                    )

            return formatted_discussions

        except GitlabError as e:
            logger.warning(f"Error fetching discussions for MR !{mr_iid}: {e}")
            return []

    async def get_merge_request_approvals(self, project_path: str, mr_iid: int) -> List[str]:
        """
        Get approvals for a merge request.

        Args:
            project_path: GitLab project path
            mr_iid: Merge request IID

        Returns:
            List of approver usernames
        """
        try:
            project = await asyncio.to_thread(self.gitlab.projects.get, project_path)
            mr = await asyncio.to_thread(project.mergerequests.get, mr_iid)

            # Get approvals - this fetches the approval state
            approvals = await asyncio.to_thread(mr.approvals.get)

            # Extract approved_by users
            approved_by = []
            if hasattr(approvals, "approved_by") and approvals.approved_by:
                for approver in approvals.approved_by:
                    username = approver.get("user", {}).get("username", "unknown")
                    if username != "unknown":
                        approved_by.append(username)

            return approved_by

        except (GitlabError, AttributeError) as e:
            # Some projects may not have approval rules configured
            logger.debug(f"Could not fetch approvals for MR !{mr_iid}: {e}")
            return []

    async def get_issues_by_labels(
        self, project_path: str, labels: List[str], state: str = "all"
    ) -> List[Dict[str, Any]]:
        """
        Get issues filtered by labels.

        Args:
            project_path: GitLab project path
            labels: List of label names to filter by
            state: Issue state ("opened", "closed", "all")

        Returns:
            List of formatted issue dictionaries
        """
        try:
            project = await asyncio.to_thread(self.gitlab.projects.get, project_path)

            # Fetch issues with specified labels
            issues = await asyncio.to_thread(
                project.issues.list, labels=labels, state=state, per_page=100, get_all=True
            )

            return [self._format_issue_detailed(issue) for issue in issues]

        except GitlabError as e:
            logger.error(f"Error fetching issues for {project_path}: {e}")
            return []

    async def get_all_contributors(self, project_path: str) -> List[str]:
        """
        Get all contributors (committers) for a project.

        Args:
            project_path: GitLab project path

        Returns:
            List of contributor usernames
        """
        try:
            project = await asyncio.to_thread(self.gitlab.projects.get, project_path)

            # Fetch repository contributors
            contributors = await asyncio.to_thread(project.repository_contributors, get_all=True)

            return [c.get("name", "unknown") for c in contributors]

        except GitlabError as e:
            logger.warning(f"Error fetching contributors for {project_path}: {e}")
            return []

    def _format_merge_request_detailed(self, mr: Any) -> Dict[str, Any]:
        """Format merge request with additional details for analytics."""
        base_data = self._format_merge_request(mr)
        base_data.update(
            {
                "merged_at": mr.merged_at if hasattr(mr, "merged_at") else None,
                "closed_at": mr.closed_at if hasattr(mr, "closed_at") else None,
                "updated_at": mr.updated_at if hasattr(mr, "updated_at") else None,
                "upvotes": mr.upvotes if hasattr(mr, "upvotes") else 0,
                "downvotes": mr.downvotes if hasattr(mr, "downvotes") else 0,
                "user_notes_count": mr.user_notes_count if hasattr(mr, "user_notes_count") else 0,
                "has_conflicts": mr.has_conflicts if hasattr(mr, "has_conflicts") else False,
                "merge_status": mr.merge_status if hasattr(mr, "merge_status") else "unknown",
            }
        )
        return base_data

    def _format_issue_detailed(self, issue: Any) -> Dict[str, Any]:
        """Format issue with additional details for analytics."""
        base_data = self._format_issue(issue)
        base_data.update(
            {
                "closed_at": issue.closed_at if hasattr(issue, "closed_at") else None,
                "updated_at": issue.updated_at if hasattr(issue, "updated_at") else None,
                "upvotes": issue.upvotes if hasattr(issue, "upvotes") else 0,
                "downvotes": issue.downvotes if hasattr(issue, "downvotes") else 0,
                "user_notes_count": (
                    issue.user_notes_count if hasattr(issue, "user_notes_count") else 0
                ),
            }
        )
        return base_data
