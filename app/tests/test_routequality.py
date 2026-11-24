"""route-quality's comparison of two versions' weighed routes (`routequality.compare`) and its older files."""

from azerothgps import routequality as rq


def _row(k, secs, rides=(), error=None):
    row = {"k": k, "trip": f"trip {k}", "secs": secs, "rides": list(rides), "from": [0, 0], "to": [1, 1], "cont": 0}
    if error:
        row["error"] = error
    return row


def test_compare_sorts_trips_into_same_better_worse_found_and_lost():
    before = [_row(1, 1000), _row(2, 1000), _row(3, 1000), _row(4, None), _row(5, 900), _row(6, 500), _row(7, None),
              _row(8, 100, error="boom")]
    after = [_row(1, 1005), _row(2, 700, ["flight"]), _row(3, 1400), _row(4, 800), _row(5, None), _row(6, 400),
             _row(7, None), _row(8, 100)]
    res = rq.compare(before, after)
    # (under NOISE_S apart: the same; no way both times: the same)
    assert res["same"] == 2
    assert [r["trip"] for r in res["better"]] == ["trip 2", "trip 6"]  # (the biggest gain first)
    assert [r["trip"] for r in res["worse"]] == ["trip 3"]
    assert [r["trip"] for r in res["found"]] == ["trip 4"]
    assert [r["trip"] for r in res["lost"]] == ["trip 5"]
    assert [r["trip"] for r in res["errors"]] == ["trip 8"]
    assert res["better"][0]["rides_after"] == ["flight"]


ROADS = """ns.Roads = {
  -- build 1, 3 nodes, 2 edges
  [0] = {
    n = {0,0,10,0,20,0},
    e = {
      {1,2,10,0,0,0,10,0},
    },
  },
  [1] = {
    n = {0,0,0,100,0,200},
    e = {
      {1,2,100,2,0,0,0,50,0,100},
      {2,3,100,0,0,100,0,200},
    },
  },
}
ns.Walls = {
  [1] = {
    {1,2,3,4},
  },
}
"""


def test_road_lines_are_ns_roads_edges_by_their_points_per_continent():
    lines = rq.road_lines(ROADS)
    assert lines == {0: {(0, 0, 10, 0)}, 1: {(0, 0, 0, 50, 0, 100), (0, 100, 0, 200)}}  # (no wall)
    # (the same road under other node numbers is the same road)
    assert rq.road_lines(ROADS.replace("{1,2,100,2,", "{7,9,100,2,")) == lines


def test_road_lines_reads_every_edge_of_the_shipped_roads():
    import re

    from azerothgps.paths import ADDON_DIR

    text = (ADDON_DIR / "Data" / "Roads.lua").read_text(encoding="utf-8")
    counts = [int(n) for n in re.findall(r"^  -- build .*, (\d+) edges$", text, re.M)]
    lines = rq.road_lines(text)
    assert sorted(lines) == [0, 1, 2991] and len(counts) == 3
    # (an edge drawn twice is one road here: at most the header's count, and nearly all of it)
    for cont, n in zip((0, 1, 2991), counts):
        assert 0.95 * n <= len(lines[cont]) <= n


CAVES = """ns.Caves[0] = {
}
do -- the caves' roads (the format of Data/Roads.lua)
  local overlays = ns.RoadOverlays[0] or {}
  ns.RoadOverlays[0] = overlays
  overlays[#overlays + 1] = { cave = true,
  n = {10,20,13,16,40,40},
  e = {
    {1,2,5,0,"W2VuW1W4"},
    {2,3,40,0,0,0,13,16,40,40},
  },
  joins = {1},
  nz = {0,0,0},
  }
end
do
  local overlays = ns.RoadOverlays[1] or {}
  ns.RoadOverlays[1] = overlays
  overlays[#overlays + 1] = { cave = true,
  n = {0,0,0,5},
  e = {
    {1,2,5,0,"W0W5"},
  },
  }
end
"""


def test_cave_road_lines_unpack_the_caves_roads_per_continent():
    # #349: Data/Caves.lua's roads are packed (caves.pack_points: from node a, each point moved by whole yards)
    from azerothgps.caves import pack_points

    assert pack_points([(10, 20), (12, 12), (13, 16)]) == "W2VuW1W4"
    lines = rq.cave_road_lines(CAVES)
    assert lines == {0: {(10, 20, 12, 12, 13, 16), (0, 0, 13, 16, 40, 40)}, 1: {(0, 0, 0, 5)}}


