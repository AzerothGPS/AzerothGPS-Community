import json

import numpy as np
import pytest

from azerothgps.roads.graph import RoadGraph, apply_overrides, bridge_gaps, skeleton_to_graph

ident = lambda r, c: (float(r), float(c))  # 1 px = 1 yd, rows = X, cols = Y


def canvas(h=60, w=60):
    return np.zeros((h, w), bool)


def test_plus_sign():
    s = canvas()
    s[30, 5:55] = True
    s[5:55, 30] = True
    g = skeleton_to_graph(s, ident)
    g.contract_degree2()
    deg = g.degree()
    assert sorted(deg.values()) == [1, 1, 1, 1, 4]
    assert len(g.edges) == 4
    assert g.total_length() == pytest.approx(98, abs=3)


def test_straight_line():
    s = canvas()
    s[10, 5:50] = True
    g = skeleton_to_graph(s, ident)
    g.contract_degree2()
    assert len(g.edges) == 1 and len(g.nodes) == 2
    assert g.total_length() == pytest.approx(44, abs=1)


def test_diagonal_staircase_is_one_edge():
    s = canvas()
    for i in range(40):
        s[5 + i, 5 + i] = True
        s[5 + i, 6 + i] = True  # thick staircase like skeletonize can leave
    from skimage.morphology import skeletonize

    g = skeleton_to_graph(skeletonize(s), ident)
    g.contract_degree2()
    g.prune_spurs(5)
    assert len(g.edges) == 1


def test_closed_loop():
    s = canvas()
    s[10, 10:40] = True
    s[40, 10:40] = True
    s[10:41, 10] = True
    s[10:41, 39] = True
    g = skeleton_to_graph(s, ident)
    g.contract_degree2()
    assert len(g.edges) >= 1
    assert g.total_length() == pytest.approx(120, abs=6)


def test_spur_pruning_keeps_main_road():
    s = canvas(80, 80)
    s[40, 5:75] = True  # main road
    s[35:40, 40] = True  # 5-px whisker
    g = skeleton_to_graph(s, ident)
    g.contract_degree2()
    g.prune_spurs(10)
    assert len(g.edges) == 1
    assert g.total_length() == pytest.approx(69, abs=2)


def test_small_components_removed():
    s = canvas(80, 80)
    s[10, 5:75] = True
    s[50, 20:25] = True  # decorative speck
    g = skeleton_to_graph(s, ident)
    g.contract_degree2()
    g.remove_small_components(30)
    assert len(g.edges) == 1


def line_graph(*segments):
    g = RoadGraph()
    for a, b in segments:
        na, nb = g.add_node(a), g.add_node(b)
        g.add_edge(na, nb, np.linspace(a, b, 10))
    return g


def test_bridge_aligned_ends():
    # Road broken by a 40 yd river gap: ends face each other.
    g = line_graph(((0, 0), (0, 100)), ((0, 140), (0, 240)))
    assert bridge_gaps(g) == 1
    g.contract_degree2()
    assert len(g.edges) == 1 and g.total_length() == pytest.approx(240)


def test_no_bridge_for_parallel_roads():
    g = line_graph(((0, 0), (0, 100)), ((30, 0), (30, 100)))
    assert bridge_gaps(g) == 0


def test_t_junction_gap_closed_unless_water():
    g = line_graph(((0, 0), (0, 200)), ((50, 100), (12, 100)))  # stops 12 yd short, heading at the road
    assert bridge_gaps(g) == 1
    assert max(g.degree().values()) == 3
    g2 = line_graph(((0, 0), (0, 200)), ((50, 100), (12, 100)))
    assert bridge_gaps(g2, crosses_water=lambda p, q: True) == 0


