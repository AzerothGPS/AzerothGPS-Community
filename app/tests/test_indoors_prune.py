"""Phase 6's insides (asked 2026-10-06: every building with an NPC upstairs or in a cellar, "merged and pruned"):
pruned by the building alone (indoors.prune_cover: every point along every road within COVER_YD of a kept road, along
the roads, the ways in from the doors joined to the land's road), chains of short pieces one road each
(collapse_chains: the graph's cost is per road; stairs kept apart, and a node kept where the height bends), then the
nodes renumbered (compact). No NPC data goes into the roads."""

import heapq
import math

from azerothgps import indoors as D


def _building():
    """A made-up inside: a door (0) joined onto the land's road (join 1), a corridor east (2, 3, 4, 5: a node every
    3 yd), a side room north off its middle (6, 7), stairs up from its end (5 -> 8, source 6), a hall upstairs (8, 9,
    10), and a second door (11) on the corridor's far side, not joined to anything."""
    nodes = [(0, 0), (-10, 0), (3, 0), (6, 0), (9, 0), (12, 0), (6, 4), (6, 8), (15, 6), (18, 6), (21, 6), (12, -3)]
    zs = [10, None, 10, 10, 10, 10, 10, 10, 16, 16, 16, 10]
    seg = lambda a, b: [nodes[a], nodes[b]]  # noqa: E731
    edges = [(0, 1, seg(0, 1), 0), (0, 2, seg(0, 2), 0), (2, 3, seg(2, 3), 0), (3, 4, seg(3, 4), 0),
             (4, 5, seg(4, 5), 0), (3, 6, seg(3, 6), 0), (6, 7, seg(6, 7), 0), (5, 8, seg(5, 8), 6),
             (8, 9, seg(8, 9), 0), (9, 10, seg(9, 10), 0), (5, 11, seg(5, 11), 0)]
    return {"nodes": list(nodes), "zs": list(zs), "edges": list(edges), "doors": [0, 11], "joins": [1], "floors": [10, 16]}


def _along_the_roads(edges, kept_nodes):
    """Each node's yards along `edges` to the nearest of `kept_nodes`."""
    adj: dict = {}
    for a, c, pts, _s in edges:
        L = sum(math.dist(pts[i], pts[i + 1]) for i in range(len(pts) - 1))
        adj.setdefault(a, []).append((c, L))
        adj.setdefault(c, []).append((a, L))
    dist = {v: 0.0 for v in kept_nodes}
    heap = [(0.0, v) for v in kept_nodes]
    while heap:
        d, v = heapq.heappop(heap)
        if d > dist[v]:
            continue
        for w, L in adj.get(v, ()):
            if d + L < dist.get(w, math.inf):
                dist[w] = d + L
                heapq.heappush(heap, (d + L, w))
    return dist


def test_pruning_keeps_every_road_within_reach_along_the_roads_and_the_doors_ways_in():
    b = _building()
    roads = list(b["edges"])
    left_out = D.prune_cover(b, cover_yd=4.0)
    assert left_out >= 1
    kept_roads = set(map(lambda e: (e[0], e[1]), b["edges"]))
    kept = {v for e in b["edges"] for v in e[:2]}
    dist = _along_the_roads(roads, kept)
    # (every point along every road, every COVER_STEP: within 4 yd of a kept road, along the roads)
    for a, c, pts, _s in roads:
        if (a, c) in kept_roads:
            continue
        L = math.dist(pts[0], pts[-1])
        for t, _x, _y in D._road_points(pts, D.COVER_STEP):
            assert min(dist.get(a, math.inf) + t, dist.get(c, math.inf) + L - t) <= 4.0 + 1e-9, (a, c, t)
    assert (0, 1) in kept_roads and (0, 2) in kept_roads  # (the joined door, its join onto the land's road)
    assert (5, 8) in kept_roads  # (up the stairs to the hall)
    assert (5, 11) not in kept_roads or 11 in kept  # (the door no road outside comes to: only for the cover)


def test_a_room_across_a_wall_isnt_covered_by_the_corridor():
    # (cover along the roads, not in a straight line: room B's road ends 3 yd from the corridor's, behind its wall,
    # and is reached the long way round; kept, or its NPC's route ended in the corridor and walked through the wall)
    nodes = [(0, 0), (-10, 0), (12, 0), (12, 12), (0, 12), (0, 4), (10, 2), (70, 0)]
    zs = [10, None, 10, 10, 10, 10, 10, 10]
    seg = lambda a, b: [nodes[a], nodes[b]]  # noqa: E731
    edges = [(0, 1, seg(0, 1), 0), (0, 2, seg(0, 2), 0), (2, 7, seg(2, 7), 0), (2, 3, seg(2, 3), 0),
             (3, 4, seg(3, 4), 0), (4, 5, seg(4, 5), 0), (5, 6, seg(5, 6), 0)]
    b = {"nodes": nodes, "zs": zs, "edges": edges, "doors": [0], "joins": [1], "floors": [10]}
    D.prune_cover(b, cover_yd=4.0)
    assert (5, 6) in {(e[0], e[1]) for e in b["edges"]}


