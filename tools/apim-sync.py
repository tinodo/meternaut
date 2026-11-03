#!/usr/bin/env python3
"""Adds the Meternaut objects to an existing API Management instance, and removes them again (standard library only).

The hub of this project is the owner's own API Management instance, which other work also uses. This tool
therefore changes nothing but objects whose name starts with `meternaut-`: an API with its operation, policy
and diagnostic, a product (the contract) with its policy, and a subscription (the contract's key). It never
touches the service itself, its global policy, its network, its loggers or any other object, and it refuses a
manifest that tries to.

    python tools/apim-sync.py plan   --apim RESOURCE_ID --var FOUNDRY_ENDPOINT=https://... --var APPINSIGHTS_LOGGER=NAME
    python tools/apim-sync.py apply  (same options)
    python tools/apim-sync.py remove (same options)
    python tools/apim-sync.py key    --apim RESOURCE_ID      prints the contract's primary key and nothing else

`plan` only reads. The tool runs from the deployment workflow, which signs in with OpenID Connect; nobody runs
`apply` or `remove` from a machine (AGENTS.md rule 18), and the tool refuses to outside GitHub Actions. `apply`
writes what the plan says and nothing else, so a second run changes nothing. `remove` deletes only the objects
the manifest names: a subscription of the product that the manifest does not name stops the removal.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ARM = "https://management.azure.com"
GUID = r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
APIM_ID = re.compile(rf"/subscriptions/{GUID}/resourceGroups/[A-Za-z0-9._()-]{{1,90}}/providers/Microsoft\.ApiManagement/service/[A-Za-z][A-Za-z0-9-]{{0,49}}", re.I)
VALUE = re.compile(r"^[A-Za-z0-9._:/,-]*$")
PREFIX = "meternaut-"  # the only objects this tool touches; a manifest cannot choose another
NAME = r"[A-Za-z0-9._-]"
VARIABLE = re.compile(r"\$\{([A-Z][A-Z0-9_]*)\}")
# The link between a product and an API. Microsoft's reference defines HEAD (204: it is there), PUT and DELETE for it:
# no GET (the instance answers 405) and no If-Match.
LINK = re.compile(r"products/[^/]+/apis/[^/]+")


def clean(text) -> str:
    """Take the query string off every link and any signature out of a message."""
    text = re.sub(r"(https?://[^\s\"'<>?]+)\?[^\s\"'<>]*", r"\1", str(text))
    return re.sub(r"(?i)\bsig=[^&\s\"'<>]+", "sig=removed", text)


class Problem(Exception):
    """Something the person running the tool can fix; printed without a trace."""

    def __init__(self, message):
        super().__init__(clean(message))


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """A redirect would carry the token to another host."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class Transport:
    """The only place that talks to the network, so that tests can replace it."""

    def __init__(self, token_command=None, sleep=time.sleep, attempts=5):
        self.token_command = token_command or [shutil.which("az") or "az", "account", "get-access-token", "--resource",
                                               ARM + "/", "--query", "accessToken", "-o", "tsv"]
        self.sleep, self.attempts, self._token = sleep, attempts, None
        self._opener = urllib.request.build_opener(_NoRedirect)

    def token(self) -> str:
        if self._token is None:
            try:
                done = subprocess.run(self.token_command, capture_output=True, text=True, timeout=120)
            except (OSError, subprocess.TimeoutExpired) as e:
                raise Problem(f"could not run the Azure CLI to get a token: {e}")
            if done.returncode != 0 or not done.stdout.strip():
                raise Problem("the Azure CLI gave no token: the workflow signs in with azure/login first")
            self._token = done.stdout.strip()
        return self._token

    def request(self, method: str, url: str, body: dict | None = None, headers: dict | None = None):
        """Returns (status, headers, bytes). Retries 429 and 5xx. The token goes only to management.azure.com."""
        parts = urllib.parse.urlsplit(url)
        if parts.scheme != "https" or parts.netloc != "management.azure.com" or parts.fragment or parts.username or parts.password:
            raise Problem("refusing to send the token anywhere but https://management.azure.com, and never with a fragment in the address")
        if body is not None:
            data = json.dumps(body).encode("utf-8")
        elif method in ("POST", "PUT", "PATCH"):
            data = b""  # the service rejects a POST or PUT without a Content-Length
        else:
            data = None
        for attempt in range(1, self.attempts + 1):
            sent = {"Authorization": "Bearer " + self.token(), **(headers or {})}
            if body is not None:
                sent["Content-Type"] = "application/json"
            request = urllib.request.Request(url, data=data, headers=sent, method=method)
            try:
                with self._opener.open(request, timeout=300) as response:
                    return response.status, dict(response.headers.items()), response.read()
            except urllib.error.HTTPError as e:
                if e.code in (429, 500, 502, 503, 504) and attempt < self.attempts:
                    waits = [float(v) for k, v in e.headers.items() if "retry-after" in k.lower() and str(v).replace(".", "").isdigit()]
                    self.sleep(min(max(waits or [2.0 ** attempt]), 120.0))
                    continue
                return e.code, dict(e.headers.items()), e.read()
            except urllib.error.URLError as e:
                raise Problem(f"could not reach {url.split('?')[0]}: {e}")
        raise Problem("too many retries")


