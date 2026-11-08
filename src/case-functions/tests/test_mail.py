import datetime as dt
import json
import unittest

import support  # noqa: F401  (puts the app on the path)
from cases import http, mail
from cases.letters import Letter
from cases.mail import BUDGET_FREE_KINDS, GRAPH_RESOURCE, MailResult, Mailer, mail_calls
from cases.memory_store import MemoryStore
from cases.models import MailRecord, SettingsRecord, StoreError, SwitchRecord
from cases.people import People, Person
from cases.redact import REDACTED, Redactor

SENDER = "meternaut-ai@contoso.example"
URL = f"https://graph.microsoft.com/v1.0/users/{SENDER}/sendMail"
JWT = ".".join(("eyJhbGciOiJSUzI1NiJ9", "eyJhdWQiOiJodHRwczovL2dyYXBoIn0abcdefgh", "c2lnbmF0dXJlLW9mLXRoZS10ZXN0"))
PLAIN = "tok-plain-0123456789-abcdefghij"
MAYA, NOOR, NOMAIL, STRANGER = ("11111111-1111-1111-1111-111111111111", "22222222-2222-2222-2222-222222222222", "33333333-3333-3333-3333-333333333333",
                                "44444444-4444-4444-4444-444444444444")
PEOPLE = People((Person(MAYA, "Maya", ("owner", "approver"), "maya@example.com"), Person(NOOR, "Noor", ("approver",), "Noor@Example.com"),
                 Person(NOMAIL, "Pat", ("ops",), "")))
LETTER = Letter("[Meternaut] A change to Azure waits for your OK", "<p>The body: other@example.org</p>", "The body")
NOW = dt.datetime(2026, 11, 5, 10, 18, 0, tzinfo=dt.timezone.utc)  # a Thursday; its ISO week began on Monday 2 November 00:00 UTC
MONDAY = "2026-11-02T00:00:00Z"


class Graph:
    """The transport behind the Client: answers from a list (the last answer repeats) and remembers every call."""

    def __init__(self, *answers):
        self.answers, self.calls = list(answers) or [(202, {}, b"")], []

    def __call__(self, method, url, headers, data, timeout):
        self.calls.append({"method": method, "url": url, "headers": dict(headers), "body": json.loads(data.decode("utf-8")) if data else None, "timeout": timeout})
        answer = self.answers.pop(0) if len(self.answers) > 1 else self.answers[0]
        if isinstance(answer, Exception):
            raise answer
        return answer


def error_answer(status, code="ErrorX", message="it failed"):
    return status, {}, json.dumps({"error": {"code": code, "message": message}}).encode("utf-8")


class Fixture:
    def __init__(self, *answers, now=NOW, people=PEOPLE, store=None, token=None, allowed=None):
        self.now = now
        self.graph = Graph(*answers)
        self.sleeps: list[float] = []
        self.redact = Redactor()
        self.client = http.Client(mail_calls(SENDER) if allowed is None else allowed, self.redact, transport=self.graph, sleep=self.sleeps.append, jitter=lambda: 0.5)
        self.store = store or MemoryStore(clock=lambda: self.now)
        self.tokens: list[str] = []
        self.token = token or self._token
        self.counter = 0
        self.mailer = Mailer(SENDER, self.client, self.token, people, self.store, lambda: self.now, self.redact, self._id)

    def _token(self, resource):
        self.tokens.append(resource)
        return JWT

    def _id(self):
        self.counter += 1
        return f"m{self.counter}"

    def send(self, person=None, letter=LETTER, kind="digest", plan_id=None):
        return self.mailer.send(person or PEOPLE.persons[0], letter, kind, plan_id)

    def settings(self, **changes):
        self.store.settings_put(SettingsRecord(oid=MAYA, **changes))

    def sent_before(self, count, kind="reminder", at="2026-11-03T08:00:00Z", status="sent", oid=MAYA):
        for n in range(count):
            self.store.mail_put(MailRecord(mail_id=f"old-{kind}-{status}-{at}-{n}", oid=oid, kind=kind, subject="[Meternaut] old", sent_at=at, status=status))

    @property
    def records(self) -> list[MailRecord]:
        return [m for m in self.store.mails if m.mail_id.startswith("m")]

    def untouched(self, test: unittest.TestCase):
        test.assertEqual(self.graph.calls, [])
        test.assertEqual(self.tokens, [])


