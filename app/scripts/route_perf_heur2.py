"""Route-speed study: the landmark bound weighed with the straight line. On long legs the search's heuristic is
max(3 x the straight line, 1 x the landmark bound): the bound almost never wins there. Here the bound is weighed too.

    python app/scripts/route_perf_heur2.py [leg ...]"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from azerothgps.gameharness import start  # noqa: E402
from route_perf_heur import LEGS, LUA  # noqa: E402

MORE = r"""
local WG = AGPS_NS.WorldGrid
local altSearch = WG.AltSearch
function H.AltScale(k)
  if not k then WG.AltSearch = altSearch return end
  WG.AltSearch = function(...)
    local AB = altSearch(...)
    return AB and function(key, ci) return AB(key, ci) * k end
  end
end
"""


def main(argv):
    for name in argv or ["taurajo-ungoro", "xroads-gadgetzan", "tanaris-sands-ungoro", "taurajo-freewind",
                         "ratchet-splintertree", "darkshire-booty"]:
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
        lua.execute(MORE)
        H = lua.globals().H
        H.Setup(cont, a[0], a[1], b[0], b[1])
        print(f"\n=== {name} ===", flush=True)
        H.Run(3, True, None, None)
        for heur, k in ((3, None), (3, 1.5), (3, 2), (3, 3), (2, 2), (1.5, 1.5), (1.5, None)):
            H.AltScale(k)
            nodes, cost, ms, steps, cut = H.Run(heur, True, None, None)
            print(f"  line x{heur}, landmark bound x{k or 1}: nodes {int(nodes):8d}  cost {cost:9.1f}  {ms:8.0f} ms  "
                  f"steps {int(steps):5d}", flush=True)
        H.AltScale(None)


if __name__ == "__main__":
    main(sys.argv[1:])
