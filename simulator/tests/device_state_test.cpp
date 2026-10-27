#include "device_health/device_state.hpp"

#include <exception>
#include <iostream>
#include <initializer_list>
#include <stdexcept>
#include <string_view>

namespace {

using device_health::DeviceState;
using device_health::is_allowed_transition;

void require(bool condition, const char* message) {
    if (!condition) {
        throw std::runtime_error(message);
    }
}

void test_progression() {
    require(is_allowed_transition(DeviceState::healthy, DeviceState::warning),
            "A healthy device must be able to enter warning.");
    require(is_allowed_transition(DeviceState::warning, DeviceState::critical),
            "A warning device must be able to enter critical.");
    require(is_allowed_transition(DeviceState::critical, DeviceState::failed),
            "A critical device must be able to fail.");
}

void test_recovery() {
    require(is_allowed_transition(DeviceState::critical, DeviceState::warning),
            "A critical device must be able to recover to warning.");
    require(is_allowed_transition(DeviceState::warning, DeviceState::healthy),
            "A warning device must be able to recover to healthy.");
    require(!is_allowed_transition(DeviceState::critical, DeviceState::healthy),
            "Critical recovery must pass through warning.");
}

void test_skipped_states() {
    require(!is_allowed_transition(DeviceState::healthy, DeviceState::critical),
            "Degradation must not skip warning.");
    require(!is_allowed_transition(DeviceState::healthy, DeviceState::failed),
            "A healthy device cannot directly fail.");
    require(!is_allowed_transition(DeviceState::warning, DeviceState::failed),
            "Failure must pass through critical.");
    require(!is_allowed_transition(DeviceState::healthy, DeviceState::healthy),
            "Holding a state must not be classified as a state change.");
}

void test_terminal() {
    for (const auto destination : {DeviceState::healthy, DeviceState::warning,
                                   DeviceState::critical, DeviceState::failed}) {
        require(!is_allowed_transition(DeviceState::failed, destination),
                "A failed lifecycle has no outgoing state-change edges.");
    }
}

void test_invalid_state() {
    constexpr auto invalid = static_cast<DeviceState>(-1);
    for (const auto valid : {DeviceState::healthy, DeviceState::warning,
                            DeviceState::critical, DeviceState::failed}) {
        require(!is_allowed_transition(invalid, valid),
                "An unknown source state must fail closed.");
        require(!is_allowed_transition(valid, invalid),
                "An unknown destination state must fail closed.");
    }
}

} // namespace

int main(int argc, char* argv[]) {
    if (argc != 2) {
        std::cerr << "Usage: device_lifecycle_tests <test-case>\n";
        return 2;
    }

    const std::string_view test_case{argv[1]};
    try {
        if (test_case == "progression") {
            test_progression();
        } else if (test_case == "recovery") {
            test_recovery();
        } else if (test_case == "skipped_states") {
            test_skipped_states();
        } else if (test_case == "terminal") {
            test_terminal();
        } else if (test_case == "invalid_state") {
            test_invalid_state();
        } else {
            std::cerr << "Unknown test case: " << test_case << '\n';
            return 2;
        }
    } catch (const std::exception& error) {
        std::cerr << test_case << ": " << error.what() << '\n';
        return 1;
    }
    return 0;
}
