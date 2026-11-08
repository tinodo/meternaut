"""The step of the action `cases` that clears what is in the way of the deploy: tools/cases-move.py, run against a model of Azure, and the step of the Hub workflow that runs it.

The first real move of the web page from Basic to Flex Consumption (2026-11-07) stopped three times: the platform answered the delete of the app with a gateway time-out although the delete went
through; a rerun then found the app gone and cleared nothing, so the deploy was refused for role assignments of the old identity; and after those were deleted by hand, for a private endpoint that was
left Disconnected. The tests below hold that the next run works whatever an earlier one did: each thing is read as it is, deleted when it is in the way, and read again.
"""
from __future__ import annotations

import importlib.util
import json
import os
import re
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("cases_move", ROOT / "tools" / "cases-move.py")
cm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cm)

SUB = "11111111-2222-3333-4444-555555555555"
GROUP = "rg-example"
APP = "func-meternaut-cases-0123abcd"
GROUP_ID = f"/subscriptions/{SUB}/resourceGroups/{GROUP}"
BASE = f"{GROUP_ID}/providers"
SITE = f"{BASE}/Microsoft.Web/sites/{APP}"
BASIC_NAME, FLEX_NAME = "plan-meternaut-cases-basic", "plan-meternaut-cases"
BASIC_PLAN, FLEX_PLAN = f"{BASE}/Microsoft.Web/serverfarms/{BASIC_NAME}", f"{BASE}/Microsoft.Web/serverfarms/{FLEX_NAME}"
ENDPOINT = f"{BASE}/Microsoft.Network/privateEndpoints/pe-{APP}"
STORAGE = f"{BASE}/Microsoft.Storage/storageAccounts/stmeternaut0123abcd"
INSIGHTS = f"{BASE}/Microsoft.Insights/components/appi-meternaut"
CONTAINERS = [f"{STORAGE}/blobServices/default/containers/{name}" for name in ("azure-webjobs-hosts", "azure-webjobs-secrets")]
BLOB, QUEUE, TABLE, METRICS = ("b7e6dc6d-f1e8-4753-8033-0f276bb0955b", "974c5e8b-45b9-4653-ba55-5f855dd0fb88", "0a9a7e1f-b9d0-4cc4-a60d-0319b160aaa3", "3913510d-42f4-4e42-8a64-420c390055eb")
# What the template writes for the app: the scope and the role of each assignment, as the preview of the deployment lists them (the model names each with a fixed id).
THE_TEMPLATES = [*[(container, BLOB) for container in CONTAINERS], (STORAGE, QUEUE), (STORAGE, TABLE), (INSIGHTS, METRICS)]
THE_IDS = [f"{scope}/providers/Microsoft.Authorization/roleAssignments/00000000-0000-4000-8000-{number:012d}" for number, (scope, _) in enumerate(THE_TEMPLATES, 1)]
OLD, NEW = "aaaaaaaa-0000-4000-8000-000000000001", "bbbbbbbb-0000-4000-8000-000000000002"
ENVIRONMENT = {"GITHUB_ACTIONS": "true", "ENV_SUBSCRIPTION_ID": SUB, "ENV_RESOURCE_GROUP": GROUP}
TIMEOUT = 'ERROR: Gateway Timeout({"error":{"code":"GatewayTimeout","message":"The gateway did not receive a response from \'Microsoft.Web\' within the specified time period."}})'
NOT_THERE = "ERROR: (ResourceNotFound) The Resource '{}' under resource group 'rg-example' was not found."


class Clock:
    def __init__(self) -> None:
        self.now = 0.0
        self.sleeps: list[float] = []

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds

    def time(self) -> float:
        return self.now


