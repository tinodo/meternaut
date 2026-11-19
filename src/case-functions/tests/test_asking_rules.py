"""Who is asked about a finding of the investigation, end to end (cases/approvals.py why_not_ask): a request is made only when code priced a saving, something was measured of the resource's use, and,
for a switch to another price of the price list, the second AI agreed. What is not asked about stays a case and an open question; a request that was made under these rules is never taken back when
its finding is judged again; one that was made before them is. The investigation runs with a fake Foundry and a fake toolbox (the harness of test_investigate). Every name is invented.
"""
import json
import unittest
from dataclasses import replace

import support  # noqa: F401  (it puts the app on the path)
from test_investigate import FakeFoundry, FakeToolbox, Harness, Moving, answer, entry, finding, loop_for, meter_line, metrics, priced, resource, verdicts
from test_pricing import COMPUTE, LISTED, billed_units, block, effect

from cases import learning
from cases.approvals import ASKED_UNDER, ASKING_RULES, NOT_ASKED, UNCONFIRMED, UNMEASURED, UNPRICED, why_not_ask
from cases.brief import taken_back
from cases.decide import NO_MEASUREMENT

CHEAPER = "Take the cheaper plan."
SECOND_AI_DID_NOT_AGREE = "the second AI did not agree that it can be switched"


def toolbox(count: int = 1, **more) -> FakeToolbox:
    """`count` resources, each billed for one meter of 600 hours that cost 60 (the bill pays 0.8 of the list price), and the price that the tool for alternatives showed for each: half of the list price."""
    handles = [f"r{n}" for n in range(1, count + 1)]
    box = FakeToolbox([resource(n, cost_usd_30d=60.0) for n in range(1, count + 1)], {handle: metrics(MetricA=0) for handle in handles},
                      meters={f"m{n}": billed_units(usd=60.0, quantity=600.0, scope=f"r{n}", words=COMPUTE) for n in range(1, count + 1)}, **more)
    box.prices, box.retail, box.offers = {"p1": LISTED["p1"]}, {f"m{n}": 0.125 for n in range(1, count + 1)}, {f"m{n}": {"p1"} for n in range(1, count + 1)}
    return box


def switch(*handles: str, **more) -> dict:
    """A finding that asks for a switch of the one billed meter of each handle to the price that the tool showed, and cites a measurement of each that the tools confirm."""
    change = block("switch", *[effect(handle, (f"m{handle[1:]}",), {"form": "alternative", "price": "p1"}) for handle in handles], how=CHEAPER)
    values = dict(handles=handles, basis="oversized", proposal="change", confidence=0.9, summary="They use a little of what they have.", change=change,
                  evidence=[entry(handle, "MetricA", 0) for handle in handles])
    return finding(**{**values, **more})


def go(raw, box, skeptic=None, clock=None, extras=None) -> Harness:
    h = Harness(FakeFoundry(answer(*(raw if isinstance(raw, list) else [raw])), skeptic), box, clock=clock, extras=extras, with_store=extras is None)
    h.go()
    return h


def said(h: Harness) -> str:
    return h.notes[-1]


