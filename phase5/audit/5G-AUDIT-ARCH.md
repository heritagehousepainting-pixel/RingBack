# 5G ARCHITECTURE AUDIT — F10 AI Voice
Date: 2026-06-18  
Branch: staging @ 503a2ea  
Suite: 11/11 (test_voice.py) green  
Auditor: READ-ONLY. No source files were modified.

---

## 0. Executive Summary

The spec's 5-slice partition (A–E) is NOT file-disjoint: Slice A touches
voice_service.py + app.py + llm.py; Slice E also touches voice_service.py +
app.py + llm.py. Slices C and D both touch messaging.py and app.py. Running all
five in parallel produces at least 4 merge collisions.

A clean 4-agent split IS achievable with one structural change: promote
voice_service.py and llm.py (voice additions) into separate owner-per-file
assignments, and fold related app.py hunks into the agent that owns the
endpoint being added. The result is 4 file-disjoint slices with no overlap.

Additionally, `tool_complete_stream` (llm.py:235) has **no `model` parameter**
— it hardcodes `CLAUDE_MODEL` (Sonnet). Any streaming voice path that calls
this function will bill Sonnet rates and incur ~3× the latency of Haiku.
This is a **P0 bug** that must be fixed before the streaming slice is complete.

---

## 1. LOCKED 4-SLICE FILE-DISJOINT PARTITION

### Why the spec's 5-slice plan collides

| Spec Slice | Files touched |
|---|---|
| A (streaming + barge-in) | voice_service.py, app.py, llm.py |
| B (pre-call guards) | app.py |
| C (metering) | db.py, messaging.py, app.py, config.py |
| D (AMD) | messaging.py, app.py |
| E (hygiene) | voice_service.py, app.py, llm.py |

Collisions: voice_service.py (A ∩ E), app.py (A ∩ B ∩ C ∩ D ∩ E),
llm.py (A ∩ E), messaging.py (C ∩ D). 4-way parallel build is impossible
without restructuring.

### The 4-agent file-disjoint partition

The key insight: app.py is the hub. Rather than one agent owning "all of
app.py," each agent owns the **specific endpoint(s)** it adds/modifies in
app.py. In practice this means app.py has 4 non-overlapping hunks each
belonging to one agent. Agents treat the file as having reserved regions.

```
SLICE 1 — voice_service.py ONLY
  Owner file: voice_service.py (entire file replaced/extended)
  App.py hunk: NONE (consumes endpoints added by other slices via HTTP)
  Specs covered: S-2 (streaming/barge-in), M-2 (ASR guard), M-3 (transcript),
                 M-5 (post-call SMS)
  Does NOT touch: llm.py, db.py, messaging.py, config.py

SLICE 2 — llm.py + config.py ONLY
  Owner files: llm.py, config.py
  App.py hunk: NONE (exposes streaming function; consumed by Slice 1 via HTTP relay)
  Specs covered: M-4 voice model wire + stream (add `model` param to
                 tool_complete_stream; add complete_stream_voice wrapper;
                 add CLAUDE_MODEL_VOICE to the function's model selection logic;
                 add VOICE_MONTHLY_CAP_CENTS + any missing voice consts to config.py)
  Does NOT touch: voice_service.py, db.py, messaging.py, app.py

SLICE 3 — db.py + messaging.py ONLY
  Owner files: db.py, messaging.py
  App.py hunk: NONE (db helpers + place_call StatusCallback/AMD params are
               consumed by Slice 4 in app.py)
  Specs covered: S-5 (voice_calls table + 4 helpers), M-1 AMD params in place_call
  Does NOT touch: voice_service.py, llm.py, config.py, app.py

SLICE 4 — app.py ONLY (all 4 endpoint hunks + guard additions)
  Owner file: app.py (4 non-overlapping regions)
  Specs covered:
    Region R1 (~line 2666-2673): STOP/detect_revocation handlers — add
      db.set_voice_consent(False) call after db.set_opt_out on both paths
    Region R2 (~line 2712-2724): voice consent block — add ordered pre-call
      guards (consent check, spam score, 60-min de-dupe, monthly cap check)
    Region R3 (new endpoint, after /internal/voice/turn ~line 2910):
      /internal/voice/stream SSE endpoint (calls llm streaming, yields tokens,
      fires handle_inbound on first [[BOOK]] detection)
    Region R4 (new endpoint, after R3):
      /internal/voice/turn_log (stores [VOICE] messages on disconnect)
    Region R5 (new endpoint, after R4):
      /webhooks/twilio/voice/status (AMD/StatusCallback handler)
  Does NOT touch: voice_service.py, llm.py, db.py, messaging.py
```

