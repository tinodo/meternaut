"""The family that moves a disk one tier down, and the family that deletes a resource of a closed list when nothing uses it.

The tier is chosen by code from a table of steps that Learn documents; the idle kinds are listed one by one, each with its own reader of what "nothing uses it" means for it, read from Azure's
own answer. A kind that is not listed has no family. The planted list holds disks, public IP addresses, machines and network interfaces (what the planting makes), so for the other kinds
of the closed list the test says that the planting made them, to show the family's own checks apart from the gate that the other tests hold.
"""
import datetime as dt
import re
import unittest
from dataclasses import replace
from unittest import mock

import familysupport as fs
from familysupport import GROUP, OID, SUB, World

from support import APP_ROOT  # noqa: F401

from cases import brief
from cases.families import calls, gates, idle, registry
from cases.families.disk import STEPS, sku_of
from cases.families.words import DELETE_WORDING, tier_words
from cases.models import NoteRecord

TIERS = {"Premium_LRS": "StandardSSD_LRS", "StandardSSD_LRS": "Standard_LRS", "Premium_ZRS": "StandardSSD_ZRS"}


def vm_of_the_planting(world, power="deallocated", **more):
    return world.arm.add(fs.vm(power=power, **more))


class MovingADiskOneTierDown(unittest.TestCase):
    def test_each_step_of_the_table_is_one_tier_down_and_the_plan_says_which_and_what_does_not_change(self):
        for sku, target in TIERS.items():
            with self.subTest(sku):
                world = World()
                resource = world.arm.add(fs.disk(sku=sku, size_gb=64))
                plan = world.plan(resource, "disk", "change", cost=20.0)
                self.assertEqual((plan.family, plan.target), ("change-disk-tier", {"skuName": target, "fromSkuName": sku}))
                self.assertEqual(plan.title, f"Move a managed disk to {tier_words(target)} in resource group meternaut-fam-rg")
                self.assertIn(f"from {tier_words(sku)} to {tier_words(target)}, with your own permissions. It changes nothing else: not the data and not the size.", plan.what_changes)
                self.assertIn("The disk is not attached to anything, so nothing stops while it changes.", plan.what_changes)
                self.assertIn("lower limits on operations and throughput", plan.could_go_wrong)
                self.assertIn("twice a day", plan.could_go_wrong)
                self.assertIn(f"Change the disk back to {tier_words(sku)}", plan.undo)
                self.assertIn(f"the disk is a {tier_words(sku)} and is unattached, as Azure shows it now", plan.evidence_level)
                self.assertEqual(plan.preconditions["family"], "change-disk-tier")

    def test_a_standard_ssd_of_up_to_16_gib_is_not_moved_to_a_standard_hdd_because_that_is_billed_from_32_gib_and_costs_more(self):
        for size, planned in ((1, False), (4, False), (8, False), (16, False), (17, True), (32, True), (128, True), (None, False)):
            with self.subTest(size=size):
                world = World()
                resource = world.arm.add(fs.disk(sku="StandardSSD_LRS", size_gb=size))
                self.assertEqual(world.plan(resource, "disk", "change", cost=20.0) is not None, planned)
        for size in (1, 4, 16, 17, 32768, None):
            with self.subTest(premium=size):
                world = World()
                resource = world.arm.add(fs.disk(sku="Premium_LRS", size_gb=size))
                self.assertIsNotNone(world.plan(resource, "disk", "change", cost=20.0), "a Premium SSD is dearer than a Standard SSD of any size")

    def test_a_size_that_azure_shows_as_something_else_than_a_whole_number_of_gib_counts_as_not_shown(self):
        for shown in (True, False, "64", 0, -1, 65537, 1.5, [64]):
            with self.subTest(shown=shown):
                world = World()
                resource = world.arm.add(fs.disk(sku="StandardSSD_LRS", size_gb=None))
                resource["properties"]["diskSizeGB"] = shown
                self.assertIsNone(world.plan(resource, "disk", "change", cost=20.0))

    def test_the_table_is_the_documented_one_and_holds_nothing_that_is_converted_in_a_way_that_azure_does_not_allow(self):
        self.assertEqual({name: target for name, target in ((k.lower(), v) for k, v in TIERS.items())}, STEPS)
        for sku in ("Standard_LRS", "UltraSSD_LRS", "PremiumV2_LRS", "StandardSSD_ZRS", "Premium_LRS_x", ""):
            with self.subTest(sku):
                world = World()
                resource = world.arm.add(fs.disk(sku=sku or "x"))
                self.assertIsNone(world.plan(resource, "disk", "change", cost=20.0), "no lower tier, or a type that is not converted in place")

    def test_a_disk_is_never_moved_to_a_tier_that_is_not_in_the_list_of_the_five(self):
        self.assertEqual(sku_of({"sku": {"name": "premium_lrs"}}), "Premium_LRS", "the name compares without case and is given as Azure writes it")
        for bad in ({}, {"sku": None}, {"sku": {"name": None}}, {"sku": {"name": "Premium_LRS; drop"}}, {"sku": {"name": "UltraSSD_LRS"}}, {"sku": {"name": "x" * 50}}):
            with self.subTest(bad=bad):
                self.assertEqual(sku_of(bad), "")

    def test_the_plan_claims_no_figure_because_the_price_of_a_disk_depends_on_its_size_and_the_price_list_is_not_read(self):
        world = World()
        resource = world.arm.add(fs.disk(sku="Premium_LRS"))
        item = world.lead(resource, "disk")
        case = world.case(item, "change", 20.0)
        plan = world.approvals.create(case, item, (OID,))
        self.assertEqual((plan.saving_usd_month, plan.waiting_costs_usd_day), (None, None))
        shown = brief.build_brief(case, plan, None, (), now=fs.NOW, may_answer=True)
        self.assertEqual((shown.saving.monthly, shown.saving.level), (None, ""))
        self.assertIn("Meternaut does not read the price list, so it claims no figure for this change", shown.saving.why_none)

    def test_a_disk_that_is_attached_to_a_machine_of_the_planting_that_is_stopped_and_released_can_be_moved(self):
        world = World()
        machine = vm_of_the_planting(world)
        resource = world.arm.add(fs.disk(sku="Premium_LRS", state="Attached", managed_by=machine["id"]))
        plan = world.plan(resource, "disk", "change", cost=20.0)
        self.assertIsNotNone(plan)
        self.assertIn("The disk is attached to a machine that is stopped and released, so nothing runs while it changes.", plan.what_changes)

    def test_a_disk_that_is_attached_to_anything_else_is_not_moved(self):
        for label, build in (
                ("a running machine", lambda w: vm_of_the_planting(w, power="running")),
                ("a machine that did not come from the planting", lambda w: vm_of_the_planting(w, tags={})),
                ("a machine in another group", lambda w: w.arm.add(fs.vm() | {"id": fs.rid("vm", "planted-vm-1", "other-rg")})),
                ("a machine that cannot be found", lambda w: {"id": fs.rid("vm", "planted-vm-9")})):
            with self.subTest(label):
                world = World()
                machine = build(world)
                resource = world.arm.add(fs.disk(sku="Premium_LRS", state="Attached", managed_by=machine["id"]))
                self.assertIsNone(world.plan(resource, "disk", "change", cost=20.0))

    def test_a_disk_in_a_state_that_is_neither_unattached_nor_attached_to_a_machine_is_not_moved(self):
        world = World()
        resource = world.arm.add(fs.disk(sku="Premium_LRS", state="Reserved"))
        self.assertIsNone(world.plan(resource, "disk", "change", cost=20.0))