class TheAllowedCall(unittest.TestCase):
    def test_the_list_holds_the_one_call_and_nothing_else(self):
        calls = mail_calls(SENDER)
        self.assertEqual(len(calls), 1)
        method, pattern = calls[0]
        self.assertEqual(method, "POST")
        self.assertTrue(pattern.fullmatch(URL))
        self.assertTrue(pattern.fullmatch(URL.upper().replace("HTTPS", "https")))
        for other in ("https://graph.microsoft.com/v1.0/users/other@contoso.example/sendMail", "https://graph.microsoft.com/v1.0/me/sendMail",
                      f"{URL}/x", f"{URL}x", URL.replace("https", "http"), f"https://graph.microsoft.com/v1.0/users/{SENDER}/messages",
                      f"https://graph.microsoft.com/v1.0/users/{SENDER}/sendMail?x=1", f"https://graph.microsoft.com/beta/users/{SENDER}/sendMail",
                      f"https://graph.microsoft.com.evil.example/v1.0/users/{SENDER}/sendMail"):
            self.assertFalse(pattern.fullmatch(other), other)

    def test_a_client_with_these_entries_makes_no_other_call(self):
        fixture = Fixture()
        for method, address in (("POST", "https://graph.microsoft.com/v1.0/users/other@contoso.example/sendMail"), ("GET", URL), ("PUT", URL), ("PATCH", URL),
                                ("DELETE", URL), ("POST", "https://graph.microsoft.com/v1.0/me/sendMail"),
                                ("POST", f"https://graph.microsoft.com/v1.0/users/{SENDER}/messages"), ("GET", "https://graph.microsoft.com/v1.0/users"),
                                ("POST", "https://management.azure.com/subscriptions")):
            with self.assertRaises(http.Refused, msg=f"{method} {address}"):
                fixture.client.request(method, address)
        self.assertEqual(fixture.graph.calls, [])
        fixture.client.request("POST", URL, body={})
        self.assertEqual([(c["method"], c["url"]) for c in fixture.graph.calls], [("POST", URL)])

    def test_the_sender_must_be_an_address(self):
        for bad in ("", "meternaut", "a@b", "a b@contoso.example", "a/b@contoso.example", "a@contoso.example/x", "a@contoso.example?x=1", "a%2f@contoso.example",
                    "a@contoso.example#x", "a@contoso.example\n", None, 5, "x" * 70 + "@contoso.example"):
            with self.subTest(sender=bad):
                with self.assertRaises(ValueError):
                    mail_calls(bad)
                with self.assertRaises(ValueError):
                    Mailer(bad, None, None, PEOPLE, MemoryStore(), lambda: NOW, Redactor(), lambda: "x")  # type: ignore[arg-type]

    def test_the_resource_of_the_token_is_graph(self):
        self.assertEqual(GRAPH_RESOURCE, "https://graph.microsoft.com")


