"""Replay captured Kafka records with their original event and lifecycle IDs."""

import argparse
import json
import os

from .errors import TransientProcessingError
from .validation import validate
from .worker import dlq_producer


def publish(producer, payload):
    candidate = json.loads(payload)
    key = candidate["device_id"].encode()
    event = validate(payload, key)
    results = []
    producer.produce(
        "device.telemetry.v1",
        key=key,
        value=payload,
        on_delivery=lambda error, _: results.append(error),
    )
    if producer.flush(15) or len(results) != 1 or results[0] is not None:
        raise TransientProcessingError("replay delivery failed for event_id=" + event["event_id"])
    return event["event_id"]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path")
    args = parser.parse_args()
    producer = dlq_producer(os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:19092"))
    count = 0
    try:
        with open(args.path, "rb") as source:
            for payload in source:
                publish(producer, payload)
                count += 1
    except Exception as error:
        print(
            json.dumps(
                {
                    "event": "replay_failed",
                    "acknowledged": count,
                    "error_type": type(error).__name__,
                }
            )
        )
        return 1
    print(json.dumps({"event": "replay_complete", "acknowledged": count}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
