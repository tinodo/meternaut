"""The impact of removing a resource: what depends on it, found with reads and nothing else, and a verdict that code derives from the facts.

A platform engineer asks the same questions before removing anything. Each kind of resource that has a check (CHECKS: today the private endpoint) reads what those questions need: Azure Resource Graph,
the two lists of Azure Resource Manager that http.allowed_calls names for it, the Activity Log and Azure Monitor. `analyse` returns one digest, which the case keeps in its facts under KEY: the
verdict (VERDICTS), its reasons, what was read and where, what happens to traffic and DNS if the resource is removed, how to undo that, and what could not be seen, all in the words of a person.
The verdict comes from the rules of `_judge` and from nothing else: no model makes it, explains it or sees it. A read that fails is never none: the fact is unknown, it is in the "Not checked" line,
the check is not complete, and the verdict is never safe.

Whose rights: every read is made with the reader identity of the cases app, the one that reads the estate for the Watch (the Reader role on the subscriptions that it can read, AGENTS.md rule 24),
through the client of cases/http.py whose list of calls holds reads and queries only. No role is added and nothing is written (rule 29): the app only reads, and a person who acts on the advice
does it in Azure with their own rights.
"""
from __future__ import annotations

import datetime as dt
import ipaddress
import math
from collections import Counter
from typing import Callable, Collection, Sequence, TypeVar

from .arm import DNS_ZONE_ID, SCOPE_ID, Arm
from .brief import IMPACT as KEY
from .brief import MEASURED_DAYS, plain, quantity, who_text
from .http import HttpError, Refused
from .identity import IdentityError
from .ownership import NOT_VISIBLE, UNAVAILABLE, OwnerReader

T = TypeVar("T")
READ_ERRORS = (HttpError, Refused, IdentityError)
MAX_READS = 80  # the reads of all the checks of one run
WINDOW = 30  # the days of traffic that are read
MAX_ADDRESSES = 6
MAX_ZONES = 3
MAX_NAMES = 4  # the names of DNS records that a sentence lists
STAMP = "%Y-%m-%dT%H:%M:%SZ"  # the time of a write and of the read, in UTC
STATES = ("approved", "pending", "rejected", "disconnected")  # what a connection of a private endpoint can be, the best first
ENDPOINTS = "microsoft.network/privateendpoints"
USE_METRICS = ("PEBytesIn", "PEBytesOut")
NEVER_SEEN = ("whether a policy or a template makes it again", "name servers and firewall rules that Azure Resource Graph does not list", "anything in a subscription that Meternaut cannot read")
LABELS = {"endpoint": "the endpoint itself", "service": "the service that it points at", "others": "the other endpoints to the service", "mentions": "what mentions its addresses",
          "addresses": "the addresses of the endpoint", "dns": "the DNS zone groups of the endpoint", "zone": "the records of its DNS zone", "traffic": "its traffic",
          "log": "its changes in the Activity Log"}
WORDS = {NOT_VISIBLE: "not visible with this access", UNAVAILABLE: "the read failed"}  # what a read that failed says; any other word of `failed` is its own plain reason
# Learn ("What is a private endpoint?", "Manage Azure private endpoints", read on 2026-11-13): only an approved endpoint sends traffic; the owner can change the state later, so a rejected endpoint
# may have carried traffic; a denied connection cannot be approved again, so no sentence says that the owner could.
STATE_SAYS = {
    "approved": "It is approved, so it can carry traffic.",
    "pending": "It waits for the owner of the service to approve it: somebody asked for it, and removing it drops that request.",
    "rejected": "The owner of the service rejected it, so it cannot carry traffic now: only an approved endpoint can.",
    "disconnected": "The owner of the service removed the connection, so the endpoint cannot carry traffic. Microsoft says that such an endpoint becomes informative and should be deleted for cleanup.",
    "unknown": "Its connection state could not be read.",
}
UNDO = ("Make the endpoint again in the same subnet, for the same service, and ask the owner of the service to approve it. Then add its DNS zone group, so that the records come back. "
        "Its addresses may be different.")
