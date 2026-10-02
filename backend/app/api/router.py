from fastapi import APIRouter

from app.api import agents, alerts, auth, metrics, system
from app.websocket import endpoint as ws

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth.router)
api_router.include_router(agents.router)
api_router.include_router(metrics.router)
api_router.include_router(alerts.router)
api_router.include_router(system.router)
api_router.include_router(ws.router)
