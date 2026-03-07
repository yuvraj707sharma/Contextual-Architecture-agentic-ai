"""
Shell Executor — Sandboxed command execution after code generation.

After MACRO writes files, developers immediately need to run:
- `pytest` / `npm test` / `go test` to verify
- `pip install X` / `npm install` for new dependencies
- `git add` / `git commit` to save changes

This module provides a SAFE way to do that, matching SafeCodeWriter's
permission model:
- SAFE commands (linters, type checkers) → auto-run
- Package installs → ask permission
- Arbitrary commands → always ask, show full command
- Destructive commands → BLOCKED, no override

Usage:
    executor = ShellExecutor("./my-project")

    # Auto-detect what needs to run after writing files
    suggestions = executor.suggest_post_write(written_files, language)

    # Run with permission check
    for suggestion in suggestions:
        result = executor.run(suggestion.command, auto_approve=suggestion.safe)
"""

import logging
import os
import platform
import re
import shlex
import subprocess
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Set

logger = logging.getLogger(__name__)


# ── Permission Levels (matches SafeCodeWriter's RiskLevel) ───

class CommandRisk(Enum):
    """Risk level for a command. Mirrors SafeCodeWriter's RiskLevel."""
    SAFE = "safe"           # Auto-run: linters, type checkers, test runners
    LOW = "low"             # Auto-run with notification: git status, git diff
    MEDIUM = "medium"       # Ask permission: package installs, git commit
    HIGH = "high"           # Always ask: build commands, database operations
    BLOCKED = "blocked"     # Never run: destructive, network-piping, sudo


# ── Command Classification ───────────────────────────────────

# Commands that are ALWAYS safe (read-only or sandboxed)
SAFE_COMMANDS: Dict[str, Set[str]] = {
    # Linters & formatters
    "ruff": {"check", "format", "--check"},
    "black": {"--check", "--diff"},
    "flake8": set(),
    "pylint": set(),
    "mypy": set(),
    "eslint": set(),
    "prettier": {"--check"},
    "tsc": {"--noEmit"},
    "golangci-lint": {"run"},

    # Test runners
    "pytest": set(),
    "python": {"-m"},  # python -m pytest, python -m mypy, etc.
    "go": {"test", "vet"},
    "npm": {"test"},
    "npx": {"jest", "vitest", "mocha"},
    "cargo": {"test", "check", "clippy"},

    # Info commands
    "git": {"status", "diff", "log", "branch", "show"},
    "ls": set(),
    "dir": set(),
    "cat": set(),
    "type": set(),  # Windows equivalent of cat
    "find": set(),
    "wc": set(),
    "head": set(),
    "tail": set(),
}

# Commands that need permission but are generally useful
PERMISSION_COMMANDS: Dict[str, Set[str]] = {
    # Package managers
    "pip": {"install", "freeze", "list", "show"},
    "pip3": {"install", "freeze", "list", "show"},
    "npm": {"install", "ci", "run", "build"},
    "yarn": {"install", "add"},
    "pnpm": {"install", "add"},
    "go": {"mod", "get", "build"},
    "cargo": {"build", "add"},
    "poetry": {"install", "add"},
    "pipenv": {"install"},

    # Version control (write operations)
    "git": {"add", "commit", "stash", "checkout", "switch"},

    # Build tools
    "make": set(),
    "cmake": set(),
    "gradle": {"build"},
    "mvn": {"compile", "package"},

    # Database
    "python": {"manage.py"},  # Django management commands
}

# Patterns that are ALWAYS blocked — destructive or dangerous
BLOCKED_PATTERNS: List[str] = [
    # File destruction
    r"rm\s+(-rf?|--recursive)",
    r"del\s+/[sq]",
    r"rmdir\s+/s",
    r"format\s+[a-zA-Z]:",

    # Database destruction
    r"DROP\s+(TABLE|DATABASE|SCHEMA)",
    r"DELETE\s+FROM\s+\w+\s*;?\s*$",  # DELETE without WHERE
    r"TRUNCATE\s+TABLE",

    # Network piping (code execution from internet)
    r"curl\s+.*\|\s*(sh|bash|python|node)",
    r"wget\s+.*\|\s*(sh|bash|python|node)",
    r"curl.*-o\s+/",

    # System-level
    r"sudo\s+",
    r"chmod\s+777",
    r"chown\s+",
    r"mkfs",
    r"dd\s+if=",

    # Disable safety
    r"--force",
    r"--no-verify",
    r"-f\s+/",

    # Environment manipulation
    r"export\s+.*=.*&&",
    r"set\s+.*=.*&&",

    # Shell escapes
    r"eval\s+",
    r"`.*`",
    r"\$\(.*\)",

    # Windows command chaining (VULN-4)
    r"\s*&\s*",        # cmd1 & cmd2
    r"\s*&&\s*",       # cmd1 && cmd2
    r"\s*\|\|\s*",     # cmd1 || cmd2
]


