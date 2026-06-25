# Red-team audit — 4 parallel sonnet agents (2026-06-25)
Goal: try to expose FirstBack. Find every bug, incorrect/overclaiming statement, gap, and
compliance/security issue. READ-ONLY audit — agents change NO app code, only write their own report.

Production: https://ringback-gixe.onrender.com (live, real Twilio acct). **Probing rule: read-only —
GET public pages + review code + run LOCAL tests only. NO real SMS/voice sends, NO load tests, NO
signups that would message anyone, NO destructive or cost-incurring actions.**

## Lanes (non-overlapping)
- [ ] **L1 Correctness & bugs** → `01-correctness-bugs.md` — logic bugs, broken/incomplete flows, error
      handling, edge cases, races, data integrity across booking/screening/reminders/billing/voice/fsm;
      run the test suites; find coverage gaps + real defects.
- [ ] **L2 Honesty & accuracy** → `02-honesty-accuracy.md` — every claim in marketing + UI vs actual
      capability; overclaiming, live-vs-gated mismatches, invented numbers/testimonials, stale/misleading
      copy, dead-end links. Hold to the project's honesty rules.
- [ ] **L3 Compliance & security** → `03-compliance-security.md` — TCPA/A2P/10DLC, consent, quiet hours,
      STOP/opt-out, FCC AI-voice disclosure, recording laws, PII/privacy; security: auth, CSRF, cross-tenant
      isolation, secrets, injection, webhook signature verification, token encryption.
- [ ] **L4 Gaps, UX & completeness** → `04-gaps-ux.md` — missing features for a contractor SaaS, incomplete
      flows, dead ends, onboarding friction, a11y, mobile, error/empty states, the password-reset gap.

Each report: prioritized findings P0 (broken/legal risk) / P1 (should-fix) / P2 (polish), each with
file:line or URL evidence + concrete fix. End with an honest severity summary. No false alarms.

## Synthesis
Orchestrator aggregates the 4 into `RED-TEAM-SYNTHESIS.md` (dedup, prioritize) and presents to owner.
No fixes applied without owner picks.
