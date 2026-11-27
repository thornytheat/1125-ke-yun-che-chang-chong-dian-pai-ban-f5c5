from collections import defaultdict
from collections.abc import Iterable

from .contracts import Interval, Opportunity, Plug, Supply


def normalize_offline(intervals: Iterable[Interval]) -> tuple[Interval, ...]:
    islands = []
    for span in sorted(set(intervals)):
        if islands and span.start <= islands[-1].stop:
            islands[-1] = Interval(islands[-1].start, max(islands[-1].stop, span.stop))
        else:
            islands.append(span)
    return tuple(islands)


def free_segments(work: Interval, outages: Iterable[Interval]) -> tuple[Interval, ...]:
    clear = []
    cursor = work.start
    for island in normalize_offline(outages):
        overlap = work.intersection(island)
        if overlap is None:
            continue
        if cursor < overlap.start:
            clear.append(Interval(cursor, overlap.start))
        cursor = overlap.stop
    if cursor < work.stop:
        clear.append(Interval(cursor, work.stop))
    return tuple(clear)


def supply_by_circuit(windows: Iterable[Supply]) -> dict[str, tuple[Supply, ...]]:
    index = defaultdict(list)
    for supply in windows:
        index[supply.circuit].append(supply)
    result = {}
    for circuit, spans in index.items():
        sorted_spans = sorted(spans, key=lambda part: part.span)
        for previous, after in zip(sorted_spans, sorted_spans[1:]):
            if previous.span.overlaps(after.span):
                raise ValueError(f"馈线 {circuit} 时段重复")
        result[circuit] = tuple(sorted_spans)
    return result


def available_slots(window: Interval, plugs: Iterable[Plug], feeds: Iterable[Supply],
                    accessible: bool = False, step: int = 15) -> list[Opportunity]:
    if step <= 0:
        raise ValueError("排班粒度须为正分钟")
    spans = supply_by_circuit(feeds)
    result = []
    for plug in sorted(plugs, key=lambda item: item.bay):
        if accessible and not plug.accessible:
            continue
        for segment in free_segments(window, plug.outages):
            for budget in spans.get(plug.circuit, ()):
                zone = segment.intersection(budget.span)
                if zone is None or budget.kw == 0:
                    continue
                ceil_start = (zone.start + step - 1) // step * step
                for start in range(ceil_start, zone.stop - step + 1, step):
                    period = Interval(start, start + step)
                    result.append(Opportunity(period, plug, min(plug.kw, budget.kw)))
    return sorted(result, key=lambda item: (item.span, item.plug.bay))
