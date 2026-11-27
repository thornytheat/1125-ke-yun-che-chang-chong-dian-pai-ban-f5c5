from decimal import Decimal
from math import isclose
import pytest
from depotload.depot_allocation.battery_gate import (
    ElectricalEnvelope, curve, fill_energy, max_added, simulate_charge, supply_by_start,
)
from depotload.dispatch_recheck.circuit_incidents import load_events, non_callable
from depotload.plug_windows.contracts import Interval, Plug, Opportunity

def spec():
    return curve([(0,60,120),(60,85,65),(85,100,38)])

def test_dynamic_slots_use_actual_available_power_and_state():
    cell_plan={15:(15,25),30:(15,65),50:(15,55),75:(15,90)}
    cells=ElectricalEnvelope(100,22,220,1.)
    total,path=simulate_charge(cells,spec(),58,cell_plan)
    assert [row["outlet_kw"] for row in path]==[25,65,55,90]
    assert total<max_added(cells,spec(),58,60)
    assert float(total)<=sum(row["stored_kwh"] for row in path)
    assert path[-1]["terminal_pct"]>path[0]["terminal_pct"]
    assert all(left["terminal_pct"]==right["initial_pct"] for left,right in zip(path,path[1:]))

@pytest.mark.parametrize(("start","minutes","kw","expected"), [
    (0,30,60,30), (59,60,145,60.1358974359), (60,30,23,11.5),
    (80,30,75,23.1538461538), (95,30,99,10), (100,30,50,0),
])
def test_stateful_charge_matches_segment_arithmetic(start,minutes,kw,expected):
    pack=ElectricalEnvelope(kw,25,200,1.)
    energy=fill_energy(pack,spec(),start,minutes)
    assert float(energy)==pytest.approx(expected)
    current,trace=simulate_charge(pack,spec(),start,{15:(minutes,kw)})
    assert float(current)==pytest.approx(int(round(expected*100,8))/100)
    if trace:
        assert trace[0]["terminal_pct"]==pytest.approx(round(start+expected/2,3))

def test_dynamic_windows_do_not_charge_between_available_cells():
    pack=ElectricalEnvelope(90,30,220,1.)
    plan={120:(15,90),210:(15,90)}
    energy,trace=simulate_charge(pack,spec(),32,plan)
    assert [row["minute"] for row in trace]==[120,210]
    assert float(energy)==45
    assert simulate_charge(pack,spec(),32,{120:(0,5),210:(15,0)})==(Decimal("0.00"),[])

def test_select_highest_candidate_across_feeds_per_time_cell():
    low=Opportunity(Interval(15,30),Plug("G1","A",60,True),55)
    high=Opportunity(Interval(15,30),Plug("G2","B",80,False),75)
    later=Opportunity(Interval(30,45),Plug("G3","B",100,True),90)
    assert supply_by_start([low,high,later])=={15:(15,75),30:(15,90)}
    assert supply_by_start([high,later,low])=={15:(15,75),30:(15,90)}

def test_maintenance_announced_in_advance_controls_only_its_own_interval():
    data=[{"circuit":"N","began":105,"ended":120,"type":"计划停供","reported":88,"trace":"MAINT"}]
    known=load_events(data,90)
    slots={('N',90):120,('N',105):115,('N',120):60,('S',105):80}
    updated,notes=non_callable(slots,known)
    assert updated=={('N',90):120,('N',105):0,('N',120):60,('S',105):80}
    assert notes[0]["trace"]==["MAINT"]
    assert non_callable(slots,load_events(data,87))[0]==slots

@pytest.mark.parametrize(("windows","state"), [
    ({12:(-3,100)},50), ({12:(15,-100)},50), ({12:(15,float("inf"))},50),
    ({12:(float("nan"),100)},50), ({12:(15,100)},-2),
])
def test_invalid_dynamic_slot_parameters_require_explicit_review(windows,state):
    with pytest.raises(ValueError):
        simulate_charge(ElectricalEnvelope(90,30,220,1.),spec(),state,windows)


@pytest.mark.parametrize(("first_kw","second_kw"), [(45,110),(110,45),(60,60),(0,85),(85,0)])
def test_window_replay_per_slot_conserves_state_and_energy(first_kw,second_kw):
    pack=ElectricalEnvelope(100,23,230,.97)
    steps={58:(15,first_kw),90:(15,second_kw)}
    value,evidence=simulate_charge(pack,spec(),58,steps)
    unrounded=sum(row["stored_kwh"] for row in evidence)
    assert -.0001<=unrounded-float(value)<.0102
    assert value>=0
    last=evidence[-1]
    assert 58<=last["terminal_pct"]<=100
    assert last["terminal_pct"]==pytest.approx(58+unrounded*100/230,abs=.00051)
    assert all(row["outlet_kw"]<=pack.kw for row in evidence)
    assert value==simulate_charge(pack,spec(),58,dict(reversed(list(steps.items()))))[0]


def test_overheated_pack_uses_reduced_bay_rating():
    hot_pack=ElectricalEnvelope(120,50,200,.9)
    cool_pack=ElectricalEnvelope(120,20,200,.9)
    slots={5:(15,110),20:(15,110),35:(15,110)}
    warm, warm_evidence=simulate_charge(hot_pack,spec(),89,slots)
    cool,cool_evidence=simulate_charge(cool_pack,spec(),89,slots)
    assert warm<cool
    assert warm_evidence[0]["stored_kwh"] < cool_evidence[0]["stored_kwh"]
    assert cool <= Decimal("22.00")
    assert cool_evidence[-1]["terminal_pct"]<=100


def test_full_pack_does_not_consume_available_charging_steps():
    pack=ElectricalEnvelope(60,20,215,.96)
    charged,trace=simulate_charge(pack,spec(),100,{60:(15,60),75:(15,60)})
    assert charged==Decimal("0.00")
    assert trace==[]
