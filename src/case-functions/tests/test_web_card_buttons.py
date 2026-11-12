"""The page that a button on a Teams card opens (cases/web/approval.py: card_answer), and what follows it.

A card carries the decision, and its buttons are links (cases/cardlinks.py): /ok/<request>/approve, /confirm or /decline with the plan's code and a link token. Opening one changes nothing; it
shows a small page that sends the form of the answer by itself, with one fixed script that the page's policy allows by its hash, and a button for a browser without scripts. The form is the
one that the page of the request posts, so every check after it stays. These tests run the real pages, the real approval loop where it matters, and a fake of the sign-in.
"""
import base64
import copy
import datetime as dt
import hashlib
import re
import unittest

from support import APP_ROOT
from test_web_look_before_approve import ScriptedChecker
from test_web_support import (MAYA, OPS, SIGNIN_URL, STRANGER, TINO, Console, FailingStore, ScriptedDecider, ScriptedDelegate, at, make_action, make_advice, make_advice_case,
                              make_decision, make_plan, snapshot)

from cases import cardlinks
from cases.models import READY, REFUSED, UNKNOWN, Begun, DecideResult, DecisionRecord, Readiness, SwitchRecord
from cases.web import layout
from cases.web.core import Response

CODE = "7F3K92QD"
ADVICE_CODE = "B4N8X2KM"
WORKS = 'var f=document.getElementById("send");if(f){f.submit();}'


def directives(policy: str) -> dict[str, list[str]]:
    return {part.split()[0]: part.split()[1:] for part in policy.split(";") if part.strip()}


def seeded(**kw) -> Console:
    console = Console(**kw)
    console.seed()
    console.store.case_put(make_advice_case())
    console.store.plan_put(make_advice())
    return console


def token_for(console: Console, plan_id: str, answer: str, *, sure: bool = False, oid: str = TINO, seconds: int = 3600, code: str | None = None) -> dict[str, str]:
    """The query of a button's address, as the app makes it when it builds the card."""
    plan = console.store.plan_get(plan_id)
    return {"code": code or plan.code, "token": cardlinks.mint(console.store.nonce_new, oid, plan_id, code or plan.code, answer, sure, seconds)}


def press(console: Console, plan_id: str, answer: str, *, sure: bool = False, oid: str = TINO, method: str = "GET", **options):
    """A person presses a button on a card: the GET of its address. Returns the reply and the query that was sent."""
    query = token_for(console, plan_id, answer, sure=sure, oid=oid, **options)
    return console.send(method, f"/ok/{plan_id}/{answer}", query=query, oid=oid), query


def script_of(reply) -> list[str]:
    return ["".join(child for child in node.children if isinstance(child, str)) for node in reply.root.find_all("script")]


def fields(reply) -> dict[str, str]:
    return reply.form("/ok/" + re.search(r'action="[^"]*/ok/([^"/]+)"', reply.text).group(1)).fields