class FakeAzure:
    """A model of the project's resource group: what is there, what a read, a delete and a preview of the deployment say, what a slow Azure says, and every call that was made."""

    def __init__(self) -> None:
        self.resources: dict[str, dict] = {}
        self.calls: list[list[str]] = []
        self.deleted: list[str] = []
        self.delete_calls: list[str] = []
        self.hooks: list = []
        self.lag: dict[str, int] = {}
        self.preview_error: str | None = None
        self.preview_raw: str | None = None
        self.preview_extra: list[dict] = []

    def put(self, resource_id: str, document: dict | None = None) -> str:
        self.resources[resource_id.lower()] = {"id": resource_id, **(document or {})}
        return resource_id

    def has(self, resource_id: str) -> bool:
        return resource_id.lower() in self.resources

    def plan(self, resource_id: str, tier: str) -> str:
        return self.put(resource_id, {"sku": {"tier": tier}})

    def site(self, plan_id: str, principal: str | None = NEW) -> str:
        return self.put(SITE, {"properties": {"serverFarmId": plan_id}, "identity": {"type": "SystemAssigned", "principalId": principal} if principal else {}})

    def endpoint(self, status: str = "Approved", target: str = SITE) -> str:
        return self.put(ENDPOINT, {"properties": {"privateLinkServiceConnections": [{"properties": {"privateLinkServiceId": target, "privateLinkServiceConnectionState": {"status": status}}}]}})

    def assignment(self, number: int, principal: str) -> str:
        scope, role = THE_TEMPLATES[number]
        return self.put(THE_IDS[number], {"properties": {"principalId": principal, "scope": scope, "roleDefinitionId": f"/subscriptions/{SUB}/providers/Microsoft.Authorization/roleDefinitions/{role}"}})

    def all_assignments(self, principal: str) -> None:
        for number in range(len(THE_IDS)):
            self.assignment(number, principal)

    def really_delete(self, path: str) -> None:
        key = path.lower()
        document = self.resources.pop(key)
        self.deleted.append(path)
        if self.lag.get(key):
            self.resources[f"{key}#ghost"] = {"ghost_of": key, "reads": self.lag[key], "document": document}

    def __call__(self, args):
        self.calls.append(list(args))
        a = list(args)
        if a[:3] == ["deployment", "group", "what-if"]:
            if self.preview_error:
                return 1, "", self.preview_error
            if self.preview_raw is not None:
                return 0, self.preview_raw, ""
            changes = [{"resourceId": THE_IDS[i], "changeType": "Modify" if self.has(THE_IDS[i]) else "Create"} for i in range(len(THE_IDS))]
            changes += [{"resourceId": SITE, "changeType": "Modify"}, {"resourceId": ENDPOINT, "changeType": "Modify"}, *self.preview_extra]
            return 0, json.dumps({"changes": changes, "status": "Succeeded"}), ""
        assert a[0] == "rest", a
        method, url = a[a.index("--method") + 1], a[a.index("--url") + 1]
        assert url.startswith(cm.ARM), url
        path = url[len(cm.ARM):url.index("?")]
        key = path.lower()
        if method == "delete":
            self.delete_calls.append(path)
        for hook in self.hooks:
            answer = hook(method, path)
            if answer is not None:
                return answer
        if method == "get":
            ghost = self.resources.get(f"{key}#ghost")
            if ghost and ghost["reads"] > 0:
                ghost["reads"] -= 1
                return 0, json.dumps(ghost["document"]), ""
            if key not in self.resources:
                return 3, "", NOT_THERE.format(path)
            return 0, json.dumps(self.resources[key]), ""
        if key not in self.resources:
            return 3, "", NOT_THERE.format(path)
        self.really_delete(path)
        return 0, "", ""

    def deletes_only(self) -> list[str]:
        """The ids of the resources that a delete reached, in order, whatever the id's case."""
        return list(self.deleted)


def arguments(**changes) -> list[str]:
    values = {"--subscription": SUB, "--resource-group": GROUP, "--app": APP, "--wanted-kind": "Flex", "--wanted-tier": "FlexConsumption", "--other-plan": BASIC_NAME, "--other-tier": "Basic",
              "--template": "environment/cases/main.bicep", "--parameters": "cases.parameters.json"}
    values.update({"--" + key.replace("_", "-"): value for key, value in changes.items()})
    return ["run", *[part for pair in values.items() for part in pair]]


def run(azure: FakeAzure, environ=None, **changes):
    clock, lines = Clock(), []
    with tempfile.TemporaryDirectory() as tmp:
        summary = Path(tmp) / "summary.md"
        code = cm.main(arguments(summary=str(summary), **changes), runner=azure, environ=ENVIRONMENT if environ is None else environ, sleep=clock.sleep, clock=clock.time, out=lines.append)
        text = summary.read_text(encoding="utf-8") if summary.exists() else ""
    return code, lines, text, clock


def said(lines: list[str]) -> str:
    return "\n".join(lines)


def basic_world() -> FakeAzure:
    """The estate as it is before the first move: the app on the Basic plan with its identity, its endpoint connected, and its assignments, all for the old identity."""
    azure = FakeAzure()
    azure.plan(BASIC_PLAN, "Basic")
    azure.site(BASIC_PLAN, OLD)
    azure.endpoint("Approved")
    azure.all_assignments(OLD)
    return azure


