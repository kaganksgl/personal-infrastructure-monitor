import { useEffect, useRef, useSyncExternalStore } from "react";

import { liveStore, type LiveSnapshot } from "../services/live";
import type { LiveEvent } from "../types/api";

export function useLive(): LiveSnapshot {
  return useSyncExternalStore(liveStore.subscribe, liveStore.getSnapshot);
}

/** Call ``handler`` for every live event; the latest handler is always used. */
export function useLiveEvents(handler: (event: LiveEvent) => void): void {
  const ref = useRef(handler);
  useEffect(() => {
    ref.current = handler;
  });
  useEffect(() => liveStore.onEvent((event) => ref.current(event)), []);
}

/** Re-render periodically so relative times ("12s ago") stay current. */
export function useNow(intervalMs = 5000): number {
  return useSyncExternalStore(
    (notify) => {
      const timer = window.setInterval(notify, intervalMs);
      return () => window.clearInterval(timer);
    },
    () => Math.floor(Date.now() / intervalMs) * intervalMs,
  );
}
