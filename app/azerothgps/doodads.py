"""Doodads: the small models placed in the world (M2: trees, rocks, crates, fences, planters, spikes; the ADTs' MDDF,
and a WMO's own doodad sets: a city's lamp posts, stalls and planters) that a character collides with.

The road and floor data was built from the terrain and the WMOs only; a road through a tree or a planter was a stop for
anyone following the line (route tests in game, 2026-10-08: Dun Morogh's trees on a road's
join, a Stormwind street's planter, Orgrimmar's spiked barricades). Each doodad's collision mesh (the M2 header's
collisionIndices / collisionPositions; a bush has none, a tree its trunk) placed in the world:

- ADT MDDF (36 bytes): nameId (a FileDataID when flags & 0x40), uniqueId, position, rotation (degrees), scale (/1024),
  flags. Placed as the WMOs are (interiors.py): world X = OFFSET - pos.z, Y = OFFSET - pos.x, Z = pos.y; yaw
  rot.y + 180 degrees, tilt by rot.x and rot.z (walknet.Placed).
- WMO MODD (40 bytes): name index (24 bits; with MODI, an index into its FileDataIDs), position, rotation quaternion
  (x, y, z, w), scale, color; MODS sets (20-byte name, first index, count): set 0 always, and the placement's MODF
  doodadSet. In the model's frame, then the WMO's placement.

`agps doodads X Y R` lists those near a spot (and `--render` draws them with the models' walls, the roads and a route).
"""

from __future__ import annotations

import math
import struct
from dataclasses import dataclass

import numpy as np

from . import interiors as I
from .extract import adt
from .extract.spike import ClientData

OFFSET = 17066.666666666668
MDDF_FILEDATA = 0x40
MODF_FILEDATA = 0x8


@dataclass
class Doodad:
    fid: int  # the M2's FileDataID
    uid: int  # its ADT placement's, or its WMO placement's
    x: float
    y: float
    z: float
    m: np.ndarray  # 3x3: its frame (scaled) to the world's
    wmo: bool = False  # one of a WMO's doodads


_COLLISION: dict = {}


def m2_collision(cd: ClientData, fid: int):
    """An M2's collision mesh in its own frame: (vertices (n, 3), triangles (m, 3) indices), or None (none: a bush)."""
    if fid in _COLLISION:
        return _COLLISION[fid]
    out = None
    try:
        data = cd.casc.read(fid)
        if data[:4] == b"MD21":  # (chunked: the MD20 header and its data are the MD21 chunk)
            pos, md20 = 0, None
            while pos + 8 <= len(data):
                magic, size = data[pos:pos + 4], struct.unpack_from("<I", data, pos + 4)[0]
                if magic == b"MD21":
                    md20 = data[pos + 8:pos + 8 + size]
                    break
                pos += 8 + size
            data = md20
        if data and data[:4] == b"MD20":
            ni, oi = struct.unpack_from("<II", data, 216)  # collisionIndices
            nv, ov = struct.unpack_from("<II", data, 224)  # collisionPositions
            if ni >= 3 and nv:
                idx = np.frombuffer(data, np.uint16, ni - ni % 3, oi).reshape(-1, 3).astype(int)
                V = np.frombuffer(data, np.float32, nv * 3, ov).reshape(-1, 3).astype(float)
                if len(idx) and idx.max() < len(V):
                    out = (V, idx)
    except Exception:  # (a file missing from this client, or not an M2)
        out = None
    _COLLISION[fid] = out
    return out


def _turn(yaw: float, rx: float = 0.0, rz: float = 0.0) -> np.ndarray:
    t, a, b = math.radians(yaw + 180), math.radians(rx), math.radians(rz)
    Rz = np.array([[math.cos(t), -math.sin(t), 0], [math.sin(t), math.cos(t), 0], [0, 0, 1]])
    Ry = np.array([[math.cos(a), 0, math.sin(a)], [0, 1, 0], [-math.sin(a), 0, math.cos(a)]])
    Rx = np.array([[1, 0, 0], [0, math.cos(b), -math.sin(b)], [0, math.sin(b), math.cos(b)]])
    return Rz @ Ry @ Rx


def _quat(x: float, y: float, z: float, w: float) -> np.ndarray:
    return np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                     [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                     [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])


def _in(box, x, y, pad=0.0) -> bool:
    return box is None or (box[0] - pad <= x <= box[2] + pad and box[1] - pad <= y <= box[3] + pad)


