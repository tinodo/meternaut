"""The digest of a plan: what a person approves is exactly what runs.

A plan holds more than the words that a person reads: a family, a resource, the parameters of the change (a VM size, a disk tier), the facts that are checked again right before it,
the place, the time at which it expires and the people who may approve it. The digest is bound into the state of the sign-in to Azure and compared again right before the change.
Each field of the plan, changed after the approval, is shown below to stop the change at every place that checks.
"""
import dataclasses
import datetime as dt
import json
import unittest
from dataclasses import replace

import familysupport as fs
from familysupport import APPROVER, GROUP, NOW, OID, SCOPES, SETTINGS, SUB, World

from support import APP_ROOT  # noqa: F401

from cases.delegated import Delegation, SigninSettings, Tokens
from cases.families import digest as plan_digest
from cases.families import registry
from cases.memory_store import parse, stamp
from cases.models import PlanRecord
from cases.runner import RunnerServices, change_calls
from test_families_gates import SAMPLES, setUpModule, tearDownModule, world_with  # noqa: F401  (the module holds a gateway on the planted list for its tests, as test_families_gates does)
from test_runner import challenge

TENANT = "cccccccc-1111-4222-8333-444444444444"
CLIENT = "dddddddd-1111-4222-8333-444444444444"
ASSERTION_CLIENT = "eeeeeeee-1111-4222-8333-444444444444"
SIGNIN = SigninSettings(TENANT, CLIENT, ASSERTION_CLIENT, "console.example.test")
VERIFIER, NONCE, CODE, ACCESS = "v" * 43, "n" * 22, "C" * 40, "access-token-of-the-person-" + "A" * 40
CHECKED = frozenset(field.name for field in dataclasses.fields(PlanRecord)) - set(plan_digest.EXCLUDED)


def different(value, name=""):
    """A value of the same type as `value` that is not equal to it (a time stays a time that can be read)."""
    if name in ("created_at", "expires_at"):
        return stamp(parse(value) + dt.timedelta(days=1))
    if isinstance(value, bool):
        return not value
    if isinstance(value, (int, float)):
        return value + 1
    if isinstance(value, str):
        return value + "x"
    if isinstance(value, tuple):
        return value + ("x",)
    if isinstance(value, dict):
        return {**value, "extra": "x"}
    if value is None:
        return 1.0
    raise AssertionError(f"a field of a type that this test does not know: {type(value)}")


def a_plan(**more) -> PlanRecord:
    world = World()
    resource = world.arm.add(fs.vm(**more))
    world.arm.sizes[resource["id"].lower()] = fs.D_SERIES
    return world.plan(resource, "vm", "change", cost=60.0)


