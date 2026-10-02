import httpx
import pytest

from infrawatch_agent.transport.backoff import Backoff
from infrawatch_agent.transport.buffer import SampleBuffer
from infrawatch_agent.transport.client import HttpTransport, Outcome


def make_transport(handler) -> HttpTransport:
    client = httpx.Client(base_url="http://test", transport=httpx.MockTransport(handler))
    return HttpTransport("http://test", "a1", "key", client=client)


@pytest.mark.parametrize(
    ("status", "outcome"),
    [
        (200, Outcome.OK),
        (401, Outcome.AUTH),
        (403, Outcome.AUTH),
        (413, Outcome.TOO_LARGE),
        (422, Outcome.REJECTED),
        (429, Outcome.RETRY),
        (500, Outcome.RETRY),
        (503, Outcome.RETRY),
    ],
)
def test_status_classification(status: int, outcome: Outcome):
    transport = make_transport(lambda req: httpx.Response(status, json={"detail": "x"}))
    assert transport.send_batch([{}]).outcome is outcome


def test_network_failure_is_retryable():
    def refuse(request):
        raise httpx.ConnectError("connection refused")

    result = make_transport(refuse).send_batch([{}])
    assert result.outcome is Outcome.RETRY and "refused" in result.detail


def test_malformed_success_response_is_retried():
    transport = make_transport(lambda req: httpx.Response(200, text="<html>proxy</html>"))
    assert transport.send_batch([{}]).outcome is Outcome.RETRY


def test_retry_after_header_is_respected():
    transport = make_transport(lambda req: httpx.Response(429, headers={"Retry-After": "30"}))
    assert transport.send_batch([{}]).retry_after == 30


def test_batch_envelope_and_auth_headers():
    seen = {}

    def capture(request: httpx.Request):
        seen["path"] = request.url.path
        seen["body"] = request.read()
        return httpx.Response(200, json={"accepted": 1})

    client = httpx.Client(base_url="http://test", transport=httpx.MockTransport(capture))
    HttpTransport("http://test", "a1", "key", client=client).send_batch([{"x": 1}], {"h": 1})
    assert seen["path"] == "/api/v1/metrics/batch"
    assert b'"system_info"' in seen["body"] and b'"agent_id":"a1"' in seen["body"]


def test_backoff_grows_exponentially_with_cap():
    now = [0.0]
    backoff = Backoff(base=2, cap=60, clock=lambda: now[0], rng=lambda lo, hi: hi)
    delays = [backoff.failure() for _ in range(7)]
    assert delays == [4, 8, 16, 32, 60, 60, 60]
    assert not backoff.ready()
    now[0] = 61
    assert backoff.ready()
    backoff.success()
    assert backoff.failures == 0 and backoff.ready()


def test_buffer_is_fifo_bounded_and_durable(tmp_path):
    path = tmp_path / "buf.db"
    buffer = SampleBuffer(path, max_size=3)
    for i in range(5):
        buffer.put({"n": i})
    assert buffer.size() == 3 and buffer.dropped_total == 2  # oldest two dropped
    batch = buffer.peek(2)
    assert [s["n"] for _, s in batch] == [2, 3]
    buffer.ack([row_id for row_id, _ in batch])
    buffer.close()

    reopened = SampleBuffer(path, max_size=3)  # survives a restart
    assert [s["n"] for _, s in reopened.peek(10)] == [4]
