"""
PR Researcher — Live GitHub PR analysis for contribution intelligence.

Fetches recent merged PRs from any GitHub repository to understand:
- Contribution patterns (how code is typically added)
- Reviewer expectations (what reviewers care about)
- Coding conventions (from actual merged code)
- Common PR structures (test requirements, docs, etc.)

Uses GitHub REST API directly (urllib) — no PyGitHub dependency needed.
Requires GITHUB_TOKEN environment variable for authenticated access.
"""

import json
import os
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .logger import get_logger

logger = get_logger("pr_researcher")

# GitHub API base
_API_BASE = "https://api.github.com"


@dataclass
class PRInsight:
    """A single insight extracted from a merged PR."""

    pr_number: int
    title: str
    author: str
    files_changed: int
    additions: int
    deletions: int
    changed_files: List[str] = field(default_factory=list)
    labels: List[str] = field(default_factory=list)
    review_comments_count: int = 0
    # Key patterns extracted
    has_tests: bool = False
    has_docs: bool = False
    has_changelog: bool = False
    # Reviewer feedback themes
    reviewer_themes: List[str] = field(default_factory=list)


@dataclass
class ContributionPattern:
    """Aggregated patterns from analyzing multiple PRs."""

    repo: str = ""
    total_prs_analyzed: int = 0

    # Common PR structure
    avg_files_per_pr: float = 0.0
    avg_additions: float = 0.0
    avg_deletions: float = 0.0

    # Conventions detected
    test_required: bool = False       # Do merged PRs always have tests?
    docs_required: bool = False       # Do merged PRs update docs?
    changelog_required: bool = False  # Do merged PRs update changelog?

    # Common file patterns
    frequently_changed_dirs: List[str] = field(default_factory=list)
    common_labels: List[str] = field(default_factory=list)

    # Naming patterns
    branch_naming: str = ""     # e.g., "feat/", "fix/", "feature-"
    commit_style: str = ""      # e.g., "conventional", "free-form"

    # Active contributors
    top_contributors: List[str] = field(default_factory=list)
    top_reviewers: List[str] = field(default_factory=list)

    # Raw insights for detail
    pr_insights: List[PRInsight] = field(default_factory=list)

    def to_prompt_context(self) -> str:
        """Convert to a concise prompt string for LLM agents."""
        lines = ["## Contribution Patterns"]
        lines.append(f"Based on {self.total_prs_analyzed} recent merged PRs:")

        if self.test_required:
            lines.append("- ✅ Tests are expected with code changes")
        if self.docs_required:
            lines.append("- 📝 Documentation updates are common")
        if self.changelog_required:
            lines.append("- 📋 Changelog updates are expected")

        lines.append(
            f"- Average PR size: +{self.avg_additions:.0f}/-"
            f"{self.avg_deletions:.0f} lines, "
            f"{self.avg_files_per_pr:.1f} files"
        )

        if self.frequently_changed_dirs:
            lines.append(
                f"- Active directories: {', '.join(self.frequently_changed_dirs[:8])}"
            )

        if self.common_labels:
            lines.append(
                f"- Common labels: {', '.join(self.common_labels[:6])}"
            )

        if self.top_contributors:
            lines.append(
                f"- Top contributors: {', '.join(self.top_contributors[:5])}"
            )

        if self.commit_style:
            lines.append(f"- Commit style: {self.commit_style}")

        return "\n".join(lines)


