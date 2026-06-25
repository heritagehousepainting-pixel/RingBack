# Red-Team Lane 4 — Gaps, UX & Product Completeness
**FirstBack · /Users/jonathanmorris/Documents/apps/firstback**
**Date:** 2026-06-25 · **Auditor:** Lane 4 (read-only, no files modified)

---

## Methodology
Read every template, the full app.py route surface, all CSS files, SETUP_NEEDED.md, DEV-HANDOFF-2026-06-23.md, and all BRAIN/ROADMAP/REVAMP/SETUP planning docs. Cross-referenced against the five named competitors (Goodcall, Rosie, Jobber AI Receptionist, LeadTruffle, Podium). Graded by user impact and whether the problem is a broken flow, a missing self-serve action, or a competitive gap.

---

## P0 — Blocks a user / broken core flow

### P0-1: Dead link on Growth Tray — "Back to command center" goes to 404
**File:** `templates/growth_tray.html:139`
```html
<a href="/command-center" ...>&larr; Back to command center</a>
```
**Problem:** No route `/command-center` exists. The signed-in command center is `/dashboard`. An owner who launches a seasonal campaign and then tries to navigate back hits a 404.
**User impact:** Disorientation after completing an action. Growth Tray is a conversion-critical screen (TCPA approvals). A broken back-nav on this screen signals immaturity.
**Fix:** Change href to `/dashboard`.

---

### P0-2: No billing self-service in the app — "Subscribe" button is unwired
**File:** SETUP_NEEDED.md line 369, `templates/pricing.html` (plan_cta macro), `templates/settings.html` (no billing section)
**Problem:** The backend billing code is complete (Stripe checkout/portal/webhook). The pricing page has a CSRF-guarded `plan_cta` macro that correctly renders a Subscribe form when `billing_live=True`, but `billing_live` is False because the Stripe Price IDs are not configured. The Settings page has zero billing section — no current plan display, no upgrade button, no "Manage billing" link to Stripe Portal. After a contractor signs up and pays by Payment Link (the workaround), they have no in-app way to upgrade, downgrade, check their plan, or cancel their subscription.
**User impact:** P0 business risk — "Cancel anytime" is a promise on the pricing page and in the FAQ (`templates/help.html:32–33`), but the mechanism to cancel is absent. A contractor who wants to cancel must email or call. This triggers chargebacks and trust erosion. For any live subscriber this is a legal/support liability.
**Fix:** Wire the billing portal button (POST to `/billing/portal`) into Settings as a "Manage billing" card. Show current plan and renewal date from `db.get_business(biz_id)` or a billing lookup. The checkout route and CSRF guard are already built; they just need a form wired in the UI.

---

### P0-3: Pricing page — Annual billing toggle exists visually but is cosmetic
**File:** `templates/pricing.html:37, 68, 83, 104`
**Problem:** The pricing page prominently says "Save 20% when you pay annually" and shows both monthly and annual prices side-by-side as static text. There is no interactive toggle. When `billing_live=True` and the user clicks Subscribe, the hidden input `name="interval" value="month"` is always hardcoded to monthly. There is no UI affordance to choose annual billing despite the annual price being displayed.
**User impact:** An owner who reads "Save $238 annually" and clicks "Get started" is checked out at the monthly rate. They will feel deceived when they see the monthly charge. **This is a trust-destroying moment at the payment wall.**
**Fix:** Add a toggle (radio or segmented control) that switches the displayed price and updates the hidden `interval` field between `month` and `year` before form submission. The checkout route already handles `interval`.

---

### P0-4: Crew tier advertises "Team roles & logins" — feature does not exist
**File:** `templates/pricing.html:111`
```html
<li>{{ check }} Team roles &amp; logins</li>
```
**Problem:** The `users` table has no role or permission columns (`db.py:220–224`). There are no invite-a-teammate routes anywhere in app.py. There is no team management UI. A Crew subscriber paying $399/mo expecting to add team members hits a dead end.
**User impact:** P0 honesty violation + refund trigger. A feature listed as included in a paid tier must exist. Misrepresenting a feature to induce purchase is a regulatory risk (FTC) and a chargeback.
**Fix (immediate):** Remove "Team roles & logins" from the Crew feature list OR label it "Coming soon — contact us." Long-term: build multi-user (invite by email, admin/member role on the users table).

