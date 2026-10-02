import { Box, Group, Text } from "@mantine/core";
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { formatTime } from "../utils/format";

export interface Series {
  key: string;
  label: string;
  color: string;
}

export type ChartRow = { t: number } & Record<string, number | null>;

interface Props {
  data: ChartRow[];
  series: Series[];
  format: (value: number | null | undefined) => string;
  height?: number;
  /** Fixed y-domain, e.g. [0, 100] for percentages so scale is comparable over time. */
  domain?: [number, number | "auto"];
  /** Show dates on the axis for multi-day ranges. */
  longRange?: boolean;
  ariaLabel: string;
}

function ChartTooltip({
  active,
  payload,
  label,
  series,
  format,
}: {
  active?: boolean;
  payload?: { dataKey?: string | number; value?: number | null }[];
  label?: number;
  series: Series[];
  format: Props["format"];
}) {
  if (!active || !payload?.length || label == null) return null;
  return (
    <Box
      p="xs"
      style={{
        background: "var(--mantine-color-body)",
        border: "1px solid var(--mantine-color-default-border)",
        borderRadius: 6,
        boxShadow: "var(--mantine-shadow-sm)",
      }}
    >
      <Text size="xs" c="dimmed" mb={4}>
        {formatTime(label, true)}
      </Text>
      {series.map((s) => {
        const value = payload.find((p) => p.dataKey === s.key)?.value;
        return (
          <Group key={s.key} gap={6} wrap="nowrap" justify="space-between">
            <Group gap={6} wrap="nowrap">
              <Box w={10} h={2} style={{ background: s.color }} />
              <Text size="xs">{s.label}</Text>
            </Group>
            <Text size="xs" fw={600} className="tabular">
              {format(value)}
            </Text>
          </Group>
        );
      })}
    </Box>
  );
}

/**
 * Line chart for metric time series.
 *
 * One y-axis per chart (series in a chart always share a unit); null values
 * break the line so outages are visible as gaps instead of being bridged.
 */
export function TimeSeriesChart({
  data,
  series,
  format,
  height = 220,
  domain = [0, "auto"],
  longRange = false,
  ariaLabel,
}: Props) {
  const tickFormatter = (t: number) =>
    longRange
      ? new Date(t).toLocaleDateString(undefined, { month: "short", day: "numeric" })
      : new Date(t).toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });

  return (
    <Box role="img" aria-label={ariaLabel}>
      <ResponsiveContainer width="100%" height={height}>
        <LineChart data={data} margin={{ top: 8, right: 12, bottom: 0, left: 0 }}>
          <CartesianGrid stroke="var(--chart-grid)" vertical={false} />
          <XAxis
            dataKey="t"
            type="number"
            scale="time"
            domain={["dataMin", "dataMax"]}
            tickFormatter={tickFormatter}
            stroke="var(--chart-axis)"
            tick={{ fill: "var(--chart-ink-muted)", fontSize: 11 }}
            minTickGap={40}
          />
          <YAxis
            domain={domain}
            tickFormatter={(v: number) => format(v)}
            stroke="var(--chart-axis)"
            tick={{ fill: "var(--chart-ink-muted)", fontSize: 11 }}
            width={84}
            allowDecimals
          />
          <Tooltip
            content={<ChartTooltip series={series} format={format} />}
            cursor={{ stroke: "var(--chart-axis)", strokeWidth: 1 }}
            isAnimationActive={false}
          />
          {series.map((s) => (
            <Line
              key={s.key}
              dataKey={s.key}
              name={s.label}
              stroke={s.color}
              strokeWidth={2}
              dot={false}
              activeDot={{ r: 4, strokeWidth: 2, stroke: "var(--chart-surface)" }}
              connectNulls={false}
              isAnimationActive={false}
            />
          ))}
        </LineChart>
      </ResponsiveContainer>
      {series.length > 1 && (
        <Group gap="md" justify="center" mt={4} aria-hidden>
          {series.map((s) => (
            <Group key={s.key} gap={6}>
              <Box w={12} h={3} style={{ background: s.color, borderRadius: 2 }} />
              <Text size="xs" c="dimmed">
                {s.label}
              </Text>
            </Group>
          ))}
        </Group>
      )}
    </Box>
  );
}
