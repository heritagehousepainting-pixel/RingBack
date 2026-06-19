# Plan 09 — Pricing Page + Marketing-Site Conversion + SEO + Positioning

**Workstream:** Pricing page, marketing-site conversion, SEO, positioning  
**Agent:** Lane 9 of 10  
**Date:** 2026-06-19  
**Status:** BUILD-READY plan — READ-ONLY, no code changed  
**Sources read:** 06-PRICING.md, 10-MARKETING-SITE.md, 11-COMPETITIVE.md, templates/pricing.html, templates/marketing_base.html, templates/landing.html, templates/customers.html, templates/solutions.html, billing.py

---

## Tier 0 — Owned by the dedicated Tier-0 agent (DO NOT re-plan here)

The following are small honesty/correction fixes already assigned to the Tier-0 agent. This plan does not re-plan them; it references them as dependencies where they interact with copy strategy:

- Auth page self-review stars (auth.html) — remove stars/`-- FirstBack` byline
- solutions.html live-voice claim — hedge to "coming soon"
- product.html voice checkmarks — change to dashed/coming-soon indicator
- `/simulator` link on hero CTA → `/demo` (login-gate fix)
- `/simulator` link in nav → `/demo`

---

## Priority Order (Quick wins first, highest impact lowest effort)

| # | Change | File(s) | Effort | Impact |
|---|--------|---------|--------|--------|
| 1 | Annual toggle + "2 months free" default | pricing.html | S | H |
| 2 | ROI anchor above pricing grid | pricing.html | S | H |
| 3 | 30-day money-back guarantee badge | pricing.html | S | H |
| 4 | Rename "conversations" → "missed-call replies" | pricing.html | S | M |
| 5 | SEO/OG meta block in marketing_base + per-page fills | marketing_base.html + pricing.html + landing.html + solutions.html + customers.html | S | H |
| 6 | Hero/positioning reframe: outcome-first copy | landing.html | S | H |
| 7 | Testimonial pipeline: Heritage dogfood slot + honest mechanism | customers.html + landing.html | M | H |
| 8 | $20/mo extra-number add-on on Pro (pricing page surface) | pricing.html | S | M |
| 9 | Soft-overage path: UI note + billing.py hook | pricing.html + billing.py | M | M |
| 10 | /customers nav dead-end remediation | customers.html + marketing_base.html | S | M |

---

## Change 1 — Annual Toggle Defaulting to Annual, "2 Months Free" Badge

### (a) What and why

The pricing page displays annual pricing as a small footnote below each tier's monthly price. Annual subscriptions are the highest-LTV, lowest-churn action on the page; defaulting to monthly loses 30–40% of potential annual subscribers to inertia. Billing.py already supports both intervals (`PRICE_IDS` keyed by `(plan, "month")` and `(plan, "year")`). No billing changes needed — this is purely a UI/copy change.

### (b) Exact template + approach

**File:** `templates/pricing.html`

Replace the static price display with a toggle-driven layout. The toggle must:
- Default to `annual` state on page load
- Switch displayed price between monthly rate and effective monthly rate on annual (e.g., "$79/mo" for Starter annual)
- Show a badge on the toggle: `2 months free` (positioned next to "Annual")
- Show the annual total below the effective monthly rate: "billed $950/year"

**Copy for toggle labels:**
```
Monthly       Annual  [2 months free]
```

**Effective monthly rates to display (annual-first):**
- Starter: $79/mo, billed $950/year — save $238
- Pro: $159/mo, billed $1,910/year — save $478
- Crew: $319/mo, billed $3,830/year — save $958

**Implementation approach (no JS framework needed):**

Add a `<div class="mk-plan-toggle">` above the `.mk-price-grid`. Use two radio-style buttons (`data-plan="monthly"` / `data-plan="annual"`) that add/remove a class on `.mk-price-grid` (`[data-billing="annual"]`). Two sets of `.price` elements per card (`.price-monthly` and `.price-annual`), toggled via CSS: `[data-billing="monthly"] .price-annual { display:none }` and vice versa.

**Copy change to price-annual sub-elements:**  
Change from: `or <strong>$950 / year</strong> &mdash; save $238 (20% off)`  
To annual primary display: `<span class="amount">$79</span><span class="per">/ mo</span>` + sub-line `Billed $950/year &mdash; save $238`

**Badge HTML (beside Annual toggle label):**
```html
<span class="mk-save-badge">2 months free</span>
```

