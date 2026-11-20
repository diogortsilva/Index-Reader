"""Build the cable graph: panels and devices as nodes, cables as edges.

Every instrument row is turned into a path
    marshalling 1 -> [marshalling 2] -> [marshalling 3] -> [JB 1] -> [JB 2] -> [JB 3] -> end device
using only the sections that are populated. Each hop is one cable segment.
Segments sharing a cable ID between the same two nodes form one cable run.
"""

from __future__ import annotations

import re

from . import config
from .sizing import Proposal

STATUS_EXISTING = "EXISTING"
STATUS_INDEX = "FROM INDEX"
STATUS_NEW = "NEW ID"

KIND_PLC = "PLC PANEL"
KIND_MARSH = "MARSHALLING"
KIND_JB = "JUNCTION BOX"
KIND_MCC = "MCC"
KIND_DEVICE = "END DEVICE"
KIND_INSTRUMENT = "INSTRUMENT"
END_KINDS = (KIND_MCC, KIND_DEVICE, KIND_INSTRUMENT)

_KIND_RE = re.compile(r"(?<![A-Z])(PR|TR)(?![A-Z])")
_NUMBER_RE = re.compile(r"(?<![A-Z])(?:PR|TR)\s*\.?\s*(\d+)")


def norm_key(text):
    return " ".join(str(text).upper().split())


def parse_pair_label(text):
    """'PR.12' -> ('PR', 12); '1 TR.' -> ('TR', None); '' -> (None, None)."""
    upper = (text or "").upper()
    kind = _KIND_RE.search(upper)
    number = _NUMBER_RE.search(upper)
    return (kind.group(1) if kind else None, int(number.group(1)) if number else None)


def is_existing(cable_text):
    return config.EXISTING_KEYWORD in cable_text.upper()


def is_anonymous_existing(cable_text):
    """True for a bare 'EXISTING' with no identifier of its own."""
    rest = cable_text.upper().replace(config.EXISTING_KEYWORD, "")
    return is_existing(cable_text) and not re.sub(r"[^A-Z0-9]", "", rest)


def sanitize_for_id(label):
    text = re.sub(r"\s*/\s*", "_", label.strip())
    return re.sub(r"[\s,;]+", "-", text)


def natural_key(text):
    return [int(p) if p.isdigit() else p for p in re.split(r"(\d+)", text.upper())]


class Node(object):
    def __init__(self, key, name, kind):
        self.key = key
        self.name = name
        self.kind = kind
        self.kinds = [kind]
        self.locations = []
        self.plcs = []
        self.strips = []
        self.tags = []          # instrument tags passing through / ending here
        self.first_row = None

    @property
    def is_end(self):
        return self.kind in END_KINDS

    def _add(self, bucket, value):
        if value and value not in bucket:
            bucket.append(value)


class Segment(object):
    def __init__(self):
        self.row = None
        self.tag = ""
        self.src = ""
        self.dst = ""
        self.section = None       # config.Section whose cable column holds this cable
        self.write_field = None   # field name of that cable column
        self.cable_raw = ""
        self.cable_id = ""
        self.status = ""
        self.kind = "PR"          # PR or TR
        self.kind_source = ""     # declared | rtn | default
        self.pair_label = ""
        self.pair_number = None
        self.src_strip = ""
        self.dst_strip = ""
        self.is_last = False


class Run(object):
    """One cable ID between one source and one destination."""

    def __init__(self, cable_id, status, src, dst):
        self.cable_id = cable_id
        self.status = status
        self.src = src
        self.dst = dst
        self.segments = []
        self.proposal = None
        self.notes = []
        self.anonymous = False

    @property
    def used_pairs(self):
        return sum(1 for s in self.segments if s.kind == "PR")

    @property
    def used_triads(self):
        return sum(1 for s in self.segments if s.kind == "TR")

    @property
    def tags(self):
        return [s.tag for s in self.segments]

    def strips(self, attr):
        seen = []
        for seg in self.segments:
            value = getattr(seg, attr)
            if value and value not in seen:
                seen.append(value)
        return seen


class Signal(object):
    def __init__(self, row, record):
        self.row = row
        self.record = record
        self.tag = record["tag"]
        self.nodes = []
        self.segments = []

    @property
    def description(self):
        parts = [self.record[f] for f in ("desc1", "desc2", "desc3", "desc4")]
        return " ".join(p for p in parts if p)


class Finding(object):
    def __init__(self, level, code, message, row=None, tag="", cable=""):
        self.level = level      # WARNING | INFO
        self.code = code
        self.message = message
        self.row = row
        self.tag = tag
        self.cable = cable


