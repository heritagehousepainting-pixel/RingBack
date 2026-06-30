"""Gmail email auto-answer for FirstBack -- Vic reads a contractor's inbound email leads
and replies as the contractor, the same way a missed call gets a text-back.

A SEPARATE Google OAuth connection from Calendar (google_cal.py) and Contacts
(google_contacts.py), by design: a contractor links email independently and is never
forced to re-consent for the others. It uses the SAME Google app credentials
(GOOGLE_CLIENT_ID/SECRET) but its own redirect URI, its own integrations row
(provider='google_mail'), and the Gmail scope.

Like the sibling modules it is:
  * Gated: a safe no-op unless CONFIGURED (client id/secret set) and the business is
    CONNECTED (has a refresh token). Every public entry point returns an empty/zero
    result when not ready, so importing/calling this is harmless until the owner links.
  * Defensive: every network/API error is swallowed and logged with the "[firstback]"
    prefix, never raised into a request or a cron tick.
  * Light: raw `requests` against the Gmail REST API, no Google SDK.

⚠️ SCOPE NOTE: reading inbound mail needs a Google "restricted" scope (gmail.modify here,
which also lets us mark a handled mail read so it isn't answered twice). Restricted scopes
require Google app verification (a CASA security assessment) before going to 100+ external
users. While in testing you can add contractors as OAuth "test users" (up to 100) with no
verification. If you'd rather avoid the restricted-scope review entirely, the alternative is
Gmail *forwarding* to an inbound-parse address + `gmail.send` (a lighter "sensitive" scope) --
swap SCOPES to gmail.send and feed inbound from the forwarder instead of fetch_unread().
"""
import base64
import sys
from datetime import datetime, timedelta, timezone
from email.mime.text import MIMEText
from email.utils import parseaddr
from urllib.parse import urlencode

import db
from google_oauth import access_is_fresh
from config import (GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, GOOGLE_MAIL_REDIRECT_URI)

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
GMAIL_API = "https://gmail.googleapis.com/gmail/v1/users/me"
# gmail.modify = read messages + send + add/remove labels (to mark handled mail read).
SCOPES = "https://www.googleapis.com/auth/gmail.modify"
PROVIDER = "google_mail"
_MAX_UNREAD = 10          # cap per poll so a flooded inbox can't stall a cron tick


def configured():
    """True if the app has Google OAuth credentials at all (shared with Cal/Contacts)."""
    return bool(GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET)


def is_connected(business_id):
    """True if this business has linked Gmail (has a refresh token)."""
    intg = db.get_integration(business_id, PROVIDER)
    return bool(intg and intg.get("connected") and intg.get("refresh_token"))


# ---- OAuth flow (mirrors google_contacts: own redirect + scope + provider) ----
def auth_url(state):
    return AUTH_URL + "?" + urlencode({
        "client_id": GOOGLE_CLIENT_ID,
        "redirect_uri": GOOGLE_MAIL_REDIRECT_URI,
        "response_type": "code",
        "scope": SCOPES,
        "access_type": "offline",           # ask for a refresh token
        "prompt": "consent",                # ensure a refresh token is returned
        "include_granted_scopes": "false",  # keep email independent of cal/contacts
        "state": state,
    })


def connect_with_code(business_id, code):
    """Exchange an auth code for tokens and store them for the business."""
    import requests
    r = requests.post(TOKEN_URL, data={
        "code": code,
        "client_id": GOOGLE_CLIENT_ID,
        "client_secret": GOOGLE_CLIENT_SECRET,
        "redirect_uri": GOOGLE_MAIL_REDIRECT_URI,
        "grant_type": "authorization_code",
    }, timeout=30)
    r.raise_for_status()
    tok = r.json()
    db.set_oauth_tokens(business_id, PROVIDER, tok.get("access_token"),
                        tok.get("refresh_token"), _expiry_iso(tok))


def disconnect(business_id):
    """Forget this business's Gmail tokens (clears the refresh token, a clean disconnect)."""
    db.set_oauth_tokens(business_id, PROVIDER, None, None, None)


def _expiry_iso(tok):
    secs = int(tok.get("expires_in", 3600))
    return (datetime.now(timezone.utc) + timedelta(seconds=secs)).isoformat()


def _access_token(business_id):
    """A valid access token for the business, refreshing if needed. None if not connected
    or a refresh fails."""
    intg = db.get_integration(business_id, PROVIDER)
    if not intg or not intg.get("refresh_token"):
        return None
    if intg.get("access_token") and access_is_fresh(intg.get("token_expiry")):
        return intg["access_token"]
    import requests
    try:
        r = requests.post(TOKEN_URL, data={
            "client_id": GOOGLE_CLIENT_ID,
            "client_secret": GOOGLE_CLIENT_SECRET,
            "refresh_token": intg["refresh_token"],
            "grant_type": "refresh_token",
        }, timeout=30)
        r.raise_for_status()
        tok = r.json()
        db.set_oauth_tokens(business_id, PROVIDER, tok.get("access_token"),
                            tok.get("refresh_token") or intg["refresh_token"],
                            _expiry_iso(tok))
        return tok.get("access_token")
    except Exception as e:
        print(f"[firstback] gmail token refresh failed (biz {business_id}): {e}",
              file=sys.stderr, flush=True)
        return None


