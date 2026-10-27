import base64
import json
from dataclasses import replace

import pytest

from device_health_ingestion.core import Processor
from device_health_ingestion.errors import PermanentProcessingError, TransientProcessingError
from device_health_ingestion.worker import KafkaDeadLetters


class Inbox:
    def __init__(self, failures=0):
        self.rows, self.calls, self.failures = {}, 0, failures

    def persist(self, event, _):
        self.calls += 1
        if self.calls <= self.failures:
            raise TransientProcessingError("database unavailable")
        old = self.rows.get(event["event_id"])
        if old is not None and old != event:
            raise PermanentProcessingError("conflicting identity")
        self.rows[event["event_id"]] = event
        return old is None


class DLQ:
    def __init__(self, fail=False):
        self.records, self.fail = [], fail

    def send(self, record, reason):
        if self.fail:
            raise TransientProcessingError("DLQ unavailable")
        self.records.append((record, reason))


def test_database_write_precedes_commit(record):
    inbox, dlq, commits = Inbox(), DLQ(), []
    result = Processor(inbox, dlq).process(record, lambda: commits.append(dict(inbox.rows)))
    assert result["outcome"] == "persisted"
    assert len(commits) == 1 and len(commits[0]) == 1
    assert not dlq.records


def test_duplicates_commit_without_duplicate_rows(record):
    inbox, commits = Inbox(), []
    processor = Processor(inbox, DLQ())
    assert processor.process(record, lambda: commits.append(True))["outcome"] == "persisted"
    assert processor.process(record, lambda: commits.append(True))["outcome"] == "duplicate"
    assert len(inbox.rows) == 1 and len(commits) == 2


def test_transient_database_failure_retries_before_commit(record):
    inbox, sleeps, commits = Inbox(failures=2), [], []
    Processor(inbox, DLQ(), sleep=sleeps.append).process(
        record, lambda: commits.append(inbox.calls)
    )
    assert commits == [3] and sleeps == [0.25, 0.5]


def test_exhausted_database_retries_leave_offset_uncommitted(record):
    inbox, commits, dlq = Inbox(failures=100), [], DLQ()
    with pytest.raises(TransientProcessingError):
        Processor(inbox, dlq, attempts=3, sleep=lambda _: None).process(
            record, lambda: commits.append(True)
        )
    assert inbox.calls == 3 and not commits and not dlq.records


def test_invalid_event_is_acknowledged_in_dlq_before_commit(record):
    dlq, inbox, commits = DLQ(), Inbox(), []
    result = Processor(inbox, dlq).process(
        replace(record, payload=b"{bad"), lambda: commits.append(len(dlq.records))
    )
    assert result["outcome"] == "dlq" and commits == [1] and inbox.calls == 0


def test_failed_dlq_delivery_leaves_offset_uncommitted(record):
    commits = []
    with pytest.raises(TransientProcessingError):
        Processor(Inbox(), DLQ(fail=True), attempts=2, sleep=lambda _: None).process(
            replace(record, payload=b"{bad"), lambda: commits.append(True)
        )
    assert not commits


def test_conflicting_identity_goes_to_dlq(record):
    inbox, dlq = Inbox(), DLQ()
    processor = Processor(inbox, dlq)
    processor.process(record, lambda: None)
    changed = json.loads(record.payload)
    changed["temperature_c"] = 80.0
    result = processor.process(replace(record, payload=json.dumps(changed).encode()), lambda: None)
    assert result["outcome"] == "dlq" and len(inbox.rows) == 1 and len(dlq.records) == 1


def test_ambiguous_offset_commit_can_replay_safely(record):
    inbox = Inbox()

    def failed_commit():
        raise RuntimeError("commit response lost")

    with pytest.raises(RuntimeError):
        Processor(inbox, DLQ()).process(record, failed_commit)
    assert Processor(inbox, DLQ()).process(record, lambda: None)["outcome"] == "duplicate"
    assert len(inbox.rows) == 1


@pytest.mark.parametrize("error,outstanding", [(None, 0), ("delivery failure", 0), (None, 1)])
def test_dlq_waits_for_broker_acknowledgement(record, error, outstanding):
    class Producer:
        def produce(self, topic, *, key, value, on_delivery):
            self.topic, self.value, self.callback = topic, value, on_delivery

        def flush(self, _):
            self.callback(error, None)
            return outstanding

    producer = Producer()
    dead_letters = KafkaDeadLetters(producer)
    if error or outstanding:
        with pytest.raises(TransientProcessingError):
            dead_letters.send(record, "validation failure")
    else:
        dead_letters.send(record, "validation failure")
        envelope = json.loads(producer.value)
        assert producer.topic == "device.telemetry.dlq.v1"
        assert base64.b64decode(envelope["raw_payload_b64"]) == record.payload
        assert envelope["source_offset"] == record.offset


def test_large_dlq_payload_is_bounded_and_identifiably_truncated(record):
    class Producer:
        def produce(self, topic, *, key, value, on_delivery):
            self.value, self.callback = value, on_delivery

        def flush(self, _):
            self.callback(None, None)
            return 0

    producer = Producer()
    KafkaDeadLetters(producer).send(replace(record, payload=b"x" * 600_000), "invalid")
    envelope = json.loads(producer.value)
    assert envelope["raw_payload_truncated"] and envelope["raw_payload_size"] == 600_000
    assert len(producer.value) < 1_000_000
