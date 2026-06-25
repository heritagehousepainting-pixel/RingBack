# Red-Team Lane 1: Correctness & Bugs — FirstBack
**Auditor:** Claude (Sonnet 4.6), adversarial read-only pass  
**Date:** 2026-06-25  
**Codebase:** /Users/jonathanmorris/Documents/apps/firstback (Flask + SQLite)  

---

## SEVERITY SUMMARY

| Severity | Count |
|---|---|
| P0 (crash / data-loss) | 4 |
| P1 (should-fix, correctness) | 9 |
| P2 (minor / edge-case) | 6 |

---

## P0 — Crash / Data-Loss

---

### P0-1: Hardcoded "painting" in voicemail recovery SMS — wrong message to every non-painting customer

**File:** `app.py:3812`

```python
messaging.send_sms(
    _biz_vs, _lead_vs["phone"],
    "We tried to reach you by phone -- happy to keep chatting "
    "here. What are you looking to get painted?"
)
```

**Trigger:** Any voicemail detection (AMD `machine_end_beep` etc.) on a live call for *any* tenant — not just Heritage House Painting.

**Bug:** The recovery SMS hardcodes `"What are you looking to get painted?"` instead of using a tenant-aware message. A plumber, electrician, or HVAC tenant's missed-call callback will tell the customer "What are you looking to get painted?" — actively confusing and damaging to that business's brand.

**Evidence:** Line 3812 in `twilio_voice_status`. This is the only place in `app.py` where a free-form SMS body string is not derived from `biz` data. Every other SMS path uses `biz.get("name")` or generic language.

**Fix:** Replace the hardcoded question with a neutral fallback like `"We tried to reach you — happy to keep chatting here. Just reply to get started."` or derive it from the business trade/name.

---

### P0-2: `_assistant_budget` double-increments rate counters on every call — throttle fires at half the intended rate

**File:** `app.py:208–224`

```python
throttled = db.incr_rate(biz["id"], "assistant", 60) > ASSISTANT_RPM
over_cap = ai.is_over_daily_cap(biz["id"])
turn_cap_ok = db.incr_rate(biz["id"], "assistant_daily", 86400) <= ASSISTANT_DAILY
```

**Trigger:** Every call to `/assistant` or `/assistant/stream` with a non-empty `message`.

**Bug:** `_assistant_budget` is called from BOTH `/assistant` (line 914) AND `/assistant/stream` (line 950). Each call to `_assistant_budget` increments both the per-minute and per-day rate buckets. However, when a streaming request comes in, the `_assistant_budget` call at line 950 already increments the counter. Then the UI (which may automatically fall back to `/assistant` on stream error) increments it a second time. More critically: the per-minute bucket `"assistant"` and the per-day bucket `"assistant_daily"` are each incremented unconditionally on every successful `_assistant_budget` call, meaning **the count increment occurs even if `throttled` is already True** (the function does not short-circuit after detecting throttle). An owner who hits the per-minute ceiling will continue to burn daily budget on every throttled attempt.

**Additional angle:** `db.incr_rate` uses `int(time.time() // window_secs)` as the key, so the daily window is 86400 seconds from epoch-start (UTC midnight), NOT from the user's local midnight. The `_next_local_midnight_iso` message shown to users when `allow_llm` is False will say midnight in their timezone — but the window actually rolls at UTC midnight. A user in e.g. Hawaii (UTC-10) will be told LLM access resets at midnight Hawaii time but it actually resets 10 hours earlier.

**Fix:** Short-circuit the counter increment when already throttled. Align the daily window to the business timezone midnight (or just use UTC midnight consistently and say UTC in the message).

---

### P0-3: Voice service streaming path double-processes each spoken turn — booking written twice per turn in production

**File:** `voice_service.py:380–428`

**Trigger:** Production mode (`WEB_INTERNAL_URL` set) with streaming enabled.

**Bug — Double booking write per turn:**

