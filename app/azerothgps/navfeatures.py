"""Floors, stairs, bridges, lifts and jumps found in our own Recast meshes (asked 2026-11-22: "for 3d interiors, I want to
come up with a detect stairs/bridges/floors automatically for route data ... When creating the city grid,
automatically determine bridges, stairs, lifts, etc.").

A dev tool's analysis over a walk grid (citygrid.Grid: a city's, or a building's from grid_from_mesh) and its mesh,
with the collision triangles the mesh was built from where they're saved (data/navmesh/<name>_tris.npz, `agps navmesh
tris`): nothing of the mesh or the triangles ships, only what citygrid bakes from the result (numbers).

What it finds (`detect`), each with a confidence (0-1):
- **Floors:** the grid's surfaces joined by flat links (FLAT_SLOPE), pieces of FLOOR_MIN_AREA or more: an id, a height
  (the median), its span; stacked floors (over each other) are separate pieces at their own heights. A piece spanning
  more than FLOOR_SPAN in height is open ground ("ground"), not a floor.
- **Stairs and ramps:** (stairs only where the collision has risers: `is_stairs`, a stepped height profile up the
  flight; a smooth slope is a ramp, never said) the surfaces between floors that aren't floors themselves (slopes and the landings too small to
  be one), joined by the grid's links: a run climbing STAIR_RISE or more between its lowest and its highest floor, its
  way up (the shortest walk through it) at a slope in STAIR_SLOPE, mostly one way (MONOTONIC); STAIR_MAX_W wide or less
  "stairs" (a spiral where its ends are close across for its length), wider "ramp", wider than RAMP_MAX_W left out
  (a hillside).
- **Bridges and walkways:** decks DECK_MAX_W wide or less across (the narrowest of four directions over the grid's
  flat links), open on both sides (no wall within SIDE_YD at chest height, by the triangles; nothing to stand on at
  the deck's height beside it, by the grid), with ground, water or a drop under the sides (UNDER_YD or more down); runs
  of BRIDGE_MIN_YD or more joining two areas.
- **Lifts:** the known lifts (Data/Capitals.lua's lift roads, the transports' lifts: their ride time is theirs) found
  on the mesh: a floor at the shaft's foot and one at its top (LIFT_RISE or more apart) with no walk between them
  within LIFT_R across.
- **Jumps and drops** (one way): an upper floor's edge over a lower floor (JUMP_MIN to SAFE_DROP down, never more:
  Nav.FALL_FREE, the drop a player always survives) with nothing in the way at body height and nothing to land on
  between; and short gaps (JUMP_GAP) a running jump crosses at one height, open underneath. Only where the grid's own
  way round is much longer (JUMP_SAVE): a jump that saves nothing isn't one.
- **Steps the mesh lacks** (`gap_links`): two surfaces of neighbor cells STEP_MIN or more apart in height (taller than
  Recast's 1 yd climb), their polys at most STEP_GAP apart across (Recast's 0.4 yd border on each side of a riser) and
  nothing at body height between: a link both ways up to STEP_UP, down only from there to JUMP_MIN, so the grid needs
  no old road there.

Output: `Features` (lists of dicts), `debug_json` for Route Studio (data/debug/navfeatures/<city>.json; floors colored,
stairs yellow, bridges blue, lifts purple, drops and jumps red).
"""

from __future__ import annotations

import heapq
import json
import math
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from . import citygrid as C
from .paths import data_dir

FLAT_SLOPE = 0.2  # yards up a yard across: a link this flat joins a floor
FLOOR_MIN_AREA = 40.0  # square yards: a smaller flat piece is a landing (part of stairs), not a floor
FLOOR_SPAN = 4.0  # yards: a flat piece spanning more in height is open ground (a gentle hillside)
STAIR_RISE = 3.0  # yards: stairs or a ramp climb at least this between two floors
STAIR_SLOPE = (0.15, 1.5)  # yards up a yard walked: stairs' and ramps' slope band
MONOTONIC = 0.75  # the share of a flight's climb that goes the one way
STAIR_MAX_W = 8.0  # yards across: narrower is stairs, wider a ramp
STAIR_PAIR_FLOORS = 6  # the floors a slope area touches most: flights looked for between each pair of them
FLIGHT_SHARED = 0.6  # a flight sharing this share of its cells with one kept is that one
FLIGHT_NEAR_YD = 4.0  # yards: a slope area's cells this near a flight's way up are its width
GRAND_STAIRS_W = 32.0  # yards: a stepped flight's line reaches this wide at the most (half each side) for StairAt
RAMP_MAX_W = 24.0  # ... wider than this is a hillside, left out
SPIRAL_SHARE = 0.55  # a flight whose ends are closer across than this share of its length winds round: a spiral
DECK_MAX_W = 12.0  # yards: a bridge's deck is this narrow or less across
DECK_DZ = 1.0  # yards: a deck's next cell across is at most this far up or down (else its edge) ...
DECK_SLOPE = 0.8  # ... or this many yards a yard (an arched deck)
COVER_YD = 15.0  # yards over a deck: anything of the collision this near over it is a roof (a covered passage, no bridge:
# Stormwind's district gates' barrel vaults are 7-13 yd up) ...
COVER_HITS = 2  # ... over this many of a cell's five probes (its point and 1.2 yd round it: not a lamp's arm)
PARAPET_TOP = 3.0  # yards: a parapet's wall is lower than this over the deck (a passage's is not)
SIDE_YD = 4.0  # yards beside a deck that are open (no wall at chest height, nothing to stand on at its height)
CHEST = 1.6  # yards over the floor: a wall at this height is a wall (a railing is lower)
UNDER_YD = 3.0  # yards: what's under a bridge's side is at least this far down (or nothing: water, a drop)
BRIDGE_MIN_YD = 8.0  # yards: a deck run this long at the least
LIFT_R = 8.0  # yards round a lift's shaft where its foot's and top's floors are looked for
LIFT_RISE = 10.0  # yards: a shaft's floors at least this far apart
SAFE_DROP = 14.0  # yards: Nav.FALL_FREE, the drop a player always survives (the health is secret: never more) ...
BIG_DROP = 400.0  # ... and the biggest kept for a fall spell (Slow Fall, Levitate: any height, #948; taken only while one is ready,
# the game's max drop against the link's own heights: CityGrid.MaxDrop, the world grid's x.maxDrop)
JUMP_MIN = 3.0  # yards down: a smaller drop is a step down (gap_links), not said
JUMP_DOWN_GAP = 2.0  # yards across between the ledge's poly and the one landed on at the most
JUMP_REACH = 4.5  # yards across from the edge's surface to the one landed on
JUMP_GAP = (1.5, 3.5)  # yards across a gap at one height a running jump crosses
JUMP_SAVE = 25.0  # yards: a jump is a link only where the grid's own way round is this much longer (or none)
JUMP_SPACING = 6.0  # yards: jumps along one ledge kept at least this far apart
JUMP_COST = 10.0  # yards a jump's link costs over its own: taken where it saves that much (the walk down first)
STEP_MIN = 1.0  # yards: a step the mesh lacks (taller than Recast's climb) ...
STEP_UP = 1.5  # ... walked up and down to this height, down only from there to JUMP_MIN
STEP_GAP = 1.0  # yards across between the step's two polys at the most (Recast's 0.4 border each side of the riser)
BODY = (0.5, 1.2, 1.8)  # yards over the floor a body's way is checked at (no wall, no railing)
USE_CONF = 0.75  # the confidence a link needs to go into the grid (else reported only)

BAKE_PARAMS = ("FLAT_SLOPE", "FLOOR_MIN_AREA", "FLOOR_SPAN", "STAIR_RISE", "STAIR_SLOPE", "MONOTONIC", "STAIR_MAX_W", "GRAND_STAIRS_W", "STAIR_PAIR_FLOORS", "FLIGHT_SHARED",
               "FLIGHT_NEAR_YD",
               "RAMP_MAX_W", "SPIRAL_SHARE", "DECK_MAX_W", "DECK_DZ", "DECK_SLOPE", "COVER_YD", "COVER_HITS",
               "PARAPET_TOP", "SIDE_YD", "CHEST",
               "UNDER_YD", "BRIDGE_MIN_YD",
               "LIFT_R", "LIFT_RISE", "SAFE_DROP", "BIG_DROP", "JUMP_MIN", "JUMP_DOWN_GAP", "JUMP_REACH", "JUMP_GAP", "JUMP_SAVE",
               "JUMP_SPACING", "JUMP_COST", "RISER_STEP", "RISER_DZ", "RISER_SHARE", "RISERS_MIN", "RISER_OFFSETS",
               "STEP_MIN", "STEP_UP", "STEP_GAP", "BODY", "USE_CONF", "STAIRS_ROAD_YD", "STAIRS_ROAD_Z",
               "LIFT_EXIT_SEARCH", "LIFT_EXIT_YD", "LIFT_RIM_SHARE", "LIFT_RIM_Z", "TRACK_CHUNK", "TRACK_FACTOR", "WALL_HEIGHTS",
               "BIG_DROP_ROUND", "WALL_LEVEL_DZ", "WALL_SEG_MIN", "TRACK_DROP_Z", "TRACK_DROP_SLOPE",
               "CLIMB_MAX_SLOPE")

K_STAIRS, K_BRIDGE, K_LIFT, K_DROP, K_JUMP = "stairs", "bridge", "lift", "drop", "jump"


# --- the collision triangles ------------------------------------------------------------------------------------------

def tris_path(mesh_name: str) -> Path:
    return data_dir() / "navmesh" / f"{mesh_name}_tris.npz"


def tris_stamp(mesh_name: str) -> str:
    import hashlib
    p = tris_path(mesh_name)
    return hashlib.sha1(p.read_bytes()).hexdigest()[:12] if p.exists() else "none"


def save_tris(cd, only=None, log=print) -> list:
    """`agps navmesh tris`: each mesh's collision triangles (recastmesh.sources': the models, doodads and ground it was
    built from) and its models' liquids (quads and their surface heights, the world's frame) into
    data/navmesh/<name>_tris.npz, for the checks here (dev data, never shipped)."""
    from . import capitals as CP
    from . import cities
    from . import recastmesh as RM

    caps = {c.name: c for c in CP.CAPITALS}
    out = []
    for name, cont, level, triangles in RM.sources():
        if only and not any(o.lower() in name.lower() for o in only):
            continue
        T, _box, _walk = triangles(cd, log)
        quads, lz = [], []
        if name in caps:
            for corners, z in CP.city_faces(cd, caps[name], log=lambda *a: None)[2]:
                quads.append(corners)
                lz.append(z)
        elif level is not None:  # (Undercity's canals: its model's liquids, placed as its triangles are)
            pl, _names = cities.placement(cd)
            for _gi, (x0, y0, x1, y1), z in cities._liquids(cd, pl.wmo):
                q = np.array([[[x0, y0, z], [x1, y0, z], [x1, y1, z]], [[x0, y1, z], [x0, y1, z], [x0, y1, z]]], float)
                W = RM.to_world(q, pl.x, pl.y, pl.z, pl.yaw)
                quads.append([tuple(W[0, 0, :2]), tuple(W[0, 1, :2]), tuple(W[0, 2, :2]), tuple(W[1, 0, :2])])
                lz.append(float(W[0, 0, 2]))
        ceil = _ceilings(cd, name, caps.get(name), level)
        p = tris_path(name.lower().replace(" ", "_"))
        p.parent.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(p, T=np.asarray(T, np.float32), lq=np.asarray(quads, np.float64).reshape(-1, 4, 2),
                            lz=np.asarray(lz, np.float64), C=np.asarray(ceil, np.float32).reshape(-1, 3, 3))
        log(f"  {name}: {len(T)} triangles, {len(lz)} liquid tiles, {len(ceil)} ceiling faces: {p}")
        out.append(p)
    return out


