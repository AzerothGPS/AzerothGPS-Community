"""Walk grids for the buildings and interiors out in the open world (1.4.2, item 119; Kooki3z 2026-11-26: "if its less
than 10mb, start that with the rebake fix for cities for 1.4.2"). Phase A: the data only, nothing routed on it yet.

The city grids' recipe (citygrid.py) over each building model's own Recast mesh, in the model's own frame, so one grid
serves every placement of the model (an inn placed in six towns is baked once):

1. **Inventory** (`inventory`): every WMO placed on the continents (and Zephras Isle) outside the capitals' models, not a
   cave (caves.CAVE_KINDS: their own data), not a prop (PROP: walls, bridges, fences, docks, tents, boats...), at least
   MIN_SIDE yards and at most MAX_SIDE across (the bigger ones are landscape: the world grid's).
2. **Variants** (`variants`): placements share a grid when they place the same model with the same colliding doodads,
   tilted at most TILT_DEG with every floor within SHARE_ERR of the untilted grid (item 129; the shared grid is then
   baked untilted), and the land meets the model alike (`ground_sig`: the terrain against the model's floors at its
   ground floor, within SIG_Z). One tilted more, another doodad set, or one sunk into the land or raised off it gets its
   own (its first placement's).
3. **Triangles** (`variant_triangles`, needs the client: run where WoW Forever is installed): the model's collision faces
   (walknet.model_faces), its placement's doodads (doodads.wmo_doodads) and the land round it (caves.Ground, GROUND_PAD
   yards, every GROUND_STEP), turned into the variant's frame: the placement's origin, turned back by its yaw (its tilt
   kept: the floors' slopes are the world's). Saved per variant under data/buildinggrid/tris/ (dev data, never shipped).
4. **Grid** (`build`, Recast and the grid: no client needed): navbuild.exe over the triangles, citygrid's surfaces
   (CELL yards) and links. Kept: the model's own floors (a surface within FLOOR_Z of the model's walkable faces there, not
   the land's) reached from a door (their piece of the grid also holds the land round the model) or an NPC's spot (Data/
   Npcs.lua's spawns in it), and the land's surfaces linked to them (each door's step, F_DOOR). Pieces smaller than
   MIN_PIECE no NPC stands on are left out (a roof's ledge).
5. **Encoding** (`encode`): the world grid's (worldbake.encode_tiles) over the variant's box, one string: cell counts |
   records (flags, point) | heights against their prediction | links against those the heights imply; run-length coded.

Format (Data in each region's load-on-demand folder, AzerothGPS_WG<cont>_<rx>_<ry>/Buildings.lua, worldbake.REGION):
`AzerothGPS_BuildingGrids["<cont>:<rx>:<ry>"] = { bake, cell, zq, z0, implied, m = { [variant] = "x0,y0,w,h|counts|recs|
zs|links" }, p = "variant,x,y,z,yaw;..." }`: x0, y0 the box's corner in the variant's frame (yards), a placement's world
point (X, Y, Z) is frame point (lx, ly, lz) = turned by -yaw about (x, y), less z. Each variant's grid is in every region
it's placed in (each region loads alone).
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
from collections import defaultdict
from pathlib import Path

import numpy as np

from . import citygrid as CGP
from .paths import data_dir

CELL = 2.0  # yards a cell (item 119's measure: 2 yd, the city grids' Undercity and Thunder Bluff)
ZQ = 0.25  # yards a height step (the city grid's)
Z0 = -256.0  # (an escaped height: 3 characters from Z0, the frame's heights)
IMPLIED_Q = 8  # height steps (2 yd): a link the heights imply (worldbake.IMPLIED_Q's rule at this ZQ)
MIN_SIDE = 8.0  # yards: a smaller model is a prop
MAX_SIDE = 400.0  # yards: a bigger model is landscape (the world grid's)
GROUND_PAD = 10.0  # yards of the land round a model built with it (its doors' outsides)
GROUND_STEP = 1.0  # yards between the land's samples ...
GROUND_STEP_BIG = 2.0  # ... round a model bigger than BIG_SIDE yards across
BIG_SIDE = 120.0
FLOOR_Z = 1.5  # yards: a surface this near a model walkable face's height there (and nearer it than the land) is the model's
MIN_PIECE = 6  # surfaces: smaller pieces no NPC stands on are left out
NPC_PAD = 2.0  # yards round a model's box an NPC's spawn is taken as standing in it
NPC_Z = 3.0  # yards: an NPC's spawn is on a surface this near its height
SIG_Z = 1.5  # yards: two placements' land differs against the model's floors by more than this somewhere: two variants
SIG_STEP = 4.0  # yards between the ground signature's points
SIG_CLIP = 3.0  # yards: the land this far under a floor or more is the same to it (no door), this far over too
TILT_DEG = 5.0  # degrees: a placement tilted more has a grid of its own (item 129) ...
SHARE_ERR = 0.5  # ... and one tilted less shares its model's when its floors are within this many yards of the shared
# grid's everywhere (half a step: recastmesh.AGENT_CLIMB)
F_DOOR, F_REACH = 1, 4  # (records' flags: a door's step on the land; a piece only an NPC's spot reaches)

# (worldbake.inv's prop filter, the research's: item 119's inventory of 459 models / 2,111 placements)
PROP = re.compile(r"collidable ?doodads|collisionwall|collisionpane|/transports/|/elevators/|skywall|bridge|fence|wall(?!ed)"
                  r"|dock|pier|lamppost|gate(?!house)|arch(?!ive)|statue|tent|boat|ship(?!wreck)|wagon|cart|pillar"
                  r"|fountain|well\b|signpost|lumber|pylon", re.I)
CONTS = (0, 1, 2991)


def work_dir() -> Path:
    """The bake's dev data (the inventory, each variant's triangles): data/buildinggrid, or AGPS_BUILDINGGRID_DIR."""
    env = os.environ.get("AGPS_BUILDINGGRID_DIR")
    return Path(env) if env else data_dir() / "buildinggrid"


def tris_dir() -> Path:
    return work_dir() / "tris"


def out_dir() -> Path:
    return data_dir() / "debug" / "buildinggrid"


# --- the inventory (needs the client) ---------------------------------------------------------------------------------

def inventory(cd, conts=CONTS, log=print, spawns=None) -> list:
    """[{cont, uid, wmo, path, kind, x, y, z, yaw, rx, rz, tilt, doodad_set, bounds, bbox}]: the building placements
    (kind "building"), and the props an NPC stands in (kind "npc": Thandol Span's insides, Foggy
    MacKreel's; only the floors an NPC stands on are kept, `build`)."""
    from . import interiors as I
    from .capitals import CAPITALS
    from .caves import CAVE_KINDS, CAVE_PLACEMENTS
    from .gridcheck import shipped_spawns

    spawns = shipped_spawns() if spawns is None else spawns
    by_cont = defaultdict(list)
    for _nid, _name, level, x, y, z in spawns:
        by_cont[level].append((x, y, z))
    out, wcache = [], {}
    for cont in conts:
        cap = {uid for c in CAPITALS if c.cont == cont for uid in c.wmos}
        try:
            from . import cities
            if cont == 0:
                cap.add(cities.placement(cd)[0].uid)
        except Exception:
            pass
        sp = np.array(by_cont.get(cont, []), float).reshape(-1, 3)
        for p in I.placements(cd, cont):
            if p.uid in cap:
                continue
            if p.wmo not in wcache:
                wcache[p.wmo] = I.read_wmo(cd, p.wmo)
            w = wcache[p.wmo]
            path = (cd.name(p.wmo) or "").lower()
            parts = path.split("/")
            if not w or (len(parts) >= 4 and parts[2] == "dungeon" and parts[3] in CAVE_KINDS) or p.uid in CAVE_PLACEMENTS:
                continue
            b = w.bbox
            side = max(b[3] - b[0], b[4] - b[1])
            kind = "building"
            if side > MAX_SIDE:
                continue  # (landscape: the world grid's)
            if PROP.search(path):
                bx = p.bounds
                inside = ((sp[:, 0] >= bx[0]) & (sp[:, 0] <= bx[2]) & (sp[:, 1] >= bx[1]) & (sp[:, 1] <= bx[3])
                          & (sp[:, 2] >= p.z + b[2] - 1) & (sp[:, 2] <= p.z + b[5] + 1))
                if not inside.any():
                    continue
                kind = "npc"
            elif side < MIN_SIDE:
                continue
            out.append(dict(cont=cont, uid=p.uid, wmo=p.wmo, path=path, kind=kind, x=p.x, y=p.y, z=p.z, yaw=p.yaw,
                            rx=p.rx, rz=p.rz, tilt=p.tilt, doodad_set=p.doodad_set, bounds=list(p.bounds), bbox=list(b)))
    nb = [r for r in out if r["kind"] == "building"]
    log(f"  {len(nb)} building placements of {len({r['wmo'] for r in nb})} models; {len(out) - len(nb)} props an NPC "
        f"stands in")
    return out


# --- frames ----------------------------------------------------------------------------------------------------------

def frame_turn(yaw: float) -> np.ndarray:
    """The 3x3 turn from a variant's frame to the world's: about the up axis by yaw + 180 (walknet.Placed's)."""
    t = math.radians(yaw + 180)
    c, s = math.cos(t), math.sin(t)
    return np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]])


