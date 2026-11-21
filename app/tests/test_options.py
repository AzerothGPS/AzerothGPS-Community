"""The options window's layout (1.2.0, asked 2026-11-10: "an overhaul on the organization of options to be as intuitive
as possible"; docs/options-1.2.0.md): the pages and their order, every setting on one page with one control, the old
page ids still opening a page, dependent options gray while their parent is off, the pages' heights for scrolling, and
the Help page's tutorial sections (Options.RegisterHelpSection)."""

import math
import re
from pathlib import Path

import pytest

ADDON = Path(__file__).resolve().parents[2] / "addon" / "AzerothGPS"

# The pages, in the list's order: id (what O.ShowPage and API.ShowOptions take) and the name shown in English.
PAGES = [("General", "General"), ("Map", "Map"), ("Layers", "Map icons"), ("Minimap", "Minimap"), ("Window", "GPS Map"),
         ("Opacity", "Opacity"), ("Routing", "Routing"),
         ("Directions", "Directions"), ("Quick buttons", "Keys and buttons"), ("Controller", "Controller"),
         ("Performance", "Performance"),
         ("Profiles", "Profiles"), ("Tools", "Tools"), ("Help", "Help")]
# The ids before 1.2.0's reorganization: each still opens a page (other code and companion addons ask for them).
OLD_IDS = ["General", "Performance", "Opacity", "Routing", "Directions", "Map", "Window", "Quick buttons", "Tools",
           "Help improve", "Minimap"]  # ("Minimap": a page of 1.2.0's first layout, merged into Map 2026-11-10)
# Every setting that had a control on an options page before the reorganization (1.1.17 + 1.2.0's merged features).
BEFORE = """shown locked windowFrame reopenFollow approachZoom rotate size width lockSize freeSize keyBlockedInCombat
distanceUnits minimap.hide searchCommonNpcs hz rerouteSeconds stopsAhead gentleBackground arrowHz alpha
fadeMoving movingAlpha clickThroughMoving clickThroughCombat combatHideMap combatAlpha combatHideArrow arrowCombatAlpha
avoidHighZones useFlights questZoneOnly useHearthstone useTeleports avoidHostile roadTolerance fastestOrder
cityKeepOrder navCloseClears acceptWay acceptMapPins acceptShared arrow arrowLocked questing arrowPx arrowBg dirShown
dirStopsOnly dirTextScale dirBg arrowSnap arrowSide terrainZoomOut interiors style seamExploredOnly poiTaxi poiPoi
poiLabels layerQuests showParty minimapRoute minimapIcons minimapShape layerQuestAreas layerHerbs layerOre
layerInstances layerCaves showCustomPins otherAddonPins replaceMinimap replaceMinimapCollapseOnMove
replaceMinimapCollapseOnCombat replaceMinimapSize windowTint windowButtons windowClose routeColor arrivalEffect charm
charmSwing devTools recordHint pinning copyRoads copyWalls copyRoutes copyPins""".split()
# (askToSave, "Remind me to save": removed with the map's Save and Dismiss buttons, asked 2026-11-17)
# Settings that were a slash command only (or the Quick buttons page's "On" column only) and have a control now.
NEW = ["arrowEase", "allowSwim", "mapEditIdle", "language", "layerCity", "showRoads", "showWalls", "useWorldMap", "escClosesMap", "replaceMinimapIdle", "questAutoReroute", "quietChat",
       "questPickRoute", "seamTerrainYd", "seamContinentAt", "seamWorldAt", "seamTerrainBlend",
       "seamContinentBlend", "seamWorldBlend", "interiorZoomYd", "roundIcons", "interiorHoldSec", "iconSize",
       # (asked 2026-11-14: how far out each kind of icon shows, GPSFrame's G.IconShown)
       "iconYdQuests", "iconYdTaxi", "iconYdPoi", "iconYdCity", "iconYdInstances", "iconYdCaves", "iconYdHerbs",
       "iconYdOre", "iconYdPins",
       "replaceMinimapKeepSquare",
       "flightMapRing",  # (asked 2026-11-17: the route's flight ringed on the flight map)
       # (1.3.6: pause routing when not following it, Performance)
       "autoPauseRouting", "autoPauseSeconds",
       "stutterPause",  # (1.3.9: the stutter watch, its own option)
       "layerQuestAreasMinimap",
       "padControl", "padLegend",  # (2026-11-16: controller support, Pad.lua)  # (asked 2026-11-15: quest areas on the map and on the minimap apart)
       "showCoords",  # (asked 2026-11-17: hide the map's X, Y line)
       "replaceMinimapRoute",  # (asked 2026-11-17: the route off the minimap square)
       "replaceMinimapResume",  # (1.3.9: a Resume button on the minimap square while paused)
       "navPanelWidth", "navPanelAlign", "navPanelDetached",  # (1.3.9: the route panel's width, side, own window)
       "navPanelHideButtons", "navPanelAlpha", "navPanelLocked", "navPanelWrap",  # (1.3.9: detached, its buttons hidden and its background's opacity)
       "dirLocked",  # (1.3.9: the directions text's own lock, apart from the arrow's)
       "importKeepOrder",  # (1.3.9: imports routed in the order listed; the Import and Share window's box too)
       "questTrackedOnly",  # (1.3.10: the quest route from the tracked quests only, Questie's tracker's or the game's)
       "routeSlopeShade"]  # (Kooki3z 2026-11-20: the route lighter uphill, darker downhill)
