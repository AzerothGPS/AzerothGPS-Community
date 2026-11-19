"""The road watcher's import of roads edited afterwards in game (Edit Road, 1.3.10, issue #640): an edit ships as its
pieces with their heights, kind and stairs (ns.FloorTracks), and the road it replaced goes out of the data."""

import json

from azerothgps.roads.graph import apply_overrides
from azerothgps.roads.tracks import dropped_times, edit_pieces, floor_tracks, import_tracks, read_tracks, shipped_times

from test_roads import line_graph

SV = """
AzerothGPSDB = {
  ["tracks"] = {
    { ["op"] = "add", ["continent"] = 1, ["time"] = 1800000000, ["drawn"] = true, ["zone"] = "Mulgore",
      ["pts"] = { 10, 0, 30, 0, 50, 0 } },
    { ["op"] = "add", ["continent"] = 1, ["time"] = 1800000100, ["drawn"] = true, ["zone"] = "Mulgore",
      ["kind"] = "bridge", ["replaces"] = 1800000000, ["pts"] = { 10, 0, 30, 0, 50, 0 }, ["zs"] = { 0, 15, 0 } },
    { ["op"] = "add", ["continent"] = 1, ["time"] = 1800000200, ["drawn"] = true, ["zone"] = "Thunder Bluff",
      ["kind"] = "floor", ["replaces"] = 1700000010, ["rpart"] = 1,
      ["pts"] = { 0, 10, 10, 10, 20, 10, 30, 10, 40, 10 }, ["zs"] = { 60, 60, 65, 70, 70 }, ["stairs"] = { 2, 4 } },
    { ["op"] = "add", ["continent"] = 1, ["time"] = 1800000300, ["drawn"] = true, ["zone"] = "Mulgore",
      ["kind"] = "ground", ["pts"] = { 0, 50, 40, 50 } },
    { ["op"] = "add", ["continent"] = 1, ["time"] = 1800000400, ["drawn"] = true, ["kind"] = "spaceship",
      ["replaces"] = true, ["stairs"] = { 3, 9 }, ["pts"] = { 0, 90, 40, 90 } },
  },
}
"""


def walk_doc():
    # a recorded walk the data has already: three pieces (ground, stairs, upstairs)
    feats = []
    for k, (c, zs, stair) in enumerate((([[0, 10], [10, 10]], None, False),
                                        ([[10, 10], [20, 10], [30, 10]], [60.0, 62.0, 64.0], True),
                                        ([[30, 10], [40, 10]], [64.0, 64.0], False))):
        feats.append({"type": "Feature", "geometry": {"type": "LineString", "coordinates": c},
                      "properties": {"op": "add", "source": "recorded", "time": 1700000010, "trim": True,
                                     "recorded": True, **({"part": k} if k else {}), **({"zs": zs} if zs else {}),
                                     **({"stair": True} if stair else {})}})
    return {"type": "FeatureCollection", "features": feats}


def test_an_edit_is_read_with_its_kind_what_it_replaces_and_its_stairs(tmp_path):
    sv = tmp_path / "WTF" / "ACC#1" / "SavedVariables"
    sv.mkdir(parents=True)
    (sv / "AzerothGPS.lua").write_text(SV)
    got = {t["time"]: t for t in read_tracks(tmp_path / "WTF")}
    assert got[1800000100]["kind"] == "bridge" and got[1800000100]["replaces"] == 1800000000
    assert got[1800000100]["rpart"] is None and got[1800000100]["zs"] == [0, 15, 0]
    e2 = got[1800000200]
    assert (e2["replaces"], e2["rpart"], e2["edit_stairs"]) == (1700000010, 1, (2, 4))
    assert [(p["coords"], p["zs"], p["stair"], p["kind"]) for p in edit_pieces(e2)] == [
        ([[0, 10], [10, 10]], [60, 60], False, "floor"),
        ([[10, 10], [20, 10], [30, 10]], [60, 65, 70], True, "stairs"),
        ([[30, 10], [40, 10]], [70, 70], False, "floor")]
    # (what's not well formed left out: a kind not one of them, `replaces` not a time, stairs off its points)
    bad = got[1800000400]
    assert "kind" not in bad and "replaces" not in bad and "edit_stairs" not in bad


