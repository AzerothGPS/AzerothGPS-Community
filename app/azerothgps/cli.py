"""agps: developer tools for the AzerothGPS addon.

The addon runs entirely in game. These commands read the *local* client to
generate the addon's data files and to inspect/test it.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

from .paths import ADDON_DIR, DEFAULT_FLAVOR, DEFAULT_WOW, data_dir, wtf_account_dir

DATA = data_dir()
PRODUCT = "wowf"  # WoW Forever, released 2026-10 (the beta was "wow_classic_beta")


def _client(args):
    from .extract.spike import ClientData

    ref = DATA / "ref"
    if not (ref / "listfile.csv").exists():
        raise SystemExit(f"missing {ref / 'listfile.csv'} (community listfile) and {ref / 'dbd'}/*.dbd")
    t = time.time()
    cd = ClientData(Path(args.wow_path), args.product, ref)
    print(f"client {args.product} {cd.casc.version} ({time.time() - t:.1f}s)")
    return cd


def cmd_extract(args) -> int:
    from .extract.pipeline import run_extract

    cd = _client(args)
    manifest = run_extract(cd, DATA)
    if not args.skip_roads:
        from .roads.build import build_roads

        manifest["roads"] = build_roads(cd, DATA)
        (DATA / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps(manifest, indent=2))
    return 0


def cmd_roads(args) -> int:
    from .roads.build import build_roads

    cd = _client(args)
    print(json.dumps(build_roads(cd, DATA, tuple(args.continents) if args.continents else None), indent=2))
    return 0


def _override_keys(folder: Path) -> set:
    """The drawn fixes in overrides/roads_*.geojson, as keys (continent, first points)."""
    keys = set()
    for f in folder.glob("roads_*.geojson"):
        for feat in json.loads(f.read_text(encoding="utf-8")).get("features", []):
            keys.add((f.stem, json.dumps(feat["geometry"]["coordinates"][:2])))
    return keys


def _touches_capital(folder: Path, before: set) -> bool:
    """Whether a drawn fix new since `before` lies over a capital's map (its roads take them)."""
    from .capitals import CAPITALS
    from .cityplaces import map_bounds

    maps = map_bounds()
    for f in folder.glob("roads_*.geojson"):
        for feat in json.loads(f.read_text(encoding="utf-8")).get("features", []):
            if (f.stem, json.dumps(feat["geometry"]["coordinates"][:2])) in before:
                continue
            for cap in CAPITALS:
                cont, b = maps[cap.ui_map]
                if f.stem == f"roads_{cont}" and any(b[0] <= p[0] <= b[2] and b[1] <= p[1] <= b[3]
                                                    for p in feat["geometry"]["coordinates"]):
                    return True
    return False


def cmd_watch_roads(args) -> int:
    """Each time the game writes the saved variables (a /reload, logging out): the roads drawn
    in game that are new go into overrides/ and the road data, and the addon is installed
    again (the next /reload has them as roads of its own; the drawn copies are dropped)."""
    from .extract.pipeline import CONTINENTS
    from .paths import RESOURCES
    from .roads.build import reapply_overrides
    from .roads.export import write_roads_lua
    from .roads.recorded import Walks
    from .roads.tracks import import_tracks

    # (with --also-wtf: another client's account folders too, a test client's saved files copied here, 2026-10-08:
    # only the walks recorded there with Record since --also-since, never its strokes or walls, which its test runs
    # draw; their heights still worked out on this client's floors, each one said)
    # (with --own-wtf: another client's account folders whose edits all count, strokes and walls too: a second
    # client the user plays and tests on themselves, 2026-10-14; never its dungeons' ways in, GM
    # teleports. --wtf: the account folders read instead of the game's, a snapshot of them)
    wtf = Path(args.wtf) if getattr(args, "wtf", None) else wtf_account_dir(Path(args.wow_path), args.flavor)
    also = [Path(p) for p in getattr(args, "also_wtf", None) or []]
    own = [Path(p) for p in getattr(args, "own_wtf", None) or []]
    since = getattr(args, "also_since", None)
    since = time.mktime(time.strptime(since, "%Y-%m-%d %H:%M")) if since else 0
    wtfs = [wtf] + own + also
    print(f"watching {', '.join(map(str, wtfs))} for drawn roads (Ctrl+C stops)")
    last: dict = {}
    # (walks recorded in game: their heights worked out over the floors under them, the client opened at the first)
    walks = Walks(lambda: _client(args), log=print)

    def recorded_since(t) -> bool:
        return bool(t.get("recorded")) and t["time"] >= since

    def walks_said(t):
        pieces = walks(t)
        if pieces:
            x, y = t["coords"][0]
            print(f"{time.strftime('%H:%M:%S')} a walk recorded on another client: {t['zone']} from {x:.1f}, {y:.1f} "
                  f"(continent {t['continent']}, recorded {time.strftime('%m-%d %H:%M', time.localtime(t['time']))}, "
                  f"{len(t['coords'])} points, {len(pieces)} piece(s))")
        return pieces
    while True:
        files = sorted(f for wtf in wtfs for f in wtf.glob("*/SavedVariables/AzerothGPS.lua"))
        cur = {f: f.stat().st_mtime for f in files}
        if cur != last:
            try:
                per: dict = {}
                before = _override_keys(RESOURCES / "overrides")
                n = sum(import_tracks(w, RESOURCES / "overrides", per, walks=walks) for w in [wtf] + own)
                n += sum(import_tracks(w, RESOURCES / "overrides", per, walks=walks_said, only=recorded_since)
                         for w in also)
                # (dungeons' ways in, learned or taken in from someone's shared map data. Never pins, nor NPCs,
                # herbs or ore: they're the players' to discover and share, never in the data, asked 2026-10-06. Not
                # the other clients': a GM's teleport into a dungeon there would be learned as its way in)
                ne_ = _import_saved_entrances(wtf)
                last = cur
                if ne_ and not n:
                    print(f"{time.strftime('%H:%M:%S')} {ne_} dungeon way(s) in "
                          "(agps instances --write puts the ways in into Instances.lua)")
                if n:
                    stamp = time.strftime("%H:%M:%S")
                    print(f"{stamp} {n} new drawn road(s): {per}")
                    reapply_overrides(DATA, [c for c in per if c in CONTINENTS])
                    if any(c not in CONTINENTS for c in per):  # (a city's own level)
                        from .cities import cities_lua

                        (ADDON_DIR / "Data" / "Cities.lua").write_text(cities_lua(_client(args)), encoding="utf-8",
                                                                       newline="\n")
                    write_roads_lua(DATA, ADDON_DIR)
                    # (over a capital: its roads take the drawn fixes too, capitals.drawn_fixes; then the
                    # buildings, whose cells a road keeps open)
                    if _touches_capital(RESOURCES / "overrides", before):
                        from .buildings import FILE as BFILE, buildings_lua
                        from .capitals import build_all, capitals_lua

                        print(f"{time.strftime('%H:%M:%S')} over a capital: its roads again (a few minutes)")
                        cd = _client(args)
                        built = build_all(cd, DATA, log=lambda *a: None)
                        (ADDON_DIR / "Data" / "Capitals.lua").write_text(capitals_lua(cd, log=lambda *a: None, built=built),
                                                                         encoding="utf-8", newline="\n")
                        BFILE.write_text(buildings_lua(cd, log=lambda *a: None)[0], encoding="utf-8", newline="\n")
                    if args.no_install:  # (a release build being tested in game: left as it is)
                        print(f"{time.strftime('%H:%M:%S')} in the road data (not installed: --no-install)")
                    else:
                        cmd_install_addon(args)
                        print(f"{time.strftime('%H:%M:%S')} in the road data: /reload in game to load it")
            except Exception as e:  # (e.g. read while the game was still writing it: again next time)
                print(f"couldn't import yet: {e}")
        if args.once:
            return 0
        time.sleep(args.interval)


def _import_saved_entrances(wtf: Path) -> int:
    """Dungeons' ways in in the saved variables (learned, or taken in from shared map data) into
    overrides/instance_entrances.json: how many were new."""
    from .instances import merge_entrances, saved_entrances
    from .savedvars.parser import load_savedvariables

    return sum(merge_entrances(saved_entrances(load_savedvariables(f)), log=lambda *a: None)
               for f in sorted(wtf.glob("*/SavedVariables/AzerothGPS.lua")))


def cmd_npc_paths(args) -> int:
    from .extract.pipeline import CONTINENTS
    from .paths import RESOURCES
    from .roads.npcpaths import write_overrides

    print(write_overrides(DATA, RESOURCES / "overrides", CONTINENTS))
    print("then: agps roads (or agps watch-roads picks them up with the next drawn road)")
    return 0


def cmd_route_check(args) -> int:
    from .routecheck import check, write_report

    modes = ("offroad", "road") if args.mode == "both" else (args.mode,)
    result = check(samples=args.samples, seed=args.seed, only=args.zone, modes=modes, faction=args.faction)
    out = write_report(result, DATA / "debug" / ("route-check" + (f"-{args.name}" if args.name else "")))
    n = len(result["flagged"])
    trips = sum(z["trips"] for z in result["zones"])
    print(f"{n} flagged of {trips} trips in {len(result['zones'])} zones; details: {out}")
    return 0


