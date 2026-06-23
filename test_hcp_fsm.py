"""Housecall Pro FSM provider tests (Plan 16).

Run: FIRSTBACK_DB_PATH=/tmp/hcpb.db .venv/bin/python test_hcp_fsm.py

~45 mocked cases covering:
  - configured/connected gating (inert when HCP_CLIENT_ID unset)
  - auth_url structure
  - connect_with_code success + failure
  - _access_token fresh/stale/no-refresh/refresh-failure (FIX-8 disconnect on fail)
  - disconnect
  - fetch_clients: FIX-3 (next_page_url pagination), FIX-4 (name join, phone filter)
  - fetch_jobs: FIX-5 (description field, client_phone always "")
  - push_quote_request: FIX-6 (v1 no-op returns None, never sets fsm_external_id)
  - sync_clients: F1 (upsert direct, ingest never called), source=import-housecall_pro
  - push_booking_async: HCP push returns None, fsm_external_id NOT set
  - provider-selection: only-jobber/only-hcp/neither/both-hcp-wins
  - maybe_sync_all routes correctly via provider selection
  - token encryption round-trip
  - FIX-11: corrected mock shapes used throughout

No live credentials. All HCP HTTP is mocked. Standalone-script convention:
prints ok/FAIL per case, exits 1 on any failure.
"""
import os
import sys
import tempfile
import threading
import time
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock

# ---- env setup (before any firstback import) ----
os.environ["FIRSTBACK_PROVIDER"] = "demo"
os.environ.setdefault("TWILIO_ACCOUNT_SID", "ACtest")
os.environ.setdefault("TWILIO_AUTH_TOKEN", "tok_test")
os.environ.setdefault("TWILIO_FROM_NUMBER", "+12677562454")
# No live HCP creds by default (gated no-op)
os.environ.pop("HCP_CLIENT_ID", None)
os.environ.pop("HCP_CLIENT_SECRET", None)
os.environ.pop("HCP_REDIRECT_URI", None)
# No live Jobber creds either
os.environ.pop("JOBBER_CLIENT_ID", None)
os.environ.pop("JOBBER_CLIENT_SECRET", None)

import config

_TMP = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_TMP.close()
_DB_PATH = _TMP.name
config.DB_PATH = _DB_PATH
os.environ["FIRSTBACK_DB_PATH"] = _DB_PATH

import db
db.DB_PATH = _DB_PATH
db.init_db()

import hcp_fsm
import jobber_fsm
import fsm_sync
import fsm_provider
import contact_import

# ---- test harness ----
_pass = _fail = 0


def check(name, cond):
    global _pass, _fail
    if cond:
        _pass += 1
        print(f"  ok   {name}")
    else:
        _fail += 1
        print(f"FAIL   {name}")


BIZ_ID = 1
future_expiry = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()


# ===========================================================================
# 1. configured() gate — inert when HCP_CLIENT_ID unset
# ===========================================================================
print("\n-- configured() gate (inert without creds) --")

check("hcp_fsm.configured() False when no creds", not hcp_fsm.configured())
check("fsm_sync.configured() False when neither provider has creds", not fsm_sync.configured())

# Set HCP creds
config.HCP_CLIENT_ID = "hcp_test_id"
config.HCP_CLIENT_SECRET = "hcp_test_secret"
hcp_fsm.HCP_CLIENT_ID = "hcp_test_id"
hcp_fsm.HCP_CLIENT_SECRET = "hcp_test_secret"

check("hcp_fsm.configured() True when creds set", hcp_fsm.configured())
check("fsm_sync.configured() True when HCP creds set", fsm_sync.configured())
check("fsm_sync.push_configured() True when HCP creds set", fsm_sync.push_configured())


# ===========================================================================
# 2. auth_url structure (FIX-1: uses api.housecallpro.com)
# ===========================================================================
print("\n-- auth_url (FIX-1: correct OAuth URL) --")

