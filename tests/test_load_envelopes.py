from decimal import Decimal as D
from math import isfinite
import pytest
from depotload.traction_history.contracts import TractionLog, Scale
from depotload.range_regression.contracts import EnergyModel
from depotload.range_regression.validation import summarize_calibration, climate_stress
from depotload.plug_windows.contracts import Plug,Supply,Interval,Opportunity
from depotload.plug_windows.topology import supply_capacity_report, usable_coverage
from depotload.depot_allocation.contracts import ChargeRequest
from depotload.depot_allocation.comparison import compare_peak_limit, feeder_delivery, overdue_chargers
from depotload.depot_allocation.priority import plan_shift

def fixture_model():
    return EnergyModel((10.,2.,3.),100.,Scale((50,1.2,22),(15,1.,7.),30),(2.,4.,6.,8.),.1,4.)

def journey(name, km, actual):
    return TractionLog(name,2,60,80,km,120,4,120,actual+2,2)

def test_residual_bands_include_missing_groups():
    model = fixture_model()
    history = [journey("A",29,85), journey("B",35,92), journey("C",54,123)]
    report = summarize_calibration(model, history)
    assert [item.rows for item in report] == [1,2,0,0]
    assert report[0].mean_underprediction is None
    assert report[1].mean_underprediction > 0
    assert report[2].coverage is None and report[2].mae is None
    with pytest.raises(ValueError):
        summarize_calibration(model, history, (40,35))

def test_temperature_stress_preserves_magnitude_order_under_chiller_load():
    options = climate_stress(fixture_model(), 50, 120, 8, 120, [0,-4,-8,15])
    assert options[0]["upper_kwh"] < options[1]["upper_kwh"] < options[2]["upper_kwh"]
    assert options[3]["upper_kwh"] <= options[0]["upper_kwh"]
    assert all(isfinite(r["reserve_pad"]) for r in options)
    with pytest.raises(ValueError):
        climate_stress(fixture_model(), -1, 70, 10, 90, [0])

def test_topology_reports_rated_and_operating_kw_separately():
    root = Supply("Q", Interval(15,45), 110)
    high = Plug("S1","Q",80,True,(Interval(20,27),))
    low = Plug("S2","Q",65,False)
    first, second = supply_capacity_report([high,low],[root],15,45)
    assert first.bays == ("S2",) and first.accessible_bays == ()
    assert first.rated_kw == first.usable_kw == 65 and first.grid_cap == 110
    assert second.bays == ("S1","S2") and second.rated_kw == 145 and second.usable_kw == 110
    assert usable_coverage((first,second)) == [{"feeder":"Q","possible_kwh":43.75,"accessible_minutes":15}]

def test_gaps_create_offline_evidence_even_with_rated_plug():
    plugs = [Plug("S1","Q",60,True)]
    schedule = [Supply("Q",Interval(30,45),100)]
    first,second = supply_capacity_report(plugs,schedule,5,45)
    assert first.start == 15 and first.rated_kw == 60 and first.usable_kw == 0
    assert second.usable_kw == 60
    with pytest.raises(ValueError):
        supply_capacity_report(plugs,schedule,60,30)

def requests():
    plug=Plug("S7","Q",70,True)
    first=Opportunity(Interval(30,45),plug,70)
    last=Opportunity(Interval(45,60),plug,70)
    return (ChargeRequest("A","R-01",80,16,True,False,(first,)),
            ChargeRequest("B","R-03",90,11,False,False,(last,)))

def test_peak_counterfactual_captures_distinct_shift_transitions():
    batch = requests()
    feeds = {("Q",30):70, ("Q",45):70}
    baseline = plan_shift(batch, feeds, 2)
    result = compare_peak_limit(batch, feeds, 2, baseline, (40,55,70))
    assert [line["scheduled"] for line in result] == [0,1,2]
    assert result[0]["lost"] == ["A","B"]
    assert result[1]["lost"] == ["A"]
    assert result[2]["shift_net_kwh"] == 0
    assert baseline.released == D(27)

def test_load_matrix_converts_quarter_hour_to_demand():
    feeds = {("Q",30):70,("Q",45):70,("Q",60):0}
    baseline = plan_shift(requests(),feeds,2)
    loads = feeder_delivery(baseline.cells,feeds)
    assert loads[0]["peak_kw"] == 64 and loads[0]["trips"] == 1
    assert loads[1]["peak_kw"] == 44 and loads[1]["limit_kw"] == 70
    assert loads[2]["peak_kw"] == 0 and loads[2]["ratio"] is None

def test_schedule_margin_uses_last_committed_cell():
    feeds = {("Q",30):70,("Q",45):70}
    baseline = plan_shift(requests(),feeds,2)
    assert overdue_chargers(baseline,{"A":49},30) == [
        {"duty":"A","last_slot":45,"room":4}, {"duty":"B","last_slot":60,"room":None},
    ]
    assert overdue_chargers(baseline,{"B":58},52)[0]["room"] == -2
