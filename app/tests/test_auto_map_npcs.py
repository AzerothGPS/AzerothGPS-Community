"""The NPCs in the maps drawn from their cells (1.4.2, Kooki3z 2026-11-27, a screenshot of Auberdine's inn: "for maps we
added, can we also add the NPCs inside as well like other buildings when mousing over?"): an auto map (item 115,
G.AutoArt) shows its NPCs as a building's inside map does (POI kind 16, G.AddInteriorNpcs: the service's icon or a
dot, the name and title on hover), each on its own floor: the floor shown, or every floor with the floor named.
Matched to the building by the map's own cells and its floors' heights (G.AutoMapNpcs), not by a list."""

from test_map_redraw import game  # noqa: F401

AUBERDINE_INN = "in292313"  # (Darkshore: two floors; the innkeeper downstairs, Wizbang's shop upstairs)
NIGHTHAVEN = "in301715"  # (Moonglade: two floors; Umber upstairs, Daeolyn Summerleaf and My'lanna downstairs)
ASTRANAAR_HALL = "in239624"  # (Astranaar, one floor: Dalria, Haljan Oakheart, Aayndia Floralwind and Xai'ander)


def _by_name(npcs):
    return {str(npcs[i].name): npcs[i] for i in range(1, len(npcs) + 1)}


def _buttons(lua, name):
    return [w for w in lua.eval("AGPS_WIDGETS").values()
            if w._shown and w.kind == 16 and w.name is not None and str(w.name) == name]


def test_each_npc_is_on_its_own_floor(game):  # noqa: F811
    lua, ns = game
    G = ns.GPS
    art = G.AutoArt(1, AUBERDINE_INN)
    assert art and str(art.name) == "Auberdine" and len(art.floors) == 2
    every = _by_name(G.AutoMapNpcs(art, None))
    for name in ("Innkeeper Shaussiy", "Laird", "Kyndri", "Allyndia"):
        assert name in every and every[name].floor == 1, (name, list(every))
    assert every["Wizbang Cranktoggle"].floor == 2
    assert "Barithras Moonshade" not in every  # (the hippogryph master, out by the inn: not on its cells)
    assert every["Innkeeper Shaussiy"].icon == ns.Pins.NPC_ICONS.inn
    assert str(every["Innkeeper Shaussiy"].floorName) == "Floor 2 of 2, from the top"
    assert str(every["Wizbang Cranktoggle"].floorName) == "Floor 1 of 2, from the top"
    low, high = _by_name(G.AutoMapNpcs(art, 1)), _by_name(G.AutoMapNpcs(art, 2))
    assert "Innkeeper Shaussiy" in low and "Wizbang Cranktoggle" not in low
    assert "Wizbang Cranktoggle" in high and "Innkeeper Shaussiy" not in high
    assert len(low) + len(high) == len(every)
    # (the inside maps' entry point gives the same: G.AddInteriorNpcs draws an auto map's through it)
    assert lua.eval("rawequal")(G.InteriorNpcs(art, None, 2, 1), G.AutoMapNpcs(art, 2))
    # (other buildings, by their own cells and floors)
    nh = _by_name(G.AutoMapNpcs(G.AutoArt(1, NIGHTHAVEN), None))
    assert nh["Umber"].floor == 2 and nh["Daeolyn Summerleaf"].floor == 1 and nh["My'lanna"].floor == 1
    hall = _by_name(G.AutoMapNpcs(G.AutoArt(1, ASTRANAAR_HALL), None))
    assert {"Dalria", "Haljan Oakheart", "Aayndia Floralwind", "Xai'ander"} <= set(hall)
    assert hall["Dalria"].floor == 1 and hall["Dalria"].floorName is None  # (one floor: none named)


def test_most_buildings_with_npcs_on_their_cells_list_them(game):  # noqa: F811
    lua, ns = game
    G = ns.GPS
    found = lua.eval("""function()
      local G, ns, n, maps = AGPS_NS.GPS, AGPS_NS, 0, 0
      for cont = 0, 1 do
        for _, r in ipairs(ns.AutoMaps[cont]) do
          local got = #G.AutoMapNpcs(G.AutoArt(cont, r[1]), nil)
          n = n + got
          if got > 0 then maps = maps + 1 end
        end
      end
      return n, maps
    end""")
    n, maps = found()
    assert n >= 60 and maps >= 15, (n, maps)


def test_the_map_shows_them_on_the_floor_shown_and_all_on_all_floors(game):  # noqa: F811
    lua, ns = game
    G = ns.GPS
    st = ns.settings.gps
    zoom = st.zoom
    art = G.AutoArt(1, AUBERDINE_INN)
    try:
        assert G.ShowCave(1, AUBERDINE_INN)
        lua.execute("AGPS_T = AGPS_T + 6")
        G.Update()
        assert G.shownView.cave is not None and str(G.shownView.cave.key) == AUBERDINE_INN
        assert G.shownView.floor == 0  # (all floors)
        inn, shop = _buttons(lua, "Innkeeper Shaussiy"), _buttons(lua, "Wizbang Cranktoggle")
        assert inn and shop
        assert inn[0].stopTex == ns.Pins.NPC_ICONS.inn and inn[0].npc and inn[0].npc.id
        assert "Floor 2 of 2, from the top" in str(inn[0].note)  # (the floor named on hover)
        assert "Floor 1 of 2, from the top" in str(shop[0].note)
        # (the top floor: the shop, not the innkeeper; then the ground floor: the other way round)
        assert G.FloorStep(False)
        lua.execute("AGPS_T = AGPS_T + 6")
        G.Update()
        assert G.shownView.floor == 1
        assert _buttons(lua, "Wizbang Cranktoggle") and not _buttons(lua, "Innkeeper Shaussiy")
        assert G.FloorStep(False)
        lua.execute("AGPS_T = AGPS_T + 6")
        G.Update()
        assert G.shownView.floor == 2
        assert _buttons(lua, "Innkeeper Shaussiy") and not _buttons(lua, "Wizbang Cranktoggle")
        assert len(G.AutoMapNpcs(art, 1)) >= 4
    finally:
        st.zoom = zoom
        G.Follow()
        lua.execute("AGPS_T = AGPS_T + 6")
        G.Update()
