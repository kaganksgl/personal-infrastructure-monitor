from datetime import UTC, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Query, Request, status
from sqlalchemy import select

from app.auth.dependencies import AdminUser, CurrentUser, DbSession, client_ip
from app.models import Agent, Alert, AlertRule
from app.schemas.alerts import (
    OFFLINE_METRIC,
    AlertOut,
    AlertRuleIn,
    AlertRuleOut,
    AlertRuleUpdate,
    Severity,
)
from app.services import audit
from app.services.alerts.notifier import AlertEvent
from app.services.alerts.queries import alert_select, rows_to_out, to_out

router = APIRouter(prefix="/alerts", tags=["alerts"])


@router.get("", response_model=list[AlertOut])
async def list_alerts(
    db: DbSession,
    _: CurrentUser,
    status_: Annotated[Literal["firing", "resolved"] | None, Query(alias="status")] = None,
    severity: Severity | None = None,
    agent_id: str | None = None,
    unacknowledged: bool = False,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> list[AlertOut]:
    query = alert_select().order_by(Alert.started_at.desc()).limit(limit)
    if status_:
        query = query.where(Alert.status == status_)
    if severity:
        query = query.where(Alert.severity == severity)
    if agent_id:
        query = query.where(Agent.agent_id == agent_id)
    if unacknowledged:
        query = query.where(Alert.acknowledged_at.is_(None))
    return rows_to_out((await db.execute(query)).all())


@router.post("/{alert_id}/acknowledge", response_model=AlertOut)
async def acknowledge_alert(
    alert_id: int, request: Request, db: DbSession, user: CurrentUser
) -> AlertOut:
    row = (await db.execute(alert_select().where(Alert.id == alert_id))).first()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Alert not found")
    alert, agent_id, _ = row
    if alert.acknowledged_at is None:
        alert.acknowledged_at = datetime.now(UTC)
        alert.acknowledged_by_id = user.id
        audit.record(
            db, "alert.acknowledged", user=user, target=str(alert_id), ip=client_ip(request)
        )
        await db.commit()
    out = to_out(alert, agent_id, user.username)
    await request.app.state.alert_engine.dispatch([AlertEvent("acknowledged", out)])
    return out


# ---- Rules ------------------------------------------------------------------


async def _rule_out(db: DbSession, rule: AlertRule) -> AlertRuleOut:
    agent_id = None
    if rule.agent_pk is not None:
        agent_id = (
            await db.execute(select(Agent.agent_id).where(Agent.id == rule.agent_pk))
        ).scalar_one_or_none()
    return AlertRuleOut(
        id=rule.id,
        name=rule.name,
        metric=rule.metric,
        operator=rule.operator,
        threshold=rule.threshold,
        duration_seconds=rule.duration_seconds,
        severity=rule.severity,
        enabled=rule.enabled,
        agent_id=agent_id,
        created_at=rule.created_at,
    )


async def _rule_or_404(db: DbSession, rule_id: int) -> AlertRule:
    rule = await db.get(AlertRule, rule_id)
    if rule is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Rule not found")
    return rule


@router.get("/rules", response_model=list[AlertRuleOut])
async def list_rules(db: DbSession, _: CurrentUser) -> list[AlertRuleOut]:
    rules = (await db.execute(select(AlertRule).order_by(AlertRule.id))).scalars()
    return [await _rule_out(db, r) for r in rules]


@router.post("/rules", response_model=AlertRuleOut, status_code=status.HTTP_201_CREATED)
async def create_rule(
    body: AlertRuleIn, request: Request, db: DbSession, admin: AdminUser
) -> AlertRuleOut:
    agent_pk = None
    if body.agent_id:
        agent_pk = (
            await db.execute(select(Agent.id).where(Agent.agent_id == body.agent_id))
        ).scalar_one_or_none()
        if agent_pk is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Agent not found")
    rule = AlertRule(**body.model_dump(exclude={"agent_id"}), agent_pk=agent_pk)
    if rule.metric == OFFLINE_METRIC:
        rule.threshold, rule.duration_seconds = 0, 0
    db.add(rule)
    await db.flush()
    audit.record(db, "alert_rule.created", user=admin, target=str(rule.id), ip=client_ip(request))
    await db.commit()
    return await _rule_out(db, rule)


@router.patch("/rules/{rule_id}", response_model=AlertRuleOut)
async def update_rule(
    rule_id: int, body: AlertRuleUpdate, request: Request, db: DbSession, admin: AdminUser
) -> AlertRuleOut:
    rule = await _rule_or_404(db, rule_id)
    changes = body.model_dump(exclude_unset=True, exclude_none=True)
    for field, value in changes.items():
        setattr(rule, field, value)
    audit.record(
        db,
        "alert_rule.updated",
        user=admin,
        target=str(rule_id),
        ip=client_ip(request),
        details=changes,
    )
    await db.commit()
    return await _rule_out(db, rule)


@router.delete("/rules/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_rule(rule_id: int, request: Request, db: DbSession, admin: AdminUser) -> None:
    rule = await _rule_or_404(db, rule_id)
    await db.delete(rule)
    audit.record(db, "alert_rule.deleted", user=admin, target=str(rule_id), ip=client_ip(request))
    await db.commit()