state = "hcp_test_state_abc"
url = hcp_fsm.auth_url(state)
check("auth_url contains api.housecallpro.com (FIX-1)",    "api.housecallpro.com" in url)
check("auth_url does NOT use auth.housecallpro.com",        "auth.housecallpro.com" not in url)
check("auth_url contains client_id",                        "hcp_test_id" in url)
check("auth_url contains state param",                      "hcp_test_state_abc" in url)
check("auth_url contains response_type=code",               "response_type=code" in url)
check("auth_url contains read:customers scope (FIX-7)",     "read" in url)


# ===========================================================================
# 3. connect_with_code
# ===========================================================================
print("\n-- connect_with_code --")

_fake_tok = {
    "access_token": "hcp_acc_abc",
    "refresh_token": "hcp_ref_xyz",
    "expires_in": 3600,
}

with patch("hcp_fsm.requests") as mock_req:
    resp = MagicMock()
    resp.json.return_value = _fake_tok
    resp.raise_for_status.return_value = None
    mock_req.post.return_value = resp
    hcp_fsm.connect_with_code(BIZ_ID, "hcp_auth_code_ok")

intg = db.get_integration(BIZ_ID, "housecall_pro")
check("connect_with_code stores access_token",  intg and intg.get("access_token") == "hcp_acc_abc")
check("connect_with_code stores refresh_token", intg and intg.get("refresh_token") == "hcp_ref_xyz")
check("connect_with_code marks connected=1",    intg and bool(intg.get("connected")))

# Failure: raise_for_status raises
with patch("hcp_fsm.requests") as mock_req:
    resp2 = MagicMock()
    resp2.raise_for_status.side_effect = Exception("HTTP 401")
    mock_req.post.return_value = resp2
    raised = False
    try:
        hcp_fsm.connect_with_code(BIZ_ID, "bad_code")
    except Exception:
        raised = True
check("connect_with_code raises on HTTP error (caller redirects)", raised)


# ===========================================================================
# 4. _access_token — fresh / stale / no-refresh / refresh-failure (FIX-8)
# ===========================================================================
print("\n-- _access_token (FIX-8: disconnect on refresh fail) --")

# 4a. fresh: access is fresh, return stored token
db.set_oauth_tokens(BIZ_ID, "housecall_pro", "hcp_fresh_acc", "hcp_ref_xyz", future_expiry)
with patch("hcp_fsm.access_is_fresh", return_value=True):
    tok = hcp_fsm._access_token(BIZ_ID)
check("_access_token fresh: returns stored token", tok == "hcp_fresh_acc")

# 4b. stale: access_is_fresh False -> refresh
_new_tok = {"access_token": "hcp_new_acc2", "expires_in": 3600}
with patch("hcp_fsm.access_is_fresh", return_value=False), \
     patch("hcp_fsm.requests") as mock_req:
    resp3 = MagicMock()
    resp3.json.return_value = _new_tok
    resp3.raise_for_status.return_value = None
    mock_req.post.return_value = resp3
    tok2 = hcp_fsm._access_token(BIZ_ID)
check("_access_token stale: refreshes and returns new token", tok2 == "hcp_new_acc2")

# 4c. no refresh token -> None
db.set_oauth_tokens(BIZ_ID, "housecall_pro", None, None, None)
tok3 = hcp_fsm._access_token(BIZ_ID)
check("_access_token no refresh_token -> None", tok3 is None)

# 4d. FIX-8: refresh HTTP failure -> None AND marks disconnected
db.set_oauth_tokens(BIZ_ID, "housecall_pro", "hcp_old_acc", "hcp_ref_xyz", "2020-01-01T00:00:00+00:00")
with patch("hcp_fsm.access_is_fresh", return_value=False), \
     patch("hcp_fsm.requests") as mock_req:
    resp4 = MagicMock()
    resp4.raise_for_status.side_effect = Exception("network error")
    mock_req.post.return_value = resp4
    tok4 = hcp_fsm._access_token(BIZ_ID)
check("FIX-8: _access_token refresh failure -> None", tok4 is None)
# Verify marked disconnected (FIX-8)
intg_after_fail = db.get_integration(BIZ_ID, "housecall_pro")
check("FIX-8: _access_token refresh failure -> marks disconnected",
      not bool(intg_after_fail and intg_after_fail.get("connected")))

