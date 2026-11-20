"""Opens the real window when this computer can show one.

Skipped where Python has no tkinter or there is no screen. On the automated
Windows build it runs for real; locally a window flashes up for a moment.
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

try:
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk
    from tkinter import font as tkfont
    _probe = tk.Tk()
    _probe.destroy()
    HAVE_WINDOW = True
except Exception:  # no tkinter, or no display
    HAVE_WINDOW = False

ROWS = [signal("FT-1", m1_cable="C-1", jb1_tag="JB-1"),
        signal("FT-2", m1_cable="C-1", jb1_tag="JB-1", point=1)]


@unittest.skipUnless(HAVE_WINDOW, "no tkinter or no display on this computer")
class RealWindow(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.mkdtemp()
        self.base = os.path.join(self.folder, "Projects")
        self.source = make_workbook(os.path.join(self.folder, "index.xlsx"), ROWS)
        self.root = tk.Tk()
        self.app = gui.App(self.root, tk, ttk, filedialog, messagebox, tkfont,
                           gui.Session(base_dir=self.base))
        self.root.update()

    def tearDown(self):
        try:
            self.root.destroy()
        except Exception:
            pass
        shutil.rmtree(self.folder)

    def pump_until_done(self, timeout=60.0):
        deadline = time.time() + timeout
        while self.app.session.state != "done" and time.time() < deadline:
            self.root.update()
            time.sleep(0.02)
        self.root.update()
        self.assertEqual(self.app.session.state, "done")

    def test_run_new_index_and_close(self):
        app = self.app
        self.assertEqual(str(app.browse_button.cget("state")), "normal")
        self.assertEqual(str(app.new_button.cget("state")), "disabled")
        self.assertEqual(app.status.cget("text"), gui.READY_TEXT)

        app.load(self.source)
        self.assertEqual(str(app.browse_button.cget("state")), "disabled")
        self.pump_until_done()
        self.assertEqual(app.status.cget("text"), "COMPLETED  (IR-000)")
        self.assertEqual(app.path_var.get(), self.source)
        self.assertEqual(float(app.bar["value"]), float(len(STEPS)))
        self.assertTrue(app.elapsed_var.get().startswith("Elapsed time: "))
        shown = app.text.get("1.0", "end")
        self.assertIn("2 signals", shown)
        self.assertIn(app.session.output.folder, shown)
        self.assertEqual(str(app.new_button.cget("state")), "normal")
        for button in app.open_buttons.values():
            self.assertEqual(str(button.cget("state")), "normal")
        self.assertEqual(len(os.listdir(app.session.output.folder)), 6)

        # New Index: the window clears and asks for a file (the dialog is cancelled here)
        with mock.patch.object(filedialog, "askopenfilename", return_value="") as asked:
            app.new_index()
        asked.assert_called_once()
        self.assertEqual(app.path_var.get(), "")
        self.assertEqual(app.status.cget("text"), gui.READY_TEXT)
        self.assertEqual(app.text.get("1.0", "end").strip(), "")
        self.assertEqual(float(app.bar["value"]), 0.0)
        self.assertEqual(str(app.browse_button.cget("state")), "normal")

        # a workbook with the wrong layout shows the failure code
        bad = make_workbook(os.path.join(self.folder, "bad.xlsx"), ROWS, drop="CN")
        app.load(bad)
        self.pump_until_done()
        self.assertEqual(app.status.cget("text"),
                         "FAILED  (IR-201  Workbook layout does not match the reference layout)")

        app.close()
        with self.assertRaises(tk.TclError):
            self.root.winfo_exists()

    def test_self_test_entry_point(self):
        self.assertEqual(gui.self_test(self.source, base_dir=self.base), 0)
        self.assertEqual(gui.self_test(os.path.join(self.folder, "missing.xlsx"),
                                       base_dir=self.base), 4)


if __name__ == "__main__":
    unittest.main()