def test_overrides(tmp_path):
    g = line_graph(((0, 0), (0, 100)), ((100, 0), (100, 100)))
    doc = {"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {"op": "add"},
         "geometry": {"type": "LineString", "coordinates": [[5, 100], [95, 100]]}},  # link the two ends
        {"type": "Feature", "properties": {"op": "remove"},
         "geometry": {"type": "LineString", "coordinates": [[100, -5], [100, 105]]}},  # drop second road
    ]}
    path = tmp_path / "roads_0.geojson"
    path.write_text(json.dumps(doc))
    stats = apply_overrides(g, path)
    assert stats == {"added": 1, "removed": 1}
    assert any(e.source == "override" for e in g.edges.values())
    assert all(abs(e.pts[:, 0].mean() - 100) > 1 for e in g.edges.values() if e.source == "terrain")


def test_json_roundtrip():
    g = line_graph(((0, 0), (0, 100)))
    g2 = RoadGraph.from_json(json.loads(json.dumps(g.to_json())))
    assert len(g2.edges) == 1 and g2.total_length() == pytest.approx(100)


def test_recorded_track_keeps_only_new_road():
    from azerothgps.roads.graph import off_network_runs

    g = line_graph(((0, 0), (0, 300)))  # existing road along Y at X=0
    # Ride 100 yd along the road, then branch off north for 150 yd.
    track = np.array([[0, y] for y in range(0, 101, 5)] + [[x, 100] for x in range(5, 151, 5)], float)
    runs = off_network_runs(g, track)
    assert len(runs) == 1
    run = runs[0]
    assert run[-1] == pytest.approx([150, 100])
    assert run[0][0] <= 12  # starts at the junction, not back at the road start


def test_trimmed_track_override_joins_network(tmp_path):
    g = line_graph(((0, 0), (0, 300)))
    track = [[0, y] for y in range(0, 101, 5)] + [[x, 100] for x in range(5, 151, 5)]
    doc = {"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {"op": "add", "trim": True},
         "geometry": {"type": "LineString", "coordinates": track}}]}
    path = tmp_path / "o.geojson"
    path.write_text(json.dumps(doc))
    assert apply_overrides(g, path)["added"] == 1
    assert max(g.degree().values()) == 3  # a T junction where the track left the road


def test_import_tracks_from_savedvariables(tmp_path):
    from azerothgps.roads.tracks import import_tracks

    sv = tmp_path / "WTF" / "ACC#1" / "SavedVariables"
    sv.mkdir(parents=True)
    (sv / "AzerothGPS.lua").write_text("""
AzerothGPSDB = {
  ["tracks"] = {
    { ["op"] = "add", ["continent"] = 1, ["zone"] = "Durotar", ["time"] = 1700000000,
      ["pts"] = { -600, -4180, -610, -4175, -620, -4170, -630, -4165 } },
  },
}
""")
    ov = tmp_path / "overrides"
    assert import_tracks(tmp_path / "WTF", ov) == 1
    assert import_tracks(tmp_path / "WTF", ov) == 0  # already imported
    doc = json.loads((ov / "roads_1.geojson").read_text())
    f = doc["features"][0]
    assert f["properties"]["op"] == "add" and f["properties"]["trim"] is True
    assert f["geometry"]["coordinates"][1] == [-610, -4175]


