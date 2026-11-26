"""Jumps on the route as coils, avoided or taken with a fall spell picked (1.4.0, Kooki3z 2026-11-23: "idea for jumps,
show them as coiled lines like swimming does with wavy lines, allow right click to avoid the jump using spell or item
(like parachutes). Also distance of the fall should be allowed up to the spell. Like the spell for skybourne only lasts
a few seconds while you can slow fall for 30s which would go much further").

A jump down a ledge or across a gap is drawn as a dashed coil (G.CoilLines) on the GPS map, in the world map and on the
minimap; right-clicking it offers "Avoid Spell Jumps" (a spell jump's) or "Avoid Jumps" (a plain one's) for the leg to
its stop (Nav.AvoidLegJumps, item 26; Nav.AvoidJump's spot bans remain for saved trips) and "Use <spell>" for each fall spell ready whose reach is
enough (Nav.PickFallSpell); each spell's reach is its own (FallSpells.RowDrop: its buff's seconds at the slow fall's
7 yd a second).
"""

import math

import pytest

from test_fall_spells import FEATHERS, HIGH, LOW, MAGE, NO_FEATHERS, SKYBORNE, WALL, cliff, kinds  # noqa: F401
from test_map_redraw import game  # noqa: F401
from test_world_map_host import SETUP as WM_SETUP

MAGE_SKYBORNE = "IsPlayerSpell = function(id) return id == 130 or id == 1271049 end"


def drop_top(ns, r):
    ks = kinds(r)
    i = ks.index(ns.Router.KIND_DROP) + 1
    return r.pts[2 * i - 1], r.pts[2 * i]


def test_each_fall_spell_reaches_as_far_as_its_buff_lasts():
    """Slow Fall's 30 s, Levitate's 120 s and Gliding on Air's 10 s, less the cast's margin, at the slow fall's 7 yd a
    second (Levitate's capped): each its own reach, not one number for all."""
    from azerothgps.gameharness import start

    lua, ns = start()
    FS = ns.FallSpells
    by = {FS.RowKey(FS.SPELLS[i]): FS.RowDrop(FS.SPELLS[i]) for i in range(1, len(FS.SPELLS) + 1)}
    assert by["Slow Fall"] == pytest.approx(28 * 7)
    assert by["Levitate"] == FS.DROP_CAP
    assert by["Gliding on Air"] == pytest.approx(8 * 7)
    assert by["Gliding on Air"] < by["Slow Fall"] < by["Levitate"]
    # (the items: the client's 10 s Slow Fall on the parachute cloaks, 15 s Propellerstorm, 30 and 45 s Lightheaded)
    assert by["item:10518"] == by["item:10684"] == by["Gliding on Air"]
    assert by["item:275729"] == pytest.approx(13 * 7)
    assert by["item:21171"] == by["Slow Fall"] and by["item:274616"] == pytest.approx(43 * 7)
    # (across: running on while slowed)
    glide = {FS.RowKey(FS.SPELLS[i]): FS.RowGlide(FS.SPELLS[i]) for i in range(1, len(FS.SPELLS) + 1)}
    assert glide["Gliding on Air"] == 70 and glide["Slow Fall"] == 210


def test_a_worn_parachute_cloak_or_one_in_the_bags_is_a_fall_item(cliff):  # noqa: F811
    """A warrior wearing a cloak with Slow Fall (item 10518): the cliff is jumped with it, "Use <item>, then jump
    down", the use button uses the item; in the bags only, not (a "Use:" on gear needs it worn); a consumable one
    (10684) from the bags; on its cooldown, none."""
    lua, ns, be, route = cliff
    FS = ns.FallSpells
    lua.execute("AGPS_IE = { IsEquippedItem, GetItemCount }")
    try:
        be("IsPlayerSpell = function() return false end",
           "GetItemCount = function(id) return id == 10518 and 1 or 0 end", "IsEquippedItem = function() return false end")
        assert FS.Current() is None and route().length > 200
        be("IsEquippedItem = function(id) return id == 10518 end")
        c = FS.Current()
        assert c and c.row.item == 10518 and 55 < c.drop < 57
        assert route().length < 160
        t = FS.CastFor(lua.table(kind="drop", dist=5, dropYd=50))
        assert t.item == 10518 and t.spell is None and t.fall
        assert ns.Turns.NowText(lua.table(kind="drop", dist=5, dropYd=50), lua.eval("function(v) return v end")).startswith("Use ")
        be("IsEquippedItem = function() return false end", "GetItemCount = function(id) return id == 10684 and 2 or 0 end")
        assert FS.Current().row.item == 10684
        # (its cooldown ending within WAIT_MAX: still counted, the trip planner weighs the wait; longer: none)
        be("C_Container.GetItemCooldown = function(id) if id == 10684 then return AGPS_T - 1, 30, 1 end return 0, 0, 1 end")
        assert FS.Current().row.item == 10684 and 28 < FS.RowCooldown(FS.Current().row) < 30
        be("C_Container.GetItemCooldown = function(id) if id == 10684 then return AGPS_T - 1, 600, 1 end return 0, 0, 1 end")
        assert FS.Current() is None
    finally:
        lua.execute("IsEquippedItem, GetItemCount = AGPS_IE[1], AGPS_IE[2] C_Container.GetItemCooldown = function() return 0, 0, 1 end")
        FS.Refresh()