def test_a_piece_no_joined_door_leads_to_is_left_out():
    # (phase 6's doors take no gap links: a piece of the inside with no door joined to the land's road couldn't be
    # reached, so it isn't kept)
    b = _building()
    b["nodes"] += [(40, 40), (46, 40)]
    b["zs"] += [10, 10]
    b["edges"].append((12, 13, [(40, 40), (46, 40)], 0))
    b["doors"].append(12)
    D.prune_cover(b, cover_yd=4.0)
    assert all(12 not in e[:2] and 13 not in e[:2] for e in b["edges"])
    assert any(e[:2] == (0, 1) for e in b["edges"])


def test_doors_joined_side_by_side_are_thinned_but_every_piece_keeps_a_way_in():
    # (spread_joins: of doors joined to the land's road within JOIN_SPREAD_YD of each other, the shortest join; a piece
    # of the inside of its own keeps its shortest whatever: Darkshire's town hall's dais lost its only one, and its NPC's
    # route ended 16 yd off, 2026-10-06)
    nodes = [(0, 0), (-5, 0), (3, 0), (3, -6), (-9, -6), (8, 0), (14, 0), (12, -4), (12, -14)]
    zs = [10, None, 10, 10, None, 10, 10, 10, None]
    seg = lambda a, b: [nodes[a], nodes[b]]  # noqa: E731
    edges = [(0, 1, seg(0, 1), 0),  # (door 0, joined 5 yd)
             (0, 2, seg(0, 2), 0), (2, 3, seg(2, 3), 0), (3, 4, seg(3, 4), 0),  # (door 3, 6 yd off, joined 12 yd)
             (2, 5, seg(2, 5), 0),
             (6, 7, seg(6, 7), 0), (7, 8, seg(7, 8), 0)]  # (a piece of its own: door 7, 13 yd off, joined 10 yd)
    b = {"nodes": nodes, "zs": zs, "edges": edges, "doors": [0, 3, 7], "joins": [1, 4, 8], "floors": [10]}
    assert D.spread_joins(b, spread_yd=20.0) == 1
    assert sorted(b["joins"]) == [1, 8]  # (door 3's join, beside door 0's, went; the piece's own stayed)
    assert all(4 not in e[:2] for e in b["edges"])


def test_chains_become_one_road_each_and_stairs_stay_apart():
    b = _building()
    before = len(b["edges"])
    fewer = D.collapse_chains(b)
    assert fewer > 0 and len(b["edges"]) == before - fewer
    ends = {(min(a, c), max(a, c)) for a, c, _p, _s in b["edges"]}
    assert (5, 8) in ends  # (the stairs: a road of their own, between the floors)
    hall = [e for e in b["edges"] if {e[0], e[1]} == {8, 10}]
    assert hall and hall[0][2] in ([(15, 6), (18, 6), (21, 6)], [(21, 6), (18, 6), (15, 6)])  # (8-9-10, in order)
    corridor = [e for e in b["edges"] if {e[0], e[1]} == {3, 5}]
    assert corridor and corridor[0][2] in ([(6, 0), (9, 0), (12, 0)], [(12, 0), (9, 0), (6, 0)])
    D.compact(b)
    n = len(b["nodes"])
    assert all(0 <= a < n and 0 <= c < n for a, c, _p, _s in b["edges"]) and len(b["zs"]) == n
    assert b["joins"] and all(0 <= j < n for j in b["joins"]) and all(0 <= d < n for d in b["doors"])
    # (each road's points still start and end at its nodes)
    for a, c, pts, _s in b["edges"]:
        assert tuple(pts[0]) == tuple(b["nodes"][a]) and tuple(pts[-1]) == tuple(b["nodes"][c])


def test_a_chain_keeps_its_nodes_where_the_height_bends():
    # (the game reads a road's floor along it from its two ends' heights: a corridor and its ramp up as one road was a
    # floor halfway between, and the route ended on the wrong floor; Stonard's great hall, 2026-10-06)
    nodes = [(0, 0), (3, 0), (6, 0), (9, 0), (12, 0), (15, 0)]
    zs = [0.0, 0.0, 0.0, 3.0, 6.0, 6.0]
    edges = [(i, i + 1, [nodes[i], nodes[i + 1]], 0) for i in range(5)]
    b = {"nodes": nodes, "zs": zs, "edges": edges, "doors": [0], "joins": [], "floors": [0.0, 6.0]}
    D.collapse_chains(b)
    assert sorted((min(a, c), max(a, c)) for a, c, _p, _s in b["edges"]) == [(0, 2), (2, 4), (4, 5)]
