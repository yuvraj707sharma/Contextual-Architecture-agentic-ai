"""
Tests for the Feedback Collector.
"""

import json
import os
import pytest
import tempfile

from ..feedback import FeedbackCollector, FeedbackEntry


# ── FeedbackEntry ────────────────────────────────────────────


class TestFeedbackEntry:
    def test_to_dict(self):
        entry = FeedbackEntry(
            request="Add auth",
            success=True,
            attempts=2,
            errors=["syntax error"],
        )
        d = entry.to_dict()
        assert d["request"] == "Add auth"
        assert d["success"] is True
        assert d["attempts"] == 2
        assert d["errors"] == ["syntax error"]
        assert "timestamp" in d

    def test_to_json(self):
        entry = FeedbackEntry(request="test", success=True)
        j = entry.to_json()
        parsed = json.loads(j)
        assert parsed["request"] == "test"

    def test_from_dict(self):
        data = {"request": "Add cache", "success": False, "attempts": 3}
        entry = FeedbackEntry.from_dict(data)
        assert entry.request == "Add cache"
        assert entry.success is False
        assert entry.attempts == 3

    def test_from_dict_ignores_unknown_keys(self):
        data = {"request": "test", "success": True, "unknown_field": "value"}
        entry = FeedbackEntry.from_dict(data)
        assert entry.request == "test"
        assert not hasattr(entry, "unknown_field")

    def test_from_json(self):
        line = '{"request": "Add logging", "success": true, "attempts": 1}'
        entry = FeedbackEntry.from_json(line)
        assert entry.request == "Add logging"
        assert entry.success is True

    def test_roundtrip(self):
        original = FeedbackEntry(
            request="Add auth",
            success=True,
            attempts=2,
            errors=["err1"],
            changes_applied=3,
            changes_skipped=1,
            duration_ms=1500.0,
            language="python",
            complexity="medium",
        )
        restored = FeedbackEntry.from_json(original.to_json())
        assert restored.request == original.request
        assert restored.success == original.success
        assert restored.attempts == original.attempts
        assert restored.errors == original.errors
        assert restored.changes_applied == original.changes_applied
        assert restored.duration_ms == original.duration_ms


# ── FeedbackCollector.save / .load ───────────────────────────


class TestSaveLoad:
    @pytest.fixture
    def collector(self):
        return FeedbackCollector()

    @pytest.fixture
    def feedback_file(self, tmp_path):
        return str(tmp_path / "feedback.jsonl")

    def test_save_creates_file(self, collector, feedback_file):
        entry = FeedbackEntry(request="test", success=True)
        collector.save(entry, feedback_file)
        assert os.path.exists(feedback_file)

    def test_save_appends(self, collector, feedback_file):
        e1 = FeedbackEntry(request="first", success=True)
        e2 = FeedbackEntry(request="second", success=False)
        collector.save(e1, feedback_file)
        collector.save(e2, feedback_file)

        entries = collector.load(feedback_file)
        assert len(entries) == 2
        assert entries[0].request == "first"
        assert entries[1].request == "second"

    def test_load_empty_file(self, collector, tmp_path):
        path = str(tmp_path / "empty.jsonl")
        open(path, "w").close()
        entries = collector.load(path)
        assert entries == []

    def test_load_nonexistent_file(self, collector):
        entries = collector.load("/tmp/does_not_exist_12345.jsonl")
        assert entries == []

    def test_load_skips_malformed_lines(self, collector, tmp_path):
        path = str(tmp_path / "mixed.jsonl")
        with open(path, "w") as f:
            f.write('{"request": "good", "success": true}\n')
            f.write("this is not json\n")
            f.write('{"request": "also good", "success": false}\n')

        entries = collector.load(path)
        assert len(entries) == 2


# ── FeedbackCollector.collect ────────────────────────────────


class TestCollect:
    @pytest.fixture
    def collector(self):
        return FeedbackCollector()

    def test_collect_from_result_object(self, collector):
        """Test collecting from a mock OrchestrationResult-like object."""

        class MockResult:
            success = True
            attempts = 2
            errors = ["minor warning"]
            metrics = None
            changeset = None
            context = {}
            generated_code = "def hello(): pass"
            agent_summaries = {"historian": "Found patterns"}

        entry = collector.collect(MockResult())
        assert entry.success is True
        assert entry.attempts == 2
        assert entry.errors == ["minor warning"]

    def test_collect_with_metrics(self, collector):
        class MockMetrics:
            total_duration_ms = 2500.0

        class MockResult:
            success = True
            attempts = 1
            errors = []
            metrics = MockMetrics()
            changeset = None
            context = {}
            generated_code = ""
            agent_summaries = {}

        entry = collector.collect(MockResult())
        assert entry.duration_ms == 2500.0


# ── FeedbackCollector.summary ────────────────────────────────


class TestSummary:
    @pytest.fixture
    def collector(self):
        return FeedbackCollector()

    def test_summary_empty(self, collector):
        s = collector.summary([])
        assert s["total_runs"] == 0
        assert s["success_rate"] == 0.0

    def test_summary_basic(self, collector):
        entries = [
            FeedbackEntry(request="a", success=True, attempts=1, duration_ms=1000),
            FeedbackEntry(request="b", success=True, attempts=2, duration_ms=2000),
            FeedbackEntry(request="c", success=False, attempts=3, duration_ms=3000, errors=["fail"]),
        ]
        s = collector.summary(entries)
        assert s["total_runs"] == 3
        assert abs(s["success_rate"] - 2 / 3) < 0.01
        assert abs(s["avg_attempts"] - 2.0) < 0.01
        assert abs(s["avg_duration_ms"] - 2000.0) < 0.01

    def test_summary_common_errors(self, collector):
        entries = [
            FeedbackEntry(request="a", success=False, errors=["syntax error"]),
            FeedbackEntry(request="b", success=False, errors=["syntax error"]),
            FeedbackEntry(request="c", success=False, errors=["import error"]),
        ]
        s = collector.summary(entries)
        assert len(s["common_errors"]) > 0
        assert s["common_errors"][0]["error"] == "syntax error"
        assert s["common_errors"][0]["count"] == 2

    def test_summary_from_path(self, collector, tmp_path):
        path = str(tmp_path / "fb.jsonl")
        collector.save(FeedbackEntry(request="x", success=True), path)
        collector.save(FeedbackEntry(request="y", success=False), path)

        s = collector.summary(path=path)
        assert s["total_runs"] == 2

    def test_summary_text(self, collector):
        entries = [
            FeedbackEntry(request="a", success=True, duration_ms=500, attempts=1),
        ]
        text = collector.summary_text(entries)
        assert "100%" in text
        assert "500ms" in text

    def test_summary_text_empty(self, collector):
        text = collector.summary_text([])
        assert "No feedback" in text
