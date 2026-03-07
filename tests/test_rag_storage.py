"""Tests for rag/ and storage/ layers."""

import os
import sys
import shutil
import tempfile
import pytest

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ═══════════════════════════════════════════════════════════════
# Code Chunker Tests
# ═══════════════════════════════════════════════════════════════


class TestCodeChunker:
    """Tests for AST-aware code chunking."""

    def test_chunk_python_simple_function(self):
        from rag.code_chunker import chunk_python_file

        source = '''
def hello():
    """Say hello."""
    return "hello"

def goodbye():
    return "bye"
'''
        chunks = chunk_python_file(source, "app.py", "test-repo")
        assert len(chunks) == 2
        assert chunks[0].metadata["symbol_name"] == "hello"
        assert chunks[0].metadata["symbol_type"] == "function"
        assert chunks[1].metadata["symbol_name"] == "goodbye"

    def test_chunk_python_class(self):
        from rag.code_chunker import chunk_python_file

        source = '''
class UserService:
    def __init__(self, db):
        self.db = db

    def get_user(self, user_id):
        return self.db.query(user_id)
'''
        chunks = chunk_python_file(source, "services.py", "test-repo")
        # Should get the class as a chunk
        class_chunks = [c for c in chunks if c.metadata["symbol_type"] == "class"]
        assert len(class_chunks) >= 1
        assert class_chunks[0].metadata["symbol_name"] == "UserService"

    def test_chunk_python_syntax_error_fallback(self):
        from rag.code_chunker import chunk_python_file

        source = "def broken(\n  invalid syntax here"
        chunks = chunk_python_file(source, "bad.py", "test-repo")
        assert len(chunks) == 1
        assert chunks[0].metadata["symbol_type"] == "file"

    def test_chunk_python_empty_file(self):
        from rag.code_chunker import chunk_python_file

        chunks = chunk_python_file("# just a comment\n", "empty.py", "test-repo")
        assert len(chunks) == 1
        assert chunks[0].metadata["symbol_type"] == "module"

    def test_chunk_python_async_function(self):
        from rag.code_chunker import chunk_python_file

        source = '''
async def fetch_data(url: str):
    """Fetch data from an API."""
    async with aiohttp.ClientSession() as session:
        return await session.get(url)
'''
        chunks = chunk_python_file(source, "api.py", "test-repo")
        assert len(chunks) == 1
        assert chunks[0].metadata["symbol_name"] == "fetch_data"
        assert chunks[0].metadata["symbol_type"] == "function"

    def test_detect_language(self):
        from rag.code_chunker import detect_language

        assert detect_language("app.py") == "python"
        assert detect_language("index.js") == "javascript"
        assert detect_language("main.go") == "go"
        assert detect_language("app.tsx") == "typescript"
        assert detect_language("readme.md") is None
        assert detect_language("Dockerfile") is None

    def test_chunk_file_unified(self):
        from rag.code_chunker import chunk_file

        source = '''
def add(a, b):
    return a + b
'''
        chunks = chunk_file(source, "math.py", "test-repo")
        assert len(chunks) == 1
        assert chunks[0].metadata["language"] == "python"

    def test_chunk_file_unsupported(self):
        from rag.code_chunker import chunk_file

        chunks = chunk_file("# Markdown content", "README.md", "test-repo")
        assert len(chunks) == 0

    def test_deduplicate(self):
        from rag.code_chunker import CodeChunk, deduplicate

        chunks = [
            CodeChunk(text="def foo(): pass", metadata={"name": "a"}),
            CodeChunk(text="def foo(): pass", metadata={"name": "b"}),
            CodeChunk(text="def bar(): pass", metadata={"name": "c"}),
        ]
        result = deduplicate(chunks)
        assert len(result) == 2

    def test_chunk_metadata_has_required_fields(self):
        from rag.code_chunker import chunk_python_file

        source = '''
def process(data):
    return data.strip()
'''
        chunks = chunk_python_file(source, "utils.py", "my-repo")
        meta = chunks[0].metadata
        assert "repo" in meta
        assert "file_path" in meta
        assert "symbol_name" in meta
        assert "symbol_type" in meta
        assert "language" in meta
        assert meta["repo"] == "my-repo"
        assert meta["file_path"] == "utils.py"


# ═══════════════════════════════════════════════════════════════
# Vector Store Tests
# ═══════════════════════════════════════════════════════════════


