# Onboarding & Time-to-First-Value Audit
## FirstBack Product Review — Lane 01

**Reviewer scope:** signup → /setup wizard → first "aha" moment  
**Method:** Read actual code: templates/auth.html, templates/onboarding.html, templates/setup.html, app.py (signup + setup routes), connections.py (step_state, is_live, CARRIER_FORWARD_CODES, a2p_sync), compliance.py (launch_blockers), messaging.py (send_sms gate).  
**Honest benchmark:** "More than enough to stay." Dave test: non-technical painter, wants set-and-forget. Reference bar: Calendly, Podium, Jobber — products Dave's peers actually use.

---

## The Journey as Dave Walks It

### Step 0: Landing (/)
Dave lands on `onboarding.html`. Hero is clear: "Every missed call, booked by AI in seconds." The phone-mockup conversation is the right move — concrete proof of value before any commitment. The segmented Text/Call toggle adds friction for zero gain (Call mode says "coming soon" and tells Dave nothing works yet). Minor but sets a slightly confused tone before he even signs up.

The hero CTA collects a phone number inline, then `action="/signup"` passes it as a GET param. But the signup form (`auth.html`) **does not render a phone field** — the `phone` value is accepted by the backend (`request.form.get("phone")`) only if it arrives via POST, which it does not. The phone Dave typed on the landing page is silently dropped. His alert_sms stays blank at signup, so day-one SMS alerts never fire.

### Step 1: Signup (/signup → auth.html)
4 fields: business name, your name, email, password. Clean. Fast. No trial language on the form itself (pricing page FAQ says "cancel anytime" but Dave won't have read it).

One hidden logic error: the backend reads `has_ein` from the signup form to set `business_type` (`"llc"` if has_ein else `"sole_prop"`). The signup form **has no `has_ein` checkbox**. So every new user is tagged `sole_prop` at signup regardless of business structure. This creates a downstream contradiction in Step 1 of the wizard (see below).

No welcome email sent on signup. Dave gets zero confirmation that anything happened except a redirect.

**Time to complete signup:** ~2 minutes. No friction.

### Step 2: /setup Wizard — The Core Gauntlet

The wizard has 4 sequential steps, rendered as a vertical stepper. The first actionable step auto-opens. This is the right pattern.

#### Wizard Step 1 — "Your business" (profile)
**Fields shown:** business name, trade, owner name, service area, **legal business name**, **EIN (business tax ID)**, **business address**, website (optional).

8 fields. 3 of them (legal name, EIN, address) exist solely to satisfy carrier A2P registration — Dave has no idea why he's being asked for his tax ID to set up a text-back service. The EIN field has `required=true` in the HTML (browser enforces it), **but** the backend `_profile_done()` exempts `sole_prop` businesses from the EIN requirement. Since every new user is tagged `sole_prop` at signup (no `has_ein` checkbox in auth.html), the backend will accept the form without EIN — but the browser will block submission if Dave leaves it blank.

**Drop-off risk:** Dave the painter doesn't have his EIN memorized. The help text says "A sole proprietor can register with their EIN" — correct, but still implies he needs one. He quits the tab. **This is the single highest-friction point in the entire onboarding flow.**

The fix is two lines: remove `required=true` from the EIN field for `sole_prop` businesses (the backend already handles the exemption). Alternatively, make the EIN field conditional on `business.business_type != 'sole_prop'`. The signup form should also collect the `has_ein` checkbox to correctly set business type.

**Time to complete if Dave has all info at hand:** ~5 minutes. Without EIN: indefinitely stalled.

#### Wizard Step 2 — "Your FirstBack number" (number)
Dave picks an area code, sees up to 5 available numbers, clicks "Buy this number." Clean flow. The system auto-wires webhooks via `provision_number`. 

**Small friction:** if Twilio isn't configured server-side, the UI shows "Connecting to our phone provider… check back in a minute. (Twilio isn't configured on the server yet.)" — that's technically honest but alarming and unexplained. Dave thinks something is broken.

