import {
  ActionIcon,
  Alert,
  Anchor,
  Button,
  Card,
  Group,
  Menu,
  Modal,
  Stack,
  Table,
  Text,
  TextInput,
  Title,
} from "@mantine/core";
import { IconDots, IconKey, IconPlus, IconTrash } from "@tabler/icons-react";
import { useState } from "react";
import type { FormEvent } from "react";
import { Link } from "react-router-dom";

import { AgentKeyModal } from "../components/AgentKeyModal";
import { StatusBadge } from "../components/StatusBadge";
import { useAgents } from "../hooks/useAgents";
import { useAuth } from "../hooks/useAuth";
import { useNow } from "../hooks/useLive";
import { api } from "../services/api";
import type { Agent, AgentCreated } from "../types/api";
import { formatTime, timeAgo } from "../utils/format";

function AddMachineModal({
  opened,
  onClose,
  onCreated,
}: {
  opened: boolean;
  onClose: () => void;
  onCreated: (created: AgentCreated) => void;
}) {
  const [agentId, setAgentId] = useState("");
  const [name, setName] = useState("");
  const [error, setError] = useState<string>();
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(undefined);
    try {
      onCreated(await api.createAgent(agentId.trim(), name.trim()));
      setAgentId("");
      setName("");
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal opened={opened} onClose={onClose} title="Add a machine">
      <form onSubmit={submit}>
        <Stack>
          {error && <Alert color="red">{error}</Alert>}
          <TextInput
            label="Agent ID"
            description="Lowercase letters, digits, '.', '_' or '-'. Usually the hostname."
            placeholder="web-server-1"
            value={agentId}
            onChange={(e) => setAgentId(e.currentTarget.value.toLowerCase())}
            pattern="^[a-z0-9][a-z0-9._-]{1,62}$"
            required
          />
          <TextInput
            label="Display name"
            placeholder="Web server (optional)"
            value={name}
            onChange={(e) => setName(e.currentTarget.value)}
          />
          <Group justify="flex-end">
            <Button variant="default" onClick={onClose}>
              Cancel
            </Button>
            <Button type="submit" loading={busy}>
              Create &amp; issue key
            </Button>
          </Group>
        </Stack>
      </form>
    </Modal>
  );
}

export function MachinesPage() {
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";
  const { data: agents, reload } = useAgents();
  const now = useNow();
  const [adding, setAdding] = useState(false);
  const [created, setCreated] = useState<AgentCreated | null>(null);
  const [deleting, setDeleting] = useState<Agent | null>(null);

  return (
    <Stack>
      <Group justify="space-between">
        <Title order={3}>Machines</Title>
        {isAdmin && (
          <Button leftSection={<IconPlus size={16} />} onClick={() => setAdding(true)}>
            Add machine
          </Button>
        )}
      </Group>
      <Card padding={0}>
        <Table.ScrollContainer minWidth={760}>
          <Table verticalSpacing="sm" highlightOnHover>
            <Table.Thead>
              <Table.Tr>
                <Table.Th>Machine</Table.Th>
                <Table.Th>Status</Table.Th>
                <Table.Th>Agent</Table.Th>
                <Table.Th>API key</Table.Th>
                <Table.Th>Last seen</Table.Th>
                <Table.Th>Registered</Table.Th>
                {isAdmin && <Table.Th aria-label="Actions" />}
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {(agents ?? []).map((a) => (
                <Table.Tr key={a.agent_id}>
                  <Table.Td>
                    <Anchor component={Link} to={`/machines/${a.agent_id}`} fw={600} size="sm">
                      {a.display_name}
                    </Anchor>
                    <Text size="xs" c="dimmed">
                      {a.agent_id}
                    </Text>
                  </Table.Td>
                  <Table.Td>
                    <StatusBadge status={a.status} />
                  </Table.Td>
                  <Table.Td>
                    <Text size="sm">{a.agent_version ? `v${a.agent_version}` : "—"}</Text>
                  </Table.Td>
                  <Table.Td>
                    <Text size="xs" ff="monospace">
                      {a.api_key_prefix}…
                    </Text>
                  </Table.Td>
                  <Table.Td>
                    <Text size="sm">{timeAgo(a.last_seen_at, now)}</Text>
                  </Table.Td>
                  <Table.Td>
                    <Text size="sm">{formatTime(a.created_at, true)}</Text>
                  </Table.Td>
                  {isAdmin && (
                    <Table.Td>
                      <Menu position="bottom-end">
                        <Menu.Target>
                          <ActionIcon variant="subtle" aria-label={`Actions for ${a.display_name}`}>
                            <IconDots size={16} />
                          </ActionIcon>
                        </Menu.Target>
                        <Menu.Dropdown>
                          <Menu.Item
                            leftSection={<IconKey size={14} />}
                            onClick={() => void api.rotateKey(a.agent_id).then(setCreated)}
                          >
                            Rotate API key
                          </Menu.Item>
                          <Menu.Item color="red" leftSection={<IconTrash size={14} />} onClick={() => setDeleting(a)}>
                            Delete machine
                          </Menu.Item>
                        </Menu.Dropdown>
                      </Menu>
                    </Table.Td>
                  )}
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        </Table.ScrollContainer>
        {agents?.length === 0 && (
          <Text p="md" size="sm" c="dimmed">
            No machines registered yet.
          </Text>
        )}
      </Card>

      <AddMachineModal
        opened={adding}
        onClose={() => setAdding(false)}
        onCreated={(c) => {
          setAdding(false);
          setCreated(c);
          reload();
        }}
      />
      <AgentKeyModal created={created} onClose={() => setCreated(null)} />
      <Modal opened={deleting !== null} onClose={() => setDeleting(null)} title="Delete machine?">
        <Text size="sm">
          This permanently deletes <b>{deleting?.display_name}</b> with all of its metrics and alerts, and revokes its
          API key.
        </Text>
        <Group justify="flex-end" mt="md">
          <Button variant="default" onClick={() => setDeleting(null)}>
            Cancel
          </Button>
          <Button
            color="red"
            onClick={() =>
              deleting &&
              void api.deleteAgent(deleting.agent_id).then(() => {
                setDeleting(null);
                reload();
              })
            }
          >
            Delete
          </Button>
        </Group>
      </Modal>
    </Stack>
  );
}
