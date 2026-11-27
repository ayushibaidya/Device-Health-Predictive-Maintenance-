export type AlertSeverity = "WARNING" | "CRITICAL" | "FAILURE";
export type AlertStatus = "ACTIVE" | "ACKNOWLEDGED" | "RESOLVED";
export interface DeviceAlert {
  alert_id: string;
  alert_order: number;
  device_id: string;
  run_id: string;
  rule_id: string;
  source: "simulator";
  severity: AlertSeverity;
  status: AlertStatus;
  message: string;
  opening_event_id: string;
  last_event_id: string;
  resolved_event_id: string | null;
  opened_event_time: string;
  last_event_time: string;
  resolved_event_time: string | null;
  created_at: string;
  updated_at: string;
  acknowledged_at: string | null;
  resolved_at: string | null;
  resolution_reason: "recovered" | "superseded" | "lifecycle_changed" | null;
}
export interface AlertPage {
  data_mode: "simulated";
  items: DeviceAlert[];
  next_before: number | null;
}
export interface AlertFilters {
  deviceId?: string;
  statuses?: AlertStatus[];
  severity?: AlertSeverity;
  before?: string;
  limit?: number;
}
export interface AcknowledgeState {
  outcome: "idle" | "success" | "conflict" | "error";
  message: string;
}
