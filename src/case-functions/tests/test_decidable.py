"""A request that a person cannot decide is a defect.

Every kind of request that Meternaut can ask (advice of the investigation, Azure Advisor's own recommendation, each of the older checks, each family of change) is built from the test fakes (invented
names, no network) and shown three ways: the page of the request, the Teams card and the approval letter. Each is read as a person reads it (the Reader of test_words: the Details are left out, and
so is every quote of an AI or of the estate) and must say six things in its own words:

  a. what it is about: the name of the thing and what kind of thing it is;
  b. the finding: why it is a lead, in a fixed phrase of code, with a fact that was measured, or as what Azure Advisor says, and never only that it is "worth a closer look";
  c. what is asked of the person, in one sentence ("You are asked whether ...");
  d. what it saves a year and what that rests on, in plain words (a request without a figure is a defect, and none is asked: brief.why_not_ask);
  e. what was not checked, where the figure rests on an assumption, an estimate or a list price;
  f. that nothing changes in Azure, or what exactly changes.

A kind that cannot meet a question is not hidden: GAPS names it, with the reason, and the test fails when a gap closes (remove it) and when a new one opens. Each question is shown to catch its fault
by a mutation: the sentence is taken out of what a person reads, and the question then fails.
"""
from __future__ import annotations

import dataclasses
import re
import unittest
from types import SimpleNamespace
from typing import Callable
from unittest import mock

import familysupport as fs
import support  # noqa: F401  (puts the app on the path)
from test_families_briefs import MAKERS, console_of, made
from test_letters import word_count
from test_web_support import NOW, SUB, TINO, VM, Console, at, make_advice, make_advice_case, make_case, make_plan, priced_facts

from cases import brief as brief_mod
from cases import cards, detectors, letters, pricing
from cases.models import GROUP_FACT, DecisionRecord
from test_words import (BASE, CONTACTS, PERSON, Block, Rendered, _ai_account, _ai_plan, _firewall, _group_finding, _letter, _machine_plan, _page, _priced_machine, _stop_machine,
                        blocks_of_card, blocks_of_html)

SURFACES = ("page", "card", "letter")
THE_SIX = {  # the older checks of Meternaut: the kind of resource that each finds, a name and a resource group, all invented
    "orphan-managed-disk": ("microsoft.compute/disks", "Microsoft.Compute/disks", "fabrikam-disk-7", "rg-fabrikam-data", "disk"),
    "orphan-public-ip": ("microsoft.network/publicipaddresses", "Microsoft.Network/publicIPAddresses", "fabrikam-ip-3", "rg-fabrikam-net", "public IP address"),
    "load-balancer-without-backends": ("microsoft.network/loadbalancers", "Microsoft.Network/loadBalancers", "fabrikam-lb-2", "rg-fabrikam-net", "load balancer"),
    "empty-app-service-plan": ("microsoft.web/serverfarms", "Microsoft.Web/serverFarms", "fabrikam-plan-5", "rg-fabrikam-web", "App Service plan"),
    "stopped-vm": ("microsoft.compute/virtualmachines", "Microsoft.Compute/virtualMachines", "fabrikam-vm-9", "rg-fabrikam-batch", "virtual machine"),
    "orphan-private-endpoint": ("microsoft.network/privateendpoints", "Microsoft.Network/privateEndpoints", "fabrikam-pe-4", "rg-fabrikam-net", "private endpoint"),
}


@dataclasses.dataclass(frozen=True)
class Kind:
    """One kind of request: its finding and its plan, what it is about (`thing`, `noun`), whether it is a change that Meternaut would make after an approval, and how the page is fetched."""

    name: str
    case: object
    plan: object
    thing: str
    noun: str
    change: bool = False
    console: Callable[[], Console] | None = None
    now: object = NOW
    decisions: tuple = ()
    viewer: str = ""
    verb: str = ""  # what Azure does, for a change, in the words of the sentence that says it: "deletes", "stops", "changes the size of"
    nobody_asked: tuple[str, ...] = ()  # the surfaces on which nobody can act (a person who confirmed already, a request with no second approver), so that nothing is asked on them

    def brief(self):
        return brief_mod.build_brief(self.case, self.plan, None, self.decisions, now=self.now, may_answer=True, viewer=self.viewer)


def setUpModule():
    global _planting
    _planting = fs.as_if_gateways_were_planted()  # the module of the families holds one gateway on the planted list for its tests: so does this one
    _planting.start()


def tearDownModule():
    _planting.stop()


# -- the kinds ------------------------------------------------------------------------------------------------------------------------------------

def _stated(name: str, noun: str, action: str, remains: dict, thing: str, rtype: str, provider: str, group: str = "rg-fabrikam-batch", costs=(360.0, 120.0), n: int = 20) -> Kind:
    """A finding of the investigation that states a change (an action and what remains of the charges that it names), priced by code from invented bill lines: its figure, its basis and its plan."""
    from test_brief import pricing_line, pricing_words

    meters = {f"m{i}": pricing_line("r1", cost, pricing_words(i)) for i, cost in enumerate(costs, 1)}
    box = SimpleNamespace(meters=meters, evidence={"r1": {"properties": {"units": 12}}})
    change = pricing.parse({"action": action, "effects": [{"handle": "r1", "meters": list(meters), "remains": remains}], "how": "A plan of the AI."})
    bill = sum(costs)
    facts = {"basis": "oversized", "proposal": "change", "metrics": {"Percentage CPU": 3.2}, "metricUnits": {"Percentage CPU": "Percent"}, "metricDays": {"Percentage CPU": 30},
             "citedMetrics": 1, pricing.KEY: pricing.digest(change, pricing.price(change, ("r1",), box, {"r1": bill}, None), "r1")}
    saved = pricing.saved(facts, bill)
    assert saved is not None, name
    rid = f"/subscriptions/{SUB}/resourceGroups/{group}/providers/{provider}/{thing}"
    case = make_advice_case(case_id=f"case02{n}", plan_id=f"plan02{n}", resource_id=rid, resource_name=thing, resource_type=rtype, resource_group=group, subscription_name="fabrikam-prod",
                            recommendation="change", confidence=0.88, saving_usd_month=None, cost_usd_30d=bill, cost_state="lines", status="proposed", facts=facts, objections=(),
                            summary="Little of it was used in the last 30 days.", owner={"lookedUp": True, "tagOwner": "batch-team", "tagName": "team"})
    plan = make_advice(plan_id=f"plan02{n}", case_id=f"case02{n}", resource_id=rid, resource_name=thing, resource_group=group, saving_usd_month=saved.low, waiting_costs_usd_day=1.0,
                       created_at=at(days=-3), preconditions={"family": "advise", "caseStatus": "proposed"})
    return Kind(name, case, plan, thing, noun)


