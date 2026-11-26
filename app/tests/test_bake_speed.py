"""The bakes' speed-ups give the same data (perf/gpu-bake, 2026-11-23): the collision's big triangles found by their
own buckets (navfeatures.Tris), the mesh walk's links the nearest in height first (worldgrid.walked_links), and the
grid step's tiles skipped only when what they're made from is the same (worldgrid.tile_stamp)."""

import math
import random

import numpy as np
import pytest

from azerothgps import navfeatures as F
from azerothgps import worldgrid as W


def _brute(T, p, q):
    """The first hit along p -> q over every triangle (navfeatures.Tris.hits' rule, no buckets)."""
    t = F.Tris.__new__(F.Tris)
    t.T = np.asarray(T, np.float64)
    t.E1, t.E2 = t.T[:, 1] - t.T[:, 0], t.T[:, 2] - t.T[:, 0]
    t.zlo, t.zhi = t.T[:, :, 2].min(axis=1), t.T[:, :, 2].max(axis=1)
    t._cands = lambda *a: np.arange(len(t.T))  # noqa: E731
    return t.hit(p, q)


def test_the_collision_s_big_triangles_are_found_by_their_buckets():
    # (triangles of every size: small (one 4 yd bucket), big (more than 16 of those: a hall's floor, a wall's face) and
    # huge (more than 16 of the big ones' 64 yd buckets); segments up, down and across: the same first hit as every
    # triangle tested)
    rnd = random.Random(5)
    T = []
    for size in [2] * 300 + [40] * 200 + [600] * 10:
        x, y, z = rnd.uniform(-500, 500), rnd.uniform(-500, 500), rnd.uniform(0, 50)
        T.append([(x + rnd.uniform(-size, size), y + rnd.uniform(-size, size), z + rnd.uniform(-5, 5)) for _ in range(3)])
    tris = F.Tris(np.array(T))
    assert len(tris.big) and len(tris.huge)
    for _ in range(600):
        x, y, z = rnd.uniform(-520, 520), rnd.uniform(-520, 520), rnd.uniform(-10, 60)
        if rnd.random() < 0.5:
            p, q = (x, y, z + 30), (x, y, z - 30)
        else:
            p, q = (x, y, z), (x + rnd.uniform(-60, 60), y + rnd.uniform(-60, 60), z + rnd.uniform(-5, 5))
        assert tris.hit(p, q) == _brute(T, p, q), (p, q)


@pytest.mark.parametrize("accel", ["off", "numba"])
def test_the_walked_link_is_the_nearest_walk_before_any_drop(accel, monkeypatch):
    if accel == "numba":
        pytest.importorskip("numba")
    monkeypatch.setenv("AGPS_WG_ACCEL", accel)
    assert W.accel() == ("python" if accel == "off" else "numba")
    # (a ledge's top over two floors in the next cell, its foot 6 yd down off the edge and a ramp's top joined to it:
    # the ramp is walked (a walk before a drop), and with the ramp gone, the drop is the link)
    def surf(with_ramp):
        top = [(0, 0, 10), (10, 0, 10), (10, 10, 10), (0, 10, 10)]
        ramp = [(10, 0, 10), (20, 0, 11), (20, 10, 11), (10, 10, 10)]
        foot = [(10, 0, 4), (20, 0, 4), (20, 10, 4), (10, 10, 4)]
        polys = [(top, [-1, 1 if with_ramp else -1, -1, -1]), (foot, [-1, -1, -1, -1])]
        if with_ramp:
            polys.append((ramp, [-1, -1, -1, 0]))
            polys[0] = (top, [-1, 2, -1, -1])
        raw = [(p[0], p[1], 1) for p in polys]
        mesh = W._mesh(raw, [{q for q in p[1] if q >= 0} for p in polys])
        samples = {(0, 0): [(10.0, 0, 5.0, 5.0)], (1, 0): [(4.0, 1, 15.0, 5.0)]}
        s = {(0, 0): [[10.0, {0}, 5.0, 5.0]], (1, 0): [[4.0, {1}, 15.0, 5.0]]}
        if with_ramp:
            samples[(1, 0)].append((10.5, 2, 15.0, 5.0))
            s[(1, 0)].append([10.5, {2}, 15.0, 5.0])
        return s, mesh, samples
    s, mesh, samples = surf(True)
    links = W.walked_links(s, mesh, 10.0, samples, 0.0, 0.0)
    assert links[(0, 0, 0)][0] == 1  # (east: the ramp's top, walked)
    s, mesh, samples = surf(False)
    links = W.walked_links(s, mesh, 10.0, samples, 0.0, 0.0)
    assert links[(0, 0, 0)][0] == 0  # (east: the foot, a drop)
    assert links[(1, 0, 0)][2] == -1  # (and never back up)