class TheSendingPage(unittest.TestCase):
    def test_a_button_that_approves_a_delete_opens_the_form_of_the_answer_with_the_word_that_the_card_already_asked(self):
        console = seeded()
        reply, query = press(console, "plan0001", "approve", sure=True)
        self.assertEqual((reply.status, reply.problems), (200, []))
        form = reply.form("/ok/plan0001")
        self.assertEqual(form.method, "post")
        self.assertEqual(form.fields, {"code": CODE, "nonce": query["token"], "decision": "approve", "confirm": "yes"})
        self.assertEqual(form.buttons, [("", "", "Yes, delete it")], "one button, with no name: a script sends the form without a button")
        self.assertEqual(reply.root.find("form").attrs["id"], "send")
        self.assertEqual(reply.headings(1), ["Delete the unattached disk planted-disk-1"])
        self.assertIn("Your answer is being sent. If nothing happens, press the button.", reply.main.text())

    def test_the_other_answers_have_the_words_of_the_card(self):
        console = seeded()
        for plan_id, answer, sure, label, fixed in (("plan0001", "decline", False, "Decline", {"decision": "decline"}), ("plan0002", "approve", False, "Worth acting on", {"decision": "approve"}),
                                                   ("plan0002", "decline", False, "Not worth it", {"decision": "decline"})):
            with self.subTest(plan=plan_id, answer=answer):
                reply, query = press(console, plan_id, answer, sure=sure)
                self.assertEqual(reply.status, 200)
                form = reply.form(f"/ok/{plan_id}")
                self.assertEqual([text for _, _, text in form.buttons], [label])
                self.assertEqual(form.fields, {"code": console.store.plan_get(plan_id).code, "nonce": query["token"], **fixed})
                self.assertNotIn("confirm", form.fields)

    def test_a_change_that_can_be_undone_is_approved_with_one_press_and_a_delete_whose_card_did_not_ask_is_asked_on_the_page_that_asks(self):
        console = seeded()
        console.store.plan_put(make_plan(plan_id="plan0003", family="stop-vm", title="Stop the virtual machine vm-1", resource_name="vm-1", undo="Start the machine again."))
        reply, query = press(console, "plan0003", "approve")
        self.assertEqual(reply.form("/ok/plan0003").buttons, [("", "", "Approve")])
        self.assertNotIn("confirm", reply.form("/ok/plan0003").fields)

    def test_the_first_of_two_people_confirms(self):
        console = seeded()
        console.store.plan_put(make_plan(approval_class="R3", approvers=(TINO, MAYA), digest="d" * 64))
        reply, query = press(console, "plan0001", "confirm")
        self.assertEqual(reply.status, 200)
        self.assertEqual(reply.form("/ok/plan0001").buttons, [("", "", "Confirm")])
        self.assertEqual(reply.form("/ok/plan0001").fields["decision"], "confirm")

    def test_the_page_is_a_page_of_the_console_with_its_footer_and_says_why_the_person_sees_it(self):
        reply, _ = press(seeded(), "plan0001", "decline")
        self.assertIsNotNone(reply.root.find("nav"))
        self.assertIn("You see this because you pressed a button on a card that Meternaut sent you.", reply.root.find("footer").text())
        self.assertIn("Models: model-detective-x, model-skeptic-y.", reply.root.find("footer").text())
        self.assertNotRegex(reply.main.text(), r"(?i)\bsign(?:s|ed|ing)?[ -]in\b")

    def test_the_page_changes_nothing_and_makes_no_call_and_asks_nobody_and_the_token_is_still_good(self):
        decider, delegate = ScriptedDecider(), ScriptedDelegate()
        console = seeded(decider=decider, delegate=delegate)
        before = snapshot(console.store)
        query = token_for(console, "plan0001", "approve", sure=True)
        nonces = copy.deepcopy(console.store.nonces)
        for method in ("GET", "HEAD", "GET"):
            console.send(method, "/ok/plan0001/approve", query=query)
        self.assertEqual(snapshot(console.store), before, "no record of a request, a case, a decision, an action, a switch, a setting, a note or a letter changed")
        self.assertEqual(console.store.nonces, nonces, "no token was made or used up")
        self.assertEqual((decider.calls, delegate.begins, delegate.finishes), ([], [], []), "nothing was asked of the decider or of the sign-in")
        self.assertIsNotNone(console.store.nonce_peek(query["token"], TINO, "plan0001"))

    def test_a_head_request_gets_the_headers_and_no_body(self):
        reply, _ = press(seeded(), "plan0001", "approve", sure=True, method="HEAD")
        self.assertEqual((reply.status, reply.body), (200, b""))
        self.assertEqual(reply.headers["Content-Security-Policy"], layout.CSP_SEND)

    def test_the_code_may_be_written_in_small_letters(self):
        console = seeded()
        reply = console.get("/ok/plan0001/decline", query={**token_for(console, "plan0001", "decline"), "code": CODE.lower()})
        self.assertEqual(reply.status, 200)
        self.assertEqual(reply.form("/ok/plan0001").fields["code"], CODE, "the form carries the code of the plan as it is stored")


