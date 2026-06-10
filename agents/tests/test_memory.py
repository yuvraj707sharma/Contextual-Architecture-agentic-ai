"""
Comprehensive tests for the MemoryStore session memory system.

All tests use in-memory SQLite (``:memory:``) or ``tmp_path`` —
no network or LLM calls required.
"""

from __future__ import annotations

import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Dict

import pytest

from agents.memory import MemoryStore


# ── Fixtures ─────────────────────────────────────────────


@pytest.fixture
def store() -> MemoryStore:
    """A fresh in-memory MemoryStore for each test."""
    ms = MemoryStore(db_path=":memory:")
    yield ms
    ms.close()


@pytest.fixture
def store_on_disk(tmp_path: Path) -> MemoryStore:
    """A MemoryStore backed by a file in tmp_path."""
    db_file = str(tmp_path / "test_memory.db")
    ms = MemoryStore(db_path=db_file)
    yield ms
    ms.close()


def _record_sample_session(
    store: MemoryStore,
    *,
    repo_path: str = "/repos/my-project",
    user_request: str = "Add authentication",
    language: str = "python",
    plan_summary: str = "Add JWT auth middleware",
    success: bool = True,
    duration_ms: int = 1500,
    target_files: list[str] | None = None,
    agent_summaries: dict[str, str] | None = None,
    error: str | None = None,
) -> int:
    """Helper to insert a session with sensible defaults."""
    if target_files is None:
        target_files = ["src/auth.py", "tests/test_auth.py"]
    if agent_summaries is None:
        agent_summaries = {
            "planner": "Created plan for JWT auth",
            "implementer": "Generated auth module",
        }
    return store.record_session(
        repo_path=repo_path,
        user_request=user_request,
        language=language,
        plan_summary=plan_summary,
        success=success,
        duration_ms=duration_ms,
        target_files=target_files,
        agent_summaries=agent_summaries,
        error=error,
    )


# ── record_session ───────────────────────────────────────


class TestRecordSession:
    """Tests for MemoryStore.record_session."""

    def test_returns_positive_id(self, store: MemoryStore) -> None:
        sid = _record_sample_session(store)
        assert sid >= 1

    def test_sequential_ids(self, store: MemoryStore) -> None:
        id1 = _record_sample_session(store, user_request="first")
        id2 = _record_sample_session(store, user_request="second")
        assert id2 == id1 + 1

    def test_stores_all_fields(self, store: MemoryStore) -> None:
        sid = _record_sample_session(
            store,
            repo_path="/repos/app",
            user_request="Fix bug #42",
            language="typescript",
            plan_summary="Patch the widget",
            success=False,
            duration_ms=3200,
            target_files=["src/widget.ts"],
            agent_summaries={"reviewer": "Found linting issues"},
            error="Type error in widget.ts",
        )
        history = store.get_repo_history("/repos/app", limit=1)
        assert len(history) == 1
        row = history[0]
        assert row["id"] == sid
        assert row["repo_path"] == "/repos/app"
        assert row["repo_name"] == "app"
        assert row["user_request"] == "Fix bug #42"
        assert row["language"] == "typescript"
        assert row["plan_summary"] == "Patch the widget"
        assert row["success"] is False
        assert row["duration_ms"] == 3200
        assert row["target_files"] == ["src/widget.ts"]
        assert row["agent_summaries"] == {"reviewer": "Found linting issues"}
        assert row["error"] == "Type error in widget.ts"

    def test_repo_name_extracted(self, store: MemoryStore) -> None:
        _record_sample_session(store, repo_path="/home/user/projects/cool-lib")
        history = store.get_repo_history("/home/user/projects/cool-lib")
        assert history[0]["repo_name"] == "cool-lib"

    def test_null_error_when_success(self, store: MemoryStore) -> None:
        _record_sample_session(store, success=True)
        history = store.get_repo_history("/repos/my-project")
        assert history[0]["error"] is None


# ── record_feedback ──────────────────────────────────────


