"""Keeps secrets out of everything that the app writes: log lines, History lines and error texts."""
from __future__ import annotations

import re

REDACTED = "[redacted]"

_HEADER_VALUE = re.compile(r"(?i)\b(api-key|ocp-apim-subscription-key|authorization|x-identity-header)\b(\s*[:=]\s*)(bearer\s+)?[^\s,;\"']+")
_BEARER = re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]{8,}")
_JWT = re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{5,}")


class Redactor:
    """Replaces every secret that was registered, and everything that looks like a header value or a token."""

    def __init__(self) -> None:
        self._secrets: set[str] = set()

    def add(self, secret: object) -> None:
        if isinstance(secret, str) and len(secret) >= 8:
            self._secrets.add(secret)

    def __call__(self, text: object) -> str:
        result = str(text)
        for secret in sorted(self._secrets, key=len, reverse=True):
            result = result.replace(secret, REDACTED)
        result = _HEADER_VALUE.sub(lambda m: f"{m.group(1)}{m.group(2)}{REDACTED}", result)
        result = _BEARER.sub(f"Bearer {REDACTED}", result)
        return _JWT.sub(REDACTED, result)