---

### P0-5: 404 page links unauthenticated users to /dashboard, causing a redirect loop
**File:** `templates/errors/404.html:42`
```html
<a class="error-link" href="/dashboard">Go to Dashboard</a>
```
**Problem:** An unauthenticated visitor who hits a 404 (e.g. follows a stale link) clicks "Go to Dashboard" → `/dashboard` requires `@login_required` → redirects to `/login`. The user is sent to a login page with no explanation. The 404 page doesn't check auth state.
**User impact:** Confusing two-step redirect for logged-out users. The correct CTA for an anon visitor is "Go to homepage" or "Sign up."
**Fix:** Change the 404 CTA to `/` (homepage). Optionally render two CTAs conditionally if you pass `current_user` to the error template.

---

## P1 — Significant gap, damages trust or blocks conversion

### P1-1: No billing management page anywhere in the app shell
(See P0-2 — the gap extends to plan display, upgrade path, and invoice history)
**Additional sub-gaps:**
- No "Current plan: Starter" display anywhere the owner can see
- No upgrade path within the app (must go back to `/pricing` and re-start checkout)
- No invoice/receipt download (Stripe Portal would fix this)
- `/billing/portal` is implemented but has no UI entry point anywhere

---

### P1-2: No self-serve account deletion
**Location:** No route, no template, no database call
**Problem:** The Privacy Policy (`templates/privacy.html`) must describe a right to delete, but no delete-account flow exists. An owner who wants to leave must contact support. For SaaS at any scale, this is a CCPA/GDPR readiness gap.
**User impact:** Operators handling a cancellation request have no tool. Angry former customers can file disputes.
**Fix:** Add a "Delete account" section to Settings (dangerous action, confirm dialog with typing "DELETE", server-side removes business+users+leads or marks them for purge).

---

### P1-3: No data export for leads / customer book
**Location:** No export route, no CSV download in dashboard or customer book
**Problem:** Competitors (Jobber, Podium) all provide data export. A contractor who wants to migrate or keep their own records has no self-serve way to download their lead list or conversation history. The customer book (`/customers`) displays data but has no export button.
**User impact:** Switching cost objection ("what happens to my data if I leave?") cannot be answered. Contractors on Pro/Crew who have hundreds of leads are locked in by inability to extract data, which could be framed negatively.
**Fix:** Add a CSV download endpoint `GET /api/leads/export` (auth-gated, tenant-scoped) and a "Download CSV" button on the customer book and pipeline pages.

---

### P1-4: No email verification on signup
**Location:** `app.py:313–361` (signup route)
**Problem:** An owner signs up with any email address. No verification email is sent. The email is trusted immediately for alert delivery. This creates:
1. Anyone can sign up with someone else's email (impersonation / typo risk)
2. Alert emails go to an address that may not belong to the owner
3. Password reset emails go to an unverified inbox
**User impact:** A mistyped email during signup → alert emails lost → owner complains FirstBack isn't alerting them. Also a basic security gap (malicious signup with another person's email).
**Fix:** Send a verification email on signup (reuse the `mail.send_email` + token pattern already built in `auth_forgot`). Block alerts until verified, or at minimum surface an "unverified" banner.

---

### P1-5: "How do I upgrade or change plans?" — Help FAQ promises a self-serve path that doesn't exist
**File:** `templates/help.html:33`
> "Switch plans from your account at any time; changes take effect on your next billing cycle."
**Problem:** No such in-app switch path exists. The help article creates an expectation the product cannot fulfill.
**User impact:** An owner who reads the help center and tries to upgrade will search for the UI, find nothing, and lose trust. This is the moment a support ticket or chargeback begins.
**Fix:** Either remove this FAQ answer until billing management UI is live, or replace it with "Contact us to switch plans" + a link to `/contact`.

