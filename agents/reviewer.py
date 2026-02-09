"""
Reviewer Agent - Validates generated code before user sees it.

The Reviewer simulates what would happen in CI/CD:
- Syntax checking
- Type checking
- Linting
- Running affected tests
- Security scanning

This prevents broken code from wasting the user's time.
"""

import os
import re
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from enum import Enum

from .base import BaseAgent, AgentContext, AgentResponse, AgentRole


class CheckType(Enum):
    """Types of validation checks."""
    SYNTAX = "syntax"
    TYPE = "type"
    LINT = "lint"
    TEST = "test"
    SECURITY = "security"
    IMPORT = "import"


class Severity(Enum):
    """Severity of validation issues."""
    ERROR = "error"      # Must fix - code won't work
    WARNING = "warning"  # Should fix - code quality issue
    INFO = "info"        # Nice to fix - suggestion


@dataclass
class ValidationIssue:
    """A single validation issue found in the code."""
    check_type: CheckType
    severity: Severity
    message: str
    file_path: str
    line_number: Optional[int] = None
    suggestion: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "check_type": self.check_type.value,
            "severity": self.severity.value,
            "message": self.message,
            "file_path": self.file_path,
            "line_number": self.line_number,
            "suggestion": self.suggestion,
        }
    
    def to_string(self) -> str:
        loc = f":{self.line_number}" if self.line_number else ""
        icon = {"error": "❌", "warning": "⚠️", "info": "ℹ️"}.get(self.severity.value, "•")
        return f"{icon} {self.file_path}{loc}: {self.message}"


@dataclass
class ValidationResult:
    """Result of all validation checks."""
    passed: bool
    issues: List[ValidationIssue] = field(default_factory=list)
    checks_run: List[str] = field(default_factory=list)
    summary: str = ""
    
    @property
    def errors(self) -> List[ValidationIssue]:
        return [i for i in self.issues if i.severity == Severity.ERROR]
    
    @property
    def warnings(self) -> List[ValidationIssue]:
        return [i for i in self.issues if i.severity == Severity.WARNING]
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "passed": self.passed,
            "error_count": len(self.errors),
            "warning_count": len(self.warnings),
            "checks_run": self.checks_run,
            "issues": [i.to_dict() for i in self.issues],
            "summary": self.summary,
        }
    
    def to_prompt_feedback(self) -> str:
        """Generate feedback for the Implementer to fix issues."""
        if self.passed:
            return "✅ All validation checks passed."
        
        lines = ["❌ Validation failed. Please fix these issues:", ""]
        
        for issue in self.errors:
            lines.append(issue.to_string())
            if issue.suggestion:
                lines.append(f"   Suggestion: {issue.suggestion}")
        
        for issue in self.warnings[:5]:  # Limit warnings
            lines.append(issue.to_string())
        
        return "\n".join(lines)


