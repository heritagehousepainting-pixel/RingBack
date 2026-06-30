"""Twilio implementation of the SMSProvider seam.

DELIBERATELY a thin delegator: every method forwards to the existing, battle-tested
functions in messaging.py. The point of this class is NOT to re-implement Twilio -- it's to
give the rest of the app a provider-shaped handle so a future Telnyx migration is a registry
swap, not a rewrite. Because it delegates, introducing it changes no behavior and the whole
existing test suite stays green.
"""
import messaging
from providers.base import SMSProvider


class TwilioProvider(SMSProvider):
    PROVIDER_KEY = "twilio"

    def configured(self) -> bool:
        return messaging.configured()

    def send_sms(self, business, to, body, lead_id=None, status_callback=None,
                 gate=True, transactional=True) -> dict:
        return messaging.send_sms(business, to, body, lead_id=lead_id,
                                  status_callback=status_callback, gate=gate,
                                  transactional=transactional)

    def place_call(self, business, to, twiml_url, status_callback=None, add_amd=False) -> dict:
        return messaging.place_call(business, to, twiml_url,
                                    status_callback=status_callback, add_amd=add_amd)

    def provision_number(self, business_id, phone=None, area_code=None, base_url=None,
                         allow_no_webhooks=False) -> dict:
        return messaging.provision_number(business_id, phone=phone, area_code=area_code,
                                          base_url=base_url, allow_no_webhooks=allow_no_webhooks)

    def valid_signature(self, url, params, signature, auth_token=None) -> bool:
        return messaging.valid_signature(url, params, signature, auth_token=auth_token)
