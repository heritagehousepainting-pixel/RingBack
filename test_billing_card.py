"""Settings 'Plan & billing' card render tests. Run: python3 test_billing_card.py

Proves the in-app upgrade/manage-plan entry point renders correctly in each state:
  * billing configured + PS-3 gate closed   -> shows the gate reason, no checkout buttons
  * gate open (voice_live + first call)      -> shows in-app plan/checkout buttons
  * existing subscriber (stripe_customer_id) -> shows 'Manage billing' (portal)
Throwaway temp DB + demo brain; no network. Stripe env is faked so billing.configured().
"""
import os
import tempfile

os.environ["FIRSTBACK_PROVIDER"] = "demo"
# Fake Stripe config BEFORE importing app/billing so billing.configured() is True.
os.environ["STRIPE_SECRET_KEY"] = "sk_test_fake"
os.environ["STRIPE_PRICE_STARTER"] = "price_starter_test"
os.environ["STRIPE_PRICE_PRO"] = "price_pro_test"
os.environ["STRIPE_PRICE_CREW"] = "price_crew_test"

import config
_TMP = tempfile.NamedTemporaryFile(suffix=".db", delete=False); _TMP.close()
config.DB_PATH = _TMP.name
import db
db.DB_PATH = _TMP.name
import app

client = app.app.test_client()
_pass = _fail = 0


def check(name, cond, detail=""):
    global _pass, _fail
    if cond:
        _pass += 1
        print(f"  ok   {name}")
    else:
        _fail += 1
        print(f"FAIL   {name}" + (f" ({detail})" if detail else ""))


db.init_db()
client.post("/login", data={"email": config.SEED_OWNER_EMAIL,
                            "password": config.SEED_OWNER_PASSWORD})
with client.session_transaction() as _s:
    _s["csrf_token"] = "test_csrf"
client.environ_base["HTTP_X_CSRF_TOKEN"] = "test_csrf"

BIZ = 1

# ── State 1: billing live, PS-3 gate CLOSED (fresh business in 'setup') ─────────
print("\n=== gate closed -> explains, no checkout buttons ===")
r = client.get("/settings")
html = r.data.decode()
check("settings renders the Plan & billing card",
      r.status_code == 200 and "Plan &amp; billing" in html)
check("gate-closed: no Starter checkout button shown",
      "Starter — $99/mo" not in html)
check("gate-closed: shows a gate reason (forwarding/first call)",
      "forwarding" in html.lower() or "first call" in html.lower())

# ── State 2: gate OPEN (voice_live + a real call answered) ──────────────────────
print("\n=== gate open -> in-app plan/checkout buttons ===")
db.set_activation_state(BIZ, "voice_live")
db.mark_first_call_nudge_sent(BIZ)
html = client.get("/settings").data.decode()
check("gate-open: Starter checkout button appears", "Starter — $99/mo" in html)
check("gate-open: Pro + Crew buttons appear",
      "Pro — $199/mo" in html and "Crew — $399/mo" in html)
check("gate-open: checkout buttons target /billing/checkout",
      'formaction="/billing/checkout"' in html)

# ── State 3: existing subscriber -> Manage billing (portal) ─────────────────────
print("\n=== subscriber -> Manage billing (portal) ===")
db.update_billing(BIZ, stripe_customer_id="cus_test", subscription_status="active", plan="pro")
html = client.get("/settings").data.decode()
check("subscriber: 'Manage billing' button shown", "Manage billing" in html)
check("subscriber: portal form action present", 'action="/billing/portal"' in html)
check("subscriber: no checkout plan buttons (managed via portal)",
      "Starter — $99/mo" not in html)

print(f"\n{_pass} passed, {_fail} failed")
import sys
sys.exit(1 if _fail else 0)
