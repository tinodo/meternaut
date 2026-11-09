"""A finding that asks for a look at many resources is one case and one question to a person (cases/investigate.py), and its brief says so (cases/brief.py): the headline, the rows,
the page, the letters and the card. Every name, id and number in it is INVENTED.

The first classes run the real investigation with a fake Foundry and a fake toolbox (the harness of test_investigate) and read what it keeps. The others work on the case that it keeps.
"""
import dataclasses
import json
import unittest

import support  # noqa: F401  (it puts the app on the path)
from test_investigate import OID, SAFE, FakeFoundry, FakeToolbox, Harness, Moving, answer, entry, finding, key_of, loop_for, metrics, resource, verdicts
from test_letters import BASE, CONTACTS, MOST_WORDS, PERSON, word_count
from test_unread import page_of
from test_web_support import NOW as WEB_NOW, SUB, TINO, Console, make_advice_case

from cases import approvals, brief, cards, investigate, learning, letters
from cases.approvals import ADVICE_MIN_USD, why_not_ask
from cases.decide import NO_MEASUREMENT
from cases.models import ADVISE, GROUP_FACT, Principal

TYPE = "microsoft.network/privateendpoints"
HOSTILE_NAME = "<script>alert(1)</script>\n[click](https://evil.example/x) \u202eevil " + "n" * 200
HEADLINE = "Look at 60 private endpoints in 14 groups, the first is pe-60"


def absent() -> dict:
    """What the real toolbox records for a measurement that has no data in the window: a total that is not there."""
    return {"metrics": {"Traffic": {"total": None, "days": 30, "days_with_data": 0, "totals": [None]}}}


def endpoints(count: int, cost=float, **changes) -> list:
    """`count` resources of one type in 14 resource groups, the higher number the dearer: 60 of them cost 1,830 US dollars together."""
    return [resource(n, resource_type=TYPE, name=f"pe-{n:02d}", resource_group=f"rg-{n % 14:02d}", cost_usd_30d=cost(n), **changes) for n in range(1, count + 1)]


def raw_of(count: int, **changes) -> dict:
    """One finding of the Investigator that asks for a look at `count` resources, none of which has data to measure."""
    values = dict(handles=[f"r{n}" for n in range(1, count + 1)], basis="other", proposal="investigate", confidence=0.4, summary="These resources have no data in the window.", evidence=[])
    values.update(changes)
    return finding(**values)


def watch(raw, resources, *, clock=None, extras=None, skeptic=None, evidence=None, contexts=None) -> Harness:
    """One Watch over a fake estate. The clock and the loop (the store) are the ones to pass again for a second Watch."""
    clock = clock or Moving()
    toolbox = FakeToolbox(resources, evidence if evidence is not None else {r.handle: absent() for r in resources})
    h = Harness(FakeFoundry(answer(*(raw if isinstance(raw, list) else [raw])), skeptic), toolbox, clock=clock, extras=extras if extras is not None else loop_for(clock))
    if contexts is not None:
        h.contexts = contexts
    h.go()
    return h


def only_case(h: Harness):
    (case,) = h.store.cases_recent()
    return case


