5G-AUDIT-SAFETY.md  --  Phase 5g AI Voice Safety & Compliance Audit
======================================================================
Date:    2026-06-18
Branch:  staging @ 503a2ea
Auditor: read-only (no source edits made)
Scope:   5 build slices (A–E) + standing infrastructure gates
Focus:   gate integrity, consent, quiet hours, AMD/voicemail, cost cap,
         PII, honesty of call status, pricing honesty


----------------------------------------------------------------------
VERDICT SUMMARY
----------------------------------------------------------------------

GATE INTEGRITY: SOUND AS-IS.  Voice cannot accidentally go live from
the current environment.  FIRSTBACK_VOICE_URL is unset; render.yaml
voice service block is commented out; VOICE_PUBLIC_URL="" at runtime;
every call-path branch guards on VOICE_PUBLIC_URL first.  No build
slice touches config.py VOICE_PUBLIC_URL assignment, render.yaml, or
pricing templates.  The 7-check gate remains the only authorized
unlock.

CONSENT/REVOCATION GAP (P0): STOP / detect_revocation handlers call
db.set_opt_out() but do NOT call db.set_voice_consent(False).
is_suppressed() checks opted_out, not voice_ok, so a future call path
that does a raw get_consent() check instead of is_suppressed() could
still see voice_ok=1 after a STOP.  Slice B MUST close this.

PRE-CALL GUARD ORDER (P0 MISSING GUARDS): Current code has no spam-
score check, no 60-min de-dupe, and no get_consent(voice_ok) re-
verification before place_call().  Slice B must add all three.

AMD / VOICEMAIL (P0): No MachineDetection params in place_call().
voice_service.py WebSocketDisconnect handler is a bare pass.  Nothing
prevents speaking a booking pitch into voicemail.  Slices C+D+E close.

COST CAP (P0): No voice_calls table, no voice_spend_this_month(), no
pre-dial credit check.  Unlimited calls possible once voice goes live
without Slice C.

PII: No secrets or caller numbers logged to stdout in voice_service.py.
Recording disclosure is hardcoded in build_twiml() and non-
configurable.  No P0 PII finding.

PRICING HONESTY: pricing.html line 39 shows "coming soon" and
"(beta -- not yet available)".  FAQ entry says "Today FirstBack
handles everything by text."  No build slice may remove these until
the 7-check gate passes.

P0 FINDINGS: 4
P1 FINDINGS: 3
P2 FINDINGS: 2


----------------------------------------------------------------------
SECTION 1 – GATE INTEGRITY (can the build accidentally go live?)
----------------------------------------------------------------------

G-1 [PASS] VOICE_PUBLIC_URL master gate
    config.py:210 reads FIRSTBACK_VOICE_URL from env (default "").
    app.py:2712 guards `if norm in _CALL_WORDS and VOICE_PUBLIC_URL:`
    place_call() itself also checks: if not twiml_url → returns
    {"status":"simulated"} (messaging.py:215).  Double gated.
    FINDING: SOUND.  No build slice assigns or overrides VOICE_PUBLIC_URL.

G-2 [PASS] render.yaml voice service is commented out
    render.yaml lines 82-98: entire voice service block is commented.
    The stale comment ("cannot share this one's SQLite disk") is wrong
    per spec §1 but is not a safety risk.
    MUST-DO (build Slice E or owner-ops): fix stale comment before
    uncommenting — wrong comment could mislead the ops person who
    enables the service.
    FINDING: SOUND for gate; stale comment is P2.

G-3 [PASS] render.yaml does not set FIRSTBACK_VOICE_URL
    No env var in render.yaml sets FIRSTBACK_VOICE_URL.  Voice stays
    off after any Blueprint deploy.
    FINDING: SOUND.

G-4 [PASS] Pricing templates unchanged
    pricing.html:39 — "coming soon" + "(beta -- not yet available)".
    pricing.html FAQ:69 — "Today FirstBack handles everything by text."
    No build slice touches templates/.
    MUST REMAIN TRUE: these strings must not be modified until the
    7-check gate passes and owner explicitly authorizes the flip.
    FINDING: SOUND.

