"""Result codes reported at the end of every run."""

from __future__ import annotations

import zipfile

SUCCESS = "IR-000"
FILE_NOT_FOUND = "IR-101"
NOT_A_WORKBOOK = "IR-102"
FILE_NOT_READABLE = "IR-103"
LAYOUT_MISMATCH = "IR-201"
NO_INSTRUMENTS = "IR-202"
CANNOT_WRITE = "IR-301"
UNEXPECTED = "IR-900"

TITLES = {
    SUCCESS: "Completed",
    FILE_NOT_FOUND: "File not found",
    NOT_A_WORKBOOK: "Not an Excel .xlsx workbook",
    FILE_NOT_READABLE: "File cannot be read",
    LAYOUT_MISMATCH: "Workbook layout does not match the reference layout",
    NO_INSTRUMENTS: "No instrument rows found on the main tab",
    CANNOT_WRITE: "Cannot write to the project folder",
    UNEXPECTED: "Unexpected error",
}


class AppError(Exception):
    """An error with a result code that is shown to the user."""

    def __init__(self, code, message):
        Exception.__init__(self, message)
        self.code = code
        self.message = message


def classify(error, writing=False):
    """Exception -> (code, one-line message)."""
    from .index_writer import IndexWriteError
    from .loader import HeaderError

    if isinstance(error, AppError):
        return error.code, error.message
    if isinstance(error, HeaderError):
        return LAYOUT_MISMATCH, str(error)
    if isinstance(error, IndexWriteError):
        return NOT_A_WORKBOOK, str(error)
    if isinstance(error, zipfile.BadZipFile):
        return NOT_A_WORKBOOK, "The file is not a valid .xlsx workbook (%s)." % error
    if isinstance(error, FileNotFoundError) and not writing:
        return FILE_NOT_FOUND, "File not found: %s" % (error.filename or error)
    if isinstance(error, PermissionError):
        code = CANNOT_WRITE if writing else FILE_NOT_READABLE
        return code, "Permission denied: %s. Close the file if it is open in Excel and " \
                     "try again." % (error.filename or error)
    if isinstance(error, OSError):
        code = CANNOT_WRITE if writing else FILE_NOT_READABLE
        return code, "%s: %s" % (type(error).__name__, error)
    return UNEXPECTED, "%s: %s" % (type(error).__name__, error)
