"""Provider interface for telephony (SMS + voice + number provisioning).

A thin abstract base so a second carrier (e.g. Telnyx) can plug in later WITHOUT touching
the conversation engine, routes, or db. Twilio is the v1 implementation
(providers/twilio_provider.py), which simply delegates to the existing messaging.py -- so
introducing this seam changes NO behavior and breaks NO call site. providers/registry.py
selects the active provider.

Mirrors the shape of fsm_provider.py:
  * Gated: ``configured()`` is False when the operator hasn't set the carrier's credentials;
    every send/call path is then a safe simulated no-op.
  * Defensive: implementors never raise into a caller -- they swallow + log every network
    error and return a status dict.
  * Scoped: every send is per-business, so a tenant's own number/identity is used.

Status-dict contract (shared so call sites don't care who the carrier is):
  send_sms()     -> {"status": "sent"|"simulated"|"blocked"|"suppressed"|"skipped"|
                                "click_to_send"|"deferred"|"error", ...}
  place_call()   -> {"status": "placed"|"simulated"|"error"|..., "sid"?: str}
"""


class SMSProvider:
    """Abstract telephony provider. Implementors: TwilioProvider, TelnyxProvider (stub)."""

    PROVIDER_KEY = ""   # e.g. "twilio" | "telnyx"

    def configured(self) -> bool:
        """True if this app has API credentials set for this carrier."""
        raise NotImplementedError

    def send_sms(self, business, to, body, lead_id=None, status_callback=None,
                 gate=True, transactional=True) -> dict:
        """Send (or simulate) an SMS for a business. Returns the shared status dict."""
        raise NotImplementedError

    def place_call(self, business, to, twiml_url, status_callback=None, add_amd=False) -> dict:
        """Place (or simulate) an outbound voice call that hands off to `twiml_url`."""
        raise NotImplementedError

    def provision_number(self, business_id, phone=None, area_code=None, base_url=None,
                         allow_no_webhooks=False) -> dict:
        """Buy + wire a number for a business. Returns the carrier's result dict."""
        raise NotImplementedError

    def valid_signature(self, url, params, signature, auth_token=None) -> bool:
        """Verify an inbound webhook's authenticity. Fail-closed when unconfigured."""
        raise NotImplementedError
