"""The two gates of every change (the scopes, and the planted tag with its list), the owner's switch and the third gate, a person's do-not-touch note.

Every family of the registry is held by the same gates, at three places: when the plan is made, again right before the change (the family's re-check, with the approver's token), and in
the runner before any call is made. The tests below are written over the registry, so a family that is added is held to them without a line here.
"""
import re
import unittest
from dataclasses import replace
from unittest import mock

import familysupport as fs
from familysupport import GROUP, NOW, OID, OTHER_SUB, SUB, World

from support import APP_ROOT, REPO_ROOT

from cases.approvals import ApprovalSettings, is_fixture, why_not
from cases.families import registry
from cases.families.calls import change_patterns, read_patterns
from cases.families.gates import (CHANGE_REQUIRES_PLANTED_TAG, PLANTED_NAMES, ChangeScope, Gates, has_tag, on_planted_list, parse_scopes, scope_of, why_not_planted, why_outside)
from cases.memory_store import stamp
from cases.models import NoteRecord

GATES_SOURCE = (APP_ROOT / "cases" / "families" / "gates.py").read_text(encoding="utf-8")
ANOTHER = "99999999-8888-4777-9666-555555555555"
REAL_PLANTED = dict(PLANTED_NAMES)  # the list as the code holds it: the module below holds a gateway on it for the time of its tests, as if a planting existed


def setUpModule():
    global _planting
    _planting = fs.as_if_gateways_were_planted()
    _planting.start()


def tearDownModule():
    _planting.stop()


# One good resource for each family of the registry: what the family changes, as a function that makes it, with the kind and the recommendation that lead to the family.
SAMPLES = {
    "delete-disk": ("disk", lambda **more: fs.disk(sku="StandardSSD_LRS", **more), "delete", "orphan-managed-disk"),
    "delete-public-ip": ("ip", lambda **more: fs.simple("ip", **more), "delete", "orphan-public-ip"),
    "stop-vm": ("vm", lambda **more: fs.vm(**more), "delete", "investigation"),
    "resize-vm": ("vm", lambda **more: fs.vm(**more), "change", "investigation"),
    "change-disk-tier": ("disk", lambda **more: fs.disk(sku="Premium_LRS", **more), "change", "investigation"),
    "delete-idle-resource": ("nic", lambda **more: fs.simple("nic", **more), "delete", "investigation"),
    "scale-vpn-gateway": ("p2s", lambda **more: fs.p2s(**more), "change", "investigation"),
}


def world_with(name: str, **more):
    """A world that holds one good resource for the family, its sizes when it is a machine, and the resource."""
    kind, make, recommendation, detector = SAMPLES[name]
    world = World()
    resource = world.arm.add(make(**more))
    if kind == "vm":
        world.arm.sizes[resource["id"].lower()] = fs.D_SERIES
    return world, resource, kind, recommendation, detector


class EveryFamilyHasASample(unittest.TestCase):
    def test_the_samples_are_the_families_of_the_registry_and_each_makes_the_plan_of_its_own_family(self):
        self.assertEqual(set(SAMPLES), set(registry.names()), "a family that is added has to be given a sample here, and is then held to every gate below")
        for name in SAMPLES:
            with self.subTest(name):
                world, resource, kind, recommendation, detector = world_with(name)
                plan = world.plan(resource, kind, recommendation, cost=50.0, detector=detector)
                self.assertIsNotNone(plan)
                self.assertEqual(plan.family, name)


