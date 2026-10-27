class ValidationError(ValueError):
    """The record permanently violates the event contract."""


class PermanentProcessingError(Exception):
    """The record cannot be processed by retrying, e.g. conflicting event identity."""


class TransientProcessingError(Exception):
    """The record can be retried without acknowledging its Kafka offset."""
