import type { LivePoint } from "../services/live";
import type { MetricName, Point } from "../types/api";
import type { ChartRow } from "./TimeSeriesChart";

/** Convert API history points into chart rows (epoch-ms x values). */
export function historyRows(points: Point[], metrics: MetricName[]): ChartRow[] {
  return points.map((p) => {
    const row: ChartRow = { t: new Date(p.t).getTime() };
    for (const m of metrics) row[m] = p[m] ?? null;
    return row;
  });
}

/**
 * Rows from live points, restricted to ``windowMs``, with a null row inserted
 * where the gap between samples suggests the machine stopped reporting.
 */
export function liveRows(
  points: readonly LivePoint[],
  metrics: MetricName[],
  windowMs: number,
  now = Date.now(),
): ChartRow[] {
  const rows: ChartRow[] = [];
  let previous: number | undefined;
  for (const p of points) {
    if (p.t < now - windowMs) continue;
    if (previous !== undefined && p.t - previous > 30_000) {
      rows.push(Object.fromEntries([["t", previous + 1], ...metrics.map((m) => [m, null])]) as ChartRow);
    }
    const row: ChartRow = { t: p.t };
    for (const m of metrics) row[m] = p.summary[m] ?? null;
    rows.push(row);
    previous = p.t;
  }
  return rows;
}

/**
 * Pivot one metric across several machines into rows keyed by agent ID.
 * Samples are aligned to ``bucketMs`` because agents report at slightly
 * different instants.
 */
export function fleetRows(
  pointsByAgent: Readonly<Record<string, readonly LivePoint[]>>,
  agentIds: string[],
  pick: (summary: LivePoint["summary"]) => number | null,
  windowMs: number,
  bucketMs = 5000,
  now = Date.now(),
): ChartRow[] {
  const buckets = new Map<number, ChartRow>();
  for (const id of agentIds) {
    for (const p of pointsByAgent[id] ?? []) {
      if (p.t < now - windowMs) continue;
      const t = Math.floor(p.t / bucketMs) * bucketMs;
      const row = buckets.get(t) ?? ({ t } as ChartRow);
      row[id] = pick(p.summary);
      buckets.set(t, row);
    }
  }
  return [...buckets.values()].sort((a, b) => a.t - b.t);
}
