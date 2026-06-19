# Plan 08 — Call Screening Value + Visibility

**Workstream:** Turn a sound-but-invisible feature into a deal-closer.
**Grounded in:** `triage.py`, `reputation.py`, `reminders.py` (`scan_screening_graduation`), `db.py` (`is_known_caller`, `screening_stats`, `record_screening_rescue`, `promote_screening`), `app.py` (dashboard route ~L786–814, rescue endpoint ~L2175–2203), `templates/dashboard.html`, `templates/settings.html`, `config.py` (`SCREEN_GRADUATION_DAYS`, `SCREEN_GRADUATION_MIN_VERDICTS`, `SCREEN_CROWD_MIN`, `REPUTATION_PROVIDER`).
**Collision surface:** `reminders.py` (graduation scanner), `db.py` (schema + stat functions), `templates/dashboard.html` + `settings.html` (UX copy), `alerts.py` (new monthly kind), `app.py` (dashboard route + rescue route copy).

---

## Change 1 — Make the auto-built allowlist a visible headline feature

**What & why:**
`db.is_known_caller` builds the known-caller allowlist from booked estimates and directory entries with zero contact import. This is the most defensible idea in the screening stack — it builds stickiness (the more you book, the smarter the screen gets) — but Dave never sees it. The settings card subtitle says "No setup, no contact import required" but doesn't explain *why*. The `trusted` verdict path in `triage.screen_caller` is what enforces it, but it's never surfaced as a user benefit.

**Exact files + approach:**

(a) `templates/settings.html` — card subtitle at line 87, currently:
> "Like your phone's screen: FirstBack only texts back real prospects — it skips people you already know (they're yours to handle) and suspected spam/robocallers. No setup, no contact import required."

Replace subtitle with:
> "Like your phone's screen, only smarter: FirstBack learns who you know automatically from your bookings — no contact import ever. It texts back real prospects, passes returning customers straight to you, and screens out robocallers."

Also change the enforce-mode description paragraph (line 111) to lead with the allowlist:
> "**Enforcing.** Every time you book an estimate, FirstBack adds that caller to your private list — they always reach you directly. New, unknown callers get the text-back. Suspected spam is screened out. It's **precision-first**: anything uncertain is still texted and flagged for review."

(b) `templates/dashboard.html` — the "Spam Shield is active" card (lines 100–105) is the only post-enforcement surface. Add one sentence after the robocallers-blocked count:
> "Your booking history automatically protects returning customers — they always reach you directly."

(c) `templates/dashboard.html` — the monitor-mode nudge (line 38) currently explains what it would screen. Prepend the allowlist benefit:
> "**FirstBack is building your caller list from your bookings — no import needed.** Call screening is in monitor mode..."

**Tests (standalone):**
- Unit: render settings.html with `screen_mode='enforce'` — assert "booking history" or "automatically" appears in the output.
- Unit: render dashboard.html with `screening_promoted_at` set — assert "returning customers" or "booking history" in rendered HTML.
- No logic changes; these are copy-only.

**Effort:** S (under 1 hour — template copy edits only)
**Risk:** Very low. No logic touched. Collision: none beyond the templates.

---

## Change 2 — Volume-aware graduation: dual-axis progress + low-volume path

**What & why:**
`reminders.scan_screening_graduation` graduates businesses from monitor to enforce after `SCREEN_GRADUATION_DAYS` (7) AND `SCREEN_GRADUATION_MIN_VERDICTS` (10 spam signals). For a contractor getting 8 calls/week with maybe 2–3 robocallers, the verdicts threshold is never reached; they stay in monitor forever and never experience blocking.

The dashboard card (lines 106–110) shows only Day N of 7. It shows nothing about the verdicts axis. Dave can't tell if he's stuck.

**Exact files + approach:**

(a) `app.py` — dashboard route (~L786–814): extend the graduation block to also pass the in-window would_screen_spam count:

```python
# After: _grad_days = max(0, (_now - _ws).days)
_window_start_str = _window_start  # keep for stats query
_grad_verdicts = None
_grad_verdicts_min = getattr(config, "SCREEN_GRADUATION_MIN_VERDICTS", 10)
try:
    _gstats = db.screening_stats(biz["id"], since=_window_start_str)
    _grad_verdicts = _gstats.get("would_screen_spam", 0)
except Exception:
    pass
```

