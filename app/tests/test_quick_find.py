"""Quick Find (asked 2026-11-14: "add a quick button above the search button that expands out for quick searches for
closest common things like repair, vendor, ammo (if the player class is hunter)"; then "for hunters, that button
should pop out again to select gun ammo or arrows"): a quick button just above Search Places, placed and hidden in
Options > Quick buttons like the others; clicked, a flyout of the common kinds (Repair, Vendor, Innkeeper, Flight
Master, Banker, Auctioneer, Stable Master, Class Trainer, and a hunter's Ammo, which opens Arrows and Bullets). An
entry clicked is a stop at the nearest of its kind, as the search's first; right-clicked, the search with its word
typed. Ammo vendors are told by what they sell (Data/VendorItems.lua, test_vendor_items.py), by their
titles where that is not known."""

import pytest

pytest.importorskip("lupa.lua51")

BRILL = (2254.0, 293.0, 0)
COMMON = ["repair", "vendor", "innkeeper", "flight master"]


@pytest.fixture(scope="module")
def game():
    from azerothgps.gameharness import start
    lua, ns = start()
    ns.Nav.FUN = False
    return lua, ns


@pytest.fixture
def qf(game):
    lua, ns = game
    G = ns.GPS
    was_npcs, was_pins = ns.db.npcs, ns.db.pins
    ns.db.npcs, ns.db.pins = lua.eval("{}"), lua.eval("{}")
    ns.CharDB().faction = "Horde"
    lua.execute(f"AGPS_POS = {{ {BRILL[0]}, {BRILL[1]}, {BRILL[2]} }}")
    lua.execute("AGPS_QF_OLD = { UnitClass = UnitClass, Print = AGPS_NS.Print } AGPS_PRINTS = {} "
                "AGPS_NS.Print = function(m) AGPS_PRINTS[#AGPS_PRINTS + 1] = tostring(m) end")
    ns.Nav.Clear()
    yield lua, ns
    G.SetQuickFindOpen(False)
    lua.execute("UnitClass, AGPS_NS.Print = AGPS_QF_OLD.UnitClass, AGPS_QF_OLD.Print AGPS_QF_OLD = nil")
    lua.execute("for k in pairs(AGPS_NS.GPS.holders) do AGPS_NS.GPS.holders[k] = nil end")
    ns.db.npcs, ns.db.pins = was_npcs, was_pins
    ns.Nav.Clear()
    if G.searchPanel:
        G.searchPanel.Hide(G.searchPanel)


def _class(lua, name, file):
    lua.execute(f"UnitClass = function() return '{name}', '{file}' end")


def _kinds(entries):
    return [str(e.kind) for e in entries.values()]


def _shown(ns):
    return sorted(str(k) for k, b in ns.GPS.quickFindButtons.items() if b._shown)


def _prints(lua):
    t = lua.eval("AGPS_PRINTS")
    return [str(t[i]) for i in range(1, len(t) + 1)]


def test_the_button_sits_just_above_search_places_and_is_a_quick_button(qf):
    lua, ns = qf
    G = ns.GPS
    slots = [str(t.id) for t in G.QuickSlots().values()]
    assert slots.index("quickFind") == slots.index("search") + 1  # (the next one up the column)
    assert str(G.QuickPlace("quickFind")) == "menuUp"  # (shown by default, with Search Places)
    t = next(t for t in G.QUICK.values() if str(t.id) == "quickFind")
    assert str(t.label) == "Quick Find" and t.icon and t.action
    # an order saved before it: still just above Search Places
    gps = ns.settings.gps
    was = gps.quickOrder
    try:
        gps.quickOrder = lua.eval("{ 'questRoute', 'search', 'styles' }")
        slots = [str(t.id) for t in G.QuickSlots().values()]
        assert slots[:3] == ["questRoute", "search", "quickFind"]
    finally:
        gps.quickOrder = was


def test_it_can_be_hidden_or_moved_in_the_options(qf):
    lua, ns = qf
    G = ns.GPS
    gps = ns.settings.gps
    was = gps.quick
    try:
        gps.quick = lua.eval("{ quickFind = 'hidden' }")
        G.LayoutQuick()
        t = next(t for t in G.QUICK.values() if str(t.id) == "quickFind")
        assert t.button._shown is False
        G.SetQuickFindOpen(True)
        assert _shown(ns) == []  # (its button not shown: nothing opens)
        gps.quick = lua.eval("{ quickFind = 'barRight' }")
        G.LayoutQuick()
        assert t.button._shown is True and str(G.QuickPlace("quickFind")) == "barRight"
    finally:
        gps.quick = was
        G.LayoutQuick()
    # its row on the Quick buttons page
    ns.Options.Show()
    assert any(str(w._text) == "Quick Find" for w in lua.eval("AGPS_WIDGETS").values() if w._kind == "FontString")


def _open_bar(lua, ns):
    gps = ns.settings.gps
    gps.quick = lua.eval("{ quickFind = 'barUp' }")
    ns.GPS.LayoutQuick()


