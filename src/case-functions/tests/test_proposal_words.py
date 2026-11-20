"""The words of a finding that proposes a change: what exactly changes, what it is worth and how that was worked out, what happens when a person answers (for each kind of request), and the
other ways to save on the same resource.

Every case is invented: a kind of resource that does not exist (`microsoft.example/gateways`, one gateway `lab-gw-1` with a property `capacityUnits`), built from the test fakes with no network. The owner
read the one request that Meternaut made about a real gateway of this shape word by word and found nothing in it: "reducing the resource", a stock sentence about traffic, and an AI's proposal
that "Meternaut did not check". These tests hold the page, the Teams card and the letter to what a person needs instead, and each key test is shown to fail when its behaviour is taken out.
"""
from __future__ import annotations

import dataclasses
import datetime as dt
import re
import unittest
from types import SimpleNamespace
from unittest import mock

import support  # noqa: F401  (puts the app on the path)
from test_web_support import NOW, SUB, Console, at, make_advice, make_advice_case, make_decision, make_plan
from test_words import BASE, CONTACTS, PERSON, Rendered, _letter, _page, blocks_of_card, blocks_of_html, problems

from cases import brief as brief_mod
from cases import cards, letters, pricing, proposals
from cases.meters import Meter
from cases.models import GROUP_FACT

START = dt.date(2026, 10, 5)
GROUP = "rg-lab"
TYPE = "microsoft.example/gateways"
GATEWAY = f"/subscriptions/{SUB}/resourceGroups/{GROUP}/providers/Microsoft.Example/gateways/lab-gw-1"
EXTRA_UNITS = ("Example Gateways", "Standard Tier", "Extra Unit", "OnDemand", "Usage", "1 Hour")
BASE_GATEWAY = ("Example Gateways", "Standard Tier", "Base Gateway", "OnDemand", "Usage", "1 Hour")
SET = [{"path": "capacityUnits", "from": 4, "to": 2}]
OTHERS = [{"title": "Move to the Lite tier", "givesUp": "Lite is shared and carries no uptime promise.", "action": "switch", "inPlace": False, "lowUsd": 150.0, "highUsd": 201.6},
          {"title": "Remove the gateway", "givesUp": "Everything that connects through it stops.", "action": "remove"}]
HOW = "Lower capacity units from 4 to 2 in the Azure portal."
DOUBT = "A weekly maintenance job may connect through it."
OWNER_HATED = ("reducing the resource", "Consider reducing", "Traffic that you cannot see from here may depend on it.", "If you act, what depends on it can slow down or stop.",
               "Meternaut changes nothing in Azure. Your answer is recorded with your name.", "That is the AI's own proposal, and Meternaut did not check it.")


def _meter(words: tuple, hours: float, usd: float) -> Meter:
    return Meter("r1", None, words, hours, usd, {START + dt.timedelta(days=n): usd / 30 for n in range(30)}, None, START, 30)


def gateway_facts(action: str = "reduce", remains: dict | None = None, proposal: dict | None = None, **more) -> dict:
    """The facts of the finding: nobody connected in 30 days, and the charge of the extra units (1,440 hours at 0.14 an hour: 201.60 a month) that the AI would take away, priced by code from invented lines
    of a resource that costs 411 in all."""
    remains = remains or {"form": "quantity", "from": 1440, "to": 0}
    box = SimpleNamespace(meters={"m1": _meter(EXTRA_UNITS, 1440.0, 201.6), "m2": _meter(BASE_GATEWAY, 720.0, 209.4)}, evidence={"r1": {"properties": {"capacityUnits": 4}}})
    change = pricing.parse({"action": action, "effects": [{"handle": "r1", "meters": ["m1"], "remains": remains}], "how": HOW})
    facts = {"basis": "no-usage", "metrics": {"Sessions": 0.0}, "metricUnits": {"Sessions": "Count"}, "metricDays": {"Sessions": 30}, "metricDaysWithData": {"Sessions": 30}, "citedMetrics": 1,
             pricing.KEY: pricing.digest(change, pricing.price(change, ("r1",), box, {"r1": 411.0}, None, lambda text: text), "r1"), **more}
    return {**facts, **({proposals.KEY: proposal} if proposal else {})}


def gateway(proposal: dict | None = None, precondition: str = "", number: int = 1, **changes):
    """The finding about the gateway and the request that asks a person about it (advice: Meternaut makes no change for this kind of finding)."""
    facts = changes.pop("facts", None) or gateway_facts(proposal=proposal)
    ident = f"case05{number:02d}"
    case = make_advice_case(case_id=ident, plan_id=f"plan05{number:02d}", resource_id=GATEWAY, resource_name="lab-gw-1", resource_type=TYPE, resource_group=GROUP, subscription_name="fabrikam-prod",
                            recommendation="change", confidence=0.88, saving_usd_month=None, cost_usd_30d=411.0, cost_state="lines", status="proposed", facts=facts, objections=(DOUBT,),
                            summary="Nobody connected in the last 30 days.", learned={"skeptic": "agree"}, owner={"lookedUp": True, "tagOwner": "lab-team", "tagName": "team"})
    case = dataclasses.replace(case, **changes) if changes else case
    held = {proposals.CANNOT_KEY: precondition} if precondition else {}
    plan = make_advice(plan_id=f"plan05{number:02d}", case_id=ident, resource_id=GATEWAY, resource_name="lab-gw-1", resource_group=GROUP, saving_usd_month=201.6, waiting_costs_usd_day=6.72,
                       created_at=at(days=-3), preconditions={"family": "advise", "caseStatus": "proposed", **held})
    return case, plan


