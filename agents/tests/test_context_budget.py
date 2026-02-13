"""
Tests for context_budget module.

Covers:
- Token estimation accuracy
- Budget allocation and compliance
- Retry error compression (sliding window)
- Complexity scoring
- Budget reports
"""

import pytest
from agents.context_budget import (
    estimate_tokens,
    truncate_to_tokens,
    ContextBudget,
    BudgetReport,
    AttemptRecord,
    compress_retry_errors,
    score_complexity,
    WORD_TO_TOKEN_MULTIPLIER,
)


# ── Token Estimation ─────────────────────────────────────

class TestEstimateTokens:
    """Tier 1 token counting — word-based approximation."""

    def test_empty_string(self):
        assert estimate_tokens("") == 0

    def test_single_word(self):
        result = estimate_tokens("hello")
        assert result == int(1 * WORD_TO_TOKEN_MULTIPLIER)

    def test_typical_code_line(self):
        code = "def delete_task(task_id: str) -> bool:"
        result = estimate_tokens(code)
        # 7 words × 1.3 ≈ 9 tokens
        assert 5 <= result <= 15

    def test_multiline_code(self):
        code = """
def delete_task(task_id):
    for i, task in enumerate(tasks_db):
        if task["id"] == task_id:
            tasks_db.pop(i)
            return True
    return False
"""
        result = estimate_tokens(code)
        # ~25 words × 1.3 ≈ 32 tokens
        assert 20 <= result <= 50

    def test_large_text(self):
        # 1000 words should produce ~1300 tokens
        text = " ".join(["word"] * 1000)
        result = estimate_tokens(text)
        assert 1200 <= result <= 1400


class TestTruncateToTokens:
    """Budget-aware text truncation."""

    def test_within_budget(self):
        text = "short text"
        result = truncate_to_tokens(text, max_tokens=100)
        assert result == text
        assert "[...truncated" not in result

    def test_over_budget(self):
        text = " ".join(["word"] * 1000)
        result = truncate_to_tokens(text, max_tokens=100)
        assert "[...truncated" in result
        assert estimate_tokens(result.split("[...truncated")[0]) <= 110  # some slack

    def test_zero_budget(self):
        assert truncate_to_tokens("hello world", max_tokens=0) == ""

    def test_empty_text(self):
        assert truncate_to_tokens("", max_tokens=100) == ""


# ── Context Budget ────────────────────────────────────────

class TestContextBudget:
    """Budget allocation and enforcement."""

    def test_default_budget_totals(self):
        budget = ContextBudget()
        assert budget.total == 10_000
        assert budget.system_prompt == 800
        assert budget.historian == 2_000

    def test_simple_complexity(self):
        budget = ContextBudget.for_complexity("simple")
        assert budget.total == 6_000
        assert budget.planner == 0  # Planner skipped for simple
        assert budget.pr_history == 0

    def test_medium_complexity(self):
        budget = ContextBudget.for_complexity("medium")
        assert budget.total == 8_000
        assert budget.planner > 0

    def test_complex_complexity(self):
        budget = ContextBudget.for_complexity("complex")
        assert budget.total == 10_000  # Full defaults

    def test_agent_budgets_dict(self):
        budget = ContextBudget()
        budgets = budget.agent_budgets
        assert "historian" in budgets
        assert "architect" in budgets
        assert "planner" in budgets
        assert budgets["historian"] == 2_000

    def test_get_budget(self):
        budget = ContextBudget()
        assert budget.get_budget("historian") == 2_000

    def test_get_budget_invalid(self):
        budget = ContextBudget()
        with pytest.raises(KeyError, match="Unknown agent"):
            budget.get_budget("nonexistent_agent")

    def test_truncate_for_agent_within_budget(self):
        budget = ContextBudget()
        short_content = "This is a short historian output."
        result = budget.truncate_for_agent("historian", short_content)
        assert result == short_content

    def test_truncate_for_agent_over_budget(self):
        budget = ContextBudget()
        # Create content that's way over 2000 tokens
        long_content = " ".join(["pattern_match"] * 5000)
        result = budget.truncate_for_agent("historian", long_content)
        assert "[...truncated" in result
        # Truncated result should be roughly within budget
        assert estimate_tokens(result.split("[...truncated")[0]) <= 2200

    def test_truncate_for_agent_zero_budget(self):
        budget = ContextBudget.for_complexity("simple")
        result = budget.truncate_for_agent("planner", "some plan content")
        assert result == ""  # Planner budget is 0 for simple

    def test_check_compliance_passing(self):
        budget = ContextBudget()
        within, msg = budget.check_compliance("historian", "short output")
        assert within is True
        assert "✅" in msg

    def test_check_compliance_failing(self):
        budget = ContextBudget()
        huge = " ".join(["pattern"] * 5000)
        within, msg = budget.check_compliance("historian", huge)
        assert within is False
        assert "OVER" in msg
        assert "⚠️" in msg


# ── Budget Report ─────────────────────────────────────────

