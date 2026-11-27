from collections import defaultdict
from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR
from math import isfinite

from .contracts import Allocation, ChargeRequest, Order, ShiftPlan

CENT = Decimal(".01")


def next_state(request: ChargeRequest, group_limit: bool) -> tuple[str, str]:
    if request.manual:
        return "人工点验", "工况或测值需确认"
    if request.needed <= 0:
        return "可直接交班", "当前电量可覆盖下一班"
    if not request.opportunities:
        return "调度协调", "当前无可用充电窗口"
    if group_limit:
        return "等候下一批", "已达到本班可放行车次数"
    return "允许试排", ""


def plan_shift(requests, feed_kw: dict[tuple[str,int], float], limit: int,
               selected_kw: float = 150) -> ShiftPlan:
    if limit < 0 or not isfinite(selected_kw) or selected_kw < 0:
        raise ValueError("本班容量配额无效")
    input_rows = sorted(requests, key=lambda bus: (bus.departure, not bus.accessible, -bus.needed, bus.duty))
    if len({row.duty for row in input_rows}) != len(input_rows):
        raise ValueError("同一车次不可重复提交")
    grid = defaultdict(Decimal)
    occupied = set()
    occupied_coach = set()
    cells = []
    results = []
    assigned = 0
    for request in input_rows:
        needed = Decimal(str(request.needed)).quantize(CENT, rounding=ROUND_CEILING)
        state, note = next_state(request, assigned >= limit)
        if state != "允许试排":
            results.append(Order(request.duty, state, needed, Decimal("0"), (note,)))
            continue
        tentative = []
        current = needed
        reasons = set()
        active_starts = set()
        for slot in sorted(request.opportunities, key=lambda item: (item.span.start, -item.input_kw, item.plug.bay)):
            k = slot.span.start
            bay = slot.plug.bay, k
            circuit = slot.plug.circuit, k
            if k in active_starts or (request.coach, k) in occupied_coach:
                reasons.add("同一车辆不可双枪充电")
                continue
            if bay in occupied:
                reasons.add("充电枪位已被占用")
                continue
            configured = min(feed_kw.get(circuit, 0), selected_kw)
            hr = Decimal(slot.span.minutes) / 60
            headroom = (Decimal(str(configured)) * hr) - grid[circuit]
            usable = min(headroom, Decimal(str(slot.input_kw)) * hr, current)
            delivered = usable.quantize(CENT, rounding=ROUND_FLOOR)
            if delivered <= 0:
                reasons.add("同馈线功率不足")
                continue
            tentative.append(Allocation(request.duty, request.coach, slot.plug.bay, slot.plug.circuit,
                                        slot.span.start, slot.span.stop, delivered))
            active_starts.add(k)
            current -= delivered
            if current <= 0:
                break
        if current > 0:
            reasons.add("截至离场时刻无法补足电量")
            results.append(Order(request.duty, "调度协调", needed, Decimal(0), tuple(sorted(reasons))))
            continue
        for fixed in tentative:
            occupied.add((fixed.bay, fixed.start))
            occupied_coach.add((fixed.coach, fixed.start))
            grid[(fixed.circuit, fixed.start)] += fixed.kwh
        assigned += 1
        results.append(Order(request.duty, "安排充电", needed, needed, tuple(sorted(reasons))))
        cells.extend(tentative)
    released = sum((cell.kwh for cell in cells), Decimal(0))
    return ShiftPlan(tuple(results), tuple(cells), released)
