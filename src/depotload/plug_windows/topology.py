from dataclasses import dataclass
from collections import defaultdict
from .contracts import Plug, Supply, Interval
from .occupancy import free_segments, supply_by_circuit

@dataclass(frozen=True, slots=True)
class FeederSummary:
    feed: str
    start: int
    stop: int
    grid_cap: float
    rated_kw: float
    usable_kw: float
    bays: tuple[str, ...]
    accessible_bays: tuple[str, ...]

def supply_capacity_report(plugs, feeds, at, through, step=15):
    if step<1 or at>=through:
        raise ValueError("接线报告时间非法")
    index=defaultdict(list)
    for plug in plugs:
        index[plug.circuit].append(plug)
    windows=supply_by_circuit(feeds)
    rows=[]
    start=(at+step-1)//step*step
    for circuit, entries in sorted(windows.items()):
        for minute in range(start,through-step+1,step):
            envelope=Interval(minute,minute+step)
            main=next((row.kw for row in entries if row.span.start<=minute and row.span.stop>=minute+step),0.)
            attached=[plug for plug in index.get(circuit,()) if free_segments(envelope,plug.outages)==(envelope,)]
            combined=sum(plug.kw for plug in attached)
            bay_ids=tuple(sorted(plug.bay for plug in attached))
            lift_ids=tuple(sorted(plug.bay for plug in attached if plug.accessible))
            rows.append(FeederSummary(circuit,minute,minute+step,main,combined,min(main,combined),bay_ids,lift_ids))
    return tuple(rows)

def usable_coverage(cells):
    totals=defaultdict(lambda: {"possible_kwh": 0.,"accessible_minutes": 0})
    for entry in cells:
        target=totals[entry.feed]
        target["possible_kwh"]+=entry.usable_kw*(entry.stop-entry.start)/60
        if entry.usable_kw and entry.accessible_bays:
            target["accessible_minutes"]+=entry.stop-entry.start
    return [dict(data,feeder=key) for key,data in sorted(totals.items())]
