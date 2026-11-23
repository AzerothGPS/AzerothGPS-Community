-- The Quest Route button's choices (asked 2026-11-22: "lets extend the quest route button with a sub menu to route in
-- different ways like by level, turn ins only, tracked quest only, etc"; then, for 1.3.14: "make these quick buttons
-- that can be toggled on/off. If any of them conflict with another auto turn it on/off like picking turn-ins only and
-- tracked quests only for example, only 1 should be on at a time or both off"; then, of the text menu that was: "this
-- still isn't sub menu buttons, should be like the ammo button, expand into more icons with on/off toggles").
-- Right-click the button: round icon buttons pop out of it as Quick Find's do (G.QUICK_FIND, the one with Ammo; the
-- same round buttons, G.NewRoundButton, the same way out and spacing: right of a column going up, up from a row going
-- right), one per toggle and one for Quest Route options. On: full color in a lit gold ring; off: gray and dimmed.
-- Each is a saved Quest Route option (Options > Routing > Quest Route is their home; these are a second control for
-- them), and a left-click of the button makes the route by them.
--
-- The toggles and their groups (at most one on in a group, or none):
--   Order: Lowest level first, About to turn gray first (`questLevelOrder` "low" / "gray"; gray in Options and the
--     slash command only, no icon). Fastest order is neither:
--     on while neither is, turning it on turns both off (clicked while on it stays on: the others turn it off).
--   What's routed: Turn-ins only (`questTurninsOnly`), Objectives only (`questObjectivesOnly`), Tracked quests only
--     (`questTrackedOnly`): one turned on turns the other two off. The Options page's check boxes keep the same rule
--     (G.SetQuestToggle).
--   This zone only (`questZoneOnly`): its own, with anything.
-- A toggle clicked on a quest route makes it again at once with the new options; on any other route (or none) it's
-- only saved. The icons stay out for more; they go in on a click anywhere else, the button again, B or Escape (Escape
-- shuts only them: not the map, nor the game's menu), and as Quick Find's do (GROUP_IDLE untouched, or the button
-- gone). Quests left out (Leave Out, a removed stop) stay out.
--
-- All our own frames, never the game's menus (MenuUtil, dropdowns): with the game's controller UI on, the game's menus
-- with an addon's entries got AzerothGPS blocked (issue #887). /agps questroute <way> [off] turns a toggle on (or off)
-- as the icons do, then makes the quest route (a controller's macro).
--
-- With a controller (asked 2026-11-22 for 1.3.14: "add controller support for quest route sub menu, just fade between
-- the 2 buttons for activating and opening the submenu"): the button in the map menu's focus, its hint fades from the
-- button that presses it (Set Stop's, A) to the one that opens the icons (Remove's, X: its right-click) and back
-- (Pad.lua's HintTargets, SWAP_SECONDS). Out: the map menu's focus ring moves over the icons as over Quick Find's
-- (Pad.MenuButtons: up and right the next, down and left the one before, round at the ends), starting on the first;
-- A turns the one in focus on or off (they stay out), B (or X again) shuts them, the focus back on the button.
local _, ns = ...
local L = ns.L
local G = ns.GPS

-- Each toggle: `key` the setting it is (with `value`: on when the setting is that), `group` the ones of which at most
-- one is on; `icon` its round button's picture, `tip` its tooltip's line.
G.QUEST_WAYS = {
  { id = "fastest", word = "fastest", label = L["Fastest order"], group = "order",
    icon = "Interface\\Icons\\INV_Boots_02",
    tip = L["Visits your quests in the quickest order."] },
  { id = "low", word = "low", label = L["Lowest level first"], key = "questLevelOrder", value = "low", group = "order",
    icon = "Interface\\Icons\\Spell_ChargePositive",
    tip = L["Visits your lowest-level quests first."] },
  -- (About to turn gray first: in Options and /agps questroute gray only, no icon on the flyout; Kooki3z 2026-11-22.
  -- Set there, Fastest order and Lowest level first both show off: it's neither)
  { id = "gray", word = "gray", label = L["About to turn gray first"], key = "questLevelOrder", value = "gray",
    group = "order", noIcon = true },
  { id = "turnins", word = "turnins", label = L["Turn-ins only"], key = "questTurninsOnly", group = "what",
    icon = "Interface\\GossipFrame\\ActiveQuestIcon",
    tip = L["Only goes to quests that are ready to turn in."] },
  { id = "objectives", word = "objectives", label = L["Objectives only"], key = "questObjectivesOnly", group = "what",
    icon = "Interface\\GossipFrame\\AvailableQuestIcon",
    tip = L["Only goes to quest objectives, not turn-ins."] },
  { id = "tracked", word = "tracked", label = L["Tracked quests only"], key = "questTrackedOnly", group = "what",
    icon = "Interface\\Icons\\INV_Misc_Eye_01",
    tip = L["Only goes to the quests you're tracking."] },
  { id = "zone", word = "zone", label = L["This zone only"], key = "questZoneOnly",
    icon = "Interface\\Icons\\INV_Misc_Map_01",
    tip = L["Only goes to quests in the zone you're in."] },
}

local function Settings() return ns.settings and ns.settings.gps or {} end

function G.QuestWayEntry(id)
  for _, e in ipairs(G.QUEST_WAYS) do
    if e.id == id then return e end
  end
  return nil
end
-- Whether toggle `id` is on (the saved options).
function G.QuestToggleOn(id)
  local e = G.QuestWayEntry(id)
  if not e then return false end
  local st = Settings()
  if e.id == "fastest" then
    return st.questLevelOrder ~= "low" and st.questLevelOrder ~= "gray"
  end
  if e.value then return st[e.key] == e.value end
  return st[e.key] and true or false
end
-- Turn toggle `id` on or off, the others of its group off when it goes on. Fastest order on: both level orders off;
-- Fastest order off: nothing (it's what's left with neither on). Returns whether a toggle changed.
function G.SetQuestToggle(id, on)
  local e = G.QuestWayEntry(id)
  if not e then return false end
  local st = Settings()
  local before = {}
  for _, o in ipairs(G.QUEST_WAYS) do before[o.id] = G.QuestToggleOn(o.id) end
  on = on and true or false
  if e.id == "fastest" then
    if on then st.questLevelOrder = "off" end
  elseif e.value then
    if on then
      st[e.key] = e.value
    elseif st[e.key] == e.value then
      st[e.key] = "off"
    end
  else
    st[e.key] = on
    if on and e.group then
      for _, o in ipairs(G.QUEST_WAYS) do
        if o.group == e.group and o ~= e and o.key and not o.value then st[o.key] = false end
      end
    end
  end
  for _, o in ipairs(G.QUEST_WAYS) do
    if before[o.id] ~= G.QuestToggleOn(o.id) then return true end
  end
  return false
end
-- What the quest route takes by the saved options: "turnin" (turn-ins only), "objectives" (no turn-ins) or nil (both).
function G.QuestOnly()
  local st = Settings()
  if st.questTurninsOnly then return "turnin" end
  if st.questObjectivesOnly then return "objectives" end
  return nil
end
-- `stops` (Layers.QuestStops') with only the turn-ins (`only` "turnin") or none of them ("objectives"); nil: all.
function G.QuestWayStops(stops, only)
  if not only then return stops end
  local out = {}
  for _, d in ipairs(stops) do
    if (only == "turnin") == (d.turnin and true or false) then out[#out + 1] = d end
  end
  return out
end
-- /agps questroute <word>: the toggle by its word (fastest, low, gray, turnins, objectives, tracked, zone), or nil.
function G.QuestWayByWord(word)
  word = tostring(word or ""):lower()
  if word == "grey" then word = "gray" end
  for _, e in ipairs(G.QUEST_WAYS) do
    if e.word == word then return e.id end
  end
  return nil
end
-- Toggle `id` turned on or off by the player (`on` nil: flipped): saved, the options window's controls and the menu
-- shown again, and a quest route made again with it at once (`always`: the quest route made whatever the route is,
-- the slash command's). Returns whether a toggle changed.
function G.QuestToggle(id, on, always)
  if on == nil then on = not G.QuestToggleOn(id) end
  local changed = G.SetQuestToggle(id, on)
  if changed and ns.Options and ns.Options.Refresh then ns.Options.Refresh() end
  G.RefreshQuestWays()
  local N = ns.Nav
  if always or (changed and N and N.OnQuestRoute and N.OnQuestRoute()) then
    G.QuestRoute()
    -- (a group quest's question came up: the menu shut, so the question takes the next click)
    if G.askBox and G.askBox.IsShown and G.askBox:IsShown() then G.CloseQuestWays() end
  end
  return changed
end

-- The icons --------------------------------------------------------------------------------------------------------

G.QUEST_WAYS_SIZE = 26 -- (Quick Find's round buttons' size)
G.QUEST_WAYS_OFF_ALPHA = 0.45 -- (an off toggle: gray and dimmed, as the quick buttons' toggles show off, G.RefreshQuick)
G.QUEST_WAYS_RING_ALPHA = 0.9 -- (an on toggle: full color in a lit gold ring, G.MakeGlow's, steady)
G.QUEST_WAYS_OPTIONS_ICON = "Interface\\Icons\\INV_Misc_Gear_01"

-- An icon clicked: a toggle flipped, the icons kept out; Quest Route options shuts them and opens Options > Routing at
-- Quest Route.
function G.QuestWayPick(id)
  if id == "options" then
    G.CloseQuestWays()
    local O = ns.Options
    if O and O.ShowSettingsAt then O.ShowSettingsAt("Routing", L["Quest Route"]) end
    return true
  end
  G.QuestToggle(id)
  return true
end

-- The icons as shown, in their order out from the button: { id, text, tip, icon, on } (`on` nil: no on or off, Quest
-- Route options), the toggles then Quest Route options.
function G.QuestWayList()
  local out = {}
  for _, e in ipairs(G.QUEST_WAYS) do
    if not e.noIcon then
      out[#out + 1] = { id = e.id, text = e.label, tip = e.tip, icon = e.icon, on = G.QuestToggleOn(e.id) }
    end
  end
  out[#out + 1] = { id = "options", text = L["Quest Route options..."], icon = G.QUEST_WAYS_OPTIONS_ICON,
    tip = L["Opens the Quest Route settings."] }
  return out
end

-- An icon's tooltip: its name, what it does, and On or Off.
function G.QuestWayTip(b)
  GameTooltip:SetOwner(b, "ANCHOR_RIGHT")
  GameTooltip:SetText(b.text or "", 1, 1, 1)
  if b.tip then GameTooltip:AddLine(b.tip, nil, nil, nil, true) end
  if b.on == true then
    GameTooltip:AddLine(L["On"], 0.3, 1, 0.3)
  elseif b.on == false then
    GameTooltip:AddLine(L["Off"], 0.6, 0.6, 0.6)
  end
  GameTooltip:Show()
end

local function Combat() return (InCombatLockdown and InCombatLockdown()) and true or false end

-- What's open: a frame of ours with no size (its keys, its clock), the click-catcher under the icons, and the icons
-- themselves, made on the Quest Route button's own parent (the map's buttons, wherever the map is).
local function Build()
  local m = CreateFrame("Frame", nil, UIParent)
  m:SetSize(1, 1)
  m:SetPoint("BOTTOMLEFT")
  m.buttons = {}
  -- (a click anywhere else shuts them: under the icons, over everything else; on the Quest Route button, its
  -- left-click goes on to it, a route as ever)
  local catch = CreateFrame("Button", nil, m)
  catch:SetFrameStrata("FULLSCREEN_DIALOG")
  catch:SetFrameLevel(1)
  catch:SetAllPoints(UIParent)
  catch:RegisterForClicks("LeftButtonUp", "RightButtonUp")
  catch:SetScript("OnClick", function(_, mouse)
    local owner = m.owner
    G.CloseQuestWays()
    if mouse == "LeftButton" and owner and owner:IsMouseOver() then
      local click = owner:GetScript("OnClick")
      if click then click(owner, "LeftButton") end
    end
  end)
  m.catch = catch
  -- (shut with its button: the map closed, the map menu shut; and as Quick Find shuts, GROUP_IDLE untouched)
  m:SetScript("OnUpdate", function(self, dt)
    local b = self.owner
    if not (b and b:IsVisible()) then G.CloseQuestWays() return end
    local over = b:IsMouseOver() or G.QuestWaysMouseOver() or G.QuestWaysSel() ~= nil
    self.idle = over and 0 or (self.idle or 0) + (dt or 0)
    if self.idle >= (G.GROUP_IDLE or 8) then G.CloseQuestWays() return end
    if G.mapMenu then G.mapMenu.idle = 0 end
  end)
  if ns.TimeScript then ns.TimeScript(m, "OnUpdate", "map buttons") end
  -- (Escape shuts the icons only, taken from the game out of combat: not the map, nor the game's menu. Every other key
  -- goes on to the game; in combat the keys can't be taken, so Escape shuts them and goes on too: G.QuestWaysKey)
  m:SetScript("OnKeyDown", function(self, key) G.QuestWaysKey(self, key) end)
  m:Hide()
  return m
end
function G.QuestWaysKey(m, key)
  local eat = key == "ESCAPE" and not Combat()
  if m.SetPropagateKeyboardInput then pcall(m.SetPropagateKeyboardInput, m, not eat) end
  if key == "ESCAPE" then G.CloseQuestWays() end
end
-- The keys while open: only out of combat (in it, a keyboard-taking frame couldn't let the other keys through).
function G.QuestWaysKeys(m)
  if not m.EnableKeyboard then return end
  local on = not Combat()
  if on and m.SetPropagateKeyboardInput then on = pcall(m.SetPropagateKeyboardInput, m, true) end
  m:EnableKeyboard(on and true or false)
end

-- Icon `i` (made the first time), on `parent`: Quick Find's round button.
local function Icon(m, i, parent)
  local b = m.buttons[i]
  if b then
    if b:GetParent() ~= parent then b:SetParent(parent) end
    return b
  end
  local icon
  b, icon = G.NewRoundButton(parent, G.QUEST_WAYS_SIZE, "Interface\\Icons\\INV_Misc_QuestionMark")
  b.iconTex = icon
  b.ring = G.MakeGlow(b)
  b.ring:SetAlpha(G.QUEST_WAYS_RING_ALPHA)
  b.ring:Hide()
  b:RegisterForClicks("LeftButtonUp", "RightButtonUp")
  b:SetScript("OnClick", function(self) if self.id then G.QuestWayPick(self.id) end end)
  b:SetScript("OnEnter", function(self)
    if G.questWays then G.questWays.idle = 0 end
    G.QuestWayTip(self)
  end)
  b:Hide()
  m.buttons[i] = b
  return b
end

-- The icons' pictures and on or off as the saved options are now (a toggle clicked, or one it turned off).
function G.RefreshQuestWays()
  local m = G.questWays
  if not m then return end
  for i, r in ipairs(G.QuestWayList()) do
    local b = m.buttons[i]
    if b then
      b.id, b.on, b.text, b.tip = r.id, r.on, r.text, r.tip
      if b.iconPath ~= r.icon then
        G.SetButtonIcon(b.iconTex, r.icon)
        b.iconPath = r.icon
      end
      local lit = r.on ~= false
      b.iconTex:SetDesaturated(not lit)
      b.iconTex:SetAlpha(lit and 1 or G.QUEST_WAYS_OFF_ALPHA)
      b.ring:SetShown(r.on == true)
      if b:IsShown() and GameTooltip:GetOwner() == b then G.QuestWayTip(b) end
    end
  end
end

function G.QuestWaysOpen()
  return (G.questWays and G.questWays:IsShown()) and true or false
end
-- The icons out, in their order from the button.
function G.QuestWaysButtons()
  local m = G.questWays
  local out = {}
  if not (m and m:IsShown()) then return out end
  for i = 1, m.count or 0 do
    local b = m.buttons[i]
    if b and b:IsShown() then out[#out + 1] = b end
  end
  return out
end
function G.QuestWaysMouseOver()
  for _, b in ipairs(G.QuestWaysButtons()) do
    if b:IsMouseOver() then return true end
  end
  return false
end
function G.CloseQuestWays()
  local m = G.questWays
  if not (m and m:IsShown()) then return end
  local P = ns.Pad
  local sel = G.QuestWaysSel()
  m:Hide()
  for _, b in pairs(m.buttons) do
    if GameTooltip:GetOwner() == b then GameTooltip:Hide() end
    b:Hide()
  end
  if sel and P and P.SetFocus then P.SetFocus(nil) end
end
-- Out from `owner` (the Quest Route button) as Quick Find's: from a column going up, a row going right; from a row
-- going right, a column going up. Quick Find's and a group's flyouts shut meanwhile (they'd lie over each other).
function G.OpenQuestWays(owner)
  owner = owner or G.questRouteButton
  if not owner then return nil end
  G.questWays = G.questWays or Build()
  local m = G.questWays
  m.owner = owner
  if G.quickFindOpen and G.SetQuickFindOpen then G.SetQuickFindOpen(false) end
  if G.CloseOpenGroup then G.CloseOpenGroup() end
  local where
  for _, t in ipairs(G.QUICK or {}) do
    if t.id == "questRoute" then where = t.where end
  end
  local sideways = where == "barUp" or where == "menuUp"
  local parent = owner:GetParent() or UIParent
  local list = G.QuestWayList()
  for j = 1, #list do
    local b = Icon(m, j, parent)
    b:ClearAllPoints()
    if sideways then
      b:SetPoint("LEFT", owner, "RIGHT", 4 + (j - 1) * G.QUICK_STEP_BAR, 0)
    else
      b:SetPoint("BOTTOM", owner, "TOP", 0, 4 + (j - 1) * G.QUICK_STEP_MENU)
    end
    -- (over the click-catcher: its strata, above it)
    b:SetFrameStrata("FULLSCREEN_DIALOG")
    b:SetFrameLevel(20)
    b:SetAlpha(1)
    b:Show()
  end
  for j = #list + 1, #m.buttons do m.buttons[j]:Hide() end
  m.count = #list
  m.sideways = sideways
  G.RefreshQuestWays()
  if GameTooltip:GetOwner() == owner then GameTooltip:Hide() end
  if G.mapMenu then G.mapMenu.idle = 0 end
  m.idle = 0
  m:Show()
  G.QuestWaysKeys(m)
  -- (with the controller: its focus on the first icon, the one next to the button)
  if G.QuestWaysPadOn() then
    local P = ns.Pad
    P.SetFocus(nil)
    P.SetFocus(m.buttons[1])
  end
  return m
end
function G.ToggleQuestWays(owner)
  if G.QuestWaysOpen() then
    G.CloseQuestWays()
    return false
  end
  return G.OpenQuestWays(owner) ~= nil
end

-- The controller ------------------------------------------------------------------------------------------------------

-- The controller in use on the map (its buttons bound, a pad pressed since the mouse was).
function G.QuestWaysPadOn()
  local P = ns.Pad
  return (P and P.bound and P.used and P.SetFocus) and true or false
end
-- The icon in the controller's focus (Pad's gold ring round it, its tooltip shown), or nil.
function G.QuestWaysSel()
  local P = ns.Pad
  local f = P and P.focus
  if not f then return nil end
  for _, b in ipairs(G.QuestWaysButtons()) do
    if b == f then return b end
  end
  return nil
end
-- The focus `step` icons on, round at the ends (none in focus: the first).
function G.QuestWaysMove(step)
  local list = G.QuestWaysButtons()
  local P = ns.Pad
  if #list == 0 or not (P and P.SetFocus) then return false end
  local at
  for i, b in ipairs(list) do
    if b == P.focus then at = i end
  end
  P.SetFocus(at and list[((at - 1 + step) % #list) + 1] or list[1])
  return true
end
-- Shut, the controller's focus back on the button that opened them.
function G.QuestWaysBack()
  local m = G.questWays
  local owner = m and m.owner
  G.CloseQuestWays()
  local P = ns.Pad
  if P and owner and owner:IsShown() and P.MenuOpen and P.MenuOpen() then
    P.SetFocus(nil) -- (its tooltip again, as the focus coming onto it shows)
    P.SetFocus(owner)
  end
  return true
end
-- A pad's controls while the icons are out (`has`: the pressed controls' ids, Pad.Run's): true when taken, nil to leave
-- them to the map menu's (Map menu: shut with it). As in Quick Find: up and right the next icon, down and left the one
-- before; A turns the one in focus on or off (they stay out), B or X shuts them.
function G.QuestWaysPad(has)
  if not G.QuestWaysOpen() then return nil end
  if has.panUp or has.panRight then return G.QuestWaysMove(1) end
  if has.panDown or has.panLeft then return G.QuestWaysMove(-1) end
  if has.select or has.yes or has.click then
    local b = G.QuestWaysSel()
    if not b then return G.QuestWaysMove(0) end
    local P = ns.Pad
    local owner = G.questWays.owner
    G.QuestWayPick(b.id)
    if G.QuestWaysOpen() then return true end -- (a toggle: still out, the focus where it was)
    -- (shut by Quest Route options or a question: the map menu still open, the focus back on the button; shut, the
    -- map's own marks)
    if P and P.MenuOpen and P.MenuOpen() then
      if owner and owner:IsShown() then P.SetFocus(owner) end
    elseif P then
      P.SetFocus(nil)
      if P.ShowMarks then P.ShowMarks(P.bound) end
    end
    return true
  end
  if has.back or has.remove then return G.QuestWaysBack() end
  if has.menu then
    G.CloseQuestWays()
    return nil
  end
  return true -- (the rest: nothing while they're out)
end
