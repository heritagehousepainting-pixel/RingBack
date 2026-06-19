# 08-RETENTION — Growth Engine & Moat Assessment

**Auditor lane:** Retention & the Growth Engine  
**Bar:** "More than enough to stay" — leaving should feel like leaving money on the table.  
**Date:** 2026-06-19

---

## What's Actually Built

The growth engine (`growth.py`, ~450 lines) is a declarative play engine that computes money-ranked opportunities from signals already in the DB: completed jobs, quiet quotes, past-customer timestamps, job density by zip, and trade seasonality. Six play types ship:

| Play | Trigger | Money frame | Delivery |
|------|---------|-------------|----------|
| `review_request` | Completed job ≤90 days | avg job value | Tray → approved |
| `quote_followup` | Quote quiet 24h–30d | avg job value | Tray → approved |
| `reactivation` | Quote quiet 30d+ | avg job value | Tray → approved |
| `winback` | Past customer 12–18 months out | 2× avg job value | Tray → approved |
| `referral` | Job wrapped ≤3 days ago | avg job value | Tray → approved |
| `membership` | 2+ jobs, avg value <$500 | avg job value | Tray → approved |

Plus four business-level (non-sendable) signals: `density` (3+ jobs in one zip in 14 days), `seasonal` (trade-specific pre-peak window), `financing` (ticket > trade threshold), and a `money_left_behind` total.

**Tray approval flow:** plays queue to `scheduled_messages` with `status='held'`. The owner taps "Send All" in the Growth Tray UI or replies SMS "GO." Individual plays can be skipped. The DB enforces a 30-day cross-kind frequency cap and a 12-month 2-touch ceiling per customer. Tone-risk plays (customer sent a negative keyword) always stay held even in auto mode. Win-backs require prior inbound contact (TCPA narrowing). Blocked plays (missing review link) surface in the tray without queuing.

**ROI milestone:** `roi.py` fires a one-time SMS once booked revenue hits 2× the monthly plan cost and A2P is live. The `analytics` endpoint powers an ROI page showing leads recovered, estimates booked, and estimated revenue vs plan cost.

**Weekly digest:** `convos.digest_email()` sends a plain-English summary: recovered leads, estimated revenue, capability gaps, and things Vic learned — framed as "what your AI did this week."

**Memory/learning:** `assistant_learnings`, `assistant_flags`, and `unmet_flag_contents()` accumulate owner corrections, capability gaps, and preferences that make Vic smarter per tenant over time.

---

## Findings

### FINDING 1: Review engine sends texts but can't see if they're working — zero closed-loop feedback

**WHAT:** The system sends review-request SMS via the tray and logs the `growth_touch_log` row. But there is no mechanism to track how many reviews actually land on Google, what the current star rating is, or whether the rating is trending up. The Google Places API key is wired for the business-lookup autocomplete during setup but is never used post-signup. `db.py` stores only a `review_link` string — no `review_count`, no `star_rating`, no `rating_history`.

**WHY IT MATTERS:** The review → GMB ranking → LSA leads pipeline is FirstBack's best compounding retention story. BRAIN.md states it explicitly: "300+ Google reviews drive ~1,046% more LSA leads than sub-100." If Dave never sees his star count going up or his review velocity accelerating, the causal chain (FirstBack sends texts → Google rank improves → more leads) is invisible. He just sees a tray item he approved. Without proof the reviews are landing, the growth engine feels like a cost center, not a compounding asset.

**RECOMMENDATION:** Add a monthly GBP check using the Google Places API (already credentialed) to pull current `user_ratings_total` and `rating`. Store in `businesses` as `google_review_count` and `google_star_rating` with a `review_count_updated_at` timestamp. Surface a "Your reputation" tile on the ROI page showing: reviews when you started FirstBack vs today, star rating trend, and — once reviews exceed a milestone (e.g., 25, 50, 100) — a Vic line like: "You've crossed 50 Google reviews. That's the threshold where LSA starts ranking you above contractors with fewer." This closes the loop and turns the review engine from "sending texts" into "building your Google reputation."

**Impact: HIGH** — reviews are the single most compounding asset a local contractor owns; showing the accumulation is a concrete stay reason.  
**Effort: SMALL** — the Places API call is trivial, one DB migration, one template tile.

---

### FINDING 2: Auto mode is permanently locked — the tray creates daily friction that erodes habit

**WHAT:** `settings_growth_mode()` server-side rejects `growth_mode='auto'` and coerces it to `'off'`. The L2 "7-day GO streak" unlock gate was spec'd in `PHASE5D-SPEC.md` and all four pre-build docs but was never built. There is no streak tracking, no progressive unlock UI, and no path for a trusted contractor to ever reach auto mode. The tray currently requires the owner to actively approve every batch every day indefinitely.

