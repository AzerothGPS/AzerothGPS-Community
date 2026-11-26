"""bake8: the grids reach every shipped stop (Kooki3z 2026-11-23: "imo fall back can't be trusted and should identify
where that would be needed and just correct it"). worldcoverage.py walks to each stop on the grids alone from starts
round it (`agps world-grid coverage`: all of them, on the bake's PC); here the stops whose floor the data hasn't (or
hasn't reached on foot) and a sample of the rest, with the reviewed exceptions (worldcoverage.EXCEPTIONS: no way on
foot there at all) apart."""

from __future__ import annotations

import random

import pytest

pytest.importorskip("lupa.lua51")

from azerothgps import worldcoverage as WC  # noqa: E402


@pytest.fixture(scope="module")
def game():
    lua, ns = WC._game()
    yield lua, ns
    ns.settings.gps.worldGrid = False
    ns.settings.gps.cityGrid = False


def _why(row):
    return [i["kind"] for i in row["issues"]]


def test_every_stop_whose_floor_the_grid_lacks_is_still_walked_to_or_a_reviewed_exception(game):
    # (an NPC on a counter, a step the cell's middle hasn't: its neighbors' floor is taken, WG.Ends; one cut off for good
    # is in the exceptions with why)
    lua, ns = game
    bad = []
    for d in WC.floor_gaps(lua, ns):
        if WC.exception_key(d) in WC.EXCEPTIONS or WC.exception_key(d) in WC.KNOWN_GAPS:
            continue
        row = WC.check_world(lua, ns, d)
        if WC.failed(row):
            bad.append((d["name"], d["x"], d["y"], d["z"], d["gap"], _why(row)))
    assert bad == []


def test_a_sample_of_the_shipped_stops_is_walked_to_on_the_grids(game):
    lua, ns = game
    CG = ns.CityGrid
    rnd = random.Random(8)
    stops = WC.stops(ns)
    rnd.shuffle(stops)
    bad, n = [], 0
    for d in stops:
        if n >= 120:
            break
        if WC.exception_key(d) in WC.EXCEPTIONS or WC.exception_key(d) in WC.KNOWN_GAPS                 or ns.WorldGrid.NotMeshed(d["cont"], d["x"], d["y"]):
            continue
        name = CG.CityFor(d["cont"], d["x"], d["y"]) or CG.GridCityAt(d["cont"], d["x"], d["y"])
        if name:
            continue  # (the city grids': the sweep's, `agps world-grid coverage`)
        n += 1
        row = WC.check_world(lua, ns, d)
        if WC.failed(row):
            bad.append((d["name"], d["x"], d["y"], d["z"], _why(row)))
    assert bad == []


@pytest.mark.parametrize("which", ["EXCEPTIONS", "KNOWN_GAPS"])
def test_the_listed_stops_are_still_out_of_reach_each_with_why(game, which):
    # (a stop the bake comes to cover leaves its list: the lists only shrink; the reviewed exceptions stay short)
    lua, ns = game
    listed = getattr(WC, which)
    if which == "EXCEPTIONS":
        assert len(listed) <= 25
    by_key = {WC.exception_key(d): d for d in WC.stops(ns)}
    reached = []
    for key, why in listed.items():
        assert why and len(why) > 10, key
        d = by_key.get(key)
        assert d is not None, f"{key}: no such stop now"
        nm = ns.CityGrid.CityFor(d["cont"], d["x"], d["y"]) or ns.CityGrid.GridCityAt(d["cont"], d["x"], d["y"])
        if nm:
            continue  # (the city grids': the sweep's)
        if not WC.failed(WC.check_world(lua, ns, d)):
            reached.append(key)
    assert reached == [], "reached now: take them off the list"


def test_the_sweep_s_starts_are_on_reached_ground_on_the_stop_s_side_of_the_walls(game):
    # (a start a town's palisade parts from its cell's floor crossed the wall on the walk's first step, Hammerfall's)
    lua, ns = game
    WG, P = ns.WorldGrid, ns.Passability
    d = {"kind": "npc", "name": "Innkeeper Adegwa", "cont": 0, "x": -912.4, "y": -3524.9, "z": 72.8}
    c = WG.Cont(0)
    starts = WC.starts_for(ns, c, d)
    assert starts
    for s in starts:
        land = [f for f in WC._surfaces(ns, c, s["x"], s["y"]) if not WC._swim(f)]
        assert len(land) == 1 and WC._reach(land[0])
        assert not P.CrossesWall(0, s["x"], s["y"], float(land[0].x), float(land[0].y))


@pytest.mark.parametrize("side", ["H", "A"])
def test_mulgore_s_plain_from_skywatcher_plateau_the_whole_addon_walks_it_on_the_grid(game, side):
    # (Kooki3z's screenshots 2026-11-23: the route shown went round by the Barrens and through Thunder Bluff, the
    # Router's own; with world routing on the trip is the grid's walk down the plain, ride check and all)
    import math

    from azerothgps import undergroundsweep as U
    lua, ns = game
    d = {"kind": "npc", "name": "stop", "side": side, "cont": 1, "x": -800.0, "y": -431.0, "z": None, "base": 1}
    row = U.route_one(lua, ns, d, {"start": "sky", "x": -472.0, "y": 245.0})
    assert row.get("yd") and row["yd"] <= 1.32 * math.dist((-472.0, 245.0), (-800.0, -431.0)), row
    r = ns.Nav.route
    walks = [r.parts[i] for i in range(1, len(r.parts) + 1) if r.parts[i].pts and len(r.parts[i].pts) >= 4]
    assert len(walks) == 1  # (no ride)
    p = walks[0].pts
    assert min(p[i] for i in range(1, len(p) + 1, 2)) > -900  # (never by Thunder Bluff's mesas, south of the stop)


@pytest.mark.parametrize("name", ["Archmage Tervosh", "Ian Strom", "Jadenvis Seawatcher"])
def test_a_stop_up_a_building_is_walked_to_on_its_floor_not_its_foot(game, name):
    # (bake9's sweep: the walk by road ground longer than WG.ROAD_DETOUR_MAX times the line was searched again with no
    # road preference, and that plain walk ended at another of the goals, the building's foot (Tervosh up Jaina's tower
    # in Theramore at 37.5 for 65, Ian Strom in Booty Bay at 0 for 22, Jadenvis at 4.5 for 19), and was taken as
    # shorter. The plain walk is taken only to the same floor)
    lua, ns = game
    d = [d for d in WC.stops(ns) if d["name"] == name]
    assert len(d) == 1
    row = WC.check_world(lua, ns, d[0])
    assert not WC.failed(row), _why(row)
