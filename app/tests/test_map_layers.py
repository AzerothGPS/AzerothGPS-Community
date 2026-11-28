"""Map Layers and the map menu's name (1.4.2, Kooki3z 2026-11-27: "Make the Map Menu say AzerothGPS Map Menu in game map
mode, and for all modes lets add another menu quick button with submenu selections for showing/hiding all our map
elements individually"; then, tried in game: "Map layer should be in the map menu pop out no always showing and all its
options should be submenu quick buttons just like every other quick button with sub buttons to toggle on and off
supported by controller too"; and "lets replace the quests button position with this one since quests and quest areas
are now under the map layer menu", "also caves/dungeons/raids, lets remove that button as its also under map layers
button").

The map menu button is "AzerothGPS Map Menu" while the GPS map is in the game's world map, "Map Menu" in its own window.
Map Layers is a group of the map menu's quick buttons (G.QUICK_GROUPS "mapLayers", in the menu's column by default):
out of it the layers' groups (G.LAYER_GROUPS), each with a flyout of its own (G.ToggleSubGroup) of a toggle per layer
(G.MAP_LAYERS), then Show All and Hide All. Each layer is a setting (the option's own where there was one), applied to
every map at once; the Route line hidden leaves the routing and the directions as they were. The controller goes through
them as through the other groups' buttons (Pad.MenuButtons), B back out a level at a time."""

import pytest

from test_controller import PAD_STUBS, _frames, _press
from test_extra_map_window import CHROME
from test_world_map_host import SETUP as WM_SETUP

# Each layer and what of it the map draws near the harness's player (Brill, zoomed out to ZOOM yd): the poi buttons'
# kind (GPSFrame's DrawPois `p[1]`), or "route" (its lines) or "stops" (the stops' markers).
DRAWN = {"taxi": 1, "poi": 2, "docks": 10, "instances": 6, "caves": 11, "route": "route", "stops": "stops"}
ZOOM = 2400
FAR = "{ { x = 2254, y = 900, cont = 0, name = 'Far' } }"  # (a stop south of Brill: a route with a line)
LAYERS = ["route", "stops", "heightProfile", "floorPicker", "avoided", "taxi", "docks", "instances", "dungeonPaths",
          "caves", "labels", "poi", "city", "npcs", "pins", "otherPins", "party", "quests", "questAreas", "herbs", "ore"]
# The layers that are an option's setting: the Options window's own control for it (Options > Map icons, Map, Routing).
OPTION_BACKED = set(LAYERS) - {"dungeonPaths"}
# ... and those that are a map menu quick button's (G.QUICK's `key`): its icon the layer's button's too
QUICK_BACKED = {"city": "city", "herbs": "herbs", "ore": "ore"}
# The map menu's buttons gone into Map Layers (2026-11-27): the Quests group's and the Caves/Dungeons/Raids group's
GONE = ["questsG", "quests", "questAreas", "dungeonsG", "caves", "instances", "dungeonPaths"]


@pytest.fixture(scope="module")
def game():
    pytest.importorskip("lupa.lua51")
    from azerothgps.gameharness import start, toc_files
    from azerothgps.paths import ADDON_DIR
    first = toc_files()[0]
    lua, ns = start(replace={first: CHROME + (ADDON_DIR / first).read_text(encoding="utf-8")})
    ns.Nav.FUN = False
    lua.execute(WM_SETUP)
    return lua, ns


@pytest.fixture
def gps(game):
    lua, ns = game
    st = ns.settings.gps
    keys = [str(e.key) for e in ns.GPS.MAP_LAYERS.values()]
    was = {k: st[k] for k in keys + ["zoom", "useWorldMap", "extraWindow", "shown", "minimized", "quick"]}
    st.shown, st.minimized, st.zoom = True, None, ZOOM
    for k in keys:
        st[k] = ns.DEFAULTS.gps[k]
    ns.GPS.ApplySettings()
    yield lua, ns
    ns.GPS.CloseOpenGroup()
    ns.GPS.mapMenu.Hide(ns.GPS.mapMenu)
    lua.execute("WorldMapFrame:Hide()")
    for k, v in was.items():
        st[k] = v
    ns.GPS.WorldMapChanged()
    ns.GPS.ApplySettings()
    ns.Nav.Clear()


def _draw(lua, G):
    lua.execute("AGPS_T = AGPS_T + 5")
    G.Redraw()
    G.Update()


def _drawn(lua, ns, what):
    """How many of `what` the first map draws (its canvas's own: not the extra window's, put away)."""
    mine = lua.eval("""function(w, c)
      local p = w
      while p do
        if rawequal(p, c) then return true end
        p = p.GetParent and p:GetParent() or nil
      end
      return false
    end""")
    c = ns.GPS.Canvas()
    ws = [w for w in lua.eval("AGPS_WIDGETS").values() if w._shown and mine(w, c)]
    if what == "route":
        return len([w for w in ws if w._kind == "Line"])
    if what == "stops":
        return len([w for w in ws if w.stopIndex is not None])
    return len([w for w in ws if w.kind == what and w.wx is not None])


def _quick(G, qid):
    return next(t for t in G.QUICK.values() if t.id == qid)


def _click(b):
    b._scripts.OnClick(b, "LeftButton")


def _open_menu(lua, G):
    """The map menu open, its drawer out (its buttons shown)."""
    if not G.mapMenu._shown:
        _click(G.mapButton)
    G.LayoutQuick()
    _frames(lua, 10)
    return G.groupOf.mapLayers


