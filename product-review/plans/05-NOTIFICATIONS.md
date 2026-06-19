# Plan 05 — Owner Notifications / Set-and-Forget
**Workstream:** Owner-facing alerts — alerts.py, reminders.py (scan_stall_nudges, scan_daily_digest, tick_once), db.py (update_alert_prefs, migration block), app.py (/settings save), templates/settings.html.

---

## Change 1 — Owner Quiet Hours (gate non-urgent SMS/email until morning)

### What & Why
`alerts.notify` calls `messaging.send_sms(gate=False)` for every owner alert — bypassing the QUIET_START/QUIET_END backstop that already guards customer texts. A 11 pm lead texts the contractor at 11 pm. Dave the roofer is asleep, wakes up, sees "New lead: a new caller" and can do nothing about it. Do it twice and he turns off all alerts — the set-and-forget promise is gone.

The fix: add `alert_quiet_start` / `alert_quiet_end` columns (INT hours, defaults 22 and 7 — i.e. silence after 10 pm, resume at 7 am) to the businesses table. In `alerts.notify`, after claiming the in-app row (always immediate — never suppressed), check local time against those hours before sending SMS and email. Non-urgent alerts that arrive outside the window write a "held_until_morning" `alert_held` row and are flushed by the `scan_daily_digest` pass at 8 am instead. Urgent kinds bypass the hold entirely.

**CRITICAL CONSTRAINT:** This MUST NOT touch the customer-facing TCPA quiet-hours backstop in `messaging.send_sms` / `reminders.run_due_once`. Those guard outbound texts TO CUSTOMERS. This gate is owner-inbound only and lives in `alerts.notify`, isolated from the customer path.

### Exact File / Function / Approach

**db.py — migration block (~line 840)**
Add after the `alert_on_daily_digest` migration:
```python
# Plan 05-1: owner quiet hours (non-urgent alerts held until morning)
for col, ddl in (
    ("alert_quiet_start", "INTEGER DEFAULT 22"),  # 10 pm local
    ("alert_quiet_end",   "INTEGER DEFAULT 7"),   # 7 am local
):
    if col not in biz_cols:
        c.execute(f"ALTER TABLE businesses ADD COLUMN {col} {ddl}")
```

**db.py — update_alert_prefs (~line 2395)**
Extend `cols` list:
```python
cols = ["alert_email", "alert_sms", "alert_on_lead", "alert_on_booking",
        "alert_on_urgent", "alert_on_daily_digest",
        "alert_on_roi_milestone",          # Plan 05-4
        "alert_quiet_start", "alert_quiet_end"]  # Plan 05-1
```

**alerts.py — new module-level constant**
```python
# Kinds that bypass owner quiet hours (fire-alarm level).
_URGENT_BYPASS_KINDS = frozenset({"urgent", "sms_fail", "forwarding_lost", "tick_stale"})
```

**alerts.py — notify() function, after `attempted.append(("inapp", "recorded"))`**
Insert a quiet-hours gate before the SMS and email sends:
```python
# Owner quiet-hours gate (Plan 05-1).
# Urgent kinds always go through. All others are held outside the owner's window.
# NEVER touches the customer TCPA backstop — that lives in messaging.send_sms.
if kind not in _URGENT_BYPASS_KINDS:
    tz = _biz_tz_for_alerts(business)   # see helper below
    local_h = datetime.now(tz).hour
    q_start = _int_pref(business, "alert_quiet_start", 22)
    q_end   = _int_pref(business, "alert_quiet_end",   7)
    in_quiet = (q_start > q_end                     # wraps midnight (22..7)
                and (local_h >= q_start or local_h < q_end)
               ) or (q_start <= q_end               # same-day window (e.g. 2..6)
                and q_start <= local_h < q_end)
    if in_quiet:
        # In-app row already recorded above; SMS/email deferred to morning digest.
        # Record a "held" marker so scan_daily_digest can surface it.
        db.add_alert(bid, kind, "sms_held", sms_to or "", "held_quiet", dedupe, body)
        return attempted   # skip the SMS and email sends below
```

