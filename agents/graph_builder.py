"""
Repository Knowledge Graph — AST-based code relationship extraction.

Extends what code_chunker.py does: same ast.parse(), but extracts
EDGES (calls, imports, inheritance) instead of just NODES (function text).

This is MACRO's technical moat. No open-source CLI coding tool builds
a deterministic call graph and feeds it to LLM planning.

Usage:
    builder = GraphBuilder("./my-project")
    graph = builder.build()

    # Who calls login()?
    graph.callers_of("auth/views.py::login")

    # What breaks if I change UserService?
    graph.dependents_of("services/user.py::UserService")

    # Full call chain from an endpoint
    graph.call_chain("api/routes.py::handle_request")

Supported languages:
    - Python: Full AST analysis (imports, calls, inheritance, decorators)
    - JS/TS:  Regex-based import + call extraction
    - Go:     Regex-based import + call extraction
"""

import ast
import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Set, Tuple

logger = logging.getLogger(__name__)


# ── Skip lists (shared with code_chunker / indexer) ──────────

SKIP_DIRS = {
    ".git", ".svn", "node_modules", "__pycache__", ".mypy_cache",
    ".pytest_cache", "venv", ".venv", "env", ".env", "dist", "build",
    ".contextual-architect", ".tox", ".eggs", "chroma_db", ".chroma",
    "vendor", ".next",
}

SUPPORTED_EXTENSIONS = {".py", ".js", ".ts", ".tsx", ".jsx", ".go"}

MAX_FILE_SIZE = 200_000  # 200KB — skip generated/vendored files


# ── Data Model ───────────────────────────────────────────────

@dataclass
class CodeNode:
    """A function, class, or module in the graph."""

    # Unique key: "relative/path.py::symbol_name"
    key: str

    # Human-readable name
    name: str

    # File this node lives in (relative to repo root)
    file_path: str

    # "function", "class", "method", "module"
    node_type: str

    # Line range in the source file
    line_start: int = 0
    line_end: int = 0

    # Decorators (useful for detecting @app.route, @login_required, etc.)
    decorators: List[str] = field(default_factory=list)

    # Parent class (for methods)
    parent_class: str = ""

    def to_dict(self) -> dict:
        return {
            "key": self.key,
            "name": self.name,
            "file_path": self.file_path,
            "node_type": self.node_type,
            "line_start": self.line_start,
            "line_end": self.line_end,
            "decorators": self.decorators,
            "parent_class": self.parent_class,
        }


@dataclass
class CodeEdge:
    """A relationship between two code nodes."""

    # Source node key
    source: str

    # Target node key (or unresolved name)
    target: str

    # "calls", "imports", "inherits", "decorates"
    edge_type: str

    # Whether target was resolved to an actual node in the graph
    resolved: bool = False

    def to_dict(self) -> dict:
        return {
            "source": self.source,
            "target": self.target,
            "edge_type": self.edge_type,
            "resolved": self.resolved,
        }


