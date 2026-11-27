from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from .contracts import Arrival, ArrivalFault, Reject, minute, numeric


@dataclass(frozen=True, slots=True)
class ArrivalRegister:
    valid: tuple[Arrival, ...]
    rejects: tuple[Reject, ...]
    snapshots: int

    def summary(self) -> dict[str, int]:
        from collections import Counter
        return dict(Counter(str(reject.reason) for reject in self.rejects))


def decode(row: Mapping) -> Arrival | Reject:
    key = str(row.get("duty", "")).strip().upper()
    depot = str(row.get("depot", "")).strip().upper()
    coach = str(row.get("coach", "")).strip().upper()
    if not key or not depot or not coach:
        return Reject(key, 0, ArrivalFault.INVALID_IDENTITY, "车场、车次和车牌字段必填")
    try:
        revision = minute(row["revision"])
        observed = minute(row["observed"])
        received = minute(row["received"])
        departure = minute(row["departure"])
        if not observed < departure or received < observed:
            raise ValueError("交班时钟顺序冲突")
    except (KeyError, ValueError, TypeError) as exc:
        return Reject(key, 0, ArrivalFault.INVALID_CLOCK, str(exc))
    try:
        odometer = numeric(row["odometer_km"], 0, 2_000_000)
    except (KeyError, ValueError, TypeError) as exc:
        return Reject(key, revision, ArrivalFault.INVALID_ODOMETER, str(exc))
    try:
        state = numeric(row["state_pct"], 0, 100)
    except (KeyError, ValueError, TypeError) as exc:
        return Reject(key, revision, ArrivalFault.INVALID_SOC, str(exc))
    try:
        battery = numeric(row["battery_kwh"], 40, 650)
        route = numeric(row["route_km"], 0, 500)
        ambient = numeric(row["ambient_c"], -40, 60)
        lift = row["lift_required"]
        if type(lift) is not bool:
            raise ValueError("无障碍车位字段应为布尔值")
    except (KeyError, ValueError, TypeError) as exc:
        return Reject(key, revision, ArrivalFault.BAD_BATTERY_RATING, str(exc))
    return Arrival(key, coach, depot, received, departure, observed,
                   revision, odometer, state, battery, route, ambient, lift)


def at_revision(packets: list[Arrival]) -> tuple[Arrival | None, list[Reject]]:
    latest = max(packet.revision for packet in packets)
    contenders = {packet for packet in packets if packet.revision == latest}
    superseded = {packet for packet in packets if packet.revision != latest}
    notes = [Reject(p.duty, p.revision, ArrivalFault.STALE_PACKET, "已收到较新的车次修订")
             for p in sorted(superseded, key=lambda row: (row.revision, row.received))]
    if len(contenders) > 1:
        key = packets[0].duty
        notes.append(Reject(key, latest, ArrivalFault.REVISION_CONFLICT, "同一版本载荷不同，须人工核对"))
        return None, notes
    return next(iter(contenders)), notes


def consolidate(rows: Iterable[Mapping], cutoff: int) -> ArrivalRegister:
    packets = defaultdict(list)
    rejects = []
    snapshots = 0
    for row in rows:
        snapshots += 1
        decoded = decode(row)
        if isinstance(decoded, Reject):
            rejects.append(decoded)
        elif decoded.received <= cutoff:
            packets[decoded.identity].append(decoded)
    accepted = []
    for key in sorted(packets):
        row, notes = at_revision(packets[key])
        rejects.extend(notes)
        if row:
            accepted.append(row)
    rejects.sort(key=lambda entry: (entry.duty, entry.revision, str(entry.reason), entry.details))
    return ArrivalRegister(tuple(accepted), tuple(rejects), snapshots)
