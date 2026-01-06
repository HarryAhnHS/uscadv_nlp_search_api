"""FastAPI application for NLP search API."""

from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, Query

from app.auth import get_current_user
from app.hybrid import hybrid_search
from app.index_store import get_index_store
from app.models import (
    ErrorResponse,
    HealthResponse,
    SearchResponse,
    SearchResult,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Load indexes on startup."""
    store = get_index_store()
    store.load()
    print(f"✓ Loaded {store.document_count} documents")
    yield
    # Cleanup on shutdown
    store.clear_cache()


app = FastAPI(
    title="USC Advancement NLP Search API",
    description="Hybrid semantic + keyword search for BI Hub resources",
    version="1.0.0",
    lifespan=lifespan,
)


@app.get(
    "/health",
    response_model=HealthResponse,
    tags=["System"],
    summary="Health check",
)
async def health_check() -> HealthResponse:
    """
    Check API health and index status.
    
    Returns:
        Health status including index load state and document count.
    """
    store = get_index_store()
    return HealthResponse(
        status="ok",
        index_loaded=store.is_loaded,
        document_count=store.document_count,
    )


@app.get(
    "/search",
    response_model=SearchResponse,
    responses={
        400: {"model": ErrorResponse, "description": "Invalid request"},
        500: {"model": ErrorResponse, "description": "Search error"},
    },
    tags=["Search"],
    summary="Search documents",
)
async def search(
    q: Annotated[str, Query(min_length=1, description="Search query")],
    type: Annotated[
        str | None,
        Query(description="Filter by document type (report, training_video, glossary)"),
    ] = None,
    category: Annotated[
        str | None,
        Query(description="Filter by category"),
    ] = None,
    top_k: Annotated[
        int,
        Query(ge=1, le=100, description="Number of results to return"),
    ] = 10,
    user: Annotated[dict, Depends(get_current_user)] = None,
) -> SearchResponse:
    """
    Search documents using hybrid semantic + keyword retrieval.
    
    The search automatically adjusts weighting based on query characteristics:
    - Short queries and acronyms favor keyword matching
    - Longer natural language queries favor semantic understanding
    
    Args:
        q: Search query text
        type: Optional filter by document type
        category: Optional filter by category
        top_k: Number of results (1-100, default 10)
    
    Returns:
        Search results with relevance scores and match explanations.
    """
    # Perform hybrid search
    search_result = hybrid_search(
        query=q,
        top_k=top_k,
        type_filter=type,
        category_filter=category,
    )
    
    # Convert to response model
    results = []
    for r in search_result["results"]:
        metadata = r["metadata"]
        doc_type = metadata.get("type", "")
        
        result = SearchResult(
            docId=metadata.get("docId", ""),
            type=doc_type,
            score=round(r["score"], 4),
            matchReason=r["match_reason"],
        )
        
        # Add type-specific fields
        if doc_type == "report":
            result.title = metadata.get("title")
            result.description = metadata.get("description")
            result.url = metadata.get("url")
            result.category = metadata.get("category")
            result.platform = metadata.get("platform")
            result.tags = metadata.get("tags")
        elif doc_type == "training_video":
            result.title = metadata.get("title")
            result.description = metadata.get("description")
        elif doc_type == "glossary":
            result.term = metadata.get("term")
            result.definition = metadata.get("definition")
        
        results.append(result)
    
    return SearchResponse(
        query=q,
        total=len(results),
        results=results,
        searchMode=search_result["search_mode"],
    )


# Error handlers
@app.exception_handler(Exception)
async def generic_exception_handler(request, exc):
    """Handle unexpected errors."""
    from fastapi.responses import JSONResponse
    
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal server error",
            "detail": str(exc) if app.debug else None,
        },
    )

