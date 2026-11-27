from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum


class GateIssue(StrEnum):
    SHIFT_TOTAL_DIFF = "SHIFT_TOTAL_DIFF"
    DUTY_BALANCE_DIFF = "DUTY_BALANCE_DIFF"
    UNAPPROVED_CHARGE = "UNAPPROVED_CHARGE"
    GRID_OVERLOAD = "GRID_OVERLOAD"
    LEAVE_LATE = "LEAVE_LATE"
    COACH_COLLISION = "COACH_COLLISION"
    BAY_COLLISION = "BAY_COLLISION"
    UNKNOWN_DUTY = "UNKNOWN_DUTY"
    NONPOSITIVE_LOAD = "NONPOSITIVE_LOAD"


@dataclass(frozen=True, slots=True)
class Issue:
    name: GateIssue
    key: tuple[str, ...]
    evidence: str


@dataclass(frozen=True, slots=True)
class Handover:
    issues: tuple[Issue, ...]
    actual_kwh: Decimal
    demand_kwh: Decimal
    assigned_trips: int
    fingerprint: str

    @property
    def ready(self) -> bool:
        return not self.issues

    @property
    def coverage_share(self) -> float | None:
        if self.demand_kwh <= 0:
            return None
        return round(float(self.actual_kwh / self.demand_kwh), 5)


@dataclass(frozen=True, slots=True)
class RiskMetrics:
    alerted: int
    false_alerts: int
    critical: int
    missed: int

    @property
    def recall(self) -> float | None:
        return (self.critical - self.missed) / self.critical if self.critical else None

    @property
    def precision(self) -> float | None:
        return (self.alerted - self.false_alerts) / self.alerted if self.alerted else None