def _open_layers(lua, G):
    grp = _open_menu(lua, G)
    if not G.OpenGroupSlot() or not lua.eval("rawequal")(G.OpenGroupSlot(), grp):
        _click(grp.button)
    assert lua.eval("rawequal")(G.OpenGroupSlot(), grp)
    return grp


def _gid(G, lid):
    return next(str(g.id) for g in G.LAYER_GROUPS.values() if lid in list(g.layers.values()))


def _open_group(lua, G, gid):
    _open_layers(lua, G)
    t = _quick(G, "layers_" + gid)
    if not G.OpenSubSlot() or not lua.eval("rawequal")(G.OpenSubSlot(), t):
        _click(t.button)
    assert lua.eval("rawequal")(G.OpenSubSlot(), t)
    return t


def _click_layer(lua, G, lid):
    """The layer's toggle clicked, through the map menu: Map Layers, its group's button, then its own."""
    _open_group(lua, G, _gid(G, lid))
    t = _quick(G, "layer_" + lid)
    assert t.button._shown
    _click(t.button)
    return t


def _lit(t):
    """A quick button's look: lit (on) or gray (off), as G.RefreshQuick sets every quick button's."""
    return t.iconTex._desat is not True


def _host_world_map(lua, ns):
    G, st = ns.GPS, ns.settings.gps
    st.useWorldMap = True
    G.ApplySettings()
    lua.globals().AzerothGPS_ToggleMap()  # (the show/hide key: the world map)
    assert G.WorldMapHosted()


def _tip(lua, button):
    button._scripts.OnEnter(button)
    return str(lua.eval("GameTooltip._text"))


def test_the_map_menu_is_named_azerothgps_map_menu_in_the_world_map_only(gps):
    lua, ns = gps
    G = ns.GPS
    assert not G.WorldMapHosted()
    assert G.MapMenuName() == "Map Menu" and _tip(lua, G.mapButton) == "Map Menu"  # (its own window)
    _host_world_map(lua, ns)
    assert G.MapMenuName() == "AzerothGPS Map Menu" and _tip(lua, G.mapButton) == "AzerothGPS Map Menu"
    lua.globals().AzerothGPS_ToggleMap()  # (the world map shut: its own window again, when shown)
    ns.settings.gps.useWorldMap = False
    G.ApplySettings()
    assert _tip(lua, G.mapButton) == "Map Menu"


def test_the_extra_map_windows_map_menu_keeps_its_name(gps):
    lua, ns = gps
    st = ns.settings.gps
    st.extraWindow = True
    ns.GPS.ApplySettings()
    e = ns.extraMap
    try:
        assert e.MapMenuName() == "Map Menu" and _tip(lua, e.mapButton) == "Map Menu"
    finally:
        st.extraWindow = False
        ns.GPS.ApplySettings()


def test_map_layers_is_in_the_map_menu_not_always_shown(gps):
    lua, ns = gps
    G, st = ns.GPS, ns.settings.gps
    # (no button of its own any more: a group of the map menu's, in its column)
    assert not any(t.id == "mapLayers" for t in G.QUICK.values())
    grp = G.groupOf.mapLayers
    assert grp.label == "Map Layers" and grp.icon == G.LAYERS_ICON
    assert G.QuickPlace("mapLayers") == "menuUp"
    assert "mapLayers" in [str(t.id) for t in G.QuickSlots().values()]  # (the Quick buttons page lists it)
    # (none of its buttons is a slot of its own: the layers' groups, Show All and Hide All only in its flyout)
    slots = {str(t.id) for t in G.QuickSlots().values()}
    assert not {s for s in slots if s.startswith("layer")}
    G.mapMenu.Hide(G.mapMenu)
    G.LayoutQuick()
    _frames(lua, 10)
    assert not grp.button._shown  # (the menu shut: not shown)
    _open_menu(lua, G)
    assert grp.button._shown and grp.where == "menuUp"
    # (sharp: a round quick button drawn at whole pixels, its icon one of the sizes drawn, G.RoundArt)
    assert grp.button.agpsArt and grp.iconTex.agpsArtPx in list(G.RING_SIZES.values())
    assert ns.IconSizes.files["icons/inv_misc_eye_01"]


def test_the_quests_and_caves_dungeons_raids_buttons_are_gone_map_layers_in_quests_place(gps):
    lua, ns = gps
    G = ns.GPS
    ids = {str(t.id) for t in G.QUICK.values()}
    assert not ids & set(GONE) and not set(GONE) & set(str(k) for k in G.groupOf.keys())
    slots = [str(t.id) for t in G.QuickSlots().values()]
    assert not set(slots) & set(GONE)
    # (where the Quests group was: after Use Hearthstone, before Herbs, Ore and Farming; the gap the Caves/Dungeons/Raids
    # group left closed)
    assert slots.index("mapLayers") == slots.index("hearth") + 1 and slots.index("gather") == slots.index("mapLayers") + 1
    col = [s for s in slots if G.QuickPlace(s) == "menuUp"]
    assert col == ["search", "quickFind", "mapLayers", "gather"]
    # (the column as laid out: Map Layers the third button up the map menu, Herbs, Ore and Farming over it)
    _open_menu(lua, G)
    ups = [b for b in ns.Pad.MenuButtons().values()]
    same = lua.eval("rawequal")
    assert same(ups[2], G.groupOf.mapLayers.button) and same(ups[3], G.groupOf.gather.button)
    # (all their toggles still there, through Map Layers: the same settings)
    for lid in ("quests", "questAreas", "caves", "instances", "dungeonPaths"):
        _click_layer(lua, G, lid)
        assert not G.LayerSet(lid), lid
        _click_layer(lua, G, lid)
        assert G.LayerSet(lid), lid
    # (the quests' and dungeons' own tooltips with them, the quest areas' tint)
    assert "objectives and turn-ins" in str(_quick(G, "layer_quests").tip)
    assert _quick(G, "layer_questAreas").tint and "boss by boss" in str(_quick(G, "layer_dungeonPaths").tip)


