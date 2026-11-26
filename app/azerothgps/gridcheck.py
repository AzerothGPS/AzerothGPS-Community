"""Data checks against the walk grids (item 112, 1.4.1): the shipped data read back from the addon's own files (no
client, no mesh: CI runs it in about 3 s), the city grids' (Data/CityGrid.lua: heights and links) and the world grid's
(Data/WorldGrid<cont>.lua and the AzerothGPS_WG<cont>_* region folders: heights) floors per cell, decoded as
CityGrid.lua and WorldGrid.lua do (test_grid_data_checks.py compares the two).

(a) `track_offenders` (the drawn roads with heights: ns.FloorTracks, from the overrides' recorded roads with `zs`) and
    `overlay_offenders` (the capitals' and buildings' roads with node heights, Data/Capitals.lua and Data/Indoors.lua,
    climbing evenly between their nodes; drops, lifts and water roads left out): `off`, a stretch of TRACK_OFF_YD or
    more with no floor within TRACK_Z of its height (a city grid: its cell's floors, the 8 round it where it has none;
    the world grid: its cell's and the 8 round it, TRACK_Z_WORLD); `jump`, on a city grid two points one after the
    other on floors TRACK_JUMP_Z or more apart that the grid doesn't join within JUMP_LINKS links (Orgrimmar's old Wind
    Rider tower coil, item 110, the model case: from a landing at 32.5 onto the turn above at 42), or a drawn step
    climbing or dropping more than TRACK_JUMP_Z in at most TRACK_JUMP_YD with no floor between.
(b) `npc_offenders`: the shipped NPCs' spawns (Data/Npcs.lua) more than NPC_Z (NPC_Z_WORLD) off every floor round them
    and off the terrain (Data/Heights.lua: a floor the grid lacks, a swimmer over the sea's bed): `floating` (the
    nearest floor is under it) or `under`.

Where a spot has a capital's city grid with floors round it, that grid is the truth (its 2-3 yd cells); elsewhere the
world grid's (8.33 yd cells). A spot with no floor of either round it (the world grid leaves the capitals' cells to the
city grids and has no instances) is never an offender.

`agps grid-check` prints the lists; app/tests/test_grid_data_checks.py fails on an offender not in
app/tests/data/grid_known_offenders.json.
"""
from __future__ import annotations

import math
import re
from functools import lru_cache
from pathlib import Path

from .paths import ADDON_DIR, RESOURCES

ALPHA = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz-_"
DEC = {ch: i for i, ch in enumerate(ALPHA)}
WG_REP, WG_ZESC = ".", 62  # (worldbake.REP, ZESC)
CG_SURF = 7  # (CityGrid.lua's SURF: height 2, point 1, links 4)

TRACK_STEP_YD = 1.5  # yards: a track's points looked at this far apart along it
TRACK_Z = 4.0  # yards: a track point within this of a city grid's floor there is on it
TRACK_Z_WORLD = 6.0  # yards: the same on the world grid (8.33 yd cells: a slope's surface point is up to 4 yd off)
TRACK_OFF_YD = 6.0  # yards: a stretch off the floors at least this long is an offender (a corner cut is shorter)
TRACK_JUMP_Z = 4.0  # yards: a step between two drawn points climbing or dropping more than this ...
TRACK_JUMP_YD = 3.0  # ... in at most this across is a jump (a stair's riser is under 1)
JUMP_LINKS = 2  # (two floors one after the other on a track joined by this many of the grid's links, and one more a
# cell walked off the floors between: not a jump)
NPC_Z = 4.0  # yards: a spawn this far off every floor round it (city grid)
NPC_Z_WORLD = 6.0  # yards: on the world grid


# --------------------------------------------------------------------------------------------------- the city grids

DX, DY = (1, 0, -1, 0, 1, -1, -1, 1), (0, 1, 0, -1, 1, 1, -1, -1)  # (CityGrid.lua's directions 1-8)


