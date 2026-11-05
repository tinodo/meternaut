import contextlib
import importlib.util
import io
import itertools
import json
import os
import re
import sys
import unittest
import uuid
from pathlib import Path
from unittest import mock
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("exchange_setup", ROOT / "tools" / "exchange-setup.py")
xs = importlib.util.module_from_spec(spec)
sys.modules["exchange_setup"] = xs
spec.loader.exec_module(xs)

TENANT = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
CLIENT = "11111111-2222-3333-4444-555555555555"
PRINCIPAL = "66666666-7777-8888-9999-000000000000"
DOMAIN = "contoso.example"
ADDRESS = "meternaut-ai@contoso.example"
OTHER = "someone-else@contoso.example"
SCOPE = "Meternaut sender mailbox"
ROLE = "Application Mail.Send"
FILTER = f"PrimarySmtpAddress -eq '{ADDRESS}'"
ANCHOR = f"UPN:SystemMailbox{{bb558c35-97f1-4cb9-8ff7-d53741dc928c}}@{DOMAIN}"
ARGS = ["--tenant-id", TENANT, "--domain", DOMAIN, "--identity-client-id", CLIENT, "--identity-principal-id", PRINCIPAL]
# one token shaped like a JWT, and one that is not: the second can only be hidden because the tool knows that it handed it out
TOKENS = {"https://outlook.office365.com": ".".join(("eyJhbGciOiJSUzI1NiJ9", "eyJhdWQiOiJleGNoYW5nZSIsInRpZCI6IngifQ", "c2lnbmF0dXJlLWV4Y2hhbmdl")),
          "https://graph.microsoft.com": "graph-token-0123456789-abcdefghij"}
EXCHANGE_URL = f"https://outlook.office365.com/adminapi/beta/{TENANT}/InvokeCommand"
WRITES = {"New-Mailbox", "New-ServicePrincipal", "New-ManagementScope", "Set-ManagementScope", "New-ManagementRoleAssignment"}
ALL_CMDLETS = {"Get-Mailbox", "New-Mailbox", "Get-ServicePrincipal", "New-ServicePrincipal", "Get-ManagementScope", "New-ManagementScope", "Set-ManagementScope",
               "Get-ManagementRoleAssignment", "New-ManagementRoleAssignment", "Test-ServicePrincipalAuthorization"}


class Fail(Exception):
    def __init__(self, status, code, message):
        super().__init__(message)
        self.status, self.code, self.message = status, code, message


def reply(status, document, headers=None):
    return status, headers or {}, json.dumps(document).encode("utf-8")


