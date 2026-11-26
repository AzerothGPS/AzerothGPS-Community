"""The grid's links that cross a model's wall the walk mesh lost (item 72, Kooki3z: "make sure we are checking the whole
map for these thin wall conditions"): worldgrid.cut_wall_links cuts a link whose line, at each of WALL_BODY_Z over its
floors, crosses a steep model face (a palisade, a fence, a barricade's plank); a floor, a ceiling or a low curb doesn't
cut it, nor a wall beside the link."""

import numpy as np

from azerothgps import worldgrid as WG


def _wall(x, y0, y1, z0, z1):
    """A vertical wall at x from y0 to y1, z0 up to z1: two triangles."""
    a, b, c, d = (x, y0, z0), (x, y1, z0), (x, y1, z1), (x, y0, z1)
    return [[a, b, c], [a, c, d]]


def _links(tmp_path, tris, surf, links):
    p = tmp_path / "t.models.npy"
    np.save(p, np.asarray(tris, np.float32))
    return WG.cut_wall_links(surf, links, p)


def _grid():
    # (two cells side by side along x, one surface each at z 0: (0,0) and (1,0), linked east and west)
    surf = {(0, 0): [[0.0, set([1]), 4.0, 0.0]], (1, 0): [[0.0, set([1]), 6.0, 0.0]]}
    east, west = WG.DIRS.index((1, 0)), WG.DIRS.index((-1, 0))
    links = {(0, 0, 0): [-1] * 8, (1, 0, 0): [-1] * 8}
    links[(0, 0, 0)][east] = 0
    links[(1, 0, 0)][west] = 0
    return surf, links, east, west


def test_a_fence_across_the_link_cuts_it_both_ways(tmp_path):
    surf, links, east, west = _grid()
    assert _links(tmp_path, _wall(5.0, -3, 3, 0, 1.6), surf, links) == 2
    assert links[(0, 0, 0)][east] == -1 and links[(1, 0, 0)][west] == -1


def test_a_curb_a_floor_or_a_wall_beside_it_doesnt(tmp_path):
    for tris in (_wall(5.0, -3, 3, 0, 0.3),  # (a curb: under the lowest body height)
                 [[(3, -3, 0.8), (7, -3, 0.8), (7, 3, 0.8)], [(3, -3, 0.8), (7, 3, 0.8), (3, 3, 0.8)]],  # (a floor over)
                 _wall(5.0, 2, 6, 0, 3)):  # (a wall beside the link, not across it)
        surf, links, east, west = _grid()
        assert _links(tmp_path, tris, surf, links) == 0, tris
        assert links[(0, 0, 0)][east] == 0


def test_a_drop_is_judged_at_the_top_floor(tmp_path):
    # (the first full bake cut 1.1 million links, median a 42 yd drop: a drop's straight line from the top floor to the
    # bottom one runs through the face it falls down. A drop is judged along a level line at its top floor's heights:
    # the cliff face under the edge doesn't cut it, a palisade on the rim does (item 43, Red Cloud Mesa).)
    surf, links, east, west = _grid()
    surf[(1, 0)][0][0] = -20.0  # (the east cell 20 yd below: a ledge's foot)
    links[(1, 0, 0)][west] = -1  # (a drop: no way back up)
    assert _links(tmp_path, _wall(5.0, -3, 3, -20, -0.2), surf, links) == 0  # (the cliff face, under the rim)
    assert links[(0, 0, 0)][east] == 0
    assert _links(tmp_path, _wall(5.0, -3, 3, -20, 3.0), surf, links) == 1  # (a palisade standing on the rim)
    assert links[(0, 0, 0)][east] == -1


def test_a_stair_walked_both_ways_is_judged_along_its_line(tmp_path):
    # (a stair climbing more than WALL_MAX_DZ, linked both ways, judged at the top floor's height ran through its
    # stairwell's wall: six upstairs innkeepers lost. Linked back, it's judged along its own line.)
    surf, links, east, west = _grid()
    surf[(1, 0)][0][0] = 3.0  # (the east cell 3 yd up the stair)
    wall = _wall(5.0, -3, 3, 2.5, 6.0)  # (the stairwell's wall over the stair's lower half: above its line)
    assert _links(tmp_path, wall, surf, links) == 0
    assert links[(0, 0, 0)][east] == 0 and links[(1, 0, 0)][west] == 0


class _M:
    def __init__(self, vs):
        self.vs = vs


