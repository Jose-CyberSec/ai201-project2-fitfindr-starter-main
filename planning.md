# FitFindr — Planning Document

## A Complete Interaction

FitFindr is a multi-tool AI agent that helps users find secondhand clothing and figure out how to wear it. When a user submits a natural language query, the agent parses it to extract a description, size, and price ceiling, then calls three tools in sequence: `search_listings` to find matching items, `suggest_outfit` to generate outfit ideas from the user's wardrobe, and `create_fit_card` to produce a shareable caption. If any step produces no usable output (especially if `search_listings` returns nothing), the agent halts early and tells the user exactly what failed and what they can try instead.

**Example query:** "I'm looking for a vintage graphic tee under $30, size M. I mostly wear baggy jeans and chunky sneakers."

**Step 1 — search_listings**
- Input: `description="vintage graphic tee"`, `size="M"`, `max_price=30.0`
- Output: 3 matching listing dicts sorted by keyword relevance. Top result: `{"title": "Faded Band Tee", "price": 22, "platform": "Depop", "condition": "Good", ...}`

**Step 2 — suggest_outfit**
- Input: `new_item=<band tee dict>`, `wardrobe=<user's 10-item wardrobe>`
- Output: "Pair this faded band tee with your wide-leg jeans and platform sneakers for a 90s grunge look. Roll the sleeves once for shape."

**Step 3 — create_fit_card**
- Input: `outfit=<suggestion above>`, `new_item=<band tee dict>`
- Output: "thrifted this faded band tee off depop for $22 and it literally completes my wide-leg fit 🖤"

**Error path:** If `search_listings` returns `[]`, the agent sets `session["error"]` to a specific message (e.g., "No listings found for 'designer ballgown' with size XXS and under $5. Try removing the size XXS filter, or broaden your search.") and returns immediately — `suggest_outfit` is never called.

---

## Tool 1: search_listings

**What it does:** Filters the mock listings dataset by keyword relevance, optional size, and optional price ceiling. Returns a ranked list of matching items.

**Inputs:**
- `description` (str): Keywords from the user's query, e.g. "vintage graphic tee"
- `size` (str | None): Size to filter by, case-insensitive. None = no size filter.
- `max_price` (float | None): Maximum price inclusive. None = no price filter.

**Returns:** `list[dict]` — each dict is a full listing record with fields: `id`, `title`, `description`, `category`, `style_tags` (list[str]), `size`, `condition`, `price` (float), `colors` (list[str]), `brand`, `platform`. Sorted by keyword overlap score, highest first. Empty list if no matches.

**Failure mode:** Returns `[]` if nothing matches. Never raises an exception. The agent checks for `[]` after this call and sets `session["error"]` with a helpful message if empty.

---

## Tool 2: suggest_outfit

**What it does:** Uses the Groq LLM to suggest 1–2 complete outfit combinations pairing the new item with pieces from the user's wardrobe.

**Inputs:**
- `new_item` (dict): A listing dict from `search_listings` — the item the user is considering.
- `wardrobe` (dict): A wardrobe dict with an `'items'` key containing a list of wardrobe item dicts. May be empty.

**Returns:** `str` — A non-empty string with outfit suggestions. If the wardrobe is empty, returns general styling advice (what types of pieces pair well) rather than crashing.

**Failure mode:** If `wardrobe['items']` is empty, the LLM is prompted for general styling ideas. If the Groq API call fails, returns a descriptive error string (prefixed `[suggest_outfit error]`) rather than raising an exception.

---

## Tool 3: create_fit_card

**What it does:** Uses the Groq LLM to generate a casual, shareable 2–4 sentence Instagram/TikTok caption for the outfit.

**Inputs:**
- `outfit` (str): The outfit suggestion string from `suggest_outfit`.
- `new_item` (dict): The listing dict for the thrifted item (used for title, price, platform).

**Returns:** `str` — A caption that sounds like a real OOTD post, mentioning the item name, price, and platform naturally. Uses temperature 1.1 to vary outputs across calls.

**Failure mode:** If `outfit` is empty or whitespace, returns a descriptive error string (`[fit card error] ...`) immediately without calling the LLM. API errors are caught and returned as error strings.

---

## Planning Loop

The planning loop in `run_agent()` follows this conditional logic:

