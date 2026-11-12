"""The decision brief: what a person needs in order to decide, built from the records of one case, its plan and its action.

A stranger who has never seen Meternaut must be able to answer eight questions from a brief, in a minute, without opening anything else: what am I asked to decide, what
do I get, how sure is it and on what evidence, what exactly happens if I say yes (who does it, with whose rights), can it be undone, what could go wrong, whose resource is
it, and what are my choices. A field of the brief answers one of them. What does not stay out of the default view.

The web page, the letter and (later) the card are renders of this one object; the answer is recorded once, by the approval loop. Everything here is a pure function of the
records and of the time that the caller passes in: no clock, no store, no network. Text that came from the estate (names, tags, a model's words) is cut to one line and kept
as data; the renders escape it, and nothing here trusts it. The words that code writes (the change, the undo, the risk, how sure) never come from a model.
"""
from __future__ import annotations

import datetime as dt
import math
import re
import unicodedata
from dataclasses import dataclass
from typing import Mapping, Sequence

from . import costs as cost_words
from . import estimate as estimates
from .twopeople import confirmations, counts, needs, standing
from .families.words import called_of, kinds, shown, type_of, words_of  # called_of and kinds are also read by the pages, which know the brief and the records and nothing else
from .models import ADVISE, GROUP_FACT, REFUSED, TIME_FORMAT, TWO_PEOPLE_CLASS, ActionRecord, CaseRecord, DecisionRecord, PlanRecord, Readiness

MAX_FACTS = 5
MAX_REASON = 240  # the most characters of what an AI wrote that a brief shows
MAX_NAME = 120
MAX_GROUP_NAMES = 12  # the names of the other resources that a case which stands for many resources keeps (cases/investigate.py keeps the same number)
MAX_GROUP = 100000  # the most resources that the digest of such a case may count and still be believed
MAX_EXAMPLES = 6  # the resources that the row "Examples" of such a case names: the one that the case belongs to and the next five
MAX_EXAMPLE = 48  # the characters of one of those names
CONFIDENT = 0.85  # the first AI's own confidence that "High" asks for; the gate for a proposal is decide.PROPOSE_CONFIDENCE
SURE_ENOUGH = 0.7
# A case that has this status was proposed, so its second AI agreed (decide.py gives the status proposed to nothing else, and a plan of a change is made for no other case).
AGREED = ("proposed", "awaiting_ok", "approved", "running", "done", "failed", "verified")
# What code wrote among the objections of a case (decide.py, investigate.py): they are notes of code and not the second AI's doubt.
CODE_NOTES = ("no measurement backs this finding", "the Investigator gave a confidence of", "past cases like this", "nothing measured shows that", "others share this kind of resource")
# What the capability profile (cases/capability.py) says that the identity cannot see, as the one sentence of a brief that its advice rests on: said only when it changes what Meternaut can say.
ACCESS_WORDS = {
    "reservations-not-visible": "This estate's reservations are not visible with the current access, so no commitment advice.",
    "savings-plans-not-visible": "This estate's savings plans are not visible with the current access, so no commitment advice.",
    "commitments-not-visible": "This estate's reservations and savings plans are not visible with the current access, so no commitment advice.",
    "savings-plans-not-offered": "Savings plans are not offered under this estate's agreement, so there is no savings plan advice.",
}
RESOURCE_GRAPH = "Azure Resource Graph"
MONITOR = "Azure Monitor"
CHECKED = "Azure, checked by code"
# The verb of a headline, from what the first AI recommends: a finding that asks for a look (investigate, or no recommendation that is known) is "Look at".
VERBS = {"delete": "Consider deleting", "change": "Consider changing", "keep": "Keep"}
# Missing data is not zero: a measurement shows that nothing used a resource only when at least this many days of its window had a value (the chart of use asks the same, usage.MIN_DAYS).
MEASURED_DAYS = 20
USE_BASES = ("no-usage", "low-usage", "unused-feature")  # what a finding of the investigation has for a basis when it says that something is not used
# Platform resources that others share, as the start of their type in lower case: private endpoints, private DNS zones and their links, gateways of networks, firewalls, route tables, NAT gateways,
# API Management, Bastion, ExpressRoute and VPN objects, peerings. Meternaut never asks to delete one, however quiet it looks, because what depends on it cannot be seen from here.
SHARED = ("microsoft.network/privateendpoints", "microsoft.network/privatednszones", "microsoft.network/privatelinkservices", "microsoft.network/virtualnetworkgateways",
          "microsoft.network/azurefirewalls", "microsoft.network/firewallpolicies", "microsoft.network/routetables", "microsoft.network/natgateways", "microsoft.apimanagement/service",
          "microsoft.network/bastionhosts", "microsoft.network/expressroute", "microsoft.network/vpn", "microsoft.network/p2svpngateways", "microsoft.network/localnetworkgateways",
          "microsoft.network/connections", "microsoft.network/virtualnetworks/virtualnetworkpeerings")
HELD_UNPROVEN = "nothing measured shows that nothing uses it, so this asks for a look and not for a deletion"  # what code notes when it turns a finding that asks to delete into a look
HELD_SHARED = "others share this kind of resource, so this asks for a look and not for a deletion"
# The risk of doing what an advice suggests, which is not the risk of answering: the second says so on every page, letter and card.
ACTING = "If you act on it: "
IF_ACTED = " if you act on it"  # what the chip of such a risk adds to its word: "High risk if you act on it"
UNPROVEN = "Unproven: nothing shows that nothing uses it."
SHARED_RISK = "Could break traffic that you cannot see from here."
RARE_USE = "Something that is used less often than the days measured may still need it."
CHANGE_RISK = "What depends on it can slow down or stop."
NOT_MEASURED = "Not measured: Azure Monitor gave no values on enough days, so nothing shows that nothing uses it."
CHECK_FIRST = ("What it connects to: open it in the Azure portal and read what it points at and what uses it.",
               "Who owns it: ask the owner that this page names, or the team that runs the subscription that it is in.",
               "Its traffic: read its metrics in Azure Monitor over a month or more, and ask what uses it only now and then.")
CHECK_FIRST_SHORT = "Check first: what it connects to, who owns it, and its traffic."
# What removing a resource would do (cases/impact.py makes the digest, which the case keeps in its facts under IMPACT): the verdict, in the three words that every page, letter and card uses.
IMPACT = "impact"
IMPACT_VERDICTS = {"safe": "Safe to remove", "check": "Check first", "keep": "Do not remove"}
NOT_ANALYSED = "Impact not analysed: Meternaut has no check yet for what depends on this kind of resource, so it did not look."
SAFE_RISK = "Nothing that Meternaut could read depends on it. Some things cannot be seen from here: see Not checked."
KEEP_RISK = "It is in use, and removing it breaks what uses it."
HELD_REASONS = ("automation", "impact", "inuse")  # why a Watch holds a finding back and makes no request for it (cases/investigate.py)

# resource type -> (what the resource is, in a sentence of a person)
TYPE_WORDS = {
    "microsoft.compute/disks": ("Managed disk", "disk"),
    "microsoft.compute/snapshots": ("Snapshot", "snapshot"),
    "microsoft.network/publicipaddresses": ("Public IP address", "public IP address"),
    "microsoft.network/networkinterfaces": ("Network interface", "network interface"),
    "microsoft.network/natgateways": ("NAT gateway", "NAT gateway"),
    "microsoft.network/privateendpoints": ("Private endpoint", "private endpoint"),
    "microsoft.network/loadbalancers": ("Load balancer", "load balancer"),
    "microsoft.network/p2svpngateways": ("Point-to-site gateway", "point-to-site gateway"),
    "microsoft.network/applicationgateways": ("Application gateway", "application gateway"),
    "microsoft.network/azurefirewalls": ("Firewall", "firewall"),
    "microsoft.web/serverfarms": ("App Service plan", "App Service plan"),
    "microsoft.web/sites": ("App Service app", "app"),
    "microsoft.compute/virtualmachines": ("Virtual machine", "virtual machine"),
    "microsoft.compute/virtualmachinescalesets": ("Virtual machine scale set", "virtual machine scale set"),
    "microsoft.storage/storageaccounts": ("Storage account", "storage account"),
    "microsoft.sql/servers/databases": ("SQL database", "SQL database"),
    "microsoft.sql/servers/elasticpools": ("SQL elastic pool", "SQL elastic pool"),
    "microsoft.dbforpostgresql/flexibleservers": ("PostgreSQL server", "PostgreSQL server"),
    "microsoft.dbformysql/flexibleservers": ("MySQL server", "MySQL server"),
    "microsoft.documentdb/databaseaccounts": ("Cosmos DB account", "Cosmos DB account"),
    "microsoft.cache/redis": ("Redis cache", "Redis cache"),
    "microsoft.containerservice/managedclusters": ("Kubernetes cluster", "Kubernetes cluster"),
    "microsoft.eventhub/namespaces": ("Event Hubs namespace", "Event Hubs namespace"),
    "microsoft.servicebus/namespaces": ("Service Bus namespace", "Service Bus namespace"),
    "microsoft.kusto/clusters": ("Data Explorer cluster", "Data Explorer cluster"),
    "microsoft.recoveryservices/vaults": ("Recovery Services vault", "Recovery Services vault"),
    "microsoft.operationalinsights/workspaces": ("Log Analytics workspace", "Log Analytics workspace"),
    "microsoft.cognitiveservices/accounts": ("AI services account", "AI services account"),
    "microsoft.subscriptions/subscriptions": ("Subscription", "subscription"),
    "microsoft.resources/subscriptions/resourcegroups": ("Resource group", "resource group"),
    "microsoft.resources/resourcegroups": ("Resource group", "resource group"),
}
GUARD_WORDS = {
    "locked": "A management lock covers the resource.",
    "keep-tag": "A tag asks to keep the resource.",
    "too-new": "The resource is less than 7 days old.",
    "managed-group": "A platform manages the resource group.",
    "unverified": "A guard could not be read, so it counts as on.",
}
REASON_WORDS = {"still-needed": "it is still needed", "figure-wrong": "the figure is wrong", "handled": "it is already handled", "other": "another reason"}
# What the query of each detector asserts, which code read from Azure: the one fact that says why the resource is a lead.
DETECTOR_STATE = {
    "orphan-managed-disk": ("State", "Not attached to any virtual machine"),
    "orphan-public-ip": ("State", "Not assigned to anything"),
    "load-balancer-without-backends": ("Backends", "None in any pool"),
    "empty-app-service-plan": ("Apps", "None run on this plan"),
    "stopped-vm": ("State", "Stopped"),
    "orphan-private-endpoint": ("Connection", "No approved connection"),
}
BASIS_WORDS = {"no-usage": "No recorded usage", "low-usage": "Little recorded usage", "oversized": "Larger than its use needs", "duplicate": "Duplicated",
               "unused-feature": "A paid feature that is unused", "commitment-misfit": "A commitment that does not fit the use"}
DISK_TYPES = {"standard_lrs": "Standard HDD (LRS)", "standardssd_lrs": "Standard SSD (LRS)", "premium_lrs": "Premium SSD (LRS)", "ultrassd_lrs": "Ultra Disk",
              "premiumv2_lrs": "Premium SSD v2", "standardssd_zrs": "Standard SSD (ZRS)", "premium_zrs": "Premium SSD (ZRS)"}

# The words of each family (what changes, what is read again, what could go wrong, and whether it can be undone) are the family's own, in cases/families/words.py, which holds no way to
# reach Azure: the families feed this brief, so that a page, a letter and a card show a new family without a line of its own here. Who acts is the same for every family, and a page says it
# once, in these words: no button and no line of an approval repeats that the person signs in to Azure (the person does, when Azure asks).
WHO_ACTS = ("You do, with your own permissions: when you approve, Azure checks your rights and the change is made right then. "
            "Meternaut holds no right of its own to change anything.")
