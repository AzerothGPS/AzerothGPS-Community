"""1.4.2's routing regressions against 1.4.1 (the hpa-bench's 100 trips and route-quality, 2026-11-27).

1. The hpa-bench's trip 32, an Alliance 50 from Kharanos to the Tower of Arathor: settled at 14.5 s on 1.4.1, 49.7 s on
   the combined build. Its stop is in Stromgarde's keep, inside the elite area round it, with no straight walkable line
   out (the keep's walls): item 142's way in (Router.EliteExit) was a line through the walls, the rest of the area paid
   for, and the search round the elites ran into its cap (150,000 nodes) before the way through was searched: 417k
   nodes for 1.4.1's 137k. Such an end's area is all its own again, as item 91 made it (Router.EliteExit's `walled`).
2. Route-quality's level 40 Horde trip from Satyrnaar to Lariss Pavilion, 1,206 s -> 1,217 s: the height bends on the
   recorded walks (Router.ZBends, Blackrock Mountain's switchback) moved a shipped walk's junctions by Lariss Pavilion
   (over a hill, no turn over another), and its walk from Camp Taurajo went round by a road and a gap link. The bends now
   go only where floors stack: a walk whose turns lie over each other (Router.TurnsOver), or one in a capital or on a
   building's or a layered cave's floors (Router.FloorsAt)."""

import json
import math
from pathlib import Path

import pytest

pytest.importorskip("lupa")

ROOT = Path(__file__).resolve().parents[2]
EK, KALIMDOR = 0, 1
KHARANOS, TOWER = (-5583.3, -516.7), (-1778.2, -1513.2)  # (the hpa-bench's trip 32; the Tower of Arathor's elite area)
STROMGARDE = 2050  # (that area's town, Data/Hostile.lua's)
CAMP_TAURAJO, LARISS = (-2380.7, -1882.7), (-4116.7, 83.3)  # (route-quality's trip 164, seed 21: its walk from the flight)
NODE_BUDGET = 200000  # world grid + city grid nodes: 1.4.1 and the fix 136,555 (the bench's), the combined build 417,397
BRD_SWITCHBACK, LARISS_WALK = 1795410740, 1795413394  # (Roads.lua's FloorTracks: their times)
STORMWIND_GATE_WALK = 1795319842  # (in the capital: its bends kept the hpa-bench's trip 23 on the tram)


@pytest.fixture(scope="module")
def game():
    from azerothgps.gameharness import start
    lua, ns = start()
    ns.Nav.FUN = False
    yield lua, ns


def _be(lua, ns, faction, level):
    lua.execute(f"UnitFactionGroup = function() return '{faction}', '{faction}' end; AGPS_LEVEL = {level}")
    ns.CharDB().faction = faction
    ns.Router.Reset()


@pytest.fixture
def char(game):
    lua, ns = game
    lua.execute("AGPS_RG_UFG, AGPS_RG_LVL = UnitFactionGroup, AGPS_LEVEL")
    saved = ns.CharDB().faction
    yield lua, ns
    lua.execute("UnitFactionGroup, AGPS_LEVEL = AGPS_RG_UFG, AGPS_RG_LVL")
    ns.CharDB().faction = saved
    ns.Router.Reset()


def test_a_stop_in_a_walled_keep_has_its_elite_area_free(char):
    lua, ns = char
    R = ns.Router
    _be(lua, ns, "Alliance", 50)
    side = R.HostileSide()
    at = R.EliteTownsAt(EK, *TOWER, side)
    assert at and at[STROMGARDE]
    _, _, depth = R.EliteExit(EK, side, STROMGARDE, *TOWER)
    assert depth > 0 and R.EliteWalled(EK, side, STROMGARDE, *TOWER)
    near = R.HostileTownsNear(EK, side, *TOWER)
    assert near[STROMGARDE] is True  # (all of it, as item 91's: the keep's way in is by its gate, across the area)


