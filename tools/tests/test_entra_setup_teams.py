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


def load(name, file):
    spec = importlib.util.spec_from_file_location(name, ROOT / "tools" / file)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


es = load("entra_setup_of_the_teams_tests", "entra-setup.py")
tp = load("teams_package_of_the_entra_tests", "teams-package.py")

TENANT = "11111111-2222-3333-4444-555555555555"
BOT = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
PERSON = "bbbbbbbb-cccc-dddd-eeee-ffffffffffff"
SECOND_PERSON = "cccccccc-dddd-eeee-ffff-000000000000"
APP = tp.app_id_of(BOT)
CATALOG_ID = "99999999-0000-4000-8000-000000000042"
ARGS = ["--tenant-id", TENANT, "--bot-id", BOT, "--assign", PERSON]
FORBIDDEN = (403, {"error": {"code": "Authorization_RequestDenied", "message": "Insufficient privileges to complete the operation."}})
HINT_POLICY = "app setup policy in the Teams admin center"


class FakeTeams:
    """The parts of Microsoft Graph that the Teams commands read and change, and a record of every call. Only what $select and $expand name is returned, as Graph does:
    a property that the tool forgot to ask for is never there to read."""

    TOKEN = "fake-graph-token-0123456789"

    def __init__(self):
        self.principals, self.catalog, self.installs, self.refusals = [], [], {}, []
        self.calls, self.queries, self.token_requests = [], [], []
        self.page_size, self.counter = None, 0

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

    def the_bot(self, kind="ManagedIdentity"):
        principal = {"id": self.new_id(), "appId": BOT, "servicePrincipalType": kind, "displayName": "id-example-bot"}
        self.principals.append(principal)
        return principal

    def the_app(self, external_id=APP, distribution="organization", catalog_id=CATALOG_ID):
        app = {"id": catalog_id, "externalId": external_id, "distributionMethod": distribution, "displayName": "Example app"}
        self.catalog.append(app)
        return app

    def installed_for(self, person, external_id=APP, catalog_id=CATALOG_ID, expanded=("id", "externalId")):
        app = {"id": catalog_id, "externalId": external_id, "displayName": "Example app"}
        self.installs.setdefault(person, []).append({"id": self.new_id(), "teamsApp": {k: v for k, v in app.items() if k in expanded}})

    def refuse(self, method, route, status=403, document=None, once=False):
        self.refusals.append([method, route, status, document if document is not None else FORBIDDEN[1], once])

    def answer(self, status, document=None):
        return status, {}, b"" if document is None else json.dumps(document).encode("utf-8")

    def pages(self, items, route, query, extra=""):
        if not self.page_size:
            return self.answer(200, {"value": items})
        start = int(query.get("$skiptoken", "0"))
        document = {"value": items[start:start + self.page_size]}
        if start + self.page_size < len(items):
            document["@odata.nextLink"] = f"https://graph.microsoft.com/v1.0/{route}?{extra}$skiptoken={start + self.page_size}"
        return self.answer(200, document)

    def transport(self, method, url, headers, body):
        parts = urlsplit(url)
        assert parts.netloc == "graph.microsoft.com" and parts.path.startswith("/v1.0/"), url
        assert headers["Authorization"] == "Bearer " + self.TOKEN
        assert " " not in url, "an address may not hold a space"
        route = parts.path[len("/v1.0/"):]
        query = {k: v[0] for k, v in parse_qs(parts.query, keep_blank_values=True).items()}
        data = json.loads(body.decode("utf-8")) if body else None
        self.calls.append((method, route, data))
        self.queries.append(query)
        for refusal in list(self.refusals):
            if refusal[0] == method and route.startswith(refusal[1]):
                if refusal[4]:
                    self.refusals.remove(refusal)
                return self.answer(refusal[2], refusal[3])
        if route == "servicePrincipals" and method == "GET":
            found = re.fullmatch(r"appId eq '([^']*)'", query.get("$filter", ""))
            assert found, query
            select = set(query["$select"].split(",")) | {"id"}
            return self.answer(200, {"value": [{k: v for k, v in p.items() if k in select} for p in self.principals if p["appId"] == found.group(1)]})
        if route == "appCatalogs/teamsApps" and method == "GET":
            assert query.get("$filter") == "distributionMethod eq 'organization'", query
            return self.pages([a for a in self.catalog if a["distributionMethod"] == "organization"], route, query)
        found = re.fullmatch(r"users/([0-9a-f-]+)/teamwork/installedApps", route)
        if found and method == "GET":
            held = self.installs.get(found.group(1), [])
            if query.get("$expand") != "teamsApp":
                held = [{k: v for k, v in i.items() if k != "teamsApp"} for i in held]
            return self.pages(held, route, query, "$expand=teamsApp&")
        if found and method == "POST":
            target = re.fullmatch(r"https://graph\.microsoft\.com/v1\.0/appCatalogs/teamsApps/([0-9a-f-]+)", data["teamsApp@odata.bind"])
            assert target, data
            app = next(a for a in self.catalog if a["id"] == target.group(1))
            self.installed_for(found.group(1), app["externalId"], app["id"])
            return self.answer(201)
        raise AssertionError(f"the tool sent a call that the model does not know: {method} {route}")


