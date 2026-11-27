from dataclasses import dataclass
from decimal import Decimal, ROUND_FLOOR, ROUND_HALF_UP
from math import isfinite

@dataclass(frozen=True, slots=True)
class Segment:
    lower_pct: float
    upper_pct: float
    max_kw: float

    def __post_init__(self):
        if not 0 <= self.lower_pct < self.upper_pct <= 100:
            raise ValueError("电池快充 SOC 分段不连续")
        if not isfinite(self.max_kw) or self.max_kw<=0:
            raise ValueError("电池温控功率非法")

@dataclass(frozen=True, slots=True)
class ElectricalEnvelope:
    kw: float
    outside_c: float
    pack_kwh: float
    overhead: float = .94

    def __post_init__(self):
        if not all(isfinite(v) for v in (self.kw,self.outside_c,self.pack_kwh,self.overhead)):
            raise ValueError("充电工况缺少可用实测值")
        if self.kw<=0 or self.pack_kwh<=0 or not 0 < self.overhead <= 1:
            raise ValueError("功率、容量或损耗系数不合法")

def curve(table):
    parts=tuple(Segment(*cells) for cells in table)
    if not parts or parts[0].lower_pct!=0 or parts[-1].upper_pct!=100:
        raise ValueError("补电曲线需要覆盖完整 SOC 范围")
    if any(a.upper_pct!=b.lower_pct for a,b in zip(parts,parts[1:])):
        raise ValueError("补电分段重叠或缺档")
    return parts

def derating(celsius):
    if celsius<=-10:
        return .45
    if celsius<5:
        return .45 + (celsius+10)*.035
    if celsius>=45:
        return .7
    if celsius>36:
        return 1-(celsius-36)/30
    return 1.

def minutes_to_reach(pack, table, state, proposed):
    """Estimate conservative time given a fixed upper supply, full charge or first crossing."""
    if not 0<=state<=proposed<=100:
        raise ValueError("充电起止 SOC 不合法")
    minutes=0.
    for segment in table:
        start=max(state,segment.lower_pct)
        finish=min(proposed,segment.upper_pct)
        if finish<=start:
            continue
        power=min(pack.kw,segment.max_kw*derating(pack.outside_c))*pack.overhead
        minutes+=(finish-start)*pack.pack_kwh/100/power*60
    return minutes

def max_added(pack, table, state, minutes):
    if not 0<=state<=100 or not isfinite(minutes) or minutes<0:
        raise ValueError("SOC 或可充电时间非法")
    unrounded = fill_energy(pack, table, state, minutes)
    # Discard sub-picowatt artifacts from divisions such as one sixth of an hour.
    precise=unrounded.quantize(Decimal(".000000000001"),rounding=ROUND_HALF_UP)
    return precise.quantize(Decimal(".01"),rounding=ROUND_FLOOR)


def fill_energy(pack, table, state, minutes):
    remainder=Decimal(str(minutes))
    total=Decimal(0)
    full=Decimal(str(pack.pack_kwh))
    ambient=Decimal(str(derating(pack.outside_c)))
    efficiency=Decimal(str(pack.overhead))
    absolute=Decimal(str(state))
    for segment in table:
        if absolute>=segment.upper_pct:
            continue
        left=max(absolute,Decimal(str(segment.lower_pct)))
        headroom=(Decimal(str(segment.upper_pct))-left)*full/100
        rate=min(Decimal(str(pack.kw)),Decimal(str(segment.max_kw))*ambient)*efficiency/60
        can_add=min(headroom,remainder*rate)
        total+=can_add
        remainder-=can_add/rate
        if remainder<=Decimal(".000000000001"):
            break
    return total

def fleet_energy_protection(valid, departure_windows, by_duty, controls):
    table=curve(controls.get("taper",((0,70,150),(70,85,85),(85,100,40))))
    evidence={}
    for vehicle in valid:
        slots=departure_windows[vehicle.duty]
        ratings=[slot.input_kw for slot in slots]
        plateau=max(ratings,default=1.)
        actual=supply_by_start(slots)
        target=by_duty[vehicle.duty]
        target_pct=vehicle.state_pct+target["needed"]*100/vehicle.battery_kwh
        pack=ElectricalEnvelope(plateau,vehicle.ambient_c,vehicle.battery_kwh)
        available=sum(item[0] for item in actual.values())
        safely,steps=simulate_charge(pack,table,vehicle.state_pct,actual)
        ending=vehicle.state_pct+float(safely)*100/vehicle.battery_kwh
        expected=minutes_to_reach(pack,table,vehicle.state_pct,target_pct) if target_pct<=100 else None
        exceed=target_pct>100 or safely+Decimal(".05")<Decimal(str(target["needed"]))
        evidence[vehicle.duty]={"duty":vehicle.duty,"minutes_available":available,
                                "can_add_kwh":float(safely),"minutes_to_target":round(expected,2) if expected is not None else None,
                                "target_soc_pct":round(target_pct,2),"ending_soc_pct":round(ending,2),
                                "charging_cells":steps,"limited":exceed}
    return evidence

def supply_by_start(slots):
    available={}
    for slot in slots:
        cutout=slot.span.start
        rating=slot.span.minutes,slot.input_kw
        if cutout not in available or rating[1]>available[cutout][1]:
            available[cutout]=rating
    return available


def simulate_charge(pack, table, state, opportunity_by_minute):
    if not 0<=state<=100:
        raise ValueError("SOC 传感值超出电池工程范围")
    from dataclasses import replace
    full=Decimal(str(pack.pack_kwh))
    baseline=Decimal(str(state))
    battery=full*baseline/100
    initial=battery
    entries=[]
    for clock,(minutes,kw) in sorted(opportunity_by_minute.items()):
        if not isfinite(kw) or not isfinite(minutes) or kw<0 or minutes<0:
            raise ValueError("时格充电功率和分钟不可为负")
        if kw==0 or minutes==0 or battery>=full:
            continue
        starting_pct=battery*100/full
        outlet=replace(pack,kw=min(kw,pack.kw))
        stored=min(full-battery,fill_energy(outlet,table,starting_pct,minutes))
        battery+=stored
        entries.append({"minute":clock,"outlet_kw":outlet.kw,"initial_pct":round(float(starting_pct),3),
                        "stored_kwh":round(float(stored),4),"terminal_pct":round(float(battery*100/full),3)})
    total=(battery-initial).quantize(Decimal(".000000000001"),rounding=ROUND_HALF_UP)
    return total.quantize(Decimal(".01"),rounding=ROUND_FLOOR),entries
