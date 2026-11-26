"""Every way of making a stop at a known NPC carries the NPC (its creature id and name: the Target button; its height: the
floor rules), Kooki3z 2026-11-22: "npc target button stopped working testing with other npcs" (a stop double-clicked on
an inside map's NPC dot, under a roof), "Gelman Stonehand routing ends too early underneath them" (Stormwind's Dwarven
District, his floor 103.4, the floor's roads 96, a stairs road 2 yd off him up to 99.2), and "consider /way points too".
"""

import pytest

GELMAN = 5513
GELMAN_XYZ = (-8434.0, 693.4, 103.4)
ARDWYN, ALLAN = 1312, 1315  # (Stormwind's Trade District, 2.9 yd apart: Ardwyn Cailen, Allan Hafgan)
ARDWYN_XY, ALLAN_XY = (-8862.5, 804.5), (-8863.5, 801.8)
BRILL_INN = (2269.5, 244.9, 0)
ARRIVED = "Arrived"
STORMWIND_MAP = 1453


def guid(npc):
    return f"Creature-0-1-0-1-{npc}-0000ABCDEF"


@pytest.fixture(scope="module")
def game():
    pytest.importorskip("lupa.lua51")
    from azerothgps.gameharness import start
    lua, ns = start()
    ns.Nav.FUN = False
    return lua, ns


@pytest.fixture()
def clean(game):
    lua, ns = game
    was = ns.db.npcs
    ns.db.npcs = lua.eval("{}")
    lua.execute("AGPS_GUIDS = nil AGPS_OLD_CID = rawget(_G, 'CheckInteractDistance') "
                "CheckInteractDistance = function() return AGPS_NEAR == true end AGPS_NEAR = nil")
    ns.Nav.ResetTrack()
    yield lua, ns
    lua.execute("AGPS_GUIDS = nil AGPS_NEAR = nil CheckInteractDistance = AGPS_OLD_CID")
    ns.db.npcs = was
    ns.Nav.Clear()
    ns.GPS.UpdateTargetButton()


def _at(lua, x, y):
    lua.execute(f"AGPS_POS[1], AGPS_POS[2], AGPS_POS[3] = {x}, {y}, 0")


def _status(lua, ns, x, y):
    _at(lua, x, y)
    return ns.Nav.Status(x, y, 0) or ""


def _confirm(ns):
    ns.GPS.ConfirmPendingOnClose()
    return ns.Nav.dest


def _button(lua, ns, t):
    G = ns.GPS
    lua.execute(f"AGPS_T = {t}")
    G.Update()
    G.navPanel.Show(G.navPanel)
    ns.Arrow.dir.Hide(ns.Arrow.dir)
    G.UpdateTargetButton()
    return G.targetBtn


def _way(lua, ns, x, y, name=None):
    # (a /way at world (x, y) in Stormwind City's map, as Import.lua reads one)
    b = ns.Maps[STORMWIND_MAP].bounds
    u = (b[4] - y) / (b[4] - b[2]) * 100
    v = (b[3] - x) / (b[3] - b[1]) * 100
    w = lua.eval("{}")
    w.mapID, w.x, w.y = STORMWIND_MAP, u, v
    if name:
        w.name = name
    stop = ns.Import.ToStop(w)
    assert abs(stop.x - x) < 0.01 and abs(stop.y - y) < 0.01
    return stop


def test_an_npc_dot_double_clicked_on_an_inside_map_is_that_npcs_stop(clean):
    lua, ns = clean
    G, N, st = ns.GPS, ns.Nav, ns.settings.gps
    _, _, by_name = ns.Layers.ShippedNpcs()
    renee = int(by_name["innkeeper renee"][1].id)
    lua.execute(f"""
      AGPS_INDOORS_NPC = {{ IsIndoors, GetMinimapZoneText }}
      IsIndoors = function() return true end
      GetMinimapZoneText = function() return "Gallows' End Tavern" end
      AGPS_POS[1], AGPS_POS[2], AGPS_POS[3] = {BRILL_INN[0]}, {BRILL_INN[1]}, 0
    """)
    zoom = st.zoom
    try:
        st.zoom = 60.0
        G.Follow()
        lua.execute("AGPS_T = (AGPS_T or 0) + 6")
        G.Redraw()
        G.Update()
        dots = [w for w in lua.eval("AGPS_WIDGETS").values() if w._shown and w.npc and w.npc.id == renee]
        assert dots, "no dot for Innkeeper Renee in Brill's inn"
        N.Clear()
        dots[0]._scripts.OnDoubleClick(dots[0])
        d = _confirm(ns)
        assert d.npcId == renee and str(d.npcName) == "Innkeeper Renee" and d.z is not None
    finally:
        st.zoom = zoom
        lua.execute("IsIndoors, GetMinimapZoneText = AGPS_INDOORS_NPC[1], AGPS_INDOORS_NPC[2] AGPS_T = AGPS_T + 6")
        G.Redraw()


