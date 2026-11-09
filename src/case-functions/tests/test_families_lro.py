"""Long-running operations: a stop, a resize and a change of a disk's tier are carried out by Azure later.

The change is followed for a short time with the approver's token, inside the request of the sign-in. When it is not finished then, the action is `running` (not failed), the approver is
told so plainly, and the end is read later by the timer with the app's own reader, by looking at the resource. An unknown end is `unknown`, never a second write.
"""
import unittest
from dataclasses import replace

import familysupport as fs
from familysupport import OID, SUB, World

from support import APP_ROOT  # noqa: F401

from cases.families import lro
from cases.families.azure import Azure
from cases.families.calls import read_patterns
from cases.http import Client, HttpError, Response
from cases.runner import POLL_ATTEMPTS, RUNNING_GIVE_UP_MINUTES, RUNNING_TEXT, UNKNOWN_END

OPERATION = fs.operation_url()


def answer(status=202, headers=None, body=b"{}") -> Response:
    return Response(status, headers or {}, body)


class WhatTheAnswerOfTheWriteSays(unittest.TestCase):
    def test_a_202_with_the_address_of_the_operation_is_asynchronous_and_the_address_is_followed(self):
        found = lro.initiated(answer(202, {"Azure-AsyncOperation": OPERATION, "Location": fs.operation_url("op-2"), "Retry-After": "4"}))
        self.assertEqual((found.status, found.url, found.via, found.wait, found.asynchronous, found.failed), (202, OPERATION, "Azure-AsyncOperation", 4.0, True, False))

    def test_azure_asyncoperation_wins_over_location_and_location_is_used_when_it_is_alone_the_names_compare_without_case(self):
        both = lro.initiated(answer(202, {"location": fs.operation_url("op-2"), "azure-asyncoperation": OPERATION}))
        self.assertEqual((both.url, both.via), (OPERATION, "Azure-AsyncOperation"))
        alone = lro.initiated(answer(202, {"LOCATION": fs.operation_url("op-2")}))
        self.assertEqual((alone.url, alone.via), (fs.operation_url("op-2"), "Location"))

    def test_a_202_without_an_address_is_asynchronous_and_has_nothing_to_follow(self):
        found = lro.initiated(answer(202))
        self.assertEqual((found.url, found.asynchronous), ("", True))

    def test_a_200_with_nothing_else_is_done_and_a_200_whose_body_is_not_finished_is_not(self):
        self.assertEqual((lro.initiated(answer(200)).asynchronous, lro.initiated(answer(200)).failed), (False, False))
        for state in ("Updating", "Creating", "InProgress"):
            with self.subTest(state):
                found = lro.initiated(answer(200, body=f'{{"properties":{{"provisioningState":"{state}"}}}}'.encode()))
                self.assertTrue(found.asynchronous)
        for state in ("Succeeded", "succeeded"):
            self.assertFalse(lro.initiated(answer(200, body=f'{{"properties":{{"provisioningState":"{state}"}}}}'.encode())).asynchronous)
        self.assertFalse(lro.initiated(answer(200, body=b'{"provisioningState":"Succeeded"}')).asynchronous, "the state can be at the top of the body too")

    def test_a_provisioning_state_of_failure_or_cancel_is_a_failure(self):
        for state in ("Failed", "Canceled", "Cancelled"):
            with self.subTest(state):
                found = lro.initiated(answer(200, body=f'{{"properties":{{"provisioningState":"{state}"}}}}'.encode()))
                self.assertTrue(found.failed)

    def test_an_address_that_is_not_on_azure_resource_manager_or_is_too_long_is_not_followed(self):
        for url in ("https://evil.example/subscriptions/x/operations/1", "http://management.azure.com/subscriptions/x", "//management.azure.com/x", "https://management.azure.com.evil.example/x",
                    "https://management.azure.com/" + "a" * 4096):
            with self.subTest(url=url[:50]):
                found = lro.initiated(answer(202, {"Azure-AsyncOperation": url, "Location": url}))
                self.assertEqual((found.url, found.via, found.asynchronous), ("", "", True))
        longest = "https://management.azure.com/" + "a" * (lro.MAX_URL - len("https://management.azure.com/"))
        self.assertEqual(lro.initiated(answer(202, {"Location": longest})).url, longest, "an address of 4 KB is accepted, as Learn asks of a client")

    def test_the_wait_that_azure_asks_for_is_read_only_when_it_is_a_number_and_kept_between_two_and_five_seconds(self):
        for value, wait in (("5", 5.0), ("0", 0.0), ("1.5", 1.5), ("abc", None), ("-3", None), ("86400", None), ("", None)):
            with self.subTest(value=value):
                self.assertEqual(lro.initiated(answer(202, {"Retry-After": value})).wait, wait)
        for asked, pause in ((None, 3.0), (0.0, 2.0), (1.0, 2.0), (4.0, 4.0), (30.0, 5.0)):
            with self.subTest(asked=asked):
                self.assertEqual(lro.pause(lro.Initiated(202, wait=asked)), pause)

    def test_a_body_that_is_not_json_says_nothing_and_does_not_break_anything(self):
        found = lro.initiated(answer(202, {"Location": OPERATION}, b"<html>"))
        self.assertEqual((found.provisioning, found.url), ("", OPERATION))

    def test_an_address_in_what_azure_says_is_never_shown(self):
        self.assertEqual(lro.forget("see https://management.azure.com/subscriptions/x/y?z=1 now"), "see (an address) now")


