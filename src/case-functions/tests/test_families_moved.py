"""The two first families, moved into the registry, say and do what they said and did before.

The expected texts below were taken from the code as it was before the registry (the plan of an unattached disk and of an unassigned public IP address, and what the decision brief
shows for each), and they are held here word for word. The behaviour of their changes (the order of the calls, the checks, the answers) is held by test_runner.py, test_approvals.py and
test_delegated.py, which were not changed in what they ask of these two families.
"""
import unittest

import familysupport as fs
from familysupport import GROUP, NOW, OID, World

from support import APP_ROOT  # noqa: F401

from cases import brief
from cases.families import registry

CASES = {
    "delete-disk": dict(
        kind="disk", detector="orphan-managed-disk", resource=lambda: fs.disk(sku="StandardSSD_LRS"),
        title="Delete an unattached managed disk in resource group meternaut-fam-rg",
        what_changes=("When you approve and sign in to Azure, Meternaut deletes the disk named planted-disk-1 in resource group meternaut-fam-rg (subscription bbbbbbbb) with your own "
                      "permissions. It changes nothing else. Right before it deletes, it reads the resource again and stops unless the resource is still unattached or unassigned, "
                      "still carries the tag that marks it as planted by Meternaut, is still in this resource group and has no management lock."),
        undo="A deleted disk cannot be restored and its data is lost. A new disk with the same name can be made, empty.",
        observed="Azure Resource Graph lists the resource as unattached or unassigned and as planted by Meternaut.",
        headline="Delete the unattached disk planted-disk-1 in group meternaut-fam-rg",
        change="Deletes the disk planted-disk-1 in resource group meternaut-fam-rg. Nothing else changes.",
        rechecked=("Right before it acts, Meternaut reads the disk again. It stops unless the disk is still unattached, still tagged as planted by Meternaut, still in this resource "
                   "group and not locked."),
        risk="If something still uses the disk, that use stops, and the data on it is lost for good.",
        brief_undo="A deleted disk cannot be restored. A new, empty disk can be made.",
        resource_type="microsoft.compute/disks"),
    "delete-public-ip": dict(
        kind="ip", detector="orphan-public-ip", resource=lambda: fs.simple("ip"),
        title="Delete an unassigned public IP address in resource group meternaut-fam-rg",
        what_changes=("When you approve and sign in to Azure, Meternaut deletes the public IP address named planted-ip-1 in resource group meternaut-fam-rg (subscription bbbbbbbb) with "
                      "your own permissions. It changes nothing else. Right before it deletes, it reads the resource again and stops unless the resource is still unattached or "
                      "unassigned, still carries the tag that marks it as planted by Meternaut, is still in this resource group and has no management lock."),
        undo="A deleted public IP address cannot be restored. The address is released and may not be given again; a new one can be made.",
        observed="Azure Resource Graph lists the resource as unattached or unassigned and as planted by Meternaut.",
        headline="Delete the unassigned public IP address planted-ip-1 in group meternaut-fam-rg",
        change="Deletes the public IP address planted-ip-1 in resource group meternaut-fam-rg. Nothing else changes.",
        rechecked=("Right before it acts, Meternaut reads the public IP address again. It stops unless the public IP address is still unassigned, still tagged as planted by Meternaut, "
                   "still in this resource group and not locked."),
        risk="If something still points at the address, that traffic stops, and the same address may not be given again.",
        brief_undo="A deleted public IP address cannot be restored. The address is released, and a new one can be made.",
        resource_type="microsoft.network/publicipaddresses"),
}
COULD_GO_WRONG = ("If something still uses the resource, that use stops. The re-check stops the change when anything is attached or assigned. If your account may not delete the resource, "
                  "Azure refuses and nothing changes. The Skeptic role raised 2 objections: they are in the notebook.")