class Tenant:
    """A small model of Exchange Online and of the two things that the tool reads in Microsoft Graph. It is the transport of the tool: it answers the calls, checks
    that each one is made the way that Exchange expects, and remembers them."""

    def __init__(self):
        self.mailboxes: dict[str, dict] = {}
        self.pointers: dict[str, dict] = {}
        self.scopes: dict[str, dict] = {}
        self.assignments: list[dict] = []
        self.users: dict[str, bool] = {}
        self.pending_users: set[str] = set()
        self.entra_principals = {PRINCIPAL}
        self.entra_assignments: dict[str, list[dict]] = {}
        self.other_mailboxes = {OTHER}
        self.absent_message = "couldn't be found"
        self.absent_as_error = False
        self.scope_covers = None
        self.failures: dict[str, list] = {}
        self.graph_failures: dict[str, tuple] = {}
        self.echo_tokens = False
        self.users_delayed = False
        self.requests: list[tuple] = []
        self.cmdlets: list[tuple[str, dict]] = []
        self.violations: list[str] = []

    # -- a tenant that is set up ---------------------------------------------------------------------------------------------------------------------
    def configured(self) -> "Tenant":
        self.mailboxes["meternaut-ai"] = {"Alias": "meternaut-ai", "PrimarySmtpAddress": ADDRESS, "DisplayName": "Meternaut (AI)", "RecipientTypeDetails": "SharedMailbox"}
        self.pointers[PRINCIPAL] = {"ObjectId": PRINCIPAL, "AppId": CLIENT, "DisplayName": "meternaut-cases"}
        self.scopes[SCOPE] = {"Name": SCOPE, "ScopeRestrictionType": "RecipientScope", "RecipientFilter": FILTER}
        self.assignments.append(self.assignment(ROLE, SCOPE))
        self.users[ADDRESS] = False
        return self

    def assignment(self, role, scope, assignee=PRINCIPAL, name=None):
        return {"Name": name or f"{role}-{len(self.assignments) + 1}", "Role": role, "RoleAssigneeName": assignee, "RoleAssigneeType": "ServicePrincipal",
                "CustomResourceScope": scope}

    def writes(self) -> list[str]:
        return [c for c, _ in self.cmdlets if c in WRITES]

    # -- the transport -------------------------------------------------------------------------------------------------------------------------------
    def __call__(self, method, url, headers, body):
        self.requests.append((method, url, dict(headers), body))
        parts = urlsplit(url)
        if parts.netloc == "outlook.office365.com":
            return self.exchange(method, parts, headers, body)
        if parts.netloc == "graph.microsoft.com":
            return self.graph(method, parts, headers)
        self.violations.append(f"a call to {parts.netloc}")
        return 404, {}, b"{}"

    def exchange(self, method, parts, headers, body):
        try:
            document = json.loads(body.decode("utf-8"))
            cmdlet, parameters = document["CmdletInput"]["CmdletName"], document["CmdletInput"]["Parameters"]
            assert set(document) == {"CmdletInput"} and set(document["CmdletInput"]) == {"CmdletName", "Parameters"}
            assert method == "POST" and parts.path == f"/adminapi/beta/{TENANT}/InvokeCommand" and not parts.query, f"{method} {parts.path}"
            assert headers["Authorization"] == f"Bearer {TOKENS['https://outlook.office365.com']}", "the token of Exchange"
            assert headers["Content-Type"] == "application/json" and headers["Accept"] == "application/json" and headers["X-ResponseFormat"] == "json"
            assert headers["X-CmdletName"] == cmdlet, "X-CmdletName"
            assert str(uuid.UUID(headers["client-request-id"])) == headers["client-request-id"], "client-request-id"
            assert headers["X-AnchorMailbox"] == ANCHOR, "X-AnchorMailbox"
            assert set(headers) == {"Authorization", "Content-Type", "Accept", "X-ResponseFormat", "X-CmdletName", "client-request-id", "X-AnchorMailbox"}
        except (AssertionError, KeyError, ValueError, TypeError) as error:
            self.violations.append(f"not what Exchange expects: {error}")
            return reply(400, {"error": {"code": "BadRequest", "message": f"not what Exchange expects: {error}"}})
        self.cmdlets.append((cmdlet, parameters))
        planned = self.failures.get(cmdlet)
        if planned:
            return planned.pop(0)
        handler = getattr(self, "cmd_" + cmdlet.replace("-", "_"), None)
        try:
            if handler is None:
                raise Fail(400, "CommandNotFound", f"the term {cmdlet} is not recognised")
            return reply(200, {"value": handler(parameters)})
        except Fail as failure:
            message = failure.message + (f" Bearer {TOKENS['https://outlook.office365.com']}" if self.echo_tokens else "")
            return reply(failure.status, {"error": {"code": failure.code, "message": message}})

    def found(self, objects, what):
        if objects or not self.absent_as_error:
            return objects
        raise Fail(400, "Ex6F9304|ManagementObjectNotFoundException", f"The operation couldn't be performed because object '{what}' {self.absent_message} on 'FAKE'.")

    def cmd_Get_Mailbox(self, p):
        key = p["Identity"].lower()
        return self.found([dict(m) for a, m in self.mailboxes.items() if key in (a.lower(), m["PrimarySmtpAddress"].lower())], p["Identity"])

    def cmd_New_Mailbox(self, p):
        assert p["Shared"] is True and set(p) == {"Shared", "Name", "DisplayName", "Alias", "PrimarySmtpAddress"}, "the parameters of New-Mailbox"
        if p["Alias"] in self.mailboxes:
            raise Fail(400, "AlreadyExists", f"The proxy address SMTP:{p['PrimarySmtpAddress']} is already being used.")
        self.mailboxes[p["Alias"]] = {"Alias": p["Alias"], "PrimarySmtpAddress": p["PrimarySmtpAddress"], "DisplayName": p["DisplayName"], "RecipientTypeDetails": "SharedMailbox"}
        if self.users_delayed:
            self.pending_users.add(p["PrimarySmtpAddress"].lower())
        self.users[p["PrimarySmtpAddress"].lower()] = False
        return [dict(self.mailboxes[p["Alias"]])]

    def cmd_Get_ServicePrincipal(self, p):
        return self.found([dict(v) for k, v in self.pointers.items() if p["Identity"].lower() in (k.lower(), v["AppId"].lower())], p["Identity"])

    def cmd_New_ServicePrincipal(self, p):
        assert set(p) == {"AppId", "ObjectId", "DisplayName"}, "the parameters of New-ServicePrincipal"
        if p["ObjectId"] not in self.entra_principals:
            raise Fail(400, "InvalidPointer", "The service principal does not exist in Microsoft Entra ID.")
        if p["ObjectId"] in self.pointers:
            raise Fail(400, "AlreadyExists", "The service principal already exists.")
        self.pointers[p["ObjectId"]] = {"ObjectId": p["ObjectId"], "AppId": p["AppId"], "DisplayName": p["DisplayName"]}
        return [dict(self.pointers[p["ObjectId"]])]

    def cmd_Get_ManagementScope(self, p):
        return self.found([dict(v) for k, v in self.scopes.items() if k.lower() == p["Identity"].lower()], p["Identity"])

    def cmd_New_ManagementScope(self, p):
        assert set(p) == {"Name", "RecipientRestrictionFilter"}, "the parameters of New-ManagementScope"
        if p["Name"] in self.scopes:
            raise Fail(400, "AlreadyExists", "The management scope already exists.")
        self.scopes[p["Name"]] = {"Name": p["Name"], "ScopeRestrictionType": "RecipientScope", "RecipientFilter": p["RecipientRestrictionFilter"]}
        return [dict(self.scopes[p["Name"]])]

    def cmd_Set_ManagementScope(self, p):
        assert set(p) == {"Identity", "RecipientRestrictionFilter"}, "the parameters of Set-ManagementScope"
        if p["Identity"] not in self.scopes:
            raise Fail(400, "NotFound", f"The operation couldn't be performed because object '{p['Identity']}' couldn't be found on 'FAKE'.")
        self.scopes[p["Identity"]]["RecipientFilter"] = p["RecipientRestrictionFilter"]
        return [dict(self.scopes[p["Identity"]])]

    def cmd_Get_ManagementRoleAssignment(self, p):
        assert set(p) <= {"RoleAssignee", "Role"} and "RoleAssignee" in p, "the parameters of Get-ManagementRoleAssignment"
        found = [dict(a) for a in self.assignments if a["RoleAssigneeName"].lower() == p["RoleAssignee"].lower() and p.get("Role", a["Role"]).lower() == a["Role"].lower()]
        return self.found(found, p["RoleAssignee"])

    def cmd_New_ManagementRoleAssignment(self, p):
        assert set(p) == {"App", "Role", "CustomResourceScope"}, "the parameters of New-ManagementRoleAssignment"
        if p["App"] not in self.pointers:
            raise Fail(400, "NotFound", f"The operation couldn't be performed because object '{p['App']}' couldn't be found on 'FAKE'.")
        if p["CustomResourceScope"] not in self.scopes:
            raise Fail(400, "NotFound", f"The operation couldn't be performed because object '{p['CustomResourceScope']}' couldn't be found on 'FAKE'.")
        self.assignments.append(self.assignment(p["Role"], p["CustomResourceScope"], p["App"]))
        return [dict(self.assignments[-1])]

    def covers(self, scope, address):
        if self.scope_covers:
            return self.scope_covers(scope, address)
        if scope not in self.scopes:
            return False
        match = re.fullmatch(r"\(*\s*PrimarySmtpAddress\s+-eq\s+'([^']+)'\s*\)*", self.scopes[scope]["RecipientFilter"].strip(), re.I)
        return bool(match) and match.group(1).lower() == address.lower()

    def cmd_Test_ServicePrincipalAuthorization(self, p):
        assert set(p) == {"Identity", "Resource"}, "the parameters of Test-ServicePrincipalAuthorization"
        if p["Identity"] not in self.pointers:
            raise Fail(400, "NotFound", f"The operation couldn't be performed because object '{p['Identity']}' couldn't be found on 'FAKE'.")
        known = {m["PrimarySmtpAddress"].lower() for m in self.mailboxes.values()} | {o.lower() for o in self.other_mailboxes}
        if p["Resource"].lower() not in known:
            raise Fail(400, "NotFound", f"The operation couldn't be performed because object '{p['Resource']}' couldn't be found on 'FAKE'.")
        return [{"RoleName": a["Role"], "GrantedPermissions": "Mail.Send", "AllowedResourceScope": a["CustomResourceScope"] or "Organization",
                 "ScopeType": "CustomRecipientScope" if a["CustomResourceScope"] else "Organization",
                 "InScope": True if not a["CustomResourceScope"] else self.covers(a["CustomResourceScope"], p["Resource"])}
                for a in self.assignments if a["RoleAssigneeName"] == p["Identity"]]

    def graph(self, method, parts, headers):
        if method != "GET" or headers.get("Authorization") != f"Bearer {TOKENS['https://graph.microsoft.com']}":
            self.violations.append(f"a Graph call that is not a GET with the Graph token: {method}")
            return reply(401, {"error": {"code": "InvalidAuthenticationToken", "message": "no"}})
        user = re.fullmatch(r"/v1\.0/users/([^/]+)", parts.path)
        roles = re.fullmatch(r"/v1\.0/servicePrincipals/([^/]+)/appRoleAssignments", parts.path)
        key = "users" if user else "roles" if roles else ""
        if key in self.graph_failures:
            status, document = self.graph_failures[key]
            if self.echo_tokens:
                document = {"error": {"code": "Forbidden", "message": f"denied for Bearer {TOKENS['https://graph.microsoft.com']} and {TOKENS['https://graph.microsoft.com']}"}}
            return reply(status, document)
        if user:
            address = unquote(user.group(1)).lower()
            if parts.query != "$select=accountEnabled":
                self.violations.append(f"the query of the user read: {parts.query}")
            if address in self.pending_users or address not in self.users:
                return reply(404, {"error": {"code": "Request_ResourceNotFound", "message": f"Resource '{address}' does not exist or one of its queried reference-property objects are not present."}})
            return reply(200, {"@odata.context": "https://graph.microsoft.com/v1.0/$metadata#users(accountEnabled)/$entity", "accountEnabled": self.users[address]})
        if roles:
            if roles.group(1) not in self.entra_principals:
                return reply(404, {"error": {"code": "Request_ResourceNotFound", "message": "no such service principal"}})
            return reply(200, {"value": list(self.entra_assignments.get(roles.group(1), []))})
        self.violations.append(f"a Graph path that the tool should not read: {parts.path}")
        return reply(404, {"error": {"code": "NotFound", "message": "no"}})


