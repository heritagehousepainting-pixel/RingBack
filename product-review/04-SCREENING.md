# Product Review 04 — Call Screening as Differentiator
**Auditor lane:** Call screening as product / competitive wedge
**Codebase reviewed:** `triage.py`, `reputation.py`, `ai.py` (`classify_intent`), `app.py` (screening hot-path, rescue route, flag-spam routes), `db.py` (`is_known_caller`, `global_spam_count`, `record_screening_rescue`, `promote_screening`, `screening_stats`), `config.py` (presets, graduation constants), `templates/dashboard.html`, `templates/settings.html`, `templates/simulator.html`, `templates/product.html`, `templates/onboarding.html`, `test_screening_graduation.py`.
**Market research:** RoboKiller, Hiya, Truecaller, Nomorobo, iPhone "Silence Unknown Callers", iOS 26 "Ask Reason for Calling", GoHighLevel missed-call text-back, Weave, Jobber.
**Date:** 2026-06-19

---

## What FirstBack's screening actually does

Six-tier decision tree evaluated cheapest-first on every missed call:

1. **Identity (free):** STOP opt-out → silent. Known non-prospect tag (personal / vendor / blocked) → screen out.
2. **Auto-derived trusted set (free):** anyone with a booked estimate or any directory entry is "known" — the bot stays out, owner handles it. Zero contact import. Built from booking history (`db.is_known_caller`).
3. **Free spam signals:** STIR/SHAKEN attestation (letter A/B/C from `StirVerstat`), neighbor-spoof detection (matching area code + 3-digit prefix), repeat-call-never-replied behavior.
4. **Paid reputation (gated, off by default):** Twilio Lookup v2 + Nomorobo score, or Hiya — cached per number, shared across all tenants, fail-open.
5. **Crowdsource ledger (free, always on):** cross-tenant spam flag count — one business marks a number spam, it pre-screens that number for every other tenant. Privacy-safe (count only).
6. **AI content screen (Tier 3, gated):** `classify_intent` runs on the caller's first text reply, labels it prospect / sales / survey / wrong_number / spam, fails open to "prospect" on any error.

**Precision-first scoring:** no single weak signal reaches `HARD` (default 80). Score ≥ HARD = hard-blocked; MID (45) ≤ score < HARD = still texted but flagged `review`; below MID = clean prospect. Single-signal examples: neighbor spoof alone = 25 (below MID), attestation C alone = 30 (below MID), burst ≥ 3 alone = 35 (below HARD). Reaching HARD requires corroboration.

**Rollout safety:** `off → monitor → enforce` modes. Default is `monitor` — computes verdicts, logs them, but texts everyone. Automatic graduation: after 7 days + ≥10 would-block verdicts in monitor, system promotes to enforce and alerts the owner. False-positive rescue ("This was real") resets the graduation clock so the owner can't be locked into enforce after a bad signal cluster.

**Sensitivity presets:** `conservative (90/55)` / `balanced (80/45)` / `aggressive (65/35)` — per-tenant threshold override.

---

## Competitive landscape

### What contractors already have before FirstBack

| Tool | What it does | Gap it leaves for FirstBack |
|------|-------------|----------------------------|
| **iPhone "Silence Unknown Callers"** | Silences any number not in Contacts, Siri Suggestions, or recent calls. Binary: ring or silent. | Hard-blocks ANY new prospect. Dave the contractor can't tell the difference between a new homeowner and a robocaller — both are "unknown." |
| **iOS 26 "Ask Reason for Calling"** | Live call screening: AI asks caller to state purpose before the phone rings through. | For personal phones only, not a business line. Requires the owner to be available to answer. Doesn't text back. |
| **Carrier spam labels (T-Mobile, AT&T, Verizon)** | Labels known robocallers "Spam Likely" or "Scam Likely." Often false-positives on legitimate VoIP/local-number business callers. | Passive label only — doesn't act, doesn't text back. Labels stick to phone's screen UI, not the CRM. |
| **RoboKiller ($5/mo)** | Audio fingerprint ML, answer bots, real-time screening. Consumer personal-phone product. | Not integrated with a business number. Can't distinguish "a homeowner calling from a VoIP line" from a robocaller. No text-back, no lead capture. |
| **Hiya (free / B2B API)** | Curated carrier-grade reputation database. Consumer app + B2B API. | Consumer app doesn't connect to a contractor's business number. B2B API requires developer integration and costs extra. No text-back loop. |
| **Truecaller** | World's largest caller ID database; community-flagged spam. | No US business-line product. Database is community-driven (can mislabel small local businesses). |
| **GoHighLevel / generic text-back** | Sends the text-back to every missed caller, no filtering. | Texts robocallers, burns SMS reputation, risks carrier flagging the business number as spam. No crowd intelligence, no known-caller pass-through. |
| **Weave / Jobber** | Practice/field management. Missed call text-back in Weave is a known-customer notification feature, not spam-filtered. | Neither product does tiered spam scoring or crowdsource ledger. |