G-5 [PASS] No build slice sets VOICE_MONTHLY_CAP_CENTS in a way that
    could activate voice.  Slice C adds the constant to config.py as
    a passive guard (only checked pre-dial).  Safe.


----------------------------------------------------------------------
SECTION 2 – FCC AI-VOICE CONSENT (robocall gate)
----------------------------------------------------------------------

C-1 [PASS] Affirmative opt-in required
    app.py:2712-2713: consent is set on "call me" in _CALL_WORDS,
    gated by VOICE_PUBLIC_URL.  The FCC requires affirmative consent
    before placing an AI voice call.  This is correctly placed before
    place_call().
    FINDING: SOUND.

C-2 [P0] STOP / detect_revocation does NOT clear voice_ok
    app.py:2666-2667 (STOP): calls db.set_opt_out() only.
    app.py:2670-2673 (detect_revocation / NLU): calls db.set_opt_out() only.
    app.py:2657-2663 (cancel→opt-out): calls db.set_opt_out() only.
    None of these three paths call db.set_voice_consent(False).

    Consequence: contacts_consent.opted_out becomes 1 (blocking SMS),
    but voice_ok remains 1.  If Slice B's pre-call guard checks
    get_consent(voice_ok) rather than is_suppressed(), a stopped caller
    could still be called.  is_suppressed() (db.py:2139) only reads
    opted_out — so any guard using is_suppressed() IS protected, but
    the spec's Slice B guard is defined as checking voice_ok separately.
    The two fields can diverge.

    REQUIRED FIX (Slice B):
      In all three opt-out paths (app.py:2663, 2667, 2673), after
      db.set_opt_out(), also call:
        db.set_voice_consent(biz["id"], caller, False)
      This ensures voice_ok=0 regardless of which field the guard reads.

C-3 [PASS] voice_ok default is 0 (opt-out-by-default)
    db.py:261: `voice_ok INTEGER DEFAULT 0`.  A new consumer row has
    no consent until they affirmatively send a call-me word.
    FINDING: SOUND.

C-4 [PASS] is_suppressed() checked before _CALL_WORDS branch
    app.py:2703 checks db.is_suppressed() before the code ever reaches
    line 2712.  An opted-out caller never triggers place_call regardless
    of the voice_ok gap in C-2 above.
    NOTE: This incidentally protects against C-2 today via opted_out,
    but the voice_ok discrepancy is still a P0 because it creates a
    latent bug if the guard path ever changes.


----------------------------------------------------------------------
SECTION 3 – PRE-CALL GUARD ORDERING
----------------------------------------------------------------------

Correct required order (from spec §2 SLICE B):
  (i)   is_suppressed() / opted_out — already fires at line 2703 ✓
  (ii)  get_consent(voice_ok) == 0 → skip call, text fallback  [MISSING]
  (iii) spam_score >= SCREEN_SCORE_HARD → skip call, text fallback  [MISSING]
  (iv)  last_voice_call_at within 60 min → skip call  [MISSING]
  (v)   voice_allowed_now() → currently at line 2714 ✓
  (vi)  monthly cost cap check  [MISSING — Slice C]
  (vii) place_call()

PG-1 [PASS] opted_out gate (i) — is_suppressed at line 2703, before
     the entire _CALL_WORDS block.  SOUND.

PG-2 [P0] voice_ok re-check (ii) ABSENT
     After set_voice_consent(True) at line 2713, there is no subsequent
     get_consent() read to verify voice_ok==1.  This matters because:
       - A future concurrent STOP between the opt-in and the dial could
         leave the caller with voice_ok cleared, but the in-flight
         request would still place_call().
       - Slice B MUST add: read get_consent() AFTER set_voice_consent()
         and confirm voice_ok==1, else skip.
     This is a required Slice B guard, not yet present.

