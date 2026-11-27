import Link from "next/link";
import { RefreshButton } from "./refresh-button";

export function ViewState({ title, children, retry = false, back = false, headingLevel = 2 }: {
  title: string; children: React.ReactNode; retry?: boolean; back?: boolean; headingLevel?: 1 | 2;
}) {
  const Heading = headingLevel === 1 ? "h1" : "h2";
  return <div className="view-state" role={retry ? "alert" : undefined}>
    <span className="state-symbol" aria-hidden="true">{retry ? "!" : "—"}</span>
    <Heading>{title}</Heading><p>{children}</p>
    {retry && <RefreshButton label="Try again" />}
    {back && <Link className="button" href="/">Back to fleet</Link>}
  </div>;
}

export function SummarySkeleton() {
  return <div role="status" aria-label="Loading fleet summary" className="grid grid-cols-2 lg:grid-cols-5 gap-3">
    {Array.from({ length: 5 }, (_, i) => <div className="summary-card" key={i} aria-hidden="true">
      <div className="skeleton w-20 h-3 mb-5" /><div className="skeleton w-10 h-8" />
    </div>)}
  </div>;
}

export function TableSkeleton({ label = "Loading devices" }: { label?: string }) {
  return <div className="card p-6" role="status" aria-label={label}>
    {Array.from({ length: 5 }, (_, i) => <div className="skeleton h-8 mb-4 last:mb-0" key={i} aria-hidden="true" />)}
  </div>;
}

export function DeviceSkeleton() {
  return <div className="page-stack" role="status" aria-label="Loading device details">
    <div className="skeleton h-4 w-28" /><div className="skeleton h-10 w-56" />
    <div className="grid grid-cols-2 md:grid-cols-3 gap-3" aria-hidden="true">
      {Array.from({ length: 6 }, (_, i) => <div key={i} className="skeleton h-24" />)}
    </div><TableSkeleton label="Loading telemetry" />
  </div>;
}
