# FirstBack Voice AI — BUY-IT Track Research
**Date:** 2026-06-30 | **Author:** BUY-IT agent (Sonnet 4.6)
**Sibling track:** BUILD-IT (Pipecat/LiveKit — separate doc)
**Synthesized by:** Opus orchestrator (combines both tracks)

---

## TL;DR

- **SHIP THIS WEEK:** Set one env var on Render. ElevenLabs is already the _default_ TTS provider for Twilio ConversationRelay as of 2026 — we just need to set `FIRSTBACK_VOICE_TTS` to a real ElevenLabs voice ID. One line. No code change mandatory.
- **MANAGED PLATFORM WINNER (if we migrate):** Retell AI — 600ms end-to-end latency, ElevenLabs + Cartesia TTS, Claude support, function calling, ~$0.095–0.15/min all-in.
- **Keep Claude Haiku 4.5** as the LLM brain for now (lowest latency, already working). Test DeepSeek V4 Flash as a 15× cost reduction option in month 2.
- **Do NOT migrate yet.** The Twilio upgrade yields 80% of the quality gain in 1 day vs. 4–7 days of migration to Retell with meaningful lock-in risk.

---

## 1. Platform Comparison Table

| Platform | Voice Quality (TTS Options) | End-to-End Latency | All-In $/min (COGS) | BYO LLM | BYO Twilio # | Function Calls / Webhooks | Native White-Label | Migration Effort |
|---|---|---|---|---|---|---|---|---|
| **Twilio ConversationRelay (incumbent)** | ElevenLabs Flash 2.5 (DEFAULT), Google, Amazon Polly | ~800–1200ms (current, untuned) | ~$0.10–0.13/min | Yes (we own it) | Yes (already on Twilio) | Yes (we own all logic) | Yes (we own stack) | 0 days |
| **Retell AI** | ElevenLabs ($0.040/min), Cartesia ($0.015/min), MiniMax, Fish, OpenAI | ~600–800ms | ~$0.095–0.15/min | Yes (custom LLM endpoint) | Via SIP trunk | Yes (custom tools + webhooks) | Not native; 3rd-party wrapper needed | 4–7 days |
| **Vapi** | ElevenLabs, Cartesia, PlayHT, 11Labs, Deepgram TTS | ~500–700ms (optimized) | ~$0.12–0.22/min | Yes (any OpenAI-compatible) | Yes (BYOK Twilio) | Yes (custom webhook tools) | Not native; VapiWrap/Vapify wrappers | 3–5 days |
| **Bland AI** | Proprietary (limited external TTS) | ~800–1000ms | ~$0.11–0.14/min (bundled) | Limited (bundled LLM) | No (Bland telephony) | Yes (webhooks) | Not native | 3–5 days |
| **Telnyx Voice AI** | Bundled STT/TTS/orchestration; supports ElevenLabs via API | ~700–900ms (carrier-grade) | ~$0.06–0.09/min | Yes (hosted or external) | Via SIP trunk | Yes | Yes (carrier; full control) | 7–10 days |
| **Synthflow AI** | ElevenLabs (default); no-code builder | ~800–1200ms | ~$0.15–0.37/min (BYOK adds cost) | Limited (BYOK add-on) | Limited | Yes (no-code integrations) | No | High; poor dev fit |

---

## 2. Per-Platform Deep Dives

### 2a. Twilio ConversationRelay (Incumbent)

**What we have:** ConversationRelay ($0.07/min) + Twilio outbound voice ($0.014/min) + Claude Haiku 4.5 (BYO, ~$0.01/min). Total COGS: ~$0.094/min + potential ElevenLabs TTS overage (see note).

**Voice quality (current):** Default voice is NOW ElevenLabs (as of 2026). When `CONVERSATIONRELAY_VOICE` env var is blank, Twilio uses its own default ElevenLabs voice ID. That's likely the robot voice you're hearing — Twilio's fallback default, not a premium voice. Fix: set a specific ElevenLabs voice ID.

