"""The people that the console and the mail know: the directory object id of each, the roles, and the address that a letter goes to.

They come from one setting, `CONSOLE_PEOPLE`: a JSON list such as
`[{"oid": "<object id>", "name": "Tino", "roles": ["owner", "approver", "ops"], "mail": "name@example.com"}]`.
A person that is not in the list sees nothing, and no letter goes to an address that is not in it.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Mapping

from .models import ROLES, Principal

SETTING = "CONSOLE_PEOPLE"
GUID = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
ADDRESS = re.compile(r"^[A-Za-z0-9._%+'-]{1,64}@[A-Za-z0-9.-]{1,200}\.[A-Za-z]{2,24}$")
MAX_PEOPLE = 20


class PeopleError(Exception):
    """The setting is missing or wrong; the text says what, and never holds an address."""


@dataclass(frozen=True)
class Person:
    oid: str
    name: str
    roles: tuple[str, ...]
    mail: str


@dataclass(frozen=True)
class People:
    persons: tuple[Person, ...]

    def by_oid(self, oid: str) -> Person | None:
        wanted = (oid or "").lower()
        return next((p for p in self.persons if p.oid.lower() == wanted), None)

    def principal(self, oid: str | None, name: str | None = None) -> Principal | None:
        """The signed-in person as a Principal, or None when the object id is not in the list."""
        person = self.by_oid(oid or "")
        return None if person is None else Principal(person.oid.lower(), person.name, person.roles)

    def with_role(self, role: str) -> tuple[Person, ...]:
        return tuple(p for p in self.persons if role in p.roles)

    def allowed_addresses(self) -> frozenset[str]:
        return frozenset(p.mail.lower() for p in self.persons if p.mail)


def load(env: Mapping[str, str]) -> People:
    raw = env.get(SETTING, "").strip()
    if not raw:
        raise PeopleError(f"{SETTING} is not set")
    try:
        document = json.loads(raw)
    except ValueError as error:
        raise PeopleError(f"{SETTING} is not JSON") from error
    if not isinstance(document, list) or not document or len(document) > MAX_PEOPLE:
        raise PeopleError(f"{SETTING} is a list of one to {MAX_PEOPLE} people")
    persons: list[Person] = []
    for index, item in enumerate(document, 1):
        if not isinstance(item, dict):
            raise PeopleError(f"person {index} is not an object")
        oid, name, roles, mail = item.get("oid"), item.get("name"), item.get("roles"), item.get("mail", "")
        if not isinstance(oid, str) or not GUID.match(oid):
            raise PeopleError(f"person {index} has no object id")
        if not isinstance(name, str) or not 1 <= len(name) <= 80:
            raise PeopleError(f"person {index} has no name")
        if not isinstance(roles, list) or not roles or not all(r in ROLES for r in roles):
            raise PeopleError(f"person {index} has roles that are not among {', '.join(ROLES)}")
        if mail and (not isinstance(mail, str) or not ADDRESS.match(mail)):
            raise PeopleError(f"person {index} has an address that is not an address")
        persons.append(Person(oid.lower(), name, tuple(dict.fromkeys(roles)), mail))
    if len({p.oid for p in persons}) != len(persons):
        raise PeopleError("an object id is listed twice")
    return People(tuple(persons))