class WhenTheSecondAiMustAgreeToASwitch(unittest.TestCase):
    """Code cannot know whether a resource can move to another tier of its service, and the second AI, which is shown the alternative, is the check that exists."""

    def test_a_switch_is_asked_about_when_the_second_ai_agreed_and_not_when_it_did_not_agree_was_not_sure_or_gave_no_verdict(self):
        verdict_of = {"it agrees": "agree", "it disagrees": "disagree", "it is not sure": "unsure", "it gives no verdict": "none"}
        for label, skeptic, asked in (("it agrees", verdicts(("agree", (), "Fine.")), True), ("it disagrees", verdicts(("disagree", ("It may not be possible.",), "No.")), False),
                                      ("it is not sure", verdicts(("unsure", (), "The window is short.")), False), ("it gives no verdict", json.dumps({"verdicts": []}), False)):
            with self.subTest(label):
                h = go(switch("r1"), toolbox(), skeptic)
                (case,) = h.store.cases_recent()
                self.assertEqual((case.facts["change"]["price"]["form"], case.saving_usd_month, case.learned["skeptic"]), ("alternative", 22.5, verdict_of[label]))
                self.assertEqual(len(h.store.plans_open()), int(asked))
                if asked:
                    (plan,) = h.store.plans_open()
                    self.assertEqual((plan.saving_usd_month, plan.preconditions[ASKED_UNDER], case.plan_id), (22.5, ASKING_RULES, plan.plan_id))
                    self.assertFalse([note for note in h.notes if "no request was made" in note])
                else:
                    self.assertEqual((case.plan_id, h.of("plan.created")), (None, []))
                    self.assertTrue(said(h).endswith(f"opened 1 case; no request was made for 1 of them because {SECOND_AI_DID_NOT_AGREE}"), said(h))
                    self.assertEqual([(row.why, row.request) for row in learning.OpenQuestions(h.store, h.clock()).rows()], [(UNCONFIRMED, "none")], "the Investigator gets it again, with the reason")

    def test_a_change_that_is_no_switch_is_asked_about_whatever_the_second_ai_said(self):
        change, meters = priced("r1", usd=40.0)
        for verdict in ("agree", "disagree", "unsure"):
            with self.subTest(verdict):
                h = go(finding(handles=("r1",), basis="oversized", proposal="change", confidence=0.9, change=change), FakeToolbox([resource(1, cost_usd_30d=40.0)], {"r1": metrics(MetricA=0)}, meters=meters),
                       verdicts((verdict, (), "Words.")))
                self.assertEqual([(p.family, p.saving_usd_month) for p in h.store.plans_open()], [("advise", 40.0)])

    def test_a_group_that_is_a_switch_is_judged_by_the_verdict_of_the_group(self):
        for verdict, asked in (("agree", True), ("disagree", False)):
            with self.subTest(verdict):
                h = go(switch(*[f"r{n}" for n in range(1, 7)], proposal="investigate", confidence=0.4), toolbox(6), verdicts((verdict, (), "Words.")))
                (case,) = h.store.cases_recent()
                self.assertEqual((case.facts["group"]["count"], case.facts["change"]["price"]["form"], case.facts["change"]["price"]["lines"], len(h.store.plans_open())), (6, "alternative", 6, int(asked)))
                if not asked:
                    self.assertEqual([row.why for row in learning.OpenQuestions(h.store, h.clock()).rows()], [UNCONFIRMED])


class WhenAFindingIsNotAskedAbout(unittest.TestCase):
    def test_the_end_note_counts_the_cases_for_each_reason_in_one_plain_sentence_and_each_stays_an_open_question_with_its_reason(self):
        change, meters = priced("r2", usd=30.0)
        box = toolbox(3)
        box.meters = {"m1": box.meters["m1"], **meters, "m3": meter_line("r3", 10.0)}
        raw = [finding(handles=("r3",), basis="low-usage", proposal="change", evidence=[entry("r3", "MetricA", 0)]),  # no change is stated: nothing is priced
               finding(handles=("r2",), basis="low-usage", proposal="change", evidence=[], change=change),  # priced, and nothing measured
               switch("r1")]
        h = go(raw, box, verdicts(("agree", (), "Fine."), ("agree", (), "Fine."), ("unsure", (), "Not sure.")))
        self.assertEqual((h.store.plans_open(), h.result.cases), ([], 3))
        self.assertEqual(h.result.not_asked, {UNPRICED: 1, UNMEASURED: 1, UNCONFIRMED: 1})
        self.assertTrue(said(h).endswith(f"opened 3 cases; no request was made for 1 of them because {NOT_ASKED[UNPRICED]}, for 1 of them because {NOT_ASKED[UNMEASURED]}, "
                                         f"for 1 of them because {NOT_ASKED[UNCONFIRMED]}"), said(h))
        rows = {row.resource_id.rsplit("-", 1)[1]: row.why for row in learning.OpenQuestions(h.store, h.clock()).rows()}
        self.assertEqual(rows, {"1": UNCONFIRMED, "2": UNMEASURED, "3": UNPRICED})

    def test_a_finding_that_is_asked_about_is_not_counted_and_a_run_that_asks_about_all_says_nothing_of_it(self):
        h = go(switch("r1"), toolbox(), verdicts(("agree", (), "Fine.")))
        self.assertEqual((h.result.not_asked, len(h.store.plans_open())), ({}, 1))
        self.assertFalse([note for note in h.notes if "no request was made" in note])

    def test_the_reasons_are_the_keys_of_the_words_and_the_words_say_why_in_plain_terms(self):
        self.assertEqual(tuple(NOT_ASKED), (UNPRICED, UNMEASURED, UNCONFIRMED))
        self.assertEqual(NOT_ASKED[UNMEASURED], "nothing was measured of its use")
        self.assertEqual(NOT_ASKED[UNCONFIRMED], SECOND_AI_DID_NOT_AGREE)
        self.assertEqual(NO_MEASUREMENT, "no measurement backs this finding; a person has to judge it", "the one flag that the rule reads")


