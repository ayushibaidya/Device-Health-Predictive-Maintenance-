import { ViewState } from "@/components/view-state";

export default function NotFound() {
  return <div className="card"><ViewState title="Page not found" headingLevel={1} back>
    This page is unavailable. Return to the fleet overview to select a device.
  </ViewState></div>;
}
