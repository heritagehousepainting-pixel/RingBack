# 07-RETENTION-MOAT — Build Plan
**Workstream:** Retention Moat Visibility  
**Audit source:** product-review/08-RETENTION.md  
**Date:** 2026-06-19  
**Bar:** Make the compounding assets visible as "what you'd lose"

---

## Overview

The growth engine is technically sound. The problem is that every asset it accumulates — customer history, Google reputation, recovered revenue — is invisible to the owner. Leaving today costs nothing because nothing is visibly stickier than day one. This plan surfaces the three compounding assets (reviews → reputation, database → customer book, revenue → running ROI) plus the two growth-engine structural gaps (streak unlock, seasonal operationalize) in order of switching-cost impact.

---

## Change 1: Closed-Loop Google Review Tracking

**What and why:** The review engine sends SMS but can't confirm reviews landed. `db.py` stores only a `review_link` string — no review count, no star rating. The Google Places API key is already credentialed for setup autocomplete but never used post-signup. Without closed-loop data, "your reviews are going up" is a claim, not a fact. With it, the product can show "14 reviews when you joined → 31 now. That's you."

**Exact files and approach:**

**(a) DB migration — `db.py` `init_db()`**

Add three columns to `businesses` (safe ALTER migrations, existing style):
```python
("google_review_count", "INTEGER"),
("google_star_rating", "REAL"),
("review_count_updated_at", "TEXT"),
```
Add a baseline snapshot pair (set once on first poll, never overwritten again):
```python
("google_review_count_baseline", "INTEGER"),
("google_star_rating_baseline", "REAL"),
```
Add a new setter `db.set_google_reputation(business_id, review_count, star_rating)` that writes count + rating + timestamp, and on first call only writes the `_baseline` columns if they are NULL.

**(b) Poll function — `reputation.py`** (file already exists; currently handles number reputation cache, unrelated)

Add a new public function `poll_google_reputation(business_id)`:
- Reads `biz["review_link"]` — extract the Place ID or use Places API text search on `biz["name"] + biz["service_area"]`.
- Call `https://maps.googleapis.com/maps/api/place/details/json?place_id=...&fields=user_ratings_total,rating&key=GOOGLE_PLACES_API_KEY`.
- On success, call `db.set_google_reputation(business_id, user_ratings_total, rating)`.
- Returns `{"review_count": N, "star_rating": X}` or `None` on failure.
- Never raises; all exceptions caught and logged to stderr.

The Google Places API key already lives in `config.py` as `GOOGLE_PLACES_API_KEY` (used for setup autocomplete). Reuse it.

**(c) Scheduler hook — `reminders.py`**

Add `scan_google_reputation(now=None)` alongside the existing scan functions:
- Runs monthly: check `review_count_updated_at` — if NULL or older than 28 days, poll.
- Call `reputation.poll_google_reputation(biz["id"])` for each eligible business.
- After first successful poll, if baseline is already set and current count differs by ≥5 reviews, queue a Vic briefing item via `alerts.notify(biz, "reputation_milestone", ctx)`.
- The milestone copy: `"You've added {delta} Google reviews since you started. You had {baseline} — now {current}. That's the FirstBack review engine working."`

Wire into `tick_once()` — add a monthly cadence check (same pattern as existing scans, gated by `review_count_updated_at`).

**(d) ROI page tile — `templates/analytics.html`**

Add a "Your reputation" tile below the existing ROI headline tile. It reads from a new `/api/reputation` endpoint (see app.py below):
```html
<div id="reputation-tile" class="stat-tile" style="display:none">
  <span class="stat-tile-label">Google reviews</span>
  <span class="stat-tile-value" id="rep-count"></span>
  <span class="stat-tile-sub" id="rep-trend"></span>
</div>
```
JS: `fetch('/api/reputation').then(...)` — if `review_count` present, show tile: "N reviews (up from M when you started)".

**(e) API route — `app.py`**

```python
@app.route("/api/reputation")
@login_required
def api_reputation():
    biz = current_business()
    return jsonify(
        review_count=biz.get("google_review_count"),
        star_rating=biz.get("google_star_rating"),
        baseline_count=biz.get("google_review_count_baseline"),
        baseline_rating=biz.get("google_star_rating_baseline"),
        updated_at=biz.get("review_count_updated_at"),
    )
```

