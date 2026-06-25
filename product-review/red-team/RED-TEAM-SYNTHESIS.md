# Red-Team Synthesis — FirstBack (2026-06-25)
4 parallel sonnet lanes (L1 bugs, L2 honesty, L3 compliance/security, L4 gaps/UX). Full lane reports:
`01-correctness-bugs.md`, `02-honesty-accuracy.md`, `03-compliance-security.md`, `04-gaps-ux.md`.
All 14 test suites green; `import app` clean. Findings are LATENT (not caught by existing tests).

## The lens that matters: LIVE-NOW vs GATED
Most P0s live in features that **aren't switched on in production yet** (pricing/billing, voice) — so they're
"fix before you flip the switch," not active fires. A smaller set affects the **live** app today. Prioritize
the live set first.

---

## TIER A — LIVE NOW (affects production today) — fix soon
**Security (the genuinely live exposure):**
- **A1 [P0] Login rate-limit bypass** (L3): rate-limit keys on `X-Forwarded-For` with no `ProxyFix` →
  attacker forges/rotates the header for unlimited credential-stuffing. Fix: add
  `werkzeug.middleware.proxy_fix.ProxyFix(app, x_for=1)`. (`app.py:375`)
- **A2 [P1] Logout is a GET** (L3, `app.py:415`) → `<img src="/logout">` logs users out cross-site. Make it POST + CSRF.
- **A3 [P1] `/contact` and `/auth/forgot` POST have no CSRF + no rate limit** (L3, `app.py:512`, `426`) →
  cross-origin spam / mail-quota exhaustion / fake contact messages. Add `_csrf_ok()` + per-IP limit.
- **A4 [P1] Real owner email hardcoded in source** (L3, `config.py`): `heritagehousepainting@gmail.com` as a
  fallback default — committed, in CI logs. Use `owner@example.com`.
- **A5 [P2] Burst rate-limit bypass at minute boundary** (L1 P1-1 / L3): epoch-aligned window, not sliding →
  ~2× burst near the boundary. Hardening.
- **A6 [P2] `TEMPLATES_AUTO_RELOAD = True` unconditionally** (L3) → should be `= DEBUG`.

**Correctness (live):**
- **A7 [P0] Assistant rate limiter double-counts + wrong reset time** (L1 P0-2, `app.py:208`): increments the
  daily bucket even on throttled calls (owners throttled harder than intended); the "resets at midnight"
  message uses local tz but the window is UTC-epoch-aligned → wrong time shown to non-UTC users.
- **A8 [P1] Rebook isn't transactional** (L1 P1-3, `app.py:2073`): new appointment is written before the old
  one is canceled → brief window with two `booked` rows; a crash mid-sequence leaves two permanent bookings.
  Wrap in one transaction.
- **A9 [P1] "cancel all" / "cancel please" routes to the AI** (L1 P1-2) instead of opt-out — only exact
  "cancel" is caught. A customer trying to stop may get an AI reply instead.
- **A10 [P2] `conversations_remaining` ignores period/status** (L1 P1-5): a canceled subscriber's last grant
  persists → gauge shows conversations + LLM stays usable post-cancel. (Matters once billing is live.)

**Compliance/privacy (live):**
- **A11 [P1] Privacy policy: vague retention, no CCPA rights section** (L3, `templates/privacy.html`).

---

## TIER B — GATED (fix BEFORE flipping the feature on)
**Pricing/billing — must fix before Stripe goes live (these are the highest legal/trust risk):**
- **B1 [P0] Crew tier sells phantom features** (L2 P0-3 + L4 P0-1, both lanes confirmed): "Team roles & logins",
  "Multiple business profiles", "Up to 5 phone numbers" have NO implementation (`pricing.html:101-114`). FTC /
  refund / chargeback risk. Either build them or remove the claims before charging anyone.
- **B2 [P0] Annual toggle is cosmetic** (L2 P0-2 + L4 P0-3): page sells "$950/yr (save $238)" but the Subscribe
  form hardcodes `interval=month` → everyone billed monthly. Wire the interval or remove the annual lines.
