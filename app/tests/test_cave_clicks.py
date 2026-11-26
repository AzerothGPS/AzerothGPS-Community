"""A click on the map over a cave means the floor the map shows (item 84, Kooki3z): with the cave's overlay up (hovered,
G.hoveredCave), the cave's floor there, routed in by its way in; without it, the ground over it, never the cave's floor
guessed (item 82g: a stop north of Lushwater Oasis took the Wailing Caverns' road under the hill). And a route to a
stop inside a cave keeps that cave's overlay shown, as if hovered (G.RouteCave)."""

from test_map_redraw import game  # noqa: F401

SPOT = (-569.8, -2291.7)  # (over the Wailing Caverns, north of Lushwater Oasis)


def test_a_click_over_a_cave_means_the_floor_the_map_shows(game):  # noqa: F811
    lua, ns = game
    G, WG = ns.GPS, ns.WorldGrid
    WG.Set(True)
    cave = G.CaveAt(1, *SPOT)
    assert cave is not None
    G.hoveredCave = None
    ground = G.ClickFloorZ(1, *SPOT)
    assert ground is not None and ground > 150  # (the hill's top: the map shows the land)
    G.hoveredCave = cave
    try:
        inside = G.ClickFloorZ(1, *SPOT)
        assert inside is not None and inside < ground - G.CAVE_UNDER_YD  # (the cave's floor under it)
    finally:
        G.hoveredCave = None


def test_a_route_to_a_stop_inside_a_cave_keeps_its_overlay(game):  # noqa: F811
    lua, ns = game
    G, N, WG = ns.GPS, ns.Nav, ns.WorldGrid
    WG.Set(True)
    cave = G.CaveAt(1, *SPOT)
    floor = G.CaveFloorZ(1, SPOT[0], SPOT[1], ns.Ground.Sample(1, *SPOT))
    assert floor is not None
    was = N.dest
    try:
        N.dest = lua.eval("{ x = %f, y = %f, cont = 1, z = %f }" % (SPOT[0], SPOT[1], floor))
        assert G.RouteCave(1) == cave
        N.dest = lua.eval("{ x = %f, y = %f, cont = 1, z = %f }" % (SPOT[0], SPOT[1], ns.Ground.Sample(1, *SPOT)))
        assert G.RouteCave(1) is None  # (a stop on the land over it: no cave shown)
    finally:
        N.dest = was


def test_a_cave_opened_from_its_icon_means_its_floor_too(game):  # noqa: F811
    # (item 84d, Kooki3z: the cave's map shown by clicking its entrance's icon (G.ShowCave) is the same as hovered: a
    # click in it means the cave's floor there, routed in by its way in)
    lua, ns = game
    G, WG = ns.GPS, ns.WorldGrid
    WG.Set(True)
    cave = G.CaveAt(1, *SPOT)
    G.hoveredCave = None
    ground = G.ClickFloorZ(1, *SPOT)
    assert G.ShowCave(1, cave)
    try:
        inside = G.ClickFloorZ(1, *SPOT)
        assert inside is not None and inside < ground - G.CAVE_UNDER_YD
    finally:
        G.Follow()
    assert G.ClickFloorZ(1, *SPOT) == ground  # (its map closed: the land again)
