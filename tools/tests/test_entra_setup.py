import contextlib
import copy
import importlib.util
import io
import itertools
import json
import re
import sys
import unittest
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("entra_setup", ROOT / "tools" / "entra-setup.py")
es = importlib.util.module_from_spec(spec)
sys.modules["entra_setup"] = es
spec.loader.exec_module(es)

TENANT = "11111111-2222-3333-4444-555555555555"
HOST = "func-example-0000.azurewebsites.net"
IDENTITY = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
PERSON = "bbbbbbbb-cccc-dddd-eeee-ffffffffffff"
SECOND_PERSON = "cccccccc-dddd-eeee-ffff-000000000000"
GRAPH_PRINCIPAL = "99999999-0000-4000-8000-000000000001"
ARM_PRINCIPAL = "99999999-0000-4000-8000-000000000002"
CALLBACK = f"https://{HOST}/.auth/login/aad/callback"
ARM_RETURN = f"https://{HOST}/arm/return"
ARGS = ["--tenant-id", TENANT, "--host", HOST, "--identity-principal-id", IDENTITY, "--assign", PERSON]
LABEL_RETURN = "Redirect address"
LABEL_PERMISSION = "Delegated permission user_impersonation of Azure Service Management"
LABEL_PUBLIC = "Public client flows off"
LABEL_CONSENT_ARM = "Consent of the administrator for user_impersonation of Azure Service Management"


def both_permissions():
    return [{"resourceAppId": es.GRAPH_APP_ID, "resourceAccess": [{"id": es.USER_READ, "type": "Scope"}]},
            {"resourceAppId": es.ARM_APP_ID, "resourceAccess": [{"id": es.USER_IMPERSONATION, "type": "Scope"}]}]


FORBIDDEN = (403, {"error": {"code": "Authorization_RequestDenied", "message": "Insufficient privileges to complete the operation."}})
STRAY_ADDRESS = "https://elsewhere.example/cb"
STRAY_PERMISSION = {"id": "11111111-1111-1111-1111-111111111111", "type": "Role"}
OTHER_RESOURCE = {"resourceAppId": "22222222-2222-2222-2222-222222222222", "resourceAccess": [{"id": "33333333-3333-3333-3333-333333333333", "type": "Scope"}]}


def with_strays(tenant):
    """What the first version made, and what somebody else added to the app registration since: an address, a permission of Microsoft Graph and a permission
    of another resource."""
    app, principal = tenant.made_by_the_first_version()
    app["web"]["redirectUris"] = [CALLBACK, STRAY_ADDRESS]
    app["requiredResourceAccess"] = [{"resourceAppId": es.GRAPH_APP_ID, "resourceAccess": [{"id": es.USER_READ, "type": "Scope"}, dict(STRAY_PERMISSION)]},
                                     copy.deepcopy(OTHER_RESOURCE)]
    return app, principal


def an_app(callback=True, arm_return=True, id_token=True, user_read=True, impersonation=True, strays=False, public_client=False):
    """An app registration as Microsoft Graph returns it, with or without each thing that the tool wants, and with or without what somebody else added;
    public_client is the value of isFallbackPublicClient."""
    addresses = ([CALLBACK] if callback else []) + ([STRAY_ADDRESS] if strays else []) + ([ARM_RETURN] if arm_return else [])
    graph = ([{"id": es.USER_READ, "type": "Scope"}] if user_read else []) + ([dict(STRAY_PERMISSION)] if strays else [])
    access = [{"resourceAppId": es.GRAPH_APP_ID, "resourceAccess": graph}] if graph else []
    access += [{"resourceAppId": es.ARM_APP_ID, "resourceAccess": [{"id": es.USER_IMPERSONATION, "type": "Scope"}]}] if impersonation else []
    access += [copy.deepcopy(OTHER_RESOURCE)] if strays else []
    return {"id": "00000000-0000-4000-8000-0000000000aa", "appId": "00000000-0000-4000-8000-0000000000bb", "displayName": es.APP_NAME,
            "signInAudience": es.THIS_TENANT_ONLY, "isFallbackPublicClient": public_client,
            "web": {"redirectUris": addresses, "implicitGrantSettings": {"enableIdTokenIssuance": id_token}},
            "requiredResourceAccess": access, "passwordCredentials": [], "keyCredentials": []}


class FakeTenant:
    """A small model of the parts of a Microsoft Entra tenant that the tool reads and changes, and a record of every call."""

    TOKEN = "eyJhbGciOiJSUzI1NiJ9.eyJhdWQiOiJ0ZXN0In0.c2lnbmF0dXJlLW9mLXRoZS10ZXN0"

    def __init__(self):
        self.apps, self.credentials, self.assigned, self.grants = [], {}, {}, []
        self.principals = [{"id": GRAPH_PRINCIPAL, "appId": es.GRAPH_APP_ID}, {"id": ARM_PRINCIPAL, "appId": es.ARM_APP_ID}]
        self.calls, self.token_requests, self.errors, self.page_size, self.counter = [], [], [], None, 0
        self.refused_consent = {}
        self.sp_follows = False  # whether the enterprise application takes the new name when the app registration is renamed
        self.stale_reads = 0  # how many reads by client id still show the old name after a rename (a write that is not seen yet)
        self.stale = {}

    def new_id(self):
        self.counter += 1
        return f"00000000-0000-4000-8000-{self.counter:012d}"

    def writes(self):
        return [c for c in self.calls if c[0] != "GET"]

    def az(self, args):
        self.token_requests.append(list(args))
        if list(args)[:2] == ["account", "get-access-token"]:
            return 0, self.TOKEN + "\n", ""
        return 1, "", "unexpected"

    def existing_app(self, **changes):
        app = {"id": self.new_id(), "appId": self.new_id(), "displayName": es.APP_NAME, "signInAudience": es.THIS_TENANT_ONLY, "isFallbackPublicClient": False,
               "web": {"redirectUris": [CALLBACK, ARM_RETURN], "implicitGrantSettings": {"enableIdTokenIssuance": True}},
               "requiredResourceAccess": both_permissions(),
               "passwordCredentials": [], "keyCredentials": []}
        app.update(changes)
        self.apps.append(app)
        return app

    def existing_everything(self, people=(PERSON,)):
        app = self.existing_app()
        principal = {"id": self.new_id(), "appId": app["appId"], "displayName": app["displayName"], "appRoleAssignmentRequired": True}
        self.principals.append(principal)
        self.credentials[app["id"]] = [{"name": es.CREDENTIAL_NAME, "issuer": f"https://login.microsoftonline.com/{TENANT}/v2.0", "subject": IDENTITY,
                                        "audiences": [es.AUDIENCE]}]
        self.assigned[principal["id"]] = [{"principalId": p} for p in people]
        self.grants.append({"clientId": principal["id"], "consentType": "AllPrincipals", "resourceId": GRAPH_PRINCIPAL, "scope": "User.Read"})
        self.grants.append({"clientId": principal["id"], "consentType": "AllPrincipals", "resourceId": ARM_PRINCIPAL, "scope": "user_impersonation"})
        return app, principal

    def made_before_the_rename(self, people=(PERSON,)):
        """What the tool made while the app registration and its enterprise application were still called by the old name."""
        app, principal = self.existing_everything(people)
        app["displayName"] = principal["displayName"] = es.FORMER_APP_NAME
        return app, principal

    def made_by_the_first_version(self, people=(PERSON,)):
        """What the tool made before the sign-in to Azure Resource Manager: one redirect address, User.Read only, and the consent for that only."""
        app, principal = self.existing_everything(people)
        app["web"]["redirectUris"] = [CALLBACK]
        app["requiredResourceAccess"] = both_permissions()[:1]
        self.grants[:] = [g for g in self.grants if g["resourceId"] == GRAPH_PRINCIPAL]
        return app, principal

    def answer(self, status, document=None, headers=None):
        raw = b"" if document is None else json.dumps(document).encode("utf-8")
        return status, headers or {}, raw

    def transport(self, method, url, headers, body):
        parts = urlsplit(url)
        assert parts.netloc == "graph.microsoft.com" and parts.path.startswith("/v1.0/"), url
        assert headers["Authorization"] == f"Bearer {self.TOKEN}"
        assert " " not in url, "an address may not hold a space"
        route = parts.path[len("/v1.0/"):]
        query = {k: v[0] for k, v in parse_qs(parts.query, keep_blank_values=True).items()}
        data = json.loads(body.decode("utf-8")) if body else None
        self.calls.append((method, route, data))
        for error in list(self.errors):
            if error[0] == method and route.startswith(error[1]):
                self.errors.remove(error)
                return self.answer(error[2], error[3], error[4] if len(error) > 4 else None)
        match = lambda pattern: re.fullmatch(pattern, route)  # noqa: E731
        filtered = lambda items: [i for i in items if self.filter_matches(query.get("$filter"), i)]  # noqa: E731
        if route == "applications":
            if method == "GET":
                shown = []
                for app in filtered(self.apps):
                    app = dict(app)
                    left = self.stale.get(app["id"])
                    if left and left[1] > 0 and (query.get("$filter") or "").startswith("appId eq"):
                        app["displayName"], left[1] = left[0], left[1] - 1
                    shown.append(self.selected(app, query.get("$select")))
                return self.answer(200, {"value": shown})
            app = dict(data, id=self.new_id(), appId=self.new_id(), passwordCredentials=[], keyCredentials=[])
            self.apps.append(app)
            return self.answer(201, app)
        found = match(r"applications/([0-9a-f-]+)")
        if found and method == "PATCH":
            app = next(a for a in self.apps if a["id"] == found.group(1))
            if "displayName" in data and data["displayName"] != app["displayName"]:
                if self.stale_reads:
                    self.stale[app["id"]] = [app["displayName"], self.stale_reads]
                if self.sp_follows:
                    for principal in self.principals:
                        if principal["appId"] == app["appId"]:
                            principal["displayName"] = data["displayName"]
            app.update(data)
            return self.answer(204)
        found = match(r"applications/([0-9a-f-]+)/federatedIdentityCredentials")
        if found:
            if method == "GET":
                return self.answer(200, {"value": self.credentials.get(found.group(1), [])})
            self.credentials.setdefault(found.group(1), []).append(data)
            return self.answer(201, data)
        if route == "servicePrincipals":
            if method == "GET":
                return self.answer(200, {"value": [self.selected(p, query.get("$select")) for p in filtered(self.principals)]})
            made_for = next((a for a in self.apps if a["appId"] == data.get("appId")), None)
            principal = dict(data, id=self.new_id(), displayName=made_for["displayName"] if made_for else None)  # an enterprise application starts with the name of its app registration
            self.principals.append(principal)
            return self.answer(201, principal)
        found = match(r"servicePrincipals/([0-9a-f-]+)")
        if found and method == "PATCH":
            next(p for p in self.principals if p["id"] == found.group(1)).update(data)
            return self.answer(204)
        found = match(r"servicePrincipals/([0-9a-f-]+)/appRoleAssignedTo")
        if found:
            held = self.assigned.setdefault(found.group(1), [])
            if method == "GET":
                if not self.page_size:
                    return self.answer(200, {"value": held})
                start = int(query.get("$skiptoken", "0"))
                page = held[start:start + self.page_size]
                document = {"value": page}
                if start + self.page_size < len(held):
                    document["@odata.nextLink"] = f"https://graph.microsoft.com/v1.0/{route}?$skiptoken={start + self.page_size}"
                return self.answer(200, document)
            held.append({"principalId": data["principalId"]})
            return self.answer(201, data)
        if route == "oauth2PermissionGrants":
            if method == "GET":
                return self.answer(200, {"value": filtered(self.grants)})
            if data["scope"] in self.refused_consent:
                return self.answer(*self.refused_consent[data["scope"]])
            self.grants.append(data)
            return self.answer(201, data)
        raise AssertionError(f"the tool sent a call that the model does not know: {method} {route}")

    @staticmethod
    def selected(item, select):
        """Microsoft Graph sends only the properties that $select names (and the id): a property that the tool forgot to select is never there to read."""
        if not select:
            return item
        names = set(select.split(",")) | {"id"}
        return {key: value for key, value in item.items() if key in names}

    @staticmethod
    def filter_matches(expression, item):
        if not expression:
            return True
        found = re.fullmatch(r"(\w+) eq '([^']*)'", expression)
        assert found, expression
        return item.get(found.group(1)) == found.group(2)


