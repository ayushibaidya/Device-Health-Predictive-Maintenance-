"""Disposable Redis latest-state cache backed by PostgreSQL."""

import hashlib
import json
import os

import redis
from redis.backoff import NoBackoff
from redis.retry import Retry

from .errors import TransientProcessingError, ValidationError
from .queries import Reading
from .validation import validate


class CacheUnavailable(Exception):
    pass


# Decimal-string comparison preserves bigint precision beyond Lua's 2**53 limit.
# One atomic script prevents a delayed rebuild from replacing a newer reading.
UPDATE_LATEST = """
local old = redis.call('HGET', KEYS[1], 'order')
local incoming = ARGV[1]
if old and string.match(old, '^[1-9][0-9]*$') then
    if #old > #incoming or (#old == #incoming and old > incoming) then return 0 end
end
redis.call('HSET', KEYS[1], 'order', incoming, 'event', ARGV[2])
redis.call('EXPIRE', KEYS[1], ARGV[3])
return 1
"""


class RedisLatest:
    def __init__(self, url, *, ttl=30, prefix="device-health:latest:v1:"):
        if type(ttl) is not int or not 1 <= ttl <= 3600:
            raise ValueError("cache TTL must be an integer in [1, 3600]")
        self.ttl, self.prefix = ttl, prefix
        self.client = redis.Redis.from_url(
            url,
            decode_responses=True,
            socket_connect_timeout=0.5,
            socket_timeout=0.5,
            retry=Retry(NoBackoff(), 0),
        )

    def key(self, device_id):
        return self.prefix + hashlib.sha256(device_id.encode()).hexdigest()

    def get(self, device_id):
        try:
            fields = self.client.hgetall(self.key(device_id))
            if not fields:
                return None
            order = int(fields["order"])
            if order <= 0:
                raise ValueError("invalid cache order")
            event = validate(fields["event"].encode(), device_id.encode())
            return Reading(order, event)
        except (redis.RedisError, ValueError, KeyError, UnicodeError, ValidationError) as error:
            raise CacheUnavailable("latest-state cache unavailable or invalid") from error

    def put(self, reading):
        try:
            return bool(
                self.client.eval(
                    UPDATE_LATEST,
                    1,
                    self.key(reading.event["device_id"]),
                    str(reading.ingestion_order),
                    json.dumps(reading.event, allow_nan=False),
                    self.ttl,
                )
            )
        except redis.RedisError as error:
            raise CacheUnavailable("latest-state cache unavailable") from error

    def close(self):
        self.client.close()


def configured_cache():
    url = os.getenv("REDIS_URL")
    return RedisLatest(url, ttl=int(os.getenv("LATEST_CACHE_TTL_SECONDS", "30"))) if url else None


class LatestState:
    def __init__(self, queries, cache=None):
        self.queries, self.cache = queries, cache

    def _cache(self, reading):
        if self.cache is None:
            return False
        try:
            if reading is not None:
                self.cache.put(reading)
            return True
        except CacheUnavailable:
            return False

    def get(self, device_id):
        if self.cache is not None:
            try:
                reading = self.cache.get(device_id)
                if reading is not None:
                    return reading
            except CacheUnavailable:
                pass
        reading = self.queries.latest(device_id)
        self._cache(reading)
        return reading

    def refresh(self, device_id):
        # Always read the durable latest row, including when processing a duplicate.
        # A failed derived-state update must not prevent a durable Kafka offset commit.
        try:
            return self._cache(self.queries.latest(device_id))
        except TransientProcessingError:
            return False

    def rebuild(self):
        if self.cache is None:
            raise ValueError("Configure REDIS_URL to rebuild latest state")
        after, refreshed, failed = "", 0, 0
        while True:
            page = self.queries.latest_page(after_device=after)
            for reading in page:
                if self._cache(reading):
                    refreshed += 1
                else:
                    failed += 1
            if len(page) < 500:
                return {"refreshed": refreshed, "failed": failed}
            after = page[-1].event["device_id"]
