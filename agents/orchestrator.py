"""
Orchestrator - Chains agents together for end-to-end code generation.

This is the "conductor" that:
1. Takes a user request
2. Runs Historian → Architect → Implementer → Reviewer
3. Handles the rejection loop if code fails review
4. Uses SafeCodeWriter for permission-based file writing
5. Returns the final generated code
"""

import asyncio
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from pathlib import Path

from .base import AgentContext, AgentResponse, AgentRole
from .historian import HistorianAgent
from .architect import ArchitectAgent
from .implementer import ImplementerAgent
from .reviewer import ReviewerAgent, ValidationResult
from .safe_writer import SafeCodeWriter, ChangeSet
from .style_fingerprint import StyleAnalyzer
from .llm_client import BaseLLMClient


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
    
    # Validation result
    validation: Optional[ValidationResult] = None
    
    # ChangeSet for safe writing
    changeset: Optional[ChangeSet] = None
    
    # Errors encountered
    errors: List[str] = field(default_factory=list)
    
    # Summary of what each agent did
    agent_summaries: Dict[str, str] = field(default_factory=dict)
    
    # Number of generation attempts
    attempts: int = 1


class Orchestrator:
    """
    Orchestrates the agent pipeline.
    
    Pipeline:
    1. Historian: Gather patterns and conventions
    2. Style Analyzer: Extract exact coding style
    3. Architect: Map structure and find utilities
    4. Implementer: Generate code with LLM
    5. Reviewer: Validate code (syntax, security, lint)
    6. SafeWriter: Plan safe file modifications
    
    If Reviewer fails, feed errors back to Implementer and retry.
    """
    
    def __init__(
        self, 
        llm_client: Optional[BaseLLMClient] = None, 
        max_retries: int = 3,
        auto_approve_new_files: bool = True,
    ):
        """
        Initialize the orchestrator.
        
        Args:
            llm_client: LLM client for Implementer
            max_retries: Max rejection loop iterations
            auto_approve_new_files: Auto-approve creation of new files
        """
        self.llm_client = llm_client
        self.max_retries = max_retries
        self.auto_approve_new_files = auto_approve_new_files
        
        # Initialize agents
        self.historian = HistorianAgent()
        self.architect = ArchitectAgent()
        self.implementer = ImplementerAgent(llm_client)
        self.reviewer = ReviewerAgent()
    
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
            OrchestrationResult with generated code and changeset
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
        
        # Step 1: Analyze project style
        print("\n🎨 Analyzing project style...")
        style_analyzer = StyleAnalyzer(repo_path, language)
        style_fingerprint = style_analyzer.analyze()
        context.prior_context["style_fingerprint"] = style_fingerprint
        print(f"   ✓ Style: {style_fingerprint.function_naming} functions, "
              f"{style_fingerprint.logger_library} logging")
        
        # Step 2: Run Historian
        print("\n📜 Running Historian Agent...")
        historian_response = await self.historian.process(context)
        
        if not historian_response.success:
            result.errors.append(f"Historian failed: {historian_response.summary}")
            return result
        
        result.agent_summaries["historian"] = historian_response.summary
        context.prior_context["historian"] = historian_response.data
        print(f"   ✓ {historian_response.summary}")
        
        # Step 3: Run Architect
        print("\n🏗️  Running Architect Agent...")
        architect_response = await self.architect.process(context)
        
        if not architect_response.success:
            result.errors.append(f"Architect failed: {architect_response.summary}")
            return result
        
        result.agent_summaries["architect"] = architect_response.summary
        context.prior_context["architect"] = architect_response.data
        result.target_file = architect_response.data.get("target_file", "")
        print(f"   ✓ {architect_response.summary}")
        
        # Step 4: Generate and validate code (with retry loop)
        print("\n💻 Generating code with Implementer...")
        
        for attempt in range(1, self.max_retries + 1):
            result.attempts = attempt
            
            # Generate code
            impl_response = await self.implementer.process(context)
            
            if not impl_response.success:
                result.errors.append(f"Implementer failed: {impl_response.summary}")
                continue
            
            generated_code = impl_response.data.get("code", "")
            target_file = impl_response.data.get("file_path", result.target_file)
            
            print(f"   ✓ Generated {len(generated_code)} chars (attempt {attempt})")
            
            # Validate with Reviewer
            print("\n🔍 Validating with Reviewer...")
            validation = await self.reviewer.validate(
                code=generated_code,
                file_path=target_file,
                language=language,
                repo_path=repo_path,
            )
            
            result.validation = validation
            result.agent_summaries["reviewer"] = validation.summary
            
            if validation.passed:
                print(f"   ✓ {validation.summary}")
                result.generated_code = generated_code
                result.target_file = target_file
                break
            else:
                print(f"   ⚠️ {validation.summary}")
                # Feed errors back for next attempt
                context.prior_context["validation_errors"] = validation.to_prompt_feedback()
                
                if attempt < self.max_retries:
                    print(f"   🔄 Retrying ({attempt}/{self.max_retries})...")
        
        # Step 5: Plan safe changes
        if result.generated_code:
            print("\n📦 Planning safe file changes...")
            safe_writer = SafeCodeWriter(repo_path)
            changeset = safe_writer.plan_changes(
                generated_files={result.target_file: result.generated_code},
                language=language,
            )
            result.changeset = changeset
            result.context = {
                "historian": context.prior_context.get("historian", {}),
                "architect": context.prior_context.get("architect", {}),
                "style": style_fingerprint.to_dict(),
            }
            result.success = True
            
            print(f"   ✓ {len(changeset.changes)} changes planned")
            print(f"   ✓ {len(changeset.untouched_files)} files preserved")
        
        print(f"\n{'✅' if result.success else '❌'} Orchestration complete!")
        if result.target_file:
            print(f"   Target file: {result.target_file}")
        
        return result
    
    async def apply_changes(
        self, 
        changeset: ChangeSet,
        repo_path: str
    ) -> Dict[str, Any]:
        """
        Apply approved changes to the filesystem.
        
        Args:
            changeset: ChangeSet with approved changes
            repo_path: Path to the repository
            
        Returns:
            Report of applied/skipped changes
        """
        safe_writer = SafeCodeWriter(repo_path)
        return safe_writer.apply_changes(changeset)
    
    def show_changes(self, result: OrchestrationResult) -> str:
        """
        Display the proposed changes for user review.
        
        Args:
            result: OrchestrationResult from run()
            
        Returns:
            Formatted string showing all proposed changes
        """
        if not result.changeset:
            return "No changes to display."
        
        return result.changeset.to_user_prompt()


async def demo():
    """Demo the orchestrator on the current project."""
    print("=" * 60)
    print("CONTEXTUAL ARCHITECT - DEMO")
    print("=" * 60)
    
    orchestrator = Orchestrator()
    
    result = await orchestrator.run(
        user_request="Add authentication middleware that validates JWT tokens",
        repo_path="E:/FUn/contextual-architect",
        language="python"
    )
    
    print("\n" + "=" * 60)
    print("ORCHESTRATION RESULT")
    print("=" * 60)
    print(f"Success: {result.success}")
    print(f"Target: {result.target_file}")
    print(f"Attempts: {result.attempts}")
    
    if result.validation:
        print(f"\nValidation: {result.validation.summary}")
    
    if result.changeset:
        print("\n" + "=" * 60)
        print("PROPOSED CHANGES")
        print("=" * 60)
        print(orchestrator.show_changes(result))
    
    if result.generated_code:
        print("\n" + "=" * 60)
        print("GENERATED CODE PREVIEW (first 500 chars)")
        print("=" * 60)
        print(result.generated_code[:500])
        if len(result.generated_code) > 500:
            print(f"... ({len(result.generated_code) - 500} more chars)")


if __name__ == "__main__":
    asyncio.run(demo())
