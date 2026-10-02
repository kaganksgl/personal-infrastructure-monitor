import { Card, Group, Text } from "@mantine/core";
import type { ReactNode } from "react";

export function ChartCard({
  title,
  subtitle,
  children,
  action,
}: {
  title: string;
  subtitle?: ReactNode;
  children: ReactNode;
  action?: ReactNode;
}) {
  return (
    <Card>
      <Group justify="space-between" mb="xs" align="flex-start">
        <div>
          <Text fw={600} size="sm">
            {title}
          </Text>
          {subtitle && (
            <Text size="xs" c="dimmed">
              {subtitle}
            </Text>
          )}
        </div>
        {action}
      </Group>
      {children}
    </Card>
  );
}