@dataclass
class RepoGraph:
    """The complete repository knowledge graph.

    Nodes = functions, classes, methods, modules
    Edges = calls, imports, inheritance relationships

    This is an in-memory graph — fast to build, fast to query.
    Not persisted to disk (rebuilt on each scan, takes <1s for most repos).
    """

    nodes: Dict[str, CodeNode] = field(default_factory=dict)
    edges: List[CodeEdge] = field(default_factory=list)

    # Pre-built indexes for fast lookups
    _callers: Dict[str, Set[str]] = field(default_factory=dict)
    _callees: Dict[str, Set[str]] = field(default_factory=dict)
    _importers: Dict[str, Set[str]] = field(default_factory=dict)
    _file_nodes: Dict[str, List[str]] = field(default_factory=dict)

    def build_indexes(self) -> None:
        """Build reverse-lookup indexes after all edges are added."""
        self._callers.clear()
        self._callees.clear()
        self._importers.clear()
        self._file_nodes.clear()

        for edge in self.edges:
            if edge.edge_type == "calls":
                self._callees.setdefault(edge.source, set()).add(edge.target)
                self._callers.setdefault(edge.target, set()).add(edge.source)
            elif edge.edge_type == "imports":
                self._importers.setdefault(edge.target, set()).add(edge.source)

        for key, node in self.nodes.items():
            self._file_nodes.setdefault(node.file_path, []).append(key)

    # ── Query Methods ────────────────────────────────────────

    def callers_of(self, node_key: str) -> List[str]:
        """Who calls this function/method? (reverse call graph)"""
        return sorted(self._callers.get(node_key, set()))

    def callees_of(self, node_key: str) -> List[str]:
        """What does this function call? (forward call graph)"""
        return sorted(self._callees.get(node_key, set()))

    def dependents_of(self, node_key: str) -> List[str]:
        """Transitive closure: everything that depends on this node.

        If you change node_key, these are ALL the things that might break.
        BFS traversal of the reverse call + import graph.
        """
        visited: Set[str] = set()
        queue = [node_key]

        while queue:
            current = queue.pop(0)
            if current in visited:
                continue
            visited.add(current)

            # Add callers
            for caller in self._callers.get(current, set()):
                if caller not in visited:
                    queue.append(caller)

            # Add importers (file-level)
            node = self.nodes.get(current)
            if node:
                for importer in self._importers.get(node.file_path, set()):
                    if importer not in visited:
                        queue.append(importer)

        visited.discard(node_key)  # Don't include self
        return sorted(visited)

    def call_chain(self, node_key: str, max_depth: int = 10) -> List[str]:
        """Full call chain FROM this function downward.

        Shows what this function triggers — useful for understanding
        the blast radius of a change.
        """
        chain: List[str] = []
        visited: Set[str] = set()
        queue: List[Tuple[str, int]] = [(node_key, 0)]

        while queue:
            current, depth = queue.pop(0)
            if current in visited or depth > max_depth:
                continue
            visited.add(current)
            chain.append(current)

            for callee in self._callees.get(current, set()):
                if callee not in visited:
                    queue.append((callee, depth + 1))

        return chain

    def files_importing(self, file_path: str) -> List[str]:
        """Which files import from this file?

        Used by Planner: "If I change this file, which other files
        might need updates?"
        """
        importers = set()
        for edge in self.edges:
            if edge.edge_type == "imports" and edge.target == file_path:
                # Find the file of the source node
                source_node = self.nodes.get(edge.source)
                if source_node:
                    importers.add(source_node.file_path)
        return sorted(importers)

    def nodes_in_file(self, file_path: str) -> List[CodeNode]:
        """All functions/classes defined in a file."""
        keys = self._file_nodes.get(file_path, [])
        return [self.nodes[k] for k in keys if k in self.nodes]

    def summary(self) -> dict:
        """Quick stats for logging/display."""
        edge_types = {}
        for edge in self.edges:
            edge_types[edge.edge_type] = edge_types.get(edge.edge_type, 0) + 1

        return {
            "total_nodes": len(self.nodes),
            "total_edges": len(self.edges),
            "edge_types": edge_types,
            "files": len(self._file_nodes),
            "functions": sum(1 for n in self.nodes.values() if n.node_type == "function"),
            "classes": sum(1 for n in self.nodes.values() if n.node_type == "class"),
            "methods": sum(1 for n in self.nodes.values() if n.node_type == "method"),
        }

    def to_dict(self) -> dict:
        """Serialize for JSON output / debugging."""
        return {
            "nodes": {k: v.to_dict() for k, v in self.nodes.items()},
            "edges": [e.to_dict() for e in self.edges],
            "summary": self.summary(),
        }


# ── Python AST Visitor ───────────────────────────────────────

