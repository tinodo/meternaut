"""The page shell and the parts that every page is made of: the style, the landmarks, the footer, notices, tables and form fields.

The style is the one stylesheet of the style guide (style.py): no outside file, Fluent 2 design tokens as CSS custom properties (light and dark), and a block for forced
colors. No page has a script but the one that sends the answer of a button on a Teams card (below). Every part returns `Safe` text, and every value that goes into it is escaped by `fmt`.
"""
from __future__ import annotations

import base64
import hashlib
from typing import Iterable, Mapping, Sequence

from ..brief import contact_text
from .core import Ctx, Response, Safe, esc, fmt, join
from .style import STYLE

HTML = "text/html; charset=utf-8"
TEXT = "text/plain; charset=utf-8"
JSON = "application/json; charset=utf-8"

SIGNIN_ORIGIN = "https://login.microsoftonline.com"
CSP = f"default-src 'none'; style-src 'unsafe-inline'; form-action 'self' {SIGNIN_ORIGIN}; frame-ancestors 'none'; base-uri 'none'"
# `form-action` names Microsoft Entra's sign-in address on purpose: the approve form is answered with a redirect to the sign-in to Azure, and Chromium checks the target of
# a redirect after a form post against this directive. Nothing else is allowed (a page has no script and no outside file, but the one below).
# The page that a button on a Teams card opens sends the form of the answer by itself with one fixed script, which the policy of that page allows by its hash (not 'unsafe-inline'); with scripts off it has a button.
SEND_SCRIPT = 'var f=document.getElementById("send");if(f){f.submit();}'
SEND_HASH = "sha256-" + base64.b64encode(hashlib.sha256(SEND_SCRIPT.encode("utf-8")).digest()).decode("ascii")
CSP_SEND = f"default-src 'none'; script-src '{SEND_HASH}'; style-src 'unsafe-inline'; form-action 'self' {SIGNIN_ORIGIN}; frame-ancestors 'none'; base-uri 'none'"
# "same-origin" and not "no-referrer", on purpose. Under "no-referrer" a browser sends `Origin: null` on every form POST (Fetch standard, "append a request Origin header"), and
# the platform's sign-in refuses an authenticated POST that carries it with an empty 403, before the app is reached: the approve button failed on 2026-11-05 (AGENTS.md rule 28).
# "same-origin" sends the function app's own origin on a POST and still sends no referrer to any other site, which is what the header is for: an address holds the request id.
SECURITY_HEADERS = {
    "Content-Security-Policy": CSP,
    "X-Frame-Options": "DENY",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "same-origin",
    "Cache-Control": "no-store",
    "Cross-Origin-Opener-Policy": "same-origin",
    "Cross-Origin-Resource-Policy": "same-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=(), payment=(), usb=()",
}

NAV = (
    ("/", "Decisions", ()),
    ("/history", "History", ()),
    ("/me/settings", "Settings", ()),
    ("/ops", "Operations", ("ops",)),
)


def respond(status: int, body: str, *, content_type: str = HTML, headers: dict[str, str] | None = None, sends: bool = False) -> Response:
    """A response. The security headers and the content type are set here, so no response leaves without them. `sends`: the page that sends the answer of a card's button, which has CSP_SEND."""
    merged = {**(headers or {}), **SECURITY_HEADERS, "Content-Type": content_type}
    if sends:
        merged["Content-Security-Policy"] = CSP_SEND
    return Response(status, merged, body.encode("utf-8", "replace"))


def secured(response: Response) -> Response:
    """The same response with the security headers on it, whatever made it (CSP_SEND is kept)."""
    headers = {**response.headers, **SECURITY_HEADERS}
    if response.headers.get("Content-Security-Policy") == CSP_SEND:
        headers["Content-Security-Policy"] = CSP_SEND
    headers.setdefault("Content-Type", HTML)
    return Response(response.status, headers, response.body)


# -- small parts ---------------------------------------------------------------------------------------------------------------------------------

def _class(cls: str) -> Safe:
    return fmt(' class="{cls}"', cls=cls) if cls else Safe("")


