"""Simplest circuit: 9 V rail -> 470 ohm -> LED -> 0 V (wires routed automatically)."""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from crocodile_mcp import create_circuit

C = [
    {"id": "V", "type": "VoltRail", "x": 100, "y": 96, "value": 9},
    {"id": "R", "type": "Resistor", "x": 200, "y": 150, "value": 470},
    {"id": "D", "type": "LED", "x": 192, "y": 240},
    {"id": "G", "type": "VZero", "x": 100, "y": 340},
]
W = [{"from": "V.out", "to": "R.top"},
     {"from": "R.bottom", "to": "D.anode"},
     {"from": "D.cathode", "to": "G.out"}]

if __name__ == "__main__":
    print(create_circuit(sys.argv[1] if len(sys.argv) > 1 else "led.cyp", C, W))
