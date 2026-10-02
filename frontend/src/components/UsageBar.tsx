import { Group, Progress, Text } from "@mantine/core";

import { formatPercent } from "../utils/format";

export function UsageBar({ value, label }: { value: number | null | undefined; label: string }) {
  if (value == null) return <Text size="sm" c="dimmed">—</Text>;
  const color =
    value >= 90 ? "var(--status-critical)" : value >= 75 ? "var(--status-warning)" : "var(--series-1)";
  return (
    <Group gap={8} wrap="nowrap">
      <Progress value={value} color={color} size="sm" w={70} aria-label={`${label} ${value.toFixed(0)}%`} />
      <Text size="sm" className="tabular" w={52}>
        {formatPercent(value)}
      </Text>
    </Group>
  );
}
