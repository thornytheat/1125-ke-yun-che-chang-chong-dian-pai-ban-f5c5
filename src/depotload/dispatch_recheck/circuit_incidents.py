from dataclasses import dataclass
from collections import defaultdict
from statistics import median
from math import isfinite

@dataclass(frozen=True,slots=True)
class Event:
    circuit: str
    began: int
    ended: int
    type: str
    reported: int
    trace: str

    def __post_init__(self):
        if self.type not in {"热断开", "计划停供", "表计失联"}:
            raise ValueError("馈线事件类别未登记")
        if self.began>=self.ended or (self.type!="计划停供" and self.reported<self.began):
            raise ValueError("馈线事件时间不一致")

def load_events(entries, now):
    known=defaultdict(list)
    identities={}
    for raw in entries:
        item=Event(**raw)
        if item.reported>now:
            continue
        if item.trace in identities and identities[item.trace]!=item:
            raise ValueError("事件日志编号产生冲突")
        identities[item.trace]=item
    for item in identities.values():
        known[item.circuit].append(item)
    return {key: tuple(sorted(group,key=lambda r:(r.began,r.ended,r.trace))) for key,group in sorted(known.items())}

def non_callable(feeds, events, grain=15):
    if grain<=0:
        raise ValueError("事件时段粒度须为正")
    removed={}
    lines=[]
    for (circuit,start),budget in sorted(feeds.items()):
        blockers=[row for row in events.get(circuit,()) if start<row.ended and row.began<start+grain
                  and row.type!="表计失联"]
        if blockers:
            lines.append({"feed":circuit,"start":start,"formerly_kw":budget,
                          "trace":[entry.trace for entry in blockers]})
            removed[circuit,start]=0.
        else:
            removed[circuit,start]=budget
    return removed,lines

def quarter_metrics(raw, between, cap):
    if not isfinite(cap) or cap<=0 or between<=0:
        raise ValueError("负荷判断窗口配置非法")
    quarters=defaultdict(list)
    for minute,load in sorted(raw):
        if not isfinite(load) or load<0:
            raise ValueError("馈线抄表记录不可用")
        quarters[minute//between*between].append(load)
    result=[]
    for key,points in sorted(quarters.items()):
        typical=median(points)
        result.append({"start":key,"valid_seconds":len(points),"median_kw":typical,
                       "reported_max_kw":max(points),"spike":max(points)>cap,
                       "typical_overdraw":typical>cap})
    return result

def event_evidence(independent_events):
    periods=[]
    for zone,entries in independent_events.items():
        for row in entries:
            periods.append({"location":zone,"from_minute":row.began,"until_minute":row.ended,
                            "visibility":row.reported,"kind":row.type,"notice":row.trace})
    return periods