def test_the_flyout_opens_and_closes(qf):
    lua, ns = qf
    G = ns.GPS
    _class(lua, "Mage", "MAGE")
    was = ns.settings.gps.quick
    try:
        _open_bar(lua, ns)
        t = next(t for t in G.QUICK.values() if str(t.id) == "quickFind")
        assert _shown(ns) == []
        t.button._scripts.OnClick(t.button)
        assert G.quickFindOpen is True and _shown(ns) == sorted(COMMON)
        b = G.quickFindButtons["repair"]
        assert str(b._pts.LEFT[3]) == "RIGHT"  # (out to the right of a column going up)
        t.button._scripts.OnClick(t.button)
        assert G.quickFindOpen is False and _shown(ns) == []
        # shut by itself after GROUP_IDLE untouched
        G.SetQuickFindOpen(True)
        d = G.quickFindDriver
        d._scripts.OnUpdate(d, 1)
        assert G.quickFindOpen is True  # (a second: still open)
        d._scripts.OnUpdate(d, G.GROUP_IDLE)
        assert G.quickFindOpen is False and _shown(ns) == []
        # not while another addon holds the map
        lua.execute("AGPS_NS.GPS.holders.Other = {}")
        assert G.SetQuickFindOpen(True) is False and _shown(ns) == []
    finally:
        ns.settings.gps.quick = was
        G.LayoutQuick()


def test_the_entries_for_a_hunter_and_a_non_hunter(qf):
    lua, ns = qf
    G = ns.GPS
    _class(lua, "Warrior", "WARRIOR")
    assert _kinds(G.QuickFindEntries()) == COMMON
    _class(lua, "Hunter", "HUNTER")
    assert _kinds(G.QuickFindEntries()) == COMMON + ["stable master", "ammo"]  # (stable: hunters, 2026-11-15)
    labels = [str(e.label) for e in G.QuickFindEntries().values()]
    assert labels == ["Repair", "Vendor", "Innkeeper", "Flight Master", "Stable Master", "Ammo"]
    # each with the game's icon for its kind
    icons = ns.Pins.NPC_ICONS
    assert str(G.QuickFindIcon(G.QUICK_FIND[1])) == str(icons.repair)
    assert str(G.QuickFindIcon(G.QUICK_FIND[3])) == str(icons.inn)
    assert all("QuestionMark" not in str(G.QuickFindIcon(e)) for e in G.QUICK_FIND.values())


def test_ammo_pops_out_arrows_and_bullets_for_a_hunter(qf):
    lua, ns = qf
    G = ns.GPS
    was = ns.settings.gps.quick
    try:
        _open_bar(lua, ns)
        _class(lua, "Hunter", "HUNTER")
        G.SetQuickFindOpen(True)
        assert _shown(ns) == sorted(COMMON + ["stable master", "ammo"])
        ammo = G.quickFindButtons["ammo"]
        ammo._scripts.OnClick(ammo, "LeftButton")
        assert G.quickFindOpen is True and len(ns.Nav.stops) == 0  # (no stop: its own flyout)
        assert _shown(ns) == sorted(COMMON + ["stable master", "ammo", "arrows", "bullets"])
        arrows = G.quickFindButtons["arrows"]
        assert str(arrows._pts.BOTTOM[3]) == "TOP"  # (up from Ammo: the other way from the flyout)
        ammo._scripts.OnClick(ammo, "LeftButton")
        assert _shown(ns) == sorted(COMMON + ["stable master", "ammo"])  # (clicked again: shut)
        _class(lua, "Mage", "MAGE")
        G.SetQuickFindOpen(True)
        assert "ammo" not in _shown(ns)
    finally:
        ns.settings.gps.quick = was
        G.LayoutQuick()


def test_ammo_vendors_are_told_by_their_titles(qf):
    lua, ns = qf
    G = ns.GPS

    def kinds(title):
        k = G.AmmoKinds(title)
        return sorted(str(k[i]) for i in range(1, len(k) + 1)) if k else []

    assert kinds("Bowyer") == ["ammo", "arrows"]
    assert kinds("Bow Merchant") == ["ammo", "arrows"]
    assert kinds("Fletcher") == ["ammo", "arrows"]
    assert kinds("Gunsmith") == ["ammo", "bullets"]
    assert kinds("Gun Merchant") == ["ammo", "bullets"]
    assert kinds("Bowyer & Gunsmith") == ["ammo", "arrows", "bullets"]
    assert kinds("Ammunition Vendor") == ["ammo", "arrows", "bullets"]
    # (asked 2026-11-15: Kaja, "Guns and Ammo Merchant", sells bullets alone: no arrows by "Ammo")
    assert kinds("Guns and Ammo Merchant") == ["ammo", "bullets"]
    assert kinds("Weaponsmith") == [] and kinds("General Goods") == [] and kinds("Elbow Grease") == []
    # the search's generic words: each kind's sellers only, nearest first (by what they sell since 2026-11-15:
    # test_vendor_items.py; the titles only where a vendor's stock isn't known)
    for word, want in (("arrows", "arrows"), ("arrow", "arrows"), ("bullets", "bullets"), ("bullet", "bullets"),
                       ("ammo", "ammo"), ("ammunition", "ammo")):
        res = G.SearchPlaces(word, 20)
        # (the kind's sellers; after them, names with the word in them: "Gwyn Farrow")
        npcs = [res[i] for i in range(1, len(res) + 1) if res[i].shipped and word not in str(res[i].lower)]
        assert npcs, word
        for e in npcs:
            assert want in [str(k) for k in e.kinds.values()], (word, str(e.name), str(e.title))
        yds = [e.yd for e in npcs if e.yd is not None]
        assert yds == sorted(yds), word