TWO_PEOPLE = "Two people approve this: one confirms the request, then another approves it."
# What a request that needs two people says, by where it stands for the person who reads it (cases/twopeople.py). A letter has no reader that it knows, so it says TWO_PEOPLE only.
SECOND_WORDS = {
    "first": "Two people approve this. One of them confirms the request, which changes nothing, and then another approves it. Nobody has confirmed it yet.",
    "second": "Two people approve this. {name} confirmed the request {when}. You approve it now.",
    "mine": "Two people approve this. You confirmed the request {when}. A second person approves it.",
    "stale": "Two people approve this. The request changed after {name} confirmed it {when}, so that confirmation does not count any more. It has to be confirmed again.",
    "alone": ("Two people approve this, and fewer than two people are listed as approvers of it, so nobody can approve it. You can decline it, say that it is not yours, "
              "or ask the people who are responsible for Meternaut to add a second approver."),
}
ADVICE_CHANGE = "Nothing changes in Azure. Your answer is recorded with your name."
ADVICE_WHO = "Meternaut may not change this resource. If you act on it, you do it in Azure with your own rights."
ADVICE_UNDO = "Nothing is changed, so there is nothing to undo."
NO_CHANGE = "No request is open for this finding. Nothing changes in Azure."
# What a plan says while its change waits in the queue: Azure asked the approver for an extra sign-in check, and the check is not completed yet.
WAITING_FOR_THE_CHECK = "Azure asked for an extra sign-in check before it would make the change. The change waits until the check is completed. Nothing was changed yet."
# What a plan says while Azure carries out a change that it accepted and has not finished (a machine takes minutes to stop or resize): the runner records its own words in the action.
RUNNING_IN_AZURE = "Azure accepted the change and is still making it. Meternaut reads the resource again in a few minutes."
# What a request says when it was approved and nothing had to be changed: when Meternaut looked, the resource was in the state that the plan wants (somebody else got there first) or was
# gone already. No write was made, so the saving is not claimed for this approval.
NOTHING_CHANGED = "Nothing was changed"
NOTHING_CHANGED_SAVING = "Nothing was changed, so no saving is claimed for this approval."
# What a person is told while a switch holds the answer that approves: all of them hold a change, and only the full stop holds advice (nothing changes in Azure for it).
PAUSED_CHANGES = "Changes are paused here. Nothing has changed, and your OK cannot be recorded now."
PAUSED_ADVICE = "Meternaut is paused here. Nothing has changed, and your answer cannot be recorded now."
# What a request says when a look at the resource (cases/precheck.py) shows that the checks which the runner makes right before the change would refuse it: the title of the box, what happens
# next, and the answers that are left. The reason is the check's own, in plain words, and then "Nothing was changed.". When the look could not be made, one line says so.
NOT_NOW_TITLE = "Meternaut will not change this {noun} now"
NOT_NOW_NEXT = ("What happens next: Meternaut looks again every time this page opens, and offers Approve again when the change can be made. "
                "Until then you can decline this request, decide later, or ask or tell.")
COULD_NOT_LOOK = "Meternaut could not look at the {noun} just now, so it cannot say whether the change can be made."
LOOKS_AGAIN = "It looks again right before it acts, and it changes nothing if a check fails."
# What a request that was refused before and is open again says at the top, when the look made now cannot say whether the reason still holds (the reason itself is the record's).
NOT_MADE_BEFORE = "Meternaut did not make this change last time"
# The data that a workspace takes in and nothing reads: cases/unread.py works it out and keeps it in the facts of the case under this key, as numbers, flags and the names of kinds of data. This
# module reads that typed digest and nothing of how it is made. The words are code's; the names of tables are text of the estate and are cut and escaped like every other.
UNREAD = "unread"
MAX_UNREAD_LINES = 6
READS_NOTHING = "0 rules, 0 saved searches and 0 workbooks"
UNREAD_MISSING = {
    "volume": "How much data this workspace takes in was not read, so there is no way to say how much of it nothing reads.",
    "readers": "Not everything that reads this workspace's data (its rules, saved searches, workbooks and analytics rules) could be read, so Meternaut cannot say which data nothing reads.",
}
# What a person could do about data that nothing reads, in one line, for a letter that has no room for the section of the page. The section ends with OPTIONS_END; a letter adds it where
# no other line says that the answer changes nothing in Azure.
OPTIONS_END = "Nothing changes in Azure when you answer."
OPTIONS_SHORT = "Options: stop sending it, filter it before it is stored, or use a cheaper plan."


@dataclass(frozen=True)
class Fact:
    """One row of evidence: what was found, the value with its unit, and where it was read."""

    label: str
    value: str
    source: str


@dataclass(frozen=True)
class Saving:
    """What it is worth, in US dollars a month as the data holds it. `level` is Verified, Expected or Scenario; `basis` says what the figure is computed from.
    Without a figure `monthly` is None and `why_none` says why in one phrase; `specific` is set when that phrase is the finding's own reason (a family's, a workspace whose volume was
    not read, a change that was not needed) and not only that no saving was worked out from the cost that was read."""

    monthly: float | None
    level: str
    basis: str
    waiting_per_day: float | None
    why_none: str
    specific: bool = False


@dataclass(frozen=True)
class Confidence:
    level: str  # High, Medium or Low
    because: str


@dataclass(frozen=True)
class Undo:
    reversible: bool
    how: str


@dataclass(frozen=True)
class Risk:
    level: str  # low, medium or high
    text: str


@dataclass(frozen=True)
class OwnerLine:
    known: bool
    text: str


@dataclass(frozen=True)
class Where:
    subscription: str  # the first eight characters of the id
    group: str
    kind: str  # the resource in words ("Managed disk"), or its type as Azure names it
    name: str
    portal_url: str  # the address in the Azure portal, only for an id of one resource; empty otherwise
    noun: str = "resource"  # the kind as a noun of a sentence ("disk"), "resource" when the kind has no words
    subscription_name: str = ""  # the display name of the subscription, when it was read: a person reads a name before an id


@dataclass(frozen=True)
class Outcome:
    """What became of a request that is no longer open, in plain lines without a time; `at` is the time of the answer (or of the expiry)."""

    state: str  # expired, declined, withdrawn, answered, approved, running, done, unchanged (approved, and nothing had to be changed), verified, failed or empty while the request is open
    title: str
    lines: tuple[str, ...]
    result: str  # one short phrase for a list
    by: str
    at: str


@dataclass(frozen=True)
class DataLine:
    """One kind of data that nothing reads, as a typed line: what it is, how much of it came in, its share of what is billed, and what reads it. `writers` names the kinds of resource of its
    largest writers on the last closed day when the tools showed them ("" otherwise): the options use it and the line does not."""

    kind: str
    gb: str
    percent: str
    reads: str
    writers: str = ""


@dataclass(frozen=True)
class Unread:
    """The data that a workspace takes in and nothing reads, for the evidence of a request: the method in one plain sentence, the volume that it rests on ("That is 88 GB of the 118 GB that
    it took in over 30 days."), the days, up to six typed lines (the largest first), how many more kinds there are, and one sentence about what was not counted ("" when everything was).
    `caveat` says the same in a few words, for a letter and a card, which have no room for the sentence (for example "Not counted: the queries people run.")."""

    sentence: str
    volume: str
    days: str
    lines: tuple[DataLine, ...]
    more: int
    note: str
    caveat: str = ""


@dataclass(frozen=True)
class Option:
    """One thing that a person could do about it, in words that code wrote, and what is lost or at risk if they do it."""

    what: str
    risk: str


@dataclass(frozen=True)
class Gateways:
    """What a finding about point-to-site gateways says in plain words of code (cases/gateways.py works the digest out): what these gateways are, what was found in one or two sentences, up to two
    rows of evidence (the scale units, and the most connections at one time), how many scale units would be taken away in all, how many gateways were counted of how many there are, and what was
    not counted, in a sentence for the page and in a few words for a letter and a card."""

    what: str
    sentence: str
    rows: tuple["Fact", ...]
    fewer: int
    counted: int
    gateways: int
    note: str = ""
    caveat: str = ""


@dataclass(frozen=True)
class Group:
    """What a case stands for when its finding covers many resources and a person is asked about the finding, not about each resource: how many, what they cost together (None when no cost
    line was read), the type that they share ("other" when they differ), in how many resource groups they are (0 when that is not known), the names of the first few that follow the
    resource that the case belongs to, and how many more of the finding the limit of cases in one run left out."""

    count: int
    cost: float | None
    kind: str
    groups: int
    names: tuple[str, ...]
    capped: int = 0


@dataclass(frozen=True)
class Second:
    """Where a request that needs two people stands for the person who reads it: `stage` is a stage of twopeople.standing (alone, first, second, mine or stale), `line` is the plain
    sentence for it, `by` the name of the person who confirmed the plan ("" when nobody did)."""

    stage: str
    line: str
    by: str = ""


@dataclass(frozen=True)
class Impact:
    """What removing the resource would do, from the digest of its check (cases/impact.py), in the words that code wrote. `verdict` is empty when the impact was not analysed, and `line` then
    says so; otherwise `line` is the verdict with its first reason, for a card and a letter."""

    verdict: str  # safe, check, keep, or empty
    label: str
    reasons: tuple[str, ...]
    rows: tuple["Fact", ...]
    removal: tuple[str, ...]
    undo: str
    unchecked: str
    line: str


@dataclass(frozen=True)
class Brief:
    case_id: str
    plan_id: str
    plan_code: str
    kind: str  # change (a change in Azure that a person may approve), advice (an advise plan: nothing changes) or info (no plan)
    family: str
    state: str  # the state of the plan as it is now: open, expired, declined, approved, consumed, failed, withdrawn; none without a plan
    headline: str
    saving: Saving
    confidence: Confidence
    facts: tuple[Fact, ...]
    reasoning: str
    doubt: str
    change: str
    who_acts: str
    rechecked: str
    undo: Undo
    risk: Risk
    owner: OwnerLine
    where: Where
    answers: tuple[str, ...]  # the answers that exist for this person right now, in the order of the page
    found_at: str
    age_days: int | None
    expires_at: str
    models: tuple[str, ...]
    outcome: Outcome
    two_people: bool
    # The one line about how past requests like this were answered ("Past cases like this: 3 of 4 approved; ..."), and, only when what the identity cannot see changes what can be said,
    # one sentence about that. Both are written by code from the case's own record of them (CaseRecord.learned); empty when the case has none.
    past: str = ""
    access: str = ""
    # The data that a workspace takes in and nothing reads, and what a person could do about it (both written by code from the typed digest in the facts of the case; None and () for every
    # other finding). And, for a case that stands for many resources, the group (also from the facts of the case; None for every other).
    unread: Unread | None = None
    options: tuple[Option, ...] = ()
    group: Group | None = None
    # The point-to-site gateways whose scale units nobody uses, for a finding about them (None for every other).
    gateways: Gateways | None = None
    # What the finding costs in 30 days, from the cost lines (everything that it stands for when it is a group); None when no cost line was read. A request that has no saving shows this cost as
    # the most that a change could save. The letter and the card read it from here, because the card has no case at hand: it is the number that the pages read with cost_of (a test holds the two together).
    cost: float | None = None
    # A switch holds the answer that approves (and the confirmation): the page and the card say so in words of their own instead of showing that answer.
    held: bool = False
    # A change that needs two people: where it stands for the reader (None for every other request).
    second: Second | None = None
    # What a look at the resource, made when the page was built, said about a change that waits for an OK (cases/precheck.py): None when no look was made (a letter and a card make none). When it
    # says `refused`, the answers that approve are not in `answers`, and the page says why in plain words.
    ready: Readiness | None = None
    # Why the last try of an open change was refused before anything was written, in the words that the record keeps (the action is `withdrawn`); empty for every other request. The page shows it at
    # the top when the look made now cannot say more: a person who opens a request that was refused sees at once that it was, and why.
    refused_before: str = ""
    # What the cost says (cases/costs.py): how it was read (lines, none, failed, currency, or "" when it was not read), what the finding is about (resource, group or subscription), what a
    # cost of a whole subscription or resource group is made of ("Made of: ..."), an estimate at list price for a managed disk that Azure has no cost line for (never a cost: it is not in `cost`),
    # and the address of Cost analysis in the Azure portal for the scope of the finding (only the page shows it: a letter and a card have one link, the page of the request).
    cost_state: str = ""
    scope: str = "resource"
    made_of: str = ""
    estimate: estimates.Estimate | None = None
    cost_url: str = ""
    cost_scope: str = ""  # the scope of that address in words ("resource group rg-demo", "subscription contoso-dev"), for the line that holds the link
    # What to check before acting on advice about a resource that others share, or that may not be used any more (CHECK_FIRST); empty for every other request.
    check_first: tuple[str, ...] = ()
    # What removing the resource would do (cases/impact.py): for a finding of the investigation, its check, or the line that says that none was made; None for every other request.
    impact: Impact | None = None