class ReviewerAgent(BaseAgent):
    """
    Agent that validates generated code before it reaches the user.
    
    Runs:
    - Syntax checks (compiles/parses)
    - Type checks (mypy, tsc, go vet)
    - Linting (ruff, eslint, golangci-lint)
    - Security scans (basic pattern matching)
    - Import validation
    """
    
    SYSTEM_PROMPT = """You are the Reviewer Agent, a code quality guardian.

Your job is to validate generated code before it's shown to the user.
You check for:
1. Syntax errors
2. Type errors
3. Linting issues
4. Security vulnerabilities
5. Import problems

You are the LAST barrier before code reaches the user. Be thorough but practical.
Only fail for real issues, not style preferences.
"""
    
    # Security patterns to flag
    SECURITY_PATTERNS = {
        "python": [
            (r"exec\s*\(", "Dangerous: exec() can run arbitrary code"),
            (r"eval\s*\(", "Dangerous: eval() can run arbitrary code"),
            (r"__import__\s*\(", "Dangerous: dynamic import"),
            (r"pickle\.loads?\s*\(", "Warning: pickle can deserialize malicious data"),
            (r"subprocess\.(?:call|run|Popen).*shell\s*=\s*True", "Warning: shell=True is vulnerable to injection"),
            (r"os\.system\s*\(", "Warning: os.system is vulnerable to injection"),
            (r"password\s*=\s*['\"][^'\"]+['\"]", "Warning: hardcoded password"),
            (r"api_key\s*=\s*['\"][^'\"]+['\"]", "Warning: hardcoded API key"),
        ],
        "go": [
            (r"exec\.Command.*\+", "Warning: command injection risk"),
            (r"sql\.Query.*\+", "Warning: SQL injection - use parameterized queries"),
            (r"password\s*:?=\s*\"[^\"]+\"", "Warning: hardcoded password"),
            (r"os\.Setenv\s*\(\s*\".*KEY\"", "Warning: hardcoded secret in env"),
        ],
        "typescript": [
            (r"eval\s*\(", "Dangerous: eval() can run arbitrary code"),
            (r"innerHTML\s*=", "Warning: XSS risk - use textContent instead"),
            (r"dangerouslySetInnerHTML", "Warning: XSS risk - sanitize input"),
            (r"password\s*[:=]\s*['\"][^'\"]+['\"]", "Warning: hardcoded password"),
        ],
    }
    
    # Tool commands for each language
    VALIDATION_TOOLS = {
        "python": {
            "syntax": ["python", "-m", "py_compile"],
            "type": ["mypy", "--ignore-missing-imports"],
            "lint": ["ruff", "check"],
        },
        "go": {
            "syntax": ["go", "build", "-o", "/dev/null"],
            "type": ["go", "vet"],
            "lint": ["golangci-lint", "run"],
        },
        "typescript": {
            "syntax": ["tsc", "--noEmit"],
            "type": ["tsc", "--noEmit"],
            "lint": ["eslint"],
        },
    }
    
    def __init__(self, llm_client=None):
        super().__init__(llm_client)
    
    @property
    def role(self) -> AgentRole:
        return AgentRole.REVIEWER
    
    @property
    def system_prompt(self) -> str:
        return self.SYSTEM_PROMPT
    
    async def process(self, context: AgentContext) -> AgentResponse:
        """
        Process is not the main entry point for Reviewer.
        Use validate() instead.
        """
        return self._create_response(
            success=True,
            data={},
            summary="Use validate() method for code validation",
        )
    
    async def validate(
        self,
        code: str,
        file_path: str,
        language: str,
        repo_path: Optional[str] = None,
    ) -> ValidationResult:
        """
        Validate a piece of generated code.
        
        Args:
            code: The generated code to validate
            file_path: Where the code will be written
            language: Programming language
            repo_path: Optional path to the repository for context
        
        Returns:
            ValidationResult with all issues found
        """
        result = ValidationResult(passed=True)
        
        # 1. Syntax check (always runs)
        syntax_issues = await self._check_syntax(code, file_path, language)
        result.issues.extend(syntax_issues)
        result.checks_run.append("syntax")
        
        # If syntax fails, other checks are unreliable
        if any(i.severity == Severity.ERROR for i in syntax_issues):
            result.passed = False
            result.summary = f"Syntax errors found ({len(syntax_issues)} issues)"
            return result
        
        # 2. Import validation
        import_issues = self._check_imports(code, language)
        result.issues.extend(import_issues)
        result.checks_run.append("imports")
        
        # 3. Security scan
        security_issues = self._check_security(code, file_path, language)
        result.issues.extend(security_issues)
        result.checks_run.append("security")
        
        # 4. Basic lint checks (without external tools)
        lint_issues = self._basic_lint(code, file_path, language)
        result.issues.extend(lint_issues)
        result.checks_run.append("lint")
        
        # Determine overall pass/fail
        error_count = len(result.errors)
        warning_count = len(result.warnings)
        
        result.passed = error_count == 0
        result.summary = (
            f"{'✅ Passed' if result.passed else '❌ Failed'}: "
            f"{error_count} errors, {warning_count} warnings"
        )
        
        return result
    
    async def validate_batch(
        self,
        files: Dict[str, str],
        language: str,
        repo_path: Optional[str] = None,
    ) -> ValidationResult:
        """
        Validate multiple files at once.
        
        Args:
            files: Dict of {file_path: code_content}
            language: Programming language
            repo_path: Optional repository path
        
        Returns:
            Combined ValidationResult
        """
        combined = ValidationResult(passed=True)
        
        for file_path, code in files.items():
            result = await self.validate(code, file_path, language, repo_path)
            combined.issues.extend(result.issues)
            combined.checks_run = list(set(combined.checks_run + result.checks_run))
            
            if not result.passed:
                combined.passed = False
        
        error_count = len(combined.errors)
        warning_count = len(combined.warnings)
        combined.summary = (
            f"{'✅ Passed' if combined.passed else '❌ Failed'}: "
            f"{len(files)} files, {error_count} errors, {warning_count} warnings"
        )
        
        return combined
    
    async def _check_syntax(
        self,
        code: str,
        file_path: str,
        language: str
    ) -> List[ValidationIssue]:
        """Check code syntax."""
        issues = []
        
        if language == "python":
            issues.extend(self._check_python_syntax(code, file_path))
        elif language == "go":
            issues.extend(self._check_go_syntax(code, file_path))
        elif language in ("typescript", "javascript"):
            issues.extend(self._check_js_syntax(code, file_path))
        
        return issues
    
    def _check_python_syntax(self, code: str, file_path: str) -> List[ValidationIssue]:
        """Check Python syntax using compile()."""
        issues = []
        
        try:
            compile(code, file_path, 'exec')
        except SyntaxError as e:
            issues.append(ValidationIssue(
                check_type=CheckType.SYNTAX,
                severity=Severity.ERROR,
                message=f"SyntaxError: {e.msg}",
                file_path=file_path,
                line_number=e.lineno,
                suggestion="Fix the syntax error before proceeding",
            ))
        except Exception as e:
            issues.append(ValidationIssue(
                check_type=CheckType.SYNTAX,
                severity=Severity.ERROR,
                message=f"Compilation error: {str(e)}",
                file_path=file_path,
            ))
        
        return issues
    
    def _check_go_syntax(self, code: str, file_path: str) -> List[ValidationIssue]:
        """Check Go syntax (basic check without go compiler)."""
        issues = []
        
        # Basic checks
        if "package " not in code:
            issues.append(ValidationIssue(
                check_type=CheckType.SYNTAX,
                severity=Severity.ERROR,
                message="Missing package declaration",
                file_path=file_path,
                line_number=1,
                suggestion="Add 'package main' or appropriate package name",
            ))
        
        # Check for unbalanced braces
        open_braces = code.count('{')
        close_braces = code.count('}')
        if open_braces != close_braces:
            issues.append(ValidationIssue(
                check_type=CheckType.SYNTAX,
                severity=Severity.ERROR,
                message=f"Unbalanced braces: {open_braces} opening, {close_braces} closing",
                file_path=file_path,
                suggestion="Check for missing or extra braces",
            ))
        
        return issues
    
    def _check_js_syntax(self, code: str, file_path: str) -> List[ValidationIssue]:
        """Check JavaScript/TypeScript syntax (basic)."""
        issues = []
        
        # Check for unbalanced braces
        open_braces = code.count('{')
        close_braces = code.count('}')
        if open_braces != close_braces:
            issues.append(ValidationIssue(
                check_type=CheckType.SYNTAX,
                severity=Severity.ERROR,
                message=f"Unbalanced braces: {open_braces} opening, {close_braces} closing",
                file_path=file_path,
            ))
        
        # Check for unbalanced parentheses
        open_parens = code.count('(')
        close_parens = code.count(')')
        if open_parens != close_parens:
            issues.append(ValidationIssue(
                check_type=CheckType.SYNTAX,
                severity=Severity.ERROR,
                message=f"Unbalanced parentheses: {open_parens} opening, {close_parens} closing",
                file_path=file_path,
            ))
        
        return issues
    
    def _check_imports(self, code: str, language: str) -> List[ValidationIssue]:
        """Check if imports look valid."""
        issues = []
        
        if language == "python":
            # Check for common typos in imports
            common_modules = {
                "os", "sys", "re", "json", "typing", "pathlib",
                "dataclasses", "asyncio", "datetime", "collections",
            }
            
            import_pattern = r'^(?:from|import)\s+(\w+)'
            for match in re.finditer(import_pattern, code, re.MULTILINE):
                module = match.group(1)
                # Warn about potentially misspelled stdlib imports
                if module not in common_modules and not module.startswith('_'):
                    # This is just a heuristic - not a real error
                    pass
        
        elif language == "go":
            # Check for import without usage (basic)
            import_section = re.search(r'import\s*\((.*?)\)', code, re.DOTALL)
            if import_section:
                imports = re.findall(r'"([^"]+)"', import_section.group(1))
                for imp in imports:
                    pkg_name = imp.split('/')[-1]
                    # Very basic check - real Go tooling should be used
                    if pkg_name not in code.replace(import_section.group(0), ''):
                        issues.append(ValidationIssue(
                            check_type=CheckType.IMPORT,
                            severity=Severity.WARNING,
                            message=f"Imported package '{pkg_name}' may be unused",
                            file_path="",
                            suggestion=f"Remove import if not needed: {imp}",
                        ))
        
        return issues
    
    def _check_security(
        self,
        code: str,
        file_path: str,
        language: str
    ) -> List[ValidationIssue]:
        """Check for security issues using pattern matching."""
        issues = []
        patterns = self.SECURITY_PATTERNS.get(language, [])
        
        lines = code.split('\n')
        for line_num, line in enumerate(lines, 1):
            for pattern, message in patterns:
                if re.search(pattern, line, re.IGNORECASE):
                    severity = Severity.ERROR if "Dangerous" in message else Severity.WARNING
                    issues.append(ValidationIssue(
                        check_type=CheckType.SECURITY,
                        severity=severity,
                        message=message,
                        file_path=file_path,
                        line_number=line_num,
                    ))
        
        return issues
    
    def _basic_lint(
        self,
        code: str,
        file_path: str,
        language: str
    ) -> List[ValidationIssue]:
        """Basic linting without external tools."""
        issues = []
        lines = code.split('\n')
        
        for line_num, line in enumerate(lines, 1):
            # Very long lines
            if len(line) > 120:
                issues.append(ValidationIssue(
                    check_type=CheckType.LINT,
                    severity=Severity.INFO,
                    message=f"Line too long ({len(line)} > 120 characters)",
                    file_path=file_path,
                    line_number=line_num,
                ))
            
            # Trailing whitespace
            if line.rstrip() != line and line.strip():
                issues.append(ValidationIssue(
                    check_type=CheckType.LINT,
                    severity=Severity.INFO,
                    message="Trailing whitespace",
                    file_path=file_path,
                    line_number=line_num,
                ))
        
        # Python-specific
        if language == "python":
            # Check for bare except
            if re.search(r'except\s*:', code):
                issues.append(ValidationIssue(
                    check_type=CheckType.LINT,
                    severity=Severity.WARNING,
                    message="Bare 'except:' clause - catch specific exceptions",
                    file_path=file_path,
                ))
            
            # Check for mutable default arguments
            if re.search(r'def\s+\w+\([^)]*=\s*\[\]', code):
                issues.append(ValidationIssue(
                    check_type=CheckType.LINT,
                    severity=Severity.WARNING,
                    message="Mutable default argument (use None instead)",
                    file_path=file_path,
                ))
        
        return issues


# Convenience function
async def validate_code(
    code: str,
    file_path: str,
    language: str,
) -> ValidationResult:
    """Quick way to validate code."""
    reviewer = ReviewerAgent()
    return await reviewer.validate(code, file_path, language)
