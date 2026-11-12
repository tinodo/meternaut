"""The Power Platform tool (tools/powerplatform.py; docs/proposals/19-teams-cards-through-power-automate.md), run against a fake of the calls that it makes, and of nothing else.

No test here calls Azure or Power Platform, and no test can say that the real services answer as the fake does: the answers are modelled on what a read only call returned on 2026-11-11 (the list of
environments with its linked policy, one environment's detail) and on the reference repository's and Microsoft's own scripts for the calls that change something, which have never been sent by this tool.
What the tests do pin: what the tool sends and to whom, that nothing that changes something is sent without --apply, that a token is never printed and never goes to another host, what each check
before a link stops on, and that every name that the tool shares with a template is the template's."""
import copy
import importlib.util
import io
import json
import re
import sys
import unittest
import urllib.parse
from contextlib import redirect_stderr
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("powerplatform_of_the_tests", ROOT / "tools" / "powerplatform.py")
pp = importlib.util.module_from_spec(spec)
sys.modules["powerplatform_of_the_tests"] = pp  # a dataclass of the tool looks its module up by name
spec.loader.exec_module(pp)

SUB = "11111111-2222-3333-4444-555555555555"
GROUP = "rg-example"
ENV = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
OTHER = "bbbbbbbb-cccc-dddd-eeee-ffffffffffff"
NEW = "cccccccc-dddd-eeee-ffff-000000000000"
SYSTEM_ID = "99999999-8888-7777-6666-555555555555"
POLICY_NAME = "ep-meternaut-netinjection"
POLICY = f"/subscriptions/{SUB}/resourceGroups/{GROUP}/providers/Microsoft.PowerPlatform/enterprisePolicies/{POLICY_NAME}"
OTHER_POLICY = f"/subscriptions/{SUB}/resourceGroups/rg-other/providers/Microsoft.PowerPlatform/enterprisePolicies/ep-other"
NETWORK = f"/subscriptions/{SUB}/resourceGroups/{GROUP}/providers/Microsoft.Network/virtualNetworks/vnet-meternaut"
BAP = "https://api.bap.microsoft.com/providers/Microsoft.BusinessAppPlatform"
BAP_TOKEN = "bap-token-0123456789"
ARM_TOKEN = "arm-token-9876543210"
FLOW_TOKEN = "flow-token-1122334455"
TENANT = "dddddddd-1111-2222-3333-444444444444"
ACCOUNT = "stmeternautexample"
OPERATION = f"{BAP}/operations/op-1"
REGIONAL_OPERATION = "https://unitedstates.api.bap.microsoft.com/providers/Microsoft.BusinessAppPlatform/operations/op-1"


def environment(env_id=ENV, name="cards", location="sweden", region="swedencentral", sku="Developer", managed="Standard", state="Succeeded", management="Ready", policy=None, instance="https://org.invalid/"):
    properties = {"displayName": name, "environmentSku": sku, "azureRegion": region, "provisioningState": state, "states": {"management": {"id": management}}, "tenantId": TENANT,
                  "governanceConfiguration": {"protectionLevel": managed}, "linkedEnvironmentMetadata": {"instanceUrl": instance} if instance else {}}
    if policy:
        properties["enterprisePolicies"] = {"VNets": {"id": policy, "linkStatus": "Linked"}}
    return {"name": env_id, "location": location, "properties": properties}


