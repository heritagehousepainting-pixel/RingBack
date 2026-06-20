# Final Ship-Gate Security Audit — Batches C/D/E/F/G

**Audited:** 2026-06-20  
**Auditor:** Security + correctness lane (READ-ONLY — no source files modified)  
**Scope:** `git diff 92aacde..HEAD` — 11 commits, ~6,200 lines, `.py` + new public endpoints  
**Prior audits:** batch-c-be-audit, batch-d-security-audit, batch-d-correctness-audit, batch-e-integration-audit, batch-e1-customer-book-audit, batch-e2a-milestone-audit, batch-f-audit, batch-g-audit  

---

## Verdict

**SHIP-WITH-FIXES**

No P0 blockers. Two P1 findings must be patched before owner-visible promotion to production: (1) `reputation_milestone` fires on every 28-day poll cycle instead of once, producing monthly "you have N reviews" spam with no per-event persistent guard, and (2) `POST /settings/growth_mode` mutates the TCPA growth-mode setting without a `_csrf_ok()` check (only `SameSite=Lax` stands between a cross-site POST and a mode change). Both are 1–3 line fixes. All P0-class concerns — tenant isolation, SQL injection, TCPA backstop, A2P gating, voice gate, billing gate, Twilio signature validation, ROI honesty invariants — are confirmed clean.

---

## P0 / P1 / P2 Findings

