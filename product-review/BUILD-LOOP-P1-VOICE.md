# Build loop — P1 Voice (caller-requested AI voice callback)
**Started 2026-06-23. Self-paced /loop. Orchestrator = main session; workers = sonnet subagents.**

**Key context (recon, 2026-06-23):** voice is NOT greenfield — it's substantially built already:
- `voice_service.py` (separate async Twilio **ConversationRelay** WebSocket service — Flask/WSGI can't host it).
- 6 test suites: `test_voice{,_app,_llm,_metering,_stream}.py`.
- `config.py` gating: `FIRSTBACK_VOICE_URL` (VOICE_PUBLIC_URL), `CLAUDE_MODEL_VOICE`, `CONVERSATIONRELAY_VOICE`,
  voice metering constants, `FIRSTBACK_VOICE_PORT`, `WEB_INTERNAL_URL`/`INTERNAL_SECRET` seam.
- `app.py`: `/webhooks/twilio/voice/{inbound,dial-status,sentinel-twiml}`, SSE streaming endpoint for the
  voice service, internal seam + turn_log storage. Settings toggle `voice_callback_enabled`.
- Direction already decided in code: **caller-requested callback** (SMS "CALL" → AI phones back), opt-in,
  Haiku-cheap, quiet-hours-bounded. NOT live inbound answering.
- Homepage says "Voice callback is coming soon … not available yet" because `FIRSTBACK_VOICE_URL` is unset
  (the separate `firstback-voice` service isn't deployed).

So the gap to go-live is likely **owner OPS (deploy the separate voice service) + copy flips**, with maybe
small code gaps/bugs — NOT a rebuild. This loop = ASSESS → plan the real gap → close genuine code gaps only.

## Hard rules
- Build on `staging` only. **Owner gates every staging→main promotion — never push `main`.**
- Voice stays gated/inert: unset `FIRSTBACK_VOICE_URL` → SMS "CALL" simply continues by text (no break).
- Honesty: never flip homepage/Pro copy to "live" until the service is actually deployed + reachable.
  The FCC treats AI voice as a robocall — keep quiet-hours + consent guards intact.
- Mocked tests only; never require live Twilio/telephony creds.

## Stages / state
- [x] **S1 ASSESS+PLAN** (sonnet) → DONE. Verdict **DONE-PENDING-DEPLOY**; 153 voice tests pass.
      Plan at `product-review/plans/15-voice-golive.md`. Genuine gaps: Bug 1 (dispatcher URL), httpx pin,
      toggle honesty; + copy flips to make conditional; rest is owner-ops deploy.
- [x] **S2 AUDIT** → compressed into orchestrator verification (plan was already evidence-based with
      file:line + ran the tests). Confirmed Bug 1: `/twiml/dispatcher/<id>` IS a Flask route (app.py:1784,
      uses `_public_base()` at 1795) but app.py:2015 builds its URL from `VOICE_PUBLIC_URL` → 404 in
      split-service prod. `_public_base()` is the correct fix primitive. `PUBLIC_BASE_URL` exists in config.
- [x] **S3 BUILD** (sonnet) → DONE. Bug 1 fixed (+test), httpx pinned, toggle honored (+R2e tests),
      marketing copy auto-flips on `voice_configured`. 187 voice/dispatcher tests green.
- [x] **S4 BUILD-AUDIT** → done inline (small pre-verified scope). **SHIP**, no P1. Audit at
      `product-review/plan-audits/15-build-audit.md`. Verified both copy directions (no overclaim when off),
      no template corruption, all suites green. **P1 batch committed + pushed to staging.**
- [x] **S5 HANDOFF** → SETUP_NEEDED voice go-live section added; memory updated; loop stops; owner notified.

## Outcome (2026-06-23)
Voice is **DONE-PENDING-DEPLOY**. The 3 genuine code gaps are closed on `staging`; voice stays inert until
the owner deploys the separate `firstback-voice` service + sets `FIRSTBACK_VOICE_URL` + flips the per-tenant
toggle on. Owner gates the staging→main promotion (NOT promoted). Deploy steps in SETUP_NEEDED → "Voice (P1)".

## Likely owner decisions to surface (don't block the loop)
- Confirm direction = caller-requested callback (already in code) vs add live inbound answering later.
- Pricing: voice as a $29–$49/mo opt-in add-on (per DEV-HANDOFF) — gated until pricing/billing live.
- The actual `firstback-voice` Render service deploy is OWNER OPS (telephony cost) — not a code build.

## Log
- 2026-06-23: loop created; recon shows voice mostly built; S1 assess+plan agent dispatched (background).
