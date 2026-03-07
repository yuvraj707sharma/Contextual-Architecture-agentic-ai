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

from .alignment import AlignmentAgent, AlignmentOutput
from .architect import ArchitectAgent
from .base import AgentContext, AgentResponse, AgentRole, BaseAgent
from .clarification_handler import ClarificationHandler
from .config import AgentConfig
from .feedback import FeedbackCollector, FeedbackEntry
from .feedback_reader import FeedbackReader
from .historian import HistorianAgent
from .implementer import ImplementerAgent
from .llm_client import (
    AnthropicClient,
    BaseLLMClient,
    DeepSeekClient,
    GeminiClient,
    MockLLMClient,
    OllamaClient,
    OpenAIClient,
    create_llm_client,
)
from .logger import PipelineMetrics, get_logger
from .orchestrator import OrchestrationResult, Orchestrator
from .output_validator import validate_agent_output, validate_reviewer_verdict
from .planner import PlannerAgent, PlannerOutput
from .plugins import (
    LLMPlugin,
    NotifierPlugin,
    PluginRegistry,
    ReviewerPlugin,
    ScannerPlugin,
    TrackerPlugin,
    WriterPlugin,
)
from .pr_search import PRSearcher, PRSummary
from .project_scanner import ProjectScanner, ProjectSnapshot
from .reasoning_display import ReasoningDisplay
from .reviewer import ReviewerAgent, ValidationResult, validate_code
from .safe_writer import ChangeSet, ProposedChange, SafeCodeWriter
from .style_fingerprint import StyleAnalyzer, StyleFingerprint
from .test_generator import TestGeneratorAgent, TestGeneratorOutput

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
