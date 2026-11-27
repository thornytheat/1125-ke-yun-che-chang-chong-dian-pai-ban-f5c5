from collections import defaultdict
from dataclasses import dataclass
from .contracts import Arrival

@dataclass(frozen=True, slots=True)
class Turnaround:
    depot: str
    coach: str
    current_duty: str
    next_duty: str
    layover: int
    state: str
    origin_odometer: float
    later_odometer: float

    def as_evidence(self):
        return {"coach": self.coach, "current_duty": self.current_duty,
                "next_duty": self.next_duty, "turnaround": self.layover,
                "state": self.state, "odometer_difference": round(self.later_odometer-self.origin_odometer, 2)}

def inspect_roster(accepted: tuple[Arrival, ...], recovery_time: int = 5) -> tuple[Turnaround, ...]:
    if recovery_time < 0:
        raise ValueError("整备留缓不可为负")
    coaches = defaultdict(list)
    for row in accepted:
        coaches[(row.depot, row.coach)].append(row)
    result = []
    for (depot, coach), assignments in sorted(coaches.items()):
        ordered = sorted(assignments, key=lambda row: (row.observed, row.departure, row.duty))
        for first, last in zip(ordered, ordered[1:]):
            layover = last.observed - first.departure
            if layover < 0:
                status = "车次时段交叠"
            elif last.odometer_km < first.odometer_km:
                status = "同车里程回退"
            elif layover < recovery_time:
                status = "相邻车次整备时间不足"
            else:
                status = "连续交接通过"
            result.append(Turnaround(depot, coach, first.duty, last.duty, layover, status,
                                     first.odometer_km, last.odometer_km))
    return tuple(result)

def forced_reviews(findings):
    uncertain = defaultdict(list)
    for entry in findings:
        if entry.state == "车次时段交叠":
            uncertain[entry.current_duty].append(entry.state)
            uncertain[entry.next_duty].append(entry.state)
        elif entry.state != "连续交接通过":
            uncertain[entry.next_duty].append(entry.state)
    return {key: tuple(sorted(set(flags))) for key, flags in sorted(uncertain.items())}
