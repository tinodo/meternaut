"""Making a change as the person who approved it: the person signs in to Azure Resource Manager, and the change is made with that person's own token.

Meternaut holds no right to change Azure. The flow is the OAuth 2.0 authorization code flow with PKCE for a web app, with a delegated permission:

1. The approve form is checked (the person, the plan, its code, the switches, the one-time token of the form). Nothing is recorded yet. The person is sent to
   Microsoft Entra with the console's own app registration, the scope `user_impersonation` of Azure Resource Manager and no `offline_access`, so that no
   refresh token exists. A `state` (one use, bound to the person, the plan and the digest of the plan, kept on the server for ten minutes), a PKCE verifier and a nonce are
   made. The digest is the SHA-256 of every field of the plan but its state (cases/families/digest.py).
2. Entra sends the person back to `/arm/return`. The `state` is used once, and only by the person it was made for.
3. The code is redeemed with the app registration's federated identity credential: a token of a managed identity of the app, for `api://AzureADTokenExchange`,
   is the client assertion. There is no secret and no certificate anywhere. The ID token must name the same person (object id), the same tenant, this client
   and the nonce of the request, come from this tenant's endpoint and not be expired, or nothing is recorded. The plan is read again, and its digest must be the one that the
   state holds: a plan that changed while the person signed in is refused, and nothing is approved.
4. Only then the approval is recorded, and the change is made with the person's access token (runner.py): the family of the plan re-reads the resource and the locks, the runner
   compares the digest once more and makes the one change of the family (a delete, a stop, a resize, a change of tier), and follows it until Azure says that it is done. A change that
   Azure carries out later is `running` when the person's request ends, and the timer settles it by reading. Azure checks the person's own rights, and the Activity Log shows the person.
5. A person who signed in without the multifactor check that a change needs can use the console, but Azure answers the write with a claims challenge (HTTP 401 and a
   `www-authenticate` header that asks for more claims). That is a step-up and not a refusal: nothing was changed, the plan stays approved and its action waits in the
   queue. The person is sent to Microsoft Entra once more, with the claims request that Azure gave, in a new state with a new PKCE verifier and a new nonce. The return of
   that second sign-in records no second approval: it checks that the approval is recorded and the action waits, redeems the code, checks the ID token as before and makes
   the change once more. A second challenge is final, and a person who cancels the check ends the request: nothing was changed.

The access token lives in memory for this one request. It is never stored, never logged and never put in a page, and what the code may do with it is the list of
calls in runner.py (`change_calls`). Errors say what went wrong in plain words and never carry a token or the text of an error description. The claims request lives in the
state of the second sign-in until it is used (ten minutes at most) and nowhere else: it is not in a record, a page, a log or a line of the History.
"""
from __future__ import annotations

import base64
import hashlib
import json
import re
import secrets
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Callable
from urllib.parse import quote, urlencode

from .approvals import Approvals
from .families import digest as plan_digest
from .http import Client, HttpError, Refused
from .models import ActionRecord, Begun, DecideResult, MAX_SIGNIN_PATH, PlanRecord, Principal, Store, StoreError
from .roles import clean_text
from .runner import RunnerServices, execute
from .store import MAX_NONCE_DATA

if TYPE_CHECKING:
    from .loop_config import LoopSettings

LOGIN_HOST = "login.microsoftonline.com"
ARM_SCOPE = "https://management.azure.com/user_impersonation"
# `profile` is asked for on purpose: the identity token holds the person's object id (`oid`) only with it, and the object id is what ties the person who is signed in
# to this console to the person who signs in to Azure.
SCOPES = f"openid profile {ARM_SCOPE}"
ASSERTION_RESOURCE = "api://AzureADTokenExchange"
ASSERTION_TYPE = "urn:ietf:params:oauth:client-assertion-type:jwt-bearer"
RETURN_PATH = "/arm/return"
PURPOSE = "arm-signin"
SIGNIN_SECONDS = 600
CODE = re.compile(r"[A-Za-z0-9._~+/=-]{20,4096}")
STATE = re.compile(r"[A-Za-z0-9_-]{20,64}")
HINT = re.compile(r"[A-Za-z0-9._%+'-]{1,64}@[A-Za-z0-9.-]{1,200}\.[A-Za-z]{2,24}")
MAX_TOKEN = 16000