def a_change(number: int = 9):
    """A request that Meternaut would make itself, of a family that does not exist: its words are the plan's own, written by code."""
    case, _ = gateway(SETTING, number=number)
    plan = make_plan(plan_id=f"plan05{number:02d}", case_id=case.case_id, family="scale-lite", resource_id=GATEWAY, resource_name="lab-gw-1", resource_group=GROUP, saving_usd_month=201.6,
                     title="Lower capacity units of the gateway lab-gw-1 from 4 to 2 in group rg-lab", created_at=at(days=-3),
                     what_changes="When you approve, Azure lowers capacity units of the gateway lab-gw-1 in resource group rg-lab from 4 to 2.",
                     could_go_wrong="Connections that need more than 2 units are refused.", undo="Set capacity units back to 4 in the Azure portal.",
                     preconditions={"family": "scale-lite", "resourceType": TYPE})
    return case, plan


SETTING = {"set": SET}
BOTH = {"set": SET, "others": OTHERS}


def brief_of(case, plan, **more):
    return brief_mod.build_brief(case, plan, None, (), now=NOW, may_answer=True, **more)


def card_of(case, plan) -> dict:
    return cards.decision_card(brief_of(case, plan), cards.CardContext(page_url=f"{BASE}/ok/{plan.plan_id}", contacts=CONTACTS))


def surfaces(case, plan) -> dict[str, Rendered]:
    """The page, the Teams card and the letter of one request, as a person reads them."""
    return {"page": _page("page", case, plan), "card": Rendered("card", "card", blocks_of_card(card_of(case, plan))),
            "letter": _letter("letter", letters.approval_letter(plan, case, PERSON, BASE, NOW, CONTACTS))}


def read(shown: Rendered) -> str:
    """What a person reads: everything but the Details, the navigation and the quotes (what an AI wrote is not what Meternaut says)."""
    return " ".join(block.text for block in shown.blocks if not block.details and block.region != "nav" and block.kind != "quote")


def quotes(shown: Rendered) -> list[str]:
    return [block.text for block in shown.blocks if block.kind == "quote"]


def title_of(shown: Rendered) -> str:
    return next(block.text for block in shown.blocks if block.kind == "heading")


class TheKindOfAResourceInWords(unittest.TestCase):
    """A kind that the brief has no words for is said in the words of the type segment of its id: "bastionHosts" is a bastion host, and never "the resource" when the id says better."""

    def test_a_kind_without_words_is_said_in_words_of_the_type_segment_of_its_id(self):
        for segment, label, noun in (("labGateways", "Lab gateway", "lab gateway"), ("edgeProxies", "Edge proxy", "edge proxy"), ("portalAddresses", "Portal address", "portal address"),
                                     ("serviceClasses", "Service class", "service class"), ("gateways", "Gateway", "gateway"), ("bastionHosts", "Bastion host", "bastion host"),
                                     ("networkAccess", "Network access", "network access"), ("redis", "Redis", "redis"), ("sshKeys", "Ssh key", "ssh key"),
                                     ("trafficRoutes", "Traffic route", "traffic route")):
            rid = f"/subscriptions/{SUB}/resourceGroups/rg-a/providers/Microsoft.Example/{segment}/x-1"
            with self.subTest(segment):
                self.assertEqual(brief_mod.kind_words(f"microsoft.example/{segment.lower()}", rid), (label, noun))

    def test_a_kind_that_the_brief_knows_keeps_its_words_and_one_that_the_id_cannot_say_is_still_a_resource(self):
        disk = f"/subscriptions/{SUB}/resourceGroups/rg-a/providers/Microsoft.Compute/disks/d-1"
        self.assertEqual(brief_mod.kind_words("microsoft.compute/disks", disk), ("Managed disk", "disk"))
        self.assertEqual(brief_mod.kind_words("microsoft.example/things"), ("microsoft.example/things", "resource"), "no id: nothing says better")
        self.assertEqual(brief_mod.kind_words("microsoft.example/things", disk), ("microsoft.example/things", "resource"), "the id is that of another kind")
        self.assertEqual(brief_mod.kind_words("microsoft.example/things", "/subscriptions/x/resourceGroups/rg-a/providers/Microsoft.Example/th1ngs!/x"), ("microsoft.example/things", "resource"))

    def test_the_page_the_card_and_the_letter_name_the_kind_of_the_gateway(self):
        case, plan = gateway()
        for surface, shown in surfaces(case, plan).items():
            with self.subTest(surface):
                self.assertIn("gateway", read(shown).lower())
                self.assertNotIn(TYPE, read(shown), "the type as Azure names it is not a word of a person")
        self.assertEqual((brief_of(case, plan).where.kind, brief_of(case, plan).where.noun), ("Gateway", "gateway"))


