"""The family `scale-vpn-gateway`: lower the scale units of a point-to-site gateway by one step when nobody has been connected for days (cases/families/gateway.py). Every name, id and number is
invented.

No gateway is planted and none may be (AGENTS.md rule 15 (g)): this module holds one on the planted list for its tests, as if a planting existed, and test_families_gates says that the real
list has none, so that the family does nothing in any estate. What every family has to do (the scope, the planted tag, a lock, a person's do-not-touch note, the plan that is the plan that
runs) is tested over the registry in test_families_gates, test_families_digest and test_families_briefs, which hold a sample of this family too. Here is what is its own: the table of sizes,
the plan, the re-check of the connection count, the PUT and its body, and what follows a change that Azure takes minutes to make.
"""
import copy
import datetime as dt
import json
import unittest
from urllib.parse import parse_qs, urlsplit

import familysupport as fs
from familysupport import World
from test_families_gates import setUpModule, tearDownModule  # noqa: F401  (the module holds a gateway on the planted list for its tests)

from support import APP_ROOT  # noqa: F401

from cases.families import calls, capacity, registry
from cases.families.azure import Azure
from cases.families.base import Env, Stop
from cases.families.gateway import READ_ONLY, ScaleVpnGateway, _highest, nobody, put_body
from cases.runner import RUNNING_GIVE_UP_MINUTES, RUNNING_TEXT, UNKNOWN_END

FAMILY = registry.get("scale-vpn-gateway")
TYPE = "microsoft.network/p2svpngateways"
KEY = fs.rid("p2s").lower()
METRICS = KEY + "/providers/microsoft.insights/metrics"


def made(units: int = 12, cost: float = 60.0, **more):
    """A world with one gateway and the plan that it gets: (the world, the gateway, the plan)."""
    world = World()
    resource = world.arm.add(fs.p2s(units=units, **more))
    return world, resource, world.plan(resource, "p2s", "change", cost)


def approved(**more):
    world, resource, plan = made(**more)
    assert plan is not None
    world.approve(plan)
    return world, resource, plan


def gateway_reads(world) -> list[str]:
    return [url for method, url in world.arm.calls if method == "GET" and "/p2svpngateways/planted-p2s-1?" in url.lower()]


def metric_reads(world) -> list[str]:
    return [url for method, url in world.arm.calls if method == "GET" and url.lower().split("?")[0].endswith("/providers/microsoft.insights/metrics")]


def the_put(world) -> tuple[str, dict]:
    (found,) = [(url, world.arm.bodies[index]) for index, (method, url) in enumerate(world.arm.calls) if method == "PUT"]
    return found


class TheSizesAndWhatEachCarries(unittest.TestCase):
    def test_they_are_the_table_of_learn(self):
        self.assertEqual(capacity.SIZES, (*range(1, 21), 40, 60, 80, 100, 120, 140, 160, 180, 200))
        for units, limit in ((1, 500), (3, 500), (4, 1000), (6, 1000), (7, 5000), (10, 5000), (11, 10000), (20, 10000), (40, 20000), (100, 50000), (200, 100000)):
            self.assertEqual(capacity.connections_of(units), limit, units)
        self.assertEqual({size for size in capacity.SIZES if capacity.connections_of(size) is None}, set())
        self.assertEqual((capacity.mbps_of(1), capacity.mbps_of(10), capacity.mbps_of(200)), (500, 5000, 100000), "one scale unit is 500 Mbps")
        self.assertIsNone(capacity.connections_of(25), "a size that the table does not list has no known limit")

    def test_a_step_down_is_the_next_listed_size_and_never_below_one(self):
        self.assertIsNone(capacity.one_step_down(1))
        for units, wanted in ((2, 1), (12, 11), (20, 19), (40, 20), (60, 40), (200, 180), (21, 20), (25, 20), (39, 20)):
            self.assertEqual(capacity.one_step_down(units), wanted, units)

    def test_the_smallest_size_for_the_most_connections_seen(self):
        for peak, wanted in ((0, 1), (1, 1), (500, 1), (501, 4), (1000, 4), (1001, 7), (5000, 7), (5001, 11), (10000, 11), (10001, 40), (100000, 200), (100001, None)):
            self.assertEqual(capacity.smallest_for(peak), wanted, peak)

    def test_only_a_whole_number_from_one_to_two_hundred_is_a_number_of_units(self):
        self.assertEqual([capacity.whole(value) for value in (1, 12, 200)], [1, 12, 200])
        for value in (True, False, 0, -1, 201, 12.0, 12.5, "12", None, [12]):
            self.assertIsNone(capacity.whole(value), repr(value))