# Where each setting's control is: the page a player would look on.
HOME = {
    "General": "shown showCoords distanceUnits language quietChat searchCommonNpcs",
    # (asked 2026-11-16: "add a new Controller section and make a keybinding list for each map control")
    "Controller": "padControl padLegend",
    # (asked 2026-11-10: "4 different map pages... maybe reduce to 2": the map itself, its icons, and its window)
    "Map": "style seamExploredOnly seamTerrainYd seamTerrainBlend seamContinentAt seamContinentBlend seamWorldAt "
           "seamWorldBlend interiorZoomYd interiorHoldSec routeColor routeSlopeShade rotate approachZoom reopenFollow terrainZoomOut interiors "
           "useWorldMap escClosesMap",
    # (2026-11-19: a Minimap page again, the GPS map in its place and the game's own)
    "Minimap": "replaceMinimap replaceMinimapSize replaceMinimapCollapseOnMove replaceMinimapCollapseOnCombat "
               "replaceMinimapIdle replaceMinimapKeepSquare replaceMinimapRoute replaceMinimapResume "
               "minimap.hide minimapRoute minimapIcons minimapShape",
    "Window": "locked size width lockSize freeSize navPanelWidth navPanelAlign navPanelDetached navPanelHideButtons "
              "navPanelAlpha navPanelWrap navPanelLocked windowFrame windowTint "
              "windowClose windowButtons charm charmSwing arrivalEffect",
    "Layers": "iconSize roundIcons layerQuests layerQuestAreas layerQuestAreasMinimap poiTaxi poiPoi poiLabels layerCity layerInstances layerCaves layerHerbs "
              "layerOre showCustomPins otherAddonPins showParty iconYdQuests iconYdTaxi iconYdPoi iconYdCity iconYdInstances "
              "iconYdCaves iconYdHerbs iconYdOre iconYdPins",
    "Opacity": "alpha fadeMoving movingAlpha combatHideMap combatAlpha combatHideArrow arrowCombatAlpha "
               "clickThroughMoving clickThroughCombat",
    "Routing": "useFlights flightMapRing useHearthstone useTeleports avoidHighZones avoidHostile allowSwim roadTolerance fastestOrder "
               "cityKeepOrder importKeepOrder questZoneOnly questTrackedOnly questAutoReroute questPickRoute navCloseClears acceptWay acceptMapPins acceptShared",
    "Directions": "arrow arrowLocked arrowEase arrowPx arrowBg dirShown dirLocked dirStopsOnly arrowSnap arrowSide dirTextScale dirBg "
                  "questing",
    "Quick buttons": "keyBlockedInCombat",  # (2026-11-19: the keys with the buttons)
    "Performance": "hz rerouteSeconds stopsAhead autoPauseRouting autoPauseSeconds stutterPause gentleBackground arrowHz",
    "Tools": "devTools mapEditIdle recordHint showRoads showWalls pinning",
    "Help": "copyRoads copyWalls copyRoutes copyPins",
}
# The room a page has in the window before it scrolls (the window 560 tall, less its title, footer and margins).
VIEW_H = 480


def _start():
    pytest.importorskip("lupa.lua51")
    from azerothgps.gameharness import start
    return start()


@pytest.fixture(scope="module")
def game():
    lua, ns = _start()
    ns.Options.Show()
    return lua, ns


def _controls(ns, mirrors=False):
    return [c for c in ns.Options.settingControls.values() if mirrors or not c.mirror]


def test_the_pages_and_their_order(game):
    lua, ns = game
    O = ns.Options
    assert O.builtInPages == len(PAGES)
    assert {i: p.index for i, p in O.pages.items()} == {pid: n for n, (pid, _) in enumerate(PAGES, 1)}
    ws = lua.eval("AGPS_WIDGETS")
    ws = [ws[i] for i in range(1, len(ws) + 1)]
    names = [name for _, name in PAGES]
    # (the list on the left: a button per page, its name a font string on it)
    tabs = [str(w._text) for w in ws if w._kind == "FontString" and w._parent and w._parent._kind == "Button"
            and w._parent.id is not None and w._parent.selected is not None]
    assert tabs == names


def test_every_setting_has_one_control_on_the_page_it_belongs_to(game):
    lua, ns = game
    found = {}
    for c in _controls(ns):
        found.setdefault(c.key, []).append(c.page)
    # none lost: every setting with a control before still has one, and the new ones
    assert not [k for k in BEFORE + NEW if k not in found]
    # none doubled, and each on the page it's listed for
    assert not {k: p for k, p in found.items() if len(p) != 1}
    home = {k: page for page, keys in HOME.items() for k in keys.split()}
    assert {k: p[0] for k, p in found.items()} == home
    assert sorted(home) == sorted(BEFORE + NEW)
    # the second controls kept on purpose: the Quick buttons page's "On" column, for buttons that are a setting
    mirrors = sorted((c.key, c.page) for c in ns.Options.settingControls.values() if c.mirror)
    assert mirrors == [("layerCity", "Quick buttons"), ("useHearthstone", "Quick buttons")]


def test_every_setting_the_options_change_is_named_for_its_control(game):
    # (a control added later without `Key("...")` before it: caught here, so the check above keeps meaning something)
    lua, ns = game
    src = (ADDON / "Options.lua").read_text(encoding="utf-8")
    pages = src[src.index("Page(L[\"General\"], nil, \"General\")"):src.index("-- Companion addons' pages")]
    set_in_code = set(re.findall(r"GPS\(\)\.(\w+) = ", pages)) | {"minimap.hide", "language"}
    known = {c.key for c in _controls(ns, mirrors=True)}
    # (`quick`: the Quick buttons table, a place per button, not a setting with a control of its own;
    # `seamExploredOnly` and `style` are set through their own functions)
    assert set_in_code - known == {"quick"}
    assert known - set_in_code == {"style", "seamExploredOnly", "stopsAhead", "copyRoads", "copyWalls", "copyRoutes",
                                   "copyPins", "layerCity"} - set_in_code
    # and every one of them is a real setting: in the defaults (or the two kept outside `gps`)
    defaults = set(ns.DEFAULTS.gps.keys())
    assert known - defaults == {"minimap.hide", "language", "width", "dirBg",  # (unset until the player sets them)
                                "seamTerrainYd"}


def test_every_old_page_id_still_opens_a_page(game):
    lua, ns = game
    O, A = ns.Options, lua.globals().AzerothGPS
    for pid in OLD_IDS:
        assert O.ShowPage(pid) is True, pid
        now = O.PAGE_ALIASES[pid] or pid
        shown = [i for i, p in O.pages.items() if p.scroll._shown]
        assert shown == [now], (pid, shown)
        assert A.ShowOptions(pid) is True, pid
    assert O.PAGE_ALIASES["Help improve"] == "Help"
    for pid, _ in PAGES:
        assert O.ShowPage(pid) is True, pid
    assert O.ShowPage("No Such Page") is False
    O.ShowPage("General")