---

### P1-6: Settings page has no "current plan" / usage display
**File:** `templates/settings.html` (entire file reviewed)
**Problem:** A contractor who's signed up has no dashboard-level view of: their current plan tier, how many replies they've used this month vs. their limit, next billing date, or a way to upgrade. The `/api/usage` endpoint exists and is used by the command center fuel gauge, but Settings surfaces none of this.
**User impact:** An owner hitting the daily cap sees a "you've hit today's limit" message in the command center but has no self-serve way to understand their plan limits, view usage history, or upgrade.
**Fix:** Add a "Plan & usage" card to Settings showing plan name, conversations used/remaining (from `/api/usage`), renewal date, and an upgrade/manage link.

---

### P1-7: First-run experience (new user after signup) sends user to `/setup` with no onboarding guidance
**Location:** `app.py:360` → `/setup`, `templates/setup.html`
**Problem:** A brand-new contractor lands on `/setup` with the 4-step Go-Live wizard. The wizard itself is good. But:
1. The user's business name/trade defaults are whatever they typed during signup — often incomplete (e.g. "Your service area" as the literal default)
2. The AI instructions field is pre-filled with a generic system default — the owner has no prompt to personalize it before going live
3. The "optional" items (calendar, contacts, Jobber) are behind an Advanced section that many will skip, but the AI is significantly less useful without them
4. There is no "what to expect next" guidance after completing setup — the owner transitions to `/dashboard` with no explanation of the command center
**User impact:** First-run churn risk. A contractor who completes setup but hasn't configured their AI voice will have a mediocre first text-back experience.
**Fix:** Add a brief welcome state to the dashboard for new users (first N days) explaining what they're looking at. Prompt for AI instructions during setup if the default is unchanged.

---

### P1-8: "Multiple business profiles" listed as Crew feature — not implemented
**File:** `templates/pricing.html:109`
```html
<li>{{ check }} Multiple business profiles</li>
```
**Problem:** The app supports exactly one business per account. There is no multi-business architecture (each user row has one `business_id`, no org/workspace layer).
**User impact:** Same as P0-4 (Crew tier misrepresentation). A multi-location shop who pays $399 expecting to manage two locations will be unable to.
**Fix:** Remove or label as "Coming soon" immediately. The architecture (tenant = business_id) would require significant refactoring to support multiple business profiles per login.

---

### P1-9: Setup wizard "EIN on file" summary shown even for sole proprietors who have none
**File:** `templates/setup.html:217`
```html
{%- if s.key == 'profile' -%}<strong>{{ business.name }}</strong> — EIN on file
```
**Problem:** When a sole proprietor (who checked "I have an EIN" as False during signup) completes step 1 of setup, the collapsed "done" summary always shows "EIN on file" regardless of whether they entered one. This is a factual inaccuracy for sole proprietors.
**User impact:** A sole-prop contractor sees "EIN on file" and is confused — they didn't enter one. Minor trust issue.
**Fix:** Conditional: `{% if business.ein %}EIN on file{% else %}Profile complete{% endif %}`.

---

### P1-10: No notification/inbox for the owner within the app when away
**Location:** No web push, no in-app notification center
**Problem:** The app sends SMS/email owner alerts when a lead arrives. But if an owner is already logged in and on the dashboard, the 25s poll refreshes the briefing feed. If the owner is NOT logged in, there's no push path (SETUP_NEEDED.md explicitly calls this out as deferred). Competitors like Goodcall and Podium have mobile apps or web push.
**User impact:** A contractor on a job site, app closed, gets an SMS alert but can't act on it easily. First-response speed (the app's core promise) depends on the owner seeing the SMS.
**Note:** This is acknowledged as deferred in SETUP_NEEDED.md. Still worth documenting as a competitive gap that will surface in real use.

