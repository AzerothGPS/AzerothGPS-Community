"""OpenXP Route (item 111, Kooki3z 2026-11-26): with OpenXP 2.0 installed (no API, everything in its own namespace), a
quick button routes to each step of its guide in turn, read only from the pins it hands to HereBeDragons-Pins-2.0 (the
one registered under OpenXP's own table, its current step's: `kind == "step"`, `glowOn`), world x and y swapped from
ours; the step's guide and number from its saved OpenXPCharDB. A step's stop is done when OpenXP moves on, never by
getting there. The whole addon (gameharness) with a stand-in for OpenXP: its arrow frame, its pins in the library, its
saved tables, as Azeroth Pilot Route's tests."""
import pytest

pytest.importorskip("lupa.lua51")

# (a stand-in OpenXP 2.0: the arrow frame it names, LibStub with HereBeDragons-Pins' registries, and a step pin under a
# table like its Pins module, `AGPS_OXP_STEP(pos, wx, wy, inst, title)` moving it the way its Pins.Refresh does)
OPENXP = r"""
  OpenXPArrow = { label = { GetText = function(self) return AGPS_OXP_LABEL end } }
  AGPS_OXP_LABEL = "Kill Kobold Vermin"
  OpenXPDB = { settings = { mapPins = true } }
  OpenXPCharDB = { currentGuide = "Alliance-PoleStar-01-60", guides = { ["Alliance-PoleStar-01-60"] = { step = 4 } } }
  local hbd = { worldmapPins = {}, worldmapPinRegistry = {}, minimapPins = {}, minimapPinRegistry = {} }
  LibStub = LibStub or setmetatable({ libs = {}, minors = {} }, { __call = function(self, n) return self.libs[n] end })
  LibStub.libs["HereBeDragons-Pins-2.0"] = hbd
  AGPS_OXP_REF = { ICON = { disc = "Interface\\AddOns\\OpenXP\\Media\\Map\\step_disc" }, STEPS_AHEAD = 6 }
  AGPS_OXP_HBD = hbd
  local function add(reg, data, ref, icon, inst, x, y)
    reg[ref] = reg[ref] or {}
    reg[ref][icon] = true
    data[icon] = { instanceID = inst, x = x, y = y }
  end
  function AGPS_OXP_CLEAR()
    for _, k in ipairs({ "worldmapPins", "worldmapPinRegistry", "minimapPins", "minimapPinRegistry" }) do hbd[k] = {} end
  end
  -- the step you're on (pulsing), the next one (not), a mob's pin, and another addon's pin
  function AGPS_OXP_STEP(pos, wx, wy, inst, title, minimapOnly)
    AGPS_OXP_CLEAR()
    OpenXPCharDB.guides["Alliance-PoleStar-01-60"].step = pos
    if not pos then return end
    local p = { kind = "step", glowOn = true, entry = { pos = pos, lines = { title, "Step " .. pos } } }
    p.mini = { owner = p, isMini = true }
    if not minimapOnly then add(hbd.worldmapPinRegistry, hbd.worldmapPins, AGPS_OXP_REF, p, inst, wx, wy) end
    add(hbd.minimapPinRegistry, hbd.minimapPins, AGPS_OXP_REF, p.mini, inst, wx, wy)
    local n = { kind = "step", glowOn = false, entry = { pos = pos + 1, lines = { "Next" } } }
    add(hbd.worldmapPinRegistry, hbd.worldmapPins, AGPS_OXP_REF, n, inst, wx + 300, wy + 300)
    local m = { kind = "mob", glowOn = false, entry = {} }
    add(hbd.worldmapPinRegistry, hbd.worldmapPins, AGPS_OXP_REF, m, inst, wx - 50, wy)
    local other = { kind = "step", glowOn = true, entry = { pos = 1 } }
    add(hbd.worldmapPinRegistry, hbd.worldmapPins, { ICON = { disc = "Interface\\AddOns\\Other\\x" } }, other, inst, 0, 0)
  end
"""


