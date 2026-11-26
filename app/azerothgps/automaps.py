"""Auto maps where the game has none (item 115, Kooki3z 2026-11-26): caves, tunnels and building insides drawn from
their walkable cells, floor by floor (Data/AutoMaps.lua, `agps auto-maps [--write]`).

This client ships no map of its own for caves and buildings: their map is the models' minimap art (Data/Interiors.lua,
G.CaveArt, G.LayoutInterior). Some models have none: the animal dens, many tunnels and mines, the night elves' and the
tauren's buildings. For those (the caves of Data/Caves.lua and the buildings of Data/Indoors.lua with no art, as the
addon looks it up: G.InteriorAt's CAVE_ART_YD), each model's walkable floors (walknet.build: the floors reached on foot
from the ground at its mouths or doors; layers.split: each floor a surface of its own, one voxel per column) grouped
into map floors: a surface joins the floor nearest it in height that it doesn't lie over or under, else starts a new
one. Each floor is its cells as rectangles (runs along the rows merged down), packed two characters a number.

The ground taken in at a mouth or a door (the terrain, drawn anyway) and, in a building, a roof (a floor with no
model over most of it: a tent's canvas reached up its side) are left out.
"""

from __future__ import annotations

import math
import re
from collections import defaultdict
from pathlib import Path

import numpy as np

from . import caves as C
from . import indoors as IN
from . import layers
from . import walknet
from .paths import ADDON_DIR

FILE = ADDON_DIR / "Data" / "AutoMaps.lua"
DATA = ADDON_DIR / "Data"
CELL = walknet.CELL
MIN_MAP_CELLS = 30  # cells: a map smaller than this is left out (an animal's den on the terrain: its floor is the land)
MIN_FLOOR, MIN_FLOOR_SHARE = 20, 0.1  # cells, share of the map's: a smaller floor is left out (a speck over another)
MIN_SURFACE = 8  # cells: smaller bits of floor are left out (a step's edge, a ledge's corner, a crate's top)
STACK_SHARE = 0.05  # a surface lying over or under more than this share of a floor's cells (or its own) is another floor
FLOOR_PAD_LO, FLOOR_PAD_HI = 1.0, 4.0  # yards under the lowest and over the highest cell of a floor: its band
ROOF_Z = 1.5  # (a building's floor cell is covered by a face more than this over it, within ROOF_REACH)
ROOF_REACH = 20.0
ROOF_SHARE = 0.5  # a building's floor with a face over less than this share of its cells is a roof
ART_YD = 1.0  # G.CAVE_ART_YD
ALPHABET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz-_"


def _lua_rows(text: str, start: str) -> str:
    i = text.index(start)
    j = text.index("\n}", i)
    return text[i:j]


def interiors_placed(text: str | None = None) -> dict:
    """Data/Interiors.lua's placements with art: {cont: [(wmo, x, y, minX, minY, maxX, maxY)]}."""
    text = text or (DATA / "Interiors.lua").read_text(encoding="utf-8")
    wmos = {int(m) for m in re.findall(r"^  \[(\d+)\] = \{ groups", text, re.M)}
    out: dict = defaultdict(list)
    cur = None
    for line in text[text.index("ns.Interiors = {"):].splitlines():
        m = re.match(r"  \[(\d+)\] = \{", line)
        if m:
            cur = int(m.group(1))
            continue
        m = re.match(r"\s+\{(\d+),([-\d.]+),([-\d.]+),[-\d.]+,[-\d.]+,([-\d.]+),([-\d.]+),([-\d.]+),([-\d.]+)\}", line)
        if m and cur is not None and int(m.group(1)) in wmos:
            out[cur].append((int(m.group(1)),) + tuple(float(v) for v in m.groups()[1:]))
    return out


def caves_without_art(caves_text: str | None = None, placed: dict | None = None) -> list:
    """The caves of Data/Caves.lua whose model has no art where the addon looks (G.CaveArt nil):
    [(cont, key, name, x, y)]."""
    caves_text = caves_text or (DATA / "Caves.lua").read_text(encoding="utf-8")
    placed = placed if placed is not None else interiors_placed()
    out = []
    for cont in (0, 1):
        rows = re.findall(r'\{ "([^"]*)", "(cave\d+)", ([-\d.]+), ([-\d.]+),',
                          _lua_rows(caves_text, f"ns.Caves[{cont}] = {{"))
        for name, key, x, y in rows:
            x, y = float(x), float(y)
            if not any(abs(p[1] - x) <= ART_YD and abs(p[2] - y) <= ART_YD for p in placed.get(cont, ())):
                out.append((cont, key, name, x, y))
    return out


