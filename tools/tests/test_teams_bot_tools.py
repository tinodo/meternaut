"""The tools of the Teams bot that run without Azure: the sub-command teams-bot of tools/entra-setup.py, the package builder tools/teams-app.py and the test that runs in the Operator, tools/teams-check.py
(docs/proposals/20-teams-cards-through-a-bot.md). Nothing here calls Azure, Microsoft Entra, Teams or the network: a fake tenant answers the calls of Microsoft Graph and of Azure Resource Manager that the tool is
allowed to make, and a fake service answers the telemetry."""
import base64
import contextlib
import importlib.util
import io
import json
import os
import re
import struct
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock
from urllib.parse import parse_qs, urlsplit

ROOT = Path(__file__).resolve().parents[2]


def load(file_name, label):
    spec = importlib.util.spec_from_file_location(label, ROOT / "tools" / file_name)
    module = importlib.util.module_from_spec(spec)
    sys.modules[label] = module
    spec.loader.exec_module(module)
    return module


es = load("entra-setup.py", "entra_setup_of_the_teams_bot_tests")
ta = load("teams-app.py", "teams_app_of_the_teams_bot_tests")
tc = load("teams-check.py", "teams_check_of_the_teams_bot_tests")

TENANT = "11111111-2222-3333-4444-555555555555"
SUBSCRIPTION = "66666666-7777-8888-9999-000000000000"
GROUP = "rg-example"
PRINCIPAL = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
OTHER_TENANT = "99999999-8888-7777-6666-555555555555"
ARGS = ["teams-bot", "--tenant-id", TENANT, "--subscription", SUBSCRIPTION, "--resource-group", GROUP]
ISSUER = f"https://login.microsoftonline.com/{TENANT}/v2.0"
TOKEN = "eyJhbGciOiJSUzI1NiJ9.eyJhdWQiOiJ0ZXN0In0.c2lnbmF0dXJlLW9mLXRoZS10ZXN0"


class FakeEntra:
    """The parts of a tenant that teams-bot reads and changes, a record of every call, and the managed identity that Azure Resource Manager reports."""

    def __init__(self, principal=PRINCIPAL, identity_tenant=TENANT, identity_error=""):
        self.apps, self.principals, self.credentials = [], [], {}
        self.calls, self.az_calls, self.counter = [], [], 0
        self.principal, self.identity_tenant, self.identity_error = principal, identity_tenant, identity_error

    def new_id(self):
        self.counter += 1
        return f"00000000-0000-4000-8000-{self.counter:012d}"

    def writes(self):
        return [c for c in self.calls if c[0] != "GET"]

    def az(self, args):
        self.az_calls.append(list(args))
        if list(args)[:2] == ["account", "get-access-token"]:
            return 0, TOKEN + "\n", ""
        if list(args)[:3] == ["rest", "--method", "get"]:
            url = args[args.index("--url") + 1]
            assert url == (f"https://management.azure.com/subscriptions/{SUBSCRIPTION}/resourceGroups/{GROUP}/providers/Microsoft.ManagedIdentity/userAssignedIdentities/id-meternaut-teams"
                           "?api-version=2023-01-31"), url
            if self.identity_error:
                return 1, "", self.identity_error
            return 0, json.dumps({"principalId": self.principal, "tenantId": self.identity_tenant}), ""
        return 1, "", "unexpected"

    def existing(self, **changes):
        app = {"id": self.new_id(), "appId": self.new_id(), "displayName": es.TEAMS_APP_NAME, "signInAudience": es.THIS_TENANT_ONLY, "isFallbackPublicClient": False,
               "web": {"redirectUris": []}, "spa": {"redirectUris": []}, "publicClient": {"redirectUris": []}, "requiredResourceAccess": [], "passwordCredentials": [], "keyCredentials": []}
        app.update(changes)
        self.apps.append(app)
        return app

    def existing_everything(self):
        app = self.existing()
        self.principals.append({"id": self.new_id(), "appId": app["appId"]})
        self.credentials[app["id"]] = [{"name": es.TEAMS_CREDENTIAL_NAME, "issuer": ISSUER, "subject": PRINCIPAL, "audiences": [es.AUDIENCE]}]
        return app

    def answer(self, status, document=None):
        return status, {}, b"" if document is None else json.dumps(document).encode("utf-8")

    def transport(self, method, url, headers, body):
        parts = urlsplit(url)
        assert parts.netloc == "graph.microsoft.com" and parts.path.startswith("/v1.0/"), url
        assert headers["Authorization"] == f"Bearer {TOKEN}"
        route = parts.path[len("/v1.0/"):]
        query = {k: v[0] for k, v in parse_qs(parts.query, keep_blank_values=True).items()}
        data = json.loads(body.decode("utf-8")) if body else None
        self.calls.append((method, route, data))

        def filtered(items):
            expression = query.get("$filter")
            if not expression:
                return items
            name, value = re.fullmatch(r"(\w+) eq '([^']*)'", expression).groups()
            return [i for i in items if i.get(name) == value]

        def selected(item):
            names = set(query.get("$select", "").split(",")) | {"id"} if query.get("$select") else None
            return item if names is None else {k: v for k, v in item.items() if k in names}

        if route == "applications":
            if method == "GET":
                return self.answer(200, {"value": [selected(a) for a in filtered(self.apps)]})
            app = dict(data, id=self.new_id(), appId=self.new_id(), passwordCredentials=[], keyCredentials=[])
            self.apps.append(app)
            return self.answer(201, app)
        found = re.fullmatch(r"applications/([0-9a-f-]+)/federatedIdentityCredentials", route)
        if found:
            if method == "GET":
                return self.answer(200, {"value": self.credentials.get(found.group(1), [])})
            self.credentials.setdefault(found.group(1), []).append(data)
            return self.answer(201, data)
        if route == "servicePrincipals":
            if method == "GET":
                return self.answer(200, {"value": [selected(p) for p in filtered(self.principals)]})
            principal = dict(data, id=self.new_id())
            self.principals.append(principal)
            return self.answer(201, principal)
        raise AssertionError(f"the tool sent a call that the model does not know: {method} {route}")


