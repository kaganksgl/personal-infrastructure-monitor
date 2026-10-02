"""Failure handling of the run loop with a fake server."""

from collections.abc import Callable

import httpx

from infrawatch_agent.collectors import CollectorRegistry
from infrawatch_agent.config import AgentConfig
from infrawatch_agent.main import AgentRunner
from infrawatch_agent.transport.client import HttpTransport


class FakeServer:
    def __init__(self) -> None:
        self.mode: Callable[[httpx.Request], httpx.Response] = self.accept
        self.received: list[dict] = []
        self.requests = 0

    def accept(self, request: httpx.Request) -> httpx.Response:
        import json

        body = json.loads(request.read())
        self.received.extend(body["samples"])
        return httpx.Response(200, json={"accepted": len(body["samples"]), "rejected": []})

    def down(self, request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.requests += 1
        return self.mode(request)


class StaticCollector:
    name = "cpu"

    def prime(self) -> None:
        pass

    def collect(self) -> dict:
        return {"usage_percent": 1.0}


def make_runner(config: AgentConfig, server: FakeServer) -> AgentRunner:
    client = httpx.Client(base_url="http://test", transport=httpx.MockTransport(server.handle))
    transport = HttpTransport("http://test", config.agent_id, config.api_key, client=client)
    return AgentRunner(config, registry=CollectorRegistry([StaticCollector()]), transport=transport)


def test_samples_are_buffered_while_server_is_down_and_flushed_in_order(config: AgentConfig):
    server = FakeServer()
    runner = make_runner(config, server)
    server.mode = server.down
    for _ in range(3):
        runner.cycle()
    assert runner.buffer.size() == 3
    assert runner.state.failed_requests_total == 1  # backoff stops repeated attempts
    assert runner.backoff.failures == 1

    server.mode = server.accept
    runner.backoff.success()  # pretend the backoff delay elapsed
    runner.cycle()
    assert runner.buffer.size() == 0
    timestamps = [s["timestamp"] for s in server.received]
    assert len(timestamps) == 4 and timestamps == sorted(timestamps)
    assert server.received[-1]["agent"]["failed_requests_total"] == 1


def test_rejected_batch_is_dropped_not_retried_forever(config: AgentConfig):
    server = FakeServer()
    server.mode = lambda req: httpx.Response(422, json={"detail": "bad"})
    runner = make_runner(config, server)
    runner.cycle()
    assert runner.buffer.size() == 0
    assert runner.backoff.failures == 0


def test_auth_failure_backs_off_to_the_cap(config: AgentConfig):
    server = FakeServer()
    server.mode = lambda req: httpx.Response(401, json={"detail": "Invalid agent credentials"})
    runner = make_runner(config, server)
    runner.cycle()
    assert runner.buffer.size() == 1  # data kept until credentials are fixed
    assert runner.backoff.seconds_until_retry >= config.max_backoff - 1
    assert "auth" in (runner.state.last_error or "")


def test_payload_too_large_halves_batch_size(config: AgentConfig):
    server = FakeServer()
    runner = make_runner(config, server)
    for _ in range(4):
        runner.collect_once()

    def limit(request: httpx.Request) -> httpx.Response:
        import json

        if len(json.loads(request.read())["samples"]) > 2:
            return httpx.Response(413, json={"detail": "too large"})
        return server.accept(request)

    server.mode = limit
    runner.flush()
    assert runner.batch_size <= 2
    assert runner.buffer.size() == 0


def test_system_info_is_sent_once_then_periodically(config: AgentConfig):
    import json

    bodies = []
    server = FakeServer()

    def capture(request: httpx.Request) -> httpx.Response:
        bodies.append(json.loads(request.read()))
        return server.accept(request)

    server.mode = capture
    runner = make_runner(config, server)
    runner.cycle()
    runner.cycle()
    assert "system_info" in bodies[0] and "system_info" not in bodies[1]


def test_state_file_reflects_progress(config: AgentConfig):
    from infrawatch_agent.state import read_state

    runner = make_runner(config, FakeServer())
    runner.cycle()
    state = read_state(config.state_path)
    assert state is not None
    assert state["samples_uploaded"] == 1 and state["queue_size"] == 0
