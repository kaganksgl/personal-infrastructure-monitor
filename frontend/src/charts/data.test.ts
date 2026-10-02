import { describe, expect, it } from "vitest";

import type { LivePoint } from "../services/live";
import { fleetRows, historyRows, liveRows } from "./data";

const point = (t: number, cpu: number): LivePoint => ({ t, summary: { cpu_percent: cpu } });

describe("chart data", () => {
  it("converts API history to epoch rows", () => {
    const rows = historyRows([{ t: "2026-10-03T10:00:00Z", cpu_percent: 12 }], ["cpu_percent", "net_rx_bps"]);
    expect(rows).toEqual([{ t: Date.parse("2026-10-03T10:00:00Z"), cpu_percent: 12, net_rx_bps: null }]);
  });

  it("inserts a null row across reporting gaps so lines break", () => {
    const now = 1_000_000;
    const rows = liveRows([point(now - 100_000, 10), point(now - 95_000, 11), point(now - 5_000, 12)], ["cpu_percent"], 600_000, now);
    expect(rows.map((r) => r.cpu_percent)).toEqual([10, 11, null, 12]);
  });

  it("drops points outside the window", () => {
    const now = 1_000_000;
    const rows = liveRows([point(now - 700_000, 1), point(now - 1_000, 2)], ["cpu_percent"], 600_000, now);
    expect(rows).toHaveLength(1);
  });

  it("pivots several machines into aligned buckets", () => {
    const now = 100_000;
    const rows = fleetRows(
      { a: [point(90_001, 10)], b: [point(92_500, 20)] },
      ["a", "b"],
      (s) => s.cpu_percent ?? null,
      60_000,
      5000,
      now,
    );
    expect(rows).toEqual([{ t: 90_000, a: 10, b: 20 }]);
  });
});
