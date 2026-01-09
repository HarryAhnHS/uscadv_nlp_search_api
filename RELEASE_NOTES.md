# Release Notes

## Version 1.0.0 - Initial Release

**Release Date:** January 2026

### Features Completed

#### Core Search Functionality
- **Hybrid Search Engine**: Combines semantic (FAISS) and keyword (SQLite FTS5) search
- **Query-Adaptive Weighting**: Automatically adjusts search weights based on query type
  - Acronyms (e.g., "WPU"): 80% keyword, 20% semantic
  - Short queries (1-2 words): 60% keyword, 40% semantic
  - Natural language: 30% keyword, 70% semantic
- **Score Normalization**: Min-max normalization ensures fair blending between sources
- **Match Reason Explanations**: Human-readable explanations for why results matched

#### Data Sources
- **Reports**: Fetched from SharePoint `Reports_Power_Automate` list
  - Includes title, description, URL, category, platform, tags
- **Training Videos**: Fetched from SharePoint `Training Resources` document library
  - Includes title, description (HTML stripped), category (from folder path)
- **Glossary Terms**: Fetched from SharePoint `Glossary Terms` list
  - Includes term and definition
- **FAQs**: Fetched from SharePoint `FAQs` list
  - Includes question and answer

#### API Endpoints
- `GET /health`: System health check with index status
- `GET /search`: Hybrid search with filters (type, category, top_k)
- Interactive API documentation at `/docs`

#### Developer Tools
- `scripts/fetch_sharepoint.py`: Fetch all content from SharePoint
- `scripts/build_index.py`: Build FAISS and FTS5 indexes
- `helpers/get_token.py`: OAuth2 token refresh helper
- `helpers/discover_fields.py`: SharePoint field name discovery

### Known Bugs
- None identified in testing

### Known Limitations
1. **No Real-Time Indexing**: Changes require manual rebuild of indexes
2. **No Permission Filtering**: All results visible to all users (filtering by `allowedGroups` not implemented)
3. **English Only**: Embedding model trained primarily on English text
4. **Token Expiration**: OAuth refresh tokens expire after 90 days of inactivity
5. **Cold Start Latency**: First query takes 2-3 seconds to load embedding model

### Deferred Items
| Item | Priority | Reason Deferred |
|------|----------|-----------------|
| Permission filtering by user groups | High | Requires authentication integration |
| Incremental indexing | Medium | Full rebuild is fast enough for current data volume |
| Query analytics dashboard | Medium | Not critical for MVP |
| Rate limiting | Low | Internal use only |
| Result caching (Redis) | Low | Current performance acceptable |
| Synonym expansion | Low | Semantic search handles most synonyms |

### Operational Considerations

#### Before Deployment
1. Ensure `.env` file has valid SharePoint credentials
2. Run `python scripts/fetch_sharepoint.py` to get fresh data
3. Run `python scripts/build_index.py` to build indexes
4. Run `python tests/smoke_test.py` to verify functionality

#### Monitoring
- Check `/health` endpoint for index status
- Monitor response times (target: < 200ms p95)
- Watch for token expiration errors in logs

#### Refresh Token Renewal
If the refresh token expires:
1. Run `python helpers/get_token.py`
2. Complete OAuth flow in browser
3. Paste authorization code into `helpers/auth_code.txt`
4. Update `REFRESH_TOKEN` in `.env`

---

## Changelog

### v1.0.0 (January 2026)
- Initial release with hybrid search
- Support for reports, training videos, glossary, FAQs
- SharePoint integration for data fetching
- FastAPI REST API with OpenAPI documentation
- Unit tests and smoke tests
- Comprehensive documentation