**Why app.py can be one agent's slice:**  
All 5 app.py changes are additive (new endpoints or 2-line additions inside
existing handlers). None touches a function body another agent owns. A single
agent writing all app.py voice additions eliminates the merge collision that
would result from 4 agents each trying to add a new `@app.route`. This is the
standard "one writer per module" rule applied correctly.

**Note on M-4 (confirmation echo):**  
M-4 is a system-prompt instruction only — no new code branch. It belongs in
Slice 2 (llm.py voice prompt builder) or can be passed as an extra instruction
from app.py /internal/voice/stream (Slice 4). Assign to Slice 2 so Slice 4
just passes a flag, keeping the prompt logic in the LLM layer.

---

## 2. THE EXACT CROSS-FILE CONTRACT

Agents build against these stubs before any other agent is complete.

### Contract: Slice 2 → Slice 1 (and Slice 4 → Slice 1)

**llm.py exposes:**
```python
def tool_complete_stream(provider, system, messages, tools, *,
                         max_tokens=700, temperature=0.4,
                         model=None) -> Iterator[tuple[str, Any]]:
    # yields ("text", delta_str)* then ("result", {text, tool_calls, usage})
    # model=None -> CLAUDE_MODEL (Sonnet); pass CLAUDE_MODEL_VOICE for Haiku
```

**llm.py exposes (new wrapper, preferred for voice path):**
```python
def complete_stream_voice(system, messages, *,
                          max_tokens=150) -> Iterator[str]:
    # Yields raw text deltas. Uses CLAUDE_MODEL_VOICE (Haiku). No tools.
    # Suitable for voice_service.py streaming to /ws.
    # Internally calls complete() with model=CLAUDE_MODEL_VOICE and streams
    # via client.messages.stream; yields each text delta.
```

**config.py exposes (additions):**
```python
CLAUDE_MODEL_VOICE: str      # already exists at line 49 — no change needed
VOICE_MONTHLY_CAP_CENTS: int # new: default 2000 (= $20)
VOICE_CREDIT_RATE_CENTS: int # new: default 25 (per 30-sec block)
```

### Contract: Slice 3 → Slice 4 and Slice 1

**db.py exposes (new functions):**
```python
def insert_voice_call(biz_id: int, lead_id: int | None,
                      twilio_sid: str) -> int:
    # inserts into voice_calls, returns new row id

def update_voice_call_outcome(twilio_sid: str, outcome: str,
                               duration: int, cost_cents: int) -> None:
    # UPDATE voice_calls SET outcome=?, duration_seconds=?, cost_cents=?,
    # ended_at=datetime('now') WHERE twilio_sid=?

def last_voice_call_at(biz_id: int,
                        caller_number: str) -> str | None:
    # Returns ISO datetime of the most recent voice_call for this caller,
    # or None. JOINs voice_calls -> leads on lead_id / phone.
    # Returns None (not an error) when voice_calls table doesn't exist yet.

def voice_spend_this_month(biz_id: int) -> int:
    # SUM(cost_cents) for this biz_id in current calendar month. Returns 0
    # when table is absent or no rows.
```

**messaging.py exposes (modified signature):**
```python
def place_call(business, to, twiml_url, status_callback=None) -> dict:
    # Already correct signature (line 209). Change: when status_callback is
    # None AND PUBLIC_BASE_URL is set, auto-populate:
    #   status_callback = PUBLIC_BASE_URL.rstrip("/") + "/webhooks/twilio/voice/status"
    # Also add to data dict when status_callback is truthy (already handled):
    #   data["MachineDetection"] = "Enable"
    #   data["AsyncAmd"] = "true"
    #   data["AsyncAmdStatusCallback"] = status_callback
```

### Contract: Slice 4 (app.py) → Slice 1 (voice_service.py)

**app.py exposes (new endpoints, consumed by voice_service.py over HTTP):**

