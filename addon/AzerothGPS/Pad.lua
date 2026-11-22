-- A controller on the map (asked 2026-11-16: "for the next AzerothGPS version lets plan on full controller support";
-- docs/controller-plan.md, phase 1). The client lets an addon's frames have no gamepad events of their own
-- (EnableGamePadButton / EnableGamePadStick are protected), so: the pad's buttons are override bindings of ours, owned
-- by a frame of ours, set only while the map is open and out of combat, and cleared before combat's lockdown
-- (PLAYER_REGEN_DISABLED), on close and on logout; the right stick, when it pans, is read by polling
-- (C_GamePad.GetDeviceMappedState). Nothing of Blizzard's is shown, hidden, moved or marked, ever: the game's
-- controller UI runs its own protected code as its panels show, and anything an addon touched there gets blocked
-- (1.2.2's world map, AzerothGPS#508's group finder eye).
--
-- While bound: A sets a stop at the reticle (the map's middle), or routes to the icon under it; X removes the stop
-- under it ("Remove?", then A); B backs out (a question's No, "Remove?", a menu, then the map); LT / RT zoom out and in;
-- the D-pad pans; the left stick press recenters on you. A question up:
-- A is its Yes, B its No. A legend of these on the map. The player's own "Show/Hide AzerothGPS" key opens the map; once,
-- with a pad first active, the player is offered a pad button for it (and any time with /agps pad). Drawing a farming
-- area: A marks a corner at the reticle, X takes the last one off, Y finishes (A on the first corner too), B cancels.
local _, ns = ...
local L = ns.L
local Pad = {}
ns.Pad = Pad

Pad.OWNER = "AzerothGPSPadOwner" -- our own frame: the override bindings' owner (never UIParent)
-- The map's controls a pad drives, and their buttons (the pad's keys, GamepadConstants.lua): Options > Controller lists
-- them, each one changeable, saved per profile (settings.gps.padBinds: [action] = key, the defaults left out; asked
-- 2026-11-16, "add a new Controller section and make a keybinding list for each map control for the controller there").
-- `game`: a binding of the game's own (the player's key for Show/Hide AzerothGPS), not one of the map's overrides.
-- The defaults (asked 2026-11-16: "update the default controller settings to what you think would be most optimal"):
-- the face buttons for the map's own (A a stop, B back, X remove, Y the map menu), the triggers zoom, the D-pad pans,
-- the stick presses recenter and open Options; LB alone Select (an entrance's map, Confirm Route), RB alone View
-- Controls; LB with a face button the route's own (+ X Clear Route, + Y Quest Route), so the one that loses a route is
-- never a single press. Back: Show/Hide GPS (the game's binding). Start: Pause/Unpause (1.3.9, asked 2026-11-18: "Make
-- a new controller action 'Pause/Unpause' default keybind to Start button"; it was Pause Routing on LB + B: the same
-- control, id "pause", renamed and moved, so a button the player gave it is kept, and Start given to another control
-- by the player keeps it, Pause/Unpause then on none: Pad.Key's step-aside).
Pad.ACTIONS = {
  { "select", "PAD1", L["Set a stop, or route to the icon"] },
  { "yes", "PAD1", L["Yes on a question"] },
  { "remove", "PAD3", L["Remove a stop"] },
  { "back", "PAD2", L["Back"] }, -- (asked 2026-11-16: "Back, close the map, No is now Back")
  -- (asked 2026-11-16: "Need a clear route key binding for controller": the map's Clear Route, no button by default)
  { "clear", "PADLSHOULDER+PAD3", L["Clear Route"] },
  -- (asked 2026-11-16: "I want quest route and pause route to allow be assignable actions"; no button by default)
  { "questRoute", "PADLSHOULDER+PAD4", L["Quest Route"] },
  { "pause", "PADFORWARD", L["Pause/Unpause"] },
  -- (asked 2026-11-16: "Need another action to do the same action as left click to open dungeon maps for example")
  -- (named Select, the stop's control Set Stop again: asked 2026-11-16, "Change the name of Open to Select and the
  -- existing Select to Set Stop")
  { "click", "PADLSHOULDER", L["Select"] },
  -- (asked 2026-11-16: "a controller action button (if bound) that opens a overlay ... show the controller image over a
  -- black faded background ... stays visible for 10 secs and fades away over the next 5 secs ... called View Controls")
  { "viewControls", "PADRSHOULDER", L["View Controls"] },
  { "zoomIn", "PADRTRIGGER", L["Zoom in"] },
  { "zoomOut", "PADLTRIGGER", L["Zoom out"] },
  { "panUp", "PADDUP", L["Pan up"] },
  { "panDown", "PADDDOWN", L["Pan down"] },
  { "panLeft", "PADDLEFT", L["Pan left"] },
  { "panRight", "PADDRIGHT", L["Pan right"] },
  { "recenter", "PADLSTICK", L["Recenter on you"] },
  { "toggle", "PADBACK", L["Show/Hide GPS"], game = true },
  -- (asked 2026-11-16: "need a map menu button and when it opens the map pan controls navigate the buttons, Set a stop
  -- button selects the map icon. Pressing the map menu controller button again closes it")
  { "menu", "PAD4", L["Map menu"] },
  -- (asked 2026-11-16: "Need a way to open options page with a controller"; Options then moves with the pad itself,
  -- PadOptions.lua)
  { "options", "PADRSTICK", L["Options"] },
}
-- Pairs (asked 2026-11-16: "need to support 2 selections like LT + A"): a binding is a key, or a modifier and a key
-- ("PADLTRIGGER+PAD1"). The modifier is read from the pad's state as the key is pressed (C_GamePad; nothing of the
-- game's own modifier emulation changed). A modifier that has a hold of its own (LT zooms out) starts it only after
-- it's held MOD_HOLD_DELAY alone; a pair pressed meanwhile cancels it till it's let go.
Pad.MODIFIERS = { PADLTRIGGER = true, PADRTRIGGER = true, PADLSHOULDER = true, PADRSHOULDER = true }
Pad.MOD_HOLD_DELAY = 0.3 -- seconds
-- Held bindings (asked 2026-11-16: "support a 'hold' keybinding, holding a key more than 2 seconds. This is allows the
-- same key to do 2 different actions so A could be 1 control and A (hold) would be another. Defined by a check box
-- next to the controller key binding"): settings.gps.padHold[action] = true. Such a control fires once its button (or
-- pair) has been held HOLD_SECONDS, once; a button with a held control does its other one when let go sooner (a button
-- with none still acts as it's pressed). The pan and zoom controls, done while held, can't be held ones.
Pad.HOLD_SECONDS = 2
function Pad.IsHold(id)
  local h = ns.settings and ns.settings.gps and ns.settings.gps.padHold
  return h and h[id] and true or false
end
-- a control's binding in the pad's own labels, "(hold)" after a held one
function Pad.ActionLabel(id)
  local t = Pad.BindLabel(Pad.Key(id))
  if Pad.IsHold(id) then t = t .. " " .. L["(hold)"] end
  return t
end
-- The game's own gamepad modifiers (asked 2026-11-16: "Back is already taken by default controller controls though"):
-- the client's cvars GamePadEmulateShift / Ctrl / Alt (in Wow.exe's cvar list, "GamePad button that should emulate the
-- Shift key", "none" when unset), read and never changed. A button set as one makes a true game binding with the next
-- button ("SHIFT-PADBACK", shown "LT + Back"): the Show/Hide key, working with the map closed and taking no button
-- from the game's own play.
Pad.EMULATE = { SHIFT = "GamePadEmulateShift", CTRL = "GamePadEmulateCtrl", ALT = "GamePadEmulateAlt" }
-- { [pad key] = "SHIFT" | "CTRL" | "ALT" } as set in the game's Gamepad settings now
function Pad.GameMods()
  local out = {}
  local C = rawget(_G, "C_CVar")
  local get = (type(C) == "table" and C.GetCVar) or rawget(_G, "GetCVar")
  if not get then return out end
  for mod, cvar in pairs(Pad.EMULATE) do
    local ok, v = pcall(get, cvar)
    if ok and type(v) == "string" and v:find("^PAD") then out[v] = mod end
  end
  return out
end
-- a game binding's modifiers ({ "SHIFT", ... }) and its pad key: "SHIFT-PADBACK" -> { "SHIFT" }, "PADBACK"
function Pad.GameSplit(bind)
  local mods = {}
  if type(bind) ~= "string" then return mods, bind end
  local rest = bind
  while true do
    local m, r = rest:match("^(%u+)%-(.+)$")
    if not (m and (m == "SHIFT" or m == "CTRL" or m == "ALT")) then break end
    mods[#mods + 1] = m
    rest = r
  end
  return mods, rest
end
-- a binding's modifier (or nil) and its key
function Pad.Split(bind)
  if type(bind) ~= "string" then return nil, bind end
  local m, k = bind:match("^(PAD%w+)%+(PAD%w+)$")
  if m then return m, k end
  return nil, bind
end
-- the modifiers some pair uses now: { [key] = true }
function Pad.ChordMods()
  local out = {}
  for _, a in ipairs(Pad.ACTIONS) do
    local m = Pad.Split(Pad.Key(a[1]))
    if m and not a.game then out[m] = true end
  end
  return out
end
Pad.SHARED = { select = "yes", yes = "select" } -- (one button for both: a question up, its Yes; else the stop)
Pad.HELD = { panUp = true, panDown = true, panLeft = true, panRight = true, zoomIn = true, zoomOut = true }
-- (the MVP's names for its buttons, Pad.Press's)
Pad.LEGACY = { A = { "yes", "select" }, B = { "back" }, X = { "remove" }, Up = { "panUp" }, Down = { "panDown" },
  Left = { "panLeft" }, Right = { "panRight" }, LT = { "zoomOut" }, RT = { "zoomIn" }, LS = { "recenter" } }
Pad.CAPTURE_SECONDS = 8 -- Change: waits this long for a button
Pad.CANCEL_KEY = "PAD2" -- (B held CANCEL_HOLD: cancels a Change, as Escape does; a tap is B, bound)
Pad.CANCEL_HOLD = 1
Pad.PAN_UI = 320 -- UI units a second the D-pad pans at, held (and the right stick at full tilt)
Pad.ZOOM_TIMES = 2.2 -- the triggers zoom this many times a second, held
Pad.NEAR_UI = 14 -- the reticle is on an icon or a stop this near its middle (UI units)
Pad.CHECK_SECONDS = 0.25 -- how often whether the pad's buttons are wanted is looked at
Pad.PAN_STEP = 80 -- UI units a macro's pan moves the view, once a press
-- Each control as a macro line (asked 2026-11-16: "if the Player could make a macro instead and put that as a
-- controller binding to do the same function, add it as a indicator tool tip"): Options > Controller's "Macro" tag
-- shows it. The pan and zoom controls, done while held, are one step a press as a macro.
Pad.MACROS = {
  select = "/agps pad select", yes = "/agps pad yes", remove = "/agps pad remove", back = "/agps pad back",
  clear = "/agps clear", questRoute = "/agps questroute", pause = "/agps pause", click = "/agps pad click", viewControls = "/agps pad viewcontrols", recenter = "/agps pad recenter", toggle = "/agps toggle", menu = "/agps menu",
  options = "/agps options",
  zoomIn = "/agps zoom in", zoomOut = "/agps zoom out",
  panUp = "/agps pan up", panDown = "/agps pan down", panLeft = "/agps pan left", panRight = "/agps pan right",
}
-- the "Macro" tag's tooltip: its lines (the first the title)
function Pad.MacroTip(id)
  local m = Pad.MACROS[id]
  if not m then return nil end
  local out = { string.format(L["Macro: %s"], m),
    L["Does the same as this control. Make a macro with that line, put it on an action bar, and bind that slot to a controller button in the game's Key Bindings."] }
  if Pad.HELD[id] then out[#out + 1] = L["As a macro it's one step a press."] end
  return out
end
-- a control by its name in a macro (/agps pad <name>, any case), or nil
function Pad.MacroId(name)
  name = type(name) == "string" and name:lower() or ""
  for _, a in ipairs(Pad.ACTIONS) do
    if a[1]:lower() == name then return a[1] end
  end
  return nil
end

local function S() return ns.settings and ns.settings.gps or {} end
local function G() return ns.GPS end

-- The pad active: the client's gamepad on and a device in use.
function Pad.Device()
  local C = rawget(_G, "C_GamePad")
  if type(C) ~= "table" or not C.GetActiveDeviceID then return nil end
  if C.IsEnabled then
    local ok, on = pcall(C.IsEnabled)
    if not ok or not on then return nil end
  end
  local ok, id = pcall(C.GetActiveDeviceID)
  if ok and id ~= nil and id ~= -1 then return id end
  return nil
end
-- Controller support on: the option (on by default) and a pad active.
function Pad.Active()
  return S().padControl ~= false and Pad.Device() ~= nil
end
local function InCombat()
  return (ns.inCombat or (InCombatLockdown and InCombatLockdown())) and true or false
end
-- The map open as a window (not only the minimap square), out of combat, with controller support on.
function Pad.MapOpen()
  local f = rawget(_G, "AzerothGPSFrame")
  local g = G()
  if not (f and f:IsShown() and g) then return false end
  if g.MinimapMode and g.MinimapMode() then return false end
  return true
end
function Pad.Wanted()
  -- (Options open: the pad is its, PadOptions.lua)
  -- (the first-run setup showing: the pad is its, Setup.lua)
  return Pad.Active() and Pad.MapOpen() and not InCombat() and not (Pad.Opt and Pad.Opt.Open())
    and not (ns.Setup and ns.Setup.padBound)
end

-- Our buttons the bindings click: "AnyDown" and "AnyUp", so a held D-pad or trigger is known.
Pad.held = {}
Pad.buttons = {}
local owner
local function Owner()
  if owner then return owner end
  owner = CreateFrame("Frame", Pad.OWNER, UIParent)
  owner:Hide() -- (never shown: only the bindings' owner and the events' listener)
  return owner
end
-- our button a key's binding clicks ("AzerothGPSPad_" .. key), made the first time it's bound
local function KeyButton(key)
  local b = Pad.buttons[key]
  if b then return b end
  b = CreateFrame("Button", "AzerothGPSPad_" .. key, Owner())
  b:RegisterForClicks("AnyDown", "AnyUp")
  b:SetScript("OnClick", function(_, _, down)
    if down ~= false then Pad.SawInput(true) end
    local g = G()
    if g and g.MarkActivity then g.MarkActivity() end -- (the map in use: its quiet clock, G.MinimapIdle)
    Pad.PressKey(key, down ~= false)
  end)
  Pad.buttons[key] = b
  return b
end

-- An action's entry, and its button now (the saved one, else its default).
function Pad.Action(id)
  for _, a in ipairs(Pad.ACTIONS) do
    if a[1] == id then return a end
  end
  return nil
end
function Pad.Key(id)
  local a = Pad.Action(id)
  if not a then return nil end
  if a.game then -- (the game's own binding: the pad key it's on, if any)
    if Pad.IsHold(id) then return (S().padBinds or {})[id] end -- (held: watched by us, Pad.ToggleHoldTick)
    if GetBindingKey then
      local keys = { GetBindingKey("AZEROTHGPS_TOGGLE") }
      for _, k in ipairs(keys) do
        if type(k) == "string" and select(2, Pad.GameSplit(k)):find("^PAD") then return k end
      end
    end
    return (S().padBinds or {})[id]
  end
  local saved = S().padBinds
  local v = saved and saved[id]
  if v == Pad.UNBOUND then return nil end -- (a control with a button by default, taken off it: Pad.Unbind)
  if v then return v end
  -- (a default on a button the player gave another control the same way: that one's, this one on none; asked
  -- 2026-11-16, View Controls' new default RB where Pause Routing already was)
  if a[2] and saved then
    local hold = Pad.IsHold(id)
    for _, o in ipairs(Pad.ACTIONS) do
      if o[1] ~= id and Pad.SHARED[id] ~= o[1] and saved[o[1]] == a[2] and Pad.IsHold(o[1]) == hold then return nil end
    end
  end
  return a[2]
end
-- [key] = { { id, mod }, ... } for the map's own actions (not the game's binding), by the key pressed (a pair's own
-- key; its modifier `mod`), Yes before the stop
function Pad.KeyActions()
  local out = {}
  for _, a in ipairs(Pad.ACTIONS) do
    if not a.game then
      local m, k = Pad.Split(Pad.Key(a[1]))
      if k then
        out[k] = out[k] or {}
        local e = { id = a[1], mod = m, hold = Pad.IsHold(a[1]) or nil }
        if a[1] == "yes" then table.insert(out[k], 1, e) else out[k][#out[k] + 1] = e end
      end
    end
  end
  return out
end
-- a binding in the pad's own labels: "A", or "LT + A" for a pair
function Pad.BindLabel(bind)
  local gm, gk = Pad.GameSplit(bind)
  if #gm > 0 then -- (a game binding with the game's modifiers: "LT + Back", by the button set as Shift there)
    local by = {}
    for key, mod in pairs(Pad.GameMods()) do by[mod] = key end
    local parts = {}
    for _, mod in ipairs(gm) do
      parts[#parts + 1] = by[mod] and Pad.KeyLabel(by[mod]) or ({ SHIFT = L["Shift"], CTRL = L["Ctrl"], ALT = L["Alt"] })[mod]
    end
    parts[#parts + 1] = Pad.KeyLabel(gk)
    return table.concat(parts, " + ")
  end
  local m, k = Pad.Split(bind)
  if not k then return L["Not bound"] end
  if m then return Pad.KeyLabel(m) .. " + " .. Pad.KeyLabel(k) end
  return Pad.KeyLabel(k)
end

-- The bindings on or off as wanted; the reticle and the legend with them. Safe to call any time: in combat it only
-- clears (ClearOverrideBindings before the lockdown, PLAYER_REGEN_DISABLED).
Pad.bound = false
local function Locked() return InCombatLockdown and InCombatLockdown() and true or false end
-- With the game's controller UI on, the game keeps the controller's buttons for its own panels: a binding of ours
-- for Show/Hide GPS on one never runs ("No interface frame to focus!" on Back). Options says so and offers the macro
-- (asked 2026-11-16: "for Show/Hide GPS we need to explain why this won't work in controller UI mode but they can
-- create a macro and assign that to a button to open the map. Other functions are expected to work").
function Pad.ToggleBlocked()
  local g = G()
  return (g and g.ControllerUI and g.ControllerUI()) and true or false
end
-- (a red NOTICE: over it, the macro's line in yellow; asked 2026-11-16: "Add NOTICE: in red bold above that message and
-- make the /agps toggle part bold and yellow" (a line can't be part bold: the colors only))
Pad.TOGGLE_UI_NOTE = "|cffff4040" .. L["NOTICE:"] .. "|r\n"
  .. (L["With the game's controller UI on, the game keeps its buttons for its own panels: Show/Hide GPS can't be set on one. Make a macro with /agps toggle and put it on a controller button to open/close the map."]:gsub("/agps toggle", "|cffffd100/agps toggle|r"))
function Pad.Apply()
  if Pad.Opt then Pad.Opt.Apply() end -- (Options' own: PadOptions.lua)
  if ns.Setup and ns.Setup.PadApply and not ns.Setup.inPadApply then ns.Setup.PadApply() end -- (the setup's: Setup.lua)
  -- (in the lockdown no binding call at all, not even a pcall'd one: it would be blocked and reported; they were
  -- cleared as the fight began)
  if Locked() then
    Pad.ShowMarks(false)
    return false
  end
  local want = Pad.Wanted()
  if want == Pad.bound then
    Pad.ShowMarks(want)
    return want
  end
  local o = Owner()
  if want then
    for key in pairs(Pad.KeyActions()) do
      KeyButton(key)
      pcall(SetOverrideBindingClick, o, true, key, "AzerothGPSPad_" .. key, "LeftButton")
    end
  else
    pcall(ClearOverrideBindings, o)
    Pad.held = {}
  end
  Pad.bound = want
  Pad.ShowMarks(want)
  if want then Pad.MaybeOffer() end
  return want
end
function Pad.Clear()
  if Pad.Opt then Pad.Opt.Clear() end
  if ns.Setup and ns.Setup.PadClear then ns.Setup.PadClear() end
  if owner and not Locked() then pcall(ClearOverrideBindings, owner) end
  Pad.bound, Pad.held, Pad.holds = false, {}, {}
  if Pad.WatchHolds then Pad.WatchHolds() end
  Pad.ShowMarks(false)
end

-- Controller input seen (asked 2026-11-16: "Only show the gamepad controls if controller input is detected"): a pad
-- button or the stick used; the mouse clicked or the game back on the keyboard (GAME_PAD_ACTIVE_CHANGED) hides them
-- again. The bindings stay on either way, so the first press works.
Pad.used = false
function Pad.SawInput(used)
  used = used and true or false
  if used == Pad.used then return end
  Pad.used = used
  if not used and Pad.focus then Pad.SetFocus(nil) end -- (the map menu's ring and its tooltip: the mouse's now)
  Pad.ShowMarks(Pad.bound)
  if ns.PadKeys then ns.PadKeys.Refresh() end -- (the search's legend and keyboard: the controller's only)
  if Pad.Opt and Pad.Opt.UpdateLook then Pad.Opt.UpdateLook() end -- (Options' look too)
  local g = G()
  if g and g.RefreshDrawHint then g.RefreshDrawHint() end -- (drawing an area: its hint in the pad's or the mouse's words)
end

-- The reticle (the map's middle, where A acts) and the legend, both of ours.
local reticle, legend
function Pad.ShowMarks(on)
  on = on and Pad.used
  if not on and Pad.hovered then Pad.SetHovered(nil) end
  local g = G()
  local canvas = g and g.Canvas and g.Canvas()
  local f = rawget(_G, "AzerothGPSFrame")
  if on and canvas and not reticle then
    -- (the map's own crosshair's look, white, not a color of its own: asked 2026-11-16, "when controller support is on,
    -- the crosshair is changed to yellow, lets not do that"; hidden while the map's own is shown, G.crossShown)
    reticle = CreateFrame("Frame", nil, canvas)
    reticle:SetSize(20, 20)
    reticle:SetPoint("CENTER", canvas, "CENTER", 0, 0)
    reticle:SetFrameLevel((canvas:GetFrameLevel() or 1) + 50)
    local h = reticle:CreateTexture(nil, "OVERLAY")
    h:SetColorTexture(1, 1, 1, 0.85)
    h:SetSize(18, 2)
    h:SetPoint("CENTER")
    local v = reticle:CreateTexture(nil, "OVERLAY")
    v:SetColorTexture(1, 1, 1, 0.85)
    v:SetSize(2, 18)
    v:SetPoint("CENTER")
    reticle.h, reticle.v = h, v
  end
  if on and f and not legend then
    legend = f:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall")
    legend:SetPoint("BOTTOM", f, "BOTTOM", 0, 48)
  end
  Pad.marksOn = on and true or false
  if reticle then reticle:SetShown(on and not (g and g.crossShown) and not Pad.MenuOpen() and true or false) end
  if not (on and Pad.MenuOpen()) then Pad.SetFocus(nil) end
  -- (the box on the map's left lists them instead, when it's on and fits; the line at the bottom otherwise, and with
  -- the map menu open: the box is hidden then)
  local boxed = Pad.UpdateBox(on)
  if legend then
    if on then legend:SetText(Pad.LegendText(true)) end
    legend:SetShown(on and not boxed and true or false)
  end
  Pad.reticle, Pad.legend = reticle, legend
end

-- The controller's buttons in a box on the map's left (asked 2026-11-16: "Have a option to show gamepad controls on the
-- map and show them with a light tinted background in this box area, map menu buttons would open on top of them or
-- maybe hide them when map menu is expanded"): one control a line, the most used first, on a dark see-through
-- panel, under the directions and over the map menu's buttons (GPSFrame's G.PadBoxRoom). Hidden while the map menu is
-- open (its own controls on the line at the bottom then). Fewer lines and "..." where they don't all fit; none at all
-- (the line at the bottom) without room for two.
Pad.BOX_PAD, Pad.BOX_LINE, Pad.BOX_TINT = 6, 14, 0.35
function Pad.BoxOn() return S().padLegend ~= false end
-- (`icons`: the buttons as their pictures, Pad.ActionIcon; the text of each where it has none)
function Pad.BoxLines(icons)
  local K = icons and Pad.ActionIcon or Pad.ActionLabel
  local out = {}
  local function add(id, name)
    if Pad.Key(id) then out[#out + 1] = K(id) .. ": " .. name end
  end
  if Pad.Drawing() then -- (drawing an area: its own controls)
    add("select", L["Add Corner"])
    add("remove", L["Undo Corner"])
    add("menu", L["Finish Area"])
    add("back", L["Cancel"])
    if Pad.Key("zoomOut") or Pad.Key("zoomIn") then out[#out + 1] = K("zoomOut") .. "/" .. K("zoomIn") .. ": " .. L["Zoom"] end
    out[#out + 1] = Pad.PanLabel(icons) .. ": " .. L["Pan"]
    return out
  end
  -- (Remove, Map Menu and Clear Route off it, View Controls last: asked 2026-11-16 with the box struck through)
  add("select", L["Set Stop"])
  add("back", L["Back"])
  if Pad.Key("zoomOut") or Pad.Key("zoomIn") then out[#out + 1] = K("zoomOut") .. "/" .. K("zoomIn") .. ": " .. L["Zoom"] end
  out[#out + 1] = Pad.PanLabel(icons) .. ": " .. L["Pan"]
  add("recenter", L["Recenter"])
  add("click", L["Select"]) -- (on the map's controls too, once it has a button: asked 2026-11-16)
  if Pad.Key("yes") ~= Pad.Key("select") or Pad.IsHold("yes") ~= Pad.IsHold("select") then add("yes", L["Yes"]) end
  add("viewControls", L["View Controls"])
  return out
end
local box
-- the box as it should be now (`on`: the controller's marks shown); true when it shows
function Pad.UpdateBox(on)
  local g = G()
  -- (the road or wall tools' legend in its room: the box gives way, the line at the bottom instead)
  local want = on and Pad.BoxOn() and g and g.PadBoxRoom and not (g.mapMenu and g.mapMenu:IsShown())
    and not (g.ToolLegendShown and g.ToolLegendShown())
  local parent, x, y, w, h
  if want then parent, x, y, w, h = g.PadBoxRoom() end
  local fit = parent and h and math.floor((h - 2 * Pad.BOX_PAD) / Pad.BOX_LINE) or 0
  if fit < 2 then
    if box then box:Hide() end
    Pad.box = box
    return false
  end
  if not box then
    box = CreateFrame("Frame", nil, parent)
    box.bg = box:CreateTexture(nil, "BACKGROUND")
    box.bg:SetAllPoints()
    box.bg:SetColorTexture(0, 0, 0, Pad.BOX_TINT)
    box.lines = {}
  end
  if box:GetParent() ~= parent then box:SetParent(parent) end
  box:SetFrameLevel((parent:GetFrameLevel() or 1) + 20)
  local lines = Pad.BoxLines(true)
  if #lines > fit then
    local cut = {}
    for i = 1, fit - 1 do cut[i] = lines[i] end
    cut[fit] = "..."
    lines = cut
  end
  for i, text in ipairs(lines) do
    local fs = box.lines[i]
    if not fs then
      fs = box:CreateFontString(nil, "ARTWORK", "GameFontHighlightSmall")
      fs:SetJustifyH("LEFT")
      fs:SetWordWrap(false)
      box.lines[i] = fs
    end
    fs:ClearAllPoints()
    fs:SetPoint("TOPLEFT", box, "TOPLEFT", Pad.BOX_PAD, -Pad.BOX_PAD - (i - 1) * Pad.BOX_LINE)
    fs:SetWidth(w - 2 * Pad.BOX_PAD)
    fs:SetText(text)
    fs:Show()
  end
  for i = #lines + 1, #box.lines do box.lines[i]:Hide() end
  box.shownLines = lines
  box:ClearAllPoints()
  box:SetPoint("TOPLEFT", parent, "TOPLEFT", x, y)
  box:SetSize(w, #lines * Pad.BOX_LINE + 2 * Pad.BOX_PAD)
  box:Show()
  Pad.box = box
  return true
end
-- A key's name in the pad's own labels (PlayStation's shapes, else letters).
function Pad.Shapes()
  local C = rawget(_G, "C_GamePad")
  if type(C) == "table" and C.GetDeviceMappedState then
    local ok, st = pcall(C.GetDeviceMappedState, Pad.Device())
    local style = ok and type(st) == "table" and st.labelStyle or nil
    return style == "Shapes" or style == 2
  end
  return false
end
function Pad.KeyLabel(key)
  if not key then return L["Not bound"] end
  local names = Pad.Shapes() and {
    PAD1 = L["Cross"], PAD2 = L["Circle"], PAD3 = L["Square"], PAD4 = L["Triangle"],
    PADLSHOULDER = "L1", PADRSHOULDER = "R1", PADLTRIGGER = "L2", PADRTRIGGER = "R2", PADLSTICK = "L3", PADRSTICK = "R3",
  } or {
    PAD1 = "A", PAD2 = "B", PAD3 = "X", PAD4 = "Y",
    PADLSHOULDER = "LB", PADRSHOULDER = "RB", PADLTRIGGER = "LT", PADRTRIGGER = "RT",
    PADLSTICK = L["Left stick press"], PADRSTICK = L["Right stick press"],
  }
  local any = { PADDUP = L["D-pad up"], PADDDOWN = L["D-pad down"], PADDLEFT = L["D-pad left"],
    PADDRIGHT = L["D-pad right"], PADBACK = L["Back"], PADFORWARD = L["Start"] }
  local p = key:match("^PADPADDLE(%d)$")
  if p then return string.format(L["Paddle %s"], p) end
  return names[key] or any[key] or key
end
-- The buttons as pixel-art icons (asked 2026-11-16: "generate a set of pixel like controller icons to use on the map
-- for controls instead of just using the letter"): our own, padicons.py's (`agps padicons`), Media\Pad\<name>_<px>.tga,
-- each drawn at each of ICON_PX pixel for pixel; shown at ICON_UNITS UI units, the size nearest its pixels on the
-- screen (shrunk by the game's filter it would blur, and nothing above LINEAR may be asked). A key with no icon (a
-- paddle), or icons the client doesn't know yet (new files: a /reload), keep their text.
Pad.ICON_DIR = "Interface\\AddOns\\AzerothGPS\\Media\\Pad\\"
Pad.ICON_PX = { 12, 14, 16, 18, 20, 24, 28, 32, 40 } -- (padicons.py's ICON_PX)
Pad.ICON_UNITS = 14 -- (a line of the box on the map: Pad.BOX_LINE)
Pad.ICONS = { PAD1 = "A", PAD2 = "B", PAD3 = "X", PAD4 = "Y", PADLSHOULDER = "LB", PADRSHOULDER = "RB",
  PADLTRIGGER = "LT", PADRTRIGGER = "RT", PADLSTICK = "LStickPress", PADRSTICK = "RStickPress", PADDUP = "DPadUp",
  PADDDOWN = "DPadDown", PADDLEFT = "DPadLeft", PADDRIGHT = "DPadRight", PADBACK = "View", PADFORWARD = "Menu",
  DPAD = "DPad" }
-- (a pad labeled with shapes: PlayStation's; its other buttons as the Xbox set's)
Pad.SHAPE_ICONS = { PAD1 = "Cross", PAD2 = "Circle", PAD3 = "Square", PAD4 = "Triangle", PADLSHOULDER = "L1",
  PADRSHOULDER = "R1", PADLTRIGGER = "L2", PADRTRIGGER = "R2" }
-- the drawn size nearest `units` UI units on a frame of effective scale `effScale`
function Pad.IconPx(units, effScale)
  local want = (units or Pad.ICON_UNITS) * (ns.PixelsPerUnit and ns.PixelsPerUnit(effScale or 1) or 1)
  local best, bd = Pad.ICON_PX[1], math.huge
  for _, n in ipairs(Pad.ICON_PX) do
    local d = math.abs(n - want)
    if d < bd then best, bd = n, d end
  end
  return best
end
local probe
Pad.iconKnown = {}
-- the client knows the file (it was there at login): a hidden texture of ours set to it has a file id
local function Known(file)
  local k = Pad.iconKnown[file]
  if k ~= nil then return k end
  if not probe then
    probe = CreateFrame("Frame"):CreateTexture(nil, "BACKGROUND") -- (a frame of our own, never shown)
    probe:Hide()
  end
  probe:SetTexture(file)
  k = true
  if probe.GetTextureFileID then
    local ok, id = pcall(probe.GetTextureFileID, probe)
    k = not ok or id ~= nil
  end
  Pad.iconKnown[file] = k
  return k
end
-- a key's icon file at `px` pixels, or nil
function Pad.IconFile(key, px)
  local name = (Pad.Shapes() and Pad.SHAPE_ICONS[key]) or Pad.ICONS[key]
  if not name then return nil end
  local file = Pad.ICON_DIR .. name .. "_" .. (px or Pad.IconPx()) .. ".tga"
  if not Known(file) then return nil end
  return file
end
-- the map's own scale (its icons' size on the screen)
local function MapScale()
  local f = rawget(_G, "AzerothGPSFrame")
  return f and f.GetEffectiveScale and f:GetEffectiveScale() or 1
end
-- a key's icon inline in text ("|T...|t", `units` big, default ICON_UNITS), or nil
function Pad.KeyIcon(key, units, effScale)
  units = units or Pad.ICON_UNITS
  local file = key and Pad.IconFile(key, Pad.IconPx(units, effScale or MapScale()))
  if not file then return nil end
  return "|T" .. file .. ":" .. units .. ":" .. units .. "|t"
end
-- a binding's parts, the modifiers first: "PADLTRIGGER+PAD1" -> { "PADLTRIGGER", "PAD1" }; a game binding's
-- modifiers as the pad's buttons set as them ("SHIFT-PADBACK" -> { "PADLTRIGGER", "PADBACK" }), else "SHIFT"
function Pad.BindParts(bind)
  local gm, gk = Pad.GameSplit(bind)
  if #gm > 0 then
    local by = {}
    for key, mod in pairs(Pad.GameMods()) do by[mod] = key end
    local parts = {}
    for _, mod in ipairs(gm) do parts[#parts + 1] = by[mod] or mod end
    parts[#parts + 1] = gk
    return parts
  end
  local m, k = Pad.Split(bind)
  if not k then return {} end
  return m and { m, k } or { k }
end
local MOD_NAMES = { SHIFT = "Shift", CTRL = "Ctrl", ALT = "Alt" }
local function PartText(p) return MOD_NAMES[p] and L[MOD_NAMES[p]] or Pad.KeyLabel(p) end
-- a binding as icons ("[LT]+[A]"), each part without one as its text (Pad.BindLabel's)
function Pad.IconLabel(bind, units, effScale)
  local parts = Pad.BindParts(bind)
  if #parts == 0 then return L["Not bound"] end
  for i, p in ipairs(parts) do parts[i] = Pad.KeyIcon(p, units, effScale) or PartText(p) end
  return table.concat(parts, "+")
end
-- a control's binding as icons, "(hold)" after a held one
function Pad.ActionIcon(id)
  local t = Pad.IconLabel(Pad.Key(id))
  if Pad.IsHold(id) then t = t .. " " .. L["(hold)"] end
  return t
end

-- Hints (asked 2026-11-16: "use the assigned button icon and overlay fade it where that control would "click" and it
-- fades in and out in 1sec every 3sec. So controller opens map, currently "Y" button icon would fade over the map menu
-- button ... When over other menu item it'd fade the A button"): while the controller's marks show (in use, the map
-- open, out of combat), a control's button icons (a pair's both, "(hold)" after a held one) pulse over what it acts
-- on: the map menu's button (menu), the menu's button in focus (select), a question's Yes and No (yes, back), the stop
-- under the crosshair (remove) and the icon under it (select). Each fades in and out over HINT_FADE seconds, once every
-- HINT_PERIOD; clear the rest of the time. Frames of our own on our own buttons, never the game's.
Pad.HINT_PERIOD, Pad.HINT_FADE, Pad.HINT_UNITS = 3, 1, 20
Pad.HINT_LOOK = 0.1 -- (what's under the crosshair looked at this often, seconds)
Pad.hints, Pad.hintT = {}, 0
-- A button with two controls (the Quest Route button: A presses it, X its right-click, the menu of other ways; asked
-- 2026-11-22 for 1.3.14, "just fade between the 2 buttons for activating and opening the submenu"): its two hints over
-- it in turn, each shown SWAP_SECONDS, cross-fading over SWAP_FADE at each change; steady, not the pulse.
Pad.SWAP_SECONDS, Pad.SWAP_FADE = 1, 0.4
-- hint `which` (1, 2) of a pair's alpha `t` seconds in: the first from 0 to SWAP_SECONDS, the second the next as long
function Pad.SwapAlpha(t, which)
  local S, F = Pad.SWAP_SECONDS, Pad.SWAP_FADE
  local p = (t or 0) % (2 * S)
  local function ramp(x) return math.min(1, math.max(0, (x + F / 2) / F)) end -- (x: seconds past a change)
  local first
  if p < S / 2 then
    first = ramp(p)
  elseif p < S * 3 / 2 then
    first = 1 - ramp(p - S)
  else
    first = ramp(p - 2 * S)
  end
  return which == 2 and 1 - first or first
end
-- the hints' alpha `t` seconds into the pulse: up and back down in the first HINT_FADE of each HINT_PERIOD
function Pad.HintAlpha(t)
  local p = (t or 0) % Pad.HINT_PERIOD
  if p >= Pad.HINT_FADE then return 0 end
  local half = Pad.HINT_FADE / 2
  return p < half and p / half or (Pad.HINT_FADE - p) / half
end
-- a control's hint: its binding's icons only (a held one's too: asked 2026-11-16, "with hold its off don't show
-- (hold) here"; the text pushed the icon off what it acts on)
function Pad.HintText(id)
  return Pad.IconLabel(Pad.Key(id), Pad.HINT_UNITS)
end
-- { { frame, control id }, ... } as things are now
function Pad.HintTargets()
  local out = {}
  if not (Pad.bound and Pad.marksOn) or (InCombatLockdown and InCombatLockdown()) then return out end
  local function add(b, id, swap)
    if b and b.IsShown and b:IsShown() and Pad.Key(id) then out[#out + 1] = { b, id, swap } end
  end
  local q = Pad.Question()
  if q then
    add(q.yes, "yes")
    add(q.no, "back")
    return out
  end
  local g = G()
  -- (the Quest Route button's menu of other ways open, QuestWays.lua: A's over the highlighted entry, Back's over the
  -- button it goes back to)
  if g and g.QuestWaysOpen and g.QuestWaysOpen() then
    add(g.QuestWaysSelRow(), "select")
    add(g.questWays.owner, "back")
    return out
  end
  add(g and g.mapButton, "menu")
  -- (routing paused: Pause/Unpause's button over the glowing Resume Routing buttons, the quick bar's and the minimap
  -- square's while it's kept beside the map; asked 2026-11-18 for 1.3.9, "when map is open and controller in use and
  -- pause is active the button needed to unpause the route fades like the others")
  if g and ns.Nav and ns.Nav.paused then
    add(g.PauseButton and g.PauseButton(), "pause")
    add(g.mmResume, "pause")
  end
  if Pad.MenuOpen() then
    local f = Pad.focus
    if f and f.agpsRightClick and Pad.Key("remove") then
      -- (a button with a right-click of its own: Set Stop's and Remove's in turn, Pad.SwapAlpha)
      add(f, "select", 1)
      add(f, "remove", 2)
    else
      add(f, "select")
    end
    -- (a group or Quick Find open: Back's icon over the button that opened it, where Back goes; asked 2026-11-16, "we
    -- should fade the button to go back when in a map menu sub menu")
    add(Pad.MenuParent(), "back")
  elseif g and g.removeAsk and g.removeAsk:IsShown() then
    -- (a stop's Remove? up: the confirm's icon over it, not X over the stop; asked 2026-11-16, "when Remove? is up, we
    -- should fade the select icon instead to signify a confirm")
    add(g.removeAsk, Pad.Key("yes") and "yes" or "select")
  else
    add(Pad.StopAt(), "remove")
    add(Pad.IconAt(), "select")
    -- (the map's bottom button by what it does now, one icon (asked 2026-11-16, "stop not set should only be the set
    -- stop button, if 1 or more stops are marked then its LB only"): stops marked, Confirm Route, Select's; none yet,
    -- Set Stop's, the way to mark one; a route up, Clear Route, its own buttons)
    if g and g.PendingStop and g.PendingStop(1) then
      add(g.confirmRouteBtn, "click")
    elseif g and #ns.Nav.stops > 0 then
      add(g.confirmRouteBtn, "clear")
    elseif g then
      add(g.confirmRouteBtn, "select")
    end
  end
  return out
end
-- a hint's target a wide button (a red one, its text across it), not a round icon
function Pad.HintWide(b)
  local w, h = b.GetWidth and b:GetWidth() or 0, b.GetHeight and b:GetHeight() or 0
  return (h > 0 and w >= h * 2.5) and true or false
end
local function HintFrame(i)
  local h = Pad.hints[i]
  if h then return h end
  h = CreateFrame("Frame", nil, Pad.driver or rawget(_G, "AzerothGPSFrame"))
  h:SetSize(Pad.HINT_UNITS, Pad.HINT_UNITS)
  h.text = h:CreateFontString(nil, "OVERLAY", "GameFontHighlight")
  h.text:SetPoint("CENTER")
  h:Hide()
  Pad.hints[i] = h
  return h
end
-- every frame: the hints placed (each HINT_LOOK) and faded
Pad.hintLook = 0
function Pad.HintTick(dt)
  Pad.hintLook = Pad.hintLook - (dt or 0)
  local was = Pad.hintTargets
  if Pad.hintLook <= 0 or not was then
    Pad.hintLook = Pad.HINT_LOOK
    Pad.hintTargets = Pad.HintTargets()
  end
  local list = Pad.hintTargets
  if #list == 0 then
    Pad.hintT = 0
  else
    Pad.hintT = Pad.hintT + (dt or 0)
  end
  local a = Pad.HintAlpha(Pad.hintT)
  local along = {} -- (a wide button with more than one: each after the one before, `along[b]` units out)
  for i, e in ipairs(list) do
    local h = HintFrame(i)
    local b, id = e[1], e[2]
    -- (a wide button, the game's red ones: Confirm Route, a question's Yes and No, Remove?: its icon at its right end,
    -- steady, not over its text and not faded; asked 2026-11-16, "Anytime there is a red button being used on the
    -- map, including zone too high level popups lets move the button to press to this pink area and not fade")
    local wide = Pad.HintWide(b) and not e[3]
    local out = wide and (along[b] or 0) or 0
    if h.target ~= b or h.wide ~= wide or h.out ~= out then
      h.out = out
      h:SetParent(b)
      h:ClearAllPoints()
      -- (a wide button: from just inside its right end outward, so a pair's two icons (LB + A) both show past its text;
      -- asked 2026-11-16, "Allow for button + button to show for the red buttons as well")
      h.text:ClearAllPoints()
      if wide then
        h:SetPoint("LEFT", b, "RIGHT", -Pad.HINT_UNITS / 2 + out, 0)
        h.text:SetPoint("LEFT", h, "LEFT", 0, 0)
      else
        h:SetPoint("CENTER", b, "CENTER")
        h.text:SetPoint("CENTER")
      end
      h.target, h.wide = b, wide
    end
    h:SetFrameLevel((b:GetFrameLevel() or 1) + 8)
    local text = Pad.HintText(id)
    if h.id ~= id or h.shown ~= text then
      h.text:SetText(text)
      h.id, h.shown = id, text
    end
    if wide then along[b] = out + (h.text:GetStringWidth() or Pad.HINT_UNITS) + 4 end
    local ha = wide and 1 or (e[3] and Pad.SwapAlpha(Pad.hintT, e[3])) or a
    h:SetAlpha(ha)
    h.alpha = ha
    h:Show()
  end
  for i = #list + 1, #Pad.hints do
    local h = Pad.hints[i]
    h:Hide()
    h.target, h.id = nil, nil
  end
end

-- Options > Controller's diagram (asked 2026-11-16: "convert the Controller option page to look something like this ...
-- transparent background with gold controller drawn lines"): the controller in gold lines (padicons.py's diagram,
-- Media\Pad\Diagram_<s * 10>.tga at `scales` pixels a unit, `w` x `h` units), each button's leader line out to the
-- left or right edge at its row (`row0` + (i - 1) * `step` units from its top), the button's controls labeled there.
Pad.DIAGRAM = { w = 200, h = 186, row0 = 14, step = 22, scales = { 1, 1.5, 2, 2.5, 3 },
  left = { "PADLTRIGGER", "PADLSHOULDER", "PADBACK", "PADLSTICK", "PADDUP", "PADDLEFT", "PADDDOWN", "PADDRIGHT" },
  right = { "PADRTRIGGER", "PADRSHOULDER", "PADFORWARD", "PAD4", "PAD2", "PAD1", "PAD3", "PADRSTICK" } }
-- the controls' short names there (the map box's)
-- (Select, as Options lists it: asked 2026-11-16, "the controller still says Set Stop not Select")
Pad.SHORT = { select = L["Set Stop"], yes = L["Yes"], remove = L["Remove"], back = L["Back"], clear = L["Clear Route"],
  zoomIn = L["Zoom in"], zoomOut = L["Zoom out"], panUp = L["Pan up"], panDown = L["Pan down"], panLeft = L["Pan left"],
  panRight = L["Pan right"], recenter = L["Recenter"], toggle = L["Show/Hide GPS"], menu = L["Map Menu"],
  options = L["Options"], questRoute = L["Quest Route"], pause = L["Pause/Unpause"], click = L["Select"], viewControls = L["View Controls"] }
-- What `key` does on the map now: its label (its icon, then each control on it: "Set Stop", "Clear Route (hold)", a
-- pair's "[LT]+ Zoom in") and the tooltip's lines (each in full: "LT + A: Clear Route"), or nil when it does nothing.
-- Options > Controller's label for pad button `key`: its controls pressed, then " : " and the held ones, each after a
-- yellow "(H)" (asked 2026-11-16: "(A [the icon]) Set Stop : (H) Remove Stop. The (H) in yellow to show its the hold
-- alternative"); the button's own icon isn't in it (Options draws it beside, pixel for pixel), a pair's other button
-- is. Returns the text, the tooltip's lines and the controls' ids (pressed first), or nil for a button with none.
Pad.HOLD_MARK = "|cffffd100(H)|r"
-- (a pair as "+LB Pause Routing", the other button first with a +: asked 2026-11-16, "not LB + Pause Routing that
-- doesn't make sense"; one line, "don't like the 2 line per button revert that"; its icon the same picture as the
-- button's own, "be consistent on the buttons")
Pad.PAIR_ICON_TIMES = 1
function Pad.DiagramLabel(key, units, effScale)
  local parts, held, tip, ids, heldIds = {}, {}, {}, {}, {}
  local sel = Pad.Key("select")
  for _, a in ipairs(Pad.ACTIONS) do
    local id = a[1]
    local bind = Pad.Key(id)
    local p = bind and Pad.BindParts(bind)
    -- (Yes on the stop's button the same way: one entry, as in the box)
    local same = id == "yes" and bind == sel and Pad.IsHold("yes") == Pad.IsHold("select")
    if p and p[#p] == key and not same then
      local t = Pad.SHORT[id] or a[3]
      -- (Show/Hide GPS with the game's controller UI on, where it can't run: red, its button's window says why;
      -- asked 2026-11-16)
      if id == "toggle" and Pad.ToggleBlocked() then t = "|cffff4040" .. t .. "|r" end
      local pair = #p > 1
      if pair then
        local mods = {}
        -- (a pair's other button as big as the label's own icon looks: asked 2026-11-16, "don't like the smaller
        -- buttons here just use the size" of the button's own; in a line of text it shows smaller at the same size)
        local big = units and math.floor(units * Pad.PAIR_ICON_TIMES + 0.5) or nil
        for i = 1, #p - 1 do mods[i] = "+" .. (Pad.KeyIcon(p[i], big, effScale) or PartText(p[i])) end
        t = table.concat(mods, " ") .. " " .. t
      end
      if Pad.IsHold(id) then
        t = Pad.HOLD_MARK .. " " .. t
        held[#held + 1] = t
        heldIds[#heldIds + 1] = id
      else
        parts[#parts + 1] = t
        ids[#ids + 1] = id
      end
      tip[#tip + 1] = Pad.ActionLabel(id) .. ": " .. a[3]
    end
  end
  if #parts + #held == 0 then return nil, nil, nil end
  for _, id in ipairs(heldIds) do ids[#ids + 1] = id end
  local text = table.concat(parts, ", ")
  if #held > 0 then text = (text ~= "" and text .. " : " or "") .. table.concat(held, ", ") end
  return text, tip, ids
end
-- a control's name, short (Options' lists: Select for the stop and Yes)
function Pad.ShortName(id)
  if id == "yes" or id == "select" then return L["Set Stop"] end
  local a = Pad.Action(id)
  return a and a[3] or tostring(id)
end
function Pad.Labels()
  return { A = Pad.ActionLabel("select"), B = Pad.ActionLabel("back"), X = Pad.ActionLabel("remove") }
end
-- the pan controls' buttons: the D-pad (its picture with `icons`), or each one's
function Pad.PanLabel(icons)
  local K = icons and Pad.ActionIcon or Pad.ActionLabel
  if Pad.Key("panUp") == "PADDUP" and Pad.Key("panDown") == "PADDDOWN" and Pad.Key("panLeft") == "PADDLEFT"
      and Pad.Key("panRight") == "PADDRIGHT" then
    return icons and Pad.KeyIcon("DPAD") or L["D-pad"]
  end
  return table.concat({ K("panUp"), K("panDown"), K("panLeft"), K("panRight") }, "/")
end
-- Drawing an area on the map now (GPSFrame's G.StartDrawing: the farming area), the pad's buttons its (Pad.DrawRun).
function Pad.Drawing()
  local g = G()
  return (g and g.drawMode and not (g.Held and g.Held())) and true or false
end
-- the legend on the map: the buttons as bound now (the map menu open: its own; drawing: the drawing's); `icons`: as
-- their pictures
function Pad.LegendText(icons)
  local K = icons and Pad.ActionIcon or Pad.ActionLabel
  local dpad = icons and Pad.KeyIcon("DPAD") or L["D-pad"]
  if Pad.MenuOpen() then
    return string.format(L["%s: Press   %s: Back   %s: Move   %s: Close Menu"], K("select"), K("back"),
      Pad.Key("panUp") == "PADDUP" and dpad or (K("panUp") .. "/" .. K("panDown")), K("menu"))
  end
  if Pad.Drawing() then
    return (ns.Format or string.format)(L["%s: Add Corner   %s: Undo Corner   %s: Finish Area   %s: Cancel   %s: Zoom   %s: Pan"],
      K("select"), K("remove"), K("menu"), K("back"), K("zoomOut") .. "/" .. K("zoomIn"), Pad.PanLabel(icons))
  end
  return string.format(L["%s: Set Stop   %s: Remove   %s: Back   %s: Zoom   %s: Pan   %s: Recenter"],
    K("select"), K("remove"), K("back"), K("zoomOut") .. "/" .. K("zoomIn"), Pad.PanLabel(icons), K("recenter"))
end

-- What's under the reticle: the nearest icon (a map point a double-click routes to) and the nearest stop's pin, each
-- within NEAR_UI of the map's middle, or nil.
local function Near(list, pos)
  local g = G()
  local vx, vy, _, s = g.PadView()
  if not vx or not s then return nil end
  local best, bd
  for _, b in pairs(list or {}) do
    if b and b.IsShown and b:IsShown() then
      local x, y = pos(b)
      if x then
        local d = math.sqrt((x - vx) ^ 2 + (y - vy) ^ 2) * s
        if d <= Pad.NEAR_UI and (not bd or d < bd) then best, bd = b, d end
      end
    end
  end
  return best
end
function Pad.IconAt()
  local g = G()
  local mine = Near(g.poiButtons, function(b)
    if b.cityMap or b.exit or not b.wx then return nil end
    return b.wx, b.wy
  end)
  if mine then return mine end
  -- (other addons' icons copied onto the map, OtherPins.lua: routed to as their double-click does; asked 2026-11-16,
  -- "if crosshairs are over an icon and route is selected, consider that the same as double click to route to it")
  local OP = ns.OtherPins
  return OP and Near(OP.copies, function(b)
    if not b.wx or (b.cont and b.cont ~= (select(3, g.PadView()))) then return nil end
    return b.wx, b.wy
  end) or nil
end
-- Select at the crosshair: a route's Confirm Route first, while it shows (asked 2026-11-16: "After a route is set, allow
-- the Select button to be used to Confirm Route"); else the icon under it clicked as the mouse would (a dungeon's entrance: its map), else the
-- map itself there (a cave with a map: that map, G.CaveClick). True when something took it.
function Pad.ClickAt()
  local g = G()
  -- (stops waiting: confirmed, as the map's Confirm Route; never that button's other job, Clear Route with a route, which
  -- cleared it and went back to the player: asked 2026-11-16, "clear route still jumped back to player position")
  if g.PendingStop and g.PendingStop(1) and g.ConfirmRoute then
    g.ConfirmRoute()
    return true
  end
  g.padClickAt = GetTime and GetTime() or 0 -- (a double-click meanwhile: not a stop, G.PadClickedJustNow)
  local b = Near(g.poiButtons, function(x) return x.wx, x.wy end)
  if b then
    for _, sc in ipairs({ "OnClick", "OnMouseUp" }) do
      local fn = b.GetScript and b:GetScript(sc)
      if fn then
        pcall(fn, b, "LeftButton", false)
        return true
      end
    end
  end
  return g.CaveClick and g.CaveClick(0, 0) or false
end
-- View Controls: the controller drawn with its controls (Options' diagram, O.MakePadDiagram) over the map's middle on
-- the box's dark tint, SHOW_SECONDS then faded out over FADE_SECONDS; again: from the start.
Pad.CONTROLS_SHOW, Pad.CONTROLS_FADE = 10, 5
Pad.CONTROLS_W, Pad.CONTROLS_H = 480, 320 -- (the size marked on a screenshot, 2026-11-16)
-- (smaller, at the map's left middle: asked 2026-11-16, "its dead center needs to be moved the left center and reduce size
-- by 60%": 60% of its size, so its labels stay readable)
Pad.CONTROLS_SCALE, Pad.CONTROLS_INSET = 1, 10 -- (0.6 was too small, asked 2026-11-16)
-- (smaller with a smaller map window, asked 2026-11-16: at most this part of the map's width and height)
Pad.CONTROLS_MAX_W, Pad.CONTROLS_MAX_H = 0.45, 0.6
function Pad.ControlsScale(map)
  local w, h = map and map:GetWidth() or 0, map and map:GetHeight() or 0
  if w <= 0 or h <= 0 then return Pad.CONTROLS_SCALE end
  return math.min(Pad.CONTROLS_SCALE, w * Pad.CONTROLS_MAX_W / Pad.CONTROLS_W, h * Pad.CONTROLS_MAX_H / Pad.CONTROLS_H)
end
-- the map back in the minimap square (View Controls: on the opened map only, asked 2026-11-16); or Options or another
-- window of ours open, which it would sit over (at TOOLTIP: asked 2026-11-16, "shouldn't show on top on the options
-- page")
function Pad.MapInSquare()
  local g = G()
  if g and g.MinimapMode and g.MinimapMode() then return true end
  for f in pairs(ns.popups or {}) do
    if f.IsShown and f:IsShown() then return true end
  end
  return false
end
function Pad.ShowControls()
  local O = ns.Options
  local parent = rawget(_G, "AzerothGPSFrame")
  if not (parent and O and O.MakePadDiagram and Pad.DIAGRAM) or Pad.MapInSquare() then return false end
  local ov = Pad.controls
  if not ov then
    -- (on the screen, not the map: the zoomed-in land's own frames drew over it inside the map's; kept to the map's
    -- left middle, gone with the map)
    ov = CreateFrame("Frame", nil, UIParent)
    ov.bg = ov:CreateTexture(nil, "BACKGROUND")
    ov.bg:SetAllPoints()
    ov.bg:SetColorTexture(0, 0, 0, Pad.BOX_TINT) -- (the map's controls box's own)
    ov.diag = O.MakePadDiagram(ov, Pad.CONTROLS_W - 16, Pad.CONTROLS_H - 16, false)
    ov.diag:SetPoint("CENTER")
    ov:EnableMouse(false)
    ov:SetScript("OnUpdate", function(self, dt)
      self.t = (self.t or 0) + (dt or 0)
      local map = rawget(_G, "AzerothGPSFrame")
      if not (map and map:IsVisible()) or Pad.MapInSquare() or self.t >= Pad.CONTROLS_SHOW + Pad.CONTROLS_FADE then
        self:Hide()
        return
      end
      self:SetAlpha(self.t <= Pad.CONTROLS_SHOW and 1 or 1 - (self.t - Pad.CONTROLS_SHOW) / Pad.CONTROLS_FADE)
    end)
    Pad.controls = ov
  end
  local k = Pad.ControlsScale(parent)
  ov:SetScale(k)
  ov:SetSize(Pad.CONTROLS_W, Pad.CONTROLS_H)
  ov:ClearAllPoints()
  ov:SetPoint("LEFT", parent, "LEFT", Pad.CONTROLS_INSET / k, 0)
  -- (over everything of the map's, the land zoomed in too: asked 2026-11-16, "zoomed in on terrain it didn't show")
  ov:SetFrameStrata("TOOLTIP")
  ov:SetFrameLevel(50)
  if ov.Raise then ov:Raise() end
  ov.t = 0
  ov:SetAlpha(1)
  ov:Show()
  O.LayoutPadDiagram(ov.diag)
  return true
end
function Pad.StopAt()
  local g = G()
  return Near(g.stopPins, function(b)
    local d = (b.stopIndex and ns.Nav.stops[b.stopIndex]) or (b.pendingIndex and g.PendingStop(b.pendingIndex))
    if not d then return nil end
    return d.x, d.y
  end)
end

-- A question up (AzerothGPS's own popups: ns.Ask, G.Confirm).
function Pad.Question()
  local f = ns.lastAsk
  if f and f.IsShown and f:IsShown() then return f end
  return nil
end
local function Click(b)
  local on = b and b.GetScript and b:GetScript("OnClick")
  if on then on(b, "LeftButton") return true end
  return false
end

-- A key pressed (down) or let go (up): its actions (Pad.KeyActions), a pair's when its modifier is held, else its own.
-- With a held control among them: those wait (Pad.holds, HOLD_SECONDS), the others are done as it's let go sooner.
Pad.pressed, Pad.chordUsed, Pad.holds = {}, {}, {}
function Pad.PressKey(key, down)
  if Pad.Capturing() then return true end -- (Change waiting for a button: the press is its, read from the pad)
  local entries = Pad.KeyActions()[key]
  if not entries then return false end
  if not down then
    local acts = Pad.pressed[key]
    Pad.pressed[key] = nil
    Pad.chordUsed[key] = nil -- (a modifier let go: its own hold may start again)
    local h = Pad.holds[key]
    if h then
      Pad.holds[key] = nil
      if not h.fired and #h.tap > 0 then
        Pad.Run(h.tap, true) -- (let go before the hold: its other control)
        return Pad.Run(h.tap, false)
      end
      return true
    end
    if not acts then
      acts = {}
      for _, e in ipairs(entries) do
        if not e.mod and not e.hold then acts[#acts + 1] = e.id end
      end
    end
    return Pad.Run(acts, false)
  end
  local downs = Pad.KeysDown()
  local chord, plain = {}, {}
  for _, e in ipairs(entries) do
    if e.mod then
      if e.mod ~= key and downs[e.mod] then
        chord[#chord + 1] = e
        Pad.chordUsed[e.mod] = true
      end
    else
      plain[#plain + 1] = e
    end
  end
  local group = #chord > 0 and chord or plain
  local tap, hold, now = {}, {}, {}
  for _, e in ipairs(group) do
    if e.hold then hold[#hold + 1] = e.id
    elseif Pad.HELD[e.id] then now[#now + 1] = e.id -- (done while held: at once, as ever)
    else tap[#tap + 1] = e.id end
  end
  if #hold == 0 then
    local acts = {}
    for _, e in ipairs(group) do acts[#acts + 1] = e.id end
    Pad.pressed[key] = acts
    return Pad.Run(acts, true)
  end
  Pad.pressed[key] = now
  if #now > 0 then Pad.Run(now, true) end
  Pad.holds[key] = { at = GetTime and GetTime() or 0, tap = tap, hold = hold }
  Pad.WatchHolds()
  return true
end
-- the held buttons watched (an OnUpdate of ours, only while one is down): a held control done at HOLD_SECONDS, once;
-- one let go without its "up" reaching us (the pad's state, C_GamePad) taken as let go
local holdWatch
function Pad.WatchHolds()
  if not holdWatch then
    holdWatch = CreateFrame("Frame", nil, UIParent)
    holdWatch:SetScript("OnUpdate", function() Pad.HoldTick() end)
    Pad.holdWatch = holdWatch
  end
  holdWatch:SetShown(next(Pad.holds) ~= nil)
end
function Pad.HoldTick()
  local now = GetTime and GetTime() or 0
  local downs
  for key, h in pairs(Pad.holds) do
    if not h.fired then
      downs = downs or Pad.KeysDown()
      if next(downs) ~= nil and not downs[key] then
        Pad.PressKey(key, false)
      elseif now - h.at >= Pad.HOLD_SECONDS then
        h.fired = true
        Pad.Run(h.hold, true)
      end
    end
  end
  Pad.WatchHolds()
end
-- (the MVP's names: "A", "B", "X", ...; Pad.LEGACY)
function Pad.Press(name, down)
  local acts = Pad.LEGACY[name]
  if not acts then return false end
  return Pad.Run(acts, down)
end
function Pad.Run(acts, down)
  local has = {}
  for _, id in ipairs(acts) do has[id] = true end
  -- (drawing an area: its corners, Pad.DrawRun; the pan and zoom as ever, to move the reticle)
  if down and Pad.Drawing() and not Pad.MenuOpen() then
    local r = Pad.DrawRun(has)
    if r ~= nil then return r end
  end
  -- (searching with the controller: the search's own controls first, its keyboard's too, PadKeys.lua; over the map
  -- menu's, which stays open behind a search opened from it. Kooki3z 2026-11-20: "A fading on highlighted letter,
  -- D-Pad also closes keyboard and navigates the list")
  -- (the Quest Route button's menu of other ways open: its own controls, QuestWays.lua's G.QuestWaysPad)
  local g0 = G()
  if down and g0 and g0.QuestWaysPad then
    local r = g0.QuestWaysPad(has)
    if r ~= nil then return r end
  end
  local PK = ns.PadKeys
  local searching = PK and PK.Wants()
  if searching then
    local r = PK.Run(has, down)
    if r ~= nil then return r end
  end
  -- (the map menu open, or opened: its own controls, Pad.MenuRun)
  if (Pad.MenuOpen() and not searching) or (has.menu and down) then return Pad.MenuRun(has, down) end
  local held = false
  for _, id in ipairs(acts) do
    if Pad.HELD[id] then
      Pad.held[id] = down and (GetTime and GetTime() or 0) or nil
      held = true
    end
  end
  if held or not down then return nil end
  local g = G()
  if not g then return end
  if has.yes then
    local q = Pad.Question()
    if q then return Click(q.yes) end
    -- (a stop's "Remove?" is a yes too, wherever the crosshair is; asked 2026-11-16: "if player removes a stop and
    -- doesn't move crosshair to the remove? button but presses the "Yes on a question" key consider that still a yes")
    if g.removeAsk and g.removeAsk:IsShown() then return Click(g.removeAsk) end
  end
  if has.select then
    if g.removeAsk and g.removeAsk:IsShown() then return Click(g.removeAsk) end
    -- (searching: the row highlighted with the D-pad, as Enter; Kooki3z 2026-11-20)
    if g.SearchOpen and g.SearchOpen() then
      g.SearchPick()
      return true
    end
    local icon = Pad.IconAt()
    if icon then
      local dbl = icon:GetScript("OnDoubleClick")
      if dbl then dbl(icon, "LeftButton") end
      return true
    end
    g.AddPending(0, 0) -- (the map's middle: as a double-click there)
    return true
  end
  if has.back then
    local q = Pad.Question()
    if q then return Click(q.no) end
    if g.removeAsk and g.removeAsk:IsShown() then g.removeAsk:Hide() return true end
    local menu = (g.mapMenu and g.mapMenu:IsShown()) or (g.searchPanel and g.searchPanel:IsShown())
    if menu then g.CloseMapMenus() return true end
    if g.quickFindOpen and g.SetQuickFindOpen then g.SetQuickFindOpen(false) return true end
    if g.CloseOpenGroup and g.CloseOpenGroup() then return true end
    -- (a dungeon's, cave's or city's map opened: out of it first, as a right-click; the map closed by the next Back)
    if g.LeaveOpenedView and g.LeaveOpenedView() then
      if g.Redraw then g.Redraw() end
      return true
    end
    if AzerothGPS_ToggleMap then AzerothGPS_ToggleMap() end -- (the map: closed, or back into the minimap square)
    Pad.Apply()
    return true
  end
  if has.remove then
    local pin = Pad.StopAt()
    if pin then g.AskRemove(pin) return true end
    return false
  end
  if has.clear then
    return g.ClearRoute and g.ClearRoute() or false -- (as the map's Clear Route: the view left where it is)
  end
  if has.questRoute then -- (as the map menu's Quest Route)
    if g.QuestRoute then g.QuestRoute() end
    return true
  end
  if has.click then return Pad.ClickAt() end
  if has.viewControls then return Pad.ShowControls() end
  if has.pause then -- (as the map menu's Pause / Resume Routing: a route only)
    if not ns.Nav.dest then return false end
    ns.Nav.TogglePaused()
    if g.Redraw then g.Redraw() end
    return true
  end
  if has.options then
    if g.OpenOptions then g.OpenOptions() end
    Pad.Apply() -- (Options' own buttons now)
    return true
  end
  if has.recenter then
    g.Follow()
    if g.Redraw then g.Redraw() end
    return true
  end
  return false
end

-- Drawing an area with the pad (asked 2026-11-16: "add controller support for drawing areas too like for drawing
-- farming area"): a question's Yes and No first; then A a corner at the reticle (on the first one again: done), X the
-- last one off, Y (the map menu's button) done, B cancels the drawing. nil: not the drawing's (pan, zoom, ...).
function Pad.DrawRun(has)
  local g = G()
  local q = Pad.Question()
  if q and has.yes then return Click(q.yes) end
  if q and has.back then return Click(q.no) end
  if has.select then return g.PadDrawCorner() end
  if has.remove then return g.PadDrawUndo() end
  if has.menu then return g.PadDrawFinish() end
  if has.back then
    g.StopDrawing()
    return true
  end
  return nil
end

-- Each frame while bound: the held D-pad and triggers. A held action whose button is a pair's modifier waits
-- MOD_HOLD_DELAY, and none while a pair used it. The map menu open: none of them.
function Pad.HeldNow(id)
  local t = Pad.held[id]
  -- (a button the game's Gamepad settings make a Shift, Ctrl or Alt (LT as Shift, its usual): the game takes it as that
  -- and no binding of ours on it is pressed or held, so it's read from the pad itself; asked 2026-11-16, "When not in
  -- controller UI, LT zoom out doesn't work when holding but zooming in does")
  if not t and Pad.HELD[id] then
    local key = Pad.Key(id)
    if key and not Pad.Split(key) and Pad.GameMods()[key] and Pad.KeysDown()[key] then
      Pad.SawInput(true)
      return true
    end
  end
  if not t then return false end
  local _, k = Pad.Split(Pad.Key(id))
  if k and Pad.ChordMods()[k] then
    if Pad.chordUsed[k] then return false end
    local now = GetTime and GetTime() or 0
    if now - (tonumber(t) or now) < Pad.MOD_HOLD_DELAY then return false end
  end
  return true
end
-- The icon or stop under the crosshair: its tooltip, as the mouse over it shows (asked 2026-11-16: "crosshair on an icon
-- should show its tool tip when using a controller"). Looked at every HOVER_EVERY; the controller in use only.
Pad.HOVER_EVERY = 0.1
function Pad.HoverTick(dt)
  Pad.hoverWait = (Pad.hoverWait or 0) - (dt or 0)
  if Pad.hoverWait > 0 then return end
  Pad.hoverWait = Pad.HOVER_EVERY
  local want = Pad.bound and Pad.used and not Pad.MenuOpen() and (Pad.StopAt() or Pad.IconAt()) or nil
  Pad.SetHovered(want)
end
function Pad.SetHovered(b)
  local old = Pad.hovered
  if b == old then return end
  Pad.hovered = b
  if old then
    local leave = old.GetScript and old:GetScript("OnLeave")
    if leave then pcall(leave, old) end
  end
  if b then
    local enter = b.GetScript and b:GetScript("OnEnter")
    if enter then pcall(enter, b) end
  end
end
Pad.SEARCH_REPEAT_FIRST, Pad.SEARCH_REPEAT = 0.35, 0.1 -- (seconds: held, the search's next row after these)
-- The player moving their character (the game's own movement, the left stick or the keys; never the D-pad panning the
-- map, which moves only the view): the controller's map menu and the search, its keyboard with it, closed as they start
-- (Kooki3z 2026-11-20: "it moves the character, which btw would and should close map menu"). The controller in use
-- only: a mouse player's menu keeps its own timer.
function Pad.MoveTick()
  local g = G()
  local moving = g.PlayerMoving and g.PlayerMoving() or false
  local started = moving and not Pad.wasMoving
  Pad.wasMoving = moving
  if not (started and Pad.used) then return false end
  local closed = false
  if Pad.MenuOpen() then
    Pad.CloseMenu()
    closed = true
  end
  if g.searchPanel and g.searchPanel:IsShown() then
    g.searchPanel:Hide()
    closed = true
  end
  return closed
end
function Pad.Tick(dt)
  if not Pad.bound or not dt or dt <= 0 then return end
  local g = G()
  Pad.HoverTick(dt)
  Pad.MoveTick()
  local PK = ns.PadKeys
  if PK then PK.Refresh() end -- (the search's legend and keyboard: shown while the controller has the search)
  local searching = PK and (PK.Wants() or (g.SearchOpen and g.SearchOpen())) or false
  if searching and Pad.focus then Pad.SetFocus(nil) end -- (the map menu's ring: the search's turn)
  if Pad.MenuOpen() and not searching then
    if g.mapMenu then g.mapMenu.idle = 0 end
    if Pad.focus and not Pad.focus:IsShown() then Pad.SetFocus(nil) end
    -- (the drawer slid out: its first button; not with the mouse in use, asked 2026-11-16: "if the player starts using
    -- the mouse again stop the map menu highlighting for a selection, its fighting the mouse selection and shows
    -- tooltips")
    if not Pad.focus and Pad.used then Pad.Move(0) end
    return
  end
  local H = Pad.HeldNow
  local dx = ((H("panRight") and 1 or 0) - (H("panLeft") and 1 or 0))
  local dy = ((H("panUp") and 1 or 0) - (H("panDown") and 1 or 0))
  -- (searching: up and down step through the results as the arrow keys do, a step a press and then repeating while
  -- held; the map isn't panned up or down meanwhile. Kooki3z 2026-11-20: "When search is active and controller is on,
  -- support D-pad for selecting line like arrow keys do". The keyboard open: all four move on its keys, PadKeys.Tick)
  if searching then
    if not PK.Tick(dt, dx, dy) then dx = 0 end
    dy = 0
  else
    Pad.searchDir = nil
  end
  local zIn, zOut = H("zoomIn"), H("zoomOut")
  if dx ~= 0 or dy ~= 0 then g.PadPan(dx * Pad.PAN_UI * dt, dy * Pad.PAN_UI * dt) end
  if zOut and not zIn then g.WheelZoom(Pad.ZOOM_TIMES ^ dt) end -- (out: more yards in view)
  if zIn and not zOut then g.WheelZoom(Pad.ZOOM_TIMES ^ -dt) end
  if (dx ~= 0 or dy ~= 0 or zIn or zOut) and g.Redraw then g.Redraw() end
end

-- The map menu with the pad (asked 2026-11-16): its button ("menu", Y) opens and closes it; open, the pan controls move
-- a focus ring of ours over its buttons in their order (the column going up, then the row going right; up and right
-- the next, down and left the one before), the stop's button presses the one in focus (a group's opens its buttons,
-- the focus on its first), Back shuts an open group or Quick Find first, then the menu. Its tooltip shows as on hover.
-- Nothing of Blizzard's gamepad focus: a ring of our own.
function Pad.MenuOpen()
  local g = G()
  return (g and g.mapMenu and g.mapMenu:IsShown() and Pad.bound) and true or false
end
function Pad.MenuButtons()
  local g = G()
  local out = {}
  local function add(b)
    if b and b.IsShown and b:IsShown() then out[#out + 1] = b end
  end
  -- (a flyout in Quick Find's open, Ammo's arrows and bullets: its buttons)
  local sub = g.quickFindOpen and g.quickFindSub
  if sub then
    for _, e in ipairs(sub.sub or {}) do add(g.quickFindButtons and g.quickFindButtons[e.kind]) end
    if #out > 0 then return out end
  end
  if g.quickFindOpen and g.QuickFindEntries then
    for _, e in ipairs(g.QuickFindEntries()) do add(g.quickFindButtons and g.quickFindButtons[e.kind]) end
    if #out > 0 then return out end
  end
  local open = g.OpenGroupSlot and g.OpenGroupSlot()
  if open then
    for _, m in ipairs(open.members or {}) do add(m.button) end
    if #out > 0 then return out end
  end
  local order = { barUp = 1, menuUp = 2, barRight = 3, menuRight = 4 }
  local slots = {}
  for i, t in ipairs(g.QuickSlots and g.QuickSlots() or {}) do
    if t.button and t.button:IsShown() and order[t.where or ""] then slots[#slots + 1] = { t, i } end
  end
  table.sort(slots, function(a, b)
    local wa, wb = order[a[1].where], order[b[1].where]
    if wa ~= wb then return wa < wb end
    return a[2] < b[2]
  end)
  for _, s in ipairs(slots) do out[#out + 1] = s[1].button end
  return out
end
Pad.RING_SHARE = 1.5 -- (the focus ring round a button, its size by the button's)
local ring
function Pad.SetFocus(b)
  local old = Pad.focus
  if old == b then return end
  if old then
    local leave = old:GetScript("OnLeave")
    if leave then pcall(leave, old) end
  end
  Pad.focus = b
  if not b then
    if ring then ring:Hide() end
    return
  end
  if not ring then
    ring = CreateFrame("Frame", nil, b)
    local t = ring:CreateTexture(nil, "OVERLAY")
    t:SetAllPoints()
    t:SetTexture("Interface\\AddOns\\AzerothGPS\\Media\\MapMenu")
    t:SetBlendMode("ADD")
    t:SetVertexColor(1, 0.82, 0.1)
    ring.tex = t
  end
  ring:SetParent(b)
  ring:ClearAllPoints()
  ring:SetPoint("CENTER", b, "CENTER")
  -- (the round frame's art drawn at its size, pixel for pixel: GPSFrame's G.FitFrameArt; a round button's by its size in
  -- whole pixels)
  local a = b.agpsArt
  local GPS = ns.GPS
  local want = (a and a.F and a.F / a.ppu or b:GetWidth() or 26) * Pad.RING_SHARE
  if GPS and GPS.FitFrameArt then
    local u = GPS.FitFrameArt(ring.tex, b, want)
    ring:SetSize(u, u)
  else
    ring:SetSize(want, want)
  end
  ring:SetFrameLevel((b:GetFrameLevel() or 1) + 5)
  ring:Show()
  Pad.ring = ring
  local enter = b:GetScript("OnEnter")
  if enter then pcall(enter, b) end
end
-- the focus `step` along the menu's buttons (0: the first, if none yet), wrapping round
function Pad.Move(step)
  local list = Pad.MenuButtons()
  if #list == 0 then Pad.SetFocus(nil) return false end
  local at
  for i, b in ipairs(list) do
    if b == Pad.focus then at = i end
  end
  if not at then Pad.SetFocus(list[1]) return true end
  Pad.SetFocus(list[((at - 1 + step) % #list) + 1])
  return true
end
-- The map menu's own buttons as laid out: the column going up and the row going right (nil while a group or Quick
-- Find is open: one list then)
function Pad.MenuParts()
  local g = G()
  if not g or g.quickFindOpen or (g.OpenGroupSlot and g.OpenGroupSlot()) then return nil end
  local col, row = {}, {}
  local order = { barUp = 1, menuUp = 2, barRight = 3, menuRight = 4 }
  local slots = {}
  for i, t in ipairs(g.QuickSlots and g.QuickSlots() or {}) do
    if t.button and t.button:IsShown() and order[t.where or ""] then slots[#slots + 1] = { t, i } end
  end
  table.sort(slots, function(a, b)
    local wa, wb = order[a[1].where], order[b[1].where]
    if wa ~= wb then return wa < wb end
    return a[2] < b[2]
  end)
  for _, sl in ipairs(slots) do
    local w = sl[1].where
    local list = (w == "barUp" or w == "menuUp") and col or row
    list[#list + 1] = sl[1].button
  end
  return col, row
end
-- The D-pad in the map menu (asked 2026-11-16: "Up/Down is only the vertical column and left/right is only the bottom
-- right row. Halfway up vertical D pad right would jump to first item on horizontal row and vise versa"): up and down
-- move along the column (from the row: the column's first), right and left along the row (from the column: the row's
-- first), each round at its end. A group or Quick Find open: its list, up and right on, down and left back.
function Pad.MoveDir(dir)
  local col, row = Pad.MenuParts()
  if not col then return Pad.Move((dir == "up" or dir == "right") and 1 or -1) end
  local vertical = dir == "up" or dir == "down"
  local list = vertical and col or row
  if #list == 0 then return false end
  local at
  for i, b in ipairs(list) do if b == Pad.focus then at = i end end
  if not at then Pad.SetFocus(list[1]) return true end
  local step = (dir == "up" or dir == "right") and 1 or -1
  Pad.SetFocus(list[((at - 1 + step) % #list) + 1])
  return true
end
function Pad.OpenMenu()
  local g = G()
  if not (g and g.mapMenu) then return false end
  g.mapMenu:Show()
  g.mapMenu.idle = 0
  Pad.SetFocus(nil)
  Pad.Move(0)
  Pad.ShowMarks(true)
  return true
end
function Pad.CloseMenu()
  local g = G()
  Pad.SetFocus(nil)
  if g.quickFindOpen and g.SetQuickFindOpen then g.SetQuickFindOpen(false) end
  if g.CloseOpenGroup then g.CloseOpenGroup() end
  if g.mapMenu then g.mapMenu:Hide() end
  Pad.ShowMarks(Pad.bound)
  return true
end
-- The button whose group (or Quick Find) is open in the map menu: Back's way out of it; nil with none open.
function Pad.MenuParent()
  local g = G()
  if not g then return nil end
  local sub = g.quickFindOpen and g.quickFindSub
  if sub then
    local pb = g.quickFindButtons and g.quickFindButtons[sub.kind]
    if pb and pb:IsShown() then return pb end
  end
  if g.quickFindOpen then
    for _, t in ipairs(g.QuickSlots and g.QuickSlots() or {}) do
      if t.id == "quickFind" and t.button and t.button:IsShown() then return t.button end
    end
  end
  local open = g.OpenGroupSlot and g.OpenGroupSlot()
  return open and open.button or nil
end
-- the focus on a quick slot by its id, if shown (back from its flyout)
function Pad.FocusSlot(id)
  local g = G()
  for _, t in ipairs(g.QuickSlots and g.QuickSlots() or {}) do
    if t.id == id and t.button and t.button:IsShown() then Pad.SetFocus(t.button) return true end
  end
  return Pad.Move(0)
end
function Pad.MenuRun(has, down)
  if not down then return nil end
  local g = G()
  if g.mapMenu then g.mapMenu.idle = 0 end
  local q = Pad.Question()
  if q and has.yes then return Click(q.yes) end
  if q and has.back then return Click(q.no) end
  if has.menu then
    if Pad.MenuOpen() then return Pad.CloseMenu() end
    return Pad.OpenMenu()
  end
  if has.back then
    -- (a flyout in a flyout, Quick Find's Ammo: back to its button; asked 2026-11-16, "we need to support sub menu
    -- nesting navigation")
    local sub = g.quickFindOpen and g.quickFindSub
    if sub and g.SetQuickFindOpen then
      g.SetQuickFindOpen(true, nil)
      Pad.SetFocus(nil)
      local pb = g.quickFindButtons and g.quickFindButtons[sub.kind]
      if pb and pb:IsShown() then Pad.SetFocus(pb) else Pad.Move(0) end
      return true
    end
    if g.quickFindOpen and g.SetQuickFindOpen then
      g.SetQuickFindOpen(false)
      Pad.SetFocus(nil)
      return Pad.FocusSlot("quickFind")
    end
    local open = g.OpenGroupSlot and g.OpenGroupSlot()
    if open and g.CloseOpenGroup and g.CloseOpenGroup() then
      Pad.SetFocus(nil)
      if open.button and open.button:IsShown() then Pad.SetFocus(open.button) else Pad.Move(0) end
      return true
    end
    return Pad.CloseMenu()
  end
  if has.select or has.yes or has.click then -- (Select too: it presses what's under it)
    local b = Pad.focus
    if not b then return Pad.Move(0) end
    local was = Pad.MenuButtons()
    Click(b)
    if not Pad.MenuOpen() then
      Pad.SetFocus(nil)
      Pad.ShowMarks(Pad.bound)
      return true
    end
    -- (a group or Quick Find opened: the focus on its first button)
    local now = Pad.MenuButtons()
    if now[1] and now[1] ~= was[1] then
      Pad.SetFocus(nil)
      Pad.Move(0)
    end
    return true
  end
  -- (a button with a right-click of its own, the Quest Route button's menu of other ways: Remove's button, X, as its
  -- right-click; asked 2026-11-22 for 1.3.14)
  if has.remove and Pad.focus and Pad.focus.agpsRightClick then
    local on = Pad.focus:GetScript("OnClick")
    if on then on(Pad.focus, "RightButton") end
    return true
  end
  if has.panUp then return Pad.MoveDir("up") end
  if has.panDown then return Pad.MoveDir("down") end
  if has.panRight then return Pad.MoveDir("right") end
  if has.panLeft then return Pad.MoveDir("left") end
  return true -- (the map's own controls: not while the menu is open)
end

-- A control done once, as from its macro (Pad.MACROS): as its button pressed and let go; the pan and zoom controls one
-- step (the map menu open: the focus moved, as the pad's). The map menu opened or closed with no pad in use too.
function Pad.MacroRun(id)
  local a = Pad.Action(id)
  local g = G()
  if not (a and g) then return false end
  if a.game then
    if AzerothGPS_ToggleMap then AzerothGPS_ToggleMap() end
    return true
  end
  if id == "menu" then
    if g.mapMenu and g.mapMenu:IsShown() then return Pad.CloseMenu() end
    if Pad.bound then return Pad.OpenMenu() end
    if not g.mapMenu then return false end
    g.mapMenu:Show()
    g.mapMenu.idle = 0
    return true
  end
  if Pad.HELD[id] and not Pad.MenuOpen() then
    if id == "zoomIn" or id == "zoomOut" then
      g.WheelZoom(id == "zoomIn" and 1 / g.ZOOM_STEP or g.ZOOM_STEP)
    else
      local s = Pad.PAN_STEP
      g.PadPan(id == "panRight" and s or id == "panLeft" and -s or 0, id == "panUp" and s or id == "panDown" and -s or 0)
    end
    if g.Redraw then g.Redraw() end
    return true
  end
  local r = Pad.Run({ id }, true)
  Pad.Run({ id }, false)
  if Pad.HELD[id] then Pad.held[id] = nil end
  return r
end

-- Offered once (a pad first active), and with /agps pad: "Show/Hide AzerothGPS" on the button the player presses (no
-- button assumed: Back is the game's own; asked 2026-11-16, "Back is already taken by default controller controls
-- though"). The capture Change uses, B or Escape canceling; a button the game has a binding on is asked about first.
function Pad.Offer()
  local g = G()
  if not (g and g.Ask) then return false end
  if InCombat() then
    if ns.Print then ns.Print(L["Controller: try again after the fight."]) end
    return false
  end
  if ns.db then ns.db.padOffered = true end
  return Pad.BeginCapture("toggle", function(r, key)
    if r == true and ns.Print then
      ns.Print(string.format(L["Controller: %s opens and closes the map."], Pad.BindLabel(key)))
    end
  end, true)
end
-- The game's binding on `key` now ("" or nil: none), and its name as the game's Key Bindings shows it.
function Pad.GameBinding(key)
  local act = GetBindingAction and GetBindingAction(key) or nil
  if act == "" then act = nil end
  return act
end
function Pad.BindingName(act)
  if not act then return L["nothing"] end
  if GetBindingName then
    local ok, n = pcall(GetBindingName, act)
    if ok and type(n) == "string" and n ~= "" and n ~= act then return n end
  end
  local n = rawget(_G, "BINDING_NAME_" .. act)
  return type(n) == "string" and n or act
end
-- What a capture of the game's Show/Hide key says: press a button, and how a pair is made (or that none can be).
function Pad.CaptureHint()
  local list = {}
  for key, mod in pairs(Pad.GameMods()) do
    list[#list + 1] = Pad.KeyLabel(key) .. " (" .. ({ SHIFT = L["Shift"], CTRL = L["Ctrl"], ALT = L["Alt"] })[mod] .. ")"
  end
  table.sort(list)
  if #list == 0 then
    return L["No trigger or bumper is a Shift, Ctrl or Alt in the game's Gamepad settings, so holding one makes no pair here. Set one there to use a pair such as LT + Back."]
  end
  return string.format(L["For a pair, hold %s, then press the other button."], table.concat(list, L[", "]))
end
function Pad.MaybeOffer()
  if ns.db and not ns.db.padOffered and Pad.Active() then return Pad.Offer() end
  return false
end

-- Changing a button (Options > Controller's list). Out of combat; in a fight it waits for the fight's end (Pad.pending).
-- Refused: a button another action has (but the stop's and Yes's, which share one), and none at all for Back (the way
-- out of the map). The game's own Show/Hide AzerothGPS binding is set with SetBinding and saved, the key it had let go.
-- Returns true; "wait" (in a fight); or false and why.
Pad.pending = {}
function Pad.Rebind()
  if not Pad.bound or Locked() then return end
  pcall(ClearOverrideBindings, Owner())
  Pad.bound, Pad.held = false, {}
  Pad.Apply()
end
local function Relegend()
  if Pad.legend and Pad.legend:IsShown() then Pad.legend:SetText(Pad.LegendText(true)) end
  if Pad.marksOn then Pad.ShowMarks(true) end -- (the box: its lines as bound now)
end
function Pad.SetBind(id, key)
  local a = Pad.Action(id)
  if not a then return false, "?" end
  if not key then
    if id == "back" then return false, L["Back can't be left without a button."] end
    return false, L["Not bound"]
  end
  local m, k = Pad.Split(key)
  if m and (a.game or m == k) then return false, L["This one takes a single button."] end
  local why = Pad.Taken(id, key, Pad.IsHold(id))
  if why then return false, why end
  if InCombat() then
    Pad.pending[id] = key
    return "wait", L["Changes after the fight."]
  end
  local saved = S().padBinds or {}
  if a.game and Pad.IsHold(id) then
    saved[id] = key -- (held: no game binding; the game's own on the button stays, a tap does that)
  elseif a.game then
    local old = Pad.Key(id)
    if old and old ~= key and SetBinding then pcall(SetBinding, old) end
    if SetBinding then pcall(SetBinding, key, "AZEROTHGPS_TOGGLE") end
    if SaveBindings and GetCurrentBindingSet then pcall(SaveBindings, GetCurrentBindingSet()) end
    saved[id] = key
  else
    saved[id] = key ~= a[2] and key or nil
  end
  S().padBinds = next(saved) and saved or nil
  if not a.game then Pad.Rebind() end
  Pad.pending[id] = nil
  Relegend()
  return true
end
-- Another control on `key` held the same way (`hold`): its "Already used" line, or nil. (A and A (hold) are two.)
function Pad.Taken(id, key, hold)
  for _, o in ipairs(Pad.ACTIONS) do
    if o[1] ~= id and Pad.SHARED[id] ~= o[1] and Pad.Key(o[1]) == key and Pad.IsHold(o[1]) == (hold and true or false) then
      return string.format(L["Already used: %s"], o[3] .. (hold and " " .. L["(hold)"] or ""))
    end
  end
  return nil
end
-- A control held or not (Options > Controller's Hold box). Not the pan and zoom controls (done while held), nor the
-- game's own Show/Hide key; refused when another control has its button that way. Returns true, "wait" or false, why.
-- Show/Hide held (asked 2026-11-16 with Gamepad UI's Back: "No interface frame to focus!", "Ideally Back (hold) would
-- be an option here"): no game binding then, its button watched while held (Pad.ToggleHoldTick), the game's own tap
-- left as it is.
function Pad.CanHold(id)
  local a = Pad.Action(id)
  return a and (not a.game or id == "toggle") and not Pad.HELD[id] and true or false
end
function Pad.SetHold(id, on)
  on = on and true or false
  if not Pad.CanHold(id) then return false, L["Done while held: it can't be a hold."] end
  local why = Pad.Taken(id, Pad.Key(id), on)
  if why then return false, why end
  if InCombat() then
    Pad.pending["hold:" .. id] = on
    return "wait", L["Changes after the fight."]
  end
  local a = Pad.Action(id)
  if a and a.game and on ~= Pad.IsHold(id) then
    local key = Pad.Key(id)
    local saved = S().padBinds or {}
    if on then -- (the game's binding of ours off; the button kept as ours, held)
      if key and SetBinding then
        pcall(SetBinding, key)
        if SaveBindings and GetCurrentBindingSet then pcall(SaveBindings, GetCurrentBindingSet()) end
      end
      saved[id] = key
    elseif key and Pad.GameBinding(key) == nil and SetBinding then -- (a tap again: the game's, when nothing's on it)
      pcall(SetBinding, key, "AZEROTHGPS_TOGGLE")
      if SaveBindings and GetCurrentBindingSet then pcall(SaveBindings, GetCurrentBindingSet()) end
    elseif key then
      saved[id] = nil -- (the game has the button: no tap of ours there, Change for another)
    end
    S().padBinds = next(saved) and saved or nil
  end
  local h = S().padHold or {}
  h[id] = on or nil
  S().padHold = next(h) and h or nil
  Pad.Rebind()
  Relegend()
  return true
end
-- A control on no button (Options' button window: its toggle off, or None): true, or false and why. Back always has one.
Pad.UNBOUND = "NONE"
function Pad.Unbind(id)
  local a = Pad.Action(id)
  if not a then return false, "?" end
  if id == "back" then return false, L["Back can't be left without a button."] end
  if not Pad.Key(id) then return true end
  if InCombat() then return false, L["Not during a fight."] end
  local saved = S().padBinds or {}
  if a.game then
    local old = Pad.Key(id)
    if not Pad.IsHold(id) and old and SetBinding then
      pcall(SetBinding, old)
      if SaveBindings and GetCurrentBindingSet then pcall(SaveBindings, GetCurrentBindingSet()) end
    end
    saved[id] = nil
  else
    saved[id] = a[2] and Pad.UNBOUND or nil
  end
  S().padBinds = next(saved) and saved or nil
  local h = S().padHold
  if h then
    h[id] = nil
    S().padHold = next(h) and h or nil
  end
  Pad.pending[id] = nil
  if not a.game then Pad.Rebind() end
  Relegend()
  return true
end
-- Control `id` on binding `bind` ("PAD1", "PADLTRIGGER+PAD1"), held or not, in one step (Options' button window: no
-- in-between state refused as taken). True, or false and why.
function Pad.Assign(id, bind, hold)
  hold = hold and true or false
  local a = Pad.Action(id)
  if not a or not bind then return false, "?" end
  if hold and not Pad.CanHold(id) then return false, L["Done while held: it can't be a hold."] end
  local m, k = Pad.Split(bind)
  if m and (a.game or m == k) then return false, L["This one takes a single button."] end
  local why = Pad.Taken(id, bind, hold)
  if why then return false, why end
  if InCombat() then return false, L["Not during a fight."] end
  if a.game then
    if hold ~= Pad.IsHold(id) then
      local r, w = Pad.SetHold(id, hold)
      if r ~= true then return r, w end
    end
    return Pad.SetBind(id, bind)
  end
  local saved = S().padBinds or {}
  saved[id] = bind ~= a[2] and bind or nil
  S().padBinds = next(saved) and saved or nil
  local h = S().padHold or {}
  h[id] = hold or nil
  S().padHold = next(h) and h or nil
  Pad.pending[id] = nil
  Pad.Rebind()
  Relegend()
  return true
end
-- What each control does, for its entry in Options' lists (asked 2026-11-16: "hovering this in the dropdown explains
-- the action")
Pad.ABOUT = {
  viewControls = L["Shows the controller's buttons over the map for a while, as Options draws them."],
  click = L["Clicks what's under the crosshair, as a left-click does: a dungeon's or cave's entrance opens its map, for example."],
  questRoute = L["Routes through your quest log's objectives and turn-ins, in the fastest order."],
  pause = L["Pauses or resumes routing, the stops kept."],
  select = L["Sets a stop at the crosshair, or routes to the map icon under it."],
  yes = L["Answers Yes to a question the map asks, such as removing a stop."],
  remove = L["Removes the stop under the crosshair (it asks first)."],
  back = L["Goes back: closes the map menu or a question (No), else the map."],
  clear = L["Clears the whole route."],
  zoomIn = L["Zooms the map in while held."],
  zoomOut = L["Zooms the map out while held."],
  panUp = L["Pans the map up while held."],
  panDown = L["Pans the map down while held."],
  panLeft = L["Pans the map left while held."],
  panRight = L["Pans the map right while held."],
  recenter = L["Moves the map back to you."],
  toggle = L["Shows or hides AzerothGPS, with the map open or not."],
  menu = L["Opens and closes the map menu."],
  options = L["Opens AzerothGPS Options."],
}
-- the map's buttons back to the defaults (the game's own Show/Hide key left as the player set it)
function Pad.ResetBinds()
  if InCombat() then
    Pad.pending.reset = true
    return "wait", L["Changes after the fight."]
  end
  local keep = S().padBinds and S().padBinds.toggle
  S().padBinds = keep and { toggle = keep } or nil
  S().padHold = nil
  Pad.pending = {}
  Pad.Rebind()
  Relegend()
  return true
end
function Pad.ApplyPending()
  if InCombat() then return end
  local p = Pad.pending
  Pad.pending = {}
  if p.reset then Pad.ResetBinds() end
  for id, key in pairs(p) do
    local hold = type(id) == "string" and id:match("^hold:(.+)$")
    if hold then Pad.SetHold(hold, key)
    elseif id ~= "reset" then Pad.SetBind(id, key) end
  end
end

-- The keys held on the pad now: { [key] = true } (C_GamePad's state; ButtonIndexToBinding names each button's key).
function Pad.KeysDown()
  local C = rawget(_G, "C_GamePad")
  local out = {}
  if type(C) ~= "table" or not C.GetDeviceMappedState then return out end
  local ok, st = pcall(C.GetDeviceMappedState, Pad.Device())
  if not ok or type(st) ~= "table" or type(st.buttons) ~= "table" then return out end
  for i, on in ipairs(st.buttons) do
    if on and C.ButtonIndexToBinding then
      local okK, k = pcall(C.ButtonIndexToBinding, i - 1)
      if okK and type(k) == "string" then out[k] = true end
    end
  end
  return out
end
-- Change: the next button pressed on the pad becomes `id`'s, B too (tapped); Escape or B held cancels;
-- CAPTURE_SECONDS without one, too. (asked 2026-11-16: "can't bind B because it cancels the input")
-- `done(result, key, why)`: result true, "wait", false (refused), or nil (canceled / timed out).
local capture
function Pad.Capturing() return capture and capture.id or nil end
local function HidePrompt(c)
  local f = c and c.prompt
  if f and f:IsShown() then
    f.answered = true -- (not its No: done here)
    f:Hide()
  end
end
function Pad.CancelCapture()
  local c = capture
  capture = nil
  if Pad.captureFrame then Pad.captureFrame:Hide() end
  HidePrompt(c)
  if c and c.done then c.done(nil, nil, L["Canceled"]) end
end
-- `prompt`: a window says to press a button (the offer, from the map); Options' row says it itself. The game's own
-- binding (Show/Hide AzerothGPS): its pairs are the game's modifiers (Pad.GameMods), and a button the game has a
-- binding on is asked about (Yes takes it, No waits for another press).
function Pad.BeginCapture(id, done, prompt)
  if capture then Pad.CancelCapture() end
  if InCombat() then
    if done then done("wait", nil, L["Changes after the fight."]) end
    return false
  end
  local a = Pad.Action(id)
  capture = { id = id, done = done, at = GetTime and GetTime() or 0, was = Pad.KeysDown(), game = a and a.game,
    wantPrompt = prompt }
  if prompt and G() and G().Ask then
    local c = capture
    c.prompt = G().Ask("AzerothGPSPadCapture",
      L["Press the controller button for Show/Hide GPS. Hold B or press Escape to cancel."] .. "\n\n" .. Pad.CaptureHint(),
      CANCEL or L["Cancel"], nil, function() if capture == c then Pad.CancelCapture() end end,
      function() if capture == c then Pad.CancelCapture() end end, { single = true })
    Pad.captureHint = nil
  else
    Pad.captureHint = capture.game and Pad.CaptureHint() or nil
  end
  local f = Pad.captureFrame
  if not f then
    f = CreateFrame("Frame", nil, UIParent)
    if f.EnableKeyboard then f:EnableKeyboard(true) end
    f:SetScript("OnKeyDown", function(self, k)
      if k == "ESCAPE" then
        if self.SetPropagateKeyboardInput then pcall(self.SetPropagateKeyboardInput, self, false) end
        Pad.CancelCapture()
      elseif self.SetPropagateKeyboardInput then
        pcall(self.SetPropagateKeyboardInput, self, true)
      end
    end)
    f:SetScript("OnUpdate", function() Pad.CaptureTick() end)
    Pad.captureFrame = f
  end
  f:Show()
  return true
end
function Pad.CaptureTick()
  local c = capture
  if not c then return end
  if GetTime and GetTime() - c.at > Pad.CAPTURE_SECONDS then return Pad.CancelCapture() end
  local now = Pad.KeysDown()
  for k in pairs(c.was) do
    if not now[k] and k ~= c.mod then c.was[k] = nil end -- (let go: a press of it again counts)
  end
  -- (a trigger or bumper held: a pair with the next button pressed, or itself alone when let go first. The game's own
  -- binding: only a button the game's Gamepad settings make a Shift, Ctrl or Alt, and the pair a game binding)
  local gameKey = c.game and not Pad.IsHold(c.id) -- (held: ours, any pair, no game binding asked about)
  local mods = gameKey and Pad.GameMods() or Pad.MODIFIERS
  local function finish(bind)
    capture = nil
    if Pad.captureFrame then Pad.captureFrame:Hide() end
    HidePrompt(c)
    local act = gameKey and Pad.GameBinding(bind)
    if act and act ~= "AZEROTHGPS_TOGGLE" then -- (the game's on it: asked, never taken unasked)
      local g = G()
      local q = string.format(L["%s is %s: use it for Show/Hide GPS instead?"], Pad.BindLabel(bind),
        Pad.BindingName(act))
      if g and g.Confirm and g.Confirm(q, function()
        local r, why = Pad.SetBind(c.id, bind)
        if c.done then c.done(r, bind, why) end
      end, function(clicked)
        if clicked then Pad.BeginCapture(c.id, c.done, c.wantPrompt) -- (No: another button)
        elseif c.done then c.done(nil, nil, L["Canceled"]) end
      end) then return end
    end
    local r, why = Pad.SetBind(c.id, bind)
    if c.done then c.done(r, bind, why) end
  end
  if c.mod and not now[c.mod] then return finish(c.mod) end
  local B = Pad.CANCEL_KEY
  if c.cancelAt then -- (B down: held, a cancel; let go first, B itself)
    if not now[B] then return finish(B) end
    if GetTime and GetTime() - c.cancelAt >= Pad.CANCEL_HOLD then return Pad.CancelCapture() end
    return
  end
  for k in pairs(now) do
    if not c.was[k] then
      if mods[k] and not c.mod then
        c.mod = k
        c.was[k] = true
      elseif k == B and not c.mod then
        c.cancelAt = GetTime and GetTime() or 0
        c.was[k] = true
        return
      elseif gameKey then
        return finish(c.mod and (mods[c.mod] .. "-" .. k) or k)
      else
        return finish(c.mod and (c.mod .. "+" .. k) or k)
      end
    end
  end
end

-- Show/Hide held: its button (or pair) down HOLD_SECONDS toggles the map, once a press; never while a Change waits.
function Pad.ToggleHoldTick(dt)
  local key = Pad.IsHold("toggle") and Pad.Key("toggle")
  if not key or Pad.Capturing() or not Pad.Device() then Pad.toggleHeld = nil return end
  local m, k = Pad.Split(key)
  local now = Pad.KeysDown()
  if not (now[k] and (not m or now[m])) then Pad.toggleHeld = nil return end
  local t = GetTime and GetTime() or 0
  if not Pad.toggleHeld then Pad.toggleHeld = { at = t } return end
  if not Pad.toggleHeld.done and t - Pad.toggleHeld.at >= Pad.HOLD_SECONDS then
    Pad.toggleHeld.done = true
    local f = rawget(_G, "AzerothGPS_ToggleMap")
    if f then f() end
  end
end

-- The listener: combat, logout, a pad coming and going, and the check twice a second (a watchdog too: the map closed
-- however it was, the bindings go).
do
  local o = Owner()
  local function Reg(e) pcall(o.RegisterEvent, o, e) end
  for _, e in ipairs({ "PLAYER_REGEN_DISABLED", "PLAYER_REGEN_ENABLED", "PLAYER_LOGOUT", "GAME_PAD_ACTIVE_CHANGED",
    "GAME_PAD_CONNECTED", "GAME_PAD_DISCONNECTED", "GLOBAL_MOUSE_DOWN" }) do
    Reg(e)
  end
  o:SetScript("OnEvent", function(_, e, a)
    if e == "GLOBAL_MOUSE_DOWN" then -- (the mouse in use: the controller's marks go)
      if Pad.used then Pad.SawInput(false) end
      return
    end
    if e == "GAME_PAD_ACTIVE_CHANGED" then Pad.SawInput(a == true) end
    if e == "GAME_PAD_DISCONNECTED" then Pad.SawInput(false) end
    if e == "PLAYER_REGEN_DISABLED" or e == "PLAYER_LOGOUT" then
      Pad.Clear() -- (before the lockdown: allowed, and a pad mid-fight is the game's)
      if capture then Pad.CancelCapture() end
    else
      if e == "PLAYER_REGEN_ENABLED" then Pad.ApplyPending() end
      Pad.Apply()
    end
  end)
  local driver = CreateFrame("Frame", nil, UIParent)
  local since = 0
  driver:SetScript("OnUpdate", function(_, dt)
    if Pad.IsHold("toggle") then
      local ok, err = pcall(Pad.ToggleHoldTick, dt)
      if not ok and ns.GPS and ns.GPS.LogError then ns.GPS.LogError("controller", err) end
    end
    since = since + (dt or 0)
    if since >= Pad.CHECK_SECONDS then
      since = 0
      local ok, err = pcall(Pad.Apply)
      if not ok and ns.GPS and ns.GPS.LogError then ns.GPS.LogError("controller", err) end
    end
    if Pad.bound then
      local ok, err = pcall(Pad.Tick, dt)
      if not ok and ns.GPS and ns.GPS.LogError then ns.GPS.LogError("controller", err) end
    end
    if Pad.bound or #Pad.hints > 0 then -- (the buttons' hints: placed and faded, hidden once not wanted)
      local ok, err = pcall(Pad.HintTick, dt)
      if not ok and ns.GPS and ns.GPS.LogError then ns.GPS.LogError("controller", err) end
    end
  end)
  Pad.driver = driver
end
