import Link from "next/link";
import { getHistory } from "@/lib/api.server";
import { number, timestamp } from "@/lib/format";
import { HealthBadge } from "./health-badge";
import { TelemetryCharts } from "./telemetry-chart";
import { ViewState } from "./view-state";

export async function TelemetryHistory({ deviceId, before }: { deviceId: string; before?: string | string[] }) {
  const route = `/devices/${encodeURIComponent(deviceId)}`;
  if (before !== undefined && (typeof before !== "string" || !/^[1-9]\d*$/.test(before))) {
    return <div className="card"><ViewState title="Invalid history page">This history cursor is invalid.</ViewState>
      <div className="state-actions"><Link className="button" href={route}>Latest readings</Link></div></div>;
  }
  let page;
  try { page = await getHistory(deviceId, before); }
  catch {
    return <section className="card" aria-label="Telemetry history"><ViewState title="Telemetry history unavailable" retry>
      The history could not be loaded. The latest device reading remains available above.
    </ViewState></section>;
  }
  return <section aria-labelledby="history-heading" className="history-stack">
      <div className="section-heading standalone"><div><h2 id="history-heading">Telemetry history</h2>
        <p>Simulation time · UTC. Readings follow accepted order; lines break between lifecycles.</p></div>
        <span className="quiet-label">{page.items.length} readings in this window</span></div>
      {page.items.length === 0 ? <div className="card"><ViewState title="No telemetry in this window">
        No readings match this history page. Return to the latest readings or refresh to try again.
      </ViewState></div> : <>
        <TelemetryCharts readings={page.items} />
        <div className="card"><div className="section-heading"><div><h3>Reading log</h3>
          <p>Newest accepted reading first. All values are from the simulator.</p></div></div>
          <div className="table-scroll history-table"><table><caption className="sr-only">Telemetry readings</caption>
            <thead><tr><th>Simulation time · UTC</th><th>State</th><th>Temp · °C</th><th>Power · W</th><th>CPU · %</th>
              <th>Memory · %</th><th>Jitter · ms</th><th>Errors</th><th>Lifecycle</th></tr></thead>
            <tbody>{page.items.map(row => <tr key={row.event.event_id}>
              <td className="time-cell">{timestamp(row.event.timestamp)}<span className="reading-order">#{row.ingestion_order}</span></td>
              <td><HealthBadge state={row.event.device_state} /></td><td>{number(row.event.temperature_c)}</td>
              <td>{number(row.event.power_draw_w)}</td><td>{number(row.event.cpu_utilization_pct)}</td>
              <td>{number(row.event.memory_utilization_pct)}</td><td>{number(row.event.timing_jitter_ms)}</td>
              <td>{number(row.event.error_count, 0)}</td><td><code title={row.event.run_id}>{row.event.run_id.slice(0, 8)}</code></td>
            </tr>)}</tbody></table></div>
        </div>
      </>}
      <nav className="pagination" aria-label="History pagination">
        <span className="quiet-label">Showing {before ? "an older" : "the latest"} history window</span>
        <div className="flex gap-2">
          {before && <Link className="button" prefetch={false} href={route}>Latest readings</Link>}
          {page.next_before !== null && <Link className="button" prefetch={false}
            href={`${route}?before=${page.next_before}`}>Older readings <span aria-hidden="true">→</span></Link>}
        </div>
      </nav>
  </section>;
}