**Key market gap:** every consumer spam-blocking tool is personal-phone-first. Every generic text-back tool fires at everyone. Nobody in the contractor CRM space has built a precision-first, fail-open spam screen that also auto-derives the known-caller allowlist from booking history.

---

## Findings

---

### F1 — The "auto-derived trusted set" is the most defensible idea in this feature, but it's invisible to Dave
**Impact: H | Effort: S (copy + UX only)**

`db.is_known_caller` builds the known-caller allowlist from booked estimates and directory entries, requiring zero contact import. This is structurally superior to Apple's approach (which needs you to have the number in Contacts) and to every other text-back product (which doesn't distinguish returning customers at all).

The problem: Dave doesn't know this is happening. The marketing copy says "Skips contacts you know" but doesn't explain the mechanism. Dave would assume he needs to import a contact list — the exact friction point this feature removes. The settings page says "anyone you've booked or saved" only in the Enforce description text, not as a headline or onboarding callout.

**Why it matters:** This is a retention-stickiness mechanism (the more you book through FirstBack, the smarter the screen gets) that's not being leveraged. It's also the strongest "we are not iPhone Silence Unknown Callers" counter-argument.

**Rec:** Add one sentence to onboarding and the dashboard screening card: "FirstBack builds your known-caller list automatically from your bookings — no contact import ever needed." Make it visible, not buried.

---

### F2 — Monitor-to-Enforce graduation is correct but the "7 days / 10 verdicts" bar is invisibly high for slow businesses
**Impact: H | Effort: M**

Graduation is precision-engineered: 7 days of observation + ≥10 would-block verdicts before auto-promotion to enforce. The false-positive rescue resets the clock, preventing premature lock-in. This is the right architecture for a paranoid contractor.

The problem: a contractor who gets 8 calls a week (which is many) might only generate 2–3 spam signals in 7 days, never graduating. They stay in monitor mode forever and never see actual blocking — which means the feature that justifies "smart screening" is never experienced. The Spam Shield Learning card says "Day N of 7" but gives no indication of where they are on the verdicts axis.

**Why it matters:** Users who never reach enforce mode see the feature as "a log of things that didn't happen." This is not the Dave test — Dave can't articulate why the feature is better than his iPhone's built-in silencing if he never sees it block anything.

**Rec:** Show progress on both axes in the dashboard card: "Day 3 of 7 · 4 of 10 spam signals seen." If a business is 7+ days in but under 10 verdicts, surface a nudge: "Ready to enforce? You can turn it on manually even before the threshold." Also consider lowering the auto-graduation verdict minimum to 5 for very-low-volume businesses (≤5 missed calls/week detected in window).

---

### F3 — The crowdsource ledger is a genuine network-effect moat, but it's disabled in practice until you have real tenant density
**Impact: H (long-term) | Effort: S (assessment), M (if you build on it)**

`global_spam_count` shares spam flags across all tenants — when one business marks a number spam, it pre-screens that number for every other business on the platform. `SCREEN_CROWD_MIN=2` means a number needs to be flagged by at least 2 distinct tenants to count. This is structurally similar to how Hiya and Truecaller operate, but for the contractor vertical.

The problem: with a small tenant base (early-stage SaaS), this signal is nearly silent. The first 50 customers will generate almost no cross-tenant flags — every number will look "clean" from the crowdsource layer. The feature exists, but the value is deferred until you have meaningful density (likely 100+ active tenants across geography).

**Why it matters from a competitive angle:** This is the right long-term play, but it cannot be used as a current selling point without being misleading. It's also the single feature that most resembles the Hiya / Truecaller model — and those have hundreds of millions of data points vs. FirstBack's early base.

**Rec:** Do not market the crowd signal as a current feature. Internally, set `SCREEN_CROWD_MIN=1` for MVP until you have enough tenants to require corroboration (this halves the needed density). Plan a "regional spam cluster" visualization for the Command Center when density grows.

