"""Two-transistor astable multivibrator (LED flasher), 24 V, T ~ 3 s.

The capacitors start in a state the circuit really reaches (T1 on, T2 off):
starting every electrolytic at 0 V makes Crocodile's first time step
reverse-bias them beyond their 3 V limit and they "explode".
"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from crocodile_mcp.cyp import create_circuit

C = [
    dict(id="V",  type="VoltRail",   x=100, y=96,  value=24),
    dict(id="C3", type="ECapacitor", x=140, y=150, value=22e-6, initial_voltage=24),
    dict(id="G0", type="VZero",      x=124, y=210),
    dict(id="R1", type="Resistor",   x=220, y=150, value=220e3),
    dict(id="R4", type="Resistor",   x=300, y=150, value=1.5e3),
    dict(id="D1", type="LED",        x=292, y=230),
    dict(id="T1", type="NPN",        x=284, y=320, value=250),
    dict(id="C1", type="ECapacitor", x=392, y=307, value=10e-6, initial_voltage=10),
    dict(id="R2", type="Resistor",   x=500, y=150, value=220e3),
    dict(id="R5", type="Resistor",   x=600, y=150, value=1.8e3),
    dict(id="T2", type="NPN",        x=584, y=320, value=250),
    dict(id="C2", type="ECapacitor", x=660, y=270, value=10e-6, initial_voltage=23),
    dict(id="G1", type="VZero",      x=276, y=380),
    dict(id="G2", type="VZero",      x=576, y=380),
]
P = lambda *pts: {"points": [list(p) for p in pts]}
W = [
    # +24 V rail
    P((128, 100), (152, 100)), P((152, 100), (224, 100)), P((224, 100), (304, 100)),
    P((304, 100), (504, 100)), P((504, 100), (604, 100)),
    P((152, 100), (152, 130)), P((224, 100), (224, 130)), P((304, 100), (304, 130)),
    P((504, 100), (504, 130)), P((604, 100), (604, 130)),
    P((152, 194), (152, 214)),                                   # C3 -> 0 V
    P((304, 194), (304, 210)),                                   # R4 -> LED
    P((304, 274), (304, 287)), P((304, 287), (304, 300)),        # LED -> T1 collector
    P((304, 287), (404, 287)),                                   # T1 collector -> C1+
    P((404, 351), (404, 370), (504, 370), (504, 332)),           # C1- -> T2 base
    P((504, 194), (504, 332)), P((504, 332), (564, 332)),        # R2 -> T2 base
    P((604, 194), (604, 250)), P((604, 250), (604, 300)),        # R5 -> T2 collector
    P((604, 250), (672, 250)),                                   # T2 collector -> C2+
    P((672, 314), (672, 400), (224, 400), (224, 332)),           # C2- -> T1 base
    P((224, 194), (224, 332)), P((224, 332), (264, 332)),        # R1 -> T1 base
    P((304, 364), (304, 384)), P((604, 364), (604, 384)),        # emitters -> 0 V
]
if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "astable.cyp"
    print(create_circuit(out, C, W))
