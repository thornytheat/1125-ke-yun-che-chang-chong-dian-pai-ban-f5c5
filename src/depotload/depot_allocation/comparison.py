from collections import defaultdict
from decimal import Decimal
from .priority import plan_shift

def feeder_delivery(cells, feeds):
    used=defaultdict(Decimal)
    routes=defaultdict(set)
    for row in cells:
        key=(row.circuit,row.start)
        used[key]+=row.kwh
        routes[key].add(row.duty)
    report=[]
    for (circuit,minute), available in sorted(feeds.items()):
        peak=used[(circuit,minute)]*Decimal(4)
        maximum=Decimal(str(available))
        share=(peak/maximum) if maximum else None
        report.append({"feeder":circuit,"minute":minute,"trips":len(routes[(circuit,minute)]),
                       "peak_kw":float(peak),"limit_kw":available,
                       "ratio":round(float(share),5) if share is not None else None})
    return report

def compare_peak_limit(requests, feeds, quota, baseline, ceilings):
    place={row.duty:row for row in baseline.orders}
    comparisons=[]
    for cap in ceilings:
        shifted=plan_shift(requests, feeds, quota, cap)
        fixed={row.duty:row for row in shifted.orders}
        lost=sorted(key for key,r in place.items() if r.state=="安排充电" and fixed[key].state!="安排充电")
        gained=sorted(key for key,r in fixed.items() if r.state=="安排充电" and place[key].state!="安排充电")
        comparisons.append({"limit_kw":cap,"scheduled":sum(x.state=="安排充电" for x in shifted.orders),
                            "lost":lost,"newly_scheduled":gained,
                            "shift_net_kwh":float(shifted.released-baseline.released)})
    return comparisons

def overdue_chargers(plan, readiness_clock, start_at):
    goals=defaultdict(list)
    for cell in plan.cells:
        if cell.stop>=start_at:
            goals[cell.duty].append(cell.stop)
    rows=[]
    for key in sorted(goals):
        latest=max(goals[key])
        if key not in readiness_clock:
            rows.append({"duty":key,"last_slot":latest,"room":None})
        else:
            rows.append({"duty":key,"last_slot":latest,"room":readiness_clock[key]-latest})
    return rows
