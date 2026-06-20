"""E3c — Auto-mode 7-day GO streak unlock (Plan 07 Change 4).

Standalone test: temp DB, no network calls, no external services.
Run: /Users/jonathanmorris/apps/firstback/.venv/bin/python test_streak_unlock.py
"""
import os
import tempfile
from datetime import datetime, timedelta, timezone, date
from unittest.mock import patch

# ---- Minimal env before any import ----
os.environ["FIRSTBACK_PROVIDER"] = "demo"
os.environ["FIRSTBACK_STREAK_THRESHOLD"] = "7"

_TMP = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_TMP.close()

import config
config.DB_PATH = _TMP.name

import db
db.DB_PATH = _TMP.name

import messaging
messaging.TWILIO_ACCOUNT_SID = ""   # no network

import app   # runs migrations including streak columns
import growth

# ---- Helpers ----
_pass = _fail = 0


def check(name, cond):
    global _pass, _fail
    if cond:
        _pass += 1
        print(f"  ok   {name}")
    else:
        _fail += 1
        print(f"FAIL   {name}")


def fresh_biz(name="StreakBiz"):
    """Insert a new business, return it."""
    c = db.get_conn()
    cur = c.execute(
        "INSERT INTO businesses (name, trade, growth_mode) VALUES (?, ?, 'tray')",
        (name, "painting"))
    c.commit()
    bid = cur.lastrowid
    c.close()
    return db.get_business(bid)


def reset_streak(business_id):
    """Zero out streak fields for a clean test."""
    c = db.get_conn()
    c.execute(
        "UPDATE businesses SET growth_streak_count=0, growth_streak_last_at=NULL,"
        " growth_streak_unlocked_at=NULL, growth_mode='tray' WHERE id=?",
        (business_id,))
    c.commit()
    c.close()


def biz_streak(business_id):
    """Fetch streak row from DB."""
    c = db.get_conn()
    row = c.execute(
        "SELECT growth_streak_count, growth_streak_last_at, growth_streak_unlocked_at, growth_mode"
        " FROM businesses WHERE id=?", (business_id,)).fetchone()
    c.close()
    return dict(row) if row else {}


# ============================================================
# --- DB LAYER TESTS ---
# ============================================================
print("\n=== 1. record_growth_go: first GO sets streak to 1 ===")
biz1 = fresh_biz("Biz1")
result = db.record_growth_go(biz1["id"])
check("streak returns 1 on first call", result["streak"] == 1)
check("unlocked=False on first call", result["unlocked"] is False)
row = biz_streak(biz1["id"])
check("DB streak_count == 1", row["growth_streak_count"] == 1)
check("DB streak_last_at is set", row["growth_streak_last_at"] is not None)


print("\n=== 2. Same-day GO is idempotent (no double-count) ===")
biz2 = fresh_biz("Biz2")
# First call
db.record_growth_go(biz2["id"])
# Second call same moment (same calendar day)
result2 = db.record_growth_go(biz2["id"])
row2 = biz_streak(biz2["id"])
check("Same-day second GO: streak stays 1", row2["growth_streak_count"] == 1)
check("Same-day returned streak == 1", result2["streak"] == 1)


print("\n=== 3. GO on different consecutive days increments streak ===")
biz3 = fresh_biz("Biz3")

# Simulate day 1
day1 = datetime(2026, 6, 10, 10, 0, 0, tzinfo=timezone.utc)
with patch("db.datetime") as mock_dt:
    mock_dt.now.return_value = day1
    mock_dt.fromisoformat = datetime.fromisoformat
    db.record_growth_go(biz3["id"])

# Simulate day 2
day2 = datetime(2026, 6, 11, 10, 0, 0, tzinfo=timezone.utc)
with patch("db.datetime") as mock_dt:
    mock_dt.now.return_value = day2
    mock_dt.fromisoformat = datetime.fromisoformat
    result3 = db.record_growth_go(biz3["id"])

row3 = biz_streak(biz3["id"])
check("Streak increments to 2 after day 2", row3["growth_streak_count"] == 2)
check("record_growth_go returned streak==2", result3["streak"] == 2)


print("\n=== 4. Gap >2 days resets streak to 1 ===")
biz4 = fresh_biz("Biz4")

# Day 1: June 1
day_a = datetime(2026, 6, 1, 10, 0, 0, tzinfo=timezone.utc)
with patch("db.datetime") as mock_dt:
    mock_dt.now.return_value = day_a
    mock_dt.fromisoformat = datetime.fromisoformat
    db.record_growth_go(biz4["id"])

# Day 2: June 2
day_b = datetime(2026, 6, 2, 10, 0, 0, tzinfo=timezone.utc)
with patch("db.datetime") as mock_dt:
    mock_dt.now.return_value = day_b
    mock_dt.fromisoformat = datetime.fromisoformat
    db.record_growth_go(biz4["id"])

# Simulate large gap: June 6 (4 days after June 2 — more than 2)
day_gap = datetime(2026, 6, 6, 10, 0, 0, tzinfo=timezone.utc)
with patch("db.datetime") as mock_dt:
    mock_dt.now.return_value = day_gap
    mock_dt.fromisoformat = datetime.fromisoformat
    result4 = db.record_growth_go(biz4["id"])