class World:
    """The services, as far as this tool talks to them: environments, an enterprise policy, a subnet and the operations that a 202 names."""

    def __init__(self, **changes):
        self.now = 0.0
        self.calls = []
        self.audiences = []
        self.admin = True
        self.environments = {ENV: environment()}
        self.policy_status = 200
        self.policy = {"id": POLICY, "kind": "NetworkInjection", "location": "sweden", "properties": {"systemId": SYSTEM_ID, "networkInjection": {"virtualNetworks": [{"id": NETWORK, "subnet": {"name": "snet-powerplatform"}}]}}}
        self.subnet = {"properties": {"addressPrefix": "10.53.0.96/27", "delegations": [{"properties": {"serviceName": "Microsoft.PowerPlatform/enterprisePolicies"}}]}}
        self.operation_states = ["Running", "Succeeded"]
        self.operation_url = OPERATION
        self.operation_error = None
        self.reads_before_ready = 2
        self.creating = None
        self.link_takes_effect = True
        self.connections = {}
        self.consents = []
        self.flows = {}
        self.runs = {}
        self.run_outcome = ("Succeeded", [])
        self.flow_counter = 0
        self.__dict__.update(changes)

    # the Azure CLI
    def runner(self, args):
        assert args[:2] == ["account", "get-access-token"] and "--resource" in args, args
        audience = args[args.index("--resource") + 1]
        self.audiences.append(audience)
        return 0, (BAP_TOKEN if "powerapps" in audience else FLOW_TOKEN if "flow.microsoft" in audience else ARM_TOKEN) + "\n", ""

    def sleep(self, seconds):
        self.now += seconds

    def clock(self):
        return self.now

    # the transport
    def transport(self, method, url, headers, body):
        payload = json.loads(body) if body else None
        self.calls.append((method, url, payload))
        token = headers["Authorization"].removeprefix("Bearer ")
        host = url.split("/")[2]
        platform = host in ("api.bap.microsoft.com", "api.powerapps.com") or host.endswith(".api.bap.microsoft.com")
        assert token == (FLOW_TOKEN if host == "api.flow.microsoft.com" else BAP_TOKEN if platform else ARM_TOKEN), "a token goes to its own host only"
        path = url.split("?")[0]
        if host == "management.azure.com":
            return self.arm(method, path)
        if host == "api.powerapps.com":
            return self.apps(method, path, url, payload)
        if host == "api.flow.microsoft.com":
            return self.flow_service(method, urllib.parse.urlsplit(url).path, payload)
        return self.bap(method, path.replace(host, "api.bap.microsoft.com", 1), payload)

    def apps(self, method, path, url, payload):
        assert f"environment%20eq%20%27{ENV}%27" in url, "the connections are asked for in one environment"
        if method == "GET" and path.endswith("/providers/Microsoft.PowerApps/connections"):
            return 200, {}, json.dumps({"value": list(self.connections.values())}).encode()
        found = re.fullmatch(r".*/apis/(shared_[a-z]+)/connections/([0-9a-f]{32})(/getConsentLink)?", path)
        if not found:
            return 500, {}, b"the fake has no such route: " + path.encode()
        api, name, consent = found.groups()
        if method == "PUT":
            self.connections[name] = {"name": name, "properties": {"apiId": f"/providers/Microsoft.PowerApps/apis/{api}", "statuses": [{"status": "Error", "error": {"code": "Unauthenticated"}}], "request": payload}}
            return 200, {}, json.dumps(self.connections[name]).encode()
        if method == "POST" and consent:
            self.consents.append((api, name, payload))
            return 200, {}, json.dumps({"consentLink": f"https://sweden-001.consent.azure-apihub.net/login?data={name}", "redirectUrl": payload["redirectUrl"]}).encode()
        return 500, {}, b"the fake has no such call: " + method.encode() + b" " + path.encode()

    def flow_service(self, method, path, payload):
        root = f"/providers/Microsoft.ProcessSimple/environments/{ENV}/flows"
        assert path.startswith(root), "the flows are asked for in one environment"
        tail = path.removeprefix(root)
        if tail == "" and method == "GET":
            return 200, {}, json.dumps({"value": list(self.flows.values())}).encode()
        if tail == "" and method == "POST":
            self.flow_counter += 1
            flow_id = f"00000000-0000-0000-0000-{self.flow_counter:012d}"
            self.flows[flow_id] = {"name": flow_id, "properties": {**payload["properties"], "flowSuspensionReason": "None"}}
            return 200, {}, json.dumps(self.flows[flow_id]).encode()
        found = re.fullmatch(r"/([0-9a-f-]{36})(?:/(triggers/manual/run|runs|runs/[0-9A-Za-z]+))?", tail)
        if not found or found.group(1) not in self.flows:
            return 404, {}, b'{"error": {"code": "NotFound", "message": "no such flow"}}'
        flow_id, rest = found.groups()
        if rest is None and method == "PATCH":
            self.flows[flow_id]["properties"].update(payload["properties"])
            return 200, {}, json.dumps(self.flows[flow_id]).encode()
        if rest is None and method == "DELETE":
            del self.flows[flow_id]
            return 200, {}, b""
        if rest == "triggers/manual/run" and method == "POST":
            self.add_run(flow_id, *self.run_outcome)
            return 200, {}, b""
        if rest == "runs" and method == "GET":
            return 200, {}, json.dumps({"value": [{k: v for k, v in r.items() if k != "codes"} for r in self.runs.get(flow_id, [])]}).encode()
        if rest and rest.startswith("runs/") and method == "GET":
            run = next(r for r in self.runs[flow_id] if r["name"] == rest.removeprefix("runs/"))
            return 200, {}, json.dumps({"properties": {"actions": {f"action{i}": {"status": "Failed", "code": code} for i, code in enumerate(run["codes"], 1)}}}).encode()
        return 500, {}, b"the fake has no such call: " + method.encode() + b" " + path.encode()

    def add_run(self, flow_id, status, codes=()):
        runs = self.runs.setdefault(flow_id, [])
        runs.append({"name": f"run{len(runs) + 1}", "properties": {"startTime": f"2026-11-11T19:{len(runs):02d}:00Z", "status": status, "code": ""}, "codes": list(codes)})

    def sign_in(self, *apis):
        """The connections that a person has made and signed in, as the connections endpoint lists them."""
        for api in apis:
            name = "%032x" % (len(self.connections) + 1)
            self.connections[name] = {"name": name, "properties": {"apiId": f"/providers/Microsoft.PowerApps/apis/{api}", "statuses": [{"status": "Connected"}]}}

    def bap(self, method, path, payload):
        admin = "/scopes/admin/" in path
        short = path.removeprefix(BAP)
        if method == "GET" and re.fullmatch(r"(/scopes/admin)?/environments", short):
            if admin and not self.admin:
                return 403, {}, b'{"error": {"code": "Forbidden", "message": "not an administrator"}}'
            return 200, {}, json.dumps({"value": list(self.environments.values())}).encode()
        found = re.fullmatch(r"(?:/scopes/admin)?/environments/([0-9a-f-]{36})", short)
        if method == "GET" and found:
            if admin and not self.admin:
                return 403, {}, b'{"error": {"code": "Forbidden", "message": "not an administrator"}}'
            if found.group(1) == self.creating:
                self.reads_before_ready -= 1
                self.environments[NEW] = environment(NEW, "new one", state="Succeeded" if self.reads_before_ready < 0 else "Provisioning", management="Ready" if self.reads_before_ready < 0 else "NotSpecified",
                                                     instance="https://org.invalid/" if self.reads_before_ready < 0 else None, sku="Developer", managed="Basic")
            environment_found = self.environments.get(found.group(1))
            return (200, {}, json.dumps(environment_found).encode()) if environment_found else (404, {}, b'{"error": {"code": "NotFound", "message": "no such environment"}}')
        if method == "POST" and short == "/environments":
            self.creating = NEW
            self.created = payload
            return 202, {"Location": OPERATION}, b""
        if method == "GET" and path == OPERATION:
            state = self.operation_states.pop(0) if len(self.operation_states) > 1 else self.operation_states[0]
            body = {"state": {"id": state}}
            if state == "Succeeded":
                body["links"] = {"environment": {"path": f"/providers/Microsoft.BusinessAppPlatform/scopes/admin/environments/{NEW}"}}
            if state == "Failed":
                body["error"] = {"message": self.operation_error or "no detail"}
                if self.operation_error is None:
                    body.pop("error")
            return 200, {"Retry-After": "7"}, json.dumps(body).encode()
        found = re.fullmatch(r"/environments/([0-9a-f-]{36})/governanceConfiguration", short)
        if method == "POST" and found:
            self.environments[found.group(1)]["properties"]["governanceConfiguration"] = {"protectionLevel": payload["protectionLevel"]}
            return 200, {}, b""
        found = re.fullmatch(r"/environments/([0-9a-f-]{36})/enterprisePolicies/NetworkInjection/(link|unlink)", short)
        if method == "POST" and found:
            self.last_link = (found.group(1), found.group(2), payload)
            if self.link_takes_effect:
                properties = self.environments[found.group(1)]["properties"]
                if found.group(2) == "link":
                    properties["enterprisePolicies"] = {"VNets": {"id": POLICY, "linkStatus": "Linked"}}
                else:
                    properties.pop("enterprisePolicies", None)
            return 202, {"operation-location": self.operation_url, "Retry-After": "7"}, b""
        return 500, {}, b"the fake has no such route: " + path.encode()

    def arm(self, method, path):
        if method != "GET":
            return 500, {}, b"nothing is written to Azure"
        if "/enterprisePolicies/" in path:
            if self.policy_status != 200:
                return self.policy_status, {}, json.dumps({"error": {"code": "AuthorizationFailed" if self.policy_status == 403 else "ResourceNotFound", "message": "no"}}).encode()
            return 200, {}, json.dumps(self.policy).encode()
        if "/subnets/" in path:
            return 200, {}, json.dumps(self.subnet).encode()
        return 500, {}, b"no route"

    # the tool
    def run(self, argv, answers=None, env=None, **kw):
        lines, errors = [], io.StringIO()
        asked = []

        def ask(prompt):
            asked.append(prompt)
            return None if answers is None else answers.pop(0)
        with redirect_stderr(errors):
            code = pp.main(argv, runner=self.runner, transport=self.transport, sleep=self.sleep, out=lines.append, ask=ask, env={} if env is None else env, clock=self.clock, **kw)
        self.asked = asked
        return code, "\n".join(lines), errors.getvalue()

    def changes(self):
        return [(m, u.split("?")[0].removeprefix(BAP)) for m, u, _ in self.calls if m != "GET"]


LINK = ["link", "--environment", ENV, "--subscription", SUB, "--resource-group", GROUP]


def connections_used(actions):
    """The connections that the steps of a flow use, in a condition too."""
    found = set()
    for action in actions.values():
        inputs = action.get("inputs")
        found.add(inputs.get("host", {}).get("connectionName") if isinstance(inputs, dict) else None)
        found |= connections_used(action.get("actions", {})) | connections_used(action.get("else", {}).get("actions", {}))
    return found - {None}


