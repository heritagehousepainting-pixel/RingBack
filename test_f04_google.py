"""F04 Google Calendar event create/cancel + all-day fix. Run: python test_f04_google.py

Covers:
  1. All-day events ({"date": "..."}) block the full day (every slot on that day
     is returned as busy).
  2. Timed events ({"dateTime": "..."}) still work (regression guard).
  3. Mixed interval lists (all-day + timed) are handled correctly.
  4. create_event_and_store persists the returned event id via db.set_google_event_id.
  5. cancel_event is idempotent: a 410 response from Google -> True (already gone).
  6. create_event_async launches a thread (smoke test: does not block or raise).

No network. All Google HTTP is monkeypatched. Agent 1's not-yet-existing db
functions (set_google_event_id, set_business_timezone) are stubbed at the db module.
"""
import os
import sys
import tempfile
from datetime import date, timedelta, datetime, timezone

os.environ.setdefault("FIRSTBACK_PROVIDER", "demo")

import config
_TMP = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_TMP.close()
config.DB_PATH = _TMP.name

import db
db.DB_PATH = _TMP.name
db.init_db()

# ---- Stub Agent 1's not-yet-existing db functions ----
_google_event_store = {}   # appointment_id -> event_id
_tz_store = {}             # business_id -> tz_name


def _stub_set_google_event_id(appointment_id, event_id):
    _google_event_store[appointment_id] = event_id


def _stub_set_business_timezone(business_id, tz_name):
    _tz_store[business_id] = tz_name


db.set_google_event_id = _stub_set_google_event_id
db.set_business_timezone = _stub_set_business_timezone

# ---- Set up a connected business ----
import google_cal

