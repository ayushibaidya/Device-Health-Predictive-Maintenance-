import json
from uuid import uuid4

import pytest
from confluent_kafka import TopicPartition

from device_health_alerts.store import AlertQueries
from device_health_ingestion.core import Processor
from device_health_ingestion.store import PostgresInbox, database_dsn
from test_integration import bootstrap, reader, receive, record_from, send, watermarks
from device_health_ingestion.worker import KafkaDeadLetters, dlq_producer

pytestmark = pytest.mark.integration


def test_alert_and_ack_survive_kafka_commit_crash_and_consumer_restart(event):
    event.update(device_id="alert-replay-" + uuid4().hex, device_state="WARNING")
    topic, group = "device.telemetry.v1", "alert-replay-" + uuid4().hex
    offsets = watermarks(topic)
    inbox, alerts = PostgresInbox(database_dsn()), AlertQueries(database_dsn())
    consumer = reader(topic, offsets, group)
    dlq = KafkaDeadLetters(dlq_producer(bootstrap()))
    try:
        send(json.dumps(event).encode(), event["device_id"].encode())
        message = receive(consumer)
        record = record_from(message)

        def crash():
            raise RuntimeError("simulated crash before offset commit")

        with pytest.raises(RuntimeError, match="simulated crash"):
            Processor(inbox, dlq).process(record, crash)
        opened = alerts.page(device_id=event["device_id"])["items"][0]
        acknowledged = alerts.acknowledge(opened["alert_id"])
        consumer.close()
        inbox.close()
        alerts.close()
        # New consumer/store connections replay the same uncommitted Kafka record.
        consumer = reader(topic, {message.partition(): message.offset()}, group)
        replay = receive(consumer)
        result = Processor(inbox, dlq).process(
            record_from(replay), lambda: consumer.commit(message=replay, asynchronous=False)
        )
        assert result["outcome"] == "duplicate"
        assert alerts.page(device_id=event["device_id"])["items"] == [acknowledged]
        committed = consumer.committed([TopicPartition(topic, replay.partition())], timeout=5)[
            0
        ].offset
        assert committed == replay.offset() + 1
    finally:
        consumer.close()
        inbox.close()
        alerts.close()