# ---- Inbound: read unread lead emails -------------------------------------
def fetch_unread(business_id, max_results=_MAX_UNREAD):
    """Unread inbound emails for the business as a list of parsed dicts:
        {id, thread_id, from_email, from_name, subject, body, message_id, references}
    Returns [] if not connected or on any error (defensive). Excludes mail the contractor
    sent (-from:me) and chats, and only looks at the primary inbox category so promo /
    notification noise doesn't get auto-answered."""
    token = _access_token(business_id)
    if not token:
        return []
    import requests
    headers = {"Authorization": f"Bearer {token}"}
    q = "is:unread -from:me -in:chats category:primary newer_than:7d"
    out = []
    try:
        r = requests.get(f"{GMAIL_API}/messages", headers=headers,
                         params={"q": q, "maxResults": max_results}, timeout=30)
        r.raise_for_status()
        ids = [m["id"] for m in (r.json().get("messages") or [])]
    except Exception as e:
        print(f"[firstback] gmail list failed (biz {business_id}): {e}",
              file=sys.stderr, flush=True)
        return []
    for mid in ids:
        try:
            mr = requests.get(f"{GMAIL_API}/messages/{mid}", headers=headers,
                              params={"format": "full"}, timeout=30)
            mr.raise_for_status()
            parsed = _parse_message(mr.json())
            if parsed and parsed.get("from_email"):
                out.append(parsed)
        except Exception as e:
            print(f"[firstback] gmail get failed (biz {business_id}, msg {mid}): {e}",
                  file=sys.stderr, flush=True)
    return out


def _header(headers, name):
    """Case-insensitive single header lookup from a Gmail payload headers list."""
    for h in headers or []:
        if (h.get("name") or "").lower() == name.lower():
            return h.get("value") or ""
    return ""


def _decode_part(data):
    """Gmail base64url-encodes body data; decode to text, tolerant of padding."""
    if not data:
        return ""
    try:
        pad = "=" * (-len(data) % 4)
        return base64.urlsafe_b64decode(data + pad).decode("utf-8", "replace")
    except Exception:
        return ""


def _extract_body(payload):
    """Best-effort plain-text body from a Gmail message payload. Prefers text/plain;
    walks multipart trees; falls back to a stripped text/html, then the snippet."""
    if not payload:
        return ""
    mime = payload.get("mimeType", "")
    body = payload.get("body", {})
    if mime == "text/plain" and body.get("data"):
        return _decode_part(body["data"])
    parts = payload.get("parts") or []
    # Depth-first: a text/plain anywhere wins.
    for p in parts:
        if p.get("mimeType") == "text/plain" and p.get("body", {}).get("data"):
            return _decode_part(p["body"]["data"])
    for p in parts:
        nested = _extract_body(p)
        if nested:
            return nested
    if mime == "text/html" and body.get("data"):
        import re
        return re.sub(r"<[^>]+>", " ", _decode_part(body["data"])).strip()
    return ""


def _parse_message(msg):
    """A raw Gmail message dict -> {id, thread_id, from_email, from_name, subject, body,
    message_id, references}. Pure (no network), so it unit-tests without OAuth."""
    payload = msg.get("payload", {})
    headers = payload.get("headers", [])
    from_name, from_email = parseaddr(_header(headers, "From"))
    body = _extract_body(payload) or msg.get("snippet", "") or ""
    return {
        "id": msg.get("id"),
        "thread_id": msg.get("threadId"),
        "from_email": (from_email or "").strip(),
        "from_name": (from_name or "").strip(),
        "subject": _header(headers, "Subject"),
        "body": body.strip(),
        "message_id": _header(headers, "Message-ID"),
        "references": _header(headers, "References"),
    }


def mark_read(business_id, message_id):
    """Remove the UNREAD label so a handled email is not answered again. Best-effort:
    a failure here just means it may be re-seen next poll (the conversation thread guards
    against a duplicate auto-reply at a higher level)."""
    token = _access_token(business_id)
    if not token or not message_id:
        return False
    import requests
    try:
        r = requests.post(f"{GMAIL_API}/messages/{message_id}/modify",
                          headers={"Authorization": f"Bearer {token}"},
                          json={"removeLabelIds": ["UNREAD"]}, timeout=30)
        r.raise_for_status()
        return True
    except Exception as e:
        print(f"[firstback] gmail mark_read failed (biz {business_id}): {e}",
              file=sys.stderr, flush=True)
        return False