class TheFamilyIsInTheRegistry(unittest.TestCase):
    def test_it_matches_the_one_type_and_leads_from_a_recommendation_to_change_only(self):
        self.assertIsInstance(FAMILY, ScaleVpnGateway)
        self.assertEqual(FAMILY.kinds, (calls.P2S_GATEWAY,))
        self.assertEqual([family.name for family in registry.candidates("investigation", TYPE, "change")], ["scale-vpn-gateway"])
        for recommendation in ("delete", "keep", "investigate", None):
            self.assertEqual(registry.candidates("investigation", TYPE, recommendation), [], recommendation)
        self.assertEqual(registry.candidates("orphan-managed-disk", TYPE, "change"), [], "no older detector leads to it: it is no detector's waste")
        self.assertNotIn(FAMILY.name, [family.name for family in registry.candidates("investigation", "microsoft.compute/virtualmachines", "change")])
        self.assertFalse(FAMILY.deletes)

    def test_its_one_call_is_the_put_of_the_gateway(self):
        self.assertIs(FAMILY.call(), calls.write_for("PUT", calls.P2S_GATEWAY))
        self.assertEqual((calls.P2S_GATEWAY.api, calls.P2S_GATEWAY.collection), ("2026-01-01", "p2svpnGateways"))


class ThePlan(unittest.TestCase):
    def test_a_gateway_that_nobody_used_gets_the_plan_of_one_step_down_written_by_code(self):
        world, resource, plan = made()
        self.assertEqual((plan.family, plan.state), ("scale-vpn-gateway", "open"))
        self.assertEqual(plan.target, {"vpnGatewayScaleUnit": 11, "fromScaleUnit": 12})
        self.assertEqual(plan.title, f"Scale a point-to-site gateway down to 11 scale units in resource group {fs.GROUP}")
        self.assertEqual(plan.saving_usd_month, 5.0, "the cost of the last 30 days times the share of the units that is taken away: 60 times one twelfth")
        self.assertEqual(plan.preconditions, {"family": "scale-vpn-gateway", "resourceType": TYPE, "tag": "meternaut-planted", "resourceGroup": fs.GROUP, "quietDays": 7})
        self.assertIn("from 12 to 11", plan.what_changes)
        self.assertIn("sends the gateway back to Azure as it was read, with that one number changed", plan.what_changes)
        self.assertIn("With 11 it carries up to 10,000 connections at one time and 5,500 Mbps, down from 10,000 and 6,000.", plan.could_go_wrong)
        self.assertIn("plan for downtime", plan.could_go_wrong)
        self.assertIn("up to 30 minutes", plan.could_go_wrong)
        self.assertIn("az network p2s-vpn-gateway update --scale-unit 12", plan.undo)
        self.assertIn("the gateway has 12 scale units", plan.evidence_level)
        self.assertIn("was 0", plan.evidence_level)
        self.assertEqual(world.arm.writes(), [], "making a plan changes nothing")
        self.assertEqual((len(gateway_reads(world)), len(metric_reads(world))), (1, 1), "the gateway and its connection count are read with the reader's token")
        self.assertEqual(set(world.reader_tokens), {"https://management.azure.com/"})

    def test_every_size_but_the_smallest_has_a_plan_that_is_one_step_of_the_table(self):
        for units in (2, 5, 11, 20, 40, 60, 200):
            with self.subTest(units):
                _, _, plan = made(units)
                self.assertEqual(plan.target, {"vpnGatewayScaleUnit": capacity.one_step_down(units), "fromScaleUnit": units})
        world, resource, plan = made(1)
        self.assertIsNone(plan, "never below 1 unit")
        self.assertEqual(world.store.plans_open(), [])

    def test_a_size_that_the_table_does_not_list_steps_down_to_the_largest_size_below_it_and_names_no_limit(self):
        _, _, plan = made(25)
        self.assertEqual(plan.target, {"vpnGatewayScaleUnit": 20, "fromScaleUnit": 25})
        self.assertNotIn("it carries up to", plan.could_go_wrong, "the limit of a size that is not listed is not known")

    def test_a_gateway_that_is_not_ready_or_shows_no_whole_number_gets_no_plan(self):
        for state in ("Updating", "Failed", None):
            with self.subTest(state):
                world = World()
                gateway = fs.p2s(provisioning=state or "Succeeded")
                if state is None:
                    del gateway["properties"]["provisioningState"]
                world.arm.add(gateway)
                self.assertIsNone(world.plan(gateway, "p2s", "change", 60.0))
        for units in ("12", 0, 12.5, None, True):
            with self.subTest(units=units):
                world = World()
                gateway = fs.p2s()
                gateway["properties"]["vpnGatewayScaleUnit"] = units
                world.arm.add(gateway)
                self.assertIsNone(world.plan(gateway, "p2s", "change", 60.0))

    def test_a_gateway_that_somebody_connected_to_gets_no_plan_and_a_count_with_too_few_days_is_no_count_of_nothing(self):
        for label, series, planned in (("a connection", [0, 0, 0, 3, 0, 0, 0], False), ("one at the end", [0, 0, 0, 0, 0, 0, 1], False), ("five days", [0, 0, None, None, 0, 0, 0], True),
                                       ("four days", [0, 0, None, None, None, 0, 0], False), ("no day", [None] * 7, False)):
            with self.subTest(label):
                world = World()
                gateway = world.arm.add(fs.p2s())
                world.arm.connections[KEY] = series
                self.assertEqual(world.plan(gateway, "p2s", "change", 60.0) is not None, planned)
                self.assertEqual(world.arm.writes(), [])

    def test_a_count_that_cannot_be_read_is_no_reason_to_plan(self):
        for label, change in (("refused", lambda arm: setattr(arm, "metrics_status", 403)), ("failed", lambda arm: setattr(arm, "metrics_status", 500)),
                              ("an answer of another shape", lambda arm: setattr(arm, "metrics_body", b'{"value":[]}')),
                              ("an error in the answer", lambda arm: setattr(arm, "metrics_body", b'{"value":[{"errorCode":"BadRequest","timeseries":[]}]}')),
                              ("no series", lambda arm: setattr(arm, "metrics_body", b'{"value":[{"errorCode":"Success"}]}'))):
            with self.subTest(label):
                world = World()
                gateway = world.arm.add(fs.p2s())
                change(world.arm)
                self.assertIsNone(world.plan(gateway, "p2s", "change", 60.0))
                self.assertEqual(world.store.plans_open(), [])

    def test_a_gateway_without_a_cost_has_a_plan_and_no_figure(self):
        world = World()
        gateway = world.arm.add(fs.p2s())
        plan = world.plan(gateway, "p2s", "change", None)
        self.assertIsNotNone(plan)
        self.assertIsNone(plan.saving_usd_month)


