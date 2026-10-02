import {
  Alert,
  Anchor,
  Breadcrumbs,
  Card,
  Group,
  Loader,
  SimpleGrid,
  Stack,
  Tabs,
  Text,
  Title,
} from "@mantine/core";
import { IconAlertCircle } from "@tabler/icons-react";
import { useState } from "react";
import { Link, useParams } from "react-router-dom";

import { AlertTable } from "../components/AlertTable";
import { ChartCard } from "../components/ChartCard";
import { CoreGrid } from "../components/machine/CoreGrid";
import { InterfaceTable } from "../components/machine/InterfaceTable";
import { ProcessTable } from "../components/machine/ProcessTable";
import { SensorTable } from "../components/machine/SensorTable";
import { StatsTable } from "../components/machine/StatsTable";
import { StorageTables } from "../components/machine/StorageTables";
import { SystemInfoCard } from "../components/machine/SystemInfoCard";
import { StatTile } from "../components/StatTile";
import { StatusBadge } from "../components/StatusBadge";
import { LIVE_RANGES, TimeRangePicker, type Range } from "../components/TimeRangePicker";
import type { ChartRow, Series } from "../charts/TimeSeriesChart";
import { TimeSeriesChart } from "../charts/TimeSeriesChart";
import { useAsync } from "../hooks/useAsync";
import { useLive, useLiveEvents, useNow } from "../hooks/useLive";
import { useMachineHistory } from "../hooks/useMachineHistory";
import { api } from "../services/api";
import { SERIES } from "../theme";
import type { Agent, LatestSample, MetricName } from "../types/api";
import {
  formatBitRate,
  formatByteRate,
  formatCelsius,
  formatDuration,
  formatNumber,
  formatPercent,
  timeAgo,
} from "../utils/format";

const STAT_METRICS: MetricName[] = [
  "cpu_percent",
  "memory_percent",
  "disk_percent_max",
  "net_rx_bps",
  "net_tx_bps",
  "temperature_max_c",
  "load_1m",
];

const s = (key: MetricName, label: string, slot: number): Series => ({ key, label, color: SERIES[slot]! });

function LiveTiles({ latest, agent }: { latest?: LatestSample; agent: Agent }) {
  const sum = latest?.summary ?? agent.latest ?? {};
  const mem = latest?.details.memory;
  return (
    <SimpleGrid cols={{ base: 2, sm: 3, lg: 6 }}>
      <StatTile
        label="CPU"
        value={formatPercent(sum.cpu_percent)}
        percent={sum.cpu_percent}
        hint={`load ${formatNumber(sum.load_1m, 2)} · ${latest?.details.cpu.logical_cores ?? "?"} cores`}
      />
      <StatTile
        label="Memory"
        value={formatPercent(sum.memory_percent)}
        percent={sum.memory_percent}
        hint={mem ? `swap ${formatPercent(mem.swap_percent)}` : undefined}
      />
      <StatTile label="Fullest disk" value={formatPercent(sum.disk_percent_max)} percent={sum.disk_percent_max} />
      <StatTile
        label="Network"
        value={formatBitRate((sum.net_rx_bps ?? 0) + (sum.net_tx_bps ?? 0))}
        hint={`↓ ${formatBitRate(sum.net_rx_bps)} · ↑ ${formatBitRate(sum.net_tx_bps)}`}
      />
      <StatTile label="Temperature" value={formatCelsius(sum.temperature_max_c)} hint="hottest sensor" />
      <StatTile
        label="Uptime"
        value={formatDuration(sum.uptime_seconds)}
        hint={`${formatNumber(sum.process_count, 0)} processes`}
      />
    </SimpleGrid>
  );
}

function Charts({ rows, range }: { rows: ChartRow[]; range: Range }) {
  const longRange = range === "7d" || range === "30d";
  const common = { data: rows, longRange };
  return (
    <SimpleGrid cols={{ base: 1, lg: 2 }}>
      <ChartCard title="CPU usage">
        <TimeSeriesChart {...common} series={[s("cpu_percent", "CPU", 0)]} format={(v) => formatPercent(v, 0)} domain={[0, 100]} ariaLabel="CPU usage over time" />
      </ChartCard>
      <ChartCard title="Memory">
        <TimeSeriesChart
          {...common}
          series={[s("memory_percent", "RAM", 0), s("swap_percent", "Swap", 1)]}
          format={(v) => formatPercent(v, 0)}
          domain={[0, 100]}
          ariaLabel="Memory and swap usage over time"
        />
      </ChartCard>
      <ChartCard title="Network throughput" subtitle="All monitored interfaces">
        <TimeSeriesChart
          {...common}
          series={[s("net_rx_bps", "Received", 0), s("net_tx_bps", "Transmitted", 1)]}
          format={formatBitRate}
          ariaLabel="Network throughput over time"
        />
      </ChartCard>
      <ChartCard title="Disk I/O">
        <TimeSeriesChart
          {...common}
          series={[s("disk_read_bps", "Read", 0), s("disk_write_bps", "Write", 1)]}
          format={formatByteRate}
          ariaLabel="Disk read and write throughput over time"
        />
      </ChartCard>
      <ChartCard title="Packets">
        <TimeSeriesChart
          {...common}
          series={[s("net_rx_pps", "RX packets/s", 0), s("net_tx_pps", "TX packets/s", 1)]}
          format={(v) => formatNumber(v, 0)}
          ariaLabel="Packets per second over time"
        />
      </ChartCard>
      <ChartCard title="Network errors & drops" subtitle="Per second, all interfaces">
        <TimeSeriesChart
          {...common}
          series={[s("net_errors_ps", "Errors/s", 0), s("net_drops_ps", "Drops/s", 1)]}
          format={(v) => formatNumber(v, 2)}
          ariaLabel="Network errors and dropped packets over time"
        />
      </ChartCard>
      <ChartCard title="Load average">
        <TimeSeriesChart
          {...common}
          series={[s("load_1m", "1 min", 0), s("load_5m", "5 min", 1), s("load_15m", "15 min", 2)]}
          format={(v) => formatNumber(v, 2)}
          ariaLabel="Load average over time"
        />
      </ChartCard>
      <ChartCard title="Temperature" subtitle="Hottest sensor">
        <TimeSeriesChart
          {...common}
          series={[s("temperature_max_c", "Hottest sensor", 0)]}
          format={(v) => (v == null ? "—" : `${v.toFixed(0)} °C`)}
          ariaLabel="Maximum temperature over time"
        />
      </ChartCard>
    </SimpleGrid>
  );
}