class FakeAz:
    """The Azure CLI as the tool calls it: it hands out the tokens, and remembers what it was asked."""

    def __init__(self, fail=False):
        self.calls, self.fail = [], fail

    def __call__(self, args):
        self.calls.append(list(args))
        if args[:2] == ["account", "get-access-token"] and not self.fail:
            return 0, TOKENS[args[args.index("--resource") + 1]] + "\n", ""
        if args[:2] == ["account", "get-access-token"]:
            return 1, "", "ERROR: Please run 'az login' to setup account."
        return 1, "", f"unexpected command {args[:3]}"


def run(argv, tenant=None, env=None, az=None):
    tenant = Tenant() if tenant is None else tenant
    az = FakeAz() if az is None else az
    lines, errors, sleeps = [], io.StringIO(), []
    ids = (str(uuid.UUID(int=n)) for n in itertools.count(1))
    with contextlib.redirect_stderr(errors):
        code = xs.main(argv, az=az, transport=tenant, env={} if env is None else env, out=lines.append, sleep=sleeps.append, new_id=lambda: next(ids))
    return code, "\n".join(lines), errors.getvalue(), sleeps


def states(output: str) -> dict[str, str]:
    """The state shown for each item key, from the lines of a report (the last report when there are two)."""
    found = {}
    for line in output.splitlines():
        match = re.match(r"^  (present|MISSING|DIFFERS|FAIL|cannot yet|UNREADABLE|not yet visible|not run)\s+(\d[ab]?)\s", line)
        if match:
            found[match.group(2)] = match.group(1)
    return found


class TheInputs(unittest.TestCase):
    def refused(self, argv, words):
        tenant, az = Tenant(), FakeAz()
        code, out, err, _ = run(argv, tenant, az=az)
        self.assertEqual(code, 1, argv)
        self.assertIn(words, err)
        self.assertEqual((out, tenant.requests, az.calls), ("", [], []), "nothing was asked of anybody")

    def test_every_required_option_is_required(self):
        pairs = list(zip(ARGS[::2], ARGS[1::2]))
        for index, (option, _) in enumerate(pairs):
            with self.subTest(option=option):
                argv = ["check"] + [x for i, pair in enumerate(pairs) if i != index for x in pair]
                self.refused(argv, f"{option} is required")

    def test_the_ids_are_guids(self):
        for option in ("--tenant-id", "--identity-client-id", "--identity-principal-id"):
            for bad in ("x", "11111111-2222-3333-4444-55555555555", "11111111-2222-3333-4444-5555555555555", "11111111-2222-3333-4444-55555555555g",
                        "11111111222233334444555555555555", "11111111-2222-3333-4444-555555555555\n", " 11111111-2222-3333-4444-555555555555"):
                with self.subTest(option=option, value=bad):
                    argv = ["check"] + [x for pair in zip(ARGS[::2], ARGS[1::2]) for x in ((pair[0], bad) if pair[0] == option else pair)]
                    self.refused(argv, f"{option} is not a GUID")

    def test_the_client_id_and_the_principal_id_are_two_values(self):
        self.refused(["check", "--tenant-id", TENANT, "--domain", DOMAIN, "--identity-client-id", CLIENT, "--identity-principal-id", CLIENT.upper()], "two different values")

    def test_the_domain_is_a_domain(self):
        for bad in ("contoso", "a..example", "-a.example", "a-.example", "a.example/x", "a b.example", "contoso.example\n", "https://contoso.example", "a.b", "a@b.example", ""):
            with self.subTest(domain=bad):
                self.refused(["check", "--tenant-id", TENANT, f"--domain={bad}", "--identity-client-id", CLIENT, "--identity-principal-id", PRINCIPAL],
                             "--domain is required" if bad == "" else "--domain is not a domain name")

    def test_the_alias_is_the_part_before_the_at_sign(self):
        for bad in ("-x", "x-", "a b", "a@b", "x" * 65, "a/b", "a\n", "a'b", "a;b"):
            with self.subTest(alias=bad):
                self.refused(["check", *ARGS, f"--alias={bad}"], "--alias is the part of the address")

    def test_the_display_name_is_one_line_and_ends_with_the_ai_mark(self):
        for bad, words in (("Meternaut", '"(AI)"'), ("Meternaut (AI cost assistant)", '"(AI)"'), ("(AI) Meternaut", '"(AI)"'), ("x" * 90 + " (AI)", "at most 80"),
                           ("Meternaut\n(AI)", "one line"), (" Meternaut (AI)", "one line")):
            with self.subTest(name=bad):
                self.refused(["check", *ARGS, "--display-name", bad], words)

    def test_the_identity_name_and_the_other_mailbox_are_checked(self):
        for bad in ("x" * 90, "a;b", "-a", "a\n"):
            with self.subTest(identity=bad):
                self.refused(["check", *ARGS, f"--identity-name={bad}"], "--identity-name is a name")
        for bad in ("someone", "a@b", "a b@contoso.example", "@contoso.example", "a@contoso.example\n", "a/b@contoso.example"):
            with self.subTest(other=bad):
                self.refused(["check", *ARGS, "--other-mailbox", bad], "--other-mailbox is an address")
        self.refused(["check", *ARGS, "--other-mailbox", ADDRESS.upper()], "a different mailbox")

    def test_the_defaults_name_the_mailbox_the_pointer_and_the_scope(self):
        tenant = Tenant()
        code, out, err, _ = run(["apply", *ARGS, "--apply"], tenant)
        self.assertEqual(code, 0, out + err)
        calls = {cmdlet: parameters for cmdlet, parameters in tenant.cmdlets if cmdlet in WRITES}
        self.assertEqual(calls["New-Mailbox"], {"Shared": True, "Name": "meternaut-ai", "DisplayName": "Meternaut (AI)", "Alias": "meternaut-ai", "PrimarySmtpAddress": ADDRESS})
        self.assertEqual(calls["New-ServicePrincipal"], {"AppId": CLIENT, "ObjectId": PRINCIPAL, "DisplayName": "meternaut-cases"})
        self.assertEqual(calls["New-ManagementScope"], {"Name": SCOPE, "RecipientRestrictionFilter": FILTER})
        self.assertEqual(calls["New-ManagementRoleAssignment"], {"App": PRINCIPAL, "Role": ROLE, "CustomResourceScope": SCOPE})

    def test_the_options_change_the_names_and_the_case_of_ids_and_addresses_does_not_matter(self):
        tenant = Tenant()
        argv = ["apply", "--tenant-id", TENANT.upper(), "--domain", "Contoso.Example", "--alias", "Sender-One", "--display-name", "Sender One (AI)",
                "--identity-client-id", CLIENT.upper(), "--identity-principal-id", PRINCIPAL.upper(), "--identity-name", "my identity (test)", "--apply"]
        code, out, err, _ = run(argv, tenant)
        self.assertEqual(code, 0, out + err)
        calls = {cmdlet: parameters for cmdlet, parameters in tenant.cmdlets if cmdlet in WRITES}
        self.assertEqual(calls["New-Mailbox"], {"Shared": True, "Name": "sender-one", "DisplayName": "Sender One (AI)", "Alias": "sender-one",
                                                "PrimarySmtpAddress": "sender-one@contoso.example"})
        self.assertEqual(calls["New-ManagementScope"], {"Name": SCOPE, "RecipientRestrictionFilter": "PrimarySmtpAddress -eq 'sender-one@contoso.example'"})
        self.assertEqual(calls["New-ServicePrincipal"], {"AppId": CLIENT, "ObjectId": PRINCIPAL, "DisplayName": "my identity (test)"})
        self.assertEqual(tenant.violations, [])


