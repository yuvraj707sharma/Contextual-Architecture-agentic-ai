"""
Reasoning Display — Shows users what agents are thinking in real-time.

Inspired by Claude CLI and Gemini CLI:
  - Animated spinner during LLM calls
  - Clean, minimal output with subtle colors
  - Elapsed time per step
  - No heavy emoji or box-drawing — just clean markers

Usage:
    reasoning.emit("scanner", "Scanning project structure...")
    reasoning.start_spinner("Generating code...")
    # ... LLM call ...
    reasoning.stop_spinner()
"""

import itertools
import sys
import threading
import time
from dataclasses import dataclass
from typing import Dict, List, Optional

# ── Rich availability check ──────────────────────────────

_HAS_RICH = False
try:
    from rich.console import Console
    from rich.live import Live
    from rich.table import Table
    from rich.panel import Panel
    from rich.text import Text
    from rich import box
    _HAS_RICH = True
except ImportError:
    pass


# ── Agent display config ─────────────────────────────────
# Clean, minimal markers — inspired by Claude CLI's subtlety

AGENT_STYLES = {
    "scanner":        {"marker": "▸", "color": "cyan",    "rich_style": "cyan"},
    "graph":          {"marker": "▸", "color": "cyan",    "rich_style": "cyan"},
    "historian":      {"marker": "▸", "color": "blue",    "rich_style": "blue"},
    "architect":      {"marker": "▸", "color": "magenta", "rich_style": "magenta"},
    "discovery":      {"marker": "▸", "color": "blue",    "rich_style": "blue"},
    "planner":        {"marker": "▸", "color": "green",   "rich_style": "green"},
    "alignment":      {"marker": "▸", "color": "green",   "rich_style": "green"},
    "implementer":    {"marker": "▸", "color": "yellow",  "rich_style": "yellow"},
    "reviewer":       {"marker": "▸", "color": "red",     "rich_style": "red"},
    "test_generator": {"marker": "▸", "color": "cyan",    "rich_style": "cyan"},
    "clarification":  {"marker": "!", "color": "yellow",  "rich_style": "yellow"},
    "executor":       {"marker": "▸", "color": "green",   "rich_style": "green"},
    "report":         {"marker": "▸", "color": "green",   "rich_style": "green"},
    "writer":         {"marker": "▸", "color": "green",   "rich_style": "green"},
}

DEFAULT_STYLE = {"marker": "▸", "color": "white", "rich_style": "white"}

# ANSI color codes (fallback)
_ANSI = {
    "cyan": "\033[36m", "blue": "\033[34m", "magenta": "\033[35m",
    "green": "\033[32m", "yellow": "\033[33m", "red": "\033[31m",
    "white": "\033[37m", "dim": "\033[2m", "bold": "\033[1m",
    "reset": "\033[0m",
}


@dataclass
class ReasoningStep:
    """A single reasoning step from an agent."""
    agent: str
    message: str
    timestamp: float = 0.0
    detail: str = ""
    duration_ms: float = 0.0

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = time.time()