**Tests (standalone):**
- `test_reputation.py` (file exists, currently tests number reputation cache) — add a new `TestGoogleReputation` class:
  - `test_poll_sets_baseline_on_first_call` — mock Places API, verify baseline columns set.
  - `test_poll_does_not_overwrite_baseline` — second call with different count; assert baseline unchanged, current updated.
  - `test_poll_handles_api_failure` — mock HTTP 500; assert no DB write, no raise.
  - `test_scan_skips_recent` — `review_count_updated_at` = today; assert `poll_google_reputation` not called.
  - `test_milestone_fires_on_delta_5` — simulate 14 → 20 reviews; assert `notify` called with `reputation_milestone`.

**Effort: S** — one API call, one db migration with 5 columns, one scan function (~50 lines), one template tile.  
**Risk:** Google Places API may not reliably resolve all contractor business names. Fail gracefully (tile stays hidden when count is NULL). Collision: `reputation.py` already exists — add to it, don't replace.

---

## Change 2: Customer Book — Make the Database a Visible Asset

**What and why:** `growth_candidates()` aggregates customer history per run but the owner never sees it as their property. The `/customers` route exists (`app.py:594`) but renders a marketing placeholder (`templates/customers.html` is "customer stories" marketing copy, not an app page). 200 customers with job history and SMS threads represent real switching cost — but only if the owner knows they exist.

**Exact files and approach:**

**(a) DB query — `db.py`**

Add `customer_book_stats(business_id)`:
```python
def customer_book_stats(business_id):
    """Aggregate stats for the owner's customer book: total unique customers,
    repeat customers (booked 2+), total jobs, all-time lifetime revenue estimate."""
    conn = get_conn()
    rows = conn.execute(
        "SELECT l.id, l.name, l.phone, "
        "(SELECT COUNT(*) FROM appointments a WHERE a.lead_id=l.id AND a.status='booked') AS job_count, "
        "(SELECT MAX(a.day) FROM appointments a WHERE a.lead_id=l.id AND a.status='booked') AS last_job_day "
        "FROM leads l WHERE l.business_id=? AND l.status='booked'",
        (business_id,)
    ).fetchall()
    conn.close()
    total = len(rows)
    repeat = sum(1 for r in rows if r["job_count"] >= 2)
    total_jobs = sum(r["job_count"] for r in rows)
    top_customers = sorted(rows, key=lambda r: -r["job_count"])[:5]
    return {
        "total_customers": total,
        "repeat_customers": repeat,
        "total_jobs": total_jobs,
        "top_customers": [dict(r) for r in top_customers],
    }
```

**(b) App route — `app.py`**

Convert `/customers` from marketing redirect to an authenticated app page:
```python
@app.route("/customers")
@login_required
def customer_book():
    biz = current_business()
    stats = db.customer_book_stats(biz["id"])
    avg = growth._job_value(biz)
    lifetime_revenue = stats["total_jobs"] * avg
    return render_template("customer_book.html", business=biz, stats=stats,
                           lifetime_revenue=lifetime_revenue, avg=avg)
```

**(c) Template — `templates/customer_book.html`** (new file, replaces the marketing stub)

Structure:
- **Hero stat row:** "N customers served · M repeat bookings · ~$X,XXX in lifetime jobs"
- **Vic line:** "You've built a customer book of {N} contractors. This history — their names, threads, job notes — is yours."
- **Top customers table:** name, job count, last job date — shows at most 5.
- **Footer:** "All {total_jobs} jobs tracked. Switching means starting over."

No new data — all existing `leads` + `appointments`.

**(d) Nav link — `templates/app_shell.html`**

Add "Customers" to the sidebar nav (alongside Leads, Analytics, Growth Tray). Single `<a href="/customers">` addition.

**(e) Vic briefing hook — `assistant.py`**

In the `briefing()` function, add a customer_book card when `total_customers >= 10`:
```
"Your customer book: {N} customers, {M} repeat, {total_jobs} jobs on record."
```
This surfaces in the daily digest and the command center automatically.

