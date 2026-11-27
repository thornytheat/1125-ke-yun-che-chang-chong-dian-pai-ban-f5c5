import hashlib
import json
from collections import defaultdict
from decimal import Decimal
from dataclasses import asdict

from ..depot_allocation.contracts import ShiftPlan
from .contracts import GateIssue, Handover, Issue, RiskMetrics


def signature(plan, duty_departures, feed_kw, buffer_minutes, config_digest) -> str:
    grid = [(feed, minute, str(value)) for (feed,minute),value in sorted(feed_kw.items())]
    cells = [asdict(cell) for cell in sorted(plan.cells, key=lambda part: (part.start,part.duty,part.bay))]
    orders = [asdict(row) for row in sorted(plan.orders, key=lambda row: row.duty)]
    document = [config_digest, buffer_minutes, sorted(duty_departures.items()), grid, cells, orders, plan.released]
    payload = json.dumps(document, ensure_ascii=False, default=str, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()


def audit_plan(plan: ShiftPlan, duty_departures, feed_kw, buffer_minutes: int,
               config_digest: str = "") -> Handover:
    problems = []
    totals = defaultdict(Decimal)
    load = defaultdict(Decimal)
    coaches = set()
    bays = set()
    for cell in plan.cells:
        kwh = cell.kwh
        dkey = (cell.duty, str(cell.start))
        if kwh <= 0 or cell.stop <= cell.start:
            problems.append(Issue(GateIssue.NONPOSITIVE_LOAD, dkey, "枪位分配数量或区间无效"))
            continue
        if cell.duty not in duty_departures:
            problems.append(Issue(GateIssue.UNKNOWN_DUTY, dkey, "分配未命中发车台账"))
        elif cell.stop + buffer_minutes > duty_departures[cell.duty]:
            problems.append(Issue(GateIssue.LEAVE_LATE, dkey, "预留整备时间不足"))
        if (cell.bay, cell.start) in bays:
            problems.append(Issue(GateIssue.BAY_COLLISION, dkey, cell.bay))
        if (cell.coach, cell.start) in coaches:
            problems.append(Issue(GateIssue.COACH_COLLISION, dkey, cell.coach))
        bays.add((cell.bay, cell.start))
        coaches.add((cell.coach, cell.start))
        totals[cell.duty] += kwh
        load[cell.circuit, cell.start] += cell.raw_grid_kw
    for circuit, start in sorted(load):
        applied = Decimal(str(feed_kw.get((circuit, start), 0)))
        if load[circuit,start] > applied:
            problems.append(Issue(GateIssue.GRID_OVERLOAD, (circuit,str(start)), str(load[circuit,start])))
    for order in plan.orders:
        qty = totals.pop(order.duty, Decimal(0))
        if qty != order.assigned_kwh:
            problems.append(Issue(GateIssue.DUTY_BALANCE_DIFF, (order.duty,), str(qty)))
        if qty > 0 and order.state != "安排充电":
            problems.append(Issue(GateIssue.UNAPPROVED_CHARGE, (order.duty,), order.state))
    for absent in sorted(totals):
        problems.append(Issue(GateIssue.UNKNOWN_DUTY, (absent,), "枪账未命中排班单"))
    cells_total = sum((cell.kwh for cell in plan.cells), Decimal(0))
    if cells_total != plan.released:
        problems.append(Issue(GateIssue.SHIFT_TOTAL_DIFF, (), str(cells_total)))
    total_need = sum((order.needed_kwh for order in plan.orders), Decimal(0))
    count = sum(order.state == "安排充电" for order in plan.orders)
    stamp = signature(plan,duty_departures,feed_kw,buffer_minutes,config_digest)
    return Handover(tuple(problems), cells_total, total_need, count, stamp)


def check_alerts(rows) -> RiskMetrics:
    counts = [0, 0, 0, 0]
    for alerted, critical in rows:
        counts[0] += bool(alerted)
        counts[1] += bool(alerted and not critical)
        counts[2] += bool(critical)
        counts[3] += bool(critical and not alerted)
    return RiskMetrics(*counts)
