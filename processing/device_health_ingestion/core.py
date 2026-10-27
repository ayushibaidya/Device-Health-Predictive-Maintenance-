import time
from dataclasses import dataclass
from typing import Callable, Protocol

from .errors import PermanentProcessingError, TransientProcessingError, ValidationError
from .validation import validate


@dataclass(frozen=True)
class Record:
    topic: str
    partition: int
    offset: int
    key: bytes | None
    payload: bytes | None


class Inbox(Protocol):
    def persist(self, event: dict, record: Record) -> bool:
        """Commit the event durably; return False for an identical duplicate."""
        ...


class DeadLetters(Protocol):
    def send(self, record: Record, reason: str) -> None:
        """Return only after broker acknowledgement; otherwise raise."""
        ...


class Processor:
    def __init__(self, inbox: Inbox, dlq: DeadLetters, *, attempts=5, sleep=time.sleep):
        if not 1 <= attempts <= 10:
            raise ValueError("retry attempts must be in [1, 10]")
        self.inbox, self.dlq, self.attempts, self.sleep = inbox, dlq, attempts, sleep

    def _retry(self, operation):
        for attempt in range(self.attempts):
            try:
                return operation()
            except TransientProcessingError:
                if attempt + 1 == self.attempts:
                    raise
                self.sleep(min(0.25 * 2**attempt, 2.0))
        raise AssertionError("unreachable")

    def process(self, record: Record, commit: Callable[[], None]) -> dict:
        try:
            event = validate(record.payload, record.key)
            inserted = self._retry(lambda: self.inbox.persist(event, record))
            result = {
                "outcome": "persisted" if inserted else "duplicate",
                "event_id": event["event_id"],
                "device_id": event["device_id"],
            }
        except (ValidationError, PermanentProcessingError) as error:
            reason = str(error)
            self._retry(lambda: self.dlq.send(record, reason))
            result = {"outcome": "dlq"}
        # A commit failure propagates. Redelivery is safe because the inbox is idempotent.
        commit()
        return result
