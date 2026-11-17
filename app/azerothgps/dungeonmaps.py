"""Dungeons' world maps from another WoW version, where its dungeon is laid out as WoW Forever's
(Data/DungeonMaps.lua, `agps dungeon-maps`; issue #4).

WoW Forever's client has no map of its own for a dungeon (no uiMap: its map rules are Classic Era's), but
the retail client's tables do (UiMap Type 4, UiMapAssignment, UiMapXMapArt, UiMapArt, UiMapArtTile), and
their art's textures are in WoW Forever's own client too, byte for byte: the addon draws them by
FileDataID at runtime, as it draws the zones' maps; nothing of the game's is shipped.

A layout matching by name or map ID isn't enough (the Cataclysm and Pandaria revamps kept both). Each
floor of each dungeon is checked against WoW Forever's own client (`verify_floor`):
- every model over the floor's bounds is placed where WoW Forever places one (`POS_YD`, `YAW_DEG`; one
  added, moved or taken out: skipped);
- the floor's rooms (the WMO groups the source's UiMapAssignment ties to it, matched to WoW Forever's by id,
  else by index where WoW Forever renumbered a model's groups, else by their boxes; a floor with no groups:
  every model over its bounds) cover the same ground seen from above, what a map of them draws
  (`footprint_match`, 1-yard cells, `FOOTPRINT_MATCH`): WoW Forever re-meshed some models (the Sunken
  Temple, Blackrock Depths, the Scarlet Monastery), so their vertices (`vertices_matched`, evidence) differ
  where their rooms don't;
- on a map with terrain, the ground over the floor's bounds is the same (`TERRAIN_YD`, `TERRAIN_SHARE`);
- the floor's groups lie inside its bounds (the two clients' coordinates agree: `ALIGN_SHARE`);
- every art tile is in WoW Forever's client with the same content (no texture to ship, and the same picture).
A floor that fails any is skipped with its reason; a dungeon with no floor accepted keeps its map as it was.
The inventory (`inventory`: every dungeon and floor, accepted or skipped and why, the source and the evidence)
goes to app/azerothgps/data/dungeon_maps.json and docs/dungeon-maps.md.
"""

from __future__ import annotations

import json
import math
import struct
import time
from collections import defaultdict
from pathlib import Path

import numpy as np

from . import instances as INS
from . import interiors as I
from .extract import adt
from .extract.spike import ClientData
from .paths import REPO

SOURCE_PRODUCT = "wow"  # the retail client's tables (read from its local install, as WoW Forever's)
SOURCE_NAME = "World of Warcraft (retail)"
SOURCE_URL = "https://wago.tools/db2/UiMap?build={build}"  # the same tables online, for that build
INVENTORY = Path(__file__).parent / "data" / "dungeon_maps.json"
DOC = REPO / "docs" / "dungeon-maps.md"
INCLUDE_RAIDS = False  # issue #4: dungeons only (the checks work for raids as they are)

POS_YD = 0.5  # a model placed this near in both clients is the same placement
YAW_DEG = 0.5
BOX_YD = 0.5  # a model's and its groups' boxes, this near
VERT_YD = 0.1  # a vertex this near one in the other client's group is the same (evidence only)
FOOTPRINT_YD = 1.0  # the floor's footprint's cells
FOOTPRINT_MATCH = 0.98  # the share of the two footprints alike (within a cell)
TERRAIN_STEP = 4.0  # yards between the ground's samples over a floor
TERRAIN_YD = 1.0  # the ground's height this near in both clients
TERRAIN_SHARE = 0.99  # ... at this share of the samples (and the same ones with ground)
ALIGN_SHARE = 0.8  # the share of a floor's groups' boxes (by area) inside its bounds: the two clients' coordinates
# agree (wrong, the rooms land off the map wholesale; a map's art may crop a wing's edges: the Armory's 85%)
FLOOR_TYPES = (4, 6)  # UiMap types: a dungeon's floor, a micro map (Zul'Farrak's, out in the open)
FAR_REGION = 10000.0  # a source assignment with bounds this wide isn't a floor's (the Deadmines' second has one)


# --- the models ------------------------------------------------------------------------


