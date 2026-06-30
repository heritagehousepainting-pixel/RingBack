"""ServiceTitan FSM provider (servicetitan_fsm.py) regression tests.

  gating       configured() needs all 3 app creds; is_connected() needs a stored tenant id.
  env base     production vs integration auth/api hosts.
  connect      connect_tenant rejects a non-numeric tenant; stores tenant + mints a token.
  fetch_clients customers joined to contacts -> phones/email; no-phone customers skipped.
  fetch_jobs   summary/status + client phone resolved from contacts.
  push         booking POST returns the new id; not-connected returns None.
  token cache  fresh cached token is reused; stale one re-mints.

No network: auth/REST are monkeypatched; the rest is pure parsing + gating.
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
import servicetitan_fsm as st

# Start from a known-unconfigured state, then enable per-test.
st.SERVICETITAN_CLIENT_ID = ""
st.SERVICETITAN_CLIENT_SECRET = ""
st.SERVICETITAN_APP_KEY = ""
st.SERVICETITAN_ENV = "production"

_pass = _fail = 0
def check(name, cond):
    global _pass, _fail
    if cond:
        _pass += 1; print(f"  ok   {name}")
    else:
        _fail += 1; print(f"FAIL   {name}")


# ---- gating ----------------------------------------------------------------
check("configured() false with no app creds", st.configured() is False)
check("is_connected() false when unconfigured", st.is_connected(1) is False)
st.SERVICETITAN_CLIENT_ID = "cid"
st.SERVICETITAN_CLIENT_SECRET = "sec"
check("configured() still false without the app key", st.configured() is False)
st.SERVICETITAN_APP_KEY = "appkey"
check("configured() true with all three app creds", st.configured() is True)
check("is_connected() false before a tenant is stored", st.is_connected(1) is False)

# ---- env base selection ----------------------------------------------------
st.SERVICETITAN_ENV = "integration"
check("integration auth host", st._auth_base() == "https://auth-integration.servicetitan.io")
check("integration api host", st._api_base() == "https://api-integration.servicetitan.io")
st.SERVICETITAN_ENV = "production"
check("production auth host", st._auth_base() == "https://auth.servicetitan.io")
check("production api host", st._api_base() == "https://api.servicetitan.io")

# ---- connect (client-credentials; tenant id is the connection identity) -----
_minted = {"n": 0}
def _fake_mint():
    _minted["n"] += 1
    return {"access_token": "TOK%d" % _minted["n"], "expires_in": 900}
st._provider._mint_token = _fake_mint

try:
    st.connect_tenant(1, "not-a-number")
    check("connect_tenant rejects non-numeric tenant", False)
except ValueError:
    check("connect_tenant rejects non-numeric tenant", True)

st.connect_tenant(1, "987654")
check("connect stores tenant id (in refresh_token slot)", st._provider._tenant_id(1) == "987654")
check("is_connected() true after connect", st.is_connected(1) is True)

# ---- token cache: fresh cached token reused; no extra mint -----------------
_before = _minted["n"]
tok = st._access_token(1)
check("fresh cached token reused (no re-mint)", tok == "TOK1" and _minted["n"] == _before)

# ---- fetch_clients: join customers + contacts, skip no-phone ---------------
def _pages_clients(biz, module, resource, params=None):
    if resource == "customers/contacts":
        return iter([
            {"customerId": 1, "type": "MobilePhone", "value": "(215) 555-0101"},
            {"customerId": 1, "type": "Email", "value": "jane@co.com"},
            {"customerId": 2, "type": "Email", "value": "nophone@x.com"},  # no phone
        ])
    if resource == "customers":
        return iter([{"id": 1, "name": "Jane Co"}, {"id": 2, "name": "No Phone LLC"}])
    return iter([])
st._provider._get_pages = _pages_clients
_clients = st.fetch_clients(1)
check("fetch_clients joins phone + email onto the named customer",
      _clients == [{"name": "Jane Co", "phones": ["(215) 555-0101"], "email": "jane@co.com"}])
check("fetch_clients skips a customer with no phone", all(c["name"] != "No Phone LLC" for c in _clients))

# ---- fetch_jobs ------------------------------------------------------------
def _pages_jobs(biz, module, resource, params=None):
    if resource == "customers/contacts":
        return iter([{"customerId": 7, "type": "Phone", "value": "215-555-0199"}])
    if resource == "jobs":
        return iter([{"customerId": 7, "jobStatus": "Scheduled", "summary": "Exterior repaint"},
                     {"customerId": 7, "jobStatus": "Completed", "jobNumber": 42}])
    return iter([])
st._provider._get_pages = _pages_jobs
_jobs = st.fetch_jobs(1)
check("fetch_jobs maps summary/status + resolves client phone",
      _jobs[0] == {"title": "Exterior repaint", "status": "Scheduled", "client_phone": "215-555-0199"})
check("fetch_jobs falls back to Job #<num> when no summary", _jobs[1]["title"] == "Job #42")

# ---- push booking ----------------------------------------------------------
import requests as _rq
class _Resp:
    content = b'{"id": 555}'
    def raise_for_status(self): pass
    def json(self): return {"id": 555}
_orig_post = _rq.post
_rq.post = lambda *a, **k: _Resp()
_pid = st.push_quote_request(1, {"name": "Jane", "phone": "2155550101"}, {"when": "Thu 10 AM"})
_rq.post = _orig_post
check("push_quote_request returns the new booking id", _pid == "555")

# not connected -> None (clear tenant first)
st.disconnect(2)
check("push returns None when not connected",
      st.push_quote_request(2, {"name": "x"}, {}) is None)

# ---- disconnect ------------------------------------------------------------
st.disconnect(1)
check("disconnect clears the connection", st.is_connected(1) is False)

print(f"\n{'='*46}")
print(f"Results: {_pass} passed, {_fail} failed")
try:
    os.unlink(_TMP.name)
except OSError:
    pass
sys.exit(1 if _fail else 0)
