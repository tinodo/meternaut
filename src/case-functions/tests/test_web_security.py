import re
import unittest

from test_web_support import (HOST, MAYA, OPS, OWNER, STRANGER, TINO, XSS, XSS_ESCAPED, Console, FailingStore, make_action, make_case, make_decision, make_plan, make_run, at,
                              snapshot)

from cases.models import ActionRecord, DecideResult, NoteRecord, SettingsRecord, SwitchRecord
from cases.people import People, Person
from cases.web import Request, handle, parse_request

FORM = "application/x-www-form-urlencoded"
REQUIRED = {
    "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; frame-ancestors 'none'; base-uri 'none'",
    "X-Frame-Options": "DENY",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "same-origin",
    "Cache-Control": "no-store",
}
GET_PATHS = ["/", "/ok/plan0001", "/why/case0001", "/history", "/history?run=run00001", "/me/decisions", "/me/activity", "/me/settings", "/me/notes",
             "/ops/permissions", "/ops/pause"]


def seeded() -> Console:
    console = Console()
    console.seed()
    console.store.action_put(make_action())
    console.store.decision_put(make_decision())
    return console


def active_content(reply) -> list[str]:
    """Everything in a page that could run or load something: scripts, event handlers, frames, scripted or outside addresses."""
    problems = []
    for node in reply.root.walk():
        if node.tag in ("script", "iframe", "object", "embed", "base", "frame", "applet", "svg", "canvas", "img", "video", "audio"):
            problems.append(f"<{node.tag}>")
        if node.tag == "link" or (node.tag == "meta" and node.attrs.get("http-equiv")):
            problems.append(f"<{node.tag}>")
        for name, value in node.attrs.items():
            if name.startswith("on"):
                problems.append(f"{name} on <{node.tag}>")
            if name in ("href", "src", "action", "formaction", "data", "poster", "srcset"):
                target = value.strip().lower()
                if target.startswith(("javascript:", "data:", "vbscript:", "http:", "https:", "//", "ftp:")):
                    problems.append(f"{name}={value}")
    return problems


class Headers(unittest.TestCase):
    def check(self, reply, content_type: str = "text/html; charset=utf-8"):
        for name, value in REQUIRED.items():
            self.assertEqual(reply.headers.get(name), value, f"{name} on a {reply.status} response")
        self.assertEqual(reply.headers.get("Content-Type"), content_type)

    def test_every_page_carries_the_headers_and_a_content_type_with_a_charset(self):
        console = seeded()
        for path in GET_PATHS:
            with self.subTest(path=path):
                reply = console.get(path)
                self.assertEqual(reply.status, 200)
                self.check(reply)

    def test_a_browser_sends_the_origin_of_the_console_on_a_post_and_no_referrer_to_another_site(self):
        # Under "no-referrer" a browser sends `Origin: null` on every form POST (Fetch standard), and the platform's sign-in answers an authenticated POST that carries it with an
        # empty 403 before the app is reached: the approve button failed on 2026-11-05 (AGENTS.md rule 28). Neither the Python harness nor the Hub's check sends such a request,
        # so this test is what holds the policy. A form or a page that sets its own policy has the same effect, so none may.
        console = seeded()
        for path in GET_PATHS:
            with self.subTest(path=path):
                reply = console.get(path)
                policy = reply.headers.get("Referrer-Policy")
                self.assertEqual(policy, "same-origin")
                self.assertNotIn(policy, (None, "", "no-referrer", "same-origin, no-referrer"))
                for node in reply.root.walk():
                    if node.tag == "form":
                        self.assertNotIn("rel", node.attrs, "a form with rel=noreferrer sends Origin: null too")
                        self.assertNotIn("referrerpolicy", node.attrs)
                    if node.tag == "meta":
                        self.assertNotEqual(node.attrs.get("name", "").lower(), "referrer", "a page may not set a policy of its own")
        self.assertEqual(console.post("/me/notes", {}).headers.get("Referrer-Policy"), "same-origin", "the answer to a POST carries it too")

    def test_the_errors_carry_them_too(self):
        console = seeded()
        replies = {
            "no sign-in": console.get("/", oid=None),
            "not listed": console.get("/", oid=STRANGER),
            "not found": console.get("/nothing"),
            "wrong method": console.post("/", {}),
            "wrong role": console.get("/ops/pause", oid=MAYA),
            "too large": console.post("/me/notes", body=b"x=" + b"a" * 20000),
            "not a form": console.send("POST", "/me/notes", body="x", content_type="text/plain"),
            "cross-site": console.send("POST", "/me/notes", form={"a": "b"}, headers={"Sec-Fetch-Site": "cross-site"}),
            "no token": console.post("/me/settings", {}),
            "not your request": console.get("/ok/plan0001", oid=MAYA),
            "no such request": console.get("/ok/nothing"),
            "no such case": console.get("/why/nothing"),
        }
        for name, reply in replies.items():
            with self.subTest(name=name):
                self.assertGreaterEqual(reply.status, 400)
                self.check(reply)

    def test_the_health_probe_and_the_download_carry_them_with_their_own_content_types(self):
        console = seeded()
        probe = console.get("/healthz", oid=None)
        self.check(probe, "text/plain; charset=utf-8")
        form = console.get("/me/settings").form("/me/settings/export")
        download = console.submit(form)
        self.assertEqual(download.status, 200)
        self.check(download, "application/json; charset=utf-8")

    def test_a_fault_of_the_store_is_a_plain_page_with_the_headers(self):
        console = Console(store=FailingStore(fail={"plans_open", "runs_recent"}))
        reply = console.get("/", )
        self.assertEqual(reply.status, 200, "the start page shows what it can read and says what it cannot")
        console = Console(store=FailingStore(fail={"case_get"}))
        reply = console.get("/why/case0001")
        self.assertEqual(reply.status, 503)
        self.check(reply)
        self.assertNotIn("Traceback", reply.text)
        self.assertNotIn("the store is down", reply.text)

    def test_a_bug_is_a_500_page_without_a_trace(self):
        console = seeded()
        console.store.case_get = lambda case_id: 1 / 0  # type: ignore[assignment]
        reply = console.get("/why/case0001")
        self.assertEqual(reply.status, 500)
        self.check(reply)
        self.assertNotIn("division", reply.text)
        self.assertNotIn("Traceback", reply.text)
        self.assertIn("Something went wrong on my side", reply.content)


