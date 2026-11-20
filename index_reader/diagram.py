"""Block diagram of the cable graph, drawn as a standalone SVG (plus an HTML viewer).

Layout: panels in columns from the PLC side (left) to the field (right), end
devices in the last column. Every node hangs under the first panel that feeds
it, so the picture reads as a tree; additional feeds are drawn as extra lines.
No external libraries or fonts are needed and nothing is loaded from a network.
"""

from __future__ import annotations

import os
from xml.sax.saxutils import escape, quoteattr

from . import config
from .graph import (KIND_INSTRUMENT, KIND_JB, KIND_MARSH, KIND_MCC, KIND_PLC, KIND_DEVICE,
                    STATUS_EXISTING, STATUS_INDEX, STATUS_NEW)

LANE = 22            # vertical space of one end-device line
PANEL_W = 210
PANEL_H = 44
DEVICE_W = 340
LABEL_W = 330        # room for the cable label on the last, straight part of a line
GAP = 90             # room for the curved part of a line
MARGIN = 30
HEADER_H = 118
LABEL_LINE = 12

FILL = {
    KIND_PLC: "#cfe2f3", KIND_MARSH: "#d9ead3", KIND_JB: "#fff2cc",
    KIND_MCC: "#f9dcc4", KIND_DEVICE: "#ececec", KIND_INSTRUMENT: "#ffffff",
}
STROKE = {STATUS_INDEX: "#1f4e79", STATUS_NEW: "#c00000", STATUS_EXISTING: "#666666"}
STATUS_TEXT = {STATUS_INDEX: "cable ID from the index", STATUS_NEW: "new cable ID proposed",
               STATUS_EXISTING: "existing cable (not sized)"}


class _Box(object):
    def __init__(self, node):
        self.node = node
        self.layer = 0
        self.lanes = 1
        self.top = 0       # first lane index
        self.x = 0
        self.y = 0         # pixel centre
        self.w = PANEL_W
        self.h = PANEL_H
        self.incoming = []  # runs, in drawing order


def _run_label(run):
    if run.status == STATUS_EXISTING:
        size = "not sized"
    else:
        size = run.proposal.text
    used = []
    if run.used_pairs:
        used.append("%d PR" % run.used_pairs)
    if run.used_triads:
        used.append("%d TR" % run.used_triads)
    return "%s  |  %s  |  %s used" % (run.cable_id, size, " + ".join(used))