class WhenAFindingToInvestigateCoversManyResources(unittest.TestCase):
    def test_sixty_resources_are_one_case_and_one_request_when_what_is_at_stake_is_enough(self):
        h = watch(raw_of(60), endpoints(60))
        case = only_case(h)
        (plan,) = h.store.plans_open()
        self.assertEqual((h.result.cases, h.result.needs_human, h.result.proposed), (1, 1, 0))
        self.assertEqual((case.case_id, case.resource_name, case.status, case.recommendation, case.saving_usd_month, case.cost_usd_30d),
                         (key_of(endpoints(60)[-1]), "pe-60", "needs_human", "investigate", None, 1830.0), "the case of the dearest, with what all of them cost")
        self.assertEqual((plan.family, plan.case_id, case.plan_id, plan.saving_usd_month), (ADVISE, case.case_id, plan.plan_id, None))
        self.assertGreaterEqual(case.cost_usd_30d, ADVICE_MIN_USD)
        self.assertIsNone(why_not_ask(case))
        self.assertEqual(plan.title, HEADLINE)

    def test_the_same_finding_that_cost_little_is_held_back_as_before_and_stays_an_open_question(self):
        for cost, held in ((0.5, True), (4.99, True), (5.0, False), (20.0, False)):
            with self.subTest(cost=cost):
                h = watch(raw_of(10, confidence=0.8), endpoints(10, cost=lambda n: cost))
                case = only_case(h)
                self.assertEqual(case.cost_usd_30d, round(10 * cost, 2))
                self.assertEqual((why_not_ask(case) is not None, h.store.plans_open() == [], case.plan_id is None), (held, held, held))
                self.assertEqual(learning.OpenQuestions(h.store, h.clock()).is_open(case), held, "a case with no request is an open question that the Investigator gets again")

    def test_the_case_keeps_what_the_group_is_as_typed_facts(self):
        case = only_case(watch(raw_of(60), endpoints(60)))
        together = case.facts[GROUP_FACT]
        self.assertEqual({key: together[key] for key in ("count", "costUsd30d", "type", "groups")}, {"count": 60, "costUsd30d": 1830.0, "type": TYPE, "groups": 14})
        self.assertEqual(together["names"], [f"pe-{n}" for n in range(59, 47, -1)], "the twelve dearest of the others, the dearest first")
        self.assertEqual(case.facts["costUsd30d"], 1830.0, "the facts of the case say what the case costs")
        self.assertEqual((case.facts["basis"], case.facts["proposal"], case.facts["finding"]), ("other", "investigate", 1))
        json.dumps(case.facts)

    def test_the_history_has_one_line_for_the_case_with_the_size_of_the_group_and_no_other_line_has_that_field(self):
        raw = [raw_of(8, handles=[f"r{n}" for n in range(1, 9)]), raw_of(3, handles=[f"r{n}" for n in range(9, 12)], proposal="delete")]
        h = watch(raw, endpoints(11))
        results = h.of("case.result")
        self.assertEqual([(r["resourceName"], r.get("groupSize"), r["costUsd30d"]) for r in results],
                         [("pe-08", 8, 36.0), ("pe-11", None, 11.0), ("pe-10", None, 10.0), ("pe-09", None, 9.0)])
        self.assertEqual(len({r["caseId"] for r in results}), 4)
        self.assertEqual((h.result.cases, len(h.store.cases_recent())), (4, 4))
        first, second = h.of("investigation.finding")
        self.assertEqual((first["handles"], second["handles"]), (8, 3))

    def test_five_resources_are_five_cases_and_six_are_one(self):
        self.assertEqual(investigate.GROUP_MIN, 5)
        five = watch(raw_of(5), endpoints(5, cost=lambda n: 100.0))
        self.assertEqual((five.result.cases, len(five.store.cases_recent()), len(five.store.plans_open())), (5, 5, 5))
        self.assertTrue(all(GROUP_FACT not in c.facts for c in five.store.cases_recent()))
        self.assertTrue(all(r.get("groupSize") is None for r in five.of("case.result")))
        six = watch(raw_of(6), endpoints(6, cost=lambda n: 100.0))
        self.assertEqual((six.result.cases, len(six.store.cases_recent()), len(six.store.plans_open())), (1, 1, 1))
        self.assertEqual(only_case(six).facts[GROUP_FACT]["count"], 6)

    def test_a_delete_and_a_change_are_never_one_case(self):
        for proposal in ("delete", "change"):
            with self.subTest(proposal=proposal):
                h = watch(raw_of(8, proposal=proposal), endpoints(8))
                cases = h.store.cases_recent()
                self.assertEqual((h.result.cases, len(cases)), (8, 8))
                self.assertTrue(all(GROUP_FACT not in c.facts for c in cases))
                self.assertTrue(all(r.get("groupSize") is None for r in h.of("case.result")))

    def test_a_finding_with_the_basis_of_a_measurement_is_one_case_too_when_it_asks_for_a_look(self):
        evidence = {f"r{n}": metrics(Traffic=0) for n in range(1, 9)}
        raw = raw_of(8, basis="low-usage", evidence=[entry(f"r{n}", "Traffic", 0) for n in range(1, 9)])
        h = watch(raw, endpoints(8), evidence=evidence)
        case = only_case(h)
        self.assertEqual((case.facts[GROUP_FACT]["count"], case.status, case.objections, h.result.unmeasured), (8, "needs_human", (), 0))

    def test_the_resources_that_a_guard_holds_are_not_part_of_the_group_and_five_that_are_left_are_five_cases(self):
        guarded = [resource(n, resource_type=TYPE, name=f"pe-{n:02d}", resource_group="rg-00", cost_usd_30d=float(n), **({"tags": {"keep": "yes"}} if n > 7 else {})) for n in range(1, 11)]
        h = watch(raw_of(10), guarded)
        case = only_case(h)
        self.assertEqual((case.facts[GROUP_FACT]["count"], case.facts[GROUP_FACT]["names"], case.cost_usd_30d), (7, [f"pe-0{n}" for n in range(6, 0, -1)], 28.0))
        (line,) = h.of("investigation.finding")
        self.assertEqual((line["handles"], line["guarded"], h.result.guarded), (7, 3, 3))
        five_left = watch(raw_of(8), [resource(n, resource_type=TYPE, name=f"pe-{n:02d}", cost_usd_30d=float(n), **({"tags": {"keep": "yes"}} if n > 5 else {})) for n in range(1, 9)])
        self.assertEqual((five_left.result.cases, len(five_left.store.cases_recent())), (5, 5))

    def test_the_dearest_resource_is_the_one_that_the_case_belongs_to_and_the_first_one_when_the_cost_is_the_same(self):
        equal = watch(raw_of(8), endpoints(8, cost=lambda n: 10.0))
        self.assertEqual(only_case(equal).resource_name, "pe-01", "the first handle of the finding")
        reversed_ = watch(raw_of(8, handles=[f"r{n}" for n in range(8, 0, -1)]), endpoints(8, cost=lambda n: 10.0))
        self.assertEqual(only_case(reversed_).resource_name, "pe-08")
        one_dearer = watch(raw_of(8), endpoints(8, cost=lambda n: 99.0 if n == 3 else 10.0))
        case = only_case(one_dearer)
        self.assertEqual((case.resource_name, case.case_id, case.cost_usd_30d), ("pe-03", key_of(resource(3)), 169.0))
        self.assertEqual(case.facts[GROUP_FACT]["names"][:2], ["pe-01", "pe-02"], "the others in the order of their cost, the first handle first")

    def test_the_cost_is_the_sum_of_the_known_costs_and_none_when_no_cost_line_was_read(self):
        no_costs = dataclasses.replace(SAFE, costs=None, currency=None)
        some = watch(raw_of(8), endpoints(8, cost=lambda n: 5.0 if n <= 2 else None), contexts={SUB: no_costs} | {support.SUBSCRIPTION: no_costs})
        case = only_case(some)
        self.assertEqual((case.cost_usd_30d, case.facts[GROUP_FACT]["costUsd30d"], case.resource_name), (10.0, 10.0, "pe-01"))
        none = watch(raw_of(8), endpoints(8, cost=lambda n: None), contexts={support.SUBSCRIPTION: no_costs})
        case = only_case(none)
        self.assertEqual((case.cost_usd_30d, case.facts[GROUP_FACT]["costUsd30d"], case.facts["costUsd30d"], none.store.plans_open()), (None, None, None, []))

    def test_the_status_comes_from_decide_with_the_verdict_of_the_finding_as_for_any_resource(self):
        for label, raw, skeptic, objections in (("it agrees", raw_of(8, confidence=0.99), None, (NO_MEASUREMENT,)),
                                                ("it disagrees", raw_of(8), verdicts(("disagree", ("It may be needed.",), "No.")), (NO_MEASUREMENT, "It may be needed.")),
                                                ("it is unsure", raw_of(8), verdicts(("unsure", (), "The window is short.")), (NO_MEASUREMENT, "The window is short."))):
            with self.subTest(label):
                h = watch(raw, endpoints(8), skeptic=skeptic)
                case = only_case(h)
                self.assertEqual((case.status, case.recommendation, case.objections, case.saving_usd_month), ("needs_human", "investigate", objections, None))
                self.assertEqual((h.result.cases, h.result.proposed), (1, 0))
        no_verdict = watch(raw_of(8), endpoints(8), skeptic=json.dumps({"verdicts": []}))
        self.assertEqual(only_case(no_verdict).steps[-1]["ok"], False, "the finding got no verdict, and the case says so as every case does")

    def test_the_resources_that_nothing_measured_are_counted_one_by_one_and_the_case_is_backed_as_its_own_resource_is(self):
        resources = endpoints(60)
        evidence = {r.handle: (metrics(Traffic=0) if r.handle == "r60" else absent()) for r in resources}
        h = watch(raw_of(60, evidence=[entry("r60", "Traffic", 0)]), resources, evidence=evidence)
        case = only_case(h)
        self.assertEqual((h.result.unmeasured, case.objections), (59, ()))
        (line,) = h.of("investigation.finding")
        self.assertEqual((line["handles"], line["unmeasured"]), (60, 59))
        every = watch(raw_of(60), endpoints(60))
        self.assertEqual((every.result.unmeasured, only_case(every).objections), (60, (NO_MEASUREMENT,)))
        self.assertIn("60 resources of the findings have no measurement that backs the finding, so a person has to judge them", every.notes)

    def test_the_cap_of_cases_counts_the_resources_and_not_the_cases(self):
        raw = [raw_of(40), raw_of(30, handles=[f"r{n}" for n in range(41, 71)])]
        h = watch(raw, endpoints(70))
        first, second = h.of("investigation.finding")
        self.assertEqual((first["handles"], first["capped"], second["handles"], second["capped"]), (40, 0, 20, 10))
        by_name = {r["resourceName"]: r for r in h.of("case.result")}
        self.assertEqual((sorted(by_name), by_name["pe-40"]["groupSize"], by_name["pe-70"]["groupSize"], h.result.cases), (["pe-40", "pe-70"], 40, 20, 2),
                         "the two groups take the sixty places, and the second one has the twenty that are left")
        self.assertIn("10 resources of the findings are not listed as cases: a run opens at most 60", h.notes)
        raw = [raw_of(40), raw_of(30, handles=[f"r{n}" for n in range(41, 71)], proposal="delete")]
        h = watch(raw, endpoints(70))
        first, second = h.of("investigation.finding")
        self.assertEqual((first["handles"], first["capped"], second["handles"], second["capped"], h.result.cases), (40, 0, 20, 10, 21), "the group takes forty of the sixty places")
        sixty = watch(raw_of(60), endpoints(70))
        self.assertEqual(only_case(sixty).facts[GROUP_FACT]["count"], 60)

    def test_the_skeptic_is_shown_every_resource_of_the_group_as_before(self):
        h = watch(raw_of(60), endpoints(60))
        (seen,) = json.loads(h.foundry.inputs()[1])["findings"]
        self.assertEqual((seen["resources"], seen["evidenceShown"], seen["costUsd30d"]), (60, 60, 1830.0))

    def test_a_group_of_workspaces_is_not_shown_the_analysis_of_the_first_of_them(self):
        from test_unread import COST, evidence_of
        from cases import unread
        resources = [resource(n, resource_type=unread.WORKSPACE, name=f"ws-{n}", cost_usd_30d=COST) for n in range(1, 8)]
        h = watch(raw_of(7, evidence=[]), resources, evidence={r.handle: evidence_of() for r in resources})
        case = only_case(h)
        self.assertEqual((case.facts[GROUP_FACT]["count"], "unread" in case.facts), (7, False), "the figure and the rows of one workspace do not stand for seven")
        b = brief.build_brief(case, None, now=WEB_NOW)
        self.assertEqual((b.unread, b.options, b.saving.monthly), (None, (), None))
        self.assertEqual(b.headline, "Look at 7 Log Analytics workspaces in 1 group, the first is ws-1")