class TheCountIsAskedFor(unittest.TestCase):
    NOW = dt.datetime(2026, 11, 8, 9, 0, tzinfo=dt.timezone.utc)

    def test_the_last_seven_closed_days_of_utc_in_daily_buckets_of_the_highest_value(self):
        world, _, _ = made()
        (url,) = metric_reads(world)
        query = parse_qs(urlsplit(url).query)
        self.assertEqual({key: value[0] for key, value in query.items()},
                         {"api-version": "2023-10-01", "metricnames": "P2SConnectionCount", "timespan": "2026-11-01T00:00:00Z/2026-11-08T00:00:00Z", "interval": "P1D", "aggregation": "Maximum"})

    def test_a_clock_that_has_a_zone_gives_the_days_of_utc(self):
        world = World()
        world.clock.now = dt.datetime(2026, 11, 8, 0, 30, tzinfo=dt.timezone(dt.timedelta(hours=2)))  # 22:30 UTC the day before
        gateway = world.arm.add(fs.p2s())
        self.assertIsNotNone(world.plan(gateway, "p2s", "change", 60.0))
        (url,) = metric_reads(world)
        self.assertEqual(parse_qs(urlsplit(url).query)["timespan"], ["2026-10-31T00:00:00Z/2026-11-07T00:00:00Z"])

    def bucket(self, day, value):
        return {"timeStamp": f"2026-11-{day:02d}T00:00:00Z", **({} if value is None else {"maximum": value})}

    def read(self, *data):
        return _highest({"value": [{"errorCode": "Success", "timeseries": [{"data": list(data)}]}]}, self.NOW)

    def test_a_bucket_is_a_value_only_when_it_is_a_day_of_the_span_with_a_number_that_is_not_below_zero(self):
        self.assertEqual(self.read(*(self.bucket(day, 0.0) for day in range(1, 8))), (7, 0.0))
        self.assertEqual(self.read(self.bucket(1, 0), self.bucket(2, 4), self.bucket(3, None), self.bucket(4, 2.5)), (3, 4.0))
        odd = [self.bucket(8, 9), self.bucket(31, 9), {"timeStamp": "2026-11-03T05:00:00Z", "maximum": 9}, self.bucket(2, -1), self.bucket(3, True), {"timeStamp": "2026-11-04T00:00:00Z", "maximum": "7"},
               {"timeStamp": "2026-11-05T00:00:00Z", "maximum": float("nan")}, "text", {"maximum": 9}]
        self.assertEqual(self.read(*odd), (0, 0.0), "a day outside the span, a time that is not a day, a negative number, a flag, a text and a number that is not one are gaps and never a value")

    def test_a_day_that_has_two_series_takes_the_higher_one(self):
        data = {"value": [{"errorCode": "Success", "timeseries": [{"data": [self.bucket(1, 0), self.bucket(2, 1)]}, {"data": [self.bucket(1, 5)]}]}]}
        self.assertEqual(_highest(data, self.NOW), (2, 5.0))

    def test_what_it_says_about_a_reading(self):
        self.assertIsNone(nobody(7, 0.0))
        self.assertIsNone(nobody(5, 0.0))
        self.assertIn("4 of the last 7 days", nobody(4, 0.0))
        self.assertIn("at least 5 days", nobody(0, 0.0))
        self.assertEqual(nobody(7, 12.0), "users were connected to the gateway in the last 7 days (up to 12 at one time)")


