"""The addon's text in every language WoW has (Locales/*.lua, keyed by the English text: L["Quest Route"]): every key
the addon uses is in every language's file, a translation keeps its key's format values, color codes, textures and
newlines, no file keeps a key that's no longer used, and the addon starts and draws in every language."""

import re
from pathlib import Path

import pytest

lupa = pytest.importorskip("lupa")

ADDON = Path(__file__).resolve().parents[2] / "addon" / "AzerothGPS"
LOCALES = ["deDE", "esES", "esMX", "frFR", "itIT", "koKR", "ptBR", "ruRU", "zhCN", "zhTW"]

# L["..."] / L['...'] in the addon's code (a key is always one plain string literal)
KEY_USE = re.compile(r"""(?<![\w.])L\[\s*("(?:[^"\\\n]|\\.)*"|'(?:[^'\\\n]|\\.)*')\s*\]""")
# a format value: %s, %d, %5.1f, %%, and positional ones (%2$s) a translation may use
SPEC = re.compile(r"%(?:(\d+)\$)?([-+ #0]*\d*(?:\.\d+)?[cdiouxXeEfgGqs%])")
COLOR = re.compile(r"\|c[0-9a-fA-F]{8}|\|r")
TEXTURE = re.compile(r"\|T[^|]*\|t|\|A[^|]*\|a")


def _code_files():
    for p in sorted(ADDON.rglob("*.lua")):
        rel = p.relative_to(ADDON).parts
        if rel[0] in ("Locales", "Data") or (rel[0] == "Atlas" and rel[1] == "Data"):
            continue
        yield p


def _strip_comments(src):
    # (a key in a comment isn't used; strings never hold "--" before a key here)
    return re.sub(r"--\[(=*)\[.*?\]\1\]|--[^\n]*", "", src, flags=re.S)


@pytest.fixture(scope="module")
def lua():
    return lupa.LuaRuntime()


@pytest.fixture(scope="module")
def used(lua):
    """{key: [file, ...]} for every L["..."] in the code, the key as Lua reads it (escapes undone)."""
    value = lua.eval("function(lit) return assert(load('return ' .. lit))() end")
    out = {}
    for p in _code_files():
        for m in KEY_USE.finditer(_strip_comments(p.read_text(encoding="utf-8"))):
            key = value(m.group(1))
            out.setdefault(key, []).append(p.name)
    return out


def _load_locale(lua, code):
    """(translations, keys assigned in order): the locale file run as the game would for its own language."""
    src = (ADDON / "Locales" / f"{code}.lua").read_text(encoding="utf-8")
    run = lua.eval("""function(src, code)
      local L, order = {}, {}
      local ns = { NewLocale = function(c) if c == code then
        return setmetatable({}, { __newindex = function(_, k, v) order[#order + 1] = k; L[k] = v end }) end end }
      assert(load(src, '@' .. code))('AzerothGPS', ns)
      return L, order
    end""")
    t, order = run(src, code)
    return dict(t.items()), list(order.values())


@pytest.fixture(scope="module")
def locales(lua):
    return {code: _load_locale(lua, code) for code in LOCALES}


def _specs(s):
    """The format values in order (positional ones put in their place), and whether any was positional."""
    found = [(m.group(1), m.group(2)) for m in SPEC.finditer(s) if m.group(2) != "%"]
    if any(pos for pos, _ in found):
        ordered = sorted(found, key=lambda f: int(f[0] or 0))
        return [spec for _, spec in ordered], True
    return [spec for _, spec in found], False


def test_the_addon_uses_its_keys_and_the_english_is_the_key(used):
    assert len(used) > 500  # (the whole addon's text, not a few strings)


def test_every_key_used_is_in_every_language(used, locales):
    missing = {code: sorted(set(used) - set(t)) for code, (t, _) in locales.items()}
    missing = {code: keys[:20] + ([f"... {len(keys)} in all"] if len(keys) > 20 else []) for code, keys in missing.items() if keys}
    assert not missing, missing


def test_no_language_keeps_a_key_no_longer_used(used, locales):
    stale = {code: sorted(set(t) - set(used)) for code, (t, _) in locales.items()}
    stale = {code: keys for code, keys in stale.items() if keys}
    assert not stale, stale


def test_no_key_is_set_twice_in_a_file(locales):
    twice = {}
    for code, (_, order) in locales.items():
        seen = set()
        dup = [k for k in order if k in seen or seen.add(k)]
        if dup:
            twice[code] = dup
    assert not twice, twice


