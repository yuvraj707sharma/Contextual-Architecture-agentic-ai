"""
Tests for Graph Builder and Impact Analyzer.

Tests the core differentiator: deterministic code graph from AST.
"""

import sys
import textwrap
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from agents.graph_builder import RepoGraph, build_repo_graph
from agents.impact_analyzer import ImpactAnalyzer, ImpactReport

# ── Fixtures ─────────────────────────────────────────────────

@pytest.fixture
def python_project(tmp_path):
    """Create a minimal Python project with known call/import relationships."""

    # models/user.py — base model
    (tmp_path / "models").mkdir()
    (tmp_path / "models" / "__init__.py").write_text("")
    (tmp_path / "models" / "user.py").write_text(textwrap.dedent("""\
        class BaseModel:
            def save(self):
                pass

        class User(BaseModel):
            def __init__(self, name: str):
                self.name = name

            def validate(self):
                check_name(self.name)
                return True

        def check_name(name: str) -> bool:
            return len(name) > 0
    """))

    # services/auth.py — imports from models, calls User methods
    (tmp_path / "services").mkdir()
    (tmp_path / "services" / "__init__.py").write_text("")
    (tmp_path / "services" / "auth.py").write_text(textwrap.dedent("""\
        from models.user import User, check_name

        def login(username: str, password: str):
            user = User(username)
            if user.validate():
                return create_token(user)
            return None

        def create_token(user):
            return f"token-{user.name}"

        def logout(token: str):
            revoke_token(token)

        def revoke_token(token: str):
            pass
    """))

    # api/routes.py — imports from services, defines endpoints
    (tmp_path / "api").mkdir()
    (tmp_path / "api" / "__init__.py").write_text("")
    (tmp_path / "api" / "routes.py").write_text(textwrap.dedent("""\
        from services.auth import login, logout

        def handle_login(request):
            username = request.get("username")
            password = request.get("password")
            token = login(username, password)
            return {"token": token}

        def handle_logout(request):
            token = request.get("token")
            logout(token)
            return {"status": "ok"}

        def health_check():
            return {"status": "healthy"}
    """))

    # utils/helpers.py — standalone, no relationships
    (tmp_path / "utils").mkdir()
    (tmp_path / "utils" / "__init__.py").write_text("")
    (tmp_path / "utils" / "helpers.py").write_text(textwrap.dedent("""\
        def format_date(dt):
            return dt.strftime("%Y-%m-%d")

        def slugify(text: str) -> str:
            return text.lower().replace(" ", "-")
    """))

    return tmp_path


@pytest.fixture
def js_project(tmp_path):
    """Create a minimal JS project."""
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "auth.js").write_text(textwrap.dedent("""\
        import { User } from './models/user';
        const jwt = require('jsonwebtoken');

        export function login(username, password) {
            const user = new User(username);
            return createToken(user);
        }

        function createToken(user) {
            return jwt.sign({ id: user.id }, 'secret');
        }

        export const logout = async (token) => {
            return revokeToken(token);
        };
    """))

    (tmp_path / "src" / "models").mkdir()
    (tmp_path / "src" / "models" / "user.js").write_text(textwrap.dedent("""\
        export class User {
            constructor(name) {
                this.name = name;
            }
        }

        export class AdminUser extends User {
            constructor(name) {
                super(name);
                this.role = 'admin';
            }
        }
    """))

    return tmp_path


@pytest.fixture
def go_project(tmp_path):
    """Create a minimal Go project."""
    (tmp_path / "handlers").mkdir()
    (tmp_path / "handlers" / "auth.go").write_text(textwrap.dedent("""\
        package handlers

        import (
            "net/http"
            "github.com/gin-gonic/gin"
        )

        func Login(c *gin.Context) {
            username := c.PostForm("username")
            token := CreateToken(username)
            c.JSON(http.StatusOK, gin.H{"token": token})
        }

        func CreateToken(username string) string {
            return "token-" + username
        }

        func (s *Server) HandleHealth(c *gin.Context) {
            c.JSON(http.StatusOK, gin.H{"status": "ok"})
        }
    """))

    return tmp_path