def test_a_click_adds_the_nearest_of_its_kind_as_a_stop(qf):
    lua, ns = qf
    G = ns.GPS
    _class(lua, "Mage", "MAGE")  # (Brill's mage trainer; the buttons are made for every class, shown by it)
    for kind in COMMON + ["arrows", "bullets"]:
        ns.Nav.Clear()
        res = G.SearchPlaces(kind, 30)
        words = kind.split()
        of_kind = [res[i] for i in range(1, len(res) + 1)
                   if G.EntryKindTyped(lua.table(*words), res[i]) and res[i].yd is not None]
        nearest = min(of_kind, key=lambda e: e.yd)
        want = (str(nearest.name), nearest.x, nearest.y)
        G.SetQuickFindOpen(True, None)
        b = G.quickFindButtons[kind]
        b._scripts.OnClick(b, "LeftButton")
        G.ConfirmRoute()
        assert G.quickFindOpen is False, kind  # (shut)
        assert len(ns.Nav.stops) == 1, kind
        s = ns.Nav.stops[1]
        assert (str(s.name) if not nearest.place else str(nearest.name)) and abs(s.x - want[1]) < 0.5 \
            and abs(s.y - want[2]) < 0.5, (kind, want, str(s.name))
    # by name: Brill's
    ns.Nav.Clear()
    assert str(G.QuickFindClick(G.QUICK_FIND[3]).name) == "Innkeeper Renee"
    G.ConfirmRoute()
    assert str(ns.Nav.stops[1].name) == "Innkeeper Renee"
    ns.Nav.Clear()
    arrows = G.QUICK_FIND[6].sub[1]
    e = G.QuickFindClick(arrows)
    assert e and "arrows" in [str(k) for k in e.kinds.values()]
    ns.Nav.Clear()
    bullets = G.QUICK_FIND[6].sub[2]
    e = G.QuickFindClick(bullets)
    assert e and "bullets" in [str(k) for k in e.kinds.values()]


def test_nothing_of_the_kind_says_so_in_chat(qf):
    lua, ns = qf
    G = ns.GPS
    was = ns.NpcsPacked
    lua.execute("AGPS_QF_KIND = AGPS_NS.GPS.QUICK_FIND[6].sub[1]")
    ns.NpcsPacked = ""
    try:
        assert G.QuickFindClick(lua.eval("AGPS_QF_KIND")) is None
        assert len(ns.Nav.stops) == 0
        assert any("Quick Find: nothing found for Arrows." in m for m in _prints(lua))
    finally:
        ns.NpcsPacked = was


def test_a_held_map_does_nothing(qf):
    lua, ns = qf
    G = ns.GPS
    lua.execute("AGPS_NS.GPS.holders.Other = {}")
    assert G.QuickFindClick(G.QUICK_FIND[1]) is None and len(ns.Nav.stops) == 0
    assert G.QuickFindSearch(G.QUICK_FIND[1]) is False and not G.searchPanel._shown


def test_right_click_fills_the_search_box(qf):
    lua, ns = qf
    G = ns.GPS
    _class(lua, "Hunter", "HUNTER")
    for kind in ("repair", "flight master", "bullets"):
        G.SetQuickFindOpen(True, G.QUICK_FIND[6])
        b = G.quickFindButtons[kind]
        b._scripts.OnClick(b, "RightButton")
        panel = G.searchPanel
        assert panel._shown and str(panel.box._text) == kind
        assert G.quickFindOpen is False and len(ns.Nav.stops) == 0  # (no stop: the list to pick from)
        same = lua.eval("rawequal")
        rows = [w for w in lua.eval("AGPS_WIDGETS").values()
                if same(w._parent, panel) and w.entry is not None and w._shown]
        assert len(rows) >= 2, kind
        yds = [r.entry.yd for r in rows if r.entry.npc and r.entry.yd is not None]
        assert yds == sorted(yds), kind  # (nearest first)
        panel.Hide(panel)
    # the Search Places button hidden: said so
    gps = ns.settings.gps
    was = gps.quick
    try:
        gps.quick = lua.eval("{ search = 'hidden' }")
        assert G.QuickFindSearch(G.QUICK_FIND[1]) is False
        assert any("Search Places button is turned off" in m for m in _prints(lua))
    finally:
        gps.quick = was
        G.LayoutQuick()
