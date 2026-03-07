"""
Tests for the Reviewer Agent.
"""

import pytest

from ..reviewer import (
    CheckType,
    ReviewerAgent,
    Severity,
    ValidationIssue,
    ValidationResult,
    validate_code,
)


class TestValidationIssue:
    """Tests for ValidationIssue dataclass."""

    def test_to_dict(self):
        issue = ValidationIssue(
            check_type=CheckType.SYNTAX,
            severity=Severity.ERROR,
            message="Missing semicolon",
            file_path="main.go",
            line_number=42,
        )
        d = issue.to_dict()
        assert d["check_type"] == "syntax"
        assert d["severity"] == "error"
        assert d["line_number"] == 42

    def test_to_string(self):
        issue = ValidationIssue(
            check_type=CheckType.SECURITY,
            severity=Severity.WARNING,
            message="Hardcoded password",
            file_path="config.py",
            line_number=10,
        )
        s = issue.to_string()
        assert "config.py:10" in s
        assert "Hardcoded password" in s


class TestValidationResult:
    """Tests for ValidationResult dataclass."""

    def test_errors_property(self):
        result = ValidationResult(
            passed=False,
            issues=[
                ValidationIssue(CheckType.SYNTAX, Severity.ERROR, "err", "f.py"),
                ValidationIssue(CheckType.LINT, Severity.WARNING, "warn", "f.py"),
                ValidationIssue(CheckType.LINT, Severity.INFO, "info", "f.py"),
            ],
        )
        assert len(result.errors) == 1
        assert len(result.warnings) == 1

    def test_to_prompt_feedback_passed(self):
        result = ValidationResult(passed=True)
        feedback = result.to_prompt_feedback()
        assert "passed" in feedback.lower()

    def test_to_prompt_feedback_failed(self):
        result = ValidationResult(
            passed=False,
            issues=[
                ValidationIssue(
                    CheckType.SYNTAX, Severity.ERROR, "SyntaxError", "f.py",
                    suggestion="Fix it"
                ),
            ],
        )
        feedback = result.to_prompt_feedback()
        assert "SyntaxError" in feedback
        assert "Fix it" in feedback


class TestReviewerAgent:
    """Tests for ReviewerAgent."""

    def test_role(self):
        agent = ReviewerAgent()
        assert agent.role.value == "reviewer"

    @pytest.mark.asyncio
    async def test_valid_python_code(self):
        agent = ReviewerAgent(use_external_tools=False)
        code = 'def hello():\n    return "world"\n'
        result = await agent.validate(code, "hello.py", "python")

        assert result.passed is True
        assert "syntax" in result.checks_run

    @pytest.mark.asyncio
    async def test_syntax_error_detected(self):
        agent = ReviewerAgent(use_external_tools=False)
        code = "def broken(\n"
        result = await agent.validate(code, "broken.py", "python")

        assert result.passed is False
        assert any(i.check_type == CheckType.SYNTAX for i in result.issues)

    @pytest.mark.asyncio
    async def test_security_eval_detected(self):
        agent = ReviewerAgent(use_external_tools=False)
        code = 'result = eval(user_input)\n'
        result = await agent.validate(code, "danger.py", "python")

        security_issues = [
            i for i in result.issues if i.check_type == CheckType.SECURITY
        ]
        assert len(security_issues) > 0
        assert any("eval" in i.message.lower() for i in security_issues)

    @pytest.mark.asyncio
    async def test_security_hardcoded_password(self):
        agent = ReviewerAgent(use_external_tools=False)
        code = 'password = "super_secret_123"\n'
        result = await agent.validate(code, "auth.py", "python")

        security_issues = [
            i for i in result.issues if i.check_type == CheckType.SECURITY
        ]
        assert len(security_issues) > 0

    @pytest.mark.asyncio
    async def test_lint_bare_except(self):
        agent = ReviewerAgent(use_external_tools=False)
        code = 'try:\n    x = 1\nexcept:\n    pass\n'
        result = await agent.validate(code, "bad.py", "python")

        lint_issues = [
            i for i in result.issues if i.check_type == CheckType.LINT
        ]
        assert any("except" in i.message.lower() for i in lint_issues)

    @pytest.mark.asyncio
    async def test_lint_mutable_default(self):
        agent = ReviewerAgent(use_external_tools=False)
        code = 'def foo(items=[]):\n    items.append(1)\n'
        result = await agent.validate(code, "mut.py", "python")

        lint_issues = [
            i for i in result.issues if i.check_type == CheckType.LINT
        ]
        assert any("mutable" in i.message.lower() for i in lint_issues)

    @pytest.mark.asyncio
    async def test_go_missing_package(self):
        agent = ReviewerAgent(use_external_tools=False)
        code = 'func main() {\n    fmt.Println("hello")\n}\n'
        result = await agent.validate(code, "main.go", "go")

        assert result.passed is False
        assert any("package" in i.message.lower() for i in result.issues)

    @pytest.mark.asyncio
    async def test_validate_batch(self):
        agent = ReviewerAgent(use_external_tools=False)
        files = {
            "good.py": 'def ok():\n    return True\n',
            "bad.py": "def broken(\n",
        }
        result = await agent.validate_batch(files, "python")

        assert result.passed is False
        assert len(result.issues) > 0

    @pytest.mark.asyncio
    async def test_external_tools_skip_when_disabled(self):
        agent = ReviewerAgent(use_external_tools=False)
        code = 'x = 1\n'
        result = await agent.validate(code, "x.py", "python")

        assert "external_tools" not in result.checks_run


class TestConvenienceFunction:
    """Tests for the module-level validate_code function."""

    @pytest.mark.asyncio
    async def test_validate_code_works(self):
        result = await validate_code(
            code='print("hello")\n',
            file_path="hello.py",
            language="python",
        )
        assert isinstance(result, ValidationResult)