# -- small helpers ------------------------------------------------------------------------------------------------------------------------------

HIDDEN = ("Cc", "Cf", "Cs", "Co", "Cn")  # control, format (direction and zero-width), surrogate, private-use and unassigned characters
BRACKETS = str.maketrans("[]", "()")
AUTOLINK = re.compile(r"(?i)\b([a-z][a-z0-9+.-]*):(?=//)")


def visible(value: object) -> str:
    """The text of a value without the characters that hide it or change its order on a screen: control characters (a line break and a tab stay), format characters such as
    the direction overrides and the zero-width ones, and characters that are unassigned or private. The Unicode line and paragraph separators become the line break that they
    are. The one rule that every page, letter and card applies to text that did not come from code."""
    raw = "" if value is None else str(value)
    return "".join("\n" if unicodedata.category(ch) in ("Zl", "Zp") else ch for ch in raw if ch in "\n\t" or unicodedata.category(ch) not in HIDDEN)


def plain(value: object, limit: int = MAX_NAME) -> str:
    """Text from the estate, from a person or from a model as one safe line, for every render (a page, a letter, a card). It has no hidden or direction character, no line
    break (so it cannot start a header, a list or a paragraph of its own), at most `limit` characters, and no link: the square brackets of a Markdown link become round ones,
    and the scheme of an address is split from its slashes, so that no client turns the text into a link that Meternaut did not make. A link is made from an id, never from text."""
    kept = " ".join(visible(" ".join(("" if value is None else str(value)).split())).split()).translate(BRACKETS)
    kept = AUTOLINK.sub(r"\1: ", kept)
    return kept if len(kept) <= limit else kept[: limit - 3].rstrip() + "..."


text_of = plain  # the name that the first modules of the decision brief use


def parse_time(value: object) -> dt.datetime | None:
    try:
        return dt.datetime.strptime(str(value), TIME_FORMAT).replace(tzinfo=dt.timezone.utc)
    except ValueError:
        return None


def _utc(moment: dt.datetime) -> dt.datetime:
    return moment.replace(tzinfo=dt.timezone.utc) if moment.tzinfo is None else moment.astimezone(dt.timezone.utc)


