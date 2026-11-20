"""Desktop window: browse to an index, watch it run, open the results.

The window uses tkinter, which ships with Python, so there is nothing extra to
install. The work itself runs on a background thread (Session) so the window
stays responsive and the progress bar and clock keep moving.
"""

from __future__ import annotations

import os
import subprocess
import sys
import threading
import time

try:
    import queue
except ImportError:  # pragma: no cover
    import Queue as queue

from . import config
from .project import STEPS, projects_dir, run_project

GREEN = "#1a7f37"
RED = "#cf222e"
GREY = "#57606a"

READY_TEXT = "Ready. Browse to an Instrument Index workbook to begin."


class Session(object):
    """Runs one index at a time on a background thread. No window code here."""

    def __init__(self, base_dir=None, runner=run_project):
        self.base_dir = base_dir
        self.runner = runner
        self.state = "idle"          # idle | running | done
        self.output = None
        self._events = queue.Queue()
        self._thread = None
        self._started = 0.0

    @property
    def running(self):
        return self.state == "running"

    def start(self, path):
        if self.running:
            raise RuntimeError("a run is already in progress")
        self.state = "running"
        self.output = None
        self._started = time.perf_counter()
        self._thread = threading.Thread(target=self._work, args=(path,))
        self._thread.daemon = True
        self._thread.start()

    def _work(self, path):
        def progress(number, total, text):
            self._events.put(("progress", number, total, text))
        output = self.runner(path, base_dir=self.base_dir, progress=progress)
        self._events.put(("done", output))

    def poll(self):
        """Events since the last call: ('progress', n, total, text) or ('done', RunOutput)."""
        events = []
        while True:
            try:
                event = self._events.get_nowait()
            except queue.Empty:
                break
            if event[0] == "done":
                self.output = event[1]
                self.state = "done"
            events.append(event)
        return events

    def elapsed(self):
        if self.state == "running":
            return time.perf_counter() - self._started
        if self.output is not None:
            return self.output.elapsed
        return 0.0

    def wait(self, timeout=None):
        if self._thread is not None:
            self._thread.join(timeout)

    def reset(self):
        if self.running:
            raise RuntimeError("a run is in progress")
        self.state = "idle"
        self.output = None


def open_path(path):
    """Open a file or folder with the operating system's default application."""
    if sys.platform.startswith("win"):
        os.startfile(path)  # noqa: only exists on Windows
    elif sys.platform == "darwin":
        subprocess.call(["open", path])
    else:
        subprocess.call(["xdg-open", path])


