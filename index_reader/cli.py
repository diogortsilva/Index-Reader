"""Command line entry point:  python -m index_reader INDEX.xlsx [-o OUTPUT_FOLDER]"""

from __future__ import annotations

import argparse
import os
import sys

from . import config
from .diagram import write_diagram
from .graph import build_graph
from .index_writer import write_updated_index
from .loader import HeaderError, load_index
from .schedule import write_schedule


class RunOutput(object):
    def __init__(self):
        self.data = None
        self.result = None
        self.files = {}


def run(input_path, output_dir=None, log=None):
    """Load the index, build the cable graph and write all outputs.

    Returns a RunOutput. Raises loader.HeaderError when the workbook layout
    cannot be matched. `log` is an optional function taking one line of text.
    """
    say = log or (lambda line: None)
    input_path = os.path.abspath(input_path)
    stem = os.path.splitext(os.path.basename(input_path))[0]
    if output_dir is None:
        output_dir = os.path.join(os.path.dirname(input_path), stem + "_output")
    output_dir = os.path.abspath(output_dir)
    if not os.path.isdir(output_dir):
        os.makedirs(output_dir)

    out = RunOutput()
    say("Reading %s" % os.path.basename(input_path))
    out.data = load_index(input_path)
    for line in out.data.report.lines():
        say("  " + line)

    out.result = build_graph(out.data)
    counts = out.result.counts()
    say("Built the graph: %(signals)d signals, %(plc_panels)d PLC panel(s), "
        "%(marshalling_panels)d other marshalling panel(s), %(junction_boxes)d junction "
        "box(es), %(end_points)d end points" % counts)
    say("Cable runs: %(cable_runs)d (%(index_runs)d from the index, %(new_id_runs)d with a "
        "new ID, %(existing_runs)d existing)" % counts)

    out.files["diagram_svg"] = os.path.join(output_dir, stem + "_block_diagram.svg")
    out.files["diagram_html"] = os.path.join(output_dir, stem + "_block_diagram.html")
    out.files["schedule"] = os.path.join(output_dir, stem + "_cable_schedule.xlsx")
    out.files["index"] = os.path.join(output_dir, stem + "_updated.xlsx")

    write_diagram(out.result, out.data, out.files["diagram_svg"], out.files["diagram_html"])
    write_schedule(out.result, out.data, out.files["schedule"])
    cells = {}
    for (row, field), cable_id in out.result.new_cells.items():
        cells[(row, out.data.columns[field])] = cable_id
    write_updated_index(input_path, out.files["index"], out.data.sheet, cells)
    say("Wrote %d proposed cable ID(s) into the updated index" % len(cells))
    say("%(warnings)d warning(s), %(infos)d information note(s), %(skipped_rows)d skipped "
        "row(s) with wiring data - see the Findings and Skipped Rows sheets" % counts)
    for key in ("diagram_svg", "diagram_html", "schedule", "index"):
        say("  " + out.files[key])
    return out


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="index_reader",
        description="Build the cable graph, cable schedule and updated Instrument Index. "
                    "Runs locally; nothing is sent anywhere.")
    parser.add_argument("index", help="Instrument Index workbook (.xlsx)")
    parser.add_argument("-o", "--output", help="output folder "
                        "(default: <index name>_output next to the workbook)")
    parser.add_argument("--version", action="version", version="Index-Reader " + config.VERSION)
    args = parser.parse_args(argv)
    if not os.path.isfile(args.index):
        print("File not found: %s" % args.index, file=sys.stderr)
        return 2
    try:
        run(args.index, args.output, log=print)
    except HeaderError as error:
        print(str(error), file=sys.stderr)
        if error.report is not None:
            for line in error.report.lines():
                print("  " + line, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
