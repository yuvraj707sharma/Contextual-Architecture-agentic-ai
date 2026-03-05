"""
Impact Analyzer — High-level query interface over the Repository Graph.

This is what the Orchestrator and Planner actually call. It translates
natural-language-like queries into graph operations and formats results
for LLM prompts.

Usage:
    from agents.graph_builder import build_repo_graph
    from agents.impact_analyzer import ImpactAnalyzer

    graph = build_repo_graph("./my-project")
    analyzer = ImpactAnalyzer(graph)

    # "Add rate limiting to login"
    impact = analyzer.analyze_impact("login", request="Add rate limiting to login")
    print(impact.to_prompt_context())
    # → login is in auth/views.py, called by api/routes.py,
    #   which imports auth/middleware.py. Modify all 3 files.
"""

import logging
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set

from .graph_builder import RepoGraph, CodeNode

logger = logging.getLogger(__name__)


# ── Impact Report ────────────────────────────────────────────

@dataclass
class ImpactReport:
    """Result of an impact analysis query.

    This is what gets injected into the Planner's context —
    it tells the LLM exactly which files need to change and why.
    """

    # The target symbol that was analyzed
    target: str

    # The file where the target lives
    target_file: str

    # Files that will likely need modification
    affected_files: List[str] = field(default_factory=list)

    # Direct callers of the target
    direct_callers: List[str] = field(default_factory=list)

    # Full call chain from the target downward
    call_chain: List[str] = field(default_factory=list)

    # Files that import from the target's file
    importing_files: List[str] = field(default_factory=list)

    # Co-located symbols (other functions in the same file)
    co_located: List[str] = field(default_factory=list)

    # Related decorators (e.g., @app.route, @login_required)
    decorators: List[str] = field(default_factory=list)

    # Inheritance chain (if target is a class)
    inherits_from: List[str] = field(default_factory=list)
    inherited_by: List[str] = field(default_factory=list)

    # Confidence: how well did the graph resolve?
    resolution_quality: str = "high"  # "high", "medium", "low"

    def to_dict(self) -> dict:
        return {
            "target": self.target,
            "target_file": self.target_file,
            "affected_files": self.affected_files,
            "direct_callers": self.direct_callers,
            "call_chain": self.call_chain,
            "importing_files": self.importing_files,
            "co_located": self.co_located,
            "decorators": self.decorators,
            "inherits_from": self.inherits_from,
            "inherited_by": self.inherited_by,
            "resolution_quality": self.resolution_quality,
        }

    def to_prompt_context(self, max_chars: int = 3000) -> str:
        """Format for injection into LLM prompts.

        Designed to be concise but complete — the Planner needs
        to know WHAT to change and WHERE, not the graph theory.
        """
        parts = []

        parts.append("## Code Graph Analysis\n")

        # Target
        parts.append(f"**Target:** `{self.target}` in `{self.target_file}`")

        # Decorators (important for understanding the role of the function)
        if self.decorators:
            dec_str = ", ".join(f"`@{d}`" for d in self.decorators)
            parts.append(f"**Decorators:** {dec_str}")

        # Direct callers — most important for impact assessment
        if self.direct_callers:
            parts.append(f"\n**Called by** ({len(self.direct_callers)}):")
            for caller in self.direct_callers[:5]:
                parts.append(f"  - `{caller}`")
            if len(self.direct_callers) > 5:
                parts.append(f"  - _...and {len(self.direct_callers) - 5} more_")

        # Call chain
        if len(self.call_chain) > 1:
            parts.append(f"\n**Calls** ({len(self.call_chain) - 1} downstream):")
            for callee in self.call_chain[1:5]:  # Skip self, show first 4
                parts.append(f"  - `{callee}`")
            if len(self.call_chain) > 5:
                parts.append(f"  - _...and {len(self.call_chain) - 5} more_")

        # Affected files — the most actionable piece
        if self.affected_files:
            parts.append(f"\n**Files that may need changes** ({len(self.affected_files)}):")
            for f in self.affected_files[:8]:
                parts.append(f"  - `{f}`")
            if len(self.affected_files) > 8:
                parts.append(f"  - _...and {len(self.affected_files) - 8} more_")

        # Importing files
        if self.importing_files:
            parts.append(f"\n**Files importing from `{self.target_file}`:**")
            for f in self.importing_files[:5]:
                parts.append(f"  - `{f}`")

        # Co-located symbols (others in the same file)
        if self.co_located:
            parts.append(f"\n**Also in `{self.target_file}`:**")
            for sym in self.co_located[:5]:
                parts.append(f"  - `{sym}`")

        # Inheritance
        if self.inherits_from:
            parts.append(f"\n**Inherits from:** {', '.join(f'`{c}`' for c in self.inherits_from)}")
        if self.inherited_by:
            parts.append(f"\n**Inherited by:** {', '.join(f'`{c}`' for c in self.inherited_by)}")

        # Resolution quality warning
        if self.resolution_quality != "high":
            parts.append(
                f"\n> ⚠️ Graph resolution: **{self.resolution_quality}** — "
                "some relationships may be missing."
            )

        result = "\n".join(parts)

        # Truncate if needed
        if len(result) > max_chars:
            result = result[:max_chars - 50] + "\n\n_...truncated for token budget_"

        return result