### (c) How to verify

Load `/pricing`. Default state should show annual prices ($79/$159/$319/mo). Clicking "Monthly" should flip to $99/$199/$399. Browser with JS disabled should fall back gracefully (show monthly prices statically). Annual CTA href should pass `?interval=annual` or the Stripe checkout uses the annual Price ID — confirm `create_checkout_session` in `billing.py` receives `interval="year"` when annual is selected (requires a small form field or URL param on the `/signup` link, e.g., `href="/signup?plan=starter&interval=year"`).

### (d) Effort

**Small** — HTML/CSS toggle, no billing changes, ~2–3 hours including wiring the CTA URLs.

### (e) Risk and collisions

- CTA links must pass `interval` to the signup/checkout flow; if `/signup` ignores the param today, the toggle is cosmetic only. Verify `billing.py` `create_checkout_session` param is surfaced through the signup route before shipping.
- No collision with Tier-0 agent (different section of pricing.html).

---

## Change 2 — ROI Anchor Above the Pricing Grid

### (a) What and why

The pricing page has zero revenue-recovery framing. A contractor who lands cold sees "$99/month" as a SaaS expense, not insurance against a $45,000/year problem. The ROI math is decisive: one recovered mid-tier job ($500–$2,000) covers a year of Starter. This framing must appear before the price grid — not below it.

Comparison to answering services is equally powerful: traditional answering services cost $300–$800/month with no AI booking. FirstBack at $99 is 3–8x cheaper and actually books the job.

### (b) Exact template + approach

**File:** `templates/pricing.html`

Insert a new section between `<header class="mk-head">` and `<section class="mk-section">` (the price grid section):

```html
<section class="mk-section mk-roi-anchor" style="padding-top:0;padding-bottom:0">
  <div class="mk-wrap">
    <div class="mk-roi-strip">
      <div class="mk-roi-stat">
        <span class="roi-num">$45K+</span>
        <span class="roi-label">average revenue lost per year to unanswered calls<sup>*</sup></span>
      </div>
      <div class="mk-roi-vs">vs.</div>
      <div class="mk-roi-stat">
        <span class="roi-num">$99<span style="font-size:1rem;font-weight:500">/mo</span></span>
        <span class="roi-label">FirstBack Starter — one recovered job pays the year</span>
      </div>
      <div class="mk-roi-vs">vs.</div>
      <div class="mk-roi-stat">
        <span class="roi-num">$300–$800</span>
        <span class="roi-label">traditional answering service — per month, no AI booking</span>
      </div>
    </div>
    <p class="mk-roi-footnote"><sup>*</sup>Based on contractors missing 5–10 calls/week at an average job value of $300–$1,500. One recovered job typically covers a year of FirstBack.</p>
  </div>
</section>
```

**Founder honesty rule:** The footnote is mandatory. It cites the underlying math, not a fabricated study. The $45K figure comes from the 06-PRICING.md audit (CallBird 1,200-contractor survey baseline). If the founder wants more conservative framing, use: "Miss one job a month? At an average job value of $300–$1,500, FirstBack pays for itself — every month."

**Alternative minimal copy (if the strip feels too heavy):**

Add to the existing `<p class="mk-lead">` in the header:

> "The average contractor loses $45,000 a year to missed calls. At $99/month, one recovered job covers FirstBack's entire annual cost."

### (c) How to verify

Load `/pricing`. Before the price cards, the ROI comparison must be visible without scrolling on desktop (1280px). On mobile it should stack vertically. Check no layout breaks.

### (d) Effort

**Small** — markup + CSS only, ~1–2 hours.

### (e) Risk and collisions

- If the ROI claim number ($45K) is challenged, the footnote defends it. Do not remove the footnote.
- No collision with other agents.

---

## Change 3 — 30-Day Money-Back Guarantee Badge on All Tiers

### (a) What and why

No free trial, no risk reversal, cold start at $99. The primary objection from a solo contractor is "what if it doesn't work for my roofing business?" Cancel-anytime is present but buried. A money-back guarantee removes the suitability objection without requiring trial infrastructure.

This is a positioning and copy decision, not a billing system change. The guarantee must be displayed prominently on each tier card and noted in the FAQ.

### (b) Exact template + approach

**File:** `templates/pricing.html`

Add a guarantee badge below each CTA button in all three tier cards:

