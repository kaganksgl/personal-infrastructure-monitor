from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Double,
    ForeignKey,
    Index,
    Integer,
    String,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, TimestampMixin

SEVERITY_CHECK = "severity IN ('info', 'warning', 'critical')"


class AlertRule(TimestampMixin, Base):
    """``metric <operator> threshold`` sustained for ``duration_seconds``.

    ``metric`` is either a name from ``app.metrics_catalog`` or the special
    value ``agent_offline``. A NULL ``agent_pk`` applies the rule fleet-wide.
    """

    __tablename__ = "alert_rules"
    __table_args__ = (
        CheckConstraint(SEVERITY_CHECK, name="severity"),
        CheckConstraint("operator IN ('>', '<')", name="operator"),
        CheckConstraint("duration_seconds >= 0", name="duration"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(128))
    metric: Mapped[str] = mapped_column(String(32))
    operator: Mapped[str] = mapped_column(String(1), default=">")
    threshold: Mapped[float] = mapped_column(Double, default=0)
    duration_seconds: Mapped[int] = mapped_column(Integer, default=0)
    severity: Mapped[str] = mapped_column(String(16))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    agent_pk: Mapped[int | None] = mapped_column(ForeignKey("agents.id", ondelete="CASCADE"))


class Alert(Base):
    __tablename__ = "alerts"
    __table_args__ = (
        CheckConstraint(SEVERITY_CHECK, name="severity"),
        CheckConstraint("status IN ('firing', 'resolved')", name="status"),
        # At most one firing alert per (agent, rule), enforced by the database
        # so concurrent ingestion requests cannot double-fire.
        Index(
            "uq_alerts_one_firing_per_rule",
            "agent_pk",
            "rule_id",
            unique=True,
            postgresql_where=text("status = 'firing'"),
        ),
        Index("ix_alerts_started_at", "started_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    agent_pk: Mapped[int] = mapped_column(ForeignKey("agents.id", ondelete="CASCADE"), index=True)
    rule_id: Mapped[int | None] = mapped_column(ForeignKey("alert_rules.id", ondelete="SET NULL"))
    rule_name: Mapped[str] = mapped_column(String(128))
    metric: Mapped[str] = mapped_column(String(32))
    severity: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(16), default="firing")
    message: Mapped[str] = mapped_column(String(512))
    value: Mapped[float | None] = mapped_column(Double)
    threshold: Mapped[float | None] = mapped_column(Double)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    acknowledged_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
