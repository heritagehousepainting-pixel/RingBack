# FirstBack Voice Pipeline — Build-It Track Research
**Authored:** 2026-06-30  
**Agent role:** BUILD-IT (self-hosted / composable stack)  
**Sibling track:** BUY-IT (Vapi / Retell / Bland — evaluated separately)  
**Orchestrator:** Opus synthesizes both tracks and picks winner

---

## TL;DR — Recommended Stack & Numbers

| What | Pick | Why |
|------|------|-----|
| Quick Win (this week) | ConversationRelay + Google Journey voice | Zero code, 1 env var, sounds human TODAY |
| Orchestration | Pipecat (Daily) | Fastest dev path, Twilio-native, swap parts in 1 line |
| ASR | Deepgram Nova-3 | <300ms, purpose-built for voice agents |
| LLM | Claude Haiku 4.5 (keep) | Best TTFT + quality for the price; Claude worth premium over DeepSeek for voice |
| TTS | Cartesia Sonic-3.5 | 40ms TTFA — best in market; $0.03/min |
| Telephony | Twilio (Phase 1-2) → Telnyx (Phase 3) | Telnyx saves 70% at scale |
| Hosting | Render now; Fly.io when migrating to Pipecat | Fly wins on WebSocket latency |

**Target mouth-to-ear latency:**
- Phase 1 (quick win): ~600-800ms (ConversationRelay, Twilio handles ASR/TTS)
- Phase 2 (Pipecat build): **490-650ms** ✅ hits the 500-700ms target

**All-in cost per minute (build-it stack):** ~$0.045-0.060/min vs $0.50/min billed to contractor = **8-11x gross margin**

---

## 1. Current Stack Audit

From codebase inspection (`voice_service.py`, `config.py`):

- **Telephony & media:** Twilio ConversationRelay (Twilio handles ASR + TTS; service receives transcribed text over WebSocket, replies with text)
- **LLM brain:** Claude Haiku 4.5 via `/internal/voice/stream` SSE relay
- **ASR:** Twilio's built-in ASR (unknown quality, not Deepgram)
- **TTS:** Controlled by `CONVERSATIONRELAY_VOICE` env var = `FIRSTBACK_VOICE_TTS`
- **Current TTS voice:** EMPTY → falls back to Twilio's default
- **Twilio ConversationRelay default (as of 2026):** `ttsProvider="ElevenLabs"`, `voice="UgBBYS2sOqTuMpoF3BR0"` (ElevenLabs Flash v2.5) — **this may already be active if no voice attr is set**
- **Filler frames:** "Mm-hmm, one moment." / "Let me check on that." / "Sure, just a sec." (rotated randomly) — already in place, reduces perceived latency
- **Barge-in:** `cancel_flag` asyncio.Event — already implemented
- **Billing to contractor:** `VOICE_CREDIT_RATE_CENTS=25` per 30s block = **$0.50/min**

**Key insight:** `build_twiml()` at line 244 only injects a `voice=""` attribute — no `ttsProvider` attribute. Since Twilio's 2026 default is ElevenLabs, if `FIRSTBACK_VOICE_TTS` is empty, the current setup *may already be using ElevenLabs Flash v2.5 by default*. If callers are still hearing robot voice, either (a) the ElevenLabs default is account-level and hasn't propagated, or (b) it changed after account creation. **Verify by test-calling before assuming a voice change is needed.**

---

## 2. Latency Budget — Mouth to Ear

### Current (ConversationRelay, unknown ASR/TTS)

| Stage | Estimated ms | Notes |
|-------|-------------|-------|
| VAD + audio capture | 50 | Twilio side |
| Twilio internal ASR | 200-400 | Twilio's legacy ASR, unknown |
| WebSocket Twilio→Render (Oregon) | 20-30 | US West same region |
| LLM TTFT (Claude Haiku 4.5) | 200-400 | Covered by filler phrase |
| TTS (Twilio/ElevenLabs Flash v2.5) | 75-200 | Flash v2.5 = 75ms model-only |
| Network Render→Twilio→Caller | 30-60 | Variable |
| **Total** | **575-1,140ms** | Filler phrase masks LLM wait |