class _PythonGraphVisitor(ast.NodeVisitor):
    """Extract nodes and edges from a Python AST.

    Walks the AST once, extracting:
    - Function/class/method definitions → nodes
    - Function calls → call edges
    - Import statements → import edges
    - Class inheritance → inheritance edges
    - Decorator usage → decorator edges
    """

    def __init__(self, file_path: str, source: str):
        self.file_path = file_path
        self.source = source
        self.nodes: List[CodeNode] = []
        self.edges: List[CodeEdge] = []

        # State tracking during traversal
        self._current_scope: List[str] = []  # Stack of enclosing scopes
        self._module_key = f"{file_path}::module"

    def _scope_key(self, name: str) -> str:
        """Build a fully qualified key for a symbol."""
        if self._current_scope:
            parent = self._current_scope[-1]
            return f"{self.file_path}::{parent}.{name}"
        return f"{self.file_path}::{name}"

    def _current_key(self) -> str:
        """Key of the innermost enclosing scope."""
        if self._current_scope:
            return f"{self.file_path}::{self._current_scope[-1]}"
        return self._module_key

    def _extract_decorators(self, node) -> List[str]:
        """Extract decorator names from a function/class."""
        decorators = []
        for dec in node.decorator_list:
            if isinstance(dec, ast.Name):
                decorators.append(dec.id)
            elif isinstance(dec, ast.Attribute):
                decorators.append(f"{self._attr_chain(dec)}")
            elif isinstance(dec, ast.Call):
                if isinstance(dec.func, ast.Name):
                    decorators.append(dec.func.id)
                elif isinstance(dec.func, ast.Attribute):
                    decorators.append(self._attr_chain(dec.func))
        return decorators

    def _attr_chain(self, node) -> str:
        """Resolve a.b.c attribute chain to a dotted string."""
        parts = []
        current = node
        while isinstance(current, ast.Attribute):
            parts.append(current.attr)
            current = current.value
        if isinstance(current, ast.Name):
            parts.append(current.id)
        return ".".join(reversed(parts))

    def visit_Module(self, node):
        """Register the module itself as a node."""
        self.nodes.append(CodeNode(
            key=self._module_key,
            name=self.file_path,
            file_path=self.file_path,
            node_type="module",
            line_start=1,
            line_end=len(self.source.splitlines()),
        ))
        self.generic_visit(node)

    def visit_Import(self, node):
        """import foo, bar → import edges from module to each imported name."""
        for alias in node.names:
            self.edges.append(CodeEdge(
                source=self._current_key(),
                target=alias.name,
                edge_type="imports",
            ))
        self.generic_visit(node)

    def visit_ImportFrom(self, node):
        """from foo.bar import baz → import edge to foo.bar."""
        if node.module:
            self.edges.append(CodeEdge(
                source=self._current_key(),
                target=node.module,
                edge_type="imports",
            ))
        self.generic_visit(node)

    def visit_ClassDef(self, node):
        """Register class as a node + inheritance edges."""
        key = self._scope_key(node.name)
        decorators = self._extract_decorators(node)

        self.nodes.append(CodeNode(
            key=key,
            name=node.name,
            file_path=self.file_path,
            node_type="class",
            line_start=node.lineno,
            line_end=node.end_lineno or node.lineno,
            decorators=decorators,
        ))

        # Inheritance edges
        for base in node.bases:
            if isinstance(base, ast.Name):
                self.edges.append(CodeEdge(
                    source=key,
                    target=base.id,
                    edge_type="inherits",
                ))
            elif isinstance(base, ast.Attribute):
                self.edges.append(CodeEdge(
                    source=key,
                    target=self._attr_chain(base),
                    edge_type="inherits",
                ))

        # Traverse methods within class scope
        self._current_scope.append(node.name)
        self.generic_visit(node)
        self._current_scope.pop()

    def visit_FunctionDef(self, node):
        """Register function/method as a node."""
        is_method = len(self._current_scope) > 0
        key = self._scope_key(node.name)
        decorators = self._extract_decorators(node)
        parent = self._current_scope[-1] if self._current_scope else ""

        self.nodes.append(CodeNode(
            key=key,
            name=node.name,
            file_path=self.file_path,
            node_type="method" if is_method else "function",
            line_start=node.lineno,
            line_end=node.end_lineno or node.lineno,
            decorators=decorators,
            parent_class=parent,
        ))

        # Traverse body within function scope
        self._current_scope.append(node.name)
        self.generic_visit(node)
        self._current_scope.pop()

    # Handle async functions identically
    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_Call(self, node):
        """Register call edges."""
        caller = self._current_key()

        if isinstance(node.func, ast.Name):
            # Direct call: foo()
            self.edges.append(CodeEdge(
                source=caller,
                target=node.func.id,
                edge_type="calls",
            ))
        elif isinstance(node.func, ast.Attribute):
            # Method call: obj.method()
            self.edges.append(CodeEdge(
                source=caller,
                target=node.func.attr,
                edge_type="calls",
            ))

        self.generic_visit(node)


