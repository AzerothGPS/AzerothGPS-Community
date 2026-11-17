"""doodads.py reads an M2's collision mesh (the header's collisionIndices / collisionPositions) and places it in the world;
a model without one (a bush) is walked through. (`agps doodads`: what route tests in game bumped into, 2026-10-08.)"""

import struct
from types import SimpleNamespace

import numpy as np

from azerothgps import doodads as D


def m2(verts, tris, chunked=True) -> bytes:
    """A minimal M2: the MD20 header with only the collision arrays set, the data after it."""
    head = bytearray(240)
    head[0:4] = b"MD20"
    vdata = b"".join(struct.pack("<3f", *v) for v in verts)
    idata = b"".join(struct.pack("<3H", *t) for t in tris)
    struct.pack_into("<II", head, 216, 3 * len(tris), 240 + len(vdata) if tris else 0)
    struct.pack_into("<II", head, 224, len(verts), 240 if verts else 0)
    md20 = bytes(head) + vdata + idata
    if not chunked:
        return md20
    return b"MD21" + struct.pack("<I", len(md20)) + md20 + b"SFID" + struct.pack("<I", 0)


def fake_cd(files):
    return SimpleNamespace(casc=SimpleNamespace(read=lambda fid: files[fid]))


def test_a_models_collision_is_read_and_placed():
    D._COLLISION.clear()
    verts = [(0, 0, 0), (1, 0, 0), (0, 1, 0), (0, 0, 2)]
    cd = fake_cd({10: m2(verts, [(0, 1, 3), (0, 2, 3)]), 11: m2(verts, [(0, 1, 3)], chunked=False), 12: m2([], [])})
    V, idx = D.m2_collision(cd, 10)
    assert V.shape == (4, 3) and idx.tolist() == [[0, 1, 3], [0, 2, 3]]
    assert D.m2_collision(cd, 11)[1].tolist() == [[0, 1, 3]]  # (an old file: the MD20 on its own)
    assert D.m2_collision(cd, 12) is None  # (a bush: none)
    # (placed: turned, scaled 2x and moved)
    d = D.Doodad(10, 1, 100.0, 200.0, 50.0, D._turn(0.0) * 2.0)
    T = D.triangles(cd, d)
    assert T.shape == (2, 3, 3)
    assert np.allclose(T[0, 0], (100, 200, 50)) and np.allclose(T[0, 2], (100, 200, 54))  # (its top 2 x 2 yd up)
    assert np.allclose(np.hypot(T[0, 1, 0] - 100, T[0, 1, 1] - 200), 2.0)
    walls = D.walls(cd, [d])
    assert len(walls) == 2 and walls[0][0] == (50.0, 54.0)


def test_a_wmo_doodad_set_is_its_own_and_set_zero():
    D._SETS.clear()
    def chunk(magic, data):
        return magic[::-1].encode() + struct.pack("<I", len(data)) + data
    mods = b"".join(name.ljust(20, b"\0") + struct.pack("<III", first, count, 0)
                    for name, first, count in ((b"Default", 0, 1), (b"Night", 1, 1), (b"Day", 2, 1)))
    modi = struct.pack("<3I", 501, 502, 503)
    modd = b"".join(struct.pack("<I3f4ff I", i, float(i), 0.0, 0.0, 0.0, 0.0, 0.0, 1.0, 1.0, 0) for i in range(3))
    wmo = chunk("MODS", mods) + chunk("MODI", modi) + chunk("MODD", modd)
    cd = fake_cd({900: wmo})
    p = SimpleNamespace(wmo=900, uid=7, x=0.0, y=0.0, z=0.0, yaw=0.0, rx=0.0, rz=0.0, doodad_set=2)
    assert sorted(d.fid for d in D.wmo_doodads(cd, p)) == [501, 503]