def to_frame(W: np.ndarray, r: dict) -> np.ndarray:
    """World points (..., 3) into placement r's frame."""
    return (np.asarray(W, float) - np.array([r["x"], r["y"], r["z"]])) @ frame_turn(r["yaw"])


def to_world(L: np.ndarray, r: dict) -> np.ndarray:
    return np.asarray(L, float) @ frame_turn(r["yaw"]).T + np.array([r["x"], r["y"], r["z"]])


def _placement(r: dict):
    from . import interiors as I
    return I.Placement(r["wmo"], r["uid"], r["x"], r["y"], r["z"], r["yaw"], r["tilt"], tuple(r["bounds"]), 0,
                       r["rx"], r["rz"], r["doodad_set"])


def model_world(cd, r: dict, cache: dict | None = None):
    """(floor triangles, all collision triangles) of placement r's model, world (N, 3, 3)."""
    from . import capitals, walknet
    key = r["wmo"]
    got = cache.get(key) if cache is not None else None
    if got is None:
        fl, wl, _lq = walknet.model_faces(cd, r["wmo"], capitals.FLOOR_SLOPE)
        F = np.array([t for _g, _z, t in fl], float).reshape(-1, 3, 3)
        A = np.array([t for _g, _z, t in fl] + [t for _g, _z, t in wl], float).reshape(-1, 3, 3)
        got = (F, A)
        if cache is not None:
            cache[key] = got
    xf = walknet.Placed(_placement(r))
    F, A = got
    return F @ xf.m.T + xf.o, A @ xf.m.T + xf.o


