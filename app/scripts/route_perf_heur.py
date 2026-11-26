"""Route-speed study: what a better heuristic would buy. One leg's WorldGrid.Search (starts and goals as WG.Walk's,
the default costs) under: the straight line alone; the landmark fields (as shipped); the heuristic's weights; a
cell-exact field flooded back from the goal over the loaded regions (the ceiling an abstraction can reach); and the
exact search kept to a corridor round the weighed search's way (a bounded refine).

    python app/scripts/route_perf_heur.py [leg ...]"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from azerothgps.gameharness import start  # noqa: E402

LEGS = {
    "taurajo-ungoro": (1, (-2292.7, -2142.6), (-7446.7, -1316.7)),
    "xroads-gadgetzan": (1, (-441.8, -2596.1), (-7139.0, -3752.0)),
    "tanaris-sands-ungoro": (1, (-6915.0, -2848.0), (-6830.0, -1975.0)),
    "taurajo-freewind": (1, (-2353.0, -1922.0), (-5454.0, -2446.0)),
    "ratchet-splintertree": (1, (-951.0, -3680.0), (2286.0, -2565.0)),
    "darkshire-booty": (0, (-10565.0, -1171.0), (-14383.0, 487.0)),
}

LUA = r"""
local ns = AGPS_NS
local WG = ns.WorldGrid
local floor = math.floor
local SHIFT = 131072
H = {}
function H.Setup(cont, sx, sy, tx, ty)
  local c = WG.Cont(cont)
  local starts, goals = WG.Ends(c, sx, sy, nil), {}
  for _, e in ipairs(WG.Ends(c, tx, ty, nil)) do goals[e.id] = e.cost end
  WG.UnderGoals(c, tx, ty, nil, goals)
  WG.NearGoals(c, tx, ty, nil, goals)
  H.c, H.starts, H.goals, H.tx, H.ty, H.sx, H.sy = c, starts, goals, tx, ty, sx, sy
end
-- one search: heur (nil: WG.HEUR), alt (false: the straight line alone), inside; nodes, cost, ms, steps
function H.Run(heur, alt, inside, cap)
  local c = H.c
  local x = WG.Costs(c, H.sx, H.sy, H.tx, H.ty, {})
  x.heur = heur
  x.nodeCap = cap
  WG.altOff = (alt == false) or nil
  local t0 = PROF_CLOCK()
  local steps = WG.Search(c, H.starts, H.goals, H.tx, H.ty, inside, x)
  local ms = (PROF_CLOCK() - t0) * 1000
  WG.altOff = nil
  H.steps = steps or H.steps
  return WG.lastNodes, steps and WG.lastCost or 0, ms, steps and #steps or 0, x.limitHit and 1 or 0
end
-- the landmark bound at the start (in cost), as the search scales it
function H.Bound()
  local c = H.c
  local x = WG.Costs(c, H.sx, H.sy, H.tx, H.ty, {})
  local set, L = WG.AltAllowed(x, c)
  local AB = set and WG.AltSearch(c, H.goals, set, L)
  local st = H.starts[1]
  local line = math.sqrt((H.tx - H.sx) ^ 2 + (H.ty - H.sy) ^ 2) * x.road
  return AB and AB(floor(st.id / SHIFT), st.ci) * math.min(1, x.road / c.road) or 0, line
end
-- a corridor round the last way found: the cells within `yd` of its steps
function H.Corridor(yd)
  local c = H.c
  local cell = c.cell
  local r = math.ceil(yd / cell)
  local set = {}
  for _, st in ipairs(H.steps) do
    local t = WG.Tile(c, st.key)
    local px, py = WG.Pt(c, t, st.id - st.key * SHIFT, st.ci)
    local gx, gy = floor(px / cell), floor(py / cell)
    for i = -r, r do
      for j = -r, r do set[(gx + i) * 65536 + gy + j] = true end
    end
  end
  return function(px, py) return set[floor(px / cell) * 65536 + floor(py / cell)] == true end