class TheHeadlineSaysWhatChanges(unittest.TestCase):
    """The title of a request names the change, from what to what when that is known, and never says "reduce"."""

    def headline(self, action: str, remains: dict, proposal=None, **more) -> str:
        case, plan = gateway(facts=gateway_facts(action, remains, proposal, **more))
        return brief_of(case, plan).headline

    def test_a_reduction_says_from_what_to_what_from_the_setting_that_the_finding_proposes(self):
        case, plan = gateway(SETTING)
        shown = brief_of(case, plan)
        self.assertEqual(shown.headline, "Scale down the gateway lab-gw-1 in group rg-lab: capacity units from 4 to 2")
        self.assertEqual(shown.verb, "Scale down")
        self.assertEqual(title_of(surfaces(case, plan)["page"]), "Scale down the gateway lab-gw-1: capacity units from 4 to 2", "the title of the page has no place: the line under it says it")

    def test_without_a_setting_it_says_it_from_the_numbers_that_the_finding_priced(self):
        self.assertEqual(self.headline("reduce", {"form": "quantity", "from": 1440, "to": 0}), "Scale down the gateway lab-gw-1 in group rg-lab: one charge from 1,440 to 0 hours in the last 30 days")
        self.assertEqual(self.headline("reduce", {"form": "quantity", "from": 1440, "to": 720}), "Scale down the gateway lab-gw-1 in group rg-lab: one charge from 1,440 to 720 hours in the last 30 days")
        self.assertEqual(self.headline("reduce", {"form": "ratio", "from": 4, "to": 2, "on": "capacityUnits"}), "Scale down the gateway lab-gw-1 in group rg-lab: capacity units from 4 to 2")
        self.assertEqual(self.headline("reduce", {"form": "assumed", "low": 0.4, "high": 0.7}), "Scale down the gateway lab-gw-1 in group rg-lab", "an assumed share has no numbers to say")

    def test_the_other_changes_say_what_they_are(self):
        self.assertEqual(self.headline("remove", {"form": "none"}), "Remove the gateway lab-gw-1 in group rg-lab")
        self.assertEqual(self.headline("schedule", {"form": "share_of_days", "days": 5, "of": 7, "span": 7}), "Turn off the gateway lab-gw-1 in group rg-lab on 2 of every 7 days")
        self.assertEqual(self.headline("schedule", {"form": "assumed", "low": 0.4, "high": 0.7}), "Turn off the gateway lab-gw-1 in group rg-lab when it is not needed")
        self.assertEqual(self.headline("commit", {"form": "assumed", "low": 0.2, "high": 0.3}), "Buy a commitment for the gateway lab-gw-1 in group rg-lab")

    def test_a_setting_that_the_finding_proposes_makes_it_a_reduction_when_the_finding_names_no_action(self):
        case, plan = gateway(SETTING, facts={"basis": "no-usage", "metrics": {}, proposals.KEY: SETTING})
        self.assertEqual(brief_of(case, plan).headline, "Scale down the gateway lab-gw-1 in group rg-lab: capacity units from 4 to 2")

    def test_no_word_of_the_old_headline_is_left_on_any_surface(self):
        for action, remains in (("reduce", {"form": "quantity", "from": 1440, "to": 0}), ("remove", {"form": "none"}), ("schedule", {"form": "share_of_days", "days": 5, "of": 7, "span": 7}),
                                ("commit", {"form": "assumed", "low": 0.2, "high": 0.3}), ("reduce", {"form": "assumed", "low": 0.4, "high": 0.7})):
            case, plan = gateway(facts=gateway_facts(action, remains))
            for surface, shown in surfaces(case, plan).items():
                with self.subTest(action, surface=surface):
                    self.assertNotRegex(read(shown).lower(), r"\bconsider (reducing|removing|scheduling|a commitment)\b|\breduc(e|ing)\b")

    def test_a_group_says_how_many_in_the_new_verb(self):
        group = {"count": 3, "groups": 2, "type": "microsoft.network/privateendpoints", "names": ["pe-b", "pe-c"], "costUsd30d": 60.0}
        case, plan = gateway(facts={**gateway_facts(), GROUP_FACT: group}, resource_type="microsoft.network/privateendpoints")
        self.assertEqual(brief_of(case, plan).headline, "Scale down 3 private endpoints in 2 groups, starting with lab-gw-1")
        schedule, plan = gateway(facts={**gateway_facts("schedule", {"form": "assumed", "low": 0.4, "high": 0.7}), GROUP_FACT: group}, resource_type="microsoft.network/privateendpoints")
        self.assertEqual(brief_of(schedule, plan).headline, "Turn off 3 private endpoints in 2 groups when they are not needed, starting with lab-gw-1")

    def test_the_headline_is_made_in_one_place_and_without_the_setting_it_does_not_say_the_numbers(self):
        case, plan = gateway(SETTING)
        with mock.patch.object(proposals, "settings", lambda facts: ()):
            self.assertNotIn("capacity units", brief_of(case, plan).headline)