def _deleting() -> Kind:
    """Advice to delete an AI services account that nothing called in 30 days (a measured zero), with the saving that the bill gives."""
    facts = {"basis": "no-usage", "proposal": "delete", "metrics": {"Total Calls": 0.0}, "metricUnits": {"Total Calls": "Count"}, "metricDays": {"Total Calls": 30},
             "metricDaysWithData": {"Total Calls": 30}, "citedMetrics": 1}
    case = _ai_account(case_id="case0231", plan_id="plan0231", recommendation="delete", saving_usd_month=848.3, facts=facts, owner={"lookedUp": True, "tagOwner": "platform-team", "tagName": "owner"},
                       status="proposed", confidence=0.9, objections=())
    plan = _ai_plan(plan_id="plan0231", case_id="case0231", saving_usd_month=848.3, waiting_costs_usd_day=28.0, preconditions={"family": "advise", "caseStatus": "proposed"})
    return Kind("advice, delete", case, plan, "fabrikam-ai-weu", "AI services account")


def _group() -> Kind:
    """One request for 50 private endpoints, with the figure that code worked out for them."""
    case, plan = _group_finding()
    facts = {**case.facts, **priced_facts("none", "none"), GROUP_FACT: {**case.facts[GROUP_FACT], "resourceIds": [PE_IDS.format(n) for n in range(2)]}}
    saved = pricing.saved(facts)
    assert saved is not None
    case = dataclasses.replace(case, facts=facts, status="proposed", saving_usd_month=None)
    plan = dataclasses.replace(plan, saving_usd_month=saved.low, preconditions={"family": "advise", "caseStatus": "proposed"})
    return Kind("advice, a group of many resources", case, plan, "50 private endpoints", "private endpoints")


PE_IDS = f"/subscriptions/{SUB}/resourceGroups/rg-fabrikam-net/providers/Microsoft.Network/privateEndpoints/pe-fabrikam-{{}}"


def _gateway(cannot: bool) -> Kind:
    """A finding that proposes to lower a setting of a resource of an invented kind (cases/proposals.py), asked as advice: Meternaut cannot make the change and says why (with two other ways to save),
    or the finding states only the charge that it would take away and Meternaut makes no change for this kind of finding yet."""
    from test_proposal_words import BOTH, gateway

    case, plan = gateway(BOTH, precondition="switch-off") if cannot else gateway(number=2)
    return Kind("advice, a setting that Meternaut cannot change" if cannot else "advice, a gateway with no setting to change", case, plan, "lab-gw-1", "gateway")


def _advisor(commitment: bool, figure: str = "usd") -> Kind:
    """Azure Advisor's own recommendation, made into a request by code (no AI looked at it): a commitment, or a recommendation about one machine. `figure` is what it says it saves: dollars, euros
    (which Meternaut does not turn into dollars) or nothing."""
    currency = "EUR" if figure == "eur" else "USD"
    rows = [["Standard_D2s_v6", 1, "swedencentral", "P1Y" if commitment else "", 400.0, currency, 60, "Single" if commitment else ""]] * 3
    digest = {"type": "84b1a508-0000-4000-8000-000000000001", "sub": "Reservations", "n": 3, "added": 3, "skipped": 0, "currencies": ["EUR"] if figure == "eur" else [],
              "usd": {"usd": 1200.0, "eur": 0.0, "none": None}[figure], "rows": rows, "more": 0, "moreUsd": 0.0}
    rid = f"/subscriptions/{SUB}" if commitment else VM
    problem = "Buy reservations" if commitment else "Right-size or shut down virtual machines that are barely used"
    number = (241 if commitment else 242) + {"usd": 0, "eur": 10, "none": 20}[figure]
    case = make_case(case_id=f"case0{number}", detector="advisor-cost", status="needs_human", saving_usd_month=None, cost_usd_30d=None if commitment else 240.0,
                     models={}, steps=(), recommendation="change", summary="", objections=(), resource_id=rid,
                     resource_type="microsoft.subscriptions/subscriptions" if commitment else "microsoft.compute/virtualmachines", resource_name="" if commitment else "oversized-vm-1",
                     resource_group="" if commitment else "team-apps-rg", facts={"category": "cost", "advisor": digest}, advice={"problem": problem, "solution": problem}, plan_id=f"plan0{number}")
    plan = make_advice(plan_id=f"plan0{number}", case_id=case.case_id, resource_id=rid, resource_name=case.resource_name, resource_group=case.resource_group,
                       saving_usd_month=100.0 if figure == "usd" else None, created_at=at(days=-3), preconditions={"family": "advise", "caseStatus": "needs_human"})
    name = ("Azure Advisor, a commitment" if commitment else "Azure Advisor, one machine") + {"usd": "", "eur": " that it prices in euros", "none": " with no figure"}[figure]
    return Kind(name, case, plan, "Azure Advisor" if commitment else "oversized-vm-1", "subscription" if commitment else "virtual machine")


def _older(detector: str, n: int, cost_read: bool = True) -> Kind:
    """Advice from one of the six older checks (the waste that Meternaut plants itself): the one fact that the check read, and the figure from the bill lines, or, when the bill could not be read,
    none (an older check states its own figure or none, and is asked about either way)."""
    rtype, provider, name, group, noun = THE_SIX[detector]
    rid = f"/subscriptions/{SUB}/resourceGroups/{group}/providers/{provider.split('/')[0]}/{provider.split('/')[1]}/{name}"
    money = dict(saving_usd_month=21.6, cost_usd_30d=21.6, cost_state="lines") if cost_read else dict(saving_usd_month=None, cost_usd_30d=None, cost_state="failed")
    case = make_case(case_id=f"case03{n}", plan_id=f"plan03{n}", detector=detector, resource_id=rid, resource_name=name, resource_type=rtype, resource_group=group, status="proposed",
                     recommendation="delete", facts={"diskState": "unattached"}, subscription_name="fabrikam-prod", owner={"lookedUp": True, "tagOwner": "platform-team", "tagName": "owner"}, **money)
    plan = make_advice(plan_id=f"plan03{n}", case_id=f"case03{n}", resource_id=rid, resource_name=name, resource_group=group, saving_usd_month=money["saving_usd_month"],
                       waiting_costs_usd_day=0.7 if cost_read else None, created_at=at(days=-3), preconditions={"family": "advise", "caseStatus": "proposed"})
    return Kind(f"older check, {detector}" + ("" if cost_read else ", cost not read"), case, plan, name, noun)