class ThePipelineRefusal(unittest.TestCase):
    def test_nothing_runs_in_github_actions_and_nothing_is_asked_of_anybody(self):
        for command in (["check"], ["apply"], ["apply", "--apply"]):
            for value in ("true", "True", "1"):
                with self.subTest(command=command, value=value):
                    tenant, az = Tenant(), FakeAz()
                    code, out, err, _ = run([*command[:1], *ARGS, *command[1:]], tenant, env={"GITHUB_ACTIONS": value}, az=az)
                    self.assertEqual(code, 1)
                    self.assertIn("never a pipeline", err)
                    self.assertEqual((out, tenant.requests, az.calls), ("", [], []))

    def test_the_variable_of_the_process_is_not_read_by_the_logic(self):
        for env in ({}, {"GITHUB_ACTIONS": ""}, {"GITHUB_ACTIONS": "false"}):
            with self.subTest(env=env):
                self.assertEqual(run(["check", *ARGS], Tenant().configured(), env=env)[0], 0)
        with mock.patch.dict(os.environ, {"GITHUB_ACTIONS": "true"}):
            self.assertEqual(run(["check", *ARGS], Tenant().configured(), env={})[0], 0, "only the env that is passed counts")


class Check(unittest.TestCase):
    def test_a_tenant_with_nothing_lists_every_item_as_missing_and_exits_1(self):
        tenant = Tenant()
        code, out, err, _ = run(["check", *ARGS], tenant)
        self.assertEqual(code, 1, out + err)
        self.assertEqual(states(out), {"1": "MISSING", "2": "MISSING", "3": "MISSING", "4": "MISSING", "4b": "present", "5a": "cannot yet", "5b": "not run",
                                       "6": "cannot yet", "7": "present"})
        self.assertIn(f"Shared mailbox {ADDRESS}", out)
        self.assertEqual(tenant.writes(), [])
        self.assertEqual(tenant.violations, [])
        self.assertIn("2 of 9 present.", out)

    def test_a_tenant_that_is_set_up_is_in_order_and_exits_0(self):
        tenant = Tenant().configured()
        code, out, err, _ = run(["check", *ARGS, "--other-mailbox", OTHER], tenant)
        self.assertEqual((code, err), (0, ""))
        self.assertEqual(states(out), {key: "present" for key in ("1", "2", "3", "4", "4b", "5a", "5b", "6", "7")})
        self.assertIn("9 of 9 present.", out)
        self.assertIn("InScope true", out)
        self.assertIn("InScope false", out)
        self.assertEqual(tenant.writes(), [])

    def test_without_another_mailbox_the_negative_proof_is_not_run_and_says_how_to_run_it(self):
        code, out, err, _ = run(["check", *ARGS], Tenant().configured())
        self.assertEqual(code, 0)
        self.assertEqual(states(out)["5b"], "not run")
        self.assertIn("give --other-mailbox", out)

    def test_every_way_of_saying_that_nothing_was_found_means_absent(self):
        for message in ("couldn't be found", "was not found", "can't be found", "could not be found"):
            for as_error in (False, True):
                with self.subTest(message=message, as_error=as_error):
                    tenant = Tenant()
                    tenant.absent_as_error, tenant.absent_message = as_error, message
                    code, out, err, _ = run(["check", *ARGS], tenant)
                    self.assertEqual((code, states(out)["1"], states(out)["3"], states(out)["4"]), (1, "MISSING", "MISSING", "MISSING"), out + err)

    def test_the_other_errors_are_real_ones_with_the_code_and_the_first_300_characters(self):
        tenant = Tenant()
        tenant.failures["Get-Mailbox"] = [reply(403, {"error": {"code": "Forbidden", "message": "x" * 500}})]
        code, out, err, _ = run(["check", *ARGS], tenant)
        self.assertEqual(code, 1)
        self.assertEqual(err.strip(), "error: Get-Mailbox failed: 403 Forbidden: " + "x" * 300)
        self.assertNotIn("MISSING", out, "nothing is reported when a call fails for a real reason")

    def test_a_refusal_for_who_you_are_is_never_taken_for_an_absent_object(self):
        for status in (401, 403):
            tenant = Tenant()
            tenant.failures["Get-Mailbox"] = [reply(status, {"error": {"code": "Denied", "message": "The object couldn't be found because you may not see it."}})]
            code, out, err, _ = run(["check", *ARGS], tenant)
            self.assertEqual(code, 1)
            self.assertIn(f"Get-Mailbox failed: {status} Denied", err)

    def test_an_error_that_is_not_json_or_has_no_error_object_is_still_shown(self):
        for answer, words in (((500, {}, b"<html>bad gateway</html>"), "500: <html>bad gateway</html>"), ((400, {}, b'{"message":"plain message"}'), "400: plain message"),
                              ((400, {}, b"{}"), "Get-Mailbox failed: 400"), ((502, {}, b""), "Get-Mailbox failed: 502")):
            with self.subTest(answer=answer):
                tenant = Tenant()
                tenant.failures["Get-Mailbox"] = [answer]
                code, out, err, _ = run(["check", *ARGS], tenant)
                self.assertEqual(code, 1)
                self.assertIn(words, err)

    def test_a_call_that_is_throttled_or_unavailable_is_tried_once_more_after_the_wait_that_was_asked_for(self):
        for status, headers, wait in ((429, {"retry-after": "7"}, 7.0), (503, {}, 5.0), (429, {"Retry-After": "500"}, 60.0), (503, {"retry-after": "soon"}, 5.0)):
            with self.subTest(status=status, headers=headers):
                tenant = Tenant().configured()
                tenant.failures["Get-Mailbox"] = [reply(status, {"error": {"code": "TooBusy", "message": "later"}}, headers)]
                code, out, err, sleeps = run(["check", *ARGS], tenant)
                self.assertEqual((code, sleeps), (0, [wait]), out + err)
                self.assertEqual([c for c, _ in tenant.cmdlets].count("Get-Mailbox"), 2)

    def test_a_second_failure_of_the_same_call_is_an_error(self):
        tenant = Tenant().configured()
        busy = reply(429, {"error": {"code": "TooBusy", "message": "later"}}, {"retry-after": "1"})
        tenant.failures["Get-Mailbox"] = [busy, busy]
        code, out, err, sleeps = run(["check", *ARGS], tenant)
        self.assertEqual((code, sleeps), (1, [1.0]))
        self.assertIn("Get-Mailbox failed: 429 TooBusy: later", err)

    def test_the_scope_that_names_another_filter_differs_and_the_filter_is_compared_as_the_same_when_only_spacing_case_or_brackets_differ(self):
        tenant = Tenant().configured()
        tenant.scopes[SCOPE]["RecipientFilter"] = "PrimarySmtpAddress -eq 'other@contoso.example'"
        code, out, err, _ = run(["check", *ARGS], tenant)
        self.assertEqual(code, 1)
        self.assertEqual(states(out)["3"], "DIFFERS")
        self.assertIn(f"its filter is PrimarySmtpAddress -eq 'other@contoso.example'; it must be {FILTER}", out)
        self.assertEqual(states(out)["5a"], "MISSING", "the mailbox is outside that scope")
        for same in (f"({FILTER})", f"((  {FILTER.upper()}  ))", FILTER.replace(" -eq ", "   -eq   ")):
            tenant.scopes[SCOPE]["RecipientFilter"] = same
            code, out, err, _ = run(["check", *ARGS], tenant)
            self.assertEqual((code, states(out)["3"]), (0, "present"), same)
        tenant.scopes[SCOPE]["RecipientFilter"] = f"(PrimarySmtpAddress -eq 'a@contoso.example') -or ({FILTER})"
        self.assertEqual(states(run(["check", *ARGS], tenant)[1])["3"], "DIFFERS", "a filter that adds a second mailbox is a different filter")

    def test_a_role_that_is_assigned_without_the_scope_is_missing_and_a_stray_assignment_fails_loudly(self):
        tenant = Tenant().configured()
        tenant.assignments[0]["CustomResourceScope"] = None
        tenant.assignments[0]["Name"] = "Application Mail.Send-unscoped"
        code, out, err, _ = run(["check", *ARGS], tenant)
        self.assertEqual(code, 1)
        self.assertEqual((states(out)["4"], states(out)["4b"]), ("MISSING", "FAIL"))
        self.assertIn("THE IDENTITY HOLDS EXCHANGE ROLE ASSIGNMENTS THAT IT MUST NOT HOLD", out)
        self.assertIn("no custom resource scope, so it covers every mailbox", out)
        self.assertIn("Remove-ManagementRoleAssignment -Identity 'Application Mail.Send-unscoped'", out)
        self.assertIn("This tool removes nothing", out)

    def test_any_other_application_role_and_any_second_scope_is_a_stray(self):
        for role, scope in (("Application Calendars.Read", SCOPE), ("Application Mail.Read", "Another scope"), ("Application Mail.Send", "Another scope"),
                            ("Application Mail.Read", None)):
            with self.subTest(role=role, scope=scope):
                tenant = Tenant().configured()
                tenant.assignments.append(tenant.assignment(role, scope, name="Stray-1"))
                code, out, err, _ = run(["check", *ARGS], tenant)
                self.assertEqual(code, 1)
                self.assertEqual((states(out)["4"], states(out)["4b"]), ("present", "FAIL"))
                self.assertIn(f"role {role}", out)
                self.assertIn("Remove-ManagementRoleAssignment -Identity 'Stray-1'", out)

    def test_the_hint_to_remove_an_assignment_is_a_safe_powershell_string_whatever_the_name_holds(self):
        tenant = Tenant().configured()
        tenant.assignments.append(tenant.assignment("Application Mail.Read", None, name="it's $(whoami) \"x\""))
        code, out, err, _ = run(["check", *ARGS], tenant)
        self.assertEqual(code, 1)
        self.assertIn("Remove-ManagementRoleAssignment -Identity 'it''s $(whoami) \"x\"'", out)

    def test_the_assignments_of_another_identity_are_not_ours(self):
        tenant = Tenant().configured()
        tenant.assignments.append(tenant.assignment("Application Mail.Read", None, assignee="99999999-9999-9999-9999-999999999999"))
        self.assertEqual(run(["check", *ARGS], tenant)[0], 0)

    def test_the_negative_proof_fails_when_the_identity_can_send_as_another_mailbox(self):
        tenant = Tenant().configured()
        tenant.scope_covers = lambda scope, address: True
        code, out, err, _ = run(["check", *ARGS, "--other-mailbox", OTHER], tenant)
        self.assertEqual(code, 1)
        self.assertEqual((states(out)["5a"], states(out)["5b"]), ("present", "FAIL"))
        self.assertIn("InScope TRUE", out)
        self.assertIn(f"can send as {OTHER}", out)

    def test_the_negative_proof_is_a_real_error_when_the_other_mailbox_does_not_exist(self):
        tenant = Tenant().configured()
        tenant.other_mailboxes = set()
        code, out, err, _ = run(["check", *ARGS, "--other-mailbox", OTHER], tenant)
        self.assertEqual(code, 1)
        self.assertIn("Test-ServicePrincipalAuthorization failed: 400 NotFound", err)

    def test_the_proofs_need_the_items_before_them(self):
        tenant = Tenant().configured()
        del tenant.pointers[PRINCIPAL]
        code, out, err, _ = run(["check", *ARGS, "--other-mailbox", OTHER], tenant)
        self.assertEqual(code, 1)
        self.assertEqual((states(out)["2"], states(out)["4"], states(out)["5a"], states(out)["5b"]), ("MISSING", "MISSING", "cannot yet", "cannot yet"))
        self.assertNotIn("Test-ServicePrincipalAuthorization", [c for c, _ in tenant.cmdlets])
        self.assertNotIn("Get-ManagementRoleAssignment", [c for c, _ in tenant.cmdlets], "nothing can be assigned to a pointer that is not there")

    def test_the_signin_of_the_mailbox_user_must_be_blocked(self):
        tenant = Tenant().configured()
        tenant.users[ADDRESS] = True
        code, out, err, _ = run(["check", *ARGS], tenant)
        self.assertEqual((code, states(out)["6"]), (1, "MISSING"))
        self.assertIn("accountEnabled is TRUE", out)
        self.assertIn("This tool does not change users", out)

    def test_a_user_that_is_not_there_yet_is_not_a_failure_and_says_so(self):
        tenant = Tenant().configured()
        tenant.pending_users.add(ADDRESS)
        code, out, err, _ = run(["check", *ARGS], tenant)
        self.assertEqual((code, states(out)["6"]), (0, "not yet visible"))
        self.assertIn("can take a few minutes to appear", out)
        self.assertIn("7 of 9 present.", out)

    def test_a_signin_that_cannot_be_read_is_not_taken_for_blocked(self):
        for status in (401, 403, 500):
            tenant = Tenant().configured()
            tenant.graph_failures["users"] = (status, {"error": {"code": "Authorization_RequestDenied", "message": "Insufficient privileges"}})
            code, out, err, _ = run(["check", *ARGS], tenant)
            self.assertEqual((code, states(out)["6"]), (1, "UNREADABLE"), status)
            self.assertIn(f"{status} Authorization_RequestDenied: Insufficient privileges", out)

    def test_a_graph_token_that_cannot_be_had_leaves_the_graph_items_unreadable_and_not_the_exchange_ones(self):
        class NoGraph(FakeAz):
            def __call__(self, args):
                if "https://graph.microsoft.com" in args:
                    self.calls.append(list(args))
                    return 1, "", "ERROR: AADSTS65001: the user has not consented"
                return super().__call__(args)

        code, out, err, _ = run(["check", *ARGS], Tenant().configured(), az=NoGraph())
        self.assertEqual(code, 1)
        self.assertEqual((states(out)["1"], states(out)["6"], states(out)["7"]), ("present", "UNREADABLE", "UNREADABLE"))
        self.assertIn("AADSTS65001", out)

    def test_an_application_permission_in_entra_fails_loudly_and_blocks_apply(self):
        tenant = Tenant().configured()
        tenant.entra_assignments[PRINCIPAL] = [{"id": "x", "appRoleId": "b633e1c5-b582-4048-a93e-9f11b44c7e96", "resourceDisplayName": "Microsoft Graph"}]
        code, out, err, _ = run(["check", *ARGS], tenant)
        self.assertEqual((code, states(out)["7"]), (1, "FAIL"))
        self.assertIn("THE IDENTITY HOLDS APPLICATION PERMISSIONS IN MICROSOFT ENTRA", out)
        self.assertIn("Microsoft Graph: app role b633e1c5-b582-4048-a93e-9f11b44c7e96", out)
        self.assertIn("This tool removes nothing", out)

    def test_an_identity_that_entra_does_not_know_is_unreadable(self):
        tenant = Tenant().configured()
        tenant.entra_principals = set()
        code, out, err, _ = run(["check", *ARGS], tenant)
        self.assertEqual((code, states(out)["7"]), (1, "UNREADABLE"))
        self.assertIn("check --identity-principal-id", out)

    def test_check_reads_and_never_writes(self):
        for tenant in (Tenant(), Tenant().configured()):
            run(["check", *ARGS, "--other-mailbox", OTHER], tenant)
            self.assertEqual(tenant.writes(), [])
            self.assertTrue(all(method == "GET" or url == EXCHANGE_URL for method, url, _, _ in tenant.requests))