class TheDigest(unittest.TestCase):
    def setUp(self):
        self.plan = a_plan()

    def test_a_plan_that_code_wrote_is_sealed_with_its_digest_and_the_code_is_the_start_of_it(self):
        self.assertRegex(self.plan.digest, r"^[0-9a-f]{64}$")
        self.assertEqual(self.plan.digest, plan_digest.digest_of(self.plan))
        self.assertEqual(self.plan.code, self.plan.digest[:8].upper())
        self.assertEqual(plan_digest.code_of(self.plan.digest), self.plan.code)

    def test_every_family_makes_a_sealed_plan_whose_parameters_are_in_it(self):
        for name in sorted(SAMPLES):
            with self.subTest(name):
                world, resource, kind, recommendation, detector = world_with(name)
                plan = world.plan(resource, kind, recommendation, cost=50.0, detector=detector)
                self.assertEqual((plan.digest, plan.code), (plan_digest.digest_of(plan), plan_digest.code_of(plan.digest)))
                self.assertEqual(plan_digest.problem(plan, plan.digest), "")
                self.assertEqual({"family", "resourceType", "tag", "resourceGroup"} - set(plan.preconditions), set())
                if name in ("resize-vm", "change-disk-tier"):
                    self.assertTrue(plan.target, "the parameters of the change are in the plan, so that the digest holds them")

    def test_the_advise_plan_is_sealed_too(self):
        from test_web_support import make_advice_case
        world = World()
        case = make_advice_case(plan_id=None, updated_at="2026-11-08T09:00:00Z", first_seen_at="2026-11-08T09:00:00Z")
        world.store.case_put(case)
        advice = world.approvals.advise(case, (OID,))
        self.assertEqual((advice.digest, advice.code), (plan_digest.digest_of(advice), plan_digest.code_of(advice.digest)))

    def test_each_field_but_the_three_that_follow_from_the_rest_changes_the_digest(self):
        self.assertEqual(CHECKED, {field.name for field in dataclasses.fields(PlanRecord)} - {"state", "digest", "code"})
        for name in sorted(CHECKED):
            with self.subTest(field=name):
                other = replace(self.plan, **{name: different(getattr(self.plan, name), name)})
                self.assertNotEqual(plan_digest.digest_of(other), self.plan.digest)
                self.assertNotEqual(plan_digest.problem(other, self.plan.digest), "")

    def test_the_state_the_digest_and_the_code_are_not_part_of_it(self):
        for name, value in (("state", "approved"), ("state", "consumed"), ("code", "ABCD1234"), ("digest", "0" * 64)):
            self.assertEqual(plan_digest.digest_of(replace(self.plan, **{name: value})), self.plan.digest, name)

    def test_the_parameters_of_the_change_are_in_the_digest_whatever_the_order_of_their_keys(self):
        target = dict(self.plan.target)
        self.assertEqual(plan_digest.digest_of(replace(self.plan, target=dict(reversed(list(target.items()))))), self.plan.digest)
        self.assertNotEqual(plan_digest.digest_of(replace(self.plan, target={**target, "vmSize": "Standard_D8s_v5"})), self.plan.digest)
        self.assertNotEqual(plan_digest.digest_of(replace(self.plan, preconditions={**self.plan.preconditions, "resourceGroup": "other"})), self.plan.digest)

    def test_a_text_with_other_characters_is_canonical_ascii(self):
        plan = replace(self.plan, title="caf\u00e9 \u2192 \u201cx\u201d")
        text = plan_digest.canonical(plan)
        self.assertTrue(text.isascii())
        self.assertEqual(json.loads(text)["title"], plan.title)
        self.assertNotIn(" ", text.replace("caf\\u00e9 \\u2192 \\u201cx\\u201d", "").replace("Resize a virtual machine", "").replace("When you approve", "").split('"title"')[0][:0])

    def test_the_problem_of_a_plan_says_which_way_it_is_not_the_plan_that_was_approved(self):
        self.assertEqual(plan_digest.problem(self.plan, self.plan.digest), "")
        self.assertEqual(plan_digest.problem(replace(self.plan, digest=""), self.plan.digest), plan_digest.NOT_BOUND)
        self.assertEqual(plan_digest.problem(replace(self.plan, title="other"), self.plan.digest), plan_digest.CHANGED)
        self.assertEqual(plan_digest.problem(self.plan, "0" * 64), plan_digest.OTHER)
        self.assertEqual(plan_digest.problem(self.plan, ""), plan_digest.OTHER, "an approval that holds no digest approves no plan")
        sentence = plan_digest.refusal(plan_digest.CHANGED)
        for words in ("This request cannot be approved", "Nothing is approved", "A new message will bring a new request and its code"):
            self.assertIn(words, sentence)


