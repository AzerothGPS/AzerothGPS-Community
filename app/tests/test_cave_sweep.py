"""Every cave and mine in Data/Caves.lua with a path inside (item 84c, Kooki3z: "this must work for ALL caves"): a stop on
its inside path (the path's point farthest from its ways in, on its floor under the ground), from a spot 200 yd out past
its way in nearest the stop, settles within the common trips' node budget (about 10 s of the game's searching) to a
route that enters by a way in (WorldGrid.CaveLeg: the grid to the mouth, the cave's own path inside), or to "No way
found yet" for the caves listed in KNOWN_NO_WAY (the grid has no way to their mouths from there). Never pending for
good. Caves with no path inside on their floor (NO_INSIDE_PATH), or no way in, aren't routed here: listed by
`test_the_caves_left_out_are_the_listed_ones`.

`AGPS_CAVE_SWEEP_REPORT=<file>`: each cave's result appended to it (the sweep's report)."""

from __future__ import annotations

import math
import os

import pytest

pytest.importorskip("lupa.lua51")

from test_cave_inside_routes import settle  # noqa: E402

NODE_BUDGET = 150000  # (test_common_trips_settle's: about 10 s of the game's searching)
MOUTH_YD = 60  # (the route passes this near one of the cave's ways in)

# Lua: each cave of continent `cont` with its ways in, and a stop on its inside path (on its floor under the ground)
PICK = r"""
function(cont)
  local WG = AGPS_NS.WorldGrid
  local out, inside = {}, {}
  for _, ov in ipairs(AGPS_NS.RoadOverlays[cont] or {}) do
    if ov.cave then
      local n, nz = ov.n, ov.nz
      for i = 1, #n / 2 do
        local x, y = n[2 * i - 1], n[2 * i]
        local cave = WG.CaveAt(cont, x, y)
        if cave then
          local z = nz and nz[i] ~= 0 and nz[i] or nil
          if not z then -- (the grid's highest floor CAVE_UNDER_YD or more under the ground there)
            local g, c = WG.GroundZ(cont, x, y), WG.Cont(cont)
            if g and c then
              for _, s in ipairs(WG.SurfacesAt(c, x, y)) do
                if s.z <= g - WG.CAVE_UNDER_YD and (not z or s.z > z) then z = s.z end
              end
            end
          end
          if z and WG.InCave(cont, x, y, z) then
            inside[cave] = inside[cave] or {}
            local t = inside[cave]
            t[#t + 1] = { x, y, z }
          end
        end
      end
    end
  end
  for _, cv in ipairs(AGPS_NS.Caves[cont] or {}) do
    local key, ways = cv[2], cv[5]
    local pts = inside[key]
    local e = { key = key, name = cv[1], ways = ways }
    if pts and ways and #ways >= 2 then
      local far, pick = -1
      for _, p in ipairs(pts) do
        local d = math.huge
        for k = 1, #ways, 2 do d = math.min(d, math.sqrt((p[1] - ways[k]) ^ 2 + (p[2] - ways[k + 1]) ^ 2)) end
        if d > far then far, pick = d, p end
      end
      local mx, my, md
      for k = 1, #ways, 2 do
        local d = math.sqrt((pick[1] - ways[k]) ^ 2 + (pick[2] - ways[k + 1]) ^ 2)
        if not md or d < md then mx, my, md = ways[k], ways[k + 1], d end
      end
      local dx, dy = mx - pick[1], my - pick[2]
      local L = math.sqrt(dx * dx + dy * dy)
      if L > 0 then
        e.stop = pick
        e.start = { mx + dx / L * 200, my + dy / L * 200 }
      end
    end
    out[#out + 1] = e
  end
  return out
end
"""

# (the grid has no way from the sweep's start to these caves' mouths, or into them: "No way found yet", the gap logged.
# Each a recorded walk in, as section 11's Wailing Caverns portal; the sweep of 2026-11-25)
KNOWN_NO_WAY = {
    # (cont 0)
    "cave71472", "cave73025", "cave127585", "cave183551", "cave228054", "cave83293", "cave363311", "cave398380",
    "cave398368", "cave463649", "cave566969", "cave66784274", "cave70157761",
    # (cont 1)
    "cave245558", "cave276930", "cave205790", "cave281496", "cave309456", "cave337455", "cave360783", "cave387503",
    "cave497832", "cave606060", "cave606084", "cave24646308", "cave24646413", "cave70195699", "cave70612836",
}
# (a route settles, but not by one of the listed ways in: the cave's data's ways in aren't where its path comes out)
KNOWN_ELSEWHERE = {"cave10009", "cave83292", "cave464691"}  # (Dreadmaul Rock 122 yd, Mo'grosh Stronghold 146, Dawning Wood Catacombs 69)