@pytest.mark.parametrize("before, place", [("{ questsG = 'menuRight' }", "menuRight"), ("{ questsG = 'hidden' }", "hidden"),
                                           ("{ quests = 'barUp' }", "barUp"), ("nil", None)])
def test_where_the_quests_button_was_put_map_layers_goes_once(before, place):
    # (InitDB's questsToLayers142: a player's place for the Quests button, and its spot in their order, Map Layers'; the
    # quest layers' own settings as they were)
    pytest.importorskip("lupa.lua51")
    from azerothgps.gameharness import start
    lua, ns = start(saved="AzerothGPSDB = { settings = { gps = { quick = %s, layerQuests = false, "
                          "quickOrder = { 'search', 'questsG', 'gather' } } } }" % before)
    st = ns.settings.gps
    assert ns.db.questsToLayers142 is True
    assert (st.quick.mapLayers if st.quick else None) == place
    assert list(st.quickOrder.values()) == ["search", "mapLayers", "gather"]
    assert st.layerQuests is False and st.layerQuestAreas is True  # (the layers themselves: untouched)
    G = ns.GPS
    assert G.QuickPlace("mapLayers") == (place or "menuUp")
    slots = [str(t.id) for t in G.QuickSlots().values()]
    assert slots[:4] == ["search", "quickFind", "mapLayers", "gather"]  # (Quick Find: just above Search Places, as ever)
    # (a later login: not again, Map Layers moved since kept)
    st.quick = lua.eval("{ mapLayers = 'menuRight', questsG = 'barUp' }")
    ns.QuestsToLayers(st)  # (the migration's own: a set Map Layers place wins)
    assert st.quick.mapLayers == "menuRight"


def test_map_layers_is_in_the_map_menu_in_every_mode(gps):
    lua, ns = gps
    G, st = ns.GPS, ns.settings.gps
    _host_world_map(lua, ns)
    grp = _open_menu(lua, G)
    assert grp.button._shown
    _open_group(lua, G, "travel")
    assert _quick(G, "layer_caves").button._shown
    G.CloseOpenGroup()
    lua.globals().AzerothGPS_ToggleMap()
    st.useWorldMap = False
    G.ApplySettings()
    st.extraWindow = True
    G.ApplySettings()
    e = ns.extraMap
    try:
        eg = e.groupOf.mapLayers
        _click(e.mapButton)
        e.LayoutQuick()
        _frames(lua, 10)
        assert eg.button._shown and not lua.eval("rawequal")(eg.button, G.groupOf.mapLayers.button)
        _click(eg.button)
        et = next(q for q in e.QUICK.values() if q.id == "layers_route")
        _click(et.button)
        assert lua.eval("rawequal")(e.OpenSubSlot(), et)
        assert next(q for q in e.QUICK.values() if q.id == "layer_route").button._shown
    finally:
        e.CloseOpenGroup()
        e.mapMenu.Hide(e.mapMenu)
        st.extraWindow = False
        G.ApplySettings()
    # (and it can be hidden in the options, as the other quick buttons)
    st.quick = lua.eval("{ mapLayers = 'hidden' }")
    _open_menu(lua, G)
    assert not G.groupOf.mapLayers.button._shown


def test_its_groups_and_their_toggles_are_quick_buttons_out_of_it(gps):
    lua, ns = gps
    G = ns.GPS
    grp = _open_layers(lua, G)
    same = lua.eval("rawequal")
    members = [str(m.id) for m in grp.members.values()]
    assert members == ["layers_route", "layers_travel", "layers_places", "layers_questsGather", "layersShowAll",
                       "layersHideAll"]
    assert [str(_quick(G, m).label) for m in members] == ["Route", "Travel", "Places", "Quests and gathering",
                                                          "Show All", "Hide All"]
    # (out of the group's button as any group's: a row right of a column going up)
    first = _quick(G, "layers_route").button
    assert first._shown and first._pt[1] == "LEFT" and same(first._pt[2], grp.button) and first._pt[3] == "RIGHT"
    grouped = []
    for g in G.LAYER_GROUPS.values():
        t = _open_group(lua, G, str(g.id))
        ids = [str(i) for i in t.subMembers.values()]
        assert ids == ["layer_" + str(i) for i in g.layers.values()]
        for j, sid in enumerate(ids):
            b = _quick(G, sid).button
            # (its own flyout the other way: a column up from its button, as Quick Find's Ammo)
            assert b._shown and b._pt[1] == "BOTTOM" and same(b._pt[2], t.button) and b._pt[3] == "TOP"
            assert abs(b._pt[5] - (4 + j * G.QUICK_STEP_MENU)) < 1e-9
        # (one group's flyout out at a time)
        for o in G.LAYER_GROUPS.values():
            if o.id != g.id:
                assert not _quick(G, "layer_" + str(o.layers[1])).button._shown
        grouped += [i[len("layer_"):] for i in ids]
    assert sorted(grouped) == sorted(LAYERS) == sorted(str(e.id) for e in G.MAP_LAYERS.values())
    # each layer a setting of the player's, saved with the others (in the defaults, on)
    for e in G.MAP_LAYERS.values():
        assert ns.DEFAULTS.gps[e.key] is True, e.key
    # the group shut: its flyouts with it
    G.CloseOpenGroup()
    assert not G.OpenSubSlot() and not first._shown and not _quick(G, "layer_route").button._shown