# ── JS/TS Regex Extractor ────────────────────────────────────

# Import patterns
_JS_IMPORT_RE = re.compile(
    r"""(?:import\s+(?:{[^}]+}|\w+)\s+from\s+['"]([^'"]+)['"]"""
    r"""|require\s*\(\s*['"]([^'"]+)['"]\s*\))""",
    re.MULTILINE,
)

# Function definitions
_JS_FUNC_DEF_RE = re.compile(
    r"(?:export\s+)?(?:async\s+)?function\s+(\w+)\s*\(",
    re.MULTILINE,
)

# Arrow functions assigned to const/let/var
_JS_ARROW_RE = re.compile(
    r"(?:export\s+)?(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s+)?(?:\([^)]*\)|[\w]+)\s*=>",
    re.MULTILINE,
)

# Class definitions
_JS_CLASS_DEF_RE = re.compile(
    r"(?:export\s+)?class\s+(\w+)(?:\s+extends\s+(\w+))?",
    re.MULTILINE,
)

# Function calls (simple: name(...))
_JS_CALL_RE = re.compile(
    r"(?<![.\w])(\w+)\s*\(",
    re.MULTILINE,
)


def _extract_js_graph(
    source: str, file_path: str
) -> Tuple[List[CodeNode], List[CodeEdge]]:
    """Regex-based graph extraction for JS/TS files."""
    nodes: List[CodeNode] = []
    edges: List[CodeEdge] = []
    module_key = f"{file_path}::module"

    nodes.append(CodeNode(
        key=module_key,
        name=file_path,
        file_path=file_path,
        node_type="module",
    ))

    # Imports
    for match in _JS_IMPORT_RE.finditer(source):
        target = match.group(1) or match.group(2)
        edges.append(CodeEdge(
            source=module_key,
            target=target,
            edge_type="imports",
        ))

    # Functions
    for match in _JS_FUNC_DEF_RE.finditer(source):
        name = match.group(1)
        key = f"{file_path}::{name}"
        line = source[:match.start()].count("\n") + 1
        nodes.append(CodeNode(
            key=key, name=name, file_path=file_path,
            node_type="function", line_start=line,
        ))

    # Arrow functions
    for match in _JS_ARROW_RE.finditer(source):
        name = match.group(1)
        key = f"{file_path}::{name}"
        line = source[:match.start()].count("\n") + 1
        nodes.append(CodeNode(
            key=key, name=name, file_path=file_path,
            node_type="function", line_start=line,
        ))

    # Classes
    for match in _JS_CLASS_DEF_RE.finditer(source):
        name = match.group(1)
        base = match.group(2)
        key = f"{file_path}::{name}"
        line = source[:match.start()].count("\n") + 1
        nodes.append(CodeNode(
            key=key, name=name, file_path=file_path,
            node_type="class", line_start=line,
        ))
        if base:
            edges.append(CodeEdge(
                source=key, target=base, edge_type="inherits",
            ))

    return nodes, edges