export function MachinePage() {
  const { id = "" } = useParams();
  const [range, setRange] = useState<Range>("15m");
  const now = useNow();
  const live = useLive();
  const agent = useAsync(() => api.agent(id), [id], 30_000);
  const latest = useAsync(() => api.latest(id), [id]);
  const alerts = useAsync(() => api.alerts({ agent_id: id, limit: "25" }), [id]);
  const stats = useAsync(() => api.stats(id, { range }, STAT_METRICS), [id, range], 60_000);
  const { rows, history } = useMachineHistory(id, range);

  useLiveEvents((event) => {
    if (event.type === "sample" && event.agent_id === id) latest.reload();
    if (event.type === "alert" && event.alert.agent_id === id) {
      alerts.reload();
      agent.reload();
    }
    if (event.type === "agent_status" && event.agent_id === id) agent.reload();
    if (event.type === "resync") {
      agent.reload();
      alerts.reload();
      history.reload();
    }
  });

  if (agent.error) {
    return (
      <Alert color="red" icon={<IconAlertCircle />} title="Machine not found">
        {agent.error.message}
      </Alert>
    );
  }
  if (!agent.data) return <Loader m="xl" />;
  const a = agent.data;
  const status = live.status[id] === "offline" ? "offline" : a.status;
  const details = latest.data?.details;
  const lastSeen = latest.data?.timestamp ?? a.last_seen_at;

  return (
    <Stack>
      <Breadcrumbs>
        <Anchor component={Link} to="/" size="sm">
          Overview
        </Anchor>
        <Text size="sm">{a.display_name}</Text>
      </Breadcrumbs>
      <Group justify="space-between" align="flex-end">
        <div>
          <Group gap="sm">
            <Title order={3}>{a.display_name}</Title>
            <StatusBadge status={status} />
          </Group>
          <Text size="sm" c="dimmed">
            {a.agent_id} · last heartbeat {timeAgo(lastSeen, now)}
            {a.active_alerts > 0 && ` · ${a.active_alerts} active alert${a.active_alerts > 1 ? "s" : ""}`}
          </Text>
        </div>
        <TimeRangePicker value={range} onChange={setRange} />
      </Group>

      {a.status === "pending" ? (
        <Alert icon={<IconAlertCircle />} title="Waiting for the first sample">
          This machine is registered but its agent has not reported yet. See the Machines page for setup steps.
        </Alert>
      ) : (
        <>
          <LiveTiles latest={latest.data} agent={a} />
          <Text size="xs" c="dimmed">
            {LIVE_RANGES.has(range) ? "Live: updates every sample. " : "Refreshes every minute. "}
            {history.data &&
              `Source: ${history.data.source === "raw" ? "raw samples" : `${history.data.source} rollups`}, ${history.data.bucket_seconds}s buckets.`}
          </Text>
          <Charts rows={rows} range={range} />
          {stats.data && (
            <ChartCard title={`Statistics · last ${range}`}>
              <StatsTable stats={stats.data} />
            </ChartCard>
          )}
        </>
      )}

      {details && (
        <Card>
          <Tabs defaultValue="processes" keepMounted={false}>
            <Tabs.List mb="sm">
              <Tabs.Tab value="processes">Processes</Tabs.Tab>
              <Tabs.Tab value="network">Network</Tabs.Tab>
              <Tabs.Tab value="storage">Storage</Tabs.Tab>
              <Tabs.Tab value="cpu">CPU cores</Tabs.Tab>
              <Tabs.Tab value="sensors">Sensors</Tabs.Tab>
            </Tabs.List>
            <Tabs.Panel value="processes">
              <ProcessTable processes={details.processes} />
            </Tabs.Panel>
            <Tabs.Panel value="network">
              <InterfaceTable network={details.network} />
            </Tabs.Panel>
            <Tabs.Panel value="storage">
              <StorageTables disks={details.disks} />
            </Tabs.Panel>
            <Tabs.Panel value="cpu">
              <CoreGrid cpu={details.cpu} />
            </Tabs.Panel>
            <Tabs.Panel value="sensors">
              <SensorTable sensors={details.sensors.temperatures} />
            </Tabs.Panel>
          </Tabs>
        </Card>
      )}

      <SystemInfoCard agent={a} latest={latest.data} />

      <ChartCard title="Alerts for this machine">
        <AlertTable
          alerts={alerts.data ?? []}
          showMachine={false}
          now={now}
          onAcknowledge={(alert) => void api.acknowledge(alert.id).then(alerts.reload)}
        />
      </ChartCard>
    </Stack>
  );
}
