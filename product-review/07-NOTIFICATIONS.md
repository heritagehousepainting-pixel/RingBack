# 07 — Owner Notifications & the Set-and-Forget Promise

Auditor lane: owner-facing alerts only — alerts.py, reminders.py (scans + tick_once), the daily_digest flow, stall nudges, settings toggles, channels.

---

## What the system actually does

**Channels in production:** in-app (always), SMS to `business.alert_sms`, email to `business.alert_email` (or owner login email). No push, no webhook, no app badge. Three channels total, two of which require manual config.

**Alert kinds that fire on the owner today:**

| Kind | Trigger | Toggle |
|---|---|---|
| `lead` | Every missed-call text-back | `alert_on_lead` |
| `booking` | Estimate booked | `alert_on_booking` |
| `urgent` | Flagged urgent | `alert_on_urgent` |
| `canceled` | Estimate canceled | `alert_on_booking` (shared) |
| `sms_fail` | Delivery failure after 3 attempts | `alert_on_urgent` (shared) |
| `forwarding_lost` | Forwarding health check fails | `alert_on_urgent` (shared) |
| `roi_milestone` | Product paid for itself | `alert_on_roi_milestone` — **NOT exposed in Settings UI** |
| `vic_morning` | Superseded but code still present | `alert_on_lead` |
| `vic_stall` | Warm lead idle >24h, per-lead, per-day, afternoon only | `alert_on_lead` (shared) |
| `growth_tray` | Superseded but code still present | `alert_on_lead` |
| `daily_digest` | One unified 8am SMS | `alert_on_daily_digest` |
| `tick_stale` | Scheduler gap >15m | `alert_on_urgent` — **goes to business id=1 only** |
| `screening_graduated` | Spam shield auto-promoted | `alert_on_urgent` |

**Stall-nudge volume:** `scan_stall_nudges` iterates ALL idle leads with no per-business daily cap. A contractor with 5 warm-but-cold leads gets 5 separate texts in the afternoon, one per lead, every day until each books or is dismissed. The dedupe is per (lead, local-day), not per (business, local-day).

**Quiet hours for owner:** none. QUIET_START / QUIET_END (default 8am–9pm) are applied to scheduled outbound customer texts (reminders, follow-ups, growth plays). The `alerts.notify` path calls `messaging.send_sms` with `gate=False`, bypassing the quiet-hours backstop entirely. A lead at 11pm means an SMS to the owner at 11pm.

**The daily_digest copy:**
- Only fires in the [8, 9) local window — good.
- Dedupe is per day — good (one per local day).
- Skips if n_leads == 0 AND plays_count == 0 AND no top_stall — the "all quiet" case is handled correctly.
- BUT the "all quiet" path sends nothing at all. There is no "Good morning — nothing needs you today" reassurance. The owner only hears silence, with no way to distinguish "everything is fine" from "the system is broken."
- The weekly digest email (`/tasks/digest` -> `convos.digest_email`) is a separate flow triggered by an external cron, covering AI training gaps. It does surface an ROI block and conversation count — it is the closest thing to a "wins recap" but it is focused on training gaps, not revenue wins.

**Toggle coverage:**
- Settings UI exposes: `alert_on_lead`, `alert_on_booking`, `alert_on_urgent`, `alert_on_daily_digest`.
- `alert_on_roi_milestone` lives in the DB schema and in `_TOGGLE_COL` but is absent from the Settings UI — the owner cannot turn it on or off.
- `vic_stall` and `vic_morning` share `alert_on_lead`. The owner cannot silence morning briefings or stall nudges without also silencing real-time new-lead alerts. That is a false trade-off.
- No combined "max stall texts per day" cap exists in Settings.

---

## Findings

### F1 — No quiet hours for the owner (HIGH impact / SMALL effort)

**What:** Owner SMS/email alerts fire at any hour. `messaging.send_sms(gate=False)` skips the QUIET_START / QUIET_END backstop entirely for owner-bound messages. A new lead at 11:15pm generates an SMS to the contractor's personal cell immediately.