@pytest.mark.parametrize("lid", LAYERS)
def test_every_layer_toggle_hides_and_shows_it(gps, lid):
    lua, ns = gps
    G, st = ns.GPS, ns.settings.gps
    e = G.layerById[lid]
    if DRAWN.get(lid) in ("route", "stops"):
        ns.Nav.SetStops(lua.eval(FAR), False)
    _draw(lua, G)
    before = _drawn(lua, ns, DRAWN[lid]) if lid in DRAWN else None
    t = _click_layer(lua, G, lid)
    assert st[e.key] is False and not G.LayerOn(lid) and not _lit(t)  # (hidden: gray, as an off quick button)
    assert t.button._shown  # (the flyout stays out for more)
    _draw(lua, G)
    if lid in DRAWN:
        after = _drawn(lua, ns, DRAWN[lid])
        assert before > 0 and after < before, (before, after)
        if DRAWN[lid] != "route":
            assert after == 0
    t = _click_layer(lua, G, lid)
    assert st[e.key] is True and G.LayerOn(lid) and _lit(t)
    _draw(lua, G)
    if lid in DRAWN:
        assert _drawn(lua, ns, DRAWN[lid]) == before


@pytest.mark.parametrize("lid", sorted(DRAWN))
def test_every_layer_toggle_hides_and_shows_it_in_the_world_map(gps, lid):
    lua, ns = gps
    G = ns.GPS
    _host_world_map(lua, ns)
    if DRAWN[lid] in ("route", "stops"):
        ns.Nav.SetStops(lua.eval(FAR), False)
    ns.settings.gps.zoom = ZOOM
    _draw(lua, G)
    before = _drawn(lua, ns, DRAWN[lid])
    _click_layer(lua, G, lid)
    _draw(lua, G)
    after = _drawn(lua, ns, DRAWN[lid])
    assert before > 0 and after < before and (DRAWN[lid] == "route" or after == 0), (before, after)
    _click_layer(lua, G, lid)
    _draw(lua, G)
    assert _drawn(lua, ns, DRAWN[lid]) == before


def test_a_layer_needing_another_is_gray_while_that_one_is_hidden(gps):
    lua, ns = gps
    G, st = ns.GPS, ns.settings.gps
    _click_layer(lua, G, "quests")
    t = _quick(G, "layer_questAreas")
    assert st.layerQuestAreas is True and not G.LayerOn("questAreas") and not _lit(t)
    _click(t.button)  # (gray: nothing)
    assert st.layerQuestAreas is True
    _click_layer(lua, G, "quests")
    assert G.LayerOn("questAreas") and _lit(t)
    # (Routes through dungeons with Dungeons and raids hidden: the same)
    _click_layer(lua, G, "instances")
    assert not _lit(_quick(G, "layer_dungeonPaths")) and _quick(G, "layer_dungeonPaths").needs == "layerInstances"
    _click_layer(lua, G, "instances")


def test_show_all_and_hide_all(gps):
    lua, ns = gps
    G, st = ns.GPS, ns.settings.gps
    ns.Nav.SetStops(lua.eval(FAR), False)
    _draw(lua, G)
    counts = {k: _drawn(lua, ns, w) for k, w in DRAWN.items()}
    grp = _open_layers(lua, G)
    _click(_quick(G, "layersHideAll").button)
    assert all(st[e.key] is False for e in G.MAP_LAYERS.values())
    # (every group's button gray, and Map Layers' own; the flyout stays out)
    assert not any(_lit(_quick(G, "layers_" + str(g.id))) for g in G.LAYER_GROUPS.values())
    assert grp.iconTex._desat is True and _quick(G, "layersHideAll").button._shown
    _draw(lua, G)
    for k, w in DRAWN.items():
        assert _drawn(lua, ns, w) < counts[k], k
    assert ns.Nav.route is not None  # (still routed)
    _click(_quick(G, "layersShowAll").button)
    assert all(st[e.key] is True for e in G.MAP_LAYERS.values())
    assert all(_lit(_quick(G, "layers_" + str(g.id))) for g in G.LAYER_GROUPS.values()) and grp.iconTex._desat is False
    _draw(lua, G)
    assert {k: _drawn(lua, ns, w) for k, w in DRAWN.items()} == counts
    # (some of a group shown: its button still lit)
    _click_layer(lua, G, "taxi")
    assert G.LayerGroupState("travel") == "some" and _lit(_quick(G, "layers_travel"))


def test_hiding_the_route_line_keeps_the_route_and_the_directions(gps):
    lua, ns = gps
    G, N = ns.GPS, ns.Nav
    N.SetStops(lua.eval(FAR), False)
    _draw(lua, G)
    steps = [str(x) for x in N.Steps().values()]
    lines = _drawn(lua, ns, "route")
    assert N.route is not None and steps and "Far" in steps[-1]
    _click_layer(lua, G, "route")
    _draw(lua, G)
    assert _drawn(lua, ns, "route") < lines
    # (the route worked out and kept, the stop and its marker, the directions as before)
    assert N.route is not None and N.dest is not None and len(N.stops) == 1
    assert [str(x) for x in N.Steps().values()] == steps and _drawn(lua, ns, "stops") == 1
    assert not N.paused
    _click_layer(lua, G, "route")
    _draw(lua, G)
    assert _drawn(lua, ns, "route") == lines


