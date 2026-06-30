# FirstBack Onboarding Blueprint — "Instant Value, Deferred Compliance"

**Goal:** real contractors sign up and get value on **Day 0**, with their missed calls,
texts, and emails auto-answered by Vic — **without waiting on Twilio's ~10–15 business-day
A2P 10DLC approval** (which usually needs at least one resubmission).

Produced from a 15-agent parallel research+design pass (Jun 29, 2026), then **verified against
the actual codebase**. Verification status is marked throughout: ✅ confirmed in code · ⚠️ needs
external confirmation before acting · 🔬 needs real-world testing.

---

## TL;DR — the strategy

The A2P wait is unavoidable for a contractor's **own local number**, so **stop putting it on the
critical path.** The day-0 "don't miss the client while you're on the ladder" promise is carried
by **VOICE**, not SMS — Vic answers the phone automatically from the contractor's own number with
zero registration. SMS text-back upgrades silently in the background once 10DLC clears.

> **The core correction (owner decision, Jun 29):** the day-0 catch is VOICE — automatic, branded,
> no taps. There is **no platform toll-free number anywhere in the product.** Every customer
> touchpoint is the contractor's own identity from minute zero. SMS is handled in two stages below.

**Activation state machine** (one column on `businesses`):

```
SETUP  →  VOICE_LIVE  →  LIVE_SMS
            (+ optional click-to-send SMS during the 10DLC wait)
```

| State | What's live | Approval needed |
|---|---|---|
| **VOICE_LIVE** (minute 0) | Missed calls forward to Vic (Twilio ConversationRelay AI voice) — **answers automatically, books the job, from the contractor's own number**. Email leads captured. Every call logged with transcript. This alone delivers the core promise. | **None** — inbound voice is unregulated |
| **VOICE_LIVE + click-to-send** (optional, opt-in) | For contractors who also want instant text-back *during the wait*: Vic drafts the text-back, the contractor taps once to send it **from their own phone** (person-to-person, not A2P). Purely optional — voice already has them covered. | **None** — P2P |
| **LIVE_SMS** (day ~10–15, automatic) | Sole-prop 10DLC clears → FirstBack flips text-back to **fully automatic, from the contractor's own local number**. Taps disappear. Two-way threading on. | 10DLC, but **off the critical path** |

**The insight that makes this work:** FirstBack already has the hard part built — `voice_service.py`
is a real-time AI receptionist on Twilio ConversationRelay (streaming, barge-in, recovery SMS),
and `messaging.py` already has A2P reseller scaffolding (`TWILIO_A2P_RESELLER_SID`,
`create_a2p_brand/service/campaign`). This is wiring + sequencing, not greenfield.

---

## The A2P bypass decision (resolved)

- **Primary Day-0 path:** conditional call-forwarding → **Vic voice, fully automatic, from the
  contractor's own number** (zero approval). This is the entire "don't miss the client" promise.
- **Optional SMS during the wait:** **click-to-send P2P** — Vic drafts, contractor taps to send
  from their own phone. Opt-in only; voice already covers the core need.
- **Background permanent path:** **sole-proprietor 10DLC per contractor**, auto-submitted at
  signup. No EIN needed (SSN + mobile OTP). Brand approves in minutes; campaign in 10–15 business
  days. On approval, SMS text-back flips to fully automatic from their own number. Cap ~1,000
  msg/day to T-Mobile — irrelevant for a contractor with 20–50 missed calls/day.

**Rejected, with reasons:**
- **Platform toll-free bridge SMS (the agents' original day-0 default)** — sending the signature
  text-back from a generic 888 number is **off-brand for a *local* home-services contractor** and
  undercuts premium pricing. Owner-rejected Jun 29. No platform TFN in the product. ❌
- **Forcing click-to-send as the day-0 catch** — also rejected: the whole promise is "answer while
  you're on the ladder," which means *zero taps*. Click-to-send is therefore **optional SMS only**,
  never the safety net. Voice is the safety net. ❌ as a primary mechanism.
- **ISV "Agents & Franchises" shared campaign** — forces Vic to speak as "FirstBack's platform,"
  not "Joe's Painting." Breaks product identity; AT&T post-reg approval adds weeks. ❌
- **Per-contractor toll-free bridge** — requires a BRN/EIN as of Feb 2026; most solo trades have
  no EIN. ❌
- **Provider switch (Telnyx/Bandwidth)** — the bottleneck is TCR's vetting queue, not the CPaaS;
  switching doesn't speed approval. Valid later as a **cost** optimization (~$365/mo saved at 50
  contractors), not a timeline fix. Bandwidth has no sole-prop path. ❌ for now.

