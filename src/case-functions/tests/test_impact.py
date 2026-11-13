"""The impact of removing a resource: what depends on it, read by code with reads only (cases/impact.py), the verdict that code derives from the facts, and what a person reads of it.

AGENTS.md rules 26, 29 and 30: no AI makes, sees or argues the verdict; the app has no write right, and a read that fails is never "nothing found". Everything here is invented: a fake of Azure answers.
"""
import dataclasses
import datetime as dt
import re
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import support  # noqa: F401  (it puts the app on the path)
from support import NOW, RG, SUBSCRIPTION, LogCapture
from test_decisions import SAFE_GUARDS, lead as detector_lead
from test_held_back import finding as held_case, request_for, watch as run_watch
from test_investigate import FakeArm, FakeFoundry, FakeToolbox, Harness, answer, finding, metrics, resource
from test_letters import BASE, CONTACTS, PERSON
from test_missing_data import ABSENT, DISK, ENDPOINTS, PE, endpoint_case, endpoint_plan
from test_run_loop import Moving, loop_for
from test_unread import page_of, walk_blocks
from test_web_support import NOW as WEB_NOW, SUB, make_advice, make_advice_case

from cases import brief, cards, evidence, impact, investigate, learning, letters, stake
from cases.approvals import IMPACT_NOT_CHECKED
from cases.arm import MetricPoint
from cases.http import HttpError

SERVICE = f"/subscriptions/{SUB}/resourceGroups/rg-apim/providers/Microsoft.ApiManagement/service/apim-demo"
ZONE = f"/subscriptions/{SUB}/resourceGroups/rg-dns/providers/Microsoft.Network/privateDnsZones/privatelink.azure-api.net"
OTHER = f"/subscriptions/{SUB}/resourceGroups/rg-platform/providers/Microsoft.Network/privateEndpoints/pe-apim-other"
RUN_PE = f"{RG}/rg-platform/providers/Microsoft.Network/privateEndpoints/pe-apim-demo"  # the same endpoint in the subscription of the runs of the investigation
IP, OTHER_IP = "10.20.0.5", "10.20.0.6"
NIC_HIT = {"type": "microsoft.network/networkinterfaces", "n": 1}  # the endpoint's own network interface holds its address: the search that works lists it
OWN = "99999999-8888-7777-6666-555555555555"
AUTOMATION = "aaaaaaaa-1111-4222-8333-444444444444"
UNANALYSED = brief.NOT_ANALYSED


def connection(state, service=SERVICE, said="", actions="None"):
    return {"properties": {"privateLinkServiceId": service, "groupIds": ["Gateway"],
                           "privateLinkServiceConnectionState": {"status": state, "description": said, "actionsRequired": actions}}}


def endpoint_row(state="Disconnected", pe=PE, service=SERVICE):
    return {"id": pe, "name": pe.rsplit("/", 1)[-1], "properties": {"privateLinkServiceConnections": [], "manualPrivateLinkServiceConnections": [connection(state, service, "Removed by the owner")],
                                                                  "customDnsConfigs": [{"fqdn": "apim-demo.azure-api.net", "ipAddresses": [IP]}]}}


def service_row(state="Disconnected", public="Enabled", pe=PE):
    return {"id": SERVICE, "name": "apim-demo", "properties": {"publicNetworkAccess": public, "privateEndpointConnections": [
        {"properties": {"privateEndpoint": {"id": pe}, "privateLinkServiceConnectionState": {"status": state}}}]}}


def other_row(state="Approved"):
    return {"id": OTHER, "name": "pe-apim-other", "properties": {"privateLinkServiceConnections": [connection(state)], "manualPrivateLinkServiceConnections": []}}


def zone_group():
    return {"name": "default", "properties": {"privateDnsZoneConfigs": [{"name": "zone", "properties": {"privateDnsZoneId": ZONE, "recordSets": [
        {"recordSetName": "apim-demo", "recordType": "A", "fqdn": "apim-demo.privatelink.azure-api.net.", "ipAddresses": [IP], "ttl": 10}]}}]}}


def a_record(name, *ips):
    return {"name": name, "properties": {"ttl": 10, "aRecords": [{"ipv4Address": ip} for ip in ips]}}


def days(total, count=30):
    return [MetricPoint(f"2026-10-{day:02d}T00:00:00Z", total, total, total) for day in range(1, count + 1)]


def written(days_ago, caller):
    when = (NOW - dt.timedelta(days=days_ago)).strftime("%Y-%m-%dT%H:%M:%S.0000000Z")
    return {"operationName": {"value": "Microsoft.Network/privateEndpoints/write"}, "status": {"value": "Succeeded"}, "eventTimestamp": when, "caller": caller}


class Azure(FakeArm):
    """A fake of everything that the impact check reads: Resource Graph, the two lists of Azure Resource Manager, Azure Monitor and the Activity Log. By default the endpoint is Disconnected, the
    service says so, another endpoint to the service is approved, one DNS record holds only its address, nothing mentions it (but its own network interface does), nobody changed it, the Activity
    Log was read to its end and no traffic was counted in 30 days. `fail` maps the name of a read (endpoint, service, others, mentions, dns, zone, traffic) to the status that it answers with."""

    def __init__(self, pe=PE):
        super().__init__()
        self.pe = pe
        self.rows = {pe: endpoint_row(pe=pe), SERVICE: service_row(pe=pe)}
        self.others, self.mentions, self.groups, self.records = [other_row()], [NIC_HIT], [zone_group()], {ZONE: [a_record("apim-demo", IP)]}
        self.points = {"PEBytesIn": days(0), "PEBytesOut": days(0)}
        self.fail: dict[str, int] = {}
        self.read: list[str] = []
        self.log_complete = True

    def activity_events(self, subscription, since, until, *, resource_id=None, group=None, max_pages=3):
        events, _ = super().activity_events(subscription, since, until, resource_id=resource_id, group=group, max_pages=max_pages)
        return events, self.log_complete

    def _get(self, what):
        self.read.append(what)
        if what in self.fail:
            raise HttpError(self.fail[what], f"GET management.azure.com: {self.fail[what]} not now")

    def graph_many(self, subscriptions, query):
        what = re.match(r"// meternaut:impact-(\w+)", query).group(1)
        if what == "one":
            what = "service" if f"'{SERVICE}'" in query else "endpoint"
        self._get(what)
        return [row for key, row in self.rows.items() if f"'{key}'" in query] if what in ("endpoint", "service") else self.others if what == "others" else self.mentions

    def zone_groups(self, endpoint_id):
        self._get("dns")
        return self.groups

    def zone_records(self, zone_id):
        self._get("zone")
        return self.records.get(zone_id, [])

    def metrics(self, resource_id, metric, start, end):
        self._get("traffic")
        return "Count", self.points.get(metric, [])


