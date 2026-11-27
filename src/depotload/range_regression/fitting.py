from math import ceil, fsum, isfinite
from dataclasses import replace

from ..traction_history.contracts import HistoricalMatrix
from .contracts import Forecast, EnergyModel, ResidualScore


def solve(gram: list[list[float]], response: list[float]) -> tuple[float, ...]:
    rows = [row[:] + [value] for row, value in zip(gram, response, strict=True)]
    for j in range(len(rows)):
        pivot = max(range(j, len(rows)), key=lambda i: abs(rows[i][j]))
        if abs(rows[pivot][j]) < 1e-13:
            raise ValueError("矩阵近似不可逆")
        rows[j], rows[pivot] = rows[pivot], rows[j]
        denominator = rows[j][j]
        rows[j] = [v / denominator for v in rows[j]]
        for i in range(len(rows)):
            if i == j:
                continue
            factor = rows[i][j]
            rows[i] = [a - factor * b for a, b in zip(rows[i], rows[j], strict=True)]
    return tuple(row[-1] for row in rows)


def train(history: HistoricalMatrix, ridge: float = 2.0, z_limit: float = 4.5) -> EnergyModel:
    if not isfinite(ridge) or not isfinite(z_limit) or ridge <= 0 or z_limit <= 0:
        raise ValueError("正则和距离门限应为有限正数")
    matrix = [history.scale.project(row.features) for row in history.earlier]
    y = [row.response for row in history.earlier]
    avg = fsum(y) / len(y)
    cols = tuple(zip(*matrix, strict=True))
    gram = [[fsum(a*b for a,b in zip(f, g, strict=True)) + (ridge if i == j else 0)
             for j, g in enumerate(cols)] for i, f in enumerate(cols)]
    cross = [fsum(x*(actual - avg) for x, actual in zip(col, y, strict=True)) for col in cols]
    fitted = EnergyModel(solve(gram, cross), avg, history.scale, (), ridge, z_limit)
    residuals = [abs(fitted.predict_center(row.features) - row.response) for row in history.held_out]
    return replace(fitted, calibration=tuple(sorted(residuals)))


def finite_sample_band(errors: tuple[float, ...], coverage: float) -> float | None:
    if not 0 < coverage < 1:
        raise ValueError("区间覆盖率需要严格位于零一之间")
    n = len(errors)
    rank = ceil((n + 1) * coverage)
    if not n or rank > n:
        return None
    return sorted(errors)[rank - 1]


def forecast(model: EnergyModel, vector: tuple[float, ...], coverage: float = .8) -> Forecast:
    center = model.predict_center(vector)
    gap = finite_sample_band(model.calibration, coverage)
    outside = model.feature_distance(vector) > model.z_limit
    flags = []
    if outside:
        flags.append("工况超出标定范围")
    if gap is None:
        flags.append("留出班次不足")
    # Sparse calibration and OOD indicate manual release; the upper estimate remains provisional.
    floor = max(4.0, center * .12) if gap is None or outside else 0.0
    pad = max(gap or 0.0, floor)
    return Forecast(round(center + pad, 4), round(center, 4), round(pad, 4), outside, tuple(flags))