> ⚠️ **EIN fork:** ask "Do you have a business EIN?" at signup. Yes → Low-Volume Standard brand
> path (Twilio penalizes sole-prop registrations that actually have an EIN). No → sole-prop.

---

## Provider recommendation: stay on Twilio (for now)

- ConversationRelay + Claude is **already built and tested** in `voice_service.py`. Rebuilding on
  Telnyx/Retell costs 1–2 weeks the first contractor can't afford.
- Twilio has the only documented **ISV sole-proprietor registration API**; Telnyx's is email-a-human.
- Per-message cost gap (~$0.004–0.005) is irrelevant at launch scale.
- **But build a `providers/` abstraction now** so a Telnyx migration at ~50 contractors / $200/mo
  Twilio SMS is a config change, not a rewrite.

---

## The contractor's 5-minute setup (no waiting, mobile, self-serve)

0. **Signup (90s)** — name, business name, trade (pills), **mobile** (OTP target + alert number),
   email, password.
1. **Address + EIN fork (60s)** — business address (carriers require it) + "Do you have an EIN?"
   yes/no. Routes sole-prop vs Low-Volume Standard.
2. **Pick Vic's number (30s)** — 3 local numbers, area code derived from their mobile. Tap →
   Twilio provisions instantly → enqueue A2P registration → set `voice_live`.
   Note appears: "Look for a text from us — reply YES (this verifies *your* number with the carriers
   so your texts go out automatically once approved)." Optional toggle: "Want Vic to draft text-backs
   for you to send while we verify your number? (one tap each)" → sets `click_to_send_optin`.
3. **Forward your calls (90s)** — full screen, carrier buttons, the star-code as a `tel:` deep
   link with `#` URL-encoded, "tap to dial." **Required TCPA checkbox:** "I authorize FirstBack to
   send automated texts to callers on my behalf. Every text includes opt-out instructions."
   **iPhone banner:** "Settings → Phone → Live Voicemail → OFF, or forwarding won't fire."
4. **Done** — status list (✓ Vic answers your missed calls now, ✓ every caller logged,
   ✓ text-back drafts ready to tap [if opted in], ⏱ your own number registering ~14 days → texts go
   automatic). Optional: 2 quick Vic-training fields + "Connect Gmail."

---

## Build plan

