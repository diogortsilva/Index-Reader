"""Write the updated Instrument Index.

The input workbook is copied part by part and only two parts are touched:
the sheet XML (the cells that receive a proposed cable ID) and the style table
(one yellow fill plus red-font copies of the styles those cells already had).
Everything else - other sheets, dropdown lists, comments, column widths,
filters, print settings - is carried over byte for byte. The spreadsheet
library is deliberately not used here because re-saving through it would drop
the dropdown lists.
"""

from __future__ import annotations

import re
import zipfile
from xml.sax.saxutils import escape

RED_RGB = "FFFF0000"
YELLOW_RGB = "FFFFFF00"

_ROW_OPEN = re.compile(r"<row\b[^>]*>")
_CELL = re.compile(r"<c\b([^>]*?)(/>|>(.*?)</c>)", re.S)
_ATTR_R = re.compile(r'\br="([A-Z]+)(\d+)"')
_ATTR_ROW = re.compile(r'\br="(\d+)"')
_ATTR_S = re.compile(r'\bs="(\d+)"')


class IndexWriteError(Exception):
    pass


def _col_index(letters):
    index = 0
    for ch in letters:
        index = index * 26 + (ord(ch) - 64)
    return index


def _unescape(text):
    return (text.replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", '"')
            .replace("&apos;", "'").replace("&amp;", "&"))


def _resolve(target):
    target = target.lstrip("/")
    return target if target.startswith("xl/") else "xl/" + target


def _find_parts(parts, sheet_name):
    """Return (sheet part name, styles part name)."""
    workbook = parts["xl/workbook.xml"].decode("utf-8")
    rels = parts["xl/_rels/workbook.xml.rels"].decode("utf-8")
    rel_id = None
    for tag in re.findall(r"<sheet\b[^>]*>", workbook):
        name = re.search(r'\bname="([^"]*)"', tag)
        rid = re.search(r'\br:id="([^"]*)"', tag)
        if name and rid and _unescape(name.group(1)) == sheet_name:
            rel_id = rid.group(1)
            break
    if rel_id is None:
        raise IndexWriteError("Sheet '%s' not found in the workbook." % sheet_name)
    sheet_part = styles_part = None
    for tag in re.findall(r"<Relationship\b[^>]*>", rels):
        rid = re.search(r'\bId="([^"]*)"', tag)
        target = re.search(r'\bTarget="([^"]*)"', tag)
        kind = re.search(r'\bType="([^"]*)"', tag)
        if not (rid and target):
            continue
        if rid.group(1) == rel_id:
            sheet_part = _resolve(target.group(1))
        if kind and kind.group(1).endswith("/styles"):
            styles_part = _resolve(target.group(1))
    if sheet_part not in parts or styles_part not in parts:
        raise IndexWriteError("Could not locate the sheet or style part inside the workbook.")
    return sheet_part, styles_part