def run(argv, tenant, env=None, answers=("yes",), asked=None):
    lines, errors = [], io.StringIO()
    answers = list(answers)

    def ask(prompt):
        if asked is not None:
            asked.append(prompt)
        return answers.pop(0) if answers else None

    with contextlib.redirect_stderr(errors):
        code = es.main(argv, runner=tenant.az, transport=tenant.transport, sleep=lambda seconds: None, out=lines.append, ask=ask, env={} if env is None else env)
    return code, "\n".join(lines), errors.getvalue()


def in_order():
    tenant = FakeTeams()
    tenant.the_bot()
    tenant.the_app()
    tenant.installed_for(PERSON)
    return tenant


class TheInputs(unittest.TestCase):
    def test_every_input_is_checked_and_named_before_anything_is_asked_or_read(self):
        for argv, word in (
            (["teams-check", "--bot-id", BOT], "--tenant-id"),
            (["teams-check", "--tenant-id", "not-a-guid", "--bot-id", BOT], "--tenant-id"),
            (["teams-check", "--tenant-id", TENANT], "--bot-id"),
            (["teams-check", "--tenant-id", TENANT, "--bot-id", "x"], "--bot-id"),
            (["teams-check", "--tenant-id", TENANT, "--bot-id", BOT, "--teams-app-id", "x"], "--teams-app-id"),
            (["teams-apply", *ARGS, "--assign", "somebody"], "--assign"),
        ):
            tenant = FakeTeams()
            code, _, err = run(argv, tenant)
            self.assertEqual(code, 1, argv)
            self.assertIn(word, err)
            self.assertEqual((tenant.calls, tenant.token_requests), ([], []), "it refused before it asked for a token or read anything")

    def test_the_default_id_of_the_teams_app_is_the_one_that_the_package_tool_makes_and_a_given_one_wins(self):
        self.assertEqual(es.teams_app_id_of(BOT), tp.app_id_of(BOT))
        self.assertEqual(es.teams_app_id_of(BOT.upper()), tp.app_id_of(BOT))
        args = es.argparse.Namespace(tenant_id=TENANT.upper(), bot_id=BOT.upper(), teams_app_id=None, assign=[f"{SECOND_PERSON},{PERSON.upper()}", PERSON])
        cfg = es.read_teams_config(args)
        self.assertEqual((cfg.tenant, cfg.bot_id, cfg.app_id, cfg.people), (TENANT, BOT, APP, (SECOND_PERSON, PERSON)))
        args.teams_app_id = "12345678-9ABC-DEF0-1234-56789ABCDEF0"
        self.assertEqual(es.read_teams_config(args).app_id, "12345678-9abc-def0-1234-56789abcdef0")

    def test_the_token_is_asked_for_once_for_microsoft_graph_in_the_tenant_and_is_never_shown(self):
        tenant = in_order()
        code, out, err = run(["teams-check", *ARGS], tenant)
        self.assertEqual(code, 0, out)
        self.assertEqual(len(tenant.token_requests), 1)
        asked = tenant.token_requests[0]
        self.assertEqual((asked[asked.index("--resource") + 1], asked[asked.index("--tenant") + 1]), ("https://graph.microsoft.com", TENANT))
        self.assertNotIn(FakeTeams.TOKEN, out + err)