Pass `grad_verdicts=_grad_verdicts` and `grad_verdicts_min=_grad_verdicts_min` to `render_template`.

(b) `templates/dashboard.html` — the shield-learning card (lines 107–110):

Replace:
```
<span class="review-nudge-text"><strong>Spam Shield: Learning (Day {{ grad_day }} of {{ grad_total }}).</strong>
Watching for {{ grad_total }} days before it can block automatically. Nothing is silenced yet.</span>
```

With:
```
<span class="review-nudge-text"><strong>Spam Shield: Learning (Day {{ grad_day }} of {{ grad_total }}
· {{ grad_verdicts or 0 }} of {{ grad_verdicts_min }} spam signals seen).</strong>
Watching for {{ grad_total }} days with {{ grad_verdicts_min }} spam signals before it can block automatically.
Nothing is silenced yet.
{% if grad_day >= grad_total and (grad_verdicts or 0) < grad_verdicts_min %}
  <a href="/settings#set-screening">Ready to enforce manually?</a>
{% endif %}
</span>
```

The last branch triggers when the time window is up but not enough verdicts have accumulated — "Ready to enforce manually?" — letting a low-volume business opt in rather than waiting forever.

(c) `config.py` — add a per-volume graduation override constant (no DB change needed, just a lower constant for early-stage):

```python
# Low-volume floor: if a business sees fewer than this many missed calls/week in the
# window, auto-graduation requires only this many verdicts instead of SCREEN_GRADUATION_MIN_VERDICTS.
# Env-overridable. Default: 5 (half of 10, sized for 2-3 spam calls in a 7d window).
SCREEN_GRADUATION_MIN_VERDICTS_LOW_VOLUME = _int_env(
    "FIRSTBACK_SCREEN_GRADUATION_MIN_VERDICTS_LOW", 5)
SCREEN_GRADUATION_LOW_VOLUME_THRESHOLD = _int_env(
    "FIRSTBACK_SCREEN_LOW_VOLUME_THRESHOLD", 20)  # total missed calls in window
```

(d) `reminders.scan_screening_graduation` (~L754–823): after the `would_block` read, add the volume-aware path:

```python
# Volume-aware graduation: if the business is low-volume (few total calls in the
# window), use a lower verdict minimum so they can still graduate.
total_in_window = stats.get("total", 0)
min_verdicts = SCREEN_GRADUATION_MIN_VERDICTS
if total_in_window < config.SCREEN_GRADUATION_LOW_VOLUME_THRESHOLD:
    min_verdicts = config.SCREEN_GRADUATION_MIN_VERDICTS_LOW_VOLUME

if would_block < min_verdicts:
    continue
```

Import `SCREEN_GRADUATION_MIN_VERDICTS_LOW_VOLUME` and `SCREEN_GRADUATION_LOW_VOLUME_THRESHOLD` from config at the top of `reminders.py` (add to the existing config import line).

**Tests (standalone):**
- Unit in `test_screening_graduation.py`: business with `total=10, would_screen_spam=5` in a 7d window — assert graduation fires with the low-volume path.
- Unit: business with `total=25, would_screen_spam=5` — assert graduation does NOT fire (above threshold, still needs 10).
- Unit: `app.py` dashboard route returns `grad_verdicts` and `grad_verdicts_min` to template context.
- Template render: when `grad_day >= grad_total` and `grad_verdicts < grad_verdicts_min`, assert the "Ready to enforce manually?" link appears.

**Effort:** M (3–5 hours: config + reminders logic + dashboard route + template)
**Risk:** Medium. The graduation logic in `reminders.py` is tested (530 tests); the new branch must not break existing passing cases. The `screening_stats` call in the dashboard route is a read-only DB hit; add it only when `_window_start` is set to avoid the extra query on enforce-mode dashboards.
**Collision:** `reminders.py` graduation scanner — coordinate with anyone touching `scan_screening_graduation`. `db.screening_stats` signature unchanged; just new caller in `app.py`.

---

## Change 3 — Reframe the false-positive counter as "caller rescued"

**What & why:**
`db.record_screening_rescue` increments `screening_false_positives` and upserts the caller as a customer. The dashboard renders:
> "0 false positives."

