# OpenAI app-katalog: teknisk readiness — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the three technical gaps blocking an OpenAI ChatGPT app-directory submission concrete and closed: a domain-verification route OpenAI's portal can check, a data-field audit of the 9 public MCP tools against `privacy.html`, and an 8-case test document ready to paste into the submission portal's Testing tab.

**Architecture:** One new Starlette route in the existing hosted MCP server (`mcp_server.py`), added to the same routes list and given the same middleware-exemption treatment as `/healthz`. The audit and test-case work are read-only investigation against the live production `/mcp` endpoint plus a small doc/text change, no new infrastructure.

**Tech Stack:** Python (Starlette route in `mcp-server/server/mcp_server.py`), `unittest` (existing test style in `mcp-server/tests/`), Docker Compose deploy on the promptbanken-dev VPS via the existing `vps-deploy` skill.

## Global Constraints

- The 9 public tools, their names, and their input schemas are a frozen contract (`DECISIONS.md`, 2026-07-31) — this plan must not add, rename, or change any of them.
- `/mcp` must never require auth (same decision) — the new route follows the same anonymous-access rule.
- No OAuth work — explicitly out of scope per the same decision.
- No change to `/sse` or `/mcp/key` — never published as the ChatGPT URL.
- The new route's response body must be **exactly** the raw token as plain text — no JSON wrapping, no extra whitespace beyond what the token itself contains.
- `BearerAuthMiddleware`'s exemption set is currently `{"/healthz", "/mcp"}` (`mcp_server.py:3364`) — a known "deploy footgun" per the existing comment at `mcp_server.py:3389`; the new path must be added to this exact set or the route silently 401s instead of serving the token.

---

## File Structure

- **Modify:** `mcp-server/server/mcp_server.py` — new `_openai_apps_challenge` handler, new `Route(...)` entry, `BearerAuthMiddleware` exemption set updated.
- **Modify:** `mcp-server/tests/test_openai_publication_contract.py` — new test for the route and the exemption.
- **Create:** `docs/openai-submission-test-cases.md` — the 8 test cases for the submission portal.
- **Modify (conditionally):** `promptbanken/privacy.html` — only if the audit in Task 3 finds an undocumented field; otherwise no change, and the audit table itself is the deliverable.

---

### Task 1: Domain-verification route

**Files:**
- Modify: `mcp-server/server/mcp_server.py` (handler near `_healthz` at line 1713, route list at lines 3504-3538, middleware at line 3364)
- Modify: `mcp-server/tests/test_openai_publication_contract.py`

**Interfaces:**
- Produces: `GET /.well-known/openai-apps-challenge` — 200 with plain-text token body when `PROMPTBANKEN_OPENAI_CHALLENGE_TOKEN` is set and non-empty; 404 with empty body when unset. No auth required regardless of `PROMPTBANKEN_MCP_API_KEY`.
- Consumes: `os.environ` (already imported at `mcp_server.py:5`), `starlette.responses` (already imports `HTMLResponse, JSONResponse, Response` at line 20 — this task adds `PlainTextResponse` to that import).

- [x] **Step 1: Add the handler**

In `mcp-server/server/mcp_server.py`, add this function immediately after `_healthz` (which ends at line 1717, right before `def _not_found`):

```python
async def _openai_apps_challenge(request: Request) -> PlainTextResponse:
    token = os.environ.get("PROMPTBANKEN_OPENAI_CHALLENGE_TOKEN", "")
    if not token:
        logger.info("http_request path=/.well-known/openai-apps-challenge status=404")
        return PlainTextResponse("", status_code=404)
    logger.info("http_request path=/.well-known/openai-apps-challenge status=200")
    return PlainTextResponse(token)
```

- [x] **Step 2: Import `PlainTextResponse`**

In `mcp-server/server/mcp_server.py` line 20, change:

```python
from starlette.responses import HTMLResponse, JSONResponse, Response
```

to:

```python
from starlette.responses import HTMLResponse, JSONResponse, PlainTextResponse, Response
```

- [x] **Step 3: Register the route**

In the `Starlette(routes=[...])` list (currently starting at line 3504), add a new entry directly after the `/healthz` line:

```python
            Route("/healthz", endpoint=_healthz),
            Route("/.well-known/openai-apps-challenge", endpoint=_openai_apps_challenge, methods=["GET"]),
```

- [x] **Step 4: Exempt the route from `BearerAuthMiddleware`**

In `mcp_server.py:3364`, change:

```python
        if scope.get("type") == "http" and token and scope.get("path") not in {"/healthz", "/mcp"}:
```

to:

```python
        if scope.get("type") == "http" and token and scope.get("path") not in {
            "/healthz",
            "/mcp",
            "/.well-known/openai-apps-challenge",
        }:
```