def test_avoiding_a_jump_goes_round_for_the_trip(cliff):  # noqa: F811
    lua, ns, be, route = cliff
    N = ns.Nav
    be(MAGE, FEATHERS)
    r = route()
    assert r.length < 160 and ns.Router.KIND_DROP in kinds(r)
    x, y = drop_top(ns, r)
    try:
        assert N.AvoidJump(1, x, y) is True
        assert N.JumpBanned(1, x + 3, y) and not N.JumpBanned(1, x + 40, y) and not N.JumpBanned(0, x, y)
        assert N.AvoidJump(1, x + 1, y) is False  # (the same jump: once)
        r2 = route()
        assert r2.length > 200 and ns.Router.KIND_DROP not in kinds(r2), r2.length
    finally:
        N.ResetJumps()
        ns.Router.Reset()
    assert N.jumpBans[1] is None
    assert route().length < 160  # (a new trip jumps again)


def test_a_picked_fall_spell_plans_the_drops_with_its_reach(cliff):  # noqa: F811
    """A mage who is also Skyborne: Slow Fall's reach (196 yd) by default; "Use Gliding on Air" on a jump plans with
    its 56 yd instead (still enough for the 50 yd cliff), said in the step; the pick dropped with the trip."""
    lua, ns, be, route = cliff
    N, FS = ns.Nav, ns.FallSpells
    be(MAGE_SKYBORNE, FEATHERS)
    try:
        assert FS.Current().row.name == "Slow Fall" and N.SafeDrop() > 190
        assert N.PickFallSpell("Gliding on Air") is True
        c = FS.Current()
        assert c.row.name == "Gliding on Air" and 55 < N.SafeDrop() < 57
        assert route().length < 160
        # (no feathers: Slow Fall isn't ready, the pick still is)
        be(NO_FEATHERS)
        assert FS.Current().row.name == "Gliding on Air"
        # (the pick not ready, its cooldown: the other, when there's one)
        be(FEATHERS, "GetSpellCooldown = function(id) if id == 1271049 then return AGPS_T - 10, 180, 1 end return 0, 0, 1 end")
        assert FS.Current().row.name == "Slow Fall"
    finally:
        lua.execute("GetSpellCooldown = function() return 0, 0, 1 end")
        N.ResetJumps()
        FS.Refresh()
    assert N.fallPick is None and FS.Current().row.name == "Slow Fall"


