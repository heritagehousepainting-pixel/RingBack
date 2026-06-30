"""ServiceTitan FSM provider — implements FSMProvider for ServiceTitan.

Read-only pull (clients, jobs) + one additive write (a CRM booking/lead).

ServiceTitan differs from Jobber/HCP in TWO ways, both handled here:
  1. Auth is OAuth2 *client-credentials* (app-level CLIENT_ID/SECRET), not a per-user
     authorization-code redirect. Access tokens are short-lived (~15 min) and minted on
     demand from the app creds — there is NO long-lived refresh token.
  2. Every request carries the `ST-App-Key` header and is TENANT-scoped:
     {api}/{module}/v2/tenant/{tenant}/...

So the per-business connection identity is the contractor's TENANT ID (entered once in the
connect form). We persist it in the integration row's `refresh_token` column — there's no real
refresh token to store there, and it lets is_connected()/get_integration() work unchanged with
no schema migration. The short-lived access token + expiry use the normal access_token columns.

Gated: a safe no-op unless SERVICETITAN_CLIENT_ID + _CLIENT_SECRET + _APP_KEY are all set.
Defensive: every network/API error is swallowed and logged; never raises into a request or tick
(connect_tenant is the one exception — it raises so the route can show a clear error).

⚠️ Built to ServiceTitan's documented v2 REST API. The exact endpoint paths / field names
(esp. the bookings write) should be confirmed against a live tenant when real credentials are
provided — every read degrades to [] and the write degrades to None if a shape is off, so a
mismatch never breaks FirstBack; it just syncs/pushes nothing until tuned.
See: https://developer.servicetitan.io/
"""
import sys
import requests
from datetime import datetime, timedelta, timezone

import db
from fsm_provider import FSMProvider
from google_oauth import access_is_fresh
from config import (
    SERVICETITAN_CLIENT_ID, SERVICETITAN_CLIENT_SECRET,
    SERVICETITAN_APP_KEY, SERVICETITAN_ENV,
)

PROVIDER = "servicetitan"
_MAX_PAGES = 20          # safety cap: 20 × 100 = 2,000 records per sync
_PAGE_SIZE = 100
_PHONE_TYPES = {"phone", "mobilephone", "mobile", "phonenumber"}
_EMAIL_TYPES = {"email"}


def _auth_base() -> str:
    return ("https://auth-integration.servicetitan.io"
            if SERVICETITAN_ENV == "integration"
            else "https://auth.servicetitan.io")


def _api_base() -> str:
    return ("https://api-integration.servicetitan.io"
            if SERVICETITAN_ENV == "integration"
            else "https://api.servicetitan.io")


