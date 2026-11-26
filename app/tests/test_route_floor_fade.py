"""The route faded by its floor (Kooki3z 2026-11-25: "For routes inside a building/cave or going up/down multiple
floors, fade the opacity of the route's sections more and more ... the further they are from the player's floor"),
with the whole addon (gameharness).

Each stretch's alpha goes by its own height (the route's `zs`, else `fz`) against the player's floor followed
(Nav.PlayerFloorZ): full within G.FLOOR_FADE_SAME_YD, then G.FLOOR_FADE_PER_STEP less each G.FLOOR_FADE_STEP_YD, at
least G.FLOOR_FADE_MIN, half (Kooki3z after testing in game, 2026-11-25). Only indoors where the map has an inside view
(G.FloorIndoorsAt: a building's rooms, a cave with its map, Undercity's level), never an open city's streets: Orgrimmar's
route from the south gate to the wind rider tower faded outdoors. Worked out once per stretch and floor followed."""

import pytest

from test_map_redraw import game  # noqa: F401

OPEN = (2000.0, 0.0)  # (Tirisfal's fields: no building, no cave)
UC = 10001  # (Undercity's own level)


@pytest.fixture
def fade(game):  # noqa: F811
    lua, ns = game
    N = ns.Nav
    lua.execute("AGPS_NS.GPS.floorFadeCache = setmetatable({}, { __mode = 'k' })")
    N.ResetTrack()
    yield lua, ns
    N.ResetTrack()
    lua.execute("AGPS_NS.GPS.floorFadeCache = setmetatable({}, { __mode = 'k' })")


def _part(lua, pts, cont, zs=None, fz=None, kinds=None):
    flat = ", ".join(f"{v}" for p in pts for v in p)
    ks = ", ".join(str(k) for k in (kinds or [0] * (len(pts) - 1)))
    z = f", zs = {{ {', '.join(str(v) for v in zs)} }}" if zs else ""
    f = f", fz = {{ {', '.join(str(v) for v in fz)} }}" if fz else ""
    return lua.eval(f"{{ cont = {cont}, pts = {{ {flat} }}, kinds = {{ {ks} }}{z}{f}, stop = 1 }}")


def _route(lua, part):
    return lua.eval("function(p) return { parts = { p }, pts = p.pts, kinds = p.kinds } end")(part)


def _undercity_spot(ns):
    b = ns.Maps[1458].bounds
    return b[3] - 52.4 / 100 * (b[3] - b[1]), b[4] - 61.3 / 100 * (b[4] - b[2])


def _follow(lua, ns, level, x, y, z):
    lua.execute("AGPS_T = (AGPS_T or 5000) + 1")
    ns.Nav.SetTrackForTests(level, x, y, z)


def test_the_steps_down_to_half(game):  # noqa: F811
    lua, ns = game
    G = ns.GPS
    assert G.FloorFadeAlpha(0) == 1 and G.FloorFadeAlpha(3) == 1
    assert abs(G.FloorFadeAlpha(5) - 0.75) < 1e-9
    assert abs(G.FloorFadeAlpha(10) - 0.5) < 1e-9
    assert G.FloorFadeAlpha(60) == G.FLOOR_FADE_MIN == 0.5
    a = [G.FloorFadeAlpha(d) for d in range(0, 40)]
    assert all(x >= y for x, y in zip(a, a[1:]))  # (never brighter further off)


