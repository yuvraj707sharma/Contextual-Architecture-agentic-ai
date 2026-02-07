"""
PR Evolution Extractor - Main Logic.

This module orchestrates the extraction of PR evolution data:
1. Fetches merged PRs with review comments
2. Extracts the "correction logic" (what was wrong → how it was fixed)
3. Outputs JSONL training data
"""

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Iterator
from tqdm import tqdm

from .config import ExtractionConfig, RepoConfig, CORRECTION_PATTERNS
from .github_client import (
    GitHubClient, 
    PREvolution, 
    PRReviewComment, 
    PRDiff
)


def detect_language(file_path: str) -> str:
    """Detect language from file extension."""
    ext_map = {
        ".go": "go",
        ".py": "python",
        ".ts": "typescript",
        ".tsx": "typescript",
        ".js": "javascript", 
        ".jsx": "javascript",
        ".rs": "rust",
    }
    for ext, lang in ext_map.items():
        if file_path.endswith(ext):
            return lang
    return "unknown"


def categorize_comment(comment: str) -> str:
    """
    Categorize a review comment into a lesson type.
    
    This is the "secret sauce" - understanding WHAT TYPE of
    correction is being made.
    """
    comment_lower = comment.lower()
    
    # Priority order matters - check most specific first
    if any(p in comment_lower for p in ["security", "vulnerability", "injection", "xss", "csrf"]):
        return "security"
    
    if any(p in comment_lower for p in ["error", "handle", "panic", "recover"]):
        return "error_handling"
    
    if any(p in comment_lower for p in ["test", "coverage", "mock", "assert"]):
        return "testing"
    
    if any(p in comment_lower for p in ["performance", "memory", "allocate", "goroutine", "async"]):
        return "performance"
    
    if any(p in comment_lower for p in ["interface", "abstract", "dependency", "couple", "layer"]):
        return "architecture"
    
    if any(p in comment_lower for p in ["convention", "style", "naming", "format"]):
        return "style"
    
    if any(p in comment_lower for p in ["internal/", "pkg/", "module", "package"]):
        return "project_structure"
    
    return "general"


def extract_code_from_diff_hunk(diff_hunk: str) -> tuple[str, str]:
    """
    Extract the 'before' and 'after' code from a diff hunk.
    
    Returns: (original_code, context_lines)
    """
    lines = diff_hunk.split('\n')
    original_lines = []
    context_lines = []
    
    for line in lines:
        if line.startswith('-') and not line.startswith('---'):
            # Removed line (original code)
            original_lines.append(line[1:])  # Remove the '-'
        elif line.startswith('+') and not line.startswith('+++'):
            # Added line (we'll get this from the fixed version)
            pass
        elif line.startswith(' ') or (not line.startswith('@') and line):
            # Context line
            context_lines.append(line[1:] if line.startswith(' ') else line)
    
    return '\n'.join(original_lines), '\n'.join(context_lines)


class PREvolutionExtractor:
    """
    Main extractor class for PR Evolution data.
    
    This is the core of Phase 1.3 - extracting the "correction logic"
    from real-world code reviews.
    """
    
    def __init__(self, config: ExtractionConfig):
        self.config = config
        self.client = GitHubClient(config)
    
    def extract_from_repo(
        self, 
        repo_config: RepoConfig,
        output_dir: Path
    ) -> int:
        """
        Extract PR evolution data from a single repository.
        
        Returns: Number of training samples extracted
        """
        print(f"\n{'='*60}")
        print(f"📦 Extracting from: {repo_config.full_name}")
        print(f"{'='*60}")
        
        repo = self.client.get_repo(repo_config)
        output_file = output_dir / f"{repo_config.owner}_{repo_config.repo}.jsonl"
        
        samples_count = 0
        
        with open(output_file, 'w', encoding='utf-8') as f:
            prs = self.client.get_merged_prs(repo, limit=repo_config.max_prs)
            
            for pr in tqdm(prs, desc="Processing PRs"):
                evolutions = self._extract_evolutions_from_pr(
                    repo, pr, repo_config
                )
                
                for evolution in evolutions:
                    json_line = json.dumps(evolution.to_jsonl(), ensure_ascii=False)
                    f.write(json_line + '\n')
                    samples_count += 1
        
        print(f"✅ Extracted {samples_count} training samples → {output_file}")
        return samples_count
    
    def _extract_evolutions_from_pr(
        self,
        repo,
        pr,
        repo_config: RepoConfig
    ) -> Iterator[PREvolution]:
        """
        Extract all evolution samples from a single PR.
        
        A PR can have multiple review comments, each potentially
        representing a different "lesson."
        """
        # Get review comments
        comments = self.client.get_pr_review_comments(pr)
        
        # Filter for comments that contain correction logic
        valuable_comments = [
            c for c in comments 
            if c.contains_correction(CORRECTION_PATTERNS)
        ]
        
        if not valuable_comments:
            return
        
        # Get file diffs
        files = self.client.get_pr_files(pr)
        file_map = {f.filename: f for f in files}
        
        # For each valuable comment, create a training sample
        for comment in valuable_comments:
            if comment.path not in file_map:
                continue
            
            file_diff = file_map[comment.path]
            
            # Extract original code from the diff hunk
            original_code, context = extract_code_from_diff_hunk(comment.diff_hunk)
            
            if not original_code.strip():
                # No removals, might be an addition-only review
                original_code = context
            
            # Try to get the fixed version from the merge commit
            fixed_code = None
            if pr.merge_commit_sha:
                fixed_code = self.client.get_file_content_at_commit(
                    repo, comment.path, pr.merge_commit_sha
                )
            
            # Categorize the lesson
            category = categorize_comment(comment.body)
            
            yield PREvolution(
                repo=repo_config.full_name,
                pr_number=pr.number,
                pr_title=pr.title,
                pr_description=pr.body or "",
                original_code=original_code,
                file_path=comment.path,
                reviewer_comment=comment.body,
                fixed_code=fixed_code,
                lesson_category=category,
                language=detect_language(comment.path)
            )
    
    def extract_from_multiple_repos(
        self,
        repo_configs: List[RepoConfig],
        output_dir: Path
    ) -> int:
        """
        Extract from multiple repositories.
        
        Returns: Total number of training samples
        """
        output_dir.mkdir(parents=True, exist_ok=True)
        
        total_samples = 0
        for repo_config in repo_configs:
            try:
                count = self.extract_from_repo(repo_config, output_dir)
                total_samples += count
            except Exception as e:
                print(f"❌ Failed to extract from {repo_config.full_name}: {e}")
                continue
        
        print(f"\n{'='*60}")
        print(f"🎉 TOTAL: {total_samples} training samples extracted")
        print(f"{'='*60}")
        
        return total_samples
