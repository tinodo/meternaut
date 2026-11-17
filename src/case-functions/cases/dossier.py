"""The picture of a few resources in one answer: their facts, what they are billed for, every platform metric that has data, what they are connected to, their Advisor items, how old they are and who
changed them last, the parts inside them and where they send their own data. It replaces the six to ten calls that one resource takes. `build_dossier` is the plain function, and the tool `profile`
(cases/toolbox.py) is a thin wrapper of it, so that a later step of the Watch can call it without the protocol of the tools.

The reads of all the resources are made at the same time (a small pool, with the time of one call), and a part that did not finish in time is named as unread, never as none. Each part is the answer
of the tool that already shows it, or the numbers that such a tool shows, and the same code registers them as evidence, so that a number that the agent cites from a profile is checked like any other.
Nothing here decides anything: it orders by numbers and says what is not known.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    from .toolbox import Toolbox

MAX_HANDLES = 5  # the resources of one profile
MIN_DAYS = 7  # the fewest closed days that a profile looks back
PER_HANDLE = 3200  # characters that a profile may take for each of them (and MAX_RESULT_CHARS at the least)
METER_ROWS = 6  # the dearest meters of a resource
LINK_ROWS = 8  # the rows of types and relations of each side of the links of a resource
ADVISOR_ROWS = 5
NO_DATA_SHOWN = 40  # the names of the metrics that have no data, or that failed, that one resource lists
METRIC_COLUMNS = ("metric", "unit", "total", "max", "avg", "days")
UNREAD = "unread"
SECTIONS = {("graph",): "links", ("ages",): "history"}


def _toolbox():
    from . import toolbox  # the toolbox imports this module, so a top-level import would be circular

    return toolbox


def _outcome(tb, key: tuple, done: dict, left: list) -> tuple[str | None, object]:
    """What a read gave: (the word that its section says when it gave no answer, None), or (None, its answer). A read that did not finish in time is `unread`, a refusal of the access of the run
    is `not visible with this access`, and any other failure is `unavailable`."""
    if key in left:
        return UNREAD, None
    found = done.get(key)
    if isinstance(found, tb.Failed):
        return (tb.NOT_VISIBLE if getattr(found.error, "status", None) in (401, 403) else "unavailable"), None
    return None, found


def _unread(left: list, entries: list) -> dict[str, list[str]]:
    """The sections of each handle whose read did not finish in time."""
    found: dict[str, list[str]] = {}
    for entry in entries:
        handle = entry.resource.handle
        for key in left:
            section = SECTIONS.get(key) or ("advisor" if key == ("advisor", entry.sub) else None) or ({"log": "history"}.get(key[1], key[1]) if key[0] == handle else None)
            if section is not None and section not in found.setdefault(handle, []):
                found[handle].append(section)
    return {handle: sections for handle, sections in found.items() if sections}


def _metrics(tb, box: "Toolbox", plans: "dict | str", found: object, hourly: bool) -> "tuple[dict | str, dict]":
    """The section of the metrics of one resource: the rows of the metrics that have data (those with a value above 0 first, then by name), the names of those that have none and the names of those that
    could not be read. Returns it and what to register as evidence for each row, by name."""
    if isinstance(plans, str):
        return plans, {}
    rows, measured, quiet, broken, codes = [], {}, [], [], set()
    for name, plan in sorted(plans.items(), key=lambda item: item[0].lower()):
        result = found.get(name) if isinstance(found, dict) else None
        if isinstance(result, tuple):
            summary, unit = box._measured(result, plan, hourly)
            if tb._bucket(summary) == "no_data":
                quiet.append(name)
            else:
                measured[name] = (summary, unit)
                rows.append((tb._bucket(summary) != "positive", name.lower(), name, summary, unit))
        else:
            broken.append(name)
            codes.add(box._why(result).get("code", ""))
    rows.sort(key=lambda item: item[:2])
    read_at = any("read_at" in row[3] for row in rows)
    block: dict = {"offered": len(plans), "with_data": len(rows), "cols": [*METRIC_COLUMNS, *(["peak", "p95"] if hourly else []), *(["read_at"] if read_at else [])],
                   "rows": [[name, unit, summary["total"], summary["max"], summary["average"], summary["days_with_data"], *([summary["peak"], summary["p95"]] if hourly else []),
                             *([summary.get("read_at")] if read_at else [])] for _, _, name, summary, unit in rows]}
    for key, names in (("no_data", quiet), ("failed", broken)):
        if names:
            block[key] = names[:NO_DATA_SHOWN]
            if len(names) > NO_DATA_SHOWN:
                block[f"{key}_not_shown"] = len(names) - NO_DATA_SHOWN
    if codes - {""}:
        block["failed_codes"] = sorted(codes - {""})
    return block, measured


def _links(box: "Toolbox", state, number: "int | None") -> dict:
    """What a resource refers to and what refers to it, as a row for each type and relation with its count and the cost of those that have one (cases/neighbors.py)."""
    if number is None:
        return {"listed": False}  # a part that Resource Graph does not list as a resource, or one that the pass did not keep
    box._prefetch_costs(sub for sub in {box._sub_of(state.names[other]) for edges in (state.out.get(number, []), state.into.get(number, [])) for other, _ in edges} if sub)
    block: dict = {}
    for name, edges in (("refers_to", state.out.get(number, [])), ("referred_by", state.into.get(number, []))):
        rows = box._grouped([(state.names[other], relation, box._usd_of(state.names[other])) for other, relation in edges])
        block[name] = {"total": len(edges), "cols": ["type", "relation", "count", "usd30d"], "rows": rows[:LINK_ROWS], **({"rows_not_shown": len(rows) - LINK_ROWS} if len(rows) > LINK_ROWS else {})}
    return block


def counted(history: object) -> bool:
    """Whether a history says a number of days: how old the resource is, or when it was last changed."""
    return isinstance(history, dict) and any(isinstance(history.get(key), int) and not isinstance(history.get(key), bool) for key in ("age_days", "changed_days"))


def read_by(part: dict) -> str:
    """What a profile of one resource holds data of, as letters: `m` when a metric answered (with a value or with none), `d` when anything else is a row, a number or a link (a meter, a link, an Advisor
    item, an age or a last change, a part, a diagnostic setting). A part that was not read, that failed or that the type does not have holds none, so nothing is credited for it."""
    def has(block: object, name: str) -> bool:
        return isinstance(block, dict) and bool(block.get(name))

    metrics, links = part.get("metrics"), part.get("links")
    described = (has(part.get("meters"), "meters"), any(has(links.get(side) if isinstance(links, dict) else None, "total") for side in ("refers_to", "referred_by")),
                 isinstance(part.get("advisor"), list) and bool(part["advisor"]), counted(part.get("history")), has(part.get("children"), "total"), has(part.get("sends_to"), "total"))
    return ("m" if has(metrics, "with_data") or has(metrics, "no_data") else "") + ("d" if any(described) else "")


def _tasks(tb, box: "Toolbox", entries: list, plans: dict, days: int) -> dict:
    """The reads that a profile needs, each as a function of the clock of the call, by what it is for: the references of the estate, the ages, the Advisor items of each subscription, and for each
    resource its metrics, its meters, its Activity Log and, when it takes no data in, its diagnostic settings."""
    start, end = box._window(days)
    tasks: dict = {("graph",): lambda late: box._load_edges(), ("ages",): lambda late: box._ages_of(entries)}
    for sub in dict.fromkeys(entry.sub for entry in entries):
        tasks[("advisor", sub)] = lambda late, sub=sub: box._advice_for(sub)
    for entry in entries:
        handle, resource_id = entry.resource.handle, entry.resource.resource_id
        if isinstance(plans[handle], dict) and plans[handle]:
            tasks[(handle, "metrics")] = lambda late, handle=handle, resource_id=resource_id: box.arm.metric_reads(resource_id, plans[handle], start, end, late)
        if entry.part_of is None:
            tasks[(handle, "meters")] = lambda late, entry=entry: box._meters_for(entry, days)
        tasks[(handle, "log")] = lambda late, resource_id=resource_id: box._owners().log(resource_id)
        if "data_writers" not in tb.deeper.offered(tb.type_word(entry.resource.resource_type)):
            tasks[(handle, "sends_to")] = lambda late, handle=handle, resource_id=resource_id: box._once(("diagnostics", handle), lambda: box.arm.diagnostic_settings(resource_id))
    return tasks


def build_dossier(box: "Toolbox", handles: list[str], days: int = 30, grain: str = "day") -> dict:
    """The picture of one to MAX_HANDLES resources that the tools of `box` have shown, for the last `days` closed days (MIN_DAYS to 30), with the metrics at the grain `day` or `hour`. A part that
    could not be read says why, and a part that did not finish in the time of the call is `unread`, and named by handle. It raises ValueError, before it reads anything, for what the tool refuses, and
    UnknownHandle for a handle that no answer showed."""
    tb = _toolbox()
    wanted = list(dict.fromkeys(handles))
    if not 1 <= len(wanted) <= MAX_HANDLES or not MIN_DAYS <= days <= tb.MAX_DAYS or grain not in ("day", "hour"):
        raise ValueError(f"a profile is of 1 to {MAX_HANDLES} handles, of {MIN_DAYS} to {tb.MAX_DAYS} days, by the day or by the hour")
    entries = [box._entry(handle) for handle in wanted]
    hourly = grain == "hour"
    box._prefetch_costs(dict.fromkeys(entry.sub for entry in entries))
    kinds = {entry.resource.handle: tb.type_word(entry.resource.resource_type) for entry in entries}
    offers = {kind: box._offers(kind) for kind in dict.fromkeys(kinds.values())}
    plans = {handle: ({name: both[hourly] for name, both in offers[kind].items()} if isinstance(offers[kind], dict) else offers[kind]) for handle, kind in kinds.items()}
    tasks = _tasks(tb, box, entries, plans, days)
    done, left = box._run(tasks)
    unread = _unread(left, entries)
    graph = _outcome(tb, ("graph",), done, left)
    state = graph[1]
    unavailable = [sub for sub in box.subscriptions if state is not None and sub in set(state.failed)]
    incomplete = state is not None and (not state.done or bool(unavailable))
    history = box._history(entries, done.get(("ages",)), {entry.resource.handle: done.get((entry.resource.handle, "log")) for entry in entries})
    profiles, lists, shown = [], [], []
    for entry in entries:
        handle, kind = entry.resource.handle, kinds[entry.resource.handle]
        facts = box._facts(entry, tb.DESCRIBED_PROPERTIES)
        part: dict = {"handle": handle, "type": kind, **{name: facts[key] for name, key in (("sku", "sku"), ("kind", "kind"), ("region", "location")) if facts.get(key) is not None},
                      "managed": facts["managed"], **{key: facts[key] for key in ("cost30d", "cost_by_service", "part_of", "property_list") if key in facts}, "properties": dict(facts["properties"])}
        lists.append((part["properties"], part, "properties"))
        if entry.part_of is None:
            word, _ = _outcome(tb, (handle, "meters"), done, left)
            if word is None:
                answer = box._tool_cost_meters({"handle": handle, "type": None, "service": None, "days": days, "offset": 0}, METER_ROWS)
                part["meters"] = {key: answer[key] for key in ("usd_total", "meters", "costs", "error", "code", "same", "cols", "rows") if key in answer}
                lists.append((part["meters"].get("rows", []), part["meters"], "rows"))
            else:
                part["meters"] = word
        word, found = _outcome(tb, (handle, "metrics"), done, left)
        part["metrics"], measured = (word, {}) if word else _metrics(tb, box, plans[handle], found, hourly)
        if isinstance(part["metrics"], dict):
            lists += [(part["metrics"]["rows"], part["metrics"], "rows"), (part["metrics"].get("no_data", []), part["metrics"], "no_data")]
        part["links"] = graph[0] or ({"complete": False} if not state.done else _links(box, state, state.ids.get(entry.key)))
        if unavailable and isinstance(part["links"], dict):
            box._listing(part["links"], "unavailable", unavailable)
        word, found = _outcome(tb, ("advisor", entry.sub), done, left)
        advice = [item for item in found or [] if item.resource_id.lower() == entry.key][:ADVISOR_ROWS]
        if word:
            part["advisor"] = word
        elif advice:
            part["advisor"] = [{key: value for key, value in item.facts.items() if value is not None} for item in advice]
            lists.append((part["advisor"], part, "advisor"))
        part["history"] = UNREAD if "history" in unread.get(handle, []) else history[handle]
        if "children" in tb.deeper.offered(kind):
            part["children"] = {key: value for key, value in box._tool_children({"handle": handle}).items() if key not in ("handle", "returned")}
        if (handle, "sends_to") in tasks:
            word, _ = _outcome(tb, (handle, "sends_to"), done, left)
            part["sends_to"] = word or box._sends_to(entry)["diagnostic_settings"]
        profiles.append(part)
        shown.append((entry, facts, part, measured, advice))
    answer = {"days": days, "grain": grain, "partial": bool(unread) or incomplete, **({"unread": unread} if unread else {}), "profiles": profiles}
    box._fit(answer, lists, max(tb.MAX_RESULT_CHARS, PER_HANDLE * len(entries)))
    for entry, facts, part, measured, advice in shown:
        handle = entry.resource.handle
        box._show(entry, {**facts, "properties": dict(part["properties"])})
        for row in part["metrics"]["rows"] if isinstance(part["metrics"], dict) else []:
            box._record_metric(handle, row[0], measured[row[0]][0], days, measured[row[0]][1])
            box._count_read(kinds[handle], handle, row[0], days, measured[row[0]][0])
        for item in advice[:len(part["advisor"])] if isinstance(part.get("advisor"), list) else []:
            box._record_advice(handle, item)
        if isinstance(part["history"], dict):
            box.evidence[handle]["history"] = dict(part["history"])
    return answer
