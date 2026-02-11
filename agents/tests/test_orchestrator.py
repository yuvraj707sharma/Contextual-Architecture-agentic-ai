"""
Tests for the Orchestrator - full pipeline integration tests.
"""

import pytest

from ..base import AgentContext, AgentRole
from ..orchestrator import Orchestrator, OrchestrationResult
from ..llm_client import MockLLMClient
from ..config import AgentConfig
from ..logger import PipelineMetrics


class TestOrchestrationResult:
    """Tests for OrchestrationResult dataclass."""

    def test_default_values(self):
        result = OrchestrationResult(success=False)
        assert result.generated_code == ""
        assert result.attempts == 1
        assert result.errors == []


class TestOrchestrator:
    """Tests for the Orchestrator pipeline."""

    def test_init_default_config(self):
        orchestrator = Orchestrator()
        assert orchestrator.config.llm_provider == "mock"
        assert orchestrator.config.max_retries == 3

    def test_init_custom_config(self):
        config = AgentConfig(max_retries=5, log_level="DEBUG")
        orchestrator = Orchestrator(config=config)
        assert orchestrator.config.max_retries == 5

    @pytest.mark.asyncio
    async def test_full_pipeline_no_llm(self, tmp_repo):
        """Run full pipeline without LLM — uses placeholder generation."""
        config = AgentConfig(
            max_retries=1,
            use_external_tools=False,
            log_level="WARNING",
        )
        orchestrator = Orchestrator(config=config)

        result = await orchestrator.run(
            user_request="Add health check endpoint",
            repo_path=str(tmp_repo),
            language="python",
        )

        assert isinstance(result, OrchestrationResult)
        assert result.success is True
        assert len(result.generated_code) > 0
        assert result.target_file != ""
        assert "historian" in result.agent_summaries
        assert "architect" in result.agent_summaries

    @pytest.mark.asyncio
    async def test_pipeline_with_mock_llm(self, tmp_repo, mock_llm):
        config = AgentConfig(
            max_retries=1,
            use_external_tools=False,
            log_level="WARNING",
        )
        orchestrator = Orchestrator(llm_client=mock_llm, config=config)

        result = await orchestrator.run(
            user_request="Add authentication",
            repo_path=str(tmp_repo),
            language="python",
        )

        assert result.success is True
        assert "authenticate" in result.generated_code

    @pytest.mark.asyncio
    async def test_pipeline_produces_changeset(self, tmp_repo):
        config = AgentConfig(
            max_retries=1,
            use_external_tools=False,
            log_level="WARNING",
        )
        orchestrator = Orchestrator(config=config)

        result = await orchestrator.run(
            user_request="Add user service",
            repo_path=str(tmp_repo),
            language="python",
        )

        assert result.changeset is not None
        assert len(result.changeset.changes) > 0

    @pytest.mark.asyncio
    async def test_pipeline_has_metrics(self, tmp_repo):
        config = AgentConfig(
            max_retries=1,
            use_external_tools=False,
            log_level="WARNING",
        )
        orchestrator = Orchestrator(config=config)

        result = await orchestrator.run(
            user_request="Add logging middleware",
            repo_path=str(tmp_repo),
            language="python",
        )

        assert result.metrics is not None
        assert result.metrics.total_duration_ms > 0

    @pytest.mark.asyncio
    async def test_show_changes(self, tmp_repo):
        config = AgentConfig(
            max_retries=1,
            use_external_tools=False,
            log_level="WARNING",
        )
        orchestrator = Orchestrator(config=config)

        result = await orchestrator.run(
            user_request="Add cache layer",
            repo_path=str(tmp_repo),
            language="python",
        )

        output = orchestrator.show_changes(result)
        assert isinstance(output, str)
        assert len(output) > 0

    def test_show_changes_no_changeset(self):
        orchestrator = Orchestrator()
        result = OrchestrationResult(success=False)
        assert orchestrator.show_changes(result) == "No changes to display."
