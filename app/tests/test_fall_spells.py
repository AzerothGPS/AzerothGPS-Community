"""Class spells for big drops (1.4.0, Kooki3z 2026-11-22: "if a class has like levitate or slow fall and they have the
necessary reagents on them and they could survive a fall, then use that by default. Add an option to turn it off called
'Use class spells'"; FallSpells.lua). With Slow Fall or Levitate and a Light Feather, or the Skyborne's Gliding on Air
off its cooldown, the routes' safe drop is the drop the spell makes safe: a cliff too high for the player's own (39 yd
out of combat with the health hidden) is jumped down, its step says to cast the spell first, and the use button casts
it only when the buff still lasts through the drop. No spell, the option off, a warrior, no feathers, the racial on its
cooldown: the long way round. A spell lost mid-route works the route out again. (Its full-health sibling option was removed, item 28: Safe drop is
the one limit without a spell.)"""

import math

import pytest

pytest.importorskip("lupa")

# (a cliff wall on the Barrens' open ground along y = -2000, drawn toward +x: its left, +y, 50 yd over its right; the
# player's own safe drop out of combat is 39 yd: test_cliff_heights' 30 yd wall is walked down without a spell)
WALL = ("{ { op = 'wall', drawn = true, continent = 1, time = 1, kind = 'cliff', "
        "pts = { -1580,-2000, -1500,-2000, -1420,-2000 }, cl = { 80, 80, 80 }, cr = { 30, 30, 30 } } }")
HIGH, LOW = (-1500.0, -1925.0), (-1500.0, -2075.0)

MAGE = "IsPlayerSpell = function(id) return id == 130 end"
PRIEST = "IsPlayerSpell = function(id) return id == 1706 end"
SKYBORNE = "IsPlayerSpell = function(id) return id == 1271049 end"
WARRIOR = "IsPlayerSpell = function() return false end"
FEATHERS = "GetItemCount = function(id) return id == 17056 and 5 or 0 end"
NO_FEATHERS = "GetItemCount = function() return 0 end"


@pytest.fixture
def cliff():
    from azerothgps.gameharness import start

    lua, ns = start()
    ns.db.tracks = lua.eval(WALL)
    ns.Passability.RefreshWalls()

    def be(*code):
        for c in code:
            lua.execute(c)
        ns.FallSpells.Refresh()
        ns.Router.Reset()

    def route(a=HIGH, b=LOW):
        ns.Router.Reset()
        return ns.Router.Route(1, *a, *b, lua.table(offroad=True))

    yield lua, ns, be, route
    ns.db.tracks = lua.eval("{}")
    ns.Passability.RefreshWalls()


