"""Missing data is not zero, a resource that others share is never to be deleted, a resource that an automation manages is held back, and advice says the risk of acting apart from the answer.

AGENTS.md rules 26 and 30: a model's claim is checked by code, and what a person reads says no more than the tools showed. Everything here is invented; a fake of Azure answers.
"""
import datetime as dt
import unittest

import support  # noqa: F401  (it puts the app on the path)
from support import NOW, REPO_ROOT, SUBSCRIPTION
from test_held_back import finding as held_case, request_for, watch as run_watch
from test_investigate import GROUP, RG, FakeFoundry, FakeToolbox, Harness, ScriptedAgent, WithTheRealToolbox, answer, disks_estate, entry, finding, metrics, resource
from test_letters import BASE, CONTACTS, PERSON
from test_run_loop import GROUP as LOOP_GROUP, Moving, loop_for
from test_unread import page_of, walk_blocks
from test_web_support import NOW as WEB_NOW, SUB, make_advice, make_advice_case

from cases import brief, cards, investigate, learning, letters, stake
from cases.approvals import MANAGED_BY_AUTOMATION, NOT_CHECKED, RULES_CHANGED
from cases.brief import CHECK_FIRST, CHECK_FIRST_SHORT, HELD_SHARED, HELD_UNPROVEN, NOT_LOOKED_UP, NOT_MEASURED
from cases.memory_store import stamp

ABSENT = {"metrics": {"MetricA": {"total": None, "days": 30, "days_with_data": 0, "totals": [None]}}}  # what the real toolbox records for a measurement that has no data
ENDPOINTS = "microsoft.network/privateendpoints"


def watch(raw, resources, evidence, **options) -> Harness:
    h = Harness(FakeFoundry(answer(raw)), FakeToolbox(resources, evidence), with_store=True, **options)
    h.go()
    return h


def cases_of(h) -> dict:
    return {case.resource_name: case for case in h.store.cases_recent()}


