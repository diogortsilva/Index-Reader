"""Command line entry point.

    python -m index_reader                      open the window
    python -m index_reader INDEX.xlsx           run into a new Projects/<date>_<time>_<name> folder
    python -m index_reader INDEX.xlsx -o DIR    run and write the outputs straight into DIR
"""

from __future__ import annotations

import argparse
import os
import sys

from . import config, errors
from .loader import HeaderError
from .project import RunOutput, process, run_project


def run(input_path, output_dir=None, log=None):
    """Run the engine and write the outputs into `output_dir` (no project folder).

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
    out.input_path = input_path
    out.data, out.result, out.files = process(
        input_path, output_dir, progress=lambda number, total, text: say(text))
    out.report = out.data.report
    out.code = errors.SUCCESS
    return out


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="index_reader",
        description="Build the cable graph, cable schedule and updated Instrument Index. "
                    "Runs locally; nothing is sent anywhere. Without arguments the window "
                    "opens.")
    parser.add_argument("index", nargs="?", help="Instrument Index workbook (.xlsx)")
    parser.add_argument("-o", "--output", help="write the outputs straight into this folder "
                        "instead of a new folder under Projects")
    parser.add_argument("--version", action="version", version="Index-Reader " + config.VERSION)
    parser.add_argument("--self-test", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)

    if args.self_test:
        # build check: open the real window, run the workbook through it, close
        from .gui import self_test
        return self_test(args.index)

    if not args.index:
        from .gui import main as gui_main
        return gui_main()

    if args.output:
        if not os.path.isfile(args.index):
            print("File not found: %s" % args.index, file=sys.stderr)
            return 2
        try:
            out = run(args.index, args.output, log=print)
        except HeaderError as error:
            print(str(error), file=sys.stderr)
            if error.report is not None:
                for line in error.report.lines():
                    print("  " + line, file=sys.stderr)
            return 2
        for line in out.summary_lines()[3:]:
            print(line)
        for key in ("diagram_svg", "diagram_html", "schedule", "index"):
            print("  " + out.files[key])
        return 0

    out = run_project(args.index, progress=lambda number, total, text:
                      print("[%d/%d] %s" % (number, total, text)))
    for line in out.summary_lines():
        print(line)
    return 0 if out.ok else 1


if __name__ == "__main__":
    sys.exit(main())