def test_cave_road_lines_reads_every_road_of_the_shipped_caves():
    import re

    from azerothgps.paths import ADDON_DIR

    text = (ADDON_DIR / "Data" / "Caves.lua").read_text(encoding="utf-8")
    edges = len(re.findall(r"^\s*\{\d+,\d+,[\d.]+,\d+,", text, re.M))
    lines = rq.cave_road_lines(text)
    assert sorted(lines) == [0, 1]
    assert 0.99 * edges <= sum(len(v) for v in lines.values()) <= edges


def test_changed_roads_counts_the_caves_roads_too(monkeypatch):
    # #349: PR #332 rebuilt the stacked caves' roads in Data/Caves.lua; a trip a little slower along them is redrawn
    old_caves = CAVES.replace('"W2VuW1W4"', '"W3Vy"')  # (the same road, before: straight from (10, 20) to (13, 16))
    texts = {(rq.ROADS_FILE, "ref"): ROADS, (rq.ROADS_FILE, None): ROADS,
             (rq.CAVES_FILE, "ref"): old_caves, (rq.CAVES_FILE, None): CAVES}
    monkeypatch.setattr(rq, "_lines_at", lambda ref, path, read: read(texts[(path, ref)]))
    assert rq.changed_roads("ref") == {0: {(10, 20, 13, 16), (10, 20, 12, 12, 13, 16)}}


def test_a_cave_road_kept_but_joined_to_other_roads_is_changed():
    # #349: the Slag Pit's south mouth's 438 yd road, the same yard for yard, led into a dead end of 3 nodes before PR
    # #332's floors and into the pit after; a road whose ends meet the same roads in both is unchanged
    kept, dead_end, floor = (0.0, 0.0, 0.0, 400.0), (0.0, 400.0, 10.0, 400.0), (0.0, 400.0, 0.0, 450.0, 50.0, 450.0)
    far = (900.0, 900.0, 950.0, 900.0)
    assert rq.rejoined({kept, dead_end, far}, {kept, dead_end, floor, far}) == {kept, dead_end}
    assert rq.rejoined({kept, dead_end, far}, {kept, dead_end, far}) == set()


def _pts(*xy, cont=1):
    return [[cont, x, y] for x, y in xy]


def test_a_trip_slower_only_on_redrawn_roads_is_redrawn_not_worse():
    # Stonetalon: the road from (0,0) to (0,100) redrawn with a bend, 48 yd longer; the rest the same
    changed = {1: {(0.0, 0.0, 0.0, 50.0, 0.0, 100.0), (0.0, 0.0, 24.0, 50.0, 0.0, 100.0)}}
    straight = _pts((0, -50), (0, 0), (0, 50), (0, 100), (0, 200))
    bent = _pts((0, -50), (0, 0), (12, 25), (24, 50), (0, 100), (0, 200))
    detour = _pts((0, -50), (0, 0), (-300, 50), (0, 100), (0, 200))  # (off the redrawn road: a real detour)

    def trips(after_pts, rides_after=()):
        before = [{**_row(1, 1000), "pts": straight}]
        return before, [{**_row(1, 1030, rides_after), "pts": after_pts}]

    res = rq.compare(*trips(bent), changed)
    assert [r["trip"] for r in res["redrawn"]] == ["trip 1"] and not res["worse"]
    for after, rides, ch in ((detour, (), changed), (bent, ("flight",), changed), (bent, (), {}), (bent, (), None),
                             (bent, (), {0: changed[1]})):  # (another continent's roads changed)
        res = rq.compare(*trips(after, rides), ch)
        assert [r["trip"] for r in res["worse"]] == ["trip 1"] and not res["redrawn"]


def test_a_trip_a_little_slower_mostly_along_new_roads_is_redrawn_not_worse():
    # Desolace: a new road the router takes over the open ground it crossed before, joined off-road
    # at its ends; 13 and 34 s slower. A short trip may be up to a minute slower (Ashenvale: 735 s to
    # 775 s). A bigger slowdown, or a stretch mostly off the new roads, is still worse.
    changed = {1: {(0.0, 100.0, 0.0, 400.0)}}
    straight = _pts((0, 0), (0, 50), (100, 250), (0, 450), (0, 500))
    along = _pts((0, 0), (0, 50), (0, 100), (0, 400), (0, 450), (0, 500))  # (on to the new road 50 yd off-road, off again)
    away = _pts((0, 0), (0, 50), (-200, 100), (0, 120), (0, 140), (-200, 400), (0, 450), (0, 500))  # (20 of 960 yd)

    def compare(after_pts, after_secs, rides_after=(), before_secs=1000):
        before = [{**_row(1, before_secs), "pts": straight}]
        return rq.compare(before, [{**_row(1, after_secs, rides_after), "pts": after_pts}], changed)

    assert rq.share_along_changed_roads(straight, along, changed) == 0.75  # (300 of its 400 yd)
    for secs, before_secs in ((1034, 1000), (775, 735), (1060, 1000)):
        res = compare(along, secs, before_secs=before_secs)
        assert [r["trip"] for r in res["redrawn"]] == ["trip 1"] and not res["worse"]
    for after, secs, rides, before_secs in ((along, 1100, (), 1000), (along, 800, (), 735), (away, 1034, (), 1000),
                                            (along, 1034, ("flight",), 1000), (away, 775, (), 735)):
        res = compare(after, secs, rides, before_secs)
        assert [r["trip"] for r in res["worse"]] == ["trip 1"] and not res["redrawn"]


