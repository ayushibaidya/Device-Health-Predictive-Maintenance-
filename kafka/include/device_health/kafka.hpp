#pragma once

#include "device_health/simulator.hpp"

#include <cstddef>
#include <memory>
#include <string>
#include <string_view>

namespace device_health {

[[nodiscard]] std::string new_uuid();
[[nodiscard]] std::string serialize_kafka_event(const TelemetrySample& sample,
                                               std::string_view event_id,
                                               std::string_view run_id);

struct KafkaConfig {
    std::string bootstrap_servers;
    std::string topic = "device.telemetry.v1";
    int delivery_timeout_ms = 10'000;
};

class KafkaPublisher {
public:
    explicit KafkaPublisher(KafkaConfig config);
    ~KafkaPublisher();
    KafkaPublisher(const KafkaPublisher&) = delete;
    KafkaPublisher& operator=(const KafkaPublisher&) = delete;

    void publish(std::string event_id, std::string device_id, std::string payload);
    void finish();
    [[nodiscard]] std::size_t delivered() const noexcept;

private:
    struct Impl;
    std::unique_ptr<Impl> impl_;
};

} // namespace device_health