class TestRecordFeedback:
    """Tests for MemoryStore.record_feedback."""

    def test_valid_feedback_types(self, store: MemoryStore) -> None:
        sid = _record_sample_session(store)
        for fb_type in ("approve", "reject", "partial", "correction"):
            store.record_feedback(sid, fb_type, f"Test {fb_type}")
        # Should show up in history
        history = store.get_repo_history("/repos/my-project")
        assert history[0]["feedback_types"] is not None

    def test_invalid_feedback_type_ignored(self, store: MemoryStore) -> None:
        sid = _record_sample_session(store)
        store.record_feedback(sid, "invalid_type", "Should be ignored")
        # Verify nothing was inserted
        with store._lock:
            row = store._conn.execute(
                "SELECT COUNT(*) AS cnt FROM feedback WHERE session_id = ?",
                (sid,),
            ).fetchone()
        assert row["cnt"] == 0

    def test_feedback_links_to_session(self, store: MemoryStore) -> None:
        sid = _record_sample_session(store)
        store.record_feedback(sid, "approve", "Looks good!")
        history = store.get_repo_history("/repos/my-project")
        assert "approve" in history[0]["feedback_types"]

    def test_multiple_feedback_per_session(self, store: MemoryStore) -> None:
        sid = _record_sample_session(store)
        store.record_feedback(sid, "partial", "Needs tests")
        store.record_feedback(sid, "correction", "Wrong function name")
        history = store.get_repo_history("/repos/my-project")
        feedback_str = history[0]["feedback_types"]
        assert "partial" in feedback_str
        assert "correction" in feedback_str


# ── get_repo_history ─────────────────────────────────────


class TestGetRepoHistory:
    """Tests for MemoryStore.get_repo_history."""

    def test_empty_db_returns_empty_list(self, store: MemoryStore) -> None:
        assert store.get_repo_history("/no/such/repo") == []

    def test_ordered_by_recency(self, store: MemoryStore) -> None:
        repo = "/repos/timeline"
        _record_sample_session(store, repo_path=repo, user_request="first")
        _record_sample_session(store, repo_path=repo, user_request="second")
        _record_sample_session(store, repo_path=repo, user_request="third")

        history = store.get_repo_history(repo)
        requests = [h["user_request"] for h in history]
        assert requests == ["third", "second", "first"]

    def test_limit_respected(self, store: MemoryStore) -> None:
        repo = "/repos/limittest"
        for i in range(10):
            _record_sample_session(store, repo_path=repo, user_request=f"req-{i}")
        history = store.get_repo_history(repo, limit=3)
        assert len(history) == 3

    def test_filters_by_repo(self, store: MemoryStore) -> None:
        _record_sample_session(store, repo_path="/repos/alpha")
        _record_sample_session(store, repo_path="/repos/beta")
        alpha = store.get_repo_history("/repos/alpha")
        assert len(alpha) == 1
        assert alpha[0]["repo_path"] == "/repos/alpha"

    def test_json_deserialized(self, store: MemoryStore) -> None:
        _record_sample_session(
            store,
            target_files=["a.py", "b.py"],
            agent_summaries={"planner": "ok"},
        )
        history = store.get_repo_history("/repos/my-project")
        assert isinstance(history[0]["target_files"], list)
        assert isinstance(history[0]["agent_summaries"], dict)


# ── get_repo_preferences ────────────────────────────────


