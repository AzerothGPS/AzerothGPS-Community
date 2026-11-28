"""FlowUp Route (item 145, Kooki3z 2026-11-27): with FlowUp Forever installed (no API, everything in its own
namespace), a quick button routes to each step of its guide in turn, read only from the pin it draws on the minimap (a
frame of its own under Minimap: `sp` the spot shown, `sp.s` the step, `ring` and `glyph`), as RestedXP Route follows
RestedXP's arrow. A step's stop is done when FlowUp moves on, never by getting there. The whole addon (gameharness) with
a stand-in for FlowUp built from the shape of what it shows, none of its route data."""
import pytest

pytest.importorskip("lupa.lua51")

# (a stand-in FlowUp: its saved FlowUpDB, and the minimap pin frame its MapPin module draws for the pinned step;
# `AGPS_FU_STEP(id, spot)` moves it the way its DrawMinimap does: the pin shown with the new spot, or hidden)
FLOWUP = r"""
  FlowUpDB = { opts = { autoPin = true, mapPin = true } }
  local function pin()
    local b = CreateFrame("Frame", nil, Minimap)
    b.bg = b:CreateTexture(nil, "BACKGROUND")
    b.ring = b:CreateTexture(nil, "BORDER")
    b.icon = b:CreateTexture(nil, "ARTWORK")
    b.glyph = b:CreateFontString(nil, "OVERLAY", "GameFontNormal")
    b:Hide()
    return b
  end
  AGPS_FU_PINS = { pin(), pin() }
  -- another addon's frame on the minimap, with an `sp` of its own: not FlowUp's
  local other = CreateFrame("Frame", nil, Minimap)
  other.sp = { s = { id = "x" }, wx = 0, wy = 0 }
  other:Show()
  function AGPS_FU_STEP(spot, target)
    for _, b in ipairs(AGPS_FU_PINS) do b:Hide() end
    if not spot then return end
    local b = AGPS_FU_PINS[1]
    b.sp = spot
    b:Show()
    if target then
      local t = AGPS_FU_PINS[2]
      t.sp = target
      t:Show()
    end
  end
"""


def _game(fu=True, off=True):
    from azerothgps.gameharness import start
    lua, ns = start()
    ns.Nav.FUN = False
    lua.execute("AGPS_PRINTS = {} AGPS_NS.Print = function(m) AGPS_PRINTS[#AGPS_PRINTS + 1] = m end")
    if fu:
        lua.execute(FLOWUP)
        # (Northshire, Elwynn Forest's uiMap 1429: the step's world yards as ours)
        lua.execute('AGPS_FU_STEP({ s = { id = "s-010", plain = "Kill |cffff0000Kobold Vermin|r" }, m = 1429, x = 48, y = 40,'
                    ' wx = -8900.0, wy = 40.0 })')
    if off:
        cdb = ns.CharDB()
        for k in ("rxpFollow", "zygorFollow", "polestarFollow", "questifyFollow", "aprFollow", "openxpFollow",
                  "flowupFollow"):
            cdb[k] = False
    return lua, ns


def _stops(ns):
    return [(round(d.x), round(d.y), d.cont, str(d.name), d.flowup) for d in ns.Nav.stops.values()]


def _prints(lua):
    return [str(m) for m in lua.eval("AGPS_PRINTS").values()]


def test_the_button_is_there_only_with_flowup():
    lua, ns = _game(fu=False)
    assert "flowupRoute" not in [str(t.id) for t in ns.GPS.QuickSlots().values()]
    assert not ns.FlowUp.Available()
    lua.execute(FLOWUP)
    assert ns.FlowUp.Available()
    assert "flowupRoute" in [str(t.id) for t in ns.GPS.QuickSlots().values()]
    assert ns.GPS.QuickPlace("flowupRoute") == "barRight"


def test_each_step_is_the_next_stop_and_done_when_flowup_moves_on():
    lua, ns = _game()
    N, F = ns.Nav, ns.FlowUp
    lua.execute("AGPS_POS[1], AGPS_POS[2], AGPS_POS[3] = -8950.0, 0.0, 0")
    N.SetDestination(-9000.0, 400.0, 0, "Somewhere else")
    F.Toggle()
    assert F.On()
    s = _stops(ns)
    assert len(s) == 1 and s[0][:3] == (-8900, 40, 0)
    assert s[0][3] == "FlowUp: Kill Kobold Vermin"
    assert s[0][4].startswith("s-010:")
    assert _prints(lua)[-1].startswith("FlowUp Route: on. Each FlowUp step")
    # getting there doesn't finish it
    lua.execute("AGPS_POS[1], AGPS_POS[2] = -8900.0, 40.0")
    F.Tick()
    assert len(_stops(ns)) == 1 and N.stops[1].flowup
    # FlowUp moves on: that stop done, the next one the stop; a spot in map percent only (no world yards): the map's
    lua.execute('AGPS_FU_STEP({ s = { id = "s-011" }, m = 1429, x = 45.0, y = 38.0 })')
    F.Tick()
    s = _stops(ns)
    x, y, c = lua.eval("AGPS_NS.Layers.MapToWorld(1429, 0.45, 0.38)")
    assert len(s) == 1 and s[0][:3] == (round(x), round(y), c) and s[0][3] == "FlowUp: Step"
    # a step with targets: the step's own spot first, not its target's
    lua.execute('AGPS_FU_STEP({ s = { id = "s-012" }, m = 1429, x = 50, y = 50, wx = -8800.0, wy = 120.0 },'
                ' { s = { id = "s-012" }, tg = { o = "kill" }, m = 1429, x = 51, y = 51, wx = -8700.0, wy = 200.0 })')
    F.Tick()
    assert _stops(ns)[0][:2] == (-8800, 120)
    # no pin shown (a step with no place, another continent): no stop, still following
    lua.execute("AGPS_FU_STEP(nil)")
    F.Tick()
    assert _stops(ns) == [] and F.On()
    # kept over a /reload
    lua.execute('AGPS_FU_STEP({ s = { id = "s-013" }, m = 1429, x = 50, y = 50, wx = -8810.0, wy = 130.0 })')
    F.Tick()
    N.Restore()
    F.lastKey = None
    F.Tick()
    assert len(_stops(ns)) == 1


