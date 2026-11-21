"""cityroads.py (issue #829): the capitals' roads straightened and thinned over a navmesh, as a post-process of the
shipped Capitals.lua. The meshes are dev data (data/navmesh/, never in git), so these use a stand-in mesh."""

import math

from azerothgps import cityroads as C


class FakeIndex:
    """A stand-in for navcompare.PolyIndex: floors as axis-aligned boxes (x0, y0, x1, y1, height)."""

    def __init__(self, boxes):
        self.boxes = boxes
        self.box = (min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes))

    def floors(self, x, y, reach):
        out = []
        for k, (x0, y0, x1, y1, h) in enumerate(self.boxes):
            d = math.hypot(max(x0 - x, 0, x - x1), max(y0 - y, 0, y - y1))
            if d <= reach:
                out.append((h, k, d))
        return out


def entry(nodes, edges, nz=None, joins=(), drops=None):
    return C.Entry('  overlays[#overlays + 1] = { capital = "capitals",', list(nodes),
                   list(nz or [10] * len(nodes)), [C.Edge(a, b, round(C.path_yards(p)), s, list(p)) for a, b, s, p in edges],
                   list(joins), dict(drops or {}))


def test_every_capitals_entry_reads_and_writes_back_exactly():
    lines = C.capitals_path().read_text(encoding="utf-8").split("\n")
    for cont in (0, 1):
        for label in ("capitals", "capitals (under others, in a mountain)"):
            e = C.read_entry(lines, cont, label)
            a, b = e.span
            assert C.entry_lines(e) == lines[a:b + 1], (cont, label)
            assert all(0 <= j < len(e.nodes) for j in e.joins)
            assert all(0 <= d.a < len(e.nodes) and 0 <= d.b < len(e.nodes) for d in e.edges)
            assert all(d.pts[0] == e.nodes[d.a] and d.pts[-1] == e.nodes[d.b] for d in e.edges)


def test_points_pack_and_unpack():
    pts = [(2205, -4741), (2203, -4744), (2240, -4700), (2240, -4700), (1300, -4000)]
    assert C.unpack(C.pack(pts), *pts[0]) == pts


def test_a_zigzag_over_an_open_floor_is_pulled_straight():
    w = C.MeshWalk(FakeIndex([(0, 0, 100, 100, 10)]))
    zig = [(10, 50), (20, 56), (30, 44), (40, 56), (50, 44), (60, 50)]
    e = entry([zig[0], zig[-1]], [(0, 1, 0, zig)])
    walked = {0: C.walk_edge(w, e, e.edges[0])}
    assert C.straighten(w, e, {0}, walked) == 4
    assert e.edges[0].pts == [zig[0], zig[-1]]


def test_a_road_round_a_hole_keeps_its_bend_and_one_over_it_is_flagged():
    # (two floors joined only along the north: y 80-100 from x 40 to 60)
    w = C.MeshWalk(FakeIndex([(0, 0, 40, 100, 10), (60, 0, 100, 100, 10), (40, 80, 60, 100, 10)]))
    round_ = [(20, 50), (30, 90), (70, 90), (80, 50)]
    over = [(20, 40), (50, 40), (80, 40)]
    e = entry([round_[0], round_[-1], over[0], over[-1]], [(0, 1, 0, round_), (2, 3, 0, over)])
    walked = {i: C.walk_edge(w, e, ed) for i, ed in enumerate(e.edges)}
    assert walked[1] is None  # (the mesh can't walk it: flagged for recording, left as it is)
    C.straighten(w, e, {0, 1}, walked)
    assert e.edges[0].pts == round_
    assert e.edges[1].pts == over
    assert C._flag(w, e, 1)["why"] == "it leaves the mesh"