def paragraph(text: object, cls: str = "") -> Safe:
    """Text (or an inline fragment) in a paragraph."""
    return fmt("<p{cls}>{text}</p>", cls=_class(cls), text=text)


def block(content: object) -> Safe:
    """A block of HTML. `Safe` text is taken to be a block already; plain text becomes a paragraph."""
    return content if isinstance(content, Safe) else paragraph(content)


def link(href: str, text: object, cls: str = "") -> Safe:
    return fmt('<a href="{href}"{cls}>{text}</a>', href=href, text=text, cls=_class(cls))


def items(values: Iterable[object], cls: str = "") -> Safe:
    return fmt("<ul{cls}>{items}</ul>", cls=_class(cls), items=join(fmt("<li>{v}</li>", v=v) for v in values))


def code(text: object) -> Safe:
    return fmt("<code>{text}</code>", text=text)


def nowrap(text: object) -> Safe:
    """Text that stays on one line, for a date in a table: a column of dates that wraps is a tall row of seven short lines."""
    return fmt('<span class="nw">{text}</span>', text=text)


def notice(kind: str, title: str, *body: object) -> Safe:
    """A box that says what it is in words (not by colour alone). `kind` is info, success, warning or error. Its title is a line of its own; a box with no title is only its lines."""
    role = {"error": ' role="alert"', "success": ' role="status"'}.get(kind, "")
    heading = fmt('<p class="notice-title">{title}</p>', title=title) if title else Safe("")
    return fmt('<div class="notice {kind}"{role}>{heading}{body}</div>', kind=kind, role=Safe(role), heading=heading, body=join(block(b) for b in body))


def summary(rows: Sequence[tuple[str, object]]) -> Safe:
    """A list of names and values (the summary list)."""
    return fmt('<dl class="summary">{rows}</dl>', rows=join(fmt("<div><dt>{name}</dt><dd>{value}</dd></div>", name=name, value=value) for name, value in rows))


def quoted(label: str, text: object) -> Safe:
    """Text from outside (an estate, a model, a person) as a labelled quote: escaped, never a link or a control."""
    return fmt('<p class="quote-label">{label}</p><blockquote class="quote">{text}</blockquote>', label=label, text=text)


def details(label: str, *content: object) -> Safe:
    """One collapsed disclosure: the label, and what only a person who wants the whole record needs."""
    return fmt('<details class="more"><summary>{label}</summary><div>{content}</div></details>', label=label, content=join(block(c) for c in content))


def head(title: str, lead: str = "", aside: object = "") -> Safe:
    """The top of a page of the guide: the title, one sentence under it that says what the page holds, and at the right what the page offers (the links to sort it, for example)."""
    sentence = fmt("<p>{lead}</p>", lead=lead) if lead else Safe("")
    return fmt('<div class="head"><div><h1>{title}</h1>{sentence}</div>{aside}</div>', title=title, sentence=sentence, aside=aside)


def kpi(label: str, value: str, unit: str = "", note: str = "", good: bool = False) -> Safe:
    """A tile of the summary: a label, one figure with its unit and one note. It is green only for a saving (the guide)."""
    return fmt('<li class="kpi{good}"><p class="k">{label}</p><p class="v">{value}{unit}</p><p class="n">{note}</p></li>', good=" good" if good else "", label=label, value=value,
               unit=Safe(f"<small> {esc(unit)}</small>") if unit else Safe(""), note=note)


def kpis(*tiles: Safe, label: str = "Summary") -> Safe:
    """The tiles of the summary, side by side where there is room and one above the other where there is not."""
    return fmt('<ul class="kpis" aria-label="{label}">{tiles}</ul>', label=label, tiles=join(tiles))


def panel(anchor: str, title: str, *content: object) -> Safe:
    """A grey panel with its own heading: one thing that a person does or reads together (a group of settings, one switch)."""
    return fmt('<section class="panel" aria-labelledby="{anchor}"><h2 id="{anchor}">{title}</h2>{content}</section>', anchor=anchor, title=title, content=join(block(c) for c in content))


