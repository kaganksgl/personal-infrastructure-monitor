import { Alert, Button, Code, CopyButton, Group, Modal, Stack, Text } from "@mantine/core";
import { IconAlertTriangle, IconCheck, IconCopy } from "@tabler/icons-react";

import type { AgentCreated } from "../types/api";

export function agentEnvFile(created: AgentCreated, origin: string): string {
  return [
    `SERVER_URL=${origin}`,
    `AGENT_ID=${created.agent.agent_id}`,
    `API_KEY=${created.api_key}`,
    "COLLECTION_INTERVAL=5",
  ].join("\n");
}

/** Shows a freshly issued API key. It is never retrievable again. */
export function AgentKeyModal({ created, onClose }: { created: AgentCreated | null; onClose: () => void }) {
  const env = created ? agentEnvFile(created, window.location.origin) : "";
  return (
    <Modal opened={created !== null} onClose={onClose} title="Agent credentials" size="lg">
      {created && (
        <Stack>
          <Alert color="yellow" icon={<IconAlertTriangle size={16} />}>
            This API key is shown only once. Only its hash is stored, so it cannot be recovered. Rotate the key
            if you lose it.
          </Alert>
          <Text size="sm">
            1. Save this as <Code>/etc/infrawatch/agent.env</Code> on <b>{created.agent.display_name}</b> (mode
            600):
          </Text>
          <Code block>{env}</Code>
          <CopyButton value={env}>
            {({ copied, copy }) => (
              <Button
                variant="default"
                leftSection={copied ? <IconCheck size={16} /> : <IconCopy size={16} />}
                onClick={copy}
              >
                {copied ? "Copied" : "Copy configuration"}
              </Button>
            )}
          </CopyButton>
          <Text size="sm">2. Install and verify the agent:</Text>
          <Code block>{`pip install ./agent
infrawatch-agent --config /etc/infrawatch/agent.env test
sudo systemctl enable --now infrawatch-agent`}</Code>
          <Group justify="flex-end">
            <Button onClick={onClose}>Done</Button>
          </Group>
        </Stack>
      )}
    </Modal>
  );
}
