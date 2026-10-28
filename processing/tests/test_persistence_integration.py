import json
import os
import time
import uuid
from pathlib import Path

import psycopg
import pytest
from confluent_kafka import TopicPartition
from psycopg import sql
from psycopg.conninfo import make_conninfo

from device_health_ingestion.core import Processor, Record
from device_health_ingestion.latest import CacheUnavailable, LatestState, RedisLatest
from device_health_ingestion.migrate import migrate
from device_health_ingestion.queries import Reading, TelemetryQueries
from device_health_ingestion.store import PostgresInbox, database_dsn
from device_health_ingestion.worker import KafkaDeadLetters, dlq_producer
from test_integration import bootstrap, reader, receive, record_from, send, watermarks

pytestmark = pytest.mark.integration


@pytest.fixture
def data():
    inbox, queries = PostgresInbox(database_dsn()), TelemetryQueries(database_dsn())
    cache = RedisLatest(os.environ["REDIS_URL"], prefix="test:" + str(uuid.uuid4()) + ":")
    try:
        yield inbox, queries, cache
    finally:
        inbox.close()
        queries.close()
        for key in cache.client.scan_iter(match=cache.prefix + "*"):
            cache.client.delete(key)
        cache.close()


def accept(inbox, event, offset):
    record = Record(
        "device.telemetry.v1", 0, offset, event["device_id"].encode(), json.dumps(event).encode()
    )
    return inbox.persist(event, record)


def test_history_filters_pagination_and_lifecycle_replay(data, event):
    inbox, queries, cache = data
    event["device_id"] = "history-" + str(uuid.uuid4())
    first = dict(event, timestamp="2026-01-01T00:00:05Z")
    second = dict(first, event_id=str(uuid.uuid4()), timestamp="2026-01-01T00:00:10Z")
    # A new lifecycle can restart its simulation clock. Accepted order remains durable.
    reset = dict(
        first,
        event_id=str(uuid.uuid4()),
        run_id=str(uuid.uuid4()),
        timestamp="2026-01-01T00:00:00Z",
        device_state="WARNING",
    )
    for offset, reading in enumerate((first, second, reset)):
        assert accept(inbox, reading, offset)
    latest = LatestState(queries, cache)
    assert latest.refresh(event["device_id"])
    assert latest.get(event["device_id"]).event == reset
    reset_order = queries.latest(event["device_id"]).ingestion_order
    assert not accept(inbox, first, 100)
    assert latest.refresh(event["device_id"])
    assert cache.get(event["device_id"]) == Reading(reset_order, reset)
    queries.close()  # Durable history/latest must survive a new connection.
    page = queries.history(event["device_id"], limit=2)
    assert [item["event"] for item in page["items"]] == [reset, second]
    tail = queries.history(event["device_id"], limit=2, before=page["next_before"])
    assert [item["event"] for item in tail["items"]] == [first]
    assert tail["next_before"] is None
    assert [
        item["event"]
        for item in queries.history(
            event["device_id"],
            run_id=first["run_id"],
            start="2026-01-01T00:00:06Z",
            end="2026-01-01T00:00:10Z",
        )["items"]
    ] == [second]
    assert len(queries.history(event["device_id"], run_id=first["run_id"])["items"]) == 2
    assert queries.history("missing-" + str(uuid.uuid4())) == {"items": [], "next_before": None}
    assert latest.get("missing-" + str(uuid.uuid4())) is None
    assert queries.latest(event["device_id"]).event == reset