def test_every_translation_keeps_its_format_values_colors_textures_and_newlines(locales):
    bad = []
    for code, (t, _) in locales.items():
        for key, text in t.items():
            assert isinstance(text, str) and text, (code, key)
            if _specs(key)[0] != _specs(text)[0]:
                bad.append((code, key, text, "format values"))
            if sorted(c.lower() for c in COLOR.findall(key)) != sorted(c.lower() for c in COLOR.findall(text)):
                bad.append((code, key, text, "color codes"))
            if sorted(TEXTURE.findall(key)) != sorted(TEXTURE.findall(text)):
                bad.append((code, key, text, "textures"))
            if key.count("\n") != text.count("\n"):
                bad.append((code, key, text, "newlines"))
            # (a separator alone, ", ", may lose its space: CJK lists use "、")
            if key != key.strip() and re.search(r"\w", key) and (key[:1].isspace() != text[:1].isspace() or key[-1:].isspace() != text[-1:].isspace()):
                bad.append((code, key, text, "spaces at the ends"))
    assert not bad, bad[:30]


def test_a_translation_with_its_values_reordered_is_formatted_by_ns_format(locales):
    # ("%2$s ... %1$s": string.format can't; ns.Format can, so such a key is only ever formatted with it)
    reordered = {key for t, _ in locales.values() for key, text in t.items() if _specs(text)[1]}
    bad = []
    for p in _code_files():
        src = _strip_comments(p.read_text(encoding="utf-8"))
        for m in KEY_USE.finditer(src):
            key = m.group(1)[1:-1]
            if any(k.replace("\n", "\\n") == key for k in reordered) and not re.search(r"Format\(\s*$", src[:m.start()]):
                bad.append((p.name, key))
    assert not bad, bad


def test_ns_format_takes_positional_values(lua):
    src = (ADDON / "Locales" / "Locales.lua").read_text(encoding="utf-8")
    ns = lua.table()
    lua.eval("function(src) return assert(load(src, '@Locales.lua')) end")(src)("AzerothGPS", ns)
    assert ns.Format("%2$s in %1$s", "30 yd", "Turn left") == "Turn left in 30 yd"
    assert ns.Format("%d of %d (100%%)", 3, 4) == "3 of 4 (100%)"
    assert ns.Format("%2$d%% %1$.1f", 1.25, 7) == "7% 1.2" or ns.Format("%2$d%% %1$.1f", 1.25, 7) == "7% 1.3"
    assert ns.L["Not translated"] == "Not translated"


@pytest.mark.parametrize("code", ["enUS"] + LOCALES)
def test_the_addon_starts_and_draws_in_every_language(code):
    # (the whole addon under the game's Lua 5.1 with GetLocale() saying `code`: its options window's every page, a
    # route with its directions on the map and in the arrow window; a translation that breaks a format fails here)
    pytest.importorskip("lupa.lua51")
    from azerothgps.gameharness import start
    lua, ns = start(locale=code)
    assert ns.LOCALE == code
    if code != "enUS":
        assert ns.L["Tools"] != "Tools"
    ns.Options.Show()  # (every page is built with the window)
    assert ns.Options.ShowPage("Tools")  # (a page asked for by its English name, whatever it reads)
    N, G = ns.Nav, ns.GPS
    N.FUN = False
    N.SetStops(lua.eval("{ { x = -1441, y = -2332, cont = 0 } }"), False, "red")
    for t in range(4):
        lua.execute(f"AGPS_T = {300 + t * 0.5}")
        G.Update()
        if N.RedAsking():
            G.confirmBox.yes._scripts.OnClick(G.confirmBox.yes)
    arrow = lua.globals().AzerothGPSArrow
    arrow._scripts.OnUpdate(arrow, 1)
    assert N.StepsText(9)
    N.Clear()
    G.Update()


@pytest.mark.parametrize("code, word", [("deDE", "Klassenlehrer"), ("frFR", "maître de classe"), ("zhCN", "职业训练师")])
def test_the_search_takes_its_generic_words_in_the_games_language(code, word):
    # (the places' names are the shipped English ones; "class trainer" and the other generic words are typed in the
    # player's language too, and the class is the game's file name, MAGE, not UnitClass's translated "Magier")
    pytest.importorskip("lupa.lua51")
    from azerothgps.gameharness import start
    lua, ns = start(locale=code)
    lua.execute("UnitClass = function() return 'Magier', 'MAGE' end")
    english = ns.GPS.SearchPlaces("class trainer")
    found = ns.GPS.SearchPlaces(word)
    assert len(found) > 0 and [found[i].name for i in found] == [english[i].name for i in english]
    assert found[1].name == ns.L["Mage Trainer"] != "Mage Trainer"


@pytest.mark.parametrize("code, typed", [("deDE", "Bergbau"), ("deDE", "bergbaulehrer"), ("deDE", "mining"),
                                         ("frFR", "minage"), ("esES", "minería"), ("esMX", "Minería"),
                                         ("itIT", "estrazione"), ("ptBR", "mineração"),
                                         ("ruRU", "наставник горного"), ("ruRU", "Горного дела"),
                                         ("koKR", "채광"), ("zhCN", "采矿"), ("zhTW", "採礦")])
