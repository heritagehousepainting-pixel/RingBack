"""TO-1: a once-a-day plain-text ops snapshot to the owner's phone.

Adapted from the podcast's "scheduled morning brief" idea to a solo founder running both PM and
ops pre-revenue: the value is preventing context loss during the weeks before contractor #1.

Gated: a no-op unless FIRSTBACK_OPS_SMS (the owner's mobile) is set. Deduped to once per local
day via the meta table, so the frequent /tasks/run-due tick only sends it once. Defensive: every
metric is independently guarded and the whole thing never raises into the cron tick.
"""
import sys
from collections import Counter
from datetime import datetime, timezone

import db
import messaging
from config import CLAUDE_DAILY_COST_CAP_USD, OPS_BRIEF_SMS, app_tz

_META_KEY = "ops_brief_last_date"


def daily_ops_brief():
    """Send the owner a 1-SMS ops snapshot, at most once per local day. Returns True if sent."""
    to = (OPS_BRIEF_SMS or "").strip()
    if not to:
        return False
    today = datetime.now(app_tz()).strftime("%Y-%m-%d")
    try:
        if db.get_meta(_META_KEY) == today:
            return False
    except Exception:
        pass

    lines = [f"FirstBack ops · {today}"]

    # Contractors by activation state + stuck A2P.
    try:
        bizes = db.list_businesses()
        states = Counter((b.get("activation_state") or "setup") for b in bizes)
        lines.append("Contractors: " + (", ".join(f"{k} {v}" for k, v in sorted(states.items())) or "none"))
        now = datetime.now(timezone.utc)
        stuck = 0
        for b in bizes:
            if b.get("a2p_status") == "pending" and b.get("a2p_submitted_at"):
                try:
                    sub = datetime.fromisoformat(b["a2p_submitted_at"])
                    if sub.tzinfo is None:
                        sub = sub.replace(tzinfo=timezone.utc)
                    if (now - sub).days > 20:
                        stuck += 1
                except (ValueError, TypeError):
                    pass
        if stuck:
            lines.append(f"A2P stuck >20d: {stuck}")
    except Exception as e:
        lines.append(f"(contractor stats unavailable: {e})")

    # LLM spend today vs the daily cap (biz 1 as the proxy in single-tenant).
    try:
        spend = db.get_llm_spend_today(1)
        lines.append(f"LLM spend today: ${spend:.2f} / ${CLAUDE_DAILY_COST_CAP_USD:.2f} cap")
    except Exception:
        pass

    # Growth plays sitting held (awaiting owner action).
    try:
        conn = db.get_conn()
        held = conn.execute("SELECT COUNT(*) FROM scheduled_messages WHERE status='held'").fetchone()[0]
        conn.close()
        if held:
            lines.append(f"Growth plays held: {held}")
    except Exception:
        pass

    body = "\n".join(lines)
    try:
        biz1 = db.get_business(1)
        messaging.send_sms(biz1, to, body, gate=False)   # owner alert path (P2P, no A2P)
        db.set_meta(_META_KEY, today)
        return True
    except Exception as e:
        print(f"[firstback] ops brief send failed: {e}", file=sys.stderr, flush=True)
        return False