def test_a_trip_slower_by_the_yards_of_a_new_road_taken_over_open_ground_is_redrawn_not_worse():
    # Loch Modan, #359: a player's road from Thelsamar toward the Badlands, taken where the older routes walked open
    # ground from Kargath (the router keeps to the roads unless they're about twice as long); the stretch 1.22 times as
    # long, the trips 6 and 7.5% slower. A stretch more than ALONG_STRETCH times as long, a trip slower by a greater
    # share than its stretch grew, or one mostly off the new roads is still worse.
    changed = {1: {(-60.0, 100.0, -60.0, 400.0)}}
    straight = _pts((0, 0), (0, 50), (60, 250), (0, 450), (0, 500))  # (the stretch 418 yd)
    along = _pts((0, 0), (0, 50), (-60, 100), (-60, 400), (0, 450), (0, 500))  # (on to the new road and off: 456 yd)
    far = _pts((0, 0), (0, 50), (-150, 60), (-60, 100), (-60, 400), (-150, 440), (0, 450), (0, 500))  # (798 yd)
    away = _pts((0, 0), (0, 50), (-200, 100), (-200, 400), (0, 450), (0, 500))  # (beside it: none of 712 yd along it)
    old_yd, new_yd = rq.stretch_yards(straight, along)
    assert round(old_yd) == 418 and round(new_yd) == 456 and new_yd <= old_yd * rq.ALONG_STRETCH
    assert rq.share_along_changed_roads(straight, far, changed) >= rq.ALONG_SHARE

    def compare(after_pts, after_secs):
        before = [{**_row(1, 1000), "pts": straight}]
        return rq.compare(before, [{**_row(1, after_secs), "pts": after_pts}], changed)

    res = compare(along, 1075)  # (past ALONG_MAX, under the stretch's 9%)
    assert [r["trip"] for r in res["redrawn"]] == ["trip 1"] and not res["worse"]
    for after, secs in ((along, 1100), (far, 1075), (away, 1075)):
        res = compare(after, secs)
        assert [r["trip"] for r in res["worse"]] == ["trip 1"] and not res["redrawn"]


def test_a_trip_onto_the_roads_at_a_new_roads_end_is_redrawn_not_worse():
    # Wellspring Lake, AzerothGPS#424 a player's road whose loose end is a nearer way onto the
    # roads; the trip walks to it, takes the join to the old road and follows that, none of it along the new road:
    # 700 yd to 942, 690 s to 716. Past the bounds, or at a changed road's end the older route passed too, it's worse.
    changed = {1: {(10322.0, 1596.0, 10663.0, 1862.0)}}
    straight = _pts((10783, 1617), (10191, 1838), (10127, 1862))
    entry = _pts((10783, 1617), (10721, 1671), (10662.5, 1862.5), (10659, 1928), (10450, 1876), (10236, 1841),
                 (10127, 1862))
    beside = [[c, x + 5, y] for c, x, y in entry]  # (5 yd off the road's end: not there)
    old_yd, new_yd = rq.stretch_yards(straight, entry)
    assert new_yd <= old_yd * rq.ALONG_STRETCH and rq.share_along_changed_roads(straight, entry, changed) == 0
    assert rq.at_changed_road_end(straight, entry, changed)
    assert not rq.at_changed_road_end(entry[:3] + straight[1:], entry, changed)  # (the older route passed it too)

    def compare(after_pts, after_secs, rides_after=()):
        before = [{**_row(1, 690), "pts": straight}]
        return rq.compare(before, [{**_row(1, after_secs, rides_after), "pts": after_pts}], changed)

    res = compare(entry, 716)
    assert [r["trip"] for r in res["redrawn"]] == ["trip 1"] and not res["worse"]
    far = entry[:4] + _pts((11500, 2500)) + entry[4:]  # (a long way round from the join: #168)
    for after, secs, rides in ((entry, 1000, ()), (beside, 716, ()), (entry, 716, ("flight",)), (far, 760, ())):
        res = compare(after, secs, rides)
        assert [r["trip"] for r in res["worse"]] == ["trip 1"] and not res["redrawn"]


