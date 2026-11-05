import base64
import datetime as dt
import hashlib
import json
import re
import unittest
from dataclasses import replace
from urllib.parse import parse_qs, urlsplit

from support import APP_ROOT  # noqa: F401

from cases import delegated, loop_config
from cases.approvals import Approvals, ApprovalSettings
from cases.delegated import ARM_SCOPE, Delegation, SigninError, SigninSettings, Tokens, TokenClient, authorize_url, explain, new_pkce, settings_of, token_calls
from cases.detectors import Lead
from cases.http import Client, HttpError, Refused
from cases.memory_store import MemoryStore, stamp
from cases.models import CaseRecord, DecisionRecord, Principal, StoreError, SwitchRecord
from cases.runner import RunnerServices, change_calls
from test_runner import DISK, FakeAzure

OID = "aaaaaaaa-1111-4222-8333-444444444444"
OTHER = "11111111-2222-3333-4444-555555555555"
SUB = "bbbbbbbb-2222-4333-9444-555555555555"
GROUP = "meternaut-sc-rg"
TENANT = "cccccccc-1111-4222-8333-444444444444"
CLIENT = "dddddddd-1111-4222-8333-444444444444"
ASSERTION_CLIENT = "eeeeeeee-1111-4222-8333-444444444444"
HOST = "console.example.test"
SETTINGS = SigninSettings(TENANT, CLIENT, ASSERTION_CLIENT, HOST)
APPROVAL = ApprovalSettings(change_group=GROUP)
APPROVER = Principal(OID, "Tino", ("owner", "approver", "ops"))
ACCESS = "ey" + "A" * 60 + ".ARM-ACCESS-TOKEN-THAT-MUST-NEVER-BE-KEPT." + "B" * 40
VERIFIER = "v" * 43
NONCE = "n" * 22
CODE = "C" * 40
NOW = dt.datetime(2026, 11, 5, 9, 0, 0, tzinfo=dt.timezone.utc)


def jwt(claims: dict) -> str:
    def part(data) -> str:
        return base64.urlsafe_b64encode(json.dumps(data).encode()).rstrip(b"=").decode()

    return f"{part({'alg': 'RS256', 'typ': 'JWT'})}.{part(claims)}.c2lnbmF0dXJl"


def good_claims(**changes) -> dict:
    claims = {"oid": OID, "tid": TENANT, "aud": CLIENT, "nonce": NONCE, "iss": f"https://login.microsoftonline.com/{TENANT}/v2.0", "exp": int(NOW.timestamp()) + 3600}
    claims.update(changes)
    return claims


def token_answer(**changes) -> dict:
    answer = {"token_type": "Bearer", "scope": "https://management.azure.com/user_impersonation", "expires_in": 3599, "access_token": ACCESS,
              "id_token": jwt(good_claims())}
    answer.update(changes)
    return answer


class FakeEntra:
    """The token endpoint of Microsoft Entra: it keeps every request and answers what a test says."""

    def __init__(self):
        self.calls: list[dict] = []
        self.status = 200
        self.body: object = token_answer()
        self.network_error = False

    def transport(self, method, url, headers, data, timeout):
        self.calls.append({"method": method, "url": url, "headers": dict(headers), "form": {k: v[0] for k, v in parse_qs((data or b"").decode()).items()}})
        if self.network_error:
            raise OSError("down")
        return self.status, {}, json.dumps(self.body).encode()


def oauth_error(error: str, description: str) -> dict:
    return {"error": error, "error_description": description, "error_codes": [1], "trace_id": "trace-0000", "correlation_id": "corr-0000"}


class Clock:
    def __init__(self):
        self.now = NOW

    def __call__(self):
        return self.now

    def advance(self, **kwargs):
        self.now += dt.timedelta(**kwargs)


class ThePkceAndTheAddress(unittest.TestCase):
    def test_the_verifier_is_long_enough_and_the_challenge_is_its_sha256(self):
        verifier, challenge = new_pkce()
        self.assertRegex(verifier, r"^[A-Za-z0-9_-]{43}$")
        self.assertEqual(challenge, base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode())
        self.assertNotEqual(new_pkce()[0], verifier)

    def test_the_address_asks_for_the_arm_permission_with_pkce_and_no_refresh_token(self):
        url = authorize_url(SETTINGS, "state-value", "challenge-value", "nonce-value", "tino@example.com")
        parts = urlsplit(url)
        self.assertEqual((parts.scheme, parts.netloc, parts.path), ("https", "login.microsoftonline.com", f"/{TENANT}/oauth2/v2.0/authorize"))
        query = {k: v[0] for k, v in parse_qs(parts.query).items()}
        self.assertEqual(query, {"client_id": CLIENT, "response_type": "code", "redirect_uri": f"https://{HOST}/arm/return", "response_mode": "query",
                                 "scope": f"openid profile {ARM_SCOPE}", "state": "state-value", "nonce": "nonce-value", "code_challenge": "challenge-value",
                                 "code_challenge_method": "S256", "login_hint": "tino@example.com"})
        self.assertNotIn("offline_access", url, "no refresh token is asked for")
        self.assertNotIn("prompt", query)
        self.assertIn("openid%20profile%20https%3A%2F%2Fmanagement.azure.com%2Fuser_impersonation", url)

    def test_a_hint_that_is_not_an_address_is_left_out(self):
        for hint in ("", "person_example.com#EXT#@tenant.onmicrosoft.com", "a b@example.com", "x" * 300, "<script>@example.com"):
            with self.subTest(hint=hint):
                self.assertNotIn("login_hint", authorize_url(SETTINGS, "s", "c", "n", hint))

    def test_the_redirect_address_is_the_consoles_own(self):
        self.assertEqual(SETTINGS.redirect_uri, f"https://{HOST}/arm/return")
        self.assertEqual(SETTINGS.token_url, f"https://login.microsoftonline.com/{TENANT}/oauth2/v2.0/token")


