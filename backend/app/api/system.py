import time
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Query, Request, Response, status
from sqlalchemy import select, text

from app import __version__
from app.auth.dependencies import AdminUser, DbSession
from app.models import AuditLog

router = APIRouter(prefix="/system", tags=["system"])


@router.get("/health")
async def health(request: Request, response: Response, db: DbSession) -> dict[str, Any]:
    """Liveness/readiness probe. Deliberately reveals nothing beyond up/down."""
    try:
        await db.execute(text("SELECT 1"))
        database = "ok"
    except Exception:
        database = "unavailable"
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return {
        "status": "ok" if database == "ok" else "degraded",
        "database": database,
        "version": __version__,
        "uptime_seconds": round(time.monotonic() - request.app.state.started_at),
        "websocket_clients": request.app.state.hub.subscriber_count,
    }


@router.get("/audit")
async def audit_log(
    db: DbSession, _: AdminUser, limit: Annotated[int, Query(ge=1, le=500)] = 100
) -> list[dict[str, Any]]:
    rows = await db.execute(select(AuditLog).order_by(AuditLog.ts.desc()).limit(limit))
    return [_audit_out(r) for r in rows.scalars()]


def _audit_out(entry: AuditLog) -> dict[str, Any]:
    ts: datetime = entry.ts
    return {
        "id": entry.id,
        "ts": ts.isoformat(),
        "username": entry.username,
        "action": entry.action,
        "target": entry.target,
        "ip_address": entry.ip_address,
        "details": entry.details,
    }
