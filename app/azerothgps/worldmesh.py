"""Our own Recast meshes of the open world, one per map tile (asked 2026-11-22: "using the same technique used for
cities, lets plan to regenerate wall data for the whole map to test"; docs/world-grid-1.4.0.md).

A dev tool only (nothing of it ships), the city meshes' recipe (recastmesh.py) over each ADT tile of a continent:
- the terrain, every quad (4.17 yd) as two triangles, not its holes (a cellar's or a cave's way down); a quad under
  water deeper than WADE is solid, not walked (Recast doesn't swim: the world grid takes the terrain grid's water);
- every WMO placed over the tile (buildings, bridges, walls, towers, caves, the capitals' models), its faces a character
  collides with (walknet.model_faces: floors and walls) as the city meshes take them;
- every doodad with collision placed over it (the ADT's, and the WMOs' own sets): trees' trunks, rocks, fences.
Walkable is decided by each face's slope (recastmesh.WALK_SLOPE), the agent is recastmesh's (a player).

Each tile is built over its own box and PAD yards round it (so the walls just past its edge are seen), by navbuild.exe
in a process of its own (`agps world-grid mesh`, many at once). Its raw output is kept as it is, `<cont>_<tx>_<ty>.bin`
under `mesh_dir()` (data/navmesh/world, or AGPS_WORLDMESH_DIR: the meshes are a few GB), read with `load_tile`.
Undercity's model is left out (its city is a level of its own: cities.UNDERCITY_ID).
"""

from __future__ import annotations

import math
import os
import struct
import subprocess
import tempfile
import time
from pathlib import Path

import numpy as np

from . import recastmesh as RM
from .extract import adt
from .paths import data_dir

T = adt.TILE_YD
Q = T / 128  # a quad, 4.17 yd
PAD = 24.0  # yards round a tile built with it
WADE = 1.0  # yards of water a quad's ground may be under and still be walked (recastmesh.WADE)
CONTINENTS = (0, 1)


def mesh_dir() -> Path:
    env = os.environ.get("AGPS_WORLDMESH_DIR")
    return Path(env) if env else data_dir() / "navmesh" / "world"


def tile_box(tx: int, ty: int) -> tuple:
    """A map tile's box (x0, y0, x1, y1), world: tile (tx, ty) holds X in [(31 - ty) T, (32 - ty) T], Y likewise by tx."""
    return ((31 - ty) * T, (31 - tx) * T, (32 - ty) * T, (32 - tx) * T)


def tile_of(x: float, y: float) -> tuple:
    return int(math.floor(32 - y / T)), int(math.floor(32 - x / T))


def tile_path(cont: int, tx: int, ty: int) -> Path:
    return mesh_dir() / f"{cont}_{tx}_{ty}.bin"


def tiles(cd, cont: int) -> list:
    """The continent's map tiles with terrain: [(tx, ty)]."""
    m = next(r for r in cd.table("Map") if r["ID"] == cont)
    wdt = adt.parse_wdt(cd.casc.read(m["WdtFileDataID"]))
    return sorted(k for k, t in wdt.tiles.items() if t.root)


# --- one tile's triangles ----------------------------------------------------------------------------------------------

class World:
    """A continent's sources, read once a process: the WDT, the WMO placements, the models' faces (local frames)."""

    def __init__(self, cd, cont: int):
        from . import interiors as I

        self.cd, self.cont = cd, cont
        m = next(r for r in cd.table("Map") if r["ID"] == cont)
        self.wdt = adt.parse_wdt(cd.casc.read(m["WdtFileDataID"]))
        self.placements = I.placements(cd, cont)
        self.skip = set()
        if cont == 0:
            from . import cities
            try:
                self.skip.add(cities.placement(cd)[0].uid)
            except Exception:
                pass
        self._faces: dict = {}
        self._roots: dict = {}

    def faces(self, wmo: int) -> np.ndarray:
        """A model's collision faces (floors and walls) in its own frame: (n, 3, 3)."""
        from . import capitals, walknet

        got = self._faces.get(wmo)
        if got is None:
            try:
                fl, wl, _lq = walknet.model_faces(self.cd, wmo, capitals.FLOOR_SLOPE)
                got = np.array([tri for _g, _z, tri in fl] + [tri for _g, _z, tri in wl], float).reshape(-1, 3, 3)
            except Exception:
                got = np.zeros((0, 3, 3))
            if len(self._faces) > 400:
                self._faces.clear()
            self._faces[wmo] = got
        return got

    def root(self, tx: int, ty: int):
        t = self.wdt.tiles.get((tx, ty))
        if not (t and t.root):
            return None
        return self.cd.casc.read(t.root)


