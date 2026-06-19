# Auditor 09 — Analytics / ROI / Proof-of-Value

**Lane:** Does the owner feel "this made me $X this month" in a way that is gut-level, credible, and cancellation-proof?

---

## What was reviewed

- `roi.py` — milestone SMS logic
- `db.py` `analytics()` — the data model powering all ROI numbers
- `config.py` — `PLAN_COST_MONTHLY`, `TRADE_JOB_VALUE_DEFAULTS`
- `templates/analytics.html` + `static/app.js` (ROI page + JS tile renderer)
- `alerts.py` — daily digest, milestone alert copy
- `convos.py` `_roi_block()` / `digest_email()` — weekly digest ROI block
- Test suites: `test_roi_milestone.py`, `test_f12_analytics.py`, `test_f12_digest.py`, `test_daily_digest.py`

---

## Findings

---

### F1 — The headline tile says "paid for itself ~Nx" but buries the dollar figure one line below — impact MEDIUM, effort S

**WHAT:** The ROI headline tile (`roi-headline`) displays "paid for itself ~18x" as the primary value and "estimated $32,400 in booked jobs" as secondary sub-text. Visually the multiplier is the hero.

**WHY it matters:** Dave the painter does not think in multiples. He thinks in dollars he almost lost. The sentence that pre-empts cancellation is "you'd have missed an estimated $32,400 this month without FirstBack" — not an abstract ratio. The multiplier is validating confirmation copy, not the hook.

**Recommendation:** Flip the visual hierarchy: `$32,400 estimated recovered` as the large hero number, `paid for itself ~18x this month` as a single supporting line below it. One-line CSS change on `.roi-headline-value` / `.roi-headline-sub`.

---

### F2 — The "Est. revenue recovered" tile shows the wrong sub-label when avg_source is industry_default — impact HIGH, effort S

**WHAT:** In `app.js` line 545:
```js
tile(hasRev ? money(t.revenue) : "—", "Est. revenue recovered",
     hasRev ? "at " + money(d.avg_job_value) + "/job" : "Set avg job value in Settings",
     hasRev ? "good" : "");
```
`d.avg_job_value` is `owner_avg` from the API response. When the owner has not set their own avg_job_value, `owner_avg` is `null` (see `db.analytics()` line 3034: `"avg_job_value": owner_avg`). So the sub-label reads "at $null/job" or "at —/job", which is broken and erodes trust instantly.

When `avg_source === "industry_default"`, the tile should read something like `"industry estimate for painting"` so the owner understands what the number is based on — and why they should go set their real value to improve accuracy.

**Recommendation:** In `renderTiles()`, branch on `d.avg_source`:
```js
const jobSub = d.avg_source === "owner"
  ? "at " + money(d.avg_job_value) + "/job"
  : "industry avg — set yours in Settings";
tile(hasRev ? money(t.revenue) : "—", "Est. revenue recovered",
     hasRev ? jobSub : "Set avg job value in Settings",
     hasRev ? "good" : "");
```
This is a ~3-line JS fix. It also doubles as a gentle persistent nudge to complete the most valuable personalization step.

---

### F3 — No "what you would have missed" framing anywhere — impact HIGH, effort M

**WHAT:** The product shows how much was recovered. It never frames what an equivalent missed-call rate would have cost without FirstBack. There is no "before vs. after" context anywhere — not on the analytics page, not in the weekly digest, not in the milestone SMS.

**WHY it matters:** Dave doesn't cancel because the numbers are bad. He cancels because the numbers feel abstract. "You recovered $3,200 this month" competes with silence. "Without FirstBack, that $3,200 estimate walks out the door" forces a concrete comparison. The psychological anchor is "loss avoidance," not gain. The milestone SMS (`roi.py`) says "FirstBack has booked an estimated $X in jobs for you so far — about Nx what it costs." That is the closest thing to framing but it still only shows the recovered side.

**Recommendation:** Add one sentence to the milestone SMS body and to the weekly digest ROI block:
- Milestone: `"Without FirstBack, those calls go unanswered and that job likely goes to a competitor."`
- Weekly digest: append `"That's revenue that would have walked without a text-back."`

On the analytics page, add a small contextual aside beneath the headline tile: `"Without text-back, missed calls convert at ~0%."`

---

### F4 — No monthly/quarterly "here's what FirstBack did for you" recap — impact HIGH, effort M

