"""HTTP transport to the InfraWatch backend.

Every outcome is classified so the run loop can decide what to do:

* ``OK``         - delivered; drop from the buffer.
* ``RETRY``      - transient (network error, timeout, 5xx, 429): keep, back off.
* ``AUTH``       - 401/403: credentials are wrong; keep data, back off to the cap.
* ``REJECTED``   - 400/422: the server will never accept this batch ("poison
                   message"); drop it so it cannot block the queue forever.
* ``TOO_LARGE``  - 413: retry with a smaller batch.
"""

import enum
import logging
from dataclasses import dataclass, field
from typing import Any

import httpx

from infrawatch_agent import __version__

log = logging.getLogger("transport")


class Outcome(enum.Enum):
    OK = "ok"
    RETRY = "retry"
    AUTH = "auth"
    REJECTED = "rejected"
    TOO_LARGE = "too_large"


@dataclass
class SendResult:
    outcome: Outcome
    status_code: int | None = None
    detail: str = ""
    retry_after: float = 0.0
    body: dict[str, Any] = field(default_factory=dict)


def _classify(status: int) -> Outcome:
    if 200 <= status < 300:
        return Outcome.OK
    if status in (401, 403):
        return Outcome.AUTH
    if status == 413:
        return Outcome.TOO_LARGE
    if status in (400, 422):
        return Outcome.REJECTED
    return Outcome.RETRY  # 429, 5xx, and anything unexpected


class HttpTransport:
    def __init__(
        self,
        server_url: str,
        agent_id: str,
        api_key: str,
        *,
        timeout: float = 10.0,
        verify: bool | str = True,
        client: httpx.Client | None = None,
    ) -> None:
        self._agent_id = agent_id
        self._client = client or httpx.Client(
            base_url=server_url,
            timeout=httpx.Timeout(timeout, connect=min(timeout, 5.0)),
            verify=verify,
            headers={
                "Authorization": f"Bearer {api_key}",
                "X-Agent-ID": agent_id,
                "User-Agent": f"infrawatch-agent/{__version__}",
            },
        )

    def send_batch(
        self, samples: list[dict[str, Any]], system_info: dict[str, Any] | None = None
    ) -> SendResult:
        payload: dict[str, Any] = {"agent_id": self._agent_id, "samples": samples}
        if system_info is not None:
            payload["system_info"] = system_info
        return self._request("POST", "/api/v1/metrics/batch", json=payload)

    def ping(self) -> SendResult:
        return self._request("GET", "/api/v1/agent/ping")

    def health(self) -> SendResult:
        return self._request("GET", "/api/v1/system/health")

    def _request(self, method: str, path: str, **kwargs: Any) -> SendResult:
        try:
            response = self._client.request(method, path, **kwargs)
        except httpx.TimeoutException as exc:
            return SendResult(Outcome.RETRY, detail=f"timeout: {exc}")
        except httpx.TransportError as exc:  # DNS, refused, TLS, reset...
            return SendResult(Outcome.RETRY, detail=f"{type(exc).__name__}: {exc}")

        outcome = _classify(response.status_code)
        try:
            body = response.json()
            if not isinstance(body, dict):
                body = {"data": body}
        except ValueError:
            # e.g. an HTML error page from a reverse proxy
            body = {}
            if outcome is Outcome.OK:
                outcome, body = Outcome.RETRY, {"detail": "malformed (non-JSON) server response"}
        retry_after = response.headers.get("Retry-After", "")
        return SendResult(
            outcome,
            status_code=response.status_code,
            detail=str(body.get("detail", ""))[:300],
            retry_after=float(retry_after) if retry_after.isdigit() else 0.0,
            body=body,
        )

    def close(self) -> None:
        self._client.close()
