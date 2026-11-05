"""The page shell and the parts that every page is made of: the style, the landmarks, the footer, notices, tables and form fields.

The style has no script and no outside file: Fluent 2 design tokens as CSS custom properties (light and dark), and a block for forced colors.
Every part returns `Safe` text, and every value that goes into it is escaped by `fmt`.
"""
from __future__ import annotations

from typing import Iterable, Mapping, Sequence
from urllib.parse import quote as percent

from .core import Ctx, Response, Safe, esc, fmt, join

HTML = "text/html; charset=utf-8"
TEXT = "text/plain; charset=utf-8"
JSON = "application/json; charset=utf-8"

SIGNIN_ORIGIN = "https://login.microsoftonline.com"
CSP = f"default-src 'none'; style-src 'unsafe-inline'; form-action 'self' {SIGNIN_ORIGIN}; frame-ancestors 'none'; base-uri 'none'"
# `form-action` names Microsoft Entra's sign-in address on purpose: the approve form is answered with a redirect to the sign-in to Azure, and Chromium checks the target of
# a redirect after a form post against this directive. Nothing else is allowed (the page has no script and no outside file).
# "same-origin" and not "no-referrer", on purpose. Under "no-referrer" a browser sends `Origin: null` on every form POST (Fetch standard, "append a request Origin header"), and
# the platform's sign-in refuses an authenticated POST that carries it with an empty 403, before the app is reached: the approve button failed on 2026-11-05 (AGENTS.md rule 28).
# "same-origin" sends the console's own origin on a POST and still sends no referrer to any other site, which is what the header is for: an address holds the request id.
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

