"""Everything that Meternaut may do to Azure, as the code holds it (cases/families/calls.py), pinned call by call.

A person who wants to know what an approval can do to an estate reads WRITES: these tests say that it is ten calls, each with the api-version that the REST reference of the call shows
(Microsoft Learn, read on 2026-11-08), that no write is among the reads, and that a client made from the lists refuses everything else before anything is sent.
"""
import unittest

import familysupport as fs
from familysupport import GROUP, OTHER_SUB, SCOPES, SUB, Arm

from support import APP_ROOT  # noqa: F401

from cases.families import calls
from cases.families.azure import Azure
from cases.families.gates import ChangeScope
from cases.http import Client, HttpError, Refused
from cases.runner import change_calls, read_calls

SCOPE = SCOPES[0]
PATH = f"https://management.azure.com/subscriptions/{SUB}/resourceGroups/{GROUP}/providers"


def client_of(patterns, arm=None) -> Client:
    return Client(patterns, lambda text: text, transport=(arm or Arm()).transport, sleep=lambda seconds: None, monotonic=lambda: 0.0)


def refused(client: Client, method: str, url: str) -> bool:
    try:
        client.check(method, url)
    except Refused:
        return True
    return False


class TheWrites(unittest.TestCase):
    def test_there_are_exactly_ten_and_each_has_the_api_version_that_learn_shows_for_it(self):
        found = [(call.method, f"{call.kind.provider}/{call.kind.collection}{call.suffix}", call.kind.api) for call in calls.WRITES]
        self.assertEqual(found, [
            ("DELETE", "Microsoft.Compute/disks", "2024-03-02"),
            ("DELETE", "Microsoft.Network/publicIPAddresses", "2024-05-01"),
            ("POST", "Microsoft.Compute/virtualMachines/deallocate", "2026-04-01"),
            ("PATCH", "Microsoft.Compute/virtualMachines", "2026-04-01"),
            ("PATCH", "Microsoft.Compute/disks", "2026-03-02"),
            ("DELETE", "Microsoft.Compute/snapshots", "2026-03-02"),
            ("DELETE", "Microsoft.Network/networkInterfaces", "2026-01-01"),
            ("DELETE", "Microsoft.Network/natGateways", "2026-01-01"),
            ("DELETE", "Microsoft.Network/loadBalancers", "2026-01-01"),
            ("DELETE", "Microsoft.Network/privateEndpoints", "2026-01-01"),
        ])

    def test_no_virtual_machine_and_no_scale_set_is_ever_deleted_and_no_write_is_a_put(self):
        self.assertEqual({call.method for call in calls.WRITES}, {"DELETE", "POST", "PATCH"})
        self.assertEqual([call for call in calls.WRITES if call.kind == calls.VIRTUAL_MACHINE and call.method == "DELETE"], [])
        self.assertEqual([call for call in calls.WRITES if "virtualMachineScaleSets" in call.kind.collection], [])
        self.assertEqual([call for call in calls.WRITES if call.method == "POST"], [calls.DEALLOCATE], "the one POST is the deallocate of a machine")

    def test_the_deletes_are_the_closed_list_of_what_a_family_names(self):
        self.assertEqual([call.kind.type for call in calls.DELETES], ["microsoft.compute/disks", "microsoft.network/publicipaddresses", "microsoft.compute/snapshots",
                                                                       "microsoft.network/networkinterfaces", "microsoft.network/natgateways", "microsoft.network/loadbalancers",
                                                                       "microsoft.network/privateendpoints"])

    def test_the_address_of_a_call_is_made_from_the_scope_the_name_the_suffix_and_the_api_version_and_nothing_else(self):
        self.assertEqual(calls.DEALLOCATE.url(SCOPE, "planted-vm-1"), f"{PATH}/Microsoft.Compute/virtualMachines/planted-vm-1/deallocate?api-version=2026-04-01")
        self.assertEqual(calls.write_for("PATCH", calls.DISK_TIER).url(SCOPE, "planted-disk-1"), f"{PATH}/Microsoft.Compute/disks/planted-disk-1?api-version=2026-03-02")
        self.assertEqual(calls.write_for("DELETE", calls.DISK).url(SCOPE, "planted-disk-1"), f"{PATH}/Microsoft.Compute/disks/planted-disk-1?api-version=2024-03-02")
        self.assertEqual(calls.Call("GET", calls.VIRTUAL_MACHINE).url(SCOPE, "planted-vm-1", "$expand=instanceView"),
                         f"{PATH}/Microsoft.Compute/virtualMachines/planted-vm-1?api-version=2026-04-01&$expand=instanceView")
        self.assertEqual(calls.usage_url(SUB, "swedencentral"), f"https://management.azure.com/subscriptions/{SUB}/providers/Microsoft.Compute/locations/swedencentral/usages?api-version=2026-04-01")

    def test_a_family_can_only_pick_a_call_of_the_list(self):
        for method, kind, suffix in (("DELETE", calls.VIRTUAL_MACHINE, ""), ("PATCH", calls.PUBLIC_IP, ""), ("POST", calls.DISK, "/deallocate"), ("PATCH", calls.SNAPSHOT, ""),
                                     ("PUT", calls.DISK, ""), ("DELETE", calls.DISK_TIER, "")):
            with self.subTest(method=method, kind=kind.collection, suffix=suffix):
                with self.assertRaises(LookupError):
                    calls.write_for(method, kind, suffix)
        self.assertIs(calls.write_for("POST", calls.VIRTUAL_MACHINE, "/deallocate"), calls.DEALLOCATE)

    def test_the_client_of_a_change_writes_only_a_call_of_the_list_and_never_retries_it(self):
        arm = Arm()
        arm.write_answers = [(500, {}, b'{"error":{"code":"InternalServerError","message":"boom"}}')]
        azure = Azure(client_of(change_calls(fs.SCOPES), arm), lambda resource: "person-token", "corr-1")
        with self.assertRaises(LookupError):
            azure.write(calls.Call("DELETE", calls.VIRTUAL_MACHINE), f"{PATH}/Microsoft.Compute/virtualMachines/planted-vm-1?api-version=2026-04-01")
        self.assertEqual(arm.calls, [], "nothing was sent")
        arm.add(fs.disk())
        with self.assertRaises(HttpError) as raised:
            azure.write(calls.write_for("DELETE", calls.DISK), calls.write_for("DELETE", calls.DISK).url(SCOPE, "planted-disk-1"))
        self.assertEqual(raised.exception.status, 500)
        self.assertEqual(len(arm.calls), 1, "a write that failed may have been carried out, so it is made once")
        self.assertEqual(arm.headers[0]["x-ms-correlation-request-id"], "corr-1")


