"""Red Cloud Mesa's palisade, a hard barrier (item 78 the third time; Kooki3z 2026-11-25 on the 1.4.0 build).

From inside the mesa by Kodo Rock (his map cursor Mulgore 49.7, 73.3) to a stop north by Bloodhoof Village the route
went straight north to the rim and jumped (a coil) through the palisade, east of where the two earlier fixes had cut it.
Those cut the world grid's links where they crossed a model's wall at 0.5 and 1.2 yd over their floors, and their
test's 84 "palisade" segments were Camp Narache's posts, not the wall. Now the wall's footprint in plan view, from the
client's model collision (app/azerothgps/modelwalls.py, Data/ModelWalls.lua), is a barrier for every route piece: the
grid's steps, its far drops, its road and drop links, the ends' surfaces, and the Router's legs and spell jumps
(Passability.CrossesWall). The way off the mesa north is the road down its west end.

- From five spots along the inside of the palisade, west to east (his among them), with class spells and Expert
  jumper on and off, to two stops north of it: no route piece crosses the footprint, and each route leaves the mesa
  top by the road.
- Every shipped link in the Mulgore tiles round the mesa (the grid's neighbor links, its far drops, its road and drop
  links) that crosses the footprint is refused by the search's own checks.
"""

import math

import pytest

from test_map_redraw import game  # noqa: F401

pytest.importorskip("lupa")

MAGE = "IsPlayerSpell = function(id) return id == 130 end"
FEATHERS = "GetItemCount = function(id) return id == 17056 and 5 or 0 end"
WARRIOR = "IsPlayerSpell = function() return false end"

# (inside the palisade, a dozen to twenty yards from it, west to east; (-2740, -579): his spot, Mulgore 49.7, 73.3,
# a yard off the wall's peak)
INSIDE = [(-2930.0, -80.0), (-2795.0, -250.0), (-2865.0, -420.0), (-2740.0, -579.0), (-2885.0, -800.0)]
NORTH = [(-2240.0, -463.0), (-2113.0, -413.0)]  # (Mulgore 47.8, 61.1 and 47, 58: by Bloodhoof Village)
MESA_TOP_Z = 30  # (the mesa's top inside the palisade is at 45 to 60; the plain north of it under 10)
# (the way off the top north: round the palisade's west end, where the road from Camp Narache goes down; the route's
# first point under the top is past that end (west of it) and this near the road: a walk down beside the road too)
ROAD_GAP_YD = 80
WEST_END_Y = -60  # (the palisade's west end, (-2915, -50))
SHIFT = 131072  # (WorldGrid.lua's: a surface's id, its tile's key * SHIFT + its index)
BOX = (-3000.0, -2650.0, -950.0, 100.0)  # (modelwalls.REGIONS' Red Cloud Mesa)


def _segments(ns, cont=1):
    out = []
    for w in ns.Passability.ModelWallOutlines(cont).values():
        p = [w[i] for i in range(1, len(w) + 1)]
        if not any(BOX[0] < p[i] < BOX[1] and BOX[2] < p[i + 1] < BOX[3] for i in range(0, len(p) - 1, 2)):
            continue  # (the mesa's walls only: the whole map's are shipped since)
        out.extend(tuple(p[i:i + 4]) for i in range(0, len(p) - 3, 2))
    return out


def _cross(a, b, s):
    def o(p, q, rx, ry):
        return (q[0] - p[0]) * (ry - p[1]) - (q[1] - p[1]) * (rx - p[0])
    c, d = (s[0], s[1]), (s[2], s[3])
    return (o(a, b, *c) * o(a, b, *d) <= 0 and o(c, d, *a) * o(c, d, *b) <= 0
            and not (o(a, b, *c) == 0 and o(a, b, *d) == 0))


def _crosses(segs, a, b):
    x0, x1, y0, y1 = min(a[0], b[0]), max(a[0], b[0]), min(a[1], b[1]), max(a[1], b[1])
    for s in segs:
        if max(s[0], s[2]) < x0 or min(s[0], s[2]) > x1 or max(s[1], s[3]) < y0 or min(s[1], s[3]) > y1:
            continue
        if _cross(a, b, s):
            return True
    return False


