"""Stairs on the open world's grid routes (item 49, Kooki3z: "directions aren't considering steps/floors in the world").
World-grid walks carry their heights as the route's floors (fz), which Turns.Stairs didn't read: up to Booty Bay's inn's
upper floor, 11 yd, nothing said. Now a steep piece (Turns.GRID_STAIR_SLOPE), short, with both ends over the terrain's
ground (a building, a dock, a tower: not a hillside) is stairs. Theramore's inn (one of Data/Indoors.lua's buildings, in
by its door) said them already."""

import pytest

from test_map_redraw import game  # noqa: F401


@pytest.mark.parametrize("cont,start,stop,tz", [
    (0, (-14383.0, 487.0), (-14457.7, 495.3), 15.2),  # (Innkeeper Skindle, Booty Bay's inn, upstairs)
    (1, (-3680.0, -4388.0), (-3616.1, -4470.8), 14.3),  # (Innkeeper Janene, Theramore's inn)
], ids=["booty_bay_skindle", "theramore_janene"])
def test_an_upstairs_innkeeper_gets_take_the_stairs_up(game, cont, start, stop, tz):  # noqa: F811
    lua, ns = game
    R, WG, st, T = ns.Router, ns.WorldGrid, ns.settings.gps, ns.Turns
    st.worldGrid, st.cityGrid = True, True
    WG.Set(True)
    R.Reset()
    r = R.Route(cont, start[0], start[1], stop[0], stop[1], lua.table(tz=tz))
    part = lua.table(cont=cont, pts=r.pts, kinds=r.kinds, stop=1, fz=r.fz, zs=r.zs)
    p = T.Path(lua.table(parts=lua.table(part), legs=lua.table(lua.table(walk=True))))
    ms = T.Maneuvers(p)
    said = [str(ms[i].text) for i in range(1, len(ms) + 1)]
    assert "Take the stairs up" in said, said
    assert abs(r.fz[len(r.fz)] - tz) < 3  # (arrived on the innkeeper's floor)
