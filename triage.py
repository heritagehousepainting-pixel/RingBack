"""Caller triage (v1): decide whether a missed caller is worth engaging.

RingBack's promise is "never lose a job to a missed call," which makes the costs
ASYMMETRIC: texting a non-prospect by mistake is cheap (a cent and a dead thread),
but NOT texting a real customer is the one failure the product exists to prevent.
So this layer suppresses with HIGH PRECISION -- it only stays silent for callers we
positively know are not prospects, never on a guess. Unknown callers are always
engaged.

v1 is deterministic + free: the per-business contact directory (db.contacts) plus
the existing opt-out ledger (db.contacts_consent). It cleanly answers the
"don't ask the power company if they need work done" case:

    prospect / unknown  -> engage (the default)
    customer (returning) -> engage
    personal (the owner's mom)     -> screen out
    vendor   (the power company)   -> screen out
    blocked  (a known nuisance)    -> screen out
    opted out (replied STOP)       -> screen out

Fuzzy telemarketer detection for UNKNOWN callers (AI content classification,
number-reputation lookup, mid-conversation bail) is a deferred later layer; this
module is its home. Pure decision helper (should_engage) + a thin DB-backed
screen_caller(); no network.
"""
import db

# Directory categories that are positively NOT a prospect -> never proactively
# texted. Everything else (prospect, customer, or an unknown number) engages.
NON_PROSPECT = {"personal", "vendor", "blocked"}


def should_engage(contact):
    """Pure: True unless the caller is a known non-prospect. A None contact means
    we have never seen this number, which we treat as a potential customer."""
    if not contact:
        return True
    return (contact.get("category") or "prospect") not in NON_PROSPECT


def screen_caller(business_id, number):
    """Verdict for a missed caller, BEFORE we text back:
    {"engage": bool, "category": str, "reason": str}.

    Screens out opted-out numbers and known non-prospects (the owner's directory);
    engages prospects, returning customers, and anyone we have not seen."""
    if db.is_suppressed(business_id, number):
        return {"engage": False, "category": "opted_out",
                "reason": "recipient opted out"}
    contact = db.get_contact(business_id, number)
    category = (contact or {}).get("category") or "prospect"
    if not should_engage(contact):
        return {"engage": False, "category": category,
                "reason": f"known {category}, not a prospect"}
    return {"engage": True, "category": category, "reason": "prospect"}


# --------------------------------------------------------------------------
# SUGGESTIONS  (QuickBooks-style: observe a caller, RECOMMEND a bucket, the
# owner confirms with one tap. Suggestions never auto-apply.)
# --------------------------------------------------------------------------
# Deliberately conservative thresholds -- a recommendation, not a verdict.
SPAM_MIN_CALLS = 3        # repeat missed calls with zero replies -> "looks like spam?"
CLIENT_MIN_BOOKINGS = 2   # multiple booked estimates -> "add to your clients?"


def suggest_category(signals):
    """Pure: from a caller's behavioral aggregates, recommend (category, reason),
    or None to leave them an engaged prospect. `signals`: {missed_calls,
    inbound_msgs, booked}. Booking is the strongest signal, so it wins."""
    booked = signals.get("booked") or 0
    missed = signals.get("missed_calls") or 0
    inbound = signals.get("inbound_msgs") or 0
    if booked >= CLIENT_MIN_BOOKINGS:
        return ("customer", f"Booked {booked} estimates with you.")
    if missed >= SPAM_MIN_CALLS and inbound == 0:
        return ("blocked", f"Called {missed} times and never replied to a text.")
    return None


def scan_suggestions(business_id):
    """Generate/refresh pending classification suggestions from observed behavior.
    Idempotent and off the hot path (run from the ticker). Never touches a number the
    owner already classified, nor a suggestion they dismissed. Returns the pending
    count."""
    classified = {c["number"] for c in db.list_contacts(business_id)}
    for s in db.caller_signals(business_id):
        if s["number"] in classified:
            continue  # already in the directory -> nothing to suggest
        rec = suggest_category(s)
        if rec:
            db.upsert_suggestion(business_id, s["number"], s.get("name") or None,
                                 rec[0], rec[1], "behavior")
    return db.count_pending_suggestions(business_id)


def scan_all_suggestions():
    """Scan every business (called from the reminders ticker, off the hot path)."""
    for biz in db.list_businesses():
        try:
            scan_suggestions(biz["id"])
        except Exception as e:
            import sys
            print(f"[ringback] suggestion scan failed (biz {biz.get('id')}): {e}",
                  file=sys.stderr, flush=True)
