"""
Singleton store for loaded indexes and embedding model.

Provides lazy loading and caching of:
- FAISS index
- Document metadata
- SQLite database connection
- Sentence transformer model with LRU-cached embeddings
"""

import json
import os
import sqlite3
from functools import lru_cache
from pathlib import Path
from typing import Any

import faiss
import numpy as np
from sentence_transformers import SentenceTransformer

# Paths
DATA_DIR = Path(__file__).parent.parent / "data"
FAISS_INDEX_FILE = DATA_DIR / "index.faiss"
METADATA_FILE = DATA_DIR / "metadata.jsonl"
SQLITE_DB_FILE = DATA_DIR / "search.db"

# Default embedding model
DEFAULT_EMBED_MODEL = "all-MiniLM-L6-v2"


class IndexStore:
    """Singleton store for search indexes."""

    _instance: "IndexStore | None" = None

    def __new__(cls) -> "IndexStore":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self) -> None:
        if self._initialized:
            return
        
        self._faiss_index: faiss.IndexFlatIP | None = None
        self._metadata: list[dict[str, Any]] = []
        self._model: SentenceTransformer | None = None
        self._db_path: Path = SQLITE_DB_FILE
        self._initialized = True
        self._loaded = False

    @property
    def is_loaded(self) -> bool:
        """Check if indexes are loaded."""
        return self._loaded

    @property
    def document_count(self) -> int:
        """Get number of indexed documents."""
        return len(self._metadata)

    def load(self) -> None:
        """Load all indexes and model."""
        if self._loaded:
            return

        # Load FAISS index
        if FAISS_INDEX_FILE.exists():
            self._faiss_index = faiss.read_index(str(FAISS_INDEX_FILE))

        # Load metadata
        if METADATA_FILE.exists():
            self._metadata = []
            with open(METADATA_FILE, "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        self._metadata.append(json.loads(line))

        # Load embedding model
        model_name = os.environ.get("EMBED_MODEL", DEFAULT_EMBED_MODEL)
        self._model = SentenceTransformer(model_name)

        self._loaded = True

    def get_faiss_index(self) -> faiss.IndexFlatIP | None:
        """Get FAISS index."""
        return self._faiss_index

    def get_metadata(self, index: int) -> dict[str, Any] | None:
        """Get metadata for document at index."""
        if 0 <= index < len(self._metadata):
            return self._metadata[index]
        return None

    def get_all_metadata(self) -> list[dict[str, Any]]:
        """Get all metadata."""
        return self._metadata

    def get_sqlite_connection(self) -> sqlite3.Connection:
        """Get SQLite database connection."""
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        return conn

    @lru_cache(maxsize=1024)
    def encode_query(self, query: str) -> tuple:
        """
        Encode query to embedding with LRU caching.
        
        Returns tuple for hashability in cache.
        """
        if self._model is None:
            raise RuntimeError("Model not loaded")
        
        embedding = self._model.encode(
            query,
            convert_to_numpy=True,
            normalize_embeddings=True,  # Normalize for cosine similarity
        )
        return tuple(embedding.tolist())

    def get_query_embedding(self, query: str) -> np.ndarray:
        """Get query embedding as numpy array."""
        cached = self.encode_query(query)
        return np.array(cached, dtype=np.float32).reshape(1, -1)

    def clear_cache(self) -> None:
        """Clear embedding cache."""
        self.encode_query.cache_clear()


# Global singleton instance
_store: IndexStore | None = None


def get_index_store() -> IndexStore:
    """Get or create the global IndexStore instance."""
    global _store
    if _store is None:
        _store = IndexStore()
    return _store

