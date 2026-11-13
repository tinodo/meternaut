"""The web pages of Meternaut: server-rendered pages as one pure handler. No page has a script but one: the page that a button on a Teams card opens has a fixed script that sends the form of the
answer (web/layout.py).

    request = parse_request(method, url, headers, body)
    response = handle(request, Services(store=..., decider=..., delegate=..., people=..., now=..., host=..., acts_on=..., models=...))

The person comes from the sign-in headers of the platform (`x-ms-client-principal-id`) and is looked up in the list of people; nothing else names a person.
A page that only shows something never changes anything: every change is a POST with a one-time token. Everything here is the standard library only.
"""
from .core import Request, Response, Services, parse_request
from .router import handle

__all__ = ["Request", "Response", "Services", "handle", "parse_request"]
