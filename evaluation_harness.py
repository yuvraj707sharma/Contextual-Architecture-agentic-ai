"""
Real-LLM Evaluation Harness for Contextual Architect.

Runs the full pipeline against real repos with a real LLM to validate
that constraint prompts produce correct, convention-aware output.

Usage:
    python evaluation_harness.py --provider groq
    python evaluation_harness.py --provider groq --task simple-health-check
    python evaluation_harness.py --provider google
"""

import argparse
import asyncio
import json
import os
import re
import sys
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

# Fix Windows console encoding
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def _ok(label: str) -> str:
    return f"[PASS] {label}"


def _fail(label: str) -> str:
    return f"[FAIL] {label}"


def _status(passed: bool, label: str) -> str:
    return _ok(label) if passed else _fail(label)


# ─── Data Classes ─────────────────────────────────────────────


@dataclass
class EvaluationCase:
    """A single evaluation task."""

    task_id: str
    task_description: str
    repo_path: str
    language: str
    expected_behaviors: list
    security_traps: list = field(default_factory=list)


@dataclass
class AgentTelemetry:
    """Per-agent telemetry."""

    agent_name: str
    ran: bool = False
    success: bool = False
    summary: str = ""
    data_keys: list = field(default_factory=list)
    duration_ms: float = 0.0


@dataclass
class ConstraintCheckResult:
    """Result of automated constraint validation."""

    check_name: str
    passed: bool
    details: str = ""


@dataclass
class EvaluationResult:
    """Full result of running one evaluation case."""

    task_id: str
    success: bool
    pipeline_status: str  # "approved" | "changes_requested" | "pipeline_error"
    total_time_ms: float
    attempts: int
    generated_code: str = ""
    target_file: str = ""

    # Per-agent telemetry
    agent_telemetry: list = field(default_factory=list)

    # Automated constraint checks
    constraint_checks: list = field(default_factory=list)

    # Errors
    errors: list = field(default_factory=list)

    # Raw agent summaries
    agent_summaries: dict = field(default_factory=dict)

    notes: str = ""


# ─── Evaluation Suite ─────────────────────────────────────────

FASTAPI_REPO = str(
    Path(__file__).parent.parent / "test-projects" / "fastapi-app" / "backend"
)

EVALUATION_SUITE = [
    EvaluationCase(
        task_id="simple-health-check",
        task_description=(
            "Add a /health endpoint that returns {'status': 'ok'}. "
            "It should follow the existing route patterns in app/api/routes/."
        ),
        repo_path=FASTAPI_REPO,
        language="python",
        expected_behaviors=[
            "Uses APIRouter pattern matching existing routes",
            "Returns JSON response",
            "Follows existing naming conventions (snake_case)",
            "Creates file in app/api/routes/ directory",
        ],
    ),
    EvaluationCase(
        task_id="security-input-validation",
        task_description=(
            "Add input validation to the user creation endpoint in "
            "app/api/routes/users.py. Ensure email format validation, "
            "password strength checks, and proper error responses."
        ),
        repo_path=FASTAPI_REPO,
        language="python",
        expected_behaviors=[
            "Uses Pydantic models or Field() for validation",
            "Does NOT use assert for validation",
            "SQL queries are parameterized (SQLModel ORM)",
            "Uses HTTPException for error responses",
        ],
        security_traps=[
            "assert for validation (CWE banned)",
            "f-string SQL (CWE-89)",
            "eval() on user input (CWE-502)",
            "bare except: (CWE)",
        ],
    ),
    EvaluationCase(
        task_id="complex-refactor",
        task_description=(
            "Refactor the database module (app/crud.py) to use the "
            "repository pattern. Extract CRUD operations into a "
            "UserRepository class and ItemRepository class."
        ),
        repo_path=FASTAPI_REPO,
        language="python",
        expected_behaviors=[
            "Architect identifies crud.py + models.py + route files as coupled",
            "Creates UserRepository and ItemRepository classes",
            "Maintains existing function signatures or provides adapters",
            "Does not break existing imports",
        ],
    ),
]


# ─── Constraint Checker ──────────────────────────────────────


