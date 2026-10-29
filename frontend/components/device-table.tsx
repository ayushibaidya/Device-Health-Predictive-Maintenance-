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
      <p>Open any device row to inspect its readings and history.</p></div><span className="quiet-label">Latest accepted readings</span></div>
    <div className="table-scroll"><table><caption className="sr-only">Devices and reported health</caption>
      <thead><tr><th scope="col">Device</th><th scope="col">State</th><th scope="col">Firmware</th><th scope="col">Temperature</th><th scope="col">CPU</th><th scope="col">Errors</th><th scope="col">Simulation time · UTC</th></tr></thead>
      <tbody>{readings.map(({ event }) => <tr className="device-row" key={event.device_id}>
        <td><Link className="device-link" prefetch={false} href={`/devices/${encodeURIComponent(event.device_id)}`} aria-label={`Inspect ${event.device_id}`}>
          <span className="device-icon" aria-hidden="true">▣</span><span>{event.device_id}
            <span className="row-action" aria-hidden="true">View details <span>→</span></span>
          </span>
        </Link></td><td><HealthBadge state={event.device_state} /></td><td className="mono">{event.firmware_version}</td>
        <td className="tabular">{number(event.temperature_c)} <span className="unit">°C</span></td>
        <td className="tabular">{number(event.cpu_utilization_pct)}<span className="unit">%</span></td>
        <td className="tabular">{number(event.error_count, 0)}</td>
        <td className="time-cell">{timestamp(event.timestamp)}</td>
      </tr>)}</tbody></table></div>
  </section>;
}