class GraphResult(object):
    def __init__(self):
        self.signals = []
        self.nodes = {}          # key -> Node, in order of first appearance
        self.runs = []
        self.findings = []
        self.skipped = []        # (row, reason, details)
        self.new_cells = {}      # (row, field) -> proposed cable ID
        self.plcs = []

    def warn(self, code, message, row=None, tag="", cable="", level="WARNING"):
        self.findings.append(Finding(level, code, message, row, tag, cable))

    def node(self, name, kind, row=None):
        key = norm_key(name)
        node = self.nodes.get(key)
        if node is None:
            node = Node(key, name, kind)
            node.first_row = row
            self.nodes[key] = node
        elif kind not in node.kinds:
            node.kinds.append(kind)
            # a name used both as a panel and as an end point stays a panel
            if node.kind in END_KINDS and kind not in END_KINDS:
                node.kind = kind
        return node

    def counts(self):
        def count(*kinds):
            return sum(1 for n in self.nodes.values() if n.kind in kinds)
        return {
            "signals": len(self.signals),
            "plc_panels": count(KIND_PLC),
            "marshalling_panels": count(KIND_MARSH),
            "junction_boxes": count(KIND_JB),
            "end_points": count(*END_KINDS),
            "cable_runs": len(self.runs),
            "existing_runs": sum(1 for r in self.runs if r.status == STATUS_EXISTING),
            "index_runs": sum(1 for r in self.runs if r.status == STATUS_INDEX),
            "new_id_runs": sum(1 for r in self.runs if r.status == STATUS_NEW),
            "new_cells": len(self.new_cells),
            "warnings": sum(1 for f in self.findings if f.level == "WARNING"),
            "infos": sum(1 for f in self.findings if f.level == "INFO"),
            "skipped_rows": len(self.skipped),
        }


def _end_point(result, record, row):
    """Node where the last cable run of this signal terminates."""
    mcc, cubicle, end_tag = record["mcc"], record["cubicle"], record["end_tag"]
    if mcc and cubicle:
        name, kind = "%s / %s" % (mcc, cubicle), KIND_MCC
    elif mcc and end_tag and norm_key(end_tag) != norm_key(mcc):
        name, kind = "%s / %s" % (mcc, end_tag), KIND_MCC
    elif mcc:
        name, kind = mcc, KIND_MCC
    elif end_tag:
        name, kind = end_tag, KIND_DEVICE
    else:
        name, kind = record["tag"], KIND_INSTRUMENT
    node = result.node(name, kind, row)
    node._add(node.locations, record["end_loc"] or config.DEFAULT_END_LOCATION)
    return node


def _wiring_summary(record):
    """Text describing the wiring data on a row, or '' when there is nothing
    beyond a pre-assigned first marshalling panel (a plain spare I/O point)."""
    parts = []
    real = False
    for number, section in enumerate(config.SECTIONS):
        if record[section.tag] or record[section.cable]:
            parts.append("%s %s %s" % (section.key, record[section.tag], record[section.cable]))
        if record[section.cable] or (number > 0 and record[section.tag]):
            real = True
    for field in ("mcc", "cubicle", "end_tag"):
        if record[field]:
            parts.append(record[field])
            real = True
    if not real:
        return ""
    return " | ".join(" ".join(p.split()) for p in parts)


