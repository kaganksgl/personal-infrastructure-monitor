import { Table, Text } from "@mantine/core";
import { IconAlertTriangle } from "@tabler/icons-react";

import type { TemperatureSensor } from "../../types/api";
import { formatCelsius } from "../../utils/format";

function isHot(s: TemperatureSensor): boolean {
  const limit = s.high_c ?? s.critical_c;
  return limit != null && s.current_c >= limit;
}

export function SensorTable({ sensors }: { sensors: TemperatureSensor[] }) {
  if (sensors.length === 0) {
    return (
      <Text size="sm" c="dimmed">
        This machine exposes no temperature sensors (common in VMs and containers).
      </Text>
    );
  }
  return (
    <Table.ScrollContainer minWidth={560}>
      <Table striped verticalSpacing={4} fz="sm">
        <Table.Thead>
          <Table.Tr>
            <Table.Th>Type</Table.Th>
            <Table.Th>Chip</Table.Th>
            <Table.Th>Sensor</Table.Th>
            <Table.Th ta="right">Current</Table.Th>
            <Table.Th ta="right">High</Table.Th>
            <Table.Th ta="right">Critical</Table.Th>
          </Table.Tr>
        </Table.Thead>
        <Table.Tbody className="tabular">
          {sensors.map((s) => (
            <Table.Tr key={`${s.chip}-${s.label}`}>
              <Table.Td tt="uppercase" fz="xs" fw={600}>
                {s.kind}
              </Table.Td>
              <Table.Td>{s.chip}</Table.Td>
              <Table.Td>{s.label}</Table.Td>
              <Table.Td ta="right" fw={isHot(s) ? 700 : undefined}>
                {isHot(s) && <IconAlertTriangle size={13} color="var(--status-warning)" aria-label="above high threshold" />}{" "}
                {formatCelsius(s.current_c)}
              </Table.Td>
              <Table.Td ta="right">{formatCelsius(s.high_c)}</Table.Td>
              <Table.Td ta="right">{formatCelsius(s.critical_c)}</Table.Td>
            </Table.Tr>
          ))}
        </Table.Tbody>
      </Table>
    </Table.ScrollContainer>
  );
}