def test_the_road_watcher_leaves_out_what_a_player_imported(tmp_path):
    # (asked 2026-10-06: imports go only into the player's own data, never the addon's) roads, walls and pins taken in
    # with the Import and Share window are marked imported: the watcher ships the roads drawn and the dev tools' shared
    # ones, never those; nor imported pins (pins never ship)
    from azerothgps.pins import saved_pins
    from azerothgps.roads.tracks import import_tracks, read_tracks

    sv = tmp_path / "WTF" / "ACC#1" / "SavedVariables"
    sv.mkdir(parents=True)
    (sv / "AzerothGPS.lua").write_text("""
AzerothGPSDB = {
  ["tracks"] = {
    { ["op"] = "add", ["continent"] = 1, ["zone"] = "Durotar", ["time"] = 1700000000, ["drawn"] = true,
      ["pts"] = { -600, -4180, -610, -4175, -620, -4170 } },
    { ["op"] = "wall", ["continent"] = 1, ["zone"] = "imported", ["time"] = 1700000001, ["drawn"] = true,
      ["imported"] = true, ["pts"] = { -700, -4180, -710, -4175 } },
    { ["op"] = "add", ["continent"] = 1, ["zone"] = "shared", ["time"] = 1700000002, ["drawn"] = true,
      ["shared"] = true, ["pts"] = { -800, -4180, -810, -4175 } },
  },
}
""")
    assert sorted(t["time"] for t in read_tracks(tmp_path / "WTF")) == [1700000000, 1700000002]
    assert import_tracks(tmp_path / "WTF", tmp_path / "overrides") == 2
    pins = {"AzerothGPSDB": {"pins": [dict(level=0, x=1, y=2, time=20, name="Imported", imported=True)]}}
    assert saved_pins(pins, shared_only=True)[0] == []


def test_roads_drawn_with_heights_ship_as_floor_tracks_not_land_roads(tmp_path, monkeypatch):
    # (1.1.6's road tools: a road drawn with a height per point, and stairs) the watcher takes them into the overrides
    # with their heights; the land's flat build leaves them out; the data ships them as they were drawn (Data/Roads.lua's
    # ns.FloorTracks), and the addon puts them on in game on their floors as it does a player's own (Router.WithTracks):
    # once shipped, nothing changes for them
    import azerothgps.paths as paths
    from azerothgps.roads.export import roads_lua
    from azerothgps.roads.tracks import floor_tracks, import_tracks, parse_shared, read_tracks, shipped_times

    sv = tmp_path / "WTF" / "ACC#1" / "SavedVariables"
    sv.mkdir(parents=True)
    (sv / "AzerothGPS.lua").write_text("""
AzerothGPSDB = {
  ["tracks"] = {
    { ["op"] = "add", ["continent"] = 0, ["time"] = 1700000000, ["pts"] = { 1, 2, 30, 2 } },
    { ["op"] = "add", ["continent"] = 0, ["time"] = 1700000001, ["pts"] = { 1, 20, 30, 20 }, ["zs"] = { 41.5, 41.5 } },
    { ["op"] = "add", ["continent"] = 0, ["time"] = 1700000002, ["stair"] = true, ["pts"] = { 1, 40, 9, 40 },
      ["zs"] = { 34.5, 41.5 } },
    { ["op"] = "add", ["continent"] = 0, ["time"] = 1700000003, ["pts"] = { 1, 60, 30, 60 }, ["zs"] = { 34.5 } },
  },
}
""")
    got = {t["time"]: t for t in read_tracks(tmp_path / "WTF")}
    assert got[1700000001]["zs"] == [41.5, 41.5] and "stair" not in got[1700000001]
    assert got[1700000002]["stair"] is True and got[1700000002]["zs"] == [34.5, 41.5]
    assert "zs" not in got[1700000000] and "zs" not in got[1700000003]  # (flat; heights not one a point: left out)
    ov = tmp_path / "overrides"
    assert import_tracks(tmp_path / "WTF", ov) == 4
    fts = floor_tracks(ov)
    assert [(t["time"], t["stair"], t["zs"]) for t in fts[0]] == [(1700000001, False, [41.5, 41.5]),
                                                                  (1700000002, True, [34.5, 41.5])]
    assert {1700000000, 1700000001, 1700000002} <= set(shipped_times(ov))
    # the land's flat build: the flat drawn roads only
    g = line_graph(((0, -50), (0, 100)))
    apply_overrides(g, ov / "roads_0.geojson")
    ys = sorted({round(float(p[1])) for e in g.edges.values() for p in e.pts if float(p[0]) > 0.5})
    assert 2 in ys and 60 in ys and 20 not in ys and 40 not in ys
    # the data: ns.FloorTracks, as drawn
    monkeypatch.setattr(paths, "RESOURCES", tmp_path)
    text = roads_lua(tmp_path / "no-roads", continents=[0])
    assert "ns.FloorTracks = {" in text
    assert '{ op = "add", time = 1700000002, pts = {1,40,9,40}, zs = {34.5,41.5}, stair = true },' in text
    assert "[1700000002]=true" in text  # (shipped: the addon drops the player's copy, the data's goes on)
    # shared lines: their heights read too
    shared = parse_shared("R add 0 5 1.0,2.0 30.0,2.0\nR add 0 6 zs=41.5,41.5 1.0,2.0 30.0,2.0\n"
                          "R stair 0 7 zs=34.5,41.5 1.0,2.0 9.0,2.0\nR stair 0 8 1.0,2.0 9.0,2.0\n"
                          "R add 0 9 zs=41.5 1.0,2.0 30.0,2.0")
    assert [(t["time"], t.get("zs"), t.get("stair"), t["op"]) for t in shared] == [
        (5, None, None, "add"), (6, [41.5, 41.5], None, "add"), (7, [34.5, 41.5], True, "add")]


