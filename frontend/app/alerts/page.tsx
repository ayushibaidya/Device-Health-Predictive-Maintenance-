import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";
import { getAlerts } from "@/lib/alerts.server";
import type { AlertSeverity, AlertStatus } from "@/lib/alert-types";
import { AlertList } from "@/components/alert-list";
import { RefreshButton } from "@/components/refresh-button";
import { TableSkeleton, ViewState } from "@/components/view-state";

export const dynamic = "force-dynamic";
export const metadata: Metadata = { title: "Alerts" };
type Parameters = Record<string, string | string[] | undefined>;

async function Results({ parameters }: { parameters: Parameters }) {
  const { view = "open", device = "", severity = "", before } = parameters;
  if (typeof view !== "string" || !["open", "resolved", "all"].includes(view) ||
      typeof device !== "string" || device.includes("\0") || typeof severity !== "string" ||
      (severity !== "" && !["WARNING", "CRITICAL", "FAILURE"].includes(severity)) ||
      (before !== undefined && (typeof before !== "string" || !/^[1-9]\d*$/.test(before) || !Number.isSafeInteger(Number(before))))) {
    return <section className="card"><ViewState title="Invalid alert filters">Choose a valid view or <Link href="/alerts">reset the filters</Link>.</ViewState></section>;
  }
  const statuses: AlertStatus[] | undefined = view === "open" ? ["ACTIVE", "ACKNOWLEDGED"] : view === "resolved" ? ["RESOLVED"] : undefined;
  const query = new URLSearchParams({ view });
  if (device) query.set("device", device);
  if (severity) query.set("severity", severity);
  const newest = `/alerts?${query}`;
  let page;
  try {
    page = await getAlerts({ deviceId: device || undefined, statuses,
      severity: severity ? severity as AlertSeverity : undefined, before });
  } catch {
    return <section className="card"><ViewState title="Alerts unavailable" retry>
      The API could not provide alerts. Check the backend and try again.
    </ViewState></section>;
  }
  if (page.next_before) query.set("before", String(page.next_before));
  return <>
    <div className="alert-toolbar"><nav className="alert-tabs" aria-label="Alert views">
      {([ ["open", "Open"], ["resolved", "Resolved"], ["all", "All"] ] as const).map(([value, label]) => {
        const tab = new URLSearchParams(query); tab.set("view", value); tab.delete("before");
        return <Link key={value} href={`/alerts?${tab}`} aria-current={view === value ? "page" : undefined}>{label}</Link>;
      })}
    </nav><form className="alert-filters" action="/alerts" method="get">
      <input type="hidden" name="view" value={view} />
      <label>Device<input name="device" defaultValue={device} placeholder="All devices" /></label>
      <label>Severity<select name="severity" defaultValue={severity}>
        <option value="">All severities</option><option value="WARNING">Warning</option>
        <option value="CRITICAL">Critical</option><option value="FAILURE">Failure</option>
      </select></label><button className="button" type="submit">Apply filters</button>
    </form></div>
    <section className="card" aria-label="Alert results">
      <div className="section-heading"><div><h2>{view === "open" ? "Open alerts" : view === "resolved" ? "Resolved alerts" : "All alerts"}</h2>
        <p>Newest first · Up to 100 episodes per page{device ? ` · ${device}` : ""}</p></div></div>
      <AlertList alerts={page.items} empty={<ViewState title="No alerts in this view">No episodes match the selected filters.</ViewState>} />
    </section>
    {(before || page.next_before) && <nav className="pagination" aria-label="Alert pagination">
      <Link className="button" href={newest}>Newest alerts</Link>
      {page.next_before && <Link className="button" href={`/alerts?${query}`}>Older alerts →</Link>}
    </nav>}
  </>;
}
export default async function AlertsPage({ searchParams }: { searchParams: Promise<Parameters> }) {
  const parameters = await searchParams;
  return <div className="page-stack"><div className="page-heading"><div>
    <p className="eyebrow">Simulator state episodes</p><h1>Alerts</h1>
    <p className="page-description">Investigate state changes and acknowledge open episodes.</p>
  </div><RefreshButton /></div>
    <p className="data-note">Alerts reflect simulator-reported states. Acknowledgement records review; it does not change device health. No user identity is recorded in this local demo.</p>
    <Suspense key={JSON.stringify(parameters)} fallback={<TableSkeleton label="Loading alerts" />}><Results parameters={parameters} /></Suspense>
  </div>;
}