class Models:
    """A map's placed models (its WDT's global WMO, else its ADTs' WMOs) in one client: placements, each
    model's groups (MOGP ids, boxes) and, read when asked, a group's vertices."""

    def __init__(self, cd: ClientData, map_id: int):
        self.cd = cd
        self.map_id = map_id
        pl = INS.wdt_placements(cd, map_id)
        self.terrain = not pl
        if not pl:
            pl = I.placements(cd, map_id)
        self.placements = pl
        self._wmo: dict = {}
        self._verts: dict = {}

    def wmo(self, fid: int) -> dict | None:
        if fid not in self._wmo:
            w = I.read_wmo(self.cd, fid)
            info = None
            if w is not None:
                gids = []
                for gi in range(w.n_groups):
                    gid = None
                    if gi < len(w.group_files):
                        try:
                            data = self.cd.casc.read(w.group_files[gi])
                            for magic, a, _b in adt.iter_chunks(data):
                                if magic == "MOGP":
                                    gid = struct.unpack_from("<I", data, a + I.MOGP_GROUP_ID)[0]
                                    break
                        except Exception:
                            pass
                    gids.append(gid)
                info = {"fid": fid, "n": w.n_groups, "bbox": tuple(w.bbox), "boxes": [tuple(g[1]) for g in w.groups],
                        "flags": [g[0] for g in w.groups], "gids": gids, "files": tuple(w.group_files)}
            self._wmo[fid] = info
        return self._wmo[fid]

    def mesh(self, fid: int, gi: int) -> tuple[np.ndarray, np.ndarray]:
        """A group's vertices (n x 3, the model's frame) and triangles (m x 3 indices)."""
        key = (fid, gi)
        if key not in self._verts:
            w = self.wmo(fid)
            verts, tris = np.zeros((0, 3), np.float32), np.zeros((0, 3), np.int64)
            if w and gi < len(w["files"]):
                data = self.cd.casc.read(w["files"][gi])
                for magic, a, b in adt.iter_chunks(data):
                    if magic == "MOGP":
                        sub = {m: (x, y) for m, x, y in adt.iter_chunks(data, a + 68, b)}
                        if "MOVT" in sub:
                            va, vb = sub["MOVT"]
                            verts = np.frombuffer(data[va:vb], np.float32).reshape(-1, 3).copy()
                        if "MOVI" in sub:
                            ia, ib = sub["MOVI"]
                            idx = np.frombuffer(data[ia:ib], np.uint16).astype(np.int64)
                            tris = idx[: len(idx) // 3 * 3].reshape(-1, 3)
                        break
            self._verts[key] = (verts, tris)
        return self._verts[key]

    def verts(self, fid: int, gi: int) -> np.ndarray:
        return self.mesh(fid, gi)[0]


def to_world(p, pts: np.ndarray) -> np.ndarray:
    """A placement's local points (n x 3) in the world (yaw only, as world_box)."""
    t = math.radians(p.yaw + 180.0)
    c, s = math.cos(t), math.sin(t)
    out = np.empty((len(pts), 3))
    out[:, 0] = p.x + pts[:, 0] * c - pts[:, 1] * s
    out[:, 1] = p.y + pts[:, 0] * s + pts[:, 1] * c
    out[:, 2] = p.z + pts[:, 2]
    return out


def footprint(models: Models, groups: list, region) -> np.ndarray:
    """The ground the groups' faces cover seen from above, FOOTPRINT_YD cells over `region` (bool rows by X,
    columns by Y): what a map of them draws."""
    from skimage.draw import polygon

    x0, y0 = region[0], region[1]
    nx = max(1, int(math.ceil((region[2] - x0) / FOOTPRINT_YD)))
    ny = max(1, int(math.ceil((region[3] - y0) / FOOTPRINT_YD)))
    grid = np.zeros((nx, ny), bool)
    for p, gi in groups:
        verts, tris = models.mesh(p.wmo, gi)
        if not len(tris) or not len(verts):
            continue
        tris = tris[(tris < len(verts)).all(1)]
        w = to_world(p, verts)
        fx, fy = (w[:, 0] - x0) / FOOTPRINT_YD, (w[:, 1] - y0) / FOOTPRINT_YD
        for t in tris:
            rr, cc = polygon(fx[t], fy[t], grid.shape)
            grid[rr, cc] = True
        # (thin faces seen edge-on, walls: their corners)
        ix, iy = fx.astype(int), fy.astype(int)
        ok = (ix >= 0) & (ix < nx) & (iy >= 0) & (iy < ny)
        grid[ix[ok], iy[ok]] = True
    return grid


def footprint_match(a: np.ndarray, b: np.ndarray) -> float:
    """How alike two footprints are (intersection over union, each dilated a cell: half-a-yard edges)."""
    from scipy.ndimage import binary_dilation

    if not a.any() and not b.any():
        return 1.0
    da, db = binary_dilation(a), binary_dilation(b)
    inter = (a & db).sum() + (b & da).sum()
    return float(inter / (a.sum() + b.sum()))


def world_box(p, box) -> tuple:
    """A model's local box (6 values) in the world: (minX, minY, maxX, maxY, minZ, maxZ) (yaw only, as
    interiors.py places its art: t = yaw + 180 degrees)."""
    t = math.radians(p.yaw + 180.0)
    c, s = math.cos(t), math.sin(t)
    xs, ys = [], []
    for lx in (box[0], box[3]):
        for ly in (box[1], box[4]):
            xs.append(p.x + lx * c - ly * s)
            ys.append(p.y + lx * s + ly * c)
    return min(xs), min(ys), max(xs), max(ys), p.z + box[2], p.z + box[5]


def _overlaps(b, region) -> bool:
    return b[0] < region[2] and b[2] > region[0] and b[1] < region[3] and b[3] > region[1]


def _near(a, b, tol) -> bool:
    return len(a) == len(b) and all(abs(x - y) <= tol for x, y in zip(a, b))


def _yaw_near(a: float, b: float) -> bool:
    d = (a - b) % 360.0
    return min(d, 360.0 - d) <= YAW_DEG


def same_model(wa: dict, wb: dict) -> str | None:
    """Why two models' groups differ (count or boxes), or None when they're alike."""
    if wa is None or wb is None:
        return "a model can't be read"
    if wa["n"] != wb["n"]:
        return f"{wa['n']} groups against {wb['n']}"
    if not _near(wa["bbox"], wb["bbox"], BOX_YD):
        return "its box differs"
    for gi, (x, y) in enumerate(zip(wa["boxes"], wb["boxes"])):
        if not _near(x, y, BOX_YD):
            return f"group {gi}'s box differs"
    return None


def pair_placements(fv: Models, src: Models, region) -> tuple[list, list, list]:
    """The two clients' placements over `region` (minX, minY, maxX, maxY) paired by spot and turn (whether
    their models are alike is the footprint's to say): (pairs [(fv placement, src placement)], WoW Forever's
    unpaired, the source's unpaired)."""
    a = [p for p in fv.placements if _overlaps(p.bounds, region)]
    b = [p for p in src.placements if _overlaps(p.bounds, region)]
    pairs, left = [], list(b)
    unpaired = []
    for p in a:
        hit = None
        for q in left:
            if (abs(p.x - q.x) <= POS_YD and abs(p.y - q.y) <= POS_YD and abs(p.z - q.z) <= POS_YD
                    and _yaw_near(p.yaw, q.yaw)):
                hit = q
                break
        if hit is None:
            unpaired.append(p)
        else:
            pairs.append((p, hit))
            left.remove(hit)
    return pairs, unpaired, left


def same_vertices(va: np.ndarray, vb: np.ndarray) -> float:
    """The share of each group's vertices with one within VERT_YD in the other (the smaller of the two ways);
    1.0 for two empty groups."""
    if len(va) == 0 and len(vb) == 0:
        return 1.0
    if len(va) == 0 or len(vb) == 0:
        return 0.0
    from scipy.spatial import cKDTree

    da, _ = cKDTree(vb).query(va, distance_upper_bound=VERT_YD)
    db, _ = cKDTree(va).query(vb, distance_upper_bound=VERT_YD)
    return float(min(np.isfinite(da).mean(), np.isfinite(db).mean()))


# --- the source's floors ----------------------------------------------------------------


def source_floors(src: ClientData, types=None) -> dict:
    """The source's dungeon maps by MapID: {map id: [floor]}, each floor a dict (ui, name, index, bounds
    (minX, minY, maxX, maxY), gids (the WMO groups the source ties to it), art (w, h, tiles [(fid, x, y, w,
    h, texW, texH)]), regions (the assignments' bounds, to check they agree)}. Only uiMaps of `types`
    (FLOOR_TYPES; interiormaps.py's micro maps too) with art."""
    types = types or FLOOR_TYPES
    maps = {m["ID"]: m for m in src.table("UiMap")}
    members = {r["UiMapID"]: r for r in src.table("UiMapGroupMember")}
    xart = defaultdict(list)
    for r in src.table("UiMapXMapArt"):
        xart[r["UiMapID"]].append(r["UiMapArtID"])
    arts = {r["ID"]: r for r in src.table("UiMapArt")}
    styles = {r["UiMapArtStyleID"]: r for r in src.table("UiMapArtStyleLayer") if r["LayerIndex"] == 0}
    tiles = defaultdict(list)
    for r in src.table("UiMapArtTile"):
        if r["LayerIndex"] == 0:
            tiles[r["UiMapArtID"]].append(r)
    rows = defaultdict(list)
    for r in src.table("UiMapAssignment"):
        rows[r["UiMapID"]].append(r)
    out = defaultdict(list)
    for ui, rs in rows.items():
        m = maps.get(ui)
        if not m or m["Type"] not in types or not xart.get(ui):
            continue
        art = arts.get(xart[ui][0])
        style = art and styles.get(art["UiMapArtStyleID"])
        tl = tiles.get(art["ID"]) if art else None
        if not style or not tl:
            continue
        regions, gids, map_ids = [], set(), set()
        for r in rs:
            reg = r["Region"]
            if (r["UiMin"] != [0.0, 0.0] or r["UiMax"] != [1.0, 1.0] or reg[3] - reg[0] >= FAR_REGION
                    or reg[3] <= reg[0] or reg[4] <= reg[1]):
                continue
            regions.append((reg[0], reg[1], reg[3], reg[4]))
            map_ids.add(r["MapID"])
            if r.get("WMOGroupID"):
                gids.add(r["WMOGroupID"])
        if not regions or len(map_ids) != 1:
            continue
        W, H, tw, th = style["LayerWidth"], style["LayerHeight"], style["TileWidth"], style["TileHeight"]
        art_tiles = []
        for t in sorted(tl, key=lambda t: (t["RowIndex"], t["ColIndex"])):
            x, y = t["ColIndex"] * tw, t["RowIndex"] * th
            if x >= W or y >= H:
                continue
            art_tiles.append((t["FileDataID"], x, y, min(tw, W - x), min(th, H - y), tw, th))
        mem = members.get(ui)
        out[map_ids.pop()].append({
            "ui": ui, "name": (mem and mem["Name_lang"]) or m["Name_lang"], "map_name": m["Name_lang"],
            "index": mem["FloorIndex"] if mem else 0, "group": mem["UiMapGroupID"] if mem else 0,
            "bounds": regions[0], "regions": regions, "gids": sorted(gids),
            "art": {"id": art["ID"], "w": W, "h": H, "tiles": art_tiles}})
    for floors in out.values():
        floors.sort(key=lambda f: (f["index"], f["ui"]))
    return dict(out)


# --- the checks ----------------------------------------------------------------------


def floor_groups(models: Models, gids: list, region) -> list:
    """(placement, group index) of the floor's groups: those with its MOGP ids among the models over its
    bounds; with no ids, every group of those models."""
    want = set(gids)
    out = []
    for p in models.placements:
        if not _overlaps(p.bounds, region):
            continue
        w = models.wmo(p.wmo)
        if not w:
            continue
        for gi, gid in enumerate(w["gids"]):
            if not want or gid in want:
                out.append((p, gi))
    return out


def fv_groups(fv: Models, src: Models, groups: list, by_src: dict) -> dict | None:
    """WoW Forever's groups for the source floor's `groups` ((src placement, index)): the same MOGP id in the
    paired model; else the same index when the two models' groups are alike (WoW Forever re-authored some
    models with their groups numbered anew: Blackrock Depths, the Sunken Temple); else its groups whose box
    lies mostly in one of theirs (a model changed: the footprint then tells). {groups, renumbered, vertices
    (the worst share alike of the groups matched one to one, or None)}; None when a model isn't paired."""
    out, seen, renumbered, worst = [], set(), 0, None
    for q, gi in groups:
        p = by_src.get(id(q))
        if p is None:
            return None
        wf, ws = fv.wmo(p.wmo), src.wmo(q.wmo)
        if wf is None or ws is None:
            return None
        gid = ws["gids"][gi]
        if gid is not None and gid in wf["gids"]:
            hits = [wf["gids"].index(gid)]
        elif same_model(wf, ws) is None:
            hits, renumbered = [gi], renumbered + 1
        else:
            sb = world_box(q, ws["boxes"][gi])
            hits = []
            for fi, box in enumerate(wf["boxes"]):
                b = world_box(p, box)
                a = max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1])
                ix = (max(0.0, min(b[2], sb[2]) - max(b[0], sb[0])) * max(0.0, min(b[3], sb[3]) - max(b[1], sb[1])))
                if a and ix >= 0.5 * a and b[4] < sb[5] and b[5] > sb[4]:
                    hits.append(fi)
        if len(hits) == 1 and wf["n"] == ws["n"]:
            share = same_vertices(fv.verts(p.wmo, hits[0]), src.verts(q.wmo, gi))
            worst = share if worst is None else min(worst, share)
        for fi in hits:
            if (id(p), fi) not in seen:
                seen.add((id(p), fi))
                out.append((p, fi))
    return {"groups": out, "renumbered": renumbered, "vertices": worst}


