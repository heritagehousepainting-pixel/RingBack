"""Regression tests for the podcast-plan Phase 1 build (PODCAST_APPLIED_PLAN.md).

  GA-1  _trade_tone keys urgency vs consultation; injected into _system_prompt.
  OA-9  first-call nudge fires once (P2P owner SMS) on the first voice turn_log, then never again.
  GA-5  email tone-risk gate: an upset email is NOT auto-replied; the owner is alerted.
  TO-1  daily ops brief: gated off without OPS sms; sends once/day, deduped via meta.
"""
import os
import sys
import tempfile

os.environ["FIRSTBACK_PROVIDER"] = "demo"
os.environ["FIRSTBACK_DB_PATH"] = tempfile.NamedTemporaryFile(suffix=".db", delete=False).name
os.environ["FIRSTBACK_OWNER_EMAIL"] = "o@x.local"
os.environ["FIRSTBACK_OWNER_PASSWORD"] = "test1234"
os.environ["FIRSTBACK_INTERNAL_SECRET"] = "sek"
import db
db.init_db()
import ai
import messaging

_pass = _fail = 0
def check(name, cond):
    global _pass, _fail
    if cond:
        _pass += 1; print(f"  ok   {name}")
    else:
        _fail += 1; print(f"FAIL   {name}")


# ---- GA-1: trade-aware tone ------------------------------------------------
check("GA-1 plumbing -> urgency tone", "urgent" in ai._trade_tone("Plumbing").lower())
check("GA-1 painting -> consultation tone", "estimate" in ai._trade_tone("Painting").lower())
check("GA-1 unknown trade -> no extra line", ai._trade_tone("Pottery") == "")
_biz = {"name": "Joe", "trade": "HVAC", "service_area": "metro", "hours": "9-5",
        "ai_instructions": "Be helpful.", "spanish_enabled": False}
check("GA-1 tone injected into system prompt", "urgent" in ai._system_prompt(_biz, []).lower())

# ---- OA-9: first-call nudge fires once -------------------------------------
import app
_sent = {}
messaging.send_sms = lambda biz, to, body, **k: (_sent.update({"to": to, "body": body}) or {"status": "simulated"})
_conn = db.get_conn(); _conn.execute("UPDATE businesses SET alert_sms='+14155550111' WHERE id=1"); _conn.commit(); _conn.close()
_lid = db.create_lead(1, "Jane Caller", "+14155550123")
_c = app.app.test_client()
_h = {"X-Internal-Secret": "sek"}
_r = _c.post("/internal/voice/turn_log", json={"biz": 1, "lead": _lid, "turns": [{"in": "hi", "out": "hello"}]}, headers=_h)
check("OA-9 turn_log 200", _r.status_code == 200)
check("OA-9 nudge sent to owner cell", _sent.get("to") == "+14155550111")
check("OA-9 flag set", bool(db.get_business(1).get("first_call_nudge_sent")))
_sent.clear()
_c.post("/internal/voice/turn_log", json={"biz": 1, "lead": _lid, "turns": [{"in": "again", "out": "ok"}]}, headers=_h)
check("OA-9 does NOT nudge a second time", not _sent)

# ---- GA-5: email tone-risk gate --------------------------------------------
import google_mail as gm
gm.is_connected = lambda b: True
gm.mark_read = lambda b, mid: None
gm.send_email = lambda *a, **k: _replies.update(n=_replies["n"] + 1) or {"status": "sent"}
_replies = {"n": 0}
_sent.clear()
gm.fetch_unread = lambda b: [{"id": "m1", "thread_id": "t", "from_email": "mad@x.com",
                              "from_name": "Mad Max", "subject": "disappointed",
                              "body": "this is terrible", "message_id": "<a>", "references": ""}]
gm.poll_and_answer(1)
check("GA-5 upset email is NOT auto-replied", _replies["n"] == 0)
check("GA-5 owner alerted about upset email", _sent.get("to") == "+14155550111")
# a normal email IS answered
_replies["n"] = 0; _sent.clear()
gm.fetch_unread = lambda b: [{"id": "m2", "thread_id": "t", "from_email": "ok@x.com",
                              "from_name": "Calm Cathy", "subject": "quote",
                              "body": "do you do exterior painting", "message_id": "<b>", "references": ""}]
gm.poll_and_answer(1)
check("GA-5 normal email IS auto-replied", _replies["n"] == 1)

# ---- TO-1: daily ops brief -------------------------------------------------
import ops
check("TO-1 gated off without OPS sms", ops.daily_ops_brief() is False)
ops.OPS_BRIEF_SMS = "+14155550111"
_sent.clear()
check("TO-1 sends once when configured", ops.daily_ops_brief() is True)
check("TO-1 brief went to owner", _sent.get("to") == "+14155550111")
check("TO-1 deduped same day", ops.daily_ops_brief() is False)

print(f"\n{'='*46}")
print(f"Results: {_pass} passed, {_fail} failed")
sys.exit(1 if _fail else 0)