class TheScriptAndThePolicy(unittest.TestCase):
    """The pages have no script, and one page has one: the one that sends the form. It is a fixed text, and the policy of that page allows exactly that text by its hash."""

    def setUp(self):
        self.reply, _ = press(seeded(), "plan0001", "approve", sure=True)

    def test_the_page_has_one_script_the_fixed_one_and_no_other_active_content(self):
        self.assertEqual(script_of(self.reply), [WORKS])
        self.assertEqual(layout.SEND_SCRIPT, WORKS)
        for node in self.reply.root.walk():
            self.assertNotIn(node.tag, ("iframe", "object", "embed", "base", "frame", "applet", "img", "link"))
            if node.tag == "script":
                self.assertEqual(node.attrs, {}, "no src, no type, nothing else")
            for name in node.attrs:
                self.assertFalse(name.startswith("on"), f"an event handler: {name}")
        self.assertEqual(self.reply.problems, [])

    def test_the_policy_is_the_policy_of_every_page_and_the_hash_of_that_script(self):
        digest = "sha256-" + base64.b64encode(hashlib.sha256(script_of(self.reply)[0].encode("utf-8")).digest()).decode("ascii")
        policy = directives(self.reply.headers["Content-Security-Policy"])
        self.assertEqual(policy, {"default-src": ["'none'"], "script-src": [f"'{digest}'"], "style-src": ["'unsafe-inline'"], "form-action": ["'self'", layout.SIGNIN_ORIGIN],
                                  "frame-ancestors": ["'none'"], "base-uri": ["'none'"]})
        self.assertNotIn("'unsafe-inline'", policy["script-src"])
        self.assertNotIn("'unsafe-eval'", " ".join(sum(policy.values(), [])))
        base = directives(layout.CSP)
        self.assertEqual({name: value for name, value in policy.items() if name != "script-src"}, base, "everything else is as on every page")
        self.assertNotIn("script-src", base)

    def test_every_other_header_is_the_header_of_every_page(self):
        for name, value in layout.SECURITY_HEADERS.items():
            if name != "Content-Security-Policy":
                self.assertEqual(self.reply.headers[name], value, name)
        self.assertEqual(self.reply.headers["Referrer-Policy"], "same-origin", "a form post carries the origin of the console and not null (AGENTS.md rule 28)")
        self.assertEqual(self.reply.headers["Cache-Control"], "no-store")
        for node in self.reply.root.walk():
            if node.tag == "form":
                self.assertNotIn("rel", node.attrs)
                self.assertNotIn("referrerpolicy", node.attrs)

    def test_the_script_only_sends_the_form_and_reads_and_changes_nothing_else(self):
        for word in ("eval", "fetch", "XMLHttpRequest", "cookie", "location", "innerHTML", "src", "http", "import", "Function", "setTimeout", "localStorage", "document.write", "window"):
            self.assertNotIn(word, WORKS, word)
        self.assertEqual(re.findall(r"\.(\w+)\(", WORKS), ["getElementById", "submit"])

    def test_no_other_response_gets_the_policy_with_a_script(self):
        self.assertEqual(layout.respond(200, "x").headers["Content-Security-Policy"], layout.CSP)
        self.assertEqual(layout.respond(200, "x", sends=True).headers["Content-Security-Policy"], layout.CSP_SEND)
        for policy in ("script-src *", layout.CSP + "; script-src 'unsafe-inline'", "default-src *", layout.CSP_SEND + " ", ""):
            kept = layout.secured(Response(200, {"Content-Security-Policy": policy}, b""))
            self.assertEqual(kept.headers["Content-Security-Policy"], layout.CSP, policy)
        self.assertEqual(layout.secured(Response(200, {"Content-Security-Policy": layout.CSP_SEND}, b"")).headers["Content-Security-Policy"], layout.CSP_SEND)
        self.assertEqual(layout.secured(Response(200, {}, b"")).headers["Content-Security-Policy"], layout.CSP)

    def test_only_the_page_that_sends_the_answer_asks_for_the_policy_and_no_other_module_has_a_script_in_it(self):
        found = {}
        for path in sorted((APP_ROOT / "cases" / "web").glob("*.py")):
            text = path.read_text(encoding="utf-8")
            found[path.name] = (text.count("sends=True"), text.count("<script"))
        self.assertEqual({name: counts for name, counts in found.items() if counts != (0, 0)}, {"approval.py": (1, 1)})
        text = (APP_ROOT / "cases" / "web" / "layout.py").read_text(encoding="utf-8")
        self.assertEqual(text.count("SEND_SCRIPT ="), 1)

    def test_the_other_pages_still_have_no_script_and_the_policy_without_one(self):
        console = seeded()
        for path in ("/", "/ok/plan0001", "/ok/plan0002", "/history", "/me/settings", "/ops", "/nothing"):
            reply = console.get(path)
            self.assertNotIn("<script", reply.text.lower(), path)
            self.assertEqual(reply.headers["Content-Security-Policy"], layout.CSP, path)