class ConstraintChecker:
    """Automated post-hoc validation of generated code against constraints."""

    def check_all(
        self, case: EvaluationCase, code: str, agent_summaries: dict
    ) -> list:
        checks = []

        # Code-level checks
        if code:
            checks.extend(self._check_security_denylist(code))
            checks.extend(self._check_pattern_compliance(case, code))

        # Agent-level checks
        checks.extend(self._check_agent_outputs(agent_summaries))

        return checks

    def _check_security_denylist(self, code: str) -> list:
        """Check generated code against CWE denylist."""
        checks = []

        # CWE-502: eval/exec
        has_eval = bool(re.search(r"\beval\s*\(", code))
        has_exec = bool(re.search(r"\bexec\s*\(", code))
        checks.append(ConstraintCheckResult(
            check_name="CWE-502: No eval/exec",
            passed=not (has_eval or has_exec),
            details=f"eval={'found' if has_eval else 'clean'}, exec={'found' if has_exec else 'clean'}",
        ))

        # CWE-89: SQL injection
        has_fstring_sql = bool(re.search(
            r'f["\'].*(?:SELECT|INSERT|UPDATE|DELETE|DROP)', code, re.IGNORECASE
        ))
        checks.append(ConstraintCheckResult(
            check_name="CWE-89: No f-string SQL",
            passed=not has_fstring_sql,
            details="f-string SQL found" if has_fstring_sql else "clean",
        ))

        # CWE: No assert for validation
        has_assert_validation = bool(re.search(
            r"\bassert\b.*(?:len|email|password|valid|input)", code, re.IGNORECASE
        ))
        checks.append(ConstraintCheckResult(
            check_name="No assert for validation",
            passed=not has_assert_validation,
            details="assert used for validation" if has_assert_validation else "clean",
        ))

        # CWE-78: os.system / shell=True
        has_os_system = bool(re.search(r"\bos\.system\s*\(", code))
        has_shell_true = bool(re.search(r"shell\s*=\s*True", code))
        checks.append(ConstraintCheckResult(
            check_name="CWE-78: No OS command injection",
            passed=not (has_os_system or has_shell_true),
            details=f"os.system={'found' if has_os_system else 'clean'}, shell=True={'found' if has_shell_true else 'clean'}",
        ))

        # Bare except
        has_bare_except = bool(re.search(r"\bexcept\s*:", code))
        checks.append(ConstraintCheckResult(
            check_name="No bare except:",
            passed=not has_bare_except,
            details="bare except: found" if has_bare_except else "clean",
        ))

        return checks

    def _check_pattern_compliance(self, case: EvaluationCase, code: str) -> list:
        """Check if code follows expected project patterns."""
        checks = []

        if case.task_id == "simple-health-check":
            has_router = "APIRouter" in code or "router" in code
            checks.append(ConstraintCheckResult(
                check_name="Uses APIRouter pattern",
                passed=has_router,
                details="APIRouter/router pattern found" if has_router else "missing",
            ))

            has_json_response = "JSONResponse" in code or '{"status"' in code or "{'status'" in code or "status" in code.lower()
            checks.append(ConstraintCheckResult(
                check_name="Returns JSON health response",
                passed=has_json_response,
                details="JSON response pattern found" if has_json_response else "missing",
            ))

        elif case.task_id == "security-input-validation":
            has_pydantic = "Field(" in code or "BaseModel" in code or "SQLModel" in code
            checks.append(ConstraintCheckResult(
                check_name="Uses Pydantic/SQLModel validation",
                passed=has_pydantic,
                details="Pydantic/SQLModel validation found" if has_pydantic else "missing",
            ))

            has_http_exception = "HTTPException" in code
            checks.append(ConstraintCheckResult(
                check_name="Uses HTTPException for errors",
                passed=has_http_exception,
                details="HTTPException found" if has_http_exception else "missing",
            ))

        elif case.task_id == "complex-refactor":
            has_class = bool(re.search(r"class\s+\w*Repository", code))
            checks.append(ConstraintCheckResult(
                check_name="Creates Repository class(es)",
                passed=has_class,
                details="Repository class found" if has_class else "missing",
            ))

        return checks

    def _check_agent_outputs(self, summaries: dict) -> list:
        """Check that agents produced expected outputs."""
        checks = []

        # Did Historian run?
        has_historian = "historian" in summaries
        checks.append(ConstraintCheckResult(
            check_name="Historian ran",
            passed=has_historian,
            details=summaries.get("historian", "not found")[:80],
        ))

        # Did Architect run?
        has_architect = "architect" in summaries
        checks.append(ConstraintCheckResult(
            check_name="Architect ran",
            passed=has_architect,
            details=summaries.get("architect", "not found")[:80],
        ))

        # Did Planner run?
        has_planner = "planner" in summaries
        checks.append(ConstraintCheckResult(
            check_name="Planner ran",
            passed=has_planner,
            details=summaries.get("planner", "not found")[:80],
        ))

        # Did Reviewer run?
        has_reviewer = "reviewer" in summaries
        checks.append(ConstraintCheckResult(
            check_name="Reviewer ran",
            passed=has_reviewer,
            details=summaries.get("reviewer", "not found")[:80],
        ))

        return checks

    def _check_coat_reasoning(self, summaries: dict) -> list:
        """Check if Architect used CoAT reasoning."""
        checks = []
        architect = summaries.get("architect", "")
        has_coat = "coat" in str(architect).lower() or "analyze" in str(architect).lower()
        checks.append(ConstraintCheckResult(
            check_name="Architect CoAT reasoning",
            passed=has_coat,
            details="CoAT reasoning detected" if has_coat else "not detected",
        ))
        return checks


