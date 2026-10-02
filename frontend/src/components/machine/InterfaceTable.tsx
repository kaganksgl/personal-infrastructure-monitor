import { Badge, Group, Table, Text } from "@mantine/core";
import { IconArrowDown, IconArrowUp } from "@tabler/icons-react";

import type { SampleDetails } from "../../types/api";
import { formatBitRate, formatBytes, formatNumber } from "../../utils/format";

export function InterfaceTable({ network }: { network: SampleDetails["network"] }) {
  return (
    <>
      <Table.ScrollContainer minWidth={900}>
        <Table striped verticalSpacing={4} fz="sm">
          <Table.Thead>
            <Table.Tr>
              <Table.Th>Interface</Table.Th>
              <Table.Th>Link</Table.Th>
              <Table.Th ta="right">RX rate</Table.Th>
              <Table.Th ta="right">TX rate</Table.Th>
              <Table.Th ta="right">Packets/s ↓ / ↑</Table.Th>
              <Table.Th ta="right">Total ↓ / ↑</Table.Th>
              <Table.Th ta="right">Errors</Table.Th>
              <Table.Th ta="right">Dropped</Table.Th>
              <Table.Th>Addresses</Table.Th>
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody className="tabular">
            {network.interfaces.map((i) => (
              <Table.Tr key={i.name}>
                <Table.Td fw={600}>{i.name}</Table.Td>
                <Table.Td>
                  <Group gap={4} wrap="nowrap">
                    {i.is_up ? (
                      <IconArrowUp size={14} color="var(--status-good)" aria-hidden />
                    ) : (
                      <IconArrowDown size={14} color="var(--status-critical)" aria-hidden />
                    )}
                    <Text size="sm">{i.is_up ? "Up" : "Down"}</Text>
                    <Text size="xs" c="dimmed">
                      {i.speed_mbps ? `${i.speed_mbps} Mb/s` : ""} {i.mtu ? `MTU ${i.mtu}` : ""}
                    </Text>
                  </Group>
                </Table.Td>
                <Table.Td ta="right">{formatBitRate(i.rx_bytes_per_sec)}</Table.Td>
                <Table.Td ta="right">{formatBitRate(i.tx_bytes_per_sec)}</Table.Td>
                <Table.Td ta="right">
                  {formatNumber(i.rx_packets_per_sec, 0)} / {formatNumber(i.tx_packets_per_sec, 0)}
                </Table.Td>
                <Table.Td ta="right">
                  {formatBytes(i.rx_bytes)} / {formatBytes(i.tx_bytes)}
                </Table.Td>
                <Table.Td ta="right">{formatNumber(i.rx_errors + i.tx_errors, 0)}</Table.Td>
                <Table.Td ta="right">{formatNumber(i.rx_dropped + i.tx_dropped, 0)}</Table.Td>
                <Table.Td>
                  <Text size="xs" ff="monospace">
                    {i.addresses.join(", ") || "—"}
                  </Text>
                </Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
      </Table.ScrollContainer>
      {network.tcp_states && (
        <Group gap="xs" mt="sm">
          <Text size="sm" fw={600}>
            TCP sockets:
          </Text>
          {Object.entries(network.tcp_states)
            .sort((a, b) => b[1] - a[1])
            .map(([state, count]) => (
              <Badge key={state} variant="default" tt="none">
                {state} {count}
              </Badge>
            ))}
        </Group>
      )}
    </>
  );
}
