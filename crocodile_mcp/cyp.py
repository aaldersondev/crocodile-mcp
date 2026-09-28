"""Read and write Crocodile Physics 1.7 simulation files (.cyp).

The format is an MFC CArchive object stream. See FORMAT.md for the byte-level
description. This module only depends on the Python standard library.
"""
from __future__ import annotations

import json
import re
import struct
from dataclasses import dataclass, field
from pathlib import Path

END_LEAF = b"@:!_BM{^"   # ends CValue / CText / CTerminal records
END_PART = b"~$+]OB@#"   # ends component and wire records
SECTION = b"+_@TR#^)"    # ends a section container
TAG = b"TestBCM\x00"
ONE = struct.pack("<d", 1.0)

_TPL = json.loads((Path(__file__).with_name("templates.json")).read_text())
TEMPLATES = _TPL["components"]
SKELETON = {k: bytes.fromhex(v) for k, v in _TPL["skeleton"].items()}

SCHEMA = {"CCircuit": 2, "CSerializeHack": 3, "CPart": 2, "COptoContainerList": 1,
          "COptoContainer": 1, "CDummyValue": 1}

PIN_NAMES = {
    "Resistor": ["top", "bottom"],
    "LED": ["anode", "cathode"],
    "ECapacitor": ["plus", "minus"],
    "NPN": ["collector", "base", "emitter"],
    "VoltRail": ["out"],
    "VZero": ["out"],
}

# --------------------------------------------------------------------------- #
# Reading
# --------------------------------------------------------------------------- #


@dataclass
class Obj:
    index: int
    cls: str
    rect: tuple
    a: int
    b: int
    tail: bytes
    end: bytes
    offset: int
    children: list = field(default_factory=list)
    tail_offset: int = 0


class Reader:
    def __init__(self, data: bytes):
        self.d = data
        self.classes: dict[int, str] = {}
        self.n = 1
        self.objs: dict[int, Obj] = {}

    def w(self, p):
        return struct.unpack_from("<H", self.d, p)[0]

    def _class(self, p):
        tag = self.w(p)
        p += 2
        if tag == 0xFFFF:
            _schema, n = struct.unpack_from("<HH", self.d, p)
            p += 4
            name = self.d[p:p + n].decode("latin1")
            p += n
            self.classes[self.n] = name
            self.n += 1
        elif tag & 0x8000:
            name = self.classes[tag & 0x7FFF]
        else:
            raise ValueError(f"object back-reference {tag} at {p - 2:#x} not supported")
        oi = self.n
        self.n += 1
        return p, name, oi

    def _obj(self, p):
        off = p
        p, name, oi = self._class(p)
        kids = []
        while self.w(p) != 0:
            p, k = self._obj(p)
            kids.append(k)
        p += 2
        rect = struct.unpack_from("<4h", self.d, p)
        a, b = struct.unpack_from("<HI", self.d, p + 8)
        p += 14
        if self.d[p:p + 8] != TAG:
            raise ValueError(f"missing record marker at {p:#x}")
        p += 8
        ends = [x for x in (self.d.find(END_LEAF, p), self.d.find(END_PART, p)) if x >= 0]
        e = min(ends)
        o = Obj(oi, name, rect, a, b, self.d[p:e], self.d[e:e + 8], off, kids)
        o.tail_offset = p
        self.objs[oi] = o
        return e + 8, o

    def _cstr(self, p):
        n = self.d[p]
        return p + 1 + n, self.d[p + 1:p + 1 + n].decode("latin1")

    def parse(self):
        p, _, _ = self._class(0)          # CCircuit
        p, _, _ = self._class(p)          # CSerializeHack
        p = 0x4E
        sections = {}
        while True:
            p2, name = self._cstr(p)
            if name not in ("OTHERS", "COMPONENTS", "WIRES", "PROBES"):
                break
            p, _, _ = self._class(p2)     # CPart container
            items = []
            while self.w(p) != 0:
                p, o = self._obj(p)
                items.append(o)
            p += 2 + 14 + 8
            sections[name] = items
        self.sections = sections
        return self


def _value_of(tail: bytes):
    i = tail.rfind(ONE)
    if i < 8:
        return None
    return struct.unpack_from("<d", tail, i - 8)[0]


def _label_of(tail: bytes):
    n = tail[14]
    return tail[15:15 + n].decode("latin1")


