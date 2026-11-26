"""A dungeon with several ways in routes to the one picked (item 45b, Kooki3z 2026-11-24: Maraudon's Orange portal clicked,
the route went to the Purple one). Its map opened from an entrance's icon shows that wing; Route Here (G.RouteHere) and
a spot picked on it (G.AddStopAt) both stop at that wing's way in (GPSFrame's G.InstanceStopEntrance), for every
instance whose ways in are wings (Maraudon, Scarlet Monastery, Dire Maul, ...)."""

import pytest

from test_map_redraw import game  # noqa: F401


def _wings(ns):
    out = []
    for lvl, info in ns.Instances.items():
        ents = info.entrances
        if not ents or len(ents) < 2:
            continue
        for i in range(1, len(ents) + 1):
            e = ents[i]
            if e[7] and e[4] and e[5]:
                out.append((int(lvl), str(e[7]), int(e[1]), float(e[2]), float(e[3]), float(e[4]), float(e[5])))
    return out


def test_route_here_and_a_spot_picked_go_to_the_wing_s_own_way_in(game):  # noqa: F811
    lua, ns = game
    G, N = ns.GPS, ns.Nav
    wings = _wings(ns)
    assert any(w[0] == 20349 and w[1] == "Orange" for w in wings) and len(wings) >= 4
    lua.execute("AGPS_POS = { -1300.0, 2500.0, 1 }; AGPS_MAP = 1443; AGPS_LEVEL = 60")  # (no zone too high to ask about)
    try:
        for lvl, wing, cont, ex, ey, ix, iy in wings:
            # (Route Here on the wing's map)
            N.Clear()
            G.Follow()
            G.ShowInstance(lvl, wing)
            if G.InstanceWing(lvl) != wing:
                continue  # (a wing with no map of its own: not picked by its map)
            G.RouteHere()
            d = N.stops[1]
            # (a wing with two doors, Dire Maul East's: either of them)
            doors = [(w[3], w[4]) for w in wings if w[0] == lvl and w[1] == wing]
            assert d and any(abs(d.x - a) < 1 and abs(d.y - b) < 1 for a, b in doors), (lvl, wing, d and (d.x, d.y), doors)
            # (a spot picked on it, by its own way in)
            N.Clear()
            G.ShowInstance(lvl, wing)
            G.AddStopAt(ix, iy, "x", lvl)
            G.ConfirmPendingOnClose()
            d = N.stops[1]
            assert d and abs(d.x - ex) < 1 and abs(d.y - ey) < 1, (lvl, wing, "picked", d and (d.x, d.y), (ex, ey))
    finally:
        lua.execute("AGPS_LEVEL = nil")
        N.Clear()
        G.Follow()
