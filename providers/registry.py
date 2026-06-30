"""Provider selection. One place that decides which carrier a send goes through.

Resolution order for get_sms_provider(business):
  1. a business-level override (businesses.sms_provider column, if ever set) -- lets a single
     tenant pilot Telnyx without moving everyone.
  2. the app-wide default env var SMS_PROVIDER (default "twilio").
  3. fall back to Twilio.

Today this always returns TwilioProvider (the only real implementation), so behavior is
unchanged. When Telnyx is built + TELNYX_API_KEY is set, flip SMS_PROVIDER=telnyx (or set the
per-business column) and nothing else changes.
"""
import os

from providers.twilio_provider import TwilioProvider
from providers.telnyx_provider import TelnyxProvider

_REGISTRY = {
    "twilio": TwilioProvider,
    "telnyx": TelnyxProvider,
}

# Cache instances (they're stateless handles) so callers can compare identity cheaply.
_INSTANCES = {}


def _instance(key):
    key = (key or "").strip().lower()
    cls = _REGISTRY.get(key, TwilioProvider)
    if cls not in _INSTANCES.values():
        _INSTANCES[key] = cls()
    return _INSTANCES.setdefault(key, cls())


def get_sms_provider(business=None):
    """The active SMSProvider for this business (or the app default). Never raises;
    unknown keys fall back to Twilio."""
    if isinstance(business, dict):
        override = (business.get("sms_provider") or "").strip().lower()
        if override in _REGISTRY:
            return _instance(override)
    return _instance(os.environ.get("SMS_PROVIDER", "twilio"))


def available_providers():
    """The provider keys this build knows about (for diagnostics / admin UI)."""
    return sorted(_REGISTRY.keys())
