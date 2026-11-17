"""How far out each kind of map icon still shows (asked 2026-11-14: "Add sliders for Map icons for how far out their
icons are rendered like ore/herbs, city locations, custom pins, cave entrances, etc"): GPSFrame's G.IconShown, a
setting per kind in yards to the map's edge at the reference size, its default the zoom the kind went at before."""

import pytest

from test_atlas import _seamless


def _herb_and_pin(lua, ns):
    lua.execute("""
      local L = AGPS_NS.Layers
      local x, y = L.MapToWorld(1420, 0.5, 0.5)
      AGPS_POS = { x, y, 0 }
      L.AddNode(0, x + 40, y, "Peacebloom", "herb")
      AGPS_NS.Pins.Add({ level = 0, x = x - 40, y = y, name = "Far Pin" })
    """)
    st = ns.settings.gps
    st.layerHerbs = True
    st.showCustomPins = True


def _shown(lua, ns, zoom):
    G, st = ns.GPS, ns.settings.gps
    st.zoom = zoom * G.ZoomScale()
    G.Redraw()
    lua.execute("AGPS_T = (AGPS_T or 0) + 3")
    G.Update()
    ws = [w for w in lua.eval("AGPS_WIDGETS").values() if w._shown and w._kind == "Button"]
    return (G.shownView, sum(1 for w in ws if w.name == "Peacebloom"), sum(1 for w in ws if w.name == "Far Pin"))


def test_the_defaults_are_the_zooms_the_icons_went_at_before():
    lua, ns = _seamless()
    G, D = ns.GPS, ns.DEFAULTS.gps
    assert {k: D[key] for k, key in G.ICON_YD_KEYS.items()} == {
        "taxi": G.ICON_YD_ALWAYS, "poi": "stage", "quests": G.SEAM_QUESTS_YD, "city": "stage",
        "instances": G.ICON_YD_ALWAYS, "caves": "stage", "herbs": "stage", "ore": "stage", "pins": G.ICON_YD_ALWAYS}
    assert G.ICON_YD_RANGE[1] < G.SEAM_QUESTS_YD < G.ICON_YD_RANGE[2] == G.ICON_YD_ALWAYS
    _herb_and_pin(lua, ns)
    view, herbs, pins = _shown(lua, ns, 250)  # (the terrain alone)
    assert not view.seamFar and herbs == 1 and pins == 1
    view, herbs, pins = _shown(lua, ns, 1300)  # (the world stage: the herbs went, the pins stayed)
    assert view.seamFar and herbs == 0 and pins == 1
    # (the slider shows the world stage's yards on the seamless map, always in the other styles)
    assert G.IconYd("herbs") == pytest.approx(G.SEAM_ICONS_FEW * G.SeamShare())
    assert G.IconYd("pins") == G.ICON_YD_ALWAYS and G.IconYd("quests") == G.SEAM_QUESTS_YD


def test_moving_a_slider_changes_whether_that_kinds_icons_are_drawn():
    lua, ns = _seamless()
    G, st = ns.GPS, ns.settings.gps
    _herb_and_pin(lua, ns)
    try:
        # (in closer than the world stage: the herbs go past 200 yd, the pins stay)
        st.iconYdHerbs = 200
        view, herbs, pins = _shown(lua, ns, 250)
        assert not view.seamFar and herbs == 0 and pins == 1
        view, herbs, pins = _shown(lua, ns, 150)
        assert herbs == 1 and pins == 1
        # (further out than it: the herbs on the world stage too, at the top notch at every zoom)
        st.iconYdHerbs = G.ICON_YD_ALWAYS
        view, herbs, pins = _shown(lua, ns, 1300)
        assert view.seamFar and herbs == 1
        # (the pins, always before: gone past theirs)
        st.iconYdPins = 200
        view, herbs, pins = _shown(lua, ns, 250)
        assert herbs == 1 and pins == 0
        # (the kinds' other icons untouched: ore past its own zoom only)
        st.iconYdOre = 100
        assert G.IconKinds(250 * G.ZoomScale(), False)["herbs"] is True
        assert G.IconKinds(250 * G.ZoomScale(), False)["ore"] is False
    finally:
        for key in G.ICON_YD_KEYS.values():
            st[key] = None


def test_the_yards_are_at_the_reference_size_as_in_the_games_world_map():
    """A bigger map (the game's world map window) shows more at a zoom: the setting's yards are at the reference size,
    as G.InteriorZoomOK's, so an icon goes at the same scale on either map."""
    lua, ns = _seamless()
    G, st = ns.GPS, ns.settings.gps
    st.iconYdCaves = 300
    lua.execute("AGPS_ZS = AGPS_NS.GPS.ZoomScale AGPS_NS.GPS.ZoomScale = function() return 2.5 end")
    try:
        assert G.IconShown("caves", 300 * 2.5, False) is True
        assert G.IconShown("caves", 301 * 2.5, False) is False
        assert G.IconShown("caves", 500, False) is True  # (500 yd on the big map: 200 at the reference size)
    finally:
        lua.execute("AGPS_NS.GPS.ZoomScale = AGPS_ZS")
        st.iconYdCaves = None


def test_in_the_terrain_style_the_world_stages_kinds_show_at_every_zoom_by_default():
    lua, ns = _seamless(on=False)
    G = ns.GPS
    assert not G.Seamless()
    _herb_and_pin(lua, ns)
    view, herbs, pins = _shown(lua, ns, 2000)
    assert not view.seamFar and herbs == 1 and pins == 1
    assert G.IconYd("herbs") == G.ICON_YD_ALWAYS
