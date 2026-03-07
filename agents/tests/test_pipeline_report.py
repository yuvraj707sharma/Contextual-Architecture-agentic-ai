"""
Tests for Pipeline Report — GitHub Actions-style dashboard.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from agents.pipeline_report import (
    ChangeSummary,
    PipelineReport,
    TestCheck,
    _box,
    generate_report,
)

# ── Fixtures ─────────────────────────────────────────────────

class MockMetrics:
    total_duration_ms = 1500

class MockValidation:
    passed = True
    summary = "All checks passed"
    errors = []

class MockChange:
    def __init__(self, path, change_type, risk, added=10, removed=2):
        self.file_path = path
        self.change_type = type('CT', (), {'value': change_type})()
        self.risk_level = type('RL', (), {'value': risk})()
        self.lines_added = added
        self.lines_removed = removed
        self.description = f"Changes to {path}"

class MockChangeSet:
    def __init__(self, changes):
        self.changes = changes

class MockResult:
    """Minimal mock of OrchestrationResult."""
    def __init__(self):
        self.success = True
        self.target_file = "services/auth.py"
        self.attempts = 1
        self.generated_code = "def login(): pass"
        self.metrics = MockMetrics()
        self.validation = MockValidation()
        self.changeset = MockChangeSet([
            MockChange("services/auth.py", "modify", "low", 25, 5),
            MockChange("tests/test_auth.py", "create", "safe", 40, 0),
        ])
        self.agent_summaries = {
            "historian": "Found existing auth pattern using sessions",
            "architect": "Target: services/auth.py (MODIFY)",
            "planner": "Plan created: Add JWT auth with token refresh",
            "reviewer": "All checks passed",
        }
        self.context = {
            "architect": {"target_file": "services/auth.py", "action": "MODIFY"},
            "style": {"function_naming": "snake_case", "string_style": "double"},
            "code_graph_summary": {
                "total_nodes": 150,
                "total_edges": 200,
                "functions": 80,
                "classes": 15,
                "methods": 55,
                "files": 12,
            },
            "impact_reports": [
                {"target": "services/auth.py::login", "affected_files": [
                    "services/auth.py", "api/routes.py", "tests/test_auth.py"
                ]},
            ],
            "project_snapshot": {
                "total_files": 45,
                "total_dirs": 8,
                "frameworks": ["Flask", "SQLAlchemy"],
            },
            "post_write_commands": [
                {"command": "python -m pytest tests/test_auth.py -v",
                 "reason": "Test file written", "risk": "safe", "auto": True},
                {"command": "python -m ruff check .",
                 "reason": "Lint new code", "risk": "safe", "auto": True},
            ],
        }


@pytest.fixture
def mock_result():
    return MockResult()


# ── TestCheck Tests ──────────────────────────────────────────

class TestTestCheck:
    """Test the TestCheck model."""

    def test_passed_check(self):
        check = TestCheck("Syntax", "passed", category="syntax")
        assert check.passed
        assert "✅" in check.icon
        assert "Syntax" in check.render()

    def test_failed_check(self):
        check = TestCheck("Lint", "failed", details="Line too long", category="lint")
        assert not check.passed
        assert "❌" in check.icon
        rendered = check.render()
        assert "Lint" in rendered
        assert "Line too long" in rendered

    def test_skipped_check(self):
        check = TestCheck("TypeCheck", "skipped", category="type_check")
        assert not check.passed
        assert "⏭️" in check.icon

    def test_duration_display(self):
        check = TestCheck("Tests", "passed", duration_ms=250, category="test")
        assert "250ms" in check.render()


# ── ChangeSummary Tests ──────────────────────────────────────

class TestChangeSummary:
    """Test the ChangeSummary model."""

    def test_create_change(self):
        c = ChangeSummary("new_file.py", "CREATE", lines_added=50)
        rendered = c.render()
        assert "🆕" in rendered
        assert "+50" in rendered

    def test_modify_change(self):
        c = ChangeSummary("existing.py", "MODIFY", lines_added=10, lines_removed=3)
        rendered = c.render()
        assert "📝" in rendered
        assert "+10/-3" in rendered

    def test_delete_change(self):
        c = ChangeSummary("old.py", "DELETE", lines_removed=100)
        rendered = c.render()
        assert "🗑️" in rendered


# ── PipelineReport Tests ─────────────────────────────────────

class TestPipelineReport:
    """Test the main PipelineReport class."""

    def test_from_result(self, mock_result):
        report = PipelineReport.from_result(mock_result, "./repo")
        assert report.success
        assert report.target_file == "services/auth.py"
        assert len(report.changes) == 2
        assert len(report.checks) > 0

    def test_render_full_dashboard(self, mock_result):
        report = PipelineReport.from_result(mock_result, "./repo")
        output = report.render()
        assert "PIPELINE PASSED" in output
        assert "services/auth.py" in output
        assert "Summary" in output
        assert "Changes" in output
        assert len(output) > 100

    def test_render_summary(self, mock_result):
        report = PipelineReport.from_result(mock_result, "./repo")
        summary = report.render_summary()
        assert "What was done" in summary
        assert "Historian" in summary
        assert "Architect" in summary
        assert "Planner" in summary

    def test_render_changes(self, mock_result):
        report = PipelineReport.from_result(mock_result, "./repo")
        changes = report.render_changes()
        assert "services/auth.py" in changes
        assert "test_auth.py" in changes
        assert "+65/-5" in changes  # Total

    def test_render_tests(self, mock_result):
        report = PipelineReport.from_result(mock_result, "./repo")
        tests = report.render_tests()
        assert "Syntax Check" in tests
        assert "Lint" in tests
        assert "Security" in tests

    def test_render_repo(self, mock_result):
        report = PipelineReport.from_result(mock_result, "./repo")
        repo = report.render_repo()
        assert "150 nodes" in repo
        assert "200 edges" in repo
        assert "Flask" in repo

    def test_render_git(self, mock_result):
        report = PipelineReport.from_result(mock_result, "./repo")
        git = report.render_git()
        assert "commit" in git.lower()
        assert "push" in git.lower()

    def test_render_post_write(self, mock_result):
        report = PipelineReport.from_result(mock_result, "./repo")
        pw = report.render_post_write()
        assert "pytest" in pw
        assert "ruff" in pw

    def test_commit_message_generation(self, mock_result):
        report = PipelineReport.from_result(mock_result, "./repo")
        assert report.commit_message != ""
        assert "feat" in report.commit_message or "fix" in report.commit_message

    def test_considerations(self, mock_result):
        report = PipelineReport.from_result(mock_result, "./repo")
        assert len(report.considerations) > 0

    def test_to_dict(self, mock_result):
        report = PipelineReport.from_result(mock_result, "./repo")
        d = report.to_dict()
        assert d["success"] is True
        assert len(d["changes"]) == 2
        assert len(d["checks"]) > 0

    def test_failed_pipeline(self):
        result = MockResult()
        result.success = False
        result.validation.passed = False
        result.validation.summary = "Syntax error on line 5"

        report = PipelineReport.from_result(result, "./repo")
        output = report.render()
        assert "PIPELINE FAILED" in output

    def test_multi_attempt(self):
        result = MockResult()
        result.attempts = 3

        report = PipelineReport.from_result(result, "./repo")
        header = report._render_header()
        assert "3 attempts" in header


# ── Box Drawing Tests ────────────────────────────────────────

class TestBoxDrawing:
    """Test the box drawing utility."""

    def test_box_basic(self):
        result = _box("Title", "Hello World", width=30)
        assert "Title" in result
        assert "Hello World" in result
        assert "┌" in result
        assert "┘" in result

    def test_box_multiline(self):
        result = _box("Test", "Line 1\nLine 2\nLine 3")
        assert "Line 1" in result
        assert "Line 3" in result

    def test_box_with_icon(self):
        result = _box("Status", "OK", icon="✅")
        assert "✅" in result


# ── Generate Report Tests ────────────────────────────────────

class TestGenerateReport:
    """Test the convenience function."""

    def test_generate_report(self, mock_result):
        output = generate_report(mock_result, "./repo")
        assert isinstance(output, str)
        assert len(output) > 100
        assert "PIPELINE" in output

    def test_generate_with_test_results(self, mock_result):
        test_results = [
            {"command": "pytest", "success": True, "duration_ms": 500},
            {"command": "ruff check .", "success": False, "stderr": "E501"},
        ]
        output = generate_report(mock_result, "./repo", test_results)
        assert "pytest" in output