class ALookAtTheOperation(unittest.TestCase):
    def setUp(self):
        self.arm = fs.Arm()
        client = Client(read_patterns(fs.SCOPES) + (("GET", __import__("cases.families.calls", fromlist=["_operations"])._operations(fs.SCOPES[0])),), lambda text: text,
                        transport=self.arm.transport, sleep=lambda seconds: None, monotonic=lambda: 0.0)
        self.azure = Azure(client, lambda resource: "token")

    def look(self, via="Azure-AsyncOperation", url=OPERATION):
        return lro.check(self.azure, lro.Initiated(202, url, via))

    def test_each_status_of_azure_is_one_of_three_states(self):
        for status, state in (("Succeeded", "succeeded"), ("Failed", "failed"), ("Canceled", "failed"), ("InProgress", "running"), ("Accepted", "running"), ("Updating", "running")):
            with self.subTest(status):
                self.arm.operation_polls, self.arm.operation_looks = [status], 0
                self.assertEqual(self.look().state, state)

    def test_what_azure_says_of_a_failure_is_the_code_and_the_first_words_with_no_address(self):
        self.arm.operation_polls = ["Failed"]
        self.arm.operation_error = {"code": "AllocationFailed", "message": "no room: see https://management.azure.com/subscriptions/x for more " + "y" * 400}
        said = self.look()
        self.assertEqual(said.state, "failed")
        self.assertTrue(said.text.startswith("AllocationFailed: no room: see (an address) for more"))
        self.assertLessEqual(len(said.text), lro.MAX_TEXT + len("(an address)"))

    def test_a_status_that_the_person_may_not_read_or_cannot_be_found_is_not_a_failure_and_is_not_asked_again(self):
        for code in (401, 403, 404):
            with self.subTest(code):
                self.arm.operation_http_status = code
                found = self.look()
                self.assertEqual((found.state, found.readable), ("running", False))

    def test_a_status_that_failed_to_come_may_be_asked_again(self):
        self.arm.operation_http_status = 500
        found = self.look()
        self.assertEqual((found.state, found.readable), ("running", True))

    def test_an_address_that_the_list_of_calls_does_not_hold_is_not_called(self):
        other = f"https://management.azure.com/subscriptions/{fs.OTHER_SUB}/providers/Microsoft.Compute/locations/swedencentral/operations/op-1?api-version=2026-04-01"
        found = self.look(url=other)
        self.assertEqual((found.state, found.readable), ("running", False))
        self.assertEqual(self.arm.calls, [])

    def test_no_address_means_nothing_to_look_at(self):
        found = lro.check(self.azure, lro.Initiated(202))
        self.assertEqual((found.state, found.readable, self.arm.calls), ("running", False, []))

    def test_the_status_of_a_location_is_a_resource_or_a_202(self):
        fine = lro.Initiated(202, OPERATION, "Location")
        self.assertEqual(lro.check(self.azure, fine).state, "succeeded")  # the fake answers 200 with a body that has a status and no provisioning state


