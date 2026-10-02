import { screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { renderWithProviders } from "../test/render";
import { SeverityBadge, StatusBadge } from "./StatusBadge";

describe("status badges", () => {
  it("always conveys state as text, not colour alone", () => {
    renderWithProviders(
      <>
        <StatusBadge status="offline" />
        <StatusBadge status="warning" />
        <SeverityBadge severity="critical" />
      </>,
    );
    expect(screen.getByText("Offline")).toBeInTheDocument();
    expect(screen.getByText("Warning")).toBeInTheDocument();
    expect(screen.getByText("Critical")).toBeInTheDocument();
  });
});
