from datetime import UTC, datetime, timedelta

import httpx

from tests.conftest import agent_headers
from tests.factories import make_sample, system_info


async def test_valid_sample_is_stored(admin_client: httpx.AsyncClient, agent_creds):
    resp = await admin_client.post(
        "/api/v1/metrics", json=make_sample("web-1", cpu=37.4), headers=agent_headers(agent_creds)
    )
    assert resp.status_code == 200
    assert resp.json() == {"accepted": 1, "duplicates": 0, "rejected": []}

    latest = (await admin_client.get("/api/v1/metrics/web-1/latest")).json()
    assert latest["summary"]["cpu_percent"] == 37.4
    assert latest["summary"]["disk_percent_max"] == 50.0
    assert latest["details"]["network"]["interfaces"][0]["name"] == "eth0"
    assert latest["details"]["processes"]["total"] == 321


async def test_batch_with_system_info(admin_client: httpx.AsyncClient, agent_creds):
    now = datetime.now(UTC)
    batch = {
        "agent_id": "web-1",
        "system_info": system_info(),
        "samples": [make_sample("web-1", now - timedelta(seconds=5 * i)) for i in range(5)],
    }
    resp = await admin_client.post(
        "/api/v1/metrics/batch", json=batch, headers=agent_headers(agent_creds)
    )
    assert resp.json()["accepted"] == 5
    agent = (await admin_client.get("/api/v1/agents/web-1")).json()
    assert agent["system_info"]["hostname"] == "test-host"
    assert agent["agent_version"] == "1.0.0"


async def test_reupload_is_idempotent(admin_client: httpx.AsyncClient, agent_creds):
    sample = make_sample("web-1")
    headers = agent_headers(agent_creds)
    await admin_client.post("/api/v1/metrics", json=sample, headers=headers)
    resp = await admin_client.post("/api/v1/metrics", json=sample, headers=headers)
    assert resp.json() == {"accepted": 0, "duplicates": 1, "rejected": []}


async def test_missing_or_wrong_credentials(admin_client: httpx.AsyncClient, agent_creds):
    sample = make_sample("web-1")
    assert (await admin_client.post("/api/v1/metrics", json=sample)).status_code == 401
    wrong = {"Authorization": "Bearer iwk_wrong", "X-Agent-ID": "web-1"}
    assert (
        await admin_client.post("/api/v1/metrics", json=sample, headers=wrong)
    ).status_code == 401
    unknown = {**agent_headers(agent_creds), "X-Agent-ID": "ghost"}
    resp = await admin_client.post("/api/v1/metrics", json=sample, headers=unknown)
    assert resp.status_code == 401  # same answer as a wrong key: no ID enumeration


async def test_agent_cannot_submit_for_another_agent(admin_client: httpx.AsyncClient, agent_creds):
    await admin_client.post("/api/v1/agents", json={"agent_id": "victim"})
    resp = await admin_client.post(
        "/api/v1/metrics", json=make_sample("victim"), headers=agent_headers(agent_creds)
    )
    assert resp.status_code == 403


async def test_malformed_payloads_are_rejected(admin_client: httpx.AsyncClient, agent_creds):
    headers = agent_headers(agent_creds)
    cases = []
    bad_cpu = make_sample("web-1")
    bad_cpu["cpu"]["usage_percent"] = 150
    cases.append(bad_cpu)
    missing = make_sample("web-1")
    del missing["memory"]
    cases.append(missing)
    naive_ts = make_sample("web-1")
    naive_ts["timestamp"] = "2026-01-01T10:00:00"
    cases.append(naive_ts)
    wrong_type = make_sample("web-1")
    wrong_type["network"]["interfaces"][0]["rx_bytes"] = "lots"
    cases.append(wrong_type)
    flood = make_sample("web-1")
    flood["cpu"]["per_core_percent"] = [1.0] * 5000
    cases.append(flood)
    future_schema = make_sample("web-1")
    future_schema["schema_version"] = 99
    cases.append(future_schema)
    for payload in cases:
        resp = await admin_client.post("/api/v1/metrics", json=payload, headers=headers)
        assert resp.status_code == 422
    garbage = await admin_client.post(
        "/api/v1/metrics",
        content=b"{not json",
        headers={**headers, "Content-Type": "application/json"},
    )
    assert garbage.status_code == 422


async def test_out_of_window_timestamps_are_rejected_individually(
    admin_client: httpx.AsyncClient, agent_creds
):
    now = datetime.now(UTC)
    batch = {
        "agent_id": "web-1",
        "samples": [
            make_sample("web-1", now),
            make_sample("web-1", now + timedelta(hours=2)),
            make_sample("web-1", now - timedelta(days=5)),
        ],
    }
    resp = await admin_client.post(
        "/api/v1/metrics/batch", json=batch, headers=agent_headers(agent_creds)
    )
    body = resp.json()
    assert body["accepted"] == 1
    assert [r["index"] for r in body["rejected"]] == [1, 2]


async def test_oversized_batch_is_rejected(admin_client: httpx.AsyncClient, agent_creds, settings):
    settings.max_batch_size = 3
    batch = {"agent_id": "web-1", "samples": [make_sample("web-1")] * 4}
    resp = await admin_client.post(
        "/api/v1/metrics/batch", json=batch, headers=agent_headers(agent_creds)
    )
    assert resp.status_code == 413


async def test_unknown_fields_are_ignored_not_stored(admin_client: httpx.AsyncClient, agent_creds):
    sample = make_sample("web-1")
    sample["cpu"]["future_field"] = 1
    sample["evil"] = "x" * 100
    resp = await admin_client.post(
        "/api/v1/metrics", json=sample, headers=agent_headers(agent_creds)
    )
    assert resp.status_code == 200
    details = (await admin_client.get("/api/v1/metrics/web-1/latest")).json()["details"]
    assert "future_field" not in details["cpu"] and "evil" not in details