def indoor_buildings(indoors_text: str | None = None) -> list:
    """The buildings of Data/Indoors.lua: [(cont, name, x, y, r)]."""
    indoors_text = indoors_text or (DATA / "Indoors.lua").read_text(encoding="utf-8")
    out = []
    for cont in (0, 1):
        for name, x, y, r in re.findall(r'\{ "([^"]*)", x = ([-\d]+), y = ([-\d]+), r = ([\d]+)',
                                        _lua_rows(indoors_text, f"ns.Indoors[{cont}] = {{")):
            out.append((cont, name, float(x), float(y), float(r)))
    return out


def has_art(placed: dict, cont: int, wmo: int, x: float, y: float) -> bool:
    """Whether the model `wmo` placed at (x, y) has minimap art (an ns.Interiors row there, as G.InteriorAt finds)."""
    return any(p[0] == wmo and abs(p[1] - x) <= ART_YD and abs(p[2] - y) <= ART_YD for p in placed.get(cont, ()))


def surfaces(u: dict, keep: np.ndarray) -> list:
    """The walkable surfaces of walk data `u` (walknet.build's) on cells `keep` (H x W): [(rows, cols, heights)],
    each a layer of layers.split (one voxel per column), MIN_SURFACE cells or more."""
    f = layers.floors(u) & keep[None]
    layer, sizes, _contacts = layers.split(f, (), log=lambda *a: None)
    b, r, c = np.nonzero(layer >= 0)
    lid = layer[b, r, c]
    order = np.argsort(lid, kind="stable")
    b, r, c, lid = b[order], r[order], c[order], lid[order]
    cuts = np.flatnonzero(np.diff(lid)) + 1
    out = []
    for bb, rr, cc in zip(np.split(b, cuts), np.split(r, cuts), np.split(c, cuts)):
        if len(rr) >= MIN_SURFACE:
            out.append((rr, cc, u["Z0"] + bb + 0.5))
    return out


def group_floors(surfs: list, H: int, W: int) -> list:
    """Surfaces grouped into map floors, lowest first: [(mask H x W, heights of its cells)]. Biggest surfaces first,
    each onto the floor nearest it in height (by medians) it doesn't stack with (STACK_SHARE), else a new floor."""
    floors: list = []  # [mask, [heights], median]
    for rr, cc, zz in sorted(surfs, key=lambda s: -len(s[0])):
        med = float(np.median(zz))
        best = None
        for fl in floors:
            over = int(fl[0][rr, cc].sum())
            if over > STACK_SHARE * min(len(rr), int(fl[0].sum())):
                continue
            d = abs(fl[2] - med)
            if best is None or d < best[0]:
                best = (d, fl)
        if best is None:
            m = np.zeros((H, W), bool)
            floors.append([m, [], med])
            best = (0, floors[-1])
        fl = best[1]
        fl[0][rr, cc] = True
        fl[1].extend(float(z) for z in zz)
        fl[2] = float(np.median(fl[1]))
    floors.sort(key=lambda fl: fl[2])
    total = sum(len(fl[1]) for fl in floors)
    # (a speck of a floor over another, a crate's top or a beam: left out)
    return [(fl[0], np.array(fl[1])) for fl in floors
            if len(floors) == 1 or len(fl[1]) >= MIN_FLOOR or len(fl[1]) >= MIN_FLOOR_SHARE * total]


def rects(mask: np.ndarray) -> list:
    """Cells `mask` as rectangles (row, col, rows, cols): each row's runs, a run the same as the one just above it
    taken into that one's rectangle."""
    H, W = mask.shape
    out: list = []
    open_: dict = {}  # (col, cols) -> index in out of the rectangle ending on the row above
    for r in range(H):
        row = mask[r]
        runs = []
        c = 0
        while c < W:
            if row[c]:
                c0 = c
                while c < W and row[c]:
                    c += 1
                runs.append((c0, c - c0))
            else:
                c += 1
        now = {}
        for run in runs:
            i = open_.get(run)
            if i is not None:
                out[i][2] += 1
            else:
                out.append([r, run[0], 1, run[1]])
                i = len(out) - 1
            now[run] = i
        open_ = now
    return [tuple(q) for q in out]


def pack(nums) -> str:
    """Numbers 0..4095, two characters each (ALPHABET, high then low)."""
    s = []
    for n in nums:
        n = int(n)
        if not 0 <= n < 4096:
            raise ValueError(n)
        s.append(ALPHABET[n >> 6] + ALPHABET[n & 63])
    return "".join(s)


def unpack(s: str) -> list:
    idx = {ch: i for i, ch in enumerate(ALPHABET)}
    return [idx[s[i]] * 64 + idx[s[i + 1]] for i in range(0, len(s), 2)]


