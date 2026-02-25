"""
Alignment Agent — Semantic check between Planner and Implementer.

Phase C2 of the pipeline. Runs AFTER the Planner but BEFORE the
Implementer to catch misalignment early (cheaper than regenerating).

Gated by complexity:
  - simple  → skip (not worth the LLM call)
  - medium  → run (catch plan-vs-request drift)
  - complex → run (critical for multi-file changes)

Two modes:
  1. LLM-powered: asks the LLM "does this plan address the request?"
  2. Heuristic fallback: basic keyword/structure checks
"""

import re
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional

from .base import BaseAgent, AgentContext, AgentResponse, AgentRole
from .logger import get_logger

logger = get_logger("alignment")


@dataclass
class AlignmentOutput:
    """Result of the alignment check."""

    aligned: bool
    concerns: List[str] = field(default_factory=list)
    suggestions: List[str] = field(default_factory=list)
    skipped: bool = False
    skip_reason: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "aligned": self.aligned,
            "concerns": self.concerns,
            "suggestions": self.suggestions,
            "skipped": self.skipped,
            "skip_reason": self.skip_reason,
        }

    def to_markdown(self) -> str:
        if self.skipped:
            return f"_Alignment check skipped: {self.skip_reason}_"

        lines = [f"**Aligned:** {'✅ Yes' if self.aligned else '❌ No'}"]

        if self.concerns:
            lines.append("\n**Concerns:**")
            for c in self.concerns:
                lines.append(f"- ⚠️ {c}")

        if self.suggestions:
            lines.append("\n**Suggestions:**")
            for s in self.suggestions:
                lines.append(f"- 💡 {s}")

        return "\n".join(lines)


