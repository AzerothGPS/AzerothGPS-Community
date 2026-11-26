"""The tutorial's spell-jump demo (Tutorial.lua's T.JumpDemoStart; Kooki3z 2026-11-25): on the "Class spells for big
drops" step the player's route is set aside and an example trip off Bluefen's ridge is shown for a simulated mage with
Slow Fall ready; the cast button is an insecure look-alike that casts nothing and, clicked (or A on a controller),
glides the simulated player down to the landing and the stop. The step left, the tutorial exited, the player moving,
combat, the map hidden or a logout put everything back at once: the real position, the saved route exactly, the real
settings, and nothing of the demo in the saved variables."""

import pytest

from test_tutorial import _reset, _start, _state, _diff

pytest.importorskip("lupa.lua51")

MY_ROUTE = "{ { x = 2400.0, y = 250.0, cont = 0, name = 'My stop' }, { x = 2500.0, y = 300.0, cont = 0, name = 'Next' } }"


@pytest.fixture(scope="module")
def game():
    return _start()


@pytest.fixture
def tut(game):
    lua, ns = game
    _reset(lua, ns)
    yield lua, ns
    lua.execute("InCombatLockdown = function() return false end AGPS_NS.inCombat = false")
    if ns.Tutorial.jumpDemo:
        ns.Tutorial.JumpDemoStop("left")
    _reset(lua, ns)


def _settle(lua, ns, n=16):
    for _ in range(n):
        lua.execute("AGPS_T = AGPS_T + 0.5")
        ns.GPS.Update()
        _arrow(lua)


def _arrow(lua):
    """The arrow window's frame update (its directions and its use button), as the game runs it."""
    w = lua.globals().AzerothGPSArrow
    w._scripts.OnUpdate(w, 1)


def _at_demo(lua, ns, route=True):
    """The player's own route set and saved, then the tutorial at the demo's step with its trip worked out."""
    N, T = ns.Nav, ns.Tutorial
    if route:
        N.SetStops(lua.eval(MY_ROUTE), False, "red")
        ns.GPS.PendingStops(lua.eval("{ { x = 2300.0, y = 280.0, cont = 0, name = 'waiting' } }"))
    before = _state(lua)
    saved_stops = lua.eval("AGPS_DUMP(AGPS_NS.CharDB().stops)")
    assert T.Start(lua.eval("{ 'cities' }"))
    T.Jump("cities")
    while T.run.step.title != ns.L["Class spells for big drops"]:
        T.NextClicked()
    assert T.run.error is None, T.run.error
    assert T.JumpDemoOn()
    _settle(lua, ns)
    return before, saved_stops


def _twin(ns):
    return ns.GPS.DemoUseShown()


def test_the_demo_sets_the_trip_for_a_simulated_mage_and_saves_nothing(tut):
    lua, ns = tut
    N, FS, Geo = ns.Nav, ns.FallSpells, ns.Geo
    _before, saved_stops = _at_demo(lua, ns)
    o = Geo.override
    assert o and o.cont == 1 and abs(o.x + 2309.8) < 1 and abs(o.y + 3253.5) < 1
    assert len(N.stops) == 1 and N.stops[1].cont == 1 and abs(N.stops[1].x + 2558.3) < 1
    assert len(ns.GPS.PendingStops()) == 0
    # (the route has its spell jump, and the step is the real one: the cast button for Slow Fall)
    r = N.route
    assert r and any(r.parts[p].kinds[i] == ns.Router.KIND_DROP for p in range(1, len(r.parts) + 1)
                     for i in range(1, len(r.parts[p].kinds) + 1))
    t = FS.CastNow()
    assert t and t.spell == 130 and t.demo
    # (the saved route as it was: the demo trip never saved)
    assert lua.eval("AGPS_DUMP(AGPS_NS.CharDB().stops)") == saved_stops
    assert "My stop" in saved_stops and "-2558" not in saved_stops