def test_quick_find_and_a_named_stop_at_an_npcs_spawn_carry_it(clean):
    lua, ns = clean
    G, N = ns.GPS, ns.Nav
    x, y, z = GELMAN_XYZ
    _at(lua, x + 40, y)
    found = G.QuickFindNearest("mining trainer")
    assert found is not None and found.npc and found.id
    G.PickSearchEntry(found)
    d = _confirm(ns)
    assert d.npcId == found.id and d.z is not None
    # (a city place or another icon at his spot, named, no NPC given: his, G.NpcAtSpot)
    N.Clear()
    G.AddStopAt(x, y, "Mining Trainer", 0, None, z)
    assert _confirm(ns).npcId == GELMAN
    # (a plain double-click on the map there, no name: a spot, as before)
    N.Clear()
    G.AddStopAt(x + 0.3, y)
    assert _confirm(ns).npcId is None


def test_gelman_stonehand_is_a_floor_up_and_not_arrived_under_him(clean):
    lua, ns = clean
    G, N = ns.GPS, ns.Nav
    x, y, z = GELMAN_XYZ
    way, dz = list(N.StopOffGround(lua.eval(f"{{ x = {x}, y = {y}, z = {z}, cont = 0 }}")))[:2]
    assert way == "up" and dz == pytest.approx(z - 96, abs=0.5)  # (the floor's roads, not the stairs road by him)
    for made in ("map", "search"):
        N.Clear()
        N.ResetTrack()
        if made == "map":
            G.AddStopAt(x, y, "Gelman Stonehand", 0, None, z)
        else:
            e = lua.eval(f"{{ name = 'Gelman Stonehand', sub = '', npc = true, id = {GELMAN}, cont = 0, x = {x}, "
                         f"y = {y}, z = {z} }}")
            _at(lua, x + 30, y)
            G.PickSearchEntry(e)
        d = _confirm(ns)
        assert d.npcId == GELMAN, made
        # (under him: the street's floor followed, within 3 yd, targeted in range: not there)
        lua.execute("AGPS_T = 500")
        N.AnchorFloor(0, x + 2.5, y, 96.0)
        assert ARRIVED not in (N.Status(x + 2.5, y, 0) or ""), made
        assert _button(lua, ns, 501)._shown
        lua.execute(f"AGPS_GUIDS = {{ target = '{guid(GELMAN)}' }} AGPS_NEAR = true")
        assert ARRIVED not in (N.Status(x + 2.5, y, 0) or ""), made
        # (his floor followed: there)
        lua.execute("AGPS_T = 502")
        N.AnchorFloor(0, x + 2, y, z)
        assert ARRIVED in (N.Status(x + 2, y, 0) or ""), made
        # (or his window opened)
        G.AddStopAt(x, y, "Gelman Stonehand", 0, None, z)
        _confirm(ns)
        N.ResetTrack()
        assert ARRIVED not in (N.Status(x + 2, y, 0) or "")
        N.OnNpcWindow(GELMAN)
        assert ARRIVED in (N.Status(x + 2, y, 0) or "")
        lua.execute("AGPS_GUIDS = nil AGPS_NEAR = nil")


def test_a_way_at_an_npc_carries_it_and_is_not_arrived_under_him(clean):
    lua, ns = clean
    N = ns.Nav
    x, y, z = GELMAN_XYZ
    for name in ("Gelman Stonehand", "Mining Trainer"):
        s = _way(lua, ns, x + 2, y + 1, name)  # (a few yards off his spawn, as a /way rounds)
        assert s.npcId == GELMAN and s.z == pytest.approx(z), name
    assert _way(lua, ns, x + 2, y + 1).npcId is None  # (no name, another NPC within 5 yd there too: neither)
    # (a text naming someone else there: none)
    assert _way(lua, ns, x + 2, y + 1, "Some Mailbox").npcId is None
    # (its route: the Target button, and not arrived under him)
    N.SetStops(lua.eval("function(s) return { s } end")(_way(lua, ns, x + 2, y + 1, "Gelman Stonehand")), False, "red")
    assert N.dest.npcId == GELMAN
    lua.execute("AGPS_T = 600")
    N.AnchorFloor(0, x + 2.5, y, 96.0)
    assert ARRIVED not in (N.Status(x + 2.5, y, 0) or "")
    assert _button(lua, ns, 601)._shown


