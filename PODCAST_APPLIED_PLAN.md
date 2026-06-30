# FirstBack Growth Plan — Lessons from Lenny's Podcast × Amol Ezzat Sary

**Source:** Lenny's Podcast × Amol Ezzat Sary (Head of Growth, Anthropic), "Anthropic is automating its own growth."
**Product:** FirstBack — AI voice receptionist for solo home-services contractors. $99–$399/mo flat. Pre-revenue.
**Framing:** Anthropic is a hyperscale AI lab with near-infinite demand, 40 growth engineers, and billions in ARR. FirstBack is a pre-revenue SaaS targeting local, non-technical contractors. Every lesson below is translated against that gap. Where a lesson does not transfer, it is stated explicitly. The plan is split into two phases: before contractor #1 is paying, and after.

---

## PHASE 0 — PREREQUISITES (do these before touching anything else)

---

### P0-A: Deploy voice (the real #0, not a mindset)

**Podcast lesson:** "FOCUS: do few things, go deep. Freedom through constraints."

**How it applies:** Every item in this plan is gated on `VOICE_PUBLIC_URL`. The `ONBOARDING_BLUEPRINT.md` lists this explicitly at its own action #3: "Deploy the voice leg (`voice_service.py` sidecar + `VOICE_PUBLIC_URL` + a real `CONVERSATIONRELAY_VOICE`)." This is a concrete engineering action — provision a server with a real public URL, wire `voice_service.py` as a sidecar, set `CONVERSATIONRELAY_VOICE` to a real Twilio voice, and enable ConversationRelay TwiML in `twilio_voice_inbound()` with the FCC-required AI disclosure. Nothing else in this plan is worth building until voice is answering calls on a real URL.

**Concrete action:** Provision the sidecar (VPS or similar), set `VOICE_PUBLIC_URL`, pick a voice, deploy. Run a real test call before any other work begins. This is action #0.

**Effort:** S-M (infra setup; `voice_service.py` is already built).
**Priority:** Absolute prerequisite — everything gates on it.
**Constraint:** Owner-gated (infrastructure decision + cost). No code change; an environment and deployment decision.

---

### P0-B: Cold outreach to 20 contractors in a specific local market

**Podcast lesson:** Amol's cold email story opens the podcast — specific hypothesis, right person, short message, direct follow-up. "Freedom through constraints: smallest/least-funded → forced narrow focus → escape velocity."

**How it applies:** The entire build list is product-side. There is no plan for how contractor #1 arrives. The product can be perfect and contractor #1 never shows up if there is no outreach. The cold email lesson maps directly to this gap — not "blast everyone" but identify a specific trade in a specific market, find 20 real contractors, and write one direct message per trade: "I saw you missed a call — the caller didn't leave a voicemail. There's a tool that answers it and books the estimate. Want to see it?" Painter Facebook groups (Painting Contractors Association local chapters), HVAC/ACCA groups, Nextdoor Pros, and supply house relationships (Sherwin-Williams reps know every painter in a territory) are the fastest paths to 20 real contractors.

**Concrete action:** Before finishing any wizard optimization: pick one trade (painting is the clearest fit for the AI preview and tone), pick one metro, find 20 contractors via Facebook groups and Nextdoor Pros, send 20 short messages with a specific hypothesis. Do this in parallel with P0-A.

**Effort:** S (a few hours; no code).
**Priority:** Parallel with voice deploy. Producing contractor #1 is the only milestone that matters before any optimization work.
**Constraint:** None. This is human action while code is being built.

---

## PHASE 1 — BEFORE CONTRACTOR #1 IS PAYING

*These are the items that make the first contractor's experience actually work end-to-end. Everything else is deferred until there is real drop-off data to act on.*

---

### OA-1: Fix the forwarding sentinel

**Podcast lesson:** Mercury spent a whole quarter fixing onboarding quality ("forget metrics") — biggest growth result of Amol's career. "Quality drives growth. Onboarding is the first experience — invest like the rest of the product."

**How it applies:** The blueprint explicitly documents (as a deferred risk): "the SID-mismatch bug is **plausibly real** but the fix needs real Twilio/carrier testing to avoid false-confirming forwarding." The current sentinel in `connections.py` uses SID matching that may break when carrier forwarding mints a new call SID. A contractor who sets up call forwarding gets either a false confirmation or no confirmation. The forwarding confirmation step is the highest-trust moment in the product — the contractor just dialed a star code on faith — and silent failure here is the single biggest churn risk before any customer ever calls.

**Note on framing:** The SID-mismatch bug is plausibly real, not confirmed. The risk of the proposed fix is false-positive confirmation (telling a contractor they are live when they are not), which is worse than the current behavior. Real-carrier testing on AT&T, T-Mobile, Verizon, and US Cellular must precede any deploy.

**Concrete action:** Implement the self-call fingerprint (`From == biz.twilio_number` within a 120-second sentinel window) + AMD detection (`machine_start` = voicemail intercept) + a `GET /api/forwarding/status` polling endpoint. The wizard shows a live "checking your forwarding..." card after "I've set up forwarding" is tapped, polling every 5 seconds, then renders either "Confirmed — you're live" or "Not detecting it yet — try again" with a retry button and a per-carrier troubleshooting note. Track `forwarding_confirmed / forwarding_attempted` by carrier.

**Effort:** M-L (new AMD webhook path, new polling endpoint, new DB columns for sentinel state, template change for the live card; requires real-carrier testing before deploy).
**Priority:** 1 in Phase 1 — gating quality issue for first contractor.
**Constraint:** Gated on P0-A (voice deploy). Build in parallel; validate only after voice is up.

---

### OA-2: Trade pills at signup

**Podcast lesson:** "The who-are-they data compounds: activation → lifecycle → look-alike ad retargeting if they drop. 'Juice that keeps giving.'" + "Right friction — ask who they are / their goals → recommend the right product."

**How it applies:** `app.py` line 339 silently defaults every new contractor to `"home services"` because `auth.html` has no trade selector. `growth.py`'s `_SEASONS`, `_FINANCING_BY_TRADE`, and `_TRADE_DEFAULT_VALUE` get no useful signal; `ai.py`'s `_system_prompt()` injects `"home services"` as the trade context; re-engagement emails cannot be trade-personalized; the wizard cannot personalize its header. One two-field change at signup unlocks every downstream personalization — this is the exact lesson.

**Concrete action:** In `auth.html`, add a trade pill grid (Painting / HVAC / Plumbing / Roofing / Electrical / Landscaping / Other) as the first element after "Business name." A hidden `<input name="trade">` is updated on tap. In `app.py` signup handler (line 339), remove the `"home services"` fallback and validate that trade was selected. The wizard header immediately personalizes ("Your painting AI is ready"), the welcome email is trade-specific, and a contractor who abandons before completing the wizard still has a trade signal captured for re-engagement.

**Effort:** S (two-file change).
**Priority:** 2 in Phase 1 — unblocks GA-1, GA-2 (when it fires), GA-3, and the lifecycle email system.
**Constraint:** None. Safe to ship before voice deploy.

---

### OA-3: Sole-prop fork UI cleanup

**Podcast lesson:** "Cut bad friction (steps with no value). Keep good friction (make it FOR THEM)."

**How it applies:** The EIN fork is correctly handled at signup — `auth.html` has an EIN checkbox, `app.py` sets `business_type` to `sole_prop` or `llc`. But wizard Step 1 in `setup.html` still shows an "EIN (business tax ID)" text input with a hint ("Sole proprietors can skip this"). A contractor who chose "no EIN" at signup is re-presented with the EIN field as if the decision is still open. Bad friction: re-litigating a decision already made with no new information.

**Concrete action:** In `setup.html`, conditionalize the EIN field on `business.business_type`. If `sole_prop`: hide the field entirely; show one static line "Sole proprietor — no tax ID needed." Update the step summary (currently "EIN on file") to "Sole proprietor" for this case. If `llc`: show the EIN text input with label "Business EIN (your LLC's tax ID)."

**Effort:** S.
**Priority:** 3 in Phase 1 — trust signal; low effort.
**Constraint:** None.

---

### GA-1: Trade-aware voice tone in `_system_prompt()`

**Podcast lesson:** "Right friction — add friction that makes the product feel FOR THEM." + data compounds from who-are-they.

**How it applies:** `ai.py`'s `_system_prompt()` injects `business['trade']` but the tone instruction is generic: "sound like a sharp, friendly person who actually works here." A plumber's caller expects urgency ("I'll get you taken care of right away"); a painter's caller expects a consultation tone ("I can get someone out to look at the scope"). The trade field is present; the differentiation is not.

**Concrete action:** Add `_trade_tone(trade)` to `ai.py` — a function returning a one-sentence tone instruction keyed on trade keyword:
- `plumb`, `hvac`, `roof` (emergency-adjacent): "For this trade, callers often have urgent problems — lead with immediate availability and a reassuring tone."
- `paint`, `landscap`, `lawn` (consultation): "For this trade, callers are planning, not in crisis — lead with the free estimate and what they can expect."
- Default: no additional instruction.
Inject the result into `_system_prompt()` immediately after the `business['trade']` line. Cost: one string check per conversation start.

**Effort:** S (one helper, one injection point).
**Priority:** 4 in Phase 1 — requires clean trade from OA-2; a 30-minute add once that lands.
**Constraint:** Requires OA-2. Without it, `business['trade']` is `"home services"` and the function has no useful input.

---

### OA-9: First-call transcript nudge (new — not in draft)

**Podcast lesson:** "Capability overhead: build on-ramps that guide users to new capabilities."

**How it applies:** The most likely day-1 churn mechanism is not a bad onboarding experience — it is: the AI answers the contractor's first real call and says something that does not match what the contractor expected (wrong tone, offers a slot the contractor can't fill, misidentifies the service). The contractor turns off forwarding that night. The AI preview in the wizard (OA-6, now deferred) is passive. The active version of this fix is: after the first AI-answered call, automatically send the contractor the call transcript and a one-question check-in — "How did that sound? Reply 1 = perfect, 2 = needs tweaking" — closing the capability overhead loop at the riskiest moment. This is the "leave money on the table" principle applied to day-1 retention: forgo the metrics of a clean first-call experience to get explicit contractor feedback before they silently churn.

**Concrete action:** In `voice_service.py`'s post-call handler, after the first call transcript is logged for a given business, check `first_call_nudge_sent` (new boolean column on `businesses`). If not sent, fire a P2P SMS to the contractor's own mobile (no A2P needed — owner-to-owner path): "FirstBack: [Caller name] just called. Here's what happened: [transcript link]. How did it sound? Reply 1 = perfect, 2 = something to tweak." Set `first_call_nudge_sent = 1`. One-time per contractor; fires the night of the first call.

**Effort:** S (new column, one conditional in post-call handler, existing `send_sms` path).
**Priority:** 5 in Phase 1 — highest-leverage day-1 retention action that exists because the transcript is already logged.
**Constraint:** Gated on P0-A. No A2P needed (owner alert, P2P).

---

### TO-1: Daily ops brief for Jack

**Podcast lesson:** Scheduled morning brief: agent reads 20–25 charts → "what to watch / what's concerning / insights." Adapted to one engineer running both PM and ops.

**How it applies:** At Anthropic the morning brief surfaces metric anomalies across a large team. For FirstBack pre-revenue, the equivalent is: how many contractors are in each activation state, are any A2P submissions stuck (pending >20 days), are there forwarding health check failures, what is LLM spend vs cap, are there growth plays held for >7 days with no action. At 0–5 contractors this fits in a 10-line SMS. The value is preventing context loss during the weeks before contractor #1 — the most dangerous phase for a solo founder.

**Concrete action:** Add `daily_ops_brief()` to `growth.py` or a new `ops.py`. Triggered by `/tasks/run-due` once per day. Queries: (1) contractor count by `activation_state`, (2) any `a2p_pending_submit=1` rows older than 20 days, (3) forwarding confirmation failures from OA-1 instrumentation, (4) LLM spend today vs cap (`db.get_llm_spend_today`), (5) growth plays in `held` status with no contractor action for >7 days. Formats as 10 lines of plain text and sends via Twilio to the owner's mobile (existing `send_sms` path, different recipient — no A2P needed, P2P).