- **B3 [P0] In-app "+50 for $12" top-up link to a product that doesn't exist** (L2 P0-1, `command.html:177`) →
  a false promise inside the paid product. Remove or build the top-up.
- **B4 [P1] "No per-call fees. Ever."** (L2 P1-1, `pricing.html:37`) becomes false once voice bills per-minute
  (`VOICE_CREDIT_RATE_CENTS=25`). Drop "Ever."
- **B5 [P1] Stripe webhook race drops the grant** (L1 P1-6): if `invoice.paid` arrives before
  `checkout.completed`, business_id can't resolve → subscriber activates with zero conversations.
- **B6 [P1] No in-app billing self-management** (L4 P0-2) despite "cancel anytime" FAQ — no upgrade/cancel/plan UI.

**Voice — must fix before deploying the voice service:**
- **B7 [P0] Outbound AI greeting omits "AI" disclosure** (L3 P0-1, `voice_service.py:240`): FCC requires it
  (inbound was fixed, outbound default wasn't). Add "AI" to the default greeting.
- **B8 [P0] Hardcoded "what are you looking to get painted?" voicemail SMS** (L1 P0-1, `app.py:3812`) sent to
  EVERY tenant's customers regardless of trade. Make it trade-neutral.
- **B9 [P0] Voice stream double-writes the inbound message** (L1 P0-3) in split-service prod → duplicated
  transcript turns. Add an `already_recorded` flag to the turn-commit path.
- **B10 [P1] Inbound-voice preflight probes the wrong URL** (L1 P1-9): GETs the voice root, treats 404 as
  healthy; the dead-air guard can pass even when `/twiml` is broken. Probe `/twiml` (or a health route).

---

## TIER C — UX / product completeness (not blocking, but the SaaS bar)
- **C1 [P0] Dead link** `/command-center` on the growth tray (L4, should be `/dashboard`).
- **C2 [P0] 404 page links unauth users to `/dashboard`** → redirect loop through `/login` (L4).
- **C3 [P1] Growth Tray "Send All" has no confirmation** (L4) — one mobile tap blasts every customer (TCPA-adjacent).
- **C4 [P1] Missing self-serve basics:** password reset (known gap), email verification on signup, account
  deletion (CCPA/GDPR), data export, current plan/usage display.
- **C5 [P1] Setup-wizard placeholder text** ("Your service area") can carry through if not changed (L4).
- **C6 [P2] `og:image` missing** on all pages (known deferred).
- **C7 [P1-7 honesty] Resources page implies existing customer stories** (L2) that the destination page admits don't exist yet.

**Competitive gaps (vs Goodcall/Rosie/Podium/Jobber):** no live inbound answering (built, undeployed), no
PWA/mobile app, no per-customer CRM record view, no Zapier.

---

## VERIFIED CLEAN (no action — reduces the noise)
Twilio webhook signatures (all 9 endpoints), Stripe HMAC, internal voice seam (fail-closed, constant-time),
token encryption at rest, **cross-tenant isolation**, A2P "approved-only" gate, quiet hours, STOP/HELP/opt-out
+ re-opt-in, blocked-sends auto-flush, debug off in prod, password hashing, SQL-injection protection. All 14
test suites pass.

## Note on P0-4 (L1): the `.replace("Z","+00:00")` fromisoformat risk only bites on Python < 3.11. Render is
on 3.12 → likely MOOT, but confirm the `PYTHON_VERSION` on the `ringback` service.

---

## Recommended fix batches (each could be a small build-loop)
1. **Security hardening (live)** — A1–A6 + A11. Small, high-value, affects prod now.
2. **Pricing honesty (pre-Stripe)** — B1–B4 + C7: mostly copy/removal; do before any Stripe go-live. Cheap, removes legal risk.
3. **Billing robustness (pre-Stripe)** — B5, B6, A10.
4. **Voice correctness/compliance (pre-deploy)** — B7–B10 + the trade-neutral SMS.
5. **Core correctness** — A7, A8, A9.
6. **UX fixes** — C1, C2, C3, C5 (quick wins) then C4 (bigger: reset/verify/export/delete).

Owner gates all of this — nothing fixed without a pick.
