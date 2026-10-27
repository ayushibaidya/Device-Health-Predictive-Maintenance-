import json

import pytest

from device_health_ingestion.errors import TransientProcessingError, ValidationError
from device_health_ingestion.replay import publish


class Producer:
    def __init__(self, error=None):
        self.error = error

    def produce(self, topic, *, key, value, on_delivery):
        self.topic, self.key, self.payload, self.callback = topic, key, value, on_delivery

    def flush(self, _):
        self.callback(self.error, None)
        return 0


def test_replay_preserves_original_identity(record, event):
    producer = Producer()
    assert publish(producer, record.payload) == event["event_id"]
    assert producer.payload == record.payload and producer.key == record.key


def test_replay_delivery_failure_is_explicit(record):
    with pytest.raises(TransientProcessingError):
        publish(Producer(error="failed"), record.payload)


def test_replay_rejects_events_without_identity(event):
    del event["event_id"]
    with pytest.raises(ValidationError):
        publish(Producer(), json.dumps(event).encode())