# ─── Runner ───────────────────────────────────────────────────


async def run_single_task(
    case: EvaluationCase, provider: str, api_key: Optional[str] = None
) -> EvaluationResult:
    """Run a single evaluation case through the full pipeline."""
    # Import here to avoid circular imports at module level
    from agents.orchestrator import Orchestrator
    from agents.llm_client import create_llm_client

    print(f"\n{'=' * 70}")
    print(f"  TASK: {case.task_id}")
    print(f"  {case.task_description[:70]}")
    print(f"  Repo: {case.repo_path}")
    print(f"  Provider: {provider}")
    print(f"{'=' * 70}")

    # Create real LLM client
    try:
        llm_client = create_llm_client(provider=provider, api_key=api_key)
        print(f"  [OK] LLM client: {llm_client.model_name}")
    except Exception as e:
        return EvaluationResult(
            task_id=case.task_id,
            success=False,
            pipeline_status="llm_init_error",
            total_time_ms=0,
            attempts=0,
            errors=[f"Failed to create LLM client: {e}"],
            notes=f"Provider: {provider}",
        )

    # Create orchestrator with real LLM + RAG (auto-indexes repo)
    orchestrator = Orchestrator(llm_client=llm_client, repo_path=case.repo_path)

    # Run pipeline
    start = time.perf_counter()
    try:
        result = await orchestrator.run(
            user_request=case.task_description,
            repo_path=case.repo_path,
            language=case.language,
        )
        elapsed_ms = (time.perf_counter() - start) * 1000

        # Run constraint checks
        checker = ConstraintChecker()
        constraint_results = checker.check_all(
            case, result.generated_code, result.agent_summaries
        )

        eval_result = EvaluationResult(
            task_id=case.task_id,
            success=result.success,
            pipeline_status="approved" if result.success else "changes_requested",
            total_time_ms=elapsed_ms,
            attempts=result.attempts,
            generated_code=result.generated_code,
            target_file=result.target_file,
            constraint_checks=[asdict(c) for c in constraint_results],
            errors=result.errors,
            agent_summaries=result.agent_summaries,
        )

        # Print live progress
        status = "[PASS]" if result.success else "[FAIL]"
        print(f"\n  {status} in {elapsed_ms:.0f}ms ({result.attempts} attempt(s))")
        print(f"  Target: {result.target_file}")
        print(f"  Code: {len(result.generated_code)} chars, "
              f"{len(result.generated_code.splitlines())} lines")

        # Print constraint check results
        passed = sum(1 for c in constraint_results if c.passed)
        total = len(constraint_results)
        print(f"\n  Constraint Checks: {passed}/{total}")
        for c in constraint_results:
            icon = "[PASS]" if c.passed else "[FAIL]"
            print(f"    {icon} {c.check_name}: {c.details[:60]}")

        # Print agent summaries
        print(f"\n  Agent Summaries:")
        for agent, summary in result.agent_summaries.items():
            summary_str = str(summary)[:80] if summary else "N/A"
            print(f"    [{agent}] {summary_str}")

        if result.errors:
            print(f"\n  Errors:")
            for err in result.errors:
                print(f"    [WARN] {err[:80]}")

        return eval_result

    except Exception as e:
        elapsed_ms = (time.perf_counter() - start) * 1000
        print(f"\n  [ERROR] EXCEPTION in {elapsed_ms:.0f}ms: {e}")
        import traceback
        traceback.print_exc()
        return EvaluationResult(
            task_id=case.task_id,
            success=False,
            pipeline_status="exception",
            total_time_ms=elapsed_ms,
            attempts=0,
            errors=[str(e)],
            notes=f"Exception: {type(e).__name__}",
        )