class WhenTheFindingIsJudgedAgain(unittest.TestCase):
    """A request that was made under the rules of today is never taken back for them, whatever a later judgment finds; one that was made before them is, once, with the reason `rules`."""

    def first(self, raw, box, skeptic, old=False):
        self.clock = Moving()
        self.h = go(raw, box, skeptic, clock=self.clock)
        self.extras = self.h.extras
        (self.plan,) = self.extras.store.plans_open()
        self.assertEqual(self.plan.preconditions[ASKED_UNDER], ASKING_RULES)
        if old:
            self.plan = replace(self.plan, preconditions={key: value for key, value in self.plan.preconditions.items() if key != ASKED_UNDER})
            self.extras.store.plan_put(self.plan)
        self.clock.advance(days=8)

    def judged_again(self, raw, box, skeptic):
        again = go(raw, box, skeptic, clock=self.clock, extras=self.extras)
        self.assertEqual(again.result.cases, 1, "the finding was judged again")
        return again

    def test_a_request_made_under_the_rules_stays_when_its_finding_is_judged_again_with_no_measurement_or_with_another_verdict(self):
        agreed = verdicts(("agree", (), "Fine."))
        for label, second, skeptic, reason in (("no measurement", switch("r1", evidence=[]), agreed, UNMEASURED),
                                               ("the second AI disagrees", switch("r1"), verdicts(("disagree", ("It may not be possible.",), "No.")), UNCONFIRMED),
                                               ("the second AI gives no verdict", switch("r1"), json.dumps({"verdicts": []}), UNCONFIRMED)):
            with self.subTest(label):
                self.first(switch("r1"), toolbox(), agreed)
                self.judged_again(second, toolbox(), skeptic)
                case = self.extras.store.case_get(self.h.store.cases_recent()[0].case_id)
                self.assertEqual(why_not_ask(case), reason, "the finding as it is judged now would not be asked about")
                self.assertEqual(self.extras.approvals.hold_back_empty(), [], "but nobody takes back a request that was asked under these rules, and says that the rules changed")
                kept = self.extras.store.plan_get(self.plan.plan_id)
                self.assertEqual((kept.state, taken_back(kept), case.plan_id), ("open", "", self.plan.plan_id), "the request stays open and is chased, and the case stays linked to it")

    def test_a_request_made_before_the_rules_is_taken_back_once_with_the_reason_rules_when_its_finding_is_judged_again_with_no_measurement_or_another_verdict(self):
        agreed = verdicts(("agree", (), "Fine."))
        for label, second, skeptic in (("no measurement", switch("r1", evidence=[]), agreed),
                                       ("the second AI disagrees", switch("r1"), verdicts(("disagree", ("It may not be possible.",), "No.")))):
            with self.subTest(label):
                self.first(switch("r1"), toolbox(), agreed, old=True)
                self.judged_again(second, toolbox(), skeptic)
                taken = self.extras.approvals.hold_back_empty()
                self.assertEqual([(plan.plan_id, taken_back(plan)) for plan, _ in taken], [(self.plan.plan_id, "rules")])
                self.assertEqual(self.extras.approvals.hold_back_empty(), [], "once")
                self.assertEqual(self.extras.store.plans_open(), [])