class Status(unittest.TestCase):
    def test_it_lists_what_the_signed_in_person_sees_with_region_type_managed_state_and_the_linked_policy(self):
        world = World()
        world.environments[OTHER] = environment(OTHER, "linked one", location="europe", region="northeurope", sku="Sandbox", managed="Standard", policy=OTHER_POLICY)
        code, out, err = world.run(["status", "--subscription", SUB, "--resource-group", GROUP])
        self.assertEqual((code, err), (0, ""))
        self.assertIn("2 environment(s) that this sign-in sees (every environment of the tenant)", out)
        self.assertRegex(out, r"cards\s+sweden \(swedencentral\)\s+Developer\s+Standard\s+Succeeded\s+none")
        self.assertRegex(out, r"linked one\s+europe \(northeurope\)\s+Sandbox\s+Standard\s+Succeeded\s+ep-other \[Linked\]")
        self.assertEqual(world.changes(), [])

    def test_a_person_who_is_not_an_administrator_sees_their_own_and_is_told(self):
        world = World(admin=False)
        code, out, _ = world.run(["status"])
        self.assertEqual(code, 0)
        self.assertIn("only its own: the sign-in is not a Power Platform administrator", out)
        self.assertIn("cards", out)

    def test_for_one_environment_it_says_whether_the_projects_policy_is_linked_and_reads_the_policy_and_its_subnet(self):
        world = World()
        world.environments[ENV] = environment(policy=POLICY)
        code, out, _ = world.run(["status", "--environment", "cards", "--subscription", SUB, "--resource-group", GROUP])
        self.assertEqual(code, 0)
        self.assertIn("the project's policy ep-meternaut-netinjection: kind NetworkInjection, geography sweden, 1 virtual network(s)", out)
        self.assertIn("subnet snet-powerplatform: 10.53.0.96/27, delegated to Microsoft.PowerPlatform/enterprisePolicies", out)
        self.assertIn("linked to the project's policy: YES", out)
        self.assertIn("ep-meternaut-netinjection (this project) [Linked]", out)

    def test_an_environment_that_is_linked_to_another_policy_or_to_none_is_not_the_projects(self):
        world = World()
        code, out, _ = world.run(["status", "--environment", ENV, "--subscription", SUB, "--resource-group", GROUP])
        self.assertIn("linked to the project's policy: NO", out)
        world.environments[ENV] = environment(policy=OTHER_POLICY)
        code, out, _ = world.run(["status", "--environment", ENV, "--subscription", SUB, "--resource-group", GROUP])
        self.assertIn("linked to the project's policy: NO (it is linked to ep-other)", out)

    def test_without_a_subscription_it_says_what_it_needs_to_read_the_policy(self):
        code, out, _ = World().run(["status", "--environment", "cards"])
        self.assertEqual(code, 0)
        self.assertIn("Give --subscription and --resource-group", out)

    def test_a_policy_that_is_not_there_and_one_that_cannot_be_read_are_said_in_plain_words(self):
        for status, words in ((404, "is not in resource group"), (403, "needs Reader on it")):
            code, out, _ = World(policy_status=status).run(["status", "--environment", ENV, "--subscription", SUB, "--resource-group", GROUP])
            self.assertEqual(code, 1)
            self.assertIn(words, out)

    def test_two_environments_with_one_name_and_a_name_nobody_has_are_refused(self):
        world = World()
        world.environments[OTHER] = environment(OTHER, "cards")
        code, _, err = world.run(["status", "--environment", "cards"])
        self.assertEqual(code, 1)
        self.assertIn("2 environments are named 'cards'", err)
        code, _, err = world.run(["status", "--environment", "nobody"])
        self.assertIn("no environment is named 'nobody'", err)


class CreateEnvironment(unittest.TestCase):
    ARGS = ["create-environment", "--name", "new one"]

    def test_a_dry_run_says_what_it_would_make_and_sends_nothing_that_changes_anything(self):
        world = World()
        code, out, _ = world.run(self.ARGS)
        self.assertEqual(code, 0)
        self.assertIn("Would make the environment new one: type Developer, location sweden, Dataverse, EUR, language 1033, domain new-one.", out)
        self.assertIn("from 15 November 2026 an unmanaged developer environment can not be made", out)
        self.assertIn("This was a dry run.", out)
        self.assertEqual(world.changes(), [])

    def test_with_apply_it_makes_the_environment_waits_for_the_operation_and_for_ready_and_says_what_comes_next(self):
        world = World()
        code, out, err = world.run([*self.ARGS, "--apply", "--yes"])
        self.assertEqual((code, err), (0, ""))
        self.assertEqual(world.changes(), [("POST", "/environments")])
        self.assertEqual(world.created, {"location": "sweden", "properties": {
            "displayName": "new one", "description": "Made by tools/powerplatform.py for the Meternaut Teams cards.", "environmentSku": "Developer", "databaseType": "CommonDataService",
            "linkedEnvironmentMetadata": {"baseLanguage": 1033, "currency": {"code": "EUR"}, "domainName": "new-one"}}})
        self.assertIn("making the environment: Running", out)
        self.assertIn("making the environment: Succeeded", out)
        self.assertIn("Provisioning, NotSpecified, no Dataverse yet", out)
        self.assertIn(f"The environment new one is Ready (id {NEW}", out)
        self.assertIn("Next: `managed`", out)
        self.assertGreaterEqual(world.now, 7, "it waited as the operation said (Retry-After)")

    def test_an_environment_with_the_same_name_is_left_alone(self):
        world = World()
        code, out, _ = world.run(["create-environment", "--name", "CARDS", "--apply", "--yes"])
        self.assertEqual(code, 0)
        self.assertIn("An environment named CARDS exists already (type Developer, sweden, Managed Environment Standard). Nothing is made.", out)
        self.assertEqual(world.changes(), [])

    def test_a_sandbox_is_the_other_type_and_nothing_else_is_taken(self):
        world = World()
        world.run(["create-environment", "--name", "box", "--sku", "Sandbox", "--apply", "--yes"])
        self.assertEqual(world.created["properties"]["environmentSku"], "Sandbox")
        for argv in (["create-environment", "--name", "x1", "--sku", "Trial"], ["create-environment", "--name", "x1", "--region", "europe"]):
            with self.assertRaises(SystemExit), redirect_stderr(io.StringIO()):
                World().run(argv)

    def test_a_failed_operation_and_one_that_does_not_end_are_reported_and_a_refusal_too(self):
        world = World(operation_states=["Failed"], operation_error="The domain name is taken.")
        code, _, err = world.run([*self.ARGS, "--apply", "--yes"])
        self.assertEqual(code, 1)
        self.assertIn("making the environment failed: The domain name is taken.", err)
        world = World(operation_states=["Running"])
        code, _, err = world.run([*self.ARGS, "--apply", "--yes"])
        self.assertEqual(code, 1)
        self.assertIn("did not end in 30 minutes", err)

    def test_it_asks_first_unless_it_is_told_not_to(self):
        world = World()
        code, _, err = world.run([*self.ARGS, "--apply"], answers=["no"])
        self.assertEqual(code, 1)
        self.assertIn("nothing was changed", err)
        self.assertEqual(world.changes(), [])
        code, _, err = World().run([*self.ARGS, "--apply"], answers=None)
        self.assertIn("--apply needs --yes when there is no terminal to ask in", err)

    def test_the_names_are_checked_before_anything_is_sent(self):
        world = World()
        for argv in (["create-environment", "--name=-bad"], ["create-environment", "--name", "good name", "--domain-name", "Bad_Domain"]):
            code, _, err = world.run(argv)
            self.assertEqual(code, 1, argv)
            self.assertEqual(world.calls, [])


class Managed(unittest.TestCase):
    def test_a_dry_run_changes_nothing_and_a_managed_environment_is_left_alone(self):
        world = World()
        world.environments[ENV] = environment(managed="Basic")
        code, out, _ = world.run(["managed", "--environment", ENV])
        self.assertEqual(code, 0)
        self.assertIn("This was a dry run.", out)
        self.assertIn("whoever runs a flow in it needs a premium licence", out)
        self.assertEqual(world.changes(), [])
        world = World()
        code, out, _ = world.run(["managed", "--environment", ENV, "--apply", "--yes"])
        self.assertIn("It is a Managed Environment already. Nothing is changed.", out)
        self.assertEqual(world.changes(), [])

    def test_with_apply_it_sends_the_body_that_learn_gives_and_reads_the_environment_again(self):
        world = World()
        world.environments[ENV] = environment(managed="Basic")
        code, out, _ = world.run(["managed", "--environment", ENV, "--apply", "--yes"])
        self.assertEqual(code, 0)
        post = [(u, b) for m, u, b in world.calls if m == "POST"]
        self.assertEqual(post, [(f"{BAP}/environments/{ENV}/governanceConfiguration?api-version=2021-04-01", {"protectionLevel": "Standard", "settings": {"extendedSettings": {}}})])
        self.assertIn("Read again: Managed Environment Standard.", out)

    def test_an_environment_type_that_virtual_network_support_does_not_cover_is_refused(self):
        world = World()
        world.environments[ENV] = environment(sku="Trial", managed="Basic")
        code, _, err = world.run(["managed", "--environment", ENV, "--apply", "--yes"])
        self.assertEqual(code, 1)
        self.assertIn("does not support virtual network support", err)
        self.assertEqual(world.changes(), [])