class MissingDataIsNotZero(unittest.TestCase):
    def test_values_on_only_a_few_days_of_the_window_prove_nothing_with_the_real_tools(self):
        from test_toolbox import point

        estate, real = disks_estate()
        estate.series[(estate.id_of("disk-a").lower(), "MetricX")] = [point(day, total=0) for day in range(1, 6)]
        h = Harness(ScriptedAgent(WithTheRealToolbox.honest), real)
        h.go()
        self.assertEqual(sorted(r["resourceName"] for r in h.of("case.result")), ["disk-c"], "five days of nil are not a measured zero")
        (line,) = h.of("investigation.finding")
        self.assertEqual((line["handles"], line["unproven"]), (1, 1))

    def test_a_deletion_without_a_measured_zero_asks_for_a_look_claims_no_saving_and_says_why(self):
        for label, evidence in (("no data", ABSENT), ("19 of 30 days", {"metrics": {"MetricA": {"total": 0, "totals": [0], "days": 30, "days_with_data": 19}}}),
                                ("nothing cited", metrics(MetricB=0))):
            with self.subTest(case=label):
                h = watch(finding(basis="other", proposal="delete", confidence=0.9, evidence=[entry("r1", "MetricA", 0)] if label != "nothing cited" else []),
                          [resource(1, cost_usd_30d=70.0)], {"r1": evidence})
                case = cases_of(h)["thing-1"]
                self.assertEqual((case.status, case.recommendation, case.saving_usd_month, case.facts["proposal"], case.facts["asked"]), ("needs_human", "investigate", None, "investigate", "delete"))
                self.assertEqual(case.objections[0], HELD_UNPROVEN)
                self.assertIn(f"finding 1: {HELD_UNPROVEN}", h.notes)
                (plan,) = h.store.plans_open()
                self.assertTrue(plan.title.startswith("Check whether the resource thing-1"), plan.title)
                self.assertTrue(plan.could_go_wrong.startswith("If you act on it: Unproven: nothing shows that nothing uses it."), plan.could_go_wrong)

    def test_a_deletion_with_a_measured_zero_on_every_resource_of_a_kind_that_others_do_not_share_stays_a_deletion(self):
        h = watch(finding(basis="other", proposal="delete", confidence=0.9), [resource(1, cost_usd_30d=70.0), resource(2, cost_usd_30d=80.0)], {"r1": metrics(MetricA=0), "r2": metrics(MetricA=0)})
        for case in cases_of(h).values():
            self.assertEqual((case.status, case.recommendation, "asked" in case.facts, case.saving_usd_month), ("proposed", "delete", False, case.cost_usd_30d))

    def test_one_resource_without_a_measured_zero_makes_the_whole_finding_a_look(self):
        h = watch(finding(basis="other", proposal="delete", confidence=0.9, evidence=[entry("r1", "MetricA", 0), entry("r2", "MetricA", 0)]),
                  [resource(1, cost_usd_30d=70.0), resource(2, cost_usd_30d=80.0)], {"r1": metrics(MetricA=0), "r2": ABSENT})
        self.assertEqual({case.recommendation for case in cases_of(h).values()}, {"investigate"})

    def test_a_resource_that_others_share_is_never_to_be_deleted_even_with_a_measured_zero(self):
        h = watch(finding(basis="no-usage", proposal="delete", confidence=0.95), [resource(1, resource_type=ENDPOINTS, name="pe-1", cost_usd_30d=70.0), resource(2, resource_type=ENDPOINTS,
                                                                                                                                                         name="pe-2", cost_usd_30d=80.0)],
                  {"r1": metrics(MetricA=0), "r2": metrics(MetricA=0)})
        for case in cases_of(h).values():
            self.assertEqual((case.status, case.recommendation, case.facts["asked"], case.objections[0]), ("needs_human", "investigate", "delete", HELD_SHARED))
            self.assertTrue(brief.measured_zero(case.facts), "it was measured: that is not what holds it back")

    def test_one_measured_zero_does_not_outweigh_a_measurement_of_the_same_resource_that_shows_use_whatever_the_basis_is(self):
        h = watch(finding(basis="low-usage", proposal="delete", confidence=0.9, evidence=[entry("r1", "Throttled", 0), entry("r1", "Requests", 4200)]),
                  [resource(1, cost_usd_30d=70.0)], {"r1": metrics(Throttled=0, Requests=4200)})
        case = cases_of(h)["thing-1"]
        self.assertEqual((case.recommendation, case.facts["asked"], case.saving_usd_month, case.objections[0]), ("investigate", "delete", None, HELD_UNPROVEN))
        self.assertFalse(brief.measured_zero(case.facts), "a deletion needs that none of its cited totals is above nil")
        (plan,) = h.store.plans_open()
        self.assertTrue(plan.title.startswith("Check whether the resource thing-1"), plan.title)

    def test_the_list_of_what_others_share(self):
        for kind in ("Microsoft.Network/privateEndpoints", "microsoft.network/privateDnsZones", "microsoft.network/privateDnsZones/virtualNetworkLinks", "microsoft.network/virtualNetworkGateways",
                     "microsoft.network/azureFirewalls", "microsoft.network/routeTables", "microsoft.network/natGateways", "microsoft.apimanagement/service", "microsoft.network/bastionHosts",
                     "microsoft.network/expressRouteCircuits", "microsoft.network/vpnGateways", "microsoft.network/virtualNetworks/virtualNetworkPeerings", "microsoft.network/virtualNetworks",
                     "microsoft.network/networkSecurityGroups", "microsoft.network/applicationGateways", "microsoft.network/virtualWans", "microsoft.network/virtualHubs",
                     "microsoft.network/dnsResolvers", "microsoft.keyvault/vaults"):
            with self.subTest(kind=kind):
                self.assertTrue(brief.shared(kind))
        for kind in ("microsoft.compute/disks", "microsoft.network/publicIPAddresses", "microsoft.network/networkInterfaces", "microsoft.network/loadBalancers", "microsoft.web/serverfarms",
                     "microsoft.storage/storageaccounts", "", None, 5):
            with self.subTest(kind=kind):
                self.assertFalse(brief.shared(kind))

    def test_the_days_of_a_measured_zero_are_those_of_the_chart_of_use(self):
        from cases import usage

        self.assertEqual((investigate.MEASURED_DAYS, brief.MEASURED_DAYS), (usage.MIN_DAYS, usage.MIN_DAYS))
        for facts, expected in (({"metrics": {"A": 0}, "metricDaysWithData": {"A": 20}}, True), ({"metrics": {"A": 0}, "metricDaysWithData": {"A": 19}}, False),
                                ({"metrics": {"A": 0.0}, "metricDaysWithData": {"A": 30}}, True), ({"metrics": {"A": 3}, "metricDaysWithData": {"A": 30}}, False),
                                ({"metrics": {"A": 0}}, False), ({"metrics": {"A": 0}, "metricDaysWithData": {"A": True}}, False), ({"metrics": {"A": None}, "metricDaysWithData": {"A": 30}}, False),
                                ({"metrics": {"A": 0, "B": 4}, "metricDaysWithData": {"A": 3, "B": 30}}, False), ({"metrics": {"A": 0, "B": 4}, "metricDaysWithData": {"A": 30, "B": 30}}, False),
                                ({}, False), (None, False)):
            with self.subTest(facts=facts):
                self.assertEqual(brief.measured_zero(facts), expected)