Also update the class docstring comment two lines above (currently "requires exactly 'Bearer <global_nyckel>' on all paths except /healthz and the published /mcp surface") to mention the new exempted path, so the next person reading the footgun warning at `AdminBearerAuthMiddleware`'s docstring (line 3389, which explicitly calls out this exemption set) isn't misled by a stale comment.

- [x] **Step 5: Write the test**

In `mcp-server/tests/test_openai_publication_contract.py`, add a new test class at the end of the file (after `OpenAIPublicationContractTests`, following the same `unittest.TestCase` + `_asgi_status`-helper pattern already used by `test_global_bearer_auth_keeps_public_mcp_anonymous` at line 152):

`_openai_apps_challenge` is a Starlette route handler: it takes a
`starlette.requests.Request` (unused in the body, same as `_healthz`'s own
signature), not an `httpx.Request`. Add a small module-level helper next to
the existing `_accept_asgi_request` (line 35) to build one from a minimal
ASGI scope:

```python
def _make_challenge_request() -> "StarletteRequest":
    from starlette.requests import Request as StarletteRequest

    async def receive() -> dict[str, object]:
        return {"type": "http.request", "body": b"", "more_body": False}

    return StarletteRequest(
        {"type": "http", "method": "GET", "path": "/.well-known/openai-apps-challenge", "headers": []},
        receive,
    )
```

Then the test class:

```python
class OpenAIAppsChallengeTests(unittest.TestCase):
    def test_challenge_route_serves_configured_token_without_auth(self) -> None:
        from server.mcp_server import _openai_apps_challenge

        with patch.dict(
            "os.environ",
            {"PROMPTBANKEN_OPENAI_CHALLENGE_TOKEN": "test-token-value"},
        ):
            response = asyncio.run(_openai_apps_challenge(_make_challenge_request()))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(bytes(response.body).decode("utf-8"), "test-token-value")

    def test_challenge_route_404s_when_token_unset(self) -> None:
        from server.mcp_server import _openai_apps_challenge

        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("PROMPTBANKEN_OPENAI_CHALLENGE_TOKEN", None)
            response = asyncio.run(_openai_apps_challenge(_make_challenge_request()))

        self.assertEqual(response.status_code, 404)

    @patch("server.mcp_server._api_key", return_value="global-key")
    def test_challenge_route_exempt_from_global_bearer_auth(self, _) -> None:
        from server.mcp_server import BearerAuthMiddleware

        app = BearerAuthMiddleware(_accept_asgi_request)

        self.assertEqual(
            _asgi_status(app, "/.well-known/openai-apps-challenge"),
            204,
        )
```

`test_challenge_route_404s_when_token_unset` needs `import os` at the top
of the test file (add it next to the existing `import sys` at line 3 if
not already present — check before adding, this file may not import `os`
yet).

- [x] **Step 6: Run the tests**

Run (from repo root, using the project's `.venv`, not `pytest` — this repo has no `pytest` dependency, only stdlib `unittest`): `cd mcp-server && .venv/Scripts/python.exe -m unittest tests.test_openai_publication_contract -v` (on Windows; `.venv/bin/python` on POSIX).

Expected: all tests pass, including the 3 new ones and the pre-existing suite (unaffected).

- [x] **Step 7: Commit**

```bash
git add mcp-server/server/mcp_server.py mcp-server/tests/test_openai_publication_contract.py
git commit -m "feat(mcp): add OpenAI domain-verification challenge route

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_014EpQBktNytn8fZT2JAsLMW"
```

---

### Task 2: Deploy and verify the route live

**Files:** None (deploy + verification only).

**Interfaces:**
- Consumes: Task 1's route, deployed to the promptbanken-dev VPS via the existing `vps-deploy` skill/workflow for this repo.

- [x] **Step 1: Set a placeholder token env var on the VPS**

Add `PROMPTBANKEN_OPENAI_CHALLENGE_TOKEN=pending-openai-submission` (or similar obviously-placeholder value) to the server's environment configuration (wherever `PROMPTBANKEN_MCP_API_KEY` and similar are already set — `docker-compose.yml` env or an `.env` file referenced by it, per this repo's existing deploy convention). This is a placeholder; the real value comes from OpenAI's submission portal later and gets swapped in at that time — do not block this task on having the real value.

- [x] **Step 2: Deploy**

Use the `vps-deploy` skill for this repo (git pull + docker-compose rebuild on promptbanken-dev, with the mandatory disk-space check first).

- [x] **Step 3: Verify live, unauthenticated**

Run: `curl -i https://mcp.promptbanken.se/.well-known/openai-apps-challenge`

Expected: `HTTP/1.1 200`, body is exactly `pending-openai-submission` (or whatever placeholder was set), no `Authorization` header sent.

- [x] **Step 4: Verify the existing public surface is unaffected**

Run: `curl -i https://mcp.promptbanken.se/healthz`

Expected: unchanged `200` response, confirming the middleware/route changes didn't regress the existing exemption.

- [x] **Step 5: Record the outcome**

