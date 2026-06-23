# Build Audit — Plan 16 (Housecall Pro FSM sync)
**Stage:** S4 BUILD-AUDIT (inline by orchestrator) · **Date:** 2026-06-23. **Verdict: SHIP**, no P1.

## Verified
- **FIX-1..8 applied** (per build report + spot-checks): OAuth URLs `api.housecallpro.com/oauth/*`; Bearer
  auth; `page_size` + `next_page_url` pagination; first+last name join; `description` job field; **push is a
  defined no-op returning None — `hcp_fsm` never calls `db.set_fsm_external_id`** (grep confirmed: only the
  docstring mentions it); `SCOPES` TODO; refresh-fail → mark disconnected.
- **Jobber non-regression:** `test_fsm_sync.py` 92/0 includes the original Jobber cases + new
  provider-selection (only-jobber/only-hcp/neither/both→HCP) — Jobber unaffected when it's the only provider.
- **Provider routing double-fire-safe:** `_get_active_provider` returns ONE provider; `sync_clients`/
  `push_booking_async` call it once; both-connected → HCP + stderr warning (no double-fire).
- **F1 carried forward:** `sync_clients` calls `db.upsert_suggestion(category="customer",
  source="import-housecall_pro")` directly; never `contact_import.ingest`.
- **Inert:** `hcp_fsm.configured()` False when `HCP_CLIENT_ID` unset → every entry point no-op.
- **Honesty:** HCP push no-op never claims "pushed"; settings copy "synced" not "imported".
- **No Jinja corruption:** `settings.html` parses; the 12 smart-quote hits are CONTENT apostrophes/quotes
  inside straight-delimited strings (Jinja-safe), not delimiter corruption. `/settings` renders 200 with
  both HCP + Jobber cards.
- **Tests:** hcp_fsm 69/0, fsm_sync 92/0, sf8_connections 99/0, setup 147/0 (count 11→12 for hcp row),
  screening 57/0. `import app` clean.

## v1 caveats (documented, owner-facing)
- HCP push degrades to no-op (no public notes endpoint / phone filter). Read-only customer sync — the
  screening benefit — is the v1 value.
- OAuth scope strings unverified publicly → confirm at HCP partner-app registration before first real OAuth.
- Provider selection Option C: if both Jobber+HCP ever connected, HCP wins, Jobber pauses silently (log only).