class TheQuestionNamesTheChange(unittest.TestCase):
    """What a person is asked says what would change, and for a change that Meternaut would make itself, what Meternaut would do."""

    def asked(self, action: str, remains: dict, proposal=None, **more) -> str:
        case, plan = gateway(facts=gateway_facts(action, remains, proposal, **more))
        return brief_of(case, plan).asked

    def test_advice_asks_whether_to_do_what_the_title_says(self):
        self.assertEqual(self.asked("reduce", {"form": "quantity", "from": 1440, "to": 0}, SETTING), "You are asked whether to scale down the gateway by lowering capacity units from 4 to 2.")
        self.assertEqual(self.asked("reduce", {"form": "quantity", "from": 1440, "to": 0}),
                         "You are asked whether to scale down the gateway by lowering one charge from 1,440 to 0 hours in the last 30 days.")
        self.assertEqual(self.asked("remove", {"form": "none"}), "You are asked whether to remove the gateway.")
        self.assertEqual(self.asked("schedule", {"form": "share_of_days", "days": 5, "of": 7, "span": 7}), "You are asked whether to turn off the gateway on 2 of every 7 days.")
        self.assertEqual(self.asked("schedule", {"form": "assumed", "low": 0.4, "high": 0.7}), "You are asked whether to turn off the gateway when it is not needed.")
        self.assertEqual(self.asked("commit", {"form": "assumed", "low": 0.2, "high": 0.3}), "You are asked whether to buy a commitment for the gateway.")
        self.assertEqual(self.asked("reduce", {"form": "assumed", "low": 0.4, "high": 0.7}), "You are asked whether to scale down the gateway.")

    def test_a_request_that_meternaut_would_make_asks_whether_to_let_meternaut_do_it_and_the_stages_of_two_people_stay(self):
        case, plan = a_change()
        self.assertEqual(brief_of(case, plan).asked, "You are asked whether to let Meternaut lower capacity units of the gateway lab-gw-1 from 4 to 2 in group rg-lab.")
        self.assertEqual(brief_mod.ASKED_BY_STAGE["first"].format(what="lower a number"), "You are asked whether to confirm that Meternaut may lower a number.")
        self.assertEqual((brief_mod.ASKED_BY_STAGE["mine"], brief_mod.ASKED_BY_STAGE["alone"]), ("", ""))

    def test_the_question_is_said_once_on_each_surface_and_is_the_same_sentence(self):
        case, plan = gateway(SETTING)
        for surface, shown in surfaces(case, plan).items():
            with self.subTest(surface):
                self.assertEqual(read(shown).count("You are asked whether to scale down the gateway by lowering capacity units from 4 to 2."), 1)


