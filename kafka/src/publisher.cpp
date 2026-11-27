#include "device_health/kafka.hpp"

#include <librdkafka/rdkafka.h>

#include <array>
#include <chrono>
#include <iostream>
#include <map>
#include <stdexcept>
#include <utility>

namespace device_health {

struct KafkaPublisher::Impl {
    struct Delivery {
        std::string id;
        bool complete = false;
        rd_kafka_resp_err_t error = RD_KAFKA_RESP_ERR_NO_ERROR;
    };

    KafkaConfig config;
    rd_kafka_t* client = nullptr;
    rd_kafka_topic_t* topic = nullptr;
    std::map<std::string, std::unique_ptr<Delivery>> pending;
    std::size_t successes = 0;
    std::size_t failures = 0;
    bool finished = false;

    explicit Impl(KafkaConfig settings) : config(std::move(settings)) {
        if (config.bootstrap_servers.empty() || config.topic.empty() ||
            config.delivery_timeout_ms < 100 || config.delivery_timeout_ms > 300'000) {
            throw std::invalid_argument("Kafka requires bootstrap servers, topic, and a "
                                        "delivery timeout in [100, 300000] milliseconds.");
        }
        rd_kafka_conf_t* conf = rd_kafka_conf_new();
        try {
            const auto set = [conf](const char* name, const std::string& value) {
                std::array<char, 512> error{};
                if (rd_kafka_conf_set(conf, name, value.c_str(), error.data(), error.size()) !=
                    RD_KAFKA_CONF_OK) {
                    throw std::invalid_argument(std::string("Kafka setting ") + name + ": " + error.data());
                }
            };
            set("bootstrap.servers", config.bootstrap_servers);
            set("client.id", "device-health-simulator");
            set("enable.idempotence", "true");
            set("acks", "all");
            set("message.timeout.ms", std::to_string(config.delivery_timeout_ms));
            set("socket.timeout.ms", std::to_string(config.delivery_timeout_ms));
            set("retry.backoff.ms", "100");
            set("retry.backoff.max.ms", "1000");
            set("queue.buffering.max.messages", "1000");
            set("queue.buffering.max.kbytes", "4096");
            set("partitioner", "consistent_random");
            rd_kafka_conf_set_dr_msg_cb(conf, [](rd_kafka_t*, const rd_kafka_message_t* message,
                                               void*) noexcept {
                auto* delivery = static_cast<Delivery*>(message->_private);
                delivery->error = message->err;
                delivery->complete = true;
            });
            std::array<char, 512> error{};
            client = rd_kafka_new(RD_KAFKA_PRODUCER, conf, error.data(), error.size());
            if (!client) throw std::runtime_error(std::string("Kafka initialization: ") + error.data());
        } catch (...) {
            rd_kafka_conf_destroy(conf);
            throw;
        }
        topic = rd_kafka_topic_new(client, config.topic.c_str(), nullptr);
        if (!topic) {
            rd_kafka_destroy(client);
            client = nullptr;
            throw std::runtime_error("Cannot initialize Kafka topic handle.");
        }
    }

    void collect() {
        for (auto iterator = pending.begin(); iterator != pending.end();) {
            const auto& delivery = *iterator->second;
            if (!delivery.complete) { ++iterator; continue; }
            if (delivery.error == RD_KAFKA_RESP_ERR_NO_ERROR) {
                ++successes;
            } else {
                ++failures;
                std::cerr << "Kafka delivery failed: event_id=" << delivery.id
                          << " error=" << rd_kafka_err2str(delivery.error) << '\n';
            }
            iterator = pending.erase(iterator);
        }
    }

    ~Impl() {
        if (!client) return;
        if (!finished && !pending.empty()) {
            rd_kafka_flush(client, config.delivery_timeout_ms + 1000);
            collect();
            for (const auto& [id, delivery] : pending) {
                (void)delivery;
                std::cerr << "Kafka delivery unconfirmed: event_id=" << id << '\n';
            }
        }
        rd_kafka_topic_destroy(topic);
        rd_kafka_destroy(client);
    }
};

KafkaPublisher::KafkaPublisher(KafkaConfig config)
    : impl_(std::make_unique<Impl>(std::move(config))) {}
KafkaPublisher::~KafkaPublisher() = default;

void KafkaPublisher::publish(std::string event_id, std::string device_id, std::string payload) {
    auto& state = *impl_;
    if (state.finished) throw std::logic_error("Cannot publish after finish.");
    rd_kafka_poll(state.client, 0);
    state.collect();
    if (state.failures) throw std::runtime_error("Kafka reported a failed send; producer is stopping.");
    auto delivery = std::make_unique<Impl::Delivery>();
    delivery->id = event_id;
    auto* context = delivery.get();
    if (!state.pending.emplace(event_id, std::move(delivery)).second) {
        throw std::invalid_argument("An event_id is already queued.");
    }
    const auto deadline = std::chrono::steady_clock::now() +
                          std::chrono::milliseconds{state.config.delivery_timeout_ms};
    rd_kafka_resp_err_t error;
    do {
        const int result = rd_kafka_produce(state.topic, RD_KAFKA_PARTITION_UA,
            RD_KAFKA_MSG_F_COPY, payload.data(), payload.size(),
            device_id.data(), device_id.size(), context);
        error = result == 0 ? RD_KAFKA_RESP_ERR_NO_ERROR : rd_kafka_last_error();
        if (error != RD_KAFKA_RESP_ERR__QUEUE_FULL) break;
        rd_kafka_poll(state.client, 100);
        state.collect();
    } while (std::chrono::steady_clock::now() < deadline && !state.failures);
    if (error != RD_KAFKA_RESP_ERR_NO_ERROR) {
        state.pending.erase(event_id);
        throw std::runtime_error("Kafka enqueue failed for event_id=" + event_id +
                                 ": " + rd_kafka_err2str(error));
    }
    rd_kafka_poll(state.client, 0);
    state.collect();
}

void KafkaPublisher::finish() {
    auto& state = *impl_;
    if (state.finished) throw std::logic_error("Publisher was already finished.");
    const auto error = rd_kafka_flush(state.client, state.config.delivery_timeout_ms + 1000);
    state.collect();
    state.finished = true;
    if (error != RD_KAFKA_RESP_ERR_NO_ERROR || !state.pending.empty() || state.failures) {
        for (const auto& [id, delivery] : state.pending) {
            (void)delivery;
            std::cerr << "Kafka delivery unconfirmed: event_id=" << id << '\n';
        }
        throw std::runtime_error("Kafka delivery incomplete: " + std::to_string(state.failures) +
                                 " failed, " + std::to_string(state.pending.size()) + " unconfirmed.");
    }
    std::cerr << "Kafka delivery complete: " << state.successes << " events acknowledged.\n";
}

std::size_t KafkaPublisher::delivered() const noexcept { return impl_->successes; }

} // namespace device_health