class FollowingAStop(unittest.TestCase):
    """The change that the people care about most: stop a machine. Everything below holds for a resize and for a change of tier in the same way (the next class)."""

    def setUp(self):
        self.world = World()
        self.arm = self.world.arm
        self.resource = self.arm.add(fs.vm())
        self.arm.sizes[self.resource["id"].lower()] = fs.D_SERIES
        self.plan, _ = self.world.approved(self.resource, "vm", "delete", 60.0)
        self.reads = len(self.arm.calls)
        self.reader_tokens_before = len(self.world.reader_tokens)

    def deallocates(self):
        return [url for url in self.arm.writes_of("POST") if "/deallocate" in url]

    def test_an_operation_that_ends_inside_the_time_is_done_and_the_resource_says_so(self):
        done = self.world.run(self.plan)
        self.assertEqual((done.kind, done.action.state), ("ran", "done"), done.action.result)
        self.assertEqual(done.action.verification["power"], "deallocated")
        self.assertEqual(self.world.state(self.plan), ("consumed", "done", "done"))
        self.assertEqual(len(self.deallocates()), 1)
        self.assertEqual(self.arm.operation_looks, 2, "the operation was looked at before each read of the resource, with the token of the person")
        self.assertEqual(set(self.world.person_tokens), {"https://management.azure.com/"})
        self.assertEqual(len(self.world.reader_tokens), self.reader_tokens_before, "the reader's token was not used for the change")

    def test_the_wait_between_two_looks_is_what_azure_asked_inside_two_to_five_seconds(self):
        self.world.run(self.plan)
        self.assertEqual(self.world.sleeps, [2.0], "Retry-After was 1, kept at two seconds")
        world = World()
        world.arm.add(fs.vm())
        world.arm.sizes[fs.rid("vm").lower()] = fs.D_SERIES
        world.arm.reads_before_effect = 3
        plan, _ = world.approved(world.arm.get(fs.rid("vm")), "vm", "delete", 60.0)
        world.run(plan)
        self.assertTrue(world.sleeps and set(world.sleeps) == {2.0})

    def test_an_operation_that_is_not_over_when_the_time_is_up_is_running_and_not_a_failure(self):
        self.arm.operation_polls = ["InProgress"]
        self.arm.stop_never = True
        done = self.world.run(self.plan)
        self.assertEqual((done.kind, done.action.state), ("running", "running"), done.action.result)
        self.assertEqual(done.action.result, RUNNING_TEXT)
        self.assertEqual(done.action.operation["pending"], True)
        self.assertEqual(done.action.operation["via"], "Azure-AsyncOperation")
        self.assertIsNone(done.action.finished_at)
        self.assertEqual(self.world.state(self.plan), ("consumed", "running", "running"), "the plan is used: a plan runs once; the case is running")
        self.assertEqual(len(self.world.sleeps), POLL_ATTEMPTS - 1)
        self.assertEqual(len(self.deallocates()), 1)
        self.assertIn("still making it", RUNNING_TEXT)
        self.assertIn("no second try", RUNNING_TEXT)

    def test_the_wait_is_bounded_and_makes_no_second_write(self):
        self.arm.operation_polls = ["InProgress"]
        self.arm.stop_never = True
        self.world.run(self.plan)
        self.assertLessEqual(sum(self.world.sleeps), 5 * (POLL_ATTEMPTS - 1))
        self.assertEqual(len(self.arm.writes()), 1)

    def test_an_operation_that_azure_says_failed_is_a_failure_at_once_with_what_azure_said(self):
        self.arm.operation_polls = ["Failed"]
        self.arm.operation_error = {"code": "AllocationFailed", "message": "no room"}
        self.arm.stop_never = True
        done = self.world.run(self.plan)
        self.assertEqual((done.kind, done.action.state), ("failed", "failed"))
        self.assertIn("AllocationFailed: no room", done.action.result)
        self.assertIn("Look at the resource in Azure before anything is tried again", done.action.result)
        self.assertEqual(self.world.state(self.plan), ("failed", "failed", "failed"))
        self.assertEqual(self.world.sleeps, [], "no look after it")
        self.assertEqual(len(self.arm.writes()), 1)

    def test_a_status_that_the_person_may_not_read_does_not_fail_the_change_the_resource_is_read_instead(self):
        for code in (401, 403, 404):
            with self.subTest(code):
                self.setUp()
                self.arm.operation_http_status = code
                done = self.world.run(self.plan)
                self.assertEqual((done.kind, done.action.state), ("ran", "done"), done.action.result)
                self.assertEqual(self.arm.operation_looks, 1, "asked once, then never again")

    def test_an_answer_with_only_a_location_is_followed_the_same_way(self):
        self.arm.via = "Location"
        done = self.world.run(self.plan)
        self.assertEqual((done.kind, done.action.state), ("ran", "done"))

    def test_an_answer_with_no_address_at_all_is_followed_by_reading_the_resource_alone(self):
        self.arm.via = "none"
        done = self.world.run(self.plan)
        self.assertEqual((done.kind, done.action.state), ("ran", "done"))
        self.assertEqual(self.arm.operation_looks, 0)
        self.arm.stop_never = True
        self.setUp()
        self.arm.via, self.arm.stop_never = "none", True
        done = self.world.run(self.plan)
        self.assertEqual((done.kind, done.action.state, done.action.operation["via"]), ("running", "running", "none"))

    def test_an_answer_of_200_with_a_state_that_is_not_final_is_followed_and_one_with_failed_is_a_failure_without_a_look(self):
        self.arm.async_writes, self.arm.provisioning_in_body = False, False
        self.arm.write_answers = [(200, {}, b'{"properties":{"provisioningState":"Updating"}}')]
        done = self.world.run(self.plan)
        self.assertEqual((done.kind, done.action.state), ("ran", "done"))
        self.setUp()
        self.arm.write_answers = []
        self.arm.async_writes = False
        original = self.arm.write

        def failing(method, key, body):
            status, headers, text = original(method, key, body)
            return 200, headers, b'{"properties":{"provisioningState":"Failed"}}'

        self.arm.write = failing
        done = self.world.run(self.plan)
        self.assertEqual((done.kind, done.action.state), ("failed", "failed"))
        self.assertIn("Azure answered that the change did not work", done.action.result)
        self.assertEqual(self.arm.operation_looks, 0)

    def test_a_synchronous_answer_that_the_resource_does_not_show_is_unknown_and_the_next_check_looks_again(self):
        self.arm.async_writes = False
        self.arm.stop_never = True
        done = self.world.run(self.plan)
        self.assertEqual((done.kind, done.action.state), ("ran_unconfirmed", "unknown"))
        self.assertIn("does not show it yet", done.action.result)
        self.assertEqual(self.world.sleeps, [5.0] * (POLL_ATTEMPTS - 1))
        self.assertEqual(self.world.state(self.plan), ("consumed", "unknown", "running"))

    def test_a_write_that_azure_refused_is_final_and_is_not_made_again(self):
        self.arm.write_answers = [(500, {}, b'{"error":{"code":"InternalError","message":"later"}}')]
        done = self.world.run(self.plan)
        self.assertEqual((done.kind, done.action.state), ("failed", "failed"))
        self.assertIn("The stop was refused or failed", done.action.result)
        self.assertEqual(len(self.deallocates()), 1)


