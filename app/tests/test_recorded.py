"""Heights for the roads walked in game with Record (roads/recorded.py): the floors under each point, the best path
over the whole walk, and the track cut into the ground's pieces and the floors'. A made-up two-floor building, and
Brill's inn from the client (skipped without it)."""

import math
import re
import statistics

import numpy as np
import pytest

from azerothgps.roads import recorded as R


def rect(x0, x1, y0, y1, z0, z1=None):
    """A rectangle's two triangles over x0..x1, y0..y1: its height z0 at x0, rising to z1 at x1 (a ramp along x)."""
    z1 = z0 if z1 is None else z1
    a, b, c, d = (x0, y0, z0), (x1, y0, z1), (x1, y1, z1), (x0, y1, z0)
    return [(a, b, c), (a, c, d)]


def building(open_stairs=False, steep=False):
    """A two-floor building on flat ground (z 0), x 10..40 by y -8..8: its ground floor at 1, its upper floor at 7, a
    flat roof at 12; stairs at y 4..8 rising from x 20 (at 1) to x 30 (at 7; x 24 `steep`), on a solid base (no floor
    under them) unless `open_stairs`; the upper floor open over them from 2 yd past their foot."""
    top = 24.0 if steep else 30.0
    tris = rect(10, 40, -8, 4, 1) + rect(10, 20, 4, 8, 1) + rect(top, 40, 4, 8, 1)
    if open_stairs:
        tris += rect(20, top, 4, 8, 1)
    tris += rect(20, top, 4, 8, 1, 7)
    tris += rect(10, 40, -8, 4, 7) + rect(10, 22, 4, 8, 7) + rect(top, 40, 4, 8, 7)
    return tris + rect(10, 40, -8, 8, 12)


def walk(way, step=2.0):
    """Points along the corners `way`, about `step` yd apart, the corners kept (as Record samples)."""
    out = [tuple(way[0])]
    for a, b in zip(way, way[1:]):
        n = max(1, round(math.dist(a, b) / step))
        out += [(a[0] + (b[0] - a[0]) * k / n, a[1] + (b[1] - a[1]) * k / n) for k in range(1, n + 1)]
    return out


def scene(**kw):
    """In from the west on the ground floor, up the stairs, along the upper floor and back west over the ground
    floor: (points, candidates, IsIndoors, the stairs' marks)."""
    top = 24.0 if kw.get("steep") else 30.0
    pts = walk([(0.0, 6.0), (20.0, 6.0), (top, 6.0), (36.0, 6.0), (36.0, -6.0), (14.0, -6.0)])
    cands = R.floors_under(pts, np.zeros(len(pts)), [R.Faces(building(**kw), uid=7)])
    indoors = [10 < x < 40 for x, _y in pts]
    return pts, cands, indoors, [(pts.index((20.0, 6.0)), pts.index((top, 6.0)))]


def test_the_floors_under_a_point_are_the_terrain_and_each_face_there():
    pts = [(25.0, 6.0), (15.0, 0.0), (5.0, 0.0), (10.2, 0.0), (9.8, 0.0), (8.0, 0.0)]
    cands = R.floors_under(pts, [0.0, 0.0, 0.0, 0.0, 0.0, 0.0], [R.Faces(building(), uid=7)])
    at = [[(c.z, c.kind, c.uid) for c in cs] for cs in cands]
    assert at[0] == [(0.0, "ground", None), (4.0, "model", 7), (12.0, "model", 7)]  # (the stairs, under the opening)
    assert at[1] == [(1.0, "model", 7), (7.0, "model", 7), (12.0, "model", 7)]  # (the terrain 1 yd under a floor: none)
    assert at[2] == [(0.0, "ground", None)]  # (outside)
    assert [c.z for c in cands[3]] == [1.0, 7.0, 12.0]  # (0.2 yd in)
    assert [c.z for c in cands[4]] == [1.0, 7.0, 12.0]  # (0.2 yd out: on it still, TOUCH)
    assert [c.z for c in cands[5]] == [0.0]
    assert cands.top[0] == 12.0 and cands.top[2] == -math.inf
    # (a floor within MERGE_Z of the terrain is one with it: the ground, with the model's uid, at the top one)
    flat = R.floors_under([(15.0, 0.0)], [0.0], [R.Faces(rect(10, 40, -8, 8, 0.3), uid=9)])
    assert flat[0] == [R.Cand(0.3, "ground", 9)]
    # (no terrain there: a hole, off the tiles)
    assert R.floors_under([(15.0, 0.0)], [np.nan], [R.Faces(rect(10, 40, -8, 8, 0.3), uid=9)])[0] == [
        R.Cand(0.3, "model", 9)]