PG-3 [P0] Spam score gate (iii) ABSENT
     No call to triage.spam_score() or triage.screen_caller() before
     place_call() in the _CALL_WORDS path.  A spam caller who sends
     "call me" would receive an outbound AI voice call.
     REQUIRED FIX (Slice B): before place_call(), compute spam_score
     against caller signals.  If >= SCREEN_SCORE_HARD (config.py:92,
     default 80), skip call and reply by text.

PG-4 [P0] 60-min de-dupe (iv) ABSENT
     No last_voice_call_at() helper in db.py (voice_calls table does
     not yet exist).  Spec notes Slice B should wire the guard with a
     None-safe fallback (no-op until Slice C creates the table).
     REQUIRED FIX (Slice B): add db.last_voice_call_at() helper that
     returns None when table absent.  Wire the guard: if last_call is
     not None and delta < 60 minutes, skip.

PG-5 [PASS] quiet hours gate (v) — compliance.voice_allowed_now() at
     line 2714.  After-hours text verbatim at lines 2715-2717.
     FINDING: SOUND.  Text matches spec exactly.

PG-6 [P0] Monthly cost cap (vi) ABSENT
     No voice_spend_this_month() check before place_call().
     Slice C MUST add: before place_call() at line 2720, check
     db.voice_spend_this_month(biz["id"]) >= VOICE_MONTHLY_CAP_CENTS
     ($20 default).  If exceeded: skip call, text fallback, alert Dave.

PG-7 [PASS] "Calling you now" honesty gate — lines 2723-2724.
     place_call() returns {"status":"placed"} only on HTTP 2xx from
     Twilio.  simulated/error returns different status.  The honesty
     guard is correct.
     FINDING: SOUND.


----------------------------------------------------------------------
SECTION 4 – VOICEMAIL / AMD
----------------------------------------------------------------------

VM-1 [P0] No MachineDetection params in place_call()
     messaging.py:217-219: data dict has To/From/Url and optionally
     StatusCallback.  No MachineDetection="Enable", no AsyncAmd="true",
     no AsyncAmdStatusCallback.
     Without these, Twilio connects the call unconditionally.  If the
     homeowner's phone rings to voicemail, ConversationRelay connects
     and voice_service.py /ws will speak the booking pitch into the
     voicemail recording.
     REQUIRED FIX (Slice D): add to place_call() data dict:
       data["MachineDetection"] = "Enable"
       data["AsyncAmd"] = "true"
       data["AsyncAmdStatusCallback"] = status_callback (same endpoint)

VM-2 [P0] WebSocketDisconnect handler is bare pass
     voice_service.py:177-178: `except WebSocketDisconnect: pass`
     No recovery SMS sent on unexpected disconnect.  If the call drops
     mid-conversation, the homeowner gets no follow-up and the lead is
     stranded with a partial thread.
     REQUIRED FIX (Slice E / M-5): on WebSocketDisconnect, check
     booking outcome and send appropriate recovery SMS.

VM-3 [P1] No /webhooks/twilio/voice/status endpoint yet
     Without this endpoint, AnsweredBy=machine_start cannot be caught,
     the voicemail path in twilio_voice_status (Slice C) cannot fire,
     and voice_calls rows cannot be updated with duration/outcome.
     This is a known gap (Slice C), but must be confirmed present
     before the 7-check gate fires.

VM-4 [PASS] Recovery SMS message text specified in spec
     Spec §2 SLICE D: "We tried to reach you by phone -- happy to keep
     chatting here."  This is the correct homeowner-facing message.
     Builders must use this exact text, not improvise.

VM-5 [P1] One retry only; retry must go through quiet-hours gate
     Spec §2 SLICE D: one retry after 2 hours.  After one retry, text-
     only resumes permanently for this consent.  MUST be enforced: the
     retry scheduler must call compliance.voice_allowed_now() before
     the second attempt.  Builders must not skip the quiet-hours check
     on the retry path.


----------------------------------------------------------------------
SECTION 5 – COST CAP
----------------------------------------------------------------------

