# Marketing Site Audit — Trust, Conversion, Honesty, Brand
**Auditor lane 10 of 12 — PUBLIC MARKETING SITE**
**Date:** 2026-06-19
**Bar:** $99/mo sign-up from a skeptical contractor who landed cold.

---

## Executive summary

The copy and structure are better than average for a pre-launch SaaS: honest on voice (clearly labeled beta/coming-soon), zero fake integration logos (prior P0 issues fixed), and the fake testimonials were pulled from `/customers`. The value prop is clear in ~5 seconds on the onboarding homepage. But the site is still missing the one thing that would actually sell a skeptical contractor: **any third-party proof**. The auth sidebar shows 5-star icons attributed to "-- FirstBack" — a self-review. The `/simulator` (primary demo CTA on the old landing) is login-gated, killing the conversion loop. SEO basics are completely absent. And the solutions page still has an unhedged voice claim that contradicts every other page's "coming soon" label. These are the conversion gaps.

---

## Finding 1 — Zero SEO meta on every marketing page

**Impact: H | Effort: S**

**WHAT:** `marketing_base.html` has no `<meta name="description">`, no `og:title`, no `og:description`, no `og:image`, no `twitter:card`, no canonical tag. The `<title>` pattern is `{% block title %}` + ` · FirstBack` — so the homepage title renders as just `FirstBack · FirstBack`. The only template with OG tags is `microsite.html` (the contractor compliance page, not the marketing site).

**WHY:** A skeptical contractor who Googles "missed call text back for painters" sees a blank snippet, no preview image when the link is shared on Facebook/Nextdoor. Google can't rank a page with no description. This is also money left on the table for every paid channel (social shares look empty).

**REC:** Add a `{% block meta %}` slot to `marketing_base.html`. Populate it per-page:
- `/` → "Turn every missed call into a booked job | FirstBack"
- `/pricing` → "Simple flat pricing — $99/mo, no per-call fees | FirstBack"
- etc.
Add `og:image` pointing to `/static/og-default.png` (already exists in microsite) and `twitter:card: summary_large_image`. This is a one-day fix that pays for itself every week.

---

## Finding 2 — Primary demo CTA is login-gated; public `/demo` is unfindable

**Impact: H | Effort: S**

**WHAT:** The old `landing.html` (the `/` route for non-logged-in users) sends the hero button "See it live" to `/simulator`, which is `@login_required` → 302 to `/login`. There IS a public demo at `/demo` (no login required, sandbox business, real AI), but nothing on the marketing site links to it. The only entry to `/demo` is if you already know the URL.

**WHY:** A contractor who clicks "See it live" and hits a signup wall before seeing the product has their attention broken at the exact moment of peak interest. The public `/demo` already exists and works — it just isn't linked from anywhere a visitor would find it.

**REC:**
1. Change `landing.html`'s hero CTA from `href="/simulator"` → `href="/demo"`. Same for the Product page "See the live demo" button (currently labeled as such but also goes to `/simulator` per the prior SITE_TRUTH_AUDIT B9 finding).
2. Add a secondary "See it live — no signup" text link beneath the primary CTA on the onboarding homepage.
This single change removes friction for the highest-intent moment on the site.

---

## Finding 3 — Auth page's 5-star proof is a self-review (trust violation)

**Impact: H | Effort: S**

**WHAT:** `auth.html` displays five filled star SVGs with `aria-label="5 out of 5"`, followed by a quote: *"Catch every missed call, book the job, and never chase a lead by hand again."* attributed to `-- FirstBack`. This is the company quoting itself with a star-rating widget that visually reads as a customer review. It appears on the login AND sign-up screens — exactly where a prospect is making the final yes/no decision.

**WHY:** Any contractor who notices this attribution will read it as fake social proof and distrust everything else on the page. Even if they don't consciously catch it, the UI convention for a 5-star block is "third party says this." Using it for a self-quote is a dark pattern regardless of intent.

**REC:** Remove the stars entirely — a self-quote doesn't earn a star widget. Replace with a 1-line product truth: *"Up and running in a day. Flat rate. No contracts."* or hold the space empty until a real customer provides a quote. Stars with `-- FirstBack` byline is worse than no proof at all.

---

## Finding 4 — `/solutions` page has an unhedged live-voice claim

**Impact: H | Effort: S**

**WHAT:** `solutions.html` line 32: *"FirstBack answers every missed call by text or a **live AI voice** and books the work while you're on the tools."*

This is stated as current product behavior, with no "coming soon," no "beta," no qualification. Every other page that mentions voice is correctly hedged: pricing calls it "coming soon (beta — not yet available)"; the onboarding Call tab says "It is not available yet; today FirstBack handles everything by text"; the FAQ says "Coming soon. Voice callback is in beta."

**WHY:** A contractor who reads the solutions page and signs up expecting live AI voice calls will experience a gap. This is an honesty issue and a churn risk. It also undercuts the founder's own rule against claiming gated features as live.