PE = f"/subscriptions/{SUB}/resourceGroups/rg-platform/providers/Microsoft.Network/privateEndpoints/pe-apim-demo"
DISK = f"/subscriptions/{SUB}/resourceGroups/rg-platform/providers/Microsoft.Compute/disks/disk-demo"
SUB_ID = f"/subscriptions/{SUBSCRIPTION}"


def endpoint_case(**changes):
    """The request of the owner's question: a private endpoint of another team's API Management instance, Disconnected, with no data for its traffic, 7.20 US dollars a month, and a deletion."""
    base = dict(case_id="case0100", resource_id=PE, resource_name="pe-apim-demo", resource_type=ENDPOINTS, resource_group="rg-platform", recommendation="delete", confidence=0.4,
                saving_usd_month=7.2, cost_usd_30d=7.2, plan_id="plan0100", summary="These private endpoints are Disconnected and had no data in the window.",
                objections=("Disconnected shows how it is now, not for how long.",), facts={"basis": "other", "proposal": "delete", "metrics": {}, "costUsd30d": 7.2, "finding": 1})
    base.update(changes)
    return make_advice_case(**base)


def endpoint_plan(case, **changes):
    base = dict(plan_id=case.plan_id, case_id=case.case_id, resource_id=case.resource_id, resource_name=case.resource_name, resource_group=case.resource_group,
                title="Consider deleting the private endpoint pe-apim-demo in group rg-platform", saving_usd_month=7.2)
    base.update(changes)
    return make_advice(**base)


