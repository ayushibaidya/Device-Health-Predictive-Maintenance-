"use client";
import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { Reading } from "@/lib/api-types";
import { number, timestamp } from "@/lib/format";
import { chartPoints, type ChartPoint } from "@/lib/history";

const charts = [
  { title: "Temperature", unit: "°C", lines: [{ key: "temperature_c", name: "Temperature", color: "#2563eb" }] },
  { title: "Power draw", unit: "W", lines: [{ key: "power_draw_w", name: "Power draw", color: "#2563eb" }] },
  { title: "CPU & memory", unit: "%", lines: [
    { key: "cpu_utilization_pct", name: "CPU", color: "#2563eb" },
    { key: "memory_utilization_pct", name: "Memory", color: "#087f8c" },
  ] },
  { title: "Timing jitter", unit: "ms", lines: [{ key: "timing_jitter_ms", name: "Timing jitter", color: "#2563eb" }] },
];

export function TelemetryCharts({ readings }: { readings: Reading[] }) {
  const points = chartPoints(readings);
  const lastSample = Math.max(readings.length - 1, 1);
  const ticks = [...new Set([0, Math.floor((readings.length - 1) / 2), readings.length - 1])];
  return <div className="grid grid-cols-1 lg:grid-cols-2 gap-4" aria-label="Telemetry charts">
    {charts.map(chart => <figure className="card chart-card" key={chart.title}>
      <figcaption><h3>{chart.title}</h3><span className="quiet-label">{chart.unit}</span></figcaption>
      <div className="chart-area" data-chart={chart.title}>
        <ResponsiveContainer width="100%" height="100%" initialDimension={{ width: 500, height: 240 }}>
          <LineChart data={points} accessibilityLayer margin={{ top: 12, right: 16, bottom: 0, left: -12 }}
            title={`${chart.title} history; readings in accepted order. See the telemetry table for values.`}>
            <CartesianGrid stroke="#e9edf3" vertical={false} />
            <XAxis dataKey="sample" type="number" domain={[0, lastSample]} ticks={ticks}
              axisLine={false} tickLine={false} tick={{ fontSize: 11, fill: "#64748b" }}
              tickFormatter={value => points.find(point => point.sample === value)?.reading?.event.timestamp.slice(11, 19) ?? ""}
              minTickGap={24} height={34} />
            <YAxis axisLine={false} tickLine={false} tick={{ fontSize: 11, fill: "#64748b" }}
              width={58} domain={chart.unit === "%" ? [0, 100] : ["auto", "auto"]}
              tickFormatter={value => number(Number(value), 2)} />
            <Tooltip filterNull contentStyle={{ borderRadius: 8, borderColor: "#e2e8f0", fontSize: 12 }}
              labelFormatter={(_, payload) => {
                const point = payload[0]?.payload as ChartPoint | undefined;
                return point?.reading ? `${timestamp(point.reading.event.timestamp)} · #${point.reading.ingestion_order}` : "Lifecycle boundary";
              }} formatter={value => `${number(typeof value === "number" ? value : null)} ${chart.unit}`} />
            <Legend iconType="plainline" wrapperStyle={{ fontSize: 11, paddingTop: 4 }} />
            {chart.lines.map(line => <Line key={line.key} type="linear" dataKey={line.key} name={line.name}
              stroke={line.color} strokeWidth={2} dot={{ r: readings.length <= 8 ? 3 : 0 }} activeDot={{ r: 4 }}
              connectNulls={false} isAnimationActive={false} />)}
          </LineChart>
        </ResponsiveContainer>
      </div>
    </figure>)}
  </div>;
}