class TheTokenCalls(unittest.TestCase):
    def test_the_one_call_is_a_post_to_the_token_endpoint_of_the_tenant(self):
        client = Client(token_calls(SETTINGS), lambda t: t, transport=lambda *a: (200, {}, b"{}"), sleep=lambda s: None, monotonic=lambda: 0.0)
        client.request("POST", SETTINGS.token_url, form={"a": "b"})
        for method, url in (("GET", SETTINGS.token_url), ("POST", SETTINGS.token_url.replace(TENANT, OTHER)), ("POST", "https://example.com/oauth2/v2.0/token"),
                            ("POST", f"https://login.microsoftonline.com/{TENANT}/oauth2/v2.0/authorize"), ("DELETE", SETTINGS.token_url),
                            ("POST", f"https://management.azure.com/subscriptions/{SUB}")):
            with self.subTest(method=method, url=url):
                with self.assertRaises(Refused):
                    client.request(method, url)

    def test_a_form_is_sent_as_a_form_and_a_call_has_one_kind_of_body(self):
        seen = []
        client = Client(token_calls(SETTINGS), lambda t: t, transport=lambda m, u, h, d, t: (seen.append((h, d)), (200, {}, b"{}"))[1], sleep=lambda s: None,
                        monotonic=lambda: 0.0)
        client.request("POST", SETTINGS.token_url, form={"grant_type": "authorization_code", "code": "a b&c"})
        headers, data = seen[0]
        self.assertEqual(headers["Content-Type"], "application/x-www-form-urlencoded")
        self.assertEqual(data, b"grant_type=authorization_code&code=a+b%26c")
        with self.assertRaises(ValueError):
            client.request("POST", SETTINGS.token_url, form={"a": "b"}, body={"c": "d"})