def test_the_search_finds_the_places_by_their_names_in_the_addons_language(code, typed):
    # (asked 2026-11-12: "I've set the add-on's language to German, so I should be able to search for "Bergbau," but
    # I'm still only able to search for "Mining."") the capitals' and towns' places are shown in the addon's language
    # and found by those names, in any case, and by the English ones too
    pytest.importorskip("lupa.lua51")
    from azerothgps.gameharness import start
    lua, ns = start(locale=code)
    found = ns.GPS.SearchPlaces(typed, 20)
    names = [found[i].name for i in found]
    assert ns.L["Mining Trainer"] in names, (typed, names)
    assert "Mining Trainer" not in names


def test_the_searchs_lowercase_takes_accented_and_cyrillic_capitals():
    pytest.importorskip("lupa.lua51")
    from azerothgps.gameharness import start
    lua, ns = start(locale="enUS")
    low = ns.GPS.SearchLower
    assert low("ÜBER ÀÉÎÕ Straße ×") == "über àéîõ straße ×"
    assert low("НАСТАВНИК Ёлка Ѐ Я") == "наставник ёлка ѐ я"
    assert low("采矿 Mining") == "采矿 mining"


def test_a_place_with_a_spot_before_its_kind_keeps_it_beside_the_city():
    # ("Sen'jin Village Alchemy Trainer", Razor Hill's: the kind translated, the spot with the town)
    pytest.importorskip("lupa.lua51")
    from azerothgps.gameharness import start
    lua, ns = start(locale="deDE")
    name, before = ns.GPS.PlaceName("Sen'jin Village Alchemy Trainer")
    assert (name, before) == ("Alchemielehrer", "Sen'jin Village")
    assert ns.GPS.PlaceName("Bloodhoof Village") == "Bloodhoof Village"  # (not a kind: as it is)
    assert ns.Layers.PlaceLabel("Orgrimmar Mining Trainer") == "Bergbaulehrer, Orgrimmar"  # (the map's icons)
    assert ns.GPS.PlaceName("Thistlefur Inn") == ("Gasthaus", "Thistlefur") and ns.GPS.PlaceName("Begin") == "Begin"


def test_a_player_can_pick_azerothgps_s_language():
    # (2026-11-09, for testing the languages on an English client too) `/agps language deDE` keeps it in
    # AzerothGPSDB.language, read as Locales.lua loads: the toc loads the saved variables first
    assert "## LoadSavedVariablesFirst: 1" in (ADDON / "AzerothGPS.toc").read_text(encoding="utf-8")
    lua = lupa.LuaRuntime()
    lua.execute('GetLocale = function() return "enUS" end; AzerothGPSDB = { language = "deDE" }')
    ns = lua.table()
    run = lua.eval("function(src, ns) return assert(load(src))('AzerothGPS', ns) end")
    for f in ("Locales/Locales.lua", "Locales/deDE.lua", "Locales/frFR.lua"):
        run((ADDON / f).read_text(encoding="utf-8"), ns)
    assert ns.LOCALE == "deDE" and ns.L["the game's"] == "die des Spiels"
    lua.execute('AzerothGPSDB = { language = "xxXX" }')  # (not a language there's text for: the game's)
    ns = lua.table()
    run((ADDON / "Locales/Locales.lua").read_text(encoding="utf-8"), ns)
    assert ns.LOCALE == "enUS"


def test_the_import_window_fits_a_long_language():
    # (the languages' screenshots, 2026-11-09: in German "Meine Kartendaten kopieren" ran out of its button, and the
    # row of boxes after it past the window's edge) buttons as wide as their text, the window as its longest row
    pytest.importorskip("lupa.lua51")
    from azerothgps.gameharness import start, toc_files
    # (the stand-in widgets measure text by its length and keep their widths: set before the addon's files run)
    sizes = """
        local orig = NewWidget
        NewWidget = function(...)
          local w = orig(...)
          w.GetStringWidth = function(s) return #(s._text or "") * 6 end
          w.GetTextWidth = function(s) return #(s._text or "") * 6 end
          w.SetWidth = function(s, v) s._w = v end
          w.SetSize = function(s, a) s._w = a end
          w.GetWidth = function(s) return s._w or 100 end
          return w
        end
    """
    first = toc_files()[0]
    lua, ns = start(locale="deDE", replace={first: sizes + (ADDON / first).read_text(encoding="utf-8")})
    ns.Import.Toggle()
    f = lua.globals().AzerothGPSImport
    mine = f.mine
    assert mine.GetWidth(mine) >= len(ns.L["Copy My Map Data"]) * 6 + 24
    assert f.GetWidth(f) >= f.needWidth > 520