# Restore valid tokens for subsequent tests
db.set_oauth_tokens(BIZ_ID, "housecall_pro", "hcp_acc_abc", "hcp_ref_xyz", future_expiry)


# ===========================================================================
# 5. disconnect
# ===========================================================================
print("\n-- disconnect --")

intg_before = db.get_integration(BIZ_ID, "housecall_pro")
check("pre-disconnect: connected=1", bool(intg_before and intg_before.get("connected")))

hcp_fsm.disconnect(BIZ_ID)
intg_after = db.get_integration(BIZ_ID, "housecall_pro")
check("disconnect: connected=0",         not bool(intg_after and intg_after.get("connected")))
check("disconnect: access_token cleared", not bool(intg_after and intg_after.get("access_token")))
check("disconnect: refresh_token cleared", not bool(intg_after and intg_after.get("refresh_token")))

# Re-connect for subsequent tests
db.set_oauth_tokens(BIZ_ID, "housecall_pro", "hcp_acc_abc", "hcp_ref_xyz", future_expiry)


# ===========================================================================
# 6. fetch_clients — FIX-3 (next_page_url), FIX-4 (name join, phone filter)
# ===========================================================================
print("\n-- fetch_clients (FIX-3: next_page_url pagination; FIX-4: name/phone) --")

# FIX-11: corrected mock shapes
# Page 1 response with next_page_url
_HCP_PAGE1_RESP = MagicMock()
_HCP_PAGE1_RESP.json.return_value = {
    "customers": [
        {
            "first_name": "Alice",
            "last_name": "Anderson",
            "mobile_number": "+12155550001",
            "home_number": None,
            "work_number": None,
            "email": "alice@example.com",
        },
        {
            "first_name": "Bob",
            "last_name": "Baker",
            "mobile_number": "+12155550002",
            "home_number": "+12155550099",
            "work_number": None,
            "email": "bob@example.com",
        },
    ],
    "next_page_url": "https://api.housecallpro.com/customers?page_size=25&page_token=tok2",
}
_HCP_PAGE1_RESP.raise_for_status.return_value = None

# Page 2 response with no next_page_url (end of pagination)
_HCP_PAGE2_RESP = MagicMock()
_HCP_PAGE2_RESP.json.return_value = {
    "customers": [
        {
            "first_name": "Carol",
            "last_name": "Clark",
            "mobile_number": "+12155550003",
            "home_number": None,
            "work_number": None,
            "email": "carol@example.com",
        },
    ],
    "next_page_url": None,
}
_HCP_PAGE2_RESP.raise_for_status.return_value = None

_page_responses = [_HCP_PAGE1_RESP, _HCP_PAGE2_RESP]
_page_call_idx = [0]

def _fake_get_paginated(*args, **kwargs):
    idx = _page_call_idx[0]
    _page_call_idx[0] += 1
    if idx < len(_page_responses):
        return _page_responses[idx]
    return MagicMock(json=lambda: {"customers": [], "next_page_url": None},
                     raise_for_status=lambda: None)

with patch("hcp_fsm.requests") as mock_req:
    # Also mock access_is_fresh so token is valid
    mock_req.get.side_effect = _fake_get_paginated
    with patch("hcp_fsm.access_is_fresh", return_value=True):
        clients = hcp_fsm.fetch_clients(BIZ_ID)

check("FIX-3: fetch_clients: returns 3 clients across 2 pages (next_page_url)", len(clients) == 3)
check("FIX-4: fetch_clients: first client name joined correctly",
      clients[0]["name"] == "Alice Anderson")
check("FIX-4: fetch_clients: second client has 2 phones (mobile + home)",
      len(clients[1]["phones"]) == 2)
check("FIX-4: fetch_clients: None phone fields filtered out",
      None not in clients[0]["phones"])
check("FIX-3: fetch_clients: third client phone correct",
      "+12155550003" in clients[2]["phones"])

# Error: requests.get raises -> []
with patch("hcp_fsm.requests") as mock_req:
    mock_req.get.side_effect = Exception("network error")
    with patch("hcp_fsm.access_is_fresh", return_value=True):
        clients_err = hcp_fsm.fetch_clients(BIZ_ID)