class TheMove(unittest.TestCase):
    def test_the_first_move_deletes_the_app_its_plan_its_endpoint_and_the_assignments_of_the_old_identity_in_that_order_and_waits_for_the_host_name(self):
        azure = basic_world()
        code, lines, summary, clock = run(azure)
        self.assertEqual(code, 0, lines)
        self.assertEqual(azure.deleted, [SITE, BASIC_PLAN, ENDPOINT, *THE_IDS])
        self.assertIn(cm.HOST_NAME_SECONDS, clock.sleeps, "the host name is let go a little after the app")
        self.assertIn("deleted (it ran on the plan plan-meternaut-cases-basic, a Basic plan, and CASES_APP_PLAN asks for Flex)", "\n".join(lines))
        self.assertIn("the role assignments that the deploy will write: 5 listed, 0 were not there, 0 are the app's own and were kept, 5 were deleted", said(lines))
        self.assertEqual(lines[-1], "Clear.")
        self.assertIn("**a new system-assigned identity**", summary)
        self.assertIn("Run `foundry` after this run", summary)
        self.assertIn("`aigateway` (on the owner's written word, as for its first run)", summary)

    def test_a_second_run_finds_nothing_in_the_way_and_deletes_nothing(self):
        azure = basic_world()
        run(azure)
        deleted = list(azure.deleted)
        code, lines, summary, clock = run(azure)
        self.assertEqual(code, 0, lines)
        self.assertEqual(azure.deleted, deleted, "nothing more is deleted")
        self.assertEqual(summary, "", "nothing was cleared, so there is nothing to tell a person")
        self.assertNotIn(cm.HOST_NAME_SECONDS, clock.sleeps)
        text = "\n".join(lines)
        for line in (f"the cases app {APP}: was not there", f"the plan {BASIC_NAME}: was not there", f"the private endpoint pe-{APP}: was not there"):
            self.assertIn(line, text)

    def test_app_already_gone_and_the_private_endpoint_disconnected_still_there_the_endpoint_is_deleted(self):
        # The third hole of the first move: the app was deleted by an earlier run, so the run that follows found no app, and the deploy was refused for the endpoint
        # (PrivateEndpointCannotBeUpdatedInDisconnectedState).
        azure = FakeAzure()
        azure.endpoint("Disconnected")
        code, lines, summary, clock = run(azure)
        self.assertEqual(code, 0, lines)
        self.assertEqual(azure.deleted, [ENDPOINT])
        self.assertIn(f"the private endpoint pe-{APP}: deleted (its connection is Disconnected); the deploy makes it again", said(lines))
        self.assertIn(f"the cases app {APP}: was not there", "\n".join(lines))
        self.assertNotIn(cm.HOST_NAME_SECONDS, clock.sleeps, "the app was not deleted by this run")
        self.assertIn("a new system-assigned identity", summary)

    def test_a_new_app_that_an_earlier_deploy_made_does_not_keep_the_endpoint_that_is_disconnected_from_its_predecessor(self):
        azure = FakeAzure()
        azure.plan(FLEX_PLAN, "FlexConsumption")
        azure.site(FLEX_PLAN, NEW)
        azure.endpoint("Disconnected")
        code, lines, _, _ = run(azure)
        self.assertEqual((code, azure.deleted), (0, [ENDPOINT]), lines)
        self.assertTrue(azure.has(SITE), "the app that the deploy made is the right kind and stays")
        self.assertIn("runs on the plan plan-meternaut-cases, a FlexConsumption plan, which is the kind that CASES_APP_PLAN asks for (Flex): kept", "\n".join(lines))

    def test_an_endpoint_that_points_at_an_app_that_is_not_there_goes_too_even_when_it_still_says_approved(self):
        azure = FakeAzure()
        azure.endpoint("Approved")
        code, lines, _, _ = run(azure)
        self.assertEqual((code, azure.deleted), (0, [ENDPOINT]), lines)
        self.assertIn("deleted (the app that it points at is not there)", "\n".join(lines))

    def test_an_endpoint_that_is_connected_to_an_app_that_is_there_is_kept(self):
        azure = FakeAzure()
        azure.plan(FLEX_PLAN, "FlexConsumption")
        azure.site(FLEX_PLAN, NEW)
        azure.endpoint("Approved")
        code, lines, _, _ = run(azure)
        self.assertEqual((code, azure.deleted), (0, []), lines)
        self.assertIn(f"the private endpoint pe-{APP}: kept (its connection is Approved, and the app that it points at is there)", said(lines))

    def test_app_already_gone_and_assignments_of_the_old_identity_still_there_they_are_deleted_before_the_deploy(self):
        # The second hole: the cleanup of the old identity's assignments ran only while the old app could be read, and the deploy was refused (RoleAssignmentUpdateNotPermitted).
        azure = FakeAzure()
        azure.all_assignments(OLD)
        code, lines, summary, _ = run(azure)
        self.assertEqual(code, 0, lines)
        self.assertEqual(azure.deleted, THE_IDS)
        text = "\n".join(lines)
        self.assertIn(f"the cases app {APP}: was not there", text)
        self.assertIn("(Storage Blob Data Owner on containers/azure-webjobs-hosts): deleted", text)
        self.assertIn("(Storage Blob Data Owner on containers/azure-webjobs-secrets): deleted", text)
        self.assertIn("(Storage Queue Data Contributor on storageAccounts/stmeternaut0123abcd): deleted", text)
        self.assertIn("(Storage Table Data Contributor on storageAccounts/stmeternaut0123abcd): deleted", text)
        self.assertIn("(Monitoring Metrics Publisher on components/appi-meternaut): deleted", text)
        self.assertIn("5 were deleted", text)
        self.assertNotIn("Event Hubs", text, "the template gives the app no role on a hub any more")
        self.assertIn("**a new system-assigned identity**", summary)

    def test_a_new_app_keeps_its_own_assignments_and_loses_the_ones_of_an_identity_that_is_gone(self):
        azure = FakeAzure()
        azure.plan(FLEX_PLAN, "FlexConsumption")
        azure.site(FLEX_PLAN, NEW)
        azure.endpoint("Approved")
        for number in (0, 1):
            azure.assignment(number, NEW.upper())
        for number in (2, 3, 4):
            azure.assignment(number, OLD)
        code, lines, _, _ = run(azure)
        self.assertEqual((code, azure.deleted), (0, THE_IDS[2:]), lines)
        self.assertIn("5 listed, 0 were not there, 2 are the app's own and were kept, 3 were deleted", said(lines))
        self.assertEqual(sum(1 for line in lines if ": kept (it is the app's own)" in line), 2)

    def test_a_leftover_plan_of_the_other_kind_is_deleted_when_the_app_is_not_on_it_and_a_wanted_plan_is_not_touched(self):
        azure = FakeAzure()
        azure.plan(BASIC_PLAN, "Basic")
        azure.plan(FLEX_PLAN, "FlexConsumption")
        azure.site(FLEX_PLAN, NEW)
        azure.endpoint("Approved")
        azure.all_assignments(NEW)
        code, lines, summary, clock = run(azure)
        self.assertEqual((code, azure.deleted), (0, [BASIC_PLAN]), lines)
        self.assertTrue(azure.has(FLEX_PLAN))
        self.assertIn(f"the plan {BASIC_NAME}: deleted (a Basic plan, and the cases app is not on it)", said(lines))
        self.assertNotIn(cm.HOST_NAME_SECONDS, clock.sleeps, "the app was not deleted by this run")
        self.assertIn("a new system-assigned identity", summary)

    def test_the_way_back_is_the_same_step_the_other_way(self):
        azure = FakeAzure()
        azure.plan(FLEX_PLAN, "FlexConsumption")
        azure.site(FLEX_PLAN, OLD)
        azure.endpoint("Approved")
        azure.all_assignments(OLD)
        code, lines, _, _ = run(azure, wanted_kind="Basic", wanted_tier="Basic", other_plan=FLEX_NAME, other_tier="FlexConsumption")
        self.assertEqual((code, azure.deleted), (0, [SITE, FLEX_PLAN, ENDPOINT, *THE_IDS]), lines)

    def test_a_plan_that_is_neither_kind_stops_the_run_and_nothing_is_deleted(self):
        azure = FakeAzure()
        elsewhere = azure.plan(f"{BASE}/Microsoft.Web/serverfarms/plan-elsewhere", "Standard")
        azure.site(elsewhere, OLD)
        azure.endpoint("Disconnected")
        azure.all_assignments(OLD)
        code, lines, _, _ = run(azure)
        self.assertEqual((code, azure.deleted, azure.delete_calls), (1, [], []))
        self.assertIn("a plan that this workflow does not know is never deleted", lines[-1])
        self.assertTrue(lines[-1].startswith("::error::The cases app runs on the plan plan-elsewhere, whose tier is Standard."))

    def test_the_plan_of_the_other_kind_is_only_deleted_while_its_tier_is_that_kinds(self):
        azure = FakeAzure()
        azure.plan(BASIC_PLAN, "Standard")
        code, lines, _, _ = run(azure)
        self.assertEqual((code, azure.delete_calls), (1, []))
        self.assertIn("is a Standard plan and the other kind is Basic: it is not deleted", lines[-1])