CONSENT = frozenset({"65001", "90094", "90095"})
AGAIN = frozenset({"50076", "50079", "50074", "50158"})
POLICY = frozenset({"53000", "53001", "53002", "53003", "53004", "530032"})
USED = frozenset({"70008", "54005", "70000", "9002313"})
SETUP = frozenset({"65005", "70021", "700016", "700025", "700027", "700213", "7000215", "7000222", "50011", "500113"})
STEP_UP_SENT = "Azure asks for an extra sign-in check. You go to Microsoft Entra once more to complete it. Nothing was changed yet."


@dataclass(frozen=True)
class SigninSettings:
    """What the sign-in to Azure needs: the tenant, the console's own app registration, the identity that presents its assertion, and the console's host."""

    tenant_id: str
    client_id: str
    assertion_client_id: str
    console_host: str

    @property
    def redirect_uri(self) -> str:
        return f"https://{self.console_host}{RETURN_PATH}"

    @property
    def authorize_url(self) -> str:
        return f"https://{LOGIN_HOST}/{self.tenant_id}/oauth2/v2.0/authorize"

    @property
    def token_url(self) -> str:
        return f"https://{LOGIN_HOST}/{self.tenant_id}/oauth2/v2.0/token"


def settings_of(loop: "LoopSettings") -> SigninSettings | None:
    """The settings of the sign-in, or None when the loop does not have all three of them (an approval is then refused, and the rest of the loop works)."""
    if not (loop.signin_tenant_id and loop.signin_client_id and loop.signin_assertion_client_id):
        return None
    return SigninSettings(loop.signin_tenant_id, loop.signin_client_id, loop.signin_assertion_client_id, loop.console_host)


def token_calls(settings: SigninSettings) -> tuple[tuple[str, "re.Pattern[str]"], ...]:
    """The one call that the token client makes: a POST to the token endpoint of the tenant."""
    return (("POST", re.compile(re.escape(settings.token_url))),)


class SigninError(Exception):
    """The sign-in gave no usable token. `plain` says why in plain words for the person; it never holds a token or the text of an error description."""

    def __init__(self, plain: str) -> None:
        super().__init__(plain)
        self.plain = plain


@dataclass(frozen=True)
class Tokens:
    """What the token endpoint gave. The access token is for Azure Resource Manager and is never shown: it is not in the text of this object."""

    access_token: str = field(repr=False)
    claims: dict = field(default_factory=dict)


def new_pkce(token: Callable[[int], str] = secrets.token_urlsafe) -> tuple[str, str]:
    """A PKCE verifier (43 characters of a URL-safe alphabet) and its S256 challenge."""
    verifier = token(32)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest()).rstrip(b"=").decode("ascii")
    return verifier, challenge


def authorize_url(settings: SigninSettings, state: str, challenge: str, nonce: str, hint: str = "", claims: str = "") -> str:
    """The address of the sign-in at Microsoft Entra. The redirect address is the console's own and is registered on the app registration.

    `claims` is the claims request that Azure gave in a claims challenge (JSON text). It goes in the `claims` parameter, encoded like every other value."""
    query = {"client_id": settings.client_id, "response_type": "code", "redirect_uri": settings.redirect_uri, "response_mode": "query", "scope": SCOPES,
             "state": state, "nonce": nonce, "code_challenge": challenge, "code_challenge_method": "S256"}
    if hint and HINT.fullmatch(hint):
        query["login_hint"] = hint
    if claims:
        query["claims"] = claims
    return f"{settings.authorize_url}?{urlencode(query, quote_via=quote, safe='')}"


def _claims(token: str) -> dict:
    parts = token.split(".")
    if len(parts) != 3 or len(token) > MAX_TOKEN:
        raise ValueError("not a token")
    document = json.loads(base64.urlsafe_b64decode(parts[1] + "=" * (-len(parts[1]) % 4)).decode("utf-8"))
    if not isinstance(document, dict):
        raise ValueError("not a token")
    return document