def test_a_way_in_the_open_stays_a_spot(clean):
    lua, ns = clean
    N = ns.Nav
    s = _way(lua, ns, -8700.0, 600.0, "Meet here")
    assert s.npcId is None and s.z is None
    s = _way(lua, ns, -8700.0, 600.0)
    assert s.npcId is None
    N.SetStops(lua.eval("function(s) return { s } end")(s), False, "red")
    assert ARRIVED in _status(lua, ns, -8700.0 + 5, 600.0)  # (the 10 yd circle, as before)


def test_a_way_between_two_npcs_attaches_one_only_by_its_name(clean):
    lua, ns = clean
    mx, my = (ARDWYN_XY[0] + ALLAN_XY[0]) / 2, (ARDWYN_XY[1] + ALLAN_XY[1]) / 2
    assert _way(lua, ns, mx, my).npcId is None  # (two this near, no name: neither)
    assert _way(lua, ns, mx, my, "Staves Merchant").npcId == ALLAN
    assert _way(lua, ns, mx, my, "Ardwyn Cailen").npcId == ARDWYN
    assert _way(lua, ns, mx, my, "Somebody").npcId is None


def _place(lua, ns, ui, name):
    c = ns.CityPlaces[ui]
    i = 1
    while c[i] is not None:
        p = c[i]
        if p[3] == name:
            x, y, pc = ns.Layers.MapToWorld(ui, p[1] / 100, p[2] / 100)
            return x, y, pc, p[4]
        i += 1
    raise AssertionError(name)


def test_a_city_place_with_one_trainer_goes_to_that_npc(clean):
    # (Kooki3z, 2026-11-22: "Locations that have a single trainer like the first aid trainer in ironforge, have routing
    # go to the NPC")
    lua, ns = clean
    G, N = ns.GPS, ns.Nav
    ns.CharDB().faction = "Alliance"
    x, y, c, z = _place(lua, ns, 1455, "Ironforge First Aid Trainer")
    _at(lua, x + 100, y)
    G.AddStopAt(x, y, "Ironforge First Aid Trainer", c, None, z)  # (as the search's place row and its map icon do)
    d = _confirm(ns)
    assert d.npcId == 5150 and str(d.npcName) == "Nissa Firestone"
    assert (d.x, d.y, d.z) == (pytest.approx(-4876.6), pytest.approx(-1149.1), pytest.approx(512.5))
    assert not _button(lua, ns, 700)._shown  # (100 yd off: not yet)
    _at(lua, d.x + 10, d.y)
    assert _button(lua, ns, 701)._shown


def test_a_city_place_with_several_npcs_picks_the_one_nearest_the_player(clean):
    lua, ns = clean
    G, N, Lay = ns.GPS, ns.Nav, ns.Layers
    ns.CharDB().faction = "Alliance"
    x, y, c, z = _place(lua, ns, 1453, "Stormwind Bank")
    bankers = []
    for n in Lay.ShippedNpcs()[0].values():
        if n.svc and "b" in str(n.svc) and n.side in ("A", "B"):
            sp = n.spawns
            for i in range(1, len(sp) + 1, 4):
                if (sp[i + 1] - x) ** 2 + (sp[i + 2] - y) ** 2 <= Lay.PLACE_NPC_YD ** 2:
                    bankers.append((n.id, sp[i + 1], sp[i + 2]))
    assert len(bankers) >= 2
    far = max(bankers, key=lambda b: (b[1] - x) ** 2 + (b[2] - y) ** 2)
    near = min(bankers, key=lambda b: (b[1] - x) ** 2 + (b[2] - y) ** 2)
    assert far[0] != near[0]
    _at(lua, far[1] + 1, far[2])  # (by the far banker: that one)
    G.AddStopAt(x, y, "Stormwind Bank", c, None, z)
    assert _confirm(ns).npcId == far[0]
    N.Clear()
    _at(lua, -5000.0, -1000.0)  # (not in the city: the one nearest the place's spot)
    G.AddStopAt(x, y, "Stormwind Bank", c, None, z)
    assert _confirm(ns).npcId == near[0]


