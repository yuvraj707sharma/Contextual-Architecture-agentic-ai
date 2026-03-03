"""Tests for proactive ClarificationHandler conflict detection."""

import pytest
from agents.clarification_handler import ClarificationHandler, ConflictQuestion


@pytest.fixture
def handler():
    return ClarificationHandler()


class TestProactiveConflictDetection:
    """Tests for detect_conflicts() — the proactive questioning system."""

    def test_no_snapshot_returns_empty(self, handler):
        """No scanner data → no conflicts."""
        result = handler.detect_conflicts("Add login page", project_snapshot=None)
        assert result == []

    def test_empty_snapshot_returns_empty(self, handler):
        result = handler.detect_conflicts("Add login page", project_snapshot={})
        assert result == []

    def test_auth_conflict_detected(self, handler):
        """User asks for supabase but project has firebase."""
        snapshot = {"auth_systems": ["firebase"], "frameworks": [], "databases": []}
        conflicts = handler.detect_conflicts("Add supabase authentication", snapshot)
        assert len(conflicts) == 1
        assert conflicts[0].category == "auth"
        assert conflicts[0].detected == "firebase"
        assert conflicts[0].requested == "supabase"

    def test_no_auth_conflict_when_same(self, handler):
        """No conflict when user asks for auth that already exists."""
        snapshot = {"auth_systems": ["firebase"], "frameworks": [], "databases": []}
        conflicts = handler.detect_conflicts("Update firebase auth rules", snapshot)
        assert len(conflicts) == 0

    def test_no_auth_conflict_when_no_existing(self, handler):
        """No conflict when project has no existing auth."""
        snapshot = {"auth_systems": [], "frameworks": ["react"], "databases": []}
        conflicts = handler.detect_conflicts("Add supabase authentication", snapshot)
        assert len(conflicts) == 0

    def test_framework_conflict_detected(self, handler):
        """User mentions vue but project uses react."""
        snapshot = {"auth_systems": [], "frameworks": ["react"], "databases": []}
        conflicts = handler.detect_conflicts("Build a vue component", snapshot)
        assert len(conflicts) == 1
        assert conflicts[0].category == "framework"
        assert "react" in conflicts[0].detected

    def test_no_framework_conflict_across_types(self, handler):
        """React (frontend) + Express (backend) aren't conflicting."""
        snapshot = {"auth_systems": [], "frameworks": ["react"], "databases": []}
        conflicts = handler.detect_conflicts("Add express API endpoint", snapshot)
        assert len(conflicts) == 0

    def test_database_conflict_detected(self, handler):
        """User asks for postgres but project uses mongodb."""
        snapshot = {"auth_systems": [], "frameworks": [], "databases": ["mongodb"]}
        conflicts = handler.detect_conflicts("Add postgres database", snapshot)
        assert len(conflicts) == 1
        assert conflicts[0].category == "database"
        assert conflicts[0].requested == "postgresql"

    def test_language_mismatch(self, handler):
        """User specifies --lang go but project is python."""
        snapshot = {"auth_systems": [], "frameworks": [], "databases": [], "language": "python"}
        conflicts = handler.detect_conflicts("Add auth", snapshot, language="go")
        assert len(conflicts) == 1
        assert conflicts[0].category == "language"

    def test_no_language_conflict_when_same(self, handler):
        """No conflict when --lang matches project."""
        snapshot = {"auth_systems": [], "frameworks": [], "databases": [], "language": "python"}
        conflicts = handler.detect_conflicts("Add auth", snapshot, language="python")
        assert len(conflicts) == 0

    def test_multiple_conflicts(self, handler):
        """Multiple conflicts detected at once."""
        snapshot = {
            "auth_systems": ["firebase"],
            "frameworks": ["flask"],
            "databases": ["sqlite"],
        }
        conflicts = handler.detect_conflicts(
            "Migrate to supabase auth with fastapi and postgres",
            snapshot,
        )
        assert len(conflicts) >= 2  # auth + framework at minimum

    def test_deduplication(self, handler):
        """Same conflict type + requested shouldn't appear twice."""
        snapshot = {"auth_systems": ["firebase"], "frameworks": [], "databases": []}
        conflicts = handler.detect_conflicts(
            "Add supabase auth and configure supabase database",
            snapshot,
        )
        auth_conflicts = [c for c in conflicts if c.category == "auth"]
        assert len(auth_conflicts) == 1


class TestFormatting:
    """Tests for format_questions() and questions_to_context()."""

    def test_format_empty(self, handler):
        assert handler.format_questions([]) == ""

    def test_format_questions(self, handler):
        questions = [ConflictQuestion(
            category="auth",
            question="Your project uses firebase but you asked for supabase",
            detected="firebase",
            requested="supabase",
            default_action="Add supabase alongside firebase",
        )]
        formatted = handler.format_questions(questions)
        assert "firebase" in formatted
        assert "supabase" in formatted
        assert "[1]" in formatted

    def test_questions_to_context(self, handler):
        questions = [ConflictQuestion(
            category="database",
            question="DB conflict",
            detected="sqlite",
            requested="postgresql",
            default_action="Add postgresql alongside sqlite",
        )]
        ctx = handler.questions_to_context(questions)
        assert "DATABASE" in ctx
        assert "sqlite" in ctx
        assert "postgresql" in ctx


class TestReactiveClarification:
    """Tests for the existing reactive handle() method."""

    def test_no_signal_proceeds(self, handler):
        data = {"architect_plan": {"something": "normal"}}
        should_continue, processed = handler.handle(data)
        assert should_continue is True

    def test_signal_can_proceed(self, handler):
        data = {
            "signal": "CLARIFICATION_NEEDED",
            "ambiguity": "Multiple auth options",
            "can_proceed_with_default": True,
            "recommendation": "Use JWT",
            "options": ["JWT", "OAuth"],
        }
        should_continue, processed = handler.handle(data)
        assert should_continue is True
        assert "signal" not in processed

    def test_signal_halts_pipeline(self, handler):
        data = {
            "signal": "CLARIFICATION_NEEDED",
            "ambiguity": "Critical ambiguity",
            "can_proceed_with_default": False,
            "recommendation": "Ask user",
            "options": ["A", "B"],
        }
        should_continue, processed = handler.handle(data)
        assert should_continue is False
        assert processed["status"] == "clarification_required"