class Link(unittest.TestCase):
    def test_a_dry_run_makes_every_check_names_what_it_would_send_and_sends_nothing_that_changes_anything(self):
        world = World()
        code, out, err = world.run(LINK)
        self.assertEqual((code, err), (0, ""))
        for words in ("ok  the environment is not linked to any policy", "ok  the environment is in the geography sweden (swedencentral)", "ok  the environment type Developer supports it",
                      "ok  the environment is a Managed Environment", "ok  the policy ep-meternaut-netinjection can be read with this sign-in",
                      "ok  the policy is a NetworkInjection policy of the geography Sweden with one virtual network and a systemId",
                      "ok  the subnet snet-powerplatform (10.53.0.96/27) is delegated to Microsoft.PowerPlatform/enterprisePolicies, and has room", "up to 30 minutes", "This was a dry run."):
            self.assertIn(words, out)
        self.assertEqual(world.changes(), [])

    def test_with_apply_it_sends_the_policys_system_id_to_the_link_address_waits_and_reads_the_environment_again(self):
        world = World()
        code, out, err = world.run([*LINK, "--apply", "--yes"])
        self.assertEqual((code, err), (0, ""))
        self.assertEqual(world.changes(), [("POST", f"/environments/{ENV}/enterprisePolicies/NetworkInjection/link")])
        posted = [(u, b) for m, u, b in world.calls if m == "POST"]
        self.assertEqual(posted, [(f"{BAP}/environments/{ENV}/enterprisePolicies/NetworkInjection/link?api-version=2019-10-01", {"SystemId": SYSTEM_ID})])
        self.assertIn("the link: Running", out)
        self.assertIn("the link: Succeeded", out)
        self.assertIn(f"Read again: the environment is linked to {pp.DEFAULT_POLICY_NAME} [Linked].", out)
        self.assertIn("Next: import the solution", out)

    def test_it_asks_for_a_yes_unless_told_not_to_and_a_no_changes_nothing(self):
        world = World()
        code, _, err = world.run([*LINK, "--apply"], answers=["no"])
        self.assertEqual(code, 1)
        self.assertEqual(world.changes(), [])
        self.assertTrue(world.asked[0].startswith("Link cards?"))
        world = World()
        code, _, err = world.run([*LINK, "--apply"], answers=["yes"])
        self.assertEqual(code, 0)
        self.assertEqual(len(world.changes()), 1)

    def test_an_environment_that_is_linked_already_is_left_alone_and_one_linked_to_another_policy_is_not_swapped(self):
        world = World()
        world.environments[ENV] = environment(policy=POLICY)
        code, out, _ = world.run([*LINK, "--apply", "--yes"])
        self.assertEqual(code, 0)
        self.assertIn("linked to the project's policy already", out)
        self.assertEqual(world.changes(), [])
        world.environments[ENV] = environment(policy=OTHER_POLICY)
        code, _, err = world.run([*LINK, "--apply", "--yes"])
        self.assertEqual(code, 1)
        self.assertIn("linked to ep-other: this tool does not swap a policy", err)
        self.assertEqual(world.changes(), [])

    def test_each_check_stops_the_link_before_anything_is_sent_and_says_what_to_do(self):
        cases = [
            ("another geography", dict(environments={ENV: environment(location="europe", region="northeurope")}), "is in europe, and the project's policy is for the geography sweden"),
            ("another region", dict(environments={ENV: environment(region="northeurope")}), "the environment runs in northeurope"),
            ("a trial", dict(environments={ENV: environment(sku="Trial")}), "does not support virtual network support"),
            ("not managed", dict(environments={ENV: environment(managed="Basic")}), "run `managed` first"),
            ("not ready", dict(environments={ENV: environment(state="Provisioning")}), "is not ready"),
            ("no right on the policy", dict(policy_status=403), "needs Reader on it"),
            ("no policy", dict(policy_status=404), "the Hub action powerplatform makes it"),
            ("wrong kind", dict(policy={"id": POLICY, "kind": "Encryption", "location": "sweden", "properties": {"systemId": SYSTEM_ID}}), "not NetworkInjection"),
            ("wrong geography", dict(policy={"id": POLICY, "kind": "NetworkInjection", "location": "europe", "properties": {"systemId": SYSTEM_ID, "networkInjection": {"virtualNetworks": [{"id": NETWORK, "subnet": {"name": "s"}}]}}}), "not sweden"),
            ("two networks", dict(policy={"id": POLICY, "kind": "NetworkInjection", "location": "sweden", "properties": {"systemId": SYSTEM_ID, "networkInjection": {"virtualNetworks": [{"id": NETWORK, "subnet": {"name": "s"}}, {"id": NETWORK, "subnet": {"name": "t"}}]}}}), "2 virtual networks"),
            ("no system id yet", dict(policy={"id": POLICY, "kind": "NetworkInjection", "location": "sweden", "properties": {"networkInjection": {"virtualNetworks": [{"id": NETWORK, "subnet": {"name": "s"}}]}}}), "no systemId yet"),
            ("a subnet that is not delegated", dict(subnet={"properties": {"addressPrefix": "10.53.0.96/27", "delegations": []}}), "delegated to nothing"),
            ("a subnet delegated to something else", dict(subnet={"properties": {"addressPrefix": "10.53.0.96/27", "delegations": [{"properties": {"serviceName": "Microsoft.Web/serverFarms"}}]}}), "Microsoft.Web/serverFarms"),
            ("a subnet that is too small", dict(subnet={"properties": {"addressPrefix": "10.53.0.96/29", "delegations": [{"properties": {"serviceName": "Microsoft.PowerPlatform/enterprisePolicies"}}]}}), "fewer than 11 addresses"),
        ]
        for label, changes, words in cases:
            world = World(**changes)
            code, out, err = world.run([*LINK, "--apply", "--yes"])
            self.assertEqual(code, 1, label)
            self.assertIn(words, err, label)
            self.assertEqual(world.changes(), [], label)

    def test_a_failed_link_and_an_environment_that_does_not_show_the_policy_are_not_reported_as_done(self):
        world = World(operation_states=["Failed"], operation_error="The subnet is in use.")
        code, _, err = world.run([*LINK, "--apply", "--yes"])
        self.assertEqual(code, 1)
        self.assertIn("the link failed: The subnet is in use.", err)
        world = World(link_takes_effect=False)
        code, out, _ = world.run([*LINK, "--apply", "--yes"])
        self.assertEqual(code, 1)
        self.assertIn("does not report the policy yet", out)

    def test_the_operation_that_the_platform_names_on_its_regional_host_is_followed_with_the_platform_token(self):
        world = World(operation_url=REGIONAL_OPERATION)
        code, out, err = world.run([*LINK, "--apply", "--yes"])
        self.assertEqual((code, err), (0, ""))
        self.assertIn(("GET", REGIONAL_OPERATION, None), world.calls)
        self.assertIn("the link: Succeeded", out)

    def test_an_operation_that_is_not_followed_after_an_accepted_link_says_that_the_link_was_accepted(self):
        world = World(operation_url="https://evil.example/providers/Microsoft.BusinessAppPlatform/operations/op-1")
        code, _, err = world.run([*LINK, "--apply", "--yes"])
        self.assertEqual(code, 1)
        self.assertIn("is not the Business Application Platform", err)
        self.assertIn("The link itself was accepted: run `status`", err)
        self.assertEqual([u for _, u, _ in world.calls if "evil.example" in u], [])

    def test_a_policy_in_another_resource_group_than_the_one_named_is_not_taken_for_the_projects(self):
        world = World()
        world.environments[ENV] = environment(policy=OTHER_POLICY)
        code, _, err = world.run(["unlink", "--environment", ENV, "--subscription", SUB, "--resource-group", GROUP, "--apply", "--yes"])
        self.assertEqual(code, 1)
        self.assertIn("this tool unlinks only its own", err)
        self.assertEqual(world.changes(), [])


