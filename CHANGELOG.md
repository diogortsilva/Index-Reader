# Changelog

Every revision pushed to GitHub is listed here and tagged with the same number.

## v0.1.1 - 2026-11-20

- Only the main tab of the workbook is read. Other tabs are ignored and copied unchanged to
  the updated index. This was already how the engine behaved; it is now a stated rule,
  covered by tests, including a main tab that has been renamed.
- Version numbering: one number and one git tag per pushed revision.

## v0.1.0 - 2026-11-20

- First revision: workbook loader with header check, cable graph, cable sizing, block diagram
  (SVG and HTML viewer), cable schedule workbook, updated index with proposed cable IDs
  highlighted, command line.
