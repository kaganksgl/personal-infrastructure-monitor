import { Badge } from "@mantine/core";
import {
  IconAlertTriangle,
  IconCircleCheck,
  IconCircleX,
  IconClockHour4,
  IconInfoCircle,
} from "@tabler/icons-react";

import { STATUS_COLOR } from "../theme";
import type { AgentStatus, Severity } from "../types/api";

// Colour is never the only signal: each state has its own icon and text.
const AGENT = {
  online: { label: "Online", Icon: IconCircleCheck },
  warning: { label: "Warning", Icon: IconAlertTriangle },
  offline: { label: "Offline", Icon: IconCircleX },
  pending: { label: "Pending", Icon: IconClockHour4 },
} as const;

const SEVERITY = {
  info: { label: "Info", Icon: IconInfoCircle, color: STATUS_COLOR.info },
  warning: { label: "Warning", Icon: IconAlertTriangle, color: STATUS_COLOR.warning },
  critical: { label: "Critical", Icon: IconCircleX, color: STATUS_COLOR.critical },
} as const;

export function StatusBadge({ status }: { status: AgentStatus }) {
  const { label, Icon } = AGENT[status];
  return (
    <Badge
      variant="default"
      tt="none"
      leftSection={<Icon size={14} color={STATUS_COLOR[status]} aria-hidden />}
    >
      {label}
    </Badge>
  );
}

export function SeverityBadge({ severity }: { severity: Severity }) {
  const { label, Icon, color } = SEVERITY[severity];
  return (
    <Badge variant="default" tt="none" leftSection={<Icon size={14} color={color} aria-hidden />}>
      {label}
    </Badge>
  );
}