# ── Go Regex Extractor ───────────────────────────────────────

_GO_IMPORT_RE = re.compile(
    r"""(?:import\s+"([^"]+)"|import\s+\([^)]*?"([^"]+)"[^)]*\))""",
    re.DOTALL,
)

_GO_FUNC_DEF_RE = re.compile(
    r"^func\s+(?:\((\w+)\s+\*?(\w+)\)\s+)?(\w+)\s*\(",
    re.MULTILINE,
)


def _extract_go_graph(
    source: str, file_path: str
) -> Tuple[List[CodeNode], List[CodeEdge]]:
    """Regex-based graph extraction for Go files."""
    nodes: List[CodeNode] = []
    edges: List[CodeEdge] = []
    module_key = f"{file_path}::module"

    nodes.append(CodeNode(
        key=module_key,
        name=file_path,
        file_path=file_path,
        node_type="module",
    ))

    # Imports
    for match in _GO_IMPORT_RE.finditer(source):
        target = match.group(1) or match.group(2)
        if target:
            edges.append(CodeEdge(
                source=module_key,
                target=target,
                edge_type="imports",
            ))

    # Functions
    for match in _GO_FUNC_DEF_RE.finditer(source):
        receiver_type = match.group(2)
        func_name = match.group(3)
        line = source[:match.start()].count("\n") + 1

        if receiver_type:
            # Method: func (s *Server) Handle()
            key = f"{file_path}::{receiver_type}.{func_name}"
            nodes.append(CodeNode(
                key=key, name=func_name, file_path=file_path,
                node_type="method", line_start=line,
                parent_class=receiver_type,
            ))
        else:
            key = f"{file_path}::{func_name}"
            nodes.append(CodeNode(
                key=key, name=func_name, file_path=file_path,
                node_type="function", line_start=line,
            ))

    return nodes, edges


# ── Graph Builder ────────────────────────────────────────────

