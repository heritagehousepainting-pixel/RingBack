# Build Audit — Plan 15 (Voice go-live gaps)
**Stage:** S4 BUILD-AUDIT (done inline by orchestrator — small, pre-verified scope) · **Date:** 2026-06-23.

**Verdict: SHIP.** No P1 issues. Scope was 3 small gaps + copy conditionals; orchestrator pre-verified
the dispatcher bug and independently ran all checks below.

## Verified
- **Bug 1 (dispatcher URL):** now built from `config.PUBLIC_BASE_URL` (Flask app), fallback `_public_base()`;
  gate still keyed on `VOICE_PUBLIC_URL`. New `test_dispatcher_call.py` test (with web≠voice hosts) asserts
  the dispatcher TwiML uses the Flask base, not the voice-service host. `test_dispatcher_call` 29/0.
- **httpx pinned** `>=0.25,<1` in requirements.txt.
- **Toggle honesty:** CALL gate now also honors `voice_callback_enabled` (defaults ON only when the key is
  absent/None, so dict-based callers aren't disabled). New R2e tests: off→no call (even with VOICE_PUBLIC_URL
  set), on/absent→proceeds. NOTE: SQL default is `INTEGER DEFAULT 0`, so the live tenant (id=1) has it OFF —
  **owner must toggle voice ON in Settings after deploy** (captured in SETUP_NEEDED).
- **Copy auto-flip:** `voice_configured=bool(VOICE_PUBLIC_URL)` passed to `/`, `/pricing`, `/product`,
  `/solutions`; templates branch on it. Verified BOTH directions: voice OFF → coming-soon/beta wording,
  **no overclaim**; voice ON → live wording (pricing/onboarding/solutions) and "beta" dropped (product).
- **No corruption:** all 4 changed templates parse; no smart-quote delimiters introduced; `import app` clean.
- **Tests:** voice 11/0, voice_app 61/0 (+5), voice_llm 13/0, voice_metering 31/0, voice_stream 42/0,
  dispatcher 29/0 (+4) — **187 total, 0 failed.** Marketing pages render 200 both ways.
- Voice stays fully inert until `FIRSTBACK_VOICE_URL` is set; consent/quiet-hours/metering untouched.