# (the dependent option, its parent's setting, the parent's value that turns it off)
DEPENDENTS = [
    ("replaceMinimapSize", "replaceMinimap", False), ("replaceMinimapCollapseOnMove", "replaceMinimap", False),
    ("replaceMinimapCollapseOnCombat", "replaceMinimap", False), ("replaceMinimapIdle", "replaceMinimap", False),
    ("replaceMinimapKeepSquare", "replaceMinimap", False), ("replaceMinimapRoute", "replaceMinimap", False),
    ("movingAlpha", "fadeMoving", False), ("combatAlpha", "combatHideMap", True),
    ("arrowCombatAlpha", "combatHideArrow", True),
    ("lockSize", "locked", True), ("freeSize", "locked", True), ("freeSize", "lockSize", True),
    ("windowTint", "windowFrame", False), ("windowClose", "windowFrame", False), ("charm", "windowFrame", False),
    ("charmSwing", "windowFrame", False), ("charmSwing", "charm", "none"),
    ("cityKeepOrder", "fastestOrder", False), ("importKeepOrder", "fastestOrder", False), ("layerQuestAreas", "layerQuests", False),
    ("layerQuestAreasMinimap", "layerQuests", False),
    ("seamExploredOnly", "style", "minimap"), ("seamTerrainYd", "style", "minimap"),
    ("seamContinentAt", "style", "zone"), ("seamWorldAt", "style", "nospoiler"),
    ("seamTerrainBlend", "style", "minimap"), ("seamContinentBlend", "style", "zone"), ("seamWorldBlend", "style", "minimap"),
    ("interiorZoomYd", "style", "zone"), ("interiorHoldSec", "style", "zone"),
    ("arrowLocked", "arrow", False), ("arrowEase", "arrow", False), ("arrowPx", "arrow", False), ("arrowBg", "arrow", False),
    ("dirShown", "arrow", False), ("dirStopsOnly", "dirShown", False),
    ("dirLocked", "dirShown", False), ("dirLocked", "arrow", False), ("dirStopsOnly", "arrow", False),
    ("arrowSnap", "dirShown", False), ("dirTextScale", "dirShown", False), ("dirBg", "dirShown", False),
    ("arrowSide", "dirShown", False),
    # (asked 2026-11-17: Arrow side's Hide; the arrow's own options gray, and the text can't be hidden too)
    ("arrowPx", "arrowSide", "hide"), ("arrowBg", "arrowSide", "hide"), ("arrowSnap", "arrowSide", "hide"),
    ("dirShown", "arrowSide", "hide"),
    ("iconYdQuests", "layerQuests", False), ("iconYdTaxi", "poiTaxi", False), ("iconYdPoi", "poiPoi", False),
    ("iconYdCity", "layerCity", False), ("iconYdInstances", "layerInstances", False), ("iconYdCaves", "layerCaves", False),
    ("iconYdHerbs", "layerHerbs", False), ("iconYdOre", "layerOre", False), ("iconYdPins", "showCustomPins", False),
    # (1.3.9: the detached route panel's own looks)
    ("navPanelHideButtons", "navPanelDetached", False), ("navPanelAlpha", "navPanelDetached", False),
    ("navPanelLocked", "navPanelDetached", False), ("navPanelWrap", "navPanelDetached", False),
]
# (the parents' values with every dependent on)
ALL_ON = {"replaceMinimap": True, "fadeMoving": True, "combatHideMap": False, "combatHideArrow": False,
          "locked": False, "lockSize": False, "windowFrame": True, "charm": "thunderfury", "fastestOrder": True,
          "layerQuests": True, "style": "seamless", "arrow": True, "dirShown": True, "arrowSnap": True, "arrowSide": "left",
          "poiTaxi": True, "poiPoi": True, "layerCity": True, "layerInstances": True, "layerCaves": True,
          "layerHerbs": True, "layerOre": True, "showCustomPins": True, "navPanelDetached": True}


def test_a_dependent_option_is_gray_while_its_parent_is_off(game):
    lua, ns = game
    O, st = ns.Options, ns.settings.gps
    by_key = {c.key: c.control for c in _controls(ns)}
    charm = next(iter(ns.Looks.Charms().values())).key  # (a charm there is)
    on = dict(ALL_ON, charm=charm)
    saved = {k: st[k] for k in on}
    try:
        for k, v in on.items():
            st[k] = v
        O.Refresh()
        for child, _, _ in DEPENDENTS:
            assert by_key[child].agpsOn is True, child
        for child, parent, off in DEPENDENTS:
            st[parent] = off
            O.Refresh()
            assert by_key[child].agpsOn is False, (child, parent)
            st[parent] = on[parent]
        O.Refresh()
        # a checkbox says so the game's way too: disabled, its label in the disabled font
        cb = by_key["cityKeepOrder"]
        st.fastestOrder = False
        O.Refresh()
        assert cb._enabled is False
        st.fastestOrder = True
        O.Refresh()
        assert cb._enabled is True
        # an option with no parent is never grayed
        assert by_key["shown"].agpsOn is None and by_key["useFlights"].agpsOn is None
    finally:
        for k, v in saved.items():
            st[k] = v
        O.Refresh()


def test_dependent_options_sit_indented_under_their_parent(game):
    lua, ns = game
    by_key = {c.key: c.control for c in _controls(ns)}
    x = lambda key: by_key[key]._pt[2]  # noqa: E731  (SetPoint("TOPLEFT", x, y))
    y = lambda key: by_key[key]._pt[3]  # noqa: E731
    for child, parent in (("seamExploredOnly", "rotate"), ("seamTerrainYd", "rotate"),
                          ("seamContinentAt", "rotate"), ("seamWorldAt", "rotate"), ("seamTerrainBlend", "rotate"),
                          ("seamContinentBlend", "rotate"), ("seamWorldBlend", "rotate"), ("interiorZoomYd", "rotate"),
                          ("interiorHoldSec", "rotate"),
                          ("layerQuestAreas", "layerQuests"), ("replaceMinimapCollapseOnMove", "replaceMinimap"),
                          ("freeSize", "lockSize"), ("charmSwing", "windowFrame"), ("cityKeepOrder", "fastestOrder"),
                          ("arrowLocked", "arrow"), ("dirLocked", "dirShown"), ("dirStopsOnly", "dirShown")):
        assert x(child) == x(parent) + 20, child
    for child, parent in (("layerQuestAreas", "layerQuests"), ("replaceMinimapCollapseOnMove", "replaceMinimap"),
                          ("cityKeepOrder", "fastestOrder"), ("arrowLocked", "arrow"), ("dirLocked", "dirShown"),
                          ("dirStopsOnly", "dirShown")):
        assert y(child) < y(parent), child  # (below it)


def test_each_pages_height_is_its_content_and_a_longer_one_scrolls(game):
    lua, ns = game
    O = ns.Options
    heights = {pid: p.child._h for pid, p in O.pages.items()}
    assert all(h and h > 60 for h in heights.values()), heights
    # no control is placed below its page's height (it would be cut off, with no way to scroll to it)
    for c in _controls(ns, mirrors=True):
        w = c.control
        if w._pt is None:
            w = w[1]  # (radio buttons: the first one)
        if c.page in ("Quick buttons", "Help") or c.key in ("width", "questing"):
            continue  # (rows in their own frames, placed from those; a control hung beside another)
        assert -w._pt[3] + 26 <= heights[c.page], (c.key, c.page)
    # the pages meant to fit without scrolling do (by the stand-in's text sizes: one line a note)
    # (Map and Map icons: a little over a screen since they took the minimap's page; General since round icons went on
    # it, asked 2026-11-14: "an option in general")
    for pid in ("Opacity",):
        assert heights[pid] <= VIEW_H, (pid, heights[pid])
    # a scroll bar only on a page longer than its room in the window
    lua.execute("""
      for _, p in pairs(AGPS_NS.Options.pages) do
        p.scroll.GetHeight = function() return 480 end
        p.child.GetHeight = function(s) return s._h end
      end
    """)
    try:
        for pid, _ in PAGES:
            O.ShowPage(pid)
            p = O.pages[pid]
            assert p.scroll.ScrollBar._shown is (heights[pid] > VIEW_H + 1), pid
    finally:
        lua.execute("""
          for _, p in pairs(AGPS_NS.Options.pages) do p.scroll.GetHeight, p.child.GetHeight = nil, nil end
        """)
        O.ShowPage("General")


