# Plan 03 — Core Loop Speed + Known-Caller Alert + Reminder Copy

**Workstream:** Core-Loop Speed / Known-Caller / Reminder Copy  
**Grounding:** `app.py`, `ai.py`, `reminders.py`, `alerts.py`  
**Date:** 2026-06-19

---

## Overview

Three independent changes in descending impact order:

1. **Fast first text-back** — skip the LLM on turn 0; send a hardcoded branded opener instantly.
2. **Known-caller owner alert** — when a trusted past customer is silenced in enforce mode, fire a "they called, reach out" owner alert.
3. **Reminder copy rewrite** — warmer language + contractor's direct phone in every reminder/follow-up.

---

## Change 1: Fast First Text-Back (Zero-LLM Turn 0)

### What and why

`open_conversation` in `app.py` line 1739 calls `ai.generate_reply(biz, [], ...)` with an empty history. This puts a cold Claude Sonnet call (up to 30 s, see `ai.py` line 140 `timeout=30`) on the critical path between the missed call and the first SMS landing on the customer's phone.

When history is empty the AI has nothing to work with. The demo mode (`_demo_reply`) returns a hard-coded `"Hi! This is {business['name']} -- sorry we missed your call. What were you looking to get painted?"`. The LLM at turn 0 produces something nearly identical but takes 5–30 s to do so.

Replacing the LLM call for turn 0 with a direct template eliminates this latency entirely. The LLM is still used from turn 1 onward (when the customer has actually said something and the LLM adds value).

### Where

**File:** `app.py`  
**Function:** `open_conversation` (line 1731)

Current call site (line 1739):
```python
reply, booking = ai.generate_reply(biz, [], exclude_slot_ids=exclude)
```

### Approach

**(a)** Add a new pure function in `ai.py`:

```python
def instant_opener(business):
    """Hardcoded, zero-latency first text-back. No LLM call.
    Called by open_conversation when history is empty (turn 0).
    Returns (text, None) — never books on the opener."""
    name = (business.get("name") or "us").strip()
    return (
        f"Hi, this is {name} — sorry we just missed your call! "
        "What can we help you with? We'd love to book you a free estimate."
    ), None
```

**(b)** In `open_conversation` (`app.py` line 1731), branch before the `generate_reply` call:

```python
# Turn 0: send a zero-latency hardcoded opener; reserve the LLM for turn 1+
# when the customer has actually said something.
if not db.get_messages(lead["id"]):  # called only on empty thread, but guard anyway
    reply, booking = ai.instant_opener(biz)
else:
    reply, booking = ai.generate_reply(biz, [], exclude_slot_ids=exclude)
```

Actually `open_conversation` is only called when the thread is empty (caller in `_missed_call_textback` at line 2617 already gates on `if not db.get_messages(lead["id"])`). The check is redundant but harmless. The simpler approach: **always use the template in `open_conversation`** since it's only ever called on an empty thread:

```python
# open_conversation is called exactly when the thread is empty (turn 0).
# Use the instant template — no LLM call needed when the customer hasn't said anything.
reply, booking = ai.instant_opener(biz)
```

This is safe. `open_conversation` handles the `if booking:` branch that follows — since `instant_opener` returns `(text, None)`, `booking` is always `None` here and the booking block is skipped entirely (correct: no customer has named a time yet).

**Important:** there is a second call to `open_conversation` at `app.py` line 1968 (inside a `handle_inbound` re-intro path) and one at line 707. Both are also empty-thread openers — the same template is correct for all.

**(c)** The existing `open_conversation` at line 2169 and 2200 (voice paths) also call `open_conversation` on a new lead — the same branch applies and is correct.

### Booking correctness

`instant_opener` returns `booking=None`, which means no appointment is created at turn 0. This is correct: the customer hasn't accepted a slot. Booking only happens at turn 2+ when `handle_inbound` → `generate_reply` detects the `[[BOOK:]]` marker. No change to `_resolve_booking`, `db.book_appointment`, or any downstream booking logic.

### Tests

- `test_ai.py` (or `test_f03_brain.py`): add `test_instant_opener_returns_str_and_no_booking` — asserts `instant_opener` returns a non-empty string and `None` for the booking.
- `test_ai.py`: add `test_instant_opener_uses_business_name` — verify the business name appears in the text.
- `test_app.py` / `test_f03_brain.py`: patch `ai.instant_opener` in a `open_conversation` unit test to confirm it is called (not `generate_reply`) on an empty-history call. Confirm the returned `reply` is sent via `messaging.send_sms`.
- `test_f03_brain.py` integration: existing `open_conversation` tests should still pass; verify the opener text is reasonable.

