"""Write the cable schedule workbook."""

from __future__ import annotations

import os

from . import config
from .graph import (STATUS_EXISTING, STATUS_NEW, sorted_runs)
from .xlsxzip import make_deterministic

RED = "FFFF0000"
YELLOW = "FFFFFF00"
HEADER_FILL = "FF1F4E79"
GREY_TEXT = "FF7F7F7F"


def _styles():
    from openpyxl.styles import Alignment, Font, PatternFill
    return {
        "header_font": Font(bold=True, color="FFFFFFFF"),
        "header_fill": PatternFill("solid", fgColor=HEADER_FILL),
        "header_align": Alignment(vertical="center", wrap_text=True),
        "new_font": Font(color=RED),
        "new_fill": PatternFill("solid", fgColor=YELLOW),
        "existing_font": Font(color=GREY_TEXT),
        "warn_font": Font(bold=True, color=RED),
        "wrap": Alignment(vertical="top", wrap_text=True),
        "bold": Font(bold=True),
    }


def _sheet(workbook, title, headers, widths, st):
    sheet = workbook.create_sheet(title)
    sheet.append(headers)
    for index, cell in enumerate(sheet[1], start=1):
        cell.font = st["header_font"]
        cell.fill = st["header_fill"]
        cell.alignment = st["header_align"]
    from openpyxl.utils import get_column_letter
    for index, width in enumerate(widths, start=1):
        sheet.column_dimensions[get_column_letter(index)].width = width
    sheet.freeze_panes = "A2"
    sheet.row_dimensions[1].height = 32
    return sheet


def _finish(sheet):
    from openpyxl.utils import get_column_letter
    if sheet.max_row > 1:
        sheet.auto_filter.ref = "A1:%s%d" % (get_column_letter(sheet.max_column), sheet.max_row)


def schedule_rows(result):
    """Rows of the cable schedule as plain dicts (also used by the tests)."""
    rows = []
    for run in sorted_runs(result):
        src, dst = result.nodes[run.src], result.nodes[run.dst]
        proposal = run.proposal
        if run.status == STATUS_EXISTING:
            size, required, spare = "Existing - not sized", "", ""
        else:
            size = proposal.text
            parts = []
            if proposal.required_pairs:
                parts.append("%d PR" % proposal.required_pairs)
            if proposal.required_triads:
                parts.append("%d TR" % proposal.required_triads)
            required = " + ".join(parts)
            spare = proposal.spare_text
        rows.append({
            "cable_id": run.cable_id,
            "status": run.status,
            "size": size,
            "used_pairs": run.used_pairs,
            "used_triads": run.used_triads,
            "required": required,
            "spare": spare,
            "source": src.name,
            "source_strips": ", ".join(run.strips("src_strip")),
            "destination": dst.name,
            "destination_type": dst.kind,
            "destination_strips": ", ".join(run.strips("dst_strip")),
            "signals": len(run.segments),
            "tags": ", ".join(run.tags),
            "notes": "; ".join(run.notes),
        })
    return rows