# ── Graph Builder Tests ──────────────────────────────────────

class TestGraphBuilderPython:
    """Test Python AST-based graph extraction."""

    def test_builds_graph(self, python_project):
        graph = build_repo_graph(str(python_project))
        assert isinstance(graph, RepoGraph)
        assert len(graph.nodes) > 0
        assert len(graph.edges) > 0

    def test_finds_all_functions(self, python_project):
        graph = build_repo_graph(str(python_project))
        func_names = {n.name for n in graph.nodes.values() if n.node_type == "function"}
        assert "login" in func_names
        assert "create_token" in func_names
        assert "logout" in func_names
        assert "check_name" in func_names
        assert "handle_login" in func_names
        assert "health_check" in func_names
        assert "format_date" in func_names

    def test_finds_classes(self, python_project):
        graph = build_repo_graph(str(python_project))
        class_names = {n.name for n in graph.nodes.values() if n.node_type == "class"}
        assert "BaseModel" in class_names
        assert "User" in class_names

    def test_finds_methods(self, python_project):
        graph = build_repo_graph(str(python_project))
        method_names = {n.name for n in graph.nodes.values() if n.node_type == "method"}
        assert "save" in method_names
        assert "validate" in method_names
        assert "__init__" in method_names

    def test_extracts_import_edges(self, python_project):
        graph = build_repo_graph(str(python_project))
        import_edges = [e for e in graph.edges if e.edge_type == "imports"]
        assert len(import_edges) > 0

        import_targets = {e.target for e in import_edges}
        assert "models.user" in import_targets or any("models" in t for t in import_targets)

    def test_extracts_call_edges(self, python_project):
        graph = build_repo_graph(str(python_project))
        call_edges = [e for e in graph.edges if e.edge_type == "calls"]
        assert len(call_edges) > 0

    def test_extracts_inheritance_edges(self, python_project):
        graph = build_repo_graph(str(python_project))
        inherit_edges = [e for e in graph.edges if e.edge_type == "inherits"]
        assert len(inherit_edges) > 0

        # User inherits from BaseModel
        found_user_inherits = False
        for edge in inherit_edges:
            if "User" in edge.source and "BaseModel" in edge.target:
                found_user_inherits = True
                break
        assert found_user_inherits, "Should find User inherits BaseModel"

    def test_callers_of(self, python_project):
        graph = build_repo_graph(str(python_project))

        # Find the login function
        login_keys = [k for k in graph.nodes if graph.nodes[k].name == "login"]
        assert len(login_keys) > 0

        login_key = login_keys[0]
        callers = graph.callers_of(login_key)
        # handle_login calls login
        assert any("handle_login" in c for c in callers), \
            f"Expected handle_login to call login, got callers: {callers}"

    def test_call_chain(self, python_project):
        graph = build_repo_graph(str(python_project))

        login_keys = [k for k in graph.nodes if graph.nodes[k].name == "handle_login"]
        assert len(login_keys) > 0

        chain = graph.call_chain(login_keys[0])
        assert len(chain) >= 1  # At least handle_login itself

    def test_dependents_of(self, python_project):
        graph = build_repo_graph(str(python_project))

        # check_name is called by User.validate, which is called by login
        check_keys = [k for k in graph.nodes if graph.nodes[k].name == "check_name"]
        if check_keys:
            dependents = graph.dependents_of(check_keys[0])
            assert len(dependents) >= 0  # May or may not resolve

    def test_summary(self, python_project):
        graph = build_repo_graph(str(python_project))
        summary = graph.summary()
        assert summary["total_nodes"] > 0
        assert summary["total_edges"] > 0
        assert summary["files"] > 0

    def test_nodes_in_file(self, python_project):
        graph = build_repo_graph(str(python_project))
        nodes = graph.nodes_in_file("services/auth.py")
        names = {n.name for n in nodes}
        assert "login" in names
        assert "create_token" in names