@pytest.fixture(scope="module")
def game():
    from azerothgps.gameharness import start
    lua, ns = start()
    ns.Nav.FUN = False
    st = ns.settings.gps
    st.worldGrid, st.cityGrid = True, True
    ns.WorldGrid.Set(True)
    ns.CityGrid.Set(True)
    lua.execute("AGPS_LEVEL = 60; UnitFactionGroup = function() return 'Horde' end")
    ns.CharDB().faction = "Horde"
    yield lua, ns
    st.worldGrid, st.cityGrid = False, False


def _cases():
    """(cont, key, name, start, stop, ways) per cave with an inside path, and the left-out caves' (cont, key, why).
    Read once from the data with a harness of its own (collection time)."""
    from azerothgps.gameharness import start
    lua, ns = start()
    ns.WorldGrid.Set(True)
    pick = lua.eval(PICK)
    cases, left = [], []
    for cont in (0, 1):
        t = pick(cont)
        for i in range(1, len(t) + 1):
            e = t[i]
            if not e.stop:
                left.append((cont, e.key, "no way in" if e.ways is None or len(e.ways) < 2 else "no path inside"))
                continue
            ways = [e.ways[k] for k in range(1, len(e.ways) + 1)]
            cases.append((cont, e.key, e.name or "", (e.start[1], e.start[2]), (e.stop[1], e.stop[2], e.stop[3]),
                          list(zip(ways[0::2], ways[1::2]))))
    return cases, left


try:
    CASES, LEFT_OUT = _cases()
except ImportError:  # (no lupa: the module's skipped above)
    CASES, LEFT_OUT = [], []


def _report(line):
    out = os.environ.get("AGPS_CAVE_SWEEP_REPORT")
    if out:
        with open(out, "a", encoding="utf-8") as f:
            f.write(line + "\n")


def _points(r):
    for i in range(1, len(r.parts) + 1):
        p = r.parts[i]
        if p.pts:
            for k in range(1, len(p.pts) + 1, 2):
                yield p.pts[k], p.pts[k + 1]


@pytest.mark.parametrize("cont,key,name,start,stop,ways", CASES, ids=[f"{c[0]}-{c[1]}" for c in CASES])
def test_a_stop_inside_every_cave_settles_in_by_its_mouth(game, cont, key, name, start, stop, ways):
    lua, ns = game
    ticks, r, nodes = settle(lua, ns, start, stop[:2], stop[2], cont=cont)
    if ticks is None:
        _report(f"{cont} {key} {name!r}: never settled ({nodes} nodes)")
    assert ticks is not None, f"{key} {name}: never settled ({nodes} nodes)"
    assert nodes <= NODE_BUDGET, f"{key} {name}: {nodes} nodes"
    if r is None:
        _report(f"{cont} {key} {name!r}: No way found yet ({nodes} nodes)")
        if key in KNOWN_NO_WAY:
            pytest.xfail(f"{key} {name}: no way to its mouth on the grid (KNOWN_NO_WAY)")
        pytest.fail(f"{key} {name}: No way found yet")
    assert key not in KNOWN_NO_WAY, f"{key} {name}: routed now; out of KNOWN_NO_WAY"
    near = min(math.hypot(x - wx, y - wy) for x, y in _points(r) for wx, wy in ways)
    _report(f"{cont} {key} {name!r}: route {r.totalYards:.0f} yd, {near:.0f} yd from a way in, {nodes} nodes")
    if near > MOUTH_YD and key in KNOWN_ELSEWHERE:
        pytest.xfail(f"{key} {name}: in {near:.0f} yd from its listed ways in (KNOWN_ELSEWHERE)")
    assert near <= MOUTH_YD, f"{key} {name}: {near:.0f} yd from its ways in"


def test_the_caves_left_out_are_the_listed_ones():
    """The caves the sweep can't route into (no path on a floor under the ground, or no way in): counted, so a data
    change that loses a cave's inside path shows."""
    assert len(CASES) >= 200, len(CASES)
    assert len(LEFT_OUT) <= 140, len(LEFT_OUT)
    for cont, key, why in LEFT_OUT:
        _report(f"{cont} {key}: left out ({why})")
