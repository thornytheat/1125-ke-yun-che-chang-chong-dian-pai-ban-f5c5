from .priority import plan_shift
from .contracts import ShiftPlan

def compile_feeders(supplies, step=15):
    if step < 1:
        raise ValueError("功率预算粒度应为正数")
    return {(row.circuit, start): row.kw for row in supplies
            for start in range((row.span.start+step-1)//step*step, row.span.stop-step+1, step)}

def allocate(requests, supplies, count):
    return plan_shift(requests, compile_feeders(supplies), count)

def slot_evidence(plan: ShiftPlan) -> list[dict]:
    return [{"duty": row.duty, "bay": row.bay, "coach": row.coach, "feed": row.circuit,
             "start": row.start, "end": row.stop, "quantity": float(row.kwh)} for row in plan.cells]
