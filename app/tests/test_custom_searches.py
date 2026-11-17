"""Search buttons (asked 2026-11-16 for 1.3.5: "a custom map menu button feature that effectively will auto search and
pick the top result and set a destination. Players create these, any icon and name with description (enforce letter
limits) and they get added to another section in the quick buttons option page account wide ... Players can choose
this to be a button on map menu or it can be under the quick find menu. Allow them to add/remove the current quick find
buttons in this section as well"): Searches.lua, GPSFrame's Quick Find and quick buttons, Options > Quick buttons."""

import pytest

pytest.importorskip("lupa.lua51")

BRILL = (2254.0, 293.0, 0)
RAZOR_HILL = (325.0, -4700.0, 1)


@pytest.fixture(scope="module")
def game():
    from azerothgps.gameharness import start
    lua, ns = start()
    ns.Nav.FUN = False
    return lua, ns


@pytest.fixture
def sx(game):
    lua, ns = game
    was = (ns.db.npcs, ns.db.pins, ns.db.searches, ns.db.searchesRemoved, ns.db.searchesNext)
    ns.db.npcs, ns.db.pins = lua.eval("{}"), lua.eval("{}")
    ns.db.searches, ns.db.searchesRemoved, ns.db.searchesNext = None, None, None
    ns.CharDB().faction = "Horde"
    lua.execute("AGPS_SX_OLD = { UnitClass = UnitClass, Print = AGPS_NS.Print } AGPS_PRINTS = {} "
                "AGPS_NS.Print = function(m) AGPS_PRINTS[#AGPS_PRINTS + 1] = tostring(m) end "
                "UnitClass = function() return 'Mage', 'MAGE' end")
    _at(lua, BRILL)
    ns.Nav.Clear()
    ns.GPS.Follow()  # (no stops waiting to be confirmed from before)
    yield lua, ns
    ns.GPS.Follow()
    ns.GPS.SetQuickFindOpen(False)
    lua.execute("UnitClass, AGPS_NS.Print = AGPS_SX_OLD.UnitClass, AGPS_SX_OLD.Print AGPS_SX_OLD = nil")
    ns.db.npcs, ns.db.pins, ns.db.searches, ns.db.searchesRemoved, ns.db.searchesNext = was
    ns.Searches.Changed()
    ns.Nav.Clear()
    _at(lua, BRILL)


def _at(lua, p):
    lua.execute(f"AGPS_POS[1], AGPS_POS[2], AGPS_POS[3] = {p[0]}, {p[1]}, {p[2]}")


def _kinds(entries):
    return [str(e.kind) for e in entries.values()]


def test_quick_finds_own_are_the_first_rows_and_the_list_is_the_accounts(sx):
    lua, ns = sx
    S = ns.Searches
    rows = S.List()
    assert [str(r.builtin) for r in rows.values()] == [str(e.kind) for e in ns.GPS.QUICK_FIND.values()]
    assert all(str(S.Place(r)) == "quickFind" for r in rows.values())
    # (in AzerothGPSDB itself: every character and profile of the account, not a character's or a profile's)
    assert lua.eval("rawequal(AzerothGPSDB.searches, AGPS_NS.Searches.List())")
    assert ns.CharDB().searches is None and ns.settings.searches is None and ns.settings.gps.searches is None
    assert _kinds(ns.GPS.QuickFindEntries()) == ["repair", "vendor", "innkeeper", "flight master"]


def test_the_letter_limits_are_kept(sx):
    lua, ns = sx
    S = ns.Searches
    r = S.Add(lua.table_from({"name": "A" * 40, "text": "repair" + "x" * 60, "desc": "d" * 300, "icon": "INV_Misc_Bag_08"}))
    assert S.Len(r.name) == S.NAME_MAX == 24 and S.Len(r.text) == S.TEXT_MAX and S.Len(r.desc) == S.DESC_MAX == 120
    assert str(r.icon) == "Interface\\Icons\\INV_Misc_Bag_08"
    # (letters, not bytes: an accented name is as long as it looks)
    r2 = S.Add(lua.table_from({"name": "É" * 30, "text": "repair"}))
    assert S.Len(r2.name) == 24 and len(str(r2.name).encode()) == 48
    assert S.Add(lua.table_from({"name": "  ", "text": "repair"}))[0] is None
    assert S.Add(lua.table_from({"name": "x", "text": "r"}))[0] is None  # (too short to search)
    assert S.IconFrom("136243") == 136243 and str(S.Add(lua.table_from({"name": "y", "text": "inn"})).icon) == str(S.DEFAULT_ICON)
    # (and no more than S.MAX in the list)
    while len(S.List()) < S.MAX:
        S.Add(lua.table_from({"name": "z", "text": "vendor"}))
    res = S.Add(lua.table_from({"name": "one more", "text": "vendor"}))
    assert res[0] is None if isinstance(res, tuple) else res is None


