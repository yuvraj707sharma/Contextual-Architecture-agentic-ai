"""
Contextual Architect - Multi-Agent Framework

This package contains the agent swarm architecture:
- BaseAgent: Abstract base class for all agents
- HistorianAgent: Analyzes PR history and patterns
- ArchitectAgent: Maps codebase structure
- ImplementerAgent: Generates code with LLM
- ReviewerAgent: Security, syntax, and compliance checks
- Orchestrator: Chains agents together
- SafeCodeWriter: Permission-based file writing
- StyleAnalyzer: Extracts project-specific code style
- LLM Clients: DeepSeek, Ollama, OpenAI, Anthropic adapters
- AgentConfig: Centralized configuration
- Logger: Structured logging and timing
"""

from .base import BaseAgent, AgentContext, AgentResponse, AgentRole
from .historian import HistorianAgent
from .architect import ArchitectAgent
from .implementer import ImplementerAgent
from .reviewer import ReviewerAgent
from .orchestrator import Orchestrator

# Safety and style
from .safe_writer import SafeCodeWriter, ChangeSet, ProposedChange, plan_safe_changes
from .style_fingerprint import StyleFingerprint, StyleAnalyzer, analyze_project_style

# LLM clients
from .llm_client import (
    BaseLLMClient,
    DeepSeekClient,
    OllamaClient,
    OpenAIClient,
    AnthropicClient,
    create_llm_client,
)

# Config and observability
from .config import AgentConfig
from .logger import get_logger, timed_operation, PipelineMetrics

__all__ = [
    # Agents
    "BaseAgent",
    "AgentContext", 
    "AgentResponse",
    "AgentRole",
    "HistorianAgent",
    "ArchitectAgent",
    "ImplementerAgent",
    "ReviewerAgent",
    "Orchestrator",
    # Safety
    "SafeCodeWriter",
    "ChangeSet",
    "ProposedChange",
    "plan_safe_changes",
    # Style
    "StyleFingerprint",
    "StyleAnalyzer",
    "analyze_project_style",
    # LLM
    "BaseLLMClient",
    "DeepSeekClient",
    "OllamaClient",
    "OpenAIClient",
    "AnthropicClient",
    "create_llm_client",
    # Config & Logging
    "AgentConfig",
    "get_logger",
    "timed_operation",
    "PipelineMetrics",
]

