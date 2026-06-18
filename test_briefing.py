"""Phase 4 Agent B -- Show-Up-Prepared briefing + roi_milestone alert tests.
Run: /Users/jonathanmorris/apps/firstback/.venv/bin/python test_briefing.py

Verifies:
  1. format_message("booking") appends address/project/summary when present.
  2. format_message("booking") is unchanged (basic line) when context lacks them.
  3. format_message("roi_milestone") returns the body from context.
  4. _subject("roi_milestone") returns a non-generic subject.
  5. "roi_milestone" is in ALERT_KINDS and has a toggle col entry.
  6. _enabled_for defaults ON for roi_milestone when toggle unset.

Exits 0 on all pass, 1 if any fail. Pure unit tests -- no DB, no network.
"""
import sys
import os

# Isolate from any real DB.
os.environ.setdefault("FIRSTBACK_PROVIDER", "demo")

import alerts

_pass = _fail = 0


def check(name, cond):
    global _pass, _fail
    if cond:
        _pass += 1
        print(f"  ok   {name}")
    else:
        _fail += 1
        print(f"FAIL   {name}")


# ---- booking: basic line when no briefing fields present --------------------
ctx_basic = {"name": "Dave Painter", "when": "Thursday 10 AM", "lead_id": 1}
basic = alerts.format_message("booking", ctx_basic)
check("booking basic line: contains who and when",
      "Dave Painter" in basic and "Thursday 10 AM" in basic)
check("booking basic line: no 'Job:' suffix when no briefing fields",
      "Job:" not in basic)

# ---- booking: all three briefing fields present ----------------------------
ctx_full = {
    "name": "Dave Painter", "when": "Thursday 10 AM", "lead_id": 1,
    "address": "123 Main St", "project": "Exterior painting", "summary": "2-story house"
}
full = alerts.format_message("booking", ctx_full)
check("booking full briefing: contains who and when",
      "Dave Painter" in full and "Thursday 10 AM" in full)
check("booking full briefing: contains address", "123 Main St" in full)
check("booking full briefing: contains project", "Exterior painting" in full)
check("booking full briefing: contains summary", "2-story house" in full)
check("booking full briefing: has 'Job:' separator", "Job:" in full)
check("booking full briefing: single message (not a second send)",
      full.startswith("Estimate booked:"))

# ---- booking: partial briefing fields (only project + address) -------------
ctx_partial = {
    "name": "Sam HVAC", "when": "Friday 2 PM", "lead_id": 2,
    "project": "AC tune-up", "address": "456 Oak Ave"
}
partial = alerts.format_message("booking", ctx_partial)
check("booking partial briefing: project present", "AC tune-up" in partial)
check("booking partial briefing: address present", "456 Oak Ave" in partial)
check("booking partial briefing: no summary when absent", "None" not in partial)

# ---- booking: empty string briefing fields -> treated as absent ------------
ctx_empty = {
    "name": "Bob", "when": "Monday", "lead_id": 3,
    "address": "", "project": "  ", "summary": ""
}
empty_msg = alerts.format_message("booking", ctx_empty)
check("booking: whitespace/empty briefing fields -> no 'Job:' suffix",
      "Job:" not in empty_msg)

# ---- roi_milestone: returns body from context ------------------------------
ctx_roi = {"body": "FirstBack has booked an estimated ~$2,200 in jobs for you -- about 22x its cost."}
roi_msg = alerts.format_message("roi_milestone", ctx_roi)
check("roi_milestone returns context body verbatim", roi_msg == ctx_roi["body"])

# ---- roi_milestone: fallback when body missing ----------------------------
roi_fallback = alerts.format_message("roi_milestone", {})
check("roi_milestone fallback is not empty", bool(roi_fallback))
check("roi_milestone fallback does not claim cash", "collected" not in roi_fallback.lower())

# ---- _subject for roi_milestone -------------------------------------------
subj = alerts._subject("roi_milestone")
check("_subject(roi_milestone) is not the generic fallback", subj != "FirstBack alert")
check("_subject(roi_milestone) mentions FirstBack", "FirstBack" in subj)

# ---- ALERT_KINDS includes roi_milestone ------------------------------------
check("roi_milestone in ALERT_KINDS", "roi_milestone" in alerts.ALERT_KINDS)

# ---- _TOGGLE_COL has an entry for roi_milestone ---------------------------
check("roi_milestone has a _TOGGLE_COL entry",
      "roi_milestone" in alerts._TOGGLE_COL)

# ---- _enabled_for: default ON when toggle unset ---------------------------
biz_no_toggle = {"id": 1}
check("roi_milestone _enabled_for defaults ON when toggle col unset",
      alerts._enabled_for(biz_no_toggle, "roi_milestone") is True)

# ---- _enabled_for: respects explicit False ---------------------------------
toggle_col = alerts._TOGGLE_COL["roi_milestone"]
biz_off = {"id": 1, toggle_col: 0}
check("roi_milestone _enabled_for respects explicit OFF",
      alerts._enabled_for(biz_off, "roi_milestone") is False)

biz_on = {"id": 1, toggle_col: 1}
check("roi_milestone _enabled_for respects explicit ON",
      alerts._enabled_for(biz_on, "roi_milestone") is True)

print(f"\n{_pass} passed, {_fail} failed")
raise SystemExit(1 if _fail else 0)