class NoActiveContent(unittest.TestCase):
    def test_no_page_has_a_script_a_handler_a_frame_or_an_address_outside_the_console(self):
        console = seeded()
        console.store.note_put(NoteRecord("n1", TINO, "note", "text", f"/subscriptions/{'1' * 8}-1111-1111-1111-{'1' * 12}/resourceGroups/g/providers/p.q/t/n", "x", "you", at(days=-1), at(days=9), 0))
        for path in GET_PATHS + ["/nothing"]:
            for oid in (TINO, MAYA, OWNER, OPS):
                with self.subTest(path=path, oid=oid):
                    reply = console.get(path, oid=oid)
                    self.assertEqual(active_content(reply), [])
                    self.assertNotIn("<script", reply.text.lower())
                    self.assertEqual(reply.problems, [])

    def test_the_style_loads_nothing(self):
        reply = seeded().get("/")
        style = "".join(child for child in reply.root.find("style").children if isinstance(child, str))
        self.assertNotIn("url(", style)
        self.assertNotIn("@import", style)
        self.assertNotIn("http", style)

    def test_the_only_links_are_to_pages_of_the_console_and_to_the_people_who_can_be_written_to(self):
        reply = seeded().get("/ok/plan0001")
        for href in reply.links():
            self.assertRegex(href, r"^(/|#|mailto:)")