**Effort:** S (2 hours; one function, one cron wire).
**Priority:** 6 in Phase 1 — build early; prevents context loss during the pre-revenue sprint.
**Constraint:** Requires owner's mobile number in config.

---

### GA-5: Tone-risk gate for email auto-answer

**Podcast lesson:** "Leave money on the table — forgo metric wins for safety/brand/quality/UX."

**How it applies:** The SMS path already has `_tone_risk()` in `growth.py` (lines 97–113 confirmed) — if a customer's last 5 messages contain negative-sentiment keywords, the play is held. The Gmail auto-answer (`google_mail.py`) has no equivalent gate. A customer who emailed "I'm very disappointed" should not get an AI auto-reply that opens the booking flow.

**Note on implementation:** The draft plan's description of a `held` draft state for email is incorrect. `poll_and_answer_all()` goes directly from `fetch_unread()` to `send_email()`. There is no `scheduled_messages` row for auto-answered emails, so there is no `held` state to toggle. The correct approach matches SMS suppression: if tone-risk detected in subject+body, skip the auto-reply entirely and send an owner alert ("New email from Maria — flagged for review before I reply. Open the app."). No held state; no draft persistence. Same outcome, correct pattern.

**Concrete action:** In `google_mail.py`'s `poll_and_answer_all()`, before drafting a reply, check the email subject and body against `_TONE_RISK_KEYWORDS` imported from `growth.py`. If matched: skip the auto-reply call; send an owner alert via the existing owner-alert path. Same behavior as SMS tone-risk suppression, correct implementation.

**Effort:** S (import and one check; same pattern as `_tone_risk()`).
**Priority:** 7 in Phase 1.
**Constraint:** Requires Google OAuth creds (owner-gated). Build the gate now; it fires when creds are added.

---

### PS-2: Competitive teardown (do while waiting for voice deploy)

**Podcast lesson:** "Competitive teardowns of onboarding/pricing via agent + Chrome extension."

**How it applies:** FirstBack's positioning — "your number, your identity, from minute zero" — is only a differentiation if competitors actually use a platform number. If they do not, the positioning needs adjustment before any public-facing copy is finalized. Targets: Goodcall, Numa, Signpost, Ruby Receptionist. Specific questions: Do they send from the contractor's own number or a platform number? Is setup self-serve in 5 minutes or does it require a sales call? What does flat-rate pricing look like vs FirstBack's $99–$399?

**Concrete action:** One browser-agent session: screenshot the signup flow for each competitor, grab pricing pages, note caller identity (contractor number vs platform number). Output a 1-page teardown. This is a few hours and directly hardens positioning copy before the first contractor lands.

**Effort:** S (2–3 hours; one-time).
**Priority:** Do during the wait for P0-A (voice deploy). This is orthogonal to the build sequence and should not block it.
**Constraint:** None.

---

### PS-3: Billing gate policy

**Podcast lesson:** "Leave money on the table — forgo metric wins for safety/brand/quality/UX → more long-term growth."

**How it applies:** At Anthropic, "leave money on the table" means not launching a product for safety/brand reasons. For FirstBack, the most important application of this principle is not in the code — it is a billing policy decision. The most likely churn catastrophe before positive word-of-mouth exists: contractor signs up, gets confused during wizard, voice is never confirmed live, they are charged $99, they dispute it, churn, and tell their contractor network. One such incident before any reviews exist is catastrophic. The fix is a billing gate: the billing clock starts when voice is confirmed live and the contractor has seen the AI work on a real call, not at signup.

**Concrete action:** Add to `decisions.md` / `[DECIDED]` comments in the codebase: "Billing gate — the Stripe subscription does not activate until `activation_state` transitions to `voice_live` AND `first_call_nudge_sent = 1` (i.e., the contractor has had at least one AI-answered call)." Not a code item for now — a policy decision that must be written down before any Stripe integration ships.

**Effort:** Zero code. One policy decision in writing.
**Priority:** Write this down before Stripe integration is built.
**Constraint:** None.

---

### PS-1 (meta-constraint): Focus

**Podcast lesson:** "FOCUS: do few things, go deep." + "Bias to big bets over micro-optimizations — only if core value is AI-underpinned."

**How it applies:** `crm/`, `providers/telnyx_provider.py`, `outlook_mail.py`, and the `density`/`financing`/`membership` play types are well-written and correctly gated. The risk is attention fragmentation before contractor #1. None of these ship or get refactored until 3 contractors each have at least 1 job booked via voice.

**Concrete action (non-code):** Write one line in `focus.md`: "North star until first $99 invoice: forwarding confirmation rate and calls-answered-by-AI rate." If a session opens with refactoring a CRM integration or the Telnyx provider, redirect. The code exists; the constraint is attention.

**Effort:** Zero code. One decision.
**Priority:** Meta-constraint over everything else in Phase 1.

---

### PS-4: Decisions as agent context — continue writing them down

**Podcast lesson:** "Culture/transparency ('notebook channels') doubles as context for the agents. Companies must write down thinking so agents have what they need."

**How it applies:** Already being done correctly. `ONBOARDING_BLUEPRINT.md` has inline `[DECIDED]`, `[owner decision Jun 29]`, and risk flags. This is exactly what Amol describes and it is working. The add is: apply it to the controversial test framework (below) and the billing gate (PS-3) so future automated agents have the institutional memory.

**Concrete action:** When the first automation (morning brief, ops review, competitive agent) is built, pass the `[DECIDED]` sections from the blueprint as context. This prevents a future agent from "helpfully" suggesting things already explicitly rejected (e.g., a toll-free bridge number).

**Effort:** Zero ongoing cost.
**Priority:** Reinforcement; already being done.

---

### PS-5: Controversial test framework as a named decision tool

**Podcast lesson:** "Controversial-test buckets: (1) never ship (red line) (2) 'yikes but not a red line' → needs high return."

**How it applies:** The plan's "Not Applicable / Rejected" section captures past decisions. But Jack needs a repeatable filter for future decisions, not just a table of past ones. The two-bucket framework, applied prospectively, is 2 minutes of structured thinking before shipping anything that touches contractor or customer experience.

**Concrete action:** Save in `decisions.md`:

*Bucket 1 (red line — never ship regardless of return):* Platform TFN anywhere in the product. ISV shared campaign (AI speaks as "FirstBack's platform" not as the contractor). Auto-enrolling contractors in growth broadcasts without explicit opt-in. Starting the billing clock before voice is confirmed live and a real call has been answered. Auto-approving growth plays that reach customers without contractor review (always human-in-loop until 20+ contractors).

*Bucket 2 (yikes but not a red line — require high return):* Charging full price before contractor has 5 AI-answered calls with booking attempts. Showing estimated job values as exact in growth plays without "(estimated)" label.

Before shipping anything that touches contractor or customer experience: 2-minute Claude pass — "Is this bucket 1, bucket 2, or neither?"

**Effort:** Zero infrastructure. One saved prompt + one documented list.
**Priority:** Process item; implement as a habit, not a ticket.

---

## PHASE 2 — AFTER CONTRACTOR #1 IS PAYING

*These items are correct in design but premature at 0 users. The Mercury lesson requires real drop-off data to act on. OA-4 through OA-8 optimize a funnel that does not yet have flow.*

---

### OA-4: Split wizard Step 1 into two screens

**Podcast lesson:** "Break one multi-input screen into two to cut cognitive load."

**How it applies:** Step 1 in `setup.html` currently presents 8 fields on one screen. The split into "identity" (trade, business name, owner name, mobile) and "legal" (legal business name, EIN/sole-prop fork, business address) is correct in design.

**Implementation note:** When this ships, `_PREREQS["number"]` in `connections.py` must be updated from `("profile",)` to `("legal",)`. Leaving it pointing to `"profile"` after the split references a step key that no longer exists in STEPS — the wizard will error. The prereq cascade is: `"identity"` → `"legal"` → `"number"`.

**Effort:** S-M. **Priority:** Revisit after first 3 contractors report confusion at this step.

---

### OA-5: Split the forwarding step into three sub-screens

**Podcast lesson:** "Break one multi-input screen into two to cut cognitive load" + "Quality drives growth."

**How it applies:** The forwarding step currently presents 5+ distinct decisions on one screen. Split into: (3a) carrier picker only; (3b) star code + tap-to-dial as primary CTA; (3c) TCPA checkbox + click-to-send opt-in + "I've set up forwarding" + the sentinel polling card from OA-1. Progress saved between sub-screens.

**Effort:** M. **Priority:** Revisit after first 3 contractors report confusion at the forwarding step.

---

### OA-6: Trade-specific AI preview before forwarding

**Podcast lesson:** "Capability overhead: build on-ramps." + "Leave money on the table."

**How it applies:** A collapsed `<details>` element in Screen 3b showing one trade-specific example exchange (painter sees exterior estimate call; HVAC sees AC inquiry). Not blocking. Requires clean trade data from OA-2.

**Effort:** S. **Priority:** Deferred; requires OA-2 and real contractor feedback that trust gap exists at this step.

---

### OA-7: On-ramp after activation — one next step, not a menu

**Podcast lesson:** "Capability overhead: build on-ramps that guide users to new capabilities."

**How it applies:** After forwarding is confirmed, the "Get the most out of FirstBack" section shows all optional connections at once. Replace with one dynamic card at a time ordered by value: no Gmail → "Catch email leads too"; Gmail connected → "Import your regulars"; SMS just flipped → informational-only card.

**Effort:** S-M. **Priority:** Deferred; `channel_state.py` integration is already built, template change is the correct scope.

---

### OA-8: Customer import on the Done screen

**Podcast lesson:** "Cold-start: import memory from ChatGPT — meet users where they are, skip the blank-slate problem."

**How it applies:** The exact mechanism (ChatGPT import) does not apply. The principle does. On the Done screen, one prompt: "Recognize your regulars. Import your past customers so FirstBack can ask for reviews and re-book them." Link to `/api/contacts/import` (confirmed in `app.py` line 2697). If Gmail is already connected, offer a one-tap "Import from Gmail contacts" shortcut.

**Effort:** S (route exists; framing and link addition only). **Priority:** Deferred; value emerges once `plays()` has seeded data to act on.

---

### GA-2: Contractor morning money brief

**Podcast lesson:** Amol's morning brief: agent reads 20–25 charts → "what to watch / what's concerning." Adapted to 2-line SMS to the contractor.

**How it applies:** `money_left_behind()` in `growth.py` already computes the contractor's morning number. `plays()` already ranks the opportunities. The missing piece is delivery. A daily 2-line SMS at 8am means the contractor knows money is on the table without opening the app. Principle transfers; density does not.

**Gating constraint:** `live_sms` is required (no P2P for scheduled broadcasts). This means A2P 10DLC clearance (~10–15 business days after contractor is set up). This is a day-30 item at minimum. Default 8am ET — do not derive timezone from zip (requires a bundled zip-to-timezone lookup table that does not exist in the codebase; add to a future polish list).

**Concrete action:** Add `morning_play_brief(business_id)` to `growth.py`. Calls `plays()`, picks top 2 by money, formats a 2-line SMS. Wire into `/tasks/run-due` with time-of-day check (8am ET). Gate: only fires if `activation_state == 'live_sms'`, `brief_on` flag set, and at least 1 sendable play exists.

**Effort:** S-M. **Priority:** Build once `live_sms` is a real state for a real contractor.

---

### GA-3: Brand-skill check gate

**Podcast lesson:** CACHE stage 3 — "test vs. quality + brand bar" before any experiment ships.

**Note on timing:** At 0 contractors with 0 plays reaching real customers, a brand-check LLM gate screens hypothetical messages. The existing `_tone_risk()` already covers live safety risk. Manual review covers brand quality at this scale. Build this when plays are reaching customers at 20+ contractors and can no longer be reviewed individually. The CACHE framework automates experimentation at scale; at current volume, reading your own copy does the same job in 30 seconds.