def explain(error: str, aadsts: str) -> str:
    """The plain words for an error of Microsoft Entra, from its error name and its AADSTS number. Nothing was approved."""
    error = re.sub(r"[^a-z_]", "", (error or "").lower())[:40]
    aadsts = re.sub(r"\D", "", aadsts or "")[:7]
    if aadsts in CONSENT or error == "consent_required":
        return ("Your tenant has not given consent yet for Meternaut to use Azure on your behalf. A tenant administrator gives it once, for the one permission "
                "Azure Service Management, user_impersonation. Nothing is approved.")
    if aadsts in AGAIN or error in ("interaction_required", "login_required"):
        return "Microsoft Entra needs you to sign in again, with the multifactor check of your tenant. Open the request and press Approve again. Nothing is approved."
    if aadsts in POLICY:
        return "A Conditional Access policy of your tenant did not let this sign-in to Azure through. Nothing is approved."
    if error == "access_denied":
        return "The sign-in to Azure was cancelled or refused. Nothing is approved."
    if aadsts in USED:
        return "The sign-in took too long, or its code was used already. Open the request and press Approve again. Nothing is approved."
    if aadsts in SETUP:
        return (f"Microsoft Entra did not accept the console's own set-up (AADSTS{aadsts}): the redirect address or the federated identity credential of the app "
                "registration is not right. This is a fault of the set-up and not of yours. Nothing is approved.")
    named = " (" + ", ".join(part for part in (error, f"AADSTS{aadsts}" if aadsts else "") if part) + ")" if error or aadsts else ""
    return f"Microsoft Entra did not give a token{named}. Nothing is approved."


def explain_stepup(error: str, aadsts: str) -> str:
    """Why Microsoft Entra did not complete the extra sign-in check, from its error name and its AADSTS number: a sentence that goes after "was not completed"."""
    error = re.sub(r"[^a-z_]", "", (error or "").lower())[:40]
    aadsts = re.sub(r"\D", "", aadsts or "")[:7]
    if aadsts in POLICY:
        return "A Conditional Access policy of your tenant did not let it through."
    if error == "access_denied":
        return "It was cancelled or refused."
    named = " (" + ", ".join(part for part in (error, f"AADSTS{aadsts}" if aadsts else "") if part) + ")" if error or aadsts else ""
    return f"Microsoft Entra did not complete it{named}."


def _oauth_error(error: HttpError) -> tuple[str, str]:
    """The error name and the AADSTS number in the text of a failed call to the token endpoint (http.error_text keeps those two and nothing else)."""
    found = re.search(r": \d{3} ([a-z_]{3,40})(?: AADSTS(\d{3,7}))?\s*$", str(error))
    return (found.group(1), found.group(2) or "") if found else ("", "")


class TokenClient:
    """Redeems the code of a sign-in for tokens. Its own client has one address on its list: the token endpoint of the tenant."""

    def __init__(self, settings: SigninSettings, assertion: Callable[[str], str], client: Client) -> None:
        self.settings, self.assertion, self.client = settings, assertion, client

    def redeem(self, code: str, verifier: str, claims: str = "") -> Tokens:
        """Redeems the code of a sign-in. After a claims challenge the claims request goes with the code too, as the authorization code flow of MSAL does it (Microsoft Learn,
        "Conditional access and claims challenges", MSAL for Python)."""
        try:
            proof = self.assertion(ASSERTION_RESOURCE)
        except Exception as error:  # noqa: BLE001 (the platform gave no token: the text says that and no more)
            raise SigninError("Meternaut could not get its own proof of identity from the platform. This is a fault on my side. Nothing is approved.") from error
        form = {"client_id": self.settings.client_id, "scope": SCOPES, "code": code, "redirect_uri": self.settings.redirect_uri, "grant_type": "authorization_code",
                "code_verifier": verifier, "client_assertion_type": ASSERTION_TYPE, "client_assertion": proof}
        if claims:
            form["claims"] = claims
        try:
            answer = self.client.request("POST", self.settings.token_url, form=form, timeout=30, retries=0, retry_network=False).json()
        except HttpError as error:
            if error.status == 0:
                raise SigninError("Microsoft Entra did not answer. Nothing is approved. Try again in a few minutes.") from error
            raise SigninError(explain(*_oauth_error(error))) from error
        except Refused as error:
            raise SigninError("This app may not call that address. This is a fault on my side. Nothing is approved.") from error
        access, ident = (answer.get("access_token"), answer.get("id_token")) if isinstance(answer, dict) else (None, None)
        if not (isinstance(access, str) and 20 <= len(access) <= MAX_TOKEN and isinstance(ident, str)):
            raise SigninError("Microsoft Entra gave an answer without the tokens that were asked for. Nothing is approved.")
        if str(answer.get("token_type", "")).lower() != "bearer":
            raise SigninError("Microsoft Entra gave a token of a kind that Meternaut does not use. Nothing is approved.")
        granted = str(answer.get("scope", "")).lower()
        if granted and "user_impersonation" not in granted:
            raise SigninError("The sign-in did not give the permission to use Azure on your behalf. Nothing is approved.")
        try:
            claims = _claims(ident)
        except (ValueError, TypeError) as error:
            raise SigninError("The ID token of the sign-in cannot be read. Nothing is approved.") from error
        return Tokens(access, claims)