def test_the_faces_index_finds_what_looking_at_every_face_finds():
    rng = np.random.default_rng(5)
    corners = rng.uniform(-60, 60, (300, 1, 2)) + rng.uniform(-1, 1, (300, 3, 2)) * rng.choice([2, 30], (300, 1, 1))
    tris = np.concatenate([corners, rng.uniform(0, 50, (300, 3, 1))], axis=2)
    pts = rng.uniform(-70, 70, (2000, 2))
    faces = R.Faces(tris, touch=0.0)
    pi, z = faces.heights(pts[:, 0], pts[:, 1])
    got = sorted(zip(pi.tolist(), np.round(z, 6).tolist()))
    # (every point against every face)
    (x1, y1, z1), (x2, y2, z2), (x3, y3, z3) = (tris[:, v, :].T[:, None, :] for v in range(3))
    x, y = pts[:, 0, None], pts[:, 1, None]
    det = (y2 - y3) * (x1 - x3) + (x3 - x2) * (y1 - y3)
    l1 = ((y2 - y3) * (x - x3) + (x3 - x2) * (y - y3)) / det
    l2 = ((y3 - y1) * (x - x3) + (x1 - x3) * (y - y3)) / det
    k, f = np.nonzero((l1 >= 0) & (l2 >= 0) & (1 - l1 - l2 >= 0))
    zz = l1[k, f] * z1[0, f] + l2[k, f] * z2[0, f] + (1 - l1[k, f] - l2[k, f]) * z3[0, f]
    want = sorted(zip(k.tolist(), np.round(zz, 6).tolist()))
    assert len(want) > 500 and got == want


def test_a_walk_in_and_up_marked_stairs_reads_each_floor():
    pts, cands, indoors, stairs = scene()
    ind = "".join("1" if v else "0" for v in indoors)  # (as Record saves it)
    zs, kinds, ambiguous = R.assign(cands, ind, stairs)
    a, b = stairs[0]
    assert zs[:5] == [0.0] * 5  # (outside)
    assert zs[5:a + 1] == [1.0] * (a - 4)  # (in at the door, x 10: the ground floor)
    assert zs[a:b + 1] == [1.0, 2.2, 3.4, 4.6, 5.8, 7.0]  # (the stairs)
    assert zs[b:] == [7.0] * (len(pts) - b)  # (the upper floor, over the ground floor too)
    assert kinds == ["ground"] * 5 + ["model"] * (len(pts) - 5)
    assert ambiguous == []


def test_without_marks_a_gradual_climb_still_reads():
    pts, cands, indoors, stairs = scene()
    marked = R.assign(cands, indoors, stairs)
    assert R.assign(cands, indoors, []) == marked
    # (the same over 1 yd steps, and the points' spacing from the points themselves)
    pts1 = walk([(0.0, 6.0), (20.0, 6.0), (30.0, 6.0), (36.0, 6.0), (36.0, -6.0), (14.0, -6.0)], 1.0)
    c1 = R.floors_under(pts1, np.zeros(len(pts1)), [R.Faces(building(), uid=7)])
    zs, _kinds, ambiguous = R.assign(c1, [10 < x < 40 for x, _y in pts1], [])
    assert zs[-1] == 7.0 and ambiguous == []


def test_steep_stairs_read_only_with_their_marks():
    pts, cands, indoors, stairs = scene(steep=True)
    zs, _kinds, _amb = R.assign(cands, indoors, [])
    assert zs[-1] == 1.0  # (a climb steeper than a walk: no way up but a jump)
    zs, _kinds, ambiguous = R.assign(cands, indoors, stairs)
    a, b = stairs[0]
    assert zs[a:b + 1] == [1.0, 4.0, 7.0] and zs[-1] == 7.0 and ambiguous == []


