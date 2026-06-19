"""Batch B -- AI conversation + core-loop speed. Regression tests.
Run: /Users/jonathanmorris/apps/firstback/.venv/bin/python test_batch_b.py

  instant_opener  zero-LLM turn-0 opener; open_conversation uses it (not generate_reply).
  urgency         detect_urgency + the is_urgent prompt variant; generate_reply stays safe.
  prompt          persona/price-pivot/Spanish rules present; Spanish gated by the toggle.
  reminder copy   reminder_body/followup_body carry the business phone (degrade without it).
  known caller    a trusted past customer silenced in enforce fires the owner "ring back" alert.
  cap             daily cost cap default raised to $5.
"""
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
import messaging
messaging.TWILIO_ACCOUNT_SID = ""
import ai
import reminders
import alerts
import app as appmod

_pass = _fail = 0
def check(name, cond):
    global _pass, _fail
    if cond:
        _pass += 1; print(f"  ok   {name}")
    else:
        _fail += 1; print(f"FAIL   {name}")

_BIZ = {"id": 1, "name": "Dave's Painting", "trade": "painting", "service_area": "metro",
        "hours": "Mon-Sat 8-6", "ai_instructions": "Be helpful.", "phone": "(555) 123-4567",
        "owner_name": "Dave", "spanish_enabled": True}


# ===========================================================================
# instant_opener + open_conversation
# ===========================================================================
print("\n=== instant_opener (zero-LLM turn 0) ===")
_txt, _book = ai.instant_opener(_BIZ)
check("instant_opener returns a non-empty string + no booking", bool(_txt) and _book is None)
check("instant_opener names the business", "Dave's Painting" in _txt)

# open_conversation must use instant_opener, NOT a cold generate_reply, on the empty thread.
biz1 = db.get_business(1)
lid = db.create_lead(1, "New Caller", "+14155550201")
lead = db.get_lead(lid)
_gen_called = []; _opener_called = []
_o_gen, _o_open, _o_notify = ai.generate_reply, ai.instant_opener, alerts.notify_async
ai.generate_reply = lambda *a, **k: (_gen_called.append(1), ("LLM reply", None))[1]
ai.instant_opener = lambda b: (_opener_called.append(1), ("Instant!", None))[1]
alerts.notify_async = lambda *a, **k: None
try:
    appmod.open_conversation(biz1, lead)
finally:
    ai.generate_reply, ai.instant_opener, alerts.notify_async = _o_gen, _o_open, _o_notify
check("open_conversation uses instant_opener on turn 0", _opener_called == [1])
check("open_conversation does NOT make a cold generate_reply call on turn 0", _gen_called == [])


# ===========================================================================
# urgency
# ===========================================================================
print("\n=== urgency fast-path ===")
check("detect_urgency: 'burst pipe flooding' is urgent", ai.detect_urgency("burst pipe flooding bathroom"))
check("detect_urgency: a normal scheduling msg is not urgent", not ai.detect_urgency("can you come monday"))
_p = ai._system_prompt(_BIZ, [])
_pu = ai._system_prompt_urgent(_BIZ, [])
check("urgent prompt = base prompt + an URGENT injection", _pu.startswith(_p) and "URGENT" in _pu)
# generate_reply must stay safe on an urgent first message (demo mode): non-empty, no booking.
_r, _b = ai.generate_reply(_BIZ, [{"direction": "in", "body": "emergency burst pipe!"}])
check("generate_reply returns a reply on urgent input", bool(_r))
check("generate_reply does not book on the first urgent message", _b is None)


# ===========================================================================
# prompt content: persona + price pivot + Spanish toggle
# ===========================================================================
print("\n=== prompt content ===")
check("prompt tells the AI to sound like a person, not a form", "not a chatbot or a form" in _p)
check("prompt has the price-objection pivot", "Price questions" in _p and "free estimate" in _p)
check("prompt includes the Spanish rule when spanish_enabled", "spanish" in _p.lower())
_p_no_es = ai._system_prompt(dict(_BIZ, spanish_enabled=False), [])
check("prompt OMITS the Spanish rule when spanish_enabled is False", "spanish" not in _p_no_es.lower())


# ===========================================================================
# reminder / followup copy carries the phone
# ===========================================================================
print("\n=== reminder copy ===")
_rb = reminders.reminder_body("Maria Lopez", "Dave's Painting", "Mon Jun 22 at 9:00 AM",
                              phone="(555) 123-4567")
check("reminder_body includes the business phone when given", "(555) 123-4567" in _rb)
check("reminder_body still names the customer + the free estimate", "Maria" in _rb and "free estimate" in _rb)
_rb_no = reminders.reminder_body("Maria", "Dave's Painting", "Mon at 9 AM")
check("reminder_body degrades gracefully without a phone (reply-here)",
      "reply here" in _rb_no.lower() and "(555)" not in _rb_no)
_fb = reminders.followup_body("Sam", "Dave's Painting", phone="(555) 123-4567")
check("followup_body includes the phone when given", "(555) 123-4567" in _fb)


# ===========================================================================
# known-caller owner alert (trusted past customer silenced in enforce)
# ===========================================================================
print("\n=== known-caller alert ===")
check("format_message lead+known is the 'past customer, ring back' copy",
      "Past customer" in alerts.format_message("lead", {"phone": "+14155550300", "known": True}))
check("format_message lead WITHOUT known stays the normal new-lead copy",
      alerts.format_message("lead", {"phone": "+14155550300", "name": "Jo"}).startswith("New lead"))
db.create_lead(1, "Regular Joe", "+14155550300")  # an existing (trusted) lead
_o_mode = appmod._effective_screen_mode
_o_scr = appmod._screen_missed_caller
_o_n = alerts.notify_async
appmod._effective_screen_mode = lambda b: "enforce"
_alerts = []
alerts.notify_async = lambda biz, kind, ctx: _alerts.append((kind, ctx.get("known")))
try:
    appmod._screen_missed_caller = lambda b, c: {"engage": False, "status": "trusted",
        "score": 0, "category": "trusted", "reasons": []}
    appmod._missed_call_textback(biz1, "+14155550300", "CAk", "no-forward")
    check("trusted caller in enforce fires a lead+known owner alert", ("lead", True) in _alerts)
    _alerts.clear()
    appmod._screen_missed_caller = lambda b, c: {"engage": False, "status": "screened_spam",
        "score": 99, "category": "spam", "reasons": ["spam"]}
    appmod._missed_call_textback(biz1, "+14155559999", "CAs", "no-forward")
    check("a screened SPAM caller fires NO owner alert", _alerts == [])
finally:
    appmod._effective_screen_mode = _o_mode
    appmod._screen_missed_caller = _o_scr
    alerts.notify_async = _o_n


# ===========================================================================
# daily cap raised to $5
# ===========================================================================
print("\n=== daily cost cap ===")
check("default daily cost cap is $5", config.CLAUDE_DAILY_COST_CAP_USD == 5.0)


print(f"\n{'='*46}")
print(f"Results: {_pass} passed, {_fail} failed")
try:
    os.unlink(_TMP.name)
except OSError:
    pass
sys.exit(1 if _fail else 0)
