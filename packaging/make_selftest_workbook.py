"""Write a small invented Instrument Index used to test the packaged program.

Usage: python packaging/make_selftest_workbook.py OUTPUT.xlsx
"""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tests"))

from helpers import make_workbook, signal  # noqa: E402

ROWS = [
    signal("ZSO-1", m1_cable="C-1", m1_pair="PR.1", jb1_tag="JB-1", jb1_strip="TB-1",
           end_tag="MOV-1"),
    signal("ZSC-1", m1_cable="C-1", m1_pair="PR.2", jb1_tag="JB-1", jb1_strip="TB-1",
           end_tag="MOV-1", point=1),
    signal("PT-2", m1_cable="(EXISTING) C-9", jb1_tag="JB-2", jb1_cable="EXISTING", point=2),
    signal("XS-3", point=3, mcc="MCC-1", cubicle="2G"),
]

if __name__ == "__main__":
    make_workbook(sys.argv[1], ROWS)
    print("wrote", sys.argv[1])
