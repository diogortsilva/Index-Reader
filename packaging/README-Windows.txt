Index-Reader for Windows
========================

Reads an Instrument Index workbook (.xlsx) and produces a cable block diagram,
a cable schedule and an updated index with proposed cable IDs.

Everything runs on this computer. No Python, no installation, no internet
connection and no other software is needed. Nothing is sent anywhere.

HOW TO START
  1. Keep this whole folder together (Index-Reader.exe needs the _internal folder).
  2. Double-click Index-Reader.exe.
  3. Click "Browse and load..." and pick the Instrument Index workbook.

If Windows shows "Windows protected your PC", click "More info" and then
"Run anyway". The program is not code-signed, so Windows asks the first time.

WHERE THE RESULTS GO
  Each run is saved in a new folder next to Index-Reader.exe:
      Projects\<date>_<time>_<index file name>\
  It holds a copy of the input workbook, the block diagram (.html and .svg),
  the cable schedule, the updated index and run_log.txt.
  Put this folder somewhere you can write to (Documents or Desktop, not
  Program Files).

RESULT CODES
  IR-000  Completed
  IR-101  File not found
  IR-102  Not an Excel .xlsx workbook
  IR-103  File cannot be read
  IR-201  Workbook layout does not match the reference layout
  IR-202  No instrument rows found on the main tab
  IR-301  Cannot write to the project folder
  IR-900  Unexpected error (details are in run_log.txt)

Source code and changes: https://github.com/diogortsilva/Index-Reader
