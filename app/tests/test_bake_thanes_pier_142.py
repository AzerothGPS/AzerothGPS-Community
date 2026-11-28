"""1.4.2 items 140, 138b and 141b, with the whole addon (the grids on, as shipped).

140: Ironforge's Hall of Thanes switchback (Kooki3z 2026-11-27, "its just that cobweb switch back section"): a player
halfway down the cobwebbed switchback under the High Seat was routed back up to the city's floor, "make a U-turn ...
toward Ironforge 35 yd up". The city grid's road link along the recorded walk (Roads.lua's FloorTracks, time 1795740878)
had the Router's node heights only, straight between, and began at the switchback's top; the bake now walks a road along
a recorded walk at the walk's own heights (citygrid.floor_tracks).
138b: Auberdine's boat waits 12 yd off the pier, the sea's bottom 19 yd under it: the walk off it swam 290 yd to the beach.
The dock's spot is on the pier's deck now (addon_data.DOCK_SPOTS).
141b: Thunder Bluff's southwest lift, one car's "lift" road from its foot to the land's road beside it (as the north
lift's were before item 141): both cars' roads go from the mesa's top to the foot.
"""

import json
import math
import re
from pathlib import Path

import pytest

pytest.importorskip("lupa")

ROOT = Path(__file__).resolve().parents[2]
ADDON = ROOT / "addon" / "AzerothGPS"
THANES_WALK = 1795740878  # (Kooki3z's recorded walk from the Great Forge down to the Hall of Thanes, 1.4.1)
WAY_IN = (-4822.3, -932.4, 399.0)  # (the Hall of Thanes' way in: test_hall_of_thanes.py's)
SWITCHBACK = 60  # (the walk's point where Kooki3z stood, 47.6, 49.9 on Ironforge's map: the second turn, z 459)
AUBERDINE_INN = (6406.5, 515.4, 8.7)  # (Innkeeper Shaussiy)
SW_SHAFTS = ((-1308.4, 185.3), (-1286.2, 189.7))  # (Thunder Bluff's southwest lift, Data/LiftTimes.lua's station 6)
SW_FOOT_ROAD = (1, -1360.0, 165.0, None)  # (Mulgore's road by the southwest lift's foot)
SW_TOP = (1, -1298.0, 150.0, 130.0)  # (the central mesa by the lift's top)


@pytest.fixture(scope="module")
def game():
    from azerothgps.gameharness import start
    lua, ns = start()
    st = ns.settings.gps
    st.cityGrid, st.worldGrid = True, True
    ns.WorldGrid.Set(True)
    ns.CityGrid.Set(True)
    ns.CharDB().faction = "Alliance"
    lua.execute('UnitFactionGroup = function() return "Alliance", "Alliance" end')
    return lua, ns


def _list(t):
    return [t[i] for i in range(1, len(t) + 1)] if t is not None else []


def _pts(r):
    n = len(r.pts) // 2
    zs = r.zs if r.zs is not None else r.fz
    return [(r.pts[2 * i - 1], r.pts[2 * i], zs[i] if zs is not None else None) for i in range(1, n + 1)]


def _walk():
    d = json.loads((ROOT / "overrides" / "roads_0.geojson").read_text(encoding="utf-8"))
    f = next(f for f in d["features"] if f["properties"].get("time") == THANES_WALK)
    return [(x, y, z) for (x, y), z in zip(f["geometry"]["coordinates"], f["properties"]["zs"])]


# --- 140: the Hall of Thanes' switchback ------------------------------------------------------------------------------