**Supported TTS providers** (source: [Twilio docs, June 2026](https://www.twilio.com/docs/voice/twiml/connect/conversationrelay)):
- `ElevenLabs` — **DEFAULT as of 2026** — Flash 2.5 model
- `Google` — Journey-O, Chirp3 voices
- `Amazon` — Polly Neural

**BYO LLM:** 100% — we own the WebSocket loop, we call our own LLM. No migration needed.
**Function calls/booking:** 100% — already calling our `/internal/voice/turn` webhooks.
**White-label:** 100% — we own the whole stack; no dependency on platform branding.
**BYO Twilio number:** Already on Twilio; every contractor's number routes through us.
**ElevenLabs cost via Twilio:** Not separately itemized on Twilio's pricing page. The $0.07/min ConversationRelay charge is the published rate; character-level ElevenLabs surcharges are not documented publicly. **Flag: verify with Twilio support before going to production.** Estimate: if Twilio absorbs TTS cost in the $0.07/min rate, COGS stays at ~$0.094/min; if billed separately at ~$0.05/1000 chars, add ~$0.02–0.05/min.

**Reliability:** Twilio has 99.95%+ SLA. ConversationRelay is GA. ElevenLabs integration is Public Beta as of early 2026 — stable but worth noting.

**Sources:**
- [Twilio ConversationRelay TwiML docs](https://www.twilio.com/docs/voice/twiml/connect/conversationrelay) (June 2026)
- [Twilio US Voice Pricing](https://www.twilio.com/en-us/voice/pricing/us) (June 2026)
- [Twilio ElevenLabs blog](https://www.twilio.com/en-us/blog/integrate-elevenlabs-voices-with-twilios-conversationrelay) (June 2026)
- [ElevenLabs ConversationRelay changelog](https://www.twilio.com/en-us/changelog/elevenlabs-voices-available-for-conversation-relay-public-beta) (June 2026)

---

### 2b. Retell AI

**Platform fee (voice infra):** $0.055/min
**TTS options:**
  - ElevenLabs: $0.040/min (exact parity with ElevenLabs direct)
  - Cartesia: $0.015/min (3× cheaper, still excellent quality, ~90ms first-audio latency)
  - MiniMax Speech 2.6: ~$0.015–0.025/min
  - Fish Audio: cheap, less known
  - OpenAI TTS: moderate

**STT:** Bundled (Deepgram-grade, included in $0.055/min)

**LLM:** Native support for Claude 4.5 Sonnet, Claude 4.6 Sonnet, GPT-5.x, Gemini 3.0 Flash. Custom LLM endpoint (OpenAI-compatible) also available — lets us keep our own Claude call and pay Anthropic directly.

**Telephony:** $0.015/min (US, via Retell's numbers) or BYO SIP trunk.

**All-in cost examples:**
  - Retell infra ($0.055) + Cartesia ($0.015) + Claude Haiku 4.5 via custom LLM ($0.01) + telephony ($0.015) = **~$0.095/min**
  - Retell infra ($0.055) + ElevenLabs ($0.040) + Claude Haiku 4.5 ($0.01) + telephony ($0.015) = **~$0.12/min**

**Function calling / tool use:** Yes. Custom tools defined as JSON schema; Retell calls your webhook during the conversation. Can hit our `/internal/voice/turn` equivalent directly. ([Retell function calling guide, 2026](https://www.sacesta.com/our-work/blog/complete-guide-retell-ai-function-calling-custom-tools))

**White-label:** NOT native. Retell is developer infrastructure. Multi-tenant via sub-accounts requires building your own dashboard or using a wrapper (VoiceAIWrapper, Awaz AI, Call Supplai). ([Source: Retell AI white-label overview, 2026](https://trillet.ai/blogs/retell-ai-white-label-alternative))

**BYO Twilio number:** Via SIP trunk import. Doable but requires SIP config.

**Latency:** Published ~600–800ms end-to-end (endpointing at ~700ms per Softcery calculator). Best-in-class among managed platforms. ([Source: Softcery latency benchmarks](https://softcery.com/ai-voice-agents-calculator))

**Reliability:** Strong reputation, widely used by agencies. No SLA number published publicly.

**Sources:**
- [Retell AI Pricing](https://www.retellai.com/pricing) (fetched June 2026)
- [Retell custom LLM docs](https://www.retellai.com/integrations/custom-llm) (June 2026)
- [Best LLM for Voice AI — Retell blog](https://www.retellai.com/blog/best-llm-for-voice-ai-agents) (2026)

---

### 2c. Vapi

**Platform fee:** $0.05/min
**TTS options:** ElevenLabs, Cartesia, PlayHT, Deepgram TTS, OpenAI TTS, others — fully BYOK
**STT:** Deepgram, Azure, AssemblyAI — BYOK at ~$0.01/min
**LLM:** Any OpenAI-compatible endpoint. BYOK. Claude, DeepSeek, MiniMax all work via OpenRouter or direct API.
**Telephony:** BYOK Twilio (we import our Twilio account). This is a strong fit — we keep our existing Twilio numbers.

**All-in cost examples:**
  - Vapi ($0.05) + Cartesia ($0.015) + Deepgram STT ($0.01) + DeepSeek V4 Flash LLM ($0.001) + Twilio outbound ($0.014) = **~$0.09/min** (ultra-lean)
  - Vapi ($0.05) + ElevenLabs ($0.040) + Deepgram ($0.01) + Claude Haiku ($0.01) + Twilio ($0.014) = **~$0.124/min**

**Function calling:** Yes — custom tools via webhook. Full control. Hits our booking endpoint. ([Vapi custom tools docs](https://docs.vapi.ai/tools/custom-tools))

**White-label:** NOT native. Vapi provides no branded dashboard or sub-account system. Wrappers like VapiWrap, Vapify, VoiceAIWrapper exist but add cost and complexity. For FirstBack (building own multi-tenant SaaS), this doesn't matter — we'd build our own UI anyway. ([Source: Vapi white-label alternatives, 2026](https://trillet.ai/blogs/vapi-alternative-for-agencies))

**BYO Twilio number:** YES — you import your Twilio account keys and your numbers work natively. This is Vapi's strongest advantage for our setup.

**Latency:** ~500–700ms with optimized configuration (better than Bland, similar to Retell). Endpointing default ~1450ms but configurable.

**Reliability:** Well-established, developer-first, large user base. Some users report occasional outages in community posts but generally stable.

**Sources:**
- [Vapi Pricing](https://vapi.ai/pricing) (fetched June 2026)
- [Vapi custom LLM guide](https://docs.vapi.ai/customization/custom-llm/using-your-server) (June 2026)
- [Vapi provider keys](https://docs.vapi.ai/customization/provider-keys) (June 2026)
- [Ringlyn per-minute pricing comparison](https://www.ringlyn.com/blog/ai-voice-agent-pricing-per-minute-2026/) (2026)

---

### 2d. Bland AI

**Bundled pricing:**
  - Free/Start: $0.14/min (all-in: LLM + STT + TTS + telephony)
  - Build ($299/mo): $0.12/min
  - Scale ($499/mo): $0.11/min
  - Plus $0.015 per outbound call attempt regardless of answer

**Voice quality:** Primarily proprietary TTS. Less flexible on external TTS providers than Retell/Vapi. Voice quality ceiling lower than ElevenLabs-powered platforms.

**LLM:** Bundled — limited ability to swap in Claude or custom models.

**Function calling:** Yes, via webhooks.

**BYO Twilio number:** No — Bland provides its own telephony. Migrating away from your Twilio numbers requires coordination.

**Latency:** ~800–1000ms (higher than Retell/Vapi). Published benchmarks: 800ms average.

**White-label:** Not native.

**Verdict for FirstBack:** Not a strong fit. Higher latency, locked telephony, proprietary voice (vs. ElevenLabs option elsewhere), and the bundled-LLM model removes our ability to use Claude as our reasoning engine.

**Sources:**
- [Bland AI Pricing docs](https://docs.bland.ai/platform/billing) (June 2026)
- [Bland AI pricing breakdown](https://www.cloudtalk.io/blog/bland-ai-pricing/) (2026)
- [Bland AI vs Retell vs Vapi latency comparison](https://ainora.lt/blog/retell-ai-vs-bland-ai-vs-vapi-comparison-2026)

---

### 2e. Telnyx Voice AI

**Why worth mentioning:** Telnyx is a licensed carrier, not just a platform. They own their network infrastructure, which is a meaningful latency + reliability advantage.

**Pricing:** $0.05/min base (STT + TTS + orchestration bundled). Telephony: $0.004/min. LLM: additional if using hosted models (Qwen3-235B at $0.0006/1K tokens; GPT-4o at $0.0025/1K tokens). External LLM (Claude via our own API key): ~$0.01/min.

**All-in estimate:** Telnyx ($0.05) + telephony ($0.004) + Claude Haiku ($0.01) = **~$0.064/min** — cheapest managed option by far.

**TTS:** Bundled. Supports external ElevenLabs via their TTS API ($0.002/1K chars), which is actually cheaper than ElevenLabs direct.

**Function calling:** Yes.

**BYO number:** Via SIP trunk — they're a carrier, so SIP integration is their strength.

**White-label:** Yes — as a carrier, you have full control. No Telnyx branding forced.

**Migration effort:** HIGH — 7–10 days. SIP integration is complex. WebSocket protocol differs from ConversationRelay. Significant rewrite of voice_service.py.

**Latency:** ~700–900ms (carrier-grade routing helps but not benchmarked publicly).

**Verdict:** Most cost-effective long-term (~$0.064/min), but highest migration cost. Consider after Retell validation.

**Sources:**
- [Telnyx Conversational AI Pricing](https://telnyx.com/pricing/conversational-ai) (June 2026)
- [Telnyx CloudTalk pricing guide](https://www.cloudtalk.io/telnyx-pricing/) (2026)
- [MiniMax vs ElevenLabs benchmarks on Telnyx](https://telnyx.com/resources/minimax-speech-2-6-vs-elevenlabs-tts-benchmarks) (2026)

---

### 2f. Synthflow AI (SKIP)

**Verdict:** No-code platform optimized for non-technical users. Loses flexibility vs. Retell/Vapi. BYOK model makes true costs $0.15–0.37/min. No strong fit for a dev-first product like FirstBack. Skip.

---

## 3. The LLM Brain Question

| LLM | Pricing (input/output per M tokens) | $/min for voice (est.) | Latency (TTFT) | Quality for booking | Available on which platforms |
|---|---|---|---|---|---|
| **Claude Haiku 4.5** (current) | $1 / $5 | ~$0.01/min | Fastest Claude | Excellent | All (BYO on Vapi/Retell; we own on Twilio) |
| **Claude Sonnet 4.6** | $3 / $15 | ~$0.05–0.06/min | Fast | Best quality | All (BYO or Retell native) |
| **DeepSeek V4 Flash** | $0.14 / $0.28 | ~$0.001/min | Moderate (verify latency from US servers) | Good for structured booking | Vapi (custom LLM), Retell (custom LLM) |
| **MiniMax M3** (LLM) | $0.60 / $2.40 | ~$0.004/min | Moderate | Good | Vapi (custom LLM) |
| **GPT-4.1 mini** | ~$0.40 / $1.60 | ~$0.003/min | Fast | Very Good | Retell native, Vapi |

**Recommendation:** Keep Claude Haiku 4.5 for launch — fastest TTFT, proven in our stack, excellent at booking conversations, $0.01/min is negligible. Test DeepSeek V4 Flash as a Phase 2 cost-reduction experiment via Vapi/Retell custom LLM endpoint. The 15× cost reduction ($0.001 vs. $0.01/min) matters only if you're doing huge call volume; at $20/mo contractor cap it's immaterial.

**MiniMax as TTS (separate from LLM):** MiniMax Speech 2.6 Turbo offers <250ms first-audio latency at ~$0.015/min via Retell. Good alternative to Cartesia if you want variety. Quality: "structured clarity" — good for scheduling assistants.

**Sources:**
- [Claude Haiku 4.5 pricing](https://www.anthropic.com/claude/haiku) (June 2026)
- [Claude API pricing page](https://platform.claude.com/docs/en/about-claude/pricing) (June 2026)
- [LLM API pricing comparison 2026](https://www.morphllm.com/llm-api) (June 2026)
- [Best LLM for voice agents — Retell blog](https://www.retellai.com/blog/best-llm-for-voice-ai-agents) (2026)
- [Cartesia vs ElevenLabs vs MiniMax comparison](https://www.famulor.io/blog/cartesia-sonic-elevenlabs-and-minimax-the-ultimate-comparison-for-ai-voice-agents-and-famulors-strategic-advantage) (2026)
- [MiniMax Speech 2.6 vs ElevenLabs benchmarks](https://telnyx.com/resources/minimax-speech-2-6-vs-elevenlabs-tts-benchmarks) (2026)

---

## 4. THE QUICK WIN — ConversationRelay ElevenLabs Upgrade

**This ships TODAY. No code deployment required for minimum viable upgrade.**

### Why it works without code changes

Looking at `voice_service.py` `build_twiml()`:
```python
voice_attr = f' voice="{_xesc(CONVERSATIONRELAY_VOICE)}"' if CONVERSATIONRELAY_VOICE else ""
```
And `config.py` line 289:
```python
CONVERSATIONRELAY_VOICE = os.environ.get("FIRSTBACK_VOICE_TTS", "")
```

The Twilio `<ConversationRelay>` `ttsProvider` attribute **defaults to `"ElevenLabs"` as of 2026** (confirmed from Twilio TwiML docs). So currently we're already on ElevenLabs — but with Twilio's default voice ID, which is whatever Twilio auto-assigns (probably the "generic" voice you're hearing).

### Step 1: Set the env var on Render (ships immediately)

```bash
# Render dashboard > Voice Service > Environment
FIRSTBACK_VOICE_TTS=ZF6FPAbjXT4488VcRRnw
```

**Voice: Amelia** — young British English woman, expressive and enthusiastic (shown in Twilio's official ElevenLabs tutorial). Good for a scheduling assistant: clear, warm, not robotic.

**Alternative voice IDs to test:**
- `21m00Tcm4TlvDq8ikWAM` — Rachel (American English female, warm, professional — ElevenLabs flagship)
- `pqHfZKP75CvOlQylNhV4` — Bill (American English male, calm, reliable)
- `9BWtsMINqrJLrRacOk9x` — Aria (American English female, upbeat, helpful)
- Browse: https://elevenlabs.io/voice-library (filter: English, Professional)

### Step 2: Optional (recommended) explicit ttsProvider in build_twiml()

Since the default is already ElevenLabs, Step 1 alone may be sufficient. But for explicit safety (in case Twilio changes the default), add `ttsProvider="ElevenLabs"` to the TwiML. This requires ONE code change in `voice_service.py`:

**File:** `/Users/jack/ops/firstback/voice_service.py`
**Function:** `build_twiml()` around line 244

Current:
```python
voice_attr = f' voice="{_xesc(CONVERSATIONRELAY_VOICE)}"' if CONVERSATIONRELAY_VOICE else ""
return (
    '<?xml version="1.0" encoding="UTF-8"?>'
    '<Response><Connect>'
    f'<ConversationRelay url="{_xesc(ws_url)}"{voice_attr} '
    f'welcomeGreeting="{_xesc(greeting)}">'
```

Change to:
```python
voice_attr = f' voice="{_xesc(CONVERSATIONRELAY_VOICE)}"' if CONVERSATIONRELAY_VOICE else ""
tts_provider_attr = ' ttsProvider="ElevenLabs"'
return (
    '<?xml version="1.0" encoding="UTF-8"?>'
    '<Response><Connect>'
    f'<ConversationRelay url="{_xesc(ws_url)}"{tts_provider_attr}{voice_attr} '
    'elevenlabsTextNormalization="on" '
    f'welcomeGreeting="{_xesc(greeting)}">'
```

The `elevenlabsTextNormalization="on"` attribute enables ElevenLabs' text normalization (improves pronunciation of phone numbers, addresses, dollar amounts — exactly what a contractor scheduling call needs).

### Step 3: Optional model pin (for production stability)

ElevenLabs Flash 2.5 is the default. To pin explicitly, append model to voice ID in the format `{VoiceID}-flash_v2_5`:
```
FIRSTBACK_VOICE_TTS=ZF6FPAbjXT4488VcRRnw-flash_v2_5
```

### Result

The resulting TwiML becomes:
```xml
<ConversationRelay url="wss://your-voice-service/ws?biz=1&lead=42"
  ttsProvider="ElevenLabs"
  voice="ZF6FPAbjXT4488VcRRnw"
  elevenlabsTextNormalization="on"
  welcomeGreeting="Hi, this is the scheduling assistant for ABC Painting. ...">
  <Parameter name="biz" value="1"/>
  <Parameter name="lead" value="42"/>
</ConversationRelay>
```

All booking logic, barge-in, filler frames, streaming tokens, turn logs, recovery SMS — **100% unchanged**.

**Sources:**
- [Twilio ConversationRelay voice config docs](https://www.twilio.com/docs/voice/conversationrelay/voice-configuration) (fetched June 2026)
- [Twilio TwiML ConversationRelay reference](https://www.twilio.com/docs/voice/twiml/connect/conversationrelay) (fetched June 2026)
- [Twilio ElevenLabs integration blog](https://www.twilio.com/en-us/blog/integrate-elevenlabs-voices-with-twilios-conversationrelay) (June 2026)

---

## 5. All-In Cost Per Minute Table

All costs in USD/min. LLM column assumes Claude Haiku 4.5 at $0.01/min (BYO). "Retail" = what we charge contractors ($0.50/min current, maps to $20/mo cap ÷ ~40 min).

| Platform | Platform/Infra | STT | TTS (ElevenLabs) | TTS (Cartesia) | LLM (Haiku) | Telephony | **All-in (ElevenLabs)** | **All-in (Cartesia)** | Margin vs. $0.50 retail |
|---|---|---|---|---|---|---|---|---|---|
| **Twilio ConvRelay + ElevenLabs** | $0.070 | bundled | ~TBD* | N/A | $0.010 | $0.014 | **~$0.094–0.13*** | — | ~74–81% |
| **Retell AI** | $0.055 | bundled | $0.040 | $0.015 | $0.010 | $0.015 | **~$0.12** | **~$0.095** | 76–81% |
| **Vapi (BYO Twilio)** | $0.050 | $0.010 | $0.040 | $0.015 | $0.010 | $0.014 | **~$0.124** | **~$0.099** | 75–80% |
| **Bland AI (Scale)** | $0.110 | bundled | — | — | bundled | bundled | **~$0.11** | N/A | 78% |
| **Telnyx Voice AI** | $0.050 | bundled | $0.020† | — | $0.010 | $0.004 | **~$0.084†** | **~$0.064** | 83–87% |

*Twilio ElevenLabs TTS surcharge not publicly documented. $0.094 assumes bundled in $0.07/min; $0.13 assumes $0.03–0.05/min additional. **Verify with Twilio support before scaling.**
†Telnyx ElevenLabs pricing via their TTS API at $0.002/1K chars ≈ $0.02/min.

**Key insight:** Current COGS at $0.094–0.13/min vs. $0.50/min retail = 74–81% gross margin. The $20/mo cap is conservative — even at $0.13/min COGS, a contractor could absorb ~150 minutes/mo before hitting cap. Most solo contractors won't come close to 150 min/mo on AI callback calls.

**Sources:**
- [Ringlyn per-minute pricing 2026](https://www.ringlyn.com/blog/ai-voice-agent-pricing-per-minute-2026/) (2026)
- [Softcery AI cost calculator](https://softcery.com/ai-voice-agents-calculator) (2026)
- [Famulor AI voice pricing comparison](https://www.famulor.io/blog/ai-voice-agent-pricing-2026-what-10-platforms-actually-cost-per-minute) (2026)
- [Retell AI cost breakdown](https://www.cekura.ai/blogs/retell-ai-pricing-per-minute) (2026)

---

## 6. Migration Effort Table

| Platform | Effort | Timeline | Lock-In Risk | Booking Logic | Notes |
|---|---|---|---|---|---|
| **Twilio (ElevenLabs upgrade)** | Trivial | 1 day | None | 100% intact | Env var + 1 optional code line |
| **Retell AI** | Medium | 4–7 days | Medium | Rewrite as custom tool webhooks | SIP trunk for existing Twilio numbers |
| **Vapi** | Medium | 3–5 days | Medium | Rewrite as custom webhook tools | BYO Twilio numbers easiest |
| **Bland AI** | Medium | 3–5 days | HIGH (proprietary telephony) | Rewrite webhooks | No Twilio import |
| **Telnyx** | High | 7–10 days | Low (carrier) | Full rewrite | SIP + new protocol layer |

**Migration to Retell/Vapi means rewriting the WebSocket loop in voice_service.py.** Our current architecture (FastAPI WS → token stream → booking webhook) maps reasonably to Retell's custom LLM endpoint or Vapi's custom tool + custom LLM model. The booking logic itself (`/internal/voice/turn`) is unchanged on our web app — only the voice WebSocket client changes.

---

## 7. Platform Rankings for FirstBack

**Criteria:** voice quality, latency, cost, booking webhook support, number portability, migration risk, white-label.

| Rank | Platform | Why |
|---|---|---|
| **#1 (SHIP NOW)** | **Twilio ConversationRelay + ElevenLabs** | Zero migration, keep all logic, ElevenLabs default already enabled — just set the voice ID. Best risk-adjusted outcome for "ship this week." |
| **#2 (MIGRATE TO IF #1 UNSATISFACTORY)** | **Retell AI + Cartesia or ElevenLabs** | Best managed latency (600ms), clean custom LLM + tool webhook model, ElevenLabs or Cartesia TTS, Claude Haiku native. 4–7 day migration. |
| **#3** | **Vapi** | More flexible (BYOK everything, BYOK Twilio numbers), but no native white-label and higher all-in cost with ElevenLabs. Good if you need maximum LLM control across providers. |
| **#4** | **Telnyx** | Cheapest ($0.064/min) but 7–10 day migration. Worth revisiting at scale. |
| **#5** | **Bland AI** | Pass: locked telephony, proprietary TTS, bundled LLM, higher latency. |
| **#6** | **Synthflow** | Pass: no-code platform, wrong fit for dev-first product. |

---

## 8. Open Questions / Verify Before Scaling

1. **Twilio ElevenLabs TTS surcharge:** Is ElevenLabs TTS charged per-character on top of $0.07/min ConversationRelay, or is it bundled? Twilio's public pricing page does not clarify. Email support@twilio.com or check Twilio console billing after a test call. This is the only material unknown for the quick win.

2. **Retell SIP trunk for existing Twilio numbers:** Retell can import Twilio numbers via SIP — confirm exact porting steps with Retell support before committing to migration.

3. **DeepSeek V4 Flash latency from US:** DeepSeek's servers may introduce higher TTFT from US East. Test via OpenRouter (which has US-based inference for DeepSeek) before switching.

4. **ElevenLabs Flash 2.5 vs. Turbo v2.5 on ConversationRelay:** Flash 2.5 is the default (lowest latency). Turbo v2.5 is slightly higher quality. For a booking call, Flash 2.5 is the right choice.

---

*All prices sourced from live web research conducted June 30, 2026. Voice AI pricing changes monthly — re-verify before contract commitments.*
