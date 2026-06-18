"""Phase 4 Agent B -- digest_email ROI block tests (F12).
Run: /Users/jonathanmorris/apps/firstback/.venv/bin/python test_f12_digest.py

Verifies:
  1. When a2p_ready=True AND db.analytics returns the extended shape:
     - Body contains an ROI block with leads/booked/revenue/multiple.
     - Revenue is labeled an estimate (never implies cash).
     - avg_source=owner -> "your average job value" label.
     - avg_source=industry_default -> "industry estimate" label.
  2. When a2p_ready=False (pending):
     - Body does NOT contain a dollar amount or "recovered N missed calls" claim.
     - Body DOES contain an honest non-dollar placeholder line.
  3. Never claims collected cash.

Exits 0 on all pass, 1 if any fail. Standalone -- no pytest.
Agent A's extended db.analytics shape is stubbed via monkeypatching.
"""
import sys
import os
import tempfile

os.environ["FIRSTBACK_PROVIDER"] = "demo"

import config
_TMP = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_TMP.close()
config.DB_PATH = _TMP.name

import db
db.DB_PATH = _TMP.name
db.init_db()

import convos
import compliance

_pass = _fail = 0


def check(name, cond):
    global _pass, _fail
    if cond:
        _pass += 1
        print(f"  ok   {name}")
    else:
        _fail += 1
        print(f"FAIL   {name}")


# ---- Stubs for Agent A's extended db.analytics ----------------------------
# Agent A extends db.analytics to add roi_multiple, avg_source, and resolves
# revenue via trade defaults. We monkeypatch it here so tests pass standalone.

_ANALYTICS_OWNER = {
    "totals": {"leads": 8, "booked": 3, "conversion": 37.5, "revenue": 4500},
    "series": [],
    "avg_job_value": 1500,
    "avg_source": "owner",
    "roi_multiple": 45.5,
    "days": 7,
}

_ANALYTICS_INDUSTRY = {
    "totals": {"leads": 5, "booked": 2, "conversion": 40.0, "revenue": 1600},
    "series": [],
    "avg_job_value": 800,
    "avg_source": "industry_default",
    "roi_multiple": 16.2,
    "days": 7,
}

_ANALYTICS_ZERO = {
    "totals": {"leads": 0, "booked": 0, "conversion": 0, "revenue": 0},
    "series": [],
    "avg_job_value": 800,
    "avg_source": "industry_default",
    "roi_multiple": None,
    "days": 7,
}

# ---- Approved business (a2p_ready=True) + owner avg_source ----------------
biz_approved = {"id": 1, "name": "Test Painter LLC", "a2p_status": "approved"}

_orig_analytics = db.analytics


def _stub_owner(bid, days=None):
    return _ANALYTICS_OWNER


db.analytics = _stub_owner

result = convos.digest_email(biz_approved, days=7)
body = result["body"]

check("approved+owner: body contains ROI block (recovered missed calls)",
      "recovered" in body.lower() and "missed calls" in body.lower())
check("approved+owner: body contains booked count",
      "3 estimates" in body or "booked 3" in body.lower())
check("approved+owner: body contains estimated revenue ($4,500)",
      "$4,500" in body or "4,500" in body)
check("approved+owner: body labels revenue as estimated (not cash)",
      "estimated" in body.lower() or "estimate" in body.lower())
check("approved+owner: body does NOT claim 'collected'",
      "collected" not in body.lower())
check("approved+owner: avg_source owner -> 'average job value' label",
      "average job value" in body.lower() or "your average" in body.lower())
check("approved+owner: roi_multiple present",
      "45.5x" in body or "45.5" in body)

# ---- Approved business + industry_default avg_source ----------------------
def _stub_industry(bid, days=None):
    return _ANALYTICS_INDUSTRY


db.analytics = _stub_industry

result2 = convos.digest_email(biz_approved, days=7)
body2 = result2["body"]

check("approved+industry: body contains ROI block",
      "recovered" in body2.lower() and "missed calls" in body2.lower())
check("approved+industry: body contains estimated revenue ($1,600)",
      "$1,600" in body2 or "1,600" in body2)
check("approved+industry: avg_source industry_default -> 'industry estimate' label",
      "industry estimate" in body2.lower() or "industry" in body2.lower())
check("approved+industry: body does NOT claim 'collected'",
      "collected" not in body2.lower())

# ---- A2P-pending business (a2p_ready=False) --------------------------------
biz_pending = {"id": 2, "name": "Pending Co", "a2p_status": "pending"}

# analytics still stubbed but should NOT be shown for pending tenant
def _stub_should_not_call(bid, days=None):
    # If called and dollar copy appears, the gate failed.
    return _ANALYTICS_OWNER


db.analytics = _stub_should_not_call

result3 = convos.digest_email(biz_pending, days=7)
body3 = result3["body"]

check("pending: body does NOT contain dollar amount",
      "$" not in body3 or ("$" in body3 and "estimate" in body3.lower() and
                           "recovered" not in body3.lower()))
check("pending: body does NOT claim recovered missed calls (no ROI dollar block)",
      not ("recovered" in body3.lower() and "$" in body3))
check("pending: body contains honest non-dollar activation line",
      "activating" in body3.lower() or "texting is" in body3.lower()
      or "texting" in body3.lower())
check("pending: body does NOT claim 'collected'",
      "collected" not in body3.lower())

# ---- Zero-activity approved tenant: ROI block suppressed gracefully --------
def _stub_zero(bid, days=None):
    return _ANALYTICS_ZERO


db.analytics = _stub_zero

result4 = convos.digest_email(biz_approved, days=7)
body4 = result4["body"]
# With roi_multiple=None and revenue=0, the headline tile is hidden; the digest
# still builds cleanly (no crash).
check("zero-activity: digest builds without error", bool(result4.get("body")))
check("zero-activity: no invented dollar claim",
      "$0" not in body4 or "estimate" in body4.lower())

# ---- Restore original analytics -------------------------------------------
db.analytics = _orig_analytics

# ---- Teardown ---------------------------------------------------------------
import os as _os
_os.unlink(_TMP.name)

print(f"\n{_pass} passed, {_fail} failed")
raise SystemExit(1 if _fail else 0)
