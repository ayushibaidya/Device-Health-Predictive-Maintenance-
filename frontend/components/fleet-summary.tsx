import { getSummary } from "@/lib/api.server";
import { HEALTH_STATES } from "@/lib/api-types";
import { number, stateLabel } from "@/lib/format";
import { ViewState } from "./view-state";

export async function FleetSummary() {
  let summary;
  try {
    summary = await getSummary();
  } catch {
    return <div className="card"><ViewState title="Fleet summary unavailable" retry>
      The summary could not be loaded. Available device readings are shown below.
    </ViewState></div>;
  }
  return <section aria-label="Fleet health summary" className="grid grid-cols-2 lg:grid-cols-5 gap-3">
    <div className="summary-card total-card"><p>Total devices</p><strong>{number(summary.total_devices, 0)}</strong><span>Across the fleet</span></div>
    {HEALTH_STATES.map(state => <div className={`summary-card summary-${state.toLowerCase()}`} key={state}>
      <p><span className="status-dot" aria-hidden="true" />{stateLabel(state)}</p>
      <strong>{number(summary.by_state[state], 0)}</strong><span>Devices</span>
    </div>)}
  </section>;
}
