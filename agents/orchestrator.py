"""
Orchestrator - Chains agents together for end-to-end code generation.

This is the "conductor" that:
1. Takes a user request
2. Runs Historian → Architect → Implementer → Reviewer
3. Handles the rejection loop if code fails review
4. Returns the final generated code
"""

import asyncio
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from pathlib import Path

from .base import AgentContext, AgentResponse, AgentRole
from .historian import HistorianAgent
from .architect import ArchitectAgent


@dataclass
class OrchestrationResult:
    """Result of the full orchestration pipeline."""
    
    # Whether the pipeline succeeded
    success: bool
    
    # The generated code (if successful)
    generated_code: str = ""
    
    # Where the code should be placed
    target_file: str = ""
    
    # Combined context from all agents
    context: Dict[str, Any] = field(default_factory=dict)
    
    # Errors encountered
    errors: List[str] = field(default_factory=list)
    
    # Summary of what each agent did
    agent_summaries: Dict[str, str] = field(default_factory=dict)


class Orchestrator:
    """
    Orchestrates the agent pipeline.
    
    Pipeline:
    1. Historian: Gather patterns and conventions
    2. Architect: Map structure and find utilities
    3. Implementer: Generate code (with LLM or placeholder)
    4. Reviewer: Validate code (optional)
    """
    
    def __init__(self, llm_client=None, max_retries: int = 3):
        """
        Initialize the orchestrator.
        
        Args:
            llm_client: LLM client for Implementer/Reviewer
            max_retries: Max rejection loop iterations
        """
        self.llm_client = llm_client
        self.max_retries = max_retries
        
        # Initialize agents
        self.historian = HistorianAgent()
        self.architect = ArchitectAgent()
        # Implementer and Reviewer will be added later
    
    async def run(
        self, 
        user_request: str, 
        repo_path: str,
        language: str = "python"
    ) -> OrchestrationResult:
        """
        Run the full orchestration pipeline.
        
        Args:
            user_request: What the user wants to build
            repo_path: Path to the repository
            language: Programming language
            
        Returns:
            OrchestrationResult with generated code or errors
        """
        result = OrchestrationResult(success=False)
        
        # Build initial context
        context = AgentContext(
            user_request=user_request,
            repo_path=repo_path,
            language=language,
        )
        
        print(f"🚀 Starting orchestration for: {user_request[:50]}...")
        print(f"   Repo: {repo_path}")
        print(f"   Language: {language}")
        
        # Step 1: Run Historian
        print("\n📜 Running Historian Agent...")
        historian_response = await self.historian.process(context)
        
        if not historian_response.success:
            result.errors.append(f"Historian failed: {historian_response.summary}")
            return result
        
        result.agent_summaries["historian"] = historian_response.summary
        context.prior_context["historian"] = historian_response.data
        print(f"   ✓ {historian_response.summary}")
        
        # Step 2: Run Architect
        print("\n🏗️  Running Architect Agent...")
        architect_response = await self.architect.process(context)
        
        if not architect_response.success:
            result.errors.append(f"Architect failed: {architect_response.summary}")
            return result
        
        result.agent_summaries["architect"] = architect_response.summary
        context.prior_context["architect"] = architect_response.data
        result.target_file = architect_response.data.get("target_file", "")
        print(f"   ✓ {architect_response.summary}")
        
        # Step 3: Generate code (placeholder until Implementer is built)
        print("\n💻 Generating code...")
        
        if self.llm_client:
            # Use LLM to generate code
            code = await self._generate_with_llm(context)
        else:
            # Generate placeholder code
            code = self._generate_placeholder_code(
                context, 
                architect_response.data
            )
        
        result.generated_code = code
        result.context = {
            "historian": historian_response.data,
            "architect": architect_response.data,
        }
        result.success = True
        
        print(f"\n✅ Orchestration complete!")
        print(f"   Target file: {result.target_file}")
        print(f"   Generated {len(code)} characters of code")
        
        return result
    
    async def _generate_with_llm(self, context: AgentContext) -> str:
        """Generate code using the LLM client."""
        # Build the prompt from aggregated context
        prompt = self._build_implementation_prompt(context)
        
        # Call LLM (placeholder for now)
        # response = await self.llm_client.generate(prompt)
        # return response.text
        
        return "# LLM generation not yet implemented"
    
    def _generate_placeholder_code(
        self, 
        context: AgentContext,
        architect_data: Dict[str, Any]
    ) -> str:
        """Generate placeholder code when no LLM is available."""
        
        target_file = architect_data.get("target_file", "feature.py")
        imports_needed = architect_data.get("imports_needed", [])
        utilities = architect_data.get("existing_utilities", [])
        
        historian_data = context.prior_context.get("historian", {})
        patterns = historian_data.get("patterns", [])
        conventions = historian_data.get("conventions", {})
        
        language = context.language
        
        if language == "python":
            return self._generate_python_placeholder(
                context.user_request, imports_needed, utilities, patterns, conventions
            )
        elif language == "go":
            return self._generate_go_placeholder(
                context.user_request, imports_needed, utilities, patterns, conventions
            )
        elif language in ("typescript", "javascript"):
            return self._generate_ts_placeholder(
                context.user_request, imports_needed, utilities, patterns, conventions
            )
        
        return f"# Placeholder for: {context.user_request}"
    
    def _generate_python_placeholder(
        self,
        request: str,
        imports: List[str],
        utilities: List[Dict],
        patterns: List[Dict],
        conventions: Dict[str, str]
    ) -> str:
        """Generate Python placeholder code."""
        lines = [
            '"""',
            f'Generated code for: {request}',
            '',
            'Detected conventions:',
        ]
        
        for key, value in conventions.items():
            lines.append(f'- {key}: {value}')
        
        lines.append('"""')
        lines.append('')
        
        # Imports
        for imp in imports:
            lines.append(f'from {imp} import *  # TODO: specific imports')
        
        if imports:
            lines.append('')
        
        # Reference utilities
        if utilities:
            lines.append('# Existing utilities to reuse:')
            for util in utilities[:3]:
                lines.append(f'# - {util["name"]} from {util["file"]}')
            lines.append('')
        
        # Placeholder implementation
        feature_name = request.split()[1] if len(request.split()) > 1 else "feature"
        lines.extend([
            f'def {feature_name.lower()}():',
            f'    """Implement: {request}"""',
            '    # TODO: Implement based on detected patterns',
        ])
        
        if patterns:
            lines.append(f'    # Following pattern: {patterns[0].get("pattern_type", "unknown")}')
        
        lines.append('    pass')
        
        return '\n'.join(lines)
    
    def _generate_go_placeholder(
        self,
        request: str,
        imports: List[str],
        utilities: List[Dict],
        patterns: List[Dict],
        conventions: Dict[str, str]
    ) -> str:
        """Generate Go placeholder code."""
        lines = [
            f'// Generated code for: {request}',
            '//',
            '// Detected conventions:',
        ]
        
        for key, value in conventions.items():
            lines.append(f'// - {key}: {value}')
        
        lines.extend([
            '',
            'package main  // TODO: adjust package',
            '',
        ])
        
        # Imports
        if imports:
            lines.append('import (')
            for imp in imports:
                lines.append(f'\t"{imp}"')
            lines.append(')')
            lines.append('')
        
        # Placeholder function
        feature_name = request.split()[1].title() if len(request.split()) > 1 else "Feature"
        lines.extend([
            f'// {feature_name} implements: {request}',
            f'func {feature_name}() error {{',
            '\t// TODO: Implement based on detected patterns',
        ])
        
        if patterns:
            lines.append(f'\t// Following pattern: {patterns[0].get("pattern_type", "unknown")}')
        
        lines.extend([
            '\treturn nil',
            '}',
        ])
        
        return '\n'.join(lines)
    
    def _generate_ts_placeholder(
        self,
        request: str,
        imports: List[str],
        utilities: List[Dict],
        patterns: List[Dict],
        conventions: Dict[str, str]
    ) -> str:
        """Generate TypeScript placeholder code."""
        lines = [
            f'/**',
            f' * Generated code for: {request}',
            f' *',
            f' * Detected conventions:',
        ]
        
        for key, value in conventions.items():
            lines.append(f' * - {key}: {value}')
        
        lines.extend([
            ' */',
            '',
        ])
        
        # Imports
        for imp in imports:
            lines.append(f"import {{ /* TODO */ }} from '{imp}';")
        
        if imports:
            lines.append('')
        
        # Placeholder function
        feature_name = request.split()[1] if len(request.split()) > 1 else "feature"
        feature_name = feature_name[0].lower() + feature_name[1:] if feature_name else "feature"
        
        lines.extend([
            f'/**',
            f' * {request}',
            f' */',
            f'export async function {feature_name}(): Promise<void> {{',
            '  // TODO: Implement based on detected patterns',
        ])
        
        if patterns:
            lines.append(f'  // Following pattern: {patterns[0].get("pattern_type", "unknown")}')
        
        lines.extend([
            '}',
        ])
        
        return '\n'.join(lines)
    
    def _build_implementation_prompt(self, context: AgentContext) -> str:
        """Build an LLM prompt from aggregated context."""
        
        historian = context.prior_context.get("historian", {})
        architect = context.prior_context.get("architect", {})
        
        prompt = f"""You are implementing the following feature:

## User Request
{context.user_request}

## Repository
Path: {context.repo_path}
Language: {context.language}

## Detected Patterns
{historian.get("patterns", [])}

## Conventions to Follow
{historian.get("conventions", {})}

## Common Mistakes to Avoid
{historian.get("common_mistakes", [])}

## Target Location
File: {architect.get("target_file", "")}
Package: {architect.get("target_package", "")}

## Existing Utilities to Reuse
{architect.get("existing_utilities", [])}

## Required Imports
{architect.get("imports_needed", [])}

Generate production-ready code that:
1. Follows the detected conventions
2. Avoids the common mistakes
3. Reuses existing utilities where appropriate
4. Is placed in the suggested target location
"""
        return prompt


async def demo():
    """Demo the orchestrator on the current project."""
    orchestrator = Orchestrator()
    
    result = await orchestrator.run(
        user_request="Add authentication middleware",
        repo_path="E:/FUn/contextual-architect",
        language="python"
    )
    
    print("\n" + "="*60)
    print("RESULT:")
    print("="*60)
    print(f"Success: {result.success}")
    print(f"Target: {result.target_file}")
    print(f"\nGenerated Code:\n{result.generated_code}")


if __name__ == "__main__":
    asyncio.run(demo())
