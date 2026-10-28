import argparse
import base64
import hashlib
import json
import math
import os
import signal
import sys
import time
from datetime import datetime, timezone

from confluent_kafka import Consumer, KafkaException, Producer

from .core import Processor, Record
from .errors import TransientProcessingError
from .latest import LatestState, configured_cache
from .queries import TelemetryQueries
from .store import PostgresInbox, database_dsn


def log(**fields):
    print(json.dumps(fields, sort_keys=True), flush=True)


class KafkaDeadLetters:
    def __init__(self, producer, topic="device.telemetry.dlq.v1", timeout=10):
        self.producer, self.topic, self.timeout = producer, topic, timeout

    def send(self, record, reason):
        raw = record.payload or b""
        key = record.key or b""
        limit = 256 * 1024
        envelope = {
            "source_topic": record.topic,
            "source_partition": record.partition,
            "source_offset": record.offset,
            "reason": reason,
            "failed_at": datetime.now(timezone.utc).isoformat(),
            "raw_payload_b64": base64.b64encode(raw[:limit]).decode(),
            "raw_payload_size": len(raw),
            "raw_payload_truncated": len(raw) > limit,
            "raw_payload_sha256": hashlib.sha256(raw).hexdigest(),
            "source_key_b64": base64.b64encode(key[:1024]).decode(),
            "source_key_truncated": len(key) > 1024,
        }
        acknowledgements = []
        try:
            self.producer.produce(
                self.topic,
                key=record.key if len(key) <= 1024 else None,
                value=json.dumps(envelope).encode(),
                on_delivery=lambda error, _: acknowledgements.append(error),
            )
            outstanding = self.producer.flush(self.timeout)
        except (KafkaException, BufferError) as error:
            raise TransientProcessingError("DLQ enqueue failed") from error
        if outstanding or len(acknowledgements) != 1 or acknowledgements[0] is not None:
            raise TransientProcessingError("DLQ delivery was not acknowledged")


def kafka_consumer(bootstrap, group):
    return Consumer(
        {
            "bootstrap.servers": bootstrap,
            "group.id": group,
            "enable.auto.commit": False,
            "enable.auto.offset.store": False,
            "auto.offset.reset": "earliest",
            "max.poll.interval.ms": 600_000,
            "allow.auto.create.topics": False,
        }
    )


def dlq_producer(bootstrap):
    return Producer(
        {
            "bootstrap.servers": bootstrap,
            "enable.idempotence": True,
            "acks": "all",
            "message.timeout.ms": 10_000,
            "retry.backoff.ms": 100,
            "retry.backoff.max.ms": 1000,
            "partitioner": "consistent_random",
        }
    )


def caught_up(consumer):
    assignment = consumer.assignment()
    if not assignment:
        return False
    for position in consumer.position(assignment):
        low, high = consumer.get_watermark_offsets(position, timeout=2)
        # Empty partitions may retain an invalid position until their first record.
        if low == high:
            continue
        if position.offset < high:
            return False
    return True


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Validate Kafka telemetry into a durable ingestion inbox"
    )
    parser.add_argument(
        "--bootstrap-servers", default=os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:19092")
    )
    parser.add_argument(
        "--group", default=os.getenv("KAFKA_GROUP_ID", "device-telemetry-validation-v1")
    )
    parser.add_argument("--max-messages", type=int, default=0, help="0 runs continuously")
    parser.add_argument("--idle-timeout", type=float, default=0, help="0 waits indefinitely")
    args = parser.parse_args(argv)
    if args.max_messages < 0 or not math.isfinite(args.idle_timeout) or args.idle_timeout < 0:
        parser.error("message limit and idle timeout must be nonnegative")
    try:
        dsn = database_dsn()
    except ValueError:
        parser.error("Configure DATABASE_URL or PGHOST/PGDATABASE/PGUSER/PGPASSWORD")
    inbox = PostgresInbox(dsn)
    queries = TelemetryQueries(dsn)
    try:
        cache = configured_cache()
    except ValueError:
        parser.error("Configure a valid REDIS_URL and LATEST_CACHE_TTL_SECONDS in [1, 3600]")
    latest = LatestState(queries, cache)
    consumer = kafka_consumer(args.bootstrap_servers, args.group)
    dead_letters = KafkaDeadLetters(dlq_producer(args.bootstrap_servers))
    processor = Processor(inbox, dead_letters, refresh_latest=latest.refresh if cache else None)
    stopping = False

    def stop(*_):
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    count, idle_since = 0, time.monotonic()
    try:
        consumer.subscribe(["device.telemetry.v1"])
        while not stopping:
            message = consumer.poll(0.5)
            if message is None:
                if args.idle_timeout and time.monotonic() - idle_since >= args.idle_timeout:
                    if args.max_messages:
                        raise TimeoutError("consumer idle timeout before message limit")
                    if caught_up(consumer):
                        break
                    if time.monotonic() - idle_since >= max(30, args.idle_timeout):
                        raise TimeoutError("consumer did not catch up before drain timeout")
                continue
            if message.error():
                raise KafkaException(message.error())
            idle_since = time.monotonic()
            record = Record(
                message.topic(),
                message.partition(),
                message.offset(),
                message.key(),
                message.value(),
            )
            result = processor.process(
                record, lambda: consumer.commit(message=message, asynchronous=False)
            )
            log(
                event="record_processed",
                topic=record.topic,
                partition=record.partition,
                offset=record.offset,
                **result,
            )
            count += 1
            if args.max_messages and count >= args.max_messages:
                break
        log(event="consumer_stopped", processed=count)
        return 0
    except Exception as error:
        # Exception messages from drivers can include connection configuration.
        log(event="consumer_failed", error_type=type(error).__name__, processed=count)
        return 1
    finally:
        consumer.close()
        inbox.close()
        queries.close()
        if cache is not None:
            cache.close()


if __name__ == "__main__":
    sys.exit(main())
