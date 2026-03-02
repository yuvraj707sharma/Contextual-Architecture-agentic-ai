"""
Reasoning Display - Shows users what agents are thinking in real-time.

Provides a callback system that agents use to emit reasoning steps.
In interactive mode, these appear as streaming "[Thinking]" blocks.
In CLI mode, reasoning is collected and shown in the final summary.

Usage in agents:
    reasoning.emit("scanner", "Scanning project structure...")
    reasoning.emit("scanner", "Found 47 files, React + TypeScript")
    reasoning.emit("planner", "Conflict: Firebase -> Supabase migration")
"""

import sys
import time
from dataclasses import dataclass
from typing import List, Dict, Optional


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
    """
    
    def __init__(self, streaming: bool = True, verbose: bool = False):
        self.streaming = streaming
        self.verbose = verbose
        self.steps: List[ReasoningStep] = []
        self._current_agent: str = ""
        self._suppress = False
    
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
            # Check if terminal supports ANSI
            if hasattr(sys.stdout, 'isatty') and sys.stdout.isatty():
                dim = "\033[2m"      # Dim text
                cyan = "\033[36m"    # Cyan for agent name
                reset = "\033[0m"
            else:
                dim = cyan = reset = ""
            
            # Show agent header when agent changes
            if step.agent != self._current_agent:
                self._current_agent = step.agent
                agent_label = step.agent.capitalize()
                print(f"{dim}[Thinking] {cyan}{agent_label}{reset}{dim}...{reset}")
            
            # Show the message
            print(f"{dim}  > {step.message}{reset}")
            
            # Show detail in verbose mode
            if self.verbose and step.detail:
                for line in step.detail.split("\n"):
                    print(f"{dim}    {line}{reset}")
            
            sys.stdout.flush()
        except (UnicodeEncodeError, OSError):
            # Terminal can't render — silently skip
            pass
    
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
                lines.append(f"  [{current_agent.upper()}]")
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
