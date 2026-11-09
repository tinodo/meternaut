"""The Study: the Scholar reads Microsoft's documentation about the kinds of resource that the estate has, and files what the pages say as claims that code checks (docs/proposals/15-learning.md).

One run of the Study (the timer `study-weekly`, or the control message with the job `study`) does, in this order, and stops at the first step that says no:

  1. It reads the switches `all` and `investigation` (a switch that cannot be read counts as pulled), the setting `STUDY` (off unless a person turns it on) and the Foundry project. Nothing
     is read or asked before that.
  2. It reads again the claims that are due (code only: the page is fetched again and the quote must still be on it, a quote that is not is marked stale).
  3. It surveys the estate: the kinds of resource that it has (one Resource Graph query, the same one that the investigation's overview makes) that have no current claim and no mark that they
     were studied, the most common first, at most STUDY_MAX_TYPES of them. The list is made from what exists; no person writes it and no rule in code names a kind of resource.
  4. It runs the Scholar (cases/agents.py) through the agent harness (cases/harness.py: the lock, the switches, the budgets, the guard on the tool calls, the trace) with one tool, `fetch_doc`
     (cases/library.py), which this app runs against public pages only. Every model call goes through the AI Gateway, as every model call of Meternaut does.
  5. It checks every claim in the Scholar's answer by code: the kind of resource is one of the input, the kind of claim is on the closed list, the page is one that this run read, and the quote is
     on that page (exact, after whitespace normalisation, plain words, at most 200 characters). A claim that fails any check is thrown away and counted by the reason, never by its text. A kind of
     resource that the Scholar read about and that has no claim left is marked as studied, so that the survey does not ask again for a month.

What it cannot do, said plainly: it cannot tell whether a page is right (it quotes it), whether a sentence means what the Scholar filed it as (the kind is the Scholar's reading, and only the
quote is checked), or whether the app's network lets the documentation hosts through (the first run says). A claim is context for the Investigator, which has measurements to read; no claim moves
a finding, a figure or a proposal.
"""
from __future__ import annotations

import datetime as dt
import logging
import os
import time
import uuid
from collections import Counter
from dataclasses import dataclass
from typing import Callable, Collection, Mapping

from . import agents, config as cfg, harness as harness_module, library, scope as scope_mod, switches, toolbox, wiring
from .arm import Arm
from .events import History
from .foundry import FoundryError, Foundry
from .harness import HarnessRefused
from .http import Client, HttpError, allowed_calls, default_transport, docs_calls
from .identity import Identity, IdentityError
from .memory_store import stamp, utc_now
from .models import CLAIM_KINDS, ClaimRecord, StoreError
from .redact import Redactor
from .roles import RoleError, clean_text, extract_object

LOG = logging.getLogger("meternaut.study")
STOPPING = harness_module.STOPPING  # the switches that stop the Study: all, and investigation (the agents' own)
RECHECK_PAGES = 12  # the pages that one run reads again for the claims that are due
CALLS_PER_PAGE = 3  # the tool calls that the budget gives for each page: the windows of a page, and the pages that were not worth reading
SURVEY_CLAIMS = 500  # the claims of the store that the survey looks at
REASONS = ("shape", "type", "kind", "url", "quote", "cap", "duplicate")  # why a claim is thrown away: the words of the History, never the text of the claim


@dataclass
class Summary:
    """What one run of the Study came to. `state` is `ran`, `off` (it is not meant to run), `held` (a switch, the lock or a stored definition says no) or `failed`."""

    state: str = "off"
    ok: bool = True
    note: str = ""
    types: int = 0  # kinds of resource given to the Scholar
    studied: int = 0  # kinds that the Scholar says it read about
    kept: int = 0  # claims that code kept
    rejected: int = 0  # claims that code threw away
    rechecked: int = 0  # claims read again, whose quote the page still holds
    stale: int = 0  # claims read again, whose quote the page no longer holds
    tokens: int = 0
    tool_calls: int = 0
    seconds: int = 0


@dataclass
class Services:
    settings: cfg.Settings
    client: Client  # Azure Resource Manager, the Foundry project and the AI Gateway (http.allowed_calls)
    docs: Client  # the public documentation pages, and nothing else (http.docs_calls)
    arm: Arm
    history: History
    redact: Callable[[str], str]
    clock: Callable[[], dt.datetime]
    monotonic: Callable[[], float]
    store: object | None = None
    foundry: "Foundry | None" = None
    harness: "harness_module.Harness | None" = None


