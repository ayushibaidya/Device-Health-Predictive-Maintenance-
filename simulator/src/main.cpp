#include "device_health/simulator.hpp"

#include <charconv>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <exception>
#include <iostream>
#include <set>
#include <stdexcept>
#include <string>
#include <string_view>
#include <thread>

namespace {

constexpr std::string_view help = R"(Usage: device_simulator [options]

Emit three devices as JSON Lines on stdout. Diagnostics use stderr.
Default: 1200 five-second ticks plus the initial sample, with no wall-clock waits.

  --help                         Show this help
  --seed N                       Unsigned 32-bit telemetry-noise seed (42)
  --start-time UTC               YYYY-MM-DDTHH:MM:SSZ (2026-01-01T00:00:00Z)
  --steps N                      Number of five-second advances (1200; 0 allowed)
  --speed N                      0: no waits; >=1: simulated seconds/wall second
  --reset-at-step N              Explicitly reset device-002 at tick N
  --clear-fault-at-step N         Clear device-003's fault at tick N (400)

Model controls use integer degradation units; 10000 units = fully degraded:
  --degradation-units N           Increase per faulty tick (20)
  --recovery-units N              Decrease per fault-free tick (10)
  --warning-threshold N          HEALTHY -> WARNING (4000)
  --critical-threshold N         WARNING -> CRITICAL (7500)
  --critical-recovery N          CRITICAL -> WARNING eligibility (6500)
  --warning-recovery N           WARNING -> HEALTHY eligibility (3000)
  --recovery-hold-ticks N         Full eligible intervals before recovery (6)

device-001: healthy control; device-002: fault until explicit reset;
device-003: fault until its configured clearance tick. All devices start healthy.
Thresholds are synthetic demonstration parameters, not physical calibration.
)";

template <typename T>
T number(std::string_view text, std::string_view option) {
    T value{};
    const auto result = std::from_chars(text.data(), text.data() + text.size(), value);
    if (text.empty() || result.ec != std::errc{} || result.ptr != text.data() + text.size()) {
        throw std::invalid_argument(std::string(option) + " has an invalid numeric value.");
    }
    return value;
}

struct Options {
    device_health::SimulationConfig simulation;
    double speed = 0;
    bool show_help = false;
};

Options parse_options(int argc, char* argv[]) {
    Options options;
    std::set<std::string_view> seen;
    for (int i = 1; i < argc; ++i) {
        const std::string_view option{argv[i]};
        if (option == "--help" && argc == 2) {
            options.show_help = true;
            return options;
        }
        if (!seen.insert(option).second) {
            throw std::invalid_argument("Duplicate option: " + std::string(option));
        }
        if (i + 1 >= argc) {
            throw std::invalid_argument("Missing value for " + std::string(option));
        }
        const std::string_view value{argv[++i]};
        auto& config = options.simulation;
        auto& model = config.model;
        if (option == "--seed") {
            config.seed = number<std::uint32_t>(value, option);
        } else if (option == "--steps") {
            config.steps = number<std::uint64_t>(value, option);
        } else if (option == "--start-time") {
            config.start = device_health::parse_utc(value);
        } else if (option == "--speed") {
            options.speed = number<double>(value, option);
        } else if (option == "--reset-at-step") {
            config.reset_at_step = number<std::uint64_t>(value, option);
        } else if (option == "--clear-fault-at-step") {
            config.clear_fault_at_step = number<std::uint64_t>(value, option);
        } else if (option == "--degradation-units") {
            model.degradation_per_tick = number<int>(value, option);
        } else if (option == "--recovery-units") {
            model.recovery_per_tick = number<int>(value, option);
        } else if (option == "--warning-threshold") {
            model.warning_threshold = number<int>(value, option);
        } else if (option == "--critical-threshold") {
            model.critical_threshold = number<int>(value, option);
        } else if (option == "--critical-recovery") {
            model.critical_recovery_threshold = number<int>(value, option);
        } else if (option == "--warning-recovery") {
            model.warning_recovery_threshold = number<int>(value, option);
        } else if (option == "--recovery-hold-ticks") {
            model.recovery_hold_ticks = number<std::uint32_t>(value, option);
        } else {
            throw std::invalid_argument("Unknown option: " + std::string(option));
        }
    }
    if (!std::isfinite(options.speed) ||
        (options.speed != 0 && options.speed < 1)) {
        throw std::invalid_argument("Speed must be 0 (no waits) or a finite value >= 1.");
    }
    options.simulation.validate();
    return options;
}

} // namespace

int main(int argc, char* argv[]) {
    try {
        const auto options = parse_options(argc, argv);
        if (options.show_help) {
            std::cout << help;
            return 0;
        }
        device_health::FleetSimulator fleet{options.simulation};
        std::ios::sync_with_stdio(false);
        auto deadline = std::chrono::steady_clock::now();
        for (;;) {
            for (const auto& sample : fleet.samples()) {
                std::cout << device_health::serialize_telemetry(sample) << '\n';
            }
            std::cout.flush();
            if (!std::cout) {
                throw std::runtime_error("Failed to write telemetry output.");
            }
            if (fleet.tick() == options.simulation.steps) {
                break;
            }
            if (options.speed != 0) {
                deadline += std::chrono::duration_cast<std::chrono::steady_clock::duration>(
                    std::chrono::duration<double>{
                        device_health::sample_interval_seconds / options.speed});
                std::this_thread::sleep_until(deadline);
            }
            fleet.advance();
        }
        return 0;
    } catch (const std::exception& error) {
        std::cerr << "device_simulator: " << error.what() << '\n';
        return 1;
    }
}