def _figure(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        return None
    return float(value)


def number_text(value: object) -> str:
    """A number for a person: thousands separated, at most two decimals, no trailing zeros. Empty for what is not a finite number."""
    number = _figure(value)
    if number is None:
        return ""
    if number.is_integer():
        return f"{int(number):,}"
    return f"{number:,.2f}".rstrip("0").rstrip(".")


def usd_text(value: object) -> str:
    """Money as the guide writes it: a dollar sign, thousands separated, two decimals ($1,682.40). The page says once that money is in US dollars. Empty for what is not a finite number."""
    number = _figure(value)
    if number is None:
        return ""
    return f"-${abs(number):,.2f}" if number < 0 else f"${number:,.2f}"


def _bytes(value: float) -> str:
    size, unit = abs(value), "bytes"
    for step in ("KB", "MB", "GB", "TB"):
        if size < 1024:
            break
        size, unit = size / 1024, step
    sign = "-" if value < 0 else ""
    return f"{sign}{number_text(round(size, 2))} {unit}"


def quantity(total: object, unit: object) -> str:
    """A total of a measurement with its unit in words: bytes as KB to TB, a percentage, seconds, a count as the bare number. A unit that has no words here is kept as the
    tools gave it. Empty when the total is not a number."""
    number = _figure(total)
    if number is None:
        return ""
    word = str(unit or "").strip()
    key = word.lower()
    if key in ("", "count", "unspecified"):
        return number_text(number)
    if key == "bytes":
        return _bytes(number)
    if key == "percent":
        return f"{number_text(number)}%"
    if key == "seconds":
        return f"{number_text(number)} seconds"
    if key == "milliseconds":
        return f"{number_text(number)} ms"
    if key == "countpersecond":
        return f"{number_text(number)} per second"
    if key == "bytespersecond":
        return f"{_bytes(number)} per second"
    return f"{number_text(number)} {text_of(word, 24)}"


def days_text(days: object) -> str:
    if isinstance(days, int) and not isinstance(days, bool) and days > 0:
        return "1 day" if days == 1 else f"{days} days"
    return ""


GUID = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")


def who_text(value: object, limit: int = 80) -> str:
    """Who made or changed a resource, as the Activity Log names the caller. A person is a sign-in name. An application, a managed identity or a service principal is only an
    id (a GUID), which names nobody: it is said to be an identity, with its id for a lookup in Azure."""
    text = text_of(value, limit)
    return f"an application or service identity (id {text.lower()})" if GUID.fullmatch(text) else text


def kind_words(resource_type: str) -> tuple[str, str]:
    """What a resource is: the label of its kind ("Managed disk") and the noun of a sentence ("disk"). A type that has no words is shown as Azure names it, and a sentence
    says "resource"."""
    found = TYPE_WORDS.get((resource_type or "").lower())
    return found if found else (text_of(resource_type, 80) or "Resource", "resource")


def ago_text(now: dt.datetime, found_at: str) -> tuple[int | None, str]:
    """How long ago something was found, as days and as a sentence part: today, yesterday, N days ago, N weeks ago, N months ago."""
    moment = parse_time(found_at)
    if moment is None:
        return None, ""
    days = max(0, (_utc(now) - moment).days)
    if days == 0:
        return days, "today"
    if days == 1:
        return days, "yesterday"
    if days < 14:
        return days, f"{days} days ago"
    if days < 60:
        return days, f"{days // 7} weeks ago"
    return days, f"{days // 30} months ago"


def portal_url(resource_id: str) -> str:
    """The address of the resource in the Azure portal, for the id of one resource and for nothing else: an id of the estate is text, and this is a link."""
    if isinstance(resource_id, str) and re.fullmatch(r"/subscriptions/[0-9A-Fa-f-]{36}/resourceGroups/[A-Za-z0-9._()-]{1,90}/providers/[A-Za-z0-9.]{1,80}(?:/[A-Za-z0-9._()~-]{1,100}){2,16}", resource_id):
        return f"https://portal.azure.com/#resource{resource_id}"
    return ""


def models_of(case: CaseRecord | None) -> tuple[str, ...]:
    values = case.models.values() if case is not None and isinstance(case.models, dict) else ()
    return tuple(dict.fromkeys(text_of(v, 60) for v in values if isinstance(v, str) and v.strip()))


def written_by(models: Sequence[str]) -> str:
    """The first sentence of the footer line: that an AI wrote what is on the page or in the letter, and which models."""
    names = ", ".join(models)
    return f"Written by an AI (models: {names}); a person approves every change." if names else "Written by an AI; a person approves every change."


def contact_text(name: object, address: object = "") -> str:
    """A person to talk to, as plain text: the name and, when there is one, the address in brackets. Never a link."""
    who, mail = plain(name, 60), plain(address, 80)
    return f"{who} ({mail})" if who and mail else (who or mail)


def footer_line(models: Sequence[str], why: str, people: Sequence[str] = ()) -> str:
    """The one line at the foot of a letter and of a card: that an AI wrote it (and which models), why this person got it, and who is responsible for Meternaut, as plain text with the address and
    no link: the words of "About this page" on a page. Without a person to name the line leaves the last sentence out."""
    responsible = f" Responsible for Meternaut: {', '.join(people)}." if people else ""
    return f"{written_by(models)} {why}{responsible}"


# -- the parts ------------------------------------------------------------------------------------------------------------------------------

def _subject(case: CaseRecord | None, plan: PlanRecord | None) -> tuple[str, str, str, str, str]:
    """The name, the resource group, the subscription, the id and the type of the resource, from the plan or else from the case."""
    if plan is not None:
        rtype = case.resource_type if case is not None else ""
        return plan.resource_name, plan.resource_group, plan.subscription_id, plan.resource_id, rtype or type_of(plan.family, plan.preconditions)  # a plan of a change knows what it changes
    if case is not None:
        return case.resource_name, case.resource_group, case.subscription_id, case.resource_id, case.resource_type
    return "", "", "", "", ""


def advice_of(case: CaseRecord | None) -> tuple[str, str] | None:
    """Advisor's own words for a finding that is an Advisor recommendation, as (what it found, what to do about it): each one safe line. The solution stands for the problem when Advisor gave
    only one. None when the case holds none (cases/detectors.py advisor_words makes them)."""
    found = case.advice if case is not None and isinstance(case.advice, dict) else {}
    problem = text_of(found.get("problem"), 160) if isinstance(found.get("problem"), str) else ""
    if not problem:
        return None
    solution = text_of(found.get("solution"), MAX_REASON) if isinstance(found.get("solution"), str) else ""
    return problem, solution or problem


def _id_like(label: str) -> bool:
    """Whether a name is no name: it is empty, an id (a GUID) or the path of an id. A request that has only that to call its subject says nothing."""
    return not label or bool(GUID.fullmatch(label)) or label.startswith("/")


def says_nothing(case: CaseRecord | None) -> bool:
    """Whether a finding cannot say what to look at, so that no request is made for it: it has no words of Advisor and no group, no analysis of data that nothing reads and no analysis of
    gateways to say it with, and it is about a whole subscription or resource group (a subscription costs what its resources cost: what to look at in it is not said by its name), or it is about
    a thing of a kind that has no words here whose name is no name at all (an id). A finding that stays in the History with the reason "held back: nothing to say"."""
    if case is None or advice_of(case) is not None or group_of(case) is not None or unread_of(case) is not None or gateways_of(case) is not None:
        return False
    if cost_words.is_container(case.resource_id):
        return True
    return kind_words(case.resource_type)[1] == "resource" and _id_like(text_of(case.resource_name, MAX_NAME))


def held_back(case: CaseRecord | None) -> str:
    """Why a Watch held a finding back (one of HELD_REASONS: an automation manages the resource, the impact of a deletion was not checked, or the check shows that something uses the resource),
    and "" when it did not: no request is made for such a finding, and one that was made before and that nobody answered is taken back."""
    held = case.learned.get("held") if case is not None and isinstance(case.learned, dict) else None
    return held if held in HELD_REASONS else ""


def automated(case: CaseRecord | None) -> bool:
    """Whether a Watch held a finding back because an automation manages its resource (investigate.py)."""
    return held_back(case) == "automation"


def _advisor_headline(problem: str, scope: str, name: str, group: str, subscription_name: str, subscription: str) -> str:
    """The title of an Advisor recommendation: Advisor's own sentence, and then what it is about: the subscription by its name (the start of its id when the name was not read), the resource
    group, or the resource and its group."""
    if scope == "subscription":
        label = text_of(subscription_name, 80) or text_of(subscription, 40)[:8]
        return f"{problem}: subscription {label}" if label else problem
    if scope == "group":
        label = text_of(group or name, 90)
        return f"{problem}: resource group {label}" if label else problem
    label = text_of(name, MAX_NAME)
    place = f" in group {text_of(group, 90)}" if group else ""
    return f"{problem}: {label}{place}" if label and not _id_like(label) else f"{problem}{place}"


def shared(rtype: object) -> bool:
    """Whether a type of resource is one that others share (SHARED)."""
    return isinstance(rtype, str) and rtype.strip().lower().startswith(SHARED)


def measured_zero(facts: object) -> bool:
    """Whether the facts of a finding hold a measurement that shows that nothing used the resource: a total of nil over a window that had a value on at least MEASURED_DAYS days. No data, a read
    that failed and a few days are not one."""
    found = facts if isinstance(facts, Mapping) else {}
    totals, days = found.get("metrics"), found.get("metricDaysWithData")
    if not isinstance(totals, dict) or not isinstance(days, dict):
        return False
    return any(_figure(total) == 0 and isinstance(days.get(name), int) and not isinstance(days.get(name), bool) and days[name] >= MEASURED_DAYS for name, total in totals.items())


def _asked_delete(case: CaseRecord) -> bool:
    facts = case.facts if isinstance(case.facts, dict) else {}
    return case.recommendation == "delete" or facts.get("asked") == "delete"


def _idle(case: CaseRecord) -> bool:
    """Whether a finding of the investigation says that a resource is not used, or asked to delete it."""
    facts = case.facts if isinstance(case.facts, dict) else {}
    return case.detector == "investigation" and (_asked_delete(case) or facts.get("basis") in USE_BASES)


def proposal_of(case: CaseRecord | None) -> str | None:
    """What a case asks for. A finding of the investigation asks to delete a resource only on a measured zero, and never for a resource that others share (investigate.py makes the case so; this
    holds a case that an earlier version made to the same). Any other case asks what it recorded."""
    if case is not None and case.detector == "investigation" and case.recommendation == "delete" and (shared(case.resource_type) or not measured_zero(case.facts)):
        return "investigate"
    return case.recommendation if case is not None else None


def still_used(case: CaseRecord | None) -> bool:
    """Whether a finding of the investigation is the question whether one resource is still used: it asks for a look, it asked to delete the resource or says that nothing uses it, and either the
    resource is one that others share or no measured zero lets it ask for more. A finding that has an analysis of its own (data that nothing reads, gateways) is not this question."""
    return (case is not None and _idle(case) and proposal_of(case) == "investigate" and group_of(case) is None and unread_of(case) is None and gateways_of(case) is None
            and (shared(case.resource_type) or _asked_delete(case) or not measured_zero(case.facts)))


def _texts(values: object, limit: int = 240) -> tuple[str, ...]:
    return tuple(text for text in (plain(item, limit) for item in (values if isinstance(values, list) else []) if isinstance(item, str)) if text)


def impact_of(case: CaseRecord | None) -> Impact | None:
    """What removing the resource of a finding of the investigation would do: its check (cases/impact.py) when one was made, and otherwise the line that says that none was. Every other case
    has none (the waste that Meternaut plants has its own words). The digest is code's own, and it is checked again here: what is not a word of the verdict, or not a text, is left out."""
    if case is None or case.detector != "investigation":
        return None
    found = case.facts.get(IMPACT) if isinstance(case.facts, dict) else None
    if not isinstance(found, dict) or found.get("verdict") not in IMPACT_VERDICTS:
        return Impact("", "", (), (), (), "", "", NOT_ANALYSED)
    rows = tuple(Fact(plain(row[0], 80), plain(row[1], 240), plain(row[2], 120)) for row in found.get("rows") or [] if isinstance(row, list) and len(row) == 3 and all(isinstance(x, str) for x in row))
    label, reasons, cannot = IMPACT_VERDICTS[found["verdict"]], _texts(found.get("reasons"))[:6], _texts(found.get("unchecked"), 120)
    return Impact(found["verdict"], label, reasons, rows, _texts(found.get("removal"))[:3], plain(found.get("undo"), 300), f"Not checked: {'; '.join(cannot)}." if cannot else "",
                  f"Impact: {label}." + (f" {reasons[0]}" if reasons else ""))


def acting_risk(case: CaseRecord | None) -> Risk:
    """The risk of doing what a request suggests, which is not the risk of answering it (that changes nothing in Azure): worked out by code from the kind of resource and the evidence level. Never
    low, because a change is at least a medium risk, unless the check of its impact finds that nothing that can be read depends on it; high for a resource that others share when nothing measured
    shows that nothing uses it, and for one that the check finds in use."""
    if case is None:
        return Risk("medium", ACTING + CHANGE_RISK)
    found = impact_of(case)
    if found is not None and found.verdict in ("safe", "keep"):
        return Risk("low", ACTING + SAFE_RISK) if found.verdict == "safe" else Risk("high", ACTING + KEEP_RISK)
    group = group_of(case)
    others = shared(group.kind if group is not None else case.resource_type)
    proven = group is None and measured_zero(case.facts)
    analysed = unread_of(case) is not None or gateways_of(case) is not None  # a finding with an analysis of its own is measured: it is not the question whether anything uses the resource
    parts = ([UNPROVEN] if _idle(case) and not proven and not analysed else []) + ([SHARED_RISK] if others else [])
    return Risk("high" if others and not proven and not analysed else "medium", ACTING + " ".join(parts or [RARE_USE if proven else CHANGE_RISK]))


def check_first(case: CaseRecord | None) -> tuple[str, ...]:
    """What to check before acting on a finding that asks whether a resource is still used (CHECK_FIRST), when its impact was not analysed: an analysis names the specific things itself."""
    found = impact_of(case)
    return CHECK_FIRST if still_used(case) and (found is None or not found.verdict) else ()


def headline_of(family: str, name: str, group: str, rtype: str, recommendation: str | None, plan_title: str = "", plan: PlanRecord | None = None, together: Group | None = None,
                case: CaseRecord | None = None) -> str:
    """The request in one line: a verb, the thing and the place. Written by code from the kind of change, never by a model. `together` is the group that a case stands for (group_of), when it
    stands for many resources: the line then says how many, of what kind and in how many groups, and names the first. A case that is an Advisor recommendation (`case`) says it in Advisor's
    own words (advice_of), then what it is about."""
    place = f" in group {text_of(group, 90)}" if group else ""
    label = text_of(name, MAX_NAME) or "this resource"
    said = words_of(family, plan, rtype, text_of(name, MAX_NAME), text_of(group, 90))
    if said is not None:
        return said.headline
    if shown(family) is None and family and family != ADVISE and plan_title:
        return text_of(plan_title, 160)
    if together is not None:
        return group_headline(together, name, recommendation)
    words = advice_of(case)
    if words is not None and case is not None:
        return _advisor_headline(words[0], cost_words.scope_of(case.resource_id).kind or "resource", name, group, case.subscription_name, case.subscription_id)
    noun = kind_words(rtype)[1]
    if still_used(case):
        return f"Check whether the {noun} {label}{place} is still used"
    verb = VERBS.get((proposal_of(case) if case is not None else recommendation) or "", "Look at")
    return f"{verb} the {noun} {label}{place}"


def plan_headline(plan: PlanRecord) -> str:
    """The headline of a request from the plan alone (a list of decided requests needs no case): the stored title of an advise plan, the words of the family otherwise."""
    if plan.family == ADVISE:
        return text_of(plan.title, 160) or headline_of(ADVISE, plan.resource_name, plan.resource_group, "", None)
    return headline_of(plan.family, plan.resource_name, plan.resource_group, type_of(plan.family, plan.preconditions), None, plan.title, plan)


def _agreed(case: CaseRecord | None, plan: PlanRecord | None) -> bool | None:
    """Whether the second AI agreed, as far as the records show: True, False, or None when the status moved on and no longer says."""
    if plan is not None and shown(plan.family) is not None:
        return True
    if case is None:
        return None
    then = (plan.preconditions.get("caseStatus") if plan is not None and isinstance(plan.preconditions, dict) else None) or case.status
    if then in AGREED:
        return True
    if then in ("needs_human", "dropped", "error"):
        return False
    return None


def _code_note(text: str) -> bool:
    return any(text.startswith(prefix) for prefix in CODE_NOTES)


def _skeptic_step(case: CaseRecord) -> dict | None:
    for step in case.steps if isinstance(case.steps, (list, tuple)) else ():
        if isinstance(step, dict) and step.get("step") == "skeptic":
            return step
    return None


def _metrics(case: CaseRecord) -> dict:
    facts = case.facts if isinstance(case.facts, dict) else {}
    metrics = facts.get("metrics")
    return metrics if isinstance(metrics, dict) else {}


def past_line(digest: object) -> str:
    """The one line of a brief about how past requests like this were answered: "Past cases like this: 3 of 4 approved; savings came in at 92 percent of the estimate." The digest is what
    cases/learning.py keeps in `CaseRecord.learned["past"]`: n (the requests that a person answered), approved, `enough` (n is at least the smallest sample), ratio (what the cost lines
    showed as a share of what was predicted, when enough changes have both) and boomerangs. Without enough it says that there is no history yet; for a case that has no record of its
    past at all (it was found before there was one) there is no line."""
    if not isinstance(digest, dict):
        return ""
    answered, approved = digest.get("n"), digest.get("approved")
    whole = isinstance(answered, int) and isinstance(approved, int) and not isinstance(answered, bool) and not isinstance(approved, bool)
    if digest.get("enough") is not True or not whole or not 0 <= approved <= answered:
        return "Past cases like this: no history yet."
    text = f"Past cases like this: {approved} of {answered} approved"
    ratio = _figure(digest.get("ratio"))
    if ratio is not None and ratio >= 0:
        text += f"; savings came in at {round(ratio * 100)} percent of the estimate"
    boomerangs = digest.get("boomerangs")
    if isinstance(boomerangs, int) and not isinstance(boomerangs, bool) and boomerangs > 0:
        text += f"; {boomerangs} {'was' if boomerangs == 1 else 'were'} undone within weeks"
    return text + "."


def _held_by_history(case: CaseRecord | None) -> bool:
    """Whether what past requests like this showed held the proposal of this case back for a person (cases/learning.py): both AIs agreed, and a person has to decide."""
    return case is not None and isinstance(case.learned, dict) and case.learned.get("held") == "history"


def confidence_of(case: CaseRecord | None, plan: PlanRecord | None = None) -> Confidence:
    """How sure it is, by code, from the second AI's verdict, the checks that fired and the share of the numbers that the AI cited and that code re-checked.

    High: both AIs agree, no check fired, every cited number was re-checked, and the first AI was sure. Low: a check held it back, the second AI did not agree (or gave no
    verdict), no number backs a finding of the investigation, the first AI was not sure enough, or past requests like this were rarely approved. Medium: the rest."""
    if case is None:
        return Confidence("Low", "No record of the review is stored.")
    held = _held_by_history(case)
    agreed = True if held else _agreed(case, plan)
    guards = [g for g in case.guards if isinstance(g, str)]
    investigated = case.detector == "investigation"
    metrics = _metrics(case)
    facts = case.facts if isinstance(case.facts, dict) else {}
    cited = facts.get("citedMetrics")
    cited = cited if isinstance(cited, int) and not isinstance(cited, bool) and cited >= len(metrics) else None
    step = _skeptic_step(case)
    asked = bool(case.models.get("skeptic")) if isinstance(case.models, dict) else step is not None
    first = _figure(case.confidence)
    pieces: list[str] = []
    own = [o for o in case.objections if isinstance(o, str) and o.strip() and not _code_note(o)]
    if agreed is True:
        pieces.append("Both AI reviewers agree")
    elif agreed is None:
        pieces.append("The second AI's verdict is no longer recorded")
    elif step is not None and step.get("ok") is False:
        pieces.append("The second AI gave no verdict")
    elif not asked:
        pieces.append("Only one AI reviewed it")
    elif own:
        pieces.append("The second AI raised an objection")
    else:
        pieces.append("The AI reviewers did not settle it")
    if guards:
        pieces.append("a check by code held it back (" + "; ".join(GUARD_WORDS.get(g, text_of(g, 40)).rstrip(".").lower() for g in guards[:2]) + ")")
    if investigated:
        if not metrics:
            pieces.append("no number backs it")
        elif cited:
            pieces.append(f"code checked {len(metrics)} of {cited} numbers again")
        else:
            pieces.append(f"code checked {len(metrics)} number{'' if len(metrics) == 1 else 's'} again")
    else:
        pieces.append("code read the facts itself")
    if first is not None and first < SURE_ENOUGH:
        pieces.append("the first AI was not sure enough")
    if held:
        pieces.append("past requests like this were rarely approved, so a person has to decide")
    low = bool(guards) or agreed is False or (investigated and not metrics) or (first is not None and first < SURE_ENOUGH) or held
    all_checked = not investigated or (bool(metrics) and (cited is None or cited == len(metrics)))
    if low:
        level = "Low"
    elif agreed is True and all_checked and (first is None or first >= CONFIDENT):
        level = "High"
    else:
        level = "Medium"
    sentence = "; ".join(pieces) + "."
    return Confidence(level, sentence[0].upper() + sentence[1:])


def reasoning_of(case: CaseRecord | None) -> str:
    if case is None or case.status == "error":
        return ""
    return text_of(case.summary, MAX_REASON)


def doubt_of(case: CaseRecord | None, plan: PlanRecord | None = None) -> str:
    """The second AI's strongest objection: the first of its own, never a note that code wrote. When there is none, what the second AI did instead."""
    if case is None or case.status == "error":
        return ""
    own = [o for o in case.objections if isinstance(o, str) and o.strip() and not _code_note(o)]
    if own:
        return text_of(own[0], MAX_REASON)
    step = _skeptic_step(case)
    asked = bool(case.models.get("skeptic")) if isinstance(case.models, dict) else step is not None
    if not asked:
        return "The second AI was not asked."
    if step is not None and step.get("ok") is False:
        return "The second AI gave no verdict on this finding."
    agreed = _agreed(case, plan)
    if agreed is True:
        return "The second AI raised no objection."
    return "The second AI raised no objection in words."


# -- a case that stands for many resources ------------------------------------------------------------------------------------------------------------

def _plural(noun: str) -> str:
    """The plural of the noun of a kind of resource ("private endpoint", "public IP address", "Redis cache")."""
    if noun.endswith(("s", "x", "z", "ch", "sh")):
        return noun + "es"
    if len(noun) > 1 and noun.endswith("y") and noun[-2] not in "aeiou":
        return noun[:-1] + "ies"
    return noun + "s"


def group_of(case: CaseRecord | None) -> Group | None:
    """The group that a case stands for, as the facts of the case keep it (cases/investigate.py), or None for a case that stands for one resource or whose digest is not as it should be. Every
    value is checked again here: a digest that is not as it should be shows less and never something else."""
    facts = case.facts if case is not None and isinstance(case.facts, dict) else {}
    found = facts.get(GROUP_FACT)
    if not isinstance(found, dict):
        return None
    count, groups, kind, names = found.get("count"), found.get("groups"), found.get("type"), found.get("names")
    if isinstance(count, bool) or not isinstance(count, int) or not 2 <= count <= MAX_GROUP:
        return None
    cost = _figure(found.get("costUsd30d"))
    named = tuple(name for name in (text_of(item, MAX_EXAMPLE) for item in (names if isinstance(names, list) else [])[:MAX_GROUP_NAMES] if isinstance(item, str)) if name)
    capped = found.get("capped")
    return Group(count, cost if cost is not None and cost >= 0 else None, text_of(kind, 80) if isinstance(kind, str) and kind else "other",
                 groups if isinstance(groups, int) and not isinstance(groups, bool) and 1 <= groups <= count else 0, named,
                 capped if isinstance(capped, int) and not isinstance(capped, bool) and 0 < capped <= MAX_GROUP else 0)


def _things(group: Group, place: str) -> str:
    """"60 private endpoints in 14 groups": how many, of what kind, and, when it is known, in how many places (`place` is the word for one: group, resource group)."""
    where = f" in {number_text(group.groups)} {place}{'' if group.groups == 1 else 's'}" if group.groups else ""
    return f"{number_text(group.count)} {_plural(kind_words(group.kind)[1])}{where}"


def things(count: int, rtype: str, groups: int = 0, place: str = "resource group") -> str:
    """Resources of one kind and the places that they are in, for a page that shows findings of one kind as one row: "4 storage accounts in 3 resource groups"."""
    return _things(Group(count, None, rtype, groups, ()), place)


def group_headline(group: Group, name: str, recommendation: str | None) -> str:
    """The headline of a case that stands for many resources: "Look at 60 private endpoints in 14 groups, the first is pe-1". The first is the one that the case belongs to."""
    first = text_of(name, MAX_NAME)
    return f"{VERBS.get(recommendation or '', 'Look at')} {_things(group, 'group')}" + (f", the first is {first}" if first else "")


def _group_facts(group: Group, case: CaseRecord) -> list[Fact]:
    """The rows of a case that stands for many resources: how many there are (and how many more the limit of one run left out), what they cost together, and the names of the first few. They take
    the place of the cost row of one resource."""
    covers = _things(group, "resource group") + (f", and {number_text(group.capped)} more that the limit of one run left out" if group.capped else "")
    rows = [Fact("Covers", covers, RESOURCE_GRAPH)]
    cost = group.cost if group.cost is not None else _figure(case.cost_usd_30d)
    state = cost_state_of(case, group)
    if cost is not None and state == cost_words.NONE:
        rows.append(Fact("Together they cost", "Azure has no cost line for them yet", "Azure cost lines"))
    elif cost is not None:
        rows.append(Fact("Together they cost", f"{usd_text(cost)} in the last 30 days", "Azure cost lines"))
    examples = [name for name in [text_of(case.resource_name, MAX_EXAMPLE), *group.names][:MAX_EXAMPLES] if name]
    if examples:
        left = group.count - len(examples)
        rows.append(Fact("Examples", ", ".join(examples) + (f" and {number_text(left)} more" if left > 0 else ""), RESOURCE_GRAPH))
    return rows


# -- the data that a workspace takes in and nothing reads ----------------------------------------------------------------------------------------------

CUSTOM_TABLE = re.compile(r"t[0-9]{1,4}")  # what the tools call a table that the platform did not make, when they do not know its name: a handle that means something in one run only


def _digest(case: CaseRecord | None) -> dict | None:
    facts = case.facts if case is not None and isinstance(case.facts, dict) else {}
    found = facts.get(UNREAD)
    return found if isinstance(found, dict) else None


def _whole(value: object) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) and value > 0 else 0


