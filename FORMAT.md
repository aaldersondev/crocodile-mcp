# The Crocodile Physics 1.7 `.cyp` format

This is a reverse-engineered description. It was decoded byte by byte from files saved by
Crocodile Physics 1.7 FR (Build 613FR), and checked by generating files that the program opens
and simulates. All integers are little-endian.

## 1. Container: MFC `CArchive` object stream

The file is an MFC serialized object graph.

| Bytes | Meaning |
|---|---|
| `FF FF` + `WORD schema` + `WORD len` + class name | first use of a class (new class tag) |
| `WORD 0x8000 \| classIndex` | later object of an already-seen class |
| `00 00` | NULL: ends a list of child objects |

Classes and objects share **one index counter starting at 1**. Each new class takes an
index, then each object takes one. Link-table entries refer to objects by this index.

Schemas: `CCircuit` 2, `CSerializeHack` 3, `CPart` and every component or wire class 2,
`CDummyValue` 1, `COptoContainerList` 1, `COptoContainer` 1.

## 2. File layout

```
CCircuit (class tag)
CSerializeHack (class tag) + fixed body (bytes 0x22–0x4E, copied verbatim)
section "OTHERS"      : CString name + CPart container + items + section trailer
section "COMPONENTS"  : ...
section "WIRES"       : ...
section "PROBES"      : ...
"\x11OPTOCONTAINERLIST" + COptoContainerList ... "OPTOCONTAINER" + COptoContainer ... "NULLTREE" + 16 bytes
link table (WORDs)
trailer
```

A CString is one length byte followed by the characters (Latin-1).

A section ends with `00 00` (end of items), then 14 zero bytes, then the marker `+_@TR#^)`.

> A missing `\x11OPTOCONTAINERLIST` string makes Crocodile refuse the file with
> "Erreur d'ouverture de la simulation / Format de fichier inattendu".

## 3. Object record

```
<class tag>
<children ...> 00 00                 child objects, then NULL
int16 x1, y1, x2, y2                 bounding rectangle (canvas pixels)
WORD a
DWORD b
"TestBCM\0"                          record marker
<class-specific tail>
end marker (8 bytes)
```

End markers:

- `@:!_BM{^` ends leaf objects: `CValue`, `CText`, `CTerminal`, `CDummyValue`, `CExplode`.
- `~$+]OB@#` ends components and wires.

### Component (part) tail — 18 bytes

```
02 00
WORD  index of the first CTerminal child
DWORD number of terminals
int16 x1, y1, x2, y2   local bounding box
00 00
```

`CECapacitor` appends a **double: the stored charge Q = C·V** (coulombs). Copying a
charged capacitor's record into a smaller capacitor starts it at a huge voltage, and it
explodes at the first time step.

### Terminal (`CTerminal`) tail — 32 bytes

```
00 00
DWORD  electrical node number
WORD   flag (0 = fresh, 1 = solved, 8/9 = component destroyed)
double saved voltage (V)
double saved current (A)
8 bytes
```

The record's `b` field is the pin id. The rectangle is the pin's lead line: vertical
`(x, y1, x+1, y2)` or horizontal `(x1, y, x2, y+1)`.

### Values (`CValue`)

- Byte 14 of the tail is the display label's length. The label follows (for example `1,5k`,
  `22µF`, `24V`, `250hFE`, with a French decimal comma).
- The numeric value is a double placed just before a constant `1.0` double.
- After the `1.0`: one SI-prefix character (`' '`, `k`, `M`, `µ` = 0xB5, `n`, `p`), a CString
  unit and a WORD.

### Destroyed components

A destroyed component gains a `CExplode` child (tail = a double), and its terminals get flag 9.
Crocodile destroys electrolytics that are reverse-biased by more than about 3 V, and parts
driven past their current limits.

### Wires (`CWire`)

- Horizontal: rect `(xmin, y, xmax+1, y+1)`, `b = 1`.
- Vertical: rect `(x, ymin, x+1, ymax+1)`, `b = 0`.
- Tail: `00 00` + DWORD node. The record ends with `~$+]OB@#`.

Optional `CCrossOver` children mark wire crossings. They are not required: generated files
omit them.

## 4. Link table

After the opto block, a list of WORD object indices describes the connections. Items are
taken in object-index order:

- each terminal writes `[self, neighbour at end 1, neighbour at end 2]`;
- each wire writes `[neighbour at end 1, neighbour at end 2]`.

All item ends located at the same point form a **circular ring** ordered by object index.
Each end points to the next item in its ring. An end that touches nothing points to its own
item (for example the inner end of a terminal).

## 5. Trailer

The trailer starts with `08 00` + a WORD equal to **number of nodes + number of `VZero`
grounds**. This fits every sample seen. The rest is copied verbatim.

## 6. Open questions

- `CSerializeHack` holds `bc 10 00 00 b2 10 80 20`, probably version stamps. It is copied as is.
- The trailer word rule is empirical.
- Only these components have been decoded so far: `Resistor`, `ECapacitor`, `LED`, `NPN`,
  `VoltRail`, `VZero`. Others can be added by saving a small GUI file containing them and
  extracting the template (see `crocodile_mcp/templates.json`).