class WhatItIsWorth(unittest.TestCase):
    """The figure comes with its arithmetic: what the charge costs now and after, what the whole resource costs now and after, what is saved, and how it was worked out."""

    def page(self, **more):
        case, plan = gateway(SETTING, **more)
        return surfaces(case, plan)["page"]

    def table(self, shown: Rendered) -> list[list[str]]:
        cells = [block for block in shown.blocks if block.kind == "cell" and not block.details]
        start = next(n for n, block in enumerate(cells) if block.text == "Now, a month")
        body = cells[start + 3:]
        return [[cell.text for cell in body[n:n + 4]] for n in range(0, len(body), 4) if body[n].text in ("Charges it would shrink", "The whole gateway")]

    def test_a_small_table_adds_up_in_whole_numbers(self):
        rows = self.table(self.page())
        self.assertEqual(rows, [["Charges it would shrink", "$202", "$0", "$202"], ["The whole gateway", "$411", "$209", "$202"]])
        for _, now, after, saved in rows:
            self.assertEqual(int(now[1:]) - int(saved[1:]), int(after[1:]), "what it costs now less what is saved is what it costs after")

    def test_the_figure_above_the_table_is_the_year_of_what_the_table_saves(self):
        self.assertIn("Meternaut worked out that this could save about $2,419 a year ($202 a month).", read(self.page()))

    def test_one_paragraph_says_how_it_was_worked_out_with_what_is_the_bill_s_and_what_is_the_ai_s(self):
        text = read(self.page())
        for said in ("How Meternaut worked it out.", "Over the last 7 days this gateway paid about $202 a month for what the change would shrink.", "The bill shows 1,440 hours of it in the last 30 days.",
                     "The change would lower that to 0 hours, which takes away all of it.", "The old quantity, 1,440, is the bill's own, and Meternaut checked it.",
                     "The new quantity, 0, is the AI's choice, and Meternaut did not check it."):
            self.assertIn(said, text)
        self.assertNotIn("That is the AI's own proposal, and Meternaut did not check it.", text)

    def test_the_paragraph_says_which_kind_of_resource_it_is_about_and_not_the_word_resource(self):
        case, plan = gateway(SETTING)
        for surface, shown in surfaces(case, plan).items():
            with self.subTest(surface):
                self.assertNotIn("this resource", read(shown))
        with mock.patch.object(brief_mod, "kind_words", lambda *found: ("Resource", "resource")):
            self.assertIn("this resource paid about $202", brief_of(case, plan).saving.basis)

    def test_the_card_and_the_letter_say_the_same_in_the_same_words_without_the_table(self):
        case, plan = gateway(SETTING)
        for surface in ("card", "letter"):
            with self.subTest(surface):
                text = read(surfaces(case, plan)[surface])
                self.assertIn("The new quantity, 0, is the AI's choice, and Meternaut did not check it.", text)
                self.assertNotIn("How Meternaut worked it out", text)
                self.assertNotIn("Now, a month", text)

    def test_a_ratio_and_a_share_of_days_say_what_is_checked_and_what_is_the_ai_s(self):
        for action, remains, said in (
                ("reduce", {"form": "ratio", "from": 4, "to": 2, "on": "capacityUnits"},
                 ("The change would lower capacity units from 4 to 2, which takes away 50 percent of it.", "The old number, 4, is what the tools read for capacity units, and Meternaut checked it.",
                  "The new number, 2, is the AI's choice, and Meternaut did not check it.", "Meternaut also did not check that the charge falls in step with capacity units.")),
                ("schedule", {"form": "share_of_days", "days": 5, "of": 7, "span": 7},
                 ("The AI says it is needed 5 days of every 7, so the change would turn it off on 2 of every 7 days, which takes away 29 percent of it.",
                  "Those days are the AI's own, and Meternaut did not check them."))):
            case, plan = gateway(facts=gateway_facts(action, remains))
            for surface, shown in surfaces(case, plan).items():
                for sentence in said:
                    with self.subTest(action, surface=surface, sentence=sentence[:30]):
                        self.assertIn(sentence, read(shown))

    def test_the_arithmetic_is_taken_out_when_the_figure_is_not_code_s(self):
        advisor = make_advice_case(detector="advisor-cost", models={}, recommendation="change", facts={"category": "cost", "advisor": {"type": "x", "sub": "x", "n": 1, "usd": 120.0, "rows": [["Standard_D2s_v6", 1, "swedencentral", "", 120.0, "USD", 60, ""]]}})
        self.assertEqual(brief_of(advisor, make_advice()).worked, ())

    def test_the_table_and_its_sentences_fail_when_the_figure_is_taken_out_of_the_digest(self):
        case, plan = gateway(SETTING)
        broken = dataclasses.replace(case, facts={key: value for key, value in case.facts.items() if key != pricing.KEY})
        self.assertEqual(brief_of(broken, plan).worked, ())
        self.assertEqual(len(brief_of(case, plan).worked), 2)


