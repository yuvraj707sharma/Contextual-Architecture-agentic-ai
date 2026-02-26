"""
Orchestrator - Chains agents together for end-to-end code generation.

This is the "conductor" that:
1. Takes a user request
2. Runs PR Search → Parallel Discovery → Planner → Implementer → Reviewer
3. Handles the rejection loop if code fails review
4. Uses SafeCodeWriter for permission-based file writing
5. Writes plan.md to workspace and re-reads on every retry
6. Returns the final generated code
"""

import asyncio
import os
import time
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional

from .base import AgentContext, AgentResponse, AgentRole
from .planner import PlannerAgent
from .alignment import AlignmentAgent
from .historian import HistorianAgent
from .architect import ArchitectAgent
from .implementer import ImplementerAgent
from .test_generator import TestGeneratorAgent
from .reviewer import ReviewerAgent, ValidationResult
from .pr_search import PRSearcher
from .safe_writer import SafeCodeWriter, ChangeSet
from .style_fingerprint import StyleAnalyzer
from .workspace import Workspace
from .llm_client import BaseLLMClient
from .config import AgentConfig
from .logger import get_logger, timed_operation, PipelineMetrics
from .feedback import FeedbackCollector
from .output_validator import validate_agent_output, validate_reviewer_verdict, try_extract_json
from .clarification_handler import ClarificationHandler
from .feedback_reader import FeedbackReader


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
    1. PR Search: Find relevant past PRs (parallel with discovery)
    2. Parallel Discovery: Style + Historian + Architect
    3. Planner: Create structured plan (plan.md)
    4. Alignment: Semantic plan-vs-request check (medium/complex only)
    5. Implementer: Generate code with LLM (re-reads plan.md)
    6. Test Generator: Auto-generate tests from plan criteria
    7. Reviewer: Validate code (syntax, security, lint)
    8. SafeWriter: Plan safe file modifications
    9. Feedback: Collect pipeline run data for improvement
    
    If Reviewer fails, feed errors back to Implementer and retry.
    Plan.md is re-read from disk on every retry (Manus technique).
    """
    
    def __init__(
        self, 
        llm_client: Optional[BaseLLMClient] = None, 
        config: Optional[AgentConfig] = None,
        pr_data_path: Optional[str] = None,
        repo_path: Optional[str] = None,
    ):
        """
        Initialize the orchestrator.
        
        Args:
            llm_client: LLM client for Implementer (overrides config provider)
            config: Pipeline configuration (defaults to AgentConfig())
            pr_data_path: Path to pr_evolution.jsonl for PR search
            repo_path: Path to the target repo (enables RAG indexing)
        """
        self.config = config or AgentConfig()
        self.llm_client = llm_client
        self.logger = get_logger(
            "orchestrator",
            level=self.config.log_level,
            fmt=self.config.log_format,
        )
        
        # Initialize RAG retriever (optional — graceful if chromadb not installed)
        retriever = self._init_retriever(repo_path) if repo_path else None
        
        # Initialize agents — ALL receive LLM client
        self.planner = PlannerAgent(llm_client, retriever=retriever)
        self.alignment = AlignmentAgent(llm_client)
        self.historian = HistorianAgent(llm_client, retriever=retriever)
        self.architect = ArchitectAgent(llm_client)
        self.implementer = ImplementerAgent(llm_client)
        self.test_generator = TestGeneratorAgent(llm_client)
        self.reviewer = ReviewerAgent(llm_client)
        
        # Utilities
        self.feedback = FeedbackCollector()
        
        # PR Search
        self.pr_searcher = PRSearcher()
        if pr_data_path:
            self.pr_searcher.load(pr_data_path)

    def _init_retriever(self, repo_path: str):
        """Initialize RAG retriever with incremental repo indexing."""
        try:
            from rag.vector_store import ChromaVectorStore
            from rag.indexer import RepoIndexer
            from rag.retriever import CodeRetriever
            from pathlib import Path
            
            repo_name = Path(repo_path).name
            persist_dir = str(Path(repo_path) / ".contextual-architect" / "chroma_db")
            
            store = ChromaVectorStore(repo_name=repo_name, persist_dir=persist_dir)
            indexer = RepoIndexer(store, repo_path=repo_path, repo_name=repo_name)
            stats = indexer.index()
            
            self.logger.info(
                f"RAG ready: {stats['total_chunks']} chunks indexed "
                f"({stats['files_indexed']} new files in {stats['duration_seconds']}s)"
            )
            return CodeRetriever(store)
        except ImportError:
            self.logger.debug("chromadb not installed — RAG disabled")
            return None
        except Exception as e:
            self.logger.warning(f"RAG init failed (non-fatal): {e}")
            return None
    
    async def run(
        self, 
        user_request: str, 
        repo_path: str,
        language: str = "python",
        user_pseudocode: str = None,
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
        
        # Initialize workspace for filesystem-backed memory
        workspace = Workspace(repo_path)
        
        # Thread user pseudocode into context if provided
        if user_pseudocode:
            context.prior_context["user_pseudocode"] = user_pseudocode
            self.logger.info(
                f"User pseudocode provided ({len(user_pseudocode)} chars)",
                extra={"agent": "orchestrator", "step": "pseudocode"},
            )
        
        self.logger.info(
            "Starting orchestration",
            extra={"agent": "orchestrator", "step": "start"},
        )
        self.logger.debug(f"Request: {user_request[:80]}")
        self.logger.debug(f"Repo: {repo_path} | Language: {language}")
        
        # ── PR SEARCH + PARALLEL DISCOVERY PHASE ─────────────────
        # PR Search, StyleAnalyzer, Historian, and Architect are all
        # independent — they scan different data sources.
        # Running them all concurrently for maximum speed.
        
        self.logger.info(
            "Starting parallel discovery (PR Search + Style + Historian + Architect)",
            extra={"agent": "orchestrator", "step": "parallel_discovery"},
        )
        
        # Launch all four concurrently
        pr_task = asyncio.ensure_future(
            asyncio.to_thread(
                lambda: self.pr_searcher.search_to_prompt(
                    user_request, max_results=3, max_tokens=1000
                )
            )
        )
        style_task = asyncio.ensure_future(
            asyncio.to_thread(lambda: StyleAnalyzer(repo_path, language).analyze())
        )
        historian_task = asyncio.ensure_future(self.historian.process(context))
        architect_task = asyncio.ensure_future(self.architect.process(context))
        
        # Wait for all to complete
        try:
            pr_context, style_fingerprint, historian_response, architect_response = (
                await asyncio.gather(
                    pr_task, style_task, historian_task, architect_task
                )
            )
        except Exception as e:
            result.errors.append(f"Parallel discovery failed: {e}")
            self.logger.error(
                f"Parallel discovery failed: {e}",
                extra={"agent": "orchestrator"},
            )
            return result
        
        # Process PR Search result
        if pr_context:
            context.prior_context["pr_history"] = pr_context
            self.logger.info(
                f"PR search found relevant history ({len(pr_context)} chars)",
                extra={"agent": "pr_search"},
            )
        
        # Process StyleAnalyzer result
        context.prior_context["style_fingerprint"] = style_fingerprint
        workspace.write_discovery("style", style_fingerprint.to_dict())
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
        workspace.write_discovery("historian", historian_response.data)
        
        # Process Architect result
        if not architect_response.success:
            result.errors.append(f"Architect failed: {architect_response.summary}")
            self.logger.error("Architect failed", extra={"agent": "architect"})
            return result
        result.agent_summaries["architect"] = architect_response.summary
        context.prior_context["architect"] = architect_response.data
        result.target_file = architect_response.data.get("target_file", "")
        workspace.write_discovery("architect", architect_response.data)
        
        # ── CLARIFICATION CHECK ──────────────────────────────────
        # Handle CLARIFICATION_NEEDED signals from Architect.
        clarification_handler = ClarificationHandler()
        should_continue, processed = clarification_handler.handle(architect_response.data)
        
        if not should_continue:
            result.errors.append(
                f"Clarification required: {processed.get('ambiguity', 'unknown')}"
            )
            result.agent_summaries["clarification"] = processed
            self.logger.warning(
                "Pipeline halted: clarification needed",
                extra={"agent": "orchestrator", "step": "clarification"},
            )
            return result
        
        # Update architect data with cleaned output (signal keys removed)
        context.prior_context["architect"] = processed
        
        # ── PLANNER PHASE ────────────────────────────────────────
        # Creates a structured plan BEFORE any code generation.
        # The plan is written to workspace/plan.md and re-read
        # by the Implementer on every retry attempt.
        
        self.logger.info(
            "Running Planner Agent",
            extra={"agent": "orchestrator", "step": "planner"},
        )
        
        with timed_operation(self.logger, "planner"):
            planner_response = await self.planner.process(context)
        
        if not planner_response.success:
            result.errors.append(f"Planner failed: {planner_response.summary}")
            self.logger.error("Planner failed", extra={"agent": "planner"})
            return result
        
        result.agent_summaries["planner"] = planner_response.summary
        plan_markdown = planner_response.data.get("plan_markdown", "")
        complexity = planner_response.data.get("complexity", "medium")
        
        # Write plan to workspace — this is re-read on every retry
        workspace.write_plan(plan_markdown)
        context.prior_context["plan"] = planner_response.data.get("plan", {})
        
        self.logger.info(
            f"Plan created: {complexity} complexity",
            extra={"agent": "planner"},
        )
        
        # ── ALIGNMENT PHASE (medium/complex only) ────────────────
        if complexity in ("medium", "complex"):
            self.logger.info(
                "Running Alignment check",
                extra={"agent": "orchestrator", "step": "alignment"},
            )
            context.prior_context["complexity"] = complexity
            with timed_operation(self.logger, "alignment"):
                align_response = await self.alignment.process(context)
            
            if align_response.success and not align_response.data.get("aligned", True):
                concerns = align_response.data.get("concerns", [])
                self.logger.warning(
                    f"Alignment failed: {concerns}",
                    extra={"agent": "alignment"},
                )
                # Feed concerns back to Implementer as extra context
                context.prior_context["alignment_concerns"] = concerns
            
            result.agent_summaries["alignment"] = align_response.summary
        
        # ── IMPLEMENTATION + REVIEW LOOP ──────────────────────────
        max_retries = self.config.max_retries
        
        for attempt in range(1, max_retries + 1):
            result.attempts = attempt
            
            # Re-read plan from disk on every attempt
            # (Manus technique: pushes plan into recent attention window)
            fresh_plan = workspace.read_plan()
            context.prior_context["plan_markdown"] = fresh_plan
            
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
                
                # Store attempt for sliding window
                error_strings = [
                    e.to_string() if hasattr(e, 'to_string') else str(e)
                    for e in (validation.errors if hasattr(validation, 'errors') else [])
                ]
                workspace.write_attempt(
                    attempt,
                    generated_code,
                    error_strings,
                )
                
                if attempt < max_retries:
                    self.logger.info(
                        f"Retrying ({attempt}/{max_retries})",
                        extra={"step": "retry"},
                    )
        
        # ── TEST GENERATION PHASE ────────────────────────────────
        if result.generated_code:
            self.logger.info(
                "Running Test Generator",
                extra={"agent": "orchestrator", "step": "test_generator"},
            )
            context.prior_context["implementer"] = {
                "code": result.generated_code,
                "file_path": result.target_file,
            }
            with timed_operation(self.logger, "test_generator"):
                test_response = await self.test_generator.process(context)
            
            if test_response.success and test_response.data.get("test_code"):
                result.agent_summaries["test_generator"] = test_response.summary
                test_code = test_response.data["test_code"]
                test_file = test_response.data["test_file_path"]
                generated_files = {result.target_file: result.generated_code}
                if test_code and test_file:
                    generated_files[test_file] = test_code
            else:
                generated_files = {result.target_file: result.generated_code}
        
        # ── SAFE WRITER PHASE ─────────────────────────────────────
        if result.generated_code:
            with timed_operation(self.logger, "safe_writer"):
                safe_writer = SafeCodeWriter(repo_path)
                changeset = safe_writer.plan_changes(
                    generated_files=generated_files,
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
        
        # ── FEEDBACK COLLECTION ───────────────────────────────────
        try:
            feedback_entry = self.feedback.collect(result)
            feedback_path = os.path.join(
                workspace.workspace_dir, "feedback.jsonl"
            )
            self.feedback.save(feedback_entry, feedback_path)
            self.logger.debug(
                "Feedback saved",
                extra={"step": "feedback"},
            )
        except Exception as e:
            self.logger.debug(f"Feedback collection skipped: {e}")
        
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
