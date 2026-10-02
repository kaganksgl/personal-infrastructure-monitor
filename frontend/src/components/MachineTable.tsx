import { Anchor, Table, Text } from "@mantine/core";
import { Link } from "react-router-dom";

import type { Agent } from "../types/api";
import { formatBitRate, formatCelsius, timeAgo } from "../utils/format";
import { StatusBadge } from "./StatusBadge";
import { UsageBar } from "./UsageBar";

export function MachineTable({ agents, now }: { agents: Agent[]; now: number }) {
  return (
    <Table.ScrollContainer minWidth={820}>
      <Table highlightOnHover verticalSpacing="xs">
        <Table.Thead>
          <Table.Tr>
            <Table.Th>Machine</Table.Th>
            <Table.Th>Status</Table.Th>
            <Table.Th>CPU</Table.Th>
            <Table.Th>Memory</Table.Th>
            <Table.Th>Disk</Table.Th>
            <Table.Th>Network ↓ / ↑</Table.Th>
            <Table.Th>Temp</Table.Th>
            <Table.Th>Last seen</Table.Th>
          </Table.Tr>
        </Table.Thead>
        <Table.Tbody>
          {agents.map((a) => (
            <Table.Tr key={a.agent_id}>
              <Table.Td>
                <Anchor component={Link} to={`/machines/${a.agent_id}`} fw={600} size="sm">
                  {a.display_name}
                </Anchor>
                <Text size="xs" c="dimmed">
                  {a.system_info?.os_name ?? a.agent_id}
                </Text>
              </Table.Td>
              <Table.Td>
                <StatusBadge status={a.status} />
              </Table.Td>
              <Table.Td>
                <UsageBar value={a.latest?.cpu_percent} label="CPU" />
              </Table.Td>
              <Table.Td>
                <UsageBar value={a.latest?.memory_percent} label="Memory" />
              </Table.Td>
              <Table.Td>
                <UsageBar value={a.latest?.disk_percent_max} label="Disk" />
              </Table.Td>
              <Table.Td className="tabular">
                <Text size="sm">
                  {formatBitRate(a.latest?.net_rx_bps)} / {formatBitRate(a.latest?.net_tx_bps)}
                </Text>
              </Table.Td>
              <Table.Td className="tabular">
                <Text size="sm">{formatCelsius(a.latest?.temperature_max_c)}</Text>
              </Table.Td>
              <Table.Td>
                <Text size="sm" c="dimmed">
                  {timeAgo(a.last_seen_at, now)}
                </Text>
              </Table.Td>
            </Table.Tr>
          ))}
        </Table.Tbody>
      </Table>
    </Table.ScrollContainer>
  );
}
