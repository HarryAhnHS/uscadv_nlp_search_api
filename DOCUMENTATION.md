# USC Advancement NLP Search API - Technical Documentation

## 1. Model Documentation

### 1.1 Purpose and Architecture

**Purpose:** Provide semantic and keyword search capabilities for the Advancement BI Hub, enabling users to find reports, training videos, glossary terms, and FAQs using natural language queries.

**Architecture Overview:**

```
┌─────────────────────────────────────────────────────────────────┐
│                         FastAPI Server                          │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │                    /search endpoint                       │  │
│  │  ┌─────────────────────────────────────────────────────┐ │  │
│  │  │              Hybrid Search Engine                    │ │  │
│  │  │  ┌──────────────┐      ┌──────────────────────────┐ │ │  │
│  │  │  │   Semantic   │      │       Keyword            │ │ │  │
│  │  │  │   (FAISS)    │      │    (SQLite FTS5)         │ │ │  │
│  │  │  └──────────────┘      └──────────────────────────┘ │ │  │
│  │  │         ↓                        ↓                   │ │  │
│  │  │    Score Normalization → Weighted Blending → Ranking │ │  │
│  │  └─────────────────────────────────────────────────────┘ │  │
│  └──────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                              ↑
                    ┌─────────┴─────────┐
                    │   Index Store     │
                    │  (Singleton)      │
                    └───────────────────┘
                              ↑
        ┌─────────────────────┼─────────────────────┐
        ↓                     ↓                     ↓
┌───────────────┐    ┌───────────────┐    ┌───────────────┐
│  index.faiss  │    │ metadata.jsonl│    │   search.db   │
│  (vectors)    │    │   (docs)      │    │    (FTS5)     │
└───────────────┘    └───────────────┘    └───────────────┘
```

**Key Components:**
- **FastAPI Server** (`app/main.py`): REST API with `/health` and `/search` endpoints
- **Hybrid Engine** (`app/hybrid.py`): Blends semantic and keyword search scores
- **Semantic Search** (`app/semantic.py`): FAISS vector similarity search
- **Keyword Search** (`app/keyword.py`): SQLite FTS5 full-text search
- **Index Store** (`app/index_store.py`): Singleton for index management with LRU cache

### 1.2 Preprocessing Steps

**Index-Time Preprocessing:**

1. **Data Fetching** (`scripts/fetch_sharepoint.py`)
   - Authenticate via OAuth2 refresh token flow
   - Fetch documents from SharePoint lists/libraries
   - Transform to normalized schema

2. **Text Canonicalization** (`scripts/build_index.py`)
   - Create type-specific canonical text for embedding:
     - Reports: `"Report: {title} {description} Category: {category} Platform: {platform} Tags: {tags}"`
     - Training Videos: `"Training Video: {title} {description}"`
     - Glossary: `"Glossary Term: {term} Definition: {definition}"`
     - FAQs: `"FAQ: {question} Answer: {answer}"`

3. **Embedding Generation**
   - Model: `sentence-transformers/all-MiniLM-L6-v2`
   - Dimension: 384
   - L2 normalization applied for cosine similarity

4. **Index Building**
   - FAISS IndexFlatIP (inner product on normalized vectors = cosine similarity)
   - SQLite FTS5 with Porter stemming tokenizer

### 1.3 Algorithm Description

**Hybrid Search Algorithm:**

```
Input: query string, optional filters (type, category), top_k

1. Query Analysis:
   - is_acronym: regex match [A-Z]{2,6}
   - is_short: word count <= 2

2. Weight Computation:
   - Acronym: semantic=0.2, keyword=0.8
   - Short: semantic=0.4, keyword=0.6
   - Natural language: semantic=0.7, keyword=0.3

3. Parallel Search:
   - Semantic: embed query → FAISS search → top 30
   - Keyword: tokenize → FTS5 MATCH → top 30

4. Score Normalization:
   - Min-max normalize each source to [0, 1]

5. Score Blending:
   - blended_score = (semantic_weight × sem_score) + (keyword_weight × kw_score)

6. Merge & Rank:
   - Deduplicate by docId
   - Sort by blended_score descending
   - Return top_k with match_reason

Output: ranked results with scores and explanations
```

### 1.4 Inference Flow

