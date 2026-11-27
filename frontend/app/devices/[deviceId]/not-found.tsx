import { ViewState } from "@/components/view-state";

export default function DeviceNotFound() {
  return <div className="card"><ViewState title="Device not found" headingLevel={1} back>
    No device readings were found for this identifier. Choose an observed device from the fleet.
  </ViewState></div>;
}