def test_off_a_landings_side_is_a_drop_not_a_step():
    # (Brill's inn: a flight up to a landing, the next back alongside over the floor, open under it: stepping off the
    # landing's side, 3.2 yd, onto that floor is a drop (DROP), so the climb on up wins, with no doubt)
    tris = rect(10, 40, -8, 0, 1) + rect(10, 20, 0, 8, 1) + rect(10, 28, 0, 4, 1)  # (the ground floor)
    tris += rect(20, 28, 4, 8, 1, 4.2) + rect(28, 32, 0, 8, 4.2)  # (the first flight, the landing)
    tris += rect(20, 28, 0, 4, 7, 4.2) + rect(10, 20, -8, 8, 7) + rect(10, 40, -8, 8, 12)  # (back up, upstairs, roof)
    pts = walk([(0.0, 6.0), (20.0, 6.0), (28.0, 6.0), (30.0, 6.0), (30.0, 2.0), (20.0, 2.0), (12.0, 2.0)])
    cands = R.floors_under(pts, np.zeros(len(pts)), [R.Faces(tris, uid=8)])
    zs, _kinds, ambiguous = R.assign(cands, [10 < x < 40 for x, _y in pts], [])
    assert zs[-5:] == [7.0] * 5 and ambiguous == []


def test_a_floor_the_walk_cant_tell_is_reported_and_a_mark_or_a_pick_settles_it():
    pts, cands, indoors, stairs = scene(open_stairs=True)
    a, b = stairs[0]
    # (a floor under the stairs: walking on under them costs nothing, the climb a little; the upper floor's a doubt,
    # from where the stairs are 2 yd over the floor to the walk's end)
    zs, _kinds, ambiguous = R.assign(cands, indoors, [])
    assert zs[-1] == 1.0
    assert ambiguous == [(a + 2, len(pts) - 1)]
    # (the marks: up the stairs)
    zs, _kinds, ambiguous = R.assign(cands, indoors, stairs)
    assert zs[a:b + 1] == [1.0, 2.2, 3.4, 4.6, 5.8, 7.0] and zs[-1] == 7.0 and ambiguous == []
    # (or a floor picked by hand upstairs at one point: a height or None per point, or a dict)
    picked = [None] * len(pts)
    picked[b + 6] = 7.0
    zs, _kinds, ambiguous = R.assign(cands, indoors, [], picked)
    assert zs[-1] == 7.0 and ambiguous == []
    zs, _kinds, _amb = R.assign(cands, indoors, [], {b + 6: 1.0})
    assert zs[-1] == 1.0


def test_each_floor_costs_by_what_the_game_said_there():
    # (indoors: the terrain under a model's floor INDOOR_MISS, a floor nothing covers (a roof's top) SKY_MISS;
    # outdoors: a model's floor under another face ROOF_MISS; a floor picked by hand: the others PICK_MISS)
    cs = [R.Cand(1.0, "ground"), R.Cand(7.0, "model", 4), R.Cand(12.0, "model", 4)]
    assert list(R._own_costs(cs, 12.0, True, None)) == [R.INDOOR_MISS, 0.0, R.SKY_MISS]
    assert list(R._own_costs(cs, 12.0, False, None)) == [0.0, R.ROOF_MISS, 0.0]
    assert list(R._own_costs(cs, 12.0, None, 7.5)) == [R.PICK_MISS, 0.0, R.PICK_MISS]
    # (a gallery over a pit under a flat roof, walked indoors with no way in seen: on the gallery, not its roof)
    pts = walk([(0.0, 0.0), (20.0, 0.0)])
    cands = R.floors_under(pts, np.full(len(pts), 1.0), [R.Faces(rect(-5, 25, -3, 3, 7) + rect(-5, 25, -3, 3, 12))])
    assert R.assign(cands, [True] * len(pts), []) == ([7.0] * len(pts), ["model"] * len(pts), [])


