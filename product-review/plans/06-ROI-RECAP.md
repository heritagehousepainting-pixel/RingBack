# Plan 06 — ROI Proof + Monthly Recap (Anti-Churn Surface)

**Workstream:** ROI proof, monthly recap, loss-framing, dollar hierarchy, real-dollar attribution  
**Source audits:** product-review/09-ROI-PROOF.md (F1–F5), product-review/08-RETENTION.md (Finding 3)  
**Read-only reference:** this file is the plan; implementation agents own the code changes.

---

## Context and Priority Logic

The analytics foundation is honest and technically sound. The milestone SMS gates correctly, the daily digest dedupes properly, the "estimate" labeling is everywhere it needs to be. What is absent is the *emotional proof layer* — the thing that makes cancellation feel financially stupid rather than just mildly inconvenient.

The changes below are ordered quick-win first, highest-retention-impact last. Changes 1–3 are S-effort and can ship in the same PR. Changes 4–5 are M/L and ship separately.

**Collision surface:** `reminders.py` (ticker scan additions), `alerts.py` (new kind + format_message), `db.py` (new column, new query). The Tier-0 agent owns the "$null/job tile" JS bug (F2); this plan explicitly excludes that fix and owns F1, F3, F4, F5 only.

---

## Change 1 — Flip the Dollar/Multiple Hierarchy in the Headline Tile (S)

**What and Why (F1 from 09-ROI-PROOF.md):**  
The ROI headline tile currently reads `"paid for itself ~18x"` as the large hero value and `"estimated $32,400 in booked jobs"` as subordinate sub-text. Dave the painter thinks in dollars he almost lost, not in abstract multiples. The sentence that prevents cancellation is `"you'd have missed $32,400 this month without FirstBack"` — the multiple is validating confirmation, not the hook.

**Exact files and approach:**

File: `/Users/jonathanmorris/apps/firstback/templates/analytics.html` — lines 19-21  
The `roi-headline-value` span currently shows the multiple string; `roi-headline-sub` shows the dollar figure. Swap the rendered text in the `renderHeadline()` function in the inline `<script>` block (lines 61-62):

- Current: `valEl.textContent = 'paid for itself ~' + multiple + 'x'` / `subEl.textContent = 'estimated ' + rev + ' in booked jobs'`  
- New: `valEl.textContent = rev + ' estimated recovered'` / `subEl.textContent = 'paid for itself ~' + multiple + 'x this month'`

The `noteEl` copy stays unchanged — it already correctly sources the estimate label. No Python changes needed. CSS class names stay; only the text content flips.

**Tests (standalone):**  
Add a test in `test_f12_analytics.py` or a new `test_roi_headline.py`: render the analytics template with a mock analytics payload and assert that the `roi-headline-value` element contains a dollar figure (matching `\$[\d,]+`) and that `roi-headline-sub` contains the `x` multiplier string. This is a pure DOM-string assertion — no network, no DB.

**Effort:** S (30 min)  
**Risk:** None. Visual-only change. The JS path is self-contained in analytics.html; no other template references it.  
**Collision:** None — the Tier-0 agent owns the `avg_source` sub-label fix on line 545 of app.js; this change is in analytics.html only.

---

## Change 2 — Loss-Framing: Add "Without FirstBack" Counterfactual (S)

**What and Why (F3 from 09-ROI-PROOF.md):**  
Every ROI surface currently shows only the *recovered* side. "You recovered $3,200" competes with silence. The psychological anchor that prevents cancellation is *loss avoidance*: "Without FirstBack, that $3,200 walks to a competitor." This framing needs to appear in three places: (a) the milestone SMS body, (b) the weekly digest ROI paragraph, (c) the analytics page beneath the headline tile.

**Exact files and approach:**

**a. Milestone SMS — `roi.py`, `check_roi_milestone()`, lines 63-68:**  
Append one sentence to the `body` string after the existing estimate copy:  
`"Without FirstBack, those calls go unanswered and that job likely goes to a competitor."`  
Keep it outside the estimate parenthetical so the honest-estimate framing stays clean.

**b. Weekly digest ROI — `convos.py`, `_roi_block()`, lines 319-323:**  
After the closing `"(roi_str}estimate based on {source_label})."`, append:  
`" That's revenue that would have walked without a text-back."`  
Single sentence; stays within the same paragraph string. No new function, no new parameter.

**c. Analytics page aside — `templates/analytics.html`:**  
Add a `<p>` element immediately after the `roi-headline` div (line 24) with class `roi-loss-note`:  
`<p class="roi-loss-note" id="roi-loss-note" style="display:none">Without text-back, missed calls convert at ~0%.</p>`  
Reveal it conditionally in the `renderHeadline()` JS function when `multiple` is truthy (same gate as the tile display). No backend change needed.