```
1. Initialize session with _new_session(query, wardrobe)
2. Call _parse_query(query) → extract description, size, max_price
   Store in session["parsed"]
3. Call search_listings(description, size, max_price)
   Store results in session["search_results"]
   IF results == []:
       session["error"] = "No listings found for ... Try ..."
       RETURN session   ← early exit, suggest_outfit never called
4. session["selected_item"] = results[0]   ← top-scored result
5. Call suggest_outfit(selected_item, wardrobe)
   Store in session["outfit_suggestion"]
6. Call create_fit_card(outfit_suggestion, selected_item)
   Store in session["fit_card"]
7. RETURN session
```

The loop is **not** unconditional — step 3 gates everything downstream. If `search_listings` returns nothing, the agent terminates after producing a human-readable error message; `suggest_outfit` and `create_fit_card` are never invoked.

---

## Architecture

```
User query (str)
      │
      ▼
  _parse_query()
  → description, size, max_price
      │
      ▼
Planning Loop (run_agent)
      │
      ├─► search_listings(description, size, max_price)
      │         │
      │         │ results == []
      │         ├──────────────► session["error"] = "No listings found..."
      │         │                RETURN session  ← early exit
      │         │
      │         │ results = [item, ...]
      │         ▼
      │   session["selected_item"] = results[0]
      │         │
      ├─► suggest_outfit(selected_item, wardrobe)
      │         │
      │   session["outfit_suggestion"] = "..."
      │         │
      └─► create_fit_card(outfit_suggestion, selected_item)
                │
          session["fit_card"] = "..."
                │
                ▼
           RETURN session
```

---

## State Management

All state lives in the `session` dict initialized by `_new_session()`. Keys and when they're set:

| Key | Set in | Used by |
|-----|--------|---------|
| `query` | `_new_session` | logging / display |
| `parsed` | Step 2 (`_parse_query`) | Step 3 (`search_listings` inputs) |
| `search_results` | Step 3 | Step 4 (item selection) |
| `selected_item` | Step 4 | Step 5 (`suggest_outfit`) and Step 6 (`create_fit_card`) |
| `wardrobe` | `_new_session` | Step 5 (`suggest_outfit`) |
| `outfit_suggestion` | Step 5 | Step 6 (`create_fit_card`) |
| `fit_card` | Step 6 | Returned to UI |
| `error` | Step 3 (if empty results) | `app.py` early-exit check |

No global variables are used. The session is created fresh for each call to `run_agent()`, so multiple concurrent users don't share state.

---

## Error Handling Strategy

| Tool | Failure mode | Agent response |
|------|-------------|----------------|
| `search_listings` | No matching listings | Sets `session["error"]` with specific message naming the filters used and suggesting what to change. Returns early; no downstream tools called. |
| `suggest_outfit` | Empty wardrobe | Calls LLM with a general styling prompt instead of wardrobe-specific one. Returns useful advice, not an error. |
| `suggest_outfit` | API/network failure | Returns `"[suggest_outfit error] ..."` string. Agent stores this in `outfit_suggestion`; `create_fit_card` guards against it. |
| `create_fit_card` | Empty `outfit` string | Returns `"[fit card error] ..."` immediately without calling LLM. |
| `create_fit_card` | API/network failure | Returns `"[fit card error] ..."` string. |

---

## AI Tool Plan

**Tool 1 (search_listings):** Used Claude with the Tool 1 spec block above as the prompt, asking it to implement keyword scoring and filtering using `load_listings()`. Verified the generated code filtered by all three parameters and returned `[]` on no matches before running. Tested with 3 queries covering happy path, no results, and price filter.

**Tools 2 & 3 (LLM tools):** Used Claude with the Tool 2 and Tool 3 spec blocks. For `suggest_outfit`, verified the empty wardrobe branch existed before running. For `create_fit_card`, verified the empty-string guard was in place and the temperature was set above 1.0. Ran `create_fit_card` three times on the same input and confirmed outputs differed.

**Planning loop (agent.py):** Provided Claude with the Architecture diagram and Planning Loop section above. Verified the generated code branched on `results == []` and did not call `suggest_outfit` unconditionally. Revised the query parser to use regex rather than a secondary LLM call (faster, no API cost for parsing).
