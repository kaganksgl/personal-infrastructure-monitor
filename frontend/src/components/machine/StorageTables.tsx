import { Stack, Table, Text } from "@mantine/core";

import type { SampleDetails } from "../../types/api";
import { formatByteRate, formatBytes, formatNumber, formatPercent } from "../../utils/format";
import { UsageBar } from "../UsageBar";

export function StorageTables({ disks }: { disks: SampleDetails["disks"] }) {
  return (
    <Stack>
      <Table.ScrollContainer minWidth={700}>
        <Table striped verticalSpacing={4} fz="sm">
          <Table.Thead>
            <Table.Tr>
              <Table.Th>Mount</Table.Th>
              <Table.Th>Device</Table.Th>
              <Table.Th>Type</Table.Th>
              <Table.Th>Usage</Table.Th>
              <Table.Th ta="right">Used / Total</Table.Th>
              <Table.Th ta="right">Free</Table.Th>
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody className="tabular">
            {disks.filesystems.map((f) => (
              <Table.Tr key={f.mountpoint}>
                <Table.Td fw={600} ff="monospace">
                  {f.mountpoint}
                </Table.Td>
                <Table.Td ff="monospace">{f.device}</Table.Td>
                <Table.Td>{f.fstype}</Table.Td>
                <Table.Td>
                  <UsageBar value={f.usage_percent} label={`${f.mountpoint} usage`} />
                </Table.Td>
                <Table.Td ta="right">
                  {formatBytes(f.used_bytes)} / {formatBytes(f.total_bytes)}
                </Table.Td>
                <Table.Td ta="right">{formatBytes(f.free_bytes)}</Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
      </Table.ScrollContainer>
      {disks.io.length > 0 ? (
        <Table.ScrollContainer minWidth={600}>
          <Table striped verticalSpacing={4} fz="sm">
            <Table.Thead>
              <Table.Tr>
                <Table.Th>Block device</Table.Th>
                <Table.Th ta="right">Read</Table.Th>
                <Table.Th ta="right">Write</Table.Th>
                <Table.Th ta="right">IOPS read / write</Table.Th>
                <Table.Th ta="right">Busy</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody className="tabular">
              {disks.io.map((d) => (
                <Table.Tr key={d.device}>
                  <Table.Td fw={600} ff="monospace">
                    {d.device}
                  </Table.Td>
                  <Table.Td ta="right">{formatByteRate(d.read_bytes_per_sec)}</Table.Td>
                  <Table.Td ta="right">{formatByteRate(d.write_bytes_per_sec)}</Table.Td>
                  <Table.Td ta="right">
                    {formatNumber(d.read_ops_per_sec)} / {formatNumber(d.write_ops_per_sec)}
                  </Table.Td>
                  <Table.Td ta="right">{formatPercent(d.busy_percent)}</Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        </Table.ScrollContainer>
      ) : (
        <Text size="sm" c="dimmed">
          No physical block devices reported.
        </Text>
      )}
    </Stack>
  );
}
