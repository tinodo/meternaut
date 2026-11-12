"""The look that a page takes before it offers Approve (cases/precheck.py): the checks that the runner makes right before a change, made now with the app's own reader.

The tests are written over the registry, like the ones of the gates: a family that is added is held to them without a line here. What they pin: the look is the family's own re-check (so it
refuses what the runner refuses, with the same words), it only reads, it never decides on a read that failed, and the nouns of its sentences are the words of the pages.
"""
import unittest
from dataclasses import replace
from unittest import mock

import familysupport as fs
from familysupport import GROUP, OID, SUB, World
from test_families_gates import SAMPLES, world_with

from cases.brief import kind_words
from cases.families import digest as plan_digest
from cases.families import registry
from cases.families.words import NOUNS, noun_of
from cases.http import HttpError, Refused
from cases.models import READY, REFUSED, UNKNOWN, NoteRecord, Readiness, StoreError
from cases.precheck import Precheck

TAG_WORDS = "it no longer carries the test tag meternaut-planted, so it cannot be told apart from a real "


def setUpModule():
    global _planting
    _planting = fs.as_if_gateways_were_planted()
    _planting.start()


def tearDownModule():
    _planting.stop()


def looker(world, reader=None):
    """The look of a world: its reader (the app's own identity, a list of calls with reads only), its settings and its store."""
    return Precheck(world.store, world.settings, reader or (lambda: world.reader), world.clock)


def open_plan(name):
    world, resource, kind, recommendation, detector = world_with(name)
    plan = world.plan(resource, kind, recommendation, cost=50.0, detector=detector)
    assert plan is not None and plan.state == "open"
    return world, resource, plan


class WhenNothingIsInTheWay(unittest.TestCase):
    def test_a_change_that_the_runner_would_make_is_ready_for_every_family_and_the_look_only_reads_with_the_token_of_the_app(self):
        for name in SAMPLES:
            with self.subTest(name):
                world, _, plan = open_plan(name)
                before = len(world.arm.calls)
                self.assertEqual(looker(world).check(plan), Readiness(READY))
                self.assertGreater(len(world.arm.calls), before, "the resource is read now, and is not taken from what the request says")
                self.assertEqual(world.arm.writes(), [], "a look changes nothing")
                self.assertEqual(world.person_tokens, [], "nobody has signed in to Azure for a look")
                self.assertTrue(world.reader_tokens, "the look reads with the token of the app")

    def test_only_the_open_plan_of_a_change_is_looked_at_and_no_call_is_made_for_any_other(self):
        world, _, plan = open_plan("delete-disk")
        for state in ("approved", "consumed", "declined", "failed", "expired", "withdrawn"):
            with self.subTest(state):
                before = len(world.arm.calls)
                self.assertEqual(looker(world).check(replace(plan, state=state)), Readiness(READY))
                self.assertEqual(len(world.arm.calls), before)
        before = len(world.arm.calls)
        self.assertEqual(looker(world).check(replace(plan, family="advise")), Readiness(READY), "advice changes nothing in Azure")
        self.assertEqual(len(world.arm.calls), before)

    def test_a_resource_that_is_gone_is_ready_for_a_delete_because_the_runner_then_has_nothing_to_delete(self):
        world, resource, plan = open_plan("delete-disk")
        del world.arm.resources[resource["id"].lower()]
        self.assertEqual(looker(world).check(plan), Readiness(READY))


