import { Alert, Button, Card, Group, Loader, SimpleGrid, Stack, Text, Title } from "@mantine/core";
import { IconAlertCircle, IconServer } from "@tabler/icons-react";
import { useMemo } from "react";
import { Link } from "react-router-dom";

import { ChartCard } from "../components/ChartCard";
import { EmptyState } from "../components/EmptyState";
import { MachineTable } from "../components/MachineTable";
import { StatTile } from "../components/StatTile";
import { fleetRows } from "../charts/data";
import { TimeSeriesChart } from "../charts/TimeSeriesChart";
import { useAgents, useSeedHistory } from "../hooks/useAgents";
import { useLive, useNow } from "../hooks/useLive";
import { SERIES } from "../theme";
import type { Agent } from "../types/api";
import { formatBitRate, formatPercent } from "../utils/format";

const WINDOW_MS = 15 * 60_000;
const MAX_SERIES = SERIES.length;

function average(values: (number | null | undefined)[]): number | null {
  const present = values.filter((v): v is number => v != null);
  return present.length ? present.reduce((a, b) => a + b, 0) / present.length : null;
}

function FleetTiles({ agents }: { agents: Agent[] }) {
  const reporting = agents.filter((a) => a.status === "online" || a.status === "warning");
  const latest = reporting.map((a) => a.latest).filter(Boolean);
  const cpu = average(latest.map((l) => l?.cpu_percent));
  const mem = average(latest.map((l) => l?.memory_percent));
  const disk = Math.max(...latest.map((l) => l?.disk_percent_max ?? 0), 0);
  const rx = latest.reduce((sum, l) => sum + (l?.net_rx_bps ?? 0), 0);
  const tx = latest.reduce((sum, l) => sum + (l?.net_tx_bps ?? 0), 0);
  const warnings = agents.filter((a) => a.status === "warning").length;
  const offline = agents.filter((a) => a.status === "offline").length;

  return (
    <SimpleGrid cols={{ base: 2, sm: 3, lg: 5 }}>
      <StatTile
        label="Online machines"
        value={`${reporting.length} / ${agents.length}`}
        hint={`${warnings} warning · ${offline} offline`}
      />
      <StatTile label="Avg CPU" value={formatPercent(cpu)} percent={cpu} hint="across online machines" />
      <StatTile label="Avg memory" value={formatPercent(mem)} percent={mem} hint="across online machines" />
      <StatTile label="Fullest disk" value={formatPercent(disk)} percent={disk} hint="highest filesystem usage" />
      <StatTile label="Network" value={formatBitRate(rx + tx)} hint={`↓ ${formatBitRate(rx)} · ↑ ${formatBitRate(tx)}`} />
    </SimpleGrid>
  );
}

export function OverviewPage() {
  const { data: agents, error, loading } = useAgents();
  const live = useLive();
  const now = useNow();
  // Stable colour per machine: index in the full, alphabetically sorted fleet,
  // so hiding/adding a machine never repaints the others.
  const ordered = useMemo(
    () => [...(agents ?? [])].sort((a, b) => a.agent_id.localeCompare(b.agent_id)),
    [agents],
  );
  const charted = ordered.slice(0, MAX_SERIES);
  useSeedHistory(charted.map((a) => a.agent_id));

  const series = charted.map((a, i) => ({ key: a.agent_id, label: a.display_name, color: SERIES[i]! }));
  const ids = charted.map((a) => a.agent_id);
  const cpuRows = fleetRows(live.points, ids, (s) => s.cpu_percent ?? null, WINDOW_MS, 5000, now);
  const netRows = useMemo(() => {
    const rx = fleetRows(live.points, ids, (s) => s.net_rx_bps ?? null, WINDOW_MS, 5000, now);
    const tx = fleetRows(live.points, ids, (s) => s.net_tx_bps ?? null, WINDOW_MS, 5000, now);
    const total = (row: Record<string, number | null>) =>
      ids.reduce((sum, id) => sum + (row[id] ?? 0), 0);
    const txByT = new Map(tx.map((r) => [r.t, total(r)]));
    return rx.map((r) => ({ t: r.t, rx: total(r), tx: txByT.get(r.t) ?? null }));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [live.points, ids.join(","), now]);

  if (loading && !agents) return <Loader m="xl" />;
  if (error) {
    return (
      <Alert color="red" icon={<IconAlertCircle />} title="Could not load machines">
        {error.message}
      </Alert>
    );
  }
  if (!agents?.length) {
    return (
      <EmptyState icon={<IconServer />} title="No machines yet">
        Register a machine, install the agent on it, and live metrics will appear here.
        <Group justify="center" mt="md">
          <Button component={Link} to="/machines">
            Add a machine
          </Button>
        </Group>
      </EmptyState>
    );
  }

  return (
    <Stack>
      <Title order={3}>Fleet overview</Title>
      <FleetTiles agents={agents} />
      <SimpleGrid cols={{ base: 1, lg: 2 }}>
        <ChartCard title="CPU usage by machine" subtitle="Last 15 minutes · live">
          <TimeSeriesChart
            data={cpuRows}
            series={series}
            format={(v) => formatPercent(v, 0)}
            domain={[0, 100]}
            ariaLabel="CPU usage per machine over the last 15 minutes"
          />
        </ChartCard>
        <ChartCard title="Fleet network traffic" subtitle="Sum of all machines · last 15 minutes · live">
          <TimeSeriesChart
            data={netRows}
            series={[
              { key: "rx", label: "Received", color: SERIES[0]! },
              { key: "tx", label: "Transmitted", color: SERIES[1]! },
            ]}
            format={formatBitRate}
            ariaLabel="Total network throughput over the last 15 minutes"
          />
        </ChartCard>
      </SimpleGrid>
      {ordered.length > MAX_SERIES && (
        <Text size="xs" c="dimmed">
          Charts show the first {MAX_SERIES} machines; open a machine for its own charts.
        </Text>
      )}
      <Card padding={0}>
        <MachineTable agents={agents} now={now} />
      </Card>
    </Stack>
  );
}
