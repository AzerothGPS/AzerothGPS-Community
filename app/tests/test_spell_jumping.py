"""Spell jumping (1.4.0, Kooki3z 2026-11-23: "with spell jumping really any ledge jump is possible no matter the distance
down. maybe this is an extra nested setting called expert jumper where the intention is any jump down is possible and
the player is expected to cast at the last moment to survive ... the thing to determine is how many jumps are needed for
the trip and if a cooldown on the spell prevents the rest of the jumps from being survivable thus making jumping not
faster").

With the whole addon: cliff walls drawn on the Barrens' open ground (test_fall_spells' spot), a trip down them. The
trip planner (Nav.CheckSpellJumps, FallSpells.Budget) takes each jump only when a source can take it by the time the
player gets there: a cooldown blocking the second jump walks round that one; the reagents running out stops jumping;
waiting for a cooldown is kept only when it beats the way round. Option "Expert jumper" (under "Use class spells", off):
any drop, cast just before landing ("Cast ... now!", timed from the fall's start).
"""

import pytest

from test_map_redraw import game  # noqa: F401

pytest.importorskip("lupa")


def _wall(y, x0, x1, hi, lo, t):
    return (f"{{ op = 'wall', drawn = true, continent = 1, time = {t}, kind = 'cliff', "
            f"pts = {{ {x0},{y}, {(x0 + x1) / 2},{y}, {x1},{y} }}, cl = {{ {hi}, {hi}, {hi} }}, cr = {{ {lo}, {lo}, {lo} }} }}")


# (two cliffs in a row down the slope, 50 yd each, 100 yd apart; the way round each by its east end)
TWO = "{ " + _wall(-1950, -1580, -1420, 130, 80, 1) + ", " + _wall(-2050, -1580, -1420, 80, 30, 2) + " }"
TOP, FOOT = (-1500.0, -1900.0), (-1500.0, -2100.0)
# (the first of them alone)
ONE = "{ " + _wall(-1950, -1580, -1420, 130, 80, 1) + " }"
# (one cliff, 50 yd, a long way round)
LONG = "{ " + _wall(-1950, -2700, -300, 130, 80, 1) + " }"
# (one cliff, 250 yd: past any fall spell's reach from the top)
DEEP = "{ " + _wall(-1950, -1580, -1420, 300, 50, 1) + " }"
# (that one, then a 60 yd one below it: within Slow Fall's reach)
DEEP_THEN_60 = "{ " + _wall(-1950, -1580, -1420, 300, 50, 1) + ", " + _wall(-2050, -1580, -1420, 50, -10, 2) + " }"

MAGE = "IsPlayerSpell = function(id) return id == 130 end"
SKYBORNE = "IsPlayerSpell = function(id) return id == 1271049 end"


def feathers(n):
    return f"GetItemCount = function(id) return id == 17056 and {n} or 0 end"


def cooldown(id_, left):
    return (f"GetSpellCooldown = function(id) if id == {id_} then return AGPS_T - 1, {left + 1}, 1 end "
            "return 0, 0, 1 end")


@pytest.fixture
def trip(game):  # noqa: F811
    """trip(walls, *setup): the trip from TOP to FOOT on the Barrens with those walls and game functions set."""
    lua, ns = game
    N, st = ns.Nav, ns.settings.gps
    cdb = ns.CharDB()
    saved = (cdb.faction, st.zoom, st.fastestOrder, st.expertJumper)
    lua.execute("AGPS_SJ = { IsPlayerSpell, GetItemCount, GetSpellCooldown }")

    def settle(n=16):
        for _ in range(n):
            lua.execute("AGPS_T = AGPS_T + 0.5")
            ns.GPS.Update()

    def run(walls, *setup, a=TOP, b=FOOT, cont=1, uimap=1413, faction="Horde"):
        st.zoom, st.fastestOrder = 300, False
        cdb.faction = faction
        N.Clear()
        ns.db.tracks = lua.eval(walls)
        ns.Passability.RefreshWalls()
        for c in setup:
            lua.execute(c)
        ns.FallSpells.Refresh()
        ns.Router.Reset()
        lua.execute(f"AGPS_MAP = {uimap} AGPS_POS = {{ {a[0]}, {a[1]}, {cont} }}")
        N.SetStops(lua.eval(f"{{ {{ x = {b[0]}, y = {b[1]}, cont = {cont}, name = 'stop' }} }}"), False, "red")
        N.Invalidate(True, True)
        ns.GPS.Follow()
        settle()
        return N.route

    run.settle = settle
    try:
        yield run
    finally:
        cdb.faction, st.zoom, st.fastestOrder, st.expertJumper = saved
        N.Clear()
        lua.execute("IsPlayerSpell, GetItemCount, GetSpellCooldown = AGPS_SJ[1], AGPS_SJ[2], AGPS_SJ[3] IsFalling = nil")
        ns.FallSpells.fall, ns.FallSpells.fallArm = None, None
        ns.FallSpells.Refresh()
        ns.db.tracks = lua.eval("{}")
        ns.Passability.RefreshWalls()
        lua.execute("AGPS_MAP = nil AGPS_POS = { 2254.0, 293.0, 0 } AGPS_T = AGPS_T + 1")
        ns.GPS.Follow()


