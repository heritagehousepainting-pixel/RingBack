# Plan 17 — Live inbound AI voice answering
**Date:** 2026-06-23 · assess+plan (read-only) · build target `staging`; owner gates main.
The AI **answers an incoming call live** and books the estimate — distinct from today's caller-requested
callback (text CALL → AI phones back). **Reuses the entire ConversationRelay voice service unchanged.**

## Recommended model: FALLBACK (forward-first, AI on no-answer)
Ring owner's cell 18s → on miss, connect caller to ConversationRelay instead of voicemail/text. Always-AI
is achievable with NO extra code: leave `forward_to` blank + enable the toggle (Hook B fires immediately).
OWNER sign-off: confirm fallback-default is desired (vs always-AI). Surface at handoff.

## Current inbound flow (assessed, file:line)
- `/webhooks/twilio/voice/inbound` (app.py:3065–3098, `@require_twilio_signature`): (1) sentinel match
  (3078–3084) confirms forwarding + hangs up — fires FIRST, always short-circuits; (2) if `forward_to`
  set → `<Dial timeout=18 action=/voice/dial-status>`; else → `_missed_call_textback` (text).
- `/voice/dial-status` (3101–3127): on `_MISSED_DIAL` (no-answer|busy|failed|canceled) → `_missed_call_textback` (+ optional voicemail).
- Voice service `build_twiml` (voice_service.py:232) → `<Connect><ConversationRelay url=wss…/ws welcomeGreeting=…>`; `/ws` relays turns to `/internal/voice/turn` → `handle_inbound` (same booking engine as SMS).
- Metering: `db.insert_voice_call`/`voice_spend_this_month`/`last_voice_call_at`; `/voice/status` closes the row by CallSid. Compliance: `compliance.voice_allowed_now()` (outbound only; docstring: consumer-initiated contact is NOT quiet-hours-gated).

## Hook points (2, surgical)
- **Hook A** — in `/voice/dial-status`, when `status in _MISSED_DIAL`, BEFORE `_missed_call_textback`: try
  `_connect_inbound_to_ai(...)`; if it returns TwiML, return it (caller still bridged via answerOnBridge). Else existing text-back.
- **Hook B** — in `/voice/inbound` no-`forward_to` branch, BEFORE `_missed_call_textback`: same. (Sentinel
  check at 3078 fires first → sentinel never routed to AI.)

## Gating — inert unless ALL true (zero behavior change otherwise)
1. `VOICE_PUBLIC_URL` set (voice service deployed). 2. new per-business `inbound_voice_enabled=1`
(default 0; SEPARATE from `voice_callback_enabled` which is outbound). 3. under monthly voice cap. 4. not
confirmed-spam in enforce mode. (60-min de-dupe: **do NOT apply to inbound** — customer chose to call; cap
still protects spend.) Any fail → return None → existing flow runs unchanged.

## Net-new (everything else REUSED unmodified: voice_service, /internal/voice/*, handle_inbound, metering, cap/de-dupe queries, /voice/status, signature decorator, screening)
1. `db.py`: `businesses.inbound_voice_enabled INTEGER DEFAULT 0` migration + `update_phone_voice` kwarg.
2. `app.py`: `_connect_inbound_to_ai(biz, caller, call_sid)` helper (~30 lines: gates → find/create lead →
   `insert_voice_call(callsid)` → build `/twiml?biz&lead&name&greeting` URL → return `<Connect><ConversationRelay>` TwiML).
3. `app.py`: 4-line Hook A in dial-status; 4-line Hook B in inbound no-forward branch.
4. `app.py`: `inbound_voice_enabled` in settings POST handler.
5. `voice_service.py`: `build_twiml(..., greeting=None)` optional param + `/twiml?greeting=` query (default
   greeting unchanged when absent — backward compatible).
6. `templates/settings.html`: toggle in `set-voice` card (gated `voice_configured and sms_configured`) + honest copy. ASCII Jinja only.

## Inbound greeting (AI disclosure, NO recording claim by default)
"Hi, you've reached {name}. I'm an AI scheduling assistant — I can get you booked for a free estimate
right now. What can we help you with?" (Omit "may be recorded" unless owner enables recording — see Q1.)

## Compliance
Quiet-hours **N/A** (consumer-initiated, like answering your own phone / IVR — confirmed by compliance.py
docstring). AI identity + business name disclosed in greeting before any exchange. Inbound = business
ANSWERING a consumer-placed call ≈ IVR, far lower TCPA risk than outbound robocall (which is why the
callback path gates on consent). A2P unaffected (voice ≠ SMS). **Attorney review is a GO-LIVE gate, not a
build gate** (feature inert until deployed + opted-in). Recording disclosure omitted by default (transcript
relay, no audio record claim).

## Build order: db migration → build_twiml greeting param → _connect_inbound_to_ai → Hook A → Hook B →
settings POST → settings toggle. Then tests.

## Mocked test plan (`test_inbound_voice.py`, no telephony): I inert-when-off (both gates) preserves
existing behavior; II Hook A (forward set + miss → ConversationRelay TwiML, correct params, voice_calls row);
III Hook B (no-forward → ConversationRelay; sentinel still hangs up); IV cap/spam gates → text-back fallback;
V build_twiml custom vs default greeting; VI settings toggle persist + render. + existing 153 voice tests pass.

## Security: no new webhooks (reuse signature-verified routes); business_id scoping via get_business_by_twilio_number;
greeting/name `_xesc()`-escaped into XML; toggle behind @login_required; internal endpoints unchanged.

## Acceptance: off → zero regression; on → no-answer triggers ConversationRelay w/ AI-disclosure greeting,
voice_calls row opened, same booking engine, cap-exhausted → text-back; sentinel + outbound callback
unaffected; 153 voice tests pass + new suite green.

## OWNER decisions (surface at handoff; defaults chosen don't block build): Q1 recording disclosure
(default: omit/transcript-only) · Q2 60-min de-dupe inbound (default: off) · Q3 voice-service downtime
(accept + monitor; `<Connect>` has no auto text fallback) · Q4 always-AI vs fallback (default fallback;
always-AI = blank forward_to) · Q5 attorney review before real-customer rollout. S2 audit: verify hook
points + sentinel-first ordering + metering SID reuse against real code; confirm no break to forwarding/sentinel/callback.
