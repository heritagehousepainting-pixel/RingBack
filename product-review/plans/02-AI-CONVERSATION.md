# Plan 02 — AI Conversation / Booking-Brain Prompt Overhaul
**FirstBack build plan — workstream 2 of 10**
Grounded in: `product-review/03-AICONVO.md` + direct read of `ai.py`, `llm.py`, `config.py`

---

## IMPORTANT: Kernel sync rule

`convos.py` and `llm.py` are **trades_core-synced kernels**. The comment at the top of `llm.py` says:
> "Edit trades_core/llm.py, then run `python3 trades_core/sync.py`."

**DO NOT edit `llm.py` in firstback directly and do not run sync.py.** Edit only firstback's local copies. The sync tool would overwrite your changes. All changes in this plan target:
- `/Users/jonathanmorris/apps/firstback/ai.py` — owns the system prompt, urgency detection, price guard, booking flow
- `/Users/jonathanmorris/apps/firstback/config.py` — owns `DEFAULT_BUSINESS["ai_instructions"]` + `CLAUDE_DAILY_COST_CAP_USD`

The single line change to `max_tokens` in `llm.py` is the only exception; see Change 4 for how to handle it safely.

---

## Change 1 — Rewrite the system prompt as an embodied receptionist persona
**Impact: H | Effort: S | Risk: Low**

### What + Why

`_system_prompt()` in `ai.py` (line 74–108) currently opens with the `ai_instructions` field verbatim, then appends a RULES block that reads like a company style guide: "professional, clear, and courteous... no slang, no filler, no emoji." This describes a voice rather than embodying one. The `ai_instructions` seed in `config.py` (lines 549–558) is three procedural sentences: find out what they want, ask for address, offer windows. There is no warmth, no trade knowledge, no sense of a real person behind the text.

The result — confirmed by the demo — is "Got it, thanks! What part of town are you in?" as a turn-2 reply. It processes the caller, it does not convert them.

### Exact file + function + approach

**File:** `/Users/jonathanmorris/apps/firstback/config.py`
**Location:** `DEFAULT_BUSINESS["ai_instructions"]` (lines 549–558)

Replace the existing `ai_instructions` seed with the following persona block. This is the rewritten text that goes verbatim into the field:

```python
"ai_instructions": (
    "You are the virtual assistant for Heritage House Painting, texting back a "
    "caller on behalf of Jonathan. Sound like a sharp, knowledgeable person who "
    "works for the company — not a chatbot and not a form. Your job is to make "
    "the caller feel heard, confirm we can help, and get them booked for a free "
    "estimate. Be warm, brief, and direct. One to two sentences per text. Ask "
    "only one thing at a time. If they have already told you what they need and "
    "roughly where they are, skip those questions and go straight to offering "
    "estimate windows. Never dodge a price question: say honestly that Jonathan "
    "quotes in person so the number is accurate, then offer to book the estimate."
),
```

**File:** `/Users/jonathanmorris/apps/firstback/ai.py`
**Location:** `_system_prompt()`, the RULES block (lines 86–108)

Restructure the RULES block into two parts: a short VOICE section (what to sound like, kept to three bullets) and a longer DO-NOT section (hard constraints). The positive tone spec moves into the `ai_instructions` persona above; the RULES block enforces boundaries only:

```python
"RULES (hard constraints — never break these):\n"
"- Punctuation: standard only. No em dashes, en dashes, or double hyphens. "
"Use periods, commas, semicolons.\n"
"- Ask one thing at a time. Do not send a list or a form.\n"
"- Check conversation history before asking. Never ask for something the "
"caller already provided (address, job type, name).\n"
"- Only offer times from the available slots listed above; never invent a time. "
"State slots in plain words ('Monday at 9:00 AM'); never show the id.\n"
"- Confirm the service area by asking for the address once. Do not ask for "
"their name or phone number.\n"
"- Booking is the goal. Once the caller agrees to a time, your entire reply "
"must be a brief warm confirmation, followed on its own final line by the "
"booking marker in EXACTLY this format (use the full label as written above):\n"
"  [[BOOK: Monday Jun 22 at 9:00 AM]]\n"
"  The customer never sees this marker. It is the only way the system books "
"the appointment. After booking, ask no further questions.\n"
```

Note: the booking instruction now asks for the **full label** (not the id). This eliminates the id-reformat failure mode (F6 from the audit) — the label-match path in `_canonicalize_slot()` is more reliable than the id path when Claude rephrases. No change to `_canonicalize_slot()` needed; the existing label-match is already there.