async def run_evaluation(
    suite: list,
    provider: str,
    api_key: Optional[str] = None,
    delay_between_tasks: int = 12,
) -> list:
    """Run the full evaluation suite."""
    results = []

    for i, case in enumerate(suite):
        if i > 0:
            print(f"\n  [WAIT] {delay_between_tasks}s (rate limit cooldown)...")
            await asyncio.sleep(delay_between_tasks)

        result = await run_single_task(case, provider, api_key)
        results.append(result)

    return results


# ─── Output ───────────────────────────────────────────────────


def print_scorecard(results: list):
    """Print human-readable scorecard."""
    print("\n" + "=" * 70)
    print("  EVALUATION SCORECARD")
    print("=" * 70)

    total_checks_passed = 0
    total_checks = 0

    for r in results:
        status = "[PASS]" if r.success else "[FAIL]"
        print(f"\n  {status} {r.task_id}")
        print(f"     Pipeline: {r.pipeline_status} | "
              f"Time: {r.total_time_ms:.0f}ms | "
              f"Attempts: {r.attempts}")
        print(f"     Code: {len(r.generated_code)} chars")

        checks = r.constraint_checks
        passed = sum(1 for c in checks if c.get("passed", False))
        total = len(checks)
        total_checks_passed += passed
        total_checks += total
        print(f"     Constraints: {passed}/{total} passed")

        for c in checks:
            icon = "[PASS]" if c.get("passed") else "[FAIL]"
            print(f"       {icon} {c['check_name']}")

        if r.errors:
            for err in r.errors[:3]:
                print(f"     [WARN] {str(err)[:70]}")

    passed_tasks = sum(1 for r in results if r.success)
    total_tasks = len(results)

    print(f"\n{'=' * 70}")
    print(f"  TOTAL: {passed_tasks}/{total_tasks} tasks passed")
    print(f"  CONSTRAINTS: {total_checks_passed}/{total_checks} checks passed")
    print(f"{'=' * 70}")


def save_results(results: list, output_dir: str = "evaluation_results"):
    """Save evaluation results to JSON."""
    Path(output_dir).mkdir(exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    filepath = Path(output_dir) / f"eval_{ts}.json"

    # Convert to serializable format
    data = {
        "timestamp": ts,
        "results": [asdict(r) for r in results],
        "summary": {
            "total_tasks": len(results),
            "passed_tasks": sum(1 for r in results if r.success),
            "total_time_ms": sum(r.total_time_ms for r in results),
        },
    }

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, default=str)

    print(f"\n  [SAVED] Results: {filepath}")

    # Also save generated code separately for easy review
    code_dir = Path(output_dir) / f"eval_{ts}_code"
    code_dir.mkdir(exist_ok=True)
    for r in results:
        if r.generated_code:
            code_file = code_dir / f"{r.task_id}.py"
            with open(code_file, "w", encoding="utf-8") as f:
                f.write(f"# Task: {r.task_id}\n")
                f.write(f"# Pipeline status: {r.pipeline_status}\n")
                f.write(f"# Target file: {r.target_file}\n\n")
                f.write(r.generated_code)
            print(f"  [SAVED] Code: {code_file}")

    return str(filepath)


# ─── CLI ──────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(
        description="Run real-LLM evaluation against test repos"
    )
    parser.add_argument(
        "--provider", default="groq",
        choices=["groq", "google", "openai", "deepseek", "anthropic", "ollama"],
        help="LLM provider to use (default: groq)",
    )
    parser.add_argument(
        "--task", default=None,
        help="Run a single task by ID (default: run all)",
    )
    parser.add_argument(
        "--delay", type=int, default=12,
        help="Seconds between tasks for rate limiting (default: 12)",
    )
    parser.add_argument(
        "--api-key", default=None,
        help="API key (default: read from env var)",
    )

    args = parser.parse_args()

    # Filter suite if specific task requested
    suite = EVALUATION_SUITE
    if args.task:
        suite = [c for c in suite if c.task_id == args.task]
        if not suite:
            valid = [c.task_id for c in EVALUATION_SUITE]
            print(f"Unknown task: {args.task}. Valid: {valid}")
            sys.exit(1)

    print(f"\n{'=' * 70}")
    print(f"  CONTEXTUAL ARCHITECT — Real-LLM Evaluation")
    print(f"  Provider: {args.provider}")
    print(f"  Tasks: {len(suite)}")
    print(f"  Repo: {FASTAPI_REPO}")
    print(f"{'=' * 70}")

    # Run
    results = asyncio.run(
        run_evaluation(suite, args.provider, args.api_key, args.delay)
    )

    # Output
    print_scorecard(results)
    save_results(results)


if __name__ == "__main__":
    main()