class PRResearcher:
    """Fetch and analyze recent merged PRs from GitHub.

    Designed for interactive use — lightweight, fast, no external deps.

    Usage:
        researcher = PRResearcher()
        patterns = researcher.analyze("owner/repo", limit=20)
        print(patterns.to_prompt_context())
    """

    def __init__(self):
        self.token = os.environ.get("GITHUB_TOKEN", "")
        if not self.token:
            logger.warning(
                "GITHUB_TOKEN not set — PR research will be limited "
                "(60 req/hr vs 5000 req/hr)",
                extra={"agent": "pr_researcher"},
            )

    def _request(self, url: str) -> Optional[Dict[str, Any]]:
        """Make an authenticated GitHub API request."""
        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": "macro-cli",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        try:
            req = Request(url, headers=headers)
            with urlopen(req, timeout=15) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except HTTPError as e:
            if e.code == 403:
                logger.warning(
                    "GitHub API rate limited",
                    extra={"agent": "pr_researcher"},
                )
            elif e.code == 404:
                logger.warning(
                    f"Repository not found: {url}",
                    extra={"agent": "pr_researcher"},
                )
            else:
                logger.warning(
                    f"GitHub API error {e.code}: {e.reason}",
                    extra={"agent": "pr_researcher"},
                )
            return None
        except (URLError, TimeoutError) as e:
            logger.warning(
                f"Network error: {e}",
                extra={"agent": "pr_researcher"},
            )
            return None

    def _request_list(self, url: str) -> List[Dict[str, Any]]:
        """Make request expecting a list response."""
        result = self._request(url)
        if isinstance(result, list):
            return result
        return []

    def fetch_merged_prs(
        self, repo_slug: str, limit: int = 20
    ) -> List[Dict[str, Any]]:
        """Fetch recent merged PRs from a repository.

        Args:
            repo_slug: "owner/repo" format
            limit: Max PRs to fetch (default 20, max 100)

        Returns:
            List of PR data dicts from GitHub API.
        """
        limit = min(limit, 100)
        url = (
            f"{_API_BASE}/repos/{repo_slug}/pulls"
            f"?state=closed&sort=updated&direction=desc"
            f"&per_page={limit}"
        )

        prs = self._request_list(url)

        # Filter to only merged PRs
        return [pr for pr in prs if pr.get("merged_at")]

    def fetch_pr_files(
        self, repo_slug: str, pr_number: int
    ) -> List[Dict[str, Any]]:
        """Fetch files changed in a specific PR."""
        url = (
            f"{_API_BASE}/repos/{repo_slug}/pulls/{pr_number}/files"
            f"?per_page=100"
        )
        return self._request_list(url)

    def fetch_pr_reviews(
        self, repo_slug: str, pr_number: int
    ) -> List[Dict[str, Any]]:
        """Fetch reviews on a specific PR."""
        url = (
            f"{_API_BASE}/repos/{repo_slug}/pulls/{pr_number}/reviews"
        )
        return self._request_list(url)

    def fetch_recent_commits(
        self, repo_slug: str, limit: int = 30
    ) -> List[Dict[str, Any]]:
        """Fetch recent commits to detect commit style."""
        url = (
            f"{_API_BASE}/repos/{repo_slug}/commits"
            f"?per_page={limit}"
        )
        return self._request_list(url)

    def analyze(
        self,
        repo_slug: str,
        limit: int = 20,
        fetch_files: bool = True,
    ) -> ContributionPattern:
        """Analyze contribution patterns for a repository.

        Args:
            repo_slug: "owner/repo" format
            limit: Number of recent merged PRs to analyze
            fetch_files: Whether to fetch file lists (uses more API calls)

        Returns:
            ContributionPattern with aggregated insights.
        """
        pattern = ContributionPattern(repo=repo_slug)

        # Fetch merged PRs
        merged_prs = self.fetch_merged_prs(repo_slug, limit=limit)
        if not merged_prs:
            logger.info(
                f"No merged PRs found for {repo_slug}",
                extra={"agent": "pr_researcher"},
            )
            return pattern

        pattern.total_prs_analyzed = len(merged_prs)

        # Track aggregates
        total_additions = 0
        total_deletions = 0
        total_files = 0
        dir_counts: Dict[str, int] = {}
        label_counts: Dict[str, int] = {}
        author_counts: Dict[str, int] = {}
        reviewer_counts: Dict[str, int] = {}
        prs_with_tests = 0
        prs_with_docs = 0
        prs_with_changelog = 0

        for pr_data in merged_prs:
            pr_num = pr_data.get("number", 0)
            title = pr_data.get("title", "")
            author = (pr_data.get("user") or {}).get("login", "unknown")
            labels = [
                lbl.get("name", "")
                for lbl in pr_data.get("labels", [])
            ]

            insight = PRInsight(
                pr_number=pr_num,
                title=title,
                author=author,
                files_changed=0,
                additions=0,
                deletions=0,
                labels=labels,
            )

            # Count labels
            for label in labels:
                label_counts[label] = label_counts.get(label, 0) + 1

            # Count authors
            author_counts[author] = author_counts.get(author, 0) + 1

            # Fetch file details if enabled
            if fetch_files:
                files = self.fetch_pr_files(repo_slug, pr_num)
                insight.files_changed = len(files)

                for f in files:
                    filename = f.get("filename", "")
                    insight.changed_files.append(filename)
                    insight.additions += f.get("additions", 0)
                    insight.deletions += f.get("deletions", 0)

                    # Track directories
                    parts = filename.split("/")
                    if len(parts) > 1:
                        top_dir = parts[0]
                        dir_counts[top_dir] = dir_counts.get(top_dir, 0) + 1

                    # Detect test files
                    if "test" in filename.lower() or "spec" in filename.lower():
                        insight.has_tests = True

                    # Detect docs
                    if (
                        filename.lower().endswith(".md")
                        or "docs/" in filename.lower()
                        or "doc/" in filename.lower()
                    ):
                        insight.has_docs = True

                    # Detect changelog
                    if "changelog" in filename.lower():
                        insight.has_changelog = True

                total_additions += insight.additions
                total_deletions += insight.deletions
                total_files += insight.files_changed

            if insight.has_tests:
                prs_with_tests += 1
            if insight.has_docs:
                prs_with_docs += 1
            if insight.has_changelog:
                prs_with_changelog += 1

            # Fetch reviews for top 5 PRs only (rate limit)
            if len(pattern.pr_insights) < 5:
                reviews = self.fetch_pr_reviews(repo_slug, pr_num)
                for review in reviews:
                    reviewer = (review.get("user") or {}).get("login", "")
                    if reviewer and reviewer != author:
                        reviewer_counts[reviewer] = (
                            reviewer_counts.get(reviewer, 0) + 1
                        )
                        insight.review_comments_count += 1

            pattern.pr_insights.append(insight)

        # Compute aggregates
        n = len(merged_prs)
        if n > 0:
            pattern.avg_additions = total_additions / n
            pattern.avg_deletions = total_deletions / n
            pattern.avg_files_per_pr = total_files / n

        # Convention detection (>60% threshold)
        threshold = 0.6
        if n > 0:
            pattern.test_required = (prs_with_tests / n) >= threshold
            pattern.docs_required = (prs_with_docs / n) >= threshold
            pattern.changelog_required = (prs_with_changelog / n) >= threshold

        # Top directories
        pattern.frequently_changed_dirs = sorted(
            dir_counts, key=dir_counts.get, reverse=True
        )[:10]

        # Top labels
        pattern.common_labels = sorted(
            label_counts, key=label_counts.get, reverse=True
        )[:8]

        # Top contributors/reviewers
        pattern.top_contributors = sorted(
            author_counts, key=author_counts.get, reverse=True
        )[:5]
        pattern.top_reviewers = sorted(
            reviewer_counts, key=reviewer_counts.get, reverse=True
        )[:5]

        # Detect commit style
        pattern.commit_style = self._detect_commit_style(repo_slug)

        logger.info(
            f"Analyzed {n} PRs for {repo_slug}: "
            f"tests={'required' if pattern.test_required else 'optional'}, "
            f"avg size={pattern.avg_additions:.0f}+/{pattern.avg_deletions:.0f}-",
            extra={"agent": "pr_researcher"},
        )

        return pattern

    def _detect_commit_style(self, repo_slug: str) -> str:
        """Detect if the repo uses conventional commits."""
        commits = self.fetch_recent_commits(repo_slug, limit=20)
        if not commits:
            return "unknown"

        conventional_count = 0
        conventional_pattern = re.compile(
            r"^(feat|fix|docs|style|refactor|test|chore|build|ci|perf|revert)"
            r"(\(.+\))?!?:\s"
        )

        for commit in commits:
            msg = (commit.get("commit") or {}).get("message", "")
            if conventional_pattern.match(msg):
                conventional_count += 1

        ratio = conventional_count / len(commits) if commits else 0
        if ratio >= 0.6:
            return "conventional commits"
        elif ratio >= 0.3:
            return "partially conventional"
        return "free-form"
