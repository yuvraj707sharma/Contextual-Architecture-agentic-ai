"""
Tool Runtime — Execution engine for thinking agents.

Provides a set of safe, sandboxed tools that thinking models can call
to explore codebases, search GitHub, and gather information.

Tools are pure functions: input → output (string).
No side effects except write_report (writes to .contextual-architect/ only).

Security:
- read_file: capped at 300 lines per call
- run_command: 30s timeout, blocked dangerous commands
- All file ops: confined to repo directory
- GitHub API: uses GITHUB_TOKEN if available
"""

import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .logger import get_logger

logger = get_logger("tool_runtime")

# ── Dangerous commands that are always blocked ────────────
_BLOCKED_COMMANDS = {
    "rm ", "rm -", "rmdir", "del ", "format ", "mkfs",
    "dd if=", ":(){", "fork", "> /dev/sd", "shutdown",
    "reboot", "poweroff", "halt", "init 0", "init 6",
}

# GitHub API
_GH_API = "https://api.github.com"


# ── Tool Definitions (what the LLM sees) ─────────────────

TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": (
                "Read the contents of a file in the repository. "
                "Returns up to 300 lines. Use start_line/end_line to read specific sections."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Relative path from repo root, e.g. 'src/main.py'",
                    },
                    "start_line": {
                        "type": "integer",
                        "description": "Start line (1-indexed). Default: 1",
                    },
                    "end_line": {
                        "type": "integer",
                        "description": "End line (1-indexed). Default: 300",
                    },
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_dir",
            "description": (
                "List files and subdirectories at a given path. "
                "Shows file sizes and marks directories with /."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Relative path from repo root. Use '.' for root.",
                    },
                    "max_depth": {
                        "type": "integer",
                        "description": "Max recursion depth. Default: 1 (immediate children only)",
                    },
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "grep",
            "description": (
                "Search for a pattern across files. Returns matching lines with "
                "file paths and line numbers. Max 50 results."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {
                        "type": "string",
                        "description": "Search pattern (plain text or regex)",
                    },
                    "path": {
                        "type": "string",
                        "description": "Directory or file to search in, relative to repo root. Default: '.'",
                    },
                    "file_pattern": {
                        "type": "string",
                        "description": "Glob filter for files, e.g. '*.py' or '*.js'. Default: all files",
                    },
                },
                "required": ["pattern"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_command",
            "description": (
                "Run a read-only shell command in the repo directory. "
                "30s timeout. Use for: git log, wc -l, find, cat, head, etc. "
                "Do NOT use for destructive operations."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "Shell command to execute",
                    },
                },
                "required": ["command"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "github_api",
            "description": (
                "Fetch data from GitHub REST API. Use for PRs, issues, "
                "contributors, README, etc. Requires owner/repo format."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "endpoint": {
                        "type": "string",
                        "description": "API path, e.g. '/repos/sympy/sympy/pulls?state=closed&per_page=10'",
                    },
                },
                "required": ["endpoint"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": (
                "Search the web for information. Returns top results with "
                "titles, URLs, and snippets. Use for CVEs, docs, best practices."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query",
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_report",
            "description": (
                "Write your final analysis report as a markdown file. "
                "This saves to .contextual-architect/reports/. "
                "Call this when you have completed your analysis."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "filename": {
                        "type": "string",
                        "description": "Report filename, e.g. 'architecture.md' or 'security_audit.md'",
                    },
                    "content": {
                        "type": "string",
                        "description": "Full markdown content of the report",
                    },
                },
                "required": ["filename", "content"],
            },
        },
    },
]


