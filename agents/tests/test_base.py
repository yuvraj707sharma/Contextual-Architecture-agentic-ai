"""
Tests for agents.base module.

Tests base classes, enums, and data structures used by all agents.
"""

import pytest

from ..base import AgentContext, AgentResponse, AgentRole


class TestAgentRole:
    """Tests for AgentRole enum."""

    def test_historian_role(self):
        """Test HISTORIAN role exists and has correct value."""
        assert AgentRole.HISTORIAN.value == "historian"

    def test_architect_role(self):
        """Test ARCHITECT role exists and has correct value."""
        assert AgentRole.ARCHITECT.value == "architect"

    def test_implementer_role(self):
        """Test IMPLEMENTER role exists and has correct value."""
        assert AgentRole.IMPLEMENTER.value == "implementer"

    def test_reviewer_role(self):
        """Test REVIEWER role exists and has correct value."""
        assert AgentRole.REVIEWER.value == "reviewer"

    def test_all_roles_unique(self):
        """Test that all role values are unique."""
        roles = [role.value for role in AgentRole]
        assert len(roles) == len(set(roles))


class TestAgentContext:
    """Tests for AgentContext dataclass."""

    def test_creation_minimal(self):
        """Test creating context with minimal required fields."""
        context = AgentContext(
            user_request="Add authentication",
            repo_path="/path/to/repo",
        )

        assert context.user_request == "Add authentication"
        assert context.repo_path == "/path/to/repo"
        assert context.prior_context == {}
        assert context.target_files == []
        assert context.language == "unknown"
        assert context.metadata == {}

    def test_creation_full(self):
        """Test creating context with all fields."""
        context = AgentContext(
            user_request="Fix bug",
            repo_path="/repo",
            prior_context={"historian": {"patterns": []}},
            target_files=["main.py", "utils.py"],
            language="python",
            metadata={"priority": "high"},
        )

        assert context.user_request == "Fix bug"
        assert context.repo_path == "/repo"
        assert "historian" in context.prior_context
        assert len(context.target_files) == 2
        assert context.language == "python"
        assert context.metadata["priority"] == "high"

    def test_to_prompt_context_minimal(self):
        """Test prompt context generation with minimal data."""
        context = AgentContext(
            user_request="Add tests",
            repo_path="/test/repo",
        )

        prompt = context.to_prompt_context()

        assert "Add tests" in prompt
        assert "/test/repo" in prompt
        assert "User Request" in prompt
        assert "Repository" in prompt
        assert "Language" in prompt

    def test_to_prompt_context_with_target_files(self):
        """Test prompt context includes target files."""
        context = AgentContext(
            user_request="Refactor",
            repo_path="/repo",
            target_files=["app.py", "models.py"],
        )

        prompt = context.to_prompt_context()

        assert "Target Files" in prompt
        assert "app.py" in prompt
        assert "models.py" in prompt

    def test_to_prompt_context_with_prior_context(self):
        """Test prompt context includes prior agent context."""
        context = AgentContext(
            user_request="Implement feature",
            repo_path="/repo",
            prior_context={
                "historian": {
                    "patterns": ["error_handling"],
                    "conventions": {"naming": "snake_case"},
                },
            },
        )

        prompt = context.to_prompt_context()

        assert "Context from Other Agents" in prompt
        assert "historian" in prompt.lower()
        assert "error_handling" in prompt
        assert "snake_case" in prompt

    def test_to_prompt_context_with_language(self):
        """Test prompt context includes language."""
        context = AgentContext(
            user_request="Add feature",
            repo_path="/repo",
            language="go",
        )

        prompt = context.to_prompt_context()

        assert "go" in prompt


class TestAgentResponse:
    """Tests for AgentResponse dataclass."""

    def test_creation_minimal(self):
        """Test creating response with minimal fields."""
        response = AgentResponse(
            agent_role=AgentRole.HISTORIAN,
            success=True,
        )

        assert response.agent_role == AgentRole.HISTORIAN
        assert response.success is True
        assert response.data == {}
        assert response.summary == ""
        assert response.errors == []
        assert response.warnings == []
        assert response.next_agent is None

    def test_creation_full(self):
        """Test creating response with all fields."""
        response = AgentResponse(
            agent_role=AgentRole.ARCHITECT,
            success=True,
            data={"structure": "analyzed"},
            summary="Analyzed codebase structure",
            errors=["Error 1"],
            warnings=["Warning 1", "Warning 2"],
            next_agent=AgentRole.IMPLEMENTER,
        )

        assert response.agent_role == AgentRole.ARCHITECT
        assert response.success is True
        assert response.data["structure"] == "analyzed"
        assert response.summary == "Analyzed codebase structure"
        assert len(response.errors) == 1
        assert len(response.warnings) == 2
        assert response.next_agent == AgentRole.IMPLEMENTER

    def test_creation_failure(self):
        """Test creating a failure response."""
        response = AgentResponse(
            agent_role=AgentRole.REVIEWER,
            success=False,
            errors=["Critical error occurred"],
        )

        assert response.success is False
        assert len(response.errors) == 1
        assert response.errors[0] == "Critical error occurred"

    def test_to_context_dict(self):
        """Test conversion to context dictionary."""
        response = AgentResponse(
            agent_role=AgentRole.HISTORIAN,
            success=True,
            data={"patterns": ["pattern1"]},
            summary="Found patterns",
            warnings=["Minor issue"],
        )

        ctx_dict = response.to_context_dict()

        assert ctx_dict["success"] is True
        assert ctx_dict["summary"] == "Found patterns"
        assert "patterns" in ctx_dict["data"]
        assert "pattern1" in ctx_dict["data"]["patterns"]
        assert ctx_dict["warnings"] == ["Minor issue"]

    def test_to_context_dict_excludes_errors_on_success(self):
        """Test that context dict includes warnings but errors are separate."""
        response = AgentResponse(
            agent_role=AgentRole.IMPLEMENTER,
            success=True,
            data={"code": "generated"},
            summary="Code generated",
            errors=[],  # No errors on success
            warnings=["Consider optimization"],
        )

        ctx_dict = response.to_context_dict()

        assert "warnings" in ctx_dict
        assert len(ctx_dict["warnings"]) == 1
        # errors is not typically passed to next agent in context
        assert "errors" not in ctx_dict


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