class TheSlowAzure(unittest.TestCase):
    def test_a_gateway_timeout_on_a_delete_that_went_through_is_tried_again_and_the_not_found_after_it_is_a_delete(self):
        # The first hole: run 42431770239 stopped here, although the app was gone afterwards.
        azure = basic_world()
        calls = []

        def hook(method, path):
            if method == "delete" and path.lower() == SITE.lower() and not calls:
                calls.append(path)
                azure.really_delete(path)
                return 1, "", TIMEOUT
            return None
        azure.hooks.append(hook)
        code, lines, _, clock = run(azure)
        self.assertEqual(code, 0, lines)
        self.assertEqual(azure.deleted, [SITE, BASIC_PLAN, ENDPOINT, *THE_IDS])
        self.assertEqual(azure.delete_calls.count(SITE), 2, "the second try found nothing: Azure says not found, and that is gone")
        self.assertTrue(any(line.startswith("::warning::the cases app") and "transient error" in line and "Gateway Timeout" in line for line in lines), lines)
        self.assertIn(cm.PAUSE, clock.sleeps)

    def test_a_delete_that_only_gets_gateway_timeouts_is_read_again_and_a_delete_that_went_through_is_accepted(self):
        azure = basic_world()
        calls = []

        def hook(method, path):
            if method == "delete" and path.lower() == BASIC_PLAN.lower():
                calls.append(path)
                if len(calls) == 1:
                    azure.really_delete(path)
                return 1, "", TIMEOUT if len(calls) == 1 else TIMEOUT.replace("Gateway Timeout(", "Gateway Timeout (again)(")
            return None
        azure.hooks.append(hook)
        code, lines, _, clock = run(azure)
        self.assertEqual(code, 0, lines)
        self.assertEqual(len(calls), cm.TRIES, "five tries, a quarter of a minute apart")
        self.assertEqual(clock.sleeps.count(cm.PAUSE), cm.TRIES - 1)
        self.assertIn("::warning::the plan plan-meternaut-cases-basic: the delete got only transient answers", " ".join(lines))
        self.assertIn(BASIC_PLAN, azure.deleted)

    def test_a_delete_that_only_gets_gateway_timeouts_and_did_not_go_through_stops_the_run_and_says_so(self):
        azure = basic_world()
        azure.hooks.append(lambda method, path: (1, "", TIMEOUT) if method == "delete" and path.lower() == SITE.lower() else None)
        code, lines, _, clock = run(azure)
        self.assertEqual((code, azure.deleted), (1, []))
        self.assertIn("is still there 5 minutes after the delete was tried, and Azure answered with a transient error every time. Run the action again", lines[-1])
        self.assertGreaterEqual(sum(clock.sleeps), cm.WAIT_SECONDS)

    def test_every_transient_answer_is_tried_again_and_no_other_is(self):
        for text in (TIMEOUT, "ERROR: (ServiceUnavailable) The service is unavailable.", "ERROR: Bad Gateway", "ERROR: TooManyRequests: slow down", "Operation returned an invalid status 'Service Unavailable'",
                     "ERROR: Too Many Requests", "ERROR: The request failed with HTTP 502", "(504) Gateway time out"):
            with self.subTest(text=text):
                self.assertTrue(cm.TRANSIENT.search(text), text)
        for text in ("ERROR: (AuthorizationFailed) The client does not have authorization", "ERROR: (ResourceNotFound) not found", "ERROR: (Conflict) the plan has apps", "ERROR: InvalidTemplate",
                     "ERROR: (AuthorizationFailed) at 2026-11-07T22:45:33.504+00:00 correlation 0a0b0c0d-1111-2222-3333-444444444503"):
            with self.subTest(text=text):
                self.assertFalse(cm.TRANSIENT.search(text), text)

    def test_a_read_that_gets_a_timeout_is_made_again_and_one_that_keeps_getting_it_stops_the_run_with_the_text(self):
        azure = FakeAzure()
        answers = [(1, "", TIMEOUT)] * 2
        azure.hooks.append(lambda method, path: answers.pop(0) if method == "get" and path.lower() == SITE.lower() and answers else None)
        code, lines, _, clock = run(azure)
        self.assertEqual(code, 0, lines)
        self.assertEqual(clock.sleeps[:2], [cm.PAUSE, cm.PAUSE])
        azure = FakeAzure()
        azure.hooks.append(lambda method, path: (1, "", TIMEOUT) if method == "get" and path.lower() == SITE.lower() else None)
        code, lines, _, clock = run(azure)
        self.assertEqual(code, 1)
        self.assertIn(f"the cases app {APP} could not be read: ERROR: Gateway Timeout", lines[-1])
        self.assertEqual(clock.sleeps.count(cm.PAUSE), cm.TRIES - 1)

    def test_a_refusal_that_is_not_transient_stops_at_once_without_another_try(self):
        azure = basic_world()
        azure.hooks.append(lambda method, path: (1, "", "ERROR: (AuthorizationFailed) The client does not have authorization to perform action") if method == "delete" and path.lower() == SITE.lower() else None)
        code, lines, _, clock = run(azure)
        self.assertEqual((code, azure.deleted, azure.delete_calls, clock.sleeps), (1, [], [SITE], []))
        self.assertIn(f"the cases app {APP} could not be deleted: ERROR: (AuthorizationFailed)", lines[-1])

    def test_a_delete_that_azure_shows_for_a_while_is_read_again_every_quarter_of_a_minute_until_it_is_gone(self):
        azure = basic_world()
        azure.lag[ENDPOINT.lower()] = 3
        code, lines, _, clock = run(azure)
        self.assertEqual(code, 0, lines)
        self.assertEqual(clock.sleeps.count(cm.POLL_SECONDS), 3)

    def test_a_refused_delete_of_an_assignment_says_what_a_person_does_and_the_deploy_is_not_left_to_fail_without_a_word(self):
        azure = FakeAzure()
        azure.all_assignments(OLD)
        azure.hooks.append(lambda method, path: (1, "", "ERROR: (AuthorizationFailed) condition") if method == "delete" and path == THE_IDS[2] else None)
        code, lines, _, _ = run(azure)
        self.assertEqual((code, azure.deleted), (1, THE_IDS[:2]))
        self.assertIn("could not be deleted: ERROR: (AuthorizationFailed) condition", lines[-1])
        self.assertIn("a person deletes it with their own sign-in, on the owner's written word, and runs the action again (environment/BOOTSTRAP.md)", lines[-1])