def cmd_route_sweep(args) -> int:
    from .routesweep import sweep, write_report

    result = sweep(trips=args.trips, seed=args.seed, only=args.zone, minutes=args.minutes)
    out = write_report(result, DATA / "debug" / "route-sweep")
    print(f"{len(result['flagged'])} flagged of {result['trips']} trips (seed {result['seed']}); details: {out}")
    return 0


def cmd_route_quality(args) -> int:
    from .routequality import run

    res = run(args.trips, args.seed, args.against, jobs=args.jobs)
    out_dir = DATA / "debug" / "route-quality"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / "report.json"
    out.write_text(json.dumps(res, indent=1), encoding="utf-8")
    print(f"{res['same']} same, {len(res['better'])} better, {len(res['worse'])} worse, {len(res['found'])} with a way where "
          f"there was none, {len(res['lost'])} with none where there was one, {len(res['errors'])} errors "
          f"(against {args.against}); details: {out}")
    for r in res["worse"] + res["lost"]:
        print(f"  worse: {r['trip']}: {r['before']} s -> {r['after']} s  {r['rides_before']} -> {r['rides_after']}")
    for r in res["redrawn"]:
        print(f"  slower along roads this change drew (not worse): {r['trip']}: {r['before']} s -> {r['after']} s")
    for r in res.get("walled", []):
        print(f"  slower round walls this change drew (not worse): {r['trip']}: {r['before']} s -> {r['after']} s")
    for r in res.get("safer", []):
        print(f"  slower past fewer of the other faction's guards (not worse): {r['trip']}: {r['before']} s -> "
              f"{r['after']} s, {r['guard_before']} -> {r['guard_after']} yd in their reach")
    for r in res.get("unguarded", []):
        print(f"  slower past posts this change dropped as guards (not worse): {r['trip']}: {r['before']} s -> "
              f"{r['after']} s, {r['new_old_guard']} yd in the older version's guards' reach")
    for r in res.get("unhopped", []):
        print(f"  slower where the older route's walks hopped blocked ground (not worse): {r['trip']}: {r['before']} s -> "
              f"{r['after']} s, its older walks {r['blocked_before']} -> {r['old_walks_blocked']} yd straight over it")
    for r in res.get("asking", []):
        print(f"  slower on the safe way while the game asks to risk the guards (not worse): {r['trip']}: {r['before']} s "
              f"-> {r['after']} s, {r['guard_before']} -> {r['guard_after']} yd in their reach")
    for r in res.get("deep", []):
        print(f"  slower where the older route swam fatigue water this change closes (not worse): {r['trip']}: "
              f"{r['before']} s -> {r['after']} s, {r['deep_before']} -> {r['deep_after']} yd of it")
    return 1 if res["errors"] else 0


def cmd_trip_sweep(args) -> int:
    from .tripsweep import sweep, write_report

    if args.replay:  # (an earlier report's flagged trips, run again: after a fix)
        old = json.loads(Path(args.replay).read_text(encoding="utf-8"))
        result = sweep(seed=old.get("seed"), replay=old["flagged"])
        out = write_report(result, DATA / "debug" / "trip-sweep", "replay.json")
    else:
        result = sweep(trips=args.trips, minutes=args.minutes, seed=args.seed)
        out = write_report(result, DATA / "debug" / "trip-sweep")
    print(f"{len(result['flagged'])} flagged of {result['trips']} trips (seed {result['seed']}); details: {out}")
    return 0


def cmd_gen_addon_data(args) -> int:
    from .addon_data import generate

    cd = _client(args)
    for p in generate(cd, ADDON_DIR):
        print(f"wrote {p} ({p.stat().st_size // 1024} KB)")
    return 0


def cmd_transit(args) -> int:
    """Maps you pass through (the Deeprun Tram): with --write, Data/Transit.lua (their art, shown like a
    dungeon's map)."""
    from .instances import transit_lua

    cd = _client(args)
    text = transit_lua(cd)
    if args.write:
        p = ADDON_DIR / "Data" / "Transit.lua"
        p.write_text(text, encoding="utf-8", newline="\n")
        print(f"wrote {p} ({p.stat().st_size // 1024} KB)")
    return 0


def cmd_dungeon_maps(args) -> int:
    """Dungeons' world maps from another WoW version, each floor checked against WoW Forever's own client
    (dungeonmaps.py): the inventory (accepted and skipped, and why), renders in data/debug/dungeonmaps/; with
    --write Data/DungeonMaps.lua, app/azerothgps/data/dungeon_maps.json and docs/dungeon-maps.md."""
    from .dungeonmaps import inventory, write
    from .extract.spike import ClientData

    cd = _client(args)
    src = ClientData(Path(args.wow_path), args.source, DATA / "ref")
    print(f"source {args.source} {src.casc.version}")
    inv = inventory(cd, src, debug_dir=DATA / "debug" / "dungeonmaps")
    rows = inv["dungeons"]
    n = sum(e["status"] == "accepted" for e in rows)
    nf = sum(f["status"] == "accepted" for e in rows for f in e["floors"])
    print(f"{n} of {len(rows)} dungeons and raids with a map from {args.source} ({nf} floors); "
          f"renders in {DATA / 'debug' / 'dungeonmaps'}")
    if args.write:
        for p in write(inv, ADDON_DIR):
            print(f"wrote {p}")
    return 0


def cmd_interior_maps(args) -> int:
    """Interiors' maps (caves, mines, cellars) from another WoW version, each floor checked against WoW Forever's
    own client (interiormaps.py): the inventory (accepted, skipped, unavailable, and why), renders in
    data/debug/interiormaps/; with --write Data/InteriorMaps.lua, app/azerothgps/data/interior_maps.json and
    docs/interior-maps.md."""
    from .extract.spike import ClientData
    from .interiormaps import inventory, write

    cd = _client(args)
    src = ClientData(Path(args.wow_path), args.source, DATA / "ref")
    print(f"source {args.source} {src.casc.version}")
    inv = inventory(cd, src, debug_dir=DATA / "debug" / "interiormaps")
    rows = inv["interiors"]
    n = sum(e["status"] == "accepted" for e in rows)
    nf = sum(f["status"] == "accepted" for e in rows for f in e["floors"])
    nc = sum(c["status"] == "accepted" for c in inv["caves"])
    print(f"{n} of {len(rows)} of {args.source}'s interior maps match ({nf} floors); {nc} of {len(inv['caves'])} of "
          f"WoW Forever's caves get a map; renders in {DATA / 'debug' / 'interiormaps'}")
    if args.write:
        for p in write(inv, ADDON_DIR):
            print(f"wrote {p}")
    return 0


def cmd_media(args) -> int:
    from .media import make
    from .paths import REPO

    files = make(ADDON_DIR / "Media", REPO / "assets")
    print(f"wrote {len(files)} corner logos in {ADDON_DIR / 'Media'} (new files: a full game restart)")
    return 0


def cmd_setup_art(args) -> int:
    from .setupart import make

    files = make(ADDON_DIR / "Media", Path(args.src), Path(args.preview) if args.preview else None)
    print(f"wrote {len(files)} setup pictures in {ADDON_DIR / 'Media' / 'Setup'} (new files: a full relog)")
    return 0


def cmd_padicons(args) -> int:
    from . import padicons

    files = padicons.write()
    print(f"wrote {len(files)} controller icons and diagrams in {padicons.PAD_DIR} (new files: a /reload)")
    if args.preview:
        for p in padicons.preview(Path(args.preview)):
            print(f"preview {p}")
    return 0


def cmd_toolicons(args) -> int:
    from . import toolicons

    files = toolicons.write()
    print(f"wrote {len(files)} tool and pin icons in {toolicons.TOOLS_DIR} (new files: log out and back in)")
    if args.preview:
        for p in toolicons.preview(Path(args.preview)):
            print(f"preview {p}")
    return 0


def cmd_keyicons(args) -> int:
    from . import keyicons

    files = keyicons.write()
    print(f"wrote {len(files)} keyboard key caps in {keyicons.KEYS_DIR} (new files: log out and back in)")
    if args.preview:
        for p in keyicons.preview(Path(args.preview)):
            print(f"preview {p}")
    return 0


def cmd_floors(args) -> int:
    """NPCs and quest objectives off the ground floor (upstairs, a cellar, a tower's top): a report for planning,
    data/debug/floors/report.md and floors.json (app/azerothgps/floors.py). Nothing goes into the addon."""
    from . import floors as F

    cd = _client(args)
    t = time.time()
    res = F.classify(cd, F.load(DATA))
    out = DATA / "debug" / "floors"
    F.report(res, out)
    print(f"wrote {out / 'report.md'} ({time.time() - t:.0f} s)")
    return 0