**Effort:** S (when built). **Priority:** Deferred to 20+ contractors.

---

### GA-4: Play outcome tracking

**Podcast lesson:** CACHE stage 4 — "analyze/learn." Score the model per stage, hill-climb.

**Table name correction:** The actual table is `growth_touch_log` (`db.py` line 698), not `growth_touches`. The draft plan had the wrong name throughout.

**Concrete action (when timing is right):** Add `reply_within_48h` (boolean) and `booking_within_7d` (boolean) columns to `growth_touch_log`. In `messaging.py`'s inbound handler, when an inbound message arrives, check if there is a `growth_touch_log` entry sent to that number within 48 hours and flip `reply_within_48h=1`. In the booking confirmation handler, flip `booking_within_7d=1`. Build tracking early; run analysis manually until 30+ touches with outcomes exist.

**Effort:** S-M. **Priority:** Build after 20+ plays have been sent to real customers.

---

### GA-6: `touch_count_12mo` in contractor tray

**Podcast lesson:** "Leave money on the table — visibility over suppression."

**N+1 note:** `growth_touch_count_12mo()` makes one DB query per lead call. Adding it inside `_opp()` means N extra queries per `plays()` call (one per lead) — on every page load and morning brief. Batch it with the existing `growth_touch_index()` single query that already builds the `touched` dict inside `plays()`, not inside `_opp()`.

**Concrete action:** In `plays()`, batch `touch_count_12mo` for all leads in one query alongside `growth_touch_index()`. Add it to each `_opp()` dict. In the tray template, display "3rd contact this year" in muted text when `touch_count_12mo >= 2`. No gate — the contractor decides.

**Effort:** S. **Priority:** After `growth_touch_log` is populated with real data.

---

### TO-3: Weekly ops review

**Podcast lesson:** "Strategy bot — constantly watching metrics, market, roadmap."

**How it applies:** At pre-revenue the strategy is obvious — get voice live. The bot adds value when you have enough contractors that the strategy is non-obvious. Build at 10+ contractors: which are stuck in `SETUP` and why, which have growth plays held for >7 days, voice call volume trends by trade, highest-ROI play type by trade (from GA-4 outcome tracking).

**Effort:** M. **Priority:** Deferred to 10+ contractors; requires GA-4 running first.

---

## Top 3 Highest-Leverage Bets

