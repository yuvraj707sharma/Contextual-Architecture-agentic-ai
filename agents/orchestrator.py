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
from pathlib import Path
from typing import Any, Dict, List, Optional

from .alignment import AlignmentAgent
from .architect import ArchitectAgent
from .base import AgentContext
from .clarification_handler import ClarificationHandler
from .config import AgentConfig
from .feedback import FeedbackCollector
from .graph_builder import GraphBuilder
from .historian import HistorianAgent
from .impact_analyzer import ImpactAnalyzer
from .implementer import ImplementerAgent
from .llm_client import BaseLLMClient
from .logger import PipelineMetrics, get_logger, timed_operation
from .pipeline_report import PipelineReport
from .planner import PlannerAgent
from .pr_search import PRSearcher
from .project_scanner import ProjectScanner
from .reasoning_display import ReasoningDisplay
from .reviewer import ReviewerAgent, ValidationResult
from .safe_writer import ChangeSet, SafeCodeWriter
from .shell_executor import ShellExecutor
from .style_fingerprint import StyleAnalyzer
from .test_generator import TestGeneratorAgent
from .trace_logger import TraceLogger
from .workspace import Workspace


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
            llm_client: Default LLM client (used for fast agents)
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

        # ── Per-Agent Provider Routing ────────────────────────
        # Smart agents can use a better provider (e.g., Gemini)
        # Fast agents use the default provider (e.g., Groq)
        planner_client = llm_client
        implementer_client = llm_client

        if self.config.planner_provider:
            try:
                from .llm_client import create_llm_client
                planner_client = create_llm_client(
                    provider=self.config.planner_provider,
                    api_key=self.config.planner_api_key,
                )
                self.logger.info(
                    f"Planner using: {self.config.planner_provider} "
                    f"({planner_client.model_name})",
                    extra={"agent": "orchestrator"},
                )
            except Exception as e:
                self.logger.warning(
                    f"Failed to create planner client ({self.config.planner_provider}): {e}. "
                    f"Falling back to default.",
                    extra={"agent": "orchestrator"},
                )

        if self.config.implementer_provider:
            try:
                from .llm_client import create_llm_client
                implementer_client = create_llm_client(
                    provider=self.config.implementer_provider,
                    api_key=self.config.implementer_api_key,
                )
                self.logger.info(
                    f"Implementer using: {self.config.implementer_provider} "
                    f"({implementer_client.model_name})",
                    extra={"agent": "orchestrator"},
                )
            except Exception as e:
                self.logger.warning(
                    f"Failed to create implementer client ({self.config.implementer_provider}): {e}. "
                    f"Falling back to default.",
                    extra={"agent": "orchestrator"},
                )

        # Initialize agents — smart agents get better provider
        self.planner = PlannerAgent(planner_client, retriever=retriever)
        self.alignment = AlignmentAgent(planner_client)  # uses planner's model
        self.implementer = ImplementerAgent(implementer_client)
        self.test_generator = TestGeneratorAgent(implementer_client)  # uses implementer's model

        # Fast agents use default provider
        self.historian = HistorianAgent(llm_client, retriever=retriever)
        self.architect = ArchitectAgent(llm_client)
        self.reviewer = ReviewerAgent(llm_client)

        # Utilities
        self.feedback = FeedbackCollector()
        self.reasoning = ReasoningDisplay(streaming=True)

        # PR Search
        self.pr_searcher = PRSearcher()
        if pr_data_path:
            self.pr_searcher.load(pr_data_path)

    def _init_retriever(self, repo_path: str):
        """Initialize RAG retriever with incremental repo indexing."""
        try:
            from pathlib import Path

            from rag.indexer import RepoIndexer
            from rag.retriever import CodeRetriever
            from rag.vector_store import ChromaVectorStore

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
        skip_test_generation: bool = False,
        run_existing_tests: str = "",
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

        # ── TRACE LOGGING (for future distillation) ──────────────
        tracer = TraceLogger()
        try:
            tracer.set_metadata(
                user_request=user_request,
                repo_path=repo_path,
                language=language,
                provider=self.config.llm_provider,
                model=self.config.llm_model or "",
            )
        except Exception:
            pass  # Tracing should never break the pipeline

        # ── Reset reasoning for this run ──────────────────────────
        self.reasoning.clear()

        # ── PROJECT SCANNING PHASE ────────────────────────────────
        # Runs FIRST — gives all agents full project awareness.
        # No LLM calls, pure filesystem. ~100ms.
        self.reasoning.emit("scanner", f"Scanning project at {Path(repo_path).name}...")

        try:
            scanner = ProjectScanner(repo_path, language)
            project_snapshot = scanner.scan()
            context.prior_context["project_snapshot"] = project_snapshot.to_dict()
            context.prior_context["project_context"] = project_snapshot.to_prompt_context()
            # Detailed context for Planner/Implementer — includes FULL file tree,
            # ALL deps, config files. These agents need complete project awareness
            # because they get ONE shot — they can't browse the filesystem themselves.
            context.prior_context["project_context_detailed"] = project_snapshot.to_prompt_context(detailed=True)

            # Emit key findings as reasoning
            self.reasoning.emit(
                "scanner",
                f"Found {project_snapshot.total_files} files across "
                f"{project_snapshot.total_dirs} directories",
            )
            if project_snapshot.frameworks:
                self.reasoning.emit(
                    "scanner",
                    f"Detected frameworks: {', '.join(project_snapshot.frameworks)}",
                )
            if project_snapshot.auth_systems:
                self.reasoning.emit(
                    "scanner",
                    f"Auth system: {', '.join(project_snapshot.auth_systems)}",
                )
            if project_snapshot.databases:
                self.reasoning.emit(
                    "scanner",
                    f"Database: {', '.join(project_snapshot.databases)}",
                )
            if project_snapshot.package_manager:
                self.reasoning.emit(
                    "scanner",
                    f"Package manager: {project_snapshot.package_manager}"
                    + (f", test runner: {project_snapshot.test_runner}" if project_snapshot.test_runner else ""),
                )
            if project_snapshot.has_ci:
                self.reasoning.emit(
                    "scanner",
                    f"CI/CD: {project_snapshot.ci_platform}",
                )

            # Trace log
            try:
                tracer.log_agent(
                    "scanner", user_request[:200],
                    f"{project_snapshot.total_files} files, "
                    f"frameworks={project_snapshot.frameworks}",
                    project_snapshot.to_dict(),
                )
            except Exception:
                pass
        except Exception as e:
            self.logger.debug(f"Project scanner skipped: {e}")
            self.reasoning.emit("scanner", f"Scan skipped (non-critical): {e}")

        # ── CODE GRAPH PHASE ──────────────────────────────────────
        # Builds a deterministic AST-based call/import graph.
        # Pure filesystem + AST — no LLM calls. Typically <500ms.
        # This is MACRO's technical moat: no competitor does this.

        graph = None
        impact_analyzer = None
        try:
            self.reasoning.emit("graph", "Building code relationship graph...")
            graph_builder = GraphBuilder(repo_path)
            graph = graph_builder.build()
            impact_analyzer = ImpactAnalyzer(graph)

            summary = graph.summary()
            self.reasoning.emit(
                "graph",
                f"Graph built: {summary['total_nodes']} nodes, "
                f"{summary['total_edges']} edges "
                f"({summary['functions']} functions, {summary['classes']} classes)",
            )
            self.logger.info(
                f"Code graph: {summary['total_nodes']} nodes, "
                f"{summary['total_edges']} edges from {summary['files']} files",
                extra={"agent": "graph_builder"},
            )

            # Store graph summary in context (lightweight)
            context.prior_context["code_graph_summary"] = summary

            try:
                tracer.log_agent(
                    "graph_builder", user_request[:200],
                    f"{summary['total_nodes']} nodes, {summary['total_edges']} edges",
                    summary,
                )
            except Exception:
                pass
        except Exception as e:
            self.logger.debug(f"Code graph skipped (non-critical): {e}")
            self.reasoning.emit("graph", f"Graph skipped (non-critical): {e}")

        # ── PR SEARCH + PARALLEL DISCOVERY PHASE ─────────────────
        # PR Search, StyleAnalyzer, Historian, and Architect are all
        # independent — they scan different data sources.
        # Running them all concurrently for maximum speed.

        self.reasoning.emit("discovery", "Running parallel discovery (Style + History + Architecture)...")
        self.reasoning.start_spinner("Analyzing project conventions...")

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
            self.reasoning.stop_spinner("Discovery complete")
        except Exception as e:
            self.reasoning.stop_spinner()
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
        self.reasoning.emit("historian", historian_response.summary)

        # Process Architect result
        if not architect_response.success:
            result.errors.append(f"Architect failed: {architect_response.summary}")
            self.logger.error("Architect failed", extra={"agent": "architect"})
            return result
        result.agent_summaries["architect"] = architect_response.summary
        context.prior_context["architect"] = architect_response.data
        result.target_file = architect_response.data.get("target_file", "")
        workspace.write_discovery("architect", architect_response.data)
        self.reasoning.emit("architect", architect_response.summary)

        # Log discovery traces
        try:
            tracer.log_agent(
                "historian", user_request[:200],
                historian_response.summary,
                historian_response.data,
                historian_response.success,
            )
            tracer.log_agent(
                "architect", user_request[:200],
                architect_response.summary,
                architect_response.data,
                architect_response.success,
            )
            tracer.log_agent(
                "style", user_request[:200],
                str(style_fingerprint.function_naming),
                style_fingerprint.to_dict(),
            )
        except Exception:
            pass

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

        # ── PROACTIVE CONFLICT DETECTION ──────────────────────────
        # Compare user request against scanner findings to surface
        # conflicts BEFORE the Planner runs.
        # e.g., "Your project uses Firebase but you asked for Supabase"

        project_snap_dict = context.prior_context.get("project_snapshot", {})
        if isinstance(project_snap_dict, dict):
            conflicts = clarification_handler.detect_conflicts(
                user_request=user_request,
                project_snapshot=project_snap_dict,
                language=context.language,
            )
        else:
            # If snapshot is a ProjectSnapshot object, convert it
            try:
                conflicts = clarification_handler.detect_conflicts(
                    user_request=user_request,
                    project_snapshot=project_snap_dict.to_dict() if hasattr(project_snap_dict, 'to_dict') else {},
                    language=context.language,
                )
            except Exception:
                conflicts = []

        if conflicts:
            self.reasoning.emit(
                "clarification",
                f"Detected {len(conflicts)} conflict(s): "
                + ", ".join(f"{c.category}({c.detected}→{c.requested})" for c in conflicts),
            )

            # Log all assumptions (these will be visible in traces)
            for c in conflicts:
                self.logger.warning(
                    f"Conflict [{c.category}]: project has {c.detected}, "
                    f"user wants {c.requested}. Default: {c.default_action}",
                    extra={"agent": "clarification", "step": "proactive"},
                )

            # Inject conflict context into planner's prior context
            conflict_context = clarification_handler.questions_to_context(conflicts)
            context.prior_context["detected_conflicts"] = conflict_context

            # Store for interactive mode to display later
            result.agent_summaries["conflicts"] = [
                {"category": c.category, "question": c.question,
                 "detected": c.detected, "requested": c.requested,
                 "default": c.default_action}
                for c in conflicts
            ]

        # ── GRAPH IMPACT ANALYSIS ─────────────────────────────────
        # Use the code graph to find which files/functions are affected
        # by this request. This gives the Planner DETERMINISTIC facts
        # about code relationships — not LLM guesses.

        if impact_analyzer:
            try:
                impact_reports = impact_analyzer.analyze_request(user_request)
                if impact_reports:
                    graph_context = impact_analyzer.format_for_planner(impact_reports)
                    context.prior_context["graph_intelligence"] = graph_context

                    # Also store structured data for downstream agents
                    context.prior_context["impact_reports"] = [
                        r.to_dict() for r in impact_reports
                    ]

                    affected_files = set()
                    for r in impact_reports:
                        affected_files.update(r.affected_files)

                    self.reasoning.emit(
                        "graph",
                        f"Impact analysis: {len(impact_reports)} target(s) analyzed, "
                        f"{len(affected_files)} file(s) may need changes",
                    )
                    self.logger.info(
                        f"Graph impact: {len(affected_files)} affected files",
                        extra={"agent": "impact_analyzer"},
                    )
                else:
                    self.reasoning.emit(
                        "graph",
                        "No graph targets found for this request (new code path)",
                    )
            except Exception as e:
                self.logger.debug(f"Impact analysis skipped: {e}")

        # ── PLANNER PHASE ────────────────────────────────────────
        # Creates a structured plan BEFORE any code generation.
        # The plan is written to workspace/plan.md and re-read
        # by the Implementer on every retry attempt.

        self.reasoning.emit("planner", f"Planning: {user_request[:80]}...")
        self.reasoning.start_spinner("Creating implementation plan...")

        self.logger.info(
            "Running Planner Agent",
            extra={"agent": "orchestrator", "step": "planner"},
        )

        with timed_operation(self.logger, "planner"):
            planner_response = await self.planner.process(context)
        self.reasoning.stop_spinner("Plan created")

        if not planner_response.success:
            result.errors.append(f"Planner failed: {planner_response.summary}")
            self.logger.error("Planner failed", extra={"agent": "planner"})
            return result

        result.agent_summaries["planner"] = planner_response.summary
        plan_markdown = planner_response.data.get("plan_markdown", "")
        complexity = planner_response.data.get("complexity", "medium")

        try:
            tracer.log_agent(
                "planner", user_request[:200],
                planner_response.summary,
                planner_response.data,
                planner_response.success,
            )
        except Exception:
            pass

        # Write plan to workspace — this is re-read on every retry
        workspace.write_plan(plan_markdown)
        context.prior_context["plan"] = planner_response.data.get("plan", {})

        # ── OVERRIDE: Planner's MODIFY target overrides Architect's guess ──
        # The Architect runs BEFORE the Planner and guesses a target filename.
        # If the Planner says MODIFY an existing file AND the user referenced
        # that file in their request, use it as the target.
        # We DON'T override if the LLM hallucinated a MODIFY target that
        # the user never mentioned (e.g., picking a random file to modify).
        import re
        user_request_lower = context.user_request.lower()
        plan_targets = planner_response.data.get("plan", {}).get("target_files", [])
        if not plan_targets:
            plan_targets = planner_response.data.get("target_files", [])
        for t in plan_targets:
            if t.get("action") == "MODIFY" and t.get("path"):
                modify_target = t["path"]
                # Only override if the user explicitly named this file
                target_basename = Path(modify_target).stem.lower()
                if target_basename in user_request_lower:
                    result.target_file = modify_target
                    if "architect" in context.prior_context:
                        context.prior_context["architect"]["target_file"] = modify_target
                    self.logger.info(
                        f"Planner overrides target: {modify_target}",
                        extra={"agent": "orchestrator"},
                    )
                    break

        self.logger.info(
            f"Plan created: {complexity} complexity",
            extra={"agent": "planner"},
        )
        self.reasoning.emit("planner", f"Complexity: {complexity}, {planner_response.summary}")

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

        # ── READ EXISTING FILE CONTENTS FOR IMPLEMENTER ────────────
        # Read content of files the Implementer should know about:
        # 1. MODIFY targets from the plan
        # 2. Files referenced in the user's request
        # 3. Architect-suggested target files that exist
        existing_file_contents = {}

        def _try_read(file_path: str):
            """Read a file if it exists, cap at 3000 chars."""
            if file_path in existing_file_contents:
                return  # Already read
            full_path = Path(repo_path) / file_path
            if full_path.exists() and full_path.is_file():
                try:
                    content = full_path.read_text(encoding="utf-8", errors="ignore")
                    if len(content) > 3000:
                        content = content[:3000] + "\n# ... (truncated) ..."
                    existing_file_contents[file_path] = content
                except Exception:
                    pass

        # Source 1: MODIFY targets from the plan
        plan_data = context.prior_context.get("plan", {})
        target_files_list = plan_data.get("target_files", [])
        if not target_files_list and isinstance(planner_response.data, dict):
            target_files_list = planner_response.data.get("target_files", [])

        for target in target_files_list:
            file_path = target.get("path", "")
            if target.get("action") == "MODIFY" and file_path:
                _try_read(file_path)

        # Source 2: Files referenced in the user's request
        ext_pattern = r"\b([\w/\\.-]+\.py)\b"
        request_files = re.findall(ext_pattern, context.user_request, re.IGNORECASE)
        for rf in request_files:
            # Try exact path first
            if (Path(repo_path) / rf).exists():
                _try_read(rf)
            else:
                # Search recursively for the filename
                basename = Path(rf).name
                for f in Path(repo_path).rglob(basename):
                    if ".contextual-architect" not in str(f):
                        rel = str(f.relative_to(Path(repo_path))).replace("\\", "/")
                        _try_read(rel)
                        break

        # Source 3: Architect-suggested target file
        architect_target = context.prior_context.get("architect", {}).get("target_file", "")
        if architect_target:
            _try_read(architect_target)

        if existing_file_contents:
            context.prior_context["existing_file_contents"] = existing_file_contents

        # ── IMPLEMENTATION + REVIEW LOOP ──────────────────────────
        max_retries = self.config.max_retries

        for attempt in range(1, max_retries + 1):
            result.attempts = attempt

            # Re-read plan from disk on every attempt
            # (Manus technique: pushes plan into recent attention window)
            fresh_plan = workspace.read_plan()
            context.prior_context["plan_markdown"] = fresh_plan

            # Generate code
            self.reasoning.emit(
                "implementer",
                f"Generating code (attempt {attempt}/{max_retries})..."
                + (f" Target: {result.target_file}" if result.target_file else ""),
            )
            self.reasoning.start_spinner(f"Writing code (attempt {attempt}/{max_retries})...")
            with timed_operation(self.logger, f"implementer_attempt_{attempt}"):
                impl_response = await self.implementer.process(context)
            self.reasoning.stop_spinner("Code generated")

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
                self.reasoning.emit("reviewer", f"Validation passed: {validation.summary}")
                result.generated_code = generated_code
                result.target_file = target_file

                # Log successful implementation + review
                try:
                    tracer.log_agent(
                        "implementer", plan_markdown[:300],
                        impl_response.summary,
                        {"code_len": len(generated_code), "file": target_file},
                        True, attempt,
                    )
                    tracer.log_agent(
                        "reviewer", f"code:{len(generated_code)} chars",
                        validation.summary,
                        {"passed": True},
                        True, attempt,
                    )
                except Exception:
                    pass

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
        if result.generated_code and not skip_test_generation:
            self.reasoning.emit("test_generator", "Generating tests for the implementation...")
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
        elif result.generated_code and skip_test_generation:
            self.reasoning.emit(
                "test_generator",
                "Skipped — using project's existing tests instead",
            )
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

        # ── POST-WRITE COMMAND SUGGESTIONS ────────────────────────
        # Auto-detect what commands should be run after writing files:
        # - New dependency file → pip install / npm install
        # - Test file written → pytest / npm test
        # - Any code → linting
        if result.generated_code:
            try:
                shell_executor = ShellExecutor(repo_path)
                suggestions = shell_executor.suggest_post_write(
                    generated_files, language
                )
                if suggestions:
                    result.context["post_write_commands"] = [
                        {"command": s.command, "reason": s.reason,
                         "risk": s.risk.value, "auto": s.auto_approve}
                        for s in suggestions
                    ]
                    self.reasoning.emit(
                        "executor",
                        f"{len(suggestions)} post-write command(s) suggested: "
                        + ", ".join(s.command for s in suggestions[:3]),
                    )
            except Exception as e:
                self.logger.debug(f"Post-write suggestions skipped: {e}")

        # ── RUN EXISTING TESTS (when skip_test_generation is enabled) ─────
        if result.generated_code and run_existing_tests:
            self.reasoning.emit(
                "test_runner",
                f"Running project tests: {run_existing_tests}",
            )
            try:
                import subprocess
                test_proc = subprocess.run(
                    run_existing_tests,
                    shell=True,
                    cwd=repo_path,
                    capture_output=True,
                    text=True,
                    timeout=120,
                )
                test_passed = test_proc.returncode == 0
                test_output = (test_proc.stdout or "")[-2000:]  # last 2000 chars
                test_stderr = (test_proc.stderr or "")[-1000:]

                result.context["existing_test_results"] = {
                    "command": run_existing_tests,
                    "passed": test_passed,
                    "return_code": test_proc.returncode,
                    "output": test_output,
                    "stderr": test_stderr,
                }

                if test_passed:
                    self.reasoning.emit(
                        "test_runner",
                        f"✅ Tests passed: {run_existing_tests}",
                    )
                else:
                    self.reasoning.emit(
                        "test_runner",
                        f"❌ Tests failed (exit code {test_proc.returncode})",
                    )
                    self.logger.warning(
                        f"Existing tests failed: {test_stderr[:200]}",
                        extra={"agent": "test_runner"},
                    )
            except subprocess.TimeoutExpired:
                self.reasoning.emit("test_runner", "⏰ Tests timed out (120s)")
                result.context["existing_test_results"] = {
                    "command": run_existing_tests,
                    "passed": False,
                    "error": "Timed out after 120 seconds",
                }
            except Exception as e:
                self.logger.debug(f"Existing test execution failed: {e}")
                self.reasoning.emit("test_runner", f"Test execution error: {e}")

        # ── PIPELINE REPORT (GitHub-style Dashboard) ─────────────
        # Generate a formatted report showing the user everything:
        # what was done, why, test/CI results, repo stats, git commands.
        try:
            # Populate result context for the report
            result.context["user_request"] = user_request
            result.context["code_graph_summary"] = context.prior_context.get("code_graph_summary", {})
            result.context["impact_reports"] = context.prior_context.get("impact_reports", [])
            result.context["project_snapshot"] = context.prior_context.get("project_snapshot", {})
            result.context["plan"] = context.prior_context.get("plan", {})

            report = PipelineReport.from_result(result, repo_path)
            result.context["pipeline_report"] = report.render()
            result.context["pipeline_report_dict"] = report.to_dict()
            result.context["commit_message"] = report.commit_message
            result.context["git_commands"] = report.git_commands

            self.reasoning.emit("report", "Pipeline dashboard generated")
        except Exception as e:
            self.logger.debug(f"Pipeline report skipped: {e}")

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

        # ── SAVE TRACE (for distillation) ─────────────────────────
        try:
            # Include reasoning steps in trace for training data
            tracer.log_agent(
                "reasoning_display", "pipeline",
                self.reasoning.get_summary()[:500],
                {"steps": self.reasoning.to_trace_data()},
            )
            tracer.log_result(
                success=result.success,
                attempts=result.attempts,
                generated_code_len=len(result.generated_code),
                errors=result.errors,
            )
            tracer.save()
        except Exception:
            pass  # Never break the pipeline

        # Store reasoning in result for display
        result.context["reasoning"] = self.reasoning.get_summary()

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
