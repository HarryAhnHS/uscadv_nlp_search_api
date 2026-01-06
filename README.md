# USC Advancement NLP Search API

A hybrid search API for the Advancement BI Hub. Combines semantic search (FAISS) with keyword search (SQLite FTS5) to find reports, training videos, and glossary terms.

## Setup

1. Create a virtual environment and install dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

2. Build the search indexes from the mock data:

```bash
python scripts/build_index.py
```

This creates three files in `data/`:
- `index.faiss` - vector index for semantic search
- `metadata.jsonl` - document metadata
- `search.db` - SQLite database for keyword search

Use `--force` to rebuild if the files already exist.

## Running the Server

```bash
source .venv/bin/activate
uvicorn app.main:app --reload
```

The API runs at http://localhost:8000. Interactive docs are at http://localhost:8000/docs.

## API Usage

### Health Check

```bash
curl http://localhost:8000/health
```

Returns index status and document count.

### Search

Basic search:

```bash
curl "http://localhost:8000/search?q=fundraising+dashboard"
```

With filters:

```bash
# Filter by type (report, training_video, glossary)
curl "http://localhost:8000/search?q=prospect&type=glossary"

# Filter by category
curl "http://localhost:8000/search?q=financial&category=Keck%20Medicine"

# Limit results
curl "http://localhost:8000/search?q=donor&top_k=5"
```

### Query Tips

The search automatically adjusts how it weights results based on your query:

- Short queries and acronyms (like "LYBUNT" or "WPU") lean more on exact keyword matching
- Longer, natural language queries (like "how to track donor retention") rely more on semantic understanding

Each result includes a `matchReason` field explaining why it matched, and a `score` between 0 and 1.

### Response Format

```json
{
  "query": "prospect ratings",
  "total": 3,
  "searchMode": "hybrid",
  "results": [
    {
      "docId": "fc4284d4-...",
      "type": "report",
      "score": 0.89,
      "matchReason": "strong semantic match + keyword match",
      "title": "Prospects Ratings and Predictive Scores",
      "description": "...",
      "url": "http://...",
      "category": "Prospect Management",
      "platform": "Tableau",
      "tags": ["Development Officers", "Prospect Development"]
    }
  ]
}
```

## Configuration

Set these environment variables as needed:

- `EMBED_MODEL` - Sentence transformer model (default: `all-MiniLM-L6-v2`)

## Project Structure

```
app/
  main.py        - FastAPI endpoints
  models.py      - Request/response schemas
  hybrid.py      - Score blending and ranking
  semantic.py    - FAISS vector search
  keyword.py     - SQLite FTS5 search
  index_store.py - Index loading and caching
  auth.py        - Auth placeholder
scripts/
  build_index.py - Index builder
data/
  mock_docs.json - Source documents
```

## Test Cases for Demo

Sample queries to demonstrate hybrid search capabilities.

### Natural Language Questions
```
how do I track my fundraising progress
which donors haven't given this year
where can I see my portfolio performance
learn how to use the reporting tools
what does it mean when a gift is promised but not received
how do I enter a contact report
```

### Acronyms
```
LYBUNT
SYBUNT
WPU
Keck
```

### Concept Searches (no exact keyword match)
```
wealth capacity
donor follow-up after a gift
how to prioritize who to visit
keeping donors engaged
lapsed donor outreach
```

### Cross-Type Discovery
```
prospect ratings
proposals
endowment
stewardship
```

### With Type Filter
```
how to enter data                    [type=training_video]
donor                                [type=glossary]
campaign performance                 [type=report]
```

### With Category Filter
```
financial summary                    [category=Keck Medicine]
contact reports                      [category=Prospect Management]
```

### Demo Sequence
```
1. LYBUNT
2. how do I see which donors stopped giving
3. track fundraiser performance against goals
4. prospect ratings
5. how to use tableau
6. Keck financial
```