class SignIn(unittest.TestCase):
    def test_no_header_is_a_short_403_that_says_nothing_about_the_system(self):
        console = seeded()
        reply = console.get("/ok/plan0001", oid=None)
        self.assertEqual(reply.status, 403)
        self.assertEqual(reply.content, "No access This account cannot open this page.")
        self.assertIsNone(reply.root.find("nav"))
        self.assertIsNone(reply.root.find("footer"))
        self.assertEqual(reply.links(), [])
        for word in ("Meternaut", "plan", "approve", "runner", "console"):
            self.assertNotIn(word.lower(), reply.content.lower())

    def test_an_object_id_that_is_not_in_the_list_gets_the_same_page(self):
        console = seeded()
        nobody = console.get("/", oid=None)
        stranger = console.get("/", oid=STRANGER)
        self.assertEqual((stranger.status, stranger.text), (nobody.status, nobody.text))
        for path in GET_PATHS:
            with self.subTest(path=path):
                self.assertEqual(console.get(path, oid=STRANGER).status, 403)

    def test_a_name_in_the_headers_is_not_enough(self):
        console = seeded()
        reply = console.get("/", oid=None, headers={"x-ms-client-principal-name": "tino@example.com", "x-ms-client-principal": "e30="})
        self.assertEqual(reply.status, 403)

    def test_a_person_is_never_read_from_a_form_or_a_link(self):
        console = seeded()
        self.assertEqual(console.get("/", oid=STRANGER, query={"oid": TINO, "x-ms-client-principal-id": TINO}).status, 403)
        self.assertEqual(console.post("/me/notes", {"oid": TINO, "x-ms-client-principal-id": TINO}, oid=STRANGER).status, 403)
        reply = console.get("/me/settings", oid=MAYA, query={"oid": TINO, "name": "Tino"})
        self.assertIn("Signed in as Maya.", reply.content)
        self.assertNotIn("Signed in as Tino", reply.content)

    def test_the_object_id_is_compared_without_regard_to_case(self):
        console = seeded()
        reply = console.get("/", oid=TINO.upper())
        self.assertEqual(reply.status, 200)
        self.assertIn("Signed in as Tino.", reply.content)

    def test_the_health_probe_needs_no_sign_in_and_nothing_else_does_not(self):
        console = seeded()
        reply = console.get("/healthz", oid=None)
        self.assertEqual((reply.status, reply.text), (200, "ok"))
        self.assertEqual(console.send("HEAD", "/healthz", oid=None).body, b"")
        self.assertEqual(console.post("/healthz", {}, oid=None).status, 403)
        self.assertEqual(console.get("/health", oid=None).status, 403)

    def test_the_list_decides_who_is_in(self):
        console = Console(people=People((Person(MAYA, "Maya", ("approver",), ""),)))
        self.assertEqual(console.get("/", oid=MAYA).status, 200)
        self.assertEqual(console.get("/", oid=TINO).status, 403)


class Limits(unittest.TestCase):
    def test_a_body_over_16_kb_is_refused_and_changes_nothing(self):
        console = seeded()
        before = snapshot(console.store)
        reply = console.post("/me/notes", body=b"text=" + b"a" * (16 * 1024 + 1))
        self.assertEqual(reply.status, 413)
        self.assertIn("at most 16 KB", reply.content)
        self.assertEqual(snapshot(console.store), before)

    def test_a_body_of_exactly_16_kb_is_read(self):
        request = parse_request("POST", "/x", {"Content-Type": "application/x-www-form-urlencoded"}, b"a=" + b"b" * (16 * 1024 - 2))
        self.assertEqual(request.problem, "")
        self.assertEqual(len(request.form["a"]), 16 * 1024 - 2)
        self.assertEqual(parse_request("POST", "/x", {}, b"a" * (16 * 1024 + 1)).problem, "too_large")

    def test_a_form_with_too_many_fields_is_refused(self):
        console = seeded()
        reply = console.post("/me/notes", body="&".join(f"f{i}=1" for i in range(200)))
        self.assertEqual(reply.status, 400)

    def test_a_post_that_is_not_a_form_is_refused(self):
        console = seeded()
        before = snapshot(console.store)
        for content_type in ("text/plain", "application/json", "multipart/form-data; boundary=x", None):
            with self.subTest(content_type=content_type):
                reply = console.send("POST", "/me/notes", body="kind=note", content_type=content_type)
                self.assertEqual(reply.status, 415)
        self.assertEqual(snapshot(console.store), before)

    def test_a_post_from_another_site_is_refused(self):
        console = seeded()
        form = console.get("/me/settings").form("/me/settings", has_button="Save settings")
        before = snapshot(console.store)
        for site in ("cross-site", "same-site", "none"):
            with self.subTest(site=site):
                reply = console.send("POST", "/me/settings", form=form.fields, headers={"Sec-Fetch-Site": site})
                self.assertEqual(reply.status, 403)
        self.assertEqual(snapshot(console.store), before)
        self.assertEqual(console.send("POST", "/me/settings", form=form.fields, headers={"Sec-Fetch-Site": "same-origin"}).status, 200)

    def test_control_characters_and_text_that_hides_or_reorders_are_taken_out_of_the_input(self):
        request = parse_request("POST", "/x?q=a%00b", {"content-type": "application/x-www-form-urlencoded; charset=utf-8"},
                                b"note=a%00b%0Dc%0Ad%09e%1Bf%7Fg%C2%85h+++i%E2%80%AEj%E2%80%8Bk%EF%BB%BFl&nonce=%20%20tok%20%20")
        self.assertEqual(request.form["note"], "a b c d e f g h ijkl")
        self.assertEqual(request.form["nonce"], "tok")
        self.assertEqual(request.query["q"], "a b")

    def test_a_form_that_names_a_field_twice_joins_the_values(self):
        request = parse_request("POST", "/x", {"Content-Type": "application/x-www-form-urlencoded"}, b"working_days=1&working_days=3&other=x")
        self.assertEqual(request.form, {"working_days": "1,3", "other": "x"})

    def test_parse_request_reads_the_parts(self):
        request = parse_request("get", "https://h.example/api/ok/abc?run=r1&x=%C3%A9", {"X-MS-Client-Principal-Id": "ABC", "Accept": "text/html"}, None)
        self.assertEqual((request.method, request.path, request.query, request.body, request.form), ("GET", "/api/ok/abc", {"run": "r1", "x": "é"}, b"", {}))
        self.assertEqual(request.headers, {"x-ms-client-principal-id": "ABC", "accept": "text/html"})
        self.assertEqual(parse_request("GET", "", None, None).path, "/")
        self.assertEqual(parse_request("POST", "/a", {"content-type": FORM}, "a=1").form, {"a": "1"})
        self.assertEqual(parse_request("POST", "/a", {"content-type": FORM}, b"\xff\xfe=1&a=%FF").form["a"], "\ufffd")


