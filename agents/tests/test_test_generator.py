"""
Tests for the Test Generator Agent.
"""


import pytest

from ..base import AgentContext, AgentRole
from ..llm_client import MockLLMClient
from ..test_generator import FRAMEWORK_MAP, TestGeneratorAgent, TestGeneratorOutput

# ── TestGeneratorOutput ──────────────────────────────────────


class TestTestGeneratorOutput:
    def test_to_dict(self):
        out = TestGeneratorOutput(
            test_code="def test_foo(): pass",
            test_file_path="tests/test_foo.py",
            test_count=1,
            framework="pytest",
            criteria_covered=["Foo works"],
        )
        d = out.to_dict()
        assert d["test_code"] == "def test_foo(): pass"
        assert d["test_count"] == 1
        assert d["framework"] == "pytest"
        assert d["criteria_covered"] == ["Foo works"]

    def test_to_dict_empty(self):
        out = TestGeneratorOutput(
            test_code="", test_file_path="", test_count=0, framework="pytest"
        )
        d = out.to_dict()
        assert d["test_count"] == 0


# ── Framework Detection ──────────────────────────────────────


class TestFrameworkDetection:
    @pytest.fixture
    def agent(self):
        return TestGeneratorAgent()

    def test_python_framework(self, agent):
        fw = agent._detect_framework("python")
        assert fw["name"] == "pytest"
        assert fw["file_ext"] == ".py"

    def test_go_framework(self, agent):
        fw = agent._detect_framework("go")
        assert fw["name"] == "testing"
        assert fw["file_ext"] == "_test.go"

    def test_typescript_framework(self, agent):
        fw = agent._detect_framework("typescript")
        assert fw["name"] == "jest"
        assert fw["file_ext"] == ".test.ts"

    def test_javascript_framework(self, agent):
        fw = agent._detect_framework("javascript")
        assert fw["name"] == "jest"
        assert fw["file_ext"] == ".test.js"

    def test_unknown_language_defaults(self, agent):
        fw = agent._detect_framework("rust")
        assert fw["name"] == "unittest"  # fallback


# ── Test Path Derivation ─────────────────────────────────────


class TestPathDerivation:
    @pytest.fixture
    def agent(self):
        return TestGeneratorAgent()

    def test_python_path(self, agent):
        fw = FRAMEWORK_MAP["python"]
        path = agent._derive_test_path("src/auth.py", "python", fw)
        assert path.endswith("test_auth.py")
        assert "tests" in path

    def test_go_path(self, agent):
        fw = FRAMEWORK_MAP["go"]
        path = agent._derive_test_path("internal/auth/handler.go", "go", fw)
        assert path.endswith("handler_test.go")
        assert "internal" in path

    def test_ts_path(self, agent):
        fw = FRAMEWORK_MAP["typescript"]
        path = agent._derive_test_path("src/auth.ts", "typescript", fw)
        assert path.endswith("auth.test.ts")

    def test_empty_impl_file(self, agent):
        fw = FRAMEWORK_MAP["python"]
        path = agent._derive_test_path("", "python", fw)
        assert path == "tests/test_generated.py"


# ── Heuristic Stub Generation ───────────────────────────────