def adt_doodads(cd: ClientData, cont: int, box=None) -> list[Doodad]:
    """The continent's ADT doodads (MDDF), those within `box` (world x0, y0, x1, y1) if given."""
    m = next(r for r in cd.table("Map") if r["ID"] == cont)
    wdt = adt.parse_wdt(cd.casc.read(m["WdtFileDataID"]))
    T = adt.TILE_YD
    out, seen = [], set()
    for (tx, ty), t in wdt.tiles.items():
        if not t.obj0:
            continue
        if box is not None and ((32 - ty) * T < box[0] - 50 or (32 - ty - 1) * T > box[2] + 50
                                or (32 - tx) * T < box[1] - 50 or (32 - tx - 1) * T > box[3] + 50):
            continue
        try:
            data = cd.casc.read(t.obj0)
        except Exception:
            continue
        for magic, a, b in adt.iter_chunks(data):
            if magic != "MDDF":
                continue
            for i in range(a, b - 35, 36):
                nid, uid = struct.unpack_from("<II", data, i)
                px, py, pz = struct.unpack_from("<3f", data, i + 8)
                rx, ry, rz = struct.unpack_from("<3f", data, i + 20)
                scale, flags = struct.unpack_from("<HH", data, i + 32)
                X, Y = OFFSET - pz, OFFSET - px
                if not flags & MDDF_FILEDATA or uid in seen or not _in(box, X, Y, 30):
                    continue
                seen.add(uid)
                out.append(Doodad(nid, uid, X, Y, py, _turn(ry, rx, rz) * (scale / 1024.0)))
    return out


_SETS: dict = {}


def _wmo_sets(cd: ClientData, wmo: int):
    """A WMO's doodad sets [(first, count)] and its doodads [(fid, position, quaternion, scale)]."""
    if wmo in _SETS:
        return _SETS[wmo]
    sets, ids, modd = [], None, []
    try:
        data = cd.casc.read(wmo)
        for magic, a, b in adt.iter_chunks(data):
            if magic == "MODS":
                sets = [struct.unpack_from("<II", data, i + 20) for i in range(a, b - 31, 32)]
            elif magic == "MODI":
                ids = struct.unpack_from(f"<{(b - a) // 4}I", data, a)
            elif magic == "MODD":
                for i in range(a, b - 39, 40):
                    ni = struct.unpack_from("<I", data, i)[0] & 0xFFFFFF
                    modd.append((ni, struct.unpack_from("<3f", data, i + 4), struct.unpack_from("<4f", data, i + 16),
                                 struct.unpack_from("<f", data, i + 32)[0]))
    except Exception:
        pass
    out = []
    if ids is not None:  # (no MODI: names in MODN; not in this client's world models)
        for ni, p, q, s in modd:
            out.append((ids[ni] if ni < len(ids) else 0, p, q, s))
    _SETS[wmo] = (sets, out)
    return _SETS[wmo]


def wmo_doodads(cd: ClientData, p: I.Placement, box=None) -> list[Doodad]:
    """The doodads a placed WMO brings (set 0 and its placement's set), those within `box` if given."""
    sets, dd = _wmo_sets(cd, p.wmo)
    use = set()
    for k in {0, getattr(p, "doodad_set", 0)}:
        if k < len(sets):
            first, count = sets[k]
            use.update(range(first, first + count))
    M = _turn(p.yaw, getattr(p, "rx", 0.0), getattr(p, "rz", 0.0))
    o = np.array([p.x, p.y, p.z])
    out = []
    for j in sorted(use):
        if j >= len(dd) or not dd[j][0]:
            continue
        fid, lp, q, s = dd[j]
        w = M @ np.array(lp) + o
        if _in(box, w[0], w[1], 30):
            out.append(Doodad(fid, p.uid, float(w[0]), float(w[1]), float(w[2]), M @ _quat(*q) * s, True))
    return out


def doodads(cd: ClientData, cont: int, box, wmos=None) -> list[Doodad]:
    """The ADT doodads within `box` and the doodads of the WMOs placed over it (only the WMO placements `wmos`, uids, if
    given)."""
    out = adt_doodads(cd, cont, box)
    for p in I.placements(cd, cont):
        b = p.bounds
        if wmos is not None and p.uid not in wmos:
            continue
        if b[2] < box[0] or b[0] > box[2] or b[3] < box[1] or b[1] > box[3]:
            continue
        out += wmo_doodads(cd, p, box)
    return out


def triangles(cd: ClientData, d: Doodad) -> np.ndarray | None:
    """A doodad's collision triangles in the world: (m, 3, 3), or None."""
    col = m2_collision(cd, d.fid)
    if col is None:
        return None
    V, idx = col
    W = V @ d.m.T + np.array([d.x, d.y, d.z])
    return W[idx]


def walls(cd: ClientData, ds: list[Doodad]) -> list:
    """The doodads' collision faces as walls in capitals.city_faces' format: ((zlo, zhi), xy triangle, vertex heights).
    Every face, steep or flat: a planter's or a table's top isn't a floor to walk on."""
    out = []
    for d in ds:
        T = triangles(cd, d)
        if T is None:
            continue
        for t in T:
            zs = [float(t[0, 2]), float(t[1, 2]), float(t[2, 2])]
            out.append(((min(zs), max(zs)), [(float(t[k, 0]), float(t[k, 1])) for k in range(3)], zs))
    return out


