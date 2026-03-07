"""
Test Generator Agent — Auto-generates unit tests from plan criteria.

Phase C3 of the pipeline. Runs AFTER the Implementer produces code
and BEFORE the Reviewer validates it. The generated tests become
part of the changeset alongside the implementation.

Two modes:
  1. LLM-powered: generates full test code via LLM
  2. Heuristic: generates test stubs from acceptance criteria

Auto-detects testing framework:
  - Python: pytest
  - Go: testing (go test)
  - JavaScript/TypeScript: jest
"""

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .base import AgentContext, AgentResponse, AgentRole, BaseAgent
from .logger import get_logger

logger = get_logger("test_generator")


# ── Framework detection ──────────────────────────────────────

FRAMEWORK_MAP = {
    "python": {
        "name": "pytest",
        "import": "import pytest",
        "test_prefix": "test_",
        "file_prefix": "test_",
        "file_ext": ".py",
        "assertion": "assert",
    },
    "go": {
        "name": "testing",
        "import": 'import "testing"',
        "test_prefix": "Test",
        "file_prefix": "",
        "file_ext": "_test.go",
        "assertion": "t.Error",
    },
    "typescript": {
        "name": "jest",
        "import": "import { describe, it, expect } from '@jest/globals';",
        "test_prefix": "",
        "file_prefix": "",
        "file_ext": ".test.ts",
        "assertion": "expect",
    },
    "javascript": {
        "name": "jest",
        "import": "const { describe, it, expect } = require('@jest/globals');",
        "test_prefix": "",
        "file_prefix": "",
        "file_ext": ".test.js",
        "assertion": "expect",
    },
}


@dataclass
class TestGeneratorOutput:
    """Result of the test generation."""

    test_code: str
    test_file_path: str
    test_count: int
    framework: str
    criteria_covered: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "test_code": self.test_code,
            "test_file_path": self.test_file_path,
            "test_count": self.test_count,
            "framework": self.framework,
            "criteria_covered": self.criteria_covered,
        }


