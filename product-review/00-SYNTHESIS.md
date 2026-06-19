# FirstBack Product Review — SYNTHESIS & "Best-Version" Roadmap
**Date:** 2026-06-19 · 12-lane parallel product audit (read-only) · reports: `product-review/01..12-*.md`
**Lens:** is this the best version of itself? (weak points, additions, competitiveness) — not security/correctness (already audited).

## The one theme that ran through all 12 lanes
**The engineering is strong; the VALUE IS INVISIBLE and the human layer is thin.** Almost every lane independently said the same thing: the architecture is production-grade (screening, booking integrity, growth engine, compliance, idempotency) — but the product doesn't *show* its value, *guide* the non-technical owner, or *speak* like a human at the moments that decide win/retain. FirstBack is well-built and under-sold to its own user. The gap to "best version" is mostly days of human-layer polish + visibility, not re-architecture.

---

## TIER 0 — Fix before real customers (cheap bugs + honesty; ~1–2 days total)
These are live RIGHT NOW on a product about to take real callers/signups. All S-effort, several are honesty issues the founder bar cares about most.
- **[01] Voice falsely says "we just sent you a text"** during the 1–3 day A2P wait when `send_sms` returned `blocked` and nothing went out. A live false promise to every caller in the window.
- **[10] Auth page shows a 5-star block attributed to "— FirstBack"** (a self-review with a star widget = dark pattern). Remove.
- **[10] solutions.html states "live AI voice"** with no "coming soon" hedge — contradicts every other page + the honesty rule.
- **[01] EIN field is hard-`required` for everyone**, but every signup is tagged `sole_prop` (which the backend exempts). Most painters don't have their EIN memorized → hard block at signup. Highest single drop-off.
- **[01/05] Landing/hero phone input submits via GET; signup never reads it** → `alert_sms` blank for every new user → day-one owner lead-alerts never fire.
- **[09] "Est. revenue" tile renders `$null/job`** when the owner hasn't set an avg job value (live JS bug).
- **[10] "See it live"/demo CTA points at a `@login_required` wall**; a working public `/demo` exists, linked nowhere. Swap the href.
- **[01] No notification when A2P approves and Dave goes live** — he set-and-forgot and never learns it's working / his first leads were texted. One `send_alert` call.
- **[07] `alert_on_roi_milestone` toggle** exists in the schema but is missing from the Settings UI + the `update_alert_prefs` whitelist (unreachable).

## TIER 1 — High-impact product gaps (make value VISIBLE + the AI sharp)
- **[03] AI conversation = 100% prompt-quality gap** (architecture is great): rewrite the system prompt as a persona, add an **urgency fast-path** (a burst-pipe caller currently gets "what part of town are you in?"), a **price-objection pivot** (it stalls on "how much?"), raise the 300-token cap (~450), add **Spanish**. ~1 day, the biggest book-rate lever in the product.
- **[02] First text-back waits on a cold LLM call** (speed = reply rate): hardcode a fast branded opener, reserve the LLM for turn 2+.
- **[02] Known/returning caller silently gets nothing in enforce mode AND no owner alert** — a past customer calls back, hears silence. Add a "known caller, no auto-text" owner ping.
- **[05] Mobile is the real gap** — the daily driver (lead triage on a phone, on a job site) is a desktop data table; nav collapses to unlabeled icons; tap targets <44px on high-stakes actions; no `tel:` links. Card layout ≤640px.
- **[07] Set-and-forget gaps:** owner quiet hours (a new lead at 11pm texts Dave at 11pm), a stall-nudge daily cap (5 stalled leads = 5 texts in one pass), and an "all clear — nothing needs you" reassurance signal.
- **[09/08] Monthly ROI recap timed to renewal** ("Your FirstBack month: 14 missed calls, 4 booked, ~$12,800") — the single highest-leverage anti-churn touchpoint, currently absent. Add loss-framing ("without a text-back that $3,200 walks to a competitor") and flip the hierarchy to **dollars over the multiplier**.
- **[04] Make screening visible:** the auto-built allowlist (zero import) is the best feature and is buried; graduation bar is too high for low-volume shops (they never reach enforce); reframe "false positive" as "caller rescued"; a monthly "N robocalls blocked, $X saved" report.
- **[08] Surface the compounding assets as "what you'd lose"** — reviews landing on Google (poll Places, track star count), the 200+ customer DB + history, accumulating ROI. The switching cost is real but hidden (moat ≈ 5/10).

## TIER 2 — Strategic additions (new lead sources + stickiness)
Ranked by impact-per-build-hour (lane 12):
1. **Spanish/bilingual AI** (H/S) — Claude already speaks it; one detect call + an owner toggle. Wins jobs in ~40% of US metros competitors can't see.
2. **Voicemail transcription → lead** (H/S) — Twilio already records; a recording webhook → transcribe → same text-back flow. Recovers the no-callback voicemails.
3. **Web-chat "Text us" widget** (H/M) — one JS snippet on the contractor's site turns dead web traffic into FirstBack leads (an entirely new lead source it ignores today).
4. **Deposit link at booking** (H/M) — uses the existing Stripe integration; converts soft-yes → committed, kills no-shows.
5. **GBP review dashboard + one-tap responses** (H/M) — closes the loop on the review engine that already sends the ask.
6. **Build the auto-mode streak unlock** that was spec'd but never built (the tray stays manual forever) — [08].

## TIER 3 — Positioning & acquisition (the site converts poorly cold)
- **[11] Reframe the category:** FirstBack is the best-designed tool for the solo/micro contractor but is perceived as "just another text-back tool." Its real wedges — **it actually books the job** (calendar-synced, where Rosie/Numa/Goodcall only capture/handle) and the **Vic daily money-briefing** — are invisible externally. Lead marketing with the outcome.
- **[06] Pricing page (price is right, the page is broken):** add an ROI anchor (vs answering services $300–800/mo, "one job pays the year"), make **annual the default** ("2 months free"), add **risk reversal** (free trial / money-back — every competitor has one), rename "conversations" → "missed-call replies" with a soft-overage path instead of a churn cliff, add a $20 extra-number add-on on Pro.
- **[10] Conversion basics:** no OG/SEO meta on any marketing page (blank Google snippet, blank social previews); zero third-party proof on the path — get **one real named contractor testimonial** from the Heritage dogfood (worth more than all polish).
- **[11] Close or credibly reframe the live-voice gap; add a Jobber/HCP read-only sync** to neutralize the "data silo" objection for 200k+ Jobber users.

---

## How to run the "loop" (the right way)
Not a live 75-agent loop (runaway cost, duplication) — **cycles**: this audit → fix Tier 0 + the cheapest Tier-1 wins → re-run this 12-lane wave → re-synthesize. Each cycle the reports get shorter as gaps close. I can re-run or schedule the wave on demand.

## Honest bottom line
The product is genuinely well-built — better-architected for its niche than anything at $99–399. But today it **hides its value, talks like a manual, and is hard to use one-handed on a phone**, and the public site gives a skeptical contractor little reason to convert. None of the top fixes are big builds; the highest-leverage 15 items are mostly S/M effort. Do Tier 0 before real customers, then Tier 1 to make the value undeniable.
