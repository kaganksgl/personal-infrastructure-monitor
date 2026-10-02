"""Pure unit tests (no database)."""

import asyncio
import json
import logging

from app.auth.passwords import hash_password, verify_password
from app.auth.rate_limit import RateLimiter
from app.auth.tokens import hash_token, new_api_key, tokens_match
from app.logging_config import JsonFormatter
from app.metrics_catalog import METRIC_NAMES
from app.models import MetricSample
from app.services.agents import OVERVIEW_METRICS
from app.services.alerts.formatting import format_value
from app.websocket.hub import Hub


def test_every_catalog_metric_is_a_sample_column():
    columns = set(MetricSample.__table__.columns.keys())
    assert set(METRIC_NAMES) <= columns
    assert set(OVERVIEW_METRICS) <= set(METRIC_NAMES)


def test_password_round_trip():
    hashed = hash_password("s3cret-password")
    assert verify_password(hashed, "s3cret-password")
    assert not verify_password(hashed, "wrong")
    assert not verify_password(None, "anything")
    assert not verify_password("not-a-hash", "anything")


def test_api_keys_are_unique_and_verifiable():
    key, key_hash, prefix = new_api_key()
    assert key.startswith(prefix) and tokens_match(key, key_hash)
    assert not tokens_match(key + "x", key_hash)
    assert new_api_key()[0] != key
    assert hash_token(key) == key_hash


def test_rate_limiter_sliding_window():
    now = [0.0]
    limiter = RateLimiter(limit=2, window_seconds=10, clock=lambda: now[0])
    assert limiter.hit("a") and limiter.hit("a")
    assert not limiter.hit("a")
    assert limiter.hit("b")  # keys are independent
    now[0] = 10.5
    assert limiter.hit("a")


def test_json_logs_redact_secrets():
    record = logging.LogRecord("ingestion", logging.INFO, "", 0, "agent.auth", None, None)
    record.api_key = "iwk_secret"
    record.agent_id = "web-1"
    payload = json.loads(JsonFormatter().format(record))
    assert payload["event"] == "agent.auth" and payload["component"] == "ingestion"
    assert payload["api_key"] == "***" and payload["agent_id"] == "web-1"


def test_value_formatting():
    assert format_value("cpu_percent", 94.71) == "94.7%"
    assert format_value("temperature_max_c", 85) == "85.0°C"
    assert format_value("net_rx_bps", 2048) == "2.0 KiB/s"


def test_hub_drops_events_for_slow_subscriber_and_requests_resync():
    async def scenario():
        hub = Hub()
        sub = hub.subscribe()
        for i in range(sub.queue.maxsize + 5):
            hub.publish({"type": "sample", "n": i})
        assert sub.lagging
        for _ in range(sub.queue.maxsize):
            await hub.next_event(sub)
        assert (await hub.next_event(sub)) == {"type": "resync"}
        hub.publish({"type": "sample", "n": "after"})
        assert (await hub.next_event(sub))["n"] == "after"

    asyncio.run(scenario())