def run(argv, tenant, env=None, answers=("yes",), asked=None, while_asking=None):
    lines, errors, sleeps = [], io.StringIO(), []
    answers = list(answers)

    def ask(prompt):
        if asked is not None:
            asked.append(prompt)
        if while_asking is not None:
            while_asking()
        return answers.pop(0) if answers else None

    with contextlib.redirect_stderr(errors):
        code = es.main(argv, runner=tenant.az, transport=tenant.transport, sleep=sleeps.append, out=lines.append, ask=ask, env={} if env is None else env)
    return code, "\n".join(lines), errors.getvalue(), sleeps


class TheInputs(unittest.TestCase):
    def test_every_input_is_checked_and_named(self):
        for argv, word in (
            (["check", "--host", HOST, "--identity-principal-id", IDENTITY], "--tenant-id"),
            (["check", "--tenant-id", "not-a-guid", "--host", HOST, "--identity-principal-id", IDENTITY], "--tenant-id"),
            (["check", "--tenant-id", TENANT, "--identity-principal-id", IDENTITY], "--host"),
            (["check", "--tenant-id", TENANT, "--host", "no spaces here", "--identity-principal-id", IDENTITY], "--host"),
            (["check", "--tenant-id", TENANT, "--host", HOST], "--identity-principal-id"),
            (["check", "--tenant-id", TENANT, "--host", HOST, "--identity-principal-id", "x"], "--identity-principal-id"),
            (["check", *ARGS, "--assign", "somebody"], "--assign"),
        ):
            tenant = FakeTenant()
            code, _, err, _ = run(argv, tenant)
            self.assertEqual(code, 1, argv)
            self.assertIn(word, err)
            self.assertEqual(tenant.calls, [], "it refused before it asked for a token or read anything")

    def test_people_can_be_given_twice_or_separated_with_commas_and_are_listed_once(self):
        tenant = FakeTenant()
        code, out, _, _ = run(["check", *ARGS, "--assign", f"{SECOND_PERSON},{PERSON.upper()}"], tenant)
        self.assertEqual(code, 1)
        self.assertEqual(len(re.findall(r"Assignment of", out)), 2)

    def test_the_token_is_asked_for_once_for_microsoft_graph_in_the_tenant(self):
        tenant = FakeTenant()
        run(["check", *ARGS], tenant)
        self.assertEqual(len(tenant.token_requests), 1)
        asked = tenant.token_requests[0]
        self.assertEqual((asked[asked.index("--resource") + 1], asked[asked.index("--tenant") + 1]), ("https://graph.microsoft.com", TENANT))

    def test_the_ids_of_the_permissions_are_the_ones_that_microsoft_publishes(self):
        self.assertEqual(es.GRAPH_APP_ID, "00000003-0000-0000-c000-000000000000")
        self.assertEqual(es.USER_READ, "e1fe6dd8-ba31-4d61-89e7-88639da4683d")
        self.assertEqual(es.ARM_APP_ID, "797f4846-ba00-4fd7-ba43-dac1f8f63013")
        self.assertEqual(es.USER_IMPERSONATION, "41094075-9dad-400e-a0bd-54e686782033")
        self.assertEqual(es.ARM_SCOPE, "user_impersonation")

    def test_the_two_redirect_addresses_follow_the_host_name_in_lower_case_and_the_consent_address_follows_the_tenant_and_the_client(self):
        cfg = es.read_config(es.argparse.Namespace(tenant_id=TENANT.upper(), host=HOST.upper(), identity_principal_id=IDENTITY, assign=None))
        self.assertEqual((cfg.callback, cfg.arm_return), (CALLBACK, ARM_RETURN))
        self.assertEqual(es.consent_address(cfg.tenant, "client-id"), f"https://login.microsoftonline.com/{TENANT}/adminconsent?client_id=client-id")