def test_the_options_search_filters_the_settings_as_typed():
    # (asked 2026-11-11: "a search function for settings like how the game's options work that would filter instantly
    # as the player types")
    pytest.importorskip("lupa.lua51")
    from azerothgps.gameharness import start
    lua, ns = start(locale="enUS")
    O = ns.Options
    O.Show()
    s = O.search
    by_key = {}
    for i in range(1, len(O.settingControls) + 1):
        c = O.settingControls[i]
        if not c.mirror:
            by_key[c.key] = c
    shown = lambda key: by_key[key].control._shown is not False  # noqa: E731
    page = lambda pid: s.pages[O.pages[pid].index]  # noqa: E731
    try:
        assert shown("replaceMinimap") and shown("rotate") and shown("useFlights")
        rot = by_key["rotate"].control
        lua.globals().AGPS_ROT = rot
        lua.execute("AGPS_PT = nil AGPS_ROT.SetPoint = function(_, ...) AGPS_PT = { ... } end")
        row = lua.eval("(function() for _, r in ipairs(AGPS_NS.Options.search.pages[AGPS_NS.Options.pages.Map.index].rows) do "
                       "if r.w == AGPS_ROT then return r end end end)()")
        assert row is not None and row.y < -44
        lua.globals().AGPS_CHILD = page("Map").child
        lua.execute("AGPS_PARENT = {} AGPS_ROT.SetParent = function(_, to) AGPS_PARENT = { [to] = true } end")
        # (typed: only what matches, on its page; the pages with none dim in the list)
        assert O.Search("replace the minimap") is True
        assert shown("replaceMinimap") and not shown("rotate")
        assert page("Minimap").hit and not page("Routing").hit
        # (one list of every page's matches, whichever page was showing: asked 2026-11-11, "it should consider all
        # tabs ... shouldn't matter the tab when searching")
        assert s.results._shown is True and page("Map").scroll._shown is False
        assert O.CurrentPage() == 1
        assert O.Search("minimap") is True
        assert shown("replaceMinimap") and shown("shown") and shown("minimapRoute") and not shown("useFlights")
        assert page("Minimap").resY is not None and page("General").resY > page("Minimap").resY
        # (however the term is written: asked 2026-11-11, "they may search mini-map, mini map, minimap. Do this for
        # all terms")
        for q in ("mini-map", "mini map", "Mini-Map", "minimap"):
            assert O.Search(q) is True and shown("replaceMinimap") and not shown("useFlights"), q
        for q in ("worldmap", "world-map", "world map"):
            assert O.Search(q) is True and shown("useWorldMap"), q
        for q in ("hearth stone", "hearth-stone", "hearthstone"):
            assert O.Search(q) is True and shown("useHearthstone"), q
        assert O.Search("minimap") is True
        # (a page's name clicked meanwhile: still the results)
        s.Pick(O.pages["Map"].index)
        assert s.results._shown is True
        # (a word of the tooltip, any case; a section's name: all of that section; a page's name: all of the page)
        assert O.Search(rot.label.GetText(rot.label)) is True and shown("rotate") and lua.eval("AGPS_PT[3]") > row.y  # (moved up)
        assert lua.eval("AGPS_PARENT[AGPS_NS.Options.search.resultsChild]") is True
        assert O.Search("FLIGHT") is True and shown("useFlights") and not shown("avoidHostile")
        assert O.Search("world map") is True and shown("useWorldMap") and not shown("replaceMinimap")
        assert O.Search("routing") is True and shown("useFlights") and shown("avoidHostile")
        # (a page laid out by hand: all of it or none)
        assert O.Search("quick buttons") is True and page("Quick buttons").hit
        assert O.CurrentPage() == O.pages["Quick buttons"].index and s.results._shown is False
        # (nothing: a line saying so)
        assert O.Search("zzzqqq") is False and s.none._shown is True
        # (emptied: everything back where it was)
        assert O.Search("") is True
        assert s.none._shown is False and shown("rotate") and shown("replaceMinimap") and shown("avoidHostile")
        assert lua.eval("AGPS_PT[1]") == "TOPLEFT" and lua.eval("AGPS_PT[2]") == row.x and lua.eval("AGPS_PT[3]") == row.y
        assert lua.eval("AGPS_PARENT[AGPS_CHILD]") is True and s.results._shown is False
        assert page("Routing").hit and page("Map").hit
        # (every setting is found by its own label)
        for key, c in by_key.items():
            ctl = c.control
            label = None
            for name in ("label", "title"):
                r = ctl[name] if hasattr(ctl, "__getitem__") else None
                if r is not None and r.GetText:
                    label = r.GetText(r)
                    break
            if label:
                assert O.Search(label) is True, key
        O.Search("")
    finally:
        O.Search("")
        lua.execute("AGPS_ROT, AGPS_PT, AGPS_CHILD, AGPS_PARENT = nil, nil, nil, nil")
