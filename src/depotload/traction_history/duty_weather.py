from math import fsum, isfinite
from statistics import median
from .contracts import TractionLog

def percentile(values: list[float], fraction: float) -> float:
    if not values or not 0 <= fraction <= 1:
        raise ValueError("分位数超限或支持集为空")
    if not all(isfinite(x) for x in values):
        raise ValueError("牵引耗电记录必须为有限值")
    ranks = sorted(values)
    index = fraction * (len(ranks)-1)
    below = int(index)
    weight = index-below
    if not weight:
        return ranks[below]
    return (1-weight)*ranks[below] + weight*ranks[below+1]

def weather_band(temp):
    if temp < 5:
        return "冷车"
    if temp < 15:
        return "温控运行"
    return "常温"

def energy_weather_overview(logs: tuple[TractionLog, ...]) -> list[dict]:
    segments = {name: [] for name in ("冷车", "温控运行", "常温")}
    for entry in logs:
        segments[weather_band(entry.outside_c)].append(entry)
    response = []
    for key, entries in segments.items():
        if not entries:
            response.append({"temperature_band": key, "count": 0, "median_wh_per_km": None,
                             "p85_wh_per_km": None, "energy_return_share": None})
            continue
        rates = [trip.response/trip.distance_km*1000 for trip in entries]
        restored = fsum(trip.recovered_kwh for trip in entries)
        draw = fsum(trip.gross_draw_kwh for trip in entries)
        response.append({"temperature_band": key, "count": len(entries),
                         "median_wh_per_km": round(median(rates), 2),
                         "p85_wh_per_km": round(percentile(rates, .85), 2),
                         "energy_return_share": round(restored/draw, 5)})
    return response

def track_energy(log: TractionLog, cold_degree_delta: float) -> dict:
    if not -45 <= cold_degree_delta <= 45:
        raise ValueError("冷暖工况扰动超出复盘合理范围")
    changed = log.outside_c+cold_degree_delta
    old = max(0.0, 15-log.outside_c)
    new = max(0.0, 15-changed)
    return {"trip": log.trip, "grade": weather_band(changed),
            "correction_degree_hours": round((new-old)*log.aux_minutes/60, 4)}