class Check(unittest.TestCase):
    def test_an_empty_tenant_misses_everything_and_nothing_is_written(self):
        tenant = FakeTenant()
        code, out, _, _ = run(["check", *ARGS], tenant)
        self.assertEqual(code, 1)
        self.assertEqual(out.count("MISSING"), 9)
        self.assertIn("0 of 9 in order.", out)
        self.assertRegex(out, rf"MISSING +{LABEL_PUBLIC}")
        self.assertEqual(tenant.writes(), [])
        self.assertNotIn("Client id of the app registration", out)
        self.assertNotIn("adminconsent", out, "there is no client id yet, so there is no address")

    def test_a_tenant_that_is_in_order_says_so_and_prints_the_client_id(self):
        tenant = FakeTenant()
        app, _ = tenant.existing_everything()
        code, out, _, _ = run(["check", *ARGS], tenant)
        self.assertEqual(code, 0, out)
        self.assertIn("9 of 9 in order.", out)
        self.assertIn(f"CONSOLE_APP_CLIENT_ID): {app['appId']}", out)
        self.assertRegex(out, rf"present +{LABEL_RETURN} {re.escape(ARM_RETURN)}")
        self.assertRegex(out, rf"present +{LABEL_PERMISSION}")
        self.assertRegex(out, rf"present +{LABEL_PUBLIC}")
        self.assertRegex(out, rf"present +{LABEL_CONSENT_ARM}")
        self.assertNotIn("adminconsent", out)
        self.assertEqual(tenant.writes(), [])

    def test_what_the_first_version_made_misses_the_two_new_things_and_the_consent_for_the_second_and_each_is_reported_on_its_own(self):
        tenant = FakeTenant()
        app, _ = tenant.made_by_the_first_version()
        code, out, _, _ = run(["check", *ARGS], tenant)
        self.assertEqual(code, 1)
        self.assertEqual(out.count("MISSING"), 3)
        self.assertRegex(out, rf"MISSING +{LABEL_RETURN} {re.escape(ARM_RETURN)}")
        self.assertRegex(out, rf"MISSING +{LABEL_PERMISSION}")
        self.assertRegex(out, rf"MISSING +{LABEL_CONSENT_ARM}")
        self.assertRegex(out, r"present +App registration")
        self.assertRegex(out, r"present +Consent of the administrator for User\.Read")
        self.assertIn("6 of 9 in order.", out)
        self.assertRegex(out, rf"present +{LABEL_PUBLIC}", "what the first version made was a confidential client: it is not reported")
        self.assertEqual(tenant.writes(), [])

    def test_a_tenant_administrator_is_told_where_to_give_the_consent(self):
        tenant = FakeTenant()
        app, _ = tenant.made_by_the_first_version()
        code, out, _, _ = run(["check", *ARGS], tenant)
        address = f"https://login.microsoftonline.com/{TENANT}/adminconsent?client_id={app['appId']}"
        self.assertEqual(out.count(address), 2, "once in the line of the missing consent, once in what a tenant administrator does")
        self.assertIn("A tenant administrator gives the missing consent once, for the whole tenant", out)
        self.assertIn("Meternaut gets no right of its own", out)

    def test_each_of_the_new_things_alone_is_the_one_that_is_missing(self):
        redirect_only = {"web": {"redirectUris": [CALLBACK], "implicitGrantSettings": {"enableIdTokenIssuance": True}}}
        permission_only = {"requiredResourceAccess": both_permissions()[:1]}
        for change, label in ((redirect_only, LABEL_RETURN), (permission_only, LABEL_PERMISSION)):
            tenant = FakeTenant()
            app, _ = tenant.existing_everything()
            app.update(change)
            code, out, _, _ = run(["check", *ARGS], tenant)
            self.assertEqual((code, out.count("MISSING")), (1, 1), change)
            self.assertRegex(out, rf"MISSING +{label}")
            self.assertRegex(out, r"present +App registration", "the line of the app registration does not say the same again")
        tenant = FakeTenant()
        tenant.existing_everything()
        tenant.grants[:] = [g for g in tenant.grants if g["resourceId"] != ARM_PRINCIPAL]
        code, out, _, _ = run(["check", *ARGS], tenant)
        self.assertEqual((code, out.count("MISSING")), (1, 1))
        self.assertRegex(out, rf"MISSING +{LABEL_CONSENT_ARM}")

    def test_the_token_is_never_printed(self):
        tenant = FakeTenant()
        tenant.errors.append(("GET", "applications", 403, {"error": {"code": "Authorization_RequestDenied", "message": f"no: {FakeTenant.TOKEN}"}}))
        code, out, err, _ = run(["check", *ARGS], tenant)
        self.assertEqual(code, 1)
        self.assertNotIn(FakeTenant.TOKEN, out + err)
        self.assertIn("Microsoft Graph refused: 403 Authorization_RequestDenied", err)

    def test_a_second_app_with_the_same_name_stops_the_check(self):
        tenant = FakeTenant()
        tenant.existing_app()
        tenant.existing_app()
        code, _, err, _ = run(["check", *ARGS], tenant)
        self.assertEqual(code, 1)
        self.assertIn("2 app registrations are called", err)

    def test_what_differs_is_named(self):
        for change, word in (
            ({"signInAudience": "AzureADMultipleOrgs"}, "this tenant only"),
            ({"passwordCredentials": [{"keyId": "x"}]}, "secret or a certificate"),
            ({"keyCredentials": [{"keyId": "x"}]}, "secret or a certificate"),
            ({"web": {"redirectUris": [ARM_RETURN], "implicitGrantSettings": {"enableIdTokenIssuance": True}}}, "of the platform's sign-in is missing"),
            ({"web": {"redirectUris": [CALLBACK, ARM_RETURN], "implicitGrantSettings": {"enableIdTokenIssuance": False}}}, "ID token issuance is off"),
            ({"requiredResourceAccess": both_permissions()[1:]}, "User.Read"),
        ):
            tenant = FakeTenant()
            tenant.existing_app(**change)
            code, out, _, _ = run(["check", *ARGS], tenant)
            self.assertEqual(code, 1, change)
            self.assertIn("DIFFERS", out, change)
            self.assertIn(word, out, change)

    def test_a_redirect_address_or_a_permission_that_somebody_else_added_is_a_note_and_not_a_difference(self):
        for change, words in (
            ({"web": {"redirectUris": [CALLBACK, ARM_RETURN, STRAY_ADDRESS], "implicitGrantSettings": {"enableIdTokenIssuance": True}}}, [STRAY_ADDRESS, "redirect address"]),
            ({"requiredResourceAccess": both_permissions() + [{"resourceAppId": es.GRAPH_APP_ID, "resourceAccess": [STRAY_PERMISSION]}]},
             [STRAY_PERMISSION["id"], "(Role)", f"of resource application {es.GRAPH_APP_ID}"]),
            ({"requiredResourceAccess": both_permissions() + [OTHER_RESOURCE]},
             [OTHER_RESOURCE["resourceAccess"][0]["id"], "(Scope)", f"of resource application {OTHER_RESOURCE['resourceAppId']}"]),
        ):
            tenant = FakeTenant()
            tenant.existing_everything()
            tenant.apps[0].update(change)
            code, out, err, _ = run(["check", *ARGS], tenant)
            self.assertEqual((code, err, tenant.writes()), (0, "", []), change)
            self.assertIn("9 of 9 in order.", out)
            self.assertNotIn("DIFFERS", out)
            self.assertRegex(out, r"present +App registration")
            self.assertIn("also there, and left alone because this tool removes nothing", out)
            self.assertIn("A person removes what nobody meant, in the portal", out)
            for word in words:
                self.assertIn(word, out, change)

    def test_the_notes_come_under_the_line_of_the_app_registration_and_count_for_nothing(self):
        tenant = FakeTenant()
        tenant.existing_everything()
        tenant.apps[0]["web"]["redirectUris"] += ["https://one.example/cb", "https://two.example/cb"]
        tenant.apps[0]["requiredResourceAccess"] += [{"resourceAppId": es.GRAPH_APP_ID, "resourceAccess": [{"id": "11111111-1111-1111-1111-111111111111", "type": "Role"}]}]
        code, out, _, _ = run(["check", *ARGS], tenant)
        lines = out.splitlines()
        first = next(i for i, line in enumerate(lines) if "App registration" in line)
        self.assertIn("redirect addresses https://one.example/cb, https://two.example/cb", lines[first + 1])
        self.assertIn("permission 11111111-1111-1111-1111-111111111111 (Role)", lines[first + 2])
        self.assertTrue(lines[first + 3].startswith("  present    Redirect address"))
        self.assertEqual(code, 0)

    def test_a_note_does_not_hide_what_is_missing(self):
        tenant = FakeTenant()
        tenant.made_by_the_first_version()
        tenant.apps[0]["web"]["redirectUris"] = [CALLBACK, "https://elsewhere.example/cb"]
        code, out, _, _ = run(["check", *ARGS], tenant)
        self.assertEqual(code, 1)
        self.assertRegex(out, rf"MISSING +{LABEL_RETURN} {re.escape(ARM_RETURN)}")
        self.assertIn("https://elsewhere.example/cb", out)

    def test_a_permission_of_another_kind_or_of_another_resource_is_not_the_one_that_is_wanted(self):
        for resource in (
            [{"resourceAppId": es.ARM_APP_ID, "resourceAccess": [{"id": es.USER_IMPERSONATION, "type": "Role"}]}],
            [{"resourceAppId": es.GRAPH_APP_ID, "resourceAccess": [{"id": es.USER_IMPERSONATION, "type": "Scope"}]}],
            [{"resourceAppId": es.ARM_APP_ID, "resourceAccess": [{"id": es.USER_READ, "type": "Scope"}]}],
        ):
            tenant = FakeTenant()
            tenant.existing_app(requiredResourceAccess=both_permissions()[:1] + resource)
            code, out, _, _ = run(["check", *ARGS], tenant)
            self.assertEqual(code, 1, resource)
            self.assertRegex(out, rf"MISSING +{LABEL_PERMISSION}", resource)

    def test_a_redirect_address_is_compared_without_regard_to_case(self):
        tenant = FakeTenant()
        tenant.existing_everything()
        tenant.apps[0]["web"]["redirectUris"] = [CALLBACK.upper(), ARM_RETURN.title()]
        code, out, _, _ = run(["check", *ARGS], tenant)
        self.assertEqual(code, 0, out)

    def test_public_client_flows_that_are_on_are_reported_as_missing_and_nothing_is_written(self):
        tenant = FakeTenant()
        app, _ = tenant.existing_everything()
        app["isFallbackPublicClient"] = True
        code, out, err, _ = run(["check", *ARGS], tenant)
        self.assertEqual((code, err, tenant.writes()), (1, "", []))
        self.assertEqual(out.count("MISSING"), 1)
        self.assertRegex(out, rf"MISSING +{LABEL_PUBLIC} \(isFallbackPublicClient false\)")
        self.assertIn("allows public client flows (isFallbackPublicClient is true), so a sign-in code could be redeemed without a credential: apply switches it off", out)
        self.assertRegex(out, r"present +App registration", "the line of the app registration does not say the same again")
        self.assertIn("8 of 9 in order.", out)

    def test_public_client_flows_that_are_off_or_not_set_are_in_order(self):
        for how in ("false", "null", "absent"):
            tenant = FakeTenant()
            app, _ = tenant.existing_everything()
            if how == "absent":
                del app["isFallbackPublicClient"]
            else:
                app["isFallbackPublicClient"] = None if how == "null" else False
            code, out, err, _ = run(["check", *ARGS], tenant)
            self.assertEqual((code, err, tenant.writes()), (0, "", []), how)
            self.assertRegex(out, rf"present +{LABEL_PUBLIC}", how)
            self.assertIn("9 of 9 in order.", out, how)

    def test_a_value_that_is_not_false_or_not_set_is_taken_as_on(self):
        for value in (True, "true", "false", 0, 1, []):
            tenant = FakeTenant()
            app, _ = tenant.existing_everything()
            app["isFallbackPublicClient"] = value
            code, out, _, _ = run(["check", *ARGS], tenant)
            self.assertEqual((code, out.count("MISSING")), (1, 1), value)
            self.assertRegex(out, rf"MISSING +{LABEL_PUBLIC}", value)

    def test_the_flag_is_asked_for_when_the_app_registration_is_read(self):
        # Microsoft Graph sends only what $select names: a flag that is not asked for would look like one that is not set, and that would pass the check.
        self.assertIn("isFallbackPublicClient", es.APP_SELECT.split(","))

    def test_an_enterprise_application_that_does_not_require_assignment_differs(self):
        tenant = FakeTenant()
        _, principal = tenant.existing_everything()
        principal["appRoleAssignmentRequired"] = False
        code, out, _, _ = run(["check", *ARGS], tenant)
        self.assertEqual(code, 1)
        self.assertIn("anybody in the tenant could sign in", out)

    def test_a_credential_for_another_identity_or_issuer_or_audience_does_not_count(self):
        for change in ({"subject": SECOND_PERSON}, {"issuer": "https://login.microsoftonline.com/other/v2.0"}, {"audiences": ["api://something-else"]}):
            tenant = FakeTenant()
            app, _ = tenant.existing_everything()
            tenant.credentials[app["id"]][0].update(change)
            code, out, _, _ = run(["check", *ARGS], tenant)
            self.assertEqual(code, 1, change)
            self.assertRegex(out, r"MISSING +Federated identity credential", change)

    def test_a_person_who_is_not_assigned_and_a_consent_for_one_user_only_are_missing(self):
        tenant = FakeTenant()
        _, principal = tenant.existing_everything(people=())
        for grant in tenant.grants:
            grant["consentType"] = "Principal"
        code, out, _, _ = run(["check", *ARGS], tenant)
        self.assertEqual(code, 1)
        self.assertRegex(out, rf"MISSING +Assignment of {PERSON}")
        self.assertRegex(out, r"MISSING +Consent of the administrator for User\.Read")
        self.assertRegex(out, rf"MISSING +{LABEL_CONSENT_ARM}")

    def test_a_consent_for_another_resource_or_another_scope_does_not_count(self):
        tenant = FakeTenant()
        _, principal = tenant.existing_everything()
        tenant.grants[0].update(resourceId=ARM_PRINCIPAL)
        tenant.grants[1].update(scope="User.Read")
        code, out, _, _ = run(["check", *ARGS], tenant)
        self.assertEqual(code, 1)
        self.assertRegex(out, r"MISSING +Consent of the administrator for User\.Read")
        self.assertRegex(out, rf"MISSING +{LABEL_CONSENT_ARM}")
        tenant = FakeTenant()
        tenant.existing_everything()
        tenant.grants[1]["scope"] = "user_impersonation openid"
        code, out, _, _ = run(["check", *ARGS], tenant)
        self.assertEqual(code, 0, "a grant may carry more than one scope")

    def test_azure_service_management_without_an_enterprise_application_in_the_tenant_is_said_and_names_the_address(self):
        tenant = FakeTenant()
        app, _ = tenant.existing_everything()
        tenant.principals[:] = [p for p in tenant.principals if p["appId"] != es.ARM_APP_ID]
        tenant.grants[:] = [g for g in tenant.grants if g["resourceId"] != ARM_PRINCIPAL]
        code, out, _, _ = run(["check", *ARGS], tenant)
        self.assertEqual(code, 1)
        self.assertRegex(out, rf"MISSING +{LABEL_CONSENT_ARM}")
        self.assertIn("the enterprise application of Azure Service Management is not in this tenant yet", out)
        self.assertIn(f"adminconsent?client_id={app['appId']}", out)

    def test_a_list_with_a_next_page_is_read_to_the_end(self):
        tenant = FakeTenant()
        _, principal = tenant.existing_everything(people=("dddddddd-eeee-ffff-0000-111111111111", "eeeeeeee-ffff-0000-1111-222222222222", PERSON))
        tenant.page_size = 1
        code, out, _, _ = run(["check", *ARGS], tenant)
        self.assertEqual(code, 0, out)
        self.assertEqual(len([c for c in tenant.calls if c[1].endswith("appRoleAssignedTo")]), 3)