### Tests

Add to `test_f03_brain.py`:
```python
# Test: persona tone — reply must NOT contain bureaucratic openers
result, _ = ai.generate_reply(_BIZ_WITH_PERSONA, [{"direction": "in", "body": "hi I need my house painted"}])
check("persona: reply does not start with 'Got it, thanks'", 
      not result.lower().startswith("got it, thanks"))
check("persona: reply is concise (under 300 chars)", len(result) < 300)

# Test: skip-already-answered — if address given in turn 1, AI does not ask again
history_with_address = [
    {"direction": "in", "body": "I need exterior painting, I'm at 123 Oak St"},
    {"direction": "out", "body": "Great, exterior painting at 123 Oak St. Can I offer you a free estimate?"},
    {"direction": "in", "body": "yes please"},
]
# This is a demo-mode test: just verify the reply doesn't ask "what part of town"
result2, _ = ai.generate_reply(_BIZ_WITH_PERSONA, history_with_address)
check("persona: does not re-ask for address when already given", 
      "part of town" not in result2.lower())
```

These are standalone demo-mode tests (no API key needed). They confirm the persona seed and the no-re-ask instruction are wired in; they do not test Claude's actual output quality (that requires a live API key and is a manual prompt-evaluation step).

---

## Change 2 — Urgency fast-path: inject urgency context when `detect_urgency()` fires
**Impact: H | Effort: M | Risk: Medium (touches generate_reply)**

### What + Why

`detect_urgency()` (lines 65–68 of `ai.py`) fires correctly when a message contains "burst", "flood", "emergency", etc. It marks the lead urgent and sends an owner alert. But `generate_reply()` (lines 467–525) calls `_system_prompt()` with no urgency context — the AI reply to "burst pipe no water" is the same three-step qualifier as any other call. This is the highest-dollar miss in the product: emergency leads are the highest premium and most likely to call a competitor in the next 5 minutes.

### Exact file + function + approach

**File:** `/Users/jonathanmorris/apps/firstback/ai.py`

**Step 1:** Add an urgency-aware system prompt builder. Add this function directly after `_system_prompt()` (after line 108):

```python
_URGENCY_INJECTION = (
    "\n\nURGENT SITUATION: The caller described an emergency or time-sensitive need. "
    "Skip the standard qualification flow entirely. In your FIRST reply: "
    "(1) Acknowledge the emergency directly and warmly. "
    "(2) Confirm you handle it. "
    "(3) Immediately offer the soonest available slot — if there are slots today or "
    "tomorrow, lead with those. "
    "Do not ask for the service area first. Do not run the standard qualifier. "
    "The address can be collected after they agree to a time."
)


def _system_prompt_urgent(business, slots):
    """System prompt variant for urgent/emergency inbound messages."""
    return _system_prompt(business, slots) + _URGENCY_INJECTION
```

**Step 2:** Modify `_claude_reply()` (line 134) to accept an `is_urgent` flag and select the prompt:

```python
def _claude_reply(business, history, slots, lead_id=None, is_urgent=False):
    """Call Claude for an SMS reply and log token usage to the ledger."""
    prompt = _system_prompt_urgent(business, slots) if is_urgent else _system_prompt(business, slots)
    text, usage = _complete("claude", prompt, _to_turns(history),
                            max_tokens=450, return_usage=True, timeout=30)
    # ... rest unchanged ...
```

Note: `max_tokens` is raised to 450 here (see Change 4 — combining changes in the same call site avoids a second diff).

**Step 3:** Modify `_minimax_reply()` the same way:

```python
def _minimax_reply(business, history, slots, is_urgent=False):
    prompt = _system_prompt_urgent(business, slots) if is_urgent else _system_prompt(business, slots)
    return _complete("minimax", prompt, _to_turns(history), max_tokens=512, temperature=1.0)
```

**Step 4:** Modify `generate_reply()` (line 467) to detect urgency from the latest inbound message and pass it through:

