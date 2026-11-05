"""The whole loop, from a planted disk to its removal, with the approver's own token.

The Watch finds the disk, a plan is made and a letter goes out; the person opens the page and presses Approve; the console sends the person to Microsoft Entra
(a fake that checks the redemption like the real one: the PKCE verifier, the redirect address and the federated assertion); the person comes back; the change is
made with the person's token in Resource Manager (a fake that lets only that token delete); the timer then tells the person what ran. At no point does an
identity of Meternaut delete anything.
"""
import base64
import datetime as dt
import hashlib
import json
import unittest
from urllib.parse import parse_qs, urlencode, urlsplit

from support import ENV, NOW, RG, SUBSCRIPTION, FakeEstate, Ticker, disk_row

from cases import console, loop, loop_config, run
from cases.http import Client
from cases.memory_store import stamp
from cases.models import SwitchRecord
from cases.redact import Redactor
from cases.store import TableStore, table_calls
from cases.web import handle, parse_request

from test_store import FakeTables
from test_web_support import Reply

OID = "aaaaaaaa-1111-4222-8333-444444444444"
GROUP = "rg-meternaut"
SENDER = "meternaut-ai@example.onmicrosoft.com"
DISK = f"{RG}/{GROUP}/providers/Microsoft.Compute/disks/planted-disk-1"
TENANT = "cccccccc-1111-4222-8333-444444444444"
CLIENT = "dddddddd-1111-4222-8333-444444444444"
ASSERTION_CLIENT = "eeeeeeee-1111-4222-8333-444444444444"
READER_CLIENT = ENV["AZURE_CLIENT_ID"]
HOST = "func.example.net"
PERSON_TOKEN = "arm-access-token-of-the-person-0123456789"
APPROVE = "Approve and sign in to Azure"
LOOP_ENV = {
    **ENV,
    "STORE_ACCOUNT_NAME": "stexample",
    "CHANGE_RESOURCE_GROUP": GROUP,
    "CHANGE_SUBSCRIPTION_ID": SUBSCRIPTION,
    "SIGNIN_TENANT_ID": TENANT,
    "SIGNIN_CLIENT_ID": CLIENT,
    "OVERRIDE_USE_MI_FIC_ASSERTION_CLIENTID": ASSERTION_CLIENT,
    "CONSOLE_HOST": HOST,
    "MAIL_SENDER": SENDER,
    "CONSOLE_PEOPLE": json.dumps([{"oid": OID, "name": "Tino", "roles": ["owner", "approver", "ops"], "mail": "tino@example.com"}]),
}


def jwt(claims: dict) -> str:
    def part(data) -> str:
        return base64.urlsafe_b64encode(json.dumps(data).encode()).rstrip(b"=").decode()

    return f"{part({'alg': 'RS256'})}.{part(claims)}.c2lnbmF0dXJl"


class Clock:
    def __init__(self):
        self.now = NOW

    def __call__(self):
        return self.now

    def advance(self, **kwargs):
        self.now += dt.timedelta(**kwargs)


class Mail:
    def __init__(self):
        self.sent = []

    def __call__(self, method, url, headers, data, timeout):
        body = json.loads(data.decode("utf-8"))
        self.sent.append({"url": url, "headers": dict(headers), "message": body["message"]})
        return 202, {}, b""


class Resources:
    """The planted disk in Resource Manager: it exists until it is deleted, and only a token that is on the list may delete it."""

    def __init__(self, may_delete):
        self.exists = True
        self.may = set(may_delete)
        self.calls = []

    def __call__(self, method, url, headers, data, timeout):
        auth = headers.get("Authorization", "")
        self.calls.append((method, urlsplit(url).path, auth))
        if method == "DELETE":
            if auth not in self.may:
                return 403, {}, b'{"error":{"code":"AuthorizationFailed","message":"no right to delete"}}'
            self.exists = False
            return 200, {}, b""
        if not self.exists:
            return 404, {}, b'{"error":{"code":"ResourceNotFound","message":"gone"}}'
        return 200, {}, json.dumps({"id": DISK, "name": "planted-disk-1", "tags": {"meternaut-planted": "demo"}, "properties": {"diskState": "Unattached"}}).encode()