def check(azure=None, **limits):
    azure = azure or Azure()
    return impact.analyse(impact.Reader(azure, [SUBSCRIPTION], NOW, own=[OWN], **limits), azure.pe, ENDPOINTS), azure


def arrange(state="Disconnected", *, theirs=None, public="Enabled", others=True, points=None, mentions=(), events=()):
    def apply(azure):
        azure.rows[PE], azure.rows[SERVICE] = endpoint_row(state), service_row(theirs or state, public)
        azure.others = [other_row()] if others else []
        azure.points = {"PEBytesIn": days(0) if points is None else points, "PEBytesOut": days(0) if points is None else points}
        azure.mentions, azure.events = [NIC_HIT, *mentions], list(events)
    return apply


class TheCheckOfAPrivateEndpoint(unittest.TestCase):
    def test_a_disconnected_endpoint_that_nothing_depends_on_is_safe_to_remove_and_says_what_removing_it_does(self):
        found, _ = check()
        self.assertEqual((found["verdict"], found["complete"]), ("safe", True))
        self.assertEqual(found["reasons"][0], impact.STATE_SAYS["disconnected"])
        self.assertIn("Another endpoint to the same service is approved.", found["reasons"])
        self.assertIn("Azure Monitor shows no traffic.", found["reasons"])
        traffic, dns = found["removal"]
        self.assertEqual(traffic, "No traffic changes: it cannot carry any.")
        self.assertIn("apim-demo", dns)
        self.assertIn("privatelink.azure-api.net", dns)
        self.assertIn("get no answer for those names", dns)
        rows = {row[0]: row[1:] for row in found["rows"]}
        self.assertEqual(rows["State that the endpoint reports"], ["Disconnected: Removed by the owner; actions required: None", "Azure Resource Graph: the endpoint"])
        self.assertEqual(rows["What the service says about it"][0], "Disconnected")
        self.assertEqual(rows["Public access of the service"][0], "Enabled")
        self.assertEqual(rows["Other endpoints to the service"][0], "1 (1 approved)")
        self.assertEqual(rows["DNS records of the endpoint"][0], "apim-demo")
        self.assertEqual(rows["Last change"], ["No change found in the 90 days before Meternaut read it", "Activity Log"])
        self.assertTrue(all(row[2] for row in found["rows"]), "every fact says where it was read")
        self.assertEqual(rows["Things that mention its addresses"][0], "None", "the search found the endpoint's own network interface, so a miss of other things is a result")
        self.assertEqual(found["readAt"], "2026-11-04T12:00:00Z", "the digest says when it was read, in UTC")
        self.assertEqual(found["unchecked"], list(impact.NEVER_SEEN), "what the reads cannot see is always said, whatever they found")
        self.assertIn("a policy or a template makes it again", found["unchecked"][0])
        self.assertEqual(found["undo"], impact.UNDO)

    def test_the_rules_turn_the_facts_into_the_verdict_and_into_nothing_else(self):
        for label, arranged, expected in (
                ("approved and carrying traffic", arrange("Approved", points=days(5)), "keep"),
                ("the only approved way to a service that takes no public traffic", arrange("Approved", others=False, public="Disabled"), "keep"),
                ("approved and quiet, with another approved endpoint", arrange("Approved"), "check"),
                ("approved and quiet, alone, and the service takes public traffic", arrange("Approved", others=False), "check"),
                ("approved and not measured", arrange("Approved", points=[]), "check"),
                ("pending", arrange("Pending"), "check"),
                ("rejected", arrange("Rejected"), "safe"),
                ("disconnected and not measured", arrange(points=[]), "safe"),
                ("disconnected, but the service lists it as approved", arrange(theirs="Approved"), "check"),
                ("disconnected, but traffic was counted", arrange(points=days(3)), "check"),
                ("something mentions its addresses", arrange(mentions=[{"type": "microsoft.network/routetables", "n": 1}]), "check"),
                ("an automation changed it 40 days ago", arrange(events=[written(40, AUTOMATION)]), "check"),
                ("a person changed it yesterday", arrange(events=[written(1, "alice@example.com")]), "safe"),
                ("a person changed it yesterday and an automation 40 days ago", arrange(events=[written(1, "alice@example.com"), written(40, AUTOMATION)]), "check"),
                ("Meternaut changed it", arrange(events=[written(1, OWN)]), "safe")):
            with self.subTest(case=label):
                azure = Azure()
                arranged(azure)
                found, _ = check(azure)
                self.assertEqual((found["verdict"], found["complete"]), (expected, True), found["reasons"])
                self.assertTrue(found["reasons"], "every verdict has its reasons")

    def test_the_reasons_of_check_first_name_the_specific_things(self):
        azure = Azure()
        arrange(mentions=[{"type": "microsoft.network/routetables", "n": 1}, {"type": "microsoft.network/networksecuritygroups", "n": 2}], events=[written(3, AUTOMATION)])(azure)
        found, _ = check(azure)
        self.assertEqual(found["verdict"], "check")
        self.assertIn("Something else mentions its addresses (routetables (1), networksecuritygroups (2)): check that it does not rely on this endpoint.", found["reasons"])
        self.assertIn("An application or service identity changed it on 1 Nov 2026 UTC: an automation may manage it and make it again.", found["reasons"])
        rows = {row[0]: row[1] for row in found["rows"]}
        self.assertEqual(rows["Things that mention its addresses"], "routetables (1), networksecuritygroups (2)")
        self.assertTrue(rows["Last change"].startswith("1 Nov 2026 UTC, by an application or service identity (id "), rows["Last change"])
        self.assertTrue(rows["Last change"].endswith("; 1 change in the 90 days before Meternaut read it"), rows["Last change"])

    def test_a_read_that_failed_is_never_none_so_the_verdict_is_never_safe_and_the_line_says_what_was_not_checked(self):
        for what, label in (("endpoint", "the endpoint itself"), ("service", "the service that it points at"), ("others", "the other endpoints to the service"),
                            ("mentions", "what mentions its addresses"), ("dns", "the DNS zone groups of the endpoint"), ("zone", "the records of its DNS zone"), ("traffic", "its traffic"),
                            ("log", "its changes in the Activity Log")):
            for status, how in ((503, "the read failed"), (403, "not visible with this access")):
                if what == "log" and status == 403:
                    continue
                with self.subTest(read=what, status=status):
                    azure = Azure()
                    if what == "log":
                        azure.log_fails = True
                    else:
                        azure.fail[what] = status
                    found, _ = check(azure)
                    self.assertEqual((found["complete"], found["verdict"] == "safe"), (False, False))
                    self.assertIn(f"{label} ({how})", found["unchecked"])
                    self.assertIn("Not everything could be read (see Not checked), so this cannot be called safe.", found["reasons"])
                    row = {"others": "Other endpoints to the service", "dns": "DNS records of the endpoint", "mentions": "Things that mention its addresses"}.get(what)
                    if row:
                        self.assertEqual({r[0]: r[1] for r in found["rows"]}[row], f"Not known ({how})", "a read that failed is never none or 0 in the table either")

    def test_a_log_that_was_read_in_part_is_not_complete_and_never_safe(self):
        for label, events in (("no change in the part that was read", []), ("a person's change in it", [written(1, "alice@example.com")])):
            with self.subTest(case=label):
                azure = Azure()
                azure.events, azure.log_complete = events, False
                found, _ = check(azure)
                self.assertEqual((found["verdict"], found["complete"]), ("check", False), found["reasons"])
                self.assertIn("its changes in the Activity Log (only part of the 90 days was read)", found["unchecked"])
                self.assertIn("the part of the 90 days that was read", {row[0]: row[1] for row in found["rows"]}["Last change"])
        azure = Azure()
        azure.events = [written(1, "alice@example.com")]
        found, _ = check(azure)
        self.assertEqual((found["verdict"], found["complete"]), ("safe", True), "the whole log, with nobody but a person in it, is safe")
        self.assertNotIn("Activity Log", " ".join(found["unchecked"][:-3]))

    def test_an_endpoint_with_no_address_that_could_be_read_is_not_searched_and_never_safe(self):
        azure = Azure()
        azure.rows[PE]["properties"]["customDnsConfigs"], azure.groups = [], []
        found, _ = check(azure)
        self.assertEqual((found["verdict"], found["complete"], "mentions" in azure.read), ("check", False, False), "nothing was searched, so nothing was found")
        self.assertEqual({row[0]: row[1] for row in found["rows"]}["Things that mention its addresses"], "Not searched")
        self.assertIn("the addresses of the endpoint (none could be read, so nothing could be searched for)", found["unchecked"])
        self.assertNotIn("Nothing that Azure Resource Graph lists mentions its addresses.", found["reasons"])
        azure = Azure()
        azure.rows[PE]["properties"]["customDnsConfigs"] = [{"fqdn": "x.example.net", "ipAddresses": [f"10.20.0.{number}" for number in range(1, 9)]}]
        found, _ = check(azure)
        self.assertEqual((found["verdict"], "mentions" in azure.read), ("check", True))
        self.assertIn("the addresses of the endpoint (only 6 of its 8 were searched for)", found["unchecked"], "an address that was left out of the search is not one that nothing mentions")

    def test_a_service_that_cannot_be_seen_is_not_a_service_with_nothing_to_say(self):
        azure = Azure()
        del azure.rows[SERVICE]
        found, _ = check(azure)
        self.assertEqual((found["verdict"], found["complete"], found["facts"]["service"]), ("check", False, "unseen"))
        self.assertIn("the service that it points at (it could not be seen: it may be in a subscription that Meternaut cannot read)", found["unchecked"])
        self.assertEqual({row[0]: row[1] for row in found["rows"]}["What the service says about it"], "The service could not be seen")
        facts = {"state": "disconnected", "service": "unseen", "serviceSays": "unknown", "publicAccess": "unknown", "othersApproved": 1, "traffic": "zero", "changedBy": "none", "changedAt": "",
                 "complete": True, "searched": True}
        verdict, reasons = impact._judge(facts, "")
        self.assertNotIn("Another endpoint to the same service is approved.", reasons, "what an unseen service says is not known, so what rests on it is not a reason")
        self.assertIn("Another endpoint to the same service is approved.", impact._judge({**facts, "service": "seen"}, "")[1])

    def test_a_search_that_does_not_find_the_endpoints_own_network_interface_cannot_be_trusted(self):
        self.assertNotIn("networkinterfaces", impact.MENTIONS, "the query leaves no interface out: the endpoint's own one is the positive control")
        azure = Azure()
        azure.mentions = []
        found, _ = check(azure)
        self.assertEqual((found["verdict"], found["complete"]), ("check", False))
        self.assertIn("what mentions its addresses (the search did not find the endpoint's own network interface, so its answer cannot be trusted)", found["unchecked"])
        self.assertNotIn("Nothing that Azure Resource Graph lists mentions its addresses.", found["reasons"])
        self.assertTrue({row[0]: row[1] for row in found["rows"]}["Things that mention its addresses"].startswith("Not known (the search did not find"))
        azure.mentions = [{"type": "Microsoft.Network/networkInterfaces", "n": 2}]
        found, _ = check(azure)
        self.assertEqual((found["verdict"], found["facts"]["mentions"]), ("safe", 0), "the interfaces are the control and no mention: whatever the case of the type")
        azure.mentions = [{"type": "microsoft.network/routetables", "n": 1}]
        found, _ = check(azure)
        self.assertEqual(found["verdict"], "check")
        self.assertEqual({row[0]: row[1] for row in found["rows"]}["Things that mention its addresses"], "routetables (1)", "a hit is listed even when the control missed: a hit is a fact")

    def test_what_a_person_reads_of_a_state_is_what_learn_says_of_it(self):
        # Learn: only an approved endpoint can send traffic, and the owner of the service can change the state later (so a rejected endpoint may have carried traffic). Learn does not settle whether a
        # rejected connection can be approved again: "Manage Azure private endpoints" says that a connection that was denied cannot be, and two troubleshooting pages say, for Rejected, to ask the
        # owner to approve it. So no sentence says either.
        self.assertEqual(impact.STATE_SAYS["rejected"], "The owner of the service rejected it, so it cannot carry traffic now: only an approved endpoint can.")
        for state, text in impact.STATE_SAYS.items():
            with self.subTest(state=state):
                self.assertNotRegex(text, r"never|again|could approve|can't be approved|cannot be approved", "a rejected endpoint may have carried traffic, and Learn does not say whether the owner can approve it again")
        azure = Azure()
        arrange("Rejected", events=[written(40, "alice@example.com")])(azure)
        found, _ = check(azure)
        self.assertEqual((found["verdict"], found["reasons"][0]), ("safe", impact.STATE_SAYS["rejected"]))
        self.assertIn("Microsoft says that such an endpoint becomes informative and should be deleted for cleanup.", impact.STATE_SAYS["disconnected"])

    def test_traffic_in_the_window_of_a_rejected_or_disconnected_endpoint_names_its_real_state_and_may_have_come_before_the_change(self):
        for state in ("Disconnected", "Rejected"):
            with self.subTest(state=state):
                azure = Azure()
                arrange(state, points=days(3))(azure)
                found, _ = check(azure)
                word = state.lower()
                self.assertEqual((found["verdict"], found["complete"]), ("check", True), "traffic means that it is not safe to remove")
                self.assertEqual(found["reasons"], [f"Azure Monitor counted traffic in the 30 days before Meternaut read it, and the endpoint is {word} now: the connection may have changed inside those 30 days, "
                                                    "so something may have used it until then."])
                self.assertNotRegex(" ".join(found["reasons"]), r"although|disagree")
                self.assertEqual("disconnected" in " ".join(found["reasons"]), state == "Disconnected", "a rejected endpoint is not called disconnected")

    def test_the_public_access_of_a_service_that_was_not_read_is_not_known_and_is_not_just_not_stated(self):
        def row(azure):
            return {name: value for name, value, _ in check(azure)[0]["rows"]}["Public access of the service"]

        failed = Azure()
        failed.fail["service"] = 503
        refused = Azure()
        refused.fail["service"] = 403
        unseen = Azure()
        del unseen.rows[SERVICE]
        nameless = Azure()
        nameless.rows[PE]["properties"]["manualPrivateLinkServiceConnections"] = []
        silent = Azure()
        del silent.rows[SERVICE]["properties"]["publicNetworkAccess"]
        self.assertEqual([row(azure) for azure in (failed, refused, unseen, nameless, silent, Azure())],
                         ["Not known (the service could not be read)", "Not known (the service could not be read)", "Not known (the service could not be seen)", "Not known (no service is named)",
                          "Not stated", "Enabled"], "a service that says nothing is 'Not stated'; a service that was not read says that it is not known")

    def test_the_words_hold_dates_and_never_yesterday_because_a_page_may_be_opened_days_after_the_read(self):
        azure = Azure()
        arrange(events=[written(1, "alice@example.com")])(azure)
        found, _ = check(azure)
        last = {row[0]: row[1] for row in found["rows"]}["Last change"]
        self.assertEqual(last, "3 Nov 2026 UTC, by alice@example.com; 1 change in the 90 days before Meternaut read it")
        later = impact.Reader(azure, [SUBSCRIPTION], NOW + dt.timedelta(days=5), own=[OWN])
        again = impact.analyse(later, azure.pe, ENDPOINTS)
        self.assertEqual({row[0]: row[1] for row in again["rows"]}["Last change"], last, "the same words five days later: the date of the write, not how long ago")
        self.assertEqual((found["readAt"], again["readAt"]), ("2026-11-04T12:00:00Z", "2026-11-09T12:00:00Z"))
        for text in (*found["reasons"], *(row[1] for row in found["rows"])):
            self.assertNotRegex(text, r"(?i)yesterday|today|days ago|last 30 days")
        arrange(events=[written(1, "alice@example.com"), written(40, AUTOMATION)])(azure)
        found, _ = check(azure)
        self.assertEqual({row[0]: row[1] for row in found["rows"]}["Last change"].split(", by ")[0:1] + [found["facts"]["changedAt"]], ["3 Nov 2026 UTC", "2026-09-25T12:00:00Z"],
                         "the row says the newest write, and the automation's older one is named as such")
        self.assertIn("; an application or service identity wrote on 25 Sep 2026 UTC; 2 changes in the 90 days before Meternaut read it", {row[0]: row[1] for row in found["rows"]}["Last change"])
        self.assertIn("An application or service identity changed it on 25 Sep 2026 UTC: an automation may manage it and make it again.", found["reasons"])

    def test_no_data_for_the_traffic_is_not_zero_and_a_few_days_are_not_a_measurement(self):
        for label, points, expected in (("no data", [], "unmeasured"), ("ten days of nil", days(0, 10), "unmeasured"), ("twenty days of nil", days(0, 20), "zero"), ("a little", days(1, 3), "some")):
            with self.subTest(case=label):
                azure = Azure()
                azure.points = {"PEBytesIn": points, "PEBytesOut": points}
                found, _ = check(azure)
                self.assertEqual(found["facts"]["traffic"], expected)
        azure = Azure()
        azure.points = {"PEBytesIn": days(0), "PEBytesOut": []}
        found, _ = check(azure)
        self.assertEqual(found["facts"]["traffic"], "unmeasured", "one metric without data is not a zero of the endpoint")
        self.assertTrue({row[0]: row[1] for row in found["rows"]}["Traffic in the 30 days before it was read"].startswith("Not measured"))

    def test_the_best_connection_counts_and_a_connection_that_names_no_service_that_can_be_read_is_not_checked(self):
        azure = Azure()
        azure.rows[PE]["properties"]["privateLinkServiceConnections"] = [connection("Approved")]
        found, _ = check(azure)
        self.assertEqual(found["facts"]["state"], "approved")
        self.assertEqual({row[0]: row[1] for row in found["rows"]}["State that the endpoint reports"], "Approved at best, of 2 connections (approved, disconnected)")
        azure = Azure()
        azure.rows[PE]["properties"]["manualPrivateLinkServiceConnections"][0]["properties"]["privateLinkServiceId"] = SERVICE + "'x"
        found, _ = check(azure)
        self.assertEqual((found["complete"], found["verdict"], "service" in azure.read, "others" in azure.read), (False, "check", False, False), "an id with a quote never goes into a query")
        self.assertIn("the service that it points at (the read failed)", found["unchecked"])

    def test_a_record_that_holds_the_addresses_of_others_says_so_and_keeps_theirs(self):
        azure = Azure()
        azure.records[ZONE] = [a_record("apim-demo", IP, OTHER_IP), a_record("another", OTHER_IP)]
        found, _ = check(azure)
        self.assertEqual({row[0]: row[1] for row in found["rows"]}["DNS records of the endpoint"], "apim-demo; 1 also hold the addresses of others")
        self.assertIn("a record that also holds the addresses of others keeps theirs", found["removal"][1])

    def test_the_budget_of_the_reads_is_one_for_the_run_and_the_checks_after_it_are_not_complete(self):
        found, azure = check(max_reads=3)
        self.assertEqual((found["complete"], found["verdict"], len(azure.read)), (False, "check", 3))
        reader = impact.Reader(Azure(), [SUBSCRIPTION], NOW, max_reads=100)
        self.assertEqual(impact.analyse(reader, PE, ENDPOINTS)["verdict"], "safe")
        self.assertGreater(reader.reads, 3)

    def test_a_fault_of_the_check_is_a_digest_that_is_not_complete_and_other_types_have_no_check(self):
        azure = Azure()
        azure.graph_many = mock.Mock(side_effect=ValueError("broken"))
        found, _ = check(azure)
        self.assertEqual((found["verdict"], found["complete"], found["reasons"]), ("check", False, ["The check could not be made."]))
        reader = impact.Reader(Azure(), [SUBSCRIPTION], NOW)
        self.assertIsNone(impact.analyse(reader, DISK, "microsoft.compute/disks"))
        self.assertIsNone(impact.analyse(reader, PE + "'", ENDPOINTS))
        self.assertIsNone(impact.analyse(reader, PE, 5))
        self.assertEqual([impact.has_check(kind) for kind in ("Microsoft.Network/privateEndpoints", ENDPOINTS, "microsoft.compute/disks", "", None)], [True, True, False, False, False])

    def test_the_check_only_reads_with_the_reads_that_the_app_may_make(self):
        found, azure = check()
        self.assertEqual((found["complete"], azure.log_reads), (True, 1))
        self.assertEqual(sorted(set(azure.read)), ["dns", "endpoint", "mentions", "others", "service", "traffic", "zone"])
        source = (Path(impact.__file__)).read_text(encoding="utf-8")
        self.assertEqual(set(re.findall(r"arm\.(\w+)\(", source)), {"graph_many", "zone_groups", "zone_records", "metrics"}, "the only calls of the module to Azure")
        self.assertEqual(re.findall(r"\b(?:put|post|patch|delete|request|urlopen)\(", source, re.I), [], "no write and no call of its own")
        queries = [impact.ONE, impact.OTHERS, impact.MENTIONS]
        self.assertTrue(all(query.startswith("// meternaut:impact-") and "\nresources\n" in query for query in queries), "each query reads the table of resources and says that it is this app's own")