class RecheckingBeforeTheMove(unittest.TestCase):
    def setUp(self):
        self.world = World()
        self.resource = self.world.arm.add(fs.disk(sku="Premium_LRS"))
        self.plan, _ = self.world.approved(self.resource, "disk", "change", 20.0)

    def stopped(self, why):
        done = self.world.run(self.plan)
        self.assertEqual((done.kind, done.action.state), ("stopped", "failed"), done.action.result)
        self.assertIn(why, done.action.result)
        self.assertEqual(self.world.arm.writes(), [])

    def test_it_stops_when_the_tier_is_neither_the_one_of_the_plan_nor_the_aim(self):
        self.resource["sku"] = {"name": "Standard_LRS"}
        self.stopped("not of the tier that the plan was made for any more")

    def test_it_stops_when_the_disk_has_been_attached_to_a_running_machine_since(self):
        machine = vm_of_the_planting(self.world, power="running")
        self.resource["managedBy"], self.resource["properties"]["diskState"] = machine["id"], "Attached"
        self.stopped("attached to a machine that is not stopped and released")

    def test_it_stops_when_the_disk_has_been_attached_to_a_machine_that_is_not_the_plantings(self):
        machine = vm_of_the_planting(self.world, tags={})
        self.resource["managedBy"], self.resource["properties"]["diskState"] = machine["id"], "Attached"
        self.stopped("attached to a machine that Meternaut did not plant")

    def test_it_stops_when_the_disk_is_in_a_state_that_is_not_one_for_a_conversion(self):
        self.resource["properties"]["diskState"] = "ActiveSAS"
        self.stopped("not unattached")

    def test_it_makes_the_change_when_the_disk_is_attached_to_a_machine_of_the_planting_that_is_released(self):
        machine = vm_of_the_planting(self.world)
        self.resource["managedBy"], self.resource["properties"]["diskState"] = machine["id"], "Attached"
        done = self.world.run(self.plan)
        self.assertEqual((done.kind, done.action.state), ("ran", "done"), done.action.result)