def _game(oxp=True, off=True):
    from azerothgps.gameharness import start
    lua, ns = start()
    ns.Nav.FUN = False
    lua.execute("AGPS_PRINTS = {} AGPS_NS.Print = function(m) AGPS_PRINTS[#AGPS_PRINTS + 1] = m end")
    if oxp:
        lua.execute(OPENXP)
        # (Northshire: the step's place at HBD world x 40 (west), y -8900 (north): ours -8900, 40)
        lua.execute('AGPS_OXP_STEP(4, 40.0, -8900.0, 0, "Kill |cffff0000Kobold Vermin|r")')
    if off:
        cdb = ns.CharDB()
        cdb.rxpFollow, cdb.zygorFollow, cdb.polestarFollow, cdb.questifyFollow, cdb.aprFollow, cdb.openxpFollow = (
            False, False, False, False, False, False)
    return lua, ns


def _stops(ns):
    return [(round(d.x), round(d.y), d.cont, str(d.name), d.openxp) for d in ns.Nav.stops.values()]


def _prints(lua):
    return [str(m) for m in lua.eval("AGPS_PRINTS").values()]


def test_the_button_is_there_only_with_openxp_2():
    lua, ns = _game(oxp=False)
    assert "openxpRoute" not in [str(t.id) for t in ns.GPS.QuickSlots().values()]
    assert not ns.OpenXP.Available()
    lua.execute(OPENXP)
    assert ns.OpenXP.Available()
    assert "openxpRoute" in [str(t.id) for t in ns.GPS.QuickSlots().values()]
    assert ns.GPS.QuickPlace("openxpRoute") == "barRight"


def test_each_step_is_the_next_stop_and_done_when_openxp_moves_on():
    lua, ns = _game()
    N, O = ns.Nav, ns.OpenXP
    lua.execute("AGPS_POS[1], AGPS_POS[2], AGPS_POS[3] = -8950.0, 0.0, 0")
    N.SetDestination(-9000.0, 400.0, 0, "Somewhere else")
    O.Toggle()
    assert O.On()
    s = _stops(ns)
    # (the pin's y is our x, its x our y; its own continent; the step's title without its colors; only the pulsing
    # pin of OpenXP's own table: not the next step's, a mob's or another addon's)
    assert len(s) == 1 and s[0][:3] == (-8900, 40, 0)
    assert s[0][3] == "OpenXP: Kill Kobold Vermin"
    assert s[0][4] == "Alliance-PoleStar-01-60:4:-8900.0,40.0"
    assert _prints(lua)[-1].startswith("OpenXP Route: on. Each OpenXP step")
    # getting there doesn't finish it
    lua.execute("AGPS_POS[1], AGPS_POS[2] = -8900.0, 40.0")
    O.Tick()
    assert len(_stops(ns)) == 1 and N.stops[1].openxp
    # OpenXP moves on: that stop done, the next one the stop (only on the minimap: still found)
    lua.execute('AGPS_OXP_STEP(5, 120.0, -8800.0, 0, "Talk to Marshal McBride", true)')
    O.Tick()
    s = _stops(ns)
    assert len(s) == 1 and s[0][:2] == (-8800, 120) and s[0][3] == "OpenXP: Talk to Marshal McBride"
    # a step with no place (no pin), the guide done or dropped: no stop, still following
    lua.execute("AGPS_OXP_STEP(nil)")
    O.Tick()
    assert _stops(ns) == [] and O.On()
    # a pin with no title: the arrow's text, else "Step"
    lua.execute('AGPS_OXP_STEP(6, 130.0, -8810.0, 0, nil)')
    O.Tick()
    assert _stops(ns)[0][3] == "OpenXP: Kill Kobold Vermin"
    lua.execute('AGPS_OXP_LABEL = nil AGPS_OXP_STEP(7, 140.0, -8820.0, 0, nil)')
    O.Tick()
    assert _stops(ns)[0][3] == "OpenXP: Step"
    # kept over a /reload
    N.Restore()
    O.lastKey = None
    O.Tick()
    assert len(_stops(ns)) == 1


