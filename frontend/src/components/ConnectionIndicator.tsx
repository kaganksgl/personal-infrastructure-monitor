import { Group, Text, Tooltip } from "@mantine/core";
import { IconPlugConnected, IconPlugConnectedX, IconLoader2 } from "@tabler/icons-react";

import { useLive } from "../hooks/useLive";

export function ConnectionIndicator() {
  const { connection } = useLive();
  const config = {
    open: { label: "Live", Icon: IconPlugConnected, color: "var(--status-good)" },
    connecting: { label: "Connecting", Icon: IconLoader2, color: "var(--status-warning)" },
    closed: { label: "Disconnected", Icon: IconPlugConnectedX, color: "var(--status-critical)" },
  }[connection];
  return (
    <Tooltip label="Real-time updates over WebSocket">
      <Group gap={4} aria-live="polite">
        <config.Icon size={16} color={config.color} aria-hidden />
        <Text size="xs" c="dimmed">
          {config.label}
        </Text>
      </Group>
    </Tooltip>
  );
}