def test_a_straight_line_up_onto_another_floor_is_not_taken():
    # (a floor at 10 and a bridge over it at 20; a road along the lower floor bending under the bridge's ends)
    w = C.MeshWalk(FakeIndex([(0, 0, 100, 30, 10), (40, 30, 60, 70, 20), (0, 70, 100, 100, 10)]))
    road = [(10, 10), (90, 10), (90, 90)]
    e = entry([road[0], road[-1]], [(0, 1, 0, road)])
    walked = {0: C.walk_edge(w, e, e.edges[0])}
    C.straighten(w, e, {0}, walked)
    assert e.edges[0].pts == road  # (straight across crosses the gap at x 0-40, y 30-70: no floor)


def test_the_web_loses_a_parallel_road_but_never_a_join_stairs_or_one_off_the_mesh():
    w = C.MeshWalk(FakeIndex([(0, 0, 100, 100, 10)]))
    nodes = [(10, 10), (60, 10), (60, 12), (10, 90), (60, 90)]
    edges = [
        (0, 1, 0, [(10, 10), (60, 10)]),
        (0, 2, 0, [(10, 10), (30, 14), (60, 12)]),  # (beside the first, its end 2 yd off)
        (1, 2, 0, [(60, 10), (60, 12)]),
        (0, 3, 6, [(10, 10), (10, 90)]),  # stairs
        (3, 4, 0, [(10, 90), (60, 90)]),
        (0, 4, 0, [(10, 10), (60, 90)]),  # (a shortcut: the others are much longer)
    ]
    e = entry(nodes, edges, joins=[4])
    walked = {i: C.walk_edge(w, e, ed) for i, ed in enumerate(e.edges)}
    drop = C.thin(e, set(range(len(edges))), walked)
    assert drop == {1}


def test_two_roads_meet_as_one_unless_the_node_is_a_join_or_by_a_place():
    w = C.MeshWalk(FakeIndex([(0, 0, 100, 100, 10)]))
    nodes = [(10, 50), (50, 52), (90, 50)]
    edges = [(0, 1, 0, [(10, 50), (50, 52)]), (1, 2, 0, [(50, 52), (90, 50)])]
    for joins, places, merged in (((), (), 1), ((1,), (), 0), ((), ((55, 60),), 0)):
        e = entry(nodes, edges, joins=joins)
        walked = {i: C.walk_edge(w, e, ed) for i, ed in enumerate(e.edges)}
        gone = set()
        assert C.merge(w, e, {0, 1}, gone, walked, places) == merged
        if merged:
            C.compact(e, gone)
            assert len(e.edges) == 1 and e.edges[0].pts == [(10, 50), (90, 50)]
            assert e.nodes == [(10, 50), (90, 50)]


def test_two_roads_dont_meet_as_one_where_the_heights_read_would_miss_the_node():
    # (a ramp up to the middle and down again: straight between the ends' heights misses the top by 10 yd)
    w = C.MeshWalk(FakeIndex([(0, 0, 100, 100, 10)]))
    nodes = [(10, 50), (50, 50), (90, 50)]
    e = entry(nodes, [(0, 1, 0, [(10, 50), (50, 50)]), (1, 2, 0, [(50, 50), (90, 50)])], nz=[10, 20, 10])
    walked = {0: [10, 10], 1: [10, 10]}
    assert C.merge(w, e, {0, 1}, set(), walked) == 0


def test_shipped_orgrimmar_roads_are_whole():
    """Orgrimmar's roads as written by `agps city-roads --write`: every node used, joins kept, the drops' roads drops."""
    lines = C.capitals_path().read_text(encoding="utf-8").split("\n")
    e = C.read_entry(lines, 1)
    used = {n for d in e.edges for n in (d.a, d.b)}
    assert used | set(e.joins) == set(range(len(e.nodes)))
    assert all(e.edges[i].src == 3 for i in e.drops)
    org = C.city_edges(e, (1269, -4978, 2314, -3759))
    assert sum(1 for i in org if e.edges[i].src == 6) > 0 and sum(1 for i in org if e.edges[i].src == 5) == 0
