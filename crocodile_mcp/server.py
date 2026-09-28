"""MCP server exposing the .cyp reader/writer as tools.

Run with:  crocodile-mcp            (stdio transport)
or:        python -m crocodile_mcp.server
"""
from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from . import cyp

mcp = FastMCP(
    "crocodile-physics",
    instructions=(
        "Read and generate Crocodile Physics 1.7 simulation files (.cyp) without the GUI. "
        "Call list_component_types first to get pin names and sizes, then create_circuit. "
        "Coordinates are canvas pixels at zoom 1; (x, y) is the top-left of a component body. "
        "Wires must be horizontal/vertical polylines whose ends land exactly on pin ends or on "
        "other wire ends. Give electrolytic capacitors in oscillators an initial_voltage that "
        "the circuit really reaches, otherwise Crocodile may reverse-bias and destroy them."
    ),
)


@mcp.tool()
def list_component_types() -> dict:
    """Supported component types with their pin names, body size and value unit."""
    units = {"Resistor": "ohm", "ECapacitor": "farad", "VoltRail": "volt", "NPN": "hFE (gain)"}
    out = {}
    for kind, t in cyp.TEMPLATES.items():
        r = t["part"]["rect"]
        out[kind] = {
            "pins": cyp.PIN_NAMES[kind],
            "body_size": [r[2] - r[0], r[3] - r[1]],
            "pin_ends_when_placed_at_0_0": cyp.pin_positions(kind, 0, 0),
            "value_unit": units.get(kind),
        }
    return out


@mcp.tool()
def pin_positions(component_type: str, x: int, y: int) -> dict:
    """Canvas coordinates of each pin end for a component whose body top-left is (x, y)."""
    return cyp.pin_positions(component_type, x, y)


@mcp.tool()
def create_circuit(path: str, components: list[dict], wires: list[dict]) -> dict:
    """Write a new .cyp file that Crocodile Physics 1.7 opens directly.

    components: [{"id": "R1", "type": "Resistor", "x": 220, "y": 150, "value": 220000}, ...]
      types: Resistor, ECapacitor (value in F, optional initial_voltage), LED,
      NPN (value = hFE), VoltRail (value in V), VZero (0 V ground).
    wires: [{"points": [[x, y], [x, y], ...]}]  axis-aligned polyline, or
           [{"from": "R1.bottom", "to": "D1.anode"}]  routed vertically then horizontally.
    Returns size, node count and any wire end that touches nothing.
    """
    return cyp.create_circuit(path, components, wires)


@mcp.tool()
def read_circuit(path: str) -> dict:
    """Decode a .cyp file: components (values, labels, saved voltages/currents,
    capacitor charge, destroyed flag), wires and the electrical node map."""
    return cyp.read_circuit(path)


@mcp.tool()
def reset_state(path: str, output_path: str | None = None) -> dict:
    """Zero saved voltages, currents and capacitor charges so the simulation restarts cold."""
    n = cyp.reset_state(path, output_path)
    return {"path": output_path or path, "records_reset": n}


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