def _percent(share: float) -> str:
    points = round(share * 100)
    return "under 1 percent" if points < 1 else f"{points} percent"


def _about(share: float) -> str:
    return _percent(share) if round(share * 100) < 1 else f"about {_percent(share)}"


def _gb_text(value: float) -> str:
    return "under 0.01 GB" if 0 < value < 0.005 else f"{number_text(round(value, 2))} GB"


def _series(words: Sequence[str]) -> str:
    return words[0] if len(words) == 1 else f"{', '.join(words[:-1])} and {words[-1]}"


def _kind_name(item: Mapping) -> str:
    """The name of a kind of data as a person reads it: the name of the table when it is known, the platform's own name, or "custom table t3" for a table of the customer that has none."""
    name, kind = plain(item.get("name"), 60), plain(item.get("kind"), 60)
    if name:
        return name
    return f"custom table {kind}" if CUSTOM_TABLE.fullmatch(kind) else kind


def _writers_text(item: Mapping) -> str:
    """The kinds of resource of the largest writers of a kind of data on the last closed day, in the words of the brief ("Key Vault, Storage account"); "" when the tools showed none."""
    types = item.get("writers") if isinstance(item.get("writers"), list) else []
    return ", ".join(dict.fromkeys(kind_words(text_of(kind, 80))[0] for kind in types[:3] if isinstance(kind, str) and text_of(kind, 80)))


def unread_of(case: CaseRecord | None) -> Unread | None:
    """The data that a workspace takes in and nothing reads, as the facts of its case keep it (cases/unread.py), or None for a case that has none or whose digest holds no kind. Every number
    is checked again here: a digest that is not as it should be shows less and never something else."""
    digest = _digest(case)
    if digest is None:
        return None
    share, gone, whole, days = _figure(digest.get("share")), _figure(digest.get("unreadGb")), _figure(digest.get("billableGb")), _whole(digest.get("days"))
    if share is None or not 0 < share <= 1 or gone is None or whole is None or not 0 < gone <= whole or not days:
        return None
    lines: list[DataLine] = []
    skipped = 0
    for item in digest.get("kinds") if isinstance(digest.get("kinds"), list) else []:
        if not isinstance(item, dict):
            continue
        volume, part, runs, kind = _figure(item.get("gb")), _figure(item.get("share")), item.get("runs"), _kind_name(item)
        counted = isinstance(runs, int) and not isinstance(runs, bool)
        if volume is None or volume < 0 or part is None or not 0 <= part <= 1 or not kind or (counted and runs != 0) or (runs is not None and not counted):
            continue  # a kind that something reads is not one that nothing reads
        if len(lines) == MAX_UNREAD_LINES:
            skipped += 1
            continue
        lines.append(DataLine(kind, _gb_text(volume), _percent(part), f"Read by {READS_NOTHING}; " + ("0 queries run" if counted else "queries run: not recorded"), _writers_text(item)))
    if not lines:
        return None
    notes, short = [], []
    unknown = _whole(digest.get("unknown"))
    if unknown:
        notes.append(f"What reads {unknown} other kind{'s' if unknown != 1 else ''} of data could not be read, so {'they are' if unknown != 1 else 'it is'} not counted.")
        short.append(f"what reads {unknown} other kind{'s' if unknown != 1 else ''} of data")
    if digest.get("runsRecorded") is not True:
        notes.append("The queries that people run were not counted: the record of them is off or could not be read in full.")
        short.append("the queries people run")
    first = "Under 1 percent" if round(share * 100) < 1 else f"About {_percent(share)}"
    sentence = f"{first} of what this workspace is billed for is data that nothing reads."
    volume = f"That is {_gb_text(gone)} of the {_gb_text(whole)} that it took in over {days_text(days)}."
    return Unread(sentence, volume, days_text(days), tuple(lines), _whole(digest.get("more")) + skipped, " ".join(notes), f"Not counted: {' and '.join(short)}." if short else "")


def unread_saving(case: CaseRecord | None) -> float | None:
    """The saving of the data that nothing reads in US dollars a month, when the digest of the case holds one that is whole: a number above 0 that is not more than the cost of the resource in the
    last 30 days. Code worked it out (cases/unread.py); a model never writes it."""
    digest = _digest(case)
    figure = _figure(digest.get("savingUsd")) if digest is not None else None
    cost = _figure(case.cost_usd_30d) if case is not None else None
    if figure is None or figure <= 0 or cost is None or figure > cost + 0.005:
        return None
    return round(figure, 2)


def _unread_basis(case: CaseRecord | None) -> str:
    """What the figure of the data that nothing reads is computed from, as a part of a sentence of every render ("from ...", "(...)", "Basis: ...")."""
    digest = _digest(case) or {}
    share = _figure(digest.get("share"))
    return "the workspace's cost of the last 30 days times the share of its data that nothing reads" + (f", {_about(share)}" if share is not None and 0 < share <= 1 else "")


def _unread_missing(case: CaseRecord | None) -> str:
    """Why there is no figure for a workspace whose record was not enough to say which data nothing reads ("" for any other case)."""
    digest = _digest(case)
    return UNREAD_MISSING.get(str(digest.get("missing")), "") if digest is not None and not digest.get("kinds") else ""


def options_of(unread: Unread | None, figure: bool) -> tuple[Option, ...]:
    """What a person could do about data that nothing reads, in three choices, with what each loses or puts at risk. The words are code's. They name the kinds of data that are listed and, when the
    tools showed them, the kinds of resource of its largest writers; they never name a thing that the tools did not show. `figure` says that the request shows a figure, which counts all of
    this data as no longer stored: the choices that remove only some of it save less."""
    if unread is None or not unread.lines:
        return ()
    names = [line.kind for line in unread.lines]
    others = max(0, len(names) - 3) + unread.more
    listed = f"{', '.join(names[:3])} and {others} more" if others > 0 else _series(names[:3])
    written = " ".join([f"On the last closed day, the largest writers of {line.kind} were: {line.writers}." for line in unread.lines if line.writers][:2])
    less = " That lowers the bill by less than the figure above." if figure else ""
    return (
        Option(f"Stop sending {listed} at the source: the log categories that a diagnostic setting sends, or the data collection rule that writes it." + (f" {written}" if written else ""),
               "alert rules, workbooks or investigations that need this data get no new data."),
        Option("Filter it before it is stored: a transformation in the data collection rule that sends it (or, for data that comes through a diagnostic setting, in the workspace's own "
               "transformation rule) can drop the rows or the columns that nobody needs.",
               "what the filter drops cannot be searched later, and a filter that is too wide hides what an investigation needs. It lowers the bill only by what it drops."),
        Option("Keep it, but cheaper: for data that people only search now and then, move its table to the Basic or Auxiliary plan, if the table supports it, or keep it for less time.",
               "those plans offer fewer ways to query the data and charge each query for what it scans, and a shorter retention deletes old data for good." + less),
    )


# -- the point-to-site gateways whose scale units nobody uses --------------------------------------------------------------------------------------

GATEWAYS = "gateways"  # the key of the digest in the facts of a case (cases/gateways.py)
GATEWAYS_WHAT = ("A point-to-site gateway is the gateway that a virtual hub runs for its User VPN setting, so that people can connect to Azure from their own devices. Azure runs it inside the hub, which Microsoft "
                 "manages, so what a person sets and sees is one number on the hub: its scale units. Azure charges for each unit by the hour whether anybody is connected or not, so a number that was set high once is easy to forget.")
