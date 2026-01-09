"""Integration tests for FastAPI endpoints."""

import pytest
from fastapi.testclient import TestClient

# These tests require the indexes to be built
# Skip if indexes don't exist


@pytest.fixture
def client():
    """Create test client. Skips if indexes not available."""
    try:
        from app.main import app
        return TestClient(app)
    except Exception as e:
        pytest.skip(f"Could not load app: {e}")


class TestHealthEndpoint:
    """Tests for /health endpoint."""

    def test_health_returns_200(self, client):
        response = client.get("/health")
        assert response.status_code == 200

    def test_health_has_required_fields(self, client):
        response = client.get("/health")
        data = response.json()
        assert "status" in data
        assert "index_loaded" in data
        assert "document_count" in data

    def test_health_status_ok(self, client):
        response = client.get("/health")
        data = response.json()
        assert data["status"] == "ok"


class TestSearchEndpoint:
    """Tests for /search endpoint."""

    def test_search_requires_query(self, client):
        response = client.get("/search")
        assert response.status_code == 422  # Validation error

    def test_search_empty_query_rejected(self, client):
        response = client.get("/search?q=")
        assert response.status_code == 422

    def test_search_returns_200(self, client):
        response = client.get("/search?q=test")
        assert response.status_code == 200

    def test_search_response_structure(self, client):
        response = client.get("/search?q=donor")
        assert response.status_code == 200
        data = response.json()
        assert "query" in data
        assert "total" in data
        assert "results" in data
        assert "searchMode" in data

    def test_search_query_echoed(self, client):
        response = client.get("/search?q=fundraising")
        data = response.json()
        assert data["query"] == "fundraising"

    def test_search_top_k_limits_results(self, client):
        response = client.get("/search?q=report&top_k=3")
        data = response.json()
        assert len(data["results"]) <= 3

    def test_search_type_filter(self, client):
        response = client.get("/search?q=help&type=glossary")
        data = response.json()
        for result in data["results"]:
            assert result["type"] == "glossary"

    def test_search_invalid_type_accepted(self, client):
        # Invalid type should not error, just return no results
        response = client.get("/search?q=test&type=invalid_type")
        assert response.status_code == 200

    def test_search_result_has_score(self, client):
        response = client.get("/search?q=prospect")
        data = response.json()
        if data["results"]:
            result = data["results"][0]
            assert "score" in result
            assert 0 <= result["score"] <= 1

    def test_search_result_has_match_reason(self, client):
        response = client.get("/search?q=dashboard")
        data = response.json()
        if data["results"]:
            result = data["results"][0]
            assert "matchReason" in result
            assert len(result["matchReason"]) > 0


class TestSearchModes:
    """Tests for different search modes based on query type."""

    def test_acronym_search(self, client):
        response = client.get("/search?q=WPU")
        assert response.status_code == 200
        data = response.json()
        # Acronyms should work (may or may not find results)
        assert "searchMode" in data

    def test_natural_language_search(self, client):
        response = client.get("/search?q=how+do+I+track+my+fundraising+progress")
        assert response.status_code == 200
        data = response.json()
        assert "searchMode" in data

    def test_short_query_search(self, client):
        response = client.get("/search?q=donors")
        assert response.status_code == 200
        data = response.json()
        assert "searchMode" in data


class TestTopKParameter:
    """Tests for top_k parameter validation."""

    def test_top_k_minimum(self, client):
        response = client.get("/search?q=test&top_k=1")
        assert response.status_code == 200

    def test_top_k_maximum(self, client):
        response = client.get("/search?q=test&top_k=100")
        assert response.status_code == 200

    def test_top_k_below_minimum(self, client):
        response = client.get("/search?q=test&top_k=0")
        assert response.status_code == 422

    def test_top_k_above_maximum(self, client):
        response = client.get("/search?q=test&top_k=101")
        assert response.status_code == 422

    def test_top_k_default(self, client):
        response = client.get("/search?q=test")
        data = response.json()
        # Default is 10, but may return fewer if less available
        assert len(data["results"]) <= 10