class Apply(unittest.TestCase):
    def test_a_dry_run_says_what_it_would_send_and_changes_nothing(self):
        tenant = Tenant()
        before = (dict(tenant.mailboxes), dict(tenant.pointers), dict(tenant.scopes), list(tenant.assignments))
        code, out, err, _ = run(["apply", *ARGS], tenant)
        self.assertEqual((code, err), (0, ""))
        self.assertEqual(tenant.writes(), [])
        self.assertEqual(before, (tenant.mailboxes, tenant.pointers, tenant.scopes, tenant.assignments))
        self.assertIn("4 cmdlet(s) would be sent to Exchange, and nothing else:", out)
        for cmdlet in ("New-Mailbox", "New-ServicePrincipal", "New-ManagementScope", "New-ManagementRoleAssignment"):
            self.assertIn(f"  {cmdlet} {{", out)
        self.assertIn(json.dumps({"App": PRINCIPAL, "Role": ROLE, "CustomResourceScope": SCOPE}), out)
        self.assertIn("This was a dry run. Run again with --apply to send them.", out)
        self.assertLess(out.index("New-Mailbox {"), out.index("New-ServicePrincipal {"))
        self.assertLess(out.index("New-ServicePrincipal {"), out.index("New-ManagementScope {"))
        self.assertLess(out.index("New-ManagementScope {"), out.index("New-ManagementRoleAssignment {"))

    def test_apply_makes_everything_in_order_and_checks_again_and_a_second_run_changes_nothing(self):
        tenant = Tenant()
        code, out, err, _ = run(["apply", *ARGS, "--other-mailbox", OTHER, "--apply"], tenant)
        self.assertEqual((code, err), (0, ""), out)
        self.assertEqual(tenant.writes(), ["New-Mailbox", "New-ServicePrincipal", "New-ManagementScope", "New-ManagementRoleAssignment"])
        self.assertEqual(tenant.violations, [])
        self.assertIn("Checking again:", out)
        self.assertEqual(states(out), {key: "present" for key in ("1", "2", "3", "4", "4b", "5a", "5b", "6", "7")})
        self.assertEqual(tenant.mailboxes["meternaut-ai"]["RecipientTypeDetails"], "SharedMailbox")
        self.assertEqual(tenant.scopes[SCOPE]["RecipientFilter"], FILTER)
        self.assertEqual([(a["Role"], a["CustomResourceScope"]) for a in tenant.assignments], [(ROLE, SCOPE)])
        done = len(tenant.cmdlets)
        code, out, err, _ = run(["apply", *ARGS, "--other-mailbox", OTHER, "--apply"], tenant)
        self.assertEqual((code, err), (0, ""), out)
        self.assertEqual([c for c, _ in tenant.cmdlets[done:] if c in WRITES], [])
        self.assertIn("Nothing to create or change.", out)
        self.assertNotIn("Checking again:", out)
        self.assertEqual(len(tenant.assignments), 1)

    def test_only_what_is_missing_is_created(self):
        tenant = Tenant().configured()
        del tenant.scopes[SCOPE]
        del tenant.assignments[0]
        code, out, err, _ = run(["apply", *ARGS, "--apply"], tenant)
        self.assertEqual(code, 0, out + err)
        self.assertEqual(tenant.writes(), ["New-ManagementScope", "New-ManagementRoleAssignment"])

    def test_a_scope_with_another_filter_is_set_right_and_nothing_else_is_made(self):
        tenant = Tenant().configured()
        tenant.scopes[SCOPE]["RecipientFilter"] = "PrimarySmtpAddress -eq 'wrong@contoso.example'"
        code, out, err, _ = run(["apply", *ARGS, "--apply"], tenant)
        self.assertEqual(code, 0, out + err)
        self.assertEqual(tenant.writes(), ["Set-ManagementScope"])
        self.assertEqual(dict(tenant.cmdlets)["Set-ManagementScope"], {"Identity": SCOPE, "RecipientRestrictionFilter": FILTER})
        self.assertEqual(tenant.scopes[SCOPE]["RecipientFilter"], FILTER)
        self.assertEqual(states(out)["3"], "present")
        dry = Tenant().configured()
        dry.scopes[SCOPE]["RecipientFilter"] = "PrimarySmtpAddress -eq 'wrong@contoso.example'"
        code, out, err, _ = run(["apply", *ARGS], dry)
        self.assertEqual((code, dry.writes()), (0, []))
        self.assertIn("Set-ManagementScope", out)

    def test_a_stray_role_assignment_stops_apply_before_anything_is_made_and_says_what_to_remove(self):
        for flags in ([], ["--apply"]):
            tenant = Tenant()
            tenant.pointers[PRINCIPAL] = {"ObjectId": PRINCIPAL, "AppId": CLIENT, "DisplayName": "x"}
            tenant.assignments.append(tenant.assignment("Application Mail.Send", None, name="Application Mail.Send-everyone"))
            code, out, err, _ = run(["apply", *ARGS, *flags], tenant)
            self.assertEqual(code, 1, out)
            self.assertEqual(tenant.writes(), [])
            self.assertIn("Nothing was changed.", out)
            self.assertIn("Remove-ManagementRoleAssignment -Identity 'Application Mail.Send-everyone'", out)
            self.assertEqual(len(tenant.assignments), 1, "nothing was removed and nothing was added")
            self.assertFalse([c for c, _ in tenant.cmdlets if c.startswith("Remove")])

    def test_an_application_permission_in_entra_stops_apply_too(self):
        tenant = Tenant()
        tenant.entra_assignments[PRINCIPAL] = [{"appRoleId": "x", "resourceDisplayName": "Microsoft Graph"}]
        code, out, err, _ = run(["apply", *ARGS, "--apply"], tenant)
        self.assertEqual((code, tenant.writes()), (1, []))
        self.assertIn("Nothing was changed.", out)

    def test_a_user_that_is_not_visible_yet_after_the_mailbox_was_made_is_not_a_failure(self):
        tenant = Tenant()
        tenant.users_delayed = True
        code, out, err, _ = run(["apply", *ARGS, "--apply"], tenant)
        self.assertEqual(code, 0, out + err)
        self.assertEqual(states(out)["6"], "not yet visible")
        tenant.pending_users.clear()
        code, out, err, _ = run(["check", *ARGS], tenant)
        self.assertEqual((code, states(out)["6"]), (0, "present"))

    def test_a_cmdlet_that_fails_stops_the_run_and_the_later_ones_are_not_sent(self):
        tenant = Tenant()
        tenant.entra_principals = set()
        code, out, err, _ = run(["apply", *ARGS, "--apply"], tenant)
        self.assertEqual(code, 1)
        self.assertIn("New-ServicePrincipal failed: 400 InvalidPointer", err)
        self.assertEqual(tenant.writes(), ["New-Mailbox", "New-ServicePrincipal"])

    def test_the_delay_of_exchange_is_said_after_a_role_or_a_scope_was_changed_and_not_otherwise(self):
        tenant = Tenant()
        code, out, err, _ = run(["apply", *ARGS, "--apply"], tenant)
        self.assertIn("after 30 minutes to 2 hours", out)
        self.assertTrue(out.index("Checking again:") < out.index("after 30 minutes to 2 hours"))
        again = run(["apply", *ARGS, "--apply"], tenant)[1]
        self.assertNotIn("30 minutes", again)
        mailbox_only = Tenant().configured()
        del mailbox_only.mailboxes["meternaut-ai"]
        out = run(["apply", *ARGS, "--apply"], mailbox_only)[1]
        self.assertEqual(mailbox_only.writes(), ["New-Mailbox"])
        self.assertNotIn("30 minutes", out)
        self.assertNotIn("30 minutes", run(["apply", *ARGS], Tenant())[1], "a dry run changes nothing, so there is no delay to wait for")

    def test_what_the_tool_does_not_do_is_said_at_the_end_of_every_run_that_reads(self):
        for argv, tenant in ((["check", *ARGS], Tenant()), (["check", *ARGS], Tenant().configured()), (["apply", *ARGS], Tenant()), (["apply", *ARGS, "--apply"], Tenant())):
            out = run(argv, tenant)[1]
            self.assertTrue(out.splitlines()[-1].startswith("Not covered by this tool: the mail-flow rule"), out)
        stray = Tenant().configured()
        stray.assignments.append(stray.assignment("Application Mail.Read", None))
        self.assertIn("Not covered by this tool", run(["apply", *ARGS], stray)[1])

    def test_nothing_that_is_not_in_order_and_cannot_be_made_passes_for_done(self):
        tenant = Tenant().configured()
        tenant.users[ADDRESS] = True
        code, out, err, _ = run(["apply", *ARGS, "--apply"], tenant)
        self.assertEqual((code, tenant.writes()), (1, []))
        self.assertIn("Nothing to create or change. Items that are not in order need more than this tool does", out)