def table(table_id: str, caption: str, headers: Sequence[str], rows: Sequence[Sequence[object]], *, row_header: bool = False, quiet_caption: bool = False) -> Safe:
    """A data table in a region that scrolls and can be reached with the keyboard. The first column is the row header when `row_header` is set; the caption is only for a screen reader
    when `quiet_caption` is set (the table sits under a heading that says the same)."""
    head = join(fmt('<th scope="col">{h}</th>', h=h) for h in headers)
    body = []
    for row in rows:
        cells = []
        for index, cell in enumerate(row):
            cells.append(fmt('<th scope="row">{c}</th>', c=cell) if row_header and index == 0 else fmt("<td>{c}</td>", c=cell))
        body.append(fmt("<tr>{cells}</tr>", cells=join(cells)))
    return fmt('<div class="table-wrap" role="region" aria-labelledby="{id}" tabindex="0"><table><caption id="{id}"{quiet}>{caption}</caption>'
               "<thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>", id=table_id, caption=caption, head=head, body=join(body),
               quiet=Safe(' class="visually-hidden"') if quiet_caption else Safe(""))


# -- forms ---------------------------------------------------------------------------------------------------------------------------------------

def hidden(name: str, value: object) -> Safe:
    return fmt('<input type="hidden" name="{name}" value="{value}">', name=name, value=value)


def form(action: str, *content: object, cls: str = "", ident: str = "") -> Safe:
    """A form that changes something: always a POST. `ident` is the id of the form, for the one page whose script sends it."""
    return fmt('<form method="post" action="{action}"{ident}{cls}>{content}</form>', action=action, ident=fmt(' id="{ident}"', ident=ident) if ident else Safe(""), cls=_class(cls),
               content=join(content))


def button(label: str, *, name: str = "", value: str = "", kind: str = "") -> Safe:
    named = fmt(' name="{name}" value="{value}"', name=name, value=value) if name else Safe("")
    return fmt('<button type="submit"{named} class="{kind}">{label}</button>', named=named, kind=kind or "secondary", label=label)


def _described(field_id: str, hint: str, error: str) -> tuple[Safe, Safe, Safe]:
    hint_html = fmt('<p class="hint" id="{id}-hint">{hint}</p>', id=field_id, hint=hint) if hint else Safe("")
    error_html = (fmt('<p class="field-error" id="{id}-error"><span class="visually-hidden">Error: </span>{error}</p>', id=field_id, error=error)
                  if error else Safe(""))
    ids = " ".join(part for part, present in ((f"{field_id}-hint", hint), (f"{field_id}-error", error)) if present)
    return hint_html, error_html, (fmt(' aria-describedby="{ids}"', ids=ids) if ids else Safe(""))


def field(field_id: str, name: str, label: str, value: object = "", *, kind: str = "text", hint: str = "", error: str = "", maxlength: int | None = None,
          required: bool = False, list_id: str = "", attrs: Mapping[str, str] | None = None) -> Safe:
    """A labelled input. `attrs` are more attributes (min, max, inputmode): the names are the page's own, the values are escaped."""
    hint_html, error_html, described = _described(field_id, hint, error)
    more = list((attrs or {}).items())
    if maxlength:
        more.append(("maxlength", str(int(maxlength))))
    if list_id:
        more.append(("list", list_id))
    attributes = join(fmt(' {n}="{v}"', n=n, v=v) for n, v in more)
    required_attr = Safe(" required") if required else Safe("")
    return fmt('<div class="field{state}"><label for="{id}">{label}</label>{hint}{error}<input type="{kind}" id="{id}" name="{name}" value="{value}"{attributes}{required}{described}></div>',
               state=" error" if error else "", id=field_id, label=label, hint=hint_html, error=error_html, kind=kind, name=name, value=value, attributes=attributes,
               required=required_attr, described=described)


def textarea(field_id: str, name: str, label: str, value: object = "", *, hint: str = "", error: str = "", maxlength: int | None = None, rows: int = 4) -> Safe:
    hint_html, error_html, described = _described(field_id, hint, error)
    limit = Safe(f' maxlength="{int(maxlength)}"') if maxlength else Safe("")
    return fmt('<div class="field{state}"><label for="{id}">{label}</label>{hint}{error}<textarea id="{id}" name="{name}" rows="{rows}"{limit}{described}>{value}</textarea></div>',
               state=" error" if error else "", id=field_id, label=label, hint=hint_html, error=error_html, name=name, rows=rows, limit=limit, described=described,
               value=value)