class AdviceSaysNoMoreThanItKnows(unittest.TestCase):
    def test_a_deletion_that_nothing_measured_backs_reads_as_a_question_whether_the_resource_is_still_used(self):
        for label, case, saving in (("a record from before this rule", endpoint_case(), 7.2),
                                    ("a record of this rule", endpoint_case(recommendation="investigate", saving_usd_month=None,
                                                                             facts={"basis": "other", "proposal": "investigate", "asked": "delete", "metrics": {}, "finding": 1}), None)):
            with self.subTest(case=label):
                b = brief.build_brief(case, endpoint_plan(case, saving_usd_month=saving), now=WEB_NOW, may_answer=True)
                self.assertEqual(b.headline, "Check whether the private endpoint pe-apim-demo in group rg-platform is still used")
                self.assertEqual(stake.title_text(b), "Check whether the private endpoint pe-apim-demo is still used")
                self.assertIsNone(b.saving.monthly, "a look claims no saving: nothing shows that the resource can go")
                self.assertEqual(stake.stake_of(b).label, "Costs, saving not measured")
                self.assertEqual(("Use, last 30 days", NOT_MEASURED), next((f.label, f.value) for f in b.facts if f.label.startswith("Use")))
                self.assertEqual(b.check_first, CHECK_FIRST)
                self.assertEqual((b.risk.level, b.risk.text), ("high", "If you act on it: Unproven: nothing shows that nothing uses it. Could break traffic that you cannot see from here."))
                self.assertEqual(stake.chips_of(b), ("High risk if you act on it", "Low confidence", "Answering changes nothing in Azure"))
                self.assertEqual((b.change, b.undo.how), (brief.ADVICE_CHANGE, brief.ADVICE_UNDO), "answering changes nothing in Azure, and says so apart from the risk")

    def test_the_page_the_card_and_the_letter_say_the_two_things_apart_and_never_low_risk(self):
        case = endpoint_case()
        plan = endpoint_plan(case)
        reply, text = page_of(case, plan)
        self.assertEqual(reply.headings(1), ["Check whether the private endpoint pe-apim-demo is still used"])
        self.assertEqual(reply.main.find("p", class_="chips").text(), "High risk if you act on it Low confidence Answering changes nothing in Azure")
        self.assertEqual(reply.facts()["What could go wrong"],
                         "If you act on it: Unproven: nothing shows that nothing uses it. Could break traffic that you cannot see from here. Risk: high.")
        self.assertEqual(reply.facts()["What changes"], brief.ADVICE_CHANGE)
        self.assertIn("Check first", reply.headings(2))
        for line in CHECK_FIRST:
            self.assertIn(line, text)
        self.assertIn("Costs, saving not measured", text)
        self.assertNotIn("Consider deleting", text)
        self.assertNotIn("Low risk", text)
        b = brief.build_brief(case, plan, now=WEB_NOW, may_answer=True)
        texts = {block["id"]: block["text"] for block in walk_blocks(cards.decision_card(b, cards.CardContext(page_url=f"https://meternaut.example/ok/{plan.plan_id}")))}
        self.assertEqual(texts["headline"], "Check whether the private endpoint pe-apim-demo is still used")
        self.assertEqual(texts["chips"], "High risk if you act on it, Low confidence, Answering changes nothing in Azure")
        self.assertEqual(texts["check-first"], CHECK_FIRST_SHORT)
        self.assertIn("**Risk, high:** If you act on it: Unproven: nothing shows that nothing uses it. Could break traffic that you cannot see from here.", texts["risk"])
        letter = letters.approval_letter(plan, case, PERSON, BASE, WEB_NOW, CONTACTS)
        for words in ("Check whether the private endpoint pe-apim-demo is still used", "High risk if you act on it, Low confidence, Answering changes nothing in Azure", CHECK_FIRST_SHORT,
                      "Risk, high: If you act on it: Unproven: nothing shows that nothing uses it. Could break traffic that you cannot see from here."):
            self.assertIn(words, letter.text)
        self.assertNotIn("Consider deleting", letter.text)
        self.assertNotIn("Low risk", letter.text)

    def test_a_deletion_that_a_measured_zero_backs_is_still_a_deletion_with_a_medium_risk_and_no_list_to_check_first(self):
        case = make_advice_case(resource_id=DISK, resource_name="disk-demo", resource_type="microsoft.compute/disks", resource_group="rg-platform", recommendation="delete",
                                facts={"basis": "no-usage", "proposal": "delete", "metrics": {"MetricA": 0}, "metricDaysWithData": {"MetricA": 27}, "metricDays": {"MetricA": 30}})
        b = brief.build_brief(case, make_advice(resource_id=DISK, resource_name="disk-demo", resource_group="rg-platform"), now=WEB_NOW, may_answer=True)
        self.assertEqual(b.headline, "Consider deleting the disk disk-demo in group rg-platform")
        self.assertEqual((b.risk.level, b.risk.text), ("medium", "If you act on it: " + brief.RARE_USE))
        self.assertEqual((b.check_first, stake.chips_of(b)[0]), ((), "Medium risk if you act on it"))
        self.assertIn("with a value on 27 of those days", next(f.value for f in b.facts if f.label == "MetricA"))

    def test_a_finding_about_a_kind_that_others_share_says_so_whatever_it_asks(self):
        asks_to_change = endpoint_case(recommendation="change", facts={"basis": "oversized", "proposal": "change", "metrics": {"MetricA": 4}})
        b = brief.build_brief(asks_to_change, endpoint_plan(asks_to_change, title="Consider changing the private endpoint pe-apim-demo"), now=WEB_NOW, may_answer=True)
        self.assertEqual((b.headline.startswith("Consider changing"), b.risk.level, b.risk.text), (True, "high", "If you act on it: " + brief.SHARED_RISK))
        self.assertEqual(b.check_first, (), "it is not the question whether the resource is still used")

    def test_a_request_with_no_plan_and_a_case_of_the_older_detectors_keep_their_words(self):
        planted = make_advice_case(detector="orphan-managed-disk", recommendation="delete", resource_type="microsoft.compute/disks", facts={"state": "unattached"})
        self.assertEqual(brief.build_brief(planted, None, now=WEB_NOW).risk, brief.Risk("low", "Nothing changes in Azure."))
        self.assertEqual(brief.headline_of("advise", "x", "", "microsoft.compute/disks", "delete", case=planted), "Consider deleting the disk x")
        info = brief.build_brief(endpoint_case(), None, now=WEB_NOW)
        self.assertEqual((info.risk.level, info.headline.startswith("Check whether")), ("high", True))