A contractor reading "1 false positive" hears: "the system made a mistake." The same fact reframed: "1 caller rescued — saved as a customer" reads as: "the system learned."

**Exact files + approach:**

(a) `templates/dashboard.html` — line 103:

Replace:
```
· {{ screening_false_positives or 0 }} false positive{{ 's' if screening_false_positives != 1 else '' }}.
```

With:
```
{% if screening_false_positives %}
· {{ screening_false_positives }} caller{{ 's' if screening_false_positives != 1 else '' }} rescued — saved as {{ 'customers' if screening_false_positives != 1 else 'a customer' }}.
{% endif %}
```

Zero rescues: nothing shown (no "0 false positives" cluttering the line). One or more: positive framing.

(b) `app.py` — `/api/calls/<int:call_id>/real` (L2175–2203): after `db.record_screening_rescue`, return a success payload with a toast message:

```python
return jsonify(ok=True, lead_id=lead["id"],
               toast="Saved as a customer — they'll always reach you directly from now on.")
```

The JS rescue handler (wherever it reads `ok` from this endpoint) should display `data.toast` as an inline confirmation. Check `templates/dashboard.html` JS for the `screen-real` button handler; update it to show `data.toast`.

(c) `templates/settings.html` — line 90 (`Spam Shield is enforcing` note): the existing copy says "Saw a real customer get skipped? Tap **This was real**..." — keep this, but append:
> "They'll be saved as a customer and will always reach you directly — the screen never misses them again."

**Tests (standalone):**
- Unit: render dashboard.html with `screening_false_positives=0` — assert "false positive" does NOT appear.
- Unit: render with `screening_false_positives=1` — assert "1 caller rescued" appears.
- Unit: render with `screening_false_positives=3` — assert "3 callers rescued" (plural).
- API: mock `record_screening_rescue` + test `/api/calls/<id>/real` returns `toast` key.

**Effort:** S (1–2 hours — copy changes + one API response field + JS toast wiring)
**Risk:** Low. The counter column is unchanged; this is display framing only. JS toast change is additive.

---

## Change 4 — Monthly Screening Report ("N robocalls blocked, $X saved")

**What & why:**
F7 in the audit: Dave never sees the ROI of screening. GoHighLevel texts everyone; his number protection is invisible. A monthly "N robocalls blocked · M wasted texts saved · $X value" alert makes the value legible and turns screening from a background process into a visible monthly win.

