import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError, api, onUnauthorized } from "./api";

function mockFetch(status: number, body: unknown) {
  const fn = vi.fn().mockResolvedValue(
    new Response(body === undefined ? null : JSON.stringify(body), { status }),
  );
  vi.stubGlobal("fetch", fn);
  return fn;
}

afterEach(() => vi.unstubAllGlobals());

describe("api client", () => {
  it("sends the CSRF header and same-origin credentials", async () => {
    const fetchMock = mockFetch(201, { agent: {}, api_key: "iwk_x" });
    await api.createAgent("web-1", "Web");
    const [url, init] = fetchMock.mock.calls[0]!;
    expect(url).toBe("/api/v1/agents");
    expect(init.method).toBe("POST");
    expect(init.credentials).toBe("same-origin");
    expect(init.headers["X-Requested-With"]).toBe("infrawatch");
    expect(JSON.parse(init.body)).toEqual({ agent_id: "web-1", display_name: "Web" });
  });

  it("builds history queries from a window and metric list", async () => {
    const fetchMock = mockFetch(200, { points: [] });
    await api.history("db 1", { range: "1h" }, ["cpu_percent", "net_rx_bps"]);
    expect(fetchMock.mock.calls[0]![0]).toBe("/api/v1/metrics/db%201?metrics=cpu_percent%2Cnet_rx_bps&range=1h");
  });

  it("surfaces backend error details and notifies on expired sessions", async () => {
    mockFetch(401, { detail: "Not authenticated" });
    const listener = vi.fn();
    const unsubscribe = onUnauthorized(listener);
    await expect(api.agents()).rejects.toEqual(new ApiError(401, "Not authenticated"));
    expect(listener).toHaveBeenCalledOnce();
    unsubscribe();
  });

  it("does not treat a failed login as an expired session", async () => {
    mockFetch(401, { detail: "Invalid username or password" });
    const listener = vi.fn();
    const unsubscribe = onUnauthorized(listener);
    await expect(api.login("a", "b")).rejects.toThrow("Invalid username or password");
    expect(listener).not.toHaveBeenCalled();
    unsubscribe();
  });

  it("returns undefined for 204 responses", async () => {
    mockFetch(204, undefined);
    await expect(api.deleteAgent("web-1")).resolves.toBeUndefined();
  });
});