# --------------------------------------------------------------------------
# styles
# --------------------------------------------------------------------------
class _Styles(object):
    def __init__(self, xml):
        self.xml = xml
        self.fonts, self._fonts_span = self._block("fonts", "font")
        self.fills, self._fills_span = self._block("fills", "fill")
        self.xfs, self._xfs_span = self._block("cellXfs", "xf")
        self._font_map = {}
        self._xf_map = {}
        self._fill_id = None

    def _block(self, outer, inner):
        match = re.search(r"<%s\b[^>]*>(.*?)</%s>" % (outer, outer), self.xml, re.S)
        if not match:
            raise IndexWriteError("Style table has no <%s> block." % outer)
        items = re.findall(r"<%s\b[^>]*?(?:/>|>.*?</%s>)" % (inner, inner), match.group(1), re.S)
        return items, match.span()

    def _red_font(self, font_id):
        if font_id in self._font_map:
            return self._font_map[font_id]
        font = self.fonts[font_id] if font_id < len(self.fonts) else "<font/>"
        color = '<color rgb="%s"/>' % RED_RGB
        if re.search(r"<color\b[^>]*/>", font):
            font = re.sub(r"<color\b[^>]*/>", color, font, count=1)
        elif re.search(r"<sz\b[^>]*/>", font):
            font = re.sub(r"(<sz\b[^>]*/>)", r"\1" + color, font, count=1)
        elif font.endswith("/>"):
            font = "<font>%s</font>" % color
        else:
            font = font.replace("</font>", color + "</font>")
        self.fonts.append(font)
        self._font_map[font_id] = len(self.fonts) - 1
        return self._font_map[font_id]

    def _yellow_fill(self):
        if self._fill_id is None:
            self.fills.append('<fill><patternFill patternType="solid"><fgColor rgb="%s"/>'
                              '<bgColor indexed="64"/></patternFill></fill>' % YELLOW_RGB)
            self._fill_id = len(self.fills) - 1
        return self._fill_id

    @staticmethod
    def _set_attr(tag_open, name, value):
        pattern = re.compile(r'\b%s="[^"]*"' % name)
        if pattern.search(tag_open):
            return pattern.sub('%s="%s"' % (name, value), tag_open, count=1)
        if tag_open.endswith("/>"):
            return tag_open[:-2] + ' %s="%s"/>' % (name, value)
        return tag_open[:-1] + ' %s="%s">' % (name, value)

    def highlighted(self, style_id):
        """Style index of `style_id` with yellow fill and red font."""
        if style_id in self._xf_map:
            return self._xf_map[style_id]
        xf = self.xfs[style_id] if style_id < len(self.xfs) else "<xf/>"
        open_end = xf.index(">") + 1
        tag_open, rest = xf[:open_end], xf[open_end:]
        font = re.search(r'\bfontId="(\d+)"', tag_open)
        font_id = self._red_font(int(font.group(1)) if font else 0)
        for name, value in (("fontId", font_id), ("fillId", self._yellow_fill()),
                            ("applyFont", 1), ("applyFill", 1)):
            tag_open = self._set_attr(tag_open, name, value)
        self.xfs.append(tag_open + rest)
        self._xf_map[style_id] = len(self.xfs) - 1
        return self._xf_map[style_id]

    def render(self):
        xml = self.xml
        # replace from the back so earlier offsets stay valid
        blocks = sorted([("fonts", self.fonts, self._fonts_span),
                         ("fills", self.fills, self._fills_span),
                         ("cellXfs", self.xfs, self._xfs_span)],
                        key=lambda b: b[2][0], reverse=True)
        for outer, items, (start, end) in blocks:
            old = xml[start:end]
            open_tag = old[:old.index(">") + 1]
            if re.search(r'\bcount="\d+"', open_tag):
                open_tag = re.sub(r'\bcount="\d+"', 'count="%d"' % len(items), open_tag, count=1)
            xml = xml[:start] + open_tag + "".join(items) + "</%s>" % outer + xml[end:]
        return xml


# --------------------------------------------------------------------------
# sheet
# --------------------------------------------------------------------------
def _new_cell(ref, style_id, text):
    space = ' xml:space="preserve"' if text != text.strip() else ""
    return '<c r="%s" s="%d" t="inlineStr"><is><t%s>%s</t></is></c>' % (
        ref, style_id, space, escape(text))


