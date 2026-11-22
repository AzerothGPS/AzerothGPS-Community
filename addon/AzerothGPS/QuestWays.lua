-- The Quest Route button's choices (asked 2026-11-22: "lets extend the quest route button with a sub menu to route in
-- different ways like by level, turn ins only, tracked quest only, etc"; then, for 1.3.14: "make these quick buttons
-- that can be toggled on/off. If any of them conflict with another auto turn it on/off like picking turn-ins only and
-- tracked quests only for example, only 1 should be on at a time or both off"). Right-click the button: a small menu
-- of ours, each entry a toggle with a check box: the player's saved Quest Route options (Options > Routing > Quest
-- Route is their home; this menu is a second control for them), and a left-click makes the route by them.
--
-- The toggles and their groups (at most one on in a group, or none):
--   Order: Lowest level first, About to turn gray first (`questLevelOrder` "low" / "gray"). Fastest order is neither:
--     on while neither is, turning it on turns both off (clicked while on it stays on: the others turn it off).
--   What's routed: Turn-ins only (`questTurninsOnly`), Objectives only (`questObjectivesOnly`), Tracked quests only
--     (`questTrackedOnly`): one turned on turns the other two off. The Options page's check boxes keep the same rule
--     (G.SetQuestToggle).
--   This zone only (`questZoneOnly`): its own, with anything.
-- A toggle clicked on a quest route makes it again at once with the new options; on any other route (or none) it's
-- only saved. The menu stays open for more; it shuts on a click anywhere else, the button again, B or Escape (Escape
-- shuts only the menu: not the map, nor the game's menu). Quests left out (Leave Out, a removed stop) stay out.
--
-- The menu is our own frame, never the game's menus (MenuUtil, dropdowns): with the game's controller UI on, the
-- game's menus with an addon's entries got AzerothGPS blocked (issue #887). /agps questroute <way> [off] turns a
-- toggle on (or off) as the menu does, then makes the quest route (a controller's macro).
--
-- With a controller (asked 2026-11-22 for 1.3.14: "add controller support for quest route sub menu, just fade between
-- the 2 buttons for activating and opening the submenu"): the button in the map menu's focus, its hint fades from the
-- button that presses it (Set Stop's, A) to the one that opens this menu (Remove's, X: its right-click) and back
-- (Pad.lua's HintTargets, SWAP_SECONDS). Open: the D-pad's up and down move a highlight of ours over the entries (round
-- at the ends), starting on the first; A toggles it (the menu stays open), B (or X again) shuts the menu, the focus
-- back on the button.
local _, ns = ...
local L = ns.L
local G = ns.GPS

-- Each toggle: `key` the setting it is (with `value`: on when the setting is that), `group` the ones of which at most
-- one is on.
G.QUEST_WAYS = {
  { id = "fastest", word = "fastest", label = L["Fastest order"], group = "order" },
  { id = "low", word = "low", label = L["Lowest level first"], key = "questLevelOrder", value = "low", group = "order" },
  { id = "gray", word = "gray", label = L["About to turn gray first"], key = "questLevelOrder", value = "gray",
    group = "order" },
  { id = "turnins", word = "turnins", label = L["Turn-ins only"], key = "questTurninsOnly", group = "what" },
  { id = "objectives", word = "objectives", label = L["Objectives only"], key = "questObjectivesOnly", group = "what" },
  { id = "tracked", word = "tracked", label = L["Tracked quests only"], key = "questTrackedOnly", group = "what" },
  { id = "zone", word = "zone", label = L["This zone only"], key = "questZoneOnly" },
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

-- The menu ---------------------------------------------------------------------------------------------------------

G.QUEST_WAYS_W, G.QUEST_WAYS_ROW, G.QUEST_WAYS_PAD, G.QUEST_WAYS_BOX = 210, 18, 5, 10

-- An entry clicked: a toggle flipped, the menu kept open; Quest Route options... shuts it and opens Options > Routing
-- at Quest Route.
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

local function Row(m, i)
  local row = CreateFrame("Button", nil, m)
  row:SetSize(G.QUEST_WAYS_W - 2 * G.QUEST_WAYS_PAD, G.QUEST_WAYS_ROW)
  row:RegisterForClicks("LeftButtonUp", "RightButtonUp")
  local hl = row:CreateTexture(nil, "HIGHLIGHT")
  hl:SetAllPoints()
  hl:SetColorTexture(1, 0.82, 0, 0.15)
  -- (the toggle's check box, drawn: an edge, its inside, and a gold fill while on)
  local B = G.QUEST_WAYS_BOX
  row.box = row:CreateTexture(nil, "ARTWORK")
  row.box:SetSize(B, B)
  row.box:SetPoint("LEFT", 5, 0)
  row.box:SetColorTexture(0.6, 0.55, 0.4, 1)
  row.boxIn = row:CreateTexture(nil, "ARTWORK", nil, 1)
  row.boxIn:SetPoint("TOPLEFT", row.box, "TOPLEFT", 1, -1)
  row.boxIn:SetPoint("BOTTOMRIGHT", row.box, "BOTTOMRIGHT", -1, 1)
  row.boxIn:SetColorTexture(0.08, 0.08, 0.08, 1)
  row.check = row:CreateTexture(nil, "ARTWORK", nil, 2)
  row.check:SetPoint("TOPLEFT", row.box, "TOPLEFT", 2, -2)
  row.check:SetPoint("BOTTOMRIGHT", row.box, "BOTTOMRIGHT", -2, 2)
  row.check:SetColorTexture(1, 0.82, 0, 1)
  row.check:Hide()
  row.text = row:CreateFontString(nil, "ARTWORK", "GameFontHighlightSmall")
  row.text:SetPoint("LEFT", B + 11, 0)
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
  -- (Escape shuts the menu only, taken from the game out of combat: not the map, nor the game's menu. Every other key
  -- goes on to the game; in combat the keys can't be taken, so Escape shuts it and goes on too: G.QuestWaysKey)
  m:SetScript("OnKeyDown", function(self, key) G.QuestWaysKey(self, key) end)
  m:Hide()
  return m
end
local function Combat() return (InCombatLockdown and InCombatLockdown()) and true or false end
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

-- The entries as shown: { id, text, on } (`on` nil: no check box), the toggles then Quest Route options...
function G.QuestWayRows()
  local out = {}
  for _, e in ipairs(G.QUEST_WAYS) do out[#out + 1] = { id = e.id, text = e.label, on = G.QuestToggleOn(e.id) } end
  out[#out + 1] = { id = "options", text = L["Quest Route options..."], gap = true }
  return out
end
-- The rows' texts and check boxes as the saved options are now (a toggle clicked, or one it turned off).
function G.RefreshQuestWays()
  local m = G.questWays
  if not m then return end
  for i, r in ipairs(G.QuestWayRows()) do
    local row = m.rows[i]
    if row then
      row.id = r.id
      row.on = r.on
      row.text:SetText(r.text)
      local box = r.on ~= nil
      row.box:SetShown(box)
      row.boxIn:SetShown(box)
      row.check:SetShown(r.on == true)
      row.text:SetPoint("LEFT", box and G.QUEST_WAYS_BOX + 11 or 6, 0)
    end
  end
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
    row:ClearAllPoints()
    row:SetPoint("TOPLEFT", P, y)
    row:Show()
    y = y - R
  end
  m:SetHeight(-y + P)
  G.RefreshQuestWays()
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
  G.QuestWaysKeys(m)
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

-- The entry the highlight starts on: the first.
function G.QuestWaysStart()
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
    if G.QuestWaysOpen() then return true end -- (a toggle: the menu stays open, the highlight where it was)
    -- (shut by Quest Route options... or a question: the map menu still open, the focus back on the button; shut, the
    -- map's own marks)
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