```
User Query: "how do I track my fundraising progress"
    ↓
Query Analysis: is_short=false, is_acronym=false
    ↓
Weights: semantic=0.7, keyword=0.3
    ↓
┌─────────────────────────────┐
│   Semantic Search           │
│   - Check LRU cache         │
│   - Generate embedding      │
│   - FAISS.search(k=30)      │
│   - Return with scores      │
└─────────────────────────────┘
    ↓                         
┌─────────────────────────────┐
│   Keyword Search            │
│   - Build FTS5 query        │
│   - Execute MATCH           │
│   - BM25 scoring            │
│   - Return top 30           │
└─────────────────────────────┘
    ↓
Score Normalization → Blending → Ranking
    ↓
Response: {results: [...], searchMode: "hybrid", total: N}
```

### 1.5 Data Dependencies and Schema

**Input Schema (docs.json):**

```json
// Report
{
  "docId": "uuid",
  "type": "report",
  "title": "string",
  "description": "string",
  "url": "string",
  "category": "string",
  "platform": "Tableau|Cognos|Power BI",
  "tags": ["string"]
}

// Training Video
{
  "docId": "video-{id}",
  "type": "training_video",
  "title": "string",
  "description": "string",
  "category": "string"
}

// Glossary
{
  "docId": "glossary-{id}",
  "type": "glossary",
  "term": "string",
  "definition": "string"
}

// FAQ
{
  "docId": "faq-{id}",
  "type": "faq",
  "question": "string",
  "answer": "string"
}
```

**Output Schema (API Response):**

```json
{
  "query": "string",
  "total": "integer",
  "searchMode": "hybrid|semantic|keyword",
  "results": [
    {
      "docId": "string",
      "type": "string",
      "score": "float (0-1)",
      "matchReason": "string",
      "title": "string (unified display field)",
      // Type-specific fields...
    }
  ]
}
```

### 1.6 Retraining & Versioning

**Retraining Criteria:**
- New document types added
- Significant changes to document content/structure
- Embedding model upgrade desired
- Poor search relevance reported

**Versioning Approach:**
- Data version: timestamp in docs.json
- Index version: rebuild timestamp
- Model version: EMBED_MODEL environment variable
- API version: Semantic versioning in FastAPI metadata

**Validation Workflow:**
1. Run test queries from README demo sequence
2. Verify expected results appear in top 5
3. Check searchMode distribution across query types
4. Validate all document types return correctly

---

## 2. Maintenance Requirements

### 2.1 Updating Model with Data Changes

**When SharePoint data changes:**
```bash
# 1. Refresh data
python scripts/fetch_sharepoint.py

# 2. Rebuild indexes
python scripts/build_index.py --force

# 3. Restart server
# (automatic with --reload, otherwise restart process)
```

**When schema changes:**
1. Update `LIST_CONFIGS` in `scripts/fetch_sharepoint.py`
2. Update transform function for affected type
3. Update `create_canonical_text()` in `scripts/build_index.py`
4. Update `normalize_document()` in `scripts/build_index.py`
5. Update response mapping in `app/main.py`
6. Update `SearchResult` model in `app/models.py`

### 2.2 Monitoring Routines

**Health Check:**
```bash
curl http://localhost:8000/health
# Expected: {"status":"ok","index_loaded":true,"document_count":N}
```

**Metrics to Monitor:**
- Response time p50/p95/p99
- Search requests per minute
- Error rate (5xx responses)
- Index load time on startup
- Memory usage (embedding model ~200MB)

### 2.3 Common Failure Modes

| Symptom | Cause | Resolution |
|---------|-------|------------|
| 500 on /search | Index not loaded | Check /health, rebuild if needed |
| Empty results | Query too specific | Try broader terms, check filters |
| Slow first query | Model cold start | Expected, ~2-3s first query |
| Auth errors in fetch | Token expired | Run `python helpers/get_token.py` |
| Missing documents | Fetch didn't include type | Check LIST_CONFIGS enabled flags |

### 2.4 Known Limitations

- **No real-time indexing**: Changes require manual rebuild
- **No permission filtering**: All results visible to all users
- **English only**: Embedding model trained on English
- **Max document size**: Very long descriptions may be truncated
- **No query expansion**: Acronyms must exist in documents to match

### 2.5 Validation Tests

```bash
# Run smoke test
python tests/smoke_test.py

# Run unit tests
pytest tests/ -v

# Manual validation queries
curl "http://localhost:8000/search?q=prospect+ratings"
curl "http://localhost:8000/search?q=WPU"
curl "http://localhost:8000/search?q=how+to+use+tableau&type=training_video"
```

---

## 3. UI Documentation

### 3.1 Architecture Overview

**Current State:** API-only (no UI layer implemented)

**Planned Integration:** SPFx Web Part for SharePoint Online

**Integration Points:**
- Single `/search` endpoint for all queries
- `/health` endpoint for status monitoring
- CORS enabled for cross-origin requests from SharePoint

