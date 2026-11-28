"""Every cave and mine in Data/Caves.lua with a path inside (item 84c, Kooki3z: "this must work for ALL caves"): a stop on
its inside path (the path's point farthest from its ways in, on its floor under the ground as a click there means it),
from a spot 200 yd out past its way in nearest the stop (or round the mouth from there: PICK), settles within the
common trips' node budget (about 10 s of the game's searching) to a route that enters by a way in (WorldGrid.CaveLeg:
the grid to the mouth, the cave's own path inside), or to "No way found yet" for the caves listed in KNOWN_NO_WAY (the
grid has no way to their mouths from there). Never pending for good. Caves with no path inside on their floor
(NO_INSIDE_PATH), or no way in, aren't routed here: listed by `test_the_caves_left_out_are_the_listed_ones`.

`AGPS_CAVE_SWEEP_REPORT=<file>`: each cave's result appended to it (the sweep's report)."""

from __future__ import annotations

import math
import os

import pytest

pytest.importorskip("lupa.lua51")

from test_cave_inside_routes import settle  # noqa: E402
from test_frame_budget import VM_HOOK, _VM_CLOCK  # noqa: E402

NODE_BUDGET = 150000  # (test_common_trips_settle's: about 10 s of the game's searching)
# (2026-11-27) The frames' slices go by the Lua VM's instructions (test_frame_budget's _VM_CLOCK), not the CPU's clock:
# by the CPU's, a known no way's settling was as many frames as the machine was slow. Woodpaw Den's two searches
# (284,844 nodes since 1.4.1's Feralas walks) took 721 of the 1,200 frames on the reference dev PC and never settled on
# the CI runners (2-4x slower a CPU millisecond), every node the same. Route work's own rate on the reference dev PC:
# 114,000-126,000 instructions a millisecond (Woodpaw Den, Plaguewood and Kalimdor's at 1832, 277).
VM_PER_MS = 120000
MOUTH_YD = 60  # (the route passes this near one of the cave's ways in)

# Lua: each cave of continent `cont` with its ways in, and a stop on its inside path (on its floor under the ground: the
# floor a click on the cave's map there means, GPSFrame's G.CaveFloorZ), and a start START_YD out past its way in
# nearest the stop. That spot is the start when a player stands on it and walks off from it (Walked: a surface there,
# not the water's, PIECE surfaces or more walked from it); else, turned round the mouth a step at a time (the nearest
# to straight out first), the first spot on the land round it (BIG surfaces or more walked from it), else the first a
# player stands on. The sweep of 2026-11-25 had 10 starts in the rock round a mouth, in the sea or on a speck (a tree's
# top) among its 28 no ways.
PICK = r"""
function(cont)
  local WG = AGPS_NS.WorldGrid
  local START_YD, PIECE, BIG = 200, 300, 10000
  local TURNS = { 20, -20, 40, -40, 60, -60, 80, -80, 100, -100, 120, -120, 140, -140, 160, -160, 180 }
  -- (the surfaces walked from (x, y), up to `cap`: nil for no surface there or the water's)
  local function Walked(cont, x, y, cap)
    local c = WG.Cont(cont)
    local ends = c and WG.Ends(c, x, y)
    local e = ends and ends[1]
    if not e or e.f % 2 == 1 then return nil end -- (WorldGrid's F_SWIM)
    local xc = WG.Costs(c, x, y, x, y, {})
    xc.side, xc.exempt, xc.light, xc.red, xc.block, xc.nodeCap = nil, nil, nil, nil, nil, cap
    local base = WG.NODES_BASE
    WG.NODES_BASE = math.max(base, cap + 1)
    WG.Search(c, ends, {}, x, y, nil, xc)
    WG.NODES_BASE = base
    return xc.limitHit and cap or WG.lastNodes
  end
  local out, inside = {}, {}
  for _, ov in ipairs(AGPS_NS.RoadOverlays[cont] or {}) do
    if ov.cave then
      local n, nz = ov.n, ov.nz
      for i = 1, #n / 2 do
        local x, y = n[2 * i - 1], n[2 * i]
        local cave = WG.CaveAt(cont, x, y)
        if cave then
          local z = nz and nz[i] ~= 0 and nz[i] or nil
          if not z then -- (the floor a click there on the cave's map means: GPSFrame's G.CaveFloorZ)
            local g = WG.GroundZ(cont, x, y)
            z = g and AGPS_NS.GPS.CaveFloorZ(cont, x, y, g)
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
        local a0 = math.atan2(dy, dx)
        local function At(deg)
          local a = a0 + math.rad(deg)
          return mx + math.cos(a) * START_YD, my + math.sin(a) * START_YD
        end
        local x0, y0 = At(0)
        if (Walked(cont, x0, y0, PIECE) or 0) >= PIECE then
          e.start, e.turned = { x0, y0 }, 0
        else
          local stands
          for _, deg in ipairs(TURNS) do
            local x, y = At(deg)
            local n = Walked(cont, x, y, BIG) or 0
            if n >= BIG then
              e.start, e.turned = { x, y }, deg
              break
            end
            if n >= PIECE and not stands then stands = { x, y, deg } end
          end
          if not e.start and stands then e.start, e.turned = { stands[1], stands[2] }, stands[3] end
        end
        e.start = e.start or { mx + dx / L * START_YD, my + dy / L * START_YD }
      end
    end
    out[#out + 1] = e
  end
  return out
end
"""