def verify_floor(fv: Models, src: Models, floor: dict, fv_ground=None, src_ground=None, art_ok=None,
                 models_region=None, ground=True) -> dict:
    """Whether a source floor's map fits WoW Forever's dungeon: {ok, why, evidence, z, rooms, places (WoW
    Forever's placements of its rooms' models: (x, y))}. `art_ok(fid)`: the art tile is in WoW Forever's client
    with the source's content; `*_ground`: caves.Ground-like samplers (a map with terrain). `models_region`: where
    every model must be placed alike (default: the floor's bounds; interiormaps.py: the box round its rooms);
    `ground` False: the ground compared as evidence only (a map of indoor rooms, which draws no terrain)."""
    region = floor["bounds"]
    ev = {}
    if any(not _near(r, region, 0.5) for r in floor["regions"]):
        return {"ok": False, "why": "the source's assignments for this floor disagree on its bounds", "evidence": ev}
    if art_ok is not None:
        missing = [t[0] for t in floor["art"]["tiles"] if not art_ok(t[0])]
        ev["art_tiles"] = len(floor["art"]["tiles"])
        if missing:
            return {"ok": False, "why": f"{len(missing)} of its {len(floor['art']['tiles'])} art tiles aren't in WoW "
                    "Forever's client as the source has them (they'd have to be shipped)", "evidence": ev}
    pairs, fv_only, src_only = pair_placements(fv, src, models_region or region)
    ev["models_paired"] = len(pairs)
    if fv_only or src_only:
        names = sorted({fv.cd.name(p.wmo).rsplit("/", 1)[-1] for p in fv_only}
                       | {src.cd.name(p.wmo).rsplit("/", 1)[-1] for p in src_only})
        return {"ok": False, "why": f"the models over it differ: {len(fv_only)} only in WoW Forever, {len(src_only)} "
                f"only in the source ({', '.join(names[:4])}{', ...' if len(names) > 4 else ''})", "evidence": ev}
    if not pairs:
        return {"ok": False, "why": "no model of the dungeon over it", "evidence": ev}
    by_src = {id(q): p for p, q in pairs}
    groups = floor_groups(src, floor["gids"], region)
    if floor["gids"]:
        # (ids no model of the source's has are left over from an older model, the Stockade's half: not a
        # difference, as long as some are its models')
        found = {src.wmo(q.wmo)["gids"][gi] for q, gi in groups}
        ev["source_group_ids_unknown"] = len(set(floor["gids"]) - found)
        if not found:
            return {"ok": False, "why": "the source ties it to WMO groups its models don't have", "evidence": ev}
    ev["groups"] = len(groups)
    mine = fv_groups(fv, src, groups, by_src)
    if mine is None:
        return {"ok": False, "why": "a group of it is on a model WoW Forever hasn't there", "evidence": ev}
    ev["renumbered"] = mine["renumbered"]
    if mine["vertices"] is not None:
        ev["vertices_matched"] = round(mine["vertices"], 4)
    fp = footprint(fv, mine["groups"], region)
    match = footprint_match(fp, footprint(src, groups, region))
    ev["footprint_matched"] = round(match, 4)
    if match < FOOTPRINT_MATCH:
        return {"ok": False, "why": f"its rooms differ: {match:.1%} of their footprint is alike", "evidence": ev}
    zs, inside, area = [], 0.0, 0.0
    rooms = [math.inf, math.inf, -math.inf, -math.inf]
    for p, gi in mine["groups"]:
        b = world_box(p, fv.wmo(p.wmo)["boxes"][gi])
        zs += [b[4], b[5]]
        rooms = [min(rooms[0], max(b[0], region[0])), min(rooms[1], max(b[1], region[1])),
                 max(rooms[2], min(b[2], region[2])), max(rooms[3], min(b[3], region[3]))]
        a = max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1])
        ix = max(0.0, min(b[2], region[2]) - max(b[0], region[0])) * max(0.0, min(b[3], region[3]) - max(b[1], region[1]))
        area += a
        inside += ix
    ev["inside_bounds"] = round(inside / area, 3) if area else 1.0
    if area and inside / area < ALIGN_SHARE:
        return {"ok": False, "why": f"only {inside / area:.0%} of its rooms are inside the map's bounds (the "
                "coordinates don't line up)", "evidence": ev}
    if fv.terrain or src.terrain:
        if fv_ground is None or src_ground is None:
            if ground:
                return {"ok": False, "why": "its ground wasn't compared", "evidence": ev}
        else:
            share = same_ground(fv_ground, src_ground, region)
            ev["ground_matched"] = round(share, 4)
            if ground and share < TERRAIN_SHARE:
                return {"ok": False, "why": f"the ground under it differs ({share:.1%} of it the same)", "evidence": ev}
    z = (round(min(zs), 1), round(max(zs), 1)) if floor["gids"] and zs else None
    if rooms[0] >= rooms[2] or rooms[1] >= rooms[3]:
        rooms = list(region)
    places = sorted({(round(p.x, 2), round(p.y, 2)) for p, _gi in mine["groups"]})
    return {"ok": True, "why": "", "evidence": ev, "z": z, "rooms": [round(v, 1) for v in rooms], "footprint": fp,
            "places": [list(p) for p in places]}