def test_candidates_takes_each_placed_models_floors_and_a_turned_over_ones_as_cover(monkeypatch):
    from types import SimpleNamespace as NS

    monkeypatch.setattr(R, "_FACES", {-5: (np.array(rect(-2, 2, -2, 2, 0.0)), np.zeros((0, 3, 3)))})
    monkeypatch.setattr(R, "_PLACED", {})
    # (walknet.Placed: yaw 180 is unturned; a tilt about its y axis, rx)
    tilted = NS(wmo=-5, uid=1, x=100.0, y=50.0, z=10.0, yaw=180.0, tilt=10.0, rx=10.0, rz=0.0, bounds=(98, 48, 102, 52))
    over = NS(wmo=-5, uid=2, x=200.0, y=50.0, z=10.0, yaw=180.0, tilt=180.0, rx=180.0, rz=0.0,
              bounds=(198, 48, 202, 52))
    ground = NS(sample=lambda X, Y: (np.zeros(len(X)), np.ones(len(X), bool)))
    cands = R.candidates(None, 0, [(100.0, 50.0), (200.0, 50.0), (150.0, 50.0)], ground, [tilted, over])
    assert [(c.kind, round(c.z, 1), c.uid) for c in cands[0]] == [("ground", 0.0, None), ("model", 10.0, 1)]
    assert cands[1] == [R.Cand(0.0, "ground")] and cands.top[1] == pytest.approx(10.0)  # (upside down: over it)
    assert cands[2] == [R.Cand(0.0, "ground")] and cands.top[2] == -math.inf
    assert cands.pts == [(100.0, 50.0), (200.0, 50.0), (150.0, 50.0)]


def test_indoors_puts_the_walk_on_a_floor_level_with_the_ground_and_outdoors_off_it():
    # (a hall whose floor is level with the terrain (merged: the ground, with its uid): "model" indoors, "ground"
    # out; the terrain under a building's floor costs INDOOR_MISS indoors: its floor, not the ground under it)
    pts = walk([(0.0, 0.0), (30.0, 0.0)])
    faces = R.Faces(rect(10, 20, -5, 5, 0.3) + rect(10, 20, -5, 5, 6), uid=3)
    cands = R.floors_under(pts, np.zeros(len(pts)), [faces])
    zs, kinds, _amb = R.assign(cands, [10 <= x <= 20 for x, _y in pts], [])
    assert kinds == ["ground"] * 5 + ["model"] * 6 + ["ground"] * 5 and zs[7] == 0.3
    zs, kinds, _amb = R.assign(cands, [False] * len(pts), [])
    assert kinds == ["ground"] * len(pts)
    faces = R.Faces(rect(10, 20, -5, 5, 1.2) + rect(10, 20, -5, 5, 6), uid=3)
    raised = R.floors_under(pts, np.zeros(len(pts)), [faces])
    zs, kinds, _amb = R.assign(raised, [10 <= x <= 20 for x, _y in pts], [])
    assert zs[5:11] == [1.2] * 6 and kinds[5:11] == ["model"] * 6


def test_pieces_cut_at_the_door_and_the_stairs():
    pts, cands, indoors, stairs = scene()
    zs, kinds, _amb = R.assign(cands, indoors, stairs)
    out = R.pieces(pts, zs, kinds, stairs)
    a, b = stairs[0]
    assert [(len(p["coords"]), p["stair"], p["zs"] is None) for p in out] == [
        (5, False, True),  # (outside, up to the doorstep)
        (a - 3, False, False),  # (the ground floor, from the doorstep to the stairs' foot)
        (b - a + 1, True, False),  # (the stairs)
        (len(pts) - b, False, False)]  # (the upper floor)
    for p, q in zip(out, out[1:]):
        assert p["coords"][-1] == q["coords"][0]  # (neighbors share their end)
    assert out[1]["zs"] == [0.0] + [1.0] * (a - 4) and out[2]["zs"] == [1.0, 2.2, 3.4, 4.6, 5.8, 7.0]
    assert [q for p in out for q in p["coords"][:-1]] + [out[-1]["coords"][-1]] == [list(q) for q in pts]
    # (without marks: no stairs piece, the inside one piece)
    out = R.pieces(pts, zs, kinds, [])
    assert [p["zs"] is None for p in out] == [True, False] and len(out[1]["coords"]) == len(pts) - 4