class TheTokenClient(unittest.TestCase):
    def setUp(self):
        self.entra = FakeEntra()
        self.assertions = []
        client = Client(token_calls(SETTINGS), lambda t: t, transport=self.entra.transport, sleep=lambda s: None, monotonic=lambda: 0.0)
        self.redeem = TokenClient(SETTINGS, lambda resource: (self.assertions.append(resource), "ASSERTION-OF-THE-MANAGED-IDENTITY")[1], client).redeem

    def test_the_code_is_redeemed_with_the_federated_assertion_and_the_verifier_and_no_secret(self):
        tokens = self.redeem(CODE, VERIFIER)
        self.assertEqual(self.assertions, ["api://AzureADTokenExchange"])
        call = self.entra.calls[0]
        self.assertEqual((call["method"], call["url"]), ("POST", SETTINGS.token_url))
        self.assertEqual(call["form"], {
            "client_id": CLIENT, "scope": f"openid profile {ARM_SCOPE}", "code": CODE, "redirect_uri": f"https://{HOST}/arm/return", "grant_type": "authorization_code",
            "code_verifier": VERIFIER, "client_assertion_type": "urn:ietf:params:oauth:client-assertion-type:jwt-bearer",
            "client_assertion": "ASSERTION-OF-THE-MANAGED-IDENTITY"})
        self.assertNotIn("Authorization", call["headers"], "the call has no credential of its own besides the assertion")
        self.assertEqual(tokens.access_token, ACCESS)
        self.assertEqual((tokens.claims["oid"], tokens.claims["tid"], tokens.claims["aud"], tokens.claims["nonce"]), (OID, TENANT, CLIENT, NONCE))

    def test_the_tokens_do_not_show_the_access_token_in_their_text(self):
        tokens = self.redeem(CODE, VERIFIER)
        self.assertNotIn("ARM-ACCESS-TOKEN", repr(tokens))
        self.assertNotIn("ARM-ACCESS-TOKEN", str(tokens))

    def test_the_call_is_made_once_whatever_the_answer_because_a_code_is_used_once(self):
        for status in (429, 500, 503):
            with self.subTest(status=status):
                self.setUp()
                self.entra.status, self.entra.body = status, oauth_error("temporarily_unavailable", "AADSTS90033: later")
                with self.assertRaises(SigninError):
                    self.redeem(CODE, VERIFIER)
                self.assertEqual(len(self.entra.calls), 1)
        self.setUp()
        self.entra.network_error = True
        with self.assertRaises(SigninError) as raised:
            self.redeem(CODE, VERIFIER)
        self.assertEqual(len(self.entra.calls), 1)
        self.assertIn("did not answer", raised.exception.plain)

    def test_each_kind_of_error_of_entra_is_said_in_plain_words_without_its_description(self):
        for aadsts, error, expected in (
                ("65001", "invalid_grant", "has not given consent yet"), ("90094", "consent_required", "has not given consent yet"),
                ("50076", "interaction_required", "multifactor"), ("53003", "access_denied", "Conditional Access"), ("70008", "invalid_grant", "code was used already"),
                ("54005", "invalid_grant", "code was used already"), ("700016", "unauthorized_client", "set-up"), ("70021", "invalid_client", "set-up"),
                ("50011", "invalid_request", "set-up"), ("99999", "invalid_request", "AADSTS99999")):
            with self.subTest(aadsts=aadsts):
                self.setUp()
                self.entra.status = 400
                self.entra.body = oauth_error(error, f"AADSTS{aadsts}: the secret details of the user someone@example.com and app {CLIENT} Trace ID: 12345")
                with self.assertRaises(SigninError) as raised:
                    self.redeem(CODE, VERIFIER)
                text = raised.exception.plain
                self.assertIn(expected, text)
                self.assertIn("Nothing is approved", text)
                for leaked in ("someone@example.com", CLIENT, "Trace ID", "secret details"):
                    self.assertNotIn(leaked, text)

    def test_an_assertion_that_the_platform_cannot_give_is_a_fault_on_our_side(self):
        def broken(resource):
            raise RuntimeError("the identity endpoint is down")

        client = Client(token_calls(SETTINGS), lambda t: t, transport=self.entra.transport, sleep=lambda s: None, monotonic=lambda: 0.0)
        with self.assertRaises(SigninError) as raised:
            TokenClient(SETTINGS, broken, client).redeem(CODE, VERIFIER)
        self.assertIn("fault on my side", raised.exception.plain)
        self.assertNotIn("identity endpoint", raised.exception.plain)
        self.assertEqual(self.entra.calls, [], "no call is made without an assertion")

    def test_an_answer_that_is_not_what_was_asked_for_is_refused(self):
        for label, body in {
            "no tokens": {"token_type": "Bearer"},
            "no id token": token_answer(id_token=None),
            "a short access token": token_answer(access_token="short"),
            "not a bearer token": token_answer(token_type="mac"),
            "another permission": token_answer(scope="https://graph.microsoft.com/User.Read"),
            "an id token that cannot be read": token_answer(id_token="not-a-token"),
            "an id token that is not JSON": token_answer(id_token="a.b.c"),
            "not an object": ["list"],
        }.items():
            with self.subTest(label):
                self.setUp()
                self.entra.body = body
                with self.assertRaises(SigninError) as raised:
                    self.redeem(CODE, VERIFIER)
                self.assertIn("Nothing is approved", raised.exception.plain)

    def test_a_scope_that_is_not_in_the_answer_is_not_an_error_by_itself(self):
        body = token_answer()
        del body["scope"]
        self.entra.body = body
        self.assertEqual(self.redeem(CODE, VERIFIER).access_token, ACCESS)

    def test_a_client_that_may_not_call_the_endpoint_gives_a_fault_on_our_side(self):
        client = Client((), lambda t: t, transport=self.entra.transport, sleep=lambda s: None, monotonic=lambda: 0.0)
        with self.assertRaises(SigninError) as raised:
            TokenClient(SETTINGS, lambda r: "a", client).redeem(CODE, VERIFIER)
        self.assertIn("fault on my side", raised.exception.plain)


class TheWordsOfTheErrors(unittest.TestCase):
    def test_a_name_and_a_number_that_are_not_known_are_shown_as_they_are_and_nothing_else(self):
        self.assertEqual(explain("weird_error", "123456"), "Microsoft Entra did not give a token (weird_error, AADSTS123456). Nothing is approved.")
        self.assertEqual(explain("", ""), "Microsoft Entra did not give a token. Nothing is approved.")

    def test_the_name_is_cleaned_before_it_is_shown(self):
        text = explain("<script>alert(1)</script>_x", "12<b>34")
        self.assertNotIn("<", text)

    def test_cancelling_the_sign_in_is_said_as_such(self):
        self.assertIn("cancelled or refused", explain("access_denied", ""))