def _ceilings(cd, name, cap, level) -> list:
    """The city's models' faces facing down (vaults, roofs' undersides, a gatehouse's passage) in the world: the
    collision's walls and floors leave them out, and a deck under one is covered, no bridge."""
    from . import cities
    from . import interiors as I
    from . import recastmesh as RM
    from . import walknet

    out = []
    if cap is not None:
        placed = {p.uid: p for p in I.placements(cd, cap.cont) if p.uid in cap.wmos}
        for uid in cap.wmos:
            p = placed.get(uid)
            if p is None:
                continue
            xf = walknet.Placed(p)
            ceil: list = []
            walknet.model_faces(cd, p.wmo, 0.64, ceilings=ceil)
            out += [[xf(v) for v in tri] for _gi, tri in ceil]
    elif level is not None:
        pl, _names = cities.placement(cd)
        ceil = []
        walknet.model_faces(cd, pl.wmo, 0.64, ceilings=ceil)
        if ceil:
            out = RM.to_world(np.array([tri for _gi, tri in ceil], float), pl.x, pl.y, pl.z, pl.yaw).tolist()
    return out


class Tris:
    """The collision triangles (N, 3, 3) bucketed by BUCKET yards across, for segment tests; and the models' liquids."""

    BUCKET = 4.0
    BIG_BUCKET = 64.0  # yards: the bigger triangles' buckets (more than 16 BUCKETs)

    def __init__(self, T: np.ndarray, lq=None, lz=None):
        self.lq = np.zeros((0, 4, 2)) if lq is None else np.asarray(lq, float)
        self.lz = np.zeros(0) if lz is None else np.asarray(lz, float)
        self.T = np.asarray(T, np.float64)
        B = self.BUCKET
        lo = np.floor(self.T[:, :, :2].min(axis=1) / B).astype(np.int64)
        hi = np.floor(self.T[:, :, :2].max(axis=1) / B).astype(np.int64)
        span = (hi - lo + 1).prod(axis=1)
        self.big = np.nonzero(span > 16)[0]
        small = np.nonzero(span <= 16)[0]
        keys, ids = [], []
        for dx in range(4):
            for dy in range(4):
                sel = small[(lo[small, 0] + dx <= hi[small, 0]) & (lo[small, 1] + dy <= hi[small, 1])]
                keys.append((lo[sel, 0] + dx + 100000) * 1000000 + (lo[sel, 1] + dy + 100000))
                ids.append(sel)
        keys, ids = np.concatenate(keys), np.concatenate(ids)
        order = np.argsort(keys, kind="stable")
        keys, ids = keys[order], ids[order]
        uk, start = np.unique(keys, return_index=True)
        ends = np.append(start[1:], len(keys))
        self.cells = {int(k): ids[a:b] for k, a, b in zip(uk.tolist(), start.tolist(), ends.tolist())}
        # (the big ones by BIG_BUCKET buckets too, the huge ones (more than 16 of those) always looked at: a segment's
        # candidates were every big triangle, made unique again on each test)
        BB = self.BIG_BUCKET
        blo = np.floor(self.T[self.big, :, :2].min(axis=1) / BB).astype(np.int64)
        bhi = np.floor(self.T[self.big, :, :2].max(axis=1) / BB).astype(np.int64)
        bspan = (bhi - blo + 1).prod(axis=1)
        self.huge = self.big[bspan > 16]
        self.big_cells = {}
        for r in np.nonzero(bspan <= 16)[0].tolist():
            for a in range(int(blo[r, 0]), int(bhi[r, 0]) + 1):
                for b in range(int(blo[r, 1]), int(bhi[r, 1]) + 1):
                    self.big_cells.setdefault((a, b), []).append(int(self.big[r]))
        self.big_cells = {k: np.array(v, np.int64) for k, v in self.big_cells.items()}
        self.E1, self.E2 = self.T[:, 1] - self.T[:, 0], self.T[:, 2] - self.T[:, 0]
        self.zlo, self.zhi = self.T[:, :, 2].min(axis=1), self.T[:, :, 2].max(axis=1)

    @classmethod
    def load(cls, mesh_name: str):
        p = tris_path(mesh_name)
        if not p.exists():
            return None
        d = np.load(p)
        t = cls(d["T"], d["lq"] if "lq" in d else None, d["lz"] if "lz" in d else None)
        t.ceil = cls(d["C"]) if "C" in d and len(d["C"]) else None
        return t

    def covered(self, x, y, z, reach) -> bool:
        """Whether a ceiling (a face facing down: a vault, a roof's underside) is within `reach` over (x, y, z), or the
        collision itself is."""
        if self.hit((x, y, z + 0.5), (x, y, z + reach)) is not None:
            return True
        return getattr(self, "ceil", None) is not None and self.ceil.hit((x, y, z + 0.5), (x, y, z + reach)) is not None

    def wet(self, x, y, z, depth=1.0) -> bool:
        """Whether (x, y, z) is more than `depth` under one of the models' liquids (a pool's or a canal's floor)."""
        if not len(self.lz):
            return False
        Q = self.lq
        inside = np.ones(len(Q), bool)
        for k in range(4):  # (each quad convex: on the same side of all four edges)
            a, b = Q[:, k], Q[:, (k + 1) % 4]
            cr = (b[:, 0] - a[:, 0]) * (y - a[:, 1]) - (b[:, 1] - a[:, 1]) * (x - a[:, 0])
            if k == 0:
                sign = np.sign(cr)
            inside &= (np.sign(cr) == sign) | (cr == 0)
        return bool((inside & (z < self.lz - depth)).any())

    def _cands(self, x0, y0, x1, y1, z0, z1):
        """The triangles' ids whose buckets the box touches and whose heights reach z0-z1."""
        # (a triangle is in each of its buckets once: only a box over more than one bucket gets one twice. The order
        # doesn't matter to `hits`, the nearest hit of them all)
        B = self.BUCKET
        ids = []
        for a in range(int(math.floor(min(x0, x1) / B)), int(math.floor(max(x0, x1) / B)) + 1):
            for b in range(int(math.floor(min(y0, y1) / B)), int(math.floor(max(y0, y1) / B)) + 1):
                v = self.cells.get((a + 100000) * 1000000 + (b + 100000))
                if v is not None:
                    ids.append(v)
        if len(ids) > 1:
            ids = [np.unique(np.concatenate(ids))]
        B = self.BIG_BUCKET
        big = []
        for a in range(int(math.floor(min(x0, x1) / B)), int(math.floor(max(x0, x1) / B)) + 1):
            for b in range(int(math.floor(min(y0, y1) / B)), int(math.floor(max(y0, y1) / B)) + 1):
                v = self.big_cells.get((a, b))
                if v is not None:
                    big.append(v)
        if len(big) > 1:
            big = [np.unique(np.concatenate(big))]
        ids += big
        if len(self.huge):
            ids.append(self.huge)
        if not ids:
            return ids
        ids = np.concatenate(ids) if len(ids) > 1 else ids[0]
        return ids[(self.zlo[ids] <= max(z0, z1)) & (self.zhi[ids] >= min(z0, z1))]

    def hits(self, segs) -> list:
        """For each (p, q) (3D points): the first hit along p -> q as a share of the way (0-1), or None."""
        P = np.asarray([s[0] for s in segs], float)
        Q = np.asarray([s[1] for s in segs], float)
        lo, hi = np.minimum(P, Q), np.maximum(P, Q)
        ids = self._cands(lo[:, 0].min(), lo[:, 1].min(), hi[:, 0].max(), hi[:, 1].max(), lo[:, 2].min(), hi[:, 2].max())
        out = [None] * len(segs)
        if not len(ids):
            return out
        T0, e1, e2 = self.T[ids, 0], self.E1[ids], self.E2[ids]
        for r in range(len(segs)):
            p, d = P[r], Q[r] - P[r]
            hx = d[1] * e2[:, 2] - d[2] * e2[:, 1]
            hy = d[2] * e2[:, 0] - d[0] * e2[:, 2]
            hz = d[0] * e2[:, 1] - d[1] * e2[:, 0]
            a = e1[:, 0] * hx + e1[:, 1] * hy + e1[:, 2] * hz
            ok = np.abs(a) > 1e-9
            f = np.where(ok, 1.0 / np.where(ok, a, 1), 0)
            sx, sy, sz = p[0] - T0[:, 0], p[1] - T0[:, 1], p[2] - T0[:, 2]
            u = f * (sx * hx + sy * hy + sz * hz)
            qx = sy * e1[:, 2] - sz * e1[:, 1]
            qy = sz * e1[:, 0] - sx * e1[:, 2]
            qz = sx * e1[:, 1] - sy * e1[:, 0]
            v = f * (qx * d[0] + qy * d[1] + qz * d[2])
            t = f * (e2[:, 0] * qx + e2[:, 1] * qy + e2[:, 2] * qz)
            m = ok & (u >= 0) & (v >= 0) & (u + v <= 1) & (t > 1e-6) & (t < 1 - 1e-6)
            if m.any():
                out[r] = float(t[m].min())
        return out

    def hit(self, p, q) -> float | None:
        """The first hit along p -> q (3D points) as a share of the way (0-1), or None."""
        return self.hits([(p, q)])[0]

    def clear(self, p, q) -> bool:
        return self.hit(p, q) is None

    def first_below(self, x, y, z, depth=200.0) -> float | None:
        """Yards down from (x, y, z) to the first triangle under it, or None."""
        t = self.hit((x, y, z), (x, y, z - depth))
        return None if t is None else t * depth


# --- the grid's surfaces as nodes -------------------------------------------------------------------------------------

def _z(g, n):
    return g.surf[n[:2]][n[2]][0]


def _pt(g, n):
    s = g.surf[n[:2]][n[2]]
    return (s[2], s[3], s[0])


def _grid_nbrs(g, n):
    i, j, _k = n
    row = g.links.get(n)
    if row:
        for d, kk in enumerate(row):
            if kk >= 0:
                dx, dy = C.DIRS[d]
                yield (i + dx, j + dy, kk), g.cell * (math.sqrt(2) if dx and dy else 1)


def nodes(g):
    return [(i, j, k) for (i, j), ss in g.surf.items() for k in range(len(ss))]