**Tests (standalone):**
- `test_sf4_db.py` or new `test_customer_book.py`:
  - `test_customer_book_stats_empty` — no booked leads, expect zeros.
  - `test_customer_book_stats_counts` — 3 customers, one with 2 bookings; assert repeat=1, total_jobs=4.
  - `test_customer_book_route_requires_login` — 302 redirect when not authenticated.
  - `test_customer_book_route_renders` — authenticated, assert 200 + "customer book" in body.

**Effort: S** — one DB function, one route change, one new template (~60 lines), one nav link, one briefing line.  
**Risk:** The `/customers` URL is already defined (`app.py:594`) so changing it from public to `@login_required` is correct but technically a breaking change for the marketing page. The marketing "customer stories" page should move to `/resources/customer-stories`. Collision: none with other agents (growth.py not touched here).

---

## Change 3: ROI Accumulation — Progressive Milestones + Monthly Briefing

**What and why:** `roi.py` fires once at 2× and goes silent. `roi_milestone_sent_at` is a single timestamp — no support for 5×, 10×, 25×. The ROI page shows a static tile. A contractor at month 6 sees "5.2×" with no visceral sense of accumulation. The monthly "what did FirstBack recover this month" story is the primary anti-churn narrative.

**Exact files and approach:**

**(a) DB migration — `db.py` `init_db()`**

Replace single `roi_milestone_sent_at` with a multi-level milestone table (backward-compatible — keep the column, add a table):
```sql
CREATE TABLE IF NOT EXISTS roi_milestones (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    business_id INTEGER NOT NULL,
    level INTEGER NOT NULL,       -- 2, 5, 10, 25 (the multiplier)
    fired_at TEXT NOT NULL,
    revenue INTEGER,
    UNIQUE(business_id, level)
);
CREATE INDEX IF NOT EXISTS idx_roi_milestones_biz ON roi_milestones(business_id);
```

Add `db.get_roi_milestones(business_id)` returning fired levels. Add `db.mark_roi_milestone(business_id, level, revenue)` for INSERT OR IGNORE.

**(b) `roi.py` — extend to multi-level**

Change `check_roi_milestone(business_id)` to return the HIGHEST unfired milestone the business has crossed:
```python
_MILESTONE_LEVELS = [2, 5, 10, 25]

def check_roi_milestone(business_id):
    ...
    fired_levels = {r["level"] for r in db.get_roi_milestones(business_id)}
    for level in reversed(_MILESTONE_LEVELS):
        if roi_multiple >= level and level not in fired_levels:
            body = _milestone_body(level, revenue, avg_source)
            return {"level": level, "multiple": roi_multiple, "revenue": revenue,
                    "avg_source": avg_source, "body": body}
    return None
```

`_milestone_body(level, revenue, avg_source)` produces level-specific copy:
- level=2: existing copy (backward compatible)
- level=5: "FirstBack has now recovered 5× its cost. Total since day one: ~$X,XXX."
- level=10: "10× its cost. That's $X,XXX in jobs that would have gone to voicemail."
- level=25: "25×. At this point, FirstBack costs you less per booked job than a cup of coffee."

**(c) Caller sites — `app.py`**

Update the two milestone-check sites (lines ~1774 and ~1892) to call `db.mark_roi_milestone(biz["id"], milestone["level"], milestone["revenue"])` instead of `db.set_roi_milestone_sent(biz["id"], ts)`. Both callers already loop on the booking event, so multi-fire on the same booking is guarded by the UNIQUE constraint.

**(d) Monthly proactive — `reminders.py`**

Add `scan_monthly_roi(now=None)`:
- Runs on the 1st of each month (check `now_local.day == 1 and 8 <= now_local.hour < 9`).
- Deduped via `alerts.notify(biz, "monthly_roi", ctx)` with a monthly key (`YYYY-MM`).
- Copy: "Last month — {leads} missed calls captured, {booked} estimates booked, ~${revenue:,} recovered. Running total since day one: ~${all_time_revenue:,}."
- Uses `db.analytics(business_id, days=30)` for last month + `db.analytics(business_id, days=None)` for all-time.
- Gate: only fires if `all_time_revenue > 0` (no empty noise for new tenants).

Wire into `tick_once()` alongside the existing monthly scans.

**(e) ROI page — `templates/analytics.html`**

