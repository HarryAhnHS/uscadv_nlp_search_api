# USC Advancement NLP Search API

A hybrid search API for the Advancement BI Hub. Combines semantic search (FAISS) with keyword search (SQLite FTS5) to find reports, training videos, glossary terms, and FAQs.

## Setup

1. Create a virtual environment and install dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

2. Fetch data from SharePoint (requires `.env` with credentials):

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

- Short queries and acronyms (like "WPU" or "PRM") lean more on exact keyword matching
- Longer, natural language queries (like "how to track donor giving") rely more on semantic understanding

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

## Updating Data from SharePoint

To refresh content from SharePoint:

```bash
# 1. Ensure .env has valid credentials (REFRESH_TOKEN, TENANT_ID, CLIENT_ID, CLIENT_SECRET)

# 2. Fetch all content (reports, training videos, glossary, FAQs)
python scripts/fetch_sharepoint.py

# 3. Rebuild indexes
python scripts/build_index.py --force

# 4. Restart the server
uvicorn app.main:app --reload
```

If your refresh token expires, use the token helper:
```bash
python scripts/get_token.py
```

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
  get_token.py        - OAuth token refresh helper
data/
  docs.json         - Documents from SharePoint (reports, videos, glossary, FAQs)
  index.faiss       - Vector embeddings for semantic search
  metadata.jsonl    - Document metadata
  search.db         - SQLite FTS5 keyword index
```

## Test Cases for Demo

Sample queries to demonstrate hybrid search capabilities. These are natural language queries that a user might type.

### Natural Language Questions
```
how do I track my fundraising progress
where can I see recent gifts
how do I find high-capacity prospects
show me donor activity for my school
how do I subscribe to a report
where can I learn about Cognos
```

### Acronyms and Short Terms
```
WPU
PRM
Keck
OMAG
PLC
```

### Concept Searches (semantic understanding)
```
wealth screening and capacity
donor stewardship activities
tracking proposal pipeline
measuring fundraiser performance
finding major gift prospects
```

### Cross-Type Discovery
```
prospect ratings
proposals
endowment
pledges
contact reports
```

### With Type Filter
```
how to save reports                  [type=training_video]
proposal status                      [type=glossary]
financial summary                    [type=report]
```

### With Category Filter
```
donors                               [category=Keck Medicine]
annual giving                        [category=Marshall]
revenue                              [category=Classical California]
```

### Demo Sequence (recommended flow)
```
1. prospect ratings
2. how do I assess donor capacity
3. track fundraiser performance against goals
4. how to use custom views in Tableau
5. what is primary credit
6. Keck financial summary
7. endowment funds
8. how to search for reports in Cognos
```