def substitute(value, variables: dict[str, str]):
    """Replaces ${NAME} in every string of a value. A name without a value is an error, never an empty string."""
    if isinstance(value, str):
        def one(match):
            if match.group(1) not in variables:
                raise Problem(f"no value for ${{{match.group(1)}}}: give it with --var {match.group(1)}=...")
            return variables[match.group(1)]
        return VARIABLE.sub(one, value)
    if isinstance(value, list):
        return [substitute(v, variables) for v in value]
    if isinstance(value, dict):
        return {substitute(k, variables): substitute(v, variables) for k, v in value.items()}
    return value


def allowed_path(path: str, prefix: str = PREFIX) -> bool:
    """Only an object of ours, or a child of one of ours that this tool knows. Nothing at the level of the service."""
    p = re.escape(prefix)
    owned = rf"{p}{NAME}+"
    patterns = [
        rf"(products|apis|subscriptions|backends|namedValues)/{owned}",
        rf"apis/{owned}/operations/{NAME}+",
        rf"apis/{owned}/policies/policy",
        rf"apis/{owned}/diagnostics/applicationinsights",
        rf"products/{owned}/policies/policy",
        rf"products/{owned}/apis/{owned}",
    ]
    return any(re.fullmatch(x, path) for x in patterns)


def read_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise Problem(f"could not read {path.name}: {e}")
    if not isinstance(value, dict):
        raise Problem(f"{path.name} holds one JSON object")
    return value


def load_variables(contract_file: Path, extra: list[str]) -> dict[str, str]:
    contract = read_json(contract_file)
    models = contract.get("models") or []
    try:
        variables = {
            "CONTRACT": str(contract.get("name", "")),
            "ALLOWED_MODELS": ",".join(str(m) for m in models),
            "TOKENS_PER_MINUTE": str(int(contract["tokensPerMinute"])),
            "TOKEN_QUOTA_PER_MONTH": str(int(contract["tokenQuotaPerMonth"])),
        }
    except (KeyError, TypeError, ValueError):
        raise Problem("the contract file needs a name, models, tokensPerMinute and tokenQuotaPerMonth (whole numbers)")
    for pair in extra:
        name, sep, value = pair.partition("=")
        if not sep or not re.fullmatch(r"[A-Z][A-Z0-9_]*", name):
            raise Problem(f"--var is NAME=VALUE with NAME in capitals, not {pair!r}")
        variables[name] = value
    endpoint = variables.get("FOUNDRY_ENDPOINT")
    if endpoint is not None:
        endpoint = endpoint.rstrip("/")
        if not re.fullmatch(r"https://[a-z0-9-]+\.(cognitiveservices|openai)\.azure\.com", endpoint):
            raise Problem("FOUNDRY_ENDPOINT is https://<account>.cognitiveservices.azure.com")
        variables["FOUNDRY_ENDPOINT"] = endpoint
    for name, value in variables.items():
        if not VALUE.match(value):
            raise Problem(f"the value of {name} has characters that do not belong in a name, a number or an address")
    if not variables["CONTRACT"] or not variables["ALLOWED_MODELS"]:
        raise Problem("the contract needs a name and at least one model")
    return variables


