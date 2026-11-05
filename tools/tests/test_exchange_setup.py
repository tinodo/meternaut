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
WRITES = {"New-Mailbox", "New-ServicePrincipal", "New-ManagementScope", "Set-ManagementScope", "New-ManagementRoleAssignment", "Enable-OrganizationCustomization"}
ALL_CMDLETS = {"Get-Mailbox", "New-Mailbox", "Get-ServicePrincipal", "New-ServicePrincipal", "Get-ManagementScope", "New-ManagementScope", "Set-ManagementScope",
               "Get-ManagementRoleAssignment", "New-ManagementRoleAssignment", "Test-ServicePrincipalAuthorization", "Enable-OrganizationCustomization"}
ENABLE = "Enable-OrganizationCustomization"
# What Exchange gives for a cmdlet that it will not run before Enable-OrganizationCustomization: the message is only "Error executing cmdlet", the rest is in the details
DEHYDRATED_WORDS = ("|Microsoft.Exchange.Configuration.Tasks.InvalidOperationInDehydratedContextException|The command you tried to run isn't currently allowed in your "
                    "organization. To run this command, you first need to run the command: Enable-OrganizationCustomization.")
ONE_TIME_STEP = "Exchange asks for a one-time step per organization: Enable-OrganizationCustomization."
# The roles that Exchange shows, as rows of its default role assignment policy, for any recipient-like object (a service principal pointer included): the real answer
DEFAULT_POLICY = (("MyBaseOptions", "Self"), ("My Custom Apps", "Self"), ("My Marketplace Apps", "Self"), ("My ReadWriteMailbox Apps", "Self"), ("MyContactInformation", "Self"),
                  ("MyMailSubscriptions", "Self"), ("MyProfileInformation", "Self"), ("MyRetentionPolicies", "Self"), ("MyTextMessaging", "Self"), ("MyVoiceMail", "Self"),
                  ("MyDistributionGroupMembership", "MyGAL"), ("MyDistributionGroups", "MyDistributionGroups"))


class Fail(Exception):
    def __init__(self, status, code, message):
        super().__init__(message)
        self.status, self.code, self.message = status, code, message


def reply(status, document, headers=None):
    return status, headers or {}, json.dumps(document).encode("utf-8")


def policy_row(role, write_scope):
    """A row of Exchange's default role assignment policy, in the shape of a real answer of Get-ManagementRoleAssignment."""
    return {"Name": f"{role}-Default Role Assignment Policy", "Role": role, "RoleAssigneeName": "Default Role Assignment Policy", "RoleAssigneeType": "RoleAssignmentPolicy",
            "RoleAssignmentDelegationType": "Regular", "CustomResourceScope": None, "RecipientWriteScope": write_scope, "AssignmentMethod": "RoleAssignmentPolicy", "IsValid": True}


def group_row(role, scope, group="Organization Management", kind="RoleGroup"):
    """A row that the identity holds through a group that it belongs to."""
    return {"Name": f"{role}-{group}", "Role": role, "RoleAssigneeName": group, "RoleAssigneeType": kind, "AssignmentMethod": kind, "CustomResourceScope": scope}


def dehydrated(where="details", extra=""):
    """Exchange's refusal of a cmdlet until the organization is customized, with its words in the details (as Exchange gives them), in the message or in the code."""
    if where == "message":
        error = {"code": "BadRequest", "message": "Error executing cmdlet " + DEHYDRATED_WORDS + extra}
    elif where == "code":
        error = {"code": "Ex6F9304|InvalidOperationInDehydratedContextException", "message": "Error executing cmdlet" + extra}
    else:
        error = {"code": "BadRequest", "message": "Error executing cmdlet", "details": [{"code": "Context", "message": DEHYDRATED_WORDS + extra, "target": ""}]}
    return reply(400, {"error": error})


