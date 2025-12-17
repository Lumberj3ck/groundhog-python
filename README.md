Groundhog (Python)
===================

This is a Python-first rewrite of the Groundhog assistant. It keeps the same goals—a small AI day-planning agent that can read your notes, talk to Google Calendar, and respond over websockets—but is implemented with FastAPI, LangChain, the OpenAI Python SDK, and Google’s official client libraries.

## Features
- Chatting agent powered by LangChain’s tool-calling agent with OpenAI-compatible models (supports Groq or OpenAI via `OPENAI_BASE_URL`/`OPENAI_API_KEY`).
- Tool calling for:
  - calculator (quick math)
  - notes reader (pulls the most recent dated notes)
  - Google Calendar list / add / edit
- FastAPI server with websocket endpoint `/ws` and lightweight auth options:
  - simple password flow via `MASTER_PASSWORD`
  - optional OAuth login when Google web client credentials are provided
- Patterns endpoint `/patterns` for the UI to pre-seed prompts.

## Getting started
1. Create and activate a virtualenv.
2. Install deps:
   ```
   pip install -r requirements.txt
   ```
3. Copy `env.sample` to `.env` (or export env vars) and fill in values (at minimum `OPENAI_API_KEY` and `NOTES_DIR`).
4. Run the server:
   ```
   uvicorn groundhog.main:app --port 8080 --reload
   ```
5. Connect a client to `ws://localhost:8080/ws` sending JSON `{"message": "...", "pattern": "Plan Day"}`.

## Environment
- `OPENAI_API_KEY` (required)
- `OPENAI_BASE_URL` (optional; set to Groq or other compatible host)
- `OPENAI_MODEL` (default `gpt-4o-mini`)
- `NOTES_DIR` (required; directory with files named YYYY-MM-DD.*)
- Calendar auth (choose one):
  - Service account: `GOOGLE_CREDENTIALS_FILE`
  - OAuth web app: `GOOGLE_CLIENT_ID`, `GOOGLE_SECRET`, `GOOGLE_REDIRECT_URL`
- `JWT_SECRET` (required if using auth cookies)
- `MASTER_PASSWORD` (optional simple login)

## Project layout
- `groundhog/agent.py` – LangChain agent/executor wiring.
- `groundhog/tools.py` – calculator, notes, and calendar tool implementations.
- `groundhog/calendar.py` – calendar client wrapper and OAuth helper.
- `groundhog/server.py` – FastAPI app, routes, websockets, auth.
- `groundhog/patterns.py` – predefined prompt patterns.
- `groundhog/notes.py` – helpers to read recent notes.

## Testing
Light smoke test for notes and tool schemas is provided under `tests/`. Run with:
```
pytest
```


