"""Heights for the roads walked in game with Record (the road watcher's; app/azerothgps/roads/recorded.py).

Record samples the player's 2D position as they walk a road: a point every ~2 yd and on turns, IsIndoors() at each,
the minimap's zone text where it changes, the player's "Stairs start" / "Stairs end" marks (point-index ranges), and
now and then a floor picked by hand. The game never gives the player's height (UnitPosition's z is always 0), so each
point's height is chosen here, offline, from the floors actually under it: the terrain's and every walkable face of
the models (WMOs) placed there (candidates). The best path over the whole walk is taken (assign: a Viterbi over the
floors; a player steps up and down, drops off a ledge but never jumps up a floor, is under a roof when the game says
indoors, and climbs where they marked stairs), not the floor nearest the last one. Then the track is cut where it goes
from the terrain onto a model's floors and back, and at the stairs (pieces): the ground's stretches go to the flat
land build, the others ship with a height per point (Data/Roads.lua's ns.FloorTracks).

Coordinates are world X, Y as the addon has them (UnitPosition's; caves.Ground.sample's, the roads'), on continents 0
(the Eastern Kingdoms), 1 (Kalimdor) and 2991 (Zephras Isle); heights are the game's world z.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from .. import interiors as I
from .. import walknet
from ..caves import Ground

FLOOR_SLOPE = 0.64  # a floor's normal at least this upright (indoors', the caves')
MERGE_Z = 0.5  # floors under a point this near each other in height are one
TOUCH = 0.3  # yards: a point this near a floor's edge is on it (the seams between faces)
INDEX_YD = 4.0  # yards: the cells faces are indexed by (per placement)
INDEX_MAX = 200000  # (the index's face-in-cell entries at most, about: bigger cells past it)
BOUNDS_PAD = 0.5  # yards round a placement's bounds still looked in
COVER_Z = 1.5  # a model's face this far over a floor covers it (a roof, the floor above; not a step's edge)
CLEAR_Z = 2.5  # the terrain with a model's floor less than this over it is no floor: under a building's floor, in a
# platform's base (Brill's town hall stands 2.1 yd over it; a walk under its roof, outdoors, took the terrain)

# The path's costs (assign). Between neighbors d yd apart a change dz up to CLIMB = STEP_Z + d * SLOPE is walked
# (CLIMB_COST a yard of it); more is a jump up (JUMP: a player can't jump up a floor) or a drop off a ledge (DROP).
STEP_YD = 2.0  # yards between points when the points aren't given (Record's spacing)
STEP_Z = 0.5  # yards: a step up or down whatever the slope (a doorstep; at 1.0 the side of Brill's stair landing,
# 3.2 yd over the floor beside it, was a step down, and the upper floor a coin toss)
SLOPE = 1.2  # and this much a yard along (about 50 degrees: FLOOR_SLOPE's steepest floor)
CLIMB_COST = 0.1  # a yard climbed or gone down
EVEN_COST = 0.01  # (and a hair more for an uneven climb, by its square: a ramp's steps over one hop)
JUMP = 50.0
DROP = 5.0
# Along a Stairs stretch (the player's marks, STAIR_PAD_YD wider each way: a key pressed a step early or late) a climb
# either way is free up to STAIR_STEP_Z + d * STAIR_SLOPE, and a stretch whose ends aren't STAIR_RISE apart in height
# costs STAIR_MISS: the stairs, not a floor under them. (A cost per level step instead had the path zigzag between two
# floors to dodge it; a flag for "climbed" was set by a step up from the terrain onto the floor at the foot.)
STAIR_STEP_Z = 1.0
STAIR_SLOPE = 1.5  # (a spiral stair's steep turns; at 1.5 + 2 yd a yard the stairs' top was a free hop onto a roof)
STAIR_PAD_YD = 3.0
STAIR_RISE = 2.0  # (Turns.STAIR_RISE is 4: a flight the map draws; a short one marked counts here)
STAIR_MISS = 3.0
# Each floor at a point: indoors on the terrain under a model's floor (INDOOR_MISS), indoors with no face of a model
# over it (SKY_MISS: a roof's top; 98% of the towns' indoor floor faces have one over them), outdoors on a model's
# floor with one over it (ROOF_MISS), a floor picked by hand more than PICK_YD off (PICK_MISS).
INDOOR_MISS = 1.0
SKY_MISS = 0.5
ROOF_MISS = 0.5
PICK_MISS = 3.0
PICK_YD = 2.0
AMBIG_COST = 1.5  # another floor on a path this near the best one's cost: a doubt
AMBIG_Z = 2.0  # (another floor: this far from the one chosen)

DOORMAT_YD = 3.0  # a model's stretch shorter than this between the ground's is the ground (a doorstep, a slab)

# A portal taken on the walk (Stormwind's Wizard's Sanctum, 2026-11-17: the tower's top and the trainers' room under the
# city, 9 yd apart on the map, too near for Record's REC_JUMP_YD): a step at least PORTAL_STEP_YD long ending within
# PORTAL_LAND_YD of where a portal puts you (addon_data.TELEPORTERS' `land`). The walk's floors are worked out either
# side of it on their own, and no road joins the two (the floors had one drop, from the stairs' middle into the room).
PORTAL_STEP_YD = 5.0
PORTAL_LAND_YD = 4.0


def _picks_from(pk, a: int, b: int):
    """Record's floor picks (where the pick changed, points from 1) for points a..b-1 (from 0) as their own walk's: the
    pick in force at its first point, then the changes in it."""
    if not pk:
        return None
    marks = sorted(pk, key=lambda m: m[0])
    before = [z for i, z in marks if i - 1 < a]
    out = [(1, before[-1])] if before else []
    out += [(i - a, z) for i, z in marks if a <= i - 1 < b]
    return out or None


def portal_steps(pts) -> list:
    """The steps i (point i to i + 1, from 0) where the walk went through a portal (PORTAL_STEP_YD, PORTAL_LAND_YD)."""
    from ..addon_data import TELEPORTERS

    lands = [xy for row in TELEPORTERS for opts in row[2:3] for xy in opts.get("land", ())]
    out = []
    for i in range(len(pts) - 1):
        (ax, ay), (bx, by) = pts[i], pts[i + 1]
        if math.hypot(bx - ax, by - ay) >= PORTAL_STEP_YD and any(
                math.hypot(bx - lx, by - ly) <= PORTAL_LAND_YD for lx, ly in lands):
            out.append(i)
    return out


@dataclass
class Cand:
    """A floor under a point: its height, "ground" (the terrain) or "model" (a placed model's floor), and the model's
    placement (a "ground" one with a uid: a model's floor at the terrain's height there)."""
    z: float
    kind: str
    uid: int | None = None


class Cands(list):
    """The floors under each point (a list of Cand per point), with the points (`pts`: the yards between them) and
    the highest face of a model over each (`top`: a floor's or a steep one's, -inf for none; what covers a floor)."""
    pts: list | None = None
    top: list | None = None


class Faces:
    """A placed model's faces in the world ((n, 3, 3) triangles), indexed by a grid of INDEX_YD cells: their heights
    under points. `touch`: yards off an edge still on a face (0 for steep faces, whose 2D shapes are slivers)."""

    def __init__(self, tris, uid=None, touch: float = TOUCH):
        T = np.asarray(tris, float).reshape(-1, 3, 3)
        x1, y1, x2, y2, x3, y3 = T[:, 0, 0], T[:, 0, 1], T[:, 1, 0], T[:, 1, 1], T[:, 2, 0], T[:, 2, 1]
        det = (y2 - y3) * (x1 - x3) + (x3 - x2) * (y1 - y3)
        keep = np.abs(det) > 1e-6  # (not upright in 2D)
        T, det = T[keep], det[keep]
        x1, y1, x2, y2, x3, y3 = T[:, 0, 0], T[:, 0, 1], T[:, 1, 0], T[:, 1, 1], T[:, 2, 0], T[:, 2, 1]
        self.uid, self.n = uid, len(T)
        self.z = T[:, :, 2]
        self.o = T[:, 2, :2]
        # (barycentrics from the third vertex: l1 = a0 dx + a1 dy, l2 = a2 dx + a3 dy)
        self.a = np.stack([(y2 - y3) / det, (x3 - x2) / det, (y3 - y1) / det, (x1 - x3) / det], 1)
        # (a point `touch` yd outside an edge is still on the face: each barycentric's slack is the edge opposite over
        # twice the area)
        L = np.stack([np.hypot(x3 - x2, y3 - y2), np.hypot(x1 - x3, y1 - y3), np.hypot(x2 - x1, y2 - y1)], 1)
        self.tol = touch * L / np.abs(det)[:, None]
        if not self.n:
            self.box = (math.inf, math.inf, -math.inf, -math.inf)
            return
        # each face in every cell of its box (cells twice as big while that's too many: a capital's long floors)
        self.cell = INDEX_YD
        while True:
            lo = np.floor((T[:, :, :2].min(1) - touch) / self.cell).astype(np.int64)
            hi = np.floor((T[:, :, :2].max(1) + touch) / self.cell).astype(np.int64)
            nx, ny = hi[:, 0] - lo[:, 0] + 1, hi[:, 1] - lo[:, 1] + 1
            cnt = nx * ny
            if int(cnt.sum()) <= max(INDEX_MAX, 16 * self.n):
                break
            self.cell *= 2
        self.c0 = lo.min(0)
        self.span = hi.max(0) - self.c0 + 1
        f = np.repeat(np.arange(self.n), cnt)
        k = np.arange(int(cnt.sum())) - np.repeat(np.cumsum(cnt) - cnt, cnt)
        cx, cy = lo[f, 0] + k // ny[f], lo[f, 1] + k % ny[f]
        key = (cx - self.c0[0]) * self.span[1] + (cy - self.c0[1])
        order = np.argsort(key, kind="stable")
        self.keys, self.ids = key[order], f[order]
        self.box = (T[:, :, 0].min() - touch, T[:, :, 1].min() - touch, T[:, :, 0].max() + touch,
                    T[:, :, 1].max() + touch)

    def heights(self, X, Y):
        """The faces' heights under world points: (point indices, heights), a pair per face under a point."""
        X, Y = np.asarray(X, float).ravel(), np.asarray(Y, float).ravel()
        x0, y0, x1, y1 = self.box
        idx = np.nonzero((X >= x0) & (X <= x1) & (Y >= y0) & (Y <= y1))[0]
        if not len(idx):
            return np.zeros(0, int), np.zeros(0)
        cx = np.floor(X[idx] / self.cell).astype(np.int64) - self.c0[0]
        cy = np.floor(Y[idx] / self.cell).astype(np.int64) - self.c0[1]
        inside = (cx >= 0) & (cx < self.span[0]) & (cy >= 0) & (cy < self.span[1])
        idx, key = idx[inside], (cx * self.span[1] + cy)[inside]
        lo = np.searchsorted(self.keys, key, "left")
        cnt = np.searchsorted(self.keys, key, "right") - lo
        pi = np.repeat(idx, cnt)
        fi = self.ids[np.repeat(lo, cnt) + np.arange(int(cnt.sum())) - np.repeat(np.cumsum(cnt) - cnt, cnt)]
        dx, dy = X[pi] - self.o[fi, 0], Y[pi] - self.o[fi, 1]
        l1 = self.a[fi, 0] * dx + self.a[fi, 1] * dy
        l2 = self.a[fi, 2] * dx + self.a[fi, 3] * dy
        l3 = 1 - l1 - l2
        ok = (l1 >= -self.tol[fi, 0]) & (l2 >= -self.tol[fi, 1]) & (l3 >= -self.tol[fi, 2])
        z = l1 * self.z[fi, 0] + l2 * self.z[fi, 1] + l3 * self.z[fi, 2]
        return pi[ok], z[ok]


def merge(found: list) -> list:
    """Floors under a point [(z, kind, uid)] as Cands, low to high: those within MERGE_Z of each other one, at the
    top one's height (what's stood on); with the terrain among them "ground", the model's uid kept. The terrain alone
    with a model's floor less than CLEAR_Z over it is left out."""
    out, group = [], []
    for f in sorted(found, key=lambda f: f[0]):
        if group and f[0] - group[-1][0] > MERGE_Z:
            out.append(_one(group))
            group = []
        group.append(f)
    if group:
        out.append(_one(group))
    g = next((k for k, c in enumerate(out) if c.kind == "ground" and c.uid is None), None)
    if g is not None and g + 1 < len(out) and out[g + 1].z - out[g].z < CLEAR_Z:
        del out[g]
    return out


def _one(group: list) -> Cand:
    models = [f for f in group if f[1] == "model"]
    return Cand(round(float(group[-1][0]), 2), "ground" if any(f[1] == "ground" for f in group) else "model",
                models[-1][2] if models else None)


def floors_under(pts, terrain, floors, cover=()) -> Cands:
    """The floors under each point: the terrain's height (`terrain`, a height per point, NaN where there's none) and
    each model's floors under it (`floors`: Faces with their uid), merged (MERGE_Z); `cover`: the models' other faces
    (Faces), for the highest face over each point (Cands.top)."""
    P = np.asarray(pts, float).reshape(-1, 2)
    found = [[] for _ in range(len(P))]
    top = np.full(len(P), -np.inf)
    terrain = np.asarray(terrain, float).ravel()
    for i in np.nonzero(np.isfinite(terrain))[0].tolist():
        found[i].append((float(terrain[i]), "ground", None))
    for f in floors:
        pi, z = f.heights(P[:, 0], P[:, 1])
        np.maximum.at(top, pi, z)
        for i, zz in zip(pi.tolist(), z.tolist()):
            found[i].append((zz, "model", f.uid))
    for f in cover:
        pi, z = f.heights(P[:, 0], P[:, 1])
        np.maximum.at(top, pi, z)
    out = Cands(merge(f) for f in found)
    out.pts = [(float(x), float(y)) for x, y in P]
    out.top = top.tolist()
    return out


def terrain_at(ground, X, Y) -> np.ndarray:
    """The terrain's height at world points, NaN where there's none: off the tiles, or a hole (a cellar's or a cave's
    way down). Steep ground and a lake's bed count (Ground.sample's `walkable` aside)."""
    X, Y = np.asarray(X, float).ravel(), np.asarray(Y, float).ravel()
    h, _ok = ground.sample(X, Y)
    h = np.array(h, float)
    holes = getattr(ground, "holes", None)
    if holes is None:  # (a stand-in ground: no holes)
        return h
    return np.where(holes(X, Y), np.nan, h)


_FACES: dict = {}  # model -> (its floors, its other faces) in its own frame, (n, 3, 3) each
_PLACED: dict = {}  # (continent, placement uid) -> (floors, other faces) as Faces in the world


def local_faces(cd, wmo: int, log=print) -> tuple[np.ndarray, np.ndarray]:
    """A model's walkable faces and its other ones (walknet.model_faces' floors and walls), in its own frame;
    cached."""
    if wmo not in _FACES:
        try:
            floors, walls, _liq = walknet.model_faces(cd, wmo, FLOOR_SLOPE)
        except Exception as ex:  # (a model this reader can't take)
            log(f"  model {wmo}: unreadable ({ex!r})")
            floors, walls = [], []
        _FACES[wmo] = (np.array([t for _g, _z, t in floors], float).reshape(-1, 3, 3),
                       np.array([t for _g, _z, t in walls], float).reshape(-1, 3, 3))
    return _FACES[wmo]


def placed_faces(cd, cont: int, p, log=print) -> tuple[Faces, Faces]:
    """A placement's floors and other faces in the world (walknet.Placed, as indoors.building_faces), indexed; cached.
    A tilted placement's floors no longer upright in the world are other faces."""
    key = (cont, p.uid)
    if key not in _PLACED:
        F, O = local_faces(cd, p.wmo, log)
        xf = walknet.Placed(p)
        Fw, Ow = F @ xf.m.T + xf.o, O @ xf.m.T + xf.o
        if len(F) and getattr(p, "tilt", 0.0) > 0.01:
            n = np.cross(F[:, 1] - F[:, 0], F[:, 2] - F[:, 0])
            n *= np.where(n[:, 2] < 0, -1.0, 1.0)[:, None]  # (up in its own frame: model_faces kept those)
            nw = n @ xf.m.T
            up = nw[:, 2] >= FLOOR_SLOPE * np.linalg.norm(nw, axis=1)
            Fw, Ow = Fw[up], np.concatenate([Ow, Fw[~up]])
        _PLACED[key] = (Faces(Fw, p.uid), Faces(Ow, p.uid, touch=0.0))
    return _PLACED[key]


def candidates(cd, cont: int, pts, ground=None, placements=None, log=print) -> Cands:
    """The floors under each point (x, y) of a recorded track: the terrain's height (caves.Ground; under a model too,
    but not in a hole nor right under a model's floor, CLEAR_Z) and every walkable face (FLOOR_SLOPE) of each model
    placed there (interiors.placements: those whose bounds hold the point) at its height there, within MERGE_Z merged;
    and the highest face of a model over each point (Cands.top). Pass `ground` and `placements` when there are many
    tracks (the models' faces are cached)."""
    P = np.asarray(pts, float).reshape(-1, 2)
    if ground is None:
        ground = Ground(cd, cont)
    if placements is None:
        placements = I.placements(cd, cont)
    X, Y = P[:, 0], P[:, 1]
    floors, cover = [], []
    if len(P):
        bx0, by0, bx1, by1 = X.min() - BOUNDS_PAD, Y.min() - BOUNDS_PAD, X.max() + BOUNDS_PAD, Y.max() + BOUNDS_PAD
        for p in placements:
            x0, y0, x1, y1 = p.bounds
            if x1 < bx0 or x0 > bx1 or y1 < by0 or y0 > by1:
                continue
            x0, y0, x1, y1 = x0 - BOUNDS_PAD, y0 - BOUNDS_PAD, x1 + BOUNDS_PAD, y1 + BOUNDS_PAD
            if ((X >= x0) & (X <= x1) & (Y >= y0) & (Y <= y1)).any():
                f, o = placed_faces(cd, cont, p, log)
                floors.append(f)
                cover.append(o)
    return floors_under(P, terrain_at(ground, X, Y) if len(P) else [], floors, cover)


def _yards(pts, n: int) -> np.ndarray:
    """The yards between neighbors (n - 1 of them); STEP_YD each without the points."""
    if pts is None or len(pts) != n:
        return np.full(max(n - 1, 0), STEP_YD)
    P = np.asarray(pts, float).reshape(-1, 2)
    return np.hypot(*np.diff(P, axis=0).T) if n > 1 else np.zeros(0)


def stretches(stairs, d: np.ndarray) -> list:
    """The Stairs marks (a, b) as the stretches assign() climbs on: each STAIR_PAD_YD wider either way along the track
    (d: the yards between neighbors), at most halfway to the next; the empty ones left out."""
    n1 = len(d)
    marks = sorted((max(0, int(a)), min(n1, int(b))) for a, b in stairs or ())
    marks = [m for m in marks if m[1] > m[0]]
    out = []
    for k, (a, b) in enumerate(marks):
        lo = (marks[k - 1][1] + a + 1) // 2 if k else 0
        hi = (b + marks[k + 1][0]) // 2 if k + 1 < len(marks) else n1
        s = 0.0
        while a > lo and s + d[a - 1] <= STAIR_PAD_YD:
            a -= 1
            s += d[a]
        s = 0.0
        while b < hi and s + d[b] <= STAIR_PAD_YD:
            s += d[b]
            b += 1
        if out:
            a = max(a, out[-1][1])
        if b > a:
            out.append((a, b))
    return out


def _step_costs(za, zb, d: float, stair: bool) -> np.ndarray:
    """The cost of each step from heights `za` to `zb` (a matrix) over d yards: a walked climb, a jump or a drop; on a
    Stairs stretch free climbs."""
    dz = zb[None, :] - za[:, None]
    adz = np.abs(dz)
    cost = np.where(adz <= STEP_Z + d * SLOPE, adz * CLIMB_COST + dz * dz * EVEN_COST, np.where(dz > 0, JUMP, DROP))
    if stair:
        cost = np.where(adz <= STAIR_STEP_Z + d * STAIR_SLOPE, dz * dz * EVEN_COST, cost)
    return cost


def _flag(v):
    """IsIndoors as recorded: True, False or None (unknown); Record's "1" / "0" too."""
    if v is None:
        return None
    if isinstance(v, str):
        return v == "1"
    return bool(v)


def _own_costs(cs: list, top: float, indoors, picked) -> np.ndarray:
    """Each floor's cost at a point, from IsIndoors there (`top`: the highest face of a model over the point) and a
    floor picked by hand."""
    out = np.zeros(len(cs))
    for k, c in enumerate(cs):
        if indoors is True:
            if c.kind == "ground" and c.uid is None and any(o.kind == "model" and o.z > c.z for o in cs):
                out[k] += INDOOR_MISS
            elif top <= c.z + COVER_Z:
                out[k] += SKY_MISS
        elif indoors is False and c.kind == "model" and top > c.z + COVER_Z:
            out[k] += ROOF_MISS
        if picked is not None and abs(c.z - picked) > PICK_YD:
            out[k] += PICK_MISS
    return out


def _at(seq, i):
    if seq is None:
        return None
    if isinstance(seq, dict):
        return seq.get(i)
    return seq[i] if i < len(seq) else None


def assign(cands, indoors, stairs, picked=None, pts=None):
    """Each point's floor, by the best path over the whole walk (Viterbi over `cands`, candidates()'): a step a player
    walks (CLIMB) costs a little, a jump up a floor a lot (JUMP), a drop off a ledge some (DROP); along a Stairs
    stretch (`stairs`: (a, b) point indices, the steps a <= i < b; see stretches) any climb up to STAIR_STEP_Z + d *
    STAIR_SLOPE is free, and one whose ends aren't STAIR_RISE apart costs STAIR_MISS; `indoors` (IsIndoors per point:
    True, False, None unknown; or Record's string of 1s and 0s) on the terrain under a model's floor costs
    INDOOR_MISS, with no model's face over it SKY_MISS, outdoors on a model's floor under another face ROOF_MISS; a
    floor `picked` by hand (a height per point, None for none; a list or a dict) more than PICK_YD off costs
    PICK_MISS. `pts`: the points, for the yards between them (candidates() keeps them; else STEP_YD each).

    Returns (zs, kinds, ambiguous): heights rounded to 0.1; "ground" or "model" per point (the terrain with a model's
    floor on it: "model" indoors); and the stretches (i, j) (first and last point) where a floor AMBIG_Z or more from
    the one chosen is on a path within AMBIG_COST of the best (min-sum marginals: the best path's cost through each
    floor, forward and backward), inside a Stairs stretch only at its ends (the climb between is the stairs')."""
    n = len(cands)
    if not n:
        return [], [], []
    d = _yards(pts if pts is not None else getattr(cands, "pts", None), n)
    if isinstance(indoors, str):
        indoors = list(indoors)
    # (a point with no floor found: its nearest neighbor's floors)
    have = [i for i in range(n) if cands[i]]
    if not have:
        raise ValueError("no floor under any point")
    near_have = [i if cands[i] else min(have, key=lambda j: abs(j - i)) for i in range(n)]
    cl = [cands[j] for j in near_have]
    tops = getattr(cands, "top", None)
    top = [tops[j] if tops is not None else max((c.z for c in cands[j] if c.kind == "model"), default=-math.inf)
           for j in near_have]
    Z = [np.array([c.z for c in cs], float) for cs in cl]
    K = [len(z) for z in Z]
    ind = [_flag(_at(indoors, i)) for i in range(n)]
    # A state is a floor, and on a Stairs stretch past its first point also the floor it started on (k * S + j):
    # S[i] of those per floor, 1 off the stairs.
    st = stretches(stairs, d)
    S, step_of, ends = [1] * n, [None] * max(n - 1, 0), {}
    for a, b in st:
        for i in range(a, b):
            step_of[i] = (a, i == a)
        for i in range(a + 1, b + 1):
            S[i] = K[a]
        ends[b] = a
    U = []
    for i in range(n):
        u = np.repeat(_own_costs(cl[i], top[i], ind[i], _at(picked, i)), S[i]).reshape(K[i], S[i])
        if i in ends:  # (a Stairs stretch not climbed: its ends less than STAIR_RISE apart)
            u += np.where(np.abs(Z[i][:, None] - Z[ends[i]][None, :]) < STAIR_RISE, STAIR_MISS, 0.0)
        U.append(u.ravel())
    steps = []
    for i in range(n - 1):
        cost = _step_costs(Z[i], Z[i + 1], float(d[i]), step_of[i] is not None)
        T = np.full((K[i], S[i], K[i + 1], S[i + 1]), np.inf)
        if step_of[i] is None:
            T[:, :, :, 0] = cost[:, None, :]
        elif step_of[i][1]:  # (a stretch's first step: the floor it starts on kept)
            for k in range(K[i]):
                T[k, :, :, k] = cost[k][None, :]
        else:
            for j in range(S[i]):
                T[:, j, :, j] = cost
        steps.append(T.reshape(K[i] * S[i], K[i + 1] * S[i + 1]))
    # forward: the best path's cost to each state (its own cost in), and where it came from
    fwd, back = [U[0]], [None]
    for i in range(n - 1):
        tot = fwd[i][:, None] + steps[i]
        back.append(np.argmin(tot, axis=0))
        fwd.append(tot.min(axis=0) + U[i + 1])
    # backward: the best path's cost on from each state (its own cost out)
    bwd = [None] * n
    bwd[n - 1] = np.zeros(len(U[n - 1]))
    for i in range(n - 2, -1, -1):
        bwd[i] = (steps[i] + (U[i + 1] + bwd[i + 1])[None, :]).min(axis=1)
    s = [0] * n
    s[n - 1] = int(np.argmin(fwd[n - 1]))
    for i in range(n - 1, 0, -1):
        s[i - 1] = int(back[i][s[i]])
    best = float(fwd[n - 1][s[n - 1]])
    inside = np.zeros(n, bool)  # (a Stairs stretch's points between its ends)
    for a, b in st:
        inside[a + 1:b] = True
    zs, kinds, doubt = [], [], []
    for i in range(n):
        c = cl[i][s[i] // S[i]]
        zs.append(round(c.z, 1))
        kinds.append("model" if c.kind == "model" or (c.uid is not None and ind[i] is True) else "ground")
        through = (fwd[i] + bwd[i]).reshape(K[i], S[i]).min(axis=1)
        doubt.append(not inside[i] and bool(((np.abs(Z[i] - c.z) >= AMBIG_Z) & (through <= best + AMBIG_COST)).any()))
    ambiguous = []
    for i in range(n):
        if doubt[i]:
            if ambiguous and ambiguous[-1][1] == i - 1:
                ambiguous[-1] = (ambiguous[-1][0], i)
            else:
                ambiguous.append((i, i))
    return zs, kinds, ambiguous


def pieces(pts, zs, kinds, stairs) -> list[dict]:
    """The track cut where it goes from the terrain onto a model's floors and back, and at each Stairs stretch's ends:
    [{"coords": [[x, y], ...], "zs": [...] or None, "stair": bool}], neighbors sharing their end point. The ground's
    stretches have no heights (the flat land build takes them); a model's stretch has one per point, from the last
    ground point before it to the first after (its doorsteps); a Stairs stretch is "stair" with its heights. A model's
    stretch under DOORMAT_YD long between two of the ground's is the ground (a doormat, a slab: not a building)."""
    n = len(pts)
    P = [(float(p[0]), float(p[1])) for p in pts]
    d = _yards(P, n)
    marks = [(max(0, int(a)), min(n - 1, int(b))) for a, b in stairs or ()]
    on_stairs = [False] * n
    for a, b in marks:
        for i in range(a, b + 1):
            on_stairs[i] = True
    lab = ["model" if k == "model" else "ground" for k in kinds]
    # (doormats: a short model stretch between the ground's, off the stairs)
    i = 0
    while i < n:
        if lab[i] != "model":
            i += 1
            continue
        j = i
        while j + 1 < n and lab[j + 1] == "model":
            j += 1
        if 0 < i and j < n - 1 and not any(on_stairs[i:j + 1]):
            if d[i - 1] / 2 + float(d[i:j].sum()) + d[j] / 2 < DOORMAT_YD:
                lab[i:j + 1] = ["ground"] * (j - i + 1)
        i = j + 1
    # each step's stretch: a Stairs stretch's (which one), else a model's when either end is on one, else the ground's
    seg = []
    for i in range(n - 1):
        m = next((k for k, (a, b) in enumerate(marks) if a <= i < b), None)
        seg.append(("stair", m) if m is not None else ("model" if "model" in (lab[i], lab[i + 1]) else "ground"))
    out = []
    i = 0
    while i < n - 1:
        j = i
        while j + 1 < n - 1 and seg[j + 1] == seg[i]:
            j += 1
        kind = seg[i] if isinstance(seg[i], str) else "stair"
        coords = [list(q) for q in P[i:j + 2]]
        if len(coords) >= 2:
            out.append({"coords": coords, "zs": None if kind == "ground" else [float(z) for z in zs[i:j + 2]],
                        "stair": kind == "stair"})
        i = j + 1
    return out


CITY_BASE = {10001: 0}  # an underground city's level -> its continent (Undercity's: cities.UNDERCITY_ID)


def picks_of(pk, n: int) -> list | None:
    """A recorded walk's floors picked by hand (Record's `rec.pk`, read by tracks.recorded_of: [(point from 1, height
    or None), ...] where the pick changed) as a height or None per point; None when none was picked."""
    if not pk:
        return None
    marks = sorted(pk, key=lambda m: m[0])
    out, cur, k = [], None, 0
    for i in range(1, n + 1):
        while k < len(marks) and marks[k][0] <= i:
            cur = marks[k][1]
            k += 1
        out.append(cur)
    return out if any(v is not None for v in out) else None


class Walks:
    """The road watcher's heights for the walks recorded in game (roads/tracks.py import_tracks' `walks`): a walk's
    floors worked out (candidates, assign) and its pieces (pieces), the client opened at the first walk (`client()`),
    each continent's terrain and placements kept for the next. None for a walk whose heights can't be worked out
    yet (it waits in the saved variables). Its doubts are logged: stretches that could be on another floor."""

    def __init__(self, client, log=print):
        self.client, self.log = client, log
        self.cd = None
        self.ground: dict = {}
        self.placements: dict = {}

    def __call__(self, t: dict):
        level = int(t["continent"])
        cont = CITY_BASE.get(level, level)
        if cont >= 20000:  # (a dungeon's level: the game hides the position there, and Record pauses)
            self.log(f"  recorded walk {t['time']}: in a dungeon, no heights there; it waits")
            return None
        pts = [(float(p[0]), float(p[1])) for p in t["coords"]]
        stairs = [(a - 1, b - 1) for a, b in t.get("stairs") or ()]  # (Record's marks count points from 1)
        # (through a portal: each side its own walk, no road across; portal_steps)
        cuts = portal_steps(pts)
        if cuts:
            out = []
            ind, pk = t.get("ind"), t.get("pk")
            for a, b in zip([0] + [c + 1 for c in cuts], [c + 1 for c in cuts] + [len(pts)]):
                if b - a < 2:
                    continue
                part = dict(t, coords=t["coords"][a:b],
                            stairs=[(max(s0, a) - a + 1, min(s1, b - 1) - a + 1) for s0, s1 in stairs
                                    if s1 > a and s0 < b - 1],
                            ind=ind[a:b] if isinstance(ind, (str, list)) else ind,
                            pk=_picks_from(pk, a, b))
                got = self(part)
                if got is None:
                    return None
                out += got
            return out
        try:
            if self.cd is None:
                self.cd = self.client()
            if cont not in self.ground:
                self.ground[cont] = Ground(self.cd, cont)
                self.placements[cont] = I.placements(self.cd, cont)
            cands = candidates(self.cd, cont, pts, self.ground[cont], self.placements[cont], log=self.log)
            if level != cont:  # (down in an underground city: never on the terrain over it)
                for i, cs in enumerate(cands):
                    cands[i] = [c for c in cs if not (c.kind == "ground" and c.uid is None)]
            zs, kinds, ambiguous = assign(cands, t.get("ind"), stairs, picks_of(t.get("pk"), len(pts)))
        except (Exception, SystemExit) as ex:  # (no client (cli._client exits), no floor under any point: again next time)
            self.log(f"  recorded walk {t['time']}: no heights yet ({ex!r}); it waits")
            return None
        for i, j in ambiguous:
            self.log(f"  recorded walk {t['time']}: points {i + 1}-{j + 1} could be on another floor (mark the stairs, "
                     "or pick the floor with Shift + mouse wheel while recording)")
        return pieces(pts, zs, kinds, stairs)