STYLE = """
:root{color-scheme:light dark;
--fontFamilyBase:"Segoe UI Variable Text","Segoe UI",system-ui,-apple-system,"Helvetica Neue",Arial,sans-serif;
--fontFamilyMonospace:"Cascadia Mono",Consolas,"Courier New",monospace;
--fontSizeBase200:.875rem;--fontSizeBase300:1rem;--fontSizeBase500:1.25rem;--fontSizeHero700:1.75rem;--fontWeightSemibold:600;
--borderRadiusMedium:4px;--strokeWidthThin:1px;--strokeWidthThick:2px;
--colorNeutralBackground1:#ffffff;--colorNeutralBackground2:#fafafa;--colorNeutralBackground3:#f5f5f5;
--colorNeutralForeground1:#242424;--colorNeutralForeground2:#424242;--colorNeutralForeground3:#616161;--colorNeutralForegroundOnBrand:#ffffff;
--colorNeutralStroke1:#d1d1d1;--colorNeutralStrokeAccessible:#616161;
--colorBrandBackground:#0f6cbd;--colorBrandBackgroundHover:#115ea3;--colorBrandStroke1:#0f6cbd;--colorBrandForegroundLink:#115ea3;
--colorStrokeFocus1:#ffffff;--colorStrokeFocus2:#000000;
--colorPaletteRedBackground1:#fdf3f4;--colorPaletteRedForeground1:#b10e1c;--colorPaletteRedBorder1:#d13438;
--colorPaletteGreenBackground1:#f1faf1;--colorPaletteGreenForeground1:#0e700e;--colorPaletteGreenBorder1:#107c10;
--colorPaletteYellowBackground1:#fffbe6;--colorPaletteYellowForeground1:#835b00;--colorPaletteYellowBorder1:#c19c00;
--colorPaletteBlueBackground1:#ebf3fc}
@media (prefers-color-scheme:dark){:root{
--colorNeutralBackground1:#292929;--colorNeutralBackground2:#1f1f1f;--colorNeutralBackground3:#141414;
--colorNeutralForeground1:#ffffff;--colorNeutralForeground2:#d6d6d6;--colorNeutralForeground3:#adadad;--colorNeutralForegroundOnBrand:#ffffff;
--colorNeutralStroke1:#666666;--colorNeutralStrokeAccessible:#adadad;
--colorBrandBackground:#115ea3;--colorBrandBackgroundHover:#0f6cbd;--colorBrandStroke1:#479ef5;--colorBrandForegroundLink:#479ef5;
--colorStrokeFocus1:#292929;--colorStrokeFocus2:#ffffff;
--colorPaletteRedBackground1:#3f1011;--colorPaletteRedForeground1:#e37d80;--colorPaletteRedBorder1:#dc626d;
--colorPaletteGreenBackground1:#052505;--colorPaletteGreenForeground1:#54b054;--colorPaletteGreenBorder1:#54b054;
--colorPaletteYellowBackground1:#4a3500;--colorPaletteYellowForeground1:#f2c661;--colorPaletteYellowBorder1:#f2c661;
--colorPaletteBlueBackground1:#082338}}
*,*::before,*::after{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--colorNeutralBackground1);color:var(--colorNeutralForeground1);font-family:var(--fontFamilyBase);font-size:var(--fontSizeBase300);line-height:1.5}
a{color:var(--colorBrandForegroundLink);text-underline-offset:.2em}
a:hover{text-decoration-thickness:.15em}
:focus-visible{outline:3px solid var(--colorStrokeFocus2);outline-offset:2px;box-shadow:0 0 0 3px var(--colorStrokeFocus1)}
.skip{position:absolute;left:-100vw;top:0;z-index:10;padding:.75rem 1rem;background:var(--colorNeutralBackground1);color:var(--colorNeutralForeground1)}
.skip:focus{left:0}
.visually-hidden{position:absolute;width:1px;height:1px;margin:-1px;padding:0;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap;border:0}
body>header{display:flex;flex-wrap:wrap;gap:.25rem 1.5rem;align-items:baseline;justify-content:space-between;padding:.75rem 1.25rem;background:var(--colorNeutralBackground3);border-bottom:var(--strokeWidthThin) solid var(--colorNeutralStroke1)}
.brand{margin:0;font-size:var(--fontSizeBase500);font-weight:var(--fontWeightSemibold)}
.brand a{color:inherit;text-decoration:none}
.who{margin:0;color:var(--colorNeutralForeground2);font-size:var(--fontSizeBase200)}
nav{padding:0 1.25rem;border-bottom:var(--strokeWidthThin) solid var(--colorNeutralStroke1)}
nav ul{display:flex;flex-wrap:wrap;gap:0 .25rem;margin:0;padding:0;list-style:none}
nav a{display:inline-block;min-height:2.75rem;padding:.65rem .75rem;border-bottom:3px solid transparent;color:var(--colorNeutralForeground1);text-decoration:none}
nav a:hover{background:var(--colorNeutralBackground3)}
nav a[aria-current="page"]{border-bottom-color:var(--colorBrandStroke1);font-weight:var(--fontWeightSemibold)}
main{max-width:64rem;margin:0 auto;padding:1.25rem}
h1{margin:.5rem 0 .75rem;font-size:var(--fontSizeHero700);line-height:1.25}
h2{margin:1.75rem 0 .5rem;font-size:var(--fontSizeBase500)}
h3{margin:1.25rem 0 .25rem;font-size:1.0625rem}
p{margin:.5rem 0}
.lead{font-size:1.125rem}
.muted{color:var(--colorNeutralForeground2)}
code,.mono{font-family:var(--fontFamilyMonospace);font-size:.9em;overflow-wrap:anywhere}
.notice{margin:1rem 0;padding:.75rem 1rem;border:var(--strokeWidthThin) solid var(--notice-border,var(--colorNeutralStroke1));border-left-width:.5rem;background:var(--notice-bg,var(--colorNeutralBackground2))}
.notice p,.notice ul{margin:.25rem 0}
.notice-title{margin:0 0 .25rem;font-weight:var(--fontWeightSemibold);font-size:1rem}
.notice.info{--notice-bg:var(--colorPaletteBlueBackground1);--notice-border:var(--colorBrandStroke1)}
.notice.success{--notice-bg:var(--colorPaletteGreenBackground1);--notice-border:var(--colorPaletteGreenBorder1)}
.notice.warning{--notice-bg:var(--colorPaletteYellowBackground1);--notice-border:var(--colorPaletteYellowBorder1)}
.notice.error{--notice-bg:var(--colorPaletteRedBackground1);--notice-border:var(--colorPaletteRedBorder1)}
dl.summary{display:grid;grid-template-columns:minmax(9rem,14rem) 1fr;margin:1rem 0;border-top:var(--strokeWidthThin) solid var(--colorNeutralStroke1)}
dl.summary>div{display:contents}
dl.summary dt,dl.summary dd{margin:0;padding:.6rem .75rem .6rem 0;border-bottom:var(--strokeWidthThin) solid var(--colorNeutralStroke1)}
dl.summary dt{font-weight:var(--fontWeightSemibold)}
dl.summary dd{overflow-wrap:anywhere}
.check{margin:1.5rem 0;padding:1rem 1.25rem;border:var(--strokeWidthThick) solid var(--colorBrandStroke1);background:var(--colorNeutralBackground2)}
.check h2{margin-top:0}
.check ol{margin:.5rem 0 0;padding-left:1.25rem}
.warning-text{display:flex;gap:.75rem;align-items:center;margin:.5rem 0}
.sign{display:inline-flex;flex:none;align-items:center;justify-content:center;width:2rem;height:2rem;border:3px solid currentColor;border-radius:50%;font-weight:700}
.actions{display:flex;flex-wrap:wrap;gap:.75rem;margin:1rem 0}
.actions>*{flex:1 1 14rem;max-width:22rem}
.btn,button{display:inline-flex;align-items:center;justify-content:center;min-height:2.75rem;min-width:11rem;padding:.5rem 1.25rem;border:var(--strokeWidthThick) solid var(--colorNeutralStrokeAccessible);border-radius:var(--borderRadiusMedium);background:var(--colorNeutralBackground1);color:var(--colorNeutralForeground1);font:inherit;font-weight:var(--fontWeightSemibold);text-align:center;text-decoration:none;cursor:pointer}
.btn:hover,button:hover{background:var(--colorNeutralBackground3)}
.btn.primary,button.primary{border-color:var(--colorBrandStroke1);background:var(--colorBrandBackground);color:var(--colorNeutralForegroundOnBrand)}
.btn.primary:hover,button.primary:hover{background:var(--colorBrandBackgroundHover)}
.btn.danger,button.danger{border-color:var(--colorPaletteRedBorder1);color:var(--colorPaletteRedForeground1)}
form{margin:1rem 0}
label,legend{display:block;margin:.75rem 0 .25rem;font-weight:var(--fontWeightSemibold)}
.hint{margin:.1rem 0 .4rem;color:var(--colorNeutralForeground2);font-size:var(--fontSizeBase200)}
.field-error{margin:.1rem 0 .4rem;color:var(--colorPaletteRedForeground1);font-weight:var(--fontWeightSemibold)}
input[type=text],input[type=date],input[type=time],input[type=number],select,textarea{display:block;width:100%;max-width:38rem;min-height:2.5rem;padding:.4rem .6rem;border:var(--strokeWidthThin) solid var(--colorNeutralStrokeAccessible);border-radius:var(--borderRadiusMedium);background:var(--colorNeutralBackground1);color:var(--colorNeutralForeground1);font:inherit}
textarea{min-height:6rem;resize:vertical}
.field.error input,.field.error textarea,.field.error select{border:var(--strokeWidthThick) solid var(--colorPaletteRedBorder1)}
fieldset{margin:1rem 0;padding:.25rem 1rem 1rem;border:var(--strokeWidthThin) solid var(--colorNeutralStroke1)}
legend{padding:0 .25rem}
.choice{display:flex;align-items:center;gap:.6rem;min-height:2.5rem}
.choice input{flex:none;width:1.5rem;height:1.5rem;margin:0}
.choice label{display:inline;margin:0;font-weight:400}
.table-wrap{overflow-x:auto;margin:1rem 0;border:var(--strokeWidthThin) solid var(--colorNeutralStroke1)}
table{width:100%;min-width:34rem;border-collapse:collapse}
caption{padding:.6rem .75rem;text-align:left;font-weight:var(--fontWeightSemibold)}
th,td{padding:.55rem .75rem;border-top:var(--strokeWidthThin) solid var(--colorNeutralStroke1);text-align:left;vertical-align:top;overflow-wrap:anywhere}
th{background:var(--colorNeutralBackground3);font-weight:var(--fontWeightSemibold)}
td form{margin:0}
td .btn,td button{min-width:0;min-height:2.5rem;padding:.25rem .75rem}
blockquote.quote{margin:.5rem 0;padding:.5rem 1rem;border-left:.375rem solid var(--colorNeutralStrokeAccessible);background:var(--colorNeutralBackground3);overflow-wrap:anywhere}
.quote-label{margin:.75rem 0 0;color:var(--colorNeutralForeground2);font-size:var(--fontSizeBase200);font-weight:var(--fontWeightSemibold)}
footer{max-width:64rem;margin:2rem auto 0;padding:1rem 1.25rem 2rem;border-top:var(--strokeWidthThin) solid var(--colorNeutralStroke1);color:var(--colorNeutralForeground2);font-size:var(--fontSizeBase200)}
@media (max-width:40em){
main{padding:1rem}
dl.summary{grid-template-columns:1fr}
dl.summary dt{padding-bottom:0;border-bottom:0}
.actions{flex-direction:column}
.actions>*{flex:none;width:100%;max-width:none}
.btn,button{width:100%}
td .btn,td button{width:auto}
}
@media (forced-colors:active){
a{color:LinkText}
.btn,button{border:2px solid ButtonText;background:ButtonFace;color:ButtonText}
.btn.primary,button.primary{border-color:Highlight}
.notice,.check,blockquote.quote,.table-wrap,th,td{border-color:CanvasText}
nav a[aria-current="page"]{border-bottom-color:Highlight}
:focus-visible{outline:3px solid Highlight;box-shadow:none}
}
"""