**WHY IT MATTERS:** The Dave test: a non-tech contractor on a Tuesday morning with three jobs, a leaking truck, and a phone face-down will approve the tray for the first two weeks then stop. Once the tap becomes a chore instead of a win, plays accumulate unreviewed and the "money on the table" frame inverts — it becomes evidence the tool isn't working. The tray is the right first mode. It is not the right permanent state. Without a graduation path, retention risk is high for power users who wanted "set and forget" and got "daily homework."

**RECOMMENDATION:** Build the L2 streak: track consecutive days the owner replies GO or taps "Send All." After 7 consecutive approvals (or configurable in `config.py`), auto-unlock `review_request` only in auto mode (the lowest-risk play — the spec already drew this line). Show the streak progress as a Vic briefing item: "5 mornings GO in a row. Two more and review requests send automatically." The graduation creates a moment of earned trust that is itself a retention hook — the owner invested seven mornings, which is data locked into their relationship with Vic.

**Impact: HIGH** — removes the primary friction path to churn for engaged users; turns daily approval from chore to investment.  
**Effort: MEDIUM** — streak table, unlock endpoint, briefing card update.

---

### FINDING 3: The ROI milestone fires once and goes silent — no compounding proof narrative

**WHAT:** `roi.py` fires a one-time SMS when booked revenue hits 2× plan cost. After that, `roi_milestone_sent_at` is set and the milestone never fires again. The ROI page shows a static tile: "paid for itself ~Nx." There is no progression (3×, 5×, 10×), no monthly check-in ("this month FirstBack recovered an estimated $2,400 in booked jobs"), and no week-over-week narrative in the weekly digest that explicitly names the month's revenue recovered.

**WHY IT MATTERS:** A contractor's cancellation decision is made in a moment of doubt — slow week, tight cash, "is this tool actually doing anything?" The antidote is a running scoreboard they didn't have to build. Right now the ROI evidence peaks at first milestone and then stops compounding in the product. The weekly digest has an ROI paragraph but it's buried in a flat email body with no visual emphasis. A contractor who opened FirstBack at month 6 and saw "this tool has booked an estimated $18,400 since you started" would not cancel. One who sees a static "5.2×" tile has no visceral sense of accumulation.

**RECOMMENDATION:** (a) Add progressive ROI milestones at 5×, 10×, 25× that each generate a Vic briefing item (not another SMS, which cheapens the signal): "FirstBack has now recovered 10x its cost. The total since you started: ~$X,XXX." (b) Add a `monthly_roi` Vic proactive to the first of each month: "Last month — N missed calls recovered, M booked, ~$X,XXX in the pipeline. Running total since day one: ~$XX,XXX." This is the key retention narrative: money that wouldn't exist without FirstBack, accumulating over time, visible in one line. (c) On the ROI page, show an "all time" bar that visually dwarfs the monthly view so the investor/retention frame beats the "is it working this week" frame.

**Impact: HIGH** — directly attacks the cancellation trigger ("is it worth it?") with compounding evidence.  
**Effort: SMALL-MEDIUM** — milestone table with multiple thresholds, monthly proactive hook in reminders.py, one template change.

---

### FINDING 4: Customer database is not surfaced as locked-in data the owner would lose

**WHAT:** FirstBack accumulates a real customer database: names, phones, addresses, job history, message threads, booking history. `growth_candidates()` queries this per run. But the owner never sees it framed as *their customer list* — a portable, valuable, growing asset. There is no "Customers" view showing total customers served, repeat customers, customer lifetime value, or "Dave's Top 10 by job value." When a contractor considers cancelling, they don't feel they'd lose anything because the database accumulation is invisible.

**WHY IT MATTERS:** A contractor who has 200 customers in FirstBack with job history, notes, and SMS threads has real switching costs — re-entering that history elsewhere is painful. But if they don't know the database exists as a coherent asset, the switching cost is invisible. This is the strongest mechanical moat: real data that accumulates with use and is genuinely hard to leave behind. Right now it's a backend query used only by the growth engine.

**RECOMMENDATION:** Add a `/customers` page (a thin read on existing lead/appointment data already in DB) showing: total unique customers served, repeat customers (booked 2+ times), estimated total revenue served (not just recovered by FirstBack — their whole job history since signup), and a top-customers list by job value or frequency. No new data — just a view of what's already there. Vic can reference it: "You've served 47 customers through FirstBack. Your top three have each booked twice." The frame shifts from "a texting tool" to "the system that knows your customers."

**Impact: HIGH** — makes the accumulated customer history visible and tangible, raising switching cost perception.  
**Effort: SMALL** — existing data, new template, one DB query grouping leads by booking count.

---

