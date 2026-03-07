"""
Implementer Agent - Generates code using LLM with full context.

The Implementer is the "hands" of the system:
1. Takes context from Historian + Architect
2. Builds a comprehensive prompt
3. Calls LLM to generate code
4. Returns code that matches project style
"""

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .base import AgentContext, AgentResponse, AgentRole, BaseAgent
from .llm_client import BaseLLMClient
from .style_fingerprint import StyleFingerprint


@dataclass
class ImplementerOutput:
    """Structured output from the Implementer Agent."""

    # Generated code
    code: str

    # Target file path
    file_path: str

    # Language used
    language: str

    # Explanation of what was generated
    explanation: str = ""

    # Dependencies that need to be added
    new_dependencies: List[str] = field(default_factory=list)

    # Files that may need to be modified
    related_modifications: List[Dict[str, str]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "code": self.code,
            "file_path": self.file_path,
            "language": self.language,
            "explanation": self.explanation,
            "new_dependencies": self.new_dependencies,
            "related_modifications": self.related_modifications,
        }


class ImplementerAgent(BaseAgent):
    """
    Agent that generates code using LLM with full project context.

    The Implementer:
    1. Receives context from Historian (patterns, conventions)
    2. Receives context from Architect (structure, utilities)
    3. Receives style fingerprint (exact coding style)
    4. Builds a comprehensive prompt
    5. Calls LLM and extracts code
    """

    SYSTEM_PROMPT = None  # Loaded from system_prompts module

    @classmethod
    def _load_prompt(cls) -> str:
        from .system_prompts import IMPLEMENTER_SYSTEM_PROMPT
        return IMPLEMENTER_SYSTEM_PROMPT

    def __init__(self, llm_client: Optional[BaseLLMClient] = None):
        super().__init__(llm_client)

    @property
    def role(self) -> AgentRole:
        return AgentRole.IMPLEMENTER

    @property
    def system_prompt(self) -> str:
        return self._load_prompt()

    async def process(self, context: AgentContext) -> AgentResponse:
        """
        Generate code based on aggregated context.

        Expects context.prior_context to contain:
        - 'historian': Output from Historian agent
        - 'architect': Output from Architect agent
        - 'style_fingerprint': StyleFingerprint (optional)
        - 'validation_errors': Errors from previous attempt (if retrying)
        """
        if not self.llm_client:
            # Fallback to placeholder generation
            output = self._generate_placeholder(context)
        else:
            # Real LLM generation
            output = await self._generate_with_llm(context)

        return self._create_response(
            success=True,
            data=output.to_dict(),
            summary=f"Generated {len(output.code)} chars for {output.file_path}",
            next_agent=AgentRole.REVIEWER,
        )

    async def _generate_with_llm(self, context: AgentContext) -> ImplementerOutput:
        """Generate code using the LLM."""
        # Build the comprehensive prompt
        prompt = self._build_prompt(context)

        # Call LLM
        response = await self.llm_client.generate(
            system_prompt=self.system_prompt,
            user_prompt=prompt,
            temperature=0.1,  # Low temp for deterministic code
            max_tokens=4096,
        )

        # Extract code from response
        code, file_path = self._extract_code(response.content, context.language)

        # If architect suggested a target file, use it
        architect_data = context.prior_context.get("architect", {})
        if not file_path and architect_data.get("target_file"):
            file_path = architect_data["target_file"]

        return ImplementerOutput(
            code=code,
            file_path=file_path or self._default_file_path(context.language),
            language=context.language,
            explanation=self._extract_explanation(response.content),
        )

    def _build_prompt(self, context: AgentContext) -> str:
        """Build a comprehensive prompt from all available context."""
        sections = []

        # User request
        sections.append("## User Request")
        sections.append(context.user_request)
        sections.append("")

        # Repository info
        sections.append("## Repository")
        sections.append(f"Path: {context.repo_path}")
        sections.append(f"Language: {context.language}")
        sections.append("")

        # Project environment snapshot (FULL detail — file tree, deps, frameworks)
        project_context = context.prior_context.get("project_context_detailed", "")
        if not project_context:
            project_context = context.prior_context.get("project_context", "")
        if project_context:
            sections.append(project_context)
            sections.append("")

        # Historian context
        historian = context.prior_context.get("historian", {})
        if historian:
            conventions = historian.get("conventions", {})
            patterns = historian.get("patterns", [])
            mistakes = historian.get("common_mistakes", [])

            # ── CRITICAL: Style conventions MUST be followed ──────────
            # This section is intentionally aggressive because LLMs tend
            # to ignore mild suggestions and revert to "textbook" style.
            if conventions or patterns:
                sections.append("## ⚠️ CRITICAL: Project Style Rules (MANDATORY)")
                sections.append("You MUST follow these rules exactly. DO NOT use your default style.")
                sections.append("The code MUST look like it was written by the same developer.")
                sections.append("")

            if patterns:
                sections.append("### Detected Code Patterns")
                for p in patterns[:3]:
                    sections.append(f"**{p.get('pattern_type', 'Pattern')}**: {p.get('description', '')}")
                    if p.get('example_code'):
                        sections.append(f"```\n{p['example_code']}\n```")

            if conventions:
                sections.append("\n### Style Conventions (DO NOT DEVIATE)")
                for key, value in conventions.items():
                    sections.append(f"- **{key}**: {value}")

                # Add explicit anti-pattern warnings for C/C++
                conv_str = str(conventions).lower()
                if "using namespace std" in conv_str or "cout" in conv_str:
                    sections.append("")
                    sections.append("**⛔ DO NOT use `std::cout`, `std::cin`, `std::endl`.**")
                    sections.append("**✅ DO use `cout`, `cin`, `endl` (with `using namespace std;`).**")
                if "snake_case" in conv_str:
                    sections.append("**⛔ DO NOT use camelCase or PascalCase for variables/functions.**")
                if "camelCase" in conv_str or "PascalCase" in conv_str:
                    sections.append("**⛔ DO NOT use snake_case for variables/functions.**")

            if mistakes:
                sections.append("\n### ⚠️ Common Mistakes to Avoid")
                for m in mistakes:
                    sections.append(f"- {m}")

            sections.append("")


        # Architect context
        architect = context.prior_context.get("architect", {})
        if architect:
            sections.append("## Project Structure (from Architect)")

            if architect.get("target_file"):
                sections.append(f"**Target File**: `{architect['target_file']}`")
            if architect.get("target_package"):
                sections.append(f"**Target Package**: `{architect['target_package']}`")

            utilities = architect.get("existing_utilities", [])
            if utilities:
                sections.append("\n### Existing Utilities to Reuse")
                for u in utilities[:5]:
                    sections.append(f"- `{u.get('name')}` from `{u.get('file')}`: {u.get('description', '')}")

            imports = architect.get("imports_needed", [])
            if imports:
                sections.append(f"\n### Imports Needed: {', '.join(imports[:5])}")

            sections.append("")

        # Style fingerprint
        style = context.prior_context.get("style_fingerprint")
        if style and isinstance(style, StyleFingerprint):
            sections.append(style.to_prompt_context())
            sections.append("")
        elif style and isinstance(style, dict):
            sections.append("## Style Requirements")
            for key, value in style.items():
                sections.append(f"- **{key}**: {value}")
            sections.append("")

        # Validation errors (if retrying)
        errors = context.prior_context.get("validation_errors")
        if errors:
            sections.append("## ⚠️ Previous Attempt Failed - Fix These Issues")
            if isinstance(errors, list):
                for e in errors:
                    sections.append(f"- {e}")
            else:
                sections.append(str(errors))
            sections.append("")

        # Target files
        if context.target_files:
            sections.append("## Target Files")
            for f in context.target_files:
                sections.append(f"- `{f}`")
            sections.append("")

        # ── EXISTING FILE CONTENTS (critical for MODIFY) ──────────
        # When modifying existing files, show the Implementer the
        # actual code so it can BUILD UPON it, not replace it.
        existing_files = context.prior_context.get("existing_file_contents", {})
        if existing_files:
            sections.append("## 📄 EXISTING CODE (BUILD UPON THIS — DO NOT REPLACE)")
            sections.append("The following files already exist in the project.")
            sections.append("You MUST preserve and extend this code, NOT rewrite it from scratch.")
            sections.append("Wrap existing logic into functions if needed, then add new functions on top.")
            sections.append("")
            for file_path, content in existing_files.items():
                sections.append(f"### Current `{file_path}`:")
                sections.append(f"```\n{content}\n```")
                sections.append("")

        # User-provided pseudocode (highest priority constraint)
        user_pseudocode = context.prior_context.get("user_pseudocode", "")
        if user_pseudocode:
            sections.append("## ⚡ USER-PROVIDED PSEUDOCODE (MANDATORY)")
            sections.append("The user has provided pseudocode that defines the exact logic structure.")
            sections.append("Your generated code MUST follow this pseudocode step-by-step.")
            sections.append("Each step in the pseudocode should map to a clear block in your code.")
            sections.append("Do NOT skip steps. Do NOT reorder steps. Do NOT add logic not in the pseudocode.")
            sections.append(f"```\n{user_pseudocode}\n```")
            sections.append("")

        # ── CODE GRAPH INTELLIGENCE ──────────────────────────────
        # Deterministic AST facts about code relationships.
        # This tells the Implementer exactly which functions call the target,
        # which files import it, and what the impact chain looks like.
        graph_intel = context.prior_context.get("graph_intelligence", "")
        if graph_intel:
            sections.append("## 🔗 Code Relationships (AST-verified, not guesses)")
            sections.append("These are deterministic facts from parsing the codebase:")
            sections.append(graph_intel)
            sections.append("")

        # ── PLAN FROM PLANNER ────────────────────────────────────
        # The plan is the contract. The implementer MUST follow it.
        plan_md = context.prior_context.get("plan_markdown", "")
        if plan_md:
            sections.append("## 📋 IMPLEMENTATION PLAN (FOLLOW EXACTLY)")
            sections.append("You MUST follow this plan step-by-step. Do NOT freelance.")
            sections.append("Each acceptance criterion MUST be met in your code.")
            sections.append(plan_md)
            sections.append("")

        # ── DETECTED CONFLICTS ───────────────────────────────────
        conflicts = context.prior_context.get("detected_conflicts", "")
        if conflicts:
            sections.append("## ⚠️ DETECTED CONFLICTS (address these)")
            sections.append("The system detected these conflicts between your request and the project:")
            sections.append(conflicts)
            sections.append("")

        # Final instruction
        sections.append("## Generate Code")
        sections.append("Generate production-ready code that:")
        sections.append("1. Implements ONLY what was requested")
        sections.append("2. Matches the exact style of this codebase")
        sections.append("3. Reuses existing utilities — do NOT reinvent what already exists")
        sections.append("4. Avoids the common mistakes listed above")
        sections.append("5. Is ready to pass code review")
        sections.append("6. Follows the implementation plan step-by-step")
        if user_pseudocode:
            sections.append("7. Follows the user pseudocode step-by-step (non-negotiable)")

        return '\n'.join(sections)

    def _extract_code(self, response: str, language: str) -> tuple:
        """Extract code blocks from LLM response."""
        # Look for code blocks with language specifier
        pattern = rf'```{language}\s*(.*?)```'
        matches = re.findall(pattern, response, re.DOTALL)

        if matches:
            code = matches[0].strip()
            # Check if there's a file path specified
            file_pattern = r'---\s*FILE:\s*([^\s]+)\s*---'
            file_match = re.search(file_pattern, response)
            file_path = file_match.group(1) if file_match else None
            return code, file_path

        # Try generic code block
        pattern = r'```\w*\s*(.*?)```'
        matches = re.findall(pattern, response, re.DOTALL)
        if matches:
            return matches[0].strip(), None

        # Last resort: return full response
        return response.strip(), None

    def _extract_explanation(self, response: str) -> str:
        """Extract any explanation text from LLM response."""
        # Look for text before the first code block
        parts = response.split('```')
        if len(parts) > 1:
            explanation = parts[0].strip()
            if len(explanation) > 20:
                return explanation
        return ""

    def _default_file_path(self, language: str) -> str:
        """Return default file path for language."""
        ext_map = {
            "python": "generated.py",
            "go": "generated.go",
            "typescript": "generated.ts",
            "javascript": "generated.js",
        }
        return ext_map.get(language, "generated.txt")

    def _generate_placeholder(self, context: AgentContext) -> ImplementerOutput:
        """Generate placeholder code when no LLM is available."""
        language = context.language
        request = context.user_request

        historian = context.prior_context.get("historian", {})
        architect = context.prior_context.get("architect", {})

        conventions = historian.get("conventions", {})
        utilities = architect.get("existing_utilities", [])
        target_file = architect.get("target_file", self._default_file_path(language))

        if language == "python":
            code = self._python_placeholder(request, conventions, utilities)
        elif language == "go":
            code = self._go_placeholder(request, conventions, utilities)
        elif language in ("typescript", "javascript"):
            code = self._ts_placeholder(request, conventions, utilities)
        else:
            code = f"# Placeholder for: {request}"

        return ImplementerOutput(
            code=code,
            file_path=target_file,
            language=language,
            explanation="Generated placeholder code (no LLM connected)",
        )

    def _python_placeholder(
        self,
        request: str,
        conventions: Dict[str, str],
        utilities: List[Dict]
    ) -> str:
        lines = [
            '"""',
            f'Generated for: {request}',
            '',
            'TODO: Connect LLM for real implementation',
            '"""',
            '',
        ]

        if utilities:
            lines.append('# Suggested imports (from Architect):')
            for u in utilities[:3]:
                lines.append(f'# from {u.get("file", "module")} import {u.get("name", "func")}')
            lines.append('')

        # Extract a name from the request
        words = request.lower().split()
        func_name = '_'.join(w for w in words[:3] if len(w) > 2)

        lines.extend([
            f'def {func_name}():',
            '    """',
            f'    {request}',
            '    ',
            '    Following conventions:',
        ])

        for key, value in list(conventions.items())[:3]:
            lines.append(f'    - {key}: {value}')

        lines.extend([
            '    """',
            '    # TODO: Implement',
            '    pass',
        ])

        return '\n'.join(lines)

    def _go_placeholder(
        self,
        request: str,
        conventions: Dict[str, str],
        utilities: List[Dict]
    ) -> str:
        lines = [
            '// Generated for: ' + request,
            '// TODO: Connect LLM for real implementation',
            '',
            'package main',
            '',
        ]

        # Extract a name from the request
        words = request.title().split()
        func_name = ''.join(w for w in words[:3] if len(w) > 2)

        lines.extend([
            f'// {func_name} implements: {request}',
            f'func {func_name}() error {{',
        ])

        if conventions:
            lines.append('\t// Following conventions:')
            for key, value in list(conventions.items())[:3]:
                lines.append(f'\t// - {key}: {value}')

        lines.extend([
            '\t// TODO: Implement',
            '\treturn nil',
            '}',
        ])

        return '\n'.join(lines)

    def _ts_placeholder(
        self,
        request: str,
        conventions: Dict[str, str],
        utilities: List[Dict]
    ) -> str:
        lines = [
            '/**',
            f' * Generated for: {request}',
            ' * TODO: Connect LLM for real implementation',
            ' */',
            '',
        ]

        # Extract a name from the request
        words = request.split()
        func_name = words[0].lower() + ''.join(w.title() for w in words[1:3] if len(w) > 2)

        lines.extend([
            '/**',
            f' * {request}',
            ' */',
            f'export async function {func_name}(): Promise<void> {{',
        ])

        if conventions:
            lines.append('  // Following conventions:')
            for key, value in list(conventions.items())[:3]:
                lines.append(f'  // - {key}: {value}')

        lines.extend([
            '  // TODO: Implement',
            '}',
        ])

        return '\n'.join(lines)