def run(argv, entra, env=None, answers=("yes",)):
    lines, errors = [], io.StringIO()
    answers = list(answers)
    with contextlib.redirect_stderr(errors):
        code = es.main(argv, runner=entra.az, transport=entra.transport, sleep=lambda s: None, out=lines.append, ask=lambda prompt: answers.pop(0) if answers else None, env={} if env is None else env)
    return code, "\n".join(lines), errors.getvalue()


class TheTeamsBotStepOfTheEntraTool(unittest.TestCase):
    def test_a_dry_run_changes_nothing_and_says_what_it_would_make(self):
        entra = FakeEntra()
        code, out, err = run(ARGS, entra)
        self.assertEqual(code, 1, "a dry run that has something to make is not a pass")
        self.assertEqual(entra.writes(), [])
        self.assertIn("3 change(s) would be made", out)
        self.assertIn("This was a dry run. Run again with --apply to make them.", out)
        self.assertNotIn("Client id of the app registration", out, "there is no app registration yet, so there is no client id to show")
        self.assertEqual(err, "")

    def test_apply_makes_the_app_the_service_principal_and_one_federated_credential_with_the_right_values_and_no_secret_or_permission(self):
        entra = FakeEntra()
        code, out, err = run(ARGS + ["--apply", "--yes"], entra)
        self.assertEqual((code, err), (0, ""), out)
        self.assertEqual([(m, r) for m, r, _ in entra.writes()[:2]], [("POST", "applications"), ("POST", "servicePrincipals")])
        self.assertRegex(entra.writes()[2][1], r"^applications/[0-9a-f-]+/federatedIdentityCredentials$")
        self.assertEqual(len(entra.writes()), 3, "nothing else is written: no secret, no certificate, no permission, no consent, no assignment")
        body = entra.writes()[0][2]
        self.assertEqual((body["displayName"], body["signInAudience"], body["isFallbackPublicClient"]), ("Meternaut Teams", "AzureADMyOrg", False))
        for forbidden in ("passwordCredentials", "keyCredentials", "requiredResourceAccess", "web", "spa", "publicClient", "api"):
            self.assertNotIn(forbidden, body, f"the app registration is made with no {forbidden}")
        (app,) = entra.apps
        self.assertEqual(entra.writes()[1][2], {"appId": app["appId"]})
        (credential,) = entra.credentials[app["id"]]
        self.assertEqual((credential["issuer"], credential["subject"], credential["audiences"]), (ISSUER, PRINCIPAL, ["api://AzureADTokenExchange"]))
        self.assertEqual(app["passwordCredentials"] + app["keyCredentials"], [], "no secret and no certificate")
        self.assertIn("0 passwords, 0 keys and 1 federated credential on the app registration", out)
        self.assertIn(app["appId"], out, "the client id is shown on the terminal")
        self.assertIn("gh secret set TEAMS_BOT_APP_ID --env hub --repo tinodo/meternaut", out)
        self.assertEqual(sum(1 for line in out.splitlines() if app["appId"] in line), 1, "and once")

    def test_a_second_run_changes_nothing_and_says_so(self):
        entra = FakeEntra()
        self.assertEqual(run(ARGS + ["--apply", "--yes"], entra)[0], 0)
        made = len(entra.writes())
        code, out, err = run(ARGS + ["--apply", "--yes"], entra)
        self.assertEqual((code, err), (0, ""))
        self.assertEqual(len(entra.writes()), made, "nothing more was written")
        self.assertIn("Nothing to make, and nothing was changed.", out)
        self.assertIn("3 of 3 in order.", out)
        self.assertIn(entra.apps[0]["appId"], out)

    def test_it_asks_before_it_writes_and_a_no_changes_nothing(self):
        entra = FakeEntra()
        code, _, err = run(ARGS + ["--apply"], entra, answers=("no",))
        self.assertEqual(code, 1)
        self.assertIn("nothing was changed", err)
        self.assertEqual(entra.writes(), [])
        code, _, err = run(ARGS + ["--apply"], entra, answers=())
        self.assertEqual(code, 1)
        self.assertIn("--apply needs --yes when there is no terminal to ask in", err)

    def test_it_refuses_to_run_in_a_pipeline_even_as_a_dry_run_and_calls_nothing(self):
        for variable in ("GITHUB_ACTIONS", "TF_BUILD"):
            entra = FakeEntra()
            code, out, err = run(ARGS, entra, env={variable: "true"})
            self.assertEqual(code, 1)
            self.assertIn("never a pipeline", err)
            self.assertEqual((entra.calls, entra.az_calls, out), ([], [], ""), "no token, no read and no line of output")

    def test_the_identity_has_to_be_there_and_in_this_tenant(self):
        code, _, err = run(ARGS, FakeEntra(identity_error="ERROR: (ResourceNotFound) The Resource 'Microsoft.ManagedIdentity/userAssignedIdentities/id-meternaut-teams' was not found"))
        self.assertEqual(code, 1)
        self.assertIn("run the Hub action teams (phase 1) first", err)
        entra = FakeEntra(identity_tenant=OTHER_TENANT)
        code, _, err = run(ARGS + ["--apply", "--yes"], entra)
        self.assertEqual(code, 1)
        self.assertIn("have to be in the same tenant", err)
        self.assertEqual(entra.writes(), [])
        code, _, err = run(ARGS, FakeEntra(identity_error="ERROR: Please run 'az login' to setup account."))
        self.assertEqual(code, 1)
        self.assertIn("could not be read with your sign-in", err)

    def test_the_subject_is_compared_as_it_was_given_and_a_wrong_credential_is_shown_and_left_alone(self):
        for subject in (PRINCIPAL.upper(), "ffffffff-0000-0000-0000-000000000000"):
            entra = FakeEntra()
            app = entra.existing_everything()
            entra.credentials[app["id"]][0]["subject"] = subject
            code, out, err = run(ARGS + ["--apply", "--yes"], entra)
            self.assertEqual((code, err), (1, ""), subject)
            self.assertEqual(entra.writes(), [], "the tool removes nothing and makes no second credential")
            self.assertIn("none has the right values", out)
        for field, value in (("issuer", "https://login.microsoftonline.com/other/v2.0"), ("audiences", ["api://somewhere-else"])):
            entra = FakeEntra()
            app = entra.existing_everything()
            entra.credentials[app["id"]][0][field] = value
            self.assertEqual(run(ARGS + ["--apply", "--yes"], entra)[0], 1, field)
            self.assertEqual(entra.writes(), [])

    def test_a_second_credential_is_shown_and_the_design_has_exactly_one(self):
        entra = FakeEntra()
        app = entra.existing_everything()
        entra.credentials[app["id"]].append({"name": "stray", "issuer": ISSUER, "subject": "x", "audiences": ["api://AzureADTokenExchange"]})
        code, out, _ = run(ARGS, entra)
        self.assertEqual(code, 1)
        self.assertIn("1 other federated credential too: the design has exactly one", out)
        self.assertEqual(entra.writes(), [])

    def test_a_secret_a_certificate_or_another_audience_stops_everything_and_a_stray_address_or_permission_is_shown(self):
        for change in ({"passwordCredentials": [{"keyId": "k"}]}, {"keyCredentials": [{"keyId": "k"}]}, {"signInAudience": "AzureADMultipleOrgs"}):
            entra = FakeEntra()
            entra.existing(**change)
            code, out, _ = run(ARGS + ["--apply", "--yes"], entra)
            self.assertEqual(code, 1)
            self.assertIn("Nothing can be changed until", out)
            self.assertEqual(entra.writes(), [])
        entra = FakeEntra()
        app = entra.existing_everything()
        app["web"] = {"redirectUris": ["https://elsewhere.example/cb"]}
        app["requiredResourceAccess"] = [{"resourceAppId": "22222222-2222-2222-2222-222222222222", "resourceAccess": [{"id": "33333333-3333-3333-3333-333333333333", "type": "Scope"}]}]
        code, out, _ = run(ARGS, entra)
        self.assertEqual(code, 1)
        self.assertIn("1 redirect address", out)
        self.assertIn("1 API permission", out)
        self.assertEqual(entra.writes(), [])

    def test_two_app_registrations_of_the_name_stop_it_and_a_missing_service_principal_is_made_alone(self):
        entra = FakeEntra()
        entra.existing()
        entra.existing()
        code, _, err = run(ARGS, entra)
        self.assertEqual(code, 1)
        self.assertIn("2 app registrations are called Meternaut Teams", err)
        entra = FakeEntra()
        app = entra.existing()
        entra.credentials[app["id"]] = [{"name": es.TEAMS_CREDENTIAL_NAME, "issuer": ISSUER, "subject": PRINCIPAL, "audiences": [es.AUDIENCE]}]
        code, out, _ = run(ARGS + ["--apply", "--yes"], entra)
        self.assertEqual(code, 0, out)
        self.assertEqual([(m, r) for m, r, _ in entra.writes()], [("POST", "servicePrincipals")])

    def test_every_input_is_checked_and_named(self):
        for argv, word in ((["teams-bot", "--subscription", SUBSCRIPTION, "--resource-group", GROUP], "--tenant-id"), (["teams-bot", "--tenant-id", TENANT, "--resource-group", GROUP], "--subscription"),
                           (["teams-bot", "--tenant-id", TENANT, "--subscription", SUBSCRIPTION], "--resource-group"),
                           (ARGS + ["--identity-name", "bad name"], "--identity-name"), (ARGS + ["--repository", "not a repository"], "--repository"), (["teams-bot", "--tenant-id", "x", "--subscription", SUBSCRIPTION, "--resource-group", GROUP], "--tenant-id")):
            entra = FakeEntra()
            code, _, err = run(argv, entra)
            self.assertEqual(code, 1, argv)
            self.assertIn(word, err)
            self.assertEqual(entra.calls, [])

    def test_the_calls_that_it_sends_are_calls_of_the_existing_list_and_the_other_sub_commands_are_untouched(self):
        entra = FakeEntra()
        run(ARGS + ["--apply", "--yes"], entra)
        for method, route, _ in entra.calls:
            self.assertTrue(any(m == method and p.fullmatch(route) for m, p in es.CALLS), (method, route))
        self.assertEqual(es.APP_NAME, "Meternaut", "the sign-in app registration keeps its own name, which is not the Teams app's")
        self.assertEqual(es.TEAMS_APP_NAME, "Meternaut Teams")
        self.assertEqual(es.TEAMS_IDENTITY_NAME, "id-meternaut-teams", "the name that the template and the parameter builder use")


