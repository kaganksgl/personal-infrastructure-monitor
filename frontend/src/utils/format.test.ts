import { describe, expect, it } from "vitest";

import { formatBitRate, formatBytes, formatDuration, formatMetric, formatPercent, timeAgo } from "./format";

describe("formatters", () => {
  it("formats bytes with binary prefixes", () => {
    expect(formatBytes(0)).toBe("0 B");
    expect(formatBytes(1536)).toBe("1.5 KiB");
    expect(formatBytes(16 * 1024 ** 3)).toBe("16.0 GiB");
    expect(formatBytes(null)).toBe("—");
  });

  it("formats network rates as bits per second", () => {
    expect(formatBitRate(125_000)).toBe("1.00 Mbps");
    expect(formatBitRate(6_000_000)).toBe("48.0 Mbps");
    expect(formatBitRate(150)).toBe("1.20 kbps");
    expect(formatBitRate(undefined)).toBe("—");
  });

  it("formats durations compactly", () => {
    expect(formatDuration(42)).toBe("42s");
    expect(formatDuration(3 * 86400 + 11 * 3600)).toBe("3d 11h");
    expect(formatDuration(3720)).toBe("1h 2m");
  });

  it("dispatches by metric unit", () => {
    expect(formatMetric("cpu_percent", 37.44)).toBe("37.4%");
    expect(formatMetric("temperature_max_c", 85)).toBe("85.0 °C");
    expect(formatMetric("unknown_metric", 3)).toBe("3");
    expect(formatPercent(null)).toBe("—");
  });

  it("renders relative times", () => {
    const now = Date.parse("2026-10-03T12:00:00Z");
    expect(timeAgo("2026-10-03T11:59:58Z", now)).toBe("just now");
    expect(timeAgo("2026-10-03T11:58:00Z", now)).toBe("2m 0s ago");
    expect(timeAgo(null, now)).toBe("never");
  });
});
