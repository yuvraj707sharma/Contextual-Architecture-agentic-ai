"""
Session Memory — Persistent cross-session memory backed by SQLite.

Remembers past pipeline sessions, user feedback, and per-repo preferences
so MACRO can learn from history and improve over time.
"""

from __future__ import annotations

import json
import os
import sqlite3
import threading
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .logger import get_logger

logger = get_logger("memory")

# ── Default database path ────────────────────────────────

_DEFAULT_DB_DIR = Path.home() / ".contextual-architect"
_DEFAULT_DB_PATH = _DEFAULT_DB_DIR / "session_memory.db"

# ── SQL schema ───────────────────────────────────────────

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    repo_path TEXT NOT NULL,
    repo_name TEXT NOT NULL,
    user_request TEXT NOT NULL,
    language TEXT,
    plan_summary TEXT,
    success INTEGER NOT NULL DEFAULT 0,
    duration_ms INTEGER,
    target_files TEXT,
    agent_summaries TEXT,
    error TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS feedback (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL,
    feedback_type TEXT NOT NULL,
    details TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (session_id) REFERENCES sessions(id)
);

CREATE TABLE IF NOT EXISTS preferences (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    repo_path TEXT NOT NULL,
    key TEXT NOT NULL,
    value TEXT NOT NULL,
    confidence REAL DEFAULT 0.5,
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(repo_path, key)
);

