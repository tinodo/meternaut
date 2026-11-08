"""Settings of the signed-in person: the page, the strict check of what is posted, the export and the deletion.

The page offers four things and nothing else: where I write to the person first, the quiet hours, how many other letters a week, and a pause. What the form does not carry
(language, time zone, working days, the day of the weekly summary, mutes) keeps the value that is stored, and is checked as strictly as before when a form does send it.
The settings are stored with the directory object id and nothing else about the person. Deleting them deletes the person's notes too, and keeps the approval records,
which hold only an object id and follow the retention of the organisation that runs Meternaut.
"""
from __future__ import annotations

import dataclasses
import datetime as dt
import json
import re

from ..models import CHANNELS, SettingsRecord
from .common import read
from .core import Ctx, Response, Safe, canonical_zone, fmt, join, stamp
from .layout import (JSON, block, button, choices, details, error_summary, field, form, hidden, link, message_page, notice, page, paragraph, respond)

NOT_APPLIED = "Quiet hours are saved and not applied yet: a letter can arrive at any time."
CHANNEL_HINT = "With only the weekly summary, no other letter is sent. A request that waits for your answer is on the Decisions page whatever you choose."
WEEKLY_BUDGET_HINT = "How many other letters a week. 0 means only the weekly summary. A request that waits for your answer and the first letter to you are never counted."
CHANNEL_WORDS = (("email", "E-mail"), ("teams", "Teams (not built yet, so e-mail is used)"), ("desk", "Only the weekly summary"))
HOURS = re.compile(r"(?:[01]\d|2[0-3]):[0-5]\d")
DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
MUTE = re.compile(r"[a-z0-9][a-z0-9-]{0,23}")
MAX_MUTES = 10
MAX_BUDGET = 10
MAX_PAUSE_DAYS = 366


def _values(record: SettingsRecord, now: dt.datetime) -> dict[str, str]:
    """The values of a stored record as the form shows them. A pause is shown as its date, and only while the date is still ahead."""
    match = re.match(r"\d{4}-\d{2}-\d{2}", record.paused_until or "")
    shown = match.group(0) if match and match.group(0) > now.date().isoformat() else ""
    return {"channel": record.channel, "quiet_from": record.quiet_from, "quiet_to": record.quiet_to, "weekly_budget": str(record.weekly_budget), "paused_until": shown}


