import { Table, Text } from "@mantine/core";

import type { StatsResponse } from "../../types/api";
import { formatMetric } from "../../utils/format";

const LABELS: Record<string, string> = {
  cpu_percent: "CPU",
  memory_percent: "Memory",
  disk_percent_max: "Fullest disk",
  net_rx_bps: "Network RX",
  net_tx_bps: "Network TX",
  temperature_max_c: "Temperature",
  load_1m: "Load (1m)",
};

export function StatsTable({ stats }: { stats: StatsResponse }) {
  return (
    <>
      <Table.ScrollContainer minWidth={620}>
        <Table verticalSpacing={4} fz="sm">
          <Table.Thead>
            <Table.Tr>
              <Table.Th>Metric</Table.Th>
              <Table.Th ta="right">Average</Table.Th>
              <Table.Th ta="right">Min</Table.Th>
              <Table.Th ta="right">Max</Table.Th>
              <Table.Th ta="right">P50</Table.Th>
              <Table.Th ta="right">P95</Table.Th>
              <Table.Th ta="right">P99</Table.Th>
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody className="tabular">
            {stats.stats.map((s) => (
              <Table.Tr key={s.metric}>
                <Table.Td fw={500}>{LABELS[s.metric] ?? s.metric}</Table.Td>
                {(["avg", "min", "max", "p50", "p95", "p99"] as const).map((k) => (
                  <Table.Td key={k} ta="right">
                    {formatMetric(s.metric, s[k])}
                  </Table.Td>
                ))}
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
      </Table.ScrollContainer>
      {!stats.percentiles_exact && (
        <Text size="xs" c="dimmed" mt={4}>
          This range is older than raw-sample retention and is served from {stats.source} rollups. Percentiles cannot
          be derived from pre-aggregated data, so they are not shown.
        </Text>
      )}
    </>
  );
}