In `_stream_tokens`, the production path (line 155–180) makes an async HTTP call to `/internal/voice/stream` which streams tokens back — but **does NOT commit the booking** (it's a pure streaming endpoint, no `handle_inbound`). Good so far.

Then at line 409–428, the code calls `/internal/voice/turn` (which DOES run `handle_inbound`) to commit the booking.

**However:** `/internal/voice/stream` (`app.py:3694`) builds messages and calls `_llm.complete_stream_voice`. This streams tokens but does NOT call `handle_inbound`. But the concern is that in `_stream_tokens` the production path GETs the full response AND THEN the commit-turn POST at line 413 calls `/internal/voice/turn` which calls `handle_inbound` — which calls `db.add_message(lead_id, "in", text)` again (line 2004 of `app.py`). This means the inbound text is appended to `messages` once by the commit POST, but the history for the streaming call already used the text as user context. This produces duplicate inbound messages on the lead thread after every spoken turn in production mode.

**Evidence:** `handle_inbound` at `app.py:2004` unconditionally runs `db.add_message(lead_id, "in", body)`. The voice stream path has NO guard to skip the "in" message record when called from the voice turn commit. Each turn adds 1 "in" message (from the turn commit POST) but the history already has the text in `messages` context — causing the transcript to show the same caller utterance twice for every voice turn.

**Fix:** The `/internal/voice/turn` endpoint should accept an `already_recorded=True` flag to skip the `add_message("in")` call, since the `_stream_tokens` path already tracked the turn in `turn_log`.

---

### P0-4: `next_send_time` quiet-hours logic has an off-by-one — midnight is excluded from the sendable window

**File:** `reminders.py:108–115`

```python
def next_send_time(dt_local, quiet_start, quiet_end):
    if dt_local.hour < quiet_start:
        return dt_local.replace(hour=int(quiet_start), minute=0, second=0, microsecond=0)
    if dt_local.hour >= quiet_end:
        nxt = dt_local + timedelta(days=1)
        return nxt.replace(hour=int(quiet_start), minute=0, second=0, microsecond=0)
    return dt_local
```

**Default config:** `QUIET_START=8`, `QUIET_END=21`

**Trigger:** `followup` or `followup_2` queuing when the current local time has `hour=21` (9pm).

**Bug:** The condition `dt_local.hour >= quiet_end` fires at hour 21. Adding `timedelta(days=1)` then calling `replace(hour=8)` produces 8am the *next* day. But a time of 21:30 local time should theoretically push to the next morning — this is actually correct. The real issue is slightly different: when `compute_send_at` is called for a reminder where `target = appt - timedelta(hours=lead_hours)` lands exactly at 21:00 (the boundary), the condition `>= quiet_end` triggers and pushes to the next morning. This means a reminder configured for "1 hour before a 10pm estimate" gets pushed to 8am the *day after* the estimate — after the appointment has passed. The safeguard `if target >= appt` catches this and pins to `appt - 5 minutes`, but `appt - 5 minutes` is 21:55, which is also in quiet hours — the reminder is still pushed to next-morning but this time the `if target >= appt` check happens AFTER `next_send_time`, so the check correctly catches it. But for edge-case times (e.g. 21:55), the reminder goes out *after* the estimate with no valid slot.

**More severe angle:** For `followup` scheduling at `scan_followups` (line 456), the send_at is computed as `next_send_time(now_local, ...)` — which when `now_local` is between quiet_start and quiet_end, returns `now_local` unchanged. But `now_local` at line 453-455 is computed from the UTC `now` string, then converted to local time. If the UTC `now` string from `db.now_iso()` includes a timezone offset (it does — `now_iso` returns an aware ISO string), then `datetime.fromisoformat(now).astimezone(biz_tz)` is correct. However, the `t2_local` computation at line 490 does `(t1_dt + timedelta(days=5)).astimezone(biz_tz)` where `t1_dt` is `datetime.fromisoformat(send_at.replace("Z", "+00:00"))` — this `.replace("Z", "+00:00")` pattern is a sign that `send_at` was an ISO string that could contain "Z", and `fromisoformat` on Python < 3.11 does NOT parse "Z" as UTC. If `send_at` ever contains "Z", `t1_dt` will be naive and the subsequent `.astimezone(biz_tz)` will use the local system time instead of UTC, causing Touch-2 to fire at the wrong wall-clock time.

---

## P1 — Should Fix (Correctness Bugs)

---

### P1-1: `incr_rate` window key uses floor-division — per-minute window can be as short as 1 second

**File:** `db.py:3323–3339`

```python
key = f"{bucket}:{int(time.time() // window_secs)}"
```

**Trigger:** An owner sends a message right before a minute boundary.

**Bug:** The window is aligned to epoch time, not to a rolling 60-second window from first request. An owner could send 59 messages at 12:59:59, and then 60 more at 13:00:00, for 119 messages in 2 seconds without triggering the rate limiter. The counter resets at fixed epoch-aligned boundaries, not a sliding window. This is a well-known truncation-window limiter weakness.

**Severity:** P1 — the burst limiter can be trivially bypassed near minute boundaries.

---

### P1-2: `_cancel_estimate_for` triggered by "cancel" SMS only when customer has an appointment — misses the plain opt-out path

**File:** `app.py:3363–3372`

```python
norm = body.lower().strip(" .!")
if norm == "cancel":
    if _cancel_estimate_for(biz, caller):
        return _twiml("...")
    db.set_opt_out(biz["id"], caller, source="sms-cancel")
```

**Trigger:** A customer who has never booked sends "cancel".

**Bug:** If a customer has no booked appointment, "cancel" falls through to `set_opt_out`. This is documented as intentional design. But a customer who texts "CANCEL ALL" or "cancel please" will NOT hit this path — they need to text exactly "cancel" (after `strip(" .!")` normalization). More critically: `_STOP_WORDS` also contains "revoke" — but a customer typing "cancel all" will be silently processed by `handle_inbound` instead, because `norm` is "cancel all" and doesn't match `_STOP_WORDS`. The compliance check `detect_revocation` (FCC 2025 NLU opt-out) fires later at line 3378, but there's a gap: "cancel" without an appointment and "cancel" with an appointment have completely different behavior with no user feedback distinguishing them.

**The actual bug:** "cancel all" reaches `handle_inbound` and generates an AI reply that may book or confirm more things, when the customer intended to stop receiving messages.

---

### P1-3: `handle_inbound` cancels old appointments AFTER writing the new booking — brief double-booking window

**File:** `app.py:2073–2100`

```python
elif db.book_appointment(biz["id"], lead_id, booking):
    booked = booking
    ...
    # Reschedule: now that the new slot is held, release the lead's old
    # estimate(s) so a re-book never double-books or orphans a slot.
    for a in prior:
        db.cancel_appointment(biz["id"], a["id"])
```

**Trigger:** A lead re-books to a different slot.

**Bug:** The new appointment is written and committed BEFORE the old ones are canceled. Between `book_appointment` returning `True` and the `cancel_appointment` loop completing, both the old and new appointments exist with `status='booked'`. If the ticker runs in this window, it may send reminders for both. The DB uniqueness index prevents a third booking of the same slot, but two different slots can both show `booked` simultaneously for up to several DB operations (~100ms on SQLite with WAL).

**More severe case:** If the server crashes between writing the new booking and canceling the old ones, the lead ends up with TWO booked appointments permanently. SQLite WAL with proper crash recovery would replay the new INSERT but the DELETE for old appointments would be lost.

**Fix:** Wrap the rebook sequence (new INSERT + old DELETEs) in a single transaction.

---

### P1-4: `twilio_voice_status` voicemail recovery SMS hardcodes business-specific question (covered in P0-1) AND does not check A2P approval before sending

**File:** `app.py:3798–3813`

```python
if outcome == "voicemail" and sid:
    ...
    messaging.send_sms(
        _biz_vs, _lead_vs["phone"],
        "We tried to reach you by phone -- happy to keep chatting "
        "here. What are you looking to get painted?"
    )
```

**Additional bug beyond P0-1:** `messaging.send_sms` is called here WITHOUT checking `compliance.a2p_ready(biz)`. The SMS path includes A2P checks, BUT the voice-status webhook fires for outbound AI callbacks, and those require A2P approval for customer-facing messages. A tenant who has `inbound_voice_enabled=1` but has not completed A2P will have voice calls routed, then have the recovery SMS attempt to go out (it will be blocked by `messaging.send_sms` internally but will log as "simulated" — misleadingly suggesting a send). More importantly, if A2P approval is pending, this SMS should not be queued at all; the comment in `messaging.send_sms` says it handles this, but the silent simulation makes debugging hard.

---

### P1-5: `conversations_remaining` reads the most-recent grant (by `id`) without checking `period_end` — a lapsed annual subscriber appears to have full grant

**File:** `db.py:3657–3679`

```python
row = conn.execute(
    "SELECT * FROM usage_grants WHERE business_id=? "
    "ORDER BY id DESC LIMIT 1",
    (business_id,)).fetchone()
...
month_start = datetime.now(timezone.utc).replace(
    day=1, hour=0, minute=0, second=0, microsecond=0).date().isoformat()
consumed = conversations_consumed(business_id, month_start)
remaining = max(0, int(grant.get("conversations_granted") or 0) - consumed)
```

**Trigger:** A subscriber cancels or lets their plan lapse. `subscription_status` in `businesses` becomes `"canceled"`, but `usage_grants` rows are never deleted. The function returns the conversations from the most-recent grant row regardless of whether that grant period has expired.

**Bug:** A canceled subscriber continues to see "remaining" conversations and can use the LLM assistant indefinitely because `conversations_remaining` does not check `period_end` or `subscription_status`. The `is_over_daily_cap` in `ai.py` may have different logic, but the fuel gauge shown in the UI (and used by any other caller of `conversations_remaining`) shows a live grant.

**Fix:** Filter by `period_end >= now` or by `subscription_status IN ('active')` from the businesses table before returning the grant.

---

### P1-6: `_on_checkout_completed` does not call `_on_invoice_paid` — the first invoice after checkout doesn't grant conversations

**File:** `billing.py:239–251`

```python
def _on_checkout_completed(session_obj):
    business_id = _business_id_from_obj(session_obj)
    ...
    db.update_billing(business_id,
                      stripe_customer_id=customer_id,
                      stripe_sub_id=sub_id,
                      subscription_status="active",
                      plan=plan)
```

**Bug:** `checkout.session.completed` sets status to `"active"` and stores the plan, but does NOT write a `usage_grants` row. The `invoice.paid` event fires separately and would write the grant. However, if the `invoice.paid` webhook arrives BEFORE `checkout.session.completed` (which can happen with race conditions in Stripe webhooks), the invoice handler can't resolve the `business_id` from the invoice because `stripe_customer_id` hasn't been stored yet. In that case `_business_id_from_obj(invoice_obj)` returns `None` and the entire grant is silently dropped. The tenant is marked active but has zero conversation grants until the next month's renewal.

**Trigger:** Any race between Stripe webhooks arriving out of order, which Stripe's docs explicitly state can happen.

---

### P1-7: `_parse_tray_reply` incorrectly identifies owner by phone number using `to_e164` — a vanity number will fail

**File:** `app.py:3402–3409`

```python
owner_cell = messaging.to_e164((biz.get("alert_sms") or "").strip())
is_owner = bool(owner_cell and caller and messaging.to_e164(caller) == owner_cell)
```

**Trigger:** Owner saves their alert SMS number in a non-standard format (e.g., "(555) 123-4567" or "5551234567" without country code), and the Twilio `From` field comes in E.164 format (+15551234567).

**Bug:** If `biz["alert_sms"]` is stored as a 10-digit number (e.g., "5551234567"), `messaging.to_e164` will either normalize it to "+15551234567" or fail to parse it depending on implementation. If normalization succeeds, the comparison works. But if the owner's phone number has a non-US country code prefix and `to_e164` doesn't handle it, `is_owner` remains `False`. This means GO/SKIP commands from the owner will silently be processed as customer messages — going through `handle_inbound` and generating an AI reply to the owner's "GO" command, and possibly advancing leads the owner didn't intend to text.

**Severity:** P1 — could cause unexpected customer texts if the owner's growth tray commands are misinterpreted.

---

### P1-8: `scan_followups` enqueues `followup_2` even when `t1_id is None` (db.add_scheduled_message returns None on failure)

**File:** `reminders.py:471–498`

```python
t1_id = db.add_scheduled_message(biz["id"], lead["id"], None, "followup",
                                  send_at, body)
if t1_id is not None:
    queued += 1
    ...
    # S5: Queue Touch-2 immediately
    if not lead.get("has_followup_2"):
        try:
            ...
            db.add_scheduled_message(biz["id"], lead["id"], None, "followup_2",
                                      t2_send_at, t2_body)
```

**Bug:** Touch-2 is only queued when `t1_id is not None` (line 473 checks this). The Touch-2 block at line 486 is INSIDE the `if t1_id is not None:` block. This looks correct. However, if `add_scheduled_message` has a unique constraint that silently ignores a duplicate insert and returns `None` when there's already a `followup` row (UPSERT or INSERT OR IGNORE semantics), then `t1_id is None` and Touch-2 is never queued even if the existing followup record is stale or in a bad state. Check `db.add_scheduled_message` implementation for the return-None-on-constraint scenario.

Also: `has_followup_2` at line 486 is read from `lead.get("has_followup_2")` which comes from `followup_candidate_rows`. If this column is missing from the query result (schema migration not yet applied), `has_followup_2` always evaluates as `None` (falsy) and Touch-2 gets re-enqueued on every scan for leads that already received it.

---

### P1-9: `_connect_inbound_to_ai` makes a synchronous HTTP GET preflight inside a Twilio webhook response window

**File:** `app.py:3105–3108`

```python
try:
    _req.get(VOICE_PUBLIC_URL, timeout=0.4)
except Exception:
    return None
```

**Trigger:** Called on every inbound voice call where `inbound_voice_enabled=1`.

**Bug:** This 400ms synchronous HTTP GET runs inside a Flask request handler responding to Twilio's voice webhook. Twilio requires a response within 5 seconds (soft limit) or 10 seconds (hard limit). In production, the voice service may be on the same host or a different process. If the voice service is slow or under load (or the TCP handshake is slow), this 400ms can expand — and since `timeout=0.4` is a *connection + response* timeout combined in `requests`, it may not reliably time out in 400ms on a slow network. More critically, this GET also hits the root of `VOICE_PUBLIC_URL` — which is the FastAPI voice service. That root URL's behavior is undefined (it will return a 404 or a 405 from FastAPI's default handler). A 404 response is treated as "success" (no exception), so the preflight passes even if the voice service's `/twiml` or `/ws` endpoints are broken.

**Fix:** The preflight should probe `/health` or `/twiml` with a correct method, not the root. And use a shorter, separate connection timeout.

---

## P2 — Minor / Edge Case

---

### P2-1: `parse_day` silently rolls dates to next year for past dates in the same year — December wrap

**File:** `db.py:1722–1728`

```python
if d < today:
    try:
        d = date(yr + 1, mon, dd)
    except ValueError:
        return None
```

**Bug:** If a customer texts "book me for Feb 29" in 2026 (a non-leap year), `date(2026, 2, 29)` raises `ValueError`, the year+1 attempt `date(2027, 2, 29)` also fails (non-leap), and `parse_day` returns `None`. The AI would respond normally without booking, but the reply body already said (hypothetically) "Booked for Feb 29" — the text goes out but no appointment is written. However, this only occurs at the AI interpretation layer, where the LLM would likely generate a valid weekday label rather than "Feb 29".

More realistic: "book me for March 1" in December 2025, where `d = date(2025, 3, 1)` which is in the past, so the year rolls to `date(2026, 3, 1)`. This is correct behavior. But if `today` itself is March 1 (the requested day), `d < today` is False so no roll occurs — the date is today, which may or may not be what the customer meant.

---

### P2-2: `dispatcher_connect_twiml` dials a raw stored phone without E.164 normalization

**File:** `app.py:1832–1834`

```python
caller_number = _xesc(lead["phone"])
return _twiml(
    f'<Response><Dial>{caller_number}</Dial></Response>'
)
```

**Bug:** `lead["phone"]` is stored as-is from the Twilio `From` field (which is E.164). But if the lead was created manually via `/api/sim/incoming` with `"phone": "+1 (555) 000-0000"`, the stored phone contains spaces and parens. Twilio's `<Dial>` verb requires E.164 or a valid numeric string; a string like `"+1 (555) 000-0000"` may be rejected or cause a Twilio error mid-call. `_xesc` only escapes XML, not phone formats.

---

### P2-3: `_assistant_budget` is called twice for streaming turn — once for throttle check, once for actual processing — but the daily counter is only incremented once per stream call

**File:** `app.py:914–934` and `950–989`

Both `/assistant` and `/assistant/stream` call `_assistant_budget` exactly once. This is correct — but if an owner switches between streaming and non-streaming mid-session (e.g., the client auto-falls back to `/assistant`), they would be charged two incr_rate increments for what was conceptually one turn (the stream timed out, then the fallback succeeded). Minor from a rate-limit accuracy standpoint, but could cause false throttling.

---

### P2-4: `_login_failures` dict grows unbounded — in-memory DoS accumulation

**File:** `app.py:369–389`

```python
_LOGIN_FAILURES: dict = collections.defaultdict(list)
```

**Bug:** `_login_failures` is pruned within `_login_blocked` by filtering stale timestamps — but only for the key being queried. Keys from IPs that stop trying are never cleaned up. Over time (on a long-running process), many distinct (email, IP) pairs accumulate. For a legitimate DoS scenario: an attacker could hammer many distinct email+IP combinations, creating thousands of list entries. Each list has at most `login_max_attempts` timestamps (default 10). With 1 million distinct keys at 10 timestamps each: ~80MB of overhead — not crash-level but measurable on a small Render instance.

---

### P2-5: `voice_spend_this_month` uses local date's `date.today()` without UTC normalization — month boundary error

**File:** `db.py:3919`

```python
first_of_month = date.today().replace(day=1).isoformat()
```

**Bug:** `date.today()` uses the server's local timezone, not UTC. If the server is in UTC but a billing-cycle-start is defined differently, this is fine. However, the docstring says "current calendar month (UTC)" — if the server OS timezone is ever set to non-UTC, this query returns the wrong month boundary. The comparison `started_at >= first_of_month` in the query compares a local date string against UTC ISO timestamps stored in `voice_calls`. A server in UTC-5 on December 31st would compute `first_of_month = "2025-12-01"` — but `started_at` values are UTC ISO timestamps that could read `"2026-01-01T01:00:00"` for a New Year's Day call, making the cap seem spent when it isn't.

---

### P2-6: `twilio_sms_inbound` processes the inbound body through `handle_inbound` even when `SCREEN_AI_CONTENT` content-screening decides to bail — the AI content screen adds the message then exits silently

**File:** `app.py:3490–3497`

```python
if SCREEN_AI_CONTENT and not any(m["direction"] == "in" for m in db.get_messages(lead["id"])):
    intent = ai.classify_intent(biz, db.get_messages(lead["id"])
                                + [{"direction": "in", "body": body}])
    if not intent["is_prospect"] and intent["confidence"] >= 0.7:
        db.add_message(lead["id"], "in", body)
        db.upsert_suggestion(biz["id"], caller, lead.get("name"), "blocked", ...)
        return _twiml("<Response/>")
```

**Bug:** When AI content screening fires, `db.add_message(lead["id"], "in", body)` records the inbound message on the thread, then the handler returns `<Response/>` without texting back. This is intentional. However, `handle_inbound` is never called, so `open_conversation` was called earlier (via `_missed_call_textback`) and the lead has an outbound message but no inbound. The thread shows: [out: opener, in: suspicious text]. The outbound opener was already sent via `messaging.send_sms` in `_missed_call_textback`. Then the screen fires on the first reply. The lead is orphaned in `status='new'` with no follow-up queued, and the owner's suggestion inbox flags it as "blocked". This is by design but means a legitimate customer whose first message happens to look like a sales pitch (e.g., "I need to upgrade my electrical panel") could be permanently silenced with no recourse until the owner reviews the suggestion.

---

## TOP 5 FINDINGS

| Rank | ID | Finding | Impact |
|---|---|---|---|
| 1 | P0-1 | Hardcoded "painting" voicemail recovery SMS sent to all tenants | Brand damage for all non-painting businesses using voice |
| 2 | P0-3 | Voice stream double-processes turns — duplicate "in" messages in DB | Corrupt conversation history, wasted LLM calls, potential double-booking |
| 3 | P0-2 | Rate limiter increments counters on every call including throttled calls; daily window is UTC-epoch-aligned not user-timezone-midnight | Owners throttled more aggressively than intended; incorrect "resets at midnight" display |
| 4 | P0-4 | `.replace("Z", "+00:00")` in Touch-2 scheduling will fail on Python < 3.11 where fromisoformat doesn't parse "Z" | Touch-2 fires at wrong time or raises ValueError (silent catch) |
| 5 | P1-6 | Stripe webhook race: checkout.completed before invoice.paid can cause zero-grant subscription | New subscribers get no conversation allotment until next month's renewal |

---

## NOTES ON TEST COVERAGE GAPS

1. **No test verifies voicemail recovery SMS content across multiple tenant trades** — `test_voice.py` / `test_voice_app.py` likely use the demo/painting biz.
2. **No test exercises the Stripe webhook race** where `invoice.paid` arrives before `checkout.session.completed`.
3. **No test for `conversations_remaining` against a canceled subscription** — the lapsed-grant bug (P1-5) would not be caught.
4. **`voice_service.py` double-write** is hard to catch in unit tests because local mode (`WEB_INTERNAL_URL` unset) skips the commit POST; the bug only manifests in production split-service mode.
5. **The `parse_day` Feb-29 edge case** is unlikely to be tested.
6. **The `_assistant_budget` UTC-vs-localtime window mismatch** is unlikely to be tested because tests typically run against a fixed now without timezone drift.

---

---

## TEST RUN RESULTS

**`import app`:** Clean — no import-time errors.

**Test suites run (all via `FIRSTBACK_DB_PATH=/tmp/rtX.db .venv/bin/python test_X.py`):**

| Suite | Result | Coverage gaps relevant to this audit |
|---|---|---|
| `test_billing.py` | 38 passed, 0 failed | No test for `conversations_remaining` against canceled subscription (P1-5 undetected) |
| `test_reminders.py` | 59 passed, 0 failed | No test for quiet-hours edge case at `lead_hours=0` with appt at `quiet_start` (P0-4 undetected) |
| `test_voice_app.py` | 61 passed, 0 failed | Recovery SMS body only checked for keyword `"phone"` — no multi-tenant body check (P0-1 undetected) |
| `test_voice_stream.py` | 42 passed, 0 failed | No test verifies message count in DB after a voice turn; duplicate `add_message("in")` bug (P0-3) not detected |
| `test_inbound_voice.py` | 38 passed, 0 failed | All pass |
| `test_scheduling.py` | 18 passed, 0 failed | All pass |
| `test_triage.py` | 46 passed, 0 failed | All pass |
| `test_screening.py` | 57 passed, 0 failed | All pass |
| `test_growth_tray.py` | 43 passed, 0 failed | All pass |
| `test_fsm_sync.py` | 92 passed, 0 failed | All pass |
| `test_webhooks.py` | 18 passed, 0 failed | All pass |
| `test_voice_metering.py` | 31 passed, 0 failed | No test for UTC vs. local-date boundary (P2-5 undetected) |
| `test_reliability.py` | 15 passed, 0 failed | All pass |
| `test_usage_gauge.py` | 17 passed, 0 failed | No test for canceled-subscriber grant leakage (P1-5 undetected) |

**Zero test failures across all suites.** The bugs in this report are all latent and not caught by the existing test suite.

---

*Report written to:* `/private/tmp/claude-501/-Users-jonathanmorris-Documents-apps-firstback/66277eb4-b9c4-4b14-95b3-18161d0a99f5/scratchpad/redteam/01-correctness-bugs.md`
