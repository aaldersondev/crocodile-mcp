"""Tests: python -m pytest tests"""
from pathlib import Path
import struct

from crocodile_mcp import cyp

DATA = Path(__file__).parent / "data"
EXAMPLES = Path(__file__).parents[1] / "examples"


def rebuild(src, dst):
    """Re-create a GUI-made circuit through the public API."""
    c = cyp.read_circuit(src)
    comps = []
    for k in c["components"]:
        d = {"id": f'P{k["index"]}', "type": k["type"], "x": k["rect"][0], "y": k["rect"][1]}
        if "value" in k and k["type"] != "VZero":
            d["value"] = k["value"]
        comps.append(d)
    wires = [{"points": [w["from"], w["to"]]} for w in c["wires"]]
    return cyp.create_circuit(dst, comps, wires)


def partition(path):
    return sorted(sorted(p.split("#", 1)[0] + "." + p.split(".")[-1] for p in v)
                  for v in cyp.read_circuit(path)["nodes"].values())


def structure(path):
    r = cyp.Reader(Path(path).read_bytes()).parse()
    out = []
    for sec, items in r.sections.items():
        for o in items:
            out.append((sec, o.cls, o.rect, o.a, o.b, [(k.cls, k.rect, k.a, k.b) for k in o.children]))
    return out


def test_rebuild_matches_gui_file(tmp_path):
    ref = DATA / "lumiere_gui.cyp"
    out = tmp_path / "same.cyp"
    info = rebuild(ref, out)
    assert info["unconnected_wire_ends"] == []
    a, b = ref.read_bytes(), out.read_bytes()
    assert len(a) == len(b)
    assert structure(ref) == structure(out)
    assert partition(ref) == partition(out)
    # link table + trailer are identical byte for byte
    i = a.find(b"NULLTREE") + 24
    assert a[i:] == b[i:]


def test_astable_example(tmp_path):
    import runpy
    ns = runpy.run_path(str(EXAMPLES / "astable.py"))
    out = tmp_path / "astable.cyp"
    info = cyp.create_circuit(out, ns["C"], ns["W"])
    assert info["nodes"] == 9 and info["unconnected_wire_ends"] == []
    nodes = [set(v) for v in cyp.read_circuit(out)["nodes"].values()]
    names = [{p.split("#")[0] + "." + p.split(".")[-1] for p in n} for n in nodes]
    assert {"LED.cathode", "NPN.collector", "ECapacitor.plus"} in names
    caps = [c for c in cyp.read_circuit(out)["components"] if c["type"] == "ECapacitor"]
    assert abs(caps[1]["saved_charge"] - 10e-6 * 10) < 1e-12


def test_values_and_labels(tmp_path):
    out = tmp_path / "v.cyp"
    cyp.create_circuit(out, [
        {"id": "R", "type": "Resistor", "x": 100, "y": 100, "value": 1500},
        {"id": "C", "type": "ECapacitor", "x": 200, "y": 100, "value": 22e-6},
        {"id": "V", "type": "VoltRail", "x": 300, "y": 100, "value": 12},
    ], [])
    labels = {c["type"]: (c["label"], c["value"]) for c in cyp.read_circuit(out)["components"]}
    assert labels["Resistor"] == ("1,5k", 1500)
    assert labels["ECapacitor"][0] == "22µF"
    assert labels["VoltRail"] == ("12V", 12)


def test_reset_state(tmp_path):
    out = tmp_path / "r.cyp"
    n = cyp.reset_state(DATA / "lumiere_gui.cyp", out)
    assert n > 0
    for c in cyp.read_circuit(out)["components"]:
        for t in c["terminals"]:
            assert t["saved_voltage"] == 0 and t["saved_current"] == 0