def parse_settings(form_data: dict[str, str], oid: str, now: dt.datetime, base: SettingsRecord | None = None) -> tuple[SettingsRecord | None, dict[str, str]]:
    """The settings from a posted form, or the problems with each field. Every field is checked strictly: a value that is not one of the allowed ones is refused.

    The four settings of the page are required. A field that the page no longer offers (language, time zone, working days, the day of the weekly summary, mutes) is taken
    from `base` (the stored settings) when the form does not send it, and is checked when it does."""
    errors: dict[str, str] = {}
    base = base or SettingsRecord(oid=oid)
    today = now.date()
    first = today + dt.timedelta(days=1)
    last = today + dt.timedelta(days=MAX_PAUSE_DAYS)

    channel = form_data.get("channel", "")
    if channel not in CHANNELS:
        errors["channel"] = "Choose e-mail, Teams or only the weekly summary."
    language, zone, days, desk, mutes = base.language, base.timezone, list(base.working_days), str(base.desk_day), list(base.mutes)
    if "language" in form_data:
        language = form_data["language"]
        if language != "en":
            errors["language"] = "English is the only language at present."
    if "timezone" in form_data:
        found = canonical_zone(form_data["timezone"])
        if found is None:
            errors["timezone"] = "Enter a time zone name that exists, for example Europe/Amsterdam."
        else:
            zone = found
    if "working_days" in form_data:
        days = []
        for token in re.split(r"[,\s]+", form_data["working_days"].strip()):
            if token and (token not in {"1", "2", "3", "4", "5", "6", "7"} or int(token) in days):
                days = []
                errors["working_days"] = "Choose working days from Monday (1) to Sunday (7), each once."
                break
            if token:
                days.append(int(token))
        if not days and "working_days" not in errors:
            errors["working_days"] = "Choose at least one working day."
    for name, label in (("quiet_from", "Quiet hours start"), ("quiet_to", "Quiet hours end")):
        if not HOURS.fullmatch(form_data.get(name, "")):
            errors[name] = f"{label} must be a time as HH:MM, from 00:00 to 23:59."
    if "desk_day" in form_data:
        desk = form_data["desk_day"]
        if desk not in {"1", "2", "3", "4", "5", "6", "7"}:
            errors["desk_day"] = "Choose the day of the weekly summary, from Monday (1) to Sunday (7)."
    budget = form_data.get("weekly_budget", "")
    if not re.fullmatch(r"\d{1,2}", budget) or int(budget) > MAX_BUDGET:
        errors["weekly_budget"] = f"Enter a whole number from 0 to {MAX_BUDGET}."
    paused = form_data.get("paused_until", "")
    paused_until: str | None = None
    if paused:
        try:
            day = dt.date.fromisoformat(paused) if DATE.fullmatch(paused) else None
        except ValueError:
            day = None
        if day is None or not first <= day <= last:
            errors["paused_until"] = f"Enter a date from {first.isoformat()} to {last.isoformat()} as YYYY-MM-DD, or leave it empty."
        else:
            paused_until = f"{day.isoformat()}T00:00:00Z"
    if "mutes" in form_data:
        mutes = []
        for word in (w for w in re.split(r"[,\s]+", form_data["mutes"].strip().lower()) if w):
            if not MUTE.fullmatch(word):
                errors["mutes"] = "Use short words of letters, digits and hyphens, up to 24 characters each, separated by commas."
                break
            if word not in mutes:
                mutes.append(word)
        if len(mutes) > MAX_MUTES and "mutes" not in errors:
            errors["mutes"] = f"Use at most {MAX_MUTES} words."
    if errors:
        return None, errors
    return SettingsRecord(oid=oid, channel=channel, language=language, timezone=zone, working_days=tuple(sorted(days)), quiet_from=form_data["quiet_from"],
                          quiet_to=form_data["quiet_to"], desk_day=int(desk), weekly_budget=int(budget), paused_until=paused_until, mutes=tuple(mutes),
                          updated_at=stamp(now)), {}


def _form(ctx: Ctx, values: dict[str, str], errors: dict[str, str]) -> Safe:
    first = ctx.now.date() + dt.timedelta(days=1)
    last = ctx.now.date() + dt.timedelta(days=MAX_PAUSE_DAYS)
    fields = join([
        choices("channel", "Where I write to you first", "channel", CHANNEL_WORDS, values.get("channel", ""), hint=CHANNEL_HINT, error=errors.get("channel", "")),
        fmt('<fieldset id="quiet-hours"><legend>Quiet hours</legend>{start}{end}</fieldset>',
            start=field("quiet_from", "quiet_from", "No letters from", values.get("quiet_from", ""), kind="time", error=errors.get("quiet_from", ""), required=True),
            end=field("quiet_to", "quiet_to", "No letters until", values.get("quiet_to", ""), kind="time", error=errors.get("quiet_to", ""), required=True)),
        field("weekly_budget", "weekly_budget", "Other letters a week, at most", values.get("weekly_budget", ""), kind="number", hint=WEEKLY_BUDGET_HINT,
              error=errors.get("weekly_budget", ""), required=True, attrs={"min": "0", "max": str(MAX_BUDGET), "step": "1", "inputmode": "numeric"}),
        field("paused_until", "paused_until", "Pause my letters until", values.get("paused_until", ""), kind="date", error=errors.get("paused_until", ""),
              hint=f"Leave it empty for no pause. A date from {first.isoformat()} to {last.isoformat()}.", attrs={"min": first.isoformat(), "max": last.isoformat()}),
    ])
    return form(ctx.url("/me/settings"), hidden("nonce", ctx.nonce("settings")), fields, fmt('<div class="actions">{b}</div>', b=button("Save settings", kind="primary")))


def _your_data(ctx: Ctx) -> Safe:
    """Taking a copy of what is stored, or deleting it, and the notes: under one disclosure, because few people need them."""
    return details("Your data and your notes",
                   paragraph(link(ctx.url("/me/notes"), "Your notes and do-not-touch marks")),
                   paragraph("You can take a copy of your settings and notes, or delete them. Deleting removes your settings and your notes. Approval records are not deleted: they hold "
                             "only your directory object id, and they follow the retention of the organisation that runs Meternaut."),
                   form(ctx.url("/me/settings/export"), hidden("nonce", ctx.nonce("settings-export")), fmt('<div class="actions">{b}</div>', b=button("Download my settings and notes", kind="secondary"))),
                   form(ctx.url("/me/settings/delete"), hidden("nonce", ctx.nonce("settings-delete")), fmt('<div class="actions">{b}</div>', b=button("Delete my settings and notes", kind="danger"))))