def test_a_recorded_walk_waits_for_its_heights_then_ships_in_pieces(tmp_path):
    # (1.1.6's Record: a walk saved with what the game said at each point and the player's stairs marks) the watcher
    # never takes it in as a flat land road (one up a building's stairs isn't): it waits until its heights are worked
    # out (roads/recorded.py), then goes in as its pieces: on the ground flat, on a floor with its heights, stairs as stairs
    from azerothgps.roads.tracks import floor_tracks, import_tracks, read_tracks, shipped_times

    sv = tmp_path / "WTF" / "ACC#1" / "SavedVariables"
    sv.mkdir(parents=True)
    (sv / "AzerothGPS.lua").write_text("""
AzerothGPSDB = {
  ["tracks"] = {
    { ["op"] = "add", ["continent"] = 0, ["time"] = 1700000010, ["drawn"] = true, ["recorded"] = true,
      ["zone"] = "Tirisfal Glades", ["pts"] = { 0, 0, 10, 0, 20, 0, 24, 0, 28, 0, 30, 0 },
      ["rec"] = { ["ind"] = "001111", ["ts"] = "0,14,14,6,6,3", ["zt"] = { 1, "Brill", 3, "Gallows' End Tavern" },
                  ["pk"] = { 4, 41.5, 6, false } },
      ["stairs"] = { 3, 5 } },
  },
}
""")
    (t,) = read_tracks(tmp_path / "WTF")
    assert t["recorded"] and t["ind"] == "001111" and t["stairs"] == [(3, 5)]
    assert t["zt"] == [(1, "Brill"), (3, "Gallows' End Tavern")]
    assert t["pk"] == [(4, 41.5), (6, None)]  # (the floor picked from point 4, none from 6)
    ov = tmp_path / "overrides"
    assert import_tracks(tmp_path / "WTF", ov) == 0  # (no heights yet: it waits)
    assert import_tracks(tmp_path / "WTF", ov, walks=lambda t: None) == 0  # (couldn't work them out: still waits)

    def walks(t):
        c = t["coords"]
        return [{"coords": c[:3], "zs": None, "stair": False},
                {"coords": c[2:5], "zs": [62.0, 64.5, 67.0], "stair": True},
                {"coords": c[4:], "zs": [67.0, 67.0], "stair": False}]

    assert import_tracks(tmp_path / "WTF", ov, walks=walks) == 1
    assert import_tracks(tmp_path / "WTF", ov, walks=walks) == 0  # (in: not again)
    feats = json.loads((ov / "roads_0.geojson").read_text())["features"]
    assert [f["properties"].get("part") for f in feats] == [None, 1, 2]
    assert all(f["properties"]["time"] == 1700000010 and f["properties"]["recorded"] for f in feats)
    assert "zs" not in feats[0]["properties"]  # (on the ground: the land's flat build takes it)
    fts = floor_tracks(ov)[0]
    assert [(f["stair"], f["zs"]) for f in fts] == [(True, [62.0, 64.5, 67.0]), (False, [67.0, 67.0])]
    assert 1700000010 in set(shipped_times(ov))  # (the player's copy goes once the data has it)


