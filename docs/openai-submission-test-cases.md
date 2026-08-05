# OpenAI submission test cases

8 test cases for the ChatGPT app directory submission portal's Testing tab.
Verified against production (`https://mcp.promptbanken.se/mcp`) on
2026-08-05, anonymous, no key. All calls are JSON-RPC `tools/call` against
the public `/mcp` endpoint.

## Positive cases

### 1. `search_templates` — find templates by free-text query

- **Input:** `{"name": "search_templates", "arguments": {"query": "mejl"}}`
- **Expected:** A non-empty result with `total_matches` and `returned`
  counts, and a `templates` array of lightweight summaries (no
  `prompt_text`) whose `title`/`tags` are relevant to "mejl" (email).
- **Actual (verified):** `total_matches: 2`, two templates returned:
  "📧 Svar på medborgarmejl" (tags include `email_reply`) and "Skriv ett
  tydligt vardagsmejl" (tags include `mejl`).
- **Why this case matters:** Confirms the primary discovery path a ChatGPT
  user's query maps to — free-text search returning relevant, correctly
  filtered results.

### 2. `get_template` — fetch one full template by id

- **Input:** `{"name": "get_template", "arguments": {"template_id": "fc9a9805-aaea-420a-aee7-0d8ea9c48c9a"}}`
- **Expected:** `status: "success"` and a `template` object containing the
  full `prompt_text`, not just a summary.
- **Actual (verified):** `status: "success"`, template title "Gör en
  att-göra-lista av mina anteckningar", full `prompt_text` present
  (multi-line instructions with a `[klistra in här]` placeholder).
- **Why this case matters:** Confirms the fetch-full-content step after a
  search/list call actually returns usable prompt text, not a truncated
  or empty payload.

### 3. `list_packages` — list all published packages, no filter

- **Input:** `{"name": "list_packages", "arguments": {}}`
- **Expected:** A `packages` array covering the known package set
  (collections/workflows), each with `slug`, `title`, `summary`.
- **Actual (verified):** Returned packages including `arbetsbank`
  ("Egen AI-arbetsbank"), `beslutsberedning`
  ("Tjänstemannastöd och beslutsberedning"), `forandringsledning`, and
  others — each with populated `slug`/`title`/`summary`/`intro_text`.
- **Why this case matters:** Confirms the package-browsing entry point
  works with zero arguments, the simplest possible call a client can make.

### 4. `get_package` — fetch one package by slug

- **Input:** `{"name": "get_package", "arguments": {"package_slug": "arbetsbank"}}`
- **Expected:** `status: "success"`, a `package` object plus a `variants`
  array (context-specific renderings of the same package).
- **Actual (verified):** `status: "success"`, package title "Egen
  AI-arbetsbank", `variants` array present with one entry per available
  context.
- **Why this case matters:** Confirms slug-based lookup (the identifier a
  client carries forward from `list_packages`) resolves correctly.

### 5. `recommend_packages` — role-based package recommendation

- **Input:** `{"name": "recommend_packages", "arguments": {"role": "kommunikator"}}`
- **Expected:** `role_recognized: true` and a ranked `recommended_areas`
  list relevant to a communications role.
- **Actual (verified):** `role_recognized: true`, `matched_role:
  "kommunikator"`, `role_match_source: "exact"`,
  `recommended_areas: ["kommunikation", "visuellt", "arbetsbank"]` —
  "kommunikation" (communication) ranked first, as expected for this role.
- **Why this case matters:** Confirms the role-matching heuristic actually
  ranks relevant areas first rather than returning an unranked or
  unfiltered list.

## Negative cases

### 6. `get_template` — unknown template id

- **Input:** `{"name": "get_template", "arguments": {"template_id": "00000000-0000-0000-0000-000000000000"}}`
- **Expected:** A clear "not found"-style error in the response payload,
  no server crash, no internal traceback leaked to the client.
- **Actual (verified):** `{"status": "error", "message": "Ingen mall
  hittades med id '00000000-0000-0000-0000-000000000000'."}` — a
  structured, human-readable Swedish error message inside a normal
  (non-`isError`) JSON-RPC result.
- **Why this case matters:** A reviewer or a ChatGPT user will inevitably
  reference a stale or hallucinated id; the server must degrade gracefully
  instead of erroring at the protocol level.

### 7. `search_templates` — empty query

- **Input:** `{"name": "search_templates", "arguments": {"query": ""}}`
- **Expected:** A broad, non-error result (the catalog's full or default
  set), not a validation failure — an empty string is a valid "no filter"
  input, not malformed input.
- **Actual (verified):** `total_matches: 66` (the full published catalog),
  `returned: 10` (the tool's own default page size), first result
  identical to the unfiltered catalog's first entry.
- **Why this case matters:** Confirms the tool distinguishes "no filter
  supplied" from "malformed input" — an important distinction for a
  conversational client that might pass an empty string when the user
  hasn't specified search terms yet.

### 8. `get_package` — wrong argument type

- **Input:** `{"name": "get_package", "arguments": {"package_slug": 12345}}` (numeric instead of the required string)
- **Expected:** A JSON-RPC schema-validation error with a clear message,
  no internal Python traceback in the response.
- **Actual (verified):** `{"code": -32602, "message": "Invalid
  get_package arguments"}` — standard JSON-RPC "Invalid params" error
  code, human-readable message, nothing implementation-specific exposed.
- **Why this case matters:** Confirms malformed input from a
  misconfigured or buggy client fails safely at the argument-validation
  layer, before reaching application code, rather than producing an
  unstructured error.
