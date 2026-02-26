"""
High-level retriever interface — agents call THIS, not vector_store directly.

Historian calls:  retriever.find_patterns("FastAPI endpoint with auth")
Planner calls:   retriever.find_similar_tasks("add health check endpoint")
Architect calls: retriever.find_by_file("app/routers/users.py")
"""

import logging
from typing import Optional

from rag.vector_store import VectorStore

logger = logging.getLogger(__name__)


class CodeRetriever:
    """
    Search interface for RAG. Wraps the vector store with
    domain-specific query methods for each agent.
    """

    def __init__(self, store: VectorStore):
        self.store = store

    @property
    def indexed_count(self) -> int:
        """Number of chunks in the index."""
        return self.store.count()

    # ─── Agent-Specific Methods ──────────────────────────────

    def find_patterns(self, query: str, k: int = 8) -> list[dict]:
        """
        Historian uses this — find conventions and patterns.

        Returns code chunks most similar to the query, ranked by relevance.
        Each result has: text, metadata (file_path, symbol_name, etc.), relevance.
        """
        results = self.store.search(query, k=k)
        logger.debug(f"find_patterns('{query[:50]}...') -> {len(results)} results")
        return results

    def find_similar_tasks(self, task_description: str, k: int = 5) -> list[dict]:
        """
        Planner uses this — find similar past implementations.

        Searches for code that resembles the described task.
        """
        results = self.store.search(task_description, k=k)
        logger.debug(
            f"find_similar_tasks('{task_description[:50]}...') -> {len(results)} results"
        )
        return results

    def find_by_symbol(self, symbol_name: str, k: int = 5) -> list[dict]:
        """
        Find chunks by function/class name.

        Useful for Architect when mapping dependencies.
        """
        # Search with both text query and metadata filter
        results = self.store.search(
            query=symbol_name,
            k=k,
        )
        # Post-filter: boost exact symbol name matches
        exact = [r for r in results if r["metadata"].get("symbol_name") == symbol_name]
        fuzzy = [r for r in results if r["metadata"].get("symbol_name") != symbol_name]
        return exact + fuzzy

    def find_by_file(self, file_path: str, k: int = 10) -> list[dict]:
        """
        Get all chunks from a specific file.

        Architect uses this to understand a file's structure.
        """
        try:
            return self.store.search(
                query=file_path,
                k=k,
                filters={"file_path": file_path},
            )
        except Exception:
            # Some vector stores don't support metadata filtering well
            results = self.store.search(query=f"file: {file_path}", k=k)
            return [r for r in results if file_path in r["metadata"].get("file_path", "")]

    def find_related(self, code_snippet: str, k: int = 5) -> list[dict]:
        """
        Find code similar to a given snippet.

        Implementer uses this to find examples of similar patterns.
        """
        return self.store.search(query=code_snippet, k=k)

    # ─── Formatted Output for Agent Prompts ──────────────────

    def format_for_prompt(self, results: list[dict], max_chars: int = 4000) -> str:
        """
        Format search results as a string suitable for LLM prompts.

        Includes file path, symbol name, relevance score, and code.
        Truncates to stay within token budget.
        """
        if not results:
            return "No relevant patterns found in the codebase."

        lines = ["## Relevant Code Patterns (from RAG)\n"]
        total_chars = 0

        for i, r in enumerate(results, 1):
            meta = r.get("metadata", {})
            relevance = r.get("relevance", 0)
            text = r.get("text", "")

            header = (
                f"### Pattern {i}: {meta.get('symbol_name', 'unknown')} "
                f"({meta.get('file_path', '?')}) "
                f"[relevance: {relevance:.2f}]\n"
            )
            block = f"```{meta.get('language', '')}\n{text}\n```\n\n"
            entry = header + block

            if total_chars + len(entry) > max_chars:
                lines.append(f"\n... ({len(results) - i + 1} more results truncated)")
                break

            lines.append(entry)
            total_chars += len(entry)

        return "".join(lines)