class TestChromaVectorStore:
    """Tests for ChromaDB vector store."""

    @pytest.fixture
    def tmp_dir(self):
        d = tempfile.mkdtemp()
        yield d
        shutil.rmtree(d, ignore_errors=True)

    @pytest.fixture
    def store(self, tmp_dir):
        pytest.importorskip("chromadb")
        from rag.vector_store import ChromaVectorStore

        return ChromaVectorStore(
            repo_name="test-repo",
            persist_dir=tmp_dir,
            embedding_model="all-MiniLM-L6-v2",
        )

    def test_add_and_count(self, store):
        chunks = [
            {"text": "def hello(): return 'hello'", "metadata": {"file_path": "a.py", "symbol_name": "hello"}},
            {"text": "def goodbye(): return 'bye'", "metadata": {"file_path": "a.py", "symbol_name": "goodbye"}},
        ]
        added = store.add_chunks(chunks)
        assert added == 2
        assert store.count() == 2

    def test_add_empty(self, store):
        assert store.add_chunks([]) == 0

    def test_search_returns_results(self, store):
        chunks = [
            {"text": "def create_user(name, email): save_to_db(name, email)", "metadata": {"file_path": "users.py", "symbol_name": "create_user"}},
            {"text": "def delete_user(user_id): db.remove(user_id)", "metadata": {"file_path": "users.py", "symbol_name": "delete_user"}},
            {"text": "def calculate_tax(amount): return amount * 0.18", "metadata": {"file_path": "billing.py", "symbol_name": "calculate_tax"}},
        ]
        store.add_chunks(chunks)

        results = store.search("create a new user", k=2)
        assert len(results) >= 1
        assert "text" in results[0]
        assert "metadata" in results[0]
        assert "relevance" in results[0]

    def test_search_empty_store(self, store):
        results = store.search("anything")
        assert results == []

    def test_upsert_idempotent(self, store):
        chunk = [{"text": "def foo(): pass", "metadata": {"file_path": "a.py", "symbol_name": "foo"}}]
        store.add_chunks(chunk)
        store.add_chunks(chunk)  # Same chunk again
        assert store.count() == 1  # Should not duplicate

    def test_delete_collection(self, store):
        store.add_chunks([{"text": "def x(): pass", "metadata": {"file_path": "x.py", "symbol_name": "x"}}])
        assert store.count() == 1
        store.delete_collection()
        assert store.count() == 0


# ═══════════════════════════════════════════════════════════════
# Retriever Tests
# ═══════════════════════════════════════════════════════════════


class TestCodeRetriever:
    """Tests for the high-level retriever interface."""

    @pytest.fixture
    def tmp_dir(self):
        d = tempfile.mkdtemp()
        yield d
        shutil.rmtree(d, ignore_errors=True)

    @pytest.fixture
    def retriever(self, tmp_dir):
        pytest.importorskip("chromadb")
        from rag.vector_store import ChromaVectorStore
        from rag.retriever import CodeRetriever

        store = ChromaVectorStore("test-repo", persist_dir=tmp_dir)
        store.add_chunks([
            {"text": "def get_user(user_id): return db.query(User, user_id)", "metadata": {"file_path": "users.py", "symbol_name": "get_user", "language": "python"}},
            {"text": "def create_order(items): total = sum(i.price for i in items)", "metadata": {"file_path": "orders.py", "symbol_name": "create_order", "language": "python"}},
            {"text": "class DatabaseConnection:\n    def connect(self): ...", "metadata": {"file_path": "db.py", "symbol_name": "DatabaseConnection", "language": "python"}},
        ])
        return CodeRetriever(store)

    def test_find_patterns(self, retriever):
        results = retriever.find_patterns("database query user")
        assert len(results) >= 1

    def test_find_similar_tasks(self, retriever):
        results = retriever.find_similar_tasks("add a new order endpoint")
        assert len(results) >= 1

    def test_find_by_symbol(self, retriever):
        results = retriever.find_by_symbol("get_user")
        assert len(results) >= 1

    def test_indexed_count(self, retriever):
        assert retriever.indexed_count == 3

    def test_format_for_prompt(self, retriever):
        results = retriever.find_patterns("user query")
        formatted = retriever.format_for_prompt(results)
        assert "## Relevant Code Patterns" in formatted
        assert "```" in formatted

    def test_format_empty(self, retriever):
        formatted = retriever.format_for_prompt([])
        assert "No relevant patterns" in formatted


# ═══════════════════════════════════════════════════════════════
# Indexer Tests
# ═══════════════════════════════════════════════════════════════