GATEWAYS_SHORT = "Options: scale them down to what their connections need, or keep them and say why."
GATEWAYS_STEPS = ("In the Azure portal, open the virtual hub, go to its Point to site page, set Gateway scale units to the smaller number and confirm (the Edit virtual hub page has the same setting). "
                  "With the Azure CLI, once for each gateway: az network p2s-vpn-gateway update --name <gateway> --resource-group <resource group> --scale-unit <scale units>. "
                  "Azure says to plan for downtime when scale units change, and a hub update can take up to 30 minutes.")
GATEWAYS_LOOK = ("In the Azure portal, open Monitor, then Metrics, choose the gateway and the metric P2S Connection Count, and look at the highest value of each day; "
                 "az network p2s-vpn-gateway list shows the gateways and their scale units.")


def _gateway_digest(case: CaseRecord | None) -> dict | None:
    facts = case.facts if case is not None and isinstance(case.facts, dict) else {}
    found = facts.get(GATEWAYS)
    return found if isinstance(found, dict) else None


def _plural_of(count: int, one: str, many: str | None = None) -> str:
    return f"{number_text(count)} {one if count == 1 else (many or one + 's')}"


def gateways_of(case: CaseRecord | None) -> Gateways | None:
    """What a finding about point-to-site gateways says, from the digest in the facts of its case (cases/gateways.py), or None for a case that has none or whose digest is not as it should be. Every
    number is checked again here: a digest that is not as it should be shows nothing and never something else."""
    digest = _gateway_digest(case)
    if digest is None:
        return None
    count, counted = _whole(digest.get("gateways")), digest.get("counted")
    if not 1 <= count <= MAX_GROUP or isinstance(counted, bool) or not isinstance(counted, int) or not 0 <= counted <= count:
        return None
    one = count == 1
    thing = "the gateway" if one else "these gateways"
    if counted == 0:
        sentence = f"Meternaut could not say how many scale units {thing} {'has' if one else 'have'} or whether anybody connected, because the tools did not record both."
        return Gateways(GATEWAYS_WHAT, sentence, (), 0, 0, count, caveat=f"Not counted: {_plural_of(count, 'gateway')}.")
    units, target, days, quiet = (_whole(digest.get(key)) for key in ("units", "target", "days", "quiet"))
    peak = _figure(digest.get("peak"))
    if units < counted or not counted <= target <= units or peak is None or peak < 0 or not days or quiet > counted:
        return None
    any_of = "the gateway" if counted == 1 else f"any of the {number_text(counted)} gateways"
    span = (f"in the {days_text(days)} that Azure Monitor has a value for" if counted == 1
            else f"in the days that Azure Monitor has a value for (at least {number_text(days)} for each)")
    if peak == 0:
        first = f"Nobody was connected to {any_of} {span}."
    else:
        first = f"The most connections at one time on {any_of} was {number_text(peak)} {span}." + (f" Nobody was connected to {number_text(quiet)} of them." if counted > 1 and quiet else "")
    fewer = units - target
    limit = _whole(digest.get("limit")) if counted == 1 else 0
    if counted == 1:
        have = f"It has {_plural_of(units, 'scale unit')}" + (f", which carry up to {number_text(limit)} connections at one time" if limit else "")
    else:
        have = f"They have {_plural_of(units, 'scale unit')} together"
    if fewer:
        second = f"{have}. The smallest size that still carries what {'it' if counted == 1 else 'each'} saw is {number_text(target)}{'' if counted == 1 else ' together'}, which is {number_text(fewer)} fewer."
    else:
        second = f"{have}. {'It is' if counted == 1 else 'Each is'} at the smallest size that carries what it saw already."
    rows = (Fact("Scale units", f"{number_text(units)} in all" + ("" if counted == 1 else f", on {number_text(counted)} gateways"), RESOURCE_GRAPH),
            Fact("Most connections at one time", f"{number_text(peak)} in the last {days_text(days)} with a value", MONITOR))
    left = count - counted
    note = f"{_plural_of(left, 'gateway')} of the {number_text(count)} {'is' if left == 1 else 'are'} not counted: the tools did not record the scale units or the connections." if left else ""
    return Gateways(GATEWAYS_WHAT, f"{first} {second}", rows, fewer, counted, count, note, f"Not counted: {number_text(left)} of {number_text(count)} gateways." if left else "")


def gateways_saving(case: CaseRecord | None) -> float | None:
    """The saving of scaling the gateways down, in US dollars a month, when the digest of the case holds one that is whole: a number above 0 that is not more than the cost of the resource in the
    last 30 days (for a group, of everything that it stands for). Code worked it out (cases/gateways.py); a model never writes it."""
    digest = _gateway_digest(case)
    figure = _figure(digest.get("savingUsd")) if digest is not None else None
    cost = _figure(case.cost_usd_30d) if case is not None else None
    if figure is None or figure <= 0 or cost is None or figure > cost + 0.005:
        return None
    return round(figure, 2)


def _gateways_basis() -> str:
    return "the cost of the gateways in the last 30 days, scaled by the share of their scale units that would be taken away (the price list was not read, so it is an estimate)"


def _gateways_missing(case: CaseRecord | None) -> str:
    """Why there is no figure for gateways whose record was not enough ("" for any other case)."""
    found = gateways_of(case)
    if found is None or found.counted:
        return ""
    return "The scale units or the connections of these gateways were not recorded, so no figure can be worked out for scaling them down."


def gateway_options(found: Gateways | None) -> tuple[Option, ...]:
    """What a person could do about gateways that carry more scale units than anybody uses, in two choices with the exact steps and what each puts at risk. The words are code's."""
    if found is None:
        return ()
    these = "the gateway" if found.gateways == 1 else "the gateways"
    keep = Option(f"Keep {these} as {'it is' if found.gateways == 1 else 'they are'}, and say why in your answer: for example a rollout that is still to come, or a gateway that is kept ready for a failure.",
                  "the scale units keep billing by the hour, used or not.")
    if found.counted and not found.fewer:
        return (Option(f"Leave {these} as {'it is' if found.gateways == 1 else 'they are'}: {'it has' if found.gateways == 1 else 'each has'} the smallest size that carries the most connections that it saw.",
                       "nothing more can be saved by scale units."),)
    first = (f"Scale {these} down by {_plural_of(found.fewer, 'scale unit')} in all, each to the smallest size that carries the most connections that it saw. " if found.counted else
             f"Look at the connections of {these} first. {GATEWAYS_LOOK} Then scale down the ones that nobody uses. ")
    return (Option(first + GATEWAYS_STEPS, "users who are connected may be disconnected while it changes, and with fewer scale units a gateway carries fewer connections and less traffic."), keep)


def scenario_saving(case: CaseRecord | None) -> float | None:
    """The figure that code worked out for a finding that has an analysis (the data that nothing reads, or gateways that carry more scale units than anybody uses), or None."""
    return unread_saving(case) if _digest(case) is not None else gateways_saving(case)


# -- what the cost says -------------------------------------------------------------------------------------------------------------------------

def cost_state_of(case: CaseRecord | None, together: Group | None = None) -> str:
    """How the 30-day cost of a case was read (cases/costs.py): lines, none, failed, currency, or "" when it was not read. A number above nothing is always lines. A record that holds no state
    (one from before the state existed) is read from its number: 0.0 is none for a resource, which is what it always meant, and unread for a subscription or a resource group, because an
    earlier version looked those up by their own id, which no cost line has, and so said 0.0 for a cost that Cost Management shows."""
    if case is None:
        return ""
    cost = together.cost if together is not None and together.cost is not None else _figure(case.cost_usd_30d)
    stored = case.cost_state if case.cost_state in cost_words.STATES else ""
    if cost is not None and cost > 0:
        return cost_words.LINES
    if stored in (cost_words.FAILED, cost_words.CURRENCY):
        return stored  # a read that failed, or that is not in dollars, is never a figure of nothing, whatever the number beside it says
    if cost is None:
        return cost_words.NONE if stored == cost_words.NONE else ""  # none without a number: the subscription has no cost line at all
    if stored in (cost_words.NONE, cost_words.LINES):
        return stored
    return "" if cost_words.is_container(case.resource_id) else cost_words.NONE


def scope_of_case(case: CaseRecord | None) -> str:
    """What a finding is about, as far as its cost goes: the subscription, a resource group, or a resource (anything else, and a case that is not known)."""
    kind = cost_words.scope_of(case.resource_id).kind if case is not None else ""
    return kind if kind in ("subscription", "group") else "resource"


def made_of_text(case: CaseRecord | None) -> str:
    """What the cost of a finding about a whole subscription or resource group is made of, as one sentence with its largest services ("Made of: Virtual Network $88.10, Microsoft Defender for
    Cloud $41.25, Azure Cognitive Search $19.60 and 5 more services $63.45."); empty for every other finding, and when the services were not kept."""
    if case is None or scope_of_case(case) == "resource":
        return ""
    parts = cost_words.valid_parts(case.cost_by_service)
    if not parts:
        return ""
    items = [f"{text_of(name, cost_words.MAX_SERVICE)} {usd_text(amount)}" for name, amount in parts["services"]]
    if parts["more"] > 0 and parts["moreUsd"] > 0:
        items.append(f"{number_text(parts['more'])} more service{'' if parts['more'] == 1 else 's'} {usd_text(parts['moreUsd'])}")
    return "Made of: " + (items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]) + "."


def estimate_for(case: CaseRecord | None, state: str, together: Group | None = None) -> estimates.Estimate | None:
    """The estimate at list price of what a managed disk costs, only for a finding about one disk that Azure has no cost line for. Never a cost, and never counted as one: it is not in
    `Brief.cost`, and a finding that has cost lines has none."""
    if case is None or together is not None or state != cost_words.NONE or (case.resource_type or "").lower() != "microsoft.compute/disks":
        return None
    return estimates.estimate_of(case.estimate)


def cost_link(subscription: str, resource_id: str, subscription_name: str, scope: str, together: Group | None) -> tuple[str, str]:
    """The address of Cost analysis in the Azure portal for the scope that the cost of a finding is the cost of, and that scope in words: the subscription for a finding about one (or about a
    resource that has no group), the resource group for a finding about one or about a resource in one. A finding about many resources in more than one group has none: what they cost is in
    no one place. The address is made from the id of the subscription and the resource group that the id of the resource names (a name that cannot be one makes no link), never from the
    words that a page shows."""
    if together is not None and together.groups != 1:
        return "", ""
    name = cost_words.scope_of(resource_id).group
    if scope != "subscription" and name:
        url = cost_words.analysis_url(subscription, name)
        return (url, f"resource group {text_of(name, 90)}") if url else ("", "")
    url = cost_words.analysis_url(subscription)
    return (url, f"subscription {text_of(subscription_name, 80) or text_of(subscription, 40)[:8]}") if url else ("", "")


def _analysed(case: CaseRecord | None) -> bool:
    return _digest(case) is not None or _gateway_digest(case) is not None


