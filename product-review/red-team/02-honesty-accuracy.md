# Red-Team Lane 2 — Honesty & Accuracy
**FirstBack @ /Users/jonathanmorris/Documents/apps/firstback**
Run: 2026-06-25

---

## Methodology

Every marketing template, in-app page, and core config/billing file read in full.
Gates cross-checked against: `billing.configured()` / `STRIPE_PRICE_*` env vars,
`VOICE_PUBLIC_URL`, `GOOGLE_CLIENT_ID/SECRET`, `MICROSOFT_CLIENT_ID/SECRET`,
`JOBBER_CLIENT_ID/SECRET`, `HCP_CLIENT_ID/SECRET`, `TWILIO_TRUST_PRODUCT_SID`,
`FIRSTBACK_REPUTATION_PROVIDER`, `FIRSTBACK_SCREEN_AI`. The prior SITE_TRUTH_AUDIT.md
was reviewed; its resolved items are not re-listed. This report covers new findings
and remaining issues.

---

## P0 — False or legally-risky claims (fix immediately)

---

### P0-1 · "+50 conversations for $12" — advertised add-on that does not exist

**File:** `templates/command.html:177`
**Quoted claim:** When a subscriber's conversation quota hits 90% the in-app fuel gauge shows:
> `rem + ' of ' + total + ' conversations left' + refill + ' · <a href="/pricing">+50 for $12</a>'`

**Why it is wrong:**
There is zero implementation of a $12 top-up anywhere in the codebase.
`billing.py` defines only three monthly plans (starter/pro/crew) and their annual
variants. There is no `STRIPE_PRICE_TOPUP`, no `/billing/topup` route, no
`add_usage_grant` call triggered by a $12 payment, no Stripe product for it. A
subscriber clicking that link lands on `/pricing` — which contains only the three
main plans. The user paid for a promise that cannot be fulfilled.

**Honest rewrite:**
Remove the `+50 for $12` link entirely. Replace with `· <a href="/pricing">Upgrade to get more</a>`
(which is accurate — the only way to get more conversations today is to upgrade).
The `$12 add-on` copy may be re-added only once a Stripe Price and a
`/billing/topup` checkout route exist.

---

### P0-2 · Annual subscription CTA is hard-coded to monthly — the advertised 20% discount is not actually purchasable

**File:** `templates/pricing.html:12`, `68`, `83`, `104`
**Quoted claims:**
- `"Save 20% when you pay annually."` (pricing page header, line 37)
- `"or $950 / year — save $238 (20% off)"` (Starter, line 68)
- `"or $1,910 / year — save $478 (20% off)"` (Pro, line 83)
- `"or $3,830 / year — save $958 (20% off)"` (Crew, line 104)

**Why it is wrong:**
The `plan_cta` macro at the top of the file generates the Subscribe form with:
```
<input type="hidden" name="interval" value="month">
```
There is no annual toggle, no second form, and no UI to choose the annual
interval. Every Subscribe button — when billing goes live — will enroll the
subscriber in the **monthly** plan, not the annual one, regardless of which
`"or $X/year"` line they read. The annual `STRIPE_PRICE_*_ANNUAL` env vars and
`_norm_interval()` logic exist in `billing.py`, but there is no checkout path
that ever sends `interval=year`.

SETUP_NEEDED.md explicitly flags this: "Deferred enrichments: annual-toggle
checkout wiring (cosmetic until checkout)."

The annual pricing is displayed prominently on a public-facing page with no
disclosure that it is not yet purchasable. A visitor who reads "$950/year" and
clicks "Get started" will be billed $99/month (or cannot subscribe at all if
`billing.configured()` is False, in which case they see a generic `/signup` link).

**Honest rewrite option A (immediate):** Remove all "or $X / year" and "Save 20%
when you pay annually" copy until the annual checkout is wired.
**Honest rewrite option B:** Add a disclosure note beneath the annual price line:
`"Annual billing coming soon — subscribe monthly to get started."`

---

### P0-3 · Crew plan features do not exist in code