class ThePreview(unittest.TestCase):
    def test_the_preview_is_asked_for_resource_ids_only_with_the_files_of_the_deploy(self):
        azure = FakeAzure()
        run(azure)
        (parts,) = [c for c in azure.calls if c[:3] == ["deployment", "group", "what-if"]]
        self.assertEqual(parts[parts.index("--result-format") + 1], "ResourceIdOnly")
        self.assertIn("--no-pretty-print", parts)
        self.assertEqual(parts[parts.index("--template-file") + 1], "environment/cases/main.bicep")
        self.assertEqual(parts[parts.index("--parameters") + 1], "@cases.parameters.json")
        self.assertEqual((parts[parts.index("--subscription") + 1], parts[parts.index("--resource-group") + 1]), (SUB, GROUP))

    def test_a_preview_that_cannot_be_read_is_said_and_the_rest_of_the_step_goes_on(self):
        azure = FakeAzure()
        azure.endpoint("Disconnected")
        azure.all_assignments(OLD)
        azure.preview_error = "ERROR: (InvalidTemplate) the template is not valid"
        code, lines, _, _ = run(azure)
        self.assertEqual((code, azure.deleted), (0, [ENDPOINT]), "the endpoint does not depend on the preview, and no assignment is deleted that is not known to be the template's")
        self.assertTrue(any(line.startswith("::warning::The preview of the deployment could not be read (ERROR: (InvalidTemplate)") for line in lines), lines)
        self.assertIn("the role assignments that the deploy will write: could not be listed (see the warning above)", said(lines))

    def test_a_preview_that_has_no_list_of_changes_is_said_too(self):
        for raw in ("not json at all", json.dumps({"status": "Succeeded"}), json.dumps([1, 2])):
            with self.subTest(raw=raw):
                azure = FakeAzure()
                azure.all_assignments(OLD)
                azure.preview_raw = raw
                code, lines, _, _ = run(azure)
                self.assertEqual((code, azure.deleted), (0, []), lines)
                self.assertTrue(any("The preview of the deployment has no list of changes" in line for line in lines), lines)

    def test_an_id_that_the_preview_cannot_work_out_before_the_deploy_is_in_potential_changes_and_counts_too(self):
        azure = FakeAzure()
        azure.all_assignments(OLD)
        azure.preview_raw = json.dumps({"status": "Succeeded", "changes": [{"resourceId": THE_IDS[0], "changeType": "Modify"}],
                                        "potentialChanges": [{"resourceId": THE_IDS[1], "changeType": "Ignore"}, {"resourceId": THE_IDS[0], "changeType": "Ignore"}]})
        code, lines, _, _ = run(azure)
        self.assertEqual((code, azure.deleted), (0, THE_IDS[:2]), lines)

    def test_the_list_may_sit_under_properties_as_the_service_writes_it(self):
        azure = FakeAzure()
        azure.all_assignments(OLD)
        azure.preview_raw = json.dumps({"status": "Succeeded", "properties": {"changes": [{"resourceId": THE_IDS[0], "changeType": "Modify"}]}})
        code, lines, _, _ = run(azure)
        self.assertEqual((code, azure.deleted), (0, [THE_IDS[0]]), lines)

    def test_only_a_role_assignment_in_the_project_group_that_the_preview_lists_is_ever_deleted(self):
        azure = FakeAzure()
        azure.all_assignments(OLD)
        other_group = f"/subscriptions/{SUB}/resourceGroups/rg-other/providers/Microsoft.Storage/storageAccounts/x/providers/Microsoft.Authorization/roleAssignments/00000000-0000-4000-8000-0000000000ff"
        other_subscription = f"/subscriptions/{SUB}/providers/Microsoft.Authorization/roleAssignments/00000000-0000-4000-8000-0000000000fe"
        a_site = SITE
        for resource_id in (other_group, other_subscription):
            azure.put(resource_id, {"properties": {"principalId": OLD}})
        azure.preview_extra = [{"resourceId": other_group, "changeType": "Modify"}, {"resourceId": other_subscription, "changeType": "Modify"}, {"resourceId": a_site, "changeType": "Modify"},
                               {"resourceId": THE_IDS[0].upper(), "changeType": "Modify"}, {"changeType": "Create"}, "not a change"]
        azure.put(a_site, {"properties": {"serverFarmId": FLEX_PLAN}})
        azure.plan(FLEX_PLAN, "FlexConsumption")
        code, lines, _, _ = run(azure)
        self.assertEqual(code, 0, lines)
        self.assertEqual(sorted(azure.deleted), sorted(THE_IDS), "the five of the template, once each, and nothing of another group, of the subscription or of a resource that is not an assignment")
        self.assertTrue(azure.has(other_group) and azure.has(other_subscription) and azure.has(a_site))

    def test_an_assignment_that_is_not_there_yet_is_counted_and_not_read_again(self):
        azure = FakeAzure()
        code, lines, summary, _ = run(azure)
        self.assertEqual(code, 0, lines)
        self.assertIn("the role assignments that the deploy will write: 5 listed, 5 were not there, 0 are the app's own and were kept, 0 were deleted", said(lines))
        self.assertEqual((azure.deleted, summary), ([], ""), "a new estate has nothing in the way and nothing to tell")