NAV = (
    ("/", "Home", ()),
    ("/history", "What Meternaut did", ()),
    ("/me/decisions", "My decisions", ()),
    ("/me/activity", "What I did here", ()),
    ("/me/notes", "What I know about your resources", ()),
    ("/me/settings", "Settings", ()),
    ("/ops/permissions", "Standing permissions", ("ops", "owner")),
    ("/ops/pause", "The kill switch", ("ops",)),
)


def respond(status: int, body: str, *, content_type: str = HTML, headers: dict[str, str] | None = None) -> Response:
    """A response. The security headers and the content type are set here, so no response leaves without them."""
    merged = {**(headers or {}), **SECURITY_HEADERS, "Content-Type": content_type}
    return Response(status, merged, body.encode("utf-8", "replace"))


def secured(response: Response) -> Response:
    """The same response with the security headers on it, whatever made it."""
    headers = {**response.headers, **SECURITY_HEADERS}
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


def notice(kind: str, title: str, *body: object) -> Safe:
    """A box with a title that says what it is in words (not by colour alone). `kind` is info, success, warning or error."""
    role = {"error": ' role="alert"', "success": ' role="status"'}.get(kind, "")
    return fmt('<div class="notice {kind}"{role}><p class="notice-title">{title}</p>{body}</div>', kind=kind, role=Safe(role), title=title,
               body=join(block(b) for b in body))