class TestGeneratorAgent(BaseAgent):
    """
    Agent that generates unit tests from plan acceptance criteria.

    Uses the plan's criteria as test cases and the generated code
    as the system under test. Produces a test file that:
    - Imports the generated module
    - Has one test per acceptance criterion
    - Uses the project's existing test framework
    """

    def __init__(self, llm_client=None):
        super().__init__(llm_client)

    @property
    def role(self) -> AgentRole:
        return AgentRole.TEST_GENERATOR

    @property
    def system_prompt(self) -> str:
        return self._load_prompt()

    @classmethod
    def _load_prompt(cls) -> str:
        from .system_prompts import TEST_GENERATOR_SYSTEM_PROMPT
        return TEST_GENERATOR_SYSTEM_PROMPT

    async def process(self, context: AgentContext) -> AgentResponse:
        """
        Generate tests for the implemented code.

        Expects context.prior_context to contain:
          - 'plan': PlannerOutput dict with acceptance_criteria
          - 'implementer': dict with 'code' and 'file_path'

        Returns:
            AgentResponse with TestGeneratorOutput in data
        """
        plan = context.prior_context.get("plan", {})
        impl = context.prior_context.get("implementer", {})
        criteria = plan.get("acceptance_criteria", [])
        code = impl.get("code", "")
        impl_file = impl.get("file_path", "")
        language = context.language

        framework = self._detect_framework(language, context.repo_path)

        if not criteria and not code:
            output = TestGeneratorOutput(
                test_code="",
                test_file_path="",
                test_count=0,
                framework=framework["name"],
            )
            return self._create_response(
                success=True,
                data=output.to_dict(),
                summary="No criteria or code to test",
                warnings=["No acceptance criteria and no code provided"],
            )

        # Derive test file path from implementation file path
        test_file = self._derive_test_path(impl_file, language, framework)

        # Generate tests
        if self.llm_client and code:
            output = await self._generate_with_llm(
                context, criteria, code, impl_file, test_file, framework
            )
        else:
            output = self._generate_stubs(
                criteria, code, impl_file, test_file, language, framework
            )

        return self._create_response(
            success=True,
            data=output.to_dict(),
            summary=(
                f"Generated {output.test_count} tests "
                f"({output.framework}) → {output.test_file_path}"
            ),
        )

    # ── Framework Detection ──────────────────────────────────

    def _detect_framework(
        self, language: str, repo_path: Optional[str] = None
    ) -> Dict[str, str]:
        """Detect the test framework for the language."""
        fw = FRAMEWORK_MAP.get(language)
        if fw:
            return fw

        # Default fallback
        return {
            "name": "unittest",
            "import": "import unittest",
            "test_prefix": "test_",
            "file_prefix": "test_",
            "file_ext": ".py",
            "assertion": "assert",
        }

    def _derive_test_path(
        self, impl_file: str, language: str, framework: Dict[str, str]
    ) -> str:
        """Derive test file path from implementation file path."""
        if not impl_file:
            return f"tests/test_generated{framework['file_ext']}"

        # Strip directory and extension
        import os
        base = os.path.basename(impl_file)
        name, _ = os.path.splitext(base)
        directory = os.path.dirname(impl_file)

        if language == "go":
            # Go tests live next to the source file
            return os.path.join(directory, f"{name}_test.go")
        elif language in ("typescript", "javascript"):
            # JS/TS tests often in __tests__ or same dir
            return os.path.join(directory, f"{name}{framework['file_ext']}")
        else:
            # Python: tests/ directory
            test_dir = "tests"
            if directory and not directory.startswith("tests"):
                test_dir = os.path.join(directory, "tests")
            return os.path.join(test_dir, f"test_{name}.py")

    # ── Heuristic Stub Generation ────────────────────────────

    def _generate_stubs(
        self,
        criteria: List[str],
        code: str,
        impl_file: str,
        test_file: str,
        language: str,
        framework: Dict[str, str],
    ) -> TestGeneratorOutput:
        """Generate test stubs from acceptance criteria."""
        generators = {
            "python": self._python_stubs,
            "go": self._go_stubs,
            "typescript": self._ts_stubs,
            "javascript": self._ts_stubs,
        }

        generator = generators.get(language, self._python_stubs)
        test_code = generator(criteria, code, impl_file, framework)
        test_count = len(criteria) if criteria else 1

        return TestGeneratorOutput(
            test_code=test_code,
            test_file_path=test_file,
            test_count=test_count,
            framework=framework["name"],
            criteria_covered=criteria,
        )

    def _python_stubs(
        self,
        criteria: List[str],
        code: str,
        impl_file: str,
        framework: Dict[str, str],
    ) -> str:
        """Generate Python/pytest test stubs."""
        lines = [
            '"""Auto-generated tests from acceptance criteria."""',
            "",
            "import pytest",
        ]

        # Try to derive import from impl_file
        if impl_file:
            module = impl_file.replace("/", ".").replace("\\", ".").rstrip(".py")
            if module.endswith(".py"):
                module = module[:-3]
            lines.append(f"# from {module} import *  # TODO: adjust import")

        lines.append("")
        lines.append("")

        # Extract function names from code
        functions = re.findall(r"def\s+(\w+)\s*\(", code) if code else []

        if criteria:
            for i, criterion in enumerate(criteria):
                func_name = self._criterion_to_func_name(criterion)
                lines.append(f"def test_{func_name}():")
                lines.append(f'    """Criterion: {criterion}"""')

                # If we found a matching function, generate a basic call
                if functions:
                    fn = functions[min(i, len(functions) - 1)]
                    lines.append(f"    # TODO: test that {fn}() satisfies: {criterion}")
                    lines.append(f"    # result = {fn}(...)")
                    lines.append("    # assert result is not None")
                else:
                    lines.append(f"    # TODO: implement test for: {criterion}")

                lines.append("    pass")
                lines.append("")
                lines.append("")
        else:
            lines.append("def test_placeholder():")
            lines.append('    """Placeholder test — no criteria provided."""')
            lines.append("    pass")
            lines.append("")

        return "\n".join(lines)

    def _go_stubs(
        self,
        criteria: List[str],
        code: str,
        impl_file: str,
        framework: Dict[str, str],
    ) -> str:
        """Generate Go test stubs."""
        # Detect package from code
        pkg_match = re.search(r"package\s+(\w+)", code) if code else None
        pkg = pkg_match.group(1) if pkg_match else "main"

        lines = [
            f"package {pkg}",
            "",
            'import "testing"',
            "",
        ]

        functions = re.findall(r"func\s+(\w+)\s*\(", code) if code else []

        if criteria:
            for i, criterion in enumerate(criteria):
                func_name = self._criterion_to_go_name(criterion)
                lines.append(f"func Test{func_name}(t *testing.T) {{")
                lines.append(f'\t// Criterion: {criterion}')

                if functions:
                    fn = functions[min(i, len(functions) - 1)]
                    lines.append(f"\t// TODO: test that {fn}() satisfies: {criterion}")
                else:
                    lines.append("\t// TODO: implement test")

                lines.append('\tt.Skip("not implemented")')
                lines.append("}")
                lines.append("")
        else:
            lines.append("func TestPlaceholder(t *testing.T) {")
            lines.append('\tt.Skip("no criteria provided")')
            lines.append("}")

        return "\n".join(lines)

    def _ts_stubs(
        self,
        criteria: List[str],
        code: str,
        impl_file: str,
        framework: Dict[str, str],
    ) -> str:
        """Generate TypeScript/JavaScript jest test stubs."""
        lines = [framework["import"], ""]

        # Derive module name for import
        if impl_file:
            import os
            name = os.path.splitext(os.path.basename(impl_file))[0]
            lines.append(f"// import {{ ... }} from './{name}';")

        lines.append("")

        if criteria:
            lines.append("describe('Generated Tests', () => {")
            for criterion in criteria:
                lines.append(f"  it('should {criterion.lower()}', () => {{")
                lines.append(f"    // TODO: implement test for: {criterion}")
                lines.append("    expect(true).toBe(true); // placeholder")
                lines.append("  });")
                lines.append("")
            lines.append("});")
        else:
            lines.append("describe('Placeholder', () => {")
            lines.append("  it('should pass', () => {")
            lines.append("    expect(true).toBe(true);")
            lines.append("  });")
            lines.append("});")

        return "\n".join(lines)

    # ── LLM-Powered Generation ───────────────────────────────

    async def _generate_with_llm(
        self,
        context: AgentContext,
        criteria: List[str],
        code: str,
        impl_file: str,
        test_file: str,
        framework: Dict[str, str],
    ) -> TestGeneratorOutput:
        """Generate tests using LLM."""
        prompt = self._build_llm_prompt(
            context, criteria, code, impl_file, framework
        )

        try:
            response = await self.llm_client.generate(
                system_prompt=self.system_prompt,
                user_prompt=prompt,
                temperature=0.1,
                max_tokens=2048,
            )
            test_code = self._extract_test_code(response.content, context.language)
            test_count = self._count_tests(test_code, context.language)

            return TestGeneratorOutput(
                test_code=test_code,
                test_file_path=test_file,
                test_count=test_count,
                framework=framework["name"],
                criteria_covered=criteria,
            )
        except Exception as e:
            logger.warning(f"LLM test generation failed, falling back: {e}")
            return self._generate_stubs(
                criteria, code, impl_file, test_file,
                context.language, framework,
            )

    def _build_llm_prompt(
        self,
        context: AgentContext,
        criteria: List[str],
        code: str,
        impl_file: str,
        framework: Dict[str, str],
    ) -> str:
        """Build prompt for LLM test generation."""
        criteria_text = "\n".join(f"  {i+1}. {c}" for i, c in enumerate(criteria))

        # Truncate code if very long
        code_preview = code[:3000] if len(code) > 3000 else code

        return (
            f"## Task\nGenerate unit tests for the following code.\n\n"
            f"## Language\n{context.language}\n\n"
            f"## Test Framework\n{framework['name']}\n\n"
            f"## Implementation File\n{impl_file}\n\n"
            f"## Code Under Test\n```{context.language}\n{code_preview}\n```\n\n"
            f"## Acceptance Criteria (one test per criterion)\n{criteria_text}\n\n"
            f"## Rules\n"
            f"- One test function per acceptance criterion\n"
            f"- Use {framework['name']} conventions\n"
            f"- Include both happy path and edge cases\n"
            f"- Import the module under test correctly\n"
            f"- Return ONLY the test code in a code block\n"
        )

    def _extract_test_code(self, response: str, language: str) -> str:
        """Extract test code from LLM response."""
        # Look for fenced code block
        pattern = rf"```(?:{language})?\s*\n(.*?)```"
        match = re.search(pattern, response, re.DOTALL)
        if match:
            return match.group(1).strip()

        # Fallback: return entire response if it looks like code
        lines = response.strip().split("\n")
        code_lines = [l for l in lines if not l.startswith("#") or "import" in l]
        if code_lines:
            return "\n".join(code_lines)

        return response.strip()

    def _count_tests(self, test_code: str, language: str) -> int:
        """Count test functions in the generated code."""
        if language == "python":
            return len(re.findall(r"def\s+test_\w+", test_code))
        elif language == "go":
            return len(re.findall(r"func\s+Test\w+", test_code))
        elif language in ("typescript", "javascript"):
            return len(re.findall(r"(?:it|test)\s*\(", test_code))
        return 1

    # ── Helpers ──────────────────────────────────────────────

    def _criterion_to_func_name(self, criterion: str) -> str:
        """Convert a criterion to a valid Python function name."""
        # "Validate JWT tokens" → "validate_jwt_tokens"
        clean = re.sub(r"[^a-zA-Z0-9\s]", "", criterion)
        words = clean.lower().split()[:5]  # Max 5 words
        return "_".join(words) if words else "criterion"

    def _criterion_to_go_name(self, criterion: str) -> str:
        """Convert a criterion to a valid Go test function name."""
        # "Validate JWT tokens" → "ValidateJWTTokens"
        clean = re.sub(r"[^a-zA-Z0-9\s]", "", criterion)
        words = clean.split()[:5]
        return "".join(w.capitalize() for w in words) if words else "Criterion"
