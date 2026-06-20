# Function + Data-Integrity Audit — Batches C/D/E/F/G
**Auditor:** Function + Data-Integrity lane (read-only)
**Base:** `92aacde` | **HEAD:** `2603ee7` | **11 commits reviewed**
**Date:** 2026-06-20

---

## Verdict

**SHIP-WITH-FIXES**

The core build is sound and safe to promote: every feature is either fully wired or honestly inert (gated off until the owner opts in). Two P1 gaps need a targeted patch before production — the widget bubble renders even when `widget_enabled=0` (silent 404 instead of no bubble), and the briefing deep-link from the plan (C8B, linking briefing action items to `/pipeline?lead_id=X` as anchor tags) was only half-shipped (the JS side works but the command-center template never emits the `<a href>` variant). Neither is a data-integrity or TCPA issue; both affect polish and UX promise. All P0 migration/wiring checks pass.

---

## P0 / P1 / P2 Findings

| Severity | File:line | Issue | Fix |
|----------|-----------|-------|-----|
| P1 | `static/widget.js:50-67` | Widget bubble **always renders** regardless of `widget_enabled` status. The server returns `window.__fb={}` for disabled slugs, but widget.js does not check `window.__fb` before injecting the DOM. A disabled-slug submission returns a 404 that is shown to the user as "Try again" — the bubble appears and the submit silently fails with no user-meaningful error. | In the `cs.onload` callback (widget.js:27-30), if `!window.__fb.biz` after config load, call `root.remove()` to tear down the bubble. Alternatively add a conditional render guard: if the endpoint config returns an empty object, do not inject the bubble. |
| P1 | `templates/command.html:44` | **Briefing deep-link (plan C8B) half-shipped.** The plan specifies that briefing items with a `deep_link` field render as `<a href="/pipeline?lead_id=X">` instead of a `<button data-action>`. The JS side (app.js:348-354) handles `?lead_id=X` auto-open correctly. But `command.html` emits every briefing row as a plain `<button data-action>` — no `deep_link` field is ever set in the briefing dict (no code in `_command_feed` or `assistant.briefing` emits `deep_link`). The test only checks that `/pipeline?lead_id=X` returns 200 and that `"lead_id" in appjs` — it does not verify the briefing actually links there. | Either: (a) add `deep_link` generation in `assistant.briefing()` for lead-thread items and add the `{% if it.get('deep_link') %}` branch to `command.html`, OR (b) formally defer C8B and remove it from the done-when scorecard. Current state: the URL works if you manually type it; the briefing never sends you there. |
| P2 | `app.py:2964` (`_widget_blocked` / widget_lead) | The batch-g-audit.md flagged rate limiter incrementing before slug check. **This was already fixed in shipping code** (slug resolved at line 2961 before `_widget_blocked` at line 2964). The audit report is stale; the code is correct. No action needed. |
| P2 | `static/widget.js:97-100` | On server 400 (bad phone format), the catch handler resets to "Try again" with no error message. An international visitor who types their country code gets no signal that the format is wrong. Not a security issue; UX gap. | Surface `r.json().error` in a small error span below the phone input on 400. |
| P2 | `reminders.py:964` (`scan_monthly_recap`) | The monthly recap fires only between hours 8-9 local (line 964: `if not (8 <= now_local.hour < 9)`). If the tenant's TZ offset is miscalculated, the SMS won't fire. No test covers the timezone edge case (midnight-crossing TZs). Low risk in practice (Heritage is US/Eastern, all customers likely US). | Add a test case for a biz with `tz='America/Los_Angeles'` to verify it fires at correct local 8am. |

---

## Done-When Scorecard

### Batch C — Mobile + Dashboard UX (plan 04)

| Criterion | Status |
|-----------|--------|
| `.dt-row[data-id]` shared by table rows AND card-list divs | PASS — dashboard.html:58 (table) and :77 (card div) both carry `class="lead-card dt-row"` and `data-id` |
| Error card (`addErrorTurn`) replaces silent `addMeta` error | PASS — app.js:99-115, openLead catch at :329 |
| All-clear empty state on the command center | PASS — command.html:62-70 + app.py:808-814 passes `last_lead_name` |
| Urgency signals (tile `:has()` tint, card `is-urgent` left border) | PASS — app.css + dashboard.html:58/77 |
| Deep-link: `/pipeline?lead_id=X` auto-opens the lead | PARTIAL — JS handler at app.js:348-354 works; briefing items never generate the `<a href>` variant (P1 above) |