class Entra:
    """Microsoft Entra, as far as the console uses it. It remembers what the sign-in asked for and checks the redemption of the code like the real one does."""

    def __init__(self):
        self.pending = {}
        self.redemptions = []
        self.counter = 0

    def sign_in(self, location, oid=OID):
        parts = urlsplit(location)
        assert (parts.scheme, parts.netloc, parts.path) == ("https", "login.microsoftonline.com", f"/{TENANT}/oauth2/v2.0/authorize"), location
        query = {k: v[0] for k, v in parse_qs(parts.query).items()}
        assert query["response_type"] == "code" and query["code_challenge_method"] == "S256" and "offline_access" not in query["scope"], query
        self.counter += 1
        code = f"authorization-code-{self.counter:04d}-" + "x" * 20
        self.pending[code] = {**query, "oid": oid}
        return code, query["state"]

    def __call__(self, method, url, headers, data, timeout):
        assert (method, url) == ("POST", f"https://login.microsoftonline.com/{TENANT}/oauth2/v2.0/token"), (method, url)
        form = {k: v[0] for k, v in parse_qs(data.decode()).items()}
        self.redemptions.append(form)
        issued = self.pending.pop(form.get("code", ""), None)
        if issued is None:
            return 400, {}, json.dumps({"error": "invalid_grant", "error_description": "AADSTS70008: the code was used already or has expired"}).encode()
        challenge = base64.urlsafe_b64encode(hashlib.sha256(form["code_verifier"].encode()).digest()).rstrip(b"=").decode()
        problems = []
        if challenge != issued["code_challenge"]:
            problems.append("the PKCE verifier does not match")
        if form["redirect_uri"] != issued["redirect_uri"] or form["redirect_uri"] != f"https://{HOST}/arm/return":
            problems.append("the redirect address does not match")
        if form["client_id"] != CLIENT or form["scope"] != issued["scope"]:
            problems.append("the client or the scope does not match")
        if form.get("client_assertion") != f"assertion-of-{ASSERTION_CLIENT}" or form.get("client_assertion_type") != "urn:ietf:params:oauth:client-assertion-type:jwt-bearer":
            problems.append("the client assertion is not the federated assertion")
        if "client_secret" in form:
            problems.append("a secret was sent")
        if problems:
            return 400, {}, json.dumps({"error": "invalid_client", "error_description": "AADSTS700027: " + "; ".join(problems)}).encode()
        claims = {"tid": TENANT, "aud": CLIENT, "nonce": issued["nonce"], "sub": "pairwise-subject-of-the-person", "iss": f"https://login.microsoftonline.com/{TENANT}/v2.0",
                  "exp": int(NOW.timestamp()) + 3600}
        if "profile" in issued["scope"].split():
            claims["oid"] = issued["oid"]  # Microsoft Entra puts the object id in the identity token only when the scope `profile` was asked for
        return 200, {}, json.dumps({"token_type": "Bearer", "scope": "https://management.azure.com/user_impersonation", "access_token": PERSON_TOKEN,
                                    "id_token": jwt(claims), "expires_in": 3599}).encode()


def fetch(url, headers, timeout):
    """The platform's token endpoint: one token for each identity and resource, so that a test can tell the identities of Meternaut from the person."""
    query = parse_qs(urlsplit(url).query)
    client, resource = query.get("client_id", ["none"])[0], query.get("resource", [""])[0]
    token = f"assertion-of-{client}" if resource == "api://AzureADTokenExchange" else f"tok-{client}"
    return 200, json.dumps({"access_token": token, "expires_on": str(int(NOW.timestamp()) + 3600), "resource": resource}).encode("utf-8")


class World:
    """Everything the app talks to, behind one transport that routes by host and path. `phase` says which part of the story a call belongs to."""

    def __init__(self):
        self.estate = FakeEstate()
        row = disk_row("planted-disk-1", GROUP, tags={"meternaut-planted": "demo"}, timeCreated=stamp(NOW))
        self.estate.graph["orphan-managed-disk"] = [row]
        self.estate.graph["recent-creations"] = [{"targetId": row["id"].lower()}]
        self.tables = FakeTables()
        self.mail = Mail()
        self.entra = Entra()
        self.resources = Resources({f"Bearer {PERSON_TOKEN}"})
        self.calls = []
        self.phase = "watch"

    def __call__(self, method, url, headers, data, timeout):
        parts = urlsplit(url)
        self.calls.append((self.phase, method, parts.netloc, parts.path, headers.get("Authorization", "")))
        if parts.netloc.endswith(".table.core.windows.net"):
            return self.tables.transport(method, url, headers, data, timeout)
        if parts.netloc == "graph.microsoft.com":
            return self.mail(method, url, headers, data, timeout)
        if parts.netloc == "login.microsoftonline.com":
            return self.entra(method, url, headers, data, timeout)
        if "/providers/microsoft.compute/disks/" in parts.path.lower() and "/providers/microsoft.authorization/" not in parts.path.lower():
            return self.resources(method, url, headers, data, timeout)
        return self.estate(method, url, headers, data, timeout)


