"""Tests for Planner Agent."""


import pytest

from agents.base import AgentContext
from agents.planner import PlannerAgent, PlannerOutput

# ── Fixtures ─────────────────────────────────────────────

@pytest.fixture
def planner():
    """PlannerAgent in heuristic mode (no LLM)."""
    return PlannerAgent()


@pytest.fixture
def simple_context(tmp_path):
    """Context for a simple request."""
    # Create a minimal project structure
    (tmp_path / "app.py").write_text("def main():\n    pass\n")
    (tmp_path / "utils.py").write_text("def helper():\n    return True\n")

    return AgentContext(
        user_request="Add a health check endpoint",
        repo_path=str(tmp_path),
        language="python",
        prior_context={
            "architect": {
                "target_file": "routes/health.py",
                "related_files": ["app.py"],
                "utilities": [{"name": "helper", "function": "helper"}],
            },
            "historian": {
                "conventions": {
                    "error_handling": "try/except with specific exceptions",
                    "logging": "use internal logger module",
                },
            },
        },
    )


@pytest.fixture
def complex_context(tmp_path):
    """Context for a complex request."""
    (tmp_path / "main.py").write_text("# main")
    (tmp_path / "auth").mkdir()
    (tmp_path / "auth" / "jwt.py").write_text("# jwt module")
    (tmp_path / "db").mkdir()
    (tmp_path / "db" / "models.py").write_text("# models")

    return AgentContext(
        user_request="Refactor authentication to use OAuth2 across all API endpoints",
        repo_path=str(tmp_path),
        language="python",
        prior_context={
            "architect": {
                "target_file": "auth/oauth2.py",
                "related_files": [
                    "auth/jwt.py",
                    "routes/api.py",
                    "middleware/auth.py",
                    "db/models.py",
                ],
                "utilities": [],
            },
        },
    )


# ── Tests: Complexity Scoring ────────────────────────────

class TestComplexityScoring:
    def test_simple_request(self, planner, simple_context):
        score = planner._score_complexity(simple_context)
        assert score in ("simple", "medium")

    def test_complex_request(self, planner, complex_context):
        score = planner._score_complexity(complex_context)
        assert score in ("medium", "complex")

    def test_architectural_keywords_increase_score(self, planner, tmp_path):
        ctx = AgentContext(
            user_request="Add database migration schema for authentication service",
            repo_path=str(tmp_path),
            language="python",
        )
        score = planner._score_complexity(ctx)
        # Multiple arch signals should push to medium or complex
        assert score in ("medium", "complex")

    def test_simple_keywords_reduce_score(self, planner, tmp_path):
        ctx = AgentContext(
            user_request="Add a simple utility helper function",
            repo_path=str(tmp_path),
            language="python",
        )
        score = planner._score_complexity(ctx)
        assert score == "simple"


# ── Tests: Heuristic Planning ────────────────────────────

class TestHeuristicPlanning:
    @pytest.mark.asyncio
    async def test_creates_plan(self, planner, simple_context):
        response = await planner.process(simple_context)
        assert response.success
        assert "plan" in response.data
        assert "plan_markdown" in response.data
        assert "complexity" in response.data

    @pytest.mark.asyncio
    async def test_plan_has_criteria(self, planner, simple_context):
        response = await planner.process(simple_context)
        plan = response.data["plan"]
        assert len(plan["acceptance_criteria"]) >= 1

    @pytest.mark.asyncio
    async def test_plan_has_target_files(self, planner, simple_context):
        response = await planner.process(simple_context)
        plan = response.data["plan"]
        assert len(plan["target_files"]) >= 1
        target = plan["target_files"][0]
        assert "path" in target
        assert "action" in target

    @pytest.mark.asyncio
    async def test_plan_has_do_not(self, planner, simple_context):
        response = await planner.process(simple_context)
        plan = response.data["plan"]
        assert len(plan["do_not"]) >= 1

    @pytest.mark.asyncio
    async def test_plan_markdown_format(self, planner, simple_context):
        response = await planner.process(simple_context)
        md = response.data["plan_markdown"]
        assert md.startswith("# Plan:")
        assert "## Acceptance Criteria" in md
        assert "## Target Files" in md
        assert "## Do NOT" in md


