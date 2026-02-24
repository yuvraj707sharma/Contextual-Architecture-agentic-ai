"""
Planner Agent — Pre-generation intelligence.

Phase 0 of the pipeline. Thinks before coding.

Creates a STRUCTURED PLAN that:
1. Defines what to build (acceptance criteria)
2. Identifies where to build it (target files)
3. Chooses how to build it (approach, patterns)
4. Lists what NOT to do (anti-patterns from PR history)
5. Includes pseudocode skeleton (from user or inferred)

The plan is written to workspace/plan.md and RE-READ by the
Implementer on every retry — this is the anti-hallucination anchor.
"""

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Dict, Any, Optional

from .base import BaseAgent, AgentContext, AgentResponse, AgentRole
from .logger import get_logger

logger = get_logger("planner")


@dataclass
class PlannerOutput:
    """Structured output from the Planner Agent.

    This becomes the plan.md that the Implementer reads on every attempt.
    """

    goal: str
    acceptance_criteria: List[str]
    target_files: List[Dict[str, str]]  # [{"path": "...", "action": "CREATE/MODIFY"}]
    approach: str
    do_not: List[str]  # anti-patterns / things to avoid
    pseudocode: str  # skeleton logic
    imports_needed: List[str]
    existing_utilities: List[str]  # existing functions to reuse
    complexity: str  # "simple", "medium", "complex"

    # Optional enrichment from PR search
    pr_warnings: List[str] = field(default_factory=list)

    def to_markdown(self) -> str:
        """Convert plan to markdown for plan.md."""
        lines = [
            f"# Plan: {self.goal}",
            f"\n**Complexity:** {self.complexity}",
            "",
            "## Acceptance Criteria",
        ]

        for i, criterion in enumerate(self.acceptance_criteria, 1):
            lines.append(f"{i}. {criterion}")

        lines.append("\n## Target Files")
        for target in self.target_files:
            action = target.get("action", "MODIFY")
            path = target.get("path", "unknown")
            reason = target.get("reason", "")
            reason_str = f" — {reason}" if reason else ""
            lines.append(f"- **[{action}]** `{path}`{reason_str}")

        lines.append(f"\n## Approach\n{self.approach}")

        if self.imports_needed:
            lines.append("\n## Imports Needed")
            for imp in self.imports_needed:
                lines.append(f"- `{imp}`")

        if self.existing_utilities:
            lines.append("\n## Existing Utilities to Reuse")
            for util in self.existing_utilities:
                lines.append(f"- `{util}`")

        if self.do_not:
            lines.append("\n## Do NOT")
            for anti in self.do_not:
                lines.append(f"- ❌ {anti}")

        if self.pr_warnings:
            lines.append("\n## PR History Warnings")
            for warning in self.pr_warnings:
                lines.append(f"- ⚠️ {warning}")

        if self.pseudocode:
            lines.append(f"\n## Pseudocode\n```\n{self.pseudocode}\n```")

        return "\n".join(lines)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "goal": self.goal,
            "acceptance_criteria": self.acceptance_criteria,
            "target_files": self.target_files,
            "approach": self.approach,
            "do_not": self.do_not,
            "pseudocode": self.pseudocode,
            "imports_needed": self.imports_needed,
            "existing_utilities": self.existing_utilities,
            "complexity": self.complexity,
            "pr_warnings": self.pr_warnings,
        }


