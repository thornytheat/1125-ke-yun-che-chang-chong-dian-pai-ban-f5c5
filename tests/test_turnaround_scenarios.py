from dataclasses import replace
import pytest
from depotload.terminal_arrivals.contracts import Arrival
from depotload.terminal_arrivals.turnaround import inspect_roster, forced_reviews
from depotload.traction_history.contracts import TractionLog
from depotload.traction_history.duty_weather import percentile, weather_band, energy_weather_overview, track_energy

def duty(name, t, odometer=50, coach="N-35", depot="东"):
    return Arrival(name, coach, depot, t+1, t+15, t, 1, odometer, 42, 295, 40, 3, False)

@pytest.mark.parametrize(("offset", "reading", "reason", "affected"), [
    (12, 55, "车次时段交叠", {"A", "B"}),
    (16, 50, "相邻车次整备时间不足", {"B"}),
    (20, 42, "同车里程回退", {"B"}),
    (21, 70, "连续交接通过", set()),
])
def test_roster_checks_implied_driver_constraints(offset, reading, reason, affected):
    earlier = duty("A", 50)
    later = duty("B", 50 + offset, reading)
    outcome = inspect_roster((later, earlier), 5)
    item = outcome[0]
    assert item.current_duty == "A" and item.next_duty == "B"
    assert item.layover == offset - 15
    assert item.state == reason
    assert set(forced_reviews(outcome)) == affected
    assert item.as_evidence()["odometer_difference"] == reading - 50

def test_public_chains_do_not_cross_depots():
    assert inspect_roster((duty("A", 50), duty("B", 55, depot="西"))) == ()
    assert inspect_roster((duty("A", 50), duty("B", 55, coach="T-7"))) == ()
    with pytest.raises(ValueError):
        inspect_roster((), -1)

def route(name="M33", weather=7, net=45, regen=5, distance=30):
    return TractionLog(name, 10, 60, 75, distance, 155, weather, 60, net+regen, regen)

@pytest.mark.parametrize(("degrees", "category"), [
    (4.99,"冷车"), (5,"温控运行"), (14.99,"温控运行"), (15,"常温"),
])
def test_weather_bin_boundaries(degrees, category):
    assert weather_band(degrees) == category
    record = energy_weather_overview((route(weather=degrees),))
    known = next(row for row in record if row["count"])
    assert known["temperature_band"] == category
    assert known["median_wh_per_km"] == known["p85_wh_per_km"] == 1500
    assert known["energy_return_share"] == .1
    assert all(row["median_wh_per_km"] is None for row in record if row is not known)

def test_aggregate_recuperation_uses_energy_weighting():
    cold = (route("A",4,35,15), route("B",3,50,50))
    report = energy_weather_overview(cold)[0]
    assert report["energy_return_share"] == round(65/150,5)
    assert report["count"] == 2
    assert 1400 < report["p85_wh_per_km"] < 1700

def test_aux_load_only_after_crossing_threshold():
    assert track_energy(route(weather=19), -5)["correction_degree_hours"] == 1
    assert track_energy(route(weather=9), -5)["correction_degree_hours"] == 5
    assert track_energy(route(weather=14), 8)["correction_degree_hours"] == -1
    with pytest.raises(ValueError):
        track_energy(route(), 100)

def test_route_percentile_matches_exact_linear_rank():
    assert percentile([50,20,40,30], .1) == 23
    assert percentile([50,20,40,30], .5) == 35
    assert percentile([50,20,40,30], 1) == 50
    with pytest.raises(ValueError):
        percentile([4,float("inf")],.5)
    with pytest.raises(ValueError):
        percentile([], .5)