class TheSettings(unittest.TestCase):
    ENV = {"STORE_ACCOUNT_NAME": "stexample", "CHANGE_RESOURCE_GROUP": GROUP, "CHANGE_SUBSCRIPTION_ID": SUB, "CONSOLE_HOST": HOST}

    def test_the_sign_in_is_there_only_when_all_three_settings_are(self):
        full = {**self.ENV, "SIGNIN_TENANT_ID": TENANT, "SIGNIN_CLIENT_ID": CLIENT, "OVERRIDE_USE_MI_FIC_ASSERTION_CLIENTID": ASSERTION_CLIENT}
        self.assertEqual(settings_of(loop_config.load(full)), SETTINGS)
        self.assertIsNone(settings_of(loop_config.load(self.ENV)))
        with self.assertRaises(loop_config.LoopConfigError):
            loop_config.load({**self.ENV, "SIGNIN_TENANT_ID": TENANT})


class Flow(unittest.TestCase):
    """The two steps of an approval over a real store, real approvals and the real change, with a fake token endpoint and a fake Resource Manager."""

    def setUp(self):
        self.clock = Clock()
        self.store = MemoryStore(clock=self.clock)
        self.azure = FakeAzure()
        self.approvals = Approvals(self.store, APPROVAL, self.clock)
        item = Lead(detector="orphan-managed-disk", resource_id=DISK, resource_type="microsoft.compute/disks", name="planted-disk-1", resource_group=GROUP,
                    subscription_id=SUB, location="swedencentral", tags={"meternaut-planted": "demo"}, managed_by="", facts={}, age_days=0)
        case = CaseRecord(case_id="k" + item.lead_id, resource_id=DISK, resource_name="planted-disk-1", resource_type=item.resource_type, resource_group=GROUP,
                          subscription_id=SUB, detector="orphan-managed-disk", run_id="r1", status="proposed", recommendation="delete", confidence=0.9,
                          updated_at=stamp(NOW), first_seen_at=stamp(NOW))
        self.store.case_put(case)
        self.plan = self.approvals.create(case, item, (OID,))
        self.events: list[tuple[str, dict]] = []
        self.redeemed: list[tuple[str, str]] = []
        self.tokens_used: list[str] = []
        self.claims = good_claims()
        self.redeem_error: SigninError | None = None
        self.delegation = self.make_delegation()

    def make_delegation(self, signin=SETTINGS, store=None):
        def redeem(code, verifier):
            self.redeemed.append((code, verifier))
            if self.redeem_error is not None:
                raise self.redeem_error
            return Tokens(ACCESS, dict(self.claims))

        def run(token):
            self.tokens_used.append(token)
            client = Client(change_calls(SUB, GROUP), lambda t: t, transport=self.azure.transport, sleep=lambda s: None, monotonic=lambda: 0.0)
            return RunnerServices(store or self.store, client, lambda resource: token, APPROVAL, SUB, clock=self.clock, sleep=lambda s: None,
                                  emit=lambda kind, **f: self.events.append((kind, f)))

        return Delegation(store or self.store, self.approvals, signin, redeem, run, emit=lambda kind, **f: self.events.append((kind, f)),
                          pkce=lambda: (VERIFIER, base64.urlsafe_b64encode(hashlib.sha256(VERIFIER.encode()).digest()).rstrip(b"=").decode()), token=lambda n: NONCE)

    def begin(self, who=APPROVER, code=None, nonce=None, note="", hint="", delegation=None):
        token = self.store.nonce_new(who.oid, self.plan.plan_id) if nonce is None else nonce
        return (delegation or self.delegation).begin(who, self.plan.plan_id, self.plan.code if code is None else code, token, note, hint)

    @staticmethod
    def state_of(begun):
        return parse_qs(urlsplit(begun.location).query)["state"][0]

    def back(self, state, who=APPROVER, **query):
        return self.delegation.finish(who, {"code": CODE, "state": state, **query})

    def whole(self, **kwargs):
        """The whole way: the form, the sign-in, the return."""
        begun = self.begin(**kwargs)
        self.assertEqual(begun.refusal, None, begun.refusal)
        return self.back(self.state_of(begun))


