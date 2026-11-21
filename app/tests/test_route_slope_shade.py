"""The route shaded by its slope (Kooki3z 2026-11-20: "since we have height indication now, can we use shades of lighter
or darker path colors to indicate elevation or de-elevation of a route?"), with the whole addon (gameharness).

Each stretch walked uphill is drawn lighter than the route's color, downhill darker, flat ground (and anything under
a small dead zone) as before; the heights are the route's own (`zs`, `fz`) where it has them, else the map's ground
(Ground.lua's grid, stubbed here); no heights, rides, or Options > Map's "Shade the route by slope" off: as before.
The shades are worked out once per stretch and kept with the route's points: a redraw of the same route reads no
height (the map redraws many times a second while moving: a lag spike otherwise)."""

import pytest

from test_map_redraw import game  # noqa: F401

BLUE = (0.05, 0.28, 0.85)  # (ROUTE_COLOR, index 3 of the route's colors)
SPOT = (2254.0, 293.0)  # (the harness's player, Brill: no cave)
OPEN = (2000.0, 0.0)  # (Tirisfal's fields: no building, no cave)


@pytest.fixture
def ground(game):  # noqa: F811
    """ground(lua_fn_source or None): the map's ground heights stubbed (Ground.Sample, water nil), the shades' cache
    emptied; put back after."""
    lua, ns = game
    GD, G = ns.Ground, ns.GPS
    real = GD.Sample
    st = ns.settings.gps
    saved = st.routeSlopeShade

    def set_(src):
        GD.Sample = lua.eval(f"function(cont, x, y, water) if water then return nil end {src} end")
        lua.execute("AGPS_NS.GPS.slopeCache = setmetatable({}, { __mode = 'k' })")

    try:
        yield set_
    finally:
        GD.Sample = real
        st.routeSlopeShade = saved
        lua.execute("AGPS_NS.GPS.slopeCache = setmetatable({}, { __mode = 'k' })")


def _part(lua, pts, zs=None, kind=0, cont=0):
    flat = ", ".join(f"{v}" for p in pts for v in p)
    kinds = ", ".join(str(kind) for _ in range(len(pts) - 1))
    z = f", zs = {{ {', '.join('false' if v is None else str(v) for v in zs)} }}" if zs else ""
    return lua.eval(f"{{ cont = {cont}, pts = {{ {flat} }}, kinds = {{ {kinds} }}{z} }}")


def _line(n=8, step=10.0, dx=1.0, at=SPOT):
    x0, y0 = at
    return [(x0 + dx * step * k, y0) for k in range(n)]


def _rgb(lua, c):
    if lua.eval("type")(c) == "number":
        c = lua.eval("AGPS_NS.GPS.ROUTE_BASE_COLORS")[c]
    return tuple(round(c[k], 4) for k in (1, 2, 3))


def _route(lua, part):
    return lua.eval("function(p) return { parts = { p } } end")(part)


def test_the_option_is_on_by_default(game):  # noqa: F811
    lua, ns = game
    assert ns.DEFAULTS.gps.routeSlopeShade is True


def test_uphill_lighter_downhill_darker_flat_unchanged(game, ground):  # noqa: F811
    lua, ns = game
    G = ns.GPS
    assert not G.CaveAt(0, *SPOT)
    ground(f"return (x - {SPOT[0]}) * 0.2")  # (a 20% slope up to the east)
    up = _part(lua, _line())
    down = _part(lua, _line(dx=-1))
    for i in range(1, 8):
        c = _rgb(lua, G.SlopeColor(_route(lua, up), up, i, 0, 3))
        assert all(a >= b for a, b in zip(c, BLUE)) and sum(c) > sum(BLUE) + 0.2, (i, c)  # (toward white)
        d = _rgb(lua, G.SlopeColor(_route(lua, down), down, i, 0, 3))
        assert all(a <= b for a, b in zip(d, BLUE)) and sum(d) < sum(BLUE) - 0.1, (i, d)  # (toward black)
    # (capped: the route's color stays its own, blue the strongest of the three)
    steep = _part(lua, _line())
    ground(f"return (x - {SPOT[0]}) * 3")
    c = _rgb(lua, G.SlopeColor(_route(lua, steep), steep, 3, 0, 3))
    assert c[2] == max(c) and c[0] < 0.6
    # flat, and a slope inside the dead zone: the color itself, untouched
    ground("return 50")
    flat = _part(lua, _line())
    assert G.SlopeColor(_route(lua, flat), flat, 3, 0, 3) == 3
    ground(f"return (x - {SPOT[0]}) * 0.03")
    gentle = _part(lua, _line())
    assert G.SlopeColor(_route(lua, gentle), gentle, 3, 0, 3) == 3