def map_of(u: dict, floors: list) -> dict | None:
    """One auto map: its grid's north-west corner (x0: world X of row 0's north edge, y0: world Y of column 0's west
    edge), its floors' bands and rectangles, cropped to its cells."""
    if not floors:
        return None
    anyf = np.zeros_like(floors[0][0])
    for m, _z in floors:
        anyf |= m
    rr, cc = np.nonzero(anyf)
    r0, r1, c0, c1 = rr.min(), rr.max() + 1, cc.min(), cc.max() + 1
    xc, yc = u["px_to_world"](r0, c0)  # (the cell's middle)
    out = {"x0": round(float(xc) + CELL / 2, 2), "y0": round(float(yc) + CELL / 2, 2), "h": int(r1 - r0),
           "w": int(c1 - c0), "floors": []}
    for m, zz in floors:
        rs = rects(m[r0:r1, c0:c1])
        out["floors"].append({"lo": round(float(zz.min()) - FLOOR_PAD_LO, 1),
                              "hi": round(float(zz.max()) + FLOOR_PAD_HI, 1),
                              "cells": int(m.sum()), "rects": pack(v for q in rs for v in q)})
    return out


def build_cave_map(cd, p, ground, label: str) -> dict | None:
    u = C.build_cave(cd, p, ground, label, log=lambda *a: None)
    if u is None:
        return None
    keep = u["model"] & ~u["ground"]
    return map_of(u, group_floors(surfaces(u, keep), u["H"], u["W"]))


def build_building_map(cd, p, ground, label: str) -> dict | None:
    from .roads.recorded import Faces

    fl, wl = IN.building_faces(cd, p)
    if not fl:
        return None
    x0, y0, x1, y1 = p.bounds

    def gnd(X, Y):
        h, ok = ground.sample(X, Y)
        X, Y = np.asarray(X, float), np.asarray(Y, float)
        near = (X >= x0 - IN.GROUND_PAD) & (X <= x1 + IN.GROUND_PAD) & (Y >= y0 - IN.GROUND_PAD) & (Y <= y1 + IN.GROUND_PAD)
        return h, ok & near

    cap, walknet.STEP_CAP = walknet.STEP_CAP, IN.STEP_CAP
    try:
        u = walknet.build(fl, wl, [], label=label, ground=gnd, ground_reach=IN.GROUND_PAD + 2, prune=IN.PRUNE, fill=0,
                          top_reached=True, road_pieces=True, stair_max=IN.STAIR_SEARCH, log=lambda *a: None)
    finally:
        walknet.STEP_CAP = cap
    keep = u["model"] & ~u["ground"]
    surfs = surfaces(u, keep)
    tris = [[(q[0], q[1], z) for q, z in zip(f[0], f[1])] for f in fl] + \
        [[(q[0], q[1], z) for q, z in zip(w[1], w[2])] for w in wl]
    cover = Faces(np.array(tris, float), touch=0.0)
    indoor = []
    for rr, cc, zz in surfs:
        X, Y = u["px_to_world"](rr, cc)
        pi, z = cover.heights(np.asarray(X, float), np.asarray(Y, float))
        over = np.zeros(len(rr), bool)
        np.logical_or.at(over, pi, (z > zz[pi] + ROOF_Z) & (z < zz[pi] + ROOF_REACH))
        if over.mean() >= ROOF_SHARE:
            indoor.append((rr, cc, zz))
    return map_of(u, group_floors(indoor, u["H"], u["W"]))


def find_building(cd, cont: int, name: str, x: float, y: float, placements: list):
    """The placement of Data/Indoors.lua's building `name` ("Town: model", the model's file name or its id) round
    (x, y)."""
    model = name.split(": ", 1)[1] if ": " in name else name
    best = None
    for p in placements:
        bx0, by0, bx1, by1 = p.bounds
        if not (bx0 - 2 <= x <= bx1 + 2 and by0 - 2 <= y <= by1 + 2):
            continue
        fn = (cd.name(p.wmo) or str(p.wmo)).split("/")[-1].removesuffix(".wmo")
        if fn.lower() != model.lower() and str(p.wmo) != model:
            continue
        d = ((bx0 + bx1) / 2 - x) ** 2 + ((by0 + by1) / 2 - y) ** 2
        if best is None or d < best[0]:
            best = (d, p)
    return best and best[1]


def _cells(m: dict) -> int:
    return sum(f["cells"] for f in m["floors"])


def _outcome(m: dict | None) -> str:
    if not m:
        return "no floors (none reached on foot, or only a roof)"
    if _cells(m) < MIN_MAP_CELLS:
        return f"too small ({_cells(m)} cells: its floor is the land's)"
    return f"map: {len(m['floors'])} floors, {_cells(m)} cells"