def test_the_demo_button_is_an_insecure_look_alike_and_casts_nothing(tut):
    lua, ns = tut
    G = ns.GPS
    _at_demo(lua, ns)
    d = _twin(ns)
    assert d is not None, "no demo button shown"
    import re
    from test_tutorial import ROOT
    src = (ROOT / "addon" / "AzerothGPS" / "GPSFrame.lua").read_text(encoding="utf-8")
    body = src[src.index("function G.DemoUseButton(b)"):src.index("function G.DemoCastClick")]
    assert re.findall(r"CreateFrame\(([^)]*)\)", body) == ['"Button", nil, UIParent']  # (no secure template)
    assert "SetAttribute" not in body
    assert not lua.eval("function(d) return d:GetName() end")(d)
    assert d.insecure and d.real is not None
    # (the secure buttons hidden meanwhile, and set to nothing)
    for real in (G.useBtn, lua.globals().AzerothGPSArrowUseButton):
        if real is not None:
            assert not real.IsShown(real) and real.key is None
    # (a click: nothing cast, used or targeted)
    lua.execute("""AGPS_CASTS = 0
      AGPS_CAST_WAS, AGPS_USE_WAS = CastSpellByName, UseItemByName
      CastSpellByName = function() AGPS_CASTS = AGPS_CASTS + 1 end
      UseItemByName = function() AGPS_CASTS = AGPS_CASTS + 1 end""")
    try:
        d.GetScript(d, "OnClick")(d, "LeftButton")
        assert lua.eval("AGPS_CASTS") == 0
        assert lua.eval("function(d) return d:GetAttribute('type') end")(d) is None
    finally:
        lua.execute("CastSpellByName, UseItemByName = AGPS_CAST_WAS, AGPS_USE_WAS")
    assert ns.Tutorial.jumpDemo.anim is not None


def _glide(lua, ns, secs=12.0, step=0.25):
    T = ns.Tutorial
    path = T.jumpDemo.anim
    seen = []
    t = 0.0
    while t < secs and T.jumpDemo:
        lua.execute(f"AGPS_T = AGPS_T + {step}")
        T.JumpDemoTick()
        ns.GPS.Update()
        _arrow(lua)
        o = ns.Geo.override
        if o and T.jumpDemo:
            seen.append((o.x, o.y, bool(T.jumpDemo.gliding)))
        t += step
    return path, seen


def test_clicking_it_glides_the_arrow_down_to_the_landing_and_arrives(tut):
    lua, ns = tut
    N, T = ns.Nav, ns.Tutorial
    _at_demo(lua, ns)
    d = _twin(ns)
    d.GetScript(d, "OnClick")(d, "LeftButton")
    path, seen = _glide(lua, ns)
    assert T.jumpDemo, "the demo ended by itself"
    # (it went forward, off the edge in a glide, then down to the stop)
    assert any(g for _x, _y, g in seen), "never in the glide"
    first, last = path.drop[1], path.drop[2]
    landing = (path.pts[2 * last - 1], path.pts[2 * last])
    assert any(abs(x - landing[0]) < 15 and abs(y - landing[1]) < 15 for x, y, _g in seen)
    o = ns.Geo.override
    assert abs(o.x + 2558.3) < 2 and abs(o.y + 3232.5) < 2
    assert N.arrivedAt is not None and len(N.stops) == 0
    o2 = ns.Geo.override
    assert "Arrived" in str(N.Status(o2.x, o2.y, o2.cont))  # (the directions say so, as at any trip's end)
    assert first >= 1 and T.jumpDemo.landed


def test_a_to_on_the_controller_clicks_the_demo_button(tut):
    lua, ns = tut
    _at_demo(lua, ns)
    assert _twin(ns) is not None
    ns.Pad.Run(lua.table("select"), True)
    assert ns.Tutorial.jumpDemo.anim is not None


