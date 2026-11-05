"""The web console of Meternaut: server-rendered pages with no script, as one pure handler.

    request = parse_request(method, url, headers, body)
    response = handle(request, Services(store=..., decider=..., delegate=..., people=..., now=..., host=..., acts_on=..., models=...))

The person comes from the sign-in headers of the platform (`x-ms-client-principal-id`) and is looked up in the list of people; nothing else names a person.
A page that only shows something never changes anything: every change is a POST with a one-time token. Everything here is the standard library only.
"""
from .core import Request, Response, Services, parse_request
from .router import handle

__all__ = ["Request", "Response", "Services", "handle", "parse_request"]