class WhatHappensIfYouAnswer(unittest.TestCase):
    """What an answer does is said for the kind of request that it is: Meternaut cannot make the change (and why), Meternaut makes no change for this kind yet, or Meternaut makes the change."""

    def test_when_meternaut_cannot_make_the_change_it_says_why_and_who_acts(self):
        case, plan = gateway(SETTING, precondition="switch-off")
        for surface, shown in surfaces(case, plan).items():
            with self.subTest(surface):
                text = read(shown)
                self.assertIn("Meternaut cannot make this change itself. The owner has not yet allowed Meternaut to change real resources. Your answer is recorded with your name.", text)
                self.assertIn(brief_mod.ADVICE_WHO, text)
                self.assertIn("The Sessions metric was 0 in 30 days.", text)
        page = surfaces(case, plan)["page"]
        self.assertIn("What the AI says you could do. Meternaut did not check the wording.", [block.text for block in page.blocks if block.kind == "paragraph"])
        self.assertIn(HOW, quotes(page))

    def test_each_reason_that_a_change_cannot_be_made_is_said_in_its_own_sentence(self):
        for key, sentence in proposals.CANNOT.items():
            case, plan = gateway(SETTING, precondition=key)
            with self.subTest(key):
                self.assertIn(sentence, brief_of(case, plan).change)

    def test_a_finding_with_no_setting_says_that_no_change_is_made_for_this_kind_yet(self):
        case, plan = gateway()
        for surface, shown in surfaces(case, plan).items():
            with self.subTest(surface):
                self.assertIn("Meternaut makes no change for this kind of finding yet. Your answer is recorded with your name.", read(shown))
                self.assertNotIn("cannot make this change itself", read(shown))
        self.assertIn(HOW, quotes(surfaces(case, plan)["page"]))

    def test_the_stock_sentences_that_the_owner_read_are_gone_where_a_measurement_exists(self):
        for precondition in ("switch-off", ""):
            case, plan = gateway(SETTING if precondition else None, precondition=precondition)
            for surface, shown in surfaces(case, plan).items():
                with self.subTest(precondition, surface=surface):
                    for said in OWNER_HATED:
                        self.assertNotIn(said, read(shown))

    def test_a_finding_that_nothing_measured_says_so_and_says_what_a_read_cannot_see(self):
        case, plan = gateway(SETTING, precondition="switch-off", facts={**gateway_facts(proposal=SETTING), "metrics": {}, "metricUnits": {}, "metricDays": {}, "metricDaysWithData": {}, "citedMetrics": 0})
        for surface, shown in surfaces(case, plan).items():
            with self.subTest(surface):
                self.assertIn("Nothing was measured of its use, and a read of Azure cannot see what depends on it.", read(shown))

    def test_what_the_second_ai_doubts_is_said_as_its_own_in_what_could_go_wrong(self):
        case, plan = gateway(SETTING, precondition="switch-off")
        self.assertIn(f'The second AI says: "{DOUBT}"', brief_of(case, plan).risk.text)
        quiet = dataclasses.replace(case, objections=())
        self.assertNotIn("The second AI says", brief_of(quiet, plan).risk.text)

    def test_the_words_that_say_what_happens_are_made_from_the_facts_and_fail_when_the_facts_are_taken_out(self):
        case, plan = gateway(SETTING, precondition="switch-off")
        for mutation, said in ((mock.patch.object(proposals, "settings", lambda facts: ()), "cannot make this change itself"), (mock.patch.object(proposals, "cannot", lambda found: ""), "The owner has not yet allowed")):
            with mutation:
                self.assertNotIn(said, brief_of(case, plan).change)
        self.assertIn("The owner has not yet allowed", brief_of(case, plan).change)

    def test_a_request_of_azure_advisor_and_of_an_older_check_keeps_its_words(self):
        for case, plan in ((make_advice_case(detector="advisor-cost", models={}, recommendation="change", resource_name="oversized-vm-1",
                                             facts={"category": "cost", "advisor": {"type": "x", "sub": "x", "n": 1, "usd": 120.0, "rows": [["Standard_D2s_v6", 1, "swedencentral", "", 120.0, "USD", 60, ""]]}}), make_advice()),
                           (make_advice_case(detector="orphan-managed-disk", recommendation="delete", facts={"diskState": "unattached"}), make_advice())):
            with self.subTest(case.detector):
                shown = brief_of(case, plan)
                self.assertEqual((shown.change, shown.who_acts), (brief_mod.ADVICE_CHANGE, brief_mod.ADVICE_WHO))


class AChangeThatMeternautMakes(unittest.TestCase):
    """A request that a person approves and Meternaut makes shows, in this order, what happens when they approve, what is read again right before, what could go wrong and the undo."""

    def test_the_block_says_what_the_family_wrote_in_the_order_of_a_decision(self):
        case, plan = a_change()
        page = surfaces(case, plan)["page"]
        terms = [block.text for block in page.blocks if block.kind == "term" and not block.details]
        self.assertEqual(terms, ["What changes", "Who does it", "What could go wrong", "Undo"])
        text = read(page)
        self.assertIn("When you approve, Azure lowers capacity units of the gateway lab-gw-1 in resource group rg-lab from 4 to 2.", text)
        self.assertIn("Connections that need more than 2 units are refused.", text)
        self.assertIn("You are asked whether to let Meternaut lower capacity units of the gateway lab-gw-1 from 4 to 2 in group rg-lab.", text)

    def test_the_card_and_the_letter_ask_the_same_question(self):
        case, plan = a_change()
        for surface in ("card", "letter"):
            with self.subTest(surface):
                self.assertIn("You are asked whether to let Meternaut lower capacity units", read(surfaces(case, plan)[surface]))

    def test_a_family_that_has_words_of_its_own_is_checked_again_before_what_could_go_wrong(self):
        case, plan = a_change()
        with mock.patch.object(brief_mod, "words_of", lambda *found: SimpleNamespace(headline="Lower it", change="Azure lowers it.", rechecked="Right before it acts, Meternaut reads it again.", risk="It slows.",
                                                                                       level="medium", undo="Raise it.", reversible=True)):
            page = Rendered("page", "page", blocks_of_html(self.page_of(case, plan)))
        self.assertEqual([block.text for block in page.blocks if block.kind == "term" and not block.details], ["What changes", "Who does it", "Checked again", "What could go wrong", "Undo"])

    @staticmethod
    def page_of(case, plan) -> str:
        console = Console()
        console.store.case_put(case)
        console.store.plan_put(plan)
        return console.get(f"/ok/{plan.plan_id}").text