**Tests (standalone):**  
- `test_roi_milestone.py`: add a test that calls `check_roi_milestone()` with a valid milestone scenario and asserts the returned `body` string contains the substring `"without FirstBack"` (case-insensitive).  
- `test_f12_digest.py`: add a test that calls `convos._roi_block()` with `a2p_ready=True` mock and asserts the returned string contains `"would have walked"`.  
- Template test: assert the `roi-loss-note` element exists in the analytics.html DOM.

**Effort:** S (45 min)  
**Risk:** Low. The milestone body change adds one sentence after existing copy; the honesty guards (estimate language, source label) are untouched. The digest paragraph extension is a pure string append.  
**Collision:** None with Tier-0. Both edits are in separate files from the app.js tile bug.

---

## Change 3 — Monthly Recap SMS + Email: Day-28 Anti-Churn Touchpoint (M)

**What and Why (F4 from 09-ROI-PROOF.md, Finding 3 from 08-RETENTION.md):**  
This is the highest single-leverage anti-churn feature not yet built. The moment most likely to trigger cancellation is the day before or day of renewal. An automated 30-day recap arriving on day 28 pre-empts the "is this worth it?" thought with concrete evidence. Currently the ROI milestone fires once, the daily digest covers today's queue, and the weekly digest covers conversations — but nothing lands at renewal time with a *running total*.

**Schema:**  
No new table needed. Use the existing `db.get_meta` / `db.set_meta` key-value store, keyed per business: `monthly_recap_sent:{business_id}:{YYYY-MM}`. The value is the ISO timestamp of the send. The 26-day dedup window (same as `daily_digest`) prevents double-sends if the ticker runs twice in the same window.