class AnAutomationsResourceIsHeldBack(unittest.TestCase):
    GUID = "aaaaaaaa-1111-4222-8333-444444444444"

    @staticmethod
    def written(days_ago, caller):
        when = (NOW - dt.timedelta(days=days_ago)).strftime("%Y-%m-%dT%H:%M:%S.0000000Z")
        return {"operationName": {"value": "Microsoft.Network/privateEndpoints/write"}, "status": {"value": "Succeeded"}, "eventTimestamp": when, "caller": caller}

    def watch(self, events, resources=None):
        h = Harness(FakeFoundry(answer(finding(handles=["r1"]))), FakeToolbox(resources or [resource(1, cost_usd_30d=70.0)], {"r1": metrics(MetricA=0)}), with_store=True)
        h.arm.activity_events = lambda subscription, since, until, **kwargs: (events, True)
        h.go()
        return h

    def test_a_change_within_14_days_by_an_application_or_service_identity_holds_the_finding_back_and_counts_it(self):
        h = self.watch([self.written(2, self.GUID)])
        self.assertEqual((h.result.held_back, h.result.said_nothing, h.result.cases), ({"automation": 1}, 0, 1))
        self.assertEqual(h.store.plans_open(), [], "no request is made")
        (case,) = h.store.cases_recent()
        self.assertEqual((case.status, brief.held_reason(case, NOW), case.owner["lookedUp"]), ("proposed", "automation", True))
        self.assertTrue(case.owner["automatedAt"].startswith((NOW - dt.timedelta(days=2)).strftime("%Y-%m-%d")))
        (held,) = h.of("case.held")
        self.assertEqual((held["caseId"], held["reason"], held["resourceName"]), (case.case_id, "held back: managed by an automation", "thing-1"))
        self.assertEqual(held["reason"], MANAGED_BY_AUTOMATION)

    def test_a_change_by_a_person_by_meternaut_itself_or_longer_ago_than_14_days_holds_nothing_back(self):
        own = "99999999-8888-7777-6666-555555555555"  # AZURE_CLIENT_ID of the app in the tests
        for label, events in (("a person", [self.written(1, "alice@example.com")]), ("Meternaut itself", [self.written(1, own)]), ("15 days ago", [self.written(15, self.GUID)]),
                              ("no change in the log", [])):
            with self.subTest(case=label):
                h = self.watch(events)
                self.assertEqual((h.result.held_back, len(h.store.plans_open()), h.of("case.held")), ({}, 1, []))

    def test_a_person_s_edit_yesterday_does_not_hide_the_write_of_an_automation_three_days_ago(self):
        h = self.watch([self.written(1, "alice@example.com"), self.written(3, self.GUID)])
        self.assertEqual((h.result.held_back, h.store.plans_open()), ({"automation": 1}, []))
        (case,) = h.store.cases_recent()
        self.assertEqual((case.owner["changedBy"], case.owner["automatedAt"][:10]), ("alice@example.com", (NOW - dt.timedelta(days=3)).strftime("%Y-%m-%d")))

    def test_waste_that_meternaut_planted_is_never_held_back_for_the_change_that_its_own_deploy_made(self):
        planted = resource(1, resource_id=f"{RG}/{GROUP}/providers/Microsoft.Compute/disks/planted-disk-1", resource_type="microsoft.compute/disks", name="planted-disk-1", resource_group=GROUP,
                           tags={"meternaut-planted": "demo"}, cost_usd_30d=70.0)
        h = self.watch([self.written(1, self.GUID)], [planted])
        self.assertEqual((h.result.held_back, len(h.store.plans_open())), ({}, 1))

    def test_a_lookup_that_could_not_be_made_holds_a_deletion_back_and_says_that_nobody_checked(self):
        for label, arrange in (("the Activity Log refuses", lambda h: setattr(h.arm, "log_fails", True)), ("the call breaks", lambda h: setattr(h.arm, "activity_events", None))):
            with self.subTest(case=label):
                h = Harness(FakeFoundry(answer(finding(handles=["r1"]))), FakeToolbox([resource(1, cost_usd_30d=70.0)], {"r1": metrics(MetricA=0)}), with_store=True)
                arrange(h)
                h.go()
                self.assertEqual((h.result.held_back, h.store.plans_open()), ({"unchecked": 1}, []), "a log that was not read shows nothing, and nothing is not 'nobody changed it'")
                (case,) = h.store.cases_recent()
                self.assertEqual((case.owner["lookedUp"], brief.held_reason(case, NOW)), (False, "unchecked"))
                (held,) = h.of("case.held")
                self.assertEqual((held["reason"], NOT_CHECKED), ("held back: not checked who changed it", "held back: not checked who changed it"))

    def test_a_lookup_that_was_not_made_does_not_hold_a_look_back_and_the_page_says_that_it_was_not_checked(self):
        h = Harness(FakeFoundry(answer(finding(handles=["r1"], proposal="investigate", basis="other"))), FakeToolbox([resource(1, resource_type=ENDPOINTS, name="pe-1", cost_usd_30d=70.0,
                                                                                                                              tags={"owner": "platform-team"})], {"r1": ABSENT}), with_store=True)
        h.arm.log_fails = True
        h.go()
        (plan,) = h.store.plans_open()
        (case,) = h.store.cases_recent()
        self.assertIn(NOT_LOOKED_UP, brief.build_brief(case, plan, now=WEB_NOW, may_answer=True).owner.text)