def same_ground(a, b, region) -> float:
    """The share of the ground's samples over `region` alike in both clients: ground in both within
    TERRAIN_YD, or in neither."""
    xs = np.arange(region[0], region[2], TERRAIN_STEP)
    ys = np.arange(region[1], region[3], TERRAIN_STEP)
    X, Y = np.meshgrid(xs, ys)
    ha, _ = a.sample(X, Y)
    hb, _ = b.sample(X, Y)
    fa, fb = np.isfinite(ha), np.isfinite(hb)
    alike = (fa == fb) & (~fa | (np.abs(np.where(fa, ha, 0) - np.where(fb, hb, 0)) <= TERRAIN_YD))
    return float(alike.mean()) if alike.size else 1.0


# --- the inventory ----------------------------------------------------------------------


def render_debug(cd: ClientData, floor: dict, fp: np.ndarray | None, path: Path) -> None:
    """The floor's art (WoW Forever's own textures) with WoW Forever's rooms' footprint outlined in red over
    it, where the map's bounds put them: to see a floor lines up."""
    import io

    from PIL import Image
    from scipy.ndimage import binary_erosion

    art = floor["art"]
    img = Image.new("RGBA", (art["w"], art["h"]))
    for fid, x, y, w, h, _tw, _th in art["tiles"]:
        tile = Image.open(io.BytesIO(cd.casc.read(fid))).convert("RGBA")
        img.paste(tile.crop((0, 0, w, h)), (x, y))
    if fp is not None and fp.any():
        x0, y0, x1, y1 = floor["bounds"]
        edge = fp & ~binary_erosion(fp)
        ix, iy = np.nonzero(edge)
        X, Y = x0 + (ix + 0.5) * FOOTPRINT_YD, y0 + (iy + 0.5) * FOOTPRINT_YD
        u = ((y1 - Y) / (y1 - y0) * art["w"]).astype(int)
        v = ((x1 - X) / (x1 - x0) * art["h"]).astype(int)
        px = np.asarray(img).copy()
        ok = (u >= 0) & (u < art["w"]) & (v >= 0) & (v < art["h"])
        px[v[ok], u[ok]] = (255, 40, 40, 255)
        img = Image.fromarray(px)
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path)


