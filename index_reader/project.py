"""One run = one project folder.

    Projects/<date>_<time>_<index file name>/
        <index file name>.xlsx                 copy of the input, exactly as loaded
        <index file name>_block_diagram.svg
        <index file name>_block_diagram.html
        <index file name>_cable_schedule.xlsx
        <index file name>_updated.xlsx
        run_log.txt

The Projects folder sits next to the application (next to the launcher when
run from source, next to the .exe when packaged).
"""

from __future__ import annotations

import datetime
import os
import re
import shutil
import sys
import time
import traceback
import zipfile

from . import config, errors
from .diagram import write_diagram
from .graph import build_graph
from .index_writer import write_updated_index
from .loader import load_index
from .schedule import write_schedule

PROJECTS_FOLDER = "Projects"
LOG_NAME = "run_log.txt"
EXTENSIONS = (".xlsx", ".xlsm")

STEPS = (
    "Checking the file",
    "Creating the project folder and saving a copy of the input",
    "Reading the workbook and checking the column headers",
    "Building the cable graph",
    "Drawing the block diagram",
    "Writing the cable schedule",
    "Writing the updated index",
)


def app_home():
    """Folder the application lives in."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def projects_dir():
    return os.path.join(app_home(), PROJECTS_FOLDER)


def safe_name(text):
    """Make `text` usable as a folder name on Windows and macOS."""
    text = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", text).strip(" .")
    return text or "index"


def project_folder(base_dir, input_path, now):
    """Path of a new, not yet existing folder for this run."""
    stem = os.path.splitext(os.path.basename(input_path))[0]
    name = "%s_%s" % (now.strftime("%Y-%m-%d_%H-%M-%S"), safe_name(stem))
    folder = os.path.join(base_dir, name)
    number = 2
    while os.path.exists(folder):
        folder = os.path.join(base_dir, "%s_%d" % (name, number))
        number += 1
    return folder


class RunOutput(object):
    """Result of one run."""

    def __init__(self):
        self.code = errors.UNEXPECTED
        self.message = ""
        self.input_path = ""
        self.folder = None        # project folder (None when the run never got that far)
        self.files = {}           # diagram_svg, diagram_html, schedule, index, input_copy, log
        self.elapsed = 0.0
        self.started = None
        self.data = None
        self.result = None
        self.report = None        # loader.HeaderReport, also available after a layout failure
        self.details = []         # extra lines for the log (traceback)

    @property
    def ok(self):
        return self.code == errors.SUCCESS

    @property
    def title(self):
        return errors.TITLES.get(self.code, "")

    def summary_lines(self):
        """What the window and the command line show at the end of a run."""
        lines = []
        if self.ok:
            lines.append("COMPLETED  (%s)" % self.code)
        else:
            lines.append("FAILED  (%s  %s)" % (self.code, self.title))
        lines.append("Elapsed time: %.1f s" % self.elapsed)
        lines.append("")
        lines.append("Input: %s" % os.path.basename(self.input_path))
        if not self.ok:
            lines.append("")
            lines.extend(self.message.splitlines())
        if self.report is not None:
            lines.append("")
            lines.extend(self.report.lines())
        if self.result is not None and self.ok:
            counts = self.result.counts()
            lines.append("")
            lines.append("%(signals)d signals, %(plc_panels)d PLC panel(s), "
                         "%(marshalling_panels)d other marshalling panel(s), "
                         "%(junction_boxes)d junction box(es), %(end_points)d end points"
                         % counts)
            lines.append("%(cable_runs)d cable runs: %(index_runs)d with a cable ID from the "
                         "index, %(new_id_runs)d with a new ID, %(existing_runs)d existing"
                         % counts)
            lines.append("%(new_cells)d cable ID(s) proposed in the updated index" % counts)
            lines.append("%(warnings)d warning(s), %(infos)d information note(s), "
                         "%(skipped_rows)d skipped row(s) with wiring data "
                         "(see the Findings and Skipped Rows sheets)" % counts)
        if self.folder:
            lines.append("")
            lines.append("Project folder:")
            lines.append("  " + self.folder)
        return lines


def process(input_path, output_dir, progress=None, first_step=2):
    """Run the engine on `input_path`, writing the outputs into `output_dir`.

    Returns (data, result, files). Raises on any problem.
    progress(step number, total steps, text) is called before each step.
    """
    def step(offset):
        if progress:
            progress(first_step + offset, len(STEPS), STEPS[first_step + offset])

    stem = os.path.splitext(os.path.basename(input_path))[0]
    files = {
        "diagram_svg": os.path.join(output_dir, stem + "_block_diagram.svg"),
        "diagram_html": os.path.join(output_dir, stem + "_block_diagram.html"),
        "schedule": os.path.join(output_dir, stem + "_cable_schedule.xlsx"),
        "index": os.path.join(output_dir, stem + "_updated.xlsx"),
    }
    step(0)
    data = load_index(input_path)
    step(1)
    result = build_graph(data)
    if not result.signals:
        raise errors.AppError(errors.NO_INSTRUMENTS,
                              "No row with an instrument tag was found on tab '%s'." % data.sheet)
    try:
        step(2)
        write_diagram(result, data, files["diagram_svg"], files["diagram_html"])
        step(3)
        write_schedule(result, data, files["schedule"])
        step(4)
        cells = {}
        for (row, field), cable_id in result.new_cells.items():
            cells[(row, data.columns[field])] = cable_id
        write_updated_index(input_path, files["index"], data.sheet, cells)
    except OSError as error:
        code, message = errors.classify(error, writing=True)
        raise errors.AppError(code, message)
    return data, result, files


def check_input(path):
    """Raise AppError when `path` cannot be an Instrument Index workbook."""
    if not path or not os.path.isfile(path):
        raise errors.AppError(errors.FILE_NOT_FOUND, "File not found: %s" % path)
    name = os.path.basename(path)
    if name.startswith("~$"):
        raise errors.AppError(errors.NOT_A_WORKBOOK,
                              "%s is a temporary lock file that Excel creates while a "
                              "workbook is open. Pick the workbook itself." % name)
    if os.path.splitext(name)[1].lower() not in EXTENSIONS:
        raise errors.AppError(errors.NOT_A_WORKBOOK,
                              "%s is not an .xlsx workbook. Older .xls files must be saved "
                              "as .xlsx in Excel first." % name)
    try:
        valid = zipfile.is_zipfile(path)
    except OSError as error:
        raise errors.AppError(*errors.classify(error))
    if not valid:
        raise errors.AppError(errors.NOT_A_WORKBOOK,
                              "%s cannot be opened as an .xlsx workbook. It may be damaged "
                              "or password protected." % name)


def run_project(input_path, base_dir=None, progress=None, now=None):
    """Run on `input_path` inside a new project folder. Never raises.

    base_dir: folder that holds the project folders (default: Projects next to the app)
    progress: optional function(step number, total steps, text)
    now:      datetime used for the folder name (default: current local time)
    """
    out = RunOutput()
    out.input_path = os.path.abspath(input_path) if input_path else ""
    out.started = now or datetime.datetime.now()
    clock = time.perf_counter()
    writing = False
    try:
        if progress:
            progress(0, len(STEPS), STEPS[0])
        check_input(out.input_path)

        if progress:
            progress(1, len(STEPS), STEPS[1])
        writing = True
        base = os.path.abspath(base_dir or projects_dir())
        folder = project_folder(base, out.input_path, out.started)
        os.makedirs(folder)
        out.folder = folder
        copy = os.path.join(folder, os.path.basename(out.input_path))
        writing = False
        try:
            shutil.copyfile(out.input_path, copy)
        except PermissionError as error:
            raise errors.AppError(*errors.classify(error))
        out.files["input_copy"] = copy

        # work on the saved copy, so the outputs match the archived input exactly
        out.data, out.result, files = process(copy, folder, progress)
        out.files.update(files)
        out.report = out.data.report
        out.code = errors.SUCCESS
        out.message = errors.TITLES[errors.SUCCESS]
    except Exception as error:  # every failure becomes a result code
        out.code, out.message = errors.classify(error, writing=writing)
        if out.code == errors.UNEXPECTED:
            out.details = traceback.format_exc().splitlines()
        out.report = getattr(error, "report", None)
    out.elapsed = time.perf_counter() - clock
    if progress:
        progress(len(STEPS), len(STEPS), "Completed" if out.ok else "Stopped")
    _write_log(out)
    return out


def _write_log(out):
    if not out.folder or not os.path.isdir(out.folder):
        return
    path = os.path.join(out.folder, LOG_NAME)
    lines = ["Index-Reader %s" % config.VERSION,
             "Started: %s" % out.started.strftime("%Y-%m-%d %H:%M:%S"),
             "Input file: %s" % out.input_path]
    if out.data is not None and getattr(out.data, "sha256", ""):
        lines.append("Input SHA-256: %s" % out.data.sha256)
    lines.append("Result code: %s  %s" % (out.code, out.title))
    lines.append("")
    lines.extend(out.summary_lines())
    if out.ok:
        lines.append("")
        lines.append("Files:")
        for key in ("input_copy", "diagram_svg", "diagram_html", "schedule", "index"):
            lines.append("  " + os.path.basename(out.files[key]))
    if out.details:
        lines.append("")
        lines.append("Technical details:")
        lines.extend(out.details)
    try:
        with open(path, "w", encoding="utf-8", newline="\n") as handle:
            handle.write("\n".join(lines) + "\n")
        out.files["log"] = path
    except OSError:
        pass
