"""Rule-based alert evaluation.

Threshold rules are evaluated against the newest sample of every ingested
batch. A rule with ``duration_seconds > 0`` fires only once its condition has
held continuously for that long, measured on sample timestamps so that a
burst of buffered samples is judged on when they were *taken*.

Pending ("breaching but not yet long enough") state is kept in memory. After a
backend restart a sustained condition therefore needs one more full duration
to fire: a deliberate trade-off for simplicity over restart-exact timing.
Firing alerts themselves live in PostgreSQL, and a partial unique index
guarantees at most one firing alert per (agent, rule).
"""

from datetime import datetime

from sqlalchemy import or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Agent, Alert, AlertRule
from app.schemas.alerts import OFFLINE_METRIC
from app.services.alerts.formatting import offline_message, threshold_message
from app.services.alerts.notifier import AlertEvent, AlertNotifier
from app.services.alerts.queries import to_out


def _breached(rule: AlertRule, value: float) -> bool:
    return value > rule.threshold if rule.operator == ">" else value < rule.threshold


class AlertEngine:
    def __init__(self, notifier: AlertNotifier) -> None:
        self._notifier = notifier
        self._pending_since: dict[tuple[int, int], datetime] = {}

    async def evaluate_sample(
        self, db: AsyncSession, agent: Agent, summary: dict[str, float | None], ts: datetime
    ) -> None:
        rules = await self._rules_for(db, agent, offline=False)
        firing = await self._firing_by_rule(db, agent)
        events: list[AlertEvent] = []

        for rule in rules:
            value = summary.get(rule.metric)
            key = (agent.id, rule.id)
            if value is not None and _breached(rule, value):
                since = self._pending_since.setdefault(key, ts)
                held = (ts - since).total_seconds()
                if rule.id not in firing and held >= rule.duration_seconds:
                    alert = await self._fire(db, agent, rule, threshold_message(rule, value), value)
                    if alert is not None:
                        events.append(AlertEvent("fired", to_out(alert, agent.agent_id)))
            else:
                self._pending_since.pop(key, None)
                if rule.id in firing:
                    events.append(self._resolve(firing[rule.id], agent, ts))

        await db.commit()
        await self._dispatch(events)

    async def agent_went_offline(
        self, db: AsyncSession, agent: Agent, now: datetime, after: int
    ) -> list[AlertEvent]:
        events: list[AlertEvent] = []
        firing = await self._firing_by_rule(db, agent)
        for rule in await self._rules_for(db, agent, offline=True):
            if rule.id in firing:
                continue
            message = offline_message(agent.display_name, after)
            alert = await self._fire(db, agent, rule, message, None, started_at=now)
            if alert is not None:
                events.append(AlertEvent("fired", to_out(alert, agent.agent_id)))
        return events

    async def agent_came_online(
        self, db: AsyncSession, agent: Agent, now: datetime
    ) -> list[AlertEvent]:
        firing = await self._firing_by_rule(db, agent, metric=OFFLINE_METRIC)
        return [self._resolve(alert, agent, now) for alert in firing.values()]

    async def dispatch(self, events: list[AlertEvent]) -> None:
        await self._dispatch(events)

    def forget_agent(self, agent_pk: int) -> None:
        for key in [k for k in self._pending_since if k[0] == agent_pk]:
            del self._pending_since[key]

    # -- internals ---------------------------------------------------------

    async def _rules_for(self, db: AsyncSession, agent: Agent, *, offline: bool) -> list[AlertRule]:
        metric_filter = (
            AlertRule.metric == OFFLINE_METRIC if offline else AlertRule.metric != OFFLINE_METRIC
        )
        result = await db.execute(
            select(AlertRule).where(
                AlertRule.enabled.is_(True),
                metric_filter,
                or_(AlertRule.agent_pk.is_(None), AlertRule.agent_pk == agent.id),
            )
        )
        return list(result.scalars())

    async def _firing_by_rule(
        self, db: AsyncSession, agent: Agent, metric: str | None = None
    ) -> dict[int, Alert]:
        query = select(Alert).where(
            Alert.agent_pk == agent.id, Alert.status == "firing", Alert.rule_id.is_not(None)
        )
        if metric is not None:
            query = query.where(Alert.metric == metric)
        return {a.rule_id: a for a in (await db.execute(query)).scalars() if a.rule_id}

    async def _fire(
        self,
        db: AsyncSession,
        agent: Agent,
        rule: AlertRule,
        message: str,
        value: float | None,
        started_at: datetime | None = None,
    ) -> Alert | None:
        # ON CONFLICT against the partial unique index: if a concurrent request
        # already fired this rule, silently do nothing.
        stmt = (
            insert(Alert)
            .values(
                agent_pk=agent.id,
                rule_id=rule.id,
                rule_name=rule.name,
                metric=rule.metric,
                severity=rule.severity,
                status="firing",
                message=message,
                value=value,
                threshold=rule.threshold if rule.metric != OFFLINE_METRIC else None,
                started_at=started_at or self._pending_since.get((agent.id, rule.id)),
            )
            .on_conflict_do_nothing(
                index_elements=["agent_pk", "rule_id"],
                index_where=Alert.status == "firing",
            )
            .returning(Alert)
        )
        return (await db.execute(stmt)).scalar_one_or_none()

    def _resolve(self, alert: Alert, agent: Agent, now: datetime) -> AlertEvent:
        alert.status = "resolved"
        alert.resolved_at = now
        return AlertEvent("resolved", to_out(alert, agent.agent_id))

    async def _dispatch(self, events: list[AlertEvent]) -> None:
        for event in events:
            await self._notifier.notify(event)
