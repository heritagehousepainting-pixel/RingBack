"""Phase 5d BETA -- growth_tray digest + delivery hook tests.
Run: /Users/jonathanmorris/apps/firstback/.venv/bin/python test_growth_tray_sms.py

Covers spec BETA tests 1-8 (SS7):
  1. scan_growth_tray fires when local hour == 8 and held plays exist; no fire outside [8,9).
  2. No digest when zero held plays (even if hour is 8).
  3. Digest fires once per day (dedupe); second tick same day -> no second SMS.
  4. Digest goes to business["alert_sms"] (owner cell), NOT to any lead phone.
  5. Digest body includes play count, money figure, GO/SKIP instructions (<= 320 chars).
  6. is_estimated=True when avg_job_value is NULL -> body contains "(estimated)".
  7. run_due_once: growth-kind 'sent' -> growth_touch_log row written; non-growth -> no row.
  8. run_due_once: growth-kind 'simulated' -> log row written with outcome='simulated'.

Exits 0 on all pass, 1 if any fail.
"""
import os
import sys
import tempfile
from datetime import datetime, timezone, timedelta

os.environ["FIRSTBACK_PROVIDER"] = "demo"   # deterministic, no network

import config
_TMP = tempfile.NamedTemporaryFile(suffix=".db", delete=False); _TMP.close()
config.DB_PATH = _TMP.name

import db
db.DB_PATH = _TMP.name
db.init_db()

import messaging
messaging.TWILIO_ACCOUNT_SID = ""           # configured() False -> simulates

import alerts
import reminders

# Resolve the default app timezone once (used to build deterministic timestamps).
_APP_TZ = config.app_tz()

_pass = _fail = 0

# Per-scope recipient capture list (reset between tests).
_CAPTURED_RECIPIENTS = []


def check(name, cond):
    global _pass, _fail
    if cond:
        _pass += 1
        print(f"  ok   {name}")
    else:
        _fail += 1
        print(f"FAIL   {name}")


# ---- Helpers ----------------------------------------------------------------

def _make_biz(owner_sms, avg_job_value=None):
    """Return a fresh business dict with growth_mode='tray'."""
    bid = db.create_business({"name": "Growth Test Co"})
    conn = db.get_conn()
    conn.execute(
        "UPDATE businesses SET alert_sms=?, alert_on_lead=1, growth_mode='tray' WHERE id=?",
        (owner_sms, bid))
    if avg_job_value is not None:
        conn.execute("UPDATE businesses SET avg_job_value=? WHERE id=?",
                     (avg_job_value, bid))
    conn.commit(); conn.close()
    return db.get_business(bid)


def _make_lead(bid, name, phone):
    return db.create_lead(bid, name, phone)


def _insert_held(bid, lead_id, kind="review_request", body="Test growth msg"):
    """Insert a past-due status='held' scheduled_messages row."""
    send_at = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    conn = db.get_conn()
    conn.execute(
        "INSERT INTO scheduled_messages "
        "(business_id, lead_id, kind, send_at, body, status) VALUES (?,?,?,?,?,?)",
        (bid, lead_id, kind, send_at, body, "held"))
    conn.commit(); conn.close()


def _iso_at_local_hour(h, minute=0, second=0):
    """Return an ISO UTC string whose local (_APP_TZ) representation is at hour h.
    This is deterministic: we anchor to today's local date, set the hour, convert to UTC.
    Avoids wall-clock dependency on 'what hour is it now?'"""
    today_local = datetime.now(_APP_TZ).replace(
        hour=h, minute=minute, second=second, microsecond=0)
    return today_local.astimezone(timezone.utc).isoformat()


def _captured_send(business, to, body, **kwargs):
    _CAPTURED_RECIPIENTS.append((to, body))
    return {"status": "simulated"}


# Patch send_sms globally.
messaging.send_sms = _captured_send


# ---- Test 1: fires at 8am local with held plays; not at 7am or 9am ---------

print("\n=== Test 1: fires at 8am local; no fire at 7am or 9am ===")

_CAPTURED_RECIPIENTS.clear()

# Business at 8am local: should fire.
biz1a = _make_biz("+15550010001")
lid1a = _make_lead(biz1a["id"], "Maria Customer", "+15559991001")
_insert_held(biz1a["id"], lid1a)

now_8am = _iso_at_local_hour(8)
fired1 = reminders.scan_growth_tray(now_8am)
biz1a_sends = [r for r in _CAPTURED_RECIPIENTS if r[0] == biz1a["alert_sms"]]
check("test1: fires at 8am when held plays exist", len(biz1a_sends) >= 1)