class AnOpenRequestThatTheRulesOfTodayHoldBackIsTakenBack(unittest.TestCase):
    """The requests that were open before the rules changed: Meternaut takes them back itself at the next Watch, says why in plain words and changes nothing in Azure."""

    def setUp(self):
        self.clock = Moving()
        self.extras = loop_for(self.clock)
        self.store = self.extras.store

    def open_request(self, title, plan_changes=None, **case_changes):
        base = dict(detector="investigation", resource_id=PE, resource_name="pe-apim-demo", resource_type=ENDPOINTS, resource_group="rg-platform", subscription_id=SUBSCRIPTION,
                    status="needs_human", recommendation="investigate", advice={}, owner={"lookedUp": True, "automatedAt": ""})
        base.update(case_changes)
        case = held_case(**base)
        plan = request_for(case, expires_at="2026-11-07T09:00:00Z", title=title, **(plan_changes or {}))
        self.store.case_put(case)
        self.store.plan_put(plan)
        return case, plan

    def watch(self):
        from support import FakeEstate
        return run_watch(FakeEstate(), self.extras, self.clock)

    def taken(self, case, plan):
        return self.store.plan_get(plan.plan_id), self.store.case_get(case.case_id)

    def test_the_request_of_a_finding_that_an_automation_manages_is_closed_and_said_and_counted_with_its_own_reason(self):
        case, plan = self.open_request("Check whether the private endpoint pe-apim-demo is still used",
                                       owner={"lookedUp": True, "automatedAt": stamp(self.clock() - dt.timedelta(days=2))})
        summary, events, _ = self.watch()
        after, kept = self.taken(case, plan)
        self.assertEqual((after.state, self.store.plans_open()), ("expired", []))
        (held,) = [e for e in events if e["type"] == "case.held"]
        self.assertEqual((held["caseId"], held["reason"]), (case.case_id, "held back: managed by an automation"))
        self.assertEqual((summary.held, self.store.runs_recent()[0].held), (1, 1))
        notes = [e["note"] for e in events if e["type"] == "run.note"]
        self.assertIn("1 finding held back: managed by an automation", notes)
        self.assertFalse([note for note in notes if note.endswith("held back: nothing to say")], "it is not a finding that says nothing")
        self.assertEqual(kept.learned["taken"], "automation")

    def test_a_request_that_asks_to_delete_on_less_than_the_rules_ask_for_now_is_taken_back_and_the_person_is_told_why(self):
        case, plan = self.open_request("Consider deleting the private endpoint pe-apim-demo in group rg-platform", dict(saving_usd_month=7.2), recommendation="delete", saving_usd_month=7.2,
                                       facts={"basis": "other", "proposal": "delete", "metrics": {}})
        summary, events, _ = self.watch()
        after, kept = self.taken(case, plan)
        self.assertEqual((after.state, kept.learned["taken"], summary.held), ("expired", "rules", 1))
        (held,) = [e for e in events if e["type"] == "case.held"]
        self.assertEqual((held["reason"], RULES_CHANGED), ("held back: Meternaut's rules changed", "held back: Meternaut's rules changed"))
        b = brief.build_brief(kept, after, now=WEB_NOW)
        self.assertEqual((b.outcome.state, b.outcome.title), ("expired", "Taken back"))
        self.assertEqual(b.outcome.lines, ("Meternaut's rules changed, so it took this request back: it asks about this resource on less evidence than Meternaut's rules ask for now.",
                                           "Nothing was changed in Azure."))
        card = cards.closed_card(b, cards.CardContext(page_url=f"https://meternaut.example/ok/{after.plan_id}"))
        text = {block["id"]: block["text"] for block in walk_blocks(card)}["closed"]
        self.assertTrue(text.startswith("Taken back. Meternaut's rules changed"), text)
        self.assertIn("Nothing was changed in Azure.", text)
        self.assertEqual(learning.lesson_of(after, kept, [], None, WEB_NOW), None, "a request that Meternaut took back is not one that nobody answered")

    def test_a_deletion_of_a_resource_that_nobody_looked_up_the_changes_of_is_taken_back_too(self):
        case, plan = self.open_request("Consider deleting the disk disk-demo in group rg-platform", dict(saving_usd_month=7.2), resource_id=DISK, resource_name="disk-demo",
                                       resource_type="microsoft.compute/disks", recommendation="delete", owner={},
                                       facts={"basis": "no-usage", "proposal": "delete", "metrics": {"M": 0}, "metricDaysWithData": {"M": 28}})
        self.watch()
        after, kept = self.taken(case, plan)
        self.assertEqual((after.state, kept.learned["taken"]), ("expired", "unchecked"))

    def test_what_a_person_decided_what_runs_and_what_meternaut_planted_stay_as_they_are(self):
        from cases.models import DecisionRecord

        kept = {}
        later, later_plan = self.open_request("Consider deleting the private endpoint pe-later in group rg-platform", resource_id=PE + "-later", recommendation="delete",
                                              facts={"basis": "other", "proposal": "delete", "metrics": {}}, case_id="klater")
        self.store.decision_put(DecisionRecord(plan_id=later_plan.plan_id, approver_oid="aaaaaaaa-1111-4222-8333-444444444444", approver_name="Tino", decision="later", at="2026-11-03T08:00:00Z",
                                               plan_code=later_plan.code))
        planted_case = held_case(detector="orphan-managed-disk", resource_id=f"{SUB_ID}/resourceGroups/{LOOP_GROUP}/providers/Microsoft.Compute/disks/planted-disk-1", resource_name="planted-disk-1",
                                 resource_type="microsoft.compute/disks", resource_group=LOOP_GROUP, subscription_id=SUBSCRIPTION, status="needs_human", recommendation="delete",
                                 case_id="kplanted", plan_id="pplanted", facts={"basis": "other"}, owner={})
        planted_plan = request_for(planted_case, expires_at="2026-11-07T09:00:00Z", title=f"Consider deleting the disk planted-disk-1 in group {LOOP_GROUP}")
        self.store.case_put(planted_case)
        self.store.plan_put(planted_plan)
        self.watch()
        self.assertEqual((self.store.plan_get(later_plan.plan_id).state, self.store.plan_get(planted_plan.plan_id).state), ("open", "open"))
        self.assertNotIn("taken", self.store.case_get("klater").learned)
        self.assertEqual(kept, {})

    def test_a_finding_that_no_rule_holds_back_keeps_its_request(self):
        case, plan = self.open_request("Check whether the private endpoint pe-apim-demo is still used")
        summary, _, _ = self.watch()
        self.assertEqual((self.store.plan_get(plan.plan_id).state, summary.held), ("open", 0))