`POST /internal/voice/stream`  
Headers: `X-Internal-Secret: <INTERNAL_SECRET>`  
Request body (JSON):
```json
{"biz": 1, "lead": 42, "text": "I'd like Thursday at 2pm", "history": [...]}
```
Response: `text/event-stream`  
Each line: `data: {"delta": "...token..."}\n\n`  
Final line: `data: {"done": true, "full": "...", "booked": "slot|null"}\n\n`  
Status 403 on bad/missing secret. Status 400 on missing biz/lead.

`POST /internal/voice/turn_log`  
Headers: `X-Internal-Secret: <INTERNAL_SECRET>`  
Request body (JSON):
```json
{
  "biz": 1, "lead": 42,
  "turns": [{"in": "caller text", "out": "ai reply"}, ...],
  "outcome": "booked|abandoned|dropped"
}
```
Response: `{"ok": true}`

`POST /webhooks/twilio/voice/status`  
Headers: Twilio signature (validated by @require_twilio_signature)  
Form params: `CallSid`, `CallStatus`, `CallDuration`, `AnsweredBy`  
Response: `{"ok": true}`

### Contract: Slice 1 (voice_service.py) internal shape

```python
# Session state object voice_service should maintain per /ws connection:
{
  "biz_id": str,
  "lead_id": str,
  "cancel_flag": asyncio.Event,       # set on "interrupt"
  "consecutive_empty": int,            # reset on non-empty prompt
  "turn_log": list[dict],              # {"in": str, "out": str}
  "booked": bool,                      # set when "booked" in stream final frame
}
```

---

## 3. BUILD AND MERGE ORDER

### Wave 0 — Stubs (can write immediately, no dependencies)

All 4 agents can stub their contract functions/endpoints simultaneously and
run tests against the stubs before implementation.

### Wave 1 — Parallel (no cross-slice dependencies yet)

| Slice | What to build | Unblocked because |
|---|---|---|
| Slice 2 | llm.py: add `model` param to `tool_complete_stream`; add `complete_stream_voice`; config.py: add VOICE_MONTHLY_CAP_CENTS, VOICE_CREDIT_RATE_CENTS | No deps |
| Slice 3 | db.py: voice_calls table + 4 helpers; messaging.py: AMD params + auto StatusCallback | No deps |

### Wave 2 — Parallel (after Wave 1 merges)

| Slice | What to build | Depends on |
|---|---|---|
| Slice 4 | app.py: R1 STOP guard, R2 pre-call guards, R3 /stream, R4 /turn_log, R5 /voice/status | Slice 2 (streaming fn), Slice 3 (db helpers, voice_monthly_cap) |

### Wave 3 — Serial last (after Wave 2 merges)

| Slice | What to build | Depends on |
|---|---|---|
| Slice 1 | voice_service.py: streaming /ws, barge-in cancel_flag, ASR guard, turn_log accumulate, post-call SMS | Slice 4 (/stream endpoint must exist to call) |

**Merge order: Slice 2 + Slice 3 in parallel → Slice 4 → Slice 1**

The test suite runs after each wave. Slice 1's tests are the integration
tests that exercise the full relay chain (mock HTTP for the SSE endpoint).

---

## 4. DESIGN CORRECTNESS REVIEW

### 4A. Booking write on first [[BOOK]] in stream — race / double-book risk

**Verdict: SAFE via existing UNIQUE constraint, but NOT reusing handle_inbound.**

Current path: `handle_inbound(biz, lead, text)` calls `ai.generate_reply`,
which calls `_claude_reply` → `_complete`, and runs booking via
`db.book_appointment` inside the same blocking call. The spec proposes that
`/internal/voice/stream` detects `[[BOOK]]` in the streaming token output and
calls `handle_inbound` on detection.

**Issue:** `handle_inbound` calls `ai.generate_reply` again (a full LLM call),
which means the voice path would run TWO LLM calls per [[BOOK]] turn: one for
the stream and one inside handle_inbound. This is wrong.

**Correct design:** `/internal/voice/stream` should NOT call `handle_inbound`.
Instead it should:  
1. Run the streaming LLM call and yield tokens.  
2. On stream completion, if `full_reply` contains `[[BOOK]]`, extract the slot
   and call `db.book_appointment(biz_id, lead_id, slot)` + the post-booking
   hooks directly (same logic as handle_inbound lines 1842–1872), OR  
3. POST the completed `full_reply` to `/internal/voice/turn` (the existing
   blocking endpoint) after the stream finishes — letting handle_inbound do
   the booking write as it does now. The stream is for UX only (getting tokens
   out fast); the booking write happens once at stream end.