# 7am: fresh business to avoid dedupe from biz1a (different business_id).
biz1b = _make_biz("+15550010091")
lid1b = _make_lead(biz1b["id"], "7am Lead", "+15559991091")
_insert_held(biz1b["id"], lid1b)
now_7am = _iso_at_local_hour(7)
reminders.scan_growth_tray(now_7am)
biz1b_sends = [r for r in _CAPTURED_RECIPIENTS if r[0] == biz1b["alert_sms"]]
check("test1: no fire at 7am for this business", len(biz1b_sends) == 0)

# 9am: same idea.
biz1c = _make_biz("+15550010092")
lid1c = _make_lead(biz1c["id"], "9am Lead", "+15559991092")
_insert_held(biz1c["id"], lid1c)
now_9am = _iso_at_local_hour(9)
reminders.scan_growth_tray(now_9am)
biz1c_sends = [r for r in _CAPTURED_RECIPIENTS if r[0] == biz1c["alert_sms"]]
check("test1: no fire at 9am for this business", len(biz1c_sends) == 0)


# ---- Test 2: no digest when zero held plays ---------------------------------

print("\n=== Test 2: no digest when zero held plays ===")

_CAPTURED_RECIPIENTS.clear()
biz2 = _make_biz("+15550010002")
# No held plays inserted.
reminders.scan_growth_tray(_iso_at_local_hour(8, minute=1))
biz2_sends = [r for r in _CAPTURED_RECIPIENTS if r[0] == biz2["alert_sms"]]
check("test2: no digest sent for biz with zero held plays", len(biz2_sends) == 0)


# ---- Test 3: once-per-day dedupe -------------------------------------------

print("\n=== Test 3: digest fires once per day (dedupe) ===")

_CAPTURED_RECIPIENTS.clear()
biz3 = _make_biz("+15550010003")
lid3 = _make_lead(biz3["id"], "Carlos Customer", "+15559991003")
_insert_held(biz3["id"], lid3, "winback")

biz3_sms = biz3["alert_sms"]
# Two ticks same local day, both at hour 8 but different minutes.
now_8_00 = _iso_at_local_hour(8, minute=2)
now_8_15 = _iso_at_local_hour(8, minute=15)

reminders.scan_growth_tray(now_8_00)
count_after_first = len([r for r in _CAPTURED_RECIPIENTS if r[0] == biz3_sms])

reminders.scan_growth_tray(now_8_15)
count_after_second = len([r for r in _CAPTURED_RECIPIENTS if r[0] == biz3_sms])

check("test3: first tick fires exactly once", count_after_first == 1)
check("test3: second tick same day is deduped (count still 1)", count_after_second == 1)


# ---- Test 4: digest to owner cell ONLY, never to lead phone -----------------

print("\n=== Test 4: digest to owner cell only, not to lead numbers ===")

_CAPTURED_RECIPIENTS.clear()
OWNER_4 = "+15550010004"
LEAD_PHONE_4 = "+15559994444"
biz4 = _make_biz(OWNER_4)
lid4 = _make_lead(biz4["id"], "Tom Lead", LEAD_PHONE_4)
_insert_held(biz4["id"], lid4, "review_request")

now_8_4 = _iso_at_local_hour(8, minute=3)
reminders.scan_growth_tray(now_8_4)

recipients_4 = [r[0] for r in _CAPTURED_RECIPIENTS]
check("test4: owner cell received the digest", OWNER_4 in recipients_4)
check("test4: lead phone received ZERO sends", LEAD_PHONE_4 not in recipients_4)


# ---- Test 5: body content -- count, money, GO/SKIP, <= 320 chars -----------

print("\n=== Test 5: body has count, money, GO/SKIP, <= 320 chars ===")

_CAPTURED_RECIPIENTS.clear()
OWNER_5 = "+15550010005"
biz5 = _make_biz(OWNER_5, avg_job_value=2500)
lid5 = _make_lead(biz5["id"], "Alice Customer", "+15559991005")
_insert_held(biz5["id"], lid5, "review_request")

now_8_5 = _iso_at_local_hour(8, minute=4)
reminders.scan_growth_tray(now_8_5)

bodies5 = [r[1] for r in _CAPTURED_RECIPIENTS if r[0] == OWNER_5]
check("test5: digest SMS was sent to owner", len(bodies5) >= 1)
if bodies5:
    body5 = bodies5[0]
    check("test5: body contains text/play count reference",
          any(w in body5 for w in ("text", "play", "1)", "ready")))
    check("test5: body contains money figure ($)", "$" in body5)
    check("test5: body contains 'GO'", "GO" in body5)
    check("test5: body contains 'SKIP'", "SKIP" in body5)
    check("test5: body <= 320 chars", len(body5) <= 320)
