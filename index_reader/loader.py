"""Read the Instrument Index workbook and verify its column headers.

The reference layout is remembered in sample_headers.py. Every time a workbook
is loaded, each column the tool depends on is located by its header text, so
added, deleted or shifted columns are detected instead of silently misread.
"""

from __future__ import annotations

import hashlib
import warnings

from . import config
from .sample_headers import SAMPLE_HEADERS


class HeaderError(Exception):
    """The workbook layout cannot be matched to the reference layout."""

    def __init__(self, message, report=None):
        Exception.__init__(self, message)
        self.report = report


def norm_header(value):
    if value is None:
        return ""
    return " ".join(str(value).upper().split())


def clean(value):
    """Cell value -> trimmed text. Blank-like tokens become ''."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, float):
        if value == int(value):
            value = int(value)
    text = " ".join(str(value).split())
    if text.upper() in config.BLANK_TOKENS:
        return ""
    return text


def col_letter(index):
    """1 -> A, 27 -> AA."""
    letters = ""
    while index > 0:
        index, rem = divmod(index - 1, 26)
        letters = chr(65 + rem) + letters
    return letters


def col_index(letters):
    index = 0
    for ch in letters:
        index = index * 26 + (ord(ch) - 64)
    return index


class FieldMatch(object):
    def __init__(self, field, sample_letter, code, description):
        self.field = field
        self.sample_letter = sample_letter
        self.code = code
        self.description = description
        self.letter = None       # where it was found in this workbook
        self.status = "MISSING"  # OK | MOVED | RENAMED | MISSING | AMBIGUOUS
        self.note = ""
        self.required = field in config.REQUIRED_FIELDS


class HeaderReport(object):
    def __init__(self):
        self.sheet = ""
        self.code_row = None
        self.desc_row = None
        self.first_data_row = None
        self.fields = []            # list of FieldMatch
        self.removed = []           # sample headers no longer present
        self.added = []             # headers present but not in the sample
        self.errors = []

    @property
    def ok(self):
        return not self.errors

    @property
    def changed(self):
        return [f for f in self.fields if f.status != "OK"]

    def lines(self):
        out = ["Sheet '%s': header rows %s/%s, data from row %s"
               % (self.sheet, self.code_row, self.desc_row, self.first_data_row)]
        moved = [f for f in self.fields if f.status in ("MOVED", "RENAMED")]
        missing = [f for f in self.fields if f.status in ("MISSING", "AMBIGUOUS")]
        if not moved and not missing:
            out.append("All %d mapped columns match the reference layout." % len(self.fields))
        for f in moved:
            out.append("%s: %s (reference column %s, found in %s) %s"
                       % (f.status, f.description or f.code, f.sample_letter, f.letter, f.note))
        for f in missing:
            out.append("%s%s: %s (reference column %s) %s"
                       % (f.status, " - REQUIRED" if f.required else "",
                          f.description or f.code, f.sample_letter, f.note))
        if self.removed:
            out.append("%d reference column(s) not found in this workbook: %s"
                       % (len(self.removed), "; ".join(self.removed[:12])
                          + (" ..." if len(self.removed) > 12 else "")))
        if self.added:
            out.append("%d column(s) not in the reference layout: %s"
                       % (len(self.added), "; ".join(self.added[:12])
                          + (" ..." if len(self.added) > 12 else "")))
        return out


class IndexData(object):
    """Result of loading a workbook."""

    def __init__(self):
        self.path = ""
        self.sha256 = ""
        self.sheet = ""
        self.report = None
        self.columns = {}     # field -> column letter (or None when missing)
        self.rows = []        # list of (row number, {field: text})


def file_sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _pick_sheet(workbook):
    if config.SHEET_NAME in workbook.sheetnames:
        return workbook[config.SHEET_NAME]
    wanted = set(h[2] for h in SAMPLE_HEADERS if h[2])
    best, best_score = None, 0
    for sheet in workbook.worksheets:
        score = 0
        for row in sheet.iter_rows(min_row=1, max_row=10, values_only=True):
            score = max(score, sum(1 for v in row if norm_header(v) in wanted))
        if score > best_score:
            best, best_score = sheet, score
    if best is None or best_score < 10:
        raise HeaderError("No sheet named '%s' and no sheet with a matching header row."
                          % config.SHEET_NAME)
    return best


def _find_header_rows(top_rows):
    """Return (code_row, desc_row) as 1-based row numbers (code_row may be None)."""
    codes = set(h[1] for h in SAMPLE_HEADERS if h[1])
    descs = set(h[2] for h in SAMPLE_HEADERS if h[2])
    tag_code = config.expected_header("tag")[1]
    tag_desc = config.expected_header("tag")[2]
    best_desc, best_desc_score = None, 0
    best_code, best_code_score = None, 0
    for number, row in enumerate(top_rows, start=1):
        values = [norm_header(v) for v in row]
        desc_score = sum(1 for v in values if v in descs) + (50 if tag_desc in values else 0)
        code_score = sum(1 for v in values if v in codes) + (50 if tag_code in values else 0)
        if desc_score > best_desc_score:
            best_desc, best_desc_score = number, desc_score
        if code_score > best_code_score:
            best_code, best_code_score = number, code_score
    if best_desc_score < 10 and best_code_score < 10:
        raise HeaderError("Could not find the header rows in the first %d rows." % len(top_rows))
    if best_desc_score < 10:
        best_desc = None
    if best_code_score < 10 or best_code == best_desc:
        # rows 1 and 2 share some texts ("I/O TYPE", "DRAWING"); keep them apart
        best_code = None
        if best_desc is not None and best_desc > 1:
            values = [norm_header(v) for v in top_rows[best_desc - 2]]
            if sum(1 for v in values if v in codes) >= 10:
                best_code = best_desc - 1
    return best_code, best_desc


def _match_fields(code_values, desc_values, report):
    """Locate every mapped field by header text. Fills report.fields."""
    columns = {}
    width = max(len(code_values), len(desc_values))

    def at(values, index):
        return values[index] if index < len(values) else ""

    for field in sorted(config.FIELD_LETTERS, key=lambda f: col_index(config.FIELD_LETTERS[f])):
        letter, code, desc = config.expected_header(field)
        match = FieldMatch(field, letter, code, desc)
        sample_pos = col_index(letter) - 1
        by_desc = [i for i in range(width) if desc and at(desc_values, i) == desc]
        by_code = [i for i in range(width) if code and at(code_values, i) == code]
        both = [i for i in by_desc if i in by_code]
        found = None
        if sample_pos in by_desc:
            # 1. still where the reference layout has it
            found = sample_pos
        elif len(both) == 1:
            # 2. moved: one column carries both the description and the short code
            found = both[0]
        elif len(by_desc) == 1:
            # 3. moved: matched on the description alone
            found = by_desc[0]
        elif not by_desc and sample_pos in by_code:
            # 4. description edited in place; short code still matches
            found = sample_pos
            match.note = "(description text changed; matched on the short code)"
        elif not by_desc and len(by_code) == 1:
            # 5. moved and description edited; short code still unique
            found = by_code[0]
            match.note = "(description text changed; matched on the short code)"
        elif len(by_desc) > 1 or len(by_code) > 1:
            match.status = "AMBIGUOUS"
            match.note = "(header text appears in columns %s)" % ", ".join(
                col_letter(i + 1) for i in (by_desc or by_code))
        if found is not None:
            match.letter = col_letter(found + 1)
            if found == sample_pos:
                match.status = "OK" if not match.note else "RENAMED"
            else:
                match.status = "MOVED" if not match.note else "RENAMED"
        columns[field] = match.letter
        report.fields.append(match)
        if match.letter is None and match.required:
            report.errors.append("Required column not found: %s (reference column %s)"
                                 % (desc or code, letter))

    # informational diff of the whole header row against the sample
    present = set()
    for i in range(width):
        present.add((at(code_values, i), at(desc_values, i)))
    present_desc = set(p[1] for p in present if p[1])
    sample_desc = set(h[2] for h in SAMPLE_HEADERS if h[2])
    for letter, code, desc in SAMPLE_HEADERS:
        if desc and desc not in present_desc:
            report.removed.append("%s %s" % (letter, desc))
    for i in range(width):
        desc = at(desc_values, i)
        if desc and desc not in sample_desc:
            report.added.append("%s %s" % (col_letter(i + 1), desc))
    return columns


def load_index(path):
    """Load the workbook. Raises HeaderError when required columns are missing."""
    import openpyxl  # imported here so the rest of the package has no hard dependency

    data = IndexData()
    data.path = path
    data.sha256 = file_sha256(path)
    with warnings.catch_warnings():
        # openpyxl warns about Excel features it does not read (dropdown lists);
        # they are irrelevant here because the workbook is only read for values.
        warnings.simplefilter("ignore")
        return _load(openpyxl, path, data)


def _load(openpyxl, path, data):
    workbook = openpyxl.load_workbook(path, read_only=True, data_only=True)
    try:
        sheet = _pick_sheet(workbook)
        report = HeaderReport()
        report.sheet = sheet.title
        all_rows = sheet.iter_rows(values_only=True)
        top = []
        for row in all_rows:
            top.append(row)
            if len(top) == 10:
                break
        code_row, desc_row = _find_header_rows(top)
        report.code_row, report.desc_row = code_row, desc_row
        code_values = [norm_header(v) for v in top[code_row - 1]] if code_row else []
        desc_values = [norm_header(v) for v in top[desc_row - 1]] if desc_row else []
        columns = _match_fields(code_values, desc_values, report)
        first_data = max(r for r in (code_row, desc_row) if r) + 1
        report.first_data_row = first_data
        data.report = report
        data.sheet = sheet.title
        data.columns = columns
        if report.errors:
            raise HeaderError("The workbook layout does not match the reference layout:\n  "
                              + "\n  ".join(report.errors), report)

        positions = dict((f, col_index(l) - 1) for f, l in columns.items() if l)

        def to_record(raw):
            record = {}
            for field in config.FIELD_LETTERS:
                pos = positions.get(field)
                record[field] = clean(raw[pos]) if pos is not None and pos < len(raw) else ""
            return record

        number = 0
        for raw in top:
            number += 1
            if number >= first_data:
                data.rows.append((number, to_record(raw)))
        for raw in all_rows:
            number += 1
            data.rows.append((number, to_record(raw)))
    finally:
        workbook.close()
    return data
