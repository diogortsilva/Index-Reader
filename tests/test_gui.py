"""Tests for the window logic.

The background Session is tested for real. The window class is driven with a
stand-in for tkinter, which checks the wiring between buttons, session and
labels. It does not replace opening the real window on a real screen.
"""

import os
import shutil
import tempfile
import time
import unittest
from unittest import mock

from helpers import make_workbook, signal
from index_reader import gui
from index_reader.project import STEPS

ROWS = [signal("FT-1", m1_cable="C-1", jb1_tag="JB-1"),
        signal("FT-2", m1_cable="C-1", jb1_tag="JB-1", point=1)]


def wait_until_done(session, timeout=20.0):
    session.wait(timeout)
    deadline = time.time() + timeout
    events = []
    while session.running and time.time() < deadline:
        events.extend(session.poll())
        time.sleep(0.01)
    return events


class Folder(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.mkdtemp()
        self.base = os.path.join(self.folder, "Projects")
        self.source = make_workbook(os.path.join(self.folder, "index.xlsx"), ROWS)

    def tearDown(self):
        shutil.rmtree(self.folder)


class SessionTest(Folder):
    def test_run_reports_progress_then_done(self):
        session = gui.Session(base_dir=self.base)
        self.assertEqual(session.state, "idle")
        session.start(self.source)
        self.assertTrue(session.running)
        events = wait_until_done(session)
        self.assertEqual(session.state, "done")
        kinds = [e[0] for e in events]
        self.assertEqual(kinds.count("done"), 1)
        self.assertEqual(kinds[-1], "done")
        self.assertEqual([e[1] for e in events if e[0] == "progress"],
                         list(range(len(STEPS) + 1)))
        self.assertTrue(session.output.ok)
        self.assertEqual(session.elapsed(), session.output.elapsed)

    def test_can_run_again_after_reset(self):
        session = gui.Session(base_dir=self.base)
        session.start(self.source)
        wait_until_done(session)
        session.reset()
        self.assertEqual(session.state, "idle")
        self.assertIsNone(session.output)
        session.start(os.path.join(self.folder, "missing.xlsx"))
        wait_until_done(session)
        self.assertEqual(session.output.code, "IR-101")
        self.assertEqual(len(os.listdir(self.base)), 1)

    def test_cannot_start_two_runs_at_once(self):
        release = []

        def slow(path, base_dir=None, progress=None):
            while not release:
                time.sleep(0.01)
            return mock.Mock(ok=True, elapsed=0.1)

        session = gui.Session(runner=slow)
        session.start("a.xlsx")
        with self.assertRaises(RuntimeError):
            session.start("b.xlsx")
        with self.assertRaises(RuntimeError):
            session.reset()
        self.assertGreaterEqual(session.elapsed(), 0)
        release.append(True)
        wait_until_done(session)
        self.assertEqual(session.state, "done")


class WindowWiring(Folder):
    """Drive App with stand-in widgets."""

    def make_app(self):
        self.root = mock.MagicMock()
        self.tk, self.ttk = mock.MagicMock(), mock.MagicMock()
        # every widget and variable created must be its own object
        for module in (self.tk, self.ttk):
            for name in ("Frame", "Label", "Button", "Entry", "Progressbar", "Text", "Scrollbar",
                         "Separator", "StringVar"):
                getattr(module, name).side_effect = lambda *a, **k: mock.MagicMock()
        self.dialog, self.box, self.font = mock.MagicMock(), mock.MagicMock(), mock.MagicMock()
        session = gui.Session(base_dir=self.base)
        return gui.App(self.root, self.tk, self.ttk, self.dialog, self.box, self.font, session)

    @staticmethod
    def state_of(button):
        return button.configure.call_args[1]["state"]

    @staticmethod
    def text_of(app):
        inserted = [c[0][1] for c in app.text.insert.call_args_list]
        return inserted[-1] if inserted else ""

    def finish(self, app):
        app.session.wait(20)
        app._tick()
        self.assertEqual(app.session.state, "done")

    def test_starting_state(self):
        app = self.make_app()
        self.assertEqual(self.state_of(app.browse_button), "normal")
        self.assertEqual(self.state_of(app.new_button), "disabled")
        for button in app.open_buttons.values():
            self.assertEqual(self.state_of(button), "disabled")
        self.root.protocol.assert_called_once_with("WM_DELETE_WINDOW", app.close)

    def test_cancelled_browse_does_nothing(self):
        app = self.make_app()
        self.dialog.askopenfilename.return_value = ""
        app.browse()
        self.assertEqual(app.session.state, "idle")

    def test_successful_run(self):
        app = self.make_app()
        self.dialog.askopenfilename.return_value = self.source
        app.browse()
        app.path_var.set.assert_called_with(self.source)
        self.assertEqual(self.state_of(app.browse_button), "disabled")
        self.assertEqual(self.state_of(app.new_button), "disabled")
        self.finish(app)
        status = app.status.configure.call_args[1]
        self.assertEqual(status["text"], "COMPLETED  (IR-000)")
        self.assertEqual(status["fg"], gui.GREEN)
        app.bar.__setitem__.assert_called_with("value", len(STEPS))
        self.assertTrue(app.elapsed_var.set.call_args[0][0].startswith("Elapsed time: "))
        self.assertIn("2 signals", self.text_of(app))
        self.assertIn(app.session.output.folder, self.text_of(app))
        self.assertEqual(self.state_of(app.new_button), "normal")
        for button in app.open_buttons.values():
            self.assertEqual(self.state_of(button), "normal")
        # the window stops polling once the run is over
        before = self.root.after.call_count
        app._tick()
        self.assertEqual(self.root.after.call_count, before)

    def test_failed_run_shows_the_code(self):
        app = self.make_app()
        bad = make_workbook(os.path.join(self.folder, "bad.xlsx"), ROWS, drop="CN")
        app.load(bad)
        self.finish(app)
        status = app.status.configure.call_args[1]
        self.assertEqual(status["text"],
                         "FAILED  (IR-201  Workbook layout does not match the reference layout)")
        self.assertEqual(status["fg"], gui.RED)
        self.assertIn("MARSH 1 CABLE NUMBER (HOMERUN)", self.text_of(app))
        self.assertEqual(self.state_of(app.new_button), "normal")
        self.assertEqual(self.state_of(app.open_buttons["folder"]), "normal")
        for key in ("diagram_html", "schedule", "index"):
            self.assertEqual(self.state_of(app.open_buttons[key]), "disabled")

    def test_new_index_resets_and_asks_for_the_next_file(self):
        app = self.make_app()
        app.load(self.source)
        self.finish(app)
        first_folder = app.session.output.folder
        second = make_workbook(os.path.join(self.folder, "second.xlsx"), ROWS)
        self.dialog.askopenfilename.return_value = second
        app.new_index()
        app.path_var.set.assert_any_call("")
        self.finish(app)
        self.assertNotEqual(app.session.output.folder, first_folder)
        self.assertTrue(app.session.output.folder.endswith("_second"))
        self.assertEqual(len(os.listdir(self.base)), 2)

    def test_open_buttons_open_the_right_things(self):
        app = self.make_app()
        app.load(self.source)
        self.finish(app)
        output = app.session.output
        with mock.patch.object(gui, "open_path") as opened:
            app.open_output("folder")
            app.open_output("diagram_html")
            app.open_output("schedule")
            app.open_output("index")
        self.assertEqual([c[0][0] for c in opened.call_args_list],
                         [output.folder, output.files["diagram_html"],
                          output.files["schedule"], output.files["index"]])

    def test_close_exits_and_asks_first_while_running(self):
        app = self.make_app()
        app.close()
        self.root.destroy.assert_called_once_with()
        self.box.askyesno.assert_not_called()

        app = self.make_app()
        app.session.state = "running"
        self.box.askyesno.return_value = False
        app.close()
        self.root.destroy.assert_not_called()
        self.box.askyesno.return_value = True
        app.close()
        self.root.destroy.assert_called_once_with()

    def test_missing_tkinter_is_explained(self):
        import builtins
        real_import = builtins.__import__

        def no_tk(name, *args, **kwargs):
            if name == "tkinter" or name.startswith("tkinter."):
                raise ImportError("No module named 'tkinter'")
            return real_import(name, *args, **kwargs)

        with mock.patch.object(builtins, "__import__", side_effect=no_tk), \
                mock.patch("sys.stderr") as stderr:
            self.assertEqual(gui.main(), 3)
        self.assertIn("tkinter", "".join(c[0][0] for c in stderr.write.call_args_list))


if __name__ == "__main__":
    unittest.main()