**Collision note:** `open_conversation` is also touched by any workstream that tests the AI-conversation pipeline. Agents working on AI-conversation or onboarding changes should be aware that `open_conversation` no longer calls `generate_reply` for turn 0.

### Effort: **S** (1–2 h)

### Risk: Low

The change is additive: `instant_opener` is a new pure function; the existing `generate_reply` is unchanged. The only risk is if any test asserts that `open_conversation` calls `generate_reply` — those tests should be updated to assert `instant_opener` is called instead.

---

## Change 2: Known-Caller Owner Alert ("They called — no auto-text sent")

### What and why

In `_missed_call_textback` (`app.py` line 2608):

```python
if not verdict["engage"] and mode == "enforce":
    db.log_call(biz["id"], call_sid, engaged=0, **common)
    return False
```

When `triage.screen_caller` returns `status: "trusted"` (a past customer, detected via `db.is_known_caller` at `triage.py` line 175), this branch fires. The call is logged (`engaged=0`) and the function returns. No text is sent to the customer. No alert fires to the owner. The contractor has to actively check the call log to learn a past customer called.

This is a silent lead drop. A returning customer — the highest-value call type — gets nothing and triggers no owner action.

The fix: fire an owner alert in the same branch, distinguishing the "known caller" case from "spam/opted-out" so the owner gets an actionable message.

### Where

**File:** `app.py`  
**Function:** `_missed_call_textback` (line 2580)

Current code at lines 2608–2610:
```python
if not verdict["engage"] and mode == "enforce":
    db.log_call(biz["id"], call_sid, engaged=0, **common)
    return False
```

### Approach

**(a)** Add a `"known_caller"` alert kind — OR reuse an existing kind with differentiated copy.

Preferred path: **reuse the existing `"lead"` kind** with a context flag. The `lead` alert fires for new prospects; a "known caller — no text" alert can share the same owner-facing channel (SMS + in-app) and respects the same `alert_on_lead` toggle.

The context flag: pass `"known": True` in the context dict. `format_message` for `"lead"` checks this flag and returns different copy.

**File: `alerts.py`** — update `format_message` for `"lead"`:

```python
if kind == "lead":
    # Known caller: past customer; no auto-text sent in enforce mode.
    if context.get("known"):
        phone = (context.get("phone") or "").strip()
        tail = f" ({phone})" if phone else ""
        return (f"Past customer{tail} just called — we didn't auto-text them. "
                f"Give them a ring when you get a chance.")
    proj = (context.get("project") or "").strip()
    about = f' about "{proj}"' if proj else ""
    return f"New lead: {who}{tail}{about}. Open FirstBack to reply."
```

**Dedupe key:** the existing `_dedupe_key` for `"lead"` returns `f"lead:{context.get('lead_id')}"` — this is correct. A known caller who calls twice quickly dedupes against the same lead ID (120 s window). If they call again the next day, a new alert fires (different event).

**(b)** In `_missed_call_textback`, replace the early return with an alert + return:

```python
if not verdict["engage"] and mode == "enforce":
    db.log_call(biz["id"], call_sid, engaged=0, **common)
    # If this is a trusted/known caller (not spam), alert the owner so they
    # can personally follow up. Spam/opted-out callers get no alert.
    if verdict.get("status") == "trusted":
        # Need the lead row for the lead_id in the dedupe key.
        _lead = db.get_lead_by_phone(biz["id"], caller)
        alerts.notify_async(biz, "lead", {
            "lead_id": _lead["id"] if _lead else None,
            "name": _lead.get("name") if _lead else None,
            "phone": caller,
            "known": True,
        })
    return False
```

This does NOT create a new lead if none exists. `db.get_lead_by_phone` returns None for a truly unknown phone. In that case: no `lead_id`, dedupe key is `"lead:None"` — which could collide across different unknown callers within 120 s. Mitigation: use `caller` in the dedupe key for the known-caller case by passing `"phone"` to the context. The existing `_dedupe_key` uses `lead_id` not `phone`, so brief collision window is acceptable for this edge case.

