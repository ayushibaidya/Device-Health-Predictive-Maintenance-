#pragma once

namespace device_health {

enum class DeviceState { healthy, warning, critical, failed };

// State-change edges from ADR-003. Remaining in a state is not a transition.
// Reset starts a new lifecycle and is intentionally outside this predicate.
[[nodiscard]] constexpr bool is_allowed_transition(DeviceState from,
                                                   DeviceState to) noexcept {
    switch (from) {
    case DeviceState::healthy:
        return to == DeviceState::warning;
    case DeviceState::warning:
        return to == DeviceState::healthy || to == DeviceState::critical;
    case DeviceState::critical:
        return to == DeviceState::warning || to == DeviceState::failed;
    case DeviceState::failed:
        return false;
    }
    return false;
}

} // namespace device_health
