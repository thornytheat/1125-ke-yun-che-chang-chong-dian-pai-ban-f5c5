import pytest
from depotload.plug_windows.contracts import Interval, Plug, Supply
from depotload.plug_windows.occupancy import normalize_offline, free_segments, supply_by_circuit, available_slots

def test_boundary_windows_do_not_overlap():
    # TRAP-23 相邻半开窗口可共享交界时刻，但共享分钟为零。
    left, right = Interval(30, 60), Interval(60, 90)
    assert not left.overlaps(right)
    assert right.intersection(left) is None
    assert free_segments(left, [right]) == (left,)

def test_combine_touching_outages():
    merged = normalize_offline([Interval(90, 100), Interval(60, 90), Interval(70, 80)])
    assert merged == (Interval(60, 100),)
    assert free_segments(Interval(50, 115), merged) == (Interval(50, 60), Interval(100, 115))

def test_partial_unavailability():
    work = Interval(60, 90)
    assert free_segments(work, [Interval(54, 66), Interval(83, 93)]) == (Interval(66, 83),)
    assert free_segments(work, [Interval(54, 93)]) == ()

def test_overlapping_feeder_profiles():
    # TRAP-25 同馈线同分钟不能按任意一份电力预算裁决。
    feeds = [Supply("C", Interval(0, 90), 80), Supply("C", Interval(45, 100), 41)]
    with pytest.raises(ValueError, match="馈线 C"):
        supply_by_circuit(feeds)

def test_slot_rated_on_available_supply():
    plug = Plug("A", "C", 120, True)
    slots = available_slots(Interval(12, 50), [plug], [Supply("C", Interval(0,60), 60)])
    assert [x.span for x in slots] == [Interval(15,30), Interval(30,45)]
    assert [x.available_kwh for x in slots] == [15, 15]

def test_accessible_plug_and_offline_feeder():
    plugs = [Plug("X", "Q", 60, False), Plug("Y", "Q", 75, True), Plug("Z", "R", 75, True)]
    budget = [Supply("Q", Interval(0,30), 100), Supply("R", Interval(0,30), 0)]
    result = available_slots(Interval(0,30), plugs, budget, accessible=True)
    assert {entry.plug.bay for entry in result} == {"Y"}
    assert len(result) == 2

def test_outage_removes_full_grid_cell():
    plug = Plug("A", "C", 120, True, (Interval(29, 32),))
    result = available_slots(Interval(0,60), [plug], [Supply("C", Interval(0,60), 130)])
    assert [slot.span for slot in result] == [Interval(0,15), Interval(45,60)]

def test_empty_and_invalid():
    assert available_slots(Interval(0,15), [], []) == []
    with pytest.raises(ValueError):
        Interval(5,5)
    with pytest.raises(ValueError):
        available_slots(Interval(0,15), [], [], step=0)
