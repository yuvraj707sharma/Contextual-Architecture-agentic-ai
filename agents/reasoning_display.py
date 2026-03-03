"""
Reasoning Display - Shows users what agents are thinking in real-time.

Uses Rich panels for beautiful terminal output when available,
falls back to plain ANSI codes otherwise.

Usage in agents:
    reasoning.emit("scanner", "Scanning project structure...")
    reasoning.emit("scanner", "Found 47 files, React + TypeScript")
    reasoning.emit("clarification", "Conflict: Firebase -> Supabase detected")
"""

import sys
import time
from dataclasses import dataclass
from typing import List, Dict, Optional


# ── Rich availability check ──────────────────────────────

_HAS_RICH = False
try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.text import Text
    _HAS_RICH = True
except ImportError:
    pass


# ── Agent display config ─────────────────────────────────

AGENT_STYLES = {
    "scanner":        {"icon": "🔍", "color": "cyan",    "rich_style": "bold cyan"},
    "historian":      {"icon": "📜", "color": "blue",    "rich_style": "bold blue"},
    "architect":      {"icon": "🏗️",  "color": "magenta", "rich_style": "bold magenta"},
    "planner":        {"icon": "📋", "color": "green",   "rich_style": "bold green"},
    "alignment":      {"icon": "✅", "color": "green",   "rich_style": "bold green"},
    "implementer":    {"icon": "⚡", "color": "yellow",  "rich_style": "bold yellow"},
    "reviewer":       {"icon": "🔎", "color": "red",     "rich_style": "bold red"},
    "test_generator": {"icon": "🧪", "color": "cyan",    "rich_style": "bold cyan"},
    "clarification":  {"icon": "⚠️",  "color": "yellow",  "rich_style": "bold yellow"},
    "writer":         {"icon": "💾", "color": "green",   "rich_style": "bold green"},
}

DEFAULT_STYLE = {"icon": "🤖", "color": "white", "rich_style": "bold white"}


@dataclass
class ReasoningStep:
    """A single reasoning step from an agent."""
    agent: str
    message: str
    timestamp: float = 0.0
    detail: str = ""
    
    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = time.time()


class ReasoningDisplay:
    """Collects and displays agent reasoning steps.
    
    Two modes:
    - streaming=True (interactive): prints reasoning as it happens
    - streaming=False (CLI): collects all, returns in summary
    
    Rendering:
    - Uses Rich panels if `rich` is installed (pip install rich)
    - Falls back to plain ANSI escape codes otherwise
    """
    
    def __init__(self, streaming: bool = True, verbose: bool = False):
        self.streaming = streaming
        self.verbose = verbose
        self.steps: List[ReasoningStep] = []
        self._current_agent: str = ""
        self._suppress = False
        self._console = Console(stderr=True) if _HAS_RICH else None
    
    def emit(self, agent: str, message: str, detail: str = ""):
        """Emit a reasoning step.
        
        Args:
            agent: Which agent is thinking (scanner, historian, planner, etc.)
            message: The main thinking message
            detail: Optional extra detail (shown only in verbose mode)
        """
        step = ReasoningStep(agent=agent, message=message, detail=detail)
        self.steps.append(step)
        
        if self._suppress:
            return
        
        if self.streaming:
            self._print_step(step)
    
    def _print_step(self, step: ReasoningStep):
        """Print a single reasoning step to terminal."""
        try:
            if _HAS_RICH and self._console:
                self._print_step_rich(step)
            else:
                self._print_step_ansi(step)
        except (UnicodeEncodeError, OSError):
            pass
    
    def _print_step_rich(self, step: ReasoningStep):
        """Render with Rich panels — beautiful terminal output."""
        style_info = AGENT_STYLES.get(step.agent, DEFAULT_STYLE)
        icon = style_info["icon"]
        agent_label = f"{icon} {step.agent.capitalize()}"
        
        # New agent → show header panel
        if step.agent != self._current_agent:
            self._current_agent = step.agent
            self._console.print(
                f"  [dim]───[/dim] [{style_info['rich_style']}]{agent_label}[/{style_info['rich_style']}] [dim]───[/dim]",
            )
        
        # Show message with dim styling
        self._console.print(f"  [dim]  › {step.message}[/dim]")
        
        # Verbose detail
        if self.verbose and step.detail:
            for line in step.detail.split("\n"):
                self._console.print(f"  [dim]    {line}[/dim]")
    
    def _print_step_ansi(self, step: ReasoningStep):
        """Fallback: raw ANSI codes for terminals without Rich."""
        if hasattr(sys.stdout, 'isatty') and sys.stdout.isatty():
            dim = "\033[2m"
            cyan = "\033[36m"
            reset = "\033[0m"
        else:
            dim = cyan = reset = ""
        
        if step.agent != self._current_agent:
            self._current_agent = step.agent
            agent_label = step.agent.capitalize()
            print(f"{dim}[Thinking] {cyan}{agent_label}{reset}{dim}...{reset}")
        
        print(f"{dim}  > {step.message}{reset}")
        
        if self.verbose and step.detail:
            for line in step.detail.split("\n"):
                print(f"{dim}    {line}{reset}")
        
        sys.stdout.flush()
    
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
                lines.append(f"  {style['icon']} [{current_agent.upper()}]")
            lines.append(f"    > {step.message}")
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
            }
            for s in self.steps
        ]
    
    def clear(self):
        """Clear all collected steps."""
        self.steps.clear()
        self._current_agent = ""


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