def test_with_flowups_map_pin_off_its_game_pin_is_followed():
    lua, ns = _game()
    F = ns.FlowUp
    lua.execute("""AGPS_FU_STEP(nil) FlowUpDB.opts.mapPin = false FlowUpDB.gamePin = { m = 1429, x = 45.0, y = 38.0 }
      AGPS_UW = { uiMapID = 1429, position = { x = 0.45, y = 0.38 } }
      C_Map.GetUserWaypoint = function() return AGPS_UW end""")
    F.Toggle()
    x, y, c = lua.eval("AGPS_NS.Layers.MapToWorld(1429, 0.45, 0.38)")
    assert _stops(ns)[0][:3] == (round(x), round(y), c)
    # the game's pin taken off (by hand, or another addon's put there): not FlowUp's any more
    lua.execute("AGPS_UW = nil")
    F.Tick()
    assert _stops(ns) == [] and F.On()


def test_flowup_is_only_read():
    lua, ns = _game()
    snap = """(function()
      local p = AGPS_FU_PINS[1]
      return tostring(p:IsShown()) .. ':' .. p.sp.s.id .. ':' .. p.sp.wx .. ':' .. tostring(FlowUpDB.opts.mapPin)
        .. ':' .. tostring(FlowUpDB.gamePin)
    end)()"""
    before = lua.eval(snap)
    ns.FlowUp.Toggle()
    ns.FlowUp.Tick()
    assert lua.eval(snap) == before


def test_another_route_picked_turns_it_off():
    lua, ns = _game()
    N, F = ns.Nav, ns.FlowUp
    lua.execute("AGPS_POS[1], AGPS_POS[2], AGPS_POS[3] = -8950.0, 0.0, 0")
    F.Toggle()
    assert len(_stops(ns)) == 1
    N.Clear()
    N.SetDestination(-8920.0, 60.0, 0, "My own place")
    F.Tick()
    assert not F.On() and [str(d.name) for d in N.stops.values()] == ["My own place"]
    assert _prints(lua)[-1].startswith("FlowUp Route: off (the route was changed)")


def test_one_guide_at_a_time():
    lua, ns = _game()
    F, O = ns.FlowUp, ns.OpenXP
    lua.execute("AGPS_POS[1], AGPS_POS[2], AGPS_POS[3] = -8950.0, 0.0, 0")
    lua.execute("OpenXPArrow = {}")
    F.Toggle()
    assert F.On()
    O.Toggle()
    assert O.On() and not F.On()
    F.Toggle()
    assert F.On() and not O.On() and len(_stops(ns)) == 1 and _stops(ns)[0][4]


def test_flowup_route_is_on_by_itself_and_the_other_guides_first():
    lua, ns = _game(off=False)
    lua.execute("AGPS_POS[1], AGPS_POS[2], AGPS_POS[3] = -8950.0, 0.0, 0")
    F = ns.FlowUp
    assert F.On() and ns.CharDB().flowupFollow is None
    F.Tick()
    assert len(_stops(ns)) == 1
    # OpenXP and Azeroth Pilot loaded too: theirs first (and asking each other doesn't loop)
    lua, ns = _game(off=False)
    lua.execute("OpenXPArrow = {} APR = { Arrow = { Active = false, x = 0, y = 0 } }")
    F, O, A = ns.FlowUp, ns.OpenXP, ns.AzerothPilot
    assert A.On() and not O.On() and not F.On()
    # with FlowUp Route on by hand, the others stay off by themselves
    ns.CharDB().flowupFollow = True
    lua.execute("RXPG_ARROW = { element = { wx = 330.0, wy = 2270.0, instance = 0, step = { index = 3, active = true } } }")
    assert F.On() and not ns.RestedXP.On() and not A.On() and not O.On()
    for k in ("Zygor", "Polestar", "Questify"):
        assert not ns[k].On()