Perceived latency is lower than this due to filler phrases firing before LLM completes.

### Phase 2 Target (Pipecat + Deepgram + Cartesia)

| Stage | Target ms | Source |
|-------|-----------|--------|
| VAD + audio capture | 50 | Standard |
| Deepgram Nova-3 STT | 150-200 | <300ms guaranteed; typical 150ms [Deepgram, 2026] |
| WebSocket Twilio→Fly.io | 20-30 | Fly.io near-region |
| LLM TTFT (Claude Haiku 4.5) | 150-300 | Covered by filler frame |
| Cartesia Sonic-3.5 TTFA | 40-90 | 40ms Turbo, 90ms standard [Cartesia, 2026] |
| Network Fly.io→Twilio→Caller | 30-50 | |
| **Total** | **490-670ms** | ✅ Hits 500-700ms target |

**ITU-T G.114:** preferred 150ms, tolerable 400ms (one-way). 500-700ms round-trip is at the human-acceptable ceiling — achievable and meaningfully better than most deployed systems (median reality is 1,400-1,700ms per 2026 benchmarks).

---

## 3. Orchestration Framework

### Pipecat (Daily.co) — RECOMMENDED for FirstBack

- **What it is:** Open-source Python framework. Data flows as typed `Frame` objects (AudioFrame, TextFrame, LLMResponseFrame) through a Pipeline of processors — Transport → STT → LLM → TTS → Transport. Swap any processor with a single line of code.
- **Twilio integration:** Native via `TwilioFrameSerializer` + WebSocket transport. Existing Twilio PSTN number stays; swap ConversationRelay TwiML for Media Streams WebSocket.
- **Production guidance (2026):** Pipecat co-founder recommends WebRTC (via Daily) over WebSockets for production audio — lower jitter, better barge-in. For phone agents, Twilio WebSocket is acceptable if Daily.co WebRTC integration is not used. [webrtc.ventures, Jan 2026]
- **Known gotcha:** `audio_in_sample_rate=8000` (Twilio's rate) silently breaks Smart Turn v3 VAD — `TwilioFrameSerializer` must handle 8kHz→16kHz upsampling internally.
- **GitHub:** `pipecat-ai/pipecat` — active, well-documented, AWS Bedrock blog post published June 2026.
- **Cost:** Free (open source); infra = your own hosting.

### LiveKit Agents — ALTERNATIVE for full migration

- **What it is:** Full WebRTC stack with native SIP/Phone Numbers built in (no Twilio bridge needed). Agent session: $0.01/min. Inbound local: $0.01/min.
- **Best when:** Want to cut Twilio entirely, own the full media stack, scale >10K min/month where Twilio costs dominate.
- **Not recommended for FirstBack Phase 1-2:** Higher migration complexity, loses Twilio ecosystem (ConversationRelay, existing number/webhook setup).

### Vocode

- Not prominently competitive in 2026 benchmarks; most production guidance steers to Pipecat or LiveKit. Not recommended.

**Decision: Pipecat for Phase 2 migration.** Lower migration effort (keeps Twilio PSTN), active community, modular enough to swap Cartesia or Deepgram in one line.

---

## 4. TTS Provider Comparison

All latency figures are time-to-first-audio (TTFA) from the model/API, excluding application and network overhead.

| Provider | Model | TTFA | Price/1M chars | Naturalness | Notes |
|----------|-------|------|----------------|-------------|-------|
| **Cartesia** | Sonic-3.5 | ~90ms | ~$37-40/1M est. | ★★★★★ | Ranked #1 naturalness 2026; GA May 2026 |
| **Cartesia** | Sonic-3.5 Turbo | **~40ms** | ~$40/1M est. | ★★★★★ | Fastest in market; SSM architecture |
| **ElevenLabs** | Flash v2.5 | **75ms** | $50/1M | ★★★★☆ | Available in Twilio CR today; 32 languages |
| **ElevenLabs** | Eleven v3 | 150ms | ~$100/1M | ★★★★★ | Most expressive; 2x Flash price |
| **Rime** | Arcana v3 | 120-200ms | $40/1M | ★★★★☆ | Feb 2026; 10 languages; 300+ voices |
| **Rime** | Mist v3 | 200-350ms | $30/1M | ★★★★☆ | Good for US English volume |
| **Inworld** | Realtime 1.5-Mini | <130ms | TBD (check pricing) | ★★★★★ | #1 ELO rating in realtime TTS; 2026 |
| **Deepgram** | Aura-2 | <90ms | $30/1M | ★★★☆☆ | Best if already on Deepgram stack; Voice Agent API $4.50/hr |
| **Amazon Polly** | Generative | 100ms-1s | $30/1M | ★★★☆☆ | Available in Twilio CR; variable latency |
| **Google** | Journey / Neural2 | 200-250ms | Varies | ★★★★☆ | Available in CR; `en-US-Journey-O` is best |
| ~~PlayHT / PlayAI~~ | ~~Play 3.0~~ | ~~200-400ms~~ | ~~$40/1M~~ | ~~★★★★☆~~ | **AVOID — acquired by Meta Jul 2025, being wound down** |
| **MiniMax** | Speech 2.6 HD | Unknown | $100/1M | ★★★☆☆ | Premium price, not competitive for voice agents |

**Winner for Phase 2 build-it:** Cartesia Sonic-3.5 (40ms Turbo or 90ms standard). Fastest, most natural, $0.03-0.04/min effective.  
**Winner for ConversationRelay path:** ElevenLabs Flash v2.5 (already integrated, 75ms, sounds human, can set TODAY).

**Cartesia credit pricing note:** Credit-based plans ($5/mo = 100K credits, $299/mo = 8M credits). Effective rate ~$37/1M chars at Scale tier. Per-minute TTS cost at ~800 chars/min of agent speech ≈ **$0.030/min**.

Sources: [Inworld TTS Benchmarks, 2026](https://inworld.ai/resources/best-voice-ai-tts-apis-for-real-time-voice-agents-2026-benchmarks); [Cartesia Changelog, 2026](https://docs.cartesia.ai/changelog/2026); [ElevenLabs Models docs](https://elevenlabs.io/docs/overview/models); [Coval TTS Guide, 2026](https://www.coval.ai/blog/best-text-to-speech-providers-in-2026-how-to-choose-(and-why-vendor-benchmarks-lie)/)

---

## 5. ASR / STT

| Provider | Model | Streaming TTFT | Price/min | Notes |
|----------|-------|----------------|-----------|-------|
| **Deepgram** | Nova-3 | **<300ms** (typ. 150ms) | $0.0077/min ($0.462/hr) PAYG | Purpose-built for voice agents; best accuracy |
| **AssemblyAI** | Universal-Streaming | ~300ms | $0.0025/min ($0.15/hr) | 3x cheaper; session-based (idle time billed); +10% price increase July 1, 2026 |
| Twilio CR | Built-in ASR | Unknown (legacy) | Included in CR | Not Deepgram; lower accuracy than dedicated STT |

**Decision: Deepgram Nova-3** for Phase 2 Pipecat build. At $0.0077/min it's only $0.0052/min more than AssemblyAI, but delivers consistently <300ms with better accuracy and no idle-time billing trap. For a voice agent where transcription accuracy directly impacts booking rate, this is worth the premium.

AssemblyAI is a legitimate cost-savings option if budget is the primary constraint — saves ~$3/hr at scale. But the session-idle billing model creates cost surprises during call holds.

Sources: [Deepgram pricing 2026](https://brasstranscripts.com/blog/deepgram-pricing-per-minute-2025-real-time-vs-batch); [AssemblyAI pricing](https://www.assemblyai.com/pricing); [STT API pricing comparison June 2026](https://www.buildmvpfast.com/api-costs/transcription)

---

## 6. LLM Brain

| Model | TTFT (est.) | Throughput | Input $/1M | Output $/1M | Voice suitability |
|-------|-------------|------------|------------|-------------|-------------------|
| **Claude Haiku 4.5** (current) | ~200-300ms | ~120 tps | $1.00 | $5.00 | ★★★★★ |
| Claude Sonnet 4.6 | ~300-500ms | ~100 tps | $3.00 | $15.00 | ★★★★☆ |
| **Groq Llama 3.1 8B** | <100ms | 500+ tps | $0.05 | $0.08 | ★★★☆☆ |
| Groq Llama 3.3 70B | **1.02s TTFT** | 394 tps | $0.59 | $0.79 | ★★☆☆☆ |
| MiniMax M2.7 | Unknown | 55.7 tps (slow) | $0.25-0.30 | $1.00-1.20 | ★★★☆☆ |
| DeepSeek V3 | Unpredictable | Unknown | $0.014 | $0.028 | ★★☆☆☆ |

**Decision: Keep Claude Haiku 4.5.** Here is why Claude is worth the premium over cheaper alternatives:

**Claude vs DeepSeek V3:** DeepSeek is 70x cheaper on input tokens but is NOT viable for voice: (a) routing to Chinese servers carries data-privacy risk for contractor+homeowner PII; (b) API latency is unpredictable and uncharacterized for sub-500ms voice use; (c) the ToS and data handling do not meet contractor business liability expectations. Pass.

**Claude vs MiniMax M2.7:** MiniMax is cheaper ($0.25 vs $1.00 input/1M) but throughput is 55.7 tps (below average). For voice, TTFT matters more than throughput since we stream to TTS. TTFT for MiniMax is uncharacterized. Not worth swapping away from a known-good integration. Pass.

**Claude vs Groq Llama 3.1 8B:** Groq 8B is 20x cheaper and extremely fast (<100ms TTFT). The risk is quality — 8B models produce more hallucinations, weaker instruction-following for booking flows, and less natural conversational English. For a product where "sounds human" is the core value prop, this is not the place to cut cost. Groq 70B TTFT of 1.02 seconds is too slow for voice without filler masking. Pass.

**Claude Haiku 4.5 vs Sonnet 4.6:** Sonnet 4.6 is 3x more expensive. For 20-30 word voice turns, the quality difference is not audible to a homeowner calling to book an estimate. The reasoning advantage of Sonnet matters for complex multi-step logic, not for conversational booking. **Stick with Haiku 4.5.**

**Cost per voice turn (Haiku 4.5):** ~200 input + ~80 output tokens × $1/$5 per 1M = $0.00020 + $0.00040 = **$0.00060/turn**. At 3-4 turns/minute = **$0.0018-0.0024/min** for LLM. Negligible.

Sources: [Claude API skill, 2026]; [Groq pricing June 2026](https://www.aipricing.guru/groq-pricing/); [MiniMax API pricing 2026](https://pricepertoken.com/pricing-page/provider/minimax); [DeepSeek API pricing](https://api-docs.deepseek.com/quick_start/pricing)

---

## 7. Telephony Ingress

| Provider | Inbound cost | Architecture | Latency advantage | Notes |
|----------|-------------|--------------|-------------------|-------|
| **Twilio ConversationRelay** | $0.0085/min receive | Twilio handles ASR+TTS; WS text-only | None (managed) | Current; lowest migration cost |
| **Twilio Media Streams** | $0.0085/min receive | Raw audio WebSocket; you own ASR+TTS | Full control | Phase 2 path with Pipecat |
| **Telnyx** | $0.002/min | SIP+WebSocket on private backbone | **43ms p95 lower** vs Twilio | 70-80% telephony savings; smaller ecosystem |
| **LiveKit SIP** | $0.01/min session + $0.01/min inbound | Native SIP+WebRTC; no Twilio | Best for non-Twilio full stack | Overkill unless going LiveKit fully |

**Phase 1-2: Stay on Twilio.** The $0.007/min telephony cost difference vs Telnyx is $4.20/1000 minutes. That's not material when the LTV per contractor is high. Twilio's ecosystem, existing webhook setup, and ConversationRelay familiarity are worth the premium at current scale.

**Phase 3 (>10K min/month or tight margin squeeze):** Switch to Telnyx. 43ms latency reduction + 70% cost savings. Telnyx's private backbone co-locates AI inference with their telephony network, enabling sub-200ms in-compute loops. Migration effort: ~2 days to re-point SIP/WebSocket endpoints.

**ElevenLabs Twilio CR integration note (for voice attribute syntax):**  
ConversationRelay uses `ttsProvider` and `voice` as *separate* attributes — unlike `<Say>` which uses `Polly.Joanna` prefix syntax.
- ElevenLabs: `ttsProvider="ElevenLabs" voice="UgBBYS2sOqTuMpoF3BR0"`
- Amazon: `ttsProvider="Amazon" voice="Joanna-Neural"`
- Google: `ttsProvider="Google" voice="en-US-Journey-O"`
- **Twilio 2026 default** (no attr set): `ttsProvider="ElevenLabs"`, voice = `UgBBYS2sOqTuMpoF3BR0`

Sources: [Twilio ConversationRelay TwiML docs](https://www.twilio.com/docs/voice/twiml/connect/conversationrelay); [Telnyx vs Twilio voice AI 2026](https://burki.dev/blog/42-twilio-vs-telnyx-voice-ai); [Telnyx pricing](https://telnyx.com/pricing/voice-api)

---

## 8. Hosting & Latency

| Platform | WebSocket latency | Global reach | Voice agent fit | Cost estimate |
|----------|------------------|-------------|-----------------|---------------|
| **Render (Oregon)** (current) | Good for US West; single region | No | Fine for ConversationRelay | ~$25-50/mo for voice service |
| **Fly.io** | Best — 20+ global regions, edge deploy | Yes | ★★★★★ for Pipecat | ~$20-40/mo, pay-per-use |
| Co-located GPU | Best possible | No | Only if running own TTS inference | Overkill for API-based |

**Decision for Phase 1 (ConversationRelay):** Render is fine. Twilio's media plane handles the heavy lifting; Render is just proxying text. Keep it.

**Decision for Phase 2 (Pipecat):** Migrate to Fly.io. Pipecat handles raw audio WebSocket — persistent connection, audio buffering, real-time pipeline. Fly.io's edge regions reduce the Twilio→app→Twilio audio roundtrip by deploying close to Twilio's media edge servers. Persistent WebSocket connections work natively on Fly.io; Render has session-affinity limitations that can drop long calls.

Sources: [Render vs Fly.io 2026](https://www.buildmvpfast.com/compare/render-vs-fly-io); [Fly.io vs Render WebSocket](https://northflank.com/blog/flyio-vs-render)

---

## 9. All-In Cost Per Minute

### Current Stack (ConversationRelay, no voice set)

| Component | $/min | Notes |
|-----------|-------|-------|
| Twilio inbound voice | $0.0085 | Standard US inbound rate |
| Twilio ConversationRelay | ~$0.005-0.010 | ⚠️ *Verify on Twilio bill — CR pricing unclear in public docs* |
| TTS (ElevenLabs Flash v2.5, if default) | ~$0.025-0.035 | $50/1M chars × ~600 chars/min agent speech |
| LLM (Claude Haiku 4.5) | $0.002 | 4 turns × ~300 tokens at $1/$5/1M |
| Hosting (Render) | $0.001 | Amortized |
| **Total estimated** | **~$0.040-0.055/min** | |
| **Billed to contractor** | **$0.500/min** | |
| **Gross margin** | **~89-92%** | |

### Phase 2 Stack (Pipecat + Deepgram + Cartesia + Fly.io, Twilio PSTN)

| Component | $/min | Source |
|-----------|-------|--------|
| Twilio inbound PSTN | $0.0085 | Twilio US inbound |
| Deepgram Nova-3 STT | $0.0077 | PAYG streaming [Deepgram 2026] |
| Claude Haiku 4.5 LLM | $0.002 | 4 turns × ~300 tokens |
| Cartesia Sonic-3.5 TTS | ~$0.030 | ~$37/1M chars × 800 chars/min |
| Fly.io hosting | $0.002 | Amortized across concurrent calls |
| **Total** | **~$0.050/min** | |
| **Billed to contractor** | **$0.500/min** | |
| **Gross margin** | **~90%** | |

### Phase 3 Stack (Telnyx + Pipecat + Deepgram + Cartesia)

| Component | $/min | Source |
|-----------|-------|--------|
| Telnyx inbound | $0.002 | [Telnyx pricing 2026] |
| Deepgram Nova-3 STT | $0.0077 | |
| Claude Haiku 4.5 LLM | $0.002 | |
| Cartesia Sonic-3.5 TTS | $0.030 | |
| Fly.io hosting | $0.002 | |
| **Total** | **~$0.044/min** | |
| **Billed to contractor** | **$0.500/min** | |
| **Gross margin** | **~91%** | |

**Key insight:** The margin is already massive at $0.50/min. The cost of premium voice (Cartesia or ElevenLabs) is ~$0.03/min — barely moves the needle vs the billing rate. **Spend the 3 cents per minute and deliver the human-sounding voice that justifies the charge.**

The real value of Phase 2-3 is not cost reduction — it's **quality** (Deepgram ASR → fewer transcription errors → better bookings) and **latency** (490-650ms → calls feel natural → lower abandonment).

---

## 10. Migration Effort

### Phase 1 — Quick Win (1-4 hours this week)

**Goal:** Make the current voice immediately sound human without touching production code.

Two options, in order of ease:

**Option A (zero code, ~10 minutes):**
Verify that the current default ElevenLabs voice is active by test-calling. The Twilio docs confirm the 2026 default for ConversationRelay is ElevenLabs Flash v2.5 (`ttsProvider="ElevenLabs"`, `voice="UgBBYS2sOqTuMpoF3BR0"`) when no `voice` attr is set. If callers are already hearing a decent voice, nothing needs to change.

**Option B (zero code + 1 env var, ~30 minutes):**
Set `FIRSTBACK_VOICE_TTS=en-US-Journey-O` on Render (Google Journey voice). **But first read the caveat:** The current `build_twiml()` only adds `voice=""` without `ttsProvider=""`. Google Journey requires `ttsProvider="Google"`. Without it, Twilio will try to use the voice ID with ElevenLabs provider and likely fail or silently fall back.

**Option C (2-line code change + 2 env vars, ~2 hours):**  
Add `ttsProvider` support to `build_twiml()`. In `voice_service.py` line 244, change:
```python
# BEFORE:
voice_attr = f' voice="{_xesc(CONVERSATIONRELAY_VOICE)}"' if CONVERSATIONRELAY_VOICE else ""

# AFTER:
from config import CONVERSATIONRELAY_TTS_PROVIDER  # add this to config.py import
_p = f' ttsProvider="{_xesc(CONVERSATIONRELAY_TTS_PROVIDER)}"' if CONVERSATIONRELAY_TTS_PROVIDER else ""
_v = f' voice="{_xesc(CONVERSATIONRELAY_VOICE)}"' if CONVERSATIONRELAY_VOICE else ""
voice_attr = _p + _v
```
Then in `config.py`, add:
```python
CONVERSATIONRELAY_TTS_PROVIDER = os.environ.get("FIRSTBACK_TTS_PROVIDER", "")
```
Then on Render, set:
- `FIRSTBACK_TTS_PROVIDER=ElevenLabs`
- `FIRSTBACK_VOICE_TTS=EXAVITQu4vr4xnSDxMaL`  ← or any ElevenLabs voice from their library

**Recommended Option C voice IDs (ElevenLabs, US English, female):**
- `EXAVITQu4vr4xnSDxMaL` — Bella (warm, friendly)
- `21m00Tcm4TlvDq8ikWAM` — Rachel (calm, professional)
- Or leave at default `UgBBYS2sOqTuMpoF3BR0` (already decent)

**Risk:** Low. ConversationRelay still handles all ASR/TTS. Only TTS voice changes. Existing barge-in, filler frames, booking flow untouched.

### Phase 2 — Pipecat Pipeline (2-4 weeks)

**Goal:** Full control of ASR + LLM + TTS for premium latency and quality.

Migration steps:
1. **Scaffold Pipecat app** (1-2 days): Install `pipecat-ai`, create new `voice_pipeline.py` alongside `voice_service.py`. Use `TwilioFrameSerializer` transport.
2. **Replace ConversationRelay TwiML** with Media Streams TwiML pointing to Pipecat WebSocket endpoint.
3. **Wire in Deepgram Nova-3 STT** (1 day): `DeepgramSTTService` processor.
4. **Keep Claude Haiku 4.5 LLM** (1 day): Use Pipecat's `AnthropicLLMService`. Port existing `handle_inbound` system prompt.
5. **Wire in Cartesia TTS** (1 day): `CartesiaTTSService` processor.
6. **Port barge-in logic** (1-2 days): Pipecat has native interrupt handling via `UserStartedSpeakingFrame` — simpler than the current `cancel_flag` Event.
7. **Port booking relay** (1 day): Same `/internal/voice/turn` POST via HTTP; Pipecat just calls it in its LLM processor.
8. **Migrate to Fly.io** (1-2 days): Deploy Pipecat service to Fly.io; update Render for Flask web app only.
9. **Test** (3-5 days): Full booking flow, barge-in, ASR edge cases, concurrent calls.

**Total: 2-4 weeks for a solo developer.** The existing `voice_service.py` can run in parallel; cutover is a single TwiML URL change per Twilio number.

**What you preserve:** Existing booking flow, DB writes, Flask web app, SMS relay, lead CRM, all untouched. Voice path is isolated.

### Phase 3 — Telnyx Migration (1-2 weeks, optional)

Do Phase 3 only when voice call volume exceeds ~5,000 min/month (at which point the telephony savings justify the migration effort). Swap SIP trunk and webhook endpoints from Twilio to Telnyx.

---

## 11. THE QUICK WIN — Shippable This Week

**Action:** Confirm and/or explicitly set the ElevenLabs Flash v2.5 voice via ConversationRelay.

**Step 1 (today — 10 minutes):** Call your own test number and listen. Twilio's 2026 default IS ElevenLabs Flash v2.5. If it already sounds human, you're done for now. Skip to Phase 2 planning.

**Step 2 (if robot voice is confirmed — 2 hours):** Apply the Option C code change above (2 lines in `voice_service.py`, 1 line in `config.py`), then set on Render:
```
FIRSTBACK_TTS_PROVIDER=ElevenLabs
FIRSTBACK_VOICE_TTS=EXAVITQu4vr4xnSDxMaL
```
Restart voice service. Test call. Done.

**Cost impact:** ElevenLabs Flash v2.5 via ConversationRelay adds ~$0.025-0.035/min to the Twilio bill. Against the $0.50/min charge, that's still 90%+ gross margin. The business case is obvious: better voice → lower abandonment → more bookings → more contractors paying.

**Why this matters NOW before Phase 2:**
Phase 2 (Pipecat) takes 2-4 weeks. Contractors are using this product today. A robot-sounding AI answering service loses calls. ElevenLabs Flash v2.5 sounds like a person. Ship the voice upgrade this week; ship the full pipeline upgrade next month.

---

## Source Index

All web research conducted June 30, 2026.

1. [Pipecat vs LiveKit comparison (f22labs)](https://www.f22labs.com/blogs/difference-between-livekit-vs-pipecat-voice-ai-platforms/)
2. [Bedrock vs Vertex vs LiveKit vs Pipecat — WebRTC.ventures, Mar 2026](https://webrtc.ventures/2026/03/choosing-a-voice-ai-agent-production-framework/)
3. [Building voice AI agent with Twilio + Pipecat + LangGraph, Jan 2026](https://webrtc.ventures/2026/01/building-a-voice-ai-agent-with-policy-guardrails-using-twilio-pipecat-and-langgraph/)
4. [ElevenLabs Flash v2.5 benchmarks](https://llm-stats.com/models/eleven_flash_v2_5)
5. [ElevenLabs Models documentation](https://elevenlabs.io/docs/overview/models)
6. [ElevenLabs pricing](https://elevenlabs.io/pricing/api)
7. [Cartesia Sonic pricing](https://www.cartesia.ai/pricing)
8. [Cartesia changelog 2026](https://docs.cartesia.ai/changelog/2026)
9. [Cartesia vs ElevenLabs showdown 2026 (CodeSOTA)](https://www.codesota.com/speech/elevenlabs-vs-cartesia)
10. [Inworld TTS benchmark 2026](https://inworld.ai/resources/best-voice-ai-tts-apis-for-real-time-voice-agents-2026-benchmarks)
11. [Best TTS APIs for voice agents 2026 (FutureAGI)](https://futureagi.com/blog/best-tts-providers-voice-agents-2026/)
12. [Coval TTS provider guide 2026](https://www.coval.ai/blog/best-text-to-speech-providers-in-2026-how-to-choose-(and-why-vendor-benchmarks-lie)/)
13. [Deepgram Nova-3 pricing 2026](https://brasstranscripts.com/blog/deepgram-pricing-per-minute-2025-real-time-vs-batch)
14. [Deepgram pricing page](https://deepgram.com/pricing)
15. [STT API pricing June 2026 (BuildMVPFast)](https://www.buildmvpfast.com/api-costs/transcription)
16. [AssemblyAI pricing](https://www.assemblyai.com/pricing)
17. [AssemblyAI Universal-Streaming](https://www.assemblyai.com/universal-streaming)
18. [Groq pricing June 2026 (AI Pricing Guru)](https://www.aipricing.guru/groq-pricing/)
19. [Groq pricing breakdown (TokenMix)](https://tokenmix.ai/blog/groq-api-pricing)
20. [MiniMax API pricing 2026](https://pricepertoken.com/pricing-page/provider/minimax)
21. [MiniMax M2.7 analysis (Artificial Analysis)](https://artificialanalysis.ai/models/minimax-m2-7)
22. [DeepSeek API pricing](https://api-docs.deepseek.com/quick_start/pricing)
23. [Telnyx vs Twilio voice AI 2026](https://burki.dev/blog/42-twilio-vs-telnyx-voice-ai)
24. [Telnyx voice API pricing](https://telnyx.com/pricing/voice-api)
25. [Telnyx vs Twilio SIP trunking](https://telnyx.com/resources/telnyx-vs-twilio-sip-trunking)
26. [Telnyx voice AI latency comparison 2026](https://telnyx.com/resources/voice-ai-agents-compared-latency)
27. [LiveKit SIP telephony docs](https://docs.livekit.io/telephony/)
28. [LiveKit pricing](https://livekit.com/pricing)
29. [Render vs Fly.io 2026 (BuildMVPFast)](https://www.buildmvpfast.com/compare/render-vs-fly-io)
30. [Fly.io vs Render (Northflank)](https://northflank.com/blog/flyio-vs-render)
31. [Twilio ConversationRelay TwiML docs](https://www.twilio.com/docs/voice/twiml/connect/conversationrelay)
32. [Twilio ConversationRelay voice configuration](https://www.twilio.com/docs/voice/conversationrelay/voice-configuration)
33. [ElevenLabs voices for ConversationRelay (Twilio changelog)](https://www.twilio.com/en-us/changelog/elevenlabs-voices-available-for-conversation-relay-public-beta)
34. [Voice AI latency budget (Chanl)](https://www.channel.tel/blog/voice-ai-pipeline-stt-tts-latency-budget)
35. [Voice AI latency guide (Famulor)](https://www.famulor.io/blog/ai-voice-agent-latency-how-fast-your-phone-bot-must-reply)
36. [Core latency guide for voice AI — Twilio](https://www.twilio.com/en-us/blog/developers/best-practices/guide-core-latency-ai-voice-agents)
37. [AI Voice TTS pricing June 2026 (BuildMVPFast)](https://www.buildmvpfast.com/api-costs/ai-voice)
38. [PlayHT / PlayAI Meta acquisition note (PlayHT review 2026)](https://www.buildfastwithai.com/ai-tools/playht)
39. [Rime Arcana v3 launch](https://rime.ai/resources/arcana-v3)
40. [Rime voice models on Together AI](https://www.together.ai/blog/rime-voice-models-now-available-on-together-ai)
41. [Best voice AI models May 2026 (FutureAGI)](https://futureagi.com/blog/best-voice-ai-may-2026/)
42. [Pipecat quickstart phone bot (GitHub)](https://github.com/pipecat-ai/pipecat-quickstart-phone-bot)
43. [Pipecat Twilio WebSocket integration](https://docs.pipecat.ai/pipecat/telephony/twilio-websockets)
44. [Voice agent stack selector (Hamming AI)](https://hamming.ai/resources/best-voice-agent-stack)