METRICS = {"metrics": {"Percentage CPU": 3.2}, "metricUnits": {"Percentage CPU": "Percent"}, "metricDays": {"Percentage CPU": 30}, "metricDaysWithData": {"Percentage CPU": 30}, "citedMetrics": 1}
FINDINGS = {  # what the finding that leads to each family says, as the check of Meternaut or the investigation reads it: the family tests make a finding with no facts at all
    "stop-vm": ("stopped-vm", {}),
    "delete-disk": ("orphan-managed-disk", {"diskState": "unattached"}),
    "delete-public-ip": ("orphan-public-ip", {}),
    "delete-idle-resource": ("investigation", {"basis": "no-usage", "proposal": "delete", **{**METRICS, "metrics": {"Total Calls": 0.0}, "metricUnits": {"Total Calls": "Count"},
                                                                                         "metricDays": {"Total Calls": 30}, "metricDaysWithData": {"Total Calls": 30}}}),
    "resize-vm": ("investigation", {"basis": "oversized", "proposal": "change", **METRICS}),
    "change-disk-tier": ("investigation", {"basis": "low-usage", "proposal": "change", **METRICS}),
    "scale-vpn-gateway": ("investigation", {"basis": "oversized", "proposal": "change", **METRICS}),
}


VERBS = {  # what Azure does in each family, as the sentence says it ("Azure deletes the disk x in resource group y"): the literal words, so that "changes" does not do for a deletion
    "stop-vm": "stops", "delete-disk": "deletes", "delete-public-ip": "deletes", "delete-idle-resource": "deletes", "resize-vm": "changes the size of", "change-disk-tier": "changes the type of",
    "scale-vpn-gateway": "changes the scale units of"}
OTHER_APPROVER = "22222222-2222-2222-2222-222222222222"


def _family(name: str) -> Kind:
    """A change that Meternaut would make after an approval: the request of one family, as the families' own tests make it, with the facts that the finding of that family has."""
    world, plan, case = made(name)
    detector, facts = FINDINGS[name]
    case = dataclasses.replace(case, detector=detector, facts=facts)
    thing = plan.resource_name
    noun = brief_mod.kind_words(case.resource_type)[1]
    return Kind(f"change, {name}", case, plan, thing, noun, change=True, console=lambda: console_of(world, plan, case), now=fs.NOW, verb=VERBS[name])


def _two_people(stage: str) -> Kind:
    """A change that needs two people (class R3), for a person at each stage of it (cases/twopeople.py): the first, who can only confirm it; the second, after somebody else confirmed it, who approves it;
    one who confirmed it already ("mine"); one whose confirmation went stale because the plan changed after it; and the request that has no second approver ("alone"). Nobody can act in the last two of
    these: a letter knows no reader, so it is the page and the card that ask nothing for a person who confirmed already, and the three for a request that nobody can approve."""
    world, plan, case = made("delete-disk")
    plan = dataclasses.replace(plan, approval_class="R3", approvers=(TINO,) if stage == "alone" else (TINO, OTHER_APPROVER), digest="d" * 64)
    world.store.plan_put(plan)
    confirmed = {"second": (OTHER_APPROVER, "Olga", plan.digest), "mine": (TINO, "Tino", plan.digest), "stale": (OTHER_APPROVER, "Olga", "e" * 64)}.get(stage)
    decisions = (DecisionRecord(plan.plan_id, confirmed[0], confirmed[1], "confirm", at(hours=-2), plan.code, plan_digest=confirmed[2]),) if confirmed else ()
    for decision in decisions:
        world.store.decision_put(decision)
    detector, facts = FINDINGS["delete-disk"]
    case = dataclasses.replace(case, detector=detector, facts=facts)
    return Kind(f"change, two people, {stage} stage", case, plan, plan.resource_name, brief_mod.kind_words(case.resource_type)[1], change=True, console=lambda: console_of(world, plan, case),
                now=fs.NOW, decisions=decisions, viewer=TINO, verb=VERBS["delete-disk"],
                nobody_asked={"mine": ("page", "card"), "alone": ("page", "card", "letter")}.get(stage, ()))


def kinds() -> list[Kind]:
    firewall, firewall_plan = _firewall()
    machine = (_priced_machine(), _machine_plan(preconditions={"family": "advise", "caseStatus": "proposed"}))
    found = [Kind("advice, a switch with names", firewall, firewall_plan, "fabrikam-hub-fw", "firewall"),
             Kind("advice, reduce (an assumed share)", *machine, "fabrikam-batch-01", "virtual machine"),
             _stated("advice, reduce (a number that a tool read)", "virtual machine", "reduce", {"form": "ratio", "from": 12, "to": 4, "on": "units"}, "fabrikam-batch-02", "microsoft.compute/virtualmachines",
                     "Microsoft.Compute/virtualMachines", n=21),
             _stated("advice, remove", "storage account", "remove", {"form": "none"}, "fabrikamstore07", "microsoft.storage/storageaccounts", "Microsoft.Storage/storageAccounts", "rg-fabrikam-data", n=22),
             _stated("advice, schedule", "virtual machine", "schedule", {"form": "share_of_days", "days": 5, "of": 7}, "fabrikam-batch-03", "microsoft.compute/virtualmachines",
                     "Microsoft.Compute/virtualMachines", n=23),
             _stated("advice, commit", "virtual machine", "commit", {"form": "assumed", "low": 0.2, "high": 0.3}, "fabrikam-batch-04", "microsoft.compute/virtualmachines",
                     "Microsoft.Compute/virtualMachines", n=24),
             _deleting(), _group(), _gateway(True), _gateway(False), _advisor(True), _advisor(False)]
    found += [_older(detector, n) for n, detector in enumerate(THE_SIX, 1)]
    found += [_older(detector, n + 10, cost_read=False) for n, detector in enumerate(THE_SIX, 1)]
    found += [_family(name) for name in MAKERS]
    found += [_two_people(stage) for stage in ("first", "second", "mine", "stale", "alone")]
    return found