class BeginningAnApproval(Flow):
    def test_a_good_form_gives_the_address_of_the_sign_in_and_records_nothing(self):
        begun = self.begin(note="go ahead", hint="tino@example.com")
        self.assertIsNone(begun.refusal)
        query = {k: v[0] for k, v in parse_qs(urlsplit(begun.location).query).items()}
        self.assertEqual((query["client_id"], query["nonce"], query["login_hint"], query["code_challenge_method"]), (CLIENT, NONCE, "tino@example.com", "S256"))
        self.assertEqual(self.store.plan_get(self.plan.plan_id).state, "open")
        self.assertEqual(self.store.decisions_of_plan(self.plan.plan_id), [])
        self.assertIsNone(self.store.action_get(self.plan.plan_id))
        self.assertEqual(self.events, [("signin.started", {"planId": self.plan.plan_id})])
        self.assertEqual(self.tokens_used, [])
        self.assertEqual(self.azure.calls, [])

    def test_what_is_kept_for_the_return_is_on_the_server_for_this_person_and_this_plan_only(self):
        begun = self.begin(note="go ahead")
        state = self.state_of(begun)
        owner, purpose, expires, data = self.store.nonces[state]
        self.assertEqual((owner, purpose), (OID, "arm-signin"))
        self.assertEqual((expires - NOW).total_seconds(), 600)
        self.assertEqual(json.loads(data), {"plan": self.plan.plan_id, "code": self.plan.code, "resource": self.plan.resource_id, "verifier": VERIFIER, "nonce": NONCE,
                                            "note": "go ahead"})
        self.assertNotIn(VERIFIER, begun.location, "the verifier never leaves the server")

    def test_the_form_token_is_used_up(self):
        token = self.store.nonce_new(OID, self.plan.plan_id)
        self.assertIsNone(self.begin(nonce=token).refusal)
        again = self.begin(nonce=token)
        self.assertEqual((again.location, again.refusal.kind), ("", "error"))

    def test_every_refusal_of_the_form_is_a_page_and_changes_nothing(self):
        for label, kwargs, kind in (
                ("a wrong code", {"code": "00000000"}, "refused_code"), ("another person", {"who": Principal(OTHER, "Other", ("approver",))}, "refused_role"),
                ("a person without the role", {"who": Principal(OID, "Tino", ("owner",))}, "refused_role"), ("a form token that is not valid", {"nonce": "x" * 30}, "error")):
            with self.subTest(label):
                begun = self.begin(**kwargs)
                self.assertEqual((begun.location, begun.refusal.kind), ("", kind))
        self.assertEqual(self.store.nonces.keys() - {n for n in self.store.nonces if self.store.nonces[n][1] == self.plan.plan_id}, set(), "no sign-in state was made")
        self.assertEqual(self.store.plan_get(self.plan.plan_id).state, "open")
        self.assertEqual(self.events, [])

    def test_a_pulled_switch_stops_the_approval_before_the_sign_in(self):
        self.store.switch_put(SwitchRecord(name="changes", paused=True))
        self.assertEqual(self.begin().refusal.kind, "refused_paused")

    def test_a_plan_that_expired_or_was_closed_is_refused(self):
        self.clock.advance(hours=73)
        self.assertEqual(self.begin().refusal.kind, "expired")
        self.setUp()
        self.store.plan_put(replace(self.plan, state="declined"))
        self.assertEqual(self.begin().refusal.kind, "refused_state")

    def test_without_the_settings_of_the_sign_in_nobody_can_approve(self):
        begun = self.begin(delegation=self.make_delegation(signin=None))
        self.assertEqual((begun.location, begun.refusal.kind), ("", "error"))
        self.assertIn("not set up", begun.refusal.message)

    def test_a_store_that_fails_when_the_state_is_kept_is_an_error_that_approves_nothing(self):
        class Failing(MemoryStore):
            def nonce_new(self, oid, purpose, ttl_seconds=3600, data=""):
                if purpose == "arm-signin":
                    raise StoreError("down", 503)
                return super().nonce_new(oid, purpose, ttl_seconds, data)

        self.store.__class__ = Failing
        begun = self.begin()
        self.assertEqual((begun.location, begun.refusal.kind), ("", "error"))
        self.assertIn("Nothing is approved", begun.refusal.message)

    def test_a_note_that_is_too_long_is_cut_and_a_hint_that_is_not_an_address_is_left_out(self):
        begun = self.begin(note="x" * 1000, hint="person_example.com#EXT#@tenant.onmicrosoft.com")
        self.assertNotIn("login_hint", begun.location)
        self.assertEqual(len(json.loads(self.store.nonces[self.state_of(begun)][3])["note"]), 300)


