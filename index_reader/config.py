"""All tunable rules in one place: column map, cable sizes, naming."""

from __future__ import annotations

from collections import namedtuple

from .sample_headers import SAMPLE_HEADERS

VERSION = "0.1.0"

# --------------------------------------------------------------------------
# Cable sizing rules
# --------------------------------------------------------------------------
PAIR_SIZES = (1, 2, 4, 8, 12, 16, 24)   # multipair, individually shielded
TRIAD_SIZES = (1, 4, 6, 12)             # multitriad, individually shielded
SPARE_PERCENT = 15                      # minimum spare capacity ...
SPARE_MIN_USED = 3                      # ... for cables using 3 or more pairs/triads

# --------------------------------------------------------------------------
# Naming rules
# --------------------------------------------------------------------------
EXISTING_KEYWORD = "EXISTING"           # cable IDs containing this are never sized
NEW_CABLE_PREFIX = "newcable_"
NEW_CABLE_DIGITS = 4                    # newcable_0001
DEFAULT_END_LOCATION = "FIELD"
SHEET_NAME = "LOOP"

# Cell text treated as "blank"
BLANK_TOKENS = ("", "-", "N/A", "NA", "N.A.")
# I/O types that mark a row as not in use
SKIP_IO_TYPES = ("SPARE", "DELETED")

# --------------------------------------------------------------------------
# Column map. Letters are the positions in the reference workbook; at load
# time every column is re-located by its header text (see loader.py), so the
# letters are only a starting point.
# --------------------------------------------------------------------------
FIELD_LETTERS = {
    "module": "D",
    "io_type": "E",
    "plc": "F",
    "tag": "H",
    "desc1": "K",
    "desc2": "L",
    "desc3": "M",
    "desc4": "N",
    "cabinet": "Y",
    "rack": "Z",
    "slot": "AA",
    "point": "AB",
    # Marshalling 1 (same panel as the PLC rack)
    "m1_tag": "CD", "m1_strip": "CE", "m1_rtn": "CK", "m1_cable": "CN", "m1_pair": "CO",
    # Marshalling 2
    "m2_tag": "CQ", "m2_strip": "CR", "m2_rtn": "CW", "m2_cable": "CZ", "m2_pair": "DA",
    # Marshalling 3
    "m3_tag": "DC", "m3_strip": "DD", "m3_rtn": "DI", "m3_cable": "DL", "m3_pair": "DM",
    # Field junction box 1
    "jb1_tag": "DO", "jb1_strip": "DP", "jb1_rtn": "DU", "jb1_cable": "DX", "jb1_pair": "DY",
    # Field junction box 2
    "jb2_tag": "EA", "jb2_strip": "EB", "jb2_rtn": "EG", "jb2_cable": "EJ", "jb2_pair": "EK",
    # Field junction box 3
    "jb3_tag": "EM", "jb3_strip": "EN", "jb3_rtn": "ES", "jb3_cable": "EV", "jb3_pair": "EW",
    # End point
    "mcc": "EY",
    "cubicle": "EZ",
    "end_loc": "FC",
    "end_type": "FD",
    "end_tag": "FE",
    "end_strip": "FF",
    "inst_sig": "FI",
}

# Without these the tool cannot build the graph, so loading stops.
REQUIRED_FIELDS = (
    "tag", "plc", "cabinet",
    "m1_tag", "m1_cable",
    "jb1_tag", "jb1_cable",
    "mcc", "cubicle", "end_loc", "end_tag",
)

Section = namedtuple("Section", "key label kind tag strip rtn cable pair")

# Order matters: this is the physical order from the PLC out to the field.
SECTIONS = (
    Section("M1", "Marshalling 1", "PLC PANEL", "m1_tag", "m1_strip", "m1_rtn", "m1_cable", "m1_pair"),
    Section("M2", "Marshalling 2", "MARSHALLING", "m2_tag", "m2_strip", "m2_rtn", "m2_cable", "m2_pair"),
    Section("M3", "Marshalling 3", "MARSHALLING", "m3_tag", "m3_strip", "m3_rtn", "m3_cable", "m3_pair"),
    Section("JB1", "Junction Box 1", "JUNCTION BOX", "jb1_tag", "jb1_strip", "jb1_rtn", "jb1_cable", "jb1_pair"),
    Section("JB2", "Junction Box 2", "JUNCTION BOX", "jb2_tag", "jb2_strip", "jb2_rtn", "jb2_cable", "jb2_pair"),
    Section("JB3", "Junction Box 3", "JUNCTION BOX", "jb3_tag", "jb3_strip", "jb3_rtn", "jb3_cable", "jb3_pair"),
)

_BY_LETTER = dict((h[0], h) for h in SAMPLE_HEADERS)


def expected_header(field):
    """Return (letter, row-1 code, row-2 description) remembered from the sample."""
    return _BY_LETTER[FIELD_LETTERS[field]]


def rules_summary():
    """Human-readable list of the active rules (written into the outputs)."""
    return [
        ("Tool version", VERSION),
        ("Pair cable sizes", ", ".join(str(s) for s in PAIR_SIZES)),
        ("Triad cable sizes", ", ".join(str(s) for s in TRIAD_SIZES)),
        ("Spare rule", "%d%% minimum spare when %d or more pairs/triads are used"
         % (SPARE_PERCENT, SPARE_MIN_USED)),
        ("Largest single cable", "%d pairs / %d triads; larger needs are split"
         % (max(PAIR_SIZES), max(TRIAD_SIZES))),
        ("Existing cables", 'Cable IDs containing "%s" are grouped but never sized'
         % EXISTING_KEYWORD),
        ("Pair or triad", 'Pair-number column next to the cable ID ("PR."/"TR."); '
                          "if blank, a populated RTN terminal at either end means triad"),
        ("New IDs between panels", "%s%s, one per source/destination run"
         % (NEW_CABLE_PREFIX, "0" * (NEW_CABLE_DIGITS - 1) + "1")),
        ("New IDs to end devices", "%s<instrument tag>, or %s<end device> when signals "
                                   "share an MCC cubicle or end-device tag"
         % (NEW_CABLE_PREFIX, NEW_CABLE_PREFIX)),
        ("Default end location", DEFAULT_END_LOCATION),
    ]