class TheRecheckRightBeforeTheChange(unittest.TestCase):
    def stopped(self, world, plan, text, kind="stopped"):
        written = len(world.arm.writes())
        done = world.run(plan)
        self.assertEqual((done.kind, done.action.state), (kind, "failed"), done.action.result)
        self.assertIn(text, done.action.result)
        self.assertEqual(len(world.arm.writes()), written, "no write was made")
        self.assertEqual(world.state(plan), ("failed", "failed", "failed"))

    def test_a_gateway_with_other_scale_units_than_the_plan_was_made_for_stops_the_change(self):
        for units in (13, 10, 8):
            with self.subTest(units):
                world, resource, plan = approved()
                resource["properties"]["vpnGatewayScaleUnit"] = units
                self.stopped(world, plan, "does not have the scale units that the plan was made for any more")

    def test_a_gateway_that_somebody_else_is_changing_stops_the_change(self):
        for state in ("Updating", "Failed", "Deleting"):
            with self.subTest(state):
                world, resource, plan = approved()
                resource["properties"]["provisioningState"] = state
                self.stopped(world, plan, f"its provisioning state is {state.lower()}")

    def test_users_who_connected_after_the_plan_stop_the_change_with_the_number(self):
        world, resource, plan = approved()
        world.arm.connections[KEY] = [0, 0, 0, 0, 2, 0, 0]
        self.stopped(world, plan, "users were connected to the gateway in the last 7 days (up to 2 at one time)")
        self.assertEqual((len(gateway_reads(world)), len(metric_reads(world))), (2, 2), "the plan read them, and the re-check read them again")

    def test_a_count_with_too_few_days_now_stops_the_change(self):
        world, resource, plan = approved()
        world.arm.connections[KEY] = [0, 0, None, None, None, 0, 0]
        self.stopped(world, plan, "for 4 of the last 7 days")

    def test_a_count_that_cannot_be_read_now_stops_the_change_and_a_refusal_says_that_the_account_has_no_right(self):
        world, resource, plan = approved()
        world.arm.metrics_status = 500
        self.stopped(world, plan, "the connection count of the gateway could not be read (500)")
        world, resource, plan = approved()
        world.arm.metrics_status = 403
        self.stopped(world, plan, "your account has no right to do this here", kind="azure_refused")

    def test_a_gateway_that_is_the_aim_already_is_not_written_and_claims_no_saving(self):
        world, resource, plan = approved()
        resource["properties"]["vpnGatewayScaleUnit"] = 11
        done = world.run(plan)
        self.assertEqual((done.kind, done.action.state, done.action.no_change), ("unchanged", "done", True))
        self.assertIn("The gateway already had 11 scale units when Meternaut looked. Nothing to change.", done.action.result)
        self.assertEqual(world.arm.writes(), [])

    def test_a_plan_that_is_not_one_step_of_the_table_is_refused_before_it_is_used(self):
        for target in ({"vpnGatewayScaleUnit": 10, "fromScaleUnit": 12}, {"vpnGatewayScaleUnit": 12, "fromScaleUnit": 12}, {"vpnGatewayScaleUnit": "11", "fromScaleUnit": 12},
                       {"vpnGatewayScaleUnit": 0, "fromScaleUnit": 1}, {"fromScaleUnit": 12}, {}):
            with self.subTest(target=target):
                world = World()
                resource = world.arm.add(fs.p2s())
                plan, _ = world.approved(resource, "p2s", "change", 60.0, mutate={"target": target})
                done = world.run(plan)
                self.assertEqual((done.kind, done.action.state), ("stopped", "failed"), done.action.result)
                self.assertIn("a change of scale units that Meternaut does not make", done.action.result)
                self.assertEqual(world.arm.writes(), [])


