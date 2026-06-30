# FirstBack — Decisions (institutional memory for humans + agents)

Written-down decisions so future sessions (and automated agents) don't re-litigate settled
calls or "helpfully" suggest something already rejected. Pair this with the `[DECIDED]` notes in
`ONBOARDING_BLUEPRINT.md`. Source for the framework below: Lenny's Podcast × Amol Ezzat Sary
(Head of Growth, Anthropic) — applied to FirstBack via `PODCAST_APPLIED_PLAN.md`.

---

## PS-3 — Billing gate policy (decided; enforce when Stripe is wired)

**The Stripe subscription does NOT activate at signup.** The billing clock starts only when
BOTH are true:
1. `activation_state` has reached `voice_live` (forwarding confirmed; the AI is answering calls), AND
2. `first_call_nudge_sent = 1` (the contractor has had at least one real AI-answered call).

**Why:** the most likely pre-reputation churn catastrophe is — contractor signs up, gets
confused, voice is never confirmed live, gets charged $99, disputes it, churns, and tells their
contractor network. One such incident before any reviews exist is disproportionately damaging.
"Leave money on the table" (forgo the early charge) to protect trust and word-of-mouth.

*Status: policy only — no Stripe activation code should ship that violates this.*

---

## PS-5 — Controversial-test framework (use before shipping anything customer/contractor-facing)

Two buckets (Amol's framework). Before shipping anything that touches a contractor or their
customer, do a 2-minute pass: "Is this Bucket 1, Bucket 2, or neither?"

### Bucket 1 — RED LINE (never ship, regardless of upside)
- A **platform toll-free / shared number** anywhere a customer sees it (off-brand for a local
  contractor; undercuts premium pricing). Every customer touchpoint is the contractor's own number.
- **ISV shared A2P campaign** where the AI speaks as "FirstBack's platform" instead of as the
  contractor. Breaks product identity.
- **Auto-enrolling contractors in growth broadcasts** without explicit opt-in.
- **Starting the billing clock** before voice is confirmed live + a real call answered (see PS-3).
- **Auto-approving growth plays that reach customers** without contractor review (human-in-loop
  stays until 20+ contractors).

### Bucket 2 — YIKES, NOT A RED LINE (allowed only with a high expected return)
- Charging full price before the contractor has several AI-answered calls with booking attempts.
- Showing estimated job values as if exact in growth plays (must label "(estimated)").
- Adding onboarding friction beyond the "make it for them" steps that are already justified.

---

## PS-1 — Focus (north star)

See `focus.md`. One line: **until the first $99 invoice, the only metrics that matter are the
forwarding-confirmation rate and the calls-answered-by-AI rate.** `crm/`, the Telnyx provider,
`outlook_mail.py`, and exotic growth play types are built and gated — they do NOT get refactored
or extended until 3 contractors each have ≥1 job booked via voice. The constraint is attention,
not code.

---

## PS-4 — Decisions as agent context

When building any automation (ops brief, future strategy agent, competitive-teardown agent),
feed it the `[DECIDED]` sections of `ONBOARDING_BLUEPRINT.md` + this file, so it never suggests
something already rejected (e.g., a toll-free bridge). Keep adding decisions here as they're made.