_RENDERED: dict[str, dict[str, Rendered]] = {}


def surfaces(kind: Kind) -> dict[str, Rendered]:
    """The page, the Teams card and the approval letter of one kind, as a person reads them."""
    if kind.name not in _RENDERED:
        console = kind.console() if kind.console is not None else Console()
        if kind.console is None:
            console.store.case_put(kind.case)
            console.store.plan_put(kind.plan)
        reply = console.get(f"/ok/{kind.plan.plan_id}")
        if reply.status != 200:
            raise AssertionError(f"the page of {kind.name} answered {reply.status}")
        brief = kind.brief()
        context = cards.CardContext(page_url=f"{BASE}/ok/{kind.plan.plan_id}", contacts=CONTACTS)
        _RENDERED[kind.name] = {
            "page": Rendered(kind.name, "page", blocks_of_html(reply.text)),
            "card": Rendered(kind.name, "card", blocks_of_card(cards.decision_card(brief, context))),
            "letter": _letter(kind.name, letters.approval_letter(kind.plan, kind.case, PERSON, BASE, kind.now, CONTACTS))}
    return _RENDERED[kind.name]


# -- the six questions ----------------------------------------------------------------------------------------------------------------------------

def seen(shown: Rendered) -> list[Block]:
    """What a person reads of a surface: no Details, no navigation, no chart, and no quote (what an AI or the estate wrote is not what Meternaut says)."""
    return [block for block in shown.blocks if not block.details and block.region != "nav" and block.kind not in ("chart", "quote")]


def text_of(shown: Rendered) -> str:
    return " ".join(block.text for block in seen(shown))


FIXED = tuple({phrase for phrase in (*brief_mod.BASIS_TITLES.values(), *brief_mod.BASIS_WORDS.values(), *(found for state in brief_mod.DETECTOR_STATE.values() for found in (state[1], state[2])))
               if len(phrase.split()) >= 3})  # the reasons that code can say, as phrases and not as single words (a word such as "Stopped" is in sentences that give no reason)
DETECTOR_FACTS = {state[1] for state in brief_mod.DETECTOR_STATE.values()}  # what one of the older checks read, as the value of a row of facts ("Stopped")
MEASURED = re.compile(r"\d[\d,.]*(?:%|\s\w+)? in \d+ days?")  # "2,929 in 30 days", "3.2% in 30 days", "3.2 percent in 30 days": a value that a tool measured, over a period
ADVISOR = re.compile(r"What to look at|Azure Advisor says")  # what Azure Advisor says is the finding: not "a recommendation of Azure Advisor", which is how the sentence of what is asked names it
ASKED = re.compile(r"You are asked (?:whether|to) [^.?!]+[.?!]")
SAVES = re.compile(r"(?:could save|saves) about \$[\d,]+ a year")
RESTS_ON = re.compile(r"bill|assum|estimate|list price|Advisor|Cost Management|proposal|proposes|paid|AI says", re.I)
ASSUMES = re.compile(r"assum|estimate|list price|Advisor|proposal|proposes|AI says|AI's choice|AI's own", re.I)
CHECKED = re.compile(r"did not check(?! the wording)|did not read|has not checked|have not checked|not checked|nobody checked|could not check|cannot check", re.I)  # "did not check the wording" is said of every quote of an AI and answers no question of the figure
NOTHING = re.compile(r"changes? nothing in Azure", re.I)


def what_it_is_about(shown: Rendered, kind: Kind) -> list[str]:
    text = text_of(shown).lower()
    found = [] if kind.thing.lower() in text else [f"it does not name {kind.thing}"]
    return found + ([] if kind.noun.lower() in text else [f"it does not say what kind of thing it is ({kind.noun})"])


def the_finding(shown: Rendered, kind: Kind) -> list[str]:
    for block in seen(without(shown, ASKED)):  # the sentence of what is asked names the thing and says "a closer look", and is not the finding
        low = block.text.lower()
        if (any(phrase.lower() in low for phrase in FIXED) or MEASURED.search(block.text) or ADVISOR.search(block.text)
                or (block.kind == "cell" and block.text.split(". Source:")[0] in DETECTOR_FACTS)):
            return []
    return ["it says that a closer look is worth it, and not why: no reason of code, no measured fact and no word of Azure Advisor"]


def what_is_asked(shown: Rendered, kind: Kind) -> list[str]:
    found = ASKED.findall(text_of(shown))
    if shown.kind in kind.nobody_asked:  # nobody can act here, and a person who cannot act is asked nothing: the lines of the stage say what is true, and this question is not asked of them
        return [] if not found else ["it asks a person who cannot act what to decide"]
    return [] if len(found) == 1 else [f"it asks {len(found)} times what is asked of the person ('You are asked whether ...')"]


def lead_and_basis(shown: Rendered) -> tuple[str, str] | None:
    """The sentence that opens the money and the one under it. The arithmetic of a page (a small table) stands between them, and is no sentence."""
    blocks = [block for block in seen(shown) if block.kind not in ("cell", "label")]
    for index, block in enumerate(blocks):
        if SAVES.search(block.text):
            return block.text, blocks[index + 1].text if index + 1 < len(blocks) else ""
    return None


def what_it_saves(shown: Rendered, kind: Kind) -> list[str]:
    found = lead_and_basis(shown)
    if found is None:
        return ["it states no saving: a request without a figure is a defect, and nobody is asked without one"]
    return [] if RESTS_ON.search(found[1]) else ["it states a saving and does not say what the saving rests on"]


def what_was_not_checked(shown: Rendered, kind: Kind) -> list[str]:
    found = lead_and_basis(shown)
    if found is None or not ASSUMES.search(found[1]):
        return []
    return [] if CHECKED.search(text_of(shown)) else ["the saving rests on an assumption, an estimate or a list price, and nothing says what was not checked"]


