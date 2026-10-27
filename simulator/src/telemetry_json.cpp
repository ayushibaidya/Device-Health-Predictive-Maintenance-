#include "device_health/simulator.hpp"

#include <nlohmann/json.hpp>

#include <cmath>
#include <stdexcept>
#include <string_view>

namespace device_health {

namespace {

std::string_view state_name(DeviceState state) {
    switch (state) {
    case DeviceState::healthy: return "HEALTHY";
    case DeviceState::warning: return "WARNING";
    case DeviceState::critical: return "CRITICAL";
    case DeviceState::failed: return "FAILED";
    }
    throw std::invalid_argument("Telemetry contains an unknown device state.");
}

} // namespace

std::string serialize_telemetry(const TelemetrySample& sample) {
    if (sample.device_id.empty() || sample.firmware_version.empty() ||
        !std::isfinite(sample.temperature_c) || !std::isfinite(sample.power_draw_w) ||
        !std::isfinite(sample.cpu_utilization_pct) ||
        !std::isfinite(sample.memory_utilization_pct) ||
        !std::isfinite(sample.timing_jitter_ms) || sample.power_draw_w < 0 ||
        sample.cpu_utilization_pct < 0 || sample.cpu_utilization_pct > 100 ||
        sample.memory_utilization_pct < 0 || sample.memory_utilization_pct > 100 ||
        sample.timing_jitter_ms < 0 || sample.error_count < 0) {
        throw std::invalid_argument("Cannot serialize invalid telemetry.");
    }
    return nlohmann::json{
        {"device_id", sample.device_id},
        {"timestamp", format_utc(sample.timestamp)},
        {"firmware_version", sample.firmware_version},
        {"temperature_c", sample.temperature_c},
        {"power_draw_w", sample.power_draw_w},
        {"cpu_utilization_pct", sample.cpu_utilization_pct},
        {"memory_utilization_pct", sample.memory_utilization_pct},
        {"timing_jitter_ms", sample.timing_jitter_ms},
        {"error_count", sample.error_count},
        {"device_state", state_name(sample.device_state)}}.dump();
}

} // namespace device_health