### FINDING 5: Referral play asks every customer the same way — no neighborhood/density intelligence applied

**WHAT:** `_copy_referral()` sends: "glad we could help. If a neighbor ever needs the same work, have them call us." This is the same message regardless of whether there are 0 or 5 other jobs in the same zip. The density play (`density`) already detects 3+ jobs in a zip and suggests a door-hanger campaign, but this signal is never piped into the referral copy. The referral fires within 3 days of job close, which is right, but the message doesn't leverage the social proof the density data could carry.

**WHY IT MATTERS:** This is a missed compounding moment. A referral ask that says "We just wrapped three jobs on your block this month — if anyone asks, tell them to call us" is materially more persuasive than a generic ask, and it's data FirstBack already has. It also primes the owner to see the density signal as a real business event ("my customers are referring on their own block"), not just a dashboard tile.

**RECOMMENDATION:** When the referral play fires for a customer in a zip with 2+ other recent jobs, upgrade the draft: "We've been busy on your block this month — if a neighbor needs [trade], have them reach out. We'll take care of them." This requires piping `zip_counts` from the `plays()` loop into the referral `_opp()` call, which is already computed in the same function. Minor copy branch, no new data.

**Impact: MEDIUM** — higher referral response rate, but secondary to the bigger structural gaps.  
**Effort: SMALL** — one-function change inside `plays()`, already has the data.

---

### FINDING 6: No seasonal campaign actually sends to past customers — it's a suggestion, not a campaign

**WHAT:** The `seasonal` play is non-sendable (`sendable=False`) — it surfaces in the growth feed as "Offer AC tune-ups to past customers now" but has no action beyond "show my leads." There is no mechanism to actually send a seasonal message to the cohort of past customers for that trade. The `growth_candidates()` query already knows who has booked HVAC jobs. The seasonal play is advisory, not operational.

**WHY IT MATTERS:** Seasonal campaigns are how a solo HVAC contractor fills their spring calendar without spending on ads. "I market before the surge" is the highest-leverage, lowest-cost play in trades marketing (BRAIN.md: "market before the surge"). Right now FirstBack surfaces the insight but hands the work back to Dave. The insight without the send is a dashboard feature — the thing the product explicitly is not supposed to be.

**RECOMMENDATION:** Convert the seasonal play from advisory to sendable for opted-in businesses. The seasonal cohort is all past customers (status='booked', last job >3 months ago) for the trade. Draft: "It's that time of year — [biz name] has openings for [service] before the rush. Reply and we'll get you in." Gate it in the tray (never auto) so Dave approves a bulk send, not individual ones. This requires a tray UI that shows "24 customers would get this" and a batch-send mechanism. The seasonal campaign that fills his spring calendar is the retention moment that makes cancelling in March feel like sabotaging himself.

**Impact: HIGH** — highest-leverage plays for trades revenue; converts the most valuable advisory insight into actual business value.  
**Effort: MEDIUM** — cohort query, bulk draft UI in tray, batch send against the existing `scheduled_messages` spine.

---

## Top 3 Retention Moves That Make Cancellation Feel Stupid

1. **Close the review loop (Finding 1):** Show the owner their Google review count and star rating going up month over month, attributable to FirstBack's review texts. "You had 14 Google reviews when you signed up. You have 31 now." That's a reputation asset they built with this tool. Leaving means the review requests stop and the pipeline dries.

2. **Make the customer database visible (Finding 4):** Surface "47 customers served, 12 repeat, ~$94,000 in lifetime jobs" as a Customers page. A contractor who can see their customer history in one place — with job notes, message threads, and booking records — has real switching cost, not just a sentimental attachment. They know cancellation means losing that organized history.

3. **Compounding ROI proof (Finding 3):** Progressive milestones (5×, 10×, 25×) plus a monthly "what FirstBack recovered for you this month" briefing item. Cancellation means losing the only tool that shows them, in plain language, what their missed calls cost them and what got recovered. The running total is the weapon against "is this worth $99."

---

## Verdict on Retention / Moat Strength

**Moat score: 5/10.** The growth engine is technically sound and compliance-hardened — the plays are right, the signals are real, the tray approval flow is appropriately cautious. But the moat is currently invisible. The compounding assets (customer database, Google reputation, ROI accumulation) exist in the code and never surface as *things you'd lose if you left.* The review engine sends texts but can't prove reviews are landing. The ROI milestone fires once and goes quiet. The tray is correct friction for month one but unyielding friction permanently. A motivated competitor could poach a six-month user today because nothing is visibly stickier than month one. The three moves above — close the review loop, make the database tangible, show the running ROI — are all achievable with existing data and would raise this to a genuine 8/10 moat where leaving genuinely feels like financial self-harm.