> **BUILD STATUS (Jun 29, autonomous /loop):** Phase 0 + the Phase 1 correctness spine + the
> Phase 3 approval-handoff are **implemented and tested green** (full suite: 2468 assertions +
> unittest block, 0 failures). Specifically DONE:
> - ✅ `ai.py` informational+STOP opener · ✅ `messaging.py` A2P Privacy/Terms URLs
> - ✅ `db.py` activation machine (`setup→voice_live→live_sms`) + `click_to_send_optin`,
>   `tcpa_consent_at`, `a2p_pending_submit` columns + setters + consent ledger at boot
> - ✅ `messaging.send_sms` state routing + `click_to_send_link()` (default stays `blocked`)
> - ✅ consent events in `_missed_call_textback` + `widget_lead`
> - ✅ `connections.auto_submit_pending_a2p()` wired into `/tasks/run-due`; forwarding-confirm
>   handler advances to `voice_live` + flags A2P
> - ✅ `a2p_sync` pending→approved handoff: flush + `live_sms` + click-to-send off
>
> ALSO DONE (second pass, authorized by owner):
> - ✅ **Gmail email auto-answer** — `google_mail.py` (OAuth mirror of google_contacts; gmail.modify
>   scope; read unread → Vic drafts via the shared brain → send threaded reply → mark read), connect/
>   callback/disconnect routes in `app.py`, `poll_and_answer_all()` wired into `/tasks/run-due`,
>   `GOOGLE_MAIL_REDIRECT_URI` in config. Gated: inert until creds + OAuth. 25 tests. **Owner: add the
>   redirect URI to the Google OAuth client, set GOOGLE_CLIENT_ID/SECRET, add contractors as test
>   users (restricted-scope verification needed before 100+ users — see module header).**
> - ✅ **Phase 3 `providers/` seam + `channel_state.py`** — `providers/{base,twilio_provider,
>   telnyx_provider,registry}.py` (Twilio delegates to messaging.py → zero behavior change; Telnyx
>   stub simulates safely; registry resolves by `SMS_PROVIDER` env / per-biz override) + `channel_state.py`
>   (honest per-channel read: voice/email/sms_auto/click_to_send, `day0_live`, `best_outbound`,
>   `next_step`). 15 tests. Telnyx migration is now a config swap, not a rewrite.
>
> ALSO DONE (third pass): **Wizard redesign** — `templates/setup.html` reframed voice-first (hero +
> blocker banner), and the forwarding step now carries the **iPhone Live-Voicemail warning**, the
> **carrier tap-to-dial code card**, a **required TCPA consent checkbox** (→ `tcpa_consent_at`), and
> the **click-to-send opt-in** (→ `click_to_send_optin`); `/setup/forwarding` captures both; new CSS in
> `static/setup.css` (v3). Verified visually in-browser. (Consent is HTML-required in the form; the
> real gate is downstream — `auto_submit_pending_a2p()` won't register A2P without `tcpa_consent_at`.)
>
> STILL DEFERRED (only this):
> - 🔬 **Sentinel forwarding-verification rewrite** — honesty-critical, tested, `[DECIDED]` code;
>   the SID-mismatch bug is plausibly real but the fix needs real Twilio/carrier testing to avoid
>   *false-confirming* forwarding. Left intact. See risk #4.
>
> **Test status: full suite green — 2508 check()-style assertions + unittest block, 0 failures.**

> File/line references below were produced by agents that demonstrably read the repo (the
> `instant_opener` text was quoted verbatim). Still, **re-confirm each line at edit time** — the
> repo moves.

### Phase 0 — patches to land first

| # | Change | Status |
|---|---|---|
| 0.1 | **`ai.py:493 instant_opener()`** — replace the sales-pitch opener with an informational + opt-out message: `"Hi — {name} here, we missed your call and want to help. What's going on with your project? Reply STOP to opt out. Msg&Data rates may apply."` Removes TCPA-promotional risk, adds required STOP. | ✅ **confirmed** — current text is the pitch, verbatim |
| 0.2 | **`messaging.py create_a2p_campaign()`** — add `PrivacyPolicyUrl` + `TermsAndConditionsUrl` to the payload; ensure `/privacy` and `/terms` stub routes exist on the micro-site slug namespace. | ✅ URLs confirmed absent. ⚠️ the "Jun 30 / HTTP 400 tomorrow" deadline is **unverified — confirm with Twilio**; do the change anyway (it's correct regardless) |
| 0.3 | **`connections.py CARRIER_FORWARD_CODES`** — review AT&T `*92`/T-Mobile/US-Cellular codes. | 🔬 **test on real devices per carrier before changing.** A universal GSM fallback (`**004*{num}#`) already exists. Don't blind-swap. |
| 0.4 | ~~Submit FirstBack's platform TFN verification~~ — **DROPPED** (owner decision). No platform toll-free in the product; voice is the day-0 catch. | ❌ removed |

### Phase 1 — get the first contractor live (this week)

- **`db.py`**: `ALTER TABLE businesses ADD COLUMN activation_state TEXT DEFAULT 'setup'` (PRAGMA
  guard), `tcpa_consent_at`, `a2p_pending_submit`, `click_to_send_optin` (default 0). Add
  `db.set_activation_state()`.
- **`messaging.py` `send_sms()` routing by state** — no platform-TFN path exists.
  - `voice_live` + `click_to_send_optin=0` → text-back is suppressed; voice has the lead. (Owner
    alert still fires.)
  - `voice_live` + `click_to_send_optin=1` → Vic drafts the reply and fires a **click-to-send
    alert** to the contractor's own phone (an `sms:` deep link pre-filled with the draft, addressed
    to the customer). The contractor taps once; the text goes from *their* number. P2P, no A2P gate.
  - `live_sms` → fully automatic send from the contractor's own local number (the `a2p_ready()`
    path, unchanged). This is the post-10DLC steady state.
- **Consent events** — in `_missed_call_textback()` and `widget_lead()`, call
  `consent.record(...)` so consent is auditable, not inferred.
- **Forwarding verification rewrite** — current sentinel SID-matching is broken (carrier
  forwarding mints a new SID). Replace with self-call fingerprint (`From == biz.twilio_number`
  within the sentinel window) + AMD (`machine_start` ⇒ voicemail intercept) + a
  `GET /api/forwarding/status` polling endpoint and a live diagnosis card on `setup.html`.
