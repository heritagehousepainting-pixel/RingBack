"""providers/ seam + channel_state.py regression tests.

  registry       get_sms_provider resolves twilio by default, telnyx when selected, unknown->twilio.
  delegation     TwilioProvider.configured() tracks messaging.configured() (it's a thin delegator).
  telnyx stub    selecting telnyx (unbuilt) safely simulates a send + fails webhook auth closed.
  channel_state  setup -> voice_live -> +click_to_send -> live_sms picture is honest at each step.
  best_outbound  prefers automatic sms, then click-to-send, then email, then None.

Pure/gated: no network -- the unbuilt providers simulate and channel probes read flags only.
"""
import os
import sys
import tempfile

os.environ["FIRSTBACK_PROVIDER"] = "demo"
os.environ.pop("SMS_PROVIDER", None)
import config
_TMP = tempfile.NamedTemporaryFile(suffix=".db", delete=False); _TMP.close()
config.DB_PATH = _TMP.name
import db
db.DB_PATH = _TMP.name
db.init_db()
import messaging
import providers
import channel_state

_pass = _fail = 0
def check(name, cond):
    global _pass, _fail
    if cond:
        _pass += 1; print(f"  ok   {name}")
    else:
        _fail += 1; print(f"FAIL   {name}")


# ---- registry resolution ----------------------------------------------------
check("default provider is twilio", providers.get_sms_provider({"id": 1}).PROVIDER_KEY == "twilio")
check("twilio delegates configured() to messaging",
      providers.get_sms_provider({"id": 1}).configured() == messaging.configured())
check("unknown per-biz override falls back to twilio",
      providers.get_sms_provider({"id": 1, "sms_provider": "bogus"}).PROVIDER_KEY == "twilio")
check("per-biz override selects telnyx",
      providers.get_sms_provider({"id": 1, "sms_provider": "telnyx"}).PROVIDER_KEY == "telnyx")
check("available_providers lists both", providers.available_providers() == ["telnyx", "twilio"])

# ---- telnyx stub is safe ----------------------------------------------------
_tel = providers.get_sms_provider({"id": 1, "sms_provider": "telnyx"})
check("telnyx send simulates (never silently drops)",
      _tel.send_sms({"id": 1}, "+15551112222", "hi").get("status") == "simulated")
check("telnyx webhook auth fails closed", _tel.valid_signature("u", {}, "sig") is False)

# ---- channel_state lifecycle ------------------------------------------------
_cs = channel_state.channel_state({"id": 1, "activation_state": "setup"})
check("setup: nothing live", _cs["day0_live"] is False and _cs["active_channels"] == [])
check("setup: best_outbound None", _cs["best_outbound"] is None)

_voice = {"id": 1, "activation_state": "voice_live",
          "twilio_number": "+15551110000", "forwarding_confirmed": 1}
_cs = channel_state.channel_state(_voice)
check("voice_live: day0_live true via voice", _cs["voice"] and _cs["day0_live"])
check("voice_live: voice in active channels", "voice" in _cs["active_channels"])

_cts = dict(_voice, click_to_send_optin=1)
_cs = channel_state.channel_state(_cts)
check("click-to-send: appears as a channel", "click_to_send" in _cs["active_channels"])
check("click-to-send: is the best outbound during the wait", _cs["best_outbound"] == "click_to_send")

# ---- sms_auto (10DLC approved) wins ----------------------------------------
# Stub compliance.a2p_ready True to simulate an approved campaign.
import compliance
_orig = compliance.a2p_ready
compliance.a2p_ready = lambda b: True
try:
    _cs = channel_state.channel_state(_cts)
    check("live_sms: automatic sms beats click-to-send", _cs["best_outbound"] == "sms")
    check("live_sms: click_to_send drops once sms is automatic", _cs["click_to_send"] is False)
finally:
    compliance.a2p_ready = _orig

print(f"\n{'='*46}")
print(f"Results: {_pass} passed, {_fail} failed")
try:
    os.unlink(_TMP.name)
except OSError:
    pass
sys.exit(1 if _fail else 0)