class TheRunner(unittest.TestCase):
    def test_az_is_the_one_of_the_environment_and_is_asked_to_show_errors_only(self):
        with mock.patch.object(cm.subprocess, "run", return_value=types.SimpleNamespace(returncode=3, stdout="out", stderr="err")) as called, mock.patch.dict(os.environ, {"AZ": "/x/az"}):
            self.assertEqual(cm.run_az(["rest", "--method", "get"]), (3, "out", "err"))
        called.assert_called_once_with(["/x/az", "rest", "--method", "get", "--only-show-errors"], capture_output=True, text=True)


class TheRefusals(unittest.TestCase):
    def test_nothing_is_read_or_changed_outside_a_github_actions_run(self):
        azure = basic_world()
        code, lines, _, _ = run(azure, environ={"ENV_SUBSCRIPTION_ID": SUB, "ENV_RESOURCE_GROUP": GROUP})
        self.assertEqual((code, azure.calls), (2, []))
        self.assertIn("only a GitHub Actions run may do that (AGENTS.md rule 18)", lines[-1])

    def test_no_other_group_or_subscription_can_be_named(self):
        for environ in ({**ENVIRONMENT, "ENV_RESOURCE_GROUP": "rg-another"}, {**ENVIRONMENT, "ENV_SUBSCRIPTION_ID": "99999999-2222-3333-4444-555555555555"}):
            azure = basic_world()
            code, lines, _, _ = run(azure, environ=environ)
            self.assertEqual((code, azure.calls), (2, []))
            self.assertTrue(lines[-1].startswith("::error::the "), lines)

    def test_a_name_that_is_not_a_resource_name_is_refused(self):
        for changes in ({"app": "x/../y"}, {"app": "a"}, {"other_plan": "plan elsewhere"}, {"resource_group": "rg/other"}, {"subscription": "not-a-guid"}):
            azure = basic_world()
            code, lines, _, _ = run(azure, **changes)
            self.assertEqual((code, azure.calls), (2, []), changes)