def _saving(case: CaseRecord | None, plan: PlanRecord | None, action: ActionRecord | None, state: str) -> Saving:
    figure = _figure(plan.saving_usd_month if plan is not None else (case.saving_usd_month if case is not None else None))
    if case is not None and (plan is None or plan.family == ADVISE) and case.recommendation == "delete" and proposal_of(case) != "delete":
        figure = None  # a finding that is only a look has no saving: a record from before this rule kept the cost as one
    scenario = scenario_saving(case)  # the figure that code worked out from the analysis of the finding (data that nothing reads, gateways): the case holds no figure of its own for a change
    fam = shown(plan.family) if plan is not None else None
    own = _figure(case.saving_usd_month) if case is not None else None
    # A case that holds that analysis and no figure of its own is worth what the analysis says now, the same numbers as its rows: the figure of a request is the one that code took when it was made,
    # and a Watch that judged the case again while the request was open may have found the volume moved. That one stays in the plan as the record of what was asked.
    current = fam is None and _analysed(case) and (own is None or own <= 0)
    if current or (plan is None and (figure is None or figure <= 0)):
        figure = scenario
    waiting = None if current else (_figure(plan.waiting_costs_usd_day) if plan is not None else None)
    check = action.verification if action is not None and isinstance(action.verification, dict) else {}
    before, after = _figure(check.get("costBeforeUsd30d")), _figure(check.get("costAfterUsd"))
    if action is not None and action.no_change:
        return Saving(None, "", "", None, NOTHING_CHANGED_SAVING, True)
    # Cost lines that show no cost confirm only a change that ends the cost (a delete, a stop). A resize or a change of tier leaves the resource billing, so its confirmation is a lower
    # figure, in the branch below, and never "no cost".
    ends = fam is None or fam.cost_ends
    if action is not None and action.state == "verified" and ends and before is not None and after == 0 and before > 0:
        return Saving(round(before, 2), "Verified", "the cost lines after the change, which show no cost for this resource", None, "")
    saved = _figure(check.get("savedUsdMonth"))
    if action is not None and action.state == "verified" and saved is not None and saved > 0:
        return Saving(round(saved, 2), "Verified", "the cost lines of the whole days after the change, which are lower than those of the 30 days before it", None, "")
    if figure is None or figure <= 0:
        cost = _figure(case.cost_usd_30d) if case is not None else None
        group = group_of(case)
        read = cost_state_of(case, group)
        scope = cost_words.scope_of(case.resource_id).kind if case is not None else ""
        thing, this = {"subscription": ("The subscription", "this subscription"), "group": ("The resource group", "this resource group")}.get(scope, ("The resource", "this resource"))
        if read == cost_words.NONE:
            why = cost_words.state_words(read, group is not None)
        elif cost is None or read == "":
            why = {cost_words.FAILED: cost_words.FAILED_WORDS, cost_words.CURRENCY: cost_words.CURRENCY_WORDS}.get(read) or (
                "No cost line of the last 30 days was read for " + ("these resources." if group is not None else f"{this}."))
        elif cost <= 0:
            why = cost_words.state_words(cost_words.LINES, group is not None)  # lines that cost nothing: Cost Management shows no cost
        elif group is not None:
            why = f"The {number_text(group.count)} resources cost {usd_text(cost)} together in the last 30 days. What a change would save was not worked out."
        else:
            why = f"{thing} cost {usd_text(cost)} in the last 30 days. What a change would save was not worked out."
        specific = False
        if fam is not None and fam.no_figure:
            why, specific = fam.no_figure, True
        elif _unread_missing(case) or _gateways_missing(case):
            why, specific = _unread_missing(case) or _gateways_missing(case), True
        return Saving(None, "", "", None, why, specific)
    if waiting is None:
        waiting = round(figure / 30, 2)
    if fam is not None and fam.saving_basis:
        return Saving(round(figure, 2), fam.saving_level, fam.saving_basis, waiting, "")
    if fam is None and scenario is not None and abs(figure - scenario) < 0.005:
        return Saving(round(figure, 2), "Scenario", _unread_basis(case) if _digest(case) is not None else _gateways_basis(), waiting, "")
    advisor = case is not None and (case.detector == "advisor-cost" or (case.detector == "investigation" and case.recommendation == "change"))
    if advisor:
        return Saving(round(figure, 2), "Scenario", "Azure Advisor's own estimate: no cost line of this resource backs it", waiting, "")
    return Saving(round(figure, 2), "Expected", "the cost lines of the last 30 days", waiting, "")


def _word(value: object) -> str:
    return text_of(str(value).replace("_", " "), 40)


def _size_gb(value: object) -> str:
    text = text_of(value, 24)
    match = re.fullmatch(r"(up to|over) (\d{1,5})", text)
    return f"{match.group(1)} {int(match.group(2)):,} GB" if match else ""


def _typed_facts(case: CaseRecord) -> list[Fact]:
    """The typed facts of a case that say what the resource is like, in the order of what helps a decision: why it is a lead, its age, its size and kind."""
    facts = case.facts if isinstance(case.facts, dict) else {}
    graph = "Azure Advisor" if case.detector == "advisor-cost" else RESOURCE_GRAPH
    rows: list[Fact] = []
    state = DETECTOR_STATE.get(case.detector)
    if state:
        rows.append(Fact(state[0], state[1], graph))
    if case.detector == "investigation" and facts.get("basis") in BASIS_WORDS:
        rows.append(Fact("What the investigation found", BASIS_WORDS[facts["basis"]], "The first AI; code checks the numbers again"))
    age = facts.get("ageDays")
    if isinstance(age, int) and not isinstance(age, bool) and age >= 0:
        rows.append(Fact("Age", "Made today" if age == 0 else days_text(age), graph))
    size = _size_gb(facts.get("sizeGb"))
    if size:
        rows.append(Fact("Size", size, graph))
    sku = facts.get("sku")
    if isinstance(sku, str) and sku and sku != "other":
        rows.append(Fact("Type", DISK_TYPES.get(sku, _word(sku).capitalize()), graph))
    tier = facts.get("tier")
    if isinstance(tier, str) and tier and tier != "other":
        rows.append(Fact("Tier", _word(tier).capitalize(), graph))
    workers = facts.get("workers")
    if isinstance(workers, int) and not isinstance(workers, bool):
        rows.append(Fact("Workers", number_text(workers), graph))
    family, vcpu = facts.get("sizeFamily"), facts.get("vcpu")
    if isinstance(vcpu, int) and not isinstance(vcpu, bool):
        rows.append(Fact("Size", f"{vcpu} vCPUs" + (f", {_word(family)} series" if isinstance(family, str) and family not in ("", "other") else ""), graph))
    allocation = facts.get("allocation")
    if isinstance(allocation, str) and allocation != "other":
        rows.append(Fact("Address", _word(allocation).capitalize(), graph))
    for key, label in (("backendPools", "Backend pools"), ("loadBalancingRules", "Rules"), ("frontends", "Frontends")):
        value = facts.get(key)
        if isinstance(value, int) and not isinstance(value, bool):
            rows.append(Fact(label, number_text(value), graph))
    target = facts.get("targetService")
    if isinstance(target, str) and target != "other":
        rows.append(Fact("Target service", _word(target), graph))
    impact = facts.get("impact")
    if isinstance(impact, str) and impact != "other":
        rows.append(Fact("Impact", _word(impact).capitalize(), graph))
    return rows


def _metric_facts(case: CaseRecord) -> list[Fact]:
    """What the tools measured and code re-checked, with unit and period: at most two, the ones with nothing recorded first (they are the idle evidence)."""
    facts = case.facts if isinstance(case.facts, dict) else {}
    units = facts.get("metricUnits") if isinstance(facts.get("metricUnits"), dict) else {}
    spans = facts.get("metricDays") if isinstance(facts.get("metricDays"), dict) else {}
    seen = facts.get("metricDaysWithData") if isinstance(facts.get("metricDaysWithData"), dict) else {}
    found = [(name, total) for name, total in _metrics(case).items() if isinstance(name, str) and _figure(total) is not None]
    rows: list[Fact] = []
    for name, total in sorted(found, key=lambda item: (item[1] != 0, item[0]))[:2]:
        days = spans.get(name)
        amount = quantity(total, units.get(name))
        value = f"{amount} in {days_text(days)}" if days_text(days) else f"{amount} in the period measured"
        if days_text(days) and isinstance(seen.get(name), int) and not isinstance(seen.get(name), bool):
            value += f", with a value on {seen[name]} of those days"
        rows.append(Fact(text_of(name, 60), value, f"{MONITOR}, {days_text(days)}" if days_text(days) else MONITOR))
    return rows


def _date(value: object) -> str:
    text = text_of(value, 40)
    match = re.match(r"\d{4}-\d{2}-\d{2}", text)
    return match.group(0) if match else text


def facts_of(case: CaseRecord | None) -> tuple[Fact, ...]:
    """At most five rows of evidence, chosen by code from the cost lines, the typed facts, the checks and the owner record, the most decision-relevant first: what Advisor says to look at (for
    an Advisor recommendation), the cost (for a case that stands for many resources: how many they are, what they cost together and the first few), a check that held the resource back,
    what was measured, why it is a lead and its age, its last change, the checks that found nothing, and then what it is like."""
    if case is None:
        return ()
    head: list[Fact] = []
    group = group_of(case)
    found = gateways_of(case)
    rows = list(found.rows) if found is not None else []
    cost = _figure(case.cost_usd_30d)
    state = cost_state_of(case, group)
    words = advice_of(case)
    if words is not None:
        head.append(Fact("What to look at", words[1], "Azure Advisor"))  # Advisor's own words say what to look at, before any figure
    if group is not None:
        covered = _group_facts(group, case)
        head += covered[:2] + rows + covered[2:]  # the cost of the case is what all of them cost: the row of the group says it; the rows of gateways come before the examples
    elif state == cost_words.NONE:
        head.append(Fact("Cost, last 30 days", "Azure has no cost line for this yet", "Azure cost lines"))
    elif cost is not None and state == cost_words.LINES:
        head.append(Fact("Cost, last 30 days", usd_text(cost), "Azure cost lines"))
    elif state in (cost_words.FAILED, cost_words.CURRENCY):
        head.append(Fact("Cost, last 30 days", "Could not be read just now" if state == cost_words.FAILED else "Not in US dollars", "Azure cost lines"))
    guards = [g for g in case.guards if isinstance(g, str)]
    if guards:
        head.append(Fact("Held back by", " ".join(GUARD_WORDS.get(g, text_of(g, 40)) for g in guards[:2]), CHECKED))
    head += rows if group is None else []
    if unread_of(case) is None and found is None:  # the rows of the data that nothing reads, and of gateways, say it better than two measurements of it
        head += _metric_facts(case) or ([Fact("Use, last 30 days", NOT_MEASURED, MONITOR)] if group is None and _idle(case) else [])
    typed = _typed_facts(case)
    tail: list[Fact] = []
    owner = case.owner if isinstance(case.owner, dict) else {}
    changed, changed_by = _date(owner.get("changedAt")), who_text(owner.get("changedBy"), 60)
    if changed:
        tail.append(Fact("Last change", changed + (f" by {changed_by}" if changed_by else ""), "Azure Activity Log"))
    if not guards and case.status != "error":
        tail.append(Fact("Locks and keep tags", "None found", CHECKED))
    return tuple((head + typed[:2] + tail + typed[2:])[:MAX_FACTS])


def owner_of(case: CaseRecord | None) -> OwnerLine:
    """Who the resource probably belongs to, as plain facts from the tags and the Activity Log. Missing is said, and so is a lookup that was not made."""
    owner = case.owner if case is not None and isinstance(case.owner, dict) else {}
    parts: list[str] = []
    tag = text_of(owner.get("tagOwner"), 80)
    if tag:
        named = text_of(owner.get("tagName"), 30) or "owner"
        parts.append(f"Tag {named}: {tag}.")
    made_by, made_at = who_text(owner.get("createdBy"), 80), _date(owner.get("createdAt"))
    if made_by or made_at:
        parts.append("Created" + (f" by {made_by}" if made_by else "") + (f" on {made_at}" if made_at else "") + ".")
    last_by, last_at = who_text(owner.get("changedBy"), 80), _date(owner.get("changedAt"))
    if last_by or last_at:
        parts.append("Last changed" + (f" by {last_by}" if last_by else "") + (f" on {last_at}" if last_at else "") + ".")
    if parts:
        return OwnerLine(True, " ".join(parts))
    if owner.get("lookedUp"):
        return OwnerLine(False, "No owner is recorded on the resource.")
    return OwnerLine(False, "Meternaut has not looked up who owns this resource yet.")


def _where(name: str, group: str, subscription: str, resource_id: str, rtype: str, subscription_name: str = "") -> Where:
    return Where(text_of(subscription, 40)[:8], text_of(group, 90), kind_words(rtype)[0], text_of(name, MAX_NAME), portal_url(resource_id), kind_words(rtype)[1],
                 text_of(subscription_name, 80))


def _answers(kind: str, state: str, may_answer: bool, changes_paused: bool, stage: str = "", refused: bool = False) -> tuple[str, ...]:
    """The answers that exist for this person right now: a person who may answer, and a request that is open. The answer that approves is missing while a switch holds it (the
    caller says so in `changes_paused`: for a change the switches `all` and `changes`, for advice the switch `all`), and while a look at the resource shows that the change would be refused
    (`refused`): the answers that are left are the ones that approve nothing. A change that needs two people (`stage`, see cases/twopeople.py)
    offers the first person "confirm" in the place of "approve", the second person "approve", and a person who confirmed it only a decline or "not mine": a question or a "later" would
    take the place of their confirmation."""
    if kind == "info" or state != "open" or not may_answer:
        return ()
    answers = ["approve", "decline", "not_mine", "ask", "later"]
    if stage == "mine":
        answers = ["decline", "not_mine"]
    elif stage:
        answers[0:1] = {"first": ["confirm"], "stale": ["confirm"], "second": ["approve"]}.get(stage, [])
    if changes_paused or refused:
        answers = [name for name in answers if name not in ("approve", "confirm")]
    return tuple(answers)


