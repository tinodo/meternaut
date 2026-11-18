"""Who comes after a person on the ladder of a request that waits (cases/escalation.py): the next person, and the word of the source that named them.

The sources are tried in this order, and each is reported by a closed word (models.ESCALATION_SOURCES): `manager` (the manager that Microsoft Entra names for the person, when the setting
ESCALATE_TO says managers: Graph `GET /users/{id}/manager`), `tag` (an address in the escalation tag of the resource, its resource group or its subscription), `contact` (the people of the list with
the role escalation) and `owners` (the people with the role owner, when nothing else was found: a request is never dropped and never sent nowhere). A lookup that fails is not an error: it is a
note, a word of NOTES, and the next source is tried. What Graph gives is text from a directory: only a Member of the tenant with a mail address, an enabled account and no place on the deny
list is a target, the name is cleaned and cut, and nothing else of the profile is kept. The only Graph calls are the two reads of http.directory_calls (the permission User.Read.All), and a
result is cached for the life of the Directory, which is one round of the timer or the Watch.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Collection

from .http import Client, HttpError, GRAPH_HOST
from .people import ADDRESS, GUID, People, Person
from .roles import clean_text

GRAPH = f"https://{GRAPH_HOST}/v1.0/users/"
GRAPH_RESOURCE = "https://graph.microsoft.com"
SELECT = "?$select=id,displayName,mail,userType,accountEnabled"
# What could not be looked up or used on the way: the closed words that a step keeps, and the plain sentence that a message says about each.
NOTES = {
    "no_manager": "No manager is set for the person in the directory.",
    "no_permission": "I could not look up the manager (no permission yet).",
    "throttled": "I could not look up the manager (the directory asked me to wait).",
    "unreachable": "I could not look up the manager (the directory did not answer).",
    "disabled": "The account that was found is disabled, so it was skipped.",
    "no_mail": "The person that was found has no mail address, so it was skipped.",
    "not_member": "The person that was found is not a member of this organisation, so it was skipped.",
    "denied": "The person that was found is on the list of people who are never written to, so it was skipped.",
    "tag_invalid": "The escalation tag does not hold a mail address, so it was skipped.",
    "no_contact": "No escalation contact is set.",
}
LOOKUP_FAILED = ("no_permission", "throttled", "unreachable")


@dataclass(frozen=True)
class Target:
    """One person that an escalation step goes to: the object id, a name that is cleaned and cut (text from a directory: shown escaped, never trusted) and the address."""

    oid: str
    name: str
    mail: str
    listed: bool = False  # on the list of people (cases/people.py): the other targets are the exception that cases/mail.py audits


@dataclass(frozen=True)
class Next:
    targets: tuple[Target, ...]
    source: str  # one of models.ESCALATION_SOURCES
    notes: tuple[str, ...] = ()  # words of NOTES, in the order in which they happened


def of_person(person: Person) -> Target:
    return Target(person.oid.lower(), clean_text(person.name, 80) or "a colleague", person.mail.lower(), True)


class Directory:
    """`client` is a Client whose list is http.directory_calls() (None: no lookup is made and the note says no permission), `managers` is the setting ESCALATE_TO."""

    def __init__(self, client: Client | None, token: Callable[[str], str] | None, people: People, *, managers: bool = False, deny: Collection[str] = ()) -> None:
        self.client, self.token, self.people, self.managers = client, token, people, managers
        self.deny = tuple(item.strip().lower() for item in deny if item.strip())
        self._cache: dict[str, tuple[dict | None, str]] = {}

    def _get(self, path: str, missing: str) -> tuple[dict | None, str]:
        if path in self._cache:
            return self._cache[path]
        if self.client is None or self.token is None:
            return None, "no_permission"
        try:
            answer = self.client.request("GET", GRAPH + path, headers={"Authorization": f"Bearer {self.token(GRAPH_RESOURCE)}"}, retries=1, retry_after_max=10, timeout=20).json()
            result = (answer, "") if isinstance(answer, dict) else (None, "unreachable")
        except HttpError as error:
            result = (None, missing if error.status == 404 else "no_permission" if error.status in (401, 403) else "throttled" if error.status == 429 else "unreachable")
        except Exception:  # noqa: BLE001 (a token that cannot be had, or a call that the list refuses, is a lookup that did not happen)
            result = (None, "unreachable")
        self._cache[path] = result
        return result

    def _denied(self, mail: str) -> bool:
        return any(mail == item or (item.startswith("@") and mail.endswith(item)) for item in self.deny)

    def vet(self, profile: object) -> tuple[Target | None, str]:
        """The target that a directory profile makes, or the word of why not: a Member of the tenant, enabled, with a mail address that is an address, and not on the deny list."""
        if not isinstance(profile, dict) or not GUID.match(str(profile.get("id") or "")) or profile.get("userType") != "Member":
            return None, "not_member"
        if profile.get("accountEnabled") is False:
            return None, "disabled"
        mail = str(profile.get("mail") or "").strip().lower()
        if not ADDRESS.match(mail):
            return None, "no_mail"
        if self._denied(mail):
            return None, "denied"
        oid = str(profile["id"]).lower()
        listed = self.people.by_oid(oid)
        return Target(oid, clean_text(profile.get("displayName"), 80) or "a colleague", mail, listed is not None and listed.mail.lower() == mail), ""

    def manager_of(self, oid: str) -> tuple[Target | None, str]:
        profile, note = self._get(f"{oid.lower()}/manager{SELECT}", "no_manager") if GUID.match(oid or "") else (None, "no_manager")
        return (None, note) if profile is None else self.vet(profile)

    def by_oid(self, oid: str) -> tuple[Target | None, str]:
        """The target for an object id: a person of the list is known already, any other is looked up and vetted again (a person may have left or been disabled since)."""
        known = self.people.by_oid(oid)
        if known is not None and known.mail:
            return of_person(known), ""
        profile, note = self._get(f"{oid.lower()}{SELECT}", "not_member") if GUID.match(oid or "") else (None, "not_member")
        return (None, note) if profile is None else self.vet(profile)

    def by_address(self, address: str) -> tuple[Target | None, str]:
        """The target for an address that an escalation tag holds: a person of the list is known already, any other is looked up and vetted."""
        mail = (address or "").strip().lower()
        if not ADDRESS.match(mail):
            return None, "tag_invalid"
        known = next((p for p in self.people.persons if p.mail.lower() == mail), None)
        if known is not None:
            return of_person(known), ""
        if self._denied(mail):
            return None, "denied"
        profile, note = self._get(f"{mail}{SELECT}", "not_member")
        return (None, note) if profile is None else self.vet(profile)

    def _listed(self, role: str) -> tuple[Target, ...]:
        return tuple(of_person(p) for p in self.people.with_role(role) if p.mail and not self._denied(p.mail.lower()))

    def owners(self) -> tuple[Target, ...]:
        return self._listed("owner")

    def contacts(self) -> Next:
        """The escalation contacts, or the owners with the note that none is set, or everybody on the list when no owner has an address: never nobody."""
        found = self._listed("escalation")
        if found:
            return Next(found, "contact")
        everyone = tuple(of_person(p) for p in self.people.persons if p.mail)
        return Next(self._listed("owner") or everyone, "owners", ("no_contact",))

    def next_after(self, oids: Collection[str], *, after: str = "", tag: Callable[[], str] = lambda: "", skip: Collection[str] = ()) -> Next:
        """The next person after the people with these object ids. `after` is the source that the step before used: a manager goes on to the manager's manager and then to the contacts, the
        other sources go on to the sources after them. `skip` holds the people who were told already: a manager or an address among them is passed over, a contact and an owner are not (the last
        link is told again, and again). `tag` is called only when its turn comes: it reads the tags of the resource, the group and the subscription."""
        told, notes = {s.lower() for s in skip}, []
        if self.managers and after in ("", "manager"):
            for oid in oids:
                target, note = self.manager_of(oid)
                if target is not None and target.oid not in told:
                    return Next((target,), "manager", tuple(dict.fromkeys(notes)))
                if note:
                    notes.append(note)
        if after in ("", "tag"):
            address = tag()
            if address:
                target, note = self.by_address(address)
                if target is not None and target.oid not in told:
                    return Next((target,), "tag", tuple(dict.fromkeys(notes)))
                if note:
                    notes.append(note)
        found = self.contacts()
        return Next(found.targets, found.source, tuple(dict.fromkeys(notes + list(found.notes))))