class GraphBuilder:
    """Build a repository knowledge graph from source files.

    Scans all supported files in a repo directory, parses each one
    to extract nodes (functions, classes) and edges (calls, imports,
    inheritance), and assembles them into a queryable RepoGraph.

    Usage:
        builder = GraphBuilder("./my-project")
        graph = builder.build()
        print(graph.summary())
    """

    def __init__(self, repo_path: str, max_files: int = 1000):
        self.repo_path = Path(repo_path).resolve()
        self.max_files = max_files

    def build(self) -> RepoGraph:
        """Scan the repository and build the graph."""
        graph = RepoGraph()
        files_scanned = 0
        errors = 0

        for file_path in self._walk_files():
            if files_scanned >= self.max_files:
                logger.warning(
                    f"Hit max_files limit ({self.max_files}). "
                    "Increase max_files for larger repos."
                )
                break

            files_scanned += 1

            try:
                source = file_path.read_text(encoding="utf-8", errors="replace")
            except OSError as e:
                logger.debug(f"Can't read {file_path}: {e}")
                errors += 1
                continue

            rel_path = str(file_path.relative_to(self.repo_path)).replace("\\", "/")
            ext = file_path.suffix.lower()

            try:
                if ext == ".py":
                    nodes, edges = self._parse_python(source, rel_path)
                elif ext in (".js", ".ts", ".tsx", ".jsx"):
                    nodes, edges = _extract_js_graph(source, rel_path)
                elif ext == ".go":
                    nodes, edges = _extract_go_graph(source, rel_path)
                else:
                    continue

                for node in nodes:
                    graph.nodes[node.key] = node
                graph.edges.extend(edges)

            except Exception as e:
                logger.debug(f"Failed to parse {rel_path}: {e}")
                errors += 1
                continue

        # Resolve edges: try to match target names to actual node keys
        self._resolve_edges(graph)

        # Build indexes for fast queries
        graph.build_indexes()

        logger.info(
            f"Graph built: {graph.summary()['total_nodes']} nodes, "
            f"{graph.summary()['total_edges']} edges from {files_scanned} files "
            f"({errors} errors)"
        )

        return graph

    def _parse_python(
        self, source: str, file_path: str
    ) -> Tuple[List[CodeNode], List[CodeEdge]]:
        """Parse a Python file using full AST analysis."""
        try:
            tree = ast.parse(source)
        except SyntaxError:
            # Can't parse — return module-level node only
            return [CodeNode(
                key=f"{file_path}::module",
                name=file_path,
                file_path=file_path,
                node_type="module",
            )], []

        visitor = _PythonGraphVisitor(file_path, source)
        visitor.visit(tree)
        return visitor.nodes, visitor.edges

    def _resolve_edges(self, graph: RepoGraph) -> None:
        """Try to resolve edge targets to actual node keys.

        When we see a call to "login()", we don't know which file's
        login() it refers to. This method tries to match unqualified
        names to node keys in the graph.
        """
        # Build a name → keys index for resolution
        name_index: Dict[str, List[str]] = {}
        for key, node in graph.nodes.items():
            name_index.setdefault(node.name, []).append(key)

        for edge in graph.edges:
            if edge.edge_type in ("calls", "inherits"):
                # Already a full key?
                if edge.target in graph.nodes:
                    edge.resolved = True
                    continue

                # Try to resolve by name
                candidates = name_index.get(edge.target, [])
                if len(candidates) == 1:
                    # Unambiguous match
                    edge.target = candidates[0]
                    edge.resolved = True
                elif len(candidates) > 1:
                    # Ambiguous — pick the one in the same file first
                    source_node = graph.nodes.get(edge.source)
                    if source_node:
                        same_file = [
                            c for c in candidates
                            if graph.nodes[c].file_path == source_node.file_path
                        ]
                        if same_file:
                            edge.target = same_file[0]
                            edge.resolved = True
                        else:
                            # Keep first candidate, mark as resolved
                            edge.target = candidates[0]
                            edge.resolved = True

            elif edge.edge_type == "imports":
                # Import targets are module paths — try to match to file paths
                target = edge.target
                # Python module path: foo.bar.baz → foo/bar/baz.py
                as_path = target.replace(".", "/") + ".py"
                as_package = target.replace(".", "/") + "/__init__.py"
                module_key_path = f"{as_path}::module"
                module_key_pkg = f"{as_package}::module"

                if module_key_path in graph.nodes:
                    edge.target = as_path
                    edge.resolved = True
                elif module_key_pkg in graph.nodes:
                    edge.target = as_package
                    edge.resolved = True

    def _walk_files(self):
        """Yield all supported source files in the repo."""
        for root, dirs, files in os.walk(self.repo_path):
            # Prune skip directories
            dirs[:] = [
                d for d in dirs
                if d not in SKIP_DIRS and not d.startswith(".")
            ]

            for fname in files:
                fpath = Path(root) / fname

                # Check extension
                if fpath.suffix.lower() not in SUPPORTED_EXTENSIONS:
                    continue

                # Skip large files
                try:
                    if fpath.stat().st_size > MAX_FILE_SIZE:
                        continue
                except OSError:
                    continue

                yield fpath


# ── Convenience Function ─────────────────────────────────────

def build_repo_graph(repo_path: str, max_files: int = 1000) -> RepoGraph:
    """One-liner to build a repo graph.

    Usage:
        from agents.graph_builder import build_repo_graph
        graph = build_repo_graph("./my-project")
        print(graph.dependents_of("auth/views.py::login"))
    """
    builder = GraphBuilder(repo_path, max_files=max_files)
    return builder.build()
