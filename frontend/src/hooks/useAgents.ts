import { useEffect, useMemo } from "react";

import { api } from "../services/api";
import { liveStore } from "../services/live";
import type { Agent } from "../types/api";
import { useAsync } from "./useAsync";
import { useLive, useLiveEvents } from "./useLive";

/**
 * Fleet list merged with live data: newest WebSocket summary and status
 * override the (periodically refreshed) REST snapshot.
 */
export function useAgents() {
  const state = useAsync(() => api.agents(), [], 60_000);
  const live = useLive();
  const { reload } = state;

  useLiveEvents((event) => {
    if (event.type === "agents_changed" || event.type === "resync") reload();
    if (event.type === "alert" && event.action !== "acknowledged") reload();
  });

  const agents = useMemo<Agent[] | undefined>(
    () =>
      state.data?.map((agent) => {
        const points = live.points[agent.agent_id];
        const newest = points?.[points.length - 1];
        const fresher = newest && (!agent.last_seen_at || newest.t > new Date(agent.last_seen_at).getTime());
        const liveStatus = live.status[agent.agent_id];
        let status = agent.status;
        if (liveStatus === "offline") status = "offline";
        else if (liveStatus === "online" && status !== "warning") status = "online";
        return {
          ...agent,
          status,
          latest: fresher ? { ...agent.latest, ...newest.summary } : agent.latest,
          last_seen_at: fresher ? new Date(newest.t).toISOString() : agent.last_seen_at,
        };
      }),
    [state.data, live],
  );
  return { ...state, data: agents };
}

/** Seed the live store with recent history so charts are populated on first paint. */
export function useSeedHistory(agentIds: string[], range = "15m") {
  const key = agentIds.join(",");
  useEffect(() => {
    for (const id of key ? key.split(",") : []) {
      api
        .history(id, { range }, ["cpu_percent", "memory_percent", "net_rx_bps", "net_tx_bps", "disk_percent_max"])
        .then((h) => liveStore.seed(id, h.points))
        .catch(() => undefined);
    }
  }, [key, range]);
}