def test_a_route_down_two_floors_in_undercity_fades_by_floor(fade):
    lua, ns = fade
    G, N = ns.GPS, ns.Nav
    x, y = _undercity_spot(ns)
    top = 60.0
    # (the hall, the stairs down to the floor under it, its floor, the stairs down again, the lowest floor)
    zs = [top, top, top, top - 5, top - 10, top - 10, top - 15, top - 20, top - 20, top - 20]
    pts = [(x + 6 * k, y) for k in range(len(zs))]
    p = _part(lua, pts, UC, zs=zs)
    r = _route(lua, p)
    assert G.FloorFade(r, p, 1) == 1  # (no floor followed yet: as before)
    _follow(lua, ns, UC, x, y, top)
    assert N.PlayerFloorZ(UC) == top
    a = [G.FloorFade(r, p, i) for i in range(1, len(zs))]
    assert a[0] == a[1] == 1 and a[2] == 1  # (the player's floor, and the stairs leaving it)
    assert a[4] < 1 and a[4] == a[5]  # (one floor down: fainter)
    assert a[-1] == a[-2] == 0.5  # (two floors down: half)
    assert all(u >= v for u, v in zip(a, a[1:]))
    # the floor followed goes down to the lowest: faded again, the other way round
    _follow(lua, ns, UC, x + 48, y, top - 20)
    b = [G.FloorFade(r, p, i) for i in range(1, len(zs))]
    assert b[-1] == b[-2] == 1
    assert b[0] == b[1] == 0.5
    assert all(u <= v for u, v in zip(b, b[1:]))


def test_the_place_is_worked_out_once_the_alpha_once_per_floor(fade):
    lua, ns = fade
    G = ns.GPS
    x, y = _undercity_spot(ns)
    zs = [40 - 2 * k for k in range(20)]
    p = _part(lua, [(x + 4 * k, y) for k in range(20)], UC, zs=zs)
    r = _route(lua, p)
    _follow(lua, ns, UC, x, y, 40)
    before = G.floorStackLooks
    first = [G.FloorFade(r, p, i) for i in range(1, 20)]
    looks = G.floorStackLooks - before
    assert looks == 19
    for _ in range(4):
        assert [G.FloorFade(r, p, i) for i in range(1, 20)] == first
    _follow(lua, ns, UC, x, y, 20)  # (another floor: alphas again, the places kept)
    second = [G.FloorFade(r, p, i) for i in range(1, 20)]
    assert second != first
    assert G.floorStackLooks - before == looks
    # the first part as the player follows it (Nav trims it, new points each step): the whole part's
    trimmed = lua.eval("""function(full, k)
      local pts, kinds, zs = { full.pts[2 * k - 1] + 1, full.pts[2 * k] }, {}, { full.zs[k] }
      for j = k + 1, #full.pts / 2 do pts[#pts + 1], pts[#pts + 2], zs[#zs + 1] = full.pts[2 * j - 1], full.pts[2 * j], full.zs[j] end
      for j = k, #full.kinds do kinds[#kinds + 1] = full.kinds[j] end
      return { cont = full.cont, pts = pts, kinds = kinds, zs = zs }
    end""")
    t = trimmed(p, 6)
    fr = lua.eval("function(full, t, k) return { parts = { t }, fullFirst = full, followIdx = k } end")(p, t, 6)
    assert [G.FloorFade(fr, t, i) for i in range(1, 15)] == second[5:]
    assert G.floorStackLooks - before == looks


def test_an_open_world_hill_stays_at_full_alpha(fade):
    lua, ns = fade
    G = ns.GPS
    assert not G.CaveAt(0, *OPEN) and not G.FloorIndoorsAt(0, *OPEN)
    # (up a hill 40 yd, the floor followed at its foot: a raised road's, say; Router's Build carrying a floor on too)
    fz = [10 + 5 * k for k in range(9)]
    p = _part(lua, [(OPEN[0] + 10 * k, OPEN[1]) for k in range(9)], 0, fz=fz)
    r = _route(lua, p)
    _follow(lua, ns, 0, OPEN[0], OPEN[1], 10)
    assert ns.Nav.PlayerFloorZ(0) == 10
    assert all(G.FloorFade(r, p, i) == 1 for i in range(1, 9))


def test_no_heights_no_fade(fade):
    lua, ns = fade
    G = ns.GPS
    x, y = _undercity_spot(ns)
    p = _part(lua, [(x + 5 * k, y) for k in range(6)], UC)
    _follow(lua, ns, UC, x, y, 80)
    assert all(G.FloorFade(_route(lua, p), p, i) == 1 for i in range(1, 6))