def what_changes(shown: Rendered, kind: Kind) -> list[str]:
    text = text_of(shown)
    if kind.change:  # a change says what Azure does to the thing, in a sentence of its own, with the verb of the family ("Azure deletes the disk planted-disk-1 in resource group ..."): "changes" does not do for a deletion
        return [] if re.search(rf"Azure {re.escape(kind.verb)} [^.]*{re.escape(kind.thing)}", text) else ["it does not say what exactly changes in Azure"]
    return [] if NOTHING.search(text) else ["it does not say that nothing changes in Azure"]


QUESTIONS = {"about": what_it_is_about, "finding": the_finding, "asked": what_is_asked, "saves": what_it_saves, "not checked": what_was_not_checked, "changes": what_changes}

# What a kind cannot say yet, and why: (kind, surface, question) -> the reason. A request without a figure is a defect (the kinds in WITHOUT_A_FIGURE are not asked at all).
GAPS: dict[tuple[str, str, str], str] = {
    (name, surface, "saves"): reason for name, reason in {
        "change, change-disk-tier": "the family cannot price a change of tier: it reads no price list, so the request asks for an approval and states no saving, which is a defect of the family (a person is told what it costs, and that nothing is claimed)",
        **{f"older check, {detector}, cost not read": "the bill could not be read, and an older check states its own figure or none: the request is still asked, says that Meternaut could not read what the resource costs and states no saving, "
                                                      "because the rule that a request which states no saving is not asked is not applied to the older checks yet" for detector in THE_SIX},
    }.items() for surface in SURFACES}


def problems_of(kind: Kind) -> dict[tuple[str, str, str], list[str]]:
    found = {}
    for surface, shown in surfaces(kind).items():
        for name, ask in QUESTIONS.items():
            said = ask(shown, kind)
            if said:
                found[(kind.name, surface, name)] = said
    return found


class EveryRequestCanBeDecided(unittest.TestCase):
    """Each kind of request, on the page, in the card and in the letter, answers the six questions, except what GAPS names."""

    def test_every_kind_is_built_and_there_are_many(self):
        found = kinds()
        self.assertGreaterEqual(len(found), 34, "38 before the four kinds of Azure Advisor that state no figure left: they are not asked about now (advisor_without_a_figure)")
        self.assertEqual(len({kind.name for kind in found}), len(found), "a name for each kind")
        self.assertEqual({kind.plan.family for kind in found if kind.change}, set(MAKERS), "every family of change is a kind")

    def test_every_older_check_of_meternaut_is_a_kind_here_with_a_bill_that_was_read_and_with_one_that_was_not(self):
        self.assertEqual({detector.name for detector in detectors.DETECTORS}, set(THE_SIX), "a new check of Meternaut needs its kind here")
        built = [kind.name.split(", ")[1] for kind in kinds() if kind.name.startswith("older check")]
        self.assertEqual(sorted(built), sorted(list(THE_SIX) * 2))

    def test_what_a_person_cannot_read_is_named_and_nothing_else_is_missing(self):
        missing = {}
        for kind in kinds():
            missing.update(problems_of(kind))
        self.assertEqual(sorted(missing), sorted(GAPS), "\n".join(f"{key}: {said}" for key, said in sorted(missing.items())))

    def test_a_gap_is_a_kind_that_exists_with_a_reason_that_is_said(self):
        names = {kind.name for kind in kinds()}
        for (name, surface, question), reason in GAPS.items():
            self.assertIn(name, names)
            self.assertIn(surface, SURFACES)
            self.assertIn(question, QUESTIONS)
            self.assertGreater(len(reason.split()), 8, "the reason is said in words")


def without_a_figure() -> list[Kind]:
    """Findings that state no saving: what the finding costs and nothing that code worked out. The owner read the request that Meternaut made for the first of them."""
    machine = _priced_machine(saving_usd_month=None, facts={"basis": "oversized", "proposal": "change", "metrics": {}}, status="needs_human")
    group, group_plan = _group_finding()
    return [Kind("an AI services account that costs money", _ai_account(), _ai_plan(), "fabrikam-ai-weu", "AI services account"),
            Kind("a machine whose change the AI did not state", machine, _machine_plan(saving_usd_month=None), "fabrikam-batch-01", "virtual machine"),
            Kind("50 private endpoints with no saving", group, group_plan, "50 private endpoints", "private endpoints")]


def advisor_without_a_figure() -> list[Kind]:
    """Azure Advisor's own recommendations that give no saving in dollars, for a commitment and for one machine: the figure is in euros (which Meternaut does not turn into dollars) or there is none. They
    were named as gaps of this test while the rule of asking did not reach Advisor, and were asked about all the same, stating no saving. Now brief.why_not_ask holds them back (NO_FIGURE), so they are
    no request that a person can fail to decide."""
    return [_advisor(commitment, figure) for commitment in (True, False) for figure in ("eur", "none")]


class NobodyIsAskedWithoutAFigure(unittest.TestCase):
    """A request without a figure is a defect: the rules of asking hold such a finding back, and the page that it would have had fails the question of what it saves."""

    def test_the_rules_of_asking_do_not_ask_about_a_finding_that_states_no_saving(self):
        for kind in without_a_figure():
            with self.subTest(kind.name):
                self.assertEqual(brief_mod.why_not_ask(kind.case), brief_mod.UNPRICED)

    def test_the_rules_of_asking_do_not_ask_about_a_recommendation_of_azure_advisor_that_counts_no_saving_in_dollars(self):
        for kind in advisor_without_a_figure():
            with self.subTest(kind.name):
                self.assertEqual(brief_mod.why_not_ask(kind.case), brief_mod.NO_FIGURE)

    def test_the_request_that_would_be_made_anyway_fails_the_question_of_what_it_saves_on_every_surface(self):
        for kind in without_a_figure() + advisor_without_a_figure():
            for surface, shown in surfaces(kind).items():
                with self.subTest(kind.name, surface=surface):
                    self.assertEqual(what_it_saves(shown, kind), ["it states no saving: a request without a figure is a defect, and nobody is asked without one"])


# -- a check that held the finding back -------------------------------------------------------------------------------------------------------------