class PlannerAgent(BaseAgent):
    """Pre-generation intelligence agent.

    Creates a structured plan before any code is written.
    Uses two modes:

    Mode 1: LLM-powered (when llm_client is provided)
      - Sends repo structure + PR context → LLM returns structured plan
      - Best quality, requires API credits

    Mode 2: Heuristic (when llm_client is None)
      - Infers plan from repo structure + keyword analysis
      - Good enough for simple requests, free

    The Planner gates on complexity:
      - Simple requests → InferredPlan (no Planner, orchestrator handles)
      - Medium/Complex → Full PlannerAgent run
    """

    def __init__(self, llm_client=None):
        super().__init__(llm_client)

    @property
    def role(self) -> AgentRole:
        return AgentRole.PLANNER

    @property
    def system_prompt(self) -> str:
        return PLANNER_SYSTEM_PROMPT

    async def process(self, context: AgentContext) -> AgentResponse:
        """Create a structured plan from user request + context.

        Args:
            context: AgentContext with:
              - user_request: what to build
              - repo_path: target repo
              - language: programming language
              - prior_context: may contain 'architect', 'historian',
                'pr_history', 'style_fingerprint'

        Returns:
            AgentResponse with data containing:
              - plan: PlannerOutput dict
              - plan_markdown: the plan as markdown string
              - complexity: scored complexity
        """
        logger.info(f"Planning: {context.user_request[:80]}")

        # Score complexity first
        complexity = self._score_complexity(context)
        logger.info(f"Complexity: {complexity}")

        if self.llm_client:
            plan = await self._plan_with_llm(context, complexity)
        else:
            plan = self._plan_heuristic(context, complexity)

        plan_md = plan.to_markdown()

        return self._create_response(
            success=True,
            data={
                "plan": plan.to_dict(),
                "plan_markdown": plan_md,
                "complexity": complexity,
            },
            summary=f"Plan created: {plan.goal} ({complexity} complexity, "
            f"{len(plan.acceptance_criteria)} criteria, "
            f"{len(plan.target_files)} target files)",
        )

    # ── Complexity Scoring ────────────────────────────────

    def _score_complexity(self, context: AgentContext) -> str:
        """Score request complexity for checkpoint decisions.

        Simple: new file, single function, no existing file modifications
        Medium: modifying existing file, 2-3 functions
        Complex: multi-file, touches core logic, architectural change

        Returns:
            "simple", "medium", or "complex"
        """
        request = context.user_request.lower()
        score = 0

        # Multi-file indicators
        multi_file_signals = [
            "refactor", "restructure", "migration", "across",
            "multiple", "all files", "everywhere", "each",
        ]
        if any(s in request for s in multi_file_signals):
            score += 3

        # Modification indicators
        modify_signals = [
            "modify", "change", "update", "fix", "replace",
            "refactor", "rename", "move",
        ]
        if any(s in request for s in modify_signals):
            score += 2

        # Architectural signals
        arch_signals = [
            "middleware", "database", "schema", "migration",
            "authentication", "authorization", "api", "endpoint",
            "service", "microservice", "queue", "cache",
        ]
        if any(s in request for s in arch_signals):
            score += 2

        # Simple signals (reduce score)
        simple_signals = [
            "add a function", "add function", "add a helper",
            "add helper", "simple", "basic", "utility",
            "create a file", "new file",
        ]
        if any(s in request for s in simple_signals):
            score -= 2

        # Check if architect found multi-file impact
        architect_data = context.prior_context.get("architect", {})
        related_files = architect_data.get("related_files", [])
        if len(related_files) > 3:
            score += 2

        if score <= 1:
            return "simple"
        elif score <= 4:
            return "medium"
        else:
            return "complex"

    # ── Heuristic Planning (No LLM) ──────────────────────

    def _plan_heuristic(
        self,
        context: AgentContext,
        complexity: str,
    ) -> PlannerOutput:
        """Create a plan using heuristic analysis (no LLM needed).

        Analyses the request text, repo structure, and prior context
        to build a reasonable plan.
        """
        request = context.user_request
        repo_path = context.repo_path
        language = context.language

        # Extract intent from request
        goal = request.strip()
        action, entity = self._parse_request_intent(request)

        # Determine target files from Architect context
        architect_data = context.prior_context.get("architect", {})
        target_file = architect_data.get("target_file", "")
        related_files = architect_data.get("related_files", [])
        utilities = architect_data.get("utilities", [])

        # Build target files list
        target_files = []
        if target_file:
            action_type = "MODIFY" if self._file_exists(
                repo_path, target_file
            ) else "CREATE"
            target_files.append({
                "path": target_file,
                "action": action_type,
                "reason": f"Primary target for {action} {entity}",
            })

        # Generate acceptance criteria from request
        criteria = self._generate_criteria(request, action, entity, language)

        # Build approach from style fingerprint and historian
        approach = self._generate_approach(context, action, entity)

        # Anti-patterns from PR history
        do_not = self._generate_do_not(context)

        # PR-based warnings
        pr_warnings = self._extract_pr_warnings(context)

        # Pseudocode
        pseudocode = self._generate_pseudocode(
            action, entity, language, utilities
        )

        # Imports
        imports = self._infer_imports(context, action, entity, language)

        # Existing utilities to reuse
        existing_utils = []
        if isinstance(utilities, list):
            for util in utilities[:5]:
                if isinstance(util, dict):
                    name = util.get("name", util.get("function", ""))
                    if name:
                        existing_utils.append(name)
                elif isinstance(util, str):
                    existing_utils.append(util)

        return PlannerOutput(
            goal=goal,
            acceptance_criteria=criteria,
            target_files=target_files,
            approach=approach,
            do_not=do_not,
            pseudocode=pseudocode,
            imports_needed=imports,
            existing_utilities=existing_utils,
            complexity=complexity,
            pr_warnings=pr_warnings,
        )

    def _parse_request_intent(self, request: str) -> tuple:
        """Parse user request into (action, entity).

        Examples:
          "Add JWT authentication" → ("add", "JWT authentication")
          "Fix the login bug"      → ("fix", "login bug")
          "Create user model"      → ("create", "user model")
        """
        request_lower = request.lower().strip()

        action_patterns = [
            (r"^(add|create|implement|build|make|write)\s+(.+)", "add"),
            (r"^(fix|repair|debug|resolve|patch)\s+(.+)", "fix"),
            (r"^(update|modify|change|edit|refactor)\s+(.+)", "modify"),
            (r"^(delete|remove|drop|clean)\s+(.+)", "delete"),
            (r"^(test|verify|check|validate)\s+(.+)", "test"),
        ]

        for pattern, action in action_patterns:
            match = re.match(pattern, request_lower)
            if match:
                entity = match.group(2).strip()
                # Clean up common filler words
                entity = re.sub(
                    r"^(a|an|the|some|new)\s+", "", entity
                )
                return action, entity

        # Default: treat whole request as entity, action is "add"
        return "add", request_lower

    def _file_exists(self, repo_path: str, file_path: str) -> bool:
        """Check if a file exists in the repo."""
        full = Path(repo_path) / file_path
        return full.exists()

    def _generate_criteria(
        self,
        request: str,
        action: str,
        entity: str,
        language: str,
    ) -> List[str]:
        """Generate acceptance criteria from the request."""
        criteria = []

        if action == "add":
            criteria.append(f"Implement {entity} functionality")
            criteria.append(
                "Follow existing code patterns and naming conventions"
            )
            criteria.append("Include proper error handling")
            if language == "go":
                criteria.append("Return errors explicitly (no panics)")
            elif language == "python":
                criteria.append("Use appropriate exception handling")

        elif action == "fix":
            criteria.append(f"Resolve the {entity} issue")
            criteria.append("Verify fix does not break existing functionality")
            criteria.append("Add appropriate error handling if missing")

        elif action == "modify":
            criteria.append(f"Update {entity} as requested")
            criteria.append("Preserve existing behavior where not modified")
            criteria.append("Maintain backward compatibility")

        elif action == "delete":
            criteria.append(f"Remove {entity} cleanly")
            criteria.append(
                "Verify no other code depends on removed functionality"
            )

        elif action == "test":
            criteria.append(f"Write tests for {entity}")
            criteria.append("Cover happy path and edge cases")
            criteria.append("Use project's existing test framework")

        # Universal criteria
        criteria.append("No security vulnerabilities introduced")

        return criteria

    def _generate_approach(
        self,
        context: AgentContext,
        action: str,
        entity: str,
    ) -> str:
        """Generate approach text based on context."""
        parts = []

        # Style fingerprint guidance
        style = context.prior_context.get("style_fingerprint")
        if style:
            if hasattr(style, "to_dict"):
                style_dict = style.to_dict()
            elif isinstance(style, dict):
                style_dict = style
            else:
                style_dict = {}

            naming = style_dict.get("function_naming", "")
            if naming:
                parts.append(f"Use {naming} naming convention")

            logger_lib = style_dict.get("logger_library", "")
            if logger_lib and logger_lib != "unknown":
                parts.append(f"Use {logger_lib} for logging")

        # Historian guidance
        historian_data = context.prior_context.get("historian", {})
        conventions = historian_data.get("conventions", {})
        if isinstance(conventions, dict):
            for key, value in list(conventions.items())[:3]:
                parts.append(f"{key}: {value}")

        if not parts:
            parts.append(
                f"Follow existing patterns in the codebase for {action}ing {entity}"
            )

        return "\n".join(f"- {p}" for p in parts)

    def _generate_do_not(self, context: AgentContext) -> List[str]:
        """Generate anti-patterns list."""
        do_not = [
            "Don't refactor existing code unless explicitly asked",
            "Don't add features not in the request",
            "Don't change function signatures of existing functions",
        ]

        # Add PR-sourced anti-patterns
        pr_context = context.prior_context.get("pr_history", "")
        if isinstance(pr_context, str) and "don't" in pr_context.lower():
            # Extract "don't" lines from PR feedback
            for line in pr_context.split("\n"):
                if "don't" in line.lower() or "avoid" in line.lower():
                    cleaned = line.strip().lstrip("- •*")
                    if cleaned and len(cleaned) > 10:
                        do_not.append(cleaned)

        return do_not

    def _extract_pr_warnings(self, context: AgentContext) -> List[str]:
        """Extract warnings from PR search results."""
        warnings = []
        pr_context = context.prior_context.get("pr_history", "")

        if isinstance(pr_context, str) and pr_context:
            # Look for feedback lines
            for line in pr_context.split("\n"):
                line = line.strip()
                if line.startswith("- ") and len(line) > 20:
                    warnings.append(line[2:])  # strip "- "

        return warnings[:5]  # max 5 warnings

    def _generate_pseudocode(
        self,
        action: str,
        entity: str,
        language: str,
        utilities: Any,
    ) -> str:
        """Generate basic pseudocode skeleton."""
        # For most requests, leave pseudocode empty so the LLM
        # can fill it in. Only generate for well-understood patterns.
        entity_lower = entity.lower()

        if "middleware" in entity_lower:
            if language == "go":
                return (
                    "func NewMiddleware() gin.HandlerFunc {\n"
                    "    return func(c *gin.Context) {\n"
                    "        // validate request\n"
                    "        // if invalid: c.AbortWithStatus(401)\n"
                    "        // if valid: c.Next()\n"
                    "    }\n"
                    "}"
                )
            elif language == "python":
                return (
                    "def middleware(request, call_next):\n"
                    "    # validate request\n"
                    "    # if invalid: return error response\n"
                    "    response = call_next(request)\n"
                    "    return response"
                )

        if "endpoint" in entity_lower or "route" in entity_lower:
            if language == "python":
                return (
                    "@app.route('/path', methods=['GET'])\n"
                    "def handler():\n"
                    "    # validate input\n"
                    "    # process\n"
                    "    # return response"
                )

        # Default: empty (let LLM figure it out)
        return ""

    def _infer_imports(
        self,
        context: AgentContext,
        action: str,
        entity: str,
        language: str,
    ) -> List[str]:
        """Infer likely imports needed."""
        imports = []
        entity_lower = entity.lower()

        if language == "python":
            if any(k in entity_lower for k in ["json", "api", "endpoint"]):
                imports.append("json")
            if "datetime" in entity_lower or "time" in entity_lower:
                imports.append("datetime")
            if "path" in entity_lower or "file" in entity_lower:
                imports.append("pathlib.Path")
            if "log" in entity_lower:
                imports.append("logging")

        elif language == "go":
            if "http" in entity_lower or "api" in entity_lower:
                imports.append("net/http")
            if "json" in entity_lower:
                imports.append("encoding/json")
            if "log" in entity_lower:
                imports.append("log")
            if "context" in entity_lower:
                imports.append("context")

        return imports

    # ── LLM-Powered Planning ─────────────────────────────

    async def _plan_with_llm(
        self,
        context: AgentContext,
        complexity: str,
    ) -> PlannerOutput:
        """Create a plan using LLM for higher quality output.

        Sends the repo structure, PR context, and user request to the LLM
        and parses the structured response into a PlannerOutput.
        """
        # Build the user prompt with all context
        prompt_parts = [
            f"## User Request\n{context.user_request}",
            f"\n## Language\n{context.language}",
            f"\n## Complexity\n{complexity}",
        ]

        # Add architect context (structure info)
        architect_data = context.prior_context.get("architect", {})
        if architect_data:
            target = architect_data.get("target_file", "")
            related = architect_data.get("related_files", [])
            utils = architect_data.get("utilities", [])

            prompt_parts.append("\n## Repository Context")
            if target:
                prompt_parts.append(f"Suggested target file: {target}")
            if related:
                related_str = ", ".join(
                    r if isinstance(r, str) else r.get("path", "")
                    for r in related[:5]
                )
                prompt_parts.append(f"Related files: {related_str}")
            if utils:
                utils_str = ", ".join(
                    u if isinstance(u, str) else u.get("name", "")
                    for u in utils[:5]
                )
                prompt_parts.append(f"Existing utilities: {utils_str}")

        # Add historian conventions
        historian_data = context.prior_context.get("historian", {})
        conventions = historian_data.get("conventions", {})
        if conventions:
            prompt_parts.append("\n## Project Conventions")
            for key, val in list(conventions.items())[:5]:
                prompt_parts.append(f"- {key}: {val}")

        # Add style fingerprint
        style = context.prior_context.get("style_fingerprint")
        if style:
            style_dict = (
                style.to_dict()
                if hasattr(style, "to_dict")
                else style if isinstance(style, dict)
                else {}
            )
            if style_dict:
                prompt_parts.append("\n## Code Style")
                for key in [
                    "function_naming", "string_style",
                    "logger_library", "indent_style",
                ]:
                    val = style_dict.get(key, "")
                    if val:
                        prompt_parts.append(f"- {key}: {val}")

        # Add PR context
        pr_context = context.prior_context.get("pr_history", "")
        if pr_context:
            prompt_parts.append(f"\n{pr_context}")

        user_prompt = "\n".join(prompt_parts)

        # Call LLM
        try:
            response = await self.llm_client.generate(
                system_prompt=self.system_prompt,
                user_prompt=user_prompt,
                temperature=0.1,
                max_tokens=2048,
            )

            plan = self._parse_llm_plan(
                response.content, context, complexity
            )
            return plan

        except Exception as e:
            logger.warning(f"LLM planning failed: {e}, falling back to heuristic")
            return self._plan_heuristic(context, complexity)

    def _parse_llm_plan(
        self,
        llm_output: str,
        context: AgentContext,
        complexity: str,
    ) -> PlannerOutput:
        """Parse LLM response into structured PlannerOutput.

        The LLM is prompted to output a specific format.
        This parser extracts the sections.
        """
        sections = self._extract_sections(llm_output)

        # Goal
        goal = sections.get("goal", context.user_request)

        # Acceptance criteria
        criteria = self._extract_list(
            sections.get("acceptance_criteria", "")
        )
        if not criteria:
            criteria = [context.user_request]

        # Target files
        target_files = []
        targets_text = sections.get("target", sections.get("target_files", ""))
        for line in targets_text.split("\n"):
            line = line.strip().lstrip("- •*")
            if not line:
                continue
            # Parse "[CREATE] path — reason" or "[MODIFY] path — reason"
            match = re.match(
                r"\[?(CREATE|MODIFY|DELETE)\]?\s*[:`]?([^\s—`]+)[`]?\s*(?:—\s*(.+))?",
                line, re.IGNORECASE,
            )
            if match:
                target_files.append({
                    "path": match.group(2).strip("`"),
                    "action": match.group(1).upper(),
                    "reason": (match.group(3) or "").strip(),
                })
            elif line and "/" in line:
                target_files.append({
                    "path": line.strip("`"),
                    "action": "MODIFY",
                    "reason": "",
                })

        # If no targets parsed, fall back to architect suggestion
        if not target_files:
            architect_data = context.prior_context.get("architect", {})
            target = architect_data.get("target_file", "")
            if target:
                target_files.append({
                    "path": target,
                    "action": "MODIFY" if self._file_exists(
                        context.repo_path, target
                    ) else "CREATE",
                    "reason": "Suggested by Architect",
                })

        # Approach
        approach = sections.get("approach", "Follow existing patterns")

        # Do NOT
        do_not = self._extract_list(sections.get("do_not", sections.get("do not", "")))
        if not do_not:
            do_not = ["Don't refactor existing code unless asked"]

        # Pseudocode
        pseudocode = sections.get("pseudocode", "")
        # Strip markdown code fences if present
        pseudocode = re.sub(r"^```\w*\n?", "", pseudocode)
        pseudocode = re.sub(r"\n?```$", "", pseudocode)

        # Imports
        imports = self._extract_list(
            sections.get("imports", sections.get("imports_needed", ""))
        )

        # Existing utilities
        utilities = self._extract_list(
            sections.get("utilities", sections.get("existing_utilities", ""))
        )

        return PlannerOutput(
            goal=goal,
            acceptance_criteria=criteria,
            target_files=target_files,
            approach=approach,
            do_not=do_not,
            pseudocode=pseudocode.strip(),
            imports_needed=imports,
            existing_utilities=utilities,
            complexity=complexity,
        )

    def _extract_sections(self, text: str) -> Dict[str, str]:
        """Extract markdown sections from LLM output.

        Parses "## Section Name" headers and collects content.
        """
        sections: Dict[str, str] = {}
        current_key = ""
        current_lines: List[str] = []

        for line in text.split("\n"):
            header_match = re.match(r"^#{1,3}\s+(.+)", line)
            if header_match:
                if current_key:
                    sections[current_key] = "\n".join(current_lines).strip()
                current_key = header_match.group(1).strip().lower()
                # Normalize common variations
                current_key = current_key.replace(" ", "_")
                current_lines = []
            else:
                current_lines.append(line)

        if current_key:
            sections[current_key] = "\n".join(current_lines).strip()

        return sections

    def _extract_list(self, text: str) -> List[str]:
        """Extract a markdown list into plain strings."""
        items = []
        for line in text.split("\n"):
            line = line.strip()
            # Match "- item", "* item", "1. item", "1) item"
            match = re.match(r"^[-*•]\s+(.+)|^\d+[.)]\s+(.+)", line)
            if match:
                item = (match.group(1) or match.group(2)).strip()
                if item:
                    items.append(item)
            elif line and not line.startswith("#"):
                # Non-list, non-header line with content
                if len(line) > 5:
                    items.append(line)
        return items


# ── System Prompt ─────────────────────────────────────────

PLANNER_SYSTEM_PROMPT = """You are the Planner Agent in a multi-agent code generation system.

Your job is to create a STRUCTURED PLAN before any code is generated.
The plan ensures the Implementer Agent writes code that is:
- Architecturally compliant (follows project patterns)
- Minimal (only implements what's asked)
- Correct (clear acceptance criteria)

## Output Format

You MUST respond with exactly these sections:

## Goal
One-line description of what we're building.

## Acceptance Criteria
1. First criterion
2. Second criterion
3. ...

## Target
- [CREATE] path/to/new_file.py — reason
- [MODIFY] path/to/existing.py — reason

## Approach
How to implement this, referencing existing patterns.

## Imports Needed
- module_name

## Existing Utilities
- function_name from file (what it does)

## Do NOT
- Don't do X because Y

## Pseudocode
```
skeleton of the solution logic
```

## Rules
1. NEVER suggest refactoring unrelated code
2. ALWAYS reference existing project patterns when available
3. Keep acceptance criteria TESTABLE (not vague)
4. Pseudocode should match the project's coding style
5. If conventions data is provided, follow them exactly
6. If PR history warnings exist, DO NOT repeat those mistakes
"""