def test_a_start_in_the_switchback_tracks_the_tunnel_s_floor_and_routes_on_down(game):
    """Walked from the Great Forge's floor down the recorded walk, the floor followed is the walk's every step (never the
    city's floor over the tunnel); from the switchback's second turn, the route goes on down the walk to the Hall's way
    in, not back up to the city."""
    lua, ns = game
    CG = ns.CityGrid
    walk = _walk()
    CG.track = None
    lua.execute("AGPS_T = (AGPS_T or 0) + 1")
    CG.TrackFloor(0, walk[0][0], walk[0][1], walk[0][2])
    off = []
    for i, (x, y, z) in enumerate(walk[1:SWITCHBACK + 1], 1):
        lua.execute("AGPS_T = AGPS_T + 1")
        CG.TrackFloor(0, x, y, None)
        t = CG.track
        got = t and (t.z or t.pick)
        if got is None or abs(got - z) > 4:
            off.append((i, round(z, 1), got))
    assert not off, off
    x, y, z = walk[SWITCHBACK]
    start_z = CG.track.z or CG.track.pick
    assert abs(start_z - z) <= 3, (start_z, z)
    try:
        ns.Router.Reset()
        r = ns.Router.Route(0, x, y, WAY_IN[0], WAY_IN[1], lua.table_from({"z": start_z, "tz": WAY_IN[2]}))
    finally:
        CG.track = None
    assert r is not None and not r.noWay
    pts = _pts(r)
    assert abs(pts[-1][2] - WAY_IN[2]) < 3, pts[-1]
    # (on down: never up to the switchback's turns over it, nor the city's floor at 502)
    top = max(p[2] for p in pts if p[2] is not None)
    assert top <= z + 6, (top, z)
    # (the walk's own way on from there is 390 yd; back up and round was 561)
    assert r.length < 450, r.length


def test_the_city_grid_s_road_links_along_the_walk_keep_to_its_heights(game):
    """No road link of the city grid along the recorded walk has a point more than a few yards off the walk's height
    where the walk is (the old one ran 225 yd from the switchback's top, straight from 491 to 446)."""
    lua, ns = game
    c = ns.CityGrid.City("Ironforge")
    walk = _walk()

    def heights(x, y):  # (the walk's heights within 2 yd across of (x, y))
        out = []
        for a, b in zip(walk, walk[1:]):
            dx, dy = b[0] - a[0], b[1] - a[1]
            L2 = dx * dx + dy * dy or 1e-9
            f = max(0.0, min(1.0, ((x - a[0]) * dx + (y - a[1]) * dy) / L2))
            if math.hypot(a[0] + dx * f - x, a[1] + dy * f - y) <= 2.0:
                out.append(a[2] + (b[2] - a[2]) * f)
        return out
    bad, along = [], 0
    for li in range(1, c.nBaked + 1):
        L = c.links[li]
        lp = [(p[1], p[2], p[3]) for p in _list(L.pts)]
        hs = [heights(x, y) for x, y, _z in lp]
        if len(lp) < 3 or sum(1 for h in hs if h) < 0.8 * len(lp):
            continue  # (not a link along the walk)
        along += 1
        for (x, y, z), h in zip(lp, hs):
            if h and min(abs(v - z) for v in h) > 6:
                bad.append((li, round(x), round(y), round(z, 1), sorted(round(v) for v in h)))
                break
    assert along, "no road link along the walk"
    assert not bad, bad[:5]


# --- 138b: Auberdine's pier -------------------------------------------------------------------------------------------

def _auberdine(ns):
    rows = ns.Transports
    for i in range(1, len(rows) + 1):
        t = rows[i]
        if t[10] == "Auberdine, Darkshore":
            return t
    raise AssertionError("no Auberdine boat")


def test_auberdine_s_boat_lands_on_the_pier_s_deck(game):
    lua, ns = game
    t = _auberdine(ns)
    assert t.z2 is not None and 4 <= t.z2 <= 9, t.z2
    WG = ns.WorldGrid
    c = WG.Cont(1)
    here = WG.SurfacesAt(c, t[5], t[6])
    dry = [s.z for s in (here[k] for k in range(1, len(here) + 1)) if int(s.f) % 2 == 0]  # (not the water's: F_SWIM)
    assert any(abs(z - t.z2) <= 2 for z in dry), (t[5], t[6], dry)


def test_the_walk_off_auberdine_s_boat_walks_the_pier(game):
    """From where the boat lands (its height the deck's, Nav's EndZ) to Auberdine's inn: along the pier, no swim."""
    lua, ns = game
    t = _auberdine(ns)
    ns.Router.Reset()
    r = ns.Router.Route(1, t[5], t[6], AUBERDINE_INN[0], AUBERDINE_INN[1],
                        lua.table_from({"z": t.z2, "tz": AUBERDINE_INN[2]}))
    assert r is not None and not r.noWay
    pts = _pts(r)
    low = [p for p in pts if p[2] is not None and p[2] < 3]
    assert not low, low[:5]  # (the sea's surface is 0: no stretch swum)
    assert r.length < 450, r.length  # (the pier's way, about 420 yd; swum round, 335 + the climb out)