else:
    for _ in range(5):
        check("test5: SKIPPED -- no body captured", False)


# ---- Test 6: (estimated) label when avg_job_value is NULL ------------------

print("\n=== Test 6: '(estimated)' label when avg_job_value is NULL ===")

_CAPTURED_RECIPIENTS.clear()
OWNER_6 = "+15550010006"
biz6 = _make_biz(OWNER_6)    # avg_job_value=None (default NULL)
lid6 = _make_lead(biz6["id"], "Bob Customer", "+15559991006")
_insert_held(biz6["id"], lid6, "winback")

now_8_6 = _iso_at_local_hour(8, minute=5)
reminders.scan_growth_tray(now_8_6)

bodies6 = [r[1] for r in _CAPTURED_RECIPIENTS if r[0] == OWNER_6]
check("test6: digest sent when avg_job_value is NULL", len(bodies6) >= 1)
if bodies6:
    check("test6: body contains '(estimated)'", "(estimated)" in bodies6[0])
else:
    check("test6: SKIPPED -- no body", False)


# ---- Test 7: run_due_once growth-kind 'sent' -> growth_touch_log ------------

print("\n=== Test 7: run_due_once growth-kind 'sent' -> growth_touch_log ===")

biz7 = _make_biz("+15550010007")
lid7 = _make_lead(biz7["id"], "Derek Customer", "+15559991007")

send_at7 = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
conn = db.get_conn()
conn.execute(
    "INSERT INTO scheduled_messages "
    "(business_id, lead_id, kind, send_at, body, status) VALUES (?,?,?,?,?,?)",
    (biz7["id"], lid7, "review_request", send_at7, "Hi Derek!", "pending"))
conn.commit(); conn.close()

def _send_sent(business, to, body, **kwargs):
    return {"status": "sent"}

orig_send = messaging.send_sms
messaging.send_sms = _send_sent
reminders.run_due_once()
messaging.send_sms = orig_send

log7 = db.get_conn().execute(
    "SELECT * FROM growth_touch_log WHERE business_id=? AND lead_id=? AND kind='review_request'",
    (biz7["id"], lid7)).fetchone()
check("test7: growth_touch_log row written for growth-kind 'sent'", log7 is not None)
if log7:
    check("test7: outcome='sent'", log7["outcome"] == "sent")

# Non-growth kind: 'followup' must NOT write to growth_touch_log.
biz7b = _make_biz("+15550010017")
lid7b = _make_lead(biz7b["id"], "Eve Customer", "+15559991017")

send_at7b = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
conn = db.get_conn()
conn.execute(
    "INSERT INTO scheduled_messages "
    "(business_id, lead_id, kind, send_at, body, status) VALUES (?,?,?,?,?,?)",
    (biz7b["id"], lid7b, "followup", send_at7b, "Hi Eve!", "pending"))
conn.commit(); conn.close()

messaging.send_sms = _send_sent
reminders.run_due_once()
messaging.send_sms = orig_send

log7b = db.get_conn().execute(
    "SELECT * FROM growth_touch_log WHERE business_id=? AND lead_id=? AND kind='followup'",
    (biz7b["id"], lid7b)).fetchone()
check("test7: non-growth 'followup' does NOT write to growth_touch_log", log7b is None)


# ---- Test 8: run_due_once growth-kind 'simulated' -> log with simulated ----

print("\n=== Test 8: run_due_once growth-kind 'simulated' -> outcome='simulated' ===")

biz8 = _make_biz("+15550010008")
lid8 = _make_lead(biz8["id"], "Frank Customer", "+15559991008")

send_at8 = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
conn = db.get_conn()
conn.execute(
    "INSERT INTO scheduled_messages "
    "(business_id, lead_id, kind, send_at, body, status) VALUES (?,?,?,?,?,?)",
    (biz8["id"], lid8, "winback", send_at8, "Hi Frank, we miss you!", "pending"))
conn.commit(); conn.close()

# send_sms patches to return "simulated".
messaging.send_sms = _captured_send
reminders.run_due_once()

log8 = db.get_conn().execute(
    "SELECT * FROM growth_touch_log WHERE business_id=? AND lead_id=? AND kind='winback'",
    (biz8["id"], lid8)).fetchone()
check("test8: growth_touch_log row written for growth-kind 'simulated'", log8 is not None)
if log8:
    check("test8: outcome='simulated'", log8["outcome"] == "simulated")


# ---- Summary ----------------------------------------------------------------

print(f"\n{'='*50}")
print(f"Results: {_pass} passed, {_fail} failed")
print(f"{'='*50}")
sys.exit(0 if _fail == 0 else 1)
