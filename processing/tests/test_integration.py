import base64
import json
import os
import pathlib
import subprocess
import sys
import time
import uuid
from collections import defaultdict

import psycopg
import pytest
from confluent_kafka import TopicPartition
from psycopg.conninfo import make_conninfo

from device_health_ingestion.core import Processor, Record
from device_health_ingestion.errors import PermanentProcessingError, TransientProcessingError
from device_health_ingestion.store import PostgresInbox, database_dsn
from device_health_ingestion.worker import KafkaDeadLetters, dlq_producer, kafka_consumer

pytestmark = pytest.mark.integration
TOPIC, DLQ_TOPIC = "device.telemetry.v1", "device.telemetry.dlq.v1"


def bootstrap():
    return os.environ["KAFKA_BOOTSTRAP_SERVERS"]


def dsn():
    return database_dsn()


def watermarks(topic):
    consumer = kafka_consumer(bootstrap(), "inspect-" + str(uuid.uuid4()))
    try:
        metadata = consumer.list_topics(topic, timeout=10).topics[topic]
        assert not metadata.error
        return {
            partition: consumer.get_watermark_offsets(TopicPartition(topic, partition), timeout=10)[
                1
            ]
            for partition in metadata.partitions
        }
    finally:
        consumer.close()


def reader(topic, offsets, group=None):
    consumer = kafka_consumer(bootstrap(), group or "test-" + str(uuid.uuid4()))
    consumer.assign(
        [TopicPartition(topic, partition, offset) for partition, offset in offsets.items()]
    )
    return consumer


def receive(consumer):
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        message = consumer.poll(0.2)
        if message is not None:
            assert not message.error(), str(message.error())
            return message
    raise AssertionError("Kafka record was not received")


def send(payload, key=b"device-test"):
    producer = dlq_producer(bootstrap())
    deliveries = []
    producer.produce(
        TOPIC,
        key=key,
        value=payload,
        on_delivery=lambda error, message: deliveries.append((error, message)),
    )
    assert producer.flush(15) == 0
    assert len(deliveries) == 1 and deliveries[0][0] is None
    return deliveries[0][1]


def record_from(message):
    return Record(
        message.topic(), message.partition(), message.offset(), message.key(), message.value()
    )


def inbox_count(ids):
    with psycopg.connect(dsn()) as connection:
        return connection.execute(
            "SELECT count(*) FROM telemetry_inbox WHERE event_id = ANY(%s::uuid[])", (ids,)
        ).fetchone()[0]


def worker(group, count):
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "device_health_ingestion",
            "--group",
            group,
            "--max-messages",
            str(count),
            "--idle-timeout",
            "20",
        ],
        capture_output=True,
        text=True,
        timeout=45,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return [json.loads(line) for line in result.stdout.splitlines()]