NIC = "microsoft.network/networkinterfaces"
# Queries start with the line that marks them as this app's own (the logs and the tests tell them by it).
ONE = "// meternaut:impact-one\nresources\n| where id =~ '{id}'\n| project id, name, properties"
OTHERS = ("// meternaut:impact-others\nresources\n| where type =~ 'microsoft.network/privateendpoints' and id !~ '{pe}'\n"
          "| where tostring(properties.privateLinkServiceConnections) contains '{service}' or tostring(properties.manualPrivateLinkServiceConnections) contains '{service}'\n"
          "| project id, name, properties")
# No interface is left out: the endpoint's own interface holds its address, so a search that works lists it (the control), and it is not counted as a mention.
MENTIONS = ("// meternaut:impact-mentions\nresources\n| where id !~ '{pe}'\n| where {any}\n| summarize n = count() by type")


def _list(value: object) -> list[dict]:
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _dict(value: object) -> dict:
    return value if isinstance(value, dict) else {}


def _props(row: object) -> dict:
    return _dict(_dict(row).get("properties"))


def _id(value: object) -> str:
    """An id that may go into a query: one id of a resource, which has no quote in it. The text of an estate is put into a query in no other way."""
    return value if isinstance(value, str) and SCOPE_ID.fullmatch(value) and "'" not in value else ""


def _address(value: object) -> str:
    try:
        return str(ipaddress.ip_address(str(value).strip()))
    except ValueError:
        return ""


def _best(states: Sequence[str]) -> str:
    return next((state for state in STATES if state in states), "unknown")


def _connections(props: dict) -> list[tuple[str, str, str]]:
    """(service id, state, what its owner wrote of it) of each connection of an endpoint to a service: the ones that Azure makes by itself and the ones that are asked for by hand."""
    found = []
    for item in _list(props.get("privateLinkServiceConnections")) + _list(props.get("manualPrivateLinkServiceConnections")):
        link = _props(item)
        said = _dict(link.get("privateLinkServiceConnectionState"))
        state = str(said.get("status") or "").strip().lower()
        words = "; ".join(part for part in (plain(said.get("description"), 80), f"actions required: {plain(said.get('actionsRequired'), 40)}" if said.get("actionsRequired") else "") if part)
        found.append((str(link.get("privateLinkServiceId") or ""), state if state in STATES else "unknown", words))
    return found


class Reader:
    """The reads of the impact checks of one run, inside one budget of reads. A read that fails puts a word in the `failed` of its check, and the check goes on without it."""

    def __init__(self, arm: Arm, subscriptions: Sequence[str], now: dt.datetime, owners: OwnerReader | None = None, own: Collection[str] = (), notes: list[str] | None = None,
                 max_reads: int = MAX_READS) -> None:
        self.arm, self.subscriptions = arm, tuple(subscriptions)
        self.now = now if now.tzinfo else now.replace(tzinfo=dt.timezone.utc)
        self.owners = owners if owners is not None else OwnerReader(arm, self.now)
        self.own = {text.lower() for text in own if text}  # the identities of Meternaut itself: a change by one of them is not an automation of somebody else
        self.notes = notes if notes is not None else []
        self.reads, self.max_reads = 0, max_reads

    def read(self, failed: dict[str, str], what: str, call: Callable[[], T]) -> T | None:
        if self.reads >= self.max_reads:
            failed[what] = UNAVAILABLE
            return None
        self.reads += 1
        try:
            return call()
        except READ_ERRORS as error:
            failed[what] = NOT_VISIBLE if getattr(error, "status", None) in (401, 403) else UNAVAILABLE
            self.notes.append(f"impact: {LABELS.get(what, what)} could not be read ({str(error)[:160]})")
            return None

    def graph(self, failed: dict[str, str], what: str, query: str) -> list[dict]:
        return (self.read(failed, what, lambda: self.arm.graph_many(self.subscriptions, query)) if self.subscriptions else None) or []


# -- the facts of a private endpoint -----------------------------------------------------------------------------------------------------------------