class TestRepoIndexer:
    """Tests for incremental repo indexing."""

    @pytest.fixture
    def tmp_repo(self):
        d = tempfile.mkdtemp()
        # Create a mini Python project
        (dir := os.path.join(d, "src"))
        os.makedirs(dir, exist_ok=True)
        with open(os.path.join(dir, "app.py"), "w") as f:
            f.write('def main():\n    print("hello")\n\ndef helper():\n    return 42\n')
        with open(os.path.join(dir, "utils.py"), "w") as f:
            f.write('def format_name(first, last):\n    return f"{first} {last}"\n')
        # Non-Python file (should be skipped)
        with open(os.path.join(d, "README.md"), "w") as f:
            f.write("# Test project\n")
        yield d
        shutil.rmtree(d, ignore_errors=True)

    @pytest.fixture
    def chroma_dir(self):
        d = tempfile.mkdtemp()
        yield d
        shutil.rmtree(d, ignore_errors=True)

    def test_index_repo(self, tmp_repo, chroma_dir):
        pytest.importorskip("chromadb")
        from rag.vector_store import ChromaVectorStore
        from rag.indexer import RepoIndexer

        store = ChromaVectorStore("test-repo", persist_dir=chroma_dir)
        indexer = RepoIndexer(store, repo_path=tmp_repo, repo_name="test-repo")

        stats = indexer.index()
        assert stats["files_scanned"] >= 2
        assert stats["files_indexed"] >= 2
        assert stats["chunks_added"] >= 3  # main, helper, format_name
        assert stats["total_chunks"] >= 3

    def test_incremental_index(self, tmp_repo, chroma_dir):
        pytest.importorskip("chromadb")
        from rag.vector_store import ChromaVectorStore
        from rag.indexer import RepoIndexer

        store = ChromaVectorStore("test-repo", persist_dir=chroma_dir)
        indexer = RepoIndexer(store, repo_path=tmp_repo, repo_name="test-repo")

        # First index
        stats1 = indexer.index()
        assert stats1["files_indexed"] >= 2

        # Second index (no changes) — should skip everything
        stats2 = indexer.index()
        assert stats2["files_indexed"] == 0

    def test_force_reindex(self, tmp_repo, chroma_dir):
        pytest.importorskip("chromadb")
        from rag.vector_store import ChromaVectorStore
        from rag.indexer import RepoIndexer

        store = ChromaVectorStore("test-repo", persist_dir=chroma_dir)
        indexer = RepoIndexer(store, repo_path=tmp_repo, repo_name="test-repo")

        indexer.index()
        stats = indexer.index(force=True)
        assert stats["files_indexed"] >= 2


# ═══════════════════════════════════════════════════════════════
# SQLite Store Tests
# ═══════════════════════════════════════════════════════════════


class TestStructuredStore:
    """Tests for SQLite structured storage."""

    @pytest.fixture
    def db(self):
        d = tempfile.mkdtemp()
        from storage.sqlite_store import StructuredStore

        store = StructuredStore(db_path=os.path.join(d, "test.db"))
        yield store
        store.close()
        shutil.rmtree(d, ignore_errors=True)

    def test_start_and_complete_run(self, db):
        run_id = db.start_run("Add health check", "/project", "python", "groq", "llama-3.3")
        assert run_id >= 1

        db.complete_run(run_id, status="completed", duration_seconds=42.5,
                       constraints_passed=11, constraints_total=11)

        run = db.get_run(run_id)
        assert run["status"] == "completed"
        assert run["duration_seconds"] == 42.5
        assert run["constraints_passed"] == 11

    def test_log_agent_telemetry(self, db):
        run_id = db.start_run("Test task", "/repo", "python")
        db.log_agent("run_id_invalid", "historian", 100, 50, 1200)  # This will use the string
        db.log_agent(run_id, "historian", input_tokens=100, output_tokens=50, duration_ms=1200)
        db.log_agent(run_id, "architect", input_tokens=200, output_tokens=80, duration_ms=800)

        telemetry = db.get_run_telemetry(run_id)
        assert len(telemetry) == 2
        assert telemetry[0]["agent_name"] == "historian"
        assert telemetry[1]["agent_name"] == "architect"

    def test_log_feedback(self, db):
        run_id = db.start_run("Test", "/repo")
        db.log_feedback(run_id, "reviewer", "accept", "Looks good")
        db.log_feedback(run_id, "implementer", "reject", "Wrong pattern")

        feedback = db.get_feedback_history()
        assert len(feedback) == 2

    def test_get_recent_runs(self, db):
        db.start_run("Task 1", "/repo-a")
        db.start_run("Task 2", "/repo-b")
        db.start_run("Task 3", "/repo-a")

        all_runs = db.get_recent_runs()
        assert len(all_runs) == 3

        repo_a_runs = db.get_recent_runs(repo="/repo-a")
        assert len(repo_a_runs) == 2

    def test_get_stats(self, db):
        run_id = db.start_run("T1", "/repo")
        db.complete_run(run_id, status="completed", duration_seconds=10.0)

        stats = db.get_stats()
        assert stats["total_runs"] == 1
        assert stats["completed_runs"] == 1
        assert stats["avg_duration_seconds"] == 10.0

    def test_context_manager(self):
        d = tempfile.mkdtemp()
        from storage.sqlite_store import StructuredStore

        with StructuredStore(db_path=os.path.join(d, "test.db")) as db:
            run_id = db.start_run("Context test", "/repo")
            assert run_id >= 1
        shutil.rmtree(d, ignore_errors=True)
