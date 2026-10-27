from types import SimpleNamespace

import pytest

from device_health_ingestion.worker import caught_up


@pytest.mark.parametrize(
    "position,high,expected",
    [
        (None, 0, False),
        (-1001, 0, True),
        (-1001, 9, False),
        (0, 9, False),
        (9, 9, True),
        (9, 10, False),
    ],
)
def test_drain_waits_for_assignment_and_all_available_records(position, high, expected):
    class Consumer:
        def assignment(self):
            return [] if position is None else [SimpleNamespace(offset=position)]

        def position(self, assignment):
            return assignment

        def get_watermark_offsets(self, partition, timeout):
            return 0, high

    assert caught_up(Consumer()) is expected