**Verdict: PARTIAL** — C8B (briefing deep-link anchor) is not wired end-to-end.

---

### Batch D — Alerts / Set-and-Forget (plan 05)

| Criterion | Status |
|-----------|--------|
| Quiet-hours hold non-urgent SMS; in-app row always recorded | PASS — alerts.py:436-459, `_int_pref(0)` bug confirmed fixed |
| Urgent bypass list (`_URGENT_BYPASS_KINDS`) | PASS — alerts.py:46 |
| Stall cap (max N per afternoon, most-idle first) | PASS — reminders.py scan_stall_nudges, cap read via `_int_pref` |
| All-clear daily digest opt-in | PASS — alerts.py:258 all_clear branch, reminders.py quiet-branch |
| Webhook channel (SSRF guard + fire-and-forget) | PASS — alerts.py:473-524; blocks http/loopback/private/link-local |
| tick_stale fans to all tenants (not hardcoded id=1) | PASS — reminders.py:1037-1041 loops `db.list_businesses()` |
| Scan-driven digests bypass quiet-hours (integration fix) | PASS — `_QUIET_BYPASS_KINDS` at alerts.py:50-51 includes `daily_digest`, `monthly_recap`, `vic_stall` |

**Verdict: YES** — all D criteria met.

---

### Batch E — Make Value Visible (plans 06+08+07)

| Criterion | Status |
|-----------|--------|
| **E5/06-1** — Dollar figure hero, multiple as sub in analytics tile | PASS — analytics.html:109/111 |
| **06-2b** — Loss-framing "without a text-back" in weekly digest | PASS — convos.py:324 |
| **06-2a** — Loss-framing in milestone SMS body | PASS — roi.py:30/50 `_LOSS_TAIL` |
| **06-2c** — Loss-note revealed in analytics page when multiple truthy | PASS — analytics.html:81/120 |
| **06-3** — Monthly recap SMS (day 28-31, 8-9am, per-month dedupe, screening section) | PASS — reminders.py:946-1004 |
| **E2a/07-3** — Progressive milestones (only-up, back-compat legacy `roi_milestone_sent_at`) | PASS — roi.py:83-100; back-compat at :86-87 |
| **06-4** — `won_amount` attribution: DB migration, setter, aggregator, API, dashboard UI | PASS — db.py:899-901, :3912-3942; app.py:2383-2403; dashboard.html:113-115 |
| **analytics()** — existing keys unchanged, new keys additive | PASS — db.py:3126-3135 confirms all original keys preserved |
| **07-1** — Google review tracking (inert without GOOGLE_PLACES_API_KEY) | PASS — reputation.py:153 key-guard; db.py 5 columns added |
| **07-2** — Customer book at `/customers` (login-required, empty state, `last_job_day`) | PASS — app.py:603-620; customer_book.html:47-50 |
| **07-2d** — Customers added to sidebar nav | PASS — app_shell.html:51 |
| **07-2e** — Briefing hook for customer book | DEFERRED — explicitly noted in tracker |
| **07-4** — Streak unlock (TCPA: auto releases only `review_request`) | PASS — growth.py:486-492; gate at app.py:1406 |
| **07-5** — Seasonal cap (28-day frequency cap, cohort function) | PASS — app.py:1492-1512; db.py:4017-4024 |
| **07-6** — Density referral copy | PASS — growth.py:189-190, :321-327 |
| **08 fold-in** — Screening section in monthly recap | PASS — reminders.py:987-996 |

**Verdict: YES (with noted deferral)** — all shipped criteria met; 07-2e (briefing hook) and the minor analytics timeline deferrals are documented in the tracker.

---

### Batch F — Pricing / Marketing / SEO (plan 09)

