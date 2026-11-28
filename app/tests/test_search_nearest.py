"""Search results nearest first (1.4.2, Kooki3z 2026-11-27, "searches should always be closest match first"): on
Zephras Isle, "tailoring" listed the Tailoring Trainers of Stormwind, Darnassus and Ironforge first (their names start
with it) and the isle's own tailors after them, and only one row showed its yards (a long place's grey text cut them
off the row). Now what matches is listed by how near it is: on the player's continent or island by its yards, then
elsewhere by how far it is on the world map; how well it matches only between those as near, a match inside a word
only after all the rest. The yards come before the grey text, so every row on the player's land shows them."""
import pytest

ZEPHRAS = (2026.7, 615.6, 2991)  # (Valanaar, Zephras Isle 65, 79)
AUBERDINE = (6500.0, 450.0, 1)  # (Darkshore)


@pytest.fixture(scope="module")
def game():
    pytest.importorskip("lupa.lua51")
    from azerothgps.gameharness import start
    lua, ns = start()
    return lua, ns


@pytest.fixture
def alliance(game):
    lua, ns = game
    was_npcs, was_pins = ns.db.npcs, ns.db.pins
    ns.db.npcs, ns.db.pins = lua.eval("{}"), lua.eval("{}")
    cdb = ns.CharDB()
    was_fac = cdb.faction
    cdb.faction = "Alliance"
    lua.execute("AGPS_SN = { pos = AGPS_POS }")
    yield lua, ns
    lua.execute("AGPS_POS = AGPS_SN.pos AGPS_SN = nil")
    ns.db.npcs, ns.db.pins = was_npcs, was_pins
    cdb.faction = was_fac


def _at(lua, spot):
    lua.execute(f"AGPS_POS = {{ {spot[0]}, {spot[1]}, {spot[2]} }}")


def _search(ns, text, max=8):
    res = ns.GPS.SearchPlaces(text, max)
    return [res[i] for i in range(1, len(res) + 1)]


def _here(ns, e, spot):
    return e.cont is not None and ns.Geo.Base(e.cont) == ns.Geo.Base(spot[2])


def _check_nearest_first(ns, res, spot):
    """Those on the player's land first, by their yards; each of them with its yards, in its row before the grey
    text; those elsewhere after, without yards."""
    here = [e for e in res if _here(ns, e, spot)]
    assert res[:len(here)] == here, [str(e.name) for e in res]
    yds = [e.yd for e in here]
    assert all(y is not None for y in yds) and yds == sorted(yds), yds
    for e in here:
        row = str(ns.GPS.SearchRowText(e))
        shown = str(ns.Nav.FormatDistance(e.yd))
        assert shown in row and row.index(shown) < row.index("|cff9d9d9d"), row  # (never cut off by a long place)
    assert all(e.yd is None for e in res[len(here):])
    return here


def test_on_zephras_isle_the_isles_tailors_come_before_the_capitals_trainers(alliance):
    lua, ns = alliance
    _at(lua, ZEPHRAS)
    res = _search(ns, "tailoring")
    names = [str(e.name) for e in res]
    here = _check_nearest_first(ns, res, ZEPHRAS)
    assert {str(e.name) for e in here} >= {"Taleen Shimmerthread", "Othesia Evengale"}, names
    assert str(res[0].name) == "Othesia Evengale"  # (Valanaar's own, under 100 yd)
    trainers = [i for i, e in enumerate(res) if str(e.name) == "Tailoring Trainer"]
    assert trainers and min(trainers) >= len(here), names  # (Stormwind's and the rest: after the isle's)


def test_from_darkshore_its_tailors_come_before_stormwinds_trainer(alliance):
    lua, ns = alliance
    _at(lua, AUBERDINE)
    res = _search(ns, "tailoring", 12)
    names = [str(e.name) for e in res]
    here = _check_nearest_first(ns, res, AUBERDINE)
    assert [str(e.name) for e in here[:2]] in (["Grondal Moonbreeze", "Valdaron"], ["Valdaron", "Grondal Moonbreeze"])
    assert all(e.yd < 100 for e in here[:2])
    # (Kalimdor's further ones on, Nighthaven's Darnall before Darnassus's: nearer; the Eastern Kingdoms' after)
    assert names[2:4] == ["Darnall", "Elynna"], names
    sw = [i for i, e in enumerate(res) if str(e.name) == "Tailoring Trainer" and "Stormwind" in str(e.sub)]
    assert not sw or sw[0] >= len(here), names


def test_elsewhere_the_nearest_land_first_on_the_world_map(alliance):
    lua, ns = alliance
    _at(lua, AUBERDINE)
    G, Geo = ns.GPS, ns.Geo
    res = _search(ns, "tailoring", 60)
    away = [e for e in res if not _here(ns, e, AUBERDINE)]
    assert away and all(e.yd is None for e in away)
    pu, pv = Geo.WorldFraction(AUBERDINE[2], AUBERDINE[0], AUBERDINE[1])

    def far(e):
        u, v = Geo.WorldFraction(e.cont, e.x, e.y)
        return ((u - pu) ** 2 + (v - pv) ** 2) ** 0.5

    lands, nearest = [], {}
    for e in away:
        b = Geo.Base(e.cont)
        if b not in lands:
            lands.append(b)
        nearest[b] = min(nearest.get(b, 9), far(e))
    assert len(lands) >= 2 and lands == sorted(lands, key=lambda b: nearest[b]), (lands, nearest)
    # (each land's own together: the Eastern Kingdoms' and Zephras Isle's never mixed)
    order = [Geo.Base(e.cont) for e in away]
    assert order == sorted(order, key=lands.index)
    # (on one land, the best match first, then the nearer on the world map: Tailoring Trainer before the tailors)
    for b in lands:
        on = [e for e in away if Geo.Base(e.cont) == b]
        names = [str(e.name) for e in on]
        if "Tailoring Trainer" in names:
            assert names[0] == "Tailoring Trainer", names
    # (and the world map's spot is the one the routes' drawing uses across the sea)
    x, y = Geo.ToContinent(1, AUBERDINE[0], AUBERDINE[1], 0)
    u, v = Geo.WorldFraction(0, x, y)
    assert abs(u - pu) < 1e-9 and abs(v - pv) < 1e-9
    assert G.SEARCH_FAR_KEY > 100000  # (past any yards on one land)


def test_a_word_inside_a_name_comes_after_every_better_match(alliance):
    lua, ns = alliance
    _at(lua, AUBERDINE)
    G = ns.GPS
    assert G.SearchWordStart("dun morogh", 5) and G.SearchWordStart("inn", 1) and G.SearchWordStart("sen'jin", 5)
    assert not G.SearchWordStart("brinna", 3)
    res = _search(ns, "inn", 40)
    inside = [i for i, e in enumerate(res)
              if not any(G.SearchWordStart(s, s.find("inn") + 1) for s in (str(e.lower), str(e.en or ""))
                         if "inn" in s) and "inn" in str(e.lower)]
    better = [i for i, e in enumerate(res) if i not in inside]
    assert better and (not inside or max(better) < min(inside)), [str(e.name) for e in res]


def test_with_the_players_spot_unknown_the_best_match_comes_first(alliance):
    lua, ns = alliance
    lua.execute("AGPS_POS = nil")
    res = _search(ns, "tailoring")
    assert res and all(e.yd is None for e in res)
    # (names starting with it first, shorter first: "Tailoring Trainer", as before the nearness)
    assert str(res[0].name) == "Tailoring Trainer"