# ---- Outbound: send a reply AS the contractor -----------------------------
def build_raw(from_addr, to_addr, subject, body, in_reply_to=None, references=None):
    """RFC822 message, base64url-encoded for the Gmail send API. Pure + testable. Sets the
    threading headers so the reply lands in the same conversation the customer started."""
    msg = MIMEText(body, "plain", "utf-8")
    msg["To"] = to_addr
    if from_addr:
        msg["From"] = from_addr
    msg["Subject"] = subject
    if in_reply_to:
        msg["In-Reply-To"] = in_reply_to
        msg["References"] = (references + " " + in_reply_to).strip() if references else in_reply_to
    raw = msg.as_bytes()
    return base64.urlsafe_b64encode(raw).decode("ascii")


def send_email(business_id, to, subject, body, thread_id=None,
               in_reply_to=None, references=None, from_addr=None):
    """Send an email as the connected contractor via Gmail. Returns a status dict:
    {'status': 'sent', 'id': ...} | {'status': 'simulated'} (not connected/unconfigured) |
    {'status': 'error', 'error': ...}. Never raises."""
    if not to or not (body or "").strip():
        return {"status": "skipped", "reason": "no destination or empty body"}
    token = _access_token(business_id)
    if not token:
        # Gated: behave like the SMS simulator -- honest about not really sending.
        return {"status": "simulated"}
    import requests
    payload = {"raw": build_raw(from_addr, to, subject, body, in_reply_to, references)}
    if thread_id:
        payload["threadId"] = thread_id
    try:
        r = requests.post(f"{GMAIL_API}/messages/send",
                          headers={"Authorization": f"Bearer {token}"},
                          json=payload, timeout=30)
        r.raise_for_status()
        return {"status": "sent", "id": r.json().get("id")}
    except Exception as e:
        print(f"[firstback] gmail send failed (biz {business_id}): {e}",
              file=sys.stderr, flush=True)
        return {"status": "error", "error": str(e)}


# ---- The auto-answer loop -------------------------------------------------
def _reply_subject(subject):
    s = (subject or "").strip()
    return s if s[:3].lower() == "re:" else f"Re: {s}" if s else "Re: your message"


def poll_and_answer(business_id):
    """For each unread inbound email: have Vic (the shared conversation brain) draft a reply,
    send it as the contractor in the same thread, and mark the original read so it is never
    answered twice. Returns the count answered. Defensive: one bad email never stops the rest,
    and the whole thing is a no-op when Gmail isn't connected. Wired into /tasks/run-due."""
    import ai
    import messaging
    from growth import _TONE_RISK_KEYWORDS
    biz = db.get_business(business_id)
    if not biz or not is_connected(business_id):
        return 0
    answered = 0
    for mail in fetch_unread(business_id):
        try:
            prompt_body = (mail["subject"] + "\n\n" + mail["body"]).strip()
            # GA-5: tone-risk gate. Mirror the SMS suppression — if the email reads as upset, do
            # NOT auto-reply into the booking flow. Skip it and alert the owner to handle it.
            low = prompt_body.lower()
            if any(kw in low for kw in _TONE_RISK_KEYWORDS):
                owner_cell = (biz.get("alert_sms") or biz.get("phone") or "").strip()
                if owner_cell:
                    sender = (mail.get("from_name") or mail.get("from_email") or "A customer")
                    messaging.send_sms(
                        biz, owner_cell,
                        f"FirstBack: email from {sender} looks upset — I held off auto-replying. "
                        "Open your inbox to handle it personally.", gate=False)
                mark_read(business_id, mail["id"])   # don't re-flag it every poll
                continue
            # Reuse the exact same brain the SMS/voice paths use: a one-message inbound
            # history. generate_reply is internally defensive (falls back to the demo brain
            # on any provider error), so this never throws on an API hiccup.
            history = [{"direction": "in", "body": prompt_body}]
            reply_text, _slot = ai.generate_reply(biz, history)
            if not (reply_text or "").strip():
                continue
            result = send_email(
                business_id, mail["from_email"], _reply_subject(mail["subject"]),
                reply_text, thread_id=mail.get("thread_id"),
                in_reply_to=mail.get("message_id"), references=mail.get("references"),
                from_addr=biz.get("email") or biz.get("contact_email"))
            if result.get("status") in ("sent", "simulated"):
                mark_read(business_id, mail["id"])
                answered += 1
        except Exception as e:
            print(f"[firstback] gmail auto-answer failed (biz {business_id}): {e}",
                  file=sys.stderr, flush=True)
    return answered


def poll_and_answer_all():
    """Cron seam (/tasks/run-due): auto-answer email for every Gmail-connected business.
    Returns the total answered across tenants. Never raises."""
    if not configured():
        return 0
    total = 0
    for biz in db.list_businesses():
        try:
            if is_connected(biz["id"]):
                total += poll_and_answer(biz["id"])
        except Exception as e:
            print(f"[firstback] gmail poll_all failed (biz {biz.get('id')}): {e}",
                  file=sys.stderr, flush=True)
    return total