FLOOR_TRACKS = """ns.FloorTracks = {
  [0] = {
  },
  [1] = {
    { op = "add", time = 5, pts = {1,2,3,4,5,6}, zs = {10,11,12} },
    { op = "remove", time = 6, pts = {7,8,9,10}, zs = {10,11} },
    { op = "add", time = 7, pts = {-1.5,2,3,-4.5}, zs = {10,11}, part = 1 },
  },
}
"""


def test_floor_track_lines_are_ns_floor_tracks_added_roads_per_continent():
    # #875: a trip onto a newly shipped floor track is on a changed road (the erasures aren't roads)
    assert rq.floor_track_lines(ROADS + FLOOR_TRACKS) == {1: {(1, 2, 3, 4, 5, 6), (-1.5, 2, 3, -4.5)}}
    assert rq.road_lines(ROADS + FLOOR_TRACKS) == rq.road_lines(ROADS)  # (and they're not ns.Roads')


def test_changed_roads_counts_the_floor_tracks_too(monkeypatch):
    # #875: the road import's conflict merge lost the four Stonetalon walks' FloorTracks lines; put back, route-quality
    # saw no road changed, so a trip onto the trail could never count as on changed roads
    texts = {(rq.ROADS_FILE, "ref"): ROADS + FLOOR_TRACKS.replace("    { op = \"add\", time = 7, pts = {-1.5,2,3,-4.5}, "
                                                                 "zs = {10,11}, part = 1 },\n", ""),
             (rq.ROADS_FILE, None): ROADS + FLOOR_TRACKS, (rq.CAVES_FILE, "ref"): CAVES, (rq.CAVES_FILE, None): CAVES}
    monkeypatch.setattr(rq, "_lines_at", lambda ref, path, read: read(texts[(path, ref)]))
    assert rq.changed_roads("ref") == {1: {(-1.5, 2, 3, -4.5)}}
    assert (-1.5, 2, 3, -4.5) not in rq.old_roads("ref")[1] and (1, 2, 3, 4, 5, 6) in rq.old_roads("ref")[1]
    assert (0, 100, 0, 200) in rq.old_roads("ref")[1] and (0, 0, 0, 5) in rq.old_roads("ref")[1]  # (ns.Roads', caves')


def test_a_trip_onto_the_roads_up_a_new_trail_is_onto_roads_not_worse():
    # #875, Cragpool Lake: the older route walked 1,785 yd west over the land to Sun Rock Retreat (the road above, 135 yd
    # off, up a cliff); Kooki3z's recorded trail up the cliff made that road reachable, and the router took the roads,
    # 2,595 yd (1.45 times: under Router.ROAD_DIRECT_PENALTY's 2), the trip 700 s to 811 s. A stretch more than twice
    # as long, a trip slower by a greater share than its stretch grew, an older stretch along the roads (not a walk over
    # the land), a new one never on a changed road, or other rides: still worse.
    trail = (0.0, 100.0, 50.0, 150.0)
    changed = {1: {trail}}
    roads = {1: {(50.0, 150.0, 400.0, 400.0, 1000.0, 400.0), (1000.0, 0.0, 1000.0, 400.0)}}
    walk = _pts((0, 0), (500, 0), (1000, 0))  # (1,000 yd over the land)
    up = _pts((0, 0), (0, 100), (50, 150), (400, 400), (1000, 400), (1000, 0))  # (1,601 yd: the trail, the roads)
    beside = [[c, x + 5, y] for c, x, y in up]  # (5 yd off the trail and its ends)
    old_yd, new_yd = rq.stretch_yards(walk, up)
    assert round(old_yd) == 1000 and 1.35 * old_yd < new_yd <= old_yd * rq.ROAD_DIRECT_PENALTY
    assert rq.share_along(walk, roads) == 0 and rq.share_along(up, roads) > 0.5

    def compare(before_pts, after_pts, after_secs, rides=(), ch=changed, rd=roads):
        return rq.compare([{**_row(1, 700), "pts": before_pts}],
                          [{**_row(1, after_secs, rides), "pts": after_pts}], ch, None, None, rd)

    res = compare(walk, up, 811)
    assert [r["trip"] for r in res["onto_roads"]] == ["trip 1"] and not res["worse"] and not res["redrawn"]
    assert (res["onto_roads"][0]["stretch_before"], res["onto_roads"][0]["stretch_after"]) == (1000, 1601)
    far = up[:-1] + _pts((1000, -700), (1000, 0))  # (3,001 yd: past twice the walk)
    on_roads = _pts((0, 0), (1000, 0)), _pts((0, 0), (0, 100), (50, 150), (400, 400), (1000, 400), (1000, 0))
    for before, after, secs, rides, ch, rd in ((walk, up, 1150, (), changed, roads), (walk, far, 811, (), changed, roads),
                                               (walk, beside, 811, (), changed, roads),
                                               (walk, up, 811, ("flight",), changed, roads),
                                               (on_roads[0], on_roads[1], 811, (), changed, {1: {(0.0, 0.0, 1000.0, 0.0)}}),
                                               (walk, up, 811, (), changed, None)):
        res = compare(before, after, secs, rides, ch, rd)
        assert [r["trip"] for r in res["worse"]] == ["trip 1"] and not res["onto_roads"]


