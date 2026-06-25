# FirstBack Dev Handoff (external)
**Date:** 2026-06-23 · **Source:** read-only audit → dev handoff, from the copy at
`/Users/jack/Documents/file transfer/RingBack` (Jack's machine). Filed verbatim here for the
record. See `RECONCILIATION` at the bottom for how it maps to what's actually shipped in THIS
repo (`~/apps/firstback`), since several "missing" items were built in the C–G batch.

## Product in one sentence
Instant missed-call text-back + AI booking for home-service contractors. When a call goes
unanswered, it texts the caller, handles the conversation, and books an estimate.

## Positioning
Not a generic missed-call autoresponder. Strongest promise:
> "FirstBack turns missed calls into booked estimates, without forcing a contractor into a full
> field-service platform."
Wedge: completed booking with calendar sync + precision call screening + proactive owner
intelligence (Vic).

## Competitors
- **Goodcall** — AI phone agent, live call answering. $79/$129/$249 per agent/mo. https://www.goodcall.com/pricing
- **Rosie AI** — AI answering service. $49/$149/$299/mo (250/1,000/2,000 min), booking on higher tiers. https://heyrosie.com/pricing
- **Jobber AI Receptionist** — call/text receptionist inside Jobber. Jobber ~$29–$529/mo; Receptionist in Plus or add-on. https://www.getjobber.com/pricing/ · https://www.getjobber.com/features/ai-receptionist/
- **LeadTruffle** — home-service AI lead capture + missed-call text-back. From $229/mo. https://www.leadtruffle.co/product-comparisons/rosie-ai-vs-leadtruffle/
- **Numa** — SMS-first missed-call recovery + conversation capture.
- **Podium / Birdeye / Signpost** — broader messaging/reputation/comms. https://www.podium.com/getpricing
- **GoHighLevel agencies** — cheap "good enough" missed-call text-back threat.

## Edge to protect
1. **Booking-complete outcome** — own "booked estimate" (slots, confirmation, reminders, owner alerts).
2. **Precision screening** — make the tiered screen a visible product value, not hidden plumbing.
3. **Contractor-specific AI (Vic)** — surface money left behind, not just reply to messages.
4. **Flat, understandable pricing** — competitive if booking ROI is shown clearly.

## What's missing / needs upgrade (per the external doc)
- **P1 Live voice answering or a strong reframe.** Competitors answer live; FirstBack recovers after a miss. Build a voice path, opt-in, priced separately — OR market text-first with conversion proof.
- **P2 Jobber or Housecall Pro sync.** Even read-only reduces the "data silo" objection. Pull customers/jobs (avoid texting known customers), push booked estimates as leads/notes. Additive, not an FSM replacement.
- **P3 Webchat widget.** Capture website leads with the same AI booking flow. Optional.
- **P4 Proof/ROI dashboard.** Missed calls recovered, estimates booked, revenue recovered, response time saved, booking rate by channel.
- **P5 Review request automation.** Compliant, post-job only. Don't distract from the core loop.
- **P6 Outlook calendar.** Google isn't enough for everyone; Outlook next.

## Recommended pricing
Keep the core ladder (matches current app): Starter **$99**/250 replies/1 number · Pro **$199**/1,000/1 ·
Crew **$399**/3,000/up to 5 · Annual −20%.
Add-ons: extra Pro number **$20/mo**; voice callback/answering **$29–$49/mo** once real; overage pack
**$25**/block or transparent usage tier; Jobber/HCP sync in Pro+ or **$29/mo** once stable.
**Don't raise Starter yet** — needs proof + brand trust before $129+.

## Dev priorities (phased)
- **Phase 1 — close perception gap:** surface booking-complete proof; "first recovered job" moment; make screening visible; keep voice copy honest (text-only today).
- **Phase 2 — voice path:** decide live answering vs callback; gated/beta; track cost/margin; never imply live until it is.
- **Phase 3 — FSM sync:** Jobber OR Housecall Pro first (not both); read-only OK for v1.
- **Phase 4 — multi-channel capture:** website widget after voice + FSM scoped; same engine.

## Acceptance checks
- Buyer can tell why FirstBack ≠ a $49 text-back tool.
- App shows ≥1 clear recovered-value metric after setup.
- Voice states accurate: live / beta / coming soon / unavailable.
- Screening never suppresses uncertain real prospects.
- Calendar booking never double-books.
- Add-ons gated by plan + billing state.

## Open questions
1. First voice impl: live inbound answering or caller-requested callback?
2. First FSM target: Jobber or Housecall Pro?
3. Review requests inside FirstBack or pushed to JobMagnet?
4. Overage behavior: hard stop, soft warning, or paid pack?

---

## RECONCILIATION — doc vs what's actually shipped in `~/apps/firstback` (2026-06-23)
Verified by grep against the repo. Much of the "missing" list is already built (C–G batch),
mostly **inert/OFF and owner-gated**, not pending dev:

| Doc priority | Real status here |
|---|---|
| **P3 Webchat widget** | **BUILT** — `static/widget.js` + Settings toggle (Batch G). Shipped OFF; needs owner to flip Widget on + paste embed; sends A2P-gated. |
| **P5 Review automation** | **BUILT** — `reputation.py`, `reminders.py`, Google review tracking (Batch E). Needs `GOOGLE_PLACES_API_KEY`. |
| **P4 Proof/ROI dashboard** | **BUILT** — `roi.py` ("$X booked", 5× recovered), analytics leads with the dollar figure, monthly recap. Could add per-channel booking rate. |
| **P1 Voice** | **PARTIAL + honestly gated** — `voice_service.py` exists; homepage says voice callback "coming soon … not available yet; today FirstBack handles everything by text." Matches the "never imply live" check. Real voice path = still a build/decision. |
| **P2 Jobber/HCP sync** | **NOT built** — no matches. Genuinely new. |
| **P6 Outlook calendar** | **NOT built** — only `google_cal.py`. Genuinely new. |

**Pricing:** the doc's recommended ladder already == the app's current pricing. The add-on ideas
align with the **founder decisions made 2026-06-23**: caller-reputation bundle = GO but DEFERRED
until `/pricing` is live; overage = HOLD (keep soft "we'll alert you", no $0.75 promise yet).

**Open-question overlap:** Q4 (overage) is already decided → **HOLD/soft**. Q1–Q3 are still open
owner decisions. Per standing rule, no new feature work starts without an owner pick.