def summary(rows: Sequence[tuple[str, object]]) -> Safe:
    """A list of names and values (the summary list)."""
    return fmt('<dl class="summary">{rows}</dl>', rows=join(fmt("<div><dt>{name}</dt><dd>{value}</dd></div>", name=name, value=value) for name, value in rows))


def quoted(label: str, text: object) -> Safe:
    """Text from outside (an estate, a model, a person) as a labelled quote: escaped, never a link or a control."""
    return fmt('<p class="quote-label">{label}</p><blockquote class="quote">{text}</blockquote>', label=label, text=text)


def table(table_id: str, caption: str, headers: Sequence[str], rows: Sequence[Sequence[object]], *, row_header: bool = False) -> Safe:
    """A data table in a region that scrolls and can be reached with the keyboard. The first column is the row header when `row_header` is set."""
    head = join(fmt('<th scope="col">{h}</th>', h=h) for h in headers)
    body = []
    for row in rows:
        cells = []
        for index, cell in enumerate(row):
            cells.append(fmt('<th scope="row">{c}</th>', c=cell) if row_header and index == 0 else fmt("<td>{c}</td>", c=cell))
        body.append(fmt("<tr>{cells}</tr>", cells=join(cells)))
    return fmt('<div class="table-wrap" role="region" aria-labelledby="{id}" tabindex="0"><table><caption id="{id}">{caption}</caption>'
               "<thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>", id=table_id, caption=caption, head=head, body=join(body))


# -- forms ---------------------------------------------------------------------------------------------------------------------------------------

def hidden(name: str, value: object) -> Safe:
    return fmt('<input type="hidden" name="{name}" value="{value}">', name=name, value=value)


