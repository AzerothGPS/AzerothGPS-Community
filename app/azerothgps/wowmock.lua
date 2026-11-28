-- A stand-in for the game's UI for tests that run the addon's frames (test_map_redraw.py): every
-- frame, texture and font string is a widget taking any call. Setters do nothing (or remember what
-- a getter gives back), getters give numbers, strings or other widgets as the game's would.
-- Enough to run the map's setup and redraw; not a check of how anything looks.

AGPS_WIDGETS = {}
local M = {}
local WMT
local numeric = {
  GetWidth = 400, GetHeight = 400, GetEffectiveScale = 1, GetScale = 1, GetStringHeight = 12,
  GetStringWidth = 40, GetUnboundedStringWidth = 40, GetAlpha = 1, GetEffectiveAlpha = 1,
  GetFrameLevel = 5, GetLeft = 100, GetRight = 500, GetTop = 500, GetBottom = 100, GetNumPoints = 1,
  GetLineHeight = 12, GetValue = 0, GetID = 0, GetNumChildren = 0, GetVerticalScroll = 0,
  GetHorizontalScroll = 0, GetTextWidth = 40, GetTextHeight = 12, GetNumLines = 0, GetSpacing = 0,
  GetDrawLayer = 0, GetThickness = 2, GetVerticalScrollRange = 0, GetMaxLetters = 0, GetNumLetters = 0,
  GetCursorPosition = 0, GetDuration = 0, GetProgress = 0, GetElapsed = 0, GetOrder = 1, GetSmoothing = 0,
}