def dehydrated_tenant(*cmdlets, lag=0):
    """An organization that refuses these cmdlets until Enable-OrganizationCustomization was sent, and then for `lag` more tries."""
    tenant = Tenant()
    tenant.needs_customization = set(cmdlets or ("New-ManagementScope",))
    tenant.customization_lag = lag
    return tenant


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
        self.needs_customization: set[str] = set()
        self.customization_requested = False
        self.customization_lag = 0
        self.enable_error: tuple | None = None
        self.indirect_assignments = [policy_row(role, write_scope) for role, write_scope in DEFAULT_POLICY]

    # -- a tenant that is set up ---------------------------------------------------------------------------------------------------------------------
    def configured(self) -> "Tenant":
        self.mailboxes["meternaut-ai"] = {"Alias": "meternaut-ai", "PrimarySmtpAddress": ADDRESS, "DisplayName": "Meternaut (AI)", "RecipientTypeDetails": "SharedMailbox"}
        self.pointers[PRINCIPAL] = {"ObjectId": PRINCIPAL, "AppId": CLIENT, "DisplayName": "meternaut-cases"}
        self.scopes[SCOPE] = {"Name": SCOPE, "ScopeRestrictionType": "RecipientScope", "RecipientFilter": FILTER}
        self.assignments.append(self.assignment(ROLE, SCOPE))
        self.users[ADDRESS] = False
        return self

    def assignment(self, role, scope, assignee=PRINCIPAL, name=None, kind="ServicePrincipal", method="Direct"):
        return {"Name": name or f"{role}-{len(self.assignments) + 1}", "Role": role, "RoleAssigneeName": assignee, "RoleAssigneeType": kind, "AssignmentMethod": method,
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
        if self.refuses(cmdlet):
            return dehydrated(extra=" " + TOKENS["https://outlook.office365.com"] if self.echo_tokens else "")
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
        if p["RoleAssignee"].lower() in (k.lower() for k in self.pointers):
            # what the identity gets through the default policy and through groups is listed for it as soon as it has a pointer
            found += [dict(r) for r in self.indirect_assignments if p.get("Role", r["Role"]).lower() == r["Role"].lower()]
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

    def refuses(self, cmdlet):
        """Whether the organization still refuses this cmdlet: until Enable-OrganizationCustomization was asked for, and for customization_lag more tries after that."""
        if cmdlet not in self.needs_customization:
            return False
        if not self.customization_requested:
            return True
        if self.customization_lag > 0:
            self.customization_lag -= 1
            return True
        return False

    def cmd_Enable_OrganizationCustomization(self, p):
        assert p == {}, "Enable-OrganizationCustomization takes no parameters"
        if self.enable_error:
            raise Fail(*self.enable_error)
        if self.customization_requested:
            raise Fail(400, "OrganizationAlreadyCustomized", "This operation is not required. Organization is already enabled for customization.")
        self.customization_requested = True
        return []

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

    def test_the_real_answer_of_exchange_for_an_object_that_is_not_there_has_its_words_in_the_details(self):
        real = {"error": {"code": "NotFound", "message": "Error executing cmdlet",
                          "details": [{"code": "Context", "message": "Ex6F9304|Microsoft.Exchange.Configuration.Tasks.ManagementObjectNotFoundException|The operation couldn't be "
                                                                     "performed because object 'meternaut-ai' couldn't be found on 'SJ0PR03A12DC002.NAMPR03A012.PROD.OUTLOOK.COM'.",
                                       "target": ""}],
                          "innererror": {"message": "Error executing cmdlet", "type": "Microsoft.Exchange.Admin.OData.Core.ODataServiceException"}}}
        code, message = xs.error_of(json.dumps(real).encode("utf-8"))
        self.assertEqual(code, "NotFound")
        self.assertIn("couldn't be found", message)
        self.assertTrue(message.startswith("Error executing cmdlet"))
        for cmdlet in ("Get-Mailbox", "Get-ServicePrincipal", "Get-ManagementScope", "Get-ManagementRoleAssignment"):
            with self.subTest(cmdlet=cmdlet):
                tenant = Tenant()
                tenant.failures[cmdlet] = [reply(404, real)]
                code, out, err, _ = run(["check", *ARGS], tenant)
                self.assertNotIn("failed", err, err)

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


class TheDefaultPolicyRows(unittest.TestCase):
    """Exchange lists the rows of its default role assignment policy (MyBaseOptions and the like) for a service principal that has a pointer. They are the policy's."""

    def test_the_fake_lists_the_twelve_rows_of_the_policy_in_the_shape_of_the_real_answer_once_the_pointer_exists(self):
        tenant = Tenant().configured()
        rows = tenant.cmd_Get_ManagementRoleAssignment({"RoleAssignee": PRINCIPAL})
        policy = [r for r in rows if r["RoleAssigneeType"] == "RoleAssignmentPolicy"]
        self.assertEqual((len(policy), len(rows)), (12, 13), "twelve rows of the policy, and the assignment of the identity")
        self.assertEqual(policy[0], {"Name": "MyBaseOptions-Default Role Assignment Policy", "Role": "MyBaseOptions", "RoleAssigneeName": "Default Role Assignment Policy",
                                     "RoleAssigneeType": "RoleAssignmentPolicy", "RoleAssignmentDelegationType": "Regular", "CustomResourceScope": None,
                                     "RecipientWriteScope": "Self", "AssignmentMethod": "RoleAssignmentPolicy", "IsValid": True})
        self.assertEqual({r["RecipientWriteScope"] for r in policy}, {"Self", "MyGAL", "MyDistributionGroups"})
        self.assertEqual([r["Role"] for r in tenant.cmd_Get_ManagementRoleAssignment({"RoleAssignee": PRINCIPAL, "Role": ROLE})], [ROLE], "a read of one role has none of them")
        tenant.pointers.clear()
        self.assertEqual([r for r in tenant.cmd_Get_ManagementRoleAssignment({"RoleAssignee": PRINCIPAL}) if r["RoleAssigneeType"] == "RoleAssignmentPolicy"], [])

    def test_the_rows_of_the_policy_are_not_the_identitys_and_do_not_fail_the_check(self):
        tenant = Tenant().configured()
        code, out, err, _ = run(["check", *ARGS, "--other-mailbox", OTHER], tenant)
        self.assertEqual((code, err), (0, ""), out)
        self.assertEqual(states(out), {key: "present" for key in ("1", "2", "3", "4", "4b", "5a", "5b", "6", "7")})
        self.assertIn("12 row(s) of Exchange's default role assignment policy (the self-service roles of a mailbox user) are not the identity's and are not counted; "
                      "items 5a and 5b show what the identity can do", out)
        for words in ("MyBaseOptions", "My Custom Apps", "MyDistributionGroups", "Remove-ManagementRoleAssignment", "MUST NOT HOLD"):
            self.assertNotIn(words, out)
        self.assertEqual(tenant.writes(), [])

    def test_a_run_that_finds_the_pointer_and_the_policy_rows_goes_on_to_make_the_scope_and_the_assignment(self):
        tenant = Tenant().configured()
        del tenant.scopes[SCOPE]
        del tenant.assignments[0]
        tenant.needs_customization, tenant.customization_lag = {"New-ManagementScope"}, 1
        code, out, err, sleeps = run(["apply", *ARGS, "--other-mailbox", OTHER, "--apply"], tenant)
        self.assertEqual((code, err), (0, ""), out)
        self.assertNotIn("Nothing was changed.", out)
        self.assertEqual(tenant.writes(), ["New-ManagementScope", "Enable-OrganizationCustomization", "New-ManagementScope", "New-ManagementScope", "New-ManagementRoleAssignment"])
        self.assertEqual(states(out), {key: "present" for key in ("1", "2", "3", "4", "4b", "5a", "5b", "6", "7")})
        self.assertEqual(tenant.violations, [])

    def test_a_row_is_the_policys_when_its_assignee_type_or_its_method_says_so_and_in_no_other_case(self):
        base = {"Name": "X-1", "Role": "MyBaseOptions", "CustomResourceScope": None}
        policy = [{**base, "RoleAssigneeType": "RoleAssignmentPolicy"}, {**base, "AssignmentMethod": "RoleAssignmentPolicy"},
                  {**base, "RoleAssigneeType": "RoleAssignmentPolicy", "AssignmentMethod": "Direct"}, {**base, "RoleAssigneeType": "User", "AssignmentMethod": "RoleAssignmentPolicy"},
                  {**base, "AssignmentMethod": ["RoleAssignmentPolicy"]}, {**base, "roleassigneetype": "roleassignmentpolicy"}, policy_row("MyVoiceMail", "Self")]
        identity = [{**base, "RoleAssigneeType": "ServicePrincipal", "AssignmentMethod": "Direct"}, {**base}, {**base, "RoleAssigneeType": "RoleGroup", "AssignmentMethod": "RoleGroup"},
                    {**base, "RoleAssigneeType": "ServicePrincipal", "AssignmentMethod": ["Direct", "RoleAssignmentPolicy"]},
                    {**base, "RoleAssigneeName": "Default Role Assignment Policy", "RoleAssigneeType": "ServicePrincipal", "AssignmentMethod": "Direct"},
                    {**base, "Name": "MyBaseOptions-Default Role Assignment Policy", "RoleAssigneeType": "User"}, {**base, "AssignmentMethod": []}]
        self.assertEqual(xs.own_assignments(policy), [])
        self.assertEqual(xs.own_assignments(identity), identity)
        self.assertEqual(xs.own_assignments(policy + identity), identity)

    def test_a_row_with_the_marks_of_the_policy_is_ignored_wherever_it_comes_from_and_a_row_without_them_is_not(self):
        marked = Tenant().configured()
        marked.indirect_assignments.append({"Name": "Odd-1", "Role": "Application Calendars.Read", "RoleAssigneeName": "Some policy", "RoleAssigneeType": "RoleAssignmentPolicy",
                                            "AssignmentMethod": "RoleAssignmentPolicy", "CustomResourceScope": None})
        self.assertEqual(run(["check", *ARGS], marked)[0], 0)
        unmarked = Tenant().configured()
        unmarked.indirect_assignments.append({"Name": "Odd-2", "Role": "Application Calendars.Read", "RoleAssigneeName": "Default Role Assignment Policy",
                                              "CustomResourceScope": None})
        code, out, err, _ = run(["check", *ARGS], unmarked)
        self.assertEqual((code, states(out)["4b"]), (1, "FAIL"), "only the marks of Exchange decide, and not a name that looks like the policy's")
        self.assertIn("assignment Odd-2: role Application Calendars.Read", out)

    def test_a_direct_assignment_without_the_scope_is_still_a_stray_and_the_policy_rows_are_not_listed_with_it(self):
        for role in ("Application Calendars.Read", "Application Mail.Read", "Application Mail.Send"):
            with self.subTest(role=role):
                tenant = Tenant().configured()
                tenant.assignments.append(tenant.assignment(role, None, name=f"{role}-everybody"))
                code, out, err, _ = run(["check", *ARGS], tenant)
                self.assertEqual((code, states(out)["4b"]), (1, "FAIL"), out)
                self.assertIn("THE IDENTITY HOLDS EXCHANGE ROLE ASSIGNMENTS THAT IT MUST NOT HOLD", out)
                self.assertIn(f"assignment {role}-everybody: role {role}, no custom resource scope, so it covers every mailbox", out)
                self.assertIn(f"Remove-ManagementRoleAssignment -Identity '{role}-everybody'", out)
                self.assertEqual(out.count("Remove-ManagementRoleAssignment"), 1)
                for words in ("Default Role Assignment Policy", "MyBaseOptions", "row(s) of Exchange's default"):
                    self.assertNotIn(words, out)

    def test_a_direct_mail_send_without_our_scope_is_still_a_stray_and_apply_changes_nothing(self):
        for scope in (None, "Another scope", "Meternaut sender mailbox 2"):
            with self.subTest(scope=scope):
                tenant = Tenant().configured()
                tenant.assignments.append(tenant.assignment(ROLE, scope, name="Mail.Send-other"))
                code, out, err, _ = run(["apply", *ARGS, "--apply"], tenant)
                self.assertEqual(code, 1, out)
                self.assertEqual((states(out)["4"], states(out)["4b"]), ("present", "FAIL"))
                self.assertIn("Remove-ManagementRoleAssignment -Identity 'Mail.Send-other'", out)
                self.assertIn("Nothing was changed.", out)
                self.assertEqual(tenant.writes(), [])

    def test_the_hint_to_remove_an_assignment_is_only_for_one_that_the_identity_holds_directly(self):
        self.assertTrue(xs.is_direct({"RoleAssigneeType": "ServicePrincipal"}))
        self.assertTrue(xs.is_direct({"AssignmentMethod": "Direct"}))
        self.assertTrue(xs.is_direct({"AssignmentMethod": ["Direct"]}))
        for row in ({}, {"RoleAssigneeType": "RoleGroup", "AssignmentMethod": "RoleGroup"}, {"RoleAssigneeType": "User"}):
            self.assertFalse(xs.is_direct(row), row)
        self.assertEqual(xs.held_through({"RoleAssigneeType": "RoleGroup", "RoleAssigneeName": "Org Mgmt"}), "RoleGroup 'Org Mgmt'")
        self.assertEqual(xs.held_through({}), "a way that Exchange does not name")
        for kind in ("RoleGroup", "SecurityGroup"):
            with self.subTest(kind=kind):
                tenant = Tenant().configured()
                tenant.indirect_assignments.append(group_row("Application Mail.Send", None, "Mail Senders", kind))
                code, out, err, _ = run(["apply", *ARGS, "--apply"], tenant)
                self.assertEqual((code, states(out)["4b"], tenant.writes()), (1, "FAIL", []), out)
                self.assertIn(f"It comes through {kind} 'Mail Senders', not directly. Do not remove the assignment (others hold it too): take the identity out of that, "
                              "or ask who owns it.", out)
                self.assertNotIn("Remove-ManagementRoleAssignment", out)
                self.assertIn("Nothing was changed.", out)

    def test_a_row_of_the_policy_is_never_taken_for_the_assignment_of_the_identity(self):
        tenant = Tenant().configured()
        tenant.assignments.clear()
        tenant.indirect_assignments.append({**policy_row(ROLE, "Self"), "CustomResourceScope": SCOPE})
        code, out, err, _ = run(["check", *ARGS], tenant)
        self.assertEqual((code, states(out)["4"], states(out)["4b"]), (1, "MISSING", "present"), out)

    def test_the_note_about_the_policy_rows_is_only_there_when_there_were_some(self):
        tenant = Tenant().configured()
        tenant.indirect_assignments = []
        code, out, err, _ = run(["check", *ARGS], tenant)
        self.assertEqual((code, states(out)["4b"]), (0, "present"))
        self.assertNotIn("default role assignment policy", out)


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


class TheOneTimeStep(unittest.TestCase):
    """A new organization refuses to make a scope until Enable-OrganizationCustomization has been run, and then takes a while to apply it."""

    def sent(self, tenant):
        return [c for c, _ in tenant.cmdlets if c in WRITES]

    def test_the_refusal_is_explained_the_step_is_sent_once_and_the_refused_cmdlet_is_tried_again_after_each_pause(self):
        tenant = dehydrated_tenant(lag=3)
        code, out, err, sleeps = run(["apply", *ARGS, "--other-mailbox", OTHER, "--apply"], tenant)
        self.assertEqual((code, err), (0, ""), out)
        self.assertEqual(self.sent(tenant), ["New-Mailbox", "New-ServicePrincipal", "New-ManagementScope", ENABLE, *["New-ManagementScope"] * 4, "New-ManagementRoleAssignment"])
        self.assertEqual(sleeps, [20.0] * 4, "one pause before every new try, and no other")
        self.assertEqual(tenant.violations, [])
        self.assertIn("New-ManagementScope was refused (400 BadRequest).", out)
        self.assertIn(f"{ONE_TIME_STEP} It only un-consolidates stored objects so that custom roles and scopes can be made; it changes no mail flow and no policy; "
                      "Exchange says it is run once and cannot be run again.", out)
        self.assertIn(f"sent {ENABLE}", out)
        self.assertIn("New-ManagementScope is tried again, 12 times at most, 20 seconds apart.", out)
        self.assertEqual(out.count("is still refused"), 3)
        self.assertIn("sent New-ManagementScope (try 4 of 12)", out)
        order = [out.index(words) for words in ("was refused", f"sent {ENABLE}", "sent New-ManagementScope (try 4 of 12)", "sent New-ManagementRoleAssignment", "Checking again:")]
        self.assertEqual(order, sorted(order), "the words come in the order of what happened, and the state is read again after the last cmdlet")
        self.assertEqual(states(out), {key: "present" for key in ("1", "2", "3", "4", "4b", "5a", "5b", "6", "7")})
        enable = [json.loads(body)["CmdletInput"] for _, _, headers, body in tenant.requests if headers.get("X-CmdletName") == ENABLE]
        self.assertEqual(enable, [{"CmdletName": ENABLE, "Parameters": {}}])

    def test_the_refused_cmdlet_is_tried_at_most_12_times_and_a_success_on_the_last_try_counts(self):
        for lag in (0, 1, 11):
            with self.subTest(lag=lag):
                tenant = dehydrated_tenant(lag=lag)
                code, out, err, sleeps = run(["apply", *ARGS, "--apply"], tenant)
                self.assertEqual((code, err), (0, ""), out)
                self.assertEqual(sleeps, [20.0] * (lag + 1))
                self.assertEqual(self.sent(tenant).count("New-ManagementScope"), lag + 2)
                self.assertEqual(self.sent(tenant).count(ENABLE), 1)
        tenant = dehydrated_tenant(lag=12)
        code, out, err, sleeps = run(["apply", *ARGS, "--apply"], tenant)
        self.assertEqual((code, sleeps), (1, [20.0] * 12), "the 13th try does not exist")

    def test_a_refusal_that_never_ends_stops_after_the_last_try_with_a_clear_message_and_sends_nothing_after_it(self):
        tenant = dehydrated_tenant(lag=10 ** 9)
        code, out, err, sleeps = run(["apply", *ARGS, "--apply"], tenant)
        self.assertEqual(code, 1)
        self.assertEqual(sleeps, [20.0] * 12)
        self.assertEqual(self.sent(tenant), ["New-Mailbox", "New-ServicePrincipal", "New-ManagementScope", ENABLE, *["New-ManagementScope"] * 12])
        self.assertEqual(err.strip(), "error: New-ManagementScope is still refused after 12 tries over 240 seconds: Exchange has not yet applied Enable-OrganizationCustomization. "
                                      "It can take longer. Wait, then run this tool again: it only creates what is missing.")
        self.assertEqual(out.count("is still refused"), 12)

    def test_an_answer_that_the_step_was_run_before_is_fine_and_the_refused_cmdlet_is_still_tried_again(self):
        for text in ("This operation is not required. Organization is already enabled for customization.", "The command has already been run for this organization.",
                     "Enable-OrganizationCustomization isn't required here.", "Enable-OrganizationCustomization isn\u2019t required here.", "Not required."):
            with self.subTest(text=text):
                tenant = dehydrated_tenant(lag=2)
                tenant.customization_requested = True  # somebody ran it a moment ago and Exchange is still applying it
                tenant.enable_error = (400, "OrganizationCustomization", text)
                code, out, err, sleeps = run(["apply", *ARGS, "--apply"], tenant)
                self.assertEqual((code, err), (0, ""), out)
                self.assertEqual(self.sent(tenant), ["New-Mailbox", "New-ServicePrincipal", "New-ManagementScope", ENABLE, "New-ManagementScope", "New-ManagementScope",
                                                     "New-ManagementRoleAssignment"])
                self.assertEqual(sleeps, [20.0, 20.0])
                self.assertIn(f"Exchange says that {ENABLE} was run before (400 OrganizationCustomization: {text}). That is fine", out)
                self.assertNotIn(f"sent {ENABLE}", out)

    def test_the_plain_answer_of_a_tenant_that_was_customized_before_is_fine(self):
        tenant = Tenant()
        tenant.customization_requested = True
        tenant.failures["New-ManagementScope"] = [dehydrated()]
        code, out, err, sleeps = run(["apply", *ARGS, "--apply"], tenant)
        self.assertEqual((code, err, sleeps), (0, "", [20.0]), out)
        self.assertIn("(400 OrganizationAlreadyCustomized: This operation is not required. Organization is already enabled for customization.)", out)

    def test_any_other_error_of_the_step_stops_the_run_at_once(self):
        for status, code_, text in ((403, "Forbidden", "You are not allowed to run this cmdlet."), (400, "Other", "The organization cannot be customized now."), (500, "", "")):
            with self.subTest(status=status):
                tenant = dehydrated_tenant(lag=1)
                tenant.enable_error = (status, code_, text)
                code, out, err, sleeps = run(["apply", *ARGS, "--apply"], tenant)
                self.assertEqual(code, 1)
                self.assertIn(f"Enable-OrganizationCustomization failed: {status}", err)
                self.assertEqual(sleeps, [])
                self.assertEqual(self.sent(tenant), ["New-Mailbox", "New-ServicePrincipal", "New-ManagementScope", ENABLE])
                self.assertNotIn("That is fine", out)

    def test_a_different_error_on_a_new_try_stops_the_run_at_once(self):
        tenant = dehydrated_tenant(lag=0)
        tenant.failures["New-ManagementScope"] = [dehydrated(), reply(400, {"error": {"code": "Other", "message": "The scope is not valid."}})]
        code, out, err, sleeps = run(["apply", *ARGS, "--apply"], tenant)
        self.assertEqual(code, 1)
        self.assertEqual(err.strip(), "error: New-ManagementScope failed: 400 Other: The scope is not valid.")
        self.assertEqual(sleeps, [20.0])
        self.assertEqual(self.sent(tenant), ["New-Mailbox", "New-ServicePrincipal", "New-ManagementScope", ENABLE, "New-ManagementScope"])

    def test_the_step_is_sent_once_per_run_even_when_a_later_cmdlet_is_refused_too(self):
        tenant = dehydrated_tenant(lag=1)
        tenant.failures["New-ManagementRoleAssignment"] = [dehydrated()]
        code, out, err, sleeps = run(["apply", *ARGS, "--apply"], tenant)
        self.assertEqual((code, err), (0, ""), out)
        self.assertEqual(self.sent(tenant).count(ENABLE), 1)
        self.assertEqual(self.sent(tenant).count("New-ManagementRoleAssignment"), 2)
        self.assertEqual(sleeps, [20.0] * 3)
        self.assertEqual(out.count("Exchange asks for a one-time step"), 1)
        self.assertIn("New-ManagementRoleAssignment was refused (400 BadRequest).", out)

    def test_any_cmdlet_that_changes_something_can_be_the_one_that_is_refused(self):
        for cmdlet in ("New-Mailbox", "New-ServicePrincipal", "New-ManagementScope", "New-ManagementRoleAssignment", "Set-ManagementScope"):
            with self.subTest(cmdlet=cmdlet):
                tenant = dehydrated_tenant(cmdlet, lag=1)
                if cmdlet == "Set-ManagementScope":
                    tenant.configured().scopes[SCOPE]["RecipientFilter"] = "PrimarySmtpAddress -eq 'wrong@contoso.example'"
                code, out, err, sleeps = run(["apply", *ARGS, "--apply"], tenant)
                self.assertEqual((code, err), (0, ""), out)
                self.assertEqual(self.sent(tenant).count(ENABLE), 1)
                self.assertEqual(self.sent(tenant).count(cmdlet), 3)
                self.assertEqual(sleeps, [20.0, 20.0])
                self.assertIn(f"{cmdlet} was refused", out)
                self.assertEqual(tenant.violations, [])

    def test_only_a_cmdlet_that_changes_something_can_ask_for_the_step(self):
        for cmdlet in ("Get-Mailbox", "Get-ServicePrincipal", "Get-ManagementScope", "Get-ManagementRoleAssignment"):
            with self.subTest(cmdlet=cmdlet):
                tenant = Tenant().configured()
                tenant.failures[cmdlet] = [dehydrated()]
                code, out, err, sleeps = run(["apply", *ARGS, "--apply"], tenant)
                self.assertEqual((code, tenant.writes(), sleeps), (1, [], []))
                self.assertIn(f"{cmdlet} failed: 400 BadRequest", err)

    def test_the_words_of_the_refusal_are_found_in_the_details_the_message_and_the_code(self):
        for where in ("details", "message", "code"):
            with self.subTest(where=where):
                tenant = Tenant()
                tenant.failures["New-ManagementScope"] = [dehydrated(where)]
                code, out, err, sleeps = run(["apply", *ARGS, "--apply"], tenant)
                self.assertEqual((code, err, sleeps), (0, "", [20.0]), out)
                self.assertEqual(self.sent(tenant).count(ENABLE), 1)

    def test_either_of_the_two_words_is_enough_and_the_case_does_not_matter(self):
        for words in ("you first need to run the command: Enable-OrganizationCustomization.", "Microsoft.Exchange.Configuration.Tasks.InvalidOperationInDehydratedContextException",
                      "ENABLE-ORGANIZATIONCUSTOMIZATION", "invalidoperationindehydratedcontext"):
            with self.subTest(words=words):
                tenant = Tenant()
                tenant.failures["New-ManagementScope"] = [reply(400, {"error": {"code": "X", "message": words}})]
                code, out, err, sleeps = run(["apply", *ARGS, "--apply"], tenant)
                self.assertEqual((code, err, sleeps), (0, "", [20.0]), out)

    def test_the_words_are_looked_for_in_the_whole_message_and_not_only_in_the_part_that_is_shown(self):
        long = reply(400, {"error": {"code": "BadRequest", "message": "x" * 400 + " You first need to run the command: Enable-OrganizationCustomization."}})
        tenant = Tenant()
        tenant.failures["New-ManagementScope"] = [long]
        code, out, err, sleeps = run(["apply", *ARGS, "--apply"], tenant)
        self.assertEqual((code, err, sleeps), (0, "", [20.0]), out)
        shown = Tenant()
        shown.failures["Get-Mailbox"] = [long]
        exchange = xs.Exchange(TENANT, DOMAIN, xs.Tokens(FakeAz(), TENANT, xs.Hider()), shown)
        with self.assertRaises(xs.Refused) as caught:
            exchange.call("Get-Mailbox", {"Identity": "x"})
        self.assertEqual((caught.exception.cmdlet, caught.exception.status, caught.exception.code), ("Get-Mailbox", 400, "BadRequest"))
        self.assertTrue(caught.exception.message.endswith("Enable-OrganizationCustomization."))
        self.assertLess(len(str(caught.exception)), 400, "the text that is shown has the first 300 characters of the message")

    def test_other_refusals_do_not_ask_for_the_step(self):
        for message in ("The proxy address is already being used.", "The operation couldn't be performed because object 'x' couldn't be found.", "Insufficient permissions.",
                        "Enable-Mailbox failed", "customization"):
            with self.subTest(message=message):
                tenant = Tenant()
                tenant.failures["New-ManagementScope"] = [reply(400, {"error": {"code": "Other", "message": message}})]
                code, out, err, sleeps = run(["apply", *ARGS, "--apply"], tenant)
                self.assertEqual((code, sleeps), (1, []))
                self.assertIn("New-ManagementScope failed: 400 Other", err)
                self.assertNotIn(ENABLE, self.sent(tenant))

    def test_a_dry_run_says_that_the_step_may_be_needed_and_sends_nothing(self):
        tenant = dehydrated_tenant(lag=3)
        code, out, err, sleeps = run(["apply", *ARGS], tenant)
        self.assertEqual((code, err, sleeps), (0, "", []))
        self.assertEqual(tenant.writes(), [])
        self.assertNotIn(ENABLE, [c for c, _ in tenant.cmdlets])
        self.assertIn("Exchange may first ask for Enable-OrganizationCustomization, once per organization.", out)
        self.assertIn("That is the one other cmdlet that this tool can send, and only when Exchange asks for it.", out)
        self.assertLess(out.index("New-ManagementRoleAssignment {"), out.index("Exchange may first ask"))
        self.assertLess(out.index("Exchange may first ask"), out.index("This was a dry run."))
        self.assertNotIn("was refused", out)

    def test_the_step_is_not_sent_unless_exchange_asks_for_it_and_the_heads_up_comes_before_the_first_cmdlet(self):
        tenant = Tenant()
        code, out, err, sleeps = run(["apply", *ARGS, "--apply"], tenant)
        self.assertEqual((code, err, sleeps), (0, "", []), out)
        self.assertEqual(self.sent(tenant), ["New-Mailbox", "New-ServicePrincipal", "New-ManagementScope", "New-ManagementRoleAssignment"])
        self.assertLess(out.index("Exchange may first ask for Enable-OrganizationCustomization"), out.index("sent New-Mailbox"))
        self.assertNotIn(ONE_TIME_STEP, out)

    def test_check_never_sends_the_step_and_a_run_with_nothing_to_do_does_not_mention_it(self):
        tenant = dehydrated_tenant(lag=0)
        code, out, err, sleeps = run(["check", *ARGS], tenant)
        self.assertEqual((code, tenant.writes(), sleeps), (1, [], []))
        self.assertNotIn(ENABLE, out)
        done = Tenant().configured()
        code, out, err, sleeps = run(["apply", *ARGS, "--apply"], done)
        self.assertEqual((code, sleeps), (0, []))
        self.assertIn("Nothing to create or change.", out)
        self.assertNotIn(ENABLE, out)


class WhatIsSent(unittest.TestCase):
    def everything(self):
        """Runs that between them use every cmdlet of the tool."""
        runs = []
        empty = Tenant()
        runs.append((run(["apply", *ARGS, "--other-mailbox", OTHER, "--apply"], empty), empty))
        wrong = Tenant().configured()
        wrong.scopes[SCOPE]["RecipientFilter"] = "PrimarySmtpAddress -eq 'wrong@contoso.example'"
        runs.append((run(["apply", *ARGS, "--apply"], wrong), wrong))
        customizing = dehydrated_tenant(lag=1)
        runs.append((run(["apply", *ARGS, "--apply"], customizing), customizing))
        return runs

    def test_the_tool_sends_exactly_the_cmdlets_of_its_list_and_no_other(self):
        sent = set()
        for _, tenant in self.everything():
            sent |= {c for c, _ in tenant.cmdlets}
            self.assertEqual(tenant.violations, [])
        self.assertEqual(sent, ALL_CMDLETS)
        self.assertEqual(set(xs.CMDLETS), ALL_CMDLETS)
        self.assertEqual({c for c in sent if c.startswith(("Remove", "Disable", "Add"))}, set())
        self.assertEqual({c for c in sent if c.startswith("Enable")}, {ENABLE}, "the one step that Exchange can ask for, and no other that enables something")

    def test_another_cmdlet_is_refused_before_a_request_is_made(self):
        tenant = Tenant()
        exchange = xs.Exchange(TENANT, DOMAIN, xs.Tokens(FakeAz(), TENANT, xs.Hider()), tenant)
        for cmdlet in ("Remove-Mailbox", "Set-Mailbox", "Remove-ManagementRoleAssignment", "Get-Mailbox ", "get-mailbox", "Get-Mailbox; Remove-Mailbox", "Invoke-Command",
                       "Add-MailboxPermission", "Get-User", "", "Enable-OrganizationCustomization ", "enable-organizationcustomization", "Disable-OrganizationCustomization",
                       "Enable-Mailbox", "Get-OrganizationConfig", "Set-OrganizationConfig"):
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
        customizing = dehydrated_tenant(lag=1)
        customizing.echo_tokens = True
        scenes.append((["apply", *ARGS, "--apply"], customizing))
        before = dehydrated_tenant(lag=1)
        before.customization_requested, before.echo_tokens = True, True
        before.enable_error = (400, "X", f"already done, token {TOKENS['https://outlook.office365.com']} seen")
        scenes.append((["apply", *ARGS, "--apply"], before))
        refused = dehydrated_tenant(lag=1)
        refused.echo_tokens = True
        refused.enable_error = (403, "Forbidden", f"no, {TOKENS['https://outlook.office365.com']}")
        scenes.append((["apply", *ARGS, "--apply"], refused))
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

    def test_what_exchange_says_about_the_one_time_step_is_shown_without_the_token(self):
        tenant = dehydrated_tenant(lag=1)
        tenant.customization_requested = True
        tenant.enable_error = (400, "X", f"already done, token {TOKENS['https://outlook.office365.com']} seen")
        code, out, err, _ = run(["apply", *ARGS, "--apply"], tenant)
        self.assertEqual(code, 0, out + err)
        self.assertIn("(400 X: already done, token [token hidden] seen)", out)
        refused = dehydrated_tenant(lag=1)
        refused.enable_error = (403, "Forbidden", f"no, {TOKENS['https://outlook.office365.com']}")
        code, out, err, _ = run(["apply", *ARGS, "--apply"], refused)
        self.assertEqual((code, err.strip()), (1, "error: Enable-OrganizationCustomization failed: 403 Forbidden: no, [token hidden]"))

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
        for words in ("python tools/exchange-setup.py check", "python tools/exchange-setup.py apply", "--apply", "never runs in a pipeline", "removes nothing", "Application Mail.Send",
                      "Enable-OrganizationCustomization", "once per organization", "cannot be run again", "12 times at most, 20 seconds apart", "default role assignment policy"):
            self.assertIn(words, doc)


if __name__ == "__main__":
    unittest.main()
