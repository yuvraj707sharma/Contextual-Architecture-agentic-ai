"""
Feedback Collector — Post-pipeline data collection for continuous improvement.

NOT an agent — a utility class that logs what worked, what failed,
and what the user approved/rejected. This data powers future
improvements to the pipeline.

Data is stored as JSONL (one JSON object per line) for easy
streaming and analysis.
"""

import json
import os
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import List, Dict, Any, Optional


@dataclass
class FeedbackEntry:
    """A single feedback record from a pipeline run."""

    # What was requested
    request: str

    # How it went
    success: bool
    attempts: int = 1
    errors: List[str] = field(default_factory=list)

    # What the user did
    user_approved: Optional[bool] = None
    changes_applied: int = 0
    changes_skipped: int = 0

    # Performance
    duration_ms: float = 0.0

    # Metadata
    language: str = ""
    complexity: str = ""
    timestamp: float = field(default_factory=time.time)

    # Agent summaries (what each agent reported)
    agent_summaries: Dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "FeedbackEntry":
        """Create from a dictionary, ignoring unknown keys."""
        known = {f.name for f in cls.__dataclass_fields__.values()}
        filtered = {k: v for k, v in data.items() if k in known}
        return cls(**filtered)

    @classmethod
    def from_json(cls, line: str) -> "FeedbackEntry":
        return cls.from_dict(json.loads(line))


class FeedbackCollector:
    """
    Collects and persists pipeline feedback data.

    Usage:
        collector = FeedbackCollector()
        entry = collector.collect(orchestration_result)
        collector.save(entry, "path/to/feedback.jsonl")

        # Later analysis
        entries = collector.load("path/to/feedback.jsonl")
        print(collector.summary(entries))
    """

    DEFAULT_FILENAME = "feedback.jsonl"

    def collect(self, result: Any) -> FeedbackEntry:
        """
        Create a FeedbackEntry from an OrchestrationResult.

        Args:
            result: OrchestrationResult from the orchestrator

        Returns:
            FeedbackEntry ready to be saved
        """
        errors = getattr(result, "errors", [])
        metrics = getattr(result, "metrics", None)
        changeset = getattr(result, "changeset", None)
        context = getattr(result, "context", {})

        # Count changes applied/skipped
        applied = 0
        skipped = 0
        if changeset:
            changes = getattr(changeset, "changes", [])
            for c in changes:
                if getattr(c, "approved", False) or getattr(c, "auto_approved", False):
                    applied += 1
                else:
                    skipped += 1

        return FeedbackEntry(
            request=getattr(result, "context", {}).get(
                "user_request",
                str(getattr(result, "generated_code", "")[:50]),
            ),
            success=getattr(result, "success", False),
            attempts=getattr(result, "attempts", 1),
            errors=errors,
            changes_applied=applied,
            changes_skipped=skipped,
            duration_ms=(
                metrics.total_duration_ms if metrics else 0.0
            ),
            complexity=context.get("plan", {}).get("complexity", ""),
            agent_summaries=getattr(result, "agent_summaries", {}),
        )

    def save(self, entry: FeedbackEntry, path: str) -> None:
        """
        Append a feedback entry to a JSONL file.

        Args:
            entry: FeedbackEntry to save
            path: Path to the JSONL file (created if missing)
        """
        os.makedirs(os.path.dirname(path) if os.path.dirname(path) else ".", exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(entry.to_json() + "\n")

    def load(self, path: str) -> List[FeedbackEntry]:
        """
        Load all feedback entries from a JSONL file.

        Args:
            path: Path to the JSONL file

        Returns:
            List of FeedbackEntry objects
        """
        entries: List[FeedbackEntry] = []
        if not os.path.exists(path):
            return entries

        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                stripped = line.strip()
                if not stripped:
                    continue
                try:
                    entries.append(FeedbackEntry.from_json(stripped))
                except (json.JSONDecodeError, TypeError):
                    continue  # skip malformed lines

        return entries

    def summary(self, entries: Optional[List[FeedbackEntry]] = None, path: Optional[str] = None) -> Dict[str, Any]:
        """
        Generate summary statistics from feedback data.

        Args:
            entries: List of FeedbackEntry (or load from path)
            path: Path to load from (if entries not provided)

        Returns:
            Dict with summary statistics
        """
        if entries is None and path:
            entries = self.load(path)
        if not entries:
            return {
                "total_runs": 0,
                "success_rate": 0.0,
                "avg_attempts": 0.0,
                "avg_duration_ms": 0.0,
                "common_errors": [],
            }

        total = len(entries)
        successes = sum(1 for e in entries if e.success)
        total_attempts = sum(e.attempts for e in entries)
        total_duration = sum(e.duration_ms for e in entries)

        # Count error frequency
        error_counts: Dict[str, int] = {}
        for e in entries:
            for err in e.errors:
                # Truncate long errors for grouping
                key = err[:100]
                error_counts[key] = error_counts.get(key, 0) + 1

        common_errors = sorted(
            error_counts.items(), key=lambda x: x[1], reverse=True
        )[:5]

        return {
            "total_runs": total,
            "success_rate": successes / total if total else 0.0,
            "avg_attempts": total_attempts / total if total else 0.0,
            "avg_duration_ms": total_duration / total if total else 0.0,
            "total_changes_applied": sum(e.changes_applied for e in entries),
            "total_changes_skipped": sum(e.changes_skipped for e in entries),
            "common_errors": [
                {"error": err, "count": cnt} for err, cnt in common_errors
            ],
        }

    def summary_text(self, entries: Optional[List[FeedbackEntry]] = None, path: Optional[str] = None) -> str:
        """Human-readable summary string."""
        s = self.summary(entries, path)
        if s["total_runs"] == 0:
            return "No feedback data yet."

        lines = [
            f"📊 Pipeline Feedback Summary ({s['total_runs']} runs)",
            f"   Success rate: {s['success_rate']:.0%}",
            f"   Avg attempts: {s['avg_attempts']:.1f}",
            f"   Avg duration: {s['avg_duration_ms']:.0f}ms",
            f"   Changes applied: {s['total_changes_applied']}",
            f"   Changes skipped: {s['total_changes_skipped']}",
        ]

        if s["common_errors"]:
            lines.append("   Common errors:")
            for item in s["common_errors"]:
                lines.append(f"     - ({item['count']}x) {item['error']}")

        return "\n".join(lines)