def test_layers_apply_to_every_map_at_once(gps):
    lua, ns = gps
    G, st = ns.GPS, ns.settings.gps
    st.extraWindow = True
    G.ApplySettings()
    e = ns.extraMap
    try:
        version = e.drawVersion
        _click_layer(lua, G, "caves")  # (the first window's)
        assert not e.LayerOn("caves") and e.drawVersion > version  # (the extra window drawn again too)
        et = next(q for q in e.QUICK.values() if q.id == "layer_caves")
        assert et.iconTex._desat is True  # (its own button says so too)
        _click(et.button)  # (and back from the extra window's)
        assert st.layerCaves is True and G.LayerOn("caves") and _lit(_quick(G, "layer_caves"))
    finally:
        st.extraWindow = False
        G.ApplySettings()


def test_toggles_stay_in_step_with_the_options_and_the_other_quick_buttons(gps):
    lua, ns = gps
    G, O, st = ns.GPS, ns.Options, ns.settings.gps
    O.Show()
    controls = {str(c.key): c.control for c in O.settingControls.values() if not c.mirror}
    for lid in sorted(OPTION_BACKED):
        e = G.layerById[lid]
        cb = controls[str(e.key)]  # (the option's own setting: no second switch)
        t = _click_layer(lua, G, lid)
        assert cb.GetChecked(cb) is False, lid  # (hidden from the map menu: the option's box cleared)
        cb.SetChecked(cb, True)
        cb._scripts.OnClick(cb)  # (the option ticked again: the layer's button lit)
        assert st[e.key] is True and _lit(t), lid
    for lid, qid in QUICK_BACKED.items():
        e, q = G.layerById[lid], _quick(G, qid)
        assert q.key == e.key, lid  # (the map menu's own toggle: the same setting)
        t = _quick(G, "layer_" + lid)
        assert t.icon == q.icon, lid  # (and the same icon)
        _click_layer(lua, G, lid)
        assert G.QuickOn(q) is False and q.iconTex._desat is True, lid
        _click(q.button)  # (the other quick button again: the layer's button lit)
        assert st[e.key] is True and _lit(t), lid
    lua.execute("AGPS_NS.Options.Toggle()")  # (shut again: the controller's tests after)
    assert not O.IsShown()


def test_the_buttons_icons_are_drawn_at_whole_pixels(gps):
    lua, ns = gps
    G = ns.GPS
    sizes = list(G.RING_SIZES.values())
    _open_layers(lua, G)
    for g in G.LAYER_GROUPS.values():
        t = _open_group(lua, G, str(g.id))
        for b in [t] + [_quick(G, s) for s in t.subMembers.values()]:
            a = b.button.agpsArt
            assert a and b.iconTex.agpsArtPx in sizes, b.id  # (the round buttons' art, G.RoundArt)
            ppu = a.ppu
            assert abs(b.iconTex._w * ppu - b.iconTex.agpsArtPx) < 1e-6 and b.iconTex._w == b.iconTex._h, b.id
    # (a game icon drawn at that size where it's shipped: the herbs' button's)
    herb = _quick(G, "layer_herbs").iconTex
    assert str(herb._tex).startswith(str(ns.IconSizes.path))


# StreetView's buttons as AzerothGPS_StreetView's Figure.lua makes them (read only, not changed): on the map's button
# layer, Street Guess's anchored by its BOTTOM over our corner (API.MapButton "recenter" while it shows, else "import"),
# the figure over Street Guess's; and its own re-placing as Back to Your Position shows or hides (its Place()).
STREETVIEW = """
  local API = AzerothGPS
  local parent = API.MapButtonParent()
  local recenter, import = API.MapButton("recenter"), API.MapButton("import")
  local figure = CreateFrame("Button", nil, parent)
  figure:SetSize(28, 28)
  local game = CreateFrame("Button", nil, parent)
  game:SetSize(28, 28)
  AGPS_SV = { game = game, figure = figure, placed = 0 }
  for _, b in ipairs({ game, figure }) do b.GetPoint = function(f) return unpack(f._pt or {}) end end -- (the stand-in's)
  AGPS_SV.Place = function()
    AGPS_SV.placed = AGPS_SV.placed + 1
    game:ClearAllPoints()
    local below = (recenter and recenter:IsShown() and recenter) or import
    game:SetPoint("BOTTOM", below, "TOP", 0, 4)
  end
  AGPS_SV.Place()
  figure:SetPoint("BOTTOM", game, "TOP", 0, 4)
  recenter:HookScript("OnShow", AGPS_SV.Place)
  recenter:HookScript("OnHide", AGPS_SV.Place)
"""


def _row(lua, G):
    """The map menu's row going right, as laid out: the slots' ids in their order."""
    G.LayoutQuick()
    return [str(t.id) for t in G.QuickSlots().values() if t.where in ("barRight", "menuRight")]


def _wide(lua):
    """The map's button layer as wide as the map grows for its row (the stand-in's layer stays 400 across otherwise:
    G.FitSize sizes the window, the layer's GetWidth is the stand-in's)."""
    lua.execute("local t = AGPS_NS.GPS.TopLayer() t.GetWidth = function() return 800 end "
                "t.GetHeight = function() return 600 end")


def _narrow(lua):
    lua.execute("local t = AGPS_NS.GPS.TopLayer() t.GetWidth, t.GetHeight = nil, nil")


def _streetview(lua, ns):
    _wide(lua)
    lua.execute(STREETVIEW)
    G = ns.GPS
    G.quickWatchAt = None
    G.WatchQuickOn()  # (its twice-a-second look: the new buttons over the corner found)
    sv = lua.eval("AGPS_SV")
    return sv.game, sv.figure