class Apply(unittest.TestCase):
    def test_a_dry_run_says_what_it_would_make_and_makes_nothing(self):
        tenant = FakeTenant()
        code, out, _, _ = run(["apply", *ARGS], tenant)
        self.assertEqual(code, 1)
        self.assertIn("6 change(s) would be made, and nothing else", out)
        self.assertIn(f"redirect addresses {CALLBACK} and {ARM_RETURN}", out)
        self.assertIn("User.Read and user_impersonation of Azure Service Management", out)
        self.assertIn("no secret, public client flows off", out)
        self.assertIn("the administrator's consent for user_impersonation of Azure Service Management, for all users", out)
        self.assertIn("a person who may not give it is told so, and gets the address that a tenant administrator opens", out)
        self.assertIn("This was a dry run", out)
        self.assertEqual(tenant.writes(), [])

    def test_apply_makes_everything_in_order_with_no_secret_and_checks_again(self):
        tenant = FakeTenant()
        code, out, _, sleeps = run(["apply", *ARGS, "--apply", "--yes"], tenant)
        self.assertEqual(code, 0, out)
        self.assertEqual([(m, r.split("/")[0] + ("/" + r.split("/")[2] if r.count("/") > 1 else "")) for m, r, _ in tenant.writes()],
                         [("POST", "applications"), ("POST", "servicePrincipals"), ("POST", "applications/federatedIdentityCredentials"),
                          ("POST", "servicePrincipals/appRoleAssignedTo"), ("POST", "oauth2PermissionGrants"), ("POST", "oauth2PermissionGrants")])
        app = tenant.apps[0]
        self.assertEqual((app["displayName"], app["signInAudience"]), (es.APP_NAME, "AzureADMyOrg"))
        self.assertIs(app["isFallbackPublicClient"], False, "made as a confidential client")
        self.assertEqual(app["web"]["redirectUris"], [CALLBACK, ARM_RETURN])
        self.assertIs(app["web"]["implicitGrantSettings"]["enableIdTokenIssuance"], True)
        self.assertEqual(app["requiredResourceAccess"], [{"resourceAppId": es.GRAPH_APP_ID, "resourceAccess": [{"id": es.USER_READ, "type": "Scope"}]},
                                                         {"resourceAppId": "797f4846-ba00-4fd7-ba43-dac1f8f63013",
                                                          "resourceAccess": [{"id": "41094075-9dad-400e-a0bd-54e686782033", "type": "Scope"}]}])
        self.assertFalse(any(k in app and app[k] for k in ("passwordCredentials", "keyCredentials")), "the app has no secret and no certificate")
        self.assertFalse(any("passwordCredentials" in (d or {}) or "keyCredentials" in (d or {}) or "addPassword" in r for _, r, d in tenant.writes()))
        principal = tenant.principals[-1]
        self.assertEqual((principal["appId"], principal["appRoleAssignmentRequired"]), (app["appId"], True))
        credential = tenant.credentials[app["id"]][0]
        self.assertEqual((credential["issuer"], credential["subject"], credential["audiences"]),
                         (f"https://login.microsoftonline.com/{TENANT}/v2.0", IDENTITY, ["api://AzureADTokenExchange"]))
        self.assertEqual(tenant.assigned[principal["id"]], [{"principalId": PERSON}])
        self.assertEqual(tenant.grants, [{"clientId": principal["id"], "consentType": "AllPrincipals", "resourceId": GRAPH_PRINCIPAL, "scope": "User.Read"},
                                         {"clientId": principal["id"], "consentType": "AllPrincipals", "resourceId": ARM_PRINCIPAL, "scope": "user_impersonation"}])
        self.assertTrue(out.rstrip().splitlines()[-2].endswith("9 of 9 in order."))
        self.assertIn(f"CONSOLE_APP_CLIENT_ID): {app['appId']}", out)
        self.assertNotIn("adminconsent", out)
        self.assertEqual(sleeps, [])

    def test_a_second_apply_has_nothing_to_make(self):
        tenant = FakeTenant()
        run(["apply", *ARGS, "--apply", "--yes"], tenant)
        before = len(tenant.writes())
        code, out, _, _ = run(["apply", *ARGS, "--apply", "--yes"], tenant)
        self.assertEqual((code, len(tenant.writes()), "Nothing to make." in out), (0, before, True))

    def test_only_what_is_missing_is_made(self):
        tenant = FakeTenant()
        app, principal = tenant.existing_everything(people=())
        tenant.grants.clear()
        code, out, _, _ = run(["apply", *ARGS, "--assign", SECOND_PERSON, "--apply", "--yes"], tenant)
        self.assertEqual(code, 0, out)
        self.assertEqual(sorted(r.split("/")[-1] for _, r, _ in tenant.writes()), ["appRoleAssignedTo", "appRoleAssignedTo", "oauth2PermissionGrants", "oauth2PermissionGrants"])
        self.assertEqual(len(tenant.apps), 1)

    def test_what_the_first_version_made_is_brought_up_to_date_and_nothing_is_removed(self):
        tenant = FakeTenant()
        app, principal = tenant.made_by_the_first_version()
        before = {"grants": [dict(g) for g in tenant.grants], "assigned": {k: list(v) for k, v in tenant.assigned.items()}, "credentials": {k: list(v) for k, v in tenant.credentials.items()},
                  "principals": [dict(p) for p in tenant.principals]}
        code, out, _, _ = run(["apply", *ARGS, "--apply", "--yes"], tenant)
        self.assertEqual(code, 0, out)
        self.assertEqual([(m, r) for m, r, _ in tenant.writes()], [("PATCH", f"applications/{app['id']}"), ("POST", "oauth2PermissionGrants")])
        patch = tenant.writes()[0][2]
        self.assertEqual(sorted(patch), ["requiredResourceAccess", "web"])
        self.assertEqual(patch["web"]["redirectUris"], [CALLBACK, ARM_RETURN])
        self.assertEqual([r["resourceAppId"] for r in patch["requiredResourceAccess"]], [es.GRAPH_APP_ID, es.ARM_APP_ID])
        self.assertEqual(tenant.writes()[1][2], {"clientId": principal["id"], "consentType": "AllPrincipals", "resourceId": ARM_PRINCIPAL, "scope": "user_impersonation"})
        self.assertEqual(tenant.grants[:1], before["grants"], "the consent that was there is still there")
        self.assertEqual((tenant.assigned, tenant.credentials), (before["assigned"], before["credentials"]))
        self.assertEqual(tenant.principals[:len(before["principals"])], before["principals"])
        self.assertEqual(len(tenant.apps), 1)
        self.assertIn("9 of 9 in order.", out)
        code, out, _, _ = run(["apply", *ARGS, "--apply", "--yes"], tenant)
        self.assertEqual((code, "Nothing to make." in out), (0, True))

    def test_the_consent_is_for_all_users_for_that_one_scope_of_that_one_resource(self):
        tenant = FakeTenant()
        app, principal = tenant.made_by_the_first_version()
        run(["apply", *ARGS, "--apply", "--yes"], tenant)
        grants = [c for c in tenant.writes() if c[1] == "oauth2PermissionGrants"]
        self.assertEqual(len(grants), 1)
        self.assertEqual(grants[0][2], {"clientId": principal["id"], "consentType": "AllPrincipals", "resourceId": ARM_PRINCIPAL, "scope": "user_impersonation"})

    def test_a_dry_run_on_what_the_first_version_made_adds_and_says_that_nothing_is_removed(self):
        tenant = FakeTenant()
        app, _ = tenant.made_by_the_first_version()
        code, out, _, _ = run(["apply", *ARGS], tenant)
        self.assertEqual(code, 1)
        self.assertIn("2 change(s) would be made, and nothing else", out)
        self.assertIn(f"PATCH applications/{app['id']}: the redirect address {ARM_RETURN} of the sign-in to Azure Resource Manager is missing; "
                      "it does not ask for the delegated permission user_impersonation of Azure Service Management. "
                      "Every redirect address and permission that is there is sent back with it: nothing is removed", out)
        self.assertEqual(tenant.writes(), [])

    def test_what_the_tool_adds_is_added_and_what_somebody_else_made_stays(self):
        tenant = FakeTenant()
        app, principal = tenant.existing_everything()
        app["web"] = {"redirectUris": ["https://old.example/cb"], "implicitGrantSettings": {"enableIdTokenIssuance": False}}
        principal["appRoleAssignmentRequired"] = False
        code, out, _, _ = run(["apply", *ARGS, "--apply", "--yes"], tenant)
        self.assertEqual(code, 0, out)
        changes = [(m, r, d) for m, r, d in tenant.writes()]
        self.assertEqual([(m, r) for m, r, _ in changes], [("PATCH", f"applications/{app['id']}"), ("PATCH", f"servicePrincipals/{principal['id']}")])
        self.assertEqual(sorted(changes[0][2]), ["web"], "both permissions were there, so the list of permissions is not sent")
        self.assertEqual(changes[1][2], {"appRoleAssignmentRequired": True})
        self.assertEqual(app["signInAudience"], "AzureADMyOrg")
        self.assertEqual(app["web"]["redirectUris"], ["https://old.example/cb", CALLBACK, ARM_RETURN])
        self.assertIs(app["web"]["implicitGrantSettings"]["enableIdTokenIssuance"], True)
        self.assertIn("Left as they were: 1 other redirect address", out)

    def test_an_address_and_a_permission_that_somebody_else_added_survive_an_apply_and_a_second_apply_changes_nothing(self):
        tenant = FakeTenant()
        app, principal = with_strays(tenant)
        code, out, err, _ = run(["apply", *ARGS, "--apply", "--yes"], tenant)
        self.assertEqual((code, err), (0, ""), out)
        method, route, patch = tenant.writes()[0]
        self.assertEqual((method, route), ("PATCH", f"applications/{app['id']}"))
        self.assertEqual(patch["web"]["redirectUris"], [CALLBACK, STRAY_ADDRESS, ARM_RETURN], "what was there, in its order, and then what was missing")
        self.assertEqual(patch["requiredResourceAccess"], [
            {"resourceAppId": es.GRAPH_APP_ID, "resourceAccess": [{"id": es.USER_READ, "type": "Scope"}, STRAY_PERMISSION]},
            OTHER_RESOURCE,
            {"resourceAppId": es.ARM_APP_ID, "resourceAccess": [{"id": es.USER_IMPERSONATION, "type": "Scope"}]}])
        self.assertEqual(app["web"]["redirectUris"], [CALLBACK, STRAY_ADDRESS, ARM_RETURN])
        self.assertIn(STRAY_PERMISSION, app["requiredResourceAccess"][0]["resourceAccess"])
        self.assertIn(OTHER_RESOURCE, app["requiredResourceAccess"])
        self.assertIn("Left as they were: 1 other redirect address, 2 other permissions", out)
        self.assertIn("9 of 9 in order.", out)
        self.assertIn(STRAY_ADDRESS, out.split("Checking again:")[1], "the check afterwards still says that it is there")
        before, kept = len(tenant.writes()), copy.deepcopy(app)
        code, out, _, _ = run(["apply", *ARGS, "--apply", "--yes"], tenant)
        self.assertEqual((code, len(tenant.writes()), "Nothing to make." in out), (0, before, True))
        self.assertEqual(app, kept, "the second apply left the app registration as it was")
        self.assertNotIn("DELETE", {c[0] for c in tenant.calls})

    def test_the_app_registration_is_read_again_right_before_it_is_changed_and_what_was_added_in_between_survives(self):
        tenant = FakeTenant()
        app, _ = tenant.made_by_the_first_version()

        def somebody_adds():
            app["web"]["redirectUris"].append("https://added-while-asking.example/cb")
            app["requiredResourceAccess"][0]["resourceAccess"].append(dict(STRAY_PERMISSION))

        code, out, _, _ = run(["apply", *ARGS, "--apply"], tenant, answers=("yes",), while_asking=somebody_adds)
        self.assertEqual(code, 0, out)
        self.assertEqual(app["web"]["redirectUris"], [CALLBACK, "https://added-while-asking.example/cb", ARM_RETURN])
        self.assertEqual(app["requiredResourceAccess"][0]["resourceAccess"], [{"id": es.USER_READ, "type": "Scope"}, STRAY_PERMISSION])
        calls = [(m, r) for m, r, _ in tenant.calls]
        patch_at = calls.index(("PATCH", f"applications/{app['id']}"))
        self.assertEqual(calls[patch_at - 1], ("GET", "applications"), "the call before the write is the read of the app registration")
        self.assertEqual(calls.count(("GET", "applications")), 6, "the first read, the read before the write, and the check afterwards: each asks for the app registration under its name and under its former name")

    def test_an_app_registration_that_is_gone_or_holds_a_secret_when_it_is_read_again_is_not_changed(self):
        tenant = FakeTenant()
        tenant.made_by_the_first_version()
        code, _, err, _ = run(["apply", *ARGS, "--apply"], tenant, answers=("yes",), while_asking=tenant.apps.clear)
        self.assertEqual((code, tenant.writes()), (1, []))
        self.assertIn("the app registration changed while this ran: nothing was changed", err)
        tenant = FakeTenant()
        app, _ = tenant.made_by_the_first_version()
        code, _, err, _ = run(["apply", *ARGS, "--apply"], tenant, answers=("yes",), while_asking=lambda: app.update(passwordCredentials=[{"keyId": "x"}]))
        self.assertEqual((code, tenant.writes()), (1, []))
        self.assertIn("holds a secret or a certificate", err)
        self.assertIn("nothing was changed", err)

    def test_what_somebody_else_made_in_web_goes_back_as_it_was_read_even_if_a_patch_of_web_replaces_all_of_it(self):
        tenant = FakeTenant()
        app, _ = tenant.made_by_the_first_version()
        app["web"].update(homePageUrl="https://home.example", logoutUrl="https://home.example/logout",
                          implicitGrantSettings={"enableIdTokenIssuance": False, "enableAccessTokenIssuance": True})
        code, out, _, _ = run(["apply", *ARGS, "--apply", "--yes"], tenant)
        self.assertEqual(code, 0, out)
        sent = tenant.writes()[0][2]["web"]
        self.assertEqual(sent, {"homePageUrl": "https://home.example", "logoutUrl": "https://home.example/logout", "redirectUris": [CALLBACK, ARM_RETURN],
                                "implicitGrantSettings": {"enableIdTokenIssuance": True, "enableAccessTokenIssuance": True}})
        self.assertEqual(app["web"], sent, "the fake tenant replaces the whole property, and nothing that was there is gone")

    def test_a_setting_that_has_no_value_is_not_sent_as_one(self):
        cfg = es.read_config(es.argparse.Namespace(tenant_id=TENANT, host=HOST, identity_principal_id=IDENTITY, assign=None))
        app = an_app(id_token=False)
        app["web"].update(homePageUrl=None, logoutUrl="", implicitGrantSettings={"enableIdTokenIssuance": None, "enableAccessTokenIssuance": None})
        self.assertEqual(es.app_changes(app, cfg), {"web": {"redirectUris": [CALLBACK, ARM_RETURN], "implicitGrantSettings": {"enableIdTokenIssuance": True}}})

    def test_only_the_list_that_lacks_something_is_sent(self):
        for lacking, sent in (({"web": {"redirectUris": [CALLBACK], "implicitGrantSettings": {"enableIdTokenIssuance": True}}}, ["web"]),
                              ({"requiredResourceAccess": both_permissions()[:1]}, ["requiredResourceAccess"]),
                              ({"web": {"redirectUris": [CALLBACK, ARM_RETURN], "implicitGrantSettings": {"enableIdTokenIssuance": False}}}, ["web"])):
            tenant = FakeTenant()
            app, _ = tenant.existing_everything()
            app.update(lacking)
            code, out, _, _ = run(["apply", *ARGS, "--apply", "--yes"], tenant)
            self.assertEqual(code, 0, out)
            self.assertEqual([sorted(d) for m, r, d in tenant.writes() if m == "PATCH"], [sent], lacking)

    def test_public_client_flows_that_are_on_are_switched_off_and_nothing_else_of_the_app_is_sent(self):
        tenant = FakeTenant()
        app, _ = tenant.existing_everything()
        app["web"]["redirectUris"] = [CALLBACK, STRAY_ADDRESS, ARM_RETURN]
        app["requiredResourceAccess"] = both_permissions() + [copy.deepcopy(OTHER_RESOURCE)]
        app["isFallbackPublicClient"] = True
        before = copy.deepcopy(app)
        code, out, err, _ = run(["apply", *ARGS, "--apply", "--yes"], tenant)
        self.assertEqual((code, err), (0, ""), out)
        self.assertEqual(tenant.writes(), [("PATCH", f"applications/{app['id']}", {"isFallbackPublicClient": False})], "one change, and it carries only the flag")
        self.assertEqual(app, {**before, "isFallbackPublicClient": False}, "everything else of the app registration is as it was, what somebody else added too")
        self.assertIn("switched public client flows off (isFallbackPublicClient was true)", out)
        self.assertNotIn("changed the app registration", out)
        self.assertIn("9 of 9 in order.", out)
        self.assertRegex(out.split("Checking again:")[1], rf"present +{LABEL_PUBLIC}")
        before_writes = len(tenant.writes())
        code, out, _, _ = run(["apply", *ARGS, "--apply", "--yes"], tenant)
        self.assertEqual((code, len(tenant.writes()), "Nothing to make." in out), (0, before_writes, True))

    def test_the_flag_goes_in_the_one_change_with_the_lists_and_the_lists_still_go_back_with_what_somebody_else_added(self):
        tenant = FakeTenant()
        app, _ = with_strays(tenant)
        app["isFallbackPublicClient"] = True
        code, out, err, _ = run(["apply", *ARGS, "--apply", "--yes"], tenant)
        self.assertEqual((code, err), (0, ""), out)
        patches = [d for m, r, d in tenant.writes() if m == "PATCH"]
        self.assertEqual(len(patches), 1, "one change of the app registration, not one for each thing")
        self.assertEqual(sorted(patches[0]), ["isFallbackPublicClient", "requiredResourceAccess", "web"])
        self.assertIs(patches[0]["isFallbackPublicClient"], False)
        self.assertEqual(patches[0]["web"]["redirectUris"], [CALLBACK, STRAY_ADDRESS, ARM_RETURN])
        self.assertIn(STRAY_PERMISSION, patches[0]["requiredResourceAccess"][0]["resourceAccess"])
        self.assertIn(OTHER_RESOURCE, patches[0]["requiredResourceAccess"])
        self.assertIs(app["isFallbackPublicClient"], False)
        self.assertIn("switched public client flows off (isFallbackPublicClient was true)", out)
        changed = next(line for line in out.splitlines() if "changed the app registration:" in line)
        self.assertNotIn("public client", changed, "the flag has a line of its own")
        self.assertIn("Left as they were: 1 other redirect address, 2 other permissions", changed)

    def test_a_flag_that_is_off_or_not_set_is_never_sent_and_stays_as_it_is(self):
        for how, expected in (("false", False), ("null", None), ("absent", "not there")):
            tenant = FakeTenant()
            app, _ = tenant.made_by_the_first_version()
            if how == "absent":
                del app["isFallbackPublicClient"]
            else:
                app["isFallbackPublicClient"] = expected
            code, out, _, _ = run(["apply", *ARGS, "--apply", "--yes"], tenant)
            self.assertEqual(code, 0, how)
            self.assertEqual([sorted(d) for m, r, d in tenant.writes() if m == "PATCH"], [["requiredResourceAccess", "web"]], how)
            self.assertNotIn("switched public client flows off", out, how)
            self.assertEqual(app.get("isFallbackPublicClient", "not there"), expected, how)

    def test_the_dry_run_for_the_flag_alone_says_so_and_does_not_say_that_the_lists_are_sent_back(self):
        tenant = FakeTenant()
        app, _ = tenant.existing_everything()
        app["isFallbackPublicClient"] = True
        code, out, _, _ = run(["apply", *ARGS], tenant)
        self.assertEqual(code, 1)
        self.assertIn("1 change(s) would be made, and nothing else", out)
        self.assertIn(f"PATCH applications/{app['id']}: public client flows are on (isFallbackPublicClient is true). "
                      "Public client flows are switched off and nothing else of the app is sent", out)
        self.assertNotIn("sent back", out)
        self.assertEqual(tenant.writes(), [])
        tenant = FakeTenant()
        app, _ = tenant.made_by_the_first_version()
        app["isFallbackPublicClient"] = True
        code, out, _, _ = run(["apply", *ARGS], tenant)
        self.assertIn("it does not ask for the delegated permission user_impersonation of Azure Service Management; "
                      "public client flows are on (isFallbackPublicClient is true). "
                      "Every redirect address and permission that is there is sent back with it: nothing is removed", out)
        self.assertEqual(tenant.writes(), [])

    def test_a_flag_that_is_turned_on_while_the_person_is_asked_is_switched_off_too_and_one_that_is_turned_off_is_not_sent(self):
        tenant = FakeTenant()
        app, _ = tenant.made_by_the_first_version()
        code, out, _, _ = run(["apply", *ARGS, "--apply"], tenant, answers=("yes",), while_asking=lambda: app.update(isFallbackPublicClient=True))
        self.assertEqual(code, 0, out)
        self.assertIs(app["isFallbackPublicClient"], False)
        self.assertEqual(sorted(next(d for m, r, d in tenant.writes() if m == "PATCH")), ["isFallbackPublicClient", "requiredResourceAccess", "web"])
        tenant = FakeTenant()
        app, _ = tenant.existing_everything()
        app["isFallbackPublicClient"] = True
        code, out, _, _ = run(["apply", *ARGS, "--apply"], tenant, answers=("yes",), while_asking=lambda: app.update(isFallbackPublicClient=False))
        self.assertEqual((code, tenant.writes()), (0, []))
        self.assertIn("the app registration was in order already", out)

    def test_a_secret_a_certificate_or_another_audience_stops_everything_before_a_change(self):
        for change in ({"passwordCredentials": [{"keyId": "x"}]}, {"keyCredentials": [{"keyId": "x"}]}, {"signInAudience": "AzureADandPersonalMicrosoftAccount"},
                       {"passwordCredentials": [{"keyId": "x"}], "isFallbackPublicClient": True}):
            tenant = FakeTenant()
            tenant.existing_app(**change)
            code, out, _, _ = run(["apply", *ARGS, "--apply", "--yes"], tenant)
            self.assertEqual(code, 1, change)
            self.assertEqual(tenant.writes(), [], change)
            self.assertIn("Nothing can be changed until", out)

    def test_a_secret_on_an_app_that_lacks_the_new_things_still_stops_everything(self):
        tenant = FakeTenant()
        tenant.made_by_the_first_version()
        tenant.apps[0]["passwordCredentials"] = [{"keyId": "x"}]
        code, out, _, _ = run(["apply", *ARGS, "--apply", "--yes"], tenant)
        self.assertEqual((code, tenant.writes()), (1, []))
        self.assertIn("Nothing can be changed until", out)

    def test_a_person_who_may_not_consent_is_told_so_and_gets_the_address_and_everything_else_is_made(self):
        tenant = FakeTenant()
        tenant.refused_consent["user_impersonation"] = (403, {"error": {"code": "Authorization_RequestDenied", "message": f"Insufficient privileges ({FakeTenant.TOKEN})"}})
        code, out, err, sleeps = run(["apply", *ARGS, "--apply", "--yes"], tenant)
        app = tenant.apps[0]
        self.assertEqual(code, 1, "the consent is not in place, and the exit code says so")
        self.assertEqual((err, sleeps), ("", []), "it did not fail: nothing on the error stream, and no pause for a refusal")
        self.assertIn("could not give the administrator's consent for user_impersonation of Azure Service Management: the signed-in person may not give consent "
                      "for the whole tenant (Microsoft Graph answered 403 Authorization_RequestDenied)", out)
        self.assertIn(f"https://login.microsoftonline.com/{TENANT}/adminconsent?client_id={app['appId']}", out)
        self.assertNotIn(FakeTenant.TOKEN, out + err)
        self.assertEqual([r for _, r, _ in tenant.writes()], ["applications", "servicePrincipals", f"applications/{app['id']}/federatedIdentityCredentials",
                                                              f"servicePrincipals/{tenant.principals[-1]['id']}/appRoleAssignedTo", "oauth2PermissionGrants",
                                                              "oauth2PermissionGrants"], "everything else was made, and the consent for User.Read too")
        self.assertEqual([g["scope"] for g in tenant.grants], ["User.Read"])
        self.assertIn("8 of 9 in order.", out)
        self.assertRegex(out, rf"MISSING +{LABEL_CONSENT_ARM}")
        self.assertIn("A tenant administrator gives the missing consent once, for the whole tenant", out)

    def test_after_the_administrator_gave_the_consent_the_next_run_is_in_order_and_makes_nothing_more(self):
        tenant = FakeTenant()
        tenant.refused_consent["user_impersonation"] = FORBIDDEN
        run(["apply", *ARGS, "--apply", "--yes"], tenant)
        principal = tenant.principals[-1]
        tenant.grants.append({"clientId": principal["id"], "consentType": "AllPrincipals", "resourceId": ARM_PRINCIPAL, "scope": "user_impersonation"})
        before = len(tenant.writes())
        code, out, _, _ = run(["apply", *ARGS, "--apply", "--yes"], tenant)
        self.assertEqual((code, len(tenant.writes()), "Nothing to make." in out), (0, before, True))

    def test_a_person_who_may_not_consent_for_either_permission_gets_both_lines_and_the_address_once_more(self):
        tenant = FakeTenant()
        tenant.refused_consent.update({"User.Read": FORBIDDEN, "user_impersonation": FORBIDDEN})
        code, out, err, _ = run(["apply", *ARGS, "--apply", "--yes"], tenant)
        self.assertEqual((code, err, tenant.grants), (1, "", []))
        self.assertEqual(out.count("could not give the administrator's consent"), 2)
        self.assertIn("7 of 9 in order.", out)
        self.assertEqual(out.count("A tenant administrator gives the missing consent once"), 1)

    def test_a_refusal_that_is_not_about_rights_still_stops_at_once(self):
        for scope, made in (("User.Read", []), ("user_impersonation", ["User.Read"])):
            tenant = FakeTenant()
            tenant.refused_consent[scope] = (400, {"error": {"code": "Request_BadRequest", "message": "Property scope is invalid."}})
            code, out, err, sleeps = run(["apply", *ARGS, "--apply", "--yes"], tenant)
            self.assertEqual((code, sleeps), (1, []), scope)
            self.assertIn("Microsoft Graph refused: 400 Request_BadRequest", err)
            self.assertIn("Property scope is invalid.", err)
            self.assertEqual([g["scope"] for g in tenant.grants], made, "what was made before the refusal is there, and the tool did not go on")

    def test_azure_service_management_without_an_enterprise_application_is_not_something_the_tool_makes(self):
        tenant = FakeTenant()
        tenant.principals[:] = [p for p in tenant.principals if p["appId"] != es.ARM_APP_ID]
        code, out, err, _ = run(["apply", *ARGS], tenant)
        self.assertEqual(code, 1)
        self.assertIn("5 change(s) would be made, and nothing else", out)
        self.assertNotIn("consent for user_impersonation of Azure Service Management, for all users", out)
        code, out, err, _ = run(["apply", *ARGS, "--apply", "--yes"], tenant)
        app = tenant.apps[0]
        self.assertEqual((code, err), (1, ""))
        self.assertIn("could not give the administrator's consent for user_impersonation of Azure Service Management: its enterprise application is not in this tenant yet", out)
        self.assertIn(f"adminconsent?client_id={app['appId']}", out)
        self.assertEqual(len([c for c in tenant.writes() if c[0] == "POST" and c[1] == "servicePrincipals"]), 1, "only the enterprise application of the app")
        self.assertEqual([g["scope"] for g in tenant.grants], ["User.Read"])

    def test_when_only_that_consent_is_left_and_the_tool_cannot_make_it_it_says_so_and_changes_nothing(self):
        tenant = FakeTenant()
        app, _ = tenant.existing_everything()
        tenant.principals[:] = [p for p in tenant.principals if p["appId"] != es.ARM_APP_ID]
        tenant.grants[:] = [g for g in tenant.grants if g["resourceId"] != ARM_PRINCIPAL]
        for argv in (["apply", *ARGS], ["apply", *ARGS, "--apply", "--yes"]):
            code, out, err, _ = run(argv, tenant)
            self.assertEqual((code, err, tenant.writes()), (1, "", []), argv)
            self.assertIn("Nothing that this tool can make is missing.", out)
            self.assertIn(f"adminconsent?client_id={app['appId']}", out)
            self.assertNotIn("Nothing to make.", out)

    def test_a_pipeline_may_not_apply_but_a_dry_run_is_allowed(self):
        tenant = FakeTenant()
        code, _, err, _ = run(["apply", *ARGS, "--apply", "--yes"], tenant, env={"GITHUB_ACTIONS": "true"})
        self.assertEqual(code, 1)
        self.assertIn("never a pipeline", err)
        self.assertEqual((tenant.calls, tenant.token_requests), ([], []), "it refused before it asked for a token or read anything")
        code, out, _, _ = run(["apply", *ARGS], tenant, env={"GITHUB_ACTIONS": "true"})
        self.assertIn("dry run", out)
        self.assertEqual(tenant.writes(), [])

    def test_it_asks_first_unless_it_is_told_not_to(self):
        tenant, asked = FakeTenant(), []
        code, out, _, _ = run(["apply", *ARGS, "--apply"], tenant, answers=("yes",), asked=asked)
        self.assertEqual(code, 0, out)
        self.assertIn(TENANT, asked[0])
        tenant = FakeTenant()
        code, _, err, _ = run(["apply", *ARGS, "--apply"], tenant, answers=("no",))
        self.assertEqual((code, tenant.writes()), (1, []))
        self.assertIn("nothing was changed", err)
        tenant = FakeTenant()
        code, _, err, _ = run(["apply", *ARGS, "--apply"], tenant, answers=())
        self.assertEqual((code, tenant.writes()), (1, []))
        self.assertIn("needs --yes", err)

    def test_what_microsoft_entra_does_not_know_yet_is_tried_again_after_a_pause(self):
        tenant = FakeTenant()
        tenant.errors += [("POST", "servicePrincipals", 400, {"error": {"code": "Request_BadRequest", "message": "The appId of the service principal does not reference a valid application object."}}),
                          ("POST", "applications/", 404, {"error": {"code": "Request_ResourceNotFound", "message": "Resource does not exist."}})]
        code, out, _, sleeps = run(["apply", *ARGS, "--apply", "--yes"], tenant)
        self.assertEqual(code, 0, out)
        self.assertEqual(sleeps, [es.READY_SECONDS, es.READY_SECONDS])

    def test_any_other_failure_stops_at_once_and_says_what(self):
        tenant = FakeTenant()
        tenant.errors.append(("POST", "servicePrincipals", 403, {"error": {"code": "Authorization_RequestDenied", "message": "Insufficient privileges to complete the operation."}}))
        code, out, err, sleeps = run(["apply", *ARGS, "--apply", "--yes"], tenant)
        self.assertEqual(code, 1)
        self.assertIn("403 Authorization_RequestDenied", err)
        self.assertEqual(sleeps, [])
        self.assertEqual([r for _, r, _ in tenant.writes()], ["applications", "servicePrincipals"], "it did not go on to the next")

    def test_a_bad_request_that_is_not_about_timing_is_not_tried_again(self):
        tenant = FakeTenant()
        tenant.errors.append(("POST", "applications", 400, {"error": {"code": "Request_BadRequest", "message": "Property displayName is invalid."}}))
        code, _, err, sleeps = run(["apply", *ARGS, "--apply", "--yes"], tenant)
        self.assertEqual((code, sleeps), (1, []))
        self.assertIn("Property displayName is invalid.", err)

    def test_a_busy_service_is_asked_again_once_after_the_pause_it_names(self):
        tenant = FakeTenant()
        tenant.errors.append(("GET", "applications", 429, {"error": {"code": "TooManyRequests", "message": "slow down"}}, {"Retry-After": "7"}))
        code, out, _, sleeps = run(["check", *ARGS], tenant)
        self.assertEqual((code, sleeps), (1, [7.0]))
        self.assertIn("0 of 9 in order.", out)