class Unlink(unittest.TestCase):
    def test_it_unlinks_the_projects_policy_only_after_a_yes_and_reads_the_environment_again(self):
        world = World()
        world.environments[ENV] = environment(policy=POLICY)
        code, out, _ = world.run(["unlink", "--environment", ENV, "--subscription", SUB, "--resource-group", GROUP])
        self.assertEqual((code, world.changes()), (0, []))
        self.assertIn("This was a dry run.", out)
        code, out, err = world.run(["unlink", "--environment", ENV, "--subscription", SUB, "--resource-group", GROUP, "--apply", "--yes"])
        self.assertEqual((code, err), (0, ""))
        self.assertEqual(world.changes(), [("POST", f"/environments/{ENV}/enterprisePolicies/NetworkInjection/unlink")])
        self.assertEqual(world.last_link, (ENV, "unlink", {"SystemId": SYSTEM_ID}))
        self.assertIn("Read again: the environment is not linked.", out)

    def test_an_environment_that_is_not_linked_has_nothing_to_unlink(self):
        world = World()
        code, out, _ = world.run(["unlink", "--environment", ENV, "--subscription", SUB, "--resource-group", GROUP, "--apply", "--yes"])
        self.assertEqual(code, 0)
        self.assertIn("not linked to a policy. Nothing is changed.", out)
        self.assertEqual(world.changes(), [])


class Steps(unittest.TestCase):
    def test_it_prints_every_step_in_order_with_the_exact_commands_and_sends_nothing(self):
        world = World()
        code, out, _ = world.run(["steps", "--subscription", SUB, "--resource-group", GROUP, "--storage-account", "stexample", "--environment", "cards", "--person", "22222222-3333-4444-5555-666666666666"])
        self.assertEqual(code, 0)
        self.assertEqual(world.calls, [])
        self.assertEqual(world.audiences, [], "not even a token is asked for")
        numbers = [int(n) for n in re.findall(r"(?m)^\s{1,2}(\d{1,2})\. ", out)]
        self.assertEqual(numbers, list(range(1, 19)))
        for words in ("connections --environment", "flow --environment", "test-card --environment", "test-close --environment", "flow-runs --environment", "You are not permitted to make flows in this environment"):
            self.assertIn(words, out)
        queue = f"/subscriptions/{SUB}/resourceGroups/{GROUP}/providers/Microsoft.Storage/storageAccounts/stexample/queueServices/default/queues/teams-cards"
        self.assertIn(f'az role assignment create --assignee-object-id 22222222-3333-4444-5555-666666666666 --assignee-principal-type User --role "Storage Queue Data Message Processor" --scope {queue}', out)
        self.assertIn(f'--role "Storage Queue Data Message Sender" --scope {queue.removesuffix("teams-cards")}teams-posted', out, "the flow writes to the queue of the posted cards: one more role of the person, on that queue only")
        self.assertIn("TEAMS_CARDS_QUEUE and TEAMS_POSTED_QUEUE", out)
        self.assertIn(f"--role Reader --scope {POLICY}", out)
        self.assertIn("az provider show --namespace Microsoft.PowerPlatform", out)
        for command in ("create-environment --name cards --sku Developer --apply", "managed --environment cards --apply", "link --environment cards", "status --environment cards"):
            self.assertIn(command, out)
        for words in ("Storage queue endpoint: https://stexample.queue.core.windows.net/", "Queue name: teams-cards", "Posted queue name: teams-posted", "Microsoft Entra ID Integrated", "turn it on", "Put a message on a queue (V2)", "https://admin.teams.microsoft.com/policies/manage-apps",
                      "az ad signed-in-user show --query id --output tsv", f"az storage account list --resource-group {GROUP}", "second connection reference"):
            self.assertIn(words, out)
        order = ["Start the action cases once more", "Start the action powerplatform", "az role assignment create", "--role Reader", "manage-apps", "create-environment", "managed --environment", "link --environment", "status --environment",
                 "Import solution", "Storage queue endpoint:", "save it and turn it on", "The first card"]
        positions = [out.index(words) for words in order]
        self.assertEqual(positions, sorted(positions), "the steps come in the order of the proposal: the Hub, the roles, Teams, the environment, the link, the import, the connections, the flow, the first card")
        self.assertLess(out.index("Import solution"), out.index("turn it on"))

    def test_without_arguments_it_prints_placeholders_and_no_id(self):
        code, out, _ = World().run(["steps"])
        self.assertEqual(code, 0)
        for placeholder in ("<subscription id>", "<resource group>", "<storage account>", "<environment name>", "<object id of the person whose connection reads the queue>"):
            self.assertIn(placeholder, out)
        self.assertIsNone(re.search(pp.GUID, out))

    def test_the_test_message_in_the_steps_is_a_message_of_the_format_that_the_flow_reads(self):
        out = World().run(["steps"])[1]
        message = json.loads(re.search(r"the JSON text (\{.*\})\. Run it", out).group(1))
        self.assertEqual(sorted(message), ["card", "id", "title", "to", "v"])
        self.assertEqual(message["v"], 1)
        self.assertEqual(message["card"]["type"], "AdaptiveCard")


