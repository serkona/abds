from datetime import date
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

ID = Annotated[int, Field(strict=True, gt=0, le=2**64 - 1)]
ReadingValue = Annotated[int, Field(strict=True, ge=0, le=2**32 - 1)]


def parse_date(value):
    if not isinstance(value, str) or len(value) != 10:
        raise ValueError("Expected YYYY-MM-DD")
    parsed = date.fromisoformat(value)
    if parsed.isoformat() != value:
        raise ValueError("Expected YYYY-MM-DD")
    return parsed


class UserPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    fio: str | None = None
    phone: str | None = None

    @field_validator("fio", "phone", mode="before")
    @classmethod
    def nonempty_string(cls, value):
        if not isinstance(value, str) or not value.strip():
            raise ValueError("Expected a nonempty string")
        return value.strip()

    @model_validator(mode="after")
    def not_empty(self):
        if not self.model_fields_set:
            raise ValueError("At least one field is required")
        return self


class Reading(BaseModel):
    model_config = ConfigDict(extra="forbid")
    user_id: ID
    gauge_id: ID
    tariff_id: ID
    reading_date: date
    day_kw: ReadingValue
    night_kw: ReadingValue

    @field_validator("reading_date", mode="before")
    @classmethod
    def valid_date(cls, value):
        day = parse_date(value)
        if not date(1970, 1, 1) <= day <= date(2149, 6, 6):
            raise ValueError("Date is outside the ClickHouse Date range")
        return day


class GaugeInstallation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    gauge_id: ID
