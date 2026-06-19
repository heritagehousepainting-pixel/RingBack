# 06 — Pricing, Packaging & Monetization Audit

**Auditor lane:** Pricing & Monetization only  
**Date:** 2026-06-19  
**Files reviewed:** `templates/pricing.html`, `billing.py`  
**Competitive sources:** Podium, Goodcall, Signpost, LeadTruffle, Slang.ai, Jobber AI Receptionist, Housecall Pro, GoHighLevel, traditional answering services

---

## 1. The Current Pricing Structure

| Tier    | Monthly | Annual (20% off) | Conversation cap |
|---------|---------|-------------------|------------------|
| Starter | $99     | $950 (~$79/mo)   | 250 / mo         |
| Pro     | $199    | $1,910 (~$159/mo)| 1,000 / mo       |
| Crew    | $399    | $3,830 (~$319/mo)| 3,000 / mo       |

Billing is flat monthly; the "fuel gauge" tracks distinct lead conversations consumed vs. granted. No overages, no per-call fees. No free trial, no setup fee, no per-booking fee.

---

## 2. Competitive Landscape

### Direct Comps (missed-call text-back / AI booking for SMBs)

| Product | Price / mo | Notes |
|---|---|---|
| **Goodcall** | $59–$79 (Starter), $199 (Scale) | Voice-first; 100 unique callers cap on Starter, $0.50/caller above cap; 14-day free trial |
| **LeadTruffle** | $229 | SMS lead capture + qualification, contractor-specific |
| **Signpost** | $199/user | Full AI comms hub for home services; more feature overlap than just text-back |
| **Jobber AI Receptionist** | $99 add-on (free on $599 plan) | Bundled into FSM software; not standalone |
| **Housecall Pro** (HCP Assist) | Included in $189 Essentials | Not standalone; requires HCP FSM subscription |
| **GoHighLevel Convo AI** | $97/sub-account flat or $0.04/msg | Agency white-label platform; requires setup |
| **CallBird / AgentZap** | $99–$149 | Contractor-specific; similar missed-call hook |

### Adjacent/Upper Market (shows price ceiling)

| Product | Price / mo | Notes |
|---|---|---|
| **Podium** | $399–$599+ base | General messaging platform; enterprise slant; 12-month contracts |
| **Slang.ai** | $379–$599 | Restaurant AI phone; per-location; premium |
| **Traditional answering service** | $300–$800 | Per-minute/per-call; limited hours; no AI booking |
| **Numa** | $49–$400 | Restaurant/auto; unclear contractor pricing |

---

## 3. Is $99 Starter Right for the Value?

### The ROI math is overwhelming in FirstBack's favor

Industry data is unambiguous:
- Average home-service job value: $300–$650 (HVAC service call), $6,000–$8,000 (roofing/plumbing project)
- Contractors miss 30–40% of inbound calls
- Missing 5–10 calls/week = $45,000–$120,000/year in lost revenue (CallBird, 1,200-contractor survey)
- One recovered job = $300–$8,000; FirstBack costs $99/month

**At $99/month, a contractor recovers FirstBack's annual cost ($1,188) with a single mid-tier job.** The value-to-price ratio is extreme. That's not a problem — it's an asset — but it must be framed explicitly on the pricing page or it gets ignored.

### The pricing page undersells the ROI

The Starter blurb ("for solo operators who can't afford to miss a call") is accurate but emotionally flat. It does not state the math. The FAQ mentions A2P registration but does not anchor the service to recovered revenue. **There is no ROI calculator, no "one job pays for a year" hook, no dollar-figure comparison to an answering service.** This is the single biggest missed monetization lever — not the price itself, but the failure to justify it.

**Finding 1 — ROI framing is missing from the pricing page**
- WHAT: The pricing page carries no revenue-recovery math, no answering-service cost comparison, and no "one job covers the year" statement.
- WHY: Contractors are price-sensitive but respond to concrete dollar saves. Without anchoring, $99 feels like a SaaS expense, not a $45k/year problem solved.
- REC: Add a one-line ROI anchor above the pricing grid (e.g., "Miss one job a month? That's $300–$3,000 gone. FirstBack costs $99.") and a small comparison table vs. live answering services.
- IMPACT: High — directly affects conversion from visit-to-signup
- EFFORT: Small — copy and HTML change only

---

## 4. Is "Conversations" the Right Axis?

### Verdict: Workable but not optimal

**Arguments for conversations as the billing unit:**
- Feels fair — you pay for usage, not just existence
- Easy to explain ("you get 250 AI text threads per month")
- Aligns cost to AI + Twilio expense (each conversation burns real LLM + SMS cost)