CREATE INDEX IF NOT EXISTS idx_sessions_repo_path ON sessions(repo_path);
CREATE INDEX IF NOT EXISTS idx_sessions_created_at ON sessions(created_at);
CREATE INDEX IF NOT EXISTS idx_feedback_session_id ON feedback(session_id);
CREATE INDEX IF NOT EXISTS idx_preferences_repo_path ON preferences(repo_path);
"""

# Valid feedback types
_VALID_FEEDBACK_TYPES = frozenset({"approve", "reject", "partial", "correction"})


class MemoryStore:
    """Persistent session memory using SQLite.

    Database location: ~/.contextual-architect/session_memory.db
    Thread-safe via ``check_same_thread=False`` on the underlying connection.
    """

    def __init__(self, db_path: Optional[str] = None) -> None:
        if db_path is None:
            _DEFAULT_DB_DIR.mkdir(parents=True, exist_ok=True)
            self._db_path = str(_DEFAULT_DB_PATH)
        else:
            # Ensure parent dirs exist (unless it's :memory:)
            if db_path != ":memory:":
                Path(db_path).parent.mkdir(parents=True, exist_ok=True)
            self._db_path = db_path

        self._lock = threading.Lock()
        self._conn = sqlite3.connect(
            self._db_path,
            check_same_thread=False,
            detect_types=sqlite3.PARSE_DECLTYPES,
        )
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._init_schema()

    # ── Schema bootstrap ─────────────────────────────────

    def _init_schema(self) -> None:
        """Create tables/indices if they don't already exist."""
        try:
            with self._conn:
                self._conn.executescript(_SCHEMA_SQL)
        except sqlite3.Error as exc:
            logger.error("Failed to initialise memory schema: %s", exc)
            raise

    # ── Session recording ────────────────────────────────

    def record_session(
        self,
        repo_path: str,
        user_request: str,
        language: str,
        plan_summary: str,
        success: bool,
        duration_ms: int,
        target_files: List[str],
        agent_summaries: Dict[str, str],
        error: Optional[str] = None,
    ) -> int:
        """Record a completed pipeline session.

        Args:
            repo_path: Absolute path to the repository.
            user_request: The original user request text.
            language: Primary language of the session.
            plan_summary: Summary produced by the planner.
            success: Whether the session completed successfully.
            duration_ms: Total wall-clock time in milliseconds.
            target_files: List of files touched during the session.
            agent_summaries: Per-agent summary strings.
            error: Error message if the session failed.

        Returns:
            The auto-generated ``session_id``.
        """
        repo_name = Path(repo_path).name
        target_files_json = json.dumps(target_files)
        agent_summaries_json = json.dumps(agent_summaries)

        try:
            with self._lock, self._conn:
                cursor = self._conn.execute(
                    """
                    INSERT INTO sessions
                        (repo_path, repo_name, user_request, language,
                         plan_summary, success, duration_ms,
                         target_files, agent_summaries, error)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        repo_path,
                        repo_name,
                        user_request,
                        language,
                        plan_summary,
                        int(success),
                        duration_ms,
                        target_files_json,
                        agent_summaries_json,
                        error,
                    ),
                )
                session_id: int = cursor.lastrowid  # type: ignore[assignment]
                logger.info(
                    "Recorded session %d for %s (success=%s)",
                    session_id,
                    repo_name,
                    success,
                )
                return session_id
        except sqlite3.Error as exc:
            logger.error("Failed to record session: %s", exc)
            return -1

    # ── Feedback ─────────────────────────────────────────

    def record_feedback(
        self,
        session_id: int,
        feedback_type: str,
        details: str,
    ) -> None:
        """Record user feedback on a session.

        Args:
            session_id: The session to attach feedback to.
            feedback_type: One of ``'approve'``, ``'reject'``,
                ``'partial'``, ``'correction'``.
            details: Free-form text with additional context.
        """
        if feedback_type not in _VALID_FEEDBACK_TYPES:
            logger.warning(
                "Invalid feedback_type '%s'; expected one of %s",
                feedback_type,
                _VALID_FEEDBACK_TYPES,
            )
            return

        try:
            with self._lock, self._conn:
                self._conn.execute(
                    """
                    INSERT INTO feedback (session_id, feedback_type, details)
                    VALUES (?, ?, ?)
                    """,
                    (session_id, feedback_type, details),
                )
                logger.info(
                    "Recorded '%s' feedback for session %d",
                    feedback_type,
                    session_id,
                )
        except sqlite3.Error as exc:
            logger.error("Failed to record feedback: %s", exc)

    # ── Repo history ─────────────────────────────────────

    def get_repo_history(
        self,
        repo_path: str,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """Get recent sessions for a repo — used by Historian to learn patterns.

        Returns a list of session dicts ordered by most-recent first.
        """
        try:
            with self._lock:
                rows = self._conn.execute(
                    """
                    SELECT s.*,
                           GROUP_CONCAT(f.feedback_type, ',') AS feedback_types
                    FROM sessions s
                    LEFT JOIN feedback f ON f.session_id = s.id
                    WHERE s.repo_path = ?
                    GROUP BY s.id
                    ORDER BY s.created_at DESC, s.id DESC
                    LIMIT ?
                    """,
                    (repo_path, limit),
                ).fetchall()
            return [self._row_to_dict(row) for row in rows]
        except sqlite3.Error as exc:
            logger.error("Failed to get repo history: %s", exc)
            return []

    # ── Repo preferences ─────────────────────────────────

    def get_repo_preferences(self, repo_path: str) -> Dict[str, Any]:
        """Extract preferences from past sessions.

        Analyses all recorded sessions for *repo_path* and returns:
        - ``language``: most common language used
        - ``success_rate``: ratio of successful sessions
        - ``total_sessions``: number of sessions recorded
        - ``frequent_files``: files sorted by modification frequency
        - ``avg_duration_ms``: mean duration across sessions
        - ``common_patterns``: frequent keywords from agent summaries
        - ``stored_preferences``: explicit key/value preferences table
        """
        prefs: Dict[str, Any] = {
            "language": None,
            "success_rate": 0.0,
            "total_sessions": 0,
            "frequent_files": [],
            "avg_duration_ms": 0.0,
            "common_patterns": [],
            "stored_preferences": {},
        }

        try:
            with self._lock:
                rows = self._conn.execute(
                    """
                    SELECT language, success, duration_ms,
                           target_files, agent_summaries
                    FROM sessions
                    WHERE repo_path = ?
                    ORDER BY created_at DESC
                    """,
                    (repo_path,),
                ).fetchall()

            if rows:
                total = len(rows)
                prefs["total_sessions"] = total

                # Language — mode
                languages = [r["language"] for r in rows if r["language"]]
                if languages:
                    prefs["language"] = Counter(languages).most_common(1)[0][0]

                # Success rate
                successes = sum(1 for r in rows if r["success"])
                prefs["success_rate"] = round(successes / total, 2)

                # Average duration
                durations = [r["duration_ms"] for r in rows if r["duration_ms"] is not None]
                if durations:
                    prefs["avg_duration_ms"] = round(sum(durations) / len(durations), 1)

                # Frequent files
                file_counter: Counter[str] = Counter()
                for r in rows:
                    if r["target_files"]:
                        try:
                            files = json.loads(r["target_files"])
                            file_counter.update(files)
                        except (json.JSONDecodeError, TypeError):
                            pass
                prefs["frequent_files"] = [
                    f for f, _ in file_counter.most_common(20)
                ]

                # Common patterns from agent summaries
                word_counter: Counter[str] = Counter()
                for r in rows:
                    if r["agent_summaries"]:
                        try:
                            summaries = json.loads(r["agent_summaries"])
                            for text in summaries.values():
                                # Extract meaningful tokens (length > 3)
                                words = text.lower().split()
                                word_counter.update(
                                    w for w in words if len(w) > 3
                                )
                        except (json.JSONDecodeError, TypeError):
                            pass
                prefs["common_patterns"] = [
                    w for w, _ in word_counter.most_common(10)
                ]

            # Stored explicit preferences (always queried, even with 0 sessions)
            with self._lock:
                pref_rows = self._conn.execute(
                    """
                    SELECT key, value, confidence
                    FROM preferences
                    WHERE repo_path = ?
                    ORDER BY confidence DESC
                    """,
                    (repo_path,),
                ).fetchall()
            prefs["stored_preferences"] = {
                r["key"]: {"value": r["value"], "confidence": r["confidence"]}
                for r in pref_rows
            }

        except sqlite3.Error as exc:
            logger.error("Failed to compute repo preferences: %s", exc)

        return prefs

    # ── Full-text search ─────────────────────────────────

    def search_sessions(
        self,
        query: str,
        limit: int = 5,
    ) -> List[Dict[str, Any]]:
        """Full-text search across past sessions.

        Searches ``user_request``, ``plan_summary``, and ``error`` columns
        using SQL ``LIKE`` for maximum compatibility (no FTS extension
        required).
        """
        if not query or not query.strip():
            return []

        pattern = f"%{query}%"
        try:
            with self._lock:
                rows = self._conn.execute(
                    """
                    SELECT *
                    FROM sessions
                    WHERE user_request LIKE ?
                       OR plan_summary LIKE ?
                       OR error LIKE ?
                       OR agent_summaries LIKE ?
                    ORDER BY created_at DESC
                    LIMIT ?
                    """,
                    (pattern, pattern, pattern, pattern, limit),
                ).fetchall()
            return [self._row_to_dict(row) for row in rows]
        except sqlite3.Error as exc:
            logger.error("Search failed: %s", exc)
            return []

    # ── Stats ────────────────────────────────────────────

    def get_stats(self) -> Dict[str, Any]:
        """Overall stats: total sessions, success rate, top repos, etc."""
        stats: Dict[str, Any] = {
            "total_sessions": 0,
            "successful_sessions": 0,
            "failed_sessions": 0,
            "success_rate": 0.0,
            "total_feedback": 0,
            "avg_duration_ms": 0.0,
            "top_repos": [],
            "languages": {},
        }
        try:
            with self._lock:
                # Aggregate counts
                row = self._conn.execute(
                    """
                    SELECT
                        COUNT(*) AS total,
                        SUM(success) AS ok,
                        AVG(duration_ms) AS avg_dur
                    FROM sessions
                    """
                ).fetchone()

            if row and row["total"]:
                total = row["total"]
                ok = row["ok"] or 0
                stats["total_sessions"] = total
                stats["successful_sessions"] = ok
                stats["failed_sessions"] = total - ok
                stats["success_rate"] = round(ok / total, 2)
                if row["avg_dur"] is not None:
                    stats["avg_duration_ms"] = round(row["avg_dur"], 1)

            with self._lock:
                # Top repos by session count
                repo_rows = self._conn.execute(
                    """
                    SELECT repo_name, COUNT(*) AS cnt
                    FROM sessions
                    GROUP BY repo_path
                    ORDER BY cnt DESC
                    LIMIT 5
                    """
                ).fetchall()
            stats["top_repos"] = [
                {"repo": r["repo_name"], "sessions": r["cnt"]}
                for r in repo_rows
            ]

            with self._lock:
                # Language distribution
                lang_rows = self._conn.execute(
                    """
                    SELECT language, COUNT(*) AS cnt
                    FROM sessions
                    WHERE language IS NOT NULL
                    GROUP BY language
                    ORDER BY cnt DESC
                    """
                ).fetchall()
            stats["languages"] = {r["language"]: r["cnt"] for r in lang_rows}

            with self._lock:
                fb_row = self._conn.execute(
                    "SELECT COUNT(*) AS cnt FROM feedback"
                ).fetchone()
            stats["total_feedback"] = fb_row["cnt"] if fb_row else 0

        except sqlite3.Error as exc:
            logger.error("Failed to compute stats: %s", exc)

        return stats

    # ── Cleanup ──────────────────────────────────────────

    def cleanup(self, older_than_days: int = 90) -> int:
        """Remove sessions older than *older_than_days*.

        Also removes associated feedback rows via ``ON DELETE CASCADE``
        emulation (SQLite doesn't always enforce it, so we delete
        feedback explicitly first).

        Returns:
            Number of sessions deleted.
        """
        cutoff = (
            datetime.now(timezone.utc) - timedelta(days=older_than_days)
        ).strftime("%Y-%m-%d %H:%M:%S")

        try:
            with self._lock, self._conn:
                # Delete feedback for old sessions first
                self._conn.execute(
                    """
                    DELETE FROM feedback
                    WHERE session_id IN (
                        SELECT id FROM sessions WHERE created_at < ?
                    )
                    """,
                    (cutoff,),
                )
                cursor = self._conn.execute(
                    "DELETE FROM sessions WHERE created_at < ?",
                    (cutoff,),
                )
                deleted = cursor.rowcount
                logger.info(
                    "Cleaned up %d sessions older than %d days",
                    deleted,
                    older_than_days,
                )
                return deleted
        except sqlite3.Error as exc:
            logger.error("Cleanup failed: %s", exc)
            return 0

    # ── Preference management ────────────────────────────

    def set_preference(
        self,
        repo_path: str,
        key: str,
        value: str,
        confidence: float = 0.5,
    ) -> None:
        """Store or update an explicit preference for a repo.

        Uses ``INSERT OR REPLACE`` to upsert the value.
        """
        try:
            with self._lock, self._conn:
                self._conn.execute(
                    """
                    INSERT INTO preferences (repo_path, key, value, confidence, updated_at)
                    VALUES (?, ?, ?, ?, datetime('now'))
                    ON CONFLICT(repo_path, key)
                    DO UPDATE SET value=excluded.value,
                                  confidence=excluded.confidence,
                                  updated_at=excluded.updated_at
                    """,
                    (repo_path, key, value, confidence),
                )
        except sqlite3.Error as exc:
            logger.error("Failed to set preference: %s", exc)

    # ── Close ────────────────────────────────────────────

    def close(self) -> None:
        """Close the underlying database connection."""
        try:
            self._conn.close()
        except sqlite3.Error:
            pass

    # ── Helpers ───────────────────────────────────────────

    @staticmethod
    def _row_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
        """Convert a ``sqlite3.Row`` into a plain dict, deserialising
        JSON columns along the way."""
        d = dict(row)
        # Deserialise JSON columns
        for col in ("target_files", "agent_summaries"):
            if col in d and d[col] is not None:
                try:
                    d[col] = json.loads(d[col])
                except (json.JSONDecodeError, TypeError):
                    pass
        # Coerce boolean
        if "success" in d:
            d["success"] = bool(d["success"])
        return d

    def __enter__(self) -> "MemoryStore":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def __repr__(self) -> str:
        return f"MemoryStore(db_path={self._db_path!r})"
