"""Route-speed profile (study/route-perf): a trip worked out as the game does (frames of 16.7 ms, the background
pumped by GPS.PumpBudget's slice), with per-job CPU, every WorldGrid.Search logged, and a time-weighted sample of where
the Lua time goes (a count hook reading a high-resolution clock).

    python app/scripts/route_perf.py [trip ...] [--no-hook] [--json out.json] [--patch WorldGrid.lua=path]

Not part of the test suite; the numbers are this PC's (lupa's Lua 5.1, as the tests)."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from azerothgps.gameharness import start  # noqa: E402

SLOW_FALL = 1259416
XR, GADGET = (-441.8, -2596.1), (-7139.0, -3752.0)
TAURAJO, FREEWIND = (-2353.0, -1922.0), (-5454.0, -2446.0)

# name: side, level, cont, start, stop, settings
TRIPS = {
    "barrens-ungoro": dict(side="Alliance", level=25, cont=1, a=(-2292.7, -2142.6), b=(-7446.7, -1316.7),
                           st=dict(roadTolerance=10, safeDropYd=60, useClassSpells=False), red_ok=True),
    "org-astranaar": dict(side="Horde", level=60, cont=1, a=(1545.9, -4412.4), b=(2862.756, -174.149), st={}),
    "xroads-gadgetzan": dict(side="Horde", level=60, cont=1, a=XR, b=GADGET, st={}),
    "xroads-gadgetzan-expert": dict(side="Horde", level=60, cont=1, a=XR, b=GADGET,
                                    st=dict(useClassSpells=True, expertJumper=True), spell=SLOW_FALL),
    "xroads-gadgetzan-roads10": dict(side="Horde", level=60, cont=1, a=XR, b=GADGET, st=dict(roadTolerance=-10)),
    "ratchet-astranaar-alliance": dict(side="Alliance", level=60, cont=1, a=(-951.0, -3680.0), b=(2720.0, -382.0), st={}),
    "org-astranaar-flights": dict(side="Horde", level=60, cont=1, a=(1545.9, -4412.4), b=(2862.756, -174.149), st={},
                                  flights=True),
    "xroads-gadgetzan-flights": dict(side="Horde", level=60, cont=1, a=XR, b=GADGET, st={}, flights=True),
    "xroads-gadgetzan-flights-expert": dict(side="Horde", level=60, cont=1, a=XR, b=GADGET, flights=True,
                                            st=dict(useClassSpells=True, expertJumper=True), spell=SLOW_FALL),
    "org-silithus-flights": dict(side="Horde", level=60, cont=1, a=(1545.9, -4412.4), b=(-6816.7, 783.3), st={},
                                 flights=True),
    "org-silithus-flights-expert": dict(side="Horde", level=60, cont=1, a=(1545.9, -4412.4), b=(-6816.7, 783.3),
                                        flights=True, st=dict(useClassSpells=True, expertJumper=True), spell=SLOW_FALL),
    "barrens-ungoro-flights": dict(side="Alliance", level=25, cont=1, a=(-2292.7, -2142.6), b=(-7446.7, -1316.7),
                                   st=dict(roadTolerance=10, safeDropYd=60, useClassSpells=False), red_ok=True,
                                   flights=True),
    "taurajo-ungoro": dict(side="Horde", level=60, cont=1, a=(-2292.7, -2142.6), b=(-7446.7, -1316.7), st={}),
    "taurajo-ungoro-expert": dict(side="Horde", level=60, cont=1, a=(-2292.7, -2142.6), b=(-7446.7, -1316.7),
                                  st=dict(useClassSpells=True, expertJumper=True), spell=SLOW_FALL),
    "taurajo-ungoro-roads10": dict(side="Horde", level=60, cont=1, a=(-2292.7, -2142.6), b=(-7446.7, -1316.7),
                                   st=dict(roadTolerance=-10)),
    "taurajo-ungoro-flights": dict(side="Horde", level=60, cont=1, a=(-2292.7, -2142.6), b=(-7446.7, -1316.7), st={},
                                   flights=True),
    "dunmorogh-horde": dict(side="Horde", level=60, cont=0, a=(-5349.0, -2960.0), b=(-5586.0, -482.0), st={}),
    "taurajo-freewind": dict(side="Horde", level=60, cont=1, a=TAURAJO, b=FREEWIND, st={}),
    "taurajo-freewind-roads10": dict(side="Horde", level=60, cont=1, a=TAURAJO, b=FREEWIND, st=dict(roadTolerance=-10)),
    "taurajo-freewind-expert": dict(side="Horde", level=60, cont=1, a=TAURAJO, b=FREEWIND,
                                    st=dict(useClassSpells=True, expertJumper=True), spell=SLOW_FALL),
}

LUA = r"""
local clock = PROF_CLOCK
PROF = { byFunc = {}, byLine = {}, byRoot = {}, searches = {}, jobs = {}, hookEvery = 0, samples = 0 }
local P = PROF
debugprofilestop = function() return clock() * 1000 end
PROF.now = debugprofilestop
local ns = AGPS_NS
local WG, R, N = ns.WorldGrid, ns.Router, ns.Nav
local getinfo, sethook = debug.getinfo, debug.sethook

