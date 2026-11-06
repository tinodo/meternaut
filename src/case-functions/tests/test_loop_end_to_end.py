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
from urllib.parse import parse_qs, quote, urlencode, urlsplit

from support import ENV, NOW, RG, SUBSCRIPTION, FakeEstate, LogCapture, Ticker, disk_row

from cases import console, loop, loop_config, run
from cases.http import Client
from cases.memory_store import stamp
from cases.models import SwitchRecord
from cases.redact import Redactor
from cases.runner import ASKED_AGAIN, STEP_UP_ABANDONED
from cases.store import TableStore, table_calls
from cases.web import handle, parse_request

from test_runner import CLAIMS, challenge
from test_store import FakeTables
from test_web_approval import rows
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
CHECKED_TOKEN = "arm-access-token-after-the-extra-check-0123456789"
SCHEME = "Bearer"
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


class CheckedResources(Resources):
    """Resource Manager in a tenant that wants the multifactor check for a delete: a delete with a token that lacks the check is answered with a claims challenge.

    `status` is what such a delete is answered with (401 is what Azure answers) and `header` is the `www-authenticate` header that goes with it (none, when it is empty)."""

    def __init__(self, may_delete, checked, header, status=401):
        super().__init__(may_delete)
        self.checked, self.header, self.status = set(checked), header, status

    def __call__(self, method, url, headers, data, timeout):
        auth = headers.get("Authorization", "")
        if method == "DELETE" and auth not in self.checked:
            self.calls.append((method, urlsplit(url).path, auth))
            return self.status, {"www-authenticate": self.header} if self.header else {}, b'{"error":{"code":"InvalidAuthenticationToken","message":"the token lacks a claim"}}'
        return super().__call__(method, url, headers, data, timeout)


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
        if form.get("claims") != issued.get("claims"):
            problems.append("the claims request goes with the code of a sign-in that asked for claims, and with no other")
        if problems:
            return 400, {}, json.dumps({"error": "invalid_client", "error_description": "AADSTS700027: " + "; ".join(problems)}).encode()
        claims = {"tid": TENANT, "aud": CLIENT, "nonce": issued["nonce"], "sub": "pairwise-subject-of-the-person", "iss": f"https://login.microsoftonline.com/{TENANT}/v2.0",
                  "exp": int(NOW.timestamp()) + 3600, "preferred_username": "tino@example.com"}
        if "profile" in issued["scope"].split():
            claims["oid"] = issued["oid"]  # Microsoft Entra puts the object id in the identity token only when the scope `profile` was asked for
        # A sign-in that was asked for with a claims request (the extra check) gives a token that carries those claims: that is the token that Azure accepts for a delete.
        return 200, {}, json.dumps({"token_type": "Bearer", "scope": "https://management.azure.com/user_impersonation",
                                    "access_token": CHECKED_TOKEN if issued.get("claims") else PERSON_TOKEN, "id_token": jwt(claims), "expires_in": 3599}).encode()


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
    """A person's browser, signed in to the console: it sends requests through the real pages and keeps the text of every page that came back."""

    def __init__(self, services, oid=OID):
        self.services, self.oid = services, oid
        self.seen: list[str] = []

    def send(self, method, path, query=None, form=None):
        url = f"https://{HOST}{path}" + (f"?{urlencode(query)}" if query else "")
        headers = {"X-MS-CLIENT-PRINCIPAL-ID": self.oid, "X-MS-CLIENT-PRINCIPAL-NAME": "tino@example.com"}
        body = None
        if form is not None:
            body, headers["Content-Type"] = urlencode(form), "application/x-www-form-urlencoded"
        reply = Reply(handle(parse_request(method, url, headers, body), self.services))
        self.seen.append(reply.text)
        return reply

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


class Story(unittest.TestCase):
    """The loop with its fakes: a world, a clock, a store that reads what the app wrote, a browser that is signed in, the timer, and the press of Approve."""

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


class TheWholeLoop(Story):
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


def auth(token: str) -> str:
    return f"{SCHEME} {token}"


# What a person's sign-in, a page, a log, a letter or a record of the store must never hold of the claims request that Azure asked for.
SECRETS = (CLAIMS, "c-unique-4711", base64.b64encode(CLAIMS.encode()).decode(), base64.urlsafe_b64encode(CLAIMS.encode()).decode().rstrip("="), quote(CLAIMS, safe=""),
           "insufficient_claims")


