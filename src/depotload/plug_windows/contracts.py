from dataclasses import dataclass
from math import isfinite


@dataclass(frozen=True, slots=True, order=True)
class Interval:
    start: int
    stop: int

    def __post_init__(self):
        if type(self.start) is not int or type(self.stop) is not int or self.stop <= self.start:
            raise ValueError("插枪时段结束须晚于开始")

    def overlaps(self, other: "Interval") -> bool:
        return self.start < other.stop and other.start < self.stop

    def intersection(self, other: "Interval") -> "Interval | None":
        if not self.overlaps(other):
            return None
        return Interval(max(self.start, other.start), min(self.stop, other.stop))

    @property
    def minutes(self) -> int:
        return self.stop - self.start


@dataclass(frozen=True, slots=True)
class Plug:
    bay: str
    circuit: str
    kw: float
    accessible: bool
    outages: tuple[Interval, ...] = ()

    def __post_init__(self):
        if not self.bay or not self.circuit or not isfinite(self.kw) or self.kw <= 0:
            raise ValueError("充电桩参数有误")


@dataclass(frozen=True, slots=True)
class Supply:
    circuit: str
    span: Interval
    kw: float

    def __post_init__(self):
        if not self.circuit or not isfinite(self.kw) or self.kw < 0:
            raise ValueError("馈线功率不可为负")


@dataclass(frozen=True, slots=True)
class Opportunity:
    span: Interval
    plug: Plug
    input_kw: float

    @property
    def available_kwh(self) -> float:
        return self.input_kw * self.span.minutes / 60