---

## P2 — Polish / UX quality gaps

### P2-1: Pricing page annual billing shown as static display only — no interactive toggle
(Covered in P0-3 but the UX quality issue: two price options shown in gray sub-text are visually buried and may not be noticed at all at smaller viewport widths)

---

### P2-2: `og:image` missing on all pages — social sharing cards show no image
**File:** `templates/onboarding.html:8` (comment), `templates/marketing_base.html:7` (comment)
**Problem:** Both templates explicitly omit `og:image` with a note that `/static/og-default.png` hasn't been generated. Every page shared to Slack, iMessage, Facebook, LinkedIn shows a text-only card with no preview image.
**User impact:** Word-of-mouth social sharing shows a blank preview. For a product aimed at contractors who often share via SMS/iMessage, this is a real conversion gap.
**Fix:** Generate the 1200×630 OG image (SETUP_NEEDED.md already calls this out). Takes ~1 hour.

---

### P2-3: Blog, Webinars, Guides — all placeholder content, no real articles
**Files:** `templates/blog.html` (3 short articles, no dates, no author), `templates/webinars.html` ("Coming soon"), `templates/guides.html` (FAQ-only)
**Problem:** These pages are linked from the main nav. The blog articles have placeholder dates (June 2026) that are current but articles are very short (2 paragraphs). The webinars page is explicitly "Coming soon." Guides are accordion-only with no downloadable content.
**User impact:** Visitors who click "Resources" to evaluate FirstBack find thin content, which signals early-stage risk to a sophisticated buyer. The webinars dead-end says "Get notified" → `/contact` → manual.
**Fix:** Either hide these pages from the main nav (route to 404 / redirect to `/contact`) until real content exists, or accept the current state and invest in 3–5 real blog posts.

---

### P2-4: Customer Stories page is explicit placeholders
**File:** `templates/customers.html`
**Problem:** SETUP_NEEDED.md acknowledges "real customer stories are placeholders today." The page renders but shows no real testimonials or case studies.
**User impact:** A prospective customer who clicks "Customer stories" in the nav to evaluate social proof finds nothing. Competitors (Podium, Jobber) have real case studies and video testimonials.
**Fix:** The current solution (honest placeholders) is better than fabricated quotes. But the nav link should be removed or the page should say "Coming soon — we're onboarding our first contractors" rather than surfacing a dead page.

---

### P2-5: Webinar page still linked via "contact us to get notified" with no actual notification mechanism
**File:** `templates/webinars.html:17`
> `<a class="ob-btn ob-btn-accent ob-btn-lg" href="/contact">Get notified</a>`
**Problem:** "Get notified" points to a generic contact form. There is no email list signup, no webhook trigger, no automated notification. An owner who submits the contact form expecting webinar notification gets a manual reply from someone at FirstBack.
**Fix:** Add a simple email capture form (separate from general contact) or connect to Mailchimp/ConvertKit. For now the lowest-lift fix is relabeling the CTA "Contact us" or removing the page from the nav.

---

### P2-6: Settings page has no visual grouping or anchor navigation for mobile users
**File:** `templates/settings.html` (full page review)
**Problem:** Settings is a single very long page with 12 cards. Desktop users can use `#anchor` deep links from the setup wizard. On mobile (<640px), the page collapses to a single column with no section jump-links or sticky sub-nav. A contractor on mobile scrolling through 12 cards to find "Call screening" is a bad experience.
**User impact:** Mobile contractors (the target demographic — people on job sites) have a poor settings experience.
**Fix:** Add an in-page TOC at the top of settings (links to anchors already exist) that's visible on mobile.

---