class TheStepUp(Story):
    """A person who signed in without the multifactor check that a change needs. Azure answers the delete with a claims challenge (HTTP 401 and a `www-authenticate`
    header): the console sends the person to Microsoft Entra once more, with the claims request, and the return of that second sign-in deletes the disk. One approval, one
    action, and the claims are in nothing that is shown or kept but the one-time state of the second sign-in, until it is used."""

    def setUp(self):
        super().setUp()
        self.header = challenge(CLAIMS)["www-authenticate"]
        # Azure accepts a delete only with the token that the second sign-in gives: the first token lacks the check.
        self.world.resources = CheckedResources({auth(CHECKED_TOKEN)}, {auth(CHECKED_TOKEN)}, self.header)
        self.capture = LogCapture()
        self.capture.__enter__()
        self.addCleanup(self.capture.__exit__, None, None, None)

    def start(self):
        watch(self.world, self.clock)
        (self.plan,) = self.store.plans_open()

    def press(self):
        """The person presses Approve, signs in to Azure and comes back: what the console answers, which is a redirect when Azure asks for the extra check."""
        self.world.phase = "approval"
        pressed = self.browser.press_approve(self.plan.plan_id)
        self.assertEqual(pressed.status, 303, pressed.text)
        self.first_address = pressed.headers["Location"]
        code, state = self.world.entra.sign_in(self.first_address)
        self.first_return = {"code": code, "state": state}
        return self.browser.send("GET", "/arm/return", query=self.first_return)

    def come_back(self, step, **more):
        """The person goes where the console sent them, signs in once more and comes back."""
        self.world.phase = "approval"
        code, state = self.world.entra.sign_in(step.headers["Location"])
        self.second_return = {"code": code, "state": state}
        return self.browser.send("GET", "/arm/return", query={**self.second_return, **more})

    @staticmethod
    def query_of(address):
        return {k: v[0] for k, v in parse_qs(urlsplit(address).query).items()}

    def deletes(self):
        return [(phase, token) for phase, method, host, _, token in self.world.calls if method == "DELETE" and host == "management.azure.com"]

    def stored(self, tables=None):
        return json.dumps({name: [row for _, (row, _) in sorted(rows_.items())] for name, rows_ in self.world.tables.tables.items() if tables is None or name in tables}, sort_keys=True)

    def kept(self, states=False):
        """The text of every page, every line of the log and of the History, every letter and every row of the store (the one-time states only when they are asked for)."""
        tables = [name for name in self.world.tables.tables if states or name != "mnnonces"]
        return "\n".join([*self.browser.seen, *self.capture.messages(), json.dumps(self.capture.events()), json.dumps(self.world.mail.sent), self.stored(tables)])

    def holders(self):
        """How many one-time states hold the claims."""
        return sum(1 for row, _ in self.world.tables.tables.get("mnnonces", {}).values() if "c-unique-4711" in str(row.get("payload", "")))

    def assert_claims_nowhere(self, states=False):
        text = self.kept(states)
        for secret in SECRETS:
            self.assertNotIn(secret, text)

    def assert_nothing_deleted_and_closed(self, plan_state="failed"):
        self.assertTrue(self.world.resources.exists)
        self.assertEqual(self.store.plan_get(self.plan.plan_id).state, plan_state)

    def test_the_second_sign_in_deletes_the_disk_with_one_approval_and_one_action_and_the_claims_are_kept_nowhere(self):
        self.start()
        self.assertEqual(len(self.world.mail.sent), 2, "the first letter and the approval letter")
        step = self.press()

        # The first return: Azure asked for the extra check, so the console answers with a redirect to the sign-in, and nothing is closed.
        self.assertEqual((step.status, step.body), (303, b""))
        self.assertEqual(step.headers["Cache-Control"], "no-store")
        self.assertIn("form-action 'self' https://login.microsoftonline.com;", step.headers["Content-Security-Policy"])
        parts = urlsplit(step.headers["Location"])
        self.assertEqual((parts.scheme, parts.netloc, parts.path), ("https", "login.microsoftonline.com", f"/{TENANT}/oauth2/v2.0/authorize"))
        first, second = self.query_of(self.first_address), self.query_of(step.headers["Location"])
        self.assertNotIn("claims", first)
        self.assertEqual(second["claims"], CLAIMS, "the authorize address of the second sign-in carries the claims request")
        for name in ("state", "nonce", "code_challenge"):
            self.assertNotEqual(second[name], first[name], f"the second sign-in has a {name} of its own")
        self.assertEqual({k: v for k, v in second.items() if k not in ("state", "nonce", "code_challenge", "claims")},
                         {"client_id": CLIENT, "response_type": "code", "redirect_uri": f"https://{HOST}/arm/return", "response_mode": "query", "scope": first["scope"],
                          "code_challenge_method": "S256", "login_hint": "tino@example.com"})
        self.assertNotIn("offline_access", second["scope"])
        self.assertTrue(self.world.resources.exists, "nothing was deleted")
        self.assertEqual(self.store.plan_get(self.plan.plan_id).state, "approved")
        action = self.store.action_get(self.plan.plan_id)
        self.assertEqual((action.state, action.step_up, action.started_at), ("queued", True, None))
        self.assertEqual([(d.decision, d.approver_oid) for d in self.store.decisions_of_plan(self.plan.plan_id)], [("approve", OID)])
        self.assertEqual(self.deletes(), [("approval", auth(PERSON_TOKEN))], "the first delete was made with the token that lacks the check, and Azure asked for it")

        # While the person is at Microsoft Entra: the page says what it waits for, the claims are in the one state and nowhere else, and the timer does nothing.
        waiting = self.browser.send("GET", f"/ok/{self.plan.plan_id}")
        self.assertEqual(waiting.status, 200)
        self.assertIn("Azure asked for an extra sign-in check before it would make the change.", waiting.content)
        self.assertIn("Nothing was changed yet.", waiting.content)
        self.assertEqual(waiting.forms(), [], "no second approval can be given")
        self.assertEqual(self.holders(), 1)
        self.assert_claims_nowhere()
        self.clock.advance(minutes=5)
        self.assertEqual(self.tick().finished, [])
        self.assertEqual(len(self.world.mail.sent), 2, "no letter while the check is waited for")
        self.assertTrue(self.world.resources.exists)

        # The second return deletes the disk with the token that the second sign-in gave.
        done = self.come_back(step)
        self.assertEqual(done.status, 200, done.text)
        self.assertIn("The change was made", done.content)
        self.assertIn("Deleted. Azure no longer lists the resource.", done.content)
        self.assertFalse(self.world.resources.exists)
        self.assertEqual(self.deletes(), [("approval", auth(PERSON_TOKEN)), ("approval", auth(CHECKED_TOKEN))])
        self.assertEqual(len(self.world.entra.redemptions), 2)
        one, two = self.world.entra.redemptions
        self.assertNotEqual(one["code_verifier"], two["code_verifier"])
        self.assertEqual({one["client_assertion"], two["client_assertion"]}, {f"assertion-of-{ASSERTION_CLIENT}"})
        self.assertEqual(len(self.store.decisions_of_plan(self.plan.plan_id)), 1, "one approval")
        self.assertEqual(len(self.store.actions_recent(10)), 1, "one action")
        action = self.store.action_get(self.plan.plan_id)
        self.assertEqual((action.state, action.step_up, action.result), ("done", True, "Deleted. Azure no longer lists the resource."))
        self.assertEqual(self.store.plan_get(self.plan.plan_id).state, "consumed")
        self.assertEqual(self.store.case_get(self.plan.case_id).status, "done")
        self.assertEqual(self.holders(), 0, "the state of the second sign-in is used up, and so are the claims in it")

        # The plan page afterwards says Done.
        after = self.browser.send("GET", f"/ok/{self.plan.plan_id}")
        self.assertEqual(rows(after)["State"], "Done.")
        self.assertEqual(rows(after)["Result"], "Deleted. Azure no longer lists the resource.")
        self.assertIn("The change was made, with the permissions of the person who approved it.", after.content)
        self.assertEqual(after.forms(), [])

        # The timer tells what ran, once.
        self.clock.advance(minutes=1)
        self.tick()
        self.assertEqual(len(self.world.mail.sent), 3)
        self.assertIn("has run", self.world.mail.sent[2]["message"]["subject"])
        self.clock.advance(minutes=20)
        self.tick()
        self.assertEqual(len(self.world.mail.sent), 3, "no letter twice")

        # The History says that the person was sent again, once.
        kinds = [event["type"] for event in self.capture.events() if event["type"].startswith(("signin.", "approval.", "action."))]
        self.assertEqual(kinds, ["signin.started", "approval.recorded", "action.started", "signin.stepup", "action.started", "action.finished"])
        self.assert_claims_nowhere(states=True)

    def test_the_retry_cannot_be_replayed_and_neither_can_the_first_return(self):
        self.start()
        step = self.press()
        self.assertEqual(self.come_back(step).status, 200)
        deletes, redemptions = len(self.deletes()), len(self.world.entra.redemptions)
        for label, query in (("the return of the second sign-in", self.second_return), ("the return of the first sign-in", self.first_return)):
            with self.subTest(label):
                again = self.browser.send("GET", "/arm/return", query=query)
                self.assertEqual(again.status, 409)
                self.assertIn("This sign-in is not valid any more", again.content)
        self.assertEqual((len(self.deletes()), len(self.world.entra.redemptions)), (deletes, redemptions), "nothing was redeemed and nothing was deleted again")
        self.assertEqual(len(self.store.decisions_of_plan(self.plan.plan_id)), 1)
        self.assertEqual(self.browser.send("GET", f"/ok/{self.plan.plan_id}").forms(), [], "a closed plan offers no second approval")

    def test_a_person_who_tries_the_first_return_again_while_the_check_is_waited_for_is_refused_and_nothing_is_closed(self):
        self.start()
        step = self.press()
        again = self.browser.send("GET", "/arm/return", query=self.first_return)
        self.assertEqual((again.status, step.status), (409, 303))
        self.assertEqual(self.store.plan_get(self.plan.plan_id).state, "approved")
        self.assertEqual(self.come_back(step).status, 200, "the second sign-in still works")

    def test_a_second_challenge_is_final_the_person_is_sent_nowhere_and_nothing_was_changed(self):
        self.world.resources = CheckedResources({auth(CHECKED_TOKEN)}, set(), self.header)  # whatever the person has done, Azure wants more
        self.start()
        step = self.press()
        self.assertEqual(step.status, 303)
        refused = self.come_back(step)
        self.assertEqual(refused.status, 403)
        self.assertNotIn("Location", refused.headers)
        self.assertIn("Azure refused the change", refused.content)
        self.assertIn(ASKED_AGAIN, refused.content)
        self.assertEqual(self.deletes(), [("approval", auth(PERSON_TOKEN)), ("approval", auth(CHECKED_TOKEN))], "two deletes were tried and there was no third")
        self.assertEqual(len(self.world.entra.redemptions), 2)
        self.assert_nothing_deleted_and_closed()
        self.assertEqual((self.store.action_get(self.plan.plan_id).state, self.store.case_get(self.plan.case_id).status), ("failed", "failed"))
        self.assertEqual(len(self.store.decisions_of_plan(self.plan.plan_id)), 1)
        self.assertEqual(len(self.store.actions_recent(10)), 1)
        self.assertEqual(self.holders(), 0)
        self.clock.advance(minutes=1)
        self.tick()
        self.assertEqual(len(self.world.mail.sent), 3)
        self.assertIn("did not run", self.world.mail.sent[2]["message"]["subject"])
        self.assert_claims_nowhere(states=True)

    def test_an_answer_that_is_not_a_valid_claims_challenge_is_an_ordinary_refusal_and_no_second_sign_in_is_made(self):
        for label, status, header in (("a 401 without a header", 401, ""), ("a 401 with a header that is not a challenge", 401, f'{SCHEME} realm="x"'),
                                      ("a 401 with claims that are not base64", 401, f'{SCHEME} error="insufficient_claims", claims="!!!"'),
                                      ("a 401 with claims that are not an object", 401, challenge('[1]')["www-authenticate"]),
                                      ("a 401 with another error", 401, self.header.replace("insufficient_claims", "invalid_token")),
                                      ("a 401 with two claims directives", 401, self.header + self.header[self.header.index(", claims="):]),
                                      ("a 403 with a valid challenge", 403, self.header), ("a 403 without a header", 403, "")):
            with self.subTest(label):
                Story.setUp(self)
                self.world.resources = CheckedResources(set(), set(), header, status=status)
                self.start()
                refused = self.press()
                self.assertEqual(refused.status, 403)
                self.assertNotIn("Location", refused.headers)
                self.assertIn("Azure refused the change", refused.content)
                self.assertIn(f"Azure refused to delete the resource ({status}, InvalidAuthenticationToken)", refused.content)
                self.assertIn("Nothing was changed", refused.content)
                self.assert_nothing_deleted_and_closed()
                action = self.store.action_get(self.plan.plan_id)
                self.assertEqual((action.state, action.step_up), ("failed", False))
                self.assertEqual(len(self.world.entra.redemptions), 1, "no second sign-in")
                self.assertEqual(self.holders(), 0)
                self.assertEqual(self.deletes(), [("approval", auth(PERSON_TOKEN))])
        self.assert_claims_nowhere(states=True)

    def test_a_person_who_cancels_the_extra_check_closes_the_request_and_is_told_once(self):
        self.start()
        step = self.press()
        state = self.query_of(step.headers["Location"])["state"]
        description = "AADSTS65004: The user declined to consent to access the app. Trace ID: 0b0c1d2e Correlation ID: 7e1f Timestamp: 2026-11-04 12:00:00Z"
        cancelled = self.browser.send("GET", "/arm/return", query={"state": state, "error": "access_denied", "error_description": description})
        self.assertEqual(cancelled.status, 400)
        self.assertEqual(cancelled.headings(1), ["The extra sign-in check was not completed"])
        self.assertIn("It was cancelled or refused.", cancelled.content)
        self.assertIn("The change was not made. Nothing was changed. The request is closed.", cancelled.content)
        for hidden in ("Trace ID", "0b0c1d2e", "AADSTS65004", "Correlation ID"):
            self.assertNotIn(hidden, cancelled.text)
        self.assert_nothing_deleted_and_closed()
        self.assertEqual((self.store.action_get(self.plan.plan_id).state, self.store.case_get(self.plan.case_id).status), ("failed", "failed"))
        self.assertEqual(len(self.world.entra.redemptions), 1, "no code was redeemed for the second sign-in")
        self.assertEqual(self.deletes(), [("approval", auth(PERSON_TOKEN))])
        self.assertEqual(self.holders(), 0, "the state was used up by the return that cancelled")
        after = self.browser.send("GET", f"/ok/{self.plan.plan_id}")
        self.assertEqual(rows(after)["State"], "Failed.")
        self.assertIn("The extra sign-in check that Azure asked for was not completed.", rows(after)["Result"])
        self.assertEqual(after.forms(), [])
        again = self.browser.send("GET", "/arm/return", query={"state": state, "error": "access_denied"})
        self.assertEqual((again.status, "not valid any more" in again.content), (409, True))
        self.clock.advance(minutes=1)
        self.tick()
        self.assertEqual(len(self.world.mail.sent), 3, "the person is told once that the change did not run")
        self.assertIn("did not run", self.world.mail.sent[2]["message"]["subject"])
        self.clock.advance(minutes=30)
        self.tick()
        self.assertEqual(len(self.world.mail.sent), 3)
        self.assert_claims_nowhere(states=True)

    def test_a_step_up_that_nobody_completes_is_closed_by_the_timer_and_a_late_return_changes_nothing(self):
        self.start()
        step = self.press()
        self.clock.advance(minutes=9)
        self.assertEqual(self.tick().finished, [], "the person may still complete the check")
        self.assertEqual(len(self.world.mail.sent), 2)
        self.clock.advance(minutes=2)
        closed = self.tick().finished
        self.assertEqual([a.state for a in closed], ["failed"])
        self.assertEqual(self.store.action_get(self.plan.plan_id).result, STEP_UP_ABANDONED)
        self.assert_nothing_deleted_and_closed()
        self.assertEqual(self.store.case_get(self.plan.case_id).status, "failed")
        self.assertEqual(len(self.world.mail.sent), 3, "the person is told that the change did not run")
        self.assertIn("did not run", self.world.mail.sent[2]["message"]["subject"])
        self.assertIn("not completed in time", self.world.mail.sent[2]["message"]["body"]["content"])
        self.clock.advance(minutes=5)
        self.tick()
        self.assertEqual(len(self.world.mail.sent), 3)
        late = self.come_back(step)
        self.assertEqual(late.status, 409)
        self.assertEqual(len(self.world.entra.redemptions), 1)
        self.assertEqual(self.deletes(), [("approval", auth(PERSON_TOKEN))])
        self.assert_nothing_deleted_and_closed()
        self.assert_claims_nowhere(states=True)

    def test_a_switch_pulled_while_the_person_passes_the_check_stops_the_retry_and_the_timer_closes_the_request(self):
        self.start()
        step = self.press()
        self.store.switch_put(SwitchRecord(name="changes", paused=True, by=OID, at=stamp(self.clock())))
        stopped = self.come_back(step)
        self.assertEqual(stopped.status, 409)
        self.assertIn("Changes are paused", stopped.content)
        self.assertEqual(len(self.world.entra.redemptions), 1, "the code is not redeemed for a change that may not be made")
        self.assertEqual(self.deletes(), [("approval", auth(PERSON_TOKEN))])
        self.assert_nothing_deleted_and_closed("approved")
        self.clock.advance(minutes=11)
        self.tick()
        self.assert_nothing_deleted_and_closed("failed")
        self.assertEqual(self.store.action_get(self.plan.plan_id).result, STEP_UP_ABANDONED)


if __name__ == "__main__":
    unittest.main()