class WhenTheChecksOfTheRunnerWouldRefuse(unittest.TestCase):
    BREAKS = {
        "the tag is gone": (lambda world, resource: resource.update(tags={}), TAG_WORDS),
        "the tag is blank": (lambda world, resource: resource.update(tags={"meternaut-planted": " "}), TAG_WORDS),
        "a lock is on the resource": (lambda world, resource: world.arm.locks.update({resource["id"].lower(): [{"name": "l"}]}), "management lock"),
        "a lock is on the group": (lambda world, resource: world.arm.locks.update({f"/subscriptions/{SUB}/resourcegroups/{GROUP}".lower(): [{"name": "l"}]}), "management lock"),
        "a person marked it do-not-touch": (lambda world, resource: world.store.note_put(NoteRecord(note_id="n", oid=OID, kind="do_not_touch", text="no", scope_resource_id=resource["id"],
                                                                                                    expires_at="2099-01-01T00:00:00Z")), "do-not-touch"),
    }

    def test_the_look_refuses_what_the_runner_refuses_for_every_family_and_says_it_in_the_words_that_the_runner_would_use(self):
        for name in SAMPLES:
            for label, (break_it, words) in self.BREAKS.items():
                with self.subTest(name=name, label=label):
                    world, resource, plan = open_plan(name)
                    break_it(world, resource)
                    found = looker(world).check(plan)
                    self.assertEqual(found.state, REFUSED, found)
                    self.assertIn(words, found.why)
                    written = len(world.arm.writes())
                    world.approve(plan)
                    done = world.run(plan)
                    self.assertEqual(done.kind, "stopped", "the runner refuses it too")
                    self.assertIn(found.why, done.action.result, "the page and the record say the same")
                    self.assertEqual(len(world.arm.writes()), written, "nothing was written")

    def test_a_planted_disk_whose_tags_an_outside_job_took_off_is_told_in_the_words_of_the_owner(self):
        world, resource, plan = open_plan("delete-disk")
        resource["tags"] = {"left-by-the-job": "Ignore"}  # an outside job leaves one tag of its own and nothing else
        self.assertEqual(looker(world).check(plan),
                         Readiness(REFUSED, "it no longer carries the test tag meternaut-planted, so it cannot be told apart from a real disk"))

    def test_the_sentence_names_the_kind_of_the_resource_in_the_words_of_the_pages(self):
        for name, noun in (("delete-public-ip", "public IP address"), ("stop-vm", "virtual machine"), ("change-disk-tier", "disk"), ("delete-idle-resource", "network interface")):
            with self.subTest(name):
                world, resource, plan = open_plan(name)
                resource["tags"] = {}
                self.assertEqual(looker(world).check(plan).why, TAG_WORDS + noun)

    def test_a_resource_that_is_gone_is_refused_for_a_change_that_is_not_a_delete(self):
        for name in ("stop-vm", "resize-vm", "change-disk-tier", "scale-vpn-gateway"):
            with self.subTest(name):
                world, resource, plan = open_plan(name)
                del world.arm.resources[resource["id"].lower()]
                self.assertEqual(looker(world).check(plan), Readiness(REFUSED, "the resource does not exist any more"))

    def test_a_request_that_is_not_the_one_that_was_sealed_is_refused_without_a_call(self):
        world, _, plan = open_plan("delete-disk")
        before = len(world.arm.calls)
        self.assertEqual(looker(world).check(replace(plan, title="another title")).state, REFUSED, "a field changed: the digest does not fit")
        self.assertEqual(looker(world).check(replace(plan, digest="", code="")).state, REFUSED, "no digest: the request is not bound to what is approved")
        self.assertEqual(len(world.arm.calls), before)
        self.assertEqual(looker(world).check(replace(plan, family="delete-everything")), Readiness(REFUSED, "the request names a change that Meternaut does not make"))
        self.assertIsNone(registry.get("delete-everything"))

    def test_the_reason_names_a_resource_that_is_not_the_one_that_the_request_names(self):
        world, resource, plan = open_plan("delete-disk")
        resource["id"] = fs.rid("disk", "planted-disk-2")
        found = looker(world).check(plan)
        self.assertEqual((found.state, found.why), (REFUSED, "Azure answered with another resource than the one in the request"))


