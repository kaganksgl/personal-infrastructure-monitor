import type { MetricName } from "../types/api";

const BYTE_UNITS = ["B", "KiB", "MiB", "GiB", "TiB", "PiB"];

export function formatBytes(value: number | null | undefined, digits = 1): string {
  if (value == null || Number.isNaN(value)) return "—";
  let v = Math.abs(value);
  let i = 0;
  while (v >= 1024 && i < BYTE_UNITS.length - 1) {
    v /= 1024;
    i++;
  }
  return `${value < 0 ? "-" : ""}${v.toFixed(i === 0 ? 0 : digits)} ${BYTE_UNITS[i]}`;
}

export function formatByteRate(value: number | null | undefined): string {
  return value == null ? "—" : `${formatBytes(value)}/s`;
}

/** Network throughput in bits per second (decimal units), as link speeds are quoted. */
export function formatBitRate(bytesPerSec: number | null | undefined): string {
  if (bytesPerSec == null || Number.isNaN(bytesPerSec)) return "—";
  const bits = bytesPerSec * 8;
  const scaled = (v: number) => v.toFixed(v >= 100 ? 0 : v >= 10 ? 1 : 2);
  if (bits >= 1e9) return `${scaled(bits / 1e9)} Gbps`;
  if (bits >= 1e6) return `${scaled(bits / 1e6)} Mbps`;
  if (bits >= 1e3) return `${scaled(bits / 1e3)} kbps`;
  return `${bits.toFixed(0)} bps`;
}

export function formatPercent(value: number | null | undefined, digits = 1): string {
  return value == null || Number.isNaN(value) ? "—" : `${value.toFixed(digits)}%`;
}

export function formatNumber(value: number | null | undefined, digits = 1): string {
  if (value == null || Number.isNaN(value)) return "—";
  return value.toLocaleString(undefined, { maximumFractionDigits: digits });
}

export function formatCelsius(value: number | null | undefined): string {
  return value == null ? "—" : `${value.toFixed(1)} °C`;
}

export function formatDuration(totalSeconds: number | null | undefined): string {
  if (totalSeconds == null) return "—";
  const s = Math.max(0, Math.floor(totalSeconds));
  const d = Math.floor(s / 86400);
  const h = Math.floor((s % 86400) / 3600);
  const m = Math.floor((s % 3600) / 60);
  if (d > 0) return `${d}d ${h}h`;
  if (h > 0) return `${h}h ${m}m`;
  if (m > 0) return `${m}m ${s % 60}s`;
  return `${s}s`;
}

export function timeAgo(iso: string | null | undefined, now = Date.now()): string {
  if (!iso) return "never";
  const seconds = (now - new Date(iso).getTime()) / 1000;
  if (seconds < 5) return "just now";
  return `${formatDuration(seconds)} ago`;
}

export function formatTime(iso: string | number, withDate = false): string {
  const date = new Date(iso);
  return withDate
    ? date.toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" })
    : date.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

type Formatter = (v: number | null | undefined) => string;

const METRIC_FORMATTERS: Record<MetricName, Formatter> = {
  cpu_percent: formatPercent,
  memory_percent: formatPercent,
  swap_percent: formatPercent,
  disk_percent_max: formatPercent,
  memory_used_bytes: formatBytes,
  disk_read_bps: formatByteRate,
  disk_write_bps: formatByteRate,
  net_rx_bps: formatBitRate,
  net_tx_bps: formatBitRate,
  net_rx_pps: (v) => (v == null ? "—" : `${formatNumber(v)} pkt/s`),
  net_tx_pps: (v) => (v == null ? "—" : `${formatNumber(v)} pkt/s`),
  net_errors_ps: (v) => (v == null ? "—" : `${formatNumber(v, 2)}/s`),
  net_drops_ps: (v) => (v == null ? "—" : `${formatNumber(v, 2)}/s`),
  temperature_max_c: formatCelsius,
  load_1m: (v) => formatNumber(v, 2),
  load_5m: (v) => formatNumber(v, 2),
  load_15m: (v) => formatNumber(v, 2),
};

export function formatMetric(metric: string, value: number | null | undefined): string {
  const formatter = METRIC_FORMATTERS[metric as MetricName];
  return formatter ? formatter(value) : formatNumber(value);
}