Add two small pure helpers to alerts.py:
```python
def _biz_tz_for_alerts(business):
    """Resolve business dict to tzinfo. Lazy-imports config.biz_tz (avoids circular
    import at module level). Falls back to UTC so a missing tz is safe."""
    try:
        from config import biz_tz as _biz_tz
        return _biz_tz(business)
    except Exception:
        from datetime import timezone
        return timezone.utc

def _int_pref(business, key, default):
    try:
        return int((business or {}).get(key) or default)
    except (TypeError, ValueError):
        return default
```

**app.py — /settings POST handler (~line 1135)**
Extend the `update_alert_prefs` call to save quiet hours:
```python
db.update_alert_prefs(biz["id"], {
    ...existing fields...,
    "alert_quiet_start": int(request.form.get("alert_quiet_start") or 22),
    "alert_quiet_end":   int(request.form.get("alert_quiet_end")   or 7),
})
```

**templates/settings.html — Owner Alerts card**
Add two time-select dropdowns (0–23) labeled "Quiet from" / "Until" with defaults 22 / 7. Note "Urgent alerts (missed calls, delivery failures) always go through."

### Tests (standalone)
- `test_quiet_hours_holds_lead_alert`: call `alerts.notify(biz, "lead", ctx)` with `alert_quiet_start=22`, `alert_quiet_end=7`, mock local hour = 23 → assert SMS not sent, in-app row recorded, `sms_held` row written.
- `test_quiet_hours_passes_urgent`: same setup, kind = `"urgent"` → assert SMS sent (gate=False path reached).
- `test_quiet_hours_allows_daytime`: mock hour = 14 → lead alert SMS goes through.
- `test_quiet_hours_boundary`: mock hour = 7 (exactly `q_end`) → goes through (window is exclusive end).
- `test_quiet_hours_same_day_window`: `q_start=2, q_end=6`, hour = 3 → held.
- `test_int_pref_fallback`: `_int_pref({}, "alert_quiet_start", 22)` → 22.

### Effort: S

### Risk & Collisions
- **alerts.py is touched by every other workstream** (booking alerts, screening alerts, ROI milestone, etc.). The quiet-hours block is inserted as a single early-return after the in-app claim, affecting ONLY the SMS/email sends. It is additive — no existing logic is modified.
- `messaging.send_sms` customer TCPA path is NOT touched. Confirm with a grep before shipping: `grep -n "gate=False" reminders.py` must show zero new hits from this change.
- `_biz_tz_for_alerts` mirrors the pattern already used in `reminders._biz_tz` — same lazy-import, same fallback.
- Migration uses the same `ALTER TABLE ... ADD COLUMN IF NOT EXIST` guard pattern already in db.py (~line 840).

---

## Change 2 — Stall-Nudge Daily Cap (max N SMS per business per afternoon)

### What & Why
`scan_stall_nudges` iterates ALL idle leads for a business with no aggregate cap. Five stalled leads = five texts in one afternoon pass. The per-(lead, local-day) dedupe stops re-sends within the same lead, but does nothing about volume across leads. The owner sees a pile of "Maria 31h… Carlos 27h… Jim 25h" and stops reading. The one that matters is buried.

Cap at `max_stall_alerts_day` (default 2) per business per afternoon. Order leads by `idle_hours` DESC so the longest-waiting lead always goes first. The rest are surfaced in the 8 am digest's `top_stall` slot (already populated by `scan_daily_digest` from the same `warm_leads_idle` query).

### Exact File / Function / Approach

**db.py — migration block**
```python
if "max_stall_alerts_day" not in biz_cols:
    c.execute("ALTER TABLE businesses ADD COLUMN max_stall_alerts_day INTEGER DEFAULT 2")
```

**db.py — update_alert_prefs**
Add `"max_stall_alerts_day"` to the `cols` list.