### P2-7: The `/growth/tray` "Send All" action has no confirmation step for large batches
**File:** `templates/growth_tray.html:82–86`
```html
<form method="post" action="/growth/tray/release" ...>
  {{ button('Send All', variant='primary') }}
</form>
```
**Problem:** A single tap on "Send All" releases all held growth messages (review requests, win-backs, etc.) to customers. The page shows how many are held, but there is no intermediate "Are you sure? You're about to send N texts" confirmation before submission.
**User impact:** A contractor who accidentally taps Send All blasts their entire customer base. This is especially risky on mobile.
**Fix:** Add a JS confirmation dialog (`confirm("Send all N texts? This can't be undone.")`) or require typing a number before submitting. The per-skip flow exists (`/growth/tray/skip/<id>`) but there's no partial-send or undo.

---

### P2-8: Alert settings show quiet hours as raw 24h numbers — no time-of-day preview
**File:** `templates/settings.html:380–382`
```html
{{ field('Quiet hours start (24h)', name='alert_quiet_start', value=..., type='number', help='Hold non-urgent texts after this hour. ...') }}
```
**Problem:** The owner types 22 and 7 into number fields. There is no preview showing "Texts held from 10:00 PM to 7:00 AM" in the owner's timezone. The help text says "24h" but doesn't explain the format clearly for non-technical users.
**User impact:** A contractor might type the wrong value or not understand the format. Misconfigured quiet hours could mean missing urgent leads or texting customers at 3am.
**Fix:** Add a live preview line that formats the start/end as human-readable time: "Texts held from 10:00 PM → 7:00 AM in your timezone."

---

### P2-9: Empty state on Customer Book redirects to /pipeline, not an onboarding action
**File:** `templates/customer_book.html:47–51`
```
{{ empty_state('Your customer book is empty — for now',
   'Every estimate FirstBack books adds a customer here...',
   action_label='See your pipeline', action_href='/pipeline') }}
```
**Problem:** For a brand-new user, the customer book is empty. The empty state CTA sends them to the pipeline (also empty). A better CTA would be "Complete your setup" or "Run a test conversation."
**User impact:** New user navigation dead-end. A chain of empty → empty states reinforces "nothing works yet."
**Fix:** For users pre-go-live (`not connections.is_live(biz)`), the CTA should be "Finish setup" pointing to `/setup`.

---

### P2-10: Access to /settings/growth_mode via Settings page has a separate form — Save All doesn't save it
**File:** `templates/settings.html:446–473`
**Problem:** The Growth Autopilot card is a separate `<form method="post" action="/settings/growth_mode">`. But it's visually embedded in the main Settings flow, with its own Save button labeled just "Save" (secondary variant). A contractor who scrolls to the bottom and clicks the main "Save changes" button (which submits the main settings form) does NOT save their growth mode selection.
**User impact:** Confusing dual-form layout. A contractor who picks "Morning Tray" and then clicks the main "Save changes" sees "Changes saved" but growth mode wasn't included.
**Fix:** Add a clear visual separator (card head, distinct section header) before the Growth Autopilot section, or consolidate into the main form. Alternatively, label the Growth mode Save button more distinctly ("Save growth mode").

---

### P2-11: ROI page — "Estimated return" tile hidden until data loads; no loading skeleton
**File:** `templates/analytics.html:17`
```html
<div id="roi-headline" ... style="display:none">
```
**Problem:** The ROI page starts with a blank area above the chart while JS fetches `/api/analytics`. For a new user with no data, the headline tile stays hidden permanently (roi_multiple is null). There's no loading state and no empty-state explanation for the headline tile area.
**User impact:** A new owner sees an incomplete-looking page. The empty chart area with no "you haven't caught any leads yet" message is jarring.
**Fix:** Add a loading skeleton on page load, then an explicit empty state ("Your first booked estimate will appear here") when the API returns zero leads.

---

