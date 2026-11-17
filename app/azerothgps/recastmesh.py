"""Our own navigation mesh of a capital, built with Recast from the same collision faces AzerothGPS's capital grids
come from, as a second opinion on where a player can walk (asked 2026-11-17: a test server's own mesh, from
client 70058, has none of Stormwind's, Ironforge's or Orgrimmar's city models; "go ahead with the Recast build").

A dev tool only (nothing of it ships): `data/tools/navbuild.exe` (navbuild/navbuild.cpp over Recast's sources in
data/thirdparty/recastnavigation, compiled with zig: `agps navmesh build-tool`), fed:
- the city's models' faces (capitals.city_faces: floors and walls, every group);
- the doodads with collision placed in and round it (doodads.doodads/triangles: planters, stalls, lamp posts);
- the terrain round it (caves.Ground, every 2 yards; not holes nor under the water: the canals' beds aren't walked).
Walkable is decided here by each face's slope (the collision faces' winding can't be trusted): at most WALK_SLOPE.
The agent is a player: AGENT_HEIGHT tall, AGENT_RADIUS round, steps up AGENT_CLIMB.
"""

from __future__ import annotations

import math
import struct
import subprocess
import tempfile
from pathlib import Path

import numpy as np

from .navmesh import NavMesh, Tile
from .paths import data_dir

CELL, CELL_H = 0.4, 0.2  # yards: Recast's cell across and up
AGENT_HEIGHT, AGENT_RADIUS, AGENT_CLIMB = 2.0, 0.4, 1.0
WALK_SLOPE = 50.0  # degrees: the steepest face walked (the terrain grid's, capitals.FLOOR_SLOPE's)
MAX_EDGE = 12.0
GROUND_STEP = 2.0
PAD = 40.0  # yards round the city's models: the ground at its gates


def tool() -> Path:
    return data_dir() / "tools" / "navbuild.exe"


def _walkable(T: np.ndarray) -> np.ndarray:
    """Each triangle (N, 3, 3: x, y, z) walkable by its slope, either winding."""
    n = np.cross(T[:, 1] - T[:, 0], T[:, 2] - T[:, 0])
    L = np.linalg.norm(n, axis=1)
    up = np.abs(n[:, 2]) / np.maximum(L, 1e-9)
    return (up >= math.cos(math.radians(WALK_SLOPE))) & (L > 1e-6)


def capital_triangles(cd, cap, log=print) -> tuple[np.ndarray, tuple]:
    """The triangles (N, 3, 3) of a capital and round it, and the box (x0, y0, x1, y1)."""
    from . import capitals, doodads
    from .caves import Ground

    fl, wl, lq, _named = capitals.city_faces(cd, cap, log)
    tris = []
    for xy, zs, _outline, _mouth in fl:
        tris.append([(xy[k][0], xy[k][1], zs[k]) for k in range(3)])
    for (_zlo, _zhi), xy, zs in wl:
        tris.append([(xy[k][0], xy[k][1], zs[k]) for k in range(3)])
    T = np.array(tris, float)
    x0, y0 = T[:, :, 0].min() - PAD, T[:, :, 1].min() - PAD
    x1, y1 = T[:, :, 0].max() + PAD, T[:, :, 1].max() + PAD
    parts = [T]
    # the doodads with collision: their faces as they are
    for d in doodads.doodads(cd, cap.cont, (x0, y0, x1, y1), wmos=None):
        D = doodads.triangles(cd, d)
        if D is not None and len(D):
            parts.append(np.asarray(D, float))
    # the terrain, every GROUND_STEP yards: two triangles a square where all four corners are walkable ground
    g = Ground(cd, cap.cont)
    xs = np.arange(x0, x1 + GROUND_STEP, GROUND_STEP)
    ys = np.arange(y0, y1 + GROUND_STEP, GROUND_STEP)
    X, Y = np.meshgrid(xs, ys, indexing="ij")
    h, ok = g.sample(X.ravel(), Y.ravel())
    H = np.asarray(h, float).reshape(X.shape)
    OK = np.asarray(ok, bool).reshape(X.shape) & np.isfinite(H)
    q = OK[:-1, :-1] & OK[1:, :-1] & OK[:-1, 1:] & OK[1:, 1:]
    ii, jj = np.nonzero(q)
    if len(ii):
        def p(a, b):
            return np.stack([X[a, b], Y[a, b], H[a, b]], -1)
        A, B, Cc, Dd = p(ii, jj), p(ii + 1, jj), p(ii, jj + 1), p(ii + 1, jj + 1)
        parts.append(np.stack([A, B, Dd], 1))
        parts.append(np.stack([A, Dd, Cc], 1))
    T = np.concatenate(parts)
    log(f"  {cap.name}: {len(fl)} floor and {len(wl)} wall faces, {len(T)} triangles with doodads and ground")
    return T, (x0, y0, x1, y1)