**REC:** Change to: *"FirstBack answers every missed call by text — and, when you'd rather talk, AI voice callback is coming soon."* One sentence fix, consistent with every other page.

---

## Finding 5 — Zero social proof on the conversion path (customers, testimonials)

**Impact: H | Effort: L (by definition — requires real customers)**

**WHAT:** `/customers` is the only live social-proof destination linked from the nav. Its current content is three placeholder cards with text like "Your first customer's quote goes here" and "We'd rather show one true story than three invented ones." The comment in `landing.html` (line 105) also confirms: `{# Testimonial section: placeholder removed -- add a real customer quote here once available. #}`. The company stats on `/company` are honest but toothless: "Seconds," "24/7," "Day one" — capability claims, not customer outcomes.

**WHY:** At $99/mo, the typical contractor (non-tech, skeptical of anything labeled "AI") is not going to self-persuade from features alone. The #1 closer for a local-service business SaaS is "someone like me did this and it worked." Without a single real quote, the conversion path has no third-party validation anywhere.

**WHY IT MATTERS NOW:** The `/customers` page is linked in the nav under the "// proof" label — a contractor who clicks it is actively seeking to be convinced. Placeholder cards are worse than removing the link: they confirm no one is actually using this.

**REC (ranked by speed):**
1. **Short-term:** Remove "Customer stories" from the nav dropdown and the Resources grid until there's a real story. Replace `/customers` with a "Be our first case study" waitlist capture. This removes the proof-seeking dead end.
2. **Parallel:** Get one real contractor (even a beta user, even the owner's own crew) to provide a real quote with a real outcome ("booked 3 estimates in the first week I never would have gotten"). A single real quote on the landing hero is worth more than 100 placeholder cards.
3. **Longer-term:** The blog posts ("June 10, 2026: The first to reply wins the job") cite "study after study" without sourcing. Consider linking to a real speed-to-lead study (the Velocify/InsideSales 5-minute data is well-known and public) to borrow third-party authority while waiting for customer quotes.

---

## Finding 6 — No risk-reversal or entry-level offer on the conversion path

**Impact: M | Effort: M**

**WHAT:** There is no free trial, no money-back guarantee, and no low-commitment starting point explicitly called out on the landing or pricing pages. The trust signals that exist ("No contracts," "Flat monthly rate," "Cancel anytime") are present but buried in small type below the hero. For a $99/mo ask to a non-tech contractor audience, the friction of "what if it doesn't work for my trade?" is never directly answered.

**WHY:** "Cancel anytime" is the right call — but it's underused as a conversion lever. At $99, the fear is "I'm going to pay $99 and it won't sound right for my roofing business" — not "I'll be locked in." The copy handles the lock-in objection but misses the suitability objection.

**REC:**
- Move "No contracts · Cancel anytime" to a line directly beneath the primary CTA on the onboarding homepage (currently only shown as small trust pills below the hero).
- Add a single sentence on `/pricing` between the plan grid and FAQ: *"Not sure it fits your trade? Set it up and try it for 30 days — if it's not booking jobs, cancel and we'll refund the first month."* This is a positioning decision, not a technical one, but it would materially lower the signup barrier.

---

## Finding 7 — Product page voice section is present-tense with checkmarks, not beta-framed

**Impact: M | Effort: S**

**WHAT:** `product.html` has a full section (`mk-kicker: "AI voice callback · beta"`) with three checkmark bullet points presented exactly like the live features above it:
- "Picks up and speaks in a natural voice"
- "Rings your cell first — only takes over if you can't"
- "Books straight onto your calendar, hands-free"

The kicker says "beta" but the bullets have the same filled-green checkmarks as "Instant text-back" and "AI booking." Visually, a contractor scanning the page reads all six sections as equivalent.

**WHY:** Checkmarks are a commitment signal — "you get this." Using them on a not-yet-available feature overpromises. A contractor who signs up based on the voice capability will be let down.

**REC:** Replace the checkmark SVGs in the voice section with a different indicator (dashed circle, clock icon) and add a single note: *"Voice callback is rolling out — sign up to get early access."* The "beta" kicker alone is not enough visual differentiation for a non-technical audience.

---

## Finding 8 — Brand/visual surface: good bones, missing differentiation

**Impact: M | Effort: M**

**WHAT:** The dark/Jarvis HUD aesthetic on the onboarding homepage is distinctive — the ruling-frame proof block, the terminal JSON, the holographic color scheme. But the marketing sub-pages (product, pricing, solutions, company) use a much simpler light-background template (`marketing_base.html`) that looks generic: white cards, icon-only illustrations (SVG wireframes), no photography, no screenshots of the actual product UI.

**WHY:** "Does it look premium?" is the first trust filter for a contractor who doesn't know the name. The onboarding page passes. The moment they click into `/product` or `/pricing` the experience downshifts to a generic marketing template that could be any SaaS from 2020.

**REC:**
- Add 1-2 actual screenshots or mockups of the dashboard/command center to `/product` — a lead list, a conversation thread, a booked estimate. Even a polished screenshot is more credible than SVG icons.
- The `/pricing` page could carry the dark brand accent into the featured ("Most popular") card more boldly to signal premium-ness.
- The `/company` stats ("Seconds", "24/7", "Day one") work better with the dark brand treatment of the onboarding page. The context-switch from "Jarvis HUD" to "plain white site" after the first click is a brand gap.

---

## Finding 9 — Webinars page is a weak dead-end for a navigational promise

**Impact: L | Effort: S**

**WHAT:** The nav's "// proof" section links to both "Customer stories" (placeholder) and "Webinars." The webinars page delivers: one event card, labeled "Coming soon · dates announced by email," with a CTA that goes to `/contact` ("Get notified"). This is honest, but a contractor who clicks "Webinars" from the nav expecting proof gets a dead-end with no date and no recordings.

**WHY:** Low individual impact, but compounds with the empty `/customers` page: both "// proof" entries in the nav are empty. Contractors who self-qualify by clicking proof content leave empty-handed twice.

**REC:** Either remove the "// proof" label until there's actual proof, or replace the webinar CTA with "Watch a 2-minute screen recording of FirstBack booking a job" and link to a Loom/YouTube clip. A screen recording is doable in a day and would outperform an upcoming-webinar placeholder for conversion purposes.

---

## Finding 10 — Blog dates appear current but articles are thin

**Impact: L | Effort: M**

**WHAT:** `blog.html` shows three articles dated June 3–10, 2026, each ~2 paragraphs. "Study after study on 'speed to lead' says the same thing" (June 10 post) cites no study. The articles are correct in thesis but very short and unsourced.

**WHY:** Blog SEO only works with depth and specificity. Two-paragraph posts don't rank. The "study after study" claim in a public article is also a minor trust risk for a "no spin" brand.

**REC:** Link out to one real speed-to-lead source (Velocify, MIT/Kellogg, InsideSales.com). The blog is not a primary conversion path at this stage, so this is deprioritized — but a single well-sourced article would help SEO and credibility more than three thin ones.

---

## Remaining honesty check — issues from prior SITE_TRUTH_AUDIT

The prior audit (SITE_TRUTH_AUDIT.md, 2026-06-15) identified several P0/P1 issues. Current state:

| Prior ID | Current status |
|----------|----------------|
| I1 — Jobber/Housecall Pro logos | FIXED (not present in current templates) |
| C1–C3 — Fabricated testimonials (Dana, Priya, Marcus) | FIXED (replaced with honest placeholder cards on /customers) |
| C10 — "Sign up for free / Start free" with no free plan | FIXED (current CTAs say "Get started" not "free") |
| B1–B4 — Dead links in auth.html (terms/privacy/#) | PARTIALLY FIXED — terms/privacy links work; auth.html stars/self-quote still there (Finding 3) |
| C11 — Voice marketed as included on Pro/Crew | PARTIALLY FIXED — pricing has "coming soon (beta — not yet available)" but product.html still uses present-tense checkmarks (Finding 7) |
| C14 — Fake webinar dates ("Thursday June 19 · 12 PM ET") | FIXED — current page says "Coming soon · dates announced by email" |
| B9 — /simulator login-gated despite "See live demo" link | STILL PRESENT (Finding 2) |
| C16 — "Most contractors are live within a day" implies a user base | PARTIALLY FIXED — now says "Most contractors finish this in a single sitting" and "Most contractors live within a day" (still implies a customer base) |
| Solutions.html voice claim | STILL PRESENT (Finding 4) |

---

## Top 3 fixes to turn visitors into trials/signups

**Fix 1 (1 day, highest ROI): Link "See it live" → `/demo`**
The public demo works. The hero CTA sends people to a login wall. Swap the URL. This alone increases demo-to-signup conversion for the largest bucket of intent.

**Fix 2 (1 day): Add OG/description meta to all marketing pages**
Zero setup required beyond a `{% block meta %}` in `marketing_base.html`. Fixes Google snippets, social sharing, and basic SEO in one pass.

**Fix 3 (1 week, requires a real customer): Get one real quote with a real outcome**
Every other gap on this list (no proof, weak trust, empty /customers) collapses if there is a single authentic contractor quote with a name, trade, and outcome ("booked 4 estimates last week I never would have caught — roofing, Austin TX"). One real story on the landing page is worth more than all the other polish combined.

---

## Verdict

**The conversion and trust gap is large.** The site's honesty improved significantly after the prior audit — fake testimonials gone, fake logos gone, voice correctly labeled. But the site has no third-party proof anywhere on the live conversion path, the demo is hidden behind a login wall, and there are no OG/SEO basics. A skeptical contractor who finds this organically will not convert: they will see a polished but empty showcase with no one vouching for it. At $99/mo, that's a trust deficit the product copy cannot close alone. The three fixes above are the shortest path to changing that.
