import type { AgentStatus, LiveEvent, Point, Summary } from "../types/api";

export type ConnectionState = "connecting" | "open" | "closed";

export interface LivePoint {
  t: number; // epoch ms
  summary: Summary;
}

export interface LiveSnapshot {
  connection: ConnectionState;
  points: Readonly<Record<string, readonly LivePoint[]>>;
  status: Readonly<Record<string, AgentStatus>>;
}

type EventListener = (event: LiveEvent) => void;

const RETAIN_MS = 35 * 60 * 1000;
const PING_MS = 25_000;

/**
 * Single shared WebSocket connection for the whole dashboard.
 *
 * Holds a rolling ~30-minute window of summaries per machine so live charts
 * can render immediately when the user navigates between pages. Reconnects
 * with capped exponential backoff; after a reconnect or a server ``resync``
 * subscribers are told to refetch REST state, because events may have been
 * missed while disconnected.
 */
export class LiveStore {
  private socket: WebSocket | null = null;
  private snapshot: LiveSnapshot = { connection: "closed", points: {}, status: {} };
  private listeners = new Set<() => void>();
  private eventListeners = new Set<EventListener>();
  private attempts = 0;
  private reconnectTimer: number | undefined;
  private pingTimer: number | undefined;
  private wanted = false;

  constructor(private readonly url: () => string = defaultUrl) {}

  subscribe = (listener: () => void): (() => void) => {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  };

  getSnapshot = (): LiveSnapshot => this.snapshot;

  onEvent(listener: EventListener): () => void {
    this.eventListeners.add(listener);
    return () => this.eventListeners.delete(listener);
  }

  connect(): void {
    this.wanted = true;
    if (this.socket) return;
    this.update({ connection: "connecting" });
    const socket = new WebSocket(this.url());
    this.socket = socket;
    socket.onopen = () => {
      const reconnected = this.attempts > 0;
      this.attempts = 0;
      this.update({ connection: "open" });
      this.pingTimer = window.setInterval(() => socket.send("ping"), PING_MS);
      if (reconnected) this.emit({ type: "resync" });
    };
    socket.onmessage = (message) => {
      try {
        this.handle(JSON.parse(message.data as string) as LiveEvent);
      } catch {
        // ignore malformed frames
      }
    };
    socket.onclose = (event) => {
      window.clearInterval(this.pingTimer);
      this.socket = null;
      this.update({ connection: "closed" });
      // 4401 = not authenticated: reconnecting would just fail again.
      if (this.wanted && event.code !== 4401) this.scheduleReconnect();
    };
  }

  disconnect(): void {
    this.wanted = false;
    window.clearTimeout(this.reconnectTimer);
    this.socket?.close();
    this.socket = null;
  }

  /** Merge historical points (from the REST API) into the live window. */
  seed(agentId: string, points: Point[]): void {
    const seeded: LivePoint[] = points
      .filter((p) => p.cpu_percent != null)
      .map((p) => {
        const { t, ...summary } = p;
        return { t: new Date(t).getTime(), summary: summary as Summary };
      });
    this.mergePoints(agentId, seeded);
  }

  private scheduleReconnect(): void {
    const delay = Math.min(30_000, 1000 * 2 ** this.attempts) * (0.5 + Math.random() / 2);
    this.attempts++;
    this.reconnectTimer = window.setTimeout(() => this.connect(), delay);
  }

  private handle(event: LiveEvent): void {
    if (event.type === "sample") {
      this.mergePoints(event.agent_id, [{ t: new Date(event.ts).getTime(), summary: event.summary }]);
    } else if (event.type === "agent_status") {
      this.update({ status: { ...this.snapshot.status, [event.agent_id]: event.status } });
    }
    this.emit(event);
  }

  private mergePoints(agentId: string, incoming: LivePoint[]): void {
    if (incoming.length === 0) return;
    const cutoff = Date.now() - RETAIN_MS;
    const byTime = new Map<number, LivePoint>();
    for (const p of this.snapshot.points[agentId] ?? []) byTime.set(p.t, p);
    for (const p of incoming) byTime.set(p.t, p);
    const merged = [...byTime.values()].filter((p) => p.t >= cutoff).sort((a, b) => a.t - b.t);
    this.update({ points: { ...this.snapshot.points, [agentId]: merged } });
  }

  private emit(event: LiveEvent): void {
    this.eventListeners.forEach((l) => l(event));
  }

  private update(patch: Partial<LiveSnapshot>): void {
    this.snapshot = { ...this.snapshot, ...patch };
    this.listeners.forEach((l) => l());
  }
}

function defaultUrl(): string {
  const scheme = window.location.protocol === "https:" ? "wss" : "ws";
  return `${scheme}://${window.location.host}/api/v1/ws`;
}

export const liveStore = new LiveStore();
