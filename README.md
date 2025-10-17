# ConversationRelay Minimal Starter

This starter lifts only the essential pieces from the full ConversationRelay project so you can get a voice-powered restaurant assistant running quickly. It includes a FastAPI backend, a ConversationRelay WebSocket handler, LLM-powered slot extraction, Google Places lookups with travel-time filtering, and a lightweight dashboard for sharing results via RCS.

## 1. Prerequisites

- Python 3.11+
- [uv](https://github.com/astral-sh/uv) or `pip` for dependency management
- Twilio account with the ConversationRelay beta enabled
- Google Cloud project with Places API (New), Geocoding API, Distance Matrix API, and Directions API enabled
- ngrok (or another public tunnel) for exposing the local server
- OpenAI API key with access to GPT-4o-mini (or compatible) for streaming responses
- MongoDB is **not** required; results are kept in memory for simplicity

## 2. Setup

```bash
git clone https://github.com/your-org/conversationrelay-minimal.git
cd conversationrelay-minimal
cp .env.example .env      # fill in Twilio + Google credentials
uv sync                   # or: pip install -r requirements.txt (generated via uv pip compile)
```

Populate `.env` with the following keys:

```env
PORT=8080
NGROK_URL=your-subdomain.ngrok-free.app   # no protocol
OPENAI_API_KEY=sk-...
GOOGLE_PLACES_API_KEY=AIza...
TWILIO_ACCOUNT_SID=AC...
TWILIO_AUTH_TOKEN=...
TWILIO_MESSAGING_SID=MG...
```

## 3. Run Locally

```bash
uv run uvicorn src.main:app --reload --port ${PORT:-8080}
ngrok http 8080   # in another terminal
```

Configure your Twilio phone number’s Voice webhook to `https://<NGROK_URL>/twiml` and attach the ConversationRelay key in the Twilio Console. Place a call to verify you hear the streaming greeting (the Twilio-side welcomeGreeting is disabled so the app controls the first prompt).

## 4. Whats Included

- `src/main.py` – FastAPI app with `/twiml`, `/ws`, `/dashboard/{id}`, `/health`, and `/api/searches/{id}` endpoints, plus `ai_response_stream` for OpenAI-powered prompts.
- `src/session.py` – Holds per-call slot data, last search signature, and caller metadata.
- `src/slot_extractor.py` – LLM-powered slot extraction that converts spoken phrases (e.g., "ten minutes") into structured fields for downstream APIs.
- `src/place_search.py` – Google Places and Geocoding helpers plus simple ranking and voice formatting.
- `src/dashboard.py` – Renders HTML for the shared dashboard view.
- `static/dashboard.css` – Minimal styling for the dashboard page.

## 5. Call Flow Overview

1. `/twiml` instructs Twilio to open a ConversationRelay WebSocket at `/ws`. The server sends the first spoken greeting over that socket.
2. Each caller utterance is parsed by `slot_extractor` (OpenAI JSON mode) while `ai_response_stream` gathers missing details conversationally.
3. Once cuisine, location, budget, travel mode, and travel time are set, a search request hits the Google Places API (New). Requests are logged, and Distance Matrix results that exceed the caller’s time limit are discarded.
4. Remaining results are stored in memory and summarized; the caller hears the top options, and an SMS/RCS (via Twilio Messaging Service) is sent with a dashboard link.
5. The dashboard (served from `/dashboard/{search_id}`) shows the results for later reference.

## 6. Customising

- Adjust the slot prompts or add new fields in `src/session.py` and `src/slot_extractor.py`.
- Replace the in-memory store in `src/main.py` with your preferred database if you need persistence.
- Extend `src/place_search.py` with richer ranking, review analysis, or support for dietary preferences.
- Tailor the dashboard markup in `src/dashboard.py` (and styles in `static/dashboard.css`) to show maps, photos, or transit directions.

## 7. Troubleshooting

- **No voice response** – confirm the WebSocket URL in TwiML matches your ngrok domain (no duplicate protocol). Check server logs for incoming `setup` and `prompt` events.
- **Slots not updating** – ensure the OpenAI key is valid; failures fall back to deterministic prompts and will be logged.
- **No restaurants returned** – ensure Google APIs are enabled, billing is active, and the Places New API quota is available. Look for `❌` markers in the server log.
- **Results ignore travel time** – watch for the “Google Places request body” log to confirm `travel_minutes` made it through, and verify Distance Matrix responses aren’t being filtered out for exceeding the limit.
- **RCS text missing** – verify `TWILIO_MESSAGING_SID` is set and the Messaging Service has RCS fallback enabled.
- **Repeated recommendations** – the session store suppresses reruns unless the caller asks for “more options”; tweak `FORCE_NEW_SEARCH_PHRASES` in `src/session.py` as needed.

Happy hacking!
