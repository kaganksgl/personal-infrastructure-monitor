import { Card, SimpleGrid, Stack, Text } from "@mantine/core";

import type { Agent, LatestSample } from "../../types/api";
import { formatBytes, formatDuration, formatTime } from "../../utils/format";

function Field({ label, value }: { label: string; value: string | null | undefined }) {
  return (
    <Stack gap={0}>
      <Text size="xs" c="dimmed">
        {label}
      </Text>
      <Text size="sm" style={{ wordBreak: "break-word" }}>
        {value || "—"}
      </Text>
    </Stack>
  );
}

export function SystemInfoCard({ agent, latest }: { agent: Agent; latest?: LatestSample }) {
  const info = agent.system_info;
  const cpu = latest?.details.cpu;
  const self = latest?.details.agent;
  return (
    <Card>
      <Text fw={600} size="sm" mb="sm">
        System
      </Text>
      <SimpleGrid cols={{ base: 2, md: 4 }} spacing="sm" verticalSpacing="sm">
        <Field label="Hostname" value={info?.hostname} />
        <Field label="Operating system" value={info?.os_name} />
        <Field label="Kernel" value={info?.kernel} />
        <Field label="Architecture" value={info?.architecture} />
        <Field label="CPU" value={info?.cpu_model} />
        <Field
          label="Cores"
          value={info ? `${info.cpu_physical_cores ?? "?"} physical / ${info.cpu_logical_cores} logical` : null}
        />
        <Field label="Frequency" value={cpu?.frequency_mhz ? `${(cpu.frequency_mhz / 1000).toFixed(2)} GHz` : null} />
        <Field label="Memory" value={info ? formatBytes(info.memory_total_bytes) : null} />
        <Field label="Uptime" value={formatDuration(latest?.summary.uptime_seconds)} />
        <Field label="Booted" value={info ? formatTime(info.boot_time, true) : null} />
        <Field label="Agent" value={info ? `v${info.agent_version} · ${info.runtime ?? ""}` : agent.agent_version} />
        <Field
          label="Agent footprint"
          value={
            self
              ? `${self.cpu_percent.toFixed(1)}% CPU · ${formatBytes(self.memory_rss_bytes)} · ${self.collection_duration_ms.toFixed(0)} ms/sample`
              : null
          }
        />
      </SimpleGrid>
      {self && (self.queue_size > 0 || self.failed_requests_total > 0 || self.collector_errors.length > 0) && (
        <Text size="xs" c="dimmed" mt="sm">
          Agent health: {self.queue_size} buffered · {self.failed_requests_total} failed uploads ·{" "}
          {self.dropped_samples_total} dropped
          {self.collector_errors.length > 0 && ` · failing collectors: ${self.collector_errors.join(", ")}`}
        </Text>
      )}
    </Card>
  );
}