def near(cd: ClientData, cont: int, X: float, Y: float, R: float, band=(0.25, 2.0)) -> list[dict]:
    """The doodads with collision within R yards of (X, Y) that a walker bumps into (faces between `band` over their
    base): each { name, fid, wmo, x, y, z, box (x0, y0, x1, y1), dist, tris }, nearest first."""
    out = []
    for d in doodads(cd, cont, (X - R, Y - R, X + R, Y + R)):
        T = triangles(cd, d)
        if T is None:
            continue
        zlo, zhi = T[:, :, 2].min(axis=1), T[:, :, 2].max(axis=1)
        T = T[(zhi >= d.z + band[0]) & (zlo <= d.z + band[1])]
        if not len(T):
            continue
        x0, y0, x1, y1 = T[:, :, 0].min(), T[:, :, 1].min(), T[:, :, 0].max(), T[:, :, 1].max()
        dist = math.hypot(max(x0 - X, 0, X - x1), max(y0 - Y, 0, Y - y1))
        if dist > R:
            continue
        out.append({"name": cd.name(d.fid) or str(d.fid), "fid": d.fid, "wmo": d.wmo, "x": d.x, "y": d.y, "z": d.z,
                    "box": (x0, y0, x1, y1), "dist": dist, "tris": T})
    return sorted(out, key=lambda f: f["dist"])


def render(cd: ClientData, cont: int, X: float, Y: float, R: float, out, route=None, z: float | None = None,
           scale: float = 6.0) -> int:
    """A picture R yards around (X, Y), north up: the doodads' collision (red), the WMOs' walls at a body's height over
    the ground (or over `z`: a city's floor; white), the land's roads (tan), `route` (polylines; blue), the spot
    (yellow). Returns the doodads drawn."""
    from PIL import Image, ImageDraw

    from . import buildings as B
    from .caves import Ground, shipped_roads

    S = scale
    Wpx = int(2 * R * S)
    img = Image.new("RGB", (Wpx, Wpx), (26, 32, 24))
    dr = ImageDraw.Draw(img, "RGBA")

    def px(x, y):  # (north up, west left)
        return (Y + R - y) * S, (X + R - x) * S

    fs = near(cd, cont, X, Y, R)
    for f in fs:
        for t in f["tris"]:
            dr.polygon([px(v[0], v[1]) for v in t], fill=(255, 70, 70, 90), outline=(255, 90, 90, 160))
    ground = Ground(cd, cont)
    for p in I.placements(cd, cont):
        b = p.bounds
        if b[0] > X + R or b[2] < X - R or b[1] > Y + R or b[3] < Y - R:
            continue
        if z is None:
            segs = B.cut(cd, p, ground)
        else:
            segs = _cut_at(cd, p, z + B.BODY_YD)
        for s in segs:
            if _in((X - R, Y - R, X + R, Y + R), *s[0]) or _in((X - R, Y - R, X + R, Y + R), *s[1]):
                dr.line([px(*s[0]), px(*s[1])], fill=(255, 255, 255, 255), width=2)
    g = shipped_roads(cont)
    for e in (g.edges.values() if isinstance(g.edges, dict) else g.edges):
        xy = [px(float(q[0]), float(q[1])) for q in e.pts]
        if any(0 <= a <= Wpx and 0 <= b <= Wpx for a, b in xy):
            dr.line(xy, fill=(180, 150, 90, 200), width=2)
    for pts in route or ():
        dr.line([px(q[0], q[1]) for q in pts], fill=(90, 200, 255, 255), width=3)
    sx, sy = px(X, Y)
    dr.ellipse([sx - 6, sy - 6, sx + 6, sy + 6], outline=(255, 255, 0, 255), width=3)
    dr.line([(10, Wpx - 10), (10 + 10 * S, Wpx - 10)], fill=(255, 255, 255, 255), width=3)
    img.save(out)
    return len(fs)


def _cut_at(cd: ClientData, p, h: float) -> np.ndarray:
    """A placed WMO's walls cut at height h: segments (m, 2, 2)."""
    from . import buildings as B
    from . import walknet

    T = B.model_walls(cd, p.wmo)
    if not len(T):
        return np.zeros((0, 2, 2))
    xf = walknet.Placed(p)
    W = T @ xf.m.T + xf.o
    pts = []
    for i in range(3):
        a, b = W[:, i], W[:, (i + 1) % 3]
        da, db = a[:, 2] - h, b[:, 2] - h
        cross = da * db < 0
        s = np.where(cross, da / np.where(cross, da - db, 1), 0)
        pts.append((cross, a[:, :2] + (b[:, :2] - a[:, :2]) * s[:, None]))
    segs = []
    for i in range(3):
        for j in range(i + 1, 3):
            sel = pts[i][0] & pts[j][0]
            if sel.any():
                segs.append(np.stack([pts[i][1][sel], pts[j][1][sel]], axis=1))
    return np.concatenate(segs) if segs else np.zeros((0, 2, 2))