def test_a_search_in_quick_find_sets_the_nearest_from_where_you_are(sx):
    lua, ns = sx
    G, S = ns.GPS, ns.Searches
    was = ns.settings.gps.quick
    ns.settings.gps.quick = lua.eval("{ quickFind = 'barUp' }")  # (its button shown: the flyout opens from it)
    G.LayoutQuick()
    r = S.Add(lua.table_from({"name": "Fix My Gear", "text": "repair", "desc": "The nearest repair.",
                              "icon": "INV_Hammer_20"}))
    e = next(e for e in G.QuickFindEntries().values() if str(e.kind) == "cs:" + str(r.id))
    assert str(e.label) == "Fix My Gear" and str(G.QuickFindIcon(e)) == "Interface\\Icons\\INV_Hammer_20"
    stops = []
    for p in (BRILL, RAZOR_HILL):
        _at(lua, p)
        ns.Nav.Clear()
        want = G.QuickFindNearest("repair")
        G.SetQuickFindOpen(True)
        b = G.quickFindButtons["cs:" + str(r.id)]
        assert b._shown
        b._scripts.OnClick(b, "LeftButton")
        G.ConfirmRoute()
        assert len(ns.Nav.stops) == 1
        s = ns.Nav.stops[1]
        assert abs(s.x - want.x) < 0.5 and abs(s.y - want.y) < 0.5
        stops.append((round(s.x), round(s.y), s.cont))
    assert stops[0] != stops[1]  # (from each place its own nearest)
    # a name typed: the search's top result, as the search box would have it
    ns.Nav.Clear()
    _at(lua, BRILL)
    named = S.Add(lua.table_from({"name": "Renee", "text": "Innkeeper Renee"}))
    assert str(S.Run(named).name) == "Innkeeper Renee"
    # nothing found: said so
    none = S.Add(lua.table_from({"name": "Nothing", "text": "zzqqxx"}))
    assert S.Run(none) is None and any("Nothing" in m for m in [str(v) for v in lua.eval("AGPS_PRINTS").values()])
    ns.settings.gps.quick = was
    G.LayoutQuick()


def test_a_search_in_the_map_menu_is_a_quick_button(sx):
    lua, ns = sx
    G, S = ns.GPS, ns.Searches
    r = S.Add(lua.table_from({"name": "Inn", "text": "innkeeper", "place": "barUp"}))
    qid = "cs:" + str(r.id)
    t = next(t for t in G.QUICK.values() if str(t.id) == qid)
    assert t.custom and str(t.label) == "Inn" and t.button._shown and str(G.QuickPlace(qid)) == "barUp"
    assert qid in [str(s.id) for s in G.QuickSlots().values()]
    assert qid not in _kinds(G.QuickFindEntries())
    ns.Nav.Clear()
    t.button._scripts.OnClick(t.button)
    G.ConfirmRoute()
    assert len(ns.Nav.stops) == 1 and str(ns.Nav.stops[1].name) == "Innkeeper Renee"
    # changed: its name and icon follow; moved to Quick Find: no button any more
    S.Update(r.id, lua.table_from({"name": "Bed", "text": "innkeeper", "icon": "INV_Misc_Bag_08", "place": "menuRight"}))
    assert str(t.label) == "Bed" and str(G.QuickPlace(qid)) == "menuRight"
    S.SetPlace(r.id, "quickFind")
    assert qid not in [str(t.id) for t in G.QUICK.values()] and not t.button._shown
    assert qid in _kinds(G.QuickFindEntries())
    # back in the map menu: the same button; removed: gone
    S.SetPlace(r.id, "barRight")
    assert lua.eval("rawequal")(next(t2 for t2 in G.QUICK.values() if str(t2.id) == qid), t)
    S.Remove(r.id)
    assert qid not in [str(t.id) for t in G.QUICK.values()] and qid not in _kinds(G.QuickFindEntries())


