import Link from "next/link";
import type { DeviceDetail } from "@/lib/api-types";
import { timestamp } from "@/lib/format";
import { HealthBadge } from "./health-badge";
import { RefreshButton } from "./refresh-button";

export function DeviceHeader({ reading }: { reading: DeviceDetail }) {
  const { event } = reading;
  return <>
    <Link className="back-link" href="/">← Back to fleet</Link>
    <div className="page-heading"><div><p className="eyebrow">Device investigation</p><div className="title-row">
      <h1>{event.device_id}</h1><HealthBadge state={event.device_state} />
    </div><p className="page-description">Latest telemetry and the accepted reading history.</p></div><RefreshButton /></div>
    <dl className="device-metadata card">
      <div><dt>Firmware</dt><dd className="mono">{event.firmware_version}</dd></div>
      <div><dt>Current lifecycle</dt><dd className="mono break-all">{event.run_id}</dd></div>
      <div><dt>Latest simulation time</dt><dd>{timestamp(event.timestamp)}</dd></div>
      <div><dt>Accepted reading</dt><dd className="mono">#{reading.ingestion_order}</dd></div>
    </dl>
  </>;
}
