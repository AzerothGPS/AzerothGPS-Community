"""The world grid's search made cheaper a node (study/route-perf, 2026-11-25) without changing a route: its heap
gives entries out in the order the plain swapping heap did (equal keys too: which of two ways as cheap is taken), and
the loop's own reading of a surface's record (its links, heights and flags in one go, a neighbor in the node's tile
without a call) finds ways whose cost is the sum WG.Link / WG.Z / WG.Flags give step by step."""

import math
import random

import pytest

from test_map_redraw import game  # noqa: F401

# (the heap as it was: every step a swap)
REFERENCE = """
local floor = math.floor
local function Push(hk, hv, k, v)
  local i = #hk + 1
  hk[i], hv[i] = k, v
  while i > 1 do
    local p = floor(i / 2)
    if hk[p] <= hk[i] then break end
    hk[p], hk[i], hv[p], hv[i] = hk[i], hk[p], hv[i], hv[p]
    i = p
  end
end
local function Pop(hk, hv)
  local n = #hk
  local k0, v0 = hk[1], hv[1]
  hk[1], hv[1] = hk[n], hv[n]
  hk[n], hv[n] = nil, nil
  n = n - 1
  local i = 1
  while true do
    local l, r, s = 2 * i, 2 * i + 1, i
    if l <= n and hk[l] < hk[s] then s = l end
    if r <= n and hk[r] < hk[s] then s = r end
    if s == i then break end
    hk[s], hk[i], hv[s], hv[i] = hk[i], hk[s], hv[i], hv[s]
    i = s
  end
  return k0, v0
end
return function(ops, push, pop)
  push, pop = push or Push, pop or Pop
  local hk, hv, out = {}, {}, {}
  for i = 1, #ops do
    local k = ops[i]
    if k >= 0 then
      push(hk, hv, k, i)
    elseif hk[1] then
      local _, v = pop(hk, hv)
      out[#out + 1] = v
    end
  end
  while hk[1] do
    local _, v = pop(hk, hv)
    out[#out + 1] = v
  end
  return table.concat(out, ",")
end
"""


def test_the_heap_gives_entries_out_in_the_swapping_heap_s_order(game):  # noqa: F811
    lua, ns = game
    WG = ns.WorldGrid
    run = lua.execute(REFERENCE)
    rng = random.Random(1125)
    for size, keys in ((1, 1), (2, 1), (3, 2), (40, 5), (400, 12), (5000, 60), (5000, 100000)):
        # (few different keys: ties all the way; a pop every third step, -1)
        ops = [(-1 if rng.random() < 0.33 else rng.randrange(keys)) for _ in range(size)]
        t = lua.table_from(ops)
        assert run(t, WG.HeapPush, WG.HeapPop) == run(t), (size, keys)


LEGS = [(1, (-600.0, -2700.0), (-900.0, -2500.0)), (1, (-2353.0, -1922.0), (-2600.0, -2200.0)),
        (1, (300.0, -4700.0), (0.0, -4500.0)), (0, (-9480.0, 64.0), (-9300.0, -200.0)),
        (0, (-5349.0, -2960.0), (-5100.0, -3200.0)), (1, (-7139.0, -3752.0), (-7400.0, -3500.0)),
        (1, (-4420.0, 200.0), (-4700.0, 500.0)), (0, (-803.0, -532.0), (-1100.0, -800.0))]


@pytest.fixture
def grid(game):  # noqa: F811
    lua, ns = game
    st, WG = ns.settings.gps, ns.WorldGrid
    was = st.worldGrid
    st.worldGrid = True
    WG.Set(True)
    yield lua, ns
    st.worldGrid = was
    WG.Set(bool(was))


def test_a_way_s_cost_is_the_sum_of_its_steps_by_the_accessors(grid):
    lua, ns = grid
    WG, R = ns.WorldGrid, ns.Router
    SHIFT = 131072
    checked, why = 0, []
    for cont, a, b in LEGS:
        c = WG.Cont(cont)
        starts, ends = WG.Ends(c, a[0], a[1], None), WG.Ends(c, b[0], b[1], None)
        if not (starts[1] and ends[1]):
            why.append("no surface")
            continue
        s0 = lua.table_from([lua.table_from({"id": starts[1].id, "key": starts[1].key, "ci": starts[1].ci, "cost": 0,
                                             "x": starts[1].x, "y": starts[1].y})])
        goals = lua.table()
        goals[ends[1].id] = 0
        steps = WG.Search(c, s0, goals, b[0], b[1], None, None)  # (the grid's own costs alone)
        if not steps:
            why.append("no way")
            continue
        cost = WG.lastCost
        path = [steps[i] for i in range(1, len(steps) + 1)]
        total = 0.0
        for p, q in zip(path, path[1:]):
            if q.link:  # (a road link: its own yards at the road's cost)
                total += c.links[q.link].yd * c.road
                continue
            t, nt = WG.Tile(c, p.key), WG.Tile(c, q.key)
            s, s2 = int(p.id) - int(p.key) * SHIFT, int(q.id) - int(q.key) * SHIFT
            # (the direction whose link leads there, by the accessors)
            took = None
            for d in range(1, 9):
                kk = WG.Link(t, s, d)
                if kk > 0:
                    nkey, nci = WG.Step(c, p.key, p.ci, d)
                    if nkey == q.key and nci == q.ci and WG.First(nt, nci) + kk - 1 == s2:
                        took = d
            assert took, (cont, a, p.id, q.id)  # (not a far drop: none without the costs)
            dz = WG.Z(c, nt, s2) - WG.Z(c, t, s)
            step = c.cell * math.sqrt(2) if took > 4 else c.cell
            w = math.sqrt(step * step + dz * dz) + abs(dz) * WG.CLIMB_COST
            fa, fb = int(WG.Flags(t, s)), int(WG.Flags(nt, s2))
            if fa & 1 or fb & 1:
                w *= c.swim
                if not fa & 1 and fb & 1:
                    w += WG.SWIM_ENTER_YD
            elif fa & 2 and fb & 2:
                w *= c.road
            if q.drop:
                w += R.DropExtra(-dz, False)
            total += w
        # (a drop down a slope after another may cost a chain's: those legs aren't summed)
        if sum(1 for st in path if st.drop) > 1:
            why.append("drops")
            continue
        assert abs(total - cost) < 1e-6 * max(1.0, cost), (cont, a, b, total, cost)
        checked += 1
    assert checked >= 6, (checked, why)
