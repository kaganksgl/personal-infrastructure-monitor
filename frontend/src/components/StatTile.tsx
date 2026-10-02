import { Card, Group, Progress, Text } from "@mantine/core";
import type { ReactNode } from "react";

interface Props {
  label: string;
  value: string;
  hint?: ReactNode;
  /** 0-100; renders a usage bar under the value. */
  percent?: number | null;
  icon?: ReactNode;
}

function barColor(percent: number): string {
  if (percent >= 90) return "var(--status-critical)";
  if (percent >= 75) return "var(--status-warning)";
  return "var(--series-1)";
}

export function StatTile({ label, value, hint, percent, icon }: Props) {
  return (
    <Card padding="sm">
      <Group justify="space-between" gap={4} wrap="nowrap">
        <Text size="xs" c="dimmed" tt="uppercase" fw={600} style={{ letterSpacing: 0.4 }}>
          {label}
        </Text>
        {icon}
      </Group>
      <Text fz={26} fw={600} lh={1.2} mt={4}>
        {value}
      </Text>
      {percent != null && (
        <Progress
          value={Math.min(100, percent)}
          color={barColor(percent)}
          size="sm"
          mt={6}
          aria-label={`${label} ${percent.toFixed(0)}%`}
        />
      )}
      {hint && (
        <Text size="xs" c="dimmed" mt={6}>
          {hint}
        </Text>
      )}
    </Card>
  );
}
