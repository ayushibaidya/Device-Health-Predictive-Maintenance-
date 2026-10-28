import { SummarySkeleton, TableSkeleton } from "@/components/view-state";

export default function Loading() {
  return <div className="page-stack"><div className="skeleton h-10 w-52" aria-hidden="true" />
    <SummarySkeleton /><TableSkeleton /></div>;
}