class AtTheRunner(unittest.TestCase):
    """The change of an approved plan, after the plan was changed in the store: nothing is written."""

    def setUp(self):
        self.world = World()
        self.resource = self.world.arm.add(fs.vm())
        self.world.arm.sizes[self.resource["id"].lower()] = fs.D_SERIES
        self.plan, self.action = self.world.approved(self.resource, "vm", "change", 60.0)
        self.reads = len(self.world.arm.calls)  # what was read to write the plan; the change itself makes no call before its digest is checked

    def refused(self, done, why=""):
        self.assertEqual((done.kind, done.action.state), ("stopped", "failed"), done.action.result)
        self.assertIn("Nothing was changed", done.action.result)
        self.assertIn(why, done.action.result)
        self.assertEqual(self.world.arm.writes(), [], "no write was made")
        self.assertEqual(self.world.arm.calls[self.reads:], [], "not even a read: the digest is the first check")

    def test_each_field_changed_after_the_approval_stops_the_change_before_any_call(self):
        for name in sorted(CHECKED - {"plan_id"}):
            with self.subTest(field=name):
                self.setUp()
                self.world.store.plan_put(replace(self.plan, **{name: different(getattr(self.plan, name), name)}))
                done = self.world.run(self.plan)
                if name == "family":
                    self.assertEqual((done.action.state, self.world.arm.calls[self.reads:]), ("failed", []))
                    self.assertIn("names a change that Meternaut does not make", done.action.result)
                else:
                    self.refused(done, plan_digest.CHANGED)

    def test_the_size_or_the_tier_that_was_approved_is_the_one_that_is_made_and_a_changed_parameter_is_refused(self):
        self.world.store.plan_put(replace(self.plan, target={**self.plan.target, "vmSize": "Standard_D8s_v5"}))
        self.refused(self.world.run(self.plan), plan_digest.CHANGED)
        self.assertEqual(self.world.arm.get(self.resource["id"])["properties"]["hardwareProfile"]["vmSize"], "Standard_D4s_v5")

    def test_a_field_changed_and_sealed_again_is_another_plan_and_its_approval_is_not_this_one(self):
        for name in sorted(CHECKED - {"plan_id", "family"}):
            with self.subTest(field=name):
                self.setUp()
                self.world.store.plan_put(plan_digest.sealed(replace(self.plan, **{name: different(getattr(self.plan, name), name)})))
                done = self.world.run(self.plan)
                self.assertEqual(done.action.state, "failed", done.action.result)
                self.assertEqual(self.world.arm.writes(), [])
                self.assertIn(done.kind, ("stopped", "failed"))
                self.assertTrue("another request" in done.action.result or "no approval" in done.action.result or "approved" in done.action.result, done.action.result)

    def test_a_digest_that_is_not_the_one_that_was_approved_is_refused_and_so_is_none(self):
        for digest in ("0" * 64, "", self.plan.digest[:-1] + ("0" if self.plan.digest[-1] != "0" else "1")):
            with self.subTest(digest=digest[:10]):
                self.setUp()
                self.refused(self.world.run(self.plan, digest=digest), plan_digest.OTHER)

    def test_a_plan_without_a_digest_cannot_be_acted_on(self):
        self.world.store.plan_put(replace(self.plan, digest=""))
        self.refused(self.world.run(self.plan, digest=""), plan_digest.NOT_BOUND)

    def test_an_approval_that_holds_another_digest_than_the_plan_does_not_make_the_change(self):
        key = (self.plan.plan_id, OID)
        self.world.store.decisions[key] = replace(self.world.store.decisions[key], plan_digest="0" * 64)
        done = self.world.run(self.plan)
        self.assertEqual(done.action.state, "failed")
        self.assertIn("no approval by a named approver is recorded for this exact plan", done.action.result)
        self.assertEqual(self.world.arm.calls[self.reads:], [])

    def test_a_plan_that_changes_between_the_recheck_and_the_write_is_stopped_at_the_last_check(self):
        world = World()
        resource = world.arm.add(fs.vm())
        world.arm.sizes[resource["id"].lower()] = fs.D_SERIES
        plan, _ = world.approved(resource, "vm", "change", 60.0)
        locks = []

        def change_the_plan(method, key):
            if key.endswith("/providers/microsoft.authorization/locks"):
                locks.append(key)
                if len(locks) == 2:  # the last read of the re-check: what follows is the write
                    world.store.plan_put(replace(plan, target={**plan.target, "vmSize": "Standard_D8s_v5"}))

        world.arm.hold_after = change_the_plan
        done = world.run(plan)
        self.assertEqual((done.kind, done.action.state), ("stopped", "failed"), done.action.result)
        self.assertIn(plan_digest.CHANGED, done.action.result)
        self.assertEqual(world.arm.writes(), [], "the plan was read once more as late as it could be, and the change was not made")
        self.assertEqual(len(locks), 2, "the checks before it were made")

    def test_a_plan_that_is_not_approved_any_more_at_the_last_check_is_stopped(self):
        world = World()
        resource = world.arm.add(fs.vm())
        world.arm.sizes[resource["id"].lower()] = fs.D_SERIES
        plan, _ = world.approved(resource, "vm", "change", 60.0)
        locks = []

        def withdraw(method, key):
            if key.endswith("/providers/microsoft.authorization/locks"):
                locks.append(key)
                if len(locks) == 2:
                    world.store.plan_put(replace(world.store.plan_get(plan.plan_id), state="withdrawn"))

        world.arm.hold_after = withdraw
        done = world.run(plan)
        self.assertEqual((done.kind, done.action.state), ("stopped", "failed"), done.action.result)
        self.assertIn("not approved any more", done.action.result)
        self.assertEqual(world.arm.writes(), [])


