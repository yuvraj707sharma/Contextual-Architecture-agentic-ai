"""
Clarification Handler — Processes CLARIFICATION_NEEDED signals from the Architect.

The Architect prompt emits a CLARIFICATION_NEEDED signal when a task is
architecturally ambiguous. This handler decides whether to:

1. Proceed with the Architect's default recommendation (log + continue)
2. Halt the pipeline and surface the ambiguity to the caller

Wired into the Orchestrator after the Architect's process() call.
"""

import logging
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger(__name__)


class ClarificationHandler:
    """
    Handles CLARIFICATION_NEEDED signals from the Architect agent.

    Behavior:
    - If can_proceed_with_default is True:
        Log the ambiguity, proceed with the Architect's recommendation.
    - If can_proceed_with_default is False:
        Halt the pipeline and surface the ambiguity to the caller.
    """

    def handle(
        self, architect_output: dict
    ) -> Tuple[bool, dict]:
        """
        Process Architect output, checking for clarification signals.

        Args:
            architect_output: The raw data dict from ArchitectAgent.process()

        Returns:
            (should_continue, processed_output_or_error)
            - should_continue=True  → pipeline continues with cleaned output
            - should_continue=False → pipeline halts, dict has clarification info
        """
        signal = self._extract_signal(architect_output)

        if signal is None:
            # No clarification needed — proceed normally
            return True, architect_output

        ambiguity = signal.get("ambiguity", "Unknown ambiguity")
        can_proceed = signal.get("can_proceed_with_default", False)
        recommendation = signal.get("recommendation", "No recommendation")
        options = signal.get("options", [])

        if can_proceed:
            logger.warning(
                "Architect flagged ambiguity (proceeding with default): %s. "
                "Recommendation: %s",
                ambiguity,
                recommendation,
            )
            # Remove the signal from output, keep the plan
            cleaned = self._remove_signal(architect_output)
            # Tag the plan so Reviewer knows a default was chosen
            if "architect_plan" in cleaned:
                cleaned["architect_plan"].setdefault("risk_factors", []).append(
                    f"AMBIGUITY_DEFAULTED: {ambiguity} → chose: {recommendation}"
                )
            return True, cleaned

        # Cannot proceed — halt pipeline
        logger.error(
            "Architect halted: ambiguity requires human input. "
            "Ambiguity: %s | Options: %s",
            ambiguity,
            options,
        )
        return False, {
            "status": "clarification_required",
            "ambiguity": ambiguity,
            "options": options,
            "recommendation": recommendation,
        }

    def _extract_signal(self, output: dict) -> Optional[dict]:
        """Extract CLARIFICATION_NEEDED signal if present.

        Searches three locations (top-level, architect_plan, coat_reasoning)
        because the LLM may nest the signal differently depending on the
        response structure.
        """
        # Top-level signal
        if output.get("signal") == "CLARIFICATION_NEEDED":
            return output

        # Nested in architect_plan
        plan = output.get("architect_plan", {})
        if isinstance(plan, dict) and plan.get("signal") == "CLARIFICATION_NEEDED":
            return plan

        # Deep-nested in coat_reasoning
        reasoning = plan.get("coat_reasoning", {}) if isinstance(plan, dict) else {}
        if isinstance(reasoning, dict) and reasoning.get("signal") == "CLARIFICATION_NEEDED":
            return reasoning

        return None

    def _remove_signal(self, output: dict) -> dict:
        """Remove the signal keys, keeping the actual plan data intact."""
        signal_keys = {"signal", "ambiguity", "options", "recommendation", "can_proceed_with_default"}
        cleaned = {k: v for k, v in output.items() if k not in signal_keys}
        return cleaned
