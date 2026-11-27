from depotload.terminal_arrivals.normalization import decode, consolidate
from depotload.terminal_arrivals.contracts import Arrival, ArrivalFault


def entry(**updates):
    row = dict(duty=" n5 ", coach=" fd-331 ", depot="归车场", observed=975, received=978,
               departure=1060, revision=1, odometer_km=123040.2, state_pct=37,
               battery_kwh=294, route_km=81, ambient_c=4, lift_required=True)
    row.update(updates)
    return row

def test_unit_conversion():
    parsed = decode(entry())
    assert isinstance(parsed, Arrival)
    assert parsed.identity == ("归车场", "N5")
    assert parsed.coach == "FD-331"
    assert parsed.dwell == 85
    assert parsed.energy_remaining == 108.78

def test_rounded_clock():
    problem = decode(entry(received=978.125))
    assert problem.reason == ArrivalFault.INVALID_CLOCK
    assert not isinstance(problem, Arrival)
    assert decode(entry(departure=975)).reason == ArrivalFault.INVALID_CLOCK

def test_invalid_soc_and_distance():
    assert decode(entry(state_pct=True)).reason == ArrivalFault.INVALID_SOC
    assert decode(entry(state_pct="NaN")).reason == ArrivalFault.INVALID_SOC
    assert decode(entry(odometer_km=-2)).reason == ArrivalFault.INVALID_ODOMETER
    assert decode(entry(battery_kwh=4)).reason == ArrivalFault.BAD_BATTERY_RATING

def test_future_arrival_revision():
    # TRAP-42 信息未到达时不能覆盖已经看到的修订。
    rows = [entry(), entry(received=1010, revision=2, state_pct=50)]
    assert consolidate(rows, 1009) == consolidate(rows[:1], 1009).__class__(consolidate(rows[:1], 1009).valid, (), 2)
    later = consolidate(rows, 1010)
    assert later.valid[0].state_pct == 50
    assert later.summary() == {"STALE_PACKET": 1}

def test_same_revision_conflicts():
    # TRAP-25 同一生效修订出现两份互相矛盾的快照。
    rows = [entry(), entry(coach="OTHER")]
    outcome = consolidate(rows, 1010)
    assert outcome == consolidate(reversed(rows), 1010)
    assert outcome.valid == ()
    assert outcome.summary() == {"REVISION_CONFLICT": 1}

def test_same_duty_different_depot():
    rows = [entry(), entry(depot="南区车场"), entry()]
    outcome = consolidate(rows, 1000)
    assert len(outcome.valid) == 2
    assert outcome.snapshots == 3
    assert outcome.rejects == ()

def test_empty_submission():
    assert consolidate([], 1000).summary() == {}
    assert consolidate([entry(received=1001)], 1000).valid == ()

def test_terminal_state_uses_latest_known_reading():
    outcome = consolidate([entry(revision=2, state_pct=38), entry()], 1000)
    assert outcome.valid[0].state_pct == 38
    previous = outcome.rejects[0]
    assert previous.revision == 1 and previous.duty == "N5"
