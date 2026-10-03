"""HTTP header helpers for safe Unicode attachment filenames.

Starlette encodes HTTP header values as latin-1.  Report filenames may contain
Persian/Unicode assignment titles, so a raw Unicode ``filename=`` parameter can
raise ``UnicodeEncodeError`` before the response is sent.

This module is presentation-only.  It does not alter report contents or
assessment state.
"""
from __future__ import annotations

import re
import unicodedata
from urllib.parse import quote


_CONTROL_OR_SEPARATOR_RE = re.compile(r"[\x00-\x1f\x7f\\/]+")
_QUOTE_RE = re.compile(r'[\"]+')


def _safe_filename(value: str) -> str:
    """Normalize a filename and remove characters unsafe for HTTP headers."""
    normalized = unicodedata.normalize("NFC", str(value or "")).strip()
    normalized = normalized.replace("\r", "").replace("\n", "")
    normalized = _CONTROL_OR_SEPARATOR_RE.sub("_", normalized)
    normalized = _QUOTE_RE.sub("_", normalized)
    return normalized or "download"


def _ascii_fallback(value: str) -> str:
    """Build an ASCII-only filename for legacy clients/header encoding."""
    cleaned = _safe_filename(value)
    ascii_value = cleaned.encode("ascii", "replace").decode("ascii")
    # ``encode(..., 'replace')`` uses '?' for non-ASCII characters; underscores
    # are less ambiguous for a filename fallback.
    ascii_value = ascii_value.replace("?", "_")
    return ascii_value or "download"


def content_disposition_attachment(filename: str, *, fallback: str = "download") -> str:
    """Return an RFC 5987-compatible attachment Content-Disposition value.

    ``filename`` is carried in UTF-8 percent-encoded ``filename*`` form, while
    ``filename`` remains strictly ASCII for Starlette/legacy clients.
    """
    safe_name = _safe_filename(filename)
    safe_fallback = _ascii_fallback(fallback)
    encoded_name = quote(safe_name, safe="!#$&+-.^_`|~")
    return (
        f'attachment; filename="{safe_fallback}"; '
        f"filename*=UTF-8''{encoded_name}"
    )