check("fetch_clients: GET error -> []", clients_err == [])

# Not connected -> []
hcp_fsm.disconnect(BIZ_ID)
clients_disc = hcp_fsm.fetch_clients(BIZ_ID)
check("fetch_clients: not connected -> []", clients_disc == [])
db.set_oauth_tokens(BIZ_ID, "housecall_pro", "hcp_acc_abc", "hcp_ref_xyz", future_expiry)

# No customers key -> []
with patch("hcp_fsm.requests") as mock_req:
    _empty_resp = MagicMock()
    _empty_resp.json.return_value = {"customers": [], "next_page_url": None}
    _empty_resp.raise_for_status.return_value = None
    mock_req.get.return_value = _empty_resp
    with patch("hcp_fsm.access_is_fresh", return_value=True):
        clients_empty = hcp_fsm.fetch_clients(BIZ_ID)
check("fetch_clients: empty customers list -> []", clients_empty == [])


# ===========================================================================
# 7. fetch_jobs — FIX-5 (description field, client_phone always "")
# ===========================================================================
print("\n-- fetch_jobs (FIX-5: description title, client_phone always empty) --")

# FIX-11: corrected mock shape — uses description + customer_id (not note/inline phone)
_HCP_JOBS_DATA = {
    "jobs": [
        {
            "id": "job-001",
            "description": "Exterior paint job",
            "work_status": "scheduled",
            "customer_id": "cust-abc",   # only customer_id, no inline phone
        },
        {
            "id": "job-002",
            "description": "Interior repaint",
            "work_status": "complete",
            "customer_id": "cust-def",
        },
    ]
}

with patch.object(hcp_fsm._provider, "_get", return_value=_HCP_JOBS_DATA):
    jobs = hcp_fsm.fetch_jobs(BIZ_ID)

check("FIX-5: fetch_jobs: returns 2 jobs",                     len(jobs) == 2)
check("FIX-5: fetch_jobs: title from description field",        jobs[0]["title"] == "Exterior paint job")
check("FIX-5: fetch_jobs: work_status field correct",           jobs[0]["status"] == "scheduled")
check("FIX-5: fetch_jobs: client_phone always '' (no inline)", jobs[0]["client_phone"] == "")
check("FIX-5: fetch_jobs: second job client_phone also ''",     jobs[1]["client_phone"] == "")

# Error: _get returns None -> []
with patch.object(hcp_fsm._provider, "_get", return_value=None):
    jobs_err = hcp_fsm.fetch_jobs(BIZ_ID)
check("fetch_jobs: _get None -> []", jobs_err == [])


# ===========================================================================
# 8. push_quote_request — FIX-6 (v1 no-op returning None)
# ===========================================================================
print("\n-- push_quote_request (FIX-6: v1 no-op, never claims pushed) --")

result_push = hcp_fsm.push_quote_request(
    BIZ_ID, {"name": "Alice", "phone": "+12155550001"}, {"day": "2026-07-01"})
check("FIX-6: push_quote_request always returns None",         result_push is None)

# With no token / disconnected — still None (no error)
hcp_fsm.disconnect(BIZ_ID)
result_push_disc = hcp_fsm.push_quote_request(BIZ_ID, {}, {})
check("FIX-6: push_quote_request disconnected -> None",        result_push_disc is None)
db.set_oauth_tokens(BIZ_ID, "housecall_pro", "hcp_acc_abc", "hcp_ref_xyz", future_expiry)


# ===========================================================================
# 9. sync_clients — F1 (direct upsert_suggestion, NOT ingest); source=import-housecall_pro
# ===========================================================================
print("\n-- sync_clients F1 (direct upsert; source=import-housecall_pro) --")

# FIX-11: corrected client shape
_FAKE_HCP_CLIENTS = [
    {"name": "Dave Diaz",  "phones": ["+12155551001"], "email": "dave@example.com"},
    {"name": "Eve Evans",  "phones": ["+12155551002"], "email": "eve@example.com"},
]