**Why it matters:** Dave the roofer is asleep. He wakes up, checks his phone, sees "New lead: a new caller." He has nothing he can act on at 11pm. Do it twice and he turns off all alerts. The set-and-forget promise evaporates the first time it wakes him.

**Rec:** Add `alert_quiet_start` / `alert_quiet_end` business columns (default 8am–9pm) defaulting to the same window. In `alerts.notify`, before the SMS send, check local time against those hours. Any alert that hits outside the window is: (a) recorded in-app immediately (never suppressed), (b) held until morning for SMS/email. Urgency exception: `urgent`, `sms_fail`, `forwarding_lost` bypass the hold — those are fire-alarm level.

**Impact: HIGH | Effort: SMALL**

---

### F2 — Stall nudges have no per-business daily cap, creating alert fatigue (HIGH impact / SMALL effort)

**What:** `scan_stall_nudges` fires one `vic_stall` SMS per idle lead per afternoon with no aggregate cap. A contractor with 5 warm-but-cold leads (not unusual after a busy week) receives 5 texts every afternoon. The per-(lead, local-day) dedupe prevents double-sends for the same lead, but does not prevent 5 separate messages arriving in a 5-minute ticker window.

**Why it matters:** Five texts about five stalled leads is not "calmly in-control" — it is a panic pile. The owner is on a roof. They glance at their phone and see a sequence of "Maria replied 31h ago... Carlos replied 27h ago... Jim replied 25h ago." They stop reading. The alert that matters gets buried.

**Rec:** Cap `scan_stall_nudges` to a maximum of 1–2 owner SMS per business per afternoon pass, ordered by `idle_hours` descending. The rest of the stalls are surfaced in the dashboard's in-app feed and in the next day's 8am digest. Optionally add a `max_stall_alerts_per_day` setting (default 2). The already-correct per-(lead, local-day) dedupe stays in place.

**Impact: HIGH | Effort: SMALL**

---

### F3 — "All quiet" sends nothing — no system-is-working signal (MEDIUM impact / SMALL effort)

**What:** When `scan_daily_digest` finds nothing to report (no open leads, no held plays, no stalls), it silently skips. The owner receives no morning message. This is identical to the experience when: the cron is broken, Twilio is down, or the number is not set up correctly.

**Why it matters:** The set-and-forget promise requires trust. Trust requires confirmation. "I haven't heard from FirstBack in 3 days" reads as "it must be broken" not "it must be quiet." The Dave test: a non-tech contractor will call support to ask if the product is working. This is the same failure mode as a smoke detector with no green LED.

**Rec:** On quiet days, send a brief "all clear" — e.g., "Good morning. Quiet day — no leads waiting, nothing to approve. FirstBack is running." Dedupe on the same `daily_digest` day key. This can be gated on `alert_on_daily_digest` so owners who don't want morning texts don't receive it. Alternatively, a weekly "system healthy" email (no leads missed, X calls handled) satisfies this at lower SMS cost.

**Impact: MEDIUM | Effort: SMALL**

---

### F4 — ROI milestone toggle missing from Settings UI (MEDIUM impact / SMALL effort)

**What:** `alert_on_roi_milestone` is a DB column and correctly wired in `_TOGGLE_COL`, but the Settings page only shows four toggles. The owner cannot turn this off. `update_alert_prefs` in db.py also does not save it — even if the form posted it, it would be silently dropped.

**Why it matters:** The ROI milestone alert ("FirstBack paid for itself") is arguably the single highest-dopamine moment in the product lifecycle. But if it fires multiple times due to edge cases, or if the owner wants to control it, they have no lever. More practically: the db.py `update_alert_prefs` whitelist (`alert_email`, `alert_sms`, `alert_on_lead`, `alert_on_booking`, `alert_on_urgent`, `alert_on_daily_digest`) does not include `alert_on_roi_milestone` — the toggle exists in the DB schema but is unreachable from the UI AND unsaveable via the settings form.

**Rec:** Add `alert_on_roi_milestone` to the Settings UI toggle list and to the `update_alert_prefs` whitelist in db.py. Also expose in app.py's settings-save block alongside the other four toggles. Two-line fix.