def _building(lua):
    # (a building of Data/Indoors.lua whose middle stretch across is all in its indoor rooms: the inside view's)
    return lua.eval("""function()
      local G = AGPS_NS.GPS
      for _, b in ipairs(AGPS_NS.Indoors and AGPS_NS.Indoors[0] or {}) do
        if b.r >= 10 then
          local ok = true
          for k = 0, 7 do
            if not G.FloorIndoorsAt(0, b.x - b.r * 0.4 + b.r * 0.8 * k / 7, b.y) then ok = false break end
          end
          if ok then return b end
        end
      end
    end""")()


def test_the_map_and_minimap_draw_the_fade_keeping_each_style(fade):
    # (in a building with its inside: the player's floor full, a floor two down half; a dotted walk stays dotted, a
    # road solid, the color the route's own; the minimap's lines alike. GPS map and world-map mode are one redraw)
    lua, ns = fade
    G, N, st = ns.GPS, ns.Nav, ns.settings.gps
    b = _building(lua)
    assert b, "no building in Data/Indoors.lua to stand in"
    x0 = b.x - b.r * 0.4
    step = b.r * 0.8 / 7
    pts = [(x0 + step * k, b.y) for k in range(8)]
    fz = [30, 30, 30, 30, 10, 10, 10, 10]
    kinds = [0, 0, 1, 0, 0, 1, 8]  # (roads, walks dotted, a jump's coil on the lower floor)
    p = _part(lua, pts, 0, fz=fz, kinds=kinds)
    route = _route(lua, p)
    saved = (st.zoom, st.routeSlopeShade, N.Route, st.cityGrid, st.worldGrid)
    st.zoom, st.routeSlopeShade = 200, False
    st.cityGrid, st.worldGrid = False, False  # (walks dotted: G.WalksSolid)
    N.Clear()
    lua.execute(f"AGPS_POS[1], AGPS_POS[2], AGPS_POS[3] = {pts[1][0]}, {pts[1][1]}, 0")
    lua.globals().AGPS_FAKE_ROUTE = route
    lua.execute("AGPS_NS.Nav.Route = function() return AGPS_FAKE_ROUTE end")
    try:
        G.Follow()

        def drawn():
            lua.execute("AGPS_T = AGPS_T + 0.5")
            _follow(lua, ns, 0, pts[1][0], pts[1][1], cur[0])
            G.Redraw()
            G.Update()
            segs, n = G.DrawnSegs()
            out = []
            for i in range(1, n + 1):
                sg = segs[i]
                if sg[8]:
                    out.append((round(sg[7], 3), bool(sg[9]), tuple(round(sg[5][k], 3) for k in (1, 2, 3))
                                if lua.eval("type")(sg[5]) == "table" else sg[5]))
            return out

        cur = [30]
        up = drawn()
        assert up, "no route drawn"
        alphas = {a for a, _, _ in up}
        assert 1 in alphas and 0.5 in alphas, alphas
        assert any(a == 1 and dot for a, dot, _ in up) and any(a == 1 and not dot for a, dot, _ in up)
        assert any(a == 0.5 and dot for a, dot, _ in up) and any(a == 0.5 and not dot for a, dot, _ in up)
        assert len({c for _, _, c in up}) <= 2  # (the route's colors only: solid and dotted's, not changed)
        coil = [a for a, d, _ in up if not d]
        assert len(up) > 12 and coil.count(0.5) > 6  # (the jump's coil: its many short lines, faded alike)
        # the floor followed down to the lower floor: re-faded the other way
        cur[0] = 10
        down = drawn()
        assert {a for a, _, _ in down} == alphas
        assert [d for _, d, _ in down] == [d for _, d, _ in up]  # (each style kept)
        assert up[0][0] == 1 and down[0][0] == 0.5 and up[-1][0] == 0.5 and down[-1][0] == 1
        assert all(u[0] == 1 or d[0] == 1 for u, d in zip(up, down))  # (one floor or the other; the stairs both)
        # the minimap's lines: faded too, and drawn again as the floor changes
        lua.execute("AGPS_NS.Nav.route = AGPS_FAKE_ROUTE; AGPS_NS.Nav.dest = { x = 0, y = 0, cont = 0 }")
        rec = lua.eval("""function()
          local G = AGPS_NS.GPS
          local mm = G.minimapRoute
          G.UpdateMinimapRoute(true)
          for i = 1, mm.used do
            mm.lines[i].SetColorTexture = function(l, r, g, b, a) l._alpha = a end
          end
          G.UpdateMinimapRoute(true)
          local out = {}
          for i = 1, mm.used do out[i] = mm.lines[i]._alpha end
          return out, mm.used
        end""")
        mm, used = rec()
        if used:
            got = {round(mm[i], 3) for i in range(1, used + 1)}
            assert any(v >= 0.6 for v in got) and any(v <= 0.48 for v in got), got  # (0.95 or 0.6 by kind, times half)
            cur[0] = 30
            _follow(lua, ns, 0, pts[1][0], pts[1][1], 30)
            assert G.UpdateMinimapRoute(False) == used  # (drawn again: the floor changed)
            mm2, _ = rec()
            assert {round(mm2[i], 3) for i in range(1, used + 1)} == got
    finally:
        st.zoom, st.routeSlopeShade = saved[0], saved[1]
        st.cityGrid, st.worldGrid = saved[3], saved[4]
        N.Route = saved[2]
        lua.execute("AGPS_FAKE_ROUTE = nil")
        N.Clear()


