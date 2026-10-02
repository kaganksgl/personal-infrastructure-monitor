import { Card, Group, SegmentedControl, Select, Stack, Title } from "@mantine/core";
import { useState } from "react";

import { AlertTable } from "../components/AlertTable";
import { useAsync } from "../hooks/useAsync";
import { useLiveEvents, useNow } from "../hooks/useLive";
import { api } from "../services/api";

export function AlertsPage() {
  const [status, setStatus] = useState("firing");
  const [severity, setSeverity] = useState<string | null>(null);
  const now = useNow();
  const alerts = useAsync(
    () =>
      api.alerts({
        limit: "200",
        ...(status !== "all" && { status }),
        ...(severity && { severity }),
      }),
    [status, severity],
    60_000,
  );
  useLiveEvents((event) => {
    if (event.type === "alert" || event.type === "resync") alerts.reload();
  });

  return (
    <Stack>
      <Title order={3}>Alerts</Title>
      <Group>
        <SegmentedControl
          value={status}
          onChange={setStatus}
          data={[
            { value: "firing", label: "Firing" },
            { value: "resolved", label: "Resolved" },
            { value: "all", label: "All" },
          ]}
          aria-label="Alert state"
        />
        <Select
          placeholder="Any severity"
          clearable
          value={severity}
          onChange={setSeverity}
          data={[
            { value: "critical", label: "Critical" },
            { value: "warning", label: "Warning" },
            { value: "info", label: "Info" },
          ]}
          w={160}
          aria-label="Severity filter"
        />
      </Group>
      <Card padding={0}>
        <AlertTable
          alerts={alerts.data ?? []}
          now={now}
          onAcknowledge={(alert) => void api.acknowledge(alert.id).then(alerts.reload)}
        />
      </Card>
    </Stack>
  );
}