def test_coil_lines_loop_are_dashed_and_short_jumps_drawn_long_enough(game):  # noqa: F811
    lua, ns = game
    G = ns.GPS
    got = lua.eval("{}")
    put = lua.eval("function(t) return function(a, b, c, d) t[#t + 1] = { a, b, c, d } end end")(got)
    G.waveLeft = G.SWIM_WAVE_MAX
    G.CoilLines(0, 0, 70, 0, 4, 7, put)
    lines = [tuple(got[i][k] for k in range(1, 5)) for i in range(1, len(got) + 1)]
    loops = 10
    steps = loops * G.JUMP_COIL_STEPS
    # (solid, Kooki3z 2026-11-23: every line of the loops drawn)
    assert G.JUMP_COIL_OFF == 0 and len(lines) == steps
    # (it loops: some lines run back along the jump; off to both sides of it; ends on it)
    assert any(l[2] < l[0] - 0.5 for l in lines)
    assert max(l[3] for l in lines) > 3 and min(l[3] for l in lines) < -3
    assert G.waveLeft == G.SWIM_WAVE_MAX - steps
    # a jump 4 px long on the screen: drawn JUMP_MIN_PX long round its middle
    lua.execute("for k in pairs(...) do (...)[k] = nil end", got)
    G.CoilLines(10, 10, 14, 10, 4, 7, put)
    xs = [got[i][k] for i in range(1, len(got) + 1) for k in (1, 3)]
    assert min(xs) <= 12 - G.JUMP_MIN_PX / 2 + 0.5 and max(xs) >= 12 + G.JUMP_MIN_PX / 2 - 4
    # (out of lines for the redraw: a straight line)
    lua.execute("for k in pairs(...) do (...)[k] = nil end", got)
    G.waveLeft = 3
    G.CoilLines(0, 0, 70, 0, 4, 7, put)
    assert len(got) == 1


@pytest.fixture
def jump_trip(game):  # noqa: F811
    """The whole addon, a mage with feathers on the Barrens cliff's top (test_fall_spells' wall), the stop below."""
    lua, ns = game
    N, st = ns.Nav, ns.settings.gps
    cdb = ns.CharDB()
    saved = (cdb.faction, st.zoom, st.fastestOrder)
    ns.db.tracks = lua.eval(WALL)
    ns.Passability.RefreshWalls()
    lua.execute("AGPS_JT = { IsPlayerSpell, GetItemCount }")
    lua.execute(MAGE)
    lua.execute(FEATHERS)
    ns.FallSpells.Refresh()

    def settle():
        for _ in range(8):
            lua.execute("AGPS_T = AGPS_T + 0.5")
            ns.GPS.Update()

    def run():
        st.zoom, st.fastestOrder = 300, False
        cdb.faction = "Horde"
        N.Clear()
        ns.Router.Reset()
        lua.execute(f"AGPS_MAP = 1413 AGPS_POS = {{ {HIGH[0]}, {HIGH[1]}, 1 }}")  # (the Barrens)
        N.SetStops(lua.eval(f"{{ {{ x = {LOW[0]}, y = {LOW[1]}, cont = 1, name = 'stop' }} }}"), False, "red")
        N.Invalidate(True, True)
        ns.GPS.Follow()
        settle()
        return N.route

    run.settle = settle
    try:
        yield run
    finally:
        cdb.faction, st.zoom, st.fastestOrder = saved
        N.Clear()
        lua.execute("IsPlayerSpell, GetItemCount = AGPS_JT[1], AGPS_JT[2]")
        ns.FallSpells.Refresh()
        ns.db.tracks = lua.eval("{}")
        ns.Passability.RefreshWalls()
        lua.execute("AGPS_MAP = nil AGPS_POS = { 2254.0, 293.0, 0 } AGPS_T = AGPS_T + 1")
        ns.GPS.Follow()
        ns.GPS.UpdateMinimapRoute(True)


