from decimal import Decimal as D
from dataclasses import replace
from depotload.dispatch_recheck.reconciliation import check_alerts, audit_plan, signature
from depotload.dispatch_recheck.contracts import GateIssue
from depotload.depot_allocation.contracts import Allocation, Order, ShiftPlan


def fresh():
    return ShiftPlan((Order("DA", "安排充电", D(5), D(5), ()),),
                     (Allocation("DA", "B", "G1", "F", 30, 45, D(5)),), D(5))


def verify(plan, departures=None, feed_kw=None, reserve=5, digest="baseline"):
    return audit_plan(plan, departures if departures is not None else {"DA":50},
                      feed_kw if feed_kw is not None else {("F",30):20}, reserve, digest)

def test_valid_conserved_and_ready():
    check = verify(fresh())
    assert check.ready and check.coverage_share == 1
    assert check.assigned_trips == 1
    assert check.actual_kwh == D(5)

def test_checks_source_config_changes():
    # TRAP-54 对同一计划变更上游功率、整备参数或特征快照版本，旧证据签名不可复用。
    plan = fresh()
    one = verify(plan)
    assert one.fingerprint == verify(plan).fingerprint
    assert one.fingerprint != verify(plan, reserve=4).fingerprint
    assert one.fingerprint != verify(plan, digest="retrained").fingerprint
    assert one.fingerprint != verify(plan, feed_kw={("F",30):21}).fingerprint

def test_late_or_overload():
    result = verify(fresh(), {"DA":49}, {("F",30):19})
    assert not result.ready
    assert {item.name for item in result.issues} == {GateIssue.LEAVE_LATE, GateIssue.GRID_OVERLOAD}

def test_checks_both_identities():
    # TRAP-21 调度单有此枪账却缺少对应发车台账时不得签发。
    check = verify(fresh(), {})
    assert [x.name for x in check.issues] == [GateIssue.UNKNOWN_DUTY]
    plan = replace(fresh(), orders=())
    assert GateIssue.UNKNOWN_DUTY in {x.name for x in verify(plan).issues}

def test_tampered_shift_and_duty_detected():
    plan = replace(fresh(), released=D(7), orders=(Order("DA", "人工点验", D(5), D(3), ()),))
    check = verify(plan)
    assert {r.name for r in check.issues} == {GateIssue.SHIFT_TOTAL_DIFF, GateIssue.DUTY_BALANCE_DIFF,
                                               GateIssue.UNAPPROVED_CHARGE}

def test_duplicate_plug_and_coach():
    plan = fresh()
    plan = replace(plan, cells=plan.cells*2)
    check = verify(plan)
    flags = {item.name for item in check.issues}
    assert {GateIssue.COACH_COLLISION, GateIssue.BAY_COLLISION} <= flags

def test_empty_positive_reference():
    # TRAP-43 没有紧急线路的验证折不可被报作满分召回。
    score = check_alerts([(False,False), (True,False)])
    assert score.recall is None
    assert score.missed == 0
    assert score.precision == 0

def test_critical_counts_outweigh_naive_accuracy():
    data = [(False,False)] * 99 + [(False,True)]
    score = check_alerts(data)
    assert score.recall == 0 and score.precision is None
    assert score.missed == score.critical == 1
