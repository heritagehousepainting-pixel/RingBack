"""Microsoft Outlook / Microsoft 365 Calendar sync for FirstBack, scoped per business.

Design goals (mirrors google_cal.py):
  * Gated: every entry point is a safe no-op unless Outlook is CONFIGURED
    (MICROSOFT_CLIENT_ID/SECRET set) and the business is CONNECTED (has tokens).
  * Defensive: any network/API error is swallowed and logged, never breaking a
    customer reply or a booking. Availability simply falls back to the in-house
    calendar; a missed event-create is logged.
  * Light: uses `requests` against Microsoft Graph endpoints (no heavy MS SDK).

OAuth: standard web server flow with offline_access scope so we get a refresh
token, then mint short-lived access tokens on demand.

Timezone note: MS Graph `me/mailboxSettings.timeZone` returns Windows timezone
names ("Eastern Standard Time"), NOT IANA. We include a Windows→IANA shim
(~15 common US zones) and try: direct ZoneInfo → shim → fail-open.

Refresh-token expiry (F8): MS personal refresh tokens expire after 24h of
inactivity or 90 days. On refresh failure we mark the integration disconnected
(set_oauth_tokens to None) so is_connected() returns False and the Settings
card shows "Reconnect Outlook."

v1 design note: per-provider event-id columns (google_event_id, outlook_event_id)
are fine for two providers. A third provider would warrant a
calendar_events(appointment_id, provider, event_id) junction table.
"""
import sys
from datetime import datetime, timedelta, timezone, date as _date
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

import db
from google_oauth import access_is_fresh
from config import (MICROSOFT_CLIENT_ID, MICROSOFT_CLIENT_SECRET, MICROSOFT_REDIRECT_URI,
                    MICROSOFT_TENANT_ID, ESTIMATE_TIMES, BOOKING_HORIZON_DAYS)

_TENANT = MICROSOFT_TENANT_ID or "common"
AUTH_URL = f"https://login.microsoftonline.com/{_TENANT}/oauth2/v2.0/authorize"
TOKEN_URL = f"https://login.microsoftonline.com/{_TENANT}/oauth2/v2.0/token"
API_BASE = "https://graph.microsoft.com/v1.0"
# Delegated permissions: read/write calendar events + offline refresh tokens.
# NOTE: prompt=consent ensures a refresh token is always returned (same as Google).
SCOPES = "https://graph.microsoft.com/Calendars.ReadWrite offline_access"
PROVIDER = "outlook"

# F6: Windows timezone name → IANA name shim (~15 common US zones).
# MS Graph mailboxSettings.timeZone returns Windows names for the majority of users.
# ZoneInfo("Eastern Standard Time") raises KeyError, so we convert first.
_WINDOWS_TZ_TO_IANA = {
    "Eastern Standard Time":       "America/New_York",
    "Eastern Daylight Time":       "America/New_York",
    "Central Standard Time":       "America/Chicago",
    "Central Daylight Time":       "America/Chicago",
    "Mountain Standard Time":      "America/Denver",
    "Mountain Daylight Time":      "America/Denver",
    "US Mountain Standard Time":   "America/Phoenix",   # Arizona (no DST)
    "Pacific Standard Time":       "America/Los_Angeles",
    "Pacific Daylight Time":       "America/Los_Angeles",
    "Alaskan Standard Time":       "America/Anchorage",
    "Alaskan Daylight Time":       "America/Anchorage",
    "Hawaiian Standard Time":      "Pacific/Honolulu",
    "Atlantic Standard Time":      "America/Halifax",
    "Atlantic Daylight Time":      "America/Halifax",
    "UTC":                         "UTC",
    "GMT Standard Time":           "Europe/London",
    "Central Europe Standard Time": "Europe/Berlin",
}


def _resolve_tz_name(tz_name):
    """Try tz_name as a direct IANA name, then the Windows→IANA shim.
    Returns the IANA name string or None (fail-open: caller skips the store)."""
    if not tz_name:
        return None
    # Try it as-is (IANA names like "America/New_York" pass directly).
    try:
        ZoneInfo(tz_name)
        return tz_name
    except (KeyError, Exception):
        pass
    # Fall through to the Windows shim.
    iana = _WINDOWS_TZ_TO_IANA.get(tz_name)
    if iana:
        try:
            ZoneInfo(iana)
            return iana
        except (KeyError, Exception):
            pass
    return None  # unknown timezone — fail-open, don't store