end
-- the goal's own field: every loaded surface's least cost to the goal (WG.AltFlood, the bake's flood), a cell's the
-- least of its surfaces'; WG.AltSearch then answers from it (the landmark fields left out)
function H.GoalField()
  local c = H.c
  local t0 = PROF_CLOCK()
  -- (every region of the continent in, and kept: the flood only crosses tiles AltPrepare saw. Undirected, falls up to
  -- WG.ALT_FALL both ways, the data's own road cost: the landmark fields' kind of bound, not the true cost to go)
  WG.TILE_CACHE_MB = 4000
  for rk in pairs(c.d.regions or {}) do
    local rx, ry = rk:match("^(%d+):(%d+)$")
    WG.LoadRegion(c, tonumber(rx), tonumber(ry))
  end
  local prep = WG.AltPrepare(c)
  local srcs = {}
  for id in pairs(H.goals) do srcs[#srcs + 1] = id end
  local dist = WG.AltFlood(c, prep, srcs, {})
  local cells, n = {}, 0
  for id, v in pairs(dist) do
    local key = floor(id / SHIFT)
    local ci = prep.cellOf[id]
    if ci then -- (none: a link's end in a region not loaded)
      local ck = key * 4096 + ci
      if not cells[ck] or v < cells[ck] then cells[ck] = v end
      n = n + 1
    end
  end
  H.cells = cells
  return n, (PROF_CLOCK() - t0) * 1000
end
local altSearch = WG.AltSearch
function H.UseGoalField(k)
  if k then
    WG.AltSearch = function() return function(key, ci) return (H.cells[key * 4096 + ci] or 0) * k end end
  else
    WG.AltSearch = altSearch
  end
end
"""


def main(argv):
    names = argv or list(LEGS)
    for name in names:
        cont, a, b = LEGS[name]
        lua, ns = start()
        lua.globals().PROF_CLOCK = time.perf_counter
        st = ns.settings.gps
        st.worldGrid, st.cityGrid = True, True
        ns.WorldGrid.Set(True)
        ns.CityGrid.Set(True)
        lua.execute("AGPS_LEVEL = 60; UnitFactionGroup = function() return 'Horde' end; "
                    "IsPlayerSpell = function() return false end")
        ns.CharDB().faction = "Horde"
        ns.FallSpells.Refresh()
        ns.Router.SYNC_WALKS = True
        WG = ns.WorldGrid
        WG.MAX_NODES, WG.NODES_BASE = 3000000, 3000000
        lua.execute(LUA)
        H = lua.globals().H
        H.Setup(cont, a[0], a[1], b[0], b[1])
        print(f"\n=== {name} ===", flush=True)

        def show(label, res):
            nodes, cost, ms, steps, cut = res
            print(f"  {label:44s} nodes {int(nodes):8d}  cost {cost:9.1f}  {ms:8.0f} ms  steps {int(steps):5d}"
                  f"{'  CUT' if cut else ''}", flush=True)
            return cost

        H.Run(3, True, None, None)  # (the tiles decoded, the far drops known: not timed)
        w3 = show("weight 3 + landmarks (shipped, long legs)", H.Run(3, True, None, None))
        corridor = {yd: H.Corridor(yd) for yd in (100, 200, 400)}
        show("weight 2 + landmarks", H.Run(2, True, None, None))
        show("weight 3, straight line only", H.Run(3, False, None, None))
        show("weight 1.1 + landmarks (the refine), cap 1.5M", H.Run(None, True, None, 1500000))
        best = show("weight 1.0, straight line only (the best way)", H.Run(1.0, False, None, 1500000))
        print(f"      (weight 3's way costs {100 * (w3 / best - 1):.1f}% over the best)", flush=True)
        for yd, inside in corridor.items():
            for alt in (True, False):
                c = show(f"weight 1.1 {'+ landmarks' if alt else 'line only'} inside {yd} yd of w3's way",
                         H.Run(None, alt, inside, None))
                print(f"      ({100 * (c / best - 1):.1f}% over the best)", flush=True)
        bound, line = H.Bound()
        if best:
            print(f"  the landmark bound at the start: {bound:.0f} = {100 * bound / best:.0f}% of the best cost; the straight "
                  f"line's: {line:.0f} = {100 * line / best:.0f}%", flush=True)
        n, ms = H.GoalField()
        print(f"  goal field: {int(n)} surfaces flooded in {ms:.0f} ms (the loaded regions)", flush=True)
        for k in (1.0, 1.2):
            H.UseGoalField(k)
            c = show(f"weight 1.1 + the goal's own field x{k}", H.Run(None, True, None, None))
            print(f"      ({100 * (c / best - 1):.1f}% over the best)", flush=True)
        H.UseGoalField(None)


if __name__ == "__main__":
    main(sys.argv[1:])