# --- 141b: Thunder Bluff's southwest lift -----------------------------------------------------------------------------

def _capitals_lifts():
    """The capitals' lift roads (source 5), Data/Capitals.lua: ((x, y, z) top, (x, y, z) foot)."""
    lines = (ADDON / "Data" / "Capitals.lua").read_text(encoding="utf-8").split("\n")
    out = []
    for i, line in enumerate(lines):
        if "overlays[#overlays + 1] = { capital = \"capitals\"," not in line:
            continue
        n = [int(v) for v in re.search(r"\bn = \{([^}]*)\}", lines[i + 1]).group(1).split(",")]
        nz = [int(v) for v in re.search(r"\bnz = \{([^}]*)\}", lines[i + 2]).group(1).split(",")]
        j = i + 4
        while lines[j].strip().startswith("{"):
            m = re.match(r"\s*\{(\d+),(\d+),(\d+),(\d+),", lines[j])
            if m and m.group(4) == "5":
                a, b = int(m.group(1)), int(m.group(2))
                pa = (n[2 * a - 2], n[2 * a - 1], nz[a - 1])
                pb = (n[2 * b - 2], n[2 * b - 1], nz[b - 1])
                out.append(tuple(sorted((pa, pb), key=lambda p: -p[2])))
            j += 1
    return out


def _near(p, shafts, yd):
    return min(math.dist(p, s) for s in shafts) <= yd


def test_the_southwest_lift_s_cars_go_from_the_mesa_s_top_to_its_foot():
    sw = [(top, foot) for top, foot in _capitals_lifts() if _near(foot[:2], SW_SHAFTS, 60) or _near(top[:2], SW_SHAFTS, 30)]
    assert len(sw) == 2, sw  # (one a car)
    for top, foot in sw:
        assert top[2] > 125 and foot[2] < 80, (top, foot)  # (the mesa's top, 130.5; the foot's ground, 69)
        assert _near(top[:2], SW_SHAFTS, 15), top  # (up top by its own shaft, not the foot's ground road)


def test_the_router_rides_the_southwest_lift_up_and_down(game):
    """Without the grids (the Router's own roads): up from the foot's road and back down by the southwest lift's cars,
    no other step climbing the mesa."""
    lua, ns = game
    R = ns.Router
    st = ns.settings.gps
    st.cityGrid, st.worldGrid = False, False
    ns.WorldGrid.Set(False)
    try:
        for a, b, kind in ((SW_FOOT_ROAD, SW_TOP, R.KIND_LIFT_UP), (SW_TOP, SW_FOOT_ROAD, R.KIND_LIFT_DOWN)):
            R.Reset()
            r = R.Route(a[0], a[1], a[2], b[1], b[2], lua.table(z=a[3], tz=b[3]))
            assert r is not None and not r.noWay
            pts, kinds = _list(r.pts), _list(r.kinds)
            lifts = [(pts[2 * i], pts[2 * i + 1]) for i in range(len(kinds)) if kinds[i] == kind]
            # (the ride by a shaft; the road's foot is the land's road 35 yd off it, as the other car's always was)
            assert lifts and any(_near(p, SW_SHAFTS, 5) for p in lifts), lifts
            assert all(_near(p, SW_SHAFTS, 40) for p in lifts), lifts
            hs = _list(r.zs if r.zs is not None else r.fz)
            for i in range(len(kinds)):
                d = math.dist(pts[2 * i:2 * i + 2], pts[2 * i + 2:2 * i + 4])
                if kinds[i] != kind and d > 1 and type(hs[i]) in (int, float) and type(hs[i + 1]) in (int, float):
                    assert abs(hs[i + 1] - hs[i]) < 30, (i, hs[i], hs[i + 1])  # (the ride's own end at its foot: 0 yd)
    finally:
        st.cityGrid, st.worldGrid = True, True
        ns.WorldGrid.Set(True)
