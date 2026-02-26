"""
SQLite store for structured data — telemetry, feedback, sessions.

Lightweight, zero-config, ships with Python. No external dependencies.
Swap to PostgreSQL by implementing the same interface.
"""

import json
import sqlite3
import logging
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)


class StructuredStore:
    """
    SQLite-backed persistent storage for structured data.

    Stores:
    - pipeline_runs: Each orchestrator execution
    - agent_telemetry: Per-agent timings, token counts, outputs
    - feedback: User accept/reject/modify signals per run
    """

    def __init__(self, db_path: str = "./.contextual-architect/contextual_architect.db"):
        db_file = Path(db_path)
        db_file.parent.mkdir(parents=True, exist_ok=True)

        self.db_path = str(db_file)
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")  # Better concurrent reads
        self._create_tables()
        logger.info(f"SQLite store ready: {self.db_path}")

    def _create_tables(self):
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS pipeline_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task TEXT NOT NULL,
                repo TEXT,
                language TEXT,
                provider TEXT,
                model TEXT,
                status TEXT DEFAULT 'running',
                attempt_count INTEGER DEFAULT 0,
                constraints_passed INTEGER DEFAULT 0,
                constraints_total INTEGER DEFAULT 0,
                generated_code TEXT,
                duration_seconds REAL,
                created_at TEXT DEFAULT (datetime('now')),
                completed_at TEXT
            );

            CREATE TABLE IF NOT EXISTS agent_telemetry (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id INTEGER NOT NULL REFERENCES pipeline_runs(id),
                agent_name TEXT NOT NULL,
                input_tokens INTEGER DEFAULT 0,
                output_tokens INTEGER DEFAULT 0,
                duration_ms INTEGER DEFAULT 0,
                output_summary TEXT,
                error TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS feedback (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id INTEGER REFERENCES pipeline_runs(id),
                agent TEXT NOT NULL,
                feedback_type TEXT NOT NULL,
                content TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            );

            CREATE INDEX IF NOT EXISTS idx_telemetry_run ON agent_telemetry(run_id);
            CREATE INDEX IF NOT EXISTS idx_feedback_run ON feedback(run_id);
            CREATE INDEX IF NOT EXISTS idx_runs_repo ON pipeline_runs(repo);
            CREATE INDEX IF NOT EXISTS idx_runs_status ON pipeline_runs(status);
        """)
        self.conn.commit()

    # ─── Pipeline Runs ────────────────────────────────────────

    def start_run(
        self,
        task: str,
        repo: str,
        language: str = "",
        provider: str = "",
        model: str = "",
    ) -> int:
        """Record start of a pipeline run. Returns the run ID."""
        cur = self.conn.execute(
            """INSERT INTO pipeline_runs (task, repo, language, provider, model)
               VALUES (?, ?, ?, ?, ?)""",
            (task, repo, language, provider, model),
        )
        self.conn.commit()
        run_id = cur.lastrowid
        logger.debug(f"Pipeline run started: id={run_id}, task='{task[:60]}...'")
        return run_id

    def complete_run(
        self,
        run_id: int,
        status: str = "completed",
        attempt_count: int = 1,
        constraints_passed: int = 0,
        constraints_total: int = 0,
        generated_code: str = "",
        duration_seconds: float = 0.0,
    ) -> None:
        """Mark a pipeline run as completed."""
        self.conn.execute(
            """UPDATE pipeline_runs
               SET status = ?, attempt_count = ?,
                   constraints_passed = ?, constraints_total = ?,
                   generated_code = ?, duration_seconds = ?,
                   completed_at = datetime('now')
               WHERE id = ?""",
            (
                status,
                attempt_count,
                constraints_passed,
                constraints_total,
                generated_code,
                duration_seconds,
                run_id,
            ),
        )
        self.conn.commit()

    def get_run(self, run_id: int) -> Optional[dict]:
        """Get a pipeline run by ID."""
        row = self.conn.execute(
            "SELECT * FROM pipeline_runs WHERE id = ?", (run_id,)
        ).fetchone()
        return dict(row) if row else None

    def get_recent_runs(self, repo: str = None, limit: int = 20) -> list[dict]:
        """Get recent pipeline runs, optionally filtered by repo."""
        if repo:
            rows = self.conn.execute(
                "SELECT * FROM pipeline_runs WHERE repo = ? ORDER BY created_at DESC LIMIT ?",
                (repo, limit),
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM pipeline_runs ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]

    # ─── Agent Telemetry ──────────────────────────────────────

    def log_agent(
        self,
        run_id: int,
        agent_name: str,
        input_tokens: int = 0,
        output_tokens: int = 0,
        duration_ms: int = 0,
        output_summary: str = "",
        error: str = "",
    ) -> None:
        """Log a single agent's execution within a run."""
        self.conn.execute(
            """INSERT INTO agent_telemetry
               (run_id, agent_name, input_tokens, output_tokens,
                duration_ms, output_summary, error)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (run_id, agent_name, input_tokens, output_tokens,
             duration_ms, output_summary, error),
        )
        self.conn.commit()

    def get_run_telemetry(self, run_id: int) -> list[dict]:
        """Get all agent telemetry for a run."""
        rows = self.conn.execute(
            "SELECT * FROM agent_telemetry WHERE run_id = ? ORDER BY created_at",
            (run_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    # ─── Feedback ─────────────────────────────────────────────

    def log_feedback(
        self,
        run_id: int,
        agent: str,
        feedback_type: str,
        content: str = "",
    ) -> None:
        """Log user feedback (accept/reject/modify) for a run."""
        self.conn.execute(
            """INSERT INTO feedback (run_id, agent, feedback_type, content)
               VALUES (?, ?, ?, ?)""",
            (run_id, agent, feedback_type, content),
        )
        self.conn.commit()

    def get_feedback_history(
        self, repo: str = None, limit: int = 50
    ) -> list[dict]:
        """Get recent feedback, optionally filtered by repo."""
        if repo:
            rows = self.conn.execute(
                """SELECT f.*, p.task, p.repo
                   FROM feedback f
                   JOIN pipeline_runs p ON f.run_id = p.id
                   WHERE p.repo = ?
                   ORDER BY f.created_at DESC LIMIT ?""",
                (repo, limit),
            ).fetchall()
        else:
            rows = self.conn.execute(
                """SELECT f.*, p.task, p.repo
                   FROM feedback f
                   JOIN pipeline_runs p ON f.run_id = p.id
                   ORDER BY f.created_at DESC LIMIT ?""",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]

    # ─── Stats ────────────────────────────────────────────────

    def get_stats(self) -> dict:
        """Get aggregate statistics for the research paper / analytics."""
        total_runs = self.conn.execute(
            "SELECT COUNT(*) FROM pipeline_runs"
        ).fetchone()[0]

        completed_runs = self.conn.execute(
            "SELECT COUNT(*) FROM pipeline_runs WHERE status = 'completed'"
        ).fetchone()[0]

        avg_duration = self.conn.execute(
            "SELECT AVG(duration_seconds) FROM pipeline_runs WHERE status = 'completed'"
        ).fetchone()[0]

        total_feedback = self.conn.execute(
            "SELECT COUNT(*) FROM feedback"
        ).fetchone()[0]

        return {
            "total_runs": total_runs,
            "completed_runs": completed_runs,
            "avg_duration_seconds": round(avg_duration, 2) if avg_duration else 0,
            "total_feedback": total_feedback,
        }

    # ─── Lifecycle ────────────────────────────────────────────

    def close(self) -> None:
        """Close the database connection."""
        self.conn.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