class WhatFollowsThePage(unittest.TestCase):
    """The form that the page sends is the form of the page of the request, so the answer is taken as it is taken there."""

    def test_approving_a_delete_goes_straight_to_the_sign_in_with_no_second_page(self):
        delegate = ScriptedDelegate()
        console = seeded(delegate=delegate)
        reply, query = press(console, "plan0001", "approve", sure=True)
        sent = console.submit(reply.form("/ok/plan0001"))
        self.assertEqual((sent.status, sent.headers["Location"], sent.body), (303, SIGNIN_URL, b""))
        self.assertEqual(delegate.begins, [dict(oid=TINO, plan_id="plan0001", code=CODE, nonce=query["token"], note="", hint="someone@example.com")])
        self.assertEqual(sent.headers["Content-Security-Policy"], layout.CSP, "the redirect is answered under the policy of every page")
        self.assertIn("form-action 'self' https://login.microsoftonline.com", sent.headers["Content-Security-Policy"])

    def test_a_delete_whose_card_did_not_ask_gets_the_page_that_asks_which_the_letter_and_the_list_keep(self):
        console = seeded()
        reply, _ = press(console, "plan0001", "approve", sure=False)
        self.assertEqual(reply.form("/ok/plan0001").buttons, [("", "", "Approve")])
        asked = console.post("/ok/plan0001", reply.form("/ok/plan0001").fields)
        self.assertEqual(asked.status, 200)
        self.assertEqual(asked.headings(1), ["Confirm: Delete the unattached disk planted-disk-1"])
        self.assertTrue(any(label == "Yes, delete it" for _, _, label in asked.form("/ok/plan0001").buttons))

    def test_declining_is_recorded_at_once_and_the_page_says_so(self):
        console = seeded(decider="loop")
        reply, query = press(console, "plan0001", "decline")
        sent = console.submit(reply.form("/ok/plan0001"))
        self.assertEqual(sent.status, 200)
        self.assertEqual(sent.headings(1), ["Declined"])
        self.assertIn("Declined. Nothing has changed. The request is closed.", sent.content)
        self.assertEqual(console.store.plan_get("plan0001").state, "declined")
        self.assertEqual([(d.decision, d.approver_oid) for d in console.store.decisions_of_plan("plan0001")], [("decline", TINO)])
        self.assertIsNone(console.store.nonce_peek(query["token"], TINO, "plan0001"), "the form used the token up")

    def test_the_answer_of_advice_is_recorded_by_the_same_form(self):
        console = seeded(decider="loop")
        reply, _ = press(console, "plan0002", "approve")
        sent = console.submit(reply.form("/ok/plan0002"))
        self.assertEqual((sent.status, sent.headings(1)), (200, ["Recorded: worth acting on"]))
        self.assertEqual(console.store.plan_get("plan0002").state, "consumed")
        reply, _ = press(console, "plan0002", "decline")
        self.assertEqual(reply.status, 409, "the request is answered: the button of its other answer cannot be used any more")

    def test_the_first_of_two_people_is_recorded_as_a_confirmation_and_the_request_stays_open(self):
        decider = ScriptedDecider(DecideResult(True, "confirmed", "Recorded."))
        console = seeded(decider=decider)
        console.store.plan_put(make_plan(approval_class="R3", approvers=(TINO, MAYA), digest="d" * 64))
        reply, query = press(console, "plan0001", "confirm")
        sent = console.submit(reply.form("/ok/plan0001"))
        self.assertEqual((sent.status, sent.headings(1)), (200, ["Recorded: you confirmed the request"]))
        self.assertEqual(decider.calls, [dict(oid=TINO, plan_id="plan0001", code=CODE, decision="confirm", nonce=query["token"], note="", reason="")])

    def test_a_token_works_once(self):
        console = seeded(decider="loop")
        reply, _ = press(console, "plan0001", "decline")
        form = reply.form("/ok/plan0001")
        self.assertEqual(console.submit(form).headings(1), ["Declined"])
        again = console.submit(form)
        self.assertNotEqual(again.headings(1), ["Declined"])
        self.assertEqual(console.get("/ok/plan0001/decline", query={"code": CODE, "token": form.fields["nonce"]}).status, 409)

    def test_a_form_that_another_person_sends_with_this_token_is_refused_by_the_decider(self):
        console = seeded(decider="loop")
        console.store.plan_put(make_plan(approvers=(TINO, MAYA)))
        reply, query = press(console, "plan0001", "decline")
        refused = console.submit(reply.form("/ok/plan0001"), oid=MAYA)
        self.assertEqual(console.store.plan_get("plan0001").state, "open")
        self.assertNotEqual(refused.headings(1), ["Declined"])
        self.assertIsNotNone(console.store.nonce_peek(query["token"], TINO, "plan0001"), "the token of the other person is not used up")


