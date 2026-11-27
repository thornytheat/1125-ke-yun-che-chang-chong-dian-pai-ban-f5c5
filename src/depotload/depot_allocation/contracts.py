from dataclasses import dataclass
from decimal import Decimal
from math import isfinite

from ..plug_windows.contracts import Opportunity


@dataclass(frozen=True, slots=True)
class ChargeRequest:
    duty: str
    coach: str
    departure: int
    needed: float
    accessible: bool
    manual: bool
    opportunities: tuple[Opportunity, ...]

    def __post_init__(self):
        if not self.duty or not self.coach or not isfinite(self.needed) or self.needed < 0:
            raise ValueError("充电申请或补电量非法")


@dataclass(frozen=True, slots=True)
class Allocation:
    duty: str
    coach: str
    bay: str
    circuit: str
    start: int
    stop: int
    kwh: Decimal

    @property
    def minutes(self):
        return self.stop - self.start

    @property
    def raw_grid_kw(self):
        return self.kwh * Decimal(60) / Decimal(self.minutes)


@dataclass(frozen=True, slots=True)
class Order:
    duty: str
    state: str
    needed_kwh: Decimal
    assigned_kwh: Decimal
    reasons: tuple[str, ...]

    @property
    def deficit(self):
        return max(Decimal(0), self.needed_kwh - self.assigned_kwh)


@dataclass(frozen=True, slots=True)
class ShiftPlan:
    orders: tuple[Order, ...]
    cells: tuple[Allocation, ...]
    released: Decimal
