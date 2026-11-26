"""Route work in short slices, the same answers (item 108, SPF parity: "performance and speed").

Measured by the slow client's instruction clock (test_frame_budget's _VM_CLOCK) on long trips, the background's slices
ran 25-85 ms past their 1-5 ms between pauses (a tile's links decoded 500 surfaces at a time, a route's swims sampled
row by row, a straight line checked a yard at a time, the collector's steps, a region's road links parsed whole). Each
of those loops now looks at the slice's clock and pauses in a background job; out of one (the frame, the tests' sync
searches) it runs through as before. Each pause is checked here the same way: run in a job whose slice is always over,
it pauses, and its answer is what it is run straight through.

Also: a route's check for the Ruins of Lordaeron (WorldGrid.ThroughNotMeshed, on every grid leg handed back) samples
only the pieces near them (a 9.5k yd route was 1,200 samples, 12-15 ms); a mount or a speed change works nothing out
again (a grid route's costs are yards; times come from the speeds when shown)."""

import math
import random

import pytest

from test_map_redraw import game  # noqa: F401

pytest.importorskip("lupa")

# (runs `fn(...)` in a job whose slice is always over: every clock check pauses. Its answer and the pauses taken)
_IN_JOB = """function(fn, ...)
  local R = AGPS_NS.Router
  local was = R.SliceOver
  R.SliceOver = function() return coroutine.running() ~= nil end
  local args, n = { ... }, select("#", ...)
  local co = coroutine.create(function() return fn(unpack(args, 1, n)) end)
  local pauses, ok, a, b = -1, true, nil, nil
  repeat
    pauses = pauses + 1
    ok, a, b = coroutine.resume(co)
  until not ok or coroutine.status(co) == "dead"
  R.SliceOver = was
  if not ok then error(a) end
  return a, pauses, b
end"""


def _flat(t):
    return None if not t else [t[i] for i in range(1, len(t) + 1)]


def test_the_terrain_s_water_along_a_long_piece_pauses_and_answers_the_same(game):  # noqa: F811
    lua, ns = game
    P = ns.Passability
    in_job = lua.eval(_IN_JOB)
    # (north to south down the Barrens' coast, past Ratchet: hundreds of the terrain grid's rows)
    pieces = [(1, -200.0, -3700.0, -2500.0, -3900.0), (1, -900.0, -3600.0, -1000.0, -4300.0),
              (0, -3000.0, -800.0, -4200.0, -1200.0)]
    paused = 0
    for cont, x1, y1, x2, y2 in pieces:
        P.ClearCache()  # (no row decoded, nothing remembered)
        got, n, _ = in_job(P.WaterSpans, cont, x1, y1, x2, y2)
        P.ClearCache()
        want = P.WaterSpans(cont, x1, y1, x2, y2)
        assert _flat(got) == _flat(want), (cont, x1, y1, x2, y2)
        paused += n
    assert paused > 50


def test_a_straight_line_on_the_world_grid_pauses_and_answers_the_same(game):  # noqa: F811
    lua, ns = game
    WG = ns.WorldGrid
    st = ns.settings.gps
    st.worldGrid = True
    WG.Set(True)
    try:
        in_job = lua.eval(_IN_JOB)
        c = WG.Cont(1)
        # (lines over the Barrens' grass by the Crossroads, 100-400 yd, and a few that stop at a wall or a cliff)
        rng = random.Random(108)
        seen, paused = set(), 0
        for _ in range(12):
            x0, y0 = -441.8 + rng.uniform(-300, 300), -2596.1 + rng.uniform(-300, 300)
            a, L = rng.uniform(0, 2 * math.pi), rng.uniform(100, 400)
            x1, y1 = x0 + L * math.cos(a), y0 + L * math.sin(a)
            want = WG.Clear(c, x0, y0, None, x1, y1, None)  # (first: its tiles decoded, the pauses the line's own)
            got, n, _ = in_job(WG.Clear, c, x0, y0, None, x1, y1, None)
            assert bool(got) == bool(want), (x0, y0, x1, y1)
            seen.add(bool(want))
            paused += n
        assert paused > 0 and seen == {True, False}
    finally:
        st.worldGrid = False
        WG.Set(False)


def test_a_tile_s_decoding_pauses_between_its_counted_pauses_and_decodes_the_same(game):  # noqa: F811
    lua, ns = game
    WG = ns.WorldGrid
    st = ns.settings.gps
    st.worldGrid = True
    WG.Set(True)
    try:
        in_job = lua.eval(_IN_JOB)
        c = WG.Cont(1)
        key, _ = WG.CellKey(c, math.floor(-441.8 / c.cell), math.floor(-2596.1 / c.cell))
        WG.Tile(c, key)  # (its region loaded)
        want = WG.Tile(c, key)
        c.tiles[key] = None
        c.bytes = c.bytes - want.bytes
        # (the counted pauses alone, Router.Breathe's every 500 surfaces: fewer)
        R = ns.Router
        br = R.Breathe
        counted = lua.eval("function() local n = 0 return function() n = n + 1 end, function() return n end end")
        add, get = counted()
        R.Breathe = add
        try:
            got, n, _ = in_job(WG.Tile, c, key)
        finally:
            R.Breathe = br
        assert got.s == want.s and got.cells == want.cells and _flat(got.base) == _flat(want.base)
        assert n > 4 * get(), (n, get())  # (by the clock, past the counted pauses' few)
    finally:
        st.worldGrid = False
        WG.Set(False)


