"""Tests for persistent repository memory (MEMORY.md)."""

import os
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from agents.base import AgentContext
from agents.historian import HistorianAgent, HistorianOutput


@pytest.fixture
def temp_repo(tmp_path):
    repo_dir = tmp_path / "test_repo"
    repo_dir.mkdir()

    # Create .contextual-architect directory
    ca_dir = repo_dir / ".contextual-architect"
    ca_dir.mkdir()

    # Create MEMORY.md
    memory_file = ca_dir / "MEMORY.md"
    memory_file.write_text("## Project Memory\n- Always use tabs.\n- Never import logging.", encoding="utf-8")

    return repo_dir


@pytest.mark.asyncio
async def test_historian_loads_memory(temp_repo):
    # Initialize historian
    historian = HistorianAgent(llm_client=None)

    context = AgentContext(
        user_request="Test request",
        repo_path=str(temp_repo),
        language="python"
    )

    # Process the context
    response = await historian.process(context)

    assert response.success
    assert "repository_memory" in response.data
    assert "Always use tabs." in response.data["repository_memory"]
    assert "repository_memory" in context.prior_context
    assert "Never import logging." in context.prior_context["repository_memory"]


def test_historian_output_to_prompt_context():
    output = HistorianOutput(
        repository_memory="## Repo Rules\n- Follow styling."
    )
    prompt_context = output.to_prompt_context()

    assert "## Persistent Repository Memory" in prompt_context
    assert "- Follow styling." in prompt_context
