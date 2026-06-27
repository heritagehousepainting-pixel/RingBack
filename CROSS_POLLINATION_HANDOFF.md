# FirstBack (RingBack) — cross-pollination handoff

**Date:** 2026-06-27 · **Repo:** heritagehousepainting-pixel/firstback (Python/Flask + a FastAPI voice service) · **Deploy:** Render `firstback` (+ `ringback-voice`).

Output of an 8-agent portfolio survey (Nod, JobMagnet, TradeSourceV3, FirstBack). FirstBack is the strongest **communications/voice/consent** product in the portfolio — it should mostly **export** those. Its own gaps are **learning from outcomes** and a **real referral rail**. Below: what FirstBack should *adopt* from the others.

## What FirstBack already leads on (export to others, don't rebuild)
Missed-call text-back, AI booking + **AI voice callback** (ConversationRelay), **call screening/triage**, **consent kernel** (`consent.py`/`tc_messaging.py`/`compliance.py`), `token_crypto.py`, gated `messaging.py`, FSM provider abstraction, calendar sync, the "Vic" command-center agent.

## Proposed adoptions (prioritized)
| # | Adopt | From | Why (better / efficient / track) | Source files to study | Effort |
|---|---|---|---|---|---|
| 1 | **Conversion-learning loop** (cross-tenant, anonymized) | Nod `insights.py` | FirstBack *sends* text-backs/growth-play messages but doesn't learn **which copy actually books**. A stats engine over its message→booking outcomes would auto-improve the AI replies + growth plays and make "what works" trackable. | Nod `insights.py` (playbook/prompt_hint, cold-start gating, privacy-by-aggregate), Nod `db.*_outcomes_for_insights` | Medium |
| 2 | **Full referral rail + e-signed agreement** | Nod referral subsystem | FirstBack has a referral *growth play* (a message); Nod has a trackable referral *system*: unique intake link → homeowner confirm (vault) → reward lifecycle → e-signed DRAFT agreement snapshot. Turns FirstBack's referral play into a measurable rail. | Nod `app.py` (intake `/r/<token>`, vault `/v/<token>`), `agreements.py`, `db.py` referrals/agreements | Medium |
| 3 | **ProjectScan: photo → structured job** | TradeSourceV3 | A caller texts a photo of the problem → strict-JSON vision extracts surfaces/scope, never free-text. Richer lead notes with zero typing. | tradesourcev3 `supabase/functions/projectscan-analyze/index.ts` (strict json_schema + anti-hallucination prompt), `lib/projectscan/` | Med-Hard (needs a vision endpoint) |
| 4 | **Local-SEO/GBP + content engine** | JobMagnet `getfound.py`/`seo.py`/`google_business.py`; TradeSourceV3 `lib/seo/*` | Extends FirstBack from "capture demand" into "create demand": GBP optimization checklist, schema.org JSON-LD, programmatic local pages. | JobMagnet `getfound.py`,`seo.py`,`google_business.py`; tradesourcev3 `lib/seo/{counties,towns,schema}.ts` | Medium |
| 5 | **Notification queue + cron (vs in-process ticker)** | TradeSourceV3 | At scale, a DB-backed queue with dedup + status + fail-closed cron is more trackable/retryable than the in-process reminder ticker. | tradesourcev3 `app/api/notifications/process/route.ts`, `notification_queue` schema | Med |

## Shared-kernel note
FirstBack + JobMagnet already share **`trades_core`** (`auth.py`,`db_core.py`,`consent.py`,`llm.py`) via `python3 trades_core/sync.py`. Nod now vendors `auth.py`+`db_core.py` and has ported `consent.py`+`llm.py` patterns — coordinate so the kernel doesn't fork across three apps.

## Working conventions
Mirror the existing FirstBack discipline already evident in-repo: **simulate-until-configured** every integration; off-hot-path daemon-thread sends; confirm-before-anything-reaches-a-customer; standalone `test_*.py` harness; `[firstback]` defensive logging; consent/quiet-hours/A2P as first-class gates. Spec new work, build, self-gate (tests), then commit/push. **Push auto-deploys** `firstback` + `ringback-voice` — verify before pushing.