def terrain(root: bytes):
    """A tile's terrain: heights V (129 x 129, the chunks' outer vertices: V[i, j] at X = (32 - ty) T - i Q,
    Y = (32 - tx) T - j Q), holes (128 x 128 quads) and each quad's water top (nan: no water over it)."""
    V = np.full((129, 129), np.nan)
    holes = np.zeros((128, 128), bool)
    top = np.full((128, 128), np.nan)
    for magic, a, b in adt.iter_chunks(root):
        if magic == "MCNK":
            flags = struct.unpack_from("<I", root, a)[0]
            ix, iy = struct.unpack_from("<II", root, a + 4)
            if ix >= 16 or iy >= 16:
                continue
            base = struct.unpack_from("<f", root, a + 0x68 + 8)[0]
            for m2, a2, b2 in adt.iter_chunks(root, a + 128, b):
                if m2 == "MCVT" and b2 - a2 >= 145 * 4:
                    mcvt = np.frombuffer(root[a2:a2 + 145 * 4], np.float32)
                    V[iy * 8:iy * 8 + 9, ix * 8:ix * 8 + 9] = np.array([mcvt[i * 17:i * 17 + 9] for i in range(9)]) + base
                    break
            h = np.zeros((8, 8), bool)
            if flags & 0x10000:
                hb = struct.unpack_from("<8B", root, a + 0x14)
                for i in range(8):
                    for j in range(8):
                        h[i, j] = bool(hb[i] >> j & 1)
            else:
                lo = struct.unpack_from("<H", root, a + 0x3C)[0]
                for i in range(8):
                    for j in range(8):
                        h[i, j] = bool(lo >> ((i // 2) * 4 + j // 2) & 1)
            holes[iy * 8:iy * 8 + 8, ix * 8:ix * 8 + 8] = h
        elif magic == "MH2O":
            for ci in range(256):
                off_inst, n_layers, _ = struct.unpack_from("<III", root, a + ci * 12)
                if not n_layers or not off_inst:
                    continue
                cy, cx = divmod(ci, 16)
                for li in range(n_layers):
                    p = a + off_inst + li * 24
                    _t, _f, _mn, mx, x0, y0, w, hh, off_mask, _ov = struct.unpack_from("<HHffBBBBII", root, p)
                    cells = np.zeros((8, 8), bool)
                    if off_mask:
                        raw = root[a + off_mask: a + off_mask + (w * hh + 7) // 8]
                        bits = np.unpackbits(np.frombuffer(raw, np.uint8), bitorder="little")[:w * hh]
                        cells[y0:y0 + hh, x0:x0 + w] = bits.reshape(hh, w).astype(bool)
                    else:
                        cells[y0:y0 + hh, x0:x0 + w] = True
                    sub = top[cy * 8:cy * 8 + 8, cx * 8:cx * 8 + 8]
                    sub[cells] = np.fmax(sub[cells], mx)
    return V, holes, top


def terrain_triangles(world: World, box) -> tuple[np.ndarray, np.ndarray, list]:
    """The terrain's triangles over `box` (N, 3, 3) and whether each may be walked (not under deep water; the slope is
    Recast's to judge with the rest), and its water [(x0, y0, x1, y1, top)] per quad (for the grid's swims)."""
    x0, y0, x1, y1 = box
    tris, walk, water = [], [], []
    t0, t1 = tile_of(x1 - 1e-6, y1 - 1e-6), tile_of(x0, y0)
    for tx in range(t0[0], t1[0] + 1):
        for ty in range(t0[1], t1[1] + 1):
            root = world.root(tx, ty)
            if root is None:
                continue
            V, holes, top = terrain(root)
            # (the quads over the box)
            X0, Y0 = (32 - ty) * T, (32 - tx) * T
            i0, i1 = max(0, int((X0 - x1) // Q)), min(127, int((X0 - x0) // Q))
            j0, j1 = max(0, int((Y0 - y1) // Q)), min(127, int((Y0 - y0) // Q))
            if i0 > i1 or j0 > j1:
                continue
            I, J = np.meshgrid(np.arange(i0, i1 + 1), np.arange(j0, j1 + 1), indexing="ij")
            I, J = I.ravel(), J.ravel()
            ok = ~holes[I, J] & np.isfinite(V[I, J]) & np.isfinite(V[I + 1, J]) & np.isfinite(V[I, J + 1]) & np.isfinite(V[I + 1, J + 1])
            I, J = I[ok], J[ok]

            def P(a, b):
                return np.stack([X0 - a * Q, Y0 - b * Q, V[a, b]], -1)
            A, B, C, D = P(I, J), P(I + 1, J), P(I, J + 1), P(I + 1, J + 1)
            g = (V[I, J] + V[I + 1, J] + V[I, J + 1] + V[I + 1, J + 1]) / 4
            wt = top[I, J]
            deep = np.isfinite(wt) & (wt - g > WADE)
            tris.append(np.stack([A, B, D], 1))
            tris.append(np.stack([A, D, C], 1))
            walk.append(~deep)
            walk.append(~deep)
            for k in np.nonzero(np.isfinite(wt))[0]:
                water.append((X0 - (I[k] + 1) * Q, Y0 - (J[k] + 1) * Q, X0 - I[k] * Q, Y0 - J[k] * Q, float(wt[k]),
                               float(g[k])))
    if not tris:
        return np.zeros((0, 3, 3)), np.zeros(0, bool), water
    return np.concatenate(tris), np.concatenate(walk), water


def model_triangles(world: World, box) -> np.ndarray:
    """The WMOs' and doodads' collision faces over `box` (N, 3, 3), world."""
    from . import doodads, walknet

    x0, y0, x1, y1 = box
    parts = []
    near = []
    for p in world.placements:
        b = p.bounds
        if p.uid in world.skip or b[2] < x0 or b[0] > x1 or b[3] < y0 or b[1] > y1:
            continue
        near.append(p)
        F = world.faces(p.wmo)
        if not len(F):
            continue
        xf = walknet.Placed(p)
        W = F @ xf.m.T + xf.o
        lo, hi = W.min(axis=1), W.max(axis=1)
        sel = (hi[:, 0] >= x0) & (lo[:, 0] <= x1) & (hi[:, 1] >= y0) & (lo[:, 1] <= y1)
        if sel.any():
            parts.append(W[sel])
    ds = doodads.adt_doodads(world.cd, world.cont, box)
    for p in near:
        ds += doodads.wmo_doodads(world.cd, p, box)
    for d in ds:
        D = doodads.triangles(world.cd, d)
        if D is not None and len(D):
            D = np.asarray(D, float)
            lo, hi = D.min(axis=1), D.max(axis=1)
            sel = (hi[:, 0] >= x0) & (lo[:, 0] <= x1) & (hi[:, 1] >= y0) & (lo[:, 1] <= y1)
            if sel.any():
                parts.append(D[sel])
    return np.concatenate(parts) if parts else np.zeros((0, 3, 3))


def tile_triangles(world: World, tx: int, ty: int, pad: float = PAD):
    """(triangles, walkable, water, box) of map tile (tx, ty) and `pad` yards round it."""
    bx = tile_box(tx, ty)
    box = (bx[0] - pad, bx[1] - pad, bx[2] + pad, bx[3] + pad)
    Tt, wt, water = terrain_triangles(world, box)
    M = model_triangles(world, box)
    T_ = np.concatenate([Tt, M]) if len(M) else Tt
    walk = np.concatenate([wt, RM._walkable(M)]) if len(M) else wt
    # (the terrain's walkable by its slope too)
    walk[:len(Tt)] &= RM._walkable(Tt) if len(Tt) else walk[:0]
    return T_, walk, water, box


# --- Recast ------------------------------------------------------------------------------------------------------------

def navbuild(T_: np.ndarray, walk: np.ndarray, box) -> bytes:
    """navbuild.exe over the triangles (recastmesh.run_recast's input), clipped to `box`: its raw output."""
    V = T_.reshape(-1, 3)[:, [0, 2, 1]].astype(np.float32)
    n = len(T_)
    idx = np.arange(n * 3, dtype=np.int32)
    areas = np.where(walk, 63, 0).astype(np.uint8)
    zmin, zmax = float(V[:, 1].min()) - 1, float(V[:, 1].max()) + 1
    # (the box in Recast's axes: x, up, z = world x, height, world y)
    bmin = np.array([box[0], zmin, box[1]], np.float32)
    bmax = np.array([box[2], zmax, box[3]], np.float32)
    with tempfile.TemporaryDirectory() as td:
        inp, out = Path(td) / "in.bin", Path(td) / "out.bin"
        with inp.open("wb") as f:
            f.write(b"AGNI")
            f.write(struct.pack("<6f", RM.CELL, RM.CELL_H, RM.AGENT_HEIGHT, RM.AGENT_RADIUS, RM.AGENT_CLIMB, RM.MAX_EDGE))
            f.write(struct.pack("<3f", *bmin))
            f.write(struct.pack("<3f", *bmax))
            f.write(struct.pack("<II", n * 3, n))
            f.write(V.tobytes())
            f.write(idx.tobytes())
            f.write(areas.tobytes())
        r = subprocess.run([str(RM.tool()), str(inp), str(out)], capture_output=True, text=True)
        if r.returncode != 0:
            raise RuntimeError(f"navbuild failed ({r.returncode}): {r.stderr}")
        return out.read_bytes()


def parse(b: bytes) -> list:
    """navbuild's output as polys: [(verts (k, 3) world x, y, z, [neighbor poly index or -1 / -2 a sub-tile's side])],
    the sub-tiles' polys numbered one after another (a side's neighbor is matched by joined edges in `join_sides`)."""
    assert b[:4] == b"AGNT"
    (ntiles,) = struct.unpack_from("<I", b, 4)
    o = 8
    polys = []
    for _ in range(ntiles):
        _tx, _ty, nv, npoly, nvp = struct.unpack_from("<iiIII", b, o)
        o += 20
        raw = np.frombuffer(b, np.float32, nv * 3, o).reshape(-1, 3)
        o += nv * 12
        verts = np.stack([raw[:, 0], raw[:, 2], raw[:, 1]], -1).astype(float)
        base = len(polys)
        for _ in range(npoly):
            vals = struct.unpack_from("<%dH" % (nvp * 2), b, o)
            o += nvp * 4
            area = b[o]
            o += 1
            vs = [v for v in vals[:nvp] if v != 0xFFFF]
            ns = []
            for nb in vals[nvp:nvp + len(vs)]:
                ns.append(-1 if nb == 0xFFFF else -2 if nb & 0x8000 else base + nb)
            polys.append((verts[vs], ns, area))
    return polys


def join_sides(polys: list, tol: float = 0.15, climb: float = 2.0) -> list:
    """Each poly's neighbors [set of poly indices], its sub-tiles' sides joined where two polys' side edges overlap on
    one line within `climb` yards in height (navmesh.NavMesh._across's rule)."""
    nb = [set(n for n in ns if n >= 0) for _v, ns, _a in polys]
    side = {}  # (axis, rounded coordinate) -> [(poly, a, b)]
    for pi, (vs, ns, _a) in enumerate(polys):
        k = len(vs)
        for e, n in enumerate(ns):
            if n != -2:
                continue
            a, b = vs[e], vs[(e + 1) % k]
            for ax in (0, 1):
                if abs(a[ax] - b[ax]) < tol:
                    side.setdefault((ax, round(a[ax] / 0.4)), []).append((pi, a, b))
    for (ax, _c), es in side.items():
        o = 1 - ax
        es.sort(key=lambda e: min(e[1][o], e[2][o]))
        for x in range(len(es)):
            p, a, b = es[x]
            lo, hi = min(a[o], b[o]), max(a[o], b[o])
            for y in range(x + 1, len(es)):
                q, c, d = es[y]
                lo2, hi2 = min(c[o], d[o]), max(c[o], d[o])
                if lo2 >= hi:
                    break
                if p == q or min(hi, hi2) - max(lo, lo2) < 0.01:
                    continue

                def at(u, v, w):
                    t = 0.0 if abs(v[o] - u[o]) < 1e-9 else (w - u[o]) / (v[o] - u[o])
                    return u[2] + (v[2] - u[2]) * t
                m0, m1 = max(lo, lo2), min(hi, hi2)
                if abs(at(a, b, m0) - at(c, d, m0)) <= climb and abs(at(a, b, m1) - at(c, d, m1)) <= climb:
                    nb[p].add(q)
                    nb[q].add(p)
    return nb


def load_tile(cont: int, tx: int, ty: int):
    """A built tile's mesh: (polys [(verts, neis, area)], neighbors [set]) or None (not built, or nothing walkable)."""
    p = tile_path(cont, tx, ty)
    if not p.exists() or p.stat().st_size < 12:
        return None
    polys = parse(p.read_bytes())
    return polys, join_sides(polys)


# --- building, many at once --------------------------------------------------------------------------------------------

_W: dict = {}


def _worker_init(wow_path: str, product: str, ref: str):
    from .extract.spike import ClientData

    _W["cd"] = ClientData(Path(wow_path), product, Path(ref))


def build_tile(job) -> dict:
    """One tile's mesh (a worker's job): writes its .bin (and its water, .water.npy); its numbers."""
    cont, tx, ty = job
    t = time.time()
    w = _W.get(("world", cont))
    if w is None:
        w = _W[("world", cont)] = World(_W["cd"], cont)
    try:
        T_, walk, water, box = tile_triangles(w, tx, ty)
        out = tile_path(cont, tx, ty)
        out.parent.mkdir(parents=True, exist_ok=True)
        if not len(T_) or not walk.any():
            out.write_bytes(b"AGNT\0\0\0\0")
            b = b""
        else:
            b = navbuild(T_, walk, box)
            out.write_bytes(b)
        np.save(out.with_suffix(".water.npy"), np.array(water, np.float32).reshape(-1, 6))
        return {"cont": cont, "tile": [tx, ty], "tris": int(len(T_)), "bytes": len(b), "s": round(time.time() - t, 1),
                "ok": True}
    except Exception as e:  # (one tile's failure is reported, the rest go on)
        return {"cont": cont, "tile": [tx, ty], "ok": False, "err": repr(e)[:300], "s": round(time.time() - t, 1)}


def models_path(cont: int, tx: int, ty: int) -> Path:
    """A tile's building and prop collision triangles (WMOs' and doodads', world yards), for the grid's wall cut."""
    return tile_path(cont, tx, ty).with_suffix(".models.npy")


def model_tile(job) -> dict:
    """One tile's model collision triangles saved (a worker's job; item 72: the grid's links cut where they cross a
    model's wall the mesh's voxels lost, a palisade, a fence, a barricade)."""
    cont, tx, ty = job
    t = time.time()
    w = _W.get(("world", cont))
    if w is None:
        w = _W[("world", cont)] = World(_W["cd"], cont)
    try:
        bx = tile_box(tx, ty)
        box = (bx[0] - PAD, bx[1] - PAD, bx[2] + PAD, bx[3] + PAD)
        M = model_triangles(w, box)
        out = models_path(cont, tx, ty)
        out.parent.mkdir(parents=True, exist_ok=True)
        np.save(out, np.asarray(M, np.float32).reshape(-1, 3, 3))
        return {"cont": cont, "tile": [tx, ty], "tris": int(len(M)), "ok": True, "s": round(time.time() - t, 1)}
    except Exception as e:
        return {"cont": cont, "tile": [tx, ty], "ok": False, "err": repr(e)[:300], "s": round(time.time() - t, 1)}


def build_models(jobs: list, wow_path: str, product: str, workers: int = 6, log=print) -> list:
    """Every tile's model triangles (model_tile) in `workers` processes."""
    import multiprocessing as mp

    from .paths import data_dir as dd

    out = []
    t0 = time.time()
    with mp.get_context("spawn").Pool(workers, initializer=_worker_init, initargs=(wow_path, product, str(dd() / "ref")),
                                      maxtasksperchild=40) as pool:
        for k, r in enumerate(pool.imap_unordered(model_tile, jobs), 1):
            out.append(r)
            if not r["ok"] or k % 50 == 0 or k == len(jobs):
                log(f"  models {k}/{len(jobs)} tiles ({time.time() - t0:.0f} s){'' if r['ok'] else ': ' + str(r)}")
    return out


def build(jobs: list, wow_path: str, product: str, workers: int = 6, log=print) -> list:
    """The tiles' meshes in `workers` processes (each reads the client once); their numbers, as they finish."""
    import multiprocessing as mp

    from .paths import data_dir as dd

    out = []
    t0 = time.time()
    ctx = mp.get_context("spawn")
    with ctx.Pool(workers, initializer=_worker_init, initargs=(wow_path, product, str(dd() / "ref")),
                  maxtasksperchild=40) as pool:
        for k, r in enumerate(pool.imap_unordered(build_tile, jobs), 1):
            out.append(r)
            if not r["ok"] or k % 25 == 0 or k == len(jobs):
                log(f"  {k}/{len(jobs)} tiles ({time.time() - t0:.0f} s){'' if r['ok'] else ': ' + str(r)}")
    return out