def test_a_wall_the_mesh_knows_keeps_its_link(tmp_path):
    # (a building's inner wall leaves a gap in the walk mesh: the grid's 8 yd link across it stands for the mesh's way
    # round through a door, and cutting it left six upstairs innkeepers unreachable. Only a wall the mesh lost, the mesh
    # running straight over it (a fence, a palisade), cuts the link.)
    fence = _wall(5.0, -3, 3, 0, 1.6)
    whole = _M([[(0.0, -5.0, 0.0), (10.0, -5.0, 0.0), (10.0, 5.0, 0.0), (0.0, 5.0, 0.0)]])  # (over the fence: lost it)
    gap = _M([[(0.0, -5.0, 0.0), (4.4, -5.0, 0.0), (4.4, 5.0, 0.0), (0.0, 5.0, 0.0)],
              [(5.6, -5.0, 0.0), (10.0, -5.0, 0.0), (10.0, 5.0, 0.0), (5.6, 5.0, 0.0)]])  # (a gap along it: knows it)
    surf, links, east, west = _grid()
    p = tmp_path / "t.models.npy"
    np.save(p, np.asarray(fence, np.float32))
    assert WG.cut_wall_links(surf, links, p, gap) == 0
    assert WG.cut_wall_links(surf, links, p, whole) == 2


def test_a_wall_on_a_rim_flags_the_surface(tmp_path):
    # (item 43: Red Cloud Mesa's palisade, which the mesh knows, has no link to cut, but the search's falls off the rim,
    # WorldGrid.FarDrops, went over it. A surface with an unlinked way out that a wall stands across within
    # RIM_WALL_CELLS cells is flagged, F_RIM_WALL: no fall starts there.)
    surf, links, east, west = _grid()
    p = tmp_path / "t.models.npy"
    np.save(p, np.asarray(_wall(9.0, -3, 3, -10, 3.0), np.float32))  # (a palisade 5 yd east of the east cell)
    rim = set()
    WG.cut_wall_links(surf, links, p, None, rim, 8.333)
    assert (1, 0, 0) in rim and (0, 0, 0) not in rim  # (the west cell's ways out: none through the palisade)
    rim = set()
    np.save(p, np.asarray(_wall(9.0, -3, 3, -10, -0.5), np.float32))  # (the rim's own face, under the edge)
    WG.cut_wall_links(surf, links, p, None, rim, 8.333)
    assert not rim


def test_a_post_or_a_trunk_on_a_rim_doesnt_flag_it(tmp_path):
    # (a trunk on a slope flagged a tenth of all surfaces: a player steps round it. A wall stands across RIM_WIDE lines.)
    surf, links, east, west = _grid()
    p = tmp_path / "t.models.npy"
    np.save(p, np.asarray(_wall(9.0, -0.4, 0.4, -10, 3.0), np.float32))  # (a post 0.8 yd wide)
    rim = set()
    WG.cut_wall_links(surf, links, p, None, rim, 8.333)
    assert not rim


def test_a_drop_through_a_wall_the_mesh_knows_is_cut_too(tmp_path):
    # (item 78a: Red Cloud Mesa's palisade, which the mesh knows (a gap along it), was still jumped through by a 3.5 yd
    # drop link: the mesh's check is for a link standing for a walk round, never for a drop off the edge)
    surf, links, east, west = _grid()
    surf[(1, 0)][0][0] = -3.5  # (the east cell 3.5 yd below)
    links[(1, 0, 0)][west] = -1  # (a drop: no way back up)
    gap = _M([[(0.0, -5.0, 0.0), (4.4, -5.0, 0.0), (4.4, 5.0, 0.0), (0.0, 5.0, 0.0)],
              [(5.6, -5.0, -3.5), (10.0, -5.0, -3.5), (10.0, 5.0, -3.5), (5.6, 5.0, -3.5)]])
    p = tmp_path / "t.models.npy"
    np.save(p, np.asarray(_wall(5.0, -3, 3, -3.5, 3.0), np.float32))  # (the palisade on the rim)
    assert WG.cut_wall_links(surf, links, p, gap) == 1
    assert links[(0, 0, 0)][east] == -1


def test_a_drop_past_a_trunk_the_mesh_knows_is_kept(tmp_path):
    # (a drop past a wall the mesh knows is cut only by a wide one: a trunk or a post on a wooded slope, whose downhill
    # links are one way too, cut 505k links and stranded 65k surfaces of the biggest pieces)
    surf, links, east, west = _grid()
    surf[(1, 0)][0][0] = -3.5
    links[(1, 0, 0)][west] = -1
    gap = _M([[(0.0, -5.0, 0.0), (4.4, -5.0, 0.0), (4.4, 5.0, 0.0), (0.0, 5.0, 0.0)],
              [(5.6, -5.0, -3.5), (10.0, -5.0, -3.5), (10.0, 5.0, -3.5), (5.6, 5.0, -3.5)]])
    p = tmp_path / "t.models.npy"
    np.save(p, np.asarray(_wall(5.0, -0.4, 0.4, -3.5, 3.0), np.float32))  # (a trunk, 0.8 yd)
    assert WG.cut_wall_links(surf, links, p, gap) == 0
