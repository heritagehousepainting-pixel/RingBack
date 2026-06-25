# Plan Audit — Plan 16 (Housecall Pro FSM sync)
**Stage:** S2 PLAN-AUDIT · **Date:** 2026-06-23 · web-verified HCP API + code check.
**Verdict: GO-WITH-FIXES.** Architecture sound, codebase ready; the plan's ASSUMED HCP API had material
errors (now corrected from live docs: api-evangelist OpenAPI spec + Rollout HCP integration guides).

## HCP API verification (corrections the S3 build MUST apply)
| Item | Plan assumed | REAL (verified) |
|---|---|---|
| OAuth authorize/token | `auth.housecallpro.com/oauth/*` | **`api.housecallpro.com/oauth/{authorize,token}`** |
| Auth header | `Token token="<t>"` | **`Authorization: Bearer <t>`** |
| Pagination | `per_page`/`total_pages`/`page` | **`page_size` query + follow `next_page_url` in response** |
| Customer name | single `name` | `first_name`+`last_name` (join) — confirmed |
| Customer phones | mobile/home/work_number | confirmed correct |
| Job text field | `note` | **`description`** (also `notes` for addl) |
| Job→customer phone | inline `customer:{mobile_number}` | **only `customer_id` string — no inline phone** |
| `work_status` | `work_status` | confirmed (unscheduled/scheduled/in_progress/complete/completed_unrated/user_canceled/pro_canceled) |
| Scopes (Q3) | `read:customers read:jobs` | **COULD-NOT-VERIFY** (not public) → TODO comment, env-gated |
| Notes endpoint (Q4) | `POST /customers/{id}/notes` | **No public evidence → push is a v1 NO-OP** |
| Phone filter (R1) | `GET /customers?mobile_number=` | **Not documented → push lookup impossible → no-op** |
| Refresh lifetime (Q8) | unknown | not documented → apply F8 (mark disconnected on refresh fail) |

## FIX LIST
**P1 (before S3 builds — all confined to new `hcp_fsm.py`):**
- FIX-1: `AUTH_URL`/`TOKEN_URL` = `https://api.housecallpro.com/oauth/{authorize,token}`.
- FIX-2: `_get`/`_post` send `Authorization: Bearer <token>`.
- FIX-3: `fetch_clients` uses `page_size=25`, paginates by following `next_page_url` until absent (`_MAX_PAGES` cap on iterations).
- FIX-4: customer map: join `first_name`+`last_name`; phones = filter([mobile_number, home_number, work_number]).
- FIX-5: `fetch_jobs` uses `description` as title; `client_phone=""` always (only `customer_id` available, no inline phone) — annotate.
- FIX-6: `push_quote_request` = defined **no-op returning None** with comment (no confirmed notes endpoint / phone filter). Do NOT wire `db.set_fsm_external_id` for HCP until confirmed. Never claim "pushed".
- FIX-7: `SCOPES = "read:customers read:jobs"  # TODO verify via HCP developer dashboard (not public)`.

**P2 (during/after build):**
- FIX-8: `_access_token` refresh failure → `db.set_oauth_tokens(bid, "housecall_pro", None, None, None)` (F8; avoids infinite retry) + log.
- FIX-9/10: `app.py` `_fsm_background_sync` unchanged (routes via refactored `fsm_sync`); `/api/fsm/sync` checks → `fsm_sync.configured()` + `_get_active_provider(bid) is not None`, provider-neutral error copy.
- FIX-11: test mocks use the corrected shapes (customers env `{customers:[{first_name,last_name,mobile_number,...}], next_page_url:null}`; jobs use `description`+`customer_id`).

## Code verification (all confirmed against real code)
- `fsm_provider.py` ABC has the 7 methods; `HCPProvider` plugs in cleanly. Mirror `jobber_fsm.py` (Bearer
  already used there; `_expiry_iso`, `google_oauth.access_is_fresh` reusable verbatim; module-singleton pattern).
- `fsm_sync.py` has **7 `jobber_fsm.*` call sites** (configured ×2; is_connected lines 56/109/136/189;
  fetch_clients 59; fetch_jobs 113; push 141) — all covered by the `_get_active_provider` refactor.
  `configured`/`push_configured` → `jobber_fsm.configured() or hcp_fsm.configured()`. `maybe_sync_all`
  line 189 → `_get_active_provider(bid) is not None`. Source/reason from `provider.PROVIDER_KEY`.
- `db.upsert_suggestion(business_id, number, name, category, reason, source)`, `set_oauth_tokens`,
  `get_integration`, `set_fsm_external_id(appt, business_id, ext, pushed_at)` — signatures confirmed;
  `integrations` PK `(business_id, provider)` accepts `"housecall_pro"`, no schema change.
- `recommended_setup` 3-touch: kwarg (connections.py:172), rows entry (:195), app.py call site (:1590) — additive, don't touch the jobber row.
- F1 (upsert-direct, never `contact_import.ingest`) + honesty copy carry forward. HCP push no-op → never call `set_fsm_external_id`.
- Option C double-fire-safe: `_get_active_provider` returns ONE provider; `sync_clients`/`push_booking_async` call it once.

## Q7 — OWNER DECISION (provider selection)
Approve **Option C** (route to whichever connected, HCP>Jobber tiebreak). Sound + double-fire-safe.
Caveat for owner: if a business is ever connected to BOTH at once, HCP wins and Jobber sync stops
**silently (log warning only, no UI indicator)**. Acceptable for single-tenant v1; a per-business
`fsm_provider` column is the v2 fix. **Proceeding with Option C** (surface to owner at handoff).

## Net: HCP v1 = read-only customer sync (feeds screening) with push as a defined no-op; honest + inert
until `HCP_CLIENT_ID/SECRET` set. Scope strings to be confirmed at partner-app registration (doesn't block build).
