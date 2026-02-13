"""
Tests for workspace module.

Covers:
- Workspace creation and directory structure
- Plan read/write (the core Manus technique)
- Discovery output isolation
- Attempt tracking for retry window
- Reports and metadata
- Cleanup
"""

import json
import pytest
from pathlib import Path
from agents.workspace import Workspace, WORKSPACE_DIR


@pytest.fixture
def workspace(tmp_path):
    """Create a workspace in a temporary directory."""
    ws = Workspace(str(tmp_path))
    yield ws
    # Cleanup after test
    if ws.exists:
        ws.cleanup()


# ── Workspace Creation ────────────────────────────────────

class TestWorkspaceCreation:

    def test_creates_workspace_dir(self, workspace, tmp_path):
        expected = tmp_path / WORKSPACE_DIR
        assert expected.exists()
        assert expected.is_dir()

    def test_creates_subdirs(self, workspace, tmp_path):
        base = tmp_path / WORKSPACE_DIR
        assert (base / "discovery").is_dir()
        assert (base / "attempts").is_dir()
        assert (base / "output").is_dir()
        assert (base / "reports").is_dir()

    def test_exists_property(self, workspace):
        assert workspace.exists

    def test_repr(self, workspace):
        assert "Workspace(" in repr(workspace)


# ── Plan Management ──────────────────────────────────────

class TestPlanManagement:
    """The core of the Manus technique — plan persistence."""

    def test_write_and_read_plan(self, workspace):
        plan = "## Goal\nAdd delete_task function\n\n## Acceptance Criteria\n1. Remove by ID"
        workspace.write_plan(plan)
        assert workspace.read_plan() == plan

    def test_read_plan_re_reads_from_disk(self, workspace, tmp_path):
        """Plan is always fresh — read from file, not memory."""
        workspace.write_plan("version 1")
        assert workspace.read_plan() == "version 1"

        # Simulate external modification (like plan amendment)
        plan_path = tmp_path / WORKSPACE_DIR / "plan.md"
        plan_path.write_text("version 2 — amended", encoding="utf-8")
        assert workspace.read_plan() == "version 2 — amended"

    def test_read_plan_no_file(self, workspace):
        assert workspace.read_plan() == ""

    def test_has_plan(self, workspace):
        assert not workspace.has_plan()
        workspace.write_plan("some plan")
        assert workspace.has_plan()

    def test_overwrite_plan(self, workspace):
        workspace.write_plan("first plan")
        workspace.write_plan("second plan — amended")
        assert workspace.read_plan() == "second plan — amended"


# ── Discovery Outputs ────────────────────────────────────

class TestDiscovery:
    """Agent output isolation — each agent writes to its own file."""

    def test_write_and_read_discovery(self, workspace):
        data = {"patterns": [{"type": "error_handling", "confidence": 80}]}
        workspace.write_discovery("historian", data)
        result = workspace.read_discovery("historian")
        assert result == data

    def test_agents_isolated(self, workspace):
        workspace.write_discovery("historian", {"patterns": []})
        workspace.write_discovery("architect", {"target": "app.py"})
        workspace.write_discovery("style", {"naming": "snake_case"})

        assert workspace.read_discovery("historian")["patterns"] == []
        assert workspace.read_discovery("architect")["target"] == "app.py"
        assert workspace.read_discovery("style")["naming"] == "snake_case"

    def test_read_missing_discovery(self, workspace):
        assert workspace.read_discovery("nonexistent") is None


# ── Attempt Tracking ─────────────────────────────────────

class TestAttemptTracking:

    def test_write_and_read_attempt(self, workspace):
        workspace.write_attempt(1, "def foo(): pass", ["SyntaxError: bad"])
        result = workspace.read_attempt(1)
        assert result["code"] == "def foo(): pass"
        assert result["errors"] == ["SyntaxError: bad"]

    def test_multiple_attempts(self, workspace):
        workspace.write_attempt(1, "v1", ["Error1"])
        workspace.write_attempt(2, "v2", ["Error2"])
        workspace.write_attempt(3, "v3", [])

        assert workspace.read_attempt(1)["code"] == "v1"
        assert workspace.read_attempt(2)["errors"] == ["Error2"]
        assert workspace.read_attempt(3)["errors"] == []

    def test_read_missing_attempt(self, workspace):
        assert workspace.read_attempt(99) is None

    def test_attempt_count(self, workspace):
        assert workspace.get_attempt_count() == 0
        workspace.write_attempt(1, "code", ["err"])
        assert workspace.get_attempt_count() == 1
        workspace.write_attempt(2, "code2", [])
        assert workspace.get_attempt_count() == 2

    def test_custom_extension(self, workspace):
        workspace.write_attempt(1, "package main", ["err"], extension="go")
        result = workspace.read_attempt(1, extension="go")
        assert result["code"] == "package main"


# ── Output ───────────────────────────────────────────────

class TestOutput:

    def test_write_output(self, workspace, tmp_path):
        workspace.write_output("feature.py", "def delete_task(): pass")
        path = tmp_path / WORKSPACE_DIR / "output" / "feature.py"
        assert path.exists()
        assert path.read_text(encoding="utf-8") == "def delete_task(): pass"

    def test_write_tests_output(self, workspace, tmp_path):
        workspace.write_output("test_feature.py", "def test_delete(): assert True")
        path = tmp_path / WORKSPACE_DIR / "output" / "test_feature.py"
        assert path.exists()


# ── Reports ──────────────────────────────────────────────

class TestReports:

    def test_write_token_report(self, workspace, tmp_path):
        report_data = {
            "total_estimated": 5000,
            "total_budget": 10000,
            "violations": [],
        }
        workspace.write_token_report(report_data)
        path = tmp_path / WORKSPACE_DIR / "reports" / "token_report.json"
        assert path.exists()
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["total_estimated"] == 5000
        assert "timestamp" in data

    def test_save_run_metadata(self, workspace, tmp_path):
        workspace.save_run_metadata(
            plan="## Plan",
            code="def foo(): pass",
            tests="def test_foo(): pass",
            request="Add foo",
            complexity="simple",
            attempts=1,
            success=True,
        )
        path = tmp_path / WORKSPACE_DIR / "reports" / "run_metadata.json"
        assert path.exists()
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["request"] == "Add foo"
        assert data["complexity"] == "simple"
        assert data["success"] is True
        assert data["attempts"] == 1


# ── Cleanup ──────────────────────────────────────────────

class TestCleanup:

    def test_cleanup_removes_workspace(self, tmp_path):
        ws = Workspace(str(tmp_path))
        assert ws.exists
        ws.cleanup()
        assert not ws.exists

    def test_cleanup_attempts_only(self, workspace):
        workspace.write_plan("keep me")
        workspace.write_attempt(1, "code", ["err"])
        workspace.write_attempt(2, "code2", ["err2"])
        assert workspace.get_attempt_count() == 2

        workspace.cleanup_attempts()
        assert workspace.get_attempt_count() == 0
        assert workspace.read_plan() == "keep me"  # Plan preserved