class AFindingThatACheckHeldBackSaysWhichCheck(unittest.TestCase):
    """A management lock, a tag that asks to keep the resource and a resource that is less than 7 days old are part of why a finding is held: the card and the letter say which, as a row of their own,
    and not only in the line about how sure Meternaut is."""

    GUARDS = {"locked": "A management lock covers the resource.", "keep-tag": "A tag asks to keep the resource.", "too-new": "The resource is less than 7 days old."}

    @staticmethod
    def shown(guard: str) -> tuple[list[dict], str]:
        kind = _deleting()
        case = dataclasses.replace(kind.case, guards=(guard,))
        brief = brief_mod.build_brief(case, kind.plan, None, (), now=kind.now, may_answer=True)
        card = cards.decision_card(brief, cards.CardContext(page_url=f"{BASE}/ok/{kind.plan.plan_id}", contacts=CONTACTS))
        rows = next(block for block in card["body"] if block.get("id") == "facts")["facts"]
        return rows, letters.approval_letter(kind.plan, case, PERSON, BASE, kind.now, CONTACTS).text

    def test_the_card_and_the_letter_have_a_row_that_says_which_check_held_the_finding_back(self):
        for guard, said in self.GUARDS.items():
            with self.subTest(guard):
                rows, letter = self.shown(guard)
                self.assertEqual([row["value"].split(". Source")[0] for row in rows if row["title"] == "Held back by"], [said.rstrip(".")])
                self.assertIn(said, letter)

    def test_the_old_choice_of_three_rows_leaves_the_row_out_of_both(self):
        def old(facts, most=3):  # what the choice was before: the facts that say why the finding is a lead first, in their order, and the check that held it back fourth
            why = {"What the investigation found", "What to look at", *(state[0] for state in brief_mod.DETECTOR_STATE.values())}
            return tuple(sorted(facts, key=lambda fact: not (fact.label in why or fact.source.startswith("Azure Monitor"))))[:most]

        with mock.patch.object(brief_mod, "shown_facts", old), mock.patch.object(cards, "shown_facts", old):
            for guard, said in self.GUARDS.items():
                with self.subTest(guard):
                    rows, letter = self.shown(guard)
                    self.assertEqual([row for row in rows if row["title"] == "Held back by"], [])
                    self.assertNotIn(said, letter)


# -- the words of the letter --------------------------------------------------------------------------------------------------------------------------

MAIN_WORDS = {  # what the approval letter of each kind measured on main (f84596a, 2026-11-19), counted as tests/test_letters.py counts: the budget of 175 words is for the one kind that that file builds
    "advice, a switch with names": 232, "advice, reduce (an assumed share)": 220, "advice, reduce (a number that a tool read)": 201, "advice, remove": 183, "advice, schedule": 201,
    "advice, commit": 220, "advice, delete": 191, "advice, a group of many resources": 170, "Azure Advisor, a commitment": 213, "Azure Advisor, one machine": 196,
    "older check, orphan-managed-disk": 175, "older check, orphan-public-ip": 176, "older check, load-balancer-without-backends": 176, "older check, empty-app-service-plan": 178,
    "older check, stopped-vm": 170, "older check, orphan-private-endpoint": 170, "change, stop-vm": 210, "change, resize-vm": 219, "change, change-disk-tier": 211, "change, delete-disk": 152,
    "change, delete-public-ip": 156, "change, delete-idle-resource": 167, "change, scale-vpn-gateway": 242,
    "older check, orphan-managed-disk, cost not read": 164, "older check, orphan-public-ip, cost not read": 165, "older check, load-balancer-without-backends, cost not read": 165,
    "older check, empty-app-service-plan, cost not read": 167, "older check, stopped-vm, cost not read": 159, "older check, orphan-private-endpoint, cost not read": 159,
    "change, two people, first stage": 165, "change, two people, second stage": 165, "change, two people, mine stage": 165,
    "change, two people, stale stage": 165, "change, two people, alone stage": 165,
    "advice, a setting that Meternaut cannot change": 268, "advice, a gateway with no setting to change": 267}  # the two kinds of the invented gateway are new (20 November 2026), so their size is the one that they have: 276 and 265 when they were added, and 268 and 267 after the paragraph under the figure was made shorter and the answer said that the AI named no setting; the four kinds of Azure Advisor with no figure are no kinds here: nobody is asked about them, so there is no letter to hold to a size
ASKS_WHAT_IT_DOES = "the sentence of what is asked names what Meternaut would do (whether to let Meternaut make this change) in the place of whether to approve this change"
RATE_AND_NO_SETTING = "the figure says which rate the cost is, and what an answer does says that the AI named no setting that Meternaut could check"
NOT_KNOWN_FIRST = "what could go wrong says what was measured of the use of the resource and that it does not show what depends on it"
RATE_AND_ONLY_COUNT = "the figure says which rate the cost is, and what an answer does says that Meternaut cannot make a commitment because it only lowers a count of units"
GREW = {  # the kinds whose letter is longer than it was on main, by how many words, and for which sentence that a person needs to decide
    "advice, a switch with names": (14, "the figure says which rate the cost is, what could go wrong says that other resources can depend on a firewall and that nothing was measured of its use, and what an answer does says that Meternaut cannot make a switch because it only lowers a count of units"),
    "advice, reduce (an assumed share)": (11, f"{RATE_AND_NO_SETTING}, and {NOT_KNOWN_FIRST}"),
    "advice, reduce (a number that a tool read)": (44, f"the figure says what the bill shows, what the AI says that the change does to it and which number Meternaut checked, and which kind of resource it is about; what an answer does says that the AI named no setting that Meternaut could check, and {NOT_KNOWN_FIRST}"),
    "advice, remove": (7, f"the title and the question say that part of it is removed, what an answer does says that Meternaut cannot make a removal because it only lowers a count of units, and {NOT_KNOWN_FIRST}"),
    "advice, schedule": (41, f"the figure says which kind of resource it is about, which rate the cost is, on how many days of how many the change turns the resource off and which numbers are the AI's; what an answer does says that Meternaut cannot make a schedule because it only lowers a count of units, and {NOT_KNOWN_FIRST}"),
    "advice, commit": (4, RATE_AND_ONLY_COUNT),
    "advice, a group of many resources": (24, "the row that says why the finding is a lead, which rate the cost is, and what could go wrong says why the risk is high and that nothing was measured of their use"),
    "change, stop-vm": (15, f"{ASKS_WHAT_IT_DOES}, and the Undo row says all of the undo of the family (a start can fail when the region has no room for the size), which it cut in the middle of a word"), "change, resize-vm": (6, ASKS_WHAT_IT_DOES), "change, change-disk-tier": (7, ASKS_WHAT_IT_DOES), "change, delete-disk": (7, ASKS_WHAT_IT_DOES),
    "change, delete-public-ip": (9, ASKS_WHAT_IT_DOES), "change, two people, first stage": (9, ASKS_WHAT_IT_DOES),
    "change, two people, second stage": (9, ASKS_WHAT_IT_DOES), "change, two people, mine stage": (9, ASKS_WHAT_IT_DOES), "change, two people, stale stage": (9, ASKS_WHAT_IT_DOES),
    "advice, a setting that Meternaut cannot change": (19, f"the sentence about the other ways says how each figure was made: worked out from the bill, the AI's estimate or not priced; {NOT_KNOWN_FIRST}"),
    "advice, a gateway with no setting to change": (8, f"what an answer does says that the AI named no setting that Meternaut could check, and {NOT_KNOWN_FIRST}")}