@dataclass
class Features:
    city: str
    cell: float
    floors: list = field(default_factory=list)
    stairs: list = field(default_factory=list)
    bridges: list = field(default_factory=list)
    lifts: list = field(default_factory=list)
    jumps: list = field(default_factory=list)  # (drops down and jumps across)
    steps: list = field(default_factory=list)  # (gap_links' steps the mesh lacks)
    floor_of: dict = field(default_factory=dict)  # node -> floor id

    def counts(self) -> dict:
        return {"floors": sum(f["kind"] == "floor" for f in self.floors),
                "ground": sum(f["kind"] == "ground" for f in self.floors),
                "stacked floors": sum(bool(f["stacked"]) for f in self.floors),
                "stairs": sum(s["kind"] in ("stairs", "spiral") for s in self.stairs),
                "spirals": sum(s["kind"] == "spiral" for s in self.stairs),
                "ramps": sum(s["kind"] == "ramp" for s in self.stairs),
                "bridges": len(self.bridges), "lifts": len(self.lifts),
                "drops": sum(j["kind"] == "down" for j in self.jumps),
                "jumps across": sum(j["kind"] == "across" for j in self.jumps),
                "steps": len(self.steps)}


# --- floors -------------------------------------------------------------------------------------------------------

def find_floors(g, feats: Features) -> None:
    flat = defaultdict(list)
    all_n = nodes(g)
    for n in all_n:
        zn = _z(g, n)
        for m, d in _grid_nbrs(g, n):
            if abs(_z(g, m) - zn) <= FLAT_SLOPE * d:
                flat[n].append(m)
    seen = {}
    pieces = []
    for n in all_n:
        if n in seen:
            continue
        idx = len(pieces)
        st, piece = [n], []
        seen[n] = idx
        while st:
            p = st.pop()
            piece.append(p)
            for q in flat[p]:
                if q not in seen:
                    seen[q] = idx
                    st.append(q)
        pieces.append(piece)
    area = g.cell * g.cell
    for piece in pieces:
        if len(piece) * area < FLOOR_MIN_AREA:
            continue
        zs = np.array([_z(g, n) for n in piece])
        fid = len(feats.floors)
        lo, hi = np.percentile(zs, [5, 95])
        xs = [_pt(g, n)[0] for n in piece]
        ys = [_pt(g, n)[1] for n in piece]
        feats.floors.append({"id": fid, "z": round(float(np.median(zs)), 1), "zmin": round(float(lo), 1),
                             "zmax": round(float(hi), 1), "cells": len(piece), "area": round(len(piece) * area),
                             "box": [round(min(xs), 1), round(min(ys), 1), round(max(xs), 1), round(max(ys), 1)],
                             "kind": "ground" if hi - lo > FLOOR_SPAN else "floor", "stacked": []})
        for n in piece:
            feats.floor_of[n] = fid
    # (stacked: floors with cells over each other's)
    by_cell = defaultdict(set)
    for n, f in feats.floor_of.items():
        by_cell[n[:2]].add(f)
    pairs = set()
    for fs in by_cell.values():
        if len(fs) > 1:
            for a in fs:
                for b in fs:
                    if a < b:
                        pairs.add((a, b))
    for a, b in pairs:
        feats.floors[a]["stacked"].append(b)
        feats.floors[b]["stacked"].append(a)


# --- stairs and ramps ---------------------------------------------------------------------------------------------

def _simplify(pts, step=3.0):
    out = [pts[0]]
    along = 0.0
    for a, b in zip(pts, pts[1:]):
        along += math.dist(a[:2], b[:2])
        if along >= step:
            out.append(b)
            along = 0.0
    if out[-1] != pts[-1]:
        out.append(pts[-1])
    return [tuple(round(v, 1) for v in p) for p in out]


def find_stairs(g, feats: Features, tris=None) -> None:
    fl = feats.floor_of
    rest = [n for n in nodes(g) if n not in fl]
    rest_set = set(rest)
    seen = set()
    for n0 in rest:
        if n0 in seen:
            continue
        comp, st = [], [n0]
        seen.add(n0)
        while st:
            p = st.pop()
            comp.append(p)
            for q, _d in _grid_nbrs(g, p):
                if q in rest_set and q not in seen:
                    seen.add(q)
                    st.append(q)
        contacts = defaultdict(list)  # floor -> [(comp node, floor node)]
        for p in comp:
            for q, _d in _grid_nbrs(g, p):
                f = fl.get(q)
                if f is not None:
                    contacts[f].append((p, q))
        if len(contacts) < 2:
            continue
        # (each pair of the floors it touches most, a climb apart: one slope area can hold several flights, the Cathedral
        # of Light's steps beside a canal's ramp; a flight sharing most of its cells with one already kept is that one)
        cs = set(comp)
        top_floors = sorted(contacts, key=lambda f: -len(contacts[f]))[:STAIR_PAIR_FLOORS]
        # (each floor's height where the area meets it: a piece of open ground spans a range, its median isn't here)
        cz = {f: float(np.median([_z(g, q) for _p, q in contacts[f]])) for f in top_floors}
        pairs = sorted(((lo, hi) for lo in top_floors for hi in top_floors if cz[hi] - cz[lo] >= STAIR_RISE),
                       key=lambda ab: cz[ab[0]] - cz[ab[1]])
        kept_paths = []
        for lo_f, hi_f in pairs:
            _flight(g, feats, tris, comp, cs, contacts, lo_f, hi_f, kept_paths, cz[hi_f] - cz[lo_f])


def _flight(g, feats, tris, comp, cs, contacts, lo_f, hi_f, kept_paths, rise) -> None:
    """The flight between floors lo_f and hi_f (`rise` apart where the area meets them) through the slope area `comp`
    (find_stairs), if it's one."""
    if rise < STAIR_RISE:
        return
    # (the way up through it: from the low floor's contacts to the high floor's)
    goal = {p for p, _q in contacts[hi_f]}
    dist, prev = {}, {}
    h = []
    for p, q in contacts[lo_f]:
        d0 = math.dist(_pt(g, q)[:2], _pt(g, p)[:2])
        if d0 < dist.get(p, math.inf):
            dist[p], prev[p] = d0, q
            heapq.heappush(h, (d0, p))
    end = None
    while h:
        d, p = heapq.heappop(h)
        if d > dist.get(p, math.inf):
            continue
        if p in goal:
            end = p
            break
        for q, c in _grid_nbrs(g, p):
            if q in cs and d + c < dist.get(q, math.inf):
                dist[q], prev[q] = d + c, p
                heapq.heappush(h, (d + c, q))
    if end is None:
        return
    top = next(q for p, q in contacts[hi_f] if p == end)
    path = [top, end]
    while path[-1] in prev and path[-1] in cs:
        path.append(prev[path[-1]])
    path.reverse()
    pset = set(path)
    if any(len(pset & u) >= FLIGHT_SHARED * len(pset) for u in kept_paths):
        return
    kept_paths.append(pset)
    pts = [_pt(g, n) for n in path]
    L = sum(math.dist(a[:2], b[:2]) for a, b in zip(pts, pts[1:])) or g.cell
    dzs = [b[2] - a[2] for a, b in zip(pts, pts[1:])]
    mono = abs(sum(dzs)) / (sum(abs(d) for d in dzs) or 1)
    # (its width: the slope area's cells near its way up, not the whole area's)
    near = sum(1 for n in comp if min(math.dist(_pt(g, n)[:2], q[:2]) for q in pts) <= FLIGHT_NEAR_YD)
    width = max(g.cell, near * g.cell * g.cell / L)
    slope = rise / L
    across = math.dist(pts[0][:2], pts[-1][:2])
    # (a smooth slope is a ramp however narrow: Orgrimmar's gate's incline said "Stairs up", Kooki3z 2026-11-22.
    # Stairs have risers in the collision; without the triangles it can't be told, and nothing is called stairs.
    # With risers, a flight is stairs however wide: Stormwind's Cathedral of Light's grand staircase, 2026-11-22)
    share, risers = stepped(tris, pts)
    has_risers = share >= RISER_SHARE and risers >= RISERS_MIN
    if width > RAMP_MAX_W and not has_risers:
        return  # (a hillside)
    if not has_risers:
        kind = "ramp"
    else:
        kind = "spiral" if across < SPIRAL_SHARE * L and L > 12 else "stairs"
    conf = 0.3 + (0.25 if mono >= MONOTONIC else 0) + (0.2 if STAIR_SLOPE[0] <= slope <= STAIR_SLOPE[1] else 0) \
        + (0.25 if width <= STAIR_MAX_W or has_risers else 0)
    feats.stairs.append({"id": len(feats.stairs), "kind": kind, "risers": risers, "riser_share": share,
                         "low": lo_f, "high": hi_f, "rise": round(rise, 1),
                         "length": round(L, 1), "width": round(width, 1), "slope": round(slope, 2),
                         "monotonic": round(mono, 2), "pts": _simplify(pts), "nodes": len(comp),
                         "conf": round(min(conf, 1.0), 2)})


# --- bridges ------------------------------------------------------------------------------------------------------

AXES = ((1, 0), (0, 1), (1, 1), (1, -1))


def _run(g, n, dx, dy):
    """Cells walked from n along (dx, dy) over flat-ish links, and the last node."""
    d = C.DIRS.index((dx, dy))
    cnt, cur = 0, n
    while cnt < 12:
        row = g.links.get(cur)
        if not row or row[d] < 0:
            break
        nxt = (cur[0] + dx, cur[1] + dy, row[d])
        # (a deck may arch: Stormwind's canal bridges climb to their middle; a step of DECK_SLOPE a yard is the deck)
        if abs(_z(g, nxt) - _z(g, cur)) > max(DECK_DZ, DECK_SLOPE * g.cell * math.hypot(dx, dy)):
            break
        cur, cnt = nxt, cnt + 1
    return cnt, cur


def _side_open(g, tris, n, dx, dy, z) -> tuple[bool, bool]:
    """Beside the edge node n, going on (dx, dy): (open at the deck's height, something under it far down or nothing)."""
    x, y, _ = _pt(g, n)
    L = math.hypot(dx, dy)
    ux, uy = dx / L, dy / L
    # nothing to stand on at the deck's height out to SIDE_YD
    steps = int(math.ceil(SIDE_YD / g.cell))
    for s in range(1, steps + 1):
        c = (n[0] + dx * s, n[1] + dy * s)
        for t in g.surf.get(c, ()):
            if abs(t[0] - z) <= 2.5:
                return False, False
    if tris is None:
        return True, True
    p = (x, y, z + CHEST)
    q = (x + ux * SIDE_YD, y + uy * SIDE_YD, z + CHEST)
    below = tris.first_below(x + ux * (g.cell * 0.5 + 1.5), y + uy * (g.cell * 0.5 + 1.5), z + 0.5)
    drop = below is None or below >= UNDER_YD
    # (a wall at chest height: closed, unless it's a parapet with the drop right past it: Stormwind's canal bridges'
    # stone sides; a corridor's wall has the next room's floor past it, not a drop. A parapet is low: clear over it at
    # PARAPET_TOP; a passage's wall (a gatehouse's over a canal, the drop past it too) is not)
    if not tris.clear(p, q):
        if not drop:
            return False, False
        if not tris.clear((x, y, z + PARAPET_TOP), (x + ux * SIDE_YD, y + uy * SIDE_YD, z + PARAPET_TOP)):
            return False, False
    return True, drop