-- the roots: a sample belongs to the innermost of these on its stack
local roots = {}
local function Root(fn, name) if type(fn) == "function" then roots[fn] = name end end
P.Root = Root

local last = clock()
local function hook()
  local now = clock()
  local dt = now - last
  local info = getinfo(2, "Sl")
  if info then
    local fk = info.short_src .. ":" .. info.linedefined
    P.byFunc[fk] = (P.byFunc[fk] or 0) + dt
    local lk = info.short_src .. ":" .. info.currentline
    P.byLine[lk] = (P.byLine[lk] or 0) + dt
    local root = "other"
    for lvl = 2, 40 do
      local f = getinfo(lvl, "f")
      if not f then break end
      local r = roots[f.func]
      if r then root = r break end
    end
    local rk = root .. " < " .. fk
    P.byRoot[rk] = (P.byRoot[rk] or 0) + dt
    P.samples = P.samples + 1
  end
  last = clock()
end
function P.Arm() if P.hookEvery > 0 then sethook(hook, "", P.hookEvery) end last = clock() end
function P.Disarm() sethook() end

-- per-job CPU: coroutine.resume timed, the job's key from Router.Background (else "router walk")
local create, resume, running = coroutine.create, coroutine.resume, coroutine.running
local keyOf, acc, startOf = setmetatable({}, { __mode = "k" }), setmetatable({}, { __mode = "k" }), {}
local nextKey
coroutine.create = function(fn)
  local co = create(function(...)
    if P.hookEvery > 0 then sethook(hook, "", P.hookEvery) end
    return fn(...)
  end)
  keyOf[co] = nextKey or "router walk"
  nextKey = nil
  acc[co] = 0
  return co
end
coroutine.resume = function(co, ...)
  local t0 = clock()
  startOf[co] = t0
  last = t0
  local function done(...)
    local t1 = clock()
    local d = t1 - t0
    acc[co] = (acc[co] or 0) + d
    startOf[co] = nil
    local k = keyOf[co] or "?"
    local kind = k:match("^([%a%-_ ]+)") or k
    if k:find("!rush", 1, true) then kind = kind .. " (rush)" end
    local j = P.jobs[kind]
    if not j then j = { cpu = 0, resumes = 0, jobs = 0, worst = 0 } P.jobs[kind] = j end
    j.cpu, j.resumes = j.cpu + d, j.resumes + 1
    if d > j.worst then j.worst = d end
    if coroutine.status(co) == "dead" then j.jobs = j.jobs + 1 end
    last = t1
    return ...
  end
  return done(resume(co, ...))
end
local function Active()
  local co = running()
  if not co then return clock(), nil end
  return (acc[co] or 0) + (clock() - (startOf[co] or clock())), co
end
local bg = R.Background
R.Background = function(key, ...)
  if not R.SYNC_WALKS then nextKey = tostring(key) end
  local a, b, c = bg(key, ...)
  nextKey = nil
  return a, b, c
end