def test_wall_lines_are_ns_walls_per_continent_and_new_walls_cross_routes():
    text = ROADS.replace("    {1,2,3,4},\n", "    {1,2,3,4},\n    {0,-5,0,5, z = 12.5},\n")
    assert rq.wall_lines(text) == {1: {(1, 2, 3, 4), (0, -5, 0, 5)}}  # (no road, no height)
    walls = {1: {(0, -5, 0, 5)}}
    assert rq.wall_steps(_pts((-10, 0), (10, 0), (20, 0)), walls) == {(1, -10, 0, 10, 0)}
    assert not rq.wall_steps(_pts((-10, 0), (-10, 10), (10, 10)), walls)  # (round its end)
    assert not rq.wall_steps(_pts((-10, 0), (10, 0), cont=0), walls)  # (another continent)


def test_a_slower_trip_that_went_through_a_new_wall_is_walled_not_worse():
    # Splintertree Post: walls drawn by its palisade; the trips that walked through it go out by
    # the road through the gate (the wall's line crossed there too, the road cut a yard either side)
    walls = {1: {(0, -5, 0, 5)}}
    through, round_ = _pts((-10, 0), (10, 0)), _pts((-10, 0), (-10, 4), (10, 4), (10, 0))

    def compare(before_pts, after_pts, rides=("flight",)):
        return rq.compare([{**_row(1, 787, ["flight"]), "pts": before_pts}],
                          [{**_row(1, 975, rides), "pts": after_pts}], None, walls)

    res = compare(through, round_)
    assert [r["trip"] for r in res["walled"]] == ["trip 1"] and not res["worse"]
    for before_pts, after_pts, rides in ((round_, round_, ("flight",)),  # (never through it: worse)
                                         (through, through, ("flight",)),  # (the same step through it: worse)
                                         (through, round_, ("other",))):  # (other rides: worse)
        res = compare(before_pts, after_pts, rides)
        assert [r["trip"] for r in res["worse"]] == ["trip 1"] and not res["walled"]


def test_a_slower_trip_whose_older_route_swam_new_deep_water_is_deep_not_worse():
    # AzerothGPS#687: the Wetlands to Southshore swum straight over the strait into fatigue; with the deep sea far out
    # closed the trip goes round by land, a boat or a flight (its rides may differ)
    import numpy as np

    from azerothgps.roads.terrain import encode_row

    cells = np.full((16, 16), 3, np.uint8)  # (16 x 16 cells of 8.33 yd, all deep: x and y -133 to 0)
    head = "  [1] = { tx0 = 32, ty0 = 32, cell = 8.333333, w = 16, h = 16, "
    rows = "".join(f'    "{encode_row(r)}",\n' for r in cells)
    deep = rq.deep_cells(f"ns.Terrain = {{\n{head}deep = 3, rows = {{\n{rows}  }} }},\n}}\nns.Hills = {{}}\n")
    assert deep[1][:3] == (32, 32, 8.333333) and deep[1][3].all()
    assert not rq.deep_cells(f"ns.Terrain = {{\n{head}rows = {{\n{rows}  }} }},\n}}\nns.Hills = {{}}\n")  # (none)
    swim, round_ = _pts((-5, -5), (-125, -5)), _pts((-5, -5), (-5, 20), (-125, 20), (-125, -5))
    assert round(rq.deep_yards(swim, deep)) == 120 and rq.deep_yards(round_, deep) < 15
    coast = _pts((-5, 5), (-125, 5))  # (along the coast: outside the grid, no deep water)

    def walks(pts):  # (as walk_parts: [[cont, [x, y, ...]]])
        return [[pts[0][0], [v for p in pts for v in p[1:]]]]

    def compare(before_walk, after_walk):
        return rq.compare([{**_row(1, 665), "guard_walks": walks(before_walk)}],
                          [{**_row(1, 2630, ["boat"]), "guard_walks": walks(after_walk)}], None, None, deep)

    # (a way round it, its rides other; and the same swim, to an end out at sea, weighed now as closed ground)
    for before_walk, after_walk in ((swim, coast), (swim, swim)):
        res = compare(before_walk, after_walk)
        assert [r["trip"] for r in res["deep"]] == ["trip 1"] and not res["worse"]
    for before_walk, after_walk in ((coast, coast), (coast, swim), (round_, swim)):  # (never out there, or more: worse)
        res = compare(before_walk, after_walk)
        assert [r["trip"] for r in res["worse"]] == ["trip 1"] and not res["deep"]
    # (a boat over it isn't a swim: only the walks count)
    res = rq.compare([{**_row(1, 665), "pts": swim, "guard_walks": walks(coast)}],
                     [{**_row(1, 2630), "pts": swim, "guard_walks": walks(coast)}], None, None, deep)
    assert [r["trip"] for r in res["worse"]] == ["trip 1"] and not res["deep"]


