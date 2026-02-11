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
import time
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional

from .base import AgentContext, AgentResponse, AgentRole
from .historian import HistorianAgent
from .architect import ArchitectAgent
from .implementer import ImplementerAgent
from .reviewer import ReviewerAgent, ValidationResult
from .safe_writer import SafeCodeWriter, ChangeSet
from .style_fingerprint import StyleAnalyzer
from .llm_client import BaseLLMClient
from .config import AgentConfig
from .logger import get_logger, timed_operation, PipelineMetrics


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
    
    # Performance metrics
    metrics: Optional[PipelineMetrics] = None


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
        config: Optional[AgentConfig] = None,
    ):
        """
        Initialize the orchestrator.
        
        Args:
            llm_client: LLM client for Implementer (overrides config provider)
            config: Pipeline configuration (defaults to AgentConfig())
        """
        self.config = config or AgentConfig()
        self.llm_client = llm_client
        self.logger = get_logger(
            "orchestrator",
            level=self.config.log_level,
            fmt=self.config.log_format,
        )
        
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
        metrics = PipelineMetrics()
        pipeline_start = time.perf_counter()
        
        # Build initial context
        context = AgentContext(
            user_request=user_request,
            repo_path=repo_path,
            language=language,
        )
        
        self.logger.info(
            "Starting orchestration",
            extra={"agent": "orchestrator", "step": "start"},
        )
        self.logger.debug(f"Request: {user_request[:80]}")
        self.logger.debug(f"Repo: {repo_path} | Language: {language}")
        
        # ── PARALLEL DISCOVERY PHASE ─────────────────────────────
        # StyleAnalyzer, Historian, and Architect are independent.
        # They all just scan the codebase — none needs the other's output.
        # Running them concurrently cuts discovery time by ~3x.
        
        self.logger.info(
            "Starting parallel discovery (Style + Historian + Architect)",
            extra={"agent": "orchestrator", "step": "parallel_discovery"},
        )
        
        # Launch all three concurrently
        style_task = asyncio.ensure_future(
            asyncio.to_thread(lambda: StyleAnalyzer(repo_path, language).analyze())
        )
        historian_task = asyncio.ensure_future(self.historian.process(context))
        architect_task = asyncio.ensure_future(self.architect.process(context))
        
        # Wait for all to complete
        try:
            style_fingerprint, historian_response, architect_response = (
                await asyncio.gather(style_task, historian_task, architect_task)
            )
        except Exception as e:
            result.errors.append(f"Parallel discovery failed: {e}")
            self.logger.error(
                f"Parallel discovery failed: {e}",
                extra={"agent": "orchestrator"},
            )
            return result
        
        # Process StyleAnalyzer result
        context.prior_context["style_fingerprint"] = style_fingerprint
        self.logger.debug(
            f"Style: {style_fingerprint.function_naming} functions, "
            f"{style_fingerprint.logger_library} logging"
        )
        
        # Process Historian result
        if not historian_response.success:
            result.errors.append(f"Historian failed: {historian_response.summary}")
            self.logger.error("Historian failed", extra={"agent": "historian"})
            return result
        result.agent_summaries["historian"] = historian_response.summary
        context.prior_context["historian"] = historian_response.data
        
        # Process Architect result
        if not architect_response.success:
            result.errors.append(f"Architect failed: {architect_response.summary}")
            self.logger.error("Architect failed", extra={"agent": "architect"})
            return result
        result.agent_summaries["architect"] = architect_response.summary
        context.prior_context["architect"] = architect_response.data
        result.target_file = architect_response.data.get("target_file", "")
        
        # Step 4: Generate and validate code (with retry loop)
        max_retries = self.config.max_retries
        
        for attempt in range(1, max_retries + 1):
            result.attempts = attempt
            
            # Generate code
            with timed_operation(self.logger, f"implementer_attempt_{attempt}"):
                impl_response = await self.implementer.process(context)
            
            if not impl_response.success:
                result.errors.append(f"Implementer failed: {impl_response.summary}")
                self.logger.warning(
                    f"Implementer failed on attempt {attempt}",
                    extra={"agent": "implementer"},
                )
                continue
            
            generated_code = impl_response.data.get("code", "")
            target_file = impl_response.data.get("file_path", result.target_file)
            
            self.logger.info(
                f"Generated {len(generated_code)} chars (attempt {attempt})",
                extra={"agent": "implementer"},
            )
            
            # Validate with Reviewer
            with timed_operation(self.logger, f"reviewer_attempt_{attempt}"):
                validation = await self.reviewer.validate(
                    code=generated_code,
                    file_path=target_file,
                    language=language,
                    repo_path=repo_path,
                )
            
            result.validation = validation
            result.agent_summaries["reviewer"] = validation.summary
            
            if validation.passed:
                self.logger.info(
                    f"Validation passed: {validation.summary}",
                    extra={"agent": "reviewer"},
                )
                result.generated_code = generated_code
                result.target_file = target_file
                break
            else:
                metrics.retries += 1
                self.logger.warning(
                    f"Validation failed: {validation.summary}",
                    extra={"agent": "reviewer"},
                )
                context.prior_context["validation_errors"] = validation.to_prompt_feedback()
                
                if attempt < max_retries:
                    self.logger.info(
                        f"Retrying ({attempt}/{max_retries})",
                        extra={"step": "retry"},
                    )
        
        # Step 5: Plan safe changes
        if result.generated_code:
            with timed_operation(self.logger, "safe_writer"):
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
            
            self.logger.info(
                f"{len(changeset.changes)} changes planned, "
                f"{len(changeset.untouched_files)} files preserved",
                extra={"agent": "safe_writer"},
            )
        
        # Finalize metrics
        metrics.total_duration_ms = (time.perf_counter() - pipeline_start) * 1000
        result.metrics = metrics
        
        self.logger.info(
            f"Orchestration {'succeeded' if result.success else 'failed'} "
            f"in {metrics.total_duration_ms:.0f}ms",
            extra={"step": "complete"},
        )
        
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
        report = safe_writer.apply_changes(changeset)
        self.logger.info(
            f"Applied {report['total_applied']} changes, "
            f"skipped {report['total_skipped']}",
            extra={"step": "apply"},
        )
        return report
    
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
    import os

    config = AgentConfig(log_level="DEBUG", log_format="pretty")
    orchestrator = Orchestrator(config=config)

    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    result = await orchestrator.run(
        user_request="Add authentication middleware that validates JWT tokens",
        repo_path=project_root,
        language="python"
    )

    logger = get_logger("demo")
    logger.info("=" * 60)
    logger.info("ORCHESTRATION RESULT")
    logger.info(f"Success: {result.success}")
    logger.info(f"Target: {result.target_file}")
    logger.info(f"Attempts: {result.attempts}")

    if result.validation:
        logger.info(f"Validation: {result.validation.summary}")

    if result.metrics:
        logger.info(f"Metrics:\n{result.metrics.summary()}")

    if result.changeset:
        logger.info("PROPOSED CHANGES")
        logger.info(orchestrator.show_changes(result))

    if result.generated_code:
        logger.info("GENERATED CODE PREVIEW (first 500 chars)")
        logger.info(result.generated_code[:500])


if __name__ == "__main__":
    asyncio.run(demo())
