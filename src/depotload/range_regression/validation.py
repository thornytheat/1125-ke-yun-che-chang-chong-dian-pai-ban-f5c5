from dataclasses import dataclass
from math import fsum
from .contracts import EnergyModel
from .fitting import forecast

@dataclass(frozen=True, slots=True)
class ValidationBand:
    bucket: str
    rows: int
    mae: float | None
    coverage: float | None
    manual_count: int
    mean_underprediction: float | None

def floor_case(trip, limits):
    for limit in limits:
        if trip.distance_km < limit:
            return f"< {limit} km"
    return f"≥ {limits[-1]} km"

def summarize_calibration(model: EnergyModel, entries, limits=(35,55,75)):
    if not limits or sorted(set(limits)) != list(limits) or limits[0]<=0:
        raise ValueError("里程误差分段须严格递增")
    active={**{f"< {limit} km":[] for limit in limits}, f"≥ {limits[-1]} km":[]}
    for ref in entries:
        estimate=forecast(model,ref.features)
        active[floor_case(ref,limits)].append((ref.response,estimate))
    results=[]
    for label,rows in active.items():
        if not rows:
            results.append(ValidationBand(label,0,None,None,0,None))
            continue
        distances=[abs(actual-guess.center_kwh) for actual,guess in rows]
        exceeded=[actual-guess.route_kwh for actual,guess in rows if actual>guess.route_kwh]
        covered=sum(actual<=estimate.route_kwh for actual,estimate in rows)
        manual=sum(bool(estimate.flags) for _,estimate in rows)
        results.append(ValidationBand(label,len(rows),round(fsum(distances)/len(rows),4),
                                      round(covered/len(rows),5),manual,
                                      round(fsum(exceeded)/len(exceeded),4) if exceeded else None))
    return tuple(results)

def climate_stress(model,route,uphill,base_temp,duration,changes):
    if duration<0 or route<0 or uphill<0:
        raise ValueError("气候复盘里程及工况非法")
    response=[]
    for shift in changes:
        temp=base_temp+shift
        features=(route,uphill/100,max(0,15-temp)*duration/60)
        prediction=forecast(model,features)
        response.append({"temperature":temp,"route":route,"upper_kwh":prediction.route_kwh,
                         "reserve_pad":prediction.band_kwh,"manual":bool(prediction.flags)})
    return response