class TheOlderDetectorsAreHeldByTheSameRules(unittest.TestCase):
    """On the days that the investigation does not run the older detectors judge every lead that is not waste that Meternaut planted: no deletion goes out on what nobody checked."""

    def test_a_private_endpoint_outside_a_group_where_a_change_may_be_made_gets_no_deletion_advice_and_is_held_with_its_reason(self):
        from test_run_loop import estate_with

        clock = Moving()
        extras = loop_for(clock)
        summary, events, _ = run_watch(estate_with(planted_disk=False, endpoints=1), extras, clock)
        self.assertEqual((summary.cases, summary.held, extras.store.plans_open()), (1, 1, []), "the Detective said delete, and no request is made")
        (case,) = extras.store.cases_recent()
        self.assertEqual((case.detector, case.recommendation, case.plan_id), ("orphan-private-endpoint", "delete", None))
        (held,) = [e for e in events if e["type"] == "case.held"]
        self.assertEqual(held["reason"], "held back: not checked who changed it")
        self.assertIn("1 finding held back: not checked who changed it", [e["note"] for e in events if e["type"] == "run.note"])

    def test_the_same_lead_in_the_group_of_meternaut_s_own_is_not_held(self):
        from test_run_loop import GROUP as OWN_GROUP, estate_with

        clock = Moving()
        extras = loop_for(clock)
        estate = estate_with(planted_disk=False, endpoints=0)
        from support import pe_row
        estate.graph["orphan-private-endpoint"] = [pe_row("pe-own", OWN_GROUP)]
        summary, _, _ = run_watch(estate, extras, clock)
        self.assertEqual((summary.held, len(extras.store.plans_open())), (0, 1))