**Option 3 is the simplest and safest:** stream tokens for UX, POST the
complete reply to `/internal/voice/turn` for the booking write. The DB
UNIQUE constraint prevents double-booking even if a race occurs. The slot
UNIQUE constraint is per-(biz_id, day, slot_time) — pre-existing and correct.

**Risk: Double-LLM call is NOT acceptable.** Slice 4 must NOT call
handle_inbound during the stream. It must call handle_inbound AFTER the stream
with the completed text, or skip handle_inbound and write the booking directly.

### 4B. Barge-in cancel semantics

**Verdict: Correct but partial; context truncation is a real problem.**

The `cancel_flag` approach correctly stops sending new tokens when Twilio fires
an interrupt. Tokens already delivered to Twilio before the interrupt are
discarded by Twilio (ConversationRelay spec behavior). The voice_service WS
loop will have a partial AI utterance as the last assistant message in
`turn_log`. Subsequent LLM turns receive a history that ends with a
partial/truncated AI sentence.

**Required:** the voice system prompt must instruct the model: "If your
previous reply appears cut off, treat it as complete and respond to the
caller's new utterance without re-completing the prior response." Without this,
the LLM may try to continue its previous partial sentence rather than handling
the new prompt.

**This is a prompt-only change** — belongs in Slice 2 (llm.py voice system
prompt builder) or Slice 4 (passed as extra_instruction in /stream).

### 4C. Render-to-Render relay hop vs. <1.5s gate (Risk 1 from spec)

**Verdict: Pre-building the in-process LLM fallback is worth it; here is why.**

The relay chain: Twilio STT → /ws (voice service) → HTTP to /internal/voice/stream
(web service) → Haiku → token stream back → /ws → Twilio TTS → caller.

The Render-to-Render HTTP hop (voice_service → web_service) for the SSE stream
adds estimated 80–250ms on cold path. Haiku's time-to-first-token is typically
300–600ms. Total: ~380–850ms before the filler fires + before first real token.
This is within the 1.5s gate under good conditions but has no headroom for
Render cold starts or Haiku latency spikes.

**Pre-build recommendation:** Slice 2 should also implement `complete_stream_voice`
as an importable function. When `WEB_INTERNAL_URL` is NOT set (i.e. the voice
service is running in-process mode for testing or a tighter deployment),
`voice_service.py` imports `llm.complete_stream_voice` directly. This is
already the pattern `_process_turn` uses for local mode (line 97: imports
`app as flask_app`). The streaming path should mirror this pattern.

**Scope impact:** Adds ~15 lines to voice_service.py — an `if WEB_INTERNAL_URL`
branch in the new streaming handler. This is a P1 item but straightforward.

**Cannot know if relay passes Gate 3 until a real call is measured.** Do not
claim the in-process path eliminates the problem — it only reduces latency by
one network hop. The filler frame ("One moment…") buys 400–600ms while Haiku
warms up, which is the real hedge.

### 4D. Unit-testable vs. deploy-gated — be explicit

**UNIT-TESTABLE without deploy (can be asserted today):**

| Test | What it verifies |
|---|---|
| `_say(text, last=False)` output shape | JSON schema correctness |
| filler frame sent before stream begins | mock stream, assert first frame is filler |
| `cancel_flag` set on "interrupt"; no further frames | mock asyncio.Event |
| final frame has `last=True` | frame accumulation |
| `/internal/voice/stream` uses `CLAUDE_MODEL_VOICE` not `CLAUDE_MODEL` | mock Anthropic client, assert model param |
| STOP text → `voice_ok=0` via `set_voice_consent(False)` | in-memory DB |
| pre-call guard skips `place_call` when `voice_ok=0` | mock place_call |
| pre-call guard skips when spam score >= SCREEN_SCORE_HARD | mock triage |
| `last_voice_call_at` returns None when table absent | no voice_calls table |
| `insert_voice_call` / `update_voice_call_outcome` round-trip | temp DB |
| `voice_spend_this_month` month boundary | temp DB with backdated rows |
| `/webhooks/twilio/voice/status` sets outcome=voicemail on AnsweredBy=machine_start | test client |
| monthly cap exceeded → place_call skipped | mock voice_spend_this_month |
| `place_call` data dict contains MachineDetection + AsyncAmd | assert data dict |
| 5 consecutive empty prompts → WS close | mock WS + event loop |
| `turn_log` accumulates and POSTs on disconnect | mock HTTP |
| post-call SMS fires with correct body per outcome | mock send_sms |