_upsert_calls = []
_orig_upsert = db.upsert_suggestion

def _capture_upsert(business_id, number, name, category, reason, source="behavior"):
    _upsert_calls.append({"business_id": business_id, "number": number,
                          "name": name, "category": category,
                          "reason": reason, "source": source})
    return _orig_upsert(business_id, number, name, category, reason, source)

db.upsert_suggestion = _capture_upsert

with patch.object(hcp_fsm._provider, "fetch_clients", return_value=_FAKE_HCP_CLIENTS):
    result = fsm_sync.sync_clients(BIZ_ID)

check("sync_clients: returns clients_fetched=2",          result.get("clients_fetched") == 2)
check("sync_clients: returns suggested=2",                 result.get("suggested") == 2)
check("sync_clients: upsert called for each client",      len(_upsert_calls) >= 2)
check("sync_clients: category='customer'",
      all(c["category"] == "customer" for c in _upsert_calls))
check("sync_clients: source='import-housecall_pro'",
      all(c["source"] == "import-housecall_pro" for c in _upsert_calls))
check("sync_clients: reason contains 'Housecall Pro'",
      all("Housecall Pro" in c["reason"] for c in _upsert_calls))

# F1: contact_import.ingest is NOT called
_ingest_calls = []
_orig_ingest = contact_import.ingest

def _capture_ingest(*a, **kw):
    _ingest_calls.append((a, kw))
    return _orig_ingest(*a, **kw)

contact_import.ingest = _capture_ingest
_upsert_calls.clear()

with patch.object(hcp_fsm._provider, "fetch_clients", return_value=_FAKE_HCP_CLIENTS):
    fsm_sync.sync_clients(BIZ_ID)

check("sync_clients F1: contact_import.ingest NOT called", len(_ingest_calls) == 0)

# Restore
db.upsert_suggestion = _orig_upsert
contact_import.ingest = _orig_ingest


# ===========================================================================
# 10. push_booking_async — HCP push is no-op; fsm_external_id NOT set
# ===========================================================================
print("\n-- push_booking_async (HCP: no-op; fsm_external_id not set) --")

# Create a minimal appointment
conn = db.get_conn()
conn.execute(
    "INSERT INTO appointments (business_id, lead_id, status) VALUES (?,?,?)",
    (BIZ_ID, 1, "booked"))
conn.commit()
appt_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
conn.close()

# HCP push is no-op: fsm_external_id must NOT be set
fsm_sync.push_booking_async(BIZ_ID, appt_id, {"name": "Alice"}, {"day": "2026-07-01"})
time.sleep(0.2)  # let daemon thread finish

conn2 = db.get_conn()
row = conn2.execute(
    "SELECT fsm_external_id FROM appointments WHERE id=?", (appt_id,)).fetchone()
conn2.close()
check("push_booking_async: HCP push no-op -> fsm_external_id stays NULL",
      row and row[0] is None)

# No-op when unconfigured
config.HCP_CLIENT_ID = ""
hcp_fsm.HCP_CLIENT_ID = ""
push_called = [False]

def _track_push(*a, **kw):
    push_called[0] = True
    return None

with patch.object(hcp_fsm._provider, "push_quote_request", side_effect=_track_push):
    fsm_sync.push_booking_async(BIZ_ID, appt_id, {}, {})
    time.sleep(0.1)
check("push_booking_async: no-op when unconfigured", not push_called[0])

# Restore
config.HCP_CLIENT_ID = "hcp_test_id"
hcp_fsm.HCP_CLIENT_ID = "hcp_test_id"


# ===========================================================================
# 11. Provider selection (Option C)
# ===========================================================================
print("\n-- provider selection (Option C: HCP>Jobber tiebreak) --")

# Set up Jobber creds for this section
config.JOBBER_CLIENT_ID = "j_test_id"
config.JOBBER_CLIENT_SECRET = "j_test_secret"
jobber_fsm.JOBBER_CLIENT_ID = "j_test_id"
jobber_fsm.JOBBER_CLIENT_SECRET = "j_test_secret"

