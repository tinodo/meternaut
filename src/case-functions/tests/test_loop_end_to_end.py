import datetime as dt
import json
import unittest
from urllib.parse import parse_qs, urlsplit

from support import ENV, NOW, RG, SUBSCRIPTION, FakeEstate, Ticker, disk_row

from cases import loop, run
from cases.approvals import Approvals
from cases.memory_store import stamp
from cases.models import Principal, SwitchRecord
from cases.store import TableStore
from cases.wiring import approval_settings
from cases import loop_config, wiring
from cases.http import Client
from cases.redact import Redactor
from cases.store import table_calls

from test_store import FakeTables

OID = "aaaaaaaa-1111-4222-8333-444444444444"
APPROVER = Principal(OID, "Tino", ("owner", "approver", "ops"))
GROUP = "rg-meternaut"
SENDER = "meternaut-ai@example.onmicrosoft.com"
DISK = f"{RG}/{GROUP}/providers/Microsoft.Compute/disks/planted-disk-1"
WRITER = "55555555-4444-3333-2222-111111111111"
LOOP_ENV = {
    **ENV,
    "STORE_ACCOUNT_NAME": "stexample",
    "WRITER_RESOURCE_GROUP": GROUP,
    "WRITER_SUBSCRIPTION_ID": SUBSCRIPTION,
    "WRITER_CLIENT_ID": WRITER,
    "CONSOLE_HOST": "func.example.net",
    "MAIL_SENDER": SENDER,
    "CONSOLE_PEOPLE": json.dumps([{"oid": OID, "name": "Tino", "roles": ["owner", "approver", "ops"], "mail": "tino@example.com"}]),
}


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
    """The planted disk in Resource Manager: it exists until it is deleted, and only the writer's token may delete it."""

    def __init__(self, tokens_that_may_delete):
        self.exists = True
        self.may = tokens_that_may_delete
        self.calls = []

    def __call__(self, method, url, headers, data, timeout):
        self.calls.append((method, urlsplit(url).path, headers.get("Authorization", "")))
        if method == "DELETE":
            if headers.get("Authorization", "") not in self.may:
                return 403, {}, b'{"error":{"code":"AuthorizationFailed","message":"no"}}'
            self.exists = False
            return 200, {}, b""
        if not self.exists:
            return 404, {}, b'{"error":{"code":"ResourceNotFound","message":"gone"}}'
        return 200, {}, json.dumps({"id": DISK, "name": "planted-disk-1", "tags": {"meternaut-planted": "demo"}, "properties": {"diskState": "Unattached"}}).encode()


def fetch(url, headers, timeout):
    """The platform's token endpoint: one token for each identity, named after its client id, so that a test can tell the reader from the writer."""
    client = parse_qs(urlsplit(url).query).get("client_id", ["none"])[0]
    return 200, json.dumps({"access_token": f"tok-{client}", "expires_on": str(int(NOW.timestamp()) + 3600), "resource": "x"}).encode("utf-8")


class World:
    """Everything the app talks to, behind one transport that routes by host and path."""

    def __init__(self):
        self.estate = FakeEstate()
        row = disk_row("planted-disk-1", GROUP, tags={"meternaut-planted": "demo"}, timeCreated=stamp(NOW))
        self.estate.graph["orphan-managed-disk"] = [row]
        self.estate.graph["recent-creations"] = [{"targetId": row["id"].lower()}]
        self.tables = FakeTables()
        self.mail = Mail()
        self.resources = Resources({f"Bearer tok-{WRITER}"})
        self.calls = []

    def __call__(self, method, url, headers, data, timeout):
        parts = urlsplit(url)
        self.calls.append((method, parts.netloc, parts.path))
        if parts.netloc.endswith(".table.core.windows.net"):
            return self.tables.transport(method, url, headers, data, timeout)
        if parts.netloc == "graph.microsoft.com":
            return self.mail(method, url, headers, data, timeout)
        if "/providers/microsoft.compute/disks/" in parts.path.lower() and "/providers/microsoft.authorization/" not in parts.path.lower():
            return self.resources(method, url, headers, data, timeout)
        return self.estate(method, url, headers, data, timeout)


