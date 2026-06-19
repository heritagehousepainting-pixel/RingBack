# FirstBack — New Lead-Source & Conversion Feature Plans
**Planning lane 10 of 10: NEW FEATURES (from report 12)**
Date: 2026-06-19
Status: BUILD-READY specs. READ-ONLY (no code written).

---

## Seams Confirmed in Real Code

Before every spec, these existing attach points were verified:

| Seam | File | Confirmed |
|------|------|-----------|
| `db.create_lead(business_id, name, phone, source=)` | db.py:1313 | YES — `source` param already there |
| `open_conversation(biz, lead)` | app.py:1731 | YES — generates + sends opening text |
| `handle_inbound(biz, lead, body)` | app.py:1789 | YES — one inbound turn, returns (reply, booked, urgent) |
| `ai.generate_reply(business, history, ...)` | ai.py:467 | YES — returns (text, booking_slot) |
| `messaging.send_sms(biz, to, body, lead_id=)` | messaging.py:77 | YES — gated, opt-out-aware |
| `messaging.place_call(biz, to, twiml_url, ...)` | messaging.py:210 | YES — used by dispatcher |
| `_missed_call_textback(biz, caller, call_sid, dial_status)` | app.py:2580 | YES — the missed-call orchestrator |
| `/webhooks/twilio/voice/inbound` (POST) | app.py:2623 | YES — Twilio-signature-verified |
| `/webhooks/twilio/voice/dial-status` (POST) | app.py:2657 | YES — fires on no-answer/busy |
| `alerts.notify_async(biz, "booking", ctx)` | app.py:1887 | YES — booking alert hook |
| `compliance.a2p_ready(business)` + opt-out gate | messaging.py:140 | YES — send_sms enforces both |
| `db.book_appointment(biz_id, lead_id, scheduled_for)` | db.py:1476 | YES |
| `billing.py` + Stripe SDK | billing.py:1 | YES — STRIPE_SECRET_KEY, Stripe SDK imported |
| `google_cal.is_connected(business_id)` | google_cal.py:42 | YES — OAuth token check |
| `db.get_integration(business_id, "google")` | google_cal.py:44 | YES — same OAuth row for GBP |
| `_BUSINESS_COLS` (settings-form save-safe cols) | db.py:20–26 | YES — `review_link` is already in it |
| `db.update_business(business_id, fields)` | db.py:1050 | YES — only saves `_BUSINESS_COLS` |
| `TWILIO_ACCOUNT_SID / AUTH_TOKEN` | messaging.py | YES — reused for recording fetch |

---

## Feature 1: Voicemail Transcription → Lead

### What & Why

When a caller leaves a voicemail, FirstBack currently loses the lead. Twilio's Recording API already captures voicemails when a `recordingStatusCallback` is added to the `<Dial>` verb. A new webhook receives the transcript, creates a lead, and fires the same `open_conversation` text-back — the caller gets a response. Owner sees the transcript in the thread. Effort: S (2–3 days). Zero new Twilio accounts.

---

### MVP Phase (2–3 days)

#### A. Wire recording into the voice webhook

**File: `app.py` — `twilio_voice_inbound` (line 2623)**

When forwarding is active (a `<Dial>` is issued), add `recordingStatusCallback` and `record="record-from-answer-dual"` so any unanswered leg is captured:

```python
# In twilio_voice_inbound, when forward is set:
recording_cb = _public_base() + "/webhooks/twilio/voice/recording"
return _twiml(
    f'<Response><Dial answerOnBridge="true" timeout="18" action="{action}" '
    f'method="POST" record="record-from-answer-dual" '
    f'recordingStatusCallback="{recording_cb}" '
    f'recordingStatusCallbackMethod="POST">'
    f'<Number>{_xesc(forward)}</Number></Dial></Response>')
```

No change to `twilio_voice_dial_status` — missed dial still fires `_missed_call_textback`. The recording webhook is ADDITIVE (handles the voicemail content separately).

#### B. New recording webhook endpoint

**New route in `app.py`:**

