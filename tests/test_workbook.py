import hashlib
import os
import shutil
import tempfile
import unittest
import warnings
import zipfile

import openpyxl

from helpers import make_workbook, signal
from index_reader import config, graph, loader
from index_reader.cli import run
from index_reader.index_writer import write_updated_index
from index_reader.sample_headers import SAMPLE_HEADERS


def digest(path):
    with open(path, "rb") as handle:
        return hashlib.sha256(handle.read()).hexdigest()


ROWS = [
    signal("ZSO-1", m1_cable="C-1", m1_pair="PR.1", jb1_tag="JB-1", jb1_strip="TB-1",
           end_tag="MOV-1"),
    signal("ZSC-1", m1_cable="C-1", m1_pair="PR.2", jb1_tag="JB-1", jb1_strip="TB-1",
           end_tag="MOV-1", point=1),
    signal("PT-2", m1_cable="(EXISTING) C-9", jb1_tag="JB-2", jb1_cable="EXISTING", point=2),
    signal("XS-3", point=3, mcc="MCC-1", cubicle="2G"),
    signal("FT-4", point=4, jb1_tag="JB-1", jb1_cable="C-4"),
]


class Folder(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.folder)

    def path(self, name):
        return os.path.join(self.folder, name)


class HeaderCheck(Folder):
    def test_reference_layout_has_unique_headers_for_every_mapped_column(self):
        descriptions = [h[2] for h in SAMPLE_HEADERS if h[2]]
        for field in config.FIELD_LETTERS:
            letter, code, description = config.expected_header(field)
            self.assertTrue(description, field)
            self.assertEqual(descriptions.count(description), 1, field)

    def test_matching_layout(self):
        data = loader.load_index(make_workbook(self.path("a.xlsx"), ROWS))
        self.assertEqual(data.report.changed, [])
        self.assertEqual(data.report.first_data_row, 3)
        self.assertEqual(data.columns["m1_cable"], "CN")
        self.assertEqual(len(data.rows), len(ROWS))

    def test_inserted_column_is_followed(self):
        plain = loader.load_index(make_workbook(self.path("a.xlsx"), ROWS))
        shifted = loader.load_index(make_workbook(self.path("b.xlsx"), ROWS, insert_before="CN"))
        self.assertEqual(shifted.columns["m1_cable"], "CO")
        self.assertEqual(shifted.columns["jb1_cable"], "DY")
        self.assertEqual(shifted.columns["tag"], "H")
        moved = [f.field for f in shifted.report.fields if f.status == "MOVED"]
        self.assertIn("m1_cable", moved)
        self.assertNotIn("tag", moved)
        self.assertEqual(shifted.report.added, ["CN A NEW COLUMN"])
        first = graph.build_graph(plain)
        second = graph.build_graph(shifted)
        self.assertEqual([(r.cable_id, r.src, r.dst, len(r.segments)) for r in first.runs],
                         [(r.cable_id, r.src, r.dst, len(r.segments)) for r in second.runs])

    def test_missing_required_column_stops(self):
        path = make_workbook(self.path("a.xlsx"), ROWS, drop="CN")
        with self.assertRaises(loader.HeaderError) as caught:
            loader.load_index(path)
        self.assertIn("MARSH 1 CABLE NUMBER (HOMERUN)", str(caught.exception))

    def test_missing_optional_column_only_reports(self):
        data = loader.load_index(make_workbook(self.path("a.xlsx"), ROWS, drop="DA"))
        self.assertIsNone(data.columns["m2_pair"])
        self.assertEqual([f.field for f in data.report.fields if f.status == "MISSING"],
                         ["m2_pair"])

    def test_edited_description_is_matched_on_the_short_code(self):
        data = loader.load_index(make_workbook(self.path("a.xlsx"), ROWS,
                                               rename={"DX": "JB 1 CABLE NO."}))
        self.assertEqual(data.columns["jb1_cable"], "DX")
        self.assertEqual([f.field for f in data.report.fields if f.status == "RENAMED"],
                         ["jb1_cable"])