def form(action: str, *content: object, cls: str = "") -> Safe:
    """A form that changes something: always a POST."""
    return fmt('<form method="post" action="{action}"{cls}>{content}</form>', action=action, cls=_class(cls), content=join(content))


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

def ai_line(models: Sequence[str]) -> str:
    return f"Written by AI (models: {', '.join(models) if models else 'none named'}). A person approves every change."


def talk_to_a_person(ctx: Ctx) -> Safe:
    """The same words in the same place on every page: who to write to. The people are the ones with a role of owner or ops (or everybody listed)."""
    people = ctx.services.people.persons
    chosen = ([p for p in people if "ops" in p.roles or "owner" in p.roles] or list(people))[:3]
    names = join((fmt('<a href="mailto:{mail}">{name}</a>', mail=percent(p.mail, safe="@"), name=p.name) if p.mail else esc(p.name) for p in chosen), ", ")
    return fmt('<p class="help"><strong>Talk to a person.</strong> Write to {names}.</p>', names=names) if chosen else Safe("")


def _nav(ctx: Ctx, current: str) -> Safe:
    roles = ctx.principal.roles if ctx.principal else ()
    shown = [(path, name) for path, name, needs in NAV if not needs or any(role in roles for role in needs)]
    return join(fmt('<li><a href="{href}"{here}>{name}</a></li>', href=ctx.url(path), name=name, here=Safe(' aria-current="page"') if path == current else "")
                for path, name in shown)


def page(ctx: Ctx, title: str, body: Safe, *, status: int = 200, current: str = "", ai: bool = False, why: str = "", extra: Safe = Safe(""),
         headers: dict[str, str] | None = None) -> Response:
    """A whole page for a signed-in person: the landmarks, the title, the footer. `extra` goes first in the footer."""
    principal = ctx.principal
    footer = join((
        extra,
        fmt("<p><strong>Why you are seeing this.</strong> {why}</p>", why=why or "You are signed in and listed as a person who may use this console."),
        talk_to_a_person(ctx),
        fmt('<p class="ai">{line}</p>', line=ai_line(ctx.services.models) if ai else "A person approves every change."),
    ))
    document = fmt(
        '<!DOCTYPE html>\n<html lang="en" dir="ltr">\n<head>\n<meta charset="utf-8">\n<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        '<meta name="color-scheme" content="light dark">\n<meta name="robots" content="noindex, nofollow">\n<title>{title} - Meternaut</title>\n'
        '<style>{style}</style>\n</head>\n<body>\n<a class="skip" href="#main">Skip to the content</a>\n'
        '<header>\n<p class="brand"><a href="{home}">Meternaut (AI)</a></p>\n<p class="who">Signed in as {name}. Roles: {roles}.</p>\n</header>\n'
        '<nav aria-label="Pages"><ul>{nav}</ul></nav>\n<main id="main">\n{body}\n</main>\n<footer>\n{footer}\n</footer>\n</body>\n</html>\n',
        title=title, style=Safe(STYLE), home=ctx.url("/"), name=principal.name if principal else "", roles=", ".join(principal.roles) if principal else "",
        nav=_nav(ctx, current), body=body, footer=footer)
    return respond(status, document, headers=headers)


def message_page(ctx: Ctx, status: int, title: str, *lines: object, back: tuple[str, str] | None = None, ai: bool = False, why: str = "",
                 current: str = "", extra: Safe = Safe("")) -> Response:
    """A short page: a title, a few lines, and a link back."""
    back_link = paragraph(link(ctx.url(back[0]), back[1])) if back else Safe("")
    body = fmt("<h1>{title}</h1>{lines}{back}", title=title, lines=join(block(line) for line in lines), back=back_link)
    return page(ctx, title, body, status=status, ai=ai, why=why, current=current, extra=extra)


def denied() -> Response:
    """The page for a person who is not signed in or not listed. It says nothing about the system."""
    document = fmt('<!DOCTYPE html>\n<html lang="en" dir="ltr">\n<head>\n<meta charset="utf-8">\n<meta name="viewport" content="width=device-width, initial-scale=1">\n'
                   '<meta name="robots" content="noindex, nofollow">\n<title>No access</title>\n<style>{style}</style>\n</head>\n<body>\n'
                   '<main id="main">\n<h1>No access</h1>\n<p>This account cannot open this page.</p>\n</main>\n</body>\n</html>\n', style=Safe(STYLE))
    return respond(403, document)