def test_a_tile_s_grid_is_current_only_when_made_from_the_same(tmp_path, monkeypatch):
    monkeypatch.setenv("AGPS_WORLDMESH_DIR", str(tmp_path / "mesh"))
    monkeypatch.setenv("AGPS_WORLDGRID_DIR", str(tmp_path / "grid"))
    (tmp_path / "mesh").mkdir()
    (tmp_path / "mesh" / "0_30_30.bin").write_bytes(b"AGNT\0\0\0\0")
    assert not W.tile_current(0, 30, 30)  # (no grid yet)
    r = W.build_tile_job((0, 30, 30, 64))
    assert r["ok"], r
    assert W.tile_current(0, 30, 30)
    (tmp_path / "mesh" / "0_30_30.bin").write_bytes(b"AGNT\0\0\0\0\0\0\0\0\0")  # (the mesh built again, different)
    assert not W.tile_current(0, 30, 30)


def test_the_compiled_walk_s_float_steps_are_python_s():
    # (worldgrid_nb's hypot and floor division are CPython's to the last bit: a walk's length, step and cell the same)
    from azerothgps import worldgrid_nb as N
    rnd = random.Random(3)
    for _ in range(20000):
        a, b = rnd.uniform(-50, 50) * 10 ** rnd.randint(-4, 4), rnd.uniform(-50, 50) * 10 ** rnd.randint(-4, 4)
        assert N._hypot(a, b) == math.hypot(a, b), (a, b)
        c = rnd.choice([8.333333333333334, 4.166666666666667, 2.0, 3.0])
        assert N._floordiv(a, c) == a // c, (a, c)


def _two_cells(top_z, foot_z, gap, joined_corner=False):
    """Two cells' surfaces 10 yd apart: a top poly (x 0-10) and, `gap` yd past its edge, a foot poly at foot_z (x from
    10 + gap); `joined_corner`: instead, the foot touches the top only at the corner (10, 10), at the top's height."""
    top = [(0, 0, top_z), (10, 0, top_z), (10, 10, top_z), (0, 10, top_z)]
    if joined_corner:
        foot = [(10, 10, top_z), (20, 10, top_z), (20, 20, top_z), (10, 20, top_z)]
        samples = {(0, 0): [(top_z, 0, 5.0, 5.0)], (1, 1): [(top_z, 1, 10.0, 10.0)]}
        s = {(0, 0): [[top_z, {0}, 5.0, 5.0]], (1, 1): [[top_z, {1}, 10.0, 10.0]]}
    else:
        foot = [(10 + gap, 0, foot_z), (20, 0, foot_z), (20, 10, foot_z), (10 + gap, 10, foot_z)]
        samples = {(0, 0): [(top_z, 0, 5.0, 5.0)], (1, 0): [(foot_z, 1, 15.0, 5.0)]}
        s = {(0, 0): [[top_z, {0}, 5.0, 5.0]], (1, 0): [[foot_z, {1}, 15.0, 5.0]]}
    polys = [(top, [-1, -1, -1, -1]), (foot, [-1, -1, -1, -1])]
    raw = [(p[0], p[1], 1) for p in polys]
    mesh = W._mesh(raw, [set(), set()])
    return s, mesh, samples