class TheHomePageSaysWhyAFindingIsHeldBack(unittest.TestCase):
    def test_a_finding_that_a_rule_holds_back_has_its_own_words_and_count_and_the_others_keep_theirs(self):
        from test_web_support import Console

        console = Console()
        recent = stamp(WEB_NOW - dt.timedelta(days=1))
        console.store.case_put(make_advice_case(case_id="case4000", resource_id=f"{PE}-a", resource_name="endpoint-a", plan_id=None, recommendation="investigate",
                                                owner={"lookedUp": True, "automatedAt": recent}))
        content = console.get("/").content
        self.assertIn("Held back: 1 finding", content)
        self.assertIn("1 finding is held back because an automation manages the resource, or because nobody has looked up who changed it.", content)
        self.assertNotIn("No measurement backs", content, "this one is held for another reason, and the page does not say that nothing measured backs it")
        console.store.case_put(make_advice_case(case_id="case4001", resource_id=f"{PE}-b", resource_name="endpoint-b", plan_id=None, recommendation="investigate", owner={"lookedUp": True}))
        content = console.get("/").content
        self.assertIn("Held back: 2 findings", content)
        self.assertIn("1 finding is held back because an automation manages the resource", content)
        self.assertIn("No measurement backs it yet, or the places for requests are full.", content)


class TheWordsAboutWhatWasNotMeasured(unittest.TestCase):
    def test_a_finding_that_cites_no_measurement_says_so_and_does_not_blame_azure_monitor(self):
        case = make_advice_case(detector="investigation", recommendation="investigate", resource_type="microsoft.compute/disks", facts={"basis": "unused-feature", "proposal": "investigate",
                                                                                                                                       "metrics": {}, "asked": "delete"})
        row = next(f for f in brief.facts_of(case) if f.label.startswith("Use"))
        self.assertEqual(row.value, "Not measured: no measurement is cited for this finding, so nothing shows that nothing uses it.")
        self.assertNotIn("Azure Monitor", row.value + row.source)


class TheStyleGuideAndTheRecordHoldTheWords(unittest.TestCase):
    def test_the_words_of_the_two_risks_and_of_the_title_are_in_the_style_guide_and_in_the_record_of_the_brief(self):
        for path, needed in ((REPO_ROOT / "docs" / "ui" / "style-guide.html", ("High risk" + brief.IF_ACTED, "Answering changes nothing in Azure", brief.UNPROVEN, brief.SHARED_RISK,
                                                                               "Check whether the private endpoint", "Costs, saving not measured", "Check first")),
                             (REPO_ROOT / "docs" / "proposals" / "09-the-decision-brief.md", ("Check whether the private endpoint x is still used", "If you act on it", brief.UNPROVEN,
                                                                                               brief.SHARED_RISK, "held back: managed by an automation", "Missing data is not zero"))):
            text = path.read_text(encoding="utf-8")
            for words in needed:
                with self.subTest(file=path.name, words=words):
                    self.assertIn(words, text)


if __name__ == "__main__":
    unittest.main()
