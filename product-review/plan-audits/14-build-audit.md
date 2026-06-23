# Build Audit — Plan 14 (Outlook Calendar)
**Stage:** S6 BUILD-AUDIT · **Date:** 2026-06-23 · read-only review of uncommitted code.

**Verdict: SHIP-WITH-NITS** → nits fixed by orchestrator before commit. No P1 blockers.

## Orchestrator-caught CRITICAL (pre-audit)
The build agent's editor mangled `templates/settings.html` calendar-card Jinja string delimiters into
smart quotes → `TemplateSyntaxError` (whole `/settings` page down; also what the build agent misreported
as a "pre-existing" test_scheduling failure). Orchestrator fixed 9 lines → straight-quote delimiters,
verified `/settings` renders 200 with both cards. The audit's independent smart-quote scan then came back
clean (no delimiter corruption remained).

## Audit fixes confirmed landed (with evidence)
- **F6 Windows→IANA tz shim:** `outlook_cal.py` `_WINDOWS_TZ_TO_IANA` + `_resolve_tz_name` (try IANA → dict → fail-open); used in `connect_with_code`. Test: "Eastern Standard Time" → `America/New_York`, bad-tz fail-open.
- **F7 recommended_setup 3-touch:** `outlook_connected` kwarg + "outlook" row + app.py call site; `jobber_connected` preserved; calendar item done when google OR outlook. `test_setup` asserts 11 items.
- **F8 refresh→reconnect:** `_access_token` refresh failure calls `db.set_oauth_tokens(…, None, None, None)` → `is_connected`→False → "Reconnect Outlook". Test verifies.
- **F10 module-top import:** `import outlook_cal` at app.py top.
- **Scoping:** `db.set_outlook_event_id` uses `WHERE id=? AND business_id=?`; cross-tenant test verifies wrong biz can't write.

## Security / correctness / honesty
Gated inert when `MICROSOFT_CLIENT_ID` unset (every entry point no-op, no HTTP). Tokens encrypted via
`set_oauth_tokens`, never logged. business_id scoping throughout; disconnect route CSRF + login_required;
`ol_state` verify-and-consume; all HTTP fail-open (never breaks Google path or a booking). Busy-slot union
correct; both booking paths + cancel guarded; both providers connectable at once. Copy honest (placeholder
when unconfigured; "Connected"/"Reconnect needed" only when true; tz stored silently).

## Nits → FIXED before commit
- **P2-2** theoretical naive-datetime in `_graph_slots_conflicting` could TypeError → void all slots (fail-open
  but silent) → now coerces naive Graph datetimes to UTC before comparison.
- **P2-3** no `/settings` render test (the just-bit bug class) → added section 25: GET /settings == 200 +
  Outlook + Jobber cards present. (test_outlook_cal now 88/0.)
- **P2-1** (left as follow-up): busy-slot union test exercises `set()|set()` rather than the app.py line;
  provider-level + booking-guard tests already cover the behavior.

Post-fix: test_outlook_cal 88/0; test_scheduling 18/0; test_fsm_sync 78/0; test_setup 147/0; imports clean.
