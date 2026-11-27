"""HTTP response contracts, preserving the accepted telemetry event shape."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class TelemetryEvent(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    event_id: UUID
    run_id: UUID
    device_id: str
    timestamp: str
    firmware_version: str
    temperature_c: float
    power_draw_w: float = Field(ge=0)
    cpu_utilization_pct: float = Field(ge=0, le=100)
    memory_utilization_pct: float = Field(ge=0, le=100)
    timing_jitter_ms: float = Field(ge=0)
    error_count: int = Field(ge=0)
    device_state: Literal["HEALTHY", "WARNING", "CRITICAL", "FAILED"]
    actuator_load_pct: float | None = Field(default=None, ge=0, le=100)
    position_error_mm: float | None = Field(default=None, ge=0)


class ReadingResponse(BaseModel):
    ingestion_order: int = Field(gt=0)
    event: TelemetryEvent


class DeviceDetail(ReadingResponse):
    data_mode: Literal["simulated"]


class DevicePage(BaseModel):
    data_mode: Literal["simulated"]
    items: list[ReadingResponse]
    next_after_device: str | None


class HistoryPage(BaseModel):
    data_mode: Literal["simulated"]
    items: list[ReadingResponse]
    next_before: int | None


class StateCounts(BaseModel):
    HEALTHY: int = Field(ge=0)
    WARNING: int = Field(ge=0)
    CRITICAL: int = Field(ge=0)
    FAILED: int = Field(ge=0)


class FleetSummary(BaseModel):
    data_mode: Literal["simulated"]
    total_devices: int = Field(ge=0)
    by_state: StateCounts


class Liveness(BaseModel):
    status: Literal["alive"]


class Readiness(BaseModel):
    status: Literal["ready"]
    database: Literal["up"]
    cache: Literal["up", "degraded", "disabled"]


class ErrorBody(BaseModel):
    code: str
    message: str


class ErrorResponse(BaseModel):
    error: ErrorBody


AlertStatus = Literal["ACTIVE", "ACKNOWLEDGED", "RESOLVED"]
AlertSeverity = Literal["WARNING", "CRITICAL", "FAILURE"]


class Alert(BaseModel):
    alert_id: UUID
    alert_order: int = Field(gt=0)
    device_id: str
    run_id: UUID
    rule_id: str
    source: Literal["simulator"]
    severity: AlertSeverity
    status: AlertStatus
    message: str
    opening_event_id: UUID
    last_event_id: UUID
    resolved_event_id: UUID | None
    opened_event_time: datetime
    last_event_time: datetime
    resolved_event_time: datetime | None
    created_at: datetime
    updated_at: datetime
    acknowledged_at: datetime | None
    resolved_at: datetime | None
    resolution_reason: Literal["recovered", "superseded", "lifecycle_changed"] | None


class AlertDetail(Alert):
    data_mode: Literal["simulated"]


class AlertPage(BaseModel):
    data_mode: Literal["simulated"]
    items: list[Alert]
    next_before: int | None