def _theirs(props: dict, endpoint: str) -> str:
    """What a service says of one endpoint in its own list of connections: its state, "unlisted" when the list does not hold it, and "unknown" when the service gives no such list."""
    if "privateEndpointConnections" not in props:
        return "unknown"
    states = [str(_dict(_props(item).get("privateLinkServiceConnectionState")).get("status") or "").strip().lower() for item in _list(props["privateEndpointConnections"])
              if str(_dict(_props(item).get("privateEndpoint")).get("id") or "").lower() == endpoint.lower()]
    return _best(states) if states else "unlisted"


def _dns(reader: Reader, failed: dict[str, str], endpoint: str, mine: set[str]) -> tuple[set[str], set[str], list[str]]:
    """The DNS side of an endpoint: the names of the records that it keeps (its zone groups say) or that point at its addresses (the records of those zones say), the names whose record also holds
    the addresses of others, and the names of its zones. The addresses that its zone groups name are added to `mine`."""
    names: set[str] = set()
    zones: dict[str, None] = {}
    for group in reader.read(failed, "dns", lambda: reader.arm.zone_groups(endpoint)) or []:
        for config in _list(_props(group).get("privateDnsZoneConfigs")):
            found = _props(config)
            zones.setdefault(str(found.get("privateDnsZoneId") or ""))
            for record in _list(found.get("recordSets")):
                names.add(plain(record.get("recordSetName"), 60))
                mine.update(address for address in map(_address, record.get("ipAddresses") or []) if address)
    sharing: set[str] = set()
    for zone in [zone for zone in zones if DNS_ZONE_ID.fullmatch(zone)][:MAX_ZONES]:
        for record in reader.read(failed, "zone", lambda zone=zone: reader.arm.zone_records(zone)) or []:
            found = {address for address in (_address(item.get("ipv4Address")) for item in _list(_props(record).get("aRecords"))) if address}
            if found & mine:
                names.add(plain(record.get("name"), 60))
                if found - mine:
                    sharing.add(plain(record.get("name"), 60))
    return names - {""}, sharing - {""}, [plain(zone.rsplit("/", 1)[-1], 80) for zone in zones if zone]


def _traffic(reader: Reader, failed: dict[str, str], endpoint: str) -> tuple[str, str]:
    """What Azure Monitor counted through the endpoint in the last WINDOW days, as ("some" | "zero" | "unmeasured", the words for a person). Zero needs a reading of nil on at least MEASURED_DAYS
    days for every metric: no data, a read that failed or a few days do not show that nothing used it (the rule of cases/brief.py measured_zero)."""
    totals: list[float | None] = []
    days: list[int] = []
    for name in USE_METRICS:
        got = reader.read(failed, "traffic", lambda name=name: reader.arm.metrics(endpoint, name, reader.now - dt.timedelta(days=WINDOW), reader.now))
        points = got[1] if got is not None else []
        values = [point.total for point in points if point.total is not None]
        totals.append(math.fsum(values) if values else None)
        days.append(sum(1 for point in points if point.total is not None or point.maximum is not None or point.average is not None))
    said = f"{quantity(totals[0] or 0, 'Bytes')} in and {quantity(totals[1] or 0, 'Bytes')} out"
    if any(totals):
        return "some", f"{said}, on {max(days)} of {WINDOW} days"
    if all(total == 0 for total in totals) and min(days) >= MEASURED_DAYS:
        return "zero", f"{said}, with a value on {min(days)} of {WINDOW} days"
    return "unmeasured", "Not measured: the read failed" if "traffic" in failed else f"Not measured: Azure Monitor gave a value on {max(days)} of {WINDOW} days, and {MEASURED_DAYS} are needed"


def _day(value: dt.datetime | str) -> str:
    """A day as a person reads it, always the day in UTC and never "yesterday": a page may be opened days after the read."""
    moment = dt.datetime.strptime(value, STAMP) if isinstance(value, str) else value
    return f"{moment.day} {moment:%b %Y} UTC"


