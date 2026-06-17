"""
tests/test_tools.py

Run with:
    pytest tests/
"""

import pytest
from tools import search_listings, suggest_outfit, create_fit_card
from utils.data_loader import get_example_wardrobe, get_empty_wardrobe


# ── search_listings ───────────────────────────────────────────────────────────

def test_search_returns_results():
    results = search_listings("vintage graphic tee", size=None, max_price=50)
    assert isinstance(results, list)
    assert len(results) > 0


def test_search_empty_results():
    results = search_listings("designer ballgown", size="XXS", max_price=5)
    assert results == []


def test_search_price_filter():
    results = search_listings("jacket", size=None, max_price=20)
    assert all(item["price"] <= 20 for item in results)


def test_search_size_filter():
    results = search_listings("top", size="M", max_price=None)
    # All returned items should have 'M' somewhere in their size field
    for item in results:
        assert "m" in (item.get("size") or "").lower()


def test_search_returns_list_on_no_keywords():
    # Even with a very short/vague query, should return a list not raise
    results = search_listings("", size=None, max_price=None)
    assert isinstance(results, list)


# ── suggest_outfit ────────────────────────────────────────────────────────────

def test_suggest_outfit_with_wardrobe():
    results = search_listings("vintage graphic tee", size=None, max_price=50)
    assert len(results) > 0
    suggestion = suggest_outfit(results[0], get_example_wardrobe())
    assert isinstance(suggestion, str)
    assert len(suggestion) > 10  # Not empty


def test_suggest_outfit_empty_wardrobe():
    results = search_listings("vintage graphic tee", size=None, max_price=50)
    assert len(results) > 0
    suggestion = suggest_outfit(results[0], get_empty_wardrobe())
    # Should return general advice, not crash
    assert isinstance(suggestion, str)
    assert len(suggestion) > 10


# ── create_fit_card ───────────────────────────────────────────────────────────

def test_create_fit_card_returns_string():
    results = search_listings("vintage graphic tee", size=None, max_price=50)
    assert len(results) > 0
    card = create_fit_card("Pair with wide-leg jeans and chunky sneakers.", results[0])
    assert isinstance(card, str)
    assert len(card) > 10


def test_create_fit_card_empty_outfit():
    results = search_listings("vintage graphic tee", size=None, max_price=50)
    assert len(results) > 0
    card = create_fit_card("", results[0])
    # Should return an error message string, not raise
    assert isinstance(card, str)
    assert "error" in card.lower() or len(card) > 5


def test_create_fit_card_whitespace_outfit():
    results = search_listings("jacket", size=None, max_price=100)
    assert len(results) > 0
    card = create_fit_card("   ", results[0])
    assert isinstance(card, str)
    assert "error" in card.lower()