def test_a_steeper_slope_is_shaded_more(game, ground):  # noqa: F811
    lua, ns = game
    G = ns.GPS
    shades = []
    for k in (0.1, 0.2, 0.3):
        ground(f"return (x - {SPOT[0]}) * {k}")
        p = _part(lua, _line())
        shades.append(sum(_rgb(lua, G.SlopeColor(_route(lua, p), p, 4, 0, 3))))
    assert shades[0] < shades[1] < shades[2]


def test_any_color_is_shaded_a_looks_and_the_rainbows(game, ground):  # noqa: F811
    lua, ns = game
    G = ns.GPS
    ground(f"return ({SPOT[0]} - x) * 0.2")  # (downhill to the east)
    p = _part(lua, _line())
    gold = lua.eval("{ 1, 0.82, 0 }")
    c = _rgb(lua, G.SlopeColor(_route(lua, p), p, 2, 1, gold))  # (an off-road, dotted stretch too)
    assert c[0] < 1 and c[1] < 0.82 and c[2] == 0
    same = lua.eval("rawequal")
    assert same(G.SlopeColor(_route(lua, p), p, 2, 1, gold), G.SlopeColor(_route(lua, p), p, 3, 1, gold))  # (kept)


def test_rides_and_drops_keep_their_color(game, ground):  # noqa: F811
    lua, ns = game
    G = ns.GPS
    ground(f"return (x - {SPOT[0]}) * 0.3")
    for kind in (2, 4, 5, 6):  # (a boat, zeppelin or flight; a drop; a lift down or up)
        p = _part(lua, _line(), kind=kind)
        assert G.SlopeColor(_route(lua, p), p, 2, kind, 4) == 4


def test_the_routes_own_heights_go_first(game, ground):  # noqa: F811
    # (a floor, a bridge, stairs: the path's `zs`, not the ground under it)
    lua, ns = game
    G = ns.GPS
    ground("return 100")  # (flat ground under it)
    stairs = _part(lua, _line(), zs=[100 + 3 * k for k in range(8)])  # (30% up)
    before = G.slopeSamples
    c = _rgb(lua, G.SlopeColor(_route(lua, stairs), stairs, 4, 0, 3))
    assert sum(c) > sum(BLUE) + 0.2
    assert G.slopeSamples == before  # (the ground not read at all)
    # (a bridge, level, over a valley: flat)
    ground(f"return 100 - math.abs(x - {SPOT[0] + 35})")
    bridge = _part(lua, _line(), zs=[100] * 8)
    assert G.SlopeColor(_route(lua, bridge), bridge, 4, 0, 3) == 3


def _with_fz(lua, part, fz):
    part.fz = lua.eval("{ " + ", ".join(str(v) for v in fz) + " }")
    return part


def test_a_buildings_floors_inside_it_but_not_carried_out_over_the_land(game, ground):  # noqa: F811
    # (Router's Build carries the last floor on over every point without one: a route out of Brill's inn was 35.5 yd
    # high all the way. Outside a building the ground goes first; inside one, its floors: stairs up to the inn's rooms)
    lua, ns = game
    G = ns.GPS
    ground(f"return (x - {OPEN[0]}) * 0.2")
    out = _with_fz(lua, _part(lua, _line(at=OPEN)), [35.5] * 8)
    assert not any(G.SlopeIndoors(0, OPEN[0] + 10 * k, OPEN[1]) for k in range(8))
    assert sum(_rgb(lua, G.SlopeColor(_route(lua, out), out, 4, 0, 3))) > sum(BLUE) + 0.2  # (the hill, shaded)
    b = lua.eval("""function()
      for _, b in ipairs(AGPS_NS.Indoors and AGPS_NS.Indoors[0] or {}) do if b.r >= 12 then return b end end
    end""")()
    assert b, "no building in Data/Indoors.lua to stand in"
    ground("return 20")  # (flat under it)
    pts = [(b.x - b.r * 0.6 + b.r * 1.2 * k / 7, b.y) for k in range(8)]
    step = b.r * 1.2 / 7
    stairs = _with_fz(lua, _part(lua, pts), [20 + 0.3 * step * k for k in range(8)])
    assert G.SlopeIndoors(0, b.x, b.y)
    assert sum(_rgb(lua, G.SlopeColor(_route(lua, stairs), stairs, 4, 0, 3))) > sum(BLUE) + 0.2


def test_no_heights_no_shade(game, ground):  # noqa: F811
    lua, ns = game
    G = ns.GPS
    ground("return nil")
    p = _part(lua, _line())
    assert all(G.SlopeColor(_route(lua, p), p, i, 0, 3) == 3 for i in range(1, 8))
    # (a level the grid hasn't, a city's down below: none either, the ground not even asked)
    ground("error('asked')")
    lower = _part(lua, _line(), cont=99999)
    assert G.SlopeColor(_route(lua, lower), lower, 3, 0, 3) == 3