class AMeasurementSaysOnHowManyDaysItHadAValueOnlyWhenNotEveryDayDid(unittest.TestCase):
    """A zero that a tool measured over 30 days needs a value on only 20 of them, so a letter that says "0 in 30 days" says more than was measured: it says the days when they are fewer than the period."""

    @staticmethod
    def row(days_with_a_value: int) -> str:
        kind = _deleting()
        case = dataclasses.replace(kind.case, facts={**kind.case.facts, "metricDaysWithData": {"Total Calls": days_with_a_value}})
        text = letters.approval_letter(kind.plan, case, PERSON, BASE, kind.now, CONTACTS).text
        return next(line for line in text.splitlines() if line.startswith("Total Calls"))

    def test_the_days_are_said_when_they_are_fewer_and_not_when_every_day_had_a_value(self):
        self.assertEqual(self.row(30), "Total Calls: 0 in 30 days")
        self.assertEqual(self.row(20), "Total Calls: 0 in 30 days, 20 of them with a value")

    def test_a_letter_that_always_leaves_them_out_says_a_zero_of_30_days_for_a_zero_of_20(self):
        with mock.patch.object(letters, "_read", lambda value: value.partition(", with a value")[0]):  # what it said before
            self.assertEqual(self.row(20), "Total Calls: 0 in 30 days")


class TheFirstOfTwoPeopleIsAskedToConfirmAndTheSecondToApprove(unittest.TestCase):
    """The first of the two people who approve a change can only confirm it, and a person who confirmed already or a request that nobody can approve asks nothing: nobody can act there."""

    WHAT = "delete the unattached disk planted-disk-1 in group meternaut-fam-rg"  # what Meternaut would do, in the words of the title
    CONFIRM = f"You are asked whether to confirm that Meternaut may {WHAT}."
    APPROVE = f"You are asked whether to let Meternaut {WHAT}."

    def test_the_first_and_a_person_whose_confirmation_went_stale_are_asked_to_confirm_on_the_page_the_card_and_the_letter(self):
        for stage in ("first", "stale"):
            kind = a_kind(f"change, two people, {stage} stage")
            for surface, shown in surfaces(kind).items():
                with self.subTest(stage, surface=surface):
                    self.assertIn(self.CONFIRM, text_of(shown))
                    self.assertNotIn(self.APPROVE, text_of(shown))

    def test_the_second_is_asked_to_approve_on_the_page_and_the_card(self):
        kind = a_kind("change, two people, second stage")
        for surface in ("page", "card"):
            with self.subTest(surface):
                text = text_of(surfaces(kind)[surface])
                self.assertIn(self.APPROVE, text)
                self.assertNotIn("to confirm that Meternaut may", text)

    def test_a_person_who_cannot_act_is_asked_nothing_and_the_lines_of_the_stage_say_what_is_true(self):
        for stage, says in (("mine", "You confirmed the request"), ("alone", "so nobody can approve it")):
            kind = a_kind(f"change, two people, {stage} stage")
            for surface in ("page", "card"):
                with self.subTest(stage, surface=surface):
                    self.assertIn(says, text_of(surfaces(kind)[surface]))
            for surface in kind.nobody_asked:
                with self.subTest(stage, nobody_asked=surface):
                    self.assertEqual(ASKED.findall(text_of(surfaces(kind)[surface])), [])
                    self.assertEqual(what_is_asked(surfaces(kind)[surface], kind), [], "the question of what is asked is not asked of a surface where nobody can act: it must ask nothing")

    def test_the_sentence_of_each_stage_is_made_in_one_place_and_without_it_a_person_who_cannot_act_is_asked_to_approve(self):
        for stage in ("mine", "alone"):
            kind = a_kind(f"change, two people, {stage} stage")
            _RENDERED.pop(kind.name, None)
            try:
                with mock.patch.object(brief_mod, "ASKED_BY_STAGE", {}):
                    for surface in kind.nobody_asked:
                        with self.subTest(stage, surface=surface):
                            self.assertEqual(what_is_asked(surfaces(kind)[surface], kind), ["it asks a person who cannot act what to decide"])
            finally:
                _RENDERED.pop(kind.name, None)

    def test_the_sentence_is_made_in_one_place_and_without_it_the_three_surfaces_ask_nothing(self):
        kind = a_kind("change, two people, first stage")
        _RENDERED.pop(kind.name, None)
        try:
            with mock.patch.object(brief_mod, "ASKED_BY_STAGE", {**brief_mod.ASKED_BY_STAGE, "first": ""}):
                for surface, shown in surfaces(kind).items():
                    with self.subTest(surface):
                        self.assertTrue(what_is_asked(shown, kind))
        finally:
            _RENDERED.pop(kind.name, None)

    def test_the_reminder_of_the_ladder_is_built_without_the_decisions_so_it_asks_nothing_of_a_change_of_two_people(self):
        for stage in ("first", "second", "mine"):
            kind = a_kind(f"change, two people, {stage} stage")
            with self.subTest(stage):
                text = letters.escalation_letter(kind.plan, kind.case, PERSON, BASE, kind.now, CONTACTS, source="same").text
                self.assertNotIn("You are asked", text, "it cannot know whether its reader confirmed already: 'confirm' would be false for the second person and for the one who confirmed")

    def test_the_reminder_of_a_change_for_one_person_still_says_what_is_asked(self):
        kind = a_kind("change, delete-disk")
        text = letters.escalation_letter(kind.plan, kind.case, PERSON, BASE, kind.now, CONTACTS, source="same").text
        self.assertIn(self.APPROVE, text)