def test_quick_finds_own_can_be_changed_removed_and_restored(sx):
    lua, ns = sx
    G, S = ns.GPS, ns.Searches
    S.Update("b:vendor", lua.table_from({"name": "Shop", "text": "vendor", "icon": ""}))
    e = next(e for e in G.QuickFindEntries().values() if str(e.kind) == "vendor")
    assert str(e.label) == "Shop" and "QuestionMark" not in str(G.QuickFindIcon(e))  # (its own icon kept)
    S.Remove("b:repair")
    assert "repair" not in _kinds(G.QuickFindEntries())
    # (a later version's list: still removed, not seeded again)
    assert S.Get("b:repair") is None and lua.eval("AzerothGPSDB.searchesRemoved.repair") is True
    mine = S.Add(lua.table_from({"name": "Mine", "text": "repair"}))
    S.RestoreDefaults()
    kinds = _kinds(G.QuickFindEntries())
    assert kinds[:4] == ["repair", "vendor", "innkeeper", "flight master"] and "cs:" + str(mine.id) in kinds
    assert str(next(e for e in G.QuickFindEntries().values() if str(e.kind) == "vendor").label) == "Vendor"
    # (a hunter's own: Stable Master and Ammo, theirs only)
    lua.execute("UnitClass = function() return 'Hunter', 'HUNTER' end")
    assert "ammo" in _kinds(G.QuickFindEntries()) and "stable master" in _kinds(G.QuickFindEntries())


def test_the_popup_is_a_window_with_the_limits_in_its_boxes(sx):
    lua, ns = sx
    S = ns.Searches
    f = S.Edit(None)
    assert f._shown and f.top is not None  # (ns.Window's: the map window's frame and the small logo, its content below)
    assert (f.name._maxLetters, f.text._maxLetters, f.desc._maxLetters) == (S.NAME_MAX, S.TEXT_MAX, S.DESC_MAX)
    f.save._scripts.OnClick(f.save)
    assert f._shown and str(f.err._text) == "Give it a name."
    f.name.SetText(f.name, "Mail")
    f.text.SetText(f.text, "mailbox")
    f.placeDD.padSet("menuUp")  # (a dropdown: the game's, or a controller's)
    assert str(f.place) == "menuUp" and str(f.placeDD.padGet()) == "menuUp"
    f.save._scripts.OnClick(f.save)
    assert not f._shown
    r = S.List()[len(S.List())]
    assert str(r.name) == "Mail" and str(r.text) == "mailbox" and str(S.Place(r)) == "menuUp"
    # editing one: its fields in the boxes
    f = S.Edit(r.id)
    assert str(f.name._text) == "Mail" and str(f.editing) == str(r.id)
    f.Hide(f)


def test_the_quick_buttons_page_lists_them(sx):
    lua, ns = sx
    S = ns.Searches
    S.Add(lua.table_from({"name": "Fix My Gear", "text": "repair"}))
    ns.Options.Show()
    ns.Options.Refresh()
    rows = [r for r in ns.Options.searchRows.values() if r._shown]
    assert [str(r.label._text) for r in rows][:4] == ["Repair", "Vendor", "Innkeeper", "Flight Master"]
    assert "Fix My Gear" in [str(r.label._text) for r in rows]
    mine = next(r for r in rows if str(r.label._text) == "Fix My Gear")
    # (where it goes: a dropdown, Options' own, a controller's too)
    w = mine.where
    assert str(w._kind) == "DropdownButton" and w.options and w.padGet and w.padSet
    assert str(w.padGet()) == "quickFind" and str(w._choice) == "In Quick Find"
    w.padSet("menuUp")
    ns.Options.Refresh()
    assert str(w.padGet()) == "menuUp" and str(w._choice) == "Map menu: in the menu, up"
    assert str(S.Place(S.List()[len(S.List())])) == "menuUp"
    mine.edit._scripts.OnClick(mine.edit)
    assert S.editor._shown and str(S.editor.editing) == str(mine.id)
    S.editor.Hide(S.editor)
    mine.remove._scripts.OnClick(mine.remove)
    ns.Options.Refresh()
    assert "Fix My Gear" not in [str(r.label._text) for r in ns.Options.searchRows.values() if r._shown]