def test_a_doormat_is_the_ground_and_a_short_walk_no_pieces():
    pts = walk([(0.0, 0.0), (20.0, 0.0)])
    kinds = ["ground"] * len(pts)
    kinds[5] = "model"  # (a slab 2 yd long)
    out = R.pieces(pts, [0.0] * len(pts), kinds, [])
    assert len(out) == 1 and out[0]["zs"] is None and len(out[0]["coords"]) == len(pts)
    kinds[4:7] = ["model"] * 3  # (a porch: 6 yd)
    out = R.pieces(pts, [0.0] * len(pts), kinds, [])
    assert [(len(p["coords"]), p["zs"] is None) for p in out] == [(4, True), (5, False), (4, True)]
    assert R.pieces(pts[:1], [0.0], ["ground"], []) == []
    assert R.pieces(pts, [0.0] * len(pts), ["ground"] * len(pts), [(3, 3)]) == [
        {"coords": [list(q) for q in pts], "zs": None, "stair": False}]  # (a mark with no length: none)


# ---- the client: Brill's inn (Gallows' End Tavern), in at its front door, up its stairs (first flight north along
# the east wall to the landing, the second back south), along the upper floor past the trainers

INN = [(2242.0, 274.0), (2246.0, 264.0), (2246.0, 258.0), (2250.0, 250.0), (2256.0, 242.0), (2259.0, 232.0),
       (2266.5, 232.0), (2269.5, 233.5), (2269.0, 237.0), (2263.0, 237.5), (2259.5, 237.0), (2258.0, 244.0),
       (2256.0, 248.0), (2251.0, 255.0)]
INN_BOUNDS = (2234.5, 220.2, 2298.9, 262.4)  # (its placement's, uid 125898)


@pytest.fixture(scope="module")
def client():
    from azerothgps.cli import DATA, DEFAULT_WOW, PRODUCT

    if not (DEFAULT_WOW / ".build.info").exists() or not (DATA / "ref" / "listfile.csv").exists():
        pytest.skip("needs the local WoW install and data/ref (listfile + dbd)")
    from azerothgps import interiors
    from azerothgps.caves import Ground
    from azerothgps.extract.spike import ClientData

    try:
        cd = ClientData(DEFAULT_WOW, PRODUCT, DATA / "ref")
    except Exception as ex:  # (an install this reader can't open)
        pytest.skip(f"the client doesn't open: {ex!r}")
    return cd, Ground(cd, 0), interiors.placements(cd, 0)


def _upstairs_heights():
    """The heights of the inn's upstairs roads (Data/Indoors.lua's indoor roads' nz, inside it, over 38 yd)."""
    from azerothgps.paths import ADDON_DIR

    text = (ADDON_DIR / "Data" / "Indoors.lua").read_text(encoding="utf-8")
    block = text[text.find("indoor = true"):]
    n = [float(v) for v in re.search(r"\bn = \{([^}]*)\}", block).group(1).split(",")]
    nz = [float(v) for v in re.search(r"\bnz = \{([^}]*)\}", block).group(1).split(",")]
    x0, y0, x1, y1 = INN_BOUNDS
    return [z for (x, y), z in zip(zip(n[::2], n[1::2]), nz) if x0 <= x <= x1 and y0 <= y <= y1 and z > 38]


def test_brill_inn_up_its_stairs_from_the_client(client):
    cd, ground, placements = client
    pts = walk(INN)
    cands = R.candidates(cd, 0, pts, ground, placements)
    x0, y0, x1, y1 = INN_BOUNDS
    indoors = [x0 < x < x1 and y0 < y < y1 for x, y in pts]
    foot, top = pts.index((2259.0, 232.0)), pts.index((2263.0, 237.5))
    up = statistics.median(_upstairs_heights())
    for stairs in ([], [(foot, top)]):
        zs, kinds, ambiguous = R.assign(cands, indoors, stairs)
        assert all(abs(z - 34.0) <= 1.0 for z in zs[:foot + 1])  # (the street, then the ground floor)
        assert all(b >= a - 0.05 for a, b in zip(zs[foot:top + 1], zs[foot + 1:top + 1]))  # (up the stairs)
        assert all(abs(z - up) <= 1.0 for z in zs[top:]), (up, zs[top:])  # (the upper floor)
        assert kinds[0] == "ground" and kinds[-1] == "model" and ambiguous == []
        out = R.pieces(pts, zs, kinds, stairs)
        assert out[0]["zs"] is None and all(p["zs"] for p in out[1:])
        assert [p["stair"] for p in out[1:]] == ([False] if not stairs else [False, True, False])