def test_drawn_roads_go_on_in_order_as_in_game(tmp_path):
    g = line_graph(((0, 0), (0, 300)))
    rec = {"source": "recorded", "trim": True}
    doc = {"type": "FeatureCollection", "features": [
        # stops 18 yd short of the road: joined to it anyway
        {"type": "Feature", "properties": {"op": "add", "time": 1, **rec},
         "geometry": {"type": "LineString", "coordinates": [[200, 150], [100, 150], [18, 150]]}},
        # drawn again, a little off: it replaces the first, not a second road beside it
        {"type": "Feature", "properties": {"op": "add", "time": 2, **rec},
         "geometry": {"type": "LineString", "coordinates": [[204, 146], [100, 155], [3, 152]]}},
        # erased across the road near its start: that stretch is cut out, the rest stays
        {"type": "Feature", "properties": {"op": "remove", "time": 3, **rec},
         "geometry": {"type": "LineString", "coordinates": [[-20, 40], [20, 40]]}},
    ]}
    path = tmp_path / "roads_0.geojson"
    path.write_text(json.dumps(doc))
    apply_overrides(g, path)
    ov = [e for e in g.edges.values() if e.source == "override"]  # (the second replaced the first)
    assert len(ov) == 1 and min(abs(e[0]) for e in ov[0].pts) < 0.01  # on the road
    for e in g.edges.values():
        assert not any(abs(x) < 5 and abs(y - 40) < 5 for x, y in e.pts)
    assert g.total_length() > 300 - 30 + 190


def two_floors():
    """A road at height 0 and one 3 yd beside it at height 20 (a walkway over it), each node's height."""
    g = line_graph(((0, 0), (0, 100)), ((3, 0), (3, 100)))
    nz = {0: 0.0, 1: 0.0, 2: 20.0, 3: 20.0}
    return g, nz


def test_a_drawn_edit_with_a_floor_changes_that_floors_roads_only(tmp_path):
    # (as the addon's Router.WithTracks: Undercity's floors over floors, cities.py)
    from azerothgps.roads.graph import LayerFloors

    rec = {"source": "recorded", "trim": True}
    erase = {"type": "Feature", "properties": {"op": "remove", "time": 1, **rec},
             "geometry": {"type": "LineString", "coordinates": [[-5, 50], [8, 50]]}}

    def left(z):
        g, nz = two_floors()
        f = json.loads(json.dumps(erase))
        if z is not None:
            f["properties"]["z"] = z
        path = tmp_path / "roads_10001.geojson"
        path.write_text(json.dumps({"type": "FeatureCollection", "features": [f]}))
        apply_overrides(g, path, city=True, floors=lambda p: LayerFloors(g, nz, p["z"]) if "z" in p else None)
        from azerothgps.roads.graph import _dist_to_polyline
        cut = {x for x in (0, 3) if not any(_dist_to_polyline(np.array([x, 50.0]), e.pts) < 0.5 for e in g.edges.values())}
        return cut, nz

    assert left(None)[0] == {0, 3}  # (no floor: both, as before)
    cut, nz = left(1.0)
    assert cut == {0}  # (down on the road: the walkway over it stays)
    assert all(abs(nz[n]) < 0.01 for n in nz if n > 3)  # (the cut ends at the road's height)
    assert left(19.0)[0] == {3}