class WhatIsSent(unittest.TestCase):
    def everything(self):
        """Runs that between them use every cmdlet of the tool."""
        runs = []
        empty = Tenant()
        runs.append((run(["apply", *ARGS, "--other-mailbox", OTHER, "--apply"], empty), empty))
        wrong = Tenant().configured()
        wrong.scopes[SCOPE]["RecipientFilter"] = "PrimarySmtpAddress -eq 'wrong@contoso.example'"
        runs.append((run(["apply", *ARGS, "--apply"], wrong), wrong))
        return runs

    def test_the_tool_sends_exactly_the_cmdlets_of_its_list_and_no_other(self):
        sent = set()
        for _, tenant in self.everything():
            sent |= {c for c, _ in tenant.cmdlets}
            self.assertEqual(tenant.violations, [])
        self.assertEqual(sent, ALL_CMDLETS)
        self.assertEqual(set(xs.CMDLETS), ALL_CMDLETS)
        self.assertEqual({c for c in sent if c.startswith(("Remove", "Disable", "Enable", "Add"))}, set())

    def test_another_cmdlet_is_refused_before_a_request_is_made(self):
        tenant = Tenant()
        exchange = xs.Exchange(TENANT, DOMAIN, xs.Tokens(FakeAz(), TENANT, xs.Hider()), tenant)
        for cmdlet in ("Remove-Mailbox", "Set-Mailbox", "Remove-ManagementRoleAssignment", "Get-Mailbox ", "get-mailbox", "Get-Mailbox; Remove-Mailbox", "Invoke-Command",
                       "Add-MailboxPermission", "Get-User", ""):
            with self.subTest(cmdlet=cmdlet):
                with self.assertRaises(xs.Problem):
                    exchange.call(cmdlet, {})
        self.assertEqual(tenant.requests, [])

    def test_every_request_is_the_post_to_the_admin_api_with_the_headers_and_a_fresh_request_id(self):
        tenant = Tenant()
        run(["apply", *ARGS, "--other-mailbox", OTHER, "--apply"], tenant)
        posts = [r for r in tenant.requests if r[1] == EXCHANGE_URL]
        self.assertGreater(len(posts), 10)
        self.assertEqual(tenant.violations, [])
        ids = [headers["client-request-id"] for _, _, headers, _ in posts]
        self.assertEqual(len(set(ids)), len(ids), "a fresh id for every request")
        for method, url, headers, body in posts:
            self.assertEqual(method, "POST")
            document = json.loads(body)
            self.assertEqual(list(document), ["CmdletInput"])
            self.assertEqual(headers["X-CmdletName"], document["CmdletInput"]["CmdletName"])
            self.assertEqual(headers["X-AnchorMailbox"], ANCHOR)
        graph = [r for r in tenant.requests if r[1] != EXCHANGE_URL]
        self.assertTrue(graph)
        for method, url, headers, body in graph:
            self.assertEqual((method, body), ("GET", None))
            self.assertRegex(url, r"^https://graph\.microsoft\.com/v1\.0/(users/[^/?]+\?\$select=accountEnabled|servicePrincipals/[0-9a-f-]{36}/appRoleAssignments)$")

    def test_a_retry_gets_a_fresh_request_id(self):
        tenant = Tenant().configured()
        tenant.failures["Get-Mailbox"] = [reply(503, {"error": {"code": "Busy", "message": "x"}})]
        run(["check", *ARGS], tenant)
        first = [h["client-request-id"] for m, u, h, b in tenant.requests if h.get("X-CmdletName") == "Get-Mailbox"]
        self.assertEqual(len(first), 2)
        self.assertNotEqual(first[0], first[1])

    def test_the_azure_cli_is_asked_once_for_each_resource_and_only_for_a_token(self):
        az = FakeAz()
        run(["apply", *ARGS, "--apply"], Tenant(), az=az)
        self.assertEqual(az.calls, [["account", "get-access-token", "--resource", "https://outlook.office365.com", "--tenant", TENANT, "--query", "accessToken", "-o", "tsv"],
                                    ["account", "get-access-token", "--resource", "https://graph.microsoft.com", "--tenant", TENANT, "--query", "accessToken", "-o", "tsv"]])

    def test_a_token_that_cannot_be_had_is_an_error_without_a_call(self):
        tenant, az = Tenant(), FakeAz(fail=True)
        code, out, err, _ = run(["check", *ARGS], tenant, az=az)
        self.assertEqual(code, 1)
        self.assertIn("the Azure CLI gave no token for https://outlook.office365.com: ERROR: Please run 'az login'", err)
        self.assertEqual(tenant.requests, [])


