// Derived from processing/device_health_api/models.py. No frontend health inference.
export const HEALTH_STATES = ["HEALTHY", "WARNING", "CRITICAL", "FAILED"] as const;
export type HealthState = (typeof HEALTH_STATES)[number];

export interface TelemetryEvent {
  event_id: string;
  run_id: string;
  device_id: string;
  timestamp: string;
  firmware_version: string;
  temperature_c: number;
  power_draw_w: number;
  cpu_utilization_pct: number;
  memory_utilization_pct: number;
  timing_jitter_ms: number;
  error_count: number;
  device_state: HealthState;
  actuator_load_pct?: number | null;
  position_error_mm?: number | null;
}

export interface Reading { ingestion_order: number; event: TelemetryEvent }
export interface DeviceDetail extends Reading { data_mode: "simulated" }
export interface DevicePage {
  data_mode: "simulated";
  items: Reading[];
  next_after_device: string | null;
}
export interface HistoryPage {
  data_mode: "simulated";
  items: Reading[];
  next_before: number | null;
}
export interface FleetSummary {
  data_mode: "simulated";
  total_devices: number;
  by_state: Record<HealthState, number>;
}
