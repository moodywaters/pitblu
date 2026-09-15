from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


def utc_now() -> datetime:
    return datetime.now(UTC)


class ApiModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")


class CookState(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    COOKING_FINISHED = "cooking_finished"
    RESTING = "resting"
    SERVED = "served"
    CLOSED = "closed"


class MeasurementKind(StrEnum):
    FOOD = "food"
    COOKER = "cooker"
    OTHER = "other"


class AlertSeverity(StrEnum):
    PROMPT = "prompt"
    ATTENTION = "attention"
    ALARM = "alarm"


class AlertStatus(StrEnum):
    ACTIVE = "active"
    ACKNOWLEDGED = "acknowledged"
    RESOLVED = "resolved"


class CookCreate(ApiModel):
    name: str | None = Field(None, min_length=1, max_length=120)
    anticipated_serve_at: datetime | None = Field(None, alias="anticipatedServeAt")
    cooker_profile_id: str | None = Field(None, alias="cookerProfileId")
    cooker_profile_ids: list[str] = Field(default_factory=list, alias="cookerProfileIds")


class ThermometerRegistration(ApiModel):
    discovery_id: str = Field(alias="discoveryId", min_length=1, max_length=200)
    friendly_name: str | None = Field(None, alias="friendlyName", min_length=1, max_length=120)


class CookPatch(ApiModel):
    name: str | None = Field(None, min_length=1, max_length=120)
    anticipated_serve_at: datetime | None = Field(None, alias="anticipatedServeAt")


class NamedCreate(ApiModel):
    name: str = Field(min_length=1, max_length=120)


class NamedPatch(ApiModel):
    name: str = Field(min_length=1, max_length=120)


class CookerProfileCreate(ApiModel):
    name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(None, max_length=500)


class CookerProfilePatch(ApiModel):
    name: str | None = Field(None, min_length=1, max_length=120)
    description: str | None = Field(None, max_length=500)


class MeasurementCreate(ApiModel):
    label: str = Field(min_length=1, max_length=120)
    kind: MeasurementKind
    cooker_id: str | None = Field(None, alias="cookerId")
    food_item_id: str | None = Field(None, alias="foodItemId")
    target_temperature_c: float | None = Field(None, alias="targetTemperatureC")
    approaching_margin_c: float = Field(3.0, ge=0, le=50, alias="approachingMarginC")
    range_min_c: float | None = Field(None, alias="rangeMinC")
    range_max_c: float | None = Field(None, alias="rangeMaxC")
    range_persistence_seconds: int = Field(120, ge=0, alias="rangePersistenceSeconds")

    @model_validator(mode="after")
    def valid_range(self) -> MeasurementCreate:
        if (
            self.range_min_c is not None
            and self.range_max_c is not None
            and self.range_min_c >= self.range_max_c
        ):
            raise ValueError("rangeMinC must be below rangeMaxC")
        return self


class MeasurementPatch(ApiModel):
    label: str | None = Field(None, min_length=1, max_length=120)
    target_temperature_c: float | None = Field(None, alias="targetTemperatureC")
    approaching_margin_c: float | None = Field(None, ge=0, le=50, alias="approachingMarginC")
    range_min_c: float | None = Field(None, alias="rangeMinC")
    range_max_c: float | None = Field(None, alias="rangeMaxC")
    range_persistence_seconds: int | None = Field(None, ge=0, alias="rangePersistenceSeconds")


class AssignmentCreate(ApiModel):
    measurement_id: str = Field(alias="measurementId")
    core_device_id: str = Field(min_length=1, max_length=200, alias="coreDeviceId")
    probe_channel: int = Field(ge=1, alias="probeChannel")


class TelemetryIn(ApiModel):
    core_device_id: str = Field(min_length=1, alias="coreDeviceId")
    probe_channel: int = Field(ge=1, alias="probeChannel")
    temperature_c: float | None = Field(None, alias="temperatureC")
    observed_at: datetime = Field(alias="observedAt")
    available: bool = True
    event_id: str | None = Field(None, alias="eventId")


class CookEventCreate(ApiModel):
    type: Literal[
        "added_fuel",
        "adjusted_vents",
        "spritzed",
        "wrapped",
        "checked_meat",
        "moved_to_oven",
        "started_rest",
        "note",
    ]
    note: str | None = Field(None, max_length=1000)
    occurred_at: datetime | None = Field(None, alias="occurredAt")


class ShareCreate(ApiModel):
    pass


class DomainError(RuntimeError):
    def __init__(self, message: str, status: int = 409, code: str = "state_conflict") -> None:
        super().__init__(message)
        self.status = status
        self.code = code


JsonObject = dict[str, Any]