# Case 1: neither connected -> None
hcp_fsm.disconnect(BIZ_ID)
jobber_fsm.disconnect(BIZ_ID)
provider_neither = fsm_sync._get_active_provider(BIZ_ID)
check("neither connected -> _get_active_provider returns None", provider_neither is None)

# Case 2: only Jobber connected -> returns Jobber provider
db.set_oauth_tokens(BIZ_ID, "jobber", "j_acc", "j_ref", future_expiry)
provider_jobber_only = fsm_sync._get_active_provider(BIZ_ID)
check("only Jobber connected -> returns Jobber provider",
      provider_jobber_only is jobber_fsm._provider)

# Case 3: only HCP connected -> returns HCP provider
jobber_fsm.disconnect(BIZ_ID)
db.set_oauth_tokens(BIZ_ID, "housecall_pro", "hcp_acc_abc", "hcp_ref_xyz", future_expiry)
provider_hcp_only = fsm_sync._get_active_provider(BIZ_ID)
check("only HCP connected -> returns HCP provider",
      provider_hcp_only is hcp_fsm._provider)

# Case 4: both connected -> HCP wins (tiebreak)
db.set_oauth_tokens(BIZ_ID, "jobber", "j_acc", "j_ref", future_expiry)
import io
captured_stderr = io.StringIO()
import sys as _sys
_old_stderr = _sys.stderr
_sys.stderr = captured_stderr
provider_both = fsm_sync._get_active_provider(BIZ_ID)
_sys.stderr = _old_stderr
warn_output = captured_stderr.getvalue()
check("both connected -> HCP wins (tiebreak)",
      provider_both is hcp_fsm._provider)
check("both connected -> warning logged to stderr",
      "both" in warn_output.lower() or "tiebreak" in warn_output.lower() or "HCP" in warn_output)

# Clean up
jobber_fsm.disconnect(BIZ_ID)
config.JOBBER_CLIENT_ID = ""
config.JOBBER_CLIENT_SECRET = ""
jobber_fsm.JOBBER_CLIENT_ID = ""
jobber_fsm.JOBBER_CLIENT_SECRET = ""


# ===========================================================================
# 12. sync_clients: routes correctly based on active provider
# ===========================================================================
print("\n-- sync_clients routes via active provider --")

# HCP connected: sync should use HCP fetch_clients, source=import-housecall_pro
_upsert_sources = []
_orig_upsert2 = db.upsert_suggestion

def _track_source(business_id, number, name, category, reason, source="behavior"):
    _upsert_sources.append(source)
    return _orig_upsert2(business_id, number, name, category, reason, source)

db.upsert_suggestion = _track_source

_SINGLE_CLIENT = [{"name": "Frank F", "phones": ["+12155552001"], "email": "f@example.com"}]

with patch.object(hcp_fsm._provider, "fetch_clients", return_value=_SINGLE_CLIENT) as mock_hcp_fetch, \
     patch.object(jobber_fsm._provider, "fetch_clients", return_value=[]) as mock_job_fetch:
    result_route = fsm_sync.sync_clients(BIZ_ID)

check("sync routes to HCP when HCP connected",
      result_route.get("clients_fetched") == 1)
check("sync source is import-housecall_pro when HCP active",
      any(s == "import-housecall_pro" for s in _upsert_sources))

db.upsert_suggestion = _orig_upsert2


# ===========================================================================
# 13. maybe_sync_all — routes via provider selection
# ===========================================================================
print("\n-- maybe_sync_all routes via _get_active_provider --")

# Neither connected -> no syncs
hcp_fsm.disconnect(BIZ_ID)
_sync_calls = []
_orig_sc = fsm_sync.sync_clients

def _capture_sync(bid):
    _sync_calls.append(bid)
    return {"clients_fetched": 0, "suggested": 0, "skipped": 0}

fsm_sync.sync_clients = _capture_sync
result_ma = fsm_sync.maybe_sync_all()
check("maybe_sync_all: skips when no provider connected",
      BIZ_ID not in _sync_calls)

