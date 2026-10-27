#include "device_health/simulator.hpp"
#include "test_support.hpp"

#include <nlohmann/json.hpp>

#include <array>
#include <chrono>
#include <exception>
#include <fstream>
#include <iostream>
#include <map>
#include <string>
#include <string_view>
#include <vector>

int main(int argc, char* argv[]) {
    if (argc != 3) return 2;
    try {
        const bool reset_mode = std::string_view{argv[2]} == "reset";
        const std::size_t steps = reset_mode ? 705 : 1'200;
        const auto start = device_health::parse_utc("2026-01-01T00:00:00Z");
        std::ifstream input{argv[1]};
        require(input.is_open(), "Could not open CLI output.");
        const std::array<std::string, 3> ids{"device-001", "device-002", "device-003"};
        std::map<std::string, std::vector<std::string>> changes;
        std::string line;
        std::size_t lines = 0;
        while (std::getline(input, line)) {
            const auto event = nlohmann::json::parse(line);
            require(event.is_object() && event.size() == 10, "CLI violated the ten-field contract.");
            const auto id = event.at("device_id").get<std::string>();
            require(id == ids[lines % ids.size()], "CLI changed device ordering or identity.");
            const auto timestamp = event.at("timestamp").get<std::string>();
            require(device_health::parse_utc(timestamp) ==
                    start + std::chrono::seconds{static_cast<std::int64_t>(lines / 3 * 5)},
                    "CLI time is not monotonic at five-second intervals.");
            require(event.at("firmware_version") == "1.0.0", "Firmware metadata missing.");
            for (const auto* key : {"temperature_c", "power_draw_w", "cpu_utilization_pct",
                                     "memory_utilization_pct", "timing_jitter_ms"}) {
                require(event.at(key).is_number_float(), "CLI omitted a numeric metric.");
            }
            require(event.at("error_count").is_number_integer(), "CLI error count has wrong type.");
            const auto state = event.at("device_state").get<std::string>();
            auto& history = changes[id];
            if (history.empty() || history.back() != state) {
                history.push_back(state);
                std::cout << timestamp << "  " << id << "  " << state << '\n';
            }
            ++lines;
        }
        require(!input.bad(), "Could not read complete CLI output.");
        require(lines == 3 * (steps + 1), "CLI emitted the wrong number of events.");
        require(changes.at(ids[0]) == std::vector<std::string>{"HEALTHY"},
                "CLI healthy control degraded.");
        std::vector<std::string> failing{"HEALTHY", "WARNING", "CRITICAL", "FAILED"};
        if (reset_mode) failing.push_back("HEALTHY");
        require(changes.at(ids[1]) == failing, "CLI failed/reset journey is incorrect.");
        const std::vector<std::string> recovery = reset_mode
            ? std::vector<std::string>{"HEALTHY", "WARNING", "CRITICAL", "WARNING"}
            : std::vector<std::string>{"HEALTHY", "WARNING", "CRITICAL", "WARNING", "HEALTHY"};
        require(changes.at(ids[2]) == recovery, "CLI recovery journey is incorrect.");
        std::cout << "Validated " << lines << " real JSON events: healthy control, "
                  << "failure, recovery" << (reset_mode ? ", explicit reset" : "")
                  << ", UTC cadence, and schema.\n";
    } catch (const std::exception& error) {
        std::cerr << "CLI contract: " << error.what() << '\n';
        return 1;
    }
    return 0;
}
