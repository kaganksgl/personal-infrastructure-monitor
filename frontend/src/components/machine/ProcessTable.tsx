import { Group, SegmentedControl, Table, Text, Tooltip } from "@mantine/core";
import { useState } from "react";

import type { SampleDetails } from "../../types/api";
import { formatBytes, formatPercent } from "../../utils/format";

export function ProcessTable({ processes }: { processes: SampleDetails["processes"] }) {
  const [sort, setSort] = useState<"cpu" | "memory">("cpu");
  const rows = sort === "cpu" ? processes.top_cpu : processes.top_memory;
  return (
    <>
      <Group justify="space-between" mb="xs">
        <Text size="sm" c="dimmed">
          {processes.total} processes · {processes.running ?? "?"} running
        </Text>
        <SegmentedControl
          size="xs"
          value={sort}
          onChange={(v) => setSort(v as "cpu" | "memory")}
          data={[
            { value: "cpu", label: "Top CPU" },
            { value: "memory", label: "Top memory" },
          ]}
          aria-label="Sort processes by"
        />
      </Group>
      <Table.ScrollContainer minWidth={760}>
        <Table striped verticalSpacing={4} fz="sm">
          <Table.Thead>
            <Table.Tr>
              <Table.Th>PID</Table.Th>
              <Table.Th>Name</Table.Th>
              <Table.Th>User</Table.Th>
              <Table.Th ta="right">CPU %</Table.Th>
              <Table.Th ta="right">Memory</Table.Th>
              <Table.Th>Status</Table.Th>
              <Table.Th>Command</Table.Th>
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody className="tabular">
            {rows.map((p) => (
              <Table.Tr key={p.pid}>
                <Table.Td>{p.pid}</Table.Td>
                <Table.Td fw={500}>{p.name}</Table.Td>
                <Table.Td>{p.username ?? "—"}</Table.Td>
                <Table.Td ta="right">{formatPercent(p.cpu_percent)}</Table.Td>
                <Table.Td ta="right">
                  {formatBytes(p.memory_rss_bytes)} ({formatPercent(p.memory_percent)})
                </Table.Td>
                <Table.Td>{p.status}</Table.Td>
                <Table.Td maw={320}>
                  <Tooltip label={p.cmdline ?? ""} disabled={!p.cmdline} multiline maw={500}>
                    <Text size="xs" ff="monospace" truncate="end">
                      {p.cmdline ?? "—"}
                    </Text>
                  </Tooltip>
                </Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
      </Table.ScrollContainer>
      <Text size="xs" c="dimmed" mt={4}>
        CPU % is relative to one core (like top), so multi-threaded processes can exceed 100%. Secrets in
        command lines are redacted by the agent.
      </Text>
    </>
  );
}
