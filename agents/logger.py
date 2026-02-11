"""
Logger - Structured logging and timing for the agent pipeline.

Replaces print() everywhere with proper logging that supports:
- Pretty mode (emoji + color) for local dev
- JSON mode for production / log aggregation
- Timing context manager for agent performance tracking
"""

import logging
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Dict, Optional


# ── Coloured formatter for local dev ─────────────────────

class PrettyFormatter(logging.Formatter):
    """Human-friendly formatter with emoji prefixes."""

    LEVEL_ICONS = {
        logging.DEBUG: "🔍",
        logging.INFO: "ℹ️ ",
        logging.WARNING: "⚠️ ",
        logging.ERROR: "❌",
        logging.CRITICAL: "🔴",
    }

    def format(self, record: logging.LogRecord) -> str:
        icon = self.LEVEL_ICONS.get(record.levelno, "•")
        # Include extra fields if present
        extras = ""
        for key in ("agent", "duration_ms", "step", "tokens"):
            val = getattr(record, key, None)
            if val is not None:
                extras += f" [{key}={val}]"
        return f"{icon} {record.getMessage()}{extras}"


class JSONFormatter(logging.Formatter):
    """Machine-readable JSON formatter."""

    def format(self, record: logging.LogRecord) -> str:
        import json as _json

        entry = {
            "ts": self.formatTime(record),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        # Merge extra fields
        for key in ("agent", "duration_ms", "step", "tokens", "error"):
            val = getattr(record, key, None)
            if val is not None:
                entry[key] = val
        return _json.dumps(entry)


# ── Logger factory ───────────────────────────────────────

_configured = False


def get_logger(
    name: str,
    level: str = "INFO",
    fmt: str = "pretty",
) -> logging.Logger:
    """
    Get a configured logger for an agent or module.

    Args:
        name: Logger name (e.g. "orchestrator", "reviewer")
        level: Log level string
        fmt: "pretty" or "json"

    Returns:
        Configured logging.Logger
    """
    global _configured
    logger = logging.getLogger(f"ca.{name}")

    if not _configured:
        _configure_root(level, fmt)
        _configured = True

    return logger


def _configure_root(level: str, fmt: str) -> None:
    """One-time root logger setup."""
    root = logging.getLogger("ca")
    root.setLevel(getattr(logging, level.upper(), logging.INFO))

    if root.handlers:
        return  # already configured

    handler = logging.StreamHandler()
    if fmt == "json":
        handler.setFormatter(JSONFormatter())
    else:
        handler.setFormatter(PrettyFormatter())

    root.addHandler(handler)
    root.propagate = False


# ── Timing context manager ───────────────────────────────

@contextmanager
def timed_operation(logger: logging.Logger, operation: str):
    """
    Context manager that logs the duration of an operation.

    Usage:
        with timed_operation(logger, "historian"):
            result = await historian.process(ctx)
    """
    start = time.perf_counter()
    try:
        yield
    finally:
        elapsed_ms = (time.perf_counter() - start) * 1000
        logger.info(
            f"{operation} completed in {elapsed_ms:.0f}ms",
            extra={"duration_ms": round(elapsed_ms, 1), "step": operation},
        )


# ── Pipeline metrics ─────────────────────────────────────

@dataclass
class PipelineMetrics:
    """Tracks timing and cost for a full pipeline run."""

    agent_timings: Dict[str, float] = field(default_factory=dict)  # ms
    total_duration_ms: float = 0.0
    llm_calls: int = 0
    tokens_used: int = 0
    retries: int = 0

    def record_agent(self, name: str, duration_ms: float) -> None:
        self.agent_timings[name] = duration_ms

    def to_dict(self) -> Dict[str, object]:
        return {
            "agent_timings": self.agent_timings,
            "total_duration_ms": round(self.total_duration_ms, 1),
            "llm_calls": self.llm_calls,
            "tokens_used": self.tokens_used,
            "retries": self.retries,
        }

    def summary(self) -> str:
        parts = [f"Total: {self.total_duration_ms:.0f}ms"]
        for agent, ms in self.agent_timings.items():
            parts.append(f"  {agent}: {ms:.0f}ms")
        if self.llm_calls:
            parts.append(f"  LLM calls: {self.llm_calls} ({self.tokens_used} tokens)")
        return "\n".join(parts)