class ToolRuntime:
    """Executes tool calls from thinking agents in a sandboxed environment.

    All file operations are confined to the repo directory.
    Commands are sandboxed with timeouts and blocked patterns.
    """

    def __init__(self, repo_path: str):
        self.repo_path = Path(repo_path).resolve()
        self.reports_dir = self.repo_path / ".contextual-architect" / "reports"
        self.reports_dir.mkdir(parents=True, exist_ok=True)
        self._gh_token = os.environ.get("GITHUB_TOKEN", "")

    # ── Main Dispatcher ───────────────────────────────────

    async def execute(self, tool_name: str, arguments: Dict[str, Any]) -> str:
        """Execute a tool by name with given arguments.

        Returns the tool's output as a string (always succeeds — errors
        are returned as error messages, never raised).
        """
        handlers = {
            "read_file": self._read_file,
            "list_dir": self._list_dir,
            "grep": self._grep,
            "run_command": self._run_command,
            "github_api": self._github_api,
            "web_search": self._web_search,
            "write_report": self._write_report,
        }

        handler = handlers.get(tool_name)
        if not handler:
            return f"Error: Unknown tool '{tool_name}'"

        try:
            result = handler(**arguments)
            logger.debug(
                f"Tool {tool_name}: {len(str(result))} chars returned",
                extra={"agent": "tool_runtime"},
            )
            return result
        except Exception as e:
            error_msg = f"Error in {tool_name}: {type(e).__name__}: {e}"
            logger.warning(error_msg, extra={"agent": "tool_runtime"})
            return error_msg

    # ── Tool Implementations ──────────────────────────────

    def _read_file(self, path: str, start_line: int = 1, end_line: int = 300) -> str:
        """Read file contents, capped at 300 lines per call."""
        target = self._safe_path(path)
        if target is None:
            return f"Error: Path '{path}' is outside the repository."

        if not target.exists():
            return f"Error: File '{path}' not found."

        if target.is_dir():
            return f"Error: '{path}' is a directory, not a file. Use list_dir instead."

        try:
            content = target.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            return f"Error reading '{path}': {e}"

        lines = content.splitlines()
        total = len(lines)

        # Clamp range
        start_line = max(1, start_line)
        end_line = min(end_line, total, start_line + 299)  # Max 300 lines

        selected = lines[start_line - 1:end_line]
        header = f"# {path} (lines {start_line}-{end_line} of {total})\n"
        numbered = "\n".join(
            f"{start_line + i}: {line}" for i, line in enumerate(selected)
        )
        return header + numbered

    def _list_dir(self, path: str = ".", max_depth: int = 1) -> str:
        """List directory contents."""
        target = self._safe_path(path)
        if target is None:
            return f"Error: Path '{path}' is outside the repository."

        if not target.exists():
            return f"Error: Directory '{path}' not found."

        if not target.is_dir():
            return f"Error: '{path}' is a file, not a directory."

        skip = {
            ".git", "__pycache__", "node_modules", ".venv", "venv",
            ".contextual-architect", ".mypy_cache", ".ruff_cache",
            ".pytest_cache", ".tox", "dist", "build",
        }

        results = []
        self._walk_dir(target, "", max_depth, 0, results, skip)

        if not results:
            return f"Directory '{path}' is empty."

        return "\n".join(results[:200])  # Cap at 200 entries

    def _walk_dir(
        self, base: Path, prefix: str, max_depth: int,
        current_depth: int, results: List[str], skip: set
    ):
        """Recursively list directory contents."""
        if current_depth > max_depth:
            return

        try:
            entries = sorted(base.iterdir(), key=lambda e: (not e.is_dir(), e.name.lower()))
        except PermissionError:
            return

        for entry in entries:
            name = entry.name
            if name in skip or name.startswith("."):
                continue
            # Skip venvs
            if entry.is_dir() and (entry / "pyvenv.cfg").exists():
                continue
            # Skip .egg-info
            if name.endswith(".egg-info"):
                continue

            rel = f"{prefix}{name}"
            if entry.is_dir():
                results.append(f"  {rel}/")
                if current_depth < max_depth:
                    self._walk_dir(entry, rel + "/", max_depth, current_depth + 1, results, skip)
            else:
                size = entry.stat().st_size
                size_str = self._format_size(size)
                results.append(f"  {rel}  ({size_str})")

    def _grep(self, pattern: str, path: str = ".", file_pattern: str = "") -> str:
        """Search for pattern in files using subprocess grep/findstr."""
        target = self._safe_path(path)
        if target is None:
            return f"Error: Path '{path}' is outside the repository."

        results = []
        try:
            regex = re.compile(pattern, re.IGNORECASE)
        except re.error as e:
            return f"Error: Invalid regex pattern: {e}"

        # Walk and search
        skip_dirs = {
            ".git", "__pycache__", "node_modules", ".venv", "venv",
            ".contextual-architect", ".mypy_cache", ".ruff_cache", "dist", "build",
        }

        for root, dirs, files in os.walk(target):
            dirs[:] = [
                d for d in dirs
                if d not in skip_dirs
                and not d.startswith(".")
                and not d.endswith(".egg-info")
                and not (Path(root) / d / "pyvenv.cfg").exists()
            ]

            for fname in files:
                # Apply file pattern filter
                if file_pattern:
                    from fnmatch import fnmatch
                    if not fnmatch(fname, file_pattern):
                        continue

                fpath = Path(root) / fname
                rel_path = str(fpath.relative_to(self.repo_path)).replace("\\", "/")

                # Skip binary files
                if self._is_binary(fname):
                    continue

                try:
                    content = fpath.read_text(encoding="utf-8", errors="replace")
                    for i, line in enumerate(content.splitlines(), 1):
                        if regex.search(line):
                            results.append(f"{rel_path}:{i}: {line.strip()}")
                            if len(results) >= 50:
                                return f"Found {len(results)} matches (capped at 50):\n" + "\n".join(results)
                except (OSError, UnicodeDecodeError):
                    continue

        if not results:
            return f"No matches found for pattern '{pattern}' in '{path}'"

        return f"Found {len(results)} matches:\n" + "\n".join(results)

    def _run_command(self, command: str) -> str:
        """Run a shell command with safety checks."""
        # Block dangerous commands
        cmd_lower = command.lower().strip()
        for blocked in _BLOCKED_COMMANDS:
            if blocked in cmd_lower:
                return f"Error: Command blocked for safety. '{blocked}' is not allowed."

        try:
            result = subprocess.run(
                command,
                shell=True,
                cwd=str(self.repo_path),
                capture_output=True,
                text=True,
                timeout=30,
            )
            output = result.stdout
            if result.stderr:
                output += f"\n[stderr]: {result.stderr}"
            if result.returncode != 0:
                output += f"\n[exit code: {result.returncode}]"

            # Cap output
            if len(output) > 10000:
                output = output[:10000] + "\n... (output truncated at 10000 chars)"

            return output if output.strip() else "(no output)"
        except subprocess.TimeoutExpired:
            return "Error: Command timed out after 30 seconds."
        except Exception as e:
            return f"Error running command: {e}"

    def _github_api(self, endpoint: str) -> str:
        """Fetch from GitHub REST API."""
        if not endpoint.startswith("/"):
            endpoint = "/" + endpoint

        url = f"{_GH_API}{endpoint}"
        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": "macro-cli",
        }
        if self._gh_token:
            headers["Authorization"] = f"Bearer {self._gh_token}"

        try:
            req = Request(url, headers=headers)
            with urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))

            # Format response nicely
            if isinstance(data, list):
                # Summarize list items (PRs, issues, etc.)
                summary = []
                for item in data[:20]:  # Cap at 20 items
                    if isinstance(item, dict):
                        parts = []
                        for key in ["number", "title", "state", "login", "name"]:
                            if key in item:
                                parts.append(f"{key}: {item[key]}")
                        # Handle nested user
                        if "user" in item and isinstance(item["user"], dict):
                            parts.append(f"author: {item['user'].get('login', '?')}")
                        summary.append(" | ".join(parts) if parts else str(item)[:200])
                    else:
                        summary.append(str(item)[:200])
                return f"GitHub API returned {len(data)} items:\n" + "\n".join(summary)
            else:
                # Single object — return key fields
                return json.dumps(data, indent=2, default=str)[:5000]

        except HTTPError as e:
            if e.code == 403:
                return "Error: GitHub API rate limited. Set GITHUB_TOKEN for higher limits."
            elif e.code == 404:
                return f"Error: GitHub resource not found: {endpoint}"
            return f"Error: GitHub API returned {e.code}: {e.reason}"
        except (URLError, TimeoutError) as e:
            return f"Error: Network error accessing GitHub: {e}"

    def _web_search(self, query: str) -> str:
        """Search the web (uses DuckDuckGo HTML search for zero deps)."""
        try:
            from urllib.parse import quote_plus
            url = f"https://html.duckduckgo.com/html/?q={quote_plus(query)}"
            headers = {"User-Agent": "Mozilla/5.0 (compatible; macro-cli/1.0)"}
            req = Request(url, headers=headers)

            with urlopen(req, timeout=10) as resp:
                html = resp.read().decode("utf-8", errors="replace")

            # Extract results from DuckDuckGo HTML
            results = []
            # Simple regex extraction of result snippets
            result_blocks = re.findall(
                r'class="result__a"[^>]*href="([^"]*)"[^>]*>(.*?)</a>.*?'
                r'class="result__snippet"[^>]*>(.*?)</(?:td|div)',
                html, re.DOTALL
            )

            for href, title, snippet in result_blocks[:8]:
                title = re.sub(r'<[^>]+>', '', title).strip()
                snippet = re.sub(r'<[^>]+>', '', snippet).strip()
                if title:
                    results.append(f"• {title}\n  {snippet}\n  URL: {href}")

            if results:
                return f"Web search results for '{query}':\n\n" + "\n\n".join(results)
            return f"No web results found for '{query}'. Try different search terms."

        except Exception as e:
            return f"Error searching web: {e}"

    def _write_report(self, filename: str, content: str) -> str:
        """Write analysis report to workspace."""
        # Sanitize filename
        safe_name = re.sub(r'[^\w\-.]', '_', filename)
        if not safe_name.endswith('.md'):
            safe_name += '.md'

        report_path = self.reports_dir / safe_name
        try:
            report_path.write_text(content, encoding="utf-8")
            rel = str(report_path.relative_to(self.repo_path)).replace("\\", "/")
            logger.info(
                f"Report written: {rel}",
                extra={"agent": "tool_runtime"},
            )
            return f"Report saved: {rel} ({len(content)} chars)"
        except Exception as e:
            return f"Error writing report: {e}"

    # ── Helpers ───────────────────────────────────────────

    def _safe_path(self, rel_path: str) -> Optional[Path]:
        """Resolve a relative path safely within the repo."""
        try:
            target = (self.repo_path / rel_path).resolve()
            # Ensure it's within the repo
            if not str(target).startswith(str(self.repo_path)):
                return None
            return target
        except (ValueError, OSError):
            return None

    @staticmethod
    def _format_size(size_bytes: int) -> str:
        """Format file size for display."""
        if size_bytes < 1024:
            return f"{size_bytes}B"
        elif size_bytes < 1024 * 1024:
            return f"{size_bytes / 1024:.1f}KB"
        else:
            return f"{size_bytes / (1024 * 1024):.1f}MB"

    @staticmethod
    def _is_binary(filename: str) -> bool:
        """Check if a file is likely binary based on extension."""
        binary_exts = {
            ".pyc", ".pyo", ".so", ".dll", ".exe", ".bin",
            ".png", ".jpg", ".jpeg", ".gif", ".ico", ".svg",
            ".woff", ".woff2", ".ttf", ".eot",
            ".zip", ".tar", ".gz", ".bz2", ".xz",
            ".pdf", ".doc", ".docx", ".xls", ".xlsx",
            ".db", ".sqlite", ".pickle", ".pkl",
        }
        return Path(filename).suffix.lower() in binary_exts
