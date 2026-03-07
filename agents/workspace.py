"""
Workspace — Filesystem-backed working memory for the pipeline.

Implements Manus AI's key technique: use the filesystem as external memory
so context survives across agent boundaries and retries.

Critical features:
1. plan.md is RE-READ from disk on every retry (not from stale context)
2. Discovery outputs are written to files — agents have isolated contexts
3. Each attempt's code and errors are stored for the sliding window
4. Token reports are persisted for calibration over time
"""

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .logger import get_logger

logger = get_logger("workspace")


WORKSPACE_DIR = ".contextual-architect"


class Workspace:
    """Manages a .contextual-architect/ working directory inside the target repo.

    Directory structure:
        {repo}/.contextual-architect/
        ├── plan.md              # Planner output (re-read on every retry)
        ├── discovery/
        │   ├── style.json       # StyleFingerprint output
        │   ├── historian.json   # Historian patterns (budgeted)
        │   └── architect.json   # Architect mapping (focused)
        ├── attempts/
        │   ├── attempt_1.py     # Generated code per attempt
        │   ├── attempt_1_errors.json
        │   ├── attempt_2.py
        │   └── attempt_2_errors.json
        ├── output/
        │   ├── code.py          # Final approved code
        │   └── tests.py         # Generated tests
        └── reports/
            ├── token_report.json  # Token budget compliance
            └── run_metadata.json  # Full run metadata
    """

    def __init__(self, repo_path: str):
        """Initialize workspace in the target repo.

        Args:
            repo_path: Path to the target repository.
        """
        self.repo_path = Path(repo_path).resolve()
        self.workspace_path = self.repo_path / WORKSPACE_DIR
        self._ensure_dirs()
        logger.info(f"Workspace initialized at {self.workspace_path}")

    def _ensure_dirs(self) -> None:
        """Create workspace directory structure."""
        for subdir in ["discovery", "attempts", "output", "reports"]:
            (self.workspace_path / subdir).mkdir(parents=True, exist_ok=True)

        # SECURITY: Auto-create .gitignore to prevent accidental commit (VULN-4)
        gitignore_path = self.workspace_path / ".gitignore"
        if not gitignore_path.exists():
            gitignore_path.write_text(
                "# MACRO workspace — auto-generated, do not commit\n"
                "# Contains plans, generated code attempts, and reports\n"
                "*\n"
                "!.gitignore\n",
                encoding="utf-8",
            )

    # ── Plan Management ──────────────────────────────────

    def write_plan(self, plan_text: str) -> Path:
        """Write the structured plan to plan.md.

        This file is RE-READ on every retry attempt — it pushes the
        plan into the model's recent attention window (Manus technique).

        Args:
            plan_text: The Planner Agent's output (markdown).

        Returns:
            Path to the written plan file.
        """
        plan_path = self.workspace_path / "plan.md"
        plan_path.write_text(plan_text, encoding="utf-8")
        logger.info("Plan written to plan.md")
        return plan_path

    def read_plan(self) -> str:
        """Re-read the plan from disk (NOT from memory).

        This is called at the start of every Implementer retry.
        The plan is always fresh — injected into the model's
        recent attention window to fight "lost in the middle."

        Returns:
            Plan text, or empty string if no plan exists.
        """
        plan_path = self.workspace_path / "plan.md"
        if plan_path.exists():
            return plan_path.read_text(encoding="utf-8")
        logger.warning("No plan.md found in workspace")
        return ""

    def has_plan(self) -> bool:
        """Check if a plan exists in the workspace."""
        return (self.workspace_path / "plan.md").exists()

    # ── Discovery Outputs ────────────────────────────────

    def write_discovery(self, agent: str, data: Dict[str, Any]) -> Path:
        """Write an agent's discovery output to a JSON file.

        Each agent writes to its own file — they never see each other's
        raw working memory (context isolation).

        Args:
            agent: Agent name (e.g. 'historian', 'architect', 'style').
            data: The agent's output data (serializable).

        Returns:
            Path to the written file.
        """
        file_path = self.workspace_path / "discovery" / f"{agent}.json"
        file_path.write_text(
            json.dumps(data, indent=2, default=str),
            encoding="utf-8",
        )
        logger.info(f"Discovery output written: {agent}.json")
        return file_path

    def read_discovery(self, agent: str) -> Optional[Dict[str, Any]]:
        """Read an agent's discovery output from disk.

        Args:
            agent: Agent name.

        Returns:
            The agent's output data, or None if not found.
        """
        file_path = self.workspace_path / "discovery" / f"{agent}.json"
        if file_path.exists():
            return json.loads(file_path.read_text(encoding="utf-8"))
        return None

    # ── Attempt Tracking ─────────────────────────────────

    def write_attempt(
        self,
        attempt_num: int,
        code: str,
        errors: List[str],
        extension: str = "py",
    ) -> Path:
        """Store a generation attempt's code and errors.

        Used by the retry sliding window — the Orchestrator reads
        previous attempts to compress error context.

        Args:
            attempt_num: Attempt number (1-indexed).
            code: The generated code from this attempt.
            errors: Error messages from Reviewer/Alignment.
            extension: File extension for the code file.

        Returns:
            Path to the code file.
        """
        attempts_dir = self.workspace_path / "attempts"

        code_path = attempts_dir / f"attempt_{attempt_num}.{extension}"
        code_path.write_text(code, encoding="utf-8")

        errors_path = attempts_dir / f"attempt_{attempt_num}_errors.json"
        errors_path.write_text(
            json.dumps({"attempt": attempt_num, "errors": errors}, indent=2),
            encoding="utf-8",
        )

        logger.info(
            f"Attempt {attempt_num} stored: {len(code)} chars, "
            f"{len(errors)} error(s)"
        )
        return code_path

    def read_attempt(self, attempt_num: int, extension: str = "py") -> Optional[Dict[str, Any]]:
        """Read a stored attempt's code and errors.

        Args:
            attempt_num: Attempt number.
            extension: File extension.

        Returns:
            Dict with 'code' and 'errors', or None if not found.
        """
        attempts_dir = self.workspace_path / "attempts"
        code_path = attempts_dir / f"attempt_{attempt_num}.{extension}"
        errors_path = attempts_dir / f"attempt_{attempt_num}_errors.json"

        if not code_path.exists():
            return None

        result = {"code": code_path.read_text(encoding="utf-8")}
        if errors_path.exists():
            data = json.loads(errors_path.read_text(encoding="utf-8"))
            result["errors"] = data.get("errors", [])
        else:
            result["errors"] = []

        return result

    def get_attempt_count(self) -> int:
        """Count how many attempts have been stored."""
        attempts_dir = self.workspace_path / "attempts"
        return len(list(attempts_dir.glob("attempt_*_errors.json")))

    # ── Final Output ─────────────────────────────────────

    def write_output(self, filename: str, content: str) -> Path:
        """Write final approved output (code or tests).

        Args:
            filename: Output filename (e.g. 'code.py', 'tests.py').
            content: The approved content.

        Returns:
            Path to the written file.
        """
        output_path = self.workspace_path / "output" / filename
        output_path.write_text(content, encoding="utf-8")
        logger.info(f"Output written: {filename}")
        return output_path

    # ── Reports ──────────────────────────────────────────

    def write_token_report(self, report_data: Dict[str, Any]) -> Path:
        """Write token budget compliance report.

        Persisted for calibration — compare estimated vs actual
        token counts over time to tune the 1.3x multiplier.

        Args:
            report_data: BudgetReport.to_dict() output.

        Returns:
            Path to the report file.
        """
        report_data["timestamp"] = datetime.now(timezone.utc).isoformat()
        report_path = self.workspace_path / "reports" / "token_report.json"
        report_path.write_text(
            json.dumps(report_data, indent=2, default=str),
            encoding="utf-8",
        )
        logger.info("Token report written")
        return report_path

    def save_run_metadata(
        self,
        plan: str,
        code: str,
        tests: Optional[str],
        request: str,
        complexity: str,
        attempts: int,
        success: bool,
    ) -> Path:
        """Save full run metadata for feedback collection.

        This is what the Feedback Collector (Phase G) reads
        when the user reports whether generated code worked.

        Args:
            plan: The plan text.
            code: The final generated code.
            tests: Generated tests (if any).
            request: The original user request.
            complexity: Scored complexity level.
            attempts: Number of generation attempts.
            success: Whether the pipeline succeeded.

        Returns:
            Path to the metadata file.
        """
        metadata = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "request": request,
            "complexity": complexity,
            "attempts": attempts,
            "success": success,
            "plan_length": len(plan),
            "code_length": len(code),
            "tests_length": len(tests) if tests else 0,
        }
        meta_path = self.workspace_path / "reports" / "run_metadata.json"
        meta_path.write_text(
            json.dumps(metadata, indent=2),
            encoding="utf-8",
        )
        logger.info("Run metadata saved")
        return meta_path

    # ── Cleanup ──────────────────────────────────────────

    def cleanup(self) -> None:
        """Remove the entire workspace directory.

        Called after successful completion, unless --keep-workspace
        flag is set.
        """
        if self.workspace_path.exists():
            shutil.rmtree(self.workspace_path)
            logger.info("Workspace cleaned up")

    def cleanup_attempts(self) -> None:
        """Remove only the attempts directory (keep plan + output)."""
        attempts_dir = self.workspace_path / "attempts"
        if attempts_dir.exists():
            shutil.rmtree(attempts_dir)
            attempts_dir.mkdir(parents=True, exist_ok=True)
            logger.info("Attempts directory cleaned")

    # ── Utilities ────────────────────────────────────────

    @property
    def exists(self) -> bool:
        """Whether the workspace directory exists."""
        return self.workspace_path.exists()

    def __repr__(self) -> str:
        return f"Workspace({self.workspace_path})"