def dungeon_rows(fv: ClientData) -> list:
    """Every dungeon and raid map WoW Forever's client has (the Map rows with an InstanceType 1 or 2)."""
    rows = [r for r in fv.table("Map") if r["InstanceType"] in (1, 2) or r["ID"] in INS.TRANSIT_MAPS]  # (+ the Deeprun Tram)
    return sorted(rows, key=lambda r: (r["InstanceType"], r["ID"]))


def inventory(fv: ClientData, src: ClientData, log=print, debug_dir: Path | None = None) -> dict:
    """Every dungeon (and raid) with each candidate floor: accepted or skipped and why. `debug_dir`: each
    candidate floor's art there (`render_debug`), the accepted ones with WoW Forever's rooms over it."""
    from .caves import Ground

    floors_by_map = source_floors(src)
    entries = []
    for r in dungeon_rows(fv):
        mid, name, raid = r["ID"], r["MapName_lang"], r["InstanceType"] == 2
        e = {"map": mid, "level": INS.level_id(mid), "name": name, "raid": raid, "floors": []}
        entries.append(e)
        cands = floors_by_map.get(mid, [])
        if raid and not INCLUDE_RAIDS:
            e.update(status="skipped", why="a raid: out of this import's scope (dungeons only)")
            continue
        if mid in INS.SKIP_MAPS:
            e.update(status="skipped", why="not a dungeon the addon has (instances.SKIP_MAPS: a test map or unused)")
            continue
        if not cands:
            e.update(status="skipped", why=f"{SOURCE_NAME} has no map of it (WoW Forever's own, or none there)")
            continue
        try:
            fm, sm = Models(fv, mid), Models(src, mid)
        except Exception as ex:  # (no WDT in one of them)
            e.update(status="skipped", why=f"its models can't be read: {ex}")
            continue
        fg = sg = None
        if fm.terrain or sm.terrain:
            fg, sg = Ground(fv, mid), Ground(src, mid)

        def art_ok(fid):
            return fv.casc.has(fid) and fv.casc.root.get(fid) == src.casc.root.get(fid)

        for f in cands:
            res = verify_floor(fm, sm, f, fg, sg, art_ok)
            fe = {"ui": f["ui"], "name": f["name"], "index": f["index"], "status": "accepted" if res["ok"] else "skipped",
                  "why": res["why"], "evidence": res["evidence"]}
            if res["ok"]:
                fe["data"] = {"bounds": [round(v, 2) for v in f["bounds"]], "z": res.get("z"), "rooms": res["rooms"],
                              "art": f["art"]}
            e["floors"].append(fe)
            if debug_dir is not None:
                render_debug(fv, f, res.get("footprint"), Path(debug_dir) / f"{mid}_{f['ui']}_{fe['status']}.png")
            log(f"  {name} ({mid}) floor {f['ui']} {f['name']!r}: {fe['status']} {res['why']}")
        n = sum(f["status"] == "accepted" for f in e["floors"])
        if n:
            e.update(status="accepted", why=f"{n} of {len(e['floors'])} floors match")
        else:
            e.update(status="skipped", why="no floor matches: " + "; ".join(sorted({f["why"] for f in e["floors"]})))
    return {"source": {"name": SOURCE_NAME, "product": SOURCE_PRODUCT, "build": src.casc.version,
                       "url": SOURCE_URL.format(build=src.casc.version)},
            "client": {"product": fv.casc.product, "build": fv.casc.version},
            "time": time.strftime("%Y-%m-%d"), "dungeons": entries}


