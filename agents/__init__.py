"""
Contextual Architect - Multi-Agent Framework

This package contains the agent swarm architecture:
- BaseAgent: Abstract base class for all agents
- HistorianAgent: Analyzes PR history and patterns
- ArchitectAgent: Maps codebase structure
- Orchestrator: Chains agents together
- ImplementerAgent: Generates code (TODO)
- ReviewerAgent: Security and compliance checks (TODO)
"""

from .base import BaseAgent, AgentContext, AgentResponse, AgentRole
from .historian import HistorianAgent
from .architect import ArchitectAgent
from .orchestrator import Orchestrator

__all__ = [
    "BaseAgent",
    "AgentContext", 
    "AgentResponse",
    "AgentRole",
    "HistorianAgent",
    "ArchitectAgent",
    "Orchestrator",
]