# (the grid has no way from the sweep's start to these caves' mouths, or into them: "No way found yet", the gap logged.
# Gone through one by one for 1.4.1 (2026-11-26); by why:
KNOWN_NO_WAY = {
    # (Mouths on a ledge the grid's links leave only by a drop down: nine were joined by the bake of 2026-11-26, Loch
    # Modan, Beren's Peril, the Crypt at -6570, -3483, Rethban Caverns, Drywhisker Gorge, Gordunni Outpost, Demon Fall
    # Ridge, Rage Scar Hold, Bolgan's Hole; Plaguewood by its regions' bake for 1.4.2, RECORDED_WALKS_IN)
    # Item 136 (1.4.2): Kooki3z's recorded walks into these four (1.4.1's roads) walk through mouths the grid already
    # joined (their walks route on the grid end to end, before the bake too: test_the_walked_mouths_join_the_grid);
    # what's missing is elsewhere:
    # - the walk's mouth on a ledge no way on the grid reaches from the land round it, nor the mesh: a walk recorded
    #   from the valley up to the mouth is needed (Woodpaw Den, its mouth at 139 over the start's 58; Kalimdor's at
    #   1832, 277, its mouth at 228, the slope under it at 163)
    "cave337455", "cave70612836",
    # - the stop on the cave's upper floor (312-318), reached only by the west way in on a ledge; the walk went in by
    #   the north mouth on the lower floor (300), which the grid doesn't join to the upper (Mo'grosh Stronghold's west)
    "cave83293",
    # - the Router's own way in to the stop is the cave's other way in (-8760, -2940), which the grid can't reach;
    #   the walked mouth (-8754, -2887) is reached and walks on to the stop, but WorldGrid.CaveLeg tries only the one
    #   (the cave at -8759, -2898)
    "cave66784274",
    # - its mouth high in Dun Morogh's peaks (z 639): no way there from the start, nor back, on the grid
    "cave363311",
    # (cave24646308, the start on a rise left only by drops, its walk down and round to the mouth 7.7k yd: past a leg's
    # budget till item 139, 1.4.2, gave a short leg to a stop cut short the whole budget once: routed now)
    # - the cave and its mouth an island of ~700 surfaces on the grid, nothing joining them to the land round it
    "cave360783",
}
# (item 136, 1.4.2: the caves Kooki3z recorded walks into, 2026-11-26, that route in since their regions' bake; the
# other four are in KNOWN_NO_WAY with why)
RECORDED_WALKS_IN = {"cave463649": "Plaguewood"}
# (each recorded walk into a cave, 1.4.1's roads: (cont, time), walked on the grid from its first point outside to its
# last inside)
WALKS_INTO_CAVES = {"cave463649": (0, 1795747278), "cave66784274": (0, 1795747315), "cave83293": (0, 1795747334),
                    "cave337455": (1, 1795747151), "cave70612836": (1, 1795747193)}