def test_real_cpp_pipeline_and_consumer_restart_deduplication():
    events = [
        json.loads(line)
        for line in pathlib.Path("/fixtures/producer-events.jsonl").read_text().splitlines()
    ]
    assert len(events) == 9
    ids = [event["event_id"] for event in events]
    assert len(set(ids)) == len(ids)
    lifecycles = defaultdict(set)
    for event in events:
        uuid.UUID(event["event_id"])
        uuid.UUID(event["run_id"])
        lifecycles[event["device_id"]].add(event["run_id"])
    assert len(lifecycles["device-002"]) == 2  # Explicit reset at tick one.
    assert len(lifecycles["device-001"]) == len(lifecycles["device-003"]) == 1
    group = "restart-" + str(uuid.uuid4())
    first = worker(group, len(events))
    assert sum(row.get("outcome") == "persisted" for row in first) == len(events)
    assert inbox_count(ids) == len(events)
    replay = subprocess.run(
        [sys.executable, "-m", "device_health_ingestion.replay", "/fixtures/producer-events.jsonl"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert replay.returncode == 0, replay.stdout + replay.stderr
    second = worker(group, len(events))  # New OS process and new database connection.
    assert sum(row.get("outcome") == "duplicate" for row in second) == len(events)
    assert inbox_count(ids) == len(events)
    with psycopg.connect(dsn()) as connection:
        rows = connection.execute(
            """SELECT device_id, source_partition, event_time FROM telemetry_inbox
               WHERE event_id = ANY(%s::uuid[]) ORDER BY source_partition, source_offset""",
            (ids,),
        ).fetchall()
    per_device = defaultdict(list)
    partitions = defaultdict(set)
    for device, partition, event_time in rows:
        per_device[device].append(event_time)
        partitions[device].add(partition)
    assert all(times == sorted(times) for times in per_device.values())
    assert all(len(values) == 1 for values in partitions.values())


def test_crash_between_database_commit_and_offset_commit_replays_safely(event):
    offsets, group = watermarks(TOPIC), "crash-" + str(uuid.uuid4())
    send(json.dumps(event).encode())
    consumer = reader(TOPIC, offsets, group)
    inbox = PostgresInbox(dsn())
    try:
        message = receive(consumer)
        consumer.commit(
            offsets=[TopicPartition(TOPIC, message.partition(), message.offset())],
            asynchronous=False,
        )

        def crash():
            raise RuntimeError("injected crash after durable write")

        with pytest.raises(RuntimeError):
            Processor(inbox, KafkaDeadLetters(dlq_producer(bootstrap()))).process(
                record_from(message), crash
            )
        assert inbox_count([event["event_id"]]) == 1
        committed = consumer.committed([TopicPartition(TOPIC, message.partition())], timeout=10)
        assert committed[0].offset == message.offset()
    finally:
        consumer.close()
        inbox.close()
    restarted = reader(TOPIC, offsets, group)
    fresh_inbox = PostgresInbox(dsn())
    try:
        replay = receive(restarted)
        result = Processor(fresh_inbox, KafkaDeadLetters(dlq_producer(bootstrap()))).process(
            record_from(replay), lambda: restarted.commit(message=replay, asynchronous=False)
        )
        assert result["outcome"] == "duplicate"
        assert inbox_count([event["event_id"]]) == 1
        assert (
            restarted.committed([TopicPartition(TOPIC, replay.partition())], timeout=10)[0].offset
            == replay.offset() + 1
        )
    finally:
        restarted.close()
        fresh_inbox.close()


def test_invalid_event_reaches_real_dlq_before_offset_commit():
    source_offsets, dlq_offsets = watermarks(TOPIC), watermarks(DLQ_TOPIC)
    raw = b'{"invalid":true}'
    send(raw)
    consumer, dlq_reader = reader(TOPIC, source_offsets), reader(DLQ_TOPIC, dlq_offsets)
    inbox = PostgresInbox(dsn())
    try:
        message = receive(consumer)
        result = Processor(inbox, KafkaDeadLetters(dlq_producer(bootstrap()))).process(
            record_from(message), lambda: consumer.commit(message=message, asynchronous=False)
        )
        assert result["outcome"] == "dlq"
        envelope = json.loads(receive(dlq_reader).value())
        assert base64.b64decode(envelope["raw_payload_b64"]) == raw
        assert envelope["source_offset"] == message.offset()
        assert envelope["source_partition"] == message.partition()
        assert (
            consumer.committed([TopicPartition(TOPIC, message.partition())], timeout=10)[0].offset
            == message.offset() + 1
        )
    finally:
        consumer.close()
        dlq_reader.close()
        inbox.close()


def test_database_unavailable_leaves_offset_then_recovers(event):
    offsets = watermarks(TOPIC)
    send(json.dumps(event).encode())
    consumer = reader(TOPIC, offsets)
    broken_inbox = PostgresInbox(make_conninfo(dsn(), port=1))
    healthy_inbox = PostgresInbox(dsn())
    dead_letters = KafkaDeadLetters(dlq_producer(bootstrap()))
    try:
        message = receive(consumer)
        consumer.commit(
            offsets=[TopicPartition(TOPIC, message.partition(), message.offset())],
            asynchronous=False,
        )
        with pytest.raises(TransientProcessingError):
            Processor(broken_inbox, dead_letters, attempts=2, sleep=lambda _: None).process(
                record_from(message), lambda: consumer.commit(message=message, asynchronous=False)
            )
        assert inbox_count([event["event_id"]]) == 0
        assert (
            consumer.committed([TopicPartition(TOPIC, message.partition())], timeout=10)[0].offset
            == message.offset()
        )
        assert (
            Processor(healthy_inbox, dead_letters).process(
                record_from(message), lambda: consumer.commit(message=message, asynchronous=False)
            )["outcome"]
            == "persisted"
        )
        assert inbox_count([event["event_id"]]) == 1
    finally:
        consumer.close()
        broken_inbox.close()
        healthy_inbox.close()


def test_database_rejects_conflicting_identity_without_overwriting(event, record):
    inbox = PostgresInbox(dsn())
    try:
        assert inbox.persist(event, record)
        event["temperature_c"] = 80.0
        with pytest.raises(PermanentProcessingError):
            inbox.persist(event, record)
        with psycopg.connect(dsn()) as connection:
            original = connection.execute(
                "SELECT payload FROM telemetry_inbox WHERE event_id = %s", (event["event_id"],)
            ).fetchone()[0]
        assert original["temperature_c"] == 40.0
        assert inbox_count([event["event_id"]]) == 1
    finally:
        inbox.close()
