"""
Base Agent - Abstract base class for all agents in the swarm.

This module defines the contract that all agents must follow,
enabling the orchestrator to work with them uniformly.
"""

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class AgentRole(Enum):
    """Roles in the agent swarm."""
    PLANNER = "planner"              # Pre-generation planning
    ALIGNMENT = "alignment"          # Semantic plan-vs-request check
    HISTORIAN = "historian"          # Analyzes PR history and patterns
    ARCHITECT = "architect"          # Maps codebase structure
    IMPLEMENTER = "implementer"     # Generates code
    TEST_GENERATOR = "test_generator"  # Auto-generates tests
    REVIEWER = "reviewer"            # Security and compliance


@dataclass
class AgentContext:
    """
    Context provided to an agent for processing.

    This is the input to an agent - it contains the user's request
    plus any context gathered by previous agents.
    """
    # The user's original request
    user_request: str

    # The target repository (local path or GitHub URL)
    repo_path: str

    # Context from other agents (keyed by agent role)
    prior_context: Dict[str, Any] = field(default_factory=dict)

    # Specific files to focus on (if known)
    target_files: List[str] = field(default_factory=list)

    # Language of the project
    language: str = "unknown"

    # Additional metadata
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_prompt_context(self) -> str:
        """Convert context to a string for LLM prompts."""
        parts = [
            f"## User Request\n{self.user_request}",
            f"\n## Repository\n{self.repo_path}",
            f"\n## Language\n{self.language}",
        ]

        if self.target_files:
            parts.append("\n## Target Files\n" + "\n".join(f"- {f}" for f in self.target_files))

        if self.prior_context:
            parts.append("\n## Context from Other Agents")
            for agent, ctx in self.prior_context.items():
                parts.append(f"\n### {agent.title()}\n{json.dumps(ctx, indent=2)}")

        return "\n".join(parts)


@dataclass
class AgentResponse:
    """
    Response from an agent.

    This is the output of an agent - it contains structured data
    that can be used by other agents or the orchestrator.
    """
    # The agent that produced this response
    agent_role: AgentRole

    # Whether the agent succeeded
    success: bool

    # Structured output data (agent-specific)
    data: Dict[str, Any] = field(default_factory=dict)

    # Human-readable summary
    summary: str = ""

    # Errors or warnings
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    # Suggested next agent to run (for chaining)
    next_agent: Optional[AgentRole] = None

    def to_context_dict(self) -> Dict[str, Any]:
        """Convert to dict for passing to next agent."""
        return {
            "success": self.success,
            "summary": self.summary,
            "data": self.data,
            "warnings": self.warnings,
        }


class BaseAgent(ABC):
    """
    Abstract base class for all agents.

    Each agent has:
    - A specific role (Historian, Architect, etc.)
    - A system prompt defining its behavior
    - A set of tools it can use (via MCP)
    - A process() method that takes context and returns a response
    """

    def __init__(self, llm_client=None):
        """
        Initialize the agent.

        Args:
            llm_client: The LLM client to use (OpenAI, Anthropic, local, etc.)
                       If None, agent runs in "dry run" mode
        """
        self.llm_client = llm_client
        self._tools = []

    @property
    @abstractmethod
    def role(self) -> AgentRole:
        """The role of this agent."""
        pass

    @property
    @abstractmethod
    def system_prompt(self) -> str:
        """The system prompt for this agent."""
        pass

    @property
    def tools(self) -> List[Dict[str, Any]]:
        """Tools available to this agent (MCP tools)."""
        return self._tools

    def register_tool(self, tool: Dict[str, Any]) -> None:
        """Register an MCP tool for this agent to use."""
        self._tools.append(tool)

    @abstractmethod
    async def process(self, context: AgentContext) -> AgentResponse:
        """
        Process the context and produce a response.

        This is the main entry point for the agent.

        Args:
            context: The input context

        Returns:
            AgentResponse with the agent's output
        """
        pass

    def _create_response(
        self,
        success: bool,
        data: Dict[str, Any],
        summary: str,
        errors: List[str] = None,
        warnings: List[str] = None,
        next_agent: AgentRole = None
    ) -> AgentResponse:
        """Helper to create a response."""
        return AgentResponse(
            agent_role=self.role,
            success=success,
            data=data,
            summary=summary,
            errors=errors or [],
            warnings=warnings or [],
            next_agent=next_agent,
        )
