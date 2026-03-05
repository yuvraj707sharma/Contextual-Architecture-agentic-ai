"""
Pipeline Report — GitHub Actions-style results dashboard for MACRO.

After MACRO generates code, this module produces a rich, formatted report
showing the user:

1. SUMMARY PANEL — What was done, why, and what was considered
2. TEST/CI PANEL — Test + lint results (like GitHub Actions checks)
3. REPO PANEL — Graph stats, impact analysis, affected files
4. GIT PANEL — Auto-generated commit message + push commands

Usage:
    from agents.pipeline_report import PipelineReport
    
    report = PipelineReport.from_result(orchestration_result, repo_path)
    print(report.render())           # Full dashboard
    print(report.render_summary())   # Just the summary panel
    print(report.render_tests())     # Just the test/CI panel
    print(report.render_git())       # Git commit + push suggestions
"""

import hashlib
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


# ── Box Drawing Characters ───────────────────────────────────

BOX_H = "─"
BOX_V = "│"
BOX_TL = "┌"
BOX_TR = "┐"
BOX_BL = "└"
BOX_BR = "┘"
BOX_LT = "├"
BOX_RT = "┤"
BOX_DIVIDER = "─"


def _box(title: str, content: str, width: int = 70, icon: str = "") -> str:
    """Draw a box around content with a title bar."""
    header = f"{icon} {title}" if icon else title
    top = f"{BOX_TL}{BOX_H * 2} {header} {BOX_H * max(0, width - len(header) - 5)}{BOX_TR}"
    bottom = f"{BOX_BL}{BOX_H * (width - 1)}{BOX_BR}"

    lines = content.split("\n")
    body = "\n".join(
        f"{BOX_V} {line:<{width - 3}}{BOX_V}" for line in lines
    )
    return f"{top}\n{body}\n{bottom}"


def _status_icon(passed: bool) -> str:
    return "✅" if passed else "❌"


def _risk_icon(risk: str) -> str:
    icons = {
        "safe": "✅", "low": "ℹ️", "medium": "⚠️",
        "high": "🔴", "blocked": "🚫",
    }
    return icons.get(risk, "")


# ── Test Result Model ────────────────────────────────────────

@dataclass
class TestCheck:
    """A single CI-style check (like a GitHub Actions job)."""
    name: str
    status: str  # "passed", "failed", "skipped", "pending"
    details: str = ""
    duration_ms: int = 0
    category: str = "test"  # "test", "lint", "type_check", "security"

    @property
    def passed(self) -> bool:
        return self.status == "passed"

    @property
    def icon(self) -> str:
        return {
            "passed": "✅",
            "failed": "❌",
            "skipped": "⏭️",
            "pending": "⏳",
            "warning": "⚠️",
        }.get(self.status, "❓")

    def render(self) -> str:
        dur = f" ({self.duration_ms}ms)" if self.duration_ms > 0 else ""
        line = f"  {self.icon} {self.name}{dur}"
        if self.details and self.status == "failed":
            # Show first line of error
            first_line = self.details.split("\n")[0][:60]
            line += f"\n      └─ {first_line}"
        return line


# ── Change Summary Model ─────────────────────────────────────

@dataclass
class ChangeSummary:
    """Summary of a single file change."""
    file_path: str
    action: str  # "CREATE", "MODIFY", "DELETE"
    lines_added: int = 0
    lines_removed: int = 0
    risk: str = "safe"
    description: str = ""

    def render(self) -> str:
        action_icons = {
            "CREATE": "🆕",
            "MODIFY": "📝",
            "DELETE": "🗑️",
        }
        icon = action_icons.get(self.action.upper(), "")
        diff_str = ""
        if self.lines_added > 0 or self.lines_removed > 0:
            diff_str = f" (+{self.lines_added}/-{self.lines_removed})"
        return f"  {icon} [{self.action}] {self.file_path}{diff_str}"


# ── Pipeline Report ──────────────────────────────────────────

