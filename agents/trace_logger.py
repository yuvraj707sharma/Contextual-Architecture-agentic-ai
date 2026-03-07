"""
Trace Logger -- Saves agent I/O for distillation data collection.

Every MACRO pipeline run saves a JSONL trace to:
  ~/.contextual-architect/traces/YYYY-MM-DD.jsonl

Each line is one complete pipeline run with all agent inputs/outputs.
This data is used for future model distillation (QLoRA fine-tuning).

The traces are append-only, one JSON object per line.
"""

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


class TraceLogger:
    """Collects and saves agent traces for distillation."""

    def __init__(self):
        self._traces: List[Dict[str, Any]] = []
        self._run_id = f"{int(time.time())}_{os.getpid()}"
        self._start_time = time.perf_counter()
        self._metadata: Dict[str, Any] = {}

    def set_metadata(
        self,
        user_request: str,
        repo_path: str,
        language: str,
        provider: str = "",
        model: str = "",
    ):
        """Set run-level metadata."""
        # Don't log the full repo path (privacy) -- just the repo name
        repo_name = Path(repo_path).name if repo_path else "unknown"
        self._metadata = {
            "run_id": self._run_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "user_request": user_request,
            "repo_name": repo_name,
            "language": language,
            "provider": provider,
            "model": model,
        }

    def log_agent(
        self,
        agent: str,
        input_summary: str,
        output_summary: str,
        output_data: Optional[Dict[str, Any]] = None,
        success: bool = True,
        attempt: int = 1,
    ):
        """Log a single agent's input/output.

        Args:
            agent: Agent name (historian, architect, planner, etc.)
            input_summary: Condensed input (NOT full prompts -- those are huge)
            output_summary: Agent's summary string
            output_data: Agent's structured output data
            success: Whether the agent succeeded
            attempt: Which attempt (for retry loop agents)
        """
        # Truncate large data to keep traces manageable
        data = _truncate_data(output_data, max_str_len=2000) if output_data else {}

        self._traces.append({
            "agent": agent,
            "attempt": attempt,
            "success": success,
            "input_summary": input_summary[:500],
            "output_summary": output_summary[:500],
            "output_data": data,
            "elapsed_ms": round((time.perf_counter() - self._start_time) * 1000),
        })

    def log_result(
        self,
        success: bool,
        attempts: int,
        generated_code_len: int = 0,
        errors: Optional[List[str]] = None,
    ):
        """Log final pipeline result."""
        self._metadata["final_success"] = success
        self._metadata["total_attempts"] = attempts
        self._metadata["generated_code_len"] = generated_code_len
        self._metadata["errors"] = (errors or [])[:5]  # Cap at 5 errors
        self._metadata["total_duration_ms"] = round(
            (time.perf_counter() - self._start_time) * 1000
        )

    def save(self):
        """Save trace to ~/.contextual-architect/traces/ as JSONL."""
        try:
            traces_dir = Path.home() / ".contextual-architect" / "traces"
            traces_dir.mkdir(parents=True, exist_ok=True)

            # One file per day (keeps files manageable)
            date_str = datetime.now().strftime("%Y-%m-%d")
            trace_file = traces_dir / f"{date_str}.jsonl"

            record = {
                **self._metadata,
                "agent_traces": self._traces,
            }

            with open(trace_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, default=str) + "\n")

        except Exception:
            pass  # Trace logging should NEVER break the pipeline


def _truncate_data(data: Any, max_str_len: int = 2000, max_depth: int = 3) -> Any:
    """Recursively truncate large strings in data structures."""
    if max_depth <= 0:
        return "<truncated>"

    if isinstance(data, str):
        if len(data) > max_str_len:
            return data[:max_str_len] + f"... ({len(data)} chars total)"
        return data
    elif isinstance(data, dict):
        return {
            k: _truncate_data(v, max_str_len, max_depth - 1)
            for k, v in data.items()
        }
    elif isinstance(data, (list, tuple)):
        return [_truncate_data(item, max_str_len, max_depth - 1) for item in data[:20]]
    else:
        return data
