"""Compliance + deliverability helpers for the callback system (Phase 2).

The real launch gate for live SMS/voice is mostly ACCOUNT + LEGAL work, not code:
A2P 10DLC brand/campaign registration, STIR/SHAKEN attestation, and a TCPA review
(see USER_TO_DO.md and CALLBACK_SYSTEM_PLAN.md section 6). What lives here is the
code half: honoring opt-outs phrased in plain language (not just the word STOP),
keeping automated VOICE inside quiet hours, and reporting how registration-ready a
business is so the UI never implies "live" before it really is.

Not legal advice.
"""
import re
from datetime import datetime

from config import app_tz, QUIET_START, QUIET_END

# Natural-language opt-out ("any reasonable means", per the 2025 FCC consent-
# revocation rule), beyond the exact CTIA keywords (STOP/UNSUBSCRIBE/...) the
# webhook matches separately. Conservative patterns so ordinary words like
# "stop by the house" do not trip it.
_REVOKE_RES = [re.compile(p) for p in (
    r"\bstop (texting|messaging|contacting|calling|msg|the texts?)",
    r"\b(do ?not|don'?t|please don'?t|never) (text|message|msg|contact|call|phone) me",
    r"\b(take|remove) me off",
    r"\bremove me\b",
    r"\bunsubscribe me\b",
    r"\bno more (texts?|messages?|calls?)\b",
    r"\bleave me alone\b",
    r"\bquit (texting|messaging|contacting|calling)\b",
    r"\bnot interested\b.*\b(stop|don'?t)\b",
)]


def detect_revocation(text):
    """True if the message is a plain-language request to stop contact, even when
    it isn't the exact keyword STOP."""
    t = (text or "").lower()
    return any(p.search(t) for p in _REVOKE_RES)


def voice_allowed_now(now=None, quiet_start=None, quiet_end=None):
    """True if the current business-local time is inside the allowed window
    [QUIET_START, QUIET_END). The TCPA bars automated calls/texts outside it; we
    gate the AI VOICE callback hard. (An immediate text reply to a call the consumer
    just placed is consumer-initiated, so it is not gated here.) Operators who want
    the stricter 8am-8pm state rule can set RINGBACK_QUIET_END=20."""
    qs = QUIET_START if quiet_start is None else quiet_start
    qe = QUIET_END if quiet_end is None else quiet_end
    hour = (now or datetime.now(app_tz())).hour
    return qs <= hour < qe


# ---- Registration readiness (honest "is this business actually live?") ----
def a2p_status(business):
    return (business or {}).get("a2p_status") or "unregistered"


def a2p_ready(business):
    """True once the tenant's A2P 10DLC brand + campaign are approved (set by the
    registration process documented in USER_TO_DO.md). US carriers filter
    unregistered local-number traffic, so this is what 'can really text' means."""
    return a2p_status(business) == "approved"


def launch_blockers(business, sms_configured):
    """Plain-English list of what still stands between this business and sending for
    real. Empty list means ready. Drives honest Settings / onboarding copy so we
    never show a dormant feature as live."""
    b = business or {}
    out = []
    if not sms_configured:
        out.append("Twilio credentials are not set on the server.")
    if not b.get("twilio_number"):
        out.append("No RingBack phone number is provisioned yet.")
    if not a2p_ready(b):
        out.append(f"A2P 10DLC registration is not approved yet (status: {a2p_status(b)}).")
    if not b.get("forward_to"):
        out.append("No contractor cell is set to ring on inbound calls.")
    return out