class Delegation:
    """An approval in its steps (the Delegate of the pages): `begin` gives the address of the sign-in, `finish` records the approval and makes the change. When Azure asks for
    an extra sign-in check, `finish` gives the address of a second sign-in (the kind step_up), and the `finish` of its return makes the change."""

    def __init__(self, store: Store, approvals: Approvals, signin: SigninSettings | None, redeem: Callable[..., Tokens],
                 run: Callable[[str], RunnerServices], *, emit: Callable[..., object] = lambda kind, **fields: None, pkce: Callable[[], tuple[str, str]] = new_pkce,
                 token: Callable[[int], str] = secrets.token_urlsafe) -> None:
        self.store, self.approvals, self.signin, self.redeem, self.run, self.emit, self.pkce, self.token = store, approvals, signin, redeem, run, emit, pkce, token

    def begin(self, principal: Principal, plan_id: str, code: str, nonce: str, note: str = "", hint: str = "") -> Begun:
        if self.signin is None:
            return Begun(refusal=DecideResult(False, "error", "Signing in to Azure is not set up here, so a change cannot be approved. Nothing is approved."))
        plan, refusal = self.approvals.check_form(principal, plan_id, code, nonce)
        if plan is None:
            return Begun(refusal=refusal or DecideResult(False, "error", "This request cannot be approved now. Nothing is approved."))
        verifier, challenge = self.pkce()
        oidc_nonce = self.token(16)
        # The digest of the plan that this approval is for is kept with the state of the round trip, on the server (cases/families/digest.py): at the return it is compared with the plan as
        # it is stored then, and the runner compares it once more right before it acts.
        data = json.dumps({"plan": plan.plan_id, "code": plan.code, "resource": plan.resource_id, "digest": plan.digest, "verifier": verifier, "nonce": oidc_nonce,
                           "note": clean_text(note, 300)}, separators=(",", ":"))
        try:
            state = self.store.nonce_new(principal.oid, PURPOSE, SIGNIN_SECONDS, data)
        except StoreError:
            return Begun(refusal=DecideResult(False, "error", "I cannot reach my records right now. Nothing is approved. Try again in a few minutes."))
        self.emit("signin.started", planId=plan.plan_id)
        return Begun(location=authorize_url(self.signin, state, challenge, oidc_nonce, hint))

    def finish(self, principal: Principal, query: dict[str, str]) -> DecideResult:
        if self.signin is None:
            return DecideResult(False, "error", "Signing in to Azure is not set up here. Nothing was changed.")
        state = (query.get("state") or "").strip()
        try:
            raw = self.store.nonce_take(state, principal.oid, PURPOSE) if STATE.fullmatch(state) else None
        except StoreError:
            return DecideResult(False, "error", "I cannot reach my records right now. Nothing was changed. Try again in a few minutes.")
        started = _read(raw)
        if started is None:
            return DecideResult(False, "refused_state", "This sign-in is not valid any more: it was used already, it ran out of time, or somebody else started it. Nothing was changed.")
        if started.get("stepup"):
            return self._finish_stepup(principal, started, query)
        plan_id = started["plan"]
        if query.get("error"):
            self.emit("signin.failed", planId=plan_id, reason=re.sub(r"[^a-z_]", "", query["error"].lower())[:40])
            found = re.search(r"AADSTS(\d{3,7})", query.get("error_description", ""))
            return DecideResult(False, "signin_failed", explain(query["error"], found.group(1) if found else ""), self._plan(plan_id))
        code = query.get("code", "")
        if not CODE.fullmatch(code):
            return DecideResult(False, "signin_failed", "Microsoft Entra sent you back without a code. Nothing is approved.", self._plan(plan_id))
        plan, refusal = self.approvals.check_approve(principal, plan_id, started["code"])
        if plan is None:
            return refusal or DecideResult(False, "error", "This request cannot be approved now. Nothing is approved.")
        if plan.resource_id != started["resource"]:
            return DecideResult(False, "refused_code", "This request changed. Nothing is approved. A new message will bring the new request and its code.", plan)
        problem = plan_digest.problem(plan, started["digest"])
        if problem:
            return DecideResult(False, "refused_code", plan_digest.refusal(problem), plan)
        try:
            tokens = self.redeem(code, started["verifier"])
        except SigninError as error:
            self.emit("signin.failed", planId=plan_id, reason="redeem")
            return DecideResult(False, "signin_failed", error.plain, plan)
        problem = self._who(tokens.claims, principal, started["nonce"])
        if problem:
            self.emit("signin.failed", planId=plan_id, reason="identity")
            return DecideResult(False, "signin_failed", problem, plan)
        recorded, action = self.approvals.record_approval(principal, plan, started["note"])
        if action is None:
            return recorded
        self.emit("approval.recorded", planId=plan_id)
        return self._change(principal, plan, started, action, tokens)

    def _change(self, principal: Principal, plan: PlanRecord, started: dict, action: ActionRecord, tokens: Tokens) -> DecideResult:
        """Makes the change with the person's token. When Azure asks for an extra sign-in check, the person is sent to Microsoft Entra once more (and only once)."""
        try:
            done = execute(self.run(tokens.access_token), action, approved_digest=started["digest"])
        except StoreError:
            return DecideResult(False, "error", "I cannot reach my records right now. Look at the resource in Azure before anything is tried again.", plan)
        if done.kind == "step_up" and not started.get("stepup"):
            return self._ask_again(principal, plan, started, done.action, done.claims, str(tokens.claims.get("preferred_username") or ""))
        return DecideResult(done.kind in ("ran", "ran_unconfirmed", "running", "unchanged"), done.kind, done.action.result or done.action.error or "", self._plan(plan.plan_id) or plan)

    def _ask_again(self, principal: Principal, plan: PlanRecord, started: dict, action: ActionRecord, request: str, hint: str) -> DecideResult:
        """Azure asked for an extra sign-in check (a claims challenge): the person goes to Microsoft Entra once more, with the claims request that Azure gave.

        The approval stays recorded, the plan stays approved and the action waits. The new sign-in has a state, a PKCE verifier and a nonce of its own: nothing of the first one
        is used again. If the request cannot be kept or sent, the change is closed, because nobody can complete a check that cannot be asked for."""
        settings = self.signin
        assert settings is not None
        verifier, challenge = self.pkce()
        oidc_nonce = self.token(16)
        data = json.dumps({"plan": plan.plan_id, "code": plan.code, "resource": plan.resource_id, "digest": started["digest"], "verifier": verifier, "nonce": oidc_nonce,
                           "note": started["note"], "stepup": "1", "claims": request}, separators=(",", ":"))
        if len(data) > MAX_NONCE_DATA:
            return self._closed(plan, action, "Meternaut cannot keep the request for it: it is too large.")
        try:
            state = self.store.nonce_new(principal.oid, PURPOSE, SIGNIN_SECONDS, data)
        except StoreError:
            return self._closed(plan, action, "Meternaut could not keep the request for it.")
        location = authorize_url(settings, state, challenge, oidc_nonce, hint, request)
        if len(location) > len(f"https://{LOGIN_HOST}/") + MAX_SIGNIN_PATH:
            return self._closed(plan, action, "Meternaut cannot send you to Microsoft Entra for it: the request is too large.")
        self.emit("signin.stepup", planId=plan.plan_id)
        return DecideResult(False, "step_up", STEP_UP_SENT, self._plan(plan.plan_id) or plan, location)

    def _finish_stepup(self, principal: Principal, started: dict, query: dict[str, str]) -> DecideResult:
        """The return from the sign-in to which Azure's claims challenge sent the person. The approval is recorded and the action waits, so no second approval is recorded: the
        checks are those of `check_stepup`, then the code is redeemed, the ID token is checked as before and the change is tried once more. From the first check on, whatever
        stops it closes the request: the state is used up, so the check cannot be tried again, and nothing was changed."""
        plan_id = started["plan"]
        plan, action, refusal = self.approvals.check_stepup(principal, plan_id, started["code"], started["resource"])
        if plan is None or action is None:
            return refusal or DecideResult(False, "error", "This request cannot be tried again now. Nothing was changed.")
        problem = plan_digest.problem(plan, started["digest"])
        if problem:
            return self._closed_for(plan, action, f"The change was not made: {problem}. Nothing was changed. The request is closed.")
        if query.get("error"):
            self.emit("signin.failed", planId=plan_id, reason=re.sub(r"[^a-z_]", "", query["error"].lower())[:40])
            found = re.search(r"AADSTS(\d{3,7})", query.get("error_description", ""))
            return self._closed(plan, action, explain_stepup(query["error"], found.group(1) if found else ""))
        code = query.get("code", "")
        if not CODE.fullmatch(code):
            return self._closed(plan, action, "Microsoft Entra sent you back without a code.")
        try:
            tokens = self.redeem(code, started["verifier"], started["claims"])
        except SigninError:
            self.emit("signin.failed", planId=plan_id, reason="redeem")
            return self._closed(plan, action, "Microsoft Entra did not give a token for it.")
        if self._who(tokens.claims, principal, started["nonce"]):
            self.emit("signin.failed", planId=plan_id, reason="identity")
            return self._closed(plan, action, "It was done with another account, or it does not belong to this request.")
        return self._change(principal, plan, started, action, tokens)

    def _closed_for(self, plan: PlanRecord, action: ActionRecord, text: str) -> DecideResult:
        """The change that waited for the extra sign-in check is closed for a reason of its own (the plan is not the one that was approved): the action, the plan and the case fail with the
        reason in plain words. Nothing was changed."""
        try:
            self.approvals.close_waiting(plan, action, text)
        except StoreError:
            return DecideResult(False, "error", "I cannot reach my records right now. Nothing was changed. The request closes by itself in a few minutes.", plan)
        self.emit("action.finished", planId=plan.plan_id, family=plan.family, ok=False)
        return DecideResult(False, "refused_code", text, self._plan(plan.plan_id) or plan)

    def _closed(self, plan: PlanRecord, action: ActionRecord, why: str) -> DecideResult:
        """The extra sign-in check cannot be completed, so the change that waited for it will not be made: the action and the plan are closed as failed, with the reason in plain
        words. Nothing was changed."""
        text = f"The extra sign-in check that Azure asked for was not completed. {why} The change was not made. Nothing was changed. The request is closed."
        try:
            self.approvals.close_waiting(plan, action, text)
        except StoreError:
            return DecideResult(False, "error", "I cannot reach my records right now. Nothing was changed. The request closes by itself in a few minutes.", plan)
        self.emit("action.finished", planId=plan.plan_id, family=plan.family, ok=False)
        return DecideResult(False, "step_up_failed", text, self._plan(plan.plan_id) or plan)

    def _plan(self, plan_id: str) -> PlanRecord | None:
        try:
            return self.store.plan_get(plan_id)
        except StoreError:
            return None

    def _who(self, claims: dict, principal: Principal, nonce: str) -> str:
        """Why the sign-in is not the person's, or an empty text when it is: the same object id, the same tenant, this client and this request, from this tenant's
        endpoint and not expired. (The token comes over the back channel from the token endpoint, so its signature is not checked: OpenID Connect Core, 3.1.3.7.)"""
        settings = self.signin
        assert settings is not None
        tenant = settings.tenant_id.lower()
        if str(claims.get("oid", "")).lower() != principal.oid.lower():
            return "You signed in to Azure with another account than the one that is signed in to this console. Nothing is approved. Use the same account."
        if str(claims.get("tid", "")).lower() != tenant:
            return "You signed in to Azure in another tenant than the one of this console. Nothing is approved."
        if str(claims.get("aud", "")).lower() != settings.client_id.lower() or not secrets.compare_digest(str(claims.get("nonce", "")).encode("utf-8"), nonce.encode("utf-8")):
            return "This sign-in does not belong to the request that started it. Nothing is approved."
        expires = claims.get("exp")
        fresh = isinstance(expires, (int, float)) and not isinstance(expires, bool) and expires > self.approvals.clock().timestamp()
        if str(claims.get("iss", "")).lower() != f"https://{LOGIN_HOST}/{tenant}/v2.0" or not fresh:
            return "The identity token of the sign-in is not one that this console accepts. Nothing is approved."
        return ""


def _read(raw: str | None) -> dict | None:
    """The data that `begin` (or the step-up) kept with the state, or None when there is none or it is not what they wrote.

    The state of a step-up has `"stepup": "1"` and the claims request of Azure; the first state has neither, and a state that has one of them without the other is refused."""
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except ValueError:
        return None
    if not isinstance(data, dict) or not all(isinstance(data.get(key), str) for key in ("plan", "code", "resource", "digest", "verifier", "nonce", "note")):
        return None
    if "stepup" not in data:
        return None if "claims" in data else data
    return data if data["stepup"] == "1" and isinstance(data.get("claims"), str) and data["claims"] else None