def _roads(ns, cont=1):
    out = []
    e = ns.Roads[cont].e
    for i in range(1, len(e) + 1):
        ed = e[i]
        pts = [(ed[k], ed[k + 1]) for k in range(5, len(ed) + 1, 2) if ed[k + 1] is not None]
        if any(BOX[0] - 200 < x < BOX[1] + 200 and BOX[2] - 200 < y < BOX[3] + 200 for x, y in pts):
            out.append(pts)
    return out


def _near_road(roads, x, y):
    best = math.inf
    for pts in roads:
        for (ax, ay), (bx, by) in zip(pts, pts[1:]):
            vx, vy = bx - ax, by - ay
            L2 = vx * vx + vy * vy
            t = max(0.0, min(1.0, ((x - ax) * vx + (y - ay) * vy) / L2)) if L2 else 0.0
            best = min(best, math.hypot(ax + vx * t - x, ay + vy * t - y))
    return best


@pytest.fixture
def mulgore(game):  # noqa: F811
    lua, ns = game
    N, st = ns.Nav, ns.settings.gps
    cdb = ns.CharDB()
    saved = (cdb.faction, st.zoom, st.fastestOrder, st.expertJumper, st.useClassSpells, st.worldGrid, st.cityGrid)
    lua.execute("AGPS_PAL = { IsPlayerSpell, GetItemCount }")
    st.worldGrid, st.cityGrid = True, True
    ns.WorldGrid.Set(True)
    ns.CityGrid.Set(True)

    def run(a, b, spells):
        st.zoom, st.fastestOrder = 300, False
        cdb.faction = "Horde"
        st.useClassSpells, st.expertJumper = spells, spells
        N.Clear()
        ns.Passability.RefreshWalls()
        lua.execute(MAGE if spells else WARRIOR)
        lua.execute(FEATHERS)
        ns.FallSpells.Refresh()
        ns.Router.Reset()
        lua.execute(f"AGPS_MAP = 1412 AGPS_POS = {{ {a[0]}, {a[1]}, 1 }}")
        N.SetStops(lua.eval(f"{{ {{ x = {b[0]}, y = {b[1]}, cont = 1, name = 'stop' }} }}"), False, "red")
        N.Invalidate(True, True)
        ns.GPS.Follow()
        for _ in range(16):
            lua.execute("AGPS_T = AGPS_T + 0.5")
            ns.GPS.Update()
        return N.route

    try:
        yield run
    finally:
        N.Clear()
        lua.execute("IsPlayerSpell, GetItemCount = AGPS_PAL[1], AGPS_PAL[2]")
        ns.FallSpells.Refresh()
        (cdb.faction, st.zoom, st.fastestOrder, st.expertJumper, st.useClassSpells, st.worldGrid,
         st.cityGrid) = saved
        ns.WorldGrid.Set(bool(st.worldGrid))
        ns.CityGrid.Set(bool(st.cityGrid))


def test_the_palisade_s_footprint_is_shipped(game):  # noqa: F811
    lua, ns = game
    segs = _segments(ns)
    assert len(segs) > 500
    xs = [v for s in segs for v in (s[1], s[3])]
    assert min(xs) < -850 and max(xs) > -60  # (the whole wall, west cliffs to east rocks)
    P = ns.Passability
    assert P.HasModelWalls(1)
    # (his jump through it, from his spot to the plain below the rim, and the earlier fixes' drop at (-2779, -245))
    assert P.CrossesModelWall(1, -2740, -579, -2712, -562) and P.CrossesWall(1, -2740, -579, -2712, -562)
    assert P.CrossesModelWall(1, -2790, -245, -2760, -245)
    assert not P.CrossesModelWall(1, -2800, -579, -2760, -585)  # (inside, along it)