```python
@app.route("/webhooks/twilio/voice/recording", methods=["POST"])
@require_twilio_signature
def twilio_voice_recording():
    """Fires when Twilio finishes transcribing a recording. Creates a lead if one
    doesn't already exist for this caller and injects the transcript as the first
    inbound message so the AI knows what they said. Then fires open_conversation
    if the thread is empty (avoids double-greeting a caller who also got a
    missed-call text-back)."""
    biz = db.get_business_by_twilio_number(request.form.get("To", ""))
    if not biz:
        return _twiml("<Response/>")
    caller = request.form.get("From", "")
    transcript = (request.form.get("TranscriptionText") or "").strip()
    recording_url = request.form.get("RecordingUrl", "")
    if not caller:
        return _twiml("<Response/>")
    lead = db.get_lead_by_phone(biz["id"], caller)
    if not lead:
        lead = db.get_lead(db.create_lead(biz["id"], "Voicemail", caller,
                                          source="voicemail"))
    # If there's a transcript, inject it as an inbound message so the AI
    # knows what the caller said when it generates the reply.
    if transcript:
        db.add_message(lead["id"], "in", f"[Voicemail] {transcript}")
        db.add_message(lead["id"], "vm_url", recording_url)  # store for UI
    # Only greet empty threads (missed-call text-back may have already gone).
    if not db.get_messages(lead["id"], direction="out"):
        reply = open_conversation(biz, lead)
        messaging.send_sms(biz, caller, reply)
    return _twiml("<Response/>")
```

#### C. DB: store recording URL on thread

**Migration in `db.py` `init_db()`:**

```python
# messages gain optional recording_url for voicemail playback in the UI
msg_cols = [r[1] for r in c.execute("PRAGMA table_info(messages)").fetchall()]
if "recording_url" not in msg_cols:
    c.execute("ALTER TABLE messages ADD COLUMN recording_url TEXT")
```

The `vm_url` direction-type row is a lightweight way to attach the URL to the thread without a new table.

#### D. Twilio configuration: enable transcription

In `messaging.provision_number()` and `attach_owned_number()`, transcription is NOT needed — the `recordingStatusCallback` in the TwiML does the work. But Twilio's free transcription must be requested at the Recording level. Use `transcribe=true` as a `<Record>` attribute OR Twilio's free `RecordingStatusCallbackEvent=transcribed`. The webhook receives `TranscriptionText` when ready (~30–60s after the call ends).

**Transcription cost:** $0.00/min (Twilio basic transcription is included). Deepgram upgrade ($0.004/min) can be added later for better accuracy — the webhook shape stays identical.

---

### Phase 2 additions (optional, 1 extra day)

