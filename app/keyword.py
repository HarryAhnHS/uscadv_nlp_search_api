"""Keyword search using SQLite FTS5."""

import json
import re
import sqlite3
from typing import Any

from app.index_store import get_index_store


def _escape_fts_query(query: str) -> str:
    """
    Escape special characters for FTS5 query.
    
    FTS5 has special syntax for operators. We escape to treat as literals.
    """
    # Remove characters that could break FTS5 syntax
    # Keep alphanumeric, spaces, and common punctuation
    cleaned = re.sub(r'[^\w\s\-\']', ' ', query)
    # Collapse multiple spaces
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    return cleaned


def _build_fts_query(query: str) -> str:
    """
    Build FTS5 query string.
    
    Handles:
    - Simple queries: word1 word2 -> word1* OR word2*
    - Quoted phrases: "exact phrase"
    - Prefix matching for partial words
    """
    cleaned = _escape_fts_query(query)
    if not cleaned:
        return ""
    
    # Split into words
    words = cleaned.split()
    
    if len(words) == 1:
        # Single word: prefix match
        return f'"{words[0]}"* OR {words[0]}'
    
    # Multiple words: OR together with prefix matching
    terms = []
    for word in words:
        if len(word) >= 2:
            terms.append(f'"{word}"*')
    
    if not terms:
        return cleaned
    
    return " OR ".join(terms)


def keyword_search(
    query: str,
    top_k: int = 30,
    type_filter: str | None = None,
    category_filter: str | None = None,
) -> list[dict[str, Any]]:
    """
    Perform keyword search using SQLite FTS5.
    
    Args:
        query: Search query text
        top_k: Number of results to return
        type_filter: Optional filter by document type
        category_filter: Optional filter by category
    
    Returns:
        List of results with doc metadata and BM25 scores
    """
    store = get_index_store()
    
    fts_query = _build_fts_query(query)
    if not fts_query:
        return []
    
    try:
        conn = store.get_sqlite_connection()
        cursor = conn.cursor()
        
        # Build SQL query with filters
        sql = """
            SELECT 
                d.doc_id,
                d.doc_type,
                d.metadata,
                bm25(documents_fts) as rank
            FROM documents_fts f
            JOIN documents d ON f.rowid = d.id
            WHERE documents_fts MATCH ?
        """
        params: list[Any] = [fts_query]
        
        if type_filter:
            sql += " AND d.doc_type = ?"
            params.append(type_filter)
        
        # Category filter needs to check JSON metadata
        if category_filter:
            sql += " AND json_extract(d.metadata, '$.category') = ?"
            params.append(category_filter)
        
        sql += " ORDER BY rank LIMIT ?"
        params.append(top_k)
        
        cursor.execute(sql, params)
        rows = cursor.fetchall()
        
        results = []
        for row in rows:
            metadata = json.loads(row["metadata"])
            # BM25 returns negative scores (more negative = better match)
            # Convert to positive score
            bm25_score = -row["rank"]
            
            results.append({
                "metadata": metadata,
                "score": bm25_score,
                "source": "keyword",
            })
        
        conn.close()
        return results
        
    except sqlite3.Error as e:
        # Log error in production
        print(f"FTS search error: {e}")
        return []


def get_keyword_scores(
    query: str,
    doc_ids: list[str],
) -> dict[str, float]:
    """
    Get keyword match scores for specific documents.
    
    Useful for re-ranking or score normalization.
    """
    if not doc_ids:
        return {}
    
    store = get_index_store()
    fts_query = _build_fts_query(query)
    
    if not fts_query:
        return {}
    
    try:
        conn = store.get_sqlite_connection()
        cursor = conn.cursor()
        
        placeholders = ",".join("?" * len(doc_ids))
        sql = f"""
            SELECT 
                d.doc_id,
                bm25(documents_fts) as rank
            FROM documents_fts f
            JOIN documents d ON f.rowid = d.id
            WHERE documents_fts MATCH ?
            AND d.doc_id IN ({placeholders})
        """
        
        cursor.execute(sql, [fts_query] + doc_ids)
        rows = cursor.fetchall()
        
        result = {row["doc_id"]: -row["rank"] for row in rows}
        conn.close()
        return result
        
    except sqlite3.Error:
        return {}