class WhenTheSameFindingComesAgain(unittest.TestCase):
    """The case belongs to one resource, so a Watch that finds the group again has to find that case and not make another case and another request."""

    def principal(self):
        return Principal(OID, "Tino", ("owner", "approver", "ops"))

    def answer(self, extras, plan, decision):
        nonce = extras.store.nonce_new(OID, plan.plan_id)
        return extras.approvals.decide(self.principal(), plan.plan_id, decision, plan.code, nonce)

    def test_a_group_that_was_judged_lately_with_the_same_evidence_adds_nothing_while_its_request_is_open(self):
        clock = Moving()
        first = watch(raw_of(60, confidence=0.8), endpoints(60), clock=clock)
        extras = first.extras
        before = {c.case_id: c for c in extras.store.cases_recent()}
        plans = extras.store.plans_open()
        self.assertEqual((len(before), len(plans)), (1, 1))
        clock.advance(days=1)
        second = watch(raw_of(60, confidence=0.8), endpoints(60), clock=clock, extras=extras)
        (line,) = second.of("investigation.finding")
        self.assertEqual((second.result.cases, second.result.kept, line["judgedLately"], line["kept"], line["handles"]), (0, 0, 60, False, 0))
        self.assertEqual(line["reason"], "no resource of it is left: 60 judged lately")
        self.assertEqual(len(second.foundry.runs), 1, "no finding is left, so the Skeptic is not asked")
        self.assertEqual({c.case_id: c for c in extras.store.cases_recent()}, before, "the case is not touched")
        self.assertEqual(extras.store.plans_open(), plans, "and no second request is made")

    def test_a_group_whose_first_ai_was_not_sure_is_taken_up_again_at_once_and_is_still_one_case_with_one_request(self):
        clock = Moving()
        first = watch(raw_of(60), endpoints(60), clock=clock)
        extras = first.extras
        (plan,) = extras.store.plans_open()
        clock.advance(days=1)
        second = watch(raw_of(60), endpoints(60), clock=clock, extras=extras)
        case = only_case(second)
        self.assertEqual((second.result.cases, case.runs_seen, case.plan_id, extras.store.plans_open()), (1, 2, plan.plan_id, [plan]))

    def test_the_costs_that_moved_do_not_make_another_resource_the_one_that_the_case_belongs_to(self):
        clock = Moving()
        first = watch(raw_of(60), endpoints(60), clock=clock)
        extras = first.extras
        (case,) = extras.store.cases_recent()
        (plan,) = extras.store.plans_open()
        clock.advance(days=1)
        second = watch(raw_of(60), endpoints(60, cost=lambda n: 1000.0 - n), clock=clock, extras=extras)
        again = only_case(second)
        self.assertEqual((again.case_id, again.resource_name, again.runs_seen, again.plan_id, extras.store.plans_open()), (case.case_id, "pe-60", 2, plan.plan_id, [plan]))
        self.assertEqual((again.cost_usd_30d, again.facts[GROUP_FACT]["names"][0]), (58170.0, "pe-01"), "the figures are the new ones")
        fresh = watch(raw_of(60), endpoints(60, cost=lambda n: 1000.0 - n))
        self.assertEqual(only_case(fresh).resource_name, "pe-01", "without an earlier case the dearest is the one")

    def test_a_group_that_a_person_answered_is_left_alone_for_the_days_of_the_recheck_and_is_not_asked_again_for_thirty(self):
        clock = Moving()
        first = watch(raw_of(60, confidence=0.8), endpoints(60), clock=clock)
        extras = first.extras
        (plan,) = extras.store.plans_open()
        self.assertTrue(self.answer(extras, plan, "decline").ok)
        (case,) = extras.store.cases_recent()
        self.assertEqual((case.status, extras.store.plan_get(plan.plan_id).state), ("declined", "declined"), "the answer is the answer of the case of the group, as for one resource")
        clock.advance(days=2)
        second = watch(raw_of(60, confidence=0.8), endpoints(60), clock=clock, extras=extras)
        self.assertEqual(second.result.cases, 0)
        clock.advance(days=6)
        third = watch(raw_of(60, confidence=0.8), endpoints(60), clock=clock, extras=extras)
        self.assertEqual((third.result.cases, only_case(third).runs_seen), (1, 2), "after the days of the recheck the group is judged again")
        self.assertEqual(extras.store.plans_open(), [], "a finding that a person answered is not put to them again for thirty days")

    def test_a_request_that_nobody_answered_is_made_again_for_the_same_case_once_the_days_of_the_recheck_have_passed(self):
        clock = Moving()
        first = watch(raw_of(60, confidence=0.8), endpoints(60), clock=clock)
        extras = first.extras
        (plan,) = extras.store.plans_open()
        clock.advance(hours=73)
        self.assertEqual(len(extras.approvals.expire()), 1)
        self.assertEqual(watch(raw_of(60, confidence=0.8), endpoints(60), clock=clock, extras=extras).result.cases, 0)
        clock.advance(days=8)
        third = watch(raw_of(60, confidence=0.8), endpoints(60), clock=clock, extras=extras)
        case = only_case(third)
        (again,) = extras.store.plans_open()
        self.assertEqual((third.result.cases, again.case_id, again.plan_id == plan.plan_id), (1, case.case_id, False))

    def test_the_resources_that_older_runs_made_a_case_of_one_by_one_stay_as_they_were(self):
        clock = Moving()
        first = watch(raw_of(5, confidence=0.8), endpoints(5, cost=lambda n: 100.0), clock=clock)
        extras = first.extras
        before = {c.case_id: c for c in extras.store.cases_recent()}
        self.assertEqual(len(before), 5)
        clock.advance(days=1)
        second = watch(raw_of(8, confidence=0.8), endpoints(8, cost=lambda n: 100.0), clock=clock, extras=extras)
        self.assertEqual((second.result.cases, len(extras.store.cases_recent())), (3, 8), "the five that were judged lately are not taken up again, and three are new")


