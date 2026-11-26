"""The other faction's guard zones, drawn red (GPSFrame's G.LayAvoided): item 63c (Kooki3z 2026-11-24) drew those a route
went round; item 98 (2026-11-25) every one in the map's visible area, with or without a route, never the player's own
faction's ("standing near Astranaar as Horde, the zones show; as Alliance they don't"); item 86: no outline, just the flat
25% union, and the hover on the minimap square too. The option Show enemy areas (saved as showAvoided) hides them.
Kooki3z on 6195a75c ("red enemy zones now show everywhere"): as before 98, only those near the player (about the
minimap's view, Nav.ENEMY_NEAR_PLAYER_YD 300) or the route (ENEMY_NEAR_ROUTE_YD 200: those it bends round or passes).
Item 99: the hover and "Through enemy territory" name the real town, or the guards themselves."""

from test_map_redraw import game  # noqa: F401

ASTRANAAR = (2719.0, -379.0)  # (Ashenvale: the Alliance's sentinels)
SPLINTERTREE = (2185.0, -2487.0)  # (Ashenvale: the Horde's guards)


def _as(lua, ns, faction):
    lua.execute("UnitFactionGroup = function() return '%s' end" % faction)
    ns.CharDB().faction = faction


def _at(lua, x, y, cont=1):
    lua.execute(f"AGPS_POS = {{ {x}, {y}, {cont} }}")


def test_zones_near_the_player_show_without_a_route_and_never_the_players_own(game):  # noqa: F811
    lua, ns = game
    N, G, st = ns.Nav, ns.GPS, ns.settings.gps
    lua.execute("AGPS_UFG = UnitFactionGroup AGPS_POS_WAS = AGPS_POS")
    saved = ns.CharDB().faction
    N.route = None
    st.showAvoided = True
    try:
        x, y = ASTRANAAR
        _at(lua, x, y)
        _as(lua, ns, "Horde")
        n = G.LayAvoided(x, y, 1, 0, 1.0, 300)
        assert n > 0 and G.avoidedStripN > 0 and G.avoidedStrips[1]._shown
        f = G.avoidedPool[1]
        assert f._shown
        tips = set()
        for i in range(1, n + 1):
            g = G.avoidedPool[i]
            g._scripts.OnEnter(g)
            tips.add(str(lua.eval("GameTooltip._text")))
        assert "Enemy guards: Astranaar" in tips, tips
        _as(lua, ns, "Alliance")  # (their own guards: nothing)
        assert G.LayAvoided(x, y, 1, 0, 1.0, 300) == 0 and not f._shown
        assert G.avoidedStripN == 0
        _as(lua, ns, "Horde")
        st.showAvoided = False
        assert G.LayAvoided(x, y, 1, 0, 1.0, 300) == 0
        st.showAvoided = True
        # (only what's in view: a small view far from any guards, none)
        assert G.LayAvoided(x + 3000, y + 3000, 1, 0, 1.0, 100) == 0
    finally:
        st.showAvoided = True
        ns.CharDB().faction = saved
        lua.execute("UnitFactionGroup = AGPS_UFG AGPS_POS = AGPS_POS_WAS")


def test_only_the_zones_near_the_player_or_the_route_show(game):  # noqa: F811
    """Kooki3z on 6195a75c: every enemy zone in the map's view was drawn. Viewing Astranaar from 1,000 yd away with no
    route: none; a route through it: those within 200 yd of it; standing there: those within 300 yd."""
    lua, ns = game
    N, G, st = ns.Nav, ns.GPS, ns.settings.gps
    lua.execute("AGPS_UFG = UnitFactionGroup AGPS_POS_WAS = AGPS_POS")
    saved = ns.CharDB().faction
    st.showAvoided = True
    x, y = ASTRANAAR
    try:
        _as(lua, ns, "Horde")
        N.route = None
        _at(lua, x + 1000, y)  # (the map browsed over Astranaar, the player far off)
        assert G.LayAvoided(x, y, 1, 0, 1.0, 600) == 0
        assert len(N.EnemyZonesIn(1, x - 600, y - 600, x + 600, y + 600)) > 0  # (there all the same)
        _at(lua, x + 1000, y, 0)  # (on the other continent: none near)
        assert G.LayAvoided(x, y, 1, 0, 1.0, 600) == 0
        # (a route walking by the town's edge, east-west 100 yd past its furthest circle: the zones within 200 yd of it)
        allin = N.EnemyZonesIn(1, x - 600, y - 600, x + 600, y + 600)
        wy = max(z[2] + z[3] for z in allin.values()) + 100
        route = lua.eval("function(x, y) return { parts = { { cont = 1, pts = { x - 900, y, x + 900, y } } } } end")(x, wy)
        N.route = route
        n = G.LayAvoided(x, y, 1, 0, 1.0, 600)
        assert n > 0
        near = N.EnemyZonesNearRoute(route, 1)
        shown = [G.avoidedPool[i].agpsI for i in range(1, n + 1)]
        assert all(near[i] for i in shown)
        lst = lua.eval("AGPS_NS.Hostile[1][AGPS_NS.Nav.Faction()]")
        for i in shown:  # (each within 200 yd of the walk's line)
            assert abs(lst[i + 1] - wy) - lst[i + 2] <= 200 + 1e-6
        far = [z[4] for z in allin.values() if abs(z[2] - wy) - z[3] > 200]
        assert far and not any(i in shown for i in far)  # (the town's far side not drawn)
        # (standing in the town, no route: those within 300 yd of the player)
        N.route = None
        _at(lua, x, y)
        n = G.LayAvoided(x, y, 1, 0, 1.0, 600)
        assert n > 0
        for i in range(1, n + 1):
            j = G.avoidedPool[i].agpsI
            assert ((lst[j] - x) ** 2 + (lst[j + 1] - y) ** 2) ** 0.5 - lst[j + 2] <= 300 + 1e-6
    finally:
        N.route = None
        st.showAvoided = True
        ns.CharDB().faction = saved
        lua.execute("UnitFactionGroup = AGPS_UFG AGPS_POS = AGPS_POS_WAS")