class TheName(unittest.TestCase):
    """The app registration and its enterprise application are called Meternaut: the name on the Microsoft sign-in screen. Until 2026-11-13 they had another name. The tool finds a
    registration that still has it, says what it would rename, and with --apply sends the display name alone, reads it back and renames the enterprise application if it did not follow."""

    OLD, NEW = "Meternaut console", "Meternaut"

    def test_the_new_name_is_the_one_that_is_made_and_the_old_one_is_only_looked_for(self):
        self.assertEqual((es.APP_NAME, es.FORMER_APP_NAME), (self.NEW, self.OLD))
        self.assertEqual(es.app_body(TheUnions.CFG)["displayName"], self.NEW)
        self.assertEqual(es.CREDENTIAL_NAME, "meternaut-console-auth", "the name of the federated credential is not a display name and stays")
        for select in (es.APP_SELECT, es.PRINCIPAL_SELECT):
            self.assertIn("displayName", select.split(","), "Microsoft Graph sends only what $select names: a name that is not asked for looks like no name")
        tenant = FakeTenant()
        code, out, _, _ = run(["apply", *ARGS, "--apply", "--yes"], tenant)
        self.assertEqual(code, 0, out)
        self.assertEqual((tenant.apps[0]["displayName"], tenant.principals[-1]["displayName"]), (self.NEW, self.NEW))
        self.assertNotIn(self.OLD, json.dumps(tenant.writes()), "nothing that is written has the old name")
        self.assertIn("would rename 'Meternaut console' to 'Meternaut'", " ".join(es.__doc__.split()), "the help says what the dry run says")

    def test_a_registration_with_the_new_name_is_found_and_nothing_is_renamed(self):
        tenant = FakeTenant()
        tenant.existing_everything()
        code, out, _, _ = run(["apply", *ARGS, "--apply", "--yes"], tenant)
        self.assertEqual((code, tenant.writes(), "Nothing to make." in out, "rename" in out), (0, [], True, False))

    def test_a_registration_with_the_old_name_is_found_and_check_says_what_differs_and_writes_nothing(self):
        tenant = FakeTenant()
        tenant.made_before_the_rename()
        code, out, err, _ = run(["check", *ARGS], tenant)
        self.assertEqual((code, err, tenant.writes()), (1, "", []))
        self.assertRegex(out, r"DIFFERS +App registration Meternaut \(client id ")
        self.assertRegex(out, r"DIFFERS +Enterprise application Meternaut, assignment required")
        self.assertEqual(out.count("it is called 'Meternaut console' and is to be called 'Meternaut': apply renames it (the display name alone is sent)"), 2)
        self.assertIn("7 of 9 in order.", out, "the two names are the only things that differ")

    def test_one_registration_of_each_name_stops_the_tool_and_so_do_two_of_one_name(self):
        for names, words in (((self.NEW, self.OLD), "one app registration is called Meternaut and another Meternaut console: the tool cannot tell which one is Meternaut's sign-in"),
                             ((self.OLD, self.OLD), "2 app registrations are called Meternaut console: remove the ones that are not Meternaut's"),
                             ((self.NEW, self.NEW), "2 app registrations are called Meternaut: remove the ones that are not Meternaut's")):
            tenant = FakeTenant()
            for name in names:
                tenant.existing_app(displayName=name)
            code, _, err, _ = run(["apply", *ARGS, "--apply", "--yes"], tenant)
            self.assertEqual((code, tenant.writes()), (1, []), names)
            self.assertIn(words, err)

    def test_the_dry_run_says_that_it_would_rename_and_writes_nothing(self):
        tenant = FakeTenant()
        app, principal = tenant.made_before_the_rename()
        code, out, _, _ = run(["apply", *ARGS], tenant)
        self.assertEqual(code, 1)
        self.assertIn("1 change(s) would be made, and nothing else", out)
        self.assertIn(f"PATCH applications/{app['id']}: would rename 'Meternaut console' to 'Meternaut'. Only the display name is sent: no redirect address, no credential and no permission", out)
        self.assertIn(f"The enterprise application is read again afterwards, and when its name has not followed it is renamed too (PATCH servicePrincipals/{principal['id']}, the display name alone)", out)
        self.assertIn("This was a dry run", out)
        self.assertEqual(tenant.writes(), [])

    def test_apply_sends_the_display_name_alone_reads_it_back_and_renames_the_enterprise_application_that_did_not_follow(self):
        tenant = FakeTenant()
        app, principal = tenant.made_before_the_rename()
        code, out, err, sleeps = run(["apply", *ARGS, "--apply", "--yes"], tenant)
        self.assertEqual((code, err, sleeps), (0, "", []), out)
        self.assertEqual(tenant.writes(), [("PATCH", f"applications/{app['id']}", {"displayName": self.NEW}), ("PATCH", f"servicePrincipals/{principal['id']}", {"displayName": self.NEW})])
        self.assertEqual((app["displayName"], principal["displayName"]), (self.NEW, self.NEW))
        self.assertIn("renamed the app registration from 'Meternaut console' to 'Meternaut': the display name alone was sent, and Microsoft Graph shows the new name", out)
        self.assertIn("the enterprise application's name did not follow, so it was renamed too, from 'Meternaut console' to 'Meternaut': the display name alone was sent", out)
        self.assertIn("9 of 9 in order.", out)
        calls = [(method, route) for method, route, _ in tenant.calls]
        at = calls.index(("PATCH", f"applications/{app['id']}"))
        self.assertEqual(calls[at + 1:at + 3], [("GET", "applications"), ("GET", "servicePrincipals")], "the new name is read back, and then the enterprise application is read")

    def test_an_enterprise_application_that_followed_is_left_alone(self):
        tenant = FakeTenant()
        tenant.sp_follows = True
        app, principal = tenant.made_before_the_rename()
        code, out, _, _ = run(["apply", *ARGS, "--apply", "--yes"], tenant)
        self.assertEqual(code, 0, out)
        self.assertEqual(tenant.writes(), [("PATCH", f"applications/{app['id']}", {"displayName": self.NEW})])
        self.assertIn("the enterprise application's name followed: it is called 'Meternaut' too", out)
        self.assertNotIn("did not follow", out)

    def test_a_second_run_changes_nothing_and_says_so(self):
        for follows in (False, True):
            tenant = FakeTenant()
            tenant.sp_follows = follows
            tenant.made_before_the_rename()
            run(["apply", *ARGS, "--apply", "--yes"], tenant)
            before, kept = len(tenant.writes()), copy.deepcopy((tenant.apps, tenant.principals))
            code, out, _, _ = run(["apply", *ARGS, "--apply", "--yes"], tenant)
            self.assertEqual((code, len(tenant.writes()), "Nothing to make." in out, "rename" in out), (0, before, True, False), follows)
            self.assertEqual((tenant.apps, tenant.principals), kept)
            code, out, _, _ = run(["check", *ARGS], tenant)
            self.assertEqual((code, "9 of 9 in order." in out), (0, True))

    def test_an_enterprise_application_with_another_name_is_renamed_alone_when_the_registration_has_the_name_already(self):
        tenant = FakeTenant()
        _, principal = tenant.existing_everything()
        principal["displayName"] = self.OLD
        code, out, _, _ = run(["apply", *ARGS], tenant)
        self.assertEqual(code, 1)
        self.assertIn("1 change(s) would be made, and nothing else", out)
        self.assertIn(f"PATCH servicePrincipals/{principal['id']}: would rename 'Meternaut console' to 'Meternaut'. Only the display name is sent", out)
        self.assertEqual(tenant.writes(), [])
        code, out, _, _ = run(["apply", *ARGS, "--apply", "--yes"], tenant)
        self.assertEqual(code, 0, out)
        self.assertEqual(tenant.writes(), [("PATCH", f"servicePrincipals/{principal['id']}", {"displayName": self.NEW})])
        self.assertIn("renamed the enterprise application from 'Meternaut console' to 'Meternaut': the display name alone was sent", out)
        code, out, _, _ = run(["apply", *ARGS, "--apply", "--yes"], tenant)
        self.assertEqual((code, len(tenant.writes()), "Nothing to make." in out), (0, 1, True))

    def test_the_name_goes_first_and_alone_and_what_else_is_missing_is_a_change_of_its_own(self):
        tenant = FakeTenant()
        app, principal = tenant.made_before_the_rename()
        app["web"]["redirectUris"] = [CALLBACK]
        principal["appRoleAssignmentRequired"] = False
        code, out, _, _ = run(["apply", *ARGS, "--apply", "--yes"], tenant)
        self.assertEqual(code, 0, out)
        writes = tenant.writes()
        self.assertEqual(writes[0], ("PATCH", f"applications/{app['id']}", {"displayName": self.NEW}))
        self.assertEqual((writes[1][:2], sorted(writes[1][2])), (("PATCH", f"applications/{app['id']}"), ["web"]), "the redirect address goes in a change that carries no name")
        self.assertEqual(writes[2:], [("PATCH", f"servicePrincipals/{principal['id']}", {"displayName": self.NEW}),
                                       ("PATCH", f"servicePrincipals/{principal['id']}", {"appRoleAssignmentRequired": True})], "the name that did not follow, and then the rest")
        self.assertEqual(app["web"]["redirectUris"], [CALLBACK, ARM_RETURN])

    def test_nothing_but_the_two_names_changes(self):
        tenant = FakeTenant()
        tenant.made_before_the_rename()

        def without_names(state):
            return [[{key: value for key, value in item.items() if key != "displayName"} for item in group] for group in state[:2]] + list(state[2:])

        before = copy.deepcopy((tenant.apps, tenant.principals, tenant.credentials, tenant.assigned, tenant.grants))
        run(["apply", *ARGS, "--apply", "--yes"], tenant)
        after = (tenant.apps, tenant.principals, tenant.credentials, tenant.assigned, tenant.grants)
        self.assertEqual(without_names(after), without_names(before), "no redirect address, credential, permission, assignment or consent was touched")
        self.assertEqual([item["displayName"] for item in tenant.apps + tenant.principals[2:]], [self.NEW, self.NEW])

    def test_a_secret_or_a_certificate_stops_everything_before_the_name_is_changed(self):
        tenant = FakeTenant()
        app, _ = tenant.made_before_the_rename()
        app["passwordCredentials"] = [{"keyId": "x"}]
        code, out, _, _ = run(["apply", *ARGS, "--apply", "--yes"], tenant)
        self.assertEqual((code, tenant.writes(), app["displayName"]), (1, [], self.OLD))
        self.assertIn("Nothing can be changed until", out)

    def test_a_pipeline_changes_no_name(self):
        tenant = FakeTenant()
        app, principal = tenant.made_before_the_rename()
        code, _, err, _ = run(["apply", *ARGS, "--apply", "--yes"], tenant, env={"GITHUB_ACTIONS": "true"})
        self.assertEqual((code, tenant.calls, (app["displayName"], principal["displayName"])), (1, [], (self.OLD, self.OLD)))
        self.assertIn("never a pipeline", err)

    def test_a_refusal_of_the_rename_stops_at_once_and_the_enterprise_application_is_not_touched(self):
        tenant = FakeTenant()
        app, principal = tenant.made_before_the_rename()
        tenant.errors.append(("PATCH", "applications/", 403, {"error": {"code": "Authorization_RequestDenied", "message": "Insufficient privileges to complete the operation."}}))
        code, _, err, _ = run(["apply", *ARGS, "--apply", "--yes"], tenant)
        self.assertEqual(code, 1)
        self.assertIn("Microsoft Graph refused: 403 Authorization_RequestDenied", err)
        self.assertEqual([(method, route.split("/")[0]) for method, route, _ in tenant.writes()], [("PATCH", "applications")], "the one change that was refused, and nothing after it")
        self.assertEqual((app["displayName"], principal["displayName"]), (self.OLD, self.OLD))

    def test_a_name_that_is_not_seen_at_once_is_read_again_after_a_pause_and_one_that_is_never_seen_stops_the_run(self):
        tenant = FakeTenant()
        tenant.stale_reads = 2
        tenant.made_before_the_rename()
        code, out, _, sleeps = run(["apply", *ARGS, "--apply", "--yes"], tenant)
        self.assertEqual((code, sleeps), (0, [es.READY_SECONDS, es.READY_SECONDS]), out)
        self.assertEqual(len(tenant.writes()), 2, "one name for the registration, one for the enterprise application: no change is sent twice")
        tenant = FakeTenant()
        tenant.stale_reads = 99
        app, principal = tenant.made_before_the_rename()
        code, _, err, sleeps = run(["apply", *ARGS, "--apply", "--yes"], tenant)
        self.assertEqual((code, len(sleeps)), (1, es.READY_TRIES - 1))
        self.assertIn("the new name 'Meternaut' was sent, and Microsoft Graph still shows the app registration as 'Meternaut console'. Nothing else was changed", err)
        self.assertEqual([route.split("/")[0] for _, route, _ in tenant.writes()], ["applications"], "the enterprise application waits for the next run")
        self.assertEqual(principal["displayName"], self.OLD)

    def test_every_call_of_a_rename_is_on_the_list_and_none_deletes(self):
        for follows in (False, True):
            tenant = FakeTenant()
            tenant.sp_follows = follows
            tenant.made_before_the_rename()
            run(["apply", *ARGS, "--apply", "--yes"], tenant)
            self.assertNotIn("DELETE", {call[0] for call in tenant.calls})
            for method, route, _ in tenant.calls:
                self.assertTrue(any(m == method and p.fullmatch(route) for m, p in es.CALLS), f"{method} {route}")