No commit needed (deploy-only task) — note the verified-live status in the conversation/ledger for whoever runs the actual OpenAI submission later, since they'll need to replace the placeholder token with OpenAI's real one when the portal issues it.

---

### Task 3: Data-field audit against `privacy.html`

**Files:**
- Create: a short audit table (inline in the task report is sufficient; promote to a repo doc only if the plan's executor judges it worth keeping — the deliverable is the finding, not a specific file).
- Modify (conditionally): `../promptbanken/privacy.html` (sibling repo, absolute path `C:\Users\petwen\OneDrive - Höglandsförbundet\Projekt\promptbanken\privacy.html`) — only if the audit finds a field not already covered by the existing disclosure text at line 48.

**Interfaces:**
- Consumes: production `/mcp` endpoint (`https://mcp.promptbanken.se/mcp`), the 9 public tools: `health_check`, `get_client_routing_instructions`, `list_templates`, `search_templates`, `get_template`, `list_packages`, `get_package`, `list_package_prompts`, `recommend_packages`.

- [x] **Step 1: Call each of the 9 public tools against production**

For each tool, issue a representative JSON-RPC `tools/call` against `https://mcp.promptbanken.se/mcp` with realistic arguments (e.g. `search_templates` with a real Swedish query term, `get_template` with a known published slug — fetch one via `list_templates` first if no slug is known ahead of time). Record the full response JSON for each.

- [x] **Step 2: List every top-level field in each response**

Build a table: tool name → list of field names in the response payload (not full values, just field names and a one-word description of what each holds, e.g. `prompt_text: full prompt template text`, `area: category label`).

- [x] **Step 3: Compare against `privacy.html`**

Read `privacy.html` (the paragraph at line 48 already discloses that usage *statistics* — not tool response payloads — exclude prompt content, raw search terms, IPs, emails, user-agent, and key material). Check: does any field returned by the 9 tools contain something that paragraph doesn't already cover the spirit of (e.g. an internal database ID, a fine-grained timestamp with tracking value, anything not obviously "public catalog content")? Expected result given this is a read-only public catalog: no — tool responses are prompt/package template content, which is the product itself, not user data. Confirm this expectation holds; don't assume it without reading the actual field list from Step 2.

- [x] **Step 4: Update `privacy.html` only if Step 3 found a gap**

If a gap is found: add one sentence to the existing paragraph at line 48 (do not create a new section) describing the additional field's presence, following the same plain-Swedish style as the rest of that paragraph.

If no gap is found: no file change. The audit table from Step 2 is the deliverable — write it into the task report.

- [x] **Step 5: Commit (only if Step 4 changed `privacy.html`)**

```bash
git add privacy.html
git commit -m "docs: clarify tool response data disclosure in privacy policy

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_014EpQBktNytn8fZT2JAsLMW"
```

Run this in the `promptbanken` repo, not `mcp_promptbanken` (different git root — `C:\Users\petwen\OneDrive - Höglandsförbundet\Projekt\promptbanken`).

---

### Task 4: Submission test-case document

**Files:**
- Create: `docs/openai-submission-test-cases.md`

**Interfaces:**
- Consumes: production `/mcp` endpoint, same 9 tools as Task 3 (reuse findings from Task 3 where relevant — e.g. a known-good slug for `get_template`).

- [x] **Step 1: Run each proposed case against production and record actual output**

For each of the 8 cases listed in the design spec (`docs/superpowers/specs/2026-08-04-openai-app-directory-technical-readiness-design.md`, "Del 3"), issue the real JSON-RPC call against `https://mcp.promptbanken.se/mcp` and record the actual response. Do not write the document from the spec's proposed cases without running them — the spec's list is a starting proposal, not verified fact; a submission reviewer running these cases expects them to work exactly as documented.

- [x] **Step 2: Write the document**

Create `docs/openai-submission-test-cases.md` with this structure, one entry per case:

```markdown
# OpenAI submission test cases

8 test cases for the ChatGPT app directory submission portal's Testing tab.
Verified against production (`https://mcp.promptbanken.se/mcp`) on <date>.

## Positive cases

### 1. <tool name> — <one-line scenario>

- **Input:** <exact JSON-RPC params>
- **Expected:** <what a reviewer should see>
- **Why this case matters:** <one sentence>

[... repeat for all 5 positive cases ...]

## Negative cases

### 6. <tool name> — <one-line scenario>

- **Input:** <exact JSON-RPC params>
- **Expected:** <clear error / graceful empty result, no crash, no internal traceback>
- **Why this case matters:** <one sentence>

[... repeat for all 3 negative cases ...]
```

Use the actual recorded outputs from Step 1, not placeholder text.

- [x] **Step 3: Commit**

```bash
git add docs/openai-submission-test-cases.md
git commit -m "docs: add OpenAI submission test cases (5 positive, 3 negative)

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_014EpQBktNytn8fZT2JAsLMW"
```