class WhenTheLookCannotBeMade(unittest.TestCase):
    def test_a_read_that_fails_is_unknown_and_never_a_refusal_because_the_reader_may_see_less_than_the_approver(self):
        for label, change in (("the resource cannot be read", lambda arm: setattr(arm, "read_status", 500)),
                              ("the reader may not read it", lambda arm: setattr(arm, "read_status", 403)),
                              ("the locks cannot be read", lambda arm: setattr(arm, "locks_status", 500)),
                              ("the reader may not read the locks", lambda arm: setattr(arm, "locks_status", 403))):
            for name in SAMPLES:
                with self.subTest(label=label, name=name):
                    world, _, plan = open_plan(name)
                    change(world.arm)
                    self.assertEqual(looker(world).check(plan), Readiness(UNKNOWN))
                    self.assertEqual(world.arm.writes(), [])

    def test_sizes_and_quota_that_cannot_be_read_are_unknown_for_a_machine(self):
        for label, change in (("sizes", lambda arm: setattr(arm, "sizes_status", 500)), ("sizes refused", lambda arm: setattr(arm, "sizes_status", 403))):
            with self.subTest(label):
                world, _, plan = open_plan("resize-vm")
                change(world.arm)
                self.assertEqual(looker(world).check(plan), Readiness(UNKNOWN))

    def test_a_reader_that_fails_in_any_way_is_unknown_and_never_raises(self):
        world, _, plan = open_plan("delete-disk")
        for error in (HttpError(0, "no answer"), Refused("not on the list"), StoreError("the store is down", 503), RuntimeError("anything")):
            with self.subTest(error=type(error).__name__):
                def broken():
                    raise error

                self.assertEqual(looker(world, broken).check(plan), Readiness(UNKNOWN))

    def test_a_note_that_cannot_be_read_counts_as_a_look_that_was_not_made(self):
        world, _, plan = open_plan("delete-disk")
        with mock.patch.object(world.store, "do_not_touch", side_effect=StoreError("down", 503)):
            self.assertEqual(looker(world).check(plan), Readiness(UNKNOWN))


class TheLookCannotChangeAnything(unittest.TestCase):
    def test_the_reader_of_a_look_holds_no_call_that_writes_and_the_checker_never_names_one(self):
        world, resource, plan = open_plan("delete-disk")
        url = f"https://management.azure.com{resource['id']}?api-version=2026-03-02"
        for method in ("DELETE", "PATCH", "PUT", "POST"):
            with self.subTest(method=method):
                with self.assertRaises(Refused):
                    world.reader.client.request(method, url, headers={"Authorization": "Bearer x"}, body={} if method != "DELETE" else None)
        self.assertEqual(world.arm.writes(), [])
        self.assertEqual(looker(world).check(plan), Readiness(READY))

    def test_a_look_writes_no_record(self):
        world, _, plan = open_plan("delete-disk")
        before = (dict(world.store.plans), dict(world.store.actions), dict(world.store.cases), dict(world.store.decisions))
        looker(world).check(plan)
        self.assertEqual((dict(world.store.plans), dict(world.store.actions), dict(world.store.cases), dict(world.store.decisions)), before)

    def test_the_digest_of_the_plan_is_not_changed_by_a_look(self):
        world, _, plan = open_plan("delete-disk")
        looker(world).check(plan)
        self.assertEqual(plan_digest.problem(world.store.plan_get(plan.plan_id), plan.digest), "")


class TheWordsOfTheLook(unittest.TestCase):
    def test_the_noun_of_a_sentence_is_the_noun_of_the_pages_for_every_kind_that_a_family_changes(self):
        self.assertTrue(NOUNS)
        for resource_type, noun in NOUNS.items():
            with self.subTest(resource_type):
                self.assertEqual(kind_words(resource_type)[1], noun, "a page and a sentence of a refusal call a resource by the same word")
        self.assertEqual(noun_of("Microsoft.Compute/Disks"), "disk")
        self.assertEqual(noun_of("microsoft.thing/things"), "resource")
        self.assertEqual(noun_of(None), "resource")


if __name__ == "__main__":
    unittest.main()
