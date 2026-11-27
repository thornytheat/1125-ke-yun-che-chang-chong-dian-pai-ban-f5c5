from collections import defaultdict
from decimal import Decimal, InvalidOperation
from dataclasses import dataclass

@dataclass(frozen=True, slots=True)
class ChargeTelemetry:
    duty: str
    bay: str
    start: int
    before_kwh: Decimal
    after_kwh: Decimal
    ending: int
    verified: bool

    @property
    def delivered(self):
        return self.after_kwh-self.before_kwh

def metered(raw):
    recorded=[]
    for row in raw:
        try:
            before=Decimal(str(row["before_kwh"]))
            after=Decimal(str(row["after_kwh"]))
        except (KeyError, InvalidOperation) as error:
            raise ValueError("枪位回执缺少可用电量") from error
        if not before.is_finite() or not after.is_finite() or before<0 or after<before:
            raise ValueError("枪位回执累计电表反向或缺失")
        stamp=row["ending"]
        if stamp<=row["start"] or type(row["verified"]) is not bool:
            raise ValueError("枪位回执时间或复核字段不合法")
        recorded.append(ChargeTelemetry(row["duty"],row["bay"],row["start"],before,after,stamp,row["verified"]))
    return recorded

def compare_receipts(plan, telemetry, tolerance=Decimal(".5")):
    if tolerance<0:
        raise ValueError("允许回执偏差不能为负")
    bills=defaultdict(list)
    reconciliation=[]
    for observed in telemetry:
        bills[(observed.duty,observed.bay,observed.start)].append(observed)
    for cell in plan.cells:
        key=(cell.duty,cell.bay,cell.start)
        incoming=bills.pop(key,[])
        row={"duty":cell.duty,"charger":cell.bay,"quarter":cell.start,"planned":float(cell.kwh)}
        if not incoming:
            row.update(result="回执缺失", measured=None)
        else:
            unique=set(incoming)
            if len(unique)>1:
                row.update(result="回执冲突",measured=None)
            else:
                observed=incoming[0]
                delta=observed.delivered-cell.kwh
                row["measured"]=float(observed.delivered)
                row["delta"]=float(delta)
                if not observed.verified or observed.ending>cell.stop:
                    row["result"]="待验签"
                elif abs(delta)>tolerance:
                    row["result"]="实际电量偏差"
                else:
                    row["result"]="匹配"
        reconciliation.append(row)
    reconciliation.extend({"duty":key[0],"charger":key[1],"quarter":key[2],"result":"未登记充电"}
                          for key in sorted(bills))
    return reconciliation
