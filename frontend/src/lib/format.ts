// Display helpers. They never invent a number: missing values show as an em dash.

export const DASH = "—";

export function formatNumber(value: number | null | undefined, digits = 0): string {
  if (value === null || value === undefined || Number.isNaN(value)) return DASH;
  return value.toLocaleString("en-US", { minimumFractionDigits: digits, maximumFractionDigits: digits });
}

/** `value` is a fraction (0.153 -> "15.3%"). */
export function formatPercent(value: number | null | undefined, digits = 0): string {
  if (value === null || value === undefined || Number.isNaN(value)) return DASH;
  return `${(value * 100).toFixed(digits)}%`;
}

/** ISO text from the API ("2026-03-10T09:05:03.449Z") -> "10 Mar 2026, 09:05:03" in UTC, so it matches the log file. */
export function formatTime(iso: string | null | undefined, withSeconds = true): string {
  if (!iso) return DASH;
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleString("en-GB", {
    day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit",
    second: withSeconds ? "2-digit" : undefined, timeZone: "UTC", hour12: false,
  });
}

/** Only the clock part: "09:05:03". */
export function formatClock(iso: string | null | undefined): string {
  if (!iso) return DASH;
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit", second: "2-digit", timeZone: "UTC", hour12: false });
}

export function formatDuration(start: string | null, end: string | null): string {
  if (!start || !end) return DASH;
  const seconds = (new Date(end).getTime() - new Date(start).getTime()) / 1000;
  if (!Number.isFinite(seconds) || seconds < 0) return DASH;
  if (seconds < 60) return `${Math.round(seconds)} s`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes} min ${Math.round(seconds % 60)} s`;
  return `${Math.floor(minutes / 60)} h ${minutes % 60} min`;
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

export function humanize(name: string): string {
  const text = name.replace(/_/g, " ").trim();
  return text.charAt(0).toUpperCase() + text.slice(1);
}

export function plural(count: number, one: string, many = `${one}s`): string {
  return `${formatNumber(count)} ${count === 1 ? one : many}`;
}

/** Show any table cell value as text; empty values become a dash. */
export function formatCell(value: unknown): string {
  if (value === null || value === undefined || value === "") return DASH;
  if (typeof value === "number") return formatNumber(value, Number.isInteger(value) ? 0 : 2);
  return String(value);
}