def configured():
    """True if the app has Microsoft OAuth credentials at all."""
    return bool(MICROSOFT_CLIENT_ID and MICROSOFT_CLIENT_SECRET)


def is_connected(business_id):
    """True if this business has linked an Outlook account (has a refresh token)."""
    intg = db.get_integration(business_id, PROVIDER)
    return bool(intg and intg.get("connected") and intg.get("refresh_token"))


# ---- OAuth flow ----
def auth_url(state):
    """The Microsoft consent URL to redirect the contractor to."""
    return AUTH_URL + "?" + urlencode({
        "client_id": MICROSOFT_CLIENT_ID,
        "redirect_uri": MICROSOFT_REDIRECT_URI,
        "response_type": "code",
        "response_mode": "query",
        "scope": SCOPES,
        "prompt": "consent",   # ensure a refresh token is returned every time
        "state": state,
    })


def connect_with_code(business_id, code):
    """Exchange an auth code for tokens and store them for the business.
    SF-5 (Outlook): after token exchange, read mailboxSettings.timeZone via
    Graph and persist it via db.set_business_timezone. Fail-open: a bad or
    Windows timezone name never breaks the connect; we log and continue.
    F6: handles Windows timezone names via _resolve_tz_name shim."""
    import requests
    r = requests.post(TOKEN_URL, data={
        "code": code,
        "client_id": MICROSOFT_CLIENT_ID,
        "client_secret": MICROSOFT_CLIENT_SECRET,
        "redirect_uri": MICROSOFT_REDIRECT_URI,
        "grant_type": "authorization_code",
    }, timeout=30)
    r.raise_for_status()
    tok = r.json()
    db.set_oauth_tokens(business_id, PROVIDER,
                        tok.get("access_token"),
                        tok.get("refresh_token"),
                        _expiry_iso(tok))
    # SF-5: read the mailbox timezone and persist it (Windows→IANA via shim).
    try:
        access_tok = tok.get("access_token")
        if access_tok:
            mb_r = requests.get(f"{API_BASE}/me/mailboxSettings",
                                headers={"Authorization": f"Bearer {access_tok}"},
                                timeout=20)
            mb_r.raise_for_status()
            tz_name_raw = mb_r.json().get("timeZone")
            if tz_name_raw:
                iana_name = _resolve_tz_name(tz_name_raw)
                if iana_name:
                    db.set_business_timezone(business_id, iana_name)
                else:
                    print(f"[firstback] outlook unknown timezone {tz_name_raw!r} "
                          f"(biz {business_id}); not stored", file=sys.stderr, flush=True)
    except Exception as e:
        print(f"[firstback] outlook timezone read failed (biz {business_id}): {e}",
              file=sys.stderr, flush=True)
        # Fail-open: the connect still succeeds.


def disconnect(business_id):
    """Forget a business's Outlook tokens and mark it disconnected."""
    db.set_oauth_tokens(business_id, PROVIDER, None, None, None)


def _expiry_iso(tok):
    secs = int(tok.get("expires_in", 3600))
    return (datetime.now(timezone.utc) + timedelta(seconds=secs)).isoformat()


def _access_token(business_id):
    """A valid access token for the business, refreshing if needed. None if the
    business is not connected or a refresh fails.

    F8 (MS refresh-token expiry): MS personal refresh tokens expire after 24h
    of inactivity or 90 days. On any refresh failure we mark the integration
    disconnected (clear tokens) so is_connected() returns False and the Settings
    card shows 'Reconnect Outlook' instead of silently failing on every turn."""
    intg = db.get_integration(business_id, PROVIDER)
    if not intg or not intg.get("refresh_token"):
        return None
    if intg.get("access_token") and access_is_fresh(intg.get("token_expiry")):
        return intg["access_token"]
    # Refresh.
    import requests
    try:
        r = requests.post(TOKEN_URL, data={
            "client_id": MICROSOFT_CLIENT_ID,
            "client_secret": MICROSOFT_CLIENT_SECRET,
            "refresh_token": intg["refresh_token"],
            "grant_type": "refresh_token",
            "scope": SCOPES,
        }, timeout=30)
        r.raise_for_status()
        tok = r.json()
        # Refresh responses may omit the refresh token; keep the stored one.
        db.set_oauth_tokens(business_id, PROVIDER,
                            tok.get("access_token"),
                            tok.get("refresh_token") or intg["refresh_token"],
                            _expiry_iso(tok))
        return tok.get("access_token")
    except Exception as e:
        print(f"[firstback] outlook token refresh failed (biz {business_id}): {e}",
              file=sys.stderr, flush=True)
        # F8: mark disconnected so Settings shows "Reconnect Outlook".
        try:
            db.set_oauth_tokens(business_id, PROVIDER, None, None, None)
        except Exception as _ce:
            print(f"[firstback] outlook disconnect-on-refresh-fail error "
                  f"(biz {business_id}): {_ce}", file=sys.stderr, flush=True)
        return None


