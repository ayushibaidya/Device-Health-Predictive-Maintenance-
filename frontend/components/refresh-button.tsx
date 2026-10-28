"use client";
import { useTransition } from "react";
import { useRouter } from "next/navigation";

export function RefreshButton({ label = "Refresh data" }: { label?: string }) {
  const router = useRouter();
  const [pending, startTransition] = useTransition();
  return <button className="button" disabled={pending} aria-busy={pending}
    onClick={() => startTransition(() => router.refresh())}>
    <svg viewBox="0 0 20 20" width="16" height="16" fill="none" aria-hidden="true">
      <path d="M16 7a6.5 6.5 0 1 0 .3 5M16 3v4h-4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>{pending ? "Refreshing…" : label}
  </button>;
}