def build_graph(data):
    """data: loader.IndexData -> GraphResult"""
    result = GraphResult()
    seen_tags = {}
    seen_addresses = {}

    for row, record in data.rows:
        tag = record["tag"]
        summary = _wiring_summary(record)
        if not tag:
            if summary:
                result.skipped.append((row, "No instrument tag", summary))
            continue
        if record["io_type"].upper() in config.SKIP_IO_TYPES:
            result.skipped.append((row, "I/O type is %s" % record["io_type"].upper(), tag))
            continue
        tag_key = norm_key(tag)
        if tag_key in seen_tags:
            result.warn("DUPLICATE_TAG", "Instrument tag also used on row %d."
                        % seen_tags[tag_key], row, tag)
        else:
            seen_tags[tag_key] = row

        signal = Signal(row, record)

        # ---- PLC address checks ------------------------------------------
        plc, cabinet = record["plc"], record["cabinet"]
        for name in (plc, cabinet):
            if name and name not in result.plcs:
                result.plcs.append(name)
        if plc and cabinet and norm_key(plc) != norm_key(cabinet):
            result.warn("PLC_MISMATCH", "PLC column says %s but cabinet column says %s."
                        % (plc, cabinet), row, tag)
        if not (record["rack"] and record["slot"] and record["point"]):
            result.warn("NO_IO_ADDRESS", "No rack/slot/point assigned.", row, tag)
        else:
            address = (norm_key(cabinet or plc), record["rack"], record["slot"], record["point"])
            if address in seen_addresses:
                result.warn("DUPLICATE_IO_ADDRESS",
                            "Rack %s slot %s point %s is also assigned on row %d."
                            % (address[1], address[2], address[3], seen_addresses[address]),
                            row, tag)
            else:
                seen_addresses[address] = row

        # ---- populated sections, PLC side first ----------------------------
        hops = []   # (section or None, node, strip)
        for section in config.SECTIONS:
            panel = record[section.tag]
            if not panel:
                if record[section.cable] or record[section.strip]:
                    result.warn("SECTION_WITHOUT_TAG",
                                "%s has strip/cable data (%s) but no panel tag; ignored."
                                % (section.label,
                                   record[section.cable] or record[section.strip]), row, tag)
                continue
            node = result.node(panel, section.kind, row)
            if hops and hops[-1][1].key == node.key:
                result.warn("REPEATED_PANEL", "%s repeats panel %s; treated as one stop."
                            % (section.label, panel), row, tag, level="INFO")
                continue
            if not record[section.strip]:
                result.warn("NO_TERMINAL_STRIP", "%s %s has no terminal strip."
                            % (section.label, panel), row, tag, level="INFO")
            hops.append((section, node, record[section.strip]))
        if not hops:
            source = cabinet or plc
            if not source:
                result.skipped.append((row, "No marshalling, junction box or PLC cabinet", tag))
                continue
            node = result.node(source, KIND_PLC, row)
            hops.append((None, node, ""))
            result.warn("NO_SECTION", "No marshalling or junction box section populated; "
                        "the cable run starts at cabinet %s." % source, row, tag, level="INFO")
        first = hops[0][1]
        first._add(first.plcs, plc or cabinet)

        end = _end_point(result, record, row)
        stops = list(hops)
        if end.key == hops[-1][1].key:
            section = hops[-1][0]
            if section is not None and record[section.cable]:
                result.warn("CABLE_AFTER_END", "The signal ends in %s but a cable (%s) is "
                            "listed leaving it; ignored." % (end.name, record[section.cable]),
                            row, tag)
        else:
            stops.append((None, end, record["end_strip"]))

        for _, node, strip in stops:
            node._add(node.tags, tag)
            if not node.is_end:
                node._add(node.strips, strip)
            signal.nodes.append(node.key)

        # ---- one segment per hop -------------------------------------------
        for i in range(len(stops) - 1):
            section, src_node, src_strip = stops[i]
            dst_section, dst_node, dst_strip = stops[i + 1]
            seg = Segment()
            seg.row, seg.tag = row, tag
            seg.src, seg.dst = src_node.key, dst_node.key
            seg.src_strip, seg.dst_strip = src_strip, dst_strip
            seg.is_last = (i == len(stops) - 2) and len(stops) > len(hops)
            seg.section = section
            if section is not None:
                seg.write_field = section.cable if data.columns.get(section.cable) else None
                seg.cable_raw = record[section.cable]
                seg.pair_label = record[section.pair]
            declared, number = parse_pair_label(seg.pair_label)
            seg.pair_number = number
            rtn_src = record[section.rtn] if section is not None else ""
            if i + 1 < len(hops):
                rtn_dst = record[dst_section.rtn]
            else:
                rtn_dst = record["inst_sig"]
            if declared:
                seg.kind, seg.kind_source = declared, "declared"
                if declared == "PR" and (rtn_src or rtn_dst):
                    result.warn("PAIR_WITH_RTN",
                                'Pair column says "%s" but an RTN terminal is populated '
                                "(%s); sized as a pair." % (seg.pair_label, " / ".join(
                                    t for t in (rtn_src, rtn_dst) if t)),
                                row, tag, seg.cable_raw, level="INFO")
            elif rtn_src or rtn_dst:
                seg.kind, seg.kind_source = "TR", "rtn"
            else:
                seg.kind, seg.kind_source = "PR", "default"
            signal.segments.append(seg)
        result.signals.append(signal)

    _assign_cable_ids(result)
    _build_runs(result)
    return result


