// Isolated browser-test fixture, never imported or shipped by the application.
import { createServer } from "node:http";
import { setTimeout } from "node:timers/promises";

let scenario = "default";
let alerts = [];
const states = ["HEALTHY", "WARNING", "CRITICAL", "FAILED"];
const runA = "11111111-1111-4111-8111-111111111111";
const runB = "22222222-2222-4222-8222-222222222222";
const deviceIds = ["device-001", "device-002", "device-003", "device-004"];

function episodes() {
  return [ ["device-002", "WARNING", "ACTIVE"], ["device-002", "WARNING", "ACKNOWLEDGED"],
    ["device-003", "CRITICAL", "ACTIVE"], ["device-002", "WARNING", "RESOLVED"],
    ["device-004", "FAILURE", "RESOLVED"] ].map(([device_id, severity, status], index) => ({
      alert_id: `aaaaaaaa-aaaa-4aaa-8aaa-${String(index + 1).padStart(12, "0")}`,
      alert_order: 5 - index, device_id, run_id: runA, rule_id: "simulator_state_v1", source: "simulator",
      severity, status, message: `Simulator reported ${severity === "FAILURE" ? "FAILED" : severity}.`,
      opening_event_id: runA, last_event_id: runB, resolved_event_id: status === "RESOLVED" ? runB : null,
      opened_event_time: "2026-01-01T00:00:05Z", last_event_time: "2026-01-01T00:00:10Z",
      resolved_event_time: status === "RESOLVED" ? "2026-01-01T00:00:10Z" : null,
      created_at: "2026-10-29T12:00:00Z", updated_at: "2026-10-29T12:01:00Z",
      acknowledged_at: status === "ACKNOWLEDGED" ? "2026-10-29T12:01:00Z" : null,
      resolved_at: status === "RESOLVED" ? "2026-10-29T12:02:00Z" : null,
      resolution_reason: status === "RESOLVED" ? "recovered" : null,
    }));
}

function reading(deviceId, index) {
  const device = deviceIds.indexOf(deviceId);
  const order = (device + 1) * 100 + index;
  return { ingestion_order: order, event: {
    event_id: `00000000-0000-4000-8000-${String(order).padStart(12, "0")}`,
    run_id: index === 4 ? runB : runA, device_id: deviceId,
    timestamp: index === 4 ? "2026-01-01T00:00:00Z" : `2026-01-01T00:00:${String(index * 5).padStart(2, "0")}Z`,
    firmware_version: "1.2.0", device_state: states[device], error_count: device,
    temperature_c: scenario === "updated" ? 65 : 40 + device * 10 + index,
    power_draw_w: 5 + index / 10, cpu_utilization_pct: 20 + index,
    memory_utilization_pct: 30 + index, timing_jitter_ms: index / 10,
    ...(device === 1 ? { actuator_load_pct: null, position_error_mm: 0 } : {}),
  } };
}

function send(response, status, body) {
  response.writeHead(status, { "Content-Type": "application/json" });
  response.end(JSON.stringify(body));
}
const error = (response, status) => send(response, status, {
  error: { code: status === 404 ? "not_found" : "service_unavailable", message: "Test API response" },
});