class App(object):
    """The window. The tkinter modules are passed in, which keeps this testable."""

    def __init__(self, root, tk, ttk, filedialog, messagebox, tkfont, session=None):
        self.root = root
        self.tk = tk
        self.filedialog = filedialog
        self.messagebox = messagebox
        self.session = session or Session()

        root.title("Index-Reader %s" % config.VERSION)
        root.minsize(780, 560)
        root.protocol("WM_DELETE_WINDOW", self.close)
        root.columnconfigure(0, weight=1)
        root.rowconfigure(0, weight=1)

        self.title_font = tkfont.nametofont("TkDefaultFont").copy()
        self.title_font.configure(size=18, weight="bold")
        self.status_font = tkfont.nametofont("TkDefaultFont").copy()
        self.status_font.configure(size=14, weight="bold")

        frame = ttk.Frame(root, padding=16)
        frame.grid(row=0, column=0, sticky="nsew")
        frame.columnconfigure(1, weight=1)
        frame.rowconfigure(6, weight=1)

        ttk.Label(frame, text="Index-Reader", font=self.title_font).grid(
            row=0, column=0, columnspan=3, sticky="w")
        ttk.Label(frame, text="Instrument Index cable builder. Runs on this computer only; "
                              "nothing is sent anywhere.").grid(
            row=1, column=0, columnspan=3, sticky="w", pady=(0, 12))

        ttk.Label(frame, text="Instrument Index:").grid(row=2, column=0, sticky="w")
        self.path_var = tk.StringVar()
        self.path_entry = ttk.Entry(frame, textvariable=self.path_var, state="readonly")
        self.path_entry.grid(row=2, column=1, sticky="ew", padx=8)
        self.browse_button = ttk.Button(frame, text="Browse and load...", command=self.browse)
        self.browse_button.grid(row=2, column=2, sticky="e")

        self.bar = ttk.Progressbar(frame, mode="determinate", maximum=len(STEPS))
        self.bar.grid(row=3, column=0, columnspan=3, sticky="ew", pady=(14, 4))

        self.step_var = tk.StringVar()
        ttk.Label(frame, textvariable=self.step_var).grid(row=4, column=0, columnspan=2,
                                                          sticky="w")
        self.elapsed_var = tk.StringVar()
        ttk.Label(frame, textvariable=self.elapsed_var).grid(row=4, column=2, sticky="e")

        self.status = tk.Label(frame, text=READY_TEXT, font=self.status_font, anchor="w",
                               justify="left")
        self.status.grid(row=5, column=0, columnspan=3, sticky="ew", pady=(12, 6))

        text_frame = ttk.Frame(frame)
        text_frame.grid(row=6, column=0, columnspan=3, sticky="nsew")
        text_frame.columnconfigure(0, weight=1)
        text_frame.rowconfigure(0, weight=1)
        self.text = tk.Text(text_frame, height=14, wrap="word", state="disabled",
                            borderwidth=1, relief="solid", padx=8, pady=6)
        self.text.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(text_frame, orient="vertical", command=self.text.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.text.configure(yscrollcommand=scroll.set)

        opens = ttk.Frame(frame)
        opens.grid(row=7, column=0, columnspan=3, sticky="w", pady=(10, 0))
        self.open_buttons = {}
        for column, (key, label) in enumerate((("folder", "Open project folder"),
                                               ("diagram_html", "Open block diagram"),
                                               ("schedule", "Open cable schedule"),
                                               ("index", "Open updated index"))):
            button = ttk.Button(opens, text=label,
                                command=lambda which=key: self.open_output(which))
            button.grid(row=0, column=column, padx=(0, 8))
            self.open_buttons[key] = button

        ttk.Separator(frame, orient="horizontal").grid(row=8, column=0, columnspan=3,
                                                       sticky="ew", pady=12)
        bottom = ttk.Frame(frame)
        bottom.grid(row=9, column=0, columnspan=3, sticky="ew")
        bottom.columnconfigure(1, weight=1)
        self.new_button = ttk.Button(bottom, text="New Index", command=self.new_index)
        self.new_button.grid(row=0, column=0, sticky="w")
        ttk.Label(bottom, text="Results are saved under: %s" % projects_dir(),
                  foreground=GREY).grid(row=0, column=1, sticky="w", padx=12)
        self.exit_button = ttk.Button(bottom, text="Close project and exit", command=self.close)
        self.exit_button.grid(row=0, column=2, sticky="e")

        self._show_idle()
        self._bring_to_front()

    # ---- state ---------------------------------------------------------------
    def _set_enabled(self, button, enabled):
        button.configure(state="normal" if enabled else "disabled")

    def _set_text(self, lines):
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        if lines:
            self.text.insert("end", "\n".join(lines))
        self.text.configure(state="disabled")

    def _show_idle(self):
        self.path_var.set("")
        self.bar["value"] = 0
        self.step_var.set("")
        self.elapsed_var.set("Elapsed time: 0.0 s")
        self.status.configure(text=READY_TEXT, fg=GREY)
        self._set_text([])
        self._set_enabled(self.browse_button, True)
        self._set_enabled(self.new_button, False)
        for button in self.open_buttons.values():
            self._set_enabled(button, False)

    def _bring_to_front(self):
        try:
            self.root.lift()
            self.root.attributes("-topmost", True)
            self.root.after(300, lambda: self.root.attributes("-topmost", False))
        except Exception:  # cosmetic only
            pass

    # ---- actions -------------------------------------------------------------
    def browse(self):
        if self.session.running:
            return
        path = self.filedialog.askopenfilename(
            parent=self.root,
            title="Select the Instrument Index workbook",
            filetypes=[("Excel workbook", "*.xlsx *.xlsm"), ("All files", "*")])
        if path:
            self.load(path)

    def load(self, path):
        self.path_var.set(path)
        self._set_text([])
        self.bar["value"] = 0
        self.step_var.set("Starting...")
        self.status.configure(text="Processing...", fg=GREY)
        self._set_enabled(self.browse_button, False)
        self._set_enabled(self.new_button, False)
        for button in self.open_buttons.values():
            self._set_enabled(button, False)
        self.session.start(path)
        self._tick()

    def _tick(self):
        for event in self.session.poll():
            if event[0] == "progress":
                _, number, total, text = event
                self.bar["value"] = number
                if number < total:
                    self.step_var.set("Step %d of %d: %s" % (number + 1, total, text))
                else:
                    self.step_var.set(text)
            elif event[0] == "done":
                self._finish(event[1])
        self.elapsed_var.set("Elapsed time: %.1f s" % self.session.elapsed())
        if self.session.running:
            self.root.after(100, self._tick)

    def _finish(self, output):
        if output.ok:
            self.bar["value"] = len(STEPS)
            self.status.configure(text="COMPLETED  (%s)" % output.code, fg=GREEN)
        else:
            self.status.configure(text="FAILED  (%s  %s)" % (output.code, output.title), fg=RED)
        self._set_text(output.summary_lines()[2:])
        self._set_enabled(self.new_button, True)
        self._set_enabled(self.open_buttons["folder"], bool(output.folder))
        for key in ("diagram_html", "schedule", "index"):
            path = output.files.get(key)
            self._set_enabled(self.open_buttons[key], bool(path and os.path.isfile(path)))

    def open_output(self, which):
        output = self.session.output
        if output is None:
            return
        path = output.folder if which == "folder" else output.files.get(which)
        if not path or not os.path.exists(path):
            self.messagebox.showerror("Index-Reader", "That item is not available.",
                                      parent=self.root)
            return
        try:
            open_path(path)
        except Exception as error:
            self.messagebox.showerror("Index-Reader", "Could not open:\n%s\n\n%s"
                                      % (path, error), parent=self.root)

    def new_index(self):
        if self.session.running:
            return
        self.session.reset()
        self._show_idle()
        self.browse()

    def close(self):
        if self.session.running:
            if not self.messagebox.askyesno(
                    "Index-Reader", "A run is still in progress. Exit anyway?",
                    parent=self.root):
                return
        self.root.destroy()


NO_TK_MESSAGE = """Index-Reader could not open its window because this Python has no tkinter.

  macOS with Homebrew Python:   brew install python-tk
  macOS, any:                   install Python from python.org (tkinter included)
  Windows:                      re-run the Python installer and tick "tcl/tk and IDLE"
  Linux (Debian/Ubuntu):        sudo apt install python3-tk

The command line still works:   python -m index_reader "INDEX.xlsx"
"""


def main():
    try:
        import tkinter as tk
        from tkinter import filedialog, messagebox, ttk
        from tkinter import font as tkfont
    except ImportError:
        print(NO_TK_MESSAGE, file=sys.stderr)
        return 3
    try:
        root = tk.Tk()
    except tk.TclError as error:
        print("Index-Reader could not open a window: %s" % error, file=sys.stderr)
        return 3
    App(root, tk, ttk, filedialog, messagebox, tkfont)
    root.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