class NothingSecretIsShown(unittest.TestCase):
    def runs(self):
        scenes = []
        for argv in (["check", *ARGS], ["check", *ARGS, "--other-mailbox", OTHER], ["apply", *ARGS], ["apply", *ARGS, "--apply"]):
            scenes.append((argv, Tenant()))
            scenes.append((argv, Tenant().configured()))
        broken = Tenant().configured()
        broken.echo_tokens = True
        broken.failures["Get-ServicePrincipal"] = [reply(400, {"error": {"code": "Weird", "message": f"the token {TOKENS['https://outlook.office365.com']} is bad"}})]
        scenes.append((["check", *ARGS], broken))
        graph = Tenant().configured()
        graph.echo_tokens = True
        graph.graph_failures["users"] = (403, {})
        graph.graph_failures["roles"] = (403, {})
        scenes.append((["check", *ARGS], graph))
        echoing = Tenant()
        echoing.echo_tokens = True
        scenes.append((["check", *ARGS], echoing))
        return scenes

    def test_no_token_is_in_anything_that_is_printed_or_in_an_error(self):
        for argv, tenant in self.runs():
            code, out, err, _ = run(argv, tenant)
            for token in TOKENS.values():
                self.assertNotIn(token, out)
                self.assertNotIn(token, err)
            self.assertNotIn("Bearer ", out + err)

    def test_a_token_that_an_error_text_repeats_is_hidden_and_the_rest_of_the_text_stays(self):
        tenant = Tenant().configured()
        tenant.failures["Get-ServicePrincipal"] = [reply(400, {"error": {"code": "Weird", "message": f"the token {TOKENS['https://outlook.office365.com']} is bad"}})]
        code, out, err, _ = run(["check", *ARGS], tenant)
        self.assertEqual(code, 1)
        self.assertEqual(err.strip(), "error: Get-ServicePrincipal failed: 400 Weird: the token [token hidden] is bad")
        graph = Tenant().configured()
        graph.echo_tokens = True
        graph.graph_failures["users"] = (403, {})
        code, out, err, _ = run(["check", *ARGS], graph)
        self.assertIn("denied for [token hidden] and [token hidden]", out)

    def test_the_hider_hides_what_was_handed_out_and_what_looks_like_a_token(self):
        hide = xs.Hider()
        hide.add("handed-out-secret-value")
        hide.add("short")
        jwt = TOKENS["https://outlook.office365.com"]
        self.assertEqual(hide("a handed-out-secret-value b short c"), "a [token hidden] b short c")
        self.assertEqual(hide("Bearer handed-out-secret-value"), "[token hidden]")
        for text, shown in (("Bearer abcdefghij123456", "[token hidden]"), ("bearer   ABCDEFGHIJ.klmno-pq", "[token hidden]"), (jwt, "[token hidden]"),
                            (f"x {jwt} y", "x [token hidden] y"), (f"Authorization: Bearer {jwt}", "Authorization: [token hidden]")):
            self.assertEqual(hide(text), shown)
        self.assertEqual(hide("an ordinary sentence"), "an ordinary sentence")

    def test_the_tokens_are_not_kept_anywhere_but_in_memory(self):
        source = (ROOT / "tools" / "exchange-setup.py").read_text(encoding="utf-8")
        for pattern in (r"\bopen\(", r"write_text", r"write_bytes", r"tempfile", r"os\.environ\[", r"\bprint\(.*token", r"\.dump\("):
            self.assertIsNone(re.search(pattern, source), pattern)