def test_a_slower_trip_past_fewer_of_the_other_factions_guards_is_safer_not_worse():
    # The Barrens: new roads gave Alliance trips a way round the Crossroads and Camp Taurajo
    def compare(guard_before, guard_after, after_secs=1862):
        return rq.compare([{**_row(1, 1523), "guard": guard_before}], [{**_row(1, after_secs, ["flight"]),
                                                                         "guard": guard_after}])

    res = compare(851, 254)
    assert [r["trip"] for r in res["safer"]] == ["trip 1"] and not res["worse"]
    assert (res["safer"][0]["guard_before"], res["safer"][0]["guard_after"]) == (851, 254)
    for guard_before, guard_after in ((851, 800), (0, 0), (254, 851)):  # (not GUARD_YD fewer: worse)
        res = compare(guard_before, guard_after)
        assert [r["trip"] for r in res["worse"]] == ["trip 1"] and not res["safer"]
    res = compare(851, 254, after_secs=1400)  # (faster and safer: better)
    assert [r["trip"] for r in res["better"]] == ["trip 1"]


def test_the_older_route_is_weighed_by_the_newer_versions_guards_too():
    # (2026-11-16: the enemy areas from the NPCs that flag a player for PvP, Theramore's sentries and Stonard's scouts
    # among them) a route round NPCs only the newer version counts walked none of the older version's guards
    def compare(old_guard, guard_after=0):
        return rq.compare([{**_row(1, 710), "guard": 0}], [{**_row(1, 722), "guard": guard_after, "old_guard": old_guard}])

    res = compare(160)
    assert [r["trip"] for r in res["safer"]] == ["trip 1"] and res["safer"][0]["old_guard"] == 160
    for old_guard, guard_after in ((60, 0), (None, 0), (160, 100)):  # (not GUARD_YD fewer, or not weighed: worse)
        assert [r["trip"] for r in compare(old_guard, guard_after)["worse"]] == ["trip 1"]


def test_a_slower_trip_whose_older_routes_walks_no_longer_hop_is_unhopped_not_worse():
    # #349: from North Gate Outpost the older route walked off the 195 yd cliff between Loch Modan and the Badlands (the
    # router's `blocked`: straight over closed ground, no walk round it). With the Slag Pit's floors (PR #332) that walk
    # goes round by Searing Gorge (#339: no wall hopping), so long the planner flew instead, its walk to Tarren Mill's
    # flight master hopping the Dun Algaz tunnel and Thandol Span as it always had (521 yd). Other rides are fine
    def compare(blocked_before, old_walks_now, blocked_after=521, after_secs=6489):
        return rq.compare([{**_row(1, 2063), "blocked": blocked_before}],
                          [{**_row(1, after_secs, ["flight", "zeppelin", "flight"]), "blocked": blocked_after,
                            "old_walks_blocked": old_walks_now}])

    res = compare(195, 0)
    assert [r["trip"] for r in res["unhopped"]] == ["trip 1"] and not res["worse"]
    assert (res["unhopped"][0]["blocked_before"], res["unhopped"][0]["old_walks_blocked"]) == (195, 0)
    for blocked_before, old_walks_now in ((195, 120), (0, 0), (0, 195), (60, 0), (195, 195)):  # (not HOP_YD less: worse)
        res = compare(blocked_before, old_walks_now)
        assert [r["trip"] for r in res["worse"]] == ["trip 1"] and not res["unhopped"]
    res = rq.compare([{**_row(1, 2063), "blocked": 195}], [{**_row(1, 6489), "blocked": 0}])  # (not routed again: worse)
    assert [r["trip"] for r in res["worse"]] == ["trip 1"]
    res = compare(195, 0, after_secs=1900)  # (faster and without the hop: better)
    assert [r["trip"] for r in res["better"]] == ["trip 1"]


