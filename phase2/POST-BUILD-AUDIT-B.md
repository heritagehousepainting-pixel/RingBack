# POST-BUILD-AUDIT-B — Phase 2 Security + Honesty + Risk + Edge Case Audit
**Auditor:** B (adversarial, read-only)  
**Date:** 2026-06-18  
**HEAD:** ~c397610 (staging, clean)  
**Suite:** 693 passed, 0 failed across 19 test files  

---

## SF-7 HONESTY VERDICT

**PARTIAL FAIL — one exploitable gap.**

`set_forwarding_confirmed(True)` appears in app.py at lines 1196, 1199, 1214, 1217 (all within `/setup/forwarding`) and line 2079 (inside `twilio_voice_inbound`). The inbound-match path at 2079 is correct and is the intended confirmation point.

The four `/setup/forwarding` sites are labelled "DEV/LOCAL FALLBACK" with comments claiming they are "unreachable on production." **This claim is FALSE.** All four are reachable on a Render deployment if `FIRSTBACK_PUBLIC_URL` is not set in the Render environment. The flow:

1. `messaging.configured()` returns `True` (Twilio creds are set on Render)
2. `connections.send_sentinel_call()` calls `_sentinel_twiml_url()` → returns `None` when `PUBLIC_BASE_URL` is empty → returns `{"status": "simulated"}`
3. Code falls through to `db.set_forwarding_confirmed(biz["id"], True)` **without any proof of carrier forwarding**

`render.yaml` does not include `FIRSTBACK_PUBLIC_URL`. It must be set manually in the Render dashboard. SETUP_NEEDED.md (line 34) documents this requirement but the code comment falsely guarantees the fallback cannot fire in production.

**`send_sentinel_call` itself is clean** — it correctly never sets `confirmed=True` and documents the honesty rule.

---

## SF-4 ABUSE VERDICT

**PARTIAL FAIL — retry cap is not enforced on the webhook path.**

The async retry design is correctly implemented in `reminders._enqueue_retry` (used by `run_due_once`). The webhook handler `twilio_sms_status` (app.py:2198) is Twilio-signature-protected, so forged callbacks cannot spam. **No synchronous retry loops exist.**

However, three bugs in `twilio_sms_status` break the webhook retry path:

1. **business_id is always None.** `get_message_by_provider_sid` returns a `messages` row. The `messages` table has no `business_id` column. `row.get("business_id")` is always `None`. All retry rows inserted from the webhook have `business_id=NULL`.

2. **Destination phone is always "".** `row.get("to", row.get("phone", ""))` — the `messages` table has no `to` or `phone` column. Retry rows have an empty destination encoded as `[retry_to:] body...`. When `run_due_once` processes these rows, `lead_phone` from the leads JOIN would save the phone — but only if `lead_id` is not NULL.

3. **Retry cap is not enforced.** `messages.retry_count` doesn't exist (migration only adds it to `scheduled_messages`). `row.get("retry_count")` returns `None` → `attempt = 1` on every webhook trigger. If retry message #1 fails at Twilio, the webhook creates retry #1 again indefinitely. The 3-attempt cap is bypassed for every retry beyond the first.

**Result:** Webhook-triggered retries silently fail (wrong business_id → `send_sms` simulates), and the 3-attempt cap cannot be reached via the webhook path. `run_due_once`'s own failure path works correctly.

---

## FINDINGS

### P0 — None

No unambiguous security holes, data-loss, or dishonest confirmed=True on a verified Twilio+cell deployment were found. The SF-7 and SF-4 gaps below are P1 (reachable but require env misconfiguration or rare Twilio delivery failure).

---

### P1-A: SF-7 False Safety Comment — Confirmed=True Reachable on Production without Proof
**File:** `app.py:1193–1217`  
**Risk:** Owner sees "forwarding verified" UI without actual carrier proof whenever `FIRSTBACK_PUBLIC_URL` is unset on Render (Twilio creds present). The sentinel call was never placed or confirmed by `twilio_voice_inbound`.  
**Fix:** Change the fallback from `set_forwarding_confirmed(True)` to `set_forwarding_confirmed(False)` + redirect to a `/setup?saved=forwarding&sentinel_skipped=1` with a clear UI message: "Twilio is configured but we couldn't reach your server to verify. Please ensure FIRSTBACK_PUBLIC_URL is set, then retry." Remove the claim "unreachable on production."  
**Alternatively (minimal):** Log a warning and do NOT set confirmed=True; let the UI show "unverified" state.

---

### P1-B: SF-4 Webhook Retry Path — business_id=None, Phone="", Cap Bypass
**File:** `app.py:2208–2232`, `db.py:2282–2294` (the INNER JOIN)  
**Risk:**  
- All webhook-initiated retries have `business_id=NULL` → `run_due_once` cannot look up the business → `send_sms` simulates → SMS is never actually retried.  
- The 3-attempt cap resets to 1 on each new retry message because `messages.retry_count` doesn't exist.  
- Owner `sms_fail` alert is never fired because `biz=None`.  
**Fix:** In `twilio_sms_status`, join through leads to get business_id: `db.get_lead(row["lead_id"])` → use `lead["business_id"]`. Then `biz = db.get_business(business_id)`. Pass `biz["id"]` to `queue_sms_retry`. For the cap bypass: either add `retry_count` to the `messages` table and update `add_message` to accept it, or check `scheduled_messages` for an existing open retry chain for this lead before enqueuing.

---