def find_bridges(g, feats: Features, tris=None) -> None:
    deck = {}
    for n in nodes(g):
        z = _z(g, n)
        best = None
        for dx, dy in AXES:
            a, na = _run(g, n, dx, dy)
            b, nb = _run(g, n, -dx, -dy)
            w = (a + b) * g.cell * math.hypot(dx, dy) + g.cell  # (the middle cell one cell across, diagonals too)
            if best is None or w < best[0]:
                best = (w, dx, dy, na, nb)
        w, dx, dy, na, nb = best
        if w > DECK_MAX_W:
            continue
        # (a covered deck is no bridge: a gatehouse's passage over a canal, Stormwind's Trade District gate; its roof
        # or vault over the body)
        if tris is not None:
            x, y, _z0 = _pt(g, n)
            probes = [(x, y)] + [(x + ox, y + oy) for ox, oy in ((1.2, 1.2), (-1.2, 1.2), (1.2, -1.2), (-1.2, -1.2))]
            if sum(tris.covered(px, py, z, COVER_YD) for px, py in probes) >= COVER_HITS:
                continue
        o1, u1 = _side_open(g, tris, na, dx, dy, z)
        if not o1:
            continue
        o2, u2 = _side_open(g, tris, nb, -dx, -dy, z)
        if not o2:
            continue
        deck[n] = (w, u1 and u2)
    seen = set()
    for n0 in deck:
        if n0 in seen:
            continue
        comp, st = [], [n0]
        seen.add(n0)
        while st:
            p = st.pop()
            comp.append(p)
            for q, dq in _grid_nbrs(g, p):
                if q in deck and q not in seen and abs(_z(g, q) - _z(g, p)) <= max(DECK_DZ, DECK_SLOPE * dq):
                    seen.add(q)
                    st.append(q)
        P = np.array([_pt(g, n) for n in comp])
        if len(P) < 2:
            continue
        c = P[:, :2].mean(axis=0)
        _u, _s, vt = np.linalg.svd(P[:, :2] - c, full_matrices=False)
        ax = vt[0]
        proj = (P[:, :2] - c) @ ax
        length = float(proj.max() - proj.min()) + g.cell
        widths = [deck[n][0] for n in comp]
        wmed = float(np.median(widths))
        if length < BRIDGE_MIN_YD or length < 1.5 * wmed:
            continue
        # (joining two areas: ground off the deck at both its ends)
        ends = []
        for n in comp:
            for q, _d in _grid_nbrs(g, n):
                if q not in deck:
                    ends.append(float((np.array(_pt(g, n)[:2]) - c) @ ax))
        if not ends or max(ends) - min(ends) < 0.6 * length:
            continue
        under = sum(deck[n][1] for n in comp) / len(comp)
        # (the deck's middle line: its points binned along it)
        bins = defaultdict(list)
        for p, t in zip(P, proj):
            bins[int((t - proj.min()) // 3)].append(p)
        line = [tuple(round(float(v), 1) for v in np.mean(bins[k], axis=0)) for k in sorted(bins)]
        conf = (0.55 if tris is None else 0.7) + 0.25 * under + (0.05 if wmed <= 6 else 0)
        feats.bridges.append({"id": len(feats.bridges), "length": round(length, 1), "width": round(wmed, 1),
                              "z": round(float(np.median(P[:, 2])), 1), "pts": line, "nodes": len(comp),
                              "open_under": round(under, 2), "conf": round(min(conf, 1.0), 2),
                              "cells": [list(n) for n in comp]})


# --- lifts --------------------------------------------------------------------------------------------------------

def find_lifts(mesh: C.Mesh, feats: Features, known) -> None:
    """`known`: [(name, foot (x, y, z), top (x, y, z) or None, cost)] (the lifts' data). Each found on the mesh: a floor
    at its foot and one at its top (straight over the foot where the top isn't known: the first LIFT_RISE over it), at
    least LIFT_RISE apart, with no walk between them round the shaft."""
    cents = np.array([np.mean(vs, axis=0) for vs in mesh.vs]) if mesh.vs else np.zeros((0, 3))
    for name, foot_p, top_p, cost in known:
        fx, fy, zf = foot_p
        tx, ty, zt = top_p if top_p is not None else (fx, fy, None)
        near_f = np.nonzero(np.hypot(cents[:, 0] - fx, cents[:, 1] - fy) <= LIFT_R)[0]
        near_t = np.nonzero(np.hypot(cents[:, 0] - tx, cents[:, 1] - ty) <= LIFT_R)[0]
        row = {"name": name, "x": round(fx, 1), "y": round(fy, 1), "cost": cost}
        if not len(near_f) or not len(near_t):
            feats.lifts.append({**row, "found": False, "conf": 0.0})
            continue
        foot = float(min(cents[near_f, 2], key=lambda z: abs(z - zf)))
        tops = cents[near_t, 2]
        # (the top unknown: the first floor LIFT_RISE or more over the foot, straight up the shaft; not a roof higher)
        up = tops[tops >= foot + LIFT_RISE]
        top = float(min(tops, key=lambda z: abs(z - zt)) if zt is not None else (up.min() if len(up) else tops.max()))
        # (no walk between: the polys round the shaft from its foot's height never climb to its top's by neighbors)
        ids = {int(i) for i in near_f} | {int(i) for i in near_t}
        lo = {i for i in ids if abs(cents[i, 2] - foot) <= 2}
        st, reach = list(lo), set(lo)
        while st:
            p = st.pop()
            for q in mesh.nb[p]:
                if q in ids and q not in reach:
                    reach.add(q)
                    st.append(q)
        walked = any(abs(cents[i, 2] - top) <= 2 for i in reach)
        rise = top - foot
        ok = rise >= LIFT_RISE and not walked
        conf = 0.5 + 0.25 * (abs(foot - zf) <= 3) + 0.25 * (zt is None or abs(top - zt) <= 3) if ok else 0.2
        feats.lifts.append({**row, "foot": round(foot, 1), "top": round(top, 1), "rise": round(rise, 1),
                            "top_xy": [round(tx, 1), round(ty, 1)], "found": bool(ok), "walked": bool(walked),
                            "conf": round(float(conf), 2)})


# --- jumps and steps ----------------------------------------------------------------------------------------------

def _body_clear(tris, a, b, zbase):
    if tris is None:
        return False
    return all(t is None for t in tris.hits([((a[0], a[1], zbase + h), (b[0], b[1], zbase + h)) for h in BODY]))


def _polys_gap(mesh, pa, pb):
    """Yards across between two sets of polys' outlines (0 where they touch or overlap)."""
    best = math.inf
    for p in pa:
        for q in pb:
            P, Q = mesh.vs[p], mesh.vs[q]
            for X, Y in ((P, Q), (Q, P)):
                for v in X:
                    for k in range(len(Y)):
                        a, b = Y[k], Y[(k + 1) % len(Y)]
                        vx, vy = b[0] - a[0], b[1] - a[1]
                        L2 = vx * vx + vy * vy
                        t = 0 if L2 == 0 else max(0.0, min(1.0, ((v[0] - a[0]) * vx + (v[1] - a[1]) * vy) / L2))
                        best = min(best, math.hypot(v[0] - a[0] - vx * t, v[1] - a[1] - vy * t))
    return best


def _edge_toward(g, n, di, dj) -> bool:
    """Whether n's floor ends toward (di, dj): no link that way onto a surface about its height."""
    d = C.DIRS.index(((di > 0) - (di < 0), (dj > 0) - (dj < 0)))
    row = g.links.get(n)
    if not row or row[d] < 0:
        return True
    dx, dy = C.DIRS[d]
    return abs(_z(g, (n[0] + dx, n[1] + dy, row[d])) - _z(g, n)) > STEP_UP


def gap_links(g, mesh, tris, feats: Features | None = None):
    """The steps and jumps the mesh lacks, as grid links: [(a, b, cost, kind, pts, conf, info)] (kind citygrid's:
    KIND_WALK a step (both ways up to STEP_UP, else down only), KIND_DROP a jump down, KIND_JUMP one across). Each with
    its confidence; build() takes those at USE_CONF or more. Needs the triangles (nothing without them)."""
    out, cands = [], []
    if tris is None:
        return out
    gaps = {}

    def gap_of(n, m):
        key = (n, m) if n < m else (m, n)
        v = gaps.get(key)
        if v is None:
            v = gaps[key] = _polys_gap(mesh, g.surf[n[:2]][n[2]][1], g.surf[m[:2]][m[2]][1])
        return v
    reach = int(math.ceil(JUMP_REACH / g.cell))
    steps = []
    for n in nodes(g):
        zn = _z(g, n)
        ps = g.surf[n[:2]][n[2]]
        linked = {m for m, _d in _grid_nbrs(g, n)}
        for di in range(-reach, reach + 1):
            for dj in range(-reach, reach + 1):
                if not (di or dj):
                    continue
                tt = g.surf.get((n[0] + di, n[1] + dj))
                if not tt or not _edge_toward(g, n, di, dj):
                    continue
                near = max(abs(di), abs(dj)) == 1
                for kk, t in enumerate(tt):
                    m = (n[0] + di, n[1] + dj, kk)
                    if m in linked:
                        continue
                    dz = zn - t[0]
                    d = math.dist(ps[2:4], t[2:4])
                    if near and 0 <= dz < JUMP_MIN:  # (a step, or a seam in the mesh at one height)
                        steps.append((n, m, d, dz))
                    elif JUMP_MIN <= dz <= BIG_DROP and d <= JUMP_REACH:
                        cands.append(("down", n, m, d, dz))
                    elif abs(dz) <= 1.0 and JUMP_GAP[0] <= d <= JUMP_GAP[1] + g.cell and not near:
                        cands.append(("across", n, m, d, dz))
    # (steps: the two polys close across (a riser between), nothing at body height over it; each pair once. Not links of
    # their own (apply: a step confirms a road link's stretch, which then becomes the step's two points): `steps`)
    done = set()
    for n, m, d, dz in steps:
        if (n, m) in done:
            continue
        done.add((n, m))
        done.add((m, n))
        gap = gap_of(n, m)
        if gap > STEP_GAP:
            continue
        a, b = _pt(g, n), _pt(g, m)
        if not _body_clear(tris, a, b, a[2]):
            continue
        info = {"from": a, "to": b, "dz": round(dz, 1), "gap": round(gap, 2), "both": dz <= STEP_UP,
                "seam": dz <= STEP_MIN}
        out.append((n, m, max(d, 1.0), C.KIND_WALK, [a, b], 0.85, info))
        out.append((m, n, max(d, 1.0), C.KIND_WALK, [b, a], 0.85, None))
    # (jumps: clear at body height over the way, nothing in between to land on, and worth it)
    kept = []
    # (the safe drops first: a big drop, a fall spell's, never takes a safe one's place along a ledge)
    for kind, n, m, d, dz in sorted(cands, key=lambda c: (c[4] > SAFE_DROP, c[3], c[4])):
        a, b = _pt(g, n), _pt(g, m)
        if any(math.dist(a[:2], k[0][:2]) < JUMP_SPACING and math.dist(b[:2], k[1][:2]) < JUMP_SPACING for k in kept):
            continue
        gap = gap_of(n, m)
        if kind == "down":
            if gap > JUMP_DOWN_GAP:
                continue
        elif not (JUMP_GAP[0] <= gap <= JUMP_GAP[1]):
            continue
        if not _body_clear(tris, a, b, a[2]):
            continue
        if tris.wet(b[0], b[1], b[2]) or tris.wet(a[0], a[1], a[2]):
            continue  # (into a pool or a canal: a swim, not a floor)
        if kind == "down":
            # (the fall: nothing under the way out before the floor landed on)
            fall = tris.first_below(b[0], b[1], a[2] + 0.4, dz + 2)
            if fall is None or abs(fall - (a[2] + 0.4 - b[2])) > 1.2:
                continue
        else:
            under = tris.first_below((a[0] + b[0]) / 2, (a[1] + b[1]) / 2, a[2] + 0.4, 50)
            if under is not None and under < UNDER_YD:
                continue
        # (worth it: the grid's own way round much longer. One that isn't is still a jump found, not a link)
        lim = d * 3 + JUMP_SAVE
        round_ = C.grid_dist(g, n, m, lim)
        conf = (0.85 if dz <= 8 else 0.8) if kind == "down" else 0.7  # (past SAFE_DROP: a fall spell's, CityGrid.MaxDrop)
        kept.append((a, b))
        info = {"kind": kind, "from": a, "to": b, "dz": round(dz, 1), "gap": round(gap, 2), "yd": round(d, 1),
                "round": None if math.isinf(round_) else round(round_, 1), "conf": conf, "saves": round_ > lim}
        ck = C.KIND_DROP if kind == "down" else C.KIND_JUMP
        out.append((n, m, max(d, 1.0) * C.ROAD_FACTOR + JUMP_COST, ck, [a, b], conf, info))
    if feats is not None:
        for a, b, cost, kind, pts, conf, info in out:
            if info is None:
                continue
            if kind == C.KIND_WALK:
                feats.steps.append({**info, "conf": conf})
            else:
                feats.jumps.append(info)
    return out


# --- stairs or a ramp: risers in the collision ------------------------------------------------------------------

RISER_STEP = 0.1  # yards: the collision's height looked at this often along a flight
RISER_DZ = 0.12  # yards up in RISER_STEP: steeper than a walkable slope (50 degrees): a riser's face
RISER_SHARE = 0.5  # stairs climb at least this share of their rise on risers (a ramp: none, a rough slope: a little)
RISERS_MIN = 2  # ... on this many risers at least (one is a ledge)
RISER_OFFSETS = (-0.6, 0.0, 0.6)  # yards beside the flight's line also looked along (the best line counts)


def stepped(tris, pts) -> tuple:
    """The collision's height profile up a flight's line (its points (x, y, z)), every RISER_STEP: (the share of the
    climb on risers, how many risers), the best of RISER_OFFSETS' lines; (0, 0) where nothing is under it."""
    best = (0.0, 0)
    if tris is None or len(pts) < 2:
        return best
    for off in RISER_OFFSETS:
        segs = []
        for a, b in zip(pts, pts[1:]):
            L = math.dist(a[:2], b[:2])
            if L < 0.01:
                continue
            nx, ny = -(b[1] - a[1]) / L, (b[0] - a[0]) / L
            n = max(1, int(L / RISER_STEP))
            for q in range(n):
                u = q / n
                x, y = a[0] + (b[0] - a[0]) * u + nx * off, a[1] + (b[1] - a[1]) * u + ny * off
                z = a[2] + (b[2] - a[2]) * u
                segs.append(((x, y, z + 2.5), (x, y, z - 3.0)))
        zs = [s_[0][2] - h * 5.5 for h, s_ in zip(tris.hits(segs), segs) if h is not None]
        if len(zs) < 10:
            continue
        dz = np.abs(np.diff(np.array(zs)))
        tot = float(dz.sum())
        if tot < 0.5:
            continue
        steep = dz >= RISER_DZ
        share = float(dz[steep].sum()) / tot
        risers = int(steep[0]) + int((steep[1:] & ~steep[:-1]).sum())
        best = max(best, (round(share, 2), risers))
    return best


def is_stairs(tris, pts) -> bool:
    """Stairs (risers: a stepped height profile), not a ramp or a slope (smooth): stepped()'s share and risers."""
    share, risers = stepped(tris, pts)
    return share >= RISER_SHARE and risers >= RISERS_MIN


# --- all of it ----------------------------------------------------------------------------------------------------

def detect(g, mesh, tris=None, lifts=(), links=True) -> Features:
    f = Features(g.city.name, g.cell)
    find_floors(g, f)
    find_stairs(g, f, tris)
    find_bridges(g, f, tris)
    find_lifts(mesh, f, lifts)
    if links:
        gap_links(g, mesh, tris, f)
    return f


def classify_link(feats: Features | None, a_pt, b_pt, kind: int, oneway: bool, yd: float, pts=None, tris=None) -> int:
    """A road link's kind by what it crosses: KIND_LIFT and KIND_DROP as they are; one way and down JUMP_MIN or more a
    drop (the roads' drops off ledges: "Jump down here"); a climb of 2 yd or more at a stairs' slope stairs; along a
    bridge found, KIND_BRIDGE; else as it was."""
    if kind in (C.KIND_LIFT, C.KIND_DROP, C.KIND_SWIM):
        return kind
    dz = b_pt[2] - a_pt[2]
    if oneway and dz <= -JUMP_MIN:  # (a road one way only, down: the roads' drops off ledges, jumped)
        return C.KIND_DROP
    if abs(dz) >= 2.0 and STAIR_SLOPE[0] <= abs(dz) / max(yd, 0.1) <= 2.5:
        # (stairs only with risers in the collision: a road up a ramp, or a stairs road laid over one, is a walk)
        line = pts if pts is not None else [a_pt, b_pt]
        if kind == C.KIND_STAIRS:  # (a stairs road's own link: its stairs, traced from the models' stair faces)
            return C.KIND_STAIRS
        if tris is not None and is_stairs(tris, line if line[-1][2] >= line[0][2] else list(reversed(line))):
            return C.KIND_STAIRS
        return C.KIND_WALK if kind == C.KIND_STAIRS else kind
    if feats is not None and abs(dz) < 1.5:
        mx, my, mz = (a_pt[0] + b_pt[0]) / 2, (a_pt[1] + b_pt[1]) / 2, (a_pt[2] + b_pt[2]) / 2
        for br in feats.bridges:
            if br["conf"] >= USE_CONF and on_line(br["pts"], mx, my, mz, br["width"] / 2 + 1.0):
                return C.KIND_BRIDGE
    return kind


def on_line(pts, x, y, z, half_w, dz=3.0) -> bool:
    for a, b in zip(pts, pts[1:] or pts):
        vx, vy = b[0] - a[0], b[1] - a[1]
        L2 = vx * vx + vy * vy
        t = 0 if L2 == 0 else max(0.0, min(1.0, ((x - a[0]) * vx + (y - a[1]) * vy) / L2))
        if math.hypot(x - a[0] - vx * t, y - a[1] - vy * t) <= half_w and abs(z - (a[2] + (b[2] - a[2]) * t)) <= dz:
            return True
    return False


# --- the city grid's bake (citygrid.build) ---------------------------------------------------------------------

def known_lifts(links, roads) -> list:
    """The city's lifts: its lift links' shafts (the grid's KIND_LIFT road links, from Data/Capitals.lua's lift roads:
    Thunder Bluff's; their lowest and highest points) and its level's lifts up (citygrid.LIFT_SOURCE:
    Undercity's to the Ruins; the top unknown), as find_lifts takes them: (name, foot, top or None, cost)."""
    out = []
    for a, b, cost, kind, pts in links:
        if kind != C.KIND_LIFT or len(pts) < 2:
            continue
        p, q = min(pts, key=lambda v: v[2]), max(pts, key=lambda v: v[2])
        if q[2] - p[2] >= LIFT_RISE:
            out.append(("lift link", tuple(p), tuple(q), round(cost)))
    for eid, src, _ow, smp, *own in roads:
        if src == C.LIFT_SOURCE:
            out.append((f"lift {-eid - 100000}", tuple(smp[0]), None, own[0] if own else None))
    # (one each: a lift's links up and down are one shaft)
    uniq = []
    for L in out:
        if all(math.dist(L[1][:2], o[1][:2]) > 4 for o in uniq):
            uniq.append(L)
    return [(f"{n} {i + 1}" if n == "lift link" else n, *rest) for i, (n, *rest) in enumerate(uniq)]


STAIRS_ROAD_YD = 2.0  # yards beside a flight's line (past its half width) a stairs road (source 6) runs along it ...
STAIRS_ROAD_Z = 3.0  # ... and this near its height


def stairs_roads(feats: Features, roads) -> int:
    """A flight the riser test calls a ramp that a stairs road of the city's roads (source 6: traced from the models'
    stair faces, or drawn) runs up is stairs after all: Ironforge's wide stone flights have collision ramps over their
    steps (Kooki3z 2026-11-22: "not seeing take stairs in ironforge", the First Aid trainer's balcony). Orgrimmar's gate
    incline has no stairs road and stays a ramp. How many were made stairs."""
    pts6 = [p for _eid, src, _ow, smp, *_o in roads if src == 6 for p in smp if p[2] is not None]
    made = 0
    for st in feats.stairs:
        if st["kind"] != "ramp" or st["width"] > STAIR_MAX_W or st["rise"] < STAIR_RISE:
            continue
        reach = st["width"] / 2 + STAIRS_ROAD_YD
        hits = sum(1 for x, y, z in pts6 if on_line(st["pts"], x, y, z, reach, STAIRS_ROAD_Z))
        if hits >= 2:
            st["kind"], st["by_road"] = "stairs", True
            made += 1
    return made


LIFT_EXIT_SEARCH = 3000  # mesh polys looked through from a lift's foot for its way out


LIFT_RIM_SHARE = 0.75  # the rim a lift's way off reaches: this share of the lifts' distance from their middle ...
LIFT_RIM_Z = 4.0  # ... at the lift's foot's height (yards up or down)
LIFT_EXIT_YD = 10.0  # yards over the mesh from a lift's end its way off runs at the least (out of the landing)


def _portal(mesh, p, q):
    """The middle of the edge polys p and q share (their common vertices), or None."""
    key = lambda v: (round(v[0], 1), round(v[1], 1), round(v[2], 1))  # noqa: E731
    a = {key(v): v for v in mesh.vs[p]}
    common = [v for v in mesh.vs[q] if key(v) in a]
    if len(common) < 2:
        return None
    return tuple(sum(v[k] for v in common[:2]) / 2 for k in range(3))


def lift_exits(g, mesh, roads) -> list:
    """Each level lift's way off at its foot (citygrid.LIFT_SOURCE: Undercity's): from the lift's city end over the
    mesh's polys, by the edges they share (through the landing's arch, never its walls), LIFT_EXIT_YD along at the least
    to a floor of the grid, as points (x, y, z). The addon starts (or ends) a walk at the lift there, not by a straight
    line to the nearest floor across the landing's wall (Kooki3z 2026-11-22: off the east lift, "Slight left now" into
    the wall)."""
    cents = [tuple(np.mean(vs, axis=0)) for vs in mesh.vs]
    out = []
    feet = [smp[0] for _eid, src, _ow, smp, *_o in roads if src == C.LIFT_SOURCE]
    # (the lifts stand round the city's middle: their way off runs in to the rim of the floor ringed round it, within
    # LIFT_RIM_SHARE of their distance from the middle (Undercity's Trade Quarter ring; Kooki3z 2026-11-22: "its really
    # just the path from the lift to the top floor circle path, once at the rim of the top floor routing is correct")
    mid = None
    if len(feet) >= 3:
        mx, my = sum(p[0] for p in feet) / len(feet), sum(p[1] for p in feet) / len(feet)
        mid = (mx, my, LIFT_RIM_SHARE * sum(math.hypot(p[0] - mx, p[1] - my) for p in feet) / len(feet))
    for _eid, src, _ow, smp, *_o in roads:
        if src != C.LIFT_SOURCE:
            continue
        x, y, z = smp[0]
        starts = [i for i, c in enumerate(cents) if math.hypot(c[0] - x, c[1] - y) <= 6 and abs(c[2] - z) <= 3]
        if not starts:
            continue
        s0 = min(starts, key=lambda i: math.hypot(cents[i][0] - x, cents[i][1] - y))
        dist, prev, h, end = {s0: 0.0}, {s0: None}, [(0.0, s0)], None
        k = 0
        while h and k < LIFT_EXIT_SEARCH:
            d, p = heapq.heappop(h)
            if d > dist[p]:
                continue
            k += 1
            c = cents[p]
            on_rim = mid is None or (math.hypot(c[0] - mid[0], c[1] - mid[1]) <= mid[2] and abs(c[2] - z) <= LIFT_RIM_Z)
            if d >= LIFT_EXIT_YD and on_rim and C.surface_at(g, c[0], c[1], c[2]) is not None:
                end = p
                break
            for q in mesh.nb[p]:
                nd = d + math.dist(cents[p], cents[q])
                if nd < dist.get(q, math.inf):
                    dist[q], prev[q] = nd, p
                    heapq.heappush(h, (nd, q))
        if end is None:
            continue
        chain = []
        while end is not None:
            chain.append(end)
            end = prev[end]
        chain.reverse()
        pts = [(x, y, z)]
        for p, q in zip(chain, chain[1:]):
            m = _portal(mesh, p, q)
            if m is not None:
                pts.append(tuple(round(float(v), 1) for v in m))
        pts.append(tuple(round(float(v), 1) for v in cents[chain[-1]]))
        out.append(pts)
    return out


TRACK_DROP_Z = 4.0  # yards: a drawn or recorded road's step down this far ...
TRACK_DROP_SLOPE = 2.0  # ... and steeper than this (yards down a yard along) is a drop (drawn_links)
TRACK_CHUNK = 6.0  # yards: a drawn or recorded road (source 2) becomes the grid's links this long along its whole length
TRACK_FACTOR = 0.7  # ... each costing this many a yard (cheaper than the grid's own ground: routes keep to them;
# CityGrid.TRACK_FACTOR for the player's own not yet in the data)


WALL_HEIGHTS = (1.2, 1.8)  # yards over the floor: a link crossing collision at both goes through a wall
CLIMB_MAX_SLOPE = 2.5  # yards up a yard along: a road link steeper than this (and STAIR_RISE up) climbs a wall
WALL_LEVEL_DZ = 1.5  # yards: only links this level are checked (a tent's floor is level; stairs are not)


def crosses_wall(tris, pts) -> bool:
    """Whether a link's points (x, y, z) pass through a wall at body height (WALL_HEIGHTS, all of them, on one stretch)."""
    if tris is None:
        return False
    for a, b in zip(pts, pts[1:]):
        if math.dist(a[:2], b[:2]) < 0.05:
            continue
        hits = tris.hits([((a[0], a[1], a[2] + h), (b[0], b[1], b[2] + h)) for h in WALL_HEIGHTS])
        if all(t is not None for t in hits):
            return True
    return False


def cut_wall_links(surf, links, mesh, tris, cell, log=print) -> int:
    """The grid's level links (neighbors on one poly, joined by a doorway's edge, or HOPS links apart) cut where the straight way between their points runs through a wall at body height
    (WALL_HEIGHTS). Thunder Bluff's tents, Kooki3z 2026-11-22: "should be colliding with the building's wall for
    routing"; the grid's walk went through the canvas by the doorway's polys. The cells either side of a wall the mesh
    has no edge at (one poly on both sides: a tent's canvas over the polys) returned, walled: CityGrid.Line draws no
    straight line through one (`walls` in the bake), so a route's corner can't cut through the canvas by the door."""
    if tris is None:
        return set()
    cut, walled = 0, set()
    for (i, j, k), row in links.items():
        s = surf[(i, j)][k]
        own = set(s[1])
        for d, kk in enumerate(row):
            if kk < 0:
                continue
            dx, dy = C.DIRS[d]
            t = surf[(i + dx, j + dy)][kk]
            a, b = (s[2], s[3], s[0]), (t[2], t[3], t[0])
            if abs(b[2] - a[2]) >= WALL_LEVEL_DZ:
                continue
            if own & t[1]:
                # (the same poly: a wall the mesh was built without, a tent's canvas over Thunder Bluff's polys; only
                # where the collision reaches body height there at all, the rays being dear)
                z0 = min(a[2], b[2]) + WALL_HEIGHTS[0]
                if not len(tris._cands(a[0], a[1], b[0], b[1], z0, max(a[2], b[2]) + WALL_HEIGHTS[-1])):
                    continue
            if crosses_wall(tris, [a, b]):
                row[d] = -1
                cut += 1
                if own & t[1]:
                    walled.add((i, j))
                    walled.add((i + dx, j + dy))
    log(f"  {cut} grid links through a wall cut, {len(walled)} cells walled over the mesh")
    return walled


def wall_segment(tris, ax, ay, bx, by, z):
    """Where a wall runs through the cell (ax, ay)-(bx, by) at body height over floor z: the two of its crossings of
    the cell's sides and diagonals farthest apart, as shares of the cell (fx0, fy0, fx1, fy1), or None (none found, or
    only one: the cell's walled whole)."""
    cx, cy = (ax + bx) / 2, (ay + by) / 2
    corners = [(ax, ay), (bx, ay), (bx, by), (ax, by)]
    rays = [(corners[k], corners[(k + 1) % 4]) for k in range(4)] + [(corners[0], corners[2]), (corners[1], corners[3])]
    rays += [(q, p) for p, q in rays]
    segs = [((p[0], p[1], z + h), (q[0], q[1], z + h)) for p, q in rays for h in WALL_HEIGHTS]
    ts = tris.hits(segs)
    pts = []
    nh = len(WALL_HEIGHTS)
    for r, (p, q) in enumerate(rays):
        hs = ts[r * nh:(r + 1) * nh]
        if any(t is None for t in hs):
            continue
        t = min(hs)
        pts.append((p[0] + (q[0] - p[0]) * t, p[1] + (q[1] - p[1]) * t))
    best, bd = None, WALL_SEG_MIN ** 2
    for i in range(len(pts)):
        for j in range(i + 1, len(pts)):
            d = (pts[i][0] - pts[j][0]) ** 2 + (pts[i][1] - pts[j][1]) ** 2
            if d > bd:
                best, bd = (pts[i], pts[j]), d
    if best is None:
        return None
    w, h = bx - ax, by - ay
    (x0, y0), (x1, y1) = best
    return ((x0 - ax) / w, (y0 - ay) / h, (x1 - ax) / w, (y1 - ay) / h)


def walled_cells(surf, tris, cell, x0, y0, cells=(), log=print) -> dict:
    """The cells a wall runs through at body height (any of the cell's sides or diagonals crossed at both WALL_HEIGHTS
    over one of its surfaces), and `cells` (cut_wall_links'), each with the wall's way through it (wall_segment) or
    None (walled whole): CityGrid.Line draws no straight line across one, so a route's straightened stretch never cuts
    a building's corner or a tent's canvas where the cells either side of it are still joined (Kooki3z 2026-11-23,
    Thunder Bluff's longhouses: "orange should be walls here not pathing through them"). By the wall's own way, not
    the whole cell: walling the cells whole bent the lines round every corner (Darnassus's spiral, Undercity's rings)."""
    out = {}
    if tris is None:
        return out
    h0, h1 = WALL_HEIGHTS[0], WALL_HEIGHTS[-1]
    want = set(cells)
    for (i, j), ss in surf.items():
        ax, ay = x0 + i * cell, y0 + j * cell
        bx, by = ax + cell, ay + cell
        segs = []
        for k, s in enumerate(ss):  # (each floor's own: another floor of the cell walks on under or over it)
            z = s[0]
            if not len(tris._cands(ax, ay, bx, by, z + h0, z + h1)):
                continue
            seg = wall_segment(tris, ax, ay, bx, by, z)
            if seg is not None:
                segs.append((k,) + seg)
        if (i, j) in want and not segs:
            out[(i, j)] = None
        elif segs:
            out[(i, j)] = segs
    log(f"  {len(out)} cells a wall runs through ({sum(1 for v in out.values() if v is None)} whole, "
        f"{sum(len(v) for v in out.values() if v)} floors' walls)")
    return out


WALL_SEG_MIN = 0.3  # yards: a wall's two crossings of a cell at least this far apart, else it's walled whole


def _through_walls(g, tris, other, tagged, log=print) -> list:
    """The road links `tagged` less those through a wall at body height (both WALL_HEIGHTS: collision a player can't
    pass), the steps on from the cells' own points included. Left out even where the grid has no other way: a piece
    reached only through a wall (the space inside a tent's canvas) is no way in. Thunder Bluff's tents, Kooki3z
    2026-11-22: "should be colliding with the building's wall for routing". `other`: unused, kept for the callers."""
    if tris is None:
        return tagged
    # (level pieces only: a climb's interpolated heights run into its own steps, Thunder Bluff's inn's stairs; each on
    # its own: Thunder Bluff's old road into the Spirit Rise bridge's tent climbs 1.6 yd in all, through the canvas on
    # a level piece)
    def through(L):
        (i, j, k), (i2, j2, k2) = L[0], L[1]
        sa, sb = g.surf[(i, j)][k], g.surf[(i2, j2)][k2]
        pts = [(sa[2], sa[3], sa[0])] + list(L[4]) + [(sb[2], sb[3], sb[0])]
        return any(abs(q[2] - p[2]) < WALL_LEVEL_DZ and crosses_wall(tris, [p, q]) for p, q in zip(pts, pts[1:]))

    bad = {i for i, L in enumerate(tagged) if L[3] not in (C.KIND_LIFT, C.KIND_DROP, C.KIND_STAIRS) and through(L)}
    if bad:
        log(f"  {g.city.name}: {len(bad)} road links through a wall left out")
    return [L for i, L in enumerate(tagged) if i not in bad]


BIG_DROP_ROUND = (3.0, 600.0)  # a road drop past SAFE_DROP is left out where the grid's way round is within this


def _drop_clear(tris, pts) -> bool:
    """Whether a drop's take-off is clear at body height over to its landing, nothing is between in the fall, and the
    landing isn't under liquid."""
    a, b = pts[0], pts[-1]
    dz = a[2] - b[2]
    if not (_body_clear(tris, a, b, a[2]) and not tris.wet(b[0], b[1], b[2])):
        return False
    fall = tris.first_below(b[0], b[1], a[2] + 0.4, dz + 2)
    return fall is not None and abs(fall - (a[2] + 0.4 - b[2])) <= 1.2


def _road_drops(g, tris, other, tagged, log=print) -> list:
    """The road links `tagged` less the roads' drops a player can't take as a jump: no clear take-off at body height
    over to the landing, something between in the fall, a landing under liquid (the checks found jumps pass); and a
    drop past SAFE_DROP where the grid has another way down (BIG_DROP_ROUND: at most this times its yards plus this). Kooki3z 2026-11-22 on
    Thunder Bluff's Spirit Rise: a 36 yd road drop to the Pools of Vision, "should be routing to the entrance underneath
    here"."""
    if tris is None:
        return tagged
    # (the drops past SAFE_DROP only: a safe one the roads have is a drop a player made (recorded or traced), its points
    # the road's, not a jump's straight take-off)
    drops = [i for i, L in enumerate(tagged) if L[3] == C.KIND_DROP and L[4][0][2] - L[4][-1][2] > SAFE_DROP]
    if not drops:
        return tagged
    keep_out = {i for i in drops if not _drop_clear(tris, tagged[i][4])}
    big = [i for i in drops if i not in keep_out and tagged[i][4][0][2] - tagged[i][4][-1][2] > SAFE_DROP]
    if big:
        g.road_out = defaultdict(list)
        for L in list(other) + [L for i, L in enumerate(tagged) if i not in keep_out and i not in big]:
            g.road_out[L[0]].append(L)
        for i in big:
            a, b, _c, _k, pts = tagged[i]
            yd = sum(math.dist(p[:2], q[:2]) for p, q in zip(pts, pts[1:]))
            lim = yd * BIG_DROP_ROUND[0] + BIG_DROP_ROUND[1]
            if C.grid_dist(g, a, b, lim) <= lim:
                keep_out.add(i)
    log(f"  {g.city.name}: {len(drops)} road drops, {len(keep_out)} left out (no clear jump, or a way down)")
    return [L for i, L in enumerate(tagged) if i not in keep_out]


def drawn_links(g, roads) -> list:
    """The city's drawn and recorded roads (source 2: truth, Kooki3z's walks) as the grid's links along their whole
    length, not only across its gaps: every TRACK_CHUNK yards between two of its points on the grid's floors (at the
    road's own heights), both ways unless the road is one way. A step down steeper than a walk (TRACK_DROP_SLOPE, at
    least TRACK_DROP_Z: the player jumped off a ledge) is a drop of its own, down only (Orgrimmar's ledge by the Hall of
    Legends, 26 yd: walked up it both ways before)."""
    out = []
    for _eid, src, oneway, smp, *_own in roads:
        if src != 2 or len(smp) < 2 or any(p[2] is None for p in smp):
            continue
        on = [C.surface_at(g, x, y, z) for x, y, z in smp]
        # (the walk in runs between its drops)
        runs, r0 = [], 0
        for q in range(1, len(smp)):
            dz = smp[q][2] - smp[q - 1][2]
            if abs(dz) >= TRACK_DROP_Z and abs(dz) > TRACK_DROP_SLOPE * math.dist(smp[q - 1][:2], smp[q][:2]):
                runs.append((r0, q - 1))
                r0 = q
                hi, lo = (q - 1, q) if dz < 0 else (q, q - 1)
                if on[hi] is not None and on[lo] is not None and on[hi] != on[lo] and (dz < 0 or not oneway):
                    pts = [tuple(smp[hi]), tuple(smp[lo])]
                    out.append((on[hi], on[lo], max(1.0, math.dist(pts[0][:2], pts[1][:2])) * TRACK_FACTOR, C.KIND_DROP, pts))
        runs.append((r0, len(smp) - 1))
        for q0, q1 in runs:
            a, along = None, 0.0
            for q in range(q0, q1 + 1):
                if q > q0:
                    along += math.dist(smp[q - 1][:2], smp[q][:2])
                node = on[q]
                if node is None:
                    continue
                if a is not None and (along >= TRACK_CHUNK or q == q1) and node != on[a]:
                    pts = _simplify([tuple(p) for p in smp[a:q + 1]], C.ROAD_LINK_PTS_YD)
                    cost = max(1.0, along) * TRACK_FACTOR
                    out.append((on[a], node, cost, C.KIND_WALK, pts))
                    if not oneway:
                        out.append((node, on[a], cost, C.KIND_WALK, list(reversed(pts))))
                if a is None or along >= TRACK_CHUNK:
                    a, along = q, 0.0
    return out


def apply(g, mesh, roads, reach, log=print) -> Features:
    """citygrid.build's step: the steps and jumps the mesh lacks (gap_links, at USE_CONF or more) become the grid's own
    links, then the city's road links are made again over them (only where the grid still has no way: fewer old-road
    links), each tagged with what it crosses (classify_link: stairs, a bridge, a drop, a lift); the floors, stairs,
    bridges and lifts found kept on the grid (g.features) for the bake's `feat` and the debug output."""
    tris = Tris.load(g.city.mesh)
    before = len(g.road) - len(reach)
    gl = gap_links(g, mesh, tris)
    use = [(a, b, cost, kind, pts) for a, b, cost, kind, pts, conf, info in gl
           if conf >= USE_CONF and kind in (C.KIND_DROP, C.KIND_JUMP) and info["saves"] and g.city.found_jumps]
    steps = {(a, b): (cost, pts) for a, b, cost, kind, pts, conf, _i in gl if kind == C.KIND_WALK and conf >= USE_CONF}
    g.road = use + list(reach)
    g.road_out = defaultdict(list)
    for L in g.road:
        g.road_out[L[0]].append(L)
    rl = C.road_links(g, roads, log, keep=True)
    feats = detect(g, mesh, tris, known_lifts(rl, roads), links=False)
    stairs_roads(feats, roads)
    for a, b, cost, kind, pts, conf, info in gl:
        if info is not None:
            used = conf >= USE_CONF and (kind == C.KIND_WALK or (info["saves"] and g.city.found_jumps))
            (feats.steps if kind == C.KIND_WALK else feats.jumps).append({**info, "conf": conf, "used": used})
    pairs = {(a, b) for a, b, *_ in rl}
    tagged, replaced = [], 0
    for a, b, cost, kind, pts in rl:
        k = classify_link(feats, pts[0], pts[-1], kind, (b, a) not in pairs, cost / C.ROAD_FACTOR, pts, tris)
        st = steps.get((a, b))
        if st is not None and kind not in (C.KIND_LIFT, C.KIND_DROP):
            # (a road's stretch over a step or seam the mesh lacks, confirmed: straight from where the road leaves the
            # grid to where it comes back, the road's points between dropped)
            # (its cost as the road's: the routes' choices stay, and the line is never longer)
            pts = [pts[0], pts[-1]]
            replaced += 1
        tagged.append((a, b, cost, k, pts))
    # (a drop down a road the old roads had, past the drop a player always survives: not the grid's way. Kooki3z
    # 2026-11-22 on Thunder Bluff's Spirit Rise, "Jump down here", 37 yd down to the Pools of Vision, "should be routing
    # to the entrance underneath here")
    # (up to BIG_DROP kept, for a fall spell: CityGrid.MaxDrop takes those past SAFE_DROP only while one is ready)
    too_far = [L for L in tagged if L[3] == C.KIND_DROP and L[4][0][2] - L[4][-1][2] > BIG_DROP]
    tagged = [L for L in tagged if not (L[3] == C.KIND_DROP and L[4][0][2] - L[4][-1][2] > BIG_DROP)]
    if too_far:
        log(f"  {g.city.name}: {len(too_far)} road drops past {BIG_DROP:g} yd left out")
    # (a road link through a wall at body height where the grid has another way round, by a door: left out. Thunder
    # Bluff's tents at its rope bridges' ends, Kooki3z 2026-11-22: "should be colliding with the building's wall for
    # routing"; the old roads went straight through their canvas)
    # (a road link climbing a wall: steeper than any walk, not a lift's or a drop's; Thunder Bluff's old road up onto
    # the Spirit Rise bridge tent's roof, 12 yd in a yard)
    steep = [L for L in tagged if L[3] not in (C.KIND_LIFT, C.KIND_DROP)
             and L[4][-1][2] - L[4][0][2] > CLIMB_MAX_SLOPE * max(1.0, sum(math.dist(p[:2], q[:2]) for p, q in zip(L[4], L[4][1:])))
             and L[4][-1][2] - L[4][0][2] >= STAIR_RISE]
    if steep:
        tagged = [L for L in tagged if not any(L is S for S in steep)]
        log(f"  {g.city.name}: {len(steep)} road links climbing a wall left out")
    # (and one down so steep a drop, not a walk: Orgrimmar's old road off the ledge by the Hall of Legends, 26 yd in 3)
    def plunge(L):
        dz = L[4][0][2] - L[4][-1][2]
        yd = sum(math.dist(p[:2], q[:2]) for p, q in zip(L[4], L[4][1:]))
        return L[3] not in (C.KIND_LIFT, C.KIND_DROP) and dz >= TRACK_DROP_Z and dz > CLIMB_MAX_SLOPE * max(1.0, yd)
    n_pl = sum(plunge(L) for L in tagged)
    if n_pl:
        tagged = [(a, b, cost, C.KIND_DROP, pts) if plunge((a, b, cost, k, pts)) else (a, b, cost, k, pts)
                  for a, b, cost, k, pts in tagged]
        log(f"  {g.city.name}: {n_pl} road links down a wall made drops")
    drawn = drawn_links(g, roads)
    if drawn:
        log(f"  {g.city.name}: {len(drawn)} links along its drawn and recorded roads")
    # (the drawn and recorded roads' links too: a recorded walk's point beside a tent's canvas, the step on from it
    # through it; a recorded walk's heights jumping a turn of Darnassus's spiral, a "drop" through the turn under it)
    nd = len(drawn)
    both = _road_drops(g, tris, use + list(reach), tagged + drawn, log)
    both = _through_walls(g, tris, use + list(reach), both, log)
    drawn_set = {id(L) for L in drawn}
    tagged, drawn = [L for L in both if id(L) not in drawn_set], [L for L in both if id(L) in drawn_set]
    if len(drawn) < nd:
        log(f"  {g.city.name}: {nd - len(drawn)} of them left out (through a wall, or a drop not taken)")
    g.road = use + list(reach) + tagged + drawn
    g.road_out = defaultdict(list)
    for L in g.road:
        g.road_out[L[0]].append(L)
    g.features = feats
    g.lift_exits = lift_exits(g, mesh, roads)
    kinds = defaultdict(int)
    for L in tagged:
        kinds[L[3]] += 1
    names = {C.KIND_WALK: "walk", C.KIND_STAIRS: "stairs", C.KIND_DROP: "drop", C.KIND_LIFT: "lift",
             C.KIND_BRIDGE: "bridge", C.KIND_JUMP: "jump", C.KIND_SWIM: "swim"}
    used = defaultdict(int)
    for L in use:
        used[L[3]] += 1
    log(f"  {g.city.name}: found {feats.counts()}")
    log(f"  {g.city.name}: {len(use)} links found ({', '.join(f'{names[k]} {v}' for k, v in sorted(used.items()))}); "
        f"road links {before} -> {len(tagged)}, {replaced} of them a step found ({', '.join(f'{names[k]} {v}' for k, v in sorted(kinds.items()))})")
    write_debug(g, feats)
    return feats


# --- what the addon reads: the features' lines ---------------------------------------------------------------------

FEAT_STAIRS, FEAT_BRIDGE = 1, 2


def feature_lines(feats: Features, road) -> list:
    """[(kind, half width, [(x, y, z)])]: the confident stairs (bottom to top) and bridges for CityGrid's StairAt and
    BridgeAt (Turns' "Take the stairs up", "Cross the bridge"; the map's stairs icon), and the grid's stairs links (road
    or step: their points)."""
    out = []
    for s in feats.stairs:
        if s["conf"] >= USE_CONF and s["kind"] in ("stairs", "spiral"):  # (not a ramp: no "Take the stairs" there)
            out.append((FEAT_STAIRS, max(1.5, min(s["width"], GRAND_STAIRS_W) / 2), s["pts"]))
    for b in feats.bridges:
        if b["conf"] >= USE_CONF:
            out.append((FEAT_BRIDGE, max(1.5, b["width"] / 2), b["pts"]))
    seen = set()
    for a, b, _cost, kind, pts in road:
        if kind == C.KIND_STAIRS and len(pts) >= 2 and abs(pts[-1][2] - pts[0][2]) >= 2.0:
            key = tuple(sorted((a, b)))
            if key in seen:
                continue
            seen.add(key)
            p = list(pts) if pts[-1][2] >= pts[0][2] else list(reversed(pts))
            out.append((FEAT_STAIRS, 1.5, [tuple(round(v, 1) for v in q) for q in p]))
    return out


# --- debug output for Route Studio ------------------------------------------------------------------------------

COLORS = {"stairs": "#f2c230", "bridge": "#3a7bd5", "lift": "#9b59b6", "drop": "#e03c31", "jump": "#e03c31"}


def debug_json(g, feats: Features) -> dict:
    """The features in a shape Route Studio draws: floors as cell squares colored by floor (height), the rest as lines
    and points in their colors."""
    cells = []
    for n, fid in feats.floor_of.items():
        x, y, z = _pt(g, n)
        cells.append([round(g.x0 + (n[0] + 0.5) * g.cell, 1), round(g.y0 + (n[1] + 0.5) * g.cell, 1), round(z, 1), fid])
    return {
        "city": feats.city, "cont": g.city.cont, "level": g.city.level, "cell": g.cell, "colors": COLORS,
        "counts": feats.counts(),
        "floors": [{k: v for k, v in f.items()} for f in feats.floors],
        "floor_cells": cells,
        "stairs": feats.stairs,
        "bridges": [{k: v for k, v in b.items() if k != "cells"} for b in feats.bridges],
        "lifts": feats.lifts,
        "jumps": feats.jumps,
        "steps": feats.steps,
    }


def write_debug(g, feats: Features) -> Path:
    d = data_dir() / "debug" / "navfeatures"
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"{g.city.mesh}.json"
    p.write_text(json.dumps(debug_json(g, feats), separators=(",", ":"),
                            default=lambda o: o.item() if hasattr(o, "item") else str(o)), encoding="utf-8")
    return p


# --- a building's grid (the interiors trial) ----------------------------------------------------------------------

def grid_from_mesh(name: str, tiles: dict, cont: int, cell: float = 2.0):
    """A walk grid of a whole mesh (a building's), no pruning: citygrid's surfaces and links."""
    mesh = C.Mesh(tiles, cont)
    xs = [v[0] for vs in mesh.vs for v in vs]
    ys = [v[1] for vs in mesh.vs for v in vs]
    x0, y0 = math.floor(min(xs) / cell) * cell, math.floor(min(ys) / cell) * cell
    w, h = int((max(xs) - x0) // cell) + 1, int((max(ys) - y0) // cell) + 1
    samples = C.rasterize(mesh, x0, y0, w, h, cell)
    surf = {c: C.merge_cell(s, mesh) for c, s in samples.items()}
    links = C.build_links(surf, mesh, cell)
    city = C.City(name, name.lower().replace(" ", "_"), cont, cell=cell)
    g = C.Grid(city, x0, y0, w, h, cell, surf, links, [])
    g.road_out = defaultdict(list)
    return g, mesh


# --- the interiors trial (buildings outside the capitals) -------------------------------------------------------

INTERIORS = [  # (name, continent, x, y: a spot inside it; Data/Indoors.lua's building there is compared)
    ("Brill: the inn", 0, 2267.0, 241.0),
    ("Goldshire: the inn", 0, -9468.0, 17.0),
    ("Darkshire: the town hall", 0, -10568.0, -1122.0),
    ("Sentinel Hill: the tower", 0, -10503.0, 1032.0),
]
INTERIORS_CELL = 1.0  # yards: a building's grid (its stairs are 2-3 yd wide)


def _indoors_entry(cont, x, y):
    """Data/Indoors.lua's building nearest (x, y): (name, x, y, r, floors)."""
    import re
    from .paths import ADDON_DIR
    txt = (ADDON_DIR / "Data" / "Indoors.lua").read_text(encoding="utf-8")
    best = None
    sect = None
    for line in txt.splitlines():
        m = re.match(r"ns\.Indoors\[(\d+)\] = \{", line)
        if m:
            sect = int(m.group(1))
            continue
        m = re.match(r'\s*\{ "([^"]+)", x = (-?[\d.]+), y = (-?[\d.]+), r = ([\d.]+),.*floors = \{ ([^}]*) \}', line)
        if m and sect == cont:
            bx, by = float(m.group(2)), float(m.group(3))
            d = math.hypot(bx - x, by - y)
            if best is None or d < best[0]:
                best = (d, m.group(1), bx, by, float(m.group(4)), [float(v) for v in m.group(5).split(",") if v.strip()])
    return best[1:] if best else None


def _indoors_stairs(ns, cont, x, y, r):
    """The stairs roads (source 6) of the addon's roads within r of (x, y): [(x1, y1, z1, x2, y2, z2)]."""
    R = ns.Router
    R.NearestEdges(cont, x, y)
    g = R.DebugGraph(cont)
    hz = g.nz
    out = []
    if hz is None:
        return out
    for eid in g.e.keys():
        e = g.e[eid]
        if int(e[4]) != 6:
            continue
        ax, ay = g.n[2 * e[1] - 1], g.n[2 * e[1]]
        bx, by = g.n[2 * e[2] - 1], g.n[2 * e[2]]
        if math.hypot(ax - x, ay - y) <= r and math.hypot(bx - x, by - y) <= r:
            out.append((ax, ay, hz[e[1]], bx, by, hz[e[2]]))
    return out


def interiors(cd, log=print) -> list:
    """The detector on the INTERIORS buildings' own meshes (built as the capitals' are: the model's faces, the doodads and
    the land round it), against Data/Indoors.lua's floors and stairs there. data/debug/navfeatures/interiors.json."""
    from . import indoors
    from . import recastmesh as RM
    from .buildings import buildings
    from .gameharness import start

    _lua, ns = start()
    rows = []
    for name, cont, x, y in INTERIORS:
        ps = [p for p in buildings(cd, cont) if p.bounds[0] <= x <= p.bounds[2] and p.bounds[1] <= y <= p.bounds[3]]
        if not ps:
            log(f"  {name}: no building there")
            continue
        p = min(ps, key=lambda p: (p.bounds[2] - p.bounds[0]) * (p.bounds[3] - p.bounds[1]))
        fl, wl = indoors.building_faces(cd, p)
        tri = [[(xy[k][0], xy[k][1], zs[k]) for k in range(3)] for xy, zs, *_r in fl]
        tri += [[(xy[k][0], xy[k][1], zs[k]) for k in range(3)] for _zr, xy, zs in wl]
        T, _box = RM._with_surroundings(cd, cont, np.array(tri, float))
        tiles = RM.run_recast(T, log=lambda *a: None)
        g, mesh = grid_from_mesh(name, tiles, cont, INTERIORS_CELL)
        tr = Tris(T)
        feats = detect(g, mesh, tr)
        x0, y0, x1, y1 = p.bounds

        def inside(px, py, pad=0.0):
            return x0 - pad <= px <= x1 + pad and y0 - pad <= py <= y1 + pad
        # (the building's own: floors with most of their cells inside it, not the land round it)
        own = []
        for f in feats.floors:
            cells = [n for n, fid in feats.floor_of.items() if fid == f["id"]]
            ins = sum(inside(*_pt(g, n)[:2]) for n in cells)
            if ins >= 0.6 * len(cells) and f["kind"] == "floor":
                own.append(f)
        heights = sorted({f["z"] for f in own})
        levels = []
        for z in heights:  # (floors within 2.5 yd of each other: one level, as Indoors' floors_of)
            if levels and z - levels[-1][-1] <= 2.5:
                levels[-1].append(z)
            else:
                levels.append([z])
        found_levels = [round(float(np.median(lv)), 1) for lv in levels]
        st = [s for s in feats.stairs if s["conf"] >= USE_CONF and inside(*s["pts"][0][:2], 2) and inside(*s["pts"][-1][:2], 2)]
        ent = _indoors_entry(cont, (x0 + x1) / 2, (y0 + y1) / 2)
        old_stairs = _indoors_stairs(ns, cont, ent[1], ent[2], ent[3]) if ent else []
        old_floors = ent[4] if ent else []
        agree_f = [z for z in old_floors if any(abs(z - f) <= 2.0 for f in found_levels)]
        # (a stairs road matched by a flight found: its ends within 4 yd across and 3 yd in height of the flight's)
        matched = 0
        for s in old_stairs:
            a, b = s[:3], s[3:]
            for f in st:
                p0, p1 = f["pts"][0], f["pts"][-1]
                for u, v in ((a, b), (b, a)):
                    if (math.dist(u[:2], p0[:2]) <= 4 and abs(u[2] - p0[2]) <= 3) or \
                       (math.dist(v[:2], p1[:2]) <= 4 and abs(v[2] - p1[2]) <= 3) or \
                       on_line(f["pts"], (u[0] + v[0]) / 2, (u[1] + v[1]) / 2, (u[2] + v[2]) / 2, f["width"] / 2 + 2):
                        matched += 1
                        break
                else:
                    continue
                break
        row = {"building": name, "model": ent[0] if ent else None, "uid": p.uid, "bounds": [round(v, 1) for v in p.bounds],
               "floors_found": found_levels, "floors_indoors": old_floors, "floors_agree": agree_f,
               "stairs_found": [{k: v for k, v in s.items() if k != "pts"} | {"from": s["pts"][0], "to": s["pts"][-1]}
                                for s in st],
               "stairs_roads_indoors": len(old_stairs), "stairs_roads_matched": matched,
               "drops_found": sum(j["kind"] == "down" for j in feats.jumps if inside(*j["from"][:2]))}
        rows.append(row)
        log(f"  {name}: floors found {found_levels} (Indoors.lua {old_floors}: {len(agree_f)} agree); stairs found "
            f"{len(st)} (rises {[s['rise'] for s in st]}); Indoors.lua's stairs roads {len(old_stairs)}, {matched} on a "
            f"flight found; drops {row['drops_found']}")
        g.city.mesh = "interiors_" + name.split(":")[0].lower().replace(" ", "_")
        write_debug(g, feats)
    d = data_dir() / "debug" / "navfeatures"
    d.mkdir(parents=True, exist_ok=True)
    (d / "interiors.json").write_text(json.dumps(rows, indent=1, default=lambda o: o.item() if hasattr(o, "item") else str(o)),
                                  encoding="utf-8")
    return rows