class AlignmentAgent(BaseAgent):
    """
    Semantic alignment check between plan and user request.

    Catches problems like:
    - Plan addresses the wrong feature
    - Plan is missing key requirements from the request
    - Plan modifies files unrelated to the request
    - Plan has no clear acceptance criteria

    Gated by complexity — skips for simple tasks.
    """

    # Keywords that suggest specific requirements in a user request
    REQUIREMENT_SIGNALS = {
        "auth": ["token", "jwt", "login", "password", "session", "cookie"],
        "test": ["test", "spec", "assert", "mock", "fixture", "coverage"],
        "api": ["endpoint", "route", "handler", "middleware", "request", "response"],
        "database": ["model", "schema", "migration", "query", "table", "column"],
        "security": ["encrypt", "hash", "sanitize", "validate", "cors", "csrf"],
        "config": ["env", "setting", "configuration", "option", "flag"],
        "cache": ["cache", "redis", "memcache", "ttl", "invalidate"],
        "log": ["log", "logging", "logger", "trace", "debug"],
    }

    def __init__(self, llm_client=None):
        super().__init__(llm_client)

    @property
    def role(self) -> AgentRole:
        return AgentRole.ALIGNMENT

    @property
    def system_prompt(self) -> str:
        return "You validate that a code generation plan correctly addresses the user's request."

    async def process(self, context: AgentContext) -> AgentResponse:
        """
        Check alignment between user request and plan.

        Args:
            context: AgentContext with prior_context containing:
                - 'plan': PlannerOutput dict
                - 'complexity': scored complexity string

        Returns:
            AgentResponse with AlignmentOutput in data
        """
        complexity = context.prior_context.get("complexity", "medium")

        # Gate: skip for simple tasks
        if complexity == "simple":
            output = AlignmentOutput(
                aligned=True,
                skipped=True,
                skip_reason="Simple task — alignment check not needed",
            )
            return self._create_response(
                success=True,
                data=output.to_dict(),
                summary="Skipped (simple task)",
            )

        plan = context.prior_context.get("plan", {})

        if not plan:
            output = AlignmentOutput(
                aligned=False,
                concerns=["No plan found in context — cannot verify alignment"],
            )
            return self._create_response(
                success=True,
                data=output.to_dict(),
                summary="No plan to check",
                warnings=["Plan missing from context"],
            )

        # Try LLM-powered check first, fall back to heuristic
        if self.llm_client:
            output = await self._check_with_llm(context, plan)
        else:
            output = self._check_heuristic(context, plan)

        return self._create_response(
            success=True,
            data=output.to_dict(),
            summary=(
                f"{'Aligned' if output.aligned else 'Misaligned'}: "
                f"{len(output.concerns)} concerns, {len(output.suggestions)} suggestions"
            ),
            warnings=output.concerns if not output.aligned else [],
        )

    # ── Heuristic Mode ───────────────────────────────────────

    def _check_heuristic(
        self, context: AgentContext, plan: Dict[str, Any]
    ) -> AlignmentOutput:
        """Basic alignment check using keyword and structure analysis."""
        concerns: List[str] = []
        suggestions: List[str] = []
        request_lower = context.user_request.lower()

        # 1. Check that plan has acceptance criteria
        criteria = plan.get("acceptance_criteria", [])
        if not criteria:
            concerns.append(
                "Plan has no acceptance criteria — "
                "Implementer won't know when it's done"
            )

        # 2. Check goal references the user request
        goal = plan.get("goal", "").lower()
        request_words = set(self._extract_keywords(request_lower))
        goal_words = set(self._extract_keywords(goal))
        overlap = request_words & goal_words

        if request_words and len(overlap) < max(1, len(request_words) // 3):
            concerns.append(
                f"Plan goal has low keyword overlap with request "
                f"({len(overlap)}/{len(request_words)} keywords match)"
            )

        # 3. Check for requirement coverage
        detected_domains = self._detect_domains(request_lower)
        criteria_text = " ".join(criteria).lower()
        plan_text = f"{goal} {criteria_text} {plan.get('approach', '')}".lower()

        for domain, keywords in detected_domains.items():
            found = any(kw in plan_text for kw in keywords)
            if not found:
                suggestions.append(
                    f"Request mentions '{domain}' but plan doesn't "
                    f"address it explicitly"
                )

        # 4. Check that target files exist
        target_files = plan.get("target_files", [])
        if not target_files:
            concerns.append(
                "Plan specifies no target files — "
                "Implementer won't know where to write code"
            )

        # 5. Check for do_not list (anti-patterns)
        do_not = plan.get("do_not", [])
        if not do_not and len(criteria) > 3:
            suggestions.append(
                "Complex plan has no 'do not' list — "
                "consider adding anti-patterns to avoid"
            )

        aligned = len(concerns) == 0
        return AlignmentOutput(
            aligned=aligned,
            concerns=concerns,
            suggestions=suggestions,
        )

    def _extract_keywords(self, text: str) -> List[str]:
        """Extract meaningful keywords from text, filtering stopwords."""
        stopwords = {
            "a", "an", "the", "is", "it", "to", "for", "of", "in", "on",
            "and", "or", "but", "with", "that", "this", "be", "as", "at",
            "by", "from", "are", "was", "were", "been", "has", "have",
            "had", "do", "does", "did", "will", "would", "could", "should",
            "may", "might", "can", "shall", "i", "we", "you", "he", "she",
            "they", "me", "us", "my", "our", "your", "add", "create",
            "make", "build", "implement", "write", "new",
        }
        words = re.findall(r"[a-z][a-z0-9_]+", text.lower())
        return [w for w in words if w not in stopwords and len(w) > 2]

    def _detect_domains(self, text: str) -> Dict[str, List[str]]:
        """Detect which requirement domains the request touches."""
        found: Dict[str, List[str]] = {}
        for domain, keywords in self.REQUIREMENT_SIGNALS.items():
            if any(kw in text for kw in keywords):
                found[domain] = keywords
        return found

    # ── LLM Mode ─────────────────────────────────────────────

    async def _check_with_llm(
        self, context: AgentContext, plan: Dict[str, Any]
    ) -> AlignmentOutput:
        """Use LLM to semantically validate plan-to-request alignment."""
        prompt = self._build_llm_prompt(context, plan)

        try:
            response = await self.llm_client.generate(
                system_prompt=self.system_prompt,
                user_prompt=prompt,
                temperature=0.0,
                max_tokens=1024,
            )
            return self._parse_llm_response(response.content)
        except Exception as e:
            logger.warning(f"LLM alignment check failed, falling back: {e}")
            return self._check_heuristic(context, plan)

    def _build_llm_prompt(
        self, context: AgentContext, plan: Dict[str, Any]
    ) -> str:
        """Build the prompt for LLM alignment check."""
        criteria = plan.get("acceptance_criteria", [])
        target_files = plan.get("target_files", [])
        approach = plan.get("approach", "Not specified")

        criteria_text = "\n".join(f"  - {c}" for c in criteria) if criteria else "  (none)"
        files_text = "\n".join(
            f"  - {f.get('path', f)}: {f.get('action', '?')}"
            if isinstance(f, dict) else f"  - {f}"
            for f in target_files
        ) if target_files else "  (none)"

        return (
            f"## User Request\n{context.user_request}\n\n"
            f"## Plan Goal\n{plan.get('goal', 'Not specified')}\n\n"
            f"## Acceptance Criteria\n{criteria_text}\n\n"
            f"## Target Files\n{files_text}\n\n"
            f"## Approach\n{approach}\n\n"
            "---\n"
            "Analyze whether this plan correctly addresses the user's request.\n\n"
            "Respond in EXACTLY this format:\n"
            "ALIGNED: yes/no\n"
            "CONCERNS:\n"
            "- concern 1\n"
            "- concern 2\n"
            "SUGGESTIONS:\n"
            "- suggestion 1\n"
        )

    def _parse_llm_response(self, response: str) -> AlignmentOutput:
        """Parse LLM response into AlignmentOutput."""
        lines = response.strip().split("\n")

        aligned = True
        concerns: List[str] = []
        suggestions: List[str] = []
        section = ""

        for line in lines:
            stripped = line.strip()
            upper = stripped.upper()

            if upper.startswith("ALIGNED:"):
                value = stripped.split(":", 1)[1].strip().lower()
                aligned = value in ("yes", "true", "✅")
            elif upper.startswith("CONCERNS:"):
                section = "concerns"
            elif upper.startswith("SUGGESTIONS:"):
                section = "suggestions"
            elif stripped.startswith("- ") or stripped.startswith("• "):
                item = stripped.lstrip("-•").strip()
                if item:
                    if section == "concerns":
                        concerns.append(item)
                    elif section == "suggestions":
                        suggestions.append(item)

        return AlignmentOutput(
            aligned=aligned,
            concerns=concerns,
            suggestions=suggestions,
        )
