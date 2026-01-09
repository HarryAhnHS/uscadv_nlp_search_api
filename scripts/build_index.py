#!/usr/bin/env python3
"""
Build search indexes from docs.json.

Outputs:
- data/index.faiss: FAISS IndexFlatIP for cosine similarity (normalized embeddings)
- data/metadata.jsonl: Document metadata with normalized fields
- data/search.db: SQLite database with FTS5 for keyword search

Usage:
    python scripts/build_index.py [--force]

Environment:
    EMBED_MODEL: Sentence transformer model (default: all-MiniLM-L6-v2)
"""

import argparse
import json
import os
import sqlite3
import sys
from pathlib import Path

import faiss
from sentence_transformers import SentenceTransformer

# Paths
SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent
DATA_DIR = PROJECT_ROOT / "data"

INPUT_FILE = DATA_DIR / "docs.json"
FAISS_INDEX_FILE = DATA_DIR / "index.faiss"
METADATA_FILE = DATA_DIR / "metadata.jsonl"
SQLITE_DB_FILE = DATA_DIR / "search.db"

# Default embedding model
DEFAULT_EMBED_MODEL = "all-MiniLM-L6-v2"


def get_embed_model() -> str:
    """Get embedding model from environment or use default."""
    return os.environ.get("EMBED_MODEL", DEFAULT_EMBED_MODEL)


def create_canonical_text(doc: dict) -> str:
    """
    Create canonical text for embedding based on document type.
    
    Uses type-specific templates to create searchable text representations.
    """
    doc_type = doc.get("type", "")
    
    if doc_type == "report":
        # Report: title, description, category, platform, tags
        parts = [
            f"Report: {doc.get('title', '')}",
            doc.get("description", ""),
            f"Category: {doc.get('category', '')}",
            f"Platform: {doc.get('platform', '')}",
        ]
        tags = doc.get("tags", [])
        if tags:
            parts.append(f"Tags: {', '.join(tags)}")
        return " ".join(filter(None, parts))
    
    elif doc_type == "training_video":
        # Training video: title, description
        parts = [
            f"Training Video: {doc.get('title', '')}",
            doc.get("description", ""),
        ]
        return " ".join(filter(None, parts))
    
    elif doc_type == "glossary":
        # Glossary: term, definition
        parts = [
            f"Glossary Term: {doc.get('term', '')}",
            f"Definition: {doc.get('definition', '')}",
        ]
        return " ".join(filter(None, parts))
    
    elif doc_type == "faq":
        # FAQ: question, answer
        parts = [
            f"FAQ: {doc.get('question', '')}",
            f"Answer: {doc.get('answer', '')}",
        ]
        return " ".join(filter(None, parts))
    
    else:
        # Fallback: concatenate all string values
        text_parts = []
        for key, value in doc.items():
            if isinstance(value, str):
                text_parts.append(value)
            elif isinstance(value, list):
                text_parts.append(" ".join(str(v) for v in value))
        return " ".join(text_parts)


def normalize_document(doc: dict) -> dict:
    """
    Normalize document fields for consistent metadata storage.
    
    Returns a normalized document with consistent field names.
    """
    doc_type = doc.get("type", "unknown")
    
    # Common fields
    normalized = {
        "docId": doc.get("docId", ""),
        "type": doc_type,
    }
    
    if doc_type == "report":
        normalized.update({
            "title": doc.get("title", ""),
            "description": doc.get("description", ""),
            "url": doc.get("url", ""),
            "category": doc.get("category", ""),
            "platform": doc.get("platform", ""),
            "tags": doc.get("tags", []),
        })
    
    elif doc_type == "training_video":
        normalized.update({
            "title": doc.get("title", ""),
            "description": doc.get("description", ""),
        })
    
    elif doc_type == "glossary":
        normalized.update({
            "term": doc.get("term", ""),
            "definition": doc.get("definition", ""),
        })
    
    elif doc_type == "faq":
        normalized.update({
            "question": doc.get("question", ""),
            "answer": doc.get("answer", ""),
        })
        if doc.get("category"):
            normalized["category"] = doc["category"]
        if doc.get("tags"):
            normalized["tags"] = doc["tags"]
    
    else:
        # Preserve all fields for unknown types
        normalized.update(doc)
    
    return normalized


def get_searchable_text(doc: dict) -> str:
    """
    Get text for FTS5 keyword search.
    
    Similar to canonical text but optimized for keyword matching.
    """
    doc_type = doc.get("type", "")
    
    if doc_type == "report":
        parts = [
            doc.get("title", ""),
            doc.get("description", ""),
            doc.get("category", ""),
            doc.get("platform", ""),
            " ".join(doc.get("tags", [])),
        ]
    elif doc_type == "training_video":
        parts = [
            doc.get("title", ""),
            doc.get("description", ""),
        ]
    elif doc_type == "glossary":
        parts = [
            doc.get("term", ""),
            doc.get("definition", ""),
        ]
    elif doc_type == "faq":
        parts = [
            doc.get("question", ""),
            doc.get("answer", ""),
            doc.get("category", ""),
            " ".join(doc.get("tags", [])),
        ]
    else:
        parts = [str(v) for v in doc.values() if isinstance(v, str)]
    
    return " ".join(filter(None, parts))


