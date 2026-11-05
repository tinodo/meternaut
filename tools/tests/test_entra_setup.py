import contextlib
import importlib.util
import io
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
CALLBACK = f"https://{HOST}/.auth/login/aad/callback"
ARGS = ["--tenant-id", TENANT, "--host", HOST, "--identity-principal-id", IDENTITY, "--assign", PERSON]


class FakeTenant:
    """A small model of the parts of a Microsoft Entra tenant that the tool reads and changes, and a record of every call."""

    TOKEN = "eyJhbGciOiJSUzI1NiJ9.eyJhdWQiOiJ0ZXN0In0.c2lnbmF0dXJlLW9mLXRoZS10ZXN0"

    def __init__(self):
        self.apps, self.principals, self.credentials, self.assigned, self.grants = [], [{"id": GRAPH_PRINCIPAL, "appId": es.GRAPH_APP_ID}], {}, {}, []
        self.calls, self.token_requests, self.errors, self.page_size, self.counter = [], [], [], None, 0

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
        app = {"id": self.new_id(), "appId": self.new_id(), "displayName": es.APP_NAME, "signInAudience": es.THIS_TENANT_ONLY,
               "web": {"redirectUris": [CALLBACK], "implicitGrantSettings": {"enableIdTokenIssuance": True}},
               "requiredResourceAccess": [{"resourceAppId": es.GRAPH_APP_ID, "resourceAccess": [{"id": es.USER_READ, "type": "Scope"}]}],
               "passwordCredentials": [], "keyCredentials": []}
        app.update(changes)
        self.apps.append(app)
        return app

    def existing_everything(self, people=(PERSON,)):
        app = self.existing_app()
        principal = {"id": self.new_id(), "appId": app["appId"], "appRoleAssignmentRequired": True}
        self.principals.append(principal)
        self.credentials[app["id"]] = [{"name": es.CREDENTIAL_NAME, "issuer": f"https://login.microsoftonline.com/{TENANT}/v2.0", "subject": IDENTITY,
                                        "audiences": [es.AUDIENCE]}]
        self.assigned[principal["id"]] = [{"principalId": p} for p in people]
        self.grants.append({"clientId": principal["id"], "consentType": "AllPrincipals", "resourceId": GRAPH_PRINCIPAL, "scope": "User.Read"})
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
                return self.answer(200, {"value": filtered(self.apps)})
            app = dict(data, id=self.new_id(), appId=self.new_id(), passwordCredentials=[], keyCredentials=[])
            self.apps.append(app)
            return self.answer(201, app)
        found = match(r"applications/([0-9a-f-]+)")
        if found and method == "PATCH":
            app = next(a for a in self.apps if a["id"] == found.group(1))
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
                return self.answer(200, {"value": filtered(self.principals)})
            principal = dict(data, id=self.new_id())
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
            self.grants.append(data)
            return self.answer(201, data)
        raise AssertionError(f"the tool sent a call that the model does not know: {method} {route}")

    @staticmethod
    def filter_matches(expression, item):
        if not expression:
            return True
        found = re.fullmatch(r"(\w+) eq '([^']*)'", expression)
        assert found, expression
        return item.get(found.group(1)) == found.group(2)


def run(argv, tenant, env=None, answers=("yes",), asked=None):
    lines, errors, sleeps = [], io.StringIO(), []
    answers = list(answers)

    def ask(prompt):
        if asked is not None:
            asked.append(prompt)
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