| Criterion | Status |
|-----------|--------|
| SEO/OG meta on onboarding.html (the live homepage) | PASS — onboarding.html:6-16 has `<title>`, `<meta description>`, `og:title`, `og:description`, `twitter:description` |
| SEO/OG meta on pricing/solutions/customers/marketing_base | PASS — marketing_base.html:7-14; pricing.html:7 |
| `og:image` omitted (asset not yet generated) | PASS — onboarding.html:8 notes this intentionally |
| "conversations" → "missed-call replies" rename in pricing | PASS — pricing.html:56/70/87 |
| ROI anchor strip above pricing grid | PASS — pricing.html:23-44 |
| Pro extra-number add-on surfaced (routes to /contact) | PASS — pricing.html confirmed |
| Soft-overage FAQ | PASS — pricing.html:101 |
| /webinars de-linked from nav | PASS — marketing_base.html:65-66 |
| Annual toggle defaulting to annual (plan C1) | DEFERRED — explicitly NEEDS-OWNER in tracker |
| Money-back badge, dogfood quote, "books the job" hero | DEFERRED — NEEDS-OWNER in tracker |

**Verdict: YES (deferred items documented)** — all code-only criteria met.

---

### Batch G — Voicemail + Widget (plan 10)

| Criterion | Status |
|-----------|--------|
| Voicemail opt-in `<Record>` in `twilio_voice_dial_status`, gated on `voicemail_enabled` | PASS — app.py:2844-2851; default OFF (db.py:889) |
| Recording webhook creates lead (source=voicemail) + injects transcript | PASS — app.py:2876-2878 |
| `recording_url` on the message row (no fake direction) | PASS — app.py:2878 `direction="in"`, `recording_url=recording_url`; db.py:1529 |
| No double-greeting (existing outbound check before `open_conversation`) | PASS — app.py:2880-2883 inline outbound filter |
| Widget bubble (`/widget.js`, `/api/widget/<slug>/config.js`, `POST /webhooks/widget/lead`) | PASS — all three routes present |
| CORS on config + lead webhook | PASS — `_widget_cors` wrapper on all responses |
| Rate limit per (slug, IP) with slug resolved first | PASS — app.py:2959-2964 (slug check before rate increment, fixing batch-g-audit P2) |
| E.164 phone validation | PASS — app.py:2956-2958 |
| `widget_enabled=1` SQL gate on slug lookup | PASS — app.py:2916 `AND widget_enabled=1` |
| Widget bubble renders when slug is disabled | **PARTIAL (P1)** — bubble renders, submit 404s silently |
| `@require_twilio_signature` on recording webhook | PASS — app.py:2860 |
| Settings toggles save (`voicemail_enabled`, `widget_enabled`) | PASS — app.py:1252-1253; db.py:2558 |

**Verdict: PARTIAL** — core features wired and inert-until-enabled; P1 widget bubble visibility gap.

---

## Orphan Columns / Wiring Gaps

**No orphan columns found.** Every new DB column is confirmed written and read:

| Column | Table | Written at | Read at |
|--------|-------|-----------|---------|
| `alert_quiet_start` / `alert_quiet_end` | businesses | app.py:1247 → `update_alert_prefs` | alerts.py:436 `_int_pref` |
| `max_stall_alerts_day` | businesses | app.py settings save | reminders.py `_int_pref` in `scan_stall_nudges` |
| `alert_all_clear` | businesses | app.py settings save | reminders.py `scan_daily_digest` |
| `alert_webhook_url` | businesses | app.py settings save | alerts.py `notify()` |
| `alert_on_roi_milestone` | businesses | app.py settings save (default 1 at signup) | alerts.py `_enabled_for` |
| `growth_streak_count/last_at/unlocked_at` | businesses | db.py:3995-4004 `record_growth_go` | app.py:1406/1437 |
| `google_review_count` / `google_star_rating` / `review_count_updated_at` | businesses | db.py:3897/3903 `set_google_reputation` | app.py:1192 `/api/reputation`; reminders.py:934 |
| `google_review_count_baseline` / `google_star_rating_baseline` | businesses | db.py:3885-3908 `set_google_reputation` (first call only) | app.py `/api/reputation` |
| `voicemail_enabled` | businesses | app.py:1252 | app.py:2844 |
| `widget_enabled` | businesses | app.py:1253 | app.py:2916 SQL predicate |
| `won_at` / `won_amount` | leads | db.py:3923 `mark_lead_won` | db.py:3936-3942 `won_leads`; `analytics()` blend |
| `recording_url` | messages | app.py:2878 `add_message(recording_url=)` | app.py `/api/reputation` N/A; available for UI (not yet consumed) |

