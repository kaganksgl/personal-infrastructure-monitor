"""Alert persistence helpers shared by the engine and the API."""

from collections.abc import Sequence

from sqlalchemy import Select, select
from sqlalchemy.orm import aliased

from app.models import Agent, Alert, User
from app.schemas.alerts import AlertOut

_Acker = aliased(User)


def alert_select() -> Select[Alert, str, str]:
    return (
        select(Alert, Agent.agent_id, _Acker.username)
        .join(Agent, Agent.id == Alert.agent_pk)
        .outerjoin(_Acker, _Acker.id == Alert.acknowledged_by_id)
    )


def to_out(alert: Alert, agent_id: str, acked_by: str | None = None) -> AlertOut:
    return AlertOut(
        id=alert.id,
        agent_id=agent_id,
        rule_id=alert.rule_id,
        rule_name=alert.rule_name,
        metric=alert.metric,
        severity=alert.severity,
        status=alert.status,
        message=alert.message,
        value=alert.value,
        threshold=alert.threshold,
        started_at=alert.started_at,
        resolved_at=alert.resolved_at,
        acknowledged_at=alert.acknowledged_at,
        acknowledged_by=acked_by,
    )


def rows_to_out(rows: Sequence[tuple[Alert, str, str | None]]) -> list[AlertOut]:
    return [to_out(alert, agent_id, acker) for alert, agent_id, acker in rows]