def settings_page(ctx: Ctx, *, values: dict[str, str] | None = None, errors: dict[str, str] | None = None, banner: Safe | None = None, status: int = 200) -> Response:
    record, ok = read(lambda: ctx.store.settings_get(ctx.principal.oid), SettingsRecord(oid=ctx.principal.oid))  # type: ignore[union-attr]
    values = values if values is not None else _values(record, ctx.now)
    errors = errors or {}
    parts: list[object] = [Safe("<h1>Settings</h1>"), paragraph("How and when I write to you. They are stored with your directory object id and nothing else about you.", "lead")]
    if banner is not None:
        parts.append(banner)
    if not ok:
        parts.append(notice("warning", "Your settings cannot be read", "The values below are the starting values, not what you saved."))
    if errors:
        parts.append(error_summary(list(errors.items())))
    parts += [fmt('<div class="notice info" id="not-applied"><p>{text}</p></div>', text=NOT_APPLIED), _form(ctx, values, errors), _your_data(ctx)]
    return page(ctx, "Settings", join(block(p) for p in parts), current="/me/settings", status=status, why="these are the settings that belong to you")


def _refused(ctx: Ctx, back: str) -> Response:
    return message_page(ctx, 403, "This form cannot be used", "The form is out of date, was used already or has no token. Nothing was changed.",
                        "Open the page again and use the form there.", back=(back, "Back to the page"))


def settings_save(ctx: Ctx) -> Response:
    if not ctx.store.nonce_use(ctx.request.form.get("nonce", ""), ctx.principal.oid, "settings"):  # type: ignore[union-attr]
        return _refused(ctx, "/me/settings")
    stored, _ = read(lambda: ctx.store.settings_get(ctx.principal.oid), None)  # type: ignore[union-attr]
    record, errors = parse_settings(ctx.request.form, ctx.principal.oid, ctx.now, stored)  # type: ignore[union-attr]
    if record is None:
        return settings_page(ctx, values=dict(ctx.request.form), errors=errors, status=400)
    ctx.store.settings_put(record)
    return settings_page(ctx, values=_values(record, ctx.now), banner=notice("success", "Saved", "Your settings are saved."))


def settings_export(ctx: Ctx) -> Response:
    """The person's settings and notes as a JSON file: this person's data and nobody else's."""
    if not ctx.store.nonce_use(ctx.request.form.get("nonce", ""), ctx.principal.oid, "settings-export"):  # type: ignore[union-attr]
        return _refused(ctx, "/me/settings")
    oid = ctx.principal.oid  # type: ignore[union-attr]
    document = {"exportedAt": stamp(ctx.now), "oid": oid, "settings": dataclasses.asdict(ctx.store.settings_get(oid)),
                "notes": [dataclasses.asdict(note) for note in ctx.store.notes_of(oid)]}
    return respond(200, json.dumps(document, indent=2, sort_keys=True, ensure_ascii=False) + "\n", content_type=JSON,
                   headers={"Content-Disposition": 'attachment; filename="meternaut-my-data.json"'})


def settings_delete(ctx: Ctx) -> Response:
    """Deletes the person's settings and notes. The approval records stay."""
    if not ctx.store.nonce_use(ctx.request.form.get("nonce", ""), ctx.principal.oid, "settings-delete"):  # type: ignore[union-attr]
        return _refused(ctx, "/me/settings")
    oid = ctx.principal.oid  # type: ignore[union-attr]
    for note in ctx.store.notes_of(oid):
        ctx.store.note_delete(oid, note.note_id)
    ctx.store.settings_delete(oid)
    return message_page(ctx, 200, "Deleted", "Your settings and your notes are deleted.",
                        "Approval records are kept. They hold only your directory object id, and they follow the retention of the organisation that runs Meternaut.",
                        back=("/me/settings", "Back to settings"), why="you deleted your settings and your notes")