def manifest_header(path: Path) -> tuple[dict, str]:
    raw = read_json(path)
    if raw.get("prefix") != PREFIX:
        raise Problem(f"the manifest's prefix is {PREFIX}: this tool touches no other objects, whatever a manifest says")
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(raw.get("apiVersion", ""))):
        raise Problem("the manifest's apiVersion is a date such as 2024-05-01")
    return raw, PREFIX


def load_manifest(path: Path, variables: dict[str, str]) -> dict:
    raw, prefix = manifest_header(path)
    objects = []
    for entry in raw.get("objects", []):
        object_path = substitute(entry["path"], variables)
        if not allowed_path(object_path, prefix):
            raise Problem(f"{object_path}: not an object this tool may touch (names start with {prefix}; no service-level objects)")
        item = {"path": object_path}
        if "policy" in entry:
            policy_file = (path.parent / entry["policy"]).resolve()
            if path.parent.resolve() not in policy_file.parents:
                raise Problem(f"{entry['policy']}: a policy file lives next to the manifest")
            try:
                text = policy_file.read_text(encoding="utf-8")
            except OSError as e:
                raise Problem(f"could not read {entry['policy']}: {e}")
            item["policy"] = substitute(text, variables)
        else:
            item["body"] = substitute(entry.get("body", {}), variables)
        objects.append(item)
    return {"apiVersion": raw["apiVersion"], "prefix": prefix, "objects": objects}


def normal_xml(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r">\s+<", "><", text.strip()))


ID_FIELDS = ("loggerId", "scope")  # the service reports these as full resource ids, the manifest gives the tail


def covers(wanted, actual, field: str = "") -> bool:
    """True when everything wanted is already so in what the service reports (the service adds fields of its own)."""
    if isinstance(wanted, dict):
        return isinstance(actual, dict) and all(k in actual and covers(v, actual[k], k) for k, v in wanted.items())
    if isinstance(wanted, list):
        return isinstance(actual, list) and len(wanted) == len(actual) and all(covers(w, a, field) for w, a in zip(wanted, actual))
    if isinstance(wanted, str) and isinstance(actual, str):
        if wanted.lower() == actual.lower():
            return True
        return field in ID_FIELDS and wanted.startswith("/") and actual.lower().endswith(wanted.lower())
    return wanted == actual


