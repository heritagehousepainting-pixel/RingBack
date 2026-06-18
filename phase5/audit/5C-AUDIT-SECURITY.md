# Phase 5c Security / Consent / Tenant-Isolation Audit

**Date:** 2026-06-18  
**Branch:** staging @ 1af7195  
**Auditor:** Read-only static analysis + throwaway probes in /tmp  
**Scope:** F07 screening graduation — rescue endpoint, settings prefs, auto-graduation,
graduation alert, crowd/burst signals, reputation gate, 5b regression, PII.

---

## Summary

**P0:** 0  
**P1:** 0  
**P2:** 2 (non-blocking, defense-in-depth gaps)  
**Clean / verified-safe:** 14 properties

No critical or high-severity findings. The two P2 items are defense-in-depth gaps — not
directly exploitable in the current code, but worth hardening in a follow-up pass.

---

## P0 Findings

None.

---

## P1 Findings

None.

---

## P2 Findings

### P2-A — `mark_call_engaged` lacks `business_id` in its UPDATE clause

**File:** `db.py:1821`  
**Code:**
```python
conn.execute("UPDATE calls SET engaged=1, lead_id=COALESCE(?, lead_id) WHERE id=?",
             (lead_id, call_id))
```

**Risk:** The UPDATE is keyed only on `call_id` (a bare integer). There is no
`AND business_id=?` guard. In the current code this is safe because both the rescue
endpoint (`api_rescue_screened_call`) and the engage endpoint (`api_engage_screened_call`)
call `db.get_call(call_id, biz["id"])` first — and that function filters by
`WHERE id=? AND business_id=?`, returning None on a cross-tenant id, causing a 404 before
`mark_call_engaged` is ever reached.

The gap is a future-proofing concern: any new code path that calls `mark_call_engaged`
without first scoping through `get_call` would allow one tenant to flip another tenant's
call row to `engaged=1`. The engaged flag triggers the lead association and could suppress
a second rescue notification.

**Suggested fix:**
```python
conn.execute(
    "UPDATE calls SET engaged=1, lead_id=COALESCE(?, lead_id) "
    "WHERE id=? AND business_id=?",
    (lead_id, call_id, business_id))
```
Add `business_id` parameter to the function signature and pass `biz["id"]` from all
call sites.

---

### P2-B — `/api/calls/<id>/real` and `/api/calls/<id>/engage` lack a CSRF double-submit token

**Files:** `app.py:1997` (rescue), `app.py:1971` (engage)  
**Code:** Both endpoints have `@login_required` only. Neither calls `_csrf_ok()`.  
**Compare to:** `app.py:812` (`/api/assistant`) which checks `_csrf_ok()` in addition
to `@login_required`.

**Risk:** SameSite=Lax (set at `app.py:53`) blocks cross-site form POSTs in modern
browsers — this is meaningful protection. However, the rescue endpoint is qualitatively
more consequential than a standard API call: a successful CSRF-driven rescue resets the
7-day graduation clock (via `db.record_screening_rescue`) AND upserts the caller's number
as `"customer"`. A crafted page hosted on a different domain that can trigger a
same-site-credential-bearing POST (e.g., via subdomain confusion on a shared hosting
platform, or a lax SameSite implementation in older browsers) could silently delay
graduation indefinitely and contaminate the contact directory.

The sibling `flag-spam` endpoints (`/api/calls/<id>/flag-spam`,
`/api/leads/<int:lead_id>/flag-spam`) have the same gap. Consistent with them, but the
rescue endpoint carries higher consequence.

**Suggested fix:** Add `if not _csrf_ok(): return jsonify(error="bad_csrf"), 403` to
both the rescue and engage endpoint bodies, and ensure the dashboard JS includes `_csrf`
in the POST body for those buttons (the framework is already wired for the assistant).

---

## Verified-Safe Properties

The following were actively confirmed (code inspection + throwaway probes):

1. **Rescue tenant-scoping:** `db.get_call(call_id, biz["id"])` at `app.py:2006` uses
   `WHERE id=? AND business_id=?` — probe confirmed biz_b cannot retrieve biz_a's call,
   returns None → 404. Cross-tenant rescue is impossible at the endpoint level.

2. **Opted-out rescue blocked:** `db.is_suppressed(biz["id"], caller)` checked at
   `app.py:2012` BEFORE `db.record_screening_rescue` is called. A STOP-opted number
   cannot be re-texted via the rescue path. The suppression check is per-tenant
   (business_id scoped via `contacts_consent`).

3. **`_save_screening_prefs` scoped to current business:** The UPDATE at `app.py:1106-1109`
   is `WHERE id=?` with `business_id` as the final parameter. The value is always
   `biz["id"]` from `current_business()`, which is derived from the authenticated session
   user. No cross-tenant write path exists.

4. **Threshold values: preset-only, no raw numeric input:** The settings handler
   (`app.py:1160-1165`) maps `screen_sensitivity` radio to `SCREEN_SENSITIVITY_PRESETS`
   keys only. Unknown/crafted keys fall through to `hard_val, mid_val = None, None`
   (config defaults). There is no raw `screen_hard`/`screen_mid` numeric form field —
   an attacker cannot POST an arbitrary threshold (e.g., 0 or -1) through the settings
   form. Minimum allowed hard threshold via presets is 65 ("aggressive").

