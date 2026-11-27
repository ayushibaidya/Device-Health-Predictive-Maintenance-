#include "device_health/kafka.hpp"

#include <nlohmann/json.hpp>

#include <array>
#include <cstdint>
#include <random>
#include <stdexcept>

namespace device_health {

namespace {

bool canonical_uuid(std::string_view value) {
    if (value.size() != 36) return false;
    bool nonzero = false;
    for (std::size_t i = 0; i < value.size(); ++i) {
        if (i == 8 || i == 13 || i == 18 || i == 23) {
            if (value[i] != '-') return false;
        } else {
            if (!((value[i] >= '0' && value[i] <= '9') ||
                  (value[i] >= 'a' && value[i] <= 'f'))) return false;
            nonzero |= value[i] != '0';
        }
    }
    return nonzero;
}

} // namespace

std::string new_uuid() {
    // Identity entropy is independent of the seeded telemetry-noise generator.
    std::random_device entropy;
    std::array<unsigned char, 16> bytes{};
    for (std::size_t i = 0; i < bytes.size(); i += 4) {
        const auto random = static_cast<std::uint32_t>(entropy());
        for (std::size_t j = 0; j < 4; ++j) {
            bytes[i + j] = static_cast<unsigned char>(random >> (j * 8));
        }
    }
    bytes[6] = static_cast<unsigned char>((bytes[6] & 0x0f) | 0x40);
    bytes[8] = static_cast<unsigned char>((bytes[8] & 0x3f) | 0x80);
    constexpr char hex[] = "0123456789abcdef";
    std::string result;
    result.reserve(36);
    for (std::size_t i = 0; i < bytes.size(); ++i) {
        if (i == 4 || i == 6 || i == 8 || i == 10) result += '-';
        result += hex[bytes[i] >> 4];
        result += hex[bytes[i] & 0x0f];
    }
    return result;
}

std::string serialize_kafka_event(const TelemetrySample& sample,
                                std::string_view event_id, std::string_view run_id) {
    if (!canonical_uuid(event_id) || !canonical_uuid(run_id)) {
        throw std::invalid_argument("Kafka event_id and run_id must be canonical nonzero UUIDs.");
    }
    auto event = nlohmann::json::parse(serialize_telemetry(sample));
    event["event_id"] = event_id;
    event["run_id"] = run_id;
    return event.dump();
}

} // namespace device_health