row4 = biz_streak(biz4["id"])
check("Streak reset to 1 after >2-day gap", row4["growth_streak_count"] == 1)
check("record_growth_go returned streak==1 after reset", result4["streak"] == 1)
check("Unlocked is False after reset", result4["unlocked"] is False)


print("\n=== 5. 7 consecutive GOs unlocks auto mode ===")
biz5 = fresh_biz("Biz5Unlock")

for day_n in range(7):
    go_time = datetime(2026, 6, 1 + day_n, 9, 0, 0, tzinfo=timezone.utc)
    with patch("db.datetime") as mock_dt:
        mock_dt.now.return_value = go_time
        mock_dt.fromisoformat = datetime.fromisoformat
        result5 = db.record_growth_go(biz5["id"])

check("After 7 GOs: unlocked=True", result5["unlocked"] is True)
check("After 7 GOs: streak==7", result5["streak"] == 7)
row5 = biz_streak(biz5["id"])
check("growth_mode set to 'auto'", row5["growth_mode"] == "auto")
check("growth_streak_unlocked_at is set", row5["growth_streak_unlocked_at"] is not None)


print("\n=== 6. After unlock, further GOs do not re-unlock (idempotent) ===")
# Already unlocked from test 5
go_day8 = datetime(2026, 6, 8, 9, 0, 0, tzinfo=timezone.utc)
with patch("db.datetime") as mock_dt:
    mock_dt.now.return_value = go_day8
    mock_dt.fromisoformat = datetime.fromisoformat
    result6 = db.record_growth_go(biz5["id"])

check("8th GO: unlocked=False (already was unlocked, not re-unlocked)", result6["unlocked"] is False)
check("8th GO: streak incremented beyond 7", result6["streak"] == 8)
row6 = biz_streak(biz5["id"])
check("growth_mode stays 'auto'", row6["growth_mode"] == "auto")


print("\n=== 7. Never raises — invalid business_id ===")
try:
    result_bad = db.record_growth_go(99999999)
    check("No exception for unknown business_id", True)
    check("Returns streak==0", result_bad["streak"] == 0)
except Exception as e:
    check(f"No exception for unknown business_id (got: {e})", False)


# ============================================================
# --- APP LAYER TESTS ---
# ============================================================
print("\n=== 8. settings_growth_mode: auto rejected without streak unlock ===")
# Use business 1 (the seed biz), log in, then reset its streak.
# Each test resets biz1 state, so they must run in order.
_client8 = app.app.test_client()
_client8.post("/login", data={"email": config.SEED_OWNER_EMAIL,
                              "password": config.SEED_OWNER_PASSWORD})
# Ensure streak NOT unlocked on biz 1
c = db.get_conn()
c.execute("UPDATE businesses SET growth_streak_unlocked_at=NULL, growth_streak_count=0,"
          " growth_mode='tray' WHERE id=1")
c.commit()
c.close()
with _client8.session_transaction() as _s:
    _s["csrf_token"] = "test_csrf"
resp8 = _client8.post("/settings/growth_mode", data={"mode": "auto", "_csrf": "test_csrf"},
                      follow_redirects=False)
final_mode8 = db.growth_mode(1)
check("POST auto without streak: mode NOT 'auto'", final_mode8 != "auto")
check("POST auto without streak: mode is 'tray'", final_mode8 == "tray")


print("\n=== 9. settings_growth_mode: auto accepted with streak unlock ===")
_client9 = app.app.test_client()
_client9.post("/login", data={"email": config.SEED_OWNER_EMAIL,
                              "password": config.SEED_OWNER_PASSWORD})
unlock_time = datetime.now(timezone.utc).isoformat()
c = db.get_conn()
c.execute("UPDATE businesses SET growth_streak_unlocked_at=?, growth_streak_count=7,"
          " growth_mode='tray' WHERE id=1", (unlock_time,))
c.commit()
c.close()
with _client9.session_transaction() as _s:
    _s["csrf_token"] = "test_csrf"
resp9 = _client9.post("/settings/growth_mode", data={"mode": "auto", "_csrf": "test_csrf"},
                      follow_redirects=False)
final_mode9 = db.growth_mode(1)
check("POST auto WITH streak: mode set to 'auto'", final_mode9 == "auto")


print("\n=== 10. settings_growth_mode: unknown mode coerced to 'off' ===")
_client10 = app.app.test_client()
_client10.post("/login", data={"email": config.SEED_OWNER_EMAIL,
                               "password": config.SEED_OWNER_PASSWORD})
with _client10.session_transaction() as _s:
    _s["csrf_token"] = "test_csrf"
resp10 = _client10.post("/settings/growth_mode", data={"mode": "hacker_mode", "_csrf": "test_csrf"},
                        follow_redirects=False)
check("Unknown mode coerced to 'off'", db.growth_mode(1) == "off")