class TheCallToChangeTheTier(unittest.TestCase):
    def test_it_is_one_patch_of_the_one_property_with_the_api_version_of_learn_and_the_disk_shows_the_new_tier(self):
        world = World()
        resource = world.arm.add(fs.disk(sku="Premium_LRS"))
        plan, action = world.approved(resource, "disk", "change", 20.0)
        done = world.run(plan)
        self.assertEqual((done.kind, done.action.state), ("ran", "done"), done.action.result)
        (patch,) = [(m, u) for m, u in world.arm.calls if m == "PATCH"]
        self.assertEqual(patch[1], f"https://management.azure.com/subscriptions/{SUB}/resourceGroups/{GROUP}/providers/Microsoft.Compute/disks/planted-disk-1?api-version=2026-03-02")
        index = world.arm.calls.index(patch)
        self.assertEqual(world.arm.bodies[index], {"sku": {"name": "StandardSSD_LRS"}})
        self.assertEqual(world.arm.headers[index]["x-ms-correlation-request-id"], action.correlation_id)
        self.assertEqual(done.action.verification["now"], "Standard SSD (StandardSSD_LRS)")
        self.assertEqual(world.arm.get(resource["id"])["sku"]["name"], "StandardSSD_LRS")

    def test_a_plan_that_names_a_tier_that_is_not_one_of_the_five_is_refused_before_it_is_used_in_a_call(self):
        for bad in ("UltraSSD_LRS", "Premium_LRS; x", "", "premium_lrs", "StandardSSD_LRS\n"):
            with self.subTest(bad=bad):
                world = World()
                resource = world.arm.add(fs.disk(sku="Premium_LRS"))
                plan, _ = world.approved(resource, "disk", "change", 20.0, mutate={"target": {"skuName": bad, "fromSkuName": "Premium_LRS"}})
                done = world.run(plan)
                self.assertEqual(world.arm.writes(), [])
                self.assertEqual(done.action.state, "failed")

    def test_the_change_is_confirmed_by_the_cost_lines_by_the_rate_of_a_day_not_by_the_end_of_all_cost(self):
        world = World()
        resource = world.arm.add(fs.disk(sku="Premium_LRS"))
        plan, _ = world.approved(resource, "disk", "change", 30.0)
        world.run(plan)
        world.costs.totals = {resource["id"].lower(): 1.0}
        world.clock.advance(days=5)
        self.assertEqual([a.state for a in world.tick().verified], ["verified"])
        self.assertEqual(world.action(plan).verification["savedUsdMonth"], 20.0,
                         "before: 30 over 30 days is 1 a day; after: 1.0 over the 3 whole days that follow the day of the change (9 to 11 November) is a third of that")
        self.assertEqual(world.costs.asked, [(SUB, dt.date(2026, 11, 9), dt.date(2026, 11, 11))])