```python
def generate_reply(business, history, exclude_slot_ids=None, lead_id=None):
    # ... existing cap/turn gates unchanged ...
    
    slots = _open_slots(business["id"], exclude_ids=exclude_slot_ids)
    
    # Urgency detection: check the most recent inbound message only (not full history,
    # to avoid re-triggering on an old message after the situation is resolved).
    inbound = [m for m in history if m.get("direction") == "in"]
    is_urgent = bool(inbound and detect_urgency(inbound[-1]["body"]))
    
    provider = _active_provider()
    raw = None
    try:
        if provider == "claude":
            raw = _claude_reply(business, history, slots, lead_id=lead_id, is_urgent=is_urgent)
        elif provider == "minimax":
            raw = _minimax_reply(business, history, slots, is_urgent=is_urgent)
    except Exception as e:
        # ... existing fallback unchanged ...
```

### Tests

Add to `test_f03_brain.py`:
```python
# Test: urgency detection still works (unchanged function, sanity check)
check("urgency: 'burst pipe' detected", ai.detect_urgency("burst pipe no water"))
check("urgency: 'today' not detected (scheduling word, not emergency)", 
      not ai.detect_urgency("can you come today"))
check("urgency: 'Las Vegas' does not trigger 'gas' keyword", 
      not ai.detect_urgency("I'm in Las Vegas"))

# Test: generate_reply does not crash when last inbound is urgent (demo mode)
urgent_history = [{"direction": "in", "body": "burst pipe flooding bathroom"}]
result_u, booking_u = ai.generate_reply(_BIZ, urgent_history)
check("urgency: generate_reply returns non-empty string on urgent input", bool(result_u))
check("urgency: generate_reply does not book on first urgent message", booking_u is None)
```

These test that urgency detection is still correct and that the new `is_urgent` parameter does not break the call signature in demo mode (where `_demo_reply` is used as fallback regardless).

### Collision risk

The `is_urgent` flag is passed only into `_claude_reply` and `_minimax_reply`. It does not touch the `_resolve_booking` or `_slot_fallback` logic. The urgency injection is a system-prompt addition — it cannot cause a double-booking or break the `[[BOOK]]` marker flow. Risk is low.

---

## Change 3 — Price-objection pivot script
**Impact: H | Effort: S | Risk: Low**

### What + Why

The price guard (`_apply_price_guard`, line 449) correctly scrubs explicit dollar amounts from the AI's output. But there is no positive instruction for HOW the AI handles a price question. Without it, Claude will comply with the "no price" rule but may produce a flat "We don't provide prices over text" response — which stops the conversation. The most common opener in home services is "how much?" and right now the prompt has nothing to convert it with.

### Exact file + function + approach

**File:** `/Users/jonathanmorris/apps/firstback/ai.py`
**Location:** `_system_prompt()`, append to the RULES block (after the booking marker instruction)

Add the following as the final rule in `_system_prompt()`:

```python
"- Price questions: when someone asks about cost or price, respond honestly "
"that the number depends on what you see in person, then pivot immediately to "
"offering the free estimate. Example: 'Pricing depends on the scope, so "
"Jonathan quotes in person to make sure the number is accurate. The estimate "
"is free. Can I get you on the calendar?' Move to the slot offer in the "
"same message. Do not hedge, do not apologize, do not say you cannot help.\n"
```

This is a pure prompt addition. No code changes, no function signature changes.

### Tests

```python
# Test: price guard still strips explicit amounts (unchanged behavior)
check("price guard: strips $500", 
      "$500" not in ai._apply_price_guard("The job is $500"))
check("price guard: does not strip 'estimate is free'", 
      "estimate is free" in ai._apply_price_guard("The estimate is free"))
check("price guard: does not strip 'three rooms'", 
      "three rooms" in ai._apply_price_guard("We'll do three rooms"))

# Prompt-level pivot is not testable without a live API call.
# Manual test: send "how much does interior painting cost?" in the simulator.
# Expected: reply should offer the estimate, not say "we cannot quote."
```

---

## Change 4 — Raise Claude `max_tokens` from 300 to 450
**Impact: H | Effort: S | Risk: Very Low**

### What + Why

`_claude_reply()` in `ai.py` (line 139) calls `_complete("claude", ..., max_tokens=300)`. The `_apply_length_guard` in `ai.py` (line 458) caps visible output at ~480 chars — the length guard is the real ceiling, and the token cap should never be the binding constraint. MiniMax gets 512 tokens (70% more room) for the same task. Raising to 450 eliminates the asymmetry and gives Claude enough headroom for a full qualifier + slot offer turn without truncation.

**Cost impact:** At `claude-sonnet-4-6` pricing ($3/$15 per 1M tokens), the extra 150 output tokens per turn = ~$0.0000023 per call. Negligible.

### Exact file + function