def test_a_slower_trip_on_the_safe_way_while_the_game_asks_is_asking_not_worse():
    # a player's road into North Gate Pass gave a level 10 Horde trip from North Gate Outpost to
    # Terral's Watch a walk to Flame Crest's flight 139 yd further from the Alliance's guards than the walk by the ride
    # check's own walks (983 -> 844), the safe way 58% slower: shown while the game asks "risk it?". `guard` here: 69 fewer
    def compare(asking, guard_after=647, old_guard=716):
        return rq.compare([{**_row(1, 1787), "guard": 716}],
                          [{**_row(1, 2820, ["flight"]), "guard": guard_after, "old_guard": old_guard, "asking": asking}])

    res = compare(True)
    assert [r["trip"] for r in res["asking"]] == ["trip 1"] and not res["worse"] and not res["safer"]
    assert [r["trip"] for r in compare(False)["worse"]] == ["trip 1"]  # (not asked: worse)
    assert [r["trip"] for r in compare(True, guard_after=800, old_guard=None)["worse"]] == ["trip 1"]  # (nearer them)
    res = rq.compare([{**_row(1, 1787), "guard": 716}], [{**_row(1, 2820, ["flight"]), "guard": 647}])  # (no flag: worse)
    assert [r["trip"] for r in res["worse"]] == ["trip 1"]


def test_weigh_trips_routes_the_older_versions_walks_again():
    # (the second version weighs each trip and then routes the first's walks: their blocked yards there)
    older = rq.weigh_trips(2, 21)
    assert all("walks" in r and "level" in r and "side" in r and r.get("asking") in (True, False) for r in older)
    newer = rq.weigh_trips(2, 21, older=older)
    for o, n in zip(older, newer):
        assert n["trip"] == o["trip"] and n["old_walks_blocked"] == n["blocked"] == o["blocked"]


def test_guard_yards_leave_out_the_towns_at_a_walks_ends():
    from azerothgps.gameharness import start

    lua, ns = start()
    lua.execute("""
      AGPS_NS.Hostile = AGPS_NS.Hostile or {}
      AGPS_NS.Hostile[77] = { A = { 0, 500, 100,  0, 0, 50 } }
      AGPS_NS.Router.HostileTowns = function() return { [1] = 'mid', [4] = 'start' } end
      AGPS_NS.Router.HostileSide = function() return 'A' end
    """)
    r = lua.eval("{ parts = { { cont = 77, pts = { 0, 0, 0, 1000 }, kinds = { 1 } } } }")
    yards = rq.guard_yards(ns, rq.walk_parts(ns, r))
    assert abs(yards - 200) <= 10  # (the guards round (0, 500), not those at the walk's start)


def test_the_working_tree_against_itself_has_no_older_files():
    assert rq._older_files("HEAD") == {} or all(name.endswith(".lua") for name in rq._older_files("HEAD"))


def test_a_slower_trip_past_posts_the_change_dropped_is_unguarded_not_worse():
    # (2026-11-16, the enemy areas from the NPCs that would flag a player: Ambermill's Dalaran Protectors flag no one, and
    # the road by them, now free, beat a 3.1k yd walk across at road mode's 2x, 492 s -> 885 s; asked: "Accept them")
    def compare(new_old_guard, guard_before=0, guard_after=0):
        return rq.compare([{**_row(1, 492), "guard": guard_before}],
                          [{**_row(1, 885), "guard": guard_after, "new_old_guard": new_old_guard}])

    res = compare(240)
    assert [r["trip"] for r in res["unguarded"]] == ["trip 1"] and not res["worse"]
    assert res["unguarded"][0]["new_old_guard"] == 240
    assert [r["trip"] for r in compare(52)["unguarded"]] == ["trip 1"]  # (Whispering Gardens -> Gilneas City)
    for new_old_guard, guard_before in ((20, 0), (None, 0), (210, 200)):  # (not UNGUARDED_YD nearer them: worse)
        assert [r["trip"] for r in compare(new_old_guard, guard_before, guard_before)["worse"]] == ["trip 1"]


def test_a_slower_trip_past_fewer_of_their_other_pvp_npcs_is_safer():
    # (2026-11-16) Venture Co. Base Camp -> Jaguero Isle, 512 s -> 688 s, 2,481 yd past the other faction's quest
    # givers and workers (the light ones) down to 384: safer, as fewer guards' yards are
    def compare(old_light, light):
        return rq.compare([{**_row(1, 512), "guard": 0}], [{**_row(1, 688), "guard": 0, "light": light, "old_light": old_light}])

    assert [r["trip"] for r in compare(2481, 384)["safer"]] == ["trip 1"]
    assert [r["trip"] for r in compare(150, 100)["worse"]] == ["trip 1"]


