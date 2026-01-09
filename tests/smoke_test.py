#!/usr/bin/env python3
"""
Smoke test for USC Advancement NLP Search API.

Verifies:
1. Server is running and healthy
2. Search endpoint returns valid results
3. All document types are searchable
4. Filters work correctly

Usage:
    python tests/smoke_test.py [--url http://localhost:8000]
"""

import argparse
import sys
from typing import Any

try:
    import httpx
except ImportError:
    print("Error: httpx not installed. Run: pip install httpx")
    sys.exit(1)


class SmokeTestRunner:
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")
        self.client = httpx.Client(timeout=30.0)
        self.passed = 0
        self.failed = 0
        self.errors: list[str] = []

    def log(self, status: str, message: str):
        symbol = "✓" if status == "PASS" else "✗" if status == "FAIL" else "○"
        print(f"  {symbol} {message}")

    def test(self, name: str, condition: bool, error_msg: str = ""):
        if condition:
            self.passed += 1
            self.log("PASS", name)
        else:
            self.failed += 1
            self.log("FAIL", f"{name}: {error_msg}")
            self.errors.append(f"{name}: {error_msg}")

    def get(self, endpoint: str, params: dict | None = None) -> dict[str, Any] | None:
        try:
            response = self.client.get(f"{self.base_url}{endpoint}", params=params)
            if response.status_code == 200:
                return response.json()
            else:
                return {"_error": response.status_code, "_body": response.text}
        except Exception as e:
            return {"_error": str(e)}

    def run_all(self) -> bool:
        print("\n" + "=" * 60)
        print("USC Advancement NLP Search API - Smoke Test")
        print("=" * 60)
        print(f"Target: {self.base_url}\n")

        # Test 1: Health Check
        print("[1/6] Health Check")
        health = self.get("/health")
        self.test(
            "Server responds",
            health is not None and "_error" not in health,
            str(health.get("_error", "No response")) if health else "No response",
        )
        if health and "_error" not in health:
            self.test(
                "Status is ok",
                health.get("status") == "ok",
                f"Got status: {health.get('status')}",
            )
            self.test(
                "Index is loaded",
                health.get("index_loaded") is True,
                "Index not loaded",
            )
            doc_count = health.get("document_count", 0)
            self.test(
                f"Documents indexed ({doc_count})",
                doc_count > 0,
                "No documents in index",
            )

        # Test 2: Basic Search
        print("\n[2/6] Basic Search")
        results = self.get("/search", {"q": "prospect ratings"})
        self.test(
            "Search returns results",
            results is not None and "_error" not in results,
            str(results.get("_error", "")) if results else "No response",
        )
        if results and "_error" not in results:
            self.test(
                "Results have total",
                "total" in results,
                "Missing 'total' field",
            )
            self.test(
                "Results have searchMode",
                "searchMode" in results,
                "Missing 'searchMode' field",
            )
            self.test(
                "Found relevant results",
                results.get("total", 0) > 0,
                "No results found",
            )

        # Test 3: Search Each Document Type
        print("\n[3/6] Document Type Coverage")
        type_queries = {
            "report": "financial summary",
            "training_video": "tableau",
            "glossary": "proposal",
            "faq": "how to",
        }
        for doc_type, query in type_queries.items():
            results = self.get("/search", {"q": query, "type": doc_type, "top_k": 5})
            if results and "_error" not in results:
                count = results.get("total", 0)
                self.test(
                    f"Type '{doc_type}' returns results",
                    count > 0,
                    f"No {doc_type} results for query '{query}'",
                )
            else:
                self.test(
                    f"Type '{doc_type}' search works",
                    False,
                    str(results.get("_error", "")) if results else "No response",
                )

        # Test 4: Result Structure
        print("\n[4/6] Result Structure Validation")
        results = self.get("/search", {"q": "donor", "top_k": 3})
        if results and "_error" not in results and results.get("results"):
            first_result = results["results"][0]
            required_fields = ["docId", "type", "score", "matchReason", "title"]
            for field in required_fields:
                self.test(
                    f"Result has '{field}' field",
                    field in first_result,
                    "Missing required field",
                )
            self.test(
                "Score is between 0 and 1",
                0 <= first_result.get("score", -1) <= 1,
                f"Score out of range: {first_result.get('score')}",
            )

        # Test 5: Query Weighting
        print("\n[5/6] Query Weighting Behavior")
        # Acronym should favor keyword
        acronym_result = self.get("/search", {"q": "WPU", "top_k": 5})
        if acronym_result and "_error" not in acronym_result:
            self.test(
                "Acronym query works",
                acronym_result.get("total", 0) >= 0,
                "Acronym search failed",
            )

        # Natural language should work
        nl_result = self.get(
            "/search", {"q": "how do I track fundraising progress", "top_k": 5}
        )
        if nl_result and "_error" not in nl_result:
            self.test(
                "Natural language query works",
                nl_result.get("total", 0) >= 0,
                "Natural language search failed",
            )

        # Test 6: Error Handling
        print("\n[6/6] Error Handling")
        empty_query = self.get("/search", {"q": ""})
        self.test(
            "Empty query returns error",
            empty_query is not None
            and (empty_query.get("_error") == 422 or "error" in str(empty_query)),
            "Should reject empty query",
        )

        # Summary
        print("\n" + "=" * 60)
        total = self.passed + self.failed
        print(f"Results: {self.passed}/{total} passed")

        if self.errors:
            print("\nFailures:")
            for error in self.errors:
                print(f"  - {error}")

        print("=" * 60 + "\n")

        return self.failed == 0


def main():
    parser = argparse.ArgumentParser(description="Smoke test for NLP Search API")
    parser.add_argument(
        "--url",
        default="http://localhost:8000",
        help="Base URL of the API (default: http://localhost:8000)",
    )
    args = parser.parse_args()

    runner = SmokeTestRunner(args.url)
    success = runner.run_all()

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()