**Time to complete:** ~2 minutes. Acceptable.

#### Wizard Step 3 — "Carrier registration (A2P)" — THE WALL
The step title says **"Carrier registration (A2P)"** — the code comment literally says "Zero Twilio/A2P/10DLC/TCR/brand/campaign jargon visible to the contractor," but "A2P" appears in the rendered `_STEP_TITLES["a2p"]` heading that every user sees. Minor jargon breach, but it erodes trust.

The real problem: clicking "Activate texting" submits to `/setup/a2p`, which calls `connections.submit_a2p()` → Twilio Trust Hub API. Then Dave waits **1–3 business days** for carrier approval. The UI says "usually within a day." During that wait:

1. The system records leads (calls come in, leads are created in the DB).
2. `send_sms()` returns `"blocked"` (status `a2p_not_approved`) for all customer-facing texts.
3. The blocked messages are **queued** in `blocked_sends` and **will replay** when A2P approves — this is genuinely good engineering.
4. But `_missed_call_textback()` still returns `True` (engaged) even when the SMS was blocked.
5. The TwiML voice response says: **"Sorry we missed you. We just sent you a text message. Goodbye."** — but **no text was sent**. The caller hears a lie. This is a material honesty failure during the A2P wait window.

Dave is also never notified when A2P approves. `a2p_sync_all()` runs on the `/tasks/run-due` cron tick, auto-flushes blocked sends, and sets `a2p_status = "approved"` — but no email or SMS fires to Dave. He finds out by refreshing `/setup`. If he set-and-forgot, he could go days without knowing he's actually live.

Step 3 and Step 4 (forwarding) are correctly marked as **independent prerequisites** — Dave can set up call forwarding while waiting for A2P. The UI correctly shows both as "Ready" in parallel. This is good.

**Time to complete:** 1 click → then 1–3 day wait. Irreducible but the experience around it is weak.

#### Wizard Step 4 — "Forward your missed calls" (forwarding)
Dave picks his carrier from a dropdown (Verizon, AT&T, T-Mobile, US Cellular, Other/GSM). The exact star code is shown with the FirstBack number pre-filled (e.g., `*71+12675551234`). A "Tap to dial it" link is provided. Dave clicks it, his phone app opens with the code pre-dialed. Hits call. Done.

Then he clicks "I've set up forwarding." A sentinel call is placed to verify forwarding is actually live (`send_sentinel_call`). If the sentinel returns, `forwarding_confirmed` is set True (the only honest path — not self-attested). The UI shows "Setup complete — make a test call to confirm."

This is the best-designed step of the four. The "Tap to dial" UX is the kind of friction removal that Dave needs. The sentinel verification is technically solid.

**One gap:** if the sentinel fails (no `FIRSTBACK_PUBLIC_URL` configured, which is the most likely prod misconfiguration), Dave gets `?unverified=1` in the URL but **the template never renders a message for `unverified` or `saved` or `err` params**. These query params are passed to the template as variables (`saved`, `err`) but are never referenced in `setup.html`. Dave sees nothing — no "something went wrong," no "check your code and try again." Silent failure.

**Time to complete forwarding step (when it works):** ~3 minutes.

#### Post-Wizard: The "You're Live" Moment
When all 4 steps complete AND a test call has been verified, the banner reads: **"You're live. FirstBack is texting back missed calls from [number]."**

This is clear, honest, and correct. But it's just a text banner. No celebration, no email, no "your first call will look like this" primer. Best-in-class SaaS (Calendly, Stripe, Intercom) delivers a "setup complete" email with next steps and what to expect. FirstBack sends nothing.

The "Get the most out of FirstBack" recommended section (calendar, alerts, AI training, screening, reminders) shows immediately below the live banner. It's well-organized. But there's no prioritization for Dave — all 9 rows look equally urgent. The most important next step for day-one revenue (connecting Google Calendar so the AI can actually book time slots) is item 2 in a list of 9, visually indistinguishable from "Set your own password."

---

## Summary Findings