class TheTool(unittest.TestCase):
    source = (ROOT / "tools" / "exchange-setup.py").read_text(encoding="utf-8")

    def test_it_imports_only_the_standard_library(self):
        import ast
        standard = set(sys.stdlib_module_names)
        for node in ast.walk(ast.parse(self.source)):
            names = [a.name for a in node.names] if isinstance(node, ast.Import) else [node.module or ""] if isinstance(node, ast.ImportFrom) else []
            for name in names:
                self.assertIn(name.split(".")[0], standard)

    def test_the_two_hosts_and_the_role_and_the_scope_are_the_ones_of_the_documents(self):
        self.assertEqual((xs.EXCHANGE, xs.GRAPH, xs.ROLE, xs.SCOPE), ("https://outlook.office365.com", "https://graph.microsoft.com", ROLE, SCOPE))
        self.assertTrue(xs.DEFAULT_DISPLAY.endswith("(AI)"))

    def test_it_says_in_its_text_how_it_is_run_and_that_it_never_runs_in_a_pipeline(self):
        doc = xs.__doc__
        for words in ("python tools/exchange-setup.py check", "python tools/exchange-setup.py apply", "--apply", "never runs in a pipeline", "removes nothing", "Application Mail.Send"):
            self.assertIn(words, doc)


if __name__ == "__main__":
    unittest.main()
