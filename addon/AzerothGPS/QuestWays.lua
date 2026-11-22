-- The Quest Route button's other ways (asked 2026-11-22: "lets extend the quest route button with a sub menu to route
-- in different ways like by level, turn ins only, tracked quest only, etc"). Right-click the button: a small menu of
-- ours, each entry a quest route made at once in that way, for that route only: the saved Quest Route options
-- (Options > Routing > Quest Route) are left as they are, and a left-click is the route by them as before.
--
-- Each way sets only its own part; the rest is the player's saved choice:
--   Fastest order (all quests): no level order, every zone, tracked or not.
--   Lowest level first / About to turn gray first: that level order (Nav.QuestBands).
--   Turn-ins only: just the finished quests' turn-ins. Objectives only: no turn-ins.
--   Tracked quests only / This zone only: that filter on.
-- Quests left out (Leave Out, a removed stop) stay out whichever way. The way is the route's (Nav.questWay, saved with
-- it): its reorders (a turn-in, a level-up) and its remakes (the Sprint icon, by itself, Put Back) keep it; the
-- entries the player's own options give are marked "(default)".
--
-- The menu is our own frame, never the game's menus (MenuUtil, dropdowns): with the game's controller UI on, the
-- game's menus with an addon's entries got AzerothGPS blocked (issue #887). /agps questroute <way> makes the same
-- routes (a controller's macro).
--
-- With a controller (asked 2026-11-22 for 1.3.14: "add controller support for quest route sub menu, just fade between
-- the 2 buttons for activating and opening the submenu"): the button in the map menu's focus, its hint fades from the
-- button that presses it (Set Stop's, A) to the one that opens this menu (Remove's, X: its right-click) and back
-- (Pad.lua's HintTargets, SWAP_SECONDS). Open: the D-pad's up and down move a highlight of ours over the entries (round
-- at the ends), starting on the "(default)" one (or the first); A picks it, B (or X again) shuts the menu, the focus
-- back on the button.
local _, ns = ...
local L = ns.L
local G = ns.GPS

G.QUEST_WAYS = {
  { id = "fastest", word = "fastest", label = L["Fastest order (all quests)"],
    way = { level = "off", zone = false, tracked = false } },
  { id = "low", word = "low", label = L["Lowest level first"], way = { level = "low" } },
  { id = "gray", word = "gray", label = L["About to turn gray first"], way = { level = "gray" } },
  { id = "turnins", word = "turnins", label = L["Turn-ins only"], way = { only = "turnin" } },
  { id = "objectives", word = "objectives", label = L["Objectives only"], way = { only = "objectives" } },
  { id = "tracked", word = "tracked", label = L["Tracked quests only"], way = { tracked = true } },
  { id = "zone", word = "zone", label = L["This zone only"], way = { zone = true } },
}

local function Settings() return ns.settings and ns.settings.gps or {} end

function G.QuestWayEntry(id)
  for _, e in ipairs(G.QUEST_WAYS) do
    if e.id == id then return e end
  end
  return nil
end
-- The way `id` for Nav.questWay: { id, level, zone, tracked, only } with only its own parts set; nil when unknown.
function G.QuestWayOf(id)
  local e = G.QuestWayEntry(id)
  if not e then return nil end
  local w = { id = e.id }
  for k, v in pairs(e.way) do w[k] = v end
  return w
end
-- The way the quest route now was made by (its remakes keep it), or nil: the saved options.
function G.QuestWayNow()
  local N = ns.Nav
  local w = N and N.questWay
  return (w and N.OnQuestRoute() and G.QuestWayEntry(w.id)) and w.id or nil
end
-- `stops` (Layers.QuestStops') with only the turn-ins (`only` "turnin") or none of them ("objectives").
function G.QuestWayStops(stops, only)
  local out = {}
  for _, d in ipairs(stops) do
    if (only == "turnin") == (d.turnin and true or false) then out[#out + 1] = d end
  end
  return out
end
-- Whether entry `e` is what a left-click does (the saved options): the level order picked, each filter on; Fastest
-- order with none of them.
function G.QuestWayIsDefault(e)
  local st = Settings()
  local level = st.questLevelOrder
  if level ~= "low" and level ~= "gray" then level = "off" end
  if e.id == "fastest" then return level == "off" and not st.questZoneOnly and not st.questTrackedOnly end
  if e.id == "low" or e.id == "gray" then return level == e.id end
  if e.id == "tracked" then return st.questTrackedOnly and true or false end
  if e.id == "zone" then return st.questZoneOnly and true or false end
  return false
end
function G.QuestWayLabel(e)
  if G.QuestWayIsDefault(e) then return e.label .. " |cff9d9d9d" .. L["(default)"] .. "|r" end
  return e.label
end
-- /agps questroute <word>: the way by its word (fastest, low, gray, turnins, objectives, tracked, zone), or nil.
function G.QuestWayByWord(word)
  word = tostring(word or ""):lower()
  if word == "grey" then word = "gray" end
  for _, e in ipairs(G.QUEST_WAYS) do
    if e.word == word then return e.id end
  end
  return nil
end

-- The menu ---------------------------------------------------------------------------------------------------------

G.QUEST_WAYS_W, G.QUEST_WAYS_ROW, G.QUEST_WAYS_PAD = 210, 18, 5

-- An entry picked: the menu shut, then its quest route ("options": Options > Routing at Quest Route).
function G.QuestWayPick(id)
  G.CloseQuestWays()
  if id == "options" then
    local O = ns.Options
    if O and O.ShowSettingsAt then O.ShowSettingsAt("Routing", L["Quest Route"]) end
    return true
  end
  G.QuestRoute(id)
  return true
end

local function Row(m, i)
  local row = CreateFrame("Button", nil, m)
  row:SetSize(G.QUEST_WAYS_W - 2 * G.QUEST_WAYS_PAD, G.QUEST_WAYS_ROW)
  row:RegisterForClicks("LeftButtonUp", "RightButtonUp")
  local hl = row:CreateTexture(nil, "HIGHLIGHT")
  hl:SetAllPoints()
  hl:SetColorTexture(1, 0.82, 0, 0.15)
  row.text = row:CreateFontString(nil, "ARTWORK", "GameFontHighlightSmall")
  row.text:SetPoint("LEFT", 6, 0)
  row.text:SetPoint("RIGHT", -4, 0)
  row.text:SetJustifyH("LEFT")
  row.text:SetWordWrap(false)
  row:SetScript("OnClick", function(self) if self.id then G.QuestWayPick(self.id) end end)
  m.rows[i] = row
  return row
end

local function Build()
  local m = CreateFrame("Frame", nil, UIParent)
  m:SetFrameStrata("FULLSCREEN_DIALOG")
  m:SetFrameLevel(20)
  m:SetClampedToScreen(true)
  m:EnableMouse(true)
  m:SetWidth(G.QUEST_WAYS_W)
  local edge = m:CreateTexture(nil, "BACKGROUND", nil, -1)
  edge:SetPoint("TOPLEFT", -1, 1)
  edge:SetPoint("BOTTOMRIGHT", 1, -1)
  edge:SetColorTexture(0.55, 0.45, 0.2, 0.95)
  local bg = m:CreateTexture(nil, "BACKGROUND")
  bg:SetAllPoints()
  bg:SetColorTexture(0.04, 0.04, 0.04, 0.97)
  m.title = m:CreateFontString(nil, "ARTWORK", "GameFontNormalSmall")
  m.title:SetPoint("TOPLEFT", G.QUEST_WAYS_PAD + 6, -G.QUEST_WAYS_PAD - 3)
  m.title:SetText(L["Quest Route"])
  m.line = m:CreateTexture(nil, "ARTWORK")
  m.line:SetHeight(1)
  m.line:SetColorTexture(1, 0.82, 0, 0.25)
  m.rows = {}
  -- (the controller's highlight: the entry A picks)
  m.sel = m:CreateTexture(nil, "ARTWORK", nil, 1)
  m.sel:SetColorTexture(1, 0.82, 0, 0.3)
  m.sel:Hide()
  -- (a click anywhere else shuts it: under the menu, over everything else)
  local catch = CreateFrame("Button", nil, m)
  catch:SetFrameStrata("FULLSCREEN_DIALOG")
  catch:SetFrameLevel(1)
  catch:SetAllPoints(UIParent)
  catch:RegisterForClicks("LeftButtonUp", "RightButtonUp")
  catch:SetScript("OnClick", function() G.CloseQuestWays() end)
  m.catch = catch
  -- (shut with its button: the map closed, the map menu shut; open, the map menu stays open)
  m:SetScript("OnUpdate", function(self)
    local b = self.owner
    if not (b and b:IsVisible()) then G.CloseQuestWays() return end
    if G.mapMenu then G.mapMenu.idle = 0 end
    G.QuestWaysShowSel() -- (the highlight: the controller's only, gone while the mouse is in use)
  end)
  if ns.TimeScript then ns.TimeScript(m, "OnUpdate", "map buttons") end
  m:Hide()
  return m
end

-- The entries as shown: { id, text }, the ways then Quest Route options...
function G.QuestWayRows()
  local out = {}
  for _, e in ipairs(G.QUEST_WAYS) do out[#out + 1] = { id = e.id, text = G.QuestWayLabel(e) } end
  out[#out + 1] = { id = "options", text = L["Quest Route options..."], gap = true }
  return out
end

function G.QuestWaysOpen()
  return (G.questWays and G.questWays:IsShown()) and true or false
end
function G.CloseQuestWays()
  local m = G.questWays
  if m and m:IsShown() then m:Hide() end
end
-- Open beside `owner` (the Quest Route button): right of it in a column going up, above it in a row going right.
function G.OpenQuestWays(owner)
  owner = owner or G.questRouteButton
  if not owner then return nil end
  G.questWays = G.questWays or Build()
  local m = G.questWays
  m.owner = owner
  local P, R = G.QUEST_WAYS_PAD, G.QUEST_WAYS_ROW
  local y = -P - R
  for i, r in ipairs(G.QuestWayRows()) do
    if r.gap then
      m.line:ClearAllPoints()
      m.line:SetPoint("TOPLEFT", P + 4, y - 3)
      m.line:SetPoint("TOPRIGHT", -P - 4, y - 3)
      y = y - 7
    end
    local row = m.rows[i] or Row(m, i)
    row.id = r.id
    row.text:SetText(r.text)
    row:ClearAllPoints()
    row:SetPoint("TOPLEFT", P, y)
    row:Show()
    y = y - R
  end
  m:SetHeight(-y + P)
  local where
  for _, t in ipairs(G.QUICK or {}) do
    if t.id == "questRoute" then where = t.where end
  end
  m:ClearAllPoints()
  if where == "barRight" or where == "menuRight" then
    m:SetPoint("BOTTOMLEFT", owner, "TOPLEFT", 0, 4)
  else
    m:SetPoint("BOTTOMLEFT", owner, "BOTTOMRIGHT", 4, 0)
  end
  if GameTooltip:GetOwner() == owner then GameTooltip:Hide() end
  if G.mapMenu then G.mapMenu.idle = 0 end
  m.count = #G.QuestWayRows()
  m.at = G.QuestWaysStart()
  m:Show()
  G.QuestWaysShowSel()
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

-- The entry the highlight starts on: the first marked "(default)", else the first.
function G.QuestWaysStart()
  for i, e in ipairs(G.QUEST_WAYS) do
    if G.QuestWayIsDefault(e) then return i end
  end
  return 1
end
-- The controller in use on the map (its buttons bound, a pad pressed since the mouse was).
function G.QuestWaysPadOn()
  local P = ns.Pad
  return (P and P.bound and P.used) and true or false
end
-- The highlighted entry's row (shown), or nil.
function G.QuestWaysSelRow()
  local m = G.questWays
  if not (m and m:IsShown() and m.at) then return nil end
  local row = m.rows[m.at]
  return (row and row:IsShown()) and row or nil
end
function G.QuestWaysShowSel()
  local m = G.questWays
  if not m then return end
  local row = G.QuestWaysPadOn() and G.QuestWaysSelRow() or nil
  if row then
    if m.sel.row ~= row then
      m.sel:ClearAllPoints()
      m.sel:SetAllPoints(row)
      m.sel.row = row
    end
    m.sel:Show()
  else
    m.sel:Hide()
  end
end
-- the highlight `step` entries on, round at the ends
function G.QuestWaysMove(step)
  local m = G.questWays
  if not (m and m:IsShown()) then return false end
  local n = m.count or #G.QuestWayRows()
  if n == 0 then return false end
  m.at = (((m.at or G.QuestWaysStart()) - 1 + step) % n) + 1
  G.QuestWaysShowSel()
  return true
end
-- Shut, the controller's focus back on the button that opened it.
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
-- A pad's controls while the menu is open (`has`: the pressed controls' ids, Pad.Run's): true when taken, nil to leave
-- them to the map menu's (Map menu: the menu shut with it).
function G.QuestWaysPad(has)
  if not G.QuestWaysOpen() then return nil end
  if has.panUp then return G.QuestWaysMove(-1) end
  if has.panDown then return G.QuestWaysMove(1) end
  if has.select or has.yes or has.click then
    local row = G.QuestWaysSelRow()
    if not row then return G.QuestWaysMove(0) end
    local P = ns.Pad
    local owner = G.questWays.owner
    G.QuestWayPick(row.id)
    -- (the map menu still open: the focus back on the button; shut, the map's own marks)
    if P and P.MenuOpen and P.MenuOpen() then
      if owner and owner:IsShown() and not G.QuestWaysOpen() then P.SetFocus(owner) end
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
  return true -- (the rest: nothing while the menu is open)
end
