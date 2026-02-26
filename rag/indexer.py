"""
Incremental repo indexer — scans a project directory and indexes into ChromaDB.

Only indexes new/changed files (checks mtime against last index timestamp).
"""

import json
import logging
import os
import time
from pathlib import Path
from typing import Optional

from rag.code_chunker import chunk_file, detect_language
from rag.vector_store import VectorStore

logger = logging.getLogger(__name__)

# Files/dirs to always skip
SKIP_DIRS = {
    ".git", ".svn", "node_modules", "__pycache__", ".mypy_cache",
    ".pytest_cache", "venv", ".venv", "env", ".env", "dist", "build",
    ".contextual-architect", ".tox", ".eggs", "*.egg-info",
    "chroma_db", ".chroma",
}

SKIP_FILES = {
    ".gitignore", ".dockerignore", "LICENSE", "Makefile",
    "package-lock.json", "poetry.lock", "Pipfile.lock",
}

# Max file size to index (skip huge generated/vendored files)
MAX_FILE_SIZE = 100_000  # 100KB


class RepoIndexer:
    """
    Incrementally indexes a repository into a vector store.

    Usage:
        store = ChromaVectorStore("my-project")
        indexer = RepoIndexer(store, repo_path="./my-project", repo_name="my-project")
        stats = indexer.index()
        print(f"Indexed {stats['chunks_added']} chunks from {stats['files_scanned']} files")
    """

    def __init__(
        self,
        store: VectorStore,
        repo_path: str,
        repo_name: str,
    ):
        self.store = store
        self.repo_path = Path(repo_path).resolve()
        self.repo_name = repo_name
        self._state_file = self.repo_path / ".contextual-architect" / "index_state.json"

    def index(self, force: bool = False) -> dict:
        """
        Index the repository.

        Args:
            force: If True, re-index everything. If False, only new/changed files.

        Returns:
            Stats dict with files_scanned, files_indexed, chunks_added, duration_seconds.
        """
        start = time.time()
        last_indexed = self._load_last_indexed() if not force else 0
        
        files_scanned = 0
        files_indexed = 0
        chunks_added = 0
        errors = 0

        for file_path in self._walk_files():
            files_scanned += 1

            # Skip if not modified since last index
            try:
                mtime = os.path.getmtime(file_path)
            except OSError:
                continue

            if mtime <= last_indexed and not force:
                continue

            # Read and chunk the file
            try:
                source = file_path.read_text(encoding="utf-8", errors="replace")
            except Exception as e:
                logger.debug(f"Can't read {file_path}: {e}")
                errors += 1
                continue

            # Get relative path for metadata
            try:
                rel_path = str(file_path.relative_to(self.repo_path))
            except ValueError:
                rel_path = str(file_path)

            chunks = chunk_file(source, rel_path, self.repo_name)
            if chunks:
                chunk_dicts = [c.to_dict() for c in chunks]
                added = self.store.add_chunks(chunk_dicts)
                chunks_added += added
                files_indexed += 1

        # Save state
        self._save_last_indexed(time.time())
        duration = round(time.time() - start, 2)

        stats = {
            "files_scanned": files_scanned,
            "files_indexed": files_indexed,
            "chunks_added": chunks_added,
            "total_chunks": self.store.count(),
            "errors": errors,
            "duration_seconds": duration,
        }
        logger.info(
            f"Indexed {self.repo_name}: {files_indexed}/{files_scanned} files, "
            f"{chunks_added} chunks in {duration}s"
        )
        return stats

    def _walk_files(self):
        """Walk the repo, yielding supported source files."""
        for root, dirs, files in os.walk(self.repo_path):
            # Prune skip directories (modifies dirs in-place)
            dirs[:] = [
                d for d in dirs
                if d not in SKIP_DIRS and not d.startswith(".")
            ]

            for fname in files:
                if fname in SKIP_FILES:
                    continue

                fpath = Path(root) / fname

                # Skip large files
                try:
                    if fpath.stat().st_size > MAX_FILE_SIZE:
                        continue
                except OSError:
                    continue

                # Only index files we can chunk (supported languages)
                if detect_language(str(fpath)) is not None:
                    yield fpath

    def _load_last_indexed(self) -> float:
        """Load timestamp of last successful index."""
        try:
            if self._state_file.exists():
                data = json.loads(self._state_file.read_text())
                return data.get("last_indexed", 0)
        except Exception:
            pass
        return 0

    def _save_last_indexed(self, timestamp: float) -> None:
        """Save timestamp for incremental indexing."""
        try:
            self._state_file.parent.mkdir(parents=True, exist_ok=True)
            self._state_file.write_text(
                json.dumps({
                    "last_indexed": timestamp,
                    "repo_name": self.repo_name,
                    "total_chunks": self.store.count(),
                })
            )
        except Exception as e:
            logger.warning(f"Could not save index state: {e}")
