"""Telnyx implementation of the SMSProvider seam -- STUB.

Per ONBOARDING_BLUEPRINT.md, Telnyx is a future COST optimization (~$365/mo saved at ~50
contractors), NOT a launch dependency: the A2P bottleneck is TCR's vetting queue, not the
CPaaS, so switching carriers does not speed approval. This stub exists so the migration is a
registry swap + filling these methods in, never an architectural change.

NOT wired into the registry's default path. configured() stays False unless TELNYX_API_KEY is
set, so even if selected it safely simulates. Two real differences to implement when this goes
live (do NOT copy Twilio's helpers blindly):
  * Auth is a Bearer API key, not Basic account-SID/token.
  * Webhook auth is Ed25519 signature verification, NOT Twilio's HMAC -- valid_signature MUST
    be reimplemented (a Twilio-style check would fail-open or fail-closed incorrectly).
"""
import os

from providers.base import SMSProvider

TELNYX_API_KEY = os.environ.get("TELNYX_API_KEY", "")


class TelnyxProvider(SMSProvider):
    PROVIDER_KEY = "telnyx"

    def configured(self) -> bool:
        return bool(TELNYX_API_KEY)

    def send_sms(self, business, to, body, lead_id=None, status_callback=None,
                 gate=True, transactional=True) -> dict:
        # Not implemented yet: behave like the gated simulator so selecting Telnyx before it's
        # built never silently drops a message or pretends one went out.
        return {"status": "simulated", "reason": "telnyx_not_implemented"}

    def place_call(self, business, to, twiml_url, status_callback=None, add_amd=False) -> dict:
        return {"status": "simulated", "reason": "telnyx_not_implemented"}

    def provision_number(self, business_id, phone=None, area_code=None, base_url=None,
                         allow_no_webhooks=False) -> dict:
        return {"status": "error", "error": "telnyx_not_implemented"}

    def valid_signature(self, url, params, signature, auth_token=None) -> bool:
        # Ed25519, not HMAC. Until implemented, fail CLOSED (reject) so no unverified webhook
        # is ever trusted under the Telnyx key.
        return False
