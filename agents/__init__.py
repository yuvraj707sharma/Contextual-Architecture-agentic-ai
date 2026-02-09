"""
Contextual Architect - Multi-Agent Framework

This package contains the agent swarm architecture:
- BaseAgent: Abstract base class for all agents
- HistorianAgent: Analyzes PR history and patterns
- ArchitectAgent: Maps codebase structure
- ImplementerAgent: Generates code
- ReviewerAgent: Security and compliance checks
"""

from .base import BaseAgent, AgentContext, AgentResponse
from .historian import HistorianAgent

__all__ = [
    "BaseAgent",
    "AgentContext", 
    "AgentResponse",
    "HistorianAgent",
]