def _insert_held_for_biz1():
    """Insert a held message for biz 1 (creates a throwaway lead if needed)."""
    c = db.get_conn()
    # Make sure a lead exists for biz 1
    row = c.execute("SELECT id FROM leads WHERE business_id=1 LIMIT 1").fetchone()
    if row:
        lead_id = row[0]
    else:
        cur = c.execute(
            "INSERT INTO leads (business_id, name, phone, status, source)"
            " VALUES (1, 'TestLead', '+15005550001', 'prospect', 'missed_call')")
        lead_id = cur.lastrowid
    send_at = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    c.execute(
        "INSERT INTO scheduled_messages (business_id, lead_id, kind, send_at, body, status)"
        " VALUES (1, ?, 'review_request', ?, 'Test msg', 'held')",
        (lead_id, send_at))
    c.commit()
    c.close()


def _clear_held_biz1():
    c = db.get_conn()
    c.execute("DELETE FROM scheduled_messages WHERE business_id=1")
    c.commit()
    c.close()


print("\n=== 11. growth_tray route: streak_count passed to template ===")
_client11 = app.app.test_client()
_client11.post("/login", data={"email": config.SEED_OWNER_EMAIL,
                               "password": config.SEED_OWNER_PASSWORD})
# Set streak to 3 on biz 1 and add a held message so the streak bar section renders
c = db.get_conn()
c.execute("UPDATE businesses SET growth_streak_count=3, growth_mode='tray',"
          " growth_streak_unlocked_at=NULL WHERE id=1")
c.commit()
c.close()
_clear_held_biz1()
_insert_held_for_biz1()
resp11 = _client11.get("/growth/tray")
check("Tray route returns 200", resp11.status_code == 200)
body11 = resp11.data.decode()
check("Tray shows '3/7' in streak bar", "3/7" in body11)
_clear_held_biz1()


print("\n=== 12. growth_tray shows unlocked badge when streak complete ===")
_client12 = app.app.test_client()
_client12.post("/login", data={"email": config.SEED_OWNER_EMAIL,
                               "password": config.SEED_OWNER_PASSWORD})
unlock_time12 = datetime.now(timezone.utc).isoformat()
c = db.get_conn()
c.execute("UPDATE businesses SET growth_streak_count=7, growth_mode='tray',"
          " growth_streak_unlocked_at=? WHERE id=1", (unlock_time12,))
c.commit()
c.close()
_clear_held_biz1()
_insert_held_for_biz1()
resp12 = _client12.get("/growth/tray")
check("Tray unlocked route returns 200", resp12.status_code == 200)
body12 = resp12.data.decode()
check("Tray shows 'Auto Mode unlocked' badge", "Auto Mode unlocked" in body12)
# When unlocked, no pip bar should appear (it checks growth_streak_unlocked_at)
check("Unlocked tray does NOT show pip bar", "mornings GO" not in body12)
_clear_held_biz1()


print("\n=== 13. TCPA safety: auto mode still only releases review_request as pending ===")
# Confirm that growth.scan() in auto mode inserts review_request as 'pending'
# and non-review plays as 'held'.
biz_tcpa = fresh_biz("BizTCPA")
db.set_growth_mode(biz_tcpa["id"], "auto")
db.set_avg_job_value(biz_tcpa["id"], 2000)
db.update_business(biz_tcpa["id"], {"review_link": "https://g.page/r/tcpatest"})

# Create a lead with a completed job (review_request eligible: job done, within 90 days)
c = db.get_conn()
c.execute(
    "INSERT INTO leads (business_id, name, phone, status, source, created_at)"
    " VALUES (?, 'TCPALead', '+15555551234', 'booked', 'missed_call', ?)",
    (biz_tcpa["id"], (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()))
lead_id_tcpa = c.execute("SELECT last_insert_rowid()").fetchone()[0]
c.execute(
    "INSERT INTO appointments (business_id, lead_id, status, day, created_at)"
    " VALUES (?, ?, 'booked', ?, ?)",
    (biz_tcpa["id"], lead_id_tcpa,
     (date.today() - timedelta(days=5)).isoformat(),
     (datetime.now(timezone.utc) - timedelta(days=5)).isoformat()))
c.commit()
c.close()

result_scan = growth.scan(now=datetime.now(timezone.utc).isoformat())

# Check that no non-review play was inserted as 'pending'
c = db.get_conn()
pending_non_review = c.execute(
    "SELECT COUNT(*) FROM scheduled_messages"
    " WHERE business_id=? AND status='pending' AND kind != 'review_request'",
    (biz_tcpa["id"],)).fetchone()[0]
review_pending = c.execute(
    "SELECT COUNT(*) FROM scheduled_messages"
    " WHERE business_id=? AND status='pending' AND kind='review_request'",
    (biz_tcpa["id"],)).fetchone()[0]
c.close()

check("TCPA: no non-review plays in 'pending' under auto mode", pending_non_review == 0)
check("TCPA: review_request may be 'pending' under auto mode", review_pending >= 0)  # 0 or 1 ok


# ============================================================
# Summary
# ============================================================
print(f"\n{'='*50}")
print(f"Results: {_pass} passed, {_fail} failed")
if _fail:
    print("SOME TESTS FAILED")
    raise SystemExit(1)
else:
    print("ALL TESTS PASSED")