def second_of(plan: PlanRecord, decisions: Sequence[DecisionRecord], viewer: str, now: dt.datetime) -> Second:
    """Where a request that needs two people stands for `viewer` (an object id; empty for a letter, which knows no reader), in plain words."""
    found = standing(plan, decisions, viewer)
    name = text_of(found.by, 80) or "A person"
    when = ago_text(now, found.at)[1] if found.at else ""
    if found.stage == "second" and not viewer:
        return Second(found.stage, f"{TWO_PEOPLE} {name} confirmed the request {when}.", name)
    return Second(found.stage, SECOND_WORDS[found.stage].format(name=name, when=when), name if found.by else "")


def _confirmed_line(plan: PlanRecord, decisions: Sequence[DecisionRecord]) -> tuple[str, ...]:
    """The line that says who confirmed a plan first, for the record of a change that needed two people; nothing for any other."""
    if not needs(plan):
        return ()
    good = [d for d in confirmations(plan, decisions) if counts(plan, d)]
    return (f"Confirmed first by {text_of(good[0].approver_name, 80)}.",) if good else ()


def _decisive(decisions: Sequence[DecisionRecord], *kinds: str) -> DecisionRecord | None:
    chosen = [d for d in decisions if d.decision in kinds]
    return max(chosen, key=lambda d: (d.at, d.approver_oid)) if chosen else None


def not_now_reason(why: str) -> str:
    """The reason that a look at the resource gave (cases/precheck.py), as a sentence of its own: a capital letter, a full stop, and that nothing was changed."""
    text = plain(why, 300).rstrip(". ")
    return f"{text[:1].upper()}{text[1:]}. Nothing was changed." if text else "Nothing was changed."


def check_lines(check: Mapping, said: str = "") -> list[str]:
    """What the check after a change found, in plain lines. A line that `said` (the result that is shown next to it) holds already is left out."""
    lines: list[str] = []
    if "gone" in check:
        lines.append("Azure no longer lists the resource." if check["gone"] else "Azure still lists the resource.")
    if check.get("now"):
        lines.append(text_of(check["now"], 200))
    after = _figure(check.get("costAfterUsd"))
    if after is not None and check.get("currency") in (None, "", "USD"):
        lines.append(f"Cost lines since the change: {usd_text(after)}.")
    before = _figure(check.get("costBeforeUsd30d"))
    if before is not None:
        lines.append(f"The 30 days before the change cost {usd_text(before)}.")
    if check.get("note"):
        lines.append(text_of(check["note"], 200))
    return [line for line in lines if line.lower() not in said.lower()]


def _nothing_changed(result: object) -> str:
    """The line of an approval that changed nothing: the action's own sentence of code ("The machine was already stopped ... Nothing to change.") without its last short sentence."""
    why = text_of(result, 300)
    for ending in ("Nothing to change.", "Nothing to delete."):
        if why.endswith(ending):
            why = why[: -len(ending)].rstrip()
    if len(why) > 1 and why[0].isupper() and not why[1].isupper():
        why = why[0].lower() + why[1:]
    return f"Nothing was changed: {why}" if why else "Nothing was changed."


def _outcome(plan: PlanRecord | None, state: str, action: ActionRecord | None, decisions: Sequence[DecisionRecord]) -> Outcome:
    none = Outcome("", "", (), "", "", "")
    if plan is None or state == "open":
        return none
    advice = plan.family == ADVISE
    if state == "expired":
        return Outcome("expired", "Expired", ("Nobody answered in time.", "Nothing changed."), "Expired, nobody answered", "", plan.expires_at)
    if state == "declined":
        found = _decisive(decisions, "decline")
        who = text_of(found.approver_name, 80) if found else "A person"
        reason = REASON_WORDS.get(found.reason, "") if found else ""
        said = f"{who} said it is not worth acting on." if advice else f"Declined by {who}."
        return Outcome("declined", "Not worth it" if advice else "Declined", (said + (f" Reason: {reason}." if reason else ""), "Nothing changed."),
                       "Not worth it" if advice else "Declined", who, found.at if found else "")
    if state == "withdrawn":
        found = _decisive(decisions, "not_mine")
        who = text_of(found.approver_name, 80) if found else "A person"
        return Outcome("withdrawn", "Not theirs", (f"{who} said that this is not theirs.", "Nothing changed."), "Not theirs", who, found.at if found else "")
    found = _decisive(decisions, "approve")
    who = text_of(found.approver_name, 80) if found else "A person"
    at = found.at if found else ""
    first = _confirmed_line(plan, decisions)
    if advice:
        return Outcome("answered", "Worth acting on", (f"{who} said this is worth acting on.", "Nothing was changed in Azure."), "Worth acting on", who, at)
    if state == "approved":
        waiting = action is not None and action.state == "queued" and action.step_up
        return Outcome("approved", "Approved", (f"Approved by {who}.", *first, WAITING_FOR_THE_CHECK if waiting else "The change is being made now."), "Being made now", who, at)
    if action is None:
        return Outcome("approved", "Approved", (f"Approved by {who}.", *first), "Approved", who, at)
    check = action.verification if isinstance(action.verification, dict) else {}
    if action.no_change and action.state in ("done", "verified", "unknown") and state == "consumed":
        # The person approved, and when Meternaut looked the resource was as the plan wants (or gone): nothing was written, so no line says that it was made with anyone's rights.
        return Outcome("unchanged", NOTHING_CHANGED, (f"Approved by {who}.", *first, _nothing_changed(action.result)), NOTHING_CHANGED, who, action.finished_at or at)
    if action.state == "verified":
        return Outcome("verified", "Done and checked", (f"Approved by {who}, and made with their own Azure rights.", *first, *(check_lines(check) or [text_of(action.result, 300)])),
                       "Done and checked", who, action.finished_at or at)
    if action.state == "running":
        return Outcome("running", "Running in Azure", (f"Approved by {who}, and sent to Azure with their own Azure rights.", *first, text_of(action.result, 300) or RUNNING_IN_AZURE),
                       "Running in Azure", who, at)
    if action.state in ("done", "unknown") and state == "consumed":
        lines = [f"Approved by {who}, and made with their own Azure rights.", *first, text_of(action.result, 300), *check_lines(check, action.result or "")]
        return Outcome("done", "Done", tuple(line for line in lines if line), "Done" if action.state == "done" else "Done, not confirmed yet", who, action.finished_at or at)
    detail = text_of(action.error or action.result, 300) or "The change could not be finished."
    return Outcome("failed", "Not made", (detail,), "Not made", who, action.finished_at or at)


# -- the whole -----------------------------------------------------------------------------------------------------------------------------

def build_brief(case: CaseRecord | None, plan: PlanRecord | None, action: ActionRecord | None = None, decisions: Sequence[DecisionRecord] = (), *, now: dt.datetime,
                may_answer: bool = False, changes_paused: bool = False, viewer: str = "", ready: Readiness | None = None) -> Brief:
    """The brief of one case, with its plan and the action of the plan when there are any. `may_answer` says that the person who looks may answer the plan (the role and
    the names are checked by the caller); `changes_paused` that a switch holds the changes; `viewer` is the object id of the person who looks, for a request that needs two people
    (what that person may do depends on whether they confirmed it); `ready` is what a look at the resource said about a change that waits for an OK (cases/precheck.py), when the caller took
    one: it takes the answers that approve out of a change that the checks of the runner would refuse. At least one of `case` and `plan` is given."""
    now = _utc(now)
    name, group, subscription, resource_id, rtype = _subject(case, plan)
    family = plan.family if plan is not None else ""
    kind = "info" if plan is None else ("advice" if family == ADVISE else "change")
    end = parse_time(plan.expires_at) if plan is not None else None
    state = "none" if plan is None else ("expired" if plan.state == "open" and (end is None or now >= end) else plan.state)
    recommendation = case.recommendation if case is not None else None
    said = words_of(family, plan, rtype, text_of(name, MAX_NAME), text_of(group, 90)) if kind == "change" and plan is not None else None
    if said is not None:
        change, who, rechecked = said.change, WHO_ACTS, said.rechecked
        undo, risk = Undo(said.reversible, said.undo), Risk(said.level, said.risk)
    elif kind == "change":
        change, who, rechecked = text_of(plan.what_changes, 300) or "The change is described in the request.", WHO_ACTS, ""
        irreversible = family.startswith("delete") or not plan.undo.strip()
        undo = Undo(False, text_of(plan.undo, 300)) if irreversible else Undo(True, text_of(plan.undo, 300))
        risk = Risk("high" if irreversible else "medium", text_of(plan.could_go_wrong, 240) or "The risk is not recorded.")
    elif kind == "advice":
        change, who, rechecked, undo, risk = ADVICE_CHANGE, ADVICE_WHO, "", Undo(True, ADVICE_UNDO), acting_risk(case)
    else:
        change, who, rechecked, undo, risk = NO_CHANGE, "", "", Undo(True, ADVICE_UNDO), (acting_risk(case) if case is not None and case.detector == "investigation" else Risk("low", "Nothing changes in Azure."))
    found_at = (case.first_seen_at if case is not None and case.first_seen_at else (plan.created_at if plan is not None else ""))
    age, _ = ago_text(now, found_at)
    saving = _saving(case, plan, action, state)
    unread = unread_of(case)
    found = gateways_of(case)
    together = group_of(case)
    read = cost_state_of(case, together)
    scope = scope_of_case(case)
    cost_url, cost_scope = cost_link(subscription, resource_id, case.subscription_name if case is not None else "", scope, together)
    second = second_of(plan, decisions, viewer, now) if kind == "change" and needs(plan) else None
    looked = Readiness(ready.state, plain(ready.why, 300)) if ready is not None and kind == "change" and state == "open" else None
    last_try = text_of(action.result, 300) if kind == "change" and state == "open" and action is not None and action.state == "withdrawn" else ""
    return Brief(
        case_id=plain(case.case_id if case is not None else (plan.case_id if plan is not None else ""), 64), plan_id=plain(plan.plan_id if plan is not None else "", 64),
        plan_code=plain(plan.code if plan is not None else "", 16), kind=kind, family=plain(family, 40), state=plain(state, 20),
        headline=headline_of(family, name, group, rtype, recommendation, plan.title if plan is not None else "", plan, together=together, case=case),
        saving=saving, confidence=confidence_of(case, plan), facts=facts_of(case), reasoning=reasoning_of(case), doubt=doubt_of(case, plan),
        change=change, who_acts=who, rechecked=rechecked, undo=undo, risk=risk, owner=owner_of(case),
        where=_where(name, group, subscription, resource_id, rtype, case.subscription_name if case is not None else ""),
        answers=_answers(kind, state, may_answer, changes_paused, second.stage if second is not None else "", looked is not None and looked.state == REFUSED), found_at=plain(found_at, 30),
        age_days=age, expires_at=plain(plan.expires_at if plan is not None else "", 30),
        models=models_of(case), outcome=_outcome(plan, state, action, decisions), two_people=plan is not None and plan.approval_class == TWO_PEOPLE_CLASS,
        past=past_line(case.learned.get("past")) if kind != "info" and case is not None and isinstance(case.learned, dict) and "past" in case.learned else "",
        access=ACCESS_WORDS.get(str(case.learned.get("access")), "") if kind != "info" and case is not None and isinstance(case.learned, dict) else "",
        unread=unread, options=(options_of(unread, saving.monthly is not None) or gateway_options(found)) if kind == "advice" else (), group=together, gateways=found,
        cost=together.cost if together is not None and together.cost is not None else (_figure(case.cost_usd_30d) if case is not None else None),
        held=bool(changes_paused and may_answer and state == "open" and kind in ("change", "advice")), second=second, ready=looked, refused_before=last_try,
        cost_state=read, scope=scope, made_of=made_of_text(case), estimate=estimate_for(case, read, together), cost_url=cost_url, cost_scope=cost_scope,
        check_first=check_first(case) if kind == "advice" else (), impact=impact_of(case) if kind == "advice" else None)


def order_key(brief: Brief) -> tuple:
    """The order of a list of decisions: the larger saving first (a request with no figure last), then the one that has waited longest."""
    figure = brief.saving.monthly
    return (0 if figure is not None else 1, -(figure or 0.0), -(brief.age_days or 0), brief.plan_id)
