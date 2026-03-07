"""
Tests for the Alignment Agent.
"""

import pytest

from ..alignment import AlignmentAgent, AlignmentOutput
from ..base import AgentContext, AgentRole
from ..llm_client import MockLLMClient

# ── AlignmentOutput ──────────────────────────────────────────


class TestAlignmentOutput:
    def test_to_dict(self):
        out = AlignmentOutput(aligned=True, concerns=["c1"], suggestions=["s1"])
        d = out.to_dict()
        assert d["aligned"] is True
        assert d["concerns"] == ["c1"]
        assert d["suggestions"] == ["s1"]
        assert d["skipped"] is False

    def test_to_dict_skipped(self):
        out = AlignmentOutput(aligned=True, skipped=True, skip_reason="simple")
        d = out.to_dict()
        assert d["skipped"] is True
        assert d["skip_reason"] == "simple"

    def test_to_markdown_aligned(self):
        out = AlignmentOutput(aligned=True)
        md = out.to_markdown()
        assert "✅" in md

    def test_to_markdown_misaligned(self):
        out = AlignmentOutput(
            aligned=False, concerns=["bad goal"], suggestions=["fix it"]
        )
        md = out.to_markdown()
        assert "❌" in md
        assert "bad goal" in md
        assert "fix it" in md

    def test_to_markdown_skipped(self):
        out = AlignmentOutput(aligned=True, skipped=True, skip_reason="test")
        md = out.to_markdown()
        assert "skipped" in md.lower()


# ── Complexity Gating ────────────────────────────────────────


class TestComplexityGating:
    @pytest.fixture
    def agent(self):
        return AlignmentAgent()

    @pytest.mark.asyncio
    async def test_skips_simple_tasks(self, agent):
        ctx = AgentContext(
            user_request="Add a hello world function",
            repo_path="/tmp/repo",
            language="python",
        )
        ctx.prior_context["complexity"] = "simple"
        ctx.prior_context["plan"] = {"goal": "hello world"}

        resp = await agent.process(ctx)
        assert resp.success
        assert resp.data["skipped"] is True
        assert resp.data["aligned"] is True

    @pytest.mark.asyncio
    async def test_runs_on_medium(self, agent):
        ctx = AgentContext(
            user_request="Add JWT authentication",
            repo_path="/tmp/repo",
            language="python",
        )
        ctx.prior_context["complexity"] = "medium"
        ctx.prior_context["plan"] = {
            "goal": "Implement JWT authentication",
            "acceptance_criteria": ["Validate tokens", "Return 401"],
            "target_files": [{"path": "auth.py", "action": "CREATE"}],
        }

        resp = await agent.process(ctx)
        assert resp.success
        assert resp.data["skipped"] is False

    @pytest.mark.asyncio
    async def test_runs_on_complex(self, agent):
        ctx = AgentContext(
            user_request="Refactor the entire auth module",
            repo_path="/tmp/repo",
            language="python",
        )
        ctx.prior_context["complexity"] = "complex"
        ctx.prior_context["plan"] = {
            "goal": "Refactor auth module",
            "acceptance_criteria": ["Better structure"],
            "target_files": [{"path": "auth.py", "action": "MODIFY"}],
        }

        resp = await agent.process(ctx)
        assert resp.success
        assert resp.data["skipped"] is False

    @pytest.mark.asyncio
    async def test_defaults_to_medium_when_missing(self, agent):
        ctx = AgentContext(
            user_request="Add logging",
            repo_path="/tmp/repo",
            language="python",
        )
        # No complexity set — should default to medium and run
        ctx.prior_context["plan"] = {
            "goal": "Add logging",
            "acceptance_criteria": ["Logger configured"],
            "target_files": [{"path": "logger.py", "action": "CREATE"}],
        }

        resp = await agent.process(ctx)
        assert resp.success
        assert resp.data["skipped"] is False


# ── Heuristic Mode ───────────────────────────────────────────