class TheTimerSettlesWhatWasStillRunning(unittest.TestCase):
    """The end is read later with the reader's token and the list of the timer, which holds no write."""

    def setUp(self):
        self.world = World()
        self.arm = self.world.arm
        self.resource = self.arm.add(fs.vm())
        self.arm.sizes[self.resource["id"].lower()] = fs.D_SERIES
        self.plan, _ = self.world.approved(self.resource, "vm", "delete", 60.0)
        self.arm.operation_polls = ["InProgress"]
        self.arm.stop_never = True
        self.done = self.world.run(self.plan)
        self.assertEqual(self.done.kind, "running")
        self.writes = len(self.arm.writes())
        self.reader_before = len(self.world.reader_tokens)

    def test_a_change_that_azure_finished_meanwhile_is_done_and_says_that_the_later_check_confirmed_it(self):
        Arm = self.arm
        Arm.effects[self.resource["id"].lower()] = fs.Effect(0, lambda found: Arm.set_power(found, "deallocated"))
        self.world.clock.advance(minutes=3)
        result = self.world.tick()
        self.assertEqual([a.state for a in result.finished], ["done"])
        action = self.world.action(self.plan)
        self.assertEqual((action.state, action.operation["pending"]), ("done", False))
        self.assertTrue(action.result.endswith("(confirmed by the later check)."), action.result)
        self.assertEqual(action.verification["power"], "deallocated")
        self.assertEqual(self.world.state(self.plan), ("consumed", "done", "done"))
        self.assertEqual(len(Arm.writes()), self.writes, "the timer made no write")
        self.assertGreater(len(self.world.reader_tokens), self.reader_before, "it read with the reader's token")
        self.assertEqual(set(self.world.person_tokens), {"https://management.azure.com/"}, "the person's token was used by the sign-in only")
        self.assertIn(("action.finished", {"planId": self.plan.plan_id, "family": "stop-vm", "ok": True}), self.world.events)

    def test_a_change_that_azure_says_failed_is_failed_and_the_plan_and_the_case_with_it(self):
        self.resource["properties"]["provisioningState"] = "Failed"
        self.world.clock.advance(minutes=3)
        result = self.world.tick()
        self.assertEqual([a.state for a in result.finished], ["failed"])
        action = self.world.action(self.plan)
        self.assertIn("last operation on the machine failed", action.result)
        self.assertIn("Look at the resource in Azure before anything is tried again", action.result)
        self.assertEqual(action.error, action.result)
        self.assertEqual(self.world.state(self.plan), ("failed", "failed", "failed"))
        self.assertEqual(len(self.arm.writes()), self.writes)

    def test_a_change_that_is_still_being_made_is_left_alone_for_an_hour_and_is_not_stuck(self):
        for minutes in (3, 7, 10, 20, 15):  # 3, 10, 20, 40 and 55 minutes after the change was accepted
            self.world.clock.advance(minutes=minutes)
            self.assertEqual(self.world.tick().finished, [], minutes)
        action = self.world.action(self.plan)
        self.assertEqual((action.state, action.operation["pending"], action.result), ("running", True, RUNNING_TEXT))
        self.assertEqual(len(self.arm.writes()), self.writes)

    def test_a_change_whose_end_is_not_shown_after_an_hour_is_unknown_and_makes_no_second_write(self):
        self.world.clock.advance(minutes=RUNNING_GIVE_UP_MINUTES + 1)
        result = self.world.tick()
        self.assertEqual([a.state for a in result.finished], ["unknown"])
        action = self.world.action(self.plan)
        self.assertEqual((action.state, action.result, action.operation["pending"]), ("unknown", UNKNOWN_END, False))
        self.assertIn("Look at the resource in Azure", UNKNOWN_END)
        self.assertIn("a new try is a new approval by a person", UNKNOWN_END)
        self.assertEqual(len(self.arm.writes()), self.writes)
        self.assertEqual(self.world.tick().finished, [], "it is closed once")
        self.assertEqual(len(self.arm.writes()), self.writes)

    def test_an_unknown_end_is_settled_by_a_later_check_when_the_resource_shows_the_change(self):
        self.world.clock.advance(minutes=RUNNING_GIVE_UP_MINUTES + 1)
        self.world.tick()
        Arm = self.arm
        Arm.effects[self.resource["id"].lower()] = fs.Effect(0, lambda found: Arm.set_power(found, "deallocated"))
        self.world.clock.advance(minutes=5)
        self.world.tick()
        action = self.world.action(self.plan)
        self.assertEqual(action.state, "done")
        self.assertIn("confirmed by the later check", action.result)
        self.assertEqual(self.world.state(self.plan), ("consumed", "done", "done"))
        self.assertEqual(len(Arm.writes()), self.writes)

    def test_a_resource_that_cannot_be_read_leaves_the_change_running_and_is_not_a_failure(self):
        self.arm.read_status = 403
        self.world.clock.advance(minutes=3)
        self.assertEqual(self.world.tick().finished, [])
        self.assertEqual(self.world.action(self.plan).state, "running")

    def test_the_cost_lines_confirm_the_saving_later_after_the_change_is_done(self):
        Arm = self.arm
        Arm.effects[self.resource["id"].lower()] = fs.Effect(0, lambda found: Arm.set_power(found, "deallocated"))
        self.world.clock.advance(minutes=3)
        self.world.tick()
        self.world.costs.totals = {self.resource["id"].lower(): 0.0}
        self.world.clock.advance(days=3)
        result = self.world.tick()
        self.assertEqual([a.state for a in result.verified], ["verified"])
        action = self.world.action(self.plan)
        self.assertEqual(action.verification["costAfterUsd"], 0.0)
        self.assertIn("Confirmed", action.verification["note"])
        self.assertEqual(self.world.store.case_get(self.plan.case_id).status, "verified")

    def test_the_timer_cannot_make_a_write_even_when_it_wants_to(self):
        from cases.http import Refused
        for method, suffix in (("POST", "/deallocate"), ("PATCH", ""), ("DELETE", "")):
            with self.assertRaises(Refused):
                self.world.t.client.request(method, f"https://management.azure.com{self.resource['id']}{suffix}?api-version=2026-04-01")