| Severity | File:line | Issue | Fix |
|---|---|---|---|
| **P1** | `alerts.py:317–357` + `reminders.py:934–937` | **`reputation_milestone` fires on every 28-day poll cycle, forever.** `_dedupe_key` has no explicit branch for `reputation_milestone`; it falls through to `f"reputation_milestone:{context.get('lead_id')}"` → `"reputation_milestone:None"`. The dedupe window is 120 s (`ALERT_DEDUPE_SECONDS`). Since `scan_google_reputation` polls every 28 days, every poll where `current - baseline >= 5` fires a new alert. There is no persistent "already fired" flag (contrast: `screening_graduated` uses `_LONG_DEDUPE_KINDS` for a year-long window; `monthly_recap` uses `db.get_meta`). An owner with 10+ reviews will get "You've added N Google reviews" once a month indefinitely. | **Option A (1 line):** Add `"reputation_milestone"` to `_LONG_DEDUPE_KINDS` in `alerts.py:44`. This gates it to once-per-business-per-year. **Option B (cleaner):** Add a `db.get_meta` / `db.set_meta` per-delta guard in `scan_google_reputation` (like `monthly_recap` does), keyed on `f"rep_milestone:{bid}:{baseline}:{current_5_bucket}"`. |
| **P1** | `app.py:1397–1412` | **`POST /settings/growth_mode` has no `_csrf_ok()` check.** The route has `@login_required` and the session cookie is `SameSite=Lax`, but `Lax` blocks cross-site navigations that trigger GETs — a cross-site HTML form POST from an attacker-controlled page still carries the cookie on most browsers when the user has recently visited the site. An owner-targeted phishing page or ad with a hidden form could silently flip `growth_mode` to `auto`, bypassing the streak gate (the streak gate is inside the same handler, but if `growth_streak_unlocked_at` is already set it allows `auto`). This is the sole TCPA-adjacent mutation endpoint without CSRF defense. Every other mutation in the codebase that touches TCPA-relevant state uses `_csrf_ok()` (e.g. `growth_tray_release:app.py:1463`, `launch_seasonal_campaign:app.py:1489`). | Add `if not _csrf_ok(): abort(403)` as the first line of `settings_growth_mode()` body, before the `biz =` line. |
| **P2** | `app.py:1190–1196` | **`api_reputation` crashes with `AttributeError` when `current_business()` returns `None`.** `@login_required` allows through a user who is authenticated but has no associated business row. `biz.get(...)` raises `AttributeError` on `None`. Pattern is fixed elsewhere: `dashboard()` (app.py:804), `customer_book()` (app.py:608) both add `if not biz: return redirect("/login")`. | Add `if not biz: return jsonify(error="no business"), 404` after `biz = current_business()`. |
| **P2** | `app.py:1483–1512` | **`launch_seasonal_campaign` does not enforce the streak gate.** The streak gate (`growth_streak_unlocked_at` check) is enforced in `settings_growth_mode` for the `auto` mode, but seasonal blast is separately accessible from the tray page without requiring `auto` mode or the streak unlock. Messages are queued as `status="held"` (still require the owner's GO tap), so there is no direct TCPA fire — but the product contract is that the seasonal blast is part of the auto-mode/streak-earned tier. | The batch-e integration audit flagged this as P2 and the fix was NOT applied. Add `if not biz.get("growth_streak_unlocked_at"): return redirect("/growth/tray?seasonal_blocked=streak_required")` before the cohort loop, or gate the seasonal card in `growth_tray.html` on `growth_streak_unlocked_at`. |
| **P2** | `reminders.py:893–940` | **`scan_google_reputation` re-fires `reputation_milestone` every poll cycle (root cause of the P1 above).** Also, the batch-e integration audit marked `reputation_milestone:None` as "harmless" because it noted the 120s window vs 28-day polls. The analysis was correct for the collision case (two simultaneous polls), but missed the repeat-fire-on-next-poll case. | Same fix as P1 above. |
| **P2** | `app.py:2859–2881` | **`twilio_voice_recording` does not check `biz.get("voicemail_enabled")`.** If an owner disables voicemail after it was active, the Twilio transcription callback URL remains registered in Twilio and will still fire, creating leads and sending SMS. The `@require_twilio_signature` guard ensures this can only come from Twilio (not an attacker), but the owner's intent is not honored. | Add `if not biz.get("voicemail_enabled"): return _twiml("<Response/>")` after `biz =` is resolved and verified non-None. |

---

## Verified-good

### 1. AUTH on all new state-changing routes

| Route | Auth | CSRF | Notes |
|---|---|---|---|
| `POST /api/leads/<id>/won` | `@login_required` | `_csrf_ok()` + 403 | Tenant-scoped via `get_lead(id, biz_id)` |
| `GET /api/reputation` | `@login_required` | — (read-only) | P2 None-biz crash noted above |
| `POST /growth/seasonal/launch` | `@login_required` | `_csrf_ok()` + 403 | |
| `POST /webhooks/widget/lead` | Public (intentional) | Rate-limit + E.164 + slug gate | A2P-gated in `send_sms` |
| `GET /api/widget/<slug>/config.js` | Public (intentional) | Read-only; reveals only biz name | |
| `GET /widget.js` | Public (intentional) | Static file serve | |
| `POST /webhooks/twilio/voice/recording` | `@require_twilio_signature` | Twilio HMAC | Confirmed at app.py:2860 |
| `POST /settings/growth_mode` | `@login_required` | **MISSING (P1)** | `SameSite=Lax` only |
| `GET /customers` (customer_book) | `@login_required` | — (read-only) | biz-None guard present |

### 2. Tenant isolation confirmed clean

- `customer_book_stats` (db.py:1460): outer `WHERE l.business_id=?` AND correlated subqueries both use `AND a.business_id=l.business_id`. The P1 from batch-e1-audit is **fixed**.
- `won_leads` (db.py:3928): `WHERE business_id=? AND won_amount IS NOT NULL`. Clean.
- `screening_monthly_stats` (db.py:3858): `WHERE business_id=? AND missed=1`. Clean.
- `set_google_reputation` (db.py:3885): `WHERE id=?` after a per-business row read. Clean.
- `record_growth_go` (db.py:3947): `WHERE id=?` on business_id. Clean.
- `recent_growth_touch_kind` (db.py:3997): `WHERE business_id=? AND kind=?`. Clean.
- `mark_lead_won` (db.py:3908): `UPDATE leads SET ... WHERE id=?`. Tenant ownership enforced at API layer via `db.get_lead(lead_id, biz["id"])` before call — 404 if cross-tenant.
- `last_lead` (db.py:1485): `WHERE business_id=?`. Clean.
- Widget slug→biz (`_biz_id_by_widget_slug`, app.py:2911): `WHERE micro_site_slug=? AND widget_enabled=1` — parameterized. Clean.
- `get_roi_milestones` (db.py:3130): `WHERE business_id=?`. Clean.
- `mark_roi_milestone` (db.py:3141): `WHERE (business_id, level)` — UNIQUE constraint prevents cross-tenant confusion.

### 3. No SQL injection in new code

- All new `db.py` functions use parameterized queries (`?` placeholders).
- `update_alert_prefs` and `update_reminder_prefs` build SET clauses from hardcoded column allowlists only — no user input reaches column names.
- `init_db` f-string `ALTER TABLE` calls use hardcoded `(_col, _ddl)` tuples — not user-controlled.
- Widget slug passed as `?` parameter in all queries. No f-string SQL in the diff.

### 4. TCPA / CONSENT / messaging.py — UNTOUCHED

- `messaging.py` has **zero diff** from `92aacde..HEAD` (confirmed: `git diff 92aacde..HEAD -- messaging.py` returns empty).
- The customer quiet-hours backstop at `messaging.py:120–134` is unchanged.
- All new `send_sms` calls in new routes (`widget_lead`, `twilio_voice_recording`) pass no `gate=` override → `gate=True` default → full A2P + TCPA check applied.
- Owner alerts still use `gate=False` (pre-existing pattern, not modified by any batch C–G commit).
- Seasonal messages queued as `status="held"` → delivered via `run_due_once` → `send_sms` with `gate=True` (reminders.py:366 uses no `gate=` override).

### 5. TCPA / voicemail is single-party

The `<Record>` element fires only in `twilio_voice_dial_status` (app.py:2848–2854), **after** the dial leg has already ended (missed call / timeout). This is a standard voicemail — caller leaving a message after a missed call. The `<Dial>` TwiML at app.py:2818–2820 has no `record=` attribute. No live conversation is being dual-recorded. Single-party consent model is intact.

### 6. Gate integrity — billing, voice, screening

- **Billing/pricing gate:** `templates/pricing.html` has only `/signup` CTAs — no `/billing/checkout` links from marketing. The `POST /billing/checkout` route exists (app.py:3213) but is `@login_required` and not linked from the marketing funnel.
- **Voice gate:** `VOICE_PUBLIC_URL` unset → `voice_configured=False` in settings render (app.py:1309); voice dispatcher path gated at app.py:3045; `settings.html` renders the voice section as unconfigured. Voice is inert.
- **Screening gate:** Default `screen_mode` starts at `"monitor"` (not `"enforce"`). The `_effective_screen_mode` guard at app.py:867 ensures no enforcement without explicit owner opt-in.
- **Voicemail gate:** `voicemail_enabled INTEGER DEFAULT 0` in migration (db.py:889). The `<Record>` TwiML block is inside `if biz.get("voicemail_enabled"):` (app.py:2844). Inert for all existing tenants until they opt in. (P2 noted: the recording endpoint doesn't re-check the flag, but this is only reachable after Twilio was given the callback URL, which only happens when the flag is true.)
- **Widget gate:** `widget_enabled INTEGER DEFAULT 0` (db.py:890). `_biz_id_by_widget_slug` requires `widget_enabled=1` (app.py:2912). Zero DB writes or SMS sends for any business that hasn't opted in.

### 7. ROI milestone progressive upgrade — correctly idempotent

- `mark_roi_milestone` uses `INSERT OR IGNORE INTO roi_milestones (business_id, level, ...)` with a `UNIQUE(business_id, level)` constraint (db.py:3141). A racing booking can never double-fire the same level.
- Back-compat: tenants with `roi_milestone_sent_at` set (pre-E2a) have `level 2` added to the fired set (roi.py:84), so they never receive a duplicate level-2 alert.
- `_fire_roi_milestone` records the milestone **before** calling `notify_async`, so a crash between db write and SMS send loses the alert (silent) but never double-fires. Correct direction for a "never spam" invariant.

### 8. SSRF guard on owner webhook URL — confirmed fixed

`alerts.py:472–494`: `_webhook_url_allowed` resolves the hostname via `socket.getaddrinfo` and rejects any IP that is `is_private`, `is_loopback`, `is_link_local`, `is_reserved`, `is_multicast`, or `is_unspecified`. The `https://` scheme is enforced. The batch-D audit P1 (SSRF risk) is confirmed **resolved**.

### 9. Widget anti-abuse — adequate for current scale

- Rate limit: 5 submissions per IP per hour per slug (`_WIDGET_RATE`, app.py:2888–2907).
- In-process dict (not Redis) is correct given `--workers 1` in `render.yaml` startCommand.
- Phone validated to E.164 before any DB write.
- CORS wildcard on a public, session-less endpoint is correct (no credential to steal).
- The P2 noted in batch-g-audit (rate counter burns a slot before slug validation) is present in current code — cosmetic, not exploitable for SMS spam.

### 10. Analytics honesty invariants hold

- `db.analytics()` additive blend (E5): new keys `confirmed_revenue`, `estimated_pipeline`, `won_n` are **additive** — existing keys (`totals`, `revenue`, `roi_multiple`, `avg_source`) are unchanged. No back-compat break.
- `revenue` (estimated) and `confirmed_revenue` (owner-entered) are separate keys — templates must not conflate them. Verified: both are distinct fields returned from the endpoint.
- `estimated_pipeline = max(0, ...)` — clamped, never negative.
- Milestone copy always says "estimated $X" with source label (`avg_label`). No "actual"/"cash"/"collected" language in `roi.py:_milestone_body`. `_LOSS_TAIL` loss-framing closes each milestone.
- Monthly recap copy uses `~$revenue` with `(estimated)` or `(based on your job value)` label (alerts.py:263–268). Honest.

### 11. Cross-batch alert merge integrity

- `monthly_recap` and `reputation_milestone` correctly inserted into `ALERT_KINDS`, `_TOGGLE_COL`, `format_message`, `_subject`.
- No key collision between any new kind and existing kinds.
- `_QUIET_BYPASS_KINDS` correctly includes scan-driven digest/recap kinds that are already time-controlled by their scanner. Reputation_milestone and roi_milestone are NOT in either bypass set — they go through the owner quiet-hours gate (correct: these are celebratory pushes, not fire-alarm level).

---

*Audit by Claude, staging branch reviewed at HEAD (`2603ee7`). Base: `92aacde`.*