def test_a_drawn_road_with_a_floor_joins_that_floor(tmp_path):
    from azerothgps.roads.graph import LayerFloors

    g, nz = two_floors()
    path = tmp_path / "roads_10001.geojson"
    path.write_text(json.dumps({"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {"op": "add", "time": 1, "source": "recorded", "trim": True, "z": 19.0},
         "geometry": {"type": "LineString", "coordinates": [[1.5, 40], [40, 40], [40, 80]]}}]}))
    apply_overrides(g, path, city=True, floors=lambda p: LayerFloors(g, nz, p["z"]))
    ov = [e for e in g.edges.values() if e.source == "override"]
    assert ov
    start = next(n for e in ov for n in (e.a, e.b) if np.hypot(*(g.nodes[n] - (1.5, 40))) < 3)
    assert abs(g.nodes[start][0] - 3) < 0.01 and nz[start] == 20.0  # (onto the walkway, at its height)


def test_walls_and_wall_erasers_on_their_floors(tmp_path):
    from azerothgps.roads.tracks import walls

    rec = {"source": "recorded"}
    line = [[0, 0], [0, 20]]
    (tmp_path / "roads_10001.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {"op": "wall", "time": 1, "z": -62.0, **rec}, "geometry": {"type": "LineString", "coordinates": line}},
        {"type": "Feature", "properties": {"op": "wall", "time": 2, "z": -43.0, **rec}, "geometry": {"type": "LineString", "coordinates": line}},
        {"type": "Feature", "properties": {"op": "unwall", "time": 3, "z": -44.0, **rec}, "geometry": {"type": "LineString", "coordinates": line}},
    ]}))
    ws = walls(tmp_path)[10001]
    assert len(ws) == 1 and ws[0].z == -62.0  # (the eraser was up on the other floor's)


def test_an_erasure_down_in_a_cave_leaves_the_land_roads_over_it(tmp_path):
    # (roads.build.finish_continent: a `down` erasure is the cave's or the floor under a capital's)
    g = line_graph(((0, 0), (0, 100)))
    path = tmp_path / "roads_1.geojson"
    path.write_text(json.dumps({"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {"op": "remove", "time": 1, "source": "recorded", "down": True, "z": 5.0},
         "geometry": {"type": "LineString", "coordinates": [[-5, 50], [5, 50]]}}]}))
    apply_overrides(g, path, keep=lambda p: not (p.get("down") and p.get("op") == "remove"))
    assert len(g.edges) == 1