**File:** `templates/pricing.html:101–114`
**Quoted claims (all with green checkmarks):**
- "Up to 5 phone numbers"
- "Multiple business profiles"
- "Team roles & logins"
- "Dedicated onboarding"

**Why it is wrong:**
None of these features are implemented anywhere in the codebase:
- `db.py` has no `phone_number_limit`, no multi-number per-business schema, no
  `business_profiles` table, no `team_roles` column.
- `app.py` has no route or logic gating anything on plan == "crew".
- `billing.py` `PLAN_GRANTS` only grants conversation counts (`crew: 3000`).
- "Dedicated onboarding" — there is no onboarding route, scheduling system, or
  queue differentiated by plan.

The code difference between a Crew plan subscriber and a Starter plan subscriber
is solely the conversation allotment (3000 vs 250 per month). Every other listed
Crew feature is phantom.

**Honest rewrite:** Remove all four unimplemented bullet points. Replace with only
"Up to 3,000 missed-call replies / mo" and a "Contact sales for multi-location
setup" note. Re-add the others only when the code ships.

---

### P0-4 · "Calendar integration" as a Pro plan exclusive feature — it is available to all plans or gated only on operator env, not plan tier

**File:** `templates/pricing.html:95`
**Quoted claim (with checkmark, listed only under Pro):**
> "Calendar integration"

**Why it is wrong:**
Google Calendar and Outlook Calendar are gated on `GOOGLE_CLIENT_ID/SECRET` and
`MICROSOFT_CLIENT_ID/SECRET` (operator env vars), not on plan tier. Any user on
any plan — Starter, Pro, or Crew — can connect their calendar once the operator
sets those vars. Nothing in `app.py`, `google_cal.py`, or `outlook_cal.py` checks
`plan == "pro"`. The Starter plan buyer who sees no "calendar integration" checkmark
has the same calendar access as a Pro subscriber.

**Honest rewrite:** Move "Calendar integration" to the Starter column (it is
platform-wide), or add a footnote clarifying it applies to all plans.

---

## P1 — Overclaims / misleading (fix before live customers)

---

### P1-1 · "No per-call or per-minute fees. Ever." — the absoluteness breaks against voice callback billing

**File:** `templates/pricing.html:37`
**Quoted claim:**
> "No per-call or per-minute fees. **Ever.**"

**Why it is wrong:**
`config.py` defines:
```python
VOICE_MONTHLY_CAP_CENTS = 2000  # $20/mo default
VOICE_CREDIT_RATE_CENTS = 25     # 25 cents per 30-second billing block
```
When the AI voice callback is deployed (`VOICE_PUBLIC_URL` set), calls are
metered at 25 cents per 30 seconds — i.e. per-minute billing. The `SETUP_NEEDED.md`
explicitly notes: "Cost: ~$0.10–0.13/min (3-min call ≈ $0.30); per DEV-HANDOFF:
price voice as a $29–$49/mo opt-in add-on once pricing/billing is live."

The word "Ever" is an absolute that will become demonstrably false the moment
voice is deployed. Even if voice is currently in beta/off, selling a plan with
"No per-call fees. Ever." creates a contract-like expectation the product will
break.

**Honest rewrite:** `"No per-call or per-minute SMS fees."` or add a footnote:
`"Voice callback, when available, is an add-on priced separately."`

---

### P1-2 · "No surprise overages, cancel whenever" — no billing system to enforce it

**File:** `templates/company.html:19`
**Quoted claim:**
> "One flat monthly rate. No per-call fees, no surprise overages, cancel whenever."

Also: `templates/help.html:32` — "Cancelling stops future billing."
Also: `templates/pricing.html:131` — "Cancel anytime — there are no contracts and no cancellation fees."

**Why it is wrong:**
`billing.py`'s `configured()` returns False in production (no `STRIPE_SECRET_KEY`
or Price IDs set). No subscriber can currently subscribe or cancel through the app.
SETUP_NEEDED.md line 325: "There is **no billing system** yet." A visitor who reads
"cancel whenever" has no mechanism to cancel because they cannot subscribe.

When billing is live via Stripe these claims will be Stripe-enforceable (no contracts,
Stripe portal cancellation) — so this is a timing issue, not a fundamental lie. But
making these promises to a visitor who clicks "Get started" and cannot actually
subscribe is misleading about the product's readiness.

