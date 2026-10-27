#pragma once

#include "device_health/device_state.hpp"

#include <array>
#include <chrono>
#include <cstdint>
#include <optional>
#include <random>
#include <string>
#include <string_view>

namespace device_health {

inline constexpr int degradation_scale = 10'000;
inline constexpr int sample_interval_seconds = 5;

struct ModelConfig {
    int degradation_per_tick = 20;
    int recovery_per_tick = 10;
    int warning_threshold = 4'000;
    int critical_threshold = 7'500;
    int critical_recovery_threshold = 6'500;
    int warning_recovery_threshold = 3'000;
    std::uint32_t recovery_hold_ticks = 6;

    void validate() const;
};

struct TelemetrySample {
    std::string device_id;
    std::chrono::sys_seconds timestamp;
    std::string firmware_version;
    double temperature_c;
    double power_draw_w;
    double cpu_utilization_pct;
    double memory_utilization_pct;
    double timing_jitter_ms;
    int error_count;
    DeviceState device_state;
};

[[nodiscard]] std::chrono::sys_seconds parse_utc(std::string_view text);
[[nodiscard]] std::string format_utc(std::chrono::sys_seconds timestamp);
[[nodiscard]] std::string serialize_telemetry(const TelemetrySample& sample);

class Device {
public:
    Device(std::string id, std::uint32_t seed, ModelConfig config = {});

    void set_fault(bool active) noexcept;
    void advance();
    void reset() noexcept;
    [[nodiscard]] DeviceState state() const noexcept;
    [[nodiscard]] TelemetrySample sample(std::chrono::sys_seconds time);

private:
    [[nodiscard]] int noise(int amplitude);
    void recover_if_stable(bool eligible, DeviceState destination);

    std::string id_;
    ModelConfig config_;
    std::mt19937 random_;
    int degradation_ = 0;
    DeviceState state_ = DeviceState::healthy;
    bool fault_ = false;
    std::optional<std::uint32_t> recovery_ticks_;
};

struct SimulationConfig {
    ModelConfig model;
    std::uint32_t seed = 42;
    std::chrono::sys_seconds start = parse_utc("2026-01-01T00:00:00Z");
    std::uint64_t steps = 1'200;
    std::uint64_t clear_fault_at_step = 400;
    std::optional<std::uint64_t> reset_at_step;

    void validate() const;
};

class FleetSimulator {
public:
    explicit FleetSimulator(SimulationConfig config);
    [[nodiscard]] std::array<TelemetrySample, 3> samples();
    void advance();
    [[nodiscard]] std::uint64_t tick() const noexcept;

private:
    SimulationConfig config_;
    std::array<Device, 3> devices_;
    std::uint64_t tick_ = 0;
};

} // namespace device_health
