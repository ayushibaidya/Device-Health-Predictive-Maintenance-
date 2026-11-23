import Link from "next/link";
import { getAlerts } from "@/lib/alerts.server";
import { AlertList } from "./alert-list";
import { ViewState } from "./view-state";

export async function RecentAlerts({ deviceId }: { deviceId?: string }) {
  const query = new URLSearchParams({ view: "all" });
  if (deviceId) query.set("device", deviceId);
  let page;
  try {
    page = await getAlerts({ deviceId, statuses: ["ACTIVE", "ACKNOWLEDGED"], limit: 5 }, Boolean(deviceId));
  } catch {
    return <section className="card"><ViewState title="Alerts unavailable" retry>
      Alerts could not be loaded. Other device data is still available.
    </ViewState></section>;
  }
  return <section className="card" aria-label="Recent open alerts">
    <div className="section-heading"><div><h2>Open alerts</h2>
      <p>Newest five open episodes. Acknowledged alerts remain open until a simulator state change.</p></div>
      <Link className="button" href={`/alerts?${query}`}>View all alerts →</Link></div>
    <AlertList alerts={page.items} empty={<div className="alert-empty">No open alerts{deviceId ? " for this device" : ""}.</div>} />
  </section>;
}