class TheCallAndItsBody(unittest.TestCase):
    def test_the_put_states_the_gateway_as_it_was_read_with_one_number_changed_and_nothing_that_azure_fills_in(self):
        world, resource, plan = approved()
        before = copy.deepcopy(resource)
        done = world.run(plan)
        self.assertEqual((done.kind, done.action.state), ("ran", "done"), done.action.result)
        url, body = the_put(world)
        self.assertEqual(url, f"https://management.azure.com{fs.rid('p2s')}?api-version=2026-01-01")
        wanted = copy.deepcopy(before)
        wanted["properties"]["vpnGatewayScaleUnit"] = 11
        for name in ("etag", "id", "name", "type"):
            del wanted[name]
        for name in ("provisioningState", "vpnClientConnectionHealth"):
            del wanted["properties"][name]
        configuration = wanted["properties"]["p2SConnectionConfigurations"][0]
        del configuration["etag"]
        del configuration["properties"]["provisioningState"], configuration["properties"]["previousConfigurationPolicyGroupAssociations"]
        self.assertEqual(body, wanted)

    def test_nothing_that_the_gateway_had_is_lost_by_it(self):
        world, resource, plan = approved()
        original = copy.deepcopy(resource)
        world.run(plan)
        now = world.arm.get(fs.rid("p2s"))
        self.assertEqual(now["tags"], fs.PLANTED)
        self.assertEqual(now["location"], fs.REGION)
        for key in ("customDnsServers", "isRoutingPreferenceInternet", "virtualHub", "vpnServerConfiguration"):
            self.assertEqual(now["properties"][key], original["properties"][key], key)
        kept = now["properties"]["p2SConnectionConfigurations"][0]
        old = original["properties"]["p2SConnectionConfigurations"][0]
        self.assertEqual((kept["name"], kept["id"]), (old["name"], old["id"]))
        for key in ("enableInternetSecurity", "vpnClientAddressPool", "routingConfiguration"):
            self.assertEqual(kept["properties"][key], old["properties"][key], key)
        self.assertEqual(now["properties"]["vpnGatewayScaleUnit"], 11)

    def test_the_read_only_keys_are_left_out_at_every_depth_and_the_gateway_that_was_read_is_not_changed(self):
        gateway = fs.p2s()
        gateway["properties"]["extra"] = {"list": [{"etag": "x", "provisioningState": "Succeeded", "keep": 1}]}
        before = copy.deepcopy(gateway)
        body = put_body(gateway, 5)
        self.assertEqual(gateway, before)
        self.assertEqual(body["properties"]["extra"], {"list": [{"keep": 1}]})
        self.assertEqual(body["properties"]["vpnGatewayScaleUnit"], 5)
        self.assertTrue(READ_ONLY.isdisjoint(json.dumps(body).replace('"', " ").replace(":", " ").split()), "none of the keys that Azure fills in is sent")

    def test_a_gateway_that_shows_no_place_cannot_be_put(self):
        gateway = fs.p2s()
        for place in (None, "", "  ", 7):
            gateway["location"] = place
            with self.assertRaises(Stop):
                put_body(gateway, 5)
        del gateway["location"]
        with self.assertRaises(Stop):
            put_body(gateway, 5)

    def test_the_call_is_made_once_with_the_person_s_token_and_the_correlation_id_and_is_the_one_write(self):
        world, resource, plan = approved()
        world.run(plan)
        writes = world.arm.writes()
        self.assertEqual([method for method, _ in writes], ["PUT"])
        index = [method for method, _ in world.arm.calls].index("PUT")
        self.assertEqual(world.arm.headers[index]["Authorization"], "Bearer person-token")
        self.assertEqual(world.arm.headers[index]["x-ms-correlation-request-id"], world.action(plan).correlation_id)
        self.assertEqual(set(world.person_tokens), {"https://management.azure.com/"})

    def test_the_gateway_is_read_once_more_right_before_the_put_and_a_change_in_between_stops_it(self):
        world, resource, plan = approved()
        env = Env(Azure(world.s.client, lambda resource_: "t"), world.settings.gates, lambda: set(), world.clock)
        located = FAMILY.locate(plan.resource_id, world.settings.gates)
        resource["properties"]["vpnGatewayScaleUnit"] = 10
        with self.assertRaises(Stop) as stop:
            FAMILY.write(env, plan, located)
        self.assertIn("changed after it was checked", str(stop.exception))
        resource["properties"]["vpnGatewayScaleUnit"] = 12
        resource["properties"]["provisioningState"] = "Updating"
        with self.assertRaises(Stop):
            FAMILY.write(env, plan, located)
        world.arm.resources.pop(KEY)
        with self.assertRaises(Stop):
            FAMILY.write(env, plan, located)
        self.assertEqual(world.arm.writes(), [])


