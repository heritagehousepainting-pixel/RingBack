# FirstBack — Highest-Leverage Feature Additions
**Auditor lane 12 of 12: ADDITIONS / Ideation**
Date: 2026-06-19

---

## What's already built (confirmed before proposing anything)

- Missed-call → instant text-back (core loop)
- AI conversation engine (booking, triage, urgency detection)
- Appointment reminders + follow-up sequences (scheduled_messages spine)
- Owner alerts (SMS + email channels via alerts.py)
- Growth plays engine: review requests (compliant), quote follow-up (24/72/168h), reactivation, win-back, referral, seasonal, density, membership, financing
- Dispatcher Call (urgent caller → owner's phone rings with caller audio, press-1 to connect)
- AI voice agent (ConversationRelay, built + gated; not yet deployed)
- ROI/analytics dashboard (leads, bookings, conversion %, estimated revenue)
- Google Calendar integration (booking creates/cancels events)
- Google Contacts import
- Morning Briefing + ambient money-ranked feed ("Vic")
- Microsite at `/c/<slug>` (opt-in page for A2P/TCR — compliance artifact, minimal)
- Stripe billing (Starter/Pro/Crew, monthly + annual)
- Setup wizard (A2P registration, forwarding verification, sentinel probe)
- Weekly digest + milestone SMS

**Gaps confirmed absent from codebase:** web-chat widget, web form capture, website embed/JavaScript snippet, instant quote engine, photo intake, deposit/payment collection, Jobber/HCP/ServiceTitan integration, voicemail transcription, Spanish/multilingual responses, team dispatch, job photo storage, invoicing handoff.

---

## The Additions

### A1 — Web-Chat Bubble / Website Text Widget
**Impact: H | Effort: M**

Every contractor has some web presence — a Google Business Profile, a Wix site, a Facebook page, a Yelp listing. Right now FirstBack only catches *phone* missed calls. A JS snippet (`<script src="firstback.app/widget.js" data-biz="slug"></script>`) drops a "Text us now" bubble on any page. Visitor clicks → phone number field → submits → creates a lead in FirstBack and fires the same AI reply flow as a missed call. No separate SaaS product. One line of code on their site.

**Why it matters to Dave:** He paid someone $800 for a website that gets 12 visitors a day and converts zero. The widget turns passive web traffic into conversations — without changing anything on his site or needing a developer. He tells his buddy at the supply house "I got three estimates off my website this month." That's a referral.

**Technical path:** Pure JS snippet (no framework), POST to `/webhooks/widget/lead`, hits the existing `create_lead` + `generate_reply` seam. Widget config served from `/api/widget/<slug>/config.js` (business name, trade, color). Takes the existing microsite `/c/<slug>` — the opt-in consent text is already there.

---

### A2 — Voicemail Transcription → Lead
**Impact: H | Effort: S**

When someone DOES leave a voicemail (after forwarding isn't set up, or they call a different number), FirstBack currently knows nothing. Twilio's Recording API captures voicemails; a webhook transcribes them (Twilio's own transcription, free at their tier, or Deepgram at ~$0.004/min) and creates a lead + sends the same AI text-back. The caller gets a response. The owner sees the transcription in the thread.

**Why it matters:** "85% of voicemails get no callback" is in BRAIN.md. This catches the callers who refused to hang up. Zero new setup beyond the existing Twilio account. Transcription cost is pennies. The owner literally gets leads from calls he didn't even know were voicemails.

**Technical path:** Voice webhook already exists (`/webhooks/twilio/voice/inbound`). Add `recordingStatusCallback` to the TwiML Dial. New `/webhooks/twilio/voice/recording` receives the transcript, runs `create_lead` + `generate_reply`. 2–3 days of work.

---

### A3 — Instant Ballpark Quote (Text-Based)
**Impact: H | Effort: M**

The biggest close-rate leak is when a homeowner asks "how much?" and gets silence, a "I'll have to come out and see," or a week-long wait for a quote. FirstBack already has the AI conversation. Add a Vic-trained quoting flow: when the AI detects a price intent (keywords: "how much," "what do you charge," "ballpark," "estimate"), it collects 3–4 job-detail questions (square footage, scope, material), looks up the owner's stored price anchors (set in settings: "I charge $X–Y per square foot for interior paint"), and texts back a *range* with a booking CTA. Not a final quote — a ballpark that keeps them from calling the next plumber.

**Why it matters:** The contractor already knows his prices. He just can't respond in real-time. This closes the gap. "Sub-5-minute response is 21× more likely to qualify" — BRAIN.md. A ballpark that arrives in 90 seconds vs. "I'll call you back" wins the job before the competitor even picks up.

**Technical path:** New intent detector in `ai.py` / `triage.py`. Owner sets price anchors in Settings (key-value pairs: service → min/max). `assistant.py` gets a `get_price_anchor(trade, service_type)` tool. LLM synthesizes a range from the anchor + gathered job details. No third-party dependency.

---

### A4 — Deposit / Payment Link in the Booking Confirmation
**Impact: H | Effort: M**

Right now, when FirstBack books an estimate, the confirmation text says "Your estimate is booked for Thursday at 2pm — see you then!" Zero friction removed from the actual close. Add a Stripe Payment Link (Stripe already integrated for billing) that the AI includes: "To hold your spot, a $50 deposit secures the appointment." Owner sets deposit amount in Settings (or $0 to skip). Stripe Payment Link requires no new account — they create it in the Stripe dashboard; FirstBack stores the URL and appends it to booking confirmations.

**Why it matters to Dave:** "No-call no-shows" are his #1 complaint. A paid deposit turns a "soft yes" into a committed appointment. It also collects card-on-file for balance later. This is the difference between a $99 tool and a tool that pays for itself in the first week.

**Technical path:** New field `deposit_link` on `businesses`. Booking confirmation template gets a conditional `{{- if deposit_link }} — Secure your spot: {{deposit_link}} {{- end}}`. The Stripe Payment Link lives outside FirstBack; we just store and embed the URL. Effort is mostly UI + template — 1–2 days.

---

### A5 — Google Business Profile Review Velocity Dashboard + Auto-Response Drafts
**Impact: H | Effort: M**

Reviews exist in basic form (review request play). The gap: owners can't SEE their review trajectory inside FirstBack, and they have to respond to every review manually. Two additions:

1. **GBP Review Sync:** Poll the Google Business Profile API (OAuth already wired) to pull recent reviews. Show a "Your Google rating" tile on the dashboard: current star rating, review count, last 30-day velocity, and any <3-star reviews flagged. This is the signal Dave needs without opening Google Maps.

2. **One-tap response drafts:** For every new review (positive or negative), Vic pre-drafts a response in the owner's voice (uses the existing LLM + trade context). Owner sees "New 5-star from Maria — tap to send this reply." One tap. No typing. Google favors owners who respond fast — 24h response rate affects LSA rank.

**Why it matters:** "Your last 12 jobs — zero review requests sent. Your Google rank is going to slide." (BRAIN.md Vic example line.) Reviews are the compounding growth asset. 300+ reviews drive 1,046% more LSA leads. FirstBack already sends the request — now it closes the loop on what happens next.

**Technical path:** GBP Reviews API (OAuth flow mirrors Google Calendar, already built). New `db.reviews` table. `reputation.py` expanded (currently handles number reputation — different concern, different file is cleaner). Dashboard tile + review response card in the growth tray.

---

### A6 — Spanish / Bilingual AI Responses
**Impact: H | Effort: S**

In 40+ US metro markets, 20–40% of homeowners speak Spanish as a first language. When they text a contractor in Spanish, they currently get an English AI reply — or no reply at all if they called and hung up. FirstBack already uses Claude. Add language detection (a single `langdetect` check or one LLM call) at the inbound message step. If Spanish (or any non-English language) is detected, reply in that language. Owner setting: "Reply in customer's language" (default ON).

**Why it matters:** A Spanish-speaking homeowner who gets an instant reply in Spanish will book. The English-only competitor will not get a callback. This is not a feature Dave will cite in a sales meeting — but it is a feature that wins jobs he would have lost silently.

**Technical path:** One language-detect call before `generate_reply`. Pass `language_hint` into the system prompt: "The customer is writing in Spanish. Reply in Spanish." No new API — Claude handles it natively. Owner toggle in Settings. 1 day of work. Potentially the highest ROI-per-hour addition on this list.

---

### A7 — Job Photo Intake via Text
**Impact: M | Effort: S**

Homeowners already text photos to contractors. Add MMS handling to the Twilio inbound webhook: when an inbound message contains a `MediaUrl`, download the image, store it attached to the lead thread, and show it in the conversation view. Optionally, the AI can reference "I can see the photo you sent — looks like water damage around the window frame" in its next reply.

**Why it matters:** A contractor who can see the job before the estimate shows up prepared. "Whoever shows up prepared wins" is the competitive truth. It also removes a scheduling back-and-forth: instead of "can you send a photo first?" the customer already sent it before the estimate is even booked.

**Technical path:** `MediaUrl0` already in the Twilio webhook payload. Store as a `lead_media` row (url, content_type, created_at, lead_id). Conversation UI renders `<img>` for media messages. AI system prompt can include "The customer sent a photo of: [description via vision model]" — optional; the storage and display alone are valuable.

---

### A8 — Jobber / Housecall Pro / ServiceTitan Handoff (One-Way Push)
**Impact: M | Effort: M**

The target contractor for Crew tier ($399/mo) already uses a field-management tool. He doesn't want to abandon it — he wants FirstBack to feed it. When an estimate is booked in FirstBack, push a new job/estimate to his existing tool via their API. Jobber has a public API. HCP has a partner API. ServiceTitan requires a partner relationship but is doable.

This is a one-way push (FirstBack → field tool), not a sync. No conflict-resolution complexity. Just: booking confirmed → create a draft job in Jobber.

**Why it matters:** Without this, the Pro/Crew contractor has to manually re-enter every FirstBack booking into Jobber. He does it twice and then stops using FirstBack. The integration removes the one friction point that kills retention at the top tier. "Friction is the product" — this is the inverse: remove the friction that makes him abandon.

**Technical path:** New `integrations.py` (mirrors `google_cal.py` gated pattern). OAuth for Jobber (they have a standard OAuth2 flow). `/api/integrations` route already exists. Start with Jobber only (highest contractor market share); add HCP in a second pass.

---

### A9 — After-Hours Capacity Overflow: Forward to Voicemail Transcription + "Next-Day Slot" AI Booking
**Impact: M | Effort: M**

Right now FirstBack catches missed calls 24/7. But for contractors who DO pick up during business hours, they only want the AI to handle calls after-hours (6pm–8am). Add a time-window gate: outside business hours, all calls go straight to FirstBack's AI; during business hours, forward to the real phone (as today). 

The secondary play: when a contractor is on the roof mid-morning, his phone rings 5 times in 3 hours and he can't answer. FirstBack should detect "same owner, multiple missed calls in a window" and surface "You missed 5 calls between 10am–1pm. Want me to text them all the next available slot?" — a burst-handle play.

**Why it matters:** Contractors with employees have the problem of "who answers?" The AI becomes the overflow, not the primary. This is the upgrade path: start them on "AI catches everything I miss" → evolve to "AI is my after-hours line."

**Technical path:** Business hours stored as `business_hours_start`/`end` + timezone (SF-5 already has per-business timezone). TwiML conditional (`<Gather>` vs `<Dial>`) based on current time vs business hours. Burst detection: new `burst_candidates(business, window_minutes=180, threshold=3)` function in `growth.py`.

---

### A10 — "Sounds Human" Guarantee: Pre-Send Message Preview + Personalization Score
**Impact: M | Effort: S**

Every text FirstBack sends is reviewed by the owner before it goes (the honest confirm). But the confirm UX today shows the message and a Send button — no signal about whether the message sounds like a real person or a robot. Add a "Vic's take" badge on the confirm card: a 1-sentence quality read ("This sounds personalized" vs "This is a bit generic — the customer's name wasn't found"). 

Separately, add a "personalization fill rate" metric to the dashboard: what % of outbound messages used the customer's real first name vs. a placeholder. Dave sees this and understands why some leads go cold — the message said "Hi Homeowner" instead of "Hi Marcus."

**Why it matters:** The #1 objection to AI texting is "it sounds fake." A visible quality signal — even just a green/yellow badge — builds Dave's trust in the product. And the metric surfaces a real problem: leads without a name in the CRM get impersonal texts that convert at half the rate.

**Technical path:** At confirm time, check for `_PLACEHOLDER_NAMES` (already defined in `growth.py`). Score = name found + message < 160 chars + no ALL-CAPS + no >2 consecutive sentences without a question. Return a 0–3 badge in the confirm card. Metric: `outbound_personalization_rate` aggregated daily in analytics. Small effort, high trust signal.

---

## Ranked Top-10 "Build Next" List

| Rank | Feature | Impact | Effort | One-Line Why |
|------|---------|--------|--------|--------------|
| 1 | A6 — Spanish / Bilingual | H | S | Wins jobs competitors can't see; Claude already speaks Spanish; 1 day |
| 2 | A2 — Voicemail Transcription | H | S | Catches the leads that refuse to hang up; Twilio already recording |
| 3 | A1 — Web-Chat Bubble | H | M | Turns a dead website into a lead source; one JS snippet Dave pastes once |
| 4 | A4 — Deposit Link at Booking | H | M | Converts soft-yes to committed slot; kills no-shows; Stripe already wired |
| 5 | A5 — GBP Review Dashboard + Auto-Responses | H | M | Reviews compound; Dave can't manage GBP manually; closes the review loop |
| 6 | A3 — Instant Ballpark Quote | H | M | Stops leads from calling the next contractor while waiting for a callback |
| 7 | A7 — Job Photo Intake (MMS) | M | S | Prepares contractor before arrival; no new account; 1-day add |
| 8 | A10 — "Sounds Human" Badge | M | S | Addresses the #1 AI texting objection; surfaces personalization gap |
| 9 | A8 — Jobber Integration | M | M | Removes the double-entry that kills retention at Crew tier |
| 10 | A9 — After-Hours Overflow + Burst Handle | M | M | Unlocks "AI as after-hours line" upgrade path for growing contractors |

---

## One-Line Verdict on the Biggest Opportunity

**Spanish is a same-day win that costs nothing and silently wins the jobs competitors can't see — the highest-leverage addition on the list by ROI per hour of build time.** The voicemail transcription is a close second: it recovers leads from callers who already tried and left evidence, and it requires almost no new code.

The web-chat widget is the biggest *revenue* opportunity because it creates an entirely new lead source (web traffic) that FirstBack currently ignores entirely — but it takes a week to build right.

---

*Lane: Additions / Ideation. READ-ONLY audit. No code written or modified.*