def _layout(result):
    boxes = dict((key, _Box(node)) for key, node in result.nodes.items())
    children, parents = {}, {}
    for run in result.runs:
        if run.dst not in children.setdefault(run.src, []):
            children[run.src].append(run.dst)
        if run.src not in parents.setdefault(run.dst, []):
            parents[run.dst].append(run.src)
        boxes[run.dst].incoming.append(run)

    # ---- columns: longest path among panels, end points in the last column
    depth, visiting = {}, set()

    def panel_depth(key):
        if key in depth:
            return depth[key]
        if key in visiting:          # circular reference in the data; break it here
            return 0
        visiting.add(key)
        best = 0
        for parent in parents.get(key, []):
            if not boxes[parent].node.is_end:
                best = max(best, panel_depth(parent) + 1)
        visiting.discard(key)
        depth[key] = best
        return best

    panel_keys = [k for k, b in boxes.items() if not b.node.is_end]
    last_panel_layer = max([panel_depth(k) for k in panel_keys] or [0])
    for key, box in boxes.items():
        box.layer = last_panel_layer + 1 if box.node.is_end else depth.get(key, 0)

    # ---- rows: depth-first under the first parent
    primary = dict((key, feeders[0]) for key, feeders in parents.items())
    placed = set()
    cursor = [0]

    def min_lanes(box):
        if box.node.is_end:
            return max(1, len(box.incoming))
        lines = max(1, len(box.incoming))
        need = 2 * (lines * LABEL_LINE + 8)
        return max(2, -(-need // LANE), -(-(PANEL_H + 10) // LANE))

    def place(key):
        if key in placed:
            return
        placed.add(key)
        box = boxes[key]
        start = cursor[0]
        own = [c for c in children.get(key, []) if primary.get(c) == key and c not in placed]
        panels = [c for c in own if not boxes[c].node.is_end]
        ends = [c for c in own if boxes[c].node.is_end]
        for child in panels + ends:
            place(child)
        if cursor[0] - start < min_lanes(box):
            cursor[0] = start + min_lanes(box)
        box.top = start
        box.lanes = cursor[0] - start

    roots = [k for k in boxes if k not in parents]
    for key in roots:
        place(key)
    for key in boxes:          # anything left (only possible with circular data)
        place(key)

    # ---- pixels
    for box in boxes.values():
        if box.node.is_end:
            box.w = DEVICE_W
            box.h = box.lanes * LANE - 6
            box.x = MARGIN + (last_panel_layer + 1) * (PANEL_W + GAP + LABEL_W)
        else:
            box.x = MARGIN + box.layer * (PANEL_W + GAP + LABEL_W)
        box.y = HEADER_H + box.top * LANE + box.lanes * LANE / 2.0
    width = MARGIN * 2 + (last_panel_layer + 1) * (PANEL_W + GAP + LABEL_W) + DEVICE_W
    height = HEADER_H + cursor[0] * LANE + MARGIN
    return boxes, width, height


def _fmt(value):
    text = "%.1f" % value
    return text[:-2] if text.endswith(".0") else text


def _node_title(result, box):
    node = box.node
    lines = ["%s (%s)" % (node.name, node.kind)]
    if node.is_end and node.locations:
        lines.append("Location: " + ", ".join(node.locations))
    if node.strips:
        lines.append("Strips: " + ", ".join(node.strips))
    lines.append("%d signal(s):" % len(node.tags))
    lines.extend(node.tags)
    return "\n".join(lines)


def build_svg(result, title, subtitle=""):
    boxes, width, height = _layout(result)
    out = []
    add = out.append
    add('<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" viewBox="0 0 %d %d" '
        'font-family="Segoe UI, Arial, Helvetica, sans-serif" font-size="11">'
        % (width, height, width, height))
    add('<rect x="0" y="0" width="%d" height="%d" fill="#ffffff"/>' % (width, height))

    # ---- header and legend
    add('<text x="%d" y="30" font-size="18" font-weight="bold">%s</text>' % (MARGIN, escape(title)))
    if subtitle:
        add('<text x="%d" y="48" fill="#555555">%s</text>' % (MARGIN, escape(subtitle)))
    counts = result.counts()
    add('<text x="%d" y="64" fill="#555555">%s</text>' % (MARGIN, escape(
        "%d signals  |  %d panels and junction boxes  |  %d end points  |  %d cable runs "
        "(%d from the index, %d with a new ID, %d existing)"
        % (counts["signals"],
           counts["plc_panels"] + counts["marshalling_panels"] + counts["junction_boxes"],
           counts["end_points"], counts["cable_runs"], counts["index_runs"],
           counts["new_id_runs"], counts["existing_runs"]))))
    x = MARGIN
    for status in (STATUS_INDEX, STATUS_NEW, STATUS_EXISTING):
        dash = ' stroke-dasharray="5 4"' if status == STATUS_EXISTING else ""
        add('<line x1="%d" y1="84" x2="%d" y2="84" stroke="%s" stroke-width="2"%s/>'
            % (x, x + 34, STROKE[status], dash))
        add('<text x="%d" y="88">%s</text>' % (x + 40, escape(STATUS_TEXT[status])))
        x += 60 + 7 * len(STATUS_TEXT[status])
    x = MARGIN
    for kind in (KIND_PLC, KIND_MARSH, KIND_JB, KIND_MCC, KIND_DEVICE, KIND_INSTRUMENT):
        add('<rect x="%d" y="97" width="16" height="12" rx="2" fill="%s" stroke="#333333"/>'
            % (x, FILL[kind]))
        label = kind.title() if kind != KIND_PLC else "PLC / marshalling 1 panel"
        if kind == KIND_MCC:
            label = "MCC"
        add('<text x="%d" y="107">%s</text>' % (x + 22, escape(label)))
        x += 46 + 7 * len(label)

    # ---- cables (drawn first so boxes sit on top)
    add('<g fill="none" stroke-width="1.4">')
    labels = []
    for key, box in boxes.items():
        runs = box.incoming
        if not runs:
            continue
        left = box.x
        if box.node.is_end:
            for lane, run in enumerate(runs):
                y = HEADER_H + (box.top + lane) * LANE + LANE / 2.0
                labels.append((left - LABEL_W + 6, y - 4, run, None))
                _edge(add, boxes[run.src], left, y, run.status)
        else:
            # one line per feeding panel, labels stacked above it
            feeders = []
            for run in runs:
                if run.src not in feeders:
                    feeders.append(run.src)
            count = len(runs)
            for position, run in enumerate(runs):
                y = box.y - 5 - (count - 1 - position) * LABEL_LINE
                prefix = None
                if len(feeders) > 1:
                    prefix = boxes[run.src].node.name
                labels.append((left - LABEL_W + 6, y, run, prefix))
            for feeder in feeders:
                statuses = [r.status for r in runs if r.src == feeder]
                status = statuses[0] if len(set(statuses)) == 1 else STATUS_INDEX
                _edge(add, boxes[feeder], left, box.y, status)
    add('</g>')

    add('<g font-family="Consolas, Menlo, DejaVu Sans Mono, monospace" font-size="10">')
    for x, y, run, prefix in labels:
        text = _run_label(run)
        if prefix:
            text = "from %s: %s" % (prefix, text)
        add('<text x="%s" y="%s" fill="%s">%s</text>' % (_fmt(x), _fmt(y), STROKE[run.status],
                                                        escape(text)))
    add('</g>')

    # ---- nodes
    for key, box in boxes.items():
        node = box.node
        top = box.y - box.h / 2.0
        add('<g class="node" data-name=%s>' % quoteattr(node.name.upper()))
        add('<title>%s</title>' % escape(_node_title(result, box)))
        add('<rect x="%s" y="%s" width="%d" height="%s" rx="4" fill="%s" stroke="#333333"/>'
            % (_fmt(box.x), _fmt(top), box.w, _fmt(box.h), FILL[node.kind]))
        if node.is_end:
            location = ", ".join(node.locations)
            if node.kind == KIND_INSTRUMENT:
                detail = location
            else:
                detail = "%d signal%s, %s" % (len(node.tags), "" if len(node.tags) == 1 else "s",
                                              location)
            add('<text x="%s" y="%s" font-weight="bold">%s</text>'
                % (_fmt(box.x + 7), _fmt(box.y + 4), escape(_clip(node.name, 38))))
            add('<text x="%s" y="%s" text-anchor="end" fill="#555555" font-size="10">%s</text>'
                % (_fmt(box.x + box.w - 7), _fmt(box.y + 4), escape(_clip(detail, 22))))
        else:
            add('<text x="%s" y="%s" font-weight="bold" font-size="12">%s</text>'
                % (_fmt(box.x + 8), _fmt(box.y - 3), escape(_clip(node.name, 28))))
            detail = "%s, %d signal%s" % (node.kind.title() if node.kind != KIND_PLC
                                          else "PLC panel", len(node.tags),
                                          "" if len(node.tags) == 1 else "s")
            add('<text x="%s" y="%s" fill="#555555" font-size="10">%s</text>'
                % (_fmt(box.x + 8), _fmt(box.y + 12), escape(detail)))
        add('</g>')
    add('</svg>')
    return "\n".join(out) + "\n"


def _clip(text, limit):
    return text if len(text) <= limit else text[:limit - 1] + "…"


def _edge(add, source, left, y, status):
    """Curve from the right side of `source` to a straight run ending at (left, y)."""
    x1 = source.x + source.w
    y1 = source.y
    # all the turning happens in the gap right after the source; from there the
    # line runs straight, in a lane that belongs to the destination alone
    x2 = x1 + GAP
    bend = GAP / 2.0
    dash = ' stroke-dasharray="5 4"' if status == STATUS_EXISTING else ""
    add('<path d="M%s,%s C%s,%s %s,%s %s,%s H%s" stroke="%s"%s/>'
        % (_fmt(x1), _fmt(y1), _fmt(x1 + bend), _fmt(y1), _fmt(x2 - bend), _fmt(y), _fmt(x2),
           _fmt(y), _fmt(left), STROKE[status], dash))


_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>%(title)s</title>
<style>
  html, body { margin: 0; height: 100%%; font-family: "Segoe UI", Arial, sans-serif; }
  #bar { position: fixed; top: 0; left: 0; right: 0; height: 40px; background: #1f4e79;
         color: #fff; display: flex; align-items: center; gap: 8px; padding: 0 12px;
         z-index: 2; font-size: 13px; }
  #bar button, #bar input { font: inherit; padding: 3px 8px; }
  #view { position: absolute; top: 40px; left: 0; right: 0; bottom: 0; overflow: auto;
          background: #f3f3f3; }
  #canvas { transform-origin: 0 0; }
  .hit rect { stroke: #c00000; stroke-width: 3; }
</style>
</head>
<body>
<div id="bar">
  <strong>%(title)s</strong>
  <button id="out" title="Zoom out">&minus;</button>
  <button id="in" title="Zoom in">+</button>
  <button id="fit">Fit width</button>
  <button id="one">100%%</button>
  <input id="find" placeholder="Find panel, device or tag" size="28">
  <span id="hits"></span>
</div>
<div id="view"><div id="canvas">
%(svg)s</div></div>
<script>
(function () {
  var view = document.getElementById('view'), canvas = document.getElementById('canvas');
  var svg = canvas.querySelector('svg'), zoom = 1;
  var w = svg.viewBox.baseVal.width, h = svg.viewBox.baseVal.height;
  function apply() { svg.setAttribute('width', w * zoom); svg.setAttribute('height', h * zoom); }
  document.getElementById('in').onclick = function () { zoom = Math.min(4, zoom * 1.25); apply(); };
  document.getElementById('out').onclick = function () { zoom = Math.max(0.1, zoom / 1.25); apply(); };
  document.getElementById('one').onclick = function () { zoom = 1; apply(); };
  document.getElementById('fit').onclick = function () { zoom = (view.clientWidth - 20) / w; apply(); };
  document.getElementById('find').oninput = function () {
    var q = this.value.trim().toUpperCase(), nodes = svg.querySelectorAll('g.node'), n = 0, first = null;
    for (var i = 0; i < nodes.length; i++) {
      var t = nodes[i].querySelector('title').textContent.toUpperCase();
      var hit = q.length > 1 && t.indexOf(q) >= 0;
      nodes[i].classList.toggle('hit', hit);
      if (hit) { n++; if (!first) first = nodes[i]; }
    }
    document.getElementById('hits').textContent = q.length > 1 ? n + ' match' + (n === 1 ? '' : 'es') : '';
    if (first) first.scrollIntoView({block: 'center', inline: 'center'});
  };
})();
</script>
</body>
</html>
"""


def write_diagram(result, data, svg_path, html_path=None):
    name = os.path.basename(data.path)
    title = "Cable block diagram"
    subtitle = "%s  |  sheet %s  |  Index-Reader %s" % (name, data.sheet, config.VERSION)
    svg = build_svg(result, title, subtitle)
    with open(svg_path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write('<?xml version="1.0" encoding="UTF-8"?>\n')
        handle.write(svg)
    if html_path:
        with open(html_path, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(_HTML % {"title": escape(title + " - " + name), "svg": svg})
    return svg_path
