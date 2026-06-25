# Plan 15 — Voice Go-Live (caller-requested AI voice callback)
**Stage:** P1 from DEV-HANDOFF · **Date:** 2026-06-23 · assess+plan (read-only).
**Verdict: DONE-PENDING-DEPLOY** — architecture correct, **153 voice tests pass** (test_voice 11 +
voice_app 56 + voice_llm 13 + voice_metering 31 + voice_stream 42), consent/compliance fully wired
(FCC AI-voice consent gate, quiet-hours `compliance.voice_allowed_now()`, STOP revocation, 60-min de-dupe,
monthly cap). Direction in code = caller texts "CALL" → AI phones back via a separate Twilio
ConversationRelay (FastAPI/uvicorn) service; opt-in; Haiku-cheap.

## (A) OWNER OPS — deploy (no code)
1. Complete the `firstback-voice` service block in `render.yaml` (uvicorn `voice_service:fastapi_app`,
   starter ~$7/mo). Env: `FIRSTBACK_WEB_URL` (the Flask app URL), `FIRSTBACK_INTERNAL_SECRET`
   (**same value on BOTH services** — gates `/internal/voice/*`), optional `FIRSTBACK_VOICE_TTS`,
   `FIRSTBACK_PROVIDER=claude`. (ANTHROPIC key NOT needed on voice svc — it relays to the web app.)
2. Deploy it; note its URL; set `FIRSTBACK_VOICE_URL=<that url>` on the web service (master switch:
   `config.py` VOICE_PUBLIC_URL; activates the CALL path, flips `voice_configured`).
3. Confirm `FIRSTBACK_PUBLIC_URL` set on web (AMD StatusCallback). ConversationRelay needs no Twilio add-on.
4. Cost: ~$0.10–0.13/min (3-min call ≈ $0.30); default cap `VOICE_MONTHLY_CAP_CENTS=2000` ($20/biz/mo,
   tunable via `FIRSTBACK_VOICE_MONTHLY_CAP_CENTS`); +$7/mo Render.

## (B) GENUINE CODE GAPS (to build before deploy)
- **Bug 1 (MEDIUM, real):** `app.py:~2015` dispatcher-call TwiML base uses `VOICE_PUBLIC_URL` (the voice
  service), but `/twiml/dispatcher/<lead_id>` (`app.py:~1784`) is a **Flask** route → 404 when the two
  services are deployed separately (prod). Fix: use `PUBLIC_BASE_URL` (Flask app), fall back to
  `VOICE_PUBLIC_URL` only for local in-process dev. Existing `test_dispatcher_call.py` masks it (patches
  both to the same URL) → add a test asserting the dispatcher TwiML uses the Flask base when the two differ.
  Impact today: urgent-lead dispatcher calls would silently 404 (no call, no owner ping) on first real use.
- **Gap 2 (LOW):** `voice_service.py` imports `httpx` (transitive via `anthropic`); pin `httpx>=0.25,<1`
  in `requirements.txt` (belt-and-suspenders).
- **Gap 3 (LOW, likely intentional):** the per-tenant `voice_callback_enabled` toggle is saved but the
  call gate (`app.py:~3250`) keys only on `VOICE_PUBLIC_URL`, not the toggle. Single-tenant today so it's
  moot; make it honest defensively (gate also honors the toggle, defaulting ON when unset) or add a clear
  comment. Don't risk disabling the live tenant.

## (C) COPY FLIPS (gate on `voice_configured` so they auto-flip, never overclaim)
Make these conditional on `voice_configured=bool(VOICE_PUBLIC_URL)` (pass it to the marketing routes) so
they flip automatically on deploy instead of needing manual edits:
- `templates/onboarding.html:~243` ("Voice callback is coming soon … not available yet").
- `templates/pricing.html:~73` ("coming soon … beta — not yet available") + FAQ `~103`.
- `templates/product.html:~15,~54` ("in beta" / "beta" kicker).
- `templates/solutions.html:~42` ("AI voice callback is coming soon.").
- `templates/settings.html:~50` already conditional on `voice_configured` — no change.

## Build scope for this loop (small, bounded)
S3 build = Bug 1 fix (+ test), httpx pin, copy-flip conditionals (+ pass `voice_configured` to those
routes), and the toggle made honest/commented. Everything stays inert until `FIRSTBACK_VOICE_URL` is set.
The actual service deploy + copy go-live remain OWNER OPS.