# ---- Availability (calendarView) + event creation ----
def _slot_dt(day_iso, time_key_str, tz=None):
    """Tz-aware datetime for a slot ('2026-06-15', '09:00').
    When `tz` (a ZoneInfo instance) is given, the slot is anchored in that zone
    so DST is handled correctly. When tz is None, astimezone() uses the server's
    local timezone (preserves pre-Phase-2 behavior)."""
    y, m, d = (int(x) for x in day_iso.split("-"))
    hh, mm = (int(x) for x in time_key_str.split(":"))
    if tz is not None:
        return datetime(y, m, d, hh, mm, tzinfo=tz)
    return datetime(y, m, d, hh, mm).astimezone()


def busy_slot_ids(business_id):
    """Slot ids ('YYYY-MM-DD@HH:MM') across the booking horizon that conflict
    with the business's Outlook calendar. Empty set if not connected or on error,
    so the AI simply falls back to the in-house calendar.

    Uses Graph calendarView (returns all events in [start, end)) which is the
    correct Graph API for free/busy (not the freebusy endpoint, which doesn't
    exist on Graph v1). Returns normalized slot-id strings."""
    token = _access_token(business_id)
    if not token:
        return set()
    today = datetime.now().date()
    win_start = _slot_dt((today + timedelta(days=1)).isoformat(), "00:00")
    win_end = _slot_dt((today + timedelta(days=BOOKING_HORIZON_DAYS + 1)).isoformat(), "00:00")
    import requests
    try:
        r = requests.get(
            f"{API_BASE}/me/calendar/calendarView",
            headers={"Authorization": f"Bearer {token}"},
            params={
                "startDateTime": win_start.isoformat(),
                "endDateTime": win_end.isoformat(),
                "$select": "start,end,showAs,isAllDay",
                "$top": "100",
            },
            timeout=20)
        r.raise_for_status()
        intervals = r.json().get("value", [])
    except Exception as e:
        print(f"[firstback] outlook calendarView failed (biz {business_id}): {e}",
              file=sys.stderr, flush=True)
        return set()
    return _graph_slots_conflicting(intervals, today)


def _graph_slots_conflicting(intervals, today):
    """Pure helper (unit-testable): given Graph calendarView items
    [{start:{dateTime,timeZone}, end:{dateTime,timeZone}, isAllDay?}],
    return the set of estimate slot ids that overlap one. Each estimate is
    treated as a one-hour block.

    Graph returns timed events with {dateTime, timeZone} and all-day events
    with isAllDay=true (dateTime is midnight UTC). We normalize both to
    tz-aware datetimes for conflict detection."""
    busy = []
    for iv in intervals:
        try:
            is_all_day = iv.get("isAllDay", False)
            start_raw = iv.get("start") or {}
            end_raw = iv.get("end") or {}
            if is_all_day:
                # All-day: dateTime is midnight of the day in UTC. Parse as date.
                s_dt_str = (start_raw.get("dateTime") or "").split("T")[0]
                e_dt_str = (end_raw.get("dateTime") or "").split("T")[0]
                if not s_dt_str or not e_dt_str:
                    continue
                s_date = _date.fromisoformat(s_dt_str)
                e_date = _date.fromisoformat(e_dt_str)
                # Treat as covering [s_date 00:00, e_date 00:00) local time.
                bs = datetime(s_date.year, s_date.month, s_date.day).astimezone()
                be = datetime(e_date.year, e_date.month, e_date.day).astimezone()
                busy.append((bs, be))
            else:
                s_str = (start_raw.get("dateTime") or "").replace("Z", "+00:00")
                e_str = (end_raw.get("dateTime") or "").replace("Z", "+00:00")
                if not s_str or not e_str:
                    continue
                bs = datetime.fromisoformat(s_str)
                be = datetime.fromisoformat(e_str)
                # Graph normally returns UTC ('Z'); if a payload ever lacks an
                # offset, assume UTC so the aware/naive comparison below can't
                # raise and silently void every busy slot for this call.
                if bs.tzinfo is None:
                    bs = bs.replace(tzinfo=timezone.utc)
                if be.tzinfo is None:
                    be = be.replace(tzinfo=timezone.utc)
                busy.append((bs, be))
        except (ValueError, KeyError, AttributeError, TypeError):
            continue
    out = set()
    for i in range(1, BOOKING_HORIZON_DAYS + 1):
        day = (today + timedelta(days=i)).isoformat()
        for t in ESTIMATE_TIMES:
            tk = db.time_key(t)
            s = _slot_dt(day, tk)
            e = s + timedelta(hours=1)
            if any(bs < e and s < be for (bs, be) in busy):
                out.add(f"{day}@{tk}")
    return out


