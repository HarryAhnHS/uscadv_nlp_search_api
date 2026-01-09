"""Pydantic models for request/response schemas."""

from typing import Literal

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    """Health check response."""

    status: str = "ok"
    index_loaded: bool
    document_count: int


class SearchRequest(BaseModel):
    """Search request parameters."""

    q: str = Field(..., min_length=1, description="Search query")
    type: str | None = Field(None, description="Filter by document type")
    category: str | None = Field(None, description="Filter by category")
    top_k: int = Field(10, ge=1, le=100, description="Number of results to return")


class SearchResult(BaseModel):
    """Individual search result."""

    docId: str
    type: str
    score: float = Field(..., ge=0.0, le=1.0)
    matchReason: str
    
    # Common fields
    title: str | None = None
    description: str | None = None
    
    # Report-specific fields
    url: str | None = None
    category: str | None = None
    platform: str | None = None
    tags: list[str] | None = None
    
    # Glossary-specific fields
    term: str | None = None
    definition: str | None = None
    
    # FAQ-specific fields
    question: str | None = None
    answer: str | None = None


class SearchResponse(BaseModel):
    """Search response."""

    query: str
    total: int
    results: list[SearchResult]
    searchMode: Literal["semantic", "keyword", "hybrid"]


class ErrorResponse(BaseModel):
    """Error response."""

    error: str
    detail: str | None = None