class OtherWaysToSave(unittest.TestCase):
    """The other ways to save on the same resource are for information: a table on the page with what each saves and gives up, and one line on the card and the letter."""

    def test_the_page_has_a_table_with_the_saving_the_way_it_is_made_and_what_is_given_up(self):
        case, plan = gateway(BOTH, precondition="switch-off")
        page = surfaces(case, plan)["page"]
        text = read(page)
        self.assertIn("The AI named 2 other ways to save on this gateway, and Meternaut priced 1 of them from the bill.", text)
        cells = [block.text for block in page.blocks if block.kind == "cell" and not block.details]
        self.assertTrue(any("Move to the Lite tier" in cell and "Azure only does this by making the resource again." in cell for cell in cells), cells)
        self.assertIn("$150 to $202", cells)
        self.assertIn("Lite is shared and carries no uptime promise.", cells)
        self.assertIn("Remove the gateway", cells, "a way that Azure has no word for in place or not says nothing of it")
        self.assertIn("Not priced", cells)
        self.assertIn("Everything that connects through it stops.", cells)
        self.assertIn("The titles and the words about what each gives up are the AI's, and Meternaut did not check the wording.", text)

    def test_the_card_and_the_letter_have_one_line_and_no_button(self):
        case, plan = gateway(BOTH)
        for surface in ("card", "letter"):
            with self.subTest(surface):
                text = read(surfaces(case, plan)[surface])
                self.assertEqual(text.count("other ways to save on this gateway"), 1)
                self.assertIn("The AI named 2 other ways to save on this gateway. They are on the page.", text)
                self.assertNotIn("Lite is shared", text)
        buttons = [action["title"] for block in card_of(case, plan)["body"] if block.get("type") == "ActionSet" for action in block["actions"]]
        self.assertEqual(buttons, ["Review and decide"], "the other ways are information and make no button")

    def test_a_request_that_meternaut_would_make_shows_them_too(self):
        case, plan = a_change()
        case = dataclasses.replace(case, facts=gateway_facts(proposal=BOTH))
        page = surfaces(case, plan)["page"]
        self.assertIn("The AI named 2 other ways to save on this gateway, and Meternaut priced 1 of them from the bill.", read(page))
        self.assertIn("If you approve", [block.text for block in page.blocks if block.kind == "heading"])

    def test_nothing_is_said_when_the_finding_has_no_other_way(self):
        case, plan = gateway(SETTING)
        for surface, shown in surfaces(case, plan).items():
            with self.subTest(surface):
                self.assertNotIn("other way", read(shown))

    def test_the_details_list_no_row_for_what_the_finding_proposes_because_its_words_are_the_ai_s(self):
        from cases.web import brief_page

        case, plan = gateway(BOTH)

        def details() -> list[str]:
            return [block.text for block in surfaces(case, plan)["page"].blocks if block.details and block.kind == "cell"]

        self.assertIn("basis", details())
        self.assertNotIn(proposals.KEY, details())
        self.assertEqual([text for text in details() if "Lite is shared" in text], [])
        with mock.patch.object(brief_page, "PROPOSED", "nothing"):
            self.assertIn(proposals.KEY, details())
            self.assertTrue([text for text in details() if "Lite is shared" in text])

    def test_the_table_fails_when_the_readers_are_taken_out(self):
        case, plan = gateway(BOTH)
        with mock.patch.object(proposals, "others", lambda facts: ()):
            self.assertEqual(brief_of(case, plan).others, ())
        self.assertEqual(len(brief_of(case, plan).others), 2)


class EverySurfaceReadsAsSentences(unittest.TestCase):
    """The lint of the words (test_words) holds the new sentences too: voice, whole sentences, no abbreviated date and no repeated sentence."""

    def test_each_request_reads_as_sentences_on_the_page_the_card_and_the_letter(self):
        group = {"count": 6, "groups": 2, "type": TYPE, "names": ["lab-gw-2", "lab-gw-3"], "costUsd30d": 2400.0}
        for name, (case, plan) in {"cannot": gateway(BOTH, precondition="switch-off"), "no change yet": gateway(), "a change": a_change(),
                                   "a group": gateway(facts={**gateway_facts(), GROUP_FACT: group}, number=4)}.items():
            for surface, shown in surfaces(case, plan).items():
                with self.subTest(name, surface=surface):
                    self.assertEqual([], problems(dataclasses.replace(shown, name=f"{name}, {surface}")))