@dataclass
class PipelineReport:
    """Complete pipeline results dashboard.

    Mirrors the GitHub Actions / PR check experience:
    - Summary: what, why, considerations
    - Checks: test + lint results
    - Changes: files modified with diffs
    - Repo: graph stats, impact
    - Git: commit message + push commands
    """

    # ── Summary
    request: str = ""
    success: bool = False
    target_file: str = ""
    complexity: str = "simple"
    pipeline_duration_ms: int = 0
    attempts: int = 1

    # ── Agent Reasoning
    agent_summaries: Dict[str, str] = field(default_factory=dict)
    considerations: List[str] = field(default_factory=list)

    # ── Changes
    changes: List[ChangeSummary] = field(default_factory=list)

    # ── Test / CI Checks
    checks: List[TestCheck] = field(default_factory=list)

    # ── Repo Details
    graph_summary: Dict[str, Any] = field(default_factory=dict)
    impact_reports: List[Dict] = field(default_factory=list)
    project_files: int = 0
    project_dirs: int = 0
    frameworks: List[str] = field(default_factory=list)

    # ── Git
    commit_message: str = ""
    git_commands: List[str] = field(default_factory=list)

    # ── Post-write Commands
    post_write_commands: List[Dict] = field(default_factory=list)

    @classmethod
    def from_result(
        cls,
        result,
        repo_path: str = "",
        test_results: Optional[List] = None,
    ) -> "PipelineReport":
        """Build a PipelineReport from an OrchestrationResult.

        This is the main constructor — takes the raw orchestration output
        and builds a structured, displayable report.
        """
        report = cls()

        # Basic info
        report.request = result.context.get("user_request", "")
        report.success = result.success
        report.target_file = result.target_file
        report.attempts = result.attempts
        report.agent_summaries = result.agent_summaries.copy()

        if result.metrics:
            report.pipeline_duration_ms = int(result.metrics.total_duration_ms)

        # Complexity from planner
        plan_data = result.context.get("plan", {})
        if isinstance(plan_data, dict):
            report.complexity = plan_data.get("complexity", "medium")

        # Changes from changeset
        if result.changeset:
            for change in result.changeset.changes:
                report.changes.append(ChangeSummary(
                    file_path=change.file_path,
                    action=change.change_type.value.upper() if hasattr(change.change_type, 'value') else str(change.change_type),
                    lines_added=change.lines_added,
                    lines_removed=change.lines_removed,
                    risk=change.risk_level.value if hasattr(change.risk_level, 'value') else str(change.risk_level),
                    description=change.description,
                ))

        # Graph summary
        report.graph_summary = result.context.get("code_graph_summary", {})
        report.impact_reports = result.context.get("impact_reports", [])

        # Project info from scanner
        snapshot = result.context.get("project_snapshot", {})
        if isinstance(snapshot, dict):
            report.project_files = snapshot.get("total_files", 0)
            report.project_dirs = snapshot.get("total_dirs", 0)
            report.frameworks = snapshot.get("frameworks", [])

        # Post-write commands
        report.post_write_commands = result.context.get("post_write_commands", [])

        # Generate considerations from agent summaries
        report.considerations = cls._extract_considerations(result)

        # Generate git commands
        report.commit_message = cls._generate_commit_message(result)
        report.git_commands = cls._generate_git_commands(result, repo_path)

        # Build test checks from reviewer + post-write results
        report.checks = cls._build_checks(result, test_results)

        return report

    # ── Rendering ─────────────────────────────────────────────

    def render(self, width: int = 70) -> str:
        """Render the full dashboard."""
        sections = []
        sections.append(self._render_header(width))
        sections.append(self.render_summary(width))
        sections.append(self.render_changes(width))
        sections.append(self.render_tests(width))
        sections.append(self.render_repo(width))
        sections.append(self.render_git(width))

        if self.post_write_commands:
            sections.append(self.render_post_write(width))

        return "\n\n".join(s for s in sections if s)

    def _render_header(self, width: int = 70) -> str:
        """Pipeline result header."""
        status = "✅ PIPELINE PASSED" if self.success else "❌ PIPELINE FAILED"
        dur = f" in {self.pipeline_duration_ms}ms" if self.pipeline_duration_ms else ""
        attempts = f" ({self.attempts} attempt{'s' if self.attempts > 1 else ''})" if self.attempts > 1 else ""

        return _box(
            f"{status}{dur}{attempts}",
            f"Request: {self.request[:60]}{'...' if len(self.request) > 60 else ''}\n"
            f"Target:  {self.target_file}\n"
            f"Complexity: {self.complexity}",
            width,
            icon="🔄",
        )

    def render_summary(self, width: int = 70) -> str:
        """SUMMARY PANEL — What was done, why, and what was considered."""
        lines = []

        # What was done
        if self.agent_summaries:
            lines.append("📋 What was done:")
            for agent, summary in self.agent_summaries.items():
                if agent in ("conflicts",):
                    continue
                emoji = {
                    "historian": "📚", "architect": "🏗️",
                    "planner": "📝", "reviewer": "🔍",
                    "test_generator": "🧪", "alignment": "⚖️",
                    "clarification": "❓",
                }.get(agent, "▸")
                lines.append(f"  {emoji} {agent.title()}: {summary[:80]}")

        # Why — reasoning chain
        if self.considerations:
            lines.append("")
            lines.append("💡 Why these decisions:")
            for c in self.considerations[:5]:
                lines.append(f"  • {c[:75]}")

        if not lines:
            return ""

        return _box("Summary", "\n".join(lines), width, icon="📊")

    def render_changes(self, width: int = 70) -> str:
        """CHANGES PANEL — Files modified."""
        if not self.changes:
            return ""

        lines = [f"Total: {len(self.changes)} file(s) affected\n"]

        for change in self.changes:
            lines.append(change.render())

        total_added = sum(c.lines_added for c in self.changes)
        total_removed = sum(c.lines_removed for c in self.changes)
        lines.append(f"\n  Net: +{total_added}/-{total_removed} lines")

        return _box("Changes", "\n".join(lines), width, icon="📁")

    def render_tests(self, width: int = 70) -> str:
        """TEST/CI PANEL — Like GitHub Actions checks view."""
        if not self.checks:
            return ""

        # Group by category
        categories = {}
        for check in self.checks:
            cat = check.category
            categories.setdefault(cat, []).append(check)

        lines = []
        total_pass = sum(1 for c in self.checks if c.passed)
        total = len(self.checks)
        overall = "✅" if total_pass == total else "❌"
        lines.append(f"{overall} {total_pass}/{total} checks passed\n")

        category_labels = {
            "lint": "🧹 Linting",
            "type_check": "🔤 Type Checking",
            "security": "🔒 Security",
            "test": "🧪 Tests",
            "syntax": "📝 Syntax",
        }

        for cat, checks in categories.items():
            cat_pass = all(c.passed for c in checks)
            cat_icon = _status_icon(cat_pass)
            cat_label = category_labels.get(cat, cat.title())
            lines.append(f"  {cat_icon} {cat_label}")

            for check in checks:
                lines.append(f"  {check.render()}")
            lines.append("")

        return _box("CI Checks", "\n".join(lines), width, icon="🏗️")

    def render_repo(self, width: int = 70) -> str:
        """REPO PANEL — Graph stats, project info."""
        lines = []

        if self.project_files > 0:
            lines.append(f"📁 Project: {self.project_files} files, {self.project_dirs} dirs")

        if self.frameworks:
            lines.append(f"🔧 Frameworks: {', '.join(self.frameworks)}")

        if self.graph_summary:
            gs = self.graph_summary
            lines.append(
                f"🕸️  Code Graph: {gs.get('total_nodes', 0)} nodes, "
                f"{gs.get('total_edges', 0)} edges"
            )
            lines.append(
                f"    {gs.get('functions', 0)} functions, "
                f"{gs.get('classes', 0)} classes, "
                f"{gs.get('methods', 0)} methods"
            )

        if self.impact_reports:
            lines.append(f"\n📌 Impact Analysis:")
            for ir in self.impact_reports[:3]:
                target = ir.get("target", "?")
                affected = ir.get("affected_files", [])
                lines.append(
                    f"  • {target} → {len(affected)} file(s) affected"
                )

        if not lines:
            return ""

        return _box("Repository", "\n".join(lines), width, icon="📦")

    def render_git(self, width: int = 70) -> str:
        """GIT PANEL — Commit message + push commands."""
        if not self.commit_message and not self.git_commands:
            return ""

        lines = []
        if self.commit_message:
            lines.append("💬 Suggested commit message:")
            lines.append(f'  git commit -m "{self.commit_message}"')

        if self.git_commands:
            lines.append("\n📤 Git commands:")
            for cmd in self.git_commands:
                lines.append(f"  $ {cmd}")

        return _box("Git", "\n".join(lines), width, icon="🔀")

    def render_post_write(self, width: int = 70) -> str:
        """POST-WRITE PANEL — Suggested commands to run."""
        if not self.post_write_commands:
            return ""

        lines = ["Suggested commands to run:\n"]
        for i, cmd in enumerate(self.post_write_commands, 1):
            risk_icon = _risk_icon(cmd.get("risk", ""))
            auto = " (auto)" if cmd.get("auto") else ""
            lines.append(
                f"  {i}. {risk_icon} {cmd['command']}{auto}\n"
                f"     └─ {cmd.get('reason', '')}"
            )

        return _box("Next Steps", "\n".join(lines), width, icon="▶️")

    def to_dict(self) -> dict:
        """Serialize for JSON output."""
        return {
            "success": self.success,
            "request": self.request,
            "target_file": self.target_file,
            "complexity": self.complexity,
            "duration_ms": self.pipeline_duration_ms,
            "attempts": self.attempts,
            "changes": [
                {"file": c.file_path, "action": c.action,
                 "added": c.lines_added, "removed": c.lines_removed}
                for c in self.changes
            ],
            "checks": [
                {"name": c.name, "status": c.status,
                 "category": c.category, "duration_ms": c.duration_ms}
                for c in self.checks
            ],
            "graph": self.graph_summary,
            "commit_message": self.commit_message,
            "git_commands": self.git_commands,
        }

    # ── Internal Helpers ──────────────────────────────────────

    @staticmethod
    def _extract_considerations(result) -> List[str]:
        """Extract reasoning considerations from agent outputs."""
        considerations = []

        # From architect
        architect = result.context.get("architect", {})
        if isinstance(architect, dict):
            if architect.get("target_file"):
                considerations.append(
                    f"Target file: {architect['target_file']} "
                    f"(action: {architect.get('action', 'create')})"
                )

        # From reviewer
        if result.validation:
            if result.validation.passed:
                considerations.append(f"Code passed review: {result.validation.summary}")
            else:
                considerations.append(f"Review issues: {result.validation.summary}")

        # From conflicts
        conflicts = result.agent_summaries.get("conflicts", [])
        if isinstance(conflicts, list):
            for c in conflicts[:2]:
                if isinstance(c, dict):
                    considerations.append(
                        f"Conflict detected: {c.get('category', '?')} — "
                        f"project has {c.get('detected', '?')}, "
                        f"request wants {c.get('requested', '?')}"
                    )

        # From style
        style = result.context.get("style", {})
        if isinstance(style, dict) and style.get("function_naming"):
            considerations.append(
                f"Matched project style: {style['function_naming']} naming, "
                f"{style.get('string_style', '?')} strings"
            )

        return considerations

    @staticmethod
    def _generate_commit_message(result) -> str:
        """Generate a conventional commit message from the result."""
        if not result.success:
            return ""

        # Determine type from agent summaries
        planner_summary = result.agent_summaries.get("planner", "").lower()

        if "fix" in planner_summary or "bug" in planner_summary:
            prefix = "fix"
        elif "test" in planner_summary:
            prefix = "test"
        elif "refactor" in planner_summary:
            prefix = "refactor"
        elif "add" in planner_summary or "implement" in planner_summary:
            prefix = "feat"
        else:
            prefix = "feat"

        # Extract scope from target file
        target = result.target_file
        if target:
            scope = Path(target).stem
            # Clean up: rate_limiter → rate-limiter
            scope = scope.replace("_", "-")
        else:
            scope = "core"

        # Description from planner
        desc = result.agent_summaries.get("planner", "update code")
        # Trim to just the first meaningful part
        desc = desc.split(",")[0].split("(")[0].strip()
        # Remove "Plan created: " prefix if present
        desc = re.sub(r"^Plan created:\s*", "", desc)
        # Lowercase first char
        if desc:
            desc = desc[0].lower() + desc[1:]

        return f"{prefix}({scope}): {desc[:50]}"

    @staticmethod
    def _generate_git_commands(result, repo_path: str) -> List[str]:
        """Generate git commands for committing and pushing."""
        if not result.success:
            return []

        commands = []

        # Add changed files
        if result.changeset:
            files = [c.file_path for c in result.changeset.changes]
            if files:
                commands.append(f"git add {' '.join(files[:5])}")

        # Commit (placeholder — actual message set separately)
        commands.append('git commit -m "<commit-message>"')

        # Push
        commands.append("git push origin HEAD")

        return commands

    @staticmethod
    def _build_checks(result, test_results=None) -> List[TestCheck]:
        """Build CI-style check list from reviewer + test results."""
        checks = []

        # Reviewer checks
        if result.validation:
            # Syntax check
            syntax_passed = not any(
                "syntax" in str(getattr(e, 'category', '')).lower()
                for e in getattr(result.validation, 'errors', [])
            )
            checks.append(TestCheck(
                name="Syntax Check",
                status="passed" if syntax_passed else "failed",
                category="syntax",
            ))

            # Lint check
            lint_passed = not any(
                "lint" in str(getattr(e, 'category', '')).lower()
                for e in getattr(result.validation, 'errors', [])
            )
            checks.append(TestCheck(
                name="Lint (ruff/eslint)",
                status="passed" if lint_passed else "failed",
                category="lint",
                details="" if lint_passed else "Lint issues found",
            ))

            # Security check
            security_passed = not any(
                "security" in str(getattr(e, 'category', '')).lower() or
                "cwe" in str(getattr(e, 'rule', '')).lower()
                for e in getattr(result.validation, 'errors', [])
            )
            checks.append(TestCheck(
                name="Security (CWE denylist)",
                status="passed" if security_passed else "failed",
                category="security",
            ))

            # Overall review
            checks.append(TestCheck(
                name="Code Review",
                status="passed" if result.validation.passed else "failed",
                category="test",
                details=result.validation.summary,
            ))

        # Test results from ShellExecutor
        if test_results:
            for tr in test_results:
                if isinstance(tr, dict):
                    checks.append(TestCheck(
                        name=tr.get("command", "test"),
                        status="passed" if tr.get("success") else "failed",
                        details=tr.get("stderr", tr.get("stdout", "")),
                        duration_ms=tr.get("duration_ms", 0),
                        category="test",
                    ))

        return checks


# ── Standalone Report Generator ──────────────────────────────

def generate_report(
    result,
    repo_path: str = "",
    test_results: Optional[List] = None,
    width: int = 70,
) -> str:
    """One-liner to generate a full pipeline report.

    Usage:
        from agents.pipeline_report import generate_report
        report_str = generate_report(orchestration_result, "./my-repo")
        print(report_str)
    """
    report = PipelineReport.from_result(result, repo_path, test_results)
    return report.render(width=width)