# (asked 2026-11-16, the editor's screenshot: "text is off, make the icon selection another popup like how custom pin
# works, allow the icon search field in that pop up"; and Options' rows: "Buttons are cutoff, look terrible")
LOCALES = ["deDE", "esES", "esMX", "frFR", "itIT", "koKR", "ptBR", "ruRU", "zhCN", "zhTW"]


def _px(text):
    """A string's width in the small font, generously: 6.5 px a letter, 12 an East Asian one."""
    import re
    text = re.sub(r"\|c[0-9a-fA-F]{8}|\|r", "", text)
    return sum(12 if ord(ch) >= 0x2E80 else 6.5 for ch in text)


def _locale(lua, code):
    from pathlib import Path
    src = (Path(__file__).resolve().parents[2] / "addon" / "AzerothGPS" / "Locales" / f"{code}.lua").read_text(encoding="utf-8")
    t = lua.eval("""function(src, code)
      local L = {}
      local ns = { NewLocale = function(c) if c == code then return L end end }
      assert(loadstring(src))('AzerothGPS', ns)
      return L
    end""")(src, code)
    return lambda k: str(t[k]) if t[k] is not None else k


def test_the_editor_s_labels_fit_above_their_boxes_in_every_language(sx):
    lua, ns = sx
    S = ns.Searches
    f = S.Edit(None)
    labels = [f.labels[i] for i in range(1, len(f.labels) + 1)]
    assert len(labels) == 5 and all(fs.room == S.EDIT_W - 40 for fs in labels)
    keys = [("Name (up to %d letters)", S.NAME_MAX), ("Search for (up to %d)", S.TEXT_MAX),
            ("Description (up to %d)", S.DESC_MAX), ("Icon", None), ("Where", None)]
    assert [str(fs._text) for fs in labels] == [k % n if n else k for k, n in keys]
    room = S.EDIT_W - 40
    for code in LOCALES:
        tr = _locale(lua, code)
        for k, n in keys:
            text = tr(k) % n if n else tr(k)
            assert _px(text) <= room, (code, text)
        # (the picker's label over its grid; the short places on Options' row dropdowns)
        assert _px(tr("Search icons: part of a name, or a file id")) <= ns.Pins.COLS * ns.Pins.CELL + 20, code
        for p in ("Quick Find", "Menu, up", "Menu, right", "Always shown, up", "Always shown, right"):
            assert _px(tr(p)) <= ns.Options.SEARCH_ROW.where[2] - 36, (code, tr(p))
    f.Hide(f)


def test_the_options_rows_fit_the_page():
    import pytest
    pytest.importorskip("lupa.lua51")
    from azerothgps.gameharness import start
    lua, ns = start()
    R = ns.Options.SEARCH_ROW
    parts = [R.icon, R.label, R.where, R.edit, R.remove]
    x = 0
    for part in parts:  # (left to right, none over the next)
        assert part[1] >= x and part[2] > 0
        x = part[1] + part[2]
    assert x <= R.w and R.x + R.w <= ns.Options.PAGE_W - 26
    assert R.label[2] >= 24 * 6  # (a name of 24 letters)
    ns.Options.Show()
    ns.Options.Refresh()
    row = ns.Options.searchRows[1]
    assert row._shown and str(row.where._kind) == "DropdownButton"
    for k in ("edit", "remove"):
        b = row[k]
        assert str(b._kind) == "Button" and b._scripts.OnClick and b._scripts.OnEnter  # (a tooltip: what it does)
    # (another class's built-in: dimmed)
    lua.execute("AGPS_SX_UC = UnitClass UnitClass = function() return 'Mage', 'MAGE' end")
    try:
        ns.Options.Refresh()
        rows = [r for r in ns.Options.searchRows.values() if r._shown]
        names = [str(r.label._text) for r in rows]
        assert any(n.startswith("|cff808080") for n in names)  # (the hunter's Stable Master and Ammo)
    finally:
        lua.execute("UnitClass = AGPS_SX_UC")