Add an "All time" tab that is the default when all-time revenue > 0 (currently the 30-day view is the default). Add a visual "running total" bar that dwarfs the monthly bar. Add a milestones timeline: "2× achieved [date] · 5× achieved [date]" from the `roi_milestones` table, surfaced via a new `/api/roi_milestones` endpoint.

**Tests (standalone):**
- `test_roi_milestone.py` (exists) — extend:
  - `test_multiple_milestones_fire_in_order` — stub 10× revenue; assert levels 2, 5, 10 all fire on successive calls.
  - `test_already_fired_milestone_not_repeated` — mark level=5 fired; assert check returns level=10 not 5.
  - `test_milestone_body_level_25` — assert "25×" copy correct.
- New `test_monthly_roi_scan.py`:
  - `test_fires_on_first_of_month` — mock now = 8am on the 1st; assert notify called.
  - `test_does_not_fire_mid_month` — mock now = 8am on 15th; assert notify not called.
  - `test_deduped_second_run` — run twice same morning; assert notify only called once.
  - `test_skips_zero_revenue` — new tenant, 0 bookings; assert not fired.

**Effort: M** — new DB table, refactored roi.py, two caller updates, one new scan function, template changes.  
**Risk:** Backward-compat: keep `roi_milestone_sent_at` column and still set it on level=2 fire so any code that reads it still sees it. The UNIQUE constraint on `roi_milestones(business_id, level)` prevents double-fire even if two booking events race. Collision: app.py booking handler (both milestone-check sites) — note for the ROI-proof agent (09) who may also touch these; coordinate to not double-refactor.

---

## Change 4: Auto-Mode Streak Unlock — The 7-Day GO Streak

**What and why:** `settings_growth_mode()` in `app.py` (line 1292) hard-rejects `mode='auto'` — it was spec'd in PHASE5D-SPEC.md but never built. The tray requires daily owner approval forever, which is correct friction for week one and a churn driver for month three. The streak is both the TCPA-safe unlock mechanism and a retention hook: seven mornings of GO is invested behavior the owner has to consciously abandon.

**Exact files and approach:**

**(a) DB migration — `db.py` `init_db()`**

Add three columns to `businesses`:
```python
("growth_streak_count", "INTEGER DEFAULT 0"),   # consecutive daily GOs
("growth_streak_last_at", "TEXT"),              # ISO of last GO (to detect breaks)
("growth_streak_unlocked_at", "TEXT"),          # when streak reached threshold
```

Add `db.record_growth_go(business_id)` — call on every successful batch release:
- Read `growth_streak_last_at`. If last GO was on a different calendar day (business local time), increment `growth_streak_count`. If last GO was more than 2 days ago, reset to 1. Update `growth_streak_last_at = now`.
- If `growth_streak_count >= STREAK_THRESHOLD` and `growth_streak_unlocked_at IS NULL`, set `growth_streak_unlocked_at = now` and call `db.set_growth_mode(business_id, 'auto')`.
- Returns `{"streak": N, "unlocked": bool}`.

Add to `config.py`: `STREAK_THRESHOLD = 7` (configurable; default 7).

**(b) `app.py` — wire streak tracking into tray release**

In `growth_tray_release()` (line 1334), after `db.release_growth_batch(...)`:
```python
streak_result = db.record_growth_go(biz["id"])
# Pass streak_result to redirect so tray can show progress.
```

In `_handle_tray_reply()` (line 1257), after successful GO batch release via SMS:
```python
db.record_growth_go(biz["id"])
```

**(c) `app.py` — unlock `auto` in `settings_growth_mode()`**

Change line 1299:
```python
# Before: if mode not in ("off", "tray"):
# After:
if mode == "auto":
    # Only allow auto if streak is unlocked
    biz = current_business()
    if not biz.get("growth_streak_unlocked_at"):
        mode = "tray"  # coerce silently; streak not yet earned
elif mode not in ("off", "tray"):
    mode = "off"
```

**(d) `templates/growth_tray.html` — streak progress bar**

Add above the "Send All" button when `growth_mode == 'tray'` and not yet unlocked:
```html
{% if streak_count < 7 %}
<div class="streak-bar">
  <span>{{ streak_count }}/7 mornings GO → unlocks Auto Mode</span>
  <div class="streak-pip-row">
    {% for i in range(7) %}
    <span class="streak-pip {% if i < streak_count %}filled{% endif %}"></span>
    {% endfor %}
  </div>
</div>
{% else %}
<div class="streak-badge">Auto Mode unlocked. Enable it in Settings.</div>
{% endif %}
```

