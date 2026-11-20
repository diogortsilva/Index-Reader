"""Small helpers for treating an .xlsx as the zip archive it is."""

from __future__ import annotations

import re
import zipfile

FIXED_DATE = (1980, 1, 1, 0, 0, 0)
_CORE_TIME = re.compile(
    r"(<dcterms:(created|modified)[^>]*>)[^<]*(</dcterms:(?:created|modified)>)")


def make_deterministic(path):
    """Rewrite an .xlsx so the same content always gives the same bytes.

    Zip entry timestamps are fixed and the created/modified times that the
    spreadsheet library stamps into docProps/core.xml are replaced.
    """
    with zipfile.ZipFile(path, "r") as source:
        entries = [(info, source.read(info.filename)) for info in source.infolist()]
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as target:
        for info, payload in entries:
            if info.filename == "docProps/core.xml":
                text = payload.decode("utf-8")
                text = _CORE_TIME.sub(r"\g<1>2000-01-01T00:00:00Z\g<3>", text)
                payload = text.encode("utf-8")
            clean = zipfile.ZipInfo(info.filename, FIXED_DATE)
            clean.compress_type = zipfile.ZIP_DEFLATED
            clean.external_attr = 0o600 << 16
            target.writestr(clean, payload)
