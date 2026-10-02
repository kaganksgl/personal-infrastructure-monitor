# Agent wire protocol (v1)

Any agent implementation (the bundled Python agent, a future Rust or Windows
agent) talks to the backend using only what is described here. The
authoritative schema is `backend/app/schemas/metrics.py` and is also visible
in the OpenAPI docs at `/api/docs`.

## Authentication

Every request carries:

```http
X-Agent-ID: web-01
Authorization: Bearer iwk_<43 random url-safe characters>
```

The key is issued once when the machine is registered (dashboard → Machines →
Add machine, or `POST /api/v1/agents`). The server stores only its SHA-256.
Unknown agent and wrong key both return `401` (no enumeration). The
`agent_id` inside the payload **must** equal `X-Agent-ID` (`403` otherwise).

`GET /api/v1/agent/ping` verifies credentials without sending data.

## Endpoints

| Method | Path | Body |
|--------|------|------|
| `POST` | `/api/v1/metrics` | one sample |
| `POST` | `/api/v1/metrics/batch` | `{"agent_id", "system_info"?, "samples": [...]}` (≤ 100 samples by default) |

Response (`200`):

```json
{ "accepted": 49, "duplicates": 1, "rejected": [{ "index": 3, "reason": "timestamp is in the future" }] }
```

* **Idempotent:** a sample with an `(agent_id, timestamp)` already stored is a
  duplicate, not an error, so re-sending after a lost response is safe.
* Samples older than raw retention or > 5 min in the future are rejected
  individually; the rest of the batch is still stored.

| Status | Meaning | Agent should |
|--------|---------|--------------|
| 200 | processed | delete the batch from its buffer |
| 401/403 | bad credentials / wrong agent | keep data, back off long |
| 413 | batch too large | retry with smaller batches |
| 422 | malformed | drop the batch (it will never be accepted) |
| 429 | rate limited | honour `Retry-After` |
| 5xx / 503 | server or database unavailable | keep data, exponential backoff |

## Sample

```jsonc
{
  "schema_version": 1,
  "agent_id": "web-01",
  "timestamp": "2026-10-03T10:00:05.123+00:00",   // UTC, timezone REQUIRED
  "interval_seconds": 5.0,                          // actual time since previous sample
  "cpu": {
    "usage_percent": 37.4, "per_core_percent": [35.1, 39.8],
    "logical_cores": 2, "physical_cores": 1, "frequency_mhz": 2400.0,
    "load_1m": 1.23, "load_5m": 1.12, "load_15m": 0.98,
    "iowait_percent": 0.5, "steal_percent": 0.0,
    "context_switches_per_sec": 8123.0, "interrupts_per_sec": 4100.0
  },
  "memory": {
    "total_bytes": 17179869184, "used_bytes": 8796093022, "available_bytes": 8383776162,
    "usage_percent": 51.2, "cached_bytes": 4294967296, "buffers_bytes": 268435456,
    "swap_total_bytes": 2147483648, "swap_used_bytes": 0, "swap_percent": 0.0
  },
  "disks": {
    "filesystems": [{ "mountpoint": "/", "device": "/dev/nvme0n1p2", "fstype": "ext4",
                      "total_bytes": 0, "used_bytes": 0, "free_bytes": 0, "usage_percent": 62.0 }],
    "io": [{ "device": "nvme0n1", "read_bytes_per_sec": 0, "write_bytes_per_sec": 0,
             "read_ops_per_sec": 0, "write_ops_per_sec": 0, "busy_percent": 1.2 }]
  },
  "network": {
    "interfaces": [{
      "name": "wlan0", "is_up": true, "speed_mbps": null, "mtu": 1500, "addresses": ["192.168.1.20"],
      "rx_bytes": 0, "tx_bytes": 0, "rx_packets": 0, "tx_packets": 0,
      "rx_errors": 0, "tx_errors": 0, "rx_dropped": 0, "tx_dropped": 0,
      "rx_bytes_per_sec": 2400000, "tx_bytes_per_sec": 410000,
      "rx_packets_per_sec": 1800, "tx_packets_per_sec": 1200,
      "errors_per_sec": 0, "drops_per_sec": 0
    }],
    "tcp_states": { "ESTABLISHED": 42, "LISTEN": 8, "TIME_WAIT": 3 }
  },
  "sensors": { "temperatures": [{ "chip": "coretemp", "label": "Package id 0", "kind": "cpu",
                                  "current_c": 52.0, "high_c": 90.0, "critical_c": 100.0 }] },
  "processes": { "total": 321, "running": 2, "top_cpu": [/* ProcessInfo */], "top_memory": [] },
  "host": { "uptime_seconds": 299700.5, "boot_time": "2026-09-29T22:45:00+00:00" },
  "agent": { "version": "1.0.0", "cpu_percent": 0.4, "memory_rss_bytes": 38000000,
             "collection_duration_ms": 31.2, "queue_size": 0, "failed_requests_total": 0,
             "dropped_samples_total": 0, "collector_errors": [] }
}
```

### Semantics an implementation must follow

* **Rates are computed by the agent** from counter deltas over the real
  elapsed interval. A counter that *decreases* (reset/wrap) yields rate `0`
  for that interval, never a negative value.
* **Memory "used"** = `MemTotal − MemAvailable` (page cache is not "used").
* **CPU usage** = non-idle share of jiffies over the interval; `iowait` counts as idle.
* **Process CPU %** is relative to one core (can exceed 100).
* **Interfaces** should exclude loopback and virtual bridge/veth devices so
  traffic is not double-counted (the server sums all reported interfaces).
* **Disk I/O** should report whole physical disks only (not partitions or
  device-mapper devices) to avoid double counting.
* Missing data is *omitted or null*, never invented: no sensors → `"temperatures": []`.
* Command lines must have credentials redacted before sending.

### Limits

Every list and string is bounded (e.g. ≤ 1024 cores, ≤ 128 interfaces,
≤ 50 processes per list, command lines ≤ 512 chars). Requests over 4 MiB are
refused. Unknown fields are **ignored**, so a newer agent can talk to an older
server; a breaking change increments `schema_version`.

### System information

Static facts (`hostname`, `os_name`, `kernel`, `architecture`, `cpu_model`,
core counts, `memory_total_bytes`, `boot_time`, `agent_version`) are sent in
the batch envelope's `system_info` on start-up and then hourly, not with every
sample.
