from __future__ import annotations

import os
import secrets
from typing import Any, Dict, Optional

import httpx
import jwt
from dotenv import load_dotenv
from fastapi import (
    Depends,
    FastAPI,
    HTTPException,
    Request,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from oauthlib.oauth2 import WebApplicationClient

from .agent import build_executor, run_agent
from langchain.memory import ConversationBufferMemory
from .calendar import (
    CalendarClient,
    SCOPES,
    credentials_from_service_account,
    credentials_from_oauth,
)
from .config import Settings, get_settings
from .patterns import PATTERNS, list_patterns
from .tools import (
    CalendarAddTool,
    CalendarEditTool,
    CalendarListTool,
    CalculatorTool,
    NotesTool,
)

load_dotenv()

app = FastAPI(title="Groundhog (Python)")


def decode_auth_cookie(
    request: Request, settings: Settings
) -> Optional[Dict[str, Any]]:
    token = request.cookies.get("Auth")
    if not token:
        return None
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
    except jwt.PyJWTError:
        return None


def encode_auth_cookie(payload: Dict[str, Any], settings: Settings) -> str:
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def calendar_client_from_request(
    request: Request, settings: Settings
) -> Optional[CalendarClient]:
    # OAuth token from cookie takes precedence
    cookie_payload = decode_auth_cookie(request, settings) or {}
    token_info = cookie_payload.get("token")
    if token_info:
        try:
            creds = credentials_from_oauth(token_info)
            return CalendarClient(creds)
        except Exception:
            pass

    # Service account fallback
    if settings.google_credentials_file and os.path.exists(
        settings.google_credentials_file
    ):
        creds = credentials_from_service_account(settings.google_credentials_file)
        return CalendarClient(creds)
    return None


def oauth_client(settings: Settings) -> WebApplicationClient:
    return WebApplicationClient(settings.google_client_id)


def build_tools(request: Request, settings: Settings) -> list:
    calendar_client = calendar_client_from_request(request, settings)

    def client_factory() -> Optional[CalendarClient]:
        return calendar_client

    tools = [
        CalculatorTool(),
        NotesTool(notes_dir=settings.notes_dir, default_limit=5),
    ]
    if calendar_client:
        tools.extend(
            [
                CalendarListTool(client_factory),
                CalendarAddTool(client_factory),
                CalendarEditTool(client_factory),
            ]
        )
    return tools


@app.get("/health")
async def health() -> Dict[str, str]:
    return {"status": "ok"}


@app.get("/patterns")
async def handle_patterns() -> list[str]:
    return list_patterns()


@app.get("/")
async def index() -> FileResponse:
    # Get the project root directory (parent of groundhog/)
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    index_path = os.path.join(project_root, "index.html")
    return FileResponse(index_path)


@app.post("/login")
async def login(request: Request, settings: Settings = Depends(get_settings)):
    if not settings.master_password:
        raise HTTPException(status_code=404, detail="Password login disabled")
    form = await request.form()
    password = form.get("password")
    if password != settings.master_password:
        raise HTTPException(status_code=401, detail="Invalid password")
    token = encode_auth_cookie({}, settings)
    response = JSONResponse({"status": "ok"})
    response.set_cookie("Auth", token, httponly=True, samesite="lax", path="/")
    return response


@app.get("/oauth/login")
async def oauth_login(settings: Settings = Depends(get_settings)):
    if not (
        settings.google_client_id
        and settings.google_client_secret
        and settings.google_redirect_url
    ):
        raise HTTPException(status_code=404, detail="OAuth not configured")
    client = oauth_client(settings)
    state = secrets.token_urlsafe(32)
    auth_url = client.prepare_request_uri(
        "https://accounts.google.com/o/oauth2/auth",
        redirect_uri=settings.google_redirect_url,
        scope=SCOPES,
        state=state,
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
    )
    response = RedirectResponse(url=auth_url)
    response.set_cookie("oauth_state", state, httponly=True, samesite="lax")
    return response


@app.get("/oauth/oauth2callback")
async def oauth_callback(request: Request, settings: Settings = Depends(get_settings)):
    if not (
        settings.google_client_id
        and settings.google_client_secret
        and settings.google_redirect_url
    ):
        raise HTTPException(status_code=404, detail="OAuth not configured")
    stored_state = request.cookies.get("oauth_state")
    incoming_state = request.query_params.get("state")
    if stored_state and incoming_state and stored_state != incoming_state:
        raise HTTPException(status_code=400, detail="State mismatch")

    # Check for OAuth errors
    error = request.query_params.get("error")
    if error:
        raise HTTPException(status_code=400, detail=f"OAuth error: {error}")

    # Allow HTTP for local development (oauthlib requires HTTPS by default)
    if settings.google_redirect_url.startswith("http://"):
        os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"

    # Exchange authorization code for tokens
    client = oauth_client(settings)
    token_url, headers, body = client.prepare_token_request(
        "https://oauth2.googleapis.com/token",
        authorization_response=str(request.url),
        redirect_url=settings.google_redirect_url,
    )

    # Configure SSL verification for token request
    verify = not settings.google_redirect_url.startswith("http://")

    async with httpx.AsyncClient(verify=verify) as http_client:
        token_response = await http_client.post(
            token_url,
            headers=headers,
            content=body,
            auth=(settings.google_client_id, settings.google_client_secret),
        )
        token_response.raise_for_status()
        token_data = token_response.json()

    # Convert token response to format expected by Google credentials
    token_info = {
        "token": token_data.get("access_token"),
        "refresh_token": token_data.get("refresh_token"),
        "token_uri": "https://oauth2.googleapis.com/token",
        "client_id": settings.google_client_id,
        "client_secret": settings.google_client_secret,
        "scopes": token_data.get("scope", "").split()
        if token_data.get("scope")
        else SCOPES,
    }

    auth_token = encode_auth_cookie({"token": token_info}, settings)
    response = RedirectResponse(url="/")
    response.delete_cookie("oauth_state")
    response.set_cookie("Auth", auth_token, httponly=True, samesite="lax", path="/")
    return response


@app.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket, settings: Settings = Depends(get_settings)
):
    await websocket.accept()
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/ws",
        "headers": websocket.scope.get("headers", []),
        "query_string": b"",
        "client": websocket.scope.get("client"),
        "server": websocket.scope.get("server"),
        "scheme": websocket.scope.get("scheme", "ws"),
    }
    request = Request(scope)
    tools = build_tools(request, settings)

    # Create memory for this WebSocket connection
    memory = ConversationBufferMemory(
        memory_key="chat_history",
        return_messages=True,
    )

    executor = build_executor(
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url,
        model=settings.openai_model,
        tools=tools,
        memory=memory,
    )

    try:
        while True:
            data = await websocket.receive_json()
            pattern_name = data.get("pattern") or ""
            user_message = data.get("message") or ""
            pattern_prompt = PATTERNS.get(pattern_name, "")
            prompt = (
                pattern_prompt
                if not user_message
                else f"{pattern_prompt}\n\n{user_message}"
                if pattern_prompt
                else user_message
            )
            result = await run_in_threadpool(run_agent, executor, prompt)
            await websocket.send_text(result)
    except WebSocketDisconnect:
        return
    except Exception as exc:  # pylint: disable=broad-except
        await websocket.send_text(f"Server error: {exc}")
        await websocket.close()