CC-1 [P0] No voice_calls table; no monthly spend tracking
     db.py init_db(): no voice_calls table.  No insert_voice_call(),
     update_voice_call_outcome(), voice_spend_this_month() helpers.
     Cost tracking is entirely absent.
     REQUIRED FIX (Slice C): create voice_calls table (schema in spec
     §2 SLICE C) and all four helpers.

CC-2 [P0] No pre-dial cap check
     app.py pre-call path has no voice_spend_this_month() guard.
     REQUIRED FIX (Slice C): add immediately before place_call():
       VOICE_MONTHLY_CAP_CENTS (config.py, default 2000 = $20)
       if db.voice_spend_this_month(biz["id"]) >= cap:
           text fallback + alert Dave + return

CC-3 [P1] VOICE_CREDIT_RATE_CENTS (25¢/30s block) must use real
     Twilio call duration, not invented values.
     StatusCallback provides CallDuration in seconds (real Twilio
     value).  Slice C spec uses `math.ceil(duration / 30)` blocks.
     Builders must not substitute a flat per-call cost or estimated
     duration.  Metering must be honest.

CC-4 [PASS] Daily LLM cost cap exists separately
     config.py:54: CLAUDE_DAILY_COST_CAP_USD ($1.00 default).
     This gates the web app's LLM path.  The voice-path Haiku calls
     through /internal/voice/turn use the same llm.py path, so the
     daily LLM cap is inherited.  The voice-specific monthly cap
     (CC-1/CC-2) is additive protection on Twilio minutes.


----------------------------------------------------------------------
SECTION 6 – PII HANDLING
----------------------------------------------------------------------

PI-1 [PASS] No caller numbers logged to stdout in voice_service.py
     voice_service.py error prints (lines 174, 180) log the error
     description, not the caller's phone number.

PI-2 [PASS] Recording disclosure is FCC-required and hardcoded
     voice_service.py:108-109: "This call may be recorded." is baked
     into build_twiml() as a non-configurable string.  No tenant can
     remove it via a settings field.  SOUND.

PI-3 [PASS] INTERNAL_SECRET uses constant-time comparison
     app.py:2898: secrets.compare_digest(sent, INTERNAL_SECRET).
     Timing-safe.  Also: returns 403 when INTERNAL_SECRET is empty
     (line 2898: `if not INTERNAL_SECRET or not ...`), so the endpoint
     is dead until the secret is set.  SOUND.