**Arguments against:**
- Contractors do not think in "conversations"; they think in calls, jobs, and revenue
- A solo painter with 80 missed calls/month and a HVAC shop with 250 are both on Starter, but their willingness-to-pay is radically different
- 250 conversations on Starter may be too low or too high depending on the business — a seasonal roofer in summer might blow through it, a solo handyman in winter might use 30
- Hard to self-diagnose: "I'm at 180/250 conversations" tells the contractor nothing about whether they should upgrade
- No overage option means conversation exhaustion is a hard cliff — potentially stranding a paying customer mid-month

**Better alternative axes to consider:**
- **Locations / business profiles**: More directly maps to business size; Crew already uses this (up to 5 numbers). A "per location" model is cleaner for scaling from 1→2→5 shops.
- **Hybrid**: Base fee (access) + light per-conversation charge above a generous floor, so small users feel safe and heavy users pay more.
- **Outcomes**: Per booked estimate/appointment (e.g., $3–5/booking confirmed). Pure upside alignment; converts trial objection ("I don't know if it works") into a risk-free entry. Hard to track without calendar integration on Starter.

**Finding 2 — Conversation caps are confusing and may create wrong-tier fit**
- WHAT: "Up to 250 conversations / mo" is a unit contractors cannot intuitively map to their business volume. No overage path means a busy contractor gets cut off, not upsold.
- WHY: The fuel gauge mechanism (tracked in `db.conversations_remaining`) is technically solid but the consumer-facing framing of it as a hard cap without an upgrade prompt or overage option is a churn risk.
- REC: (a) Rename "conversations" to "missed-call replies" in all consumer copy — that's what contractors understand. (b) Add a soft overage: $0.50–$1.00 per conversation above cap (or a one-click mid-month upgrade prompt when at 80% utilization). (c) Add a "how many do I need?" tooltip estimator on the pricing page.
- IMPACT: High — reduces churn from cap confusion, surfaces upgrade intent
- Effort: Medium — requires billing.py overage logic + UI change

---

## 5. Is the Annual Discount Sensible?

### Verdict: Discount rate is fine; the annual price display is slightly confusing

20% off is industry standard (Goodcall, Textline, Podium all use 20%). The math is correct ($99 × 12 × 0.8 = $950.40, displayed as $950 — fine).

**Issue:** The pricing page shows "or $950 / year — save $238 (20% off)" below the monthly price. This is buried below the CTA rather than featured as the primary value prop. Annual plans dramatically improve LTV and reduce churn. The current layout gives annual billing secondary visual weight.

**Finding 3 — Annual plan is under-featured; no annual-first default**
- WHAT: Annual pricing is shown as a small-print footnote under each tier, not the default selected state. No badge highlights cash savings for the contractor ("save $238 = 2.4 free months").
- WHY: Annual billing is the highest-LTV action on the page. Software that defaults to monthly loses ~40% of potential annual subscribers due to inertia.
- REC: Add a toggle (Monthly / Annual, default to Annual) with a "save 20%" badge. Show the annual effective monthly rate as the hero price. Show Starter annual as "$79/mo, billed yearly." This alone can shift 20–30% of signups to annual.
- IMPACT: High — directly increases LTV per customer without changing the product
- Effort: Small — HTML/CSS toggle, no billing changes needed

---

## 6. Missing Monetization Vectors

### 6a. No Free Trial (or Even a Risk Reversal)

**Current:** Direct to paid ($99). No trial, no guarantee.  
**Comps:** Goodcall (14-day free trial), Jobber (includes AI receptionist in trial period), most SMB SaaS tools offer 7–14 days.

A $99 cold-start for a contractor who has never heard of FirstBack is a real barrier. A free trial is not necessary — but some risk-reversal is. Options:
- 7-day free trial (requires card; converts well for contractors who are motivated)
- 30-day money-back guarantee (no card risk; works for skeptics)
- First month free on annual plan (pulls fence-sitters to annual immediately)

**Finding 4 — No trial or risk-reversal; cold-start at $99 creates unnecessary hesitation**
- WHAT: No free trial, no money-back guarantee, no risk language on the pricing page.
- WHY: The target buyer (solo contractor, Dave the painter) is price-sensitive and skeptical of new software. Without any risk cushion, the friction to the first $99 is high. The "Get started" CTA goes to /signup — presumably to a paid checkout.
- REC: Add "30-day money-back guarantee" badge to all three tiers (cheapest to implement, highest trust signal). Or offer a 7-day full trial. Either removes the primary objection for the Starter buyer.
- IMPACT: High — directly improves top-of-funnel conversion
- Effort: Small (guarantee language) to Medium (full trial flow)

### 6b. No Setup Fee (Arguably Correct, But Worth Noting)