def test_the_terrain_has_a_hole_where_the_inns_cellar_stairs_go_down(client):
    cd, ground, placements = client
    h = R.terrain_at(ground, [2286.0, 2289.0, 2270.0, 2300.0], [247.0, 247.0, 246.0, 300.0])
    assert np.isnan(h[:2]).all() and np.isfinite(h[2:]).all()
    cands = R.candidates(cd, 0, [(2289.0, 247.0)], ground, placements)
    assert [c.kind for c in cands[0]] == ["model"] * len(cands[0]) and min(c.z for c in cands[0]) < 31


def test_the_watchers_walks_take_records_marks_picks_and_levels(monkeypatch):
    # (Walks: what the road watcher calls for each recorded walk) Record's stairs marks count points from 1, its picks
    # are where the pick changed (`pk`), Undercity's level has no terrain under it, and a walk that can't be worked
    # out (no client) waits (None)
    from types import SimpleNamespace as NS

    monkeypatch.setattr(R, "_FACES", {-7: (np.array(building(open_stairs=True), float), np.zeros((0, 3, 3)))})
    monkeypatch.setattr(R, "_PLACED", {})
    place = NS(wmo=-7, uid=7, x=0.0, y=0.0, z=0.0, yaw=180.0, tilt=0.0, rx=0.0, rz=0.0, bounds=(10, -8, 40, 8))
    flat = NS(sample=lambda X, Y: (np.zeros(len(X)), np.ones(len(X), bool)))
    logs = []
    w = R.Walks(lambda: object(), log=logs.append)
    w.ground[0], w.placements[0] = flat, [place]
    pts, _c, indoors, stairs = scene(open_stairs=True)
    a, b = stairs[0]
    walk_ = {"time": 5, "continent": 0, "coords": [list(p) for p in pts],
             "ind": "".join("1" if v else "0" for v in indoors), "stairs": [(a + 1, b + 1)], "pk": []}
    out = w(walk_)
    assert [p["stair"] for p in out] == [False, False, True, False] and out[-1]["zs"][-1] == 7.0
    # (no marks: the upper floor a doubt, logged; a floor picked upstairs settles it)
    out = w(dict(walk_, stairs=[]))
    assert out[-1]["zs"][-1] == 1.0 and any("could be on another floor" in m for m in logs)
    logs.clear()
    out = w(dict(walk_, stairs=[], pk=[(b + 7, 7.0)]))
    assert out[-1]["zs"][-1] == 7.0 and not logs
    # (Undercity's level: the model's floors only, so no piece is on the ground)
    out = w(dict(walk_, continent=10001, coords=[list(p) for p in pts if p[0] > 10]))
    assert all(p["zs"] is not None for p in out)
    # (no client: it waits)
    def fail():
        raise OSError("no client")
    assert R.Walks(fail, log=logs.append)(walk_) is None and "it waits" in logs[-1]

    def no_listfile():  # (cli._client exits when the client data's reference files are missing)
        raise SystemExit("missing data/ref/listfile.csv")
    assert R.Walks(no_listfile, log=logs.append)(walk_) is None  # (the watcher goes on; the walk waits)
    assert R.picks_of([(3, 7.5), (6, None)], 7) == [None, None, 7.5, 7.5, 7.5, None, None]
    assert R.picks_of([(2, None)], 3) is None