def test_empty_and_corrupt_cache_recovery_rebuild_and_old_writer_guard(data, event):
    inbox, queries, cache = data
    event["device_id"] = "recover-" + str(uuid.uuid4())
    assert accept(inbox, event, 0)
    old = queries.latest(event["device_id"])
    newer = dict(event, event_id=str(uuid.uuid4()), temperature_c=90.0)
    assert accept(inbox, newer, 1)
    latest = LatestState(queries, cache)
    assert cache.get(event["device_id"]) is None
    assert latest.get(event["device_id"]).event == newer
    assert cache.put(old) is False  # Delayed writer cannot undo a concurrent newer refresh.
    assert cache.get(event["device_id"]).event == newer
    cache.client.hset(cache.key(event["device_id"]), mapping={"event": "malformed"})
    assert latest.get(event["device_id"]).event == newer
    cache.client.delete(cache.key(event["device_id"]))
    rebuilt = latest.rebuild()
    assert rebuilt["failed"] == 0 and rebuilt["refreshed"] >= 1
    assert cache.get(event["device_id"]).event == newer
    page = queries.latest_page(limit=1)
    next_page = queries.latest_page(after_device=page[0].event["device_id"], limit=1)
    if next_page:
        assert next_page[0].event["device_id"] > page[0].event["device_id"]


def test_cache_expiry_and_bigint_version_comparison(data, event):
    _, _, cache = data
    cache.ttl = 1
    event["device_id"] = "precision-" + str(uuid.uuid4())
    assert cache.put(Reading(2**53 + 1, event))
    assert not cache.put(Reading(2**53, dict(event, temperature_c=99)))
    assert cache.get(event["device_id"]).event == event
    deadline = time.monotonic() + 3
    while cache.get(event["device_id"]) is not None and time.monotonic() < deadline:
        time.sleep(0.05)
    assert cache.get(event["device_id"]) is None


def test_redis_connection_failure_does_not_block_durable_offset_commit(data, event):
    inbox, queries, healthy_cache = data
    event["device_id"] = "outage-" + str(uuid.uuid4())
    group = "outage-" + str(uuid.uuid4())
    offsets = watermarks("device.telemetry.v1")
    unavailable = RedisLatest("redis://redis:1/0")
    consumer = reader("device.telemetry.v1", offsets, group)
    try:
        with pytest.raises(CacheUnavailable):
            unavailable.get(event["device_id"])
        send(json.dumps(event).encode(), event["device_id"].encode())
        message = receive(consumer)
        latest = LatestState(queries, unavailable)
        result = Processor(
            inbox,
            KafkaDeadLetters(dlq_producer(bootstrap())),
            refresh_latest=latest.refresh,
        ).process(
            record_from(message), lambda: consumer.commit(message=message, asynchronous=False)
        )
        assert result["outcome"] == "persisted" and result["latest_cache"] == "degraded"
        committed = consumer.committed(
            [TopicPartition(message.topic(), message.partition())],
            timeout=5,
        )[0].offset
        assert committed == message.offset() + 1
        assert latest.get(event["device_id"]).event == event
        assert LatestState(queries, healthy_cache).get(event["device_id"]).event == event
        assert healthy_cache.get(event["device_id"]).event == event
    finally:
        consumer.close()
        unavailable.close()


def test_migration_preserves_existing_inbox_and_is_repeatable(event):
    schema = "migration_" + uuid.uuid4().hex
    dsn = make_conninfo(database_dsn(), options=f"-c search_path={schema}")
    with psycopg.connect(database_dsn(), autocommit=True) as admin:
        admin.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
        try:
            with psycopg.connect(dsn) as connection:
                connection.execute((Path("migrations") / "001_telemetry_inbox.sql").read_text())
            inbox = PostgresInbox(dsn)
            try:
                assert accept(inbox, event, 10)
                newer = dict(event, event_id=str(uuid.uuid4()), temperature_c=77)
                assert accept(inbox, newer, 11)
            finally:
                inbox.close()
            assert len(migrate(dsn)) == 2
            assert migrate(dsn) == []
            queries = TelemetryQueries(dsn)
            try:
                assert len(queries.history(event["device_id"])["items"]) == 2
                assert queries.latest(event["device_id"]).event == newer
                order = queries.latest(event["device_id"]).ingestion_order
                inbox = PostgresInbox(dsn)
                try:
                    assert not accept(inbox, event, 12)
                    newest = dict(newer, event_id=str(uuid.uuid4()))
                    assert accept(inbox, newest, 13)
                finally:
                    inbox.close()
                assert queries.latest(event["device_id"]).ingestion_order > order
            finally:
                queries.close()
        finally:
            admin.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))