def cmd_doodads(args) -> int:
    """The doodads a character bumps into (trees, rocks, planters, a city's stalls: their collision) near a spot;
    --render a picture of them with the models' walls, the land's roads and a route (data/debug/doodads/)."""
    import json

    from . import doodads as D

    cd = _client(args)
    X, Y, R = args.x, args.y, args.r
    found = D.near(cd, args.cont, X, Y, R)
    print(f"{len(found)} doodads with collision within {R:.0f} yd of ({X:.1f}, {Y:.1f}) [{args.cont}]")
    for f in found:
        b = f["box"]
        print(f"  {f['dist']:5.1f} yd  {'wmo' if f['wmo'] else 'adt'} ({b[0]:.1f}, {b[1]:.1f})-({b[2]:.1f}, {b[3]:.1f})"
              f" z {f['z']:.1f}  {f['name'].split('/')[-1]}")
    if args.render:
        out = DATA / "debug" / "doodads"
        out.mkdir(parents=True, exist_ok=True)
        path = out / f"doodads_{args.cont}_{X:.0f}_{Y:.0f}.png"
        route = json.loads(Path(args.route).read_text(encoding="utf-8")) if args.route else None
        D.render(cd, args.cont, X, Y, R, path, route=route, z=args.z)
        print(path)
    return 0


def cmd_buildings(args) -> int:
    """Buildings as cells routes don't walk through: --render X Y R a picture of those around a spot
    (data/debug/buildings/), --write Data/Buildings.lua."""
    from . import buildings as B

    cd = _client(args)
    if args.render:
        X, Y, R = args.render
        out = DATA / "debug" / "buildings"
        out.mkdir(parents=True, exist_ok=True)
        path = out / f"buildings_{args.cont}_{X:.0f}_{Y:.0f}.png"
        print(B.render(cd, args.cont, X, Y, R, path), path)
    if args.write:
        t = time.time()
        text, counts = B.buildings_lua(cd)
        B.FILE.write_text(text, encoding="utf-8", newline="\n")
        print(f"wrote {B.FILE} ({B.FILE.stat().st_size // 1024} KB, {time.time() - t:.0f} s): cells blocked "
              + ", ".join(f"[{c}] {n}" for c, n in counts.items()))
    return 0


def cmd_bridges(args) -> int:
    """The continents' bridges' outlines (Data/Bridges.lua): the directions' "Cross the bridge"."""
    from . import bridges as BR

    cd = _client(args)
    text, counts = BR.bridges_lua(cd)
    if args.write:
        BR.FILE.write_text(text, encoding="utf-8", newline="\n")
        print(f"wrote {BR.FILE} ({BR.FILE.stat().st_size // 1024} KB): bridges "
              + ", ".join(f"[{c}] {n}" for c, n in counts.items()))
    else:
        print(text)
    return 0


def cmd_heights(args) -> int:
    """The ground's height per map tile (Data/Heights.lua; 1.3.10, issue #685): 8 yd when both continents fit in
    heights.MAX_BYTES, else 16 yd (--step forces one)."""
    from . import heights as HT

    cd = _client(args)
    steps = (args.step,) if args.step else (2, 4)
    for step in steps:
        t = time.time()
        tiles = {c: HT.continent_tiles(cd, c, step) for c in HT.CONTINENTS}
        text = HT.heights_lua(tiles, step, cd.casc.version)
        size = len(text.encode("utf-8"))
        print(f"{128 // step} cells a tile ({HT.adt.TILE_YD * step / 128:.1f} yd): {size / 1048576:.2f} MB, "
              f"{sum(len(v) for v in tiles.values())} tiles ({time.time() - t:.0f} s)")
        if size <= HT.MAX_BYTES or step == steps[-1]:
            break
    if args.write:
        HT.FILE.write_text(text, encoding="utf-8", newline="\n")
        print(f"wrote {HT.FILE} ({HT.FILE.stat().st_size // 1024} KB)")
    return 0


def cmd_coast(args) -> int:
    """The seamless map's coastline masks (issue #73): a report; --render X Y R a picture (data/debug/coast/),
    --write Data/Coast.lua and Media/Coast/."""
    from . import coast as C

    if args.render:
        X, Y, R = args.render
        print(C.render(args.cont, X, Y, R, DATA / "debug" / "coast" / f"coast_{args.cont}_{X:.0f}_{Y:.0f}.png"))
    if args.buttons:
        C.write_buttons()
    if args.write:
        C.write()
    elif not (args.render or args.buttons):
        C.build()
    return 0


def cmd_isle_mask(args) -> int:
    """The seamless map's isles' land masks (issue #90): a report; --write Atlas/Media/Textures/MapIsle/."""
    from . import islemask as I
    from .extract.casc import CascStorage

    st = CascStorage(Path(args.wow_path), args.product)
    print(f"client {args.product} {st.version}")
    if args.write:
        I.write(st.read)
    else:
        for map_id in I.ISLES:
            m = I.mask(I.compose(st.read, map_id))
            print(f"uiMap {map_id}: island {(m[..., 3] > 127).mean():.1%} of the page")
    return 0


def cmd_indoors(args) -> int:
    """Buildings' insides as roads with floors and stairs (the towns in indoors.TOWNS): list each, with --write
    Data/Indoors.lua."""
    from . import indoors as D

    cd = _client(args)
    t = time.time()
    towns = args.town or ([] if args.npcs else list(D.TOWNS))
    built = []
    for town in towns:
        built += D.build_town(cd, town)
    if not args.town:  # (and every building with an NPC upstairs or in a cellar: phase 6, those its inside helps)
        built += D.npc_reached(cd, D.build_npc_buildings(cd))
    D.walk_joins(built)  # (the doors further from a road: walked to it on the terrain)
    print(f"{len(built)} buildings in {', '.join(towns + ([] if args.town else ['the NPCs buildings']))}"
          f" ({time.time() - t:.0f} s)")
    out = DATA / "debug" / "indoors"
    for b in built:
        safe = re.sub(r'[<>:"/\|?*]', "_", f"{b['town']}_{b['uid']}_{b['name']}")  # (a file name Windows takes)
        D.render(cd, b, out / f"{safe}.png")
    print(f"pictures: {out}")
    if args.check:
        res = D.check(cd, built)
        bad = [r for r in res if not r["ok"]]
        print(f"{len(res) - len(bad)} of {len(res)} places reached through their buildings' insides")
    if args.write:
        D.FILE.write_text(D.indoors_lua(cd, built), encoding="utf-8", newline="\n")
        print(f"wrote {D.FILE} ({D.FILE.stat().st_size // 1024} KB)")
    return 0


