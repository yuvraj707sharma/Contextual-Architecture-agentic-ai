"""
Clarification Handler — Proactive conflict detection + Architect signal processing.

Two modes:
1. PROACTIVE (new): Compares user request against ProjectScanner findings
   to surface conflicts like "project uses Firebase but you asked for Supabase".
   Runs BEFORE the Planner, giving users a chance to clarify intent.

2. REACTIVE (existing): Processes CLARIFICATION_NEEDED signals from the Architect
   when a task is architecturally ambiguous.

Wired into the Orchestrator after Discovery and before Planner.
"""

import logging
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# ── Conflict detection rules ──────────────────────────────

AUTH_KEYWORDS = {
    "firebase": "firebase", "supabase": "supabase", "auth0": "auth0",
    "clerk": "clerk", "jwt": "jwt", "passport": "passport",
    "nextauth": "nextauth", "oauth": "oauth",
}

FRAMEWORK_KEYWORDS = {
    "react": "react", "vue": "vue", "angular": "angular", "svelte": "svelte",
    "next": "next.js", "nuxt": "nuxt", "express": "express", "fastify": "fastify",
    "flask": "flask", "django": "django", "fastapi": "fastapi",
    "streamlit": "streamlit", "gin": "gin", "fiber": "fiber",
}

DB_KEYWORDS = {
    "postgres": "postgresql", "postgresql": "postgresql", "mongodb": "mongodb",
    "mongo": "mongodb", "mysql": "mysql", "sqlite": "sqlite", "redis": "redis",
    "prisma": "prisma", "sqlalchemy": "sqlalchemy", "drizzle": "drizzle",
}

# Framework groups — conflicts only within the same group
_FRONTEND_FRAMEWORKS = {"react", "vue", "angular", "svelte"}
_BACKEND_PY_FRAMEWORKS = {"flask", "django", "fastapi"}
_BACKEND_JS_FRAMEWORKS = {"express", "fastify", "nest.js"}


@dataclass
class ConflictQuestion:
    """A proactive question surfaced before planning."""
    category: str       # "auth", "framework", "database", "language"
    question: str       # Human-readable question
    detected: str       # What the scanner found (e.g., "firebase")
    requested: str      # What the user asked for (e.g., "supabase")
    default_action: str # What MACRO will do if user doesn't respond