def _settle(lua, ns, side, level, cont, start, stop, max_ticks=2000):
    """The trip set and worked out as the game does (test_common_trips_settle's): (ticks till settled or None, nodes)."""
    R, N, WG, CG = ns.Router, ns.Nav, ns.WorldGrid, ns.CityGrid
    _be(lua, ns, side, level)
    WG.routes, WG.order, WG.targets = lua.table(), lua.table(), lua.table()
    WG.failed, WG.failOrder = lua.table(), lua.table()
    CG.routes, CG.order = lua.table(), lua.table()
    now = lua.eval("function() return os.clock() * 1000 end")
    R.SYNC_WALKS = False
    N.Clear()
    lua.execute(f"AGPS_POS = {{ {start[0]}, {start[1]}, {cont} }}")
    n0 = WG.stats.nodes + CG.stats.nodes
    N.SetStops(lua.eval(f"{{ {{ x = {stop[0]}, y = {stop[1]}, cont = {cont}, name = 'stop' }} }}"), False, "red")
    settled = None
    try:
        for tick in range(max_ticks):
            lua.execute(f"AGPS_T = {tick * 0.05}")
            r = N.Route(start[0], start[1], cont)
            t1 = now()
            while R.HasWork() and now() - t1 < 8:
                res = R.Pump(now() + 4, now)
                done, fixed = res if isinstance(res, tuple) else (res, None)
                if done:
                    N.SearchDone(fixed)
            if r and not r.pending:
                settled = tick
                break
            if WG.stats.nodes + CG.stats.nodes - n0 > NODE_BUDGET * 3:
                break  # (far past it)
    finally:
        while R.HasWork():
            R.Pump(now() + 50, now)
        R.SYNC_WALKS = True
        N.Clear()
    return settled, WG.stats.nodes + CG.stats.nodes - n0


def test_kharanos_to_the_tower_of_arathor_settles_within_its_budget(char):
    lua, ns = char
    st, WG, CG = ns.settings.gps, ns.WorldGrid, ns.CityGrid
    saved = (st.worldGrid, st.cityGrid)
    st.worldGrid, st.cityGrid = True, True
    WG.Set(True)
    CG.Set(True)
    try:
        ticks, nodes = _settle(lua, ns, "Alliance", 50, EK, KHARANOS, TOWER)
        assert ticks is not None, f"never settled ({nodes} nodes)"
        assert nodes <= NODE_BUDGET, nodes
    finally:
        st.worldGrid, st.cityGrid = saved
        WG.Set(saved[0])
        CG.Set(saved[1])


def _pieces(cont, time):
    """A recorded walk's pieces with their heights (overrides/roads_<cont>.geojson, as Roads.lua's FloorTracks)."""
    d = json.loads((ROOT / "overrides" / f"roads_{cont}.geojson").read_text(encoding="utf-8"))
    return [list(zip(f["geometry"]["coordinates"], f["properties"]["zs"])) for f in d["features"]
            if f["properties"].get("time") == time and f["properties"].get("zs")]


def _turns_over(lua, ns, pts):
    """Router.TurnsOver on a walk's points made dense as Router.WithTracks makes them (every 2 yd or so)."""
    dx, dy, dz = [pts[0][0][0]], [pts[0][0][1]], [pts[0][1]]
    for ((ax, ay), za), ((bx, by), zb) in zip(pts, pts[1:]):
        m = max(1, math.ceil(math.dist((ax, ay), (bx, by)) / 2))
        for q in range(1, m + 1):
            dx.append(ax + (bx - ax) * q / m)
            dy.append(ay + (by - ay) * q / m)
            dz.append(za + (zb - za) * q / m)
    along = [0.0]
    for q in range(1, len(dx)):
        along.append(along[-1] + math.dist((dx[q - 1], dy[q - 1]), (dx[q], dy[q])))
    t = lua.table
    return bool(ns.Router.TurnsOver(t(*dx), t(*dy), t(*dz), t(*along), len(dx)))


def test_the_height_bends_go_only_where_floors_stack(game):
    lua, ns = game
    (brd,) = _pieces(EK, BRD_SWITCHBACK)
    assert _turns_over(lua, ns, brd)  # (Blackrock Mountain's switchback: 264 over 250 over 226)
    lariss = _pieces(KALIMDOR, LARISS_WALK)
    assert lariss and not any(_turns_over(lua, ns, p) for p in lariss)  # (over a hill by Lariss Pavilion)
    t = lua.table
    for p in lariss:  # (on the open land: no capital, no building's or cave's floors)
        assert not ns.Router.FloorsAt(KALIMDOR, t(*[q[0][0] for q in p]), t(*[q[0][1] for q in p]), len(p))
    stormwind = _pieces(EK, STORMWIND_GATE_WALK)
    assert stormwind and ns.Router.FloorsAt(EK, t(*[q[0][0] for q in stormwind[0]]), t(*[q[0][1] for q in stormwind[0]]),
                                             len(stormwind[0]))


def test_the_walk_from_camp_taurajo_to_lariss_pavilion_keeps_1_4_1_s_way(char):
    lua, ns = char
    R = ns.Router
    _be(lua, ns, "Horde", 40)
    R.SYNC_WALKS = True
    r = R.Route(KALIMDOR, *CAMP_TAURAJO, *LARISS, lua.table())
    assert r and not r.pending
    assert r.length <= 5660, r.length  # (1.4.1: 5,648 yd; the bends by Lariss Pavilion, 5,719)