class TestHeuristicAlignment:
    @pytest.fixture
    def agent(self):
        return AlignmentAgent()  # No LLM — heuristic mode

    @pytest.mark.asyncio
    async def test_aligned_plan(self, agent):
        ctx = AgentContext(
            user_request="Add user authentication with JWT",
            repo_path="/tmp/repo",
            language="python",
        )
        ctx.prior_context["complexity"] = "medium"
        ctx.prior_context["plan"] = {
            "goal": "Implement JWT user authentication",
            "acceptance_criteria": [
                "Validate JWT tokens",
                "Return 401 for invalid tokens",
            ],
            "target_files": [{"path": "auth.py", "action": "CREATE"}],
            "approach": "Use PyJWT for token validation",
        }

        resp = await agent.process(ctx)
        assert resp.data["aligned"] is True
        assert len(resp.data["concerns"]) == 0

    @pytest.mark.asyncio
    async def test_no_criteria_raises_concern(self, agent):
        ctx = AgentContext(
            user_request="Add caching layer",
            repo_path="/tmp/repo",
            language="python",
        )
        ctx.prior_context["complexity"] = "medium"
        ctx.prior_context["plan"] = {
            "goal": "Add caching",
            "acceptance_criteria": [],
            "target_files": [{"path": "cache.py", "action": "CREATE"}],
        }

        resp = await agent.process(ctx)
        assert any("acceptance criteria" in c.lower() for c in resp.data["concerns"])

    @pytest.mark.asyncio
    async def test_no_target_files_raises_concern(self, agent):
        ctx = AgentContext(
            user_request="Add logging",
            repo_path="/tmp/repo",
            language="python",
        )
        ctx.prior_context["complexity"] = "medium"
        ctx.prior_context["plan"] = {
            "goal": "Add logging support",
            "acceptance_criteria": ["Logger works"],
            "target_files": [],
        }

        resp = await agent.process(ctx)
        assert any("target files" in c.lower() for c in resp.data["concerns"])

    @pytest.mark.asyncio
    async def test_missing_plan_returns_misaligned(self, agent):
        ctx = AgentContext(
            user_request="Add auth",
            repo_path="/tmp/repo",
            language="python",
        )
        ctx.prior_context["complexity"] = "medium"
        # No plan at all

        resp = await agent.process(ctx)
        assert resp.data["aligned"] is False

    @pytest.mark.asyncio
    async def test_low_keyword_overlap_raises_concern(self, agent):
        ctx = AgentContext(
            user_request="Add WebSocket real-time notifications",
            repo_path="/tmp/repo",
            language="python",
        )
        ctx.prior_context["complexity"] = "complex"
        ctx.prior_context["plan"] = {
            "goal": "Build a REST endpoint for data export",
            "acceptance_criteria": ["CSV export works"],
            "target_files": [{"path": "export.py", "action": "CREATE"}],
        }

        resp = await agent.process(ctx)
        # Goal is totally unrelated to request
        assert not resp.data["aligned"] or len(resp.data["concerns"]) > 0


# ── LLM Mode ────────────────────────────────────────────────


class TestLLMAlignment:
    @pytest.mark.asyncio
    async def test_llm_aligned_response(self):
        mock = MockLLMClient(responses=[
            "ALIGNED: yes\n"
            "CONCERNS:\n"
            "SUGGESTIONS:\n"
            "- Consider adding error handling\n"
        ])
        agent = AlignmentAgent(llm_client=mock)

        ctx = AgentContext(
            user_request="Add auth",
            repo_path="/tmp/repo",
            language="python",
        )
        ctx.prior_context["complexity"] = "medium"
        ctx.prior_context["plan"] = {
            "goal": "Add authentication",
            "acceptance_criteria": ["Works"],
            "target_files": [{"path": "auth.py", "action": "CREATE"}],
        }

        resp = await agent.process(ctx)
        assert resp.data["aligned"] is True
        assert len(resp.data["suggestions"]) == 1

    @pytest.mark.asyncio
    async def test_llm_misaligned_response(self):
        mock = MockLLMClient(responses=[
            "ALIGNED: no\n"
            "CONCERNS:\n"
            "- Plan does not address WebSocket requirement\n"
            "- Missing rate limiting\n"
            "SUGGESTIONS:\n"
            "- Add WebSocket handler\n"
        ])
        agent = AlignmentAgent(llm_client=mock)

        ctx = AgentContext(
            user_request="Add WebSocket support",
            repo_path="/tmp/repo",
            language="python",
        )
        ctx.prior_context["complexity"] = "complex"
        ctx.prior_context["plan"] = {
            "goal": "Add REST endpoints",
            "acceptance_criteria": ["API works"],
            "target_files": [{"path": "api.py", "action": "CREATE"}],
        }

        resp = await agent.process(ctx)
        assert resp.data["aligned"] is False
        assert len(resp.data["concerns"]) == 2
        assert len(resp.data["suggestions"]) == 1

    @pytest.mark.asyncio
    async def test_llm_failure_falls_back_to_heuristic(self):
        mock = MockLLMClient(responses=[])  # Will raise on generate
        agent = AlignmentAgent(llm_client=mock)

        ctx = AgentContext(
            user_request="Add auth",
            repo_path="/tmp/repo",
            language="python",
        )
        ctx.prior_context["complexity"] = "medium"
        ctx.prior_context["plan"] = {
            "goal": "Add authentication",
            "acceptance_criteria": ["Token validation"],
            "target_files": [{"path": "auth.py", "action": "CREATE"}],
        }

        # Should NOT raise — falls back to heuristic
        resp = await agent.process(ctx)
        assert resp.success


# ── Agent Role ───────────────────────────────────────────────


class TestAlignmentRole:
    def test_role_is_alignment(self):
        agent = AlignmentAgent()
        assert agent.role == AgentRole.ALIGNMENT