def select(field_id: str, name: str, label: str, options: Sequence[tuple[str, str]], value: str, *, hint: str = "", error: str = "") -> Safe:
    hint_html, error_html, described = _described(field_id, hint, error)
    rendered = join(fmt('<option value="{v}"{selected}>{t}</option>', v=v, t=t, selected=Safe(" selected") if v == value else "") for v, t in options)
    return fmt('<div class="field{state}"><label for="{id}">{label}</label>{hint}{error}<select id="{id}" name="{name}"{described}>{options}</select></div>',
               state=" error" if error else "", id=field_id, label=label, hint=hint_html, error=error_html, name=name, described=described, options=rendered)


def choices(group_id: str, legend: str, name: str, options: Sequence[tuple[str, str]], value: str, *, hint: str = "", error: str = "") -> Safe:
    """A group of radio buttons with one legend."""
    hint_html, error_html, _ = _described(group_id, hint, error)
    rendered = join(fmt('<div class="choice"><input type="radio" id="{id}-{v}" name="{name}" value="{v}"{checked}><label for="{id}-{v}">{t}</label></div>',
                        id=group_id, v=v, name=name, t=t, checked=Safe(" checked") if v == value else "") for v, t in options)
    return fmt('<fieldset id="{id}"><legend>{legend}</legend>{hint}{error}{options}</fieldset>', id=group_id, legend=legend, hint=hint_html, error=error_html,
               options=rendered)


def checks(group_id: str, legend: str, name: str, boxes: Sequence[tuple[str, str, bool]], *, hint: str = "", error: str = "") -> Safe:
    """A group of check boxes that share one name. Each is (value, label, checked); the values of the boxes that are on come back joined with commas."""
    hint_html, error_html, _ = _described(group_id, hint, error)
    rendered = join(fmt('<div class="choice"><input type="checkbox" id="{id}-{v}" name="{name}" value="{v}"{checked}><label for="{id}-{v}">{t}</label></div>',
                        id=group_id, name=name, v=v, t=t, checked=Safe(" checked") if on else "") for v, t, on in boxes)
    return fmt('<fieldset id="{id}"><legend>{legend}</legend>{hint}{error}{boxes}</fieldset>', id=group_id, legend=legend, hint=hint_html, error=error_html,
               boxes=rendered)


def error_summary(problems: Sequence[tuple[str, str]]) -> Safe:
    """The list at the top of a form that was refused. Each line links to its field."""
    return fmt('<div class="notice error" role="alert" aria-labelledby="problem-title"><h2 class="notice-title" id="problem-title">There is a problem</h2>'
               "<p>Nothing was saved.</p>{list}</div>", list=items(link(f"#{anchor}", message) for anchor, message in problems))


# -- the page --------------------------------------------------------------------------------------------------------------------------------------

def talk_to_a_person(ctx: Ctx) -> str:
    """The one person to write to, as plain text with the address and no link: the first with the role owner or ops (everybody listed, when none has one) who is not the person
    who reads the page, or that person when nobody else is listed. Empty when nobody is listed."""
    people = ctx.services.people.persons
    chosen = [p for p in people if "ops" in p.roles or "owner" in p.roles] or list(people)
    me = ctx.principal.oid.lower() if ctx.principal else ""
    return ", ".join(contact_text(p.name, p.mail) for p in ([p for p in chosen if p.oid.lower() != me] or chosen)[:1])


AI_LINE = "Recommendations written by AI. A person approves every change."


def footer_line(ctx: Ctx, ai: bool, why: str, models: Sequence[str] | None = None) -> Safe:
    """The foot of every page. A page that shows text that an AI wrote has one quiet line that says so and that a person approves every change. Every page has "About this page", which holds
    the models (for a page with AI text), why this person sees the page and who answers for Meternaut: rule 13 (b) to (d) of AGENTS.md, in plain text and with no link."""
    names = ", ".join(ctx.services.models if models is None else models)
    written = fmt("Models: {names}. ", names=names) if ai and names else Safe("")
    person = talk_to_a_person(ctx)
    owner = fmt(" Responsible for Meternaut: {person}.", person=person) if person else Safe("")
    about = fmt("<details><summary>About this page</summary><p>{written}You see this because {why}.{owner}</p></details>", written=written,
                why=why or "you are listed as a person who may use this page", owner=owner)
    return join([paragraph(AI_LINE) if ai else Safe(""), about])


