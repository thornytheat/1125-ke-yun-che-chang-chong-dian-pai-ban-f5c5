from dataclasses import dataclass
from math import fsum, isfinite

from ..traction_history.contracts import Scale


@dataclass(frozen=True, slots=True)
class Forecast:
    route_kwh: float
    center_kwh: float
    band_kwh: float
    ood: bool
    flags: tuple[str, ...]

    def with_reserve(self, reserve: float) -> float:
        if not isfinite(reserve) or reserve < 0:
            raise ValueError("备用电量应为非负数")
        return self.route_kwh + reserve


@dataclass(frozen=True, slots=True)
class EnergyModel:
    slope: tuple[float, ...]
    center: float
    scale: Scale
    calibration: tuple[float, ...]
    ridge: float
    z_limit: float

    def predict_center(self, vector: tuple[float, ...]) -> float:
        projected = self.scale.project(vector)
        return max(0.0, self.center + fsum(x*w for x,w in zip(projected, self.slope, strict=True)))

    def feature_distance(self, vector: tuple[float, ...]) -> float:
        scores = self.scale.project(vector)
        return max(abs(score) for score in scores)

    @property
    def calibration_n(self) -> int:
        return len(self.calibration)


@dataclass(frozen=True, slots=True)
class ResidualScore:
    mean_abs_kwh: float | None
    cover_share: float | None
    observed: int
    covered: int

    @classmethod
    def empty(cls):
        return cls(None, None, 0, 0)