class UpdatedIndex(Folder):
    def test_only_the_proposed_cells_change(self):
        source = make_workbook(self.path("a.xlsx"), ROWS)
        target = self.path("b.xlsx")
        cells = {(3, "DX"): "newcable_MOV-1", (4, "DX"): "newcable_MOV-1",
                 (6, "CN"): "newcable_<&>", (40, "CN"): "new row", (3, "ZZ"): "far right"}
        self.assertEqual(write_updated_index(source, target, "LOOP", cells), 5)

        with zipfile.ZipFile(source) as a, zipfile.ZipFile(target) as b:
            self.assertEqual(a.namelist(), b.namelist())
            changed = [n for n in a.namelist() if a.read(n) != b.read(n)]
        self.assertEqual(sorted(changed), ["xl/styles.xml", "xl/worksheets/sheet1.xml"])

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            before = openpyxl.load_workbook(source)["LOOP"]
            after = openpyxl.load_workbook(target)["LOOP"]
        different = {}
        for row in after.iter_rows():
            for cell in row:
                if cell.value != before[cell.coordinate].value:
                    different[cell.coordinate] = cell.value
        self.assertEqual(different, {"DX3": "newcable_MOV-1", "DX4": "newcable_MOV-1",
                                     "CN6": "newcable_<&>", "CN40": "new row",
                                     "ZZ3": "far right"})
        for coordinate in different:
            self.assertEqual(after[coordinate].fill.fgColor.rgb, "FFFFFF00", coordinate)
            self.assertEqual(after[coordinate].font.color.rgb, "FFFF0000", coordinate)
        self.assertEqual(after["H3"].value, "ZSO-1")
        self.assertNotEqual(after["H3"].fill.fgColor.rgb, "FFFFFF00")

    def test_no_cells_means_identical_parts(self):
        source = make_workbook(self.path("a.xlsx"), ROWS)
        target = self.path("b.xlsx")
        write_updated_index(source, target, "LOOP", {})
        with zipfile.ZipFile(source) as a, zipfile.ZipFile(target) as b:
            self.assertTrue(all(a.read(n) == b.read(n) for n in a.namelist()))


class EndToEnd(Folder):
    def test_outputs_exist_and_are_reproducible(self):
        source = make_workbook(self.path("index.xlsx"), ROWS)
        first = run(source, self.path("out1"))
        second = run(source, self.path("out2"))
        self.assertEqual(sorted(first.files), ["diagram_html", "diagram_svg", "index", "schedule"])
        for key in first.files:
            self.assertTrue(os.path.getsize(first.files[key]) > 0, key)
            self.assertEqual(digest(first.files[key]), digest(second.files[key]), key)

    def test_updated_index_carries_the_proposed_ids(self):
        source = make_workbook(self.path("index.xlsx"), ROWS)
        out = run(source, self.path("out"))
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            sheet = openpyxl.load_workbook(out.files["index"])["LOOP"]
        self.assertEqual(sheet["DX3"].value, "newcable_MOV-1")
        self.assertEqual(sheet["DX4"].value, "newcable_MOV-1")
        self.assertEqual(sheet["CN6"].value, "newcable_MCC-1_2G")
        self.assertEqual(sheet["CN7"].value, "newcable_0001")
        self.assertEqual(sheet["DX5"].value, "EXISTING")
        # feeding the updated index back in proposes nothing new
        again = run(out.files["index"], self.path("out_again"))
        self.assertEqual(again.result.new_cells, {})
        self.assertEqual(len(again.result.runs), len(out.result.runs))

    def test_schedule_workbook(self):
        source = make_workbook(self.path("index.xlsx"), ROWS)
        out = run(source, self.path("out"))
        book = openpyxl.load_workbook(out.files["schedule"])
        self.assertEqual(book.sheetnames, ["Cable Schedule", "Signal Routing", "Panels & Devices",
                                           "Findings", "Skipped Rows", "Run Info"])
        rows = list(book["Cable Schedule"].iter_rows(min_row=2, values_only=True))
        by_id = dict((r[0], r) for r in rows)
        self.assertEqual(by_id["C-1"][1:5], ("FROM INDEX", "1-2 PR", 2, 0))
        self.assertEqual(by_id["newcable_MOV-1"][1:5], ("NEW ID", "1-2 PR", 2, 0))
        self.assertEqual(by_id["(EXISTING) C-9"][1:3], ("EXISTING", "Existing - not sized"))
        self.assertEqual(by_id["newcable_MOV-1"][7], "JB-1")
        self.assertEqual(by_id["newcable_MOV-1"][9], "MOV-1")


if __name__ == "__main__":
    unittest.main()