# ── Tests: PlannerOutput ─────────────────────────────────

class TestPlannerOutput:
    def test_to_markdown(self):
        plan = PlannerOutput(
            goal="Add health endpoint",
            acceptance_criteria=["Returns 200 OK", "No auth required"],
            target_files=[
                {"path": "routes/health.py", "action": "CREATE", "reason": "New endpoint"},
            ],
            approach="- Use Flask route\n- Return JSON",
            do_not=["Don't add database queries"],
            pseudocode="@app.route('/health')\ndef health():\n    return {'status': 'ok'}",
            imports_needed=["flask"],
            existing_utilities=["app_factory"],
            complexity="simple",
            pr_warnings=["PR #42: Don't expose internal state in health checks"],
        )
        md = plan.to_markdown()
        assert "# Plan: Add health endpoint" in md
        assert "simple" in md
        assert "Returns 200 OK" in md
        assert "[CREATE]" in md
        assert "routes/health.py" in md
        assert "Don't add database queries" in md
        assert "PR #42" in md
        assert "flask" in md
        assert "```" in md  # pseudocode block

    def test_to_dict(self):
        plan = PlannerOutput(
            goal="test",
            acceptance_criteria=["c1"],
            target_files=[{"path": "a.py", "action": "CREATE"}],
            approach="test approach",
            do_not=["don't"],
            pseudocode="pass",
            imports_needed=["os"],
            existing_utilities=["helper"],
            complexity="simple",
        )
        d = plan.to_dict()
        assert d["goal"] == "test"
        assert d["complexity"] == "simple"
        assert isinstance(d["acceptance_criteria"], list)


# ── Tests: Request Intent Parsing ────────────────────────

class TestRequestParsing:
    def test_add_intent(self, planner):
        action, entity = planner._parse_request_intent("Add JWT authentication")
        assert action == "add"
        assert "jwt" in entity.lower()
        assert "authentication" in entity.lower()

    def test_fix_intent(self, planner):
        action, entity = planner._parse_request_intent("Fix the login bug")
        assert action == "fix"
        assert "login" in entity

    def test_modify_intent(self, planner):
        action, entity = planner._parse_request_intent("Update user model")
        assert action == "modify"

    def test_delete_intent(self, planner):
        action, entity = planner._parse_request_intent("Remove old cache layer")
        assert action == "delete"

    def test_unknown_intent_defaults_to_add(self, planner):
        action, entity = planner._parse_request_intent("JWT middleware please")
        assert action == "add"

    def test_strips_articles(self, planner):
        action, entity = planner._parse_request_intent("Add a new authentication layer")
        assert entity.startswith("authentication") or "authentication" in entity
        assert not entity.startswith("a ")


# ── Tests: PR Context Integration ─────────────────────────

class TestPRContextIntegration:
    @pytest.mark.asyncio
    async def test_pr_warnings_included(self, planner, tmp_path):
        ctx = AgentContext(
            user_request="Add authentication",
            repo_path=str(tmp_path),
            language="python",
            prior_context={
                "pr_history": (
                    "## PR History\n"
                    "- Don't use global middleware for auth\n"
                    "- Always validate token expiry\n"
                ),
            },
        )
        response = await planner.process(ctx)
        plan = response.data["plan"]
        assert len(plan["pr_warnings"]) >= 1


# ── Tests: Style-Aware Planning ──────────────────────────

class TestStyleAwarePlanning:
    @pytest.mark.asyncio
    async def test_approach_uses_style(self, planner, tmp_path):
        ctx = AgentContext(
            user_request="Add helper function",
            repo_path=str(tmp_path),
            language="python",
            prior_context={
                "style_fingerprint": {
                    "function_naming": "snake_case",
                    "logger_library": "structlog",
                    "string_style": "double_quotes",
                },
            },
        )
        response = await planner.process(ctx)
        approach = response.data["plan"]["approach"]
        assert "snake_case" in approach
        assert "structlog" in approach