def kinds(r):
    return [r.kinds[i] for i in range(1, len(r.pts) // 2)]


def drop_step(lua, ns, r):
    """The route's drop maneuver (Turns) and its words now (Turns.NowText)."""
    path = lua.eval("""function(r)
      local p = { pts = r.pts, kinds = r.kinds, cum = { 0 }, zs = {}, fz = {} }
      for i = 1, #r.pts / 2 - 1 do
        p.cum[i + 1] = p.cum[i] + math.sqrt((r.pts[2 * i + 1] - r.pts[2 * i - 1]) ^ 2 + (r.pts[2 * i + 2] - r.pts[2 * i]) ^ 2)
      end
      p.total = p.cum[#p.cum]
      return p
    end""")(r)
    ms = ns.Turns.Maneuvers(path, "Stop", math.inf)
    for i in range(1, len(ms) + 1):
        if ms[i].kind == "drop":
            return ms[i], ns.Turns.NowText(ms[i], lua.eval("function(v) return string.format('%d yd', v) end"))
    return None, None


def test_a_mage_with_light_feathers_jumps_down_the_cliff_and_is_told_to_cast_slow_fall(cliff):
    lua, ns, be, route = cliff
    be(MAGE, NO_FEATHERS)
    assert ns.Nav.SafeDrop() < 45
    assert route().length > 200  # (no feathers: round the wall's end)
    be(FEATHERS)
    assert ns.Nav.SafeDrop() > 50 and ns.Nav.PlainSafeDrop() < 45
    r = route()
    assert r.length < 160, r.length
    assert ns.Router.KIND_DROP in kinds(r)
    m, text = drop_step(lua, ns, r)
    assert m is not None and abs(m.dropYd - 50) < 1, m and m.dropYd
    assert "Cast Slow Fall" in text and "jump down" in text, text
    assert route(LOW, HIGH).length > 200  # (never up it)


def test_no_spell_no_big_drop(cliff):
    """A warrior, a mage without feathers, the option off: round the wall's end."""
    lua, ns, be, route = cliff
    be(WARRIOR, FEATHERS)
    assert route().length > 200
    be(MAGE, NO_FEATHERS)
    assert route().length > 200
    be(MAGE, FEATHERS)
    ns.settings.gps.useClassSpells = False
    try:
        be()
        assert ns.FallSpells.Current() is None
        assert route().length > 200
    finally:
        ns.settings.gps.useClassSpells = True


def test_a_priest_levitates_down_but_not_in_shadowform(cliff):
    lua, ns, be, route = cliff
    be(PRIEST, FEATHERS)
    r = route()
    assert r.length < 160 and ns.Router.KIND_DROP in kinds(r)
    assert "Cast Levitate" in drop_step(lua, ns, r)[1]
    be("GetShapeshiftFormID = function() return 28 end")
    try:
        assert ns.FallSpells.Current() is None and route().length > 200
    finally:
        lua.execute("GetShapeshiftFormID = nil")


def test_a_skyborne_glides_down_without_feathers_but_not_on_its_cooldown(cliff):
    """The Skyborne's racial (Gliding on Air: no reagent, 10 s of slow fall, a 3 min cooldown): "Use Gliding on Air,
    then jump down"; on its cooldown, the long way."""
    lua, ns, be, route = cliff
    be(SKYBORNE, NO_FEATHERS)
    c = ns.FallSpells.Current()
    assert c and c.id == 1271049 and c.drop > 50
    r = route()
    assert r.length < 160 and ns.Router.KIND_DROP in kinds(r)
    m, text = drop_step(lua, ns, r)
    # (74 yd from the start: its 10 s don't last that walk and the fall, so at the ledge; there, use it and jump)
    assert text == "Wait to use Gliding on Air until the ledge (in 74 yd)", text
    m.dist = 3
    assert ns.Turns.NowText(m, lua.eval("function(v) return v end")) == "Use Gliding on Air, then jump down"
    assert ns.FallSpells.CastFor(m).spell == 1271049
    be("GetSpellCooldown = function(id) if id == 1271049 then return AGPS_T - 10, 180, 1 end return 0, 0, 1 end")
    try:
        assert ns.FallSpells.Current() is None
        assert route().length > 200
    finally:
        lua.execute("GetSpellCooldown = function() return 0, 0, 1 end")


def test_walk_on_air_glides_down_like_gliding_on_air_but_not_on_its_cooldown(cliff):
    """The racial Walk on Air (Kooki3z 2026-11-23, a level 25 character: instant, 10 s of gliding down, a 2 min
    cooldown; spell 1259416 in the client): a spell-jump source beside Slow Fall and Levitate."""
    lua, ns, be, route = cliff
    be("IsPlayerSpell = function(id) return id == 1259416 end", NO_FEATHERS)
    c = ns.FallSpells.Current()
    assert c and c.id == 1259416 and c.drop > 50
    r = route()
    assert r.length < 160 and ns.Router.KIND_DROP in kinds(r)
    m, _text = drop_step(lua, ns, r)
    m.dist = 3
    assert ns.Turns.NowText(m, lua.eval("function(v) return v end")) == "Use Walk on Air, then jump down"
    assert ns.FallSpells.CastFor(m).spell == 1259416
    be("GetSpellCooldown = function(id) if id == 1259416 then return AGPS_T - 10, 120, 1 end return 0, 0, 1 end")
    try:
        assert ns.FallSpells.Current() is None
        assert route().length > 200
    finally:
        lua.execute("GetSpellCooldown = function() return 0, 0, 1 end")


def test_the_last_feather_spent_works_the_route_out_again(cliff):
    """The reagent gone mid-route (or the spell unusable): what's ready changed, so the route is worked out again
    (Nav.OptionsChanged), without the big drop. The buff up on the cast that spent it still counts."""
    lua, ns, be, route = cliff
    be(MAGE, FEATHERS)
    FS = ns.FallSpells
    assert FS.Current() is not None
    calls = lua.eval("{ n = 0 }")
    was = ns.Nav.OptionsChanged
    ns.Nav.OptionsChanged = lua.eval("function(t, was) return function() t.n = t.n + 1 was() end end")(calls, was)
    try:
        before = FS.changes or 0
        # (cast: the feather spent, the buff up for 30 s)
        lua.execute(NO_FEATHERS)
        lua.execute("C_UnitAuras = { GetPlayerAuraBySpellID = function(id) if id == 130 then "
                    "return { expirationTime = AGPS_T + 30 } end end }")
        FS.Refresh()
        assert FS.Current() is not None and calls.n == 0  # (still ready: the buff is up)
        assert route().length < 160
        # (the buff ran out, no feathers left)
        lua.execute("C_UnitAuras = nil")
        FS.Refresh()
        assert FS.Current() is None and calls.n == 1 and FS.changes == before + 1
        assert route().length > 200
    finally:
        ns.Nav.OptionsChanged = was
        lua.execute("C_UnitAuras = nil")


def test_the_cast_button_only_when_the_buff_lasts_through_the_drop(cliff):
    """Far from the ledge: "Cast Slow Fall at the ledge (in N yd)", no button; near enough that casting now lasts
    through the fall: the button with Slow Fall; the buff up: a plain jump, no button; it ran out: the button again;
    in combat the secure button isn't set."""
    lua, ns, be, route = cliff
    be(MAGE, FEATHERS)
    FS = ns.FallSpells
    fmt = lua.eval("function(v) return string.format('%d yd', v) end")
    far = lua.table(kind="drop", dist=400, dropYd=50)
    near = lua.table(kind="drop", dist=10, dropYd=50)
    assert FS.CastFor(far).early  # (shown early, dimmed: Kooki3z 2026-11-23)
    assert ns.Turns.NowText(far, fmt) == "Wait to cast Slow Fall until the ledge (in 400 yd)"
    t = FS.CastFor(near)
    assert t is not None and t.spell == 130 and t[8] == "Slow Fall" and t.fall
    assert ns.Turns.NowText(near, fmt) == "Cast Slow Fall, then jump down"
    # (the buff up for 20 s more)
    lua.execute("C_UnitAuras = { GetPlayerAuraBySpellID = function(id) if id == 130 then "
                "return { expirationTime = AGPS_T + 20 } end end }")
    try:
        FS.Refresh()
        assert FS.CastFor(near) is None
        assert ns.Turns.NowText(near, fmt) == "Continue straight, then jump down in 10 yd"  # (no spell said)
        lua.execute("C_UnitAuras = nil")
        FS.Refresh()
        assert FS.CastFor(near) is not None
    finally:
        lua.execute("C_UnitAuras = nil")
    # (a small drop, within the player's own: no spell said)
    small = lua.table(kind="drop", dist=5, dropYd=20, text="Jump down here")
    assert FS.CastFor(small) is None and ns.Turns.NowText(small, fmt) == "Jump down here"
    # (in combat: the secure button isn't touched)
    G = ns.GPS
    b = lua.eval("{ panel = {} }")
    lua.execute("InCombatLockdown = function() return true end")
    try:
        G.SetUseButton(b, FS.CastFor(near), lua.eval("function() end"))
        assert b.key is None
    finally:
        lua.execute("InCombatLockdown = function() return false end")


def test_the_full_health_option_is_gone_and_a_saved_one_cleared():
    """Item 28 (Kooki3z 2026-11-24: redundant with the Safe drop slider): no option, the saved setting cleared, no drop
    past Safe drop without a spell."""
    from azerothgps.gameharness import start

    lua, ns = start(saved="AzerothGPSDB = { settings = { gps = { bigDropsFullHealth = true } } }")
    assert ns.db.settings.gps.bigDropsFullHealth is None and ns.Nav.FullHealthDrop is None
    lua.execute(WARRIOR)
    ns.FallSpells.Refresh()
    assert ns.Nav.FallSpellDrop() is None and ns.Nav.SafeDrop() == ns.Nav.PlainSafeDrop()


# Kooki3z's case, 2026-11-22 (his screenshot): from Camp Taurajo's flight master in the Barrens to Brackenwall Village
# in Dustwallow Marsh, the route ~3 km south round the ridges between; his red line: up the ridge from the Barrens side
# ("this was scalable from the barrens side") and down its far side. Along that line (from (-2480, -1890) to
# (-3040, -2800)) the ground climbs from ~92 to ~211 with two cells the terrain grid closes as too steep on the way up,
# then falls ~150 yd to the marsh over ~90 yd of the grid's closed steep cells: a slope slid down, longer than
# Passability.STEEP_RUN_MAX_YD. The spell lifts the drop's limit, but not those: still round, for now.
TAURAJO_FM, BRACKENWALL = (-2380.7, -1882.7), (-3083.3, -2850.0)


@pytest.mark.xfail(strict=True, reason="the ridge's climb and its far side's long steep slope stay closed (not the drop)")
def test_the_barrens_ridge_is_crossed_with_slow_fall():
    from azerothgps.gameharness import start

    lua, ns = start()
    lua.execute(MAGE)
    lua.execute(FEATHERS)
    ns.FallSpells.Refresh()
    ns.Router.Reset()
    r = ns.Router.Route(1, *TAURAJO_FM, *BRACKENWALL, lua.table(offroad=False))
    assert r.length < 2000, r.length  # (round the ridges: ~3040 yd; straight over: ~1200)


def test_the_fall_spell_drop_is_one_number_for_both_grids(cliff):
    """Nav.FallSpellDrop (the city grid's CityGrid.MaxDrop reads it): the spell's safe drop, nil without one; Nav.SafeDrop (the world grid's and the Router's x.maxDrop / maxDrop) is it when it's bigger."""
    lua, ns, be, route = cliff
    N = ns.Nav
    be(WARRIOR, NO_FEATHERS)
    assert N.FallSpellDrop() is None and N.SafeDrop() == N.PlainSafeDrop()
    be(MAGE, FEATHERS)
    assert N.FallSpellDrop() == ns.FallSpells.MaxDrop() > N.PlainSafeDrop()
    assert N.SafeDrop() == N.FallSpellDrop()


# (Kooki3z 2026-11-23: Options > Routing's Safe drop, `safeDropYd`: the plain drop limit out of combat, 39 by default;
# the same wall 30 yd high, walked down at 39, round its end at 20)
WALL_30 = WALL.replace("cl = { 80, 80, 80 }", "cl = { 60, 60, 60 }")


def test_the_safe_drop_option_sets_the_plain_drop_limit(cliff):
    lua, ns, be, route = cliff
    N = ns.Nav
    ns.db.tracks = lua.eval(WALL_30)
    ns.Passability.RefreshWalls()
    be(WARRIOR, NO_FEATHERS)
    assert ns.DEFAULTS.gps.safeDropYd == 39 and N.PlainSafeDrop() == 39 and N.SafeDrop() == 39
    r = route()
    assert r.length < 160, r.length  # (straight down it)
    ns.settings.gps.safeDropYd = 20
    try:
        N.OptionsChanged()
        assert N.PlainSafeDrop() == 20 and N.SafeDrop() == 20
        assert route().length > 200  # (30 yd is past 20: round the wall's end)
        lua.execute("UnitAffectingCombat = function() return true end")
        try:
            assert N.PlainSafeDrop() == 20  # (in combat the same, Kooki3z 2026-11-23)
        finally:
            lua.execute("UnitAffectingCombat = function() return false end")
    finally:
        ns.settings.gps.safeDropYd = 39
        N.OptionsChanged()
    assert route().length < 160


def test_only_a_drop_of_jump_callout_yd_or_more_is_a_jump_step(cliff):
    """Kooki3z 2026-11-23: "saying jump here really should be like 25 yd or more": a drop under Router.JUMP_CALLOUT_YD
    has no "Jump down here" step (and no coil, Router.JumpCalledOut), still routed; 25 yd or more, one that needs a fall
    spell, or one whose fall isn't known, has."""
    lua, ns, be, route = cliff
    R = ns.Router
    assert R.JUMP_CALLOUT_YD == 25
    be(WARRIOR, NO_FEATHERS)
    # (a path along x: walk, a drop at (-1500, -1950), walk)
    pts = lua.eval("{ -1500,-1900, -1500,-1950, -1500,-1955, -1500,-2050 }")
    kinds = lua.eval("{ 1, R_DROP, 1 }".replace("R_DROP", str(R.KIND_DROP)))
    r = lua.table(pts=pts, kinds=kinds, length=150)

    R.NoteDrop(-1500.0, -1950.0, 20)
    assert drop_step(lua, ns, r)[0] is None and R.JumpCalledOut(pts, kinds, 2) is False
    R.NoteDrop(-1500.0, -1950.0, 30)
    assert drop_step(lua, ns, r)[0] is not None and R.JumpCalledOut(pts, kinds, 2) is True
    assert R.JumpCalledOut(pts, kinds, 3) is True  # (not a drop piece)
    R.NoteDrop(-1500.0, -1950.0, 20)
    ns.settings.gps.safeDropYd = 14  # (20 yd past the safe drop: a fall spell's, called out)
    try:
        assert R.JumpCalledOut(pts, kinds, 2) is True
    finally:
        ns.settings.gps.safeDropYd = 39