def read_circuit(path: str | Path) -> dict:
    """Decode a .cyp file into components, wires and electrical nodes."""
    r = Reader(Path(path).read_bytes()).parse()
    comps = []
    for o in r.sections.get("COMPONENTS", []):
        c = {"index": o.index, "type": o.cls[1:], "rect": list(o.rect), "terminals": []}
        if c["type"] == "ECapacitor" and len(o.tail) >= 26:
            c["saved_charge"] = struct.unpack_from("<d", o.tail, 18)[0]
        if any(k.cls == "CExplode" for k in o.children):
            c["destroyed"] = True
        for k in o.children:
            if k.cls == "CTerminal":
                node = struct.unpack_from("<I", k.tail, 2)[0]
                v, i = struct.unpack_from("<2d", k.tail, 8)
                c["terminals"].append({"index": k.index, "pin": k.b, "rect": list(k.rect),
                                       "node": node, "saved_voltage": v, "saved_current": i})
            elif k.cls in ("CValue", "CText", "CDummyValue"):
                c["label"] = _label_of(k.tail)
                val = _value_of(k.tail)
                if val is not None and k.cls != "CText":
                    c["value"] = val
        names = PIN_NAMES.get(c["type"])
        if names and len(names) == len(c["terminals"]):
            for t, nm in zip(c["terminals"], names):
                t["name"] = nm
        comps.append(c)
    wires = []
    for o in r.sections.get("WIRES", []):
        node = struct.unpack_from("<I", o.tail, 2)[0] if len(o.tail) >= 6 else None
        x1, y1, x2, y2 = o.rect
        horiz = o.b == 1
        wires.append({"index": o.index, "from": [x1, y1],
                      "to": [x2 - 1, y1] if horiz else [x1, y2 - 1], "node": node})
    nodes: dict[int, list] = {}
    for c in comps:
        for t in c["terminals"]:
            nodes.setdefault(t["node"], []).append(f'{c["type"]}#{c["index"]}.{t.get("name", t["pin"])}')
    return {"components": comps, "wires": wires, "nodes": {str(k): v for k, v in sorted(nodes.items())},
            "classes": sorted(set(r.classes.values()))}


def reset_state(src: str | Path, dst: str | Path | None = None) -> int:
    """Zero every saved terminal voltage/current and capacitor charge so the
    simulation starts cold. Returns the number of records reset."""
    d = bytearray(Path(src).read_bytes())
    n = 0
    for o in Reader(bytes(d)).parse().sections.get("COMPONENTS", []):
        if o.cls == "CECapacitor" and len(o.tail) >= 26:
            d[o.tail_offset + 18:o.tail_offset + 26] = b"\x00" * 8
            n += 1
    for m in re.finditer(re.escape(TAG), d):
        s = m.end()
        if len(d) >= s + 24 and d[s + 6:s + 8] in (b"\x00\x00", b"\x01\x00", b"\x08\x00") \
                and struct.unpack_from("<I", d, s + 2)[0] < 10000 and d.find(END_LEAF, s) == s + 32:
            d[s + 8:s + 24] = b"\x00" * 16
            n += 1
    Path(dst or src).write_bytes(bytes(d))
    return n

# --------------------------------------------------------------------------- #
# Writing
# --------------------------------------------------------------------------- #


def fmt_value(kind: str, value: float) -> tuple[str, str]:
    """Return (label, SI-prefix character) as Crocodile displays them."""
    def num(x):
        s = f"{x:.3g}"
        return s.replace(".", ",")
    if kind == "Resistor":
        for f, p in ((1e6, "M"), (1e3, "k")):
            if value >= f:
                return num(value / f) + p, p
        return num(value), " "
    if kind == "ECapacitor":
        for f, p in ((1e-6, "\xb5"), (1e-9, "n"), (1e-12, "p")):
            if value >= f:
                return num(value / f) + p + "F", p
        return num(value / 1e-12) + "pF", "p"
    if kind == "VoltRail":
        return num(value) + "V", " "
    if kind == "NPN":
        return f"{int(round(value))}hFE", " "
    raise ValueError(kind)