class TheTemplate(unittest.TestCase):
    """What the tool relies on is what the template writes: a change of the template that breaks it fails here."""

    def setUp(self):
        self.code = re.sub(r"(?m)//.*$", "", (ROOT / "environment" / "cases" / "main.bicep").read_text(encoding="utf-8"))

    def test_every_role_assignment_of_the_template_is_for_the_apps_own_identity_and_named_after_the_apps_id(self):
        blocks = [b for b in re.split(r"(?m)^(?=resource )", self.code) if b.startswith("resource ") and "Microsoft.Authorization/roleAssignments" in b.splitlines()[0]]
        self.assertGreaterEqual(len(blocks), 5)
        for block in blocks:
            header = block.splitlines()[0]
            self.assertIn("principalId: functionApp.identity.principalId", block, f"{header}: an assignment for another principal would look stale to the tool, which deletes what is not the app's own")
            self.assertRegex(block, r"name: guid\([^)\n]*functionApp\.id", f"{header}: named after the app's id, so that a new identity meets an assignment of the same name and Azure refuses the change")

    def test_the_resources_that_the_tool_reads_and_deletes_are_the_ones_of_the_template_with_the_api_versions_that_it_writes_them_with(self):
        made = re.search(r"resource functionAppEndpoint 'Microsoft\.Network/privateEndpoints@(\S+)' = \{\s+name: 'pe-\$\{functionAppName\}'", self.code)
        self.assertIsNotNone(made, "the endpoint is named pe-<app>")
        self.assertEqual(made.group(1), cm.ENDPOINT_API)
        self.assertRegex(self.code, r"resource functionApp 'Microsoft\.Web/sites@" + re.escape(cm.SITE_API) + "'")
        self.assertRegex(self.code, r"resource plan 'Microsoft\.Web/serverfarms@" + re.escape(cm.PLAN_API) + "'")
        self.assertRegex(self.code, r"'Microsoft\.Authorization/roleAssignments@" + re.escape(cm.ASSIGNMENT_API) + "'")