@pytest.mark.parametrize("spells", [True, False], ids=["spells_expert", "no_spells"])
@pytest.mark.parametrize("start", INSIDE, ids=["west", "camp_north", "mid", "his_spot", "east"])
def test_no_route_crosses_the_palisade_and_each_leaves_by_the_road(game, mulgore, start, spells):  # noqa: F811
    lua, ns = game
    segs, roads = _segments(ns), _roads(ns)
    for stop in NORTH:
        r = mulgore(start, stop, spells)
        assert r and r.parts and len(r.parts) >= 1, (start, stop)
        off = None
        for p in range(1, len(r.parts) + 1):
            part = r.parts[p]
            n = len(part.pts) // 2
            for i in range(1, n):
                a = (part.pts[2 * i - 1], part.pts[2 * i])
                b = (part.pts[2 * i + 1], part.pts[2 * i + 2])
                assert not _crosses(segs, a, b), \
                    f"through the palisade: {start} -> {stop}, piece {i} ({a[0]:.0f}, {a[1]:.0f}) -> ({b[0]:.0f}, " \
                    f"{b[1]:.0f}), kind {part.kinds[i]}"
                z = part.fz[i + 1] if part.fz else None
                if off is None and isinstance(z, (int, float)) and z < MESA_TOP_Z:
                    off = b
        assert off, (start, stop)  # (down off the top somewhere)
        assert off[1] > WEST_END_Y and _near_road(roads, *off) <= ROAD_GAP_YD,             f"off the mesa away from the road's way down: {start} at {off}"


def test_no_shipped_link_through_the_palisade_is_taken(game, mulgore):  # noqa: F811
    """Every link in the tiles round the mesa (the grid's neighbor links, the far drops, the road and drop links) that
    crosses the footprint is refused by the search's own checks (Passability.CrossesModelWall, WorldGrid.WalledLinks)."""
    lua, ns = game
    mulgore(INSIDE[3], NORTH[0], True)  # (the region's tiles loaded)
    WG, P = ns.WorldGrid, ns.Passability
    c = WG.Cont(1)
    segs = _segments(ns)
    cell = c.cell
    walled = WG.WalledLinks(c)
    seen_keys = set()
    crossing = {"step": 0, "far": 0, "link": 0}
    checked = 0
    for gx in range(int(BOX[0] // cell), int(BOX[1] // cell) + 1):
        for gy in range(int(BOX[2] // cell), int(BOX[3] // cell) + 1):
            key, ci = WG.CellKey(c, gx, gy)
            t = key and WG.Tile(c, key)
            if not t:
                continue
            seen_keys.add(key)
            n = WG.Count(t, ci)
            f0 = WG.First(t, ci) if n else 0
            for k in range(n):
                s = f0 + k
                sx, sy = WG.Pt(c, t, s, ci)
                for d in range(1, 9):
                    kk = WG.Link(t, s, d)
                    if kk and kk > 0:
                        nkey, nci = WG.Step(c, key, ci, d)
                        nt = nkey and WG.Tile(c, nkey)
                        if nt:
                            px, py = WG.Pt(c, nt, WG.First(nt, nci) + kk - 1, nci)
                            checked += 1
                            if _crosses(segs, (sx, sy), (px, py)):
                                crossing["step"] += 1
                                assert P.CrossesModelWall(1, sx, sy, px, py), (sx, sy, px, py)
                fd = WG.FarDrops(c, t, s, key, ci, WG.Z(c, t, s), sx, sy)
                for e in (fd.values() if fd else []):
                    checked += 1
                    if _crosses(segs, (sx, sy), (e.x, e.y)):
                        crossing["far"] += 1
                        assert P.CrossesModelWall(1, sx, sy, e.x, e.y), (sx, sy, e.x, e.y)
                out = c.out[key * SHIFT + s]
                for li in (out.values() if out else []):
                    L = c.links[li]
                    pts = [(L.pts[j][1], L.pts[j][2]) for j in range(1, len(L.pts) + 1)]
                    checked += 1
                    if any(_crosses(segs, a, b) for a, b in zip(pts, pts[1:])):
                        crossing["link"] += 1
                        assert walled(L), pts
    assert seen_keys and checked > 10000, checked
    print(crossing, checked)
