"""
Vector store abstraction + ChromaDB implementation.

Agents never import this directly — they use retriever.py.
Swap ChromaDB for Qdrant/pgvector by implementing VectorStore ABC.
"""

from abc import ABC, abstractmethod
from typing import Optional
import hashlib
import logging

logger = logging.getLogger(__name__)


class VectorStore(ABC):
    """Abstract vector store interface — swap implementations freely."""

    @abstractmethod
    def add_chunks(self, chunks: list[dict]) -> int:
        """Add chunks to the store. Returns number added."""
        ...

    @abstractmethod
    def search(
        self, query: str, k: int = 10, filters: Optional[dict] = None
    ) -> list[dict]:
        """Search for similar chunks. Returns list of {text, metadata, distance}."""
        ...

    @abstractmethod
    def count(self) -> int:
        """Number of chunks in the store."""
        ...

    @abstractmethod
    def delete_collection(self) -> None:
        """Delete the entire collection (for re-indexing)."""
        ...


class ChromaVectorStore(VectorStore):
    """
    ChromaDB implementation with per-repo collections.

    Uses sentence-transformers for embeddings (CPU-only, no GPU needed).
    Falls back to ChromaDB's default embeddings if sentence-transformers
    isn't available.
    """

    def __init__(
        self,
        repo_name: str,
        persist_dir: str = "./.contextual-architect/chroma_db",
        embedding_model: str = "all-MiniLM-L6-v2",
    ):
        try:
            import chromadb
            from chromadb.config import Settings
        except ImportError:
            raise ImportError(
                "chromadb is required for RAG. Install: pip install chromadb"
            )

        self.client = chromadb.PersistentClient(
            path=persist_dir,
            settings=Settings(anonymized_telemetry=False),
        )

        # Try sentence-transformers first, fall back to default
        ef = self._create_embedding_function(embedding_model)

        # Sanitize collection name (ChromaDB rules: 3-63 chars, [a-zA-Z0-9_-])
        collection_name = (
            repo_name.replace("/", "_")
            .replace("\\", "_")
            .replace("-", "_")
            .replace(".", "_")
        )
        collection_name = collection_name[:63] if len(collection_name) > 63 else collection_name
        if len(collection_name) < 3:
            collection_name = f"repo_{collection_name}"

        self.collection = self.client.get_or_create_collection(
            name=collection_name,
            embedding_function=ef,
            metadata={"hnsw:space": "cosine"},
        )
        logger.info(
            f"ChromaDB collection '{collection_name}' ready "
            f"({self.collection.count()} chunks)"
        )

    def _create_embedding_function(self, model_name: str):
        """Create embedding function, with graceful fallback."""
        # Strategy 1: sentence-transformers (best for code)
        try:
            from chromadb.utils import embedding_functions

            ef = embedding_functions.SentenceTransformerEmbeddingFunction(
                model_name=model_name
            )
            # Quick test to ensure it actually works (catches Keras issues)
            ef(["test"])
            logger.info(f"Using SentenceTransformer embeddings: {model_name}")
            return ef
        except Exception as e:
            logger.debug(f"SentenceTransformer failed: {e}")

        # Strategy 2: ChromaDB's built-in default (onnxruntime, CPU-only)
        try:
            from chromadb.utils.embedding_functions import DefaultEmbeddingFunction

            ef = DefaultEmbeddingFunction()
            logger.info("Using ChromaDB default embeddings (onnxruntime)")
            return ef
        except Exception as e:
            logger.debug(f"DefaultEmbeddingFunction failed: {e}")

        # Strategy 3: ONNXMini explicitly
        try:
            from chromadb.utils.embedding_functions import ONNXMiniLM_L6_V2

            ef = ONNXMiniLM_L6_V2()
            logger.info("Using ONNXMiniLM_L6_V2 embeddings")
            return ef
        except Exception as e:
            logger.warning(
                f"All embedding strategies failed. Last error: {e}. "
                f"Install: pip install chromadb[onnxruntime]"
            )
            raise RuntimeError(
                "No embedding function available. Install one of: "
                "sentence-transformers, onnxruntime, or chromadb[onnxruntime]"
            )

    def add_chunks(self, chunks: list[dict]) -> int:
        """Add code chunks to the collection."""
        if not chunks:
            return 0

        # Generate stable IDs from content hash
        ids = []
        documents = []
        metadatas = []

        for chunk in chunks:
            text = chunk.get("text", "")
            meta = chunk.get("metadata", {})

            # Stable ID: hash of file_path + symbol_name + content
            id_source = f"{meta.get('file_path', '')}:{meta.get('symbol_name', '')}:{text[:200]}"
            chunk_id = hashlib.sha256(id_source.encode()).hexdigest()[:16]

            ids.append(chunk_id)
            documents.append(text)
            # ChromaDB requires metadata values to be str/int/float/bool
            clean_meta = {
                k: str(v) if v is not None else ""
                for k, v in meta.items()
            }
            metadatas.append(clean_meta)

        # ChromaDB upsert (idempotent — safe to re-index)
        self.collection.upsert(
            ids=ids, documents=documents, metadatas=metadatas
        )
        logger.info(f"Upserted {len(ids)} chunks")
        return len(ids)

    def search(
        self, query: str, k: int = 10, filters: Optional[dict] = None
    ) -> list[dict]:
        """Semantic search for similar code chunks."""
        if self.collection.count() == 0:
            return []

        kwargs = {"query_texts": [query], "n_results": min(k, self.collection.count())}
        if filters:
            kwargs["where"] = filters

        try:
            results = self.collection.query(**kwargs)
        except Exception as e:
            logger.warning(f"ChromaDB search failed: {e}")
            return []

        output = []
        if results["documents"] and results["documents"][0]:
            docs = results["documents"][0]
            metas = results["metadatas"][0] if results["metadatas"] else [{}] * len(docs)
            dists = results["distances"][0] if results["distances"] else [0.0] * len(docs)

            for doc, meta, dist in zip(docs, metas, dists):
                output.append({
                    "text": doc,
                    "metadata": meta,
                    "distance": dist,
                    "relevance": round(1.0 - dist, 4),  # cosine: 0=identical
                })

        return output

    def count(self) -> int:
        return self.collection.count()

    def delete_collection(self) -> None:
        """Delete and recreate the collection."""
        name = self.collection.name
        ef = self.collection._embedding_function
        self.client.delete_collection(name)
        self.collection = self.client.get_or_create_collection(
            name=name, embedding_function=ef, metadata={"hnsw:space": "cosine"}
        )
        logger.info(f"Collection '{name}' deleted and recreated")