# Ensure business 1 has a Google integration with tokens.
db.set_google_tokens(1, "access-test", "refresh-test",
                     (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
                     "primary")

import requests as _req_mod

_pass = _fail = 0


def check(name, cond):
    global _pass, _fail
    if cond:
        _pass += 1
        print(f"  ok   {name}")
    else:
        _fail += 1
        print(f"FAIL   {name}")


# ---- Helpers ----
class _FakeResp:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload or {}

    def raise_for_status(self):
        if self.status_code >= 400:
            err = requests_HTTPError(response=self)
            raise err

    def json(self):
        return self._payload


# We need requests.exceptions.HTTPError available.
import importlib
requests_HTTPError = _req_mod.exceptions.HTTPError

_orig_post = _req_mod.post
_orig_get = _req_mod.get
_orig_delete = _req_mod.delete


# ===========================================================================
# 1. All-day event blocks the full day
# ===========================================================================
today = db._today()
horizon = config.BOOKING_HORIZON_DAYS

# Pick the first day in the booking window (tomorrow).
target_day = (today + timedelta(days=1)).isoformat()

# Build an all-day interval for that day using Google's date-only format.
# Google all-day: {"date": "YYYY-MM-DD"} start=target_day, end=target_day+1.
all_day_intervals = [
    {"start": {"date": target_day},
     "end":   {"date": (today + timedelta(days=2)).isoformat()}}
]

# We need ESTIMATE_TIMES to build expected slot ids.
from config import ESTIMATE_TIMES

def _slot_ids_for_day(day_iso):
    return {f"{day_iso}@{db.time_key(t)}" for t in ESTIMATE_TIMES}

busy = google_cal._slots_conflicting(all_day_intervals, today)
expected_slots = _slot_ids_for_day(target_day)
check("all-day event blocks ALL estimate slots on that day",
      expected_slots.issubset(busy))
check("all-day event does NOT block slots on a different day",
      not _slot_ids_for_day((today + timedelta(days=2)).isoformat()).issubset(busy))


# ===========================================================================
# 2. Timed event regression: timed intervals still conflict correctly
# ===========================================================================
# Use a flat dateTime interval (old format) to hit the legacy path.
first_slot_str = db.time_key(ESTIMATE_TIMES[0])   # e.g. "09:00"
slot_start = google_cal._slot_dt(target_day, first_slot_str)
slot_end = slot_start + __import__("datetime").timedelta(hours=1)

timed_intervals_old = [
    {"start": slot_start.isoformat(), "end": slot_end.isoformat()}
]
busy2 = google_cal._slots_conflicting(timed_intervals_old, today)
check("timed event (legacy flat string) conflicts with the overlapping slot",
      f"{target_day}@{first_slot_str}" in busy2)
check("timed event does not block a slot on a different day",
      not any(s.startswith((today + timedelta(days=2)).isoformat()) for s in busy2))

# New dateTime-dict format.
timed_intervals_new = [
    {"start": {"dateTime": slot_start.isoformat()},
     "end":   {"dateTime": slot_end.isoformat()}}
]
busy3 = google_cal._slots_conflicting(timed_intervals_new, today)
check("timed event (dict dateTime) conflicts with the overlapping slot",
      f"{target_day}@{first_slot_str}" in busy3)


# ===========================================================================
# 3. Mixed all-day + timed intervals
# ===========================================================================
day2 = (today + timedelta(days=2)).isoformat()
day3 = (today + timedelta(days=3)).isoformat()
mixed = [
    # all-day on day2
    {"start": {"date": day2}, "end": {"date": day3}},
    # timed on day3, first slot
    {"start": {"dateTime": google_cal._slot_dt(day3, first_slot_str).isoformat()},
     "end":   {"dateTime": (google_cal._slot_dt(day3, first_slot_str) +
                             __import__("datetime").timedelta(hours=1)).isoformat()}}
]
busy4 = google_cal._slots_conflicting(mixed, today)
check("mixed: all-day event blocks all slots on day2",
      _slot_ids_for_day(day2).issubset(busy4))
check("mixed: timed event on day3 blocks just the first slot",
      f"{day3}@{first_slot_str}" in busy4)


# ===========================================================================
# 4. create_event_and_store stores the event id via db.set_google_event_id
# ===========================================================================
_event_create_calls = []


def _fake_post_event(url, headers=None, json=None, **kw):
    if "calendars" in url and "events" in url and json:
        _event_create_calls.append(json)
        return _FakeResp(200, {"id": "google-event-abc123"})
    # Token refresh (shouldn't happen with a fresh token, but fallback)
    return _FakeResp(200, {"access_token": "new-token", "expires_in": 3600})


_req_mod.post = _fake_post_event
_google_event_store.clear()

event_id = google_cal.create_event_and_store(
    business_id=1, appointment_id=42,
    summary="Painting estimate", description="Kitchen + living room",
    day_iso=target_day, time_key_str=first_slot_str)

check("create_event_and_store returns the event id",
      event_id == "google-event-abc123")
check("create_event_and_store stores the id via db.set_google_event_id",
      _google_event_store.get(42) == "google-event-abc123")

_req_mod.post = _orig_post


# ===========================================================================
# 5. cancel_event is idempotent on HTTP 410 (already gone -> True)
# ===========================================================================
def _fake_delete_410(url, headers=None, **kw):
    r = _FakeResp(410)
    return r


def _fake_delete_204(url, headers=None, **kw):
    return _FakeResp(204)


_req_mod.delete = _fake_delete_410
result_410 = google_cal.cancel_event(1, "ghost-event-id")
check("cancel_event returns True on 410 (idempotent / already gone)",
      result_410 is True)

_req_mod.delete = _fake_delete_204
result_204 = google_cal.cancel_event(1, "live-event-id")
check("cancel_event returns True on 204 (successfully deleted)",
      result_204 is True)

_req_mod.delete = _orig_delete

# cancel_event with no event_id returns False (nothing to cancel).
check("cancel_event with None event_id returns False",
      google_cal.cancel_event(1, None) is False)

# cancel_event when not connected returns False.
db.set_google_tokens(99, None, None, None)
check("cancel_event returns False when not connected",
      google_cal.cancel_event(99, "some-event") is False)


# ===========================================================================
# 6. create_event_async smoke test: launches without blocking (no exception)
# ===========================================================================
import threading
_async_called = threading.Event()
_req_mod.post = lambda *a, **k: (_async_called.set(), _FakeResp(200, {"id": "async-id"}))[1]
_google_event_store.clear()

google_cal.create_event_async(1, 55, "async summary", "async desc",
                              target_day, first_slot_str)
hit = _async_called.wait(timeout=3)
check("create_event_async fires without blocking (thread runs)",
      hit is True)

_req_mod.post = _orig_post


# ===========================================================================
# 7. _slot_dt: tz=None preserves pre-Phase-2 behavior; tz=ZoneInfo works
# ===========================================================================
from zoneinfo import ZoneInfo

dt_no_tz = google_cal._slot_dt("2026-07-04", "09:00")
check("_slot_dt with tz=None returns a tz-aware datetime",
      dt_no_tz.tzinfo is not None)

eastern = ZoneInfo("America/New_York")
dt_eastern = google_cal._slot_dt("2026-07-04", "09:00", tz=eastern)
check("_slot_dt with tz=ZoneInfo returns a datetime in that zone",
      dt_eastern.tzinfo is eastern)
check("_slot_dt Eastern 9am is UTC-4 in summer (EDT)",
      dt_eastern.utcoffset().total_seconds() == -4 * 3600)


print(f"==== {_pass} passed, {_fail} failed ====")
sys.exit(1 if _fail else 0)