def _lua_str(s: str) -> str:
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def dungeon_maps_lua(inv: dict) -> str:
    """Data/DungeonMaps.lua: each accepted dungeon's floors' world maps (numbers and names only)."""
    src = inv["source"]
    out = [f"-- GENERATED by `agps dungeon-maps --write` from client {inv['client']['build']} and the dungeon maps of",
           f"-- {src['name']} {src['build']} where their layout is WoW Forever's (app/azerothgps/dungeonmaps.py;",
           "-- the inventory: docs/dungeon-maps.md). Do not edit by hand.",
           "local _, ns = ...",
           "",
           "-- [level] = { floors = { { ui, name, index, bounds = { minX, minY, maxX, maxY } (the instance's world yards),",
           "--   z = { lo, hi } or nil (its rooms' heights; nil: every height), rooms = { minX, minY, maxX, maxY } (the box",
           "--   round its rooms, in its bounds: which floor a view is on), artW, artH,",
           "--   tiles = { {fileID, x, y, w, h, texW, texH} } (art pixels, as Maps.lua's) } } }",
           "ns.DungeonMaps = {"]
    for e in inv["dungeons"]:
        fl = [f for f in e["floors"] if f["status"] == "accepted"]
        if not fl:
            continue
        out.append(f"  [{e['level']}] = {{ name = {_lua_str(e['name'])}, floors = {{")
        for f in fl:
            d = f["data"]
            b = d["bounds"]
            z = f"{{ {d['z'][0]:.1f}, {d['z'][1]:.1f} }}" if d["z"] else "nil"
            r = d["rooms"]
            tiles = ", ".join("{%d,%d,%d,%d,%d,%d,%d}" % tuple(t) for t in d["art"]["tiles"])
            out.append(f"    {{ ui = {f['ui']}, name = {_lua_str(f['name'])}, index = {f['index']}, "
                       f"bounds = {{ {b[0]:.2f}, {b[1]:.2f}, {b[2]:.2f}, {b[3]:.2f} }}, z = {z}, "
                       f"rooms = {{ {r[0]:.1f}, {r[1]:.1f}, {r[2]:.1f}, {r[3]:.1f} }}, "
                       f"artW = {d['art']['w']}, artH = {d['art']['h']},")
            out.append(f"      tiles = {{ {tiles} }} }},")
        out.append("  } },")
    out.append("}")
    return "\n".join(out) + "\n"