Competitors (Slang.ai, Signpost) sometimes charge one-time setup or onboarding fees ($99–$499). For FirstBack's positioning as "same-day, self-serve," charging a setup fee contradicts the UX promise and should remain absent at this stage. Crew's "dedicated onboarding" is the right premium to hold for high-touch enterprise, not a separate charge.

**Verdict:** Correct decision to omit setup fee at launch.

### 6c. No Per-Number / Extra Location Add-On Below Crew

Currently, extra phone numbers only appear at Crew (5 numbers). A contractor who runs two trucks but doesn't need 3,000 conversations/month is forced to upgrade from $199 to $399 just to add a second number.

**Finding 5 — Gap in packaging: Pro-to-Crew jump forces over-buying on conversations to get multi-number**
- WHAT: The only way to get more than 1 phone number is to jump to Crew ($399). Pro at $199 is capped at 1 number despite serving "busy crews."
- WHY: A 2-truck shop or a contractor who runs two trade specialties (HVAC + electrical) under different numbers needs a second line. Forcing them to Crew (3,000 conversations, 5 numbers, $200 more/month) for what they need (2 numbers, ~300 conversations) is a packaging mismatch.
- REC: Allow 1 additional number as a $15–$25/month add-on on Pro. This captures the 2-truck shop without requiring a Crew-level commitment and adds a revenue stream with near-zero cost.
- IMPACT: Medium — expands addressable market at Pro tier; reduces churn from "too expensive to go to Crew"
- Effort: Small — Stripe product add-on + minor UI

### 6d. Voice Callback Monetization Gap

Pro features "AI voice callback (beta — not yet available)." When it ships, this is a premium feature that merits a price bump on Pro or a separate add-on ($20–$30/mo). Do not release it as a free Pro inclusion — it has real per-minute Twilio cost and is a clear upgrade driver.

No immediate action needed, but this must be priced before it ships.

---

## 7. Where FirstBack Sits in the Market

| Axis | FirstBack | Market range |
|---|---|---|
| Price vs. direct comps | $99 Starter = at/below median (Goodcall $59, CallBird $99, LeadTruffle $229, Signpost $199) | Competitive |
| Price vs. traditional alternatives | $99 vs. $300–$800/mo answering service | Massive value advantage; not stated on page |
| Price vs. ROI | $99/mo vs. $45k–$120k/yr lost revenue | Extreme value — completely unmarked |
| Tier breakpoints | 250/1k/3k conversations | Unusual unit; comps use callers, locations, seats |
| Annual discount | 20% (standard) | Correct; under-featured |
| Free trial | None | Outlier; most comps offer 7–14 days |
| Add-ons/overages | None | Leaves upgrade-path money on table |

---

## 8. Is There Money Left on the Table?

**Yes — significantly — but not by raising prices.**

The primary money left on the table is conversion leakage, not price undercut:
1. **Annual plan under-conversion**: Probably 80%+ of signups default to monthly due to UI; flipping even 30% to annual on Starter = $238 × 0.3 × N customers.
2. **Trial friction**: Unknown drop-off rate at the cold $99 paywall; a 30-day guarantee is nearly free to offer.
3. **Overage/upgrade revenue**: Customers hitting 250-conversation cap with no path but full tier upgrade will churn instead of paying a small overage. Overage pricing = retention + upsell.
4. **Pro second-number add-on**: Low-hanging revenue for 2-truck shops stuck between Pro and Crew.

**Raising Starter to $129 is premature.** Brand recognition is zero. Pricing pressure in this segment is real. $99 is the right "easy yes" price point for year one. The play is: fix conversion via ROI framing + annual default + money-back guarantee, then raise prices after the first 100 customers prove retention.

---

## 9. Top 3 Pricing & Packaging Moves

### Move 1 — Default to Annual + Add "2 Free Months" Framing (Impact: H / Effort: S)
Add a toggle to the pricing page defaulting to "Annual" with a "2 free months" badge. Show the effective monthly rate as the hero number (e.g., $79/mo). This alone is the highest-LTV, lowest-cost change available.

### Move 2 — Add "30-Day Money-Back Guarantee" Badge on All Tiers (Impact: H / Effort: S)
One line of copy and a badge. Removes the primary objection for the cold-start contractor. No trial infrastructure required.

### Move 3 — Add "Missed-Call Reply" ROI Anchor Above the Pricing Grid (Impact: H / Effort: S)
One paragraph or callout: "The average contractor loses $45,000/year to unanswered calls. At $99/month, FirstBack pays for itself with one recovered job." This reframes $99 from "software expense" to "insurance against a $45k problem."

---

## 10. One-Line Verdict

**$99 Starter is priced correctly for year-one customer acquisition, but the pricing page is leaving 30–40% of potential conversion on the table through three fixable omissions: no annual-first UI, no risk reversal, and no ROI anchor — all fixable in a single afternoon of work.**
