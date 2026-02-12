"""
Contextual Architect — Multi-Agent Code Generation System.

Agents:
  - HistorianAgent: Mines patterns and conventions from a codebase
  - ArchitectAgent: Maps project structure and finds utilities
  - ImplementerAgent: Generates code using LLM with full context
  - ReviewerAgent: Validates code (syntax, security, lint)
  - StyleAnalyzer: Fingerprints a project's exact coding style

Infrastructure:
  - Orchestrator: Chains agents with rejection loop
  - SafeCodeWriter: Permission-based file writing
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
from .historian import HistorianAgent
from .architect import ArchitectAgent
from .implementer import ImplementerAgent
from .reviewer import ReviewerAgent, ValidationResult, validate_code
from .style_fingerprint import StyleAnalyzer, StyleFingerprint
from .orchestrator import Orchestrator, OrchestrationResult
from .safe_writer import SafeCodeWriter, ChangeSet, ProposedChange
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

__all__ = [
    # Agents
    "BaseAgent",
    "HistorianAgent",
    "ArchitectAgent",
    "ImplementerAgent",
    "ReviewerAgent",
    "StyleAnalyzer",
    # Orchestration
    "Orchestrator",
    "OrchestrationResult",
    # Data models
    "AgentContext",
    "AgentResponse",
    "AgentRole",
    "ValidationResult",
    "StyleFingerprint",
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
]