def test_shards_draw_the_same_trips_as_one_run():
    # (2026-11-16, "find a faster way for PRs to run tests": route-quality's trips in processes, each a shard) every trip
    # is still drawn from the seed, so the shards together are the one run's trips, each once, in its place
    one = rq.weigh_trips(6, 21, None, lambda *_: None)
    shards = [rq.weigh_trips(6, 21, None, lambda *_: None, None, (i, 3)) for i in range(3)]
    assert sorted((r["k"], r["trip"]) for s in shards for r in s) == [(r["k"], r["trip"]) for r in one]
    assert all(r["k"] % 3 == i for i, s in enumerate(shards) for r in s)


def test_kept_rows_are_the_versions_own_and_only_for_the_same_trips(tmp_path):
    """CI keeps main's rows for the PRs on it (--keep-rows, --before-rows): what the version alone chose, never the
    fields it took from the older rows it was handed, and only read back for the same trips."""
    row = {**_row(0, 100), "old_guard": 3, "old_light": 1, "old_walks_blocked": 9, "error": "older walks: boom"}
    kept = tmp_path / "rows" / "rows.json"
    rq.save_rows(kept, [row, _row(1, None, error="lua: oops")], 2, 21)
    rows = rq.load_rows(kept, 2, 21)
    assert rows == [_row(0, 100), _row(1, None, error="lua: oops")]
    assert rq.load_rows(kept, 3, 21) is None and rq.load_rows(kept, 2, 22) is None
    assert rq.load_rows(tmp_path / "none.json", 2, 21) is None and rq.load_rows(None, 2, 21) is None
    kept.write_text("[1, 2]", encoding="utf-8")
    assert rq.load_rows(kept, 2, 21) is None


def test_kept_older_rows_stand_in_for_weighing_them(tmp_path, monkeypatch):
    weighed = []

    def weigh(count, seed, replace, log, older, jobs):
        weighed.append("older" if older is None else "newer")
        return [{**_row(k, 100 + k), **({"old_guard": 0} if older else {})} for k in range(count)]

    monkeypatch.setattr(rq, "_weigh", weigh)
    monkeypatch.setattr(rq, "_older_files", lambda ref: {})
    for name in ("changed_roads", "new_walls", "new_deep", "old_roads"):
        monkeypatch.setattr(rq, name, lambda ref: None)
    base, head = tmp_path / "base.json", tmp_path / "head.json"
    first = rq.run(3, 21, "main", log=lambda *a: None, before_rows=base, keep_rows=head)
    assert weighed == ["older", "newer"] and base.is_file() and head.is_file()
    assert "old_guard" not in rq.load_rows(head, 3, 21)[0]
    weighed.clear()
    again = rq.run(3, 21, "main", log=lambda *a: None, before_rows=base)
    assert weighed == ["newer"]  # (the older version's rows read, not weighed)
    assert again["same"] == first["same"] == 3


def test_kept_rows_from_other_places_are_weighed_again(tmp_path, monkeypatch):
    """2026-11-24: rows kept before #978 took a place out of Data/Pois.lua were other trips row by row; read back, a
    routing PR showed trips "worse" and "lost" that were never its own. Kept rows carry their places' fingerprint."""
    weighed = []

    def weigh(count, seed, replace, log, older, jobs):
        weighed.append("older" if older is None else "newer")
        return [_row(k, 100 + k) for k in range(count)]

    monkeypatch.setattr(rq, "_weigh", weigh)
    monkeypatch.setattr(rq, "_older_files", lambda ref: {})
    for name in ("changed_roads", "new_walls", "new_deep", "old_roads"):
        monkeypatch.setattr(rq, name, lambda ref: None)
    base = tmp_path / "base.json"
    rq.save_rows(base, [_row(k, 100 + k) for k in range(3)], 3, 21, "other places")
    assert rq.load_rows(base, 3, 21) is not None and rq.load_rows(base, 3, 21, rq.trip_places()) is None
    rq.run(3, 21, "main", log=lambda *a: None, before_rows=base)
    assert weighed == ["older", "newer"]  # (weighed again, not read back)
    assert rq.load_rows(base, 3, 21, rq.trip_places()) is not None
    # (an older version with its own places: those are its trips')
    assert rq.trip_places({"Data/Pois.lua": "ns.Pois = {}"}) != rq.trip_places()