def _route_kinds(r):
    out = []
    for p in range(1, len(r.parts) + 1):
        part = r.parts[p]
        out += [part.kinds[i] for i in range(1, len(part.pts) // 2)]
    return out


def test_a_jump_is_a_coil_and_right_click_avoids_it(game, jump_trip):  # noqa: F811
    lua, ns = game
    N, G = ns.Nav, ns.GPS
    r = jump_trip()
    if ns.Router.KIND_DROP not in _route_kinds(r):
        pytest.skip("the whole addon's route here doesn't jump the test cliff")
    G.Update()
    assert G.jumpSegN > 0
    sg = G.jumpSegs[1]
    info = G.JumpInfo(sg)
    assert info.kind == "drop" and info.cont == 1 and abs(info.dz - 50) < 1.5, info.dz
    tip = G.JumpTip(info)
    assert str(tip.title) == "Spell jump" and "Right-click" in str(tip.lines[len(tip.lines)])
    # (on the minimap: more lines than the same route with no jump coiled)
    coiled = G.UpdateMinimapRoute(True)
    cx, cy = lua.eval("function(f) return f:GetCenter() end")(G.markLayer)
    mx, my = cx + (sg[1] + sg[3]) / 2, cy + (sg[2] + sg[4]) / 2
    lua.execute(f"AGPS_CUR = GetCursorPosition GetCursorPosition = function() return {mx}, {my} end")
    try:
        assert G.JumpClick() is True
    finally:
        lua.execute("GetCursorPosition = AGPS_CUR")
    ask = G.jumpAsk
    # (item 26: a spell jump's right-click avoids the leg's spell jumps)
    assert ask._shown and str(ask["items"][1].text) == "Avoid Spell Jumps"
    # (item 32: no fall spell choices, the avoid alone)
    assert len(ask["items"]) == 1
    b = ask.buttons[1]
    b.GetScript(b, "OnClick")(b)
    jump_trip.settle()
    assert N.stops[1].avoidJumps == "spell" and ns.CharDB().stops[1].avoidJumps == "spell"
    r2 = N.route
    assert ns.Router.KIND_DROP not in _route_kinds(r2)
    G.Update()
    assert G.jumpSegN == 0
    # (a new trip jumps again)
    jump_trip()
    assert N.stops[1].avoidJumps is None


def test_the_coil_is_drawn_in_the_world_map_too(game, jump_trip):  # noqa: F811
    lua, ns = game
    G, st = ns.GPS, ns.settings.gps
    r = jump_trip()
    if ns.Router.KIND_DROP not in _route_kinds(r):
        pytest.skip("the whole addon's route here doesn't jump the test cliff")
    lua.execute(WM_SETUP)
    was = {k: st[k] for k in ("useWorldMap", "replaceMinimap", "shown", "minimized")}
    try:
        st.shown, st.minimized, st.useWorldMap = True, None, True
        G.ApplySettings()
        lua.globals().AzerothGPS_ToggleMap()
        assert G.WorldMapHosted()
        lua.execute("AGPS_T = AGPS_T + 0.5")
        G.Update()
        assert G.jumpSegN > 0
    finally:
        lua.execute("WorldMapFrame:Hide() ToggleWorldMap = nil")
        for k, v in was.items():
            st[k] = v
        G.WorldMapChanged()
        G.ApplySettings()


def test_a_jump_ban_and_pick_are_kept_over_a_reload(game, jump_trip):  # noqa: F811
    lua, ns = game
    N = ns.Nav
    jump_trip()
    N.AvoidJump(1, HIGH[0], HIGH[1] - 70)
    N.PickFallSpell("Levitate")
    cdb = ns.CharDB()
    assert cdb.jumpBans[1].x == HIGH[0] and cdb.fallPick == "Levitate"
    N.jumpBans, N.fallPick = lua.eval("{}"), None
    N.Restore()
    assert len(N.jumpBans) == 1 and N.fallPick == "Levitate" and N.JumpBanned(1, HIGH[0], HIGH[1] - 70)
    # (bad saved data is left out)
    cdb.jumpBans = lua.eval("{ { cont = 1, x = 'a', y = 2 }, 5 }")
    N.Restore()
    assert len(N.jumpBans) == 0


def test_an_avoided_city_grid_drop_is_walked_round(game):  # noqa: F811
    """Orgrimmar's ledge by the bank (test_navfeatures): the city grid's drop link; avoided, the grid walks round it
    (its walks kept by WorldGrid.CostKey, which changes with the bans)."""
    from test_navfeatures import ORG_DROP_TOP, _route

    lua, ns = game
    N = ns.Nav
    a, b = (1, 1643.0, -4295.0, 27.0), (1, 1622.0, -4312.0, 20.0)
    # (a city's ledge is hopped by an Expert jumper only, navfeatures' rule since 2026-11-23)
    ns.settings.gps.expertJumper = True
    try:
        r = _route(lua, ns, a, b)
        assert r.cityGrid == "Orgrimmar" and ns.Router.KIND_DROP in kinds(r)
        key = ns.WorldGrid.CostKey()
        N.AvoidJump(1, ORG_DROP_TOP[0], ORG_DROP_TOP[1])
        assert ns.WorldGrid.CostKey() != key
        r2 = _route(lua, ns, a, b)
        assert ns.Router.KIND_DROP not in kinds(r2) and r2.length > r.length, (r2.length, r.length)
    finally:
        ns.settings.gps.expertJumper = None
        N.ResetJumps()
        ns.Router.Reset()
