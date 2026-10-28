import type { TelemetryEvent } from "@/lib/api-types";
import { number } from "@/lib/format";

export function TelemetryValues({ event }: { event: TelemetryEvent }) {
  const values: [string, number | null | undefined, string][] = [
    ["Temperature", event.temperature_c, "°C"], ["Power draw", event.power_draw_w, "W"],
    ["CPU utilization", event.cpu_utilization_pct, "%"], ["Memory utilization", event.memory_utilization_pct, "%"],
    ["Timing jitter", event.timing_jitter_ms, "ms"], ["Error count", event.error_count, ""],
  ];
  if ("actuator_load_pct" in event) values.push(["Actuator load", event.actuator_load_pct, "%"]);
  if ("position_error_mm" in event) values.push(["Position error", event.position_error_mm, "mm"]);
  return <section aria-label="Latest telemetry" className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-6 gap-3">
    {values.map(([label, value, unit]) => <div className="metric-card" key={label}><p>{label}</p>
      <strong className={value == null ? "metric-unavailable" : ""}>{number(value)}{value != null && <span>{unit}</span>}</strong>
    </div>)}
  </section>;
}