def cmd_caves(args) -> int:
    """Caves and mines: build them, render each (data/debug/caves/), list what's covered and
    what's skipped (summary.txt), and with --write, Data/Caves.lua."""
    from .caves import build_continent, caves_lua, render_debug

    cd = _client(args)
    out = DATA / "debug" / "caves"
    report: list = []
    if args.only:
        for cont in (0, 1):
            for u in build_continent(cd, cont, DATA, only=args.only, report=report):
                render_debug(u, out)
    else:
        text = caves_lua(cd, debug_dir=out, report=report)
        if args.write:
            p = ADDON_DIR / "Data" / "Caves.lua"
            p.write_text(text, encoding="utf-8", newline="\n")
            print(f"wrote {p} ({p.stat().st_size // 1024} KB)")
            from .hpa import refresh

            refresh()  # (the caves' grids are laid over the terrain the blocks are made from: Data/TerrainHPA.lua)
    lines = [f"{status:8s} [{cont}] {name or '(unnamed)'} ({uid}) {path.split('/')[-1]}: {why}"
             for cont, name, uid, path, status, why in sorted(report, key=lambda r: (r[4], r[0], r[1] or "~"))]
    out.mkdir(parents=True, exist_ok=True)
    (out / "summary.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    n = sum(1 for r in report if r[4] == "covered")
    print(f"{n} caves covered, {len(report) - n} skipped; renders and summary.txt in {out}")
    return 0


def _dev_addon() -> Path | None:
    """The developer addon's folder: a checkout next to this repo named in private_paths.py (the maintainers' own,
    not in every copy of this repo), or None."""
    try:
        from .private_paths import DEV_ADDON
    except ImportError:
        return None
    return ADDON_DIR.parents[2].joinpath(*DEV_ADDON)


def cmd_city_roads(args) -> int:
    """A capital's roads straightened and thinned over its navmesh (cityroads.py, issue #829)."""
    from . import cityroads

    res = cityroads.run(args.city, write=args.write)
    if args.check:
        out = cityroads.check(args.city, args.against)
        (DATA / "debug" / "cityroads" / f"{args.city.lower().replace(' ', '_')}_check.json").write_text(
            json.dumps(out, indent=1), encoding="utf-8")
    print(f"{len(res.flags)} roads the mesh can't walk: data/debug/cityroads/ (for recording in game)")
    return 0


def cmd_navmesh(args) -> int:
    """The capitals' and Undercity's Recast meshes (recastmesh.py, a dev tool: nothing ships): `build-tool` compiles
    navbuild.exe with zig over Recast's sources in data/thirdparty/recastnavigation; `build` makes each city's mesh
    (data/navmesh/: recastmesh.sources) and
    the developer addon's NavMeshData.lua (where one is checked out: _dev_addon()), for its route comparison."""
    import shutil
    import subprocess
    import sys

    from . import recastmesh as RM

    if args.what == "build-tool":
        rc = DATA / "thirdparty" / "recastnavigation" / "Recast"
        if not rc.is_dir():
            print(f"no Recast sources at {rc}: git clone --depth 1 https://github.com/recastnavigation/recastnavigation.git "
                  f"{rc.parent}")
            return 1
        src = Path(__file__).resolve().parent / "navbuild" / "navbuild.cpp"
        RM.tool().parent.mkdir(parents=True, exist_ok=True)
        cmd = [sys.executable, "-m", "ziglang", "c++", "-O2", "-std=c++17", "-target", "x86_64-windows-gnu",
               "-I", str(rc / "Include"), str(src), *map(str, sorted((rc / "Source").glob("*.cpp"))), "-o", str(RM.tool())]
        r = subprocess.run(cmd)
        print(f"built {RM.tool()}" if r.returncode == 0 else "build failed (pip install ziglang?)")
        return r.returncode
    if args.what == "compare":  # (the roads against the meshes built: navcompare.py)
        from . import navcompare

        return 0 if navcompare.run(only=args.only) else 1
    if not RM.tool().exists():
        print(f"no {RM.tool()}: agps navmesh build-tool first")
        return 1
    cd = _client(args)
    meshes = {}
    # (--only: only those built; the others already in data/navmesh/ are exported as they are)
    for name, cont, level, triangles in RM.sources():
        p = RM.mesh_path(name)
        if not args.only or any(o.lower() in name.lower() for o in args.only):
            if args.rebuild or not p.exists():
                T, _box, walk = triangles(cd, print)
                RM.save(RM.run_recast(T, walk=walk), p)
        if p.exists():
            meshes[name] = (cont, RM.load(p), level)
    out = DATA / "navmesh" / "NavMeshData.lua"
    RM.export_lua(meshes, out)
    dev = _dev_addon()
    if dev and dev.is_dir():
        shutil.copyfile(out, dev / "NavMeshData.lua")
        print(f"copied to {dev / 'NavMeshData.lua'} (agps install-addon --dev puts it in the game)")
    return 0


def cmd_capitals(args) -> int:
    """Capital cities at ground level: build them, render each (data/debug/capitals/) with
    summary.txt, and with --write, Data/Capitals.lua."""
    from .capitals import build_all, capitals_lua, render_debug

    cd = _client(args)
    out = DATA / "debug" / "capitals"
    logs: list = []

    def log(s):
        print(s)
        logs.append(s)

    built = build_all(cd, DATA, log=log, only=args.only)
    for u in built:
        render_debug(u, out)
    out.mkdir(parents=True, exist_ok=True)
    if args.write:
        if args.only:
            print("--write builds every capital: run it without --only")
            return 1
        p = ADDON_DIR / "Data" / "Capitals.lua"
        p.write_text(capitals_lua(cd, log=log, built=built), encoding="utf-8", newline="\n")
        print(f"wrote {p} ({p.stat().st_size // 1024} KB)")
        from .hpa import refresh

        refresh()  # (the terrain's blocks are made with the capitals' grids over it: Data/TerrainHPA.lua, #715)
    if args.check:  # (the routes over Data/Capitals.lua as it is: --write first after a change)
        from .capitals import check_routes

        log("-- routes from outside each gate to the places (the addon's routing, 3D walk over the floors):")
        check_routes(built, log=log)
    if args.roads3d:
        from .capitals import check_roads_3d

        rows = check_roads_3d(built)
        (out / "roads3d.txt").write_text("\n".join(rows) + "\n", encoding="utf-8")
        log(f"-- every road in 3D: {sum(1 for r in rows if r.startswith('!'))} flagged; {out / 'roads3d.txt'}")
    (out / "summary.txt").write_text("\n".join(logs) + "\n", encoding="utf-8")
    print(f"{len(built)} capitals built; renders and summary.txt in {out}")
    return 0


def cmd_instances(args) -> int:
    """Dungeons and raids: build them, render each (data/debug/instances/) with summary.txt
    (covered and skipped), with --write Data/Instances.lua, with --check the routes from the
    entrance to every boss walked in 3D."""
    from .instances import build_all, check_routes, instances_lua, render_debug

    cd = _client(args)
    out = DATA / "debug" / "instances"
    logs: list = []

    def log(s):
        print(s)
        logs.append(s)

    report: list = []
    built = build_all(cd, DATA, log=log, only=args.only, report=report)
    for inst, u in built:
        render_debug(inst, u, out)
    text = instances_lua(cd, built, log=log) if (args.write or args.check) else None
    if args.write:
        if args.only:
            print("--write builds every instance: run it without --only")
            return 1
        p = ADDON_DIR / "Data" / "Instances.lua"
        p.write_text(text, encoding="utf-8", newline="\n")
        print(f"wrote {p} ({p.stat().st_size // 1024} KB)")
    if args.check:  # (the routes over the data just built)
        log("-- routes from the entrance to each boss (the addon's routing, 3D walk over the floors):")
        check_routes(built, log=log, text=text)
    if args.roads3d:
        from .instances import check_roads_3d

        out.mkdir(parents=True, exist_ok=True)
        rows = check_roads_3d(built)
        (out / "roads3d.txt").write_text("\n".join(rows) + "\n", encoding="utf-8")
        flagged = [r for r in rows if r.startswith("!")]
        log(f"-- every road in 3D: {len(flagged)} flagged of {len(rows)}; {out / 'roads3d.txt'}")
        by = {}
        for r in flagged:
            name = r[2:].split(": road")[0]
            by[name] = by.get(name, 0) + 1
        for name, n in sorted(by.items(), key=lambda kv: -kv[1]):
            log(f"  {n:5d} {name}")
    lines = [f"{status:8s} {inst.name} ({inst.map_id}{', raid' if inst.raid else ''}): {why}"
             for inst, status, why in sorted(report, key=lambda r: (r[1], r[0].raid, r[0].map_id))]
    out.mkdir(parents=True, exist_ok=True)
    (out / "summary.txt").write_text("\n".join(lines + ["", "-- log:"] + logs) + "\n", encoding="utf-8")
    print(f"{len(built)} instances built, {len(report) - len(built)} skipped; renders and summary.txt in {out}")
    return 0


def cmd_rxp_floors(args) -> int:
    """RestedXP's and Zygor's guide waypoints over stacked floors and their NPCs' heights (Data/GuideFloors.lua)."""
    from .paths import data_dir
    from .rxpfloors import FILE, build, lua_text, rxp_version, zygor_version

    rxp, zyg = Path(args.rxp), Path(args.zygor)
    entries, rep = build(rxp, data_dir(), zyg)
    print(f"{rep['steps']} steps, {rep['spots']} waypoints; {rep['stacked']} over stacked floors, {rep['heights']} with "
          f"their NPC's height, {len(rep['untold'])} without (no NPC named, or none near)")
    if args.write:
        FILE.write_text(lua_text(entries, rxp_version(rxp), zygor_version(zyg)), encoding="utf-8", newline="\n")
        print(f"wrote {FILE}")
    return 0


def cmd_npc_floors(args) -> int:
    """The heights of every NPC spawn in the capitals, down in Undercity and in the caves (Data/NpcFloors.lua)."""
    from .npcfloors import FILE, build, lua_text
    from .paths import data_dir

    entries, rep = build(data_dir())
    print(f"{len(entries)} NPC spots: {rep['capital']} in the capitals, {rep['undercity']} down in Undercity, "
          f"{rep['cave']} in caves ({rep['same']} more at the same spot left out)")
    if args.write:
        FILE.write_text(lua_text(entries), encoding="utf-8", newline="\n")
        print(f"wrote {FILE} ({FILE.stat().st_size // 1024} KB)")
    return 0


def cmd_interior_floors(args) -> int:
    """The floors' heights in the buildings' inside maps (Data/InteriorFloors.lua) from the models, checked and filled
    with the NPCs' spots; the rooms neither settles go to the floor height survey's list."""
    from . import interiorfloors as F

    cd = _client(args)
    doc = F.build(cd, DATA)
    r = doc["report"]
    print(f"{r['models']} models, {r['rooms']} rooms: {r['rooms_with_floors']} with floors; {r['floors_model']} floors "
          f"from the models, {r['floors_npc']} from NPCs, {r['floors_survey']} surveyed; {r['npc_confirmed']} confirmed "
          f"by NPCs; {r['todo']} rooms to survey")
    if args.write:
        F.FILE.write_text(F.lua_text(doc["floors"]), encoding="utf-8", newline="\n")
        F.write_todo(doc["todo"])
        print(f"wrote {F.FILE} and {F.FILE_TODO}")
    return 0


def _survey_dirs(args) -> list:
    dirs = [Path(args.wow_path) / args.flavor / "Interface" / "AddOns"] + extra_addons_dirs()
    return [d for d in dirs if d.is_dir()]


def cmd_floor_survey(args) -> int:
    """The floor height survey: `export` writes the rooms still to measure into the survey addon's folder (any addon
    whose .toc lists FloorSurvey.lua); `watch` opens the window that checks and keeps each height as it's measured
    (floorsurvey.py); `import` takes the heights measured (the window's file, then the addon's SavedVariables) into
    the floor data (overrides/interior_floors.json, Data/InteriorFloors.lua) and off the list."""
    from . import interiorfloors as F

    dirs = _survey_dirs(args)
    if args.action == "watch":
        from . import floorsurvey as W
        return W.run_window()
    if args.action == "export":
        n = F.export_survey(dirs)
        print(f"{len(F.load_todo())} rooms to measure; {n} survey addon(s) found")
        return 0 if n else 1
    from .floorsurvey import CAPTURES
    doc = F.read_survey(dirs, CAPTURES)
    if not doc["rooms"]:
        print("nothing measured yet")
        return 0
    tmp = DATA / "debug" / "floor_survey.json"
    tmp.parent.mkdir(parents=True, exist_ok=True)
    tmp.write_text(json.dumps(doc, indent=1), encoding="utf-8")
    n = F.import_survey(tmp)
    over = F.load_overrides()
    wmos, _places = F.shipped_interiors()
    text = F.FILE.read_text(encoding="utf-8")
    F.FILE.write_text(F.patch_lua(text, over, {f: len(r) for f, r in wmos.items()}), encoding="utf-8", newline="\n")
    todo = [e for e in F.load_todo() if tuple(int(v) for v in e["id"].split(":")) not in over]
    F.write_todo(todo)
    F.export_survey(dirs, todo)
    print(f"{n} rooms measured taken in ({F.OVERRIDES}); {len(todo)} left to measure")
    return 0


def cmd_npc_spots(args) -> int:
    """NPC spots marked in game (a JSON list of marks: npcspots.py) into overrides/npc_spots.json, and the overrides
    into Data/Npcs.lua (only the spawns marked change; the dump isn't needed)."""
    import json

    from . import npcspots

    path = Path(args.overrides) if args.overrides else npcspots.FILE
    lua = Path(args.npcs_lua) if args.npcs_lua else npcspots.NPCS_LUA
    if args.import_file:
        marks = json.loads(Path(args.import_file).read_text(encoding="utf-8"))
        marks = marks.get("marks", []) if isinstance(marks, dict) else marks
        if args.write:
            new = npcspots.merge_marks(marks, path)
        else:  # (what it would take in)
            have = npcspots.times(path)
            new = [g for g in map(npcspots.spot_of, marks) if g and g[1]["time"] not in have]
        print(f"{len(new)} new NPC spot(s) of {len(marks)} mark(s)")
        doc = npcspots.load(path)
        if not args.write:  # (as it would be)
            for nid, s in new:
                doc["npcs"].setdefault(str(nid), []).append(s)
    else:
        doc = npcspots.load(path)
        new = []
    text, applied = npcspots.patch_lua(lua.read_text(encoding="utf-8"), doc, log=print)
    for nid, done in sorted(applied.items()):
        for s, moved in done:
            how = "added as a spawn" if moved is None else f"moved {moved:.1f} yd"
            print(f"  {nid} {s['name'] or '?'} ({s['zone'] or '?'}, {'live' if s.get('live') else 'other client'}, "
                  f"time {s['time']}): {s['x']:.1f}, {s['y']:.1f} on level {s['level']}, {how}")
    if args.write:
        lua.write_text(text, encoding="utf-8", newline="\n")
        print(f"wrote {lua}")
    else:
        print("(nothing written: --write)")
    return 0


def cmd_npcs(args) -> int:
    """Every friendly NPC, for the search (Data/Npcs.lua)."""
    from .npcs import FILE, build, lua_text
    from .paths import data_dir

    from . import npcspots

    npcs, rep = build(data_dir())
    spawns = sum(len(n["spawns"]) for n in npcs.values())
    print(f"{len(npcs)} NPCs, {spawns} spawns; left out: " +
          ", ".join(f"{v} {k}" for k, v in sorted(rep.items()) if k != "kept"))
    fixed = npcspots.apply(npcs, npcspots.load(), log=print)  # (the spots marked in game: overrides/npc_spots.json)
    if fixed:
        print(f"{sum(len(v) for v in fixed.values())} spot(s) of {len(fixed)} NPC(s) from overrides/npc_spots.json")
    if args.write:
        FILE.write_text(lua_text(npcs), encoding="utf-8", newline="\n")
        print(f"wrote {FILE} ({FILE.stat().st_size // 1024} KB)")
    return 0


def cmd_npc_names(args) -> int:
    """The shipped NPCs' names in each client language (Data/NpcNames/<locale>.lua, from AzerothCore)."""
    from .npc_names import LOCALES, OUT_DIR, build, lua_text
    from .paths import data_dir

    names, rep = build(data_dir())
    print(", ".join(f"{v} {k}" for k, v in rep.items()))
    total = 0
    for loc in LOCALES:
        text = lua_text(loc, names[loc])
        size = len(text.encode("utf-8"))
        total += size
        print(f"  {loc}: {len(names[loc])} NPCs, {size // 1024} KB")
        if args.write:
            OUT_DIR.mkdir(parents=True, exist_ok=True)
            (OUT_DIR / f"{loc}.lua").write_text(text, encoding="utf-8", newline="\n")
    print(f"  {total // 1024} KB in all" + ("" if args.write else " (nothing written: --write)"))
    return 0


def cmd_place_names(args) -> int:
    """The shipped places' names in each client language (Data/PlaceNames/<locale>.lua, from WMOAreaTable and
    AreaTable)."""
    from .paths import data_dir
    from .place_names import LOCALES, OUT_DIR, build, lua_text

    names, rep = build(data_dir())
    print(", ".join(f"{len(v) if isinstance(v, list) else v} {k}" for k, v in rep.items()), rep["not found"] or "")
    total = 0
    for loc in LOCALES:
        text = lua_text(loc, names[loc])
        size = len(text.encode("utf-8"))
        total += size
        print(f"  {loc}: {len(names[loc])} places, {size // 1024} KB")
        if args.write:
            OUT_DIR.mkdir(parents=True, exist_ok=True)
            (OUT_DIR / f"{loc}.lua").write_text(text, encoding="utf-8", newline="\n")
    print(f"  {total // 1024} KB in all" + ("" if args.write else " (nothing written: --write)"))
    return 0


def cmd_vendors(args) -> int:
    """What each shipped vendor sells, for the search (Data/VendorItems.lua)."""
    from .paths import data_dir
    from .vendors import FILE, build, lua_text

    items, sells = build(data_dir())
    print(f"{len(sells)} vendors, {len(items)} items, {sum(len(s) for s in sells.values())} sold")
    if args.write:
        FILE.write_text(lua_text(items, sells), encoding="utf-8", newline="\n")
        print(f"wrote {FILE} ({FILE.stat().st_size // 1024} KB)")
    return 0


def cmd_terrain_hpa(args) -> int:
    from .hpa import write

    print(f"wrote {write()}")
    return 0


def cmd_city_places(args) -> int:
    """Heights of the capitals' service locations (Data/CityPlaces.lua) from their NPCs' spawns."""
    from .cityplaces import FILE, map_bounds, npc_spawns, with_heights
    from .paths import data_dir

    maps = map_bounds()
    spawns = npc_spawns(data_dir())
    text = FILE.read_text(encoding="utf-8")
    if args.add:
        from .cityplaces import with_made

        text, done = with_made(text, maps, spawns)
        print("made from their NPCs: " + ", ".join(done))
    text, n, missing = with_heights(text, maps, spawns)
    if args.towns:
        from .townplaces import town_places, with_towns

        towns = town_places(data_dir(), spawns)
        from .townplaces import floors

        print(f"{floors(_client(args), towns)} town places off the ground floor (upstairs or in a cellar)")
        text = with_towns(text, towns)
        print("towns: " + ", ".join(f"{t['town']} {len(t['places'])}" for t in towns.values()))
    FILE.write_text(text, encoding="utf-8", newline="\n")
    print(f"{n} places with their NPC's height; none found for {len(missing)}: {', '.join(missing)}")
    return 0


# More AddOns folders every install also goes into, one per line (a second install of the game, a private
# test server's): in the user's home folder, so the paths stay out of the repo.
EXTRA_INSTALLS = Path.home() / ".agps-installs"


def extra_addons_dirs() -> list:
    """The AddOns folders listed in EXTRA_INSTALLS (blank lines and "#" comments skipped)."""
    if not EXTRA_INSTALLS.is_file():
        return []
    out = []
    for line in EXTRA_INSTALLS.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            out.append(Path(line))
    return out


def cmd_install_addon(args) -> int:
    from .hpa import refresh

    addons = Path(args.wow_path) / args.flavor / "Interface" / "AddOns"
    if not addons.is_dir():
        print(f"no AddOns folder at {addons}")
        return 1
    refresh()  # (the terrain's blocks, when the terrain or the shipped walls changed: Data/TerrainHPA.lua)
    rc = _install_into(addons, getattr(args, "dev", False))
    for extra in extra_addons_dirs():
        if extra.is_dir() and extra.resolve() != addons.resolve():
            rc = _install_into(extra, getattr(args, "dev", False)) or rc
        elif not extra.is_dir():
            print(f"no AddOns folder at {extra} (listed in {EXTRA_INSTALLS})")
    return rc


def _install_into(addons: Path, dev: bool) -> int:
    import shutil

    dst = addons / "AzerothGPS"
    # Copy over the installed addon, then remove files the addon no longer has (a clean copy
    # without deleting everything first: a file another program has open can't stop halfway
    # and leave the folder half empty).
    shutil.copytree(ADDON_DIR, dst, dirs_exist_ok=True)
    keep = {p.relative_to(ADDON_DIR) for p in ADDON_DIR.rglob("*")}
    for p in sorted(dst.rglob("*"), reverse=True):
        if p.relative_to(dst) not in keep:
            try:
                p.unlink() if p.is_file() else p.rmdir()
            except OSError as e:
                print(f"couldn't remove stale {p}: {e}")
    old = dst.parent / "AzerothGPS_Link"
    if old.is_dir():
        shutil.rmtree(old)  # replaced by AzerothGPS
        print(f"removed old {old}")
    print(f"copied addon to {dst} -- /reload in game to pick up changes")
    try:  # (the floor height survey's list, where an addon there takes it: kept up to date with every install)
        from .interiorfloors import export_survey
        export_survey([addons])
    except Exception as e:  # (never fails an install)
        print(f"floor survey list not written: {e}")
    if dev:
        # the developer tools (a checkout next to this repo, _dev_addon()): never shipped
        src = _dev_addon()
        if not src or not src.is_dir():
            print(f"no developer addon {'at ' + str(src) if src else 'configured (app/azerothgps/private_paths.py)'}")
            return 1
        ddst = dst.parent / src.name
        if ddst.is_dir():
            shutil.rmtree(ddst)
        shutil.copytree(src, ddst)
        print(f"copied dev tools to {ddst} (new files: log out and back in, or restart WoW, the first time)")
    return 0


def cmd_probes(args) -> int:
    from .savedvars.parser import load_savedvariables

    base = wtf_account_dir(Path(args.wow_path), args.flavor)
    files = sorted(base.glob("*/SavedVariables/AzerothGPS.lua"))
    if not files:
        print(f"no AzerothGPS.lua under {base} (/reload once after installing the addon)")
        return 1
    for f in files:
        db = load_savedvariables(f).get("AzerothGPSDB", {})
        print(f"== {f}")
        probes = db.get("probes") or []  # an empty Lua table parses as {}
        for p in probes[-args.last:]:
            print(f"-- {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(p.get('time', 0)))} ({p.get('reason')})")
            for r in p.get("results", []):
                print(f"   {r.get('name')} = {r.get('value')}")
    return 0


def cmd_perf(args) -> int:
    """Print the /agps debug perf snapshots saved in SavedVariables (newest last)."""
    from .savedvars.parser import load_savedvariables

    base = wtf_account_dir(Path(args.wow_path), args.flavor)
    files = sorted(base.glob("*/SavedVariables/AzerothGPS.lua"))
    if not files:
        print(f"no AzerothGPS.lua under {base} (/reload once after installing the addon)")
        return 1
    for f in files:
        snaps = load_savedvariables(f).get("AzerothGPSDB", {}).get("perf") or []
        if isinstance(snaps, dict):  # an empty Lua table parses as {}
            snaps = list(snaps.values())
        print(f"== {f}")
        if not snaps:
            print("   no snapshots: run /agps debug perf in game, then /reload")
        for snap in snaps[-args.last:]:
            span = snap.get("span") or 1
            when = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(snap.get("time", 0)))
            print(f"-- {when}: {span:.0f} s measured, {snap.get('fps', 0):.0f} fps, version {snap.get('version')}")
            print(f"   settings: {snap.get('settings')}")
            rows = snap.get("rows") or []
            if isinstance(rows, dict):
                rows = list(rows.values())
            print(f"   {'part':40} {'ms/s':>7} {'avg ms':>7} {'max ms':>7} {'runs/s':>7} {'>16ms':>6}")
            for r in sorted(rows, key=lambda r: r.get("name", "")):
                n = r.get("n") or 1
                print(f"   {r.get('name', '?'):40} {r.get('total', 0) / span:7.2f} {r.get('total', 0) / n:7.2f}"
                      f" {r.get('max', 0):7.1f} {n / span:7.1f} {r.get('slow', 0):6d}")
    return 0