---

### F4 — The "This was real" rescue is airtight in code but the UX does not communicate that false positives are tracked and acknowledged
**Impact: M | Effort: S**

`record_screening_rescue` increments `screening_false_positives`, upserts the caller as a customer contact with `source='owner-rescue'`, and resets the graduation clock. The dashboard shows the false positive count in the Spam Shield active card ("0 false positives"). This is technically sound.

The problem: a contractor who sees "Spam Shield is active — 1 false positive" may read this as "the system made an error and is going to do it again" rather than "the system learned from that." There's no feedback loop showing that the rescued caller is now always handled by the owner (not re-screened). The rescue UX is a single "This was real" button with no confirmation message about what happened next.

**Why it matters:** False-positive fear is the primary reason contractors would not turn on Enforce mode. The false-positive counter actually builds trust if framed correctly — but currently it's framed as a defect counter, not a learning counter.

**Rec:** Rename the counter "1 caller corrected" or "1 caller rescued — saved as customer." After a rescue action, show an inline toast: "Saved as a customer — they'll always reach you directly from now on." This reframes the safety net as a teaching mechanism, not an error log.

---

### F5 — Paid reputation (Tier 2) is off by default and requires env-var configuration that most contractors will never touch
**Impact: M | Effort: M**

`reputation.py` supports Twilio Lookup + Nomorobo or Hiya as a paid reputation layer. It's architecturally clean — cached, fail-open, cross-tenant. But it's entirely gated behind `FIRSTBACK_REPUTATION_PROVIDER` + API keys that the contractor never sets. The Settings UI shows a disabled "Optional add-on" button.

The problem: this means FirstBack's free spam tier relies on STIR/SHAKEN + neighbor-spoof + behavior + crowdsource. These are good signals for obvious robocallers (non-fixed VoIP, clear spoofing patterns), but they miss the most prevalent form of contractor spam: legitimate-looking local numbers used by lead-gen vendors (roof lead sellers, solar salespeople, warranty scammers). These have A-level attestation, real local numbers, never trigger neighbor-spoof, and don't yet appear in a crowdsource ledger. They will ring through and get the text-back.

**Why it matters:** Dave's actual spam problem is not robocall blitzes — it's the lead-gen vendor who calls 30 times a week from a real local cell number. The free tier alone cannot catch this category.

**Rec:** Bundle Twilio Nomorobo into a paid FirstBack tier (the per-lookup cost is fractions of a cent, easily absorbed in a $99/mo product). Make it the default for paying customers, not an opt-in add-on. Frame it in Settings as "Professional screening (included)" rather than "Optional add-on." This removes a dangerous gap and upgrades the marketing claim from "screens robocallers" to "screens robocallers AND lead-gen vendors."

---

### F6 — The AI content screen (Tier 3) is correctly scoped but "fails open to prospect" under no-key conditions that will be the norm in production
**Impact: M | Effort: S (config), M (if you want it reliable)**

`classify_intent` is called on a caller's first text reply to classify their intent (prospect / sales / survey / wrong_number / spam). It's fail-open by design — no LLM key means it returns `{"label": "prospect", "is_prospect": True}` always. This prevents silencing real callers when the AI is unavailable.

The problem: `SCREEN_AI_CONTENT=1` requires a live `MINIMAX_API_KEY` or `FIRSTBACK_PROVIDER=claude` + `ANTHROPIC_API_KEY`. In the current deployment, neither is reliably configured for all tenants. The practical result: Tier 3 is off for nearly every user. More importantly, the AI screen fires *after* the caller has already received the text-back and replied — it's a mid-conversation bail-out, not a pre-screening mechanism. It catches vendor pitches that made it through Tier 1–2, but it cannot prevent wasted SMS credits on the first outbound text.

**Why it matters:** This is fine for precision (you never lose a real homeowner), but it means a contractor in "enforce" mode will still text back a "Hi I'm calling about your business insurance" vendor — they just won't get a second text. The marketing claim "screens spam before texting back" is only true for Tiers 1–4.

**Rec:** This is correctly engineered for what it is (mid-conversation filter). The copy should not imply it prevents the first text — only that it stops the conversation from continuing. Ensure the AI key is bundled into the production deploy config rather than requiring per-tenant setup.

---

### F7 — Screening is genuinely differentiating vs. generic text-back tools, but is not yet a standalone reason to choose FirstBack over a contractor-specific CRM (Jobber + text-back plugin)
**Impact: H | Effort: L (strategic)**