class TheConnectionsAndTheFlow(unittest.TestCase):
    """What a person does when the maker portal refuses them (a B2B guest of the tenant): the same calls, made by the tool."""
    ARGS = ["--environment", ENV]

    def test_the_dry_run_of_connections_says_what_is_missing_and_changes_nothing(self):
        world = World()
        code, out, err = world.run(["connections", *self.ARGS])
        self.assertEqual((code, err), (0, ""))
        self.assertIn("--  Azure Queues (Microsoft Entra ID Integrated): not made", out)
        self.assertIn("--  Microsoft Teams: not made", out)
        self.assertIn("This was a dry run.", out)
        self.assertEqual((world.changes(), world.connections), ([], {}))

    def test_apply_makes_each_missing_connection_with_the_entra_sign_in_for_the_queue_and_gives_both_addresses_and_the_guest_hint(self):
        world = World()
        code, out, err = world.run(["connections", *self.ARGS, "--apply", "--yes"])
        self.assertEqual((code, err), (0, ""))
        made = {c["properties"]["apiId"].rsplit("/", 1)[-1]: c["properties"]["request"]["properties"] for c in world.connections.values()}
        self.assertEqual(sorted(made), ["shared_azurequeues", "shared_teams"])
        self.assertEqual(made["shared_azurequeues"]["connectionParametersSet"], {"name": "tokenBasedAuth", "values": {}})
        self.assertEqual(made["shared_teams"]["connectionParameters"], {})
        for properties in made.values():
            self.assertEqual(properties["environment"], {"id": f"/providers/Microsoft.PowerApps/environments/{ENV}", "name": ENV})
        self.assertEqual(sorted(api for api, _, _ in world.consents), ["shared_azurequeues", "shared_teams"])
        self.assertTrue(all(payload == {"redirectUrl": pp.CONSENT_RETURN} for _, _, payload in world.consents))
        self.assertEqual(out.count("https://sweden-001.consent.azure-apihub.net/login?data="), 2)
        self.assertIn("#EXT#", out)
        self.assertIn("/common/", out)
        self.assertIn(TENANT, out)

    def test_a_connection_that_is_made_and_not_signed_in_gets_a_new_address_and_no_second_connection(self):
        world = World()
        world.run(["connections", *self.ARGS, "--apply", "--yes"])
        made = sorted(world.connections)
        code, out, _ = world.run(["connections", *self.ARGS, "--apply", "--yes"])
        self.assertEqual((code, sorted(world.connections)), (0, made))
        self.assertIn("made, and not signed in", out)
        self.assertEqual(len(world.consents), 4)
        world.connections = {}
        world.sign_in("shared_azurequeues", "shared_teams")
        code, out, _ = world.run(["connections", *self.ARGS])
        self.assertIn("Both are connected.", out)

    def test_the_flow_needs_both_connections_connected_and_says_what_to_run(self):
        world = World()
        world.sign_in("shared_teams")
        code, _, err = world.run(["flow", *self.ARGS, "--storage-account", ACCOUNT])
        self.assertEqual(code, 1)
        self.assertIn("Azure Queues", err)
        self.assertIn("run `connections --apply`", err)

    def test_the_flow_is_made_from_the_definition_of_the_solution_with_the_three_values_and_the_two_connections(self):
        world = World()
        world.sign_in("shared_azurequeues", "shared_teams")
        code, out, err = world.run(["flow", *self.ARGS, "--storage-account", ACCOUNT, "--apply", "--yes"])
        self.assertEqual((code, err), (0, ""))
        self.assertIn("by a message on the queue teams-posted", out)
        (flow,) = world.flows.values()
        properties = flow["properties"]
        self.assertEqual((properties["displayName"], properties["state"]), (pp.FLOW_NAME, "Started"))
        names = {c["properties"]["apiId"].rsplit("/", 1)[-1]: c["name"] for c in world.connections.values()}
        self.assertEqual({k: (v["connectionName"], v["source"], v["id"]) for k, v in properties["connectionReferences"].items()},
                         {api: (names[api], "Embedded", f"/providers/Microsoft.PowerApps/apis/{api}") for api in ("shared_azurequeues", "shared_teams")})
        self.assertEqual({k: v["tier"] for k, v in properties["connectionReferences"].items()}, {"shared_azurequeues": "Premium", "shared_teams": "Standard"})
        expected = copy.deepcopy(pp.flow_definition())
        expected["parameters"][pp.ENDPOINT_PARAMETER]["defaultValue"] = f"https://{ACCOUNT}.queue.core.windows.net/"
        expected["parameters"][pp.QUEUE_PARAMETER]["defaultValue"] = "teams-cards"
        expected["parameters"][pp.POSTED_PARAMETER]["defaultValue"] = "teams-posted"
        self.assertEqual(properties["definition"], expected)
        self.assertEqual(connections_used(properties["definition"]["actions"]), {"shared_azurequeues", "shared_teams"}, "every connection that a step of the flow uses, in a condition too, has its reference")
        self.assertLessEqual(connections_used(properties["definition"]["actions"]), set(properties["connectionReferences"]))

    def test_a_second_run_updates_the_flow_and_two_flows_of_the_name_are_left_alone(self):
        world = World()
        world.sign_in("shared_azurequeues", "shared_teams")
        world.run(["flow", *self.ARGS, "--storage-account", ACCOUNT, "--apply", "--yes"])
        code, out, _ = world.run(["flow", *self.ARGS, "--storage-account", ACCOUNT, "--apply", "--yes"])
        self.assertEqual((code, len(world.flows)), (0, 1))
        self.assertIn("is updated", out)
        self.assertEqual([m for m, _ in world.changes()], ["POST", "PATCH"])
        world.flows["00000000-0000-0000-0000-999999999999"] = {"name": "00000000-0000-0000-0000-999999999999", "properties": {"displayName": pp.FLOW_NAME}}
        before = list(world.changes())
        code, _, err = world.run(["flow", *self.ARGS, "--storage-account", ACCOUNT, "--apply", "--yes"])
        self.assertEqual(code, 1)
        self.assertIn("changes none of them on a guess", err)
        self.assertEqual(world.changes(), before)

    def test_the_dry_run_of_the_flow_changes_nothing(self):
        world = World()
        world.sign_in("shared_azurequeues", "shared_teams")
        code, out, _ = world.run(["flow", *self.ARGS, "--storage-account", ACCOUNT])
        self.assertEqual((code, world.changes(), world.flows), (0, [], {}))
        self.assertIn("This was a dry run.", out)

    def test_flow_runs_lists_the_newest_first_and_names_the_action_that_failed(self):
        world = World()
        world.sign_in("shared_azurequeues", "shared_teams")
        world.run(["flow", *self.ARGS, "--storage-account", ACCOUNT, "--apply", "--yes"])
        (flow_id,) = world.flows
        world.add_run(flow_id, "Succeeded")
        world.add_run(flow_id, "Failed", ["ActionFailed", "Forbidden"])
        world.add_run(flow_id, "Succeeded")
        code, out, _ = world.run(["flow-runs", *self.ARGS, "--last", "2"])
        self.assertEqual(code, 1)
        lines = [line.strip() for line in out.splitlines() if line.startswith("  2026")]
        self.assertEqual([line.split()[1] for line in lines], ["Succeeded", "Failed"])
        self.assertIn("action2: Forbidden", out)
        code, out, _ = world.run(["flow-runs", *self.ARGS, "--last", "1"])
        self.assertEqual(code, 0)

    def test_flow_runs_without_a_flow_says_to_run_flow(self):
        code, _, err = World().run(["flow-runs", *self.ARGS])
        self.assertEqual(code, 1)
        self.assertIn("run `flow` first", err)

    def test_test_card_makes_a_flow_runs_it_says_where_the_card_is_and_deletes_the_flow(self):
        world = World()
        world.sign_in("shared_azurequeues")
        code, out, err = world.run(["test-card", *self.ARGS, "--storage-account", ACCOUNT, "--to", "someone@example.com", "--apply", "--yes"])
        self.assertEqual((code, err), (0, ""))
        self.assertEqual(world.flows, {})
        made = [p for m, u, p in world.calls if m == "POST" and u.split("?")[0].endswith("/flows")]
        self.assertEqual(len(made), 1)
        action = made[0]["properties"]["definition"]["actions"]["Put_a_message_on_a_queue_(V2)"]["inputs"]
        message = json.loads(action["parameters"]["message"])
        self.assertEqual((message["v"], message["to"], message["card"]["type"]), (1, "someone@example.com", "AdaptiveCard"))
        self.assertEqual((action["host"]["operationId"], action["parameters"]["queueName"], action["parameters"]["storageAccountName"]), ("PutMessage_V2", "teams-cards", f"https://{ACCOUNT}.queue.core.windows.net/"))
        self.assertIn("The card is on the queue teams-cards", out)
        self.assertIn("The test flow is deleted.", out)

    def test_a_test_card_that_the_queue_refuses_names_the_role_and_the_flow_is_deleted_all_the_same(self):
        world = World(run_outcome=("Failed", ["Forbidden"]))
        world.sign_in("shared_azurequeues")
        code, out, _ = world.run(["test-card", *self.ARGS, "--storage-account", ACCOUNT, "--to", "someone@example.com", "--apply", "--yes"])
        self.assertEqual((code, world.flows), (1, {}))
        self.assertIn("Storage Queue Data Message Sender", out)
        world = World(run_outcome=("Running", []))
        world.sign_in("shared_azurequeues")
        code, out, _ = world.run(["test-card", *self.ARGS, "--storage-account", ACCOUNT, "--to", "someone@example.com", "--apply", "--yes"])
        self.assertEqual((code, world.flows), (1, {}))
        self.assertIn("did not end in two minutes", out)

    def test_the_dry_run_of_the_test_card_changes_nothing(self):
        world = World()
        world.sign_in("shared_azurequeues")
        code, _, _ = world.run(["test-card", *self.ARGS, "--storage-account", ACCOUNT, "--to", "someone@example.com"])
        self.assertEqual((code, world.changes()), (0, []))

    def test_test_close_posts_a_card_waits_and_replaces_it_with_the_two_steps_of_the_flow_and_deletes_the_flow(self):
        world = World()
        world.sign_in("shared_teams")
        code, out, err = world.run(["test-close", *self.ARGS, "--to", "someone@example.com", "--apply", "--yes"])
        self.assertEqual((code, err, world.flows), (0, "", {}))
        made = [p for m, u, p in world.calls if m == "POST" and u.split("?")[0].endswith("/flows")]
        self.assertEqual(len(made), 1)
        definition = made[0]["properties"]["definition"]
        self.assertEqual(list(made[0]["properties"]["connectionReferences"]), ["shared_teams"], "no queue is used: the Teams connection alone")
        post, wait, update = (definition["actions"][name] for name in (pp.POST_ACTION, "Wait_ten_seconds", pp.UPDATE_ACTION))
        real = pp.flow_definition()
        for test, name in ((post, pp.POST_ACTION), (update, pp.UPDATE_ACTION)):
            self.assertEqual(test["inputs"]["host"], pp.action_of(real, name)["inputs"]["host"], "the step that the flow runs")
            self.assertEqual(set(test["inputs"]["parameters"]), set(pp.action_of(real, name)["inputs"]["parameters"]), "with the fields that the flow gives it")
        self.assertEqual((post["runAfter"], wait["runAfter"], update["runAfter"]), ({}, {pp.POST_ACTION: ["Succeeded"]}, {"Wait_ten_seconds": ["Succeeded"]}))
        self.assertEqual(update["inputs"]["parameters"]["body/messageId"], f"@body('{pp.POST_ACTION}')?['id']", "the message that the post gave")
        self.assertEqual((post["inputs"]["parameters"]["body/recipient"], update["inputs"]["parameters"]["body/recipient"]), ("someone@example.com",) * 2)
        for step in (post, update):
            self.assertEqual(json.loads(step["inputs"]["parameters"]["body/messageBody"])["type"], "AdaptiveCard")
        self.assertIn("The card was posted and replaced.", out)
        self.assertIn("The test flow is deleted.", out)

    def test_a_test_close_that_fails_names_the_step_and_the_flow_is_deleted_all_the_same(self):
        world = World(run_outcome=("Failed", ["BadRequest"]))
        world.sign_in("shared_teams")
        code, out, _ = world.run(["test-close", *self.ARGS, "--to", "someone@example.com", "--apply", "--yes"])
        self.assertEqual((code, world.flows), (1, {}))
        self.assertIn("The test flow failed: BadRequest.", out)
        self.assertIn("check it against the flow", out)

    def test_the_dry_run_of_the_test_close_changes_nothing_and_needs_no_queue_connection(self):
        world = World()
        world.sign_in("shared_teams")
        code, out, _ = world.run(["test-close", *self.ARGS, "--to", "someone@example.com"])
        self.assertEqual((code, world.changes(), world.flows), (0, [], {}))
        self.assertIn("No queue is used.", out)
        code, _, err = World().run(["test-close", *self.ARGS, "--to", "someone@example.com"])
        self.assertEqual(code, 1)
        self.assertIn("Microsoft Teams", err)

    def test_a_bad_storage_account_queue_mail_address_or_count_is_refused_before_anything_is_asked(self):
        for argv, words in ((["flow", *self.ARGS, "--storage-account", "Not_Valid"], "--storage-account is a storage account name"),
                            (["flow", *self.ARGS, "--storage-account", ACCOUNT, "--queue", "Bad_Queue"], "--queue is a queue name"),
                            (["flow", *self.ARGS, "--storage-account", ACCOUNT, "--posted-queue", "Bad_Queue"], "--posted-queue is a queue name"),
                            (["test-card", *self.ARGS, "--storage-account", ACCOUNT, "--to", "not a mail"], "--to is a mail address"),
                            (["test-close", *self.ARGS, "--to", "not a mail"], "--to is a mail address"),
                            (["flow-runs", *self.ARGS, "--last", "0"], "--last is a number from 1 to 20")):
            world = World()
            code, _, err = world.run(argv)
            self.assertEqual(code, 1, argv)
            self.assertIn(words, err)
            self.assertEqual((world.calls, world.audiences), ([], []), argv)

    def test_the_two_new_hosts_take_their_own_token_and_only_the_calls_that_are_written_for_them(self):
        world = World()
        client = pp.Client(pp.Tokens(world.runner, pp.Hider()), world.transport, lambda s: None)
        query = f"api-version=2016-11-01&$filter=environment%20eq%20%27{ENV}%27"
        connection = f"https://api.powerapps.com/providers/Microsoft.PowerApps/apis/shared_teams/connections/{'a' * 32}"
        flows = f"https://api.flow.microsoft.com/providers/Microsoft.ProcessSimple/environments/{ENV}/flows"
        for method, url in (("DELETE", f"{connection}?{query}"), ("PUT", f"{flows}?api-version=2016-11-01"), ("GET", "https://api.flow.microsoft.com/providers/Microsoft.ProcessSimple/scopes/admin/environments/x/flows?api-version=2016-11-01"),
                            ("POST", f"https://api.powerapps.com/providers/Microsoft.PowerApps/apis/shared_office365/connections/{'a' * 32}?{query}"),
                            ("PUT", f"https://api.powerapps.com/providers/Microsoft.PowerApps/apis/shared_teams/connections/short?{query}"),
                            ("GET", f"http://api.flow.microsoft.com/providers/Microsoft.ProcessSimple/environments/{ENV}/flows?api-version=2016-11-01"),
                            ("GET", f"https://api.flow.microsoft.com.evil.example/providers/Microsoft.ProcessSimple/environments/{ENV}/flows?api-version=2016-11-01"),
                            ("DELETE", f"{flows}?api-version=2016-11-01"), ("GET", f"{flows}/{ENV}/runs/x/y?api-version=2016-11-01")):
            with self.assertRaises(pp.Problem, msg=f"{method} {url}"):
                client.send(method, url, {})
        self.assertEqual((world.calls, world.audiences), ([], []))

    def test_the_names_that_the_tool_gives_the_flow_are_the_ones_of_the_packed_solution(self):
        parameters = pp.flow_definition()["parameters"]
        self.assertIn(pp.ENDPOINT_PARAMETER, parameters)
        self.assertIn(pp.QUEUE_PARAMETER, parameters)
        self.assertIn(pp.POSTED_PARAMETER, parameters)
        self.assertEqual(sorted(pp.flow_definition()["triggers"]), ["When_there_are_messages_in_a_queue_(V2)"])
        self.assertEqual((pp.QUEUE_NAME, pp.POSTED_QUEUE_NAME), ("teams-cards", "teams-posted"))


