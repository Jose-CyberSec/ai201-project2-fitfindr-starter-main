"""
tools.py

The three required FitFindr tools. Each tool is a standalone function that
can be called and tested independently before being wired into the agent loop.

Tools:
    search_listings(description, size, max_price) → list[dict]
    suggest_outfit(new_item, wardrobe) → str
    create_fit_card(outfit, new_item) → str
"""

import os
from dotenv import load_dotenv
from groq import Groq
from utils.data_loader import load_listings

load_dotenv(encoding="utf-8")


# ── Groq client ───────────────────────────────────────────────────────────────

def _get_groq_client():
    """Initialize and return a Groq client using GROQ_API_KEY from .env."""
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise ValueError(
            "GROQ_API_KEY not set. Add it to a .env file in the project root."
        )
    return Groq(api_key=api_key)


# ── Tool 1: search_listings ───────────────────────────────────────────────────

def search_listings(
    description: str,
    size: str | None = None,
    max_price: float | None = None,
) -> list[dict]:
    """
    Search the mock listings dataset for items matching the description,
    optional size, and optional price ceiling.

    Args:
        description: Keywords describing what the user is looking for
                     (e.g., "vintage graphic tee").
        size: Size string to filter by, or None to skip size filtering.
              Matching is case-insensitive (e.g., "M" matches "S/M").
        max_price: Maximum price (inclusive), or None to skip price filtering.

    Returns:
        A list of matching listing dicts sorted by relevance (best match first).
        Returns an empty list if nothing matches — does NOT raise an exception.
        Each listing dict has: id, title, description, category, style_tags (list),
        size, condition, price (float), colors (list), brand, platform.
    """
    try:
        listings = load_listings()
    except Exception:
        return []

    # Step 1: Filter by price
    if max_price is not None:
        listings = [l for l in listings if l.get("price", 0) <= max_price]

    # Step 2: Filter by size (case-insensitive, partial match)
    if size is not None:
        size_lower = size.lower()
        listings = [
            l for l in listings
            if size_lower in (l.get("size") or "").lower()
        ]

    # Step 3: Score by keyword overlap with description
    keywords = [w.lower() for w in description.split() if len(w) > 2]

    def score(listing):
        text = " ".join([
            listing.get("title") or "",
            listing.get("description") or "",
            listing.get("category") or "",
            listing.get("brand") or "",
            " ".join(listing.get("style_tags") or []),
            " ".join(listing.get("colors") or []),
        ]).lower()
        return sum(1 for kw in keywords if kw in text)

    scored = [(score(l), l) for l in listings]

    # Step 4: Drop zero-score items
    scored = [(s, l) for s, l in scored if s > 0]

    # Step 5: Sort by score descending
    scored.sort(key=lambda x: x[0], reverse=True)

    return [l for _, l in scored]


# ── Tool 2: suggest_outfit ────────────────────────────────────────────────────

def suggest_outfit(new_item: dict, wardrobe: dict) -> str:
    """
    Given a thrifted item and the user's wardrobe, suggest 1–2 complete outfits.

    Args:
        new_item: A listing dict (the item the user is considering buying).
        wardrobe: A wardrobe dict with an 'items' key containing a list of
                  wardrobe item dicts. May be empty — handled gracefully.

    Returns:
        A non-empty string with outfit suggestions. If the wardrobe is empty,
        returns general styling advice rather than raising an exception.
    """
    try:
        client = _get_groq_client()
    except ValueError as e:
        return f"[suggest_outfit error] {e}"

    item_desc = (
        f"{new_item.get('title', 'Unknown item')} "
        f"(${new_item.get('price', '?')}, {new_item.get('condition', 'unknown condition')}, "
        f"from {new_item.get('platform', 'unknown platform')}). "
        f"Style tags: {', '.join(new_item.get('style_tags', []))}. "
        f"Colors: {', '.join(new_item.get('colors', []))}."
    )

    wardrobe_items = wardrobe.get("items", [])

    if not wardrobe_items:
        # Empty wardrobe: give general styling advice
        prompt = (
            f"A thrift shopper is considering buying: {item_desc}\n\n"
            "They don't have a wardrobe on file yet. Give them 1–2 outfit ideas "
            "suggesting the types of pieces that would pair well with this item "
            "(e.g. specific types of bottoms, shoes, outerwear). Be specific about "
            "style, not just generic categories. Keep it to 3–5 sentences total."
        )
    else:
        # Build wardrobe description
        wardrobe_text = "\n".join(
            f"- {item.get('name', item.get('title', 'item'))}: "
            f"{item.get('category', '')}, {item.get('color', item.get('colors', ''))}, "
            f"{item.get('style', '')}"
            for item in wardrobe_items
        )
        prompt = (
            f"A thrift shopper is considering buying: {item_desc}\n\n"
            f"Their current wardrobe includes:\n{wardrobe_text}\n\n"
            "Suggest 1–2 specific complete outfit combinations using the new item "
            "and named pieces from their wardrobe. Be specific — mention exact items "
            "by name, describe the vibe, and add one styling tip per look. "
            "Keep it to 4–6 sentences total."
        )

    try:
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=300,
            temperature=0.7,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        return f"[suggest_outfit error] Could not generate outfit suggestion: {e}"


# ── Tool 3: create_fit_card ───────────────────────────────────────────────────

def create_fit_card(outfit: str, new_item: dict) -> str:
    """
    Generate a short, shareable outfit caption for the thrifted find.

    Args:
        outfit: The outfit suggestion string from suggest_outfit().
        new_item: The listing dict for the thrifted item.

    Returns:
        A 2–4 sentence string usable as an Instagram/TikTok caption.
        If outfit is empty or missing, returns a descriptive error message string
        rather than raising an exception.
    """
    # Guard: empty outfit string
    if not outfit or not outfit.strip():
        return (
            "[fit card error] Cannot generate a fit card without an outfit suggestion. "
            "Make sure suggest_outfit ran successfully first."
        )

    item_title = new_item.get("title", "thrifted find")
    item_price = new_item.get("price", "?")
    item_platform = new_item.get("platform", "a thrift app")

    prompt = (
        f"Write a 2–4 sentence Instagram/TikTok caption for this thrift outfit post.\n\n"
        f"Item: {item_title} — ${item_price} from {item_platform}\n"
        f"Outfit: {outfit}\n\n"
        "Rules:\n"
        "- Sound like a real person posting their OOTD, not a brand writing copy\n"
        "- Mention the item name, price, and platform naturally (once each)\n"
        "- Capture the specific vibe of the outfit\n"
        "- Add 1–2 relevant emojis at most\n"
        "- Do NOT start with 'I'\n"
        "- Keep it under 60 words"
    )

    try:
        client = _get_groq_client()
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=150,
            temperature=1.1,  # Higher temp for varied outputs
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        return f"[fit card error] Could not generate fit card: {e}"