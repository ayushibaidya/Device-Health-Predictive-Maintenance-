import { Suspense } from "react";
import { getDevices } from "@/lib/api.server";
import { FleetSummary } from "@/components/fleet-summary";
import { DeviceTable } from "@/components/device-table";
import { RefreshButton } from "@/components/refresh-button";
import { SummarySkeleton, TableSkeleton, ViewState } from "@/components/view-state";

export const dynamic = "force-dynamic";

async function Devices() {
  let readings;
  try { readings = await getDevices(); }
  catch {
    return <section className="card"><ViewState title="Device data unavailable" retry>
      The API could not provide device readings. Check that the backend is running, then try again.
    </ViewState></section>;
  }
  return <DeviceTable readings={readings} />;
}

export default function FleetPage() {
  return <div className="page-stack">
    <div className="page-heading"><div><p className="eyebrow">Device monitoring</p>
      <h1>Fleet overview</h1><p className="page-description">A clear view of device health. Select a device to investigate.</p>
    </div><RefreshButton /></div>
    <Suspense fallback={<SummarySkeleton />}><FleetSummary /></Suspense>
    <Suspense fallback={<TableSkeleton />}><Devices /></Suspense>
    <p className="data-note"><span aria-hidden="true">ⓘ</span> Health states are reported by the simulator. Simulation timestamps do not indicate wall-clock device freshness.</p>
  </div>;
}
