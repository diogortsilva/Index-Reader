# Changelog

Every revision pushed to GitHub is listed here and tagged with the same number.

## v0.3.0 - 2026-11-20

- Windows program: every pushed revision is built into `Index-Reader.exe` on a GitHub Windows
  machine and published as a release (`Index-Reader-vX.Y.Z-windows.zip`). It needs no Python,
  no installation and no internet connection.
- The build runs all unit tests on Windows, opens the real window, runs a test workbook
  through the packaged program, and only then publishes.
- Releases carry the version tag (`v0.3.0`, ...), created by the build.
- New test that opens the real window where the computer can show one.

## v0.2.0 - 2026-11-20

- Desktop window: browse and load an index, progress bar with the current step, elapsed
  time, and a result line with a result code (`IR-000` completed, `IR-1xx` input file,
  `IR-2xx` workbook content, `IR-3xx` output folder, `IR-900` unexpected).
- "New Index" button to run another workbook; "Close project and exit" button.
- Buttons to open the project folder, block diagram, cable schedule and updated index.
- Every run is saved in `Projects/<date>_<time>_<index file name>/` together with a copy of
  the input workbook and a `run_log.txt`.
- Double-click launchers: `Index-Reader.command` (macOS) and `Index-Reader.bat` (Windows).
- Command line: with no arguments the window opens; with a workbook the run goes to a new
  Projects folder; `-o DIR` keeps the old behaviour.
- No change to the engine: outputs for a given index are identical to v0.1.1 apart from the
  version text.

## v0.1.1 - 2026-11-20

- Only the main tab of the workbook is read. Other tabs are ignored and copied unchanged to
  the updated index. This was already how the engine behaved; it is now a stated rule,
  covered by tests, including a main tab that has been renamed.
- Version numbering: one number and one git tag per pushed revision.

## v0.1.0 - 2026-11-20

- First revision: workbook loader with header check, cable graph, cable sizing, block diagram
  (SVG and HTML viewer), cable schedule workbook, updated index with proposed cable IDs
  highlighted, command line.