def test_the_help_page_has_the_news_the_links_and_what_help_improve_had(game):
    lua, ns = game
    O = ns.Options
    ws = lua.eval("AGPS_WIDGETS")
    texts = [str(w._text) for w in ws.values() if w._text]
    for label in ("What's new in 1.3", "Commands and links", "Show Commands", "Help improve AzerothGPS",
                  "How to share...", "Copy Map Data...", "What Copy Map Data... includes", "Thanks"):
        assert label in texts, label
    news = [str(line) for line in O.WHATS_NEW.values()]
    assert len(news) >= 3 and all(line in texts for line in news)
    assert O.siteBox._text == O.SITE_URL == "https://azerothgps.com" and O.discordBox._text == O.DISCORD_URL
    assert str(O.creditBox._text).startswith("https://www.curseforge.com/")  # (the Thanks section's address)
    # Show Commands prints the slash commands, as /agps help
    printed = []
    lua.globals().AGPS_PRINTED = printed.append
    lua.execute("AGPS_OLD_PRINT = AGPS_NS.Print AGPS_NS.Print = function(...) AGPS_PRINTED((...)) end")
    try:
        b = next(w for w in ws.values() if w._kind == "Button" and w._text == "Show Commands")
        b._scripts.OnClick(b)
    finally:
        lua.execute("AGPS_NS.Print = AGPS_OLD_PRINT")
    assert any("/agps replace" in str(line) for line in printed) and len(printed) > 20



def test_the_help_pages_debug_log_is_exported_without_a_reload(game):
    # (asked 2026-11-13: a player ticks Debug log, does what goes wrong, and exports the log to send; in memory only)
    lua, ns = game
    O, D = ns.Options, ns.Debug
    ws = lua.eval("AGPS_WIDGETS")
    texts = [str(w._text) for w in ws.values() if w._text]
    assert "Debugging" in texts and "Debug log" in texts
    assert O.feedbackBox._text == O.FEEDBACK_URL == "https://azerothgps.com/feedback/#report"
    D.Log("before", lua.eval("{ x = 1 }"))  # (off: nothing noted)
    assert len(D.log) == 0
    cb = O.debugCheck
    cb.SetChecked(cb, True)
    cb._scripts.OnClick(cb)
    try:
        assert D.On() is True
        D.Log("gathered", lua.eval("{ name = 'Copper Vein', x = -1059.04, added = true }"))
        ns.GPS.LogError("test", "boom")
        # (a line a second while on: the addon's work in it and what took most of it; CPU spikes)
        D.Second()
        lua.eval("function(ns) ns.PerfAdd('redraw', 12) ns.PerfAdd('minimap icons', 3) end")(ns)
        D.Second()
        b = next(w for w in ws.values() if w._kind == "Button" and w._text == "Export Debug Log...")
        b._scripts.OnClick(b)
        win = lua.eval("_G.AzerothGPSDebugExport")
        assert win is not None and win._shown
        text = str(win.edit._text)
        assert text.startswith("AzerothGPS debug log" + chr(10))
        assert "gathered added=true name=Copper Vein x=-1059.0" in text
        assert "error err=boom what=test" in text and "errors (" in text and "settings: " in text
        assert "where: " in text
        assert "second fps=60 ms=15.0 top=redraw 12.0, minimap icons 3.0" in text
        assert "performance (" in text and "  redraw: " in text
        # (the window closed: the log off and its box unticked, the log kept; asked 2026-11-13)
        win.Hide(win)
        win._scripts.OnHide(win)  # (the mock runs no OnHide: the game does)
        assert D.On() is False and not cb.GetChecked(cb) and len(D.log) > 0
    finally:
        cb.SetChecked(cb, False)
        cb._scripts.OnClick(cb)
    assert D.On() is False and len(D.log) > 0  # (off: the log stays, to export)
    ns.db.errors = lua.eval("{}")


def _help_state(O):
    h = O.help
    return h.host._shown, h.host._h, h.rest._pts.TOPLEFT[5], h.page._h


def test_the_help_page_hosts_a_registered_tutorial_section():
    # (for the in-game tutorial: its replay list goes under Help's "Tutorial" header) a section registered before the
    # window is built is built with it; one registered after, at once; the same id again builds it again; the rest of
    # the page moves down by the sections' height; an error stays in its section
    lua, ns = _start()
    O = ns.Options
    lua.execute("""
      AGPS_TUT = { runs = 0, rows = 2 }
      AGPS_TUT.build = function(ui)
        AGPS_TUT.runs = AGPS_TUT.runs + 1
        AGPS_TUT.page = ui.page
        ui.note("Watch a lesson again:")
        for i = 1, AGPS_TUT.rows do ui.button("Replay " .. i, 150, function() AGPS_TUT.clicked = i end) end
        ui.check("Show tips", "tip", function() return AGPS_TUT.tips end, function(v) AGPS_TUT.tips = v end)
      end
    """)
    T = lua.eval("AGPS_TUT")
    assert O.RegisterHelpSection("tutorial", T.build) is True
    assert O.RegisterHelpSection("bad", "not a function") is False
    assert T.runs == 0  # (not until the window is built)
    O.Show()
    assert T.runs == 1 and O.ShowPage("Help") is True
    host, page = O.HelpHost()
    same = lua.eval("rawequal")
    assert same(T.page._parent, host) and same(host._parent, page) and same(page, O.pages.Help.child)
    shown, host_h, rest_y, page_h = _help_state(O)
    sec = O.helpSections[1]
    assert shown is True and same(sec.frame, T.page) and sec.height == 20 + 2 * 28 + 26
    assert host_h == O.help.headH + sec.height and rest_y == O.help.top - host_h
    ws = lua.eval("AGPS_WIDGETS")
    head = [w for w in ws.values() if w._kind == "FontString" and w._text == "Tutorial" and same(w._parent, host)]
    assert len(head) == 1  # (the header, in the host: shown and hidden with it)
    replay = next(w for w in ws.values() if w._kind == "Button" and w._text == "Replay 2")
    assert same(replay._parent, T.page)
    replay._scripts.OnClick(replay)
    assert T.clicked == 2
    # its controls refresh with the window's
    T.tips = True
    O.Refresh()
    cb = next(w for w in ws.values() if w._kind == "FontString" and w._text == "Show tips")._parent
    assert cb._checked is True
    # the same id again: built again (a longer list), the old frame hidden, the page longer by it
    T.rows = 5
    old = T.page
    assert O.RegisterHelpSection("tutorial", T.build) is True
    assert T.runs == 2 and old._shown is False and not same(T.page, old) and len(list(O.helpSections.values())) == 1
    shown2, host_h2, rest_y2, page_h2 = _help_state(O)
    assert host_h2 == host_h + 3 * 28 and rest_y2 == rest_y - 3 * 28 and page_h2 == page_h + 3 * 28
    # a second section, added with the window built, goes under the first; one that fails doesn't stop the page
    lua.execute("AGPS_TUT.second = function(ui) ui.note('More') end AGPS_TUT.broken = function(ui) error('boom') end")
    assert O.RegisterHelpSection("more", T.second) is True and O.RegisterHelpSection("broken", T.broken) is True
    second = O.helpSections[2]
    assert second.frame._pts.TOPLEFT[5] == -(O.help.headH + O.helpSections[1].height)
    assert _help_state(O)[1] == host_h2 + second.height + O.helpSections[3].height
    assert O.ShowPage("Help") is True and O.ShowPage("Help improve") is True