One new column on `businesses` is needed as an anchor: `signed_up_at TEXT` (migration in `db.py`'s `_migrate()` function, same pattern as `roi_milestone_sent_at` at line 839). Populate it for new tenants via `create_business()` and backfill existing rows to `datetime('now')` in the migration. This anchors the "day 28-30 of your billing month" calculation. Alternatively, the businesses table `users` table already has `created_at` per user — use `MIN(users.created_at) WHERE users.business_id=?` as the signup anchor if adding a column is undesirable.

**New function: `scan_monthly_recap(now=None)` in `reminders.py`:**

Pattern follows `scan_daily_digest()` exactly:
1. Iterate `db.list_businesses()`
2. Resolve business-local timezone via `_biz_tz(biz)`
3. Skip unless local day-of-month is in [28, 29, 30, 31] (to catch all billing-month endings including short months)
4. Build a per-business dedupe key: `f"monthly_recap:{biz['id']}:{YYYY-MM}"` where YYYY-MM is the *current* month
5. Check `db.get_meta(dedupe_key)` — skip if already sent within 26 days
6. Load analytics: `db.analytics(biz['id'], days=30)` — the existing function, no changes needed
7. Gate: A2P must be ready (`compliance.a2p_ready(biz)`), and `booked_n >= 1` (don't send a recap for zero bookings — that's sad, not celebratory)
8. Build SMS body (see copy below) and call `alerts.notify(biz, "monthly_recap", ctx)` — owner cell only, same as `daily_digest`
9. On success: `db.set_meta(dedupe_key, now_utc)` to record the send

**New alert kind: `"monthly_recap"`** in `alerts.py`:
- Add `"monthly_recap"` to `ALERT_KINDS` tuple (line 31)
- Add to `_TOGGLE_COL`: `"monthly_recap": "alert_on_daily_digest"` — rides the daily digest toggle; no new DB column needed
- Add to `_DAILY_DEDUPE_KINDS` — same 26h dedup window
- Add `format_message` branch for `"monthly_recap"`:

```python
if kind == "monthly_recap":
    leads = context.get("leads", 0)
    booked = context.get("booked", 0)
    revenue = context.get("revenue", 0)
    multiple = context.get("multiple")
    avg_source = context.get("avg_source", "industry_default")
    est_label = "(estimated)" if avg_source != "owner" else "(based on your job value)"
    multi_line = f" -- about {multiple}x what it costs" if multiple else ""
    return (
        f"Your FirstBack month: {leads} missed calls rescued, {booked} booked, "
        f"~${revenue:,} recovered {est_label}{multi_line}. "
        f"Reply STATS to see the full breakdown."
    )
```

Copy discipline: "recovered" not "earned," "estimated" always labeled, "~$X" not "$X," never "cash" or "collected."

**Wire into `tick_once()` in `reminders.py`:**  
Add a call after `scan_daily_digest(now)` (line 913), same try/except pattern:
```python
try:
    scan_monthly_recap(now)
except Exception as e:
    print(f"[firstback] monthly recap scan failed: {e}", file=sys.stderr, flush=True)
```

**Tests (standalone, new file `test_monthly_recap.py`):**
- `test_scan_monthly_recap_fires_on_day_28`: mock `db.list_businesses()` returning one business with day-28 local date, A2P ready, 4 bookings; assert `alerts.notify` called with kind `"monthly_recap"` and body containing `"month"` and `"rescued"`.
- `test_scan_monthly_recap_skips_already_sent`: set `db.get_meta` to return a recent ISO timestamp; assert `alerts.notify` NOT called.
- `test_scan_monthly_recap_skips_a2p_pending`: mock `compliance.a2p_ready` returning False; assert no send.
- `test_scan_monthly_recap_skips_zero_bookings`: mock `db.analytics` returning `booked=0`; assert no send.
- `test_format_message_monthly_recap`: call `alerts.format_message("monthly_recap", {...})` directly; assert body is under 320 chars and contains "estimated" or "based on your job value".

**Effort:** M (3-4 hours including migration + tests)  
**Risk:** Medium. New alert kind touches `alerts.py` ALERT_KINDS + _TOGGLE_COL + format_message + a new scan in reminders.py + tick_once. Regression risk is low because the scan is purely additive (no existing scan is modified) and the dedupe guard prevents double-sends. The main failure mode is a broken meta key leading to a double-send on a retry; the 26h dedup window and the per-month key together make this extremely unlikely.  
**Collisions:** `reminders.py` (tick_once) and `alerts.py` (ALERT_KINDS) — coordinate with any agent touching those files in the same sprint. The Tier-0 agent is in app.js only; no collision there.

---

## Change 4 — Real-Dollar Attribution: "Mark as Won ($___)" Action (L)

**What and Why (F5 from 09-ROI-PROOF.md):**  
Revenue is always and only estimated: `booked_n * avg_job_value`. There is no mechanism for Dave to say "Maria's job closed for $4,200" and have that exact number flow into the ROI tile. Real closed-job numbers are 100% credible — no "estimate" caveat needed. As real amounts accumulate, the ROI display migrates from persuasive-but-hedged to undeniable-and-exact. This is the strongest possible proof statement and also the highest retention anchor: data the owner themselves entered is maximally sticky.

**This is a phased build. Phase 1 ships first; Phase 2 follows when Phase 1 has real data.**

### Phase 1: Schema + UI — "Mark as Won ($___)"

**Schema change (`db.py`):**  
Add two columns to the `leads` table via `_migrate()`:
- `won_at TEXT` — ISO timestamp when the owner marked the job closed
- `won_amount REAL` — the actual dollar amount the owner entered (NULL = not yet closed)

Migration pattern: same as existing ALTER TABLE migrations in `_migrate()`. Gate with `"won_at" not in lead_cols`.

Add two new functions:
- `db.mark_lead_won(lead_id, amount, ts=None)` — sets `won_at`, `won_amount` on a lead; validates `amount > 0`
- `db.won_leads(business_id, days=None)` — returns rows with `won_amount IS NOT NULL`, scoped to tenant, with optional date window

**API endpoint (`app.py`):**  
`POST /api/leads/<lead_id>/won` — accepts JSON `{"amount": float}`. Validates: amount > 0, lead belongs to this business (tenant scope). Calls `db.mark_lead_won()`. Returns `{"status": "ok", "won_amount": amount}`. Guard: a lead can only be marked won once (if `won_at` is already set, 409 or update allowed — choose update for UX simplicity).

**UI change (`templates/dashboard.html` or lead card component):**  
Add a "Mark closed ($)" button/link to the lead detail view. On click, show an inline number input + "Save" button. On save, POST to the new endpoint. On success, show "Closed: $X,XXX" in place of the button. This should be a minimal DOM manipulation — no framework needed, matches the existing JS patterns in `app.js`.

### Phase 2: Blend Real Amounts into Analytics

**`db.analytics()` update:**  
After Phase 1 ships and real `won_amount` data exists:

1. Query `db.won_leads(business_id, days)` alongside the existing booked appointments query
2. Calculate two separate revenue figures:
   - `confirmed_revenue = sum(won_amount for won leads in window)` — exact, no caveat
   - `estimated_pipeline = (booked_n - won_n) * resolved_avg` — estimated, for not-yet-closed bookings
   - `total_revenue = confirmed_revenue + estimated_pipeline`
3. Add `confirmed_revenue`, `estimated_pipeline`, and `won_n` to the analytics response

**`templates/analytics.html` + `static/app.js` update:**  
When `confirmed_revenue > 0`, show a second sub-tile under "Est. revenue recovered":  
`"Confirmed: $X,XXX — Estimated pipeline: $Y,YYY"`  
The headline tile switches to `"$X,XXX confirmed + ~$Y,YYY estimated"` to show the real-vs-estimate split honestly.

**Monthly recap update:**  
When `confirmed_revenue > 0`, the monthly recap SMS leads with `"$X,XXX confirmed closed + ~$Y,YYY estimated"` instead of the all-estimated copy.

**Tests (standalone):**  
- `test_db_mark_lead_won`: call `db.mark_lead_won(lead_id, 4200)` and assert `won_at` and `won_amount` are set on the lead row; assert cross-tenant isolation (wrong business_id 404s at the API layer).
- `test_analytics_blends_confirmed`: seed two booked leads, mark one won for $4,200 (avg is $3,000); assert `analytics()` returns `confirmed_revenue=4200`, `estimated_pipeline=3000`, `won_n=1`.
- `test_api_won_endpoint`: POST `/api/leads/<id>/won` with `{"amount": 4200}`, assert 200 and response fields; assert a second POST returns 200 (update allowed); assert wrong-tenant lead returns 404.
- `test_monthly_recap_with_confirmed`: mock analytics returning `confirmed_revenue > 0`; assert recap body contains "confirmed" and no all-estimated copy.

**Effort:** L (6-8 hours across Phase 1 + Phase 2, including migration, endpoint, UI, analytics blend, tests)  
**Risk:** Medium-high. The schema migration touches `leads`, which is the most-queried table. Use `ALTER TABLE ... ADD COLUMN` (never recreate), which is safe for SQLite under production load. The analytics blending is additive — the existing `revenue` key stays in the response for backward compatibility; new keys (`confirmed_revenue`, `won_n`) are additions. The UI change is minimal and isolated to the lead card. The biggest risk is the Phase 2 analytics query introducing N+1 if `won_leads()` is called per-lead rather than in a single window query — use a single aggregate query with SUM and COUNT, same pattern as the existing `booked` query.  
**Collisions:** `db.py` (migrate + two new functions), `app.py` (new endpoint), `templates/dashboard.html` or lead card. Coordinate with any agent adding columns to `leads` in the same sprint.

---

## Summary: What This Does Not Cover

- The `$null/job` tile bug (F2 in 09-ROI-PROOF.md, app.js line 545) — explicitly owned by the Tier-0 agent.
- Progressive multi-milestone SMS (5×, 10×, 25×) noted in 08-RETENTION.md Finding 3 — a Vic briefing item approach is the right form for those, and they belong in a future growth/retention sprint after the monthly recap ships.
- All-time "running total" bar on the analytics page — valuable, deferred; the "All time" range selector already exists and serves this function once the dollar hierarchy flip (Change 1) makes the number the headline.

---

## Collision Register

| File | This plan touches | Coordinate with |
|------|-------------------|-----------------|
| `reminders.py` | Add `scan_monthly_recap()`, wire into `tick_once()` | Any agent modifying `tick_once()` or adding scan functions |
| `alerts.py` | Add `monthly_recap` kind to ALERT_KINDS, _TOGGLE_COL, format_message, _DAILY_DEDUPE_KINDS | Any agent adding alert kinds |
| `db.py` | `_migrate()` for `signed_up_at` on businesses, `won_at`/`won_amount` on leads; new functions `mark_lead_won()`, `won_leads()` | Tier-0 (owns app.js only — no collision); any agent adding migrations |
| `templates/analytics.html` | Headline text swap (Change 1), loss note element (Change 2c) | Any agent modifying analytics.html |
| `roi.py` | Append loss-framing sentence to milestone body (Change 2a) | Tier-0 (owns app.js, not roi.py — no collision) |
| `convos.py` | Append loss-framing tail to `_roi_block()` (Change 2b) | Any agent modifying `digest_email()` |
| `app.py` | New `POST /api/leads/<id>/won` endpoint (Change 4) | Any agent adding endpoints |

---

## Honest Revenue Framing Invariants (Do Not Relax)

These guardrails exist throughout the codebase and must be preserved in all changes above:

1. Revenue figures always carry "estimated" or "~" unless `won_amount` is a real owner-entered value.
2. The word "cash," "collected," or "actual" never appears in any revenue claim.
3. ROI milestones and monthly recaps gate on `compliance.a2p_ready()` — if texts didn't reach customers, no revenue claim is made.
4. The monthly recap gates on `booked >= 1` — a zero-booking month gets no recap (it would be demoralizing, not anti-churn).
5. The `roi_multiple >= 2.0` floor on the initial milestone is not lowered to trigger the recap earlier.
