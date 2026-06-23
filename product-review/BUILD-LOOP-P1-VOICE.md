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
- [ ] **S1 ASSESS+PLAN** (sonnet, read-only) → audit `voice_service.py` + voice tests + app.py voice seams +
      metering/cost + consent/quiet-hours guards. Determine true readiness. Output a GO-LIVE plan that
      separates: (a) OWNER OPS (deploy firstback-voice + env), (b) genuine CODE gaps/bugs to build,
      (c) copy flips (homepage/Pro/settings) — gated on deploy. ← **IN PROGRESS**
- [ ] **S2 AUDIT** (sonnet) → scrutinize the plan + verify claimed gaps against real code.
- [ ] **S3 BUILD** (sonnet, write-capable) → close ONLY the genuine code gaps (if any); mocked tests green.
- [ ] **S4 BUILD-AUDIT** (sonnet) → review + tests green. Orchestrator commits/pushes staging.
- [ ] **S5 HANDOFF** → SETUP_NEEDED voice go-live (deploy steps) + memory; loop stops; notify owner.

## Likely owner decisions to surface (don't block the loop)
- Confirm direction = caller-requested callback (already in code) vs add live inbound answering later.
- Pricing: voice as a $29–$49/mo opt-in add-on (per DEV-HANDOFF) — gated until pricing/billing live.
- The actual `firstback-voice` Render service deploy is OWNER OPS (telephony cost) — not a code build.

## Log
- 2026-06-23: loop created; recon shows voice mostly built; S1 assess+plan agent dispatched (background).