class Check(unittest.TestCase):
    def test_a_tenant_that_has_nothing_misses_the_identity_the_app_and_the_install_and_nothing_is_written(self):
        tenant = FakeTeams()
        code, out, _ = run(["teams-check", *ARGS], tenant)
        self.assertEqual(code, 1)
        self.assertRegex(out, rf"MISSING +The bot's identity \(client id {BOT}\) is a managed identity of this tenant")
        self.assertRegex(out, rf"MISSING +The Teams app {APP} is in the organization's app catalog")
        self.assertRegex(out, rf"MISSING +The Teams app is installed in the personal scope of {PERSON}")
        self.assertIn("Upload new app", out)
        self.assertIn("24-48 hours", out)
        self.assertIn("0 of 3 in order.", out)
        self.assertEqual(tenant.writes(), [])

    def test_everything_in_place_is_in_order_and_the_run_only_reads(self):
        tenant = in_order()
        code, out, _ = run(["teams-check", *ARGS], tenant)
        self.assertEqual(code, 0, out)
        self.assertIn("3 of 3 in order.", out)
        self.assertIn(f"the catalog's own id for it is {CATALOG_ID}", out)
        self.assertEqual([c[:2] for c in tenant.calls], [("GET", "servicePrincipals"), ("GET", "appCatalogs/teamsApps"), ("GET", f"users/{PERSON}/teamwork/installedApps")])
        self.assertEqual(tenant.writes(), [])

    def test_without_people_only_the_identity_and_the_catalog_are_read(self):
        tenant = FakeTeams()
        tenant.the_bot()
        tenant.the_app()
        code, out, _ = run(["teams-check", "--tenant-id", TENANT, "--bot-id", BOT], tenant)
        self.assertEqual((code, "2 of 2 in order." in out), (0, True), out)
        self.assertNotIn("users/", " ".join(c[1] for c in tenant.calls))

    def test_an_identity_that_is_an_application_and_not_a_managed_identity_differs(self):
        tenant = in_order()
        tenant.principals[0]["servicePrincipalType"] = "Application"
        code, out, _ = run(["teams-check", *ARGS], tenant)
        self.assertEqual(code, 1)
        self.assertRegex(out, r"DIFFERS +The bot's identity")
        self.assertIn("it is of the type Application, not a managed identity", out)

    def test_the_app_is_found_by_the_id_of_its_manifest_in_any_case_and_another_app_of_the_organization_is_not_it(self):
        tenant = FakeTeams()
        tenant.the_bot()
        tenant.the_app(external_id="12345678-9abc-def0-1234-56789abcdef0", catalog_id="99999999-0000-4000-8000-000000000001")
        code, out, _ = run(["teams-check", "--tenant-id", TENANT, "--bot-id", BOT], tenant)
        self.assertEqual(code, 1)
        self.assertRegex(out, r"MISSING +The Teams app")
        tenant.the_app(external_id=APP.upper(), catalog_id=CATALOG_ID)
        code, out, _ = run(["teams-check", "--tenant-id", TENANT, "--bot-id", BOT], tenant)
        self.assertEqual((code, f"the catalog's own id for it is {CATALOG_ID}" in out), (0, True), out)

    def test_an_app_of_the_store_with_the_same_id_is_not_an_app_of_the_organization(self):
        tenant = FakeTeams()
        tenant.the_bot()
        tenant.the_app(distribution="store")
        code, out, _ = run(["teams-check", "--tenant-id", TENANT, "--bot-id", BOT], tenant)
        self.assertEqual(code, 1)
        self.assertRegex(out, r"MISSING +The Teams app")

    def test_the_catalog_is_asked_for_the_apps_of_the_organization_with_the_documented_filter_and_the_installs_expand_the_app(self):
        tenant = in_order()
        run(["teams-check", *ARGS], tenant)
        self.assertEqual(tenant.queries[1], {"$filter": "distributionMethod eq 'organization'"})
        self.assertEqual(tenant.queries[2], {"$expand": "teamsApp"})

    def test_an_install_is_found_by_the_id_of_the_manifest_or_by_the_id_that_the_catalog_gave(self):
        for expanded in (("id", "externalId"), ("externalId",), ("id",)):
            tenant = FakeTeams()
            tenant.the_bot()
            tenant.the_app()
            tenant.installed_for(PERSON, expanded=expanded)
            code, out, _ = run(["teams-check", *ARGS], tenant)
            self.assertEqual((code, "3 of 3 in order." in out), (0, True), (expanded, out))

    def test_an_install_of_another_app_is_not_an_install_of_this_one(self):
        tenant = FakeTeams()
        tenant.the_bot()
        tenant.the_app()
        tenant.installed_for(PERSON, external_id="12345678-9abc-def0-1234-56789abcdef0", catalog_id="99999999-0000-4000-8000-000000000001")
        code, out, _ = run(["teams-check", *ARGS], tenant)
        self.assertEqual(code, 1)
        self.assertRegex(out, rf"MISSING +The Teams app is installed in the personal scope of {PERSON}")

    def test_a_list_of_installs_with_more_than_one_page_is_read_to_its_end(self):
        tenant = FakeTeams()
        tenant.the_bot()
        tenant.the_app()
        for number in range(1, 4):
            tenant.installed_for(PERSON, external_id=f"12345678-9abc-def0-1234-56789abcdef{number}", catalog_id=f"99999999-0000-4000-8000-00000000000{number}")
        tenant.installed_for(PERSON)
        tenant.page_size = 2
        code, out, _ = run(["teams-check", *ARGS], tenant)
        self.assertEqual((code, "3 of 3 in order." in out), (0, True), out)
        self.assertGreater(len([c for c in tenant.calls if c[1].endswith("installedApps")]), 1)

    def test_a_catalog_that_this_sign_in_may_not_read_is_a_line_and_the_rest_goes_on(self):
        tenant = in_order()
        tenant.refuse("GET", "appCatalogs/teamsApps")
        code, out, err = run(["teams-check", *ARGS], tenant)
        self.assertEqual(code, 1)
        self.assertRegex(out, rf"UNREADABLE +The Teams app {APP} is in the organization's app catalog")
        self.assertIn("Microsoft Graph answered 403 Authorization_RequestDenied", out)
        self.assertIn("Teams admin center", out)
        self.assertRegex(out, rf"present +The Teams app is installed in the personal scope of {PERSON}")
        self.assertIn("2 of 3 in order.", out)
        self.assertEqual(err, "")

    def test_the_installs_of_a_person_that_this_sign_in_may_not_read_are_a_line_that_names_the_setup_policy(self):
        tenant = in_order()
        tenant.refuse("GET", f"users/{PERSON}/teamwork/installedApps")
        code, out, _ = run(["teams-check", *ARGS], tenant)
        self.assertEqual(code, 1)
        self.assertRegex(out, rf"UNREADABLE +The Teams app is installed in the personal scope of {PERSON}")
        self.assertIn("a person's own installs only", out)
        self.assertIn(HINT_POLICY, out)

    def test_a_person_that_microsoft_graph_does_not_know_is_named_and_not_a_crash(self):
        tenant = in_order()
        tenant.refuse("GET", f"users/{PERSON}/teamwork/installedApps", 404, {"error": {"code": "Request_ResourceNotFound", "message": "not found"}})
        code, out, _ = run(["teams-check", *ARGS], tenant)
        self.assertEqual(code, 1)
        self.assertIn("does not know this person (404)", out)

    def test_an_answer_that_is_not_a_refusal_stops_the_run_with_the_text_of_graph(self):
        tenant = in_order()
        tenant.refuse("GET", "appCatalogs/teamsApps", 500, {"error": {"code": "InternalServerError", "message": "something broke"}})
        code, out, err = run(["teams-check", *ARGS], tenant)
        self.assertEqual(code, 1)
        self.assertIn("error: Microsoft Graph refused: 500 InternalServerError: something broke", err)
        self.assertNotIn("in order", out)

    def test_two_people_are_two_lines_and_a_person_who_has_it_does_not_hide_one_who_does_not(self):
        tenant = in_order()
        code, out, _ = run(["teams-check", *ARGS, "--assign", SECOND_PERSON], tenant)
        self.assertEqual(code, 1)
        self.assertRegex(out, rf"present +The Teams app is installed in the personal scope of {PERSON}")
        self.assertRegex(out, rf"MISSING +The Teams app is installed in the personal scope of {SECOND_PERSON}")
        self.assertIn("3 of 4 in order.", out)