```html
<p class="mk-guarantee">
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" style="width:15px;height:15px;vertical-align:-2px"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>
  30-day money-back guarantee
</p>
```

Style: small, secondary color, shield icon. Not a heavy badge — a quiet trust line beneath the CTA.

**Add a new FAQ entry** below "What if I want to cancel?":

```html
<details>
  <summary>Is there a money-back guarantee?</summary>
  <p>Yes. If FirstBack isn't booking jobs for you within the first 30 days, we'll refund your first month — no questions asked. Just email us. We'd rather earn your business than keep a month's payment from someone it didn't work for.</p>
</details>
```

**Founder note:** This commits the business to a real guarantee. Confirm the founder is operationally ready to honor it before shipping. Do not add it as copy without that confirmation — this falls under the no-overclaiming rule. If not ready to offer a guarantee, the alternative is: "30-day setup support. If you need help in your first month, we're on it."

### (c) How to verify

Load `/pricing`. Each tier card has the shield + "30-day money-back guarantee" line below its CTA. FAQ has the refund policy entry. grep pricing.html for "guarantee" — should return 4 hits (3 cards + 1 FAQ).

### (d) Effort

**Small** — copy + minor HTML, ~1 hour. The real effort is the founder decision to commit to the guarantee.

### (e) Risk and collisions

- **Decision gate:** Founder must confirm the guarantee policy before this ships. It is not a cosmetic change — it's a promise.
- If the guarantee is not approved, substitute with "Cancel anytime, no fee" moved directly under each CTA (currently only at FAQ level).
- No collision with other agents.

---

## Change 4 — Rename "conversations" to "missed-call replies" in Pricing Copy

### (a) What and why

"Up to 250 conversations / mo" is opaque to a contractor. They don't count conversations — they count missed calls. "Missed-call replies" maps directly to the trigger event they understand and links the limit to the product's core promise. This is a copy rename only; the underlying billing unit does not change.

### (b) Exact template + approach

**File:** `templates/pricing.html`

Three replacements in the tier `<ul>` items:
- `Up to 250 conversations / mo` → `Up to 250 missed-call replies / mo`
- `Up to 1,000 conversations / mo` → `Up to 1,000 missed-call replies / mo`
- `Up to 3,000 conversations / mo` → `Up to 3,000 missed-call replies / mo`

Also update the FAQ entry for overages/caps once Change 9 (soft overage) is added.

**Add a tooltip/explainer** next to each limit line (optional, lower priority):

```html
<li>{{ check }} Up to 250 missed-call replies / mo
  <span class="mk-tip" title="Each unique missed call that FirstBack texts back counts as one reply. Spam and robocalls don't count.">?</span>
</li>
```

### (c) How to verify

