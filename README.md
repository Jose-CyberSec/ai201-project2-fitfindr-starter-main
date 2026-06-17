# FitFindr

A multi-tool AI agent that helps users find secondhand clothing and figure out how to wear it. FitFindr searches mock thrift listings, generates outfit ideas from the user's wardrobe, and produces a shareable fit card — all from a single natural language query.

---

## Setup

```bash
python -m venv .venv
source .venv/bin/activate       # Mac/Linux
# or: source .venv/Scripts/activate   # Windows

pip install -r requirements.txt
```

Create a `.env` file:

```
GROQ_API_KEY=your_key_here
```

Get a free key at [console.groq.com](https://console.groq.com) — no credit card required.

Run the app:

```bash
python app.py
```

Open the URL shown in your terminal (usually `http://localhost:7860`).

---

## Tool Inventory

### `search_listings(description, size, max_price)`

**Inputs:**
- `description` (str) — keywords describing the item (e.g. `"vintage graphic tee"`)
- `size` (str | None) — size to filter by, case-insensitive; `None` skips size filtering
- `max_price` (float | None) — maximum price inclusive; `None` skips price filtering

**Returns:** `list[dict]` — matching listing dicts sorted by keyword overlap score, highest first. Each dict contains: `id`, `title`, `description`, `category`, `style_tags` (list[str]), `size`, `condition`, `price` (float), `colors` (list[str]), `brand`, `platform`. Returns `[]` if nothing matches.

**Purpose:** Filters the 40-item mock dataset and ranks results by relevance to the user's description.

---

### `suggest_outfit(new_item, wardrobe)`

**Inputs:**
- `new_item` (dict) — a listing dict returned by `search_listings`
- `wardrobe` (dict) — a wardrobe dict with an `'items'` key (list of wardrobe item dicts); may be empty

**Returns:** `str` — 1–2 outfit suggestions (4–6 sentences). If the wardrobe is empty, returns general styling advice. If the API call fails, returns a descriptive error string prefixed `[suggest_outfit error]`.

**Purpose:** Uses Groq's `llama-3.3-70b-versatile` to generate specific outfit combinations pairing the new thrift find with the user's existing wardrobe.

---

### `create_fit_card(outfit, new_item)`

**Inputs:**
- `outfit` (str) — the outfit suggestion string from `suggest_outfit`
- `new_item` (dict) — the listing dict for the thrifted item

**Returns:** `str` — a 2–4 sentence Instagram/TikTok caption mentioning the item name, price, and platform. Uses temperature 1.1 so outputs vary between calls. If `outfit` is empty/whitespace, returns a descriptive error string without calling the LLM.

**Purpose:** Generates a caption that sounds like a real person's OOTD post, not a product description.

---

## How the Planning Loop Works

`run_agent()` in `agent.py` runs a conditional planning loop — it does **not** call all three tools unconditionally:

1. **Parse** the query with regex to extract `description`, `size`, and `max_price`.
2. **Call `search_listings`** with parsed parameters. If the result is an empty list → set `session["error"]` with a message naming the filters used and suggesting what to change, then **return early**. `suggest_outfit` is never called with empty input.
3. **Select the top result** (`results[0]`) and store it as `session["selected_item"]`.
4. **Call `suggest_outfit`** with the selected item and wardrobe. Store the result.
5. **Call `create_fit_card`** with the outfit suggestion and selected item. Store the result.
6. Return the complete session.

The branch at step 2 is what makes this a real planning loop: the agent's behavior changes based on what `search_listings` returns. The downstream tools only run if there's a valid item to work with.

---

## State Management

All state lives in a `session` dict created fresh for each `run_agent()` call. Key fields:

| Key | When set | Flows into |
|-----|----------|-----------|
| `parsed` | After query parsing | `search_listings` inputs |
| `search_results` | After `search_listings` | Item selection |
| `selected_item` | Top of `search_results` | `suggest_outfit`, `create_fit_card` |
| `outfit_suggestion` | After `suggest_outfit` | `create_fit_card` |
| `fit_card` | After `create_fit_card` | UI output panel |
| `error` | If `search_results == []` | UI early-exit display |

No global variables. Each call to `run_agent()` is fully independent.

---

## Error Handling

| Tool | Failure mode | Agent response |
|------|-------------|----------------|
| `search_listings` | No matches found | Sets `session["error"]` naming the filters used (e.g., "size M and under $30") and suggests removing filters. Returns early — no downstream tools called. |
| `suggest_outfit` | Empty wardrobe | Switches to a general styling prompt asking what *types* of pieces pair well. Returns useful advice, not a crash. |
| `suggest_outfit` | Groq API failure | Returns `"[suggest_outfit error] ..."` string. The agent stores this and continues to `create_fit_card`, which catches the malformed input via its own guard. |
| `create_fit_card` | Empty/whitespace `outfit` | Immediately returns `"[fit card error] Cannot generate a fit card without an outfit suggestion."` — no LLM call. |
| `create_fit_card` | Groq API failure | Catches the exception and returns `"[fit card error] Could not generate fit card: ..."` string. |

**Concrete example from testing:**

Running `python -c "from tools import search_listings; print(search_listings('designer ballgown', size='XXS', max_price=5))"` returns `[]` without raising an exception. When this flows through `run_agent()`, the error message returned is:

> "No listings found for "designer ballgown" with size XXS and under $5. Try removing the size XXS and under $5 filter, or broaden your search."

---

## Spec Reflection

**One way planning.md helped during implementation:** Writing out the exact conditional logic for the planning loop before touching `agent.py` made the implementation almost mechanical — I already knew exactly what to check after `search_listings` and what to store at each step. Without that, I would have probably wired all three tools unconditionally and missed the early-exit requirement entirely.

**One divergence from the spec, and why:** The spec suggested using the LLM to parse the user's query (extract size and price). During implementation I switched to regex instead. The LLM approach adds latency and an extra API call for something a few patterns can handle reliably. Regex also makes the parser deterministic and testable — I can write a test that asserts `_parse_query("vintage tee under $30 size M")` returns exactly `{"description": "vintage tee", "size": "M", "max_price": 30.0}`. That's not possible with an LLM parser.

---

## AI Usage

**Instance 1 — implementing `search_listings`:** I gave Claude the Tool 1 spec block from `planning.md` (inputs, return value, failure mode, keyword scoring description) and asked it to implement the function using `load_listings()`. The generated code used a single scoring function that joined all text fields and checked each keyword. I revised it to explicitly drop zero-score listings (the original version returned all items sorted, even ones with no keyword overlap) and to use case-insensitive partial matching for size (the original used exact match, which would fail for "S/M" when user enters "M").

**Instance 2 — implementing the planning loop:** I gave Claude the Architecture ASCII diagram and the Planning Loop and State Management sections from `planning.md`. The generated code was close but called `suggest_outfit` before checking whether `search_results` was populated — the branch was in the wrong place. I moved the empty-results check to immediately after `search_listings` returns, before item selection, which is what the spec described.
