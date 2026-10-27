#include "device_health/kafka.hpp"
#include "test_support.hpp"

#include <nlohmann/json.hpp>

#include <exception>
#include <iostream>
#include <set>
#include <string>

int main() {
    try {
        std::set<std::string> identifiers;
        for (int i = 0; i < 1000; ++i) {
            const auto id = device_health::new_uuid();
            require(id.size() == 36 && id[14] == '4' &&
                    (id[19] == '8' || id[19] == '9' || id[19] == 'a' || id[19] == 'b'),
                    "Identity is not a canonical variant-1 UUID v4.");
            require(identifiers.insert(id).second, "Identity generation collided.");
        }
        device_health::Device device{"device-001", 42};
        const auto sample = device.sample(device_health::parse_utc("2026-01-01T00:00:00Z"));
        const auto id = device_health::new_uuid();
        const auto run = device_health::new_uuid();
        const auto event = nlohmann::json::parse(device_health::serialize_kafka_event(sample, id, run));
        require(event.size() == 12 && event.at("event_id") == id && event.at("run_id") == run,
                "Kafka identity fields are missing.");
        require(event.at("device_id") == sample.device_id, "Stable device identity changed.");
        require(device_health::serialize_kafka_event(sample, id, run) == event.dump(),
                "Retry changed event identity or payload.");
        require_rejection([&] { (void)device_health::serialize_kafka_event(sample, "", run); },
                          "Missing identity was accepted.");
        require_rejection([] { device_health::KafkaPublisher publisher{{"", "", 1}}; },
                          "Invalid broker configuration was accepted.");
    } catch (const std::exception& error) {
        std::cerr << error.what() << '\n';
        return 1;
    }
    return 0;
}