# -- the idle resources ---------------------------------------------------------------------------------------------------------------------------------

PLANTED_BY_THE_TEST = {
    "microsoft.compute/snapshots": re.compile(r"planted-snapshot-[a-z0-9]{1,12}"),
    "microsoft.network/natgateways": re.compile(r"planted-nat-[a-z0-9]{1,12}"),
    "microsoft.network/loadbalancers": re.compile(r"planted-lb-[a-z0-9]{1,12}"),
    "microsoft.network/privateendpoints": re.compile(r"planted-pe-[a-z0-9]{1,12}"),
}
CONNECTION = lambda status: {"properties": {"privateLinkServiceConnectionState": {"status": status}}}  # noqa: E731
IDLE = {
    "snapshot": ({"provisioningState": "Succeeded"}, "2026-03-02", "Microsoft.Compute/snapshots", "Delete a snapshot"),
    "nic": ({"ipConfigurations": [{"properties": {}}]}, "2026-01-01", "Microsoft.Network/networkInterfaces", "Delete an unattached network interface"),
    "nat": ({}, "2026-01-01", "Microsoft.Network/natGateways", "Delete a NAT gateway that serves no subnet"),
    "lb": ({"loadBalancingRules": [], "backendAddressPools": [{"properties": {"backendIPConfigurations": []}}]}, "2026-01-01", "Microsoft.Network/loadBalancers",
           "Delete a load balancer with no backends and no rules"),
    "pe": ({"privateLinkServiceConnections": [CONNECTION("Disconnected")]}, "2026-01-01", "Microsoft.Network/privateEndpoints", "Delete a disconnected private endpoint"),
}
IN_USE = {
    "snapshot": [{"provisioningState": "Updating"}, {"diskState": "Attached"}, {"diskState": "ActiveSAS"}],
    "nic": [{"virtualMachine": {"id": "/x"}}, {"privateEndpoint": {"id": "/x"}}, {"privateLinkService": {"id": "/x"}},
            {"ipConfigurations": [{"properties": {"loadBalancerBackendAddressPools": [{"id": "/x"}]}}]},
            {"ipConfigurations": [{"properties": {"applicationGatewayBackendAddressPools": [{"id": "/x"}]}}]},
            {"ipConfigurations": [{"properties": {"loadBalancerInboundNatRules": [{"id": "/x"}]}}]}],
    "nat": [{"subnets": [{"id": "/x"}]}],
    "lb": [{"loadBalancingRules": [{"id": "/x"}]}, {"inboundNatRules": [{}]}, {"inboundNatPools": [{}]}, {"outboundRules": [{}]},
           {"backendAddressPools": [{"properties": {"backendIPConfigurations": [{"id": "/x"}]}}]}, {"backendAddressPools": [{"properties": {"loadBalancerBackendAddresses": [{}]}}]}],
    "pe": [{"privateLinkServiceConnections": [CONNECTION("Approved")]}, {"privateLinkServiceConnections": [CONNECTION("Pending")]},
           {"manualPrivateLinkServiceConnections": [CONNECTION("Rejected")]}, {"privateLinkServiceConnections": [CONNECTION("Disconnected"), CONNECTION("Approved")]},
           {}, {"privateLinkServiceConnections": [{"properties": {}}]}],
}