@dataclass
class CommandResult:
    """Result of a shell command execution."""
    command: str
    success: bool
    returncode: int = 0
    stdout: str = ""
    stderr: str = ""
    duration_ms: int = 0
    risk: CommandRisk = CommandRisk.SAFE
    blocked_reason: str = ""
    skipped: bool = False

    def to_dict(self) -> dict:
        return {
            "command": self.command,
            "success": self.success,
            "returncode": self.returncode,
            "stdout": self.stdout[-2000:] if self.stdout else "",
            "stderr": self.stderr[-1000:] if self.stderr else "",
            "duration_ms": self.duration_ms,
            "risk": self.risk.value,
            "blocked_reason": self.blocked_reason,
            "skipped": self.skipped,
        }

    def to_prompt_feedback(self) -> str:
        """Format for injection into LLM context on retry."""
        if self.blocked_reason:
            return f"Command `{self.command}` was BLOCKED: {self.blocked_reason}"
        if self.skipped:
            return f"Command `{self.command}` was skipped by user"
        if self.success:
            output = self.stdout[:500] if self.stdout else "(no output)"
            return f"Command `{self.command}` succeeded:\n```\n{output}\n```"
        else:
            error = self.stderr[:500] if self.stderr else self.stdout[:500]
            return (
                f"Command `{self.command}` FAILED (exit code {self.returncode}):\n"
                f"```\n{error}\n```"
            )


@dataclass
class CommandSuggestion:
    """A suggested command to run after writing files."""
    command: str
    reason: str
    risk: CommandRisk
    auto_approve: bool = False  # Whether to run without asking

    def to_display(self) -> str:
        risk_icons = {
            CommandRisk.SAFE: "✅",
            CommandRisk.LOW: "ℹ️",
            CommandRisk.MEDIUM: "⚠️",
            CommandRisk.HIGH: "🔴",
            CommandRisk.BLOCKED: "🚫",
        }
        icon = risk_icons.get(self.risk, "")
        auto = " (auto)" if self.auto_approve else ""
        return f"{icon} {self.command}{auto} — {self.reason}"


# ── Shell Executor ───────────────────────────────────────────

