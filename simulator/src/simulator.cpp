#include "device_health/simulator.hpp"

#include <algorithm>
#include <charconv>
#include <iomanip>
#include <limits>
#include <locale>
#include <sstream>
#include <stdexcept>
#include <utility>

namespace device_health {

void ModelConfig::validate() const {
    if (!(0 <= warning_recovery_threshold &&
          warning_recovery_threshold < warning_threshold &&
          warning_threshold < critical_recovery_threshold &&
          critical_recovery_threshold < critical_threshold &&
          critical_threshold < degradation_scale)) {
        throw std::invalid_argument("Thresholds must satisfy 0 <= warning recovery "
                                    "< warning < critical recovery < critical < 10000.");
    }
    const int smallest_gap = std::min({warning_threshold,
                                     critical_threshold - warning_threshold,
                                     degradation_scale - critical_threshold});
    if (degradation_per_tick <= 0 || degradation_per_tick > smallest_gap) {
        throw std::invalid_argument("Degradation per tick must be positive and "
                                    "must not skip a state threshold.");
    }
    if (recovery_per_tick <= 0 || recovery_per_tick > degradation_scale ||
        recovery_hold_ticks == 0) {
        throw std::invalid_argument("Recovery step must be in [1, 10000] and "
                                    "recovery hold ticks must be positive.");
    }
}

std::chrono::sys_seconds parse_utc(std::string_view text) {
    using namespace std::chrono;
    if (text.size() != 20 || text[4] != '-' || text[7] != '-' ||
        text[10] != 'T' || text[13] != ':' || text[16] != ':' || text[19] != 'Z') {
        throw std::invalid_argument("Time must use YYYY-MM-DDTHH:MM:SSZ UTC format.");
    }
    const auto number = [text](std::size_t offset, std::size_t length) {
        int value = 0;
        const char* begin = text.data() + offset;
        const auto result = std::from_chars(begin, begin + length, value);
        if (result.ec != std::errc{} || result.ptr != begin + length || value < 0) {
            throw std::invalid_argument("Invalid digit in UTC time.");
        }
        for (std::size_t i = offset; i < offset + length; ++i) {
            if (text[i] < '0' || text[i] > '9') {
                throw std::invalid_argument("UTC time requires decimal digits.");
            }
        }
        return value;
    };
    const int y = number(0, 4);
    const int m = number(5, 2);
    const int d = number(8, 2);
    const int h = number(11, 2);
    const int minute = number(14, 2);
    const int second = number(17, 2);
    const year_month_day date{year{y}, month{static_cast<unsigned>(m)},
                              day{static_cast<unsigned>(d)}};
    if (y < 1 || !date.ok() || h > 23 || minute > 59 || second > 59) {
        throw std::invalid_argument("UTC time contains an invalid calendar date or clock time.");
    }
    return sys_days{date} + hours{h} + minutes{minute} + seconds{second};
}

std::string format_utc(std::chrono::sys_seconds timestamp) {
    using namespace std::chrono;
    const auto date_part = floor<days>(timestamp);
    const year_month_day date{date_part};
    const int y = static_cast<int>(date.year());
    if (y < 1 || y > 9999) {
        throw std::invalid_argument("UTC year must be in [0001, 9999].");
    }
    const hh_mm_ss time{timestamp - date_part};
    std::ostringstream output;
    output.imbue(std::locale::classic());
    output << std::setfill('0') << std::setw(4) << y << '-'
           << std::setw(2) << static_cast<unsigned>(date.month()) << '-'
           << std::setw(2) << static_cast<unsigned>(date.day()) << 'T'
           << std::setw(2) << time.hours().count() << ':'
           << std::setw(2) << time.minutes().count() << ':'
           << std::setw(2) << time.seconds().count() << 'Z';
    return output.str();
}

Device::Device(std::string id, std::uint32_t seed, ModelConfig config)
    : id_(std::move(id)), config_(config), random_(seed) {
    config_.validate();
    if (id_.empty()) {
        throw std::invalid_argument("Device ID must not be empty.");
    }
}

void Device::set_fault(bool active) noexcept {
    fault_ = active;
    if (active) recovery_ticks_.reset();
}
DeviceState Device::state() const noexcept { return state_; }

void Device::recover_if_stable(bool eligible, DeviceState destination) {
    if (!eligible) {
        recovery_ticks_.reset();
        return;
    }
    if (!recovery_ticks_) {
        recovery_ticks_ = 0;
    } else {
        ++*recovery_ticks_;
    }
    if (*recovery_ticks_ >= config_.recovery_hold_ticks) {
        state_ = destination;
        recovery_ticks_.reset();
    }
}

void Device::advance() {
    if (state_ == DeviceState::failed) {
        return;
    }
    degradation_ = std::clamp(degradation_ +
        (fault_ ? config_.degradation_per_tick : -config_.recovery_per_tick),
        0, degradation_scale);

    switch (state_) {
    case DeviceState::healthy:
        if (degradation_ >= config_.warning_threshold) {
            state_ = DeviceState::warning;
        }
        break;
    case DeviceState::warning:
        if (degradation_ >= config_.critical_threshold) {
            state_ = DeviceState::critical;
            recovery_ticks_.reset();
        } else {
            recover_if_stable(!fault_ && degradation_ <= config_.warning_recovery_threshold,
                              DeviceState::healthy);
        }
        break;
    case DeviceState::critical:
        if (degradation_ >= degradation_scale) {
            state_ = DeviceState::failed;
            recovery_ticks_.reset();
        } else {
            recover_if_stable(!fault_ && degradation_ <= config_.critical_recovery_threshold,
                              DeviceState::warning);
        }
        break;
    case DeviceState::failed:
        break;
    }
}

void Device::reset() noexcept {
    degradation_ = 0;
    state_ = DeviceState::healthy;
    fault_ = false;
    recovery_ticks_.reset();
}

int Device::noise(int amplitude) {
    // mt19937 integer output is specified; uniform_real_distribution is not.
    const auto width = static_cast<std::uint32_t>(2 * amplitude + 1);
    return static_cast<int>(random_() % width) - amplitude;
}

TelemetrySample Device::sample(std::chrono::sys_seconds time) {
    const auto metric = [this](int base, int increase, int noise_amplitude) {
        return (base + increase * degradation_ / degradation_scale +
                noise(noise_amplitude)) / 100.0;
    };
    return {id_, time, "1.0.0",
            metric(4'000, 6'000, 100),
            metric(500, 1'500, 10),
            std::clamp(metric(2'000, 7'000, 200), 0.0, 100.0),
            std::clamp(metric(3'000, 5'000, 100), 0.0, 100.0),
            std::max(0.0, metric(100, 2'000, 20)),
            10 * degradation_ / degradation_scale, state_};
}

void SimulationConfig::validate() const {
    model.validate();
    const auto earliest = parse_utc("0001-01-01T00:00:00Z");
    const auto latest = parse_utc("9999-12-31T23:59:59Z");
    if (start < earliest || start > latest) {
        throw std::invalid_argument("Starting UTC year must be in [0001, 9999].");
    }
    const auto available_steps = static_cast<std::uint64_t>(
        (latest - start).count() / sample_interval_seconds);
    if (steps > available_steps) {
        throw std::invalid_argument("Simulation would overflow the supported UTC calendar.");
    }
    if (reset_at_step && (*reset_at_step == 0 || *reset_at_step > steps)) {
        throw std::invalid_argument("Reset tick must be in [1, steps].");
    }
}

FleetSimulator::FleetSimulator(SimulationConfig config)
    : config_(std::move(config)),
      devices_{Device{"device-001", config_.seed, config_.model},
               Device{"device-002", config_.seed ^ 0x9e3779b9U, config_.model},
               Device{"device-003", config_.seed ^ 0x3c6ef372U, config_.model}} {
    config_.validate();
    devices_[1].set_fault(true);
    devices_[2].set_fault(config_.clear_fault_at_step != 0);
}

std::array<TelemetrySample, 3> FleetSimulator::samples() {
    const auto time = config_.start + std::chrono::seconds{
        static_cast<std::int64_t>(tick_ * sample_interval_seconds)};
    return {devices_[0].sample(time), devices_[1].sample(time), devices_[2].sample(time)};
}

void FleetSimulator::advance() {
    if (tick_ >= config_.steps) {
        throw std::out_of_range("Simulation has reached its configured final tick.");
    }
    for (auto& device : devices_) {
        device.advance();
    }
    ++tick_;
    if (tick_ == config_.clear_fault_at_step) {
        devices_[2].set_fault(false);
    }
    if (config_.reset_at_step && tick_ == *config_.reset_at_step) {
        devices_[1].reset();
    }
}

std::uint64_t FleetSimulator::tick() const noexcept { return tick_; }

} // namespace device_health
