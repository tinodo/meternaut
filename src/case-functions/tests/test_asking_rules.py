"""Who is asked about a finding of the investigation, end to end (cases/approvals.py why_not_ask): a request is made only when code priced a saving, something was measured of the resource's use, and,
for a switch to another price of the price list, the second AI agreed. What is not asked about stays a case and an open question; a request that was made under these rules is never taken back when
its finding is judged again; one that was made before them is. The investigation runs with a fake Foundry and a fake toolbox (the harness of test_investigate). Azure Advisor's own recommendations
are asked about only when a saving in dollars is counted for them, and the last class of this file says how, with the Watch of test_advisor_parity. Every name is invented.
"""
import json
import unittest
from dataclasses import replace

import support  # noqa: F401  (it puts the app on the path)
import test_advisor_parity as advisor_fixtures
from support import SUBSCRIPTION, disk_row
from test_investigate import FakeFoundry, FakeToolbox, Harness, Moving, answer, entry, finding, meter_line, metrics, priced, resource, unasked, verdicts
from test_pricing import COMPUTE, LISTED, billed_units, block, effect
from test_run_loop import GROUP, PLANTED

from cases import learning
from cases.approvals import ASKED_UNDER, ASKING_RULES, NO_FIGURE, NOT_ASKED, UNCONFIRMED, UNMEASURED, UNPRICED, ApprovalSettings, Approvals, build_advice, why_not_ask
from cases.brief import says_nothing, taken_back
from cases.decide import NO_MEASUREMENT
from cases.detectors import ADVISOR
from cases.families import digest as plan_digest
from cases.memory_store import MemoryStore
from test_estate_watch import of_type
from test_web_support import TINO, Console, make_advice_case, make_case, make_decision

CHEAPER = "Take the cheaper plan."
SECOND_AI_DID_NOT_AGREE = "the second AI did not agree that the switch can be made, or the first was not sure"


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


def assumed_switch(*handles: str, **more) -> dict:
    """The same switch, but its saving is a share of the bill that the AI assumes (a low and a high), not the price that the tool showed: nothing in the bill checks it either."""
    return switch(*handles, change=block("switch", *[effect(handle, (f"m{handle[1:]}",), {"form": "assumed", "low": 0.4, "high": 0.7}) for handle in handles], how=CHEAPER), **more)


