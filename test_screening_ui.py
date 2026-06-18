"""Phase 5c UI -- screening endpoints + surfaces. Run: python3 test_screening_ui.py

Proves the owner-facing half of F07 graduation: the "This was real" rescue endpoint
(trusts the number + records the false-positive that defers graduation + re-engages, never
double-texting, never re-texting an opt-out), per-tenant sensitivity thresholds flowing
through _screen_missed_caller, the per-tenant paid-reputation gate, and the dashboard
surfaces (blocked counter + graduation cards) rendering. Throwaway temp DB, demo brain.
"""
import os
import re as _re
import tempfile

os.environ["FIRSTBACK_PROVIDER"] = "demo"
import config
_TMP = tempfile.NamedTemporaryFile(suffix=".db", delete=False); _TMP.close()
config.DB_PATH = _TMP.name

import db
db.DB_PATH = _TMP.name

import messaging
messaging.TWILIO_ACCOUNT_SID = ""           # configured() False -> sends simulate

import triage
import reputation
import app as appmod
client = appmod.app.test_client()

_pass = _fail = 0


def check(name, cond):
    global _pass, _fail
    if cond:
        _pass += 1
        print(f"  ok   {name}")
    else:
        _fail += 1
        print(f"FAIL   {name}")


# count real send attempts so a double-text is observable
_sends = []
_orig_send = messaging.send_sms
messaging.send_sms = lambda b, to, body, **k: (_sends.append((to, body)),
                                               _orig_send(b, to, body, **k))[1]

biz = db.get_business(1)
client.post("/login", data={"email": config.SEED_OWNER_EMAIL,
                            "password": config.SEED_OWNER_PASSWORD})


def _screened_call(number, status="screened_spam"):
    """Log a missed call with the given screen verdict; return its call id."""
    db.log_call(1, f"CA{number[-7:]}", from_number=number, to_number="+15550000000",
                missed=1, engaged=0, category="spam", screen_status=status,
                spam_score=88, screen_reasons="looks like spam", screen_mode="enforce")
    rows = db.recent_screened_calls(1, 20)
    return next(c["id"] for c in rows if c["from_number"] == number)


# --- 1) "This was real" rescue: trusts + records false-positive + re-engages once ---
RESCUE = "+15557770001"
cid = _screened_call(RESCUE)
_fp_before = (db.get_business(1).get("screening_false_positives") or 0)
_sends.clear()
r = client.post(f"/api/calls/{cid}/real")
check("rescue endpoint returns ok", r.status_code == 200 and r.get_json().get("ok"))
check("rescued number is now a trusted customer contact",
      (db.get_contact(1, RESCUE) or {}).get("category") == "customer")
check("rescue incremented the false-positive counter",
      (db.get_business(1).get("screening_false_positives") or 0) == _fp_before + 1)
check("rescue texted the caller back exactly once", len(_sends) == 1 and _sends[0][0] == RESCUE)
# a second rescue tap must not re-open + re-text (thread now exists)
_sends.clear()
client.post(f"/api/calls/{cid}/real")
check("a second rescue tap does not double-text", len(_sends) == 0)

# --- 2) rescue resets the graduation window (the safety-valve seam) ---
_ws = db.get_business(1).get("screening_window_start")
check("rescue reset the observation window (graduation deferred)", bool(_ws))

# --- 3) opted-out number can't be rescued ---
OPT = "+15557770002"
cid_opt = _screened_call(OPT)
db.set_opt_out(1, OPT, source="test")
_sends.clear()
r = client.post(f"/api/calls/{cid_opt}/real")
check("an opted-out caller cannot be rescued (no re-text)",
      r.status_code == 400 and len(_sends) == 0)

# --- 4) per-tenant thresholds flow through _screen_missed_caller ---
# A caller flagged by 2 OTHER businesses scores 40 (crowd) -> 'review' band by default
# (hard=80). With a per-tenant hard of 35, the same 40 becomes 'screened_spam'.
SCORED = "+15558880003"
b2 = db.create_business({"name": "B2"}); b3 = db.create_business({"name": "B3"})
db.add_spam_flag(b2, SCORED); db.add_spam_flag(b3, SCORED)
with appmod.app.test_request_context("/"):
    v_default = appmod._screen_missed_caller(db.get_business(1), SCORED)
_c = db.get_conn(); _c.execute("UPDATE businesses SET screen_hard=35, screen_mid=20 WHERE id=1")
_c.commit(); _c.close()
with appmod.app.test_request_context("/"):
    v_strict = appmod._screen_missed_caller(db.get_business(1), SCORED)
check("default thresholds: a crowd=2 caller is NOT hard-screened",
      v_default["status"] != "screened_spam")
check("a stricter per-tenant screen_hard flips the same caller to screened_spam",
      v_strict["status"] == "screened_spam")
# reset thresholds for the next check
_c = db.get_conn(); _c.execute("UPDATE businesses SET screen_hard=NULL, screen_mid=NULL WHERE id=1")
_c.commit(); _c.close()

# --- 5) per-tenant paid-reputation gate ---
_lookups = []
reputation.configured = lambda: True
reputation.lookup = lambda n: (_lookups.append(n), {})[1]
REPCALLER = "+15559990004"
b4 = db.create_business({"name": "B4"}); b5 = db.create_business({"name": "B5"})
db.add_spam_flag(b4, REPCALLER); db.add_spam_flag(b5, REPCALLER)   # crowd=2 -> ambiguous band
_c = db.get_conn(); _c.execute("UPDATE businesses SET reputation_enabled=0 WHERE id=1")
_c.commit(); _c.close()
_lookups.clear()
with appmod.app.test_request_context("/"):
    appmod._screen_missed_caller(db.get_business(1), REPCALLER)
check("reputation toggle OFF: no paid lookup even when provider configured", len(_lookups) == 0)
_c = db.get_conn(); _c.execute("UPDATE businesses SET reputation_enabled=1 WHERE id=1")
_c.commit(); _c.close()
_lookups.clear()
with appmod.app.test_request_context("/"):
    appmod._screen_missed_caller(db.get_business(1), REPCALLER)
check("reputation toggle ON: paid lookup fires in the ambiguous band", len(_lookups) == 1)

# --- 6) cockpit surfaces render (blocked counter + shield card) ---
# The screened-calls strip + Spam Shield card live on /pipeline (the manual cockpit),
# not the conversational command center at /dashboard. biz 1 was rescued above, so its
# observation window is open -> the "Learning" shield card should show.
d = client.get("/pipeline")
html = d.get_data(as_text=True)
check("cockpit renders 200 with the screening surfaces", d.status_code == 200)
check("cockpit exposes the Spam Shield card", "Spam Shield" in html)

print(f"\n{_pass} passed, {_fail} failed")
raise SystemExit(1 if _fail else 0)