class ClarificationHandler:
    """
    Handles both PROACTIVE conflict detection and REACTIVE Architect signals.

    Proactive mode:
    - Compares user request against ProjectScanner findings
    - Surfaces conflicts: auth changes, framework mismatches, DB switches
    - In interactive mode: pauses for user input
    - In single-shot mode: logs assumptions and proceeds

    Reactive mode:
    - Checks for CLARIFICATION_NEEDED signals from Architect
    - Halts or proceeds based on can_proceed_with_default flag
    """

    # ── PROACTIVE: Conflict detection ─────────────────────

    def detect_conflicts(
        self,
        user_request: str,
        project_snapshot: Optional[Dict[str, Any]] = None,
        language: str = "",
    ) -> List[ConflictQuestion]:
        """Proactively detect conflicts between user request and project state.

        Args:
            user_request: What the user wants to build
            project_snapshot: The ProjectSnapshot.to_dict() output from scanner
            language: The target language (from CLI --lang)

        Returns:
            List of ConflictQuestion objects (empty = no conflicts)
        """
        if not project_snapshot:
            return []

        questions: List[ConflictQuestion] = []
        request_lower = user_request.lower()

        def _kw_match(keyword: str) -> bool:
            """Word-boundary match to avoid false positives.
            e.g., 'next' won't match 'the next feature'
            """
            return bool(re.search(rf'\b{re.escape(keyword)}\b', request_lower))

        # ── Auth system conflicts ────────────────────────────
        existing_auth = set(project_snapshot.get("auth_systems", []))
        if existing_auth:
            for keyword, auth_name in AUTH_KEYWORDS.items():
                if _kw_match(keyword) and auth_name not in existing_auth:
                    existing_str = ", ".join(existing_auth)
                    questions.append(ConflictQuestion(
                        category="auth",
                        question=(
                            f"Your project uses **{existing_str}** for auth, "
                            f"but you asked for **{auth_name}**. "
                            f"Migrate from {existing_str} → {auth_name}, "
                            f"or add {auth_name} alongside?"
                        ),
                        detected=existing_str,
                        requested=auth_name,
                        default_action=f"Add {auth_name} alongside {existing_str}",
                    ))

        # ── Framework conflicts ──────────────────────────────
        existing_fw = set(project_snapshot.get("frameworks", []))
        if existing_fw:
            for keyword, fw_name in FRAMEWORK_KEYWORDS.items():
                if _kw_match(keyword) and fw_name not in existing_fw:
                    for group in [_FRONTEND_FRAMEWORKS, _BACKEND_PY_FRAMEWORKS, _BACKEND_JS_FRAMEWORKS]:
                        if fw_name in group and (existing_fw & group):
                            conflicting = existing_fw & group
                            questions.append(ConflictQuestion(
                                category="framework",
                                question=(
                                    f"Your project uses **{', '.join(conflicting)}** "
                                    f"but you mentioned **{fw_name}**. "
                                    f"Adding a new {fw_name} service, or migrating?"
                                ),
                                detected=", ".join(conflicting),
                                requested=fw_name,
                                default_action=f"Add {fw_name} code alongside existing framework",
                            ))

        # ── Database conflicts ───────────────────────────────
        existing_db = set(project_snapshot.get("databases", []))
        if existing_db:
            for keyword, db_name in DB_KEYWORDS.items():
                if _kw_match(keyword) and db_name not in existing_db:
                    existing_str = ", ".join(existing_db)
                    questions.append(ConflictQuestion(
                        category="database",
                        question=(
                            f"Your project uses **{existing_str}**, "
                            f"but you referenced **{db_name}**. "
                            f"Migrate to {db_name}, or add as additional data source?"
                        ),
                        detected=existing_str,
                        requested=db_name,
                        default_action=f"Add {db_name} alongside {existing_str}",
                    ))

        # ── Language mismatch ────────────────────────────────
        project_lang = project_snapshot.get("language", "")
        if language and project_lang and language.lower() != project_lang.lower():
            questions.append(ConflictQuestion(
                category="language",
                question=(
                    f"Project is primarily **{project_lang}**, "
                    f"but you specified **--lang {language}**. "
                    f"Generate {language} code in this {project_lang} project?"
                ),
                detected=project_lang,
                requested=language,
                default_action=f"Generate {language} code as requested",
            ))

        # Deduplicate by (category, requested)
        seen: set = set()
        unique: List[ConflictQuestion] = []
        for q in questions:
            key = (q.category, q.requested)
            if key not in seen:
                seen.add(key)
                unique.append(q)

        return unique

    def format_questions(self, questions: List[ConflictQuestion]) -> str:
        """Format conflict questions for terminal display."""
        if not questions:
            return ""

        lines = ["\n  \u26a0\ufe0f  MACRO detected potential conflicts:\n"]
        for i, q in enumerate(questions, 1):
            lines.append(f"  [{i}] {q.question}")
            lines.append(f"      \u2192 Default: {q.default_action}")
            lines.append("")

        lines.append("  Press Enter to use defaults, or type your clarification.")
        return "\n".join(lines)

    def questions_to_context(self, questions: List[ConflictQuestion]) -> str:
        """Convert questions to context string for the Planner's prompt.

        When running in single-shot mode (no user interaction), we log
        the assumptions so the Planner can factor them into its plan.
        """
        if not questions:
            return ""

        lines = ["## \u26a0\ufe0f Detected Conflicts (defaults applied)"]
        for q in questions:
            lines.append(
                f"- **{q.category.upper()}**: Project has {q.detected}, "
                f"user wants {q.requested}. "
                f"Action: {q.default_action}"
            )
        return "\n".join(lines)

    # ── REACTIVE: Architect signal handling ────────────────

    def handle(
        self, architect_output: dict
    ) -> Tuple[bool, dict]:
        """
        Process Architect output, checking for clarification signals.

        Args:
            architect_output: The raw data dict from ArchitectAgent.process()

        Returns:
            (should_continue, processed_output_or_error)
            - should_continue=True  → pipeline proceeds with cleaned output
            - should_continue=False → pipeline halts, dict has clarification info
        """
        signal = self._extract_signal(architect_output)

        if signal is None:
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
            cleaned = self._remove_signal(architect_output)
            if "architect_plan" in cleaned:
                cleaned["architect_plan"].setdefault("risk_factors", []).append(
                    f"AMBIGUITY_DEFAULTED: {ambiguity} \u2192 chose: {recommendation}"
                )
            return True, cleaned

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
        """Extract CLARIFICATION_NEEDED signal if present."""
        if output.get("signal") == "CLARIFICATION_NEEDED":
            return output

        plan = output.get("architect_plan", {})
        if isinstance(plan, dict) and plan.get("signal") == "CLARIFICATION_NEEDED":
            return plan

        reasoning = plan.get("coat_reasoning", {}) if isinstance(plan, dict) else {}
        if isinstance(reasoning, dict) and reasoning.get("signal") == "CLARIFICATION_NEEDED":
            return reasoning

        return None

    def _remove_signal(self, output: dict) -> dict:
        """Remove the signal keys, keeping the actual plan data intact."""
        signal_keys = {"signal", "ambiguity", "options", "recommendation", "can_proceed_with_default"}
        return {k: v for k, v in output.items() if k not in signal_keys}