class TestBudgetReport:
    """Full compliance reporting."""

    def test_report_all_within_budget(self):
        budget = ContextBudget()
        contents = {
            "system_prompt": "You are an implementer.",
            "user_request": "Add delete_task function",
            "planner": "## Goal\nAdd delete",
            "style": "Use snake_case.",
            "historian": "Pattern: error handling",
            "architect": "Target: app.py",
            "pr_history": "",
            "retry_reserve": "",
        }
        report = budget.report(contents)
        assert report.within_budget
        assert len(report.violations) == 0
        assert report.total_estimated < budget.total

    def test_report_with_violation(self):
        budget = ContextBudget()
        huge_historian = " ".join(["pattern_match_detail"] * 5000)
        contents = {
            "system_prompt": "x",
            "user_request": "x",
            "planner": "x",
            "style": "x",
            "historian": huge_historian,
            "architect": "x",
            "pr_history": "",
            "retry_reserve": "",
        }
        report = budget.report(contents)
        assert not report.within_budget
        assert len(report.violations) >= 1
        assert "historian" in report.violations[0].lower()

    def test_report_summary_output(self):
        budget = ContextBudget()
        contents = {
            "system_prompt": "x",
            "user_request": "x",
            "planner": "x",
            "style": "x",
            "historian": "x",
            "architect": "x",
            "pr_history": "",
            "retry_reserve": "",
        }
        report = budget.report(contents)
        summary = report.summary()
        assert "Per-Agent Context" in summary
        assert "Total" in summary

    def test_report_record_actual(self):
        report = BudgetReport(total_estimated=5000, total_budget=10000)
        report.record_actual(prompt_tokens=4800, completion_tokens=350)
        assert report.actual_usage["prompt_tokens"] == 4800
        assert report.actual_usage["total_tokens"] == 5150

    def test_report_to_dict(self):
        budget = ContextBudget()
        report = budget.report({"system_prompt": "x", "user_request": "y"})
        d = report.to_dict()
        assert "budget_allocated" in d
        assert "budget_actual" in d
        assert "total_estimated" in d


# ── Retry Error Compression ──────────────────────────────

class TestCompressRetryErrors:
    """Sliding window error compression for retry loop."""

    def test_empty_attempts(self):
        assert compress_retry_errors([]) == ""

    def test_single_attempt(self):
        attempt = AttemptRecord(
            attempt=1,
            code="def foo(): pass",
            errors=["NameError: undefined 'bar'", "SyntaxError: unexpected indent"],
        )
        result = compress_retry_errors([attempt])
        assert "attempt 1" in result.lower()
        assert "NameError" in result
        assert "SyntaxError" in result
        assert "def foo(): pass" in result

    def test_two_attempts_compresses_first(self):
        a1 = AttemptRecord(
            attempt=1,
            code="def foo(): bar",
            errors=["SyntaxError: invalid syntax", "NameError: 'bar'"],
        )
        a2 = AttemptRecord(
            attempt=2,
            code="def foo(): return bar()",
            errors=["ImportError: no module 'bar'"],
        )
        result = compress_retry_errors([a1, a2])

        # Attempt 1 should be compressed to a summary
        assert "2 error(s)" in result or "SyntaxError" in result
        # Attempt 2 should have full errors
        assert "ImportError" in result
        # Should include closest-to-passing code
        assert "closest-to-passing" in result.lower()

    def test_three_attempts_top_three_errors(self):
        a1 = AttemptRecord(
            attempt=1,
            code="v1",
            errors=["Error1", "Error2", "Error3", "Error4"],
        )
        a2 = AttemptRecord(
            attempt=2,
            code="v2",
            errors=["Error5", "Error6"],
        )
        a3 = AttemptRecord(
            attempt=3,
            code="v3",
            errors=["ErrorA", "ErrorB", "ErrorC", "ErrorD", "ErrorE"],
        )
        result = compress_retry_errors([a1, a2, a3])

        # Only top 3 errors from latest attempt
        assert "ErrorA" in result
        assert "ErrorB" in result
        assert "ErrorC" in result
        # ErrorD and ErrorE should be excluded
        # (but we say "3 of 5" so it's fine if they appear in count)
        assert "5" in result  # "3 of 5"

    def test_never_exceeds_budget(self):
        # Create a huge attempt with many errors
        big_code = " ".join(["x = 1"] * 2000)
        big_errors = [f"Error line {i}: very long error message details" for i in range(100)]
        attempts = [
            AttemptRecord(attempt=1, code=big_code, errors=big_errors),
            AttemptRecord(attempt=2, code=big_code, errors=big_errors),
        ]
        result = compress_retry_errors(attempts, max_tokens=500)
        assert estimate_tokens(result) <= 600  # Some slack for truncation marker

    def test_attempt_record_auto_counts(self):
        record = AttemptRecord(attempt=1, code="def foo(): pass", errors=[])
        assert record.token_count > 0


# ── Complexity Scoring ────────────────────────────────────

class TestScoreComplexity:
    """Heuristic complexity scoring."""

    def test_simple_request(self):
        assert score_complexity("Add a helper function for date formatting") == "simple"

    def test_simple_short(self):
        assert score_complexity("Add a utility to parse JSON") == "simple"

    def test_medium_request(self):
        assert score_complexity("Add a delete endpoint that validates permissions") == "medium"

    def test_complex_request(self):
        assert score_complexity(
            "Refactor the authentication system to use OAuth2 and migrate "
            "the database schema to support multi-tenancy"
        ) == "complex"

    def test_long_request_is_complex(self):
        # 51+ words → complex
        long_request = " ".join(["implement"] * 55)
        assert score_complexity(long_request) == "complex"

    def test_returns_valid_values(self):
        for req in ["foo", "add a function", "refactor everything"]:
            result = score_complexity(req)
            assert result in ("simple", "medium", "complex")
