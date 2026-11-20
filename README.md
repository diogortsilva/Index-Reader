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
input always produces byte-identical outputs.

## Run

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m index_reader "path/to/INSTRUMENT INDEX.xlsx" -o output_folder
```

Without `-o`, outputs go to `<index name>_output` next to the workbook.
Python 3.9 or newer. The only dependency is `openpyxl`.

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

## Status

- v0.1.0: engine and command line.
- Next: desktop window (file picker, run, results) and a packaged Windows `.exe`.
