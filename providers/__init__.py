"""Telephony provider seam. Import the factory from here:

    from providers import get_sms_provider
    prov = get_sms_provider(business)
    prov.send_sms(business, to, body)

Today this resolves to Twilio (delegating to messaging.py), so it's a no-op refactor; it
exists so a future Telnyx migration is a registry swap, not a rewrite.
"""
from providers.registry import get_sms_provider, available_providers

__all__ = ["get_sms_provider", "available_providers"]