Alternative: create the lead if it doesn't exist. The audit notes that `db.is_known_caller` checks `db.get_lead_by_phone` — if the caller is "trusted," they almost certainly already have a lead row. The `None` case is extremely rare. Proceed without lead creation to stay minimal.

### Tests

- `test_app.py`: unit test `test_known_caller_enforce_fires_owner_alert` — stub `triage.screen_caller` to return `{"engage": False, "status": "trusted", "score": 0, "category": "trusted", "reasons": []}`, assert `alerts.notify_async` is called with `kind="lead"` and `context["known"] == True`.
- `test_app.py`: `test_spam_caller_enforce_no_alert` — stub verdict as `screened_spam`, assert `notify_async` is NOT called.
- `test_app.py`: `test_opted_out_enforce_no_alert` — stub verdict as `opted_out`, assert `notify_async` is NOT called.
- `test_alerts.py`: `test_format_message_known_lead` — assert the "Past customer ... just called" copy is returned.
- `test_alerts.py`: existing `test_format_message_lead` — must still pass (unaffected when `known` is absent).

**Collision note:** `alerts.py` and `app.py` are shared with workstreams 07 (Notifications) and 04 (Screening). Coordinate: 
- Workstream 07 may also be adding alert kinds — confirm `ALERT_KINDS` tuple additions don't conflict.
- Workstream 04 may touch `_missed_call_textback` for screening-mode changes — ensure the `known_caller` branch is inserted before any screening-mode refactor.

### Effort: **M** (3–4 h including tests)

### Risk: Low-Medium

Adding an alert in the screened-out branch is safe — the branch currently does nothing alertable. The `format_message` change is pure and unit-testable. The only risk: if the `lead` alert is being throttled or dedupe-colliding for an unknown-phone caller, the owner misses the alert. Mitigated by the 120 s window being short.

---

## Change 3: Reminder Copy Rewrite (Warmer + Include Business Phone)

### What and why

`reminder_body` in `reminders.py` (lines 72–75):

```
"Hi {first_name}, this is {business_name}. A friendly reminder of your free estimate {when}. We look forward to seeing you, and you can reply here if anything has changed."
```

Problems per audit finding 5:
1. "We look forward to seeing you" — stiff, not how a contractor texts.
2. "Reply here if anything has changed" — vague; doesn't say cancel/reschedule.
3. No contractor direct phone — customers who need to call day-of are stranded.

`followup_body` (lines 78–80) also stiff.

Both functions are called at:
- `enqueue_reminder` (reminders.py line 170) — passes `business.get("name")` but NOT `business.get("phone")`.
- `enqueue_morning_reminder` (reminders.py line 221) — same.

**Fix:** Add `phone` parameter to `reminder_body` and `followup_body`; update callers to pass `business.get("phone")`.

### Where

**File:** `reminders.py`  
**Functions:** `reminder_body` (line 72), `followup_body` (line 78), `enqueue_reminder` (line 152), `enqueue_morning_reminder` (line 179)

### Approach

**(a)** Rewrite `reminder_body`:

```python
def reminder_body(name, business_name, when, phone=None):
    phone_line = f" Call us at {phone} or reply here" if phone else " Reply here"
    return (
        f"Hi {_first_name(name)}! Just a reminder — {business_name} is coming "
        f"{when} for your free estimate. Questions or need to reschedule?"
        f"{phone_line}."
    )
```

Example output: `"Hi Maria! Just a reminder — Dave's Painting is coming Mon Jun 15 at 9:00 AM for your free estimate. Questions or need to reschedule? Call us at (555) 555-1234 or reply here."`

**(b)** Rewrite `followup_body`:

```python
def followup_body(name, business_name, phone=None):
    phone_line = f" Call or text us at {phone}." if phone else " Just reply here."
    return (
        f"Hi {_first_name(name)}, {business_name} here — still happy to get you "
        f"a free estimate.{phone_line} What day works best?"
    )
```

**(c)** Update callers to pass the phone:

`enqueue_reminder` (line 170):
```python
body = reminder_body(
    lead.get("name"),
    business.get("name") or "your contractor",
    when_phrase(day_iso, slot_time),
    phone=business.get("phone") or None,
)
```

`enqueue_morning_reminder` (line 221):
```python
body = reminder_body(
    lead.get("name"),
    business.get("name") or "your contractor",
    when_phrase(day_iso, slot_time),
    phone=business.get("phone") or None,
)
```