class Apim:
    def __init__(self, transport: Transport, apim_id: str, api_version: str, sleep=time.sleep):
        if not APIM_ID.fullmatch(apim_id):
            raise Problem("--apim is the resource id of the instance: /subscriptions/<id>/resourceGroups/<group>/providers/Microsoft.ApiManagement/service/<name>")
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}(-preview)?", api_version):
            raise Problem("the API version is a date such as 2024-05-01")
        self.transport, self.apim_id, self.api_version, self.sleep = transport, apim_id, api_version, sleep
        self.notes: list[str] = []

    def url(self, path: str, **query) -> str:
        """The address of an object. It is built, then read back: the path must be exactly the instance's, with nothing after it."""
        wanted = f"{self.apim_id}/{path}"
        url = urllib.parse.urlunsplit(("https", "management.azure.com", wanted, urllib.parse.urlencode({"api-version": self.api_version, **query}), ""))
        parts = urllib.parse.urlsplit(url)
        if parts.path != wanted or parts.fragment or parts.netloc != "management.azure.com" or any(c in path for c in "?#%\\ "):
            raise Problem(f"{path}: not an address inside the instance")
        return url

    def read(self, path: str):
        if LINK.fullmatch(path):
            status, _, raw = self.transport.request("HEAD", self.url(path))
            if status == 404:
                return None
            if status not in (200, 204):
                raise Problem(f"{path}: looking for it gave {status}")
            return {"properties": {}}
        is_policy = path.endswith("/policies/policy")
        status, _, raw = self.transport.request("GET", self.url(path, **({"format": "rawxml"} if is_policy else {})))
        if status == 404:
            return None
        if status != 200:
            raise Problem(f"{path}: reading it gave {status}: {raw.decode('utf-8', 'replace')[:300]}")
        text = raw.decode("utf-8", "replace")
        if is_policy:
            return text if text.lstrip().startswith("<") else json.loads(text)["properties"]["value"]
        return json.loads(text)

    def settled(self, path: str, must_exist: bool = False, tries: int = 30, pause: float = 10.0):
        """Reads an object, waiting while the service is still making it, and returns the last read (None: it is not there).

        The service may answer a write with 200, 201 or 202 and still be working: the object then reports a state
        that is not final, or is not visible yet. Whatever depends on it waits for the end."""
        for _ in range(tries):
            found = self.read(path)
            state = state_of(found)
            if (found is None and not must_exist) or (found is not None and state not in WORKING_STATES):
                if state is not None and state not in FINAL_STATES + BAD_STATES:
                    word = re.sub(r"[^A-Za-z0-9 _.-]", "?", raw_state(found))[:40]
                    note = f"{path} reports the state {word!r}, which this tool does not know; it is taken as a final state"
                    if note not in self.notes:
                        self.notes.append(note)
                return found
            self.sleep(pause)
        raise Problem(f"{path}: still not ready after {int(tries * pause)} seconds")

    def write(self, item: dict, exists: bool = False) -> None:
        """PUT one object and wait until the service has made it. An object that is there is replaced only with If-Match."""
        body = {"properties": {"format": "rawxml", "value": item["policy"]}} if "policy" in item else (item["body"] or None)
        headers = {"If-Match": "*"} if exists and body is not None else None
        status, _, raw = self.transport.request("PUT", self.url(item["path"]), body, headers)
        if status not in (200, 201, 202):
            raise Problem(f"{item['path']}: writing it gave {status}: {raw.decode('utf-8', 'replace')[:500]}")
        state = state_of(self.settled(item["path"], must_exist=True))
        if state in BAD_STATES:
            raise Problem(f"{item['path']}: the service reports that making it {state}")

    def gone(self, path: str, tries: int = 30, pause: float = 10.0) -> None:
        """Waits until an object whose removal the service has only accepted is no longer there."""
        for _ in range(tries):
            if self.read(path) is None:
                return
            self.sleep(pause)
        raise Problem(f"{path}: still there after {int(tries * pause)} seconds, although the service accepted its removal")

    def delete(self, path: str) -> str:
        """DELETE one object that is there. Never the subscriptions of a product or anything else the manifest does not name.

        The object is read first: the service answers a DELETE of an object that does not exist with 204, which would read
        as "deleted". What was not there is "absent" and no DELETE is sent for it."""
        if self.read(path) is None:
            return "absent"
        query = {"deleteRevisions": "true"} if re.fullmatch(r"apis/[^/]+", path) else {}
        headers = None if LINK.fullmatch(path) else {"If-Match": "*"}
        status, _, raw = self.transport.request("DELETE", self.url(path, **query), None, headers)
        if status in (200, 202, 204):
            if status == 202:  # deleting an API answers 202 or 204: with 202 the service is still taking it away
                self.gone(path)
            return "deleted"
        if status == 404:
            return "absent"
        hint = " (a subscription that is not in the manifest may still use the product; it is not deleted)" if path.startswith("products/") else ""
        raise Problem(f"{path}: removing it gave {status}: {raw.decode('utf-8', 'replace')[:300]}{hint}")


def raw_state(found) -> str | None:
    """The state the service reports for an object it is making or has made, as it wrote it (a policy, read as text, has none)."""
    state = found.get("properties", {}).get("provisioningState") if isinstance(found, dict) else None
    return state if isinstance(state, str) else None


def state_of(found) -> str | None:
    """The same, without case, spaces, underscores and hyphens, so that 'InProgress', 'In Progress' and 'in_progress' are one word."""
    state = raw_state(found)
    return re.sub(r"[\s_-]", "", state).lower() if state is not None else None


# The reference names no final state for an API ("The provisioning state"), so only what clearly means "still working"
# is waited for and only what clearly means "did not work" stops the run. Any other word is a final state: waiting on
# an unknown word would fail every run for a perfectly good object. Such a word is printed as a note, so that the first
# real run shows which words the service uses; a dependent write that then starts too early fails and stops the run.
WORKING_STATES = ("inprogress", "accepted", "creating", "updating", "provisioning", "pending", "running", "activating", "starting",
                  "queued", "notstarted", "waiting", "submitted", "deploying", "validating", "migrating", "scaling", "restarting", "deleting")
BAD_STATES = ("failed", "canceled", "cancelled", "error", "errored", "rejected", "aborted", "timedout")
FINAL_STATES = ("succeeded", "created", "completed", "ready", "active")