class AtTheSignIn(unittest.TestCase):
    """The state of the round trip to Microsoft Entra holds the digest, and the return compares it with the plan as it is stored then."""

    def setUp(self):
        self.world = World()
        self.resource = self.world.arm.add(fs.vm())
        self.world.arm.sizes[self.resource["id"].lower()] = fs.D_SERIES
        self.plan = self.world.plan(self.resource, "vm", "change", cost=60.0)
        self.reads = len(self.world.arm.calls)  # what was read to write the plan: nothing after it is read before the person's approval is recorded
        self.redeemed = []
        self.tokens_used = []
        self.delegation = Delegation(self.world.store, self.world.approvals, SIGNIN, self.redeem, self.runner_for, pkce=lambda: (VERIFIER, "challenge"), token=lambda size: NONCE)

    def redeem(self, code, verifier, claims=""):
        self.redeemed.append(code)
        return Tokens(ACCESS, {"oid": OID, "tid": TENANT, "aud": CLIENT, "nonce": NONCE, "iss": f"https://login.microsoftonline.com/{TENANT}/v2.0",
                               "exp": int(NOW.timestamp()) + 3600})

    def runner_for(self, token):
        self.tokens_used.append(token)
        client = self.world.client(change_calls(SCOPES))
        return RunnerServices(self.world.store, client, lambda resource: token, SETTINGS, clock=self.world.clock, sleep=self.world.sleeps.append)

    def begin(self, plan=None):
        plan = plan or self.plan
        token = self.world.store.nonce_new(OID, plan.plan_id)
        return self.delegation.begin(APPROVER, plan.plan_id, plan.code, token)

    def state_of(self, begun):
        from urllib.parse import parse_qs, urlsplit
        return parse_qs(urlsplit(begun.location).query)["state"][0]

    def test_the_state_of_the_sign_in_holds_the_digest_of_the_plan_that_the_person_saw(self):
        begun = self.begin()
        self.assertIsNone(begun.refusal)
        data = json.loads(self.world.store.nonces[self.state_of(begun)][3])
        self.assertEqual((data["digest"], data["code"], data["resource"]), (self.plan.digest, self.plan.code, self.plan.resource_id))

    def test_a_plan_that_was_changed_before_the_sign_in_starts_is_refused_and_no_state_is_made(self):
        self.world.store.plan_put(replace(self.plan, target={**self.plan.target, "vmSize": "Standard_D8s_v5"}))
        begun = self.begin()
        self.assertEqual((begun.location, begun.refusal.kind), ("", "refused_code"))
        self.assertIn("This request cannot be approved", begun.refusal.message)
        self.assertEqual([n for n in self.world.store.nonces.values() if n[1] == "arm-signin"], [])

    def test_each_field_changed_while_the_person_signs_in_is_refused_at_the_return_and_the_code_is_not_redeemed(self):
        for name in sorted(CHECKED - {"plan_id"}):
            with self.subTest(field=name):
                self.setUp()
                state = self.state_of(self.begin())
                self.world.store.plan_put(replace(self.plan, **{name: different(getattr(self.plan, name), name)}))
                result = self.delegation.finish(APPROVER, {"code": CODE, "state": state})
                self.assertFalse(result.ok)
                self.assertIn(result.kind, ("refused_code", "refused_state", "refused_role", "expired"))
                self.assertEqual((self.redeemed, self.tokens_used, self.world.arm.calls[self.reads:], self.world.store.decisions_of_plan(self.plan.plan_id)), ([], [], [], []))

    def test_a_plan_that_was_sealed_again_while_the_person_signs_in_is_refused_by_its_digest_even_when_the_code_is_made_to_fit(self):
        for name in sorted(CHECKED - {"plan_id", "family", "resource_id"}):
            with self.subTest(field=name):
                self.setUp()
                state_data = {"plan": self.plan.plan_id, "code": "", "resource": self.plan.resource_id, "digest": self.plan.digest, "verifier": VERIFIER, "nonce": NONCE, "note": ""}
                newer = plan_digest.sealed(replace(self.plan, **{name: different(getattr(self.plan, name), name)}))
                self.world.store.plan_put(newer)
                state = self.world.store.nonce_new(OID, "arm-signin", 600, json.dumps({**state_data, "code": newer.code}))
                result = self.delegation.finish(APPROVER, {"code": CODE, "state": state})
                self.assertEqual((result.ok, result.kind), (False, "refused_code"))
                self.assertIn(plan_digest.OTHER, result.message)
                self.assertEqual((self.redeemed, self.world.arm.calls[self.reads:], self.world.store.decisions_of_plan(self.plan.plan_id)), ([], [], []))

    def test_a_plan_that_is_as_it_was_runs_with_the_digest_of_the_state_and_the_change_is_made_once(self):
        state = self.state_of(self.begin())
        result = self.delegation.finish(APPROVER, {"code": CODE, "state": state})
        self.assertEqual((result.ok, result.kind), (True, "ran"), result.message)
        self.assertEqual(len(self.world.arm.writes()), 1)
        self.assertEqual(self.world.action(self.plan).plan_digest, self.plan.digest)
        self.assertEqual([d.plan_digest for d in self.world.store.decisions_of_plan(self.plan.plan_id)], [self.plan.digest])

    def test_a_resource_that_is_as_the_plan_wants_when_the_person_returns_is_not_written_and_the_result_says_that_nothing_was_changed(self):
        self.resource["properties"]["hardwareProfile"]["vmSize"] = "Standard_D2s_v5"  # somebody resized it between the plan and the OK
        state = self.state_of(self.begin())
        result = self.delegation.finish(APPROVER, {"code": CODE, "state": state})
        self.assertEqual((result.ok, result.kind), (True, "unchanged"), result.message)
        self.assertIn("already of size Standard_D2s_v5", result.message)
        self.assertEqual(self.world.arm.writes(), [])
        self.assertTrue(self.world.action(self.plan).no_change)
        self.assertEqual(self.world.state(self.plan), ("consumed", "done", "done"))

    def test_the_digest_follows_the_second_sign_in_that_a_claims_challenge_asks_for_and_a_plan_changed_meanwhile_closes_the_change(self):
        self.world.arm.write_answers = [(401, challenge(), b'{"error":{"code":"InsufficientClaims","message":"a check is needed"}}')]
        state = self.state_of(self.begin())
        first = self.delegation.finish(APPROVER, {"code": CODE, "state": state})
        self.assertEqual(first.kind, "step_up")
        from urllib.parse import parse_qs, urlsplit
        second_state = parse_qs(urlsplit(first.location).query)["state"][0]
        kept = json.loads(self.world.store.nonces[second_state][3])
        self.assertEqual((kept["digest"], kept["stepup"]), (self.plan.digest, "1"), "the second state carries the digest of the first")
        self.world.store.plan_put(replace(self.world.store.plan_get(self.plan.plan_id), target={**self.plan.target, "vmSize": "Standard_D8s_v5"}))
        result = self.delegation.finish(APPROVER, {"code": "D" * 40, "state": second_state})
        self.assertEqual(result.kind, "refused_code", result.message)
        self.assertIn("The change was not made", result.message)
        self.assertEqual(len(self.world.arm.writes()), 1, "only the first write, which Azure refused for the missing check: nothing was written again")
        self.assertEqual(self.world.state(self.plan)[1:], ("failed", "failed"))
        self.assertEqual(self.world.store.plan_get(self.plan.plan_id).state, "failed")

    def test_every_family_of_the_registry_binds_its_plan_the_same_way(self):
        for name in sorted(registry.names()):
            with self.subTest(name):
                world, resource, kind, recommendation, detector = world_with(name)
                plan, _ = world.approved(resource, kind, recommendation, 50.0, detector)
                self.assertEqual(world.action(plan).plan_digest, plan.digest)
                world.store.plan_put(replace(plan, expires_at=fs.stamp(fs.NOW + fs.dt.timedelta(days=30))))
                done = world.run(plan)
                self.assertEqual((done.kind, done.action.state), ("stopped", "failed"))
                self.assertEqual(world.arm.writes(), [])


if __name__ == "__main__":
    unittest.main()