class ReasoningDisplay:
    """Clean, minimal reasoning display — like Claude CLI / Gemini CLI.

    Two modes:
    - streaming=True (interactive): prints reasoning as it happens + spinners
    - streaming=False (CLI): collects all, returns in summary

    Features:
    - Animated spinner during LLM calls
    - Elapsed time tracking
    - Clean markers instead of heavy emoji
    - Uses Rich if available, falls back to ANSI
    """

    def __init__(self, streaming: bool = True, verbose: bool = False):
        self.streaming = streaming
        self.verbose = verbose
        self.steps: List[ReasoningStep] = []
        self._current_agent: str = ""
        # Suppress all TUI in CI/quiet mode (set by --quiet / -z flag)
        import os
        self._suppress = os.environ.get("MACRO_QUIET") == "1"
        self._console = Console(stderr=True) if (_HAS_RICH and not self._suppress) else None

        # Spinner state
        self._spinner_thread: Optional[threading.Thread] = None
        self._spinner_stop = threading.Event()
        self._spinner_message = ""
        self._step_start: float = 0.0

        # Live Stepper Dashboard State
        self._live: Optional[Live] = None
        self._start_time: float = 0.0
        self._current_log_lines: List[str] = []
        
        self.steps_info = [
            {"name": "Scan", "agents": ["scanner"], "status": "pending"},
            {"name": "Graph", "agents": ["graph"], "status": "pending"},
            {"name": "Plan", "agents": ["discovery", "historian", "architect", "planner", "alignment", "clarification"], "status": "pending"},
            {"name": "Code", "agents": ["implementer"], "status": "pending"},
            {"name": "Review", "agents": ["reviewer"], "status": "pending"},
            {"name": "Test", "agents": ["test_generator", "test_runner"], "status": "pending"},
            {"name": "Write", "agents": ["writer", "executor", "report"], "status": "pending"},
        ]

    def _update_stepper_status(self, agent: str, message: str):
        # Find step containing this agent
        step_idx = -1
        for idx, step in enumerate(self.steps_info):
            if agent in step["agents"]:
                step_idx = idx
                break
        if step_idx == -1:
            return

        # Update preceding steps
        for idx in range(step_idx):
            if self.steps_info[idx]["status"] not in ("success", "failed"):
                self.steps_info[idx]["status"] = "success"

        # Mark current step as running
        self.steps_info[step_idx]["status"] = "running"
        self._spinner_message = message

    def _render_dashboard(self) -> Panel:
        # Build stepper text
        stepper_parts = []
        symbols = {
            "pending": "[dim]⚬[/]",
            "running": "[bold yellow]◷[/]",
            "success": "[bold green]✔[/]",
            "failed": "[bold red]✘[/]"
        }
        for step in self.steps_info:
            symbol = symbols[step["status"]]
            name = step["name"]
            
            if step["status"] == "running":
                name_style = "bold yellow"
            elif step["status"] == "success":
                name_style = "bold green"
            elif step["status"] == "failed":
                name_style = "bold red"
            else:
                name_style = "dim"
                
            stepper_parts.append(f"{symbol} [{name_style}]{name}[/]")
            
        stepper_line = "  ➔  ".join(stepper_parts)
        
        # Activity line
        elapsed = time.time() - self._start_time if self._start_time else 0
        activity_text = f"[bold cyan]Activity:[/] {self._spinner_message or 'Processing...'} [dim]({elapsed:.1f}s)[/]"
        
        # Build body
        body = Text()
        body.append("\n")
        body.append(Text.from_markup(f"  {stepper_line}\n\n"))
        body.append(Text.from_markup(f"  {activity_text}\n\n"))
        
        if self._current_log_lines:
            body.append(Text.from_markup("  [dim]Latest logs:[/]\n"))
            for line in self._current_log_lines:
                body.append(Text.from_markup(f"   {line}\n"))
            
        return Panel(
            body,
            title="[bold cyan]MACRO Pipeline Dashboard[/]",
            border_style="cyan",
            box=box.ROUNDED,
            padding=(0, 1),
            width=min(Console().width, 84),
        )

    def _start_live_display(self):
        if not self.streaming or self.verbose or not _HAS_RICH or self._suppress:
            return
        if self._live is not None:
            return
        
        # Reset statuses
        for step in self.steps_info:
            step["status"] = "pending"
        self._current_log_lines = []
        self._start_time = time.time()
        
        self._live = Live(
            self._render_dashboard(),
            console=self._console or Console(stderr=True),
            refresh_per_second=10,
            transient=False,
        )
        self._live.start()

    def stop(self, success: bool = True):
        """Stop the stepper display and mark all steps appropriately."""
        self.stop_spinner()
        if self._live is not None:
            for step in self.steps_info:
                if step["status"] == "running":
                    step["status"] = "success" if success else "failed"
                elif step["status"] == "pending":
                    step["status"] = "success" if success else "pending"
            
            self._live.update(self._render_dashboard())
            self._live.stop()
            self._live = None

    def emit(self, agent: str, message: str, detail: str = ""):
        """Emit a reasoning step — clean, minimal output."""
        step = ReasoningStep(agent=agent, message=message, detail=detail)

        # Track duration since last step
        now = time.time()
        if self._step_start > 0:
            step.duration_ms = (now - self._step_start) * 1000
        self._step_start = now

        self.steps.append(step)

        if self._suppress:
            return

        # Handle Live Dashboard mode if streaming and not verbose
        if self.streaming and not self.verbose and _HAS_RICH:
            if self._live is None:
                self._start_live_display()
            
            self._update_stepper_status(agent, message)
            
            # Add to the log lines buffer
            style_info = AGENT_STYLES.get(agent, DEFAULT_STYLE)
            log_line = f"[dim]▸ {agent.capitalize()}: {message}[/]"
            self._current_log_lines.append(log_line)
            if len(self._current_log_lines) > 4:
                self._current_log_lines.pop(0)
                
            if self._live is not None:
                self._live.update(self._render_dashboard())
            return

        if self.streaming:
            self._print_step(step)

    def start_spinner(self, message: str = "Thinking..."):
        """Start an animated spinner — shows activity during LLM calls."""
        if self._suppress or not self.streaming:
            return

        self._spinner_message = message
        self._step_start = time.time()

        # If live dashboard is running, just update message
        if self._live is not None:
            # Update current step's activity/message
            self._live.update(self._render_dashboard())
            return

        self._spinner_stop.clear()
        if _HAS_RICH and self._console:
            self._start_rich_spinner(message)
        else:
            self._start_ansi_spinner(message)

    def stop_spinner(self, final_message: str = ""):
        """Stop the spinner and optionally print a completion message."""
        if self._live is not None:
            if final_message:
                elapsed = time.time() - self._step_start if self._step_start else 0
                log_line = f"[green]✔[/] {final_message} [dim]({elapsed:.1f}s)[/]"
                self._current_log_lines.append(log_line)
                if len(self._current_log_lines) > 4:
                    self._current_log_lines.pop(0)
                self._live.update(self._render_dashboard())
            return

        self._spinner_stop.set()
        elapsed = time.time() - self._step_start if self._step_start else 0

        if self._spinner_thread and self._spinner_thread.is_alive():
            self._spinner_thread.join(timeout=1)
        self._spinner_thread = None

        # Clear spinner line
        if self.streaming and not self._suppress:
            try:
                sys.stderr.write("\r\033[K")
                sys.stderr.flush()
            except (OSError, ValueError):
                pass

            if final_message:
                dur = f" ({elapsed:.1f}s)" if elapsed > 0.1 else ""
                self._print_clean(f"  ✓ {final_message}{dur}", "green")

    def _start_rich_spinner(self, message: str):
        """Start spinner using Rich."""
        def _spin():
            spinner_chars = itertools.cycle(["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"])
            while not self._spinner_stop.is_set():
                elapsed = time.time() - self._step_start
                char = next(spinner_chars)
                try:
                    sys.stderr.write(f"\r  {_ANSI['cyan']}{char}{_ANSI['reset']} {_ANSI['dim']}{message} ({elapsed:.1f}s){_ANSI['reset']}")
                    sys.stderr.flush()
                except (OSError, ValueError):
                    break
                self._spinner_stop.wait(0.08)

        self._spinner_thread = threading.Thread(target=_spin, daemon=True)
        self._spinner_thread.start()

    def _start_ansi_spinner(self, message: str):
        """Start spinner using ANSI codes."""
        def _spin():
            spinner_chars = itertools.cycle(["|", "/", "-", "\\"])
            while not self._spinner_stop.is_set():
                elapsed = time.time() - self._step_start
                char = next(spinner_chars)
                try:
                    sys.stderr.write(f"\r  {char} {message} ({elapsed:.1f}s)")
                    sys.stderr.flush()
                except (OSError, ValueError):
                    break
                self._spinner_stop.wait(0.1)

        self._spinner_thread = threading.Thread(target=_spin, daemon=True)
        self._spinner_thread.start()

    def _print_step(self, step: ReasoningStep):
        """Print a single reasoning step — clean and minimal."""
        try:
            if _HAS_RICH and self._console:
                self._print_step_rich(step)
            else:
                self._print_step_ansi(step)
        except (UnicodeEncodeError, OSError):
            pass

    def _print_step_rich(self, step: ReasoningStep):
        """Render with Rich — clean, subtle output."""
        style_info = AGENT_STYLES.get(step.agent, DEFAULT_STYLE)
        marker = style_info["marker"]

        # New agent → show agent name
        if step.agent != self._current_agent:
            self._current_agent = step.agent
            self._console.print(
                f"  [{style_info['rich_style']}]{marker} {step.agent.capitalize()}[/{style_info['rich_style']}]",
            )

        # Duration tag
        dur = ""
        if step.duration_ms > 100:
            dur = f" [dim]({step.duration_ms/1000:.1f}s)[/dim]"

        # Show message with dim styling
        self._console.print(f"  [dim]  {step.message}{dur}[/dim]")

        # Verbose detail
        if self.verbose and step.detail:
            for line in step.detail.split("\n"):
                self._console.print(f"  [dim]    {line}[/dim]")

    def _print_step_ansi(self, step: ReasoningStep):
        """Fallback: clean ANSI output."""
        is_tty = hasattr(sys.stdout, 'isatty') and sys.stdout.isatty()
        dim = _ANSI["dim"] if is_tty else ""
        reset = _ANSI["reset"] if is_tty else ""

        style_info = AGENT_STYLES.get(step.agent, DEFAULT_STYLE)
        color = _ANSI.get(style_info["color"], "") if is_tty else ""
        marker = style_info["marker"]

        if step.agent != self._current_agent:
            self._current_agent = step.agent
            print(f"  {color}{marker} {step.agent.capitalize()}{reset}")

        dur = ""
        if step.duration_ms > 100:
            dur = f" ({step.duration_ms/1000:.1f}s)"

        print(f"  {dim}  {step.message}{dur}{reset}")

        if self.verbose and step.detail:
            for line in step.detail.split("\n"):
                print(f"  {dim}    {line}{reset}")

        sys.stdout.flush()

    def _print_clean(self, text: str, color: str = "white"):
        """Print a clean line with optional color."""
        try:
            if _HAS_RICH and self._console:
                self._console.print(f"[{color}]{text}[/{color}]")
            else:
                is_tty = hasattr(sys.stdout, 'isatty') and sys.stdout.isatty()
                c = _ANSI.get(color, "") if is_tty else ""
                r = _ANSI["reset"] if is_tty else ""
                print(f"{c}{text}{r}")
        except (UnicodeEncodeError, OSError):
            print(text)

    def suppress(self):
        """Temporarily suppress output (for non-interactive runs)."""
        self._suppress = True

    def unsuppress(self):
        """Resume output."""
        self._suppress = False

    def get_summary(self) -> str:
        """Get a formatted summary of all reasoning steps."""
        if not self.steps:
            return ""

        lines = ["Agent Reasoning:"]
        current_agent = ""

        for step in self.steps:
            if step.agent != current_agent:
                current_agent = step.agent
                style = AGENT_STYLES.get(step.agent, DEFAULT_STYLE)
                lines.append(f"  {style['marker']} {current_agent.capitalize()}")

            dur = ""
            if step.duration_ms > 100:
                dur = f" ({step.duration_ms/1000:.1f}s)"
            lines.append(f"    {step.message}{dur}")

            if self.verbose and step.detail:
                for detail_line in step.detail.split("\n"):
                    lines.append(f"      {detail_line}")

        return "\n".join(lines)

    def get_steps_for_agent(self, agent: str) -> List[ReasoningStep]:
        """Get all reasoning steps for a specific agent."""
        return [s for s in self.steps if s.agent == agent]

    def to_trace_data(self) -> List[Dict]:
        """Export reasoning to trace-friendly format (for distillation)."""
        return [
            {
                "agent": s.agent,
                "message": s.message,
                "detail": s.detail,
                "timestamp": s.timestamp,
                "duration_ms": s.duration_ms,
            }
            for s in self.steps
        ]

    def clear(self):
        """Clear all collected steps."""
        self.steps.clear()
        self._current_agent = ""
        self._step_start = 0.0


# ── Module-level singleton for easy access ────────────────

_global_reasoning: Optional[ReasoningDisplay] = None


def get_reasoning(streaming: bool = True, verbose: bool = False) -> ReasoningDisplay:
    """Get the global reasoning display instance."""
    global _global_reasoning
    if _global_reasoning is None:
        _global_reasoning = ReasoningDisplay(streaming=streaming, verbose=verbose)
    return _global_reasoning


def reset_reasoning():
    """Reset the global reasoning display."""
    global _global_reasoning
    _global_reasoning = None
