// Isolated browser-test fixture, never imported or shipped by the application.
import { createServer } from "node:http";
import { setTimeout } from "node:timers/promises";

let scenario = "default";
const states = ["HEALTHY", "WARNING", "CRITICAL", "FAILED"];
const runA = "11111111-1111-4111-8111-111111111111";
const runB = "22222222-2222-4222-8222-222222222222";
const deviceIds = ["device-001", "device-002", "device-003", "device-004"];

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
    return send(response, 200, { scenario });
  }
  if (scenario === "delay") await setTimeout(2500);
  if (scenario === "api-error") return error(response, 503);
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
