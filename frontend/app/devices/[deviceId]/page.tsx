import { Suspense } from "react";
import { notFound } from "next/navigation";
import { ApiError, getDevice } from "@/lib/api.server";
import { DeviceHeader } from "@/components/device-header";
import { TelemetryValues } from "@/components/telemetry-values";
import { TelemetryHistory } from "@/components/telemetry-history";
import { TableSkeleton, ViewState } from "@/components/view-state";

export const dynamic = "force-dynamic";

export default async function DevicePage({ params, searchParams }: {
  params: Promise<{ deviceId: string }>;
  searchParams: Promise<{ before?: string | string[] }>;
}) {
  const { deviceId } = await params;
  const { before } = await searchParams;
  let reading;
  try { reading = await getDevice(deviceId); }
  catch (error) {
    if (error instanceof ApiError && error.status === 404) notFound();
    return <div className="card"><ViewState title="Device data unavailable" headingLevel={1} retry back>
      This device could not be loaded. The API may be unavailable; try again shortly.
    </ViewState></div>;
  }
  return <div className="page-stack">
    <DeviceHeader reading={reading} />
    <TelemetryValues event={reading.event} />
    <Suspense key={`${deviceId}:${before ?? "latest"}`} fallback={<TableSkeleton label="Loading telemetry history" />}>
      <TelemetryHistory deviceId={deviceId} before={before} />
    </Suspense>
  </div>;
}