class Check(unittest.TestCase):
    def test_an_empty_tenant_misses_everything_and_nothing_is_written(self):
        tenant = FakeTenant()
        code, out, _, _ = run(["check", *ARGS], tenant)
        self.assertEqual(code, 1)
        self.assertEqual(out.count("MISSING"), 5)
        self.assertIn("0 of 5 in order.", out)
        self.assertEqual(tenant.writes(), [])
        self.assertNotIn("Client id of the app registration", out)

    def test_a_tenant_that_is_in_order_says_so_and_prints_the_client_id(self):
        tenant = FakeTenant()
        app, _ = tenant.existing_everything()
        code, out, _, _ = run(["check", *ARGS], tenant)
        self.assertEqual(code, 0, out)
        self.assertIn("5 of 5 in order.", out)
        self.assertIn(f"CONSOLE_APP_CLIENT_ID): {app['appId']}", out)
        self.assertEqual(tenant.writes(), [])

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
            ({"web": {"redirectUris": [CALLBACK, "https://elsewhere.example/cb"], "implicitGrantSettings": {"enableIdTokenIssuance": True}}}, "redirect addresses"),
            ({"web": {"redirectUris": [CALLBACK], "implicitGrantSettings": {"enableIdTokenIssuance": False}}}, "ID token issuance is off"),
            ({"requiredResourceAccess": []}, "User.Read"),
            ({"requiredResourceAccess": [{"resourceAppId": es.GRAPH_APP_ID, "resourceAccess": [{"id": es.USER_READ, "type": "Scope"},
                                                                                              {"id": "11111111-1111-1111-1111-111111111111", "type": "Role"}]}]}, "nothing else"),
        ):
            tenant = FakeTenant()
            tenant.existing_app(**change)
            code, out, _, _ = run(["check", *ARGS], tenant)
            self.assertEqual(code, 1, change)
            self.assertIn("DIFFERS", out, change)
            self.assertIn(word, out, change)

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
        tenant.grants[0]["consentType"] = "Principal"
        code, out, _, _ = run(["check", *ARGS], tenant)
        self.assertEqual(code, 1)
        self.assertRegex(out, rf"MISSING +Assignment of {PERSON}")
        self.assertRegex(out, r"MISSING +Consent of the administrator")

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
        self.assertIn("5 change(s) would be made, and nothing else", out)
        self.assertIn("This was a dry run", out)
        self.assertEqual(tenant.writes(), [])

    def test_apply_makes_everything_in_order_with_no_secret_and_checks_again(self):
        tenant = FakeTenant()
        code, out, _, sleeps = run(["apply", *ARGS, "--apply", "--yes"], tenant)
        self.assertEqual(code, 0, out)
        self.assertEqual([(m, r.split("/")[0] + ("/" + r.split("/")[2] if r.count("/") > 1 else "")) for m, r, _ in tenant.writes()],
                         [("POST", "applications"), ("POST", "servicePrincipals"), ("POST", "applications/federatedIdentityCredentials"),
                          ("POST", "servicePrincipals/appRoleAssignedTo"), ("POST", "oauth2PermissionGrants")])
        app = tenant.apps[0]
        self.assertEqual((app["displayName"], app["signInAudience"]), (es.APP_NAME, "AzureADMyOrg"))
        self.assertEqual(app["web"]["redirectUris"], [CALLBACK])
        self.assertIs(app["web"]["implicitGrantSettings"]["enableIdTokenIssuance"], True)
        self.assertEqual(app["requiredResourceAccess"], [{"resourceAppId": es.GRAPH_APP_ID, "resourceAccess": [{"id": es.USER_READ, "type": "Scope"}]}])
        self.assertFalse(any(k in app and app[k] for k in ("passwordCredentials", "keyCredentials")), "the app has no secret and no certificate")
        self.assertFalse(any("passwordCredentials" in (d or {}) or "keyCredentials" in (d or {}) or "addPassword" in r for _, r, d in tenant.writes()))
        principal = tenant.principals[-1]
        self.assertEqual((principal["appId"], principal["appRoleAssignmentRequired"]), (app["appId"], True))
        credential = tenant.credentials[app["id"]][0]
        self.assertEqual((credential["issuer"], credential["subject"], credential["audiences"]),
                         (f"https://login.microsoftonline.com/{TENANT}/v2.0", IDENTITY, ["api://AzureADTokenExchange"]))
        self.assertEqual(tenant.assigned[principal["id"]], [{"principalId": PERSON}])
        self.assertEqual(tenant.grants[-1], {"clientId": principal["id"], "consentType": "AllPrincipals", "resourceId": GRAPH_PRINCIPAL, "scope": "User.Read"})
        self.assertTrue(out.rstrip().splitlines()[-2].endswith("5 of 5 in order."))
        self.assertIn(f"CONSOLE_APP_CLIENT_ID): {app['appId']}", out)
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
        self.assertEqual(sorted(r.split("/")[-1] for _, r, _ in tenant.writes()), ["appRoleAssignedTo", "appRoleAssignedTo", "oauth2PermissionGrants"])
        self.assertEqual(len(tenant.apps), 1)

    def test_what_the_tool_owns_is_changed_and_nothing_else_of_the_app(self):
        tenant = FakeTenant()
        app, principal = tenant.existing_everything()
        app["web"] = {"redirectUris": ["https://old.example/cb"], "implicitGrantSettings": {"enableIdTokenIssuance": False}}
        principal["appRoleAssignmentRequired"] = False
        code, out, _, _ = run(["apply", *ARGS, "--apply", "--yes"], tenant)
        self.assertEqual(code, 0, out)
        changes = [(m, r, d) for m, r, d in tenant.writes()]
        self.assertEqual([(m, r) for m, r, _ in changes], [("PATCH", f"applications/{app['id']}"), ("PATCH", f"servicePrincipals/{principal['id']}")])
        self.assertEqual(sorted(changes[0][2]), ["requiredResourceAccess", "web"])
        self.assertEqual(changes[1][2], {"appRoleAssignmentRequired": True})
        self.assertEqual(app["signInAudience"], "AzureADMyOrg")

    def test_a_secret_a_certificate_or_another_audience_stops_everything_before_a_change(self):
        for change in ({"passwordCredentials": [{"keyId": "x"}]}, {"keyCredentials": [{"keyId": "x"}]}, {"signInAudience": "AzureADandPersonalMicrosoftAccount"}):
            tenant = FakeTenant()
            tenant.existing_app(**change)
            code, out, _, _ = run(["apply", *ARGS, "--apply", "--yes"], tenant)
            self.assertEqual(code, 1, change)
            self.assertEqual(tenant.writes(), [], change)
            self.assertIn("Nothing can be changed until", out)

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
        self.assertIn("0 of 5 in order.", out)


class TheCallsOfTheTool(unittest.TestCase):
    def test_nothing_is_deleted_and_no_secret_is_made(self):
        self.assertEqual({m for m, _ in es.CALLS}, {"GET", "POST", "PATCH"})
        for _, pattern in es.CALLS:
            self.assertNotRegex(pattern.pattern, r"addPassword|addKey|keyCredentials|passwordCredentials|owners|directoryRoles")

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


if __name__ == "__main__":
    unittest.main()
