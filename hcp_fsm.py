"""Housecall Pro (HCP) FSM provider — implements FSMProvider for Housecall Pro.

Read-only pull (customers, jobs). Push is a v1 no-op (see push_quote_request).

Gated: a safe no-op unless HCP_CLIENT_ID + HCP_CLIENT_SECRET are set.
Defensive: every network/API error is swallowed and logged; never raises into
a request or a scheduler tick.

FIX-1: OAuth URLs use api.housecallpro.com (not auth.housecallpro.com).
FIX-2: HTTP helpers use Authorization: Bearer <token> (not Token token=).
FIX-3: fetch_clients paginates by following next_page_url (not page/per_page).
FIX-4: Customer name = first_name + " " + last_name (joined).
FIX-5: Job title from description field; client_phone always "" (no inline phone).
FIX-6: push_quote_request is a defined no-op returning None (no confirmed endpoint).
FIX-7: SCOPES = "read:customers read:jobs" (TODO: verify via HCP developer dashboard).
FIX-8: _access_token refresh failure marks disconnected via db.set_oauth_tokens(...None).

Token lifecycle mirrors google_contacts.py:
  * _access_token: check access_is_fresh, refresh if stale, fail-open on error.
  * db.set_oauth_tokens / db.get_integration for all token persistence.
  * token_crypto handles encrypt/decrypt at rest.
"""
import sys
import requests
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import db
from fsm_provider import FSMProvider
from google_oauth import access_is_fresh
from config import (
    HCP_CLIENT_ID, HCP_CLIENT_SECRET,
    HCP_REDIRECT_URI,
)

# FIX-1: Correct HCP OAuth and API base URLs (verified from live HCP OpenAPI spec).
AUTH_URL  = "https://api.housecallpro.com/oauth/authorize"
TOKEN_URL = "https://api.housecallpro.com/oauth/token"
API_BASE  = "https://api.housecallpro.com"
PROVIDER  = "housecall_pro"
# FIX-7: Scope strings are not publicly documented; TODO verify via developer dashboard.
SCOPES    = "read:customers read:jobs"  # TODO verify exact HCP OAuth scopes via developer dashboard (not documented publicly)
_MAX_PAGES = 20   # safety cap on pagination iterations (20 × 25 = 500 customers per sync)


