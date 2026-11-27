"use client";

import { useActionState, useEffect } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { acknowledge } from "@/app/alerts/actions";
import type { AcknowledgeState, DeviceAlert } from "@/lib/alert-types";
import { AcknowledgeButton } from "./acknowledge-button";

const reasons = { recovered: "Recovered", superseded: "Severity changed", lifecycle_changed: "Lifecycle changed" };
const initial: AcknowledgeState = { outcome: "idle", message: "" };
function stamp(value: string) { return value.replace("T", " ").replace(/(?:\.\d+)?(?:Z|\+00:00)$/, " UTC"); }
export function AlertList({ alerts, empty }: { alerts: DeviceAlert[]; empty?: React.ReactNode }) {
  const [feedback, action, pending] = useActionState(acknowledge, initial);
  const router = useRouter();
  useEffect(() => {
    if (feedback.outcome === "success" || feedback.outcome === "conflict") router.refresh();
  }, [feedback, router]);
  return <>
    {feedback?.message && <p className="alert-feedback" role={feedback.outcome === "error" ? "alert" : "status"}>{feedback.message}</p>}
    {alerts.length === 0 ? empty : <ol className="alert-list" aria-label="Device alerts">{alerts.map(alert =>
    <li key={alert.alert_id}><article aria-label={`${alert.severity} alert for ${alert.device_id}`} className="alert-row">
      <div className="alert-content"><div className="alert-title">
        <span className={`health-badge health-${alert.severity === "FAILURE" ? "failed" : alert.severity.toLowerCase()}`}>
          <span className="status-dot" />{alert.severity === "FAILURE" ? "Failure" : alert.severity === "CRITICAL" ? "Critical" : "Warning"}
        </span>
        <Link className="device-link" href={`/devices/${encodeURIComponent(alert.device_id)}`}>{alert.device_id}</Link>
        <span className={`alert-status alert-status-${alert.status.toLowerCase()}`}>
          {alert.status === "ACKNOWLEDGED" ? "Acknowledged" : alert.status === "RESOLVED" ? "Resolved" : "Active"}
        </span>
      </div><p className="alert-message">{alert.message}</p>
      <dl className="alert-evidence">
        <div><dt>Opened · simulation</dt><dd><time dateTime={alert.opened_event_time}>{stamp(alert.opened_event_time)}</time></dd></div>
        <div><dt>Last evidence · simulation</dt><dd><time dateTime={alert.last_event_time}>{stamp(alert.last_event_time)}</time></dd></div>
        {alert.acknowledged_at && <div><dt>Acknowledged · wall clock</dt><dd><time dateTime={alert.acknowledged_at}>{stamp(alert.acknowledged_at)}</time></dd></div>}
        {alert.resolution_reason && <div><dt>Resolution</dt><dd>{reasons[alert.resolution_reason]}</dd></div>}
      </dl></div>
      <AcknowledgeButton alertId={alert.alert_id} status={alert.status} action={action} pending={pending} />
    </article></li>)}</ol>}</>;
}