def go(raw, box, skeptic=None, clock=None, extras=None) -> Harness:
    h = Harness(FakeFoundry(answer(*(raw if isinstance(raw, list) else [raw])), skeptic), box, clock=clock, extras=extras, with_store=extras is None)
    h.go()
    return h


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
                    self.assertFalse(unasked(h))
                else:
                    self.assertEqual((case.plan_id, h.of("plan.created")), (None, []))
                    self.assertEqual(unasked(h), [f"no request was made for 1 case because {SECOND_AI_DID_NOT_AGREE}"])
                    self.assertEqual([(row.why, row.request) for row in learning.OpenQuestions(h.store, h.clock()).rows()], [(UNCONFIRMED, "none")], "the Investigator gets it again, with the reason")

    def test_a_switch_that_the_second_ai_agreed_to_is_asked_about_only_when_the_first_ai_was_sure_enough_too(self):
        for confidence, asked in ((0.45, False), (0.69, False), (0.7, True), (0.9, True)):
            with self.subTest(confidence=confidence):
                h = go(switch("r1", confidence=confidence), toolbox(), verdicts(("agree", (), "Fine.")))
                (case,) = h.store.cases_recent()
                self.assertEqual((case.learned["skeptic"], case.confidence, len(h.store.plans_open())), ("agree", confidence, int(asked)))
                self.assertEqual(bool(unasked(h)), not asked, unasked(h))

    def test_a_switch_whose_saving_is_a_share_that_the_ai_assumed_needs_both_ais_to_be_sure_like_one_priced_from_the_list(self):
        for label, raw, skeptic, asked in (("both are sure", assumed_switch("r1"), verdicts(("agree", (), "Fine.")), True),
                                           ("the second AI is unsure", assumed_switch("r1"), verdicts(("unsure", (), "The window is short.")), False),
                                           ("the first AI is not sure", assumed_switch("r1", confidence=0.45), verdicts(("agree", (), "Fine.")), False)):
            with self.subTest(label):
                h = go(raw, toolbox(), skeptic)
                (case,) = h.store.cases_recent()
                self.assertEqual((case.facts["change"]["action"], case.facts["change"]["price"]["form"], len(h.store.plans_open())), ("switch", "assumed", int(asked)))
                self.assertEqual((why_not_ask(case), bool(unasked(h))), (None if asked else UNCONFIRMED, not asked))

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
                h = go(switch(*[f"r{n}" for n in range(1, 7)], proposal="investigate", confidence=0.8), toolbox(6), verdicts((verdict, (), "Words.")))
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
        self.assertEqual(unasked(h), [f"no request was made for 1 case because {NOT_ASKED[UNPRICED]}", f"no request was made for 1 case because {NOT_ASKED[UNMEASURED].format(their='its')}",
                                      f"no request was made for 1 case because {NOT_ASKED[UNCONFIRMED]}"], "one sentence for each reason: a note keeps 300 characters, and none of them is cut")
        rows = {row.resource_id.rsplit("-", 1)[1]: row.why for row in learning.OpenQuestions(h.store, h.clock()).rows()}
        self.assertEqual(rows, {"1": UNCONFIRMED, "2": UNMEASURED, "3": UNPRICED})

    def test_a_finding_that_is_asked_about_is_not_counted_and_a_run_that_asks_about_all_says_nothing_of_it(self):
        h = go(switch("r1"), toolbox(), verdicts(("agree", (), "Fine.")))
        self.assertEqual((h.result.not_asked, len(h.store.plans_open())), ({}, 1))
        self.assertFalse(unasked(h))

    def test_a_case_is_counted_only_when_no_request_is_open_for_its_own_resource(self):
        h = go([switch("r1"), switch("r2")], toolbox(2), verdicts(("agree", (), "Fine."), ("unsure", (), "Not sure.")))
        self.assertEqual([plan.resource_id.rsplit("-", 1)[1] for plan in h.store.plans_open()], ["1"], "the first is asked about")
        self.assertEqual((h.result.not_asked, unasked(h)), ({UNCONFIRMED: 1}, [f"no request was made for 1 case because {SECOND_AI_DID_NOT_AGREE}"]), "the second is not, and a request for another resource does not hide it")

    def test_the_reasons_are_the_keys_of_the_words_and_the_words_say_why_in_plain_terms(self):
        self.assertEqual(tuple(NOT_ASKED), (UNPRICED, UNMEASURED, UNCONFIRMED, NO_FIGURE), "the order of the reasons of the investigation stays, and the one of Azure Advisor is the last")
        self.assertEqual(NOT_ASKED[UNMEASURED], "nothing was measured of {their} use")
        self.assertEqual(NOT_ASKED[UNCONFIRMED], SECOND_AI_DID_NOT_AGREE)
        self.assertEqual(NO_MEASUREMENT, "no measurement backs this finding; a person has to judge it", "the one flag that the rule reads")

    def test_the_words_of_each_reason_are_right_for_one_case_and_for_more_than_one(self):
        for count, their, wrong in ((1, "its", r"\b(they|them|their)\b"), (2, "their", r"\b(it|its)\b")):
            for why, words in NOT_ASKED.items():
                with self.subTest(count=count, why=why):
                    self.assertNotRegex(words.format(their=their), wrong)
        h = go([switch("r1"), switch("r2")], toolbox(2), verdicts(("unsure", (), "Not sure."), ("unsure", (), "Not sure.")))
        self.assertEqual(unasked(h), [f"no request was made for 2 cases because {SECOND_AI_DID_NOT_AGREE}"])