def digest_of(verdict):
    arranged = {"safe": arrange(), "keep": arrange("Approved", points=days(5)), "check": arrange("Pending")}[verdict]
    azure = Azure()
    arranged(azure)
    return check(azure)[0]


def case_with(found, **changes):
    facts = {"basis": "other", "proposal": "investigate", "asked": "delete", "metrics": {}, "finding": 1, **({"impact": found} if found is not None else {})}
    return endpoint_case(recommendation="investigate", saving_usd_month=None, facts=facts, **changes)


class WhatAPersonReads(unittest.TestCase):
    def test_the_page_says_the_verdict_the_reasons_where_each_fact_was_read_what_removal_does_how_to_undo_it_and_what_was_not_checked(self):
        found = digest_of("safe")
        case = case_with(found)
        reply, text = page_of(case, endpoint_plan(case, saving_usd_month=None))
        self.assertIn("Impact", reply.headings(2))
        self.assertNotIn("Check first", reply.headings(2), "the reasons say what to check, not the general list")
        self.assertEqual([h for h in reply.headings(3) if h.startswith(("If it is", "How to"))], ["If it is removed", "How to undo it"])
        self.assertIn("Safe to remove", text)
        self.assertIn("Read on 4 Nov 2026 UTC.", text, "the page says when it was read: it may be opened days later")
        for line in (*found["reasons"], *found["removal"], found["undo"], "Not checked: " + "; ".join(found["unchecked"]) + "."):
            self.assertIn(line, text)
        (table,) = [t for t in reply.main.find_all("table") if t.find("caption").attrs.get("id") == "impact"]
        rows = {row.find("th").text(): [cell.text() for cell in row.find_all("td")] for row in table.find_all("tr")[1:]}
        self.assertEqual(rows["Traffic in the 30 days before it was read"][1], "Azure Monitor")
        self.assertEqual(len(rows), 8)
        self.assertEqual(reply.main.find("p", class_="chips").text(), "Medium risk if you act on it Low confidence Answering changes nothing in Azure")
        self.assertEqual(reply.facts()["What could go wrong"], f"If you act on it: {brief.SAFE_RISK} Risk: medium.")
        self.assertEqual(reply.headings(1), ["Check whether the private endpoint pe-apim-demo is still used"], "a shared kind of resource is never asked to be deleted, whatever the verdict")

    def test_the_risk_of_acting_follows_the_verdict_and_never_the_risk_of_answering(self):
        for verdict, level, words in (("safe", "medium", brief.SAFE_RISK), ("keep", "high", brief.KEEP_RISK)):
            with self.subTest(verdict=verdict):
                case = case_with(digest_of(verdict))
                b = brief.build_brief(case, endpoint_plan(case, saving_usd_month=None), now=WEB_NOW, may_answer=True)
                self.assertEqual((b.risk.level, b.risk.text, b.impact.verdict), (level, f"If you act on it: {words}", verdict))
                self.assertEqual(stake.chips_of(b)[0], f"{level.capitalize()} risk if you act on it")
                self.assertEqual((b.check_first, b.change), ((), brief.ADVICE_CHANGE))
        case = case_with(digest_of("check"))
        b = brief.build_brief(case, endpoint_plan(case, saving_usd_month=None), now=WEB_NOW, may_answer=True)
        self.assertEqual((b.impact.verdict, b.risk.level, b.risk.text), ("check", "high", "If you act on it: " + brief.UNPROVEN + " " + brief.SHARED_RISK))

    def test_the_card_and_the_letter_carry_the_verdict_and_its_first_reason_in_one_line(self):
        for verdict, label in (("safe", "Safe to remove"), ("keep", "Do not remove"), ("check", "Check first")):
            with self.subTest(verdict=verdict):
                found = digest_of(verdict)
                case = case_with(found)
                plan = endpoint_plan(case, saving_usd_month=None)
                line = f"Impact: {label}. Read on 4 Nov 2026 UTC. {found['reasons'][0].partition('. ')[0]}"
                b = brief.build_brief(case, plan, now=WEB_NOW, may_answer=True)
                self.assertEqual(b.impact.line, line if line.endswith(".") else line + ".")
                texts = {block["id"]: block["text"] for block in walk_blocks(cards.decision_card(b, cards.CardContext(page_url=f"https://meternaut.example/ok/{plan.plan_id}")))}
                self.assertEqual((texts["impact"], "check-first" in texts), (b.impact.line, False))
                letter = letters.approval_letter(plan, case, PERSON, BASE, WEB_NOW, CONTACTS)
                self.assertIn(b.impact.line, letter.text)
                self.assertLessEqual(len(b.impact.line.split()), 30, "a letter has little room: the line holds the verdict and the first sentence of the first reason")
                self.assertNotIn("console", letter.text.lower())

    def test_every_line_says_when_it_was_read_and_a_digest_with_no_date_says_that_it_is_not_known(self):
        found = digest_of("check")
        case = case_with(found)
        plan = endpoint_plan(case, saving_usd_month=None)
        lines = {brief.build_brief(case, plan, now=now, may_answer=True).impact.line for now in (WEB_NOW, WEB_NOW + dt.timedelta(days=9))}
        self.assertEqual(len(lines), 1, "the words do not depend on the day that the page is opened")
        shown = brief.impact_of(case)
        self.assertEqual((shown.read, shown.line.startswith("Impact: Check first. Read on 4 Nov 2026 UTC. ")), ("Read on 4 Nov 2026 UTC.", True))
        undated = brief.impact_of(case_with({key: value for key, value in found.items() if key != "readAt"}))
        self.assertEqual((undated.read, undated.line.startswith("Impact: Check first. The date that it was read is not known. ")), ("The date that it was read is not known.", True))

    def test_the_details_do_not_say_that_an_ai_saw_what_only_code_worked_out(self):
        case = case_with(digest_of("safe"))
        case = dataclasses.replace(case, facts={**case.facts, "gateways": {"gateways": 2, "counted": 5}})
        reply, _ = page_of(case, endpoint_plan(case, saving_usd_month=None))
        self.assertEqual({row["Fact"] for row in reply.table("facts").rows}, {"asked", "basis", "finding", "metrics", "proposal"})
        self.assertNotIn("readAt", reply.content, "the digest is not printed as a row of raw JSON anywhere on the page")
        self.assertEqual(sorted(case.facts), ["asked", "basis", "finding", "gateways", "impact", "metrics", "proposal"], "the case keeps the digest all the same")

    def test_an_unfinished_check_says_so_in_the_line_of_the_card_and_the_letter(self):
        azure = Azure()
        azure.fail["traffic"] = 503
        found, _ = check(azure)
        case = case_with(found)
        b = brief.build_brief(case, endpoint_plan(case, saving_usd_month=None), now=WEB_NOW, may_answer=True)
        self.assertTrue(b.impact.line.endswith(" Part of it could not be read."), b.impact.line)
        self.assertEqual(b.impact.unchecked, "Not checked: its traffic (the read failed); " + "; ".join(impact.NEVER_SEEN) + ".")
        longest = {**found, "reasons": ["Something else mentions its addresses (" + ", ".join(f"routetables{n} ({n})" for n in range(30)) + "): check that it does not rely on this endpoint."]}
        case = case_with(longest)
        plan = endpoint_plan(case, saving_usd_month=None)
        b = brief.build_brief(case, plan, now=WEB_NOW, may_answer=True)
        self.assertGreater(len(b.impact.line), 300, "the first sentence is cut at 240 characters and the line is longer than a letter once allowed")
        texts = {block["id"]: block["text"] for block in walk_blocks(cards.decision_card(b, cards.CardContext(page_url=f"https://meternaut.example/ok/{plan.plan_id}")))}
        self.assertTrue(texts["impact"].endswith("Part of it could not be read."), "the caveat is the last thing that a card or a letter may lose")
        self.assertIn(b.impact.line, letters.approval_letter(plan, case, PERSON, BASE, WEB_NOW, CONTACTS).text)

    def test_a_finding_whose_kind_has_no_check_or_whose_check_was_not_made_says_that_nothing_was_analysed_and_keeps_the_general_list(self):
        case = case_with(None)
        plan = endpoint_plan(case, saving_usd_month=None)
        reply, text = page_of(case, plan)
        self.assertIn("Impact", reply.headings(2))
        self.assertIn("Check first", reply.headings(2))
        self.assertIn(UNANALYSED, text)
        b = brief.build_brief(case, plan, now=WEB_NOW, may_answer=True)
        self.assertEqual((b.impact.verdict, b.impact.line, b.check_first), ("", UNANALYSED, brief.CHECK_FIRST))
        texts = {block["id"]: block["text"] for block in walk_blocks(cards.decision_card(b, cards.CardContext(page_url=f"https://meternaut.example/ok/{plan.plan_id}")))}
        self.assertEqual((texts["impact"], texts["check-first"]), (UNANALYSED, brief.CHECK_FIRST_SHORT))
        self.assertIn(UNANALYSED, letters.approval_letter(plan, case, PERSON, BASE, WEB_NOW, CONTACTS).text)
        self.assertNotIn("Impact not analysed", reply.headings(2))

    def test_what_meternaut_planted_and_what_the_older_detectors_found_show_no_impact_and_a_digest_that_is_no_digest_counts_for_nothing(self):
        planted = make_advice_case(detector="orphan-managed-disk", recommendation="delete", resource_type="microsoft.compute/disks", facts={"state": "unattached"})
        self.assertIsNone(brief.build_brief(planted, make_advice(), now=WEB_NOW).impact)
        for label, hostile in (("a verdict that is none of the three", {"verdict": "delete now", "complete": True, "reasons": ["x"]}), ("not a dict", "safe"), ("a list", ["safe"])):
            with self.subTest(case=label):
                b = brief.build_brief(case_with(hostile), endpoint_plan(case_with(hostile), saving_usd_month=None), now=WEB_NOW, may_answer=True)
                self.assertEqual((b.impact.verdict, b.impact.line), ("", UNANALYSED))
        found = {"verdict": "keep", "complete": True, "reasons": ["a\u202eb", 5, "  "], "rows": [["x", "y\u0007", "z"], ["bad"], "no"], "removal": "text", "undo": None, "unchecked": ["q\u202e"]}
        shown = brief.impact_of(case_with(found))
        self.assertEqual((shown.reasons, shown.rows, shown.removal, shown.undo, shown.unchecked), (("ab",), (("x", "y", "z"),), (), "", "Not checked: q."))