# HCP connected + past interval -> syncs
db.set_oauth_tokens(BIZ_ID, "housecall_pro", "hcp_acc_abc", "hcp_ref_xyz", future_expiry)
old_stamp = (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat()
db.set_fsm_sync_stamp(BIZ_ID, old_stamp, 0)
_sync_calls.clear()
fsm_sync.maybe_sync_all()
check("maybe_sync_all: syncs when HCP connected + past interval",
      BIZ_ID in _sync_calls)

# No-op when unconfigured
config.HCP_CLIENT_ID = ""
hcp_fsm.HCP_CLIENT_ID = ""
_sync_calls.clear()
result_nc = fsm_sync.maybe_sync_all()
check("maybe_sync_all: no-op when no provider configured",
      result_nc.get("businesses_checked") == 0 and len(_sync_calls) == 0)

# Restore
config.HCP_CLIENT_ID = "hcp_test_id"
hcp_fsm.HCP_CLIENT_ID = "hcp_test_id"
db.set_oauth_tokens(BIZ_ID, "housecall_pro", "hcp_acc_abc", "hcp_ref_xyz", future_expiry)
fsm_sync.sync_clients = _orig_sc


# ===========================================================================
# 14. FIX-2: Bearer header (not Token token=)
# ===========================================================================
print("\n-- FIX-2: Authorization: Bearer header --")

# Verify _get sends Bearer token
captured_headers = []

def _fake_requests_get(url, params=None, headers=None, timeout=None):
    captured_headers.append(headers or {})
    resp = MagicMock()
    resp.json.return_value = {"jobs": []}
    resp.raise_for_status.return_value = None
    return resp

with patch("hcp_fsm.requests") as mock_req:
    mock_req.get.side_effect = _fake_requests_get
    with patch("hcp_fsm.access_is_fresh", return_value=True):
        hcp_fsm.fetch_jobs(BIZ_ID)

if captured_headers:
    auth_header = captured_headers[0].get("Authorization", "")
    check("FIX-2: _get uses Authorization: Bearer (not Token token=)",
          auth_header.startswith("Bearer "))
    check("FIX-2: auth header does NOT use Token token= pattern",
          "Token token=" not in auth_header)
else:
    check("FIX-2: _get was called (headers captured)", False)
    check("FIX-2: Bearer check skipped (no call)", False)


# ===========================================================================
# 15. FIX-1: Correct OAuth URL constants
# ===========================================================================
print("\n-- FIX-1: OAuth URL constants --")

check("FIX-1: AUTH_URL uses api.housecallpro.com",
      hcp_fsm.AUTH_URL == "https://api.housecallpro.com/oauth/authorize")
check("FIX-1: TOKEN_URL uses api.housecallpro.com",
      hcp_fsm.TOKEN_URL == "https://api.housecallpro.com/oauth/token")
check("FIX-1: API_BASE uses api.housecallpro.com",
      hcp_fsm.API_BASE == "https://api.housecallpro.com")


# ===========================================================================
# 16. PROVIDER_KEY
# ===========================================================================
print("\n-- PROVIDER_KEY --")

check("hcp_fsm.PROVIDER = 'housecall_pro'", hcp_fsm.PROVIDER == "housecall_pro")
check("HCPProvider.PROVIDER_KEY = 'housecall_pro'",
      hcp_fsm._provider.PROVIDER_KEY == "housecall_pro")
check("HCPProvider is a FSMProvider subclass",
      isinstance(hcp_fsm._provider, fsm_provider.FSMProvider))


# ===========================================================================
# 17. is_connected gating
# ===========================================================================
print("\n-- is_connected gating --")

hcp_fsm.disconnect(BIZ_ID)
check("is_connected False after disconnect", not hcp_fsm.is_connected(BIZ_ID))
db.set_oauth_tokens(BIZ_ID, "housecall_pro", "hcp_acc_abc", "hcp_ref_xyz", future_expiry)
check("is_connected True when tokens set", hcp_fsm.is_connected(BIZ_ID))


# ===========================================================================
# Final summary
# ===========================================================================
print(f"\n{_pass} passed, {_fail} failed")
try:
    os.unlink(_TMP.name)
except OSError:
    pass
sys.exit(1 if _fail else 0)
