# USC Advancement NLP Search API

A hybrid search API for the Advancement BI Hub. Combines semantic search (FAISS) with keyword search (SQLite FTS5) to find reports, training videos, glossary terms, and FAQs.

## Setup

1. Create a virtual environment and install dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

2. Fetch data from SharePoint (requires credentials in `.env`):

```bash
python scripts/fetch_sharepoint.py
```

3. Build the search indexes:

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

For SharePoint integration (production data):

- `TENANT_ID` - Azure AD tenant ID
- `CLIENT_ID` - Azure AD app client ID
- `CLIENT_SECRET` - Azure AD app client secret
- `REFRESH_TOKEN` - Microsoft Graph refresh token

## Fetching Real Data from SharePoint

To use real SharePoint data instead of mock data:

```bash
# 1. Set up environment variables in .env file
# 2. Fetch reports from SharePoint
python scripts/fetch_sharepoint.py

# 3. Rebuild indexes with the new data
python scripts/build_index.py --force

# 4. Restart the server
uvicorn app.main:app --reload
```

The fetch script will create `data/docs.json` which `build_index.py` will automatically use if present.

## Project Structure

```
app/
  main.py           - FastAPI endpoints
  models.py         - Request/response schemas
  hybrid.py         - Score blending and ranking
  semantic.py       - FAISS vector search
  keyword.py        - SQLite FTS5 search
  index_store.py    - Index loading and caching
scripts/
  fetch_sharepoint.py - Fetch all content from SharePoint
  build_index.py      - Build FAISS + FTS indexes
  discover_fields.py  - Helper to find SharePoint field names
  get_token.py        - Helper to refresh OAuth tokens
data/
  docs.json         - Documents from SharePoint
```

## Test Cases

Sample natural language queries to demonstrate hybrid search capabilities.

### Semantic Search (Natural Language)

These queries test meaning-based matching where exact keywords may not appear in results:

```
how do I track my fundraising progress
which donors stopped giving this year
where can I see my portfolio assignments
how to prioritize which prospects to visit
keeping donors engaged after they give
how do I find wealthy prospects
what reports show campaign performance
```

### Keyword/Acronym Search

Short queries and acronyms rely more on exact keyword matching:

```
LYBUNT
SYBUNT
WPU
Keck
CFR
```

### Concept Discovery

Searches for concepts that should match related content across types:

```
prospect ratings
proposal pipeline
endowment funds
stewardship
donor retention
wealth screening
contact reports
pledges
```

### Training Video Queries

Natural language questions that should surface training content:

```
how to use tableau
learn about collections
how do I subscribe to a report
getting started with cognos
how to filter data in dashboards
```

### Glossary Term Lookups

Queries that should return glossary definitions:

```
what is a funded proposal
primary credit vs assist credit
what does win rate mean
proposal status definitions
```

### Cross-Type Discovery

Queries that should return mixed results (reports + videos + glossary):

```
proposals
prospect management
contact activity
fundraiser performance
```

### Filtered Searches

Test type and category filters:

```
# Type filters
subscriptions                        [type=training_video]
pledge                               [type=glossary]
alumni giving                        [type=report]

# Category filters
financial summary                    [category=Keck Medicine]
campaign performance                 [category=Athletics]
donor activity                       [category=Prospect Management]
```

### Demo Walkthrough

A suggested sequence for demonstrating the search:

```
1. LYBUNT
   → Should return glossary definition and related reports

2. which donors stopped giving
   → Semantic match to LYBUNT/SYBUNT content

3. proposal pipeline
   → Should return proposal-related reports and glossary terms

4. how to use tableau
   → Should prioritize training videos

5. prospect ratings
   → Should return Prospects Ratings report and related content

6. Keck financial summary
   → Should return Keck Medicine financial reports

7. what is primary credit
   → Should return glossary definition
```

### Edge Cases

```
empty query                          → should return error
single character                     → should handle gracefully  
very long query with many words      → should still work
special characters !@#$%             → should be handled
```
