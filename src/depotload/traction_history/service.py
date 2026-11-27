from .chronology import kwh_by_time, operating_split
from .contracts import HistoricalMatrix

def prepare_history(logs, train_at, usable_at) -> HistoricalMatrix:
    return operating_split(logs, train_at, usable_at)

def history_evidence(history: HistoricalMatrix) -> list[dict]:
    summary = kwh_by_time(history.earlier, 60)
    result = [{"start": hour, "net_kwh": round(kwh, 2), "phase": "拟合"}
              for hour, kwh in summary.items()]
    result.extend({"trip": trip, "phase": "待入账"} for trip in history.not_booked)
    result.extend({"trip": row.trip, "net_kwh": round(row.response, 2), "phase": "留出"}
                  for row in history.held_out)
    result.extend({"reason": entry, "phase": "隔离"} for entry in history.bad_rows)
    return result
