import { SegmentedControl } from "@mantine/core";

export const RANGES = ["5m", "15m", "1h", "6h", "24h", "7d", "30d"] as const;
export type Range = (typeof RANGES)[number];

export const RANGE_MS: Record<Range, number> = {
  "5m": 5 * 60_000,
  "15m": 15 * 60_000,
  "1h": 3_600_000,
  "6h": 6 * 3_600_000,
  "24h": 24 * 3_600_000,
  "7d": 7 * 86_400_000,
  "30d": 30 * 86_400_000,
};

/** Ranges short enough to be fed by the live WebSocket stream. */
export const LIVE_RANGES: ReadonlySet<Range> = new Set(["5m", "15m"]);

export function TimeRangePicker({ value, onChange }: { value: Range; onChange: (r: Range) => void }) {
  return (
    <SegmentedControl
      size="xs"
      value={value}
      onChange={(v) => onChange(v as Range)}
      data={RANGES.map((r) => ({ value: r, label: r }))}
      aria-label="Time range"
    />
  );
}