class WhenTheButtonCannotBeUsed(unittest.TestCase):
    """A link that fails a check says why, offers the page of the request, and sends nothing: no script, no form."""

    def assert_nothing_is_sent(self, reply, status: int):
        self.assertEqual(reply.status, status, reply.content)
        self.assertEqual(script_of(reply), [])
        self.assertNotIn("id=\"send\"", reply.text)
        self.assertEqual(reply.headers["Content-Security-Policy"], layout.CSP)
        self.assertEqual(reply.problems, [])

    def stale(self, reply):
        self.assert_nothing_is_sent(reply, 409)
        self.assertEqual(reply.headings(1), ["This button cannot be used now"])
        self.assertIn("It was used already, it ran out of time, or the request changed since the card was sent. Nothing was changed.", reply.content)
        self.assertEqual([(a.attrs["href"], a.text()) for a in reply.main.find_all("a")], [("/ok/plan0001", "Open the request")])

    def test_a_token_that_is_not_one_was_used_belongs_to_somebody_else_or_is_for_another_answer(self):
        console = seeded()
        console.store.plan_put(make_plan(approvers=(TINO, MAYA)))
        good = token_for(console, "plan0001", "approve", sure=True)
        for label, query in (("none", {"code": CODE}), ("garbage", {"code": CODE, "token": "not a token"}), ("short", {"code": CODE, "token": "abc"}),
                             ("unknown", {"code": CODE, "token": "u" * 24}), ("a form token of the page", {"code": CODE, "token": console.store.nonce_new(TINO, "plan0001")}),
                             ("a token of another request", {"code": CODE, "token": token_for(console, "plan0002", "approve")["token"]})):
            with self.subTest(label):
                self.stale(console.get("/ok/plan0001/approve", query=query))
        with self.subTest("another person"):
            self.stale(console.get("/ok/plan0001/approve", query=good, oid=MAYA))
        with self.subTest("another answer"):
            self.stale(console.get("/ok/plan0001/decline", query=good))
        self.assertIsNotNone(console.store.nonce_peek(good["token"], TINO, "plan0001"), "a link that is refused uses no token up")

    def test_a_token_that_was_used_or_ran_out_of_time(self):
        console = seeded()
        query = token_for(console, "plan0001", "approve", sure=True)
        self.assertEqual(console.get("/ok/plan0001/approve", query=query).status, 200)
        self.assertTrue(console.store.nonce_use(query["token"], TINO, "plan0001"))
        self.stale(console.get("/ok/plan0001/approve", query=query))
        short = token_for(console, "plan0001", "decline", seconds=0)
        self.assertEqual(console.get("/ok/plan0001/decline", query=short).status, 200, "a token lives a quarter of an hour at least")
        console.now += dt.timedelta(hours=2)
        self.stale(console.get("/ok/plan0001/decline", query=short))

    def test_a_code_that_is_not_the_plans_says_that_the_request_changed(self):
        console = seeded()
        reply = console.get("/ok/plan0001/approve", query=token_for(console, "plan0001", "approve", code="AAAA1111"))
        self.assert_nothing_is_sent(reply, 409)
        self.assertEqual(reply.headings(1), ["This request changed"])
        self.assertIn("This request changed. Nothing is approved. A new message will bring the new request and its code.", reply.content)
        reply = console.get("/ok/plan0001/approve", query={"token": token_for(console, "plan0001", "approve")["token"]})
        self.assertEqual(reply.headings(1), ["This request changed"], "no code is a code that is not the plan's")

    def test_a_request_that_changed_after_the_card_was_sent_refuses_the_buttons_of_the_old_card(self):
        console = seeded()
        query = token_for(console, "plan0001", "approve", sure=True)
        console.store.plan_put(make_plan(code="NEW00000", saving_usd_month=99.0))
        reply = console.get("/ok/plan0001/approve", query=query)
        self.assert_nothing_is_sent(reply, 409)
        self.assertEqual(reply.headings(1), ["This request changed"])
        again = console.get("/ok/plan0001/approve", query={"code": "NEW00000", "token": query["token"]})
        self.stale(again)
        self.assertNotIn("sends", again.text)

    def test_a_request_that_is_not_open_shows_what_became_of_it(self):
        for state, status, title in (("declined", 409, "This request cannot take an answer"), ("approved", 409, "This request cannot take an answer"),
                                     ("consumed", 409, "This request cannot take an answer"), ("withdrawn", 409, "This request cannot take an answer"), ("failed", 409, "This request cannot take an answer")):
            with self.subTest(state):
                console = seeded()
                query = token_for(console, "plan0001", "decline")
                console.store.plan_put(make_plan(state=state))
                reply = console.get("/ok/plan0001/decline", query=query)
                self.assert_nothing_is_sent(reply, status)
                self.assertEqual(reply.headings(1), [title])

    def test_a_request_whose_time_is_over_says_so_even_before_the_timer_has_closed_it(self):
        console = seeded()
        query = token_for(console, "plan0001", "decline")
        console.store.plan_put(make_plan(expires_at=at(minutes=-1)))
        reply = console.get("/ok/plan0001/decline", query=query)
        self.assert_nothing_is_sent(reply, 410)
        self.assertEqual(reply.headings(1), ["This request expired"])
        self.assertEqual(console.store.plan_get("plan0001").state, "open", "a page records nothing: the timer closes it")

    def test_a_switch_that_holds_the_answers_is_said_and_the_token_is_kept(self):
        console = seeded()
        query = token_for(console, "plan0001", "approve", sure=True)
        console.store.switch_put(SwitchRecord("changes", True, "Otto", at(minutes=-5), "drill"))
        reply = console.get("/ok/plan0001/approve", query=query)
        self.assert_nothing_is_sent(reply, 409)
        self.assertEqual(reply.headings(1), ["Changes are paused"])
        self.assertIsNotNone(console.store.nonce_peek(query["token"], TINO, "plan0001"))
        decline = console.get("/ok/plan0001/decline", query=token_for(console, "plan0001", "decline"))
        self.assertEqual(decline.status, 200, "the switch holds the answers that approve, and a decline is still taken")
        console.store.switch_put(SwitchRecord("changes"))
        self.assertEqual(console.get("/ok/plan0001/approve", query=query).status, 200, "and when it is released the same card works")

    def test_a_person_who_is_not_named_has_no_role_or_is_not_signed_in_gets_what_every_page_gives(self):
        console = seeded()
        query = token_for(console, "plan0001", "decline")
        denied = console.get("/ok/plan0001/decline", query=query, oid=None)
        self.assertEqual((denied.status, denied.content), (403, "No access This account cannot open this page."))
        self.assertEqual(console.get("/ok/plan0001/decline", query=query, oid=STRANGER).status, 403)
        for oid in (MAYA, OPS):
            reply = console.get("/ok/plan0001/decline", query=token_for(console, "plan0001", "decline", oid=oid), oid=oid)
            self.assert_nothing_is_sent(reply, 403)
            self.assertEqual(reply.headings(1), ["I cannot take your OK on this request."], oid)
        nothing = console.get("/ok/nothing/decline", query=query)
        self.assert_nothing_is_sent(nothing, 404)

    def test_the_owner_who_is_not_an_approver_may_answer_advice_and_nothing_else_by_a_button(self):
        from test_web_support import OWNER
        console = seeded()
        console.store.plan_put(make_advice(approvers=(TINO, OWNER)))
        console.store.plan_put(make_plan(approvers=(TINO, OWNER)))
        reply = console.get("/ok/plan0002/decline", query=token_for(console, "plan0002", "decline", oid=OWNER), oid=OWNER)
        self.assertEqual(reply.status, 200)
        refused = console.get("/ok/plan0001/decline", query=token_for(console, "plan0001", "decline", oid=OWNER), oid=OWNER)
        self.assert_nothing_is_sent(refused, 403)

    def test_a_record_that_cannot_be_read_is_a_plain_page_and_not_a_send(self):
        console = seeded()
        query = token_for(console, "plan0001", "decline")
        console.store = FailingStore(fail={"nonce_peek"}, clock=lambda: console.now)
        console.services = type(console.services)(**{**console.services.__dict__, "store": console.store})
        console.store.plan_put(make_plan())
        console.store.case_put(make_advice_case(case_id="case0001", plan_id="plan0001"))
        reply = console.get("/ok/plan0001/decline", query=query)
        self.assertEqual(reply.status, 503)
        self.assertEqual(script_of(reply), [])
        self.assertIn("I cannot reach my records", reply.content)

    def test_only_a_get_opens_the_page(self):
        console = seeded()
        query = token_for(console, "plan0001", "decline")
        reply = console.post("/ok/plan0001/decline", {"nonce": query["token"], "code": CODE})
        self.assertEqual(reply.status, 405)
        self.assertEqual(reply.headers["Allow"], "GET, HEAD")
        self.assertEqual(console.store.plan_get("plan0001").state, "open")


