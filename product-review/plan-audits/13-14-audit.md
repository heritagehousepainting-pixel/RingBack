# Plan Audit — Plans 13 (FSM Sync) + 14 (Outlook Calendar)
**Stage:** S2 PLAN-AUDIT · **Date:** 2026-06-23 · read-only pass against `staging`.

## Verdicts
- **Plan 13 (Jobber FSM sync): GO-WITH-FIXES** — sound architecture/token flow/triage path; 1 critical bug (F1), 3 P2.
- **Plan 14 (Outlook calendar): GO-WITH-FIXES** — solid google_cal mirror; `recommended_setup` more invasive than stated; Windows-tz risk real. 3 P1, 2 P2.

## Assumed-name verification (key results)
All these EXIST as assumed (verified signatures): `db.set_oauth_tokens(business_id, provider, access, refresh, expiry)`,
`db.get_integration(business_id, provider)` (returns decrypted dict/None), `db.set_business_timezone`,
`db.set_google_event_id(appointment_id, event_id)`, `db.is_known_caller(business_id, number)` (checks `contacts`
OR booked appt — **NOT** `contact_suggestions`), `db.get_contact`, `db.set_contact(…, source="owner")`,
`db.book_appointment`, `db.cancel_appointment` (returns canceled row), `db.upsert_suggestion(business_id, number,
name, category, reason, source)`, `token_crypto.encrypt/decrypt` (None-safe, dual-read), `google_oauth.access_is_fresh`,
`google_cal.busy_slot_ids/create_event_async(business_id, appointment_id, summary, desc, day_iso, time_key, tz=None)/
cancel_event_async(business_id, google_event_id)/_access_token/_slots_conflicting`, `triage.screen_caller` (statuses:
trusted, screened_contact, screened_spam, review, prospect, opted_out), `integrations` cols (incl. `calendar_id`,
PK `(business_id, provider)`), `appointments` partial UNIQUE `uniq_booked_slot(business_id, day, slot_time) WHERE
status='booked'`, `contacts`/`contact_suggestions` schema, `reminders.tick_once` isolated try/except pattern.

**MISMATCH / MISSING (must address in build):**
- `contact_import.ingest(business_id, contacts, source)` EXISTS but its `presort` (contact_import.py:42) returns
  None for anyone who hasn't already booked AND has no `org` — i.e. **drops 100% of Jobber customers on first sync.** → F1.
- `connections.recommended_setup` is a **function** with fixed kwargs (connections.py:172), not a list — adding a
  provider needs signature kwarg + rows entry + the app.py:1569 call-site update. → F2/F7.
- `db.set_outlook_event_id`, `appointments.outlook_event_id`, `appointments.fsm_external_id`,
  `appointments.fsm_pushed_at`, `businesses.fsm_last_synced_at/fsm_clients_synced` — all MISSING (expected; add via migration).
- `contact_import.ingest` docstring lists only import-file/import-google → add import-jobber. → F3.
- Use generic `db.set_oauth_tokens` for Jobber+Outlook (NOT the Google-specific `db.set_google_tokens`). ✓ plans correct.
- App.py call sites confirmed: booking google event ~2075 (handle_inbound) + ~1940 (open_conversation); cancel ~2267; busy_slot_ids ~2019.

## Fix list
### Plan 13 (Jobber)
- **F1 [P1 CRITICAL]:** `fsm_sync.sync_clients` must NOT use `contact_import.ingest` (its `presort` drops all new
  Jobber customers). Call `db.upsert_suggestion(business_id, number, name, category="customer", reason="Existing
  Jobber client", source="import-jobber")` directly. Update tests: assert `upsert_suggestion` called w/ category="customer".
- **F2 [P1]:** `recommended_setup` needs 3 touches: add `jobber_connected=False` kwarg + a rows entry (connections.py),
  and update the call site app.py:1569 to pass it (gated by `fsm_sync.push_configured()`).
- **F3 [P1]:** update `contact_import.ingest` docstring to include `'import-jobber'`.
- **F4 [P2]:** decide cadence store — reuse `db.set_meta/get_meta` (`fsm_sync_at:{bid}`) like Google Contacts, OR keep
  `businesses.fsm_last_synced_at` for UI display; test the interval-skip against whichever owns cadence.
- **F5 [P2]:** Jobber API access is plan-tier-gated (Core/Connect/Grow); `requestCreate` may need Grow. Note min-tier
  in `jobber_fsm.py` + owner copy ("Requires Jobber Connect or higher"); document assumed GraphQL shapes in tests.

### Plan 14 (Outlook)
- **F6 [P1]:** MS Graph `mailboxSettings.timeZone` returns **Windows** names ("Eastern Standard Time"), not IANA →
  `ZoneInfo(...)` raises and tz is silently never stored for ~90% of users. Add a Windows→IANA shim (~15 common
  zones): try the name directly, then dict lookup, then fail-open. Add a test: mailboxSettings "Eastern Standard
  Time" → `set_business_timezone("America/New_York")`.
- **F7 [P1]:** same `recommended_setup` 3-touch change as F2, for `outlook_connected`. (Sequencing avoids clobbering F2.)
- **F8 [P1]:** MS personal refresh tokens expire (24h inactivity / 90d). On refresh failure in `_access_token`, mark
  the integration disconnected (so `is_connected`→False and Settings shows "Reconnect Outlook"). Add acceptance
  criterion + test for the reconnect state.
- **F9 [P2]:** document in `outlook_cal.py` docstring that a 3rd provider would warrant a `calendar_events(appointment_id,
  provider, event_id)` table (per-provider columns OK for v1).
- **F10 [P2]:** import `outlook_cal` at app.py module top (gated, no-op when unconfigured) — don't lazy-import per booking turn.

## Security (both)
Token encryption ✓ (set_oauth_tokens→token_crypto). Cross-tenant ✓ (business_id scoping, composite PK, current_business()).
OAuth state CSRF ✓ (`fsm_j_state` / `ol_state`, verify-and-consume). No raw-id bypass. Webhooks safely deferred.
**Gap:** the new `db.set_outlook_event_id` must scope `UPDATE … WHERE id=? AND business_id=?` (existing `set_google_event_id`
uses `WHERE id=?` only, relying on caller validation — be explicit for the new helper).

## Risks
R1 Jobber tier-gating (real → note min tier). R2 Windows tz (real → F6). R3 500+ clients review friction (scope-correct;
add "Bulk Accept" link — the bulk route `/api/suggestions/bulk` already exists, app.py:2515). R4 per-provider columns
(defer, document). R5 MS refresh expiry (→ F8).

## Sequencing for build
1. **Fix F1 before S3.** 2. S3 must do the full `recommended_setup` 3-touch change. 3. **Build P2 fully (S3→S4→commit)
BEFORE P6 (S5)** — both edit `connections.py` + `app.py`; sequential avoids conflicts. 4. Give the P6 builder the
Windows-tz shim as a hard requirement (not an open risk). 5. `set_outlook_event_id` scopes by `business_id`.
