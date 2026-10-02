import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { LiveEvent } from "../types/api";
import { LiveStore } from "./live";

class FakeSocket {
  static instances: FakeSocket[] = [];
  onopen: (() => void) | null = null;
  onmessage: ((m: { data: string }) => void) | null = null;
  onclose: ((e: { code: number }) => void) | null = null;
  sent: string[] = [];
  constructor(public url: string) {
    FakeSocket.instances.push(this);
  }
  send(data: string) {
    this.sent.push(data);
  }
  close() {
    this.onclose?.({ code: 1000 });
  }
  deliver(event: LiveEvent) {
    this.onmessage?.({ data: JSON.stringify(event) });
  }
}

beforeEach(() => {
  FakeSocket.instances = [];
  vi.stubGlobal("WebSocket", FakeSocket);
  vi.useFakeTimers();
});
afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("LiveStore", () => {
  it("accumulates samples per machine and tracks status", () => {
    const store = new LiveStore(() => "ws://test/api/v1/ws");
    store.connect();
    const socket = FakeSocket.instances[0]!;
    socket.onopen?.();
    expect(store.getSnapshot().connection).toBe("open");

    const ts = new Date().toISOString();
    socket.deliver({ type: "sample", agent_id: "web-1", ts, summary: { cpu_percent: 42 } });
    socket.deliver({ type: "agent_status", agent_id: "web-1", status: "offline" });
    const snap = store.getSnapshot();
    expect(snap.points["web-1"]![0]!.summary.cpu_percent).toBe(42);
    expect(snap.status["web-1"]).toBe("offline");
  });

  it("deduplicates seeded history against live samples", () => {
    const store = new LiveStore(() => "ws://test");
    const t = new Date().toISOString();
    store.seed("a", [{ t, cpu_percent: 1 }]);
    store.seed("a", [{ t, cpu_percent: 2 }]);
    expect(store.getSnapshot().points["a"]).toHaveLength(1);
    expect(store.getSnapshot().points["a"]![0]!.summary.cpu_percent).toBe(2);
  });

  it("reconnects with backoff and asks listeners to resync", () => {
    const store = new LiveStore(() => "ws://test");
    const events: string[] = [];
    store.onEvent((e) => events.push(e.type));
    store.connect();
    FakeSocket.instances[0]!.onopen?.();
    FakeSocket.instances[0]!.onclose?.({ code: 1006 });
    expect(store.getSnapshot().connection).toBe("closed");

    vi.advanceTimersByTime(30_000);
    expect(FakeSocket.instances).toHaveLength(2);
    FakeSocket.instances[1]!.onopen?.();
    expect(events).toContain("resync");
  });

  it("does not reconnect when the server rejects the session", () => {
    const store = new LiveStore(() => "ws://test");
    store.connect();
    FakeSocket.instances[0]!.onclose?.({ code: 4401 });
    vi.advanceTimersByTime(60_000);
    expect(FakeSocket.instances).toHaveLength(1);
  });
});