createServer(async (request, response) => {
  const url = new URL(request.url, "http://127.0.0.1");
  if (url.pathname === "/") return send(response, 200, { ready: true });
  if (request.method === "POST" && url.pathname.startsWith("/__test__/scenario/")) {
    scenario = url.pathname.split("/").pop();
    alerts = scenario.startsWith("alerts") ? episodes() : [];
    if (scenario === "alerts-conflict-single") alerts = alerts.slice(0, 1);
    return send(response, 200, { scenario });
  }
  if (scenario === "delay") await setTimeout(2500);
  if (scenario === "api-error") return error(response, 503);
  const alertRoute = /^\/api\/v1\/(?:alerts|devices\/([^/]+)\/alerts)$/.exec(url.pathname);
  if (alertRoute) {
    if (scenario === "alerts-error") return error(response, 503);
    if (scenario === "alerts-delay") await setTimeout(2500);
    const device = alertRoute[1] ? decodeURIComponent(alertRoute[1]) : url.searchParams.get("device_id");
    if (alertRoute[1] && !deviceIds.includes(device)) return error(response, 404);
    const statuses = url.searchParams.getAll("status");
    const severity = url.searchParams.get("severity");
    const before = Number(url.searchParams.get("before") ?? Infinity);
    const rows = alerts.filter(alert => (!device || alert.device_id === device) &&
      (!statuses.length || statuses.includes(alert.status)) && (!severity || alert.severity === severity) && alert.alert_order < before);
    const limit = Math.min(Number(url.searchParams.get("limit") ?? 100), 2);
    return send(response, 200, { data_mode: "simulated", items: rows.slice(0, limit),
      next_before: rows.length > limit ? rows[limit - 1].alert_order : null });
  }
  const acknowledge = /^\/api\/v1\/alerts\/([^/]+)\/acknowledge$/.exec(url.pathname);
  if (acknowledge && request.method === "POST") {
    await setTimeout(700);
    if (scenario === "alerts-ack-error") return error(response, 503);
    const alert = alerts.find(item => item.alert_id === acknowledge[1]);
    if (!alert) return error(response, 404);
    if (scenario.startsWith("alerts-conflict")) {
      Object.assign(alert, { status: "RESOLVED", resolved_event_id: runB,
        resolved_event_time: alert.last_event_time, resolved_at: "2026-10-29T12:02:00Z", resolution_reason: "recovered" });
    }
    if (alert.status === "RESOLVED") return send(response, 409, { error: { code: "alert_resolved", message: "Resolved" } });
    if (alert.status === "ACTIVE") Object.assign(alert, { status: "ACKNOWLEDGED", acknowledged_at: "2026-10-29T12:03:00Z" });
    return send(response, 200, { data_mode: "simulated", ...alert });
  }
  if (url.pathname === "/api/v1/fleet/summary") {
    if (scenario === "summary-error") return error(response, 503);
    return send(response, 200, { data_mode: "simulated", total_devices: scenario === "empty" ? 0 : 4,
      by_state: Object.fromEntries(states.map(state => [state, scenario === "empty" ? 0 : 1])) });
  }
  if (url.pathname === "/api/v1/devices") {
    const cursor = url.searchParams.get("after_device") ?? "";
    const remaining = scenario === "empty" ? [] : deviceIds.filter(id => id > cursor);
    // Small pages deliberately exercise cursor traversal despite a larger client limit.
    const ids = remaining.slice(0, 2);
    const items = ids.map(id => reading(id, 4));
    if (scenario === "malformed" && items[0]) items[0].event.device_state = "INVENTED_STATE";
    return send(response, 200, { data_mode: "simulated", items,
      next_after_device: scenario === "bad-cursor" ? "device-002" : remaining.length > 2 ? ids.at(-1) : null });
  }
  const match = /^\/api\/v1\/devices\/([^/]+)(\/telemetry)?$/.exec(url.pathname);
  if (match) {
    const deviceId = decodeURIComponent(match[1]);
    if (!deviceIds.includes(deviceId)) return error(response, 404);
    if (!match[2]) return send(response, 200, { data_mode: "simulated", ...reading(deviceId, 4) });
    if (scenario === "history-error") return error(response, 503);
    const before = url.searchParams.get("before");
    return send(response, 200, { data_mode: "simulated",
      items: scenario === "history-empty" ? [] : (before ? [1] : [4, 3, 2]).map(i => reading(deviceId, i)),
      next_before: before || scenario === "history-empty" ? null : reading(deviceId, 2).ingestion_order,
    });
  }
  return error(response, 404);
}).listen(3101, "127.0.0.1", () => console.log("Fixture API ready on 127.0.0.1:3101"));