@pytest.mark.parametrize("accel", ["off", "numba"])
def test_a_sheer_cliff_s_drop_is_found_on_along_the_line_both_walks(accel, monkeypatch):
    # (bake9: the foot's floor starts the agent's room off a sheer face, not under the top's edge: no drop link off
    # Skywatcher Plateau's east edge. Looked for on along the line, DROP_SCAN_YD, a fall of DROP_SCAN_MIN or more only)
    if accel == "numba":
        pytest.importorskip("numba")
    monkeypatch.setenv("AGPS_WG_ACCEL", accel)
    s, mesh, samples = _two_cells(130.0, 0.0, 1.0)
    assert W.walked_links(s, mesh, 10.0, samples, 0.0, 0.0)[(0, 0, 0)][0] == 0  # (the drop, past the 1 yd gap)
    s, mesh, samples = _two_cells(20.0, 0.0, 1.0)
    assert W.walked_links(s, mesh, 10.0, samples, 0.0, 0.0)[(0, 0, 0)][0] == -1  # (a 20 yd step past a gap: never)
    s, mesh, samples = _two_cells(130.0, 0.0, 4.0)
    assert W.walked_links(s, mesh, 10.0, samples, 0.0, 0.0)[(0, 0, 0)][0] == -1  # (past DROP_SCAN_YD: none)


@pytest.mark.parametrize("accel", ["off", "numba"])
def test_a_corner_two_pieces_share_is_never_arrived_at_both_walks(accel, monkeypatch):
    # (bake8's arrival rule, the compiled walk's too: Gurubashi Arena's ring walked into through its wall's end)
    if accel == "numba":
        pytest.importorskip("numba")
    monkeypatch.setenv("AGPS_WG_ACCEL", accel)
    s, mesh, samples = _two_cells(10.0, 10.0, 0.0, joined_corner=True)
    assert W.walked_links(s, mesh, 10.0, samples, 0.0, 0.0)[(0, 0, 0)][4] == -1  # (north-east: no link)


@pytest.mark.parametrize("accel", ["off", "numba"])
def test_a_drop_never_lands_under_ground_going_on_past_the_edge_both_walks(accel, monkeypatch):
    # (bake9: from the Barrens' ridge, 208, a 176 yd "drop" into Darkmist Cavern's tunnels under the ridge's own ground:
    # the ground past the edge, at its height, a piece of its own over the landing, is never fallen through)
    if accel == "numba":
        pytest.importorskip("numba")
    monkeypatch.setenv("AGPS_WG_ACCEL", accel)
    top = [(0, 0, 100), (10, 0, 100), (10, 10, 100), (0, 10, 100)]
    ground = [(10, 0, 99), (20, 0, 99), (20, 10, 99), (10, 10, 99)]
    tunnel = [(10, 0, 0), (20, 0, 0), (20, 10, 0), (10, 10, 0)]
    polys = [(top, [-1, -1, -1, -1]), (ground, [-1, -1, -1, -1]), (tunnel, [-1, -1, -1, -1])]
    mesh = W._mesh([(p[0], p[1], 1) for p in polys], [set(), set(), set()])
    samples = {(0, 0): [(100.0, 0, 5.0, 5.0)], (1, 0): [(0.0, 2, 15.0, 5.0), (99.0, 1, 15.0, 5.0)]}
    s = {(0, 0): [[100.0, {0}, 5.0, 5.0]], (1, 0): [[0.0, {2}, 15.0, 5.0], [99.0, {1}, 15.0, 5.0]]}
    assert W.walked_links(s, mesh, 10.0, samples, 0.0, 0.0)[(0, 0, 0)][0] == -1  # (not the tunnel's floor)