class CityGrid:
    def __init__(self, name: str, head: dict, cells: str, s: str, links: str = ""):
        self.name = name
        self.cont = int(head["cont"])
        self.level = int(head["level"]) if "level" in head else self.cont
        self.cell, self.x0, self.y0 = float(head["cell"]), float(head["x0"]), float(head["y0"])
        self.w, self.h = int(head["w"]), int(head["h"])
        self.zmin, self.zq, self.offs = float(head["zmin"]), float(head["zq"]), int(head["offs"])
        self.whole = head.get("whole") == "true"
        self.counts = [DEC[ch] for ch in cells]
        first, f = [], 0
        for c in self.counts:
            first.append(f)
            f += c
        self.first, self.s = first, s
        self.road = {}  # (the road links: surface to surfaces, both ways; CityGrid.lua's c.links, 1-based there)
        for item in filter(None, links.split(";")):
            v = item.split(",")
            a, b = int(v[0]) - 1, int(v[1]) - 1
            self.road.setdefault(a, set()).add(b)
            self.road.setdefault(b, set()).add(a)
        self.cell_of = None

    def surfaces(self, i: int, j: int) -> list:
        """[(surface, z)] of cell (i, j)."""
        if i < 0 or j < 0 or i >= self.w or j >= self.h:
            return []
        ci = i * self.h + j
        out, s = [], self.s
        for k in range(self.counts[ci]):
            q = self.first[ci] + k
            p = q * CG_SURF
            out.append((q, (DEC[s[p]] * 64 + DEC[s[p + 1]]) * self.zq + self.zmin))
        return out

    def ij(self, x: float, y: float) -> tuple:
        return math.floor((x - self.x0) / self.cell), math.floor((y - self.y0) / self.cell)

    def _cell(self, q: int) -> int:
        if self.cell_of is None:
            import bisect
            self.cell_of = lambda q_: bisect.bisect_right(self.first, q_) - 1
        ci = self.cell_of(q)
        while ci > 0 and self.counts[ci] == 0:
            ci -= 1
        return ci

    def neighbors(self, q: int) -> set:
        """The surfaces surface q walks onto (its 8 links: CityGrid.lua's Link) and its road links."""
        ci = self._cell(q)
        i, j = divmod(ci, self.h)
        out = set(self.road.get(q, ()))
        for d in range(1, 9):
            v = DEC[self.s[q * CG_SURF + 2 + (d + 1) // 2]]
            k = v // 8 if d % 2 == 1 else v % 8
            ni, nj = i + DX[d - 1], j + DY[d - 1]
            if k and 0 <= ni < self.w and 0 <= nj < self.h:
                out.add(self.first[ni * self.h + nj] + k - 1)
        return out

    def linked(self, a: int, b: int, steps: int = 2) -> bool:
        """Whether the grid walks from surface a to b (or b to a) in at most `steps` links."""
        for x, y in ((a, b), (b, a)):
            seen, front = {x}, {x}
            for _ in range(steps):
                front = {n for f in front for n in self.neighbors(f)} - seen
                if y in front:
                    return True
                seen |= front
        return False

    def contains(self, x: float, y: float) -> bool:
        return self.x0 <= x < self.x0 + self.w * self.cell and self.y0 <= y < self.y0 + self.h * self.cell

    def cell_zs(self, i: int, j: int) -> list:
        if i < 0 or j < 0 or i >= self.w or j >= self.h:
            return []
        ci = i * self.h + j
        out, s = [], self.s
        for k in range(self.counts[ci]):
            p = (self.first[ci] + k) * CG_SURF
            out.append((DEC[s[p]] * 64 + DEC[s[p + 1]]) * self.zq + self.zmin)
        return out

    def zs_round(self, x: float, y: float, r: int = 1) -> list:
        i, j = math.floor((x - self.x0) / self.cell), math.floor((y - self.y0) / self.cell)
        return [z for di in range(-r, r + 1) for dj in range(-r, r + 1) for z in self.cell_zs(i + di, j + dj)]


@lru_cache(maxsize=1)
def city_grids() -> tuple:
    txt = (ADDON_DIR / "Data" / "CityGrid.lua").read_text(encoding="utf-8")
    out = []
    for m in re.finditer(r'ns\.CityGridData\["([^"]+)"\] = \{ (.*?)\n  cells = "([^"]*)",.*?\n  s = "([^"]*)",'
                         r'.*?\n  links = "([^"]*)"', txt, re.S):
        head = dict(re.findall(r'(\w+) = ("[^"]*"|[-\w.]+)', m.group(2)))
        out.append(CityGrid(m.group(1), head, m.group(3), m.group(4), m.group(5)))
    return tuple(out)


def city_grid_at(level: int, x: float, y: float):
    for g in city_grids():
        if g.level == level and g.contains(x, y):
            return g
    return None


# --------------------------------------------------------------------------------------------------- the world grid

class WorldGrid:
    def __init__(self, cont: int):
        txt = (ADDON_DIR / "Data" / f"WorldGrid{cont}.lua").read_text(encoding="utf-8")
        m = re.search(r"per = (\d+), cell = ([\d.]+), zq = ([\d.]+), z0 = (-?[\d.]+)", txt)
        self.cont = cont
        self.per, self.cell, self.zq, self.z0 = int(m.group(1)), float(m.group(2)), float(m.group(3)), float(m.group(4))
        self.raw = {}
        for folder in sorted(ADDON_DIR.parent.glob(f"AzerothGPS_WG{cont}_*")):
            body = (folder / "Data.lua").read_text(encoding="utf-8")
            self.raw.update({int(k): v for k, v in re.findall(r'\n  \[(\d+)\] = "([^"]*)",', body)})
        self.tiles = {}

    @staticmethod
    def _tokens(part: str, width):
        out, i, last = [], 0, None
        while i < len(part):
            if part[i] == WG_REP:
                out += [last] * (DEC[part[i + 1]] + 2)
                i += 2
            else:
                w = width(part[i])
                last = part[i:i + w]
                out.append(last)
                i += w
        return out

    def tile(self, key: int):
        """{ci: [z, ...]} of tile `key` (WorldGrid.lua's WG.Tile, heights only), or None where the grid has none."""
        if key in self.tiles:
            return self.tiles[key]
        raw = self.raw.get(key)
        t = None
        if raw is not None:
            counts_s, _recs, hs_s, _lks = raw.split("|")
            counts = [DEC[c] for c in self._tokens(counts_s, lambda ch: 1)]
            hs = self._tokens(hs_s, lambda ch: 4 if DEC[ch] == WG_ZESC else 1)
            per, q, last, prev, t = self.per, 0, None, [], {}
            for ci in range(per * per):
                n = counts[ci] if ci < len(counts) else 0
                if ci % per == 0:
                    prev = []
                if not n:
                    prev = []
                    continue
                cur = []
                for k in range(n):
                    h = hs[q]
                    q += 1
                    if len(h) == 4:
                        v = (DEC[h[1]] * 64 + DEC[h[2]]) * 64 + DEC[h[3]]
                    else:
                        pred = prev[k] if k < len(prev) else (prev[-1] if prev else (last or 0))
                        v = pred + DEC[h] - 31
                    last = v
                    cur.append(v)
                t[ci] = [v * self.zq + self.z0 for v in cur]
                prev = cur
        self.tiles[key] = t
        return t

    def cell_zs(self, gx: int, gy: int) -> list:
        per = self.per
        ty, tx = 31 - gx // per, 31 - gy // per
        if not (0 <= tx <= 63 and 0 <= ty <= 63):
            return []
        gx0, gy0 = (31 - ty) * per, (31 - tx) * per
        t = self.tile(tx * 64 + ty)
        return (t or {}).get((gx - gx0) * per + (gy - gy0), [])

    def zs_round(self, x: float, y: float, r: int = 1) -> list:
        gx, gy = math.floor(x / self.cell), math.floor(y / self.cell)
        return [z for di in range(-r, r + 1) for dj in range(-r, r + 1) for z in self.cell_zs(gx + di, gy + dj)]


@lru_cache(maxsize=None)
def world_grid(cont: int):
    if not (ADDON_DIR / "Data" / f"WorldGrid{cont}.lua").exists():
        return None
    return WorldGrid(cont)


def floors_round(level: int, x: float, y: float) -> tuple:
    """(the grid's floor heights round (x, y): a city grid's cell's (the 8 round it where it has none), else the world
    grid's cell's and the 8 round it; which grid: "city" or "world" or None)."""
    zs, grid, _surfs = _floors(level, x, y)
    return zs, grid


def _floors(level: int, x: float, y: float) -> tuple:
    """floors_round's, and on a city grid its surfaces [(surface, z)] (the grid, its surfaces)."""
    g = city_grid_at(level, x, y)
    if g:
        i, j = g.ij(x, y)
        surfs = g.surfaces(i, j) or [sf for di in (-1, 0, 1) for dj in (-1, 0, 1) for sf in g.surfaces(i + di, j + dj)]
        if surfs:
            return [z for _q, z in surfs], "city", (g, surfs)
    w = world_grid(level) if level in (0, 1, 2991) else None
    if w:
        zs = w.zs_round(x, y)
        if zs:
            return zs, "world", None
    return [], None, None


# --------------------------------------------------------------------------------------------------- (a) the tracks

def floor_tracks(overrides: Path = RESOURCES / "overrides") -> dict:
    from .roads.tracks import floor_tracks as ft
    return ft(overrides)


def _samples(pts: list, zs: list):
    """(x, y, z, along) every TRACK_STEP_YD along the drawn line, heights between its points' (the router's own)."""
    out, along = [], 0.0
    xy = [(pts[i], pts[i + 1]) for i in range(0, len(pts) - 1, 2)]
    for k in range(len(xy) - 1):
        (x1, y1), (x2, y2) = xy[k], xy[k + 1]
        z1, z2 = zs[k], zs[k + 1]
        d = math.hypot(x2 - x1, y2 - y1)
        n = max(1, int(d / TRACK_STEP_YD))
        for q in range(n):
            f = q / n
            out.append((x1 + (x2 - x1) * f, y1 + (y2 - y1) * f, z1 + (z2 - z1) * f, along + d * f))
        along += d
    if xy:
        out.append((xy[-1][0], xy[-1][1], zs[len(xy) - 1], along))
    return out


def track_id(cont: int, t: dict) -> str:
    return f"{cont}:{t['time']}" + (f":{t['part']}" if t.get("part") else "")


def check_track(cont: int, t: dict) -> list:
    """The track's offenders: {kind: "off", yd, worst (yards off the nearest floor), at (x, y, z), floors} for each
    stretch off the grid's floors at least TRACK_OFF_YD long; {kind: "jump", dz, at, ...} for each floor jumped: on a
    city grid, two points one after the other on floors TRACK_JUMP_Z or more apart that the grid doesn't walk between
    (within two links: a spiral's turn above, the floor over a hall), or anywhere a drawn step climbing or dropping more
    than TRACK_JUMP_Z in at most TRACK_JUMP_YD across with no floor between."""
    pts, zs = t["pts"], t["zs"]
    if len(zs) * 2 != len(pts):
        return [{"kind": "bad", "why": f"{len(pts) // 2} points, {len(zs)} heights"}]
    out = []
    run, last = None, None

    def close(run, last):
        """A stretch off the floors reported when long enough; the last floor matched kept over a short one only."""
        if run and run["end"] - run["start"] >= TRACK_OFF_YD:
            out.append({"kind": "off", "yd": round(run["end"] - run["start"], 1), "worst": round(run["worst"], 1),
                        "at": run["at"], "floors": run["floors"], "grid": run["grid"]})
            return None
        return last

    for x, y, z, along in _samples(pts, zs):
        floors, grid, surfs = _floors(cont, x, y)
        if not floors:
            close(run, last)
            run = last = None
            continue
        tol = TRACK_Z if grid == "city" else TRACK_Z_WORLD
        dz = min(abs(f - z) for f in floors)
        if dz > tol:  # (the last floor matched kept: a short stretch off it, then onto a floor it isn't joined to)
            if run is None:
                run = {"start": along, "end": along, "worst": 0.0}
            run["end"] = along
            if dz > run["worst"]:
                run.update(worst=dz, at=(round(x, 1), round(y, 1), round(z, 1)), grid=grid,
                           floors=sorted({round(f, 1) for f in floors}))
            continue
        last = close(run, last)
        run = None
        if surfs:
            g, lst = surfs
            q, qz = min(lst, key=lambda sf: abs(sf[1] - z))
            if (last and last[0] is g and last[1] != q and abs(qz - last[2]) >= TRACK_JUMP_Z
                    and not g.linked(last[1], q, JUMP_LINKS + int((along - last[3]) / g.cell))):
                out.append({"kind": "jump", "dz": round(qz - last[2], 1), "at": (round(x, 1), round(y, 1), round(z, 1)),
                            "from": round(last[2], 1), "to": round(qz, 1), "grid": "city"})
            last = (g, q, qz, along)
        else:
            last = None
    close(run, last)
    # (a drawn step the grid has no floor between for)
    for k in range(len(zs) - 1):
        x1, y1, x2, y2 = pts[2 * k], pts[2 * k + 1], pts[2 * k + 2], pts[2 * k + 3]
        d, dz = math.hypot(x2 - x1, y2 - y1), zs[k + 1] - zs[k]
        if abs(dz) > TRACK_JUMP_Z and d <= TRACK_JUMP_YD:
            lo, hi = min(zs[k], zs[k + 1]), max(zs[k], zs[k + 1])
            mid = floors_round(cont, (x1 + x2) / 2, (y1 + y2) / 2)[0]
            if not any(lo + 1 < f < hi - 1 for f in mid):
                out.append({"kind": "jump", "dz": round(dz, 1), "yd": round(d, 1),
                            "at": (round(x1, 1), round(y1, 1), round(zs[k], 1)), "grid": "drawn"})
    return out


def track_offenders(tracks: dict | None = None) -> dict:
    """{track id ("cont:time[:part]"): [offender, ...]} over every FloorTrack."""
    tracks = floor_tracks() if tracks is None else tracks
    out = {}
    for cont, lst in sorted(tracks.items()):
        for t in lst:
            if t.get("op", "add") != "add":
                continue
            bad = check_track(cont, t)
            if bad:
                out[track_id(cont, t)] = bad
    return out


# (the road overlays with node heights: the capitals' roads, Data/Capitals.lua, and the buildings' insides with their
# stairs, Data/Indoors.lua. A road between two nodes with heights climbs evenly along its points (as Router's floor
# roads); drops (source 3 and the overlay's `drops`), lifts (5) and the water's roads (7) are left out: they leave the
# floors by design. A node height of 0 is none, +-10000 any floor.)
OVERLAY_FILES = ("Capitals.lua", "Indoors.lua")
OVERLAY_SOURCES = ("0", "6")  # (a plain road, stairs)
_NUM = r"[-\d.]+"


def _nums(s: str) -> list:
    return [float(v) for v in re.findall(_NUM, s)]


def overlay_roads(files=OVERLAY_FILES):
    """Each overlay road with heights at both ends: (id "File:cont:x,y,z>x,y,z" (its ends: kept when the file's roads
    are numbered again), cont, pts, zs, stairs)."""
    for fn in files:
        txt = (ADDON_DIR / "Data" / fn).read_text(encoding="utf-8")
        starts = [m.start() for m in re.finditer(r"overlays\[#overlays \+ 1\] = \{", txt)]
        conts = [(m.start(), int(m.group(1))) for m in re.finditer(r"ns\.RoadOverlays\[(\d+)\] = overlays", txt)]
        for oi, st in enumerate(starts):
            block = txt[st:starts[oi + 1] if oi + 1 < len(starts) else len(txt)]
            cont = max((c for c in conts if c[0] < st), default=(0, None))[1]
            mn, mz = re.search(r"\n  n = \{([^}]*)\}", block), re.search(r"\n  nz = \{([^}]*)\}", block)
            me = re.search(r"\n  e = \{\n(.*?)\n  \},", block, re.S)
            if cont is None or not (mn and mz and me):
                continue
            n, nz = _nums(mn.group(1)), _nums(mz.group(1))
            md = re.search(r"\n  drops = \{([^}]*)\}", block)
            drops = {int(k) for k in re.findall(r"\[(\d+)\]", md.group(1))} if md else set()
            edges = re.findall(r'\{(\d+),(\d+),([\d.]+),(\d+),"([^"]*)"\}', me.group(1))
            for k, (a, b, _len, src, s) in enumerate(edges, 1):
                a, b = int(a), int(b)
                if src not in OVERLAY_SOURCES or k in drops:
                    continue
                za, zb = nz[a - 1], nz[b - 1]
                if not za or not zb or abs(za) >= 9999 or abs(zb) >= 9999:
                    continue
                x, y = n[2 * a - 2], n[2 * a - 1]
                pts = [x, y]
                for i in range(0, len(s) - 3, 4):  # (Router's Unpacked: whole yards from node a)
                    x += DEC[s[i]] * 64 + DEC[s[i + 1]] - 2048
                    y += DEC[s[i + 2]] * 64 + DEC[s[i + 3]] - 2048
                    pts += [x, y]
                bx, by = n[2 * b - 2], n[2 * b - 1]
                if (pts[-2], pts[-1]) != (bx, by):
                    pts += [bx, by]
                seg = [math.hypot(pts[i + 2] - pts[i], pts[i + 3] - pts[i + 1]) for i in range(0, len(pts) - 2, 2)]
                tot, acc, zs = sum(seg), 0.0, [za]
                for d in seg:
                    acc += d
                    zs.append(za + (zb - za) * (acc / tot if tot else 1))
                yield (f"{fn[:-4]}:{cont}:{pts[0]:.0f},{pts[1]:.0f},{za:.0f}>{bx:.0f},{by:.0f},{zb:.0f}", cont, pts, zs,
                       src == "6")


def overlay_offenders() -> dict:
    """{road id: [offender, ...]} over the overlays' roads with heights (check_track's, the drawn step's left out: a
    road's heights are its two nodes', one climb between)."""
    out = {}
    for rid, cont, pts, zs, _stairs in overlay_roads():
        bad = [o for o in check_track(cont, {"pts": pts, "zs": zs}) if o.get("grid") != "drawn"]
        if bad:
            out.setdefault(rid, []).extend(bad)  # (two roads between the same ends: one entry)
    return out


# --------------------------------------------------------------------------------------------------- (b) the NPCs

def shipped_spawns(path: Path = ADDON_DIR / "Data" / "Npcs.lua"):
    """[(id, name, level, x, y, z)] of Data/Npcs.lua's lines."""
    txt = path.read_text(encoding="utf-8")
    body = txt[txt.index("[==[") + 4:txt.index("]==]")]
    out = []
    for line in body.strip().splitlines():
        f = line.split("|")
        if len(f) < 7:
            continue
        for sp in f[6].split(";"):
            v = sp.split()
            if len(v) == 4:
                out.append((int(f[0]), f[1], int(v[0]), float(v[1]), float(v[2]), float(v[3])))
    return out


@lru_cache(maxsize=1)
def _ground():
    from .interiorfloors import shipped_ground
    return shipped_ground()


def check_spawn(level: int, x: float, y: float, z: float):
    """None when (x, y, z) is on a floor of the grid round it, or on the terrain (Data/Heights.lua: a floor the grid
    lacks, Teldrassil's crown in the world grid; a swimmer over the sea's bed), or there's no grid there; else {kind:
    "floating" | "under", dz (the nearest floor's height less z), floors, grid, ground}."""
    floors, grid = floors_round(level, x, y)
    if not floors:
        return None
    tol = NPC_Z if grid == "city" else NPC_Z_WORLD
    near = min(floors, key=lambda f: abs(f - z))
    if abs(near - z) <= tol:
        return None
    ground = _ground()(level, x, y) if level in (0, 1) else None
    if ground is not None and abs(ground - z) <= NPC_Z_WORLD:
        return None
    return {"kind": "floating" if near < z else "under", "dz": round(near - z, 1), "grid": grid,
            "floors": sorted({round(f, 1) for f in floors}), "ground": None if ground is None else round(ground, 1)}


def spawn_id(nid: int, level: int, x: float, y: float) -> str:
    return f"{nid}@{level}:{x:.0f},{y:.0f}"


def npc_offenders(spawns=None) -> dict:
    """{spawn id ("npc@level:x,y"): {name, z, kind, dz, floors, grid}} over every shipped spawn."""
    spawns = shipped_spawns() if spawns is None else spawns
    out = {}
    for nid, name, level, x, y, z in spawns:
        bad = check_spawn(level, x, y, z)
        if bad:
            bad.update(name=name, z=z)
            out[spawn_id(nid, level, x, y)] = bad
    return out


def _worst(offs: list) -> float:
    return max(o.get("worst", abs(o.get("dz", 0))) for o in offs)


def report(log=print) -> tuple:
    tr, ov, np_ = track_offenders(), overlay_offenders(), npc_offenders()
    log(f"FloorTracks off the grid's floors or jumping floors: {len(tr)}")
    for k, v in sorted(tr.items(), key=lambda kv: -_worst(kv[1])):
        log(f"  {k}: {v}")
    log(f"Capital and indoor roads off the grid's floors: {len(ov)}")
    for k, v in sorted(ov.items(), key=lambda kv: -_worst(kv[1])):
        log(f"  {k}: {v}")
    log(f"NPC spawns off the grid's floors: {len(np_)}")
    for k, v in sorted(np_.items(), key=lambda kv: -abs(kv[1]["dz"])):
        log(f"  {k} {v['name']}: z {v['z']} {v['kind']} by {abs(v['dz'])} ({v['grid']} floors {v['floors']})")
    return tr, ov, np_