class TheBriefOfAGroup(unittest.TestCase):
    def setUp(self):
        self.h = watch(raw_of(60), endpoints(60))
        self.case = only_case(self.h)
        (self.plan,) = self.h.store.plans_open()
        self.b = brief.build_brief(self.case, self.plan, now=WEB_NOW, may_answer=True)

    def test_the_headline_says_how_many_of_what_in_how_many_groups_and_names_the_first(self):
        self.assertEqual(self.b.headline, HEADLINE)
        self.assertEqual((self.plan.title, brief.plan_headline(self.plan)), (HEADLINE, HEADLINE))
        self.assertEqual(brief.build_brief(self.case, None, now=WEB_NOW).headline, HEADLINE, "the case without a request says the same")
        self.assertEqual((self.b.group.count, self.b.group.groups, self.b.kind), (60, 14, "advice"))

    def test_the_rows_say_what_it_covers_what_it_costs_together_and_give_examples_and_the_cost_row_of_one_resource_is_not_there(self):
        self.assertEqual([(f.label, f.value, f.source) for f in self.b.facts[:3]],
                         [("Covers", "60 private endpoints in 14 resource groups", "Azure Resource Graph"),
                          ("Together they cost", "1,830.00 US dollars in the last 30 days", "Azure cost lines"),
                          ("Examples", "pe-60, pe-59, pe-58, pe-57, pe-56, pe-55 and 54 more", "Azure Resource Graph")])
        self.assertNotIn("Cost, last 30 days", [f.label for f in self.b.facts])
        self.assertLessEqual(len(self.b.facts), brief.MAX_FACTS)

    def test_the_answers_are_those_of_a_request_about_one_resource_and_no_figure_is_made(self):
        one = watch(raw_of(1), endpoints(1, cost=lambda n: 100.0))
        single = brief.build_brief(only_case(one), one.store.plans_open()[0], now=WEB_NOW, may_answer=True)
        self.assertEqual((self.b.answers, self.b.change, self.b.who_acts, self.b.undo, self.b.risk), (single.answers, single.change, single.who_acts, single.undo, single.risk))
        self.assertEqual((self.b.saving.monthly, self.b.saving.level, self.b.saving.waiting_per_day), (None, "", None))
        self.assertEqual(self.b.saving.why_none, "The 60 resources cost 1,830.00 US dollars together in the last 30 days. What a change would save was not worked out.")
        self.assertEqual((self.b.unread, self.b.options), (None, ()))
        self.assertEqual(single.group, None)

    def test_the_resource_that_the_case_belongs_to_is_whose_it_is_and_what_the_portal_shows(self):
        self.assertEqual((self.b.where.name, self.b.where.kind, self.b.where.group), ("pe-60", "Private endpoint", "rg-04"))
        self.assertEqual(self.b.case_id, key_of(resource(60)))

    def test_every_kind_of_resource_with_words_has_its_plural_and_a_group_is_said_in_them(self):
        for rtype, (_, noun) in brief.TYPE_WORDS.items():
            with self.subTest(type=rtype):
                plural = brief._plural(noun)
                self.assertNotEqual(plural, noun)
                self.assertTrue(plural.startswith(noun[:-1]), (noun, plural))
                self.assertEqual(brief.group_headline(brief.Group(7, 12.5, rtype, 3, ("b", "c")), "a", "investigate"), f"Look at 7 {plural} in 3 groups, the first is a")
        for noun, plural in (("private endpoint", "private endpoints"), ("public IP address", "public IP addresses"), ("Redis cache", "Redis caches"), ("app", "apps"),
                             ("resource", "resources"), ("gateway", "gateways"), ("policy", "policies"), ("box", "boxes")):
            self.assertEqual(brief._plural(noun), plural)

    def test_one_group_one_kind_that_is_not_known_and_a_name_that_is_missing_are_said_in_plain_words(self):
        for digest, headline, covers in (({"count": 6, "type": "other", "groups": 1, "names": [], "costUsd30d": 12.0}, "Look at 6 resources in 1 group, the first is pe-60", "6 resources in 1 resource group"),
                                         ({"count": 6, "type": TYPE, "names": [], "costUsd30d": 12.0}, "Look at 6 private endpoints, the first is pe-60", "6 private endpoints"),
                                         ({"count": 1200, "type": TYPE, "groups": 40, "names": ["a"], "costUsd30d": 12.0}, "Look at 1,200 private endpoints in 40 groups, the first is pe-60",
                                          "1,200 private endpoints in 40 resource groups")):
            with self.subTest(digest=digest):
                case = group_case(digest)
                self.assertEqual(brief.build_brief(case, None, now=WEB_NOW).headline, headline)
                self.assertEqual(brief.facts_of(case)[0].value, covers)
        nameless = group_case({"count": 6, "type": TYPE, "groups": 2}, resource_name="")
        self.assertEqual(brief.build_brief(nameless, None, now=WEB_NOW).headline, "Look at 6 private endpoints in 2 groups")
        self.assertEqual([f.label for f in brief.facts_of(nameless)][:2], ["Covers", "Together they cost"], "no name, no row of examples")

    def test_the_examples_are_the_first_resource_and_the_next_five_and_what_is_left_is_counted(self):
        names = [f"n{n}" for n in range(12)]
        many = brief.facts_of(group_case({"count": 60, "type": TYPE, "groups": 2, "names": names, "costUsd30d": 1.0}))[2]
        self.assertEqual(many.value, "pe-60, n0, n1, n2, n3, n4 and 54 more")
        six = brief.facts_of(group_case({"count": 6, "type": TYPE, "groups": 2, "names": names[:5], "costUsd30d": 1.0}))[2]
        self.assertEqual(six.value, "pe-60, n0, n1, n2, n3, n4", "all of them: nothing is left to count")
        short = brief.facts_of(group_case({"count": 9, "type": TYPE, "groups": 2, "names": names[:2], "costUsd30d": 1.0}))[2]
        self.assertEqual(short.value, "pe-60, n0, n1 and 6 more")

    def test_a_digest_that_is_not_as_it_should_be_shows_less_and_never_something_else(self):
        plain_headline = "Look at the private endpoint pe-60 in group rg-60"
        good = {"count": 60, "type": TYPE, "groups": 14, "names": ["a"], "costUsd30d": 1.0}
        for label, found in (("text", "text"), ("a list", [1]), ("an empty digest", {}), ("no count", {k: v for k, v in good.items() if k != "count"}), ("a count of one", {**good, "count": 1}),
                             ("a count that is a flag", {**good, "count": True}), ("a count that is text", {**good, "count": "60"}), ("a count that is not a number", {**good, "count": float("nan")}),
                             ("a count that is not believed", {**good, "count": 10 ** 9})):
            with self.subTest(label):
                case = group_case(found)
                self.assertIsNone(brief.group_of(case))
                self.assertEqual(brief.build_brief(case, None, now=WEB_NOW).headline, plain_headline)
                self.assertEqual(brief.facts_of(case)[0].label, "Cost, last 30 days")
        self.assertIsNone(brief.group_of(None))
        self.assertIsNone(brief.group_of(make_advice_case(facts=None)))
        for bad_cost in (-5.0, float("nan"), float("inf"), "12", True, None):
            with self.subTest(cost=bad_cost):
                found = group_case({**good, "costUsd30d": bad_cost}, cost_usd_30d=None)
                self.assertIsNone(brief.group_of(found).cost)
                self.assertEqual([f.label for f in brief.facts_of(found)][:2], ["Covers", "Examples"], "no cost row without a cost")
        fallback = group_case({**good, "costUsd30d": "12"}, cost_usd_30d=7.5)
        self.assertEqual(brief.facts_of(fallback)[1].value, "7.50 US dollars in the last 30 days", "the cost of the case when the digest holds none")
        for bad_groups in (0, -1, True, "14", 61, 2.5):
            with self.subTest(groups=bad_groups):
                self.assertEqual(brief.group_of(group_case({**good, "groups": bad_groups})).groups, 0)
        for bad_type in (5, "", None, ["x"]):
            with self.subTest(type=bad_type):
                self.assertEqual(brief.group_of(group_case({**good, "type": bad_type})).kind, "other")
        found = brief.group_of(group_case({**good, "names": [5, None, "", "b", HOSTILE_NAME] + [f"x{n}" for n in range(30)]}))
        self.assertEqual(found.names[0], "b")
        self.assertLessEqual(len(found.names), brief.MAX_GROUP_NAMES)
        self.assertTrue(all(len(name) <= brief.MAX_EXAMPLE and "\n" not in name for name in found.names))
        self.assertEqual(brief.group_of(group_case({**good, "names": "text"})).names, ())

    def test_it_is_a_pure_function_of_the_records(self):
        case = self.case
        before = case.to_json()
        brief.build_brief(case, self.plan, now=WEB_NOW)
        self.assertEqual(case.to_json(), before)