def build_faiss_index(
    documents: list[dict],
    model: SentenceTransformer,
) -> tuple[faiss.IndexFlatIP, list[str]]:
    """
    Build FAISS index with normalized embeddings for cosine similarity.
    
    Returns:
        - FAISS IndexFlatIP index
        - List of canonical texts used for embeddings
    """
    print(f"Creating embeddings for {len(documents)} documents...")
    
    # Create canonical texts
    canonical_texts = [create_canonical_text(doc) for doc in documents]
    
    # Generate embeddings
    embeddings = model.encode(
        canonical_texts,
        show_progress_bar=True,
        convert_to_numpy=True,
    )
    
    # Normalize embeddings for cosine similarity with IndexFlatIP
    # When vectors are L2-normalized, inner product equals cosine similarity
    faiss.normalize_L2(embeddings)
    
    # Create index
    dimension = embeddings.shape[1]
    index = faiss.IndexFlatIP(dimension)
    index.add(embeddings)
    
    print(f"FAISS index created with {index.ntotal} vectors (dim={dimension})")
    
    return index, canonical_texts


def save_metadata(documents: list[dict], output_file: Path) -> None:
    """Save normalized document metadata to JSONL file."""
    print(f"Saving metadata to {output_file}...")
    
    with open(output_file, "w", encoding="utf-8") as f:
        for i, doc in enumerate(documents):
            normalized = normalize_document(doc)
            normalized["_index"] = i  # Store index position for FAISS lookup
            f.write(json.dumps(normalized, ensure_ascii=False) + "\n")
    
    print(f"Saved {len(documents)} metadata records")


def build_sqlite_fts(documents: list[dict], db_file: Path) -> None:
    """
    Build SQLite database with FTS5 index for keyword search.
    """
    print(f"Building SQLite FTS5 index at {db_file}...")
    
    # Remove existing database
    if db_file.exists():
        db_file.unlink()
    
    conn = sqlite3.connect(db_file)
    cursor = conn.cursor()
    
    # Create FTS5 virtual table
    cursor.execute("""
        CREATE VIRTUAL TABLE documents_fts USING fts5(
            doc_id,
            doc_type,
            title,
            content,
            tokenize='porter unicode61'
        )
    """)
    
    # Create metadata table for full document storage
    cursor.execute("""
        CREATE TABLE documents (
            id INTEGER PRIMARY KEY,
            doc_id TEXT UNIQUE,
            doc_type TEXT,
            metadata JSON
        )
    """)
    
    # Create index on doc_id
    cursor.execute("CREATE INDEX idx_doc_id ON documents(doc_id)")
    cursor.execute("CREATE INDEX idx_doc_type ON documents(doc_type)")
    
    # Insert documents
    for i, doc in enumerate(documents):
        doc_id = doc.get("docId", "")
        doc_type = doc.get("type", "")
        
        # Get title based on type
        if doc_type == "glossary":
            title = doc.get("term", "")
        elif doc_type == "faq":
            title = doc.get("question", "")
        else:
            title = doc.get("title", "")
        
        content = get_searchable_text(doc)
        normalized = normalize_document(doc)
        
        # Insert into FTS5 table
        cursor.execute(
            "INSERT INTO documents_fts (rowid, doc_id, doc_type, title, content) VALUES (?, ?, ?, ?, ?)",
            (i, doc_id, doc_type, title, content),
        )
        
        # Insert into metadata table
        cursor.execute(
            "INSERT INTO documents (id, doc_id, doc_type, metadata) VALUES (?, ?, ?, ?)",
            (i, doc_id, doc_type, json.dumps(normalized, ensure_ascii=False)),
        )
    
    conn.commit()
    
    # Verify
    cursor.execute("SELECT COUNT(*) FROM documents_fts")
    fts_count = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM documents")
    doc_count = cursor.fetchone()[0]
    
    conn.close()
    
    print(f"SQLite FTS5 index created: {fts_count} FTS records, {doc_count} documents")


def check_outputs_exist() -> list[Path]:
    """Check which output files already exist."""
    outputs = [FAISS_INDEX_FILE, METADATA_FILE, SQLITE_DB_FILE]
    return [f for f in outputs if f.exists()]


def main():
    parser = argparse.ArgumentParser(
        description="Build search indexes from document JSON file"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing output files",
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=INPUT_FILE,
        help="Input JSON file (default: data/docs.json)",
    )
    args = parser.parse_args()
    
    input_file = args.input
    
    # Check input file
    if not input_file.exists():
        print(f"Error: Input file not found: {input_file}")
        print("Run fetch_sharepoint.py first to generate docs.json.")
        sys.exit(1)
    
    # Check for existing outputs
    existing = check_outputs_exist()
    if existing and not args.force:
        print("Error: Output files already exist:")
        for f in existing:
            print(f"  - {f}")
        print("\nUse --force to overwrite.")
        sys.exit(1)
    
    # Load documents
    print(f"Loading documents from {input_file}...")
    with open(input_file, "r", encoding="utf-8") as f:
        documents = json.load(f)
    print(f"Loaded {len(documents)} documents")
    
    # Load embedding model
    model_name = get_embed_model()
    print(f"Loading embedding model: {model_name}...")
    model = SentenceTransformer(model_name)
    
    # Build FAISS index
    faiss_index, _ = build_faiss_index(documents, model)
    
    # Save FAISS index
    print(f"Saving FAISS index to {FAISS_INDEX_FILE}...")
    faiss.write_index(faiss_index, str(FAISS_INDEX_FILE))
    
    # Save metadata
    save_metadata(documents, METADATA_FILE)
    
    # Build SQLite FTS index
    build_sqlite_fts(documents, SQLITE_DB_FILE)
    
    print("\n✓ Index build complete!")
    print(f"  - FAISS index: {FAISS_INDEX_FILE}")
    print(f"  - Metadata: {METADATA_FILE}")
    print(f"  - SQLite DB: {SQLITE_DB_FILE}")


if __name__ == "__main__":
    main()