grep `pricing.html` for "conversations" — should return 0 hits in tier feature lists (FAQ and billing.py use the term internally, that's fine).

### (d) Effort

**Small** — three text replacements, ~15 minutes.

### (e) Risk and collisions

- `billing.py` internally uses "conversations" — that does not change. Only consumer-facing copy changes.
- `db.conversations_remaining` column name does not change. No migration.
- If other marketing pages (product.html, landing.html) also say "conversations," rename there too as a follow-on pass.

---

## Change 5 — SEO/OG Meta Block in marketing_base + Per-Page Fills

### (a) What and why

`marketing_base.html` has no `<meta name="description">`, no OG tags, no twitter:card, no canonical. The `<title>` renders as "FirstBack · FirstBack" on the homepage. A contractor who Googles "missed call text back painter" sees a blank snippet. Social shares look empty. This is the single lowest-effort, highest-SEO-leverage fix in the entire codebase.

### (b) Exact template + approach

**File 1:** `templates/marketing_base.html`

Add a `{% block meta %}` slot inside `<head>`, after `<meta name="viewport">`:

```html
<meta name="viewport" content="width=device-width, initial-scale=1">
{% block meta %}
<meta name="description" content="FirstBack texts back every missed call in seconds, answers their questions, and books the estimate — AI-powered for home-services contractors.">
<meta property="og:type" content="website">
<meta property="og:site_name" content="FirstBack">
<meta property="og:title" content="FirstBack — AI missed-call text-back for contractors">
<meta property="og:description" content="Miss a call. We text back. They book. Set up in a day, flat monthly rate.">
<meta property="og:image" content="/static/og-default.png">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="FirstBack — AI missed-call text-back for contractors">
<meta name="twitter:description" content="Miss a call. We text back. They book.">
<meta name="twitter:image" content="/static/og-default.png">
{% endblock %}
```

The default values in the block act as site-wide fallbacks. Each page overrides with `{% block meta %}...{% endblock %}`.

**File 2:** `templates/pricing.html` — add after `{% block title %}Pricing{% endblock %}`:

```html
{% block meta %}
<meta name="description" content="Simple flat pricing for AI missed-call text-back. Starter $99/mo, Pro $199/mo, Crew $399/mo. No per-call fees. Cancel anytime.">
<meta property="og:title" content="Pricing — FirstBack">
<meta property="og:description" content="Flat monthly plans starting at $99. No per-call fees, no contracts. One recovered job pays the year.">
<meta property="og:image" content="/static/og-default.png">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="Pricing — FirstBack">
<meta name="twitter:description" content="Flat monthly plans starting at $99. No per-call fees, no contracts.">
<meta name="twitter:image" content="/static/og-default.png">
{% endblock %}
```

**File 3:** `templates/landing.html` — add after `{% block title %}`:

```html
{% block meta %}
<meta name="description" content="FirstBack texts back every missed call in seconds and books the estimate — AI-powered for home-services contractors. Set up in one day, flat $99/mo.">
<meta property="og:title" content="FirstBack — Turn every missed call into a booked job">
<meta property="og:description" content="Miss a call. We text back. They book. Set up in a day, flat monthly rate, no per-call fees.">
<meta property="og:image" content="/static/og-default.png">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="FirstBack — Turn every missed call into a booked job">
<meta name="twitter:description" content="Miss a call. We text back. They book.">
<meta name="twitter:image" content="/static/og-default.png">
{% endblock %}
```

**File 4:** `templates/solutions.html` — add after `{% block title %}Solutions{% endblock %}`:

```html
{% block meta %}
<meta name="description" content="FirstBack AI missed-call text-back for painters, HVAC, plumbers, roofers, electricians — built for any trade that books work over the phone.">
<meta property="og:title" content="Solutions by trade — FirstBack">
<meta property="og:description" content="AI missed-call booking for painters, HVAC, plumbing, roofing, and 15+ other trades.">
<meta property="og:image" content="/static/og-default.png">
<meta name="twitter:card" content="summary_large_image">
{% endblock %}
```

**File 5:** `templates/customers.html` — add meta (understated until real proof exists):

```html
{% block meta %}
<meta name="description" content="Real contractor results with FirstBack AI missed-call text-back — customer stories from the trades.">
<meta property="og:title" content="Customer stories — FirstBack">
<meta property="og:description" content="Real results from real contractors. FirstBack books the jobs you were missing.">
<meta property="og:image" content="/static/og-default.png">
<meta name="twitter:card" content="summary_large_image">
{% endblock %}
```

**OG image note:** `/static/og-default.png` is referenced in `microsite.html` as already existing. Verify it exists at that path before shipping. If not, a 1200×630 dark-background image with the FirstBack wordmark and tagline ("Miss a call. We text back. They book.") serves as the default. Use headless Chrome or Higgsfield to generate if not already present.

### (c) How to verify

- `curl -s http://localhost:5000/ | grep 'og:title'` — should return the meta tag.
- Paste the landing URL into the Twitter Card Validator (cards-dev.twitter.com) or the Facebook Sharing Debugger — should show image, title, description.
- Google Search Console — submit the sitemap; within 1–2 weeks snippets should update.
- In Chrome DevTools > Elements, check `<head>` for all five tags on each page.

### (d) Effort

**Small** — template edits only, no backend changes, ~2–3 hours for all five pages.

### (e) Risk and collisions

- If `og-default.png` does not exist, the OG image tag will 404 silently on social shares. Check before shipping.
- No collision with other agents.
- Title tag change on the homepage (removing the doubled "FirstBack · FirstBack") requires changing the `{% block title %}` default in `marketing_base.html` or overriding per page. Current pattern: `{% block title %}{{ app_name }}{% endblock %} · {{ app_name }}`. Landing.html already overrides with `FirstBack — Every missed call, booked by AI`. The doubled title only affects pages that don't override — check which pages still render the doubled form and add `{% block title %}` to each.

---

## Change 6 — Hero and Positioning Reframe: Lead with the Booking-Complete Outcome

### (a) What and why

From 11-COMPETITIVE.md, the "another text-back tool" problem: FirstBack's first impression looks like one of dozens of missed-call SMS tools (Numa $49, GoHighLevel agencies $97–297). The differentiation — booking-complete with real calendar sync + Vic intelligence briefing — is not visible from the outside.

The hero currently leads with a good line ("Turn every missed call into a booked job") but the sub-copy is feature-description: "texts the customer back in seconds, answers their questions, and books the estimate." The competitive wedge is the *completed* booking AND the Vic briefing (morning intelligence). Both should be surfaced in the positioning layer.

The hero phone mockup already shows the conversation ending in "Booked — Thursday 10 AM" — that's the right visual. The copy needs to align with it.

### (b) Exact template + approach

**File:** `templates/landing.html`

**Hero h1:** Keep — "Turn every missed call into a booked job" is outcome-first and good.

**Hero lead paragraph — current:**
> "When you can't pick up, FirstBack's AI texts the customer back in seconds, answers their questions, and books the estimate — so the job doesn't go to the next painter."

**Hero lead paragraph — reframe to booking-complete + Vic wedge:**
> "Most tools text back. FirstBack books the job — calendar hold confirmed, estimate on the schedule, and you get a morning briefing on every open lead. While you're on the roof, your schedule fills itself."

This version:
- Leads with the competitive wedge ("most tools text back; FirstBack books the job")
- States the booking-complete outcome (calendar hold confirmed)
- Introduces the Vic briefing without overclaiming (honest: "morning briefing on every open lead")
- Closes with the contractor's lived experience ("while you're on the roof")

**Important founder honesty check:** Verify that the morning briefing (Vic) is actually live for all users, not just in development. If Vic's briefing is not yet live, the copy must be hedged: "...and when Vic's morning briefing rolls out, you'll get a daily run-down on every open lead." Alternatively, omit the briefing reference and save it for the Product page where it's correctly labeled.

**Value section kicker + h2 — current:**
> "The first to respond wins the work."

**Suggested reframe for kicker:**
> "Why contractors switch to FirstBack"

**Card 02 "Books the estimate" — strengthen to booking-complete:**
> "Books the estimate — confirmed on your calendar"  
> "Qualifies the job and locks in the time while you're on the ladder. The customer gets a confirmation. You get a calendar hold."

**Vic card (add as card 05 if Vic briefing is live):**
> "05 / Your morning brief"  
> "Every morning, Vic summarizes every open lead — who hasn't heard back, which job is worth chasing, which slot you should fill. You get actionable plays, not a raw inbox."

If Vic is not live for all users, hold this card for the Product page under the "coming soon" section.

### (c) How to verify

Load `/`. Read the hero sub-copy aloud as a contractor. Does it sound like "we text back fast" or "we book the job and brief you"? The latter is the target. Confirm the copy does not claim Vic briefing as live if it isn't.

### (d) Effort

**Small** — copy change only, ~1 hour.

### (e) Risk and collisions

- **Honesty gate:** If Vic briefing is not live for all users, do not include it in the hero lead. The morning briefing claim is the highest-value copy but also the highest risk if it's unavailable.
- Coordinate with any agent touching landing.html (check for collision).

---

## Change 7 — Testimonial Pipeline: Heritage Dogfood Slot + Honest Mechanism

### (a) What and why

The `/customers` page has three placeholder cards ("Your first customer's quote goes here"). These are honest but actively harmful — a contractor who clicks "// proof" in the nav lands on confirmation that no one uses this product. Per audit 10-MARKETING-SITE.md: "placeholder cards are worse than removing the link: they confirm no one is actually using this."

The founder (Jonathan Morris) runs Heritage House Painting. If FirstBack has been used on even one real job — even a dogfood beta test — that story is the first testimonial. It should be real, specific, and attributed. One real result from the owner's own painting crew is more credible than any placeholder.

The testimonial system also needs an honest pipeline mechanism — a way to slot future named-contractor quotes when they arrive, without fabrication.

### (b) Exact template + approach

**Phase 1 — Immediate (the Heritage slot):**

**File:** `templates/customers.html`

If Heritage House Painting has used FirstBack and booked at least one estimate through it, replace the first placeholder card with a real attributed quote. Template for the slot:

```html
<div class="mk-card mk-story">
  <blockquote>"[Real quote in Jonathan's words — specific outcome, e.g., 'I missed a call on a Saturday. By the time I was off the ladder, FirstBack had already booked an estimate for Tuesday. That's a job I would have lost.']"</blockquote>
  <div class="mk-story-who">
    <span class="name">Jonathan Morris</span>
    <span class="biz">Heritage House Painting — Ambler, PA</span>
  </div>
</div>
```

The remaining two cards should change from "Your first customer's quote goes here" to a **waitlist capture** (see Phase 2).

**Founder honesty rule:** The quote must be real and in the founder's own words. Do not write the quote in this plan — the founder must provide it. If no real outcome exists yet, skip this card and proceed to Phase 2.

**Phase 2 — Replace dead placeholder cards with "Be our first case study" capture:**

Replace cards 2 and 3 with:

```html
<div class="mk-card mk-story mk-story-open">
  <h3>Be the first case study in your trade</h3>
  <p>If FirstBack is booking jobs for you, we want to tell your story — a real result, in your words, with your name and trade. In return: a free month on us and a backlink to your business.</p>
  <a class="ob-btn ob-btn-accent" href="/contact?subject=case-study">Share my results →</a>
</div>
```

This is honest, incentivized, and useful — it converts the dead-end into a lead-gen mechanism for proof.

**Phase 3 — Landing page testimonial slot (when one real quote exists):**

**File:** `templates/landing.html` (currently has: `{# Testimonial section: placeholder removed -- add a real customer quote here once available. #}`)

When a real quote is obtained, replace the comment with:

```html
<section class="mk-section mk-proof">
  <div class="mk-wrap">
    <div class="mk-section-head center">
      <span class="mk-kicker">From the field</span>
    </div>
    <blockquote class="mk-pullquote">
      "[Real quote here]"
      <footer>— [Name], [Trade] — [City, State]</footer>
    </blockquote>
  </div>
</section>
```

**Phase 4 — Remove "// proof" nav label and nav links until real proof exists:**

Per audit: the "// proof" section in the nav links to both `customers.html` (placeholders) and `webinars` (coming soon). Both are dead ends. Until real proof exists, either:
- Remove the "// proof" label and move "Customer stories" and "Webinars" under "// learn" with an honest framing, OR
- Add a `?ref=nav` param to the `/customers` link and show the waitlist-capture version exclusively when no testimonials are live.

The simplest change: remove "Customer stories" and "Webinars" from the nav dropdown until real proof exists. They remain accessible by direct URL.

**File:** `templates/marketing_base.html` — comment out the two `ob-dditem` entries for `/customers` and `/webinars` under `// proof`. Replace the label with nothing or a single "Blog" link:

```html
<span class="ob-ddlabel">// proof</span>
<a class="ob-dditem" href="/customers" ...> <!-- restore when real quotes live -->
<a class="ob-dditem" href="/webinars" ...>  <!-- restore when webinar scheduled -->
```

### (c) How to verify

Load `/customers`. The Heritage quote (if approved) shows a real name, real trade, real city. The other cards show the "Be the first case study" capture, not placeholder text. No card says "Your first customer's quote goes here."

Load the nav — "// proof" section either removed or links to something that doesn't dead-end.

### (d) Effort

**Medium** — the HTML changes are Small; the real work is the founder providing a real quote (the "Vic delivered a specific win" moment described in 11-COMPETITIVE.md). Timeline depends entirely on founder input, not engineering.

### (e) Risk and collisions

- **Blocker:** If no real customer outcome exists yet (not even a Heritage dogfood result), the Heritage slot cannot be filled. In that case, deploy Phase 2 (waitlist capture) and Phase 4 (nav dead-end removal) immediately and defer Phase 1 and Phase 3.
- Do not fill the Heritage quote slot without founder-provided copy. The founder is Heritage House Painting — this is the dogfood account.
- No collision with other agents (Tier-0 agent owns the auth.html self-review stars; that's a separate honesty fix not related to the testimonial system).

---

## Change 8 — $20/mo Extra-Number Add-On on Pro (Pricing Page Surface)

### (a) What and why

Currently, getting a second phone number requires upgrading from Pro ($199) to Crew ($399) — a $200/mo jump. A 2-truck shop or a contractor running two trade specialties needs a second number but doesn't need 3,000 missed-call replies or 5 numbers. The packaging gap forces over-buying.

Adding a $20/mo extra-number add-on on Pro captures this buyer, adds a low-friction revenue stream, and reduces churn from contractors who hit the Pro ceiling for numbers.

**billing.py implication:** This requires a new Stripe product (a metered or flat add-on price, billed alongside the Pro subscription). The pricing page surface is a small copy change; the Stripe wiring is the medium-effort backend part. This plan covers the pricing page copy — the billing.py add-on logic is a separate backend task.

### (b) Exact template + approach

**File:** `templates/pricing.html`

In the Pro tier card, add a line below "1 phone number" (implied from Starter tier) or add explicitly:

```html
<li>{{ check }} 1 phone number
  <span class="mk-addon">+ $20/mo per extra number</span>
</li>
```

Or as a separate feature line below the feature list:

```html
<p class="mk-tier-addon">
  Need a second number? Add one for <strong>$20/mo</strong>. 
  <a href="/contact">Ask us →</a>
</p>
```

This is a soft surface: contractors who need it will notice; others skip it. The `/contact` link for now (before Stripe wiring is complete) lets the founder handle it manually.

**Copy note (honesty):** Only surface this on the pricing page if the founder is prepared to actually provision extra numbers. If not yet operationally ready, skip until the billing.py add-on is wired.

### (c) How to verify

Load `/pricing`. Pro card shows the extra-number add-on mention. Click "Ask us →" — goes to `/contact`. No 404s.

### (d) Effort

**Small** for the pricing page copy. **Medium** for the full billing.py Stripe add-on wiring (separate backend task).

### (e) Risk and collisions

- If billing.py doesn't support the add-on yet, the pricing page copy must route to `/contact` rather than a self-serve checkout. Do not surface a self-serve buy flow until `billing.py` is wired.
- No collision with other agents.

---

## Change 9 — Soft-Overage Path: UI Note + billing.py Hook

### (a) What and why

The current system has a hard cap: when `conversations_remaining` hits 0, no more texts go out. There is no overage option, no upgrade prompt, no revenue recovery. A contractor who blows through 250 missed-call replies mid-month either gets silently cut off or churns.

The fix is two-part: (1) a pricing page copy change that communicates the soft-overage path, and (2) a billing.py hook that either charges overages automatically or triggers an upgrade prompt at 80% utilization. This plan covers the pricing page copy change; the billing.py logic is noted as the related backend task.

### (b) Exact template + approach

**File:** `templates/pricing.html` — update the "Are there per-call or per-minute fees?" FAQ entry to address overages:

**Current:** "No. Your plan is one flat monthly rate — answer as many calls as your plan allows with no metered charges or surprise overages."

**Updated (honest + helpful):**

```html
<details>
  <summary>Are there per-call or per-minute fees?</summary>
  <p>No hidden fees and no metered charges. Your plan includes a set number of missed-call replies per month. If you're a busy month away from your limit, FirstBack will alert you at 80% so you can upgrade — there's no silent cutoff. And if you go over, replies continue at $0.75 each until your plan renews, or you can upgrade mid-month to a larger plan.</p>
</details>
```

**If the overage charge is not yet implemented in billing.py:** Change the FAQ copy to:

```html
<p>No per-call or per-minute fees. Your plan includes a set number of missed-call replies per month. If you're getting close to your limit, we'll let you know so you can upgrade — we don't cut you off mid-month without warning.</p>
```

This version commits only to an alert (which requires a notification hook) without committing to an automatic overage charge. It is honest and does not overclaim.

**billing.py implication:** The 80% alert requires a check in the conversation-decrement function: when `conversations_remaining` drops below 20% of the granted amount, trigger an owner notification (email or SMS alert). This is a small addition to the existing fuel-gauge logic. The $0.75/conversation overage requires a new Stripe metered billing setup — that is a separate medium-effort backend task.

### (c) How to verify

- Load `/pricing`. FAQ "Are there per-call fees?" entry explains the overage/alert behavior accurately.
- Test (billing.py): decrement a business's conversations_remaining to 20% and verify the alert fires (if implemented).
- If overage charging is live: verify Stripe records a usage record for conversations above the cap.

### (d) Effort

**Small** for the pricing page copy. **Medium** for the billing.py 80%-alert hook and overage charge wiring.

### (e) Risk and collisions

- The FAQ copy must match the actual system behavior. If overage charging is not live, do not promise "$0.75 each" — use the softer version ("we'll alert you").
- The 80% alert and overage charge are backend tasks that another agent or the founder should plan separately. This plan only covers the consumer-facing copy.

---

## Change 10 — /customers Nav Dead-End Remediation

### (a) What and why

(Covered in Change 7, Phase 4.) Extracted here as a standalone quick-win because it can ship immediately without waiting for real testimonials.

The nav "// proof" section links to `/customers` (three placeholder cards) and `/webinars` (coming soon, no date). Both dead-end. A contractor who navigates to either is actively seeking to be convinced and leaves empty-handed twice.

### (b) Exact template + approach

**File:** `templates/marketing_base.html`

Remove the `// proof` label and its two items from the Resources dropdown. Replace with nothing, or move Blog to the top of the `// learn` section. The `// proof` label should reappear only when real proof exists.

```html
{# proof section — restore when real customer quotes are live #}
{# <span class="ob-ddlabel">// proof</span> #}
{# <a class="ob-dditem" href="/customers" ...>Customer stories</a> #}
{# <a class="ob-dditem" href="/webinars" ...>Webinars</a> #}
```

### (c) How to verify

Load any marketing page. Open the Resources dropdown. No "// proof" label, no "Customer stories" or "Webinars" links. Navigating directly to `/customers` still works (it's not deleted, just de-linked from the nav).

### (d) Effort

**Small** — HTML comment-out, ~10 minutes.

### (e) Risk and collisions

- If another agent's plan also touches `marketing_base.html` nav, coordinate to avoid merge conflicts.
- Restore the proof section with real content as a follow-up task once testimonials are live.

---

## Dependency Map

```
Change 1 (annual toggle)
  └── requires: /signup route passes interval param to billing.py create_checkout_session

Change 3 (money-back guarantee)
  └── requires: founder confirms guarantee policy before shipping

Change 6 (hero reframe)
  └── requires: confirm Vic morning briefing is live for all users before claiming it in hero

Change 7 (testimonial pipeline)
  └── Phase 1 requires: founder-provided real quote (Heritage dogfood outcome)
  └── Phase 4 (nav de-link) is independent, can ship now

Change 8 ($20 add-on)
  └── pricing page copy can ship now (routes to /contact)
  └── self-serve flow requires: billing.py Stripe add-on wiring (separate backend task)

Change 9 (soft overage)
  └── pricing page FAQ can ship now (soft version without overage charge)
  └── $0.75 overage requires: billing.py metered charge + Stripe setup

Change 10 (nav dead-end)
  └── independent, no dependencies — ship first
```

---

## Collision Notes for Other Agents

- **Tier-0 agent** owns: auth.html stars/self-quote, solutions.html voice claim, product.html voice checkmarks, /simulator→/demo CTA links. This plan does not touch those.
- **landing.html** is touched by Change 6 (hero copy) and Change 7 Phase 3 (testimonial slot). If another agent also edits landing.html, coordinate.
- **marketing_base.html** is touched by Change 5 (meta block) and Change 10 (nav dead-end). If another agent touches the nav, coordinate on the `ob-ddmenu` for Resources.
- **billing.py** is noted as the target for Changes 1 (interval param), 8 (add-on), and 9 (overage) but this plan does NOT make billing.py changes — it only surfaces the UI/copy layer. A separate backend agent or the founder should wire the billing.py additions.

---

## File + Effort Summary

| File | Changes | Effort |
|------|---------|--------|
| templates/pricing.html | Annual toggle, ROI anchor, guarantee badge, "missed-call replies" rename, extra-number add-on surface, overage FAQ | S |
| templates/marketing_base.html | {% block meta %} slot, nav dead-end de-link | S |
| templates/landing.html | Hero lead copy reframe, {% block meta %}, testimonial slot (Phase 3, deferred) | S |
| templates/solutions.html | {% block meta %} | S |
| templates/customers.html | Heritage quote slot (deferred on founder input), waitlist-capture cards, {% block meta %} | S–M |
| billing.py | NOT touched by this plan — annual interval param, 80% alert, overage wiring are backend tasks flagged for a separate agent | — |

**Total plan effort: Small across the board. The one Medium item (testimonials) is gated on founder input, not engineering.**

**Biggest risk: The money-back guarantee (Change 3) and Vic briefing in hero copy (Change 6) are policy decisions, not technical ones. Shipping copy that commits to a policy the business isn't ready to honor is a trust violation. These two changes require explicit founder confirmation before merging.**
