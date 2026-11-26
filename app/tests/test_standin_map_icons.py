"""WoW Forever's stand-in NPCs (overrides/standin_npcs.json, Layers' `n.standin`) on the map as the shipped ones are: in a
hovered building's inside map, their service's icon (G.InteriorNpcs, POI kind 16). Kooki3z on 6195a75c: Riverglades'
stand-ins were in Search Places with no icon in their buildings. Their spots are Wowhead's map percentages and their
height the ground's there, so they're placed by x and y alone, a few yards' slack, on whichever floor the map shows."""

from test_addon_lua import env, load  # noqa: F401
from test_map_redraw import game  # noqa: F401
from test_world_map_host import SETUP

HARLAN = 257595  # (Barracks Master Harlan, Farholde's innkeeper, in its barracks)
HARLAN_AT = (-9182.7, -5024.8)
BILGERAT_BANK = (-8219.1, -5616.5)  # (Brakkit, Lizi Pinchwhistle and Mizzy, the bankers, over the building's cellar)


def _names(npcs):
    return {str(npcs[i].name): npcs[i] for i in range(1, len(npcs) + 1)}


def test_farholdes_innkeeper_and_bilgerats_bankers_have_their_icons(env):  # noqa: F811
    lua, ns = env
    load(lua, ns, "Data/Interiors.lua", "Data/Npcs.lua", "Layers.lua", "Pins.lua")
    G, I = ns.GPS, ns.Pins.NPC_ICONS
    _, by_id, _ = ns.Layers.ShippedNpcs()
    assert by_id[HARLAN].standin
    place, wmo, room = G.InteriorUnder(HARLAN_AT[0], HARLAN_AT[1], 0)
    got = _names(G.InteriorNpcs(place, wmo, room, 0))
    assert "Barracks Master Harlan" in got and got["Barracks Master Harlan"].icon == I.inn, list(got)
    # (the map shows the cellar, the lowest floor; the bankers stand on the floor over it, their height the ground's)
    place, wmo, room = G.InteriorUnder(BILGERAT_BANK[0], BILGERAT_BANK[1], 0)
    got = _names(G.InteriorNpcs(place, wmo, room, 0))
    for name in ("Brakkit", "Lizi Pinchwhistle", "Mizzy"):
        assert name in got and got[name].icon == I.bank, list(got)


def test_every_stand_in_in_a_building_has_its_dot_there(env):  # noqa: F811
    lua, ns = env
    load(lua, ns, "Data/Interiors.lua", "Data/Npcs.lua", "Layers.lua", "Pins.lua")
    G = ns.GPS
    lst, _, _ = ns.Layers.ShippedNpcs()
    missing, checked = [], 0
    for i in range(1, len(lst) + 1):
        n = lst[i]
        if not (n.standin and any(c in str(n.svc or "") for c in str(G.NPC_DOT_SERVICES))):
            continue
        sp = n.spawns
        place, wmo, room = G.InteriorUnder(sp[2], sp[3], sp[1])
        if place is None:
            continue  # (standing out in the open: no inside map, as the shipped ones)
        checked += 1
        if str(n.name) not in _names(G.InteriorNpcs(place, wmo, room, sp[1])):
            missing.append(str(n.name))
    assert checked >= 30 and not missing, missing


def _dots(lua, ns):
    G = ns.GPS
    place, wmo, room = G.InteriorUnder(HARLAN_AT[0], HARLAN_AT[1], 0)
    G.hoverInside = lua.eval("function(p, w, r) return { p, w, r, cont = 0 } end")(place, wmo, room)
    G.hoverInsideKey = "standin-test"
    lua.execute("AGPS_T = AGPS_T + 6")
    G.Redraw()
    G.Update()
    return [w for w in lua.eval("AGPS_WIDGETS").values() if w._shown and w.npc and w.npc.id == HARLAN]


def test_farholdes_innkeeper_shows_on_the_gps_map_and_in_the_world_map(game):  # noqa: F811
    lua, ns = game
    G, st = ns.GPS, ns.settings.gps
    zoom = st.zoom
    was = {k: st[k] for k in ("useWorldMap", "shown", "minimized")}
    lua.execute("AGPS_POS_WAS = AGPS_POS")
    try:
        lua.execute(f"AGPS_POS = {{ {HARLAN_AT[0] + 40}, {HARLAN_AT[1] + 40}, 0 }}")
        st.zoom = 60.0
        G.Follow()
        b = _dots(lua, ns)
        assert b and b[0].stopTex == ns.Pins.NPC_ICONS.inn
        # (the GPS map in the game's world map: the same)
        lua.execute(SETUP)
        st.shown, st.minimized, st.useWorldMap = True, None, True
        G.ApplySettings()
        lua.execute("ToggleWorldMap()")
        assert G.WorldMapHosted()
        G.Follow()
        b = _dots(lua, ns)
        assert b and b[0].stopTex == ns.Pins.NPC_ICONS.inn
    finally:
        G.hoverInside, G.hoverInsideKey = None, None
        st.zoom = zoom
        lua.execute("if WorldMapFrame then WorldMapFrame:Hide() end ToggleWorldMap = nil AGPS_POS = AGPS_POS_WAS")
        for k, v in was.items():
            st[k] = v
        G.WorldMapChanged()
        G.ApplySettings()
        lua.execute("AGPS_T = AGPS_T + 6")
        G.Redraw()