def test_openxp_is_only_read():
    lua, ns = _game()
    before = lua.eval("""(function()
      local n = 0
      for _ in pairs(AGPS_OXP_HBD.worldmapPins) do n = n + 1 end
      return n .. ':' .. OpenXPCharDB.guides['Alliance-PoleStar-01-60'].step .. ':' .. tostring(OpenXPDB.settings.mapPins)
    end)()""")
    ns.OpenXP.Toggle()
    ns.OpenXP.Tick()
    after = lua.eval("""(function()
      local n = 0
      for _ in pairs(AGPS_OXP_HBD.worldmapPins) do n = n + 1 end
      return n .. ':' .. OpenXPCharDB.guides['Alliance-PoleStar-01-60'].step .. ':' .. tostring(OpenXPDB.settings.mapPins)
    end)()""")
    assert before == after


def test_step_pins_off_says_how_to_turn_them_on():
    lua, ns = _game()
    lua.execute("OpenXPDB.settings.mapPins = false AGPS_OXP_CLEAR()")
    ns.OpenXP.Toggle()
    assert ns.OpenXP.On() and _stops(ns) == []
    assert "Step pins" in _prints(lua)[-1]


def test_another_route_picked_turns_it_off():
    lua, ns = _game()
    N, O = ns.Nav, ns.OpenXP
    lua.execute("AGPS_POS[1], AGPS_POS[2], AGPS_POS[3] = -8950.0, 0.0, 0")
    O.Toggle()
    assert len(_stops(ns)) == 1
    N.Clear()
    N.SetDestination(-8920.0, 60.0, 0, "My own place")
    O.Tick()
    assert not O.On() and [str(d.name) for d in N.stops.values()] == ["My own place"]
    assert _prints(lua)[-1].startswith("OpenXP Route: off (the route was changed)")


def test_one_guide_at_a_time():
    lua, ns = _game()
    O, A = ns.OpenXP, ns.AzerothPilot
    lua.execute("AGPS_POS[1], AGPS_POS[2], AGPS_POS[3] = -8950.0, 0.0, 0")
    lua.execute("""APR = { ActiveRoute = "Forever-Elwynn", Arrow = { Active = true, x = 10.0, y = -8850.0 },
      GetCurrentStep = function(self) return {}, 3, {} end }""")
    O.Toggle()
    assert O.On()
    A.Toggle()
    assert A.On() and not O.On()
    O.Toggle()
    assert O.On() and not A.On() and len(_stops(ns)) == 1 and _stops(ns)[0][4]


def test_openxp_route_is_on_by_itself_and_the_other_guides_first():
    lua, ns = _game(off=False)
    lua.execute("AGPS_POS[1], AGPS_POS[2], AGPS_POS[3] = -8950.0, 0.0, 0")
    O = ns.OpenXP
    assert O.On() and ns.CharDB().openxpFollow is None
    O.Tick()
    assert len(_stops(ns)) == 1
    # Azeroth Pilot loaded too: its route first (and asking each other doesn't loop)
    lua, ns = _game(off=False)
    lua.execute("APR = { Arrow = { Active = false, x = 0, y = 0 } }")
    O, A = ns.OpenXP, ns.AzerothPilot
    assert A.On() and not O.On()
    A.Toggle()
    assert not A.On() and O.On()
    # with OpenXP Route on by hand, the others stay off by themselves
    for k in ("RestedXP", "Zygor", "Polestar", "Questify", "AzerothPilot"):
        ns.CharDB()[{"RestedXP": "rxpFollow", "Zygor": "zygorFollow", "Polestar": "polestarFollow",
                     "Questify": "questifyFollow", "AzerothPilot": "aprFollow"}[k]] = None
    ns.CharDB().openxpFollow = True
    lua.execute("RXPG_ARROW = { element = { wx = 330.0, wy = 2270.0, instance = 0, step = { index = 3, active = true } } }")
    assert O.On() and not ns.RestedXP.On() and not A.On()