def _change(reader: Reader, failed: dict[str, str], endpoint: str) -> tuple[str, str, str]:
    """Who changed the endpoint, as ("none" | "person" | "meternaut" | "automation", the time of the write that says so, the words for a person), from every write of its Activity Log: an
    automation if any write of the 90 days is by an identity that is no person and not Meternaut's own (its caller is an id, which names no person), else the newest write. The log is read in
    pages, newest first, and at most a few: when they stop early only part of the 90 days was read, and the check is not complete. Dates are absolute: a page may be opened days after the read."""
    writes = reader.owners.writes(endpoint)
    if writes is None:
        failed["log"] = UNAVAILABLE
        return "none", "", "Not read: the Activity Log could not be read"
    whole = reader.owners.complete(endpoint)
    if not whole:
        failed["log"] = "only part of the 90 days was read"
    span = "the 90 days before Meternaut read it" if whole else "the part of the 90 days that was read"
    if not writes:
        return "none", "", f"No change found in {span}"

    def kind(caller: str) -> str:
        return "person" if "@" in caller else "meternaut" if caller.lower() in reader.own else "automation"

    def who(write: tuple[dt.datetime, str]) -> str:
        return f"{_day(write[0])}, by {'Meternaut' if kind(write[1]) == 'meternaut' else who_text(write[1])}"

    found = next((write for write in writes if kind(write[1]) == "automation"), writes[0])
    more = f"; an application or service identity wrote on {_day(found[0])}" if found != writes[0] else ""  # the row says the newest write: an automation's older one is the second thing that it says
    return kind(found[1]), found[0].strftime(STAMP), f"{who(writes[0])}{more}; {len(writes)} change{'s' if len(writes) != 1 else ''} in {span}"


def _judge(f: dict, things: str) -> tuple[str, list[str]]:
    """The verdict and its reasons from the facts. Keep: the endpoint is in use (it is approved and carries traffic, or it is the only private way to a service that takes nothing public).
    Safe: it is disconnected or rejected, every read worked and nothing points at it or manages it. Check first: anything else, with each thing that is unsettled as a sentence. A good reason is
    listed only when it was read (a search that could be trusted, a service that was seen)."""
    state, use = f["state"], f["traffic"]
    keep: list[str] = []
    check: list[str] = []
    good: list[str] = [STATE_SAYS[state]] if state in ("rejected", "disconnected") else []
    if state == "approved":
        if use == "some":
            keep.append("It carries traffic: Azure Monitor counted some in the 30 days before Meternaut read it.")
        if not f["othersApproved"] and f["publicAccess"] == "disabled":
            keep.append("It is the only approved private way to the service, and the service does not accept public traffic.")
        if not keep:
            check.append(STATE_SAYS[state] + (" No traffic was measured, but something may use it now and then." if use == "zero" else " Nothing measured shows that nothing uses it."))
    elif state in ("pending", "unknown"):
        check.append(STATE_SAYS[state])
    elif use == "some":
        check.append("Azure Monitor counted traffic although it is disconnected: the readings disagree.")
    if state in ("rejected", "disconnected"):
        if f["serviceSays"] in ("approved", "pending"):
            check.append(f"The service lists it as {f['serviceSays']}, not as {state}: the two disagree.")
        if f["othersApproved"] and f["service"] == "seen":
            good.append("Another endpoint to the same service is approved.")
    if things:
        check.append(f"Something else mentions its addresses ({things}): check that it does not rely on this endpoint.")
    elif state in ("rejected", "disconnected") and f["searched"]:
        good.append("Nothing that Azure Resource Graph lists mentions its addresses.")
    if f["changedBy"] == "automation":
        check.append(f"An application or service identity changed it on {_day(f['changedAt'])}: an automation may manage it and make it again.")
    if not f["complete"]:
        check.append("Not everything could be read (see Not checked), so this cannot be called safe.")
    if keep:
        return "keep", keep
    return ("check", check) if check else ("safe", good + {"zero": ["Azure Monitor shows no traffic."], "unmeasured": ["Its traffic was not measured, and its state says that it carries none."]}.get(use, []))