def cmd_import_shared(args) -> int:
    """Roads players copied from the share page (a text file of them) into the road data."""
    from .extract.pipeline import CONTINENTS
    from .paths import RESOURCES
    from .roads.build import reapply_overrides
    from .roads.export import write_roads_lua
    from .roads.tracks import import_shared

    per: dict = {}
    if args.github:
        # (the open "road data" issues: their bodies hold the pasted text)
        import subprocess

        out = subprocess.run(["gh", "issue", "list", "-R", args.repo, "-l", "road data", "--state", "open",
                              "--limit", "200", "--json", "number,body"], capture_output=True, text=True, check=True)
        issues = json.loads(out.stdout or "[]")
        text = "\n".join(i.get("body") or "" for i in issues)
        print(f"{len(issues)} open road data issue(s) in {args.repo}")
    elif args.file:
        text = Path(args.file).read_text(encoding="utf-8")
    else:
        print("give a file, or --github")
        return 1
    n = import_shared(text, RESOURCES / "overrides", per)
    print(f"{n} new road(s): {per}")
    from .instances import merge_entrances, parse_shared_entrances

    ne = merge_entrances(parse_shared_entrances(text))
    if ne:
        print(f"{ne} new dungeon way(s) in: agps instances --write to put them in the data")
    from .pins import parse_shared_pins

    added, removed = parse_shared_pins(text)
    if added or removed:  # (never in the data: the players' to discover and share, asked 2026-10-06)
        print(f"{len(added) + len(removed)} pin line(s) left out: pins stay the players', never in the data")
    from .sharedtrips import merge_trips, parse_shared_trips

    ntrips = merge_trips(parse_shared_trips(text))
    if ntrips:
        print(f"{ntrips} new faster trip(s) (routes): in data/feedback/shared_trips.json")
    if n:
        reapply_overrides(DATA, [c for c in per if c in CONTINENTS])
        write_roads_lua(DATA, ADDON_DIR)
        print("in the road data (city levels: run agps gen-addon-data for Cities.lua)")
    return 0


