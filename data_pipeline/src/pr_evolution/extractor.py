"""
PR Evolution Extractor - Main Logic.

This module orchestrates the extraction of PR evolution data:
1. Fetches merged PRs with review comments
2. Extracts the "correction logic" (what was wrong → how it was fixed)
3. Outputs JSONL training data

UPDATED: Addressed code review feedback:
1. Fixed diff hunk extraction to capture BOTH removed (-) and added (+) lines
2. Fixed fixed_code retrieval to extract only relevant hunk, not entire file
3. Added quality score filtering
4. Added security audit for training data
5. Now uses shared utils for language detection and categorization
"""

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Iterator, Tuple
from tqdm import tqdm

from .config import (
    ExtractionConfig, 
    RepoConfig, 
    CORRECTION_PATTERNS_STRONG,
    calculate_quality_score,
    check_for_secrets,
    check_for_vulnerabilities,
    SUGGESTION_PATTERN,
)
from .github_client import (
    GitHubClient, 
    PREvolution, 
    PRReviewComment, 
    PRDiff
)

# Import from shared utils (single source of truth)
from ..utils import detect_language_from_code, categorize_comment


# Alias for backward compatibility
def detect_language(file_path: str) -> str:
    """Detect language from file path. Uses shared utils."""
    return detect_language_from_code("", file_path)


def extract_code_from_diff_hunk(diff_hunk: str) -> Tuple[str, str, str]:
    """
    Extract the 'original', 'added', and 'context' code from a diff hunk.
    
    FIXED: Now correctly captures BOTH removed (-) and added (+) lines.
    
    Returns: (original_code, added_code, context_lines)
    - original_code: Lines that were removed (the "before")
    - added_code: Lines that were added (the "after" / fix)
    - context_lines: Unchanged context lines
    """
    lines = diff_hunk.split('\n')
    original_lines = []  # Lines starting with '-' (removed)
    added_lines = []     # Lines starting with '+' (added) - THIS WAS MISSING
    context_lines = []   # Lines starting with ' ' (unchanged)
    
    for line in lines:
        # Skip diff header lines
        if line.startswith('@@') or line.startswith('diff ') or line.startswith('index '):
            continue
        if line.startswith('---') or line.startswith('+++'):
            continue
            
        if line.startswith('-'):
            # Removed line (original code that was wrong)
            original_lines.append(line[1:])  # Remove the '-' prefix
        elif line.startswith('+'):
            # Added line (the fix!) - CRITICAL FIX
            added_lines.append(line[1:])  # Remove the '+' prefix
        elif line.startswith(' '):
            # Context line (unchanged)
            context_lines.append(line[1:])  # Remove the ' ' prefix
        elif line and not line.startswith('\\'):
            # Line without prefix (some diff formats)
            context_lines.append(line)
    
    return (
        '\n'.join(original_lines),
        '\n'.join(added_lines),
        '\n'.join(context_lines)
    )


def extract_suggestion_code(comment_body: str) -> Optional[str]:
    """
    Extract code from GitHub's ```suggestion blocks.
    
    These are the highest quality fixes because they're explicit
    code suggestions from the reviewer.
    """
    match = SUGGESTION_PATTERN.search(comment_body)
    if match:
        return match.group(1).strip()
    return None


class PREvolutionExtractor:
    """
    Main extractor class for PR Evolution data.
    
    This is the core of Phase 1.3 - extracting the "correction logic"
    from real-world code reviews.
    """
    
    def __init__(self, config: ExtractionConfig):
        self.config = config
        self.client = GitHubClient(config)
        
        # Stats for reporting
        self.stats = {
            "prs_processed": 0,
            "comments_processed": 0,
            "samples_extracted": 0,
            "skipped_low_quality": 0,
            "skipped_too_short": 0,
            "skipped_secrets": 0,
        }
    
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
        
        # Reset stats for this repo
        self.stats = {k: 0 for k in self.stats}
        
        with open(output_file, 'w', encoding='utf-8') as f:
            prs = self.client.get_merged_prs(repo, limit=repo_config.max_prs)
            
            for pr in tqdm(prs, desc="Processing PRs"):
                self.stats["prs_processed"] += 1
                
                evolutions = self._extract_evolutions_from_pr(
                    repo, pr, repo_config
                )
                
                for evolution in evolutions:
                    json_line = json.dumps(evolution.to_jsonl(), ensure_ascii=False)
                    f.write(json_line + '\n')
                    self.stats["samples_extracted"] += 1
        
        # Print stats
        print(f"\n📊 Extraction Stats for {repo_config.full_name}:")
        print(f"   PRs processed: {self.stats['prs_processed']}")
        print(f"   Comments processed: {self.stats['comments_processed']}")
        print(f"   ✅ Samples extracted: {self.stats['samples_extracted']}")
        print(f"   ⏭️  Skipped (low quality): {self.stats['skipped_low_quality']}")
        print(f"   ⏭️  Skipped (too short): {self.stats['skipped_too_short']}")
        print(f"   🔒 Skipped (secrets detected): {self.stats['skipped_secrets']}")
        print(f"   → Output: {output_file}")
        
        return self.stats["samples_extracted"]
    
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
        
        # Get file diffs for context
        files = self.client.get_pr_files(pr)
        file_map = {f.filename: f for f in files}
        
        # Process each comment
        for comment in comments:
            self.stats["comments_processed"] += 1
            
            # QUALITY FILTER 1: Minimum length
            if len(comment.body) < self.config.min_comment_length:
                self.stats["skipped_too_short"] += 1
                continue
            
            # QUALITY FILTER 2: Quality score
            quality_score = calculate_quality_score(comment.body)
            if quality_score < self.config.min_quality_score:
                self.stats["skipped_low_quality"] += 1
                continue
            
            if comment.path not in file_map:
                continue
            
            file_diff = file_map[comment.path]
            
            # Extract code from the diff hunk (FIXED)
            original_code, added_code, context = extract_code_from_diff_hunk(
                comment.diff_hunk
            )
            
            # SECURITY AUDIT: Check for secrets in the code
            secrets_original = check_for_secrets(original_code)
            secrets_added = check_for_secrets(added_code)
            if secrets_original or secrets_added:
                self.stats["skipped_secrets"] += 1
                print(f"   ⚠️  Skipped comment (secrets detected): PR#{pr.number}")
                continue
            
            # Determine the "fixed" code:
            # Priority 1: GitHub suggestion block (highest quality)
            # Priority 2: Added lines from diff hunk
            # Priority 3: Full file at merge commit (last resort, less useful)
            fixed_code = None
            
            # Try to get suggestion block first
            suggestion = extract_suggestion_code(comment.body)
            if suggestion:
                fixed_code = suggestion
            elif added_code.strip():
                # Use the added lines from the diff (the actual fix!)
                fixed_code = added_code
            
            # If no local fix found, we DON'T fetch the entire file
            # (That was the bug - entire file is useless as training data)
            if not fixed_code:
                continue  # Skip if we can't get a localized fix
            
            # Categorize the lesson
            category = categorize_comment(comment.body)
            
            # Check for vulnerabilities (warn but include for learning)
            vulns = check_for_vulnerabilities(original_code)
            
            yield PREvolution(
                repo=repo_config.full_name,
                pr_number=pr.number,
                pr_title=pr.title,
                pr_description=pr.body or "",
                original_code=original_code if original_code.strip() else context,
                file_path=comment.path,
                reviewer_comment=comment.body,
                fixed_code=fixed_code,
                lesson_category=category,
                language=detect_language(comment.path),
                quality_score=quality_score,
                has_vulnerability=len(vulns) > 0,
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