def test_a_recorded_walk_in_a_saved_file_ships_with_its_floors(client, tmp_path):
    # (end to end, as the road watcher does it: Record's walk, saved packed at logout, read back, its heights worked out
    # against the client, in as pieces: the street flat, the inn's floors with their heights, its stairs as stairs)
    import json

    from azerothgps.roads.tracks import floor_tracks, import_tracks

    cd, ground, placements = client
    pts = walk(INN)
    foot, top = pts.index((2259.0, 232.0)), pts.index((2263.0, 237.5))
    x0, y0, x1, y1 = INN_BOUNDS
    ind = "".join("1" if x0 < x < x1 and y0 < y < y1 else "0" for x, y in pts)
    pk = " ".join(f"{v:g}" for q in pts for v in q)
    sv = tmp_path / "WTF" / "ACC#1" / "SavedVariables"
    sv.mkdir(parents=True)
    (sv / "AzerothGPS.lua").write_text(f"""AzerothGPSDB = {{
  ["tracks"] = {{
    {{ ["op"] = "add", ["drawn"] = true, ["recorded"] = true, ["continent"] = 0, ["zone"] = "Tirisfal Glades",
      ["time"] = 1800000000, ["pk"] = "{pk}", ["rec"] = {{ ["ind"] = "{ind}", ["ts"] = "0" }},
      ["stairs"] = {{ {foot + 1}, {top + 1} }} }},
  }},
}}
""", encoding="utf-8")
    walks = R.Walks(lambda: cd, log=lambda *a: None)
    walks.ground[0], walks.placements[0] = ground, placements
    ov = tmp_path / "overrides"
    assert import_tracks(tmp_path / "WTF", ov, walks=walks) == 1
    feats = json.loads((ov / "roads_0.geojson").read_text())["features"]
    assert "zs" not in feats[0]["properties"]  # (the street: the land's flat build)
    assert any(f["properties"].get("stair") for f in feats)
    up = statistics.median(_upstairs_heights())
    last = [f for f in floor_tracks(ov)[0] if not f["stair"]][-1]
    assert abs(last["zs"][-1] - up) <= 1.0  # (the walk ends upstairs, at the upstairs roads' height)


def test_a_walk_through_a_portal_gets_its_floors_either_side_on_their_own(monkeypatch):
    # (Stormwind's Wizard's Sanctum, 2026-11-17: up the tower's stairs, through the portal at the top into the trainers'
    # room under the city, 9 yd on on the map. As one walk its floors dropped into the room halfway up the stairs, and
    # its roads joined the stairs to the room)
    land = (-9017.46, 885.90)  # (addon_data.TELEPORTERS: where #704 puts you)
    up = [(-9010.0 + k, 870.0) for k in range(8)]  # (the stairs, points 1-8; marked 2-7)
    room = [(land[0] + 1.0, land[1] - k) for k in range(5)]  # (a 9-yd hop onto the landing, then the room)
    pts = up + room
    assert R.portal_steps(pts) == [7]
    assert R.portal_steps(up) == [] and R.portal_steps(room) == []
    seen = []

    def candidates(cd, cont, ps, ground=None, placements=None, log=print):
        return [[R.Cand(0.0, "model")] for _ in ps]

    def assign(cands, indoors, stairs, picked=None, pts=None):
        seen.append((len(cands), list(stairs), indoors, picked))
        z0 = 130.0 if len(seen) == 1 else 30.0
        return [z0 + k for k in range(len(cands))], ["model"] * len(cands), []

    monkeypatch.setattr(R, "candidates", candidates)
    monkeypatch.setattr(R, "assign", assign)
    monkeypatch.setattr(R, "Ground", lambda cd, cont: None)
    monkeypatch.setattr(R.I, "placements", lambda cd, cont: None)
    w = R.Walks(lambda: object(), log=lambda *a: None)
    t = {"time": 1, "continent": 0, "coords": [list(p) for p in pts], "stairs": [(2, 7)],
         "ind": "0" * 8 + "1" * 5, "pk": [(1, 120.0), (10, 31.0)]}
    out = w(t)
    # (each side worked out alone: the stairs and picks with it, counted from its own first point)
    assert [s[0] for s in seen] == [8, 5]
    assert seen[0][1] == [(1, 6)] and seen[1][1] == []
    assert seen[0][2] == "0" * 8 and seen[1][2] == "1" * 5
    assert seen[0][3][0] == 120.0 and seen[1][3] == [120.0, 31.0, 31.0, 31.0, 31.0]
    # (and no road across the hop)
    ups, rooms = {tuple(p) for p in up}, {tuple(p) for p in room}
    assert out and all({tuple(q) for q in pc["coords"]} <= ups or {tuple(q) for q in pc["coords"]} <= rooms
                       for pc in out)
    assert any(pc["coords"][0] == list(room[0]) for pc in out)