PI-4 [P2] Transcript storage via [VOICE] messages (Slice E / M-3)
     When turn_log is written via /internal/voice/turn_log (Slice E),
     the builders MUST store as direction="system" with body prefix
     "[VOICE] caller: ..." / "[VOICE] ai: ...".
     MUST NOT: store raw caller phone numbers inside message bodies.
     MUST NOT: store Twilio recording URLs in db.add_message bodies
     (recording is handled by ConversationRelay on Twilio's side).

PI-5 [PASS] biz_id + lead_id are integers; SQL params are parameterized
     app.py:2902-2903 and voice_service.py build_twiml use integer
     casts and parameterized queries.  No SQL injection vector.


----------------------------------------------------------------------
SECTION 7 – MODEL GATING (voice path must use Haiku)
----------------------------------------------------------------------

MG-1 [PASS] CLAUDE_MODEL_VOICE = "claude-haiku-4-5"
     config.py:49.  Correctly distinguished from CLAUDE_MODEL (Sonnet).

MG-2 [P1] /internal/voice/stream (Slice A) MUST use CLAUDE_MODEL_VOICE
     The streaming endpoint in Slice A calls the LLM.  Builders must
     pass model=CLAUDE_MODEL_VOICE (haiku) explicitly.  Using the web
     app's default CLAUDE_MODEL (Sonnet) would:
       (a) blow latency past the 1.5s first-word gate
       (b) cost ~15× more per voice turn
     The test suite spec (§6) requires: "/internal/voice/stream uses
     CLAUDE_MODEL_VOICE (Haiku), not CLAUDE_MODEL."  This test must
     be present and must pass before merging Slice A.

MG-3 [PASS] Existing /internal/voice/turn uses handle_inbound, which
     calls llm.complete() — that function picks the model from config.
     As long as the voice service's CLAUDE_MODEL_VOICE env var is set
     (Gate 0 / owner-ops), the model is correct.  But: for the
     streaming path (Slice A), the model must be passed explicitly per
     above.


----------------------------------------------------------------------
SECTION 8 – WHAT MUST REMAIN TRUE AFTER THE BUILD
----------------------------------------------------------------------

The following invariants must hold after all 5 slices are merged to
staging and before any owner-ops step is taken:

  1. VOICE IS NOT LIVE.  FIRSTBACK_VOICE_URL is not set in render.yaml
     or any committed file.  VOICE_PUBLIC_URL="" at runtime.
     No tenant has voice active.

  2. PRICING IS UNCHANGED.  pricing.html still shows "coming soon" and
     "(beta -- not yet available)" on the voice line item.  The FAQ
     still says "Today FirstBack handles everything by text."

  3. NO TENANT IS ACTIVATED.  No database migration sets voice_ok=1
     for any existing lead.  Slices only add tables (voice_calls) and
     alter code paths.

  4. ALL EXISTING TESTS PASS.  test_voice.py 9 baseline checks +
     all new Slice A–E tests run without real Twilio/Claude.

  5. THE INTERNAL ENDPOINT IS DEAD WITHOUT THE SECRET.  
     /internal/voice/turn returns 403 when FIRSTBACK_INTERNAL_SECRET
     is unset.  Slice A's /internal/voice/stream must have the same
     guard.

  6. THE 7-CHECK GATE IS THE SOLE UNLOCK.  Pricing flip, first tenant
     activation, and marking 5g DONE all require the owner to run the
     gate on a real deployment.  This spec does not authorize any of
     those from the staging environment.


----------------------------------------------------------------------
SECTION 9 – CHECKLIST: NON-NEGOTIABLE GATES PER BUILD SLICE
----------------------------------------------------------------------

SLICE A (S-2 Streaming + barge-in)
  [ ] /internal/voice/stream passes model=CLAUDE_MODEL_VOICE (Haiku)
  [ ] /internal/voice/stream is secret-gated (same as /internal/voice/turn)
  [ ] Filler frame is sent BEFORE streaming begins (latency UX)
  [ ] cancel_flag stops frame emission on "interrupt" (barge-in)
  [ ] Final frame has last=True
  [ ] Tests: model guard, filler, cancel_flag, last=True

SLICE B (S-4 Pre-call guard additions)
  [ ] STOP (norm in _STOP_WORDS): after set_opt_out(), also call
      db.set_voice_consent(biz["id"], caller, False)       [P0 C-2]
  [ ] detect_revocation() path: same set_voice_consent(False)  [P0 C-2]
  [ ] cancel→opt-out path: same set_voice_consent(False)       [P0 C-2]
  [ ] Pre-call: get_consent(voice_ok)==0 → skip + text fallback [P0 PG-2]
  [ ] Pre-call: spam_score >= SCREEN_SCORE_HARD → skip + text  [P0 PG-3]
  [ ] Pre-call: last_voice_call_at within 60 min → skip        [P0 PG-4]
  [ ] last_voice_call_at() returns None when table absent (safe no-op)
  [ ] Guard order: consent → quiet → spam → de-dupe → cap → dial
  [ ] Tests: STOP clears voice_ok, detect_revocation clears voice_ok,
      spam skip, de-dupe skip (table absent = no-op)

SLICE C (S-5 Voice metering + cost enforcement)
  [ ] voice_calls table created with schema from spec §2 SLICE C
  [ ] insert_voice_call / update_voice_call_outcome / voice_spend_this_month
      / last_voice_call_at all present
  [ ] place_call() passes StatusCallback when PUBLIC_BASE_URL is set
  [ ] /webhooks/twilio/voice/status endpoint exists and is
      @require_twilio_signature gated
  [ ] AnsweredBy machine_* → outcome=voicemail (no spoken TwiML)
  [ ] Pre-dial cap: voice_spend_this_month >= VOICE_MONTHLY_CAP_CENTS
      → skip call + text + alert Dave                          [P0 CC-2]
  [ ] VOICE_MONTHLY_CAP_CENTS in config.py (default 2000)
  [ ] Cost calculation uses real Twilio CallDuration, not invented  [P1 CC-3]
  [ ] Tests: table round-trip, spend sum, AnsweredBy voicemail, cap skip

SLICE D (M-1 AMD / voicemail)
  [ ] place_call() data dict: MachineDetection="Enable",
      AsyncAmd="true", AsyncAmdStatusCallback=status_callback [P0 VM-1]
  [ ] voicemail detected → no spoken TwiML to voicemail
  [ ] voicemail detected → recovery SMS sent
  [ ] voicemail retry: max 1 retry; retry goes through quiet-hours gate [P1 VM-5]
  [ ] Tests: data dict params, recovery SMS sent, no TwiML to voicemail

SLICE E (M-2/M-3/M-4/M-5 Session hygiene)
  [ ] 5 consecutive empty ASR → WS close + recovery SMS       [P0 VM-2 partial]
  [ ] WebSocketDisconnect → recovery SMS for each outcome type [P0 VM-2]
  [ ] turn_log accumulates and POSTs [VOICE] messages on disconnect
  [ ] [VOICE] messages stored as direction="system", no raw phone
      numbers in body                                          [P2 PI-4]
  [ ] /internal/voice/turn_log is secret-gated
  [ ] M-4 confirmation echo: system prompt instructs AI to confirm
      slot before [[BOOK]] (prompt change, no code branch)
  [ ] Tests: 5-empty close, turn_log POST, post-call SMS per outcome type


----------------------------------------------------------------------
SECTION 10 – P0/P1/P2 REGISTER
----------------------------------------------------------------------

P0 (ship-blocker — build will be unsafe without this):
  P0-1  C-2   STOP/detect_revocation does not clear voice_ok
  P0-2  PG-2  No voice_ok re-check before place_call()
  P0-3  PG-3  No spam-score gate before place_call()
  P0-4  PG-4  No 60-min de-dupe before place_call()
  P0-5  PG-6  No monthly cost cap check before place_call()
  P0-6  VM-1  No MachineDetection/AsyncAmd in place_call()
  P0-7  VM-2  WebSocketDisconnect handler is bare pass (no recovery SMS)
  P0-8  CC-1  No voice_calls table / no spend tracking

P1 (must-fix before 7-check gate):
  P1-1  VM-3  No /webhooks/twilio/voice/status endpoint
  P1-2  VM-5  Retry quiet-hours gate must be enforced on retry path
  P1-3  MG-2  Slice A /internal/voice/stream must use CLAUDE_MODEL_VOICE

P2 (flag — fix before production, not a gate blocker):
  P2-1  G-2   render.yaml stale comment must be deleted before uncomment
  P2-2  PI-4  [VOICE] transcript bodies must not contain raw phone numbers

Total:  P0=8  P1=3  P2=2


----------------------------------------------------------------------
SECTION 11 – HONEST OPEN RISKS (not code, not in the gate)
----------------------------------------------------------------------

Risk A — Streaming latency is unknown until real deployment.
  Even with Haiku + relay, the Render-to-Render hop may exceed 1.5s.
  The 7-check Gate 3 is the only real test.  Builders should not
  assume the gate passes until measured.

Risk B — Barge-in context: partial AI sentence in conversation history.
  The system prompt (Slice A / M-4) must instruct the AI to treat
  partial context as complete and answer the new utterance.

Risk C — Double-booking race (SMS + voice concurrent).
  Protected by the DB UNIQUE slot constraint (pre-existing), not by
  new code.  Confirm in integration testing.

Risk D — Render Starter cold-start (15-30s) kills Twilio TwiML timeout.
  Operational decision: Standard plan or health-ping cron.

----------------------------------------------------------------------
END OF AUDIT
----------------------------------------------------------------------
