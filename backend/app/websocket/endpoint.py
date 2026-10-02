"""``/api/v1/ws`` — live event stream for the dashboard."""

import asyncio
import contextlib
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status

from app.auth.dependencies import SESSION_COOKIE, resolve_session_user
from app.websocket.hub import Hub, Subscriber

log = logging.getLogger("websocket")
router = APIRouter()


def _origin_allowed(websocket: WebSocket) -> bool:
    """Block cross-site WebSocket hijacking.

    Browsers attach cookies to cross-origin WebSocket handshakes and CORS does
    not apply, so the Origin header must be checked explicitly.
    """
    origin = websocket.headers.get("origin")
    if origin is None:
        return True  # non-browser client; it still needs a valid session cookie
    host = websocket.headers.get("host", "")
    same_origin = origin.split("://", 1)[-1] == host
    return same_origin or origin in websocket.app.state.settings.cors_origins


@router.websocket("/ws")
async def live_events(websocket: WebSocket) -> None:
    if not _origin_allowed(websocket):
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return
    async with websocket.app.state.db.sessionmaker() as db:
        user = await resolve_session_user(db, websocket.cookies.get(SESSION_COOKIE))
    if user is None:
        await websocket.close(code=4401)
        return

    await websocket.accept()
    hub = websocket.app.state.hub
    sub = hub.subscribe()
    log.info("websocket.connected", extra={"user": user.username})
    sender = asyncio.create_task(_pump(websocket, hub, sub))
    try:
        # The client only sends keep-alive pings; reading also detects disconnects.
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        sender.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await sender
        hub.unsubscribe(sub)
        log.info("websocket.disconnected", extra={"user": user.username})


async def _pump(websocket: WebSocket, hub: Hub, sub: Subscriber) -> None:
    await websocket.send_json({"type": "hello"})
    while True:
        event = await hub.next_event(sub)
        await websocket.send_json(event)