def test_the_icon_picker_is_its_own_popup_with_a_search(sx):
    lua, ns = sx
    S = ns.Searches
    f = S.Edit(None)
    assert f.preview and f.iconBtn and str(f.iconName._text) == "INV_Misc_QuestionMark"
    f.iconBtn._scripts.OnClick(f.iconBtn)
    pk = S.picker
    assert pk._shown and pk.top is not None and str(pk._name) == "AzerothGPSIconPicker"  # (ns.Window's look)
    assert lua.eval("AGPS_NS.popups")[pk] is not None  # (a popup: Escape, a controller's)
    assert len(pk.cells) == ns.Pins.COLS * ns.Pins.ROWS
    every = len(S.PickerIcons())
    assert every >= 30 + len(ns.Pins.FALLBACK_ICONS)  # (the game's and the addon's named ones)
    assert "of %d" % every in str(pk.count._text)
    # typed: only the icons whose name has every word
    pk.search.SetText(pk.search, "bag")
    pk.search._scripts.OnTextChanged(pk.search)
    got = [pk.list[i] for i in range(1, len(pk.list) + 1)]
    names = [str(S.IconLabel(v)).lower() for v in got]
    assert names and all("bag" in n for n in names[1:]) and "inv_misc_bag_08" in names
    assert not any(isinstance(v, (int, float)) for v in got[1:])
    # (the word typed itself as an icon: only a file the game has)
    lua.globals().AGPS_PK = pk
    lua.execute("AGPS_PK.probe.GetTextureFileID = function() return nil end")
    pk.search._scripts.OnTextChanged(pk.search)
    names = [str(S.IconLabel(pk.list[i])).lower() for i in range(1, len(pk.list) + 1)]
    assert "bag" not in names and all("bag" in n for n in names)
    pk.search.SetText(pk.search, "zzqqxx")
    pk.search._scripts.OnTextChanged(pk.search)
    assert len(pk.list) == 0 and str(pk.count._text) == "No icons match." and not pk.cells[1]._shown
    # a file id: those with it in theirs; one typed whole the first
    lua.execute("AGPS_PK.probe.GetTextureFileID = function() return 1 end")
    pk.search.SetText(pk.search, "136005")
    pk.search._scripts.OnTextChanged(pk.search)
    assert pk.list[1] == 136005 and len(pk.list) == 1
    pk.search.SetText(pk.search, "INV_Hammer_20")  # (a name the list hasn't: the typed one)
    pk.search._scripts.OnTextChanged(pk.search)
    assert str(pk.list[1]) == "Interface\\Icons\\INV_Hammer_20"
    # picked: the editor's, the picker closed
    pk.search.SetText(pk.search, "bag_08")
    pk.search._scripts.OnTextChanged(pk.search)
    cell = next(c for c in pk.cells.values() if c._shown and str(S.IconLabel(c.value)) == "INV_Misc_Bag_08")
    cell._scripts.OnClick(cell)
    assert not pk._shown and str(f.iconName._text) == "INV_Misc_Bag_08"
    f.name.SetText(f.name, "Bags")
    f.text.SetText(f.text, "vendor")
    f.save._scripts.OnClick(f.save)
    r = S.List()[len(S.List())]
    assert str(r.icon) == "Interface\\Icons\\INV_Misc_Bag_08"
    # a file id picked, and the picker scrolls (wheel) and closes with the editor
    f = S.Edit(r.id)
    f.choose._scripts.OnClick(f.choose)
    assert pk._shown and str(pk.search._text) == ""
    before = pk.top0  # (the icon it has in view and marked)
    assert pk.sel._shown and any(c._shown and str(S.IconLabel(c.value)) == "INV_Misc_Bag_08" for c in pk.cells.values())
    S.ScrollPicker(1)
    assert pk.top0 == before + 1
    S.ScrollPicker(-100)
    assert pk.top0 == 0
    S.PickIcon(136003)
    assert f.iconValue == 136003 and str(f.iconName._text) == "File id 136003"
    f.iconBtn._scripts.OnClick(f.iconBtn)
    f.Hide(f)
    if f._scripts.OnHide:
        f._scripts.OnHide(f)
    assert not pk._shown
