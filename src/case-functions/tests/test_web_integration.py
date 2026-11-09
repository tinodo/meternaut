"""The pages, the real approval loop and the real sign-in to Azure over one in-memory store: the forms of the pages are the ones that the loop checks, and what the person sees
after the sign-in is what the change recorded. Only what is outside the app is made up: Microsoft Entra (who signed in, and the token that it gives) and Azure Resource Manager."""
import json
import unittest
from dataclasses import replace
from urllib.parse import parse_qs, urlsplit

from test_web_support import GROUP, HOST, MAYA, NOW, OPS, SUB, TINO, Console, snapshot

from cases.approvals import Approvals, ApprovalSettings
from cases.delegated import Delegation, SigninSettings, Tokens
from cases.detectors import Lead
from cases.families import digest as plan_digest
from cases.families.gates import ChangeScope
from cases.http import Client
from cases.memory_store import stamp
from cases.models import CaseRecord, SwitchRecord
from cases.runner import RunnerServices, change_calls

APPROVE = "Approve and sign in to Azure"
TENANT = "cccccccc-3333-4444-8555-666666666666"
CLIENT = "dddddddd-4444-4555-8666-777777777777"
ASSERTION_CLIENT = "eeeeeeee-5555-4666-8777-888888888888"
ACCESS = "the-access-token-of-the-person-" + "a" * 40
CODE = "the-code-that-entra-sends-back-" + "b" * 20


def lead(kind="orphan-managed-disk", name="planted-disk-1"):
    resource = "microsoft.compute/disks" if kind == "orphan-managed-disk" else "microsoft.network/publicipaddresses"
    return Lead(detector=kind, resource_id=f"/subscriptions/{SUB}/resourceGroups/{GROUP}/providers/{resource}/{name}", resource_type=resource, name=name, resource_group=GROUP,
                subscription_id=SUB, location="swedencentral", tags={"meternaut-planted": "demo"}, managed_by="", facts={"diskState": "unattached"}, age_days=0)


def rows(reply) -> dict[str, str]:
    """The names and values of the summary lists of the page."""
    found = {}
    for dl in reply.main.find_all("dl", class_="summary"):
        for div in dl.find_all("div"):
            dt, dd = div.find("dt"), div.find("dd")
            if dt is not None and dd is not None:
                found[dt.text()] = dd.text()
    return found


def feed_lines(reply) -> list[tuple[str, str, str]]:
    """The lines of the history: for each one the chip, the title or the count, and the quiet part (empty when the line has none)."""
    found = []
    for ul in reply.main.find_all("ul", class_="recent"):
        for li in ul.find_all("li"):
            texts = [child.text() for child in li.children if hasattr(child, "tag") and child.tag == "span"]
            found.append(tuple((texts + ["", ""])[:3]))
    return found


def form_action_of(reply) -> list[str]:
    """The sources that the policy of a response allows for `form-action`."""
    for part in reply.headers["Content-Security-Policy"].split(";"):
        if part.split()[:1] == ["form-action"]:
            return part.split()[1:]
    return []


class Entra:
    """The sign-in and the token endpoint as far as the console meets them: who signed in, and the tokens that go with that sign-in."""

    def __init__(self) -> None:
        self.signed_in = TINO
        self.nonce = ""
        self.asked: list[tuple[str, str]] = []

    def redeem(self, code: str, verifier: str) -> Tokens:
        self.asked.append((code, verifier))
        return Tokens(ACCESS, {"oid": self.signed_in, "tid": TENANT, "aud": CLIENT, "nonce": self.nonce, "iss": f"https://login.microsoftonline.com/{TENANT}/v2.0",
                               "exp": int(NOW.timestamp()) + 3600})


class Azure:
    """Azure Resource Manager for the token of the person: one unattached disk that carries the tag of the plan, no lock, and a delete that works unless the person may not make it."""

    def __init__(self, resource_id: str) -> None:
        self.resource_id = resource_id
        self.exists = True
        self.may_delete = True
        self.calls: list[tuple[str, str, str]] = []

    def transport(self, method, url, headers, data, timeout):
        path = urlsplit(url).path
        self.calls.append((method, path, headers.get("Authorization", "")))
        if path.lower().endswith("/providers/microsoft.authorization/locks"):
            return 200, {}, b'{"value": []}'
        if method == "GET":
            if not self.exists:
                return 404, {}, b'{"error":{"code":"ResourceNotFound","message":"gone"}}'
            disk = {"id": self.resource_id, "name": "planted-disk-1", "tags": {"meternaut-planted": "demo"}, "properties": {"diskState": "Unattached"}}
            return 200, {}, json.dumps(disk).encode()
        if method == "DELETE":
            if not self.may_delete:
                return 403, {}, b'{"error":{"code":"AuthorizationFailed","message":"the account has no right to delete"}}'
            self.exists = False
            return 200, {}, b""
        return 405, {}, b"{}"

    def deletes(self) -> int:
        return sum(1 for method, _, _ in self.calls if method == "DELETE")