**File:** `/Users/jonathanmorris/apps/firstback/ai.py`
**Location:** `_claude_reply()`, line 139 (and same function after Change 2 is applied)

This change is **combined with Change 2** — when `_claude_reply` is rewritten to accept `is_urgent`, also change `max_tokens=300` to `max_tokens=450` in the same edit. Do not make this as a separate commit to avoid a second diff to the same line.

**Note on llm.py:** The `max_tokens` parameter is passed *into* `complete()` in `llm.py` (line 181) as `max_tokens=max_tokens` — it's already a parameter, not a constant. No edit to `llm.py` is needed. This is safe.

### Tests

```python
# Test: max_tokens value is not something we can assert from outside the function.
# Verify indirectly: generate_reply still returns a non-empty string (smoke test).
# The existing test suite already covers this via generate_reply integration tests.
# No new test needed — the change is a parameter value, not a control flow change.
```

---

## Change 5 — Spanish language detection and auto-response
**Impact: M | Effort: M | Risk: Low**

### What + Why

No language detection exists. If a Spanish-speaking caller texts in Spanish, the system prompt is English-only and the RULES block says "correct grammar" without specifying which language. Claude (Sonnet) will likely respond in Spanish on its own — but the business context, slot labels, and RULES are English, so the AI may oscillate or produce a mixed-language reply. In painting, plumbing, HVAC, and landscaping markets (the target verticals), Spanish-speaking callers are 15–25% of the lead pool in many metro areas. This is a zero-cost fix at the prompt level.

**Scope note:** This plan owns the conversational mechanic (detect language, respond in kind). The separate "Spanish as a marketed product feature" (marketing site copy, onboarding toggle, settings UI) belongs to a different workstream and is NOT planned here.

### Exact file + function + approach

**Two-layer approach:** prompt instruction (always on) + owner toggle (for future marketing).

**Layer 1 — Prompt instruction (always on, zero cost):**

**File:** `/Users/jonathanmorris/apps/firstback/ai.py`
**Location:** `_system_prompt()`, append to the RULES block

```python
"- Language: detect the language of the caller's messages. If they write in "
"Spanish, reply in Spanish throughout the entire conversation. Use the same "
"tone (warm, brief, professional). Slot offers and booking confirmations stay "
"in Spanish. If they switch to English, switch back to English.\n"
```

This is a single prompt addition. Claude Sonnet handles this natively and reliably.

**Layer 2 — Owner toggle (database-ready, deferred UI):**

**File:** `/Users/jonathanmorris/apps/firstback/config.py`
**Location:** `DEFAULT_BUSINESS` dict

Add a field for the owner toggle:
```python
"spanish_enabled": True,  # auto-detect Spanish and respond in kind
```

**File:** `/Users/jonathanmorris/apps/firstback/ai.py`
**Location:** `_system_prompt()` signature

Add a conditional: if `business.get("spanish_enabled", True)` is False, omit the language instruction (for operators who explicitly want English-only). Default is True (on for everyone), but the toggle is wired so the settings page can expose it without a code change:

```python
if business.get("spanish_enabled", True):
    rules += (
        "- Language: detect the language of the caller's messages. If they write "
        "in Spanish, reply in Spanish throughout. Slot offers and confirmations "
        "stay in Spanish. Switch back to English if they do.\n"
    )
```

**No database migration needed for the toggle** at this phase — `business.get("spanish_enabled", True)` defaults to True when the column doesn't exist, so existing rows behave correctly. The settings UI can add the column and toggle later.

### Tests

```python
# Test: Spanish detection instruction is present in system prompt when enabled
biz_with_spanish = dict(_BIZ, spanish_enabled=True)
prompt = ai._system_prompt(biz_with_spanish, [])
check("spanish: instruction present when enabled", "spanish" in prompt.lower())

# Test: Spanish instruction absent when disabled
biz_no_spanish = dict(_BIZ, spanish_enabled=False)
prompt2 = ai._system_prompt(biz_no_spanish, [])
check("spanish: instruction absent when disabled", "spanish" not in prompt2.lower())

# Live API test (manual, requires ANTHROPIC_API_KEY):
# Send "hola, quería saber sobre pintura" to the simulator.
# Expected: reply in Spanish, same warmth and slot-offer flow.
```

---

## Change 6 — Raise daily cost cap default from $1.00 to $5.00
**Impact: M | Effort: S | Risk: Very Low**

### What + Why

