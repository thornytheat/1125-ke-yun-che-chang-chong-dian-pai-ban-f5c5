import json
import pytest
from depotload.pipeline import run

def test_north_depot_reproducible_shift():
    batch = run()
    assert batch == run()
    assert len(batch["rows"]) >= 10
    assert len(batch["stages"]) == 6
    assert len(batch["series"]) >= 5
    json.dumps(batch, allow_nan=False)

def test_power_and_duty_units_conserve():
    batch = run()
    review = batch["stages"][-1]["records"][0]
    assert review["ready"]
    assert review["allocated_kwh"] == pytest.approx(sum(row["assigned"] for row in batch["rows"]))
    assert review["allocated_kwh"] == pytest.approx(sum(point["value"] for point in batch["series"]))

def test_capacity_restricts_enrollment():
    plan = run(1)
    review = plan["stages"][-1]["records"][0]
    assert review["charged_trips"] == 1
    assert any(row["status"] == "等候下一批" for row in plan["rows"])
    assert review["key"] != run(10)["stages"][-1]["records"][0]["key"]

def test_valid_fixture_exercises_manual_and_failures():
    batch = run()
    assert any(row["status"] == "人工点验" for row in batch["rows"])
    assert any(row["status"] == "调度协调" for row in batch["rows"])
    assert any(row.get("fault") == "INVALID_SOC" for row in batch["stages"][0]["records"])

def test_bad_capacity_never_computes():
    for value in (True, 0, 101, 1.5):
        with pytest.raises(ValueError, match="车次"):
            run(value)