class GetsChangeNothing(unittest.TestCase):
    def test_no_get_changes_a_record(self):
        console = seeded()
        console.store.settings_put(SettingsRecord(oid=TINO, channel="desk"))
        console.store.note_put(NoteRecord("n1", TINO, "note", "text", None, "x", "you", at(days=-1), at(days=9), 0))
        console.store.switch_put(SwitchRecord("changes", True, "Otto", at(minutes=-5), "drill"))
        before = snapshot(console.store)
        for path in GET_PATHS + ["/nothing", "/history?run=nothing", "/history?run=%3Cscript%3E"]:
            for oid in (TINO, MAYA, OWNER, OPS, STRANGER, None):
                with self.subTest(path=path, oid=oid):
                    console.get(path, oid=oid)
                    self.assertEqual(snapshot(console.store), before)
        self.assertEqual(console.decider.calls, [])
        self.assertEqual(console.decider.withdrawals, [])

    def test_a_head_request_is_a_get_without_a_body(self):
        console = seeded()
        before = snapshot(console.store)
        reply = console.send("HEAD", "/")
        self.assertEqual((reply.status, reply.body), (200, b""))
        self.assertEqual(reply.headers["Cache-Control"], "no-store")
        self.assertEqual(snapshot(console.store), before)
        self.assertEqual(console.send("HEAD", "/ops/pause", oid=MAYA).status, 403)