`CLAUDE_DAILY_COST_CAP_USD = 1.00` in `config.py` (line 54–56). At `claude-sonnet-4-6` pricing, a typical SMS turn (350-token system prompt + 100-token context + 100-token reply) costs ~$0.003–$0.006 USD. The $1.00 cap allows 167–333 turns per business per day — safe for a normal contractor, but a busy painting company with 5–10 active leads on a rainy Monday could hit it by midday and start returning the "resting" message. That looks like a broken product.

$5.00 buys ~833–1,667 turns — more than enough for the busiest contractor day. The cap is a cost-control safeguard, not a business logic gate.

### Exact file + function

**File:** `/Users/jonathanmorris/apps/firstback/config.py`
**Location:** Line 54

```python
CLAUDE_DAILY_COST_CAP_USD = float(
    os.environ.get("FIRSTBACK_DAILY_COST_CAP", "") or "5.00")  # was "1.00"
```

Operator override via env var `FIRSTBACK_DAILY_COST_CAP` is already supported — no change needed there.

### Tests

```python
# Existing test: cap behavior at threshold (already in test_f03_brain.py or add):
# Verify is_over_daily_cap returns False when spend is $4.99 (under new cap)
# and True when spend is $5.01. Test uses db.log_llm_usage to set spend.
# This is a unit test on is_over_daily_cap() with a mock/temp DB — same pattern
# already used in test_f03_brain.py for the turn cap tests.
```

---

## Ordered Build Sequence

| # | Change | File | Effort | Depends on |
|---|---|---|---|---|
| 1 | Persona + RULES rewrite | `config.py` + `ai.py:_system_prompt` | S | — |
| 2 | Urgency fast-path (prompt injection + generate_reply wire) | `ai.py` | M | 1 (combined in same _system_prompt edit) |
| 3 | Price-objection pivot script | `ai.py:_system_prompt` | S | 1 |
| 4 | Raise max_tokens 300→450 | `ai.py:_claude_reply` | S | 2 (same function edit) |
| 5 | Spanish detection + owner toggle | `ai.py:_system_prompt` + `config.py` | M | 1 |
| 6 | Raise daily cap $1→$5 | `config.py` | S | — |

Changes 1, 3, 5 are all prompt additions to `_system_prompt()` — do them in a single editing pass to avoid three separate diffs to the same function.

Changes 2 and 4 both touch `_claude_reply()` — combine into one edit.

---

## Risk Assessment

### Biggest risk: regressions to the booking flow

The `_system_prompt()` rewrite (Change 1) changes the instruction the AI receives about how to emit the `[[BOOK]]` marker. The current instruction asks the model to use the slot **id**; this plan changes it to use the full **label**. This is a net improvement (the label match in `_canonicalize_slot` is more reliable than the id match), but it is a behavior change.

**Mitigation:**
1. The fallback chain is unchanged: `_canonicalize_slot` tries id → label → day/time parse. Even if the new instruction causes Claude to emit a slightly different format, the fallback path catches it.
2. `_slot_fallback` (the safety net in `generate_reply`) is also unchanged.
3. Manual simulator test required after Change 1: walk a full booking conversation and confirm `[[BOOK]]` fires and the appointment is created.

### Secondary risk: urgency injection on a 12-turn conversation

The urgency detection checks `inbound[-1]["body"]` (only the latest message). If a conversation is on turn 10 and the caller suddenly says "actually it's an emergency," the injection fires on an otherwise mid-qualified lead. The urgency block says "skip the standard qualifier" — in this case, the qualifier is already done and slots may have been offered. The AI should still short-circuit correctly because the "offer soonest slot" instruction aligns with what the booking flow expects. But this scenario should be tested manually.

### Non-risk: llm.py is not modified

All changes are in `ai.py` and `config.py`. The `max_tokens` change passes a different integer into `complete()` in `llm.py` — the function signature `complete(provider, system, messages, *, max_tokens, ...)` already accepts it as a parameter. No edit to `llm.py` is needed, and the sync.py risk does not apply.

---

## Total Effort

- Changes 1 + 3 + 5 (prompt additions, single editing pass): **S**
- Change 2 (urgency wiring, one new function + 3 call-site edits): **M**
- Change 4 (one integer, combined with Change 2): **S** (absorbed)
- Change 6 (one string): **S**

**Total: ~1 day of focused work.** The bulk is prompt evaluation — after code changes are committed, each change needs a live API run through the simulator to confirm the AI's actual output. Budget 2–3 hours for prompt tuning after the initial implementation.