function NewWidget(kind, name, parent)
  local w = setmetatable({ _kind = kind or "Frame", _scripts = {}, _shown = true, _attr = {}, _events = {},
    _parent = parent, _name = name, _text = "" }, WMT)
  AGPS_WIDGETS[#AGPS_WIDGETS + 1] = w
  if name then _G[name] = w end
  return w
end

M.SetScript = function(s, n, f) s._scripts[n] = f end
M.GetScript = function(s, n) return s._scripts[n] end
M.HookScript = function(s, n, f)
  local o = s._scripts[n]
  s._scripts[n] = function(...)
    if o then o(...) end
    return f(...)
  end
end
M.HasScript = function() return true end
M.Show = function(s) s._shown = true end
M.Hide = function(s) s._shown = false end
M.SetShown = function(s, v) s._shown = v and true or false end
M.IsShown = function(s) return s._shown end
M.IsVisible = function(s) return s._shown end
M.SetEnabled = function(s, v) s._enabled = v and true or false end -- (recorded)
M.IsEnabled = function(s) return s._enabled ~= false end -- (as set: enabled unless disabled)
M.Enable = function(s) s._enabled = true end
M.SetMotionScriptsWhileDisabled = function(s, v) s._motionWhileDisabled = v and true or false end -- (recorded: the game
-- sends a disabled button no OnEnter/OnLeave without it)
M.Disable = function(s) s._enabled = false end
M.RegisterEvent = function(s, e) s._events[e] = true end
M.RegisterUnitEvent = M.RegisterEvent
M.UnregisterEvent = function(s, e) s._events[e] = nil end
M.UnregisterAllEvents = function(s) s._events = {} end
M.IsEventRegistered = function(s, e) return s._events[e] or false end
M.SetText = function(s, t) s._text = t end
M.SetMaxLetters = function(s, n) s._maxLetters = n end -- (recorded: the limits of an edit box)
M.GetMaxLetters = function(s) return s._maxLetters or 0 end
M.GetText = function(s) return s._text end
M.SetFormattedText = function(s, f, ...) s._text = string.format(f, ...) end
M.SetAttribute = function(s, k, v) s._attr[k] = v end
M.RegisterForClicks = function(s, ...) s._clicks = { ... } end -- (recorded: a secure button's halves)
M.GetAttribute = function(s, k) return s._attr[k] end
M.GetParent = function(s) -- (UIParent has none: a walk up the frames ends, as the stitched map's Live.Under does)
  if s == UIParent then return nil end
  return s._parent or UIParent
end
M.SetParent = function(s, p) -- (as the game: off the old parent's children, onto the new one's)
  local old = s._parent
  if old == p then return end
  if old and old._kids then
    for i = #old._kids, 1, -1 do if old._kids[i] == s then table.remove(old._kids, i) end end
  end
  s._parent = p
  if p then
    p._kids = p._kids or {}
    p._kids[#p._kids + 1] = s
  end
end
M.GetName = function(s) return s._name end
M.GetObjectType = function(s) return s._kind end
M.IsObjectType = function(s, k) return s._kind == k end
M.GetCenter = function() return 300, 300 end
M.GetPoint = function() return "CENTER", nil, "CENTER", 0, 0 end
M.GetSize = function() return 400, 400 end
M.GetRect = function() return 100, 100, 400, 400 end
M.SetFrameStrata = function(s, v) s._strata = v end -- (recorded)
M.SetAlpha = function(s, a) s._alpha = a end -- (recorded; GetAlpha stays the stand-in's)
M.GetFrameStrata = function(s) return s._strata or "MEDIUM" end
M.GetChecked = function(s) return s._checked or false end
M.SetChecked = function(s, v) s._checked = v end
-- The client asserts `flags.m_filter <= GxTex_Linear` and crashes on any filter mode above LINEAR
-- ("TRILINEAR" did, 1.60.1.70124, 2026-10-01): the stand-in fails the same way.
local function FilterOK(filter)
  if filter ~= nil and filter ~= "LINEAR" and filter ~= "NEAREST" then
    error("ASSERT(flags.m_filter <= GxTex_Linear): filter mode " .. tostring(filter) .. " crashes the client", 3)
  end
end
M.SetScale = function(s, k) s._scale = k end
M.GetScale = function(s) return s._scale or 1 end
M.SetSize = function(s, w, h) s._w, s._h = w, h end -- (recorded; GetSize stays the stand-in's)
M.SetWidth = function(s, w) s._w = w end -- (recorded)
M.SetHeight = function(s, h) s._h = h end -- (recorded)
M.SetVerticalScroll = function(s, v) s._vs = v end
M.GetVerticalScroll = function(s) return s._vs or 0 end
M.SetPoint = function(s, ...) -- (the last one; and each by its point since ClearAllPoints)
  s._pt = { ... }
  s._pts = s._pts or {}
  s._pts[(...)] = { ... }
end
M.ClearAllPoints = function(s) s._pts = {} end
M.SetJustifyH = function(s, j) s._justify = j end -- (recorded)
M.SetFrameLevel = function(s, l) s._level = l end -- (recorded; GetFrameLevel stays the stand-in's)
M.EnableKeyboard = function(s, v) s._keyboard = v end -- (recorded)
M.SetPropagateKeyboardInput = function(s, v) s._propagate = v end -- (recorded)
M.GetPropagateKeyboardInput = function(s) return s._propagate or false end
M.SetWordWrap = function(s, w) s._wrap = w end -- (recorded)
M.SetTexture = function(s, t, _, _, filter) FilterOK(filter) s._tex, s._filter = t, filter end
M.SetAtlas = function(s, a, _, filter) FilterOK(filter) s._atlas, s._filter = a, filter end
M.GetTexture = function(s) return s._tex end
M.AddMaskTexture = function(s, m) s._masks = s._masks or {} s._masks[#s._masks + 1] = m end
M.RemoveMaskTexture = function(s, m)
  for i = #(s._masks or {}), 1, -1 do
    if s._masks[i] == m then table.remove(s._masks, i) end
  end
end
M.SetColorTexture = function(s, r, g, b) s._tex = string.format("color:%.2f,%.2f,%.2f", r, g, b) end
M.SetVertexColor = function(s, r, g, b) s._vc = string.format("%.2f,%.2f,%.2f", r, g, b) s._grad = nil end -- (recorded)
M.SetGradient = function(s, o, a, b) s._grad = { o, a.a, b.a } end -- (recorded: the orientation, the two ends' alpha)
M.SetDesaturated = function(s, d) s._desat = d and true or false end -- (recorded)
M.IsDesaturated = function(s) return s._desat or false end
M.SetThickness = function(s, t) s._thick = t end -- (recorded)
M.SetTexCoord = function(s, ...) s._coords = { ... } end -- (recorded)
M.SetDrawLayer = function(s, layer, sub) s._layer, s._sub = layer, sub end -- (recorded)
-- (recorded; false for a file in AGPS_MISSING_FONTS, as the game says when a font file does not load)
M.SetFont = function(s, f, size, flags)
  if AGPS_MISSING_FONTS and AGPS_MISSING_FONTS[f] then return false end
  s._font = { f, size, flags }
  return true
end
-- (a font string's template is its font object; set again, it takes that one's font: the file set by SetFont goes)
M.CreateFontString = function(s, name, layer, template)
  local w = NewWidget("FontString", name, s)
  w._fontObject = template
  return w
end
M.SetFontObject = function(s, o) s._fontObject, s._font = o, nil end
M.GetFontObject = function(s) return s._fontObject end
M.SetShadowOffset = function(s, x, y) s._shadowOffset = { x, y } end -- (recorded)
M.GetShadowOffset = function(s) local o = s._shadowOffset or { 1, -1 } return o[1], o[2] end
M.SetShadowColor = function(s, r, g, b, a) s._shadowColor = { r, g, b, a } end -- (recorded)
M.GetShadowColor = function(s) local c = s._shadowColor or { 0, 0, 0, 1 } return c[1], c[2], c[3], c[4] end
M.SetTextScale = function(s, k) s._textScale = k end -- (recorded: Arrow.lua scales its text so)
M.GetTextScale = function(s) return s._textScale or 1 end
M.GetFont = function(s)
  if s._font then return s._font[1], s._font[2], s._font[3] end
  return "Fonts\\FRIZQT__.TTF", 12, ""
end
M.GetTextColor = function() return 1, 1, 1, 1 end
M.GetVertexColor = function() return 1, 1, 1, 1 end
M.GetTexCoord = function() return 0, 0, 0, 1, 1, 0, 1, 1 end
M.GetStartPoint = function() return "CENTER", nil, 0, 0 end
M.GetEndPoint = function() return "CENTER", nil, 0, 0 end
M.GetMinMaxValues = function() return 0, 1 end
M.GetHitRectInsets = function(s) local h = s._hitInsets or {} return h[1] or 0, h[2] or 0, h[3] or 0, h[4] or 0 end
M.SetHitRectInsets = function(s, l, r, t, b) s._hitInsets = { l, r, t, b } end
M.SetClampRectInsets = function(s, l, r, t, b) s._clamp = { l, r, t, b } end -- (recorded)
M.GetClampRectInsets = function(s)
  local c = s._clamp or { 0, 0, 0, 0 }
  return c[1], c[2], c[3], c[4]
end
M.GetChildren = function(s) return unpack(s._kids or {}) end -- (the frames made with it as their parent)
M.GetRegions = function() end
M.GetAnimationGroups = function() end
M.SetBackdropColor = function(s, r, g, b, a) s._bg = { r, g, b, a } end -- (recorded)
M.GetBackdropColor = function(s)
  local c = s._bg or { 0, 0, 0, 0 }
  return c[1], c[2], c[3], c[4]
end
M.GetBackdropBorderColor = function() return 0, 0, 0, 0 end
M.GetBackdrop = function() return nil end
M.GetOwner = function(s) return s._owner end
M.SetOwner = function(s, o, a) s._owner = o s._anchor = a end
M.GetAnchorType = function(s) return s._anchor end
M.SetAnchorType = function(s, a) s._anchor = a end
M.GetUnit = function() return nil end
M.GetSpell = function() return nil end
M.GetItem = function() return nil end
M.NumLines = function() return 0 end
M.GetCursorPosition = function() return 0 end
M.GetJustifyH = function(s) return s._justify or "LEFT" end
M.GetButtonState = function() return "NORMAL" end
M.SetMinMaxValues = function(s, a, b) s._minmax = { a, b } end -- (recorded)

local VERB = { "Set", "Get", "Is", "Can", "Create", "Enable", "Disable", "Register", "Unregister", "Show", "Hide",
  "Clear", "Start", "Stop", "Play", "Pause", "Raise", "Lower", "Add", "Remove", "Hook", "Lock", "Unlock", "Click",
  "Update", "Refresh", "Apply", "Scroll", "Adjust", "Reset", "Toggle", "Highlight", "Unhighlight", "Finish",
  "Restart", "Flash", "Stretch", "Fade", "Append", "Insert", "Execute", "Enable", "Has", "Num", "Wrap", "Intersects",
  "Rotate", "Load", "Save", "Cancel", "Run", "Fire" }

WMT = { __index = function(_, k)
  local m = M[k]
  if m then return m end
  if type(k) ~= "string" then return nil end
  local n = numeric[k]
  if n then return function() return n end end
  if k:match("^Create") then return function(s, ...) return NewWidget(k:sub(7), nil, s) end end
  if k:match("^Get") then return function(s) return NewWidget("child", nil, s) end end
  if k:match("^Is") or k:match("^Can") or k:match("^Has") then return function() return false end end
  for _, v in ipairs(VERB) do
    if k:sub(1, #v) == v then return function() end end
  end
  return nil -- (a field: the template's parts, the addon's own)
end }

function CreateFrame(kind, name, parent, template)
  -- (AGPS_NO_MENUS: a client without Blizzard_Menu's dropdowns, for Options.lua's own)
  if kind == "DropdownButton" and AGPS_NO_MENUS then error("CreateFrame: unknown frame type DropdownButton") end
  local w = NewWidget(kind, name, parent)
  if type(parent) == "table" then
    parent._kids = parent._kids or {}
    parent._kids[#parent._kids + 1] = w
  end
  -- (a template's parts the addon reaches for)
  if template and template:find("ScrollFrame") then w.ScrollBar = NewWidget("Slider", nil, w) end
  if template and template:find("UIPanelButtonTemplate") then -- (its three pieces: left end, middle, right end)
    w.Left, w.Middle, w.Right = NewWidget("Texture", nil, w), NewWidget("Texture", nil, w), NewWidget("Texture", nil, w)
  end
  return w
end
-- (a button's textures: the same one each time, as the game's)
for _, k in ipairs({ "Normal", "Pushed", "Disabled", "Highlight" }) do
  M["Get" .. k .. "Texture"] = function(s)
    s["_" .. k] = s["_" .. k] or NewWidget("Texture", nil, s)
    return s["_" .. k]
  end
end
-- The client's menu dropdowns (Blizzard_Menu's WowStyle1DropdownTemplate: Options.lua's Dropdown): SetupMenu's
-- generator run on a root recording its titles and radios; `_menu` the list, `_choice` the selected radio's text (the
-- dropdown's text, as the game shows it), `_scroll` its scroll height.
M.SetupMenu = function(s, gen)
  s._gen = gen
  s:GenerateMenu()
end
M.GenerateMenu = function(s)
  if not s._gen then return end
  local items, root = {}, {}
  function root:SetScrollMode(h) s._scroll = h end
  function root:CreateTitle(text) items[#items + 1] = { kind = "title", text = text } end
  function root:CreateRadio(text, isSelected, setSelected)
    local d = { kind = "radio", text = text, isSelected = isSelected, setSelected = setSelected }
    function d:SetTooltip(fn) self.tooltip = fn end
    items[#items + 1] = d
    return d
  end
  s._gen(s, root)
  s._menu, s._choice = items, nil
  for _, it in ipairs(items) do
    if it.kind == "radio" and it.isSelected() then s._choice = it.text end
  end
end
-- Pick the radio called `text` in a dropdown's menu, as a click would (an error for none).
function AGPS_PICK(dd, text)
  dd:GenerateMenu()
  for _, it in ipairs(dd._menu) do
    if it.kind == "radio" and it.text == text then return it.setSelected() end
  end
  error("no choice " .. tostring(text))
end
-- A dropdown's radios' texts, in order.
function AGPS_MENU(dd)
  dd:GenerateMenu()
  local out = {}
  for _, it in ipairs(dd._menu) do
    if it.kind == "radio" then out[#out + 1] = it.text end
  end
  return out
end
M.SetScrollChild = function(s, c) s._child = c end
M.GetScrollChild = function(s) return s._child end

-- Every script of `event` on every frame registered for it.
function AGPS_FIRE(event, ...)
  for _, w in ipairs(AGPS_WIDGETS) do
    if w._events[event] and w._scripts.OnEvent then w._scripts.OnEvent(w, event, ...) end
  end
end

UIParent = NewWidget("Frame", "UIParent")
-- (the screen, in UI units: a 1920 x 1080 one, not every widget's 400 x 400; a test sets its own with
-- UIParent.GetWidth / GetHeight, and setting them back to nil gives this again)
local SCREEN = { GetWidth = 1920, GetHeight = 1080 }
setmetatable(UIParent, { __index = function(s, k)
  local n = SCREEN[k]
  if n then return function() return n end end
  return WMT.__index(s, k)
end })
WorldFrame = NewWidget("Frame", "WorldFrame")
Minimap = NewWidget("Minimap", "Minimap")
WorldMapFrame = NewWidget("Frame", "WorldMapFrame")
GameTooltip = NewWidget("GameTooltip", "GameTooltip")
UIErrorsFrame = NewWidget("MessageFrame", "UIErrorsFrame")
DEFAULT_CHAT_FRAME = NewWidget("ScrollingMessageFrame", "DEFAULT_CHAT_FRAME")
GameTooltip_Hide = function() end
GameTooltip_SetTitle = function(t, text) t._title = text end -- (the game's menus' tooltips use these)
GameTooltip_AddNormalLine = function(t, text) t._line = text end
UISpecialFrames = {}
SlashCmdList = {}
StaticPopupDialogs = {}
StaticPopup_Show = function() end
YES, NO, OKAY, CANCEL = "Yes", "No", "Okay", "Cancel"

AGPS_T = 100
GetTime = function() return AGPS_T end
debugprofilestop = function() return os.clock() * 1000 end
C_Timer = { After = function() end,
  NewTicker = function() return { Cancel = function() end } end,
  NewTimer = function() return { Cancel = function() end } end }
GetCursorPosition = function() return 0, 0 end
InCombatLockdown = function() return false end
IsShiftKeyDown = function() return false end
IsControlKeyDown = function() return false end
IsAltKeyDown = function() return false end
IsMouseButtonDown = function() return false end
GetFramerate = function() return 60 end
GetLocale = function() return "enUS" end
GetBuildInfo = function() return "1.60.1", "70124", "Sep 1 2026", 16001 end
GetRealmName = function() return "Realm" end
UnitName = function() return "Tester" end
UnitIsPlayer = function(unit) return unit == "player" end -- (the Import and Share window: your target, a player?)
UnitIsUnit = function(a, b) return a == b end
-- (AGPS_GUIDS[unit]: a test's other units, "target" an NPC; else the player's)
UnitGUID = function(unit) return AGPS_GUIDS and AGPS_GUIDS[unit] or "Player-1-00000001" end
-- The game's protected (and, in this client, restricted) unit calls: an addon calling one is blocked in game. Here each
-- call is listed in AGPS_PROTECTED and fails, so a test sees it (AzerothGPS targets nothing by itself: the Target
-- button's secure macro, the player's own click, does).
AGPS_PROTECTED = {}
for _, f in ipairs({ "TargetUnit", "FocusUnit", "AssistUnit", "InteractUnit", "SetRaidTarget", "ClearRaidMarker",
  "PlaceRaidMarker", "RunMacroText" }) do
  _G[f] = function() AGPS_PROTECTED[#AGPS_PROTECTED + 1] = f error(f .. " is protected: blocked from an addon", 2) end
end
UnitFactionGroup = function() return "Horde" end
UnitRace = function() return "Undead", "Scourge" end
UnitClass = function() return "Mage", "MAGE" end
UnitLevel = function() return AGPS_LEVEL or 14 end
-- (this client hides the player's current health from addons, out of combat too: UnitHealth is a secret value,
-- its max isn't; probed in game 2026-10-08. So Nav.SafeDrop is FALL_FREE in game, and here)
AGPS_SECRET = setmetatable({}, { __tostring = function() return "<secret>" end })
UnitHealth = function() return AGPS_SECRET end
UnitHealthMax = function() return 430 end
UnitIsDeadOrGhost = function() return false end
UnitIsGhost = function() return false end
UnitOnTaxi = function() return false end
UnitAffectingCombat = function() return false end
UnitBuff = function() return nil end
UnitAura = function() return nil end
AGPS_POS = { 2254.0, 293.0, 0 } -- world x, y, continent (Brill)
UnitPosition = function() return AGPS_POS[1], AGPS_POS[2], AGPS_POS[4] or 0, AGPS_POS[3] end -- (4: the height, when set)
GetPlayerFacing = function() return 0 end
CreateColor = function(r, g, b, a) return { r = r, g = g, b = b, a = a } end -- (ColorMixin's values)
GetUnitSpeed = function() return 0, 7, 7, 4.7 end
IsMounted = function() return false end
IsFlying = function() return false end
IsSwimming = function() return false end
IsIndoors = function() return false end
IsSwimming = function() return AGPS_SWIMMING == true end -- (AGPS_SWIMMING: a test's swimmer)
IsResting = function() return false end
IsInInstance = function() return false, "none" end
GetInstanceInfo = function() return "Eastern Kingdoms", "none", 0, "", 5, 0, false, 0, 0 end
GetZoneText = function() return "Tirisfal Glades" end
GetRealZoneText = GetZoneText
GetSubZoneText = function() return "Brill" end
GetMinimapZoneText = function() return "Brill" end
GetBindLocation = function() return "Gallows' End Tavern" end
GetItemCount = function() return 0 end
GetItemCooldown = function() return 0, 0, 1 end
GetItemInfo = function() return nil end
GetItemIcon = function() return 134400 end
GetSpellCooldown = function() return 0, 0, 1 end
IsPlayerSpell = function() return false end
IsSpellKnown = function() return false end
GetSpellTexture = function() return 134400 end
GetNumSkillLines = function() return 0 end
PlaySound = function() end
PlaySoundFile = function() end
hooksecurefunc = function() end
-- chat message filters and EventRegistry callbacks, kept for the tests to call (AGPS_CHAT_FILTERS[event],
-- AGPS_CALLBACKS[event]: lists of functions)
AGPS_CHAT_FILTERS, AGPS_CALLBACKS = {}, {}
ChatFrame_OpenChat = function(text) AGPS_CHAT_OPENED = text end -- (a chat box opened with text, unsent)
ChatFrame_AddMessageEventFilter = function(event, fn)
  AGPS_CHAT_FILTERS[event] = AGPS_CHAT_FILTERS[event] or {}
  table.insert(AGPS_CHAT_FILTERS[event], fn)
end
EventRegistry = { RegisterCallback = function(self, event, fn, owner)
  AGPS_CALLBACKS[event] = AGPS_CALLBACKS[event] or {}
  table.insert(AGPS_CALLBACKS[event], fn)
end }
SetOverrideBindingClick = function() end
ClearOverrideBindings = function() end
GetBindingKey = function() return nil end
SetBinding = function() end
SaveBindings = function() end
GetCurrentBindingSet = function() return 1 end
issecretvalue = function(v) return v ~= nil and v == AGPS_SECRET end
securecall = function(f, ...) return f(...) end
GetAddOnMetadata = function() return "1.0.8" end
C_AddOns = { GetAddOnMetadata = GetAddOnMetadata, IsAddOnLoaded = function() return false end }
IsAddOnLoaded = function() return false end
C_ChatInfo = { RegisterAddonMessagePrefix = function() return true end, SendAddonMessage = function() end }
RegisterAddonMessagePrefix = C_ChatInfo.RegisterAddonMessagePrefix
C_Container = { GetItemCooldown = function() return 0, 0, 1 end }
C_Spell = nil
C_TaxiMap = { GetAllTaxiNodes = function() return {} end, GetTaxiNodesForMap = function() return {} end }
NumTaxiNodes = function() return 0 end
C_QuestLog = { GetNumQuestLogEntries = function() return 0 end, GetInfo = function() return nil end,
  GetQuestsOnMap = function() return {} end, GetQuestObjectives = function() return {} end,
  IsComplete = function() return false end, GetLogIndexForQuestID = function() return nil end }
GetNumQuestLogEntries = function() return 0 end
C_QuestLine = { RequestQuestLinesForMap = function() end, GetAvailableQuestLines = function() return {} end }
C_Minimap = { IsInsideQuestBlob = function() return false end }
C_GossipInfo = { GetPoiForUiMapID = function() return nil end }
C_DeathInfo = { GetCorpseMapPosition = function() return nil end }
C_MapExplorationInfo = { GetExploredMapTextures = function() return {} end }
Enum = setmetatable({}, { __index = function() return setmetatable({}, { __index = function() return 0 end }) end })

-- The map API: the player in Tirisfal Glades, the continent's map for world coordinates.
C_Map = {
  GetBestMapForUnit = function() return AGPS_MAP or 1420 end,
  GetPlayerMapPosition = function() return { GetXY = function() return 0.6, 0.5 end } end,
  GetMapInfo = function(id)
    local m = AGPS_NS and AGPS_NS.Maps and AGPS_NS.Maps[id]
    return m and { mapID = id, name = m.name, mapType = m.type, parentMapID = m.parent } or nil
  end,
  GetMapLevels = function() return nil end,
  GetMapArtID = function() return nil end,
  GetMapGroupID = function() return nil end,
  GetMapChildrenInfo = function() return {} end,
  GetMapArtLayers = function() return {} end,
  GetMapArtLayerTextures = function() return {} end,
  GetMapInfoAtPosition = function() return nil end,
  GetWorldPosFromMapPos = function() return nil end,
  GetMapWorldSize = function() return 0, 0 end,
}

CopyTable = function(t)
  local o = {}
  for k, v in pairs(t) do o[k] = type(v) == "table" and CopyTable(v) or v end
  return o
end
tostringall = function(...)
  local out = {}
  for i = 1, select("#", ...) do out[i] = tostring((select(i, ...))) end
  return unpack(out, 1, select("#", ...))
end
-- (the icons a macro can have: the game fills the table it's given with file ids)
GetMacroIcons = function(t) for i = 1, 30 do t[#t + 1] = 136000 + i end end
GetMacroItemIcons = function(t) for i = 1, 25 do t[#t + 1] = 133000 + i end end