def _restored(lua, ns, before, saved_stops):
    T = ns.Tutorial
    assert not T.JumpDemoOn()
    assert ns.Geo.override is None and ns.FallSpells.demo is None and not ns.Nav.demoRoute
    assert _twin(ns) is None
    assert lua.eval("AGPS_DUMP(AGPS_NS.CharDB().stops)") == saved_stops
    names = [ns.Nav.stops[i].name for i in range(1, len(ns.Nav.stops) + 1)]
    assert names == ["My stop", "Next"], names
    assert [p.name for p in ns.GPS.PendingStops().values()] == ["waiting"]


TRIGGERS = {
    "moved": "AGPS_POS[1] = AGPS_POS[1] + 3",
    "combat": "AGPS_NS.inCombat = true InCombatLockdown = function() return true end",
    "hidden": "AGPS_NS.settings.gps.shown = false",
}


@pytest.mark.parametrize("why", ["moved", "combat", "hidden", "combat_event", "logout", "next", "back", "exit"])
@pytest.mark.parametrize("glide", [False, True])
def test_every_exit_puts_everything_back_at_once(tut, why, glide):
    lua, ns = tut
    T = ns.Tutorial
    before, saved_stops = _at_demo(lua, ns)
    if glide:
        d = _twin(ns)
        d.GetScript(d, "OnClick")(d, "LeftButton")
        lua.execute("AGPS_T = AGPS_T + 1")
        T.JumpDemoTick()
    if why in TRIGGERS:
        lua.execute(TRIGGERS[why])
        lua.execute("AGPS_T = AGPS_T + 1")
        T.JumpDemoTick()
    elif why == "combat_event":
        lua.execute("AGPS_FIRE('PLAYER_REGEN_DISABLED')")
    elif why == "logout":
        lua.execute("AGPS_FIRE('PLAYER_LOGOUT')")
    elif why == "next":
        T.NextClicked()
    elif why == "back":
        T.Back()
    else:
        T.Exit()
    assert not T.JumpDemoOn(), why
    lua.execute("InCombatLockdown = function() return false end AGPS_NS.inCombat = false AGPS_POS = { 2254.0, 293.0, 0 }")
    if why == "hidden":
        ns.settings.gps.shown = True
    if T.run and not T.run.card and why in ("moved", "hidden", "combat"):
        assert str(T.panel.body._text).startswith("The example stopped")
    _restored(lua, ns, before, saved_stops)
    if T.run:
        T.Exit()
    db, live = _state(lua)
    assert db == before[0], _diff(before[0], db)  # (the real settings and the saved variables exactly as before)


def test_show_again_plays_it_again_and_no_route_is_fine(tut):
    lua, ns = tut
    T = ns.Tutorial
    _at_demo(lua, ns, route=False)
    lua.execute("AGPS_POS[1] = AGPS_POS[1] + 3")
    lua.execute("AGPS_T = AGPS_T + 1")
    T.JumpDemoTick()
    assert not T.JumpDemoOn()
    lua.execute("AGPS_POS[1] = AGPS_POS[1] - 3")
    T.panel.choices[1].GetScript(T.panel.choices[1], "OnClick")(T.panel.choices[1], "LeftButton")
    assert T.JumpDemoOn() and ns.Geo.override is not None
    T.Exit()
    assert not T.JumpDemoOn() and ns.Geo.override is None


def test_the_demo_shows_in_the_games_world_map_for_a_world_map_player(tut):
    lua, ns = tut
    T, st = ns.Tutorial, ns.settings.gps
    st.useWorldMap = True
    try:
        before, saved_stops = _at_demo(lua, ns)
        assert st.useWorldMap is True and lua.eval("WorldMapFrame:IsShown()")
        assert _twin(ns) is not None or ns.FallSpells.CastNow() is not None
        ns.GPS.CloseWorldMap()
        lua.execute("AGPS_T = AGPS_T + 1")
        T.JumpDemoTick()
        assert not T.JumpDemoOn()
        _restored(lua, ns, before, saved_stops)
        T.Exit()
        assert st.useWorldMap is True
    finally:
        st.useWorldMap = False