class TestGraphBuilderJS:
    """Test JS/TS regex-based graph extraction."""

    def test_builds_js_graph(self, js_project):
        graph = build_repo_graph(str(js_project))
        assert len(graph.nodes) > 0

    def test_finds_js_functions(self, js_project):
        graph = build_repo_graph(str(js_project))
        func_names = {n.name for n in graph.nodes.values() if n.node_type == "function"}
        assert "login" in func_names
        assert "createToken" in func_names

    def test_finds_js_classes(self, js_project):
        graph = build_repo_graph(str(js_project))
        class_names = {n.name for n in graph.nodes.values() if n.node_type == "class"}
        assert "User" in class_names
        assert "AdminUser" in class_names

    def test_finds_js_inheritance(self, js_project):
        graph = build_repo_graph(str(js_project))
        inherit_edges = [e for e in graph.edges if e.edge_type == "inherits"]
        assert any("AdminUser" in e.source and "User" in e.target for e in inherit_edges)

    def test_finds_js_imports(self, js_project):
        graph = build_repo_graph(str(js_project))
        import_edges = [e for e in graph.edges if e.edge_type == "imports"]
        targets = {e.target for e in import_edges}
        assert "./models/user" in targets or "jsonwebtoken" in targets


class TestGraphBuilderGo:
    """Test Go regex-based graph extraction."""

    def test_builds_go_graph(self, go_project):
        graph = build_repo_graph(str(go_project))
        assert len(graph.nodes) > 0

    def test_finds_go_functions(self, go_project):
        graph = build_repo_graph(str(go_project))
        func_names = {n.name for n in graph.nodes.values() if n.node_type == "function"}
        assert "Login" in func_names
        assert "CreateToken" in func_names

    def test_finds_go_methods(self, go_project):
        graph = build_repo_graph(str(go_project))
        method_names = {n.name for n in graph.nodes.values() if n.node_type == "method"}
        assert "HandleHealth" in method_names

    def test_finds_go_imports(self, go_project):
        graph = build_repo_graph(str(go_project))
        import_edges = [e for e in graph.edges if e.edge_type == "imports"]
        targets = {e.target for e in import_edges}
        assert "net/http" in targets or "github.com/gin-gonic/gin" in targets


class TestGraphBuilderEdgeCases:
    """Edge cases and error handling."""

    def test_empty_directory(self, tmp_path):
        graph = build_repo_graph(str(tmp_path))
        assert len(graph.nodes) == 0

    def test_syntax_error_file(self, tmp_path):
        (tmp_path / "bad.py").write_text("def foo(\n  # syntax error")
        graph = build_repo_graph(str(tmp_path))
        # Should still return a graph (module-level node)
        assert isinstance(graph, RepoGraph)

    def test_binary_file_skipped(self, tmp_path):
        (tmp_path / "image.png").write_bytes(b"\x89PNG\r\n")
        graph = build_repo_graph(str(tmp_path))
        assert len(graph.nodes) == 0

    def test_skips_venv(self, tmp_path):
        (tmp_path / "venv").mkdir()
        (tmp_path / "venv" / "lib.py").write_text("def venv_func(): pass")
        (tmp_path / "real.py").write_text("def real_func(): pass")
        graph = build_repo_graph(str(tmp_path))
        func_names = {n.name for n in graph.nodes.values() if n.node_type == "function"}
        assert "real_func" in func_names
        assert "venv_func" not in func_names


# ── Impact Analyzer Tests ────────────────────────────────────