# -- what the Scholar answers ------------------------------------------------------------------------------------------------------------------------

def parse_answer(text: object) -> tuple[list, list[str]]:
    """The claims and the kinds of resource that the Scholar says it read about, from its last text. Raises RoleError when that is not one JSON object with a list of claims."""
    try:
        data = extract_object(text)
    except RecursionError:
        raise RoleError("the answer is nested too deeply") from None
    claims = data.get("claims")
    if not isinstance(claims, list):
        raise RoleError("the answer holds no list of claims")
    studied = data.get("studied")
    return claims, [item for item in (studied if isinstance(studied, list) else []) if isinstance(item, str)]


def accept(raw: list, types: Collection[str], pages: library.Library, now: dt.datetime) -> tuple[list[ClaimRecord], Counter]:
    """The claims of the answer that code keeps, and how many were thrown away for each reason (REASONS). The answer is data: a claim is kept only when its kind of resource is one of the input,
    its kind is on the closed list, its address is a page that this run read, and its quote is on that page (library.verified_quote). At most MAX_CLAIMS in all and MAX_CLAIMS_PER_TYPE for
    one kind of resource; what is over is thrown away, and so is a claim that is there twice."""
    kept: list[ClaimRecord] = []
    thrown: Counter = Counter()
    per_type: Counter = Counter()
    seen: set[str] = set()
    if len(raw) > agents.MAX_CLAIMS:
        thrown["cap"] += len(raw) - agents.MAX_CLAIMS
    for item in raw[: agents.MAX_CLAIMS]:
        if not isinstance(item, dict):
            thrown["shape"] += 1
            continue
        resource_type = item.get("type") if isinstance(item.get("type"), str) else ""
        if resource_type not in types:
            thrown["type"] += 1
            continue
        kind = item.get("kind").strip().lower() if isinstance(item.get("kind"), str) else ""
        if kind not in CLAIM_KINDS:
            thrown["kind"] += 1
            continue
        url = library.doc_url(item.get("url"))
        page = pages.pages.get(url) if url else None
        if page is None:
            thrown["url"] += 1
            continue
        quote = library.verified_quote(item.get("quote"), page)
        if quote is None:
            thrown["quote"] += 1
            continue
        if per_type[resource_type] >= agents.MAX_CLAIMS_PER_TYPE:
            thrown["cap"] += 1
            continue
        claim = library.claim_of(resource_type, kind, page.url, quote, now)
        if claim.claim_id in seen:
            thrown["duplicate"] += 1
            continue
        seen.add(claim.claim_id)
        per_type[resource_type] += 1
        kept.append(claim)
    return kept, thrown


# -- the steps ---------------------------------------------------------------------------------------------------------------------------------------

def recheck(s: Services, now: dt.datetime, out: Summary) -> None:
    """Reads again, by code, the claims that are current and were last checked more than a week ago: a quote that the page still holds is fresh for another month, and one that it does not
    hold is marked stale. A page that cannot be read changes nothing: the claim runs out at its own time."""
    claims = [claim for claim in s.store.claims_recent(SURVEY_CLAIMS) if library.current(claim, now) and library.due(claim, now)]  # type: ignore[union-attr]
    if not claims:
        return
    pages = library.Library(s.docs, max_pages=RECHECK_PAGES, max_chars=1)
    for claim in claims:
        found = library.rechecked(claim, pages, now)
        if found is None:
            continue
        s.store.claim_put(found)  # type: ignore[union-attr]
        out.rechecked += found.state == "fresh"
        out.stale += found.state == "stale"