class HCPProvider(FSMProvider):
    PROVIDER_KEY = PROVIDER

    # ------------------------------------------------------------------
    # Gate
    # ------------------------------------------------------------------
    def configured(self) -> bool:
        """True if the app has Housecall Pro OAuth credentials."""
        return bool(HCP_CLIENT_ID and HCP_CLIENT_SECRET)

    def is_connected(self, business_id: int) -> bool:
        """True if this business has a valid HCP refresh token."""
        intg = db.get_integration(business_id, PROVIDER)
        return bool(intg and intg.get("connected") and intg.get("refresh_token"))

    # ------------------------------------------------------------------
    # OAuth flow
    # ------------------------------------------------------------------
    def auth_url(self, state: str) -> str:
        """OAuth2 authorization URL (redirect the owner here)."""
        return AUTH_URL + "?" + urlencode({
            "client_id":     HCP_CLIENT_ID,
            "redirect_uri":  HCP_REDIRECT_URI,
            "response_type": "code",
            "scope":         SCOPES,
            "state":         state,
        })

    def connect_with_code(self, business_id: int, code: str) -> None:
        """Exchange auth code for tokens and store them.

        Raises on HTTP error so the route can redirect to an error page.
        """
        r = requests.post(TOKEN_URL, data={
            "code":          code,
            "client_id":     HCP_CLIENT_ID,
            "client_secret": HCP_CLIENT_SECRET,
            "redirect_uri":  HCP_REDIRECT_URI,
            "grant_type":    "authorization_code",
        }, timeout=30)
        r.raise_for_status()
        tok = r.json()
        db.set_oauth_tokens(
            business_id, PROVIDER,
            tok.get("access_token"),
            tok.get("refresh_token"),
            _expiry_iso(tok),
        )

    def disconnect(self, business_id: int) -> None:
        """Clear HCP tokens for this business.

        Keeps already-synced contacts (contact_suggestions) in place —
        a disconnect is a de-auth, not a data wipe.
        """
        db.set_oauth_tokens(business_id, PROVIDER, None, None, None)

    # ------------------------------------------------------------------
    # Token management (internal)
    # ------------------------------------------------------------------
    def _access_token(self, business_id: int):
        """Return a valid access token, refreshing if needed.

        Returns None when not connected or on any refresh failure
        (fail-open: sync skips, screening is never broken).

        FIX-8: on refresh failure, mark the integration disconnected so
        the system doesn't retry infinitely on a revoked token.
        """
        intg = db.get_integration(business_id, PROVIDER)
        if not intg or not intg.get("refresh_token"):
            return None
        if intg.get("access_token") and access_is_fresh(intg.get("token_expiry")):
            return intg["access_token"]
        try:
            r = requests.post(TOKEN_URL, data={
                "client_id":     HCP_CLIENT_ID,
                "client_secret": HCP_CLIENT_SECRET,
                "refresh_token": intg["refresh_token"],
                "grant_type":    "refresh_token",
            }, timeout=30)
            r.raise_for_status()
            tok = r.json()
            # Refresh responses often omit the refresh token; keep the stored one.
            db.set_oauth_tokens(
                business_id, PROVIDER,
                tok.get("access_token"),
                tok.get("refresh_token") or intg["refresh_token"],
                _expiry_iso(tok),
            )
            return tok.get("access_token")
        except Exception as e:
            print(
                f"[firstback] hcp token refresh failed (biz {business_id}): {e}",
                file=sys.stderr, flush=True,
            )
            # FIX-8: mark disconnected so we don't hammer a revoked token on every tick.
            try:
                db.set_oauth_tokens(business_id, PROVIDER, None, None, None)
            except Exception as mark_e:
                print(
                    f"[firstback] hcp disconnect-on-refresh-fail error (biz {business_id}): {mark_e}",
                    file=sys.stderr, flush=True,
                )
            return None

    # ------------------------------------------------------------------
    # REST helpers (FIX-2: Authorization: Bearer)
    # ------------------------------------------------------------------
    def _get(self, business_id: int, path: str, params: dict = None):
        """GET request to the HCP API. Returns parsed JSON or None on error."""
        token = self._access_token(business_id)
        if not token:
            return None
        try:
            r = requests.get(
                API_BASE + path,
                params=params or {},
                headers={
                    "Authorization": f"Bearer {token}",  # FIX-2
                    "Content-Type": "application/json",
                },
                timeout=30,
            )
            r.raise_for_status()
            return r.json()
        except Exception as e:
            print(
                f"[firstback] hcp GET {path} error (biz {business_id}): {e}",
                file=sys.stderr, flush=True,
            )
            return None

    def _post(self, business_id: int, path: str, payload: dict = None):
        """POST request to the HCP API. Returns parsed JSON or None on error."""
        token = self._access_token(business_id)
        if not token:
            return None
        try:
            r = requests.post(
                API_BASE + path,
                json=payload or {},
                headers={
                    "Authorization": f"Bearer {token}",  # FIX-2
                    "Content-Type": "application/json",
                },
                timeout=30,
            )
            r.raise_for_status()
            return r.json()
        except Exception as e:
            print(
                f"[firstback] hcp POST {path} error (biz {business_id}): {e}",
                file=sys.stderr, flush=True,
            )
            return None

    # ------------------------------------------------------------------
    # Fetch clients (paginated REST — FIX-3: follow next_page_url)
    # ------------------------------------------------------------------
    def fetch_clients(self, business_id: int) -> list:
        """Return this business's HCP customers as [{name, phones, email}].

        FIX-3: uses page_size=25 and paginates by following next_page_url
        in the response envelope until it is null/absent. Caps at _MAX_PAGES.

        FIX-4: name = (first_name + " " + last_name).strip(); phones = filter
        of [mobile_number, home_number, work_number] (non-empty strings only).

        Returns [] when not connected or on any error.
        """
        out = []
        # FIX-3: first request uses path + page_size; subsequent requests follow next_page_url.
        next_url = API_BASE + "/customers"
        params = {"page_size": 25}

        for _ in range(_MAX_PAGES):
            token = self._access_token(business_id)
            if not token:
                break
            try:
                r = requests.get(
                    next_url,
                    params=params,
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Content-Type": "application/json",
                    },
                    timeout=30,
                )
                r.raise_for_status()
                data = r.json()
            except Exception as e:
                print(
                    f"[firstback] hcp fetch_clients error (biz {business_id}): {e}",
                    file=sys.stderr, flush=True,
                )
                break

            for customer in (data.get("customers") or []):
                # FIX-4: join first_name + last_name
                first = (customer.get("first_name") or "").strip()
                last  = (customer.get("last_name") or "").strip()
                name  = (first + " " + last).strip()
                # FIX-4: filter the three phone fields to non-empty strings
                phones = [
                    p for p in (
                        customer.get("mobile_number"),
                        customer.get("home_number"),
                        customer.get("work_number"),
                    )
                    if p
                ]
                if phones:
                    out.append({
                        "name":   name or None,
                        "phones": phones,
                        "email":  (customer.get("email") or "").strip(),
                    })

            # FIX-3: follow next_page_url; stop when absent or null
            next_page = data.get("next_page_url")
            if not next_page:
                break
            next_url = next_page
            params = {}   # next_page_url already contains pagination params

        return out

    # ------------------------------------------------------------------
    # Fetch jobs
    # ------------------------------------------------------------------
    def fetch_jobs(self, business_id: int) -> list:
        """Return recent HCP jobs as [{title, status, client_phone}].

        FIX-5: title from `description` field (not `note`).
        FIX-5: client_phone is always "" — HCP jobs carry only customer_id,
               no inline phone number. A separate customer lookup would be
               needed (not performed here to avoid N+1 calls).

        Returns [] on error or when not connected.
        """
        data = self._get(business_id, "/jobs")
        if not data:
            return []
        out = []
        for job in (data.get("jobs") or []):
            # FIX-5: use description as title proxy
            title = (job.get("description") or "").strip()
            status = (job.get("work_status") or "").strip()
            # FIX-5: no inline phone — jobs only carry customer_id
            out.append({
                "title":        title,
                "status":       status,
                "client_phone": "",   # HCP jobs carry only customer_id; no inline phone
            })
        return out

    # ------------------------------------------------------------------
    # Push quote request (FIX-6: v1 no-op)
    # ------------------------------------------------------------------
    def push_quote_request(self, business_id: int, lead: dict, booking: dict):
        """Push a booked FirstBack estimate to HCP.

        FIX-6: v1 no-op returning None. HCP has no confirmed public
        customer-notes endpoint, and the phone-number filter on /customers
        is not documented — so the full push pipeline (phone→customer lookup
        → note creation) cannot be built reliably. Never claims "pushed";
        never calls db.set_fsm_external_id for HCP.

        Returns None always.
        """
        # v1 no-op: no confirmed notes endpoint / phone filter in HCP public API.
        return None


# Module-level singleton (mirrors jobber_fsm / google_contacts usage pattern)
_provider = HCPProvider()


def configured() -> bool:
    return _provider.configured()


def is_connected(business_id: int) -> bool:
    return _provider.is_connected(business_id)


def auth_url(state: str) -> str:
    return _provider.auth_url(state)


def connect_with_code(business_id: int, code: str) -> None:
    return _provider.connect_with_code(business_id, code)


def disconnect(business_id: int) -> None:
    return _provider.disconnect(business_id)


def fetch_clients(business_id: int) -> list:
    return _provider.fetch_clients(business_id)


def fetch_jobs(business_id: int) -> list:
    return _provider.fetch_jobs(business_id)


def push_quote_request(business_id: int, lead: dict, booking: dict):
    return _provider.push_quote_request(business_id, lead, booking)


def _access_token(business_id: int):
    """Exposed for tests."""
    return _provider._access_token(business_id)


# ------------------------------------------------------------------
# Utility
# ------------------------------------------------------------------
def _expiry_iso(tok):
    secs = int(tok.get("expires_in", 3600))
    return (datetime.now(timezone.utc) + timedelta(seconds=secs)).isoformat()
