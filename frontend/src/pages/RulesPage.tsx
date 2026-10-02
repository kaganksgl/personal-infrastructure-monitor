import {
  ActionIcon,
  Alert,
  Button,
  Card,
  Group,
  Modal,
  NumberInput,
  Select,
  Stack,
  Switch,
  Table,
  Text,
  TextInput,
  Title,
} from "@mantine/core";
import { IconPencil, IconPlus, IconTrash } from "@tabler/icons-react";
import { useState } from "react";
import type { FormEvent } from "react";

import { SeverityBadge } from "../components/StatusBadge";
import { useAsync } from "../hooks/useAsync";
import { useAuth } from "../hooks/useAuth";
import { api } from "../services/api";
import type { AlertRule, Severity } from "../types/api";
import { formatMetric } from "../utils/format";

type Draft = Omit<AlertRule, "id" | "created_at">;
const EMPTY: Draft = {
  name: "",
  metric: "cpu_percent",
  operator: ">",
  threshold: 90,
  duration_seconds: 60,
  severity: "warning",
  enabled: true,
  agent_id: null,
};

function RuleModal({
  rule,
  onClose,
  onSaved,
}: {
  rule: AlertRule | Draft | null;
  onClose: () => void;
  onSaved: () => void;
}) {
  const catalog = useAsync(() => api.catalog(), []);
  const agents = useAsync(() => api.agents(), []);
  const [draft, setDraft] = useState<Draft>(rule ?? EMPTY);
  const [error, setError] = useState<string>();
  const existing = rule && "id" in rule ? rule : null;
  const set = <K extends keyof Draft>(key: K, value: Draft[K]) => setDraft((d) => ({ ...d, [key]: value }));
  const offline = draft.metric === "agent_offline";

  async function submit(event: FormEvent) {
    event.preventDefault();
    try {
      if (existing) {
        const { name, operator, threshold, duration_seconds, severity, enabled } = draft;
        await api.updateRule(existing.id, { name, operator, threshold, duration_seconds, severity, enabled });
      } else {
        await api.createRule(draft);
      }
      onSaved();
    } catch (err) {
      setError((err as Error).message);
    }
  }

  return (
    <Modal opened onClose={onClose} title={existing ? "Edit rule" : "New alert rule"}>
      <form onSubmit={submit}>
        <Stack>
          {error && <Alert color="red">{error}</Alert>}
          <TextInput label="Name" value={draft.name} onChange={(e) => set("name", e.currentTarget.value)} required />
          <Select
            label="Metric"
            disabled={existing !== null}
            value={draft.metric}
            onChange={(v) => v && set("metric", v)}
            data={[
              ...(catalog.data ?? []).map((m) => ({ value: m.name, label: m.label })),
              { value: "agent_offline", label: "Machine offline (heartbeat)" },
            ]}
          />
          {!offline && (
            <Group grow>
              <Select
                label="Condition"
                value={draft.operator}
                onChange={(v) => v && set("operator", v as ">" | "<")}
                data={[
                  { value: ">", label: "above" },
                  { value: "<", label: "below" },
                ]}
              />
              <NumberInput label="Threshold" value={draft.threshold} onChange={(v) => set("threshold", Number(v))} />
              <NumberInput
                label="For (seconds)"
                min={0}
                value={draft.duration_seconds}
                onChange={(v) => set("duration_seconds", Number(v))}
              />
            </Group>
          )}
          <Select
            label="Severity"
            value={draft.severity}
            onChange={(v) => v && set("severity", v as Severity)}
            data={["info", "warning", "critical"]}
          />
          <Select
            label="Applies to"
            disabled={existing !== null}
            value={draft.agent_id ?? ""}
            onChange={(v) => set("agent_id", v || null)}
            data={[
              { value: "", label: "All machines" },
              ...(agents.data ?? []).map((a) => ({ value: a.agent_id, label: a.display_name })),
            ]}
          />
          <Group justify="flex-end">
            <Button variant="default" onClick={onClose}>
              Cancel
            </Button>
            <Button type="submit">Save</Button>
          </Group>
        </Stack>
      </form>
    </Modal>
  );
}

function describe(rule: AlertRule): string {
  if (rule.metric === "agent_offline") return "No heartbeat within the offline window";
  const sustained = rule.duration_seconds ? ` for ${rule.duration_seconds}s` : "";
  return `${rule.metric} ${rule.operator} ${formatMetric(rule.metric, rule.threshold)}${sustained}`;
}

export function RulesPage() {
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";
  const rules = useAsync(() => api.rules(), []);
  const [editing, setEditing] = useState<AlertRule | Draft | null>(null);

  return (
    <Stack>
      <Group justify="space-between">
        <Title order={3}>Alert rules</Title>
        {isAdmin && (
          <Button leftSection={<IconPlus size={16} />} onClick={() => setEditing(EMPTY)}>
            New rule
          </Button>
        )}
      </Group>
      <Text size="sm" c="dimmed">
        Rules are evaluated on every incoming sample. A rule with a duration fires only after its condition has held
        continuously for that long, and resolves automatically once it clears.
      </Text>
      <Card padding={0}>
        <Table.ScrollContainer minWidth={700}>
          <Table verticalSpacing="sm">
            <Table.Thead>
              <Table.Tr>
                <Table.Th>Enabled</Table.Th>
                <Table.Th>Rule</Table.Th>
                <Table.Th>Condition</Table.Th>
                <Table.Th>Severity</Table.Th>
                <Table.Th>Scope</Table.Th>
                {isAdmin && <Table.Th aria-label="Actions" />}
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {(rules.data ?? []).map((rule) => (
                <Table.Tr key={rule.id}>
                  <Table.Td>
                    <Switch
                      checked={rule.enabled}
                      disabled={!isAdmin}
                      aria-label={`Enable ${rule.name}`}
                      onChange={(e) => void api.updateRule(rule.id, { enabled: e.currentTarget.checked }).then(rules.reload)}
                    />
                  </Table.Td>
                  <Table.Td fw={500}>{rule.name}</Table.Td>
                  <Table.Td>
                    <Text size="sm" ff="monospace">
                      {describe(rule)}
                    </Text>
                  </Table.Td>
                  <Table.Td>
                    <SeverityBadge severity={rule.severity} />
                  </Table.Td>
                  <Table.Td>{rule.agent_id ?? "All machines"}</Table.Td>
                  {isAdmin && (
                    <Table.Td>
                      <Group gap={4} wrap="nowrap">
                        <ActionIcon variant="subtle" aria-label={`Edit ${rule.name}`} onClick={() => setEditing(rule)}>
                          <IconPencil size={16} />
                        </ActionIcon>
                        <ActionIcon
                          variant="subtle"
                          color="red"
                          aria-label={`Delete ${rule.name}`}
                          onClick={() => void api.deleteRule(rule.id).then(rules.reload)}
                        >
                          <IconTrash size={16} />
                        </ActionIcon>
                      </Group>
                    </Table.Td>
                  )}
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        </Table.ScrollContainer>
      </Card>
      {editing && (
        <RuleModal
          rule={editing}
          onClose={() => setEditing(null)}
          onSaved={() => {
            setEditing(null);
            rules.reload();
          }}
        />
      )}
    </Stack>
  );
}