local search = WG.Search
WG.Search = function(c, starts, goals, tx, ty, inside, x)
  local t0, co = Active()
  local tiles0 = WG.stats.tiles
  local altSet = WG.AltAllowed(x, c)
  local steps = search(c, starts, goals, tx, ty, inside, x)
  local t1 = Active()
  P.searches[#P.searches + 1] = { job = co and keyOf[co] or "main", nodes = WG.lastNodes, ms = (t1 - t0) * 1000,
    heur = x and x.heur or WG.HEUR, cap = x and x.nodeCap or 0, alt = altSet and true or false, found = steps and #steps or 0,
    cut = x and x.limitHit and true or false, guards = x and x.side and true or false, red = x and x.red and true or false,
    road = x and x.road or c.road, maxDrop = x and x.maxDrop or -1, tiles = WG.stats.tiles - tiles0,
    cost = steps and WG.lastCost or 0, t = AGPS_T }
  return steps
end

Root(search, "WG.Search")
Root(WG.Tile, "WG.Tile")
Root(WG.FarDrops, "WG.FarDrops")
Root(WG.Pull, "WG.Pull")
Root(WG.Straighten, "WG.Straighten")
Root(WG.Costs, "WG.Costs")
Root(WG.LoadRegion, "WG.LoadRegion")
Root(WG.BlockCorridor, "WG.BlockCorridor")
Root(WG.BlockDistances, "WG.BlockDistances")
Root(WG.AltSearch, "WG.AltSearch(setup)")
Root(WG.Extra, "WG.Extra")
Root(WG.Line, "WG.Line")
Root(WG.Clear, "WG.Clear")
Root(ns.Passability and ns.Passability.CrossesWall, "P.CrossesWall")
Root(ns.Ground and ns.Ground.Sample, "Ground.Sample")
Root(ns.CityGrid and ns.CityGrid.Search, "CG.Search")
Root(N.Plan, "N.Plan")
Root(R.Route, "R.Route")
Root(WG.GcStep, "WG.GcStep")
P.invalidates = 0
local inv = N.Invalidate
N.Invalidate = function(...) P.invalidates = P.invalidates + 1 return inv(...) end
"""


def run(name, hook_every=0, max_frames=60 * 240, patches=None, quiet_frames=120, verbose=True, pre_lua=None):
    spec = TRIPS[name]
    replace = {k: Path(v).read_text(encoding="utf-8") for k, v in (patches or {}).items()} or None
    lua, ns = start(replace=replace)
    lua.globals().PROF_CLOCK = time.perf_counter
    lua.execute(LUA)
    if pre_lua:
        lua.execute(pre_lua)
    prof = lua.globals().PROF
    prof.hookEvery = hook_every
    R, N, WG, CG, G = ns.Router, ns.Nav, ns.WorldGrid, ns.CityGrid, ns.GPS
    N.FUN = False
    st = ns.settings.gps
    st.worldGrid, st.cityGrid = True, True
    for k, v in spec["st"].items():
        st[k] = v
    WG.Set(True)
    CG.Set(True)
    side = spec["side"]
    lua.execute(f"AGPS_LEVEL = {spec['level']}; UnitFactionGroup = function() return '{side}' end")
    if spec.get("spell"):
        lua.execute(f"IsPlayerSpell = function(id) return id == {spec['spell']} end; GetItemCount = function() return 0 end")
    else:
        lua.execute("IsPlayerSpell = function() return false end")
    cdb = ns.CharDB()
    cdb.faction = side
    if spec.get("flights"):
        from azerothgps import tripsweep as ts
        known = ts._masters(ns, spec["cont"], side[0])
        cdb.taxiNodes = lua.eval("{ [1415] = { nodes = { " + "".join(f"{{ nodeID = {n}, known = true }}," for n in known)
                                 + " } } }")
        ns.Teleports.Changed()
        N.FlightsChanged()
    ns.FallSpells.Refresh()
    cont, a, b = spec["cont"], spec["a"], spec["b"]
    now = prof.now
    out = {"trip": name, "runs": []}
    arm, disarm = prof.Arm, prof.Disarm
    budget_fn = G.PumpBudget

    def one(label, reset):
        # (as in the game: the plans in background jobs (Router.WARM), the continent's road network built before the
        # trip is asked for, as after a login: untimed)
        R.WARM, R.SYNC_WALKS = True, False
        if reset:
            lua.execute(f"AGPS_POS = {{ {a[0]}, {a[1]}, {cont} }}; AGPS_T = 900")
            R.WarmUp(cont, a[0], a[1])
            for _ in range(20000):
                if not R.HasWork():
                    break
                R.Pump(now() + 50, now)
        for t in ("routes", "order", "targets", "failed", "failOrder"):
            WG[t] = lua.table()
        CG.routes, CG.order = lua.table(), lua.table()
        prof.byFunc, prof.byLine, prof.byRoot = lua.table(), lua.table(), lua.table()
        prof.searches, prof.jobs, prof.samples, prof.invalidates = lua.table(), lua.table(), 0, 0
        N.Clear()
        t_base = 1000.0 if reset else 5000.0
        lua.execute(f"AGPS_POS = {{ {a[0]}, {a[1]}, {cont} }}; AGPS_T = {t_base}")
        n0 = WG.stats.nodes + CG.stats.nodes
        tiles0, regions0 = WG.stats.tiles, WG.stats.regions
        cpu_route, cpu_pump, route_calls, recomputes = 0.0, 0.0, 0, 0
        worst_frame, over6, over10 = 0.0, 0, 0
        settled, quiet, first_route = None, 0, None
        t0 = time.perf_counter()
        arm()
        N.SetStops(lua.eval(f"{{ {{ x = {b[0]}, y = {b[1]}, cont = {cont}, name = 'stop' }} }}"), False, "red")
        if spec.get("red_ok"):
            lua.execute("AGPS_NS.Nav.redOk = { all = true }")
        cpu_set = time.perf_counter() - t0
        r = None
        frame = 0
        big_frames = 0
        for frame in range(max_frames):
            lua.execute(f"AGPS_T = {t_base + frame / 60.0}")
            f0 = time.perf_counter()
            if frame % 3 == 0:
                arm()
                r = N.Route(a[0], a[1], cont)
                d = time.perf_counter() - f0
                cpu_route += d
                route_calls += 1
                if d > 0.0003:
                    recomputes += 1
                if r is not None and first_route is None:
                    first_route = frame
            if R.HasWork():
                bigger = bool((R.Warming and R.Warming()) or (R.Building and R.Building()) or N.Fresh() or N.Landing())
                rer = (not bigger) and bool(N.Rerouting())
                budget = budget_fn(16.7, bigger or rer)
                big_frames += 1 if (bigger or rer) else 0
                p0 = time.perf_counter()
                arm()
                res = R.Pump(now() + budget, now)
                done, fixed = res if isinstance(res, tuple) else (res, None)
                if done:
                    N.SearchDone(fixed)
                cpu_pump += time.perf_counter() - p0
                quiet = 0
            else:
                quiet += 1
            fd = time.perf_counter() - f0
            worst_frame = max(worst_frame, fd)
            over6 += fd > 0.006
            over10 += fd > 0.010
            if settled is None and r is not None and not r.pending:
                settled = frame
            if settled is not None and quiet >= quiet_frames:
                break
        disarm()
        searches = [dict(s) for s in prof.searches.values()]
        jobs = {k: dict(v) for k, v in prof.jobs.items()}
        res = dict(label=label, settled_frame=settled, settled_s=settled / 60.0 if settled is not None else None,
                   quiet_frame=frame - quiet, frames=frame, first_route_frame=first_route,
                   cpu_setstops=cpu_set, cpu_route=cpu_route, cpu_pump=cpu_pump, route_calls=route_calls,
                   recomputes=recomputes, invalidates=prof.invalidates, big_frames=big_frames,
                   nodes=WG.stats.nodes + CG.stats.nodes - n0, tiles=WG.stats.tiles - tiles0,
                   regions=WG.stats.regions - regions0, worst_frame_ms=worst_frame * 1000, frames_over_6ms=over6,
                   frames_over_10ms=over10, yards=(r.totalYards if r is not None else None),
                   pending=(bool(r.pending) if r is not None else None),
                   parts=(len(r.parts) if r is not None and r.parts else 0),
                   searches=searches, jobs=jobs, samples=prof.samples,
                   byFunc=dict(prof.byFunc.items()), byLine=dict(prof.byLine.items()), byRoot=dict(prof.byRoot.items()),
                   heapMB=lua.eval('collectgarbage("count")') / 1024)
        # (let the rest of the queue run out)
        for _ in range(20000):
            if not R.HasWork():
                break
            R.Pump(now() + 50, now)
        return res

    out["runs"].append(one("cold", True))
    out["runs"].append(one("warm", False))
    if verbose:
        for run_ in out["runs"]:
            report(name, run_)
    return out


def report(name, r):
    print(f"\n=== {name} [{r['label']}] ===")
    ss = r["settled_s"]
    print(f"settled: {'never' if ss is None else f'{ss:.1f} s at 60 fps'} (frame {r['settled_frame']}), queue quiet at "
          f"{r['quiet_frame'] / 60.0:.1f} s; route {r['yards'] and round(r['yards'])} yd, {r['parts']} parts, "
          f"pending {r['pending']}")
    print(f"CPU: SetStops {r['cpu_setstops'] * 1000:.0f} ms, N.Route {r['cpu_route'] * 1000:.0f} ms in {r['route_calls']} "
          f"calls ({r['recomputes']} over 0.3 ms; {r['invalidates']} invalidates), background {r['cpu_pump'] * 1000:.0f} ms "
          f"({r['big_frames']} bigger-slice frames)")
    print(f"grid nodes {r['nodes']}, tiles decoded {r['tiles']}, regions loaded {r['regions']}, worst frame "
          f"{r['worst_frame_ms']:.1f} ms, frames > 6 ms: {r['frames_over_6ms']}, > 10 ms: {r['frames_over_10ms']}, "
          f"heap {r['heapMB']:.0f} MB")
    print("jobs (kind: finished, resumes, CPU ms, worst slice ms):")
    for k, j in sorted(r["jobs"].items(), key=lambda kv: -kv[1]["cpu"]):
        print(f"  {k:28s} {j['jobs']:4d} {j['resumes']:6d} {j['cpu'] * 1000:9.0f} {j['worst'] * 1000:7.1f}")
    print("searches (job kind, nodes, ms, us/node, heur, cap, alt, guards, red, road, maxDrop, tiles, found steps, cut):")
    for s in r["searches"]:
        kind = str(s["job"]).split(":")[0]
        us = s["ms"] * 1000 / max(1, s["nodes"])
        print(f"  {kind:18s} {s['nodes']:7d} {s['ms']:8.0f} {us:6.1f} h{s['heur']:<4} cap{s['cap']:<7} alt={int(s['alt'])} "
              f"g={int(s['guards'])} red={int(s['red'])} road={s['road']:.2f} drop={s['maxDrop']:<6.0f} "
              f"tiles={s['tiles']:<3} steps={s['found']:<5} cut={int(s['cut'])}")
    if r["samples"]:
        tot = sum(r["byRoot"].values())
        roots = {}
        for k, v in r["byRoot"].items():
            roots[k.split(" < ")[0]] = roots.get(k.split(" < ")[0], 0) + v
        print(f"sampled {r['samples']} samples, {tot * 1000:.0f} ms; by root:")
        for k, v in sorted(roots.items(), key=lambda kv: -kv[1])[:16]:
            print(f"  {k:26s} {v * 1000:9.0f} ms {100 * v / tot:5.1f}%")
        print("top functions (root < function):")
        for k, v in sorted(r["byRoot"].items(), key=lambda kv: -kv[1])[:28]:
            print(f"  {k:60s} {v * 1000:9.0f} ms {100 * v / tot:5.1f}%")


def main(argv):
    names, hook, out_json, patches = [], 2000, None, {}
    it = iter(argv)
    for arg in it:
        if arg == "--no-hook":
            hook = 0
        elif arg == "--hook":
            hook = int(next(it))
        elif arg == "--json":
            out_json = next(it)
        elif arg == "--patch":
            k, v = next(it).split("=", 1)
            patches[k] = v
        else:
            names.append(arg)
    results = []
    for n in names or list(TRIPS):
        results.append(run(n, hook_every=hook, patches=patches))
    if out_json:
        Path(out_json).write_text(json.dumps(results, indent=1, default=str), encoding="utf-8")


if __name__ == "__main__":
    main(sys.argv[1:])
