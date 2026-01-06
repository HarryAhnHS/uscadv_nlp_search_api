"""Semantic search using FAISS."""

from typing import Any

import numpy as np

from app.index_store import get_index_store


def semantic_search(
    query: str,
    top_k: int = 30,
    type_filter: str | None = None,
    category_filter: str | None = None,
) -> list[dict[str, Any]]:
    """
    Perform semantic search using FAISS.
    
    Args:
        query: Search query text
        top_k: Number of results to return
        type_filter: Optional filter by document type
        category_filter: Optional filter by category
    
    Returns:
        List of results with doc metadata and similarity scores
    """
    store = get_index_store()
    index = store.get_faiss_index()
    
    if index is None:
        return []
    
    # Get query embedding (cached)
    query_embedding = store.get_query_embedding(query)
    
    # Search with more results if filtering (to ensure enough after filter)
    search_k = top_k * 3 if (type_filter or category_filter) else top_k
    search_k = min(search_k, index.ntotal)
    
    # FAISS search
    scores, indices = index.search(query_embedding, search_k)
    
    results = []
    for score, idx in zip(scores[0], indices[0]):
        if idx < 0:  # Invalid index
            continue
        
        metadata = store.get_metadata(int(idx))
        if metadata is None:
            continue
        
        # Apply filters
        if type_filter and metadata.get("type") != type_filter:
            continue
        if category_filter and metadata.get("category") != category_filter:
            continue
        
        results.append({
            "metadata": metadata,
            "score": float(score),  # Inner product score (0-1 for normalized vectors)
            "source": "semantic",
        })
        
        if len(results) >= top_k:
            break
    
    return results


def get_semantic_scores(
    query: str,
    doc_ids: list[str],
) -> dict[str, float]:
    """
    Get semantic similarity scores for specific documents.
    
    Useful for re-ranking or score normalization.
    """
    store = get_index_store()
    all_metadata = store.get_all_metadata()
    
    # Build doc_id to index mapping
    id_to_idx = {
        doc.get("docId"): doc.get("_index")
        for doc in all_metadata
        if doc.get("docId") in doc_ids
    }
    
    if not id_to_idx:
        return {}
    
    # Get query embedding
    query_embedding = store.get_query_embedding(query)
    index = store.get_faiss_index()
    
    if index is None:
        return {}
    
    # Search all documents
    scores, indices = index.search(query_embedding, index.ntotal)
    
    # Map scores to doc_ids
    result = {}
    for score, idx in zip(scores[0], indices[0]):
        if idx < 0:
            continue
        metadata = store.get_metadata(int(idx))
        if metadata:
            doc_id = metadata.get("docId")
            if doc_id in doc_ids:
                result[doc_id] = float(score)
    
    return result