def ground_sig(ground, r: dict, floors_w: np.ndarray) -> np.ndarray:
    """The land against the model's ground floor: at every SIG_STEP over the model's floors' footprint (its frame's
    grid, so alike placements' points are alike), the terrain's height less the lowest floor's there (nan: none)."""
    L = to_frame(floors_w.reshape(-1, 3), r).reshape(-1, 3, 3)
    bb = r["bbox"]  # (the model's own box: alike for each placement of it)
    lo, hi = (bb[0], bb[1]), (bb[3], bb[4])
    xs = np.arange(math.floor(lo[0] / SIG_STEP) * SIG_STEP, hi[0] + 1e-6, SIG_STEP)
    ys = np.arange(math.floor(lo[1] / SIG_STEP) * SIG_STEP, hi[1] + 1e-6, SIG_STEP)
    fz = _lowest_on(L, xs, ys).ravel()
    X, Y = np.meshgrid(xs, ys, indexing="ij")
    P = np.stack([X.ravel(), Y.ravel()], -1)
    Wp = to_world(np.c_[P, np.zeros(len(P))], r)
    h, ok = ground.sample(Wp[:, 0], Wp[:, 1])
    h = np.where(np.asarray(ok, bool), np.asarray(h, float), np.nan) - r["z"]
    # (clipped: land well under a floor (no door there) is alike however far under; land well over one alike too)
    return np.where(np.isfinite(fz), np.clip(h - fz, -SIG_CLIP, SIG_CLIP), np.nan)


def _lowest_on(T: np.ndarray, xs: np.ndarray, ys: np.ndarray) -> np.ndarray:
    """(len(xs), len(ys)): at each grid point the lowest of the triangles' heights over it (nan: none)."""
    out = np.full((len(xs), len(ys)), np.inf)
    if not len(xs) or not len(ys):
        return out
    sx, sy = (xs[1] - xs[0]) if len(xs) > 1 else 1.0, (ys[1] - ys[0]) if len(ys) > 1 else 1.0
    for t in T:
        lo, hi = t[:, :2].min(axis=0), t[:, :2].max(axis=0)
        i0, i1 = max(0, int(math.ceil((lo[0] - xs[0]) / sx - 1e-9))), min(len(xs) - 1, int(math.floor((hi[0] - xs[0]) / sx + 1e-9)))
        j0, j1 = max(0, int(math.ceil((lo[1] - ys[0]) / sy - 1e-9))), min(len(ys) - 1, int(math.floor((hi[1] - ys[0]) / sy + 1e-9)))
        if i0 > i1 or j0 > j1:
            continue
        a, b, c = t
        d = (b[1] - c[1]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[1] - c[1])
        if abs(d) < 1e-9:
            continue
        X, Y = np.meshgrid(xs[i0:i1 + 1], ys[j0:j1 + 1], indexing="ij")
        u = ((b[1] - c[1]) * (X - c[0]) + (c[0] - b[0]) * (Y - c[1])) / d
        v = ((c[1] - a[1]) * (X - c[0]) + (a[0] - c[0]) * (Y - c[1])) / d
        w = 1 - u - v
        z = np.where((u >= -1e-6) & (v >= -1e-6) & (w >= -1e-6), u * a[2] + v * b[2] + w * c[2], np.inf)
        sub = out[i0:i1 + 1, j0:j1 + 1]
        np.minimum(sub, z, out=sub)
    return np.where(np.isfinite(out), out, np.nan)


_DSIG: dict = {}


def doodad_sig(cd, wmo: int, dset: int) -> tuple:
    """The doodads with collision a placement of the model with doodad set `dset` brings (set 0 and its own;
    doodads.wmo_doodads), as (FileDataID, its spot in the model to a tenth of a yard): two sets alike here are one grid
    (a set's other doodads are decoration a character walks through)."""
    key = (wmo, dset)
    got = _DSIG.get(key)
    if got is None:
        from . import doodads as DD
        sets, dd = DD._wmo_sets(cd, wmo)
        use = set()
        for k in {0, dset}:
            if k < len(sets):
                first, count = sets[k]
                use.update(range(first, first + count))
        got = tuple(sorted((dd[j][0], tuple(round(v, 1) for v in dd[j][1])) for j in use
                           if j < len(dd) and dd[j][0] and DD.m2_collision(cd, dd[j][0]) is not None))
        _DSIG[key] = got
    return got


def tilt_err(cd, r: dict, cache: dict) -> float:
    """Yards: the farthest any of placement r's model floors' corners lies from where its model's untilted grid puts it
    (the placement's own turn and tilt against its yaw alone)."""
    F, _A = model_world(cd, r, cache)
    if not len(F):
        return 0.0
    flat = dict(r, rx=0.0, rz=0.0, tilt=0.0)
    G, _B = model_world(cd, flat, cache)
    return float(np.linalg.norm((F - G).reshape(-1, 3), axis=1).max())


def variants(cd, rows: list, log=print) -> list:
    """[{id, ref (a placement row), members [uids]}]: the placements grouped into shared grids (the module's doc)."""
    from .caves import Ground
    grounds, cache = {}, {}
    by = defaultdict(list)
    for r in rows:
        # (item 129, Kooki3z 2026-11-26: a placement tilted up to TILT_DEG shares its model's untilted grid when its
        # floors stay within SHARE_ERR of the grid's everywhere, its building's edges too)
        r["tilt_err"] = 0.0
        if r["tilt"] > 0.01:
            try:
                r["tilt_err"] = tilt_err(cd, r, cache)
            except Exception:  # noqa: BLE001
                r["tilt_err"] = math.inf
        own = r["tilt"] > TILT_DEG or r["tilt_err"] > SHARE_ERR
        by[(r["wmo"], doodad_sig(cd, r["wmo"], r["doodad_set"]), r["uid"] if own else 0, r["kind"])].append(r)
    out = []
    for key in sorted(by):
        groups = []  # [(sig, ref, members)]
        for r in sorted(by[key], key=lambda q: (q["tilt"], q["uid"])):
            g = grounds.get(r["cont"])
            if g is None:
                g = grounds[r["cont"]] = Ground(cd, r["cont"])
            try:
                F, _A = model_world(cd, r, cache)
                sig = ground_sig(g, r, F) if len(F) else np.zeros(0)
            except Exception as e:  # noqa: BLE001
                log(f"  {r['uid']} {r['path']}: {e}")
                continue
            r["sig_n"] = int(np.isfinite(sig).sum())
            for gs in groups:
                a, b = gs[0], sig
                if len(a) != len(b):
                    continue
                both = np.isfinite(a) & np.isfinite(b)
                # (the land over a floor in one and not the other, or the ground floor's step off the land unlike)
                if not (np.abs(a[both] - b[both]) > SIG_Z).any():
                    gs[2].append(r["uid"])
                    break
            else:
                groups.append((sig, r, [r["uid"]]))
        for _sig, ref, members in groups:
            # (shared: the model's grid untilted, each member's floors within SHARE_ERR of it)
            flat = key[2] == 0 and ref["tilt"] > 0.01
            out.append({"id": len(out) + 1, "ref": ref, "members": members, "flat": flat})
    log(f"  {len(rows)} placements into {len(out)} grids ({len(by)} model and doodad set pairs)")
    return out


