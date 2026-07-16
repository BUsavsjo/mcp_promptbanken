# Valvet MCP-verktyg — pekare till huvudspec

Fullständig design (datamodell, plangränser, webbapp, deployment) finns i
`promptbanken`-repot: `docs/superpowers/specs/2026-07-16-valvet-design.md`.

Den här repons del av arbetet: sex nya MCP-verktyg (`list_my_items`,
`search_my_items`, `get_my_item`, `save_my_item`, `update_my_item`,
`archive_my_item`), tillagda bredvid befintliga tools — ingen befintlig
tool byts ut eller ändrar beteende.

Detta bygger vidare på det smala write-undantaget från
`2026-07-12-mcp-save-as-template-write-design.md`/`DECISIONS.md`: samma
princip (smalt, loggat, plan-gated) men nu uttryckligen breddat till full
CRUD för Pro (motiveringen finns i huvudspecen — Free förblir läs-tungt
med en snäv skrivkvot, Pro får full CRUD). Nya säkerhetsmekanismer som
tillkommer utöver det tidigare mönstret: idempotency key på `save_my_item`,
optimistic locking på `update_my_item`, explicit `confirm`-flagga på
`archive_my_item`, samt en modul-tagg (`content_items.module`) som håller
Valvet-poster åtskilda från kommun-poster i räkning och synlighet.