class TheUnions(unittest.TestCase):
    CFG = es.Config(TENANT, HOST, IDENTITY, (PERSON,))

    def test_addresses_that_are_there_stay_in_their_order_and_the_missing_ones_follow_and_case_does_not_matter(self):
        self.assertEqual(es.union_addresses(["https://b.example/x", "HTTPS://A.EXAMPLE/x"], ["https://a.example/x", "https://c.example/x"]),
                         ["https://b.example/x", "HTTPS://A.EXAMPLE/x", "https://c.example/x"])
        self.assertEqual(es.union_addresses([], ["https://a.example/x"]), ["https://a.example/x"])
        there = ["https://one.example/x"]
        es.union_addresses(there, ["https://two.example/x"])
        self.assertEqual(there, ["https://one.example/x"], "what is passed in is not changed")

    def test_permissions_are_united_per_resource_by_id_and_by_type_and_what_is_there_keeps_its_form(self):
        there = [{"resourceAppId": "AAAA", "resourceAccess": [{"id": "X1", "type": "Scope"}, {"id": "Y1", "type": "Role"}]},
                 {"resourceAppId": "bbbb", "resourceAccess": [{"id": "Z1", "type": "Scope"}]}]
        wanted = [{"resourceAppId": "aaaa", "resourceAccess": [{"id": "x1", "type": "Scope"}, {"id": "X1", "type": "Role"}]},
                  {"resourceAppId": "cccc", "resourceAccess": [{"id": "W1", "type": "Scope"}]}]
        self.assertEqual(es.union_access(there, wanted), [
            {"resourceAppId": "AAAA", "resourceAccess": [{"id": "X1", "type": "Scope"}, {"id": "Y1", "type": "Role"}, {"id": "X1", "type": "Role"}]},
            {"resourceAppId": "bbbb", "resourceAccess": [{"id": "Z1", "type": "Scope"}]},
            {"resourceAppId": "cccc", "resourceAccess": [{"id": "W1", "type": "Scope"}]}])

    def test_two_entries_for_one_resource_become_one_and_nothing_in_them_is_lost(self):
        there = [{"resourceAppId": "aaaa", "resourceAccess": [{"id": "X1", "type": "Scope"}]},
                 {"resourceAppId": "AAAA", "resourceAccess": [{"id": "Y1", "type": "Scope"}, {"id": "X1", "type": "Scope"}]}]
        self.assertEqual(es.union_access(there, []), [{"resourceAppId": "aaaa", "resourceAccess": [{"id": "X1", "type": "Scope"}, {"id": "Y1", "type": "Scope"}]}])

    def test_other_properties_of_an_entry_are_kept_and_the_inputs_and_the_wanted_list_are_not_changed(self):
        there = [{"resourceAppId": "aaaa", "@odata.type": "#microsoft.graph.requiredResourceAccess", "resourceAccess": [{"id": "X1", "type": "Scope"}]}]
        before, wanted_before = copy.deepcopy(there), copy.deepcopy(es.WANTED_ACCESS)
        united = es.union_access(there, es.WANTED_ACCESS)
        self.assertEqual(united[0]["@odata.type"], "#microsoft.graph.requiredResourceAccess")
        united[0]["resourceAccess"].append({"id": "changed", "type": "Scope"})
        united[1]["resourceAccess"].append({"id": "changed", "type": "Scope"})
        self.assertEqual((there, es.WANTED_ACCESS), (before, wanted_before))

    def test_nothing_there_gives_what_is_wanted_and_a_resource_without_a_list_gets_an_empty_one(self):
        self.assertEqual(es.union_access([], es.WANTED_ACCESS), list(es.WANTED_ACCESS))
        self.assertEqual(es.union_access([{"resourceAppId": "q"}], []), [{"resourceAppId": "q", "resourceAccess": []}])

    def test_the_body_of_a_new_app_registration_is_the_wanted_lists_and_does_not_share_them(self):
        body = es.app_body(self.CFG)
        self.assertEqual(body["requiredResourceAccess"], list(es.WANTED_ACCESS))
        body["requiredResourceAccess"][0]["resourceAccess"].append({"id": "changed", "type": "Scope"})
        self.assertNotIn({"id": "changed", "type": "Scope"}, es.WANTED_ACCESS[0]["resourceAccess"])

    def test_a_new_app_registration_is_made_as_a_confidential_client(self):
        self.assertIs(es.app_body(self.CFG)["isFallbackPublicClient"], False)

    def test_a_change_is_sent_exactly_when_something_is_missing_and_it_adds_and_removes_nothing_and_a_second_one_is_not_needed(self):
        for flags in itertools.product((True, False), repeat=7):
            callback, arm_return, id_token, user_read, impersonation, strays, public_client = flags
            app = an_app(callback, arm_return, id_token, user_read, impersonation, strays, public_client)
            review = es.review_app(app, self.CFG)
            changes = es.app_changes(app, self.CFG)
            self.assertEqual(bool(changes), not (callback and arm_return and id_token and user_read and impersonation) or public_client, flags)
            self.assertEqual(bool(changes), bool(review.fixable(self.CFG)), flags)
            self.assertLessEqual(set(changes), {"web", "requiredResourceAccess", "isFallbackPublicClient"}, "nothing else of the app registration is ever sent")
            self.assertEqual(changes.get("isFallbackPublicClient", "not sent"), False if public_client else "not sent", "the flag is sent as false, and only when it is on")
            self.assertEqual("web" in changes, not (callback and arm_return and id_token), flags)
            self.assertEqual("requiredResourceAccess" in changes, not (user_read and impersonation), flags)
            after = {**app, **changes}
            self.assertEqual(es.review_app(after, self.CFG).fixable(self.CFG), [], flags)
            self.assertEqual(es.app_changes(after, self.CFG), {}, flags)
            self.assertLessEqual({u.lower() for u in app["web"]["redirectUris"]}, {u.lower() for u in after["web"]["redirectUris"]}, flags)
            self.assertLessEqual(es.permissions_of(app), es.permissions_of(after), flags)
            self.assertEqual(sorted(es.review_app(after, self.CFG).other_addresses), sorted(review.other_addresses), flags)
            self.assertEqual(es.review_app(after, self.CFG).other_permissions, review.other_permissions, flags)