def _closed(lua, G):
    """The map menu shut, its drawer in."""
    G.mapMenu.Hide(G.mapMenu)
    G.LayoutQuick()
    _frames(lua, 10)


def _in_row(lua, G, b):
    """`b` out on the row going right from the map menu button, shown."""
    return b._shown and b._pt[1] == "LEFT" and lua.eval("rawequal")(b._pt[2], G.mapButton) and b._pt[3] == "RIGHT"


def test_import_and_share_is_at_the_end_of_the_map_menus_row_while_it_is_open(gps):
    # (Kooki3z 2026-11-27, tried in game: "the import and streetview buttons are on the horizontal menu line, which is
    # correct but should only be visible when clicking the map menu button")
    lua, ns = gps
    G = ns.GPS
    same = lua.eval("rawequal")
    imp = G.importButton
    t = _quick(G, "import")
    assert same(t.button, imp) and t.label == "Import and Share" and G.QuickPlace("import") == "menuRight"
    _wide(lua)
    try:
        row = _row(lua, G)
        assert row[-1] == "import" or row[row.index("import") + 1:] == [r for r in row if r.startswith("companion")]
        # (shut: not shown, taking no room; the row's always-shown buttons as they were)
        _closed(lua, G)
        assert not imp._shown and t.where == "menuRight"
        # (open: out on the row from the map menu button, past the menu's others going right)
        _open_menu(lua, G)
        assert _in_row(lua, G, imp)
        hearth = _quick(G, "hearth").button
        assert imp._pt[4] > hearth._pt[4]
        _closed(lua, G)
        assert not imp._shown
        # (on the row like every other quick button, Use Hearthstone's: the map as wide as the row needs, Pause
        # Routing counted whether a route shows it or not, so a route starting never widens it)
        assert G.QuickCounts()[1] == 4 and G.QuickMinWidth() == 480
        # (the old corner's frame kept, Back to Your Position in its spot, the column only it)
        assert G.mapButtons["import"] is not None and not same(G.mapButtons["import"], imp)
        rc = G.mapButtons.recenter
        assert rc._pt[1] == "BOTTOMRIGHT" and same(rc._pt[2], G.mapButtons["import"])
        assert G.CORNER_COLUMN == 1
        col = G.CornerColumnRect()
        assert col[4] - col[2] == pytest.approx(G.CORNER_STEP - G.CORNER_GAP)
        # (the click: Import and Share, as ever)
        was = ns.Import.Toggle
        try:
            lua.execute("AGPS_IMPORTS = 0 AGPS_NS.Import.Toggle = function() AGPS_IMPORTS = AGPS_IMPORTS + 1 end")
            _click(imp)
            assert lua.eval("AGPS_IMPORTS") == 1
        finally:
            ns.Import.Toggle = was
    finally:
        _closed(lua, G)
        _narrow(lua)


def test_with_a_route_import_and_streetviews_buttons_share_the_row_with_pause_routing(gps):
    # (Kooki3z 2026-11-27: "They should because like quick buttons do now like the hearthstone toggle": on the row with
    # Pause Routing and Use Hearthstone, never into the column; the map as wide as they need, as for any quick button)
    lua, ns = gps
    G, st = ns.GPS, ns.settings.gps
    was = (st.size, st.width, st.freeSize)
    st.size, st.freeSize = 450, False  # (the default map)
    G.ApplySettings()
    game, figure = _streetview(lua, ns)
    try:
        need = G.QuickMinWidth()
        assert need == 600 and tuple(G.MapSize()) == (600, 600)  # (six going right: the square that holds them)
        ns.Nav.SetStops(lua.eval(FAR), False)
        _draw(lua, G)
        G.ApplySettings()
        assert G.QuickMinWidth() == need and tuple(G.MapSize()) == (600, 600)  # (a route starting: the same size)
        lua.execute("local t = AGPS_NS.GPS.TopLayer() t.GetWidth = function() return 600 end "
                    "t.GetHeight = function() return 600 end")  # (the stand-in's layer that size)
        _open_menu(lua, G)
        ids = ["questRoute", "hearth", "pauseRoute", "import"]
        buttons = [_quick(G, i).button for i in ids] + [game, figure]
        assert all(_quick(G, i).where == "menuRight" for i in ids)
        xs = []
        for b in buttons:
            assert _in_row(lua, G, b), b
            xs.append(b._pt[4])
        # (one after another along the row from the map menu button, a step apart, the last clear of the bottom's
        # middle (Clear Route, the coordinates): the row's own room, G.QuickCapacityAt)
        assert xs == sorted(xs) and all(abs(b - a - G.QUICK_STEP_BAR) < 1e-9 for a, b in zip(xs, xs[1:]))
        assert 3 + 32 + xs[-1] + 28 <= 600 / 2 - 80 + 30
        assert G.QuickCapacityAt(600, 600)[1] >= 6
    finally:
        ns.Nav.Clear()
        lua.execute("AzerothGPS.MapMenuButtonShown(AGPS_SV.game, false) AzerothGPS.MapMenuButtonShown(AGPS_SV.figure, false)")
        _closed(lua, G)
        _narrow(lua)
        st.size, st.width, st.freeSize = was
        G.ApplySettings()