class Nonces(unittest.TestCase):
    """The forms of the console that do not go through the decider check their one-time token themselves."""

    def forms(self, console, who=TINO):
        settings = console.get("/me/settings", oid=who)
        return settings.form("/me/settings", has_button="Save settings"), settings.form("/me/settings/delete"), console.get("/me/notes", oid=who).form("/me/notes", has_button="Save")

    def test_a_missing_or_wrong_token_changes_nothing(self):
        console = seeded()
        save, delete, add = self.forms(console)
        console.store.note_put(NoteRecord("n1", TINO, "note", "text", None, "x", "you", at(days=-1), at(days=9), 0))
        before = snapshot(console.store)
        changed = {**save.fields, "channel": "desk"}
        for label, fields in (("none", {k: v for k, v in changed.items() if k != "nonce"}), ("empty", {**changed, "nonce": ""}), ("wrong", {**changed, "nonce": "x" * 32})):
            with self.subTest(label=label):
                reply = console.post("/me/settings", fields)
                self.assertEqual(reply.status, 403)
                self.assertIn("Nothing was changed", reply.content)
                self.assertEqual(snapshot(console.store), before)
        self.assertEqual(console.post("/me/settings/delete", {}).status, 403)
        self.assertEqual(console.post("/me/settings/delete", {"nonce": "nope"}).status, 403)
        self.assertEqual(console.post("/me/notes", {"kind": "note"}).status, 403)
        self.assertEqual(console.post("/me/notes/n1/delete", {}).status, 403)
        self.assertEqual(console.post("/ops/pause", {"name": "all", "action": "pause"}).status, 403)
        self.assertEqual(snapshot(console.store), before)

    def test_a_token_works_once(self):
        console = seeded()
        save, _, _ = self.forms(console)
        fields = {**save.fields, "channel": "desk"}
        self.assertEqual(console.post("/me/settings", fields).status, 200)
        self.assertEqual(console.store.settings_get(TINO).channel, "desk")
        console.store.settings_put(SettingsRecord(oid=TINO, channel="teams"))
        again = console.post("/me/settings", fields)
        self.assertEqual(again.status, 403)
        self.assertEqual(console.store.settings_get(TINO).channel, "teams", "a second use of the same token changed nothing")

    def test_a_token_is_bound_to_the_person(self):
        console = seeded()
        save, _, _ = self.forms(console, who=TINO)
        before = snapshot(console.store)
        reply = console.post("/me/settings", {**save.fields, "channel": "desk"}, oid=MAYA)
        self.assertEqual(reply.status, 403)
        self.assertEqual(snapshot(console.store), before)
        self.assertEqual(console.post("/me/settings", {**save.fields, "channel": "desk"}, oid=TINO).status, 200, "the token was not used up by the refusal")

    def test_a_token_is_bound_to_the_purpose(self):
        console = seeded()
        save, delete, add = self.forms(console)
        console.store.settings_put(SettingsRecord(oid=TINO, channel="teams"))
        before = snapshot(console.store)
        self.assertEqual(console.post("/me/settings/delete", {"nonce": save.fields["nonce"]}).status, 403)
        self.assertEqual(console.post("/me/settings", {**save.fields, "nonce": delete.fields["nonce"]}).status, 403)
        self.assertEqual(console.post("/me/notes", {**add.fields, "nonce": save.fields["nonce"], "resource_id": "x", "text": "t", "expires": "2026-12-01"}).status, 403)
        self.assertEqual(console.post("/ops/pause", {"name": "all", "action": "pause", "nonce": save.fields["nonce"]}).status, 403)
        self.assertEqual(snapshot(console.store), before)

    def test_a_token_runs_out(self):
        console = seeded()
        save, _, _ = self.forms(console)
        console.now = console.now.replace(day=console.now.day + 1)
        before = snapshot(console.store)
        self.assertEqual(console.post("/me/settings", {**save.fields, "channel": "desk"}).status, 403)
        self.assertEqual(snapshot(console.store), before)

    def test_a_form_gets_a_token_of_its_own_for_this_person_and_this_purpose(self):
        console = seeded()
        page = console.get("/me/settings")
        tokens = [f.fields["nonce"] for f in page.forms()]
        self.assertEqual(len(tokens), 3)
        self.assertEqual(len(set(tokens)), 3)
        self.assertTrue(console.store.nonce_use(tokens[0], TINO, "settings"))
        self.assertFalse(console.store.nonce_use(tokens[1], MAYA, "settings-export"))
        self.assertFalse(console.store.nonce_use(tokens[1], TINO, "settings"))
        self.assertTrue(console.store.nonce_use(tokens[1], TINO, "settings-export"))
        self.assertTrue(console.store.nonce_use(tokens[2], TINO, "settings-delete"))