class ShellExecutor:
    """Sandboxed command execution with permission flow.

    Matches SafeCodeWriter's safety philosophy:
    - Everything is classified by risk before execution
    - Destructive commands are BLOCKED unconditionally
    - Safe commands auto-run (linters, test runners)
    - Medium-risk commands require user permission
    """

    def __init__(
        self,
        cwd: str,
        timeout: int = 120,
        auto_approve_safe: bool = True,
    ):
        self.cwd = str(Path(cwd).resolve())
        self.timeout = timeout
        self.auto_approve_safe = auto_approve_safe
        self._is_windows = platform.system() == "Windows"

    def classify(self, command: str) -> CommandRisk:
        """Classify a command's risk level.

        Returns:
            CommandRisk enum value
        """
        # Check blocked patterns FIRST
        for pattern in BLOCKED_PATTERNS:
            if re.search(pattern, command, re.IGNORECASE):
                return CommandRisk.BLOCKED

        # Parse command into parts
        parts = self._parse_command(command)
        if not parts:
            return CommandRisk.BLOCKED

        base = parts[0].lower()
        # Strip path (e.g., /usr/bin/python → python)
        base = Path(base).stem

        subcommand = parts[1].lower() if len(parts) > 1 else ""

        # Check safe commands
        if base in SAFE_COMMANDS:
            allowed_subs = SAFE_COMMANDS[base]
            if not allowed_subs:  # Empty set = all subcommands safe
                return CommandRisk.SAFE
            if subcommand in allowed_subs:
                return CommandRisk.SAFE
            # Special case: python -m <module>
            if base == "python" and subcommand == "-m":
                module = parts[2].lower() if len(parts) > 2 else ""
                if module in ("pytest", "mypy", "ruff", "black", "flake8", "pylint"):
                    return CommandRisk.SAFE

        # Check permission commands
        if base in PERMISSION_COMMANDS:
            allowed_subs = PERMISSION_COMMANDS[base]
            if not allowed_subs:
                return CommandRisk.MEDIUM
            if subcommand in allowed_subs:
                return CommandRisk.MEDIUM
            # git with a write subcommand not in permission list
            if base == "git" and subcommand not in SAFE_COMMANDS.get("git", set()):
                return CommandRisk.HIGH

        # Unknown command → HIGH risk
        return CommandRisk.HIGH

    def run(
        self,
        command: str,
        auto_approve: bool = False,
        env_override: Optional[Dict[str, str]] = None,
    ) -> CommandResult:
        """Run a command with risk classification and permission check.

        Args:
            command: The shell command to run
            auto_approve: Skip permission prompt for medium-risk commands
            env_override: Additional environment variables

        Returns:
            CommandResult with output, timing, and status
        """
        risk = self.classify(command)

        # BLOCKED: never run
        if risk == CommandRisk.BLOCKED:
            reason = self._get_block_reason(command)
            logger.warning(f"BLOCKED: {command} — {reason}")
            return CommandResult(
                command=command,
                success=False,
                risk=risk,
                blocked_reason=reason,
            )

        # Permission check
        needs_permission = risk in (CommandRisk.MEDIUM, CommandRisk.HIGH)
        if needs_permission and not auto_approve:
            risk_label = "⚠️ MEDIUM" if risk == CommandRisk.MEDIUM else "🔴 HIGH"
            print(f"\n  {risk_label} risk command:")
            print(f"  $ {command}")
            print(f"  Working dir: {self.cwd}")
            try:
                choice = input("  Run? [Y/n/skip] ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                choice = "n"

            if choice in ("n", "no"):
                return CommandResult(
                    command=command,
                    success=False,
                    risk=risk,
                    skipped=True,
                )
            if choice in ("skip", "s"):
                return CommandResult(
                    command=command,
                    success=True,
                    risk=risk,
                    skipped=True,
                )

        # Execute
        return self._execute(command, risk, env_override)

    def run_batch(
        self,
        suggestions: List[CommandSuggestion],
        stop_on_fail: bool = True,
    ) -> List[CommandResult]:
        """Run a batch of suggested commands.

        Args:
            suggestions: List of CommandSuggestion from suggest_post_write()
            stop_on_fail: Stop executing if a command fails

        Returns:
            List of CommandResult for each command run
        """
        results = []

        for suggestion in suggestions:
            if suggestion.risk == CommandRisk.BLOCKED:
                results.append(CommandResult(
                    command=suggestion.command,
                    success=False,
                    risk=CommandRisk.BLOCKED,
                    blocked_reason="Blocked by safety policy",
                ))
                continue

            result = self.run(
                suggestion.command,
                auto_approve=suggestion.auto_approve,
            )
            results.append(result)

            if stop_on_fail and not result.success and not result.skipped:
                logger.warning(
                    f"Batch stopped: {suggestion.command} failed "
                    f"(exit code {result.returncode})"
                )
                break

        return results

    def suggest_post_write(
        self,
        written_files: Dict[str, str],
        language: str = "python",
    ) -> List[CommandSuggestion]:
        """Auto-detect what commands to run after writing files.

        Analyzes the written files to suggest:
        - New dependency → pip install / npm install
        - Test file written → pytest / npm test
        - Config changed → relevant restart
        - Linting → always suggest

        Args:
            written_files: Dict of {file_path: file_content}
            language: Programming language

        Returns:
            List of CommandSuggestion, ordered by priority
        """
        suggestions: List[CommandSuggestion] = []

        for file_path, content in written_files.items():
            path = Path(file_path)

            # ── New dependency detection ──────────────────────
            if path.name == "requirements.txt":
                suggestions.append(CommandSuggestion(
                    command="pip install -r requirements.txt",
                    reason="requirements.txt was modified",
                    risk=CommandRisk.MEDIUM,
                ))
            elif path.name == "pyproject.toml" and "[project]" in content:
                suggestions.append(CommandSuggestion(
                    command="pip install -e .",
                    reason="pyproject.toml was modified",
                    risk=CommandRisk.MEDIUM,
                ))
            elif path.name == "package.json":
                suggestions.append(CommandSuggestion(
                    command="npm install",
                    reason="package.json was modified",
                    risk=CommandRisk.MEDIUM,
                ))
            elif path.name == "go.mod":
                suggestions.append(CommandSuggestion(
                    command="go mod tidy",
                    reason="go.mod was modified",
                    risk=CommandRisk.MEDIUM,
                ))
            elif path.name == "Cargo.toml":
                suggestions.append(CommandSuggestion(
                    command="cargo build",
                    reason="Cargo.toml was modified",
                    risk=CommandRisk.MEDIUM,
                ))

            # ── New import detection (Python) ─────────────────
            if language == "python" and path.suffix == ".py":
                new_imports = self._detect_new_imports(content)
                for imp in new_imports:
                    # Map common import names to pip package names
                    pip_name = self._import_to_pip(imp)
                    if pip_name:
                        suggestions.append(CommandSuggestion(
                            command=f"pip install {pip_name}",
                            reason=f"New import detected: {imp}",
                            risk=CommandRisk.MEDIUM,
                        ))

            # ── Test file detection ───────────────────────────
            if self._is_test_file(file_path):
                if language == "python":
                    suggestions.append(CommandSuggestion(
                        command=f"python -m pytest {file_path} -v",
                        reason=f"Test file written: {path.name}",
                        risk=CommandRisk.SAFE,
                        auto_approve=True,
                    ))
                elif language in ("javascript", "typescript"):
                    suggestions.append(CommandSuggestion(
                        command="npm test",
                        reason=f"Test file written: {path.name}",
                        risk=CommandRisk.SAFE,
                        auto_approve=True,
                    ))
                elif language == "go":
                    suggestions.append(CommandSuggestion(
                        command=f"go test ./{path.parent}/...",
                        reason=f"Test file written: {path.name}",
                        risk=CommandRisk.SAFE,
                        auto_approve=True,
                    ))

        # ── Always suggest linting ────────────────────────────
        if language == "python":
            # Check if ruff is available
            suggestions.append(CommandSuggestion(
                command="python -m ruff check .",
                reason="Lint new/modified code",
                risk=CommandRisk.SAFE,
                auto_approve=True,
            ))
        elif language in ("javascript", "typescript"):
            suggestions.append(CommandSuggestion(
                command="npx eslint .",
                reason="Lint new/modified code",
                risk=CommandRisk.SAFE,
                auto_approve=True,
            ))
        elif language == "go":
            suggestions.append(CommandSuggestion(
                command="go vet ./...",
                reason="Vet new/modified code",
                risk=CommandRisk.SAFE,
                auto_approve=True,
            ))

        # Deduplicate by command
        seen = set()
        unique = []
        for s in suggestions:
            if s.command not in seen:
                seen.add(s.command)
                unique.append(s)

        return unique

    def format_suggestions(
        self, suggestions: List[CommandSuggestion]
    ) -> str:
        """Format suggestions for display to user."""
        if not suggestions:
            return ""

        lines = ["\n📋 Suggested commands:"]
        for i, s in enumerate(suggestions, 1):
            lines.append(f"  {i}. {s.to_display()}")

        return "\n".join(lines)

    def format_results(self, results: List[CommandResult]) -> str:
        """Format execution results for display."""
        if not results:
            return ""

        lines = ["\n📊 Execution results:"]
        for r in results:
            if r.blocked_reason:
                lines.append(f"  🚫 {r.command} — BLOCKED: {r.blocked_reason}")
            elif r.skipped:
                lines.append(f"  ⏭️  {r.command} — skipped")
            elif r.success:
                lines.append(f"  ✅ {r.command} — passed ({r.duration_ms}ms)")
                if r.stdout and len(r.stdout.strip()) > 0:
                    # Show first 3 lines of output
                    out_lines = r.stdout.strip().split("\n")[:3]
                    for ol in out_lines:
                        lines.append(f"      {ol[:100]}")
            else:
                lines.append(
                    f"  ❌ {r.command} — FAILED (exit {r.returncode}, {r.duration_ms}ms)"
                )
                if r.stderr:
                    err_lines = r.stderr.strip().split("\n")[:3]
                    for el in err_lines:
                        lines.append(f"      {el[:100]}")

        return "\n".join(lines)

    # ── Internal Methods ─────────────────────────────────────

    def _execute(
        self,
        command: str,
        risk: CommandRisk,
        env_override: Optional[Dict[str, str]] = None,
    ) -> CommandResult:
        """Actually execute a command in a subprocess."""
        env = os.environ.copy()
        if env_override:
            env.update(env_override)

        # Security: lock working directory to project
        cwd = self.cwd

        start = time.perf_counter()

        try:
            # SECURITY: NEVER use shell=True (VULN-4)
            parts = self._parse_command(command)

            if self._is_windows:
                # Windows built-in commands need cmd.exe
                win_builtins = {
                    "dir", "type", "echo", "copy", "move", "ren",
                    "mkdir", "md", "rmdir", "rd", "del", "cls",
                    "set", "ver", "vol", "path", "cd",
                }
                base = Path(parts[0]).stem.lower() if parts else ""
                if base in win_builtins:
                    parts = ["cmd", "/c"] + parts

            proc = subprocess.run(
                parts,
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=self.timeout,
                env=env,
                shell=False,  # NEVER shell=True
            )

            duration = int((time.perf_counter() - start) * 1000)

            return CommandResult(
                command=command,
                success=proc.returncode == 0,
                returncode=proc.returncode,
                stdout=proc.stdout[-5000:] if proc.stdout else "",
                stderr=proc.stderr[-2000:] if proc.stderr else "",
                duration_ms=duration,
                risk=risk,
            )

        except subprocess.TimeoutExpired:
            duration = int((time.perf_counter() - start) * 1000)
            logger.warning(f"Command timed out after {self.timeout}s: {command}")
            return CommandResult(
                command=command,
                success=False,
                returncode=-1,
                stderr=f"Timed out after {self.timeout}s",
                duration_ms=duration,
                risk=risk,
            )
        except FileNotFoundError:
            return CommandResult(
                command=command,
                success=False,
                returncode=-1,
                stderr=f"Command not found: {command.split()[0]}",
                duration_ms=0,
                risk=risk,
            )
        except Exception as e:
            logger.error(f"Execution error: {e}")
            return CommandResult(
                command=command,
                success=False,
                returncode=-1,
                stderr=str(e),
                duration_ms=0,
                risk=risk,
            )

    def _parse_command(self, command: str) -> List[str]:
        """Parse a command string into parts safely."""
        try:
            if self._is_windows:
                # Windows: split manually (shlex doesn't handle Windows well)
                return command.split()
            return shlex.split(command)
        except ValueError:
            return command.split()

    def _get_block_reason(self, command: str) -> str:
        """Get a human-readable reason for why a command was blocked."""
        for pattern in BLOCKED_PATTERNS:
            if re.search(pattern, command, re.IGNORECASE):
                return f"Matches blocked pattern: {pattern}"
        return "Unknown dangerous pattern"

    def _is_test_file(self, file_path: str) -> bool:
        """Check if a file is a test file."""
        name = Path(file_path).stem.lower()
        return (
            name.startswith("test_") or
            name.endswith("_test") or
            name.endswith(".test") or
            name.endswith(".spec") or
            name.endswith("_spec") or
            "/tests/" in file_path or
            "/test/" in file_path or
            "\\tests\\" in file_path or
            "\\test\\" in file_path
        )

    def _detect_new_imports(self, content: str) -> List[str]:
        """Detect potentially new third-party imports in Python code."""
        stdlib = {
            "os", "sys", "re", "json", "math", "time", "datetime",
            "pathlib", "typing", "collections", "itertools", "functools",
            "logging", "unittest", "dataclasses", "enum", "abc",
            "io", "copy", "hashlib", "uuid", "random", "string",
            "textwrap", "shutil", "tempfile", "subprocess", "threading",
            "asyncio", "concurrent", "socket", "http", "urllib",
            "xml", "csv", "sqlite3", "ast", "inspect", "dis",
            "argparse", "configparser", "statistics", "decimal",
            "fractions", "operator", "contextlib", "warnings",
            "traceback", "pdb", "profile", "timeit", "platform",
            "shlex", "signal", "struct", "array", "queue",
        }

        third_party = []
        for match in re.finditer(
            r"^(?:from\s+(\w+)|import\s+(\w+))", content, re.MULTILINE
        ):
            module = match.group(1) or match.group(2)
            if module and module not in stdlib and not module.startswith("_"):
                third_party.append(module)

        return list(set(third_party))

    def _import_to_pip(self, import_name: str) -> Optional[str]:
        """Map Python import name to pip package name."""
        # Common mismatches between import and pip names
        mappings = {
            "PIL": "Pillow",
            "cv2": "opencv-python",
            "sklearn": "scikit-learn",
            "yaml": "PyYAML",
            "bs4": "beautifulsoup4",
            "dotenv": "python-dotenv",
            "jwt": "PyJWT",
            "redis": "redis",
            "celery": "celery",
            "flask": "Flask",
            "django": "Django",
            "fastapi": "fastapi",
            "starlette": "starlette",
            "uvicorn": "uvicorn",
            "gunicorn": "gunicorn",
            "sqlalchemy": "SQLAlchemy",
            "pydantic": "pydantic",
            "requests": "requests",
            "httpx": "httpx",
            "aiohttp": "aiohttp",
            "boto3": "boto3",
            "numpy": "numpy",
            "pandas": "pandas",
            "matplotlib": "matplotlib",
            "pytest": "pytest",
            "rich": "rich",
            "click": "click",
            "typer": "typer",
            "chromadb": "chromadb",
            "openai": "openai",
            "anthropic": "anthropic",
            "transformers": "transformers",
            "torch": "torch",
            "tensorflow": "tensorflow",
        }
        return mappings.get(import_name)