@pytest.mark.parametrize("mode", ["window", "worldMap", "extra"])
def test_the_row_tail_shows_only_with_the_menu_open_in_every_mode(gps, mode):
    lua, ns = gps
    G, st = ns.GPS, ns.settings.gps
    g = G
    _wide(lua)
    try:
        if mode == "worldMap":
            _host_world_map(lua, ns)
        if mode == "extra":
            st.extraWindow = True
            G.ApplySettings()
            g = ns.extraMap
            lua.execute("local t = AGPS_NS.extraMap.TopLayer() t.GetWidth = function() return 800 end "
                        "t.GetHeight = function() return 600 end")
        imp = g.importButton
        g.mapMenu.Hide(g.mapMenu)
        g.LayoutQuick()
        _frames(lua, 10)
        assert not imp._shown, mode
        _click(g.mapButton)
        g.LayoutQuick()
        _frames(lua, 10)
        assert _in_row(lua, g, imp), mode
        g.mapMenu.Hide(g.mapMenu)
        g.LayoutQuick()
        _frames(lua, 10)
        assert not imp._shown, mode
    finally:
        if mode == "extra":
            lua.execute("local t = AGPS_NS.extraMap.TopLayer() t.GetWidth, t.GetHeight = nil, nil")
            st.extraWindow = False
            G.ApplySettings()
        _closed(lua, G)
        _narrow(lua)


def test_streetviews_buttons_follow_import_and_share_while_the_menu_is_open_then_in_the_pop_out(gps):
    lua, ns = gps
    G, st = ns.GPS, ns.settings.gps
    same = lua.eval("rawequal")
    game, figure = _streetview(lua, ns)
    try:
        a, b = G.companionOf[game], G.companionOf[figure]
        assert a and b and a.companion and b.companion
        row = _row(lua, G)
        assert row[-3:] == ["import", str(a.id), str(b.id)]  # (after Import and Share: Street Guess's, the figure)
        # (shut: hidden; open: on the row after Import and Share)
        _closed(lua, G)
        assert not game._shown and not figure._shown
        _open_menu(lua, G)
        for k in (game, figure):
            assert _in_row(lua, G, k)
        assert game._pt[4] > G.importButton._pt[4] and figure._pt[4] > game._pt[4]
        assert G.CornerColumnRect()[4] - G.CornerColumnRect()[2] == pytest.approx(G.CORNER_STEP - G.CORNER_GAP)
        # (its own re-placing as Back to Your Position shows, the menu open: back on the row at once)
        rc = G.mapButtons.recenter
        rc.Show(rc)
        rc._scripts.OnShow(rc)
        assert lua.eval("AGPS_SV.placed") >= 2 and _in_row(lua, G, game)
        rc.Hide(rc)
        rc._scripts.OnHide(rc)
        # (... and with the menu shut: still hidden, through its re-placing and the drawer's frames after)
        _closed(lua, G)
        placed = lua.eval("AGPS_SV.placed")
        rc.Show(rc)
        rc._scripts.OnShow(rc)
        _frames(lua, 10)
        assert lua.eval("AGPS_SV.placed") > placed and not game._shown and not figure._shown
        rc.Hide(rc)
        rc._scripts.OnHide(rc)
        _frames(lua, 10)
        assert not game._shown and not figure._shown
        # (open again: back)
        _open_menu(lua, G)
        assert _in_row(lua, G, game) and _in_row(lua, G, figure)
        _closed(lua, G)
        # (not on the Quick buttons page: the option says where they go)
        assert all(not t.companion or str(t.id).startswith("companion") for t in G.QuickSlots().values())
        # the option on: at the end of the map menu's column (its pop-out), not on the row
        st.companionsInMenu = True
        G.ApplySettings()
        assert G.QuickPlace(str(a.id)) == "menuUp"
        col = [str(t.id) for t in G.QuickSlots().values() if t.where == "menuUp"]
        assert col[-2:] == [str(a.id), str(b.id)] and str(a.id) not in _row(lua, G)
        _open_menu(lua, G)
        for k in (game, figure):
            assert k._shown and k._pt[1] == "BOTTOM" and same(k._pt[2], G.mapButton) and k._pt[3] == "TOP"
        _closed(lua, G)
        assert not game._shown and not figure._shown  # (the menu shut: in it)
    finally:
        st.companionsInMenu = False
        lua.execute("AzerothGPS.MapMenuButtonShown(AGPS_SV.game, false) AzerothGPS.MapMenuButtonShown(AGPS_SV.figure, false)")
        _narrow(lua)
        G.ApplySettings()


def test_another_companions_button_through_the_api(gps):
    lua, ns = gps
    G = ns.GPS
    _wide(lua)
    lua.execute("""
      AGPS_MINE = CreateFrame("Button", nil, AzerothGPS.MapButtonParent())
      AGPS_MINE:SetSize(28, 28)
      AGPS_MINE_IN = AzerothGPS.MapMenuButton(AGPS_MINE, "Mine", "A companion's button")
    """)
    try:
        mine = lua.eval("AGPS_MINE")
        assert lua.eval("AGPS_MINE_IN") is True and lua.eval("AzerothGPS.MapMenuButton(AGPS_MINE)") is True  # (once)
        t = G.companionOf[mine]
        assert t.label == "Mine" and _row(lua, G)[-1] == str(t.id)
        _closed(lua, G)
        assert not mine._shown
        _open_menu(lua, G)
        assert _in_row(lua, G, mine)
    finally:
        lua.execute("AzerothGPS.MapMenuButtonShown(AGPS_MINE, false)")
        assert not lua.eval("AGPS_MINE")._shown and str(G.companionOf[lua.eval("AGPS_MINE")].id) not in _row(lua, G)
        _closed(lua, G)
        _narrow(lua)


