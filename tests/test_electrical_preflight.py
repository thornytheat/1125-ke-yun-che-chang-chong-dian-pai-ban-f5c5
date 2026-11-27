from decimal import Decimal
from dataclasses import replace
from types import SimpleNamespace
import pytest
from depotload.depot_allocation.battery_gate import ElectricalEnvelope, curve, derating, max_added, minutes_to_reach, fleet_energy_protection
from depotload.dispatch_recheck.circuit_incidents import load_events,non_callable,quarter_metrics,event_evidence
from depotload.pipeline import run
from depotload.plug_windows.contracts import Interval, Plug, Opportunity

def calibration():
    return curve([(0,70,130),(70,90,60),(90,100,25)])

def pack(kw=120,celsius=22,kwh=200,overhead=1.):
    return ElectricalEnvelope(kw,celsius,kwh,overhead)

def test_minutes_to_reach_resolves_each_taper_segment():
    secs=minutes_to_reach(pack(),calibration(),65,95)
    want=10/120*60 + 40/60*60 + 10/25*60
    assert secs==pytest.approx(want)
    assert max_added(pack(),calibration(),65,secs)==Decimal(60)

def test_operating_voltage_holds_first_segment():
    table=calibration()
    vehicle=pack(28,celsius=25)
    assert minutes_to_reach(vehicle,table,15,29)==pytest.approx(60)
    assert max_added(vehicle,table,15,60)==Decimal(28)
    assert max_added(vehicle,table,99,240)==Decimal(2)

def test_taper_target_near_full_cannot_use_full_rate():
    fast=minutes_to_reach(pack(),calibration(),10,15)
    upper=minutes_to_reach(pack(),calibration(),95,100)
    assert fast==pytest.approx(5)
    assert upper==pytest.approx(24)
    assert max_added(pack(),calibration(),95,fast)==Decimal("2.08")

@pytest.mark.parametrize(("temperature","scale"),[(-20,.45),(-10,.45),(0,.8),(5,1),(36,1),(42,.8),(45,.7),(60,.7)])
def test_physical_temperature_derating_is_bounded(temperature,scale):
    assert derating(temperature)==pytest.approx(scale)
    assert max_added(pack(celsius=temperature),calibration(),65,0)==0

def test_low_temperature_and_thermal_loss_worsen_earliest_departure():
    hot=pack(celsius=21,overhead=.95)
    cold=pack(celsius=-10,overhead=.95)
    warm=minutes_to_reach(hot,calibration(),50,68)
    cold_answer=minutes_to_reach(cold,calibration(),50,68)
    assert cold_answer>warm
    assert warm>minutes_to_reach(pack(),calibration(),50,68)
    assert max_added(cold,calibration(),50,warm)<36

@pytest.mark.parametrize("shape",[[],[(5,100,60)],[(0,50,60)],[(0,60,70),(40,100,40)],[(0,40,40),(60,100,60)],[(0,100,-6)]])
def test_unsupported_battery_tables_must_be_repaired(shape):
    with pytest.raises(ValueError):
        curve(shape)

@pytest.mark.parametrize("input_values",[(-1,20),(10,-2),(90,89),(0,101),(0,float("NaN"))])
def test_charge_targets_cannot_outside_state_envelope(input_values):
    with pytest.raises(ValueError):
        minutes_to_reach(pack(),calibration(),*input_values)

def test_two_live_guns_are_not_twice_available_vehicle_minutes():
    first=Plug("Z1","A",100,False)
    other=Plug("Z2","B",65,False)
    slots=(Opportunity(Interval(15,30),first,100),Opportunity(Interval(15,30),other,65))
    vehicle=SimpleNamespace(duty="M12",battery_kwh=200,state_pct=93.,ambient_c=20)
    report=fleet_energy_protection([vehicle],{"M12":slots},{"M12":{"needed":18}}, {})["M12"]
    assert report["minutes_available"]==15
    assert report["limited"] and report["target_soc_pct"]>100 and report["minutes_to_target"] is None
    assert report["can_add_kwh"]==9.4

def notice(**changes):
    entry={"circuit":"A","began":15,"ended":28,"type":"热断开","reported":15,"trace":"K-11"}
    entry.update(changes)
    return entry

def test_breaker_events_respect_open_ended_boundaries():
    source={('A',0):100.,('A',15):90.,('A',30):140.,('B',15):100.}
    alarms=load_events([notice(ended=30)],23)
    result, rows=non_callable(source,alarms)
    assert result=={('A',0):100.,('A',15):0.,('A',30):140.,('B',15):100.}
    assert rows==[{"feed":"A","start":15,"formerly_kw":90.,"trace":["K-11"]}]
    assert source['A',15]==90.

def test_late_reports_not_reread_into_prior_snapshot():
    known=load_events([notice(reported=30)],29)
    assert known=={}
    seen=load_events([notice(reported=30)],30)
    assert event_evidence(seen)[0]["visibility"]==30

def test_telemetry_gap_does_not_remove_usable_circuit():
    events=load_events([notice(type="表计失联")],25)
    snapshot={('A',15):107.}
    kept,signals=non_callable(snapshot,events)
    assert kept==snapshot and signals==[]
    assert event_evidence(events)[0]["kind"]=="表计失联"

def test_conflicting_event_revision_rejected_and_repeat_is_idempotent():
    accepted=load_events([notice(),notice()],45)
    assert len(accepted['A'])==1
    with pytest.raises(ValueError,match="冲突"):
        load_events([notice(),notice(ended=42)],45)
    with pytest.raises(ValueError):
        load_events([notice(reported=13)],45)

def test_metered_peak_differs_from_typical_draw():
    samples=[(15,43),(20,71),(25,120),(30,110),(33,120)]
    result=quarter_metrics(samples,15,105)
    assert result[0]["spike"] and not result[0]["typical_overdraw"]
    assert result[0]["median_kw"]==71 and result[0]["reported_max_kw"]==120
    assert result[1]["typical_overdraw"] and result[1]["median_kw"]==115
    with pytest.raises(ValueError):
        quarter_metrics([(15,-1)],15,105)
    with pytest.raises(ValueError):
        quarter_metrics([],15,0)

def test_documented_interruptions_have_per_schedule_accounting():
    rendered=run(5)["stages"]
    load=rendered[4]["records"]
    evidence=rendered[-1]["records"]
    assert any(row.get("spike") for row in load)
    interrupted=next(row for row in evidence if "interrupt_qtr_energy" in row or "interruption_qtr_energy" in row)
    assert interrupted["baseline_qtr_energy"]>=0 and interrupted["interruption_qtr_energy"]>=0
    assert interrupted["interruption_scheduled"]<=5
    assert any(r.get("kind")=="热断开" for r in evidence)
    assert all(r.get("notice")!="PP-延期" for r in evidence)