### Finding 1 — EIN required=true for sole_props [IMPACT: HIGH | EFFORT: S]
**What:** The profile step shows EIN as HTML-required for everyone. Every new user is tagged `sole_prop` at signup (no `has_ein` checkbox in auth.html). The backend already exempts sole_props from EIN. The browser blocks form submission unnecessarily.  
**Why it matters:** This is the single most likely drop-off point. A painter sitting in his truck doesn't have his EIN. He closes the tab. Revenue lost.  
**Fix:** Remove `required=true` from the EIN field (the backend validation already handles it correctly). Add the `has_ein` checkbox to the signup form so `business_type` is set correctly from the start. Optionally: make the EIN field conditional on `business.business_type != 'sole_prop'` in the template.

### Finding 2 — Voice says "We sent you a text" when no text was sent [IMPACT: HIGH | EFFORT: S]
**What:** During the A2P approval window (1–3 days), `_missed_call_textback()` returns `True` (engaged), and the TwiML voice response plays: "Sorry we missed you. We just sent you a text message. Goodbye." But `send_sms()` returned `"blocked"` — no text went out.  
**Why it matters:** Every inbound call during the A2P wait window — Dave's first real calls — hears a false promise. Caller expects a text, never gets one (until A2P approves and the queue replays, potentially hours or days later). Customer trust damage on day one.  
**Fix:** Have `_missed_call_textback()` check the return value of `send_sms()`. If `status == "blocked"`, return a different TwiML response: "Sorry we missed you. We'll reach out to you soon." Or: don't play any voice message when blocked.

### Finding 3 — Silent failures on error/saved states [IMPACT: HIGH | EFFORT: S]
**What:** The `/setup` route passes `saved`, `err`, `verifying`, and `unverified` query params to the template. The `setup.html` template never renders any of them. A failed forwarding sentinel, a failed number purchase, a failed A2P submission — all redirect with a descriptive error code, but Dave sees no message.  
**Why it matters:** Dave clicks "Activate texting," gets redirected, nothing visual changes. He clicks again. Support tickets. Churn.  
**Fix:** Add 10–15 lines to `setup.html` mapping the known `err` and `saved` values to human-readable banners (the infrastructure is already there — just unused). Example: `{% if err == 'a2p_submit' %}<div class="setup-banner is-error">We hit a snag...{% endif %}`.

### Finding 4 — No notification when A2P approves / Dave goes live [IMPACT: HIGH | EFFORT: S]
**What:** When `a2p_sync_all()` transitions a business from `pending` to `approved` and auto-flushes blocked sends, no notification fires to the contractor. Dave must remember to check `/setup`.  
**Why it matters:** The most important moment in the product — going live — is invisible to the customer. Dave set-and-forgot after step 4. His AI has been live for 12 hours and he doesn't know. He also doesn't know his first queued leads were just texted. Set-and-forget means he needs a nudge to come back.  
**Fix:** In `connections.a2p_sync()`, on the `pending→approved` transition (after `flush_blocked_sends`), call `alerts.send_alert(biz, "You're live! FirstBack is now texting back your missed calls...")` via both email and SMS.

### Finding 5 — Hero phone CTA drops Dave's phone number [IMPACT: MED | EFFORT: S]
**What:** The landing page hero shows a phone number input that submits to `/signup` via GET. The signup form (`auth.html`) never renders a phone field, and the backend only reads `phone` from POST body — not GET params. Dave's number is lost silently. `alert_sms` stays blank. He never gets SMS alerts on his first lead.  
**Why it matters:** The phone field is the most emotionally resonant CTA on the landing — "try it on your phone." Dave types his number, hits submit, and... nothing. His number wasn't saved. The first inbound lead alert goes nowhere.  
**Fix:** Add `phone` field (hidden or visible) to the signup form, pre-populated from `request.args.get('phone')`. Two lines.

