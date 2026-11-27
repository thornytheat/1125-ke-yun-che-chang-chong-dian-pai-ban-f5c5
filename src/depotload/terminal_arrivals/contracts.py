from dataclasses import dataclass
from enum import StrEnum
from math import isfinite


class ArrivalFault(StrEnum):
    INVALID_CLOCK = "INVALID_CLOCK"
    INVALID_ODOMETER = "INVALID_ODOMETER"
    INVALID_SOC = "INVALID_SOC"
    INVALID_IDENTITY = "INVALID_IDENTITY"
    BAD_BATTERY_RATING = "BAD_BATTERY_RATING"
    STALE_PACKET = "STALE_PACKET"
    REVISION_CONFLICT = "REVISION_CONFLICT"


@dataclass(frozen=True, slots=True)
class Arrival:
    duty: str
    coach: str
    depot: str
    received: int
    departure: int
    observed: int
    revision: int
    odometer_km: float
    state_pct: float
    battery_kwh: float
    route_km: float
    ambient_c: float
    lift_required: bool

    @property
    def dwell(self) -> int:
        return self.departure - self.observed

    @property
    def energy_remaining(self) -> float:
        return self.battery_kwh * self.state_pct / 100

    @property
    def identity(self) -> tuple[str, str]:
        return self.depot, self.duty


@dataclass(frozen=True, slots=True)
class Reject:
    duty: str
    revision: int
    reason: ArrivalFault
    details: str


def numeric(value: object, low: float, high: float) -> float:
    if isinstance(value, bool):
        raise ValueError("boolean reading")
    number = float(value)
    if not isfinite(number) or not low <= number <= high:
        raise ValueError("reading outside engineering range")
    return number


def minute(value: object) -> int:
    number = numeric(value, 0, 3000)
    if number != int(number):
        raise ValueError("fractional minute")
    return int(number)
