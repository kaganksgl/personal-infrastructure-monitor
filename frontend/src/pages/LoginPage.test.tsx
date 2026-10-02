import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AuthProvider } from "../hooks/useAuth";
import { renderWithProviders } from "../test/render";
import { LoginPage } from "./LoginPage";

function routeFetch(routes: Record<string, { status: number; body: unknown }>) {
  const fn = vi.fn(async (url: string) => {
    const route = routes[url] ?? { status: 404, body: { detail: "not found" } };
    return new Response(JSON.stringify(route.body), { status: route.status });
  });
  vi.stubGlobal("fetch", fn);
  return fn;
}

afterEach(() => vi.unstubAllGlobals());

describe("LoginPage", () => {
  it("offers first-user registration on an empty installation", async () => {
    routeFetch({
      "/api/v1/auth/me": { status: 401, body: { detail: "Not authenticated" } },
      "/api/v1/auth/status": { status: 200, body: { has_users: false, registration_open: true } },
    });
    renderWithProviders(
      <AuthProvider>
        <LoginPage />
      </AuthProvider>,
    );
    expect(await screen.findByText(/It will be the administrator/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Create account" })).toBeInTheDocument();
  });

  it("shows the server's error on failed sign-in", async () => {
    const fetchMock = routeFetch({
      "/api/v1/auth/me": { status: 401, body: { detail: "Not authenticated" } },
      "/api/v1/auth/status": { status: 200, body: { has_users: true, registration_open: false } },
      "/api/v1/auth/login": { status: 401, body: { detail: "Invalid username or password" } },
    });
    renderWithProviders(
      <AuthProvider>
        <LoginPage />
      </AuthProvider>,
    );
    await screen.findByText("Sign in to your monitoring dashboard");
    await userEvent.type(screen.getByLabelText(/Username/), "admin");
    await userEvent.type(screen.getByLabelText(/Password/), "wrong-password");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Invalid username or password");
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith("/api/v1/auth/login", expect.anything()));
  });
});
