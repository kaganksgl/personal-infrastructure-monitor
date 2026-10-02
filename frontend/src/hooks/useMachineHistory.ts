import { useMemo } from "react";

import { historyRows, liveRows } from "../charts/data";
import type { ChartRow } from "../charts/TimeSeriesChart";
import { LIVE_RANGES, RANGE_MS, type Range } from "../components/TimeRangePicker";
import { api } from "../services/api";
import type { HistoryResponse, MetricName } from "../types/api";
import { useAsync } from "./useAsync";
import { useLive } from "./useLive";

export const DETAIL_METRICS: MetricName[] = [
  "cpu_percent",
  "load_1m",
  "load_5m",
  "load_15m",
  "memory_percent",
  "swap_percent",
  "disk_read_bps",
  "disk_write_bps",
  "net_rx_bps",
  "net_tx_bps",
  "net_rx_pps",
  "net_tx_pps",
  "net_errors_ps",
  "net_drops_ps",
  "temperature_max_c",
];

/**
 * Chart rows for one machine. Short ranges combine REST history with samples
 * streamed over the WebSocket since; long ranges are refreshed periodically.
 */
export function useMachineHistory(agentId: string, range: Range) {
  const isLive = LIVE_RANGES.has(range);
  const history = useAsync<HistoryResponse>(
    () => api.history(agentId, { range }, DETAIL_METRICS),
    [agentId, range],
    isLive ? undefined : 60_000,
  );
  const live = useLive();
  const points = live.points[agentId];

  const rows = useMemo<ChartRow[]>(() => {
    const base = history.data ? historyRows(history.data.points, DETAIL_METRICS) : [];
    if (!isLive || !points) return base;
    const last = base.length ? base[base.length - 1]!.t : 0;
    const appended = liveRows(points, DETAIL_METRICS, RANGE_MS[range]).filter((r) => r.t > last);
    const cutoff = Date.now() - RANGE_MS[range];
    return [...base, ...appended].filter((r) => r.t >= cutoff);
  }, [history.data, isLive, points, range]);

  return { rows, history };
}