class TheReads(unittest.TestCase):
    def test_none_of_them_writes_and_each_kind_that_is_written_can_be_read_again(self):
        self.assertEqual({call.method for call in calls.READS}, {"GET"})
        read = {call.kind for call in calls.READS if not call.suffix}
        for call in calls.WRITES:
            self.assertIn(call.kind, read, f"{call.method} {call.kind.collection} has no read to check it before and after")

    def test_each_read_has_the_api_version_of_its_kind(self):
        found = {(call.kind.provider + "/" + call.kind.collection + call.suffix): call.kind.api for call in calls.READS}
        self.assertEqual(found["Microsoft.Compute/virtualMachines"], "2026-04-01")
        self.assertEqual(found["Microsoft.Compute/virtualMachines/vmSizes"], "2026-04-01")
        self.assertEqual(found["Microsoft.Compute/snapshots"], "2026-03-02")
        self.assertEqual(found["Microsoft.Network/networkInterfaces"], "2026-01-01")
        self.assertEqual(calls.LOCKS_API, "2016-09-01")


class TheListsOfTheClients(unittest.TestCase):
    def setUp(self):
        self.change = client_of(change_calls(fs.SCOPES))
        self.timer = client_of(read_calls(fs.SCOPES))

    def allowed(self, client, method, url) -> bool:
        return not refused(client, method, url)

    def test_no_call_is_on_a_list_twice_although_two_kinds_of_one_collection_have_each_their_api_version(self):
        self.assertEqual(len({(kind.provider, kind.collection) for kind in calls.KINDS}), len(calls.KINDS) - 1, "the disk is read and deleted with one api-version and moved with another")
        for patterns in (change_calls(fs.SCOPES), read_calls(fs.SCOPES)):
            keys = [(method, pattern.pattern) for method, pattern in patterns]
            self.assertEqual(len(keys), len(set(keys)))

    def test_the_client_of_a_change_makes_each_call_of_the_list_in_the_scope_and_no_other(self):
        for call in calls.WRITES:
            with self.subTest(call=f"{call.method} {call.kind.collection}{call.suffix}"):
                url = call.url(SCOPE, "planted-x-1")
                self.assertTrue(self.allowed(self.change, call.method, url))
                self.assertFalse(self.allowed(self.change, call.method, call.url(ChangeScope(OTHER_SUB, GROUP), "planted-x-1")), "another subscription")
                self.assertFalse(self.allowed(self.change, call.method, call.url(ChangeScope(SUB, "rg-of-somebody-else"), "planted-x-1")), "another resource group")
                self.assertFalse(self.allowed(self.change, call.method, url.replace("https://", "http://")), "plain http")

    def test_nothing_else_is_written_not_even_on_a_kind_that_is_deleted(self):
        for method, tail in (("DELETE", "Microsoft.Compute/virtualMachines/planted-vm-1"), ("DELETE", "Microsoft.Storage/storageAccounts/plantedsa1"),
                             ("PUT", "Microsoft.Compute/disks/planted-disk-1"), ("PUT", "Microsoft.Compute/virtualMachines/planted-vm-1"),
                             ("PATCH", "Microsoft.Network/publicIPAddresses/planted-ip-1"), ("PATCH", "Microsoft.Compute/snapshots/planted-snapshot-1"),
                             ("POST", "Microsoft.Compute/virtualMachines/planted-vm-1/start"), ("POST", "Microsoft.Compute/virtualMachines/planted-vm-1/powerOff"),
                             ("POST", "Microsoft.Compute/virtualMachines/planted-vm-1/restart"), ("POST", "Microsoft.Compute/virtualMachines/planted-vm-1/redeploy"),
                             ("POST", "Microsoft.Compute/virtualMachines/planted-vm-1/runCommand"), ("POST", "Microsoft.Compute/disks/planted-disk-1/deallocate"),
                             ("POST", "Microsoft.Compute/disks/planted-disk-1/beginGetAccess"), ("DELETE", "Microsoft.Compute/virtualMachines/planted-vm-1/extensions/x"),
                             ("DELETE", "Microsoft.Authorization/locks/lock-1"), ("PUT", "Microsoft.Authorization/locks/lock-1"), ("DELETE", "Microsoft.Compute/disks"),
                             ("DELETE", "Microsoft.Compute/disks/planted-disk-1/extra"), ("DELETE", "Microsoft.Compute/disks/.."), ("DELETE", "Microsoft.Compute/disks/.")):
            with self.subTest(method=method, tail=tail):
                self.assertFalse(self.allowed(self.change, method, f"{PATH}/{tail}?api-version=2026-04-01"))

    def test_a_name_of_two_dots_does_not_walk_up_the_address_for_a_read_either(self):
        for tail in ("Microsoft.Compute/disks/..", "Microsoft.Compute/disks/.", "Microsoft.Compute/virtualMachines/../vmSizes"):
            with self.subTest(tail=tail):
                self.assertFalse(self.allowed(self.change, "GET", f"{PATH}/{tail}"))
                self.assertFalse(self.allowed(self.timer, "GET", f"{PATH}/{tail}"))
        self.assertTrue(self.allowed(self.change, "GET", f"{PATH}/Microsoft.Compute/disks/planted.disk-1"), "a dot inside a name is a name")

    def test_the_client_of_the_timer_and_of_the_watch_holds_no_write_at_all(self):
        self.assertEqual({method for method, _ in read_calls(fs.SCOPES)}, {"GET"})
        for call in calls.WRITES:
            with self.subTest(call=f"{call.method} {call.kind.collection}{call.suffix}"):
                self.assertFalse(self.allowed(self.timer, call.method, call.url(SCOPE, "planted-x-1")))
        self.assertTrue(self.allowed(self.timer, "GET", f"{PATH}/Microsoft.Compute/virtualMachines/planted-vm-1"))
        self.assertTrue(self.allowed(self.timer, "GET", f"{PATH}/Microsoft.Compute/virtualMachines/planted-vm-1/vmSizes"))

    def test_the_status_of_an_operation_is_read_by_the_client_of_a_change_only_and_only_in_the_subscription_and_the_two_providers(self):
        status = f"https://management.azure.com/subscriptions/{SUB}/providers/Microsoft.Compute/locations/swedencentral/operations/op-1"
        self.assertTrue(self.allowed(self.change, "GET", status))
        self.assertFalse(self.allowed(self.timer, "GET", status), "the timer reads the resource, not the operation")
        self.assertFalse(self.allowed(self.change, "POST", status))
        self.assertFalse(self.allowed(self.change, "GET", status.replace(SUB, OTHER_SUB)))
        self.assertFalse(self.allowed(self.change, "GET", status.replace("Microsoft.Compute", "Microsoft.Storage")))
        self.assertTrue(self.allowed(self.change, "GET", status.replace("Microsoft.Compute", "Microsoft.Network")))

    def test_the_locks_and_the_quota_are_read_in_the_scope_only(self):
        locks = f"https://management.azure.com/subscriptions/{SUB}/resourceGroups/{GROUP}/providers/Microsoft.Authorization/locks"
        usages = f"https://management.azure.com/subscriptions/{SUB}/providers/Microsoft.Compute/locations/swedencentral/usages"
        for client in (self.change, self.timer):
            self.assertTrue(self.allowed(client, "GET", locks))
            self.assertTrue(self.allowed(client, "GET", usages))
            self.assertFalse(self.allowed(client, "GET", locks.replace(SUB, OTHER_SUB)))
            self.assertFalse(self.allowed(client, "GET", usages.replace(SUB, OTHER_SUB)))
            self.assertFalse(self.allowed(client, "PUT", locks))
            self.assertFalse(self.allowed(client, "DELETE", locks))

    def test_a_list_made_for_two_scopes_holds_both_and_one_made_for_none_holds_nothing(self):
        two = client_of(change_calls((SCOPE, ChangeScope(OTHER_SUB, "meternaut-second-rg"))))
        delete = calls.write_for("DELETE", calls.DISK)
        self.assertTrue(self.allowed(two, "DELETE", delete.url(ChangeScope(OTHER_SUB, "meternaut-second-rg"), "planted-disk-1")))
        self.assertTrue(self.allowed(two, "DELETE", delete.url(SCOPE, "planted-disk-1")))
        self.assertFalse(self.allowed(two, "DELETE", delete.url(ChangeScope(OTHER_SUB, GROUP), "planted-disk-1")))
        self.assertEqual(change_calls(()), ())


if __name__ == "__main__":
    unittest.main()