class WhenTheFindingIsJudgedAgain(unittest.TestCase):
    """A request that was made under the rules of today is never taken back for them, whatever a later judgment finds; one that was made before them is, once, with the reason `rules`."""

    def first(self, raw, box, skeptic, old=False):
        self.clock = Moving()
        self.h = go(raw, box, skeptic, clock=self.clock)
        self.extras = self.h.extras
        (self.plan,) = self.extras.store.plans_open()
        self.assertEqual(self.plan.preconditions[ASKED_UNDER], ASKING_RULES)
        if old:  # a request as an earlier version made it: sealed without the marker
            self.plan = plan_digest.sealed(replace(self.plan, preconditions={key: value for key, value in self.plan.preconditions.items() if key != ASKED_UNDER}))
            self.extras.store.plan_put(self.plan)
        self.clock.advance(days=8)

    def judged_again(self, raw, box, skeptic):
        again = go(raw, box, skeptic, clock=self.clock, extras=self.extras)
        self.assertEqual(again.result.cases, 1, "the finding was judged again")
        return again

    def test_a_request_made_under_the_rules_stays_when_its_finding_is_judged_again_with_no_measurement_or_with_another_verdict(self):
        agreed = verdicts(("agree", (), "Fine."))
        for old in (False, True):  # old: made before the marker, and marked by the first Watch, when its finding met the rules
            for label, second, skeptic, reason in (("no measurement", switch("r1", evidence=[]), agreed, UNMEASURED),
                                                   ("the second AI disagrees", switch("r1"), verdicts(("disagree", ("It may not be possible.",), "No.")), UNCONFIRMED),
                                                   ("the first AI is less sure", switch("r1", confidence=0.45), agreed, UNCONFIRMED),
                                                   ("the second AI gives no verdict", switch("r1"), json.dumps({"verdicts": []}), UNCONFIRMED)):
                with self.subTest(label, old=old):
                    self.first(switch("r1"), toolbox(), agreed, old=old)
                    if old:
                        self.assertEqual(self.extras.approvals.hold_back_empty(), [], "the first Watch: the finding meets the rules, so nothing is taken back, and the request is marked")
                    again = self.judged_again(second, toolbox(), skeptic)
                    self.assertEqual((again.result.not_asked, unasked(again)), ({}, []), "a request is open for it, so it is no case that nobody is asked about: the end note does not count it")
                    case = self.extras.store.case_get(self.h.store.cases_recent()[0].case_id)
                    self.assertEqual(why_not_ask(case), reason, "the finding as it is judged now would not be asked about")
                    self.assertEqual(self.extras.approvals.hold_back_empty(), [], "but nobody takes back a request that was asked under these rules, and says that the rules changed")
                    kept = self.extras.store.plan_get(self.plan.plan_id)
                    self.assertEqual((kept.state, taken_back(kept), case.plan_id), ("open", "", self.plan.plan_id), "the request stays open and is chased, and the case stays linked to it")

    def test_a_request_made_before_the_marker_gets_it_once_when_it_meets_the_rules_sealed_again_with_its_code_and_one_that_a_person_answered_is_left_alone(self):
        agreed = verdicts(("agree", (), "Fine."))
        self.first(switch("r1"), toolbox(), agreed, old=True)
        old = self.extras.store.plan_get(self.plan.plan_id)
        self.assertEqual((ASKED_UNDER in old.preconditions, plan_digest.digest_of(old) == old.digest), (False, True))
        self.assertEqual(self.extras.approvals.hold_back_empty(), [])
        marked = self.extras.store.plan_get(self.plan.plan_id)
        self.assertEqual((marked.preconditions[ASKED_UNDER], marked.state, marked.code, marked.approvers), (ASKING_RULES, "open", old.code, old.approvers))
        self.assertEqual((plan_digest.digest_of(marked) == marked.digest, marked.digest != old.digest), (True, True), "sealed again, and the code that a card or a letter carries stays")
        self.assertEqual(self.extras.approvals.hold_back_empty(), [])
        self.assertEqual(self.extras.store.plan_get(self.plan.plan_id), marked, "once: a second Watch writes nothing")
        self.first(switch("r1"), toolbox(), agreed, old=True)
        self.extras.store.decision_put(make_decision(plan_id=self.plan.plan_id, approver_oid="oid-ann", decision="later"))
        self.assertEqual(self.extras.approvals.hold_back_empty(), [])
        self.assertNotIn(ASKED_UNDER, self.extras.store.plan_get(self.plan.plan_id).preconditions, "a request that a person put off is theirs: nothing is written to it")
        self.first(switch("r1"), toolbox(), agreed, old=True)
        case = self.h.store.cases_recent()[0]
        self.extras.store.case_put(replace(case, saving_usd_month=0.0))
        self.assertEqual(why_not_ask(self.extras.store.case_get(case.case_id)), UNPRICED)
        self.assertEqual(self.extras.approvals.hold_back_empty(), [], "a request that was asked with a saving stays")
        self.assertNotIn(ASKED_UNDER, self.extras.store.plan_get(self.plan.plan_id).preconditions, "but its finding does not meet the rules today, so it is not marked as asked under them")

    def test_a_request_made_before_the_rules_is_taken_back_once_with_the_reason_rules_when_its_finding_does_not_meet_them_at_the_first_watch(self):
        agreed = verdicts(("agree", (), "Fine."))
        for label, second, skeptic in (("no measurement", switch("r1", evidence=[]), agreed),
                                       ("the second AI disagrees", switch("r1"), verdicts(("disagree", ("It may not be possible.",), "No."))),
                                       ("the first AI is less sure", switch("r1", confidence=0.45), agreed)):
            with self.subTest(label):
                self.first(switch("r1"), toolbox(), agreed, old=True)
                self.judged_again(second, toolbox(), skeptic)
                taken = self.extras.approvals.hold_back_empty()
                self.assertEqual([(plan.plan_id, taken_back(plan)) for plan, _ in taken], [(self.plan.plan_id, "rules")])
                self.assertEqual(self.extras.approvals.hold_back_empty(), [], "once")
                self.assertEqual(self.extras.store.plans_open(), [])