**DEPLOY-GATED — no unit test can verify these:**

| Gate | Why blocked |
|---|---|
| Latency < 1.5s first word (Gate 3) | Requires real Twilio STT + real Haiku + Render network; cannot simulate |
| Real barge-in interrupts TTS (Gate 4) | Requires real ConversationRelay interrupt event sequence |
| Voicemail suppression (Gate 5) | Requires real AMD AnsweredBy values from Twilio |
| Cold-start survival (Risk 4) | Requires real Render cold start timing |
| TTS voice quality (Gate 7) | Human ear-test only |

**Any test that sets a mock latency threshold and asserts it passes is a fake
test. Do not write those.**

---

## 5. FINDINGS TAGGED P0/P1/P2

### P0 — Blocking (must fix before any slice can be correct)

**P0-1: `tool_complete_stream` has no `model` parameter (llm.py:251)**  
`client.messages.stream(model=CLAUDE_MODEL, ...)` hardcodes Sonnet. If Slice 4's
`/internal/voice/stream` calls this function for the voice path, it will use
Sonnet, not Haiku. Latency will be 2–4× higher and cost will be ~4× higher.
The `complete()` function correctly accepts a `model` override (line 127, 151);
`tool_complete_stream` must be given the same `model=None` parameter and pass
it through. This is a 2-line fix in Slice 2. **Do not merge Slice 4 until Slice 2
lands with this fixed.**

**P0-2: `/internal/voice/stream` spec calls handle_inbound inside the stream (double LLM)**  
The spec (Section 2, SLICE A, Design point 2 bullet 1) says the stream endpoint
"runs the booking write (handle_inbound) on the FIRST [[BOOK]] detection in the
stream." `handle_inbound` calls `ai.generate_reply` which calls the LLM again.
This would run TWO LLM completions per booking turn. The correct behavior is to
stream tokens for UX, then call `/internal/voice/turn` (or write the booking
directly) at stream END with the completed full text. Slice 4 must NOT call
`handle_inbound` during the stream. See Section 4A above.

### P1 — Significant design risk (fix before Gate testing)

**P1-1: STOP voice consent revocation missing (spec gap S-4)**  
`app.py:2666–2673`: neither the STOP keyword path nor the `detect_revocation()`
path calls `db.set_voice_consent(biz["id"], caller, False)`. This means a
caller who texts STOP still has `voice_ok=1` in the DB. If voice is activated
later, the revoked consent is not honored. Slice 4 / Region R1 must fix this.
This is a regulatory compliance issue (FCC AI voice = robocall category).

**P1-2: Pre-call guards wired to non-existent table (spec gap B + C ordering)**  
Spec Slice B adds `last_voice_call_at()` guard in app.py, but writes it
"with a None-safe fallback" until Slice C creates the table. This is correct
but requires `last_voice_call_at()` in db.py to gracefully handle a missing
`voice_calls` table (catch `OperationalError`). This must be explicitly
contracted. Slice 3 must document the None-safe behavior. Slice 4 must not
assume the function returns a datetime.