class TheOwnersSwitch(unittest.TestCase):
    def test_it_is_true_and_the_line_and_its_comment_say_that_only_the_owner_may_change_it(self):
        self.assertIs(CHANGE_REQUIRES_PLANTED_TAG, True)
        self.assertEqual([line for line in GATES_SOURCE.splitlines() if line.startswith("CHANGE_REQUIRES_PLANTED_TAG")], ["CHANGE_REQUIRES_PLANTED_TAG = True"])
        comment = GATES_SOURCE.split("CHANGE_REQUIRES_PLANTED_TAG = True")[0].rsplit("\n\n", 1)[-1]
        for words in ("ONLY THE OWNER MAY CHANGE THIS LINE", "rule 26 (a)", "in writing", "It is not a setting", "no environment variable reaches it", "A test pins it True, and pins this comment"):
            self.assertIn(words, comment)

    def test_no_setting_no_template_no_workflow_and_no_other_module_can_reach_it(self):
        users = sorted(path.relative_to(APP_ROOT).as_posix() for path in (APP_ROOT / "cases").rglob("*.py") if "CHANGE_REQUIRES_PLANTED_TAG" in path.read_text(encoding="utf-8"))
        self.assertEqual(users, ["cases/families/gates.py"])
        for folder, pattern in (("environment", "**/*"), (".github", "**/*"), ("tools", "*.py")):
            for path in (REPO_ROOT / folder).glob(pattern):
                if path.is_file() and path.suffix in (".bicep", ".json", ".yml", ".yaml", ".py", ".sh", ".md") and "tests" not in path.parts:
                    self.assertNotIn("CHANGE_REQUIRES_PLANTED_TAG", path.read_text(encoding="utf-8", errors="ignore"), path.as_posix())

    def test_what_the_switch_does_is_shown_so_that_the_pin_means_something(self):
        unplanted = dict(tags={}, resource_type="microsoft.compute/disks", name="somebody-elses-disk")
        self.assertIsNotNone(why_not_planted(**unplanted, tag="meternaut-planted"))
        with mock.patch("cases.families.gates.CHANGE_REQUIRES_PLANTED_TAG", False):
            self.assertIsNone(why_not_planted(**unplanted, tag="meternaut-planted"), "this is the line that the owner alone may change")

    def test_the_scopes_are_not_widened_by_anything_the_watch_reads(self):
        # Reading more does not widen what may be changed (rule 29): the scopes come from the one setting, and the lists of calls are built from them and from nothing else.
        for scopes in ((), (ChangeScope(SUB, GROUP),), (ChangeScope(SUB, GROUP), ChangeScope(ANOTHER, "meternaut-two"))):
            wanted = len(scopes)
            self.assertEqual(len(change_patterns(scopes)), len(read_patterns(scopes)) + wanted * 12, "each scope adds its reads, eleven writes and the status of an operation")


class TheScopes(unittest.TestCase):
    def test_each_entry_is_one_subscription_and_one_group_and_nothing_else(self):
        scopes, problems = parse_scopes(f"{SUB.upper()}/rg-one, {ANOTHER}/rg-two")
        self.assertEqual((problems, [(s.subscription, s.group) for s in scopes]), ([], [(SUB, "rg-one"), (ANOTHER, "rg-two")]))
        for bad in ("", " ", "rg-only", SUB, f"{SUB}/", f"{SUB}/*", f"*/{SUB}", f"{SUB}/rg/extra", f"{SUB}/rg-one,,{ANOTHER}/rg-two", f"{SUB}/rg-one,{SUB.upper()}/RG-ONE", "x/rg",
                    f"{SUB}/" + "g" * 91, f"{SUB}/rg with space", f"{SUB}/rg\nx", f"{SUB}\n/rg"):
            with self.subTest(bad=bad):
                found, problems = parse_scopes(bad)
                self.assertTrue(problems, "a text that is not a list of scopes says why")
                self.assertFalse(any(re.search(r"[*?]", s.group) for s in found))

    def test_both_the_subscription_and_the_group_have_to_match_without_regard_to_case(self):
        scopes = (ChangeScope(SUB, GROUP),)
        self.assertEqual(scope_of(scopes, SUB.upper(), GROUP.upper()), scopes[0])
        for subscription, group in ((OTHER_SUB, GROUP), (SUB, "other-rg"), (None, GROUP), (SUB, None), ("", ""), (SUB, GROUP + "x")):
            with self.subTest(subscription=subscription, group=group):
                self.assertIsNone(scope_of(scopes, subscription, group))

    def test_the_reasons_say_the_one_group_while_there_is_one_and_the_groups_when_there_are_several(self):
        one = (ChangeScope(SUB, GROUP),)
        self.assertEqual(why_outside(one, SUB, "other"), "the resource is outside the one resource group in which a change may be made")
        self.assertEqual(why_outside(one, OTHER_SUB, GROUP), "the resource is outside the one subscription in which a change may be made")
        self.assertEqual(why_outside(one, "", GROUP), "the resource has no subscription id")
        self.assertIsNone(why_outside(one, SUB, GROUP))
        two = (*one, ChangeScope(ANOTHER, "meternaut-two"))
        self.assertEqual(why_outside(two, SUB, "other"), "the resource is outside the resource groups in which a change may be made")
        self.assertEqual(why_outside(two, OTHER_SUB, GROUP), "the resource is outside the subscriptions in which a change may be made")
        self.assertIsNone(why_outside(two, ANOTHER, "meternaut-two"))
        self.assertIsNotNone(why_outside(two, ANOTHER, GROUP), "the group of the other scope in the subscription of the first is not a scope")

    def test_no_scopes_at_all_means_nothing_may_be_changed(self):
        self.assertIsNotNone(why_outside((), SUB, GROUP))
        self.assertIsNone(scope_of((), SUB, GROUP))