class ReturningFromTheSignIn(Flow):
    def test_the_whole_way_records_the_approval_and_makes_the_change_with_the_persons_own_token(self):
        result = self.whole(note="go ahead")
        self.assertEqual((result.ok, result.kind), (True, "ran"))
        self.assertEqual(result.message, "Deleted. Azure no longer lists the resource.")
        self.assertEqual(result.plan.plan_id, self.plan.plan_id)
        self.assertEqual(self.redeemed, [(CODE, VERIFIER)])
        self.assertEqual(self.tokens_used, [ACCESS])
        self.assertTrue(self.azure.headers and all(h["Authorization"] == f"Bearer {ACCESS}" for h in self.azure.headers))
        self.assertEqual([m for m, _ in self.azure.calls].count("DELETE"), 1)
        self.assertNotIn(DISK.lower(), self.azure.resources)
        decisions = self.store.decisions_of_plan(self.plan.plan_id)
        self.assertEqual([(d.decision, d.approver_oid, d.note) for d in decisions], [("approve", OID, "go ahead")])
        self.assertEqual(self.store.plan_get(self.plan.plan_id).state, "consumed")
        self.assertEqual(self.store.action_get(self.plan.plan_id).state, "done")
        self.assertEqual(self.store.case_get(self.plan.case_id).status, "done")
        self.assertEqual([kind for kind, _ in self.events], ["signin.started", "approval.recorded", "action.started", "action.finished"])

    def test_the_access_token_is_in_no_record_no_result_and_no_event(self):
        result = self.whole()
        everything = json.dumps([
            result.message, [e for e in self.events], self.store.plan_get(self.plan.plan_id).to_json(), self.store.action_get(self.plan.plan_id).to_json(),
            [d.to_json() for d in self.store.decisions_of_plan(self.plan.plan_id)], self.store.case_get(self.plan.case_id).to_json(), sorted(self.store.nonces.values(), key=str),
        ], default=str)
        self.assertNotIn("ARM-ACCESS-TOKEN", everything)
        self.assertNotIn(ACCESS, everything)

    def test_a_person_whom_azure_does_not_let_delete_gets_a_refusal_and_the_resource_stays(self):
        self.azure.delete_status = 403
        result = self.whole()
        self.assertEqual((result.ok, result.kind), (False, "azure_refused"))
        self.assertIn("Azure refused to delete the resource (403, AuthorizationFailed)", result.message)
        self.assertIn(DISK.lower(), self.azure.resources)
        self.assertEqual([d.decision for d in self.store.decisions_of_plan(self.plan.plan_id)], ["approve"], "the approval itself is recorded")
        self.assertEqual(self.store.plan_get(self.plan.plan_id).state, "failed")

    def test_a_delete_that_azure_took_but_that_still_shows_is_not_confirmed_yet(self):
        self.azure.reads_before_gone = 99
        result = self.whole()
        self.assertEqual((result.ok, result.kind), (True, "ran_unconfirmed"))
        self.assertIn("still lists the resource", result.message)

    def test_a_resource_that_changed_since_the_plan_stops_the_change_after_the_approval_is_recorded(self):
        self.azure.resources[DISK.lower()]["properties"]["diskState"] = "Attached"
        result = self.whole()
        self.assertEqual((result.ok, result.kind), (False, "stopped"))
        self.assertIn("not unattached any more", result.message)
        self.assertIn(DISK.lower(), self.azure.resources)
        self.assertNotIn("DELETE", [m for m, _ in self.azure.calls])

    def test_the_state_is_used_once(self):
        begun = self.begin()
        state = self.state_of(begun)
        self.assertEqual(self.back(state).kind, "ran")
        again = self.back(state)
        self.assertEqual((again.ok, again.kind), (False, "refused_state"))
        self.assertIn("not valid any more", again.message)
        self.assertEqual(len(self.redeemed), 1, "the code is not redeemed twice")

    def test_a_state_that_belongs_to_another_person_is_refused_and_stays_usable_for_its_owner(self):
        state = self.state_of(self.begin())
        stranger = Principal(OTHER, "Other", ("approver",))
        refused = self.delegation.finish(stranger, {"code": CODE, "state": state})
        self.assertEqual(refused.kind, "refused_state")
        self.assertEqual(self.redeemed, [])
        self.assertEqual(self.back(state).kind, "ran")

    def test_a_state_that_is_unknown_malformed_or_missing_is_refused_without_redeeming_anything(self):
        for state in ("", "short", "x" * 30, "../etc/passwd", "a" * 100):
            with self.subTest(state=state):
                self.assertEqual(self.delegation.finish(APPROVER, {"code": CODE, "state": state}).kind, "refused_state")
        self.assertEqual(self.delegation.finish(APPROVER, {"code": CODE}).kind, "refused_state")
        self.assertEqual(self.redeemed, [])

    def test_a_state_that_ran_out_of_time_is_refused(self):
        state = self.state_of(self.begin())
        self.clock.advance(minutes=11)
        self.assertEqual(self.back(state).kind, "refused_state")
        self.assertEqual(self.redeemed, [])

    def test_what_was_kept_for_the_state_must_be_what_begin_wrote(self):
        for data in ("not json", "[]", json.dumps({"plan": "p"}), json.dumps({"plan": 1, "code": "c", "resource": "r", "verifier": "v", "nonce": "n", "note": ""}),
                     json.dumps({"plan": "p", "code": "c", "verifier": "v", "nonce": "n", "note": ""})):
            with self.subTest(data=data):
                state = self.store.nonce_new(OID, "arm-signin", 600, data)
                self.assertEqual(self.back(state).kind, "refused_state")
        self.assertEqual(self.redeemed, [])

    def test_a_plan_that_names_another_resource_than_the_one_that_was_approved_is_refused_before_the_code_is_redeemed(self):
        state = self.state_of(self.begin())
        other = DISK.replace("planted-disk-1", "planted-disk-2")
        self.store.plan_put(replace(self.store.plan_get(self.plan.plan_id), resource_id=other))
        result = self.back(state)
        self.assertEqual((result.ok, result.kind), (False, "refused_code"))
        self.assertEqual(self.redeemed, [])
        self.assertEqual(self.azure.calls, [])
        self.assertEqual(self.store.decisions_of_plan(self.plan.plan_id), [])

    def test_a_person_who_cancelled_or_was_refused_at_the_sign_in_leaves_the_request_open(self):
        for error, description, expected in (("access_denied", "AADSTS65004: the user declined to consent", "cancelled or refused"),
                                             ("consent_required", "AADSTS65001: consent", "has not given consent yet"),
                                             ("interaction_required", "AADSTS50076: mfa", "multifactor"),
                                             ("access_denied", "AADSTS53003: blocked by Conditional Access", "Conditional Access")):
            with self.subTest(error=error, description=description):
                self.setUp()
                state = self.state_of(self.begin())
                result = self.back(state, error=error, error_description=description)
                self.assertEqual((result.ok, result.kind), (False, "signin_failed"))
                self.assertIn(expected, result.message)
                self.assertIn("Nothing is approved", result.message)
                self.assertEqual(result.plan.plan_id, self.plan.plan_id)
                self.assertEqual(self.store.plan_get(self.plan.plan_id).state, "open")
                self.assertEqual(self.store.decisions_of_plan(self.plan.plan_id), [])
                self.assertEqual(self.redeemed, [])
                self.assertIn(("signin.failed", {"planId": self.plan.plan_id, "reason": error}), self.events)

    def test_the_text_of_an_error_description_is_never_shown(self):
        state = self.state_of(self.begin())
        result = self.back(state, error="invalid_request", error_description=f"AADSTS70000: details for someone@example.com {CLIENT} <script>")
        self.assertNotIn("someone@example.com", result.message)
        self.assertNotIn("<script>", result.message)

    def test_a_return_without_a_usable_code_is_a_failed_sign_in(self):
        for code in ("", "short", "has spaces in the code that is long enough", "<script>" + "a" * 30, "a" * 5000):
            with self.subTest(code=code):
                self.setUp()
                state = self.state_of(self.begin())
                result = self.delegation.finish(APPROVER, {"code": code, "state": state})
                self.assertEqual((result.ok, result.kind), (False, "signin_failed"))
                self.assertEqual(self.redeemed, [])
                self.assertEqual(self.store.decisions_of_plan(self.plan.plan_id), [])

    def test_a_code_that_cannot_be_redeemed_leaves_the_request_open_and_says_why(self):
        self.redeem_error = SigninError("The sign-in took too long, or its code was used already. Nothing is approved.")
        result = self.whole()
        self.assertEqual((result.ok, result.kind), (False, "signin_failed"))
        self.assertIn("took too long", result.message)
        self.assertEqual(self.store.plan_get(self.plan.plan_id).state, "open")
        self.assertEqual(self.store.decisions_of_plan(self.plan.plan_id), [])
        self.assertEqual(self.azure.calls, [])
        self.assertIn(("signin.failed", {"planId": self.plan.plan_id, "reason": "redeem"}), self.events)

    def test_a_sign_in_that_is_not_the_persons_is_refused_before_anything_is_recorded_or_changed(self):
        for label, claims, expected in (
                ("another account", {"oid": OTHER}, "another account"), ("another tenant", {"tid": OTHER}, "another tenant"),
                ("another client", {"aud": OTHER}, "does not belong to the request"), ("another request", {"nonce": "other-nonce"}, "does not belong to the request"),
                ("no object id", {"oid": None}, "another account"), ("no nonce", {"nonce": None}, "does not belong to the request")):
            with self.subTest(label):
                self.setUp()
                self.claims = good_claims(**claims)
                result = self.whole()
                self.assertEqual((result.ok, result.kind), (False, "signin_failed"))
                self.assertIn(expected, result.message)
                self.assertEqual(self.store.plan_get(self.plan.plan_id).state, "open")
                self.assertEqual(self.store.decisions_of_plan(self.plan.plan_id), [])
                self.assertEqual(self.azure.calls, [])
                self.assertEqual(self.tokens_used, [], "the token is not even used")
                self.assertIn(("signin.failed", {"planId": self.plan.plan_id, "reason": "identity"}), self.events)

    def test_the_object_id_is_compared_without_regard_to_case(self):
        self.claims = good_claims(oid=OID.upper(), tid=TENANT.upper(), aud=CLIENT.upper(), iss=f"https://login.microsoftonline.com/{TENANT.upper()}/v2.0")
        self.assertEqual(self.whole().kind, "ran")

    def test_an_identity_token_from_another_endpoint_or_one_that_is_expired_or_has_no_time_is_refused(self):
        late = int(NOW.timestamp()) - 1
        for label, claims in (("another endpoint", {"iss": f"https://login.microsoftonline.com/{OTHER}/v2.0"}), ("a v1 issuer", {"iss": f"https://sts.windows.net/{TENANT}/"}),
                              ("another host", {"iss": f"https://login.example.test/{TENANT}/v2.0"}), ("no issuer", {"iss": None}), ("expired", {"exp": late}),
                              ("no time", {"exp": None}), ("a time as text", {"exp": str(int(NOW.timestamp()) + 3600)}), ("a time that is true", {"exp": True})):
            with self.subTest(label):
                self.setUp()
                self.claims = good_claims(**claims)
                result = self.whole()
                self.assertEqual((result.ok, result.kind), (False, "signin_failed"))
                self.assertIn("not one that this console accepts", result.message)
                self.assertEqual(self.store.decisions_of_plan(self.plan.plan_id), [])
                self.assertEqual(self.azure.calls, [])

    def test_a_nonce_with_characters_outside_ascii_is_a_refusal_and_not_a_crash(self):
        self.claims = good_claims(nonce="\u00e9" * 22)
        result = self.whole()
        self.assertEqual((result.ok, result.kind), (False, "signin_failed"))
        self.assertIn("does not belong to the request", result.message)

    def test_a_plan_that_changed_while_the_person_signed_in_is_refused_before_the_code_is_redeemed(self):
        for label, change, kind in (("declined", lambda: self.store.plan_put(replace(self.store.plan_get(self.plan.plan_id), state="declined")), "refused_state"),
                                    ("a new code", lambda: self.store.plan_put(replace(self.store.plan_get(self.plan.plan_id), code="ABCD1234")), "refused_code"),
                                    ("expired", lambda: (self.store.plan_put(replace(self.store.plan_get(self.plan.plan_id), expires_at=stamp(NOW + dt.timedelta(minutes=1)))),
                                                         self.clock.advance(minutes=5)), "expired"),
                                    ("paused", lambda: self.store.switch_put(SwitchRecord(name="all", paused=True)), "refused_paused")):
            with self.subTest(label):
                self.setUp()
                state = self.state_of(self.begin())
                change()
                result = self.back(state)
                self.assertEqual((result.ok, result.kind), (False, kind))
                self.assertEqual(self.redeemed, [], "the code is not spent for a request that cannot be approved")
                self.assertEqual(self.azure.calls, [])

    def test_an_approver_who_decided_already_cannot_make_the_change_again(self):
        state = self.state_of(self.begin())
        self.store.decision_put(DecisionRecord(self.plan.plan_id, OID, "Tino", "approve", stamp(NOW), self.plan.code))
        result = self.back(state)
        self.assertEqual((result.ok, result.kind), (False, "duplicate"))
        self.assertEqual(self.azure.calls, [])
        self.assertEqual(self.tokens_used, [])

    def test_a_store_that_fails_when_the_state_is_taken_is_an_error_that_changes_nothing(self):
        state = self.state_of(self.begin())

        class Failing(MemoryStore):
            def nonce_take(self, token, oid, purpose):
                raise StoreError("down", 503)

        self.store.__class__ = Failing
        result = self.back(state)
        self.assertEqual((result.ok, result.kind), (False, "error"))
        self.assertEqual(self.redeemed, [])

    def test_a_store_that_fails_during_the_change_says_to_look_at_the_resource(self):
        state = self.state_of(self.begin())
        original = self.delegation.run

        def run(token):
            raise StoreError("down", 503)

        self.delegation.run = run
        result = self.back(state)
        self.delegation.run = original
        self.assertEqual((result.ok, result.kind), (False, "error"))
        self.assertIn("Look at the resource in Azure", result.message)

    def test_without_the_settings_of_the_sign_in_the_return_changes_nothing(self):
        delegation = self.make_delegation(signin=None)
        result = delegation.finish(APPROVER, {"code": CODE, "state": "s" * 30})
        self.assertEqual((result.ok, result.kind), (False, "error"))
        self.assertEqual(self.redeemed, [])

    def test_the_change_is_never_made_for_a_plan_without_a_recorded_approval(self):
        # The recorded approval is what the change looks for: without it the change stops, whatever the sign-in said.
        state = self.state_of(self.begin())
        original = self.approvals.record_approval

        def forget(principal, plan, note):
            result, action = original(principal, plan, note)
            self.store.decisions.clear()
            return result, action

        self.approvals.record_approval = forget
        result = self.back(state)
        self.assertEqual((result.ok, result.kind), (False, "failed"))
        self.assertIn(DISK.lower(), self.azure.resources)
        self.assertNotIn("DELETE", [m for m, _ in self.azure.calls])


if __name__ == "__main__":
    unittest.main()
