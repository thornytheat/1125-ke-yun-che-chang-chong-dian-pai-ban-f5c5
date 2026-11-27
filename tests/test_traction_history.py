import math
import pytest
from depotload.traction_history.chronology import fit_scale, operating_split, kwh_by_time
from depotload.traction_history.contracts import TractionLog


def log(**updates):
    result = dict(trip="B-21", departed=10, completed=79, booked=81, distance_km=39,
                  uphill_m=72, outside_c=4, aux_minutes=60, gross_draw_kwh=49, recovered_kwh=7)
    result.update(updates)
    return result

def test_regeneration_and_degree_hours():
    tach = TractionLog(**log())
    assert tach.features == (39, .72, 11)
    assert tach.response == 42
    assert TractionLog(**log(outside_c=18)).features[-1] == 0

def test_variance_centered():
    # TRAP-32 大基数上小波动与常数列不能走 E[X²]-E[X]²。
    data = ((1e12 - 1, 4), (1e12, 4), (1e12 + 1, 4))
    naive_variance = sum(row[0] ** 2 for row in data) / 3 - 1e24
    assert not math.isclose(naive_variance, 2/3)
    scale = fit_scale(data)
    assert scale.mean == (1e12, 4)
    assert scale.spread[0] == pytest.approx(math.sqrt(2/3))
    assert scale.project(data[1]) == (0, 0)

def test_dimension_mismatch():
    with pytest.raises(ValueError, match="对齐"):
        fit_scale([(1,), (2, 3)])
    with pytest.raises(ValueError, match="列数"):
        fit_scale([(1, 2)]).project((1,))

def test_late_booking_and_temporal_split():
    # TRAP-42 留出数据不影响训练缩放，迟到标签也不能用于回溯拟合。
    old = log()
    late = log(trip="L", completed=80, booked=95, distance_km=200)
    future = log(trip="O", completed=105, booked=106, distance_km=300)
    split = operating_split([future, old, late], 90, 100)
    assert [r.trip for r in split.earlier] == ["B-21"]
    assert [r.trip for r in split.held_out] == ["L"]
    assert split.not_booked == ("O",)
    assert split.scale == operating_split([old], 90, 100).scale

def test_training_window_is_left_closed():
    boundary = log(trip="EDGE", completed=90, booked=90)
    split = operating_split([boundary, log()], 90, 90)
    assert split.held_out[0].trip == "EDGE"
    assert split.earlier[0].trip == "B-21"

def test_bad_regeneration_isolated():
    split = operating_split([log(), log(trip="BAD", recovered_kwh=51)], 90, 95)
    assert len(split.earlier) == 1
    assert split.bad_rows[0].startswith("BAD:")

def test_duplicate_trip_excluded():
    split = operating_split([log(trip="N"), log(distance_km=40), log()], 90, 100)
    assert [item.trip for item in split.earlier] == ["N"]
    assert split.bad_rows == ("B-21: 重复已关账班次",)

def test_energy_bucket_alignment():
    records = [TractionLog(**log()), TractionLog(**log(trip="C", completed=120, booked=122))]
    assert kwh_by_time(records, 60) == {60: 42, 120: 42}
    with pytest.raises(ValueError):
        kwh_by_time(records, 0)
