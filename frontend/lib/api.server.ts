import "server-only";
import { HEALTH_STATES, type DeviceDetail, type DevicePage, type FleetSummary,
  type HistoryPage, type Reading } from "./api-types";

export class ApiError extends Error {
  constructor(public readonly status: number) {
    super(status === 404 ? "Device not found" : "Device data is currently unavailable");
    this.name = "ApiError";
  }
}

function object(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}
function count(value: unknown): value is number {
  return typeof value === "number" && Number.isSafeInteger(value) && value >= 0;
}
function reading(value: unknown): value is Reading {
  if (!object(value) || !count(value.ingestion_order) || value.ingestion_order === 0 ||
      !object(value.event)) return false;
  const event = value.event;
  const strings = ["event_id", "run_id", "device_id", "timestamp", "firmware_version"];
  const metrics = ["temperature_c", "power_draw_w", "cpu_utilization_pct",
    "memory_utilization_pct", "timing_jitter_ms"];
  return strings.every(key => typeof event[key] === "string" && event[key].length > 0) &&
    metrics.every(key => typeof event[key] === "number" && Number.isFinite(event[key])) &&
    count(event.error_count) && HEALTH_STATES.some(state => state === event.device_state) &&
    ["actuator_load_pct", "position_error_mm"].every(key => event[key] == null ||
      (typeof event[key] === "number" && Number.isFinite(event[key]))) &&
    Number.isFinite(Date.parse(event.timestamp as string));
}

async function request<T>(path: string, valid: (value: unknown) => boolean): Promise<T> {
  try {
    const base = process.env.API_BASE_URL;
    if (!base) throw new ApiError(503);
    const response = await fetch(new URL(path, base), {
      cache: "no-store", signal: AbortSignal.timeout(8_000), redirect: "error",
    });
    if (!response.ok) {
      await response.body?.cancel().catch(() => undefined);
      throw new ApiError(response.status);
    }
    const data: unknown = await response.json();
    if (!object(data) || data.data_mode !== "simulated" || !valid(data)) throw new ApiError(502);
    return data as T;
  } catch (error) {
    if (error instanceof ApiError) throw error;
    // Do not expose internal URLs, raw server errors, or connection configuration.
    throw new ApiError(503);
  }
}

export function getSummary(): Promise<FleetSummary> {
  return request("/api/v1/fleet/summary", value => {
    if (!object(value) || !count(value.total_devices) || !object(value.by_state)) return false;
    const byState = value.by_state;
    return HEALTH_STATES.every(state => count(byState[state]));
  });
}

export async function getDevices(): Promise<Reading[]> {
  const readings: Reading[] = [];
  const cursors = new Set<string>();
  const deviceIds = new Set<string>();
  let cursor = "";
  do {
    const query = new URLSearchParams({ limit: "1000", after_device: cursor });
    const page = await request<DevicePage>(`/api/v1/devices?${query}`, value => object(value) &&
      Array.isArray(value.items) && value.items.every(reading) &&
      (value.next_after_device === null || typeof value.next_after_device === "string"));
    for (const item of page.items) {
      if (deviceIds.has(item.event.device_id)) throw new ApiError(502);
      deviceIds.add(item.event.device_id);
      readings.push(item);
    }
    if (page.next_after_device === null) return readings;
    cursor = page.next_after_device;
    if (!cursor || cursors.has(cursor) || page.items.length === 0) throw new ApiError(502);
    cursors.add(cursor);
  } while (cursor);
  return readings;
}

export function getDevice(deviceId: string): Promise<DeviceDetail> {
  return request(`/api/v1/devices/${encodeURIComponent(deviceId)}`, value => reading(value) &&
    value.event.device_id === deviceId);
}

export function getHistory(deviceId: string, before?: string): Promise<HistoryPage> {
  const query = new URLSearchParams({ limit: "100" });
  if (before) query.set("before", before);
  return request(`/api/v1/devices/${encodeURIComponent(deviceId)}/telemetry?${query}`, value =>
    object(value) && Array.isArray(value.items) && value.items.every(item =>
      reading(item) && item.event.device_id === deviceId) &&
    (value.next_before === null || (count(value.next_before) && value.next_before > 0)));
}