class TheCallsOfTheTool(unittest.TestCase):
    # The names of the sub-command teams-bot (replaced by the owner's ruling of 2026-11-13, his plain yes of 2026-11-13): tests/test_teams_bot_tools.py tests them.
    TEAMS_BOT_NAMES = {"TEAMS_APP_NAME", "TEAMS_APP_SELECT", "TEAMS_CALLS", "TEAMS_CREDENTIAL_NAME", "TEAMS_IDENTITY_NAME", "TEAMS_REPOSITORY", "TeamsConfig", "TeamsState", "command_teams_bot", "examine_teams", "read_teams_config",
                       "teams_apply", "teams_credential_matches", "teams_final", "teams_plan", "teams_problems", "teams_report"}

    def test_nothing_is_deleted_and_no_secret_is_made(self):
        self.assertEqual({m for m, _ in es.CALLS}, {"GET", "POST", "PATCH"})
        for _, pattern in es.CALLS:
            self.assertNotRegex(pattern.pattern, r"addPassword|addKey|keyCredentials|passwordCredentials|owners|directoryRoles")

    def test_the_tool_has_nothing_to_do_with_teams_the_cards_are_posted_by_a_flow_and_need_no_registration_or_permission(self):
        for _, pattern in es.CALLS:
            self.assertNotRegex(pattern.pattern, r"(?i)teams|installedApps|appCatalogs|teamwork")
        self.assertEqual(sorted({pattern.pattern.split("/")[0] for _, pattern in es.CALLS}), ["applications", "oauth2PermissionGrants", "servicePrincipals"])
        self.assertFalse([name for name in dir(es) if "teams" in name.lower() and name not in self.TEAMS_BOT_NAMES],
                         "nothing about Teams but the sub-command teams-bot (replaced by the owner's ruling of 2026-11-13, his plain yes of 2026-11-13)")
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            es.main(["teams-check", "--tenant-id", TENANT])

    def test_a_call_that_is_not_on_the_list_is_refused_before_it_is_sent(self):
        tenant = FakeTenant()
        graph = es.Graph(es.Tokens(tenant.az, TENANT, es.Hider()), tenant.transport, lambda s: None)
        for method, route in (("DELETE", "applications/00000000-0000-4000-8000-000000000001"), ("POST", "applications/00000000-0000-4000-8000-000000000001/addPassword"),
                              ("GET", "users"), ("PATCH", "applications")):
            with self.assertRaises(es.Problem, msg=f"{method} {route}"):
                graph.send(method, route, {})
        self.assertEqual(tenant.calls, [])

    def test_every_call_of_a_whole_run_is_on_the_list(self):
        tenant = FakeTenant()
        run(["apply", *ARGS, "--apply", "--yes"], tenant)
        self.assertGreater(len(tenant.calls), 5)
        for method, route, _ in tenant.calls:
            self.assertTrue(any(m == method and p.fullmatch(route) for m, p in es.CALLS), f"{method} {route}")

    def test_no_run_of_the_new_version_sends_a_delete_or_asks_for_anything_that_the_old_one_did_not(self):
        for prepare in (lambda t: None, lambda t: t.made_by_the_first_version(), lambda t: t.existing_everything(), with_strays, lambda t: t.made_before_the_rename(),
                        lambda t: t.existing_everything()[0].update(isFallbackPublicClient=True)):
            tenant = FakeTenant()
            prepare(tenant)
            run(["apply", *ARGS, "--apply", "--yes"], tenant)
            self.assertNotIn("DELETE", {c[0] for c in tenant.calls})
            for method, route, _ in tenant.calls:
                self.assertTrue(any(m == method and p.fullmatch(route) for m, p in es.CALLS), f"{method} {route}")

    def test_nothing_that_was_in_the_tenant_before_a_run_is_gone_after_it(self):
        for prepare in (lambda t: t.made_by_the_first_version(), with_strays, lambda t: t.made_before_the_rename()):
            tenant = FakeTenant()
            app, _ = prepare(tenant)
            before = {"addresses": list(app["web"]["redirectUris"]), "permissions": es.permissions_of(app), "grants": [dict(g) for g in tenant.grants]}
            run(["apply", *ARGS, "--apply", "--yes"], tenant)
            self.assertTrue(set(before["addresses"]) <= set(app["web"]["redirectUris"]))
            self.assertTrue(before["permissions"] <= es.permissions_of(app))
            self.assertTrue(all(g in tenant.grants for g in before["grants"]))