def test_the_tutorial_header_is_hidden_without_a_section():
    # (the tutorial registers its own section at login, Tutorial.lua: taken out here before the window is built)
    lua, ns = _start()
    O = ns.Options
    assert [str(e.id) for e in O.helpSections.values()] == ["tutorial"]
    lua.execute("AGPS_NS.Options.helpSections = {}")
    O.Show()
    shown, host_h, rest_y, page_h = _help_state(O)
    assert shown is False and rest_y == O.help.top and page_h == -O.help.top + O.help.restH + 16


def test_the_tutorial_header_shows_with_the_tutorials_own_section(game):
    lua, ns = game
    O = ns.Options
    assert [str(e.id) for e in O.helpSections.values()] == ["tutorial"]
    shown, host_h, rest_y, page_h = _help_state(O)
    assert shown is True and host_h == O.help.headH + O.helpSections[1].height and rest_y == O.help.top - host_h


def test_the_language_can_be_picked_in_the_options(game):
    # (1.2.0: /agps language's setting had no control) General > Language: the game's, or one of the addon's
    lua, ns = game
    O = ns.Options
    dd = next(c.control for c in _controls(ns) if c.key == "language")
    codes = [o.value for o in dd.options.values()]
    assert codes[0] == "auto" and sorted(codes[1:]) == sorted(ns.LOCALES.keys())
    before = ns.db.language
    try:
        assert list(lua.globals().AGPS_MENU(dd).values())[:3] == ["The game's language", "English", "Deutsch"]
        lua.globals().AGPS_PICK(dd, "Deutsch")
        assert ns.db.language == "deDE" and dd._choice == "Deutsch"
        lua.globals().AGPS_PICK(dd, "The game's language")
        assert ns.db.language is None and dd._choice == "The game's language"
    finally:
        ns.db.language = before


def test_a_changed_language_shows_an_apply_button_that_reloads(game):
    # (asked 2026-11-10: "for language selection, if changed add a Apply button to pop up if a /reload is required")
    lua, ns = game
    O = ns.Options
    was = ns.db.language
    try:
        ns.db.language = None if ns.loadedLanguage == "auto" else ns.loadedLanguage
        O.Apply()
        assert O.LanguagePending() is False and not O.languageApply._shown  # (the one loaded: nothing to apply)
        ns.db.language = "deDE" if ns.loadedLanguage != "deDE" else "frFR"
        O.Apply()
        assert O.LanguagePending() is True and O.languageApply._shown
        assert str(O.languageApply._text) == "Apply (Reload UI)"
        r = O.languageReload  # (the reload itself: a secure button over it, an addon's own click can't reload here)
        assert r is not None and r._attr.macrotext == "/reload"
    finally:
        ns.db.language = was
        O.Apply()
    assert not O.languageApply._shown


def test_the_map_window_and_game_minimap_options_say_where_they_apply(game):
    # (asked 2026-11-12: the world map option at the top of the Map page; the game's minimap options are the game's
    # minimap's, not the GPS map in its place; opacity, fading, hiding and turning are the GPS map's own window's,
    # not in the game's world map)
    lua, ns = game
    O, st = ns.Options, ns.settings.gps
    by_key = {c.key: c.control for c in _controls(ns)}
    top = lambda c: (c.control._pt or c.control[1]._pt)[3]  # noqa: E731  (radio buttons: the first one)
    on_map = sorted((c for c in _controls(ns) if c.page == "Map"), key=lambda c: -top(c))
    assert on_map[0].key == "useWorldMap"
    saved = {k: st[k] for k in ("useWorldMap", "replaceMinimap", "fadeMoving", "combatHideMap")}
    window = ("alpha", "fadeMoving", "movingAlpha", "combatHideMap", "combatAlpha", "rotate")
    game_mm = ("minimapRoute", "minimapIcons", "minimapShape")
    try:
        st.fadeMoving, st.combatHideMap = True, False
        st.useWorldMap, st.replaceMinimap = False, False
        O.Refresh()
        assert all(by_key[k].agpsOn is True for k in window + game_mm)
        st.useWorldMap = True
        O.Refresh()
        assert not [k for k in window if by_key[k].agpsOn is not False]
        assert by_key["clickThroughMoving"].agpsOn is None  # (the arrow's too: kept)
        st.replaceMinimap = True
        O.Refresh()
        assert not [k for k in game_mm if by_key[k].agpsOn is not False]
        assert by_key["minimap.hide"].agpsOn is None  # (the button goes round the square)
    finally:
        for k, v in saved.items():
            st[k] = v
        O.Refresh()


# The seamless map's stages' sliders (asked 2026-11-14: "sliders for adjusting the distance the map transitions from terrain
# to zone to world map like we did in the dev addon", then "zone map to world map doesn't change the distance the map
# fades ... a third one for the fade to world view ... a transition setting for each level"): GPSFrame's
# G.ApplySeamPlayer, the dev tools' knobs for the terrain and the art engine's own fades for the other two (test_atlas.py
# reads those on the map).
STAGE_KEYS = ["seamTerrainYd", "seamTerrainBlend", "seamContinentAt", "seamContinentBlend", "seamWorldAt", "seamWorldBlend"]