# ── Impact Analyzer ──────────────────────────────────────────

class ImpactAnalyzer:
    """High-level query interface over the repo graph.

    Translates requests like "Add rate limiting to login" into
    concrete impact analysis: which files, which functions,
    which callers need attention.
    """

    def __init__(self, graph: RepoGraph):
        self.graph = graph

    def analyze_impact(
        self,
        target_name: str,
        request: str = "",
        max_depth: int = 5,
    ) -> ImpactReport:
        """Full impact analysis for a target symbol.

        Args:
            target_name: Function/class name to analyze (e.g., "login",
                         "UserService", or fully qualified "auth/views.py::login")
            request: The user's original request (helps with context)
            max_depth: Max depth for call chain traversal

        Returns:
            ImpactReport with all affected files, callers, and call chains
        """
        # Resolve target to a graph node
        node, key = self._resolve_target(target_name, request)

        if not node:
            return ImpactReport(
                target=target_name,
                target_file="(not found)",
                resolution_quality="low",
            )

        report = ImpactReport(
            target=key,
            target_file=node.file_path,
            decorators=node.decorators,
        )

        # Direct callers
        report.direct_callers = self.graph.callers_of(key)

        # Call chain (forward)
        report.call_chain = self.graph.call_chain(key, max_depth=max_depth)

        # Files importing from target's file
        report.importing_files = self.graph.files_importing(node.file_path)

        # Co-located symbols
        co_located_nodes = self.graph.nodes_in_file(node.file_path)
        report.co_located = [
            n.name for n in co_located_nodes
            if n.key != key and n.node_type != "module"
        ]

        # Inheritance
        if node.node_type == "class":
            report.inherits_from, report.inherited_by = self._get_inheritance(key)

        # Affected files (aggregate unique files from all impacts)
        affected = set()
        affected.add(node.file_path)

        for caller_key in report.direct_callers:
            caller_node = self.graph.nodes.get(caller_key)
            if caller_node:
                affected.add(caller_node.file_path)

        for chain_key in report.call_chain:
            chain_node = self.graph.nodes.get(chain_key)
            if chain_node:
                affected.add(chain_node.file_path)

        for imp_file in report.importing_files:
            affected.add(imp_file)

        report.affected_files = sorted(affected)

        # Resolution quality
        total_edges = len(self.graph.edges)
        resolved = sum(1 for e in self.graph.edges if e.resolved)
        if total_edges == 0:
            report.resolution_quality = "low"
        elif resolved / total_edges > 0.7:
            report.resolution_quality = "high"
        elif resolved / total_edges > 0.4:
            report.resolution_quality = "medium"
        else:
            report.resolution_quality = "low"

        return report

    def find_targets(self, request: str) -> List[str]:
        """Extract likely target symbols from a user request.

        "Add rate limiting to login" → ["login"]
        "Update the UserService to support pagination" → ["UserService"]
        "Fix the auth middleware" → ["auth", "middleware"]
        """
        # Extract words that could be symbol names
        # (PascalCase, snake_case, camelCase — not regular English)
        words = request.split()
        candidates = []

        for word in words:
            clean = re.sub(r"[^a-zA-Z0-9_]", "", word)
            if not clean or len(clean) < 3:
                continue

            # Skip common English verbs/articles
            skip = {
                "add", "create", "build", "implement", "make", "write",
                "fix", "update", "modify", "refactor", "the", "and",
                "for", "from", "with", "that", "this", "new", "old",
                "should", "must", "will", "can", "need", "want",
                "support", "handle", "process", "return", "function",
            }
            if clean.lower() in skip:
                continue

            # Check if this word matches any node in the graph
            for node_key, node in self.graph.nodes.items():
                if node.node_type == "module":
                    continue
                if (clean == node.name or
                    clean.lower() == node.name.lower() or
                    clean.lower() in node.name.lower()):
                    candidates.append(node_key)
                    break

        return candidates

    def analyze_request(
        self,
        request: str,
        max_targets: int = 3,
        max_depth: int = 5,
    ) -> List[ImpactReport]:
        """Analyze a full user request, finding all relevant targets.

        This is the main entry point for the Orchestrator:
            reports = analyzer.analyze_request("Add rate limiting to login")
            for report in reports:
                planner_context += report.to_prompt_context()
        """
        targets = self.find_targets(request)

        if not targets:
            logger.info(f"No graph targets found for: {request[:60]}")
            return []

        # Deduplicate by file (don't analyze 5 functions in the same file)
        seen_files: Set[str] = set()
        unique_targets = []
        for target in targets:
            node = self.graph.nodes.get(target)
            if node and node.file_path not in seen_files:
                seen_files.add(node.file_path)
                unique_targets.append(target)

        reports = []
        for target_key in unique_targets[:max_targets]:
            node = self.graph.nodes.get(target_key)
            if node:
                report = self.analyze_impact(
                    node.name, request=request, max_depth=max_depth
                )
                reports.append(report)

        return reports

    def format_for_planner(
        self,
        reports: List[ImpactReport],
        max_chars: int = 4000,
    ) -> str:
        """Format multiple impact reports as a single prompt section.

        Designed for injection into the Planner's context window.
        """
        if not reports:
            return ""

        parts = ["## Repository Graph Intelligence\n"]
        parts.append(
            "_The following analysis was generated from the code graph, "
            "not from the LLM. These are deterministic facts about the codebase._\n"
        )

        total_chars = 0
        for report in reports:
            section = report.to_prompt_context(max_chars=max_chars // len(reports))
            if total_chars + len(section) > max_chars:
                parts.append("\n_...additional reports truncated for token budget_")
                break
            parts.append(section)
            parts.append("")  # blank line between reports
            total_chars += len(section)

        return "\n".join(parts)

    def _resolve_target(
        self, target_name: str, request: str = ""
    ) -> tuple:
        """Resolve a target name to a graph node and key.

        Tries in order:
        1. Exact key match (e.g., "auth/views.py::login")
        2. Exact name match (e.g., "login")
        3. Partial name match (e.g., "log" matches "login")
        4. Request keyword matching
        """
        # 1. Exact key
        if target_name in self.graph.nodes:
            return self.graph.nodes[target_name], target_name

        # 2. Exact name match
        candidates = []
        for key, node in self.graph.nodes.items():
            if node.node_type == "module":
                continue
            if node.name == target_name:
                candidates.append((key, node))

        if len(candidates) == 1:
            return candidates[0][1], candidates[0][0]

        # If multiple matches, use request keywords to disambiguate
        if candidates and request:
            req_lower = request.lower()
            best_score = -1
            best = None
            for key, node in candidates:
                score = sum(
                    1 for word in req_lower.split()
                    if word in node.file_path.lower() or word in key.lower()
                )
                if score > best_score:
                    best_score = score
                    best = (key, node)
            if best:
                return best[1], best[0]

        if candidates:
            return candidates[0][1], candidates[0][0]

        # 3. Partial name match
        for key, node in self.graph.nodes.items():
            if node.node_type == "module":
                continue
            if target_name.lower() in node.name.lower():
                return node, key

        return None, ""

    def _get_inheritance(self, class_key: str) -> tuple:
        """Get inheritance relationships for a class."""
        inherits_from = []
        inherited_by = []

        for edge in self.graph.edges:
            if edge.edge_type == "inherits":
                if edge.source == class_key:
                    inherits_from.append(edge.target)
                elif edge.target == class_key:
                    inherited_by.append(edge.source)

        return inherits_from, inherited_by