def _removal(f: dict, names: Sequence[str], zones: Sequence[str]) -> list[str]:
    """What happens to traffic and to DNS if the endpoint is removed."""
    if f["state"] == "approved":
        traffic = ("Clients that use it must use another approved endpoint: their DNS decides which one they reach." if f["othersApproved"] else
                   "Clients lose their private way to the service, and use its public address if it accepts public traffic." if f["publicAccess"] == "enabled" else
                   "Clients lose their private way to the service, and cannot reach it." if f["publicAccess"] == "disabled" else
                   "Clients lose their private way to the service. Whether they can still reach it depends on its public access, which Meternaut could not read.")
    else:
        traffic = "Nothing carries traffic through it yet, and the request to connect is withdrawn." if f["state"] == "pending" else "No traffic changes: it cannot carry any."
    dns = (f"Azure removes its DNS records ({', '.join(sorted(names)[:MAX_NAMES])}{' and more' if len(names) > MAX_NAMES else ''}) from {', '.join(zones[:MAX_ZONES]) or 'the zone'}"
           f"{', and a record that also holds the addresses of others keeps theirs' if f['dnsShared'] else ''}. "
           "Computers that use that zone get no answer for those names unless another record answers them." if names else "It has no DNS records that Meternaut could read.")
    return [traffic, dns]


