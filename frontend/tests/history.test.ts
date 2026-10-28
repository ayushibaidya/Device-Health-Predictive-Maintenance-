import assert from "node:assert/strict";
import { test } from "node:test";
import { chartPoints } from "../lib/history.ts";
import type { Reading } from "../lib/api-types.ts";

function reading(order: number, run: string, timestamp: string): Reading {
  return { ingestion_order: order, event: {
    event_id: String(order), run_id: run, device_id: "device-test", timestamp,
    firmware_version: "1.0.0", device_state: "HEALTHY", error_count: 0,
    temperature_c: order, power_draw_w: 0, cpu_utilization_pct: 0,
    memory_utilization_pct: 30, timing_jitter_ms: 1,
  } };
}

test("a lifecycle reset never reorders history by its restarted clock or joins the runs", () => {
  const newer = reading(9, "new-run", "2026-01-01T00:00:00Z");
  const older = reading(4, "old-run", "2026-01-01T00:00:10Z");
  const points = chartPoints([newer, older]);
  assert.deepEqual(points.map(point => point.reading?.ingestion_order ?? null), [4, null, 9]);
  assert.equal(points[1].temperature_c, null);
  assert.equal(points[1].power_draw_w, null);
});

test("accepted order is stable without mutating API readings", () => {
  const input = [reading(9, "same", "2026-01-01T00:00:10Z"), reading(4, "same", "2026-01-01T00:00:05Z")];
  assert.deepEqual(chartPoints(input).map(point => point.reading?.ingestion_order), [4, 9]);
  assert.deepEqual(input.map(point => point.ingestion_order), [9, 4]);
});

test("real zero readings remain zero", () => {
  assert.equal(chartPoints([reading(1, "same", "2026-01-01T00:00:00Z")])[0].power_draw_w, 0);
});

test("empty history has no fabricated points", () => assert.deepEqual(chartPoints([]), []));