def watch_endpoint(azure, **options):
    toolbox = FakeToolbox([resource(1, resource_id=RUN_PE, resource_type=ENDPOINTS, name="pe-apim-demo", resource_group="rg-platform", cost_usd_30d=70.0)], {"r1": ABSENT})
    h = Harness(FakeFoundry(answer(finding(handles=["r1"], basis="other", proposal="delete"))), toolbox, with_store=True, **options)
    h.arm = h.s.arm = azure
    h.go()
    return h


class TheInvestigationChecksWhatItProposesToRemove(unittest.TestCase):
    def test_a_private_endpoint_is_checked_once_with_the_reads_of_the_run_and_the_digest_goes_to_the_case_and_the_page(self):
        azure = Azure(RUN_PE)
        h = watch_endpoint(azure)
        (case,) = h.store.cases_recent()
        self.assertEqual((case.facts["impact"]["verdict"], case.facts["impact"]["complete"]), ("safe", True))
        self.assertEqual(azure.log_reads, 1, "the owner line and the check share one read of the Activity Log")
        self.assertEqual([what for what in azure.read if what == "endpoint"], ["endpoint"])
        (plan,) = h.store.plans_open()
        b = brief.build_brief(case, plan, now=WEB_NOW, may_answer=True)
        self.assertEqual((b.impact.verdict, b.check_first, b.risk.level), ("safe", (), "medium"))

    def test_a_run_with_more_resources_than_room_checks_the_oldest_first_and_a_case_judged_again_keeps_the_digest_that_it_had(self):
        clock = Moving()
        extras = loop_for(clock)
        pes = [RUN_PE.replace("pe-apim-demo", f"pe-apim-{n}") for n in range(1, 5)]
        azure = Azure(pes[0])
        azure.rows.update({pe: endpoint_row(pe=pe) for pe in pes[1:]})

        def run(days_later):
            clock.now = NOW + dt.timedelta(days=days_later)
            toolbox = FakeToolbox([resource(n, resource_id=pe, resource_type=ENDPOINTS, name=f"pe-apim-{n}", resource_group="rg-platform", cost_usd_30d=100.0 - n) for n, pe in enumerate(pes, 1)],
                                  {f"r{n}": ABSENT for n in range(1, 5)})
            h = Harness(FakeFoundry(answer(finding(handles=["r1", "r2", "r3", "r4"], basis="other", proposal="delete"))), toolbox, with_store=True, clock=clock, extras=extras)
            h.arm = h.s.arm = azure
            azure.read.clear()
            with mock.patch.object(investigate, "MAX_IMPACTS", 2):
                h.go()
            read = {case.resource_name[-1]: (case.facts.get("impact") or {}).get("readAt", "") for case in h.store.cases_recent()}
            return read, azure.read.count("endpoint"), {case.resource_name[-1]: brief.impact_of(case).read for case in h.store.cases_recent()}

        day = lambda days_later: (NOW + dt.timedelta(days=days_later)).strftime("%Y-%m-%dT%H:%M:%SZ")
        first, reads, _ = run(0)
        self.assertEqual((first, reads), ({"1": day(0), "2": day(0), "3": "", "4": ""}, 2), "the room is two: the first two are checked, and the others are not analysed")
        second, reads, said = run(8)
        self.assertEqual((second, reads), ({"1": day(0), "2": day(0), "3": day(8), "4": day(8)}, 2), "the ones with no digest go first, and the others keep theirs")
        self.assertEqual(said["1"], "Read on 4 Nov 2026 UTC.", "a case that is judged again keeps what was read, with the date of the read, and is not shown as not analysed")
        third, reads, _ = run(16)
        self.assertEqual((third, reads), ({"1": day(16), "2": day(16), "3": day(8), "4": day(8)}, 2), "then the oldest digests are read again")

    def test_a_kind_of_resource_without_a_check_makes_no_read_for_it_and_is_shown_as_not_analysed(self):
        azure = Azure()
        h = Harness(FakeFoundry(answer(finding(handles=["r1"], basis="other", proposal="delete"))), FakeToolbox([resource(1, cost_usd_30d=70.0)], {"r1": ABSENT}), with_store=True)
        h.arm = h.s.arm = azure
        h.go()
        (case,) = h.store.cases_recent()
        self.assertEqual((azure.read, "impact" in case.facts), ([], False))
        (plan,) = h.store.plans_open()
        self.assertEqual(brief.build_brief(case, plan, now=WEB_NOW, may_answer=True).impact.line, UNANALYSED)

    def test_a_run_checks_no_more_than_the_most_and_reads_through_one_reader_whose_notes_go_to_the_run(self):
        azure = Azure(RUN_PE)
        azure.fail["traffic"] = 503
        h = Harness(toolbox=FakeToolbox(), with_store=True)
        h.arm = h.s.arm = azure
        out = investigate.Investigation()
        lead = SimpleNamespace(resource_id=RUN_PE, resource_type=ENDPOINTS)
        with mock.patch.object(investigate, "MAX_IMPACTS", 2), LogCapture() as capture:
            found = [investigate._impact_of(h.s, out, lead) for _ in range(3)]
        self.assertEqual([item is not None for item in found], [True, True, False])
        self.assertEqual((found[0]["complete"], out.impacts, out.impact_reader.notes), (False, 2, []))
        self.assertIn("impact: its traffic could not be read (GET management.azure.com: 503 not now)", [event["note"] for event in capture.events() if event["type"] == "run.note"])

    def test_a_deletion_of_a_resource_of_the_network_that_nobody_checked_the_impact_of_is_held_back_and_counted(self):
        ip = resource(1, resource_id=f"{RG}/rg-app/providers/Microsoft.Network/publicIPAddresses/ip-demo", resource_type="microsoft.network/publicipaddresses", name="ip-demo", cost_usd_30d=70.0)
        h = Harness(FakeFoundry(answer(finding(handles=["r1"], basis="other", proposal="delete"))), FakeToolbox([ip], {"r1": metrics(MetricA=0)}), with_store=True)
        h.go()
        (case,) = h.store.cases_recent()
        self.assertEqual((case.status, case.recommendation, case.owner["lookedUp"], brief.held_reason(case, NOW)), ("proposed", "delete", True, "impact"))
        self.assertEqual((h.result.held_back, h.store.plans_open()), ({"impact": 1}, []))
        (held,) = h.of("case.held")
        self.assertEqual((held["reason"], IMPACT_NOT_CHECKED), ("held back: impact not checked", "held back: impact not checked"))

    def test_a_deletion_of_a_resource_that_is_not_of_the_network_stays_a_request_with_the_line_that_the_impact_was_not_analysed(self):
        disk = resource(1, resource_id=f"{RG}/rg-app/providers/Microsoft.Compute/disks/disk-demo", resource_type="microsoft.compute/disks", name="disk-demo", cost_usd_30d=70.0)
        h = Harness(FakeFoundry(answer(finding(handles=["r1"], basis="other", proposal="delete"))), FakeToolbox([disk], {"r1": metrics(MetricA=0)}), with_store=True)
        h.go()
        (case,) = h.store.cases_recent()
        (plan,) = h.store.plans_open()
        shown = brief.build_brief(case, plan, now=WEB_NOW, may_answer=True)
        self.assertEqual((case.recommendation, shown.headline.startswith("Consider deleting"), shown.impact.line, h.result.held_back), ("delete", True, UNANALYSED, {}))

    def test_the_rule_of_the_hold_in_every_combination(self):
        zero = {"basis": "no-usage", "proposal": "delete", "metrics": {"M": 0}, "metricDaysWithData": {"M": 28}}
        complete = {"verdict": "safe", "complete": True, "reasons": ["x"]}
        owner = {"lookedUp": True, "automatedAt": ""}
        ip = "microsoft.network/publicipaddresses"
        for label, kind, facts, held in (("no digest", ip, zero, "impact"), ("a complete digest", ip, {**zero, "impact": complete}, ""), ("an incomplete digest", ip, {**zero, "impact": {**complete, "complete": False}}, "impact"),
                                         ("a digest with no verdict", ip, {**zero, "impact": {"complete": True}}, "impact"), ("a kind that is not of the network", "microsoft.compute/disks", zero, ""),
                                         ("a kind that others share (it asks for a look, never for a deletion)", ENDPOINTS, zero, ""), ("no measured zero (it asks for a look)", ip, {"basis": "other", "proposal": "delete"}, "")):
            with self.subTest(case=label):
                case = held_case(detector="investigation", resource_id=f"{RG}/rg-platform/providers/Microsoft.Network/publicIPAddresses/ip-x", resource_name="ip-x", resource_group="rg-platform",
                                 resource_type=kind, recommendation="delete", facts=facts, owner=owner)
                self.assertEqual(brief.held_reason(case, NOW), held)
        self.assertTrue(brief.needs_impact("Microsoft.Network/loadBalancers") and brief.needs_impact(ENDPOINTS) and brief.needs_impact("microsoft.apimanagement/service"))
        self.assertFalse(brief.needs_impact("microsoft.compute/disks") or brief.needs_impact(None) or brief.needs_impact(5))


