from __future__ import annotations

import json
import logging

from fastapi import FastAPI, Form, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from .clients import openai_client, twilio_client
from .dashboard import render_results
from .place_search import search_restaurants
from .session import ConversationSession, SessionStore
from .settings import settings
from .slot_extractor import extract_slots, follow_up_for_missing

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("conversationrelay-minimal")

SYSTEM_PROMPT = """
You are a friendly restaurant assistant on a phone call. Collect these details:
- cuisine
- location (cross streets or neighborhood)
- budget (rough price level)
- travel preference (walking or transit) AND minutes
Guidelines:
- Ask only for the fields that are still missing.
- Keep responses short and conversational.
- When all fields are collected and a new search is needed, confirm you'll look up options.
- Never render lists or bullets.
- If the caller repeats a fulfilled request, offer to search again.
"""

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

SEARCH_HISTORY: dict[str, dict[str, object]] = {}


def build_conversation(
    session: ConversationSession,
    missing_slots: list[str],
    ready_for_search: bool,
    duplicate_request: bool,
) -> list[dict[str, str]]:
    conversation: list[dict[str, str]] = [{"role": "system", "content": SYSTEM_PROMPT}]
    for role, content in session.history:
        conversation.append({"role": role, "content": content})

    status_payload = {
        "known_slots": session.slots,
        "missing_slots": missing_slots,
        "ready_for_search": ready_for_search,
        "duplicate_request": duplicate_request,
    }

    conversation.append(
        {
            "role": "system",
            "content": (
                "Conversation status: "
                + json.dumps(status_payload)
                + ". If missing_slots is not empty, ask for one of them naturally. "
                "If ready_for_search is true and duplicate_request is false, acknowledge you'll search now. "
                "If duplicate_request is true, remind the caller you've already shared results and offer to search again."
            ),
        }
    )

    return conversation

# -- TODO 2: Streaming response handler -------------------------------
async def ai_response_stream(
    conversation: list[dict[str, str]],
    websocket: WebSocket,
) -> str:
    full_response = ""
    stream = openai_client.chat.completions.create(
        model="gpt-4o-mini",
        messages=conversation,
        stream=True,
        temperature=0.5,
    )

    for chunk in stream:
        token = chunk.choices[0].delta.content or ""
        if token:
            full_response += token
            await websocket.send_text(
                json.dumps({"type": "text", "token": token, "last": False})
            )

    await websocket.send_text(json.dumps({"type": "text", "token": "", "last": True}))
    return full_response


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
    # -- TODO 1: TwiML handler and ws URL assembly -------------------------------



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

                # Build conversation context using current slots
                missing_before = session.missing_slots
                ready_before = session.ready_for_search
                duplicate_before = ready_before and session.should_skip_search(normalized)

                conversation = build_conversation(
                    session, missing_before, ready_before, duplicate_before
                )

                try:
                    assistant_text = await ai_response_stream(conversation, websocket)
                    assistant_text = assistant_text.strip()
                except Exception as exc:  # pragma: no cover
                    logger.error("OpenAI streaming failed: %s", exc)
                    assistant_text = (
                        follow_up_for_missing(missing_before)
                        if missing_before
                        else "Got it. Let me check the latest options for you."
                    )
                    await websocket.send_text(
                        json.dumps({"type": "text", "token": assistant_text, "last": True})
                    )

                if assistant_text:
                    session.append("assistant", assistant_text)

                # Update slots after the response has started streaming
                session.update_slots(extract_slots(user_text, session.slots))
                missing_slots = session.missing_slots
                ready_for_search = session.ready_for_search
                duplicate_request = ready_for_search and session.should_skip_search(normalized)

                if not ready_for_search or duplicate_request:
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
        # -- TODO 6: Sending RCS text -------------------------------
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
