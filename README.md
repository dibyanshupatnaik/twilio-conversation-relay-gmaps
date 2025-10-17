# ConversationRelay Minimal Starter

This starter lifts only the essential pieces from the full ConversationRelay project so you can get a voice-powered restaurant assistant running quickly. It includes a FastAPI backend, a ConversationRelay WebSocket handler, rudimentary slot extraction, Google Places lookups, and a lightweight dashboard for sharing results via RCS.

## 1. Prerequisites

- Python 3.11+
- [uv](https://github.com/astral-sh/uv) or `pip` for dependency management
- Twilio account with the ConversationRelay beta enabled
- Google Cloud project with Places API (New), Geocoding API, Distance Matrix API, and Directions API enabled
- ngrok (or another public tunnel) for exposing the local server
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

Configure your Twilio phone number’s Voice webhook to `https://<NGROK_URL>/twiml` and attach the ConversationRelay key in the Twilio Console. Place a call to verify you hear the greeting.

## 4. Whats Included

- `src/main.py` – FastAPI app with `/twiml`, `/ws`, `/dashboard/{id}`, `/health`, and `/api/searches/{id}` endpoints.
- `src/session.py` – Holds per-call slot data, last search signature, and caller metadata.
- `src/slot_extractor.py` – Deterministic heuristics to capture cuisine, location, budget, travel mode, and timing from user speech.
- `src/place_search.py` – Google Places and Geocoding helpers plus simple ranking and voice formatting.
- `src/dashboard.py` – Renders HTML for the shared dashboard view.
- `static/dashboard.css` – Minimal styling for the dashboard page.

## 5. Call Flow Overview

1. `/twiml` instructs Twilio to open a ConversationRelay WebSocket at `/ws` with a friendly greeting.
2. The WebSocket collects user input via the `slot_extractor`, prompting for missing fields.
3. Once cuisine, location, budget, travel mode, and travel time are set, a search request hits the Google Places API (New).
4. Results are stored in memory and summarized; the caller hears the top options, and an SMS/RCS is sent with a dashboard link.
5. The dashboard (served from `/dashboard/{search_id}`) shows the results for later reference.

## 6. Customising

- Adjust the slot prompts or add new fields in `src/session.py` and `src/slot_extractor.py`.
- Replace the in-memory store in `src/main.py` with your preferred database if you need persistence.
- Extend `src/place_search.py` with richer ranking, review analysis, or support for dietary preferences.
- Tailor the dashboard at `static/dashboard.html` to show maps, photos, or transit directions.

## 7. Troubleshooting

- **No voice response** – confirm the WebSocket URL in TwiML matches your ngrok domain (no duplicate protocol). Check server logs for incoming `setup` and `prompt` events.
- **No restaurants returned** – ensure Google APIs are enabled, billing is active, and the Places New API quota is available. Look for `❌` markers in the server log.
- **RCS text missing** – verify `TWILIO_MESSAGING_SID` is set and the Messaging Service has RCS fallback enabled.
- **Repeated recommendations** – the session store suppresses reruns unless the caller asks for “more options”; tweak `FORCE_NEW_SEARCH_PHRASES` in `src/session.py` as needed.

Happy hacking!