def test_orgrimmars_south_gate_to_the_wind_rider_tower_stays_at_full_alpha(fade):
    # (Kooki3z, in game 2026-11-25: through the Valley of Strength up to the tower the route faded outdoors, hard to
    # see. Orgrimmar's rooms are nearly all flagged indoors, its streets too: an open city's never count)
    lua, ns = fade
    G, N = ns.GPS, ns.Nav
    b = ns.Maps[1454].bounds

    def at(px, py):
        return b[3] - px / 100 * (b[3] - b[1]), b[4] - py / 100 * (b[4] - b[2])

    gate, tower = at(49.5, 92.0), at(45.1, 63.9)
    N.Clear()
    lua.execute(f"AGPS_POS[1], AGPS_POS[2], AGPS_POS[3] = {gate[0]}, {gate[1]}, 1; AGPS_MAP = 1454")
    try:
        G.Follow()
        N.SetStops(lua.eval(f"{{ {{ x = {tower[0]}, y = {tower[1]}, cont = 1 }} }}"), False, "red")
        for _ in range(40):
            lua.execute("AGPS_T = AGPS_T + 0.5")
            G.Update()
            if N.route and not N.route.pending:
                break
        r = N.route
        assert r and not r.pending
        p = r.parts[1]
        assert p.cont == 1 and p.fz, "no heights on the route through Orgrimmar"
        zs = [p.fz[i] for i in range(1, len(p.pts) // 2 + 1) if p.fz[i]]
        assert max(zs) - min(zs) > 20  # (up to the tower: well over a floor's height)
        _follow(lua, ns, 1, gate[0], gate[1], min(zs))
        assert all(G.FloorFade(r, p, i) == 1 for i in range(1, len(p.pts) // 2))
        # (the Orgrimmar model's room the gate stands in: an open city's, so not indoors)
        assert G.InteriorUnder(gate[0], gate[1], 1) is None or not G.FloorIndoorsAt(1, gate[0], gate[1])
    finally:
        N.Clear()
        lua.execute("AGPS_MAP = nil; AGPS_POS[1], AGPS_POS[2], AGPS_POS[3] = 2254.0, 293.0, 0")