### 3.2 API Interaction Details

**Search Request:**
```
GET /search?q={query}&type={type}&category={category}&top_k={limit}

Parameters:
- q (required): Search query text, min 1 character
- type (optional): report | training_video | glossary | faq
- category (optional): Filter by category name
- top_k (optional): 1-100, default 10
```

**Search Response:**
```json
{
  "query": "prospect ratings",
  "total": 5,
  "searchMode": "hybrid",
  "results": [
    {
      "docId": "fc4284d4-79cb-4d9f-8543-6ce936ced728",
      "type": "report",
      "score": 0.8923,
      "matchReason": "strong semantic match + keyword match",
      "title": "Prospects Ratings and Predictive Scores",
      "description": "This dashboard provides...",
      "url": "http://...",
      "category": "Prospect Management",
      "platform": "Tableau",
      "tags": ["Prospect Development", "Wealth Screening"]
    }
  ]
}
```

**Health Response:**
```json
{
  "status": "ok",
  "index_loaded": true,
  "document_count": 314
}
```

**Error Response:**
```json
{
  "error": "Invalid request",
  "detail": "Query parameter 'q' is required"
}
```

---

## 4. Operational Notes

### 4.1 Required Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `TENANT_ID` | For SharePoint | Azure AD tenant ID |
| `CLIENT_ID` | For SharePoint | Azure AD app client ID |
| `CLIENT_SECRET` | For SharePoint | Azure AD app client secret |
| `REFRESH_TOKEN` | For SharePoint | OAuth2 refresh token |
| `EMBED_MODEL` | No | Sentence transformer model (default: all-MiniLM-L6-v2) |

### 4.2 Configuration Files

| File | Purpose |
|------|---------|
| `.env` | Environment variables (not in repo) |
| `requirements.txt` | Python dependencies |
| `data/docs.json` | Source documents |
| `data/index.faiss` | Vector embeddings |
| `data/metadata.jsonl` | Document metadata |
| `data/search.db` | FTS5 keyword index |

### 4.3 Runtime Assumptions

- Python 3.11+ required
- ~500MB RAM for embedding model
- ~100MB disk for indexes (scales with document count)
- Single-threaded embedding (use workers for parallelism)
- Indexes loaded on startup, held in memory

### 4.4 Logging Locations

**Current:** stdout via uvicorn

**Log Levels:**
- INFO: Startup, document count, query processing
- WARNING: Token expiration, missing fields
- ERROR: Search failures, index load errors

**Debugging Procedures:**
```bash
# Verbose server output
uvicorn app.main:app --reload --log-level debug

# Check index contents
python -c "import json; print(len(json.load(open('data/docs.json'))))"

# Verify FAISS index
python -c "import faiss; idx = faiss.read_index('data/index.faiss'); print(idx.ntotal)"
```

### 4.5 Technical Debt & Deferred Items

| Item | Priority | Notes |
|------|----------|-------|
| Permission filtering | High | Filter results by user groups |
| Incremental indexing | Medium | Only re-embed changed docs |
| Query analytics | Medium | Track queries for relevance tuning |
| Structured logging | Medium | JSON logs for aggregation |
| Rate limiting | Low | Prevent abuse |
| Caching layer | Low | Redis for query result caching |
| Synonym expansion | Low | Domain-specific query expansion |

---

## 5. Appendix

### 5.1 File Inventory

```
app/
  __init__.py         - Package init
  main.py             - FastAPI endpoints (168 lines)
  models.py           - Pydantic schemas (67 lines)
  hybrid.py           - Score blending (238 lines)
  semantic.py         - FAISS search (116 lines)
  keyword.py          - FTS5 search (178 lines)
  index_store.py      - Index management (145 lines)

scripts/
  fetch_sharepoint.py - Data ingestion (570 lines)
  build_index.py      - Index building (398 lines)

helpers/
  get_token.py        - OAuth helper (89 lines)
  discover_fields.py  - SharePoint field discovery (226 lines)

data/
  docs.json           - Source documents
  index.faiss         - Vector index
  metadata.jsonl      - Document metadata
  search.db           - SQLite FTS5 index
```

### 5.2 Dependencies

```
fastapi==0.115.6          # Web framework
uvicorn[standard]==0.30.6 # ASGI server
sentence-transformers==3.0.1  # Embeddings
faiss-cpu==1.8.0.post1    # Vector search
numpy==1.26.4             # Numerical ops
python-dotenv==1.0.1      # Env management
pydantic==2.9.2           # Data validation
ruff==0.7.4               # Linting
pytest==8.3.3             # Testing
httpx==0.27.2             # HTTP client for tests
```