def test_roads_drawn_and_erased_down_in_a_cave_go_on_its_roads(tmp_path, monkeypatch):
    # (caves.drawn_fixes: the addon puts them on the cave's roads until they ship, then drops the track
    # (ns.RoadTracksIn), so Data/Caves.lua must have them: else an erased cave road came back, and a drawn
    # one was a land road only)
    import re
    from types import SimpleNamespace

    from azerothgps import caves, paths
    from azerothgps.roads import terrain

    X0, Y0, N = 1000, 2000, 100  # (the cave's grid: a yard a cell, rows along X, columns along Y)
    ground = np.zeros((N, N), bool)
    ground[75:, :] = True  # (the ground at its mouth)
    ground[20:41, :6] = True  # (... and at a side opening)
    overlay = np.where(ground, caves.CONT, caves.OPEN).astype(np.uint8)
    overlay[10:30, 55:95] = caves.FLOOR_UNDER  # (a hill over it there)
    g = RoadGraph()
    a, j, m1, b = (g.add_node(p) for p in ((1010, 2050), (1030, 2050), (1085, 2050), (1030, 2003)))
    for p, q in ((a, j), (j, m1), (j, b)):  # (its tunnel to the mouth, and a side tunnel to the opening)
        g.add_edge(p, q, np.linspace(g.nodes[p], g.nodes[q], 10))
    u = {"graph": g, "H": N, "W": N, "footprint": ~ground, "walk": np.ones((N, N), bool), "ground": ground,
         "overlay": overlay, "world_to_px": lambda x, y: (int(x - X0), int(y - Y0)), "stair_z": {},
         "is_open": lambda x, y: True, "height_at": lambda x, y: 0.0, "tx0": 30.0, "ty0": 30.0}

    class Finder:  # (the ways out: on to the land's road just outside)
        def __init__(self, grid, roads):
            pass

        def walk(self, p, inside, blocked_max=None):
            return 10.0, [p, (p[0] + 10, p[1]) if p[0] > 1080 else (p[0], p[1] - 8)]

    place = SimpleNamespace(uid=7, x=1040.0, y=2050.0)
    monkeypatch.setattr(caves, "Ground", lambda cd, cont: None)
    monkeypatch.setattr(caves, "shipped_roads", lambda cont: line_graph(((1095, 1900), (1095, 2200))))
    monkeypatch.setattr(terrain, "continent_grid", lambda cd, cont, log=None: {
        "cells": np.zeros((4, 4), np.uint8), "tileX0": 0, "tileY0": 0, "cellYd": 4.0})
    monkeypatch.setattr(caves, "RoadFinder", Finder)
    monkeypatch.setattr(caves, "find_caves", lambda cd, cont: [(place, "world/wmo/dungeon/md_mountaincave/t.wmo", "Test Cave")])
    monkeypatch.setattr(caves, "build_cave", lambda *a, **k: u)
    monkeypatch.setattr(paths, "RESOURCES", tmp_path)
    rec = {"source": "recorded", "trim": True, "z": 40.0, "indoors": True}

    def feat(op, coords, **props):
        return {"type": "Feature", "properties": {"op": op, **rec, **props},
                "geometry": {"type": "LineString", "coordinates": coords}}

    (tmp_path / "overrides").mkdir()
    (tmp_path / "overrides" / "roads_1.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": [
        feat("remove", [[1025, 2008], [1035, 2008]], down=True),  # the side tunnel and its opening's way out
        feat("add", [[1050, 2052], [1050, 2066], [1050, 2080]], down=True),  # a tunnel off the main one
        feat("add", [[1020, 2060], [1020, 2075], [1020, 2090]], indoors=False),  # up on the hill: the land's
        feat("add", [[1090, 2010], [1090, 2025], [1090, 2040]], down=True),  # over the ground outside: not its
    ]}))
    text = caves.caves_lua(SimpleNamespace(casc=SimpleNamespace(version="test")), continents=(1,),
                           log=lambda *a: None, data_dir=tmp_path)

    def near(x, y, yd):
        from azerothgps.roads.graph import _dist_to_polyline

        return any(_dist_to_polyline(np.array([x, y], float), e.pts) <= yd for e in g.edges.values())

    drawn = [e for e in g.edges.values() if e.source == "override"]
    assert len(drawn) == 1 and {tuple(np.round(g.nodes[n])) for n in (drawn[0].a, drawn[0].b)} == {(1050, 2050), (1050, 2080)}
    assert g.degree()[next(n for n in g.nodes if tuple(np.round(g.nodes[n])) == (1050, 2050))] == 3  # (joined on)
    assert not near(1030, 2008, 5) and b not in g.nodes  # (erased, the opening's way out too)
    assert near(1030, 2035, 1)  # (the rest of the side tunnel stays)
    assert not near(1020, 2075, 3) and not near(1090, 2025, 3)
    assert [tuple(q) for _, q in u["joins"]] == [(1095, 2050)] and u["mouths"] == [m1]
    # (as written: the joins and the gap links' nodes are nodes that are there)
    nodes = [float(v) for v in re.search(r"^  n = \{([^}]*)\},$", text, re.M).group(1).split(",")]
    xy = list(zip(nodes[::2], nodes[1::2]))
    assert (1050, 2080) in xy and (1030, 2003) not in xy and (1030, 1995) not in xy

    def listed(key):
        return [xy[int(i) - 1] for i in re.search(r"^  %s = \{([^}]*)\},$" % key, text, re.M).group(1).split(",") if i]

    assert listed("joins") == [(1095, 2050)]
    assert sorted(listed("bridge")) == [(1085, 2050), (1095, 2050)]