def write_schedule(result, data, path):
    import openpyxl

    st = _styles()
    workbook = openpyxl.Workbook()
    workbook.remove(workbook.active)

    # ---- Cable Schedule ----------------------------------------------------
    sheet = _sheet(workbook, "Cable Schedule",
                   ["Cable ID", "Status", "Proposed size", "Used pairs", "Used triads",
                    "Required with spare", "Spare", "Source", "Source strip(s)", "Destination",
                    "Destination type", "Destination strip(s)", "Signals", "Instrument tags",
                    "Notes"],
                   [34, 12, 20, 8, 8, 12, 10, 22, 18, 36, 15, 14, 8, 70, 40], st)
    for row in schedule_rows(result):
        sheet.append([row["cable_id"], row["status"], row["size"], row["used_pairs"],
                      row["used_triads"], row["required"], row["spare"], row["source"],
                      row["source_strips"], row["destination"], row["destination_type"],
                      row["destination_strips"], row["signals"], row["tags"], row["notes"]])
        line = sheet.max_row
        if row["status"] == STATUS_NEW:
            sheet.cell(line, 1).font = st["new_font"]
            sheet.cell(line, 1).fill = st["new_fill"]
        elif row["status"] == STATUS_EXISTING:
            for column in range(1, 4):
                sheet.cell(line, column).font = st["existing_font"]
        if row["notes"]:
            sheet.cell(line, 15).font = st["new_font"]
    _finish(sheet)

    # ---- Signal Routing ----------------------------------------------------
    hops = max([len(s.segments) for s in result.signals] or [0])
    headers = ["Index row", "Instrument tag", "Description", "I/O type", "PLC", "Rack", "Slot",
               "Point", "From"]
    widths = [8, 20, 40, 8, 10, 6, 6, 6, 22]
    for number in range(1, hops + 1):
        headers += ["Cable %d" % number, "Type %d" % number, "To %d" % number]
        widths += [34, 7, 34]
    sheet = _sheet(workbook, "Signal Routing", headers, widths, st)
    for signal in result.signals:
        record = signal.record
        line = [signal.row, signal.tag, signal.description, record["io_type"],
                record["plc"] or record["cabinet"], record["rack"], record["slot"],
                record["point"], result.nodes[signal.nodes[0]].name if signal.nodes else ""]
        new_columns = []
        for seg in signal.segments:
            if seg.status == STATUS_NEW:
                new_columns.append(len(line) + 1)
            line += [seg.cable_id, seg.kind, result.nodes[seg.dst].name]
        sheet.append(line)
        for column in new_columns:
            cell = sheet.cell(sheet.max_row, column)
            cell.font = st["new_font"]
            cell.fill = st["new_fill"]
    _finish(sheet)

    # ---- Panels & Devices --------------------------------------------------
    cables_in, cables_out = {}, {}
    for run in result.runs:
        cables_out.setdefault(run.src, []).append(run.cable_id)
        cables_in.setdefault(run.dst, []).append(run.cable_id)
    sheet = _sheet(workbook, "Panels & Devices",
                   ["Name", "Type", "Location", "PLC", "Terminal strips", "Signals",
                    "Cable runs in", "Cable runs out"],
                   [38, 15, 12, 12, 40, 8, 10, 10], st)
    order = ["PLC PANEL", "MARSHALLING", "JUNCTION BOX", "MCC", "END DEVICE", "INSTRUMENT"]
    for node in sorted(result.nodes.values(), key=lambda n: (order.index(n.kind), n.first_row or 0,
                                                             n.key)):
        sheet.append([node.name, node.kind,
                      ", ".join(node.locations) if node.is_end else "",
                      ", ".join(node.plcs), ", ".join(node.strips), len(node.tags),
                      len(cables_in.get(node.key, [])), len(cables_out.get(node.key, []))])
    _finish(sheet)

    # ---- Findings ----------------------------------------------------------
    sheet = _sheet(workbook, "Findings",
                   ["Level", "Check", "Index row", "Instrument tag", "Cable ID", "Message"],
                   [10, 24, 8, 20, 34, 110], st)
    for finding in sorted(result.findings, key=lambda f: (0 if f.level == "WARNING" else 1,
                                                          f.code, f.row or 0)):
        sheet.append([finding.level, finding.code, finding.row, finding.tag, finding.cable,
                      finding.message])
        if finding.level == "WARNING":
            sheet.cell(sheet.max_row, 1).font = st["warn_font"]
    _finish(sheet)

    # ---- Skipped Rows ------------------------------------------------------
    sheet = _sheet(workbook, "Skipped Rows", ["Index row", "Reason", "Wiring data on the row"],
                   [8, 44, 110], st)
    for row, reason, details in result.skipped:
        sheet.append([row, reason, details])
    _finish(sheet)

    # ---- Run Info ----------------------------------------------------------
    sheet = _sheet(workbook, "Run Info", ["Item", "Value"], [34, 110], st)
    sheet.append(["Input file", os.path.basename(data.path)])
    sheet.append(["Input SHA-256", data.sha256])
    sheet.append(["Sheet", data.sheet])
    for label, value in config.rules_summary():
        sheet.append([label, value])
    sheet.append(["", ""])
    sheet.append(["RESULT", ""])
    sheet.cell(sheet.max_row, 1).font = st["bold"]
    counts = result.counts()
    for label, key in (("Instrument signals", "signals"), ("PLC / marshalling 1 panels", "plc_panels"),
                       ("Other marshalling panels", "marshalling_panels"),
                       ("Junction boxes", "junction_boxes"), ("End points", "end_points"),
                       ("Cable runs", "cable_runs"), ("  existing (not sized)", "existing_runs"),
                       ("  cable ID from the index (sized)", "index_runs"),
                       ("  new cable ID proposed (sized)", "new_id_runs"),
                       ("Index cells filled with a new cable ID", "new_cells"),
                       ("Warnings", "warnings"), ("Information notes", "infos"),
                       ("Rows skipped with wiring data", "skipped_rows")):
        sheet.append([label, counts[key]])
    sheet.append(["PLCs", ", ".join(result.plcs)])
    sheet.append(["", ""])
    sheet.append(["HEADER CHECK", ""])
    sheet.cell(sheet.max_row, 1).font = st["bold"]
    for text in data.report.lines():
        sheet.append(["", text])
    for row in sheet.iter_rows(min_row=2):
        row[1].alignment = st["wrap"]

    workbook.save(path)
    make_deterministic(path)
    return path