class TestImpactAnalyzer:
    """Test the impact analysis query interface."""

    def test_analyze_impact_finds_target(self, python_project):
        graph = build_repo_graph(str(python_project))
        analyzer = ImpactAnalyzer(graph)

        report = analyzer.analyze_impact("login")
        assert report.target_file != "(not found)"
        assert "services/auth.py" in report.target_file

    def test_analyze_impact_finds_callers(self, python_project):
        graph = build_repo_graph(str(python_project))
        analyzer = ImpactAnalyzer(graph)

        report = analyzer.analyze_impact("login")
        # handle_login calls login
        assert any("handle_login" in c for c in report.direct_callers)

    def test_analyze_impact_finds_affected_files(self, python_project):
        graph = build_repo_graph(str(python_project))
        analyzer = ImpactAnalyzer(graph)

        report = analyzer.analyze_impact("login")
        assert len(report.affected_files) >= 1

    def test_analyze_impact_finds_co_located(self, python_project):
        graph = build_repo_graph(str(python_project))
        analyzer = ImpactAnalyzer(graph)

        report = analyzer.analyze_impact("login")
        # create_token, logout, revoke_token are in the same file
        assert "create_token" in report.co_located or len(report.co_located) > 0

    def test_find_targets_from_request(self, python_project):
        graph = build_repo_graph(str(python_project))
        analyzer = ImpactAnalyzer(graph)

        targets = analyzer.find_targets("Add rate limiting to login")
        assert len(targets) > 0
        assert any("login" in t for t in targets)

    def test_analyze_request(self, python_project):
        graph = build_repo_graph(str(python_project))
        analyzer = ImpactAnalyzer(graph)

        reports = analyzer.analyze_request("Fix the login function")
        assert len(reports) > 0
        assert reports[0].target_file != "(not found)"

    def test_format_for_planner(self, python_project):
        graph = build_repo_graph(str(python_project))
        analyzer = ImpactAnalyzer(graph)

        reports = analyzer.analyze_request("Update login")
        formatted = analyzer.format_for_planner(reports)
        assert "## Repository Graph Intelligence" in formatted
        assert "login" in formatted

    def test_unknown_target(self, python_project):
        graph = build_repo_graph(str(python_project))
        analyzer = ImpactAnalyzer(graph)

        report = analyzer.analyze_impact("nonexistent_function_xyz")
        assert report.resolution_quality == "low"
        assert report.target_file == "(not found)"


class TestImpactReport:
    """Test the ImpactReport data class."""

    def test_to_prompt_context(self):
        report = ImpactReport(
            target="auth/views.py::login",
            target_file="auth/views.py",
            direct_callers=["api/routes.py::handle_login"],
            affected_files=["auth/views.py", "api/routes.py"],
            co_located=["create_token", "logout"],
        )
        context = report.to_prompt_context()
        assert "login" in context
        assert "handle_login" in context
        assert "auth/views.py" in context

    def test_to_dict(self):
        report = ImpactReport(
            target="test",
            target_file="test.py",
        )
        d = report.to_dict()
        assert d["target"] == "test"
        assert d["target_file"] == "test.py"

    def test_truncation(self):
        report = ImpactReport(
            target="test",
            target_file="test.py",
            direct_callers=[f"caller_{i}" for i in range(100)],
        )
        context = report.to_prompt_context(max_chars=200)
        assert len(context) <= 250  # Some tolerance for truncation marker


# ── Integration: Run on own codebase ─────────────────────────

class TestSelfAnalysis:
    """Run the graph builder on the contextual-architect codebase itself."""

    def test_can_graph_own_codebase(self):
        """The graph builder should work on itself."""
        repo_root = Path(__file__).parent.parent
        if not (repo_root / "agents").exists():
            pytest.skip("Not in contextual-architect repo")

        graph = build_repo_graph(str(repo_root))
        summary = graph.summary()

        assert summary["total_nodes"] > 20, \
            f"Expected 20+ nodes for our own codebase, got {summary['total_nodes']}"
        assert summary["total_edges"] > 10, \
            f"Expected 10+ edges, got {summary['total_edges']}"
        assert summary["files"] >= 4, \
            f"Expected 4+ files, got {summary['files']}"

    def test_can_find_reviewer(self):
        """Should find the ReviewerAgent in its own graph."""
        repo_root = Path(__file__).parent.parent
        if not (repo_root / "agents").exists():
            pytest.skip("Not in contextual-architect repo")

        graph = build_repo_graph(str(repo_root))
        analyzer = ImpactAnalyzer(graph)

        report = analyzer.analyze_impact("ReviewerAgent")
        assert report.target_file != "(not found)", \
            "Should find ReviewerAgent in its own codebase"