def test_the_controller_reaches_import_and_the_companions_buttons_only_with_the_menu_open(pad):
    lua, ns = pad
    G, P = ns.GPS, ns.Pad
    same = lua.eval("rawequal")
    game, figure = _streetview(lua, ns)
    try:
        G.ApplySettings()
        G.LayoutQuick()
        _frames(lua)
        assert not P.MenuOpen() and not G.importButton._shown and not game._shown  # (shut: none of them)
        _press(lua, "PAD4")  # (Y: the map menu)
        G.LayoutQuick()
        _frames(lua)
        col, row = P.MenuParts()
        row = list(row.values())
        # (on the row past the menu's others going right: Import and Share, then StreetView's)
        at = next(i for i, b in enumerate(row) if same(b, G.importButton))
        assert same(row[at + 1], game) and same(row[at + 2], figure)
        _press(lua, "PADDRIGHT")  # (onto the row: its first)
        for _ in range(len(row)):
            if same(P.focus, game):
                break
            _press(lua, "PADDRIGHT")
        assert same(P.focus, game)
        _press(lua, "PAD4")  # (Y again: shut, the focus gone with them)
        G.LayoutQuick()  # (the menu's OnHide hook, which the stand-in game doesn't run)
        _frames(lua)
        assert not P.MenuOpen() and P.focus is None and not game._shown
        # (the option on: the end of the column)
        ns.settings.gps.companionsInMenu = True
        G.ApplySettings()
        _press(lua, "PAD4")
        G.LayoutQuick()
        _frames(lua)
        col, row = P.MenuParts()
        assert same(list(col.values())[-1], figure) and not any(same(b, game) for b in row.values())
    finally:
        ns.settings.gps.companionsInMenu = False
        lua.execute("AzerothGPS.MapMenuButtonShown(AGPS_SV.game, false) AzerothGPS.MapMenuButtonShown(AGPS_SV.figure, false)")
        _narrow(lua)
        G.ApplySettings()


@pytest.fixture
def pad(gps):
    lua, ns = gps
    G, P = ns.GPS, ns.Pad
    lua.execute(PAD_STUBS)
    ns.db.padOffered = True
    ns.settings.gps.padControl = True
    P.used = True
    lua.execute("AGPS_T = AGPS_T + 1")
    G.Update()
    assert P.Apply()
    yield lua, ns
    if P.MenuOpen():
        P.CloseMenu()
    P.Clear()


def test_the_controller_goes_through_map_layers_and_toggles_each(pad):
    lua, ns = pad
    G, P, st = ns.GPS, ns.Pad, ns.settings.gps
    same = lua.eval("rawequal")
    _press(lua, "PAD4")  # (Y: the map menu)
    G.LayoutQuick()
    _frames(lua)
    assert P.MenuOpen()
    grp = G.groupOf.mapLayers
    # up the column to Map Layers: the third, where Quests was (Search Places, Quick Find, then it)
    assert same(P.focus, P.MenuButtons()[1])
    _press(lua, "PADDUP")
    _press(lua, "PADDUP")
    assert same(P.focus, grp.button)
    _press(lua, "PAD1")  # (A: its buttons out, the focus on the first)
    assert same(G.OpenGroupSlot(), grp) and same(P.focus, _quick(G, "layers_route").button)
    _press(lua, "PADDRIGHT")  # (along them: Travel)
    travel = _quick(G, "layers_travel")
    assert same(P.focus, travel.button)
    _press(lua, "PAD1")  # (A: Travel's toggles out, the focus on the first: Flight masters)
    assert same(G.OpenSubSlot(), travel)
    assert [same(b, _quick(G, "layer_" + lid).button) for b, lid in
            zip(P.MenuButtons().values(), G.LAYER_GROUPS[2].layers.values())] == [True] * 5
    assert same(P.focus, _quick(G, "layer_taxi").button)
    _press(lua, "PADDUP")
    assert same(P.focus, _quick(G, "layer_docks").button)
    _press(lua, "PAD1")  # (A: the docks hidden, the toggles still out, the focus where it was)
    assert st.layerDocks is False and same(G.OpenSubSlot(), travel) and same(P.focus, _quick(G, "layer_docks").button)
    assert not _lit(_quick(G, "layer_docks"))
    _press(lua, "PAD1")  # (A again: shown)
    assert st.layerDocks is True and _lit(_quick(G, "layer_docks"))
    _press(lua, "PAD2")  # (B: back to Travel, Map Layers' buttons still out)
    assert not G.OpenSubSlot() and same(G.OpenGroupSlot(), grp) and same(P.focus, travel.button)
    _press(lua, "PAD2")  # (B: back to Map Layers)
    assert not G.OpenGroupSlot() and same(P.focus, grp.button) and P.MenuOpen()
    _press(lua, "PAD2")  # (B: the menu shut)
    assert not P.MenuOpen()


@pytest.mark.parametrize("poi, docks", [(False, False), (True, True)])
def test_the_docks_stay_hidden_where_points_of_interest_hid_them(poi, docks):
    # (InitDB's docks142: before 1.4.2 the docks showed with Points of interest, turned off they were hidden; their own
    # layer since, off once for those players, in every profile; on for everyone else)
    pytest.importorskip("lupa.lua51")
    from azerothgps.gameharness import start
    p = "true" if poi else "false"
    lua, ns = start(saved="AzerothGPSDB = { settings = { gps = { poiPoi = %s } }, profiles = { Alt = { gps = { poiPoi = %s } } } }"
                    % (p, p))
    assert ns.settings.gps.layerDocks is docks
    assert ns.db.profiles.Alt.gps.layerDocks is (False if not poi else None)  # (a profile: its defaults when it's used)
    assert ns.db.docks142 is True
    ns.settings.gps.layerDocks = True  # (turned back on: not put back off again by a later login's InitDB)
    assert ns.GPS.LayerOn("docks")