- **Auto-submit A2P** on forwarding-confirmed: set `a2p_pending_submit=1`; the `/tasks/run-due`
  tick picks up rows with number + consent + pending and calls `submit_a2p()`. No contractor action.
- **Voice deploy** — set `VOICE_PUBLIC_URL`, pick a real `CONVERSATIONRELAY_VOICE`; in
  `twilio_voice_inbound()`, return ConversationRelay TwiML directly (skip `<Dial>`) when active;
  greet with the **FCC-required AI disclosure** ("I'm Vic, an AI scheduling assistant for [Name]").

### Phase 2 — production wizard + email (days 5–10)

- Rebuild `/setup` as the 4 full-page screens above; drop the manual "Activate texting" button.
- **Email auto-answer** — fastest zero-delay channel. Outlook OAuth (`outlook_mail.py`, mirror
  `outlook_cal.py`; live in ~1hr) **plus** Gmail-forwarding → Postmark Inbound
  (`vic+{biz_id}@inbound.firstback.com`). Submit Google `gmail.send` for verification early
  (~10 biz days; use test-users meanwhile). Avoid restricted scopes (triggers CASA $$).

### Phase 3 — provider abstraction + channel FSM (days 10–20)

- **`providers/` package** — `base.py` ABC (`send_sms`, `place_call`, `provision_number`,
  `valid_signature`), `twilio_provider.py` (move REST calls out of `messaging.py`),
  `telnyx_provider.py` stub (Ed25519 sig — **not** reusable from Twilio), `registry.py` factory.
- **`channel_state.py`** — tiered channel resolution + `best_outbound_channel(biz)`.
- **Handoff on 10DLC approval** — in `a2p_sync()` on `pending→approved`: set
  `activation_state='live_sms'`, turn off the click-to-send alert path, and from here text-back is
  fully automatic from the contractor's own number. (No bridge to retire — there never was a
  platform number.)

---

## Top risks

1. ⚠️ **A2P payload deadline** — add Privacy/Terms URLs now; **verify the date with Twilio**, don't
   panic on an unconfirmed "tomorrow."
2. **No instant *automatic* SMS in the first ~2 weeks** — by design. Voice carries the day-0
   catch (automatic, branded). SMS text-back is either optional click-to-send (opt-in, one tap) or
   waits for 10DLC. This is the accepted tradeoff, not a gap to paper over with a toll-free number.
3. 🔬 **Carrier forwarding codes** — test each on a real handset; wrong code = silent churn.
4. **Sentinel SID-matching broken** — replace with self-call detection (Phase 1).
5. **iPhone Live Voicemail (iOS 17+)** intercepts the call before no-answer forward fires —
   prominent wizard banner + AMD detection.
6. **OTP 24h expiry** — brand never clears if the contractor ignores the OTP; nudge at h4/h8,
   one-tap retry. Run Twilio Lookup `line_type_intelligence` first to reject VoIP mobiles before
   the brand fee is charged. (Mobile has a 3-use lifetime cap across TCR.)
7. **TCPA opener** — fixed by 0.1; add a TCPA indemnification clause to contractor onboarding
   (ties to `legal-intake.md`).
8. **EIN routed to sole-prop** — the signup EIN fork prevents campaign suspension.
9. **Voice forwarding target must be a LOCAL DID** (AT&T blocks conditional call-forwarding to
   toll-free anyway). The contractor's own provisioned local number is both the call-forward target
   and, post-10DLC, the text-back sender. One number, the contractor's own.
10. **Sole-prop daily cap** (~1,000/day T-Mobile) — flag at 800/day, prompt upgrade to
    Low-Volume Standard. Growth problem, not launch.

---

## Immediate action order (verified)

1. **`ai.py` `instant_opener`** → informational + STOP. ✅ safe, do now.
2. **`messaging.py` A2P payload** → add Privacy/Terms URLs + micro-site stub routes. ✅ safe;
   ⚠️ verify the urgency date with Twilio separately.
3. **Deploy the voice leg** (`voice_service.py` sidecar + `VOICE_PUBLIC_URL` + a real
   `CONVERSATIONRELAY_VOICE`) — this is the day-0 catch and must be solid. ✅
4. **Carrier codes** → schedule real-device testing before any change. 🔬 don't blind-edit.

*Source: 15-workstream agent fan-out + synthesis, `wf_393b26fd-98c`. Full per-workstream detail
(sole-prop numbers, provider shootout, competitive teardown, carrier codes, voice infra, etc.) in
the workflow output.*
