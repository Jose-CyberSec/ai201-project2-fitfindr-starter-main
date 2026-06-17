"""
agent.py

The FitFindr planning loop. Orchestrates the three tools in response to a
natural language user query, passing state between them via a session dict.

Usage:
    from agent import run_agent
    from utils.data_loader import get_example_wardrobe

    result = run_agent(
        query="vintage graphic tee under $30, size M",
        wardrobe=get_example_wardrobe(),
    )
    print(result["fit_card"])
    print(result["error"])  # None on success
"""

import re
from tools import search_listings, suggest_outfit, create_fit_card


# ── session state ─────────────────────────────────────────────────────────────

def _new_session(query: str, wardrobe: dict) -> dict:
    """Initialize and return a fresh session dict for one user interaction."""
    return {
        "query": query,
        "parsed": {},
        "search_results": [],
        "selected_item": None,
        "wardrobe": wardrobe,
        "outfit_suggestion": None,
        "fit_card": None,
        "error": None,
    }


# ── query parser ──────────────────────────────────────────────────────────────

def _parse_query(query: str) -> dict:
    """
    Extract description, size, and max_price from a natural language query
    using regex patterns.

    Returns a dict with keys: description (str), size (str|None), max_price (float|None).
    """
    q = query.lower()

    # Extract price: "under $30", "under 30", "$30 or less", "max $40"
    price_match = re.search(
        r'(?:under|below|less than|max|maximum|up to)\s*\$?\s*(\d+(?:\.\d+)?)',
        q
    )
    max_price = float(price_match.group(1)) if price_match else None

    # Extract size: standalone S, M, L, XL, XXL, XS, or "size M/L/etc."
    size_match = re.search(
        r'\bsize\s+([a-z0-9/]+)\b|\b(xxs|xs|s/m|m/l|l/xl|xl/xxl|xxl|xl|xs|s|m|l)\b',
        q
    )
    if size_match:
        size = (size_match.group(1) or size_match.group(2)).upper()
    else:
        size = None

    # Description: remove price/size phrases from the query
    description = query
    if price_match:
        description = description[:price_match.start()].strip()
    if size_match:
        # Remove the size clause from description
        description = re.sub(
            r',?\s*(?:size\s+)?(?:xxs|xs|s/m|m/l|l/xl|xl/xxl|xxl|xl|xs|s|m|l)\b',
            '',
            description,
            flags=re.IGNORECASE
        ).strip()
    # Clean trailing punctuation / filler words
    description = re.sub(r'\b(under|below|for|in|a|an|the)\s*$', '', description, flags=re.IGNORECASE).strip(' ,')

    return {
        "description": description or query,
        "size": size,
        "max_price": max_price,
    }


# ── planning loop ─────────────────────────────────────────────────────────────

def run_agent(query: str, wardrobe: dict) -> dict:
    """
    Main agent entry point. Runs the FitFindr planning loop for a single
    user interaction and returns the completed session dict.

    Planning loop logic:
        1. Parse query → extract description, size, max_price
        2. search_listings() → if empty, set error and return early
        3. Select top result → store as selected_item
        4. suggest_outfit() → store outfit_suggestion
        5. create_fit_card() → store fit_card
        6. Return completed session

    Args:
        query: Natural language user request
        wardrobe: User's wardrobe dict

    Returns:
        Session dict. Check session["error"] first — if not None, the
        interaction ended early and outfit_suggestion / fit_card will be None.
    """
    # Step 1: Initialize session
    session = _new_session(query, wardrobe)

    # Step 2: Parse the query
    parsed = _parse_query(query)
    session["parsed"] = parsed

    # Step 3: Search listings
    results = search_listings(
        description=parsed["description"],
        size=parsed["size"],
        max_price=parsed["max_price"],
    )
    session["search_results"] = results

    # Branch: no results → set error and return early
    if not results:
        filters_used = []
        if parsed["size"]:
            filters_used.append(f"size {parsed['size']}")
        if parsed["max_price"] is not None:
            filters_used.append(f"under ${parsed['max_price']:.0f}")
        filter_str = " and ".join(filters_used)
        hint = (
            f" Try removing the {filter_str} filter"
            if filter_str else " Try different keywords"
        )
        session["error"] = (
            f"No listings found for \"{parsed['description']}\""
            + (f" with {filter_str}" if filter_str else "")
            + f".{hint}, or broaden your search."
        )
        return session

    # Step 4: Select top result
    session["selected_item"] = results[0]

    # Step 5: Suggest outfit
    outfit = suggest_outfit(
        new_item=session["selected_item"],
        wardrobe=session["wardrobe"],
    )
    session["outfit_suggestion"] = outfit

    # Step 6: Create fit card
    fit_card = create_fit_card(
        outfit=outfit,
        new_item=session["selected_item"],
    )
    session["fit_card"] = fit_card

    # Step 7: Return completed session
    return session


# ── CLI test ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    from utils.data_loader import get_example_wardrobe, get_empty_wardrobe

    print("=== Happy path: graphic tee ===\n")
    session = run_agent(
        query="looking for a vintage graphic tee under $30",
        wardrobe=get_example_wardrobe(),
    )
    if session["error"]:
        print(f"Error: {session['error']}")
    else:
        print(f"Found:   {session['selected_item']['title']}")
        print(f"\nOutfit:  {session['outfit_suggestion']}")
        print(f"\nFit card: {session['fit_card']}")

    print("\n\n=== No-results path ===\n")
    session2 = run_agent(
        query="designer ballgown size XXS under $5",
        wardrobe=get_example_wardrobe(),
    )
    print(f"Error message: {session2['error']}")