- Show a "Voicemail" badge in the lead thread UI (the `vm_url` row becomes a playable audio player).
- If `TranscriptionText` is empty (caller didn't leave a message, just hung up), skip the inject-and-reply — the missed-call text-back already handled it.
- Owner setting: `voicemail_transcription_enabled` (default ON, toggle in Settings).

---

### Standalone Tests

```
test_voicemail_transcription.py

1. twilio_voice_recording with valid sig + TranscriptionText -> lead created with source='voicemail', transcript injected as inbound message, reply sent
2. Recording webhook with existing lead -> no duplicate lead, thread extended
3. Recording webhook with empty TranscriptionText -> no message injected, empty thread still gets open_conversation reply
4. Recording webhook with non-empty thread (missed-call text already sent) -> no double-greeting
5. Recording webhook to unknown biz number -> 200, no-op
6. Recording webhook without Twilio signature -> 403
7. db migration: messages table gains recording_url column idempotently
```

**Effort: S (2–3 days) | Risk: Low | Dependency: Twilio creds + PUBLIC_BASE_URL (already required for live mode)**

---

## Feature 2: Web-Chat "Text Us" Widget

### What & Why

A single `<script>` tag drops a "Text us" bubble on any contractor website (Wix, WordPress, GBP, Yelp). Visitor submits a phone number → FirstBack creates a lead → fires the same `open_conversation` flow. No separate product, no new AI, no contractor code change beyond one paste.

---

### MVP Phase (5–7 days)

#### A. Widget config endpoint

**New route in `app.py`:**

```python
@app.route("/api/widget/<slug>/config.js")
def widget_config(slug):
    """Serves the per-tenant widget config (CORS-open, cache-friendly).
    Returns a JS assignment so the snippet can pull it with a <script> tag."""
    conn = db.get_conn()
    row = conn.execute(
        "SELECT id, name, trade FROM businesses WHERE micro_site_slug=?",
        (slug,)
    ).fetchone()
    conn.close()
    if not row:
        return "window.__fb={};", 200, {"Content-Type": "application/javascript"}
    cfg = {"slug": slug, "biz": row["name"], "trade": row["trade"],
           "endpoint": "/webhooks/widget/lead"}
    js = f"window.__fb={json.dumps(cfg)};"
    resp = app.response_class(js, mimetype="application/javascript")
    resp.headers["Cache-Control"] = "public, max-age=300"
    resp.headers["Access-Control-Allow-Origin"] = "*"
    return resp
```

#### B. Lead intake webhook

**New route in `app.py`:**

```python
# Rate-limit: 5 submissions per (slug, IP) per hour (in-memory, same pattern as login limiter)
_WIDGET_RATE: dict = collections.defaultdict(list)
_WIDGET_MAX = 5
_WIDGET_WINDOW = 3600

def _widget_rate_key(slug):
    ip = request.headers.get("X-Forwarded-For", request.remote_addr or "").split(",")[0].strip()
    return f"{slug}:{ip}"

def _widget_blocked(slug):
    key = _widget_rate_key(slug)
    cutoff = _time.monotonic() - _WIDGET_WINDOW
    _WIDGET_RATE[key] = [t for t in _WIDGET_RATE[key] if t > cutoff]
    if len(_WIDGET_RATE[key]) >= _WIDGET_MAX:
        return True
    _WIDGET_RATE[key].append(_time.monotonic())
    return False


@app.route("/webhooks/widget/lead", methods=["POST"])
def widget_lead():
    """Public lead intake from the embedded web-chat widget. No auth required —
    anti-abuse: rate-limited per (slug, IP), phone validated to E.164, lead
    de-duped by phone (get_lead_by_phone). Fires open_conversation + send_sms
    exactly like a missed call."""
    data = request.get_json(silent=True) or {}
    slug = (data.get("slug") or "").strip()
    phone_raw = (data.get("phone") or "").strip()
    name = (data.get("name") or "Web Visitor").strip()[:80]
    if not slug or not phone_raw:
        return jsonify(error="Missing slug or phone."), 400
    phone = messaging.to_e164(phone_raw)
    if not phone:
        return jsonify(error="Invalid phone number."), 400
    if _widget_blocked(slug):
        return jsonify(error="Too many submissions. Try again later."), 429
    conn = db.get_conn()
    row = conn.execute(
        "SELECT id FROM businesses WHERE micro_site_slug=?", (slug,)
    ).fetchone()
    conn.close()
    if not row:
        return jsonify(error="Business not found."), 404
    biz = db.get_business(row["id"])
    lead = db.get_lead_by_phone(biz["id"], phone)
    if not lead:
        lead = db.get_lead(db.create_lead(biz["id"], name, phone, source="web_widget"))
    # Only open a new conversation; don't interrupt an existing one.
    if not db.get_messages(lead["id"]):
        reply = open_conversation(biz, lead)
        messaging.send_sms(biz, phone, reply, lead_id=lead["id"])
    return jsonify(ok=True)
```

#### C. Embeddable JS snippet

**New static file: `static/widget.js`**

Delivered from `/api/widget/<slug>/config.js` + this loader. The contractor pastes ONE line:

```html
<script src="https://firstback.app/widget.js?slug=abc123" defer></script>
```

The widget JS:
1. Injects a floating "Text us" button (bottom-right, brand-blue, FirstBack branding optional via config).
2. On click: shows a small pop-up — name field (optional), phone field (required), consent line "By submitting, you agree to receive texts from [Business Name]. Reply STOP to opt out."
3. POST to `/webhooks/widget/lead` with `{slug, phone, name}`.
4. On success: "We'll text you right back!"

The consent line mirrors the existing `/c/<slug>` microsite's TCR language (already A2P-compliant). No new consent infrastructure needed.

**Tenant attribution:** slug → business_id. The slug is already on `businesses.micro_site_slug` (populated during setup wizard).

#### D. Settings: enable widget + get embed code

**Settings page addition:** a "Website Widget" card showing:
- Toggle: Widget enabled (default OFF — opt-in so contractors don't get surprise leads)
- Copy-paste `<script>` tag for their site
- Preview link (opens the microsite with the widget active)

No new DB column needed for MVP — if the slug exists, the widget endpoint works. The opt-in toggle can be a simple `widget_enabled INTEGER DEFAULT 0` migration.

---

### Phase 2 additions (1 week extra)

- Visitor's initial message (an optional "What do you need?" text field) injected as the first inbound message, giving the AI context.
- WhatsApp widget variant (same endpoint, different button).
- Analytics: `source='web_widget'` already on the lead; dashboard shows "Widget leads" count.
- GBP widget embed instructions (works in the "website" field on the GBP listing).

---

### Standalone Tests

```
test_web_widget.py

1. POST /webhooks/widget/lead with valid slug + US phone -> lead created, open_conversation fired, send_sms called
2. Same phone submits again -> no duplicate lead, existing thread not re-opened
3. Invalid E.164 phone -> 400
4. Unknown slug -> 404
5. Rate limit: 6th submission from same IP in 1 hour -> 429
6. GET /api/widget/<slug>/config.js -> valid JS with correct biz name + endpoint
7. GET /api/widget/<unknown>/config.js -> empty config JS, 200
8. CORS header present on config.js response
9. Consent text present in widget HTML (A2P gate: no send until compliance.a2p_ready)
```

**Effort: M (5–7 days) | Risk: Medium (anti-abuse, A2P compliance for new lead source) | Dependency: `micro_site_slug` populated (setup wizard — already required for Go Live)**

---

## Feature 3: Deposit Link at Booking Confirmation

### What & Why

No-shows cost contractors money. Stripe is already wired for billing. Owner stores a Stripe Payment Link URL (created once in their Stripe dashboard; FirstBack just stores and appends it). When a booking is confirmed, the AI appends the link. A paid deposit converts a soft-yes into a committed slot. Effort: S–M (1–2 days, mostly DB + template). No new Stripe API calls — just URL storage.

---

### MVP Phase (1–2 days)

#### A. DB: add `deposit_link` to businesses

**Migration in `db.py` `init_db()`:**

```python
biz_cols = [r[1] for r in c.execute("PRAGMA table_info(businesses)").fetchall()]
if "deposit_link" not in biz_cols:
    c.execute("ALTER TABLE businesses ADD COLUMN deposit_link TEXT")
if "deposit_amount" not in biz_cols:
    c.execute("ALTER TABLE businesses ADD COLUMN deposit_amount TEXT")
    # e.g. "$50" — purely display, the actual amount is in the Stripe Payment Link
```

Add `"deposit_link"` and `"deposit_amount"` to `_BUSINESS_COLS` in db.py so the Settings form saves them.

#### B. Settings UI: Deposit Link card

**`settings` POST handler in `app.py`** — already iterates `_BUSINESS_COLS` so adding the two cols to `_BUSINESS_COLS` is sufficient. The Settings template gets a new card:

```html
<h3>Deposit Link</h3>
<p>Paste your Stripe Payment Link URL. FirstBack will add it to booking confirmations
   to reduce no-shows. Leave blank to skip.</p>
<input name="deposit_link" type="url" value="{{ business.deposit_link or '' }}"
       placeholder="https://buy.stripe.com/..." />
<input name="deposit_amount" type="text" value="{{ business.deposit_amount or '' }}"
       placeholder="$50" />
```

#### C. Inject deposit link into booking confirmation

The booking confirmation text is generated by `ai.generate_reply()` and immediately sent in `handle_inbound()` / `open_conversation()`. The deposit link needs to be appended AFTER the AI's reply, in the send layer — not inside the LLM prompt (we don't want the LLM fabricating URLs).

**Hook location: `handle_inbound()` in `app.py` (line 1857), after `booked = booking` is set:**

```python
# After db.book_appointment() succeeds and reply is set:
if booked and biz.get("deposit_link"):
    amount = biz.get("deposit_amount") or "a deposit"
    deposit_suffix = (
        f" To hold your spot, secure it here ({amount}): {biz['deposit_link']}"
    )
    # Append only if the message + suffix fit within 320 chars (2 SMS segments).
    if len(reply) + len(deposit_suffix) <= 320:
        reply = reply + deposit_suffix
        # Re-record the outbound message with the deposit link included.
        db.add_message(lead_id, "out", reply)
```

**Same hook in `open_conversation()` at app.py:1739** — for first-turn bookings.

The reply is already recorded in `db.add_message` BEFORE the deposit suffix; the suffix replaces/updates the last outbound row. Cleaner alternative: pass `deposit_suffix` as a parameter to `open_conversation` and let it append before the initial `db.add_message` call. Either is valid; the latter avoids a double-write.

#### D. Stripe Payment Link creation guide

No in-app Stripe API call is needed for MVP. Owner creates the link in their Stripe dashboard (Products → Payment Links → Create, set price to deposit amount). They paste the URL into FirstBack's Settings. FirstBack stores and appends it.

**Phase 2** (optional): `POST /api/stripe/create-deposit-link` that uses the Stripe API to programmatically create a Payment Link given `deposit_amount_cents`. Requires the owner's Stripe account via OAuth (Stripe Connect). This is L-effort; defer for now.

---

### Phase 2 additions (2–3 days extra)

- Optional: "Deposit required" flag on appointment row — only mark as `booked` once payment is confirmed (via a Stripe webhook `checkout.session.completed`). This is the no-show nuclear option — don't default to it.
- Stripe Connect path: owner connects their Stripe account, FirstBack creates the Payment Link programmatically.
- Deposit link expiry: auto-expire link 48h after booking (Stripe Payment Links support deactivation via API).

---

### Standalone Tests

```
test_deposit_link.py

1. Business with deposit_link set -> booking confirmation includes the link
2. Business with no deposit_link -> confirmation unmodified
3. Long reply + long link -> suffix NOT appended when total > 320 chars
4. deposit_link + deposit_amount both stored via settings POST -> retrieved from db
5. deposit_link + deposit_amount are in _BUSINESS_COLS -> not blanked by profile save
6. open_conversation path: first-turn booking also gets deposit suffix
7. handle_inbound path: reply-turn booking also gets deposit suffix
8. db migration: deposit_link + deposit_amount columns added idempotently
```

**Effort: S (1–2 days) | Risk: Low | Dependency: Owner has a Stripe account and creates a Payment Link (zero FirstBack infra needed)**

---

## Feature 4: GBP Review Dashboard + One-Tap Response Drafts

### What & Why

FirstBack already sends review requests (growth engine). The gap: owners can't see their review trajectory or respond fast — and Google LSA rank correlates with response rate. The Google OAuth flow is already built (google_cal.py). The GBP My Business API uses the same OAuth credentials. This adds: (1) a DB table for reviews, (2) a sync function in `reputation.py`, (3) a dashboard tile, and (4) one-tap AI-drafted responses.

**Coordination note:** The retention agent owns the review-request send side (growth plays) and `review_link` field (already in `_BUSINESS_COLS`). This plan owns the dashboard + response-draft UX only.

---

### MVP Phase (5–7 days)

#### A. GBP API scope

The Google OAuth flow in `google_cal.py` requests `calendar.events` + `calendar.readonly`. Adding the GBP scope requires a scope upgrade. The GBP Reviews API scope is `https://www.googleapis.com/auth/business.manage`.

**File: `google_cal.py` — `SCOPES` constant:**

```python
SCOPES = ("https://www.googleapis.com/auth/calendar.events "
          "https://www.googleapis.com/auth/calendar.readonly "
          "https://www.googleapis.com/auth/business.manage")
```

Existing connected tenants will be asked to re-authorize when the scope changes (OAuth flow redirects them automatically on next use). The `prompt="consent"` is already set in `auth_url()`, so re-auth works with one click.

#### B. DB: reviews table

**Migration in `db.py` `init_db()`:**

```python
c.execute("""
    CREATE TABLE IF NOT EXISTS gbp_reviews (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        business_id     INTEGER NOT NULL,
        review_id       TEXT NOT NULL,
        reviewer_name   TEXT,
        star_rating     INTEGER,   -- 1-5
        comment         TEXT,
        create_time     TEXT,
        update_time     TEXT,
        reply_text      TEXT,      -- current reply in GBP (if any)
        draft_response  TEXT,      -- AI-drafted response (pending owner tap)
        responded_at    TEXT,      -- when we sent a response
        synced_at       TEXT,
        UNIQUE(business_id, review_id)
    )
""")
c.execute("CREATE INDEX IF NOT EXISTS idx_gbp_reviews_biz "
          "ON gbp_reviews(business_id, create_time)")
```

#### C. GBP sync function

**New module: `google_gbp.py`** (mirrors `google_cal.py` shape: gated, defensive, uses same OAuth tokens from `integrations` table):

```python
GBP_API_BASE = "https://mybusinessbusiness.googleapis.com/v1"

def configured():
    return bool(GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET)

def is_connected(business_id):
    # Same integrations table row as google_cal (same OAuth grant)
    return google_cal.is_connected(business_id)

def sync_reviews(business_id, max_reviews=50):
    """Fetch recent GBP reviews for a business and upsert into gbp_reviews.
    Returns list of new/updated review dicts. Never raises."""
    ...
    # 1. Get access token via google_oauth.access_is_fresh / refresh
    # 2. GET /accounts/-/locations/-/reviews (list accounts -> list locations -> list reviews)
    # 3. Upsert into gbp_reviews (INSERT OR REPLACE)
    # 4. For new reviews without draft_response: call _draft_response(biz, review)
    # 5. Return new rows

def _draft_response(biz, review):
    """Use the LLM to draft a review response in the owner's voice."""
    star = review["star_rating"]
    comment = review.get("comment") or ""
    name = review.get("reviewer_name") or "this customer"
    trade = biz.get("trade") or "home services"
    prompt = (
        f"Draft a warm, professional response to this {star}-star Google review for "
        f"a {trade} business. Sound like the owner, not a marketing team. "
        f"Keep it under 100 words. Reviewer: {name}. Review: {comment!r}. "
        f"Output ONLY the response text, no quotes, no intro."
    )
    # Uses llm.py / ai.py's Claude call (same LLM, same cost ledger)
    ...

def post_reply(business_id, review_id, reply_text):
    """Post a reply to a GBP review. Returns True on success."""
    ...
    # PUT /accounts/-/locations/-/reviews/{review_id}/reply
```

#### D. Sync trigger

**Periodic sync:** Add to `/tasks/run-due` (the existing cron endpoint) or a new `/tasks/gbp-sync` (POST, tasks-secret-gated), called once per hour by Render's cron. For MVP, the sync also fires when the owner loads `/dashboard` (async, background thread, same pattern as `google_cal.create_event_async`).

**File: `app.py`** — add to `dashboard()` view:

```python
# Background GBP sync (best-effort; no-op unless Google connected + GBP scope)
if google_gbp.configured() and google_gbp.is_connected(biz["id"]):
    threading.Thread(target=google_gbp.sync_reviews, args=(biz["id"],),
                     daemon=True).start()
```

#### E. Dashboard tile

**New section in `command.html` / `dashboard.html`** (growth tray pattern):

```
+--------------------------------------+
| Google Reviews                        |
| ★ 4.8  (47 reviews)  +3 this month  |
+--------------------------------------+
| New review from Maria S. — ★★★★★     |
| "Showed up on time, great work!"      |
|  [Vic's draft] "Thank you, Maria!..." |
|  [Send reply] [Edit] [Dismiss]        |
+--------------------------------------+
| ⚠ 2 reviews need a response (>48h)  |
+--------------------------------------+
```

**API endpoint: `/api/reviews`** (GET, login_required) — returns `{rating, count, velocity_30d, pending: [...], flagged: [...]}` for the current tenant.

#### F. One-tap response route

**New route in `app.py`:**

```python
@app.route("/api/reviews/<int:review_id>/reply", methods=["POST"])
@login_required
def api_review_reply(review_id):
    """Send (or update) a GBP review reply. Uses the stored draft or an edited version."""
    biz = current_business()
    body = (request.get_json(silent=True) or {})
    text = (body.get("text") or "").strip()
    if not text:
        return jsonify(error="Reply text required."), 400
    ok = google_gbp.post_reply(biz["id"], review_id, text)
    if ok:
        conn = db.get_conn()
        conn.execute(
            "UPDATE gbp_reviews SET reply_text=?, responded_at=? "
            "WHERE business_id=? AND id=?",
            (text, db.now_iso(), biz["id"], review_id))
        conn.commit()
        conn.close()
    return jsonify(ok=ok)
```

---

### Phase 2 additions (1 week extra)

- Daily summary: "You got 2 new reviews today — 1 needs a reply." (Vic / morning briefing integration)
- Negative review alert: if a <3-star review arrives, notify the owner immediately via alert channel.
- Review velocity trend chart in `/analytics`.
- Vic assistant command: "Reply to Maria's review" → pre-populates the confirm card.

---

### Standalone Tests

```
test_gbp_reviews.py

1. sync_reviews with valid OAuth tokens + GBP API mock -> reviews upserted in gbp_reviews table
2. New review without reply -> draft_response generated and stored
3. Review with existing reply -> draft_response not overwritten
4. post_reply success -> gbp_reviews.responded_at set, reply_text updated
5. post_reply with expired token -> refreshes token, retries once, returns True
6. sync_reviews with GBP API error -> swallowed, returns [], no crash
7. GET /api/reviews -> returns rating, count, pending reviews for current tenant only
8. POST /api/reviews/<id>/reply -> sends reply, updates DB row
9. POST /api/reviews/<id>/reply from wrong tenant -> 404
10. DB migration: gbp_reviews table + index created idempotently
11. UNIQUE(business_id, review_id) constraint: duplicate sync upserts cleanly
12. _draft_response: <3-star review -> empathetic tone in draft (smoke test)
13. _draft_response: 5-star review -> warm thank-you in draft (smoke test)
```

**Effort: M (5–7 days) | Risk: Medium (GBP API scope upgrade forces re-auth of connected tenants; GBP API quota limits) | Dependency: Google OAuth connected (already required for Calendar) + GBP My Business API enabled in Google Cloud Console**

---

## Summary Table

| # | Feature | Impact | Effort | Top Dependency |
|---|---------|--------|--------|---------------|
| 1 | Voicemail Transcription → Lead | H | S | Twilio creds + PUBLIC_BASE_URL (already live) |
| 2 | Web-Chat "Text Us" Widget | H | M | `micro_site_slug` set (Go Live wizard); A2P approval |
| 3 | Deposit Link at Booking | H | S | Owner Stripe account + Payment Link URL |
| 4 | GBP Review Dashboard + Response Drafts | H | M | Google OAuth connected; GBP API scope added |

**Recommended build order:** 1 → 3 → 4 → 2

- Start with voicemail (S effort, no new UI, reuses every existing seam exactly).
- Deposit link next (S effort, highest Dave-perceived ROI — kills no-shows immediately).
- GBP dashboard third (M effort, compounds; sets up the review-velocity signal the retention agent wants).
- Widget last (M effort, most moving parts: anti-abuse, JS, new lead source compliance).

**Total effort estimate:** ~2.5–3 weeks one developer.

**Top dependency:** Twilio credentials + `PUBLIC_BASE_URL` set (features 1 and 2 both require a live webhook-reachable deployment — already required for the core missed-call flow to work at all).

---

*Lane: New Lead-Source & Conversion Features. READ-ONLY planning. No code written or modified.*
