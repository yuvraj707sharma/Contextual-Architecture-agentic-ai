"""
Tests for the Safe Writer module.
"""

import os
import pytest
from pathlib import Path

from ..safe_writer import (
    SafeCodeWriter,
    ProposedChange,
    ChangeSet,
    ChangeType,
    RiskLevel,
    plan_safe_changes,
)


class TestProposedChange:
    """Tests for ProposedChange dataclass."""

    def test_to_display_string_new_file(self):
        change = ProposedChange(
            file_path="auth.py",
            change_type=ChangeType.CREATE_FILE,
            risk_level=RiskLevel.SAFE,
            description="New file (25 lines)",
            new_content="def auth():\n    pass\n",
            lines_added=25,
            auto_approved=True,
        )
        display = change.to_display_string()
        assert "auth.py" in display
        assert "CREATE" in display

    def test_to_display_string_modification(self):
        change = ProposedChange(
            file_path="main.py",
            change_type=ChangeType.MODIFY_LINES,
            risk_level=RiskLevel.HIGH,
            description="Modify existing file",
            diff_lines=["+new line", "-old line"],
            lines_added=1,
            lines_removed=1,
        )
        display = change.to_display_string()
        assert "main.py" in display
        assert "MODIFY" in display


class TestChangeSet:
    """Tests for ChangeSet."""

    def _make_changeset(self):
        return ChangeSet(
            changes=[
                ProposedChange(
                    file_path="new.py",
                    change_type=ChangeType.CREATE_FILE,
                    risk_level=RiskLevel.SAFE,
                    description="New file",
                    new_content="x = 1\n",
                    auto_approved=True,
                ),
                ProposedChange(
                    file_path="old.py",
                    change_type=ChangeType.MODIFY_LINES,
                    risk_level=RiskLevel.MEDIUM,
                    description="Modify existing",
                    new_content="x = 2\n",
                ),
            ],
        )

    def test_needs_permission(self):
        cs = self._make_changeset()
        assert cs.needs_permission is True

    def test_safe_changes(self):
        cs = self._make_changeset()
        assert len(cs.safe_changes) == 1
        assert cs.safe_changes[0].file_path == "new.py"

    def test_permission_required(self):
        cs = self._make_changeset()
        assert len(cs.permission_required) == 1
        assert cs.permission_required[0].file_path == "old.py"

    def test_approve_all(self):
        cs = self._make_changeset()
        cs.approve_all()
        assert cs.all_approved is True

    def test_approve_by_index(self):
        cs = self._make_changeset()
        cs.approve_by_index([1])
        assert cs.changes[1].approved is True
        assert cs.all_approved is True

    def test_reject_by_index(self):
        cs = self._make_changeset()
        cs.reject_by_index([1])
        assert cs.changes[1].approved is False

    def test_to_user_prompt(self):
        cs = self._make_changeset()
        prompt = cs.to_user_prompt()
        assert "NEW FILES" in prompt
        assert "MODIFICATIONS" in prompt

    def test_to_dict(self):
        cs = self._make_changeset()
        d = cs.to_dict()
        assert d["total_changes"] == 2
        assert d["auto_approved"] == 1


class TestSafeCodeWriter:
    """Tests for SafeCodeWriter."""

    def test_plan_new_file(self, tmp_repo):
        writer = SafeCodeWriter(str(tmp_repo))
        changeset = writer.plan_changes(
            {"brand_new.py": 'def hello():\n    pass\n'},
            language="python",
        )

        assert len(changeset.changes) == 1
        change = changeset.changes[0]
        assert change.change_type == ChangeType.CREATE_FILE
        assert change.risk_level == RiskLevel.SAFE
        assert change.auto_approved is True

    def test_plan_existing_file_modification(self, tmp_repo):
        writer = SafeCodeWriter(str(tmp_repo))
        changeset = writer.plan_changes(
            {"src/main.py": '# completely replaced\nprint("new")\n'},
            language="python",
        )

        assert len(changeset.changes) == 1
        change = changeset.changes[0]
        assert change.change_type in (ChangeType.MODIFY_LINES, ChangeType.DELETE_LINES)
        assert change.auto_approved is False
        assert len(change.diff_lines) > 0

    def test_risk_level_critical_for_critical_files(self, tmp_repo):
        writer = SafeCodeWriter(str(tmp_repo))
        # requirements.txt is a critical file
        changeset = writer.plan_changes(
            {"requirements.txt": "flask>=3.0\n"},
            language="python",
        )

        assert len(changeset.changes) == 1
        assert changeset.changes[0].risk_level == RiskLevel.CRITICAL

    def test_risk_level_high_for_dangerous_patterns(self, tmp_repo):
        writer = SafeCodeWriter(str(tmp_repo))
        changeset = writer.plan_changes(
            {"danger.py": 'import os\nos.RemoveAll("/tmp")\n'},
            language="python",
        )

        assert changeset.changes[0].risk_level == RiskLevel.HIGH

    def test_untouched_files_tracked(self, tmp_repo):
        writer = SafeCodeWriter(str(tmp_repo))
        changeset = writer.plan_changes(
            {"brand_new.py": "x = 1\n"},
            language="python",
        )

        # Should list existing .py files as untouched
        assert len(changeset.untouched_files) > 0

    def test_apply_new_file(self, tmp_repo):
        writer = SafeCodeWriter(str(tmp_repo))
        changeset = writer.plan_changes(
            {"output.py": 'x = 42\n'},
            language="python",
        )

        report = writer.apply_changes(changeset)
        assert report["success"] is True
        assert "output.py" in report["applied"]
        assert (tmp_repo / "output.py").exists()
        assert (tmp_repo / "output.py").read_text(encoding="utf-8") == "x = 42\n"

    def test_apply_modification_creates_backup(self, tmp_repo):
        writer = SafeCodeWriter(str(tmp_repo))
        changeset = writer.plan_changes(
            {"src/main.py": '# new content\n'},
            language="python",
        )
        changeset.approve_all()

        report = writer.apply_changes(changeset)
        assert report["success"] is True
        assert len(report["backed_up"]) > 0

    def test_apply_skips_unapproved(self, tmp_repo):
        writer = SafeCodeWriter(str(tmp_repo))
        changeset = writer.plan_changes(
            {"src/main.py": '# new content\n'},
            language="python",
        )
        # Don't approve — should be skipped

        report = writer.apply_changes(changeset)
        assert "src/main.py" in report["skipped"] or "src\\main.py" in report["skipped"]

    def test_no_changes_for_identical_content(self, tmp_repo):
        """If new content == existing content, no change should be planned."""
        existing = (tmp_repo / "src" / "models.py").read_text(encoding="utf-8")
        writer = SafeCodeWriter(str(tmp_repo))
        changeset = writer.plan_changes(
            {"src/models.py": existing},
            language="python",
        )

        # Should produce no changes since content is identical
        model_changes = [c for c in changeset.changes if "models" in c.file_path]
        assert len(model_changes) == 0


class TestConvenience:
    """Tests for module-level convenience functions."""

    def test_plan_safe_changes(self, tmp_repo):
        changeset = plan_safe_changes(
            str(tmp_repo),
            {"new.py": "x = 1\n"},
            language="python",
        )
        assert isinstance(changeset, ChangeSet)
        assert len(changeset.changes) == 1