def inventory_md(inv: dict) -> str:
    src = inv["source"]
    lines = ["# Dungeon maps: coverage", "",
             "Generated by `agps dungeon-maps --write` (app/azerothgps/dungeonmaps.py) on " + inv["time"] + ".", "",
             f"- Source: {src['name']} {src['build']}, its UiMap tables ({src['url']}), read from the local client.",
             f"- Checked against WoW Forever {inv['client']['build']}.",
             "- A floor is accepted only when every model over it is placed alike, its rooms cover the same ground seen",
             "  from above (`footprint_matched`), its ground is the same (maps with terrain: `ground_matched`), its rooms",
             "  are inside its bounds (`inside_bounds`) and its art tiles are in WoW Forever's own client with the same",
             "  content: see the module's docstring. `vertices_matched` is evidence only (WoW Forever re-meshed some",
             "  models whose rooms are the same). A skipped dungeon keeps the map it had (its models' minimap art, or",
             "  its terrain's). Raids are out of this import's scope.",
             "- The source's art has its own version's boss marks drawn in; the addon's boss icons are drawn over it.",
             "- Pictures of each floor with WoW Forever's rooms outlined over it: `data/debug/dungeonmaps/` (not in git).",
             ""]
    for status in ("accepted", "skipped"):
        rows = [e for e in inv["dungeons"] if e["status"] == status]
        lines += [f"## {status.capitalize()} ({len(rows)})", ""]
        for e in rows:
            lines.append(f"- **{e['name']}** (map {e['map']}{', raid' if e['raid'] else ''}): {e['why']}")
            for f in e["floors"]:
                evid = ", ".join(f"{k} {v}" for k, v in f["evidence"].items())
                lines.append(f"  - floor {f['ui']} \"{f['name']}\": {f['status']}"
                             + (f" ({f['why']})" if f["why"] else "") + (f"; {evid}" if evid else ""))
        lines.append("")
    return "\n".join(lines)


def write(inv: dict, addon_dir: Path) -> list:
    INVENTORY.write_text(json.dumps(inv, indent=1) + "\n", encoding="utf-8", newline="\n")
    DOC.write_text(inventory_md(inv), encoding="utf-8", newline="\n")
    p = addon_dir / "Data" / "DungeonMaps.lua"
    p.write_text(dungeon_maps_lua(inv), encoding="utf-8", newline="\n")
    return [INVENTORY, DOC, p]