def run_recast(T: np.ndarray, log=print) -> dict:
    """navbuild.exe over the triangles: the mesh's tiles, {(tx, ty): navmesh.Tile} (world x, y, z; neis 1-based, 0 none,
    0x8000 a tile's side)."""
    walk = _walkable(T)
    # (Recast's axes: x, up, z = world x, height, world y; the solid faces' area 0)
    V = T.reshape(-1, 3)[:, [0, 2, 1]].astype(np.float32)
    n = len(T)
    idx = np.arange(n * 3, dtype=np.int32)
    areas = np.where(walk, 63, 0).astype(np.uint8)
    bmin = V.min(axis=0) - 1
    bmax = V.max(axis=0) + 1
    with tempfile.TemporaryDirectory() as td:
        inp, out = Path(td) / "in.bin", Path(td) / "out.bin"
        with inp.open("wb") as f:
            f.write(b"AGNI")
            f.write(struct.pack("<6f", CELL, CELL_H, AGENT_HEIGHT, AGENT_RADIUS, AGENT_CLIMB, MAX_EDGE))
            f.write(struct.pack("<3f", *bmin))
            f.write(struct.pack("<3f", *bmax))
            f.write(struct.pack("<II", n * 3, n))
            f.write(V.tobytes())
            f.write(idx.tobytes())
            f.write(areas.tobytes())
        r = subprocess.run([str(tool()), str(inp), str(out)], capture_output=True, text=True)
        log("  recast: " + r.stderr.strip().replace("\n", "; "))
        if r.returncode != 0:
            raise RuntimeError(f"navbuild failed ({r.returncode}): {r.stderr}")
        b = out.read_bytes()
    assert b[:4] == b"AGNT"
    (ntiles,) = struct.unpack_from("<I", b, 4)
    o = 8
    tiles = {}
    for _ in range(ntiles):
        tx, ty, nv, npoly, nvp = struct.unpack_from("<iiIII", b, o)
        o += 20
        raw = np.frombuffer(b, np.float32, nv * 3, o).reshape(-1, 3)
        o += nv * 12
        t = Tile.__new__(Tile)
        t.tx, t.ty = tx, ty
        t.climb = AGENT_CLIMB
        t.verts = [(float(v[0]), float(v[2]), float(v[1])) for v in raw]
        t.polys = []
        for _ in range(npoly):
            vals = struct.unpack_from("<%dH" % (nvp * 2), b, o)
            o += nvp * 4
            area = b[o]
            o += 1
            vs = [v for v in vals[:nvp] if v != 0xFFFF]
            ns = []
            for nb in vals[nvp:nvp + len(vs)]:
                if nb == 0xFFFF:
                    ns.append(0)
                elif nb & 0x8000:  # (a tile's side: joined to the next tile's by navmesh.NavMesh._across)
                    ns.append(0x8000)
                else:
                    ns.append(nb + 1)
            t.polys.append({"verts": vs, "neis": ns, "flags": 1, "area": 11 if area else 0, "type": 0})
        xs = [v[0] for v in t.verts]
        ys = [v[1] for v in t.verts]
        zs = [v[2] for v in t.verts]
        t.bmin, t.bmax = (min(xs), min(ys), min(zs)), (max(xs), max(ys), max(zs))
        tiles[(tx, ty)] = t
    return tiles


class RecastMesh(NavMesh):
    """One built mesh (a capital's), searched as navmesh.NavMesh's: its tiles, nothing loaded from disk."""

    def __init__(self, tiles: dict, cont: int):
        self.cont, self.dir = cont, None
        self.orig, self.tile_w = (0.0, 0.0, 0.0), 1e9
        self.tiles = dict(tiles)
        self._centers = {}

    def tile(self, tx, ty):
        return self.tiles.get((tx, ty))

    def load_box(self, *a):
        return None


def save(tiles: dict, path: Path) -> None:
    import pickle

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as f:
        pickle.dump({k: {"verts": t.verts, "polys": t.polys, "bmin": t.bmin, "bmax": t.bmax} for k, t in tiles.items()}, f)