# (a route settles, but not by one of the listed ways in: none since 2026-11-26 (Dreadmaul Rock went through the next
# cave's tunnel, WorldGrid.CaveLeg's mouth; Mo'grosh Stronghold's and the Dawning Wood Catacombs' stops were on the
# ground over them, G.CaveFloorZ))
KNOWN_ELSEWHERE: set = set()


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
    lua.execute("AGPS_T = AGPS_T or 0")
    undo = lua.eval(_VM_CLOCK)(VM_PER_MS, VM_HOOK)
    yield lua, ns
    undo()
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
            TURNED[e.key] = e.turned
    return cases, left


TURNED = {}  # (each cave's start: degrees turned round its mouth from straight out, None for no spot found)
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
    ticks, r, nodes = settle(lua, ns, start, stop[:2], stop[2], cont=cont,
                             now=lua.eval("function() return debugprofilestop() end"))
    if ticks is None:
        _report(f"{cont} {key} {name!r}: never settled ({nodes} nodes)")
    assert ticks is not None, f"{key} {name}: never settled ({nodes} nodes)"
    if r is None:
        _report(f"{cont} {key} {name!r}: No way found yet ({nodes} nodes, {ticks} frames, start turned {TURNED.get(key)})")
        if key in KNOWN_NO_WAY:  # (its budget not weighed: a known no way's two searches, round the guards and
            # through, may go a little past it, 150.2k for the Kalimdor cave at 1832, 277)
            pytest.xfail(f"{key} {name}: no way to its mouth on the grid (KNOWN_NO_WAY)")
        assert nodes <= NODE_BUDGET, f"{key} {name}: {nodes} nodes"
        pytest.fail(f"{key} {name}: No way found yet")
    assert nodes <= NODE_BUDGET, f"{key} {name}: {nodes} nodes"
    assert key not in KNOWN_NO_WAY, f"{key} {name}: routed now; out of KNOWN_NO_WAY"
    near = min(math.hypot(x - wx, y - wy) for x, y in _points(r) for wx, wy in ways)
    _report(f"{cont} {key} {name!r}: route {r.totalYards:.0f} yd, {near:.0f} yd from a way in, {nodes} nodes, {ticks} frames"
            f" (start turned {TURNED.get(key)})")
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


@pytest.mark.parametrize("key", sorted(RECORDED_WALKS_IN))
def test_the_caves_walked_into_route_in_by_their_mouths(game, key):
    """Item 136 (1.4.2): a cave Kooki3z recorded a walk into settles in by one of its ways in, within the budget."""
    case = next((c for c in CASES if c[1] == key), None)
    assert case is not None, f"{key}: no stop inside it picked (its inside path or way in lost?)"
    cont, key, name, start, stop, ways = case
    lua, ns = game
    ticks, r, nodes = settle(lua, ns, start, stop[:2], stop[2], cont=cont)
    assert ticks is not None, f"{key} {RECORDED_WALKS_IN[key]}: never settled ({nodes} nodes)"
    assert r is not None, f"{key} {RECORDED_WALKS_IN[key]}: No way found yet ({nodes} nodes)"
    assert nodes <= NODE_BUDGET, f"{key}: {nodes} nodes"
    near = min(math.hypot(x - wx, y - wy) for x, y in _points(r) for wx, wy in ways)
    assert near <= MOUTH_YD, f"{key}: {near:.0f} yd from its ways in"
    assert key not in KNOWN_NO_WAY


@pytest.mark.parametrize("key", sorted(WALKS_INTO_CAVES))
def test_the_walked_mouths_join_the_grid(game, key):
    """Item 136 (1.4.2): each recorded walk into a cave is walked on the grid, from its first point outside the mouth to
    its last inside, at the walk's height."""
    import json
    from azerothgps.paths import REPO
    cont, t = WALKS_INTO_CAVES[key]
    feats = json.loads((REPO / "overrides" / f"roads_{cont}.geojson").read_text(encoding="utf-8"))["features"]
    parts = sorted((f["properties"].get("part") or 0, f) for f in feats if f["properties"].get("time") == t)
    assert parts, (key, t)
    a = parts[0][1]["geometry"]["coordinates"][0]
    last = parts[-1][1]
    b, bz = last["geometry"]["coordinates"][-1], last["properties"]["zs"][-1]
    lua, ns = game
    ns.Router.Reset()
    r = ns.Router.Route(cont, a[0], a[1], b[0], b[1], lua.table_from({"tz": bz}))
    assert r is not None and not r.noWay, (key, r and r.noWay)
    assert r.length < 3 * math.dist(a, b) + 30, (key, r.length)