### Finding 6 — "Carrier registration (A2P)" jargon in step title [IMPACT: LOW | EFFORT: XS]
**What:** `_STEP_TITLES["a2p"] = "Carrier registration (A2P)"`. The comment in setup.html explicitly says "Zero Twilio/A2P/10DLC/TCR/brand/campaign jargon visible to the contractor." The step title violates its own rule.  
**Fix:** Rename to "Activate texting" or "Turn on texting" — matches the button copy that's already in the step body.

### Finding 7 — No welcome email, no A2P wait bridge, no post-live next-steps email [IMPACT: MED | EFFORT: M]
**What:** Zero emails sent on: signup, A2P submission, A2P approval, or first call received. Best-in-class SaaS for non-technical SMB (Podium, Jobber, Calendly) sends:  
  - Signup: welcome + "here's what to do first"  
  - Setup pending: "A2P submitted — you'll hear from us within 24 hours"  
  - A2P approved: "You're live! Your first calls are coming in"  
  - First lead: "You just got your first lead — here's what happened"  
**Why it matters:** Dave the painter signs up, goes through the wizard, clicks "Activate texting," closes his laptop, and goes on a job. There's no bridge. He forgets. A2P approves 20 hours later. Nothing told him. He checks back 3 days later and sees leads in the queue that he never knew about. He cancels.

### Finding 8 — Recommended section not prioritized for day-one revenue [IMPACT: MED | EFFORT: S]
**What:** The post-live "Get the most out of FirstBack" section lists 9 items in a flat list with no visual hierarchy. Calendar connection (required for actual booking) is visually equivalent to "Set your own password."  
**Fix:** Separate into two tiers: "Do this first" (calendar, AI training) vs. "When you're ready" (contacts, voice, reminders, screening). Or pin a "Your AI can't book until you connect your calendar" nudge card in the dashboard empty state.

---

## Competitive Benchmark

| Capability | FirstBack (current) | Calendly/Podium/Jobber bar |
|---|---|---|
| Time to signup | ~2 min | ~2 min ✓ |
| Time to first config | ~10 min (if EIN at hand) | ~5 min |
| EIN friction | Blocks sole_props | No equivalent gate |
| A2P wait handling | Honest but silent | N/A (SMS products use same wait) |
| Welcome email | None | Always sent |
| Live notification | None | Always sent |
| Error feedback | Silent | Always explicit |
| Post-live next steps | 9-item flat list | Guided 1-2-3 |
| "Aha" celebration | Text banner | Animated + email |
| Phone number carried from CTA | Lost | Persisted |

---

## Time-to-First-Value Estimate

| Path | Minutes to "live" (verified) |
|---|---|
| LLC with EIN at hand | ~15 min setup + 24 hr A2P wait |
| Sole prop without EIN | Indefinitely blocked at step 1 (EIN required=true) |
| Sole prop with EIN | ~15 min setup + 24 hr A2P wait |

The irreducible A2P wait (24 hrs) is industry-standard and can't be removed. The surrounding experience — no bridge, no notification, false voice message during the wait, silent errors — makes a bad-but-necessary wait feel broken.

**The single biggest drop-off risk:** The EIN `required=true` on the profile form, combined with every user being tagged `sole_prop` (no `has_ein` checkbox exists). A painter opens the wizard, sees "EIN (business tax ID) — Required," and closes the tab. This can be fixed in under 1 hour.

**The highest-leverage fix after EIN:** Send the "you're live" email + SMS the moment A2P approves. That one email converts a "set-and-forgot" churn risk into a delighted customer who gets a text saying "Your AI is live and just sent your first lead a message."

---

## Verdict

The wizard's bones are right: honest state machine, parallel A2P + forwarding, sentinel verification, queued blocked sends. The engineering is solid. But the human layer — what Dave sees, hears, and receives — has four High-impact gaps that each individually cost paying customers: a false voice message during the A2P wait, a broken EIN gate for sole_props, silent error states, and zero notification at go-live. The gap to best-in-class SMB SaaS onboarding is not architecture — it's 3–5 days of product polish work, mostly template and alert additions. At $99–399/month, a customer who quits at the EIN field or never realizes they went live is a $1,200–4,800/year loss per churned account.
