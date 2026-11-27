"use client";

import type { AlertStatus } from "@/lib/alert-types";

export function AcknowledgeButton({ alertId, status, action, pending }: {
  alertId: string; status: AlertStatus; action: (form: FormData) => void; pending: boolean;
}) {
  return <div className="ack-control">
    {status === "ACTIVE" && <form action={action}>
      <input type="hidden" name="alert_id" value={alertId} />
      <button className="button" disabled={pending} type="submit">
        {pending ? "Acknowledging…" : "Acknowledge"}
      </button>
    </form>}
  </div>;
}