class ServiceTitanFSM(FSMProvider):
    PROVIDER_KEY = PROVIDER

    # ------------------------------------------------------------------
    # Gate
    # ------------------------------------------------------------------
    def configured(self) -> bool:
        """True if the app has ServiceTitan client-credentials + app key."""
        return bool(SERVICETITAN_CLIENT_ID and SERVICETITAN_CLIENT_SECRET and SERVICETITAN_APP_KEY)

    def is_connected(self, business_id: int) -> bool:
        """True if this business has a stored ServiceTitan tenant id (the connection identity,
        kept in the refresh_token column)."""
        intg = db.get_integration(business_id, PROVIDER)
        return bool(intg and intg.get("connected") and intg.get("refresh_token"))

    # ------------------------------------------------------------------
    # Connection (client-credentials: no redirect — the owner enters a tenant id)
    # ------------------------------------------------------------------
    def connect_tenant(self, business_id: int, tenant_id: str) -> None:
        """Store the contractor's ServiceTitan tenant id and validate the app credentials by
        minting a token. Raises on bad input or HTTP error so the route can surface it.

        The tenant id is persisted in the refresh_token column; the freshly minted access token
        + expiry use the access_token columns. (Tenant access itself is verified on first sync —
        a token mints from app creds alone.)"""
        tenant_id = (tenant_id or "").strip()
        if not tenant_id.isdigit():
            raise ValueError("ServiceTitan tenant id must be numeric")
        tok = self._mint_token()   # raises on bad app creds
        db.set_oauth_tokens(
            business_id, PROVIDER,
            tok.get("access_token"),
            tenant_id,                 # connection identity (no real refresh token exists)
            _expiry_iso(tok),
        )

    def disconnect(self, business_id: int) -> None:
        """Clear ServiceTitan for this business (forgets the tenant id + token). Keeps any
        already-synced contact suggestions — a disconnect is a de-auth, not a data wipe."""
        db.set_oauth_tokens(business_id, PROVIDER, None, None, None)

    # The base interface's redirect-OAuth hooks don't apply to client-credentials.
    def auth_url(self, state: str) -> str:
        raise NotImplementedError("ServiceTitan uses client-credentials; connect via connect_tenant().")

    def connect_with_code(self, business_id: int, code: str) -> None:
        raise NotImplementedError("ServiceTitan uses client-credentials; connect via connect_tenant().")

    # ------------------------------------------------------------------
    # Token management (internal)
    # ------------------------------------------------------------------
    def _mint_token(self) -> dict:
        """Mint a client-credentials access token from the app creds. Raises on HTTP error."""
        r = requests.post(
            _auth_base() + "/connect/token",
            data={
                "grant_type": "client_credentials",
                "client_id": SERVICETITAN_CLIENT_ID,
                "client_secret": SERVICETITAN_CLIENT_SECRET,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=30,
        )
        r.raise_for_status()
        return r.json()

    def _access_token(self, business_id: int):
        """A valid access token for the business, minting a fresh one when the cached one is
        stale. Returns None when not connected or on any mint failure (fail-open: sync skips)."""
        intg = db.get_integration(business_id, PROVIDER)
        if not intg or not intg.get("refresh_token"):   # no tenant id => not connected
            return None
        if intg.get("access_token") and access_is_fresh(intg.get("token_expiry")):
            return intg["access_token"]
        try:
            tok = self._mint_token()
            # Keep the tenant id (refresh_token col) — pass None so set_oauth_tokens preserves it.
            db.set_oauth_tokens(business_id, PROVIDER, tok.get("access_token"), None, _expiry_iso(tok))
            return tok.get("access_token")
        except Exception as e:
            print(f"[firstback] servicetitan token mint failed (biz {business_id}): {e}",
                  file=sys.stderr, flush=True)
            return None

    def _tenant_id(self, business_id: int):
        intg = db.get_integration(business_id, PROVIDER)
        return (intg or {}).get("refresh_token")   # tenant id is stored here

    # ------------------------------------------------------------------
    # REST helpers
    # ------------------------------------------------------------------
    def _get_pages(self, business_id: int, module: str, resource: str, params: dict = None):
        """Yield each row across paginated GET {api}/{module}/v2/tenant/{tenant}/{resource}.
        Stops at _MAX_PAGES or when the API reports no more pages. Yields nothing on any error
        or when not connected (defensive)."""
        token = self._access_token(business_id)
        tenant = self._tenant_id(business_id)
        if not token or not tenant:
            return
        base = f"{_api_base()}/{module}/v2/tenant/{tenant}/{resource}"
        headers = {"Authorization": f"Bearer {token}", "ST-App-Key": SERVICETITAN_APP_KEY}
        page = 1
        for _ in range(_MAX_PAGES):
            q = {"page": page, "pageSize": _PAGE_SIZE}
            if params:
                q.update(params)
            try:
                r = requests.get(base, headers=headers, params=q, timeout=30)
                r.raise_for_status()
                body = r.json()
            except Exception as e:
                print(f"[firstback] servicetitan GET {resource} failed (biz {business_id}): {e}",
                      file=sys.stderr, flush=True)
                return
            for row in (body.get("data") or []):
                yield row
            if not body.get("hasMore"):
                return
            page += 1

    # ------------------------------------------------------------------
    # Fetch clients (customers joined to their contacts for phone/email)
    # ------------------------------------------------------------------
    def fetch_clients(self, business_id: int) -> list:
        """Return this tenant's customers as [{name, phones, email}].

        ServiceTitan keeps phone/email on customer *contacts*, not the customer record, so we
        page the contacts endpoint to build customerId -> {phones, email}, then page customers
        for names and join. Returns [] when not connected or on any error."""
        # 1) contacts -> {customerId: {"phones": [...], "email": ""}}
        by_customer = {}
        for c in self._get_pages(business_id, "crm", "customers/contacts"):
            cid = c.get("customerId")
            ctype = (c.get("type") or "").strip().lower()
            value = (c.get("value") or "").strip()
            if not cid or not value:
                continue
            entry = by_customer.setdefault(cid, {"phones": [], "email": ""})
            if ctype in _PHONE_TYPES:
                entry["phones"].append(value)
            elif ctype in _EMAIL_TYPES and not entry["email"]:
                entry["email"] = value

        # 2) customers -> name; join with contacts. Skip anyone with no phone (can't be texted).
        out = []
        for cust in self._get_pages(business_id, "crm", "customers", {"active": "true"}):
            cid = cust.get("id")
            contact = by_customer.get(cid) or {}
            phones = contact.get("phones") or []
            if not phones:
                continue
            out.append({
                "name": (cust.get("name") or "").strip(),
                "phones": phones,
                "email": contact.get("email") or "",
            })
        return out

    # ------------------------------------------------------------------
    # Fetch jobs
    # ------------------------------------------------------------------
    def fetch_jobs(self, business_id: int) -> list:
        """Return recent jobs as [{title, status, client_phone}]. Phone is resolved from the
        customer's first contact. Returns [] on error or when not connected."""
        # Build customerId -> first phone (reuse the contacts endpoint).
        phone_by_customer = {}
        for c in self._get_pages(business_id, "crm", "customers/contacts"):
            cid = c.get("customerId")
            if cid in phone_by_customer:
                continue
            if (c.get("type") or "").strip().lower() in _PHONE_TYPES and (c.get("value") or "").strip():
                phone_by_customer[cid] = c["value"].strip()

        out = []
        for job in self._get_pages(business_id, "jpm", "jobs"):
            title = (job.get("summary") or job.get("name") or "").strip()
            if not title and job.get("jobNumber"):
                title = f"Job #{job['jobNumber']}"
            out.append({
                "title": title,
                "status": (job.get("jobStatus") or "").strip(),
                "client_phone": phone_by_customer.get(job.get("customerId"), ""),
            })
        return out

    # ------------------------------------------------------------------
    # Push booking (additive write — best effort)
    # ------------------------------------------------------------------
    def push_quote_request(self, business_id: int, lead: dict, booking: dict):
        """Push a booked FirstBack estimate into ServiceTitan as a CRM booking (inbound lead).
        Returns the new booking id (str) on success, None on failure. Never raises.

        Booking payload shape is best-effort against the CRM v2 bookings endpoint; if the tenant
        requires a booking-provider id or different fields, this returns None and the booking is
        simply not mirrored (FirstBack's own booking is unaffected). Confirm against a live tenant."""
        token = self._access_token(business_id)
        tenant = self._tenant_id(business_id)
        if not token or not tenant:
            return None
        name = (lead.get("name") or "").strip() or "FirstBack lead"
        phone = (lead.get("phone") or "").strip()
        when = (booking.get("when") or booking.get("day") or "").strip()
        summary = f"FirstBack booked estimate — {name}"
        if when:
            summary += f" — {when}"
        payload = {
            "source": "FirstBack",
            "summary": summary,
            "name": name,
            "isFirstContact": True,
        }
        if phone:
            payload["contacts"] = [{"type": "Phone", "value": phone}]
        url = f"{_api_base()}/crm/v2/tenant/{tenant}/bookings"
        headers = {"Authorization": f"Bearer {token}", "ST-App-Key": SERVICETITAN_APP_KEY}
        try:
            r = requests.post(url, json=payload, headers=headers, timeout=30)
            r.raise_for_status()
            body = r.json() if r.content else {}
            bid = body.get("id")
            return str(bid) if bid is not None else None
        except Exception as e:
            print(f"[firstback] servicetitan push booking failed (biz {business_id}): {e}",
                  file=sys.stderr, flush=True)
            return None


# Module-level singleton (mirrors jobber_fsm / hcp_fsm usage pattern).
_provider = ServiceTitanFSM()


def configured() -> bool:
    return _provider.configured()


def is_connected(business_id: int) -> bool:
    return _provider.is_connected(business_id)


def connect_tenant(business_id: int, tenant_id: str) -> None:
    return _provider.connect_tenant(business_id, tenant_id)


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
    secs = int(tok.get("expires_in", 900))   # ServiceTitan tokens default ~15 min
    return (datetime.now(timezone.utc) + timedelta(seconds=secs)).isoformat()
