from decimal import Decimal
import pytest
from depotload.depot_allocation.contracts import ChargeRequest
from depotload.depot_allocation.priority import plan_shift, next_state
from depotload.plug_windows.contracts import Plug, Opportunity, Interval


def request(duty="R1", coach="B1", needed=10, window=(0,15), accessible=False, manual=False, departure=90):
    choices = tuple(Opportunity(Interval(s,s+15), Plug(name,"E",60,True), 60)
                    for s in window for name in ("A", "B"))
    return ChargeRequest(duty, coach, departure, needed, accessible, manual, choices)

def test_deterministic_priority_and_no_double_charge():
    # TRAP-19 双规则命中时按发车钟、无障碍约束、需求以及班次号显式排序。
    rows = [request("R2", "B2"), request("R1", "B1", accessible=True)]
    feed = {("E", 0): 80, ("E", 15): 80}
    plan = plan_shift(rows, feed, 1)
    assert plan == plan_shift(reversed(rows), feed, 1)
    assert [group.duty for group in plan.orders] == ["R1", "R2"]
    assert [group.state for group in plan.orders] == ["安排充电", "等候下一批"]

def test_partial_request_rolls_back_all_slots():
    feed = {("E", 0): 60}
    plan = plan_shift([request(needed=19, window=(0,)), request("R2", "B2", window=(0,))], feed, 2)
    assert [row.state for row in plan.orders] == ["调度协调", "安排充电"]
    assert len(plan.cells) == 1 and plan.cells[0].duty == "R2"
    assert plan.released == Decimal("10.00")

def test_feed_power_is_shared_by_plugs():
    windows = {("E",0):60}
    both = plan_shift([request(window=(0,)), request("R2", "B2", window=(0,), needed=6)], windows, 3)
    assert [row.state for row in both.orders] == ["安排充电", "调度协调"]
    assert both.released == Decimal("10")

def test_manual_and_zero_do_not_spend_slots():
    rows = [request(manual=True), request("RR", "B2", needed=0), request("T", "B3")]
    plan = plan_shift(rows, {("E",0):60}, 1)
    assert {row.state for row in plan.orders} == {"人工点验", "可直接交班", "安排充电"}
    assert plan.released == Decimal("10")

def test_cent_rounding_conserves_energy():
    # TRAP-24 电量预留量向上到分，容量预算向下到分，处置与桩账逐分守恒。
    slots = {("E",0):40.02, ("E",15):60}
    plan = plan_shift([request(needed=10.004)], slots, 1)
    assert plan.released == plan.orders[0].assigned_kwh == Decimal("10.01")
    assert [cell.kwh for cell in plan.cells] == [Decimal("10.00"), Decimal("0.01")]
    assert sum(cell.kwh for cell in plan.cells) == plan.released

def test_coach_cannot_charge_two_duties_at_same_time():
    plan = plan_shift([request(window=(0,)), request("R2", "B1", window=(0,))], {("E", 0):120}, 2)
    assert len(plan.cells) == 1
    assert "同一车辆不可双枪充电" in plan.orders[1].reasons

def test_no_budget_and_no_window_reason():
    assert next_state(request(window=()), False) == ("调度协调", "当前无可用充电窗口")
    plan = plan_shift([request()], {}, 1)
    assert "同馈线功率不足" in plan.orders[0].reasons
    assert plan.orders[0].deficit == Decimal(10)

def test_duplicate_duty_rejected():
    with pytest.raises(ValueError, match="重复"):
        plan_shift([request(), request(coach="DIFF")], {}, 1)
    with pytest.raises(ValueError, match="配额"):
        plan_shift([], {}, -1)