def watch(world, clock):
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

    def tick(self):
        return loop.tick(dict(LOOP_ENV), transport=self.world, sleep=lambda s: None, monotonic=Ticker(), clock=self.clock, fetch=fetch)

    def approve(self, plan):
        approvals = Approvals(self.store, approval_settings(loop_config.load(LOOP_ENV)), self.clock)
        return approvals.decide(APPROVER, plan.plan_id, "approve", plan.code, self.store.nonce_new(OID, plan.plan_id))

    def test_from_a_planted_disk_to_its_removal_and_the_letters_on_the_way(self):
        summary = watch(self.world, self.clock)
        self.assertTrue(summary.ok)
        (case,) = self.store.cases_recent()
        self.assertEqual((case.status, case.detector, case.resource_group), ("awaiting_ok", "orphan-managed-disk", GROUP))
        (plan,) = self.store.plans_open()
        self.assertEqual((plan.state, plan.family, plan.approvers), ("open", "delete-disk", (OID,)))

        letters = self.world.mail.sent
        self.assertEqual([m["message"]["subject"].split("]")[0] for m in letters], ["[Meternaut", "[Meternaut"])
        self.assertTrue(all(m["url"] == f"https://graph.microsoft.com/v1.0/users/{SENDER}/sendMail" for m in letters))
        self.assertTrue(all(m["message"]["toRecipients"] == [{"emailAddress": {"address": "tino@example.com"}}] for m in letters))
        approval = letters[1]["message"]["body"]["content"]
        self.assertIn(f"https://func.example.net/ok/{plan.plan_id}", approval)
        self.assertNotIn("planted-disk-1", letters[1]["message"]["subject"])

        self.assertEqual(self.tick().finished, [], "nothing runs before a person has answered")
        self.assertTrue(self.world.resources.exists)

        result = self.approve(plan)
        self.assertEqual(result.kind, "recorded")
        self.clock.advance(seconds=60)
        self.assertEqual(self.tick().finished, [], "nothing runs before the start time: the approver may still cancel")
        self.assertTrue(self.world.resources.exists)
        self.clock.advance(seconds=61)
        done = self.tick().finished
        self.assertEqual([a.state for a in done], ["done"])
        self.assertFalse(self.world.resources.exists)
        self.assertEqual(self.store.plan_get(plan.plan_id).state, "consumed")
        self.assertEqual(self.store.case_get(case.case_id).status, "done")
        deletes = [c for c in self.world.resources.calls if c[0] == "DELETE"]
        self.assertEqual(len(deletes), 1)
        self.assertEqual(len(self.world.mail.sent), 3, "the third letter says what ran")
        self.assertIn("[Meternaut]", self.world.mail.sent[2]["message"]["subject"])

        self.clock.advance(minutes=5)
        self.assertEqual(self.tick().finished, [])
        self.assertEqual(len(self.world.mail.sent), 3, "no letter twice")

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
        self.approve(plan)
        self.clock.advance(seconds=200)
        self.assertEqual([a.state for a in self.tick().finished], ["done"])
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

    def test_the_reader_identity_is_never_the_one_that_deletes(self):
        watch(self.world, self.clock)
        (plan,) = self.store.plans_open()
        self.approve(plan)
        self.clock.advance(seconds=200)
        self.world.resources.may = {"Bearer tok-nobody"}
        self.tick()
        self.assertTrue(self.world.resources.exists, "the delete was refused, so the disk is still there")
        self.assertEqual(self.store.action_get(plan.plan_id).state, "failed")
        self.assertEqual(self.store.case_get(self.store.cases_recent()[0].case_id).status, "failed")

    def test_a_pulled_switch_stops_the_change_and_releasing_it_lets_it_run(self):
        watch(self.world, self.clock)
        (plan,) = self.store.plans_open()
        self.approve(plan)
        self.clock.advance(seconds=200)
        self.store.switch_put(SwitchRecord(name="changes", paused=True, by=OID, at=stamp(self.clock())))
        self.tick()
        self.assertTrue(self.world.resources.exists)
        self.store.switch_put(SwitchRecord(name="changes", paused=False))
        self.tick()
        self.assertFalse(self.world.resources.exists)

    def test_a_cancelled_approval_never_runs(self):
        watch(self.world, self.clock)
        (plan,) = self.store.plans_open()
        self.approve(plan)
        approvals = Approvals(self.store, approval_settings(loop_config.load(LOOP_ENV)), self.clock)
        self.clock.advance(seconds=30)
        self.assertEqual(approvals.withdraw(APPROVER, plan.plan_id, self.store.nonce_new(OID, plan.plan_id)).kind, "withdrawn")
        self.clock.advance(seconds=300)
        self.tick()
        self.assertTrue(self.world.resources.exists)

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

    def test_nothing_in_any_call_holds_a_key_and_only_the_known_hosts_were_called(self):
        watch(self.world, self.clock)
        (plan,) = self.store.plans_open()
        self.approve(plan)
        self.clock.advance(seconds=200)
        self.tick()
        hosts = {host for _, host, _ in self.world.calls}
        self.assertEqual(hosts, {"management.azure.com", "stexample.table.core.windows.net", "example-apim.azure-api.net", "graph.microsoft.com"})


if __name__ == "__main__":
    unittest.main()
