"""
PR Search — Lightweight search over PR evolution data.

Searches the pr_evolution.jsonl file (produced by the data pipeline)
to find PRs relevant to the user's current request. Returns budget-aware
summaries — NEVER raw diffs or full file contents.

No vector DB needed — uses TF-IDF keyword matching against PR titles,
descriptions, reviewer comments, and changed file paths.
"""

import json
import math
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Dict, Any, Optional

from .logger import get_logger

logger = get_logger("pr_search")


@dataclass
class PRSummary:
    """Budget-friendly summary of a relevant PR.

    Designed to fit in ~200 tokens per summary, so 3 results = 600 tokens
    which fits inside the 1,000-token pr_history budget.
    """

    title: str
    pr_number: int
    category: str  # "security", "error_handling", "architecture", etc.
    # 1-2 sentence summary of what changed
    summary: str
    # Key reviewer feedback (the "correction logic")
    reviewer_feedback: List[str] = field(default_factory=list)
    # Files that were changed
    changed_files: List[str] = field(default_factory=list)
    # Relevance score (0.0 - 1.0)
    relevance_score: float = 0.0

    def to_prompt_context(self, max_feedback: int = 2) -> str:
        """Convert to a budget-friendly string for LLM prompt.

        Args:
            max_feedback: Max number of reviewer comments to include.

        Returns:
            Formatted string (~150-200 tokens).
        """
        parts = [
            f"### PR #{self.pr_number}: {self.title}",
            f"Category: {self.category}",
            f"Summary: {self.summary}",
        ]

        if self.reviewer_feedback:
            feedback = self.reviewer_feedback[:max_feedback]
            parts.append("Key feedback:")
            for fb in feedback:
                # Truncate long comments
                truncated = fb[:200] + "..." if len(fb) > 200 else fb
                parts.append(f"  - {truncated}")

        if self.changed_files:
            files = self.changed_files[:5]
            parts.append(f"Changed files: {', '.join(files)}")

        return "\n".join(parts)