class Browser:
    """A person's browser, signed in to the console: it sends requests through the real pages."""

    def __init__(self, services, oid=OID):
        self.services, self.oid = services, oid

    def send(self, method, path, query=None, form=None):
        url = f"https://{HOST}{path}" + (f"?{urlencode(query)}" if query else "")
        headers = {"X-MS-CLIENT-PRINCIPAL-ID": self.oid, "X-MS-CLIENT-PRINCIPAL-NAME": "tino@example.com"}
        body = None
        if form is not None:
            body, headers["Content-Type"] = urlencode(form), "application/x-www-form-urlencoded"
        return Reply(handle(parse_request(method, url, headers, body), self.services))

    def press_approve(self, plan_id):
        page = self.send("GET", f"/ok/{plan_id}")
        assert page.status == 200, page.text
        form = page.form(f"/ok/{plan_id}", has_button=APPROVE)
        name, value = form.button_value(APPROVE)
        return self.send("POST", f"/ok/{plan_id}", form={**form.fields, name: value})


def watch(world, clock):
    world.phase = "watch"
    return run.run_watch("control", "a" * 32, dict(LOOP_ENV), clock=clock, monotonic=Ticker(), sleep=lambda s: None, transport=world, fetch=fetch,
                         new_id=iter(f"{n:032x}" for n in range(1, 1000)).__next__)


def store_of(world, clock):
    client = Client(table_calls("stexample"), Redactor(), transport=world.tables.transport, sleep=lambda s: None, monotonic=lambda: 0.0)
    return TableStore(client, lambda r: "T0KEN", "stexample", clock=clock)


