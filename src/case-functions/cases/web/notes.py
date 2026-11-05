"""What I know about your resources: the notes and do-not-touch marks of the signed-in person.

A note is about one resource and never wider: the resource id is checked to be the id of one resource, not of a group or a subscription. Every note
has an expiry, at most a year away. Text of a note is shown escaped, in a quote, and never acts as a link or a control.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import re

from ..models import NOTE_KINDS, NoteRecord
from .common import read
from .core import MAX_NOTE, Ctx, Response, Safe, clean_line, fmt, join, link_part, parse_time, stamp
from .layout import (block, button, choices, error_summary, field, form, hidden, message_page, notice, page, paragraph, table, textarea)

GUID = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
# A resource group name does not end with a period. The rest is the id of one resource: a provider and at least one pair of type and name.
RESOURCE_ID = re.compile(rf"/subscriptions/{GUID}/resourcegroups/[a-z0-9._()-]{{0,89}}[a-z0-9_()-]/providers/[a-z0-9.]{{1,80}}(?:/[a-z0-9._()~-]{{1,100}}){{2,16}}", re.I)
DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
MAX_DAYS = 365
MAX_NOTES = 100
SOURCE = "you, on the notes page"
KIND_WORDS = (("note", "A note: something that is known about this resource"),
              ("do_not_touch", "A do-not-touch mark: Meternaut proposes no change for this resource until the mark expires"))
UNDERSTOOD = {"note": "A note about this one resource. It stops nothing.",
              "do_not_touch": "A do-not-touch mark on this one resource. No plan is made for it, and no change is made to it, until the mark expires."}


def is_one_resource(resource_id: str) -> bool:
    """The id of one resource: a subscription, a resource group, a provider and at least one pair of type and name. A group or a subscription is not one."""
    if not RESOURCE_ID.fullmatch(resource_id):
        return False
    parts = resource_id.split("/")
    tail = parts[7:]
    return len(tail) >= 2 and len(tail) % 2 == 0 and not any(set(part) <= {"."} for part in parts[1:])


def parse_note(form_data: dict[str, str], oid: str, now: dt.datetime) -> tuple[NoteRecord | None, dict[str, str]]:
    errors: dict[str, str] = {}
    today = now.date()
    last = today + dt.timedelta(days=MAX_DAYS)
    kind = form_data.get("kind", "")
    if kind not in NOTE_KINDS:
        errors["kind"] = "Choose a note or a do-not-touch mark."
    resource_id = clean_line(form_data.get("resource_id", ""))
    if not is_one_resource(resource_id):
        errors["resource_id"] = ("Enter the id of one resource: /subscriptions/<id>/resourceGroups/<name>/providers/<type>/<name>. "
                                 "A resource group or a subscription is not accepted.")
    text = clean_line(form_data.get("text", ""))
    if not text:
        errors["text"] = "Write what you know about the resource."
    elif len(text) > MAX_NOTE:
        errors["text"] = f"The text has {len(text)} characters. The most is {MAX_NOTE}."
    expires = form_data.get("expires", "")
    day = None
    if DATE.fullmatch(expires):
        try:
            day = dt.date.fromisoformat(expires)
        except ValueError:
            day = None
    if day is None or not today <= day <= last:
        errors["expires"] = f"Enter an expiry date from {today.isoformat()} to {last.isoformat()} as YYYY-MM-DD. A note always expires."
    if errors:
        return None, errors
    expires_at = f"{expires}T23:59:59Z"
    note_id = "n" + hashlib.sha256(f"{oid}|{kind}|{resource_id.lower()}|{text}|{stamp(now)}".encode("utf-8")).hexdigest()[:12]
    return NoteRecord(note_id=note_id, oid=oid, kind=kind, text=text, scope_resource_id=resource_id, understood_as=UNDERSTOOD[kind], source=SOURCE,
                      created_at=stamp(now), expires_at=expires_at, uses=0), {}


def _row(ctx: Ctx, note: NoteRecord, token: str) -> list[object]:
    ended = parse_time(note.expires_at)
    expired = ended is not None and ctx.now >= ended
    kind = "Do-not-touch mark" if note.kind == "do_not_touch" else "Note"
    delete = form(ctx.url(f"/me/notes/{link_part(note.note_id)}/delete"), hidden("nonce", token),
                  button(fmt('Delete<span class="visually-hidden"> the note about {rid}</span>', rid=note.scope_resource_id or "no resource"), kind="danger"))
    return [kind, note.scope_resource_id or "no resource is named", fmt('<blockquote class="quote">{text}</blockquote>', text=note.text), note.understood_as, note.source,
            ctx.when(note.created_at), fmt("{when}{state}", when=ctx.when(note.expires_at), state=" (expired)" if expired else ""), str(note.uses), delete]


def notes_page(ctx: Ctx, *, values: dict[str, str] | None = None, errors: dict[str, str] | None = None, banner: Safe | None = None, status: int = 200) -> Response:
    values, errors = values or {}, errors or {}
    notes, ok = read(lambda: ctx.store.notes_of(ctx.principal.oid), [])  # type: ignore[union-attr]
    today = ctx.now.date()
    last = today + dt.timedelta(days=MAX_DAYS)
    parts: list[object] = [
        Safe("<h1>What I know about your resources</h1>"),
        paragraph("Here is everything that you told Meternaut about your resources. A note is about one resource and never more. Every note expires, and you can delete one "
                  "at any time.", "lead"),
    ]
    if banner is not None:
        parts.append(banner)
    if errors:
        parts.append(error_summary(list(errors.items())))
    parts.append(Safe("<h2>Your notes</h2>"))
    if not ok:
        parts.append(notice("error", "Your notes cannot be read", "I cannot read your notes now. Nothing has changed."))
    elif not notes:
        parts.append(paragraph("You have no note and no do-not-touch mark."))
    else:
        token = ctx.nonce("note-delete")
        parts.append(table("notes", "Notes and marks, newest first", ["Kind", "Resource", "What you wrote", "How it was understood", "Source", "Added", "Expires", "Times used", "Delete"],
                           [_row(ctx, note, token) for note in notes]))
    parts += [
        Safe("<h2>Add a note or a do-not-touch mark</h2>"),
        paragraph("A do-not-touch mark stops changes to that resource until it expires or you delete it. Only a person sets or clears it."),
        form(ctx.url("/me/notes"), hidden("nonce", ctx.nonce("note-add")),
             choices("kind", "What to add", "kind", KIND_WORDS, values.get("kind", "note"), error=errors.get("kind", "")),
             field("resource_id", "resource_id", "Resource id", values.get("resource_id", ""), hint="The id of one resource, as Azure shows it. A resource group or a subscription is not accepted.",
                   error=errors.get("resource_id", ""), required=True, maxlength=400),
             textarea("text", "text", "What you know", values.get("text", ""), hint=f"Up to {MAX_NOTE} characters.", error=errors.get("text", ""), maxlength=MAX_NOTE),
             field("expires", "expires", "Expires on", values.get("expires", ""), kind="date", hint=f"Required. From {today.isoformat()} up to {last.isoformat()}.",
                   error=errors.get("expires", ""), required=True, attrs={"min": today.isoformat(), "max": last.isoformat()}),
             fmt('<div class="actions">{b}</div>', b=button("Save", kind="primary"))),
    ]
    return page(ctx, "What I know about your resources", join(block(p) for p in parts), current="/me/notes", status=status, why="These are the notes that you wrote.")


def _refused(ctx: Ctx) -> Response:
    return message_page(ctx, 403, "This form cannot be used", "The form is out of date, was used already or has no token. Nothing was changed.",
                        "Open the page again and use the form there.", back=("/me/notes", "Back to your notes"))


def notes_add(ctx: Ctx) -> Response:
    if not ctx.store.nonce_use(ctx.request.form.get("nonce", ""), ctx.principal.oid, "note-add"):  # type: ignore[union-attr]
        return _refused(ctx)
    note, errors = parse_note(ctx.request.form, ctx.principal.oid, ctx.now)  # type: ignore[union-attr]
    if note is None:
        return notes_page(ctx, values=dict(ctx.request.form), errors=errors, status=400)
    if len(ctx.store.notes_of(ctx.principal.oid)) >= MAX_NOTES:  # type: ignore[union-attr]
        return notes_page(ctx, values=dict(ctx.request.form), errors={"text": f"You have {MAX_NOTES} notes. Delete one before you add another."}, status=400)
    ctx.store.note_put(note)
    return notes_page(ctx, banner=notice("success", "Saved", "Your note is saved. It expires on the date that you gave."))


def notes_delete(ctx: Ctx, note_id: str) -> Response:
    oid = ctx.principal.oid  # type: ignore[union-attr]
    if not ctx.store.nonce_use(ctx.request.form.get("nonce", ""), oid, "note-delete"):
        return _refused(ctx)
    if not any(note.note_id == note_id for note in ctx.store.notes_of(oid)):
        return message_page(ctx, 404, "I cannot find this note", "You have no note with this address. Nothing has changed.", back=("/me/notes", "Back to your notes"))
    ctx.store.note_delete(oid, note_id)
    return notes_page(ctx, banner=notice("success", "Deleted", "The note is deleted."))