class WhenTheLookRefusesTheChange(unittest.TestCase):
    """The look at the resource (cases/precheck.py) that the page of the request takes before it offers Approve is taken here too: a button on a card is an offer of Approve."""

    def console(self, answer) -> Console:
        console = seeded()
        console.services = type(console.services)(**{**console.services.__dict__, "checker": ScriptedChecker(answer)})
        return console

    def test_a_refused_look_shows_the_page_that_says_why_and_sends_nothing(self):
        why = "it no longer carries the test tag meternaut-planted, so it cannot be told apart from a real disk"
        for answer in ("approve", "confirm"):
            with self.subTest(answer):
                console = self.console(Readiness(REFUSED, why))
                if answer == "confirm":
                    console.store.plan_put(make_plan(approval_class="R3", approvers=(TINO, MAYA), digest="d" * 64))
                query = token_for(console, "plan0001", answer, sure=answer == "approve")
                reply = console.get(f"/ok/plan0001/{answer}", query=query)
                self.assertEqual(reply.status, 409)
                self.assertEqual(script_of(reply), [])
                self.assertEqual(reply.headers["Content-Security-Policy"], layout.CSP)
                self.assertIn("Meternaut will not change this disk now", reply.content)
                self.assertFalse(reply.has_button("Approve"))
                self.assertFalse(reply.has_button("Confirm this request"))
                self.assertIsNotNone(console.store.nonce_peek(query["token"], TINO, "plan0001"), "nothing was used up")
                self.assertEqual(console.services.checker.asked, ["plan0001"])

    def test_declining_is_not_a_change_so_no_look_is_made_and_the_answer_goes_on(self):
        console = self.console(Readiness(REFUSED, "it is not there any more"))
        reply, _ = press(console, "plan0001", "decline")
        self.assertEqual(reply.status, 200)
        self.assertEqual(console.services.checker.asked, [])

    def test_a_look_that_could_not_be_made_does_not_stop_the_answer_and_a_ready_look_lets_it_go(self):
        for answer in (Readiness(UNKNOWN), Readiness(READY), RuntimeError("down")):
            with self.subTest(answer=answer):
                console = self.console(answer)
                reply, _ = press(console, "plan0001", "approve", sure=True)
                self.assertEqual(reply.status, 200)
                self.assertEqual(script_of(reply), [WORKS])

    def test_advice_has_no_look(self):
        console = self.console(Readiness(REFUSED, "x"))
        reply, _ = press(console, "plan0002", "approve")
        self.assertEqual(reply.status, 200)
        self.assertEqual(console.services.checker.asked, [])


class TheRoutesOfTheButtons(unittest.TestCase):
    def test_a_button_has_a_path_of_its_own_and_every_page_of_the_request_is_still_where_it_was(self):
        from cases.web import router
        shown = {(method, re.sub(r"\(\?P<\w+>[^)]*\)", "<id>", pattern)) for method, pattern, _, _ in router.ROUTES}
        for path in ("/ok/<id>/approve", "/ok/<id>/confirm", "/ok/<id>/decline"):
            self.assertIn(("GET", path), shown)
            self.assertNotIn(("POST", path), shown, "a button opens a page and changes nothing")
        for kept in (("GET", "/ok/<id>"), ("POST", "/ok/<id>"), ("POST", "/ok/<id>/ask"), ("POST", "/ok/<id>/not-mine")):
            self.assertIn(kept, shown)
        for method, pattern, handler, roles in router.ROUTES:
            if pattern.endswith(("/approve", "/confirm", "/decline")):
                self.assertEqual((method, roles), ("GET", ()), "any listed person; the page checks that the person is named on the request")
                self.assertNotIn(handler, router.NO_HEAD, "a HEAD request is as harmless as a GET: neither changes anything")


if __name__ == "__main__":
    unittest.main()