class NoAIIsGivenTheDigest(unittest.TestCase):
    """The digest is made after both AIs have judged, and nothing that a model is given or a replay is made of is made from the facts of a case (AGENTS.md rule 30: no AI makes, sees or argues it)."""

    def test_the_inputs_of_the_two_agents_hold_none_of_it_and_neither_do_the_other_ways_in(self):
        h = watch_endpoint(Azure(RUN_PE))
        (case,) = h.store.cases_recent()
        found = case.facts["impact"]
        said = [text for text in (*found["reasons"], *found["removal"], *found["unchecked"], found["undo"], *(cell for row in found["rows"] for cell in row)) if len(text) > 25]
        self.assertGreater(len(said), 10)
        sent = h.foundry.inputs()
        self.assertEqual(len(sent), 2, "the Investigator and the Skeptic")
        for text in said:
            self.assertEqual([payload for payload in sent if text in payload], [], text)
        # a later run: the rows of the Skeptic are made from the tools, never from the facts of a lead or of a case, even when those hold the digest
        toolbox = FakeToolbox([resource(1, resource_id=RUN_PE, resource_type=ENDPOINTS, name="pe-apim-demo")], {"r1": ABSENT})
        held = investigate._lead(toolbox.handles["r1"], dict(case.facts), 70.0, None)
        text, _ = investigate._skeptic_input([investigate.Finding(number=1, basis="other", proposal="delete", items=[investigate.Item("r1", held, {"MetricA": 0}, shown=True)])], toolbox)
        self.assertEqual(([item for item in said if item in text], '"impact"' in text), ([], False))
        # the typed case of the older detectors refuses a text that is no word of its vocabulary, so a digest in the facts of a lead stops before any prompt is made
        with self.assertRaises(evidence.EvidenceError):
            evidence.case_dto(1, detector_lead(facts={"impact": found}), SAFE_GUARDS)
        # what the learning keeps and replays is buckets of typed values and the open questions that the Investigator may recall carry no text of a case
        signals = learning.signals_of(case)
        self.assertTrue(set(signals) <= set(learning.SIGNAL_KEYS) and not [item for item in said if item in str(signals)])
        self.assertEqual([field.name for field in dataclasses.fields(learning.OpenQuestion)], ["resource_id", "resource_type", "runs_seen", "days_open", "confidence", "request"])


