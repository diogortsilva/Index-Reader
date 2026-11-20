"""Build small synthetic Instrument Index workbooks for the tests.

No project data is used: headers come from the remembered reference layout
and every row is invented.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import openpyxl  # noqa: E402
from openpyxl.utils import column_index_from_string  # noqa: E402

from index_reader import config  # noqa: E402
from index_reader.sample_headers import SAMPLE_HEADERS  # noqa: E402


def make_workbook(path, rows, insert_before=None, drop=None, rename=None,
                  sheet_name=None, extra_sheets=None):
    """rows: list of {field: value}. Data starts on sheet row 3.

    insert_before: column letter - a new column is inserted there (shifts the rest)
    drop:          column letter - its two header cells are blanked
    rename:        {column letter: new row-2 description}
    sheet_name:    name of the main tab (default: LOOP)
    extra_sheets:  {tab name: list of rows} - additional tabs, added after the main one
    """
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.title = sheet_name or config.SHEET_NAME
    for letter, code, description in SAMPLE_HEADERS:
        column = column_index_from_string(letter)
        if drop == letter:
            continue
        if code:
            sheet.cell(1, column, code)
        text = description
        if rename and letter in rename:
            text = rename[letter]
        if text:
            sheet.cell(2, column, text)
    for offset, row in enumerate(rows):
        for field, value in row.items():
            column = column_index_from_string(config.FIELD_LETTERS[field])
            sheet.cell(3 + offset, column, value)
    if insert_before:
        sheet.insert_cols(column_index_from_string(insert_before))
        sheet.cell(2, column_index_from_string(insert_before), "A NEW COLUMN")
    other = workbook.create_sheet("LIST")
    other["A1"] = "untouched"
    for name, lines in (extra_sheets or {}).items():
        extra = workbook.create_sheet(name)
        for line in lines:
            extra.append(line)
    workbook.save(path)
    return path


def signal(tag, **fields):
    row = {"tag": tag, "plc": "UC-1", "cabinet": "UC-1", "io_type": "DI",
           "rack": 1, "slot": 1, "point": 0,
           "m1_tag": "PNL-1", "m1_strip": "TS-1"}
    row.update(fields)
    return row