class WhenAzureTakesMinutes(unittest.TestCase):
    def test_a_201_with_an_operation_to_follow_ends_done_and_the_operation_is_looked_at(self):
        world, resource, plan = approved()
        done = world.run(plan)
        self.assertEqual((done.kind, done.action.state), ("ran", "done"), done.action.result)
        self.assertEqual(done.action.result, "Azure shows the gateway with 11 scale units, and its last operation worked.")
        self.assertEqual(done.action.verification["scaleUnits"], 11)
        self.assertGreaterEqual(world.arm.operation_looks, 1)
        self.assertEqual(world.state(plan), ("consumed", "done", "done"))

    def test_a_gateway_that_azure_is_still_updating_is_running_and_the_timer_settles_it_with_the_reader_and_no_write(self):
        world, resource, plan = approved()
        world.arm.units_never = True
        world.arm.operation_polls = ["InProgress"]
        done = world.run(plan)
        self.assertEqual((done.kind, done.action.state), ("running", "running"), done.action.result)
        self.assertEqual(done.action.result, RUNNING_TEXT)
        self.assertEqual(world.state(plan), ("consumed", "running", "running"))
        writes = len(world.arm.writes())
        world.arm.effects[KEY] = fs.Effect(0, lambda found: fs.Arm.set_provisioning(found, "Succeeded"))
        world.clock.advance(minutes=3)
        result = world.tick()
        self.assertEqual([action.state for action in result.finished], ["done"])
        self.assertTrue(world.action(plan).result.endswith("(confirmed by the later check)."), world.action(plan).result)
        self.assertEqual(len(world.arm.writes()), writes, "the timer makes no write")
        self.assertEqual(world.state(plan), ("consumed", "done", "done"))

    def test_an_operation_that_azure_says_failed_is_a_failure_and_a_gateway_that_shows_failed_is_one_too(self):
        world, resource, plan = approved()
        world.arm.operation_polls = ["Failed"]
        done = world.run(plan)
        self.assertEqual((done.kind, done.action.state), ("failed", "failed"), done.action.result)
        self.assertIn("Azure did not finish the change", done.action.result)
        self.assertEqual(len(world.arm.writes()), 1)
        world, resource, plan = approved()
        world.arm.units_fail = True
        world.arm.operation_polls = ["InProgress"]
        done = world.run(plan)
        self.assertEqual((done.kind, done.action.state), ("failed", "failed"), done.action.result)
        self.assertIn("the last operation on the gateway did not work", done.action.result)
        self.assertIn("may keep running at the old size", done.action.result)
        self.assertEqual(len(world.arm.writes()), 1, "a write that failed is never made again")

    def test_an_end_that_is_not_shown_in_an_hour_is_unknown_and_makes_no_second_write(self):
        world, resource, plan = approved()
        world.arm.units_never = True
        world.arm.operation_polls = ["InProgress"]
        world.run(plan)
        writes = len(world.arm.writes())
        world.clock.advance(minutes=RUNNING_GIVE_UP_MINUTES + 1)
        self.assertEqual([action.state for action in world.tick().finished], ["unknown"])
        self.assertEqual(world.action(plan).result, UNKNOWN_END)
        self.assertEqual(len(world.arm.writes()), writes)

    def test_azure_that_refuses_the_put_is_refused_and_nothing_is_tried_again(self):
        world, resource, plan = approved()
        world.arm.write_answers = [(403, {}, b'{"error":{"code":"AuthorizationFailed","message":"no right"}}')]
        done = world.run(plan)
        self.assertEqual((done.kind, done.action.state), ("azure_refused", "failed"), done.action.result)
        self.assertIn("your account has no right to do this here", done.action.result)
        self.assertEqual(len(world.arm.writes()), 1)