**reminders.py — scan_stall_nudges (~line 615)**
Replace the loop body:
```python
idle_leads = db.warm_leads_idle(biz["id"], 24)
# Sort by most-idle first so the cap keeps the most urgent leads.
idle_leads.sort(key=lambda r: r.get("idle_hours", 0) or 0, reverse=True)
cap = _int_pref(biz, "max_stall_alerts_day", 2)  # import _int_pref from alerts or re-define
nudged_this_pass = 0
for lead in idle_leads:
    if nudged_this_pass >= cap:
        break
    ...existing per-lead try/except...
    result = alerts.notify(biz, "vic_stall", ctx)
    if result:
        fired += 1
        nudged_this_pass += 1
```

Add `_int_pref` to `reminders.py` (tiny pure helper, already defined in alerts.py — can either import or duplicate the two-liner; prefer duplicate to avoid circular import risk).

**app.py — /settings POST handler**
```python
db.update_alert_prefs(biz["id"], {
    ...existing...,
    "max_stall_alerts_day": max(0, min(10, int(request.form.get("max_stall_alerts_day") or 2))),
})
```

**templates/settings.html**
Add a small numeric input (1–5) or a simple select (1, 2, 3, 5) labeled "Max stall nudges per day" in the Alerts card.

### Tests (standalone)
- `test_stall_cap_limits_sends`: 5 idle leads, cap=2 → `scan_stall_nudges` fires exactly 2 alerts.notify calls.
- `test_stall_cap_most_idle_first`: cap=1 → the lead with highest `idle_hours` is the one notified.
- `test_stall_cap_zero`: cap=0 → no nudges (edge case for "mute stall texts" preference).
- `test_stall_cap_default_two`: `max_stall_alerts_day` absent from biz dict → defaults to 2.
- `test_stall_per_lead_dedupe_still_works`: same lead in two consecutive passes → each pass respects the per-(lead, day) dedupe independent of the cap.

### Effort: S

### Risk & Collisions
- `scan_stall_nudges` is called only from `tick_once` (~line 918 reminders.py). No other workstream calls it directly.
- `warm_leads_idle` is also called by `scan_daily_digest`. The sort added here is local — `scan_daily_digest` already sorts its own copy (`stalls.sort(...)` at line ~723). No interference.
- The per-(lead, local-day) dedupe key in `alerts._dedupe_key` is untouched.
- If another workstream adds a `max_stall_alerts_day` column by a different name, there will be a collision — the column name is documented here explicitly.

---

## Change 3 — "All Clear" Daily Digest (system-is-working reassurance)

### What & Why
When `scan_daily_digest` finds nothing to report (n_leads == 0, plays_count == 0, no top_stall), it `continue`s — the owner receives no morning text. This is indistinguishable from: cron broken, Twilio down, number not set up. The set-and-forget promise requires trust, and trust requires confirmation. Dave the non-tech contractor calls support after 3 quiet mornings, thinking the product is broken.