### P2-12: The 404 page uses `style.css` (legacy stylesheet) instead of `ui.css`
**File:** `templates/errors/404.html:10`
```html
<link rel="stylesheet" href="/static/style.css">
```
**Problem:** Every other page in the app uses `ui.css` and the design system tokens. The 404 page references `style.css` (the legacy stylesheet) with CSS variables like `var(--accent)` and `var(--ink)` that may or may not be defined in `style.css`. There is no guarantee of visual consistency.
**User impact:** Minor visual inconsistency. Potentially broken styling if `style.css` doesn't define the color tokens referenced in the inline styles.
**Fix:** Replace `style.css` with `ui.css` + `app.css` on the error pages.

---

## Competitive Gaps (vs. Goodcall / Rosie / Jobber AI Receptionist / LeadTruffle / Podium)

### CG-1: No live inbound answering (Goodcall, Rosie primary feature)
Goodcall ($79–$249/agent/mo) and Rosie ($49–$299/mo) answer calls live before they miss. FirstBack only recovers after the miss. The voice callback feature is built but not deployed. Until `FIRSTBACK_VOICE_URL` is live and `inbound_voice_enabled` is toggled on, FirstBack cannot compete on "live phone answering." This is the single largest competitive perception gap.
**Current honest status:** "Coming soon (beta)" copy is in place — this is good. But the gap remains real.
**Recommendation:** Prioritize the voice service deploy (render.yaml `firstback-voice` block). Cost is ~$7/mo for the service.

---

### CG-2: No mobile app / PWA (all competitors)
Goodcall, Rosie, Podium, and Jobber all have mobile apps. FirstBack is responsive web-only. Contractors are on job sites on phones. The responsive design is solid (900px and 640px breakpoints), but there is no "Add to home screen" PWA manifest, no push notifications, and the mobile nav collapses to a horizontally-scrollable tab bar which is functional but not app-like.
**Impact:** A contractor who adds the app to their home screen gets a browser-looking experience. App Store presence = perceived legitimacy for B2B SaaS in trades.
**Recommendation:** Add a `manifest.json` + service worker for basic PWA (installable, offline fallback). Doesn't require App Store.

---

### CG-3: No CRM / contact history for leads (Jobber, Podium)
The Customer Book shows repeat customers and job count, but there's no detailed contact record view: no notes field, no call log, no linked jobs-per-customer, no "tag as VIP." Competitors like Podium and Jobber have full contact profiles.
**Current state:** Leads have a name, phone, and an AI-summarized conversation note (`summary` column). But these aren't browsable per-contact.
**Recommendation:** At minimum, add a click-through from the customer book to see full conversation history for that customer (linking via phone number across all their leads).

---

### CG-4: No internal review / notes for booked estimates (Jobber)
After booking an estimate, the only internal record is the appointment row. There is no place for the owner to add internal notes about the job (materials needed, special access instructions, etc.) before the estimate visit.
**Recommendation:** Add a "job notes" field on the appointment/lead detail view in the pipeline.

---

### CG-5: No multi-number per account below Crew tier (Rosie, Goodcall)
Rosie and Goodcall let you add numbers per agent/seat at their lower pricing tiers. FirstBack's Starter and Pro show "1 phone number" as a hard limit. For a contractor who wants to separate residential and commercial lines, there's no path below $399/mo.
**Recommendation:** The pricing note "need a second? add one for $20/mo" (Pro tier) is the right direction but it's unclear and has no wiring.

---

### CG-6: No review response / review management dashboard (Birdeye, Podium)
Podium and Birdeye are specifically strong on reputation management (review requests, star ratings, responding to negative reviews). FirstBack's Google reputation tracking exists (`api/reputation`) but is read-only and only surfaces a count. There's no review-request campaign visible in the UI (growth tray includes it but only in Morning Tray mode), and no response drafting.
**Current state:** `SETUP_NEEDED.md` documents this as deferred (needs GBP connector).

---

### CG-7: No web chat that converts to SMS thread (LeadTruffle, GoHighLevel)
The `widget.js` web-chat widget exists and is buildable (Batch G). But:
- It requires the owner to manually flip a toggle in Settings AND paste an embed script
- The widget generates a lead but there's no in-app preview of what the chat looks like from a website visitor's perspective
- There's no sandbox/preview of the widget in the app
**Recommendation:** Add a widget preview modal in Settings when the widget is enabled, so the owner can see what visitors will see before embedding it.