**Honest rewrite:** No copy change needed once billing is live. In the interim: no
customer-facing "cancel anytime" promise needs to change, but the "Get started"
CTA should not imply a paid subscription is available until `billing.configured()`.
The macro already gates the Subscribe button on `billing_live` — but the surrounding
copy makes promises regardless.

---

### P1-3 · "Rings your cell first — only takes over if you can't" — only true when `forward_to` is configured

**File:** `templates/product.html:59`
**Quoted claim (with green checkmark under "AI voice callback"):**
> "Rings your cell first — only takes over if you can't"

**Why it is wrong:**
This is only true in "dial-through" mode (`forward_to` is set in Settings).
From `app.py:3169-3175`:
```python
forward = biz.get("forward_to")
if forward:
    # Dials the cell first, then falls through to AI/text on no-answer
```
When `forward_to` is blank — i.e. the default for any new user — the inbound call
goes directly to AI answering or text-back, never ringing the owner's cell. The
product page presents "rings your cell first" as a universal feature description,
not a conditional one.

**Honest rewrite:** "Rings your cell first (optional) — only takes over if you
don't pick up." Or: "You can set it to ring your cell first before the AI kicks in."

---

### P1-4 · "The first to reply wins the job" blog post cites "Study after study" with no source

**File:** `templates/blog.html:14`
**Quoted claim:**
> "Study after study on 'speed to lead' says the same thing: respond in minutes and
> your odds of winning the work jump dramatically."

**Why it is wrong:**
No source is cited. The phrase "study after study" implies a body of research; there
is none referenced. In a product blog this reads as invented authority. The prior
SITE_TRUTH_AUDIT noted this as C9 (P2). Given the explicit "no invented quotes"
honesty ethic, vague appeals to unnamed studies violate the same standard.

