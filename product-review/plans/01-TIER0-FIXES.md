# Plan: Tier-0 Critical Bug + Honesty Fixes
**Workstream:** Tier-0 (launch-critical, pre-customer) — all 9 items in this plan.
**Author:** Planning Agent 01
**Date:** 2026-06-19
**Source reports:** 00-SYNTHESIS.md Tier 0, 01-ONBOARDING.md, 09-ROI-PROOF.md, 10-MARKETING-SITE.md

---

## Ordering rationale
Quick-wins first; riskiest last. Items 1–4 are pure template/JS edits with zero shared-code risk. Items 5–7 touch messaging and DB logic. Items 8–9 involve backend wiring and DB schema.

---

## Fix 1 — Voice says "We just sent you a text" when SMS was blocked (A2P wait window)

### What + why
During the 1–3 day A2P approval wait, `messaging.send_sms()` returns `{"status": "blocked"}`. The caller hears "Sorry we missed you. We just sent you a text message. Goodbye." but no text was sent. It is a live false promise to every first caller.

### Exact location
**`app.py` lines 2649–2653** (`twilio_voice_inbound`) and **lines 2665–2669** (`twilio_voice_dial_status`):
```python
# current (both call-paths):
return _twiml("<Response><Say>Sorry we missed you. We just sent you a text "
              "message. Goodbye.</Say><Hangup/></Response>")
```

**`app.py` lines 2617–2620** (`_missed_call_textback`):
```python
# current (does NOT check send_sms return value):
if not db.get_messages(lead["id"]):
    reply = open_conversation(biz, lead)
    messaging.send_sms(biz, caller, reply)  # return value discarded
return True
```

### Concrete approach
Step 1 — Capture the send result in `_missed_call_textback` and return it:

```python
# app.py _missed_call_textback, replace the block at ~line 2617-2620:
sent = "blocked"
if not db.get_messages(lead["id"]):
    reply = open_conversation(biz, lead)
    result = messaging.send_sms(biz, caller, reply)
    sent = (result or {}).get("status", "sent")
return sent != "blocked"   # False when blocked; True when sent/simulated
```

Step 2 — Change the TwiML voice copy in BOTH call-paths when not engaged:
- `twilio_voice_inbound` (lines 2649–2654): `_missed_call_textback` already returns a boolean (`engaged`). The current `if engaged:` check is correct. But `_missed_call_textback` returns `True` even when the send was blocked (because the thread is non-empty on repeat calls). The fix in Step 1 already narrows `True` to "a text actually went/was scheduled to go out," so the existing voice-path logic becomes honest.
- However, on the FIRST call during the A2P wait, `_missed_call_textback` will now return `False` (blocked), so the voice will `<Hangup/>` silently — that is better than the lie, but still cold. Add an honest fallback voice message:

```python
# Replace in twilio_voice_inbound (~line 2649) and twilio_voice_dial_status (~line 2664):
engaged = _missed_call_textback(biz, request.form.get("From", ""),
                                call_sid, "no-forward")
if engaged:
    return _twiml("<Response><Say>Sorry we missed you. We just sent you a text "
                  "message. Goodbye.</Say><Hangup/></Response>")
# A2P not yet approved — honest fallback (no text went out)
return _twiml("<Response><Say>Sorry we missed you. We will be in touch "
              "soon. Goodbye.</Say><Hangup/></Response>")
```

> Note: The fallback fires for *screened-out* callers too (already the case). For A2P-blocked sends this is newly honest. Consider a separate `is_blocked` return signal if you need to distinguish the two cases in a follow-up pass.

### Tests to add
File: `test_voice_app.py` (standalone).

```python
# test: _missed_call_textback returns False when send_sms returns blocked
# test: twilio_voice_inbound TwiML says "will be in touch soon" when engaged=False (covers both blocked + screened)
# test: twilio_voice_inbound TwiML says "just sent you a text" when engaged=True
# test: twilio_voice_dial_status same two cases
```
Run: `.venv/bin/python test_voice_app.py`

