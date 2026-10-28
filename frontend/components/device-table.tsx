import Link from "next/link";
import type { Reading } from "@/lib/api-types";
import { number, timestamp } from "@/lib/format";
import { HealthBadge } from "./health-badge";
import { ViewState } from "./view-state";

export function DeviceTable({ readings }: { readings: Reading[] }) {
  if (readings.length === 0) return <div className="card"><ViewState title="No devices yet">
    Devices will appear here when telemetry is received from the simulator.
  </ViewState></div>;
  return <section className="card" aria-labelledby="devices-heading">
    <div className="section-heading"><div><h2 id="devices-heading">Devices <span className="count-label">{readings.length}</span></h2>
      <p>Select a device to investigate its readings and history.</p></div><span className="quiet-label">Latest accepted readings</span></div>
    <div className="table-scroll"><table><caption className="sr-only">Observed devices and current device health</caption>
      <thead><tr><th>Device</th><th>State</th><th>Firmware</th><th>Temperature</th><th>CPU</th><th>Simulation time · UTC</th></tr></thead>
      <tbody>{readings.map(({ event }) => <tr key={event.device_id}>
        <td><Link className="device-link" prefetch={false} href={`/devices/${encodeURIComponent(event.device_id)}`} aria-label={`Inspect ${event.device_id}`}>
          <span className="device-icon" aria-hidden="true">▣</span>{event.device_id}<span className="link-arrow" aria-hidden="true">↗</span>
        </Link></td><td><HealthBadge state={event.device_state} /></td><td className="mono">{event.firmware_version}</td>
        <td className="tabular">{number(event.temperature_c)} <span className="unit">°C</span></td>
        <td className="tabular">{number(event.cpu_utilization_pct)}<span className="unit">%</span></td>
        <td className="time-cell">{timestamp(event.timestamp)}</td>
      </tr>)}</tbody></table></div>
  </section>;
}