5. **Rescue → defer chain cannot be bypassed:** `db.record_screening_rescue` resets
   `screening_window_start` to `now()` atomically (same `conn.commit()`). The graduation
   scanner reads `window_start` from the DB at tick time and computes `age_days`. A window
   reset to "now" means `age_days < 7` on the next pass, blocking promotion. Test suite
   verified this: test case 10 confirms rescue → graduation deferred.

6. **Graduation never fires when `screening_hold=1`:** `reminders.py:510`
   `if biz.get("screening_hold"): continue`. No graduation code path modifies
   `screening_hold`. A business with the hold set can never be auto-promoted.

7. **Graduation never fires in off/enforce mode:** Effective mode resolution in
   `reminders.py:503-507` skips any business not in `"monitor"` mode. Businesses
   already in enforce (promoted) are skipped automatically.

8. **Graduation alert goes to OWNER cell only:** `alerts.py:244`
   `sms_to = (business.get("alert_sms") or "").strip()`. The `business` dict passed to
   `alerts.notify` is `db.get_business(bid)` (the business row). The context passed for
   `screening_graduated` is `{"n": would_screen}` — no caller phone number is included.
   `format_message` for this kind only uses `context.get("n")`. The alert body does NOT
   contain any customer phone number or caller identity.

9. **Graduation alert body is honest, no customer-contact claim:** Confirmed via probe:
   the body is `"Spam blocking is now ON -- this week we'd have blocked N robocallers and
   you rescued none. Manage or pause it in Settings."` — no "texted", "contacted",
   or caller PII. Test suite case 12 covers this.

10. **Burst alone cannot reach HARD:** At default HARD=80: burst(+35) alone = 35 < 80.
    At the most aggressive preset HARD=65: burst(35) + neighbor_spoof(25) = 60 < 65.
    burst + att_C(30) = 65 = 65 (just meets aggressive preset, but att_C is a genuine
    failed-verification signal, not arbitrary data). Corroboration is required to reach
    HARD at any preset. Confirmed via probe.

11. **`within_hours` SQL injection safe:** The `within_hours` value in
    `db.global_spam_count` is used only in `timedelta(hours=within_hours)` arithmetic —
    a non-numeric value raises `TypeError` before the SQL is constructed. The actual SQL
    uses parameterized `args.append(cutoff)` with `WHERE created_at>=?`. No injection
    surface. Confirmed via probe.

12. **Per-tenant reputation gate is a double gate:** `_effective_reputation_enabled(biz)`
    at `app.py:2335-2340` requires BOTH `reputation.configured()` (provider key present)
    AND `bool(biz.get("reputation_enabled"))` (per-tenant toggle). Default is
    `reputation_enabled=0`, so existing tenants are never charged without explicit opt-in.
    In the test environment, `reputation.configured()` returns False → no paid lookup.

13. **5b `enforce_ack` two-tap not regressed:** `app.py:953-957` — the gate
    `if (tool == "set_screen_mode" and args.get("mode") == "enforce" and enforce_ack != "true")`
    is still present and intact. Graduation bypasses this deliberately (it is the
    announced auto-path, not the assistant command path) — as per spec.

14. **No raw PII in log statements:** Searched all five key files (`app.py`, `db.py`,
    `triage.py`, `reminders.py`, `alerts.py`) for `print()` calls containing
    `number`, `caller`, or `phone` references. None found. Screening reasons logged to
    the `calls.screen_reasons` column are stored in the DB (not stdout) and use generic
    human-readable strings ("attestation C", "crowd flagged", etc.) without raw numbers.

---

## Test Suite Results

`python3 test_screening_graduation.py` (standalone, real temp DB, no Twilio):
**61 passed, 0 failed.**

`test_screening_ui.py` and `test_screening.py` could not run (Flask not installed in
`/Library/Frameworks/Python.framework/Versions/3.14`). All graduation-core tests passed
without Flask.

---

## Dave Test Assessment

A non-tech contractor ("Dave") cannot accidentally:
- Trigger enforce mode without the 7-day clean window (graduation requires time + verdicts).
- Be silenced after a STOP (suppression check is first in the rescue path).
- Have their calls rescued by a different business (tenant scope blocks it).
- Lose the rescue option after a false positive (the "This was real" button resets the
  clock, customer is upserted, re-engagement follows).

The Settings sensitivity preset is a named radio (conservative / balanced / aggressive),
not a raw number input — Dave cannot craft an absurd threshold by accident.

---

## Recommendations (in priority order)

1. **(P2-A, short-term)** Add `AND business_id=?` to the `UPDATE` in `mark_call_engaged`
   as a defense-in-depth hardening. Low risk now, high insurance value as the codebase grows.

2. **(P2-B, short-term)** Add `_csrf_ok()` check to `api_rescue_screened_call` and
   `api_engage_screened_call`. The dashboard JS already has the CSRF token infrastructure
   from the assistant buttons; wiring it to these buttons is a one-line change per handler.

3. **(P2, nice-to-have)** Consider a CROWD_MIN of 3 or a per-business flag-rate limit to
   reduce the colluding-accounts crowd-poisoning surface (currently requires 2 distinct
   business accounts but no ownership verification).