class ThePlantedGate(unittest.TestCase):
    def test_the_tag_is_a_name_with_a_value_and_the_name_compares_without_case(self):
        self.assertTrue(has_tag({"Meternaut-Planted": "demo"}, "meternaut-planted"))
        for tags in (None, {}, {"meternaut-planted": ""}, {"meternaut-planted": "   "}, {"meternaut-planted-x": "demo"}, {"other": "demo"}):
            with self.subTest(tags=tags):
                self.assertFalse(has_tag(tags, "meternaut-planted"))

    def test_the_planted_list_holds_the_types_and_name_shapes_that_the_planting_makes(self):
        self.assertEqual(sorted(REAL_PLANTED), ["microsoft.compute/disks", "microsoft.compute/virtualmachines", "microsoft.network/networkinterfaces",
                                                "microsoft.network/publicipaddresses"])
        for kind, name in (("microsoft.compute/disks", "planted-disk-demo"), ("microsoft.compute/disks", "planted-osdisk-demo"), ("microsoft.network/publicipaddresses", "planted-ip-1"),
                           ("microsoft.compute/virtualmachines", "planted-vm-a1b2c3d4e5f6"), ("microsoft.network/networkinterfaces", "planted-nic-demo"),
                           ("Microsoft.Compute/Disks", "Planted-Disk-DEMO")):
            with self.subTest(kind=kind, name=name):
                self.assertTrue(on_planted_list(kind, name))
        for kind, name in (("microsoft.compute/disks", "planted-disk-"), ("microsoft.compute/disks", "planted-disk-abcdefghijklm"), ("microsoft.compute/disks", "my-planted-disk-1"),
                           ("microsoft.compute/disks", "planted-disk-1 "), ("microsoft.compute/disks", "planted-disk-a-b"), ("microsoft.compute/disks", "disk-1"),
                           ("microsoft.compute/disks", "planted-vm-1"), ("microsoft.compute/virtualmachines", "planted-disk-1"), ("microsoft.compute/snapshots", "planted-disk-1"),
                           ("microsoft.network/natgateways", "planted-nat-1"), ("microsoft.compute/disks", ""), ("", "planted-disk-1"), ("microsoft.compute/disks", None)):
            with self.subTest(kind=kind, name=name):
                self.assertFalse(on_planted_list(kind, name))

    def test_a_tag_alone_is_not_a_proof_and_neither_is_a_name_alone(self):
        self.assertIn("tag", why_not_planted({}, "microsoft.compute/disks", "planted-disk-1", "meternaut-planted"))
        self.assertIn("planted", why_not_planted({"meternaut-planted": "x"}, "microsoft.compute/disks", "somebody-elses-disk", "meternaut-planted"))
        self.assertIsNone(why_not_planted({"meternaut-planted": "x"}, "microsoft.compute/disks", "planted-disk-1", "meternaut-planted"))

    def test_the_planted_list_and_the_template_that_plants_are_held_together(self):
        template = (REPO_ROOT / "environment" / "cases" / "planted.bicep").read_text(encoding="utf-8")
        made = {(match.group(1).lower(), match.group(2)) for match in re.finditer(r"resource \w+ '(Microsoft\.[A-Za-z]+/[A-Za-z]+)@[0-9-]+' = (?:if \([^)]*\) )?\{\s*name: '([^']+)'", template)}
        self.assertTrue(made, "the template makes resources, each with a name")
        for kind, name in made:
            with self.subTest(kind=kind, name=name):
                self.assertTrue(on_planted_list(kind, name.replace("${plantedId}", "demo")), "what the template plants is on the planted list, or nothing could change it")
        self.assertEqual("'meternaut-planted': plantedId" in template, True, "and it carries the tag that the loop looks for")