class TheTokensAndTheCalls(unittest.TestCase):
    def test_each_audience_is_asked_for_once_and_the_two_hosts_get_their_own_tokens(self):
        world = World()
        world.run(["status", "--environment", ENV, "--subscription", SUB, "--resource-group", GROUP])
        self.assertEqual(sorted(world.audiences), ["https://management.azure.com/", "https://service.powerapps.com/"])

    def test_a_token_is_never_printed_even_when_a_service_echoes_it(self):
        world = World()
        original = world.bap

        def echoing(method, path, payload):
            status, headers, body = original(method, path, payload)
            return (403, headers, f'{{"error": {{"code": "X", "message": "your token {BAP_TOKEN} is bad"}}}}'.encode()) if path.endswith("/environments") else (status, headers, body)
        world.bap = echoing
        code, out, err = world.run(["status"])
        self.assertEqual(code, 1)
        self.assertNotIn(BAP_TOKEN, out + err)
        self.assertIn("[token hidden]", err)

    def test_a_missing_sign_in_is_said_in_plain_words(self):
        world = World()
        world.runner = lambda args: (1, "", "ERROR: Please run 'az login' to setup account.")
        code, _, err = world.run(["status"])
        self.assertEqual(code, 1)
        self.assertIn("the Azure CLI gave no token", err)
        self.assertIn("az login", err)

    def test_the_client_sends_only_its_own_calls_and_only_to_the_two_hosts(self):
        client = pp.Client(pp.Tokens(World().runner, pp.Hider()), World().transport, lambda s: None)
        for method, url in (("POST", "https://management.azure.com/subscriptions/x"), ("DELETE", f"{BAP}/environments/{ENV}?api-version=2021-04-01"), ("GET", "https://evil.example/providers/Microsoft.BusinessAppPlatform/environments"),
                            ("PUT", f"https://management.azure.com{POLICY}?api-version=2020-10-30-preview"), ("GET", "https://graph.microsoft.com/v1.0/me"),
                            ("POST", f"{BAP}/environments/{ENV}/enterprisePolicies/Encryption/link?api-version=2019-10-01"),
                            ("POST", f"https://unitedstates.api.bap.microsoft.com/providers/Microsoft.BusinessAppPlatform/environments/{ENV}/enterprisePolicies/NetworkInjection/link?api-version=2019-10-01"),
                            ("DELETE", "https://unitedstates.api.bap.microsoft.com/providers/Microsoft.BusinessAppPlatform/operations/1")):
            with self.assertRaises(pp.Problem, msg=f"{method} {url}"):
                client.send(method, url, {})

    def test_the_address_of_an_operation_is_followed_only_on_the_platform_host_or_its_regional_host(self):
        for url in ("https://evil.example/providers/Microsoft.BusinessAppPlatform/operations/1",
                    "https://api.bap.microsoft.com.evil.example/providers/Microsoft.BusinessAppPlatform/operations/1",
                    "https://evil.example/api.bap.microsoft.com/providers/Microsoft.BusinessAppPlatform/operations/1",
                    "http://unitedstates.api.bap.microsoft.com/providers/Microsoft.BusinessAppPlatform/operations/1",
                    "https://a.b.api.bap.microsoft.com/providers/Microsoft.BusinessAppPlatform/operations/1",
                    "https://user@unitedstates.api.bap.microsoft.com/providers/Microsoft.BusinessAppPlatform/operations/1",
                    "https://unitedstates.api.bap.microsoft.com:8443/providers/Microsoft.BusinessAppPlatform/operations/1",
                    "https://unitedstates.api.bap.microsoft.com@evil.example/providers/Microsoft.BusinessAppPlatform/operations/1"):
            world = World()
            client = pp.Client(pp.Tokens(world.runner, pp.Hider()), world.transport, lambda s: None)
            with self.assertRaises(pp.Problem, msg=url) as caught:
                pp.wait_for_operation(client, url, "x", lambda s: None, 60, lambda: 0)
            self.assertIn("is not the Business Application Platform", str(caught.exception), url)
            self.assertEqual((world.audiences, world.calls), ([], []), url)

    def test_a_terminal_that_is_closed_or_absent_is_nobody_to_ask(self):
        class Terminal:
            def __init__(self, tty):
                self.tty = tty

            def isatty(self):
                return self.tty
        with mock.patch.object(sys, "stdin", Terminal(False)):
            self.assertIsNone(pp.ask_on_terminal("Link? "))
        with mock.patch.object(sys, "stdin", Terminal(True)), mock.patch("builtins.input", side_effect=EOFError):
            self.assertIsNone(pp.ask_on_terminal("Link? "))
        with mock.patch.object(sys, "stdin", Terminal(True)), mock.patch("builtins.input", return_value="yes"):
            self.assertEqual(pp.ask_on_terminal("Link? "), "yes")

    def test_nothing_that_changes_anything_is_sent_without_apply_whatever_the_command(self):
        for argv in (["status", "--environment", ENV, "--subscription", SUB, "--resource-group", GROUP], ["create-environment", "--name", "new one"], ["managed", "--environment", ENV], LINK,
                     ["unlink", "--environment", ENV, "--subscription", SUB, "--resource-group", GROUP], ["steps"]):
            world = World()
            world.environments[ENV] = environment(managed="Basic", policy=POLICY if argv[0] == "unlink" else None)
            world.run(argv, answers=["yes"])
            self.assertEqual(world.changes(), [], argv)

    def test_a_pipeline_is_refused_for_every_command_but_steps(self):
        for argv in (["status"], ["create-environment", "--name", "new one"], ["managed", "--environment", ENV], LINK):
            world = World()
            code, out, err = world.run(argv, env={"GITHUB_ACTIONS": "true"})
            self.assertEqual(code, 1, argv)
            self.assertIn("never a pipeline", err)
            self.assertEqual(world.calls + world.audiences, [], argv)
        code, out, _ = World().run(["steps"], env={"GITHUB_ACTIONS": "true"})
        self.assertEqual(code, 0)

    def test_the_arguments_are_checked_and_the_variables_of_the_hub_are_the_defaults(self):
        world = World()
        code, _, err = world.run(["status", "--subscription", "not-a-guid"])
        self.assertEqual(code, 1)
        self.assertIn("--subscription is a subscription id", err)
        code, _, err = world.run(["link", "--environment", ENV])
        self.assertIn("--subscription and --resource-group name where the project's policy is", err)
        world = World()
        code, out, _ = world.run(["link"], env={"PP_ENVIRONMENT": ENV, "ENV_SUBSCRIPTION_ID": SUB, "ENV_RESOURCE_GROUP": GROUP})
        self.assertEqual(code, 0)
        self.assertIn("This was a dry run.", out)