def test_a_class_trainer_place_picks_that_classs_trainer_not_its_portal_trainer(clean):
    # (Kooki3z, 2026-11-23: "in UC for mage trainer you actually chose a portal trainer": Lexington Mortaim, Portal
    # Trainer, trains mages too and stands nearer the place's spot)
    lua, ns = clean
    Lay = ns.Layers
    ns.CharDB().faction = "Horde"
    x, y, c, z = _place(lua, ns, 1458, "Undercity Mage Trainer")
    n = Lay.PlaceNpc("Undercity Mage Trainer", c, x, y)
    assert n.id in (4566, 4567, 4568)  # (Kaelystia Hatebringer, Pierce Shackleton, Anastasia Hartwell)
    lx, ly = 1778.2, 65.5  # (Lexington Mortaim: by him, still a mage trainer)
    n = Lay.PlaceNpc("Undercity Mage Trainer", c, x, y, lx, ly, c)
    assert n.id in (4566, 4567, 4568)
    ns.CharDB().faction = "Alliance"


def test_a_city_place_with_no_npc_of_its_kind_stays_the_places_spot(clean):
    lua, ns = clean
    G, Lay = ns.GPS, ns.Layers
    ns.CharDB().faction = "Horde"
    x, y, c, z = _place(lua, ns, 1454, "Orgrimmar Transmogrifier")
    assert Lay.PlaceNpc("Orgrimmar Transmogrifier", c, x, y) is None
    _at(lua, x + 50, y)
    G.AddStopAt(x, y, "Orgrimmar Transmogrifier", c, None, z)
    d = _confirm(ns)
    assert (d.x, d.y) == (pytest.approx(x), pytest.approx(y))
    assert Lay.PlaceNpc("Some Spot", 0, x, y) is None  # (not a place's name: nothing)
    ns.CharDB().faction = "Alliance"


def test_ironforges_first_aid_trainer_on_her_balcony_is_a_floor_up_not_under_the_mountain(clean):
    # (Kooki3z, 2026-11-22: "arrived Ironforge First Aid Trainer (distance): 9.8 yd, stop z 512.5, off no, roads ground
    # 759.8, floor 505.5, target -, npc 5150": her spot is off the city's own cells, so the ground over Ironforge was
    # taken; the city's roads 2 yd from her are at 505.8)
    lua, ns = clean
    G, N = ns.GPS, ns.Nav
    ns.CharDB().faction = "Alliance"
    x, y, z = -4876.6, -1149.1, 512.5
    way, dz = list(N.StopOffGround(lua.eval(f"{{ x = {x}, y = {y}, z = {z}, cont = 0 }}")))[:2]
    assert way == "up" and dz == pytest.approx(6.7, abs=0.3)
    px, py, pc, pz = _place(lua, ns, 1455, "Ironforge First Aid Trainer")
    _at(lua, x + 9.8, y)
    G.AddStopAt(px, py, "Ironforge First Aid Trainer", pc, None, pz)
    d = _confirm(ns)
    assert d.npcId == 5150
    # (her spot is off the city's own cells: no floor followed there; the floor under her known from before or not,
    # she's a floor off: 9.8 yd away and right under her, not there; her window: there)
    assert ARRIVED not in (N.Status(x + 9.8, y, 0) or "") and N.dest is not None
    assert ARRIVED not in (N.Status(x + 2.5, y, 0) or "")
    N.OnNpcWindow(5150)
    assert ARRIVED in (N.Status(x + 2.5, y, 0) or "")


def test_an_npc_up_on_open_land_is_still_judged_by_the_ground(clean):
    # (Booty Bay's Auctioneer Kresky, up on its decks: no road with a height by him, the ground 10 yd under him)
    lua, ns = clean
    N = ns.Nav
    d = lua.eval("{ x = -14446.5, y = 448.4, z = 4.1, cont = 0 }")
    r = list(N.StopOffGround(d))
    assert r[0] == "up" and r[1] == pytest.approx(10.1, abs=0.5)
    assert str(N.lastOffFloor.roads).startswith("ground")