class XssEverywhere(unittest.TestCase):
    """A payload that was stored in an estate, by a model, by a person or in the list of people is escaped on every page."""

    def console(self, state: str = "approved") -> Console:
        people = People((Person(TINO, "Tino " + XSS, ("owner", "approver", "ops"), "tino@example.com"), Person(MAYA, "Maya", ("approver",), "")))
        console = Console(people=people, writer=XSS, models=(XSS, "m2"))
        store = console.store
        store.run_put(make_run(trigger=XSS, notes=(XSS,), ok=False, reason=XSS))
        store.case_put(make_case(resource_name=XSS, resource_group=XSS, resource_type=XSS, subscription_id=XSS, resource_id=XSS, detector=XSS, summary=XSS,
                                 objections=(XSS,), guards=(XSS,), models={"detective": XSS, "skeptic": XSS}, recommendation=XSS, status=XSS,
                                 steps=({"step": XSS, "model": XSS, "promptTokens": XSS, "completionTokens": XSS, "ms": XSS, "ok": XSS, "note": XSS},),
                                 facts={XSS: XSS, "list": [XSS], "nested": {XSS: XSS}}, plan_id="plan0001", run_id="run00001"))
        store.case_put(make_case(case_id='odd"><b>id', resource_name="odd id", plan_id=None, run_id="run00001"))
        store.plan_put(make_plan(title=XSS, what_changes=XSS, could_go_wrong=XSS, undo=XSS, evidence_level=XSS, resource_name=XSS, resource_group=XSS, resource_id=XSS,
                                 code="7F3K92QD", family=XSS, approvers=(TINO, MAYA), state=state))
        store.action_put(ActionRecord("plan0001", "case0001", XSS, XSS, "queued", at(minutes=-1), start_after=at(minutes=1), result=XSS, error=XSS,
                                      verification={"note": XSS, "gone": True, XSS: XSS}, correlation_id=XSS))
        store.decision_put(make_decision(note=XSS, approver_name=XSS, plan_code=XSS))
        store.note_put(NoteRecord("n1", TINO, "note", XSS, XSS, XSS, XSS, at(days=-1), at(days=9), 3))
        store.switch_put(SwitchRecord("changes", True, XSS, at(minutes=-5), XSS))
        return console

    def test_the_payload_is_escaped_on_every_page_and_never_becomes_a_tag_or_a_handler(self):
        console = self.console()
        shows_records = ["/", "/why/case0001", "/history", "/me/decisions", "/me/activity", "/me/notes", "/ops/pause", "/ops/permissions", "/ok/plan0001"]
        for path in GET_PATHS + ["/history?run=run00001"]:
            for oid in (TINO, MAYA):
                with self.subTest(path=path, oid=oid):
                    reply = console.get(path, oid=oid)
                    self.assertIn(reply.status, (200, 403))
                    self.assertNotIn(XSS, reply.text)
                    self.assertNotIn("<script", reply.text.lower())
                    self.assertNotIn("<img", reply.text.lower())
                    self.assertEqual(active_content(reply), [])
                    self.assertEqual(reply.problems, [])
        for path in shows_records:
            with self.subTest(shows=path):
                self.assertIn(XSS_ESCAPED, console.get(path).text)

    def test_the_payload_is_escaped_on_the_pages_that_answer_a_post(self):
        console = self.console(state="open")
        text = "<script>alert(1)</script>" * 20
        form = console.get("/ok/plan0001").form("/ok/plan0001/ask")
        reply = console.submit(form, note=text)
        self.assertEqual(reply.status, 400)
        self.assertNotIn("<script", reply.text.lower())
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", reply.text)
        self.assertEqual(active_content(reply), [])
        form = console.get("/me/notes").form("/me/notes", has_button="Save")
        reply = console.submit(form, text=XSS, resource_id=XSS, expires="nope", kind="note")
        self.assertEqual(reply.status, 400)
        self.assertNotIn(XSS, reply.text)
        self.assertIn(XSS_ESCAPED, reply.text)
        self.assertEqual(active_content(reply), [])
        form = console.get("/ops/pause").form("/ops/pause", has_button="Resume changes")
        reply = console.submit(form, reason=XSS * 20)
        self.assertEqual(reply.status, 400)
        self.assertNotIn(XSS, reply.text)
        self.assertEqual(active_content(reply), [])

    def test_an_id_with_characters_that_are_not_for_an_address_is_made_safe_in_the_link(self):
        console = self.console()
        links = console.get("/history").links()
        self.assertIn("/why/odd%22%3E%3Cb%3Eid", links)
        self.assertEqual(console.get("/why/odd%22%3E%3Cb%3Eid").status, 404, "the id of a link is not decoded: only plain ids are routed")

    def test_what_the_decider_says_is_escaped_and_the_note_goes_to_it_as_text(self):
        console = self.console(state="open")
        console.decider.result = DecideResult(False, "error", XSS)
        form = console.get("/ok/plan0001").form("/ok/plan0001", has_button="Decline")
        reply = console.submit(form, "Decline", note=XSS)
        self.assertNotIn(XSS, reply.text)
        self.assertIn(XSS_ESCAPED, reply.text)
        self.assertEqual(active_content(reply), [])
        self.assertEqual(console.decider.calls[0]["note"], XSS)