Add an `alert_all_clear` toggle (default OFF — opt-in only, to avoid SMS fatigue on genuinely busy owners who don't need it). When ON, the quiet-morning branch sends a brief reassurance: "Good morning. Quiet day — no leads waiting, nothing to approve. FirstBack is running." This fires through the same `daily_digest` dedupe key so it is still exactly one morning text.

### Exact File / Function / Approach

**db.py — migration block**
```python
if "alert_all_clear" not in biz_cols:
    c.execute("ALTER TABLE businesses ADD COLUMN alert_all_clear INTEGER DEFAULT 0")
```

**db.py — update_alert_prefs**
Add `"alert_all_clear"` to the `cols` list.

**reminders.py — scan_daily_digest (~line 733)**
Replace the `continue` in the nothing-to-report branch:
```python
if n_leads == 0 and plays_count == 0 and not top_stall_name:
    # All-clear reassurance (opt-in per business).
    if biz.get("alert_all_clear"):
        ctx = {
            "n_leads": 0, "money": "", "is_estimated": False,
            "plays_count": 0, "plays_summary": "",
            "top_stall_name": "", "top_stall_hours": 0,
            "local_day": local_day,
            "all_clear": True,   # flag for format_message
        }
        result = alerts.notify(biz, "daily_digest", ctx)
        if result:
            fired += 1
    continue
```

**alerts.py — format_message, `daily_digest` branch (~line 161)**
At the top of the `daily_digest` branch, add:
```python
if context.get("all_clear"):
    return "Good morning. Quiet day — no leads waiting, nothing to approve. FirstBack is running."
```

**app.py — /settings POST handler**
```python
"alert_all_clear": 1 if request.form.get("alert_all_clear") else 0,
```

**templates/settings.html**
Add a checkbox labeled "Send a 'quiet day' message when there's nothing to act on" under the daily digest toggle.

### Tests (standalone)
- `test_all_clear_fires_when_opted_in`: `biz["alert_all_clear"]=1`, no leads/plays/stalls → `scan_daily_digest` fires exactly one `daily_digest` alert.
- `test_all_clear_silent_when_opted_out`: `biz["alert_all_clear"]=0` (default) → no alert fired on quiet day.
- `test_all_clear_copy`: `alerts.format_message("daily_digest", {"all_clear": True})` returns the reassurance string.
- `test_all_clear_deduped`: opt-in, second pass same day → dedupe prevents a second text.
- `test_all_clear_does_not_fire_when_active_leads`: `alert_all_clear=1` but n_leads=1 → normal digest fires (not the all-clear variant).

### Effort: S

### Risk & Collisions
- Only `scan_daily_digest` is modified (the quiet-day `continue` branch). The active-day path is untouched.
- `format_message` is pure and unit-tested — the `all_clear` flag check is additive at the top of the `daily_digest` branch.
- The `daily_digest` dedupe key (`daily_digest:{day}`) already prevents double-sends regardless of which variant fires.

---

## Change 4 — ROI Milestone Toggle Exposed in Settings UI

### What & Why
`alert_on_roi_milestone` is a DB column (added ~line 844), mapped in `alerts._TOGGLE_COL`, but absent from the Settings UI and from the `update_alert_prefs` whitelist. The owner cannot turn it off, and even if they could, the form POST would silently drop it. The ROI milestone is the highest-dopamine moment in the product — but if it fires erroneously or repeatedly, the owner has no lever.

### Exact File / Function / Approach

**db.py — update_alert_prefs (~line 2398)**
`alert_on_roi_milestone` is already handled in Change 1 (added to `cols` list there). Confirm it is present.

**app.py — /settings POST handler (~line 1135)**
Add to the `update_alert_prefs` call:
```python
"alert_on_roi_milestone": 1 if request.form.get("alert_on_roi_milestone") else 0,
```

Also add to the `db.update_alert_prefs` call in the `/signup` handler (~line 334):
```python
"alert_on_roi_milestone": 1,   # default ON at signup
```

**templates/settings.html — Owner Alerts card**
Add a checkbox: "Notify me when FirstBack pays for itself" (default checked). Position below the `alert_on_urgent` toggle and above the digest toggle.

### Tests (standalone)
- `test_roi_milestone_toggle_saved`: POST settings with `alert_on_roi_milestone=0` → `biz["alert_on_roi_milestone"]` reads 0 from DB after update.
- `test_roi_milestone_toggle_prevents_alert`: `biz["alert_on_roi_milestone"]=0` → `alerts._enabled_for(biz, "roi_milestone")` returns False.
- `test_roi_milestone_default_on_signup`: fresh business via signup path → `biz["alert_on_roi_milestone"]` == 1.

### Effort: XS (two-liner fix across three files)

### Risk & Collisions
- `_TOGGLE_COL` mapping in alerts.py already exists (`"roi_milestone": "alert_on_roi_milestone"`) — no change needed there.
- `update_alert_prefs` whitelist change is consolidated with Change 1 — handled in a single edit to `cols`.

---

## Change 5 — Webhook Channel Field in Settings (Slack/Teams/Zapier)

### What & Why
SMS and email are the only owner channels. Both require external service configuration. Power users (many contractors use a shared Slack or a team channel) want alerts piped to a webhook URL with a single paste. The minimal version: a `alert_webhook_url` text field in Settings. On each `alerts.notify` call (after in-app, after SMS, after email), if the URL is set, POST a JSON payload to it. No signature, no retry, fire-and-forget — the same philosophy as the existing email path.

### Exact File / Function / Approach

**db.py — migration block**
```python
if "alert_webhook_url" not in biz_cols:
    c.execute("ALTER TABLE businesses ADD COLUMN alert_webhook_url TEXT")
```

**db.py — update_alert_prefs**
Add `"alert_webhook_url"` to `cols`.

**alerts.py — notify() function, at the end (after email send)**
```python
webhook_url = (business.get("alert_webhook_url") or "").strip()
if webhook_url:
    _send_webhook(webhook_url, bid, kind, body, context)
    attempted.append(("webhook", "sent"))
```

Add a new function (pure network call, no DB side-effect):
```python
def _send_webhook(url, business_id, kind, body, context):
    """POST a JSON alert payload to the owner's webhook URL (Slack/Teams/Zapier).
    Fire-and-forget: failures are logged but never crash the alert fan-out."""
    try:
        import urllib.request, json as _json
        payload = {
            "business_id": business_id,
            "kind": kind,
            "body": body,
            "context": {k: v for k, v in (context or {}).items()
                        if isinstance(v, (str, int, float, bool, type(None)))},
        }
        data = _json.dumps(payload).encode()
        req = urllib.request.Request(url, data=data,
                                     headers={"Content-Type": "application/json"},
                                     method="POST")
        with urllib.request.urlopen(req, timeout=5) as resp:
            _ = resp.read()
    except Exception as e:
        import sys
        print(f"[firstback] webhook alert failed ({url[:40]}): {e}",
              file=sys.stderr, flush=True)
```

Uses only stdlib (`urllib.request`) — no new dependency. 5-second timeout. Context is sanitized to scalar-safe values before serializing.

**app.py — /settings POST handler**
```python
"alert_webhook_url": request.form.get("alert_webhook_url", "").strip(),
```

**templates/settings.html — Owner Alerts card**
Add a text input: "Webhook URL (Slack, Teams, Zapier)" with a placeholder and a link to a help doc.

### Tests (standalone)
- `test_webhook_posts_on_alert`: mock `urllib.request.urlopen`; fire `alerts.notify` with `alert_webhook_url` set → confirm POST called with correct JSON body including `kind` and `body`.
- `test_webhook_skipped_when_url_empty`: `alert_webhook_url = ""` → `urlopen` never called.
- `test_webhook_failure_does_not_raise`: `urlopen` raises `OSError` → `notify` returns normally, `attempted` does not include webhook entry.
- `test_webhook_context_sanitized`: context with a non-serializable value → JSON still encodes (sanitizer strips it).

### Effort: S

### Risk & Collisions
- `alerts.notify` is modified to add a fourth channel after the email block. The existing SMS and email paths are untouched. The webhook call is synchronous inside `notify` (which is already called from a daemon thread via `notify_async`) — the 5-second timeout is acceptable in that context.
- No new pip dependency — `urllib.request` is stdlib.
- The quiet-hours gate (Change 1) applies BEFORE the webhook send: if the owner is in quiet hours, the webhook is also held (it shares the same early-return). This is the correct behavior for a Slack integration (no 11 pm Slack pings).
- **Collision flag:** any workstream that adds a new channel to `alerts.notify` must be coordinated. The webhook block is appended last and is self-contained.

---

## Change 6 — Fix tick_stale Hardcoded to Business id=1

### What & Why
`tick_once` at reminders.py line 882 calls `db.get_business(1)` — hardcoded. In a multi-tenant future, every tenant except the first misses the scheduler-stale alert. A five-line fix.

### Exact File / Function / Approach

**reminders.py — tick_once stale-ticker block (~line 876)**
Replace:
```python
alerts.notify(db.get_business(1), "tick_stale", {...})
```
With:
```python
for _biz in db.list_businesses():
    alerts.notify(_biz, "tick_stale", {
        "gap_minutes": round(_gap_s / 60, 1),
        "local_day": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
    })
```

Alternatively, if `tick_stale` is considered a platform-ops alert (not per-tenant), change it to use a hardcoded ops recipient env var (`FIRSTBACK_OPS_BIZ_ID`) rather than tenant-id 1. The cleaner path for a product positioning as multi-tenant is to fan it to all businesses (each business's owner should know if their scheduler is down).

### Tests (standalone)
- `test_tick_stale_fans_to_all_businesses`: two businesses in DB, gap > 900s → `alerts.notify` called twice (once per business).
- `test_tick_stale_skipped_when_gap_small`: gap < 900s → `alerts.notify` not called.

### Effort: XS

### Risk & Collisions
- `tick_once` is called only from `start_ticker` and `POST /tasks/run-due`. No other workstream calls it.
- The `_DAILY_DEDUPE_SECONDS` window (26h) on `tick_stale` dedupe keys prevents an alert storm even if this loop runs across multiple businesses.

---

## Collision Map — Functions Touched by Other Workstreams

| File | Function | This Plan's Change | Risk |
|---|---|---|---|
| `alerts.py` | `notify()` | Quiet-hours gate (C1), webhook channel (C5) | HIGH — every workstream calls notify_async; gate is isolated early-return; test carefully |
| `alerts.py` | `format_message()` | all_clear flag in daily_digest branch (C3) | LOW — additive; pure function |
| `alerts.py` | `_TOGGLE_COL` | No change — roi_milestone already present | NONE |
| `reminders.py` | `scan_stall_nudges()` | Cap + sort (C2) | LOW — only called from tick_once |
| `reminders.py` | `scan_daily_digest()` | all_clear branch (C3) | LOW — only called from tick_once |
| `reminders.py` | `tick_once()` | tick_stale fan-out (C6) | LOW — isolated block |
| `db.py` | `update_alert_prefs()` | Extend cols list (C1+C4+C5) | MEDIUM — if another workstream also extends this list, merge carefully |
| `db.py` | migration block | 5 new ALTER TABLE columns | LOW — guard pattern matches existing code; columns are independent |
| `app.py` | `/settings` POST | Save new prefs (C1+C2+C3+C4+C5) | MEDIUM — settings save is a hot spot; consolidate all changes into one edit |
| `templates/settings.html` | Alerts card | 4 new inputs (C1+C2+C3+C5) | LOW — additive HTML |

---

## Implementation Order (Quick-Wins First)

| # | Change | Files | Effort |
|---|---|---|---|
| 1 | ROI milestone toggle exposed | db.py, app.py, settings.html | XS |
| 2 | tick_stale fan-out fix | reminders.py | XS |
| 3 | Stall-nudge daily cap | db.py, reminders.py, app.py, settings.html | S |
| 4 | All-clear daily digest | db.py, alerts.py, reminders.py, app.py, settings.html | S |
| 5 | Owner quiet hours | db.py, alerts.py, app.py, settings.html | S |
| 6 | Webhook channel field | db.py, alerts.py, app.py, settings.html | S |

Total: 2×XS + 4×S = ~1–1.5 dev days end-to-end with tests.

---

## Biggest Risk

**Change 1 (quiet hours) modifies `alerts.notify` — the most-called function in the system.** Every other workstream routes owner alerts through it. The gate must be inserted AFTER the in-app claim (so the audit trail is always complete) and BEFORE the SMS/email sends (so the hold is effective). The key invariant to test: `notify` must always return `[("inapp", "recorded")]` even when the quiet-hours gate fires, and `_safe_notify` must swallow all exceptions. The TCPA customer-text path in `messaging.send_sms` must show zero new `gate=False` hits from this change.