class TheFirstTwoFamiliesSayWhatTheySaid(unittest.TestCase):
    def made(self, name: str, cost=None):
        spec = CASES[name]
        world = World()
        resource = world.arm.add(spec["resource"]())
        item = world.lead(resource, spec["kind"], spec["detector"])
        case = world.case(item, "delete", cost, objections=("one", "two"), models={"detective": "m1", "skeptic": "m2"})
        plan = world.approvals.create(case, item, (OID,))
        self.assertIsNotNone(plan)
        return world, plan, case

    def test_the_plan_is_written_by_code_with_the_words_that_it_always_had(self):
        for name, spec in CASES.items():
            with self.subTest(name):
                world, plan, _ = self.made(name)
                self.assertEqual(plan.family, name)
                self.assertEqual((plan.title, plan.what_changes, plan.could_go_wrong, plan.undo), (spec["title"], spec["what_changes"], COULD_GO_WRONG, spec["undo"]))
                self.assertEqual(plan.evidence_level, f"Observed now: {spec['observed']} Judged: two AI roles running on different models agree. Not measured yet: the saving, "
                                                      "which cost lines confirm after the change.")
                self.assertEqual(plan.preconditions, {"family": name, "resourceType": spec["resource_type"], "tag": "meternaut-planted", "resourceGroup": GROUP})
                self.assertEqual(plan.target, {})
                self.assertEqual((plan.state, plan.approval_class, plan.approvers), ("open", "R2", (OID,)))
                self.assertEqual(world.arm.calls, [], "an older detector's lead says by its query that the resource is unused: nothing is read to write the plan")

    def test_the_saving_is_the_cost_lines_of_the_case_and_the_waiting_costs_a_thirtieth_of_it(self):
        for name in CASES:
            with self.subTest(name):
                _, plan, _ = self.made(name, cost=3.65)
                self.assertEqual((plan.saving_usd_month, plan.waiting_costs_usd_day), (3.65, 0.12))
                _, plan, _ = self.made(name, cost=None)
                self.assertEqual((plan.saving_usd_month, plan.waiting_costs_usd_day), (None, None))

    def test_the_brief_shows_what_it_always_showed_for_them(self):
        for name, spec in CASES.items():
            with self.subTest(name):
                world, plan, case = self.made(name, cost=3.65)
                shown = brief.build_brief(case, plan, None, (), now=NOW, may_answer=True)
                self.assertEqual((shown.headline, shown.change, shown.rechecked), (spec["headline"], spec["change"], spec["rechecked"]))
                self.assertEqual((shown.risk.level, shown.risk.text), ("medium", spec["risk"]))
                self.assertEqual((shown.undo.reversible, shown.undo.how), (False, spec["brief_undo"]))
                self.assertEqual(shown.who_acts, brief.WHO_ACTS)
                self.assertEqual((shown.saving.monthly, shown.saving.level, shown.saving.basis, shown.saving.waiting_per_day),
                                 (3.65, "Expected", "the cost lines of the last 30 days", 0.12))

    def test_the_older_detectors_lead_to_these_two_and_to_nothing_else(self):
        self.assertEqual({detector: family for detector, family in registry.DETECTOR_FAMILY.items()},
                         {"orphan-managed-disk": "delete-disk", "orphan-public-ip": "delete-public-ip", "stopped-vm": "stop-vm"})
        for detector in ("orphan-private-endpoint", "load-balancer-without-backends", "empty-app-service-plan", "advisor-cost"):
            self.assertEqual(registry.candidates(detector, "microsoft.compute/disks", "delete"), [], detector)

    def test_their_calls_are_the_two_deletes_with_the_api_versions_that_were_tested_in_a_real_estate(self):
        for name, path, version in (("delete-disk", "/providers/Microsoft.Compute/disks/planted-disk-1", "2024-03-02"),
                                    ("delete-public-ip", "/providers/Microsoft.Network/publicIPAddresses/planted-ip-1", "2024-05-01")):
            with self.subTest(name):
                spec = CASES[name]
                world = World()
                resource = world.arm.add(spec["resource"]())
                item = world.lead(resource, spec["kind"], spec["detector"])
                plan = world.approvals.create(world.case(item, "delete"), item, (OID,))
                world.approve(plan)
                done = world.run(plan)
                self.assertEqual((done.kind, done.action.state), ("ran", "done"), done.action.result)
                (call,) = [(m, u) for m, u in world.arm.calls if m == "DELETE"]
                self.assertEqual(call[1], f"https://management.azure.com/subscriptions/{fs.SUB}/resourceGroups/{GROUP}{path}?api-version={version}")
                self.assertEqual(done.action.result, "Deleted. Azure no longer lists the resource.")
                self.assertEqual(world.arm.bodies[-1], None)


if __name__ == "__main__":
    unittest.main()