class TheApprovalLettersDoNotGrowWithoutSayingSo(unittest.TestCase):
    """A letter is read once, in a minute: no kind of approval letter is longer than it was on main, except by the words that GREW names, each for the sentence that a person needs to decide. The other
    kinds got shorter by the words of the footer, the days that a measurement had a value and the second line that said that a deletion cannot be undone."""

    @staticmethod
    def words(kind: Kind) -> int:
        return word_count(letters.approval_letter(kind.plan, kind.case, PERSON, BASE, kind.now, CONTACTS))

    def test_every_kind_has_its_own_size_on_main_and_no_letter_is_longer_than_that_except_by_the_words_that_are_named(self):
        self.assertEqual(set(MAIN_WORDS), {kind.name for kind in kinds()}, "a kind is measured on main when it is added, and is held to its own size and not to that of another kind")
        for kind in kinds():
            with self.subTest(kind.name):
                self.assertLessEqual(self.words(kind), MAIN_WORDS[kind.name] + GREW.get(kind.name, (0, ""))[0])

    def test_what_is_named_as_grown_has_grown_by_no_more_than_it_says_and_says_why(self):
        for name, (extra, why) in GREW.items():
            with self.subTest(name):
                words = self.words(a_kind(name))
                self.assertGreater(words, MAIN_WORDS[name], "it did not grow: remove it from GREW")
                self.assertLessEqual(words, MAIN_WORDS[name] + extra)
                self.assertGreater(len(why.split()), 5)


# -- the mutations --------------------------------------------------------------------------------------------------------------------------------

SENTENCE = re.compile(r"(?<=[.?!])\s+(?=[\"“(]?[A-Z0-9$])")


def without(shown: Rendered, pattern: re.Pattern | str) -> Rendered:
    """What a person reads when every sentence that matches is taken out; a block with no sentence left is gone."""
    pattern = re.compile(pattern, re.IGNORECASE) if isinstance(pattern, str) else pattern
    blocks = []
    for block in shown.blocks:
        kept = " ".join(part for part in SENTENCE.split(block.text) if not pattern.search(part))
        if kept:
            blocks.append(dataclasses.replace(block, text=kept, raw=kept))
    return dataclasses.replace(shown, blocks=tuple(blocks))


def a_kind(name: str) -> Kind:
    return next(kind for kind in kinds() if kind.name == name)


def reworded(shown: Rendered, old: str, new: str) -> Rendered:
    """What a person reads when `old` is said as `new`."""
    return dataclasses.replace(shown, blocks=tuple(dataclasses.replace(block, text=block.text.replace(old, new), raw=block.raw.replace(old, new)) for block in shown.blocks))


class EachQuestionCatchesItsFault(unittest.TestCase):
    """A sentence that answers a question is taken out of what a person reads, and the question then fails on the page, the card and the letter; with the sentence, it passes."""

    MACHINE = "advice, reduce (an assumed share)"  # a figure that rests on the AI's own assumption: all six questions apply
    DISK = "change, delete-disk"

    def shown(self, name: str, surface: str) -> tuple[Kind, Rendered]:
        kind = a_kind(name)
        return kind, surfaces(kind)[surface]

    def fails(self, name: str, question: str, mutation: re.Pattern | str):
        for surface in SURFACES:
            with self.subTest(question, surface=surface):
                kind, shown = self.shown(name, surface)
                self.assertEqual([], QUESTIONS[question](shown, kind), "it passes with the sentence")
                self.assertTrue(QUESTIONS[question](without(shown, mutation), kind), "and fails without it")

    def test_what_it_is_about(self):
        kind = a_kind(self.MACHINE)
        self.fails(self.MACHINE, "about", re.escape(kind.thing))
        self.fails(self.MACHINE, "about", re.escape(kind.noun))

    def test_the_finding(self):
        self.fails(self.MACHINE, "finding", r"Larger than its use needs|3\.2% in 30 days")
        self.fails("Azure Advisor, one machine", "finding", r"What to look at|Azure Advisor says")  # the sentence of what is asked names Azure Advisor too, and is not the finding

    def test_what_is_asked(self):
        self.fails(self.MACHINE, "asked", ASKED)
        self.fails(self.DISK, "asked", ASKED)

    def test_what_it_saves(self):
        self.fails(self.MACHINE, "saves", SAVES)
        self.fails(self.MACHINE, "saves", RESTS_ON)

    def test_what_was_not_checked(self):
        self.fails(self.MACHINE, "not checked", "That is the AI's own assumption, and Meternaut did not check it")  # the caption of a quote ("Meternaut did not check the wording.") is no answer
        self.fails("Azure Advisor, one machine", "not checked", "did not check that what it covers will keep running|did not check Advisor's estimate")

    def test_what_changes(self):
        self.fails(self.MACHINE, "changes", NOTHING)
        self.fails(self.DISK, "changes", "Azure deletes the disk planted-disk-1")

    def test_what_changes_needs_the_verb_of_the_family_and_not_any_verb(self):
        kind = a_kind(self.DISK)
        for surface, shown in surfaces(kind).items():
            with self.subTest(surface):
                self.assertEqual([], what_changes(shown, kind))
                self.assertTrue(what_changes(reworded(shown, "Azure deletes the disk", "Azure changes the disk"), kind), "a deletion that is said as a change is not what changes")

    def test_a_sentence_that_is_taken_out_of_the_code_is_taken_out_of_the_three_surfaces(self):
        # The sentence of what is asked is made in one place (brief.ASKED for advice, brief.ASKED_CHANGE for a change): empty it, and the page, the card and the letter all fail.
        for name, constant in ((self.MACHINE, "ASKED"), (self.DISK, "ASKED_CHANGE")):
            kind = a_kind(name)
            _RENDERED.pop(kind.name, None)
            try:
                with mock.patch.object(brief_mod, constant, ""):
                    for surface, shown in surfaces(kind).items():
                        with self.subTest(name, surface=surface):
                            self.assertTrue(what_is_asked(shown, kind), f"{surface} still says what is asked")
            finally:
                _RENDERED.pop(kind.name, None)