def _private_endpoint(reader: Reader, endpoint: str) -> dict:
    """The check of a private endpoint: the state of its connection and what the service says of it, the public access of the service, the other endpoints to the service, its DNS records and
    who shares them, what else mentions its addresses, who changed it last and the traffic through it."""
    failed: dict[str, str] = {}
    own = reader.graph(failed, "endpoint", ONE.format(id=endpoint))
    if not own:
        failed.setdefault("endpoint", UNAVAILABLE)
    props = _props(own[0] if own else {})
    links = _connections(props)
    service = next((target for target, _, _ in links if _id(target)), "")
    if links and not service:
        failed["service"] = UNAVAILABLE  # the connection names no service that can be read
    state = _best([link[1] for link in links])
    mine = {address for address in (_address(ip) for config in _list(props.get("customDnsConfigs")) for ip in config.get("ipAddresses") or []) if address}
    seen, said, public, rivals = "none", "unlisted", "unknown", []
    if service:
        found = reader.graph(failed, "service", ONE.format(id=service))
        seen = "seen" if found else "unseen"
        if not found:  # a service in a subscription that the app cannot read gives no row: that is not a service with nothing to say, and it is the usual shape of a shared service
            failed.setdefault("service", "it could not be seen: it may be in a subscription that Meternaut cannot read")
        theirs = _props(found[0]) if found else {}
        said = _theirs(theirs, endpoint)
        public = str(theirs.get("publicNetworkAccess") or "").strip().lower()
        rivals = [(plain(_dict(item).get("name"), 80), _best([link[1] for link in _connections(_props(item)) if link[0].lower() == service.lower()]))
                  for item in reader.graph(failed, "others", OTHERS.format(pe=endpoint, service=service))]
    names, sharing, zones = _dns(reader, failed, endpoint, mine)
    if not mine or len(mine) > MAX_ADDRESSES:
        failed["addresses"] = f"only {MAX_ADDRESSES} of its {len(mine)} were searched for" if mine else "none could be read, so nothing could be searched for"
    hits = reader.graph(failed, "mentions", MENTIONS.format(pe=endpoint, any=" or ".join(f"tostring(properties) has '{ip}'" for ip in sorted(mine)[:MAX_ADDRESSES]))) if mine else []
    found_types = [item for item in hits if isinstance(item.get("n"), int) and isinstance(item.get("type"), str)]
    if mine and "mentions" not in failed and not any(item["type"].lower() == NIC for item in found_types):  # the endpoint's own interface holds its address: a search that misses it misses things
        failed["mentions"] = "the search did not find the endpoint's own network interface, so its answer cannot be trusted"
    found_types = [item for item in found_types if item["type"].lower() != NIC]
    things = ", ".join(f"{item['type'].rsplit('/', 1)[-1]} ({item['n']})" for item in found_types)
    by, changed_at, changed = _change(reader, failed, endpoint)
    use, traffic = _traffic(reader, failed, endpoint)
    states = Counter(other for _, other in rivals)
    f = {"state": state, "service": seen, "serviceSays": said, "publicAccess": public if public in ("enabled", "disabled") else "unknown", "others": len(rivals),
         "othersApproved": states["approved"], "dnsNames": len(names), "dnsShared": len(sharing), "mentions": sum(item["n"] for item in found_types), "searched": not {"addresses", "mentions"} & failed.keys(),
         "traffic": use, "changedBy": by, "changedAt": changed_at, "complete": not failed}

    def gap(what: str, value: str) -> str:
        """A read that failed, or that was not made, is never "none": the row says so."""
        return f"Not known ({WORDS.get(failed[what], failed[what])})" if what in failed else value

    why = failed.get("mentions") or failed.get("addresses") or ""
    rows = [["State that the endpoint reports", (f"{state.capitalize()}{': ' + links[0][2] if links[0][2] else ''}" if len(links) == 1 else
                                                 f"{state.capitalize()} at best, of {len(links)} connections ({', '.join(link[1] for link in links)})") if links else "Not read",
             "Azure Resource Graph: the endpoint"],
            ["What the service says about it", {"unlisted": "It does not list this endpoint", "unknown": "It gives no list of its endpoints"}.get(said, said.capitalize()) if seen == "seen"
             else "The service could not be seen" if seen == "unseen" else "No service is named", "Azure Resource Graph: the service"],
            ["Public access of the service", f["publicAccess"].capitalize() if f["publicAccess"] != "unknown" else "Not stated", "Azure Resource Graph: the service"],
            ["Other endpoints to the service", gap("others", f"{len(rivals)}" + (f" ({', '.join(f'{count} {word}' for word, count in sorted(states.items()))})" if rivals else "")) if service else "Not read",
             "Azure Resource Graph"],
            ["DNS records of the endpoint", gap("dns", (", ".join(sorted(names)[:MAX_NAMES]) + (f"; {len(sharing)} also hold the addresses of others" if sharing else "")) if names else "None found"),
             "Azure Resource Manager: its DNS zone groups and their zones"],
            ["Things that mention its addresses", things or ("None" if f["searched"] else "Not searched" if not mine else f"Not known ({WORDS.get(why, why)})"), "Azure Resource Graph"],
            ["Last change", changed, "Activity Log"], ["Traffic in the 30 days before it was read", traffic, "Azure Monitor"]]
    verdict, reasons = _judge(f, things)
    unchecked = [*(f"{LABELS[what]} ({WORDS.get(word, word)})" for what, word in failed.items()), *NEVER_SEEN]
    return {"verdict": verdict, "complete": f["complete"], "reasons": reasons[:6], "rows": [[plain(cell, 240) for cell in row] for row in rows], "removal": _removal(f, sorted(names), zones),
            "undo": UNDO, "unchecked": unchecked, "facts": f}


CHECKS: dict[str, Callable[[Reader, str], dict]] = {ENDPOINTS: _private_endpoint}


def has_check(rtype: object) -> bool:
    """Whether the impact of a resource of this type is checked here."""
    return isinstance(rtype, str) and rtype.strip().lower() in CHECKS


def analyse(reader: Reader, resource_id: str, rtype: object) -> dict | None:
    """The digest of the check of one resource, or None when its type has no check. It never raises: a fault of the check is a digest that says that it is not complete. It says when it was read
    (`readAt`, UTC): a page may be opened days later."""
    check = CHECKS.get(rtype.strip().lower()) if isinstance(rtype, str) else None
    if check is None or not _id(resource_id):
        return None
    at = reader.now.astimezone(dt.timezone.utc).strftime(STAMP)
    try:
        return {**check(reader, resource_id), "readAt": at}
    except Exception:  # noqa: BLE001 (a check never stops an investigation)
        return {"verdict": "check", "complete": False, "readAt": at, "reasons": ["The check could not be made."], "rows": [], "removal": [], "undo": "", "unchecked": list(NEVER_SEEN),
                "facts": {"complete": False}}
