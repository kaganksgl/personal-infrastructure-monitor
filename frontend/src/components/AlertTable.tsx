import { Anchor, Button, Group, Table, Text } from "@mantine/core";
import { IconCheck, IconCircleCheck, IconFlame } from "@tabler/icons-react";
import { Link } from "react-router-dom";

import type { Alert } from "../types/api";
import { formatDuration, formatTime } from "../utils/format";
import { SeverityBadge } from "./StatusBadge";

interface Props {
  alerts: Alert[];
  onAcknowledge?: (alert: Alert) => void;
  showMachine?: boolean;
  now: number;
}

export function AlertTable({ alerts, onAcknowledge, showMachine = true, now }: Props) {
  if (alerts.length === 0) {
    return (
      <Text size="sm" c="dimmed" p="md">
        No alerts match.
      </Text>
    );
  }
  return (
    <Table.ScrollContainer minWidth={820}>
      <Table verticalSpacing="xs" fz="sm" highlightOnHover>
        <Table.Thead>
          <Table.Tr>
            <Table.Th>Severity</Table.Th>
            <Table.Th>State</Table.Th>
            {showMachine && <Table.Th>Machine</Table.Th>}
            <Table.Th>Alert</Table.Th>
            <Table.Th>Started</Table.Th>
            <Table.Th>Duration</Table.Th>
            <Table.Th>Acknowledged</Table.Th>
          </Table.Tr>
        </Table.Thead>
        <Table.Tbody>
          {alerts.map((a) => {
            const end = a.resolved_at ? new Date(a.resolved_at).getTime() : now;
            return (
              <Table.Tr key={a.id}>
                <Table.Td>
                  <SeverityBadge severity={a.severity} />
                </Table.Td>
                <Table.Td>
                  <Group gap={4} wrap="nowrap">
                    {a.status === "firing" ? (
                      <IconFlame size={15} color="var(--status-critical)" aria-hidden />
                    ) : (
                      <IconCircleCheck size={15} color="var(--status-good)" aria-hidden />
                    )}
                    <Text size="sm">{a.status === "firing" ? "Firing" : "Resolved"}</Text>
                  </Group>
                </Table.Td>
                {showMachine && (
                  <Table.Td>
                    <Anchor component={Link} to={`/machines/${a.agent_id}`} size="sm">
                      {a.agent_id}
                    </Anchor>
                  </Table.Td>
                )}
                <Table.Td>
                  <Text size="sm" fw={500}>
                    {a.rule_name}
                  </Text>
                  <Text size="xs" c="dimmed">
                    {a.message}
                  </Text>
                </Table.Td>
                <Table.Td className="tabular">{formatTime(a.started_at, true)}</Table.Td>
                <Table.Td className="tabular">
                  {formatDuration((end - new Date(a.started_at).getTime()) / 1000)}
                </Table.Td>
                <Table.Td>
                  {a.acknowledged_at ? (
                    <Text size="xs" c="dimmed">
                      by {a.acknowledged_by ?? "?"}
                      <br />
                      {formatTime(a.acknowledged_at, true)}
                    </Text>
                  ) : onAcknowledge ? (
                    <Button
                      size="compact-xs"
                      variant="default"
                      leftSection={<IconCheck size={12} />}
                      onClick={() => onAcknowledge(a)}
                    >
                      Acknowledge
                    </Button>
                  ) : (
                    "—"
                  )}
                </Table.Td>
              </Table.Tr>
            );
          })}
        </Table.Tbody>
      </Table>
    </Table.ScrollContainer>
  );
}