class WhatIsCheckedAfterwards(unittest.TestCase):
    def verdict(self, world, plan):
        env = Env(Azure(world.t.client, lambda resource: "reader"), world.settings.gates, lambda: set(), world.clock)
        return FAMILY.verify(env, plan)

    def test_the_gateway_is_done_pending_failed_or_not_known(self):
        world, resource, plan = approved()
        self.assertEqual(self.verdict(world, plan).state, "pending", "the gateway still has the old units")
        resource["properties"]["vpnGatewayScaleUnit"] = 11
        self.assertEqual(self.verdict(world, plan).state, "done")
        resource["properties"]["provisioningState"] = "Updating"
        self.assertEqual(self.verdict(world, plan).state, "pending", "the units that were asked for, and the operation not finished")
        resource["properties"]["provisioningState"] = "Failed"
        failed = self.verdict(world, plan)
        self.assertEqual(failed.state, "failed", "a failed update may still show the units that were asked for")
        self.assertIn("may keep running at the old size", failed.text)
        resource["properties"]["provisioningState"] = "Canceled"
        self.assertEqual(self.verdict(world, plan).state, "failed")
        world.arm.read_status = 500
        self.assertEqual(self.verdict(world, plan).state, "unknown")
        world.arm.read_status = 200
        world.arm.resources.pop(KEY)
        self.assertEqual(self.verdict(world, plan).state, "unknown")

    def test_the_cost_lines_confirm_a_lower_figure_and_never_no_cost(self):
        confirmed, text, saved = FAMILY.cost_check(60.0, 3.0, 2)
        self.assertEqual((confirmed, saved), (True, 15.0), "1.50 a day after against 2.00 a day before")
        self.assertIn("lower", text)
        self.assertEqual(FAMILY.cost_check(60.0, 27.5, 2)[0], False, "13.75 a day is not lower than 2.00")
        self.assertEqual(FAMILY.cost_check(60.0, 0, 2)[0], False)
        self.assertEqual(FAMILY.cost_check(None, 10.0, 2)[0], False)
        self.assertFalse(FAMILY.cost_ends, "a gateway with fewer units still bills: no cost line is not the aim")


if __name__ == "__main__":
    unittest.main()