class TheMessage(unittest.TestCase):
    def test_the_exact_json_the_address_and_the_token_that_are_sent(self):
        fixture = Fixture()
        result = fixture.send(kind="approval", plan_id="p1a2b3")
        self.assertEqual(result.status, "sent")
        self.assertEqual(len(fixture.graph.calls), 1)
        call = fixture.graph.calls[0]
        self.assertEqual((call["method"], call["url"]), ("POST", URL))
        self.assertEqual(call["headers"]["Authorization"], f"Bearer {JWT}")
        self.assertEqual(call["headers"]["Content-Type"], "application/json")
        self.assertEqual(call["body"], {
            "message": {"subject": LETTER.subject, "body": {"contentType": "HTML", "content": LETTER.html},
                        "toRecipients": [{"emailAddress": {"address": "maya@example.com"}}],
                        "internetMessageHeaders": [{"name": "x-ai-generated", "value": "true"}, {"name": "x-auto-response-suppress", "value": "All"}]},
            "saveToSentItems": True})
        self.assertEqual(fixture.tokens, ["https://graph.microsoft.com"])

    def test_graph_accepting_a_letter_is_not_delivery_and_the_result_says_so(self):
        result = Fixture().send()
        self.assertEqual(result, MailResult("sent", "Graph accepted the letter (202). That is not delivery: only receipt in the inbox shows that it arrived."))
        self.assertIn("receipt", mail.__doc__)
        self.assertIn("not by this call", Mailer.send.__doc__)

    def test_the_recipient_is_the_address_of_the_list_and_only_that_one(self):
        fixture = Fixture()
        noor = Person(NOOR, "Noor", ("approver",), "NOOR@example.com")
        self.assertEqual(fixture.send(noor).status, "sent")
        body = fixture.graph.calls[0]["body"]
        self.assertEqual(body["message"]["toRecipients"], [{"emailAddress": {"address": "Noor@Example.com"}}])
        self.assertEqual(set(body), {"message", "saveToSentItems"})
        self.assertEqual(set(body["message"]), {"subject", "body", "toRecipients", "internetMessageHeaders"})
        self.assertIn("other@example.org", body["message"]["body"]["content"], "an address in the text of a letter is only text")

    def test_the_outcome_is_written_and_nothing_of_the_letter_but_its_subject(self):
        fixture = Fixture(now=NOW)
        fixture.send(kind="approval", plan_id="p1a2b3")
        self.assertEqual(fixture.records, [MailRecord(mail_id="m1", oid=MAYA, kind="approval", subject=LETTER.subject, sent_at="2026-11-05T10:18:00Z", status="sent",
                                                      plan_id="p1a2b3", detail="Graph accepted the letter (202). That is not delivery: only receipt in the inbox shows that it arrived.")])
        stored = fixture.records[0].to_json()
        for secret in (JWT, "The body", "<p>", "maya@example.com", "other@example.org"):
            self.assertNotIn(secret, stored)
        self.assertEqual(len(fixture.store.mails), 1)
        for table in (fixture.store.runs, fixture.store.cases, fixture.store.plans, fixture.store.decisions, fixture.store.actions, fixture.store.notes, fixture.store.nonces):
            self.assertEqual(len(table), 0)
        self.assertEqual(fixture.store.settings, {})

    def test_a_person_that_is_written_with_another_case_still_gets_the_address_of_the_list(self):
        fixture = Fixture()
        self.assertEqual(fixture.send(Person(MAYA.upper(), "Maya", (), " MAYA@EXAMPLE.COM ")).status, "sent")
        self.assertEqual(fixture.graph.calls[0]["body"]["message"]["toRecipients"][0]["emailAddress"]["address"], "maya@example.com")

    def test_the_clock_decides_the_time_of_the_record_also_when_it_is_not_utc_or_has_no_zone(self):
        zoned = Fixture(now=dt.datetime(2026, 11, 5, 11, 18, tzinfo=dt.timezone(dt.timedelta(hours=1))))
        zoned.send()
        self.assertEqual(zoned.records[0].sent_at, "2026-11-05T10:18:00Z")
        naive = Fixture(now=dt.datetime(2026, 11, 5, 10, 18))
        naive.send()
        self.assertEqual(naive.records[0].sent_at, "2026-11-05T10:18:00Z")


class Refusals(unittest.TestCase):
    def refused(self, fixture, result, record_detail):
        self.assertEqual(result.status, "refused")
        self.assertIn(record_detail, result.detail)
        fixture.untouched(self)
        self.assertEqual([(r.status, r.detail) for r in fixture.records], [("refused", result.detail)])

    def test_a_person_without_an_address(self):
        fixture = Fixture()
        self.refused(fixture, fixture.send(PEOPLE.persons[2]), "no address")
        fixture = Fixture()
        self.refused(fixture, fixture.send(Person(MAYA, "Maya", (), "")), "no address")
        fixture = Fixture()
        self.refused(fixture, fixture.send(Person(MAYA, "Maya", (), "   ")), "no address")

    def test_an_address_that_is_not_on_the_list(self):
        fixture = Fixture()
        self.refused(fixture, fixture.send(Person(STRANGER, "Eve", ("owner",), "eve@example.org")), "not on the list")
        self.assertEqual(fixture.records[0].oid, STRANGER)

    def test_a_person_that_the_list_does_not_hold_for_that_address(self):
        fixture = Fixture()
        self.refused(fixture, fixture.send(Person(STRANGER, "Eve", ("owner",), "maya@example.com")), "not the person")
        fixture = Fixture()
        self.refused(fixture, fixture.send(Person(MAYA, "Maya", ("owner",), "noor@example.com")), "not the person")

    def test_a_kind_that_is_not_a_kind(self):
        for kind in ("", "Digest", "a b", "x" * 40, "1abc", "digest\n", None, 5):
            with self.subTest(kind=kind):
                fixture = Fixture()
                self.refused(fixture, fixture.send(kind=kind), "kind of letter")
                self.assertEqual(fixture.records[0].kind, "unknown")

    def test_a_subject_that_is_empty_or_not_one_line(self):
        for subject in ("", "   ", "[Meternaut] a\nb", "[Meternaut] a\r\nBcc: x@example.org", "[Meternaut] a\x00"):
            with self.subTest(subject=subject):
                fixture = Fixture()
                self.refused(fixture, fixture.send(letter=Letter(subject, "<p>x</p>", "x")), "subject")

    def test_the_refusals_come_before_the_holds(self):
        fixture = Fixture()
        fixture.store.switch_put(SwitchRecord(name="all", paused=True))
        self.assertEqual(fixture.send(Person(STRANGER, "Eve", (), "eve@example.org")).status, "refused")


