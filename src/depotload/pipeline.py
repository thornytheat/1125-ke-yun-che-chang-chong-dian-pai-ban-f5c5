import hashlib
import json
from collections import Counter
from collections import defaultdict
from pathlib import Path
from dataclasses import asdict
from .terminal_arrivals.turnaround import inspect_roster, forced_reviews
from .traction_history.duty_weather import energy_weather_overview, track_energy
from .range_regression.validation import summarize_calibration, climate_stress
from .plug_windows.topology import supply_capacity_report, usable_coverage
from .depot_allocation.comparison import feeder_delivery, compare_peak_limit, overdue_chargers
from .dispatch_recheck.energy_receipts import compare_receipts, metered
from .dispatch_recheck.circuit_incidents import load_events, non_callable, quarter_metrics, event_evidence
from .depot_allocation.battery_gate import fleet_energy_protection
from .depot_allocation.service import plan_shift

from .terminal_arrivals.service import post_arrivals, register_evidence
from .traction_history.service import prepare_history, history_evidence
from .range_regression.service import recalibrate, estimate_vehicle, calibration_summary
from .plug_windows.service import load_infrastructure, pickup_slots
from .depot_allocation.contracts import ChargeRequest
from .depot_allocation.service import allocate, compile_feeders, slot_evidence
from .dispatch_recheck.service import certify, review_evidence

SAMPLE = Path(__file__).resolve().parents[2] / "sample_data"


def read(field):
    return json.loads((SAMPLE / field).read_text(encoding="utf-8"))


