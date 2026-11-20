import os
import shutil
import tempfile
import unittest

from helpers import make_workbook, signal
from index_reader import graph, loader
from index_reader.schedule import schedule_rows


class GraphCase(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.folder)

    def build(self, rows, **kwargs):
        path = make_workbook(os.path.join(self.folder, "index.xlsx"), rows, **kwargs)
        data = loader.load_index(path)
        return data, graph.build_graph(data)

    def runs(self, result):
        return dict(((r.cable_id, result.nodes[r.src].name, result.nodes[r.dst].name), r)
                    for r in result.runs)


class Paths(GraphCase):
    def test_skips_unpopulated_sections(self):
        # marshalling 2/3 and JB 2/3 blank: M1 -> JB1 -> device
        data, result = self.build([
            signal("FT-1", m1_cable="C-1", m1_pair="PR.1", jb1_tag="JB-1", jb1_strip="TB-1",
                   jb1_cable="C-2", jb1_pair="PR.1"),
        ])
        sig = result.signals[0]
        self.assertEqual([result.nodes[k].name for k in sig.nodes], ["PNL-1", "JB-1", "FT-1"])
        self.assertEqual([s.cable_id for s in sig.segments], ["C-1", "C-2"])
        self.assertEqual(result.new_cells, {})

    def test_all_six_sections(self):
        data, result = self.build([
            signal("FT-1", m1_cable="A", m2_tag="M2", m2_cable="B", m3_tag="M3", m3_cable="C",
                   jb1_tag="J1", jb1_cable="D", jb2_tag="J2", jb2_cable="E", jb3_tag="J3",
                   jb3_cable="F"),
        ])
        sig = result.signals[0]
        self.assertEqual([result.nodes[k].name for k in sig.nodes],
                         ["PNL-1", "M2", "M3", "J1", "J2", "J3", "FT-1"])
        self.assertEqual([s.cable_id for s in sig.segments], ["A", "B", "C", "D", "E", "F"])

    def test_default_location_is_field(self):
        data, result = self.build([signal("FT-1", m1_cable="C-1"),
                                   signal("FT-2", m1_cable="C-2", end_loc="CABINET")])
        self.assertEqual(result.nodes["FT-1"].locations, ["FIELD"])
        self.assertEqual(result.nodes["FT-2"].locations, ["CABINET"])

    def test_rows_without_tag_or_spare_are_skipped(self):
        data, result = self.build([
            {"m1_tag": "PNL-1"},                                   # plain spare point
            {"m1_tag": "PNL-1", "m1_cable": "C-9", "jb1_tag": "JB-9"},
            signal("FT-1", m1_cable="C-1", io_type="SPARE"),
            signal("FT-2", m1_cable="C-2"),
        ])
        self.assertEqual([s.tag for s in result.signals], ["FT-2"])
        self.assertEqual([(row, reason) for row, reason, _ in result.skipped],
                         [(4, "No instrument tag"), (5, "I/O type is SPARE")])


class CableIds(GraphCase):
    def test_last_run_blank_gets_tag_based_id(self):
        data, result = self.build([
            signal("FT-1", m1_cable="C-1", jb1_tag="JB-1"),
            signal("FT-2", m1_cable="C-1", jb1_tag="JB-1"),
        ])
        self.assertEqual(result.new_cells, {(3, "jb1_cable"): "newcable_FT-1",
                                            (4, "jb1_cable"): "newcable_FT-2"})

    def test_last_run_grouped_by_end_device_tag(self):
        data, result = self.build([
            signal("ZSO-1", m1_cable="C-1", jb1_tag="JB-1", end_tag="MOV-1"),
            signal("ZSC-1", m1_cable="C-1", jb1_tag="JB-1", end_tag="MOV-1"),
            signal("HSO-1", m1_cable="C-2", jb1_tag="JB-1", end_tag="MOV-1"),
        ])
        self.assertEqual(set(result.new_cells.values()), {"newcable_MOV-1"})
        run = self.runs(result)[("newcable_MOV-1", "JB-1", "MOV-1")]
        self.assertEqual(run.used_pairs, 3)
        self.assertEqual(run.proposal.text, "1-4 PR")

    def test_last_run_grouped_by_mcc_cubicle(self):
        data, result = self.build([
            signal("XS-1", mcc="MCC-1", cubicle="3A", end_tag="PUMP A"),
            signal("XS-2", mcc="MCC-1", cubicle="3A"),
            signal("XS-3", mcc="MCC-1", cubicle="4B"),
        ])
        self.assertEqual(result.new_cells, {(3, "m1_cable"): "newcable_MCC-1_3A",
                                            (4, "m1_cable"): "newcable_MCC-1_3A",
                                            (5, "m1_cable"): "newcable_MCC-1_4B"})

    def test_blank_cable_between_panels_is_numbered_and_shared(self):
        data, result = self.build([
            signal("FT-1", jb1_tag="JB-1", jb1_cable="X-1"),
            signal("FT-2", jb1_tag="JB-1", jb1_cable="X-2"),
            signal("FT-3", jb1_tag="JB-2", jb1_cable="X-3"),
        ])
        self.assertEqual(result.new_cells, {(3, "m1_cable"): "newcable_0001",
                                            (4, "m1_cable"): "newcable_0001",
                                            (5, "m1_cable"): "newcable_0002"})

    def test_new_id_does_not_collide_with_an_id_in_the_index(self):
        data, result = self.build([
            signal("FT-1", m1_cable="newcable_FT-2"),
            signal("FT-2"),
        ])
        self.assertEqual(result.new_cells, {(4, "m1_cable"): "newcable_FT-2_2"})