def plan(apim: Apim, objects: list[dict]) -> list[tuple[str, str]]:
    result = []
    for item in objects:
        existing = apim.settled(item["path"])
        if existing is None:
            action = "create"
        elif state_of(existing) in BAD_STATES:
            action = "update"  # whatever it matches, a failed object is made again from the approved definition
        elif "policy" in item:
            action = "unchanged" if normal_xml(existing) == normal_xml(item["policy"]) else "update"
        else:
            action = "unchanged" if covers(item["body"].get("properties", {}), existing.get("properties", {})) else "update"
        result.append((action, item["path"]))
    return result


def apply(apim: Apim, objects: list[dict]) -> list[tuple[str, str]]:
    """What the plan says, and only that: an object that is already right is not written again."""
    rows = []
    for (action, path), item in zip(plan(apim, objects), objects):
        if action == "unchanged":
            rows.append(("unchanged", path))
            continue
        apim.write(item, exists=(action == "update"))
        rows.append(("created" if action == "create" else "updated", path))
    return rows


def report(rows: list[tuple[str, str]], closing: str) -> str:
    counts: dict[str, int] = {}
    for action, _ in rows:
        counts[action] = counts.get(action, 0) + 1
    lines = [f"{action:<9} {path}" for action, path in rows]
    lines.append(", ".join(f"{n} {a}" for a, n in sorted(counts.items())) + f". {closing}")
    return "\n".join(lines)


def contract_key(apim: Apim, subscription: str, prefix: str) -> str:
    if not subscription.startswith(prefix) or not re.fullmatch(rf"{NAME}+", subscription):
        raise Problem(f"only the key of a subscription whose name starts with {prefix} can be read")
    status, _, raw = apim.transport.request("POST", apim.url(f"subscriptions/{subscription}/listSecrets"))
    if status != 200:
        raise Problem(f"reading the key of {subscription} gave {status}")
    key = json.loads(raw).get("primaryKey", "")
    if not key:
        raise Problem(f"{subscription} has no primary key")
    return key


def main(argv: list[str] | None = None, transport: Transport | None = None, environ=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=("plan", "apply", "remove", "key"))
    parser.add_argument("--apim", required=True, help="resource id of the API Management instance")
    parser.add_argument("--manifest", default=str(ROOT / "hub" / "apim" / "manifest.json"))
    parser.add_argument("--contract", default=str(ROOT / "hub" / "contract.json"))
    parser.add_argument("--var", action="append", default=[], help="NAME=VALUE for ${NAME} in the manifest and the policies")
    args = parser.parse_args(argv)
    environ = os.environ if environ is None else environ
    apim = None
    try:
        if args.command in ("apply", "remove") and environ.get("GITHUB_ACTIONS") != "true":
            raise Problem(f"{args.command} runs only from the deployment workflow (AGENTS.md rule 18); use plan to see what it would do")
        variables = load_variables(Path(args.contract), args.var)
        transport = transport or Transport()
        sleep = getattr(transport, "sleep", time.sleep)
        if args.command == "key":
            raw, prefix = manifest_header(Path(args.manifest))
            apim = Apim(transport, args.apim, str(raw["apiVersion"]), sleep)
            print(contract_key(apim, f"{variables['CONTRACT']}-sub-01", prefix))
            return 0
        for needed in ("FOUNDRY_ENDPOINT", "APPINSIGHTS_LOGGER"):
            if needed not in variables:
                raise Problem(f"--var {needed}=... is needed")
            if not variables[needed].strip():
                raise Problem(f"{needed} is empty: is the repository variable set?")
        manifest = load_manifest(Path(args.manifest), variables)
        apim = Apim(transport, args.apim, manifest["apiVersion"], sleep)
        objects = manifest["objects"]
        if args.command == "plan":
            print(report(plan(apim, objects), "Nothing was changed."))
        elif args.command == "apply":
            print(report(apply(apim, objects), "Only what says created or updated was written; a second run changes nothing."))
        else:
            rows = [(apim.delete(item["path"]), item["path"]) for item in reversed(objects) if not item["path"].endswith("/policies/policy")]
            print(report(rows, "Only objects named in the manifest were removed."))
        for note in apim.notes:
            print(f"note: {note}")
    except Problem as e:
        for note in getattr(apim, "notes", []):
            print(f"note: {note}", file=sys.stderr)
        print(f"error: {e}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
