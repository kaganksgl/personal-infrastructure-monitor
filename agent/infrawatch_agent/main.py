"""The agent run loop.

    every COLLECTION_INTERVAL seconds:
        collect  -> append to durable buffer       (never blocked by the network)
        flush    -> upload buffered batches         (only when backoff allows)

Collection and upload are decoupled: while the server is unreachable the
agent keeps sampling into the buffer and uploads the backlog, oldest first,
once the server is back.
"""

import logging
import os
import signal
import threading
import time
from datetime import datetime, timezone
from typing import Any

import psutil

from infrawatch_agent import PROTOCOL_VERSION, __version__
from infrawatch_agent.collectors import CollectorRegistry, HostPaths, default_registry
from infrawatch_agent.collectors.host import system_info
from infrawatch_agent.config import AgentConfig
from infrawatch_agent.state import AgentState, write_state
from infrawatch_agent.transport.backoff import Backoff
from infrawatch_agent.transport.buffer import SampleBuffer
from infrawatch_agent.transport.client import HttpTransport, Outcome

log = logging.getLogger("agent")

_SYSTEM_INFO_REFRESH = 3600.0
_MAX_BATCHES_PER_CYCLE = 10


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class AgentRunner:
    def __init__(
        self,
        config: AgentConfig,
        *,
        registry: CollectorRegistry | None = None,
        transport: HttpTransport | None = None,
        buffer: SampleBuffer | None = None,
        paths: HostPaths | None = None,
    ) -> None:
        self.config = config
        self.paths = paths or HostPaths()
        self.registry = registry or default_registry(config, self.paths)
        self.transport = transport or HttpTransport(
            config.server_url,
            config.agent_id,
            config.api_key,
            timeout=config.request_timeout,
            verify=config.ca_bundle or config.verify_tls,
        )
        self.buffer = buffer or SampleBuffer(config.buffer_path, config.buffer_size)
        self.backoff = Backoff(cap=config.max_backoff)
        self.batch_size = config.batch_size
        self.stop_event = threading.Event()
        self.state = AgentState(
            pid=os.getpid(),
            version=__version__,
            agent_id=config.agent_id,
            server_url=config.server_url,
            started_at=_utcnow().isoformat(),
            queue_size=self.buffer.size(),
        )
        self._self_proc = psutil.Process()
        self._self_proc.cpu_percent()
        self._last_collect = time.monotonic()
        self._system_info_sent_at: float | None = None

    # -- lifecycle -----------------------------------------------------------

    def run_forever(self) -> None:
        self._install_signal_handlers()
        log.info(
            "agent.started",
            extra={
                "version": __version__,
                "server": self.config.server_url,
                "interval": self.config.collection_interval,
                "buffered": self.buffer.size(),
            },
        )
        self.registry.prime()
        self._last_collect = time.monotonic()
        next_tick = time.monotonic() + self.config.collection_interval
        while not self.stop_event.wait(max(0.0, next_tick - time.monotonic())):
            next_tick += self.config.collection_interval
            # If a cycle overran (e.g. a slow upload), skip missed ticks instead
            # of firing a burst of back-to-back collections.
            if next_tick < time.monotonic():
                next_tick = time.monotonic() + self.config.collection_interval
            self.cycle()
        self.shutdown()

    def cycle(self) -> None:
        try:
            self.collect_once()
        except Exception:
            log.exception("agent.collect_failed")
        try:
            self.flush()
        except Exception:
            log.exception("agent.flush_failed")
        self._write_state()

    def shutdown(self) -> None:
        log.info("agent.stopping", extra={"buffered": self.buffer.size()})
        # One last best-effort flush so a clean restart loses nothing.
        if self.backoff.ready():
            self.flush()
        self._write_state()
        self.transport.close()
        self.buffer.close()

    def _install_signal_handlers(self) -> None:
        def stop(signum: int, _frame: object) -> None:
            log.info("agent.signal", extra={"signal": signal.Signals(signum).name})
            self.stop_event.set()

        signal.signal(signal.SIGTERM, stop)
        signal.signal(signal.SIGINT, stop)

    # -- collection ----------------------------------------------------------

    def collect_once(self) -> dict[str, Any]:
        now_mono = time.monotonic()
        interval = max(0.001, now_mono - self._last_collect)
        self._last_collect = now_mono
        result = self.registry.collect()
        sample = {
            "schema_version": PROTOCOL_VERSION,
            "agent_id": self.config.agent_id,
            "timestamp": _utcnow().isoformat(),
            "interval_seconds": round(min(interval, 3600.0), 3),
            **result.sections,
            "agent": self._self_metrics(result.duration_ms, result.errors),
        }
        self.buffer.put(sample)
        self.state.samples_collected += 1
        self.state.last_collection_at = sample["timestamp"]
        log.debug("agent.collected", extra={"duration_ms": round(result.duration_ms, 1)})
        return sample

    def _self_metrics(self, duration_ms: float, errors: list[str]) -> dict[str, Any]:
        """The monitor monitors itself: its own footprint travels with every sample."""
        with self._self_proc.oneshot():
            cpu = self._self_proc.cpu_percent()
            rss = self._self_proc.memory_info().rss
        return {
            "version": __version__,
            "cpu_percent": round(cpu, 2),
            "memory_rss_bytes": rss,
            "collection_duration_ms": round(duration_ms, 2),
            "queue_size": self.buffer.size(),
            "failed_requests_total": self.state.failed_requests_total,
            "dropped_samples_total": self.buffer.dropped_total,
            "collector_errors": errors,
        }

    # -- upload --------------------------------------------------------------

    def flush(self) -> None:
        for _ in range(_MAX_BATCHES_PER_CYCLE):
            if not self.backoff.ready():
                return
            batch = self.buffer.peek(self.batch_size)
            if not batch or not self._send(batch):
                return

    def _system_info_due(self) -> bool:
        sent = self._system_info_sent_at
        return sent is None or time.monotonic() - sent > _SYSTEM_INFO_REFRESH

    def _send(self, batch: list[tuple[int, dict[str, Any]]]) -> bool:
        """Upload one batch; return True if the loop may continue with the next."""
        ids = [row_id for row_id, _ in batch]
        info = system_info(self.paths) if self._system_info_due() else None
        result = self.transport.send_batch([s for _, s in batch], info)
        self.state.queue_size = self.buffer.size()

        if result.outcome is Outcome.OK:
            self.buffer.ack(ids)
            self.backoff.success()
            if info is not None:
                self._system_info_sent_at = time.monotonic()
            self._record_success(result.body, len(ids))
            return True

        self.state.failed_requests_total += 1
        self.state.last_error = (
            f"{result.outcome.value}: {result.status_code or ''} {result.detail}"
        )
        if result.outcome is Outcome.REJECTED:
            log.error(
                "upload.rejected",
                extra={"status": result.status_code, "detail": result.detail, "dropped": len(ids)},
            )
            self.buffer.ack(ids)
            return True
        if result.outcome is Outcome.TOO_LARGE and self.batch_size > 1:
            self.batch_size = max(1, self.batch_size // 2)
            log.warning("upload.batch_too_large", extra={"new_batch_size": self.batch_size})
            return True
        cap = self.config.max_backoff if result.outcome is Outcome.AUTH else 0.0
        delay = self.backoff.failure(minimum=max(result.retry_after, cap))
        log.warning(
            "upload.failed",
            extra={
                "outcome": result.outcome.value,
                "status": result.status_code,
                "detail": result.detail,
                "retry_in": round(delay, 1),
                "buffered": self.buffer.size(),
            },
        )
        return False

    def _record_success(self, body: dict[str, Any], count: int) -> None:
        self.state.samples_uploaded += count
        self.state.last_upload_at = _utcnow().isoformat()
        self.state.last_error = None
        for rejected in body.get("rejected", []):
            log.warning("upload.sample_rejected", extra={"reason": rejected.get("reason")})

    def _write_state(self) -> None:
        self.state.queue_size = self.buffer.size()
        self.state.dropped_samples_total = self.buffer.dropped_total
        self.state.next_retry_in_seconds = round(self.backoff.seconds_until_retry, 1)
        try:
            write_state(self.config.state_path, self.state)
        except OSError:
            log.warning("agent.state_write_failed", extra={"path": str(self.config.state_path)})