class TestHeuristicStubs:
    @pytest.fixture
    def agent(self):
        return TestGeneratorAgent()  # No LLM

    @pytest.mark.asyncio
    async def test_python_stubs_from_criteria(self, agent):
        ctx = AgentContext(
            user_request="Add auth",
            repo_path="/tmp/repo",
            language="python",
        )
        ctx.prior_context["plan"] = {
            "acceptance_criteria": [
                "Validate JWT tokens",
                "Return 401 for invalid tokens",
            ],
        }
        ctx.prior_context["implementer"] = {
            "code": "def validate_token(token: str) -> bool:\n    return True\n",
            "file_path": "src/auth.py",
        }

        resp = await agent.process(ctx)
        assert resp.success
        assert resp.data["test_count"] == 2
        assert resp.data["framework"] == "pytest"
        assert "test_" in resp.data["test_code"]
        assert "validate_token" in resp.data["test_code"]

    @pytest.mark.asyncio
    async def test_go_stubs(self, agent):
        ctx = AgentContext(
            user_request="Add handler",
            repo_path="/tmp/repo",
            language="go",
        )
        ctx.prior_context["plan"] = {
            "acceptance_criteria": ["Handle GET requests"],
        }
        ctx.prior_context["implementer"] = {
            "code": "package handlers\n\nfunc HandleGet() {}\n",
            "file_path": "internal/handlers/get.go",
        }

        resp = await agent.process(ctx)
        assert resp.success
        assert resp.data["framework"] == "testing"
        assert "func Test" in resp.data["test_code"]
        assert "package handlers" in resp.data["test_code"]

    @pytest.mark.asyncio
    async def test_ts_stubs(self, agent):
        ctx = AgentContext(
            user_request="Add component",
            repo_path="/tmp/repo",
            language="typescript",
        )
        ctx.prior_context["plan"] = {
            "acceptance_criteria": ["Render correctly"],
        }
        ctx.prior_context["implementer"] = {
            "code": "export function render() {}",
            "file_path": "src/component.ts",
        }

        resp = await agent.process(ctx)
        assert resp.success
        assert resp.data["framework"] == "jest"
        assert "describe" in resp.data["test_code"]

    @pytest.mark.asyncio
    async def test_no_criteria_no_code(self, agent):
        ctx = AgentContext(
            user_request="Add something",
            repo_path="/tmp/repo",
            language="python",
        )
        ctx.prior_context["plan"] = {}
        ctx.prior_context["implementer"] = {}

        resp = await agent.process(ctx)
        assert resp.success
        assert resp.data["test_count"] == 0

    @pytest.mark.asyncio
    async def test_criteria_covered_tracking(self, agent):
        criteria = ["Check auth", "Handle errors"]
        ctx = AgentContext(
            user_request="Add auth",
            repo_path="/tmp/repo",
            language="python",
        )
        ctx.prior_context["plan"] = {"acceptance_criteria": criteria}
        ctx.prior_context["implementer"] = {
            "code": "def check(): pass",
            "file_path": "auth.py",
        }

        resp = await agent.process(ctx)
        assert resp.data["criteria_covered"] == criteria


# ── LLM Mode ────────────────────────────────────────────────


class TestLLMGeneration:
    @pytest.mark.asyncio
    async def test_llm_generates_tests(self):
        mock = MockLLMClient(responses=[
            '```python\n'
            'import pytest\n\n'
            'def test_validate_token():\n'
            '    assert validate_token("valid") is True\n\n'
            'def test_invalid_token():\n'
            '    assert validate_token("") is False\n'
            '```\n'
        ])
        agent = TestGeneratorAgent(llm_client=mock)

        ctx = AgentContext(
            user_request="Add auth",
            repo_path="/tmp/repo",
            language="python",
        )
        ctx.prior_context["plan"] = {
            "acceptance_criteria": ["Validate tokens", "Reject invalid"],
        }
        ctx.prior_context["implementer"] = {
            "code": "def validate_token(t): return bool(t)",
            "file_path": "auth.py",
        }

        resp = await agent.process(ctx)
        assert resp.success
        assert resp.data["test_count"] == 2
        assert "test_validate_token" in resp.data["test_code"]

    @pytest.mark.asyncio
    async def test_llm_failure_falls_back(self):
        mock = MockLLMClient(responses=[])  # Will fail
        agent = TestGeneratorAgent(llm_client=mock)

        ctx = AgentContext(
            user_request="Add auth",
            repo_path="/tmp/repo",
            language="python",
        )
        ctx.prior_context["plan"] = {
            "acceptance_criteria": ["Token works"],
        }
        ctx.prior_context["implementer"] = {
            "code": "def validate(): pass",
            "file_path": "auth.py",
        }

        resp = await agent.process(ctx)
        assert resp.success  # Falls back to stubs


# ── Helpers ──────────────────────────────────────────────────


class TestHelpers:
    @pytest.fixture
    def agent(self):
        return TestGeneratorAgent()

    def test_criterion_to_func_name(self, agent):
        assert agent._criterion_to_func_name("Validate JWT tokens") == "validate_jwt_tokens"

    def test_criterion_to_func_name_special_chars(self, agent):
        result = agent._criterion_to_func_name("Return 401 for invalid!")
        assert result == "return_401_for_invalid"

    def test_criterion_to_go_name(self, agent):
        assert agent._criterion_to_go_name("Handle GET requests") == "HandleGetRequests"

    def test_criterion_to_func_name_empty(self, agent):
        assert agent._criterion_to_func_name("") == "criterion"

    def test_count_tests_python(self, agent):
        code = "def test_a(): pass\ndef test_b(): pass\n"
        assert agent._count_tests(code, "python") == 2

    def test_count_tests_go(self, agent):
        code = "func TestA(t *testing.T) {}\nfunc TestB(t *testing.T) {}\n"
        assert agent._count_tests(code, "go") == 2

    def test_count_tests_js(self, agent):
        code = "it('works', () => {});\nit('fails', () => {});\n"
        assert agent._count_tests(code, "javascript") == 2


# ── Agent Role ───────────────────────────────────────────────


class TestRole:
    def test_role_is_test_generator(self):
        agent = TestGeneratorAgent()
        assert agent.role == AgentRole.TEST_GENERATOR