class TestGetRepoPreferences:
    """Tests for MemoryStore.get_repo_preferences."""

    def test_empty_db_returns_defaults(self, store: MemoryStore) -> None:
        prefs = store.get_repo_preferences("/no/repo")
        assert prefs["total_sessions"] == 0
        assert prefs["language"] is None
        assert prefs["success_rate"] == 0.0
        assert prefs["frequent_files"] == []

    def test_language_is_most_common(self, store: MemoryStore) -> None:
        repo = "/repos/multilang"
        _record_sample_session(store, repo_path=repo, language="python")
        _record_sample_session(store, repo_path=repo, language="python")
        _record_sample_session(store, repo_path=repo, language="typescript")
        prefs = store.get_repo_preferences(repo)
        assert prefs["language"] == "python"

    def test_success_rate(self, store: MemoryStore) -> None:
        repo = "/repos/rates"
        _record_sample_session(store, repo_path=repo, success=True)
        _record_sample_session(store, repo_path=repo, success=True)
        _record_sample_session(store, repo_path=repo, success=False)
        prefs = store.get_repo_preferences(repo)
        assert prefs["success_rate"] == pytest.approx(0.67, abs=0.01)

    def test_frequent_files_sorted(self, store: MemoryStore) -> None:
        repo = "/repos/files"
        _record_sample_session(
            store, repo_path=repo, target_files=["a.py", "b.py"]
        )
        _record_sample_session(
            store, repo_path=repo, target_files=["a.py", "c.py"]
        )
        _record_sample_session(
            store, repo_path=repo, target_files=["a.py"]
        )
        prefs = store.get_repo_preferences(repo)
        # a.py should come first (3 occurrences)
        assert prefs["frequent_files"][0] == "a.py"

    def test_avg_duration(self, store: MemoryStore) -> None:
        repo = "/repos/dur"
        _record_sample_session(store, repo_path=repo, duration_ms=1000)
        _record_sample_session(store, repo_path=repo, duration_ms=3000)
        prefs = store.get_repo_preferences(repo)
        assert prefs["avg_duration_ms"] == pytest.approx(2000.0)

    def test_common_patterns(self, store: MemoryStore) -> None:
        repo = "/repos/patterns"
        _record_sample_session(
            store,
            repo_path=repo,
            agent_summaries={"planner": "authentication middleware setup"},
        )
        _record_sample_session(
            store,
            repo_path=repo,
            agent_summaries={"planner": "authentication route handler"},
        )
        prefs = store.get_repo_preferences(repo)
        # "authentication" appears in both sessions
        assert "authentication" in prefs["common_patterns"]

    def test_stored_preferences_included(self, store: MemoryStore) -> None:
        repo = "/repos/prefs"
        _record_sample_session(store, repo_path=repo)
        store.set_preference(repo, "test_framework", "pytest", confidence=0.9)
        prefs = store.get_repo_preferences(repo)
        assert "test_framework" in prefs["stored_preferences"]
        assert prefs["stored_preferences"]["test_framework"]["value"] == "pytest"
        assert prefs["stored_preferences"]["test_framework"]["confidence"] == 0.9


# ── search_sessions ──────────────────────────────────────


class TestSearchSessions:
    """Tests for MemoryStore.search_sessions."""

    def test_empty_query_returns_empty(self, store: MemoryStore) -> None:
        assert store.search_sessions("") == []
        assert store.search_sessions("   ") == []

    def test_finds_by_user_request(self, store: MemoryStore) -> None:
        _record_sample_session(
            store, user_request="Add JWT authentication",
            plan_summary="Setup token auth",
            agent_summaries={"planner": "setup auth"},
        )
        _record_sample_session(
            store, user_request="Fix database connection",
            plan_summary="Repair db pool",
            agent_summaries={"planner": "fix db"},
        )
        results = store.search_sessions("JWT")
        assert len(results) == 1
        assert "JWT" in results[0]["user_request"]

    def test_finds_by_plan_summary(self, store: MemoryStore) -> None:
        _record_sample_session(store, plan_summary="Implement caching layer")
        results = store.search_sessions("caching")
        assert len(results) == 1

    def test_finds_by_error(self, store: MemoryStore) -> None:
        _record_sample_session(
            store, success=False, error="ImportError: no module named flask"
        )
        results = store.search_sessions("flask")
        assert len(results) == 1

    def test_finds_by_agent_summaries(self, store: MemoryStore) -> None:
        _record_sample_session(
            store,
            agent_summaries={"reviewer": "Found security vulnerability in auth"},
        )
        results = store.search_sessions("vulnerability")
        assert len(results) == 1

    def test_limit_respected(self, store: MemoryStore) -> None:
        for i in range(10):
            _record_sample_session(store, user_request=f"Add feature number {i}")
        results = store.search_sessions("feature", limit=3)
        assert len(results) == 3

    def test_case_insensitive_search(self, store: MemoryStore) -> None:
        _record_sample_session(store, user_request="Add GRAPHQL endpoint")
        results = store.search_sessions("graphql")
        # SQLite LIKE is case-insensitive for ASCII by default
        assert len(results) == 1


# ── get_stats ────────────────────────────────────────────