`followup_body` is called inside `scan_followups` (line 450) via `followup_body_contextual` which falls back to `followup_body`. Both `followup_body_contextual` (line 387) and the direct call to `followup_body` in `scan_followups` need the business phone. `scan_followups` has `biz` in scope (line 428); update the fallback:

In `followup_body_contextual` (line 418):
```python
return followup_body(name, biz_name, phone=biz.get("phone") if biz else None)
```

But `followup_body_contextual` currently takes `(name, biz_name, last_in_text)` — add `phone=None`:
```python
def followup_body_contextual(name, biz_name, last_in_text, phone=None):
    ...
    return followup_body(name, biz_name, phone=phone)
```

And update the `scan_followups` call (line 450):
```python
body = followup_body_contextual(
    lead.get("name"), biz_name, last_in_text, phone=biz.get("phone") or None
)
```

**(d)** `phone` is optional (defaults to `None`) in all signatures — if `business.phone` is empty or missing, the old copy degrades gracefully (no phone line included). Fully backward-compatible.

### Tests

- `test_reminders.py`: `test_reminder_body_with_phone` — assert phone appears in output.
- `test_reminders.py`: `test_reminder_body_without_phone` — assert no phone line, existing text still correct.
- `test_reminders.py`: `test_followup_body_with_phone` — assert phone in output.
- `test_reminders.py`: `test_followup_body_without_phone` — assert graceful degradation.
- `test_reminders.py`: existing `test_reminder_body` — update assertions for the new wording; verify `when` still appears.
- `test_reminders.py`: `test_enqueue_reminder_includes_phone` — mock `business` with a phone, assert the queued `body` contains the phone string.

**Collision note:** `reminders.py` is shared with workstream 06 (Pricing) and 08 (Retention), which may add new reminder kinds. Adding `phone=None` to `reminder_body` and `followup_body` is backward-compatible (keyword-only default); existing calls without the `phone` arg continue to work. Any test asserting the exact current wording of `reminder_body` will need updating.

### Effort: **S** (2–3 h including tests)

### Risk: Low

Pure function changes. `phone=None` default is backward-compatible. The only risk: any snapshot/golden-string test asserting exact reminder body text will fail and must be updated. Search for `"We look forward to seeing you"` and `"happy to find a time"` in test files before merging.

---

## Collision Summary

| File | Shared with |
|------|-------------|
| `app.py` (`open_conversation`, `_missed_call_textback`) | Workstream 04 (Screening), Workstream 07 (Notifications), Workstream 03 (AI Convo) |
| `ai.py` (`generate_reply`, new `instant_opener`) | Workstream 03 (AI Convo) |
| `alerts.py` (`ALERT_KINDS`, `format_message`) | Workstream 07 (Notifications), Workstream 04 (Screening) |
| `reminders.py` (`reminder_body`, `followup_body`, `enqueue_reminder`) | Workstream 08 (Retention), Workstream 06 (Pricing) |

**Critical coordination point:** If Workstream 07 (Notifications) adds a new alert kind to `ALERT_KINDS`, ensure `"known_caller"` is not independently added — this plan reuses `"lead"` with a `known=True` flag to avoid the tuple change.

If Workstream 04 (Screening) refactors `_missed_call_textback`, the known-caller alert branch (Change 2) must be preserved. Communicate the exact line range (2608–2610) to that workstream.

---

## Ordered Change List (Quick-wins First)

| # | Change | File(s) | Effort | Risk |
|---|--------|---------|--------|------|
| 1 | Fast first text-back: `ai.instant_opener` + branch in `open_conversation` | `ai.py`, `app.py` | S | Low |
| 2 | Reminder copy: add `phone` param, rewrite wording | `reminders.py` | S | Low |
| 3 | Known-caller owner alert: fire `notify_async` in screened-out branch | `app.py`, `alerts.py` | M | Low-Med |

**Total effort:** ~6–9 h across all three changes.

**Biggest risk:** Change 3 touches `alerts.py` (`format_message` and `ALERT_KINDS` logic) which is shared across many notification workstreams. The reuse of the `"lead"` kind with a `known=True` flag is safer than adding a new kind (no tuple change, no new DB column), but it requires coordination with Workstream 07 to avoid conflicting `format_message` edits.