### Effort: S (2–3 hours)
### Risk: LOW
- `_missed_call_textback` is called from two routes only; both are covered by existing `test_voice_app.py`.
- Return type change (bool → bool, same semantics) but narrower true-set. No shared-code side-effects. The existing "simulated" path (`send_sms` returns `{"status": "simulated"}`) is treated as non-blocked, so demo mode stays functional.
- **Collision risk:** none — `_missed_call_textback` is not called from anywhere else.

---

## Fix 2 — EIN field hard-`required` in wizard blocks every sole-prop signup

### What + why
`templates/setup.html` line 83 has `required=true` on the EIN field. The backend (`connections._profile_done`) already exempts `sole_prop` businesses from needing an EIN. But every new user is tagged `sole_prop` at signup (the `has_ein` checkbox doesn't exist in `auth.html`). The browser HTML5 validator blocks form submission for any user who doesn't type an EIN — which is every new painter. This is the single highest drop-off point.

### Exact location
**`templates/setup.html` line 83:**
```jinja
{{ field('EIN (business tax ID)', name='ein', ..., required=true, help='...') }}
```

**`auth.html` line 86–93:** the signup `<form>` has no `has_ein` checkbox and no `phone` field.

**`app.py` line 344:** `has_ein = bool(request.form.get("has_ein"))` — correctly reads it, but the form never sends it.

### Concrete approach

**Part A — Remove the browser-enforced `required` on EIN (1 line):**
```jinja
{# setup.html line 83 — remove required=true, change help text: #}
{{ field('EIN (business tax ID)', name='ein', value=business.ein or '',
         placeholder='12-3456789',
         help='Sole proprietors can skip this — we register with your name and address. LLC or corporation? Enter your EIN here.') }}
```

**Part B — Add `has_ein` checkbox to auth.html signup form** (so `business_type` is set correctly from the start, not always defaulting to `sole_prop`):
```jinja
{# auth.html, after the password field and before the submit button (is_signup block): #}
{% if is_signup %}
<label class="au-check">
  <input type="checkbox" name="has_ein" value="1">
  I have an EIN (business tax ID) — my business is an LLC or corporation
</label>
{% endif %}
```
This already wires up: `app.py` line 344 already reads `has_ein` from the form.

**Optionally (follow-up, not Tier 0):** make the EIN field conditionally `required` in the wizard via JS based on `business.business_type`. But removing `required=true` is the immediate fix — the backend already handles validation correctly.

### Tests to add
File: `test_setup.py` (standalone):
```python
# test: GET /setup with sole_prop business shows EIN field without required attribute
# test: POST /setup/profile without EIN succeeds for sole_prop
# test: POST /setup/profile without EIN fails (400 or redirect with err) for llc
# test: POST /signup with has_ein=1 sets business_type='llc'
# test: POST /signup without has_ein sets business_type='sole_prop'
```
Run: `.venv/bin/python test_setup.py`

### Effort: S (1–2 hours)
### Risk: LOW
- Template-only change for the EIN fix. The backend validation already handles the sole_prop exemption.
- Adding `has_ein` to auth.html aligns the form with code that already reads it (`app.py` line 344).
- **Collision risk:** `templates/setup.html` and `templates/auth.html` — two shared templates. Verify no other route POSTs to `/setup/profile` or `/signup` with an assumption that `has_ein` is absent.

---

## Fix 3 — Hero phone input submits via GET; signup never reads it → `alert_sms` blank

### What + why
`onboarding.html` line 79: `<form class="ob-search" action="/signup" method="get">` — the phone field is sent as a GET query param. `app.py` line 333 reads `phone` from `request.form` (POST body only). The phone is silently dropped. `alert_sms` stays blank, so the owner never gets SMS alerts on their first lead. Every new user is affected.

### Exact location
**`templates/onboarding.html` line 79:**
```html
<form class="ob-search" action="/signup" method="get">
```

**`templates/auth.html` line 86–93:** signup form has no phone input and no pre-population of GET param.

**`app.py` line 333:**
```python
signup_phone = (request.form.get("phone") or "").strip()
```

### Concrete approach

**Option A (simplest — read GET param in backend):** Change `app.py` line 333 to also check query args:
```python
signup_phone = (request.form.get("phone") or request.args.get("phone") or "").strip()
```
This works because the GET form action passes `?phone=...` in the URL, and Flask makes `request.args` available even on POST routes when the URL carries the param. **But** the signup form (`auth.html`) currently submits as POST to `/signup`, so the phone from onboarding's GET form won't survive the form redirect into the POST signup.

**Option B (correct — wire it through auth.html as hidden field):**
1. `onboarding.html`: leave the form as `method="get"` and `action="/signup"`.
2. `auth.html` signup block: add a hidden field pre-populated from the GET param:
```jinja
{# auth.html, inside the is_signup form, before submit: #}
{% if is_signup %}
<input type="hidden" name="phone" value="{{ request.args.get('phone', '') | e }}">
{% endif %}
```
3. `app.py` line 333 stays as-is (`request.form.get("phone")`).

Option B is cleaner: the phone travels GET → rendered in hidden field → POSTed with signup form. The user flow is: onboarding CTA (GET /signup?phone=555...) → auth.html renders with the hidden phone → user submits signup POST → backend reads phone from form body.

### Tests to add
File: `test_sf8_signup_fork.py` (or new `test_phone_wire.py`, standalone):
```python
# test: POST /signup with phone in form body sets alert_sms on the new business
# test: GET /signup?phone=5551234567 renders auth.html with hidden phone field populated
# test: full round-trip: GET /signup?phone=... -> POST /signup -> business.alert_sms is set
```
Run: `.venv/bin/python test_phone_wire.py`

### Effort: S (1–2 hours)
### Risk: LOW
- `auth.html` template change is the only write. `app.py` line 333 unchanged.
- Only the signup path reads `phone` from the form; no other route is affected.
- **Collision risk:** none.

---

## Fix 4 — `$null/job` on Est. revenue tile when avg_job_value is unset

### What + why
`static/app.js` line 544–546:
```js
tile(hasRev ? money(t.revenue) : "—", "Est. revenue recovered",
     hasRev ? "at " + money(d.avg_job_value) + "/job" : "Set avg job value in Settings",
     hasRev ? "good" : "");
```
`d.avg_job_value` is `owner_avg` from `db.analytics()` line 3034. When the owner hasn't set their own value, `owner_avg` is `null` (not the industry default). So `money(null)` renders as `"$null"` or `"$NaN"`. The `avg_source` field is also returned from the API (`"industry_default"` or `"owner"`) but never read in JS.

### Exact location
**`static/app.js` lines 538–547** (`renderTiles` function).
**`db.py` line 3034:** `"avg_job_value": owner_avg` (null when not owner-set).
The API endpoint that returns this data: find via `grep -n "api.*analytics\|/api/analytics" app.py` — it passes both `avg_job_value` and `avg_source` in the response.

### Concrete approach
Replace the `tile(...)` call for "Est. revenue recovered" in `renderTiles`:

```js
// static/app.js, replace lines 544-546:
const jobSub = d.avg_source === "owner"
  ? "at " + money(d.avg_job_value) + "/job"
  : "industry avg — set yours in Settings";
tile(hasRev ? money(t.revenue) : "—", "Est. revenue recovered",
     hasRev ? jobSub : "Set avg job value in Settings",
     hasRev ? "good" : "");
```

This eliminates `money(null)` when source is industry default, and surfaces a nudge to improve accuracy.

### Tests to add
File: `test_f12_analytics.py` (standalone — already exists, add test cases):
```python
# test: renderTiles API response with avg_source='industry_default' has avg_job_value=null
# test: renderTiles API response with avg_source='owner' has avg_job_value=<number>
```
For the JS itself, write a minimal Node.js or browser test if the test suite runs JS, otherwise cover via an integration test that hits `/api/analytics` and checks response shape.

Run: `.venv/bin/python test_f12_analytics.py`

### Effort: S (1 hour)
### Risk: LOW
- Pure JS change in one function. `db.analytics()` already returns `avg_source`.
- **Collision risk:** `static/app.js` is a shared file used across the app. The change is inside `renderTiles()` only. No other call sites.

---

## Fix 5 — "See it live" CTA → `@login_required` wall; public `/demo` exists but unlinked

### What + why
`templates/landing.html` line 15 and `templates/product.html` line 18 both point to `/simulator`, which is `@login_required` (app.py line 615). A public `/demo` route exists (app.py line 680, no auth required). The public demo works but nothing on the marketing site links to it. A visitor who clicks "See it live" hits a login redirect at peak intent.

### Exact location
**`templates/landing.html` line 15:**
```html
<a class="ob-btn ob-btn-accent ob-btn-lg" href="/simulator">See it live...
```

**`templates/product.html` line 18:**
```html
<a class="ob-btn ob-btn-light ob-btn-lg" href="/simulator">See the live demo</a>
```
**`templates/product.html` line 47:**
```html
<a class="mk-textlink" href="/simulator">See it screen a call →</a>
```

**`templates/onboarding.html` line 37** (nav dropdown):
```html
<a class="ob-dditem" href="/simulator" ...>Live demo</a>
```

**`templates/marketing_base.html` lines 36 and 96** (nav and footer):
```html
href="/simulator"  (two instances)
```

### Concrete approach
Swap `/simulator` → `/demo` in every marketing-facing template. The logged-in app shell (app_shell.html) and dashboard links can stay at `/simulator` — those users are already authenticated.

Files and changes:
1. `templates/landing.html` line 15: `href="/simulator"` → `href="/demo"`
2. `templates/product.html` lines 18 and 47: both `href="/simulator"` → `href="/demo"`
3. `templates/onboarding.html` line 37 (nav dropdown): `href="/simulator"` → `href="/demo"`
4. `templates/marketing_base.html` lines 36 and 96: `href="/simulator"` → `href="/demo"`

Do NOT change:
- `templates/app_shell.html` line 55 (logged-in nav)
- `templates/base.html` line 26 (logged-in base nav)
- `templates/dashboard.html` lines 15 and 69 (logged-in dashboard)

### Tests to add
File: `test_demo_public.py` (standalone — already exists):
```python
# test: GET /demo returns 200 without session cookie
# test: GET /demo returns 200 with a landing=... referrer
```
Add to existing test or new file:
```python
# test: landing.html rendered HTML does not contain href="/simulator" for the hero CTA
# test: landing.html rendered HTML contains href="/demo" for the hero CTA
```
Run: `.venv/bin/python test_demo_public.py`

### Effort: S (30 minutes)
### Risk: LOW
- Template-only. No Python logic changed.
- **Collision risk:** `marketing_base.html` is inherited by all marketing pages. Verify the nav dropdown change renders correctly on `/product`, `/pricing`, `/solutions`, `/company`.

---

## Fix 6 — Auth page 5-star self-review block

### What + why
`templates/auth.html` lines 31–35 render five filled-star SVGs with `aria-label="5 out of 5"` and a quote attributed to `-- FirstBack`. This is a dark pattern: the star widget convention is third-party social proof. A prospect making their final yes/no decision on the signup screen sees what reads as a customer review. It is neither deceptive in intent nor compliant with the "no spin" honesty rule in practice.

### Exact location
**`templates/auth.html` lines 31–35:**
```html
<div class="au-proof">
  <span class="au-stars" aria-label="5 out of 5">{{ star }}...{{ star }}</span>
  <p class="au-quote">Catch every missed call, book the job, and never chase a lead by hand again.</p>
  <p class="au-by">-- FirstBack</p>
</div>
```

### Concrete approach
Replace the star block with a plain product truth statement that requires no third-party attribution:

```jinja
{# auth.html: replace the au-proof div (lines 31-35) with: #}
<div class="au-proof">
  <p class="au-quote">Up and running in a day. Flat rate. No contracts.</p>
</div>
```

Remove the `{% set star %}...{% endset %}` Jinja macro at line 6 if it's only used in this block (verify with `grep -n "star" templates/auth.html` — the macro is currently set on line 6 and used only in lines 32–32).

When a real customer testimonial is available: restore the `au-proof` block with the quote, a real name/trade/city, and omit the star widget until there are enough ratings to aggregate honestly.

### Tests to add
File: `test_auth_reset.py` or new `test_auth_honesty.py` (standalone):
```python
# test: GET /signup rendered HTML does not contain aria-label="5 out of 5"
# test: GET /login rendered HTML does not contain aria-label="5 out of 5"
# test: GET /signup contains "au-proof" div without star SVGs
```
Run: `.venv/bin/python test_auth_honesty.py`

### Effort: S (30 minutes)
### Risk: LOW
- Single template, one block removed.
- **Collision risk:** none.

---

## Fix 7 — `solutions.html` "live AI voice" with no "coming soon" hedge

### What + why
`templates/solutions.html` line 32 states: "FirstBack answers every missed call by text or a **live AI voice** and books the work while you're on the tools." This is present-tense product claim. Every other page that mentions voice is correctly hedged ("coming soon," "beta — not yet available"). The solutions page contradicts the product's own honesty standard and will cause expectation mismatch for contractors who sign up expecting voice.

### Exact location
**`templates/solutions.html` line 32:**
```html
<p class="mk-lead">Whatever you install, repair, or build — if your business lives off the phone, FirstBack answers every missed call by text or a live AI voice and books the work while you're on the tools.</p>
```

### Concrete approach
```jinja
{# solutions.html line 32: replace the mk-lead paragraph: #}
<p class="mk-lead">Whatever you install, repair, or build — if your business lives off the phone, FirstBack answers every missed call by text and books the work while you're on the tools. AI voice callback is coming soon.</p>
```

This matches the hedging on every other page, removes the false present-tense voice claim, and doesn't kill the aspiration.

### Tests to add
File: `test_predeploy_fixes.py` (standalone — already exists):
```python
# test: GET /solutions rendered HTML does not contain "live AI voice" as a present-tense claim
# test: GET /solutions contains "coming soon" near "voice"
```
Run: `.venv/bin/python test_predeploy_fixes.py`

### Effort: XS (15 minutes)
### Risk: LOW
- Single sentence change in one template.
- **Collision risk:** none.

---

## Fix 8 — No owner notification when A2P flips pending→approved

### What + why
`connections.a2p_sync()` correctly transitions the business from `pending` to `approved` and flushes blocked sends (lines 526–531). But no notification fires to the contractor. If Dave set-and-forgot after step 4 of the wizard, he has no idea he went live. The most important moment in the product lifecycle is invisible.

The pattern for this exact scenario already exists in the codebase: `connections.py` line 641 uses `import alerts` (lazy import) and line 662 calls `alerts.notify_async(biz, "forwarding_lost", {})` on the forwarding-lost event. The `roi_milestone` kind already maps to `alert_on_roi_milestone` in `_TOGGLE_COL`. We need a new "a2p_approved" kind — or we can use `notify_async` with a direct kind + context.

### Exact location
**`connections.py` lines 526–531:**
```python
if mapped == "approved" and current != "approved":
    try:
        flush_blocked_sends(biz["id"])
    except Exception as _fe:
        print(...)
return mapped
```

**`alerts.py` line 30:** `ALERT_KINDS` tuple (must add the new kind if we create one).
**`alerts.py` lines 46–62:** `_TOGGLE_COL` dict (must add the new kind mapping).
**`alerts.py` `format_message`:** add copy for the new kind.

### Concrete approach

**Option A (minimal, no new alert kind):** Send a direct SMS + email from `connections.a2p_sync` using `messaging.send_sms` and `mail.send_email` with a hardcoded body. Skip the full alerts machinery.

**Option B (preferred — consistent with codebase pattern):** Add `"a2p_approved"` as a new alert kind and call `notify_async`.

Steps for Option B:

1. **`alerts.py` line 30:** add `"a2p_approved"` to `ALERT_KINDS`:
```python
ALERT_KINDS = ("lead", "booking", "urgent", "canceled", "sms_fail", "forwarding_lost",
               "roi_milestone", "vic_morning", "vic_stall", "screening_graduated",
               "growth_tray", "daily_digest", "tick_stale", "a2p_approved")
```

2. **`alerts.py` `_TOGGLE_COL`:** add:
```python
"a2p_approved": "alert_on_lead",  # rides lead-alert toggle; owner needs to know this
```

3. **`alerts.py` `format_message`:** add a branch:
```python
if kind == "a2p_approved":
    return ("You're live! FirstBack is now texting back your missed calls. "
            "Any calls we received while you were waiting have been sent — "
            "check your leads inbox.")
```

4. **`connections.py` lines 526–531:** fire the alert after flush:
```python
if mapped == "approved" and current != "approved":
    try:
        flush_blocked_sends(biz["id"])
    except Exception as _fe:
        print(f"[firstback] a2p_sync flush error (biz {biz['id']}): {_fe}",
              file=sys.stderr, flush=True)
    try:
        import alerts
        alerts.notify_async(biz, "a2p_approved", {})
    except Exception as _ae:
        print(f"[firstback] a2p_sync alert error (biz {biz['id']}): {_ae}",
              file=sys.stderr, flush=True)
```

The lazy `import alerts` pattern (already used at line 641) avoids circular imports.

### Tests to add
File: `test_sf8_connections.py` (standalone — already exists):
```python
# test: a2p_sync on pending->approved transition calls notify_async with kind='a2p_approved'
# test: a2p_sync on pending->pending does NOT call notify_async
# test: a2p_sync on approved->approved does NOT call notify_async (idempotent)
# test: format_message('a2p_approved', {}) returns the expected copy (unit test, no DB)
```
Run: `.venv/bin/python test_sf8_connections.py`

### Effort: S (2–3 hours)
### Risk: MEDIUM — this is the riskiest fix in this batch
- `connections.py` is called on the `/tasks/run-due` cron tick for every business with a pending campaign. The alert must not raise or slow down the sync loop.
- The lazy `import alerts` pattern is already established, so circular import risk is mitigated.
- `a2p_sync` is already wrapped in try/except at the call site in `a2p_sync_all`; the new alert block uses its own try/except.
- **Collision risk:** `alerts.py` (`ALERT_KINDS`, `_TOGGLE_COL`, `format_message`) are shared. Adding a new kind is additive and does not break existing kinds. The `test_alert_channel.py` suite should be run after changes.
- **Dedup note:** `notify_async` dedupes within `ALERT_DEDUPE_SECONDS` (120s). Since A2P approval fires once per business lifetime, this is fine — no chance of double-fire within the window.

---

## Fix 9 — `alert_on_roi_milestone` toggle missing from Settings UI + `update_alert_prefs` whitelist

### What + why
`db.py` lines 844–845 add the `alert_on_roi_milestone` column. `alerts.py` line 49 maps `"roi_milestone"` to `"alert_on_roi_milestone"` in `_TOGGLE_COL`. But:
- `db.update_alert_prefs` (line 2398–2399) has a hardcoded whitelist of columns: `["alert_email", "alert_sms", "alert_on_lead", "alert_on_booking", "alert_on_urgent", "alert_on_daily_digest"]` — `alert_on_roi_milestone` is absent. Any Settings form submission cannot persist this toggle.
- `templates/settings.html` lines 198–202 render 4 toggles but not `alert_on_roi_milestone`.

The toggle is therefore unreachable: the column exists and the alert respects it, but the owner can never turn it off.

### Exact location
**`db.py` lines 2398–2399:**
```python
cols = ["alert_email", "alert_sms", "alert_on_lead", "alert_on_booking",
        "alert_on_urgent", "alert_on_daily_digest"]
```

**`app.py` lines 1135–1141** (`settings` POST handler):
```python
db.update_alert_prefs(biz["id"], {
    "alert_email": ...,
    "alert_sms": ...,
    "alert_on_lead": ...,
    "alert_on_booking": ...,
    "alert_on_urgent": ...,
    "alert_on_daily_digest": ...,
})
```

**`templates/settings.html` lines 198–202:** four `alert_toggle` macros, missing roi_milestone.

### Concrete approach

**Step 1 — `db.py` line 2399:** add `"alert_on_roi_milestone"` to the whitelist:
```python
cols = ["alert_email", "alert_sms", "alert_on_lead", "alert_on_booking",
        "alert_on_urgent", "alert_on_daily_digest", "alert_on_roi_milestone"]
```

**Step 2 — `app.py` lines 1135–1141:** add the key to the dict passed to `update_alert_prefs`:
```python
db.update_alert_prefs(biz["id"], {
    "alert_email": ...,
    "alert_sms": ...,
    "alert_on_lead": ...,
    "alert_on_booking": ...,
    "alert_on_urgent": ...,
    "alert_on_daily_digest": ...,
    "alert_on_roi_milestone": 1 if request.form.get("alert_on_roi_milestone") else 0,
})
```

**Step 3 — `templates/settings.html` line 202:** add the toggle after `alert_on_daily_digest`:
```jinja
{{ alert_toggle('alert_on_roi_milestone', 'A milestone SMS when FirstBack pays for itself', business.alert_on_roi_milestone) }}
```

### Tests to add
File: `test_toggles_hub.py` (standalone — already exists):
```python
# test: POST /settings with alert_on_roi_milestone=1 persists 1 to DB
# test: POST /settings without alert_on_roi_milestone persists 0 to DB
# test: GET /settings renders alert_on_roi_milestone toggle
# test: update_alert_prefs({'alert_on_roi_milestone': 1}, biz_id) updates the column (unit test)
```
Run: `.venv/bin/python test_toggles_hub.py`

### Effort: S (1–2 hours)
### Risk: LOW
- `db.py` whitelist is additive (new column already exists).
- `app.py` settings handler: additive dict entry.
- `settings.html`: additive template line.
- **Collision risk:** `db.py` and `app.py` are shared files, but these are isolated additions within a well-bounded function. Run `test_toggles_hub.py` and `test_sf7_sentinel.py` (since settings.py touches the same DB) after changes.

---

## Summary Table

| # | Fix | File(s) | Effort | Risk |
|---|-----|---------|--------|------|
| 1 | Voice says "sent you a text" when blocked | `app.py` lines 2617–2670 | S | LOW |
| 2 | EIN `required=true` blocks sole-props | `templates/setup.html:83`, `templates/auth.html:86–93` | S | LOW |
| 3 | Hero phone GET not wired to signup | `templates/auth.html:86–93`, `templates/onboarding.html:79` | S | LOW |
| 4 | `$null/job` on analytics tile | `static/app.js` lines 544–546 | S | LOW |
| 5 | "See it live" CTA → login wall | `templates/landing.html:15`, `templates/product.html:18,47`, `templates/onboarding.html:37`, `templates/marketing_base.html:36,96` | S | LOW |
| 6 | 5-star self-review on auth page | `templates/auth.html:31–35` | S | LOW |
| 7 | `solutions.html` "live AI voice" | `templates/solutions.html:32` | XS | LOW |
| 8 | No alert when A2P approves | `connections.py:526–531`, `alerts.py:30,46,format_message` | S | MEDIUM |
| 9 | `alert_on_roi_milestone` unreachable | `db.py:2399`, `app.py:1135–1141`, `templates/settings.html:202` | S | LOW |

**Total estimated effort:** 1–1.5 days for all 9 fixes.

**Riskiest fix:** Fix 8 (A2P approval alert). It touches `connections.py` which runs on every cron tick, `alerts.py` which fans out to SMS/email, and adds a new `ALERT_KIND`. Both the flush and the new notify call must be wrapped in isolated try/excepts to prevent a failed alert from breaking the sync loop. Test thoroughly with `test_sf8_connections.py` and `test_alert_channel.py`.

---

## Execution order recommendation

Run in this sequence to minimize risk and confirm each fix before proceeding:

1. Fix 7 (XS, 15 min — solutions.html one-liner, instant verify)
2. Fix 6 (S, 30 min — auth.html star removal, instant verify)
3. Fix 5 (S, 30 min — demo CTA swaps, instant verify)
4. Fix 4 (S, 1 hr — JS tile fix, verify in browser with no avg_job_value set)
5. Fix 2 (S, 1–2 hr — EIN gate removal, test setup.py)
6. Fix 3 (S, 1–2 hr — phone wire-through, test phone_wire.py)
7. Fix 1 (S, 2–3 hr — TwiML honest copy, test voice_app.py)
8. Fix 9 (S, 1–2 hr — roi_milestone toggle, test toggles_hub.py)
9. Fix 8 (S, 2–3 hr — A2P approval alert, test sf8_connections.py + alert_channel.py)