class TestGetStats:
    """Tests for MemoryStore.get_stats."""

    def test_empty_db_stats(self, store: MemoryStore) -> None:
        stats = store.get_stats()
        assert stats["total_sessions"] == 0
        assert stats["success_rate"] == 0.0
        assert stats["top_repos"] == []

    def test_correct_aggregates(self, store: MemoryStore) -> None:
        _record_sample_session(store, success=True, duration_ms=1000)
        _record_sample_session(store, success=True, duration_ms=2000)
        _record_sample_session(store, success=False, duration_ms=3000)
        stats = store.get_stats()
        assert stats["total_sessions"] == 3
        assert stats["successful_sessions"] == 2
        assert stats["failed_sessions"] == 1
        assert stats["success_rate"] == pytest.approx(0.67, abs=0.01)
        assert stats["avg_duration_ms"] == pytest.approx(2000.0)

    def test_top_repos(self, store: MemoryStore) -> None:
        for _ in range(5):
            _record_sample_session(store, repo_path="/repos/popular")
        for _ in range(2):
            _record_sample_session(store, repo_path="/repos/niche")
        stats = store.get_stats()
        assert stats["top_repos"][0]["repo"] == "popular"
        assert stats["top_repos"][0]["sessions"] == 5

    def test_language_distribution(self, store: MemoryStore) -> None:
        _record_sample_session(store, language="python")
        _record_sample_session(store, language="python")
        _record_sample_session(store, language="rust")
        stats = store.get_stats()
        assert stats["languages"]["python"] == 2
        assert stats["languages"]["rust"] == 1

    def test_feedback_count(self, store: MemoryStore) -> None:
        sid = _record_sample_session(store)
        store.record_feedback(sid, "approve", "Great")
        store.record_feedback(sid, "correction", "Rename func")
        stats = store.get_stats()
        assert stats["total_feedback"] == 2


# ── cleanup ──────────────────────────────────────────────


class TestCleanup:
    """Tests for MemoryStore.cleanup."""

    def test_no_op_on_empty_db(self, store: MemoryStore) -> None:
        deleted = store.cleanup(older_than_days=30)
        assert deleted == 0

    def test_removes_old_sessions(self, store: MemoryStore) -> None:
        sid = _record_sample_session(store)
        # Manually backdate the session
        with store._conn:
            store._conn.execute(
                "UPDATE sessions SET created_at = datetime('now', '-100 days') WHERE id = ?",
                (sid,),
            )
        deleted = store.cleanup(older_than_days=90)
        assert deleted == 1
        assert store.get_repo_history("/repos/my-project") == []

    def test_keeps_recent_sessions(self, store: MemoryStore) -> None:
        _record_sample_session(store)
        deleted = store.cleanup(older_than_days=1)
        assert deleted == 0

    def test_removes_associated_feedback(self, store: MemoryStore) -> None:
        sid = _record_sample_session(store)
        store.record_feedback(sid, "approve", "Good")
        # Backdate
        with store._conn:
            store._conn.execute(
                "UPDATE sessions SET created_at = datetime('now', '-200 days') WHERE id = ?",
                (sid,),
            )
        store.cleanup(older_than_days=90)
        # Verify feedback is also gone
        with store._lock:
            row = store._conn.execute(
                "SELECT COUNT(*) AS cnt FROM feedback WHERE session_id = ?",
                (sid,),
            ).fetchone()
        assert row["cnt"] == 0


# ── set_preference ───────────────────────────────────────


class TestSetPreference:
    """Tests for MemoryStore.set_preference."""

    def test_insert_and_retrieve(self, store: MemoryStore) -> None:
        repo = "/repos/x"
        _record_sample_session(store, repo_path=repo)  # Need a session for prefs
        store.set_preference(repo, "test_runner", "pytest", confidence=0.8)
        prefs = store.get_repo_preferences(repo)
        sp = prefs["stored_preferences"]
        assert "test_runner" in sp
        assert sp["test_runner"]["value"] == "pytest"
        assert sp["test_runner"]["confidence"] == 0.8

    def test_upsert_updates_value(self, store: MemoryStore) -> None:
        repo = "/repos/x"
        _record_sample_session(store, repo_path=repo)
        store.set_preference(repo, "style", "google", confidence=0.5)
        store.set_preference(repo, "style", "pep8", confidence=0.9)
        prefs = store.get_repo_preferences(repo)
        assert prefs["stored_preferences"]["style"]["value"] == "pep8"
        assert prefs["stored_preferences"]["style"]["confidence"] == 0.9


# ── Context manager ──────────────────────────────────────


class TestContextManager:
    """Tests for using MemoryStore as a context manager."""

    def test_context_manager(self) -> None:
        with MemoryStore(db_path=":memory:") as ms:
            sid = _record_sample_session(ms)
            assert sid >= 1

    def test_repr(self, store: MemoryStore) -> None:
        assert "MemoryStore" in repr(store)
        assert ":memory:" in repr(store)


# ── Disk persistence ────────────────────────────────────