class Holds(unittest.TestCase):
    def held(self, fixture, result, words):
        self.assertEqual(result.status, "held")
        self.assertIn(words, result.detail)
        fixture.untouched(self)
        self.assertEqual([(r.status, r.detail) for r in fixture.records], [("held", result.detail)])

    def test_a_pulled_switch_holds_the_letter(self):
        for name in ("messages", "all"):
            with self.subTest(switch=name):
                fixture = Fixture()
                fixture.store.switch_put(SwitchRecord(name=name, paused=True))
                self.held(fixture, fixture.send(), f'The switch "{name}" is pulled.')

    def test_a_switch_that_is_not_pulled_and_the_switch_of_changes_do_not(self):
        fixture = Fixture()
        fixture.store.switch_put(SwitchRecord(name="messages", paused=False))
        fixture.store.switch_put(SwitchRecord(name="changes", paused=True))
        self.assertEqual(fixture.send().status, "sent")

    def test_a_switch_that_cannot_be_read_counts_as_pulled(self):
        class Broken(MemoryStore):
            def __init__(self, failing, **kw):
                super().__init__(**kw)
                self.failing = failing

            def switch_get(self, name):
                if name in self.failing:
                    raise StoreError("the table is not reachable")
                return super().switch_get(name)

        for failing in (("messages",), ("all",), ("messages", "all")):
            for kind in ("reminder", *BUDGET_FREE_KINDS):
                with self.subTest(failing=failing, kind=kind):
                    fixture = Fixture(store=Broken(failing))
                    self.held(fixture, fixture.send(kind=kind), "could not be read, so it counts as pulled")

    def test_paused_messages_hold_the_letter_until_the_time_has_come(self):
        fixture = Fixture()
        fixture.settings(paused_until="2026-11-05T10:18:01Z")
        self.held(fixture, fixture.send(), "paused messages until 2026-11-05T10:18:01Z")
        for until in ("2026-11-05T10:18:00Z", "2026-11-05T10:17:59Z", "2026-01-01T00:00:00Z", None):
            with self.subTest(until=until):
                fixture = Fixture()
                fixture.settings(paused_until=until)
                self.assertEqual(fixture.send().status, "sent")

    def test_a_pause_that_cannot_be_read_holds_the_letter(self):
        fixture = Fixture()
        fixture.settings(paused_until="next week")
        self.held(fixture, fixture.send(), "cannot be read")

    def test_a_pulled_switch_and_the_pause_hold_the_letters_that_the_budget_leaves_free(self):
        for kind in BUDGET_FREE_KINDS:
            with self.subTest(kind=kind, held_by="the pause"):
                fixture = Fixture()
                fixture.settings(paused_until="2026-12-01T00:00:00Z")
                self.held(fixture, fixture.send(kind=kind), "paused messages")
            with self.subTest(kind=kind, held_by="the switch"):
                fixture = Fixture()
                fixture.store.switch_put(SwitchRecord(name="messages", paused=True))
                self.held(fixture, fixture.send(kind=kind), 'The switch "messages" is pulled.')

    def test_the_weekly_budget_counts_the_sent_letters_of_this_iso_week(self):
        fixture = Fixture()
        fixture.settings(weekly_budget=2)
        fixture.sent_before(1, "reminder", MONDAY)
        fixture.sent_before(1, "reminder", "2026-11-04T09:00:00Z")
        for kind in BUDGET_FREE_KINDS:  # a letter of a free kind is not counted
            fixture.sent_before(2, kind, "2026-11-04T10:00:00Z")
        self.held(fixture, fixture.send(kind="reminder"), "weekly budget of 2 messages is reached (2 sent since Monday)")

    def test_a_letter_under_the_budget_is_sent(self):
        fixture = Fixture()
        fixture.settings(weekly_budget=2)
        fixture.sent_before(1, "reminder", MONDAY)
        self.assertEqual(fixture.send(kind="reminder").status, "sent")

    def test_only_letters_with_the_status_sent_count_and_only_the_letters_of_this_person(self):
        fixture = Fixture()
        fixture.settings(weekly_budget=1)
        for status in ("held", "refused", "failed"):
            fixture.sent_before(2, "reminder", "2026-11-04T09:00:00Z", status)
        fixture.sent_before(5, "reminder", "2026-11-04T09:00:00Z", "sent", oid=NOOR)
        self.assertEqual(fixture.send(kind="reminder").status, "sent")
        self.assertEqual(fixture.send(kind="reminder").status, "held", "the letter that was sent now counts")

    def test_the_week_begins_on_monday_at_midnight_utc(self):
        monday = dt.datetime(2026, 11, 9, 0, 0, 30, tzinfo=dt.timezone.utc)
        for sent_at, expected in (("2026-11-08T23:59:59Z", "sent"), ("2026-11-09T00:00:00Z", "held"), ("2026-11-02T10:00:00Z", "sent")):
            with self.subTest(sent_at=sent_at):
                fixture = Fixture(now=monday)
                fixture.settings(weekly_budget=1)
                fixture.sent_before(1, "reminder", sent_at)
                self.assertEqual(fixture.send(kind="reminder").status, expected)

    def test_the_week_is_the_week_in_utc_whatever_the_zone_of_the_clock(self):
        sunday_night_utc = dt.datetime(2026, 11, 9, 0, 30, tzinfo=dt.timezone(dt.timedelta(hours=2)))  # Monday 00:30 at +02:00, Sunday 22:30 UTC
        fixture = Fixture(now=sunday_night_utc)
        fixture.settings(weekly_budget=1)
        fixture.sent_before(1, "reminder", "2026-11-08T21:00:00Z")
        self.assertEqual(fixture.send(kind="reminder").status, "held")

    def test_the_free_kinds_are_pinned_and_each_is_neither_held_by_the_budget_nor_counted_against_it(self):
        self.assertEqual(BUDGET_FREE_KINDS, ("approval", "first_contact", "notice", "verified", "digest", "alert"))
        for kind in BUDGET_FREE_KINDS:
            with self.subTest(kind=kind, what="not held when the budget is used up"):
                fixture = Fixture()
                fixture.settings(weekly_budget=1)
                fixture.sent_before(3, "reminder", MONDAY)
                self.assertEqual(fixture.send(kind=kind).status, "sent")
            with self.subTest(kind=kind, what="not held when the budget is nothing"):
                fixture = Fixture()
                fixture.settings(weekly_budget=0)
                self.assertEqual(fixture.send(kind=kind).status, "sent")
            with self.subTest(kind=kind, what="not counted"):
                fixture = Fixture()
                fixture.settings(weekly_budget=1)
                fixture.sent_before(4, kind, MONDAY)
                self.assertEqual(fixture.send(kind="reminder").status, "sent")

    def test_free_letters_sent_one_after_the_other_leave_the_budget_whole_and_are_still_sent_when_it_is_used_up(self):
        fixture = Fixture()
        fixture.settings(weekly_budget=1)
        for kind in BUDGET_FREE_KINDS:
            self.assertEqual(fixture.send(kind=kind).status, "sent", kind)
        self.assertEqual(fixture.send(kind="reminder").status, "sent")
        self.assertEqual(fixture.send(kind="reminder").status, "held", "the one reminder used the budget of one")
        for kind in BUDGET_FREE_KINDS:
            self.assertEqual(fixture.send(kind=kind).status, "sent", f"{kind} goes although the budget is used up")
        free = len(BUDGET_FREE_KINDS)
        self.assertEqual([r.status for r in fixture.records], ["sent"] * (free + 1) + ["held"] + ["sent"] * free)

    def test_a_budget_of_nothing_leaves_the_weekly_desk_and_holds_the_other_kinds(self):
        fixture = Fixture()
        fixture.settings(weekly_budget=0)
        self.assertEqual(fixture.send(kind="digest").status, "sent")
        self.assertEqual(fixture.send(kind="reminder").status, "held")
        self.assertIn("The weekly budget of 0 messages is reached (0 sent since Monday).", fixture.records[-1].detail)
        paused = Fixture()
        paused.settings(weekly_budget=0, paused_until="2026-12-01T00:00:00Z")
        self.held(paused, paused.send(kind="digest"), "paused messages")
        pulled = Fixture()
        pulled.settings(weekly_budget=0)
        pulled.store.switch_put(SwitchRecord(name="all", paused=True))
        self.held(pulled, pulled.send(kind="digest"), 'The switch "all" is pulled.')
        desk = Fixture()
        desk.settings(weekly_budget=0, channel="desk")
        self.assertEqual(desk.send(kind="digest").status, "sent")
        self.assertEqual(desk.send(kind="reminder").status, "held")

    def test_the_text_says_which_kinds_the_budget_leaves_free_and_that_any_other_kind_counts(self):
        for text in (mail.__doc__, Mailer.send.__doc__):
            for kind in BUDGET_FREE_KINDS:
                self.assertIn(kind, text)
            self.assertIn("BUDGET_FREE_KINDS", text)
            self.assertIn("budget of 0", " ".join(text.split()))
        text = " ".join(mail.__doc__.split())
        self.assertIn("is valid and counts against the weekly budget", text)
        self.assertIn("the weekly budget neither counts nor holds any of these six", text)
        self.assertNotIn("counts like a notice", text)
        self.assertIn("the weekly desk (the digest) still goes", " ".join(Mailer.send.__doc__.split()))

    def test_the_default_budget_of_a_person_with_no_settings_is_three(self):
        fixture = Fixture()
        fixture.sent_before(3, "reminder", MONDAY)
        self.assertEqual(fixture.send(kind="reminder").status, "held")
        fixture = Fixture()
        fixture.sent_before(2, "reminder", MONDAY)
        self.assertEqual(fixture.send(kind="reminder").status, "sent")

    def test_a_person_of_the_weekly_desk_gets_the_digest_and_nothing_else(self):
        for kind in ("approval", "first_contact", "notice", "verified", "reminder"):
            with self.subTest(kind=kind):
                fixture = Fixture()
                fixture.settings(channel="desk")
                self.held(fixture, fixture.send(kind=kind), "weekly desk only")
        fixture = Fixture()
        fixture.settings(channel="desk")
        self.assertEqual(fixture.send(kind="digest").status, "sent")
        for channel in ("email", "teams"):
            for kind in ("notice", "reminder"):
                fixture = Fixture()
                fixture.settings(channel=channel)
                self.assertEqual(fixture.send(kind=kind).status, "sent")

    def test_the_checks_run_in_the_order_of_the_rules(self):
        fixture = Fixture()
        fixture.settings(paused_until="2026-12-01T00:00:00Z", weekly_budget=0, channel="desk")
        fixture.store.switch_put(SwitchRecord(name="messages", paused=True))
        fixture.store.switch_put(SwitchRecord(name="all", paused=True))
        reasons = [fixture.send(kind="reminder").detail]
        fixture.store.switch_put(SwitchRecord(name="messages", paused=False))
        reasons.append(fixture.send(kind="reminder").detail)
        fixture.store.switch_put(SwitchRecord(name="all", paused=False))
        reasons.append(fixture.send(kind="reminder").detail)
        fixture.settings(weekly_budget=0, channel="desk")
        reasons.append(fixture.send(kind="reminder").detail)
        free = fixture.send(kind="notice").detail  # the budget skips a free kind, so the next check is the desk
        fixture.settings(weekly_budget=5, channel="desk")
        reasons.append(fixture.send(kind="reminder").detail)
        for reason, words in zip(reasons, ('The switch "messages" is pulled.', 'The switch "all" is pulled.', "paused messages until 2026-12-01T00:00:00Z",
                                           "The weekly budget of 0 messages is reached", "This person gets the weekly desk only.")):
            self.assertIn(words, reason)
        self.assertIn("This person gets the weekly desk only.", free)
        self.assertEqual(len(fixture.graph.calls), 0)

    def test_settings_or_records_that_cannot_be_read_hold_the_letter(self):
        class NoSettings(MemoryStore):
            def settings_get(self, oid):
                raise StoreError("down")

        class NoRecords(MemoryStore):
            def mails_since(self, oid, since):
                raise StoreError("down")

        for kind in ("reminder", *BUDGET_FREE_KINDS):
            with self.subTest(kind=kind, unreadable="the settings"):
                fixture = Fixture(store=NoSettings())
                self.held(fixture, fixture.send(kind=kind), "could not be read, so nothing was sent")
        fixture = Fixture(store=NoRecords())
        self.held(fixture, fixture.send(kind="reminder"), "could not be read, so nothing was sent")
        for kind in BUDGET_FREE_KINDS:
            with self.subTest(kind=kind, unreadable="the record of the week"):
                fixture = Fixture(store=NoRecords())
                self.assertEqual(fixture.send(kind=kind).status, "sent", f"a {kind} letter needs no record of the week")