def variant_triangles(cd, v: dict, ground=None, cache=None, spawns=None) -> dict:
    """The variant's sources in its frame: {T (N, 3, 3) all, walk (N), nm (the model's own first nm), floors (the model's
    walkable faces), npcs (K, 3)}."""
    from . import doodads
    from .caves import Ground
    r = v["ref"]
    if v.get("flat"):
        r = dict(r, rx=0.0, rz=0.0, tilt=0.0)
    F, A = model_world(cd, r, cache)
    parts = [A]
    p = _placement(r)
    for d in doodads.wmo_doodads(cd, p):
        D = doodads.triangles(cd, d)
        if D is not None and len(D):
            parts.append(np.asarray(D, float))
    nm = sum(len(q) for q in parts)
    M = np.concatenate(parts) if parts else np.zeros((0, 3, 3))
    # (the land round it, world)
    g = ground or Ground(cd, r["cont"])
    x0, y0 = M[:, :, 0].min() - GROUND_PAD, M[:, :, 1].min() - GROUND_PAD
    x1, y1 = M[:, :, 0].max() + GROUND_PAD, M[:, :, 1].max() + GROUND_PAD
    step = GROUND_STEP if max(x1 - x0, y1 - y0) <= BIG_SIDE + 2 * GROUND_PAD else GROUND_STEP_BIG
    xs = np.arange(x0, x1 + step, step)
    ys = np.arange(y0, y1 + step, step)
    X, Y = np.meshgrid(xs, ys, indexing="ij")
    h, ok = g.sample(X.ravel(), Y.ravel())
    H = np.asarray(h, float).reshape(X.shape)
    OK = np.asarray(ok, bool).reshape(X.shape) & np.isfinite(H)
    q = OK[:-1, :-1] & OK[1:, :-1] & OK[:-1, 1:] & OK[1:, 1:]
    ii, jj = np.nonzero(q)
    land = []
    if len(ii):
        def P(a, b):
            return np.stack([X[a, b], Y[a, b], H[a, b]], -1)
        A_, B_, C_, D_ = P(ii, jj), P(ii + 1, jj), P(ii, jj + 1), P(ii + 1, jj + 1)
        land = [np.stack([A_, B_, D_], 1), np.stack([A_, D_, C_], 1)]
    T = np.concatenate([M] + land) if land else M
    from . import recastmesh as RM
    walk = RM._walkable(T)
    Tf = to_frame(T.reshape(-1, 3), r).reshape(-1, 3, 3)
    Ff = to_frame(F.reshape(-1, 3), r).reshape(-1, 3, 3)
    npcs = []
    b = r["bounds"]
    for nid, _name, level, x, y, z in (spawns or []):
        if level == r["cont"] and b[0] - NPC_PAD <= x <= b[2] + NPC_PAD and b[1] - NPC_PAD <= y <= b[3] + NPC_PAD:
            npcs.append((x, y, z, nid))
    N = np.array([to_frame(np.array([n[:3]]), r)[0].tolist() + [n[3]] for n in npcs], float).reshape(-1, 4)
    return {"T": Tf.astype(np.float32), "walk": walk, "nm": nm, "floors": Ff.astype(np.float32), "npcs": N}


def extract(cd, only=None, log=print) -> dict:
    """The inventory, the variants and every variant's triangles into data/buildinggrid/ (needs the client).
    `only`: path substrings or uids: only those variants' triangles (the index is always whole)."""
    from .caves import Ground
    from .gridcheck import shipped_spawns
    spawns = shipped_spawns()
    rows = inventory(cd, log=log, spawns=spawns)
    vs = variants(cd, rows, log)
    d = tris_dir()
    d.mkdir(parents=True, exist_ok=True)
    index = {"rows": rows, "variants": [{"id": v["id"], "ref": v["ref"]["uid"], "members": v["members"],
                                         "flat": v.get("flat", False)} for v in vs]}
    (work_dir() / "index.json").write_text(json.dumps(index), encoding="utf-8")
    grounds, cache, n = {}, {}, 0
    for v in vs:
        r = v["ref"]
        if only and not any(o in r["path"] or o in {str(u) for u in v["members"]} for o in only):
            continue
        g = grounds.get(r["cont"]) or grounds.setdefault(r["cont"], Ground(cd, r["cont"]))
        try:
            src = variant_triangles(cd, v, g, cache, spawns)
        except Exception as e:  # noqa: BLE001
            log(f"  variant {v['id']} ({r['path']}): {e}")
            continue
        np.savez_compressed(d / f"{v['id']}.npz", T=src["T"], walk=src["walk"], nm=src["nm"], floors=src["floors"],
                            npcs=src["npcs"], npc_only=r["kind"] == "npc")
        n += 1
    log(f"  {n} variants' triangles in {d}")
    return index


# --- the grid (no client) ---------------------------------------------------------------------------------------------

