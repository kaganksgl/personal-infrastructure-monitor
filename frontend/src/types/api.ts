// Mirrors the backend's Pydantic response models (backend/app/schemas).

export type AgentStatus = "online" | "warning" | "offline" | "pending";
export type Severity = "info" | "warning" | "critical";

export interface User {
  id: number;
  username: string;
  role: "admin" | "viewer";
  created_at: string;
  last_login_at: string | null;
}

export interface AuthStatus {
  registration_open: boolean;
  has_users: boolean;
}

export interface SystemInfo {
  hostname: string;
  os_name: string;
  os_version: string | null;
  kernel: string;
  architecture: string;
  cpu_model: string | null;
  cpu_physical_cores: number | null;
  cpu_logical_cores: number;
  memory_total_bytes: number;
  boot_time: string;
  agent_version: string;
  runtime: string | null;
}

export type Summary = Record<string, number | null>;

export interface Agent {
  agent_id: string;
  display_name: string;
  status: AgentStatus;
  api_key_prefix: string;
  agent_version: string | null;
  system_info: SystemInfo | null;
  last_seen_at: string | null;
  created_at: string;
  active_alerts: number;
  latest: Summary | null;
}

export interface AgentCreated {
  agent: Agent;
  api_key: string;
}

export type MetricName =
  | "cpu_percent"
  | "load_1m"
  | "load_5m"
  | "load_15m"
  | "memory_percent"
  | "memory_used_bytes"
  | "swap_percent"
  | "disk_percent_max"
  | "disk_read_bps"
  | "disk_write_bps"
  | "net_rx_bps"
  | "net_tx_bps"
  | "net_rx_pps"
  | "net_tx_pps"
  | "net_errors_ps"
  | "net_drops_ps"
  | "temperature_max_c";

export type Point = { t: string } & Partial<Record<MetricName, number | null>>;

export interface HistoryResponse {
  agent_id: string;
  start: string;
  end: string;
  source: "raw" | "1h" | "1d";
  bucket_seconds: number;
  metrics: MetricName[];
  points: Point[];
}

export interface MetricStats {
  metric: MetricName;
  samples: number;
  avg: number | null;
  min: number | null;
  max: number | null;
  p50: number | null;
  p95: number | null;
  p99: number | null;
}

export interface StatsResponse {
  agent_id: string;
  source: "raw" | "1h" | "1d";
  percentiles_exact: boolean;
  stats: MetricStats[];
}

export interface Filesystem {
  mountpoint: string;
  device: string;
  fstype: string;
  total_bytes: number;
  used_bytes: number;
  free_bytes: number;
  usage_percent: number;
}

export interface DiskIO {
  device: string;
  read_bytes_per_sec: number;
  write_bytes_per_sec: number;
  read_ops_per_sec: number;
  write_ops_per_sec: number;
  busy_percent: number | null;
}

export interface NetworkInterface {
  name: string;
  is_up: boolean;
  speed_mbps: number | null;
  mtu: number | null;
  addresses: string[];
  rx_bytes: number;
  tx_bytes: number;
  rx_packets: number;
  tx_packets: number;
  rx_errors: number;
  tx_errors: number;
  rx_dropped: number;
  tx_dropped: number;
  rx_bytes_per_sec: number;
  tx_bytes_per_sec: number;
  rx_packets_per_sec: number;
  tx_packets_per_sec: number;
  errors_per_sec: number;
  drops_per_sec: number;
}

export interface TemperatureSensor {
  chip: string;
  label: string;
  kind: string;
  current_c: number;
  high_c: number | null;
  critical_c: number | null;
}

export interface ProcessInfo {
  pid: number;
  name: string;
  username: string | null;
  cpu_percent: number;
  memory_percent: number;
  memory_rss_bytes: number;
  status: string;
  num_threads: number | null;
  cmdline: string | null;
}

export interface SampleDetails {
  cpu: {
    usage_percent: number;
    per_core_percent: number[];
    logical_cores: number;
    physical_cores: number | null;
    frequency_mhz: number | null;
    load_1m: number;
    load_5m: number;
    load_15m: number;
    iowait_percent: number | null;
    steal_percent: number | null;
    context_switches_per_sec: number | null;
    interrupts_per_sec: number | null;
  };
  memory: {
    total_bytes: number;
    used_bytes: number;
    available_bytes: number;
    usage_percent: number;
    cached_bytes: number | null;
    buffers_bytes: number | null;
    swap_total_bytes: number;
    swap_used_bytes: number;
    swap_percent: number;
  };
  disks: { filesystems: Filesystem[]; io: DiskIO[] };
  network: { interfaces: NetworkInterface[]; tcp_states: Record<string, number> | null };
  sensors: { temperatures: TemperatureSensor[] };
  processes: {
    total: number;
    running: number | null;
    top_cpu: ProcessInfo[];
    top_memory: ProcessInfo[];
  };
  agent: {
    version: string;
    cpu_percent: number;
    memory_rss_bytes: number;
    collection_duration_ms: number;
    queue_size: number;
    failed_requests_total: number;
    dropped_samples_total: number;
    collector_errors: string[];
  };
}

export interface LatestSample {
  agent_id: string;
  timestamp: string;
  summary: Summary;
  details: SampleDetails;
}

export interface Alert {
  id: number;
  agent_id: string;
  rule_id: number | null;
  rule_name: string;
  metric: string;
  severity: Severity;
  status: "firing" | "resolved";
  message: string;
  value: number | null;
  threshold: number | null;
  started_at: string;
  resolved_at: string | null;
  acknowledged_at: string | null;
  acknowledged_by: string | null;
}

export interface AlertRule {
  id: number;
  name: string;
  metric: string;
  operator: ">" | "<";
  threshold: number;
  duration_seconds: number;
  severity: Severity;
  enabled: boolean;
  agent_id: string | null;
  created_at: string;
}

export interface CatalogEntry {
  name: MetricName;
  label: string;
  unit: string;
}

// ---- WebSocket events ----

export type LiveEvent =
  | { type: "hello" }
  | { type: "resync" }
  | { type: "agents_changed" }
  | { type: "sample"; agent_id: string; ts: string; summary: Summary }
  | { type: "agent_status"; agent_id: string; status: AgentStatus }
  | { type: "alert"; action: "fired" | "resolved" | "acknowledged"; alert: Alert };
