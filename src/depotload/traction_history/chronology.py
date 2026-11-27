from math import fsum, sqrt, isfinite
from collections import Counter
from collections.abc import Iterable

from .contracts import HistoricalMatrix, Scale, TractionLog


def fit_scale(matrix: Iterable[tuple[float, ...]], floor: float = 1e-8) -> Scale:
    if floor <= 0 or not isfinite(floor):
        raise ValueError("缩放下限必须是有限正数")
    material = tuple(matrix)
    if not material or not material[0]:
        raise ValueError("空训练窗口")
    if any(len(row) != len(material[0]) for row in material):
        raise ValueError("牵引特征列不对齐")
    columns = tuple(zip(*material, strict=True))
    centers = []
    spreads = []
    for column in columns:
        if not all(isfinite(x) for x in column):
            raise ValueError("特征缺少有限测值")
        center = fsum(column) / len(column)
        centers.append(center)
        variance = fsum((x - center) ** 2 for x in column) / len(column)
        spreads.append(max(floor, sqrt(variance)))
    return Scale(tuple(centers), tuple(spreads), len(material))


def operating_split(rows: Iterable[dict], train_end: int, available_at: int) -> HistoricalMatrix:
    if train_end > available_at:
        raise ValueError("训练时钟晚于推算时钟")
    early = []
    held = []
    delayed = []
    failed = []
    valid = []
    fingerprints = Counter()
    for raw in rows:
        trip = str(raw.get("trip", "")).strip()
        try:
            value = TractionLog(**raw)
            if not trip:
                raise ValueError("缺少牵引班次")
        except (TypeError, ValueError) as error:
            failed.append(f"{trip}: {error}")
            continue
        if value.booked > available_at:
            delayed.append(trip)
            continue
        valid.append(value)
        fingerprints[trip] += 1
    for item in sorted(valid, key=lambda value: (value.completed, value.trip)):
        if fingerprints[item.trip] > 1:
            failed.append(f"{item.trip}: 重复已关账班次")
        elif item.completed < train_end and item.booked <= train_end:
            early.append(item)
        else:
            held.append(item)
    matrix = fit_scale(record.features for record in early)
    return HistoricalMatrix(tuple(early), tuple(held), tuple(sorted(delayed)), tuple(sorted(set(failed))), matrix)


def kwh_by_time(logs: Iterable[TractionLog], step: int) -> dict[int, float]:
    if step <= 0:
        raise ValueError("分组步长须为正")
    parts = {}
    for event in logs:
        bucket = event.completed // step * step
        parts.setdefault(bucket, []).append(event.response)
    return {key: fsum(parts[key]) for key in sorted(parts)}