def cmd_entrances(args) -> int:
    """Dungeons' ways in the addon learned in game (SavedVariables) into
    overrides/instance_entrances.json."""
    from .instances import merge_entrances, saved_entrances
    from .savedvars.parser import load_savedvariables

    base = wtf_account_dir(Path(args.wow_path), args.flavor)
    n = 0
    for f in sorted(base.glob("*/SavedVariables/AzerothGPS.lua")):
        n += merge_entrances(saved_entrances(load_savedvariables(f)))
    print(f"{n} new dungeon way(s) in" + (": agps instances --write to put them in the data" if n else ""))
    return 0


def cmd_feedback(args) -> int:
    """Export the opt-in feedback (shared roads, faster trips) to a JSON file for upload."""
    from .savedvars.packed import unpacked
    from .savedvars.parser import load_savedvariables

    base = wtf_account_dir(Path(args.wow_path), args.flavor)
    roads, trips = [], []
    for f in sorted(base.glob("*/SavedVariables/AzerothGPS.lua")):
        fb = load_savedvariables(f).get("AzerothGPSDB", {}).get("feedback") or {}
        as_list = lambda v: [unpacked(r) for r in (v if isinstance(v, list) else list((v or {}).values()))]
        roads += as_list(fb.get("roads"))
        trips += as_list(fb.get("trips"))
    if not roads and not trips:
        print("no feedback saved (turn on the sharing options in game, then /reload)")
        return 1
    out = DATA / "feedback" / time.strftime("feedback-%Y%m%d-%H%M%S.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"format": 1, "roads": roads, "trips": trips}, indent=1), encoding="utf-8")
    print(f"wrote {out}: {len(roads)} roads, {len(trips)} trips (uploading comes later)")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="agps", description=__doc__.splitlines()[0])
    sub = p.add_subparsers(dest="cmd", required=True)

    def client_args(sp):
        sp.add_argument("--wow-path", default=str(DEFAULT_WOW))
        sp.add_argument("--product", default=PRODUCT, help="product code in .build.info")

    sp = sub.add_parser("route-check", help="run the addon's routing on random trips per zone; flag bad routes")
    sp.add_argument("--samples", type=int, default=20, help="trips per zone")
    sp.add_argument("--seed", type=int, default=1)
    sp.add_argument("--zone", help="only zones whose name contains this")
    sp.add_argument("--mode", choices=("offroad", "road", "both"), default="offroad",
                    help="route with offroad shortcuts, along the roads, or both")
    sp.add_argument("--faction", choices=("A", "H"), help="as an Alliance or Horde character: the other's guards weighed")
    sp.add_argument("--name", help="the report in data/debug/route-check-<name>/ (runs side by side)")
    sp.set_defaults(fn=cmd_route_check)

    sp = sub.add_parser("entrances", help="dungeons' ways in the addon learned in game into overrides/")
    sp.add_argument("--wow-path", default=str(DEFAULT_WOW))
    sp.add_argument("--flavor", default=DEFAULT_FLAVOR)
    sp.set_defaults(fn=cmd_entrances)

    sp = sub.add_parser("route-sweep", help="random trips in random zones, routed as in game: snapbacks, U-turns, spikes")
    sp.add_argument("--trips", type=int, default=60)
    sp.add_argument("--minutes", type=float, help="run for this long instead (as many trips as fit)")
    sp.add_argument("--seed", type=int, help="(random when left out)")
    sp.add_argument("--zone", help="only zones whose name contains this")
    sp.set_defaults(fn=cmd_route_sweep)

    sp = sub.add_parser("route-quality", help="the routes the whole addon chooses on random trips, weighed, against an older "
                                              "version (a git ref): better, worse, a way found or lost")
    sp.add_argument("--trips", type=int, default=200)
    sp.add_argument("--seed", type=int, default=21)
    sp.add_argument("--against", default="HEAD", help="the git ref to compare with (default HEAD: the uncommitted changes)")
    sp.add_argument("--jobs", type=int, default=3, help="processes, each a share of the trips (CI's 3: keep it so a run here matches CI's)")
    sp.set_defaults(fn=cmd_route_quality)

    sp = sub.add_parser("trip-sweep", help="random trips planned and followed as in game: flights, levels, detours, frame budget")
    sp.add_argument("--trips", type=int, default=20)
    sp.add_argument("--minutes", type=float, help="run for this long instead (as many trips as fit)")
    sp.add_argument("--seed", type=int, help="(random when left out)")
    sp.add_argument("--replay", help="an earlier report.json: its flagged trips run again (into replay.json)")
    sp.set_defaults(fn=cmd_trip_sweep)

    sp = sub.add_parser("gen-addon-data", help="write addon/AzerothGPS/Data/*.lua from the client")
    client_args(sp)
    sp.set_defaults(fn=cmd_gen_addon_data)

    sp = sub.add_parser("transit", help="maps you pass through (the Deeprun Tram): their art (--write: Data/Transit.lua)")
    client_args(sp)
    sp.add_argument("--write", action="store_true", help="write Data/Transit.lua")
    sp.set_defaults(fn=cmd_transit)

    sp = sub.add_parser("media", help="the addon's own art from assets/: the logo's round portrait in sizes (Media/)")
    sp.set_defaults(fn=cmd_media)

    sp = sub.add_parser("setup-art", help="the first-run setup's card pictures from the screenshots (Media/Setup/)")
    sp.add_argument("--src", default=str(Path.home() / "Downloads"), help="the folder with the screenshots")
    sp.add_argument("--preview", metavar="DIR", help="also the pictures as PNGs to look at, in DIR")
    sp.set_defaults(fn=cmd_setup_art)

    sp = sub.add_parser("padicons", help="the controller's button icons and Options > Controller's diagram (Media/Pad/)")
    sp.add_argument("--preview", metavar="DIR", help="also pictures of them to look at, in DIR")
    sp.set_defaults(fn=cmd_padicons)

    sp = sub.add_parser("toolicons", help="the road and wall tools' legend icons (mouse buttons, Shift, Ctrl), the map's stairs glyph and Search Places' pin (Media/Tools/)")
    sp.add_argument("--preview", metavar="DIR", help="also pictures of them to look at, in DIR")
    sp.set_defaults(fn=cmd_toolicons)

    sp = sub.add_parser("keyicons", help="the controller's on-screen keyboard's key caps (Media/Keyboard/)")
    sp.add_argument("--preview", metavar="DIR", help="also pictures of them to look at, in DIR")
    sp.set_defaults(fn=cmd_keyicons)

    sp = sub.add_parser("buildings", help="buildings as ground routes don't walk through (Data/Buildings.lua)")
    client_args(sp)
    sp.add_argument("--write", action="store_true", help="write Data/Buildings.lua")
    sp.add_argument("--render", nargs=3, type=float, metavar=("X", "Y", "R"),
                    help="a picture of the buildings R yards around world X, Y (data/debug/buildings/)")
    sp.add_argument("--cont", type=int, default=0, help="the continent for --render")
    sp.set_defaults(fn=cmd_buildings)

    sp = sub.add_parser("bridges", help="the continents' bridges' outlines for the directions (Data/Bridges.lua)")
    client_args(sp)
    sp.add_argument("--write", action="store_true", help="write Data/Bridges.lua")
    sp.set_defaults(fn=cmd_bridges)

    sp = sub.add_parser("heights", help="the ground's height per map tile for the road and wall tools (Data/Heights.lua)")
    client_args(sp)
    sp.add_argument("--write", action="store_true", help="write Data/Heights.lua")
    sp.add_argument("--step", type=int, choices=(2, 4), help="the grid: every 2 (8 yd) or 4 (16 yd) of a tile's 128 quads")
    sp.set_defaults(fn=cmd_heights)

    sp = sub.add_parser("coast", help="the seamless map's coastline masks (Data/Coast.lua, Media/Coast/)")
    sp.add_argument("--write", action="store_true", help="write Data/Coast.lua and Media/Coast/*.tga")
    sp.add_argument("--render", nargs=3, type=float, metavar=("X", "Y", "R"),
                    help="a picture of the masks R yards around world X, Y (data/debug/coast/)")
    sp.add_argument("--cont", type=int, default=0, help="the continent for --render")
    sp.add_argument("--buttons", action="store_true",
                    help="write only the map buttons' art drawn at each size (Media/Buttons/*.tga)")
    sp.set_defaults(fn=cmd_coast)

    sp = sub.add_parser("isle-mask", help="the seamless map's isles' land masks (Atlas/Media/Textures/MapIsle/)")
    client_args(sp)
    sp.add_argument("--write", action="store_true", help="write the masks")
    sp.set_defaults(fn=cmd_isle_mask)

    sp = sub.add_parser("doodads", help="the doodads a character bumps into near a spot (trees, planters, stalls)")
    client_args(sp)
    sp.add_argument("x", type=float)
    sp.add_argument("y", type=float)
    sp.add_argument("r", type=float, nargs="?", default=25.0, help="yards around the spot (25)")
    sp.add_argument("--cont", type=int, default=0, help="the continent (0, 1, ...)")
    sp.add_argument("--render", action="store_true", help="a picture of them (data/debug/doodads/)")
    sp.add_argument("--z", type=float, help="--render: the models' walls cut over this floor height (a city's)")
    sp.add_argument("--route", help="--render: a route to draw, a JSON list of polylines [[[x, y], ...], ...]")
    sp.set_defaults(fn=cmd_doodads)

    sp = sub.add_parser("indoors", help="buildings' insides as roads with floors and stairs (Data/Indoors.lua)")
    client_args(sp)
    sp.add_argument("--write", action="store_true", help="write Data/Indoors.lua")
    sp.add_argument("--town", action="append", help="only this town (indoors.TOWNS or TOWNS_NEXT); again for more")
    sp.add_argument("--check", action="store_true", help="route from outside to every town place inside (the game harness)")
    sp.add_argument("--npcs", action="store_true", help="only the buildings with an NPC upstairs or in a cellar (phase 6)")
    sp.set_defaults(fn=cmd_indoors)

    sp = sub.add_parser("floors", help="NPCs and quest objectives upstairs or under the ground: data/debug/floors/")
    client_args(sp)
    sp.set_defaults(fn=cmd_floors)

    sp = sub.add_parser("caves", help="build the caves' grids and roads; renders and a summary in data/debug/caves/")
    client_args(sp)
    sp.add_argument("--only", nargs="+", help="only caves whose name contains one of these (or with this placement id)")
    sp.add_argument("--write", action="store_true", help="also write Data/Caves.lua (gen-addon-data writes it too)")
    sp.set_defaults(fn=cmd_caves)

    sp = sub.add_parser("navmesh", help="the capitals' and Undercity's Recast meshes for the dev tools' route comparison "
                                        "(never shipped)")
    client_args(sp)
    sp.add_argument("what", choices=["build-tool", "build", "compare"],
                    help="build-tool: compile navbuild.exe; build: the meshes; compare: the roads against them "
                         "(data/debug/navcompare/)")
    sp.add_argument("--only", nargs="+", help="only build the cities whose name contains one of these (the others' "
                                              "meshes already built are kept in NavMeshData.lua)")
    sp.add_argument("--rebuild", action="store_true", help="build the meshes again (else the ones in data/navmesh/)")
    sp.set_defaults(fn=cmd_navmesh)
    sp = sub.add_parser("city-roads", help="a capital's roads without the spiderweb: straightened and thinned over its "
                                           "navmesh (data/navmesh/); report, pictures and flags in data/debug/cityroads/")
    sp.add_argument("--city", default="Orgrimmar", help="the city (cityroads.CITIES: Orgrimmar so far)")
    sp.add_argument("--write", action="store_true", help="patch that city's roads in Data/Capitals.lua")
    sp.add_argument("--check", action="store_true", help="also route in the city over the data as --against had it and "
                                                         "as it is: yards, turns, ways lost")
    sp.add_argument("--against", default="HEAD")
    sp.set_defaults(fn=cmd_city_roads)
    sp = sub.add_parser("capitals", help="build the capitals' grids and roads; renders in data/debug/capitals/")
    client_args(sp)
    sp.add_argument("--only", nargs="+", help="only capitals whose name contains one of these")
    sp.add_argument("--write", action="store_true", help="also write Data/Capitals.lua (gen-addon-data writes it too)")
    sp.add_argument("--check", action="store_true",
                    help="route from outside each gate to its places over the data and walk them in 3D")
    sp.add_argument("--roads3d", action="store_true",
                    help="walk every road of each capital in 3D: jumps between levels, stairs, drops (roads3d.txt)")
    sp.set_defaults(fn=cmd_capitals)

    sp = sub.add_parser("instances", help="build the dungeons' and raids' levels; renders in data/debug/instances/")
    client_args(sp)
    sp.add_argument("--only", nargs="+", help="only instances whose name contains one of these (or with this MapID)")
    sp.add_argument("--write", action="store_true", help="also write Data/Instances.lua (gen-addon-data writes it too)")
    sp.add_argument("--check", action="store_true",
                    help="route from each entrance to every boss over the data and walk the routes in 3D")
    sp.add_argument("--roads3d", action="store_true",
                    help="walk every road of each instance in 3D: jumps between levels, joins between floors (roads3d.txt)")
    sp.set_defaults(fn=cmd_instances)

    sp = sub.add_parser("dungeon-maps", help="dungeons' world maps from another WoW version where their layout "
                        "is WoW Forever's (renders in data/debug/dungeonmaps/)")
    client_args(sp)
    sp.add_argument("--source", default="wow", help="the other version's product code in .build.info (retail: wow)")
    sp.add_argument("--write", action="store_true",
                    help="write Data/DungeonMaps.lua, app/azerothgps/data/dungeon_maps.json, docs/dungeon-maps.md")
    sp.set_defaults(fn=cmd_dungeon_maps)

    sp = sub.add_parser("interior-maps", help="interiors' maps (caves, mines) from another WoW version where their "
                        "layout is WoW Forever's (renders in data/debug/interiormaps/)")
    client_args(sp)
    sp.add_argument("--source", default="wow", help="the other version's product code in .build.info (retail: wow)")
    sp.add_argument("--write", action="store_true",
                    help="write Data/InteriorMaps.lua, app/azerothgps/data/interior_maps.json, docs/interior-maps.md")
    sp.set_defaults(fn=cmd_interior_maps)

    sp = sub.add_parser("extract", help="extract map art, bounds, POIs, area grid (+ roads) into data/")
    client_args(sp)
    sp.add_argument("--skip-roads", action="store_true", help="skip the (slower) road network build")
    sp.set_defaults(fn=cmd_extract)

    sp = sub.add_parser("roads", help="rebuild road networks (after editing overrides/)")
    client_args(sp)
    sp.add_argument("--continents", type=int, nargs="+", default=None, help="map IDs (default: all: 0 Eastern Kingdoms, 1 Kalimdor, 2991 Zephras Isle)")
    sp.set_defaults(fn=cmd_roads)

    sp = sub.add_parser("import-shared", help="roads, walls and pins players copied from the share page into the data")
    sp.add_argument("file", nargs="?", help="a text file of it")
    sp.add_argument("--github", action="store_true", help="from the open 'road data' GitHub issues instead")
    sp.add_argument("--repo", default="AzerothGPS/AzerothGPS")
    sp.set_defaults(fn=cmd_import_shared)

    sp = sub.add_parser("npc-paths", help="NPC travel paths (data/thirdparty) into overrides/paths_<map>.geojson")
    sp.set_defaults(fn=cmd_npc_paths)

    sp = sub.add_parser("watch-roads", help="on every /reload: roads drawn in game go into the road data")
    client_args(sp)
    sp.add_argument("--flavor", default=DEFAULT_FLAVOR)
    sp.add_argument("--interval", type=float, default=3.0, help="seconds between checks")
    sp.add_argument("--once", action="store_true", help="check once and stop")
    sp.add_argument("--no-install", action="store_true",
                    help="into the road data only, the addon not installed (a release build being tested in game)")
    sp.add_argument("--also-wtf", action="append", metavar="ACCOUNT_DIR",
                    help="also watch this WTF/Account folder (a test client's saved files, copied here): "
                         "its recorded walks only")
    sp.add_argument("--also-since", metavar="'YYYY-MM-DD HH:MM'", help="--also-wtf: walks recorded since then only")
    sp.add_argument("--own-wtf", action="append", metavar="ACCOUNT_DIR",
                    help="also watch this WTF/Account folder, all of its road and wall edits counting (a client the "
                         "user plays on themselves); never its dungeons' ways in")
    sp.add_argument("--wtf", metavar="ACCOUNT_DIR", help="read this WTF/Account folder instead of the game's (a snapshot)")
    sp.set_defaults(fn=cmd_watch_roads)

    sp = sub.add_parser("city-places", help="heights of the capitals' service locations (Data/CityPlaces.lua) from NPC spawns")
    client_args(sp)  # (--towns: the places' floors, from the terrain and the buildings)
    sp.add_argument("--add", action="store_true", help="also make the Alliance capitals' places from their NPCs")
    sp.add_argument("--towns", action="store_true", help="also the starting zones' towns' places (ns.TownPlaces)")
    sp.set_defaults(fn=cmd_city_places)

    sp = sub.add_parser("rxp-floors", help="RestedXP's and Zygor's guide waypoints over stacked floors, their heights (Data/GuideFloors.lua)")
    from .rxpfloors import DEFAULT_RXP, DEFAULT_ZYGOR
    sp.add_argument("--rxp", default=str(DEFAULT_RXP), help="the RXPGuides addon folder")
    sp.add_argument("--zygor", default=str(DEFAULT_ZYGOR), help="the ZygorGuidesViewerForever addon folder")
    sp.add_argument("--write", action="store_true")
    sp.set_defaults(fn=cmd_rxp_floors)

    sp = sub.add_parser("npc-floors", help="the heights of the NPCs' spots in the capitals and caves (Data/NpcFloors.lua)")
    sp.add_argument("--write", action="store_true")
    sp.set_defaults(fn=cmd_npc_floors)

    sp = sub.add_parser("interior-floors", help="the floors' heights in the buildings' inside maps (Data/InteriorFloors.lua)")
    client_args(sp)
    sp.add_argument("--write", action="store_true", help="write Data/InteriorFloors.lua and the survey's list")
    sp.set_defaults(fn=cmd_interior_floors)

    sp = sub.add_parser("floor-survey", help="the floor height survey's list out, the heights measured in")
    sp.add_argument("action", choices=("export", "import", "watch"))
    sp.add_argument("--wow-path", default=str(DEFAULT_WOW))
    sp.add_argument("--flavor", default=DEFAULT_FLAVOR)
    sp.set_defaults(fn=cmd_floor_survey)

    sp = sub.add_parser("npcs", help="every friendly NPC, for the search (Data/Npcs.lua)")
    sp.add_argument("--write", action="store_true")
    sp.set_defaults(fn=cmd_npcs)

    sp = sub.add_parser("npc-names", help="the shipped NPCs' names in each client language (Data/NpcNames/, AzerothCore)")
    sp.add_argument("--write", action="store_true")
    sp.set_defaults(fn=cmd_npc_names)

    sp = sub.add_parser("place-names", help="the shipped places' names in each client language (Data/PlaceNames/, "
                        "WMOAreaTable and AreaTable)")
    sp.add_argument("--write", action="store_true")
    sp.set_defaults(fn=cmd_place_names)

    sp = sub.add_parser("npc-spots", help="NPC spots marked in game into overrides/npc_spots.json and Data/Npcs.lua")
    sp.add_argument("--import", dest="import_file", metavar="MARKS_JSON",
                    help="marks to take in (a JSON list: id, name, level, cont, x, y, z, zone, time, client)")
    sp.add_argument("--write", action="store_true", help="write the overrides and Data/Npcs.lua")
    sp.add_argument("--overrides", help=argparse.SUPPRESS)
    sp.add_argument("--npcs-lua", help=argparse.SUPPRESS)
    sp.set_defaults(fn=cmd_npc_spots)

    sp = sub.add_parser("vendors", help="what each shipped vendor sells, for the search (Data/VendorItems.lua)")
    sp.add_argument("--write", action="store_true")
    sp.set_defaults(fn=cmd_vendors)

    sp = sub.add_parser("terrain-hpa", help="prepare the terrain's blocks for the walk search (Data/TerrainHPA.lua)")
    sp.set_defaults(fn=cmd_terrain_hpa)

    sp = sub.add_parser("install-addon", help="copy the addon into the WoW AddOns folder")
    sp.add_argument("--wow-path", default=str(DEFAULT_WOW))
    sp.add_argument("--flavor", default=DEFAULT_FLAVOR)
    sp.add_argument("--dev", action="store_true", help="also the developer addon, where one is checked out")
    sp.set_defaults(fn=cmd_install_addon)

    sp = sub.add_parser("probes", help="show /agps debug results from SavedVariables")
    sp.add_argument("--wow-path", default=str(DEFAULT_WOW))
    sp.add_argument("--flavor", default=DEFAULT_FLAVOR)
    sp.add_argument("--last", type=int, default=5)
    sp.set_defaults(fn=cmd_probes)

    sp = sub.add_parser("perf", help="show /agps debug perf timings saved in SavedVariables")
    sp.add_argument("--wow-path", default=str(DEFAULT_WOW))
    sp.add_argument("--flavor", default=DEFAULT_FLAVOR)
    sp.add_argument("--last", type=int, default=3)
    sp.set_defaults(fn=cmd_perf)

    sp = sub.add_parser("feedback", help="export shared roads and faster trips (opt-in) to data/feedback/")
    sp.add_argument("--wow-path", default=str(DEFAULT_WOW))
    sp.add_argument("--flavor", default=DEFAULT_FLAVOR)
    sp.set_defaults(fn=cmd_feedback)

    try:  # (the maintainers' sync with the community repo: only where its module is checked out)
        from . import community
    except ImportError:
        community = None
    if community is not None:
        community.add_parser(sub)

    args = p.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