Pass `streak_count = biz.get("growth_streak_count", 0)` from the `growth_tray()` route.

**(e) Daily digest copy — `reminders.py` `scan_daily_digest()`**

If streak > 0 and < threshold, append to digest: "Streak: {N}/7 GO mornings. {7-N} more and review requests send automatically."

**Tests (standalone):**
- `test_growth_tray.py` (exists) — extend:
  - `test_record_growth_go_increments` — call twice on different days; assert streak=2.
  - `test_record_growth_go_resets_on_gap` — 3-day gap; assert streak reset to 1.
  - `test_streak_unlocks_at_threshold` — call 7 times on consecutive mock days; assert `growth_mode='auto'` and `growth_streak_unlocked_at` set.
  - `test_auto_rejected_without_streak` — POST `/settings/growth_mode` with `mode=auto` when streak not earned; assert mode stays `tray`.
  - `test_auto_accepted_with_streak` — same POST when `growth_streak_unlocked_at` is set; assert mode=`auto`.
  - `test_tray_shows_streak_progress` — GET `/growth/tray` with streak=3; assert "3/7" in response.

**TCPA safety preserved:** Auto mode still only releases `review_request` plays to `pending` (existing `scan()` logic, line 432). Win-backs, referrals, reactivations remain `held` even in auto mode. Tone-risk plays always held. TCPA narrowing on win-backs (has_inbound check) unchanged. The streak is a gate to earn auto mode; it doesn't change what auto mode does.

**Effort: M** — 3 DB columns, one new function, two caller sites, one template section, one settings gate change.  
**Risk:** Streak counting uses server-side timestamps (business local day). If a business spans timezones, `_biz_tz(biz)` resolves it correctly. The "more than 2 days gap = reset" rule prevents a streak from counting a daily GO that happened after a week's absence as a continuation. Collision: `growth_approvals` (db.py) and `release_growth_batch` are touched — cross-check with any agent modifying the tray flow.

---

## Change 5: Seasonal Campaign — One-Tap Operational

**What and why:** `_seasonal_play()` in `growth.py` (line 340) produces a non-sendable play (`sendable=False`) that surfaces as "Offer AC tune-ups to past customers now" with action `"show my leads"`. No send mechanism exists. The seasonal campaign that fills Dave's spring calendar is the highest-leverage advisory play FirstBack generates, and it hands all the work back to Dave.

**Exact files and approach:**

**(a) `growth.py` — seasonal cohort query**

Add a new public function `seasonal_cohort(business_id, today=None)`:
- Returns the list of past customers eligible for a seasonal blast: `status='booked'` leads whose last appointment was > 3 months ago.
- Uses existing `growth_candidates()` data filtered to `last_appt_day` > 90 days ago + `booked_count >= 1`.
- Returns `[{"id": ..., "name": ..., "phone": ..., "first": ...}]`.

**(b) `growth.py` — seasonal play draft**

Add `_copy_seasonal(first, business, service)`:
```python
def _copy_seasonal(first, business, service):
    return (f"{_greet(first)}It's that time of year — {_bizname(business)} has openings "
            f"for {service} before the rush. Reply and we'll get you in.")
```

Change `_seasonal_play()` to become sendable when `seasonal_cohort` is non-empty:
```python
def _seasonal_play(business, today, val):
    trade = (business.get("trade") or "").lower()
    for key, (start_m, end_m), service in _SEASONS:
        if key in trade and start_m <= today.month <= end_m:
            return _opp("seasonal", None, "", "", "grow",
                        title=f"Seasonal: send {service} offer to past customers",
                        why="peak season opening; past customers book faster than new leads",
                        tone="ok", label="Seasonal", money=val * 5,
                        sendable=True,  # now sendable — cohort-blast, not per-lead
                        action="launch_seasonal_campaign",
                        seasonal_service=service)  # pass through to tray
    return None
```