class EveryFamilyIsHeldByTheGates(unittest.TestCase):
    """Each gate, at the three places, for every family of the registry."""

    def subtests(self):
        for name in sorted(SAMPLES):
            with self.subTest(family=name):
                yield name

    # -- when the plan is made --------------------------------------------------------------------------------------------------------------------------

    def test_a_resource_outside_the_scopes_gets_no_plan_of_a_change(self):
        for name in self.subtests():
            kind, make, recommendation, detector = SAMPLES[name]
            for label, group, subscription in (("another group", "other-rg", SUB), ("another subscription", GROUP, OTHER_SUB)):
                with self.subTest(label=label):
                    world = World()
                    resource = make()
                    resource["id"] = fs.rid(kind, resource["name"], group, subscription)
                    world.arm.add(resource)
                    item = world.lead(resource, kind, detector, group, subscription)
                    case = world.case(item, recommendation, 50.0)
                    self.assertIsNotNone(why_not(case, item, world.settings, world.store))
                    self.assertIsNone(world.approvals.create(case, item, (OID,)))
                    self.assertEqual(world.store.plans_open(), [])
                    self.assertEqual(world.arm.calls, [], "nothing was even read for a resource that no scope holds")

    def test_a_resource_without_the_tag_or_off_the_planted_list_gets_no_plan_of_a_change(self):
        for name in self.subtests():
            kind, make, recommendation, detector = SAMPLES[name]
            for label, more in (("no tag", dict(tags={})), ("a blank tag", dict(tags={"meternaut-planted": " "})), ("another tag", dict(tags={"owner": "me"})),
                                ("a name off the list", dict(name="keep-this-1"))):
                with self.subTest(label=label):
                    world = World()
                    resource = make(**more)
                    if "name" in more:
                        resource["id"] = fs.rid(kind, "keep-this-1")
                    world.arm.add(resource)
                    self.assertIsNone(world.plan(resource, kind, recommendation, 50.0, detector))
                    self.assertEqual(world.store.plans_open(), [])
                    self.assertEqual(world.arm.calls, [])

    def test_a_resource_that_a_person_marked_do_not_touch_gets_no_plan_and_an_open_plan_stops_a_second_one(self):
        for name in self.subtests():
            world, resource, kind, recommendation, detector = world_with(name)
            world.store.note_put(NoteRecord(note_id="n", oid=OID, kind="do_not_touch", text="keep", scope_resource_id=resource["id"], expires_at="2099-01-01T00:00:00Z"))
            self.assertIsNone(world.plan(resource, kind, recommendation, 50.0, detector))
            world.store.note_delete(OID, "n")
            self.assertIsNotNone(world.plan(resource, kind, recommendation, 50.0, detector))
            self.assertIsNone(world.plan(resource, kind, recommendation, 50.0, detector), "a plan for the resource is open already")

    def test_a_case_that_is_not_proposed_for_a_change_gets_no_plan(self):
        for name in self.subtests():
            world, resource, kind, recommendation, detector = world_with(name)
            for status, wanted in (("needs_human", recommendation), ("proposed", "keep"), ("proposed", "investigate")):
                with self.subTest(status=status, wanted=wanted):
                    item = world.lead(resource, kind, detector)
                    case = world.case(item, wanted, 50.0, status=status)
                    self.assertIsNone(world.approvals.create(case, item, (OID,)))

    # -- right before the change, with the approver's token -----------------------------------------------------------------------------------------------

    def test_the_recheck_stops_when_the_tag_is_gone_or_blank_or_the_resource_has_a_lock_or_a_person_says_do_not_touch(self):
        for name in self.subtests():
            for label in ("tag gone", "tag blank", "lock on the resource", "lock on the group", "do-not-touch"):
                with self.subTest(label=label):
                    world, resource, kind, recommendation, detector = world_with(name)
                    plan, _ = world.approved(resource, kind, recommendation, 50.0, detector)
                    if label == "tag gone":
                        resource["tags"] = {}
                    elif label == "tag blank":
                        resource["tags"] = {"meternaut-planted": ""}
                    elif label == "lock on the resource":
                        world.arm.locks[resource["id"].lower()] = [{"name": "l"}]
                    elif label == "lock on the group":
                        world.arm.locks[f"/subscriptions/{SUB}/resourcegroups/{GROUP}".lower()] = [{"name": "l"}]
                    else:
                        world.store.note_put(NoteRecord(note_id="n", oid=OID, kind="do_not_touch", text="no", scope_resource_id=resource["id"], expires_at="2099-01-01T00:00:00Z"))
                    written = len(world.arm.writes())
                    done = world.run(plan)
                    self.assertEqual((done.kind, done.action.state), ("stopped", "failed"), done.action.result)
                    self.assertIn("Nothing was changed", done.action.result)
                    self.assertEqual(len(world.arm.writes()), written, "no write was made")
                    self.assertEqual(world.state(plan), ("failed", "failed", "failed"))

    def test_the_plan_itself_cannot_name_another_scope_kind_or_a_name_off_the_planted_list_even_when_it_was_approved_as_it_is(self):
        for name in self.subtests():
            kind, make, recommendation, detector = SAMPLES[name]
            plain = make()
            other_kind = "disk" if kind != "disk" else "vm"
            off_list = fs.rid(kind, "keep-this-1")
            for label, mutate, expected in (
                    ("another group", {"resource_id": plain["id"].replace(GROUP, "other-rg")}, "a change may be made on"),
                    ("another subscription", {"resource_id": plain["id"].replace(SUB, OTHER_SUB)}, "a change may be made on"),
                    ("another kind", {"resource_id": fs.rid(other_kind, "planted-" + other_kind + "-1")}, "a change may be made on"),
                    ("a name off the planted list", {"resource_id": off_list}, "planted"),
                    ("an id that is not an id", {"resource_id": plain["id"] + "/extra"}, "a change may be made on")):
                with self.subTest(label=label):
                    world, resource, kind, recommendation, detector = world_with(name)
                    if label == "a name off the planted list":
                        world.arm.add(make(name="keep-this-1") | {"id": off_list})
                    plan, _ = world.approved(resource, kind, recommendation, 50.0, detector, mutate=mutate)
                    done = world.run(plan)
                    self.assertEqual((done.kind, done.action.state), ("stopped", "failed"), done.action.result)
                    self.assertIn(expected, done.action.result)
                    self.assertEqual(world.arm.writes(), [], "nothing was written")

    # -- in the runner, before any call is made ------------------------------------------------------------------------------------------------------------

    def test_a_plan_whose_family_is_not_in_the_registry_is_not_executed_and_makes_no_call(self):
        for name in self.subtests():
            world, resource, kind, recommendation, detector = world_with(name)
            plan, _ = world.approved(resource, kind, recommendation, 50.0, detector, mutate={"family": "delete-everything"})
            before = len(world.arm.calls)
            done = world.run(plan)
            self.assertEqual((done.kind, done.action.state), ("failed", "failed"))
            self.assertIn("names a change that Meternaut does not make", done.action.result)
            self.assertEqual(len(world.arm.calls), before)

    def test_the_lists_of_calls_refuse_a_resource_outside_the_scopes_whatever_the_family_asks_for(self):
        from cases.http import Refused
        world = World()
        for group, subscription in (("other-rg", SUB), (GROUP, OTHER_SUB)):
            for kind in fs.KINDS:
                url = f"https://management.azure.com{fs.rid(kind, 'planted-x-1', group, subscription)}?api-version=2026-04-01"
                for client in (world.s.client, world.t.client):
                    with self.assertRaises(Refused):
                        client.request("GET", url)
                with self.assertRaises(Refused):
                    world.s.client.request("DELETE", url)