class WithTheRealLoop(unittest.TestCase):
    def setUp(self):
        self.console = Console()
        self.settings = ApprovalSettings(change_scopes=(ChangeScope(SUB, GROUP),))
        self.loop = Approvals(self.console.store, self.settings, lambda: self.console.now)
        item = lead()
        self.entra = Entra()
        self.azure = Azure(item.resource_id)
        self.client = Client(change_calls(self.settings.change_scopes), lambda text: text, transport=self.azure.transport, sleep=lambda seconds: None, monotonic=lambda: 0.0)
        self.delegation = Delegation(self.console.store, self.loop, SigninSettings(TENANT, CLIENT, ASSERTION_CLIENT, HOST), self.entra.redeem, self.runner_for)
        self.console.use(self.loop)
        self.console.use_delegate(self.delegation)
        self.case = CaseRecord(case_id="k1", resource_id=item.resource_id, resource_name=item.name, resource_type=item.resource_type, resource_group=GROUP, subscription_id=SUB,
                               detector=item.detector, run_id="run00001", status="proposed", recommendation="delete", confidence=0.9, saving_usd_month=7.17, cost_usd_30d=7.17,
                               summary="The model said so.", objections=("An objection.",), updated_at=stamp(NOW), first_seen_at=stamp(NOW))
        self.console.store.case_put(self.case)
        self.plan = self.loop.create(self.case, item, (TINO,))
        self.assertIsNotNone(self.plan)
        self.path = f"/ok/{self.plan.plan_id}"

    def runner_for(self, token: str) -> RunnerServices:
        """What the change is made with: the token of the person, for the one request."""
        return RunnerServices(self.console.store, self.client, lambda resource: token, self.settings, clock=lambda: self.console.now, sleep=lambda seconds: None)

    def reseal(self, **changes):
        """Changes a field of the plan as a new plan would have it: its digest and its code are made again, as they are for every plan."""
        self.plan = plan_digest.sealed(replace(self.plan, **changes))
        self.console.store.plan_put(self.plan)

    def form(self, who=TINO, action=None, button=None):
        return self.console.get(self.path, oid=who).form(action or self.path, has_button=button)

    def sign_in(self, who=TINO, **fields):
        """Presses the approve button. The console answers with a redirect to the sign-in."""
        return self.console.submit(self.form(who=who, button=APPROVE), APPROVE, oid=who, **fields)

    def sign_in_address(self, redirect):
        parts = urlsplit(redirect.headers["Location"])
        return parts, {name: values[0] for name, values in parse_qs(parts.query).items()}

    def come_back(self, query, who=TINO, **kwargs):
        return self.console.get("/arm/return", query=query, oid=who, **kwargs)

    def approve(self, who=TINO, **fields):
        """The whole approval: the button, the sign-in of the person, and the return. Gives the redirect and the page of the return."""
        redirect = self.sign_in(who, **fields)
        self.assertEqual(redirect.status, 303)
        _, query = self.sign_in_address(redirect)
        self.entra.signed_in, self.entra.nonce = who, query["nonce"]
        return redirect, self.come_back({"code": CODE, "state": query["state"], "session_state": "a-session"}, who=who)

    def open_requests(self):
        return self.console.store.plan_get(self.plan.plan_id), self.console.store.decisions_of_plan(self.plan.plan_id), self.console.store.action_get(self.plan.plan_id)

    def test_the_page_shows_the_plan_that_the_loop_made(self):
        reply = self.console.get(self.path)
        self.assertEqual(reply.status, 200)
        self.assertEqual(reply.headings(1), ["Delete the unattached disk planted-disk-1"])
        self.assertIn("Saves, Expected. $7.17 a month.", reply.main.find("p", class_="figsub").text())
        found = reply.facts()
        self.assertEqual(found["What changes"], "Deletes the disk planted-disk-1 in resource group meternaut-test-rg. Nothing else changes.")
        self.assertEqual(found["Undo"], "This cannot be undone.")
        self.assertIn("Meternaut holds no right of its own to change anything.", found["Who does it"])
        (form,) = reply.forms()
        self.assertEqual(form.fields["code"], self.plan.code)
        self.assertEqual(self.console.store.case_get("k1").status, "awaiting_ok")
        self.assertEqual(self.plan.family, "delete-disk")

    def test_an_approval_goes_through_the_sign_in_and_the_change_is_made_with_the_token_of_the_person(self):
        redirect = self.sign_in(note="Go on")
        self.assertEqual(redirect.status, 303)
        self.assertEqual(redirect.body, b"")
        parts, query = self.sign_in_address(redirect)
        self.assertEqual((parts.scheme, parts.netloc, parts.path), ("https", "login.microsoftonline.com", f"/{TENANT}/oauth2/v2.0/authorize"))
        self.assertEqual((query["client_id"], query["response_type"], query["response_mode"], query["redirect_uri"]), (CLIENT, "code", "query", f"https://{HOST}/arm/return"))
        self.assertEqual(query["code_challenge_method"], "S256")
        self.assertIn("https://management.azure.com/user_impersonation", query["scope"].split())
        self.assertNotIn("offline_access", query["scope"])
        self.assertEqual(query["login_hint"], "someone@example.com", "the hint is the name that the platform's sign-in gave")
        self.assertIn(f"{parts.scheme}://{parts.netloc}", form_action_of(redirect), "the policy of the page lets the browser follow the redirect to the sign-in")
        plan, answers, action = self.open_requests()
        self.assertEqual((plan.state, answers, action), ("open", [], None), "nothing is recorded before the person is back")
        self.assertEqual((self.azure.calls, self.entra.asked, self.azure.exists), ([], [], True))
        self.assertEqual(len(self.console.get(self.path).forms()), 1, "the request is open until the person is back")
        self.entra.nonce = query["nonce"]
        returned = self.come_back({"code": CODE, "state": query["state"], "session_state": "a-session"})
        self.assertEqual((returned.status, returned.headings(1)), (200, ["The change was made"]))
        self.assertIn("Deleted. Azure no longer lists the resource.", returned.content)
        plan, answers, action = self.open_requests()
        self.assertEqual((plan.state, action.state, self.console.store.case_get("k1").status), ("consumed", "done", "done"))
        self.assertEqual([(d.decision, d.approver_oid, d.note) for d in answers], [("approve", TINO, "Go on")])
        self.assertFalse(self.azure.exists)
        self.assertEqual(self.azure.deletes(), 1)
        self.assertTrue(all(ACCESS in token for _, _, token in self.azure.calls), "every call to Azure carried the token of the person")
        self.assertEqual([code for code, _ in self.entra.asked], [CODE])

    def test_the_pages_report_what_the_change_made_and_show_nothing_of_the_sign_in(self):
        redirect, returned = self.approve(note="Go on")
        _, query = self.sign_in_address(redirect)
        plan_page = self.console.get(self.path)
        self.assertEqual([p.text() for p in plan_page.main.find_all("p", class_="notice-title")], ["Done"])
        self.assertIn("Approved by Tino, and made with their own Azure rights.", plan_page.content)
        self.assertEqual(plan_page.forms(), [])
        self.assertEqual(rows(plan_page)["State"], "Done.")
        self.assertEqual(rows(plan_page)["Result"], "Deleted. Azure no longer lists the resource.")
        history = self.console.get("/history")
        lines = feed_lines(history)
        self.assertIn(("Approved", "Delete the unattached disk planted-disk-1", "Tino"), lines)
        self.assertIn(("Change made", "Delete the unattached disk planted-disk-1", "Deleted. Azure no longer lists the resource."), lines)
        for old in ("/me/decisions", "/me/activity"):
            self.assertEqual(feed_lines(self.console.get(old)), lines, "the old addresses answer with the same page")
        notebook = self.console.get("/why/k1")
        self.assertEqual(rows(notebook)["State of the request"], "Used. The change was made with the approver's own permissions, and a request runs once.")
        self.assertIn("Nothing waits for you.", self.console.get("/").content)
        for page in (returned, plan_page, history, notebook):
            for secret in (ACCESS, CODE, query["state"], query["nonce"], query["code_challenge"]):
                self.assertNotIn(secret, page.text)

    def test_a_person_who_may_not_delete_sees_that_azure_refused_and_that_nothing_was_changed(self):
        self.azure.may_delete = False
        _, returned = self.approve()
        self.assertEqual((returned.status, returned.headings(1)), (403, ["Azure refused the change"]))
        self.assertIn("Nothing was changed.", returned.content)
        self.assertNotIn(ACCESS, returned.text)
        self.assertTrue(self.azure.exists)
        page = self.console.get(self.path)
        self.assertEqual([p.text() for p in page.main.find_all("p", class_="notice-title")], ["Not made"])
        self.assertEqual(rows(page)["State"], "Failed.")
        self.assertEqual(page.forms(), [])

    def test_a_sign_in_that_was_refused_leaves_the_request_open_and_asks_azure_for_nothing(self):
        _, query = self.sign_in_address(self.sign_in())
        returned = self.come_back({"state": query["state"], "error": "access_denied", "error_description": "AADSTS65004: The user declined to consent.\r\nTrace ID: 0b0c"})
        self.assertEqual((returned.status, returned.headings(1)), (400, ["The sign-in to Azure was not completed"]))
        plan, answers, action = self.open_requests()
        self.assertEqual((plan.state, answers, action), ("open", [], None))
        self.assertEqual((self.azure.calls, self.entra.asked), ([], []))
        self.assertEqual(len(self.console.get(self.path).forms()), 1)

    def test_a_sign_in_with_another_account_is_refused_and_nothing_is_approved(self):
        _, query = self.sign_in_address(self.sign_in())
        self.entra.signed_in, self.entra.nonce = MAYA, query["nonce"]
        returned = self.come_back({"code": CODE, "state": query["state"]})
        self.assertEqual((returned.status, returned.headings(1)), (400, ["The sign-in to Azure was not completed"]))
        self.assertIn("Nothing is approved.", returned.content)
        plan, answers, action = self.open_requests()
        self.assertEqual((plan.state, answers, action), ("open", [], None))
        self.assertEqual(self.azure.calls, [])

    def test_a_return_is_taken_once_and_only_from_the_person_who_started_the_sign_in(self):
        _, query = self.sign_in_address(self.sign_in())
        self.entra.nonce = query["nonce"]
        wanted = {"code": CODE, "state": query["state"]}
        stranger = self.come_back(wanted, who=MAYA)
        self.assertEqual((stranger.status, stranger.headings(1)), (409, ["This request cannot take an answer"]))
        self.assertEqual((self.entra.asked, self.open_requests()[0].state), ([], "open"))
        done = self.come_back(wanted)
        self.assertEqual((done.status, done.headings(1)), (200, ["The change was made"]))
        again = self.come_back(wanted)
        self.assertEqual((again.status, again.headings(1)), (409, ["This request cannot take an answer"]))
        self.assertIn("Nothing was changed.", again.content)
        self.assertEqual((len(self.entra.asked), self.azure.deletes()), (1, 1))

    def test_a_return_with_no_state_or_with_a_state_that_was_never_made_is_refused(self):
        for query in ({}, {"code": CODE}, {"state": "x" * 32, "code": CODE}, {"state": "../" + "x" * 30, "code": CODE}):
            with self.subTest(query=query):
                reply = self.come_back(query)
                self.assertEqual((reply.status, reply.headings(1)), (409, ["This request cannot take an answer"]))
        self.assertEqual((self.entra.asked, self.azure.calls, self.open_requests()[0].state), ([], [], "open"))

    def test_a_switch_that_is_pulled_between_the_redirect_and_the_return_stops_the_approval(self):
        _, query = self.sign_in_address(self.sign_in())
        self.entra.nonce = query["nonce"]
        self.console.store.switch_put(SwitchRecord("changes", True, "Otto", "2026-11-05T08:30:00Z", "drill"))
        returned = self.come_back({"code": CODE, "state": query["state"]})
        self.assertEqual((returned.status, returned.headings(1)), (409, ["Changes are paused"]))
        plan, answers, action = self.open_requests()
        self.assertEqual((plan.state, answers, action), ("open", [], None))
        self.assertEqual((self.entra.asked, self.azure.calls), ([], []))

    def test_a_plan_that_runs_out_of_time_between_the_redirect_and_the_return_is_not_approved(self):
        self.reseal(expires_at="2026-11-05T09:05:00Z")
        _, query = self.sign_in_address(self.sign_in())
        self.entra.nonce = query["nonce"]
        self.console.now = self.console.now.replace(minute=6)
        returned = self.come_back({"code": CODE, "state": query["state"]})
        self.assertEqual((returned.status, returned.headings(1)), (410, ["This request expired"]))
        self.assertEqual(self.console.store.case_get("k1").status, "expired")
        self.assertEqual((self.entra.asked, self.azure.calls, self.open_requests()[1]), ([], [], []))

    def test_a_wrong_code_a_token_of_somebody_else_and_a_pulled_switch_each_have_their_page_and_start_no_sign_in(self):
        main = self.form(button=APPROVE)
        reply = self.console.submit(main, APPROVE, code="WRONG")
        self.assertEqual((reply.status, reply.headings(1)), (409, ["This request changed"]))
        self.reseal(approvers=(TINO, MAYA))
        main = self.form(button=APPROVE)
        reply = self.console.submit(main, APPROVE, oid=MAYA)
        self.assertEqual((reply.status, reply.headings(1)), (500, ["I could not take your answer"]))
        self.assertIn("This form is no longer valid.", reply.content)
        self.console.store.switch_put(SwitchRecord("changes", True, "Otto", "2026-11-05T08:00:00Z", "drill"))
        forged = self.console.post(self.path, {**main.fields, "decision": "approve"})
        self.assertEqual((forged.status, forged.headings(1)), (409, ["Changes are paused"]))
        for answer in (reply, forged):
            self.assertNotIn("Location", answer.headers)
        plan, answers, action = self.open_requests()
        self.assertEqual((plan.state, answers, action), ("open", [], None))
        self.assertEqual((self.entra.asked, self.azure.calls), ([], []))

    def test_a_form_that_was_used_already_is_refused_and_so_is_an_approval_of_a_plan_that_is_not_open_any_more(self):
        main = self.form(button=APPROVE)
        self.assertEqual(self.console.submit(main, APPROVE).status, 303)
        again = self.console.submit(main, APPROVE)
        self.assertEqual((again.status, again.headings(1)), (500, ["I could not take your answer"]))
        self.assertIn("This form is no longer valid.", again.content)
        self.assertEqual(self.approve()[1].status, 200)
        late = self.console.post(self.path, {**main.fields, "decision": "approve", "nonce": self.console.store.nonce_new(TINO, self.plan.plan_id)})
        self.assertEqual((late.status, late.headings(1)), (409, ["This request cannot take an answer"]), "the plan was used, so it takes no answer")
        self.assertNotIn("Location", late.headers)
        self.assertEqual(self.azure.deletes(), 1)

    def test_a_plan_whose_time_is_over_has_its_page_and_closes_the_case(self):
        main = self.form(button=APPROVE)
        self.console.now = self.console.now.replace(day=9)
        late = self.console.post(self.path, {**main.fields, "decision": "approve", "nonce": self.console.store.nonce_new(TINO, self.plan.plan_id)})
        self.assertEqual((late.status, late.headings(1)), (410, ["This request expired"]))
        self.assertIn("This request expired on Sun 8 Nov 2026 09:00 UTC", late.content)
        self.assertEqual(self.console.store.case_get("k1").status, "expired")
        self.assertEqual((self.entra.asked, self.azure.calls), ([], []))

    def test_a_question_then_an_approval_leaves_one_answer(self):
        ask = self.console.get(self.path).form(self.path)
        self.assertEqual(self.console.submit(ask, "Ask or tell", note="Is it the standby?").headings(1), ["Recorded: your words"])
        self.assertEqual([d.decision for d in self.console.store.decisions_of_plan(self.plan.plan_id)], ["ask"])
        self.assertEqual(self.approve()[1].headings(1), ["The change was made"])
        answers = self.console.store.decisions_of_plan(self.plan.plan_id)
        self.assertEqual([d.decision for d in answers], ["approve"])

    def test_a_decline_closes_the_request_and_the_case(self):
        declined = self.console.submit(self.form(button="Decline"), "Decline", note="Not now", reason="handled")
        self.assertEqual(declined.headings(1), ["Declined"])
        self.assertEqual(self.console.store.plan_get(self.plan.plan_id).state, "declined")
        self.assertEqual(self.console.store.case_get("k1").status, "declined")
        (record,) = self.console.store.decisions_of_plan(self.plan.plan_id)
        self.assertEqual((record.decision, record.note, record.reason), ("decline", "Not now", "handled"))
        lines = feed_lines(self.console.get("/history"))
        self.assertIn(("Declined", "Delete the unattached disk planted-disk-1", "Tino · reason: it is already handled"), lines)

    def test_a_person_who_is_not_named_is_refused_by_the_page_before_the_loop(self):
        self.assertEqual(self.console.get(self.path, oid=MAYA).status, 403)
        self.assertEqual(self.console.get(self.path, oid=OPS).status, 403)
        before = snapshot(self.console.store)
        main = self.form(button=APPROVE)
        reply = self.console.submit(main, APPROVE, oid=MAYA)
        self.assertEqual(reply.status, 403)
        self.assertNotIn("Location", reply.headers)
        self.assertEqual(snapshot(self.console.store), before)
        self.assertEqual((self.entra.asked, self.azure.calls), ([], []))


if __name__ == "__main__":
    unittest.main()