class ThePackageOfTheTeamsApp(unittest.TestCase):
    CLIENT = "12345678-aaaa-bbbb-cccc-0123456789ab"

    def build(self, environ, extra=(), folder=None):
        lines = []
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(folder or tmp)
            with contextlib.redirect_stderr(io.StringIO()) as err:
                code = ta.main(["build", "--out", str(target), *extra], environ=environ, out=lines.append)
            data = (target / ta.PACKAGE_NAME).read_bytes() if (target / ta.PACKAGE_NAME).exists() else None
            return code, lines, err.getvalue(), data

    def test_the_package_holds_the_manifest_and_the_two_icons_and_prints_only_its_path_and_its_size(self):
        code, lines, _, data = self.build({"TEAMS_BOT_APP_ID": self.CLIENT, "CONSOLE_HOST_NAME": "pages.example.com"})
        self.assertEqual(code, 0)
        self.assertEqual(len(lines), 1)
        self.assertRegex(lines[0], r"^Wrote .*meternaut-teams-app\.zip \(\d+ bytes\)\.$")
        self.assertEqual(int(re.search(r"\((\d+) bytes\)", lines[0]).group(1)), len(data))
        self.assertNotIn(self.CLIENT, lines[0])
        self.assertNotIn("pages.example.com", lines[0])
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            self.assertEqual(sorted(archive.namelist()), ["color.png", "manifest.json", "outline.png"])
            manifest = json.loads(archive.read("manifest.json"))
            self.assertEqual(ta.check_manifest(manifest, {n: archive.read(n) for n in archive.namelist()}), [])
        self.assertEqual(manifest["bots"], [{"botId": self.CLIENT, "scopes": ["personal"], "isNotificationOnly": True, "supportsFiles": False}])
        self.assertEqual((manifest["manifestVersion"], manifest["name"]["short"], manifest["id"]), ("1.30", "Meternaut", "f3a9efc4-ae3e-4d9a-a71c-b11d0f2d00f5"))
        self.assertEqual(manifest["validDomains"], ["pages.example.com"], "the host that the buttons of a card open")
        self.assertTrue(manifest["developer"]["websiteUrl"].startswith("https://github.com/tinodo/meternaut"))

    def test_the_same_bytes_come_out_every_time_and_the_icons_are_the_sizes_that_teams_asks_for(self):
        environ = {"TEAMS_BOT_APP_ID": self.CLIENT}
        first = self.build(environ)[3]
        self.assertEqual(first, self.build(environ)[3])
        with zipfile.ZipFile(io.BytesIO(first)) as archive:
            for file_name, side in (("color.png", 192), ("outline.png", 32)):
                data = archive.read(file_name)
                self.assertTrue(data.startswith(b"\x89PNG\r\n\x1a\n"))
                self.assertEqual(struct.unpack(">II", data[16:24]), (side, side))
                self.assertLess(len(data), 100_000)
            self.assertEqual(archive.read("outline.png")[24:26], b"\x08\x06", "8 bits a channel, with an alpha channel: transparent")

    def test_it_refuses_a_missing_or_malformed_client_id_and_a_folder_inside_the_repository_and_a_bad_domain(self):
        for environ in ({}, {"TEAMS_BOT_APP_ID": "not-a-guid"}):
            code, _, err, data = self.build(environ)
            self.assertEqual((code, data), (1, None))
            self.assertIn("client id of the bot", err)
        code, _, err, _ = self.build({"TEAMS_BOT_APP_ID": self.CLIENT}, folder=ROOT / "local" / "teams-package-test")
        self.assertEqual(code, 1)
        self.assertIn("outside the repository", err)
        self.assertFalse((ROOT / "local" / "teams-package-test").exists())
        for domain in ("https://pages.example.com", "*.example.com", "pages"):
            code, _, err, _ = self.build({"TEAMS_BOT_APP_ID": self.CLIENT}, ["--valid-domain", domain])
            self.assertEqual(code, 1, domain)
            self.assertIn("a valid domain is a host name", err)

    def test_the_client_id_may_come_from_a_file_and_only_the_two_keys_are_read(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "hub-local.env"
            path.write_text(f"# a comment\nAZURE_TENANT_ID=11111111-2222-3333-4444-555555555555\nexport TEAMS_BOT_APP_ID='{self.CLIENT}'\nCONSOLE_HOST_NAME=\"pages.example.com\"\nbroken line\n", encoding="utf-8")
            found = ta.read_env_file(path)
            self.assertEqual(found, {"TEAMS_BOT_APP_ID": self.CLIENT, "CONSOLE_HOST_NAME": "pages.example.com"}, "no other line is read or kept")
            code, lines, _, data = self.build({}, ["--env-file", str(path)])
            self.assertEqual(code, 0)
            self.assertEqual(json.loads(zipfile.ZipFile(io.BytesIO(data)).read("manifest.json"))["bots"][0]["botId"], self.CLIENT)
            environment_wins = self.build({"TEAMS_BOT_APP_ID": "99999999-aaaa-bbbb-cccc-0123456789ab"}, ["--env-file", str(path)])
            self.assertEqual(json.loads(zipfile.ZipFile(io.BytesIO(environment_wins[3])).read("manifest.json"))["bots"][0]["botId"], "99999999-aaaa-bbbb-cccc-0123456789ab", "the environment comes first")

    def test_without_a_host_the_manifest_has_no_valid_domains_and_the_person_is_told(self):
        code, lines, _, data = self.build({"TEAMS_BOT_APP_ID": self.CLIENT})
        self.assertEqual(code, 0)
        self.assertNotIn("validDomains", json.loads(zipfile.ZipFile(io.BytesIO(data)).read("manifest.json")))
        self.assertTrue(any("may lead to untrusted content" in line for line in lines))

    def manifest(self):
        return ta.manifest(self.CLIENT, ["pages.example.com"])

    def test_the_rules_that_can_be_checked_offline_each_fail_when_they_are_broken(self):
        self.assertEqual(ta.check_manifest(self.manifest()), [])
        broken = {
            "manifestVersion": ("1.17", "manifestVersion is 1.30"), "version": ("1.0", "version is semver"), "id": ("not-a-guid", "id is a GUID"), "accentColor": ("blue", "accentColor is a colour"),
            "icons": ({"color": "a.png", "outline": "b.png"}, "icons name color.png and outline.png"),
        }
        for key, (value, text) in broken.items():
            manifest = self.manifest()
            manifest[key] = value
            self.assertTrue(any(text in p for p in ta.check_manifest(manifest)), key)
        changes = [
            (lambda m: m["developer"].update(name="x" * 33), "developer.name"), (lambda m: m["developer"].update(privacyUrl="http://example.com/p"), "developer.privacyUrl"),
            (lambda m: m["developer"].update(termsOfUseUrl=""), "developer.termsOfUseUrl"), (lambda m: m["name"].update(short="x" * 31), "name.short"), (lambda m: m["name"].update(full="Meternaut"), "name.short and name.full"),
            (lambda m: m["description"].update(short="x" * 81), "description.short is 1 to 80"), (lambda m: m["description"].update(full="x" * 4001), "description.full"),
            (lambda m: m["description"].update(full="Intro. " + m["description"]["short"]), "description.short is not repeated"),
            (lambda m: m["bots"][0].update(botId="x"), "botId"), (lambda m: m["bots"][0].update(scopes=["personal", "team"]), "scope is personal"), (lambda m: m["bots"][0].update(isNotificationOnly=False), "notification only"),
            (lambda m: m["bots"][0].update(supportsFiles=True), "support files"), (lambda m: m["bots"][0].update(supportsCalling=True), "no calling"), (lambda m: m.update(bots=[]), "one bot"),
            (lambda m: m.update(validDomains=["*.example.com"]), "validDomains"), (lambda m: m.update(validDomains=["a.example.com"] * 17), "validDomains"),
            (lambda m: m.update(webApplicationInfo={"id": self.CLIENT, "resource": "api://x"}), "no tab, no messaging extension, no sign-in and no permission"),
            (lambda m: m.update(permissions=["identity"]), "no tab, no messaging extension, no sign-in and no permission"),
            (lambda m: m["description"].update(full="token: " + "A" * 60), "secret or a token"), (lambda m: m["description"].update(full="client_secret=abc123 is here"), "secret or a token"),
            (lambda m: m["description"].update(full="eyJhbGciOiJSUzI1NiJ9.eyJhdWQiOiJ0ZXN0In0.c2lnbmF0dXJl"), "secret or a token"),
        ]
        for change, text in changes:
            manifest = self.manifest()
            change(manifest)
            self.assertTrue(any(text in p for p in ta.check_manifest(manifest)), (text, ta.check_manifest(manifest)))

    def test_the_icons_are_checked_and_the_command_check_reads_a_package(self):
        files = ta.package_files(self.CLIENT, [])
        self.assertEqual(ta.check_manifest(json.loads(files["manifest.json"]), files), [])
        for change, text in (({"color.png": b"not a png"}, "color.png is a PNG of 192x192"), ({"outline.png": files["color.png"]}, "outline.png is a PNG of 32x32"), ({"extra.txt": b"x"}, "and nothing else")):
            self.assertTrue(any(text in p for p in ta.check_manifest(json.loads(files["manifest.json"]), {**files, **change})), text)
        with tempfile.TemporaryDirectory() as tmp:
            good = Path(tmp) / "good.zip"
            good.write_bytes(ta.zip_bytes(files))
            bad = Path(tmp) / "bad.zip"
            bad.write_bytes(ta.zip_bytes({**files, "manifest.json": json.dumps({**json.loads(files["manifest.json"]), "version": "1"}).encode("utf-8")}))
            lines = []
            self.assertEqual(ta.main(["check", str(good)], out=lines.append), 0)
            self.assertEqual(lines, [])
            self.assertEqual(ta.main(["check", str(bad)], out=lines.append), 1)
            self.assertEqual(lines, ["fails: version is semver: 1.0.0"])

    def test_the_description_says_what_the_brief_says_and_the_tool_installs_nothing_and_reads_nothing_it_does_not_name(self):
        manifest = self.manifest()
        self.assertIn("AI-written recommendations for Azure cost savings. A person approves every change.", manifest["description"]["full"])
        source = (ROOT / "tools" / "teams-app.py").read_text(encoding="utf-8")
        for word in ("urlopen", "http.client", "requests", "subprocess", "socket"):
            self.assertNotIn(word, source, "the tool builds a file: it calls no service and uploads nothing")
        self.assertIn("installs nothing", source)


class TheTeamsTest(unittest.TestCase):
    INSIGHTS = f"/subscriptions/{SUBSCRIPTION}/resourceGroups/{GROUP}/providers/Microsoft.Insights/components/appi-meternaut"

    class World:
        """A fake of Azure for the tool: the Azure CLI's answers, the queue's answer, the telemetry that the app writes, and a clock that moves when the tool sleeps."""

        def __init__(self, test, steps=(), finished=True, queue_status=201, finished_extra=None):
            self.test, self.steps, self.finished, self.queue_status, self.finished_extra = test, list(steps), finished, queue_status, finished_extra or {}
            self.now, self.posts, self.queries = 0.0, [], 0

        def runner(self, args):
            args = list(args)
            if args[:2] == ["account", "get-access-token"]:
                return 0, "token-of-the-operator\n", ""
            if args[:3] == ["rest", "--method", "post"]:
                self.queries += 1
                request_id = self.posts and json.loads(base64.b64decode(re.search(r"<MessageText>([^<]*)</MessageText>", self.posts[0][2].decode()).group(1)))["requestId"]
                rows = []
                if request_id and self.queries >= 2:
                    for step in self.steps:
                        rows.append(["2026-11-13T10:00:00Z", tc.EVENT_PREFIX + json.dumps({"type": "teams.test.step", "requestId": request_id, **step})])
                    if self.finished:
                        rows.append(["2026-11-13T10:00:01Z", tc.EVENT_PREFIX + json.dumps({"type": "teams.test.finished", "requestId": request_id, "ok": bool(self.steps) and all(s.get("ok") for s in self.steps),
                                                                                           **self.finished_extra})])
                    rows.append(["2026-11-13T10:00:02Z", tc.EVENT_PREFIX + json.dumps({"type": "teams.test.step", "requestId": "someoneelse", "step": "token", "ok": False})])
                    rows.append(["2026-11-13T10:00:03Z", "an unrelated line"])
                return 0, json.dumps({"tables": [{"rows": rows}]}), ""
            return 1, "", "unexpected"

        def post(self, url, headers, body):
            self.posts.append((url, headers, body))
            return self.queue_status, b""

        def azure(self):
            return tc.Azure(runner=self.runner, post=self.post, sleep=self.sleep, clock=lambda: self.now)

        def sleep(self, seconds):
            self.now += seconds

    def go(self, world, fetcher, argv=None, env=None):
        lines, errors = [], io.StringIO()
        argv = argv or ["run", "--storage-account", "stmeternautfn0123abcd", "--insights", self.INSIGHTS, "--minutes", "3"]
        with mock.patch.dict(os.environ, {"GITHUB_ACTIONS": "true", **(env or {})}), contextlib.redirect_stdout(io.StringIO()) as out, contextlib.redirect_stderr(errors):
            code = tc.main(argv, azure=world.azure(), fetcher=fetcher)
        return code, out.getvalue(), errors.getvalue()

    OPEN = staticmethod(lambda url: 404 if "smba" in url else 200)
    GOOD = [{"step": "token", "ok": True, "status": 200}, {"step": "create", "ok": True, "status": 201}, {"step": "send", "ok": True, "status": 200}, {"step": "update", "ok": True, "status": 200}]

    def test_a_good_run_says_each_step_in_plain_words_and_passes(self):
        world = self.World(self, self.GOOD)
        code, out, err = self.go(world, self.OPEN)
        self.assertEqual((code, err), (0, ""), out)
        for words in ("login.microsoftonline.com: answered over HTTPS with 200 (2xx)", "smba.trafficmanager.net: answered over HTTPS with 404 (4xx). Any HTTP answer, even 401 or 404, proves that the path is open.",
                      "Token exchange (the identity's token for the app registration's token for the Bot Connector): ok (HTTP 200, 2xx).", "Create the 1:1 chat with the owner: ok (HTTP 201, 2xx).",
                      "Send the test card in that chat: ok (HTTP 200, 2xx).", "Replace the test card with the closing card: ok (HTTP 200, 2xx).", "The Teams test passed"):
            self.assertIn(words, out)
        (url, headers, body) = world.posts[0]
        self.assertEqual(url.split("?")[0], "https://stmeternautfn0123abcd.queue.core.windows.net/cases-control/messages")
        message = json.loads(base64.b64decode(re.search(r"<MessageText>([^<]*)</MessageText>", body.decode()).group(1)))
        self.assertEqual(set(message), {"job", "requestId"})
        self.assertEqual(message["job"], "teams-card-test")
        self.assertRegex(message["requestId"], r"^[0-9a-f]{32}$")

    def test_a_failed_token_exchange_prints_the_aadsts_number_alone_and_a_403_says_which_kind(self):
        cases = (
            ([{"step": "token", "ok": False, "status": 401, "aadsts": 700213, "reason": "unauthorized"}], ("NOT ok (AADSTS700213, HTTP 401, 4xx); the Bot Connector did not accept the token.", "Create the 1:1 chat with the owner: not tried")),
            ([{"step": "token", "ok": True}, {"step": "create", "ok": False, "status": 403, "reason": "not-installed"}], ("NOT ok (HTTP 403, 4xx); the Teams app is not installed for the owner.", "Send the test card in that chat: not tried")),
            ([{"step": "token", "ok": True}, {"step": "create", "ok": False, "status": 403, "reason": "blocked"}], ("NOT ok (HTTP 403, 4xx); the owner or the organisation blocks the app.",)),
            ([{"step": "token", "ok": False, "reason": "network"}], ("Token exchange (the identity's token for the app registration's token for the Bot Connector): NOT ok; there was no answer",)),
            ([{"step": "token", "ok": True}, {"step": "create", "ok": True, "status": 201}, {"step": "send", "ok": True, "status": 200}, {"step": "update", "ok": False, "status": 404, "reason": "other"}],
             ("Replace the test card with the closing card: NOT ok (HTTP 404, 4xx); another reason.",)),
        )
        for steps, words in cases:
            code, out, _ = self.go(self.World(self, steps), self.OPEN)
            self.assertEqual(code, 1, steps)
            for text in words:
                self.assertIn(text, out)
            self.assertIn("The Teams test did not pass", out)

    def test_nothing_that_the_app_wrote_is_printed_except_fixed_words_and_checked_numbers(self):
        hostile = "Bearer abcdefghijklmnop 11111111-2222-3333-4444-555555555555 person@example.com https://smba.trafficmanager.net/teams/v3/conversations/19:abc"
        steps = [{"step": "token", "ok": False, "status": 400, "aadsts": 70011, "reason": hostile, "text": hostile, "note": hostile, "url": hostile},
                 {"step": "create", "ok": False, "status": "403 " + hostile, "reason": hostile, "aadsts": hostile}]
        code, out, _ = self.go(self.World(self, steps), self.OPEN)
        self.assertEqual(code, 1)
        for secret in ("abcdefghijklmnop", "person@example.com", "11111111-2222", "19:abc", "Bearer", "v3/conversations"):
            self.assertNotIn(secret, out)
        self.assertIn("NOT ok (AADSTS70011, HTTP 400, 4xx); another reason.", out)
        self.assertNotRegex(out, r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", "no GUID is printed")

    def test_a_host_that_gives_no_answer_is_a_finding_and_the_reason_is_one_fixed_word(self):
        import socket
        import ssl
        import urllib.error

        for error, word in ((socket.gaierror(-2, "Name or service not known"), "the name did not resolve"), (TimeoutError(), "the connection timed out"), (ConnectionRefusedError(), "the connection was refused"),
                            (urllib.error.URLError(ssl.SSLError("bad certificate for secret-host.example")), "the TLS handshake failed"), (OSError("details that stay private"), "the connection failed")):
            def fetcher(url, error=error):
                if "smba" in url:
                    raise error
                return 200

            code, out, _ = self.go(self.World(self, self.GOOD), fetcher)
            self.assertEqual(code, 1, word)
            self.assertIn(f"smba.trafficmanager.net: NO ANSWER over HTTPS ({word}).", out)
            self.assertNotIn("private", out)
            self.assertNotIn("secret-host", out)
            self.assertIn("login.microsoftonline.com: answered over HTTPS with 200", out)

    def test_a_history_that_does_not_arrive_fails_and_says_what_to_check(self):
        code, out, _ = self.go(self.World(self, self.GOOD, finished=False), self.OPEN)
        self.assertEqual(code, 1)
        self.assertIn("The end of the test did not arrive in the telemetry. Has the cases app the new code", out)

    def test_when_no_step_ran_the_last_line_says_why_in_one_fixed_word_and_nothing_else_is_printed(self):
        for reason, words in (("off", "the cases app is not set to deliver through the bot"), ("no-owner", "the cases app found no person with the role owner"), ("held", "a switch of the owner (messages or all) holds the cards"),
                              ("other", "the cases app could not read its settings")):
            code, out, _ = self.go(self.World(self, [], finished_extra={"reason": reason}), self.OPEN)
            self.assertEqual(code, 1, reason)
            self.assertIn(f"The cases app sent nothing: {words}", out)
            self.assertIn("The Teams test did not pass", out)
        hostile = "person@example.com 11111111-2222-3333-4444-555555555555 Bearer abcdefghijklmnop"
        code, out, _ = self.go(self.World(self, [], finished_extra={"reason": hostile}), self.OPEN)
        self.assertEqual(code, 1)
        self.assertIn("The cases app sent nothing, for another reason.", out)
        for secret in ("person@example.com", "11111111-2222", "abcdefghijklmnop"):
            self.assertNotIn(secret, out)

    def test_the_queue_refusing_the_message_stops_the_run_with_a_plain_error_and_only_a_pipeline_may_send(self):
        code, out, err = self.go(self.World(self, self.GOOD, queue_status=403), self.OPEN)
        self.assertEqual(code, 1)
        self.assertIn("putting the control message in the queue answered 403", err)
        lines, errors = [], io.StringIO()
        with mock.patch.dict(os.environ, {"GITHUB_ACTIONS": "false"}), contextlib.redirect_stderr(errors), contextlib.redirect_stdout(io.StringIO()):
            code = tc.main(["run", "--storage-account", "stmeternautfn0123abcd", "--insights", self.INSIGHTS], azure=self.World(self, self.GOOD).azure(), fetcher=self.OPEN)
        self.assertEqual(code, 1)
        self.assertIn("only a GitHub Actions run may do that", errors.getvalue())

    def test_the_egress_command_probes_the_two_hosts_and_needs_no_azure(self):
        with contextlib.redirect_stdout(io.StringIO()) as out:
            code = tc.main(["egress"], azure=object(), fetcher=self.OPEN)
        self.assertEqual(code, 0)
        self.assertEqual([h for h, _ in tc.HOSTS], ["login.microsoftonline.com", "smba.trafficmanager.net"])
        self.assertEqual([u for _, u in tc.HOSTS], ["https://login.microsoftonline.com/", "https://smba.trafficmanager.net/teams/"])
        self.assertIn("Egress from the Operator's subnet", out.getvalue())

    def test_the_summary_gets_the_lines_and_the_probe_sends_no_credential(self):
        world = self.World(self, self.GOOD)
        with tempfile.TemporaryDirectory() as tmp:
            summary = Path(tmp) / "summary.md"
            code, _, _ = self.go(world, self.OPEN, ["run", "--storage-account", "stmeternautfn0123abcd", "--insights", self.INSIGHTS, "--minutes", "3", "--summary", str(summary)])
            self.assertEqual(code, 0)
            text = summary.read_text(encoding="utf-8")
        self.assertIn("### The Teams test, and the way out to Teams", text)
        self.assertIn("The Teams test passed", text)
        source = (ROOT / "tools" / "teams-check.py").read_text(encoding="utf-8")
        self.assertNotIn("Authorization", source.split("def fetch", 1)[1].split("def no_answer_word", 1)[0], "the probe carries no credential")


if __name__ == "__main__":
    unittest.main()
