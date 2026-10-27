#include "device_health/simulator.hpp"
#include "test_support.hpp"

#include <nlohmann/json.hpp>

#include <array>
#include <chrono>
#include <cmath>
#include <exception>
#include <iostream>
#include <limits>
#include <string>
#include <string_view>

namespace {

using namespace device_health;

void test_thresholds() {
    Device device{"test", 42};
    device.set_fault(true);
    for (int tick = 1; tick <= 600; ++tick) {
        device.advance();
        const auto expected = tick < 200 ? DeviceState::healthy :
                              tick < 375 ? DeviceState::warning :
                              tick < 500 ? DeviceState::critical : DeviceState::failed;
        require(device.state() == expected, "State changed before/after its exact boundary.");
    }
    device.set_fault(false);
    for (int tick = 0; tick < 1'000; ++tick) {
        device.advance();
        require(device.state() == DeviceState::failed, "Failure recovered without reset.");
    }
}

void test_recovery() {
    SimulationConfig config;
    FleetSimulator fleet{config};
    for (std::uint64_t tick = 0; tick <= config.steps; ++tick) {
        const auto samples = fleet.samples();
        require(samples[0].device_state == DeviceState::healthy, "Healthy control degraded.");
        const auto expected = tick < 200 ? DeviceState::healthy :
                              tick < 375 ? DeviceState::warning :
                              tick < 556 ? DeviceState::critical :
                              tick < 906 ? DeviceState::warning : DeviceState::healthy;
        require(samples[2].device_state == expected,
                "Recovery threshold or 30-second stable period is incorrect.");
        if (tick != config.steps) {
            fleet.advance();
        }
    }
}

void test_interrupted_recovery() {
    Device device{"test", 42};
    device.set_fault(true);
    for (int tick = 0; tick < 200; ++tick) device.advance();
    device.set_fault(false);
    for (int tick = 0; tick < 102; ++tick) device.advance();
    require(device.state() == DeviceState::warning, "Recovery completed too early.");
    device.set_fault(true);
    device.advance();
    device.advance(); // Cross back above the warning recovery threshold.
    device.set_fault(false);
    for (int tick = 0; tick < 7; ++tick) device.advance();
    require(device.state() == DeviceState::warning,
            "Interrupted recovery reused an old stability timer.");
    device.advance();
    require(device.state() == DeviceState::healthy, "Stable recovery did not complete.");
}

void test_fault_blocks_recovery() {
    Device device{"test", 42};
    device.set_fault(true);
    for (int tick = 0; tick < 200; ++tick) device.advance();
    device.set_fault(false);
    for (int tick = 0; tick < 105; ++tick) device.advance();
    // The old recovery timer is one tick from completion. Even though the
    // degradation remains below the recovery threshold, an active fault blocks it.
    device.set_fault(true);
    device.advance();
    require(device.state() == DeviceState::warning,
            "A newly active fault must cancel pending recovery immediately.");
}

void test_custom_configuration() {
    SimulationConfig config;
    config.seed = 0;
    config.steps = 400;
    config.clear_fault_at_step = 150;
    config.model.degradation_per_tick = 50;
    config.model.recovery_per_tick = 25;
    config.model.warning_threshold = 3'000;
    config.model.critical_threshold = 6'000;
    config.model.critical_recovery_threshold = 5'000;
    config.model.warning_recovery_threshold = 2'000;
    config.model.recovery_hold_ticks = 2;
    FleetSimulator fleet{config};
    for (std::uint64_t tick = 0; tick <= config.steps; ++tick) {
        const auto samples = fleet.samples();
        const auto failing = tick < 60 ? DeviceState::healthy :
                             tick < 120 ? DeviceState::warning :
                             tick < 200 ? DeviceState::critical : DeviceState::failed;
        const auto recovering = tick < 60 ? DeviceState::healthy :
                                tick < 120 ? DeviceState::warning :
                                tick < 252 ? DeviceState::critical :
                                tick < 372 ? DeviceState::warning : DeviceState::healthy;
        require(samples[1].device_state == failing, "Custom progression controls were ignored.");
        require(samples[2].device_state == recovering, "Custom recovery controls were ignored.");
        if (tick != config.steps) fleet.advance();
    }
}

void test_reset() {
    SimulationConfig config;
    config.steps = 705;
    config.reset_at_step = 700;
    FleetSimulator fleet{config};
    const auto start = config.start;
    for (std::uint64_t tick = 0; tick <= config.steps; ++tick) {
        const auto sample = fleet.samples()[1];
        require(sample.timestamp == start + std::chrono::seconds{tick * 5},
                "Reset rewound the fleet clock.");
        require(sample.device_id == "device-002", "Reset changed device identity.");
        if (tick >= 500 && tick < 700) {
            require(sample.device_state == DeviceState::failed, "Failed device recovered early.");
        }
        if (tick >= 700) {
            require(sample.device_state == DeviceState::healthy, "Reset did not clear the fault.");
            require(sample.temperature_c >= 39 && sample.temperature_c <= 41,
                    "Reset did not clear hidden degradation.");
        }
        if (tick != config.steps) fleet.advance();
    }
}

void test_reproducibility() {
    SimulationConfig config;
    FleetSimulator first{config};
    FleetSimulator second{config};
    ++config.seed;
    FleetSimulator different_seed{config};
    bool changed_noise = false;
    for (std::uint64_t tick = 0; tick <= config.steps; ++tick) {
        const auto a = first.samples();
        const auto b = second.samples();
        const auto c = different_seed.samples();
        for (std::size_t device = 0; device < a.size(); ++device) {
            require(serialize_telemetry(a[device]) == serialize_telemetry(b[device]),
                    "Same inputs did not reproduce identical JSON.");
            require(a[device].device_state == c[device].device_state,
                    "Noise seed changed ground-truth lifecycle.");
            changed_noise |= a[device].temperature_c != c[device].temperature_c;
        }
        if (tick != config.steps) {
            first.advance(); second.advance(); different_seed.advance();
        }
    }
    require(changed_noise, "Different seeds did not change telemetry noise.");
}

void test_schema() {
    SimulationConfig config;
    config.steps = 600;
    FleetSimulator fleet{config};
    for (std::uint64_t tick = 0; tick <= config.steps; ++tick) {
        for (const auto& sample : fleet.samples()) {
            const auto event = nlohmann::json::parse(serialize_telemetry(sample));
            require(event.size() == 10, "Event contains missing or unexpected fields.");
            for (const auto* key : {"device_id", "timestamp", "firmware_version", "device_state"}) {
                require(event.at(key).is_string(), "Required string field has wrong type.");
            }
            for (const auto* key : {"temperature_c", "power_draw_w", "cpu_utilization_pct",
                                     "memory_utilization_pct", "timing_jitter_ms"}) {
                require(event.at(key).is_number_float(), "Required metric is not a JSON float.");
                require(std::isfinite(event.at(key).get<double>()), "Non-finite telemetry escaped.");
            }
            require(event.at("error_count").is_number_integer(), "Error count is not an integer.");
            require(sample.temperature_c >= 39 && sample.temperature_c <= 101, "Temperature bound.");
            require(sample.power_draw_w >= 4.9 && sample.power_draw_w <= 20.1, "Power bound.");
            require(sample.cpu_utilization_pct >= 0 && sample.cpu_utilization_pct <= 100, "CPU bound.");
            require(sample.memory_utilization_pct >= 0 && sample.memory_utilization_pct <= 100,
                    "Memory bound.");
            require(sample.timing_jitter_ms >= 0.8 && sample.timing_jitter_ms <= 21.2, "Jitter bound.");
            require(sample.error_count >= 0 && sample.error_count <= 10, "Error count bound.");
            require(parse_utc(event.at("timestamp").get<std::string>()) == sample.timestamp,
                    "JSON timestamp did not round-trip.");
        }
        if (tick != config.steps) fleet.advance();
    }
    Device escaped{"device-\"quoted\\id", 1};
    const auto event = nlohmann::json::parse(serialize_telemetry(escaped.sample(config.start)));
    require(event.at("device_id") == "device-\"quoted\\id", "Device ID was not JSON escaped.");
}

void test_invalid_sample() {
    Device device{"test", 1};
    const auto valid = device.sample(parse_utc("2026-01-01T00:00:00Z"));
    for (int field = 0; field < 8; ++field) {
        auto invalid = valid;
        switch (field) {
        case 0: invalid.temperature_c = std::numeric_limits<double>::quiet_NaN(); break;
        case 1: invalid.power_draw_w = -1; break;
        case 2: invalid.cpu_utilization_pct = 101; break;
        case 3: invalid.memory_utilization_pct = -1; break;
        case 4: invalid.timing_jitter_ms = std::numeric_limits<double>::infinity(); break;
        case 5: invalid.error_count = -1; break;
        case 6: invalid.device_id.clear(); break;
        case 7: invalid.device_state = static_cast<DeviceState>(99); break;
        }
        require_rejection([&] { (void)serialize_telemetry(invalid); },
                          "Invalid sample was silently serialized.");
    }
}

void test_time() {
    for (const auto* text : {"0001-01-01T00:00:00Z", "2024-02-29T23:59:59Z",
                             "2026-12-31T23:59:59Z", "9999-12-31T23:59:59Z"}) {
        require(format_utc(parse_utc(text)) == text, "UTC calendar round-trip failed.");
    }
    require(format_utc(parse_utc("2024-02-29T23:59:59Z") + std::chrono::seconds{1}) ==
            "2024-03-01T00:00:00Z", "Leap-day rollover failed.");
    for (const auto* text : {"2026-02-29T00:00:00Z", "2026-13-01T00:00:00Z",
                             "2026-01-01T24:00:00Z", "2026-01-01T00:60:00Z",
                             "2026-01-01T00:00:60Z", "2026-01-01T00:00:00+00:00",
                             "0000-01-01T00:00:00Z", "+026-01-01T00:00:00Z"}) {
        require_rejection([&] { (void)parse_utc(text); }, "Invalid calendar date was accepted.");
    }
}

void test_configuration() {
    for (int variant = 0; variant < 7; ++variant) {
        SimulationConfig config;
        switch (variant) {
        case 0: config.model.degradation_per_tick = 0; break;
        case 1: config.model.degradation_per_tick = 3'000; break;
        case 2: config.model.warning_threshold = config.model.critical_threshold; break;
        case 3: config.model.recovery_hold_ticks = 0; break;
        case 4: config.model.recovery_per_tick = -1; break;
        case 5: config.steps = std::numeric_limits<std::uint64_t>::max(); break;
        case 6: config.reset_at_step = config.steps + 1; break;
        }
        require_rejection([&] { config.validate(); }, "Invalid configuration was accepted.");
    }
    require_rejection([] { Device invalid{"", 1}; }, "Empty device ID was accepted.");
    SimulationConfig boundary;
    boundary.start = parse_utc("9999-12-31T23:59:59Z");
    boundary.steps = 0;
    boundary.validate();
    boundary.steps = 1;
    require_rejection([&] { boundary.validate(); }, "Calendar overflow was accepted.");
}

} // namespace

int main(int argc, char* argv[]) {
    if (argc != 2) return 2;
    const std::string_view name{argv[1]};
    try {
        if (name == "thresholds") test_thresholds();
        else if (name == "recovery") test_recovery();
        else if (name == "interrupted_recovery") test_interrupted_recovery();
        else if (name == "fault_blocks_recovery") test_fault_blocks_recovery();
        else if (name == "custom_configuration") test_custom_configuration();
        else if (name == "reset") test_reset();
        else if (name == "reproducibility") test_reproducibility();
        else if (name == "schema") test_schema();
        else if (name == "invalid_sample") test_invalid_sample();
        else if (name == "time") test_time();
        else if (name == "configuration") test_configuration();
        else return 2;
    } catch (const std::exception& error) {
        std::cerr << name << ": " << error.what() << '\n';
        return 1;
    }
    return 0;
}