class Apply(unittest.TestCase):
    def a_tenant_that_lacks_the_install(self, *people):
        tenant = FakeTeams()
        tenant.the_bot()
        tenant.the_app()
        for person in people:
            tenant.installed_for(person)
        return tenant

    def test_a_dry_run_says_what_it_would_make_and_makes_nothing(self):
        tenant = self.a_tenant_that_lacks_the_install()
        code, out, _ = run(["teams-apply", *ARGS], tenant)
        self.assertEqual(code, 1)
        self.assertIn("1 change(s) would be made, and nothing else:", out)
        self.assertIn(f"POST users/{PERSON}/teamwork/installedApps: install the Teams app (catalog id {CATALOG_ID})", out)
        self.assertIn("This was a dry run. Run again with --apply to make them.", out)
        self.assertEqual(tenant.writes(), [])

    def test_apply_installs_the_app_for_the_person_with_the_documented_body_and_checks_again(self):
        tenant = self.a_tenant_that_lacks_the_install()
        asked = []
        code, out, _ = run(["teams-apply", *ARGS, "--apply"], tenant, asked=asked)
        self.assertEqual(code, 0, out)
        self.assertEqual(len(asked), 1)
        self.assertIn(f"installed the app for {PERSON}", out)
        self.assertIn("Checking again:", out)
        self.assertIn("3 of 3 in order.", out)
        self.assertEqual(tenant.writes(), [("POST", f"users/{PERSON}/teamwork/installedApps", {"teamsApp@odata.bind": f"https://graph.microsoft.com/v1.0/appCatalogs/teamsApps/{CATALOG_ID}"})])

    def test_a_second_run_has_nothing_to_make(self):
        tenant = self.a_tenant_that_lacks_the_install()
        run(["teams-apply", *ARGS, "--apply", "--yes"], tenant)
        before = len(tenant.writes())
        code, out, _ = run(["teams-apply", *ARGS, "--apply", "--yes"], tenant)
        self.assertEqual((code, "Nothing to make." in out, len(tenant.writes())), (0, True, before))

    def test_the_question_is_asked_unless_yes_is_given_and_anything_but_yes_changes_nothing(self):
        tenant = self.a_tenant_that_lacks_the_install()
        code, _, err = run(["teams-apply", *ARGS, "--apply"], tenant, answers=("no",))
        self.assertEqual((code, tenant.writes()), (1, []))
        self.assertIn("nothing was changed", err)
        code, _, err = run(["teams-apply", *ARGS, "--apply"], tenant, answers=())
        self.assertEqual((code, tenant.writes()), (1, []))
        self.assertIn("--apply needs --yes when there is no terminal to ask in", err)

    def test_the_app_is_not_installed_while_the_catalog_does_not_have_it(self):
        tenant = FakeTeams()
        tenant.the_bot()
        code, out, _ = run(["teams-apply", *ARGS, "--apply", "--yes"], tenant)
        self.assertEqual((code, tenant.writes()), (1, []))
        self.assertIn("Nothing that this tool can make is missing", out)
        self.assertRegex(out, r"MISSING +The Teams app")

    def test_nobody_is_written_for_whose_installs_could_not_be_read(self):
        tenant = self.a_tenant_that_lacks_the_install()
        tenant.refuse("GET", f"users/{PERSON}/teamwork/installedApps")
        code, out, _ = run(["teams-apply", *ARGS, "--apply", "--yes"], tenant)
        self.assertEqual((code, tenant.writes()), (1, []))
        self.assertRegex(out, r"UNREADABLE")
        self.assertIn("Nothing that this tool can make is missing", out)

    def test_a_refused_install_is_said_in_plain_words_and_the_next_person_still_gets_the_app(self):
        tenant = self.a_tenant_that_lacks_the_install()
        tenant.refuse("POST", f"users/{PERSON}/teamwork/installedApps")
        code, out, err = run(["teams-apply", *ARGS, "--assign", SECOND_PERSON, "--apply", "--yes"], tenant)
        self.assertEqual(code, 1, "one person still lacks the app, so the run is not in order")
        self.assertIn(f"could not install the app for {PERSON}: Microsoft Graph answered 403 Authorization_RequestDenied", out)
        self.assertIn(HINT_POLICY, out)
        self.assertIn(f"installed the app for {SECOND_PERSON}", out)
        self.assertRegex(out, rf"MISSING +The Teams app is installed in the personal scope of {PERSON}")
        self.assertEqual(err, "")
        self.assertEqual([c[1] for c in tenant.writes()], [f"users/{PERSON}/teamwork/installedApps", f"users/{SECOND_PERSON}/teamwork/installedApps"])

    def test_an_install_that_is_there_already_is_not_a_failure(self):
        tenant = self.a_tenant_that_lacks_the_install()
        tenant.refuse("POST", f"users/{PERSON}/teamwork/installedApps", 409, {"error": {"code": "Conflict", "message": "already installed"}}, once=True)
        code, out, _ = run(["teams-apply", *ARGS, "--apply", "--yes"], tenant)
        self.assertIn(f"the app was installed for {PERSON} already", out)
        self.assertEqual(code, 1, "the second read found no install, so the line stays MISSING and the exit code says so")

    def test_an_answer_that_is_not_a_refusal_stops_the_run_and_is_shown(self):
        tenant = self.a_tenant_that_lacks_the_install()
        tenant.refuse("POST", f"users/{PERSON}/teamwork/installedApps", 500, {"error": {"code": "InternalServerError", "message": "something broke"}})
        code, _, err = run(["teams-apply", *ARGS, "--apply", "--yes"], tenant)
        self.assertEqual(code, 1)
        self.assertIn("error: Microsoft Graph refused: 500 InternalServerError: something broke", err)

    def test_a_pipeline_never_writes_but_may_read_and_a_dry_run_is_allowed(self):
        env = {"GITHUB_ACTIONS": "true"}
        tenant = self.a_tenant_that_lacks_the_install()
        code, _, err = run(["teams-apply", *ARGS, "--apply", "--yes"], tenant, env=env)
        self.assertEqual((code, tenant.calls, tenant.token_requests), (1, [], []))
        self.assertIn("never a pipeline", err)
        self.assertIn("AGENTS.md rules 18 and 24", err)
        code, out, _ = run(["teams-apply", *ARGS], tenant, env=env)
        self.assertEqual((code, tenant.writes()), (1, []))
        self.assertIn("This was a dry run.", out)
        code, _, _ = run(["teams-check", *ARGS], tenant, env=env)
        self.assertEqual((code, tenant.writes()), (1, []))


