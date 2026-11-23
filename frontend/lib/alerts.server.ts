import "server-only";
import { ApiError } from "./api.server";
import type { AlertFilters, AlertPage, DeviceAlert } from "./alert-types";

function object(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}
function time(value: unknown): value is string {
  return typeof value === "string" && Number.isFinite(Date.parse(value));
}
function alert(value: unknown): value is DeviceAlert {
  if (!object(value)) return false;
  return ["alert_id", "device_id", "run_id", "rule_id", "message", "opening_event_id", "last_event_id"]
    .every(key => typeof value[key] === "string" && value[key].length > 0) &&
    Number.isSafeInteger(value.alert_order) && (value.alert_order as number) > 0 &&
    value.source === "simulator" && ["WARNING", "CRITICAL", "FAILURE"].includes(value.severity as string) &&
    ["ACTIVE", "ACKNOWLEDGED", "RESOLVED"].includes(value.status as string) &&
    ["opened_event_time", "last_event_time", "created_at", "updated_at"].every(key => time(value[key])) &&
    ["resolved_event_time", "acknowledged_at", "resolved_at"].every(key => value[key] === null || time(value[key])) &&
    (value.resolved_event_id === null || typeof value.resolved_event_id === "string") &&
    (value.resolution_reason === null || ["recovered", "superseded", "lifecycle_changed"].includes(value.resolution_reason as string));
}
async function request(path: string, method = "GET"): Promise<unknown> {
  try {
    if (!process.env.API_BASE_URL) throw new ApiError(503);
    const response = await fetch(new URL(path, process.env.API_BASE_URL), {
      method, cache: "no-store", redirect: "error", signal: AbortSignal.timeout(8_000),
    });
    if (!response.ok) {
      await response.body?.cancel().catch(() => undefined);
      throw new ApiError(response.status);
    }
    const data: unknown = await response.json();
    if (!object(data) || data.data_mode !== "simulated") throw new ApiError(502);
    return data;
  } catch (error) {
    if (error instanceof ApiError) throw error;
    throw new ApiError(503);
  }
}
export async function getAlerts(filters: AlertFilters = {}, deviceRoute = false): Promise<AlertPage> {
  const query = new URLSearchParams({ limit: String(filters.limit ?? 100) });
  if (filters.deviceId && !deviceRoute) query.set("device_id", filters.deviceId);
  for (const status of filters.statuses ?? []) query.append("status", status);
  if (filters.severity) query.set("severity", filters.severity);
  if (filters.before) query.set("before", filters.before);
  const path = deviceRoute && filters.deviceId
    ? `/api/v1/devices/${encodeURIComponent(filters.deviceId)}/alerts` : "/api/v1/alerts";
  const data = await request(`${path}?${query}`);
  if (!object(data) || !Array.isArray(data.items) || !data.items.every(alert) ||
      !(data.next_before === null || (Number.isSafeInteger(data.next_before) && (data.next_before as number) > 0)) ||
      data.items.some(item => (filters.deviceId && item.device_id !== filters.deviceId) ||
        (filters.statuses && !filters.statuses.includes(item.status)) ||
        (filters.severity && item.severity !== filters.severity))) throw new ApiError(502);
  return data as unknown as AlertPage;
}
export async function acknowledgeAlert(alertId: string): Promise<DeviceAlert> {
  const data = await request(`/api/v1/alerts/${encodeURIComponent(alertId)}/acknowledge`, "POST");
  if (!alert(data) || data.alert_id !== alertId) throw new ApiError(502);
  return data;
}
