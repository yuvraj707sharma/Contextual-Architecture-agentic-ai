"""Tests for PR Search module."""

import json
import tempfile
from pathlib import Path

import pytest

from agents.pr_search import PRSearcher, PRSummary


# ── Fixtures ─────────────────────────────────────────────

SAMPLE_RECORDS = [
    {
        "pr_number": 101,
        "title": "Add JWT authentication middleware",
        "description": "Implements JWT token validation for API routes",
        "category": "security",
        "comments": [
            {"body": "Use error-first handling for token validation"},
            {"body": "Don't use global middleware, scope to API routes only"},
        ],
        "changed_files": ["middleware/auth.py", "routes/api.py"],
        "review_comment": "Approved after scoping middleware to /api/ prefix",
    },
    {
        "pr_number": 102,
        "title": "Fix database connection pooling",
        "description": "Resolves connection leak in PostgreSQL pool",
        "category": "database",
        "comments": [
            {"body": "Always use context manager for connections"},
        ],
        "changed_files": ["db/pool.py", "db/connection.py"],
    },
    {
        "pr_number": 103,
        "title": "Add user profile endpoint",
        "description": "REST API endpoint for user profiles with caching",
        "category": "api",
        "comments": [
            {"body": "Use the internal logger, not print statements"},
            {"body": "Add rate limiting"},
        ],
        "changed_files": ["routes/profile.py", "models/user.py"],
    },
    {
        "pr_number": 104,
        "title": "Refactor logging to use structured logger",
        "description": "Migrate all print() calls to the internal logging module",
        "category": "architecture",
        "comments": [
            {"body": "Good refactor. Make sure tests still pass."},
        ],
        "changed_files": ["common/logger.py", "services/billing.py"],
    },
]


@pytest.fixture
def searcher():
    """PRSearcher loaded with sample data."""
    s = PRSearcher()
    s.load_from_records(SAMPLE_RECORDS)
    return s


@pytest.fixture
def empty_searcher():
    """PRSearcher with no data loaded."""
    return PRSearcher()


@pytest.fixture
def jsonl_file(tmp_path):
    """Write sample records to a temp JSONL file."""
    path = tmp_path / "pr_evolution.jsonl"
    with open(path, "w", encoding="utf-8") as f:
        for record in SAMPLE_RECORDS:
            f.write(json.dumps(record) + "\n")
    return str(path)


# ── Tests: Loading ───────────────────────────────────────

class TestLoading:
    def test_load_from_records(self, searcher):
        assert searcher.record_count == 4
        assert searcher.is_loaded

    def test_load_from_jsonl(self, jsonl_file):
        s = PRSearcher()
        count = s.load(jsonl_file)
        assert count == 4
        assert s.is_loaded

    def test_load_missing_file(self):
        s = PRSearcher()
        count = s.load("nonexistent.jsonl")
        assert count == 0
        assert not s.is_loaded

    def test_load_from_empty_records(self):
        s = PRSearcher()
        count = s.load_from_records([])
        assert count == 0
        assert not s.is_loaded


# ── Tests: Search ────────────────────────────────────────

class TestSearch:
    def test_search_auth(self, searcher):
        results = searcher.search("JWT authentication middleware")
        assert len(results) >= 1
        assert results[0].pr_number == 101
        assert results[0].category == "security"

    def test_search_database(self, searcher):
        results = searcher.search("database connection pool")
        assert len(results) >= 1
        # PR 102 should rank highest for database queries
        assert any(r.pr_number == 102 for r in results)

    def test_search_empty_query(self, searcher):
        results = searcher.search("")
        assert results == []

    def test_search_no_data(self, empty_searcher):
        results = empty_searcher.search("anything")
        assert results == []

    def test_search_max_results(self, searcher):
        results = searcher.search("authentication", max_results=1)
        assert len(results) <= 1

    def test_search_min_score(self, searcher):
        results = searcher.search("completely irrelevant quantum physics", min_score=10.0)
        assert results == []

    def test_relevance_scoring(self, searcher):
        results = searcher.search("authentication middleware")
        if len(results) >= 2:
            # Scores should be descending
            assert results[0].relevance_score >= results[1].relevance_score


# ── Tests: PRSummary ─────────────────────────────────────

class TestPRSummary:
    def test_to_prompt_context(self):
        summary = PRSummary(
            title="Test PR",
            pr_number=42,
            category="testing",
            summary="A test summary",
            reviewer_feedback=["Use mocks", "Add edge cases"],
            changed_files=["test_file.py"],
            relevance_score=0.85,
        )
        ctx = summary.to_prompt_context()
        assert "PR #42" in ctx
        assert "Test PR" in ctx
        assert "testing" in ctx
        assert "Use mocks" in ctx
        assert "test_file.py" in ctx

    def test_to_prompt_context_truncates_feedback(self):
        long_feedback = "x" * 300
        summary = PRSummary(
            title="Test",
            pr_number=1,
            category="test",
            summary="test",
            reviewer_feedback=[long_feedback],
        )
        ctx = summary.to_prompt_context()
        assert "..." in ctx  # should be truncated

    def test_to_prompt_context_limits_feedback(self):
        summary = PRSummary(
            title="Test",
            pr_number=1,
            category="test",
            summary="test",
            reviewer_feedback=["fb1", "fb2", "fb3", "fb4"],
        )
        ctx = summary.to_prompt_context(max_feedback=2)
        assert "fb1" in ctx
        assert "fb2" in ctx
        assert "fb3" not in ctx


# ── Tests: search_to_prompt ──────────────────────────────

class TestSearchToPrompt:
    def test_output_format(self, searcher):
        prompt = searcher.search_to_prompt("authentication")
        if prompt:
            assert "## PR History" in prompt
            assert "PR #" in prompt

    def test_empty_when_no_results(self, empty_searcher):
        prompt = empty_searcher.search_to_prompt("anything")
        assert prompt == ""

    def test_respects_token_budget(self, searcher):
        prompt = searcher.search_to_prompt("authentication", max_tokens=50)
        # Very small budget should still produce something reasonable
        assert len(prompt) < 1000  # rough check