def _assign_cable_ids(result):
    used = set()
    for signal in result.signals:
        for seg in signal.segments:
            if seg.cable_raw:
                used.add(norm_key(seg.cable_raw))
    assigned = {}
    counter = 0
    for signal in result.signals:
        for seg in signal.segments:
            if seg.cable_raw:
                seg.cable_id = seg.cable_raw
                seg.status = STATUS_EXISTING if is_existing(seg.cable_raw) else STATUS_INDEX
                continue
            group = (seg.src, seg.dst, seg.is_last)
            if group not in assigned:
                if seg.is_last:
                    node = result.nodes[seg.dst]
                    label = seg.tag if node.kind == KIND_INSTRUMENT else node.name
                    base = config.NEW_CABLE_PREFIX + sanitize_for_id(label)
                else:
                    counter += 1
                    base = "%s%0*d" % (config.NEW_CABLE_PREFIX, config.NEW_CABLE_DIGITS, counter)
                candidate, suffix = base, 2
                while norm_key(candidate) in used:
                    candidate = "%s_%d" % (base, suffix)
                    suffix += 1
                used.add(norm_key(candidate))
                assigned[group] = candidate
            seg.cable_id = assigned[group]
            seg.status = STATUS_NEW
            if seg.write_field:
                result.new_cells[(seg.row, seg.write_field)] = seg.cable_id
            else:
                result.warn("NO_CABLE_COLUMN", "Proposed cable %s has no cable column to be "
                            "written to in the index." % seg.cable_id, seg.row, seg.tag,
                            seg.cable_id, level="INFO")


def _build_runs(result):
    runs = {}
    order = []
    for signal in result.signals:
        for seg in signal.segments:
            key = (norm_key(seg.cable_id), seg.src, seg.dst)
            run = runs.get(key)
            if run is None:
                run = Run(seg.cable_id, seg.status, seg.src, seg.dst)
                run.anonymous = is_anonymous_existing(seg.cable_id)
                runs[key] = run
                order.append(key)
            run.segments.append(seg)
    result.runs = [runs[k] for k in order]

    # same cable ID between different end points
    by_id = {}
    for run in result.runs:
        if not run.anonymous:
            by_id.setdefault(norm_key(run.cable_id), []).append(run)
    for same in by_id.values():
        if len(same) > 1:
            where = "; ".join("%s -> %s (%d)" % (result.nodes[r.src].name, result.nodes[r.dst].name,
                                                 len(r.segments)) for r in same)
            result.warn("CABLE_ID_REUSED", "Cable ID is used on %d different runs: %s. "
                        "Each run is listed and sized separately." % (len(same), where),
                        same[0].segments[0].row, "", same[0].cable_id)
            for run in same:
                run.notes.append("Cable ID also used on another run")

    for run in result.runs:
        if run.status != STATUS_EXISTING:
            run.proposal = Proposal(run.used_pairs, run.used_triads)
            if run.used_pairs and run.used_triads:
                run.notes.append("Pairs and triads under one cable ID")
                result.warn("MIXED_PAIRS_TRIADS", "Cable carries %d pair(s) and %d triad(s); "
                            "separate pair and triad cables are proposed."
                            % (run.used_pairs, run.used_triads),
                            run.segments[0].row, "", run.cable_id)
            if len(run.proposal.pair_cables) + len(run.proposal.triad_cables) > 1 and not (
                    run.used_pairs and run.used_triads):
                run.notes.append("Split into %d cables" % run.proposal.cable_count)
        if run.anonymous:
            continue
        # the same pair/triad number listed twice in one cable
        seen = {}
        for seg in run.segments:
            if seg.pair_number is None:
                continue
            slot = (seg.kind, seg.pair_number)
            if slot in seen:
                result.warn("DUPLICATE_PAIR", "%s.%d is used by both %s (row %d) and %s (row %d)."
                            % (slot[0], slot[1], seen[slot].tag, seen[slot].row, seg.tag, seg.row),
                            seg.row, seg.tag, run.cable_id)
                if "Duplicate pair number" not in run.notes:
                    run.notes.append("Duplicate pair number")
            else:
                seen[slot] = seg
        # pair numbers beyond what is proposed
        if run.proposal is not None:
            for unit, capacity in (("PR", run.proposal.pair_capacity),
                                   ("TR", run.proposal.triad_capacity)):
                numbers = [s.pair_number for s in run.segments
                           if s.pair_number is not None and s.kind == unit]
                if numbers and max(numbers) > capacity:
                    run.notes.append("Index uses %s.%d, above the proposed capacity"
                                     % (unit, max(numbers)))
                    result.warn("PAIR_NUMBER_ABOVE_SIZE", "The index references %s.%d but the "
                                "proposed capacity is %d." % (unit, max(numbers), capacity),
                                run.segments[0].row, "", run.cable_id, level="INFO")


def sorted_runs(result):
    """Schedule order: cables from the index, proposed new IDs, then existing."""
    rank = {STATUS_INDEX: 0, STATUS_NEW: 1, STATUS_EXISTING: 2}
    return sorted(result.runs, key=lambda r: (rank[r.status], natural_key(r.cable_id),
                                              r.src, r.dst))