def group_case(digest, **changes):
    """The case of a group as the store keeps it, with the digest that a test gives it."""
    values = dict(resource_type=TYPE, resource_name="pe-60", resource_group="rg-60", recommendation="investigate", saving_usd_month=None, cost_usd_30d=1830.0,
                  facts={"basis": "other", "proposal": "investigate", "metrics": {}, GROUP_FACT: digest})
    values.update(changes)
    return make_advice_case(**values)


class WhatAPersonSees(unittest.TestCase):
    def setUp(self):
        self.h = watch(raw_of(60), endpoints(60))
        self.case = only_case(self.h)
        (self.plan,) = self.h.store.plans_open()
        self.reply, self.text = page_of(self.case, self.plan)

    def test_the_page_has_the_headline_the_sentence_without_a_figure_the_rows_and_the_one_form(self):
        self.assertEqual(self.reply.status, 200)
        self.assertEqual(self.reply.headings(1), [HEADLINE])
        self.assertIn("No figure. The 60 resources cost 1,830.00 US dollars together in the last 30 days. What a change would save was not worked out.", self.text)
        self.assertIn("Covers 60 private endpoints in 14 resource groups Azure Resource Graph Together they cost 1,830.00 US dollars in the last 30 days Azure cost lines "
                      "Examples pe-60, pe-59, pe-58, pe-57, pe-56, pe-55 and 54 more Azure Resource Graph", self.text)
        self.assertTrue(self.reply.form(has_button="Worth acting on").has_button("Not worth it"))
        self.assertEqual(self.reply.problems, [])

    def test_nothing_else_on_the_page_changes_the_sections_are_those_of_any_request_about_one_resource(self):
        one = watch(raw_of(1), endpoints(1, cost=lambda n: 100.0))
        single, _ = page_of(only_case(one), one.store.plans_open()[0])
        self.assertEqual(self.reply.headings(2), single.headings(2))
        self.assertEqual(self.reply.headings(3), single.headings(3))
        self.assertEqual([button for _, _, button in self.reply.form(has_button="Worth acting on").buttons], [button for _, _, button in single.form(has_button="Worth acting on").buttons])

    def test_the_details_do_not_say_that_an_ai_saw_the_group_that_code_made(self):
        facts = {row["Fact"] for row in self.reply.table("facts").rows}
        self.assertEqual(facts, {"basis", "costUsd30d", "finding", "metrics", "proposal"})
        self.assertIn(GROUP_FACT, self.case.facts)

    def test_the_start_page_lists_the_one_decision_with_the_headline_of_the_group(self):
        plan = dataclasses.replace(self.plan, approvers=(TINO,))
        console = Console()
        console.store.case_put(self.case)
        console.store.plan_put(plan)
        text = console.get("/").main.text()
        self.assertIn("Waiting for you (1)", text)
        self.assertIn(HEADLINE, text)

    def test_the_weekly_letter_has_the_headline_and_what_the_resources_cost_together_and_stays_within_its_words(self):
        letter = letters.digest_letter(PERSON, BASE, WEB_NOW, [(self.plan, self.case)], CONTACTS)
        self.assertEqual(letter.subject, "[Meternaut] 1 decision waits for you")
        self.assertIn(f"- {HEADLINE}. Together they cost 1,830.00 US dollars in 30 days.\n", letter.text)
        self.assertLessEqual(word_count(letter), MOST_WORDS["digest"])
        self.assertEqual(letter.html.count('href="'), 1)
        self.assertTrue(letter.text.isascii())
        many = [(dataclasses.replace(self.plan, plan_id=f"plan-{n}", case_id=f"case-{n}"), dataclasses.replace(self.case, case_id=f"case-{n}")) for n in range(3)]
        three = letters.digest_letter(PERSON, BASE, WEB_NOW, many, CONTACTS)
        self.assertEqual(sum(1 for line in three.text.splitlines() if line.startswith("- ")), 3)
        self.assertLessEqual(word_count(three), MOST_WORDS["digest"])

    def test_the_decision_letter_has_the_three_rows_and_stays_within_the_words_of_a_letter(self):
        letter = letters.approval_letter(self.plan, self.case, PERSON, BASE, WEB_NOW, CONTACTS)
        for row in ("Covers: 60 private endpoints in 14 resource groups", "Together they cost: 1,830.00 US dollars in the last 30 days",
                    "Examples: pe-60, pe-59, pe-58, pe-57, pe-56, pe-55 and 54 more", "If you answer: Nothing changes in Azure. Your answer is recorded with your name."):
            self.assertIn(row, letter.text)
        self.assertIn("No figure: the 60 resources cost 1,830.00 US dollars together in the last 30 days.", letter.text)
        self.assertLessEqual(word_count(letter), MOST_WORDS["approval"])
        self.assertTrue(letter.text.isascii())
        for gone in ("?", "!", "saved", "\u2013", "\u2014"):
            self.assertNotIn(gone, letter.text.lower())

    def test_the_card_has_the_headline_and_the_first_three_rows(self):
        b = brief.build_brief(self.case, self.plan, now=WEB_NOW, may_answer=True)
        card = cards.decision_card(b, cards.CardContext(page_url=f"https://meternaut.example/ok/{self.plan.plan_id}", nonce="n" * 24))
        text = json.dumps(card)
        self.assertIn(HEADLINE, text)
        for row in ("Covers", "60 private endpoints in 14 resource groups", "Together they cost", "1,830.00 US dollars in the last 30 days", "Examples", "and 54 more"):
            self.assertIn(row, text)

    def test_the_history_and_the_start_page_know_a_request_that_was_answered_by_the_same_headline(self):
        self.assertEqual(brief.plan_headline(dataclasses.replace(self.plan, state="declined")), HEADLINE)


