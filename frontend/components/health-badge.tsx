import type { HealthState } from "@/lib/api-types";
import { stateLabel } from "@/lib/format";

export function HealthBadge({ state }: { state: HealthState }) {
  return <span className={`health-badge health-${state.toLowerCase()}`}>
    <span className="status-dot" aria-hidden="true" />{stateLabel(state)}
  </span>;
}