class AGatewayIsNotPlantedSoItsFamilyIsInert(unittest.TestCase):
    """No planting of a gateway exists and none may be added (AGENTS.md rule 15 (g): a virtual hub with its gateway costs about 450 US dollars a month). So with the planted list as the code
    holds it, the family `scale-vpn-gateway` is held back by the planted gate for every resource, whatever its tag and its name: it does something only after the owner changes rule 26 (a)."""

    TYPE = "microsoft.network/p2svpngateways"

    @staticmethod
    def real():
        return mock.patch.dict("cases.families.gates.PLANTED_NAMES", REAL_PLANTED, clear=True)

    def test_the_list_holds_no_gateway_and_the_template_that_plants_makes_none(self):
        self.assertNotIn(self.TYPE, REAL_PLANTED)
        template = (REPO_ROOT / "environment" / "cases" / "planted.bicep").read_text(encoding="utf-8").lower()
        for word in ("p2svpngateways", "virtualhubs", "virtualwans"):
            self.assertNotIn(word, template)

    def test_a_gateway_with_the_tag_and_a_planted_name_gets_no_plan_and_nothing_is_even_read(self):
        with self.real():
            world = World()
            resource = world.arm.add(fs.p2s())
            self.assertIsNotNone(why_not_planted(resource["tags"], self.TYPE, resource["name"], "meternaut-planted"))
            self.assertIsNone(world.plan(resource, "p2s", "change", 50.0))
            self.assertEqual((world.store.plans_open(), world.arm.calls), ([], []))

    def test_a_plan_that_was_made_while_the_gateway_was_on_the_list_is_stopped_by_the_recheck_and_writes_nothing(self):
        world = World()
        resource = world.arm.add(fs.p2s())
        plan, _ = world.approved(resource, "p2s", "change", 50.0)
        with self.real():
            done = world.run(plan)
        self.assertEqual((done.kind, done.action.state), ("stopped", "failed"), done.action.result)
        self.assertIn("planted", done.action.result)
        self.assertEqual(world.arm.writes(), [])