def load(path: Path) -> dict:
    import pickle

    out = {}
    for k, d in pickle.loads(path.read_bytes()).items():
        t = Tile.__new__(Tile)
        t.tx, t.ty = k
        t.climb = AGENT_CLIMB
        t.verts, t.polys, t.bmin, t.bmax = d["verts"], d["polys"], d["bmin"], d["bmax"]
        out[k] = t
    return out


def mesh_path(name: str) -> Path:
    return data_dir() / "navmesh" / f"{name.lower().replace(' ', '_')}.pkl"


GRID_YD = 16.0  # the export's lookup cells: each cell lists the polys touching it


def export_lua(meshes: dict, out: Path, log=print) -> None:
    """The meshes ({name: (cont, tiles)}) as one Lua file for the developer addon's route comparison:
    AzerothGPSDevNav[name] = { cont, box = {x0, y0, x1, y1}, cell, gx0, gy0, gw, vs = "x,y,z,...", ps = "vi,vi,..;..."
    (a poly's vertices, 1-based), ns = "nb,va,vb,...;..." (each poly's neighbors and the portal's vertices), gs =
    "k:pid,pid;..." (the grid cells' polys, k = gx * gw + gy) }.
    Never shipped: local, git-ignored."""
    lines = ["-- GENERATED by azerothgps.recastmesh.export_lua: Recast meshes for the dev tools' route comparison.",
             "-- Local only, never committed or shipped.", "AzerothGPSDevNav = AzerothGPSDevNav or {}"]
    for name, (cont, tiles) in meshes.items():
        m = RecastMesh(tiles, cont)
        ids, verts, vindex, polys = {}, [], {}, []

        def vid(v):
            k = (round(v[0], 1), round(v[1], 1), round(v[2], 1))
            i = vindex.get(k)
            if i is None:
                i = len(verts)
                vindex[k] = i
                verts.append(k)
            return i
        for key, i, t, p in m._polys():
            if p["area"] == 0:
                continue
            ids[(key, i)] = len(polys) + 1
            polys.append([vid(t.verts[v]) + 1 for v in p["verts"]])
        neigh = [[] for _ in polys]
        for (key, i), pid in ids.items():
            for nb, edge in m.neighbors(key, i):
                q = ids.get(nb)
                if q:
                    neigh[pid - 1].extend([q, vid(edge[0]) + 1, vid(edge[1]) + 1])
        xs = [v[0] for v in verts]
        ys = [v[1] for v in verts]
        x0, y0 = min(xs), min(ys)
        gw = int((max(ys) - y0) / GRID_YD) + 1
        grid: dict = {}
        for pid, pv in enumerate(polys, 1):
            px = [verts[v - 1][0] for v in pv]
            py = [verts[v - 1][1] for v in pv]
            for gx in range(int((min(px) - x0) / GRID_YD), int((max(px) - x0) / GRID_YD) + 1):
                for gy in range(int((min(py) - y0) / GRID_YD), int((max(py) - y0) / GRID_YD) + 1):
                    grid.setdefault(gx * gw + gy, []).append(pid)
        # (as strings, read on first use: Lua 5.1 allows 262143 constants a function, a city's numbers are more)
        flat = ",".join(f"{v[0]:.1f},{v[1]:.1f},{v[2]:.1f}" for v in verts)
        lines.append(f'AzerothGPSDevNav[{name!r}] = {{ cont = {cont}, box = {{ {x0:.1f}, {y0:.1f}, {max(xs):.1f}, {max(ys):.1f} }},')
        lines.append(f"  cell = {GRID_YD}, gx0 = {x0:.1f}, gy0 = {y0:.1f}, gw = {gw},")
        lines.append(f'  vs = "{flat}",')
        lines.append('  ps = "' + ";".join(",".join(map(str, pv)) for pv in polys) + '",')
        lines.append('  ns = "' + ";".join(",".join(map(str, nv)) for nv in neigh) + '",')
        lines.append('  gs = "' + ";".join(f"{k}:" + ",".join(map(str, v)) for k, v in sorted(grid.items())) + '",')
        lines.append("}")
        log(f"  {name}: {len(polys)} polys, {len(verts)} verts, {sum(len(n) for n in neigh) // 3} links")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    log(f"wrote {out} ({out.stat().st_size / 1e6:.1f} MB)")
