"""What can actually reach a contractor's customers right now -- one honest read of every
channel, derived from the activation machine + the live integrations.

This is the dashboard/wizard's source of truth for "are you live, and how?". It encodes the
ONBOARDING_BLUEPRINT.md model: the day-0 catch is VOICE (missed calls answered from the
contractor's own number, no A2P), email is an independent zero-delay channel, and automatic
SMS turns on only when the contractor's own number clears 10DLC. There is no platform
toll-free anywhere; during the 10DLC wait, optional click-to-send lets Vic draft texts the
contractor taps to send from their own phone.

Pure-ish + defensive: every probe is wrapped so a misconfigured integration never breaks the
read; an unknown/empty business degrades to the 'setup' picture.
"""
import compliance
import db
import google_mail


def _voice_live(biz):
    """Missed calls are being caught: the business has its own number AND has confirmed
    carrier call-forwarding to it."""
    return bool(biz.get("twilio_number") and biz.get("forwarding_confirmed"))


def _email_live(biz):
    try:
        return bool(google_mail.is_connected(biz.get("id")))
    except Exception:
        return False


def _sms_auto(biz):
    """Fully automatic SMS text-back from the contractor's OWN number (10DLC approved)."""
    try:
        return bool(compliance.a2p_ready(biz))
    except Exception:
        return False


def channel_state(biz):
    """A dict describing every channel for a business:
        {
          activation_state, voice, email, sms_auto, click_to_send,
          active_channels: [..], day0_live: bool, best_outbound: str|None, next_step: str
        }
    `day0_live` is the thing that matters for go-live: is the contractor catching leads at all
    yet (voice OR email), with zero dependence on the 10DLC wait."""
    biz = biz or {}
    voice = _voice_live(biz)
    email = _email_live(biz)
    sms_auto = _sms_auto(biz)
    # Click-to-send only matters as a bridge: opted in, and not yet on automatic SMS.
    click_to_send = bool(biz.get("click_to_send_optin")) and not sms_auto

    active = []
    if voice:
        active.append("voice")
    if email:
        active.append("email")
    if sms_auto:
        active.append("sms")
    elif click_to_send:
        active.append("click_to_send")

    return {
        "activation_state": biz.get("activation_state") or "setup",
        "voice": voice,
        "email": email,
        "sms_auto": sms_auto,
        "click_to_send": click_to_send,
        "active_channels": active,
        "day0_live": voice or email,
        "best_outbound": best_outbound_channel(biz, _sms_auto=sms_auto,
                                               _click=click_to_send, _email=email),
        "next_step": _next_step(voice, email, sms_auto),
    }


def best_outbound_channel(biz, _sms_auto=None, _click=None, _email=None):
    """The best way to TEXT/REACH a customer right now, in order of preference:
    automatic SMS (own number) -> click-to-send draft -> email -> None. The private args let
    channel_state reuse already-computed probes; callers pass just `biz`."""
    sms_auto = _sms_auto if _sms_auto is not None else _sms_auto_safe(biz)
    if sms_auto:
        return "sms"
    click = _click if _click is not None else (bool(biz.get("click_to_send_optin")) and not sms_auto)
    if click:
        return "click_to_send"
    email = _email if _email is not None else _email_live(biz)
    if email:
        return "email"
    return None


def _sms_auto_safe(biz):
    return _sms_auto(biz)


def _next_step(voice, email, sms_auto):
    """The single most useful thing the contractor should do next."""
    if not voice:
        return "Set up call forwarding so missed calls reach FirstBack."
    if not email:
        return "Connect Gmail so FirstBack answers email leads too."
    if not sms_auto:
        return "Your number is registering with carriers (~14 days) -- automatic texts turn on then."
    return "You're fully live: calls, email, and texts all answered."
