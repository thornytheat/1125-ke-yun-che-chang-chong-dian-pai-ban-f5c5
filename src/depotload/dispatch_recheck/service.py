from .reconciliation import audit_plan, check_alerts
from .contracts import Handover

def certify(plan, departures, feed_kw, reserve_time, config_digest) -> Handover:
    return audit_plan(plan, departures, feed_kw, reserve_time, config_digest)

def review_evidence(check: Handover) -> list[dict]:
    entries = [{"ready": check.ready, "demand_kwh": float(check.demand_kwh),
                "allocated_kwh": float(check.actual_kwh), "charged_trips": check.assigned_trips,
                "coverage": check.coverage_share, "key": check.fingerprint}]
    entries.extend({"fault": str(item.name), "identity": "/".join(item.key), "details": item.evidence}
                   for item in check.issues)
    return entries