**WHAT:** The daily digest fires at 8am about today's queue. The weekly digest covers conversations/gaps. The milestone SMS fires once, lifetime. There is no monthly or first-30-days retrospective that says: "You've been on FirstBack for 30 days. Here's what happened: 14 missed calls answered, 4 estimates booked, ~$12,800 recovered."

**WHY it matters:** The moment most likely to trigger cancellation is the day before or the day of renewal. An automated 30-day recap arriving the morning of day 28–30 pre-empts the "is this worth it?" thought with concrete evidence. Without it, the decision to stay relies entirely on the owner's memory of isolated alert pings.

**Recommendation:** Add a `scan_monthly_recap()` function in `reminders.py` analogous to `scan_daily_digest()`. It fires once per billing month (or 30-day window from signup), uses `db.analytics(days=30)`, and sends the owner a formatted SMS + email: `"Your FirstBack month: 14 missed calls rescued, 4 estimates booked, ~$12,800 estimated — that's 129x what it costs. Reply STATS to see the full breakdown."` Gate it on A2P approved + at least 1 booking (same as the milestone). Dedupe over 26 days.

---

### F5 — No real-dollar attribution when a job actually closes — impact MEDIUM, effort L

**WHAT:** Revenue is always and only an estimate: `booked_n * avg_job_value`. There is no mechanism for the owner to say "Maria's job closed for $4,200" and have that concrete number flow back into the ROI display. The system doesn't even have a lead status of `won` or `closed`.

**WHY it matters:** If an owner sets `avg_job_value = $3,200` and a painting job actually closes for $4,200, the app underreports. More importantly, real closed-job numbers are 100% credible — no "estimate" caveat needed. Over time, having real revenue figures that the owner themselves entered replaces doubt with proof.

**Recommendation (phased):** Phase 1 — add a "Mark as won ($___)" action on the lead card; record `won_at` and `won_amount` on the leads table. Phase 2 — update `db.analytics()` to prefer the sum of `won_amount` for won leads over `booked_n * avg_job_value`. The analytics page then shows "confirmed revenue: $X" alongside "estimated pipeline: $Y." The ROI tile becomes far more compelling as real numbers accumulate. This is a longer build (L effort) but it is the strongest possible proof statement.

---

## What works well (do not break)

- **Honesty gates are solid.** The A2P gate on the milestone SMS, the `source='missed_call'` filter on analytics, the "estimate" labeling everywhere, and the `roi_multiple >= 2.0` floor before the milestone fires — all of these are well-considered. Do not loosen them for the sake of a bigger headline number.
- **The milestone SMS body is credible.** It distinguishes owner avg vs. industry default and never says "cash" or "collected." This is the right approach.
- **The daily digest is smart and deduped.** The 8am unified digest firing once per day (26h dedup window, empty-state suppression, no auto-release of held plays) is production-grade.
- **The weekly digest ROI block gates correctly on A2P.** The pending-tenant path returns an honest non-dollar placeholder instead of a false claim.
- **Industry defaults by trade are reasonable.** $3,200 for painting, $8,500 for roofing, $1,800 for plumbing — these are defensible national 2024-25 benchmarks with an honest $800 floor for unknowns.

---

## What single thing most strengthens "obviously worth it" proof?

**The monthly recap (F4).** Arriving on day 28, before renewal, it converts vague goodwill into a concrete dollar statement the owner just received in their pocket. It costs nothing to deliver, it reuses existing `analytics()` infrastructure, and it directly pre-empts the cancellation moment. Without it, all the other ROI machinery fires once (the milestone) or daily (digest), but nothing lands at the exact moment the owner is deciding whether to stay.

---

## Verdict

The analytics foundation is honest and technically sound. The milestone SMS and daily digest work correctly. But the proof-of-value story has two critical gaps: it never frames what the owner would have lost without the product (loss-avoidance framing), and it has no monthly recap timed to pre-empt renewal-cancellation. The ROI tile also has a live bug where `avg_job_value` shows as null when using industry defaults, which erodes trust at first sight. Fix the JS bug first (S effort, high trust impact), then build the monthly recap (M effort, highest retention impact).

**Score: 5/10.** The math is right and the honesty guards are strong, but the emotional proof — "you'd be crazy to cancel this" — is absent at the moments that matter.