# Up Grom'gol's zeppelin tower (Stranglethorn Vale, recorded in game 2026-11-18): from the road outside to its foot,
# round the spiral stairs (Stairs Start / End at points 37 and 71, from 1) and onto the landing up top.
GROMGOL = ("-12396.1 177 -12395.3 179.4 -12394.6 182.3 -12394.1 185.2 -12393.7 187.2 -12393.4 190.1 -12393.3 192.1 "
           "-12393.5 195.1 -12393.8 197.1 -12394.5 200 -12395 202 -12395.6 204 -12396.4 205.9 -12397.3 207.8 "
           "-12398.3 209.6 -12399.5 211.3 -12400.7 212.9 -12402.7 215.1 -12404.1 216.4 -12404.2 217.4 -12406.7 219.1 "
           "-12408.2 220.3 -12409.4 221.8 -12412.1 222.8 -12413.4 224.4 -12415.2 225.4 -12417 226.4 -12419 227 "
           "-12422 227.2 -12424.9 226.6 -12425.8 226.1 -12426.5 223.2 -12427.1 220.3 -12427.3 218.3 -12427.4 216.2 "
           "-12427.3 214.2 -12427.3 214 -12427.1 212 -12426.9 210 -12427.1 207.9 -12427.8 205.1 -12429.4 203.9 "
           "-12430.5 203.7 -12433.1 205.2 -12434.2 206.9 -12434.4 208.9 -12433 211.4 -12431 211.9 -12428.4 210.8 "
           "-12427.1 208.3 -12427.8 206.3 -12430 204.3 -12431 204.1 -12433.5 205.5 -12434.1 207.3 -12432.8 209.9 "
           "-12431.1 211 -12428.3 211.4 -12426.1 209.7 -12426 207.7 -12426.9 205.9 -12429.2 204.1 -12431.2 203.9 "
           "-12433.7 205.3 -12434.5 206.1 -12434.9 209.1 -12433.6 211.7 -12432 212.9 -12430 213.1 -12428.1 212.2 "
           "-12426.8 210.3 -12424.4 209.9 -12422.4 209.5 -12420.4 209 -12418.4 208.6 -12415.5 208")


def test_gromgols_tower_climbs_with_its_stairs_marks_and_not_from_the_line_alone(client):
    # (2026-11-18: "the path is flat and doesn't show where I started/stopped stairs". The game gives no height, so the
    # walk is flat in game until it's imported; the import puts its climb on the tower's stairs from Record's marks. A
    # road drawn the same way, with no marks, can't be told from a walk round the tower's ground floor: the floors are
    # stacked over the same spot, so its heights are left to Record's Stairs marks)
    cd, ground, placements = client
    v = [float(x) for x in GROMGOL.split()]
    pts = list(zip(v[::2], v[1::2]))
    assert len(pts) == 76
    cands = R.candidates(cd, 0, pts, ground, placements)
    stairs = [(36, 70)]
    zs, kinds, ambiguous = R.assign(cands, "0" * len(pts), stairs)
    assert ambiguous == [] and kinds[0] == "ground" and kinds[-1] == "model"
    out = R.pieces(pts, zs, kinds, stairs)
    assert out[0]["zs"] is None  # (the road outside: the land's flat build)
    (flight,) = [p for p in out if p["stair"]]
    foot, top = flight["zs"][0], flight["zs"][-1]
    assert top - foot >= 25 and all(b >= a - 0.05 for a, b in zip(flight["zs"], flight["zs"][1:]))
    assert abs(out[-1]["zs"][-1] - top) <= 1.0  # (the landing up top)
    # (no marks: the tower's ground floor all the way round, and the climb a doubt the watcher logs)
    zs, _kinds, ambiguous = R.assign(cands, None, [])
    assert max(zs) - foot < 2 and ambiguous