**P1-3: Voice streaming relay — in-process LLM fallback not pre-built**  
The Render-to-Render SSE relay has no latency guarantee. If Gate 3 fails at
1.5s, recovery requires adding the in-process fallback path to voice_service.py.
This is cheaper to pre-build than to retrofit post-deploy. Slice 1 should
implement the `if not WEB_INTERNAL_URL: use llm directly` branch alongside
the relay path (mirroring `_process_turn`'s pattern at line 88–103).

**P1-4: Barge-in context truncation — no prompt instruction**  
The voice system prompt does not tell the LLM to handle truncated prior
assistant turns gracefully. After a barge-in, the LLM will receive a partial
AI sentence as the last message and may try to complete it rather than respond
to the new utterance. Slice 2 must add the instruction. (Low code cost, high
call quality impact.)

**P1-5: place_call does not auto-populate StatusCallback**  
`messaging.py:place_call` already accepts `status_callback` (line 209) but the
call site in app.py (line 2720) does not pass it. Until Slice 3 adds the
auto-populate logic AND Slice 4 adds the `/webhooks/twilio/voice/status`
endpoint, `place_call` never registers outcomes in `voice_calls`. Metering is
entirely dark until both are live. The fix is in Slice 3 (auto-populate from
`PUBLIC_BASE_URL` when `status_callback` is None).

### P2 — Quality / completeness gaps

**P2-1: Render cold-start risk for voice service (Risk 4 from spec)**  
Render Starter plan ($7/mo) has no CPU reservation. A cold start (15–30s) will
cause Twilio to time out the /twiml TwiML request before the call connects.
This is operational (not a code bug), but the owner must know: upgrade voice
service to Render Standard ($25/mo) before any real calls, OR add a health-ping
cron to keep the service warm.

**P2-2: AMD spec — voicemail recovery SMS uses wrong send path**  
The AMD voicemail handler (spec Section 2, SLICE D) sends a recovery SMS to
the lead, but at the time /webhooks/twilio/voice/status fires, the WebSocket
has already closed. The SMS must be sent from the status webhook handler
(app.py), not from voice_service.py. Slice 4 / Region R5 must send the
recovery SMS directly via `messaging.send_sms`.

**P2-3: `_say()` with `last=False` is not yet tested**  
The existing test_voice.py checks `/ws replies with a spoken text frame per
prompt` but only validates the final frame (last=True). The streaming path
requires last=False frames. Slice 1 tests must add explicit last=False coverage.

**P2-4: turn_log POST to /internal/voice/turn_log is fire-and-forget**  
If the POST fails (network error, web service restart), the voice transcript is
lost silently. Slice 1 should wrap the disconnect POST in a try/except and
log the failure with the session's biz_id + lead_id so it can be recovered.

**P2-5: 60-min de-dupe guard has no fallback SMS**  
Spec says when de-dupe skips the call, the response should be "text fallback."
The spec does not specify the fallback SMS text. Slice 4 must define the exact
message (e.g., "We spoke recently by phone — feel free to keep texting here.").

---

## 6. SUMMARY TABLE

| Item | Priority | Slice | Fix |
|---|---|---|---|
| tool_complete_stream missing `model` param | P0 | Slice 2 | Add `model=None` param, pass through |
| handle_inbound called inside stream (double LLM) | P0 | Slice 4 | Stream tokens only; POST to /turn at end |
| STOP does not revoke voice_ok | P1 | Slice 4 (R1) | Add set_voice_consent(False) after set_opt_out |
| last_voice_call_at needs None-safe on missing table | P1 | Slice 3 | Catch OperationalError, return None |
| In-process LLM fallback not pre-built | P1 | Slice 1 | Mirror _process_turn pattern for streaming |
| Barge-in context truncation prompt | P1 | Slice 2 | Add prompt instruction |
| place_call StatusCallback auto-populate | P1 | Slice 3 | Auto-set from PUBLIC_BASE_URL when None |
| Render cold-start risk | P2 | Owner-ops | Upgrade to Standard or add health-ping cron |
| Voicemail SMS must be sent from app.py not voice_service | P2 | Slice 4 (R5) | send_sms in status webhook |
| last=False frames untested | P2 | test_voice.py | Add explicit test |
| turn_log POST no error handling | P2 | Slice 1 | Wrap in try/except + log |
| De-dupe fallback SMS text not specified | P2 | Slice 4 (R2) | Define exact message |

**P0 count: 2. P1 count: 5. P2 count: 5.**

---

## 7. VERDICT ON APP.PY AS SINGLE-AGENT SLICE

**App.py CAN be one agent's slice.** All 5 regions (R1–R5) are additive.
No other agent modifies app.py. The regions are:

- R1 (~2 lines): inside existing STOP/detect_revocation handlers
- R2 (~10 lines): inside the existing `if norm in _CALL_WORDS` block
- R3 (new function, ~40 lines): `/internal/voice/stream` endpoint
- R4 (new function, ~15 lines): `/internal/voice/turn_log` endpoint
- R5 (new function, ~25 lines): `/webhooks/twilio/voice/status` endpoint

A skilled agent can handle these sequentially in one pass without merge
conflict. The risk of splitting app.py across agents is higher than the
complexity of keeping it with one agent.

---

## 8. REPORT LOCATION

`/Users/jonathanmorris/apps/firstback/phase5/audit/5G-AUDIT-ARCH.md`

Suite verification: 11/11 green (`python test_voice.py`).  
No source files were modified.
