"""Hybrid search combining semantic and keyword retrieval."""

import re
from typing import Any

from app.keyword import keyword_search
from app.semantic import semantic_search


def _is_short_query(query: str) -> bool:
    """Check if query is short (1-2 words)."""
    words = query.strip().split()
    return len(words) <= 2


def _is_acronym_query(query: str) -> bool:
    """Check if query looks like an acronym."""
    cleaned = query.strip()
    # All caps, 2-6 characters
    if re.match(r'^[A-Z]{2,6}$', cleaned):
        return True
    # Mixed case acronym-like (e.g., "LYBUNT", "WPU")
    if re.match(r'^[A-Z][A-Za-z]{1,5}$', cleaned) and cleaned.isupper():
        return True
    return False


def _compute_blend_weights(query: str) -> tuple[float, float]:
    """
    Compute blending weights for semantic vs keyword search.
    
    Short queries and acronyms favor keyword search.
    Longer natural language queries favor semantic search.
    
    Returns:
        (semantic_weight, keyword_weight) that sum to 1.0
    """
    is_short = _is_short_query(query)
    is_acronym = _is_acronym_query(query)
    
    if is_acronym:
        # Acronyms: heavily favor keyword (exact match important)
        return 0.2, 0.8
    elif is_short:
        # Short queries: balanced with slight keyword preference
        return 0.4, 0.6
    else:
        # Longer queries: favor semantic understanding
        return 0.7, 0.3


def _normalize_scores(
    results: list[dict[str, Any]],
    source: str,
) -> list[dict[str, Any]]:
    """
    Normalize scores to 0-1 range using min-max normalization.
    
    Args:
        results: List of results with scores
        source: Source identifier ("semantic" or "keyword")
    
    Returns:
        Results with normalized scores
    """
    if not results:
        return results
    
    scores = [r["score"] for r in results]
    min_score = min(scores)
    max_score = max(scores)
    
    # Avoid division by zero
    score_range = max_score - min_score
    if score_range == 0:
        # All same score, normalize to 1.0
        for r in results:
            r["normalized_score"] = 1.0
    else:
        for r in results:
            r["normalized_score"] = (r["score"] - min_score) / score_range
    
    return results


def _generate_match_reason(
    semantic_score: float | None,
    keyword_score: float | None,
    semantic_weight: float,
    keyword_weight: float,
) -> str:
    """Generate human-readable match reason."""
    reasons = []
    
    if semantic_score is not None and semantic_score > 0.3:
        if semantic_score > 0.7:
            reasons.append("strong semantic match")
        elif semantic_score > 0.5:
            reasons.append("good semantic match")
        else:
            reasons.append("partial semantic match")
    
    if keyword_score is not None and keyword_score > 0.3:
        if keyword_score > 0.7:
            reasons.append("exact keyword match")
        elif keyword_score > 0.5:
            reasons.append("keyword match")
        else:
            reasons.append("partial keyword match")
    
    if not reasons:
        if semantic_score is not None:
            reasons.append("semantic similarity")
        if keyword_score is not None:
            reasons.append("keyword relevance")
    
    if not reasons:
        return "relevance match"
    
    return " + ".join(reasons)


def hybrid_search(
    query: str,
    top_k: int = 10,
    type_filter: str | None = None,
    category_filter: str | None = None,
) -> dict[str, Any]:
    """
    Perform hybrid search combining semantic and keyword retrieval.
    
    Args:
        query: Search query text
        top_k: Number of results to return
        type_filter: Optional filter by document type
        category_filter: Optional filter by category
    
    Returns:
        Dict with results, search mode, and metadata
    """
    # Determine blend weights based on query characteristics
    semantic_weight, keyword_weight = _compute_blend_weights(query)
    
    # Get results from both sources (fetch more for merging)
    fetch_k = 30
    
    semantic_results = semantic_search(
        query,
        top_k=fetch_k,
        type_filter=type_filter,
        category_filter=category_filter,
    )
    
    keyword_results = keyword_search(
        query,
        top_k=fetch_k,
        type_filter=type_filter,
        category_filter=category_filter,
    )
    
    # Normalize scores within each source
    semantic_results = _normalize_scores(semantic_results, "semantic")
    keyword_results = _normalize_scores(keyword_results, "keyword")
    
    # Build lookup by doc_id
    semantic_by_id: dict[str, dict] = {}
    for r in semantic_results:
        doc_id = r["metadata"].get("docId")
        if doc_id:
            semantic_by_id[doc_id] = r
    
    keyword_by_id: dict[str, dict] = {}
    for r in keyword_results:
        doc_id = r["metadata"].get("docId")
        if doc_id:
            keyword_by_id[doc_id] = r
    
    # Merge results
    all_doc_ids = set(semantic_by_id.keys()) | set(keyword_by_id.keys())
    
    merged_results = []
    for doc_id in all_doc_ids:
        sem_result = semantic_by_id.get(doc_id)
        kw_result = keyword_by_id.get(doc_id)
        
        # Get normalized scores (default to 0 if not found)
        sem_score = sem_result.get("normalized_score", 0) if sem_result else 0
        kw_score = kw_result.get("normalized_score", 0) if kw_result else 0
        
        # Compute blended score
        blended_score = (semantic_weight * sem_score) + (keyword_weight * kw_score)
        
        # Get metadata from whichever source has it
        metadata = (sem_result or kw_result)["metadata"]
        
        # Generate match reason
        match_reason = _generate_match_reason(
            sem_score if sem_result else None,
            kw_score if kw_result else None,
            semantic_weight,
            keyword_weight,
        )
        
        merged_results.append({
            "metadata": metadata,
            "score": blended_score,
            "semantic_score": sem_score if sem_result else None,
            "keyword_score": kw_score if kw_result else None,
            "match_reason": match_reason,
        })
    
    # Sort by blended score (descending)
    merged_results.sort(key=lambda x: x["score"], reverse=True)
    
    # Trim to top_k
    merged_results = merged_results[:top_k]
    
    # Determine search mode for response
    has_semantic = any(r.get("semantic_score") for r in merged_results)
    has_keyword = any(r.get("keyword_score") for r in merged_results)
    
    if has_semantic and has_keyword:
        search_mode = "hybrid"
    elif has_semantic:
        search_mode = "semantic"
    else:
        search_mode = "keyword"
    
    return {
        "results": merged_results,
        "search_mode": search_mode,
        "weights": {
            "semantic": semantic_weight,
            "keyword": keyword_weight,
        },
    }