class TheSameForAResizeAndAChangeOfTier(unittest.TestCase):
    def test_a_resize_whose_state_is_failed_is_a_failure_even_when_the_size_shows_the_new_one(self):
        world = World()
        resource = world.arm.add(fs.vm())
        world.arm.sizes[resource["id"].lower()] = fs.D_SERIES
        plan, _ = world.approved(resource, "vm", "change", 60.0)
        world.arm.resize_fails = True
        done = world.run(plan)
        self.assertEqual((done.kind, done.action.state), ("failed", "failed"), done.action.result)
        self.assertEqual(world.arm.get(resource["id"])["properties"]["hardwareProfile"]["vmSize"], "Standard_D2s_v5", "Azure shows the size that was asked for")
        self.assertIn("The size that Azure shows is the one that was asked for", done.action.result)

    def test_a_resize_that_is_still_updating_is_running_and_the_timer_settles_it(self):
        world = World()
        resource = world.arm.add(fs.vm())
        world.arm.sizes[resource["id"].lower()] = fs.D_SERIES
        plan, _ = world.approved(resource, "vm", "change", 60.0)
        world.arm.resize_never = True
        world.arm.operation_polls = ["InProgress"]
        done = world.run(plan)
        self.assertEqual((done.kind, done.action.state), ("running", "running"))
        self.assertEqual(len(world.arm.writes()), 1)
        resource["properties"]["provisioningState"] = "Succeeded"
        world.clock.advance(minutes=4)
        world.tick()
        self.assertEqual(world.state(plan), ("consumed", "done", "done"))
        self.assertEqual(len(world.arm.writes()), 1)

    def test_a_change_of_tier_is_followed_the_same_way(self):
        world = World()
        resource = world.arm.add(fs.disk(sku="Premium_LRS"))
        plan, _ = world.approved(resource, "disk", "change", 20.0)
        world.arm.tier_never = True
        world.arm.operation_polls = ["InProgress"]
        done = world.run(plan)
        self.assertEqual((done.kind, done.action.state), ("running", "running"))
        resource["properties"]["provisioningState"] = "Succeeded"
        world.clock.advance(minutes=4)
        world.tick()
        action = world.action(plan)
        self.assertEqual((action.state, action.verification["sku"]), ("done", "StandardSSD_LRS"))
        self.assertEqual(len(world.arm.writes()), 1)


