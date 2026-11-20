# Index-Reader

Deterministic cable builder for Instrument Index workbooks.

It reads an Instrument Index (`.xlsx`, sheet `LOOP`), builds the cable graph from the
PLC/marshalling panel out to each end device, proposes multiconductor cable sizes, and writes:

| Output | File |
| --- | --- |
| Block diagram | `<name>_block_diagram.svg` and `.html` (viewer with zoom and search) |
| Cable schedule | `<name>_cable_schedule.xlsx` |
| Updated Instrument Index | `<name>_updated.xlsx` (new cable IDs: yellow fill, red text) |

Everything runs locally. There is no network code and no AI engine in this package: the same
input always produces byte-identical output files (only the folder name and `run_log.txt`
carry the date and time of the run).

## Windows program (no Python needed)

Download `Index-Reader-vX.Y.Z-windows.zip` from the
[Releases page](https://github.com/diogortsilva/Index-Reader/releases), extract it, and
double-click `Index-Reader.exe` inside the extracted folder. Nothing else has to be installed
and no internet connection is used. Results go to a `Projects` folder next to the `.exe`.

The program is not code-signed: the first time, Windows may show "Windows protected your PC".
Click **More info**, then **Run anyway**.

Each release is built by `.github/workflows/windows-release.yml` from the source in this
repository, after the tests pass on Windows.

## Start from source

Double-click the launcher in this folder:

- **macOS:** `Index-Reader.command`
- **Windows:** `Index-Reader.bat`

The first launch sets up a private Python environment in `.venv` and downloads `openpyxl`
(the only dependency; this is the only time the internet is used). Every later launch runs
offline. Python 3.9 or newer with tkinter is required.

In the window:

1. **Browse and load...** picks the Instrument Index and starts the run. The progress bar,
   the current step and the elapsed time update while it works.
2. The result line shows `COMPLETED (IR-000)` or `FAILED (<code> <reason>)`, followed by the
   header check and the counts. Buttons open the project folder, block diagram, cable
   schedule and updated index.
3. **New Index** clears the window and asks for the next workbook.
4. **Close project and exit** closes the program.

## Project folders

Every run gets its own folder next to the launcher:

```
Projects/
  2026-11-20_14-16-05_<index file name>/
    <index file name>.xlsx                  copy of the input, exactly as loaded
    <index file name>_block_diagram.svg
    <index file name>_block_diagram.html
    <index file name>_cable_schedule.xlsx
    <index file name>_updated.xlsx
    run_log.txt                             date, input checksum, result code, summary
```

The run works on the saved copy, so the outputs always match the archived input. `Projects/`
is listed in `.gitignore` and is never committed.

## Result codes

| Code | Meaning |
| --- | --- |
| `IR-000` | Completed |
| `IR-101` | File not found |
| `IR-102` | Not an Excel `.xlsx` workbook (wrong type, damaged, password protected, lock file) |
| `IR-103` | File cannot be read (permission; often open and locked) |
| `IR-201` | Workbook layout does not match the reference layout (required column missing) |
| `IR-202` | No instrument rows found on the main tab |
| `IR-301` | Cannot write to the project folder |
| `IR-900` | Unexpected error (technical details are in `run_log.txt`) |

## Command line

```bash
source .venv/bin/activate
python -m index_reader                              # open the window
python -m index_reader "path/to/INDEX.xlsx"         # run into a new Projects folder
python -m index_reader "path/to/INDEX.xlsx" -o DIR  # write the outputs straight into DIR
```

## Test

```bash
python -m unittest discover -s tests
```

Tests build small synthetic workbooks; no project data is needed or stored in this repository.
`.gitignore` blocks `*.xlsx` so a project workbook cannot be committed by accident.

## Rules

All rules live in `index_reader/config.py`.

- **Path of a signal:** Marshalling 1 → Marshalling 2 → Marshalling 3 → J-Box 1 → J-Box 2 →
  J-Box 3 → end device, using only the sections whose panel tag is populated. The cable ID
  listed in a section connects it to the next populated section.
- **End device:** grouped by MCC section + cubicle, else MCC section + end-device tag, else
  end-device tag. With none of these, every instrument is its own destination.
  Location defaults to `FIELD`.
- **Pair or triad:** the pair-number column next to the cable ID (`PR.` / `TR.`). If blank, a
  populated RTN terminal at either end of the segment means triad.
- **Sizes:** pairs 1, 2, 4, 8, 12, 16, 24; triads 1, 4, 6, 12. Three or more in use: 15% spare,
  rounded up. Larger needs are split (fewest cables, then least capacity, largest first).
- **Existing cables:** any cable ID containing `EXISTING` is grouped and listed, never sized.
- **Blank cable ID between panels:** `newcable_0001`, one per source/destination pair.
- **Blank cable ID to the end device:** `newcable_<instrument tag>`, or `newcable_<end device>`
  when signals share an end device.
- **Rows used:** rows with an instrument tag whose I/O type is not `SPARE` or `DELETED`.
- **Tabs used:** only the main tab (`LOOP`, or the tab whose headers match the reference
  layout if it was renamed). All other tabs are ignored and copied unchanged to the updated
  index.

## Header check

The header text of every column in the reference layout is stored in
`index_reader/sample_headers.py`. On load, each column the tool uses is located by that text:

- found in the reference position: OK
- found elsewhere: followed, and reported as MOVED
- description edited but short code intact: followed, and reported as RENAMED
- required column not found: the run stops and names the column

To adopt a new reference layout: `python tools/make_sample_headers.py REFERENCE.xlsx`.

## Checks reported in the schedule workbook (sheet `Findings`)

`CABLE_ID_REUSED`, `DUPLICATE_PAIR`, `MIXED_PAIRS_TRIADS`, `PAIR_WITH_RTN`,
`PAIR_NUMBER_ABOVE_SIZE`, `PLC_MISMATCH`, `NO_IO_ADDRESS`, `DUPLICATE_IO_ADDRESS`,
`DUPLICATE_TAG`, `SECTION_WITHOUT_TAG`, `NO_TERMINAL_STRIP`, `CABLE_AFTER_END`.

## Versions

Every revision pushed to GitHub gets the next version number. From v0.3.0 on, the Windows
build also creates a matching git tag and release. The number is in
`index_reader/config.py` and is printed on the block diagram and in the schedule's Run Info
sheet. See `CHANGELOG.md`.

- Third number: fixes and small changes. Second number: new features. First number: 1 at the
  first release packaged for Windows users.