def build_all(cd, log=print, only=None, report=None) -> list:
    """Every auto map: [{cont, key, name, kind, x0, y0, h, w, floors}]. `report`: a list given each model with no art
    looked at, (cont, key or name, name, what came of it)."""
    from . import interiors as I

    placed = interiors_placed()
    out = []
    want_caves = caves_without_art(placed=placed)
    want_bld = indoor_buildings()
    for cont in (0, 1):
        ground = C.Ground(cd, cont)
        by_uid = {p.uid: p for p, _path, _name in C.find_caves(cd, cont)}
        for c_, key, name, _x, _y in want_caves:
            if c_ != cont or (only and key not in only):
                continue
            p = by_uid.get(int(key[4:]))
            if p is None:
                log(f"  {key}: no placement")
                continue
            try:
                m = build_cave_map(cd, p, ground, key)
            except Exception as ex:  # (a model this reader can't take)
                log(f"  {key}: skipped ({ex!r})")
                continue
            if report is not None:
                report.append((cont, key, name, _outcome(m)))
            if m and _cells(m) >= MIN_MAP_CELLS:
                m.update(cont=cont, key=key, name=name, kind="cave")
                out.append(m)
                log(f"  {key} {name!r}: {len(m['floors'])} floors, {sum(f['cells'] for f in m['floors'])} cells")
        pls = I.placements(cd, cont)
        for c_, name, x, y, _r in want_bld:
            if c_ != cont or (only and name not in only):
                continue
            p = find_building(cd, cont, name, x, y, pls)
            if p is None:
                log(f"  {name}: no placement")
                continue
            if has_art(placed, cont, p.wmo, p.x, p.y):
                continue
            try:
                m = build_building_map(cd, p, ground, name)
            except Exception as ex:
                log(f"  {name}: skipped ({ex!r})")
                continue
            if report is not None:
                report.append((cont, f"in{p.uid}", name, _outcome(m)))
            if m and _cells(m) >= MIN_MAP_CELLS:
                town = name.split(": ", 1)[0]
                m.update(cont=cont, key=f"in{p.uid}", name=town, kind="inside")
                out.append(m)
                log(f"  {name}: {len(m['floors'])} floors, {sum(f['cells'] for f in m['floors'])} cells")
    return out


def _q(s: str) -> str:
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def automaps_lua(maps: list, version: str = "") -> str:
    lines = [
        f"-- GENERATED by `agps auto-maps --write` (app/azerothgps/automaps.py){' from client ' + version if version else ''}."
        " Do not edit by hand.",
        "-- Auto maps where the game has none (item 115): caves and buildings with no minimap art, drawn from their",
        "-- walkable cells floor by floor (G.AutoArt, G.LayoutAutoMap). Per continent: { key, name, kind (\"cave\" or",
        "-- \"inside\"), x0, y0 (world X of the grid's north edge, Y of its west edge), h, w (rows south, columns east, of",
        f"-- {CELL:g} yd), floors (lowest first): {{ lo, hi (world height), rects (row, col, rows, cols: two characters a",
        "-- number, \"0-9A-Za-z-_\" base 64) } }.",
        "local _, ns = ...",
        f"ns.AutoMaps = {{ cell = {CELL:g} }}",
    ]
    for cont in sorted({m["cont"] for m in maps}):
        lines.append(f"ns.AutoMaps[{cont}] = {{")
        for m in sorted((m for m in maps if m["cont"] == cont), key=lambda m: m["key"]):
            fls = ", ".join(f"{{ {f['lo']:g}, {f['hi']:g}, {_q(f['rects'])} }}" for f in m["floors"])
            lines.append(f"  {{ {_q(m['key'])}, {_q(m['name'])}, {_q(m['kind'])}, {m['x0']:g}, {m['y0']:g}, {m['h']}, "
                         f"{m['w']}, {{ {fls} }} }},")
        lines.append("}")
    return "\n".join(lines) + "\n"


def render(m: dict, out: Path, scale: int = 4) -> None:
    """A picture of an auto map's floors (data/debug/automaps/): each floor its own color."""
    from PIL import Image, ImageDraw

    cols = [(200, 170, 120), (120, 190, 220), (220, 120, 160), (150, 220, 120), (230, 220, 110), (170, 140, 230)]
    img = Image.new("RGB", (m["w"] * scale, m["h"] * scale), (20, 18, 16))
    d = ImageDraw.Draw(img, "RGBA")
    for i, f in enumerate(m["floors"]):
        v = unpack(f["rects"])
        col = cols[i % len(cols)] + (160,)
        for k in range(0, len(v), 4):
            r, c, h, w = v[k:k + 4]
            d.rectangle([c * scale, r * scale, (c + w) * scale - 1, (r + h) * scale - 1], fill=col)
    img.save(out)