def _nav(ctx: Ctx, current: str) -> Safe:
    roles = ctx.principal.roles if ctx.principal else ()
    shown = [(path, name) for path, name, needs in NAV if not needs or any(role in roles for role in needs)]
    return join(fmt('<li><a href="{href}"{here}>{name}</a></li>', href=ctx.url(path), name=name, here=Safe(' aria-current="page"') if path == current else "")
                for path, name in shown)


def page(ctx: Ctx, title: str, body: Safe, *, status: int = 200, current: str = "", ai: bool = False, why: str = "", models: Sequence[str] | None = None,
         headers: dict[str, str] | None = None, wide: bool = False, sends: bool = False) -> Response:
    """A whole page for a signed-in person: the landmarks, the title, the footer. `why` finishes the sentence "You see this because ..." of "About this page". `wide` is for the page
    of the decisions, which has room for a chart beside the text. `sends` is for the page that sends the answer of a button on a card by itself (respond)."""
    principal = ctx.principal
    footer = footer_line(ctx, ai, why, models)
    document = fmt(
        '<!DOCTYPE html>\n<html lang="en" dir="ltr">\n<head>\n<meta charset="utf-8">\n<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        '<meta name="color-scheme" content="light dark">\n<meta name="robots" content="noindex, nofollow">\n<title>{title} - Meternaut</title>\n'
        '<style>{style}</style>\n</head>\n<body>\n<a class="skip" href="#main">Skip to the content</a>\n'
        '<header>\n<p class="brand"><a href="{home}">Meternaut (AI)</a></p>\n<p class="who">Signed in as {name}. Roles: {roles}.</p>\n</header>\n'
        '<nav aria-label="Pages"><ul>{nav}</ul></nav>\n<main id="main"{wide}>\n{body}\n</main>\n<footer>\n{footer}\n</footer>\n</body>\n</html>\n',
        title=title, style=Safe(STYLE), home=ctx.url("/"), name=principal.name if principal else "", roles=", ".join(principal.roles) if principal else "",
        nav=_nav(ctx, current), body=body, footer=footer, wide=Safe(' class="wide"') if wide else Safe(""))
    return respond(status, document, headers=headers, sends=sends)


def message_page(ctx: Ctx, status: int, title: str, *lines: object, back: tuple[str, str] | None = None, ai: bool = False, why: str = "", current: str = "", kind: str = "") -> Response:
    """A short page of the guide: a title, one box that says in its edge, its colour and its place what kind of news the lines are (information, success, warning or error; when the caller
    does not say, the status decides: success below 300, error from 500, warning between), and one main button back."""
    kind = kind or ("success" if status < 300 else "error" if status >= 500 else "warning")
    way = fmt('<p class="acts"><a class="btn primary" href="{href}">{label}</a></p>', href=ctx.url(back[0]), label=back[1]) if back else Safe("")
    body = fmt("<h1>{title}</h1>{box}{back}", title=title, box=notice(kind, "", *lines), back=way)
    return page(ctx, title, body, status=status, ai=ai, why=why, current=current)


def denied() -> Response:
    """The page for a person who is not signed in or not listed. It says nothing about the system."""
    document = fmt('<!DOCTYPE html>\n<html lang="en" dir="ltr">\n<head>\n<meta charset="utf-8">\n<meta name="viewport" content="width=device-width, initial-scale=1">\n'
                   '<meta name="robots" content="noindex, nofollow">\n<title>No access</title>\n<style>{style}</style>\n</head>\n<body>\n'
                   '<main id="main">\n<h1>No access</h1>\n<p>This account cannot open this page.</p>\n</main>\n</body>\n</html>\n', style=Safe(STYLE))
    return respond(403, document)
