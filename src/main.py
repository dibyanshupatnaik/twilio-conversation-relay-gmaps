from __future__ import annotations

import json
import logging

from fastapi import FastAPI, Form, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from twilio.rest import Client

from .dashboard import render_results
from .place_search import search_restaurants
from .session import ConversationSession, SessionStore
from .settings import settings
from .slot_extractor import extract_slots, follow_up_for_missing

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("conversationrelay-minimal")

app = FastAPI(
    title="ConversationRelay Minimal",
    description="Twilio ConversationRelay starter with Google Places integration.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory="static"), name="static")

session_store = SessionStore()
twilio_client = Client(settings.twilio_account_sid, settings.twilio_auth_token)

SEARCH_HISTORY: dict[str, dict[str, object]] = {}


@app.get("/health", tags=["system"])
async def health_check():
    return {
        "status": "ok",
        "ngrok_url": settings.ngrok_url,
        "twilio": bool(settings.twilio_account_sid),
        "google_places": bool(settings.google_places_api_key),
    }


@app.post("/twiml", tags=["twilio"])
async def twiml_endpoint(From: str = Form(None), CallSid: str = Form(None)):
    if CallSid and From:
        session_store.get(CallSid).caller_number = From
    ws_url = f"wss://{settings.ngrok_url}/ws" if settings.ngrok_url else "ws://localhost/ws"
    xml_content = f"""
    <Response>
      <Connect>
        <ConversationRelay url="{ws_url}" welcomeGreeting="{settings.welcome_greeting}" />
      </Connect>
    </Response>
    """.strip()
    return Response(content=xml_content, media_type="application/xml")


@app.post("/api/searches/{search_id}", tags=["dashboard"])
async def get_search(search_id: str):
    data = SEARCH_HISTORY.get(search_id)
    if not data:
        return JSONResponse(
            status_code=404, content={"error": "Search not found or expired."}
        )
    return data


@app.get("/dashboard/{search_id}", response_class=HTMLResponse, tags=["dashboard"])
async def dashboard(search_id: str):
    data = SEARCH_HISTORY.get(search_id)
    if not data:
        return HTMLResponse(
            content=render_results([]),
            status_code=404,
        )
    return HTMLResponse(content=render_results(data["results"]))


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    session: ConversationSession | None = None

    try:
        while True:
            raw_message = await websocket.receive_text()
            event = json.loads(raw_message)
            event_type = event.get("type")

            if event_type == "setup":
                call_sid = event.get("callSid")
                session = session_store.get(call_sid)
                logger.info("📞 Call connected: %s", call_sid)
                session.append("assistant", settings.welcome_greeting)
                await websocket.send_text(
                    json.dumps(
                        {
                            "type": "text",
                            "token": settings.welcome_greeting,
                            "last": False,
                        }
                    )
                )

            elif event_type == "prompt" and session:
                user_text = event.get("voicePrompt", "")
                normalized = user_text.strip().lower()

                logger.info("🎤 User: %s", user_text)
                session.append("user", user_text)
                session.update_slots(extract_slots(user_text, session.slots))

                if not session.ready_for_search:
                    follow_up = follow_up_for_missing(session.missing_slots)
                    session.append("assistant", follow_up)
                    await websocket.send_text(
                        json.dumps({"type": "text", "token": follow_up, "last": True})
                    )
                    continue

                if session.should_skip_search(normalized):
                    follow_up = (
                        "I've already shared those recommendations. Would you like me to run a new search?"
                    )
                    await websocket.send_text(
                        json.dumps({"type": "text", "token": follow_up, "last": True})
                    )
                    continue

                result = search_restaurants(session.slots)
                if not result["success"]:
                    session.append("assistant", result["message"])
                    await websocket.send_text(
                        json.dumps(
                            {"type": "text", "token": result["message"], "last": True}
                        )
                    )
                    continue

                session.mark_search(normalized)

                search_id = result["search_id"]
                SEARCH_HISTORY[search_id] = {
                    "slots": session.slots.copy(),
                    "results": result["results"],
                }

                dashboard_url = (
                    f"https://{settings.ngrok_url}/dashboard/{search_id}"
                    if settings.ngrok_url
                    else f"http://localhost:{settings.port}/dashboard/{search_id}"
                )

                voice_response = result["voice_response"]
                session.append("assistant", voice_response)
                await websocket.send_text(
                    json.dumps({"type": "text", "token": voice_response, "last": True})
                )

                await maybe_send_rcs(session, dashboard_url)

            elif event_type == "interrupt":
                logger.info("⏸️ User interrupted")
                continue

    except WebSocketDisconnect:
        if session:
            logger.info("🔚 Call ended: %s", session.call_sid)
            session_store.clear(session.call_sid)
    except Exception as exc:  # pragma: no cover
        logger.exception("WebSocket error: %s", exc)
        await websocket.close(code=1011)


async def maybe_send_rcs(session: ConversationSession, dashboard_url: str) -> None:
    if session.rcs_sent:
        return
    try:
        to_number = session.caller_number or fetch_caller_number(session.call_sid)
        if not to_number:
            return
        twilio_client.messages.create(
            to=to_number,
            messaging_service_sid=settings.twilio_messaging_sid,
            body=f"Here are the restaurants I found for you: {dashboard_url}",
        )
        session.rcs_sent = True
    except Exception as exc:  # pragma: no cover
        logger.error("Failed to send RCS: %s", exc)


def fetch_caller_number(call_sid: str) -> str | None:
    try:
        call = twilio_client.calls(call_sid).fetch()
        number = getattr(call, "from_", None)
        if number:
            session_store.get(call_sid).caller_number = number
        return number
    except Exception as exc:  # pragma: no cover
        logger.error("Could not fetch caller number: %s", exc)
        return None


def main():
    import uvicorn

    uvicorn.run("src.main:app", host="0.0.0.0", port=settings.port, reload=False)


if __name__ == "__main__":
    main()
