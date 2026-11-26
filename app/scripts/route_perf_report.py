"""Route-speed study: route_perf.py's --json, each trip's sampled time by part (the base WorldGrid.lua's line numbers).

    python app/scripts/route_perf_report.py hook.json [cold|warm]"""

import json
import re
import sys

ACCESS = {"WorldGrid.lua:514": "First", "WorldGrid.lua:521": "Flags", "WorldGrid.lua:522": "Z", "WorldGrid.lua:526": "Link",
          "WorldGrid.lua:532": "Pt", "WorldGrid.lua:151": "Bit", "WorldGrid.lua:1053": "Step", "WorldGrid.lua:282": "Origin",
          "WorldGrid.lua:288": "CellKey", "WorldGrid.lua:513": "Count", "WorldGrid.lua:1009": "Drop"}
HEAP = {"WorldGrid.lua:1024", "WorldGrid.lua:1034"}
HEUR = {"WorldGrid.lua:1809", "WorldGrid.lua:1457", "WorldGrid.lua:1399", "WorldGrid.lua:150"}
ORDER = ["neighbor decode (Link/Step/First/Pt/Z/Flags/Bit)", "search loop: settle + cost calc", "heap (Push/Pop)",
         "heuristic (line + landmark bound)", "far-drop scans (FarDrops + ground samples)", "tile lookup (decoded already)",
         "tile decode", "region load", "guards / high zones (Extra)", "walls (CrossesWall)", "string pulling (Pull/Line/Clear)",
         "pauses (Breathe, clock)", "planner + Router's own", "other"]


def part(root, func, line_ms):
    f = func.split("\\")[-1].split("/")[-1]
    if root == "WG.Tile":
        return None  # (by line, below)
    if root in ("WG.FarDrops", "Ground.Sample"):
        return ORDER[4]
    if f in HEAP:
        return ORDER[2]
    if root == "WG.Search":
        if f in ACCESS:
            return ORDER[0]
        if f in HEUR:
            return ORDER[3]
        if f == "WorldGrid.lua:1780":
            return ORDER[1]
        if f.startswith("Router.lua:15"):
            return ORDER[11]
        return ORDER[1]
    if root == "WG.LoadRegion":
        return ORDER[7]
    if root == "WG.Extra":
        return ORDER[8]
    if root == "P.CrossesWall":
        return ORDER[9]
    if root in ("WG.Pull", "WG.Line", "WG.Clear", "WG.Straighten"):
        return ORDER[10]
    if root in ("N.Plan", "R.Route", "WG.Costs", "CG.Search"):
        return ORDER[12]
    if root.startswith("WG.AltSearch"):
        return ORDER[3]
    return ORDER[13]


def main(argv):
    data = json.load(open(argv[0], encoding="utf-8"))
    which = argv[1] if len(argv) > 1 else "cold"
    rows = {}
    names = []
    for trip in data:
        run = next(r for r in trip["runs"] if r["label"] == which)
        names.append(trip["trip"])
        agg = {k: 0.0 for k in ORDER}
        for k, v in run["byRoot"].items():
            root, func = k.split(" < ")
            p = part(root, func, None)
            if p:
                agg[p] += v
        for k, v in run["byLine"].items():
            m = re.search(r"WorldGrid\.lua:(\d+)$", k)
            if m and 303 <= int(m.group(1)) <= 473:
                agg[ORDER[5] if int(m.group(1)) <= 310 else ORDER[6]] += v
        # (the Tile root's samples in other functions, the accessors its decode calls: decode)
        tile_root = sum(v for k, v in run["byRoot"].items() if k.startswith("WG.Tile < "))
        agg[ORDER[6]] += max(0.0, tile_root - agg[ORDER[5]] - agg[ORDER[6]])
        rows[trip["trip"]] = (agg, run)
    w = 22
    print(f"{'part':52s}" + "".join(f"{n[:w]:>{w}s}" for n in names))
    for k in ORDER:
        line = f"{k:52s}"
        for n in names:
            agg, run = rows[n]
            tot = sum(agg.values())
            line += f"{agg[k] * 1000:12.0f} ms {100 * agg[k] / tot:4.1f}%"[:w].rjust(w)
        print(line)
    print(f"{'sampled':52s}" + "".join(f"{sum(rows[n][0].values()) * 1000:19.0f} ms" for n in names))
    for label, fn in (("settled (s at 60 fps)", lambda r: f"{r['settled_s']:.1f}" if r["settled_s"] is not None else "never"),
                      ("queue quiet (s)", lambda r: f"{r['quiet_frame'] / 60:.0f}"),
                      ("grid nodes", lambda r: str(r["nodes"])), ("searches", lambda r: str(len(r["searches"]))),
                      ("tiles decoded", lambda r: str(r["tiles"])), ("regions loaded", lambda r: str(r["regions"])),
                      ("route yd", lambda r: str(round(r["yards"] or 0))),
                      ("plan jobs (route:)", lambda r: str(r["jobs"].get("route", {}).get("jobs", 0))),
                      ("invalidates", lambda r: str(r["invalidates"])),
                      ("worst frame ms", lambda r: f"{r['worst_frame_ms']:.0f}")):
        print(f"{label:52s}" + "".join(f"{fn(rows[n][1]):>{w}s}" for n in names))


if __name__ == "__main__":
    main(sys.argv[1:])