def test_the_collector_steps_in_pieces_pausing_when_the_slice_is_over(game):  # noqa: F811
    lua, ns = game
    WG = ns.WorldGrid
    in_job = lua.eval(_IN_JOB)
    lua.execute("AGPS_JUNK = {} for i = 1, 200000 do AGPS_JUNK[i] = { i } end AGPS_JUNK = nil")
    _, n, _ = in_job(WG.GcSteps, 256)
    assert n == 256 // WG.GC_PIECE - 1  # (a pause between each two pieces: one step of 256 was 7-9 ms on a dev PC)


def test_the_ruins_check_samples_only_near_the_ruins_and_answers_the_same(game):  # noqa: F811
    lua, ns = game
    WG = ns.WorldGrid
    brute = lua.eval("""function(cont, r)
      local WG, p = AGPS_NS.WorldGrid, r.pts
      for i = 1, #p - 3, 2 do
        local L = math.sqrt((p[i + 2] - p[i]) ^ 2 + (p[i + 3] - p[i + 1]) ^ 2)
        local n = math.max(1, math.ceil(L / 8))
        for q = 0, n do
          if WG.NotMeshed(cont, p[i] + (p[i + 2] - p[i]) * q / n, p[i + 1] + (p[i + 3] - p[i + 1]) * q / n) then
            return true
          end
        end
      end
      return false
    end""")
    calls = lua.eval("""function(cont, r)
      local WG = AGPS_NS.WorldGrid
      local nm, n = WG.NotMeshed, 0
      WG.NotMeshed = function(...) n = n + 1 return nm(...) end
      local v = WG.ThroughNotMeshed(cont, r)
      WG.NotMeshed = nm
      return v, n
    end""")
    boxes = WG.NotMeshedBoxes(0)
    assert boxes and len(boxes) == 1  # (the Ruins of Lordaeron's)
    rng = random.Random(108)
    yes = 0
    for k in range(200):
        # (routes round Brill and Lordaeron's ruins (1320-1906, -22-502), through them and past them)
        pts = []
        x, y = rng.uniform(1100, 2300), rng.uniform(-300, 800)
        for _ in range(rng.randint(2, 6)):
            pts += [x, y]
            x, y = x + rng.uniform(-400, 400), y + rng.uniform(-400, 400)
        r = lua.eval("function(t) return { pts = t } end")(lua.table(*pts))
        want = bool(brute(0, r))
        got, _ = calls(0, r)
        assert bool(got) == want, pts
        yes += want
    assert 20 < yes < 180
    # (a long route far from them: not a sample)
    far = lua.eval("function() return { pts = { -9000, 500, -10500, 1000, -10500, -1200, -8000, -2000 } } end")()
    got, n = calls(0, far)
    assert not got and n == 0
    got, n = calls(1, lua.eval("function() return { pts = { -441, -2596, -7139, -3752 } } end")())
    assert not got and n == 0  # (Kalimdor: no such place)


def test_mounting_works_nothing_out_again(game):  # noqa: F811
    # (a grid route's costs are yards, its time the speeds' when shown (Nav.TripSecs): a mount, a speed buff or a slower
    # run reads the same remembered walk, no search again. The one speed in the costs is the swim weight, run over swim
    # read on foot (Kooki3z 2026-11-22), the same while both scale alike; test_swim_routes)
    lua, ns = game
    WG, R = ns.WorldGrid, ns.Router
    st = ns.settings.gps
    st.worldGrid = True
    WG.Set(True)
    old = lua.eval("{ GetUnitSpeed, IsMounted }")
    try:
        lua.execute("GetUnitSpeed = function() return 0, 7, 7, 4.72 end; IsMounted = function() return false end")
        ns.Nav.Speeds()
        a, b = (-441.8, -2596.1), (-838.0, -2037.0)  # (the Crossroads to the Wailing Caverns)
        r1 = WG.Leg(1, a[0], a[1], b[0], b[1], lua.table())
        assert r1 and r1 != "pending"
        key1, searches = WG.CostKey(lua.table()), WG.stats.searches
        for speeds, mounted in (("14, 7, 14, 4.72", "true"), ("9.8, 9.8, 14, 6.6", "false"), ("0, 6.3, 6.3, 4.25", "false")):
            lua.execute(f"GetUnitSpeed = function() return {speeds} end; IsMounted = function() return {mounted} end")
            ns.Nav.Speeds()
            assert WG.CostKey(lua.table()) == key1, speeds
            r2 = WG.Leg(1, a[0], a[1], b[0], b[1], lua.table())
            assert WG.stats.searches == searches, speeds
            assert _flat(r2.pts) == _flat(r1.pts)
    finally:
        lua.eval("function(t) GetUnitSpeed, IsMounted = t[1], t[2] end")(old)
        st.worldGrid = False
        WG.Set(False)