**Impact: MEDIUM | Effort: SMALL**

---

### F5 — No push / app notification channel; SMS-only is a single point of failure (MEDIUM impact / LARGE effort)

**What:** The only real-time owner channel is SMS (via Twilio) and email (via SMTP). Both require external service configuration. If Twilio is unconfigured, ALL proactive alerts are in-app only — meaning the owner must open the dashboard to see them. There is no push notification, no native app badge, no webhook endpoint the owner can wire to their own tools (Slack, Zapier, etc.).

**Why it matters:** The pitch is "I forget it's even there until it books me a job." That sensation requires the notification reaching the owner where they are — their phone's lock screen. SMS works, but it creates a dependency on Twilio A2P approval and a hard setup step. Without it, the owner must babysit the dashboard. Push notifications (PWA push or a simple Twilio Notify wrapper) would deliver the same lock-screen feel with zero A2P friction and no per-SMS cost. A webhook option lets power users pipe to Slack/Teams in one URL paste.

**Rec (phased):** 
1. Short term: add a Zapier/webhook field to the Settings alerts card. Low code, zero infra. A webhook URL receives a JSON POST per alert.
2. Medium term: PWA push via the Web Push API (no native app required). Free, no Twilio dependency, works from the browser on any phone. Cover the "Twilio not configured" gap this creates.

**Impact: MEDIUM | Effort: LARGE (push), SMALL (webhook URL field)**

---

### F6 — `tick_stale` alert hardcoded to business id=1 (LOW impact / SMALL effort)

**What:** In `tick_once` (reminders.py line ~882), the stale-ticker alert calls `db.get_business(1)` — hardcoded to the first business. In a multi-tenant future, every tenant gets this alert only if they happen to be business #1.

**Why it matters:** Low impact today (single-tenant), but a quiet correctness bug that will cause confusion when a second tenant is added.

**Rec:** Iterate `db.list_businesses()` and fire `tick_stale` for each business, or use a platform-level ops notification (not a per-tenant alert). Five lines.

**Impact: LOW | Effort: SMALL**

---

## What "I forget it's even there" needs — gap summary

| Gap | Status |
|---|---|
| Lock-screen notification reaches owner in real time | Partial — only if Twilio + `alert_sms` configured |
| Owner can sleep without being woken by non-urgent alerts | Missing — no owner quiet hours |
| A busy day doesn't flood the phone | Missing — no stall-nudge cap |
| Silence means quiet, not broken | Missing — no "all clear" signal |
| Owner can see the product is earning its keep | Partial — ROI milestone fires but toggle inaccessible |
| Owner can turn individual alert types on/off granularly | Partial — vic_stall and daily_digest share `alert_on_lead` |
| Weekly wins recap | Partial — weekly digest email exists but is AI-training-gap focused, not a "you won X jobs" wins email |

---

## Top 3 moves (ordered by impact/effort ratio)

1. **Owner quiet hours** — add `alert_quiet_start` / `alert_quiet_end` to the business row; hold non-urgent SMS/email until morning. QUIET_START/QUIET_END already exist for customer texts — reuse the same pattern. (H impact / S effort)

2. **Cap stall nudges at 2 per business per afternoon** — slice `idle_leads` before the loop; lead everything with the highest `idle_hours`. Prevents alert fatigue without losing signal. (H impact / S effort)

3. **"All clear" daily digest** — when the digest has nothing to report, send a brief "Quiet day, FirstBack is running" instead of silence. Closes the trust-vs-broken ambiguity. (M impact / S effort)

---

## Verdict on the set-and-forget gap

The architecture is correct — one consolidated 8am digest, dedupe guards, async off the hot path, channel fan-out. The execution gap is three missing features: no owner quiet hours (risks alert fatigue from late-night leads), no stall-nudge cap (risks afternoon SMS pile-ons), and no "all clear" signal (silence reads as broken). Fix those three and the product earns the "I forget it's even there" claim. Right now it is a 6/10: calm on a quiet day, chaotic on a busy one.