class TheCallsOfTheTool(unittest.TestCase):
    def test_the_teams_calls_are_on_the_list_and_nothing_else_was_added(self):
        for method, route in (("GET", "appCatalogs/teamsApps"), ("GET", f"users/{PERSON}/teamwork/installedApps"), ("POST", f"users/{PERSON}/teamwork/installedApps")):
            self.assertTrue(any(m == method and p.fullmatch(route) for m, p in es.CALLS), f"{method} {route}")
        self.assertEqual({m for m, _ in es.CALLS}, {"GET", "POST", "PATCH"}, "nothing is deleted")

    def test_what_is_not_an_install_or_a_read_of_the_catalog_is_refused_before_it_is_sent(self):
        tenant = FakeTeams()
        graph = es.Graph(es.Tokens(tenant.az, TENANT, es.Hider()), tenant.transport, lambda s: None)
        for method, route in (("DELETE", f"users/{PERSON}/teamwork/installedApps/00000000-0000-4000-8000-000000000001"), ("POST", "appCatalogs/teamsApps"),
                              ("PATCH", f"users/{PERSON}/teamwork/installedApps"), ("GET", f"users/{PERSON}/teamwork"), ("GET", "users"),
                              ("GET", f"users/{PERSON}/teamwork/installedApps/00000000-0000-4000-8000-000000000001/chat"), ("POST", "appCatalogs/teamsApps/00000000-0000-4000-8000-000000000001/appDefinitions")):
            with self.assertRaises(es.Problem, msg=f"{method} {route}"):
                graph.send(method, route, {})
        self.assertEqual(tenant.calls, [])

    def test_every_call_of_a_whole_run_is_on_the_list_and_none_is_a_delete(self):
        tenant = FakeTeams()
        tenant.the_bot()
        tenant.the_app()
        run(["teams-apply", *ARGS, "--assign", SECOND_PERSON, "--apply", "--yes"], tenant)
        self.assertGreater(len(tenant.calls), 5)
        self.assertNotIn("DELETE", {c[0] for c in tenant.calls})
        for method, route, _ in tenant.calls:
            self.assertTrue(any(m == method and p.fullmatch(route) for m, p in es.CALLS), f"{method} {route}")


class TheDocumentation(unittest.TestCase):
    def test_the_docstring_names_the_two_commands_and_says_what_is_not_proven(self):
        text = (ROOT / "tools" / "entra-setup.py").read_text(encoding="utf-8")
        for needle in ("teams-check --tenant-id", "teams-apply --tenant-id", "never in a pipeline", "nothing removed", "NOT proven",
                       "https://learn.microsoft.com/graph/api/userteamwork-post-installedapps"):
            self.assertIn(needle, text)

    def test_the_two_commands_are_in_the_help(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), self.assertRaises(SystemExit):
            es.main(["--help"])
        self.assertIn("teams-check", out.getvalue())
        self.assertIn("teams-apply", out.getvalue())


if __name__ == "__main__":
    unittest.main()