def survey(s: Services, now: dt.datetime, notes: list[str]) -> list[dict]:
    """The kinds of resource of the estate that wait to be studied, most common first, as the input of the Scholar wants them: the type, and the address of its reference page. A kind that has a
    current claim, or a mark that it was studied, does not wait. A kind that is not a plain name of a resource type is left out."""
    st = s.settings
    try:
        scope = scope_mod.resolve(s.arm, st, None, s.redact)
    except scope_mod.ScopeError as error:
        notes.append(clean_text(s.redact(error), 300))
        return []
    notes.extend(scope.notes)
    counts: Counter = Counter()
    for row in s.arm.graph_many(list(scope.subscriptions), toolbox.TYPE_COUNTS):
        resource_type = toolbox.type_word(str(row.get("type") or "").lower())
        number = row.get("n")
        if resource_type is not None and isinstance(number, int) and not isinstance(number, bool):
            counts[resource_type] += number
    known = {claim.resource_type for claim in s.store.claims_recent(SURVEY_CLAIMS) if library.current(claim, now)}  # type: ignore[union-attr]
    waiting = [(resource_type, library.reference_url(resource_type)) for resource_type, _ in sorted(counts.items(), key=lambda item: (-item[1], item[0])) if resource_type not in known]
    return [{"type": resource_type, "reference": reference} for resource_type, reference in waiting if reference][: st.study_max_types]


def execute(s: Services, trigger: str) -> Summary:
    """One run of the Study. It never raises: the History says how it ended."""
    h, st = s.history, s.settings
    out = Summary()
    began = s.monotonic()
    deadline = began + st.study_max_seconds
    s.client.deadline = s.docs.deadline = deadline
    h.emit("study.started", trigger=trigger, maxTypes=st.study_max_types, maxPages=st.study_max_pages, maxSeconds=st.study_max_seconds, maxTokens=st.study_max_tokens)
    try:
        _study(s, out, deadline)
    except Exception as error:  # noqa: BLE001 (a run of the Study never stops the app)
        out.state, out.ok = "failed", False
        out.note = clean_text(s.redact(f"{type(error).__name__}: {error}"), 300)
        LOG.warning("the Study failed: %s", out.note)
    finally:
        if s.harness is not None:
            s.harness.close()  # the line of the Scholar's run, and the brake for a run that misbehaved (cases/harness.py)
        out.seconds = int(s.monotonic() - began)
        h.emit("study.finished", state=out.state, ok=out.ok, types=out.types, studied=out.studied, kept=out.kept, rejected=out.rejected, rechecked=out.rechecked, stale=out.stale,
               toolCalls=out.tool_calls, tokens=out.tokens, seconds=out.seconds, note=out.note)
    return out


def _study(s: Services, out: Summary, deadline: float) -> None:
    h, st = s.history, s.settings

    def note(text: str) -> None:
        text = clean_text(s.redact(text), 300)
        h.emit("study.note", note=text)
        out.note = out.note or text

    if not st.study:
        out.note = "the Study is switched off"
        return
    if not st.foundry_endpoint or s.foundry is None:
        out.note = "no Foundry endpoint is set"
        return
    if s.store is None:
        out.note = "no store keeps the claims, so there is nothing to study for"
        return
    if switches.pulled(s.store, *STOPPING):  # type: ignore[arg-type]
        out.state, out.note = "held", "the switch all or the switch investigation is pulled, or cannot be read"
        return
    now = s.clock()
    out.state = "ran"
    try:
        recheck(s, now, out)
        notes: list[str] = []
        types = survey(s, now, notes)
    except (HttpError, IdentityError, StoreError) as error:
        out.state, out.ok = "failed", False
        note(f"the survey or the re-read of the claims could not be made ({clean_text(s.redact(error), 200)})")
        return
    for text in notes:
        note(text)
    out.types = len(types)
    if not types:
        out.note = out.note or "no kind of resource waits to be studied"
        return
    spec = agents.scholar(st, (library.FETCH_DOC,))
    try:
        reference = s.harness.ensure(spec) if s.harness is not None else s.foundry.ensure_agent(spec)
    except FoundryError as error:
        out.state, out.ok = ("held", True) if isinstance(error, HarnessRefused) else ("failed", False)
        note(f"the Scholar could not be made ready ({clean_text(s.redact(getattr(error, 'route', '') or error), 200)})")
        return
    max_pages = st.study_max_pages
    max_calls = max_pages * CALLS_PER_PAGE
    pages = library.Library(s.docs, max_pages=max_pages, max_chars=max_calls * library.WINDOW)
    asked = agents.scholar_input(types, max_calls, max_pages)
    left = max(1.0, deadline - s.monotonic())
    try:
        if s.harness is None:
            answer = s.foundry.run(reference, asked, pages.call, max_calls=max_calls, max_seconds=left)
        else:
            answer = s.harness.run(reference, spec, asked, pages.call, max_calls=max_calls, max_seconds=left)
    except FoundryError as error:
        partial = getattr(error, "partial", None)
        out.tokens = partial.input_tokens + partial.output_tokens if partial is not None else 0
        out.state, out.ok = ("held", True) if isinstance(error, HarnessRefused) else ("failed", False)
        note(f"the Scholar gave no answer ({clean_text(s.redact(getattr(error, 'route', '') or error), 200)})")
        return
    out.tokens = answer.input_tokens + answer.output_tokens
    out.tool_calls = len([call for call in answer.calls if isinstance(call, dict) and not call.get("refused")])
    try:
        raw, studied = parse_answer(answer.text)
    except RoleError as error:
        if s.harness is not None:
            s.harness.guard_failed(spec.name, "unreadable")
        out.state, out.ok = "failed", False
        note(f"the Scholar gave no answer that could be read ({clean_text(error, 200)})")
        return
    names = {item["type"] for item in types}
    kept, thrown = accept(raw, names, pages, now)
    out.rejected = sum(thrown.values())
    for claim in kept:
        s.store.claim_put(claim)  # type: ignore[union-attr]
        out.kept += 1
        h.emit("study.claim", claimId=claim.claim_id, resourceType=claim.resource_type, claimKind=claim.kind, url=claim.url)
    read = [name for name in dict.fromkeys(studied) if name in names][: agents.MAX_STUDIED]
    with_claims = {claim.resource_type for claim in kept}
    for name in read:
        if name not in with_claims:
            s.store.claim_put(library.mark_of(name, now))  # type: ignore[union-attr]
    out.studied = len(read)
    if thrown:
        note("claims thrown away: " + ", ".join(f"{reason} {thrown[reason]}" for reason in REASONS if thrown[reason]))
    refused = sum(1 for entry in pages.log if not entry["ok"])
    if refused:
        h.emit("study.note", note=f"{refused} of {len(pages.log)} calls of the page reader were refused or failed")