def _set_value(tail: bytes, kind: str, value: float) -> bytes:
    label, prefix = fmt_value(kind, value)
    n = tail[14]
    t = tail[:14] + bytes([len(label)]) + label.encode("latin1") + tail[15 + n:]
    i = t.rfind(ONE)
    t = t[:i - 8] + struct.pack("<d", value) + t[i:]
    return t[:i + 8] + prefix.encode("latin1") + t[i + 9:]


class _Writer:
    def __init__(self):
        self.b = bytearray()
        self.cls: dict[str, int] = {}
        self.n = 1

    def obj(self, cname):
        if cname in self.cls:
            self.b += struct.pack("<H", 0x8000 | self.cls[cname])
        else:
            self.b += b"\xff\xff" + struct.pack("<HH", SCHEMA.get(cname, 2), len(cname)) + cname.encode()
            self.cls[cname] = self.n
            self.n += 1
        oi = self.n
        self.n += 1
        return oi

    def record(self, rect, a, b, tail, end):
        self.b += struct.pack("<4hHI", *rect, a, b) + TAG + tail + end

    def section(self, name):
        self.b += bytes([len(name)]) + name.encode()

    def close(self):
        self.b += b"\x00\x00" + SKELETON["section_trail"] + SECTION


def _ends(rect, horizontal):
    x1, y1, x2, y2 = rect
    return ((x1, y1), (x2 - 1, y1)) if horizontal else ((x1, y1), (x1, y2 - 1))


def pin_positions(kind: str, x: int, y: int) -> dict:
    """Outer end of each pin for a component whose body top-left is (x, y)."""
    t = TEMPLATES[kind]
    out = {}
    for name, term in zip(PIN_NAMES[kind], t["terms"]):
        r = term["rect"]
        horiz = r[3] - r[1] == 1
        e1, e2 = _ends((r[0] + x, r[1] + y, r[2] + x, r[3] + y), horiz)
        body = (x, y, x + t["part"]["rect"][2], y + t["part"]["rect"][3])
        inside = lambda p: body[0] <= p[0] <= body[2] and body[1] <= p[1] <= body[3]
        out[name] = list(e2 if inside(e1) else e1)
    return out


