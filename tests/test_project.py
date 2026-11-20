import contextlib
import datetime
import hashlib
import io
import os
import shutil
import tempfile
import unittest

from helpers import make_workbook, signal
from index_reader import errors, project
from index_reader.cli import main as cli_main

NOW = datetime.datetime(2026, 11, 20, 14, 16, 5)

ROWS = [
    signal("ZSO-1", m1_cable="C-1", m1_pair="PR.1", jb1_tag="JB-1", end_tag="MOV-1"),
    signal("ZSC-1", m1_cable="C-1", m1_pair="PR.2", jb1_tag="JB-1", end_tag="MOV-1", point=1),
    signal("PT-2", m1_cable="(EXISTING) C-9", jb1_tag="JB-2", jb1_cable="EXISTING", point=2),
]


def digest(path):
    with open(path, "rb") as handle:
        return hashlib.sha256(handle.read()).hexdigest()


class ProjectCase(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.mkdtemp()
        self.base = os.path.join(self.folder, "Projects")
        self.events = []

    def tearDown(self):
        shutil.rmtree(self.folder)

    def path(self, name):
        return os.path.join(self.folder, name)

    def progress(self, number, total, text):
        self.events.append((number, total, text))

    def run_on(self, path, now=NOW):
        return project.run_project(path, base_dir=self.base, progress=self.progress, now=now)


class Success(ProjectCase):
    def test_folder_name_and_contents(self):
        source = make_workbook(self.path("My Index Rev.3.xlsx"), ROWS)
        out = self.run_on(source)
        self.assertTrue(out.ok)
        self.assertEqual(out.code, "IR-000")
        self.assertEqual(out.folder,
                         os.path.join(self.base, "2026-11-20_14-16-05_My Index Rev.3"))
        self.assertEqual(sorted(os.listdir(out.folder)),
                         ["My Index Rev.3.xlsx",
                          "My Index Rev.3_block_diagram.html",
                          "My Index Rev.3_block_diagram.svg",
                          "My Index Rev.3_cable_schedule.xlsx",
                          "My Index Rev.3_updated.xlsx",
                          "run_log.txt"])

    def test_input_copy_is_identical_and_original_untouched(self):
        source = make_workbook(self.path("index.xlsx"), ROWS)
        before = digest(source)
        out = self.run_on(source)
        self.assertEqual(digest(source), before)
        self.assertEqual(digest(out.files["input_copy"]), before)

    def test_progress_runs_through_every_step_in_order(self):
        source = make_workbook(self.path("index.xlsx"), ROWS)
        self.run_on(source)
        total = len(project.STEPS)
        self.assertEqual([e[0] for e in self.events], list(range(total + 1)))
        self.assertTrue(all(e[1] == total for e in self.events))
        self.assertEqual([e[2] for e in self.events[:-1]], list(project.STEPS))
        self.assertEqual(self.events[-1][2], "Completed")

    def test_elapsed_time_and_summary(self):
        source = make_workbook(self.path("index.xlsx"), ROWS)
        out = self.run_on(source)
        self.assertGreater(out.elapsed, 0)
        lines = out.summary_lines()
        self.assertEqual(lines[0], "COMPLETED  (IR-000)")
        self.assertTrue(lines[1].startswith("Elapsed time: "))
        self.assertIn("3 signals, 1 PLC panel(s), 0 other marshalling panel(s), "
                      "2 junction box(es), 2 end points", lines)
        with open(out.files["log"], encoding="utf-8") as handle:
            log = handle.read()
        self.assertIn("Result code: IR-000  Completed", log)
        self.assertIn("Started: 2026-11-20 14:16:05", log)
        self.assertIn("Input SHA-256: %s" % digest(source), log)

    def test_same_second_gets_a_separate_folder(self):
        source = make_workbook(self.path("index.xlsx"), ROWS)
        first = self.run_on(source)
        second = self.run_on(source)
        self.assertEqual(os.path.basename(first.folder), "2026-11-20_14-16-05_index")
        self.assertEqual(os.path.basename(second.folder), "2026-11-20_14-16-05_index_2")

    def test_outputs_do_not_depend_on_the_time_of_the_run(self):
        source = make_workbook(self.path("index.xlsx"), ROWS)
        first = self.run_on(source)
        second = self.run_on(source, now=NOW + datetime.timedelta(days=3))
        for key in ("diagram_svg", "diagram_html", "schedule", "index"):
            self.assertEqual(digest(first.files[key]), digest(second.files[key]), key)

    def test_folder_name_is_safe_on_windows(self):
        self.assertEqual(project.safe_name('A:B*C?"D<E>F|G. '), "A_B_C__D_E_F_G")
        self.assertEqual(project.safe_name("..."), "index")


class Failure(ProjectCase):
    def test_file_not_found(self):
        out = self.run_on(self.path("missing.xlsx"))
        self.assertEqual(out.code, errors.FILE_NOT_FOUND)
        self.assertIsNone(out.folder)
        self.assertFalse(os.path.exists(self.base))
        self.assertEqual(out.summary_lines()[0], "FAILED  (IR-101  File not found)")

    def test_wrong_file_type(self):
        text = self.path("notes.txt")
        with open(text, "w") as handle:
            handle.write("hello")
        self.assertEqual(self.run_on(text).code, errors.NOT_A_WORKBOOK)
        old = self.path("old.xls")
        shutil.copyfile(text, old)
        out = self.run_on(old)
        self.assertEqual(out.code, errors.NOT_A_WORKBOOK)
        self.assertIn("saved as .xlsx", out.message)

    def test_not_really_a_workbook(self):
        fake = self.path("fake.xlsx")
        with open(fake, "w") as handle:
            handle.write("this is not a zip archive")
        out = self.run_on(fake)
        self.assertEqual(out.code, errors.NOT_A_WORKBOOK)
        self.assertFalse(os.path.exists(self.base))

    def test_excel_lock_file(self):
        source = make_workbook(self.path("~$index.xlsx"), ROWS)
        self.assertEqual(self.run_on(source).code, errors.NOT_A_WORKBOOK)

    def test_layout_mismatch_keeps_the_input_copy_and_a_log(self):
        source = make_workbook(self.path("index.xlsx"), ROWS, drop="CN")
        out = self.run_on(source)
        self.assertEqual(out.code, errors.LAYOUT_MISMATCH)
        self.assertEqual(sorted(os.listdir(out.folder)), ["index.xlsx", "run_log.txt"])
        text = "\n".join(out.summary_lines())
        self.assertIn("FAILED  (IR-201  Workbook layout does not match the reference layout)",
                      text)
        self.assertIn("MARSH 1 CABLE NUMBER (HOMERUN)", text)
        self.assertEqual(self.events[-1][2], "Stopped")

    def test_workbook_without_instruments(self):
        source = make_workbook(self.path("index.xlsx"), [])
        self.assertEqual(self.run_on(source).code, errors.NO_INSTRUMENTS)

    def test_projects_folder_cannot_be_created(self):
        source = make_workbook(self.path("index.xlsx"), ROWS)
        blocker = self.path("blocked")
        with open(blocker, "w") as handle:
            handle.write("a file where the Projects folder should be")
        out = project.run_project(source, base_dir=os.path.join(blocker, "Projects"), now=NOW)
        self.assertEqual(out.code, errors.CANNOT_WRITE)

    def test_unexpected_error_is_reported_with_details(self):
        source = make_workbook(self.path("index.xlsx"), ROWS)
        original = project.build_graph
        project.build_graph = lambda data: 1 / 0
        try:
            out = self.run_on(source)
        finally:
            project.build_graph = original
        self.assertEqual(out.code, errors.UNEXPECTED)
        self.assertIn("ZeroDivisionError", out.message)
        with open(out.files["log"], encoding="utf-8") as handle:
            self.assertIn("Traceback", handle.read())


class CommandLine(ProjectCase):
    def test_explicit_output_folder(self):
        source = make_workbook(self.path("index.xlsx"), ROWS)
        target = self.path("out")
        with contextlib.redirect_stdout(io.StringIO()) as printed:
            self.assertEqual(cli_main([source, "-o", target]), 0)
        self.assertIn("3 signals", printed.getvalue())
        self.assertEqual(sorted(os.listdir(target)),
                         ["index_block_diagram.html", "index_block_diagram.svg",
                          "index_cable_schedule.xlsx", "index_updated.xlsx"])

    def test_default_goes_to_the_projects_folder(self):
        source = make_workbook(self.path("index.xlsx"), ROWS)
        original = project.projects_dir
        project.projects_dir = lambda: self.base
        try:
            with contextlib.redirect_stdout(io.StringIO()) as printed:
                self.assertEqual(cli_main([source]), 0)
                self.assertEqual(cli_main([self.path("missing.xlsx")]), 1)
        finally:
            project.projects_dir = original
        self.assertIn("COMPLETED  (IR-000)", printed.getvalue())
        self.assertIn("FAILED  (IR-101  File not found)", printed.getvalue())
        self.assertEqual(len(os.listdir(self.base)), 1)


if __name__ == "__main__":
    unittest.main()