class TheWholeLoop(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        self.world = World()
        self.store = store_of(self.world, self.clock)
        self.browser = Browser(console.build_services(dict(LOOP_ENV), transport=self.world, sleep=lambda s: None, monotonic=Ticker(), clock=self.clock, fetch=fetch))

    def tick(self):
        self.world.phase = "timer"
        return loop.tick(dict(LOOP_ENV), transport=self.world, sleep=lambda s: None, monotonic=Ticker(), clock=self.clock, fetch=fetch)

    def approve(self, plan):
        """The person presses Approve, signs in to Azure and comes back. Returns the page that shows what came of it."""
        self.world.phase = "approval"
        pressed = self.browser.press_approve(plan.plan_id)
        self.assertEqual(pressed.status, 303, pressed.text)
        code, state = self.world.entra.sign_in(pressed.headers["Location"])
        return self.browser.send("GET", "/arm/return", query={"code": code, "state": state})

    def test_from_a_planted_disk_to_its_removal_with_the_approvers_own_token_and_the_letters_on_the_way(self):
        summary = watch(self.world, self.clock)
        self.assertTrue(summary.ok)
        (case,) = self.store.cases_recent()
        self.assertEqual((case.status, case.detector, case.resource_group), ("awaiting_ok", "orphan-managed-disk", GROUP))
        (plan,) = self.store.plans_open()
        self.assertEqual((plan.state, plan.family, plan.approvers), ("open", "delete-disk", (OID,)))

        letters = self.world.mail.sent
        self.assertEqual([m["message"]["subject"].split("]")[0] for m in letters], ["[Meternaut", "[Meternaut"])
        approval = letters[1]["message"]["body"]["content"]
        self.assertIn(f"https://{HOST}/ok/{plan.plan_id}", approval)
        self.assertIn("with your own permissions", approval)
        self.assertNotIn("planted-disk-1", letters[1]["message"]["subject"])

        self.assertEqual(self.tick().finished, [], "nothing runs before a person has answered")
        self.assertTrue(self.world.resources.exists)

        self.world.phase = "approval"
        pressed = self.browser.press_approve(plan.plan_id)
        self.assertEqual(pressed.status, 303)
        self.assertEqual(pressed.body, b"")
        self.assertEqual(pressed.headers["Cache-Control"], "no-store")
        self.assertIn("form-action 'self' https://login.microsoftonline.com", pressed.headers["Content-Security-Policy"])
        self.assertTrue(self.world.resources.exists, "pressing Approve changes nothing: the person has still to sign in")
        self.assertEqual(self.store.plan_get(plan.plan_id).state, "open")
        self.assertEqual(self.store.decisions_of_plan(plan.plan_id), [])

        code, state = self.world.entra.sign_in(pressed.headers["Location"])
        done = self.browser.send("GET", "/arm/return", query={"code": code, "state": state})
        self.assertEqual(done.status, 200, done.text)
        self.assertIn("The change was made", done.content)
        self.assertIn("Deleted. Azure no longer lists the resource.", done.content)
        self.assertIn("Activity Log shows your name", done.content)
        self.assertFalse(self.world.resources.exists)
        self.assertEqual(self.store.plan_get(plan.plan_id).state, "consumed")
        self.assertEqual(self.store.action_get(plan.plan_id).state, "done")
        self.assertEqual(self.store.case_get(case.case_id).status, "done")
        self.assertEqual([(d.decision, d.approver_oid) for d in self.store.decisions_of_plan(plan.plan_id)], [("approve", OID)])

        # The redemption of the code was a proper one: verifier, redirect address, federated assertion and no secret (the fake Entra refuses otherwise).
        self.assertEqual(len(self.world.entra.redemptions), 1)
        self.assertEqual(self.world.entra.redemptions[0]["client_assertion"], f"assertion-of-{ASSERTION_CLIENT}")

        # Only the person's token deleted, once; no identity of Meternaut did.
        deletes = [c for c in self.world.calls if c[1] == "DELETE" and c[2] == "management.azure.com"]
        self.assertEqual([(phase, auth) for phase, _, _, _, auth in deletes], [("approval", f"Bearer {PERSON_TOKEN}")])
        arm_calls = [c for c in self.world.calls if c[0] == "approval" and c[2] == "management.azure.com"]
        self.assertTrue(arm_calls)
        self.assertTrue(all(c[4] == f"Bearer {PERSON_TOKEN}" for c in arm_calls), arm_calls)

        # The timer tells the person what ran, and makes no change.
        self.clock.advance(minutes=1)
        self.assertEqual(self.tick().finished, [])
        self.assertEqual(len(self.world.mail.sent), 3, "the third letter says what ran")
        self.assertIn("[Meternaut]", self.world.mail.sent[2]["message"]["subject"])
        self.assertIn("has run", self.world.mail.sent[2]["message"]["subject"])
        timer_arm = [c for c in self.world.calls if c[0] == "timer" and c[2] == "management.azure.com"]
        self.assertTrue(all(c[1] in ("GET", "POST") for c in timer_arm))
        self.clock.advance(minutes=5)
        self.tick()
        self.assertEqual(len(self.world.mail.sent), 3, "no letter twice")

    def test_a_person_whom_azure_does_not_let_delete_gets_a_refusal_and_the_disk_stays(self):
        watch(self.world, self.clock)
        (plan,) = self.store.plans_open()
        self.world.resources.may = set()
        refused = self.approve(plan)
        self.assertEqual(refused.status, 403)
        self.assertIn("Azure refused the change", refused.content)
        self.assertIn("(403, AuthorizationFailed)", refused.content)
        self.assertIn("Nothing was changed", refused.content)
        self.assertTrue(self.world.resources.exists)
        self.assertEqual(self.store.action_get(plan.plan_id).state, "failed")
        self.assertEqual(self.store.plan_get(plan.plan_id).state, "failed")
        self.assertEqual(self.store.case_get(self.store.cases_recent()[0].case_id).status, "failed")
        self.clock.advance(minutes=1)
        self.tick()
        self.assertEqual(len(self.world.mail.sent), 3, "the person is told that the change did not complete")
        self.assertTrue(self.world.resources.exists)

    def test_a_pulled_switch_stops_an_approval_before_the_sign_in_and_releasing_it_lets_it_go_on(self):
        watch(self.world, self.clock)
        (plan,) = self.store.plans_open()
        self.world.phase = "approval"
        opened = self.browser.send("GET", f"/ok/{plan.plan_id}")
        form = opened.form(f"/ok/{plan.plan_id}", has_button=APPROVE)
        name, value = form.button_value(APPROVE)
        self.store.switch_put(SwitchRecord(name="changes", paused=True, by=OID, at=stamp(self.clock())))
        paused = self.browser.send("GET", f"/ok/{plan.plan_id}")
        self.assertFalse(any(f.has_button(APPROVE) for f in paused.forms()), "the page has no approve button while changes are paused")
        stale = self.browser.send("POST", f"/ok/{plan.plan_id}", form={**form.fields, name: value})
        self.assertEqual(stale.status, 409, "a page that was opened before the switch was pulled cannot approve")
        self.assertIn("Changes are paused", stale.content)
        self.assertTrue(self.world.resources.exists)
        self.assertEqual(self.world.entra.redemptions, [])
        self.store.switch_put(SwitchRecord(name="changes", paused=False))
        self.assertEqual(self.approve(plan).status, 200)
        self.assertFalse(self.world.resources.exists)

    def test_a_switch_pulled_while_the_person_signs_in_stops_the_change_at_the_return(self):
        watch(self.world, self.clock)
        (plan,) = self.store.plans_open()
        self.world.phase = "approval"
        pressed = self.browser.press_approve(plan.plan_id)
        code, state = self.world.entra.sign_in(pressed.headers["Location"])
        self.store.switch_put(SwitchRecord(name="all", paused=True, by=OID, at=stamp(self.clock())))
        stopped = self.browser.send("GET", "/arm/return", query={"code": code, "state": state})
        self.assertEqual(stopped.status, 409)
        self.assertIn("Changes are paused", stopped.content)
        self.assertTrue(self.world.resources.exists)
        self.assertEqual(self.world.entra.redemptions, [], "the code is not redeemed for a change that may not be made")

    def test_a_sign_in_that_never_returns_changes_nothing_and_leaves_the_request_open(self):
        watch(self.world, self.clock)
        (plan,) = self.store.plans_open()
        self.world.phase = "approval"
        pressed = self.browser.press_approve(plan.plan_id)
        code, state = self.world.entra.sign_in(pressed.headers["Location"])
        self.clock.advance(minutes=11)
        late = self.browser.send("GET", "/arm/return", query={"code": code, "state": state})
        self.assertEqual(late.status, 409)
        self.assertIn("not valid any more", late.content)
        self.assertTrue(self.world.resources.exists)
        self.assertEqual(self.store.plan_get(plan.plan_id).state, "open")
        self.assertEqual(self.store.decisions_of_plan(plan.plan_id), [])
        self.assertEqual(self.approve(plan).status, 200, "the request can be approved again")

    def test_a_person_who_signs_in_with_another_account_approves_nothing(self):
        watch(self.world, self.clock)
        (plan,) = self.store.plans_open()
        self.world.phase = "approval"
        pressed = self.browser.press_approve(plan.plan_id)
        code, state = self.world.entra.sign_in(pressed.headers["Location"], oid="99999999-8888-7777-6666-555555555555")
        reply = self.browser.send("GET", "/arm/return", query={"code": code, "state": state})
        self.assertEqual(reply.status, 400)
        self.assertIn("another account", reply.content)
        self.assertTrue(self.world.resources.exists)
        self.assertEqual(self.store.decisions_of_plan(plan.plan_id), [])
        self.assertEqual([c for c in self.world.calls if c[1] == "DELETE" and c[2] == "management.azure.com"], [])

    def test_letters_that_could_not_be_sent_are_offered_again_by_the_timer_until_they_arrive_and_never_twice(self):
        real = self.world.mail
        self.world.mail = lambda method, url, headers, data, timeout: (403, {}, b'{"error":{"code":"ErrorAccessDenied","message":"no"}}')
        watch(self.world, self.clock)
        (plan,) = self.store.plans_open()
        self.assertEqual(real.sent, [])
        self.assertEqual({m.status for m in self.store.mails_since(OID, "2000-01-01T00:00:00Z")}, {"failed"})
        self.clock.advance(minutes=1)
        self.tick()
        self.assertEqual(len(self.store.mails_since(OID, "2000-01-01T00:00:00Z")), 2, "the last try was a minute ago: not yet")
        self.world.mail = real
        self.clock.advance(minutes=16)
        self.tick()
        self.assertEqual(len(real.sent), 2)
        self.clock.advance(minutes=16)
        self.tick()
        self.assertEqual(len(real.sent), 2, "what arrived is not sent again")
        self.assertEqual(self.approve(plan).status, 200)
        self.clock.advance(minutes=1)
        self.tick()
        self.assertEqual(len(real.sent), 3)
        self.clock.advance(minutes=20)
        self.tick()
        self.assertEqual(len(real.sent), 3)

    def test_a_second_watch_does_not_judge_the_same_disk_again_or_write_a_second_plan_or_send_a_second_letter(self):
        watch(self.world, self.clock)
        chats = len(self.world.estate.chat_calls())
        self.clock.advance(days=1)
        watch(self.world, self.clock)
        self.assertEqual(len(self.world.estate.chat_calls()), chats)
        self.assertEqual(len(self.store.plans_open()), 1)
        self.assertEqual(len(self.world.mail.sent), 2)

    def test_an_unanswered_plan_expires_and_the_case_says_so(self):
        watch(self.world, self.clock)
        (plan,) = self.store.plans_open()
        self.clock.advance(hours=73)
        self.assertEqual([p.plan_id for p in self.tick().expired], [plan.plan_id])
        self.assertEqual(self.store.plans_open(), [])
        self.assertEqual(self.store.cases_recent()[0].status, "expired")
        self.assertTrue(self.world.resources.exists)

    def test_the_loop_is_off_without_its_settings(self):
        self.assertIsNone(loop.tick({**ENV}, transport=self.world, sleep=lambda s: None, monotonic=Ticker(), clock=self.clock, fetch=fetch))
        self.assertEqual(self.world.calls, [])

    def test_no_mail_without_a_sender_and_the_loop_still_runs(self):
        env = {k: v for k, v in LOOP_ENV.items() if k != "MAIL_SENDER"}
        run.run_watch("control", "a" * 32, env, clock=self.clock, monotonic=Ticker(), sleep=lambda s: None, transport=self.world, fetch=fetch)
        self.assertEqual(self.world.mail.sent, [])
        self.assertEqual(len(self.store.plans_open()), 1)

    def test_a_mail_that_graph_refuses_never_stops_the_loop_and_is_recorded(self):
        self.world.mail = lambda method, url, headers, data, timeout: (403, {}, b'{"error":{"code":"ErrorAccessDenied","message":"no"}}')
        summary = watch(self.world, self.clock)
        self.assertTrue(summary.ok)
        self.assertEqual(len(self.store.plans_open()), 1)
        statuses = {m.status for m in self.store.mails_since(OID, "2000-01-01T00:00:00Z")}
        self.assertEqual(statuses, {"failed"})

    def test_without_the_settings_of_the_sign_in_the_loop_works_and_nobody_can_approve(self):
        env = {k: v for k, v in LOOP_ENV.items() if not k.startswith("SIGNIN_") and k != "OVERRIDE_USE_MI_FIC_ASSERTION_CLIENTID"}
        run.run_watch("control", "a" * 32, env, clock=self.clock, monotonic=Ticker(), sleep=lambda s: None, transport=self.world, fetch=fetch)
        (plan,) = self.store.plans_open()
        browser = Browser(console.build_services(env, transport=self.world, sleep=lambda s: None, monotonic=Ticker(), clock=self.clock, fetch=fetch))
        refused = browser.press_approve(plan.plan_id)
        self.assertEqual(refused.status, 500)
        self.assertIn("not set up", refused.content)
        self.assertTrue(self.world.resources.exists)

    def test_nothing_that_the_app_does_on_its_own_changes_azure_and_only_the_known_hosts_were_called(self):
        watch(self.world, self.clock)
        (plan,) = self.store.plans_open()
        self.assertEqual(self.approve(plan).status, 200)
        self.clock.advance(days=3)
        self.tick()
        hosts = {host for _, _, host, _, _ in self.world.calls}
        self.assertEqual(hosts, {"management.azure.com", "stexample.table.core.windows.net", "example-apim.azure-api.net", "graph.microsoft.com", "login.microsoftonline.com"})
        writes = [(phase, method, host) for phase, method, host, path, _ in self.world.calls if method in ("PUT", "DELETE", "PATCH") and host == "management.azure.com"]
        self.assertEqual(writes, [("approval", "DELETE", "management.azure.com")], "the one change was made during the approval, with the person's token")

    def test_the_timer_has_no_way_to_delete(self):
        watch(self.world, self.clock)
        (plan,) = self.store.plans_open()
        pressed = self.browser.press_approve(plan.plan_id)
        self.assertEqual(pressed.status, 303)
        self.clock.advance(hours=1)
        for _ in range(3):
            self.tick()
        self.assertTrue(self.world.resources.exists)
        self.assertEqual([c for c in self.world.calls if c[1] == "DELETE" and c[2] == "management.azure.com"], [])


if __name__ == "__main__":
    unittest.main()
