"""Route-speed study: two WorldGrid.lua files against each other on the same legs (WorldGrid.Walk at once, warm, the
least of N runs each): the nodes, the cost and the yards must be the same, the time is what's compared.

    python app/scripts/route_perf_ab.py BASE.lua [OTHER.lua] [--runs 3] [--set default|expert|roads-10]"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from azerothgps.gameharness import start  # noqa: E402
from azerothgps.paths import ADDON_DIR  # noqa: E402

LEGS = {
    "taurajo-ungoro": (1, (-2292.7, -2142.6), (-7446.7, -1316.7)),
    "tanaris-sands-ungoro": (1, (-6915.0, -2848.0), (-6830.0, -1975.0)),
    "taurajo-freewind": (1, (-2353.0, -1922.0), (-5454.0, -2446.0)),
    "ratchet-splintertree": (1, (-951.0, -3680.0), (2286.0, -2565.0)),
    "thelsamar-menethil": (0, (-5349.0, -2960.0), (-3673.0, -828.0)),
    "darkshire-booty": (0, (-10565.0, -1171.0), (-14383.0, 487.0)),
}
SETS = {"default": {}, "expert": dict(useClassSpells=True, expertJumper=True), "roads-10": dict(roadTolerance=-10)}


def load(path, sname):
    text = Path(path).read_text(encoding="utf-8") if path else None
    lua, ns = start(replace={"WorldGrid.lua": text} if text else None)
    st = ns.settings.gps
    st.worldGrid, st.cityGrid = True, True
    for k, v in SETS[sname].items():
        st[k] = v
    ns.WorldGrid.Set(True)
    ns.CityGrid.Set(True)
    spell = "id == 1259416" if sname == "expert" else "false"
    lua.execute("AGPS_LEVEL = 60; UnitFactionGroup = function() return 'Horde' end; "
                f"IsPlayerSpell = function(id) return {spell} end; GetItemCount = function() return 0 end")
    ns.CharDB().faction = "Horde"
    ns.FallSpells.Refresh()
    ns.Router.SYNC_WALKS = True
    return lua, ns


def walk(lua, ns, leg):
    WG = ns.WorldGrid
    cont, a, b = leg
    for t in ("routes", "order", "targets", "failed", "failOrder"):
        WG[t] = lua.table()
    n0 = WG.stats.nodes
    t0 = time.perf_counter()
    r = WG.Walk(WG.Cont(cont), a[0], a[1], None, b[0], b[1], None, lua.table())
    dt = time.perf_counter() - t0
    pts = tuple(r.pts.values()) if r else ()
    return dt, WG.stats.nodes - n0, (round(r.length, 3) if r else None), hash(pts)


def main(argv):
    files, runs, sname = [], 3, "default"
    it = iter(argv)
    for arg in it:
        if arg == "--runs":
            runs = int(next(it))
        elif arg == "--set":
            sname = next(it)
        else:
            files.append(arg)
    if len(files) == 1:
        files.append(str(ADDON_DIR / "WorldGrid.lua"))
    games = [load(f, sname) for f in files]
    tot = [0.0, 0.0]
    same = True
    for name, leg in LEGS.items():
        best, sig = [None, None], [None, None]
        for g in games:
            walk(*g, leg)  # (the tiles decoded, the far drops known)
        for _ in range(runs):
            for i, g in enumerate(games):
                dt, nodes, yd, h = walk(*g, leg)
                best[i] = dt if best[i] is None else min(best[i], dt)
                sig[i] = (nodes, yd, h)
        ok = sig[0] == sig[1]
        same = same and ok
        tot[0], tot[1] = tot[0] + best[0], tot[1] + best[1]
        print(f"{name:22s} nodes {sig[0][0]:7d} {sig[0][1]} yd: {best[0] * 1000:8.0f} ms -> {best[1] * 1000:8.0f} ms "
              f"({100 * (best[1] / best[0] - 1):+5.1f}%) {'same route' if ok else 'DIFFERENT ' + str(sig)}", flush=True)
    print(f"all: {tot[0] * 1000:.0f} ms -> {tot[1] * 1000:.0f} ms ({100 * (tot[1] / tot[0] - 1):+.1f}%), "
          f"{'every route the same' if same else 'ROUTES DIFFER'}")
    return 0 if same else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