class Sizing(GraphCase):
    def test_existing_is_bundled_and_not_sized(self):
        data, result = self.build([
            signal("FT-%d" % n, m1_cable="(EXISTING) C-77", jb1_tag="JB-1", jb1_cable="EXISTING")
            for n in range(5)
        ])
        run = self.runs(result)[("(EXISTING) C-77", "PNL-1", "JB-1")]
        self.assertEqual(run.status, graph.STATUS_EXISTING)
        self.assertIsNone(run.proposal)
        self.assertEqual(len(run.segments), 5)
        rows = [r for r in schedule_rows(result) if r["cable_id"] == "(EXISTING) C-77"]
        self.assertEqual(rows[0]["size"], "Existing - not sized")
        self.assertEqual(result.new_cells, {})

    def test_split_above_24_pairs(self):
        data, result = self.build([
            signal("FT-%d" % n, m1_cable="C-BIG", m1_pair="PR.%d" % (n + 1), jb1_tag="JB-1",
                   jb1_cable="EXISTING") for n in range(30)
        ])
        run = self.runs(result)[("C-BIG", "PNL-1", "JB-1")]
        self.assertEqual(run.used_pairs, 30)
        self.assertEqual(run.proposal.text, "1-24 PR + 1-12 PR")
        self.assertIn("Split into 2 cables", run.notes)

    def test_triad_from_pair_column_or_rtn_terminal(self):
        data, result = self.build([
            signal("AT-1", m1_cable="C-1", m1_pair="TR.1", jb1_tag="JB-1", jb1_cable="EXISTING"),
            signal("AT-2", m1_cable="C-1", jb1_tag="JB-1", jb1_rtn="9", jb1_cable="EXISTING"),
            signal("AT-3", m1_cable="C-1", m1_rtn="12", jb1_tag="JB-1", jb1_cable="EXISTING"),
            signal("PT-4", m1_cable="C-1", jb1_tag="JB-1", jb1_cable="EXISTING"),
            signal("PT-5", m1_cable="C-1", m1_pair="PR.5", jb1_tag="JB-1", jb1_rtn="15",
                   jb1_cable="EXISTING"),
        ])
        run = self.runs(result)[("C-1", "PNL-1", "JB-1")]
        self.assertEqual((run.used_pairs, run.used_triads), (2, 3))
        self.assertEqual(run.proposal.text, "1-2 PR + 1-4 TR")
        codes = [f.code for f in result.findings]
        self.assertIn("MIXED_PAIRS_TRIADS", codes)
        self.assertIn("PAIR_WITH_RTN", codes)

    def test_triad_on_last_run_from_instrument_signal_terminal(self):
        data, result = self.build([signal("AT-1", m1_cable="EXISTING", jb1_tag="JB-1",
                                          inst_sig="S")])
        run = self.runs(result)[("newcable_AT-1", "JB-1", "AT-1")]
        self.assertEqual(run.proposal.text, "1-1 TR")


class Checks(GraphCase):
    def test_cable_id_reused_between_different_end_points(self):
        data, result = self.build([
            signal("FT-1", m1_cable="C-1", jb1_tag="JB-1", jb1_cable="EXISTING"),
            signal("FT-2", m1_cable="C-1", jb1_tag="JB-2", jb1_cable="EXISTING"),
        ])
        self.assertIn("CABLE_ID_REUSED", [f.code for f in result.findings])
        self.assertEqual(len([r for r in result.runs if r.cable_id == "C-1"]), 2)

    def test_bare_existing_may_go_anywhere(self):
        data, result = self.build([
            signal("FT-1", m1_cable="EXISTING", jb1_tag="JB-1", jb1_cable="EXISTING"),
            signal("FT-2", m1_cable="EXISTING", jb1_tag="JB-2", jb1_cable="EXISTING"),
        ])
        self.assertNotIn("CABLE_ID_REUSED", [f.code for f in result.findings])

    def test_duplicate_pair_number(self):
        data, result = self.build([
            signal("FT-1", m1_cable="C-1", m1_pair="PR.3", jb1_tag="JB-1", jb1_cable="EXISTING"),
            signal("FT-2", m1_cable="C-1", m1_pair="PR.3", jb1_tag="JB-1", jb1_cable="EXISTING"),
        ])
        self.assertIn("DUPLICATE_PAIR", [f.code for f in result.findings])

    def test_plc_and_address_checks(self):
        data, result = self.build([
            signal("FT-1", m1_cable="C-1", plc="UC-2"),
            signal("FT-2", m1_cable="C-2", rack="", slot="", point=""),
            signal("FT-3", m1_cable="C-3", point=7),
            signal("FT-4", m1_cable="C-4", point=7),
        ])
        codes = [(f.code, f.tag) for f in result.findings]
        self.assertIn(("PLC_MISMATCH", "FT-1"), codes)
        self.assertIn(("NO_IO_ADDRESS", "FT-2"), codes)
        self.assertIn(("DUPLICATE_IO_ADDRESS", "FT-4"), codes)

    def test_signal_ending_inside_a_junction_box(self):
        data, result = self.build([signal("XS-1", m1_cable="C-1", jb1_tag="JB-1",
                                          end_tag="JB-1")])
        sig = result.signals[0]
        self.assertEqual([result.nodes[k].name for k in sig.nodes], ["PNL-1", "JB-1"])
        self.assertEqual(result.new_cells, {})


if __name__ == "__main__":
    unittest.main()