class TheNamesAreTheTemplates(unittest.TestCase):
    def text(self, path):
        return (ROOT / path).read_text(encoding="utf-8").replace("\r\n", "\n")

    def test_the_policy_the_geography_the_delegation_the_version_and_the_queue_are_the_ones_of_the_templates_and_the_builder(self):
        template = self.text("environment/powerplatform/main.bicep")
        code = re.sub(r"(?m)//.*$", "", template)
        self.assertIn("var enterprisePolicyName = 'ep-${workload}-netinjection'", code)
        self.assertEqual(pp.DEFAULT_POLICY_NAME, "ep-meternaut-netinjection")
        self.assertIn(f"var enterprisePolicyGeography = '{pp.GEOGRAPHY}'", code)
        self.assertIn(f"Microsoft.PowerPlatform/enterprisePolicies@{pp.POLICY_API}", code)
        self.assertIn(f"serviceName: '{pp.DELEGATION}'", code)
        self.assertIn(f"'{pp.AZURE_REGION}'", code)
        self.assertIn(f"var cardsQueueName = '{pp.QUEUE_NAME}'", self.text("environment/cases/main.bicep"))
        self.assertIn(f"var postedQueueName = '{pp.POSTED_QUEUE_NAME}'", self.text("environment/cases/main.bicep"))
        spec = importlib.util.spec_from_file_location("environment_params_of_the_powerplatform_tests", ROOT / "tools" / "environment-params.py")
        params = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(params)
        self.assertEqual((params.POWERPLATFORM_POLICY_NAME, params.POWERPLATFORM_GEOGRAPHY, params.POWERPLATFORM_AZURE_REGION, params.CARDS_QUEUE_NAME),
                         (pp.DEFAULT_POLICY_NAME, pp.GEOGRAPHY, pp.AZURE_REGION, pp.QUEUE_NAME))
        self.assertIn(f"snet-powerplatform", code)
        self.assertEqual(params.POWERPLATFORM_SUBNET_NAME, "snet-powerplatform")

    def test_the_least_room_is_a_slash_28_and_the_builders_subnet_has_at_least_that(self):
        self.assertEqual(pp.usable_addresses("10.0.0.0/28"), 11)
        self.assertEqual(pp.usable_addresses("10.0.0.0/27"), 27)
        self.assertEqual(pp.usable_addresses("10.0.0.0/29"), 3)
        self.assertEqual(pp.usable_addresses("nonsense"), 0)
        spec = importlib.util.spec_from_file_location("environment_params_of_the_powerplatform_tests2", ROOT / "tools" / "environment-params.py")
        params = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(params)
        self.assertGreaterEqual(pp.usable_addresses(f"10.0.0.0/{params.POWERPLATFORM_SUBNET_LENGTH}"), pp.LEAST_USABLE)

    def test_the_tool_holds_no_identifier_no_secret_and_no_stored_credential(self):
        source = self.text("tools/powerplatform.py")
        self.assertIsNone(re.search(pp.GUID, source), "no id of an environment, a tenant or a subscription")
        code = re.sub(r'""".*?"""', "", source, flags=re.S)
        for pattern in (r"client_secret", r"client_id", r"password", r"\bpfx\b", r"keyring", r"(?<![A-Za-z_])open\(", r"read_text", r"write_text", r"AZURE_CLIENT", r"os\.environ\.get\(.AZURE"):
            self.assertIsNone(re.search(pattern, code), pattern)
        self.assertEqual(sorted(re.findall(r'(?m)^(BAP|ARM) = "([^"]+)"', source)), [("ARM", "https://management.azure.com"), ("BAP", "https://api.bap.microsoft.com")])


if __name__ == "__main__":
    unittest.main()
