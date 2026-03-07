"""
Tests for the Historian Agent.
"""

import pytest

from ..base import AgentContext, AgentRole
from ..historian import HistorianAgent, HistorianOutput, PatternMatch


class TestPatternMatch:
    """Tests for PatternMatch dataclass."""

    def test_to_dict(self):
        pattern = PatternMatch(
            source="PR #123",
            pattern_type="error_handling",
            description="Wrap errors with context",
            example_code="fmt.Errorf('failed: %w', err)",
            confidence=80,
        )

        result = pattern.to_dict()

        assert result["source"] == "PR #123"
        assert result["pattern_type"] == "error_handling"
        assert result["confidence"] == 80


class TestHistorianOutput:
    """Tests for HistorianOutput dataclass."""

    def test_to_dict_empty(self):
        output = HistorianOutput()
        result = output.to_dict()

        assert result["patterns"] == []
        assert result["conventions"] == {}
        assert result["relevant_prs"] == []

    def test_to_prompt_context(self):
        output = HistorianOutput(
            conventions={"naming": "camelCase"},
            common_mistakes=["Don't use global state"],
        )

        context = output.to_prompt_context()

        assert "camelCase" in context
        assert "global state" in context


class TestHistorianAgent:
    """Tests for HistorianAgent."""

    def test_role(self):
        agent = HistorianAgent()
        assert agent.role == AgentRole.HISTORIAN

    def test_system_prompt_exists(self):
        agent = HistorianAgent()
        assert len(agent.system_prompt) > 100
        assert "Historian" in agent.system_prompt

    @pytest.mark.asyncio
    async def test_process_go_project(self, tmp_path):
        agent = HistorianAgent()
        context = AgentContext(
            user_request="Add authentication middleware",
            repo_path=str(tmp_path),
            language="go",
        )

        response = await agent.process(context)

        assert response.success is True
        assert response.agent_role == AgentRole.HISTORIAN
        assert "patterns" in response.data
        assert "conventions" in response.data

    @pytest.mark.asyncio
    async def test_process_python_project(self, tmp_path):
        # Create a Python file so historian has something to scan
        (tmp_path / "app.py").write_text(
            'def hello_world():\n    pass\n', encoding="utf-8"
        )
        agent = HistorianAgent()
        context = AgentContext(
            user_request="Add user registration",
            repo_path=str(tmp_path),
            language="python",
        )

        response = await agent.process(context)

        assert response.success is True
        assert "conventions" in response.data

    @pytest.mark.asyncio
    async def test_process_suggests_next_agent(self):
        agent = HistorianAgent()
        context = AgentContext(
            user_request="Test",
            repo_path="/test",
            language="go",
        )

        response = await agent.process(context)

        # Historian should suggest Architect as next
        assert response.next_agent == AgentRole.ARCHITECT


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
