"""
Feedback Reader — Loads past run feedback to inform the Historian.

This closes the learning loop:
  Run → Feedback JSONL → Historian reads patterns → Better next run

Reads the JSONL written by FeedbackCollector and extracts:
- Which review issues recur (anti-pattern signal)
- Which files get retried most (high-churn signal)
- Which convention violations are most common (convention gap signal)
"""

import json
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List


class FeedbackReader:
    """Reads historical feedback to surface patterns for the Historian."""

    def __init__(self, feedback_dir: str | Path = ".contextual-architect/feedback"):
        self.feedback_dir = Path(feedback_dir)

    def get_historical_patterns(self) -> Dict[str, Any]:
        """
        Analyze all past feedback and return patterns.

        Returns a dict compatible with the Historian's input format:
        {
            "feedback_patterns": {
                "recurring_issues": [...],
                "high_retry_files": [...],
                "common_violations": [...],
                "total_runs_analyzed": int
            }
        }
        """
        entries = self._load_all_entries()

        if not entries:
            return {
                "feedback_patterns": {
                    "recurring_issues": [],
                    "high_retry_files": [],
                    "common_violations": [],
                    "total_runs_analyzed": 0,
                }
            }

        return {
            "feedback_patterns": {
                "recurring_issues": self._find_recurring_issues(entries),
                "high_retry_files": self._find_high_retry_files(entries),
                "common_violations": self._find_common_violations(entries),
                "total_runs_analyzed": len(entries),
            }
        }

    def _load_all_entries(self) -> List[dict]:
        """Load all JSONL feedback files."""
        entries: List[dict] = []
        if not self.feedback_dir.exists():
            return entries

        for jsonl_file in self.feedback_dir.glob("*.jsonl"):
            with open(jsonl_file, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            entries.append(json.loads(line))
                        except json.JSONDecodeError:
                            continue
        return entries

    def _find_recurring_issues(
        self, entries: List[dict]
    ) -> List[Dict[str, Any]]:
        """Find review issues that appear across multiple runs."""
        issue_counter: Counter = Counter()
        for entry in entries:
            review = entry.get("review_result", {})
            if not isinstance(review, dict):
                continue
            for layer in ("layer_1_logic", "layer_2_security", "layer_3_style"):
                layer_data = review.get(layer, {})
                if not isinstance(layer_data, dict):
                    continue
                issues = layer_data.get("issues", [])
                for issue in issues:
                    issue_text = issue.get("issue", "") if isinstance(issue, dict) else str(issue)
                    if issue_text:
                        issue_counter[issue_text] += 1

        return [
            {"issue": issue, "occurrences": count}
            for issue, count in issue_counter.most_common(10)
            if count >= 2  # only flag if it recurred
        ]

    def _find_high_retry_files(
        self, entries: List[dict]
    ) -> List[Dict[str, Any]]:
        """Find files that triggered the most retry loops."""
        file_retry_counter: Counter = Counter()
        for entry in entries:
            retries = entry.get("retries", 0)
            if not isinstance(retries, int) or retries <= 0:
                continue
            files_modified = entry.get("files_modified", [])
            if not isinstance(files_modified, list):
                continue
            for f in files_modified:
                if isinstance(f, str):
                    file_retry_counter[f] += retries

        return [
            {"file": f, "total_retries": count}
            for f, count in file_retry_counter.most_common(10)
            if count >= 2
        ]

    def _find_common_violations(
        self, entries: List[dict]
    ) -> List[Dict[str, Any]]:
        """Find the most common convention violations."""
        violation_counter: Counter = Counter()
        for entry in entries:
            violations = entry.get("convention_violations", [])
            if not isinstance(violations, list):
                continue
            for v in violations:
                violation_text = v.get("violation", v) if isinstance(v, dict) else str(v)
                if violation_text:
                    violation_counter[violation_text] += 1

        return [
            {"violation": v, "occurrences": count}
            for v, count in violation_counter.most_common(10)
            if count >= 2
        ]
