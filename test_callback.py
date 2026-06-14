"""Phase 0 callback-system checks. Run: python3 test_callback.py

No framework: prints each check and a summary, exits non-zero on any failure. DB
tests run against a throwaway temp database so the real ringback.db is untouched.
"""
import base64
import hashlib
import hmac
import os
import sys
import tempfile

# Point storage at a temp DB BEFORE importing db so nothing touches ringback.db.
import config
_TMP = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_TMP.close()
config.DB_PATH = _TMP.name

import db
db.DB_PATH = _TMP.name      # db copied DB_PATH at import; override there too
db.init_db()                # builds the schema, incl. the new calls/consent tables

import messaging

_pass = _fail = 0


def check(name, cond):
    global _pass, _fail
    if cond:
        _pass += 1
        print(f"  ok   {name}")
    else:
        _fail += 1
        print(f"FAIL   {name}")


def _reference_sig(token, url, params):
    """Independent re-implementation of Twilio's algorithm, for round-trip tests."""
    data = url + "".join(f"{k}{params[k]}" for k in sorted(params))
    digest = hmac.new(token.encode(), data.encode(), hashlib.sha1).digest()
    return base64.b64encode(digest).decode()


# ---- valid_signature -------------------------------------------------------
TOKEN = "test-auth-token-12345"
URL = "https://app.ringback.test/webhooks/twilio/sms/inbound"
PARAMS = {"From": "+14155551212", "To": "+18005550100", "Body": "hi there",
          "MessageSid": "SM0123456789abcdef"}
good = _reference_sig(TOKEN, URL, PARAMS)
check("valid_signature accepts a correct signature",
      messaging.valid_signature(URL, PARAMS, good, auth_token=TOKEN) is True)
reordered = {k: PARAMS[k] for k in reversed(list(PARAMS))}  # order must not matter
check("valid_signature is param-order independent",
      messaging.valid_signature(URL, reordered, good, auth_token=TOKEN) is True)
check("valid_signature rejects a tampered body",
      messaging.valid_signature(URL, dict(PARAMS, Body="evil"), good,
                                auth_token=TOKEN) is False)
check("valid_signature rejects the wrong auth token",
      messaging.valid_signature(URL, PARAMS, good, auth_token="nope") is False)
check("valid_signature rejects a wrong URL (proxy scheme mismatch)",
      messaging.valid_signature(URL.replace("https", "http"), PARAMS, good,
                                auth_token=TOKEN) is False)
check("valid_signature rejects an empty signature",
      messaging.valid_signature(URL, PARAMS, "", auth_token=TOKEN) is False)


# ---- send_sms simulated / skipped (no network) -----------------------------
messaging.TWILIO_ACCOUNT_SID = ""   # force "not configured" so nothing hits network
messaging.TWILIO_AUTH_TOKEN = ""
check("send_sms simulates when Twilio not configured",
      messaging.send_sms({"id": 1}, "+14155551212", "hello")["status"] == "simulated")
check("send_sms skips an empty destination",
      messaging.send_sms({"id": 1}, "", "hello")["status"] == "skipped")
check("send_sms skips an empty body",
      messaging.send_sms({"id": 1}, "+14155551212", "")["status"] == "skipped")

lead_id = db.create_lead(1, "Tester", "+14155551212")
before = len(db.get_messages(lead_id))
messaging.send_sms({"id": 1}, "+14155551212", "demo reply", lead_id=lead_id)
after = db.get_messages(lead_id)
check("simulated send_sms records the outbound on the lead thread",
      len(after) == before + 1 and after[-1]["direction"] == "out")


# ---- consent / suppression -------------------------------------------------
check("is_suppressed False before any opt-out",
      db.is_suppressed(1, "+14155559999") is False)
db.set_opt_out(1, "(415) 555-9999")  # different formatting, same number
check("is_suppressed True after opt-out (format-independent)",
      db.is_suppressed(1, "+1 415-555-9999") is True)
check("opt-out is scoped per business", db.is_suppressed(2, "+14155559999") is False)
messaging.TWILIO_ACCOUNT_SID = "AC_fake"  # creds present, but recipient opted out
messaging.TWILIO_AUTH_TOKEN = "fake"
messaging.TWILIO_FROM_NUMBER = "+18005550100"
check("send_sms refuses a suppressed recipient (never hits network)",
      messaging.send_sms({"id": 1}, "+14155559999", "no")["status"] == "suppressed")
messaging.TWILIO_ACCOUNT_SID = messaging.TWILIO_AUTH_TOKEN = ""  # back to unconfigured


# ---- tenant lookup by Twilio number ---------------------------------------
db.set_business_twilio(1, "+15553140000", "PN_test")
check("get_business_by_twilio_number matches (formatting-independent)",
      (db.get_business_by_twilio_number("(555) 314-0000") or {}).get("id") == 1)
check("get_business_by_twilio_number matches +1 prefix variants",
      (db.get_business_by_twilio_number("+1 555-314-0000") or {}).get("id") == 1)
check("get_business_by_twilio_number returns None for an unknown number",
      db.get_business_by_twilio_number("+19998887777") is None)


# ---- log_call idempotency --------------------------------------------------
db.log_call(1, "CAtest123", from_number="+14155551212", to_number="+15553140000")
db.log_call(1, "CAtest123", from_number="+14155551212", to_number="+15553140000",
            dial_status="no-answer", missed=1)  # same SID -> update, not insert
conn = db.get_conn()
rows = conn.execute("SELECT * FROM calls WHERE call_sid='CAtest123'").fetchall()
conn.close()
check("log_call is idempotent on call_sid (one row)", len(rows) == 1)
check("log_call updates the outcome on a repeat event",
      bool(rows) and rows[0]["missed"] == 1 and rows[0]["dial_status"] == "no-answer")


# ---- message provider sid + delivery status --------------------------------
db.add_message(lead_id, "out", "sent via twilio", provider_sid="SMabc")
db.set_message_delivery("SMabc", "delivered")
conn = db.get_conn()
row = conn.execute("SELECT * FROM messages WHERE provider_sid='SMabc'").fetchone()
conn.close()
check("set_message_delivery records delivery status by provider sid",
      row is not None and row["delivery_status"] == "delivered")


# ---- summary ---------------------------------------------------------------
os.unlink(_TMP.name)
print(f"\n{_pass} passed, {_fail} failed")
sys.exit(1 if _fail else 0)