class TestDiskPersistence:
    """Verify data survives across MemoryStore instances."""

    def test_data_persists(self, tmp_path: Path) -> None:
        db_file = str(tmp_path / "persist.db")

        # Write with one instance
        with MemoryStore(db_path=db_file) as ms:
            sid = _record_sample_session(ms, user_request="persist me")

        # Read with a new instance
        with MemoryStore(db_path=db_file) as ms2:
            history = ms2.get_repo_history("/repos/my-project")
            assert len(history) == 1
            assert history[0]["user_request"] == "persist me"


# ── Thread safety ────────────────────────────────────────


class TestThreadSafety:
    """Basic concurrency smoke tests."""

    def test_concurrent_writes(self, store: MemoryStore) -> None:
        errors: list[Exception] = []

        def writer(n: int) -> None:
            try:
                for i in range(10):
                    _record_sample_session(
                        store,
                        repo_path=f"/repos/thread-{n}",
                        user_request=f"req-{n}-{i}",
                    )
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=writer, args=(t,)) for t in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == [], f"Concurrent writes failed: {errors}"
        stats = store.get_stats()
        assert stats["total_sessions"] == 40  # 4 threads × 10

    def test_concurrent_read_write(self, store: MemoryStore) -> None:
        # Pre-populate
        for i in range(20):
            _record_sample_session(store, user_request=f"setup-{i}")

        errors: list[Exception] = []

        def reader() -> None:
            try:
                for _ in range(10):
                    store.get_stats()
                    store.search_sessions("setup")
            except Exception as exc:
                errors.append(exc)

        def writer() -> None:
            try:
                for i in range(10):
                    _record_sample_session(store, user_request=f"extra-{i}")
            except Exception as exc:
                errors.append(exc)

        threads = [
            threading.Thread(target=reader),
            threading.Thread(target=reader),
            threading.Thread(target=writer),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == []


# ── Edge cases ───────────────────────────────────────────


class TestEdgeCases:
    """Edge-case and boundary tests."""

    def test_special_characters_in_request(self, store: MemoryStore) -> None:
        sid = _record_sample_session(
            store,
            user_request="Fix O'Malley's bug; DROP TABLE sessions; --",
        )
        assert sid >= 1
        history = store.get_repo_history("/repos/my-project")
        assert "O'Malley" in history[0]["user_request"]

    def test_unicode_in_request(self, store: MemoryStore) -> None:
        sid = _record_sample_session(
            store,
            user_request="日本語テスト — emoji 🚀",
        )
        assert sid >= 1
        history = store.get_repo_history("/repos/my-project")
        assert "🚀" in history[0]["user_request"]

    def test_empty_target_files(self, store: MemoryStore) -> None:
        sid = _record_sample_session(store, target_files=[])
        assert sid >= 1
        history = store.get_repo_history("/repos/my-project")
        assert history[0]["target_files"] == []

    def test_empty_agent_summaries(self, store: MemoryStore) -> None:
        sid = _record_sample_session(store, agent_summaries={})
        assert sid >= 1
        history = store.get_repo_history("/repos/my-project")
        assert history[0]["agent_summaries"] == {}

    def test_very_long_request(self, store: MemoryStore) -> None:
        long_text = "x" * 10_000
        sid = _record_sample_session(store, user_request=long_text)
        assert sid >= 1
        history = store.get_repo_history("/repos/my-project")
        assert len(history[0]["user_request"]) == 10_000

    def test_search_no_match(self, store: MemoryStore) -> None:
        _record_sample_session(store)
        results = store.search_sessions("zzz_nonexistent_zzz")
        assert results == []

    def test_get_preferences_no_sessions_but_has_prefs(
        self, store: MemoryStore
    ) -> None:
        """Stored preferences exist but no sessions for the repo."""
        store.set_preference("/repos/orphan", "lint", "ruff", confidence=0.7)
        prefs = store.get_repo_preferences("/repos/orphan")
        assert prefs["total_sessions"] == 0
        # stored prefs still returned even with zero sessions
        assert prefs["stored_preferences"]["lint"]["value"] == "ruff"

    def test_cleanup_zero_days(self, store: MemoryStore) -> None:
        """Cleanup with 0 days should delete everything."""
        _record_sample_session(store)
        # Backdate by 1 second so it's definitely "older than 0 days"
        with store._conn:
            store._conn.execute(
                "UPDATE sessions SET created_at = datetime('now', '-1 day')"
            )
        deleted = store.cleanup(older_than_days=0)
        assert deleted == 1
