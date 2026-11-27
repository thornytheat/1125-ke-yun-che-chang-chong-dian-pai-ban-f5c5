from dataclasses import asdict
from .normalization import ArrivalRegister, consolidate

def post_arrivals(rows, cutoff: int) -> ArrivalRegister:
    return consolidate(rows, cutoff)

def register_evidence(register: ArrivalRegister) -> list[dict]:
    rows = [asdict(arrival) for arrival in register.valid]
    for note in register.rejects:
        rows.append({"duty": note.duty, "revision": note.revision,
                     "fault": str(note.reason), "details": note.details})
    return rows
