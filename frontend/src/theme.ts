import { createTheme } from "@mantine/core";

export const theme = createTheme({
  primaryColor: "blue",
  fontFamily: 'system-ui, -apple-system, "Segoe UI", Roboto, sans-serif',
  fontFamilyMonospace: 'ui-monospace, "JetBrains Mono", "SFMono-Regular", Menlo, monospace',
  defaultRadius: "md",
  headings: { fontWeight: "600" },
  components: {
    Card: { defaultProps: { withBorder: true, padding: "md" } },
    Paper: { defaultProps: { withBorder: true } },
  },
});

/** Categorical colour per slot; assigned by a stable index, never by rank. */
export const SERIES = Array.from({ length: 8 }, (_, i) => `var(--series-${i + 1})`);

export const STATUS_COLOR = {
  online: "var(--status-good)",
  warning: "var(--status-warning)",
  offline: "var(--status-critical)",
  pending: "var(--status-muted)",
  info: "var(--series-1)",
  critical: "var(--status-critical)",
} as const;