# -- the entry ---------------------------------------------------------------------------------------------------------------------------------------

def run_study(trigger: str, request_id: str | None, env: Mapping[str, str] | None = None, *, clock: Callable[[], dt.datetime] = utc_now,
              monotonic: Callable[[], float] = time.monotonic, sleep: Callable[[float], None] = time.sleep, transport=default_transport, fetch=None,
              new_id: Callable[[], str] = lambda: uuid.uuid4().hex, extras: "wiring.Extras | None" = None, foundry: "Foundry | None" = None,
              harness: "harness_module.Harness | None" = None) -> Summary:
    """The whole run, with a History line for whatever goes wrong. It never raises: the History says how the run ended.

    `extras` is the loop, whose store keeps the claims; None builds it from the settings. `foundry` is the client of the Foundry project; None builds it from the settings, with the harness
    around the agent (cases/harness.py): a caller that hands in a client of its own hands in the harness too, or none. The documentation is read through the same `transport`."""
    env = os.environ if env is None else env
    redact = Redactor()
    history = History(new_id(), request_id, clock, redact)
    try:
        settings = cfg.load(env)
        identity = Identity(env, sleep=sleep, **({"fetch": fetch} if fetch else {}))
        client = Client(allowed_calls(foundry_endpoint=settings.foundry_endpoint, ai_gateway_host=settings.ai_gateway_host), redact, transport=transport, sleep=sleep, monotonic=monotonic)
        docs = Client(docs_calls(), redact, transport=transport, sleep=sleep, monotonic=monotonic)
        if extras is None:
            extras = wiring.build_extras(env, identity.token, redact, transport=transport, sleep=sleep, monotonic=monotonic, clock=clock)
        if foundry is None and settings.foundry_endpoint:
            foundry = Foundry(settings.foundry_endpoint, client, identity.token, redact)
            harness = harness_module.build(settings, foundry, extras, env=env, clock=clock, monotonic=monotonic, redact=redact)
        services = Services(settings, client, docs, Arm(client, identity.token), history, redact, clock, monotonic, getattr(extras, "store", None), foundry, harness)
        return execute(services, trigger)
    except Exception as error:  # noqa: BLE001 (the History must say how every run ended)
        reason = clean_text(redact(f"{type(error).__name__}: {error}"), 300)
        history.emit("study.finished", state="failed", ok=False, note=reason)
        LOG.error(redact(f"the Study failed: {reason}"))
        return Summary(state="failed", ok=False, note=reason)
