#include "device_health/simulator.hpp"
#ifdef DEVICE_HEALTH_KAFKA_ENABLED
#include "device_health/kafka.hpp"
#endif

#include <array>
#include <charconv>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <cstdlib>
#include <exception>
#include <iostream>
#include <memory>
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
  --output MODE                  stdout (default) or kafka (Kafka build only)
  --bootstrap-servers HOSTS       Kafka brokers; defaults to KAFKA_BOOTSTRAP_SERVERS
                                 or localhost:19092 when Kafka output is selected
  --delivery-timeout-ms N         Bounded Kafka delivery timeout (10000)

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
    std::string output = "stdout";
    std::string bootstrap_servers;
    int delivery_timeout_ms = 10'000;
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
        } else if (option == "--output") {
            options.output = value;
        } else if (option == "--bootstrap-servers") {
            options.bootstrap_servers = value;
            if (value.empty()) throw std::invalid_argument("Bootstrap servers must not be empty.");
        } else if (option == "--delivery-timeout-ms") {
            options.delivery_timeout_ms = number<int>(value, option);
        } else {
            throw std::invalid_argument("Unknown option: " + std::string(option));
        }
    }
    if (!std::isfinite(options.speed) ||
        (options.speed != 0 && options.speed < 1)) {
        throw std::invalid_argument("Speed must be 0 (no waits) or a finite value >= 1.");
    }
    options.simulation.validate();
    if (options.output != "stdout" && options.output != "kafka") {
        throw std::invalid_argument("Output must be stdout or kafka.");
    }
    if (options.delivery_timeout_ms < 100 || options.delivery_timeout_ms > 300'000) {
        throw std::invalid_argument("Delivery timeout must be in [100, 300000] milliseconds.");
    }
    if (options.output == "kafka") {
#ifndef DEVICE_HEALTH_KAFKA_ENABLED
        throw std::invalid_argument("Kafka is not enabled in this build; use the kafka CMake preset.");
#else
        if (options.bootstrap_servers.empty()) {
            const char* configured = std::getenv("KAFKA_BOOTSTRAP_SERVERS");
            options.bootstrap_servers = configured ? configured : "localhost:19092";
        }
        if (options.bootstrap_servers.empty()) {
            throw std::invalid_argument("Kafka bootstrap servers must not be empty.");
        }
#endif
    }
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
#ifdef DEVICE_HEALTH_KAFKA_ENABLED
        std::unique_ptr<device_health::KafkaPublisher> publisher;
        std::array<std::string, 3> run_ids;
        if (options.output == "kafka") {
            publisher = std::make_unique<device_health::KafkaPublisher>(device_health::KafkaConfig{
                options.bootstrap_servers, "device.telemetry.v1", options.delivery_timeout_ms});
            for (auto& run_id : run_ids) run_id = device_health::new_uuid();
        }
#endif
        std::ios::sync_with_stdio(false);
        auto deadline = std::chrono::steady_clock::now();
        for (;;) {
#ifdef DEVICE_HEALTH_KAFKA_ENABLED
            if (publisher && options.simulation.reset_at_step &&
                fleet.tick() == *options.simulation.reset_at_step) {
                run_ids[1] = device_health::new_uuid();
            }
            std::size_t device_index = 0;
#endif
            for (const auto& sample : fleet.samples()) {
#ifdef DEVICE_HEALTH_KAFKA_ENABLED
                if (publisher) {
                    const auto id = device_health::new_uuid();
                    const auto payload = device_health::serialize_kafka_event(sample, id, run_ids[device_index]);
                    // Write a replayable record before sending, preserving its identity on failure.
                    std::cout << payload << '\n';
                    std::cout.flush();
                    if (!std::cout) throw std::runtime_error("Failed to write Kafka event journal output.");
                    publisher->publish(id, sample.device_id, payload);
                } else {
                    std::cout << device_health::serialize_telemetry(sample) << '\n';
                }
                ++device_index;
#else
                std::cout << device_health::serialize_telemetry(sample) << '\n';
#endif
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
#ifdef DEVICE_HEALTH_KAFKA_ENABLED
        if (publisher) publisher->finish();
#endif
        return 0;
    } catch (const std::exception& error) {
        std::cerr << "device_simulator: " << error.what() << '\n';
        return 1;
    }
}
