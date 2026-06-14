"""RingBack AI voice agent -- a SEPARATE async service (Phase 3).

Flask/WSGI cannot host a long-lived WebSocket, and Twilio ConversationRelay needs
one, so the voice leg runs here as its own ASGI app (FastAPI/uvicorn) alongside
the Flask app. Run it with:

    python voice_service.py            # uvicorn on RINGBACK_VOICE_PORT (default 8810)

It exposes two endpoints Twilio talks to during an outbound AI callback:
  * GET/POST /twiml -> the ConversationRelay TwiML (welcome greeting with the
    required AI + recording disclosure, the wss /ws URL, and the biz/lead ids).
  * WS /ws -> the ConversationRelay loop. Twilio does the speech-to-text and
    text-to-speech; we just turn each caller utterance into text, run it through
    the SAME shared conversation engine the simulator and SMS webhooks use
    (app.handle_inbound), and send the reply text back for Twilio to speak. So a
    voice call books the estimate, alerts the owner, and queues the reminder with
    zero extra logic.

The brain is whatever RINGBACK_PROVIDER selects (Claude for launch, the demo
responder offline) -- identical to the text path. Booking integrity is the DB
UNIQUE slot constraint, shared across both processes (SQLite in WAL mode).

See CALLBACK_SYSTEM_PLAN.md (Phase 3). The voice callback is placed only after the
customer texts "call me" (FCC AI-voice consent gate; see app.twilio_sms_inbound).
"""
import asyncio
import json
import sys

from fastapi import FastAPI, Request, Response, WebSocket, WebSocketDisconnect

import db
import app as flask_app   # reuse the shared conversation engine (handle_inbound)
from config import VOICE_PUBLIC_URL, CONVERSATIONRELAY_VOICE, VOICE_SERVICE_PORT

fastapi_app = FastAPI()


def _xesc(s):
    """Escape a value for safe placement inside a TwiML attribute or text node."""
    return (str(s or "").replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def _isint(s):
    try:
        int(s)
        return True
    except (TypeError, ValueError):
        return False


def _wss_base():
    """Our public wss origin, from VOICE_PUBLIC_URL (https -> wss). Empty if unset
    (the caller then falls back to the request host)."""
    base = (VOICE_PUBLIC_URL or "").rstrip("/")
    if base.startswith("https://"):
        return "wss://" + base[len("https://"):]
    if base.startswith("http://"):
        return "ws://" + base[len("http://"):]
    return base


def build_twiml(biz_id, lead_id, wss_base=None):
    """The ConversationRelay TwiML for an AI voice call. Pure + testable."""
    biz = db.get_business(int(biz_id)) if _isint(biz_id) else None
    name = (biz or {}).get("name") or "our team"
    greeting = (f"Hi, this is the scheduling assistant for {name}. "
                "This call may be recorded. How can I help you book your free estimate?")
    base = (wss_base or _wss_base() or "").rstrip("/")
    ws_url = f"{base}/ws?biz={biz_id}&lead={lead_id}"
    voice_attr = f' voice="{_xesc(CONVERSATIONRELAY_VOICE)}"' if CONVERSATIONRELAY_VOICE else ""
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Response><Connect>'
        f'<ConversationRelay url="{_xesc(ws_url)}"{voice_attr} '
        f'welcomeGreeting="{_xesc(greeting)}">'
        f'<Parameter name="biz" value="{_xesc(biz_id)}"/>'
        f'<Parameter name="lead" value="{_xesc(lead_id)}"/>'
        '</ConversationRelay></Connect></Response>')


@fastapi_app.api_route("/twiml", methods=["GET", "POST"])
async def twiml(request: Request):
    biz_id = request.query_params.get("biz", "")
    lead_id = request.query_params.get("lead", "")
    # If VOICE_PUBLIC_URL isn't set (e.g. local ngrok), derive wss from the host
    # Twilio reached us on. Twilio always uses TLS, so wss:// is correct.
    fallback = None
    if not _wss_base():
        fallback = "wss://" + request.headers.get("host", "")
    return Response(content=build_twiml(biz_id, lead_id, fallback),
                    media_type="text/xml")


def _say(text, last=True):
    """A ConversationRelay 'text' frame (Twilio speaks it via TTS)."""
    return json.dumps({"type": "text", "token": text, "last": last})


@fastapi_app.websocket("/ws")
async def ws(websocket: WebSocket):
    await websocket.accept()
    biz = lead = None
    loop = asyncio.get_event_loop()
    try:
        while True:
            raw = await websocket.receive_text()
            try:
                msg = json.loads(raw)
            except ValueError:
                continue
            mtype = msg.get("type")
            if mtype == "setup":
                params = msg.get("customParameters") or {}
                biz_id = params.get("biz") or websocket.query_params.get("biz")
                lead_id = params.get("lead") or websocket.query_params.get("lead")
                biz = db.get_business(int(biz_id)) if _isint(biz_id) else None
                lead = db.get_lead(int(lead_id)) if _isint(lead_id) else None
            elif mtype == "prompt":
                text = (msg.get("voicePrompt") or "").strip()
                if not text or not biz or not lead:
                    continue
                # handle_inbound is synchronous (DB + LLM); keep it off the event
                # loop so other calls' sockets stay responsive.
                reply, _booked, _urgent = await loop.run_in_executor(
                    None, flask_app.handle_inbound, biz, lead, text)
                await websocket.send_text(_say(reply, last=True))
            elif mtype == "interrupt":
                # The caller barged in. We send whole turns, so there's nothing
                # half-spoken to reconcile; just keep listening.
                continue
            elif mtype == "error":
                print(f"[ringback] voice relay error: {msg.get('description')}",
                      file=sys.stderr, flush=True)
                break
    except WebSocketDisconnect:
        pass
    except Exception as e:  # never let one call crash the worker
        print(f"[ringback] voice ws error: {e}", file=sys.stderr, flush=True)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(fastapi_app, host="0.0.0.0", port=VOICE_SERVICE_PORT)