class DeletingWhatNothingUses(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.dict(gates.PLANTED_NAMES, PLANTED_BY_THE_TEST)
        patcher.start()
        self.addCleanup(patcher.stop)

    def idle(self, world, kind, properties=None):
        return world.arm.add(fs.simple(kind, properties=IDLE[kind][0] if properties is None else properties))

    def test_the_closed_list_is_five_kinds_each_with_its_own_reader_and_its_own_words_and_its_own_delete(self):
        self.assertEqual(sorted(idle.BY_TYPE), sorted(["microsoft.compute/snapshots", "microsoft.network/networkinterfaces", "microsoft.network/natgateways",
                                                       "microsoft.network/loadbalancers", "microsoft.network/privateendpoints"]))
        family = registry.get("delete-idle-resource")
        self.assertEqual([kind.type for kind in family.kinds], list(idle.BY_TYPE))
        for kind in family.kinds:
            self.assertIn(kind.type, DELETE_WORDING)
            self.assertEqual(len([c for c in calls.WRITES if c.method == "DELETE" and c.kind == kind]), 1, kind.type)
        listed = {c.kind.type for c in calls.WRITES if c.method == "DELETE"}
        self.assertEqual(listed, {"microsoft.compute/disks", "microsoft.network/publicipaddresses", *idle.BY_TYPE}, "no delete exists that no family names")

    def test_an_idle_resource_of_each_kind_gets_a_plan_in_its_own_words_and_a_resource_in_use_gets_none(self):
        for kind, (properties, version, path, title) in IDLE.items():
            with self.subTest(kind):
                world = World()
                plan = world.plan(self.idle(world, kind), kind, "delete", cost=5.0)
                self.assertEqual((plan.family, plan.title), ("delete-idle-resource", f"{title} in resource group meternaut-fam-rg"))
                self.assertEqual(plan.target, {})
                self.assertEqual(plan.preconditions["resourceType"], fs.KINDS[kind][2])
                self.assertIn("When you approve and sign in to Azure, Meternaut deletes the", plan.what_changes)
                self.assertIn("with your own permissions", plan.what_changes)
                for state in IN_USE[kind]:
                    with self.subTest(kind=kind, in_use=state):
                        busy = World()
                        self.assertIsNone(busy.plan(self.idle(busy, kind, state), kind, "delete", cost=5.0))

    def test_the_call_of_each_kind_is_one_delete_with_the_api_version_of_learn_and_the_resource_is_gone_afterwards(self):
        for kind, (properties, version, path, title) in IDLE.items():
            with self.subTest(kind):
                world = World()
                resource = self.idle(world, kind)
                plan, action = world.approved(resource, kind, "delete", 5.0)
                done = world.run(plan)
                self.assertEqual((done.kind, done.action.state), ("ran", "done"), done.action.result)
                (delete,) = [(m, u) for m, u in world.arm.calls if m == "DELETE"]
                self.assertEqual(delete[1], f"https://management.azure.com/subscriptions/{SUB}/resourceGroups/{GROUP}/providers/{path}/{fs.NAMES[kind]}?api-version={version}")
                self.assertEqual(world.arm.bodies[world.arm.calls.index(delete)], None)
                self.assertEqual(done.action.result, "Deleted. Azure no longer lists the resource.")
                self.assertNotIn(resource["id"].lower(), world.arm.resources)

    def test_the_reader_is_asked_again_right_before_the_delete_and_a_resource_that_is_in_use_by_then_is_not_deleted(self):
        for kind in IDLE:
            for state in IN_USE[kind]:
                with self.subTest(kind=kind, state=state):
                    world = World()
                    resource = self.idle(world, kind)
                    plan, _ = world.approved(resource, kind, "delete", 5.0)
                    resource["properties"] = dict(state)
                    done = world.run(plan)
                    self.assertEqual((done.kind, done.action.state), ("stopped", "failed"), done.action.result)
                    self.assertEqual(world.arm.writes(), [])
                    self.assertIn("Nothing was changed", done.action.result)

    def test_a_kind_that_is_not_on_the_closed_list_has_no_family_and_so_no_plan(self):
        world = World()
        resource = {"id": f"/subscriptions/{SUB}/resourceGroups/{GROUP}/providers/Microsoft.Storage/storageAccounts/planted-sa-1", "name": "planted-sa-1", "tags": fs.PLANTED}
        world.arm.add(resource)
        item = replace(world.lead(resource, "disk"), resource_type="microsoft.storage/storageaccounts")
        case = world.case(item, "delete", 5.0)
        self.assertEqual(registry.candidates("investigation", item.resource_type, "delete"), [])
        self.assertIsNone(world.approvals.create(case, item, (OID,)))
        self.assertEqual(world.arm.calls, [])

    def test_the_readers_judge_only_what_azure_shows_and_a_property_that_is_not_shown_counts_as_nothing_there(self):
        self.assertIsNone(idle.snapshot_in_use({}))
        self.assertIsNone(idle.snapshot_in_use({"properties": {"diskState": "Unattached", "provisioningState": "Succeeded"}}))
        self.assertIsNone(idle.network_interface_in_use({"properties": {"ipConfigurations": "text"}}))
        self.assertIsNone(idle.nat_gateway_in_use({"properties": {"subnets": []}}))
        self.assertIsNone(idle.load_balancer_in_use({"properties": {"backendAddressPools": [{"properties": {"backendIPConfigurations": []}}, "text"]}}))
        self.assertIsNone(idle.private_endpoint_in_use({"properties": {"privateLinkServiceConnections": [CONNECTION("disconnected")]}}), "the state compares without case")
        self.assertIn("shows no connection to judge", idle.private_endpoint_in_use({"properties": {}}))
        self.assertIn("not Disconnected", idle.private_endpoint_in_use({"properties": {"privateLinkServiceConnections": [CONNECTION("Approved <b>")]}}))

    def test_the_gates_hold_for_a_kind_that_the_planting_does_not_make_unless_the_planting_made_it(self):
        for kind in ("snapshot", "nat", "lb", "pe"):
            with self.subTest(kind):
                world = World()
                self.assertIsNotNone(world.plan(self.idle(world, kind), kind, "delete", cost=5.0), "the list says that the planting made it")
        for name in PLANTED_BY_THE_TEST:
            gates.PLANTED_NAMES.pop(name)
        for kind in ("snapshot", "nat", "lb", "pe"):
            with self.subTest(kind=kind, planted=False):
                world = World()
                self.assertIsNone(world.plan(self.idle(world, kind), kind, "delete", cost=5.0), "a resource of a kind that the planting does not make is never changed")


class TheNetworkInterfaceThatThePlantingMakes(unittest.TestCase):
    def test_a_network_interface_that_belongs_to_no_machine_is_deleted_and_one_that_belongs_to_a_machine_is_not(self):
        world = World()
        nic = world.arm.add(fs.simple("nic", properties={"ipConfigurations": [{"properties": {}}]}))
        plan, _ = world.approved(nic, "nic", "delete", 0.0)
        self.assertEqual(world.run(plan).action.state, "done")
        world = World()
        nic = world.arm.add(fs.simple("nic", properties={"virtualMachine": {"id": fs.rid("vm")}}))
        self.assertIsNone(world.plan(nic, "nic", "delete", cost=0.0))

    def test_a_note_that_says_do_not_touch_stops_it_like_every_other_family(self):
        world = World()
        nic = world.arm.add(fs.simple("nic"))
        plan, _ = world.approved(nic, "nic", "delete", 0.0)
        world.store.note_put(NoteRecord(note_id="n", oid=OID, kind="do_not_touch", text="no", scope_resource_id=nic["id"], expires_at="2099-01-01T00:00:00Z"))
        done = world.run(plan)
        self.assertEqual((done.kind, done.action.state), ("stopped", "failed"))
        self.assertIn("do-not-touch", done.action.result)


if __name__ == "__main__":
    unittest.main()