def create_event(business_id, summary, description, day_iso, time_key_str, tz=None):
    """Create a 1-hour event on the business's Outlook calendar via Graph API.
    Returns the event id, or None if not connected or on error.

    Graph carries timezone per field (start.timeZone, end.timeZone), so we
    send the IANA name directly without converting to UTC. When tz is None,
    server-local tz is used (preserves pre-Phase-2 behavior)."""
    token = _access_token(business_id)
    if not token:
        return None
    start = _slot_dt(day_iso, time_key_str, tz=tz)
    end = start + timedelta(hours=1)
    # Determine the timezone name to send (Graph requires a timezone per field).
    tz_name = getattr(tz, "key", None) or str(start.tzinfo) or "UTC"
    import requests
    try:
        r = requests.post(
            f"{API_BASE}/me/calendar/events",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "subject": summary,
                "body": {"contentType": "Text", "content": description},
                "start": {"dateTime": start.strftime("%Y-%m-%dT%H:%M:%S"), "timeZone": tz_name},
                "end":   {"dateTime": end.strftime("%Y-%m-%dT%H:%M:%S"),   "timeZone": tz_name},
            },
            timeout=20)
        r.raise_for_status()
        return r.json().get("id")
    except Exception as e:
        print(f"[firstback] outlook event create failed (biz {business_id}): {e}",
              file=sys.stderr, flush=True)
        return None


def create_event_and_store(business_id, appointment_id, summary, description,
                           day_iso, time_key_str, tz=None):
    """Create a calendar event and persist the Outlook event id on the appointment
    row via db.set_outlook_event_id. Returns the event id or None."""
    event_id = create_event(business_id, summary, description, day_iso, time_key_str, tz=tz)
    if event_id and appointment_id is not None:
        try:
            db.set_outlook_event_id(appointment_id, business_id, event_id)
        except Exception as e:
            print(f"[firstback] set_outlook_event_id failed (appt {appointment_id}): {e}",
                  file=sys.stderr, flush=True)
    return event_id


def create_event_async(business_id, appointment_id, summary, description,
                       day_iso, time_key_str, tz=None):
    """Fire-and-forget event creation so booking never blocks on Outlook.
    Stores the returned event id on the appointment row."""
    import threading
    threading.Thread(target=create_event_and_store,
                     args=(business_id, appointment_id, summary, description,
                           day_iso, time_key_str),
                     kwargs={"tz": tz},
                     daemon=True).start()


def cancel_event(business_id, outlook_event_id):
    """Delete an Outlook Calendar event by its Graph id. Idempotent: a 404 (already
    gone) is treated as success. Returns True on success/already-gone, False on error."""
    if not outlook_event_id:
        return False
    token = _access_token(business_id)
    if not token:
        return False
    import requests
    try:
        r = requests.delete(
            f"{API_BASE}/me/calendar/events/{outlook_event_id}",
            headers={"Authorization": f"Bearer {token}"},
            timeout=20)
        if r.status_code in (204, 200, 404):
            return True
        r.raise_for_status()
        return True
    except requests.exceptions.HTTPError as e:
        if e.response is not None and e.response.status_code == 404:
            return True   # already gone -- idempotent
        print(f"[firstback] outlook event cancel failed (biz {business_id}, "
              f"event {outlook_event_id}): {e}", file=sys.stderr, flush=True)
        return False
    except Exception as e:
        print(f"[firstback] outlook event cancel failed (biz {business_id}, "
              f"event {outlook_event_id}): {e}", file=sys.stderr, flush=True)
        return False


def cancel_event_async(business_id, outlook_event_id):
    """Fire-and-forget event cancellation."""
    import threading
    threading.Thread(target=cancel_event,
                     args=(business_id, outlook_event_id),
                     daemon=True).start()
