# OpenAI submission: data-field audit of the 9 public MCP tools

Verified 2026-08-05 against production (`https://mcp.promptbanken.se/mcp`),
anonymous, no key. Task 3 of
`docs/superpowers/plans/2026-08-05-openai-app-directory-technical-readiness.md`.

## Method

Called each of the 9 public tools with a representative argument set via
JSON-RPC `tools/call` against the live endpoint and recorded every
top-level field in the response payload.

## Fields returned, per tool

| Tool | Fields |
|---|---|
| `health_check` | `status`, `service`, `version`, `mode`, `catalog`, `plan`, `message`, `catalog_prompt_count` |
| `get_client_routing_instructions` | `mode`, `privacy_instruction`, `client_flow` (array of instruction strings) |
| `list_templates` | `unlocked`, `requested_context_keys`, `matched_context_keys`, `variant_source`, `total`, `returned`, `offset`, `has_more`, `templates[]` — **paginated**, 25 per page by default (`limit`/`offset`), **by default the summary shape** (see `search_templates`). With `include_prompt_text: true`, each entry on the page is the **full template shape**: `id`, `title`, `syfte`, `area`, `area_label`, `output_format`, `tags`, `risk_level`, `slug`, `icon_key`, `image_key`, `color_theme`, `prompt_text`, `example_input`, `audience_label`, `tone_hint`, `context_key`, `parameter_schema`, `default_bindings`, `binding_overrides`, `security_examples` |
| `search_templates` | `total_matches`, `returned`, `templates[]` — the **summary shape** (no `prompt_text`): `id`, `title`, `syfte`, `area`, `area_label`, `output_format`, `tags`, `risk_level` |
| `get_template` | `status`, `requested_context_keys`, `matched_context_keys`, `variant_source`, `template` (one entry in the **full template shape**) |
| `list_packages` | `packages[]` — the **summary shape**, enough to choose one: `id`, `slug`, `title`, `summary`, `package_type`. The full package comes from `get_package` |
| `get_package` | `status`, `requested_context_keys`, `matched_context_keys`, `variant_source`, `package` (single, **full package shape**: `id`, `slug`, `package_type`, `icon_key`, `image_key`, `color_theme`, `title`, `summary`, `intro_text`, `audience_label`, `context_key`, `parameter_schema`, `default_bindings`, `binding_overrides`), `variants[]` (same shape, one per context) |
| `list_package_prompts` | `requested_context_keys`, `matched_context_keys`, `variant_source`, `prompts[]` — **by default the step shape**: `id`, `slug`, `title`, `syfte`, `area`, `prompt_slug`, `sort_order`, `step_title`, `step_intro`, `is_required`. The step's prompt text is fetched just in time with `get_template(id)`. With `include_prompt_text: true`, each entry is the **full template shape** plus the step fields |
| `recommend_packages` | `role_recognized`, `packages[]` (`area`, `area_label`, `template_count`), `matched_role`, `role_match_source`, `recommended_areas` |

## Assessment

Every field across all 9 tools is one of:

- **Catalog product content** — prompt template text, package descriptions,
  titles, tags, risk labels, area labels. This is the product itself
  (public prompt library content), not user data.
- **Structural metadata about the catalog item** — its own UUID, slug,
  icon/color theming keys, parameter schema shape. Not a user identifier —
  it identifies a *template*, not a *person*.
- **Echo of the caller's own request** — `requested_context_keys`,
  `matched_context_keys`, `matched_role` simply reflect back what the
  client asked for (a context filter or role string), not anything stored
  about the caller.

No field contains: an internal user ID, a session/trace ID, a raw IP, an
email, a timestamp with individual tracking value, an API key, or anything
resembling personal data. This matches the expectation for a read-only,
anonymous, public-catalog MCP server.

## Conclusion

No gap against `privacy.html`. Its existing paragraph (see the "Anonym
användningsstatistik" section of privacy.html) already discloses that usage
*statistics* collection excludes personal/sensitive data; this audit
additionally confirms the tool *responses* themselves —
a separate data flow from usage statistics — carry only public catalog
content. No text change to `privacy.html` is needed. **This audit finding
is the Task 3 deliverable.**