class Failures(unittest.TestCase):
    def test_an_error_of_graph_is_a_failed_send_with_its_redacted_text(self):
        for secret in (JWT, PLAIN):
            with self.subTest(secret=secret[:8]):
                fixture = Fixture(error_answer(403, "ErrorAccessDenied", f"Access is denied for the token {secret} of the app"),
                                  token=lambda resource, secret=secret: secret)
                result = fixture.send()
                self.assertEqual(result.status, "failed")
                self.assertIn("403 ErrorAccessDenied: Access is denied for the token", result.detail)
                self.assertNotIn(secret, result.detail)
                self.assertIn(REDACTED, result.detail)
                self.assertNotIn(secret, fixture.records[0].to_json())
                self.assertEqual(fixture.records[0].status, "failed")
                self.assertNotIn("Sent Items", result.detail, "a 403 sent nothing")

    def test_a_throttled_call_is_tried_again_once_graph_has_said_how_long_to_wait(self):
        fixture = Fixture((429, {"retry-after": "3"}, b'{"error":{"code":"ApplicationThrottled","message":"slow down"}}'), (202, {}, b""))
        self.assertEqual(fixture.send().status, "sent")
        self.assertEqual([c["url"] for c in fixture.graph.calls], [URL, URL])
        self.assertEqual(fixture.sleeps, [3.0])
        self.assertEqual(len(fixture.records), 1)

    def test_a_throttled_call_that_stays_throttled_fails_after_the_retries(self):
        fixture = Fixture(error_answer(429, "ApplicationThrottled", "slow down"))
        result = fixture.send()
        self.assertEqual(result.status, "failed")
        self.assertIn("429 ApplicationThrottled", result.detail)
        self.assertEqual(len(fixture.graph.calls), 3)

    def test_a_letter_that_may_have_been_taken_is_never_sent_again_by_the_mailer(self):
        for answer in (error_answer(500), error_answer(502), error_answer(503), error_answer(504), OSError("reset"), TimeoutError("slow")):
            with self.subTest(answer=repr(answer)[:40]):
                fixture = Fixture(answer)
                result = fixture.send()
                self.assertEqual(result.status, "failed")
                self.assertEqual(len(fixture.graph.calls), 1, "one call, no retry")
                self.assertEqual(fixture.sleeps, [])
                self.assertIn("look at the Sent Items of the mailbox before it is sent again", result.detail)
                self.assertEqual(fixture.records[0].status, "failed")

    def test_an_error_of_the_client_sent_nothing_and_says_so_by_not_warning(self):
        for status in (400, 401, 404):
            with self.subTest(status=status):
                fixture = Fixture(error_answer(status, "BadThing", "no"))
                result = fixture.send()
                self.assertEqual((result.status, len(fixture.graph.calls)), ("failed", 1))
                self.assertIn(f"{status} BadThing: no", result.detail)
                self.assertNotIn("Sent Items", result.detail)

    def test_a_token_that_cannot_be_had_stops_the_send_before_any_call(self):
        def refuse(resource):
            raise RuntimeError(f"the endpoint answered 500 for Bearer {JWT}")

        fixture = Fixture(token=refuse)
        result = fixture.send()
        self.assertEqual(result.status, "failed")
        self.assertIn("No token for Graph: RuntimeError", result.detail)
        self.assertNotIn(JWT, result.detail + fixture.records[0].detail)
        self.assertEqual(fixture.graph.calls, [])

    def test_an_answer_that_is_not_a_token_stops_the_send_before_any_call(self):
        for bad in ("", None, 5, "a b", "tok\r\nBcc: x@example.org", "tok\x00"):
            with self.subTest(token=bad):
                fixture = Fixture(token=lambda resource, bad=bad: bad)
                result = fixture.send()
                self.assertEqual(result.status, "failed")
                self.assertIn("not a token", result.detail)
                self.assertEqual(fixture.graph.calls, [])

    def test_a_call_that_the_list_does_not_allow_is_a_failed_send_and_never_leaves(self):
        fixture = Fixture(allowed=())
        result = fixture.send()
        self.assertEqual(result.status, "failed")
        self.assertIn("the app makes no POST call to graph.microsoft.com", result.detail)
        self.assertEqual(fixture.graph.calls, [])
        other = Fixture(allowed=mail_calls("someone-else@contoso.example"))
        self.assertEqual(other.send().status, "failed")
        self.assertEqual(other.graph.calls, [])

    def test_a_record_that_cannot_be_written_does_not_make_the_caller_send_again(self):
        class NoRecords(MemoryStore):
            def mail_put(self, mail_record):
                raise StoreError("down")

        fixture = Fixture(store=NoRecords())
        result = fixture.send()
        self.assertEqual(result.status, "sent")
        self.assertIn("The record of it could not be written.", result.detail)
        self.assertEqual(len(fixture.graph.calls), 1)
        held = Fixture(store=NoRecords())
        held.store.switch_put(SwitchRecord(name="all", paused=True))
        self.assertEqual(held.send().status, "held")

    def test_a_long_detail_is_cut(self):
        fixture = Fixture(error_answer(400, "Bad", "x" * 5000))
        self.assertLessEqual(len(fixture.send().detail), mail.MAX_DETAIL)
        self.assertLessEqual(len(fixture.records[0].detail), mail.MAX_DETAIL)