class TheWorkflow(unittest.TestCase):
    def setUp(self):
        self.text = (ROOT / ".github" / "workflows" / "deploy-hub.yml").read_text(encoding="utf-8")
        steps = re.split(r"(?m)^      - ", self.text)[1:]
        (self.block,) = [b for b in steps if b.startswith("name: Clear what is in the way of the deploy of the cases app")]
        self.names = [re.match(r"name: (.+)", b).group(1) for b in steps]
        self.script = "\n".join(line for line in self.block.split("run: |")[1].splitlines() if not line.strip().startswith("#"))

    def test_the_step_runs_the_tool_with_the_files_of_the_deploy_and_nothing_else(self):
        self.assertIn("if: inputs.action == 'cases'", self.block)
        for line in ("FUNCTION_APP: ${{ steps.params.outputs.cases_function_app_name }}", "WANTED_KIND: ${{ steps.params.outputs.cases_app_plan }}", "WANTED_TIER: ${{ steps.params.outputs.cases_plan_tier }}",
                     "OTHER_PLAN: ${{ steps.params.outputs.cases_other_plan_name }}", "OTHER_TIER: ${{ steps.params.outputs.cases_other_plan_tier }}"):
            self.assertIn(line, self.block, line)
        self.assertEqual(re.findall(r"python3 tools/(\S+) (\w+)", self.script), [("cases-move.py", "run")])
        for option in ('--subscription "$ENV_SUBSCRIPTION_ID"', '--resource-group "$ENV_RESOURCE_GROUP"', '--app "$FUNCTION_APP"', '--wanted-kind "$WANTED_KIND"', '--wanted-tier "$WANTED_TIER"',
                       '--other-plan "$OTHER_PLAN"', '--other-tier "$OTHER_TIER"', "--template environment/cases/main.bicep", '--parameters "$RUNNER_TEMP/cases.parameters.json"', '--summary "$GITHUB_STEP_SUMMARY"'):
            self.assertIn(option, self.script, option)
        for word in ("az ", "gh ", "curl", "sleep", "delete"):
            self.assertNotIn(word, self.script, f"the step calls the tool, which does every read and every delete: {word}")

    def test_the_step_is_after_the_check_of_the_subnet_and_before_everything_that_needs_the_ground_clear_and_the_deploy(self):
        title = "Clear what is in the way of the deploy of the cases app (an app and a plan of the other kind, a private endpoint that is Disconnected, role assignments of an identity that is gone)"
        self.assertIn(title, self.names)
        position = self.names.index(title)
        self.assertLess(self.names.index("The function subnet is free for the cases app, which runs on Flex Consumption"), position, "a refusal of the subnet leaves the web page where it was")
        for later in ("Remove what the Flex Consumption version left in the storage account, when it is still there", "Let the cases app go from an integration subnet that is not the one of the template",
                      "Deploy the first cases"):
            self.assertLess(position, self.names.index(later), later)

    def test_the_parameter_file_that_the_tool_previews_is_the_one_that_the_deploy_uses(self):
        deploy = [b for b in re.split(r"(?m)^      - ", self.text)[1:] if b.startswith("name: Deploy the first cases")][0]
        self.assertIn('--parameters "$RUNNER_TEMP/cases.parameters.json"', deploy)
        self.assertIn("--template environment/cases/main.bicep", deploy)

    def test_the_wait_after_the_deploy_is_for_the_zone_group_of_the_new_endpoint_which_an_endpoint_that_was_kept_would_already_have(self):
        steps = re.split(r"(?m)^      - ", self.text)[1:]
        (wait,) = [b for b in steps if b.startswith("name: Wait until the landing zone has registered the cases app's private endpoint in the central zone")]
        self.assertIn("dns-zone-group list", wait)
        self.assertLess(self.names.index("Deploy the first cases"), self.names.index("Wait until the landing zone has registered the cases app's private endpoint in the central zone"))

    def test_the_tool_deletes_only_what_the_docstring_names(self):
        source = (ROOT / "tools" / "cases-move.py").read_text(encoding="utf-8")
        self.assertEqual(len(re.findall(r'"--method", "delete"', source)), 1, "one delete, in one place: Azure.remove")
        self.assertEqual(sorted(re.findall(r"azure\.remove\((\w+), (\w+), ", source)), sorted([("assignment_id", "ASSIGNMENT_API"), ("endpoint_id", "ENDPOINT_API"), ("other_id", "PLAN_API"), ("site_id", "SITE_API")]))
        for word in ("--yes", "az resource delete", "az role assignment delete", "listKeys", "az group delete"):
            self.assertNotIn(word, source, word)


if __name__ == "__main__":
    unittest.main()