def test_the_watcher_ships_an_edit_and_takes_the_road_it_replaced_out(tmp_path, monkeypatch):
    import azerothgps.paths as paths
    from azerothgps.roads.export import roads_lua

    sv = tmp_path / "WTF" / "ACC#1" / "SavedVariables"
    sv.mkdir(parents=True)
    (sv / "AzerothGPS.lua").write_text(SV)
    ov = tmp_path / "overrides"
    ov.mkdir()
    (ov / "roads_1.geojson").write_text(json.dumps(walk_doc()))
    assert import_tracks(tmp_path / "WTF", ov) == 5
    feats = json.loads((ov / "roads_1.geojson").read_text())["features"]
    by = {(f["properties"]["time"], f["properties"].get("part", 0)): f["properties"] for f in feats}
    # the flat road edited into a bridge: out, its time dropped (the addon forgets its copy; never taken in again)
    assert (1800000000, 0) not in by and 1800000000 in dropped_times(ov)
    assert by[(1800000100, 0)]["kind"] == "bridge" and by[(1800000100, 0)]["zs"] == [0, 15, 0]
    # the walk's middle piece replaced by the edit's three; the walk's other pieces stay
    assert (1700000010, 0) in by and (1700000010, 2) in by and (1700000010, 1) not in by
    assert 1700000010 not in dropped_times(ov)
    assert [by[(1800000200, k)].get("kind") for k in range(3)] == ["floor", "stairs", "floor"]
    assert by[(1800000200, 1)]["stair"] is True and by[(1800000200, 1)]["zs"] == [60, 65, 70]
    # a ground road with no heights: the land's, flat
    assert "zs" not in by[(1800000300, 0)] and by[(1800000300, 0)]["kind"] == "ground"
    # again: nothing new, nothing put back
    assert import_tracks(tmp_path / "WTF", ov) == 0
    assert len(json.loads((ov / "roads_1.geojson").read_text())["features"]) == len(feats)
    # shipped: the edits' times and the replaced ones'
    assert {1800000000, 1800000100, 1800000200, 1700000010} <= set(shipped_times(ov))
    fts = floor_tracks(ov)[1]
    assert [(t["time"], t["part"], t["kind"], t["stair"]) for t in fts] == [
        (1700000010, 2, None, False), (1800000100, 0, "bridge", False),
        (1800000200, 0, "floor", False), (1800000200, 1, "stairs", True), (1800000200, 2, "floor", False)]
    monkeypatch.setattr(paths, "RESOURCES", tmp_path)
    text = roads_lua(tmp_path / "no-roads", continents=[1])
    assert 'zs = {60,65,70}, stair = true, part = 1, kind = "stairs" },' in text
    assert 'zs = {0,15,0}, kind = "bridge" },' in text
    # the land's flat build: the ground road, never the replaced one
    g = line_graph(((0, -100), (0, 200)))
    apply_overrides(g, ov / "roads_1.geojson")
    ys = {round(float(p[1])) for e in g.edges.values() for p in e.pts if float(p[0]) > 5}
    assert 50 in ys and 0 not in ys


def test_an_edit_waits_for_nothing_the_walk_it_edits_is_cut_when_it_comes_in(tmp_path):
    # (an edit of a recorded walk not in the data yet: the walk comes in later, its pieces worked out; the piece the
    # edit replaced is left out then)
    sv = tmp_path / "WTF" / "ACC#1" / "SavedVariables"
    sv.mkdir(parents=True)
    (sv / "AzerothGPS.lua").write_text("""
AzerothGPSDB = { ["tracks"] = {
  { ["op"] = "add", ["continent"] = 1, ["time"] = 1700000010, ["drawn"] = true, ["recorded"] = true,
    ["pts"] = { 0, 10, 10, 10, 20, 10, 30, 10, 40, 10 } },
  { ["op"] = "add", ["continent"] = 1, ["time"] = 1800000200, ["drawn"] = true, ["kind"] = "floor",
    ["replaces"] = 1700000010, ["rpart"] = 1, ["pts"] = { 10, 10, 30, 10 }, ["zs"] = { 70, 70 } },
} }
""")
    ov = tmp_path / "overrides"
    assert import_tracks(tmp_path / "WTF", ov) == 1  # (the edit; the walk waits for its heights)

    def walks(t):
        return [{"coords": f["geometry"]["coordinates"], "zs": f["properties"].get("zs"),
                 "stair": f["properties"].get("stair", False)} for f in walk_doc()["features"]]

    assert import_tracks(tmp_path / "WTF", ov, walks=walks) == 1
    parts = sorted((f["properties"]["time"], f["properties"].get("part", 0))
                   for f in json.loads((ov / "roads_1.geojson").read_text())["features"])
    assert parts == [(1700000010, 0), (1700000010, 2), (1800000200, 0)]