def test_shipped_times_list_the_drawn_roads_in_the_overrides(tmp_path):
    from azerothgps.roads.tracks import shipped_times

    (tmp_path / "roads_0.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {"op": "add", "source": "recorded", "time": 5},
         "geometry": {"type": "LineString", "coordinates": [[0, 0], [1, 1]]}},
        {"type": "Feature", "properties": {"op": "add"},
         "geometry": {"type": "LineString", "coordinates": [[0, 0], [1, 1]]}}]}))
    assert shipped_times(tmp_path) == [5]


def test_despeckle_closes_ridge_gaps_and_fills_pockets():
    from azerothgps.roads.terrain import MIN_OPEN, despeckle

    cells = np.zeros((120, 120), np.uint8)
    cells[:, 59:62] = 2  # a ridge across the map ...
    cells[50, 59:62] = 0  # ... with a one-cell gap through it
    cells[10:24, 10:24] = 2  # a mountain ...
    cells[14:20, 14:20] = 0  # ... with a small flat top
    out = despeckle(cells)
    assert out[50, 60] == 2  # the gap is closed
    assert (out[14:20, 14:20] == 2).all()  # the unreachable top is blocked
    assert out[100, 30] == 0 and out[100, 90] == 0  # open ground on both sides stays open
    assert 36 < MIN_OPEN


def test_a_drawn_erase_loop_cuts_the_roads_inside(tmp_path):
    import math as m
    g = line_graph(((0, 0), (0, 300)))
    loop = [[40 * m.cos(k * m.pi / 6), 150 + 40 * m.sin(k * m.pi / 6)] for k in range(13)]
    doc = {"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {"op": "remove", "source": "recorded", "time": 1, "area": True},
         "geometry": {"type": "LineString", "coordinates": loop}}]}
    path = tmp_path / "roads_0.geojson"
    path.write_text(json.dumps(doc))
    apply_overrides(g, path)
    assert len(g.edges) == 2
    assert all(abs(y - 150) >= 38 for e in g.edges.values() for _, y in e.pts)


def test_import_tracks_takes_only_what_its_filter_lets_through(tmp_path):
    # (a test client's saved files, 2026-10-08: its recorded walks only, its test runs' strokes left where they
    # are, not marked imported, so a later import without the filter could still take them)
    from azerothgps.roads.tracks import import_tracks

    sv = tmp_path / "WTF" / "ACC#1" / "SavedVariables"
    sv.mkdir(parents=True)
    (sv / "AzerothGPS.lua").write_text("""
AzerothGPSDB = {
  ["tracks"] = {
    { ["op"] = "add", ["continent"] = 1, ["zone"] = "Durotar", ["time"] = 1700000000, ["drawn"] = true,
      ["pts"] = { -600, -4180, -610, -4175, -620, -4170 } },
    { ["op"] = "add", ["continent"] = 1, ["zone"] = "Durotar", ["time"] = 1700000005, ["drawn"] = true,
      ["recorded"] = true, ["pts"] = { -700, -4180, -710, -4175, -720, -4170 } },
  },
}
""")
    ov = tmp_path / "overrides"
    walks = lambda t: [{"coords": t["coords"]}]
    assert import_tracks(tmp_path / "WTF", ov, walks=walks, only=lambda t: bool(t.get("recorded"))) == 1
    doc = json.loads((ov / "roads_1.geojson").read_text())
    assert [f["properties"]["time"] for f in doc["features"]] == [1700000005]
    assert import_tracks(tmp_path / "WTF", ov, walks=walks) == 1  # (the stroke, still there)