def _stage_sliders(ns):
    by_key = {c.key: c.control for c in _controls(ns)}
    return [by_key[k] for k in STAGE_KEYS]


def _move(holder, value):
    s = holder.slider
    s._scripts.OnValueChanged(s, value)


def _shipped(G):
    return (G.SEAM_SHARP_NOTCHES, G.SEAM_ART_NOTCHES, G.SEAM_TILES_NOTCHES, G.SEAM_WORLD_NOTCHES, G.SEAM_ART_IN[1],
            G.SEAM_ART_IN[2], G.SEAM_TILES_OUT[1], G.SEAM_TILES_OUT[2], G.SEAM_ICONS_FEW)


def _pair(t):
    return (t[1], t[2])


def _reset(ns):
    st = ns.settings.gps
    st.seamTerrainYd = None
    for k in STAGE_KEYS[1:]:
        st[k] = ns.DEFAULTS.gps[k]
    ns.Options.Apply()


def test_the_seamless_stage_settings_default_to_the_shipped_stages():
    lua, ns = _start()
    G, st = ns.GPS, ns.settings.gps
    # the defaults: where they're shipped (0 notches from it), each blend as long as shipped (1); the terrain's unset
    d = ns.DEFAULTS.gps
    assert (d.seamContinentAt, d.seamWorldAt, d.seamTerrainBlend, d.seamContinentBlend, d.seamWorldBlend) == (0, 0, 1, 1, 1)
    assert st.seamTerrainYd is None and "seamTerrainYd" not in ns.DEFAULTS.gps.keys()
    assert G.SEAM_SHARP_NOTCHES == G.SEAM_DEFAULTS.SEAM_SHARP_NOTCHES == -8
    assert G.SEAM_ART_NOTCHES == G.SEAM_TILES_NOTCHES == 3 and G.SEAM_WORLD_NOTCHES == 0
    assert round(G.SEAM_ART_IN[1]) == 305 and round(G.SEAM_TILES_OUT[2]) == 743
    assert G.SEAM_ICONS_FEW == G.SEAM_TILES_OUT[2]
    # nothing given to the art engine: its fades as written (test_atlas.py checks them number for number)
    assert ns.Atlas.STAGES is None
    assert tuple(G.SeamPlayerStages())[1:3] == (0, 0)
    # the fades' middles in yards at the reference size: the zones' map's at 6,082, the continents' at 12,163
    assert round(G.SeamFadeYards("zone")) == 6082 and round(G.SeamFadeYards("world")) == 12163
    # with nothing moved, applying the settings leaves the knobs as they are (a dev knob turned is kept)
    G.SetSeamKnob("SEAM_ART_NOTCHES", 3)
    ns.Options.Apply()
    assert G.SEAM_ART_NOTCHES == 3
    G.SetSeamKnob("SEAM_ART_NOTCHES", None)


def test_the_seamless_stage_sliders_gray_out_in_the_other_styles(game):
    lua, ns = game
    O, st = ns.Options, ns.settings.gps
    sliders = _stage_sliders(ns)
    saved = st["style"]
    try:
        for style, on in (("seamless", True), ("minimap", False), ("zone", False), ("nospoiler", False)):
            st["style"] = style
            O.Refresh()
            assert all(s.agpsOn is on for s in sliders), style
        st["style"] = "seamless"
        O.Refresh()
        assert [s.title._text for s in sliders] == [
            "Terrain to zone map", "Terrain transition", "Zone map to continent map", "Zone map transition",
            "Continent map to world map", "Continent map transition"]
        # the stages shown as the zoom in yards, the transitions as a share of the shipped blend
        terrain, tb, cont, cb, world, wb = sliders
        assert cont.slider._minmax[2] == 6 and world.slider._minmax[2] == 3
        assert (tb.slider._minmax[1], tb.slider._minmax[2]) == (0, 3)
    finally:
        st["style"] = saved
        O.Refresh()


def test_moving_the_terrain_sliders_moves_its_stage_and_blend(game):
    lua, ns = game
    G, st = ns.GPS, ns.settings.gps
    terrain, tb = _stage_sliders(ns)[:2]
    before = _shipped(G)
    try:
        # the terrain out 4 notches: the art in, the tiles out and the world stage with it
        _move(terrain, -4)
        assert st.seamTerrainYd == pytest.approx(1000 * 1.16 ** -4)
        assert G.SEAM_SHARP_NOTCHES == pytest.approx(-4)
        assert G.SEAM_ART_IN[1] == pytest.approx(1000 * 1.16 ** -4)
        assert G.SEAM_TILES_OUT[2] == pytest.approx(1000 * 1.16 ** 2)
        # its transition twice as long: the art in and the tiles out 6 notches each (3 shipped), from the same start
        _move(tb, 2)
        assert st.seamTerrainBlend == 2 and G.SEAM_ART_NOTCHES == 6 and G.SEAM_TILES_NOTCHES == 6
        assert G.SEAM_ART_IN[1] == pytest.approx(1000 * 1.16 ** -4)
        assert G.SEAM_TILES_OUT[2] == pytest.approx(1000 * 1.16 ** 8)
        # none: the terrain switches to the zones' map at once
        _move(tb, 0)
        assert G.SEAM_ART_NOTCHES == 0 and G.SEAM_TILES_NOTCHES == 0
        at = G.SEAM_ART_IN[1]
        assert tuple(G.ArtBlend(at * 0.999)) == (0, 1) and tuple(G.ArtBlend(at * 1.001)) == (1, 0)
    finally:
        _reset(ns)
    assert _shipped(G) == before


def test_the_seamless_stages_order_cannot_turn_round(game):
    lua, ns = game
    G, st = ns.GPS, ns.settings.gps
    O = ns.Options
    terrain, tb, cont, cb, world, wb = _stage_sliders(ns)
    try:
        st["style"] = "seamless"
        # the continents' fade pulled in past the zones' (5 notches apart as shipped): it's where the zones' is
        _move(world, -6)
        assert G.seamStage.world == pytest.approx(-math.log(2) / math.log(1.16))
        assert G.SeamFadeYards("world", G.seamStage.world) == pytest.approx(G.SeamFadeYards("zone"))
        # the terrain pushed out with a long blend: the zones' fade no closer in than the tiles' end
        _move(terrain, 4)
        _move(tb, 1.5)
        _move(cont, -4)
        assert G.SeamFadeYards("zone", G.seamStage.continent) == pytest.approx(G.SEAM_TILES_OUT[2])
        assert G.SeamFadeYards("world", G.seamStage.world) >= G.SeamFadeYards("zone", G.seamStage.continent) - 1e-6
        # and the sliders' least is where the stage before is now
        O.Refresh()
        least_c, least_w = G.SeamContinentLeast(), G.SeamWorldLeast(G.seamStage.continent)
        assert (cont.slider._minmax[1], world.slider._minmax[1]) == (pytest.approx(least_c), pytest.approx(least_w))
        # out of range: kept in it
        st.seamContinentAt, st.seamWorldAt, st.seamWorldBlend = 99, 99, -5
        O.Apply()
        assert (G.seamStage.continent, G.seamStage.world) == (6, 3)
        assert _pair(ns.Atlas.STAGES.world) == (pytest.approx(1.16 ** -3), 0)
    finally:
        _reset(ns)
    assert ns.Atlas.STAGES.zone is None and ns.Atlas.STAGES.world is None