class TheConsoleOnThePlatformsGateway(unittest.TestCase):
    """Behind the platform's Application Gateway the function app is opened on a host name of its own (docs/proposals/07-private-by-default.md, phase 3 for the cases app). Both return addresses then name that
    host, which is the one the sign-in sends a person back to. This tool needs no new option for it: --host is the name that people open. It adds the addresses of the new host in one change and removes
    nothing, so the addresses of the app's own name, which a closed app no longer answers on, stay until a person removes them in the portal."""

    GATEWAY_HOST = "console.example.com"
    ARGS = ["--tenant-id", TENANT, "--host", GATEWAY_HOST, "--identity-principal-id", IDENTITY, "--assign", PERSON]
    NEW = [f"https://{GATEWAY_HOST}/.auth/login/aad/callback", f"https://{GATEWAY_HOST}/arm/return"]

    def test_the_two_return_addresses_of_the_gateway_s_host_are_asked_for_and_the_ones_of_the_apps_own_name_are_a_note(self):
        tenant = FakeTenant()
        tenant.existing_everything()
        code, out, _, _ = run(["check", *self.ARGS], tenant)
        self.assertEqual(code, 1)
        self.assertIn(f"the redirect address {self.NEW[0]} of the platform's sign-in is missing", out)
        self.assertRegex(out, rf"MISSING +{LABEL_RETURN} {re.escape(self.NEW[1])}")
        self.assertIn("7 of 9 in order.", out)
        self.assertIn(f"left alone because this tool removes nothing: redirect addresses {CALLBACK}, {ARM_RETURN}", out)
        self.assertEqual(tenant.writes(), [])

    def test_one_change_adds_the_two_addresses_of_the_gateway_s_host_after_the_ones_that_are_there_and_removes_nothing(self):
        tenant = FakeTenant()
        app, _ = tenant.existing_everything()
        code, out, _, _ = run(["apply", *self.ARGS, "--apply", "--yes"], tenant)
        self.assertEqual(code, 0, out)
        (change,) = tenant.writes()
        self.assertEqual((change[0], change[1]), ("PATCH", f"applications/{app['id']}"))
        self.assertEqual(change[2]["web"]["redirectUris"], [CALLBACK, ARM_RETURN, *self.NEW], "what is there stays, in its order, and the new addresses follow")
        self.assertEqual(sorted(change[2]), ["web"], "nothing else of the app is sent: the permissions, the credential and the people are in order already")
        self.assertIn("Left as they were: 2 other redirect addresses", out)
        self.assertIn("9 of 9 in order.", out)
        self.assertNotIn("DELETE", {call[0] for call in tenant.calls})
        code, out, _, _ = run(["apply", *self.ARGS, "--apply", "--yes"], tenant)
        self.assertEqual((code, "Nothing to make." in out), (0, True), "a second run has nothing to add")

    def test_a_host_name_in_capitals_is_the_same_host_and_the_apps_own_name_still_works_as_before(self):
        cfg = es.read_config(es.argparse.Namespace(tenant_id=TENANT, host=self.GATEWAY_HOST.upper(), identity_principal_id=IDENTITY, assign=None))
        self.assertEqual((cfg.callback, cfg.arm_return), tuple(self.NEW))
        tenant = FakeTenant()
        tenant.existing_everything()
        code, out, _, _ = run(["check", *ARGS], tenant)
        self.assertEqual((code, "9 of 9 in order." in out), (0, True), "the default is what it was")

    def test_the_help_says_that_the_host_is_the_name_that_people_open_and_the_tool_still_makes_only_the_calls_of_its_list(self):
        source = (ROOT / "tools" / "entra-setup.py").read_text(encoding="utf-8")
        self.assertIn("the host name that people open: the function app's host name on the platform's Application Gateway (the variable CONSOLE_HOST_NAME), or the function app's own name", source)
        self.assertIn("It only adds the addresses of the new host: the addresses of the app's own name stay", source)
        tenant = FakeTenant()
        run(["apply", *self.ARGS, "--apply", "--yes"], tenant)
        for method, route, _ in tenant.calls:
            self.assertTrue(any(m == method and p.fullmatch(route) for m, p in es.CALLS), f"{method} {route}")


if __name__ == "__main__":
    unittest.main()
