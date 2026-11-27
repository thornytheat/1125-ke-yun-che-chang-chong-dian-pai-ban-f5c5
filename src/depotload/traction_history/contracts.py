from dataclasses import dataclass
from math import isfinite


@dataclass(frozen=True, slots=True)
class TractionLog:
    trip: str
    departed: int
    completed: int
    booked: int
    distance_km: float
    uphill_m: float
    outside_c: float
    aux_minutes: float
    gross_draw_kwh: float
    recovered_kwh: float

    def __post_init__(self):
        numbers = (self.distance_km, self.uphill_m, self.outside_c, self.aux_minutes,
                   self.gross_draw_kwh, self.recovered_kwh)
        if not all(isfinite(v) for v in numbers):
            raise ValueError("非法牵引测值")
        if not 0 < self.distance_km <= 500 or self.uphill_m < 0 or self.aux_minutes < 0:
            raise ValueError("牵引记录里程或辅助时长有误")
        if self.departed >= self.completed or self.booked < self.completed:
            raise ValueError("完结及入账时间必须有序")
        if not 0 <= self.recovered_kwh < self.gross_draw_kwh:
            raise ValueError("再生电量超出牵引取电量")

    @property
    def features(self):
        cold_degree_hours = max(0.0, 15.0 - self.outside_c) * self.aux_minutes / 60
        return self.distance_km, self.uphill_m / 100, cold_degree_hours

    @property
    def response(self) -> float:
        return self.gross_draw_kwh - self.recovered_kwh


@dataclass(frozen=True, slots=True)
class Scale:
    mean: tuple[float, ...]
    spread: tuple[float, ...]
    rows: int

    def project(self, features: tuple[float, ...]) -> tuple[float, ...]:
        if len(features) != len(self.mean):
            raise ValueError("牵引特征列数不符")
        return tuple((value - center) / sigma
                     for value, center, sigma in zip(features, self.mean, self.spread, strict=True))


@dataclass(frozen=True, slots=True)
class HistoricalMatrix:
    earlier: tuple[TractionLog, ...]
    held_out: tuple[TractionLog, ...]
    not_booked: tuple[str, ...]
    bad_rows: tuple[str, ...]
    scale: Scale