class Routing(unittest.TestCase):
    def test_an_unknown_path_is_a_plain_404(self):
        console = seeded()
        for path in ("/nothing", "/ok", "/ok/", "/ok/a/b", "/why", "/me", "/ops", "/me/settings/other", "/index.html", "/ok/%2e%2e", "/ok/a%20b", "//", "/history/x"):
            with self.subTest(path=path):
                reply = console.get(path)
                self.assertEqual(reply.status, 404)
                self.assertIn("I cannot find this page", reply.content)

    def test_a_known_path_with_the_wrong_method_is_a_405_that_says_what_is_allowed(self):
        console = seeded()
        for method, path, allowed in (("POST", "/", "GET, HEAD"), ("POST", "/history", "GET, HEAD"), ("GET", "/me/settings/export", "POST"), ("GET", "/ok/plan0001/ask", "POST"),
                                      ("POST", "/why/case0001", "GET, HEAD"), ("GET", "/me/settings/delete", "POST"), ("GET", "/me/notes/n1/delete", "POST")):
            with self.subTest(method=method, path=path):
                reply = console.send(method, path, form={"a": "b"} if method == "POST" else None)
                self.assertEqual(reply.status, 405)
                self.assertEqual(reply.headers["Allow"], allowed)
        self.assertEqual(console.send("PUT", "/me/settings", form={}).status, 405)
        self.assertEqual(console.send("DELETE", "/me/notes/n1").status, 405)
        self.assertEqual(console.send("PATCH", "/").status, 405)
        self.assertEqual(console.send("OPTIONS", "/").status, 405)

    def test_a_closing_slash_is_taken_away(self):
        console = seeded()
        self.assertEqual(console.get("/history/").status, 200)
        self.assertEqual(console.get("/ok/plan0001/").status, 200)

    def test_a_path_in_front_of_the_console_is_taken_away_and_put_back_in_every_link(self):
        console = Console(base="/api")
        console.seed()
        reply = console.get("/")
        self.assertEqual(reply.status, 200)
        for href in reply.links():
            if href.startswith(("mailto:", "#")):
                continue
            self.assertTrue(href.startswith("/api/") or href == "/api/", href)
        self.assertEqual(console.get("/healthz", oid=None).text, "ok")
        form = console.get("/ok/plan0001").form("/ok/plan0001")
        self.assertEqual(form.action, "/api/ok/plan0001")
        self.assertEqual(console.send("GET", "/", oid=TINO).status, 200)
        outside = handle(parse_request("GET", f"https://{HOST}/history", {"x-ms-client-principal-id": TINO}, None), console.services)
        self.assertEqual(outside.status, 404)
        self.assertEqual(console.get("/me/settings").form("/me/settings/export").action, "/api/me/settings/export")

    def test_the_handler_reads_header_names_without_regard_to_case(self):
        console = seeded()
        request = Request("GET", "/", {}, {"X-MS-Client-Principal-Id": TINO}, {}, b"")
        self.assertEqual(handle(request, console.services).status, 200)


class Determinism(unittest.TestCase):
    NONCE = re.compile(r'(name="nonce" value=")[^"]*(")')

    def test_a_page_is_the_same_page_for_the_same_time_and_the_same_records(self):
        first, second = seeded(), seeded()
        for path in GET_PATHS:
            with self.subTest(path=path):
                one, two = first.get(path).text, second.get(path).text
                self.assertEqual(self.NONCE.sub(r"\1X\2", one), self.NONCE.sub(r"\1X\2", two))
        again = first.get("/ok/plan0001").text
        self.assertEqual(self.NONCE.sub(r"\1X\2", again), self.NONCE.sub(r"\1X\2", second.get("/ok/plan0001").text))

    def test_the_time_comes_from_the_clock_of_the_services(self):
        console = seeded()
        self.assertIn("Sun 8 Nov 2026 08:00 UTC", console.get("/ok/plan0001").content)
        console.now = console.now.replace(day=9)
        reply = console.get("/ok/plan0001")
        self.assertIn("This request expired on Sun 8 Nov 2026 08:00 UTC", reply.content)


if __name__ == "__main__":
    unittest.main()
