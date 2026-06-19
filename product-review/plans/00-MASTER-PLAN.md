# FirstBack Upgrades — MASTER IMPLEMENTATION PLAN
**Date:** 2026-06-19 · Synthesized from 10 build-ready workstream plans (`product-review/plans/01..10-*.md`), themselves from the 12-lane product audit (`product-review/00-SYNTHESIS.md`).
**Purpose:** resolve cross-workstream collisions + sequence the work into shippable batches. Nothing here is built yet.

## Cross-workstream collisions (resolved here — read before building)
The plans independently flagged these shared seams. Resolutions:

1. **`alerts.py` is the hottest shared file.** Five workstreams add alert kinds / edit `format_message` / `ALERT_KINDS` / `_TOGGLE_COL`: a2p_approved (01), known-caller via a `"lead"` flag (03), owner-quiet-hours + all_clear + webhook (05), monthly_recap (06), screening_report (08). **Resolution: all `alerts.py` + alert-prefs (db whitelist + settings UI) edits are serialized through ONE pass (Batch D owns the file).** Other batches contribute their copy/kind but do NOT independently edit `alerts.py`/`db.update_alert_prefs` in parallel.
2. **One monthly digest, not three.** Monthly ROI recap (06) is the carrier SMS; **screening's monthly report (08) rides it as a section**, and the lifetime-ROI/review-delta surfaces (07) feed the same digest. One `scan_monthly_recap` on the 1st, one dedupe key, one SMS. (08 already recommended this.)
3. **ROI-milestone booking sites** (the two booking handlers + `roi_milestone_sent_at`) are touched by both 07 (progressive 2x/5x/10x/25x + a `roi_milestones` table) and 06 (real-dollar `won_amount`). **Resolution: 07 owns the milestone refactor (keep `roi_milestone_sent_at` set at level=2 for back-compat); 06's `won_amount` is additive attribution that feeds the same surfaces — build 07's refactor first, then 06's attribution.**
4. **`reminders.tick_once` + new `scan_*`** — several new scans (monthly recap, screening report, all-clear). Add them together, each in its own try/except, after the heartbeat (the established pattern).
5. **`db.py` migrations** — many ADD-COLUMN (alert prefs, quiet hours, webhook, won_amount, streak, milestones). **ALTER TABLE ADD COLUMN only, never recreate.** Batch the migrations.
6. **`app.css` / `app.js` / shared templates** — Mobile (04) owns the shared CSS/JS changes; smoke-test Command, Pipeline, Settings, Callers (not just Dashboard) on any `app.css`/`app_shell.html` edit.
7. **Kernel files:** `convos.py`/`llm.py` are trades_core-synced — edit firstback's local copies, never run `sync.py` (relevant to Batch B).

## Sequenced build batches (recommended order)

### Batch A — TIER-0 critical (ship FIRST) · ~1–1.5 days · plan 01
The live honesty + signup-blocker fixes. Mostly independent. Highest urgency (real callers/signups now).
- Honest voice line during A2P wait · EIN gate unblocks sole-props · hero phone wired to signup · `$null/job` tile · demo CTA → `/demo` · remove auth self-review stars · solutions "live voice" hedge · A2P-approved owner alert · roi_milestone toggle reachable.
- **Coordinate:** the a2p_approved alert kind + the roi_milestone toggle are alerts/prefs edits — do them here OR fold into Batch D, but not both. (Recommend: do the two tiny alert additions here since A is first, and have D build on it.)

### Batch B — AI conversation + core-loop speed · ~1.5 days · plans 02 + 03
The biggest book-rate lever. Persona prompt rewrite, urgency fast-path, price-objection pivot, token cap→450, Spanish (conversational); fast hardcoded first text-back (LLM reserved for turn 2+), known-caller owner alert, warmer reminder copy + direct phone.
- **Gate:** a full booking walkthrough in the live simulator after the prompt rewrite (the `[[BOOK]]` marker change is the main regression risk). **Coordinate** the alerts "lead" branch (known-caller flag) with Batch D.

### Batch C — Mobile + dashboard UX · ~1 day · plan 04
Card layout ≤640px, labeled nav, 44px tap targets, `tel:` links, styled error states, "all clear" empty state, urgency tint, briefing deep-links. Mostly CSS/templates/JS. **Defer the two-home merge** to a later sprint (too risky to bundle).

### Batch D — Alerts & set-and-forget consolidation · ~1.5 days · plan 05 (+ absorbs the alert-kind work)
THE coordinated `alerts.py` pass: owner quiet hours (urgent bypass; must NOT touch the customer TCPA backstop), stall-nudge daily cap, all-clear reassurance, webhook channel, the tick_stale per-business fan-out fix, and registration of every new alert kind from A/B/E. Highest-risk file in the system — validate the in-app claim still always writes + the customer quiet-hours backstop is untouched.

### Batch E — Make the value VISIBLE · ~3–4 days · plans 06 + 08 + 07
The anti-churn core. ONE monthly recap (ROI $ recovered + screening "robocalls blocked" section + lifetime running total), loss-framing + dollar-over-multiple, real-dollar `won_amount` attribution, the auto-built-allowlist headline + dual-axis graduation + low-volume path + "caller rescued" reframe, the Customer Book page, Google-review delta tracking, progressive ROI milestones, the auto-mode streak unlock, seasonal one-tap. Build the monthly-digest + milestone refactor as the shared spine.

### Batch F — Pricing + marketing + SEO · ~1 day (mostly copy) · plan 09
Annual-default toggle + "2 months free", ROI anchor, money-back badge, "missed-call replies" rename, SEO/OG meta across marketing pages, "books the job" hero wedge, testimonial pipeline (Heritage dogfood slot). **Blocked on 2 founder decisions** (below). Otherwise ships immediately, independent of code batches.

### Batch G — New lead-source features · ~2.5–3 weeks · plan 10
The revenue-ceiling raisers, sequenced MVP-first: (1) Voicemail→lead [S, only needs Twilio], (2) Deposit link at booking [S, only needs Stripe], (3) GBP review dashboard [M, needs Google re-auth w/ business scope], (4) Web-chat widget [M, needs micro-site slug]. Do 1+2 early (small, high impact); 3+4 as a dedicated track.

## Founder decisions required (yours, before building those bits)
- **30-day money-back guarantee?** (Batch F change 3 — a business policy, not code.)
- **Hero copy: lead with "it books the job" + the Vic briefing?** (Batch F — confirm we'll honor the framing.)
- **Bundle paid caller-reputation (Nomorobo/Hiya) into a paid tier?** (Batch E/08 — has a real cost; set `FIRSTBACK_REPUTATION_PROVIDER` + pricing implication.)
- **Soft-overage billing** (charge per extra reply) vs hard cap? (Batch F/06 — needs billing work if yes; copy-only "soft" version otherwise.)

## Effort summary
- **Polish + value track (A–F):** ~8–10 focused dev days for everything except the new features.
- **New-features track (G):** ~2.5–3 weeks, MVP-first.
- **Recommended first ship:** Batch A (today's live issues) → Batch B (the conversion lever) → then C/D/E in parallel-ish, F whenever the founder decisions land, G as a separate track.

## How this becomes the "loop"
Build a batch → run the standalone test suite + a be-audit on any money/consent/alerts path → re-run the 12-lane product audit to confirm the gap closed and surface what's next. Cycles, not a runaway loop.
