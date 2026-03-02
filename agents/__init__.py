"""
Contextual Architect — Multi-Agent Code Generation System.

Agents:
  - PlannerAgent: Pre-generation planning and complexity scoring
  - AlignmentAgent: Semantic plan-vs-request validation
  - HistorianAgent: Mines patterns and conventions from a codebase
  - ArchitectAgent: Maps project structure and finds utilities
  - ImplementerAgent: Generates code using LLM with full context
  - TestGeneratorAgent: Auto-generates tests from plan criteria
  - ReviewerAgent: Validates code (syntax, security, lint)
  - StyleAnalyzer: Fingerprints a project's exact coding style

Infrastructure:
  - Orchestrator: Chains agents with rejection loop
  - SafeCodeWriter: Permission-based file writing
  - FeedbackCollector: Post-run data collection
  - AgentConfig: Central configuration
  - create_llm_client: Multi-provider LLM factory

Usage:
    # As a library
    from agents import Orchestrator, AgentConfig
    config = AgentConfig(llm_provider="deepseek")
    orch = Orchestrator(config=config)
    result = await orch.run("Add auth", repo_path="./myproject", language="python")

    # As a CLI
    python -m agents "Add JWT auth" --repo ./myproject --lang python
"""

from .base import BaseAgent, AgentContext, AgentResponse, AgentRole
from .planner import PlannerAgent, PlannerOutput
from .alignment import AlignmentAgent, AlignmentOutput
from .historian import HistorianAgent
from .architect import ArchitectAgent
from .implementer import ImplementerAgent
from .test_generator import TestGeneratorAgent, TestGeneratorOutput
from .reviewer import ReviewerAgent, ValidationResult, validate_code
from .style_fingerprint import StyleAnalyzer, StyleFingerprint
from .pr_search import PRSearcher, PRSummary
from .orchestrator import Orchestrator, OrchestrationResult
from .safe_writer import SafeCodeWriter, ChangeSet, ProposedChange
from .feedback import FeedbackCollector, FeedbackEntry
from .output_validator import validate_agent_output, validate_reviewer_verdict
from .clarification_handler import ClarificationHandler
from .feedback_reader import FeedbackReader
from .llm_client import (
    BaseLLMClient,
    DeepSeekClient,
    OllamaClient,
    OpenAIClient,
    AnthropicClient,
    GeminiClient,
    MockLLMClient,
    create_llm_client,
)
from .config import AgentConfig
from .logger import get_logger, PipelineMetrics
from .project_scanner import ProjectScanner, ProjectSnapshot
from .reasoning_display import ReasoningDisplay
from .plugins import (
    LLMPlugin, WriterPlugin, ReviewerPlugin,
    TrackerPlugin, ScannerPlugin, NotifierPlugin,
    PluginRegistry,
)

__all__ = [
    # Agents
    "BaseAgent",
    "PlannerAgent",
    "AlignmentAgent",
    "HistorianAgent",
    "ArchitectAgent",
    "ImplementerAgent",
    "TestGeneratorAgent",
    "ReviewerAgent",
    "StyleAnalyzer",
    # Orchestration
    "Orchestrator",
    "OrchestrationResult",
    # Data models
    "AgentContext",
    "AgentResponse",
    "AgentRole",
    "PlannerOutput",
    "AlignmentOutput",
    "ValidationResult",
    "TestGeneratorOutput",
    "StyleFingerprint",
    "PRSearcher",
    "PRSummary",
    "ChangeSet",
    "ProposedChange",
    # LLM
    "BaseLLMClient",
    "DeepSeekClient",
    "OllamaClient",
    "OpenAIClient",
    "AnthropicClient",
    "GeminiClient",
    "MockLLMClient",
    "create_llm_client",
    # Config
    "AgentConfig",
    # Utilities
    "get_logger",
    "PipelineMetrics",
    "validate_code",
    # Feedback
    "FeedbackCollector",
    "FeedbackEntry",
    # Clarification & Feedback Loop
    "ClarificationHandler",
    "FeedbackReader",
    # Scanner & Reasoning
    "ProjectScanner",
    "ProjectSnapshot",
    "ReasoningDisplay",
    # Plugins
    "LLMPlugin",
    "WriterPlugin",
    "ReviewerPlugin",
    "TrackerPlugin",
    "ScannerPlugin",
    "NotifierPlugin",
    "PluginRegistry",
]
