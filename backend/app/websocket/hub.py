"""In-process publish/subscribe hub that fans events out to WebSocket clients.

Each subscriber gets a bounded queue. A slow client never blocks ingestion:
if its queue fills up, further events are dropped for it and it receives a
single ``resync`` message telling the dashboard to refetch state over REST.

Scaling note: with several backend replicas the hub would be backed by
PostgreSQL LISTEN/NOTIFY or Redis pub/sub; ``publish`` is the only seam.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any

log = logging.getLogger("websocket.hub")

Event = dict[str, Any]


@dataclass(eq=False)
class Subscriber:
    queue: asyncio.Queue[Event] = field(default_factory=lambda: asyncio.Queue(maxsize=256))
    lagging: bool = False


class Hub:
    def __init__(self) -> None:
        self._subscribers: set[Subscriber] = set()

    @property
    def subscriber_count(self) -> int:
        return len(self._subscribers)

    def subscribe(self) -> Subscriber:
        sub = Subscriber()
        self._subscribers.add(sub)
        return sub

    def unsubscribe(self, sub: Subscriber) -> None:
        self._subscribers.discard(sub)

    def publish(self, event: Event) -> None:
        for sub in self._subscribers:
            if sub.lagging:
                continue
            try:
                sub.queue.put_nowait(event)
            except asyncio.QueueFull:
                sub.lagging = True
                log.warning("websocket.subscriber_lagging")

    async def next_event(self, sub: Subscriber) -> Event:
        if sub.lagging and sub.queue.empty():
            sub.lagging = False
            return {"type": "resync"}
        return await sub.queue.get()