def test_the_seamless_stages_reset_and_are_read_at_login(game):
    lua, ns = game
    G, st = ns.GPS, ns.settings.gps
    terrain, tb, cont, cb, world, wb = _stage_sliders(ns)
    st["style"] = "seamless"
    before = _shipped(G)
    _move(terrain, -6)
    _move(cb, 2)
    _move(world, 2)
    assert G.SEAM_SHARP_NOTCHES == pytest.approx(-6)
    assert _pair(ns.Atlas.STAGES.zone) == (1, 2) and _pair(ns.Atlas.STAGES.world) == (pytest.approx(1.16 ** -2), 1)
    # Reset to defaults: the terrain's unset, the rest their defaults, the shipped stages back
    reset = ns.Options.seamStagesReset
    assert reset._text == "Reset to defaults" and reset._enabled is True
    reset._scripts.OnClick(reset)
    assert st.seamTerrainYd is None and st.seamWorldAt == 0 and st.seamContinentBlend == 1
    assert _shipped(G) == before
    assert ns.Atlas.STAGES.zone is None and ns.Atlas.STAGES.world is None
    assert reset._enabled is False
    # saved in the profile's settings and read at login; the first world slider's setting let go
    saved = ("AzerothGPSDB = { settings = { gps = { seamTerrainYd = %r, seamContinentAt = 2, seamWorldBlend = 0.5, "
             "seamWorldYd = 3000 } } }" % (1000 * 1.16 ** -5))
    lua2, ns2 = _start_saved(saved)
    G2 = ns2.GPS
    assert G2.SEAM_SHARP_NOTCHES == pytest.approx(-5)
    assert G2.seamStage.continent == 2
    assert _pair(ns2.Atlas.STAGES.zone) == (pytest.approx(1.16 ** -2), 1)
    assert _pair(ns2.Atlas.STAGES.world) == (1, 0.5)
    assert ns2.settings.gps.seamWorldYd is None


def test_the_maps_reset_takes_the_inside_map_sliders_too(game):
    # (asked 2026-11-16, a screenshot: Options > Map's Reset to defaults grey with "Hold an inside map for" at 120 s)
    lua, ns = game
    O, st = ns.Options, ns.settings.gps
    st["style"] = "seamless"
    reset = O.seamStagesReset
    O.Refresh()
    assert reset._enabled is False
    for key, value in (("interiorHoldSec", 120), ("interiorZoomYd", 300)):
        st[key] = value
        O.Refresh()
        assert reset._enabled is True, key
        reset._scripts.OnClick(reset)
        O.Refresh()
        assert st[key] == ns.DEFAULTS.gps[key] and reset._enabled is False, key


def test_a_stage_sliders_range_change_never_saves_its_clamped_value(game):
    """#367: Reset to defaults left seamWorldAt at -0.17. The client clamps a slider when its range moves and fires
    OnValueChanged; the options' own range update must not leave that in the settings."""
    lua, ns = game
    G, st = ns.GPS, ns.settings.gps
    terrain, tb, cont, cb, world, wb = _stage_sliders(ns)
    st["style"] = "seamless"
    clamp = lua.eval("""function(s, cur)
      local old = s.SetMinMaxValues
      s._cur = cur -- (where the slider sits: past the range its new least gives)
      s.SetMinMaxValues = function(self, a, b)
        old(self, a, b)
        -- (the client: a value outside the new range is clamped to it, and that change fires OnValueChanged)
        local v = math.max(a, math.min(b, self._cur))
        if v ~= self._cur then self._cur = v; self._scripts.OnValueChanged(self, v) end
      end
    end""")
    clamp(cont.slider, -30)
    clamp(world.slider, -30)
    try:
        ns.Options.Refresh()
        assert st.seamContinentAt == 0 and st.seamWorldAt == 0
    finally:
        _reset(ns)


def _start_saved(saved):
    pytest.importorskip("lupa.lua51")
    from azerothgps.gameharness import start
    return start(saved=saved)


def test_search_places_hover_is_short_and_its_help_is_on_the_help_page(game):
    # (asked 2026-11-14: "the whole "Search Places" grey text should be moved somewhere into options, thats too much
    # text for a button hover") the button's tooltip: its name and one line; what it finds and the Pin button on Help
    lua, ns = game
    lines = lua.eval("{}")
    old = lua.eval("GameTooltip.AddLine")
    lua.globals().GameTooltip.AddLine = lua.eval("function(t) return function(self, text) t[#t + 1] = text end end")(lines)
    try:
        ns.GPS.searchButton._scripts.OnEnter(ns.GPS.searchButton)
    finally:
        lua.globals().GameTooltip.AddLine = old
    said = [str(lines[i]) for i in range(1, len(lines) + 1)]
    assert len(said) == 1 and not any(s.startswith("Finds:") for s in said), said
    ws = lua.eval("AGPS_WIDGETS")
    texts = [str(w._text) for w in ws.values() if w._text]
    assert any(t.startswith("Finds: towns and places") for t in texts)
    assert any(t.startswith("Pin beside an NPC") for t in texts)