Note: `sendable=True` here changes behavior — the tray will show it as actionable. The seasonal play has no `lead_id` (it's a cohort blast), so `scan()` must explicitly skip it in the per-lead loop (it already does: `if not p.get("sendable") or p.get("lead_id") is None` — this guard stays, the seasonal blast takes a different path via a dedicated route).

**(c) `app.py` — seasonal campaign launch route**

```python
@app.route("/growth/seasonal/launch", methods=["POST"])
@login_required
def launch_seasonal_campaign():
    """Tray-gated cohort blast: queue one seasonal SMS per eligible past customer.
    Dave approves the batch (CSRF-gated); sends flow through scheduled_messages spine."""
    if not _csrf_ok():
        abort(403)
    biz = current_business()
    # Frequency cap: one seasonal blast per business per season (28-day window).
    if db.recent_growth_touch_kind(biz["id"], "seasonal", within_days=28):
        return redirect("/growth/tray?seasonal_blocked=already_sent")
    from growth import seasonal_cohort, _copy_seasonal, _SEASONS
    today = date.today()
    service = request.form.get("service", "seasonal work")
    cohort = seasonal_cohort(biz["id"], today)
    queued = 0
    for lead in cohort:
        phone = lead.get("phone", "").strip()
        if not phone or messaging.outbound_mode(biz, phone) == "suppressed":
            continue
        if db.recent_growth_touch(biz["id"], lead["id"], within_days=30):
            continue
        body = _copy_seasonal(lead.get("first", ""), biz, service)
        if "[" in body:
            continue
        send_at = (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat()
        db.add_scheduled_message(biz["id"], lead["id"], None, "seasonal",
                                 send_at, body, status="held")
        queued += 1
    return redirect(f"/growth/tray?seasonal_queued={queued}")
```

Add `db.recent_growth_touch_kind(business_id, kind, within_days)` to check for any touch of a specific kind in the window (variant of existing `recent_growth_touch`).

**(d) `templates/growth_tray.html` — seasonal campaign card**

When a `seasonal` play is in the feed (non-cohort surface), show a dedicated card above the per-lead plays:
```html
{% if seasonal_play %}
<div class="seasonal-card">
  <h3>{{ seasonal_play.title }}</h3>
  <p>{{ seasonal_cohort_count }} past customers eligible — they know you, they book faster.</p>
  <form method="post" action="/growth/seasonal/launch">
    <input type="hidden" name="_csrf" value="{{ csrf_token }}">
    <input type="hidden" name="service" value="{{ seasonal_play.seasonal_service }}">
    {{ button('Launch Campaign', variant='primary') }}
  </form>
</div>
{% endif %}
```

Pass `seasonal_play` and `seasonal_cohort_count` from the `growth_tray()` route (call `growth.seasonal_cohort(biz["id"])` to get count).

**Tests (standalone):**
- `test_growth.py` (exists) — extend:
  - `test_seasonal_cohort_filters_recent` — lead with last appt 30 days ago excluded; 100+ days ago included.
  - `test_seasonal_cohort_empty_outside_season` — trade=hvac, month=July (outside season window); assert empty.
  - `test_seasonal_campaign_launch_queues_cohort` — 3 eligible leads; POST `/growth/seasonal/launch`; assert 3 `held` rows in `scheduled_messages`.
  - `test_seasonal_campaign_frequency_cap` — recent `seasonal` touch within 28 days; assert redirect with `seasonal_blocked`.
  - `test_seasonal_campaign_respects_opt_out` — one lead suppressed; assert only 2 rows queued.

**Effort: M** — new cohort function, copy function, one route, frequency-cap DB helper, template card.  
**Risk:** The seasonal play currently has `lead_id=None` which means `scan()` already skips it in the per-lead path. The new launch route queues per-lead rows with real `lead_id`s, so frequency caps and dedup indexes apply correctly. Collision: `growth.py` `_seasonal_play()` return signature changes (adds keys) — check `test_growth.py` `test_seasonal_play_*` tests for any assertion on the play dict structure. The `seasonal` kind is new in `_GROWTH_EXCLUSION` — does NOT need to be added there (it should be frequency-capped, unlike `reminder` and `followup`).

---

## Change 6 (QUICK WIN): Density-Aware Referral Copy

**What and why:** `_copy_referral()` in `growth.py` (line 184) sends the same message regardless of whether there are 0 or 5 other jobs in the zip. `zip_counts` is already computed in the `plays()` loop but never piped to the referral `_opp()`. A referral ask that mentions "we just wrapped three jobs on your block" is materially more persuasive and costs zero new data.

**Exact files and approach:**

`growth.py` — in the `plays()` loop, the referral block (line 306):
```python
# Before:
out.append(_opp("referral", lid, who, phone, "grow", ..., draft=_copy_referral(first, business)))

# After:
z = _zip(c.get("address"))
nearby = zip_counts.get(z, 0) if z else 0
draft = (_copy_referral_dense(first, business) if nearby >= 2
         else _copy_referral(first, business))
out.append(_opp("referral", lid, who, phone, "grow", ..., draft=draft))
```

Add `_copy_referral_dense(first, business)`:
```python
def _copy_referral_dense(first, business):
    return (f"{_greet(first)}we've been busy on your block this month. "
            f"If a neighbor needs the same work, have them call {_bizname(business)}.")
```

Note: `zip_counts` is built from leads with `created_at` within 14 days. The referral fires within 3 days of last appointment. These windows overlap but aren't identical — close enough; the density signal is conservative.

**Tests:**
- `test_growth.py` — add:
  - `test_referral_dense_copy_when_zip_count_2` — seed 2 leads same zip within 14d; assert referral draft contains "busy on your block".
  - `test_referral_standard_copy_when_zip_count_0` — no density; assert standard copy.

**Effort: S** — 4 lines of code + 1 copy function.  
**Risk:** Minimal. The `zip_counts` dict is built earlier in `plays()` and is available at the referral block. Edge case: if `_zip(c.get("address"))` returns None (no address), `nearby=0` and standard copy fires. No collision.

---

## Effort Summary and Order

| # | Change | File(s) | Effort | Risk |
|---|--------|---------|--------|------|
| 6 | Density-aware referral copy | `growth.py` | **S** | minimal |
| 2 | Customer Book page | `db.py`, `app.py`, new template, `app_shell.html` | **S** | low |
| 1 | Google Review tracking | `db.py`, `reputation.py`, `reminders.py`, `analytics.html`, `app.py` | **S** | low-medium (Places API) |
| 3 | Progressive ROI milestones + monthly briefing | `db.py`, `roi.py`, `app.py`, `reminders.py`, `analytics.html` | **M** | medium (backward compat) |
| 4 | Auto-mode streak unlock | `db.py`, `app.py`, `growth_tray.html`, `reminders.py`, `config.py` | **M** | medium (TCPA safety) |
| 5 | Seasonal campaign operational | `growth.py`, `app.py`, `db.py`, `growth_tray.html` | **M** | medium (cohort blast) |

**Total effort:** ~2 S + 3 M = approximately 3–4 focused days for a careful, tested build.

---

## Collision Map

| This plan touches | Also touched by |
|------------------|----------------|
| `growth.py` `plays()` | Any agent modifying the growth tray (check for concurrent edits to the play loop) |
| `db.py` `release_growth_batch()` | Tray flow agents; coordinate streak counter wiring |
| `app.py` booking handler (ROI milestone sites, lines ~1774, ~1892) | ROI-proof agent (09) — coordinate so milestone refactor isn't done twice |
| `reminders.py` `tick_once()` | Scheduling/notifications agents — adding two new scan functions is additive, low collision risk |
| `analytics.html` | ROI-proof agent (09) — the "all time" bar and milestones timeline may overlap |
| `reputation.py` | Separate call-screening reputation cache — add, don't replace |

**Monthly ROI scan ownership:** The monthly `$X recovered` briefing (Change 3d) is a Vic briefing item (owner-facing, in-app + SMS). The broader monthly `$X RECAP` email is another agent's territory (ROI agent, 09). These do not conflict: this plan's monthly proactive is a short SMS/briefing card, not the full monthly email.

---

## Biggest Risk

**ROI milestone backward compatibility.** The existing `roi_milestone_sent_at` column is read by `roi.py:42` and written by `db.set_roi_milestone_sent()` (called from two sites in `app.py`). The new `roi_milestones` table replaces the logic but the column must keep being set at level=2 fire so any monitoring, tests, or future code reading it doesn't break silently. The UNIQUE constraint on the new table prevents double-fire but the migration must run before the app restarts on the next deploy. Migration is additive (new table, new columns on businesses are all additive ALTERs) — safe.