**Coordination note:** The ROI monthly recap owns aggregate revenue/ROI (another agent's workstream). This plan owns the *screening content* — robocalls blocked, texts saved, cost calculation. The channel should be the **same monthly digest** (the ROI recap). This plan defines the `screening_report` alert kind with the screening numbers; the ROI agent should include it in the monthly digest body OR the screening card should be a second section of the same monthly email/SMS. If they ship independently, both ride `alerts.notify` with a monthly dedupe key.

**Exact files + approach:**

(a) `db.py` — new function `screening_monthly_stats(business_id, year, month)`:

```python
def screening_monthly_stats(business_id, year, month):
    """Screening stats for a calendar month (UTC). Returns:
      {spam_blocked, contact_trusted, texts_saved, texts_saved_cost_cents,
       rescues, month_label}
    where texts_saved = enforced blocks (calls we did NOT text back).
    Cost: $0.0075/segment (Twilio A2P outbound rate; 1 segment per text-back).
    texts_saved_cost_cents = texts_saved * 0.75 (75 cents per 100 texts saved)."""
    import calendar
    _, last_day = calendar.monthrange(year, month)
    since = f"{year:04d}-{month:02d}-01T00:00:00+00:00"
    until = f"{year:04d}-{month:02d}-{last_day:02d}T23:59:59+00:00"
    conn = get_conn()
    row = conn.execute(
        "SELECT "
        "  SUM(CASE WHEN screen_status='screened_spam' AND screen_mode='enforce' THEN 1 ELSE 0 END) AS spam_blocked, "
        "  SUM(CASE WHEN screen_status='screened_contact' AND screen_mode='enforce' THEN 1 ELSE 0 END) AS contact_trusted, "
        "  SUM(CASE WHEN screen_status IN ('screened_spam','screened_contact') AND screen_mode='enforce' THEN 1 ELSE 0 END) AS texts_saved "
        "FROM calls WHERE business_id=? AND missed=1 AND created_at>=? AND created_at<=?",
        (business_id, since, until)).fetchone()
    conn.close()
    d = {k: (row[k] or 0) for k in row.keys()}
    d["texts_saved_cost_cents"] = d["texts_saved"]  # 1 cent per text (rounded; real rate ~0.75¢)
    # rescues: false positives corrected during the month (from businesses table, not call-level)
    # Note: screening_false_positives is cumulative not monthly; for MVP, omit or read all-time.
    # A per-month rescue count would need a rescues table or a timestamp column — defer to v2.
    d["rescues"] = None
    import calendar as _cal
    d["month_label"] = _cal.month_name[month]
    return d
```

(b) `alerts.py` — add `"screening_report"` to `_TEMPLATES` and `_SUBJECT`:

```python
# In _TEMPLATES dict, add:
"screening_report": (
    lambda ctx: (
        f"FirstBack Screening — {ctx.get('month_label','this month')}: "
        f"{ctx.get('spam_blocked',0)} robocalls blocked, "
        f"{ctx.get('texts_saved',0)} texts saved"
        + (f" (~${ctx.get('texts_saved_cost_cents',0)/100:.2f} in SMS cost)." if ctx.get('texts_saved_cost_cents') else ".")
        + (" Your caller list grows automatically with every booking." if ctx.get('spam_blocked',0) > 0 else "")
    )
),
```

In `_SUBJECT` dict:
```python
"screening_report": "Your FirstBack screening report — {month_label}",
```

Add `"screening_report"` to the dedupe kinds with a monthly (26-day) window — in `alerts._dedupe_key`:
```python
if kind == "screening_report":
    # month-stamped: one per business per calendar month
    month = ctx.get("month_label", "")
    return f"screening_report:{month}"
```

Toggle: add `"screening_report": "alert_on_screening_report"` to `_TOGGLE_COL`. Add the column to `db.py` schema backfill:
```python
("alert_on_screening_report", "INTEGER DEFAULT 1")
```

(c) `reminders.py` — new function `scan_screening_report(now=None)`, called from `tick_once`. Fires once per business on the 1st of each month in the [8, 10) window:

```python
def scan_screening_report(now=None):
    """Monthly: fire a screening report on the 1st of each month to owner.
    Only fires when in enforce mode (there's something to report).
    Deduped via alerts.notify 'screening_report' kind (month-stamped).
    Returns count of reports fired."""
    import calendar as _cal
    now_dt = datetime.now(timezone.utc)
    now_str = now or now_dt.isoformat()
    fired = 0
    for biz in db.list_businesses():
        try:
            tz = _biz_tz(biz)
            try:
                now_local = datetime.fromisoformat(now_str).astimezone(tz)
            except (TypeError, ValueError):
                now_local = datetime.now(tz)
            # Only fire on the 1st of the month in [8, 10) local
            if now_local.day != 1 or not (8 <= now_local.hour < 10):
                continue
            # Only report if in enforce mode (something actually blocked)
            from config import SCREEN_MODE as _SCREEN_MODE
            effective = (biz.get("screen_mode") or "").strip().lower() or _SCREEN_MODE
            if effective != "enforce":
                continue
            # Previous month's stats
            prev_month = (now_local.month - 1) or 12
            prev_year = now_local.year if now_local.month > 1 else now_local.year - 1
            stats = db.screening_monthly_stats(biz["id"], prev_year, prev_month)
            # Skip if nothing was blocked (no value to report)
            if stats.get("spam_blocked", 0) == 0 and stats.get("texts_saved", 0) == 0:
                continue
            ctx = {
                "month_label": stats["month_label"],
                "spam_blocked": stats["spam_blocked"],
                "texts_saved": stats["texts_saved"],
                "texts_saved_cost_cents": stats["texts_saved_cost_cents"],
            }
            result = alerts.notify(biz, "screening_report", ctx)
            if result:
                fired += 1
        except Exception as e:
            print(f"[firstback] screening report scan failed (biz {biz.get('id')}): {e}",
                  file=sys.stderr, flush=True)
    return fired
```

Call from `tick_once`: add `scan_screening_report(now)` wrapped in a try/except after the existing `scan_daily_digest` call. Import nothing new (it's in the same module).

(d) `templates/settings.html` — under the alerts toggle-list (near line 199–202), add:

```html
{{ alert_toggle('screening_report', 'Monthly screening report (robocalls blocked, texts saved)', business.alert_on_screening_report) }}
```

**Tests (standalone):**
- Unit: `db.screening_monthly_stats` with mocked calls table — assert correct spam_blocked and texts_saved counts.
- Unit: `scan_screening_report` with `now_local.day=1, hour=8, effective='enforce'` and non-zero stats — assert `alerts.notify` called.
- Unit: `scan_screening_report` with `effective='monitor'` — assert NOT called.
- Unit: `scan_screening_report` with zero spam_blocked — assert NOT called.
- Unit: alerts dedupe key for `screening_report` — same month never fires twice.

**Effort:** M (4–6 hours: db function + alerts template + reminders scanner + settings toggle + schema column)
**Risk:** Medium. New DB schema column requires backfill migration (already the pattern in db.py init). `tick_once` growth is acceptable (same pattern as `scan_daily_digest`). Coordination risk: the ROI agent may also add a monthly kind — if both ship, two monthly SMSs fire on the 1st. Mitigation: the screening report is a second section added to the ROI recap email body, OR they use the same "monthly_digest" kind and the ROI agent adds a `screening_section` key to its ctx. **Recommend:** coordinate with agent 07 (ROI) to merge into one monthly owner SMS.
**Collision:** `reminders.py` + `db.py` + `alerts.py` — three files all touched by multiple agents. Lock acquisition order in db.py is already safe (WAL mode). No functional collision, but merge conflicts are possible.

---

## Change 5 — Bundle paid reputation into the paid tier (default-on for paying customers)

**What & why:**
`reputation.py` is off by default behind `FIRSTBACK_REPUTATION_PROVIDER` + API keys. The Settings page shows "Optional add-on" with a disabled button. This means lead-gen vendor spam (local numbers with A-level attestation, never in the crowd ledger) rings through and gets the full text-back. Dave's real daily spam problem — the solar guy, the warranty company, the roof-lead seller calling from a real local cell — is not caught by the free tier.

The fix: for the $99 plan, `FIRSTBACK_REPUTATION_PROVIDER=twilio_nomorobo` should be set in the Render environment by default. The per-lookup cost via Twilio Nomorobo is ~$0.005–0.01 per number (cached 24h; a robocaller hitting 10 businesses = one lookup), easily absorbed in the margin. On the UI, reframe it as "Professional screening (included)" not "Optional add-on."

**Exact files + approach:**

(a) `config.py` — no code change needed for the toggle; the env var `FIRSTBACK_REPUTATION_PROVIDER=twilio_nomorobo` should be set in Render's environment variables for the production web service. Document this as an OWNER_TODO.

Add a constant that makes the feature *look* included in the paid tier to the UI:

```python
# Whether the reputation provider is "included" (bundled into the plan) vs. an
# operator-configured add-on. True when the provider is set and credentials exist.
# Used by the settings UI to show "Included" vs "Optional add-on".
REPUTATION_INCLUDED = REPUTATION_PROVIDER != "off" and bool(
    (REPUTATION_PROVIDER == "twilio_nomorobo" and TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN)
    or (REPUTATION_PROVIDER == "hiya" and HIYA_API_KEY)
)
```

(b) `reputation.py` — `provider_label()` returns a human-readable string. Extend to include "included" signal:

```python
def provider_label():
    return {"twilio_nomorobo": "Twilio Lookup + Nomorobo Spam Score",
            "hiya": "Hiya number reputation"}.get(REPUTATION_PROVIDER, "Off")

def is_included():
    """True when reputation is bundled (not optional) — shapes the settings UI copy."""
    from config import REPUTATION_INCLUDED
    return REPUTATION_INCLUDED
```

(c) `templates/settings.html` — the provider-card block (lines 117–128):

Replace the disabled "Optional add-on" button with copy that differentiates by state:

```html
<div class="provider-card{{ ' is-connected' if reputation_configured else ' is-available' }}" data-provider="reputation">
  <span class="provider-meta">
    <span class="provider-name">Professional spam screening</span>
    <span class="provider-status">{{ reputation_label if reputation_configured else 'Not active' }}</span>
  </span>
  {% if reputation_configured %}
    <span class="btn btn-secondary btn-sm provider-btn" aria-disabled="true">Included</span>
  {% else %}
    <span class="btn btn-secondary btn-sm provider-btn" aria-disabled="true" title="Catches lead-gen vendor spam (local numbers with real caller ID). Included in Pro — contact support to activate.">Contact us to activate</span>
  {% endif %}
</div>
```

Change "The free tiers above are always on. The two add-ons are extra layers..." to:
> "The free tiers are always on. Professional spam screening — which catches lead-gen vendors with real local numbers — is included in your plan. AI message screening is an additional layer you can enable."

(d) `app.py` — settings route: ensure `reputation_configured` is passed (already is via `reputation.configured()`). Also pass `reputation_included = reputation.is_included()` if the new `is_included()` function is added, so the template can distinguish "I have a key but it's not included in plan" vs "it's truly included."

**Tests (standalone):**
- Unit: `reputation.is_included()` returns True when `REPUTATION_PROVIDER='twilio_nomorobo'` and creds set; False when `REPUTATION_PROVIDER='off'`.
- Unit: settings template renders "Included" badge when `reputation_configured=True`.
- Unit: settings template renders "Contact us to activate" when `reputation_configured=False`.
- Integration (env-level): set `FIRSTBACK_REPUTATION_PROVIDER=twilio_nomorobo` in the test env — confirm `reputation.configured()` is True and `lookup()` makes a network call (mock with `responses` library).

**Effort:** M (3–5 hours: config constant + reputation.py function + template copy + app.py context + Render env-var OWNER_TODO)
**Risk:** Medium. The real risk is cost: Twilio Nomorobo is billed per lookup (not cached hits). Mitigation: the 24h TTL cache in `db.number_reputation` means each unique number is looked up at most once per day across ALL tenants (shared cache). At MVP scale (<100 tenants, low unique-number volume), cost is negligible. At scale, a per-business daily lookup budget cap should be added (defer until needed). Collision: `reputation.py` + `config.py` + `settings.html` — coordinate with any agent touching the settings provider grid.

---

## Collision register

| File | Changes in this plan | Other agents likely touching |
|------|---------------------|------------------------------|
| `reminders.py` | New `scan_screening_report`, config import update, graduation low-volume path | Agent touching graduation (any 5c work) |
| `db.py` | New `screening_monthly_stats`, new schema column `alert_on_screening_report` | Any agent adding DB columns or stats functions |
| `templates/dashboard.html` | Copy edits: allowlist headline, dual-axis graduation bar, false-positive reframe | Agent 05 (dashboard UX) |
| `templates/settings.html` | Subtitle, reputation card copy, new alert toggle | Agent 01 (onboarding/settings) |
| `alerts.py` | New `screening_report` kind, toggle col, dedupe key | Agent 07 (ROI monthly recap) — coordinate channel |
| `app.py` | Dashboard route: `grad_verdicts` context, `grad_verdicts_min`; rescue route: toast payload | Dashboard agent, rescue UX agent |
| `config.py` | Low-volume graduation constants, `REPUTATION_INCLUDED` | Any agent touching config |
| `reputation.py` | `is_included()` function | None expected |

---

## Ordered change list (quick-wins first)

| # | Change | File(s) | Effort |
|---|--------|---------|--------|
| 1 | Auto-built allowlist headline copy | `settings.html`, `dashboard.html` | S |
| 3 | False-positive → "caller rescued" reframe + toast | `dashboard.html`, `app.py` rescue route | S |
| 2a | Dual-axis graduation progress (Day N · M signals) | `app.py` dashboard route, `dashboard.html` | M |
| 2b | Low-volume graduation path (5 verdicts if <20 calls/window) | `reminders.py`, `config.py` | M |
| 4 | Monthly Screening Report | `db.py`, `alerts.py`, `reminders.py`, `settings.html` | M |
| 5 | Bundle reputation into paid tier (env var + UI copy) | `config.py`, `reputation.py`, `settings.html`, `app.py`, Render env | M |

**Total effort:** 1S + 1S + 3M ≈ 2–4 days of focused work.

**Biggest risk:** Change 4 (monthly screening report) coordination with the ROI agent. If both agents add a monthly kind to `alerts.py`, two monthly SMSs fire on the 1st. Recommend: the ROI agent's monthly recap is the carrier; screening adds a `screening_section` to the ROI digest context rather than a separate kind.