class _Model:
    name = "building"
    level = None
    cont = 0


def _floor_heights(floors: np.ndarray, x0: float, y0: float, w: int, h: int, cell: float) -> dict:
    """{(i, j): [heights]}: the model's walkable faces' heights at each cell's middle (or their points nearest it)."""
    from . import navmesh as NM
    out = defaultdict(list)
    for t in floors:
        vs = [tuple(map(float, p)) for p in t]
        xs, ys = [p[0] for p in vs], [p[1] for p in vs]
        i0, i1 = max(0, int((min(xs) - x0) // cell)), min(w - 1, int((max(xs) - x0) // cell))
        j0, j1 = max(0, int((min(ys) - y0) // cell)), min(h - 1, int((max(ys) - y0) // cell))
        for i in range(i0, i1 + 1):
            for j in range(j0, j1 + 1):
                mx, my = x0 + (i + 0.5) * cell, y0 + (j + 0.5) * cell
                if NM._in_poly(vs, mx, my):
                    px, py = mx, my
                else:
                    px, py = NM._closest_on_poly(vs, mx, my)
                    if not (x0 + i * cell - 1e-6 <= px <= x0 + (i + 1) * cell + 1e-6
                            and y0 + j * cell - 1e-6 <= py <= y0 + (j + 1) * cell + 1e-6):
                        continue
                out[(i, j)].append(NM._height_on(vs, px, py))
    return out


def build(src: dict, cell: float = CELL, log=print):
    """The variant's grid (a citygrid.Grid, its frame), or None: the module's doc, step 4."""
    from . import recastmesh as RM
    T, walk = np.asarray(src["T"], float), np.asarray(src["walk"], bool)
    nm = int(src["nm"])
    if not len(T) or not walk[:nm].any():
        return None
    tiles = RM.run_recast(T, log=lambda *_a: None, walk=walk)
    mesh = CGP.Mesh(tiles, 0)
    if not mesh.vs:
        return None
    xs = [v[0] for vs in mesh.vs for v in vs]
    ys = [v[1] for vs in mesh.vs for v in vs]
    x0, y0 = math.floor(min(xs) / cell) * cell, math.floor(min(ys) / cell) * cell
    w, h = int((max(xs) - x0) // cell) + 1, int((max(ys) - y0) // cell) + 1
    samples = CGP.rasterize(mesh, x0, y0, w, h, cell)
    surf = {c: CGP.merge_cell(s, mesh) for c, s in samples.items()}
    links = CGP.build_links(surf, mesh, cell)
    city = CGP.City("building", "", 0, cell=cell)
    g = CGP.Grid(city, x0, y0, w, h, cell, surf, links, [])
    g.road_out = defaultdict(list)
    # (the model's own floors: near one of its walkable faces' heights there, nearer it than the land's)
    fh = _floor_heights(np.asarray(src["floors"], float), x0, y0, w, h, cell)
    land = _land_heights(T[nm:], x0, y0, w, h, cell)
    own = set()
    for (i, j), ss in surf.items():
        fz, lz = fh.get((i, j), ()), land.get((i, j))
        for k, s in enumerate(ss):
            if not fz:
                continue
            d = min(abs(z - s[0]) for z in fz)
            if d <= FLOOR_Z and (lz is None or d <= abs(lz - s[0])):
                own.add((i, j, k))
    piece, sizes = CGP.pieces(g)
    landp = {piece[n] for n in piece if n not in own}
    npc_nodes = set()
    for x, y, z, _nid in np.asarray(src["npcs"], float).reshape(-1, 4):
        n = CGP.surface_at(g, x, y, z, NPC_Z)
        if n is not None:
            npc_nodes.add(n)
    npcp = {piece.get(n) for n in npc_nodes}
    npc_only = bool(src.get("npc_only", False))
    if npc_only:  # (a prop's: only the pieces an NPC stands on the model's own floor of)
        npcp = {piece.get(n) for n in npc_nodes if n in own}
    keep = set()
    for n in own:
        p = piece.get(n)
        if p is None:
            continue
        if p in npcp or (not npc_only and p in landp and sizes[p] >= MIN_PIECE):
            keep.add(n)
    # (each door's step: the land's surfaces linked to a kept floor)
    door = set()
    for n in keep:
        for m, _c in CGP.neighbors(g, n):
            if m not in own:
                door.add(m)
    reach = {n for n in keep if piece.get(n) not in landp}
    CGP._prune(g, lambda n: n in keep or n in door)
    # (the flags, renumbered as _prune did: by order within each cell)
    remap = _remap(surf, keep | door)
    g.flags = {remap[n]: (F_DOOR if n in door else 0) | (F_REACH if n in reach else 0) for n in keep | door}
    g.kept_floors, g.doors, g.npcs = len(keep), len(door), len(npc_nodes)
    g.npc_nodes = {remap[n] for n in npc_nodes if n in remap}
    return g


def _remap(surf: dict, kept: set) -> dict:
    out = {}
    for (i, j), ss in surf.items():
        nk = 0
        for k in range(len(ss)):
            if (i, j, k) in kept:
                out[(i, j, k)] = (i, j, nk)
                nk += 1
    return out


def _land_heights(L: np.ndarray, x0, y0, w, h, cell) -> dict:
    """{(i, j): the land's height at the cell's middle} from the land's triangles (two a GROUND_STEP square)."""
    out = {}
    if not len(L):
        return out
    c = L.mean(axis=1)
    i = ((c[:, 0] - x0) // cell).astype(int)
    j = ((c[:, 1] - y0) // cell).astype(int)
    acc = defaultdict(list)
    for a, b, z in zip(i.tolist(), j.tolist(), c[:, 2].tolist()):
        acc[(a, b)].append(z)
    return {k: float(np.median(v)) for k, v in acc.items()}


# --- the encoding (the world grid's, worldbake.encode_tiles, over one box) ---------------------------------------------

def _box(g):
    ii = [c[0] for c in g.surf]
    jj = [c[1] for c in g.surf]
    return min(ii), min(jj), max(ii) - min(ii) + 1, max(jj) - min(jj) + 1


def encode(g) -> str:
    """"x0,y0,w,h|counts|recs|zs|links" (the module's doc; worldbake.encode_tiles' parts and rules, the implied links
    by the heights within IMPLIED_Q, every neighbor in the box)."""
    from .worldbake import ZESC, _rle
    A = CGP.ALPHA
    i0, j0, w, h = _box(g)
    zq = {}
    for (i, j), ss in g.surf.items():
        for k, s in enumerate(ss[:CGP.MAX_IN_CELL]):
            zq[(i, j, k)] = min(64 ** 3 - 1, max(0, int(round((s[0] - Z0) / ZQ))))

    def implied(i, j, k):
        row = []
        for dx, dy in CGP.DIRS:
            tt = g.surf.get((i + dx, j + dy), ())[:CGP.MAX_IN_CELL]
            best, bk = None, 0
            for kk in range(len(tt)):
                dz = abs(zq[(i + dx, j + dy, kk)] - zq[(i, j, k)])
                if best is None or dz < best:
                    best, bk = dz, kk + 1
            row.append(bk if best is not None and best <= IMPLIED_Q else 0)
        return row
    counts, recs, zs, lks = [], [], [], []
    last = None
    flags = getattr(g, "flags", {})
    for i in range(i0, i0 + w):
        prev_cell = []
        for j in range(j0, j0 + h):
            ss = g.surf.get((i, j), ())[:CGP.MAX_IN_CELL]
            counts.append(A[len(ss)])
            if not ss:
                prev_cell = []
                continue
            cell_z = []
            cx0, cy0 = g.x0 + i * g.cell, g.y0 + j * g.cell
            for k, s in enumerate(ss):
                ox = min(7, max(0, int((s[2] - cx0) / g.cell * 8)))
                oy = min(7, max(0, int((s[3] - cy0) / g.cell * 8)))
                recs.append(A[flags.get((i, j, k), 0)] + A[ox * 8 + oy])
                row = g.links.get((i, j, k), [-1] * 8)
                L = [row[d] + 1 if 0 <= row[d] < CGP.MAX_IN_CELL else 0 for d in range(8)]
                im = implied(i, j, k)
                diff = [(L[d] - im[d]) % 8 for d in range(8)]
                lks.append("0" if not any(diff) else "1" + "".join(A[diff[2 * m] * 8 + diff[2 * m + 1]] for m in range(4)))
                pred = prev_cell[k] if k < len(prev_cell) else (prev_cell[-1] if prev_cell else last)
                v = zq[(i, j, k)]
                dd = v - pred if pred is not None else 999
                zs.append(A[dd + 31] if -30 <= dd <= 30 else A[ZESC] + A[v >> 12] + A[(v >> 6) & 63] + A[v & 63])
                last = v
                cell_z.append(v)
            prev_cell = cell_z
    head = f"{g.x0 + i0 * g.cell:.0f},{g.y0 + j0 * g.cell:.0f},{w},{h}"
    return "|".join((head, _rle(counts), _rle(recs), _rle(zs), _rle(lks)))


def city_bytes(g) -> int:
    """The same grid in the city grids' format (citygrid.encode: 7 characters a surface, a character a cell)."""
    e = CGP.encode(g)
    return len(e["cells"]) + len(e["s"]) + len(e["links"]) + 6 * len(e["base"])


BAKE_PARAMS = ("CELL", "ZQ", "Z0", "IMPLIED_Q", "MIN_SIDE", "MAX_SIDE", "GROUND_PAD", "GROUND_STEP", "GROUND_STEP_BIG", "BIG_SIDE", "FLOOR_Z", "MIN_PIECE",
               "NPC_PAD", "NPC_Z", "SIG_Z", "SIG_STEP", "SIG_CLIP", "TILT_DEG", "SHARE_ERR")


def bake_stamp() -> str:
    """The building bake's parameters and the city grids' (one bake: `agps building-grid --write` writes both)."""
    g = globals()
    parts = [f"{k}={g[k]!r}" for k in BAKE_PARAMS] + [f"city={CGP.bake_stamp()}", f"PROP={PROP.pattern}"]
    return hashlib.sha1("|".join(parts).encode("utf-8")).hexdigest()[:12]


def bake_variant(vid: int, log=print) -> dict:
    """One variant's grid from its triangles: its numbers and its encoded string."""
    p = tris_dir() / f"{vid}.npz"
    d = np.load(p)
    src = {k: d[k] for k in d.files}
    g = build(src, log=log)
    if g is None or not g.surf:
        return {"id": vid, "surfaces": 0, "rle": "", "city_bytes": 0}
    s = encode(g)
    return {"id": vid, "surfaces": sum(min(len(ss), CGP.MAX_IN_CELL) for ss in g.surf.values()), "cells": len(g.surf), "floors": g.kept_floors, "doors": g.doors,
            "npcs": g.npcs, "rle": s, "rle_bytes": len(s), "city_bytes": city_bytes(g)}


def _bake_job(vid):
    try:
        return bake_variant(vid, log=lambda *_a: None)
    except Exception as e:  # noqa: BLE001
        return {"id": vid, "error": repr(e), "surfaces": 0, "rle": "", "city_bytes": 0}


# --- decoding (the tests', gridcheck's: the addon's reader comes with the routing, item 119's steps 4-5) ---------------

def _unrle(part: str, width) -> list:
    """A part's tokens (worldbake._rle undone): `width(part, i)` the token's length at i."""
    from .worldbake import REP
    A = CGP.ALPHA
    out, i = [], 0
    while i < len(part):
        if part[i] == REP:
            out += [out[-1]] * (A.index(part[i + 1]) + 2)
            i += 2
        else:
            n = width(part, i)
            out.append(part[i:i + n])
            i += n
    return out


def decode(s: str) -> dict:
    """{x0, y0, w, h, cells: {(a, b): [(z, flags, ox, oy, links[8])]}} of an encoded variant (frame yards; a, b the
    cell in the box; links: the neighbor cell's surface 1-7, 0 none)."""
    from .worldbake import ZESC
    A = CGP.ALPHA
    head, counts, recs, zs, lks = s.split("|")
    x0, y0, w, h = (int(v) for v in head.split(","))
    cnt = [A.index(t) for t in _unrle(counts, lambda p, i: 1)]
    rec = _unrle(recs, lambda p, i: 2)
    zt = _unrle(zs, lambda p, i: 4 if A.index(p[i]) == ZESC else 1)
    lt = _unrle(lks, lambda p, i: 5 if p[i] == "1" else 1)
    assert len(cnt) == w * h, (len(cnt), w, h)
    zof, pos, last = {}, 0, None
    for a in range(w):
        prev_cell = []
        for b in range(h):
            n = cnt[a * h + b]
            if not n:
                prev_cell = []
                continue
            cell_z = []
            for k in range(n):
                t = zt[pos + k]
                if A.index(t[0]) == ZESC:
                    v = A.index(t[1]) * 4096 + A.index(t[2]) * 64 + A.index(t[3])
                else:
                    pred = prev_cell[k] if k < len(prev_cell) else (prev_cell[-1] if prev_cell else last)
                    v = pred + A.index(t) - 31
                last = v
                cell_z.append(v)
            prev_cell = cell_z
            zof[(a, b)] = cell_z
            pos += n
    cells, pos = {}, 0
    for a in range(w):
        for b in range(h):
            for k in range(cnt[a * h + b]):
                f, o = A.index(rec[pos][0]), A.index(rec[pos][1])
                v = zof[(a, b)][k]
                im = []
                for dx, dy in CGP.DIRS:
                    tt = zof.get((a + dx, b + dy), [])
                    best, bk = None, 0
                    for kk, t in enumerate(tt):
                        dz = abs(t - v)
                        if best is None or dz < best:
                            best, bk = dz, kk + 1
                    im.append(bk if best is not None and best <= IMPLIED_Q else 0)
                if lt[pos] == "0":
                    links = im
                else:
                    diff = []
                    for ch in lt[pos][1:]:
                        q = A.index(ch)
                        diff += [q // 8, q % 8]
                    links = [(im[d] + diff[d]) % 8 for d in range(8)]
                cells.setdefault((a, b), []).append((Z0 + v * ZQ, f, o // 8, o % 8, links))
                pos += 1
    return {"x0": x0, "y0": y0, "w": w, "h": h, "cells": cells}


# --- the bake and the files -------------------------------------------------------------------------------------------

def region_key(cont: int, x: float, y: float) -> tuple:
    from . import worldbake as WB
    from . import worldmesh as WM
    tx, ty = WM.tile_of(x, y)
    return (cont,) + WB.region_of(tx * 64 + ty)


def load_index() -> dict:
    return json.loads((work_dir() / "index.json").read_text(encoding="utf-8"))


def bake_all(ids=None, jobs: int = 6, log=print) -> list:
    """Every variant's grid (`ids`: only these), in `jobs` processes."""
    from multiprocessing import Pool
    idx = load_index()
    ids = ids or [v["id"] for v in idx["variants"] if (tris_dir() / f"{v['id']}.npz").exists()]
    with Pool(jobs) as pool:
        res = pool.map(_bake_job, ids, chunksize=4)
    bad = [r for r in res if r.get("error")]
    log(f"  {len(res)} grids baked, {sum(r['surfaces'] for r in res)} surfaces, {len(bad)} failed")
    return res


FILE = "Buildings.lua"


def region_texts(idx: dict, res: list) -> dict:
    """{(cont, rx, ry): text}: each region's Buildings.lua (the module's doc)."""
    rows = {r["uid"]: r for r in idx["rows"]}
    enc = {r["id"]: r["rle"] for r in res if r.get("rle")}
    by = defaultdict(lambda: ([], set()))
    for v in idx["variants"]:
        if v["id"] not in enc:
            continue
        for uid in v["members"]:
            r = rows[uid]
            reg = region_key(r["cont"], r["x"], r["y"])
            by[reg][0].append((v["id"], r))
            by[reg][1].add(v["id"])
    stamp = bake_stamp()
    out = {}
    for reg in sorted(by):
        places, vids = by[reg]
        lines = ["-- GENERATED by `agps building-grid --write` (app/azerothgps/buildinggrid.py). Do not edit by hand.",
                 "-- AzerothGPS's building grids (item 119): the walk grids of this region's buildings, numbers only.",
                 "local all = AzerothGPS_BuildingGrids or {}",
                 "AzerothGPS_BuildingGrids = all",
                 f'all["{reg[0]}:{reg[1]}:{reg[2]}"] = {{ bake = "{stamp}", cell = {CELL:g}, zq = {ZQ:g}, z0 = {Z0:g}, '
                 f"implied = {IMPLIED_Q}, m = {{"]
        for vid in sorted(vids):
            lines.append(f'  [{vid}] = "{enc[vid]}",')
        lines.append("  },")
        p = ";".join(f"{vid},{r['x']:.2f},{r['y']:.2f},{r['z']:.2f},{r['yaw']:.3f}"
                     for vid, r in sorted(places, key=lambda t: (t[0], t[1]["uid"])))
        lines.append(f'  p = "{p}",')
        lines.append("}")
        out[reg] = "\n".join(lines) + "\n"
    return out


def sizes(texts: dict) -> dict:
    """The building data's bytes, unpacked and in a zip (deflate, as the release's)."""
    import io
    import zipfile
    raw = sum(len(t.encode("utf-8")) for t in texts.values())
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for (c, rx, ry), t in texts.items():
            z.writestr(f"AzerothGPS_WG{c}_{rx}_{ry}/{FILE}", t)
    return {"unpacked": raw, "zip": len(buf.getvalue()), "regions": len(texts)}


def write(texts: dict, log=print) -> list:
    """Each region's Buildings.lua into its folder (its toc lists it, worldbake.region_toc); old ones elsewhere removed."""
    from . import worldbake as WB
    root = WB.addons_root()
    want = {WB.region_folder(c, (rx, ry)) for c, rx, ry in texts}
    for f in root.glob(f"AzerothGPS_WG*/{FILE}"):
        if f.parent.name not in want:
            f.unlink()
            m = re.fullmatch(r"AzerothGPS_WG(\d+)_(\d+)_(\d+)", f.parent.name)
            if m:  # (its toc no longer lists it)
                (f.parent / f"{f.parent.name}.toc").write_text(
                    WB.region_toc(int(m.group(1)), (int(m.group(2)), int(m.group(3))), root), encoding="utf-8", newline="\n")
    out = []
    for (c, rx, ry), t in texts.items():
        d = root / WB.region_folder(c, (rx, ry))
        d.mkdir(parents=True, exist_ok=True)
        (d / FILE).write_text(t, encoding="utf-8", newline="\n")
        (d / f"{d.name}.toc").write_text(WB.region_toc(c, (rx, ry), root), encoding="utf-8", newline="\n")
        out.append(d / FILE)
    log(f"wrote {len(out)} regions' {FILE}")
    return out


def run(write_files: bool = False, jobs: int = 6, city: bool = True, log=print) -> dict:
    """`agps building-grid`: the city grids' rebake (citygrid.run, the same run: one stamp, bake_stamp's) and every
    variant's grid, their sizes; `write_files`: Data/CityGrid.lua and the regions' Buildings.lua."""
    st = {}
    if city:
        rows = CGP.run(write=write_files, log=log)
        st["city"] = [{k: r[k] for k in ("city", "surfaces", "bytes")} for r in rows]
    idx = load_index()
    res = bake_all(jobs=jobs, log=log)
    texts = region_texts(idx, res)
    st.update(sizes(texts))
    st["variants"] = len([r for r in res if r.get("rle")])
    st["placements"] = sum(len(v["members"]) for v in idx["variants"])
    st["surfaces"] = sum(r["surfaces"] for r in res)
    st["failed"] = [r["id"] for r in res if r.get("error")]
    st["bake"] = bake_stamp()
    out_dir().mkdir(parents=True, exist_ok=True)
    (out_dir() / "stats.json").write_text(json.dumps(st, indent=1), encoding="utf-8")
    (out_dir() / "variants.json").write_text(json.dumps([{k: v for k, v in r.items() if k != "rle"} for r in res]),
                                             encoding="utf-8")
    log(f"  {st['variants']} grids for {st['placements']} placements: {st['unpacked'] / 1e6:.2f} MB, zip "
        f"{st['zip'] / 1e6:.2f} MB in {st['regions']} regions")
    if write_files:
        write(texts, log)
    return st


# --- reading the shipped files (gridcheck's, the tests') -------------------------------------------------------------

def shipped(root: Path | None = None) -> dict:
    """{(cont, rx, ry): {bake, m: {variant: string}, p: [(variant, x, y, z, yaw)]}} of the shipped Buildings.lua files."""
    from . import worldbake as WB
    root = root or WB.addons_root()
    out = {}
    for f in sorted(root.glob(f"AzerothGPS_WG*/{FILE}")):
        txt = f.read_text(encoding="utf-8")
        m = re.search(r'all\["(\d+):(\d+):(\d+)"\] = \{ bake = "(\w+)"', txt)
        if not m:
            continue
        ms = {int(k): v for k, v in re.findall(r'\n  \[(\d+)\] = "([^"]*)",', txt)}
        p = re.search(r'\n  p = "([^"]*)",', txt).group(1)
        ps = [(int(a), float(b), float(c), float(d), float(e)) for a, b, c, d, e in
              (q.split(",") for q in p.split(";") if q)]
        out[(int(m.group(1)), int(m.group(2)), int(m.group(3)))] = {"bake": m.group(4), "m": ms, "p": ps}
    return out


_DECODED: dict = {}


def floors_at(cont: int, x: float, y: float, data: dict | None = None, r: int = 0) -> list:
    """The building grids' floor heights (world) at (x, y): every placement whose grid has a cell there (and the `r`
    cells round it); not the doors' steps (the land's)."""
    data = shipped() if data is None else data
    reg = data.get(region_key(cont, x, y))
    if not reg:
        return []
    out = []
    for vid, px, py, pz, yaw in reg["p"]:
        s = reg["m"].get(vid)
        if s is None:
            continue
        d = _DECODED.get(s)
        if d is None:
            d = _DECODED[s] = decode(s)
        lx, ly, _lz = to_frame(np.array([x, y, 0.0]), {"x": px, "y": py, "z": pz, "yaw": yaw})
        a, b = int(math.floor((lx - d["x0"]) / CELL)), int(math.floor((ly - d["y0"]) / CELL))
        if not (-r <= a < d["w"] + r and -r <= b < d["h"] + r):
            continue
        for da in range(-r, r + 1):
            for db in range(-r, r + 1):
                for z, f, _ox, _oy, _l in d["cells"].get((a + da, b + db), ()):
                    if not f & F_DOOR:
                        out.append(z + pz)
    return out
