"""
GitHub API Client for PR Evolution Extraction.

This module handles all interactions with the GitHub API,
including rate limiting, pagination, and error handling.
"""

import os
import time
from dataclasses import dataclass
from typing import List, Optional, Dict, Any, Iterator
from github import Github, GithubException
from github.PullRequest import PullRequest
from github.PullRequestComment import PullRequestComment
from github.Repository import Repository
from tenacity import retry, stop_after_attempt, wait_exponential

from .config import ExtractionConfig, RepoConfig


@dataclass
class PRReviewComment:
    """A single review comment on a PR."""
    
    id: int
    body: str
    path: str  # File path the comment is on
    line: Optional[int]  # Line number
    original_line: Optional[int]  # Original line (before changes)
    diff_hunk: str  # The code context
    user: str
    created_at: str
    
    def contains_correction(self, patterns: List[str]) -> bool:
        """Check if this comment contains correction logic."""
        body_lower = self.body.lower()
        return any(pattern.lower() in body_lower for pattern in patterns)


@dataclass  
class PRDiff:
    """A file diff from a PR."""
    
    filename: str
    status: str  # added, modified, removed
    additions: int
    deletions: int
    patch: Optional[str]  # The actual diff
    
    @property
    def total_changes(self) -> int:
        return self.additions + self.deletions


@dataclass
class PREvolution:
    """
    The core training data format.
    
    This captures the "evolution" of code:
    Original Code → Reviewer Feedback → Fixed Code
    """
    
    repo: str
    pr_number: int
    pr_title: str
    pr_description: str
    
    # The original code that was submitted
    original_code: str
    
    # The file path
    file_path: str
    
    # The reviewer's feedback (the "lesson")
    reviewer_comment: str
    
    # The fixed code (after addressing feedback)
    fixed_code: Optional[str]
    
    # Categorized lesson learned
    lesson_category: str  # e.g., "error_handling", "security", "architecture"
    
    # Language of the code
    language: str
    
    # Quality score (0-100) - higher = more valuable for training
    quality_score: int = 0
    
    # Flag if the original code had vulnerability patterns
    has_vulnerability: bool = False
    
    def to_jsonl(self) -> Dict[str, Any]:
        """Convert to JSONL format for training."""
        return {
            "repo": self.repo,
            "pr_number": self.pr_number,
            "type": "pr_evolution",
            "file_path": self.file_path,
            "original_code": self.original_code,
            "reviewer_comment": self.reviewer_comment,
            "fixed_code": self.fixed_code,
            "lesson_category": self.lesson_category,
            "language": self.language,
            "quality_score": self.quality_score,
            "has_vulnerability": self.has_vulnerability,
            "metadata": {
                "pr_title": self.pr_title,
                "pr_description": self.pr_description[:500] if self.pr_description else ""
            }
        }


class GitHubClient:
    """
    Client for extracting PR evolution data from GitHub.
    
    Handles:
    - Rate limiting
    - Pagination
    - Error recovery
    - Quality filtering
    """
    
    def __init__(self, config: ExtractionConfig):
        self.config = config
        token = os.environ.get("GITHUB_TOKEN")
        if not token:
            raise ValueError(
                "GITHUB_TOKEN environment variable not set. "
                "Create a token at https://github.com/settings/tokens"
            )
        self.github = Github(token)
        self._check_rate_limit()
    
    def _check_rate_limit(self) -> None:
        """Check and log current rate limit status."""
        rate = self.github.get_rate_limit()
        remaining = rate.core.remaining
        reset_time = rate.core.reset
        
        if remaining < 100:
            wait_seconds = (reset_time - time.time()) + 10
            if wait_seconds > 0:
                print(f"⚠️  Rate limit low ({remaining} remaining). "
                      f"Waiting {wait_seconds:.0f} seconds...")
                time.sleep(wait_seconds)
    
    def get_repo(self, repo_config: RepoConfig) -> Repository:
        """Get a repository object."""
        return self.github.get_repo(repo_config.full_name)
    
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
    def get_merged_prs(
        self, 
        repo: Repository, 
        limit: int = 100
    ) -> Iterator[PullRequest]:
        """
        Get merged PRs from a repository.
        
        Filters for PRs that are likely to contain valuable training data:
        - Merged (not closed without merge)
        - Has review comments
        - Not too small or too large
        """
        self._check_rate_limit()
        
        # Get closed PRs (we'll filter for merged)
        prs = repo.get_pulls(state="closed", sort="updated", direction="desc")
        
        count = 0
        for pr in prs:
            if count >= limit:
                break
            
            # Must be merged
            if not pr.merged:
                continue
            
            # Must have review comments
            if pr.review_comments < self.config.min_review_comments:
                continue
            
            # Check size constraints
            if pr.additions + pr.deletions < self.config.min_lines_changed:
                continue
            if pr.additions + pr.deletions > self.config.max_lines_changed:
                continue
            
            count += 1
            yield pr
    
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
    def get_pr_review_comments(
        self, 
        pr: PullRequest
    ) -> List[PRReviewComment]:
        """Get all review comments on a PR."""
        self._check_rate_limit()
        
        comments = []
        for comment in pr.get_review_comments():
            # Skip bot comments
            if comment.user.type == "Bot":
                continue
            
            comments.append(PRReviewComment(
                id=comment.id,
                body=comment.body,
                path=comment.path,
                line=comment.line,
                original_line=comment.original_line,
                diff_hunk=comment.diff_hunk or "",
                user=comment.user.login,
                created_at=comment.created_at.isoformat()
            ))
        
        return comments
    
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
    def get_pr_files(self, pr: PullRequest) -> List[PRDiff]:
        """Get all file diffs from a PR."""
        self._check_rate_limit()
        
        files = []
        for file in pr.get_files():
            # Filter by extension
            if not any(file.filename.endswith(ext) 
                      for ext in self.config.file_extensions):
                continue
            
            # Filter out excluded patterns
            if any(pattern in file.filename 
                  for pattern in self.config.exclude_patterns):
                continue
            
            files.append(PRDiff(
                filename=file.filename,
                status=file.status,
                additions=file.additions,
                deletions=file.deletions,
                patch=file.patch
            ))
        
        return files
    
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
    def get_file_content_at_commit(
        self, 
        repo: Repository, 
        path: str, 
        commit_sha: str
    ) -> Optional[str]:
        """Get the content of a file at a specific commit."""
        self._check_rate_limit()
        
        try:
            content = repo.get_contents(path, ref=commit_sha)
            if content.encoding == "base64":
                import base64
                return base64.b64decode(content.content).decode("utf-8")
            return content.decoded_content.decode("utf-8")
        except GithubException as e:
            if e.status == 404:
                return None  # File didn't exist at this commit
            raise