**Honest rewrite:** "Research on speed-to-lead consistently shows…" and link one
real source (e.g. Harvard Business Review's Lead Response Management study), or
rewrite as opinion: "In our experience, the first to reply wins the job."

---

### P1-5 · Homepage "works with Google Calendar" — gated on operator env vars, not actually live in prod

**File:** `templates/onboarding.html:168-169`
**Quoted claim:**
> `<span>Google Calendar</span><span>Your existing number</span>` (under "works with")

**Why it is misleading:**
Google Calendar is real and implemented (gated on `GOOGLE_CLIENT_ID/SECRET`). But
the homepage states it as a current capability with no qualification. In production
(`ringback-gixe.onrender.com`), if `GOOGLE_CLIENT_ID` is not set, Google Calendar
shows "Coming soon" in Settings. A visitor who sees "works with Google Calendar"
on the homepage, signs up, and finds "Coming soon" in their settings has been misled.

**Honest rewrite:** Add conditional text: "works with Google Calendar (when connected)"
or restrict the claim to only appear when `google_configured` is True (already
available as a template variable). Or accept the claim as aspirational product
positioning (lowest-risk interpretation given the code exists).

This is a judgment call — the claim is not fabricated, but it can disappoint new
users who expect it to work immediately.

---

### P1-6 · "Start the same day" on pricing page headline — A2P carrier registration takes 1-5 business days for real text-back

**File:** `templates/pricing.html:37`
**Quoted claim:**
> "Pick a plan, **start the same day**, and only pay for the seats you need."

**Why it is misleading:**
The pricing FAQ (line 130) correctly and honestly discloses:
> "Live text-back to your customers switches on once your carrier registration
> (A2P) clears — usually 1–5 business days."

But the headline claim "start the same day" is the first thing a visitor reads,
and it contradicts the FAQ. A customer who signs up expecting to text customers
"the same day" will be disappointed to learn real text-backs are blocked for
1–5 days. The FAQ buries the qualification; the headline leads with the exception.

The SETUP_NEEDED.md also notes that `TWILIO_TRUST_PRODUCT_SID` must be set before
any real A2P submission fires (without it, `submit_a2p()` returns "simulated" and
nothing is submitted to carriers). So "usually 1–5 business days" is itself an
optimistic number that assumes the operator's Twilio Trust Hub is already configured.

**Honest rewrite:** `"Pick a plan, get set up today, and start catching missed calls."`
with the A2P qualification visible in the hero section, not just buried in FAQ.

---

### P1-7 · Resources page: "How painters, plumbers, and HVAC crews booked more work" — no actual customer stories exist

**File:** `templates/resources.html:22`
**Quoted claim:**
> "How painters, plumbers, and HVAC crews booked more work without hiring a front desk."

**Why it is wrong:**
`customers.html` explicitly says "FirstBack is just getting started. As contractors
go live, their real results will show up here — no invented quotes." There are zero
real customers documented. The resources page card implies these stories currently
exist and can be read. Clicking "Read stories" lands on the placeholder.

**Honest rewrite:** `"When contractors go live, their real results will show up here.
Be the first."` or remove the "How painters, plumbers…" sentence from the resources
card until real stories exist.

---

### P1-8 · Product page: "AI voice callback" section presents all features with green checkmarks regardless of voice_configured status

**File:** `templates/product.html:54–64`
**Quoted claim (three green checkmarks listed regardless of beta status):**
> "Picks up and speaks in a natural voice"
> "Rings your cell first — only takes over if you can't"
> "Books straight onto your calendar, hands-free"

**Why it is wrong:**
When `voice_configured` is False (i.e., `VOICE_PUBLIC_URL` is not set — the current
production state), the kicker correctly says "AI voice callback · beta", but all
three features still render with full green checkmarks (the `{{ check }}` SVG) and
no qualification. There is no visual difference between features that work today and
features that are in beta and not deployed.

Contrast: the pricing page (when `voice_configured` is False) shows `<span
style="opacity:.5">coming soon</span>` for this feature. The product page is inconsistent.

**Honest rewrite:** When `not voice_configured`, render the bullet list items
with muted styling or a `(coming soon)` tag, matching the pricing page treatment.

---

### P1-9 · Pricing FAQ: "we don't cut you off mid-month without warning" — the system DOES degrade without billing

**File:** `templates/pricing.html:122`
**Quoted claim:**
> "If you're getting close to your limit, we'll let you know so you can upgrade —
> we don't cut you off mid-month without warning."

**Why it is partially wrong:**
When a business has no active subscription (`has_plan = false`), the daily
`CLAUDE_DAILY_COST_CAP_USD` ($5 default) acts as a hard spending cap and the
system degrades to "resting" mode with no text-back. This can happen to a free/
non-subscribed user without a meaningful "heads up" that they are about to be
cut off. The command center fuel gauge shows this only after the cap is hit.
The claim applies cleanly to paid subscribers; it overpromises for non-subscribers.

Additionally: when billing is not live (`billing.configured() = False`), no one
is a "subscriber" in the traditional sense — the FAQ's framing of "upgrade" is
meaningless.

**Honest rewrite:** "Subscribed customers: we'll let you know before you hit
your monthly limit. We don't cut you off mid-month without warning."

---

## P2 — Minor inaccuracies / stale copy (fix when convenient)

---

### P2-1 · "Set up for you" / "No hour-long onboarding calls. We get you live in a day" — implies human-assisted setup

**File:** `templates/company.html:18`
**Quoted claim:**
> "No hour-long onboarding calls. We get you live in a day and stay reachable by
> a real human after."

**Why it is slightly wrong:**
The product is a self-serve SaaS. The operator handles A2P concierge work, but
there is no documented "we get you live" human-assisted onboarding process. A
customer who expects a human to set up FirstBack for them will be surprised to
find a self-serve wizard. "We" implies someone at FirstBack does the work; "in a
day" implies the person will be operational in 24h (but A2P adds 1-5 days).

**Honest rewrite:** "No hour-long onboarding calls. You can be live in a day —
we're here by chat or email whenever you need us."

---

### P2-2 · "Most contractors live within a day" / "Most contractors finish in a single sitting" — no customer base to support "most"

**File:** `templates/company.html:27`, `templates/help.html:13`, `templates/guides.html:12`
**Quoted claims:**
- "Most contractors live within a day" (company stats)
- "Most contractors are live within a day" (help center)
- "Most contractors finish this in a single sitting" (guides)

**Why it is wrong:**
The SITE_TRUTH_AUDIT (C16) already flagged this. There are zero external contractors
with measured onboarding times. The word "most" implies a statistically validated
population. The prior audit recommended rewording to capability language.

**Honest rewrite:** "You can be live in a day." / "You can finish setup in a
single sitting." (Already addressed as C16 in prior audit — confirm it was fixed.)

---

### P2-3 · $45K+ revenue-lost figure — footnote math does not match the headline number

**File:** `templates/pricing.html:46–60`
**Quoted claim:**
> "$45K+ average revenue lost per year to unanswered calls"
> Footnote: "Based on contractors missing 5-10 calls/week at an average job value
> of $300-$1,500."

**Why it is wrong:**
At 5 calls/week × 52 weeks × $300/job = $78,000. The minimum in the stated range
already exceeds $45K. The $45K figure is below the floor of its own stated
assumptions. Running the actual math:
- To get $45K at $300/job: you need ~2.9 calls/week (less than the "5-10" stated)
- At $300/call × 5 calls × 52 weeks = $78,000 — 73% above the headline.

The $45K headline is lower than any combination in the footnote supports, making
the footnote mathematically inconsistent with the headline. (The number is
conservative/favorable to honesty in the sense that the true figure under stated
assumptions is higher — but the footnote doesn't support the headline as written.)

**Honest rewrite:** Either change the headline to "$78K+" (which matches the footnote
floor) and update the footnote, or change the footnote to "contractors missing
~3 calls/week" to match $45K at $300/job. Also add the implicit assumption that
every missed call would have become a booked job (which is not stated).

---

### P2-4 · Homepage "live · missed-call → booked" and "live · your morning briefing" labels on static mockups

**File:** `templates/onboarding.html:123`, `188`
**Quoted claim:**
> `"live · missed-call → booked"` (label on the phone screenshot mockup)
> `"live · your morning briefing"` (label on the morning briefing mockup)

**Why it is slightly wrong:**
Both are static HTML mockups — hardcoded demo data (Maria, Dave, Janelle, $1,850,
"Downtown"). The word "live" on a marketing page conventionally signals "this is
a real/actual data feed." A viewer could reasonably interpret these as showing
real FirstBack data in real time. The phone thread mockup is fine as a product
demo illustration, but the "live ·" prefix is potentially misleading.

**Honest rewrite:** Change to `"example · missed-call → booked"` or `"demo · your
morning briefing"` to make it unambiguous these are illustrations.

---

### P2-5 · "Pro" plan includes "Priority support" — undefined and unimplemented

**File:** `templates/pricing.html:96`
**Quoted claim (with green checkmark):**
> "Priority support"

**Why it is misleading:**
There is no support ticketing system, no SLA, no documentation of what "priority
support" means, and no code that differentiates support handling by plan. Listing
it as a checkmark feature implies Pro subscribers receive something Starter
subscribers do not. No such differentiation exists.

**Honest rewrite:** Remove or rephrase: "Direct support from the team" (if that's
the intent and genuinely offered to all plans, just move it to the Starter column
or remove the tier distinction).

---

### P2-6 · "Second phone number for $20/mo" add-on — not implemented

**File:** `templates/pricing.html:88`
**Quoted claim:**
> "(need a second? <a href="/contact">add one for $20/mo</a>)"

**Why it is misleading:**
There is no second-number add-on in the billing system, no multi-number schema in
`db.py`, and no UI for managing additional numbers. The `/contact` link sends the
customer to a contact form. This reads as an available purchase option, not a
"contact us for a manual arrangement." If this is intentional (manual concierge
billing), the wording should reflect that.

**Honest rewrite:** "Need a second number? <a href="/contact">Contact us.</a>"
(Drop the "$20/mo" until it is a real billed product.)

---

### P2-7 · OG/SEO meta still lacks `og:image` — stated as omitted but could affect link previews

**File:** `templates/onboarding.html:8` (comment), `templates/microsite.html:11`
**Issue:**
`onboarding.html` comment: "og:image omitted until /static/og-default.png is
generated." `microsite.html:11` has `<meta property="og:image"
content="/static/og-default.png">` referencing a file that SETUP_NEEDED.md confirms
does not yet exist ("Generate /static/og-default.png"). The microsite OG tag will
return a 404 for `og:image` in production.

**Fix:** Either generate the file (SETUP_NEEDED.md tracks this) or remove the
`og:image` from `microsite.html` until the asset exists.

---

### P2-8 · Landing page (`/landing`) has "Texted back in 4 seconds" — a hardcoded specific number presented as measured

**File:** `templates/landing.html:48`
**Quoted claim:**
> `<div class="mk-sms-meta">Texted back in 4 seconds</div>`

**Why it is slightly wrong:**
The live homepage (`onboarding.html`) correctly changed this to "texted back in
seconds" (no specific number). The `landing.html` page still shows the precise "4
seconds" which was flagged in SITE_TRUTH_AUDIT as C5. SETUP_NEEDED.md notes that
`landing.html` is an unrouted dead page — but it is technically in the repo and
reachable if routed. Keep "in seconds" or delete `landing.html` (as recommended).

---

## Severity Summary

| Priority | Count | Top Issues |
|----------|-------|-----------|
| P0 | 4 | +$12 add-on doesn't exist; annual plan not purchasable; Crew features phantom; calendar is not plan-gated |
| P1 | 9 | "No per-call fees Ever" breaks when voice deploys; billing copy makes promises with no billing system; voice features use checkmarks in beta; $45K footnote math is inconsistent; customer stories promised but empty |
| P2 | 8 | "live" labels on mockups; "most contractors" without population; "priority support" undefined; "$20/mo second number" not implemented; og:image 404 |

---

## Top 5 (by business risk)

**1. P0-1 — "+50 for $12" in-app link (command.html:177)**
Any subscribed user nearing their quota sees a purchase link for a product that
does not exist. This is an active promise made inside the paid product. Highest
priority: remove or disable this link immediately.

**2. P0-2 — Annual plans displayed but not purchasable (pricing.html:68,83,104)**
The pricing page prominently shows annual discounts ($950/$1,910/$3,830) but
every Subscribe button hardcodes `interval=month`. A customer who chooses annual
to save $238-$958 will be enrolled in monthly billing. This is a billing accuracy
failure that becomes a real financial harm once Stripe is live.

**3. P0-3 — Crew plan sells features that do not exist (pricing.html:101-114)**
Four green-checkmark features ("Up to 5 phone numbers," "Multiple business
profiles," "Team roles & logins," "Dedicated onboarding") have no implementation.
A $399/mo subscriber is buying things that cannot be delivered.

**4. P1-1 — "No per-call or per-minute fees. Ever." (pricing.html:37)**
The word "Ever" is an absolute that will be false when voice callback is deployed
at 25¢/30 seconds. This creates a contractual-expectation risk.

**5. P1-7 — Resources page promises customer stories that do not exist (resources.html:22)**
"How painters, plumbers, and HVAC crews booked more work" implies existing case
studies. The destination page (`customers.html`) explicitly says there are none.
This is a bait-and-switch on a linked resource.

---

## What the code gets right (honesty wins)

- Billing CTA gated on `billing_live` — no Subscribe button shown when Stripe is unconfigured.
- Voice callback honestly marked "beta" / "not yet available" in most places (pricing, homepage JS).
- SMS gated on A2P approval — no real texts sent until carrier registration is approved.
- Customer stories page: zero invented testimonials; honest placeholder with "no invented quotes."
- Settings accurately shows "Coming soon" for unset integrations (Apple, Yahoo, unkeyed Google/Outlook).
- Daily cost cap degrades honestly ("resting" message) rather than silently breaking.
- Webinar page no longer lists a fake dated event.
- The homepage "works with" section correctly omits Jobber/Housecall Pro (removed in prior audit).

---

_Report generated by Red-Team Lane 2 (Honesty & Accuracy). Lane 1 (code bugs),
Lane 3 (security/compliance), and Lane 4 (UX/gaps) are out of scope here._