class TheListsSayItInTheWordsOfNow(unittest.TestCase):
    """The title that a request made before these words kept is said in the new verbs in the lists of what was asked (the History): a request that waits has its title made again from its finding."""

    OLD = (("Consider reducing the gateway lab-gw-1 in group rg-lab", "Scale down the gateway lab-gw-1 in group rg-lab"), ("Consider removing the gateway lab-gw-1 in group rg-lab", "Remove the gateway lab-gw-1 in group rg-lab"),
           ("Consider switching the firewall x in group g from A to B", "Switch the firewall x in group g from A to B"),
           ("Consider scheduling the gateway lab-gw-1 in group rg-lab", "Turn off the gateway lab-gw-1 in group rg-lab when it is not needed"),
           ("Consider a commitment for the gateway lab-gw-1 in group rg-lab", "Buy a commitment for the gateway lab-gw-1 in group rg-lab"),
           ("Consider deleting the disk x in group g", "Consider deleting the disk x in group g"), ("Look at the gateway lab-gw-1 in group rg-lab", "Look at the gateway lab-gw-1 in group rg-lab"))

    def test_an_old_title_is_said_in_the_new_verbs_and_a_title_that_never_changed_is_left_alone(self):
        for old, new in self.OLD:
            with self.subTest(old):
                self.assertEqual(brief_mod.plan_headline(make_advice(title=old)), new)

    def test_the_history_page_says_it_so(self):
        console = Console()
        plan = make_advice(plan_id="plan0510", case_id="case0510", state="declined", title="Consider reducing the gateway lab-gw-1 in group rg-lab", created_at=at(days=-2))
        console.store.plan_put(plan)
        console.store.decision_put(make_decision(plan_id="plan0510", decision="decline", reason="handled", at=at(days=-1)))
        reply = console.get("/history")
        text = " ".join(block.text for block in blocks_of_html(reply.text) if not block.details)
        self.assertIn("Scale down the gateway lab-gw-1", text)
        self.assertNotIn("Consider reducing", text)


def hated(shown: Rendered) -> list[str]:
    """What of the words that the owner threw out a person still reads (the old verbs, the stock sentences, the sentence that made him think that nothing was calculated)."""
    text = read(shown)
    return [said for said in (*OWNER_HATED, "reducing", "Consider scheduling", "Consider removing", "Consider switching") if said in text]


class EachKeyCheckFailsWhenItsBehaviourIsTakenOut(unittest.TestCase):
    """A check that passes with and without what it guards guards nothing: each of the key ones is shown to fail when the behaviour is put back as it was."""

    def shown(self, case, plan) -> Rendered:
        return surfaces(case, plan)["page"]

    def test_the_headline_and_the_question_fail_with_the_old_verb(self):
        case, plan = gateway(SETTING, precondition="switch-off")
        self.assertEqual(hated(self.shown(case, plan)), [])
        with mock.patch.dict(brief_mod.CHANGE_VERBS, {"reduce": "Consider reducing"}), mock.patch.dict(brief_mod.ASKED_WHAT, {"Consider reducing": "reducing {thing}"}):
            old = brief_mod.build_brief(case, plan, None, (), now=NOW, may_answer=True)
        self.assertTrue(old.headline.startswith("Consider reducing") and old.verb == "Consider reducing")

    def test_what_could_go_wrong_fails_with_the_sentence_that_fits_any_request(self):
        case, plan = gateway(SETTING, precondition="switch-off")
        with mock.patch.object(brief_mod, "use_words", lambda found: brief_mod.CHANGE_RISK):
            self.assertEqual(hated(self.shown(case, plan)), ["If you act, what depends on it can slow down or stop."])

    def test_what_an_answer_does_fails_with_the_sentence_that_made_the_owner_ask_whether_nothing_happens(self):
        case, plan = gateway(SETTING, precondition="switch-off")
        with mock.patch.object(brief_mod, "advice_words", lambda found, then: (brief_mod.ADVICE_CHANGE, brief_mod.ADVICE_WHO)):
            self.assertEqual(hated(self.shown(case, plan)), ["Meternaut changes nothing in Azure. Your answer is recorded with your name."])

    def test_the_figure_fails_with_the_sentence_that_said_that_nothing_was_calculated(self):
        case, plan = gateway(SETTING)
        with mock.patch.object(pricing, "_basis", lambda *found, **more: "That is the AI's own proposal, and Meternaut did not check it."):
            shown = self.shown(case, plan)
        self.assertEqual(hated(shown), ["That is the AI's own proposal, and Meternaut did not check it."])

    def test_the_arithmetic_and_the_other_ways_fail_when_they_are_taken_out(self):
        case, plan = gateway(BOTH)

        def words() -> list[str]:
            return [block.text for block in self.shown(case, plan).blocks]

        self.assertTrue({"Now, a month", "Saves a month"} <= set(words()))
        with mock.patch.object(brief_mod, "worked_of", lambda *found: ()):
            self.assertNotIn("Now, a month", words())
        with mock.patch.object(proposals, "others", lambda facts: ()):
            self.assertNotIn("Saves a month", words())


class TheSharedShapeHoldsNoWayToReachAzure(unittest.TestCase):
    def test_it_imports_only_the_standard_library(self):
        import ast
        from pathlib import Path

        tree = ast.parse((Path(support.APP_ROOT) / "cases" / "proposals.py").read_text(encoding="utf-8"))
        found = {(node.level, (node.module or "").split(".")[0]) for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)} | {(0, a.name.split(".")[0]) for node in ast.walk(tree) if isinstance(node, ast.Import) for a in node.names}
        self.assertLessEqual(found, {(0, "__future__"), (0, "math"), (0, "re"), (0, "dataclasses"), (0, "typing")})


if __name__ == "__main__":
    unittest.main()