**1. P0-A — Deploy `VOICE_PUBLIC_URL` (the real #0)**
Not in the original draft. The single prerequisite for every other item. Voice is the day-0 catch; every activation, retention, and growth mechanism is inert without it. This is not a mindset choice — it is a concrete engineering action: sidecar server, real public URL, ConversationRelay TwiML with FCC disclosure, one test call. Nothing else matters until this is done.

**2. P0-B — Cold outreach to 20 contractors in a specific local trade + market**
The plan had no acquisition path. Every build item is internal. The most direct application of the podcast's cold email lesson: specific hypothesis, specific person (or cohort), short message, direct follow-up. Target painters or HVAC contractors in one metro via Facebook groups and Nextdoor Pros. Run this in parallel with voice deploy. Contractor #1 is the only milestone that validates everything else.

**3. OA-1 + OA-2 as a same-sprint pair (the Mercury move)**
Once voice is deployed and contractor #1 is inbound, these two are the quality and data foundation for everything else. OA-1 (sentinel fix) is the blocking quality issue — a contractor who cannot confirm they are live will not trust the product and will not pay. OA-2 (trade pills at signup) is a two-file change that unlocks every downstream personalization: voice tone, growth play accuracy, lifecycle emails, re-engagement. Together: S-M effort, and GA-1 (trade-aware voice tone) follows as a 30-minute add.

---

## Deliberately Not Applying (and Why)

| Lesson | Verdict | Reason |
|---|---|---|
| **CACHE full automation — copy variants, auto-experimentation, hill-climbing** | Not yet | Requires statistical volume. 5–20 contractors/month cannot support a 2-variant test. Build brand-check gate (GA-3) and outcome tracking (GA-4) first; add experimentation infrastructure at $30K–$50K MRR. |
| **"Win rate = junior PM" for AI copy at scale** | Not yet | Only valuable at volume. At 20 contractors, manually craft every communication touchpoint. |
| **Platform toll-free bridge SMS** | Rejected (owner decision, Jun 29) | Off-brand for a local contractor; undercuts premium pricing. Voice is the day-0 catch. No platform TFN anywhere in the product. |
| **Per-contractor toll-free bridge** | Rejected (blueprint) | Requires BRN/EIN as of Feb 2026; most solo trades have no EIN. |
| **Log-linear chart culture, 25-chart morning review** | Not applicable | Get to revenue first. No charts to read at 0 contractors. |
| **Strategy bot watching metrics + market + roadmap** | Too early | Strategy at pre-revenue is obvious: get voice live. Revisit at 10+ contractors (TO-3). |
| **40-person team structure; engineers-as-mini-PMs org design** | Does not transfer | Solo founder. The two-week rule transfers (every decision is ≤2 weeks by definition); the org design does not. |
| **Manager/report coaching bot** | Does not transfer | Internal Anthropic tooling for a large team. No analog at FirstBack's stage. |
| **Cold email blast infrastructure** | Does not transfer at scale | The personalization principle transfers (trade-specific outreach, re-engagement). The blast infrastructure does not — local contractor market is trust-based and regional. Equivalent: targeted community presence in contractor Facebook groups, Nextdoor Pros, and supplier partnerships (Sherwin-Williams reps know every painter in a territory). |
| **ISV shared campaign / "Agents & Franchises" shared SMS** | Rejected (blueprint) | Forces the AI to speak as "FirstBack's platform" not as the contractor. Breaks product identity. AT&T post-reg approval adds weeks. |
| **Telnyx migration now** | Deferred | Bottleneck is TCR's vetting queue, not the CPaaS. The `providers/` abstraction (Phase 3, already built) makes it a config swap at ~50 contractors. |
| **GA-2 (morning money brief) in Top 3** | Deferred from Top 3 | Gated on `live_sms` which requires A2P 10DLC clearance (~10–15 business days after contractor is set up). Four sequential dependencies before it can fire. Correct long-term automation; wrong short-term priority. |
| **OA-4 through OA-8 now** | Deferred | Premature optimization. The Mercury lesson about spending a quarter on onboarding quality applies to a product with paying users generating measurable drop-off. At 0 contractors there is no funnel to optimize. Revisit when a contractor reports confusion at a specific step. |

---

## Ordered Build List

### Phase 1 — before contractor #1 is paying

| # | Initiative | File(s) | Effort | What it unblocks |
|---|---|---|---|---|
| 0 | P0-A: Deploy `VOICE_PUBLIC_URL` + sidecar + ConversationRelay | `voice_service.py`, infra | S-M | Everything — absolutely nothing else works without this |
| 0 | P0-B: Cold outreach, 20 contractors in 1 trade + market | Human action | S | Contractor #1 |
| 1 | OA-1: Sentinel fix (with real-carrier testing) | `connections.py`, `setup.html` | M-L | First contractor confirmed live |
| 2 | OA-2: Trade pills at signup | `auth.html`, `app.py` | S | GA-1, GA-2 (future), lifecycle emails |
| 3 | GA-1: Trade-aware voice tone | `ai.py` | S | Day-1 voice retention |
| 4 | OA-9: First-call transcript nudge | `voice_service.py`, `db.py` | S | Day-1 churn prevention |
| 5 | OA-3: Sole-prop fork UI cleanup | `setup.html` | S | Trust signal at wizard |
| 6 | GA-5: Tone-risk gate for email | `google_mail.py` | S | Brand safety on email channel |
| 7 | TO-1: Daily ops brief for Jack | `growth.py` or `ops.py` | S | Context preservation pre-revenue |
| 8 | PS-2: Competitive teardown | Browser agent | S | Positioning hardening (run during P0-A wait) |
| 9 | PS-3: Billing gate policy | `decisions.md` | 0 | Churn catastrophe prevention |
| 10 | PS-5: Controversial test framework | `decisions.md` | 0 | Repeatable product decision filter |

### Phase 2 — after contractor #1 is paying (revisit with real data)

| # | Initiative | File(s) | Effort | Gate condition |
|---|---|---|---|---|
| 11 | OA-4: Split wizard Step 1 (with prereq cascade fix) | `connections.py`, `setup.html` | S-M | Contractor reports confusion at profile step |
| 12 | OA-5: Split forwarding step into sub-screens | `setup.html` | M | Contractor reports confusion at forwarding step |
| 13 | GA-2: Contractor morning money brief | `growth.py` | S-M | `live_sms` state exists for ≥1 contractor |
| 14 | OA-6: Trade-specific AI preview in wizard | `setup.html` | S | Requires OA-2; contractor reports trust gap |
| 15 | OA-7: Sequential on-ramp post-activation | `setup.html`, template | S-M | `channel_state.py` integration already built |
| 16 | OA-8: Customer import on Done screen | `setup.html` | S | Growth engine has real history to act on |
| 17 | GA-4: Play outcome tracking | `db.py`, `messaging.py` | S-M | 20+ plays sent to real customers (table: `growth_touch_log`) |
| 18 | GA-6: `touch_count_12mo` in tray (batched, not per-lead) | `growth.py`, template | S | `growth_touch_log` populated with real data |
| 19 | GA-3: Brand-skill check gate | `growth.py` | S | 20+ contractors; plays no longer manually reviewable |
| 20 | TO-3: Weekly ops review | `ops.py` | M | 10+ contractors; requires GA-4 running |

---

## FirstBack's Hypothesis

FirstBack's bet is that the moment a missed call becomes a booked job — automatically, from the contractor's own number, while they're on the ladder — is worth $99–$399 per month to the contractor who has lost that revenue blind for years. The specific hypothesis to validate with contractor #1: a solo painter or HVAC contractor in a mid-size US metro, already spending money on Google ads or word-of-mouth, is losing 1–3 bookable calls per week to voicemail. If FirstBack catches one of those per week, the ROI is immediate and obvious. The first three months are about proving this loop works on real calls, with real bookings, before building anything else. **[Owner: fill in the specific trade, metro, and the number of missed-call bookings per week that would make a contractor pay without hesitation.]**

---

## Appendix — loop trail (brainstorm → audit)

*The reasoning behind this plan, for the orchestrator. Produced by 2 Sonnet agents per round.*

<details>
<summary><b>Brainstorm A — Onboarding &amp; Activation lens</b></summary>

Now I have the full picture. Here is the analysis:

---

# Podcast Lessons → FirstBack Onboarding & Activation: Grounded Idea List

---

## What the codebase actually shows (baseline)

Before mapping lessons: a few observations the read surfaced that are material.

**Signup (auth.html):** Business name, owner name, email, password, one EIN checkbox ("I have an EIN — my business is an LLC or corporation"). NO trade selection in the UI — `app.py` line 339 defaults it to `"home services"` silently.

**Wizard Step 1 (setup.html profile form):** 8 fields on one form — business name, trade (free text, `placeholder='e.g. Painting'`), owner name, service area, legal business name, EIN text field (with a hint note), business address, website. The EIN field is a text input, even though `business_type` was already set at signup via the checkbox.

**Wizard Steps 2–4:** Number picker, A2P auto-submit, forwarding step (carrier picker, star code, tap-to-dial, iPhone warning, TCPA checkbox, click-to-send opt-in).

**Trade downstream:** `growth.py` uses keyword matching against the trade string (`_SEASONS`, `_FINANCING_BY_TRADE`, `_TRADE_DEFAULT_VALUE`). `ai.py` line 89 injects `business['trade']` into the brain's context. Both work best with a clean, known value — and currently every new contractor gets `"home services"` until they reach wizard Step 1.

---

## Idea 1: Trade pills at signup, not in the wizard

**Lesson (exact):** "The who-are-they data compounds: activation → lifecycle → look-alike ad retargeting if they drop. 'Juice that keeps giving.'" + "Right friction — ask who they are / their goals → recommend the right product."

**How it maps:** The trade field exists in `app.py`'s `/signup` handler (line 339) but is not exposed in `auth.html` — it silently defaults to `"home services"`. Every contractor enters the wizard as an undifferentiated "home services" business. This breaks `growth.py`'s seasonal plays (a painter shouldn't get the HVAC tune-up pitch), degrades the AI's voice context in `ai.py`, and leaves no segmentation data for re-engagement if they abandon before completing Step 1.

**Take as-is or adjust?** TAKE — this is the exact lesson. One change at signup: replace the free-text absence with a pill grid (Painting / HVAC / Plumbing / Roofing / Electrical / Landscaping / Other) as the first UI element after "Business name." Two taps. This is the highest-information, lowest-friction thing you can ask before the wizard.

**Concrete change:** In `auth.html`, add a trade pill grid after "Business name" — the `<input type="hidden" name="trade" value="">` is updated by the tap. In `app.py` signup handler (line 339), remove the `"home services"` fallback and validate that a trade was selected. The data immediately: (a) personalizes the Step 1 wizard ("Set up your painting business" vs. "Set up your HVAC business"), (b) drives trade-specific welcome email, (c) powers re-engagement if they abandon after signup but before completing the wizard — the only moment you know their trade with zero wizard completion.

---

## Idea 2: Split wizard Step 1 into two screens

**Lesson (exact):** "Break one multi-input screen into two to cut cognitive load."

**How it maps:** Step 1 currently has 8 fields: business name, trade, owner name, service area, legal name, EIN, address, website. A contractor on their phone between jobs hits this first and has no established context for why "legal business name" or "service area" matters yet. Nothing in this step delivers value — it's all collection before any payoff.

**Take as-is or adjust?** TAKE — directly applicable. The split maps cleanly to two distinct categories already embedded in the form:

- **Screen 1a ("Tell us about your work" — 30 seconds on mobile):** Trade pills (if not captured at signup), business name, owner name, mobile number (needed for OTP and alert SMS — currently captured only if passed from the landing hero). This is identity: who you are, what you do. Payoff visible immediately: the wizard personalizes to their trade.
- **Screen 1b ("Carrier registration — one time" — 60 seconds):** Legal business name (explain why: "Phone carriers verify this"), EIN/sole-prop fork (see Idea 3), business address. Frame as: "This is what lets your texts go out in your name — you only fill this in once." The 8 fields become 4 + 4 with a clear purpose statement on each.

**What changes:** In `connections.py`, `STEPS` currently defines `"profile"` as a single step. Split into `"identity"` and `"legal"` with `_PREREQS["legal"] = ("identity",)`. The wizard advances to the number step only after both are done. The cognitive separation is more important than the total field count.

---

## Idea 3: Explicit sole-prop fork, not a text-field hint

**Lesson (exact):** "Right friction — understand the user to recommend the right path. Cut bad friction (steps with no value), keep good friction (make it FOR THEM)."

**How it maps:** The EIN fork is actually done correctly at **signup** — `auth.html` has an EIN checkbox, `app.py` sets `business_type` to `sole_prop` or `llc`. But wizard Step 1 still shows an "EIN (business tax ID)" text input with a hint ("Sole proprietors can skip this"). This is confusion-as-UI: the business_type was already set, yet the form re-asks it ambiguously. A contractor who said "no EIN" at signup now sees an EIN field again and wonders if they missed something.

**Take as-is or adjust?** ADJUST — the backend EIN fork is correct. The wizard Step 1 UI needs to reflect what was already decided. Two changes:

1. If `business.business_type == 'sole_prop'`: hide the EIN field entirely in setup.html, show one line: "Sole proprietor — no tax ID needed." The text "EIN on file" in the step summary (line 228) should change to "Sole proprietor" for this case.
2. If `business.business_type == 'llc'`: show the EIN text field with a clear label: "Business EIN (your LLC's tax ID)."

The wizard should never force a contractor to re-negotiate a decision they already made at signup.

---

## Idea 4: Show an AI response preview before "I've set up forwarding"

**Lesson (exact):** "Leave money on the table — forgo metric wins for safety/brand/quality/UX → more long-term growth. Best products all do this."

**How it maps:** The forwarding step is the critical activation event. Once a contractor taps the star code, their customers start hearing the AI on the very next missed call. A contractor who doesn't know what the AI will say is making a trust-free leap. Churn risk: they try it, a customer gets an AI response that doesn't match the contractor's voice, and they turn it off the next day.

**Take as-is or adjust?** ADJUST — "leave money on the table" at Anthropic means declining experiment wins that hurt the brand. For FirstBack, it means accepting that showing a preview might lower the forwarding completion rate slightly but dramatically lowers day-1 churn. Different tradeoff than a lab with millions of users, but the direction is the same: optimize for long-run retention, not conversion.

**Concrete change:** Before the TCPA checkbox in the forwarding step, add a single collapsed-by-default `<details>` panel: "See what your callers experience." Inside: one short, trade-specific example exchange (a painter sees a painter scenario, an HVAC contractor sees an AC inquiry). The example is generated at page-render time by pulling the business's trade from `business.trade` and picking a pre-written scenario. Not blocking — it's a `<details>` element. Contractors who expand it complete the step with higher confidence. Contractors who don't are unaffected.

---

## Idea 5: Mercury play — fix the sentinel before shipping anything else

**Lesson (exact):** "Mercury: spent a WHOLE QUARTER fixing onboarding QUALITY ('forget metrics') → biggest growth result of his career. 'Quality drives growth.' Onboarding is the first experience — invest like the rest of the product."

**How it maps:** This is the most direct, highest-priority translation. ONBOARDING_BLUEPRINT.md risk #4 explicitly flags: "Sentinel SID-matching broken — replace with self-call detection." The forwarding-confirmation sentinel currently uses SID matching that breaks because carrier forwarding mints a new call SID. A contractor who sets up forwarding gets either a false confirmation or no confirmation — and walks away unsure if they're live.

**Take as-is or adjust?** TAKE — the Mercury lesson is exactly this: before the next feature, make the activation moment actually work. The sentinel is the "did it work?" signal at the most critical moment in onboarding.

**Concrete change:** The fix is already designed in ONBOARDING_BLUEPRINT.md Phase 1: self-call fingerprint (match `From == biz.twilio_number` within a 120-second sentinel window), plus AMD detection (`machine_start` = voicemail intercept), plus a `GET /api/forwarding/status` polling endpoint. The wizard shows a live "checking your forwarding..." card after the contractor taps "I've set up forwarding" — polling every 5 seconds — then shows either "Confirmed — you're live" or "Not detecting it yet — try again" with a retry button. This is the Mercury move: one sprint on quality, zero new features until this is solid.

---

## Idea 6: Post-activation on-ramp — one next step, not a menu

**Lesson (exact):** "Capability overhead: build on-ramps that guide users to new capabilities."

**How it maps:** After forwarding is confirmed (VOICE_LIVE state), `setup.html` shows a static "Get the most out of FirstBack" section with a list of optional connections. This is a menu of capabilities with no ordering signal. A contractor in VOICE_LIVE state is coming off the high of "I just set that up" — the right moment to capture one more activation, not present a list of 6 options.

**Take as-is or adjust?** TAKE — directly applicable. The on-ramp model is sequential, not a menu.

**Concrete change:** Make the "Get the most out of FirstBack" section dynamic based on `channel_state.py` (already built in Phase 3). The section shows exactly ONE card at a time, ordered by value:

- State: VOICE_LIVE, no Gmail → "Catch email leads too" + "Connect Gmail" button (2 taps, already built in `google_mail.py`)
- State: VOICE_LIVE + Gmail, no contacts → "So FirstBack knows your regulars" + "Import customer list" button (links to `contact_import` route already in the codebase)
- State: LIVE_SMS just flipped → "Texts now go automatic — here's your first week" (a moment-of-delight notification, no action required, just an update)
- State: LIVE_SMS + contacts + 30 days → first growth.py seasonal play surfaces as the next step

Each card has a single CTA and a one-line explanation of why it matters now. The "progress bar" in the section (`fs-meter` in the current HTML) stays, but it advances through the on-ramp sequence rather than all optional items at once.

---

## Idea 7: Contact import as the cold-start bridge on the Done screen

**Lesson (exact):** "Cold-start: import memory from ChatGPT (meet users where they are, skip the blank-slate problem)."

**How it maps:** In the transcript, this refers to a specific feature where Anthropic's Claude can import a user's ChatGPT conversation history to skip the cold-start problem. The principle: don't make users start from zero when they have existing context somewhere. For FirstBack, the cold-start problem is that the AI doesn't know the contractor's existing customers. When a returning customer calls and the AI has no record, the experience is worse than for a new customer.

**Take as-is or adjust?** ADJUST — the exact mechanism (ChatGPT import) doesn't apply; the principle does. The bridge for contractors is their existing customer list, which may be in Gmail contacts, a spreadsheet, or a CRM.

**Concrete change:** On the Done screen (after forwarding confirmed, when the status checklist shows), add a single prompt under the checklist: "Recognize your regulars. Import your existing customers so FirstBack can greet them by name." Link goes to `/contacts/import` (already in the codebase via `contact_import.py`). Alternative: if Gmail was connected in the on-ramp, offer "Import from Gmail contacts — one tap." The framing matters: don't say "import contacts," say "so FirstBack knows who's calling before they speak." This is the cold-start bridge in contractor language.

---

## Idea 8: Trade-segmented lifecycle emails (the data compounds)

**Lesson (exact):** "The who-are-they data compounds: activation → lifecycle → retargeting. 'Juice that keeps giving.'"

**How it maps:** This is the downstream payoff of Idea 1. Once trade is captured cleanly at signup (not defaulted to "home services"), every email — confirmation, onboarding drip, re-engagement — can be trade-specific. This is the "compounding" the lesson describes.

**Take as-is or adjust?** TAKE — but it only activates once trade data is clean. Ideas 1 and 2 are prerequisites.

**Concrete sequences:**
- Welcome email after signup (immediate): "Your [trade] AI is ready — here's what happens next" — with one trade-specific job example ("a painter's caller asking about exterior prep" vs. "a plumber's caller with an emergency leak")
- Day 7, VOICE_LIVE: "You've answered X calls automatically this week — here's the transcript" — trade-specific framing ("X paint estimates auto-handled")
- Drop-off after signup, never completed forwarding: trade-specific urgency — "For plumbers, a missed emergency call is typically $800+. Here's the 90-second setup you haven't finished." This is where the trade data captured at signup (Idea 1) pays off: you can send this before they ever touched the wizard, because you have the trade from signup.
- Pre-10DLC expiry approaching: "Your texts go automatic in 3 days — here's what changes" (no action needed, builds anticipation)

None of these require new infrastructure — `mail.py` and the existing `alerts` system handle outbound email. The only missing piece is (a) clean trade data from signup and (b) a triggered email queue keyed to `activation_state` changes.

---

## Idea 9: The forwarding step deserves a split screen

**Lesson (exact):** "Break one multi-input screen into two to cut cognitive load" + "Quality drives growth."

**How it maps:** The forwarding step is the single most cognitively loaded moment in the wizard. It currently puts on one screen: iPhone Live Voicemail warning, carrier picker (submit form), code card with tap-to-dial, TCPA consent checkbox (legally required), click-to-send opt-in checkbox (optional), a submit button, and an advanced "ring my cell first" option. A contractor on a phone who's never done call forwarding before is navigating 5 distinct decision points simultaneously.

**Take as-is or adjust?** TAKE — directly applicable.

**Split:**
- **Screen 4a — iPhone warning + carrier picker:** Full width, single focus. "First: pick your carrier." iPhone warning is a banner, not a footnote. Carrier selector + "Show my code" is the only action. This screen's entire purpose is to get them to the right star code.
- **Screen 4b — the dial action:** Full width. The star code, tap-to-dial as the primary CTA (large button, not a text link). "Done dialing?" advances to 4c.
- **Screen 4c — confirm + consents:** TCPA checkbox (required), click-to-send opt-in (optional, clearly secondary), "I've set up forwarding" button. Then the sentinel polling card from Idea 5 replaces the button after submit.

Three sub-screens for one step. Each has one job. A contractor who abandons between 4a and 4b has at least selected their carrier — that data is saved and they can resume.

---

## What does NOT transfer — explicit flags

**1. CACHE (automated growth experimentation at scale).** The podcast's CACHE system ("press play, it prints money") requires statistical volume — thousands of signups per month to detect winner variants with significance. FirstBack is pre-revenue with potentially 5–20 contractors/month at launch. Running copy variants or UI experiments on that sample produces noise, not signal. The lesson to extract is narrower: automate the operational mechanics of growth (the plays in `growth.py`, the lifecycle emails in Idea 8) — not the experimentation infrastructure. Revisit at $30K–$50K MRR when signup volume can support a 2-variant test.

**2. "Win rate ≈ junior PM" for AI-generated copy.** Anthropic has enough daily signups that an AI generating copy variants with even a 15% win rate compounds to meaningful revenue. For FirstBack at 20 contractors, manually crafting every communication touchpoint is correct and sufficient. Auto-generating and scoring copy variants is only valuable at volume.

**3. Engineers as mini-PMs, two-week rule.** This is an org design lesson for a team of 5+. Not applicable at pre-revenue stage.

**4. Morning brief agent reading 20–25 charts.** Anthropic has the data density to justify this. FirstBack's command-center AI is a better analog — but it's already more sophisticated than a chart-reading agent, and the contractor doesn't have 25 charts. The principle (surface the important thing, not everything) transfers via the on-ramp in Idea 6 — don't show all optional items at once.

**5. Cold email mastery at scale.** The transcript describes cold outreach infrastructure optimized for high volume. For a pre-revenue SaaS targeting local contractors (a regional, trust-based market), the equivalent is targeted community presence: contractor Facebook groups, Nextdoor Pros, trade association partnerships, referral from suppliers like Sherwin-Williams or Ferguson. The personalization principle transfers; the blast infrastructure does not.

**6. Manager/report coaching bot.** Internal Anthropic tooling. Not applicable.

---

## Priority ordering (grounded in the actual build state)

| Priority | Idea | Why now |
|---|---|---|
| 1 | Idea 5 — fix the sentinel | Mercury move: quality first. This is flagged as the critical deferred item in the blueprint. Nothing else matters if the activation moment silently fails. |
| 2 | Idea 1 — trade pills at signup | Unblocks everything downstream. Currently every new user is `"home services"`. Two-line fix in auth.html + one-line fix in app.py. |
| 3 | Idea 3 — sole-prop fork cleanup in wizard | The backend is correct; the wizard UI is confusing. Low-effort, high-trust-signal for the contractor. |
| 4 | Idea 2 — split Step 1 into two screens | Cognitive load reduction at the most complex data-collection moment. Requires a new step in `connections.py`. |
| 5 | Idea 9 — split the forwarding step | Same lesson applied to the most critical activation moment. Three sub-screens. |
| 6 | Idea 4 — AI response preview | Trust-building before activation. Pre-written scenarios per trade, `<details>` element. Low risk, low effort. |
| 7 | Idea 6 — on-ramp (one next step) | Replaces the static optional-connections list with a sequential guide. Uses `channel_state.py` already built. |
| 8 | Idea 7 — contact import on Done screen | Cold-start bridge. One link addition; the route already exists. |
| 9 | Idea 8 — trade-segmented lifecycle emails | Requires Ideas 1 and 6 first. Highest long-term compounding value, lowest urgency at pre-revenue stage. |

</details>

<details>
<summary><b>Brainstorm B — Growth automation &amp; Product/Ops lens</b></summary>

Now I have enough context. Let me produce the analysis.

---

# Podcast → FirstBack: Growth Automation + Product/Ops Lessons

Source: Lenny's × Amol Ezzat Sary (Head of Growth, Anthropic), synthesized against the actual codebase.

---

## 1. CACHE — Automating Growth Experimentation

**Lesson (transcript, ~40k mark):** Anthropic's "CACHE" initiative uses Claude to automate 4 stages of growth experimentation: (1) identify opportunities, (2) build, (3) test vs brand/quality bar, (4) analyze/learn. Currently: copy + minor UI tweaks, human-in-loop approve, a "brand skill" of do's/don'ts. Win rate ≈ junior PM. Stage 5 (cross-functional alignment) stays human.

**FirstBack mapping:** `growth.py` already IS a partial implementation of stage 1 + 2. It identifies money-ranked opportunities (plays) and drafts copy. What's missing: stages 3 and 4. Stage 3 equivalent = a "brand quality check" before surfacing a play. Stage 4 = tracking which copy variants produce actual replies and bookings.

**TAKE vs ADJUST:** Take the concept; radically shrink the scope. CACHE at Anthropic operates on thousands of experiments/week across millions of users. At 5–10 contractors you have zero statistical power. Build the infrastructure now; don't expect A/B signal until 50+ contractors.

**Concrete changes:**
- Add a `copy_variants` column or table keyed on `(play_kind, trade)`. When a growth play draft is generated, route it through a single Claude call: "Does this sound like a local contractor texting a customer, or a marketing robot? Return: pass / flag + reason." If flagged, set `status='held'` and surface to Jack (not contractor) before it enters the contractor's tray. This is the "brand skill" equivalent — one function, one API call, no new infrastructure.
- Add `reply_within_48h` and `booking_within_7d` boolean columns to `growth_touches`. This closes the stage-4 loop. Even at low volume, after 20–30 tracked plays you'll have signal on which play types and copy patterns convert.
- The cross-functional alignment stage (stage 5) for FirstBack is the CONTRACTOR's one-tap approve flow, not an internal stakeholder review. The current `held` → contractor-approves → `pending` flow already implements this correctly.

**What does NOT transfer:** Auto-firing experiments without human review is dangerous at this stage. Contractors are trusting "their" AI to sound like them. A bad automated message sent from "Dave's Painting" to a past customer is a churn event, not a stat you can unship. Keep human (contractor) approval on every outbound play until you have 100+ plays with measured reply rates.

---

## 2. Personal AI Automation Stack — For Jack, and the Contractor Analog

**Lesson (transcript, ~65k mark):** Amol's personal stack: scheduled morning brief (20–25 charts → "what to watch / what's concerning"), weekly misalignment detector across Slack/projects, manager/report coaching model, admin automation (booking rooms, inbox triage, expenses), and a forthcoming "strategy bot" that watches metrics + market + roadmap → "here's the pivot."

**Subcategory A — For Jack (the FirstBack team itself):**

**TAKE:** Directly applicable. You are both the PM and the ops team, and the equivalent of "20–25 charts" is: active contractors, forwarding confirmation status, A2P pending/approved/failed, missed calls captured vs answered, growth plays queued vs sent, daily LLM spend.

**Concrete change:** Add a `daily_ops_brief()` function to `growth.py` or a new `ops.py`. Triggered by `/tasks/run-due` once per day, it:
1. Queries: contractor count by activation_state, any `a2p_pending_submit=1` rows older than 20 days (flag for Twilio follow-up), forwarding health check failures, LLM spend vs cap, growth plays in `held` status awaiting action.
2. Formats as a 10-line plain-text brief.
3. Sends to Jack's phone via Twilio (same `send_sms` path, but to the owner's mobile, not a lead).

Cost: ~2 hours to build. This is the most underrated item on this list. Pre-revenue founders lose context fast; a daily "here's what's broken and what's on the table" text stops that.

**Misalignment detector:** At this stage, the misalignment risk isn't between teams (there are no teams). It's between what you're building and what the first 3 contractors actually need. The analog: a weekly pass over any contractor support messages or Vic conversation transcripts, looking for patterns (callers hanging up before booking, wrong trade detection, urgent-keyword false positives). This is worth doing manually for the first month — you need to read every conversation anyway. When you have 10+ contractors, automate it.

**Subcategory B — For Contractors (the agent running THEIR growth/reviews/referrals):**

**This is the biggest, most grounded opportunity from the podcast.** Amol's morning brief tells him what to pay attention to. FirstBack's growth engine already computes exactly this for Dave the painter: `money_left_behind()` returns a headline and a play-count. Dave does not see this as a morning briefing — he only sees it if he opens the app.

**TAKE:** Turn `money_left_behind()` into a push or daily text to the contractor. Each morning at 8am: "Dave, you have ~$3,400 on the table today: ask Maria for a Google review (job wrapped yesterday), follow up on Tom's estimate from 3 days ago. Tap to act." This is the strategy bot — but for Dave's 8 leads, not Anthropic's metrics. The data is already there. Delivery is missing.

**Concrete change:**
- Add a `morning_play_brief(business_id)` function that calls `plays()`, picks the top 2 by money, and formats a 2-line SMS: "FirstBack: [contractor name], ~$X on the table. [Play 1 title]. [Play 2 title]. Open the app to send." 
- Gate: only fires if `growth_on` or new flag `brief_on`; only if there are plays; A2P must be live_sms (don't send via platform number).
- Wire into `/tasks/run-due` with a time-of-day check (8am contractor local time — use their address zip to infer timezone offset, or default to 8am ET).
- This is maybe 3–4 hours of code. The UX unlock is enormous: contractors don't need to log in to know money is on the table. The app comes to them.

---

## 3. Big Bets vs Micro-Optimizations

**Lesson (transcript, ~28k–40k):** Anthropic flips the usual 70/30 small-vs-large to roughly 50/50 or even 70% large bets. Amol's explicit qualifier: "This is IF the primary value your product delivers is underpinned by AI as a central element." Normal SaaS: product value +30–50% in 2 years. AI-first: 100–1000x in 2 years. Micro-optimizations capture a meaningful share of a static value pool; they miss the forest when the forest is growing exponentially.

**TRANSFER ASSESSMENT: PARTIAL. Requires honest adjustment.**

FirstBack IS AI-first — the entire product value (voice AI answering, booking, growth plays) is AI-underpinned. So the spirit applies. But Anthropic is at $19B ARR with 40 growth engineers. FirstBack is pre-revenue with one engineer. At pre-revenue, there is only one "big bet" available, and it has already been placed: get voice answering working for contractor #1. 

The practical translation is NOT "spend 70% on big bets." It is: **do not let micro-optimizations steal focus from the critical path to first revenue.** The critical path is: VOICE_PUBLIC_URL deployed → first contractor forwarding confirmed → first missed call answered by AI → first job booked. Every hour spent on CRM integrations, financing prompts, seasonal campaigns, or providers abstraction before this milestone is a micro-optimization that costs macro-focus.

**Concrete constraint:** Freeze all non-voice features in the app UI behind a "coming soon" state until you have 3 contractors each with at least 1 job booked via voice. Then unfreeze email auto-answer. CRM integrations last. The code is written; the constraint is product prioritization, not engineering.

**What does NOT transfer:** The "index towards larger bets" advice doesn't mean "build big features." It means "don't spend a quarter A/B testing button colors." At FirstBack's stage, the equivalent is "don't spend a week optimizing follow-up message timing before you have a working voice call."

---

## 4. Focus / Do-Few-Things-Deep ("Freedom Through Constraints")

**Lesson (transcript, ~75k):** Anthropic's coding bet wasn't just a market bet — it was a feedback loop: better coding → accelerates research → better models → better coding. They're smallest/least-funded → constraint forced narrow focus → escape velocity. "Freedom through constraints."

**DIRECT TRANSFER.** FirstBack has the same constraint structure: pre-revenue, one engineer, real blockers (VOICE_PUBLIC_URL, A2P, Stripe, Google creds) owned by one person. The constraint is real.

The current codebase is already sprawling: providers abstraction, Gmail OAuth, Outlook OAuth (mentioned in blueprint Phase 2), 5 CRM integrations (all gated), channel_state FSM, growth engine with 8 play types, seasonal campaigns, financing plays, density heatmaps. All of this code is well-written and correct. The risk is that the breadth fragments attention during the weeks before contractor #1.

The "coding bet → research loop" analog for FirstBack: **voice answering → reviews → more calls.** Every booked job via voice potentially generates a Google review (growth.py already has `review_request` play), which drives organic search ranking, which drives more missed calls, which books more jobs. This is FirstBack's compound feedback loop. Focus there first.

**Concrete change (non-code):** Create a personal `focus.md` with one line: "North star until first $99 invoice: forwarding confirmation rate and calls-answered-by-AI rate." Don't open `crm/`, `providers/telnyx_provider.py`, or `outlook_mail.py` until that metric exists and is healthy.

---

## 5. Leave Money on the Table

**Lesson (synthesis doc):** Forgo metric wins for safety/brand/quality/UX → more long-term growth. "Best products all do this."

**ALREADY PARTIALLY IMPLEMENTED — reinforce it.**

FirstBack has made exactly this call twice correctly:
1. No platform toll-free number — owner-rejected because it undercuts the "local contractor" brand. Correct. The transcript's equivalent: Anthropic caps aggressive growth tactics that could damage safety reputation.
2. The `tone_risk` gate in `growth.py` scan() — win-back plays are held for review if the customer has said "rip off," "terrible," etc. This is leaving money on the table (the play has dollar value) in exactly the right way.

**Gaps where this principle hasn't been applied yet:**
- The growth engine's frequency cap (30-day cross-kind, 2/year) is the right mechanism, but it's only active in `scan()` (the auto-scheduler). The contractor's manual tray has no displayed warning like "⚠️ You've texted Maria twice this year — consider whether a 3rd touch is right." Add a `touch_count_12mo` field to the play dict in `plays()` so the tray can surface it.
- The email auto-answer (just built) has no equivalent of the tone-risk gate. A customer who emailed "I'm very disappointed" should not get an AI auto-reply that opens with the booking flow. Add: check the email subject/body for `_TONE_RISK_KEYWORDS` before drafting a reply; if flagged, draft but hold for contractor review.

**What does NOT transfer:** "Leave money on the table" at Anthropic sometimes means not launching a product for safety reasons (they had a chatbot before ChatGPT and chose not to launch). At FirstBack's stage, you cannot afford this interpretation — you need revenue. The correct FirstBack version is: "leave metric gaming on the table" (no dark patterns, no fake urgency, no reviews gating by sentiment), not "don't ship."

---

## 6. "Tell Us What To Do" — Strategy Bot

**Lesson (transcript, ~67k):** "Constantly watching metrics, market, roadmap → here's the pivot, here's where we're going to win." Amol thinks this becomes real "later this year" at Anthropic's scale.

**TRANSFER ASSESSMENT: Too early for FirstBack, but the skeleton is buildable now.**

The inputs for a FirstBack strategy bot would be: activation_state distribution across contractors, A2P approval lag times, forwarding confirmation rates, voice call → booking conversion, growth play reply rates, Twilio error logs. At 0–5 contractors, you can read all of this yourself in 10 minutes. The bot adds value at 20+ contractors when context overflows.

**Concrete change (deferred):** When you have 10+ contractors, add an `ops_review.py` that runs weekly and outputs: (1) which contractors are stuck in SETUP state and why, (2) which contractors have growth plays sitting in `held` for >7 days with no action, (3) voice call volume trends, (4) highest-ROI growth play type by trade. This is 3–4 hours of SQL + Claude formatting, and it becomes the weekly strategic read.

**What does NOT transfer:** The "strategy bot" at Anthropic is watching $19B ARR across multiple products and market signals. At FirstBack pre-revenue, the "strategy" is obvious: get contractor #1 live on voice. Don't build the strategy bot until you have enough contractors that the strategy is non-obvious.

---

## 7. Competitive Teardowns via Agent

**Lesson (synthesis doc):** Competitive teardowns of onboarding/pricing via agent + Chrome extension.

**DIRECT TAKE.** Competitors: Goodcall, Numa, Signpost, Ruby Receptionist, AnswerConnect, Jobber Answering. The specific questions FirstBack needs answered:
1. Do they promise the caller from the contractor's own number, or a shared platform number?
2. What is their day-0 promise (answer instantly? text back? book?) vs what actually works on day 1?
3. What does their pricing page say, and how does their flat-rate compare to FirstBack's $99–$399?
4. Is their setup wizard self-serve in 5 minutes, or does it require a sales call?

**Concrete change:** One-time agent run (Claude + browser tool) per competitor: screenshot the signup flow, grab the pricing page, note what identity the caller sees (contractor number vs platform number). Produces a 1-page teardown. This is a few hours of work and directly hardens FirstBack's positioning — "your number, your identity, from minute zero" is only a differentiator if you know competitors send from a generic number.

---

## 8. Activation Quality ("Forget Metrics for a Quarter")

**Lesson (synthesis doc):** Mercury spent a whole quarter on onboarding quality, ignoring metrics → biggest growth result of Amol's career. "Onboarding is the first experience — invest like the rest of the product."

**DIRECT TRANSFER. The wizard redesign (just done) is exactly this. The risk is stopping too soon.**

The quality bar for FirstBack's onboarding is specific and testable: can a 55-year-old painter with an iPhone 13 set up call forwarding in under 5 minutes without calling you? That's it. Every other onboarding metric is downstream of that.

The current wizard has the iPhone Live-Voicemail warning (correct), the tap-to-dial carrier codes (correct), the TCPA checkbox (correct). The unsolved quality problem is Step 3 (forwarding confirmation): the sentinel fix is deferred because it needs real-carrier testing. That deferral is correct, but the forwarding confirmation rate is the single most important quality signal you'll have in the first 30 days.

**Concrete metric to track:** `forwarding_confirmed / forwarding_attempted` ratio per carrier (AT&T, T-Mobile, Verizon, US Cellular). If this ratio is below 80%, nothing else in the product matters.

---

## 9. "Right Friction" — Personalization at Onboarding

**Lesson (synthesis doc):** Don't strip friction; add friction that makes the product feel "for them." Trade pills, who-are-they questions, MasterClass/Calm quiz model. The data compounds: activation → lifecycle → look-alike ads.

**ALREADY PARTIALLY IMPLEMENTED.** Trade pills and EIN fork are the right friction. One gap:

The trade data collected at signup is not yet feeding Vic's voice persona differentiation. A plumber's "emergency" caller expects urgency; a painter's caller expects a consultation tone. The voice system prompt in `ai.py` uses the business name and trade, but the prompt calibration should go further: HVAC callers get "I'll get you taken care of right away," painters get "I'll get you scheduled for an estimate."

**Concrete check:** Read `_system_prompt()` in `ai.py`. Confirm that `business['trade']` is injected into the prompt and that the tone instruction varies by trade (urgency language for HVAC/plumbing/roofing; consultation language for painting/landscaping). If not, add a `_trade_tone()` helper that returns a one-sentence tone instruction and inject it into the prompt.

The who-are-they data also compounds for growth: trade-specific play timing (painters' win-backs hit differently in October before interior season) is already in `_SEASONS` in `growth.py`. Good. The compounding is built; make sure trade is never None in the DB.

---

## 10. Engineer-as-Mini-PM (2-Week Rule) and Anti-PRD

**Lesson (transcript, ~50k):** `≤2 eng-weeks → engineer owns end-to-end, including cross-functional coordination. >2 weeks → PM accountable.` 60–80% no PRD; "go go go."

**DIRECT TRANSFER.** Jack is both the PM and the engineer. Every decision is ≤2 weeks by definition. The risk is the inverse: without a PM check, brand-risky or contractor-experience-damaging decisions ship without review.

**Concrete substitute for the PM layer:** Before shipping anything that touches the contractor or customer experience (message copy, voice prompt changes, growth play logic, onboarding wording), do a 5-minute Claude pass: "Read this change. Does it sound like a local contractor's business, or like a SaaS platform? Does it create any TCPA, FTC, or Google-review-policy risk? Does it match the FirstBack voice: plain, contractor-branded, not salesy?" This is the brand skill + controversy check in a single prompt. 2 minutes, one API call.

The `[DECIDED]` inline comments in the codebase (forwarding sentinel, toll-free rejection, etc.) are the "write down your thinking" equivalent that Amol describes as critical context for agents. Continue this practice — it directly feeds any future ops agent that needs to understand what was decided and why.

---

## 11. Cold Start — Import Context from Where Users Already Are

**Lesson (synthesis doc):** Import memory from ChatGPT — meet users where they are. The cold-start problem is that new users don't have context in the system yet.

**FirstBack's cold-start problem is different but analogous.** Contractors arrive with existing customers: phone contacts, Jobber exports, handwritten job logs. Right now, FirstBack's growth engine has zero data on day 1. The first growth play can only fire after a contractor has had at least one inbound call (to generate a lead record). If Dave has 200 past customers, you're leaving 200 win-back and review-request opportunities on the table on day 1.

**Concrete change:** Add a CSV import step at the end of onboarding (after forwarding confirmation). "Import your past customers — we'll remind you to ask for Google reviews and re-book them." Collect: name, phone, last job date, job type. Map to `leads` table with `status='booked'` and `last_appt_day` set. This instantly seeds the growth engine with real historical data and turns day-1 into the first morning brief with actual dollar amounts.

This is the FirstBack equivalent of "import memory from ChatGPT" — not importing AI context, but importing the contractor's business context so the AI can act on it immediately.

**CRM integrations (Jobber, Housecall Pro) are the automated version of this.** The CSV path gets the value unlocked in 2 hours instead of waiting for OAuth integrations.

---

## 12. Culture / Write Down Thinking So Agents Have Context

**Lesson (synthesis doc):** "Companies must write down thinking so agents have context. Notebook channels double as context for the agents."

**ALREADY DOING THIS.** The ONBOARDING_BLUEPRINT.md with inline `[DECIDED]`, `[owner decision Jun 29]`, and risk flags is exactly this. The decisions doc is the agent's institutional memory.

**Concrete reinforcement:** When any future ops agent (morning brief, strategy bot, competitive teardown runner) is built, pass `ONBOARDING_BLUEPRINT.md` or a distilled `decisions.md` as context. The agent then knows: no platform toll-free, sole-prop 10DLC path, voice-first architecture, why CRM integrations are gated. This prevents the agent from "helpfully" suggesting things that have already been decided and rejected.

---

## Summary: What Transfers, What Doesn't

| Lesson | Transfers? | Adjustment |
|---|---|---|
| CACHE growth automation | Partially | Build infra now; no A/B signal until 50+ contractors |
| Morning metric brief (for Jack) | Directly | Build `daily_ops_brief()` now — 2 hours |
| Contractor morning money brief | Directly | Highest-leverage UX unlock; build now |
| Big bets vs micro-optimizations | Partially | "Big bet" at this stage = voice working, not new features |
| Focus / do-few-things-deep | Directly | Freeze non-voice features until contractor #1 has a booked job |
| Leave money on the table | Directly | Already implemented correctly (no TFN, tone-risk gate) |
| Strategy bot | Too early | Build at 10+ contractors |
| Competitive teardowns | Directly | One-time agent run; do this week |
| Activation quality | Directly | Track forwarding confirmation rate as the north-star metric |
| Right friction / personalization | Partially | Trade-aware voice tone is the gap |
| Engineer-as-mini-PM | Directly | Brand-skill Claude check before any customer-facing change |
| Cold start import | Directly | CSV customer import at end of onboarding |
| Write down thinking | Already doing | Keep it; pass as agent context |
| 40-person team structure | Does not transfer | n/a |
| Log-linear chart culture | Aspirational | Get to revenue first |
| Cross-functional alignment as human stage | Reframes correctly | The contractor's one-tap approve IS the human-in-loop |

---

## Ordered Build List (by leverage, respecting hard realities)

1. **`daily_ops_brief()`** — Jack's morning text: contractor states, A2P status, stuck plays, LLM spend. 2 hours. Prevents context loss during the pre-revenue sprint.
2. **Forwarding confirmation rate instrumentation** — track `forwarding_attempted` + `forwarding_confirmed` per carrier in the DB. This is the quality metric the Mercury lesson points to.
3. **Brand-skill Claude check** — one function in `growth.py` that gates draft copy through a Claude call before surfacing to contractor. 2 hours. Prevents tone-deaf auto-play.
4. **Contractor morning money brief** — `morning_play_brief()` → daily SMS to contractor at 8am. Gates on `live_sms` (A2P must be active). 3–4 hours.
5. **Trade-aware voice tone** — check `_system_prompt()` in `ai.py` for trade-specific tone instruction. If absent, add `_trade_tone(trade)` helper. 1 hour.
6. **CSV customer import** — end-of-onboarding step to seed growth engine. 4–6 hours.
7. **Competitive teardown** — one-time agent run on Goodcall/Numa/Ruby. 2–3 hours. Informs positioning.
8. **`touch_count_12mo` in play dict** — surface in tray UI so contractor sees "you've texted Maria twice this year." 1 hour.
9. **Tone-risk gate for email auto-answer** — mirror the SMS `_tone_risk()` check in `google_mail.py`. 1 hour.
10. **`reply_within_48h` / `booking_within_7d` on `growth_touches`** — closes stage-4 CACHE loop. Build when you have 10+ plays to measure.

</details>

<details>
<summary><b>Audit 1 — Feasibility &amp; grounding (adversarial)</b></summary>

Now I have what I need. Here is the adversarial audit.

---

# Adversarial audit of the FirstBack growth plan

This audit is sequenced by severity: definite errors first, then misapplied lessons, then priority/framing issues, then validations.

---

## DEFINITE ERRORS — fix before treating this plan as a build spec

### GA-4: Wrong table name throughout

The draft says "Add `reply_within_48h` and `booking_within_7d` columns to the `growth_touches` table." There is no `growth_touches` table. The actual table is `growth_touch_log` (`db.py` line 698). `cancel_lead_growth_touches()` in `db.py` operates on `scheduled_messages`, not a `growth_touches` table. The migration target for GA-4 outcome columns is `growth_touch_log`. Any developer following this spec would build the migration against a non-existent table.

### GA-5: Email "held" state doesn't exist — implementation path is fabricated

`poll_and_answer()` in `google_mail.py` has two states: send or don't send. No "held draft" state exists for email. The draft says "set the draft status to `held`" as if this is a one-line state toggle, consistent with how growth plays handle the same condition. It is not. Growth play `held` state lives in `scheduled_messages.status`; there is no `scheduled_messages` row for auto-answered emails — they go directly from `fetch_unread()` to `send_email()`. Implementing email "held" requires a new table to persist pending email drafts and a UI to release them. That is medium effort, not small.

The correct implementation of the tone-risk gate here is simpler and already has a pattern: if tone-risk detected in subject+body, skip the auto-reply call and send an owner alert instead (same as SMS suppression: the lead is surfaced for human action, not auto-acted on). The implementation description in the draft should be replaced entirely.

### OA-4: Prereq chain cascade is missing — would leave the wizard broken

The draft proposes `_PREREQS["legal"] = ("identity",)` but does not update `_PREREQS["number"]`, which currently reads `("profile",)`. If "profile" is split into "identity" and "legal," "number" must prereq "legal" (the full legal profile — name + address + EIN fork — is required before provisioning a number that doubles as the A2P registration entity). Leaving `_PREREQS["number"] = ("profile",)` after the split references a step key that no longer exists in STEPS. The wizard would error. This cascade must be addressed in the concrete action.

---

## MISAPPLIED LESSONS — cut or substantially downgrade

### GA-3: Brand-skill check is busywork at 0 contractors — wrong priority

The CACHE framework automates experimentation at scale. Anthropic runs hundreds of copy variants per week with statistical volume. At FirstBack pre-revenue, the growth engine has generated zero real plays to real customers. Every message that will reach a real customer in the next 60 days will be manually reviewed before it ships. Building an LLM gate that screens these hypothetical messages is engineering work with zero return until you have 20+ contractors generating regular plays.

The draft ranks it priority 3 in growth and puts it at #6 in the ordered build list, above outcome tracking (GA-4) and below morning brief (GA-2). This is the inversion: GA-4 (outcome tracking) is the prerequisite for knowing whether any copy variant works at all. GA-3 is a meta-layer on top of that. Building the meta-layer first is the wrong order.

The `_tone_risk()` gate in `growth.py` already handles the live safety risk (negative-sentiment customers). GA-3's brand-check adds a quality signal on top of that. That quality signal has value at scale. At 0 contractors, manually reading your own play copy does the same job in 30 seconds.

Verdict: Remove from the ordered build list. Add a deferred note: "Build when plays are reaching customers at 20+ contractors and you can no longer manually review each one."

### OA-1: The SID-mismatch bug is unconfirmed — the draft asserts it as fact

The blueprint explicitly says: "the SID-mismatch bug is **plausibly real** but the fix needs real Twilio/carrier testing to avoid **false-confirming** forwarding." The draft says the sentinel "breaks when carrier forwarding mints a new call SID" as a definite statement of fact. The bug has not been reproduced on real hardware. This is not a dishonesty problem in the plan — it's a framing problem that matters because the fix's risk is false-positive confirmation (telling a contractor they're live when they're not), which is worse than the current behavior (no confirmation). The draft should preserve the blueprint's "plausibly real" language.

The concrete action (self-call fingerprint + AMD detection + `GET /api/forwarding/status` polling endpoint) is new infrastructure, not a patch. The polling endpoint does not exist anywhere in the codebase. Effort "M" is likely undersized: this is a new webhook path for AMD events, a new polling endpoint, new DB columns for sentinel state, and a template change to show the live polling card. "M-L" is more honest.

The priority-1 judgment is still correct. The framing needs adjustment.

---

## PRIORITY / FRAMING ISSUES

### PS-2: "Do this week" contradicts the ordered build list

The competitive teardown is ranked #16 in the ordered build list but the initiative text says "Do this week, before finalizing any public-facing positioning copy." This is a contradiction. If the competitive teardown is pre-requisite to positioning decisions, it should either be in the top 5 of the ordered list or explicitly marked as orthogonal to the build sequence. The inconsistency leaves it unclear whether it's urgent or not.

### GA-2: Timezone-from-zip is non-trivial and should not be a parenthetical

"Derive timezone from address zip when available" requires either a bundled zip-to-timezone lookup table (e.g., pytz + a zip-to-tz CSV) or an external API call. Neither exists in the codebase. The project has a no-external-dependency pattern where possible. This is not a parenthetical — it's a design decision. The correct call: default 8am ET (most US home-services contractors are Eastern or Central), no zip lookup. Add the zip-timezone path to a future polish list. The draft should say this explicitly instead of implying the zip lookup is a one-liner.

### GA-6: N+1 risk when adding touch_count_12mo to `_opp()`

`growth_touch_count_12mo()` makes one DB query per (biz, lead) call. Adding it inside `_opp()` means one extra query per lead per `plays()` call. For a contractor with 200 leads, that is 200 extra queries on every plays() call (which fires on page load, in the tray, in the morning brief). The existing frequency cap in `scan()` already has this N+1 pattern, but scan() runs once per cron tick. plays() runs on every request. The draft should note that `touch_count_12mo` should be batched with `growth_touch_index()` (a single query already in `plays()` that builds the `touched` dict) rather than queried per-lead inside `_opp()`.

---

## VALIDATIONS — grounded claims confirmed against actual code

These are correct and should be treated as build-ready without further verification:

**OA-2 (trade pills):** `app.py` line 339 confirms `"home services"` default. `auth.html` has no trade picker. Two-file change is accurate.

**OA-3 (sole-prop fork UI):** `setup.html` lines 80–86 confirm the EIN field appears unconditionally with the "sole proprietors can skip this" hint. The summary at line 228 confirms "EIN on file" text regardless of business_type. Valid friction issue.

**GA-1 (trade-aware tone):** `ai.py` `_system_prompt()` lines 88–90 confirm `business['trade']` is injected but the tone instruction is generic. The `_trade_tone()` add is a confirmed gap.

**GA-5 pattern validity:** `_TONE_RISK_KEYWORDS` and `_tone_risk()` confirmed in `growth.py` lines 97–113. The pattern exists and is the right model to mirror — the implementation path just needs correction per the error above.

**OA-8 route:** `contact_import.py` exists. `/api/contacts/import` confirmed in `app.py` line 2697. OA-8's link target is correct.

**OA-7 fs-meter:** `fs-meter` div confirmed in `setup.html` line 250. The `recommended_setup()` function in `connections.py` is the existing implementation. Template change is the correct scope.

**GA-6 db support:** `growth_touch_count_12mo()` confirmed in `db.py` line 2984. Already called in `scan()`. The `_opp()` dict exclusion is confirmed. Valid gap — subject to the N+1 note above.

**TO-1 ops brief:** `db.get_llm_spend_today` confirmed called in `ai.py` line 32. P2P owner-to-owner SMS path is valid (no A2P needed). `send_sms` path exists. Straightforward build.

**PS-1 (focus constraint):** Blueprint confirms deferred/gated list is real: `crm/`, `telnyx_provider.py`, `outlook_mail.py`, density/financing/membership play types all exist and are correctly gated. The focus constraint is accurately described.

---

## Summary: what to cut, fix, or adjust

| Initiative | Verdict | Action |
|---|---|---|
| GA-3 Brand-skill check | Cut from ordered build list | Defer to 20+ contractors. `_tone_risk()` already covers live safety. Manual review covers brand quality at this scale. |
| GA-4 outcome tracking | Fix table name | `growth_touch_log`, not `growth_touches`. Correct throughout. |
| GA-5 email tone-risk gate | Fix implementation path | Drop "held" state (doesn't exist). Correct action: skip auto-reply + owner alert when tone-risk detected. |
| OA-4 wizard split | Fix prereq cascade | Must update `_PREREQS["number"]` from `("profile",)` to `("legal",)` when profile is split. |
| OA-1 sentinel | Fix framing | Bug is "plausibly real" per blueprint, not confirmed. Effort is M-L not M. |
| PS-2 competitive teardown | Fix inconsistency | Either move to top 5 or explicitly mark orthogonal to build list. |
| GA-2 timezone | Fix scope | Drop zip-to-timezone. Default 8am ET. Note this explicitly. |
| GA-6 touch_count_12mo | Add note | Batch with `growth_touch_index()`, don't query inside `_opp()`. |

</details>

<details>
<summary><b>Audit 2 — Strategy &amp; completeness (adversarial)</b></summary>

Now I have enough to deliver a thorough adversarial audit. Here it is:

---

ADVERSARIAL AUDIT — FirstBack / Anthropic Growth Podcast Plan

---

## THE SINGLE BIGGEST STRATEGIC GAP: Voice deploy is not in the build list

The draft plan's ordered build list starts with OA-1 (sentinel fix). But OA-1 is explicitly gated on `VOICE_PUBLIC_URL` — the plan says so. `VOICE_PUBLIC_URL` is the literal unblock condition for everything. Yet "deploy voice" does not appear anywhere in the 17-item ordered build list.

The blueprint's own "Immediate action order" puts it at #3: "Deploy the voice leg (`voice_service.py` sidecar + `VOICE_PUBLIC_URL` + a real `CONVERSATIONRELAY_VOICE`)." The draft plan demotes this to a PS-1 non-code note titled "Voice works for first 3 contractors before anything else unfreezes" and calls it "zero code, one decision." That is wrong. Deploying a server sidecar with a real public URL, picking a voice, and enabling ConversationRelay TwiML in production is a concrete engineering action, not a mindset choice.

The true item #0, above everything else in the build list: deploy `VOICE_PUBLIC_URL` + sidecar + ConversationRelay in production. Every other item in the list is blocked on it or meaningless without it.

---

## THE SECOND BIGGEST GAP: No acquisition path

The plan is entirely product-side. There is zero plan for how contractor #1 arrives. Every item in the 17-item build list is internal. The product can be perfect and no one gets live if there is no outreach.

The transcript's most immediately applicable lesson to this gap is Amol's cold email story — the opening of the podcast. He identified a specific hypothesis ("Anthropic badly needs a growth team"), found the right person (Mike Krieger via personal email, not LinkedIn), kept the message short and direct, and followed up. The plan maps this to PS-2 (competitive teardown) but does not map it to the actual contractor acquisition problem.

The correct translation: identify 20 painters, HVAC contractors, or plumbers in a specific local market. Find them via contractor Facebook groups (Painting Contractors Association groups, HARDI/ACCA HVAC groups, local chamber directories). Write one short message per trade: "I saw you missed a call and the caller didn't leave a voicemail. There's a tool that would have answered it and booked the estimate. Want to see it?" Cold outreach to 20 real contractors in week 1 is higher leverage than any item in OA-2 through OA-8.

The podcast lesson "freedom through constraints" is explicitly about being smallest and least-funded — and finding the narrow path. For FirstBack right now, the constraint is: voice is not in production yet and contractor #1 doesn't exist. The narrow path is: get voice deployed, pick up the phone (or keyboard), and find one real painter willing to be the first.

This section should exist in the plan and should rank above the wizard-split items.

---

## PRIORITIZATION ERROR: GA-2 in Top 3 is wrong

GA-2 (morning money brief) is listed as Top 3 highest-leverage initiative. The plan itself acknowledges it is gated on `live_sms` — which requires A2P 10DLC approval (10-15 business days). At pre-revenue with 0 contractors, the morning brief requires:

- Voice deployed
- Contractor #1 goes live
- A2P clears (~2 weeks later)
- `plays()` generates at least 1 opportunity from real call data

None of these conditions currently exist. Calling GA-2 "Top 3 highest-leverage" while it is gated behind 4 sequential dependencies — including a regulatory wait — is a misprioritization. GA-2 is the right long-term automation and should stay in the build list at position 10. It should not be in Top 3.

The actual Top 3 highest-leverage initiatives right now, in order:

1. Deploy `VOICE_PUBLIC_URL` — unblocks everything
2. Cold outreach to 20+ contractors in a specific local market — produces contractor #1
3. OA-1 (sentinel fix) — ensures contractor #1's activation is confirmed, not silent

---

## OVER-INDEXED: 14 onboarding items before first contractor

The plan has OA-1 through OA-8 plus GA-1 through GA-6, totaling 14 optimization items for a product with 0 users. The Mercury lesson that the plan invokes is about fixing onboarding quality for a product with paying users generating drop-off data. Amol says "we spent a whole quarter fixing onboarding." Mercury was not pre-revenue when they did this — they had enough signups to measure "onboarding-start to completion."

The correct translation of the Mercury lesson for pre-revenue FirstBack is: make the first contractor's experience actually work end-to-end, once. That is OA-1 only. OA-4 (split wizard Step 1 into two screens), OA-5 (split forwarding step into three sub-screens), OA-6 (AI preview), OA-7 (on-ramp), and OA-8 (customer import on Done screen) are all premature optimization. There is no conversion metric to improve when there are no contractors in the funnel.

OA-2 (trade pills at signup) and OA-3 (sole-prop fork UI cleanup) are genuinely worthwhile before contractor #1 because they fix data quality and trust signals that affect every downstream system (AI tone, growth plays, lifecycle). Those stay. OA-4 through OA-8 should be demoted to a "after first 3 contractors" backlog explicitly, with a note: "revisit if a contractor reports confusion at this step."

---

## UNDER-USED LESSON: The controversial test framework

The transcript has a specific two-bucket framework for controversial decisions. It is directly applicable to ongoing FirstBack product decisions and is entirely absent from the plan.

Bucket 1 (red line, never ship regardless of return): Platform TFN (already correctly rejected), ISV shared campaign (rejected), charging before AI-answered-call confirmed, auto-enrolling contractors in growth broadcasts without explicit opt-in.

Bucket 2 (yikes, but not a red line — require high return): Charging full price before contractor has 5 AI-answered calls with bookings, showing estimated job values as exact in growth plays without "(estimated)" label.

The plan has a "Not Applicable / Rejected" table but does not give Jack a repeatable decision filter. The "controversial test framework" should be added as a named decision tool in the PS or TO section, with FirstBack-specific examples. Concretely: any decision where the answer is not obvious gets run through "is this bucket 1 or bucket 2?" before shipping.

---

## UNDER-USED LESSON: "Leave money on the table" applied to billing gate design

The plan invokes this lesson for GA-5 (tone-risk gate for email) and OA-6 (AI preview). The most important application of this principle is not in the plan: do not start billing until contractor has a confirmed, AI-answered call with a real booking attempt.

The transcript: "We are very comfortable forgoing metric wins to prioritize safety, brand, quality, UX." For a pre-revenue product targeting trust-sensitive local contractors, the analogous move is: the billing clock starts when voice is confirmed live and the contractor has seen the AI work on a real call, not at signup. This protects against the most likely churn scenario — contractor signs up, gets confused during wizard, voice is never confirmed, they are charged $99, they dispute it, churn and tell their contractor network. One such incident before positive word-of-mouth exists is catastrophic.

This should be a named decision in the plan: "Billing activation gate." Not a code item — a policy item. Add it to the decisions.md / [DECIDED] pattern.

---

## UNDER-USED LESSON: Capability overhead and the day-1 churn mechanism

Amol describes "capability overhead" — the gap between what the model can do and what users know to expect from it. The plan routes this into OA-6 (AI preview in wizard). That is the right mechanism, but the plan undersizes the risk.

The most likely day-1 churn mechanism for FirstBack is not a bad onboarding experience. It is: contractor sets up forwarding, AI answers first real call, says something that does not match what the contractor expected (wrong tone, doesn't offer the right service, books a slot the contractor can't fill), contractor turns off forwarding that night. The AI preview in the wizard (OA-6) is good but it is a passive card in a details element. The more leverage move is: after the first AI-answered call, automatically send the contractor the call transcript and a one-question text: "How did that sound? Reply 1 = perfect, 2 = needs tweaking." This closes the capability overhead loop at the highest-risk moment.

This is not in the plan. It should be OA-9 or a GA item. The transcript lesson maps to it directly. Effort is S (transcript is already logged; the one-question SMS is a simple trigger).

---

## UNDER-USED LESSON: "70% fire-fighting success disasters"

Amol says 70% of his time is managing problems caused by growth — things going well enough to break other things. The plan does not address what happens when voice works too well for the first contractor. "Success disaster" scenarios to prepare for pre-contractor-#1:

- Contractor gets too many AI-answered calls and their calendar fills; they don't have slots; AI keeps booking to "the next available window" which doesn't exist
- AI answers a call the contractor specifically wanted to take personally (e.g., a regular they know by voice)
- A caller leaves a deeply personal message (grief, health crisis) that the AI handles generically

None of these scenarios are addressed in the plan. For each: what is the contractor's path to override the AI? The plan correctly notes `training.html` exists but the "success disaster" protocol is not named or outlined.

Recommended add (brief, not a full section): "Contractor override protocol" — a named feature allowing contractor to set call categories as "alert me first" (send a push/text before AI engages for that caller). This is the product analog of Anthropic's controversial test bucket 1 (things that should never be automated regardless of efficiency).

---

## STRUCTURAL CRITIQUE: The plan violates the focus principle it names

PS-1 says "treat CRM/, telnyx_provider.py, outlook_mail.py, density/financing/membership play types as frozen." The plan then immediately lists 17 items in the ordered build list, including GA-4 (play outcome tracking — "value compounds only after 20+ plays are sent"), TO-3 (weekly ops review — explicitly deferred to 10+ contractors), and GA-6 (touch_count_12mo visibility in the tray, which requires `growth_touches` to be populated). These are items for a product with active users. The build list claims to be sequenced but contains at least 8 items that are not actionable until after contractor #1 is paying.

The plan would be stronger with an explicit split:

**Before contractor #1 is paying:** Deploy voice, fix sentinel, trade pills at signup, cold outreach to 20 contractors, daily ops brief for Jack, trade-aware voice tone, brand-skill check, tone-risk gate for email, first-call transcript nudge (the missing OA-9 above).

**After contractor #1 is paying:** Everything else.

---

## WHAT TO ADD

1. **Action #0: Deploy VOICE_PUBLIC_URL** — Concrete steps: provision a server with a real public URL (ngrok for dev, a real VPS for prod), wire voice_service.py as a sidecar, set CONVERSATIONRELAY_VOICE to a real Twilio voice, enable ConversationRelay TwiML in twilio_voice_inbound(). This is the prerequisite for every other item.

2. **Acquisition section** — Translate the cold email mastery lesson: 20 contractors, specific local market, one message per trade, direct hypothesis. Target painter and HVAC Facebook groups, Nextdoor Pros, supply house bulletin boards (Sherwin-Williams reps know every painter in a territory). This is the highest-leverage human action while code is being built.

3. **Billing gate policy** — Do not start billing clock until contractor has a confirmed AI-answered call with at least one booking attempt. Named decision in decisions.md / [DECIDED]. Not a code item.

4. **OA-9: First-call transcript nudge** — After the first AI-answered call, automatically send the contractor the call transcript with a one-question check-in. Effort S; highest-leverage day-1 retention action because it closes the capability overhead loop at the riskiest moment.

5. **Controversial test framework** — Add as a named decision tool with FirstBack-specific examples. Replaces the implicit "this feels wrong" filter with a structured one that survives context loss.

---

## WHAT TO DE-EMPHASIZE

OA-4 through OA-8 (wizard splits, AI preview, on-ramp, customer import): Move to "after first 3 contractors" explicitly. Not because they're wrong, but because there are no conversions to optimize yet and the Mercury lesson requires real drop-off data to act on.

GA-2 in Top 3: Demote to ordered list position 10. Correct gating (live_sms) makes it a ~3-week item at minimum, not a current top initiative.

GA-4 and GA-6: Move to "after 20+ plays are sent." Correct design, wrong timing.

TO-3 (weekly ops review): Already correctly deferred. Remove it from the build list entirely and note it as "add to roadmap at 10 contractors."

PS-2 (competitive teardown): Useful but should be done in the background while waiting for voice deploy, not as a priority task. Re-label it "do while waiting for VOICE_PUBLIC_URL."

---

## CORRECTED TOP 3

1. **Deploy VOICE_PUBLIC_URL** — Not in the plan. Must be #0. Every other item is gated on it.

2. **Cold outreach to 20+ contractors in a specific local trade + market** — The podcast's cold email lesson, correctly applied. Nothing else produces contractor #1.

3. **OA-1 (Sentinel fix) + OA-2 (Trade pills) as a same-sprint pair** — Sentinel fix is the blocking quality issue for activation; trade pills is the S-effort unlock for all downstream personalization. Both are ready to ship once voice is deployed.

GA-2 (morning money brief) is correctly designed but removed from Top 3. It is a day-30+ item.

---

## SUMMARY OF ADDITIONS AND MOVES

Add: Voice deploy as ordered-list #0. Contractor acquisition section. Billing gate policy. OA-9 (first-call transcript nudge). Controversial test framework as a named decision tool.

Elevate to Top 3: Voice deploy (#0, currently missing). Contractor acquisition (#2, currently missing). Keep OA-1 at #3.

De-emphasize: OA-4 through OA-8 (move to post-first-3-contractors backlog). GA-2 out of Top 3 (stays in list at position 10). GA-4, GA-6, TO-3 (all require live usage data; move to post-revenue backlog).

The plan's strongest sections are PS-1 (focus meta-constraint), OA-1 (sentinel fix), OA-2 (trade pills), and GA-3 (brand-skill check). The plan's weakest assumptions are that the ordered build list constitutes a ready-to-execute roadmap and that GA-2 is a near-term priority. The deepest strategic miss is the absence of any path to acquiring contractor #1 — which is the only thing that actually matters before any optimization work.

</details>
