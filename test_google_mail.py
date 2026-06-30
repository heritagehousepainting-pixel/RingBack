"""Gmail email auto-answer (google_mail.py) -- pure-function + gating regression tests.

  gated          configured()/is_connected() false without creds; send simulates; polls 0.
  parse          _parse_message extracts from/subject/body/threading from a Gmail payload.
  body           _extract_body prefers text/plain, walks multipart, falls back to html/snippet.
  build_raw      RFC822 + base64url round-trips with correct In-Reply-To/References threading.
  reply subject  _reply_subject adds one Re: (idempotent) and handles the empty case.

No network: every test hits pure helpers or the gated (unconfigured) no-op paths.
"""
import base64
import os
import sys
import tempfile

os.environ["FIRSTBACK_PROVIDER"] = "demo"
import config
_TMP = tempfile.NamedTemporaryFile(suffix=".db", delete=False); _TMP.close()
config.DB_PATH = _TMP.name
import db
db.DB_PATH = _TMP.name
db.init_db()
# Ensure Gmail reads as UNCONFIGURED for the gating tests regardless of the env.
import google_mail as gm
gm.GOOGLE_CLIENT_ID = ""
gm.GOOGLE_CLIENT_SECRET = ""

_pass = _fail = 0
def check(name, cond):
    global _pass, _fail
    if cond:
        _pass += 1; print(f"  ok   {name}")
    else:
        _fail += 1; print(f"FAIL   {name}")


def _b64url(s):
    return base64.urlsafe_b64encode(s.encode()).decode().rstrip("=")


# ---- gating: a no-op until configured + connected --------------------------
check("configured() false without client id/secret", gm.configured() is False)
check("is_connected() false for an unlinked business", gm.is_connected(1) is False)
check("poll_and_answer_all() is 0 when unconfigured", gm.poll_and_answer_all() == 0)
check("poll_and_answer() is 0 when not connected", gm.poll_and_answer(1) == 0)
check("send_email simulates when not connected",
      gm.send_email(1, "a@b.com", "Hi", "body").get("status") == "simulated")
check("send_email skips an empty body",
      gm.send_email(1, "a@b.com", "Hi", "  ").get("status") == "skipped")
check("mark_read false when not connected", gm.mark_read(1, "m1") is False)

# ---- _parse_message ---------------------------------------------------------
_msg = {
    "id": "m1", "threadId": "t1", "snippet": "snippet text",
    "payload": {
        "mimeType": "multipart/alternative",
        "headers": [
            {"name": "From", "value": "Jane Doe <jane@example.com>"},
            {"name": "Subject", "value": "Painting quote"},
            {"name": "Message-ID", "value": "<abc@mail>"},
            {"name": "References", "value": "<ref1@mail>"},
        ],
        "parts": [
            {"mimeType": "text/html", "body": {"data": _b64url("<p>ignore me</p>")}},
            {"mimeType": "text/plain",
             "body": {"data": _b64url("Do you do exterior painting?")}},
        ],
    },
}
_p = gm._parse_message(_msg)
check("parse: from_email", _p["from_email"] == "jane@example.com")
check("parse: from_name", _p["from_name"] == "Jane Doe")
check("parse: subject", _p["subject"] == "Painting quote")
check("parse: prefers text/plain body", _p["body"] == "Do you do exterior painting?")
check("parse: thread_id + message_id", _p["thread_id"] == "t1" and _p["message_id"] == "<abc@mail>")
check("parse: references", _p["references"] == "<ref1@mail>")

# ---- _extract_body fallbacks ------------------------------------------------
_html_only = {"mimeType": "text/html", "body": {"data": _b64url("<b>Hello</b> there")}}
check("body: strips html when no text/plain", "Hello" in gm._extract_body(_html_only))
_nested = {"mimeType": "multipart/mixed", "parts": [
    {"mimeType": "multipart/alternative", "parts": [
        {"mimeType": "text/plain", "body": {"data": _b64url("nested plain")}}]}]}
check("body: walks nested multipart", gm._extract_body(_nested) == "nested plain")
check("body: empty payload -> ''", gm._extract_body({}) == "")

# ---- build_raw threading ----------------------------------------------------
_raw = gm.build_raw("me@biz.com", "jane@example.com", "Re: Painting quote",
                    "We sure do!", in_reply_to="<abc@mail>", references="<ref1@mail>")
_dec = base64.urlsafe_b64decode(_raw + "=" * (-len(_raw) % 4)).decode()
check("build_raw: To header", "To: jane@example.com" in _dec)
check("build_raw: From header", "From: me@biz.com" in _dec)
check("build_raw: Subject header", "Subject: Re: Painting quote" in _dec)
check("build_raw: In-Reply-To", "In-Reply-To: <abc@mail>" in _dec)
check("build_raw: References chains prior + replied", "References: <ref1@mail> <abc@mail>" in _dec)
# MIMEText base64-encodes a utf-8 body (standard CTE), so decode the MIME to read it back.
import email as _email
_parsed_mime = _email.message_from_string(_dec)
check("build_raw: body round-trips",
      _parsed_mime.get_payload(decode=True).decode("utf-8") == "We sure do!")

# ---- _reply_subject ---------------------------------------------------------
check("reply_subject adds one Re:", gm._reply_subject("Painting quote") == "Re: Painting quote")
check("reply_subject idempotent on Re:", gm._reply_subject("Re: already") == "Re: already")
check("reply_subject empty -> default", gm._reply_subject("") == "Re: your message")

print(f"\n{'='*46}")
print(f"Results: {_pass} passed, {_fail} failed")
try:
    os.unlink(_TMP.name)
except OSError:
    pass
sys.exit(1 if _fail else 0)