class EverySend(unittest.TestCase):
    def test_whatever_happens_the_only_call_is_the_post_to_the_sender(self):
        calls = []
        scenes = [(), ((202, {}, b""),), (error_answer(403),), (error_answer(500),), (OSError("x"),), (error_answer(429),)]
        for answers in scenes:
            for kind in ("reminder", *BUDGET_FREE_KINDS):
                fixture = Fixture(*answers)
                fixture.send(kind=kind)
                fixture.send(PEOPLE.persons[1], kind=kind)
                fixture.send(Person(STRANGER, "Eve", (), "eve@example.org"), kind=kind)
                calls += [(c["method"], c["url"]) for c in fixture.graph.calls]
        self.assertTrue(calls)
        self.assertEqual(set(calls), {("POST", URL)})

    def test_every_send_writes_one_record_and_one_only(self):
        fixture = Fixture()
        fixture.send(kind="digest")
        fixture.send(kind="notice")
        fixture.send(Person(STRANGER, "Eve", (), "eve@example.org"))
        fixture.store.switch_put(SwitchRecord(name="messages", paused=True))
        fixture.send(kind="approval", plan_id="p1")
        self.assertEqual([(r.mail_id, r.status, r.kind, r.plan_id) for r in fixture.records],
                         [("m1", "sent", "digest", None), ("m2", "sent", "notice", None), ("m3", "refused", "digest", None), ("m4", "held", "approval", "p1")])

    def test_the_record_of_a_letter_that_is_held_has_the_time_of_the_attempt(self):
        fixture = Fixture(now=dt.datetime(2026, 11, 6, 8, 5, 9, tzinfo=dt.timezone.utc))
        fixture.store.switch_put(SwitchRecord(name="all", paused=True))
        fixture.send()
        self.assertEqual(fixture.records[0].sent_at, "2026-11-06T08:05:09Z")

    def test_the_plan_id_is_kept_short(self):
        fixture = Fixture()
        fixture.send(kind="approval", plan_id="p" * 500)
        self.assertEqual(len(fixture.records[0].plan_id), 64)


if __name__ == "__main__":
    unittest.main()