# -- Azure Advisor's own recommendations ---------------------------------------------------------------------------------------------------------------------

NO_FIGURE_WORDS = "Meternaut counts no saving in dollars from Azure Advisor"


class WhenAnAdvisorRecommendationCountsNoSaving(unittest.TestCase):
    """A recommendation of Azure Advisor is asked about only when a saving in dollars is counted for it (brief.why_not_ask, NO_FIGURE). Two of the nine decisions of the invented list of test_advisor_parity
    are alternatives of a purchase that saves more, so Advisor's figure for them is not counted: nobody is asked about them, the History and the start page say why, and a request that an earlier version made
    for one of them is taken back when it states no saving."""

    @classmethod
    def setUpClass(cls):
        cls.watched = advisor_fixtures.Watched().run()

    def alternatives(self, watched):
        return [case for case in watched.cases() if case.facts["advisor"]["alt"]]

    def old_request(self, **changes):
        """A Watch, and the request that an earlier version made for an alternative: it states no saving, whatever `changes` say (a request that was asked while the purchase was the counted one has one)."""
        watched = advisor_fixtures.Watched().run()
        alternative = self.alternatives(watched)[0]
        plan = replace(build_advice(alternative, (TINO,), watched.clock(), watched.extras.approvals.settings), **changes)
        watched.store.plan_put(plan)
        return watched, alternative, plan

    def test_an_alternative_of_a_purchase_that_saves_more_is_not_asked_about_and_the_counted_ones_are(self):
        watched = self.watched
        self.assertEqual(len(self.alternatives(watched)), 2)
        for case in watched.cases():
            counted = not case.facts["advisor"]["alt"]
            with self.subTest(case.case_id, counted=counted):
                self.assertEqual((why_not_ask(case), bool(case.plan_id)), (None, True) if counted else (NO_FIGURE, False))
        self.assertEqual(len(watched.store.plans_open()), 7)
        self.assertEqual(learning.OpenQuestions(watched.store, watched.clock()).rows(), [], "no question for the Investigator: it is no finding of the investigation")

    def test_a_recommendation_with_no_figure_in_dollars_is_not_asked_about_whether_it_is_in_euros_or_has_none(self):
        for label, change in (("euros", {"savingsCurrency": "EUR"}), ("no figure", {"annualSavingsAmount": "none"})):
            with self.subTest(label):
                watched = advisor_fixtures.Watched(advisor_fixtures.estate({SUBSCRIPTION: [], advisor_fixtures.SUB_B: [advisor_fixtures.rec(advisor_fixtures.VM, advisor_fixtures.SUB_B, 1, **change)]})).run()
                (case,) = watched.cases()
                self.assertEqual((why_not_ask(case), watched.store.plans_open(), case.status), (NO_FIGURE, [], "needs_human"))
                self.assertEqual(Approvals(watched.store, ApprovalSettings(change_scopes=())).advise(case, (TINO,)), None)

    def test_the_words_are_plain_and_say_what_is_counted_and_not_that_advisor_gave_nothing_because_an_alternative_has_a_figure_of_its_own(self):
        self.assertEqual(NOT_ASKED[NO_FIGURE], NO_FIGURE_WORDS)
        (alternative, *_) = self.alternatives(self.watched)
        self.assertGreater(alternative.facts["advisor"]["low"], 0, "Advisor gave a figure for it, so 'Advisor gave no saving' would be untrue; what is true is that none is counted")

    def test_a_recommendation_that_cannot_say_what_to_look_at_keeps_its_own_reason_and_its_held_note(self):
        case = make_case(case_id="kold", detector=ADVISOR, status="needs_human", resource_id=f"/subscriptions/{SUBSCRIPTION}", resource_type="microsoft.subscriptions/subscriptions", resource_name="",
                         resource_group="", subscription_id=SUBSCRIPTION, plan_id=None, saving_usd_month=None, cost_usd_30d=None, facts={"category": "cost", "impact": "high"}, advice={})
        self.assertEqual((says_nothing(case), why_not_ask(case)), (True, None), "the four whole-subscription findings with no words are held back for nothing to say, as before")

    def test_the_waste_that_meternaut_planted_and_the_older_checks_are_asked_about_all_the_same_with_a_saving_of_nothing(self):
        for detector in ("orphan-managed-disk", "orphan-public-ip", "orphan-private-endpoint", "stopped-vm", "empty-app-service-plan", "load-balancer-without-backends"):
            with self.subTest(detector):
                case = make_case(case_id=f"k{detector}", detector=detector, status="needs_human", recommendation="change", saving_usd_month=0.0, cost_usd_30d=0.0, owner={"lookedUp": True})
                self.assertIsNone(why_not_ask(case))
                plan = Approvals(MemoryStore(), ApprovalSettings(change_scopes=())).advise(case, (TINO,))
                self.assertEqual(plan is not None and (plan.family, plan.saving_usd_month), ("advise", None), "a request that states no saving is made for it, as it always was")
        no_figure = make_case(case_id="kadvisor", detector=ADVISOR, status="needs_human", recommendation="change", saving_usd_month=None, cost_usd_30d=0.0,
                              facts={"category": "cost", "advisor": {"n": 1, "usd": 0.0, "low": 0.0, "high": 0.0, "alt": "", "rows": [["Standard_D2s_v6", 1, "x", "P1Y", None, "EUR", 30, "Single"]]}},
                              advice={"problem": "Buy reservations", "solution": "Buy reservations"})
        self.assertEqual((why_not_ask(no_figure), Approvals(MemoryStore(), ApprovalSettings(change_scopes=())).advise(no_figure, (TINO,))), (NO_FIGURE, None), "and a recommendation of Advisor with none is not")

    def test_a_disk_that_meternaut_planted_is_asked_about_when_advisor_lists_it_with_a_figure_of_nothing(self):
        lists, _ = advisor_fixtures.the_list()
        tenant = advisor_fixtures.estate(lists)
        row = disk_row("planted-disk-1", GROUP, tags=PLANTED, timeCreated="2026-01-02T10:00:00+00:00")
        lists[SUBSCRIPTION][-3] = advisor_fixtures.rec(advisor_fixtures.DISKS, SUBSCRIPTION, 0, annual=0.0, resource=row["id"])
        tenant.graph["orphan-managed-disk"] = [row]
        watched = advisor_fixtures.Watched(tenant).run()
        (case,) = [c for c in watched.store.cases_recent() if c.detector == "orphan-managed-disk"]
        (plan,) = [p for p in watched.store.plans_open() if p.case_id == case.case_id]
        self.assertEqual((plan.family, plan.saving_usd_month or 0, case.facts["advisor"]["usd"], why_not_ask(case)), ("delete-disk", 0, 0.0, None))

    def test_an_old_request_that_states_no_saving_is_taken_back_by_the_watch_with_the_reason_rules_and_its_case_stays(self):
        watched, alternative, plan = self.old_request()
        self.assertIsNone(plan.saving_usd_month)
        watched.clock.advance(days=1)
        watched.run()
        kept = watched.store.plan_get(plan.plan_id)
        self.assertEqual((kept.state, taken_back(kept), watched.store.case_get(alternative.case_id).status), ("expired", "rules", "needs_human"))
        self.assertEqual([e["reason"] for e in of_type(watched.events, "case.held") if e["caseId"] == alternative.case_id], ["held back: Meternaut's rules changed"])
        self.assertTrue(any("held back: Meternaut's rules changed" in e["note"] for e in of_type(watched.events, "run.note")), "the Watch counts it")
        self.assertEqual(len(watched.store.plans_open()), 7, "every request of a counted purchase is as it was")
        watched.clock.advance(days=1)
        watched.run()
        self.assertEqual((len(watched.store.plans_open()), of_type(watched.events, "case.held")), (7, []), "once: no request is made again for it, and the History does not say it again")

    def test_a_request_that_was_asked_with_a_saving_stays_whatever_the_figure_of_its_case_is_now_and_so_does_one_that_a_person_put_off(self):
        for label, changes, decided in (("asked with a saving", {"saving_usd_month": 44.5}, False), ("put off", {}, True)):
            with self.subTest(label):
                watched, _, plan = self.old_request(**changes)
                if decided:
                    watched.store.decision_put(make_decision(plan_id=plan.plan_id, approver_oid=TINO, decision="later"))
                self.assertEqual(watched.extras.approvals.hold_back_empty(), [])
                watched.clock.advance(days=1)
                watched.run()
                self.assertEqual((watched.store.plan_get(plan.plan_id).state, len(watched.store.plans_open())), ("open", 8))

    def test_the_request_of_the_counted_purchase_of_a_pair_is_untouched_and_the_alternative_comes_back_when_the_counted_one_goes(self):
        fx = advisor_fixtures
        lists = {SUBSCRIPTION: [], fx.SUB_B: fx.variants(fx.VM, fx.SUB_B, 250.0, 0, sku=fx.D2S) + fx.variants(fx.SAVINGS_PLAN, fx.SUB_B, 450.0, 30, lookbacks=(30,))}
        watched = fx.Watched(fx.estate(lists)).run()
        reservation, plan_of_savings = watched.case(fx.VM, fx.SUB_B), watched.case(fx.SAVINGS_PLAN, fx.SUB_B)
        self.assertEqual((reservation.facts["advisor"]["alt"], reservation.plan_id, why_not_ask(reservation)), ("savings plan", None, NO_FIGURE), "the reservation is the alternative")
        (counted,) = watched.store.plans_open()
        self.assertEqual((counted.case_id, counted.saving_usd_month), (plan_of_savings.case_id, round(585.0 / 12, 2)))
        watched.clock.advance(days=1)
        watched.run()
        self.assertEqual(watched.store.plans_open(), [counted], "a Watch of the same list changes nothing")
        watched.tenant.advisor_of = {SUBSCRIPTION: [], fx.SUB_B: fx.variants(fx.VM, fx.SUB_B, 250.0, 0, sku=fx.D2S)}  # the savings plan is bought: Advisor lists it no more
        watched.clock.advance(days=1)
        watched.run()
        (asked,) = watched.store.plans_open()
        self.assertEqual((asked.case_id, asked.saving_usd_month, watched.store.plan_get(counted.plan_id).state), (reservation.case_id, round(267.5 / 12, 2), "expired"))
        self.assertEqual([e["caseKey"] for e in of_type(watched.events, "plan.created")], [reservation.case_id], "the alternative is asked about as soon as it counts a saving")

    def test_the_history_says_once_why_nobody_is_asked_about_an_alternative(self):
        watched = advisor_fixtures.Watched().run()
        held = of_type(watched.events, "case.held")
        self.assertEqual([(e["detector"], e["reason"]) for e in held], [(ADVISOR, f"held back: {NO_FIGURE_WORDS}")] * 2)
        self.assertEqual({e["caseId"] for e in held}, {case.case_id for case in self.alternatives(watched)})
        self.assertIn(f"2 findings held back: {NO_FIGURE_WORDS}", [e["note"] for e in of_type(watched.events, "run.note")])
        watched.clock.advance(days=1)
        watched.run()
        self.assertEqual((of_type(watched.events, "case.held"), [e for e in of_type(watched.events, "run.note") if NO_FIGURE_WORDS in e["note"]]), ([], []), "it is not said again at each Watch")

    def test_the_start_page_counts_them_by_cause_and_says_that_meternaut_and_not_the_ai_looks_again(self):
        watched = advisor_fixtures.Watched().run()
        content = Console(store=watched.store).get("/").content
        self.assertIn("Held back: 2 findings", content)
        self.assertIn(f"Nobody is asked about 2 findings yet. For both of them, {NO_FIGURE_WORDS}. Meternaut looks at them again at its next search.", content)
        watched.store.case_put(make_advice_case(case_id="case3500", resource_id="/subscriptions/x/resourceGroups/rg/providers/p/t/dear", resource_name="dear", plan_id=None, saving_usd_month=None, cost_usd_30d=848.0, objections=()))
        content = Console(store=watched.store).get("/").content
        self.assertIn(f"Nobody is asked about 3 findings yet. For 1 of them, Meternaut could not work out from the bill what a change would save. For 2, {NO_FIGURE_WORDS}. Meternaut looks at them again at its next search.",
                      content)

    def test_a_request_for_the_same_subscription_does_not_hide_an_alternative_and_an_answer_to_it_takes_the_alternative_out_of_the_count(self):
        watched = advisor_fixtures.Watched().run()
        alternative = self.alternatives(watched)[0]
        asked_about_the_subscription = [p for p in watched.store.plans_open() if p.resource_id.lower() == alternative.resource_id.lower()]
        self.assertTrue(asked_about_the_subscription, "the counted purchases of the same subscription have requests about the same resource id")
        self.assertIn("Held back: 2 findings", Console(store=watched.store).get("/").content)
        watched.store.plan_put(replace(build_advice(alternative, (TINO,), watched.clock(), watched.extras.approvals.settings), state="withdrawn"))
        self.assertIn("Held back: 1 finding", Console(store=watched.store).get("/").content, "a person who said that it is not theirs lately is not asked again, and it is not counted")
