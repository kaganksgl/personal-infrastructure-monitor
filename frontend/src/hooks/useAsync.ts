import { useCallback, useEffect, useRef, useState } from "react";

export interface AsyncState<T> {
  data: T | undefined;
  error: Error | undefined;
  loading: boolean;
  reload: () => void;
}

/**
 * Run an async loader, re-running when ``deps`` change and optionally every
 * ``refreshMs``. Stale responses from superseded calls are discarded.
 */
export function useAsync<T>(
  loader: () => Promise<T>,
  deps: unknown[],
  refreshMs?: number,
): AsyncState<T> {
  const [data, setData] = useState<T>();
  const [error, setError] = useState<Error>();
  const [loading, setLoading] = useState(true);
  const generation = useRef(0);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const load = useCallback(loader, deps);

  const run = useCallback(() => {
    const current = ++generation.current;
    setLoading(true);
    load()
      .then((result) => {
        if (current !== generation.current) return;
        setData(result);
        setError(undefined);
      })
      .catch((err: Error) => {
        if (current === generation.current) setError(err);
      })
      .finally(() => {
        if (current === generation.current) setLoading(false);
      });
  }, [load]);

  useEffect(() => {
    run();
    if (!refreshMs) return;
    const timer = window.setInterval(run, refreshMs);
    return () => window.clearInterval(timer);
  }, [run, refreshMs]);

  return { data, error, loading, reload: run };
}