def run(capacity: int | None = None) -> dict:
    cap = 7 if capacity is None else capacity
    if type(cap) is not int or not 1 <= cap <= 100:
        raise ValueError("可放行车次数须在 1 到 100 之间")
    grid = read("north_depot_grid.json")
    rows = read("incoming_terminal_duties.json")
    logs = read("traction_journal.json")
    logged = post_arrivals(rows, grid["at"])
    chained = inspect_roster(logged.valid, grid["reserve_minutes"])
    holdovers = forced_reviews(chained)
    history = prepare_history(logs, grid["train_until"], grid["at"])
    comparison = energy_weather_overview(history.earlier)
    cold_snap = [track_energy(row, -6) for row in history.held_out[:4]]
    model = recalibrate(history)
    residuals = [asdict(row) for row in summarize_calibration(model, history.held_out)]
    stress = climate_stress(model, 59, 117, 8, 84, [-8, -4, 0, 4, 8])
    quality = calibration_summary(model, history)
    plugs, feeds = load_infrastructure(grid)
    feeder_cells = supply_capacity_report(plugs, feeds, grid["at"], max(feed.span.stop for feed in feeds))
    feeder_stats = usable_coverage(feeder_cells)
    requests = []
    estimates = []
    battery_windows = {}
    line_choices = []
    by_duty = {}
    departures = {}
    for fleet in logged.valid:
        # Schedule duty sheet separates these estimates from telemetry captured after dispatch.
        drive_minutes = 16 + fleet.route_km * 1.17
        elevation = 40 + fleet.route_km * 1.31
        prediction = estimate_vehicle(model, fleet.route_km, elevation, fleet.ambient_c, drive_minutes)
        objective = prediction.with_reserve(grid["reserve_kwh"])
        needed = max(0.0, objective - fleet.energy_remaining)
        slots = pickup_slots(fleet, plugs, feeds, grid["at"], grid["reserve_minutes"])
        key = fleet.duty
        battery_windows[key] = slots
        notes = prediction.flags + holdovers.get(key, ())
        requests.append(ChargeRequest(key, fleet.coach, fleet.departure, needed,
                                       fleet.lift_required, bool(notes), tuple(slots)))
        evidence = {"duty": key, "coach": fleet.coach, "departure": fleet.departure,
                    "soc": fleet.state_pct, "route_kwh": round(prediction.route_kwh, 2),
                    "needed": round(needed, 2), "reasons": "；".join(notes)}
        by_duty[key] = evidence
        estimates.append(evidence)
        departures[key] = fleet.departure
        line_choices.append({"duty": key, "first": slots[0].span.start if slots else None,
                             "last": slots[-1].span.stop if slots else None,
                             "plugs": sorted({row.plug.bay for row in slots}), "cells": len(slots)})
    battery_report = fleet_energy_protection(logged.valid, battery_windows, by_duty, grid)
    plan = allocate(requests, feeds, cap)
    feeder_limits = compile_feeders(feeds)
    incidents = read("grid_breaker_notices.json")
    currently_known = load_events(incidents["events"], grid["at"])
    outage_constrained, outages = non_callable(feeder_limits, currently_known)
    interrupted = plan_shift(requests, outage_constrained, cap)
    stress_load = quarter_metrics(incidents["readings"], 15, 110)
    emergency_evidence = event_evidence(currently_known)
    emergency_evidence.append({"interruption_scheduled":sum(row.state=="安排充电" for row in interrupted.orders),
                               "baseline_qtr_energy":float(plan.released),"interruption_qtr_energy":float(interrupted.released)})
    peak_comparison = compare_peak_limit(requests, feeder_limits, cap, plan, (45, 65, 85))
    load_by_grid = feeder_delivery(plan.cells, feeder_limits)
    reserve_clock = {name: minute-grid["reserve_minutes"] for name,minute in departures.items()}
    margins = overdue_chargers(plan, reserve_clock, grid["at"])
    telemetry = compare_receipts(plan, metered(read("verified_pile_receipts.json")))
    source_model = json.dumps([grid, history.scale.mean, history.scale.spread, model.slope,
                               model.calibration, model.ridge, model.z_limit, cap], sort_keys=True)
    snapshot = hashlib.sha256(source_model.encode("utf-8")).hexdigest()
    validation = certify(plan, departures, compile_feeders(feeds), grid["reserve_minutes"], snapshot)
    final_rows = []
    status_counts = Counter(row.state for row in plan.orders)
    for decision in plan.orders:
        record = dict(by_duty[decision.duty])
        text = "；".join(decision.reasons)
        record.update(status=decision.state, assigned=float(decision.assigned_kwh),
                      reasons="；".join(x for x in (record["reasons"], text) if x) or "符合当前配额")
        final_rows.append(record)
    demand_line = defaultdict(float)
    for choice in plan.cells:
        demand_line[choice.start] += float(choice.kwh)
    axis = sorted({start for _, start in compile_feeders(feeds) if start >= grid["at"]})
    trend = [{"label": f"{k//60:02d}:{k%60:02d}", "value": round(demand_line[k], 2)} for k in axis]
    release = status_counts.get("可直接交班", 0) + status_counts.get("安排充电", 0)
    return {
        "metrics": {"待交班车次": len(logged.valid), "具备交班条件": release,
                    "已排补电 kWh": float(plan.released), "人工与排队": len(logged.valid) - release},
        "columns": {"duty":"车次","coach":"车牌","departure":"离场分钟","soc":"到场 SOC %",
                    "route_kwh":"下一班上界 kWh","needed":"缺口 kWh","assigned":"安排 kWh",
                    "status":"放行结果","reasons":"处置依据"},
        "rows": final_rows,
        "series": trend,
        "stages": [
            {"title":"车次归集","summary":f"收录 {logged.snapshots} 份快照，当前 {len(logged.valid)} 个车次",
             "records": register_evidence(logged)+[item.as_evidence() for item in chained]},
            {"title":"能耗校正","summary":f"训练 {len(history.earlier)} 段，留出 {len(history.held_out)} 段",
             "records": history_evidence(history)+comparison+cold_snap},
            {"title":"电量回归","summary":f"留出平均绝对偏差 {quality.mean_abs_kwh} kWh",
             "records": estimates+residuals+stress+list(battery_report.values())},
            {"title":"插枪窗口","summary":f"{len(plugs)} 个枪位，含报停及无障碍约束","records":line_choices+feeder_stats+outages},
            {"title":"峰段分派","summary":f"配额 {cap} 辆，排定 {len(plan.cells)} 个枪位时间格",
             "records":slot_evidence(plan)+peak_comparison+load_by_grid+stress_load},
            {"title":"交班验算","summary":"馈线和整备时钟核验通过" if validation.ready else "发现交班冲突",
             "records":review_evidence(validation)+margins+telemetry+emergency_evidence},
        ],
    }
