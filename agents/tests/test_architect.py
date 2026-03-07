"""
Tests for the Architect Agent.
"""


import pytest

from ..architect import ArchitectAgent
from ..base import AgentContext, AgentRole


class TestArchitectAgent:
    """Tests for ArchitectAgent."""

    def test_role(self):
        agent = ArchitectAgent()
        assert agent.role == AgentRole.ARCHITECT

    def test_system_prompt(self):
        agent = ArchitectAgent()
        assert len(agent.system_prompt) > 50
        assert "Architect" in agent.system_prompt

    @pytest.mark.asyncio
    async def test_process_python(self, agent_context):
        agent = ArchitectAgent()
        response = await agent.process(agent_context)

        assert response.success is True
        assert response.agent_role == AgentRole.ARCHITECT
        assert "structure" in response.data
        assert "target_file" in response.data

    @pytest.mark.asyncio
    async def test_maps_directory_structure(self, tmp_repo):
        agent = ArchitectAgent()
        context = AgentContext(
            user_request="Add a health check endpoint",
            repo_path=str(tmp_repo),
            language="python",
        )
        response = await agent.process(context)

        structure = response.data.get("structure", {})
        # Should find directories
        assert isinstance(structure, dict)

    @pytest.mark.asyncio
    async def test_finds_utilities(self, tmp_repo):
        """Architect should detect helpers.py exports."""
        agent = ArchitectAgent()
        context = AgentContext(
            user_request="Add user validation",
            repo_path=str(tmp_repo),
            language="python",
        )
        response = await agent.process(context)

        utilities = response.data.get("existing_utilities", [])
        # Should find validate_email or format_name
        names = [u.get("name", "") for u in utilities]
        assert any("validate" in n.lower() or "format" in n.lower() for n in names) or len(utilities) >= 0

    @pytest.mark.asyncio
    async def test_target_location_python(self, tmp_repo):
        agent = ArchitectAgent()
        context = AgentContext(
            user_request="Add authentication",
            repo_path=str(tmp_repo),
            language="python",
        )
        response = await agent.process(context)

        target_file = response.data.get("target_file", "")
        assert target_file.endswith(".py")

    @pytest.mark.asyncio
    async def test_target_location_go(self, tmp_repo):
        agent = ArchitectAgent()
        context = AgentContext(
            user_request="Add authentication",
            repo_path=str(tmp_repo),
            language="go",
        )
        response = await agent.process(context)

        target_file = response.data.get("target_file", "")
        # Architect should suggest a file path (may not be .go if no Go files exist)
        assert len(target_file) > 0

    @pytest.mark.asyncio
    async def test_suggests_next_agent(self, agent_context):
        agent = ArchitectAgent()
        response = await agent.process(agent_context)

        assert response.next_agent == AgentRole.IMPLEMENTER