**Wiring gaps (minor):**

- `recording_url` on the messages table is written but never READ by any current UI route. The dashboard thread view does not render it. This is explicitly a Phase 2 deferral per plan 10. Not an orphan — it's there for the voicemail playback feature.
- `alert_on_daily_digest` was added in an earlier phase — confirmed in `update_alert_prefs` whitelist at db.py:2485.

---

## Data Integrity: Migration Safety

All migrations are `ALTER TABLE ... ADD COLUMN` with `IF NOT EXISTS` (PRAGMA table_info guard). No `DROP COLUMN`, no `RENAME`, no destructive backfills. The one exception to note: `google_review_count_baseline` and `google_star_rating_baseline` are written only on the FIRST `set_google_reputation` call — this is safe additive behavior. The `roi_milestones` table is `CREATE TABLE IF NOT EXISTS` with `UNIQUE(business_id, level)` — idempotent. `db.init_db()` is safe to call repeatedly.

---

## State Matrix: UI Surfaces

| Surface | Empty state | Loading state | Error state | No-data hidden |
|---------|-------------|---------------|-------------|----------------|
| Customer book | PASS — `empty_state()` macro at customer_book.html:47 | N/A (server-rendered) | N/A | N/A |
| Analytics tiles | Hidden until `roi:data` event | `display:none` default | Tile stays hidden | PASS |
| Reputation tile | Hidden (no data) | — | Stays hidden on catch | PASS — analytics.html:68 |
| Widget bubble (disabled slug) | — | — | Silent "Try again" (P1) | FAIL — bubble renders |
| Analytics ROI headline | Hidden if `!multiple || !revenue` | — | Stays hidden | PASS — analytics.html:96-99 |

---

## Test Coverage Notes

- **Coverage is strong for happy paths.** The 76 green tests span all new features with dedicated per-batch test files.
- **Gaps:**
  - No test asserts the widget bubble is absent when `widget_enabled=0` (the P1 gap).
  - No test covers `scan_monthly_recap` across a UTC-midnight TZ boundary (P2 note above).
  - No test verifies that the briefing's `data-action` button is ever replaced by a `deep_link` `<a>` tag (the C8B wiring gap).
  - `recording_url` column is tested for existence and population (test_batch_g.py:65-67) but no test renders it in a UI context.
- **No false assertions found:** examined test checks align with the actual code behavior.

---

## Regression Surface (Live Heritage Tenant)

| Change | Heritage Impact | Assessment |
|--------|-----------------|------------|
| Quiet-hours gate in `alerts.notify` | Owner SMS alerts held 10pm-7am unless urgent. Heritage gets the in-app row always. | SAFE — correct behavior; owner configured same defaults |
| Stall-nudge cap (default 2) | Max 2 stall-nudge SMS per afternoon instead of unlimited | SAFE — improvement, not a regression |
| `analytics()` blend | `confirmed_revenue`/`estimated_pipeline`/`won_n` added; all existing keys untouched | SAFE — strictly additive |
| `/customers` repurposed as login-required Customer Book | Public marketing URL now redirects anonymous visitors to login | LOW RISK — no marketing links to `/customers` remain in templates (confirmed); marketing stories at `/resources/customer-stories` |
| Voicemail `<Record>` in dial-status | Gated on `voicemail_enabled` (DEFAULT 0); Heritage not affected until they opt in | SAFE |
| Widget bubble | Gated on `widget_enabled` (DEFAULT 0) | SAFE |
| `tick_stale` fan-out (all tenants) | Heritage is the only live tenant, so no change in practice | SAFE |
| Progressive ROI milestones | Back-compat: if Heritage has `roi_milestone_sent_at` set, level 2 is pre-loaded into the fired set; no re-send | SAFE |
| Growth mode coercion of `auto` without streak | Heritage would see mode coerced to `tray` if they try to set `auto` without a streak — UI should reflect this. Streak unlock gate is correct TCPA protection. | SAFE |
