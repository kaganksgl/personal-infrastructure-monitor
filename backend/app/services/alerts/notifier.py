"""Alert delivery channels.

The engine only knows the ``AlertNotifier`` protocol. Email, Discord or
Telegram delivery can be added as new notifiers without touching the engine.
"""

import logging
from dataclasses import dataclass
from typing import Literal, Protocol

from app.schemas.alerts import AlertOut
from app.services.events import alert_event
from app.websocket.hub import Hub

AlertAction = Literal["fired", "resolved", "acknowledged"]


@dataclass(frozen=True, slots=True)
class AlertEvent:
    action: AlertAction
    alert: AlertOut


class AlertNotifier(Protocol):
    async def notify(self, event: AlertEvent) -> None: ...


class LogNotifier:
    def __init__(self) -> None:
        self._log = logging.getLogger("alerts")

    async def notify(self, event: AlertEvent) -> None:
        level = logging.WARNING if event.action == "fired" else logging.INFO
        self._log.log(
            level,
            f"alert.{event.action}",
            extra={
                "agent_id": event.alert.agent_id,
                "alert_id": event.alert.id,
                "severity": event.alert.severity,
                "rule": event.alert.rule_name,
                "alert_message": event.alert.message,
            },
        )


class WebSocketNotifier:
    def __init__(self, hub: Hub) -> None:
        self._hub = hub

    async def notify(self, event: AlertEvent) -> None:
        self._hub.publish(alert_event(event.action, event.alert))


class CompositeNotifier:
    def __init__(self, *notifiers: AlertNotifier) -> None:
        self._notifiers = notifiers

    async def notify(self, event: AlertEvent) -> None:
        for notifier in self._notifiers:
            try:
                await notifier.notify(event)
            except Exception:  # one broken channel must not block the others
                logging.getLogger("alerts").exception("alert.notify_failed")