def test_the_zones_have_no_outline(game):  # noqa: F811
    lua, ns = game
    G = ns.GPS
    assert G.AvoidedEdge is None and G.avoidedEdges is None


def test_the_minimap_square_names_the_zone_under_the_pointer(game):  # noqa: F811
    lua, ns = game
    N, G, st = ns.Nav, ns.GPS, ns.settings.gps
    lua.execute("AGPS_UFG = UnitFactionGroup AGPS_POS_WAS = AGPS_POS")
    saved = ns.CharDB().faction
    N.route = None
    st.showAvoided = True
    mode = G.MinimapMode
    try:
        _as(lua, ns, "Alliance")
        x, y = SPLINTERTREE
        _at(lua, x, y)
        assert G.LayAvoided(x, y, 1, 0, 1.0, 300) > 0
        G.MinimapMode = lua.eval("function() return true end")
        lua.execute("GetCursorPosition = function() return 300, 300 end")  # (the frames' centers: the mock's)
        for i in range(1, G.avoidedUsed + 1):
            G.avoidedPool[i].IsMouseOver = lua.eval("function() return false end")
        f = G.avoidedPool[1]
        f.IsMouseOver = lua.eval("function() return true end")
        assert str(G.MinimapTipAt()) == str(G.AvoidedTip(f))
        assert str(G.MinimapTipAt()).startswith("Enemy guards: ")
        f.IsMouseOver = lua.eval("function() return false end")
        assert G.MinimapTipAt() is None
    finally:
        G.MinimapMode = mode
        ns.CharDB().faction = saved
        lua.execute("UnitFactionGroup = AGPS_UFG; GetCursorPosition = function() return 0, 0 end AGPS_POS = AGPS_POS_WAS")


def test_a_town_is_named_by_its_place_else_by_its_guards(game):  # noqa: F811
    # (item 99: "Through enemy territory: Greenpaw Village" named a lone NPC's walk after the nearest village. A town is
    # its place within HOSTILE_TOWN_NAME_YD, else its guards: the five Ashenvale Sentinels south-east of Greenpaw)
    lua, ns = game
    N = ns.Nav

    def nearest(cont, side, x, y):
        lst = ns.Hostile[cont][side]
        best = min(range(1, len(lst) + 1, 3), key=lambda i: (lst[i] - x) ** 2 + (lst[i + 1] - y) ** 2)
        return best

    assert N.HostileTownName(1, "A", nearest(1, "A", *SPLINTERTREE)) == "Splintertree Post"
    assert N.HostileTownName(1, "H", nearest(1, "H", 2400, -1720)) == "Ashenvale Sentinel"
    assert N.HostileTownName(1, "H", nearest(1, "H", *ASTRANAAR)) == "Astranaar"


def test_overlapping_zones_are_one_area_at_one_alpha(game):  # noqa: F811
    # (item 79, Kooki3z at Astranaar: overlapping circles each drawn at 25% stacked, the area solid red and the map under
    # it hidden. The union is drawn once: rows whose spans never overlap, every point of either circle in exactly one)
    lua, ns = game
    G = ns.GPS
    circles = lua.eval("{ { 0, 0, 40 }, { 30, 10, 35 }, { 120, 0, 20 } }")
    rows = G.AvoidedRows(circles, 2, 1000)
    spans = [(rows[i][1], rows[i][2], rows[i][3]) for i in range(1, len(rows) + 1)]
    by_y = {}
    for y, a, b in spans:
        by_y.setdefault(y, []).append((a, b))
    for y, ss in by_y.items():
        ss.sort()
        assert all(p[1] < q[0] for p, q in zip(ss, ss[1:])), (y, ss)  # (no span over another: one alpha)
    cs = [(0, 0, 40), (30, 10, 35), (120, 0, 20)]
    for px in range(-40, 141, 7):
        for py in range(-40, 46, 7):
            if any((px - x) ** 2 + (py - y) ** 2 < (r - 2) ** 2 for x, y, r in cs):
                row = min(by_y, key=lambda y: abs(y - py))
                hits = sum(1 for a, b in by_y[row] if a <= px <= b)
                assert hits == 1, (px, py, hits)