---

### CG-8: No Zapier / Make integration or public webhook documentation
Podium and Goodcall both have Zapier integrations. FirstBack has a webhook URL field in alert settings (sends JSON on lead/booking events) but there's no documentation of the payload format. An owner who sets a webhook URL sees no schema, no test-send button, no delivery log.
**Recommendation:** Add a "Test webhook" button in Settings that POSTs a sample payload to the configured URL. Add a brief inline payload spec.

---

## Accessibility Spot-Check

The core design system shows solid a11y thinking (aria-labels, sr-only labels on colored pills per SETUP_NEEDED.md Phase 5 notes). Key remaining gaps:

- **`templates/errors/404.html`:** Uses `<p class="error-code">404</p>` — should be `<h1>` or have a visually-hidden heading before the decorative 404. Screen reader reads "404" as content before the h1.
- **`templates/settings.html` toggle inputs:** The `alert_toggle` macro creates `<label class="toggle"><input type="checkbox">`. The toggle has a custom track/thumb but no visible `<span>` text that would be separately hit by screen readers when not labeled. The toggle label text is inside the same `<label>`, which is correct, but there is no `role="switch"` and no `aria-checked` on the custom visual element (though `input[type=checkbox]` handles this natively, the custom `span.toggle-track` may confuse some screen readers).
- **`templates/onboarding.html:33`:** The logo `<img src="/static/firstback-mark-light.svg" ... alt="">` has empty alt text — correct for a decorative logo when the text "FirstBack" is adjacent. Confirmed acceptable.
- **`templates/growth_tray.html`:** The streak progress bar (`<div style="height:8px">`) has no aria label for its current value — a screen reader user cannot determine progress toward auto-unlock.
- **Color contrast:** The `var(--ink-faint)` color used on `.stat-sub`, `.briefing-last`, and `.dt-muted` should be verified at 3:1 minimum against `var(--bg)`. SETUP_NEEDED.md Phase 5 notes a11y fixes were applied, but the audit found contrast was addressed on chips/buttons — the faint text in data tables should be separately validated.

---

## Severity Summary

| Priority | Count | Worst impact |
|---|---|---|
| P0 (breaks flow or honesty) | 5 | Crew tier selling non-existent features; broken back-nav; billing unsubscribable |
| P1 (significant gap) | 8 | No data export; no email verify; no billing management; conflicting FAQ |
| P2 (polish/UX) | 12 | Growth tray no confirmation; pricing toggle cosmetic only; empty states; dead page links |
| Competitive gaps | 8 | No live inbound answering; no mobile app/PWA; no CRM contact records |

---

## Top 5 to Fix First

1. **P0-4 + P1-8 (Crew misprep):** Remove "Team roles & logins" and "Multiple business profiles" from pricing.html immediately. These are fabricated feature claims on a paid tier.

2. **P0-2 + P1-6 (No billing self-management):** Wire `/billing/portal` into Settings as "Manage billing." Without it, "Cancel anytime" is an empty promise and every cancellation is a manual support ticket.

3. **P0-3 (Annual billing toggle is cosmetic):** The pricing page shows annual prices but always checks out at monthly. Fix the toggle before any real billing goes live — discovering this on a credit card statement destroys trust.

4. **P0-1 (Dead /command-center link):** One-line fix in `growth_tray.html:139`. Change to `/dashboard`. A broken back-nav on a TCPA-sensitive screen is embarrassing.

5. **P1-4 (No email verification):** Signup accepts any email and immediately uses it for alerts and resets. A mistyped email = owner gets no alerts = product failure = churn. Reuse the existing token/mail infrastructure from `auth_forgot`.

---

*Report written 2026-06-25 by Red-Team Lane 4. No files in the repo were modified.*