class TheScopesOfTheApprovalSettings(unittest.TestCase):
    def test_a_fixture_is_a_resource_inside_a_scope_with_the_tag_and_on_the_list_and_nothing_else_is_held_back_for_being_new_by_that(self):
        world = World()
        resource = fs.disk(sku="StandardSSD_LRS")
        item = world.lead(resource, "disk", "orphan-managed-disk")
        self.assertTrue(is_fixture(item, world.settings))
        for changes in ({"tags": {}}, {"name": "keep-this"}, {"resource_group": "other-rg"}, {"subscription_id": OTHER_SUB}, {"resource_type": "microsoft.storage/storageaccounts"}):
            with self.subTest(changes=changes):
                self.assertFalse(is_fixture(replace(item, **changes), world.settings))
        two = ApprovalSettings(change_scopes=(ChangeScope(SUB, GROUP), ChangeScope(ANOTHER, "meternaut-two")))
        self.assertTrue(is_fixture(replace(item, subscription_id=ANOTHER, resource_group="meternaut-two"), two))
        self.assertFalse(is_fixture(replace(item, subscription_id=ANOTHER, resource_group=GROUP), two))

    def test_the_gates_object_gives_the_scopes_and_the_tag_to_whoever_asks(self):
        gates = Gates((ChangeScope(SUB, GROUP),), "my-tag")
        self.assertEqual(gates.planted_tag, "my-tag")
        self.assertIsNone(gates.why_not_planted({"my-tag": "x"}, "microsoft.compute/disks", "planted-disk-1"))
        self.assertIsNotNone(gates.why_not_planted({"meternaut-planted": "x"}, "microsoft.compute/disks", "planted-disk-1"))
        self.assertEqual(stamp(NOW), "2026-11-08T09:00:00Z")


if __name__ == "__main__":
    unittest.main()