class WhatAHostileEstateCanDo(unittest.TestCase):
    def setUp(self):
        resources = endpoints(60)
        resources[59] = dataclasses.replace(resources[59], name=HOSTILE_NAME)
        resources[58] = dataclasses.replace(resources[58], name=HOSTILE_NAME + " second")
        self.h = watch(raw_of(60), resources)
        self.case = only_case(self.h)
        (self.plan,) = self.h.store.plans_open()

    def test_the_names_are_cut_and_cleaned_in_the_case_and_in_the_history(self):
        together = self.case.facts[GROUP_FACT]
        self.assertLessEqual(len(self.case.resource_name), 120)
        self.assertLessEqual(len(together["names"][0]), 60)
        for text in (self.case.resource_name, *together["names"], self.plan.title):
            self.assertNotIn("\n", text)
        self.assertNotIn("https://", json.dumps(self.case.facts) + self.case.resource_name)
        for event in self.h.events:
            if event["type"] == "case.result":
                self.assertNotIn("\n", event["resourceName"])
                self.assertNotIn("https://", json.dumps(event))

    def test_the_brief_says_one_line_and_cuts_the_names(self):
        b = brief.build_brief(self.case, self.plan, now=WEB_NOW)
        self.assertNotIn("\n", b.headline)
        self.assertLessEqual(len(b.headline), 200)
        self.assertTrue(b.headline.startswith("Look at 60 private endpoints in 14 groups, the first is <script>alert(1)</script>"))
        self.assertNotIn("](", b.headline)
        for fact in b.facts:
            self.assertNotIn("\n", fact.value)
            self.assertLessEqual(len(fact.value), 400)
        self.assertLessEqual(len(b.facts[2].value), 400)

    def test_the_page_escapes_them_and_the_letters_and_the_card_do_too(self):
        reply, _ = page_of(self.case, self.plan)
        self.assertNotIn("<script>", reply.text)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", reply.text)
        self.assertEqual(reply.root.find_all("script"), [])
        self.assertEqual(reply.problems, [])
        self.assertFalse([link for link in reply.links() if "evil.example" in link])
        for letter in (letters.digest_letter(PERSON, BASE, WEB_NOW, [(self.plan, self.case)], CONTACTS), letters.approval_letter(self.plan, self.case, PERSON, BASE, WEB_NOW, CONTACTS)):
            self.assertNotIn("<script>", letter.html)
            self.assertIn("&lt;script&gt;", letter.html)
            self.assertLessEqual(max(len(line) for line in letter.text.splitlines() if not line.startswith("Decide:")), 500)
        b = brief.build_brief(self.case, self.plan, now=WEB_NOW, may_answer=True)
        card = cards.decision_card(b, cards.CardContext(page_url=f"https://meternaut.example/ok/{self.plan.plan_id}", nonce="n" * 24))
        self.assertNotIn("<script>", json.dumps(card))

    def test_a_type_that_is_not_a_type_of_azure_is_other_and_the_group_is_called_resources(self):
        resources = [dataclasses.replace(r, resource_type="<script>alert(1)</script> x/y") for r in endpoints(8)]
        case = only_case(watch(raw_of(8), resources))
        self.assertEqual(case.facts[GROUP_FACT]["type"], "other")
        self.assertEqual(brief.build_brief(case, None, now=WEB_NOW).headline, "Look at 8 resources in 8 groups, the first is pe-08")
        mixed = endpoints(8)
        mixed[0] = dataclasses.replace(mixed[0], resource_type="microsoft.network/publicipaddresses")
        self.assertEqual(only_case(watch(raw_of(8), mixed)).facts[GROUP_FACT]["type"], "other", "resources of different types are resources")
        hostile = group_case({"count": 8, "type": "<script>alert(1)</script>\n" * 50, "groups": 2, "names": [], "costUsd30d": 1.0})
        self.assertEqual(brief.build_brief(hostile, None, now=WEB_NOW).headline, "Look at 8 resources in 2 groups, the first is pe-60")


class TheWordsOfTheCode(unittest.TestCase):
    def test_the_new_constants_are_the_ones_that_the_brief_reads(self):
        self.assertEqual((investigate.GROUP_MIN, investigate.MAX_GROUP_NAMES, brief.MAX_GROUP_NAMES, GROUP_FACT), (5, 12, 12, "group"))
        self.assertEqual(investigate.MAX_CASES, 60)

    def test_a_request_is_asked_for_a_group_under_the_same_worth_as_for_one_resource(self):
        self.assertEqual((approvals.ADVICE_MIN_USD, approvals.ADVICE_OPEN_MAX), (50.0, 10))


if __name__ == "__main__":
    unittest.main()