def test_the_icon_distance_sliders_set_each_kinds_yards_and_reset():
    """Options > Map icons, How far out icons show (asked 2026-11-14): a slider a kind, in yards at the reference size
    (GPSFrame's G.IconYd), the top notch Always; each starts at the zoom its icons went at before; Reset puts them back."""
    lua, ns = _start()
    ns.Options.Show()
    O, G, st = ns.Options, ns.GPS, ns.settings.gps
    st["style"] = "seamless"
    by_key = {c.key: c.control for c in _controls(ns)}
    keys = list(G.ICON_YD_KEYS.values())
    assert len(keys) == 9 and all(by_key[k] for k in keys)
    assert tuple(G.ICON_YD_RANGE.values()) == (100, G.ICON_YD_ALWAYS, 100)
    assert tuple(by_key["iconYdPins"].slider._minmax.values()) == (100, G.ICON_YD_ALWAYS)
    O.Refresh()
    text = lambda key: str(by_key[key].valueText._text)  # noqa: E731
    yd = ns.Nav.FormatDistance
    assert text("iconYdPins") == "Always" and text("iconYdTaxi") == "Always" and text("iconYdInstances") == "Always"
    assert text("iconYdQuests") == yd(G.SEAM_QUESTS_YD)
    # (the herbs' default: where the seamless map's world stage takes them off, shown in yards)
    assert text("iconYdHerbs") == yd(min(G.ICON_YD_ALWAYS, G.SEAM_ICONS_FEW * G.SeamShare()))
    assert O.iconYdReset._enabled is False
    try:
        # (moved: the setting takes the yards, and the reset lights up)
        _move(by_key["iconYdHerbs"], 300)
        assert st.iconYdHerbs == 300 and text("iconYdHerbs") == yd(300)
        assert G.IconShown("herbs", 300 * G.ZoomScale(), False) and not G.IconShown("herbs", 400 * G.ZoomScale(), False)
        O.Refresh()
        assert O.iconYdReset._enabled is True
        # (the top notch reads Always and shows them at every zoom, past the world stage too)
        _move(by_key["iconYdHerbs"], G.ICON_YD_ALWAYS)
        O.Refresh()
        assert text("iconYdHerbs") == "Always" and G.IconShown("herbs", 1e6, True)
        # (a kind's slider gray while its icons are off)
        st.layerHerbs = False
        O.Refresh()
        assert by_key["iconYdHerbs"].agpsOn is False
        st.layerHerbs = True
        O.iconYdReset._scripts.OnClick(O.iconYdReset)
        assert [st[k] for k in keys] == [ns.DEFAULTS.gps[k] for k in keys]
        O.Refresh()
        assert O.iconYdReset._enabled is False
    finally:
        for k in keys:
            st[k] = ns.DEFAULTS.gps[k]


def test_arrow_side_hide_and_the_directions_text_alone(game):
    # (asked 2026-11-17: "add a fifth option that is 'Hide' that hides the arrow", and "hide the text separately and only
    # show the arrow") Hide is the fifth Arrow side, there with the arrow snapped or not; a side picked snaps the arrow
    # there (as dropping it against that side does), Hide leaves the snapping as it was; the text's own checkbox is
    # named for the text, and gray while the arrow is hidden (never both hidden)
    lua, ns = game
    st, O = ns.settings.gps, ns.Options
    by_key = {c.key: c.control for c in _controls(ns)}
    buttons = by_key["arrowSide"]
    radio = {buttons[i].value: buttons[i] for i in range(1, len(buttons) + 1)}
    assert list(radio) == ["left", "right", "top", "bottom", "hide"]
    assert radio["hide"].text._text == "Hide"
    saved = {k: st[k] for k in ("arrow", "arrowSnap", "arrowSide", "dirShown")}
    try:
        st.arrow, st.dirShown, st.arrowSnap, st.arrowSide = True, True, False, "left"
        O.Refresh()
        assert buttons.agpsOn is True  # (the arrow on its own: still there to pick)
        radio["hide"]._scripts.OnClick(radio["hide"])
        assert st.arrowSide == "hide" and st.arrowSnap is False
        O.Refresh()
        assert by_key["dirShown"].agpsOn is False and by_key["arrowSnap"].agpsOn is False
        radio["right"]._scripts.OnClick(radio["right"])
        assert st.arrowSide == "right" and st.arrowSnap is True
        O.Refresh()
        assert by_key["dirShown"].agpsOn is True
        assert [w for w in lua.eval("AGPS_WIDGETS").values() if w._text == "Show the directions text"]
    finally:
        for k, v in saved.items():
            st[k] = v
        O.Refresh()


def test_a_section_collapses_by_its_title_and_the_search_still_finds_it(game):
    # (asked 2026-11-19: "a yellow +/- button ... that will collapse and expand the section")
    lua, ns = game
    O = ns.Options
    p = lua.eval("AzerothGPSOptionsSearch and AGPS_NS.Options.search.pages")[O.pages["Opacity"].index]
    rows = list(p.rows.values())
    heads = [r for r in rows if r.header]
    assert len(heads) == 3 and all(r.foldButton for r in heads)
    full = p.child._h
    first, second = heads[0], heads[1]
    under = [r for r in rows[rows.index(first) + 1:rows.index(second)]]
    assert under and all(r.w._shown for r in under) and str(first.foldButton.sign._text) == "-"
    y2 = second.w._pt[3]
    try:
        first.foldButton._scripts["OnClick"](first.foldButton)
        assert ns.db.optFold[first.foldKey] is True and str(first.foldButton.sign._text) == "+"
        assert not any(r.w._shown for r in under)
        assert second.w._pt[3] > y2 and p.child._h < full  # (what's after moved up, the page shorter)
        O.Search("opacity")  # (the search opens every section)
        assert all(r.w._shown for r in under)
        O.Search("")
        assert not any(r.w._shown for r in under)
        first.foldButton._scripts["OnClick"](first.foldButton)
        assert all(r.w._shown for r in under) and second.w._pt[3] == y2 and p.child._h == full
    finally:
        ns.db.optFold = None
        O.Search("")
    # (the fine-tuning sections start collapsed)
    pm = O.search.pages[O.pages["Map"].index]
    zoom = next(r for r in pm.rows.values() if r.header and str(r.w._text) == "Zoom levels")
    assert str(zoom.foldButton.sign._text) == "+"


def test_the_minimap_and_world_map_options_show_pictures_that_pick_them(game):
    # (asked 2026-11-19: pictures in the options of what a choice does, the first-run setup's)
    lua, ns = game
    O = ns.Options
    st = ns.settings.gps
    was = st.replaceMinimap
    row = O.minimapPictures
    assert row and len(row.cards) == 2 and str(row.cards[1].label._text) == "The game's minimap"
    try:
        st.replaceMinimap = False
        O.Refresh() if O.Refresh else None
        row.cards[2]._scripts["OnClick"](row.cards[2])
        assert st.replaceMinimap is True
        assert row.cards[2].lit[1]._shown and not row.cards[1].lit[1]._shown
        row.cards[1]._scripts["OnClick"](row.cards[1])
        assert st.replaceMinimap is False and row.cards[1].lit[1]._shown
    finally:
        st.replaceMinimap = was
    assert O.worldMapPictures and str(O.worldMapPictures.cards[2].label._text) == "In the world map"


def test_icon_size_is_a_dropdown_again(game):
    # (the radio buttons under pictures were taken back, 2026-11-19: a dropdown, as in 1.3.9)
    lua, ns = game
    assert getattr(ns.Options, "iconSizeRow", None) is None
    src = (ADDON / "Options.lua").read_text(encoding="utf-8")
    assert 'Dropdown(L["Icon size"]' in src