GoHighLevel and Weave text back every caller. iPhone "Silence Unknown Callers" is the only free alternative but nukes all new prospects. RoboKiller/Hiya are personal-phone tools with no text-back integration. In the missed-call text-back SaaS category, FirstBack's precision-first screen is a real, demonstrable advantage.

The gap: a contractor already using Jobber + a simple text-back automation (easy to set up via Twilio or a GHL workflow) would not switch for screening alone, because Jobber's "known customer" database is already more complete than FirstBack's auto-derived set (Jobber has full job history, client addresses, notes). The screening wedge only sharpens once the auto-derived allowlist is demonstrably better than what they'd configure manually.

**Why it matters:** Screening is a "never lose a job to spam + never embarrass yourself with known contacts" message. It's compelling for contractors who have not yet adopted a field management CRM. But it's a weak wedge for a Jobber user because they already have the contact history piece.

**Rec:** Build a "Screening Report" — monthly email/SMS to the owner showing "You blocked N robocalls, rescued M real callers, saved X in wasted texts." Make the value visible in dollar terms ($0.01/text × N = $X saved; 1 recovered homeowner lead = $Y). This makes the feature's ROI legible, which is the only way screening becomes a reason to choose and stay.

---

## What's missing to make screening a reason to choose FirstBack

1. **Phone-number health score (carrier flagging protection):** GoHighLevel's policy doc mentions that missed-call texts count toward daily message limits. FirstBack already protects business numbers by not texting robocallers (reducing spam complaint rates). This should be marketed explicitly: "We protect your business number from carrier spam flags — generic text-back tools don't." Add a stat showing how many spam complaint sources were filtered.

2. **Sensitivity presets as a settings UX win:** The three presets (conservative / balanced / aggressive) exist in config and the Settings UI, but they're described vaguely ("fewer blocks, more certain"). Make them concrete: "Conservative — only blocks numbers that have been flagged by 3+ other businesses or have a confirmed robocall fingerprint. Aggressive — blocks any VoIP caller who can't prove caller ID." Dave understands outcomes, not tuning parameters.

3. **Screening as a lead-gen angle:** The framing "we make sure you never miss a real job AND never get spam" is underused. The onboarding page has a single line ("Screens spam & robocalls"). A 30-second video or animated simulator showing a robocall being silenced + a homeowner getting the instant text-back would make this visceral. The simulator exists (`/simulator`) but the spam-call button leads to a text screen, not a visual "blocked" moment.

4. **Crowd-signal growth visualization (deferred):** When tenant density reaches 100+, a "Spam activity map" (anonymized, regional spam cluster view) would be a powerful retention feature — shows Dave that being on FirstBack protects him in a way being alone on GoHighLevel never could.

---

## Verdict summary

**Competitive strength: Solid foundation, not yet a killer app.**

FirstBack's screening architecture is genuinely precision-engineered — fail-open, precision-first, auto-derived known-caller set, crowd ledger, false-positive rescue, safe rollout graduation. This is better than anything in the generic text-back SaaS category. The problem is threefold: (1) the auto-derived allowlist benefit is invisible to the contractor, (2) the feature is effectively in monitor mode for most users and many will never see it block anything, (3) the paid reputation tier that would catch lead-gen vendor spam (the actual daily pain) is opt-in infrastructure that most tenants will never configure.

Screening is a real moat seed, not a minor add-on. But it doesn't close deals on its own yet — it needs (a) the auto-derived allowlist to be the headline, not a footnote, (b) the value to be legible in dollars via a Screening Report, and (c) paid reputation bundled into the paid tier so the free signals are not the ceiling.

---

## Top findings at a glance

| # | Finding | Impact | Effort | One line |
|---|---------|--------|--------|----------|
| F1 | Auto-derived allowlist is invisible | H | S | Best feature in the product is buried in the settings description |
| F2 | Graduation bar too high for low-volume businesses | H | M | Many contractors will stay in monitor forever and never see blocking |
| F5 | Paid reputation off by default, lead-gen spam gets through free | M | M | The spam contractors actually hate is not caught by the free tier alone |
| F4 | False-positive counter framed as error log, not learning signal | M | S | "1 false positive" reads as defect, not "1 caller now saved as customer" |
| F7 | No Screening Report = value invisible in dollar terms | H | L | Contractor never sees ROI; screening can't justify itself to Dave |
