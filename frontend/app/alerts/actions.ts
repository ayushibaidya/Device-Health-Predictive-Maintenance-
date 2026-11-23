"use server";

import { revalidatePath } from "next/cache";
import { ApiError } from "@/lib/api.server";
import { acknowledgeAlert } from "@/lib/alerts.server";
import type { AcknowledgeState } from "@/lib/alert-types";

export async function acknowledge(_previous: AcknowledgeState, form: FormData): Promise<AcknowledgeState> {
  const alertId = form.get("alert_id");
  if (typeof alertId !== "string" || !/^[0-9a-f-]{36}$/i.test(alertId)) {
    return { outcome: "error", message: "Invalid alert. Refresh and try again." };
  }
  try {
    const alert = await acknowledgeAlert(alertId);
    revalidatePath(`/devices/${encodeURIComponent(alert.device_id)}`);
    revalidatePath("/");
    revalidatePath("/alerts");
    return { outcome: "success", message: "Alert acknowledged." };
  } catch (error) {
    if (error instanceof ApiError && error.status === 409) {
      revalidatePath("/");
      revalidatePath("/alerts");
      return { outcome: "conflict", message: "This alert has already resolved. The view has been refreshed." };
    }
    return { outcome: "error", message: "Could not acknowledge this alert. Try again; repeating the request is safe." };
  }
}