class PRSearcher:
    """Lightweight PR history search over pr_evolution.jsonl.

    Uses TF-IDF-style keyword matching — no vector DB, no embeddings.
    Designed to be fast and work offline on small datasets (100-10k PRs).

    Usage:
        searcher = PRSearcher()
        searcher.load("data_pipeline/output/pr_evolution.jsonl")
        results = searcher.search("JWT authentication middleware", max_results=3)
    """

    def __init__(self):
        self._records: List[Dict[str, Any]] = []
        self._idf: Dict[str, float] = {}
        self._loaded = False

    def load(self, jsonl_path: str) -> int:
        """Load PR evolution data from a JSONL file.

        Each line should be a JSON object with at least:
          - pr_number: int
          - title: str
          - description: str (optional)
          - category: str
          - original_code: str (optional)
          - fixed_code: str (optional)
          - comments: list of {body: str, path: str, ...}

        Args:
            jsonl_path: Path to the JSONL file.

        Returns:
            Number of records loaded.
        """
        path = Path(jsonl_path)
        if not path.exists():
            logger.warning(f"PR data file not found: {jsonl_path}")
            return 0

        self._records = []
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                    self._records.append(record)
                except json.JSONDecodeError:
                    logger.debug(f"Skipping malformed line {line_num}")

        if self._records:
            self._build_idf()
            self._loaded = True

        logger.info(f"Loaded {len(self._records)} PR records from {path.name}")
        return len(self._records)

    def load_from_records(self, records: List[Dict[str, Any]]) -> int:
        """Load from an in-memory list of records.

        Useful for testing or when records come from a different source.

        Args:
            records: List of PR record dicts.

        Returns:
            Number of records loaded.
        """
        self._records = records
        if self._records:
            self._build_idf()
            self._loaded = True
        return len(self._records)

    def search(
        self,
        query: str,
        max_results: int = 3,
        min_score: float = 0.05,
    ) -> List[PRSummary]:
        """Search PR history for records relevant to the query.

        Uses TF-IDF keyword matching against multiple fields:
        - PR title (weight 3x)
        - PR description (weight 2x)
        - Reviewer comments (weight 2x)
        - Changed file paths (weight 1.5x)
        - Category (weight 1x)

        Args:
            query: The user's request (e.g. "Add JWT auth middleware").
            max_results: Maximum results to return.
            min_score: Minimum relevance score to include.

        Returns:
            List of PRSummary objects, sorted by relevance.
        """
        if not self._loaded or not self._records:
            logger.debug("No PR data loaded — returning empty results")
            return []

        query_tokens = self._tokenize(query)
        if not query_tokens:
            return []

        scored: List[tuple] = []

        for record in self._records:
            score = self._score_record(record, query_tokens)
            if score >= min_score:
                scored.append((score, record))

        # Sort by score descending
        scored.sort(key=lambda x: x[0], reverse=True)

        results = []
        for score, record in scored[:max_results]:
            summary = self._record_to_summary(record, score)
            results.append(summary)

        logger.info(
            f"Search '{query[:50]}' → {len(results)} results "
            f"(top score: {results[0].relevance_score:.3f})"
            if results else f"Search '{query[:50]}' → 0 results"
        )

        return results

    def search_to_prompt(
        self,
        query: str,
        max_results: int = 3,
        max_tokens: int = 1000,
    ) -> str:
        """Search and format results for injection into LLM prompt.

        Respects the pr_history token budget.

        Args:
            query: User request.
            max_results: Max results.
            max_tokens: Token budget for the output.

        Returns:
            Formatted string for the LLM prompt.
        """
        results = self.search(query, max_results=max_results)

        if not results:
            return ""

        parts = ["## PR History (relevant patterns from past reviews)\n"]
        total_chars = len(parts[0])

        for pr_summary in results:
            entry = pr_summary.to_prompt_context()
            entry_chars = len(entry)
            # Rough token estimate: chars / 4
            estimated_tokens = (total_chars + entry_chars) / 4
            if estimated_tokens > max_tokens:
                break
            parts.append(entry)
            parts.append("")  # blank line separator
            total_chars += entry_chars

        return "\n".join(parts)

    # ── Private Methods ────────────────────────────────────

    def _tokenize(self, text: str) -> List[str]:
        """Tokenize text into lowercase words, removing noise."""
        if not text:
            return []
        # Split on non-alphanumeric, filter short tokens and stopwords
        tokens = re.findall(r"[a-z][a-z0-9_]+", text.lower())
        return [t for t in tokens if t not in _STOPWORDS and len(t) > 1]

    def _build_idf(self) -> None:
        """Build inverse document frequency for all tokens."""
        doc_count = len(self._records)
        if doc_count == 0:
            return

        # Count how many documents each token appears in
        df: Counter = Counter()
        for record in self._records:
            doc_text = self._get_searchable_text(record)
            unique_tokens = set(self._tokenize(doc_text))
            df.update(unique_tokens)

        # Calculate IDF: log(N / df(t)) with smoothing
        self._idf = {
            token: math.log((doc_count + 1) / (count + 1)) + 1
            for token, count in df.items()
        }

    def _get_searchable_text(self, record: Dict[str, Any]) -> str:
        """Extract all searchable text from a PR record."""
        parts = [
            record.get("title", ""),
            record.get("description", ""),
            record.get("category", ""),
        ]

        # Add comment bodies
        comments = record.get("comments", [])
        if isinstance(comments, list):
            for comment in comments:
                if isinstance(comment, dict):
                    parts.append(comment.get("body", ""))
                elif isinstance(comment, str):
                    parts.append(comment)

        # Add changed file paths
        changed_files = record.get("changed_files", [])
        if isinstance(changed_files, list):
            parts.extend(changed_files)

        # Add any other text fields
        for key in ("original_code", "fixed_code", "review_comment"):
            val = record.get(key, "")
            if isinstance(val, str):
                parts.append(val)

        return " ".join(parts)

    def _score_record(
        self,
        record: Dict[str, Any],
        query_tokens: List[str],
    ) -> float:
        """Score a record against query tokens using weighted TF-IDF.

        Fields are weighted by importance:
          title: 3x, description: 2x, comments: 2x,
          changed_files: 1.5x, category: 1x
        """
        weighted_fields = [
            (record.get("title", ""), 3.0),
            (record.get("description", ""), 2.0),
            (record.get("category", ""), 1.0),
        ]

        # Comments
        comments = record.get("comments", [])
        if isinstance(comments, list):
            comment_text = " ".join(
                c.get("body", "") if isinstance(c, dict) else str(c)
                for c in comments
            )
            weighted_fields.append((comment_text, 2.0))

        # Review comment (single string field)
        review_comment = record.get("review_comment", "")
        if review_comment:
            weighted_fields.append((review_comment, 2.5))

        # Changed files
        changed_files = record.get("changed_files", [])
        if isinstance(changed_files, list):
            weighted_fields.append((" ".join(changed_files), 1.5))

        total_score = 0.0
        for text, weight in weighted_fields:
            field_tokens = self._tokenize(text)
            if not field_tokens:
                continue

            tf = Counter(field_tokens)
            field_score = 0.0
            for qt in query_tokens:
                if qt in tf:
                    term_freq = tf[qt] / len(field_tokens)
                    idf = self._idf.get(qt, 1.0)
                    field_score += term_freq * idf

            total_score += field_score * weight

        # Normalize by query length to keep scores comparable
        if query_tokens:
            total_score /= len(query_tokens)

        return total_score

    def _record_to_summary(
        self,
        record: Dict[str, Any],
        score: float,
    ) -> PRSummary:
        """Convert a raw record to a budget-friendly PRSummary."""
        # Extract reviewer feedback
        feedback = []
        comments = record.get("comments", [])
        if isinstance(comments, list):
            for c in comments:
                body = c.get("body", "") if isinstance(c, dict) else str(c)
                if body and len(body) > 20:  # skip trivial comments
                    feedback.append(body)

        # Fall back to review_comment field
        review_comment = record.get("review_comment", "")
        if review_comment and review_comment not in feedback:
            feedback.insert(0, review_comment)

        # Extract changed files
        changed = record.get("changed_files", [])
        if not isinstance(changed, list):
            changed = []

        # Build summary from description or title
        desc = record.get("description", "")
        if desc and len(desc) > 20:
            summary_text = desc[:300]
        else:
            summary_text = record.get("title", "No description")

        return PRSummary(
            title=record.get("title", "Untitled PR"),
            pr_number=record.get("pr_number", 0),
            category=record.get("category", "general"),
            summary=summary_text,
            reviewer_feedback=feedback[:5],  # max 5 feedback items
            changed_files=changed[:10],  # max 10 files
            relevance_score=round(score, 4),
        )

    @property
    def record_count(self) -> int:
        """Number of loaded PR records."""
        return len(self._records)

    @property
    def is_loaded(self) -> bool:
        """Whether PR data has been loaded."""
        return self._loaded


# Stopwords to exclude from tokenization
_STOPWORDS = frozenset({
    "the", "is", "at", "which", "on", "a", "an", "and", "or", "but",
    "in", "to", "for", "of", "with", "by", "from", "as", "it", "its",
    "this", "that", "be", "are", "was", "were", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would",
    "could", "should", "may", "might", "shall", "can",
    "not", "no", "nor", "so", "if", "then", "than", "too", "very",
    "just", "about", "above", "after", "again", "all", "also", "am",
    "any", "because", "before", "between", "both", "each", "few",
    "get", "got", "here", "him", "his", "her", "how", "into",
    "more", "most", "my", "now", "only", "other", "our", "out",
    "own", "same", "she", "some", "such", "them", "there", "these",
    "they", "those", "through", "under", "until", "up", "we", "what",
    "when", "where", "who", "whom", "why", "you", "your",
})
