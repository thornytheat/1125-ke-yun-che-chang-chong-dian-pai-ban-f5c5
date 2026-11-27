from .occupancy import available_slots
from .contracts import Interval, Plug, Supply

def load_infrastructure(config):
    plugs = tuple(Plug(row["bay"], row["circuit"], row["kw"], row["accessible"],
                  tuple(Interval(*gap) for gap in row.get("outages", [])))
                  for row in config["plugs"])
    if len({plug.bay for plug in plugs}) != len(plugs):
        raise ValueError("一号桩位不能登记两遍")
    feeds = tuple(Supply(row["circuit"], Interval(*row["span"]), row["kw"])
                  for row in config["feeds"])
    return plugs, feeds

def pickup_slots(arrival, plugs, feeds, now, turnaround_buffer):
    cutoff = arrival.departure - turnaround_buffer
    open_at = max(arrival.observed, arrival.received, now)
    if open_at >= cutoff:
        return []
    return available_slots(Interval(open_at, cutoff), plugs, feeds, arrival.lift_required)
