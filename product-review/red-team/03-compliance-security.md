# RED-TEAM LANE 3: Compliance & Security Audit
**FirstBack** — Flask + SQLite SaaS at `/Users/jonathanmorris/Documents/apps/firstback`
**Audited:** 2026-06-25 | **Auditor role:** Lane 3 (Compliance & Security), read-only

---

## SECTION 1: COMPLIANCE

### P0 — Outbound AI-Voice FCC Non-Disclosure

**File/line:** `voice_service.py:239-241`

**Scenario:** The FCC's 2024 order (In re: Advanced Methods to Target and Eliminate Unlawful Robocalls) requires that any AI-generated voice call **disclose** at the outset that the call uses an artificial or prerecorded voice. When a lead is called back via the outbound ConversationRelay path (`place_call` → `build_twiml` with `greeting=None`), the injected greeting is:

```
"Hi, this is the scheduling assistant for {name}. This call may be recorded. How can I help you book your free estimate?"
```

"Scheduling assistant" is not a disclosure that the voice is AI-generated. A reasonable recipient does not know they are speaking to a machine. Carriers and the FCC have been enforcing this aggressively post-2024; the FCC treats the absence of an AI disclosure as a TCPA violation at the outset of each call. Each non-compliant call = a separate violation (up to $10,000 per call under the FCC's 2024 rules).

**Contrast:** The inbound path (`app.py:3124-3129`) was separately fixed and now correctly says `"I'm an AI scheduling assistant"`. The outbound path was not updated.

**Fix:** Change the default greeting in `voice_service.py:240`:
```python
greeting = (f"Hi, this is an AI scheduling assistant for {_greeting_name(biz_id, name)}. "
            "This call may be recorded. How can I help you book your free estimate?")
```
The words "AI" before "scheduling assistant" satisfies the FCC "any reasonable means" standard. Remove "scheduling" if a shorter disclosure is preferred.

---

### P1 — Privacy Policy: Vague Data Retention Language

**File/line:** `templates/privacy.html` (retention section)

**Scenario:** The privacy policy states data is retained "as long as your account is active and as needed." This is legally inadequate for:

1. **CCPA/CPRA (California):** California users have the right to deletion. Without specific retention periods, the business cannot demonstrate compliance when exercising deletion rights, and regulators may treat the vagueness as a CCPA violation.
2. **TCPA/FCC best practice:** Consent records (specifically the `consent_ledger` table) must be retained for proof of consent; the policy doesn't specify that consent records are retained after account deletion.
3. **Federal Trade Commission Act Section 5:** Vague promises about data handling can constitute unfair or deceptive practices if user data is retained beyond a reasonable interpretation of "as needed."

**Fix:**
- Add explicit retention periods per data category: e.g., "account data deleted within 30 days of account closure; SMS/voice consent records retained for 5 years."
- Add a CCPA rights section listing the right to know, delete, and opt out of sale/sharing.
- Specify that consent ledger entries are retained for at least 5 years (TCPA statute of limitations).

---

### P1 — Consent Ledger Is a Migration Target, Not Active System

**File/line:** `consent.py` (docstring/comments); `connections.py:394-498` (flush_blocked_sends uses `outbound_mode`)

**Scenario:** The `consent_ledger` append-only table is described as a "migration target." The live consent state for FirstBack is the mutable `contacts_consent` field on the contacts/leads table. If a future migration fails or partially runs, the system could be operating in a state where opt-outs received before the migration were written to the old table but not migrated to the new ledger — enabling texts to go to opted-out numbers. Regulators interpret TCPA consent as a strict-liability standard; "migration in progress" is not a defense.

**Fix:** Either fully commit to the `consent_ledger` as the source of truth (complete the migration and make all consent queries use it) or document the current hybrid state clearly and add a CI check that no consent is ever read from the old table once the migration is live. Add a one-time migration audit script that cross-references both tables for discrepancies.

---

### P1 — Recording Disclosure: Outbound Path Missing, Inbound Path Removed

**File/line:** `app.py:3123-3129` (inbound greeting), `voice_service.py:240` (outbound greeting)

**Scenario:** The inbound AI greeting (post-FCC fix) reads: `"I'm an AI scheduling assistant -- I can get you booked for a free estimate right now."` This does NOT include "this call may be recorded." Two-party consent jurisdictions (California, Illinois, Florida, Connecticut, Maryland, Michigan, Montana, Nevada, New Hampshire, Oregon, Pennsylvania, Washington) require all-party consent for recording. The app records calls via Twilio recording webhook (`/webhooks/twilio/voice/recording`). Notifying only on the outbound path (which has the recording disclosure) and omitting it on inbound creates exposure in those states.

**Fix:** Add recording disclosure to the inbound greeting: `"I'm an AI scheduling assistant. This call may be recorded for quality and booking purposes."` This is a single sentence addition and satisfies all 12 two-party states.

---

### P1 — HELP Response Missing Service Name / Short Code / Opt-out Instructions

**File/line:** `app.py:3385-3388`

**Scenario:** The CTIA Messaging Principles require that a HELP response include: (1) program/product name, (2) customer support contact, and (3) opt-out reminder. The current response is:
```
"{biz_name}: Hi, reply here about your free estimate. Reply STOP to unsubscribe."
```
It includes biz_name and opt-out, but omits the customer support contact (phone or email). CTIA non-compliance can result in carrier filtering of A2P messages and campaign deactivation by Twilio.

**Fix:** Add a support contact reference: `"...Reply STOP to unsubscribe or email {support_email} for help."` Wire the business's alert_email or a support alias.

---

### P2 — No Explicit STOP/Opt-out Language in Initial Outbound SMS

**File/line:** `messaging.py` (send_sms), initial message templates

**Scenario:** CTIA A2P 10DLC guidelines require that the FIRST message in a new marketing/transactional thread include an opt-out disclosure ("Reply STOP to unsubscribe"). If `open_conversation` generates the welcome text, that message should end with an opt-out disclosure. This is not verified in the code — the AI-generated welcome reply may or may not include STOP language depending on the prompt's output.

**Fix:** After calling `open_conversation()`, append a disclaimer to the sent SMS if the reply doesn't already contain "STOP": e.g., wrap `send_sms` to append `"\n\nReply STOP to unsubscribe."` if the body doesn't already contain opt-out language.

---

### P2 — A2P 10DLC: No UI Warning That "submitted" != "approved"

**File/line:** `connections.py` (`a2p_sync`); `app.py` (setup/a2p route, ~line 1667)

**Scenario:** The code correctly enforces `a2p_status == "approved"` before real sends (`compliance.py`, `messaging.py`). However, the setup UI that submits the A2P brand/campaign registration shows a success screen on HTTP 200 from Twilio's "create" endpoint. Twilio returns 200 for campaign submission, but campaigns go through a multi-day vetting queue. If the UI text reads "A2P registration complete" or "10DLC approved," users may believe they can send immediately, leading to confusion or attempts to bypass the gate. This is a legal-risk gap: the correct message is "submitted for approval — texting will be enabled automatically once Twilio approves your campaign."

**Fix:** Audit the setup/a2p template for wording. Ensure the status shown is "Pending approval" until `a2p_status == "approved"`. Add a banner to the dashboard when `a2p_status != "approved"` explaining that texting is paused pending carrier approval.

---

## SECTION 2: SECURITY

### P0 — Login Rate Limit Bypass via X-Forwarded-For Spoofing

**File/line:** `app.py:375`

**Scenario:** The login rate limiter uses the key `f"{email}:{ip}"` where `ip` is extracted from the `X-Forwarded-For` header:
```python
ip = request.headers.get("X-Forwarded-For", request.remote_addr or "").split(",")[0].strip()
```
There is no ProxyFix middleware configured. When the app runs behind a load balancer/proxy (Render, Heroku, etc.), the real client IP IS in X-Forwarded-For — but since the header is not validated against a trusted proxy list, a direct attacker (bypassing the proxy) can forge the header with any IP and rotate through 10 attempts per fake IP, effectively turning the rate limiter off.

**Attack scenario:**
1. Attacker sends POST `/login` with header `X-Forwarded-For: 1.2.3.4` — 10 attempts.
2. Changes header to `X-Forwarded-For: 1.2.3.5` — 10 more attempts.
3. Repeat for unlimited credential stuffing against any user's email.

**Fix:** Configure `werkzeug.middleware.proxy_fix.ProxyFix` with the correct `x_for` value for your proxy tier (typically 1 for single-proxy):
```python
from werkzeug.middleware.proxy_fix import ProxyFix
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)
```
With ProxyFix in place, Werkzeug strips untrusted X-Forwarded-For headers and populates `request.remote_addr` with the true client IP. The `_login_rate_key` function can then use `request.remote_addr` directly instead of the header.

---

### P0 — Logout is a GET Endpoint (Cross-Site Logout Attack)

**File/line:** `app.py:415-418`

**Scenario:** The logout route is a plain GET with no CSRF or state:
```python
@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")
```
Any webpage or email the authenticated user visits can silently log them out via a zero-pixel image or link:
```html
<img src="https://app.firstback.com/logout" width="0" height="0">
```
While logout CSRF isn't directly exploitable for account takeover by itself, it can be chained with a login CSRF or used as a denial-of-service (disrupts active sessions, forces re-authentication during business hours). More importantly, it demonstrates the CSRF architecture has a gap that needs to be addressed for defense-in-depth.

**Fix:** Change logout to POST and protect it with `_csrf_ok()`:
```python
@app.route("/logout", methods=["POST"])
def logout():
    if not _csrf_ok():
        return redirect("/")
    session.clear()
    return redirect("/")
```
Update any template logout links to use `<form method="POST" action="/logout">` with the CSRF token.

---

### P1 — /auth/forgot POST Has No CSRF Protection

**File/line:** `app.py:426-453`

**Scenario:** The password-reset request route processes a POST without calling `_csrf_ok()`. A cross-origin attacker can submit `<form>` to `/auth/forgot` with any victim's email, causing the server to:
1. Generate a password-reset token for the victim.
2. Send a password-reset email to the victim from the app.

This is a "reset email spam" vector. While it doesn't compromise the account (the actual `/auth/reset` token must be used in the victim's browser session and the victim must click the link), it is a low-friction harassment or phishing-prep attack. It also invalidates any previously issued tokens since `create_password_reset_token` writes a new row (depending on DB schema — if tokens aren't deduplicated per user, multiple tokens coexist).

**Fix:** Add `if not _csrf_ok(): return render_template("auth.html", mode="forgot", error="Invalid request."), 403` at the top of the POST branch. The forgot form template must include the CSRF token field.

---

### P1 — /contact POST Has No CSRF Protection

**File/line:** `app.py:512-531`

**Scenario:** The contact form (used by prospects/visitors to send inquiries) processes POSTs without CSRF validation. An attacker can submit fake contact messages cross-origin. While this doesn't directly compromise user data, it pollutes the contact message queue with attacker-controlled content (phishing lures, spam) that the business owner reads in their inbox.

**Fix:** Add `if not _csrf_ok(): return render_template("contact.html", error="Invalid request."), 403` at the top of the POST branch. Update the contact template to include the CSRF token.

---

### P1 — SEED_OWNER_EMAIL PII Hardcoded in Source

**File/line:** `config.py:468`

**Scenario:**
```python
SEED_OWNER_EMAIL = os.environ.get("FIRSTBACK_OWNER_EMAIL", "heritagehousepainting@gmail.com")
```
A real Gmail address is hardcoded as the fallback default. This means:
1. The address is committed to the git repository and visible in any repo exposure (leak, contributor access, CI logs).
2. If `FIRSTBACK_OWNER_EMAIL` is not set in a staging/dev environment, the seed owner is created with this address — a real email. Password-reset emails, alert emails, and any seed-data operations go to the hardcoded address.
3. Enumeration: any user who knows to try `heritagehousepainting@gmail.com` on the login form gets a non-enumeration-safe "try logging in" error (line 333), confirming the email exists.

**Fix:** Replace with a synthetic placeholder: `"owner@example.com"`. Add a `SEED_OWNER_EMAIL is required in production` check to `config.py`'s fail-fast block (alongside the existing `SECRET_KEY` check).

---

### P1 — Login Rate Limit is In-Memory (Process-Scoped, Non-Persistent)

**File/line:** `app.py:365-383` (LOGIN_FAILURES dict)

**Scenario:** The `_LOGIN_FAILURES` dict is a module-level `defaultdict(list)`. This means:
1. **Process restart bypass:** Any time the app process restarts (deploy, crash, autoscale), all accumulated failure counts are lost. An attacker can trigger a restart (OOM, crash loop) to reset the counter.
2. **Multi-worker bypass:** If the app runs under gunicorn with multiple worker processes (the standard production configuration), each worker maintains its own counter. With 4 workers, the effective limit is 40 attempts before any worker blocks.
3. **Email rotation:** An attacker who rotates email prefixes can enumerate passwords on existing accounts by using a different (but registered) email format.

**Fix:** Move rate-limit tracking to a Redis counter (keyed by IP) with TTL-based expiry. Even a simple `redis.incr(key); redis.expire(key, 300)` pattern is significantly more robust. If Redis is unavailable, use the database with a `login_attempts` table. Per-IP (not per-email+IP) limits are also more robust.

---

### P2 — No ProxyFix Middleware for X-Forwarded-Proto (Twilio Signature Risk)

**File/line:** `app.py:96-112` (`require_twilio_signature`)

**Scenario:** The `@require_twilio_signature` decorator reconstructs the URL for HMAC verification using the raw `X-Forwarded-Proto` header:
```python
proto = request.headers.get("X-Forwarded-Proto")
if proto:
    url = url.replace("http://", proto + "://", 1)
```
Without ProxyFix, a direct attacker bypassing the proxy can forge `X-Forwarded-Proto: https` to cause URL reconstruction to produce an `https://` URL, potentially making signature verification fail (if Twilio signed for `http://`) or pass an incorrect reconstructed URL. This is less critical than the login bypass since Twilio webhooks also have the HMAC computed over form params, but it is a defense-in-depth gap. Additionally, the widget endpoint (`/webhooks/widget/lead`) reads X-Forwarded-For at line 3277 for rate limiting, with the same spoofability as the login route.

**Fix:** Install ProxyFix (see P0 fix above). With ProxyFix, `request.scheme` becomes correct and `X-Forwarded-Proto` does not need to be manually read.

---

### P2 — TEMPLATES_AUTO_RELOAD = True in Production

**File/line:** `app.py:54`

**Scenario:**
```python
app.config["TEMPLATES_AUTO_RELOAD"] = True
```
This is unconditional — no `if DEBUG:` guard. In production, this forces Flask to check template file modification times on every request. It has two effects:
1. **Performance:** Stat syscall on every template render — measurable latency impact at scale.
2. **Security (minor):** If an attacker can write to the template directory (via a path traversal or misconfigured deployment with writable template files), auto-reload means the injected template takes effect immediately on next request rather than requiring a restart.

**Fix:**
```python
app.config["TEMPLATES_AUTO_RELOAD"] = DEBUG
```

---

### P2 — /auth/forgot Has No Rate Limit

**File/line:** `app.py:426-453`

**Scenario:** The forgot-password route has no rate limiting. An attacker with a list of email addresses can submit rapid-fire POST requests to `/auth/forgot`, causing the app to:
1. Consume outbound email quota (mail.py sends a reset email for every valid address hit).
2. Flood users' inboxes with reset emails.
3. Exhaust any per-account token limits.

The login route has a 10-attempt/5-minute limit. The forgot route has no protection at all.

**Fix:** Apply the same `_login_blocked` pattern to the forgot route, keyed by the submitted email address and IP. Alternatively, add a global per-IP rate limit (e.g., 5 forgot requests per 5 minutes from a single IP) to reduce email spam without requiring an email lookup.

---

### P2 — INTERNAL_SECRET Empty String Disables Voice Seam (Fail-Open Documentation Gap)

**File/line:** `config.py:281`, `app.py:3664`

**Scenario:** The code is correctly fail-closed:
```python
if not INTERNAL_SECRET or not secrets.compare_digest(sent, INTERNAL_SECRET):
    return jsonify(error="Forbidden."), 403
```
When `FIRSTBACK_INTERNAL_SECRET` is not set, `INTERNAL_SECRET = ""` — the condition `not INTERNAL_SECRET` is True, so all requests are rejected. This is the correct, safe behavior.

However, the config docstring/comment at `config.py:281` does not make it explicit that this means the voice seam is fully disabled (not just unsecured). Operators who don't read the code may deploy `voice_service.py` and `app.py` without setting `INTERNAL_SECRET` and debug for hours wondering why no voice turns arrive at the web app.

**Fix:** Add a startup log warning when `INTERNAL_SECRET` is empty and the voice service is configured (`VOICE_PUBLIC_URL` is set). Something like: `logger.warning("FIRSTBACK_INTERNAL_SECRET not set — /internal/voice/turn is disabled (403 for all callers). Set this env var on both app and voice service.")`.

---

### P2 — Signup POST Has No CSRF Protection

**File/line:** `app.py:313-357`

**Scenario:** The `/signup` POST route creates a new business account and user. It does not call `_csrf_ok()`. While signup CSRF is low-risk (an attacker would create an account for themselves, not the victim), it allows cross-origin form submission to create new accounts from any page, and it means pre-fill attacks (attacker crafts a URL/form that pre-populates the signup form with attacker-controlled data) can succeed without user interaction. More importantly, if the signup flow ever includes payment or sensitive setup data, the missing CSRF becomes a higher-priority issue.

**Fix:** Add `if not _csrf_ok(): return render_template("auth.html", mode="signup", error="Invalid request."), 403` and include the CSRF token in the signup form template.

---

## SEVERITY SUMMARY

| Severity | Count | Issues |
|----------|-------|--------|
| P0 | 2 | Outbound AI-voice FCC non-disclosure; Login rate limit IP spoofing |
| P1 | 6 | Logout GET (no CSRF); /auth/forgot no CSRF; /contact no CSRF; SEED_OWNER_EMAIL PII in source; In-memory rate limit; Privacy policy retention vagueness |
| P2 | 5 | ProxyFix missing; TEMPLATES_AUTO_RELOAD unconditional; /auth/forgot no rate limit; INTERNAL_SECRET documentation gap; Signup no CSRF |

**CONFIRMED WORKING:**
- All Twilio webhooks: `@require_twilio_signature` on all 9 endpoints (lines 1769, 1797, 1822, 3150, 3194, 3236, 3353, 3504, 3767).
- Stripe webhook: `stripe.Webhook.construct_event()` with `STRIPE_WEBHOOK_SECRET` (billing.py).
- Internal voice seam: constant-time compare, fail-closed when empty (app.py:3664).
- TASKS_SECRET: constant-time compare, fail-closed when empty (app.py:3553-3555).
- Token encryption: HKDF-SHA256 + counter-mode XOR + HMAC (token_crypto.py), correct constant-time MAC compare.
- Cross-tenant isolation: all DB reads/writes scoped by `business_id`; `get_lead(lead_id, biz["id"])`, `cancel_appointment(biz["id"], appt_id)`, contacts/suggestions/calls all scoped.
- A2P gate: `a2p_ready()` requires `a2p_status == "approved"`, never triggers on CREATE 200.
- Quiet hours: enforced in `reminders.py` `next_send_time()`, backstop in `messaging.send_sms()`.
- STOP/opt-out: `STOP_WORDS` includes "cancel", NLU opt-out (`opt_out_nlu()`) handles natural language.
- Re-opt-in: `START_WORDS` set, `opt_in_nlu()` enforced in SMS inbound path.
- Blocked-sends flush: 8 safety rules in `connections.py:394-498` (freshness, opt-out, quiet hours, dedupe).
- Password hashing: `generate_password_hash` (Werkzeug bcrypt/pbkdf2) on create and reset.
- Session cookie: `SECRET_KEY` fail-fast in production; SameSite=Lax blocks cross-site POST.
- CSRF: `_csrf_ok()` constant-time compare on ~55 state-changing routes.
- Inbound AI voice: correct disclosure at `app.py:3126`.
- Debug off by default: `DEBUG = os.environ.get("FIRSTBACK_DEBUG", "").strip().lower() in (...)`.
- SQL injection: `_BUSINESS_COLS` whitelist for dynamic SET clauses; all user input parameterized.

---

## TOP 5 FINDINGS

1. **[P0] Outbound AI-voice FCC non-disclosure** (`voice_service.py:240`) — every outbound callback call says "scheduling assistant" not "AI." FCC 2024 rules; up to $10K per call. One-word fix: add "AI" before "scheduling assistant."

2. **[P0] Login rate limit IP spoofing** (`app.py:375`) — `X-Forwarded-For` taken verbatim without ProxyFix. Attacker rotates IP header to run unlimited credential stuffing against any account. Fix: install `ProxyFix` middleware.

3. **[P1] Logout is a GET** (`app.py:415`) — cross-site logout via zero-pixel image. Low direct impact but demonstrates CSRF architecture gap; chains with other attacks. Fix: change to POST + `_csrf_ok()`.

4. **[P1] SEED_OWNER_EMAIL real address hardcoded** (`config.py:468`) — `heritagehousepainting@gmail.com` committed to source; leaks to any repo/CI observer; seed-data flows send live emails to this address in non-prod environments. Fix: replace with `owner@example.com`, add fail-fast.

5. **[P1] /auth/forgot no CSRF + no rate limit** (`app.py:426-453`) — cross-origin attacker can spam arbitrary email addresses with reset emails from the FirstBack mail channel; can exhaust email quota and harass users. Fix: add `_csrf_ok()` check and per-IP rate limit.