class IdempotencyAndNoSecondTry(unittest.TestCase):
    def test_a_plan_runs_once_a_second_execution_is_refused_and_writes_nothing(self):
        world = World()
        resource = world.arm.add(fs.vm())
        world.arm.sizes[resource["id"].lower()] = fs.D_SERIES
        plan, _ = world.approved(resource, "vm", "delete", 60.0)
        self.assertEqual(world.run(plan).action.state, "done")
        again = world.run(plan)
        self.assertEqual((again.kind, again.action.state), ("failed", "failed"))
        self.assertEqual(len(world.arm.writes()), 1)

    def test_a_running_action_cannot_be_executed_again_either(self):
        world = World()
        resource = world.arm.add(fs.vm())
        world.arm.sizes[resource["id"].lower()] = fs.D_SERIES
        plan, _ = world.approved(resource, "vm", "delete", 60.0)
        world.arm.operation_polls, world.arm.stop_never = ["InProgress"], True
        self.assertEqual(world.run(plan).kind, "running")
        again = world.run(plan)
        self.assertEqual(again.action.state, "failed", "the plan is used: it is not approved any more")
        self.assertEqual(len(world.arm.writes()), 1)

    def test_a_machine_that_is_released_already_is_a_no_op_that_says_so(self):
        world = World()
        resource = world.arm.add(fs.vm())
        world.arm.sizes[resource["id"].lower()] = fs.D_SERIES
        plan, _ = world.approved(resource, "vm", "delete", 60.0)
        fs.Arm.set_power(resource, "deallocated")
        done = world.run(plan)
        self.assertEqual((done.kind, done.action.state), ("unchanged", "done"))
        self.assertIn("already stopped and released", done.action.result)
        self.assertEqual(world.arm.writes(), [])

    def test_a_machine_that_has_the_size_already_is_a_no_op_and_one_that_is_still_updating_to_it_is_not(self):
        world = World()
        resource = world.arm.add(fs.vm())
        world.arm.sizes[resource["id"].lower()] = fs.D_SERIES
        plan, _ = world.approved(resource, "vm", "change", 60.0)
        resource["properties"]["hardwareProfile"]["vmSize"] = "Standard_D2s_v5"
        done = world.run(plan)
        self.assertEqual((done.kind, done.action.state), ("unchanged", "done"))
        self.assertIn("already of size Standard_D2s_v5", done.action.result)
        self.assertEqual(world.arm.writes(), [])
        world = World()
        resource = world.arm.add(fs.vm())
        world.arm.sizes[resource["id"].lower()] = fs.D_SERIES
        plan, _ = world.approved(resource, "vm", "change", 60.0)
        resource["properties"]["hardwareProfile"]["vmSize"] = "Standard_D2s_v5"
        resource["properties"]["provisioningState"] = "Updating"
        done = world.run(plan)
        self.assertEqual((done.kind, done.action.state), ("stopped", "failed"), "an operation is going on: it is not made a second time")
        self.assertEqual(world.arm.writes(), [])

    def test_a_disk_that_has_the_tier_already_is_a_no_op(self):
        world = World()
        resource = world.arm.add(fs.disk(sku="Premium_LRS"))
        plan, _ = world.approved(resource, "disk", "change", 20.0)
        resource["sku"] = {"name": "StandardSSD_LRS"}
        done = world.run(plan)
        self.assertEqual((done.kind, done.action.state), ("unchanged", "done"))
        self.assertIn("already a Standard SSD", done.action.result)
        self.assertEqual(world.arm.writes(), [])

    def test_a_resource_that_is_gone_is_done_for_a_delete_and_a_stop_for_a_change(self):
        world = World()
        resource = world.arm.add(fs.disk(sku="StandardSSD_LRS"))
        plan, _ = world.approved(resource, "disk", "delete", 20.0, detector="orphan-managed-disk")
        del world.arm.resources[resource["id"].lower()]
        done = world.run(plan)
        self.assertEqual((done.kind, done.action.state), ("unchanged", "done"))
        self.assertIn("did not exist any more", done.action.result)
        world = World()
        vm = world.arm.add(fs.vm())
        world.arm.sizes[vm["id"].lower()] = fs.D_SERIES
        plan, _ = world.approved(vm, "vm", "delete", 60.0)
        del world.arm.resources[vm["id"].lower()]
        done = world.run(plan)
        self.assertEqual((done.kind, done.action.state), ("stopped", "failed"))
        self.assertIn("does not exist any more", done.action.result)


if __name__ == "__main__":
    unittest.main()
