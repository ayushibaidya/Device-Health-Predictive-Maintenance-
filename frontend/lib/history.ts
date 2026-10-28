import type { Reading } from "./api-types.ts";

export interface ChartPoint {
  sample: number;
  reading: Reading | null;
  temperature_c: number | null;
  power_draw_w: number | null;
  cpu_utilization_pct: number | null;
  memory_utilization_pct: number | null;
  timing_jitter_ms: number | null;
}

export function chartPoints(readings: Reading[]): ChartPoint[] {
  const ordered = [...readings].sort((a, b) => a.ingestion_order - b.ingestion_order);
  const points: ChartPoint[] = [];
  for (let index = 0; index < ordered.length; index++) {
    const row = ordered[index];
    if (index > 0 && row.event.run_id !== ordered[index - 1].event.run_id) {
      points.push({ sample: index - 0.5, reading: null, temperature_c: null,
        power_draw_w: null, cpu_utilization_pct: null, memory_utilization_pct: null,
        timing_jitter_ms: null });
    }
    points.push({ sample: index, reading: row, temperature_c: row.event.temperature_c,
      power_draw_w: row.event.power_draw_w, cpu_utilization_pct: row.event.cpu_utilization_pct,
      memory_utilization_pct: row.event.memory_utilization_pct,
      timing_jitter_ms: row.event.timing_jitter_ms });
  }
  return points;
}