### P1-C: SF-4 due_scheduled_messages INNER JOIN — sms_retry Rows with NULL lead_id Drop Silently
**File:** `db.py:2286–2292`  
```sql
FROM scheduled_messages s JOIN leads l ON l.id = s.lead_id
```
This is an INNER JOIN. `queue_sms_retry` can be called with `lead_id=None` (when the original message has no lead — e.g. the alert path). Those rows are permanently stuck in `pending` status and never processed.  
**Fix:** Change to `LEFT JOIN leads l ON l.id = s.lead_id` and use `COALESCE(l.phone, '')` for `lead_phone`. `run_due_once` already handles empty phone by marking the row skipped.

---

### P2-A: SF-7 "Simulated" Status Not Surfaced to UI
**File:** `app.py:1193–1199`, `connections.py:344–346`  
`send_sentinel_call` returns `{"status": "simulated"}` when no twiml URL (no public URL). The route silently falls through to the manual confirm instead of showing the user a "Configure FIRSTBACK_PUBLIC_URL" error. The comment claims this is intentional for dev, but it's confusing for an operator who deployed to Render but forgot the env var.  
**Fix:** In the `/setup/forwarding` route, distinguish `status == "simulated"` from other errors. Show a dedicated message: "Verification skipped — FIRSTBACK_PUBLIC_URL not configured."

---

### P2-B: Alert sms_fail Body Renders Ugly with Empty "who"
**File:** `alerts.py:64–67`, `app.py:2229–2232`  
The `sms_fail` context passed from the webhook is `{"lead_id": ..., "message_id": ...}` — no `name` or `phone`. `_who(context)` returns `""`. The alert body becomes: `"SMS delivery failed after 3 attempts to . Check FirstBack for details."` (note the trailing `"to ."`)  
**Fix:** In `format_message`, check `who` before appending: `f"SMS delivery failed after {attempts} attempts{(' to ' + who) if who else ''}. Check FirstBack for details."`

---

### P2-C: Morning-of Reminder Near-Term Booking Ordering (Note, Not a Bug)
**Concern from spec:** "morning-of can't fire before the 24h reminder on near-term bookings."  
**Finding:** If a booking is made for tomorrow at 10 AM, `enqueue_reminder` computes a 24h send_at that is in the past (e.g. 10 AM today if booked at 9 PM). The past-dated row IS inserted with status=pending. `due_scheduled_messages` picks it up on the next tick (within seconds of booking). The morning reminder fires at 8 AM tomorrow. So **the 24h reminder fires immediately after booking (correct), and the morning fires at 8 AM next day (correct)**. The ordering is fine. **No bug — documented for clarity.**

---

## ADVERSARIAL PRICE GUARD TABLE

| Input | Expected | Result |
|---|---|---|
| "the estimate is free" | no scrub | PASS |
| "I have 3 rooms" | no scrub | PASS |
| "call us at 555-1200" | no scrub | PASS |
| "we'll be there at 2:30" | no scrub | PASS |
| "your area is 90210" | no scrub | PASS |
| "free estimate, no cost to you" | no scrub | PASS |
| "hundred of options available" | no scrub | PASS |
| "property is 2000 thousand sq ft" | no scrub | PASS |
| "available in 2024" | no scrub | PASS |
| "$0 deposit" | scrub | PASS |
| "the job is $500" | scrub | PASS |
| "five hundred dollars" | scrub | PASS |
| "that's 1200 dollars" | scrub | PASS |
| "200 bucks" | scrub | PASS |
| "2 coats, $350" | scrub | PASS |

**All 15 adversarial inputs pass. No false positives detected.**

---

## LANE-BY-LANE RESULTS

| Lane | Status | Notes |
|---|---|---|
| SF-7 Honesty | PARTIAL FAIL | 4 sites in setup/forwarding set confirmed=True without proof when PUBLIC_URL missing on prod (P1-A) |
| SF-4 Abuse | PARTIAL FAIL | Webhook path: business_id=None, phone="", cap bypass (P1-B). run_due_once path correct. No sync retries. |
| SF-5 DST | PASS | ZoneInfo throughout, no pytz, DST tests pass. 312=Chicago, 480=Phoenix (no-DST), 808=Honolulu verified. |
| F04 Cancel | PASS | cancel_event_async called correctly; 410 idempotent; all-day fix does not regress timed events. |
| F03 Price Guard | PASS | All adversarial inputs pass. Turn cap counts inbound, cap=12, handoff includes business phone. |
| F05 test_reminders | PASS | No pytest import. 34 tests pass. Morning-of ordering is correct. |
| Reliability | PASS | No smart quotes in error templates. 404/500 render HTML for browser paths, JSON for /api|/webhooks. |
| Auth on new routes | PASS | `/api/appointments/<id>/cancel` has @login_required. Sentinel TwiML has @require_twilio_signature. |
| PII leaks | PASS | sms_fail/forwarding_lost alerts contain no raw customer phone numbers. |

---

## SETUP_NEEDED ADDITIONS

Append to SETUP_NEEDED.md:
- **SF-7+SF-4 require `FIRSTBACK_PUBLIC_URL` set in Render env.** Without it: (a) the SMS StatusCallback is blank → no delivery receipts → webhook retry path never fires; (b) the sentinel TwiML URL is None → forwarding falls back to a manual confirm that falsely claims verification. This is the single highest-priority env var for Phase 2 correctness. Add it to render.yaml as a placeholder so it cannot be silently omitted.