class AnOpenRequestToDeleteAResourceWhoseImpactNobodyCheckedIsTakenBack(unittest.TestCase):
    def test_it_is_taken_back_at_the_next_watch_with_the_reason_in_plain_words_and_a_complete_check_keeps_it(self):
        clock = Moving()
        extras = loop_for(clock)
        zero = {"basis": "no-usage", "proposal": "delete", "metrics": {"M": 0}, "metricDaysWithData": {"M": 28}}
        complete = {"verdict": "safe", "complete": True, "reasons": ["x"]}
        made = {}
        for name, facts in (("ip-old", zero), ("ip-checked", {**zero, "impact": complete})):
            case = held_case(case_id=f"k{name}", plan_id=f"p{name}", detector="investigation", resource_id=f"{RG}/rg-platform/providers/Microsoft.Network/publicIPAddresses/{name}", resource_name=name,
                             resource_type="microsoft.network/publicipaddresses", resource_group="rg-platform", subscription_id=SUBSCRIPTION, status="proposed", recommendation="delete",
                             saving_usd_month=7.2, facts=facts, owner={"lookedUp": True, "automatedAt": ""})
            plan = request_for(case, expires_at="2026-11-07T09:00:00Z", title=f"Consider deleting the public IP address {name} in group rg-platform", saving_usd_month=7.2)
            extras.store.case_put(case)
            extras.store.plan_put(plan)
            made[name] = (case, plan)
        summary, events, _ = run_watch(__import__("support").FakeEstate(), extras, clock)
        old_case, old_plan = made["ip-old"]
        after, kept = extras.store.plan_get(old_plan.plan_id), extras.store.case_get(old_case.case_id)
        self.assertEqual((after.state, after.preconditions["takenBack"], summary.held), ("expired", "impact", 1))
        (held,) = [e for e in events if e["type"] == "case.held"]
        self.assertEqual((held["caseId"], held["reason"]), (old_case.case_id, IMPACT_NOT_CHECKED))
        shown = brief.build_brief(kept, after, now=WEB_NOW)
        self.assertEqual(shown.outcome.lines, ("Meternaut took this request back: nobody checked what depends on the resource.", "Nothing was changed in Azure."))
        new_case, new_plan = made["ip-checked"]
        self.assertEqual(extras.store.plan_get(new_plan.plan_id).state, "open", "a request whose impact was checked to the end stays")


if __name__ == "__main__":
    unittest.main()
