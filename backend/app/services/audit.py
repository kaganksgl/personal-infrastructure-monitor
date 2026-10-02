"""Audit trail for security-relevant actions.

Entries are added to the caller's transaction, so an action and its audit
record are committed (or rolled back) together.
"""

import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditLog, User

log = logging.getLogger("audit")


def record(
    db: AsyncSession,
    action: str,
    *,
    user: User | None = None,
    username: str | None = None,
    target: str | None = None,
    ip: str | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    name = user.username if user else username
    db.add(
        AuditLog(
            user_id=user.id if user else None,
            username=name,
            action=action,
            target=target,
            ip_address=ip,
            details=details,
        )
    )
    log.info(action, extra={"user": name, "target": target, "ip": ip})
