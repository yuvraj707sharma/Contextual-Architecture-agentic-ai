"""
Context Budget — Hard resource limits for LLM context windows.

Treats context like a budget, not a free dump. Every upstream agent gets
a token allocation and must stay inside it. The Implementer never receives
more than ~10k tokens of combined context.

Token Counting — Two-Tier Approach:
    Tier 1 (ESTIMATE): Used pre-send for budget enforcement.
           Method: len(text.split()) * 1.3
           Accuracy: ±15% for English/code, ±25% for mixed/CJK

    Tier 2 (ACTUAL): Used post-send for logging/reporting.
           Method: API response usage.prompt_tokens (provider-reported, exact)
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from .logger import get_logger

logger = get_logger("budget")


# ── Token Estimation ─────────────────────────────────────

# Default multiplier: 1 word ≈ 1.3 tokens for English/code.
# Empirically reasonable for OpenAI, Anthropic, DeepSeek.
# Gemini tokenizer may differ by up to ±25% — acceptable for budgeting.
WORD_TO_TOKEN_MULTIPLIER = 1.3


def estimate_tokens(text: str) -> int:
    """Estimate token count from text (Tier 1 — pre-send).

    Uses word-count approximation. NOT exact — use API-reported
    usage.prompt_tokens for actual counts (Tier 2).

    Accuracy:
        ±15% for English prose and code
        ±25% for mixed-language or CJK content

    Args:
        text: The text to estimate tokens for.

    Returns:
        Estimated token count.
    """
    if not text:
        return 0
    return int(len(text.split()) * WORD_TO_TOKEN_MULTIPLIER)


def truncate_to_tokens(text: str, max_tokens: int) -> str:
    """Truncate text to fit within a token budget.

    Truncates at word boundaries (not mid-word) and appends
    a marker so the LLM knows content was truncated.

    Args:
        text: Text to truncate.
        max_tokens: Maximum token budget.

    Returns:
        Truncated text, possibly with '[...truncated]' marker.
    """
    if not text or max_tokens <= 0:
        return ""

    current = estimate_tokens(text)
    if current <= max_tokens:
        return text

    # Approximate: 1 token ≈ 1/1.3 words
    max_words = int(max_tokens / WORD_TO_TOKEN_MULTIPLIER)
    words = text.split()
    truncated = " ".join(words[:max_words])

    return truncated + "\n\n[...truncated to fit token budget]"


# ── Context Budget ────────────────────────────────────────

@dataclass
class ContextBudget:
    """Token budget allocation for the Implementer's context window.

    Each agent gets a slice of the total budget. The sum of all slices
    must not exceed `total`. Budget enforcement happens in the Orchestrator
    after agents produce output and before passing to the Implementer.

    Attributes:
        total:         Hard cap on total tokens sent to the Implementer.
        system_prompt: Fixed — the Implementer's system instructions.
        user_request:  Fixed — the user's original request text.
        planner:       Budget for the Planner Agent's structured plan.
        style:         Budget for StyleFingerprint (rules only, no examples).
        historian:     Budget for Historian patterns (top N relevant only).
        architect:     Budget for Architect output (target + 3 related + 3 utils).
        pr_history:    Budget for PR search summaries (titles + key feedback).
        retry_reserve: Reserved for error feedback on retry attempts.
    """

    total: int = 10_000
    system_prompt: int = 800
    user_request: int = 200
    planner: int = 1_500
    style: int = 500
    historian: int = 2_000
    architect: int = 1_500
    pr_history: int = 1_000
    retry_reserve: int = 2_500

    # ── Factory methods ──────────────────────────────────

    @classmethod
    def for_complexity(cls, complexity: str) -> "ContextBudget":
        """Create a budget scaled to request complexity.

        Simple requests get smaller budgets (less discovery needed).
        Complex requests get the full allocation.

        Args:
            complexity: One of 'simple', 'medium', 'complex'.

        Returns:
            ContextBudget with appropriate allocations.
        """
        if complexity == "simple":
            return cls(
                total=6_000,
                system_prompt=800,
                user_request=200,
                planner=0,       # Simple requests skip the Planner
                style=300,
                historian=1_200,
                architect=1_000,
                pr_history=0,    # Not needed for simple
                retry_reserve=2_500,
            )
        elif complexity == "medium":
            return cls(
                total=8_000,
                system_prompt=800,
                user_request=200,
                planner=1_000,
                style=400,
                historian=1_500,
                architect=1_200,
                pr_history=400,
                retry_reserve=2_500,
            )
        else:  # complex
            return cls()  # Full defaults

    # ── Budget enforcement ───────────────────────────────

    @property
    def agent_budgets(self) -> Dict[str, int]:
        """Return all agent budget allocations as a dict."""
        return {
            "system_prompt": self.system_prompt,
            "user_request": self.user_request,
            "planner": self.planner,
            "style": self.style,
            "historian": self.historian,
            "architect": self.architect,
            "pr_history": self.pr_history,
            "retry_reserve": self.retry_reserve,
        }

    def get_budget(self, agent: str) -> int:
        """Get the token budget for a specific agent.

        Args:
            agent: Agent name (e.g. 'historian', 'architect').

        Returns:
            Token budget for that agent.

        Raises:
            KeyError: If agent name is not recognized.
        """
        budgets = self.agent_budgets
        if agent not in budgets:
            raise KeyError(
                f"Unknown agent '{agent}'. Valid agents: {list(budgets.keys())}"
            )
        return budgets[agent]

    def truncate_for_agent(self, agent: str, content: str) -> str:
        """Truncate agent output to fit its allocated budget.

        Args:
            agent: Agent name (e.g. 'historian', 'architect').
            content: The agent's output text.

        Returns:
            Content truncated to the agent's token budget.
        """
        budget = self.get_budget(agent)
        if budget <= 0:
            return ""
        return truncate_to_tokens(content, budget)

    def check_compliance(self, agent: str, content: str) -> Tuple[bool, str]:
        """Check if an agent's output fits its allocated budget.

        Returns both a boolean and a human-readable message.
        Logs a warning if the agent exceeds its budget.

        Args:
            agent: Agent name.
            content: The agent's output text.

        Returns:
            Tuple of (within_budget, message).
        """
        budget = self.get_budget(agent)
        if budget <= 0:
            return True, f"{agent}: budget=0, skipped"

        actual = estimate_tokens(content)
        within_budget = actual <= budget

        if within_budget:
            pct = (actual / budget) * 100 if budget > 0 else 0
            msg = f"{agent}: {actual}/{budget} tokens ({pct:.0f}% of budget) ✅"
        else:
            overage = ((actual - budget) / budget) * 100
            msg = f"{agent}: {actual}/{budget} tokens ({overage:.0f}% OVER budget) ⚠️"
            logger.warning(msg)

        return within_budget, msg

    def report(self, contents: Dict[str, str]) -> "BudgetReport":
        """Generate a full compliance report for all agent outputs.

        Args:
            contents: Dict mapping agent names to their output text.

        Returns:
            BudgetReport with per-agent compliance data.
        """
        entries = {}
        violations = []
        total_estimated = 0

        for agent, budget in self.agent_budgets.items():
            content = contents.get(agent, "")
            actual = estimate_tokens(content)
            total_estimated += actual

            within_budget, msg = self.check_compliance(agent, content)
            entries[agent] = {
                "budget": budget,
                "estimated": actual,
                "within_budget": within_budget,
            }
            if not within_budget:
                violations.append(msg)

        return BudgetReport(
            entries=entries,
            total_estimated=total_estimated,
            total_budget=self.total,
            violations=violations,
        )


# ── Budget Report ─────────────────────────────────────────

@dataclass
class BudgetReport:
    """Report on token budget compliance across all agents.

    Attributes:
        entries:         Per-agent breakdown of budget vs actual.
        total_estimated: Sum of all estimated token counts.
        total_budget:    The total budget cap.
        violations:      List of human-readable violation messages.
        actual_usage:    Filled in post-LLM-call with real token counts.
    """

    entries: Dict[str, Dict[str, int]] = field(default_factory=dict)
    total_estimated: int = 0
    total_budget: int = 10_000
    violations: List[str] = field(default_factory=list)
    actual_usage: Optional[Dict[str, int]] = None  # Set post-send from API

    @property
    def within_budget(self) -> bool:
        """Whether all agents stayed within their budgets."""
        return len(self.violations) == 0

    def record_actual(self, prompt_tokens: int, completion_tokens: int) -> None:
        """Record actual token usage from the LLM API response.

        This is Tier 2 data — exact, provider-reported. Logged alongside
        Tier 1 estimates so we can calibrate the estimate multiplier.

        Args:
            prompt_tokens: Actual prompt/input tokens from API.
            completion_tokens: Actual completion/output tokens from API.
        """
        self.actual_usage = {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
        }

        # Log estimate vs actual for calibration
        if self.total_estimated > 0:
            error_pct = ((self.total_estimated - prompt_tokens) / prompt_tokens * 100
                         if prompt_tokens > 0 else 0)
            logger.info(
                f"Token estimate accuracy: estimated={self.total_estimated}, "
                f"actual={prompt_tokens}, error={error_pct:+.1f}%"
            )

    def summary(self) -> str:
        """Human-readable summary for CLI output."""
        lines = ["📈 Per-Agent Context:"]
        for agent, data in self.entries.items():
            if data["budget"] == 0:
                continue
            check = "✅" if data["within_budget"] else "⚠️"
            lines.append(
                f"   {agent:>12s}: {data['estimated']:>5,} / {data['budget']:>5,} {check}"
            )

        used_pct = (self.total_estimated / self.total_budget * 100
                    if self.total_budget > 0 else 0)
        lines.append(
            f"\n📊 Total: {self.total_estimated:,} / {self.total_budget:,} "
            f"({used_pct:.0f}% of budget)"
        )

        if self.actual_usage:
            lines.append(
                f"   Actual (API): {self.actual_usage['prompt_tokens']:,} input, "
                f"{self.actual_usage['completion_tokens']:,} output"
            )

        if self.violations:
            lines.append(f"\n⚠️  {len(self.violations)} budget violation(s):")
            for v in self.violations:
                lines.append(f"   {v}")

        return "\n".join(lines)

    def to_dict(self) -> Dict[str, object]:
        """Convert to dict for JSON serialization (token_report.json)."""
        return {
            "budget_allocated": {
                agent: data["budget"] for agent, data in self.entries.items()
            },
            "budget_actual": {
                agent: data["estimated"] for agent, data in self.entries.items()
            },
            "total_estimated": self.total_estimated,
            "total_budget": self.total_budget,
            "budget_violations": self.violations,
            "actual_usage": self.actual_usage,
        }


# ── Retry Error Compression ──────────────────────────────

@dataclass
class AttemptRecord:
    """Record of a single generation attempt for the retry window.

    Attributes:
        attempt:    Attempt number (1-indexed).
        code:       The generated code from this attempt.
        errors:     Error messages from Reviewer/Alignment.
        token_count: Estimated token count of the code.
    """

    attempt: int
    code: str
    errors: List[str]
    token_count: int = 0

    def __post_init__(self):
        self.token_count = estimate_tokens(self.code)


def compress_retry_errors(
    attempts: List[AttemptRecord],
    max_tokens: int = 2_500,
) -> str:
    """Compress retry context using a sliding window strategy.

    The strategy (from the implementation plan):
    - Attempt 1 fails → send full errors to Implementer
    - Attempt 2 fails → compress attempt 1 to one-line summary,
                         send full attempt 2 errors
    - Attempt 3       → compressed summary of both previous failures +
                         only top 3 errors from attempt 2 +
                         the code from the closest-to-passing attempt

    The context NEVER grows unboundedly — it maintains a rolling
    compressed window that stays within max_tokens.

    Args:
        attempts: List of AttemptRecords from previous attempts.
        max_tokens: Maximum token budget for retry context.

    Returns:
        Formatted retry context string within the token budget.
    """
    if not attempts:
        return ""

    parts = []

    if len(attempts) == 1:
        # First retry: send full errors + the code
        attempt = attempts[0]
        parts.append(f"## Previous Attempt (attempt {attempt.attempt}) — FAILED")
        parts.append(f"Errors ({len(attempt.errors)}):")
        for err in attempt.errors:
            parts.append(f"- {err}")
        parts.append(f"\nCode that failed:\n```\n{attempt.code}\n```")

    elif len(attempts) == 2:
        # Second retry: compress first, full second
        a1, a2 = attempts

        # Compress attempt 1 to one-line summary
        parts.append("## Attempt History")
        parts.append(
            f"- Attempt {a1.attempt}: FAILED with {len(a1.errors)} error(s) — "
            f"{_summarize_errors(a1.errors)}"
        )

        # Full attempt 2 errors
        parts.append(f"\n## Most Recent Attempt ({a2.attempt}) — FAILED")
        parts.append(f"Errors ({len(a2.errors)}):")
        for err in a2.errors:
            parts.append(f"- {err}")

        # Keep code from the closest-to-passing attempt
        best = min(attempts, key=lambda a: len(a.errors))
        parts.append(
            f"\nClosest-to-passing code (attempt {best.attempt}):"
            f"\n```\n{best.code}\n```"
        )

    else:
        # 3+ retries: compressed summaries + top 3 errors from latest + best code
        latest = attempts[-1]
        previous = attempts[:-1]

        parts.append("## Attempt History (compressed)")
        for a in previous:
            parts.append(
                f"- Attempt {a.attempt}: FAILED with {len(a.errors)} error(s) — "
                f"{_summarize_errors(a.errors)}"
            )

        # Top 3 errors from the most recent attempt only
        parts.append(f"\n## Most Recent Attempt ({latest.attempt}) — FAILED")
        top_errors = latest.errors[:3]
        parts.append(f"Top errors ({len(top_errors)} of {len(latest.errors)}):")
        for err in top_errors:
            parts.append(f"- {err}")

        # Best code (fewest errors across all attempts)
        best = min(attempts, key=lambda a: len(a.errors))
        parts.append(
            f"\nClosest-to-passing code (attempt {best.attempt}):"
            f"\n```\n{best.code}\n```"
        )

    result = "\n".join(parts)

    # Hard enforcement: never exceed the budget
    return truncate_to_tokens(result, max_tokens)


def _summarize_errors(errors: List[str]) -> str:
    """Compress a list of errors into a single-line summary.

    Examples:
        ["NameError: undefined 'foo'", "SyntaxError: ..."]
        → "NameError, SyntaxError (2 errors)"
    """
    if not errors:
        return "no errors recorded"

    # Extract error types (first word before ':')
    types = []
    for err in errors:
        err_type = err.split(":")[0].split(".")[-1].strip()
        if err_type and err_type not in types:
            types.append(err_type)

    if types:
        return f"{', '.join(types[:3])} ({len(errors)} error(s))"
    return f"{len(errors)} error(s)"


# ── Complexity Scoring ────────────────────────────────────

def score_complexity(user_request: str) -> str:
    """Score request complexity for budget allocation and gating.

    Heuristic scoring based on request text. Used to decide:
    - Which budget to use (simple=6k, medium=8k, complex=10k)
    - Whether to run the Planner (skip for simple)
    - Whether to run the Alignment Agent (skip for simple)
    - Whether to auto-proceed at checkpoints

    Args:
        user_request: The user's code generation request.

    Returns:
        One of 'simple', 'medium', 'complex'.
    """
    request_lower = user_request.lower()
    word_count = len(user_request.split())

    # ── Complex indicators ───────────────────────────
    complex_indicators = [
        "refactor", "migrate", "redesign", "architecture",
        "multi-file", "across files", "system", "pipeline",
        "integrate", "authentication", "authorization",
        "database schema", "api gateway", "microservice",
    ]
    complex_score = sum(1 for ind in complex_indicators if ind in request_lower)

    # ── Simple indicators ────────────────────────────
    simple_indicators = [
        "add a function", "add a method", "add a helper",
        "add a utility", "create a file", "rename",
        "fix typo", "update comment", "add docstring",
        "add a test", "simple", "basic",
    ]
    simple_score = sum(1 for ind in simple_indicators if ind in request_lower)

    # ── Decision ─────────────────────────────────────
    if complex_score >= 2 or word_count > 50:
        return "complex"
    elif simple_score >= 1 and complex_score == 0 and word_count <= 20:
        return "simple"
    else:
        return "medium"