def test_option_off_draws_as_before(game, ground):  # noqa: F811
    lua, ns = game
    G = ns.GPS
    ground(f"return (x - {SPOT[0]}) * 0.3")
    ns.settings.gps.routeSlopeShade = False
    p = _part(lua, _line())
    before = G.slopeSamples
    assert all(G.SlopeColor(_route(lua, p), p, i, 0, 3) == 3 for i in range(1, 8))
    assert G.slopeSamples == before


def test_each_stretch_is_worked_out_once(game, ground):  # noqa: F811
    # (a repeated lag spike gets a test: the shades are kept with the route's points, read again for free)
    lua, ns = game
    G = ns.GPS
    ground(f"return (x - {SPOT[0]}) * 0.2")
    p = _part(lua, _line(40))
    r = _route(lua, p)
    for i in range(1, 40):
        G.SlopeColor(r, p, i, 0, 3)
    read = G.slopeSamples
    assert read > 0
    for _ in range(5):
        for i in range(1, 40):
            G.SlopeColor(r, p, i, 0, 3)
    assert G.slopeSamples == read
    # the first part as the player follows it (Nav trims it to them, new points each step): the whole one's shades
    trimmed = lua.eval("""function(full, k)
      local pts, kinds = { full.pts[2 * k - 1] + 3, full.pts[2 * k] }, {}
      for j = k + 1, #full.pts / 2 do pts[#pts + 1], pts[#pts + 2] = full.pts[2 * j - 1], full.pts[2 * j] end
      for j = k, #full.kinds do kinds[#kinds + 1] = full.kinds[j] end
      return { cont = full.cont, pts = pts, kinds = kinds }
    end""")
    same = lua.eval("rawequal")
    for k in (2, 7, 20):
        t = trimmed(p, k)
        fr = lua.eval("function(full, t, k) return { parts = { t }, fullFirst = full, followIdx = k } end")(p, t, k)
        for i in range(1, 40 - k):
            assert same(G.SlopeColor(fr, t, i, 0, 3), G.SlopeColor(r, p, i + k - 1, 0, 3))
    assert G.SlopeColor(r, p, 1, 0, 3) != 3
    assert G.slopeSamples == read


@pytest.fixture
def east_trip(game, ground):  # noqa: F811
    lua, ns = game
    N, st = ns.Nav, ns.settings.gps
    saved = st.zoom
    st.zoom = 600
    N.Clear()
    lua.execute(f"AGPS_POS[1], AGPS_POS[2], AGPS_POS[3] = {SPOT[0]}, {SPOT[1]}, 0")
    ns.GPS.Follow()
    ground(f"return (x - {SPOT[0]}) * 0.2 + (y - {SPOT[1]}) * 0.2")

    def redraw(n=3):
        for _ in range(n):
            lua.execute("AGPS_T = AGPS_T + 0.5")
            ns.GPS.Update()

    N.SetStops(lua.eval("{ { x = 2050, y = 520, cont = 0 } }"), False, "red")
    redraw(6)
    assert N.route
    try:
        yield redraw
    finally:
        st.zoom = saved
        N.Clear()


def _route_colors(lua, ns):
    segs, n = ns.GPS.DrawnSegs()
    out = set()
    for i in range(1, n + 1):
        if segs[i][8]:  # (the route's: kept while moving)
            out.add(_rgb(lua, segs[i][5]))
    return out


def test_the_map_draws_the_route_shaded_and_redraws_read_nothing(game, east_trip):  # noqa: F811
    lua, ns = game
    G, st = ns.GPS, ns.settings.gps
    cols = _route_colors(lua, ns)
    assert cols - {BLUE}, cols  # (shaded stretches on the map)
    # a redraw of the same route: no height read again
    read = G.slopeSamples
    east_trip(4)
    assert G.slopeSamples == read
    # the minimap square's route too
    G.UpdateMinimapRoute(True)
    mm = G.minimapRoute
    mcols = {str(mm.lines[i]._tex) for i in range(1, mm.used + 1)}
    base = "color:%.2f,%.2f,%.2f" % tuple(G.MINIMAP_ROUTE_COLOR[k] for k in (1, 2, 3))
    if mm.used:
        assert mcols - {base}, mcols
    # off: the route's own color only, at once
    st.routeSlopeShade = False
    G.Redraw()
    east_trip(2)
    assert _route_colors(lua, ns) <= {BLUE}
    if mm.used:
        G.UpdateMinimapRoute(False)  # (the option is part of what the minimap's route goes by)
        assert {str(mm.lines[i]._tex) for i in range(1, mm.used + 1)} == {base}
