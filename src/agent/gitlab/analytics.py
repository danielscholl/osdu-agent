"""GitLab contribution analysis engine for reporting."""

import asyncio
import logging
from collections import defaultdict
from datetime import datetime
from typing import Dict, List, Optional, Tuple, cast

from agent.config import AgentConfig
from agent.gitlab.direct_client import GitLabDirectClient
from agent.gitlab.models import ADRStats, ContributionStats, PeriodStats, ProjectStats

logger = logging.getLogger(__name__)

# ADR label variants used in OSDU
ADR_LABELS = ["ADR", "ADR::Proposed", "ADR::Approved", "Issue::ADR"]


class GitLabContributionAnalyzer:
    """Analyzer for GitLab contribution patterns and ADR tracking."""

    def __init__(self, config: AgentConfig, gitlab_client: GitLabDirectClient):
        """
        Initialize analyzer with configuration and GitLab client.

        Args:
            config: Agent configuration
            gitlab_client: GitLab direct API client
        """
        self.config = config
        self.client = gitlab_client

    async def analyze_contributions(
        self, project_paths: List[str], start_date: datetime, end_date: datetime
    ) -> PeriodStats:
        """
        Analyze contributions across multiple projects for a time period.

        Args:
            project_paths: List of GitLab project paths
            start_date: Period start date
            end_date: Period end date

        Returns:
            PeriodStats with aggregated contribution data
        """
        # Calculate days in period
        days = (end_date - start_date).days

        # Create period stats
        period_stats = PeriodStats(start_date=start_date, end_date=end_date, days=days)

        # Analyze each project in parallel
        tasks = [
            self._analyze_project_contributions(project_path, start_date, end_date)
            for project_path in project_paths
        ]

        project_results = await asyncio.gather(*tasks, return_exceptions=True)

        # Aggregate results
        for project_path, result in zip(project_paths, project_results):
            if isinstance(result, Exception):
                logger.error(f"Error analyzing {project_path}: {result}")
                continue

            # Type narrowing - result is ProjectStats (not BaseException)
            project_stats = cast(ProjectStats, result)
            period_stats.project_breakdown[project_path] = project_stats

            # Aggregate contributions
            period_stats.contributions = self._merge_contribution_stats(
                period_stats.contributions, project_stats.contributions
            )

        # Count unique contributors across all projects
        all_contributors: set[str] = set()
        for project_stats in period_stats.project_breakdown.values():
            all_contributors.update(project_stats.contributions.contributors.keys())
        period_stats.contributions.active_contributors = len(all_contributors)

        return period_stats

    async def _analyze_project_contributions(
        self, project_path: str, start_date: datetime, end_date: datetime
    ) -> ProjectStats:
        """
        Analyze contributions for a single project.

        Args:
            project_path: GitLab project path
            start_date: Period start date
            end_date: Period end date

        Returns:
            ProjectStats with project-specific data
        """
        project_name = project_path.split("/")[-1]
        project_stats = ProjectStats(project_name=project_name, project_path=project_path)

        # Fetch merge requests for period
        mrs = await self.client.get_merge_requests_for_period(project_path, start_date, end_date)

        # Analyze MRs
        contributions = ContributionStats()
        contributors: Dict[str, Dict[str, int]] = defaultdict(
            lambda: {"mrs": 0, "approvals": 0, "comments": 0}
        )

        for mr in mrs:
            contributions.total_mrs += 1

            # Count by state
            state = mr.get("state", "opened")
            if state == "opened":
                contributions.open_mrs += 1
            elif state == "merged":
                contributions.merged_mrs += 1
            elif state == "closed":
                contributions.closed_mrs += 1

            # Track author
            author = mr.get("author", "unknown")
            if author != "unknown":
                contributors[author]["mrs"] += 1

            # Get MR IID
            mr_iid = mr.get("iid")
            if not mr_iid:
                continue

            # Fetch approvals (formal GitLab approvals - identifies maintainers)
            approved_by = await self.client.get_merge_request_approvals(project_path, mr_iid)
            for approver_username in approved_by:
                if approver_username and approver_username != "unknown":
                    contributions.approvals += 1
                    contributors[approver_username]["approvals"] += 1

            # Fetch discussions for comment tracking
            discussions = await self.client.get_merge_request_discussions(project_path, mr_iid)

            for discussion in discussions:
                # Skip system notes
                if discussion.get("system", False):
                    continue

                discussion_author = discussion.get("author", "unknown")
                if discussion_author == "unknown":
                    continue

                # Count comments (engagement in code review discussions)
                contributions.comments += 1
                contributors[discussion_author]["comments"] += 1

        contributions.contributors = dict(contributors)
        contributions.active_contributors = len(contributors)
        project_stats.contributions = contributions

        return project_stats

    async def analyze_adrs(
        self,
        project_paths: List[str],
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> ADRStats:
        """
        Analyze Architecture Decision Records across projects.

        Args:
            project_paths: List of GitLab project paths
            start_date: Optional filter for ADRs created after this date
            end_date: Optional filter for ADRs created before this date

        Returns:
            ADRStats with ADR analysis
        """
        adr_stats = ADRStats()
        seen_adr_iids: set = set()
        participants: set = set()

        # Analyze each project in parallel
        tasks = [self._analyze_project_adrs(project_path) for project_path in project_paths]

        project_results = await asyncio.gather(*tasks, return_exceptions=True)

        # Aggregate results
        for result in project_results:
            if isinstance(result, Exception):
                logger.error(f"Error analyzing ADRs: {result}")
                continue

            # Type narrowing - result is List[Dict] (not BaseException)
            adr_list = cast(List[Dict], result)
            for adr in adr_list:
                # Deduplicate by IID
                adr_iid = adr.get("iid")
                if adr_iid in seen_adr_iids:
                    continue
                seen_adr_iids.add(adr_iid)

                # Filter by date if specified
                created_at = adr.get("created_at")
                if created_at:
                    try:
                        created_date = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                        if start_date and created_date < start_date:
                            continue
                        if end_date and created_date > end_date:
                            continue
                    except (ValueError, AttributeError):
                        # Ignore ADRs with malformed or missing created_at date
                        logger.debug(
                            f"Skipping ADR {adr_iid} with invalid created_at: {created_at}"
                        )

                adr_stats.total_adrs += 1

                # Count by state
                labels = adr.get("labels", [])
                state = adr.get("state", "opened")

                if state == "opened" or "ADR::Proposed" in labels:
                    adr_stats.open_adrs += 1
                if "ADR::Approved" in labels or state == "closed":
                    adr_stats.approved_adrs += 1

                # Track participants
                author = adr.get("author")
                if author:
                    participants.add(author)
                    adr_stats.authored_count += 1

                # Track assignees as participants
                assignees = adr.get("assignees", [])
                participants.update(assignees)

                # Count comments
                adr_stats.comments_count += adr.get("user_notes_count", 0)

                # Store ADR details
                adr_stats.adr_details.append(
                    {
                        "iid": adr_iid,
                        "title": adr.get("title", ""),
                        "state": state,
                        "labels": labels,
                        "author": author,
                        "created_at": created_at,
                        "web_url": adr.get("web_url", ""),
                    }
                )

        adr_stats.participants = len(participants)
        return adr_stats

    async def _analyze_project_adrs(self, project_path: str) -> List[Dict]:
        """
        Analyze ADRs for a single project.

        Args:
            project_path: GitLab project path

        Returns:
            List of ADR issue dictionaries
        """
        all_adrs = []

        # Fetch issues with all ADR label variants
        for label in ADR_LABELS:
            issues = await self.client.get_issues_by_labels(project_path, [label], state="all")
            all_adrs.extend(issues)

        return all_adrs

    async def analyze_trends(
        self, project_paths: List[str], periods: List[Tuple[datetime, datetime]]
    ) -> List[PeriodStats]:
        """
        Analyze contribution trends across multiple time periods.

        Args:
            project_paths: List of GitLab project paths
            periods: List of (start_date, end_date) tuples for each period

        Returns:
            List of PeriodStats, one for each period
        """
        # Analyze each period in parallel
        tasks = [
            self.analyze_contributions(project_paths, start_date, end_date)
            for start_date, end_date in periods
        ]

        period_results = await asyncio.gather(*tasks, return_exceptions=True)

        # Filter out errors
        valid_periods: List[PeriodStats] = []
        for i, result in enumerate(period_results):
            if isinstance(result, Exception):
                logger.error(f"Error analyzing period {i}: {result}")
                continue
            # Type narrowing - result is PeriodStats (not BaseException)
            period_stat = cast(PeriodStats, result)
            valid_periods.append(period_stat)

        return valid_periods

    def _merge_contribution_stats(
        self, stats1: ContributionStats, stats2: ContributionStats
    ) -> ContributionStats:
        """
        Merge two ContributionStats objects.

        Args:
            stats1: First stats object
            stats2: Second stats object

        Returns:
            Merged ContributionStats
        """
        merged = ContributionStats()
        merged.total_mrs = stats1.total_mrs + stats2.total_mrs
        merged.open_mrs = stats1.open_mrs + stats2.open_mrs
        merged.merged_mrs = stats1.merged_mrs + stats2.merged_mrs
        merged.closed_mrs = stats1.closed_mrs + stats2.closed_mrs
        merged.approvals = stats1.approvals + stats2.approvals
        merged.comments = stats1.comments + stats2.comments

        # Merge contributors
        all_contributors = {**stats1.contributors}
        for username, contrib_stats in stats2.contributors.items():
            if username in all_contributors:
                for key, value in contrib_stats.items():
                    all_contributors[username][key] = all_contributors[username].get(key, 0) + value
            else:
                all_contributors[username] = contrib_stats

        merged.contributors = all_contributors
        merged.active_contributors = len(all_contributors)

        return merged
