from dataclasses import replace
from decimal import Decimal as D
import pytest
from depotload.depot_allocation.contracts import Allocation, ShiftPlan
from depotload.dispatch_recheck.energy_receipts import metered,compare_receipts
from depotload.pipeline import run

def slot(*cases):
    rows = tuple(Allocation(key,"C-1",charger,"F1",10,25,D(quantity)) for key,charger,quantity in cases)
    return ShiftPlan((),rows,sum((row.kwh for row in rows),D(0)))

def entry(**adjust):
    row = {"duty":"A", "bay":"R1", "start":10, "ending":25, "before_kwh":"110.0",
           "after_kwh":"122.0", "verified":True}
    row.update(adjust)
    return row

@pytest.mark.parametrize(("supplied","result"),[
    ({"after_kwh":"121.45"}, "实际电量偏差"),
    ({"after_kwh":"121.5"}, "匹配"),
    ({"after_kwh":"122.5"}, "匹配"),
    ({"after_kwh":"123.1"}, "实际电量偏差"),
    ({"verified":False}, "待验签"),
    ({"ending":26}, "待验签"),
])
def test_signed_meter_reconciliation_preserves_quantity(supplied,result):
    verified = metered([entry(**supplied)])
    row = compare_receipts(slot(("A","R1",12)),verified)[0]
    assert row["result"] == result
    assert row["planned"] == 12
    assert row["measured"] == float(D(entry(**supplied)["after_kwh"])-110)
    assert row["delta"] == float(D(entry(**supplied)["after_kwh"])-122)

def test_missing_and_unplanned_charge_are_reported_separately():
    expected=slot(("A","R1",12),("B","R2",11))
    observed=metered([entry(),entry(duty="CY",bay="Q3")])
    outcomes=compare_receipts(expected,observed)
    assert [r["result"] for r in outcomes] == ["匹配","回执缺失","未登记充电"]
    assert outcomes[-1]["duty"] == "CY" and outcomes[1]["measured"] is None

def test_conflict_rejected_while_identical_retry_is_idempotent():
    expected=slot(("A","R1",12))
    twice=metered([entry(),entry()])
    assert compare_receipts(expected,twice)[0]["result"] == "匹配"
    conflict=metered([entry(),entry(after_kwh="120.0")])
    result=compare_receipts(expected,conflict)
    assert result==compare_receipts(expected,conflict[::-1])
    assert result[0]["result"]=="回执冲突" and result[0]["measured"] is None

@pytest.mark.parametrize("changed",[
    {"after_kwh":"NaN"}, {"after_kwh":"108.0"}, {"before_kwh":-4}, {"verified":1}, {"ending":10},
])
def test_invalid_meter_facts_not_admitted(changed):
    with pytest.raises(ValueError):
        metered([entry(**changed)])

def test_full_workbench_exposes_all_advanced_evidence():
    overview=run()
    inspection=overview["stages"]
    assert any("temperature_band" in row for row in inspection[1]["records"])
    assert any("manual_count" in row for row in inspection[2]["records"])
    assert any("possible_kwh" in row for row in inspection[3]["records"])
    assert any("shift_net_kwh" in row for row in inspection[4]["records"])
    assert any("planned" in row for row in inspection[5]["records"])
    assert any(row.get("result")=="未登记充电" for row in inspection[5]["records"])