def drops(ns, r):
    R = ns.Router
    n = 0
    for p in range(1, len(r.parts) + 1):
        part = r.parts[p]
        ks = [part.kinds[i] for i in range(1, len(part.pts) // 2)]
        n += sum(1 for i, k in enumerate(ks) if k == R.KIND_DROP and (i == 0 or ks[i - 1] != R.KIND_DROP))
    return n


def autos(ns):
    return [ns.Nav.jumpBans[i] for i in range(1, len(ns.Nav.jumpBans) + 1) if ns.Nav.jumpBans[i].auto]


def test_with_feathers_enough_both_jumps_are_taken_and_nothing_is_left_out(game, trip):  # noqa: F811
    lua, ns = game
    r = trip(TWO, MAGE, feathers(5))
    assert drops(ns, r) == 2, r.length
    assert autos(ns) == [] and not ns.Nav.spellJumpsOff
    # (the budget: two Slow Falls, two feathers)
    FS = ns.FallSpells
    jumps = ns.Nav.SpellJumps(r)
    assert len(jumps) == 2 and jumps[1].t < jumps[2].t
    assert FS.Budget(jumps, ns.Nav.PlainSafeDrop())[0] is None


def test_a_cooldown_blocking_the_second_jump_walks_round_that_one(game, trip):  # noqa: F811
    """Gliding on Air (3 min cooldown): the first cliff glided down, the second walked round (waiting 2.5 min there
    is slower than the way round its end)."""
    lua, ns = game
    r = trip(TWO, SKYBORNE, feathers(0))
    assert drops(ns, r) == 1, r.length
    plan = ns.Nav.jumpPlan
    assert len(autos(ns)) == 1 and list(plan.decided.values()) == ["walk"]
    assert not ns.CharDB().jumpBans  # (the planner's own: not saved)


def test_the_last_feather_spent_stops_the_jumping(game, trip):  # noqa: F811
    lua, ns = game
    r = trip(TWO, MAGE, feathers(1))
    assert drops(ns, r) == 1, r.length
    assert len(autos(ns)) == 1


def test_jumping_that_is_not_faster_is_not_used(game, trip):  # noqa: F811
    """Gliding on Air 40 s from ready: waiting at the cliff is slower than its short way round: walked."""
    lua, ns = game
    r = trip(ONE, SKYBORNE, feathers(0), cooldown(1271049, 40))
    assert drops(ns, r) == 0, r.length
    assert list(ns.Nav.jumpPlan.decided.values()) == ["walk"]


def test_a_short_wait_beats_a_long_way_round(game, trip):  # noqa: F811
    """Gliding on Air 15 s from ready, the cliff 2.4 km long: the route waits at the top ("Wait 0:08 for Gliding on
    Air, then jump down"), and with the wait counted it's still faster than without any spell jump."""
    lua, ns = game
    r = trip(LONG, SKYBORNE, feathers(0), cooldown(1271049, 15))
    assert drops(ns, r) == 1, r.length
    plan = ns.Nav.jumpPlan
    # (weighed against the way with the jump left out: "wait"; no second search without spell jumps for the same question)
    assert list(plan.decided.values()) == ["wait"] and not ns.Nav.spellJumpsOff
    m = lua.table(kind="drop", dist=3, dropYd=50)
    text = str(ns.Turns.NowText(m, lua.eval("function(v) return v end")))
    assert text.startswith("Wait ") and "Gliding on Air" in text, text


def test_expert_off_keeps_the_reach_and_on_takes_any_drop_cast_just_before_landing(game, trip):  # noqa: F811
    lua, ns = game
    FS = ns.FallSpells
    st = ns.settings.gps
    assert st.expertJumper is False  # (off by default)
    r = trip(DEEP, SKYBORNE, feathers(0))
    assert drops(ns, r) == 0  # (250 yd: past Gliding on Air's 56)
    assert FS.RowDrop(FS.SPELLS[3]) == pytest.approx(56)
    st.expertJumper = True
    r = trip(DEEP, SKYBORNE, feathers(0))
    assert FS.Expert() and FS.RowDrop(FS.SPELLS[3]) == FS.EXPERT_DROP
    assert drops(ns, r) == 1, r.length
    fmt = lua.eval("function(v) return v end")
    m = lua.table(kind="drop", dist=5, dropYd=250)
    assert str(ns.Turns.NowText(m, fmt)) == "Jump, then use Gliding on Air just before you land"
    assert FS.CastFor(m).early  # (shown dimmed at the ledge: cast in the air, from the cue)
    # the fall: the cue when 85% of its reach is left (250 - 47.6 yd of free fall: about 4.9 s), then the button
    lua.execute("IsFalling = function() return true end")
    FS.WatchFall()
    f = FS.fall
    assert f is not None and 4 < f.cueAt - f.start < 5 and f.landAt > f.cueAt
    assert FS.FallCue() is None and FS.CastNow().early  # (falling, before the cue: dimmed)
    lua.execute("AGPS_T = AGPS_T + 5.1")
    assert str(FS.FallCue()) == "Use Gliding on Air now!"
    assert str(ns.Turns.NowText(lua.table(kind="turn", dist=50, text="Turn left"), fmt)) == "Use Gliding on Air now!"
    assert FS.CastNow().spell == 1271049 and not FS.CastNow().early
    lua.execute("IsFalling = function() return false end")
    FS.WatchFall()
    assert FS.fall is None and FS.FallCue() is None


def test_the_fall_takes_the_game_s_time():
    from azerothgps.gameharness import start

    lua, ns = start()
    FS = ns.FallSpells
    assert FS.FallTime(0) == 0
    assert FS.FallTime(19.2911 / 2) == pytest.approx(1.0)  # (half g: a second)
    tt = 60.148 / 19.2911
    dt = 0.5 * 19.2911 * tt * tt
    assert FS.FallTime(dt + 60.148) == pytest.approx(tt + 1)  # (at terminal speed a second more)


def test_the_cast_button_shows_at_the_ledge(game, trip):  # noqa: F811
    """Kooki3z 2026-11-23 (Tanaris's rim into Un'Goro, a gnome mage with Light Feathers): the jump's coil and tooltip
    showed, the Slow Fall button didn't. At the ledge's top, a drop within Slow Fall's reach: the step says to cast it
    and the use button (as the hearthstone's) casts it."""
    lua, ns = game
    G, FS = ns.GPS, ns.FallSpells
    r = trip(ONE, MAGE, feathers(5), a=(-1500.0, -1945.0))
    assert drops(ns, r) == 1
    fmt = lua.eval("function(v) return string.format('%d yd', v) end")
    _, ms = ns.Turns.Ahead(r)
    assert ms[1].kind == "drop" and abs(ms[1].dropYd - 50) < 1
    assert str(ns.Turns.NowText(ms[1], fmt)) == "Cast Slow Fall, then jump down"
    t = FS.CastNow()
    assert t is not None and t.spell == 130 and t.fall
    st = ns.settings.gps
    was = st.stepsCollapsed
    st.stepsCollapsed = False
    try:
        lua.execute("AGPS_T = AGPS_T + 0.5")
        G.Update()
        assert G.useBtn._shown and G.useBtn.key == "spell:130"
        # the arrow window's: the same secure button kind as the hearthstone's (G.NewUseButton, on UIParent), beside the
        # arrow, and its own icon showing (a hearthstone's is clear over the picture in the arrow's place; a fall
        # spell's had no picture under it: clickable and clear in the game, Kooki3z 2026-11-23)
        btn = lua.globals().AzerothGPSArrowUseButton
        arrowWin = lua.globals().AzerothGPSArrow
        lua.execute("""AGPS_ANCHOR = nil
          AzerothGPSArrowUseButton.SetPoint = function(self, p, rel) AGPS_ANCHOR = rel end""")
        btn.key = None
        arrowWin._scripts.OnUpdate(arrowWin, 1)
        assert btn._shown and btn.key == "spell:130" and btn._attr["type"] == "spell" and btn._attr["spell"]
        assert lua.eval("AGPS_ANCHOR")._name == "AzerothGPSArrow" and btn._parent._name == "UIParent"
        assert btn.icon._alpha == 1 and not btn.clearIcon
        # (in the arrow's place at the arrow's size, the arrow small and faint above it as in a quest area, A.SmallArrow;
        # Kooki3z 2026-11-23: "replace the arrow with the button and show the arrow tiny above it")
        # (sized and placed as the hearthstone's and the teleports', one rule for every use button: Kooki3z 2026-11-23,
        # "should be rendered at scale and the same size as the hearthstone and portal buttons", "for all these spells")
        A = ns.Arrow
        arrow = A.arrowTex
        assert btn._w == A.USE_PX and btn._h == A.USE_PX and lua.eval("AGPS_ANCHOR")._name == "AzerothGPSArrow"
        assert arrow._alpha == A.SMALL_ARROW_ALPHA and arrow._w < A.USE_PX * 2
        assert arrow._pt[1] == "BOTTOM" and arrow._pt[3] == "CENTER" and arrow._pt[5] > A.USE_PX / 2
        # (under the step, the jump's fall, not the slope's few yards before it)
        texts = [str(w._text) for w in lua.eval("AGPS_WIDGETS").values() if w._text]
        assert any("50 yd down" in t for t in texts) and not any(t.endswith("3 yd down|r") for t in texts), texts
        # (an item's, a worn parachute cloak's: the same size and place)
        lua.execute("AGPS_IPS = IsPlayerSpell IsPlayerSpell = function() return false end "
                    "AGPS_IEI = IsEquippedItem IsEquippedItem = function(id) return id == 10518 end")
        try:
            FS.Refresh()
            btn.key = None
            lua.execute("AGPS_T = AGPS_T + 1")
            arrowWin._scripts.OnUpdate(arrowWin, 1)
            assert btn._shown and btn.key == "item:10518" and btn._w == A.USE_PX
            assert lua.eval("AGPS_ANCHOR")._name == "AzerothGPSArrow" and btn.icon._alpha == 1
        finally:
            lua.execute("IsPlayerSpell, IsEquippedItem = AGPS_IPS, AGPS_IEI")
            FS.Refresh()
            btn.key = None
            lua.execute("AGPS_T = AGPS_T + 1")
            arrowWin._scripts.OnUpdate(arrowWin, 1)
        # (the debug line for a report from the game)
        out = FS.DebugButtons()
        lines = [str(out[i]) for i in range(1, len(out) + 1)]
        assert any(l.startswith("arrow window button: key spell:130 shown true") for l in lines), lines
        # (the step passed, no cast: the arrow back to its own size, full)
        lua.execute("AGPS_REAL_CN = AGPS_NS.FallSpells.CastNow AGPS_NS.FallSpells.CastNow = function() return nil end")
        try:
            lua.execute("AGPS_T = AGPS_T + 1")
            arrowWin._scripts.OnUpdate(arrowWin, 1)
            assert arrow._w == A.arrowTex._w and arrow._w > A.USE_PX and arrow._alpha == 1 and not btn._shown
        finally:
            lua.execute("AGPS_NS.FallSpells.CastNow = AGPS_REAL_CN")
    finally:
        st.stepsCollapsed = was


def test_a_drop_noted_a_few_yards_off_the_route_s_point_is_still_its_fall(game):  # noqa: F811
    """The fall is noted where the route's drop was made; the route's own point there can be a few yards off once the
    walk is smoothed or rejoined. The steps find it as the map's tooltip does (within Turns.DROP_NOTE_YD), so the spell is
    said and its button shown."""
    lua, ns = game
    R, T = ns.Router, ns.Turns
    ns.Router.NoteDrop(5003.0, 5002.0, 120)  # (noted 3.6 yd off the drop's top at (5000, 5000))
    part = lua.eval("{ cont = 1, stop = 1, pts = { 4900, 5000, 5000, 5000, 5010, 5000, 5100, 5000 }, "
                    f"kinds = {{ 1, {R.KIND_DROP}, 1 }} }}")
    path = T.Path(lua.eval("function(p) return { parts = { p } } end")(part))
    ms = T.Maneuvers(path, "the stop")
    m = [ms[i] for i in range(1, len(ms) + 1) if ms[i].kind == "drop"][0]
    assert m.dropYd == 120


def test_the_jump_s_tooltip_says_what_to_do(game, trip):  # noqa: F811
    lua, ns = game
    G, st = ns.GPS, ns.settings.gps
    trip(ONE, MAGE, feathers(5))
    tip = G.JumpTip(lua.table(kind="drop", dz=50))
    lines = [str(tip.lines[i]) for i in range(1, len(tip.lines) + 1)]
    assert str(tip.title) == "Spell jump" and "Cast Slow Fall at the edge, then jump" in lines
    assert not any("up to" in l for l in lines)
    st.expertJumper = True
    trip(DEEP, SKYBORNE, feathers(0))
    tip = G.JumpTip(lua.table(kind="drop", dz=250))
    lines = [str(tip.lines[i]) for i in range(1, len(tip.lines) + 1)]
    assert "Jump, then use Gliding on Air just before you land" in lines


def test_rerouting_the_same_trip_without_casting_keeps_the_jump(game, trip):  # noqa: F811
    lua, ns = game
    N = ns.Nav
    r = trip(TWO, MAGE, feathers(5))
    assert drops(ns, r) == 2
    for _ in range(3):
        N.Invalidate(True, True)
        trip.settle()
        assert drops(ns, N.route) == 2 and autos(ns) == []
    # (the same stop set again: the same trip)
    N.SetStops(lua.eval(f"{{ {{ x = {FOOT[0]}, y = {FOOT[1]}, cont = 1, name = 'stop' }} }}"), False, "red")
    trip.settle()
    assert drops(ns, N.route) == 2 and autos(ns) == []


# Kooki3z's trip (2026-11-23, his screenshots): Tanaris's west rim near Zul'Farrak's south to the river north of Fire
# Plume Ridge in Un'Goro. The world grid's drops are baked up to 39 yd: its walk goes 3.4k yd round by the southern way
# down; the Router's own goes off the rim (through the cliff face the terrain grid closes) in 790 yd.
UNGORO_RIM, UNGORO_RIVER = (-6772.0, -2661.0), (-6818.0, -1923.0)


@pytest.fixture
def world_grid(game):  # noqa: F811
    lua, ns = game
    ns.settings.gps.worldGrid = True
    ns.WorldGrid.Set(True)
    yield
    ns.settings.gps.worldGrid = False
    ns.WorldGrid.Set(False)


def test_slow_fall_goes_off_un_goro_s_rim_expert_jumper_or_not(game, trip, world_grid):  # noqa: F811
    """Kooki3z 2026-11-23: "Expert jumper is only needed if the available spell wouldn't cover the fall distance and
    they need to cast on the way down." The rim's 151 yd is within Slow Fall's reach cast at the edge (196 yd)."""
    lua, ns = game
    st = ns.settings.gps
    r = trip("{}", MAGE, feathers(5), a=UNGORO_RIM, b=UNGORO_RIVER)
    assert r.totalYards < 1000 and drops(ns, r) >= 1, r.totalYards  # (not an expert: Slow Fall cast at the edge)
    st.expertJumper = True
    r = trip("{}", MAGE, feathers(5), a=UNGORO_RIM, b=UNGORO_RIVER)
    assert r.totalYards < 1000 and drops(ns, r) >= 1, r.totalYards
    # (and again, the same trip worked out once more: still off the rim)
    ns.Nav.Invalidate(True, True)
    trip.settle()
    assert ns.Nav.route.totalYards < 1000


# A mage's trip (Kooki3z 2026-11-23, a level 60 mage, Slow Fall and feathers, Expert jumper on, Safe drop 60; his
# screenshot, the spots read off the map): from Tanaris's sands well back from the west rim to Un'Goro north-west of
# Fire Plume Ridge. The route walked round by the southern ramp, 3.6k yd: "i get spell jump if i get closer to the
# edge". The edge's fan (Router.SpellJumpVia) looked only 500 yd out from the stop and the rim is further; it and the
# straight line ran for an Expert jumper only, though Slow Fall covers the rim cast at the edge; and with Safe drop 60
# its edges had to drop more than 60 yd.
DADDIO_FAR, DADDIO_NEAR, DADDIO_STOP = (-6950.0, -2950.0), (-6850.0, -2700.0), (-6827.2, -1833.35)


@pytest.fixture
def safe_drop_60(game):  # noqa: F811
    lua, ns = game
    st = ns.settings.gps
    was = st.safeDropYd
    st.safeDropYd = 60
    yield
    st.safeDropYd = was


@pytest.mark.parametrize("a,expert", [(DADDIO_FAR, False), (DADDIO_FAR, True), (DADDIO_NEAR, True)],
                         ids=["far_back", "far_back_expert", "near_expert"])
def test_slow_fall_jumps_off_tanaris_s_rim_from_far_back(game, trip, world_grid, safe_drop_60, a, expert):  # noqa: F811
    lua, ns = game
    ns.settings.gps.expertJumper = expert
    r = trip("{}", MAGE, feathers(5), a=a, b=DADDIO_STOP)
    straight = ((a[0] - DADDIO_STOP[0]) ** 2 + (a[1] - DADDIO_STOP[1]) ** 2) ** 0.5
    assert drops(ns, r) >= 1 and r.totalYards < straight * 1.3 + 100, (r.totalYards, straight)


def test_far_back_routed_in_the_background_lands_on_the_jump(game, trip, world_grid, safe_drop_60):  # noqa: F811
    """As in the game (Router.WARM, walks in the background), the Router reset mid-search (#977's re-ask): the trip
    lands, final, on the jump; no route shown as final walks round. (The walks to the edges were searched inside a
    pcall: in Lua 5.1 a pause there errors, every search of the trip was dropped and asked again, and never landed.)"""
    lua, ns = game
    R, N, G = ns.Router, ns.Nav, ns.GPS
    st = ns.settings.gps
    st.expertJumper = True
    trip("{}", MAGE, feathers(5), a=DADDIO_FAR, b=DADDIO_STOP)
    clock = lua.eval("function() return os.clock() * 1000 end")
    was = (R.WARM, R.SYNC_WALKS)
    try:
        R.Reset()
        R.WARM, R.SYNC_WALKS = True, False
        N.Clear()
        N.SetStops(lua.eval(f"{{ {{ x = {DADDIO_STOP[0]}, y = {DADDIO_STOP[1]}, cont = 1, name = 'stop' }} }}"),
                   False, "red")
        shown = []
        for k in range(3000):
            lua.execute("AGPS_T = AGPS_T + 0.1")
            G.Update()
            if R.HasWork():
                t0 = clock()
                R.Pump(t0 + 8, clock)
            if N.route:
                shown.append((round(N.route.totalYards), bool(N.route.pending)))
            if k == 20:
                R.Reset()
        final = [y for y, p in shown if not p]
        assert final and max(final) < 1500 and not shown[-1][1], sorted(set(shown))
        assert drops(ns, N.route) >= 1
    finally:
        R.WARM, R.SYNC_WALKS = was


def test_a_cliff_past_slow_fall_s_reach_is_not_gone_down_without_expert_jumper(game, trip):  # noqa: F811
    """The Router's own way down through cliff faces (own.blocked): a 250 yd cliff, then a 60 yd one. The 250 is past
    Slow Fall's 196 yd reach cast at the edge: not an Expert jumper, MarkBigDrops marks only the 60 and leaves the 250
    a walk down its face; that way isn't taken (walked round). An Expert jumper's: both marked, jumps, taken."""
    lua, ns = game
    R = ns.Router
    st = ns.settings.gps
    A, B = (TOP[0] + 10, TOP[1]), (FOOT[0] + 10, FOOT[1])  # (off the walls' middle points: crossing them, not touching)
    was = R.RouteOwn
    face = lua.eval("""function(R, cont, sx, sy, tx, ty, opts)
      local r = { pts = { sx, sy, tx, ty }, kinds = { R.KIND_OFFROAD }, length = math.sqrt((tx - sx) ^ 2 + (ty - sy) ^ 2),
        road = 0, blocked = true }
      return R.MarkBigDrops(cont, r, opts)
    end""")
    try:
        trip(DEEP_THEN_60, MAGE, feathers(5))
        R.RouteOwn = lua.eval("function(f, R) return function(...) return f(R, ...) end end")(face, R)
        got = lua.table(length=5000)
        assert ns.Nav.FallSpellDrop() == pytest.approx(196)
        face_r = R.RouteOwn(1, A[0], A[1], B[0], B[1], lua.table())
        assert [face_r.kinds[i] for i in range(1, len(face_r.pts) // 2)].count(R.KIND_DROP) == 1  # (the 60 only)
        assert R.UnmarkedFall(1, face_r, lua.table())
        assert R.SpellJumpOwnOnly(1, A[0], A[1], B[0], B[1], lua.table(), got) is None
        st.expertJumper = True
        R.RouteOwn = was
        trip(DEEP_THEN_60, MAGE, feathers(5))  # (worked out again: the cliffs' drop limit an Expert's)
        R.RouteOwn = lua.eval("function(f, R) return function(...) return f(R, ...) end end")(face, R)
        own = R.SpellJumpOwnOnly(1, A[0], A[1], B[0], B[1], lua.table(), got)
        assert own is not None and [own.kinds[i] for i in range(1, len(own.pts) // 2)].count(R.KIND_DROP) == 2
    finally:
        R.RouteOwn = was


def test_a_plain_drop_within_safe_drop_is_jumped_with_no_spell(game, trip):  # noqa: F811
    """A 50 yd cliff, no fall spell: within Safe drop 60 it's a plain drop, taken by the Router's own and weighed by
    spell jumping's straight line past the grids' baked drops (Router.JumpDrops); at Safe drop 39, walked round."""
    lua, ns = game
    R, st = ns.Router, ns.settings.gps
    was = st.safeDropYd
    try:
        st.safeDropYd = 60
        r = trip(LONG, feathers(0))
        assert ns.Nav.FallSpellDrop() is None and drops(ns, r) == 1 and r.totalYards < 300, r.totalYards
        s = R.SpellJumpStraight(1, TOP[0], TOP[1], FOOT[0], FOOT[1], lua.table(), lua.table(length=5000))
        assert s is not None and R.KIND_DROP in [s.kinds[i] for i in range(1, len(s.pts) // 2)]
        st.safeDropYd = 39
        r = trip(LONG, feathers(0))
        assert drops(ns, r) == 0 and r.totalYards > 1000, r.totalYards
        assert R.SpellJumpStraight(1, TOP[0], TOP[1], FOOT[0], FOOT[1], lua.table(), lua.table(length=5000)) is None
    finally:
        st.safeDropYd = was


def test_a_long_straight_before_a_hairpin_still_says_the_turn(game):  # noqa: F811
    """Kooki3z's way round (the grid's): "Straight, then arrive at destination in 3.4k yd" on a route doubling back
    1.7k yd on. Nothing within the horizon but the arrival: looked further for the next maneuver."""
    lua, ns = game
    T = ns.Turns
    part = lua.eval("{ cont = 1, stop = 1, pts = { 0, 0, 0, -1700, 100, -1700, 100, 0 }, kinds = { 1, 1, 1 } }")
    route = lua.eval("function(p) return { parts = { p } } end")(part)
    _, ms = T.Ahead(route, "the stop")
    kinds_ = [str(ms[i].kind) for i in range(1, len(ms) + 1)]
    assert "turn" in kinds_ and kinds_[-1] == "arrive", kinds_
    text = str(T.NowText(ms[1], lua.eval("function(v) return string.format('%d yd', v) end")))
    assert "arrive" not in text, text


def test_the_settled_route_never_swaps_the_spell_jump_for_the_grid_s_long_walk(game, trip, world_grid):  # noqa: F811
    """Kooki3z 2026-11-23 (video, the game's background routing): the faded route off the rim, then the 3.35k yd walk
    round settled for half a minute: the grid's answer landed while the Router's own way off the rim was still searched.
    Worked out as in the game (Router.WARM, walks in the background): every route shown goes off the rim, the last one
    final; near the first drop, the Slow Fall button."""
    lua, ns = game
    R, N, G, FS = ns.Router, ns.Nav, ns.GPS, ns.FallSpells
    st = ns.settings.gps
    st.expertJumper = True
    trip("{}", MAGE, feathers(5), a=UNGORO_RIM, b=UNGORO_RIVER)
    clock = lua.eval("function() return os.clock() * 1000 end")
    was = (R.WARM, R.SYNC_WALKS, st.stepsCollapsed)

    def run(n):
        shown = []
        for _ in range(n):
            lua.execute("AGPS_T = AGPS_T + 0.1")
            G.Update()
            if R.HasWork():
                t0 = clock()
                R.Pump(t0 + 8, clock)
            if N.route:
                shown.append((round(N.route.totalYards), bool(N.route.pending)))
        return shown

    try:
        R.Reset()
        R.WARM, R.SYNC_WALKS = True, False
        N.Clear()
        N.SetStops(lua.eval(f"{{ {{ x = {UNGORO_RIVER[0]}, y = {UNGORO_RIVER[1]}, cont = 1, name = 'stop' }} }}"),
                   False, "red")
        shown = run(1500)
        assert shown and max(y for y, _ in shown) < 1000, sorted(set(shown))
        assert shown[-1][1] is False and not R.HasWork()
        # (10 yd before the first drop's top: the step says to cast, and the button casts it)
        j = N.SpellJumps(N.route)[1]
        lua.execute(f"AGPS_POS = {{ {j.x}, {j.y} - 10, 1 }}")
        st.stepsCollapsed = False
        run(60)
        assert FS.CastNow().spell == 130 and G.useBtn.key == "spell:130"
    finally:
        R.WARM, R.SYNC_WALKS, st.stepsCollapsed = was


def test_the_spell_button_shows_early_and_the_step_says_to_wait_till_casting_lasts(game, trip):  # noqa: F811
    """Kooki3z 2026-11-23: "show the spell icon early, just tell the user to wait to cast it to survive the fall". From
    the trip's start the button is there, dimmed (`early`), the step "Wait to cast Slow Fall until the ledge (in N yd)";
    once casting would last through the fall: "Cast Slow Fall, then jump down", lit. For an expert's deep drop: shown
    dimmed at the ledge, "Jump, then ... just before you land", lit from the mid-fall cue."""
    lua, ns = game
    FS, T = ns.FallSpells, ns.Turns
    fmt = lua.eval("function(v) return string.format('%d yd', v) end")
    # (a 180 yd drop: Slow Fall's 30 s last through it from 25 yd before the ledge on)
    trip(ONE, MAGE, feathers(5))
    far = lua.table(kind="drop", dist=115, dropYd=180)
    t = FS.CastFor(far)
    assert t is not None and t.spell == 130 and t.early
    assert str(T.NowText(far, fmt)) == "Wait to cast Slow Fall until the ledge (in 115 yd)"
    near = lua.table(kind="drop", dist=5, dropYd=180)
    t = FS.CastFor(near)
    assert t is not None and t.spell == 130 and not t.early
    assert str(T.NowText(near, fmt)) == "Cast Slow Fall, then jump down"
    # (the button itself: dimmed while early, lit at the cast point; clickable both times)
    G = ns.GPS
    b = lua.eval("{ icon = { SetDesaturated = function(self, v) self.gray = v end, SetAlpha = function(self, a) self.a = a end }, "
                 "SetAttribute = function(self, k, v) self[k] = v end }")
    G.UseWait(b, FS.CastFor(far))
    assert b.icon.gray is True and b.icon.a < 1 and b.type == "spell"
    lua.execute("AGPS_T = AGPS_T + 0.2")
    G.UseWait(b, FS.CastFor(near))
    assert b.icon.gray is False and b.icon.a == 1 and b.type == "spell"
    # an expert's deep drop: shown at the ledge, dimmed; the cast in the air
    ns.settings.gps.expertJumper = True
    trip(DEEP, SKYBORNE, feathers(0))
    deep = lua.table(kind="drop", dist=5, dropYd=250)
    t = FS.CastFor(deep)
    assert t is not None and t.spell == 1271049 and t.early
    assert str(T.NowText(deep, fmt)) == "Jump, then use Gliding on Air just before you land"


def test_standing_still_for_minutes_the_spell_jump_route_stays(game, trip, world_grid):  # noqa: F811
    """Kooki3z 2026-11-23: "eventually got even worse not moving": standing on the rim, a later recalculation went back
    to the 3.35k yd walk round. Three minutes of game time standing still, routed as in the game (background walks, the
    reroutes' timers, the ride checks): every route shown goes off the rim."""
    lua, ns = game
    R, N, G = ns.Router, ns.Nav, ns.GPS
    st = ns.settings.gps
    st.expertJumper = True
    trip("{}", MAGE, feathers(5), a=UNGORO_RIM, b=UNGORO_RIVER)
    clock = lua.eval("function() return os.clock() * 1000 end")
    was = (R.WARM, R.SYNC_WALKS)
    try:
        R.Reset()
        R.WARM, R.SYNC_WALKS = True, False
        N.Clear()
        N.SetStops(lua.eval(f"{{ {{ x = {UNGORO_RIVER[0]}, y = {UNGORO_RIVER[1]}, cont = 1, name = 'stop' }} }}"),
                   False, "red")
        worst, seen = 0, 0
        for k in range(1800):
            lua.execute("AGPS_T = AGPS_T + 0.1")
            G.Update()
            if R.HasWork():
                t0 = clock()
                R.Pump(t0 + 8, clock)
            if N.route:
                seen += 1
                worst = max(worst, N.route.totalYards)
        assert seen > 1000 and worst < 1000, worst
    finally:
        R.WARM, R.SYNC_WALKS = was


# Kooki3z's cases of a poor jump point (2026-11-23, his screenshots; the spots read off the map's coordinates, so near
# his, not exact): from Tanaris's rim by the Noxious Lair to below Ironstone Plateau, the route jumped off south-west
# and walked the Marshlands round (~3.3k yd for a 1.6k yd straight line; his green: off the rim further north and
# straight down); from Freewind Post's mesa to the canyon road below its north-west edge (the route by the mesa's west
# bridge; his green: off the edge straight down).
NOXIOUS_RIM, BELOW_IRONSTONE = (-7663.8, -2641.3), (-6539.0, -1464.7)
FREEWIND_TOP, FREEWIND_ROAD = (-5404.0, -2404.5), (-5292.0, -2204.5)


@pytest.mark.parametrize("a,b", [(NOXIOUS_RIM, BELOW_IRONSTONE), (FREEWIND_TOP, FREEWIND_ROAD)],
                         ids=["un_goro_ironstone", "freewind_post"])
def test_an_expert_jumper_jumps_where_the_straight_line_goes_down(game, trip, world_grid, a, b):  # noqa: F811
    """With a fall spell and Expert jumper, the straight line to the stop where it only goes down (no cliff to climb,
    no wall: Router.SpellJumpStraight) is weighed against the way round, and the trip's planning weighs its cliff face
    as jumped (Nav's Weighed), not as blocked ground."""
    lua, ns = game
    ns.settings.gps.expertJumper = True
    r = trip("{}", MAGE, feathers(9), a=a, b=b)
    straight = ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5
    assert r.totalYards < straight * 1.3 + 60 and drops(ns, r) >= 1, (r.totalYards, straight)


# Kooki3z 2026-11-23 (his screenshot, the spots read off the map): the southern Barrens to below Dustwallow's ridge. The
# route went south by the Barrens road and back north through the marsh (about 3 times his way: east over the hills to
# the ridge's edge and a spell jump down). From further west the straight line climbs the hills, so the jump is taken by
# way of an edge near the stop (Router.SpellJumpVia: walked to it as any leg, then straight down).
SOUTH_BARRENS, BELOW_DUSTWALLOW_RIDGE = (-2262.2, -2152.1), (-2482.6, -2920.0)
BARRENS_HILLS = (-2262.2, -2000.0)


@pytest.mark.parametrize("a", [SOUTH_BARRENS, BARRENS_HILLS], ids=["his_start", "over_the_hills"])
def test_slow_fall_walks_to_the_ridge_s_edge_and_jumps(game, trip, world_grid, a):  # noqa: F811
    """With no fall spell, the way round; with Slow Fall, to the edge and down, Expert jumper or not (the ridge is
    within its reach cast at the edge)."""
    lua, ns = game
    b = BELOW_DUSTWALLOW_RIDGE
    straight = ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5
    r = trip("{}", feathers(0), a=a, b=b)
    plain = r.totalYards
    for expert in (False, True):
        ns.settings.gps.expertJumper = expert
        r = trip("{}", MAGE, feathers(9), a=a, b=b)
        assert drops(ns, r) >= 1 and r.totalYards < straight * 1.15 + 60 and r.totalYards < plain, (expert, r.totalYards, plain)


def test_the_edge_s_way_is_found_where_the_straight_line_climbs(game, trip, world_grid):  # noqa: F811
    lua, ns = game
    R, P = ns.Router, ns.Passability
    a, b = BARRENS_HILLS, BELOW_DUSTWALLOW_RIDGE
    ns.settings.gps.expertJumper = True
    trip("{}", MAGE, feathers(9), a=a, b=b)
    assert P.CliffAlong(1, a[0], a[1], b[0], b[1])  # (the hills climbed on the straight line)
    assert R.SpellJumpStraight(1, a[0], a[1], b[0], b[1], lua.table(), lua.table(length=5000)) is None
    v = R.SpellJumpVia(1, a[0], a[1], b[0], b[1], lua.table(), lua.table(length=5000))
    assert v is not None and v.spellJumpVia and R.KIND_DROP in [v.kinds[i] for i in range(1, len(v.pts) // 2)]


# Kooki3z 2026-11-23: "all cave routes should only be accessible through an entrance" (Darkmist Cavern; the Deadmines
# from Moonbrook, a coil down through the ground onto its portal).
MOONBROOK, DEADMINES_PORTAL = (-11015.0, 1560.0), (-11208.4, 1672.5)


def test_spell_jumping_never_drops_into_a_cave_from_over_it(game, trip):  # noqa: F811
    lua, ns = game
    R = ns.Router
    ns.settings.gps.expertJumper = True
    trip("{}", MAGE, feathers(9), a=MOONBROOK, b=DEADMINES_PORTAL, cont=0, uimap=1436)
    a, b = MOONBROOK, DEADMINES_PORTAL
    assert R.InCaveGrid(0, *b) and not R.InCaveGrid(0, *a)
    far = lua.table(length=50000)
    for fn in (R.SpellJumpStraight, R.SpellJumpVia, R.SpellJumpOwn):
        got = fn(0, a[0], a[1], b[0], b[1], lua.table(), far)
        assert got is None or not R.JumpsIntoCave(0, got), fn
    # (a drop from the ground onto a cave's floor is one; along the way in, not)
    into = lua.eval(f"{{ pts = {{ {a[0]}, {a[1]}, {b[0]}, {b[1]} }}, kinds = {{ {R.KIND_DROP} }} }}")
    assert R.JumpsIntoCave(0, into)
    r = ns.Nav.route
    assert not R.JumpsIntoCave(0, r.parts[1]), "the Router's own way jumps into the Deadmines"


# Thunder Bluff (Kooki3z 2026-11-23, his screenshots, an Alliance mage, "Through enemy territory: Thunder Bluff"; the
# spots read off the map): on the main mesa's east rim to the Mulgore ground east, his way a spell jump straight off the
# rim; on the rope bridge to Hunter Rise to the ground east, the route a straight walk with no jump.
TB_EAST_RIM, TB_EAST_GROUND = (-1211.8, -67.8), (-1232.0, -329.8)
TB_HUNTER_BRIDGE, TB_HUNTER_GROUND = (-1349.6, -131.5), (-1282.6, -404.5)


@pytest.mark.parametrize("faction", ["Horde", "Alliance"])
def test_thunder_bluff_s_rim_and_bridge_are_jumped_off_in_either_faction(game, trip, faction):  # noqa: F811
    lua, ns = game
    ns.settings.gps.expertJumper = True
    a, b = TB_EAST_RIM, TB_EAST_GROUND
    r = trip("{}", MAGE, feathers(9), a=a, b=b, uimap=1456, faction=faction)
    straight = ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5
    assert drops(ns, r) >= 1 and r.totalYards < straight * 1.15 + 30, r.totalYards
    # (on the bridge: off its side, the fall noted, "Cast Slow Fall" when it's next)
    a, b = TB_HUNTER_BRIDGE, TB_HUNTER_GROUND
    r = trip("{}", MAGE, feathers(9), a=a, b=b, uimap=1456, faction=faction)
    _, ms = ns.Turns.Ahead(r)
    m = [ms[i] for i in range(1, len(ms) + 1) if ms[i].kind == "drop"]
    assert m and m[0].dropYd > 60 and m[0].dist < 30, [(str(ms[i].kind), ms[i].dist) for i in range(1, len(ms) + 1)]
    fmt = lua.eval("function(v) return string.format('%d yd', v) end")
    m[0].dist = 3
    assert str(ns.Turns.NowText(m[0], fmt)) == "Cast Slow Fall, then jump down"


def test_walking_off_a_bridge_s_end_onto_land_at_its_height_is_no_drop(game, trip):  # noqa: F811
    lua, ns = game
    R = ns.Router
    trip("{}", MAGE, feathers(9), a=TB_HUNTER_BRIDGE, b=TB_HUNTER_GROUND, uimap=1456)
    a, b = TB_HUNTER_BRIDGE, TB_HUNTER_GROUND
    gz = ns.Passability.GroundZ(1, b[0], b[1])
    # (the same deck height, ending on land as high: not a drop)
    r = lua.eval(f"{{ pts = {{ {a[0]}, {a[1]}, {b[0]}, {b[1]} }}, kinds = {{ 1 }}, fz = {{ {gz + 1}, false }} }}")
    out = R.MarkDeckDrops(1, r, lua.table())
    assert R.KIND_DROP not in [out.kinds[i] for i in range(1, len(out.kinds) + 1)]


def test_a_reroute_mid_jump_keeps_the_spell_button_till_landed(game, trip):  # noqa: F811
    """Kooki3z 2026-11-23 by Bluefen, Walk on Air's button up, then a reroute on the way down made the step "Jump down
    here" and the button went: "can't take the button away mid jump like that." Once shown it stays, the same spell,
    while falling and till FS.HOLD_SETTLE after landing; walked HOLD_YD away without a fall, it goes."""
    lua, ns = game
    FS = ns.FallSpells
    trip(ONE, MAGE, feathers(5), a=(-1500.0, -1945.0))
    lua.execute("AGPS_POS[1], AGPS_POS[2] = -1500.0, -1945.0")
    t = FS.CastNow()
    assert t is not None and t.spell == 130
    lua.execute("AGPS_NEXT_DROP_WAS = AGPS_NS.FallSpells.NextDrop; AGPS_NS.FallSpells.NextDrop = function() return nil end;"
                "AGPS_FALLING_WAS = IsFalling")
    try:
        lua.execute("IsFalling = function() return true end; AGPS_T = AGPS_T + 0.5")
        t = FS.CastNow()  # (the reroute's step: no spell; mid-fall)
        assert t is not None and t.spell == 130
        lua.execute("IsFalling = function() return false end; AGPS_T = AGPS_T + 0.5")
        assert FS.CastNow() is not None  # (just landed: kept a moment)
        lua.execute("AGPS_T = AGPS_T + 2")
        assert FS.CastNow() is None  # (landed and settled)
        # (shown again, then walked away from the edge without jumping)
        lua.execute("AGPS_NS.FallSpells.NextDrop = AGPS_NEXT_DROP_WAS")
        assert FS.CastNow() is not None
        lua.execute("AGPS_NS.FallSpells.NextDrop = function() return nil end")
        assert FS.CastNow() is not None  # (still at the edge: kept)
        lua.execute("AGPS_POS[1] = AGPS_POS[1] + 30")
        assert FS.CastNow() is None
    finally:
        lua.execute("AGPS_NS.FallSpells.NextDrop = AGPS_NEXT_DROP_WAS; IsFalling = AGPS_FALLING_WAS")
        FS.held = None


WALK_ON_AIR = "IsPlayerSpell = function(id) return id == 1259416 end"


def test_casting_the_steps_spell_keeps_the_route_through_the_jump(game, trip):  # noqa: F811
    """Kooki3z 2026-11-23: "no reroute after casting the jump spell". A warrior's Walk on Air at the ledge: cast, its
    cooldown starts and the glide ends on landing, but the route stays through the fall; worked out again once landed
    (FallSpells.held, FS.Release). Cast, but no jump made within the glide: worked out again then."""
    lua, ns = game
    FS = ns.FallSpells
    trip(ONE, WALK_ON_AIR, feathers(0), a=(-1500.0, -1945.0))
    lua.execute("AGPS_POS[1], AGPS_POS[2] = -1500.0, -1945.0")
    lua.execute("""AGPS_OC = 0; AGPS_OC_WAS = AGPS_NS.Nav.OptionsChanged
      AGPS_NS.Nav.OptionsChanged = function(...) AGPS_OC = AGPS_OC + 1 return AGPS_OC_WAS(...) end
      AGPS_FALL_WAS, AGPS_CD_WAS, AGPS_AURAS_WAS = IsFalling, GetSpellCooldown, C_UnitAuras
      AGPS_BUFF = nil
      C_UnitAuras = { GetPlayerAuraBySpellID = function(id)
        if id == 1259416 and AGPS_BUFF and AGPS_T < AGPS_BUFF then return { expirationTime = AGPS_BUFF } end end }""")
    try:
        t = FS.CastNow()
        assert t is not None and t.spell == 1259416
        # (cast: the buff up for 10 s, the cooldown 2 min)
        lua.execute("AGPS_BUFF = AGPS_T + 10; AGPS_CD0 = AGPS_T; "
                    "GetSpellCooldown = function(id) if id == 1259416 then return AGPS_CD0, 120, 1 end return 0, 0, 1 end")
        for _ in range(3):  # (jumped: falling, the glide on)
            lua.execute("IsFalling = function() return true end; AGPS_T = AGPS_T + 1")
            FS.Refresh()
            assert FS.CastNow() is not None
        lua.execute("AGPS_BUFF = nil; IsFalling = function() return false end; AGPS_T = AGPS_T + 0.5")  # (landed)
        FS.Refresh()
        FS.CastNow()
        assert lua.eval("AGPS_OC") == 0  # (no reroute for the cooldown, nor the glide ended on landing)
        lua.execute("AGPS_T = AGPS_T + 2")
        assert FS.CastNow() is None and lua.eval("AGPS_OC") == 1  # (landed and settled: worked out again)
        # (cast again later, but no jump made within the glide: worked out again when it ends)
        lua.execute("GetSpellCooldown = function() return 0, 0, 1 end; AGPS_T = AGPS_T + 200")
        FS.Refresh()
        for _ in range(16):  # (the route worked out again, as the game's frames do)
            lua.execute("AGPS_T = AGPS_T + 0.5")
            ns.GPS.Update()
        lua.execute("AGPS_OC = 0")
        assert FS.CastNow() is not None
        lua.execute("AGPS_BUFF = AGPS_T + 10; AGPS_CD0 = AGPS_T; "
                    "GetSpellCooldown = function(id) if id == 1259416 then return AGPS_CD0, 120, 1 end return 0, 0, 1 end")
        lua.execute("AGPS_T = AGPS_T + 1")
        FS.Refresh()
        FS.CastNow()
        assert lua.eval("AGPS_OC") == 0
        lua.execute("AGPS_T = AGPS_T + 10")  # (the glide over, still on the ledge)
        FS.Refresh()
        assert FS.CastNow() is None and lua.eval("AGPS_OC") == 1
    finally:
        lua.execute("AGPS_NS.Nav.OptionsChanged = AGPS_OC_WAS; IsFalling = AGPS_FALL_WAS; GetSpellCooldown = AGPS_CD_WAS; "
                    "C_UnitAuras = AGPS_AURAS_WAS")
        FS.held = None
        FS.Refresh()
