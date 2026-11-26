"""Route-speed study: the grid's own walk (WorldGrid.Walk, searched at once) for a set of long legs under several
settings, nodes and CPU per search. Used for the heuristic experiments (Expert jumper on/off, Road tolerance, the
landmark fields on/off, the heuristic's weight).

    python app/scripts/route_perf_walks.py [--patch WorldGrid.lua=path] [--lua "WG.X = 1"] [--set name]"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from azerothgps.gameharness import start  # noqa: E402

SLOW_FALL = 1259416
LEGS = {
    "taurajo-ungoro": (1, (-2292.7, -2142.6), (-7446.7, -1316.7)),
    "xroads-gadgetzan": (1, (-441.8, -2596.1), (-7139.0, -3752.0)),
    "freewind-mojache": (1, (-5454.0, -2446.0), (-4420.0, 200.0)),
    "tanaris-sands-ungoro": (1, (-6915.0, -2848.0), (-6830.0, -1975.0)),
    "taurajo-freewind": (1, (-2353.0, -1922.0), (-5454.0, -2446.0)),
    "ratchet-splintertree": (1, (-951.0, -3680.0), (2286.0, -2565.0)),
    "sunrock-desolace": (1, (936.0, 911.0), (-1350.0, 1983.3)),
    "org-xroads": (1, (1550.8, -4411.4), (-441.8, -2596.1)),
    "thelsamar-menethil": (0, (-5349.0, -2960.0), (-3673.0, -828.0)),
    "southshore-refuge": (0, (-803.0, -532.0), (-1251.0, -2527.0)),
    "darkshire-booty": (0, (-10565.0, -1171.0), (-14383.0, 487.0)),
}
SETS = {
    "default": {},
    "expert": dict(useClassSpells=True, expertJumper=True, _spell=True),
    "roads-10": dict(roadTolerance=-10),
    "roads+10": dict(roadTolerance=10),
    "no-guards": dict(avoidHostile=False),
}


def run(sets, patches=None, pre_lua=None, legs=None, side="Horde"):
    replace = {k: Path(v).read_text(encoding="utf-8") for k, v in (patches or {}).items()} or None
    rows = []
    for sname in sets:
        lua, ns = start(replace=replace)
        if pre_lua:
            lua.execute(pre_lua)
        R, N, WG, CG = ns.Router, ns.Nav, ns.WorldGrid, ns.CityGrid
        st = ns.settings.gps
        st.worldGrid, st.cityGrid = True, True
        spec = dict(SETS[sname])
        spell = spec.pop("_spell", False)
        for k, v in spec.items():
            st[k] = v
        WG.Set(True)
        CG.Set(True)
        lua.execute(f"AGPS_LEVEL = 60; UnitFactionGroup = function() return '{side}' end")
        lua.execute(f"IsPlayerSpell = function(id) return {'id == %d' % SLOW_FALL if spell else 'false'} end; "
                    "GetItemCount = function() return 0 end")
        ns.CharDB().faction = side
        ns.FallSpells.Refresh()
        R.SYNC_WALKS = True
        lua.globals().PROF_CLOCK = time.perf_counter
        lua.execute("""
          local WG = AGPS_NS.WorldGrid
          local search = WG.Search
          PROF_LOG = {}
          WG.Search = function(c, starts, goals, tx, ty, inside, x)
            local t0 = PROF_CLOCK()
            local steps = search(c, starts, goals, tx, ty, inside, x)
            PROF_LOG[#PROF_LOG + 1] = string.format("%s%d/%.0fms%s%s", (x and x.heur or WG.HEUR) > 2 and "w" or "e", WG.lastNodes,
              (PROF_CLOCK() - t0) * 1000, steps and "" or "!", WG.AltAllowed(x, c) and "" or "-noalt")
            return steps
          end
        """)
        for name, (cont, a, b) in (legs or LEGS).items():
            c = WG.Cont(cont)
            for t in ("routes", "order", "targets", "failed", "failOrder"):
                WG[t] = lua.table()
            # (twice: the second with the tiles decoded and the far drops known)
            out = []
            for _ in range(2):
                for t in ("routes", "order", "targets", "failed", "failOrder"):
                    WG[t] = lua.table()
                n0, s0 = WG.stats.nodes, WG.stats.searches
                lua.execute("PROF_LOG = {}")
                t0 = time.perf_counter()
                r = WG.Walk(c, a[0], a[1], None, b[0], b[1], None, lua.table())
                dt = time.perf_counter() - t0
                out.append((WG.stats.nodes - n0, WG.stats.searches - s0, dt, r.length if r else None))
            cold, warm = out
            rows.append((sname, name, cold, warm))
            yd = f"{warm[3]:7.0f}" if warm[3] else "   none"
            print(f"{sname:10s} {name:22s} nodes {warm[0]:7d} in {warm[1]} searches, cold {cold[2] * 1000:7.0f} ms, "
                  f"warm {warm[2] * 1000:7.0f} ms ({warm[2] * 1e6 / max(1, warm[0]):5.1f} us/node), {yd} yd  "
                  + " ".join(lua.eval("PROF_LOG").values()), flush=True)
    return rows


def main(argv):
    patches, pre, sets = {}, None, []
    it = iter(argv)
    for arg in it:
        if arg == "--patch":
            k, v = next(it).split("=", 1)
            patches[k] = v
        elif arg == "--lua":
            pre = next(it)
        elif arg == "--set":
            sets.append(next(it))
    run(sets or list(SETS), patches, pre)


if __name__ == "__main__":
    main(sys.argv[1:])