def _patch_row(row_xml, row_number, cells, styles):
    """row_xml: '<row ...>...</row>' or '<row .../>'. cells: {column letters: text}."""
    if row_xml.endswith("/>") and "</row>" not in row_xml:
        open_tag, body = row_xml[:-2] + ">", ""
    else:
        open_end = row_xml.index(">") + 1
        open_tag, body = row_xml[:open_end], row_xml[open_end:-len("</row>")]
    existing = []
    for match in _CELL.finditer(body):
        ref = _ATTR_R.search(match.group(1))
        if not ref:
            continue
        style = _ATTR_S.search(match.group(1))
        existing.append([_col_index(ref.group(1)), match.start(), match.end(),
                         int(style.group(1)) if style else 0])
    edits = []   # (start, end, text)
    for letters in sorted(cells, key=_col_index):
        column = _col_index(letters)
        ref = "%s%d" % (letters, row_number)
        hit = [e for e in existing if e[0] == column]
        if hit:
            _, start, end, style = hit[0]
            edits.append((start, end, _new_cell(ref, styles.highlighted(style), cells[letters])))
        else:
            later = [e for e in existing if e[0] > column]
            position = later[0][1] if later else len(body)
            edits.append((position, position,
                          _new_cell(ref, styles.highlighted(0), cells[letters])))
    for start, end, text in sorted(edits, key=lambda e: (e[0], e[1]), reverse=True):
        body = body[:start] + text + body[end:]
    return open_tag + body + "</row>"


def _patch_sheet(xml, cells, styles):
    by_row = {}
    for (row, letters), text in cells.items():
        by_row.setdefault(int(row), {})[letters] = text
    rows = []   # (row number, start, end)
    for match in _ROW_OPEN.finditer(xml):
        number = _ATTR_ROW.search(match.group(0))
        if not number:
            continue
        if match.group(0).endswith("/>"):
            end = match.end()
        else:
            close = xml.find("</row>", match.end())
            if close < 0:
                raise IndexWriteError("Malformed sheet XML: row without an end tag.")
            end = close + len("</row>")
        rows.append((int(number.group(1)), match.start(), end))
    located = dict((number, (start, end)) for number, start, end in rows)
    edits = []
    for number in sorted(by_row):
        if number in located:
            start, end = located[number]
            edits.append((start, end, _patch_row(xml[start:end], number, by_row[number], styles)))
        else:
            new_row = _patch_row('<row r="%d"/>' % number, number, by_row[number], styles)
            later = [r for r in rows if r[0] > number]
            if later:
                position = later[0][1]
            else:
                position = xml.find("</sheetData>")
                if position < 0:
                    empty = xml.find("<sheetData/>")
                    if empty < 0:
                        raise IndexWriteError("Malformed sheet XML: no sheetData element.")
                    edits.append((empty, empty + len("<sheetData/>"),
                                  "<sheetData>" + new_row + "</sheetData>"))
                    continue
            edits.append((position, position, new_row))
    # several new rows at one insertion point must stay in ascending order
    edits.sort(key=lambda e: (e[0], e[1]))
    out, cursor = [], 0
    for start, end, text in edits:
        out.append(xml[cursor:start])
        out.append(text)
        cursor = end
    out.append(xml[cursor:])
    return "".join(out)


def write_updated_index(source_path, target_path, sheet_name, cells):
    """Copy the workbook, writing `cells` into `sheet_name`.

    cells: {(row number, column letters): text}. Each written cell gets a
    yellow fill and red text and otherwise keeps its existing formatting.
    Returns the number of cells written.
    """
    with zipfile.ZipFile(source_path, "r") as source:
        infos = source.infolist()
        parts = dict((info.filename, source.read(info.filename)) for info in infos)
    if cells:
        sheet_part, styles_part = _find_parts(parts, sheet_name)
        styles = _Styles(parts[styles_part].decode("utf-8"))
        sheet_xml = _patch_sheet(parts[sheet_part].decode("utf-8"), cells, styles)
        parts[sheet_part] = sheet_xml.encode("utf-8")
        parts[styles_part] = styles.render().encode("utf-8")
    with zipfile.ZipFile(target_path, "w", zipfile.ZIP_DEFLATED) as target:
        for info in infos:
            clone = zipfile.ZipInfo(info.filename, info.date_time)
            clone.compress_type = info.compress_type
            clone.external_attr = info.external_attr
            clone.create_system = info.create_system
            target.writestr(clone, parts[info.filename])
    return len(cells)