def create_circuit(path: str | Path, components: list[dict], wires: list[dict]) -> dict:
    """Write a new .cyp file.

    components: [{"id": "R1", "type": "Resistor", "x": 700, "y": 360, "value": 470}, ...]
      ECapacitor also accepts "initial_voltage" (V, default 0 = discharged).
      x, y = top-left corner of the component body (canvas units, 1 unit = 1 pixel at zoom 1).
    wires: each item is either {"points": [[x, y], [x, y], ...]} (axis-aligned polyline) or
      {"from": "R1.bottom", "to": "D1.anode"} (routed vertically first, then horizontally,
      like Crocodile's own wire tool).
    """
    placed = {}
    for c in components:
        if c["type"] not in TEMPLATES:
            raise ValueError(f'unsupported type {c["type"]}; supported: {sorted(TEMPLATES)}')
        placed[c["id"]] = c

    segs = []
    for w in wires:
        if "points" in w:
            pts = [tuple(p) for p in w["points"]]
        else:
            (ca, pa), (cb, pb) = (s.split(".") for s in (w["from"], w["to"]))
            A = tuple(pin_positions(placed[ca]["type"], placed[ca]["x"], placed[ca]["y"])[pa])
            B = tuple(pin_positions(placed[cb]["type"], placed[cb]["x"], placed[cb]["y"])[pb])
            pts = [A, (A[0], B[1]), B]
        for p, q in zip(pts, pts[1:]):
            if p == q:
                continue
            if p[0] != q[0] and p[1] != q[1]:
                raise ValueError(f"wire segment {p}->{q} is not horizontal or vertical")
            segs.append((p, q))

    wr = _Writer()
    wr.obj("CCircuit")
    wr.obj("CSerializeHack")
    wr.b += SKELETON["hack_body"]
    wr.section("OTHERS"); wr.obj("CPart"); wr.close()
    wr.section("COMPONENTS"); wr.obj("CPart")

    items = {}      # obj index -> (kind, ends)
    term_nodes_pos = []   # (obj index, tail offset of node field in wr.b)
    part_info = []
    for c in components:
        kind = c["type"]
        t = TEMPLATES[kind]
        x, y = c["x"], c["y"]
        mv = lambda r: [r[0] + x, r[1] + y, r[2] + x, r[3] + y]
        wr.obj(t["cls"])
        for ch in t["children"]:
            tail = bytes.fromhex(ch["tail"])
            if ch["cls"] != "CText" and "value" in c:
                tail = _set_value(tail, kind, float(c["value"]))
            wr.obj(ch["cls"])
            wr.b += b"\x00\x00"
            wr.record(mv(ch["rect"]), ch["a"], ch["b"], tail, bytes.fromhex(ch["end"]))
        first = None
        for term in t["terms"]:
            oi = wr.obj("CTerminal")
            first = first or oi
            r = mv(term["rect"])
            tail = bytearray(bytes.fromhex(term["tail"]))
            tail[6:8] = b"\x00\x00"
            tail[8:24] = b"\x00" * 16
            wr.b += b"\x00\x00"
            start = len(wr.b) + 14 + 8
            wr.record(r, term["a"], term["b"], bytes(tail), bytes.fromhex(term["end"]))
            term_nodes_pos.append((oi, start + 2))
            items[oi] = ("T", _ends(r, r[3] - r[1] == 1))
        p = t["part"]
        tail = bytearray(bytes.fromhex(p["tail"]))
        tail[2:4] = struct.pack("<H", first)
        if kind == "ECapacitor":
            # stored charge Q = C * V0 (Crocodile saves it after the bounding box)
            C = float(c.get("value", 22e-6))
            struct.pack_into("<d", tail, 18, C * float(c.get("initial_voltage", 0.0)))
        wr.b += b"\x00\x00"
        wr.record(mv(p["rect"]), p["a"], p["b"], bytes(tail), bytes.fromhex(p["end"]))
        part_info.append((c["id"], kind))
    wr.close()

    wr.section("WIRES"); wr.obj("CPart")
    wire_nodes_pos = []
    for (p, q) in segs:
        oi = wr.obj("CWire")
        horiz = p[1] == q[1]
        if horiz:
            rect = (min(p[0], q[0]), p[1], max(p[0], q[0]) + 1, p[1] + 1)
        else:
            rect = (p[0], min(p[1], q[1]), p[0] + 1, max(p[1], q[1]) + 1)
        wr.b += b"\x00\x00"
        start = len(wr.b) + 14 + 8
        wr.record(rect, 0, 1 if horiz else 0, b"\x00\x00" + struct.pack("<I", 0), END_PART)
        wire_nodes_pos.append((oi, start + 2))
        items[oi] = ("W", _ends(rect, horiz))
    wr.close()
    wr.section("PROBES"); wr.obj("CPart"); wr.close()
    wr.b += SKELETON["opto_block"]

    # connection rings: all item ends sharing a point form a circular list
    at = {}
    for oi in sorted(items):
        for k, pt in enumerate(items[oi][1]):
            at.setdefault(pt, []).append((oi, k))
    link = {}
    for pt, lst in at.items():
        for j, (oi, k) in enumerate(lst):
            link[(oi, k)] = lst[(j + 1) % len(lst)][0]
    # electrical nodes (union-find over shared points)
    parent = {oi: oi for oi in items}
    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a
    for lst in at.values():
        for (oi, _), (oj, _) in zip(lst, lst[1:]):
            parent[find(oi)] = find(oj)
    node_id = {}
    for oi, _ in term_nodes_pos + wire_nodes_pos:
        node_id.setdefault(find(oi), len(node_id) + 1)
    for oi, pos in term_nodes_pos + wire_nodes_pos:
        struct.pack_into("<I", wr.b, pos, node_id[find(oi)])

    words = []
    for oi in sorted(items):
        if items[oi][0] == "T":
            words.append(oi)
        words += [link[(oi, 0)], link[(oi, 1)]]
    wr.b += struct.pack(f"<{len(words)}H", *words)
    n_ground = sum(1 for _, k in part_info if k == "VZero")
    tr = bytearray(SKELETON["trailer"])
    struct.pack_into("<H", tr, 2, len(node_id) + n_ground)
    wr.b += tr
    Path(path).write_bytes(bytes(wr.b))

    dangling = [f"{pt}" for pt, lst in at.items() if len(lst) == 1 and items[lst[0][0]][0] == "W"]
    return {"path": str(path), "bytes": len(wr.b), "components": len(components),
            "wires": len(segs), "nodes": len(node_id), "unconnected_wire_ends": dangling}
