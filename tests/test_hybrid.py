"""Unit tests for hybrid search logic."""

import re
import pytest


# Copy functions from hybrid.py to avoid FAISS import during testing
# This allows unit tests to run without loading the full index

def _is_short_query(query: str) -> bool:
    """Check if query is short (1-2 words)."""
    words = query.strip().split()
    return len(words) <= 2


def _is_acronym_query(query: str) -> bool:
    """Check if query looks like an acronym."""
    cleaned = query.strip()
    if re.match(r'^[A-Z]{2,6}$', cleaned):
        return True
    if re.match(r'^[A-Z][A-Za-z]{1,5}$', cleaned) and cleaned.isupper():
        return True
    return False


def _compute_blend_weights(query: str) -> tuple[float, float]:
    """Compute blending weights for semantic vs keyword search."""
    is_short = _is_short_query(query)
    is_acronym = _is_acronym_query(query)
    
    if is_acronym:
        return 0.2, 0.8
    elif is_short:
        return 0.4, 0.6
    else:
        return 0.7, 0.3


def _normalize_scores(results: list[dict], source: str) -> list[dict]:
    """Normalize scores to 0-1 range using min-max normalization."""
    if not results:
        return results
    
    scores = [r["score"] for r in results]
    min_score = min(scores)
    max_score = max(scores)
    
    score_range = max_score - min_score
    if score_range == 0:
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


class TestQueryAnalysis:
    """Tests for query classification functions."""

    def test_is_short_query_single_word(self):
        assert _is_short_query("WPU") is True

    def test_is_short_query_two_words(self):
        assert _is_short_query("prospect ratings") is True

    def test_is_short_query_three_words(self):
        assert _is_short_query("track donor giving") is False

    def test_is_short_query_long_sentence(self):
        assert _is_short_query("how do I track my fundraising progress") is False

    def test_is_acronym_uppercase(self):
        assert _is_acronym_query("WPU") is True
        assert _is_acronym_query("PRM") is True
        assert _is_acronym_query("OMAG") is True

    def test_is_acronym_too_short(self):
        assert _is_acronym_query("A") is False

    def test_is_acronym_too_long(self):
        assert _is_acronym_query("ABCDEFGH") is False

    def test_is_acronym_lowercase(self):
        assert _is_acronym_query("wpu") is False

    def test_is_acronym_mixed_case(self):
        assert _is_acronym_query("Wpu") is False

    def test_is_acronym_with_numbers(self):
        assert _is_acronym_query("ABC123") is False


class TestBlendWeights:
    """Tests for weight computation based on query type."""

    def test_acronym_weights(self):
        sem, kw = _compute_blend_weights("WPU")
        assert sem == 0.2
        assert kw == 0.8

    def test_short_query_weights(self):
        sem, kw = _compute_blend_weights("donors")
        assert sem == 0.4
        assert kw == 0.6

    def test_natural_language_weights(self):
        sem, kw = _compute_blend_weights("how do I track fundraising progress")
        assert sem == 0.7
        assert kw == 0.3

    def test_weights_sum_to_one(self):
        queries = ["WPU", "donors", "how do I find prospects"]
        for query in queries:
            sem, kw = _compute_blend_weights(query)
            assert sem + kw == pytest.approx(1.0)


class TestScoreNormalization:
    """Tests for score normalization."""

    def test_normalize_empty_list(self):
        result = _normalize_scores([], "semantic")
        assert result == []

    def test_normalize_single_result(self):
        results = [{"score": 0.5, "metadata": {}}]
        normalized = _normalize_scores(results, "semantic")
        assert normalized[0]["normalized_score"] == 1.0

    def test_normalize_multiple_results(self):
        results = [
            {"score": 0.8, "metadata": {}},
            {"score": 0.4, "metadata": {}},
            {"score": 0.6, "metadata": {}},
        ]
        normalized = _normalize_scores(results, "semantic")
        # Max (0.8) should normalize to 1.0
        assert normalized[0]["normalized_score"] == 1.0
        # Min (0.4) should normalize to 0.0
        assert normalized[1]["normalized_score"] == 0.0
        # Middle (0.6) should normalize to 0.5
        assert normalized[2]["normalized_score"] == pytest.approx(0.5)

    def test_normalize_same_scores(self):
        results = [
            {"score": 0.5, "metadata": {}},
            {"score": 0.5, "metadata": {}},
        ]
        normalized = _normalize_scores(results, "semantic")
        # All same scores should normalize to 1.0
        assert all(r["normalized_score"] == 1.0 for r in normalized)


class TestMatchReason:
    """Tests for match reason generation."""

    def test_strong_semantic_match(self):
        reason = _generate_match_reason(0.8, None, 0.7, 0.3)
        assert "strong semantic match" in reason

    def test_exact_keyword_match(self):
        reason = _generate_match_reason(None, 0.9, 0.3, 0.7)
        assert "exact keyword match" in reason

    def test_combined_match(self):
        reason = _generate_match_reason(0.8, 0.8, 0.5, 0.5)
        assert "semantic" in reason
        assert "keyword" in reason

    def test_partial_matches(self):
        reason = _generate_match_reason(0.4, 0.4, 0.5, 0.5)
        assert "partial" in reason

    def test_fallback_reason(self):
        reason = _generate_match_reason(0.1, 0.1, 0.5, 0.5)
        assert len(reason) > 0  # Should return something


class TestEdgeCases:
    """Edge case tests."""

    def test_empty_query(self):
        # Empty query should be treated as short
        assert _is_short_query("") is True
        assert _is_acronym_query("") is False

    def test_whitespace_query(self):
        assert _is_short_query("   ") is True

    def test_special_characters(self):
        assert _is_acronym_query("A+B") is False
        assert _is_acronym_query("A&B") is False

