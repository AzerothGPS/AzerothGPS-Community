-- Options window, minimap button, and the entry in the game's AddOns options.
local _, ns = ...
local L = ns.L or setmetatable({}, { __index = function(_, k) return k end }) -- (the game's language: Locales.lua)
local Format = ns.Format or string.format

local O = {}
ns.Options = O

local window
local controls = {} -- refresh functions, run when the window opens or settings change

local function GPS() return ns.settings.gps end

local function Apply()
  ns.GPS.ApplySettings()
  if ns.Arrow then ns.Arrow.Apply() end
  if ns.Looks then ns.Looks.Apply() end
  if O.button then O.UpdateButton() end
  for _, refresh in ipairs(controls) do refresh() end
end
O.Apply = Apply
-- refresh the window's controls (a setting changed elsewhere, e.g. a quick button)
function O.Refresh()
  for _, refresh in ipairs(controls) do refresh() end
end

---------------------------------------------------------------------------
-- Widgets (built from basic textures so they work on any client version)
---------------------------------------------------------------------------

-- Which setting each control changes (1.2.0): `Key("locked")` before making a control names it, and the control made
-- next is listed in O.settingControls as { key, page (the page's id), control, mirror }. The tests read it: every
-- setting has one control, on one page (a `mirror` is a second one kept on purpose: the Quick buttons' "On" column).
-- A control with an `enabled` function is gray while it returns false, and says so in `control.agpsOn`.
O.settingControls = {}
local trackKey, trackPage
local StartGroup -- (the search's groups: made in BuildWindow)
local function Key(key)
  trackKey = key
  if StartGroup then StartGroup("setting") end
end
local function Track(control, mirror)
  if not trackKey then return end
  O.settingControls[#O.settingControls + 1] = { key = trackKey, page = trackPage, control = control, mirror = mirror }
  trackKey = nil
end
local INDENT = 20 -- a dependent option, under its parent

-- `enabled` (optional): a function; the checkbox is grayed out while it returns false.
local function Checkbox(parent, label, tooltip, get, set, enabled)
  local cb = CreateFrame("CheckButton", nil, parent, "UICheckButtonTemplate")
  cb:SetSize(24, 24)
  local text = cb:CreateFontString(nil, "ARTWORK", "GameFontHighlight")
  text:SetPoint("LEFT", cb, "RIGHT", 2, 0)
  text:SetText(label)
  cb.label = text
  cb:SetScript("OnClick", function(self)
    set(self:GetChecked() and true or false)
    Apply()
  end)
  if tooltip then
    cb:SetScript("OnEnter", function(self)
      GameTooltip:SetOwner(self, "ANCHOR_RIGHT")
      GameTooltip:SetText(label, 1, 1, 1)
      GameTooltip:AddLine(tooltip, nil, nil, nil, true)
      GameTooltip:Show()
    end)
    cb:SetScript("OnLeave", GameTooltip_Hide)
  end
  controls[#controls + 1] = function()
    cb:SetChecked(get())
    if enabled then
      local on = enabled() and true or false
      cb.agpsOn = on
      cb:SetEnabled(on)
      text:SetFontObject(on and "GameFontHighlight" or "GameFontDisable")
    end
  end
  Track(cb)
  return cb
end

-- The key that shows and hides the map (Bindings.xml): click, then press a key (with
-- Shift/Ctrl/Alt if wanted); Escape cancels, right-click clears it. Saved like any other
-- key binding (also in the game's Key Bindings, under AddOns). Not in combat: the game
-- doesn't allow changing key bindings then.
O.BINDING = "AZEROTHGPS_TOGGLE"
local MODIFIER_KEYS = { LSHIFT = true, RSHIFT = true, LCTRL = true, RCTRL = true, LALT = true, RALT = true,
  LMETA = true, RMETA = true, UNKNOWN = true }

local function SaveKeys()
  if SaveBindings then SaveBindings(GetCurrentBindingSet and GetCurrentBindingSet() or 1) end
end

local function KeyBind(parent, label, binding, tip)
  binding = binding or O.BINDING
  local holder = CreateFrame("Frame", nil, parent)
  holder:SetSize(360, 26)
  local text = holder:CreateFontString(nil, "ARTWORK", "GameFontHighlight")
  text:SetPoint("LEFT", 4, 0)
  text:SetText(label)
  local b = CreateFrame("Button", nil, holder, "UIPanelButtonTemplate")
  b:SetSize(130, 22)
  b:SetPoint("LEFT", text, "RIGHT", 10, 0)
  local msg = holder:CreateFontString(nil, "ARTWORK", "GameFontDisableSmall")
  msg:SetPoint("LEFT", b, "RIGHT", 8, 0)
  local waiting = false
  local function Refresh()
    local key = GetBindingKey and GetBindingKey(binding)
    b:SetText(waiting and L["Press a key..."] or (key and (GetBindingText and GetBindingText(key) or key) or L["Not bound"]))
  end
  local function Stop()
    waiting = false
    b:EnableKeyboard(false)
    Refresh()
  end
  b:RegisterForClicks("LeftButtonUp", "RightButtonUp")
  b:SetScript("OnClick", function(_, button)
    msg:SetText("")
    if InCombatLockdown and InCombatLockdown() then
      msg:SetText(L["|cffff6060Not in combat.|r"])
      return
    end
    if button == "RightButton" then
      local key = GetBindingKey and GetBindingKey(binding)
      while key do
        SetBinding(key)
        key = GetBindingKey(binding)
      end
      SaveKeys()
      Stop()
      return
    end
    waiting = not waiting
    b:EnableKeyboard(waiting)
    Refresh()
  end)
  b:SetScript("OnKeyDown", function(self, key)
    if not waiting then return end
    if key == "ESCAPE" then Stop() return end
    if MODIFIER_KEYS[key] then return end -- wait for the key itself
    if InCombatLockdown and InCombatLockdown() then Stop() return end
    local full = (IsAltKeyDown() and "ALT-" or "") .. (IsControlKeyDown() and "CTRL-" or "")
      .. (IsShiftKeyDown() and "SHIFT-" or "") .. key
    local before = GetBindingAction and GetBindingAction(full)
    local old = GetBindingKey and GetBindingKey(binding)
    while old do -- one key for it
      SetBinding(old)
      old = GetBindingKey(binding)
    end
    if SetBinding(full, binding) then
      SaveKeys()
      if before and before ~= "" and before ~= binding then
        msg:SetText(string.format(L["Was: %s"], GetBindingName and GetBindingName(before) or before))
      end
    else
      msg:SetText(L["|cffff6060That key can't be used.|r"])
    end
    Stop()
  end)
  b:SetScript("OnHide", function() if waiting then Stop() end end)
  -- setting OnKeyDown turns keyboard capture on: off until it's waiting for a key, or
  -- the character can't be moved while this page shows
  b:EnableKeyboard(false)
  b:SetScript("OnEnter", function(self)
    GameTooltip:SetOwner(self, "ANCHOR_RIGHT")
    GameTooltip:SetText(label, 1, 1, 1)
    GameTooltip:AddLine(tip or L["Click, then press a key (Shift, Ctrl or Alt with it if you like). The same key shows and hides the map. Escape cancels, right-click clears it. Also in the game's Key Bindings, under AddOns."], nil, nil, nil, true)
    GameTooltip:Show()
  end)
  b:SetScript("OnLeave", GameTooltip_Hide)
  controls[#controls + 1] = Refresh
  return holder
end

-- `enabled` (optional): a function; the slider is grayed out while it returns false. `tip` (optional): its tooltip.
local function Slider(parent, label, minV, maxV, step, fmt, get, set, enabled, tip)
  local holder = CreateFrame("Frame", nil, parent)
  holder:SetSize(260, 40)
  local title = holder:CreateFontString(nil, "ARTWORK", "GameFontNormalSmall")
  title:SetPoint("TOPLEFT")
  title:SetText(label)
  holder.title = title
  local value = holder:CreateFontString(nil, "ARTWORK", "GameFontHighlightSmall")
  value:SetPoint("TOPRIGHT")
  holder.valueText = value -- (the tests)

  local s = CreateFrame("Slider", nil, holder, "BackdropTemplate")
  s:SetOrientation("HORIZONTAL")
  s:SetPoint("TOPLEFT", 0, -16)
  s:SetPoint("TOPRIGHT", 0, -16)
  s:SetHeight(16)
  s:SetBackdrop({
    bgFile = "Interface\\Buttons\\UI-SliderBar-Background",
    edgeFile = "Interface\\Buttons\\UI-SliderBar-Border",
    tile = true, tileSize = 8, edgeSize = 8,
    insets = { left = 3, right = 3, top = 6, bottom = 6 },
  })
  s:SetThumbTexture("Interface\\Buttons\\UI-SliderBar-Button-Horizontal")
  s:SetMinMaxValues(minV, maxV)
  holder.slider = s
  s:SetValueStep(step)
  s:SetObeyStepOnDrag(true)
  local updating = false
  local function Text(v) return type(fmt) == "function" and tostring(fmt(v)) or fmt:format(v) end
  s:SetScript("OnValueChanged", function(_, v)
    value:SetText(Text(v))
    if updating then return end
    set(v)
    Apply() -- other controls may follow this one (e.g. combat opacity follows opacity)
  end)
  -- (a controller's left and right: a step, PadOptions.lua)
  s.padStep = function(d)
    if s.IsEnabled and not s:IsEnabled() then return end
    set(math.max(minV, math.min(maxV, (tonumber(get()) or minV) + d * step)))
    Apply()
  end
  s:EnableMouseWheel(true)
  s:SetScript("OnMouseWheel", function(self, d)
    if self:IsEnabled() then self:SetValue(self:GetValue() + d * step) end
  end)
  if tip then
    s:SetScript("OnEnter", function(self)
      GameTooltip:SetOwner(self, "ANCHOR_RIGHT")
      GameTooltip:SetText(label, 1, 1, 1)
      GameTooltip:AddLine(tip, nil, nil, nil, true)
      GameTooltip:Show()
    end)
    s:SetScript("OnLeave", GameTooltip_Hide)
  end
  controls[#controls + 1] = function()
    updating = true
    s:SetValue(get())
    value:SetText(Text(get()))
    updating = false
    local on = not enabled or enabled()
    holder.agpsOn = on and true or false
    if on then s:Enable() else s:Disable() end
    s:SetAlpha(on and 1 or 0.4)
    title:SetFontObject(on and "GameFontNormalSmall" or "GameFontDisableSmall")
    value:SetFontObject(on and "GameFontHighlightSmall" or "GameFontDisableSmall")
  end
  Track(holder)
  return holder
end

local function Button(parent, label, width, onClick)
  local b = CreateFrame("Button", nil, parent, "UIPanelButtonTemplate")
  b:SetSize(width, 22)
  b:SetText(label)
  -- (a longer language's label: the button grows to fit it)
  local tw = b.GetTextWidth and b:GetTextWidth()
  if tw and tw + 24 > width then b:SetWidth(tw + 24) end
  b:SetScript("OnClick", function() onClick(); Apply() end)
  return b
end

---------------------------------------------------------------------------
-- Window
---------------------------------------------------------------------------

-- "How to share": what's kept, where, and how to send it (the report form on azerothgps.com with the
-- map data pasted in; or the AzerothGPS Discord).
O.SHARE_URL = "https://azerothgps.com/report"
O.DISCORD_URL = "https://discord.gg/hHEguxVQFb"
-- Help improve's Thanks (issue #91): the OpenMap style's stitched map, built from an open-source addon
O.OPENMAP_URL = "https://www.curseforge.com/wow/addons/openmap"
O.FEEDBACK_URL = "https://azerothgps.com/feedback/#report" -- (Help > Debugging: the report form, to paste the log in)
O.SITE_URL = "https://azerothgps.com" -- (Options > Help: the website, with the guide and the report form)
-- Options > General's language list (`/agps language`'s codes, ns.LOCALES; names every client's font can draw)
O.LANGUAGES = { { "enUS", "English" }, { "deDE", "Deutsch" }, { "esES", "Espa\195\177ol (Espa\195\177a)" },
  { "esMX", "Espa\195\177ol (Latinoam\195\169rica)" }, { "frFR", "Fran\195\167ais" }, { "itIT", "Italiano" },
  { "koKR", "Korean (koKR)" }, { "ptBR", "Portugu\195\170s (Brasil)" }, { "ruRU", "Russian (ruRU)" },
  { "zhCN", "Chinese, Simplified (zhCN)" }, { "zhTW", "Chinese, Traditional (zhTW)" } }
-- Options > Help's "What's new" (the changelog's 1.2.0 section, in short)
O.WHATS_NEW = {
  L["- The GPS map can take the minimap's place: a square in its corner that opens to the whole map (Options > Map)."],
  L["- RestedXP Route and Zygor Route: quick buttons that follow your guide, each step your next stop."],
  L["- Other addons' world map icons show on the GPS map too."],
  L["- AzerothGPS shows its text in your game's language (Options > General to pick another)."],
  L["- The options are regrouped: one page for the map, one for its icons, and this Help page."],
  L["- A short tutorial shows the main features on your own map: below, or /agps tutorial."],
}
-- A page's old id, still asked for by other code and addons (API.ShowOptions): the page it's on now.
O.PAGE_ALIASES = { ["Help improve"] = "Help", Minimap = "Map" }
O.CREDIT_TEXT = L["Thanks to |cffffd100jigrobbulus|r, creator of OpenMap, for making it open source, so its stitched world map could be built into AzerothGPS as the OpenMap map style. Click the address to select it, then Ctrl+C to copy it:"]
O.SHARE_INFO = {
  L["|cffffd100What is kept|r"],
  L["Roads and walls you draw or erase with the road tools, your pins, and the way you went when you reached a stop clearly faster than estimated. Positions, and your pins' names and icons: no character or realm names. Copy Map Data... includes what you tick there."],
  " ",
  L["|cffffd100Where it is kept|r"],
  L["On your PC, in this addon's saved variables (WTF\\Account\\<account>\\SavedVariables\\AzerothGPS.lua). Addons can't send anything from the game."],
  " ",
  L["|cffffd100How to share your roads, walls and pins|r"],
  L["1. Type |cffffd100/reload|r (it saves all your edits, so every one is copied), then click |cffffd100Copy Map Data...|r and press |cffffd100Ctrl+C|r."],
  L["2. Paste it in either place (click an address below, Ctrl+C, and open it in your browser):"],
  L["    |cffffd100Report form|r: the first address is the report form on azerothgps.com."],
  L["    |cffffd100Discord|r: the second is the AzerothGPS Discord."],
  L["3. Name the zone and say what you fixed."],
  " ",
  L["Roads and walls that check out are added in a later version, for everyone. Your pins stay yours, to share with"],
  L["other players as you like: they're never put into AzerothGPS's own data."],
}

local shareInfo
-- Your drawn roads as text, selected, to copy (Ctrl+C) and send.
local roadsCopy
-- (the text again, with the kinds picked: a checkbox in the window changed)
local function FillRoadsText()
  local f = roadsCopy
  local text, n = ns.Feedback.RoadsText()
  local counts = ns.Feedback.KindCounts()
  for _, cb in ipairs(f.kinds) do
    cb:SetChecked(ns.Feedback.Included(cb.kind))
    cb.text:SetText(string.format("%s (%d)", cb.label, counts[cb.kind] or 0))
  end
  f.text = text
  if n == 0 then
    f.hint:SetText(L["Nothing picked to copy: tick what to include above."])
  else
    f.hint:SetText(string.format(n == 1 and L["%d line of map data. Press |cffffd100Ctrl+C|r to copy (it's all selected), then paste it in the report form on azerothgps.com or on the AzerothGPS Discord (see How to share). Missing an edit? Type |cffffd100/reload|r and copy again."]
      or L["%d lines of map data. Press |cffffd100Ctrl+C|r to copy (it's all selected), then paste it in the report form on azerothgps.com or on the AzerothGPS Discord (see How to share). Missing an edit? Type |cffffd100/reload|r and copy again."], n))
  end
  f.edit:SetText(text)
  f.edit:SetFocus()
  f.edit:HighlightText()
end
local function ShowRoadsText()
  local total = 0
  for _, c in pairs(ns.Feedback.KindCounts()) do total = total + c end
  if total == 0 then
    ns.Print(L["no map data to share yet: roads or walls you drew or erased, faster trips, pins"])
    return
  end
  if not roadsCopy then
    local f = ns.Window("AzerothGPSRoadsCopy", 460, 360, L["Your Map Data"], "FULLSCREEN_DIALOG")
    local top = f.top
    local hint = f:CreateFontString(nil, "ARTWORK", "GameFontHighlightSmall")
    hint:SetPoint("TOPLEFT", 14, top - 8)
    hint:SetPoint("RIGHT", -14, 0)
    hint:SetJustifyH("LEFT")
    f.hint = hint
    -- what goes in the text (Feedback.KINDS: all ticked unless the player unticked one; saved)
    f.kinds = {}
    for i, k in ipairs(ns.Feedback.KINDS) do
      local cb = CreateFrame("CheckButton", nil, f, "UICheckButtonTemplate")
      cb:SetSize(22, 22)
      cb:SetPoint("TOPLEFT", 10 + (i - 1) * 110, top - 36)
      cb.text = cb:CreateFontString(nil, "ARTWORK", "GameFontHighlightSmall")
      cb.text:SetPoint("LEFT", cb, "RIGHT", 1, 0)
      cb.kind, cb.label = k.kind, k.label
      cb:SetScript("OnClick", function(self)
        ns.settings.gps[k.key] = self:GetChecked() and true or false
        FillRoadsText()
        O.Refresh()
      end)
      cb:SetScript("OnEnter", function(self)
        GameTooltip:SetOwner(self, "ANCHOR_RIGHT")
        GameTooltip:SetText(k.label, 1, 1, 1)
        GameTooltip:AddLine(k.tip, nil, nil, nil, true)
        GameTooltip:AddLine(L["Unticked: left out of the copy."], 0.7, 0.7, 0.7, true)
        GameTooltip:Show()
      end)
      cb:SetScript("OnLeave", GameTooltip_Hide)
      f.kinds[#f.kinds + 1] = cb
    end
    local scroll = CreateFrame("ScrollFrame", "AzerothGPSRoadsCopyScroll", f, "UIPanelScrollFrameTemplate")
    scroll:SetPoint("TOPLEFT", 14, top - 64)
    scroll:SetPoint("BOTTOMRIGHT", -34, 14)
    local bg = f:CreateTexture(nil, "BACKGROUND", nil, 1)
    bg:SetPoint("TOPLEFT", scroll, -4, 4)
    bg:SetPoint("BOTTOMRIGHT", scroll, 4, -4)
    bg:SetColorTexture(0, 0, 0, 1)
    local edit = CreateFrame("EditBox", nil, scroll)
    edit:SetMultiLine(true)
    edit:SetAutoFocus(false)
    edit:SetFontObject(ChatFontNormal)
    edit:SetWidth(400)
    edit:SetScript("OnEscapePressed", function() f:Hide() end)
    -- (read only: typing puts the text back; a click selects it all again)
    edit:SetScript("OnTextChanged", function(self, user)
      if user then
        self:SetText(f.text or "")
        self:HighlightText()
      end
    end)
    edit:SetScript("OnMouseUp", function(self) self:HighlightText() end)
    scroll:SetScrollChild(edit)
    scroll:SetScript("OnMouseDown", function() edit:SetFocus() end)
    f.edit = edit
    roadsCopy = f
  end
  if shareInfo then shareInfo:Hide() end -- (one window at a time: it was on top of this one)
  roadsCopy:Show()
  roadsCopy:Raise()
  FillRoadsText()
end
O.ShowRoadsText = ShowRoadsText

local function ShowShareInfo()
  if not shareInfo then
    local f = ns.Window("AzerothGPSShareInfo", 380, 260, L["Sharing Your Map Data"], "FULLSCREEN_DIALOG")
    local text = f:CreateFontString(nil, "ARTWORK", "GameFontHighlightSmall")
    text:SetPoint("TOPLEFT", 16, f.top - 12)
    text:SetPoint("RIGHT", -16, 0)
    text:SetJustifyH("LEFT")
    text:SetSpacing(2)
    f.text = text
    -- the addresses, to copy (the game can't open links): selected when clicked, not editable
    local function Address(value, below, gap)
      local url = CreateFrame("EditBox", nil, f, "InputBoxTemplate")
      url:SetHeight(20)
      url:SetPoint("TOPLEFT", below, "BOTTOMLEFT", gap, -8)
      url:SetPoint("RIGHT", -16, 0)
      url:SetAutoFocus(false)
      url:SetScript("OnEditFocusGained", function(self) self:HighlightText() end)
      url:SetScript("OnMouseUp", function(self) self:HighlightText() end)
      url:SetScript("OnTextChanged", function(self, user)
        if user then
          self:SetText(value)
          self:HighlightText()
        end
      end)
      url:SetScript("OnEscapePressed", function() f:Hide() end)
      return url
    end
    f.url = Address(O.SHARE_URL, text, 6)
    f.discord = Address(O.DISCORD_URL, f.url, 0)
    local copy = CreateFrame("Button", nil, f, "UIPanelButtonTemplate")
    copy:SetSize(150, 22)
    copy:SetPoint("TOPLEFT", f.discord, "BOTTOMLEFT", -6, -8)
    copy:SetText(L["Copy Map Data..."])
    copy:SetWidth(math.max(150, (copy:GetTextWidth() or 0) + 24))
    copy:SetScript("OnClick", function() O.ShowRoadsText() end)
    shareInfo = f
  end
  shareInfo.text:SetText(table.concat(O.SHARE_INFO, "\n"))
  shareInfo.url:SetText(O.SHARE_URL)
  shareInfo.url:SetCursorPosition(0)
  shareInfo.discord:SetText(O.DISCORD_URL)
  shareInfo.discord:SetCursorPosition(0)
  shareInfo:SetHeight(shareInfo.text:GetStringHeight() + 64 + 92)
  shareInfo:Show()
end
O.ShowShareInfo = ShowShareInfo

-- Stops routed ahead (the Performance page): the trip worked out again with it.
function O.SetStopsAhead(v)
  GPS().stopsAhead = v
  ns.Nav.Invalidate(true)
  if ns.GPS and ns.GPS.Redraw then ns.GPS.Redraw() end
end

-- Options > Performance. "Use Low-End Settings" sets these; "Restore Defaults" puts them back.
O.PERF_KEYS = { "hz", "rerouteSeconds", "stopsAhead", "gentleBackground", "arrowHz" }
O.LOW_END = { hz = 10, rerouteSeconds = 6, stopsAhead = 1, gentleBackground = true, arrowHz = 20 }
local function SetPerf(values)
  local before = GPS().stopsAhead
  for _, k in ipairs(O.PERF_KEYS) do GPS()[k] = values[k] end
  if GPS().stopsAhead ~= before then O.SetStopsAhead(GPS().stopsAhead) end
end
-- (and pausing routing when you're not following it: turned on with them, left as it is when they're undone;
-- asked 2026-11-16, Nav.WatchFollowing)
function O.UseLowEnd()
  SetPerf(O.LOW_END)
  GPS().autoPauseRouting = true
end
function O.PerfDefaults() SetPerf(ns.DEFAULTS.gps) end
function O.IsLowEnd()
  for _, k in ipairs(O.PERF_KEYS) do
    if GPS()[k] ~= O.LOW_END[k] then return false end
  end
  return true
end
-- The addon's share of the time, from its work (ms) over `secs` seconds of play.
function O.UsageText(ms, secs)
  if not ms or not secs or secs <= 0 then return L["AzerothGPS's work: measuring..."] end
  local perSec = math.max(0, ms / secs)
  return string.format(L["AzerothGPS's work: %.1f ms a second, %.1f%% of the time"], perSec, perSec / 10)
end

-- The options window, laid out like the game's Settings: categories on the left, one page
-- of settings at a time on the right. New settings go on the page they belong to (or a new
-- page: one more entry in the list).
local PAGE_W, LIST_W = 440, 150
-- Options > Quick buttons' search rows: each part's { x, width } in a row as wide as the page leaves (the page is
-- PAGE_W - 26 wide, the rows start 16 in); the name gets what's left between the icon and the dropdown.
do
  local w = PAGE_W - 26 - 16 - 6
  local remove = { w - 22, 22 }
  local edit = { remove[1] - 6 - 22, 22 }
  local where = { edit[1] - 8 - 150, 150 }
  local icon = { 2, 20 }
  local label = { icon[1] + icon[2] + 6, 0 }
  label[2] = where[1] - 8 - label[1]
  O.PAGE_W = PAGE_W
  O.SEARCH_ROW = { w = w, x = 16, icon = icon, label = label, where = where, edit = edit, remove = remove }
end
local SEARCH_H = 26 -- (the search box's row, over the pages)
local currentPage = 1

-- Options > Controller's diagram (asked 2026-11-16 with a picture of a controller's line drawing, each button's line
-- out to its name: "convert the Controller option page to look something like this but more AzerothGPS options themed.
-- Like transparent background with gold controller drawn lines"): the controller in gold lines on the page's own dark
-- (Pad.DIAGRAM's texture, drawn at the scale nearest the screen's pixels a unit and shown 1:1), each button's map
-- controls at the end of its line, as bound now; a button that does nothing on the map is left unlabeled. A long
-- label is cut short; its tooltip has the controls in full.
O.PAD_LABEL_MIN = 80 -- (UI units left for each side's labels, at least)
O.PAD_ICON_UNITS = 16 -- (the labels' button icons, about: drawn pixel for pixel, Pad.ICON_PX's nearest)
-- Pad button `key`'s icon on texture `tex`, pixel for pixel (asked 2026-11-16, "buttons needs better scaling where
-- used"): the drawn size nearest `units` UI units, shown at exactly its pixels. Its size in units, or 0 (none: hidden).
function O.PadIcon(tex, key, units, effScale)
  local P = ns.Pad
  local px = P.IconPx(units, effScale)
  local file = key and P.IconFile(key, px)
  if not file then
    tex:Hide()
    return 0
  end
  tex:SetTexture(file)
  tex:SetTexCoord(0, 1, 0, 1)
  if tex.SetSnapToPixelGrid then tex:SetSnapToPixelGrid(true) end
  local size = px / ns.PixelsPerUnit(effScale)
  tex:SetSize(size, size)
  tex:Show()
  return size
end
-- The controller drawn with each button's controls on its line (Options > Controller's page, and the map's overlay,
-- Pad.ShowControls): a frame `w` x `h` on `parent`, its labels clickable (a button's window) when `clickable`; laid out
-- by O.LayoutPadDiagram.
function O.MakePadDiagram(parent, w, h, clickable)
  local D = ns.Pad.DIAGRAM
  local diag = CreateFrame("Frame", nil, parent)
  diag:SetSize(w, h)
  diag.tex = diag:CreateTexture(nil, "ARTWORK")
  diag.labels = {}
  for _, side in ipairs({ "left", "right" }) do
    for i, key in ipairs(D[side]) do
      local b = CreateFrame("Button", nil, diag)
      b:SetHeight(18)
      b.text = b:CreateFontString(nil, "ARTWORK", "GameFontHighlightSmall")
      b.text:SetHeight(18)
      b.text:SetJustifyH(side == "left" and "RIGHT" or "LEFT")
      b.text:SetWordWrap(false)
      b.icon = b:CreateTexture(nil, "ARTWORK") -- (the button's icon, pixel for pixel: O.LayoutPadDiagram)
      b.key, b.side, b.row = key, side, i
      if clickable then
        -- (clicked: the button's own window, O.PadButton)
        b:SetScript("OnClick", function(self) O.PadButton(self.key) end)
        b:SetScript("OnEnter", function(self)
          GameTooltip:SetOwner(self, "ANCHOR_RIGHT")
          GameTooltip:SetText(ns.Pad.KeyLabel(self.key), 1, 0.82, 0)
          for _, line in ipairs(self.tip or {}) do GameTooltip:AddLine(line, 1, 1, 1, true) end
          GameTooltip:AddLine(L["Click to change its action."], 0.4, 0.8, 1)
          GameTooltip:Show()
        end)
        b:SetScript("OnLeave", GameTooltip_Hide)
      else
        b:EnableMouse(false)
      end
      diag.labels[#diag.labels + 1] = b
    end
  end
  return diag
end
function O.LayoutPadDiagram(diag)
  local P = ns.Pad
  local D = P and P.DIAGRAM
  if not D then return end
  local eff = diag.GetEffectiveScale and diag:GetEffectiveScale() or 1
  local ppu = ns.PixelsPerUnit(eff)
  local W, H = diag:GetWidth(), diag:GetHeight()
  local room = W - 2 * O.PAD_LABEL_MIN
  local best, bd
  for _, sc in ipairs(D.scales) do
    local k = sc / ppu
    if D.h * k <= H and D.w * k <= room then
      local d = math.abs(sc - ppu)
      if not bd or d < bd then best, bd = sc, d end
    end
  end
  local k
  if best then
    k = best / ppu
  else -- (a screen with fewer pixels a unit than the smallest drawn: that one, shrunk to fit)
    best = D.scales[1]
    k = math.min(H / D.h, room / D.w)
  end
  local tw, th = D.w * k, D.h * k
  local file = P.ICON_DIR .. "Diagram_" .. math.floor(best * 10 + 0.5) .. ".tga"
  local t = diag.tex
  if diag.file ~= file then
    t:SetTexture(file)
    t:SetTexCoord(0, 1, 0, 1)
    if t.SetSnapToPixelGrid then t:SetSnapToPixelGrid(true) end
    diag.file = file
  end
  t:SetSize(tw, th)
  t:ClearAllPoints()
  t:SetPoint("TOP", diag, "TOP", 0, -math.floor((H - th) / 2))
  local known = true
  if t.GetTextureFileID then -- (a file added since login: nothing till a /reload, the labels still listed)
    local ok, id = pcall(t.GetTextureFileID, t)
    known = not ok or id ~= nil
  end
  t:SetShown(known)
  diag.scale, diag.k = best, k
  local lw = math.max(20, (W - tw) / 2 - 6)
  for _, b in ipairs(diag.labels) do
    local y = -(D.row0 + (b.row - 1) * D.step) * k
    b:ClearAllPoints()
    b:SetWidth(lw)
    if b.side == "left" then
      b:SetPoint("RIGHT", t, "TOPLEFT", -3, y)
    else
      b:SetPoint("LEFT", t, "TOPRIGHT", 3, y)
    end
    local text, tip, ids = P.DiagramLabel(b.key, O.PAD_ICON_UNITS, eff)
    -- (a button with nothing on it: listed greyed, a click gives it a control)
    b.text:SetText(text or ("|cff808080" .. L["Not bound"] .. "|r"))
    b.tip, b.ids, b.empty = tip, ids, text == nil
    -- (the button's icon first, then its controls: on the left side the two right against the line)
    local iw = O.PadIcon(b.icon, b.key, O.PAD_ICON_UNITS, eff)
    local room = math.max(10, lw - iw - (iw > 0 and 3 or 0))
    local sw = b.text.GetUnboundedStringWidth and b.text:GetUnboundedStringWidth() or b.text:GetStringWidth()
    local tw = math.min(sw or room, room)
    b.text:ClearAllPoints()
    b.icon:ClearAllPoints()
    b.text:SetWidth(tw)
    if b.side == "left" then
      b.text:SetPoint("RIGHT", b, "RIGHT", 0, 0)
      b.icon:SetPoint("RIGHT", b.text, "LEFT", -3, 0)
    else
      b.icon:SetPoint("LEFT", b, "LEFT", 0, 0)
      b.text:SetPoint("LEFT", b, "LEFT", iw > 0 and iw + 3 or 0, 0)
    end
  end
end

-- A pad button's own window (asked 2026-11-16, with dropdowns: the button's own control first, then lines greyed
-- till toggled on, each needing a trigger or bumper and/or Hold, one more as each is filled, till all are used; the
-- window half again the old one's size, scrolling instead of growing): the control on the button pressed alone, then
-- a line a combination: its toggle, its modifier, its Hold and its control. A control is on one button: picking it
-- here moves it here. Hovering a control in a list says what it does.
O.BUTTON_W, O.BUTTON_H = 510, 300 -- (half again the 340 x 200 window it replaced)
O.BUTTON_LINE = 34
O.BUTTON_NOTE_H = 54 -- (the note's room over Apply and Done: four lines, a NOTICE: line and three)
O.BUTTON_MODS = { "PADLTRIGGER", "PADRTRIGGER", "PADLSHOULDER", "PADRSHOULDER" }
-- (each line's control list, under the button's own; inside the lines' scroll, not cut off at its edge: asked
-- 2026-11-16, "dropdowns cutoff")
O.BUTTON_ACTION_X, O.BUTTON_ACTION_W = 220, 232
-- (laid out as asked 2026-11-16 with a sketch: the first line always, "Pressed" and its control, Not bound at the top
-- of the list doing nothing; then a line a combination: the modifier's icons, "+", the button's own icon, a Hold box
-- (off at first, "Hold" in yellow) and its control; the left side greyed while the control is Not bound, and a new
-- line once one is picked)

function O.IsModifier(key)
  for _, m in ipairs(O.BUTTON_MODS) do if m == key then return true end end
  return false
end
local function ComboKey(mod, hold) return (mod or "") .. "|" .. (hold and "h" or "") end
local function SlotBind(mod, key) return mod and (mod .. "+" .. key) or key end

-- the combinations a button `key` can have besides itself pressed alone, in the order new lines take them: each
-- trigger and bumper (not itself), held alone, then each trigger and bumper held
function O.ButtonCombos(key)
  local out = {}
  -- (a trigger or bumper itself: no combinations, its first line only; asked 2026-11-16, "Shouldn't allow LT itself to
  -- + with a modifier. All modifiers only show the top row")
  if O.IsModifier(key) then return out end
  for _, m in ipairs(O.BUTTON_MODS) do
    if m ~= key then out[#out + 1] = { mod = m, hold = false } end
  end
  out[#out + 1] = { hold = true }
  for _, m in ipairs(O.BUTTON_MODS) do
    if m ~= key then out[#out + 1] = { mod = m, hold = true } end
  end
  return out
end
-- the controls on `key` now, by combination: { [ComboKey] = { ids... } }
function O.ButtonUses(key)
  local P = ns.Pad
  local by = {}
  for _, a in ipairs(P.ACTIONS) do
    local b = P.Key(a[1])
    if b then
      local parts = P.BindParts(b)
      if parts[#parts] == key then
        local c = ComboKey(#parts > 1 and parts[1] or nil, P.IsHold(a[1]))
        by[c] = by[c] or {}
        table.insert(by[c], a[1])
      end
    end
  end
  return by
end
-- a dropdown in the window (the options' look: Blizzard_Menu's; a controller's through padGet / padSet / options).
-- `list()`: { { value, text, tip = { lines }, off = true }, ... }
-- An option's `short` (optional): its text on the dropdown while closed (a narrow one: Options' search rows).
-- A dropdown of ours (a box with the one picked and an arrow; a click opens PadOptions' list under it, the mouse's and
-- the pad's alike): the button window's with the game's controller UI on, where the game's menu can't be used
-- (O.PadDropdown).
function O.OwnDropdown(parent, width, list, get, set)
  -- (our own, not the game's Menu: touched to show over the window, the game's menu got the addon blocked with the
  -- controller UI on, asked 2026-11-16. A box with the one picked and an arrow; a click opens PadOptions' list under
  -- it, the mouse's and the pad's alike)
  local dd = CreateFrame("Button", nil, parent)
  dd:SetSize(width, 24)
  local edge = dd:CreateTexture(nil, "BACKGROUND", nil, -1)
  edge:SetPoint("TOPLEFT", -1, 1)
  edge:SetPoint("BOTTOMRIGHT", 1, -1)
  edge:SetColorTexture(0.55, 0.45, 0.2, 0.9)
  local bg = dd:CreateTexture(nil, "BACKGROUND")
  bg:SetAllPoints()
  bg:SetColorTexture(0.06, 0.06, 0.06, 0.95)
  local hl = dd:CreateTexture(nil, "HIGHLIGHT")
  hl:SetAllPoints()
  hl:SetColorTexture(1, 0.82, 0, 0.08)
  dd.text = dd:CreateFontString(nil, "ARTWORK", "GameFontHighlightSmall")
  dd.text:SetPoint("LEFT", 8, 0)
  dd.text:SetPoint("RIGHT", -24, 0)
  dd.text:SetJustifyH("LEFT")
  dd.text:SetWordWrap(false)
  dd.arrow = dd:CreateTexture(nil, "ARTWORK")
  dd.arrow:SetSize(16, 16)
  dd.arrow:SetPoint("RIGHT", -5, 0)
  dd.arrow:SetTexture("Interface\\ChatFrame\\ChatFrameExpandArrow")
  dd.arrow:SetRotation(-math.pi / 2)
  dd.padGet, dd.padSet, dd.padList = get, set, list
  dd.options = list()
  dd:SetScript("OnClick", function(self)
    local PO = ns.Pad and ns.Pad.Opt
    if not PO then return end
    if PO.listOpen and PO.list and PO.list.drop == self then PO.CloseList() return end
    self.options = list()
    PO.OpenList(self)
  end)
  dd:SetScript("OnHide", function(self)
    local PO = ns.Pad and ns.Pad.Opt
    if PO and PO.listOpen and PO.list and PO.list.drop == self then PO.CloseList() end
  end)
  function dd.Update(self, on)
    self.options = list()
    self.agpsOn = on and true or false
    local t = ""
    for _, o in ipairs(self.options) do if o.value == get() then t = o.text or tostring(o.value) end end
    self.text:SetText(t)
    self.text:SetFontObject(on and "GameFontHighlightSmall" or "GameFontDisableSmall")
    self.arrow:SetDesaturated(not on)
    self:SetEnabled(on and true or false)
  end
  return dd
end
function O.PadDropdown(parent, width, list, get, set)
  local ok, dd = pcall(CreateFrame, "DropdownButton", nil, parent, O.DROPDOWN_TEMPLATE or "WowStyle1DropdownTemplate")
  if ok and dd and dd.SetupMenu then
    dd:SetWidth(width)
    if dd.SetSelectionText then
      pcall(dd.SetSelectionText, dd, function()
        for _, o in ipairs(list()) do
          if o.value == get() then return o.short or o.text end
        end
        return ""
      end)
    end
    dd:SetupMenu(function(_, root)
      if root.SetScrollMode then root:SetScrollMode(12 * 20) end
      for _, o in ipairs(list()) do
        local r = root:CreateRadio(o.text, function() return get() == o.value end, function() set(o.value) end)
        if o.off and r and r.SetEnabled then r:SetEnabled(false) end
        if o.tip and r and r.SetTooltip and GameTooltip_SetTitle and GameTooltip_AddNormalLine then
          r:SetTooltip(function(t)
            GameTooltip_SetTitle(t, o.text)
            for _, line in ipairs(o.tip) do GameTooltip_AddNormalLine(t, line) end
          end)
        end
      end
    end)
  else -- (no menus on this client: a button stepping to the next choice)
    dd = CreateFrame("Button", nil, parent, "UIPanelButtonTemplate")
    dd:SetSize(width, 22)
    dd:SetScript("OnClick", function()
      local l, at = list(), 0
      for i, o in ipairs(l) do if o.value == get() then at = i end end
      for step = 1, #l do
        local o = l[(at + step - 1) % #l + 1]
        if not o.off then set(o.value) return end
      end
    end)
  end
  dd.padGet, dd.padSet, dd.padList = get, set, list
  dd.options = list()
  -- (with the game's controller UI on, ours in its place: the game's menu shown or hidden there runs its controller
  -- code, which is blocked for a menu an addon's code filled, "blocked from an action only available to the Blizzard
  -- UI" each time, asked 2026-11-16)
  if dd.SetupMenu then
    dd.own = O.OwnDropdown(parent, width, list, get, set)
    dd.own:SetPoint("TOPLEFT", dd, "TOPLEFT", 0, 0)
    dd.own:Hide()
  end
  function dd.Update(self, on)
    if self.own then
      local ui = ns.GPS and ns.GPS.ControllerUI and ns.GPS.ControllerUI() or false
      self:SetShown(not ui)
      self.own:SetShown(ui)
      self.own:Update(on)
    end
    self.options = list()
    self.agpsOn = on and true or false
    if self.GenerateMenu then self:GenerateMenu() end
    if self.SetupMenu == nil and self.SetText then
      local t = ""
      for _, o in ipairs(self.options) do if o.value == get() then t = o.short or o.text end end
      self:SetText(t)
    end
    if self.SetEnabled then self:SetEnabled(on and true or false) end
  end
  return dd
end
-- the controls' list: Not bound first (nothing), then each control (what it does and its macro on hover). The stop
-- and Yes on a question are one, Select (asked 2026-11-16: "combine Set a stop and yes on a question into the same key
-- and its just Select"): picked, both go on the line.
function O.ActionChoices()
  local P = ns.Pad
  local out = { { value = "none", text = L["Not bound"], tip = { L["Does nothing."] } } }
  for _, a in ipairs(P.ACTIONS) do
    if a[1] ~= "yes" then
      local tip = { P.ABOUT and P.ABOUT[a[1]] or a[3] }
      if a[1] == "select" then tip[#tip + 1] = P.ABOUT and P.ABOUT.yes end
      local blocked = a[1] == "toggle" and P.ToggleBlocked and P.ToggleBlocked()
      if blocked then tip[#tip + 1] = P.TOGGLE_UI_NOTE end
      local m = P.MacroTip(a[1])
      if m then tip[#tip + 1] = m[1] end
      out[#out + 1] = { value = a[1], text = a[1] == "select" and L["Set Stop"] or a[3], tip = tip, off = blocked or nil }
    end
  end
  return out
end
-- a line's control as its list shows it (Yes alone on a line: Select's)
local function Shown(ids)
  local id = ids and ids[1]
  if id == "yes" then return "select" end
  return id or "none"
end

-- (changes wait for Apply, grayed till there's one; Done closes, leaving any not applied: asked 2026-11-16, "Have 2
-- buttons here, one is Apply one is Done. Apply is grey until change is made and that change is only applied when this
-- is clicked to prevent accidentally unassigning another key". f.draft: { [ComboKey] = { mod, hold, id } }, the
-- button's lines as they'd be; the line pressed alone always there, "none" for Not bound.)
local BASE = ComboKey(nil, false)
-- the draft as the button's controls are now
local function LiveDraft(key)
  local d = { [BASE] = { id = "none" } }
  for ck, ids in pairs(O.ButtonUses(key)) do
    local m, h = ck:match("^(.-)|(h?)$")
    d[ck] = { mod = m ~= "" and m or nil, hold = h == "h", id = Shown(ids) }
  end
  return d
end
local function DraftSig(d)
  local t = {}
  for ck, e in pairs(d) do t[#t + 1] = ck .. "=" .. e.id end
  table.sort(t)
  return table.concat(t, ",")
end
function O.PadButton(key)
  local P = ns.Pad
  if not (P and key) then return nil end
  local f = O.padButton
  if not f then
    -- (at DIALOG, Options' own strata, raised over it as it opens: the game's menus open at FULLSCREEN_DIALOG, over
    -- it then, with nothing of theirs touched; asked 2026-11-16, the menu behind the window, and the game's menu
    -- touched to be over it got the addon blocked with the controller UI on)
    f = ns.Window("AzerothGPSPadButton", O.BUTTON_W, O.BUTTON_H, "", "DIALOG")
    local top = f.top or -30
    -- the first line, always: the button's icon, "Pressed", its control
    f.icon = f:CreateTexture(nil, "ARTWORK")
    f.icon:SetPoint("TOPLEFT", 18, top - 14)
    f.baseLabel = f:CreateFontString(nil, "ARTWORK", "GameFontNormal")
    f.baseLabel:SetPoint("TOPLEFT", 46, top - 16)
    f.baseLabel:SetText(L["Pressed"])
    f.base = O.PadDropdown(f, O.BUTTON_ACTION_W, O.ActionChoices,
      function() return f.draft and f.draft[BASE] and f.draft[BASE].id or "none" end,
      function(v) O.ButtonPick(nil, false, v) end)
    f.base:SetPoint("TOPLEFT", 16 + O.BUTTON_ACTION_X, top - 10)
    -- the combinations' lines, scrolling when long
    local scroll = CreateFrame("ScrollFrame", nil, f, "UIPanelScrollFrameTemplate")
    scroll:SetPoint("TOPLEFT", 12, top - 44)
    scroll:SetPoint("BOTTOMRIGHT", -30, 44 + O.BUTTON_NOTE_H)
    local child = CreateFrame("Frame", nil, scroll)
    child:SetSize(O.BUTTON_W - 44, 10)
    scroll:SetScrollChild(child)
    f.scroll, f.child = scroll, child
    -- (what Apply will move, or a refusal, or why Show/Hide GPS can't be set: the whole width over Apply and Done, three
    -- lines; at their left, two, it was cut off: asked 2026-11-16, "this text is cut off")
    f.note = f:CreateFontString(nil, "ARTWORK", "GameFontHighlightSmall")
    f.note:SetPoint("BOTTOMLEFT", 18, 42)
    f.note:SetPoint("TOPRIGHT", f, "BOTTOMRIGHT", -18, 42 + O.BUTTON_NOTE_H)
    f.note:SetJustifyH("LEFT")
    f.note:SetJustifyV("BOTTOM")
    f.done = Button(f, L["Done"], 90, function() f:Hide() end)
    f.done:SetPoint("BOTTOMRIGHT", -14, 12)
    f.apply = Button(f, L["Apply"], 90, function() O.ButtonApply() end)
    f.apply:SetPoint("RIGHT", f.done, "LEFT", -8, 0)
    f.lines = {}
    O.padButton = f
  end
  f.key = key
  f.draft = LiveDraft(key)
  f:SetWindowTitle(P.KeyLabel(key))
  f.said = nil
  f:Show()
  if f.Raise then f:Raise() end
  O.PadButtonRefresh()
  return f
end
-- a combination's choices: no modifier (with Hold only), each trigger and bumper (not the button itself) as its icon;
-- one another line has, greyed
function O.ModChoices(ln)
  local f, P = O.padButton, ns.Pad
  local hold = ln.combo and ln.combo.hold
  local out = { { value = "", text = L["No modifier"], off = not hold or nil } }
  for _, m in ipairs(O.BUTTON_MODS) do
    if m ~= f.key then
      local c = ComboKey(m, hold)
      local used = f.used and f.used[c] and c ~= ComboKey(ln.combo and ln.combo.mod, hold)
      local icon = P.KeyIcon(m, 16, f.GetEffectiveScale and f:GetEffectiveScale() or 1)
      out[#out + 1] = { value = m, text = (icon and icon .. " " or "") .. P.KeyLabel(m), off = used or nil }
    end
  end
  return out
end
-- a line of the window (made the first time it's needed)
local function ButtonLine(f, i)
  local ln = f.lines[i]
  if ln then return ln end
  ln = CreateFrame("Frame", nil, f.child)
  ln:SetSize(O.BUTTON_W - 48, O.BUTTON_LINE)
  ln.mod = O.PadDropdown(ln, 100, function() return O.ModChoices(ln) end,
    function() return ln.combo and ln.combo.mod or "" end,
    function(v) O.ButtonCombo(ln, v ~= "" and v or nil, ln.combo and ln.combo.hold) end)
  ln.mod:SetPoint("LEFT", 0, 0)
  ln.plus = ln:CreateFontString(nil, "ARTWORK", "GameFontHighlight")
  ln.plus:SetPoint("LEFT", 106, 0)
  ln.plus:SetText("+")
  ln.icon = ln:CreateTexture(nil, "ARTWORK") -- (the button's own: O.PadIcon)
  ln.icon:SetPoint("LEFT", 118, 0)
  ln.hold = CreateFrame("CheckButton", nil, ln, "UICheckButtonTemplate")
  ln.hold:SetSize(24, 24)
  ln.hold:SetPoint("LEFT", 144, 0)
  ln.hold.label = ln.hold:CreateFontString(nil, "ARTWORK", "GameFontNormal")
  ln.hold.label:SetPoint("LEFT", ln.hold, "RIGHT", 1, 0)
  ln.hold.label:SetText(L["Hold"])
  ln.hold:SetScript("OnClick", function(self)
    O.ButtonCombo(ln, ln.combo and ln.combo.mod, self:GetChecked() and true or false)
  end)
  ln.hold:SetScript("OnEnter", function(self)
    GameTooltip:SetOwner(self, "ANCHOR_RIGHT")
    GameTooltip:SetText(L["Hold"], 1, 1, 1)
    GameTooltip:AddLine(L["Held for 2 seconds: the same button (or pair) can do another control when it's only pressed. A button with a held control does its other one as it's let go."], nil, nil, nil, true)
    GameTooltip:Show()
  end)
  ln.hold:SetScript("OnLeave", GameTooltip_Hide)
  ln.action = O.PadDropdown(ln, O.BUTTON_ACTION_W, O.ActionChoices,
    function() return ln.id or "none" end,
    function(v) if ln.combo then O.ButtonPick(ln.combo.mod, ln.combo.hold, v) end end)
  ln.action:SetPoint("LEFT", O.BUTTON_ACTION_X, 0)
  f.lines[i] = ln
  return ln
end
local function Say(r, why)
  local f = O.padButton
  if f then f.said = r ~= true and (why or "") or nil end
  return r == true
end
-- control `id` (or "none", Not bound) on the combination, in the draft: off any other line it was on here
function O.ButtonPick(mod, hold, id)
  local f, P = O.padButton, ns.Pad
  local ck = ComboKey(mod, hold)
  if id ~= "none" then
    if id == "toggle" and P.ToggleBlocked() then
      Say(false, P.TOGGLE_UI_NOTE)
      return O.PadButtonRefresh()
    end
    if hold and not P.CanHold(id) then
      Say(false, L["Done while held: it can't be a hold."])
      return O.PadButtonRefresh()
    end
    local a = P.Action(id)
    if mod and a and a.game then
      Say(false, L["This one takes a single button."])
      return O.PadButtonRefresh()
    end
    for k, e in pairs(f.draft) do
      if e.id == id and k ~= ck then
        if k == BASE then e.id = "none" else f.draft[k] = nil end
      end
    end
  end
  if ck == BASE then f.draft[BASE].id = id
  elseif id == "none" then f.draft[ck] = nil
  else f.draft[ck] = { mod = mod, hold = hold, id = id } end
  Say(true)
  O.PadButtonRefresh()
  return true
end
-- a line's modifier or Hold changed, in the draft
function O.ButtonCombo(ln, mod, hold)
  local f, P = O.padButton, ns.Pad
  hold = hold and true or false
  if not ln.id then O.PadButtonRefresh() return false end -- (Not bound: greyed, nothing to move)
  local fail
  if not mod and not hold then fail = L["Pick LT, RT, LB or RB, or Hold."]
  elseif ComboKey(mod, hold) ~= ComboKey(ln.combo.mod, ln.combo.hold) and f.used[ComboKey(mod, hold)] then
    fail = L["Another line has that one."]
  elseif hold and not P.CanHold(ln.id) then fail = L["Done while held: it can't be a hold."]
  elseif mod and P.Action(ln.id) and P.Action(ln.id).game then fail = L["This one takes a single button."] end
  if fail then
    Say(false, fail)
    O.PadButtonRefresh()
    return false
  end
  f.draft[ComboKey(ln.combo.mod, ln.combo.hold)] = nil
  f.draft[ComboKey(mod, hold)] = { mod = mod, hold = hold, id = ln.id }
  Say(true)
  O.PadButtonRefresh()
  return true
end
-- the draft's changes from the controls as they are: lines for the note ("Zoom out comes off LT."), and whether any
function O.ButtonChanges()
  local f, P = O.padButton, ns.Pad
  local lines = {}
  if DraftSig(f.draft) == DraftSig(LiveDraft(f.key)) then return lines, false end
  local wanted = {}
  for _, e in pairs(f.draft) do
    if e.id ~= "none" then
      wanted[e.id] = true
      local k = P.Key(e.id)
      local parts = k and P.BindParts(k)
      if parts and parts[#parts] ~= f.key then
        lines[#lines + 1] = string.format(L["%s comes off %s."], P.ShortName(e.id), P.BindLabel(k))
      end
    end
  end
  for _, ids in pairs(O.ButtonUses(f.key)) do
    for _, o in ipairs(ids) do
      if not wanted[o] and not (o == "yes" and wanted.select) then
        lines[#lines + 1] = string.format(L["%s will have no button."], P.ShortName(o))
      end
    end
  end
  return lines, true
end
-- Apply: the draft made so (the controls not wanted here off it first, then each one on its line; one moved here
-- comes off its other button), and the window again as things are now
function O.ButtonApply()
  local f, P = O.padButton, ns.Pad
  local key = f.key
  local want = {}
  for _, e in pairs(f.draft) do
    if e.id ~= "none" then
      want[e.id] = { SlotBind(e.mod, key), e.hold }
      if e.id == "select" then want.yes = want.select end
    end
  end
  local errs = {}
  local function name(id) return P.ShortName(id) end
  for _, ids in pairs(O.ButtonUses(key)) do
    for _, o in ipairs(ids) do
      local w = want[o]
      local k = P.Key(o)
      if not w or k ~= w[1] or P.IsHold(o) ~= w[2] then -- (off here first: a swap between two lines works)
        if o ~= "back" or not w then
          local r, why = P.Unbind(o)
          if r ~= true then errs[#errs + 1] = name(o) .. ": " .. (why or "") end
        end
      end
    end
  end
  for id, w in pairs(want) do
    if P.Key(id) ~= w[1] or P.IsHold(id) ~= w[2] then
      local r, why = P.Assign(id, w[1], w[2])
      if r ~= true then errs[#errs + 1] = name(id) .. ": " .. (why or "") end
    end
  end
  f.draft = LiveDraft(key)
  f.said = #errs > 0 and table.concat(errs, " ") or nil
  O.Refresh()
  O.PadButtonRefresh()
  return #errs == 0
end
-- the window as the draft has it: a line each combination in it, then one Not bound (on the next combination free,
-- its left side greyed) while any are left; Apply lit while it differs from the controls as they are
function O.PadButtonRefresh()
  local f, P = O.padButton, ns.Pad
  if not (f and f.key and f:IsShown()) then return end
  local eff = f.GetEffectiveScale and f:GetEffectiveScale() or 1
  O.PadIcon(f.icon, f.key, 20, eff)
  f.used = {}
  for c in pairs(f.draft) do f.used[c] = true end
  f.base:Update(true)
  local shown = {}
  for _, c in ipairs(O.ButtonCombos(f.key)) do
    local e = f.draft[ComboKey(c.mod, c.hold)]
    if e then shown[#shown + 1] = { combo = c, id = e.id } end
  end
  -- (a combination not among them, a game modifier's: as it is)
  for ck, e in pairs(f.draft) do
    local known = ck == BASE
    for _, c in ipairs(O.ButtonCombos(f.key)) do if ComboKey(c.mod, c.hold) == ck then known = true end end
    if not known then shown[#shown + 1] = { combo = { mod = e.mod, hold = e.hold }, id = e.id } end
  end
  for _, c in ipairs(O.ButtonCombos(f.key)) do
    if not f.used[ComboKey(c.mod, c.hold)] then
      shown[#shown + 1] = { combo = c, empty = true }
      break
    end
  end
  local y = -4
  for i, info in ipairs(shown) do
    local ln = ButtonLine(f, i)
    ln.combo, ln.id, ln.empty = info.combo, info.id, info.empty
    ln:ClearAllPoints()
    ln:SetPoint("TOPLEFT", 4, y)
    ln:Show()
    local on = not info.empty -- (the left side: greyed while Not bound)
    ln.mod:Update(on)
    O.PadIcon(ln.icon, f.key, 20, eff)
    ln.icon:SetAlpha(on and 1 or 0.4)
    ln.plus:SetFontObject(on and "GameFontHighlight" or "GameFontDisable")
    ln.hold:SetChecked(info.combo.hold and true or false)
    ln.hold:SetEnabled(on)
    ln.hold.agpsOn = on
    ln.hold.label:SetFontObject(on and "GameFontNormal" or "GameFontDisable")
    ln.action:Update(true)
    y = y - O.BUTTON_LINE
  end
  for i = #shown + 1, #f.lines do f.lines[i]:Hide() end
  f.shown = shown
  local h = -y + 8
  f.child:SetHeight(h)
  local room = f.scroll.GetHeight and f.scroll:GetHeight() or 0
  local bar = f.scroll.ScrollBar
  if bar then bar:SetShown(h > room + 1) end
  local moves, dirty = O.ButtonChanges()
  f.dirty = dirty
  f.apply:SetEnabled(dirty)
  f.apply.agpsOn = dirty
  if f.said then f.note:SetText(f.said:find("|c", 1, true) and f.said or ("|cffff6060" .. f.said .. "|r")) -- (colored itself)
  elseif #moves == 0 and P.ToggleBlocked() then -- (Show/Hide GPS here with the controller UI on: why it won't run)
    local has = false
    for _, e in pairs(f.draft) do if e.id == "toggle" then has = true end end
    f.note:SetText(has and P.TOGGLE_UI_NOTE or "")
  else f.note:SetText(table.concat(moves, " ")) end
end

local function BuildWindow()
  O.settingControls, O.pages = {}, {}
  trackKey = nil
  local ok, f = pcall(CreateFrame, "Frame", "AzerothGPSOptions", UIParent, "PortraitFrameTemplate")
  local framed = ok and f and f.NineSlice
  if framed then
    -- the game's metal window frame, the AzerothGPS logo top left (on its plate or in the round
    -- portrait: ns.ApplyLogoLook; dragging the plate moves the window)
    if f.SetTitle then f:SetTitle(L["AzerothGPS Options"])
    elseif f.TitleContainer and f.TitleContainer.TitleText then f.TitleContainer.TitleText:SetText(L["AzerothGPS Options"]) end
    ns.SetLogoPortrait(f, nil, function(starting)
      local fn = f:GetScript(starting and "OnDragStart" or "OnDragStop")
      if fn then fn(f) end
    end)
    -- close with a plain Hide: the template's own close goes through the game's panel
    -- manager, which can refuse during combat
    if f.CloseButton then f.CloseButton:SetScript("OnClick", function() f:Hide() end) end
  else
    f = CreateFrame("Frame", "AzerothGPSOptions", UIParent, "BackdropTemplate")
    f:SetBackdrop({ bgFile = "Interface\\Buttons\\WHITE8X8", edgeFile = "Interface\\Buttons\\WHITE8X8", edgeSize = 1 })
    f:SetBackdropColor(0.06, 0.06, 0.07, 0.95)
    f:SetBackdropBorderColor(0.3, 0.3, 0.3, 1)
    local title = f:CreateFontString(nil, "ARTWORK", "GameFontNormalLarge")
    title:SetPoint("TOP", 0, -8)
    title:SetText(L["AzerothGPS Options"])
    local close = CreateFrame("Button", nil, f, "UIPanelCloseButton")
    close:SetScript("OnClick", function() f:Hide() end) -- works in combat too
    close:SetPoint("TOPRIGHT", 2, 2)
    f.closeButton = close
  end
  f:SetSize(LIST_W + PAGE_W + 36, 560 + SEARCH_H)
  f:SetPoint("CENTER")
  f:SetFrameStrata("DIALOG")
  ns.RegisterPopup(f, "DIALOG") -- (over the map opened out of the minimap square)
  f.agpsBusy = true -- (open over it: the map stays out, ns.PopupOverShown)
  f:SetClampedToScreen(true)
  f:SetMovable(true)
  f:EnableMouse(true)
  f:RegisterForDrag("LeftButton")
  f:SetScript("OnDragStart", f.StartMoving)
  f:SetScript("OnDragStop", f.StopMovingOrSizing)
  tinsert(UISpecialFrames, "AzerothGPSOptions") -- Escape closes it

  -- category list (left) and page area (right)
  local list = CreateFrame("Frame", nil, f, "BackdropTemplate")
  list:SetPoint("TOPLEFT", 10, framed and -62 or -30) -- below the portrait
  list:SetPoint("BOTTOMLEFT", 10, 44)
  list:SetWidth(LIST_W)
  list:SetBackdrop({ bgFile = "Interface\\Buttons\\WHITE8X8" })
  list:SetBackdropColor(0, 0, 0, 0.35)
  -- (asked 2026-10-05: with companions' pages the list ran off the window) it scrolls, a scroll bar only when it's
  -- longer than the window; the tabs and section headers are in `listChild`
  local listScroll = CreateFrame("ScrollFrame", nil, list, "UIPanelScrollFrameTemplate")
  listScroll:SetPoint("TOPLEFT", 0, 0)
  listScroll:SetPoint("BOTTOMRIGHT", 0, 0)
  local listChild = CreateFrame("Frame", nil, listScroll)
  listChild:SetSize(LIST_W, 10)
  listScroll:SetScrollChild(listChild)
  if listScroll.ScrollBar then listScroll.ScrollBar:Hide() end
  O.listScroll, O.listChild = listScroll, listChild
  local area = CreateFrame("Frame", nil, f, "BackdropTemplate")
  area:SetPoint("TOPLEFT", LIST_W + 18, -30 - SEARCH_H)
  area:SetPoint("BOTTOMRIGHT", -10, 44)
  area:SetBackdrop({ bgFile = "Interface\\Buttons\\WHITE8X8" })
  area:SetBackdropColor(0, 0, 0, 0.2)

  -- The search (asked 2026-11-11: "a search function for settings like how the game's options work that would filter
  -- instantly as the player types"): a box over the pages; while there's text in it, one list shows every page's
  -- settings that match (O.Search below), and a page with none has its name dim in the list. A setting matches by its label, its tooltip, its choices, its section's or its page's name:
  -- every word typed, anywhere in those. Everything laid out by `place` is a row of a group (a setting from its
  -- `Key`, a section's header, a note); a page laid out by hand (`whole`) shows as it is or not at all.
  local search = { pages = {} }
  O.search = search
  local pinfo, group, section, lastRow
  local function AddText(g, ...)
    if not g then return end
    for i = 1, select("#", ...) do
      local s = select(i, ...)
      if type(s) == "string" and s ~= "" then g.text = g.text .. " " .. s:lower() end
    end
  end
  StartGroup = function(kind, ...)
    if not pinfo then return nil end
    group = { kind = kind, text = "", rows = {}, section = kind ~= "header" and section or nil }
    if kind == "header" then section = group end
    pinfo.groups[#pinfo.groups + 1] = group
    AddText(group, ...)
    return group
  end
  -- (something hung on the row placed last, not placed itself: shown and hidden with it)
  local function also(w, row)
    row = row or lastRow
    if not (row and w) then return end
    w.padRow, w.padY = row.w, row.y
    row.extras = row.extras or {}
    row.extras[#row.extras + 1] = w
  end

  local pages, tabs = {}, {}
  O.tabs = tabs -- (the page list: a controller's, PadOptions.lua)
  local function ShowPage(n)
    currentPage = n
    if search.none then search.none:Hide() end
    if search.results then search.results:Hide() end
    for i, pg in ipairs(pages) do
      pg:SetShown(i == n)
      if i == n and pg.ScrollBar then -- a scroll bar only when the page is longer than the window
        local child = pg:GetScrollChild()
        pg.ScrollBar:SetShown(child and child:GetHeight() > pg:GetHeight() + 1)
        if not pg.ScrollBar:IsShown() then pg:SetVerticalScroll(0) end
      end
    end
    for i, t in ipairs(tabs) do
      t.selected:SetShown(i == n)
      t.text:SetFontObject(i == n and (t.small and "GameFontHighlightSmall" or "GameFontHighlight")
        or (t.small and "GameFontNormalSmall" or "GameFontNormal"))
    end
    -- (the page's tab scrolled into view: ShowOptions opening a page further down)
    local t = tabs[n]
    if t and t.listY and listScroll.ScrollBar and listScroll.ScrollBar:IsShown() then
      local top, h = -t.listY, listScroll:GetHeight() or 0
      local cur = listScroll:GetVerticalScroll() or 0
      local range = math.max(0, (O.listFull or 0) - h)
      if top < cur then
        listScroll:SetVerticalScroll(math.max(0, top - 6))
      elseif top + 24 > cur + h then
        listScroll:SetVerticalScroll(math.min(range, top + 30 - h))
      end
    end
  end

  -- A page: its category button, and a layout that fills it top to bottom.
  local page, col
  -- (the page before gets its height, for scrolling)
  local function FinishPage()
    if page and col and not page.agpsOwnHeight then page:SetHeight(math.max(10, -col.y + 16)) end
  end
  -- (`id`: a built-in page's English name, what O.ShowPage asks for in every language; `name` as shown)
  local function Page(name, heading, id)
    FinishPage()
    local sf = CreateFrame("ScrollFrame", nil, area, "UIPanelScrollFrameTemplate")
    sf:SetPoint("TOPLEFT", area, "TOPLEFT", 0, -2)
    sf:SetPoint("BOTTOMRIGHT", area, "BOTTOMRIGHT", -26, 4)
    sf:Hide()
    page = CreateFrame("Frame", nil, sf)
    page:SetSize(PAGE_W - 26, 10)
    sf:SetScrollChild(page)
    local n = #pages + 1
    pages[n] = sf
    trackPage = id
    if id then O.pages[id] = { index = n, scroll = sf, child = page } end -- (a built-in page, by its id)
    pinfo = { index = n, child = page, scroll = sf, groups = {}, rows = {}, top = -44, name = heading or name,
      text = (tostring(name) .. " " .. tostring(heading or "")):lower() }
    search.pages[n] = pinfo
    section, lastRow = nil, nil
    StartGroup("page")
    local t = CreateFrame("Button", nil, listChild)
    t:SetSize(LIST_W - 8, 24)
    t:SetPoint("TOPLEFT", 4, -6 - (n - 1) * 26)
    t.selected = t:CreateTexture(nil, "BACKGROUND")
    t.selected:SetAllPoints()
    t.selected:SetColorTexture(1, 0.82, 0, 0.18)
    local hl = t:CreateTexture(nil, "HIGHLIGHT")
    hl:SetAllPoints()
    hl:SetColorTexture(1, 1, 1, 0.08)
    t.text = t:CreateFontString(nil, "ARTWORK", "GameFontNormal")
    t.text:SetPoint("LEFT", 10, 0)
    t.text:SetText(name)
    t.id = id
    -- (a longer language's page name: a smaller font, then cut short at the list's edge)
    t.text:SetPoint("RIGHT", -4, 0)
    t.text:SetJustifyH("LEFT")
    t.text:SetWordWrap(false)
    t.small = (t.text:GetStringWidth() or 0) > LIST_W - 22
    if t.small then t.text:SetFontObject("GameFontNormalSmall") end
    t:SetScript("OnClick", function()
      if search.on and search.Pick then search.Pick(n) else ShowPage(n) end
    end)
    tabs[n] = t
    pinfo.tab = t
    local title = page:CreateFontString(nil, "ARTWORK", "GameFontHighlightLarge")
    title:SetPoint("TOPLEFT", 16, -12)
    title:SetText(heading or name)
    col = { x = 16, y = -44 }
  end
  local function place(w, h, indent)
    w:SetPoint("TOPLEFT", col.x + (indent or 0), col.y)
    w.padY, w.padH = col.y, h or 26
    if group then -- (the search: its row, and what it reads)
      if pinfo and page == pinfo.child then
        lastRow = { w = w, x = col.x + (indent or 0), y = col.y, h = h or 26, group = group }
        pinfo.rows[#pinfo.rows + 1] = lastRow
        group.rows[#group.rows + 1] = lastRow
      end
      for _, r in ipairs({ w, w.label or false, w.title or false, w.text or false }) do
        if type(r) == "table" and r.GetText then
          local ok, s = pcall(r.GetText, r)
          if ok then AddText(group, s) end
        end
      end
    end
    col.y = col.y - (h or 26)
  end
  local function header(text, note)
    if col.y < -44 then col.y = col.y - 10 end -- space above a new section
    StartGroup("header", text, note)
    local fs = page:CreateFontString(nil, "ARTWORK", "GameFontNormal")
    fs:SetText(text)
    place(fs, 18)
    local line = page:CreateTexture(nil, "ARTWORK")
    line:SetColorTexture(1, 0.82, 0, 0.25)
    line:SetHeight(1)
    line:SetPoint("TOPLEFT", fs, "BOTTOMLEFT", 0, -2)
    line:SetWidth(PAGE_W - 40)
    if lastRow and lastRow.w == fs then
      lastRow.header = true
      also(line)
    end
    if note then -- (wrapped to the page: a long one ran off it, seen 2026-10-03)
      local nt = page:CreateFontString(nil, "ARTWORK", "GameFontDisableSmall")
      nt:SetWidth(PAGE_W - 48)
      nt:SetJustifyH("LEFT")
      nt:SetText(note)
      place(nt, math.max(16, (nt:GetStringHeight() or 0) + 4), 4)
    end
    col.y = col.y - 2
  end
  local function note(text)
    StartGroup("note", text)
    local nt = page:CreateFontString(nil, "ARTWORK", "GameFontDisableSmall")
    nt:SetWidth(PAGE_W - 48)
    nt:SetJustifyH("LEFT")
    nt:SetText(text)
    place(nt, nt:GetStringHeight() + 8, 4)
  end
  -- (`enabled`: gray while it returns false; `indent`: under its parent)
  local function check(label, tip, get, set, enabled, indent)
    local cb = Checkbox(page, label, tip, get, set, enabled)
    AddText(group, tip)
    place(cb, 26, indent)
    return cb
  end
  local function slider(...)
    local s = Slider(page, ...)
    AddText(group, (select(9, ...)))
    place(s, 44)
    return s
  end
  local function Choice(label, options, get, set, enabled, indent)
    for _, o in ipairs(options or {}) do AddText(group, o.text, o.tip) end
    local title = page:CreateFontString(nil, "ARTWORK", "GameFontNormalSmall")
    title:SetText(label)
    place(title, 18, indent and indent + 4)
    local buttons = {}
    for _, o in ipairs(options or {}) do
      local ok, b = pcall(CreateFrame, "CheckButton", nil, page, "UIRadioButtonTemplate")
      if not ok then b = CreateFrame("CheckButton", nil, page, "UICheckButtonTemplate") end
      b:SetSize(16, 16)
      b.text = b.text or b:CreateFontString(nil, "ARTWORK", "GameFontHighlightSmall")
      b.text:ClearAllPoints()
      b.text:SetPoint("LEFT", b, "RIGHT", 4, 0)
      b.text:SetText(o.text or tostring(o.value))
      b.value = o.value
      b:SetScript("OnClick", function()
        set(o.value)
        Apply()
      end)
      if o.tip then
        b:SetScript("OnEnter", function(self)
          GameTooltip:SetOwner(self, "ANCHOR_RIGHT")
          GameTooltip:SetText(o.text or tostring(o.value), 1, 1, 1)
          GameTooltip:AddLine(o.tip, nil, nil, nil, true)
          GameTooltip:Show()
        end)
        b:SetScript("OnLeave", GameTooltip_Hide)
      end
      place(b, 20, 8 + (indent or 0))
      buttons[#buttons + 1] = b
    end
    controls[#controls + 1] = function()
      local v = get()
      local on = not enabled or enabled()
      buttons.agpsOn = on and true or false
      title:SetFontObject(on and "GameFontNormalSmall" or "GameFontDisableSmall")
      for _, b in ipairs(buttons) do
        b:SetChecked(b.value == v)
        b:SetEnabled(on)
        b.text:SetFontObject(on and "GameFontHighlightSmall" or "GameFontDisableSmall")
      end
    end
    Track(buttons)
    return buttons
  end
  -- A dropdown (asked 2026-10-06, API 15: for companions' pages): ui.choice's arguments and refresh. The client's own
  -- (asked 2026-11-04, "I'd rather all dropdowns look like this one": Blizzard_Menu's WowStyle1DropdownTemplate, as a
  -- companion's pages had): a radio each, the one picked checked and shown, a scroll past DROP_ROWS; its menu made
  -- again each time it opens and at each refresh, so options added to the list since show (another addon's charm).
  -- Where the client has none, a box of our own with the one picked and an arrow; a click opens its list under it (a
  -- dark box with a gray edge, a row each, the picked one marked; DROP_ROWS at most, the mouse wheel scrolls the rest),
  -- a click on a row picks it, a click anywhere else closes it (and the window going, Escape).
  local DROP_W, DROP_ROW, DROP_ROWS = 220, 18, 12
  O.DROPDOWN_TEMPLATE = "WowStyle1DropdownTemplate"
  local function GameDropdown(label, options, get, set, enabled)
    local ok, dd = pcall(CreateFrame, "DropdownButton", nil, page, O.DROPDOWN_TEMPLATE)
    if not (ok and dd and dd.SetupMenu) then return nil end
    local title = page:CreateFontString(nil, "ARTWORK", "GameFontNormalSmall")
    title:SetText(label)
    place(title, 18)
    dd:SetWidth(DROP_W)
    dd:SetupMenu(function(_, root)
      if root.SetScrollMode then root:SetScrollMode(DROP_ROWS * 20) end
      for _, o in ipairs(options) do
        local value, text, tip = o.value, o.text or tostring(o.value), o.tip
        local r = root:CreateRadio(text, function() return get() == value end, function()
          set(value)
          Apply()
        end)
        if tip and r and r.SetTooltip and GameTooltip_SetTitle and GameTooltip_AddNormalLine then
          r:SetTooltip(function(t)
            GameTooltip_SetTitle(t, text)
            GameTooltip_AddNormalLine(t, tip)
          end)
        end
      end
    end)
    place(dd, 32, 4)
    dd.options = options
    dd.padGet, dd.padSet = get, function(v) set(v) Apply() end -- (a controller's: PadOptions.lua, never the game's menu)
    -- (with the game's controller UI on, ours in its place, for the mouse and the pad: the game's menu shown or hidden
    -- there runs its controller code, blocked for a menu an addon filled; asked 2026-11-16, "swap all dropdowns to this
    -- when controller UI is enabled and the use the other dropdown style when its not")
    local own = O.OwnDropdown(page, DROP_W, function() return options end, get, function(v) set(v) Apply() end)
    own:SetPoint("TOPLEFT", dd, "TOPLEFT", 0, 0)
    own:Hide()
    also(own)
    dd.own = own
    controls[#controls + 1] = function()
      local on = not enabled or enabled()
      dd.agpsOn = on and true or false
      local ui = ns.GPS and ns.GPS.ControllerUI and ns.GPS.ControllerUI() or false
      if not dd.agpsSearchHid then dd:SetShown(not ui) end
      if not own.agpsSearchHid then own:SetShown(ui) end
      own:Update(on)
      dd:GenerateMenu() -- (the one picked shown; a list grown since)
      if dd.SetEnabled then dd:SetEnabled(on) end
      title:SetFontObject(on and "GameFontNormalSmall" or "GameFontDisableSmall")
    end
    Track(dd)
    return dd
  end
  local function Dropdown(label, options, get, set, enabled)
    options = options or {}
    AddText(group, label)
    for _, o in ipairs(options) do AddText(group, o.text, o.tip) end
    local game = GameDropdown(label, options, get, set, enabled)
    if game then return game end
    local title = page:CreateFontString(nil, "ARTWORK", "GameFontNormalSmall")
    title:SetText(label)
    place(title, 18)
    local box = CreateFrame("Button", nil, page)
    box:SetSize(DROP_W, 22)
    local edge = box:CreateTexture(nil, "BACKGROUND", nil, -1)
    edge:SetPoint("TOPLEFT", -1, 1)
    edge:SetPoint("BOTTOMRIGHT", 1, -1)
    edge:SetColorTexture(0.45, 0.45, 0.45, 0.9)
    local bg = box:CreateTexture(nil, "BACKGROUND")
    bg:SetAllPoints()
    bg:SetColorTexture(0.06, 0.06, 0.06, 0.95)
    local hl = box:CreateTexture(nil, "HIGHLIGHT")
    hl:SetAllPoints()
    hl:SetColorTexture(1, 1, 1, 0.08)
    local text = box:CreateFontString(nil, "ARTWORK", "GameFontHighlightSmall")
    text:SetPoint("LEFT", 8, 0)
    text:SetPoint("RIGHT", -24, 0)
    text:SetJustifyH("LEFT")
    text:SetWordWrap(false)
    box.text = text
    -- (the arrow: a "v" of two short bars, drawn: the old button art is missing in this client)
    for i, a in ipairs({ -math.pi / 4, math.pi / 4 }) do
      local bar = box:CreateTexture(nil, "ARTWORK")
      bar:SetSize(7, 2)
      bar:SetColorTexture(1, 0.82, 0, 1)
      bar:SetPoint("CENTER", box, "RIGHT", i == 1 and -14 or -9.5, 0)
      pcall(bar.SetRotation, bar, a)
    end
    place(box, 28, 4)
    box.options = options
    box.padGet, box.padSet = get, function(v) set(v) Apply() end -- (a controller's: PadOptions.lua)
    local list, catch
    local function Fill()
      local v = get()
      for r, row in ipairs(list.rows) do
        local o = options[list.top + r]
        row.value, row.option = o and o.value, o
        row.text:SetText(o and (o.text or tostring(o.value)) or "")
        row.mark:SetShown(o ~= nil and o.value == v)
      end
    end
    local function Pick(value)
      set(value)
      list:Hide()
      Apply()
    end
    local function Open()
      if not list then
        list = CreateFrame("Frame", nil, box)
        list:SetFrameStrata("FULLSCREEN_DIALOG")
        list:SetFrameLevel(10)
        list:SetWidth(DROP_W)
        list:SetPoint("TOPLEFT", box, "BOTTOMLEFT", 0, -2)
        list:EnableMouse(true)
        list:EnableMouseWheel(true)
        local le = list:CreateTexture(nil, "BACKGROUND", nil, -1)
        le:SetPoint("TOPLEFT", -1, 1)
        le:SetPoint("BOTTOMRIGHT", 1, -1)
        le:SetColorTexture(0.45, 0.45, 0.45, 0.95)
        local lb = list:CreateTexture(nil, "BACKGROUND")
        lb:SetAllPoints()
        lb:SetColorTexture(0.04, 0.04, 0.04, 0.97)
        -- (a click anywhere else: closed; under the list, over everything else)
        catch = CreateFrame("Button", nil, box)
        catch:SetFrameStrata("FULLSCREEN_DIALOG")
        catch:SetFrameLevel(1)
        catch:SetAllPoints(UIParent)
        catch:SetScript("OnClick", function() list:Hide() end)
        catch:Hide()
        list:SetScript("OnShow", function() catch:Show() end)
        list:SetScript("OnHide", function() catch:Hide() end)
        list.rows, list.top = {}, 0
        local n = math.min(#options, DROP_ROWS)
        for r = 1, n do
          local row = CreateFrame("Button", nil, list)
          row:SetSize(DROP_W - 2, DROP_ROW)
          row:SetPoint("TOPLEFT", 1, -1 - (r - 1) * DROP_ROW)
          local rh = row:CreateTexture(nil, "HIGHLIGHT")
          rh:SetAllPoints()
          rh:SetColorTexture(1, 1, 1, 0.1)
          row.mark = row:CreateTexture(nil, "ARTWORK")
          row.mark:SetSize(6, 6)
          row.mark:SetPoint("LEFT", 7, 0)
          row.mark:SetColorTexture(1, 0.82, 0, 1)
          row.text = row:CreateFontString(nil, "ARTWORK", "GameFontHighlightSmall")
          row.text:SetPoint("LEFT", 19, 0)
          row.text:SetPoint("RIGHT", -4, 0)
          row.text:SetJustifyH("LEFT")
          row.text:SetWordWrap(false)
          row:SetScript("OnClick", function(self) if self.option then Pick(self.value) end end)
          row:SetScript("OnEnter", function(self)
            local o = self.option
            if not (o and o.tip) then return end
            GameTooltip:SetOwner(self, "ANCHOR_RIGHT")
            GameTooltip:SetText(o.text or tostring(o.value), 1, 1, 1)
            GameTooltip:AddLine(o.tip, nil, nil, nil, true)
            GameTooltip:Show()
          end)
          row:SetScript("OnLeave", GameTooltip_Hide)
          list.rows[r] = row
        end
        list:SetHeight(n * DROP_ROW + 2)
        list:SetScript("OnMouseWheel", function(_, delta)
          list.top = math.max(0, math.min(#options - #list.rows, list.top - delta))
          Fill()
        end)
      end
      -- (opened on the one picked: a long list scrolled to it)
      local v, at = get(), 1
      for i, o in ipairs(options) do
        if o.value == v then at = i end
      end
      list.top = math.max(0, math.min(#options - #list.rows, at - math.ceil(#list.rows / 2)))
      Fill()
      list:Show()
    end
    box:SetScript("OnClick", function()
      if list and list:IsShown() then list:Hide() else Open() end
    end)
    controls[#controls + 1] = function()
      local v = get()
      local on = not enabled or enabled()
      local shown = v ~= nil and tostring(v) or ""
      for _, o in ipairs(options) do
        if o.value == v then shown = o.text or tostring(o.value) end
      end
      text:SetText(shown)
      text:SetFontObject(on and "GameFontHighlightSmall" or "GameFontDisableSmall")
      title:SetFontObject(on and "GameFontNormalSmall" or "GameFontDisableSmall")
      box.agpsOn = on and true or false
      box:SetEnabled(on)
      if list and list:IsShown() then
        if on then Fill() else list:Hide() end
      end
    end
    Track(box)
    return box
  end

  -- Lay something out in another frame with the page's helpers (header, note, check...), from `y` down: its height.
  local function Into(frame, y, build)
    local p, c = page, col
    page, col = frame, { x = 16, y = y or 0 }
    local ok, err = pcall(build)
    local h = -col.y
    page, col = p, c
    if not ok then error(err, 0) end
    return h
  end
  -- The Help page (below): its tutorial host's sections stacked, the rest hung under them, the page's height.
  local help = {}
  O.help = help
  local function LayoutHelp()
    local y, any = -help.headH, false
    for _, sec in ipairs(O.helpSections) do
      if sec.frame then
        sec.frame:ClearAllPoints()
        sec.frame:SetPoint("TOPLEFT", help.host, "TOPLEFT", 0, y)
        sec.frame.padY = y
        y = y - sec.height
        any = true
      end
    end
    local hostH = any and -y or 0
    help.host:SetShown(any)
    help.host:SetHeight(math.max(1, hostH))
    help.rest:ClearAllPoints()
    help.rest:SetPoint("TOPLEFT", help.page, "TOPLEFT", 0, help.top - hostH)
    help.rest.padY, help.host.padY = help.top - hostH, help.top
    help.rest:SetHeight(math.max(10, help.restH))
    help.height = hostH - help.top + help.restH + 16
    help.page:SetHeight(help.height)
    if help.built then ShowPage(currentPage) end -- (its scroll bar, when it's the page showing)
  end

  -- The pages (1.2.0, asked 2026-11-10: laid out by what a player wants to do, docs/options-1.2.0.md): each option in
  -- one place, the most used first, a dependent one indented under its parent and gray while that's off. `Key` names
  -- the setting the next control changes (O.settingControls: the tests check none is lost or doubled).
  ---------------------------------------------------------------- General
  Page(L["General"], nil, "General")
  header(L["Map"])
  Key("shown")
  check(L["Show the map"], L["The GPS map window. Also: left-click the minimap button, a key (at the end of this section), or /agps toggle."],
    function() return GPS().shown end, function(v) GPS().shown = v end)
  place(KeyBind(page, L["Show/hide key"]))
  -- (asked 2026-11-14: Quick Search, the map open and its search box ready: Core.lua's AzerothGPS_QuickSearch)
  O.QUICK_SEARCH_BINDING = "AZEROTHGPS_SEARCH"
  place(KeyBind(page, L["Quick search key"], O.QUICK_SEARCH_BINDING,
    L["Click, then press a key (Shift, Ctrl or Alt with it if you like). It opens the map with its search box ready, so you can type a place at once. Escape cancels, right-click clears it. Also in the game's Key Bindings, under AddOns."]))
  -- (issue #20: an accidental press mid-fight can't pop the map up)
  Key("keyBlockedInCombat")
  check(L["Key doesn't show the map in combat"], L["In combat, pressing the show/hide key doesn't show the map, so a press by mistake can't pop it up mid-fight. It can still hide the map, and a map already showing stays. The minimap button and /agps toggle work as usual."],
    function() return GPS().keyBlockedInCombat ~= false end, function(v) GPS().keyBlockedInCombat = v end, nil, INDENT)
  -- (asked 2026-10-07: European distances. Nav.FormatDistance: the directions, the arrow window, the steps, the hints)
  -- (asked 2026-11-17: "add option to general to hide X,Y display on pop out map"; GPSFrame's G.PlaceInfo)
  Key("showCoords")
  check(L["Show the coordinates (X, Y)"], L["The X, Y line at the bottom of the map: the spot under the mouse pointer, the crosshair while panning, else you. Off: hidden."],
    function() return GPS().showCoords ~= false end, function(v)
      GPS().showCoords = v
      if ns.GPS and ns.GPS.PlaceInfo then ns.GPS.PlaceInfo() end
    end)
  header(L["Language and units"])
  Key("distanceUnits")
  Dropdown(L["Show distances in"], {
    { value = "yards", text = L["Yards (the game's)"] },
    { value = "metric", text = L["Meters and kilometers"] },
    { value = "imperial", text = L["Feet and miles"] },
  }, function() return GPS().distanceUnits or "yards" end, function(v) GPS().distanceUnits = v end)
  -- (1.2.0: /agps language's setting, AzerothGPSDB.language; read as the files load, so a /reload applies it)
  local languages = { { value = "auto", text = L["The game's language"] } }
  for _, l in ipairs(O.LANGUAGES) do languages[#languages + 1] = { value = l[1], text = l[2] } end
  Key("language")
  Dropdown(L["Show AzerothGPS in"], languages, function() return ns.db and ns.db.language or "auto" end, function(v)
    local want = v ~= "auto" and v or nil
    if not ns.db or ns.db.language == want then return end
    ns.db.language = want
    ns.Print(string.format(L["AzerothGPS's language: %s. Type /reload to apply it."], want or L["the game's"]))
  end)
  note(L["A change of language shows after a /reload."])
  -- (asked 2026-11-10: "if changed add a Apply button to pop up if a /reload is required": there while the language
  -- picked isn't the one loaded; the reload itself is a secure button over it, ns.SecureReloadButton, since an addon's
  -- own click can't reload in this client)
  do
    local apply = Button(page, L["Apply (Reload UI)"], 150, function()
      if not (ns.SaveNow and ns.SaveNow()) then ns.Print(L["Type /reload to apply it."]) end
    end)
    place(apply, 26, 4)
    apply:Hide()
    O.languageApply = apply
    function O.LanguagePending()
      return ((ns.db and ns.db.language) or "auto") ~= (ns.loadedLanguage or "auto")
    end
    local function Sync()
      if O.languageReload then pcall(O.languageReload.Sync) end
    end
    apply:HookScript("OnShow", Sync)
    apply:HookScript("OnHide", Sync)
    controls[#controls + 1] = function()
      local need = O.LanguagePending()
      apply:SetShown(need)
      if need and not O.languageReload and ns.SecureReloadButton then
        O.languageReload = ns.SecureReloadButton(apply, _G.AzerothGPSOptions)
      end
      Sync()
    end
  end
  header(L["Chat"])
  Key("quietChat")
  check(L["Quiet chat: no AzerothGPS messages"], L["AzerothGPS puts none of its messages in the chat window (routes made, quest reminders, tips). The answers to the /agps commands you type still show."],
    function() return GPS().quietChat end, function(v) GPS().quietChat = v end)
  -- (asked 2026-10-06: every place an NPC was met is kept; the ones met in several are left out of the search by default)
  header(L["Search"])
  Key("searchCommonNpcs")
  check(L["Find NPCs met in several places"], L["NPCs you've talked to in places far apart (a guard, a supplier in every town) are left out of the search. On: they're found too, at the place you met them nearest you."],
    function() return GPS().searchCommonNpcs == true end, function(v) GPS().searchCommonNpcs = v end)

  -- (asked 2026-11-10: "4 different map pages... maybe reduce to 2": three. The map itself (how it looks, and where it
  -- shows: the minimap's place, the game's world map), its icons (on it, and on the game's minimap), and its window
  -- (size and looks). Two would put the map and its window on one page three screens long. "Minimap" still opens the
  -- first: O.PAGE_ALIASES.)
  -- (the GPS map in its own window: not in the game's world map, GPSFrame's G.WorldMapWanted; its opacity, fading,
  -- hiding and turning are that window's. And the game's own minimap, not the GPS map in its place.)
  local function OwnWindow()
    return not (GPS().useWorldMap == true and not (ns.GPS and ns.GPS.ControllerUI and ns.GPS.ControllerUI()))
  end
  local function NotReplacing() return GPS().replaceMinimap ~= true end
  ---------------------------------------------------------------- Map
  Page(L["Map"], nil, "Map")
  -- (the world map first, asked 2026-11-12: "move the Show the GPS map in the game's world map to the top of the Map
  -- section")
  header(L["World map"])
  -- (asked 2026-11-10: the GPS map in the game's own world map window, GPSFrame's G.WorldMapHosted)
  Key("useWorldMap")
  check(L["Show the GPS map in the game's world map"], L["The GPS map shows in the game's own world map window (M) instead of a window of its own, with its route, buttons and map styles. The show/hide key, and the logo on the minimap square, open the world map."],
    function() return GPS().useWorldMap == true end, function(v) GPS().useWorldMap = v and true or false end,
    -- (gray with the game's controller UI on: GPSFrame's G.WorldMapWanted)
    function() return not (ns.GPS and ns.GPS.ControllerUI and ns.GPS.ControllerUI()) end)
  header(L["Map style"])
  -- (issue #75: the four map styles, as the Map Style buttons; the OpenMap style (issue #91, Seamless before) once the seamless map's option)
  Key("style")
  Dropdown(L["Map style"], {
    { value = "seamless", text = "OpenMap" },
    { value = "minimap", text = L["Terrain"] },
    { value = "zone", text = L["World Map"] },
    { value = "nospoiler", text = L["No Spoiler Map"] },
  }, function() return GPS().style or "seamless" end, function(v) ns.GPS.SetStyle(v) end)
  Key("seamExploredOnly")
  check(L["Show only explored areas"], L["The OpenMap style's zone art shows only the areas this character has explored, as the game's own world map does; the rest is the zone's blank parchment. The terrain close in is never changed."],
    function() return GPS().seamExploredOnly == true end, function(v) ns.Atlas.SetExploredOnly(v) end,
    function() return (GPS().style or "seamless") == "seamless" end, INDENT)
  -- (asked 2026-11-14: "sliders for adjusting the distance the map transitions from terrain to zone to world map like
  -- we did in the dev addon", then: "zone map to world map doesn't change the distance the map fades between these 2.
  -- Also should be a third one for the fade to world view ... Also want a transition setting for each level":
  -- GPSFrame's G.ApplySeamPlayer turns them into the dev tools' knobs and the art engine's own fades. Where: in the
  -- wheel's notches, shown as the zoom in yards (the distance from the map's middle to its edge); each stage's least
  -- follows the one before, so their order can't turn round. Transition: the blend's length, times the shipped.)
  do
    local G = ns.GPS
    local R = G.SEAM_PLAYER_RANGE
    local function OpenMap() return (GPS().style or "seamless") == "seamless" end
    local function stageSlider(label, range, step, fmt, get, set, tip)
      local s = Slider(page, label, range[1], range[2], step, fmt, get, set, OpenMap, tip)
      AddText(group, tip)
      place(s, 44, INDENT)
      return s
    end
    local function Pct(v) return ("%d%%"):format(math.floor(v * 100 + 0.5)) end
    local function blendSlider(key, label, set, tip)
      Key(key)
      stageSlider(label, R.blend, 0.25, Pct, function() return G.SeamNum(GPS()[key], R.blend[1], R.blend[2], 1) end,
        set, tip)
    end
    Key("seamTerrainYd")
    stageSlider(L["Terrain to zone map"], R.terrain, 0.5, function(n) return ns.Nav.FormatDistance(G.SeamNotchYards(n)) end,
      function() return (G.SeamPlayerStages()) end, function(v) GPS().seamTerrainYd = G.SeamNotchYards(v) end,
      L["How far out the map zooms before the terrain gives way to the zone map. Further out: the terrain stays longer as you zoom out."])
    blendSlider("seamTerrainBlend", L["Terrain transition"], function(v) GPS().seamTerrainBlend = v end,
      L["How long the terrain takes to fade into the zone map as you zoom: the least switches at once, more blends over more of the zoom."])
    Key("seamContinentAt")
    local continent = stageSlider(L["Zone map to continent map"], R.continent, 0.5,
      function(n) return ns.Nav.FormatDistance(G.SeamFadeYards("zone", n)) end,
      function() return select(2, G.SeamPlayerStages()) end, function(v) GPS().seamContinentAt = v end,
      L["How far out the map zooms before the zone map fades into the continent map. Further out: the zone map stays longer as you zoom out."])
    blendSlider("seamContinentBlend", L["Zone map transition"], function(v) GPS().seamContinentBlend = v end,
      L["How long the zone map takes to fade into the continent map as you zoom: the least switches at once, more blends over more of the zoom."])
    Key("seamWorldAt")
    local world = stageSlider(L["Continent map to world map"], R.world, 0.5,
      function(n) return ns.Nav.FormatDistance(G.SeamFadeYards("world", n)) end,
      function() return select(3, G.SeamPlayerStages()) end, function(v) GPS().seamWorldAt = v end,
      L["How far out the map zooms before the continent map fades into the whole world. It's never closer than where the zone map fades."])
    blendSlider("seamWorldBlend", L["Continent map transition"], function(v) GPS().seamWorldBlend = v end,
      L["How long the continent map takes to fade into the world map as you zoom: the least switches at once, more blends over more of the zoom."])
    -- (their least: where the stage before them is now, before their own refresh)
    table.insert(controls, #controls, function()
      local _, _, _, cLeast, wLeast = G.SeamPlayerStages()
      -- (a range change clamps the slider and the client fires OnValueChanged, which would save the clamped value:
      -- Reset to defaults left the world's at -0.17, #367; the settings are the player's alone to change)
      local st = GPS()
      local c, w = st.seamContinentAt, st.seamWorldAt
      continent.slider:SetMinMaxValues(cLeast, R.continent[2])
      world.slider:SetMinMaxValues(wLeast, R.world[2])
      st.seamContinentAt, st.seamWorldAt = c, w
    end)
    -- (asked 2026-11-14: "another slider additional to the open map sliders, set a toleration on how far zooming in on
    -- a building or cave it transitions to the interior view of that building": GPSFrame's G.ZoomedInterior; the
    -- inside maps belong to the terrain view, so every style but the world map ones)
    Key("interiorZoomYd")
    local range = G.INTERIOR_ZOOM_RANGE
    local inside = Slider(page, L["Inside maps when zoomed in"], range[1], range[2], 25,
      function(v) return v <= 0 and L["Off"] or ns.Nav.FormatDistance(v) end,
      function() return G.InteriorZoomYd() end, function(v) GPS().interiorZoomYd = v end,
      function() return not G.IsMapStyle(GPS().style or "seamless") end,
      L["Zoomed in this close over a building or cave, its inside map shows, with a dot for each NPC who offers something there. Off: only when you're inside."])
    AddText(group, L["Zoomed in this close over a building or cave, its inside map shows, with a dot for each NPC who offers something there. Off: only when you're inside."])
    place(inside, 44, INDENT)
    Key("interiorHoldSec")
    local hr = G.INTERIOR_HOLD_RANGE
    local hold = Slider(page, L["Hold an inside map for"], hr[1], hr[2], 5,
      function(v) return v <= 0 and L["Off"] or ("%d s"):format(v) end,
      function() return G.InteriorHoldSec() end, function(v) GPS().interiorHoldSec = v end,
      function() return not G.IsMapStyle(GPS().style or "seamless") and G.InteriorZoomYd() > 0 end,
      L["A left click on a building whose inside map shows keeps it up this long, wherever the mouse goes. Right-click lets it go."])
    AddText(group, L["A left click on a building whose inside map shows keeps it up this long, wherever the mouse goes. Right-click lets it go."])
    place(hold, 44, INDENT)
    -- (the inside maps' two sliders too: asked 2026-11-16, a screenshot, the button grey with Hold at 120 s of 30)
    local KEYS = { "seamContinentAt", "seamWorldAt", "seamTerrainBlend", "seamContinentBlend", "seamWorldBlend",
      "interiorZoomYd", "interiorHoldSec" }
    local reset = Button(page, L["Reset to defaults"], 140, function()
      GPS().seamTerrainYd = nil
      for _, k in ipairs(KEYS) do GPS()[k] = ns.DEFAULTS.gps[k] end
    end)
    place(reset, 30, INDENT + 4)
    O.seamStagesReset = reset -- (the tests)
    controls[#controls + 1] = function()
      local moved = GPS().seamTerrainYd ~= nil
      for _, k in ipairs(KEYS) do moved = moved or GPS()[k] ~= ns.DEFAULTS.gps[k] end
      reset:SetEnabled(OpenMap() and moved)
    end
  end
  note(L["OpenMap (the default): the ground seen from above, and the mouse wheel zooms on out past the land, through zones and continents to the whole world on a stitched world map, and back in to the roads. Right-click zooms out a few steps on the same spot, up to the whole world. Picked again after another style, it loads once the UI is reloaded (a prompt offers it); in the other styles nothing of it is loaded."])
  note(L["Terrain: the ground alone, as far out as the land. World Map: the world map, fully explored. No Spoiler Map: the world map as your character has explored it."])
  Key("routeColor")
  Dropdown(L["Route color"], { { value = "blue", text = L["Blue"] },
    { value = "rainbow", text = L["Rainbow"], tip = L["The colors of the rainbow along the route."] } },
    function() return GPS().routeColor == "rainbow" and "rainbow" or "blue" end, function(v) GPS().routeColor = v end)
  header(L["View"])
  Key("rotate")
  check(L["Turn the map with me"], L["On: the map turns so that where you face is up (heading-up). Off: north stays up and the arrow turns. Not in the game's world map: north stays up there, as on the game's map."],
    function() return GPS().rotate end, function(v) GPS().rotate = v end, OwnWindow)
  Key("approachZoom")
  check(L["Zoom in near a stop"], L["Within 50 yards of your next stop, the map zooms in smoothly so you can see exactly where it is, and back out to your zoom once you're there. Zooming yourself keeps your zoom for that stop."],
    function() return GPS().approachZoom ~= false end, function(v) GPS().approachZoom = v end)
  Key("reopenFollow")
  check(L["Reopen following me"], L["With a route set: if you hid the map while looking around it (dragged or zoomed out to the world map), it opens again centered on you, following your position. Off: it opens where you left it (the button at the bottom right brings it back to you)."],
    function() return GPS().reopenFollow end, function(v) GPS().reopenFollow = v end)
  Key("terrainZoomOut")
  check(L["Right-click opens the world map"], L["In the OpenMap style, right-click zooms out a few steps on the same spot (each right-click a few more, up to the whole world). In the Terrain style, it shows Azeroth: click a continent, then a spot on it, to come back to the terrain view there. Right-click again goes back."],
    function() return GPS().terrainZoomOut ~= false end, function(v) GPS().terrainZoomOut = v end)
  Key("interiors")
  check(L["Building interiors"], L["Inside buildings and caves (e.g. Undercity), the terrain view shows the building's own map, like the minimap."],
    function() return GPS().interiors end, function(v) GPS().interiors = v end)

  ---------------------------------------------------------------- Minimap
  -- (everything about the game's minimap: the GPS map in its place, 1.2.0, asked 2026-11-08, GPSFrame's G.MinimapMode;
  -- and what AzerothGPS puts on the game's own)
  header(L["Minimap"])
  local function Replacing() return GPS().replaceMinimap == true end
  Key("replaceMinimap")
  check(L["Replace the minimap with the GPS map"], L["The GPS map takes the minimap's place in its corner, a square with the minimap's own icons on it (herbs and ore you track, mailboxes, party members, quests). It follows the minimap's zoom and turn. Changed in combat, it waits until the fight ends."],
    Replacing, function(v) GPS().replaceMinimap = v end)
  Key("replaceMinimapSize")
  Choice(L["Minimap size"], {
    { value = "small", text = L["Small"] },
    { value = "medium", text = L["Medium"] },
    { value = "large", text = L["Large"] },
  }, function() return GPS().replaceMinimapSize or "small" end, function(v) GPS().replaceMinimapSize = v end, Replacing, INDENT)
  -- (asked 2026-11-15: the square left as it is while the map is open out of it, both shown)
  Key("replaceMinimapKeepSquare")
  check(L["Keep the minimap while the map is open"], L["The opened GPS map grows out of the minimap corner while the minimap stays as it is, so both show. Off: the game's own minimap goes back to its usual place and shape while the GPS map is open."],
    function() return GPS().replaceMinimapKeepSquare ~= false end, function(v) GPS().replaceMinimapKeepSquare = v end,
    Replacing, INDENT)
  -- (asked 2026-11-09: the map opened from the square goes back by itself as you move, or as a fight starts)
  Key("replaceMinimapCollapseOnMove")
  check(L["Back to the minimap when you move"], L["The opened GPS map goes back to the minimap corner as soon as you start moving."],
    function() return GPS().replaceMinimapCollapseOnMove == true end, function(v) GPS().replaceMinimapCollapseOnMove = v end,
    Replacing, INDENT)
  Key("replaceMinimapCollapseOnCombat")
  check(L["Back to the minimap when combat starts"], L["The opened GPS map goes back to the minimap corner as soon as a fight starts."],
    function() return GPS().replaceMinimapCollapseOnCombat == true end, function(v) GPS().replaceMinimapCollapseOnCombat = v end,
    Replacing, INDENT)
  -- (asked 2026-11-11: how long the opened map waits, or never)
  Key("replaceMinimapIdle")
  slider(L["Back to the minimap after"], 0, 60, 1,
    function(v) return v <= 0 and L["Never"] or Format(L["%d s"], v) end,
    function() return tonumber(GPS().replaceMinimapIdle) or 5 end,
    function(v) GPS().replaceMinimapIdle = math.floor(v + 0.5) end, Replacing,
    L["How long the opened GPS map waits, with nothing done on it, before it goes back to the minimap corner. Never: it stays open until you send it back."])
  ---------------------------------------------------------------- Show on the map
  Page(L["Map icons"], nil, "Layers")
  -- (asked 2026-11-14: the icons' size, "render them in multiple sizes, current is small, make a medium, and large. put
  -- this under the map icon options", and round icons moved here, "put these in their own section above the other
  -- options": GPSFrame's G.ICON_SIZES and G.RoundIcon)
  header(L["Icon look"])
  Key("iconSize")
  Dropdown(L["Icon size"], {
    { value = "small", text = L["Small"] },
    { value = "medium", text = L["Medium"] },
    { value = "large", text = L["Large"] },
  }, function() return GPS().iconSize or "medium" end, function(v) GPS().iconSize = v end)
  Key("roundIcons")
  check(L["Round icons"], L["The map's and minimap's icons are round, in a gold ring, or a class trainer's in its class's color. Off: square, as the game's."],
    function() return GPS().roundIcons ~= false end, function(v) GPS().roundIcons = v end)
  header(L["Shown on the map"])
  note(L["Map style and layers: the round button at the map's bottom-left."])
  note(L["Double-click one to add it as a stop."])
  Key("layerQuests")
  check(L["Quests"], L["Your quests' objectives and turn-ins."],
    function() return GPS().layerQuests end, function(v) GPS().layerQuests = v end)
  Key("layerQuestAreas")
  check(L["Quest areas on the map"], L["Outlines of your quests' objective areas, like on the minimap. Hover one to see the quest's objectives."],
    function() return GPS().layerQuestAreas end, function(v) GPS().layerQuestAreas = v end,
    function() return GPS().layerQuests and true or false end, INDENT)
  Key("layerQuestAreasMinimap")
  check(L["Quest areas on the minimap"], L["Our outlines of your quests' objective areas on the GPS map as your minimap. Off: the game's own quest areas there instead."],
    function() return GPS().layerQuestAreasMinimap ~= false end, function(v) GPS().layerQuestAreasMinimap = v end,
    function() return GPS().layerQuests and true or false end, INDENT)
  Key("poiTaxi")
  check(L["Flight masters"], L["Green: known. Gray: not learned. Yellow: open a flight map once so the addon can tell."],
    function() return GPS().poiTaxi end, function(v) GPS().poiTaxi = v end)
  Key("poiPoi")
  check(L["Points of interest"], L["Places marked on the world map."],
    function() return GPS().poiPoi end, function(v) GPS().poiPoi = v end)
  Key("poiLabels")
  check(L["Place names"], L["Town and area names, when zoomed in."],
    function() return GPS().poiLabels end, function(v) GPS().poiLabels = v end)
  -- (1.2.0: only on the Quick buttons page's "On" column before)
  Key("layerCity")
  check(L["City locations"], L["Places guards pointed out to you (trainers, bank, ...), for all your characters."],
    function() return GPS().layerCity ~= false end, function(v) GPS().layerCity = v end)
  Key("layerInstances")
  check(L["Dungeons and raids"], L["Their entrances, on every map style. Click one for its map, with its bosses in the usual order; right-click goes back out."],
    function() return GPS().layerInstances ~= false end, function(v) GPS().layerInstances = v end)
  Key("layerCaves")
  check(L["Cave entrances"], L["The ways into caves and mines (not on a continent's map). Double-click one for a stop there."],
    function() return GPS().layerCaves ~= false end, function(v) GPS().layerCaves = v end)
  Key("layerHerbs")
  check(L["Herbs"], L["Herbs you've gathered, hovered on the game minimap, right-clicked (without Herbalism) or imported. Saved for all your characters. A farming area (map menu) uses the kinds shown."],
    function() return GPS().layerHerbs ~= false end, function(v) GPS().layerHerbs = v end)
  Key("layerOre")
  check(L["Ore"], L["Mining nodes you've gathered, hovered on the game minimap, right-clicked (without Mining) or imported. Saved for all your characters. A farming area (map menu) uses the kinds shown."],
    function() return GPS().layerOre ~= false end, function(v) GPS().layerOre = v end)
  Key("showCustomPins")
  check(L["Pins"], L["Your pins (Shift + left-click on the map: Options > Tools) and the ones shared with everyone. Double-click one for a stop there; right-click to remove it."],
    function() return GPS().showCustomPins ~= false end, function(v) GPS().showCustomPins = v end)
  -- (asked 2026-11-09: OtherPins.lua)
  Key("otherAddonPins")
  check(L["Show other addons' map icons"], L["Icons other addons put on the game's world map (quest helpers, guides, waypoints) show on this map too, at the same places. Point at one for its own tooltip; double-click for a stop there."],
    function() return GPS().otherAddonPins ~= false end, function(v) GPS().otherAddonPins = v end)
  Key("showParty")
  check(L["Party members"], L["Your party's or raid's members, as round icons of their class in their class's color (their name when you point at one), where the game gives their position. They don't need AzerothGPS themselves."],
    function() return GPS().showParty ~= false end, function(v) GPS().showParty = v end)
  -- (asked 2026-11-14: "sliders for Map icons for how far out their icons are rendered like ore/herbs, city locations,
  -- custom pins, cave entrances, etc": GPSFrame's G.IconShown; yards at the reference size, the top notch always)
  do
    local G = ns.GPS
    local R = G.ICON_YD_RANGE
    local tip = L["Each kind's icons show while the map is zoomed in at least this close (the distance from its middle to its edge), on any map size and in the game's world map. Always: at every zoom."]
    header(L["How far out icons show"], tip)
    local function Yd(v) return v >= G.ICON_YD_ALWAYS and L["Always"] or ns.Nav.FormatDistance(v) end
    local function iconSlider(kind, label, set, on)
      Key(G.ICON_YD_KEYS[kind])
      slider(label, R[1], R[2], R[3], Yd, function() return G.IconYd(kind) end, set, on, tip)
    end
    iconSlider("quests", L["Quests"], function(v) GPS().iconYdQuests = v end, function() return GPS().layerQuests and true or false end)
    iconSlider("taxi", L["Flight masters"], function(v) GPS().iconYdTaxi = v end, function() return GPS().poiTaxi and true or false end)
    iconSlider("poi", L["Points of interest"], function(v) GPS().iconYdPoi = v end, function() return GPS().poiPoi and true or false end)
    iconSlider("city", L["City locations"], function(v) GPS().iconYdCity = v end, function() return GPS().layerCity ~= false end)
    iconSlider("instances", L["Dungeons and raids"], function(v) GPS().iconYdInstances = v end,
      function() return GPS().layerInstances ~= false end)
    iconSlider("caves", L["Cave entrances"], function(v) GPS().iconYdCaves = v end, function() return GPS().layerCaves ~= false end)
    iconSlider("herbs", L["Herbs"], function(v) GPS().iconYdHerbs = v end, function() return GPS().layerHerbs ~= false end)
    iconSlider("ore", L["Ore"], function(v) GPS().iconYdOre = v end, function() return GPS().layerOre ~= false end)
    iconSlider("pins", L["Pins"], function(v) GPS().iconYdPins = v end, function() return GPS().showCustomPins ~= false end)
    local reset = Button(page, L["Reset to defaults"], 140, function()
      for _, k in pairs(G.ICON_YD_KEYS) do GPS()[k] = ns.DEFAULTS.gps[k] end
    end)
    place(reset, 30, 4)
    O.iconYdReset = reset -- (the tests)
    controls[#controls + 1] = function()
      local moved = false
      for _, k in pairs(G.ICON_YD_KEYS) do moved = moved or (GPS()[k] ~= nil and GPS()[k] ~= ns.DEFAULTS.gps[k]) end
      reset:SetEnabled(moved)
    end
  end

  -- (asked 2026-11-12: these came before the GPS map could take the minimap's place, "clarify those are for the game's
  -- minimap not ours when it is shown": with it there, the route and icons are the square's own, and the game's
  -- minimap standing in (dungeons) gets the route and icons whatever these say; the button goes round the square)
  header(L["On the game's minimap"], L["For the game's own minimap. With the GPS map in its place, only the minimap button is used: the GPS map shows your route and its icons itself."])
  Key("minimap.hide")
  check(L["Minimap button"], L["The AzerothGPS button on the game's minimap. Without it, /agps opens this window."],
    function() return not ns.settings.minimap.hide end, function(v) ns.settings.minimap.hide = not v end)
  -- (asked 2026-10-06)
  Key("minimapRoute")
  check(L["Route on the minimap"], L["Your route on the game's minimap too, around you, and the next stop's marker (on the minimap's edge while it's further). It's drawn again only when something on it changes."],
    function() return GPS().minimapRoute ~= false end, function(v) GPS().minimapRoute = v end, NotReplacing)
  Key("minimapIcons")
  check(L["Icons on the minimap"], L["The map's icons on the game's minimap too: your pins, the herbs and ore you know, city places, party members, docks and entrances, each when it's shown on the map. Off by default."],
    function() return GPS().minimapIcons == true end, function(v) GPS().minimapIcons = v end, NotReplacing)
  -- (a bug report, 2026-10-30: EllesmereUI's square minimap, the route cut off at a circle)
  Key("minimapShape")
  Choice(L["Minimap shape"], {
    { value = "auto", text = L["Automatic"], tip = L["What your minimap addon says, or the shape it gives the minimap."] },
    { value = "round", text = L["Round"] },
    { value = "square", text = L["Square"] },
  }, function() return GPS().minimapShape or "auto" end, function(v) GPS().minimapShape = v end, NotReplacing)

  ---------------------------------------------------------------- Map window
  -- (where the window is, its size and frame, and its own looks, asked 2026-11-04: Looks.lua)
  Page(L["Map window"], nil, "Window")
  local LK = ns.Looks
  local function Tints(first)
    local out = first
    for _, t in ipairs(LK.TINTS) do out[#out + 1] = { value = t.key, text = t.name, tip = t.tip } end
    return out
  end
  local function Framed() return GPS().windowFrame ~= false end
  header(L["Position and size"])
  Key("locked")
  check(L["Lock map position"], L["Locks the map in place. Unlocked: drag the window frame's title bar (or the Move tab without the frame, or Shift+drag the map) to move it."],
    function() return GPS().locked end, function(v) GPS().locked = v end)
  local sizeWarn
  local function SizeWarn(text)
    sizeWarn:SetText("|cffff4040" .. text .. "|r")
    local shown = sizeWarn:GetText()
    C_Timer.After(6, function() if sizeWarn:GetText() == shown then sizeWarn:SetText("") end end)
  end
  -- (the sliders show the map as it shows: G.MapSize keeps a saved size between the quick buttons' need and the screen)
  Key("size")
  local sizeSlider = slider(L["Size"], 120, 800, 10, "%d", function() return select(2, ns.GPS.MapSize(nil, true)) end, function(v)
    local nv = ns.GPS.ClampSize and ns.GPS.ClampSize(v, true) or v -- not too small for the quick buttons
    GPS().size = nv -- (any shape: the height; the width has its own slider)
    if nv > v then
      SizeWarn(string.format(L["Can't be smaller than %d with your quick buttons: move some to the menu or hide them (Quick buttons page)."], nv))
    end
  end, nil, L["The map's size on the screen. Dragging the map's bottom-right corner sets it too."])
  -- (up to the screen, less the title bar: a 4K one's whole height too, not 800)
  table.insert(controls, #controls, function() sizeSlider.slider:SetMinMaxValues(120, ns.GPS.SizeMax()) end)
  -- With "Any shape" on (asked 2026-10-04): "Size" splits in two, the height and beside it the width, each set by hand.
  Key("width")
  local widthSlider = Slider(page, L["Width"], 120, 800, 10, "%d",
    function() return (ns.GPS.MapSize(nil, true)) end,
    function(v)
      if not ns.GPS.FreeSize() then return end
      v = math.min(ns.GPS.WidthMax(), v)
      local nv = ns.GPS.ClampWidth and ns.GPS.ClampWidth(v, true) or v -- not too narrow for the buttons going right
      GPS().width = nv
      if nv > v then
        SizeWarn(string.format(L["Can't be narrower than %d with your quick buttons going right: put some going up or hide them (Quick buttons page)."], nv))
      end
    end)
  widthSlider:SetPoint("TOPLEFT", sizeSlider, "TOPRIGHT", 20, 0)
  also(widthSlider) -- (the search: beside the size's slider, with it)
  if lastRow then AddText(lastRow.group, L["Width"]) end
  table.insert(controls, #controls, function() widthSlider.slider:SetMinMaxValues(120, ns.GPS.WidthMax()) end)
  controls[#controls + 1] = function()
    local free = ns.GPS.FreeSize()
    sizeSlider:SetWidth(free and 190 or 260)
    sizeSlider.title:SetText(free and L["Height"] or L["Size"])
    widthSlider:SetWidth(190)
    widthSlider:SetShown(free)
  end
  sizeWarn = page:CreateFontString(nil, "ARTWORK", "GameFontNormalSmall")
  sizeWarn:SetWidth(PAGE_W - 60)
  sizeWarn:SetJustifyH("LEFT")
  place(sizeWarn, 26, 4)
  -- (on by default, asked 2026-10-03; off while the map's position is locked, back on when it's unlocked)
  Key("lockSize")
  check(L["Resize from the corner"], L["Drag the map window's bottom-right corner to resize it (on by default). While Lock map position is on, the corner doesn't resize; unlock the map and it does again. Off: the size only changes with the slider above."],
    function() return GPS().lockSize == false end, function(v) GPS().lockSize = not v end,
    function() return not GPS().locked end)
  -- (asked 2026-10-04: "make square default and have a check box ... to freely size the map however")
  Key("freeSize")
  check(L["Any shape"], L["Dragging the corner sets the map's width and height separately, to any shape (a wide map on a wide or 4K screen, say). Off (the default): the map stays square."],
    function() return GPS().freeSize == true end, function(v)
      GPS().freeSize = v
      GPS().width = v and GPS().size or nil -- (on: from square; off: square again at its height)
    end, function() return not GPS().locked and GPS().lockSize == false end, INDENT)
  -- (asked 2026-10-04: with it on, a note that the corner on the map sizes it too, while the map isn't locked)
  local anyNote = page:CreateFontString(nil, "ARTWORK", "GameFontDisableSmall")
  anyNote:SetWidth(PAGE_W - 90)
  anyNote:SetJustifyH("LEFT")
  anyNote:SetText(L["While Lock map position is off, you can also drag the map's bottom-right corner to any width and height."])
  place(anyNote, 28, 46)
  controls[#controls + 1] = function() anyNote:SetShown(ns.GPS.FreeSize() == true) end
  header(L["Frame and buttons"], L["Other windows keep the game's own look."])
  Key("windowFrame")
  check(L["Window frame"], L["The game-style window frame around the map: title bar, logo and close button. Off: just the map."],
    Framed, function(v) GPS().windowFrame = v end)
  Key("windowTint")
  Dropdown(L["Frame color"], Tints({ { value = "default", text = L["AzerothGPS's own"] } }),
    function() return GPS().windowTint or "default" end, function(v) GPS().windowTint = v end, Framed)
  Key("windowClose")
  Dropdown(L["Close button (X)"], Tints({ { value = "buttons", text = L["Same as the buttons"] },
    { value = "default", text = L["The game's own"] }, { value = "frame", text = L["Match the frame"] } }),
    function() return GPS().windowClose or "buttons" end, function(v) GPS().windowClose = v end, Framed)
  Key("windowButtons")
  Dropdown(L["Buttons"], Tints({ { value = "default", text = L["The game's own"] },
    { value = "frame", text = L["Match the frame"], tip = L["The frame color's (above)."] } }),
    function() return GPS().windowButtons or "default" end, function(v) GPS().windowButtons = v end)
  header(L["Charm"], L["A legendary weapon hanging on a string from the AzerothGPS logo."])
  -- (one list: a charm another addon adds later goes on it, Looks.AddCharm)
  LK.charmOptions = { { value = "none", text = L["None"] } }
  for _, c in ipairs(LK.Charms()) do LK.charmOptions[#LK.charmOptions + 1] = { value = c.key, text = c.name, tip = c.tip } end
  local function Charmed() return LK.Charm(GPS().charm) and GPS().charm or "none" end
  Key("charm")
  Dropdown(L["Charm"], LK.charmOptions, Charmed, function(v) GPS().charm = v end, Framed)
  Key("charmSwing")
  check(L["Swings while you move"], L["Turning swings it out of the turn and the road jostles it; it twists on its string and settles when you stop. Off: it hangs still, facing you."],
    function() return GPS().charmSwing ~= false end, function(v) GPS().charmSwing = v end,
    function() return Framed() and Charmed() ~= "none" end, INDENT)
  header(L["Arriving"], L["A little celebration over the map when you reach your trip's last stop."])
  local effects = {}
  for _, e in ipairs(LK.EFFECTS) do effects[#effects + 1] = { value = e.key, text = e.name } end
  effects[#effects + 1] = { value = "none", text = L["None"] }
  Key("arrivalEffect")
  Dropdown(L["Celebration"], effects, function() return GPS().arrivalEffect or "confetti" end,
    function(v) GPS().arrivalEffect = v end)
  place(Button(page, L["Try It"], 100, function()
    local e = GPS().arrivalEffect or "confetti"
    if e ~= "none" then LK.Play(e) end
  end), 30, 4)

  ---------------------------------------------------------------- Opacity and combat
  Page(L["Opacity and combat"], nil, "Opacity")
  -- (asked 2026-11-12: "the opacity settings, turn with me, etc is for the GPS map only not if using the in game map":
  -- in the world map the map is that window's child, fading and hiding with it, GPSFrame's G.MapFades)
  header(L["Map"], L["For the GPS map's own window. In the game's world map, the map fades and hides with that window instead and always takes clicks (click-through still works for the direction arrow)."])
  Key("alpha")
  slider(L["Map opacity"], 5, 100, 5, "%d%%",
    function() return math.floor(GPS().alpha * 100 + 0.5) end, function(v) GPS().alpha = v / 100 end, OwnWindow,
    L["How solid the whole map window is: lower shows the game world through it."])
  Key("fadeMoving")
  check(L["Fade the map while moving"], L["While you move, the map fades to the opacity below, leaving the route, the stop markers and your arrow as they are. It comes back a moment after you stop, or right away when you point at the map."],
    function() return GPS().fadeMoving end, function(v) GPS().fadeMoving = v end, OwnWindow)
  Key("movingAlpha")
  slider(L["Map opacity while moving"], 0, 100, 5, "%d%%",
    function() return math.floor((GPS().movingAlpha or 0.4) * 100 + 0.5) end, function(v) GPS().movingAlpha = v / 100 end,
    function() return GPS().fadeMoving and OwnWindow() end)
  header(L["In combat"])
  Key("combatHideMap")
  check(L["Hide the map"], L["Hidden while you're in combat, so nothing on it gets clicked by mistake mid-fight. It comes back when combat ends."],
    function() return GPS().combatHideMap end, function(v) GPS().combatHideMap = v end, OwnWindow)
  Key("combatAlpha")
  slider(L["Map opacity in combat"], 0, 100, 5, "%d%%",
    function() return math.floor((GPS().combatAlpha or GPS().alpha) * 100 + 0.5) end, function(v) GPS().combatAlpha = v / 100 end,
    function() return not GPS().combatHideMap and OwnWindow() end)
  Key("combatHideArrow")
  check(L["Hide the direction arrow"], L["Hidden while you're in combat. It comes back when combat ends."],
    function() return GPS().combatHideArrow end, function(v) GPS().combatHideArrow = v end)
  Key("arrowCombatAlpha")
  slider(L["Arrow opacity in combat"], 0, 100, 5, "%d%%",
    function() return math.floor((GPS().arrowCombatAlpha or 1) * 100 + 0.5) end, function(v) GPS().arrowCombatAlpha = v / 100 end,
    function() return not GPS().combatHideArrow end)
  header(L["Click-through"], L["Clicks go to the game world (targeting, the camera), not the map or arrow."])
  Key("clickThroughMoving")
  check(L["Click-through while moving"], L["While you move, the map and the direction arrow ignore the mouse, so a click there targets or turns the camera instead. They take clicks again a moment after you stop."],
    function() return GPS().clickThroughMoving end, function(v) GPS().clickThroughMoving = v end)
  Key("clickThroughCombat")
  check(L["Click-through in combat"], L["In combat, the map and the direction arrow ignore the mouse, so a click there targets or turns the camera instead."],
    function() return GPS().clickThroughCombat end, function(v) GPS().clickThroughCombat = v end)

  ---------------------------------------------------------------- Routing
  Page(L["Routing"], nil, "Routing")
  header(L["Routes"])
  Key("useFlights")
  check(L["Use flight paths"], L["Routes take flights (connecting ones too) between the flight masters this character knows, when that's faster. The addon learns which ones you know from the flight map: open it once at any flight master."],
    function() return GPS().useFlights ~= false end, function(v)
      GPS().useFlights = v
      ns.Nav.OptionsChanged()
    end)
  Key("useHearthstone")
  check(L["Use hearthstone"], L["Routes may start with your Hearthstone (or a shaman's Astral Recall) when it's in your bags, off cooldown, and faster. Home is your inn's town; the exact spot is learned after your first hearth. The directions say when; click the button beside them to use it."],
    function() return GPS().useHearthstone ~= false end, function(v)
      GPS().useHearthstone = v
      ns.Nav.OptionsChanged()
    end)
  Key("useTeleports")
  check(L["Use class teleports and teleport items"], L["Routes may start with a mage's teleport (with a Rune of Teleportation), Teleport: Moonglade, or an engineer's Dimensional Ripper - Everlook or Ultrasafe Transporter: Gadgetzan (with the specialization it needs) when it's known or in your bags, off cooldown, and faster. Click the button beside the directions to use it."],
    function() return GPS().useTeleports ~= false end, function(v)
      GPS().useTeleports = v
      ns.Nav.OptionsChanged()
    end)
  Key("avoidHighZones")
  check(L["Avoid zones too high for your level"], L["Routes go around zones whose levels are red for your character (their lowest level more than 4 above yours) when there's another way, like the other faction's towns. The zones you start and end in don't count."],
    function() return GPS().avoidHighZones ~= false end, function(v) GPS().avoidHighZones = v ns.Nav.OptionsChanged() end)
  Key("avoidHostile")
  check(L["Avoid the other faction's towns"], L["Routes keep away from the other faction's guards (their towns and camps, and where their guards patrol), going around when there's a way. A stop inside one is still reached, the shortest way in."],
    function() return GPS().avoidHostile ~= false end, function(v)
      GPS().avoidHostile = v
      ns.Nav.OptionsChanged()
    end)
  -- (asked 2026-11-04: how much the roads are kept; Router.RoadFactor)
  Key("roadTolerance")
  slider(L["Road tolerance"], ns.Router.ROAD_TOLERANCE_MIN, ns.Router.ROAD_TOLERANCE_MAX, 1,
    function(v) return v == 0 and L["0 (as AzerothGPS chooses)"] or string.format("%+d", v) end,
    function() return GPS().roadTolerance or 0 end, function(v)
      GPS().roadTolerance = v
      ns.Nav.OptionsChanged()
    end)
  note(L["Below 0, routes keep to the roads more and more; above 0, they cut straight across open ground more and more, at the top as if the roads weren't there."])
  header(L["Stops"])
  Key("fastestOrder")
  check(L["Visit stops in the fastest order"], L["Routes with several stops visit them in the fastest order instead of the order you placed them. (Double-click the map to place stops.)"],
    function() return GPS().fastestOrder end, function(v)
      GPS().fastestOrder = v
      if v and #ns.Nav.stops > 1 and not ns.Nav.KeepCityOrder() then ns.Nav.OrderStops() end
    end)
  Key("cityKeepOrder")
  check(L["Except in cities"], L["Stops down in a city (Undercity) are visited in the order you placed them among themselves: how you want to go around a city is up to you. Stops outside the city still go in the fastest order. (A quest route is always put in the fastest order.)"],
    function() return GPS().cityKeepOrder ~= false end, function(v) GPS().cityKeepOrder = v end,
    function() return GPS().fastestOrder and true or false end, INDENT)
  Key("questZoneOnly")
  check(L["Quest route: only this zone"], L["The Quest Route button takes only the quests whose objective or turn-in is in the zone you're in (a city counts as its zone). Off: every quest in your log, anywhere."],
    function() return GPS().questZoneOnly end, function(v) GPS().questZoneOnly = v end)
  Key("questAutoReroute")
  check(L["Quest route: reroute by itself"], L["When you pick up or finish a quest on a quest route, the route is made again with it by itself, as clicking the pulsing Sprint icon in the directions does. Off: the icon pulses until you click it. (Either way, quest stops you removed stay out of the route until it ends.)"],
    function() return GPS().questAutoReroute end, function(v) GPS().questAutoReroute = v end)
  Key("questPickRoute")
  check(L["Quest route: the quest you pick"], L["Pick a quest in your quest log or in the objective tracker (click it to focus it) and the route goes to that quest's objectives and turn-in. Off: only the Quest Route button makes a quest route."],
    function() return GPS().questPickRoute end, function(v) GPS().questPickRoute = v end)
  Key("navCloseClears")
  check(L["X on the route panel cancels the route"], L["The X at the top right of the map's route panel (the steps) cancels the whole route. Off: it only closes the panel until the route changes, and the route goes on."],
    function() return GPS().navCloseClears end, function(v) GPS().navCloseClears = v end)
  header(L["Waypoints and sharing"])
  Key("acceptWay")
  check(L["Accept TomTom /way commands"], L["/way lines typed or pasted in chat add stops to the route (several pasted lines at once become several stops). With TomTom installed, its waypoint is set too. Questie's \"Set TomTom Target\" adds a stop the same way."],
    function() return GPS().acceptWay ~= false end, function(v) GPS().acceptWay = v end)
  Key("acceptMapPins")
  check(L["Map pin links add stops"], L["Clicking a map pin someone posted in chat (\"[Map Pin Location]\") adds a stop there. To share a spot yourself, Ctrl + left-click it on the map for the map pin (a diamond, the game's own waypoint), then Shift + left-click the pin; Ctrl + left-click it again removes it."],
    function() return GPS().acceptMapPins ~= false end, function(v) GPS().acceptMapPins = v end)
  Key("acceptShared")
  check(L["Accept routes shared by players"], L["Route links other AzerothGPS users post in chat (\"[AzerothGPS Route: 3 stops]\", from the Import and Share window) can be clicked to get their route. Nothing comes in unless you click one, and you're asked before it replaces yours."],
    function() return GPS().acceptShared ~= false end, function(v) GPS().acceptShared = v end)
  place(Button(page, L["Import and Share..."], 200, function() ns.Import.Toggle() end), 30, 4)
  -- (asked 2026-10-03) each zeppelin, boat and the tram, on by default: unticked, never in a route (also: right-click
  -- its dock on the map). Only your faction's (Nav.TransportUsable). Last on the page: the list is long.
  header(L["Zeppelins, boats and the tram"], L["Unticked ones are never used in routes. Right-clicking a dock on the map does the same."])
  local function Town(name) return ((name or "?"):match("^[^,]+")) end
  for _, kind in ipairs({ { "zeppelin", L["Zeppelins"], L["Routes may take the zeppelin between %s and %s. Unticked: never."] },
    { "boat", L["Boats"], L["Routes may take the boat between %s and %s. Unticked: never."] },
    { "tram", L["The Deeprun Tram"], L["Routes may take the Deeprun Tram between %s and %s. Unticked: never."] } }) do
    local rows = {}
    for _, t in ipairs(ns.Transports or {}) do
      if t[8] == kind[1] and ns.Nav.TransportUsable(t) then rows[#rows + 1] = t end
    end
    if #rows > 0 then
      local sub = page:CreateFontString(nil, "ARTWORK", "GameFontHighlight")
      sub:SetText(kind[2])
      place(sub, 20, 4)
      table.sort(rows, function(a, b) return Town(a[9]) .. Town(a[10]) < Town(b[9]) .. Town(b[10]) end)
      for _, t in ipairs(rows) do
        local label = Town(t[9]) .. " - " .. Town(t[10])
        place(Checkbox(page, label, Format(kind[3], t[9] or "?", t[10] or "?"),
          function() return ns.Nav.RideAllowed(t) end, function(v) ns.Nav.SetRideAllowed(t, v) end), 26, 20)
      end
    end
  end

  ---------------------------------------------------------------- Directions
  Page(L["Directions"], nil, "Directions")
  local function ArrowOn() return GPS().arrow and true or false end
  local function DirOn() return ArrowOn() and GPS().dirShown ~= false end
  header(L["Quests"])
  -- Questing objective tracker, with the ! the arrow shows in a quest's area (on this page since 2026-10-16; at its top since 2026-11-15, asked)
  local qholder = CreateFrame("Frame", nil, page)
  qholder:SetSize(360, 24)
  StartGroup("setting", L["Questing objective tracker"])
  place(qholder, 24)
  local qmarker = qholder:CreateFontString(nil, "ARTWORK", "GameFontHighlight")
  qmarker:SetText("|cffffd100!|r")
  qmarker:SetPoint("LEFT", 12, 0)
  local qcb = CreateFrame("CheckButton", nil, qholder, "UICheckButtonTemplate")
  qcb:SetSize(20, 20)
  qcb:SetPoint("LEFT", qmarker, "RIGHT", 6, 0)
  local qtext = qcb:CreateFontString(nil, "ARTWORK", "GameFontHighlightSmall")
  qtext:SetPoint("LEFT", qcb, "RIGHT", 2, 0)
  qtext:SetText(L["Questing objective tracker"])
  qcb:SetScript("OnClick", function(self)
    GPS().questing = self:GetChecked()
    ns.Nav.Invalidate(true, true)
    Apply()
  end)
  qcb:SetScript("OnEnter", function(self)
    GameTooltip:SetOwner(self, "ANCHOR_RIGHT")
    GameTooltip:SetText(L["Questing objective tracker"], 1, 1, 1)
    GameTooltip:AddLine(L["A stop inside a quest's area (the blue outlines, for quests in your log) is done when that quest's objectives are, not when you get there. In the area, the route waits and the arrow shows a ! and the objective counters. Leave before they're done and the route leads back; then it goes on to the next stop."], nil, nil, nil, true)
    GameTooltip:Show()
  end)
  qcb:SetScript("OnLeave", GameTooltip_Hide)
  controls[#controls + 1] = function() qcb:SetChecked(GPS().questing ~= false) end
  Key("questing")
  Track(qcb)
  header(L["Direction arrow"])
  Key("arrow")
  check(L["Show direction arrow"], L["Two small panels (TomTom style): an arrow along the route, and beside it the directions: the next turn (\"Turn left 120 yd, toward Razor Hill\"), the stop's distance and ETA, and the stops after it when made taller."],
    function() return GPS().arrow end, function(v) GPS().arrow = v end)
  Key("arrowLocked")
  check(L["Lock arrow position"], L["Locks the arrow and the directions in place. Unlocked: drag them to move them and the directions' corner to resize them (taller lists the later stops). With no route they show a placeholder while unlocked, so you can place them. Locked, clicks pass through them to the game world."],
    function() return GPS().arrowLocked end, function(v) GPS().arrowLocked = v end, ArrowOn, INDENT)
  Key("arrowPx")
  slider(L["Arrow size"], ns.Arrow.ARROW_PX_MIN, ns.Arrow.ARROW_PX_MAX, 2, L["%d px"],
    function() return GPS().arrowPx or ns.Arrow.ARROW_PX end, function(v) GPS().arrowPx = v end, ArrowOn)
  Key("arrowBg")
  slider(L["Arrow background"], 0, 100, 5, "%d%%",
    function() return math.floor((GPS().arrowBg or 0.55) * 100 + 0.5) end, function(v) GPS().arrowBg = v / 100 end, ArrowOn,
    L["How dark the panel behind the arrow is. At 0, the arrow alone."])
  -- (the arrow and the directions two panels, asked 2026-10-30)
  header(L["Directions panel"])
  Key("dirShown")
  check(L["Show the directions"], L["The panel beside the arrow with the next turn, the stop's distance and ETA and the stops after it. Off: the arrow alone."],
    function() return GPS().dirShown ~= false end, function(v) GPS().dirShown = v end, ArrowOn)
  Key("dirStopsOnly")
  check(L["List the stops only"], L["The directions list the route's stops, each with its distance and ETA, without the turns (\"Continue straight, then turn left in 280 yd\")."],
    function() return GPS().dirStopsOnly == true end, function(v) GPS().dirStopsOnly = v end, DirOn, INDENT)
  Key("arrowSnap")
  check(L["Snap the arrow to the directions"], L["The arrow sits against a side of the directions and the two move as one: drag the directions to move both. Unlocked, drag the arrow away to move it on its own, and drop it against a side of the directions to snap it there again."],
    function() return GPS().arrowSnap ~= false end, function(v) GPS().arrowSnap = v end, DirOn, INDENT)
  Key("arrowSide")
  Choice(L["Arrow side"], {
    { value = "left", text = L["Left"] },
    { value = "right", text = L["Right"] },
    { value = "top", text = L["Above"] },
    { value = "bottom", text = L["Below"] },
  }, function() return GPS().arrowSide or "left" end, function(v) GPS().arrowSide = v end,
    function() return DirOn() and GPS().arrowSnap ~= false end, INDENT * 2)
  Key("dirTextScale")
  slider(L["Text size"], 70, 160, 5, "%d%%",
    function() return math.floor((GPS().dirTextScale or 1) * 100 + 0.5) end, function(v) GPS().dirTextScale = v / 100 end, DirOn)
  Key("dirBg")
  slider(L["Directions background"], 0, 100, 5, "%d%%",
    function() return math.floor((GPS().dirBg or GPS().arrowBg or 0) * 100 + 0.5) end, function(v) GPS().dirBg = v / 100 end, DirOn,
    L["How dark the panel behind the directions is. At 0, the text alone."])
  header(L["How it works"])
  note(L["The arrow points along the route: |cff73ff73green|r straight ahead, |cffffffffwhite|r for a turn coming up, |cffff7359red|r when the route is behind you. On a flight it shows where you land and when."])
  note(L["The directions' lines: the next turn and its distance, the road or place you're heading toward, the stop with its distance and ETA, then the turn after that. With List the stops only, just the stops."])
  note(L["To move them, untick Lock arrow position, then drag them; drag the directions' bottom-right corner to resize them. Made taller, they list the later stops too. Unlocked with no route, they show a placeholder so you can place them."])
  note(L["Drag the arrow off the directions to move it on its own; drop it against any side of them and it snaps there. Dragging the directions takes a snapped arrow along."])
  note(L["In a quest's area the arrow shows a ! and the directions the quest's objectives. A small Sprint icon pulsing in the directions' top-right corner means you picked up or finished a quest after making your quest route: click it (or the quest route button on the map) to make the route again with it or its turn-in."])

  ---------------------------------------------------------------- Quick buttons
  Page(L["Quick buttons"], nil, "Quick buttons")
  pinfo.whole = true -- (laid out by hand: the search shows all of it or none)
  header(L["Where each one goes"])
  note(L["Always shown: next to the map button, going up or to the right. In the menu: slides out past those when you click the map button (it closes after 20 seconds untouched). Hidden: not on the map (the setting still works). A group (map style, quests, herbs and ore) is one button: click it and its buttons slide out beside it. ^ and v set the order."])
  local fit = page:CreateFontString(nil, "ARTWORK", "GameFontDisableSmall")
  fit:SetWidth(PAGE_W - 60)
  fit:SetJustifyH("LEFT")
  place(fit, 18, 4)
  local qwarn = page:CreateFontString(nil, "ARTWORK", "GameFontNormalSmall")
  qwarn:SetWidth(PAGE_W - 60)
  qwarn:SetJustifyH("LEFT")
  place(qwarn, 28, 4)
  controls[#controls + 1] = function()
    local up, right = 0, 0
    if ns.GPS.QuickCapacity then up, right = ns.GPS.QuickCapacity() end
    fit:SetText(Format(L["At the map's size: %d fit going up and %d going right (always shown and in the menu together)."], up, right))
  end
  local function Warn(text)
    qwarn:SetText(text and ("|cffff4040" .. text .. "|r") or "")
    if text then
      local shown = qwarn:GetText()
      C_Timer.After(8, function() if qwarn:GetText() == shown then qwarn:SetText("") end end)
    end
  end
  -- the columns: place, x, heading
  local COLS = { { "barUp", 168 }, { "barRight", 204 }, { "menuUp", 252 }, { "menuRight", 288 }, { "hidden", 336 } }
  local ON_X = 380
  local heads = CreateFrame("Frame", nil, page)
  heads:SetSize(PAGE_W - 40, 30)
  local function Head(text, x, y, w)
    local fs = heads:CreateFontString(nil, "ARTWORK", "GameFontNormalSmall")
    fs:SetPoint("TOP", heads, "TOPLEFT", x, y)
    if w then fs:SetWidth(w) end
    fs:SetText(text)
  end
  Head(L["Always shown"], 186 + 12, 0, 90)
  Head(L["In the menu"], 270 + 12, 0, 90)
  Head(L["Up"], 168 + 12, -14)
  Head(L["Right"], 204 + 12, -14)
  Head(L["Up"], 252 + 12, -14)
  Head(L["Right"], 288 + 12, -14)
  Head(L["Hidden"], 336 + 12, -14)
  Head(L["On"], ON_X + 12, -14)
  place(heads, 32)
  -- one row per button or group, in their order (^ / v move one)
  local rowsTop, rowsX, rowById = col.y, col.x, {}
  local function OrderRows()
    for i, t in ipairs(ns.GPS.QuickSlots and ns.GPS.QuickSlots() or {}) do
      local row = rowById[t.id]
      if row then
        row:ClearAllPoints()
        row:SetPoint("TOPLEFT", rowsX, rowsTop - (i - 1) * 24)
        row.padY, row.padH = rowsTop - (i - 1) * 24, 24
      end
    end
  end
  local function Arrow(row, text, x, id, delta, tip)
    local b = CreateFrame("Button", nil, row)
    b:SetSize(14, 16)
    b:SetPoint("LEFT", row, "LEFT", x, 0)
    local fill = b:CreateTexture(nil, "BACKGROUND")
    fill:SetAllPoints()
    fill:SetColorTexture(0.3, 0.25, 0.1, 0.8)
    local hl = b:CreateTexture(nil, "HIGHLIGHT")
    hl:SetAllPoints()
    hl:SetColorTexture(1, 1, 1, 0.2)
    local fs = b:CreateFontString(nil, "OVERLAY", "GameFontNormalSmall")
    fs:SetPoint("CENTER", 0, 0)
    fs:SetText(text)
    b:SetScript("OnClick", function()
      ns.GPS.MoveSlot(id, delta)
      OrderRows()
    end)
    b:SetScript("OnEnter", function(self)
      GameTooltip:SetOwner(self, "ANCHOR_RIGHT")
      GameTooltip:SetText(tip, 1, 1, 1)
      GameTooltip:Show()
    end)
    b:SetScript("OnLeave", GameTooltip_Hide)
  end
  local slots = {}
  for _, t in ipairs(ns.GPS.QuickSlots and ns.GPS.QuickSlots() or {}) do
    if not t.custom then slots[#slots + 1] = t end -- (the searches: their own section, below)
  end
  for _, t in ipairs(slots) do
    local row = CreateFrame("Frame", nil, page)
    row:SetSize(PAGE_W - 40, 24)
    rowById[t.id] = row
    Arrow(row, "^", 0, t.id, -1, L["Earlier (nearer the map button)"])
    Arrow(row, "v", 16, t.id, 1, L["Later (further from the map button)"])
    local icon = row:CreateTexture(nil, "ARTWORK")
    icon:SetSize(18, 18)
    icon:SetPoint("LEFT", 34, 0)
    if t.icon then
      ns.SetIcon(icon, t.icon, "Interface\\Icons\\INV_Misc_QuestionMark")
    elseif t.id == "search" then
      ns.SetIcon(icon, "atlas:common-search-magnifyingglass", "Interface\\Icons\\INV_Misc_Spyglass_03")
    else
      icon:SetTexture("Interface\\Icons\\Ability_Rogue_Sprint")
    end
    local label = row:CreateFontString(nil, "ARTWORK", "GameFontHighlightSmall")
    label:SetPoint("LEFT", icon, "RIGHT", 4, 0)
    label:SetWidth(108)
    label:SetJustifyH("LEFT")
    label:SetText(t.label)
    if t.group then
      row:SetScript("OnEnter", function(self)
        GameTooltip:SetOwner(self, "ANCHOR_RIGHT")
        GameTooltip:SetText(t.label, 1, 1, 1)
        local names = {}
        for _, m in ipairs(t.members) do names[#names + 1] = m.label end
        GameTooltip:AddLine(string.format(L["A group: %s."], table.concat(names, L[", "])), nil, nil, nil, true)
        GameTooltip:Show()
      end)
      row:SetScript("OnLeave", GameTooltip_Hide)
    end
    local boxes = {}
    for _, c in ipairs(COLS) do
      local cb = CreateFrame("CheckButton", nil, row, "UICheckButtonTemplate")
      cb:SetSize(22, 22)
      cb:SetPoint("LEFT", row, "LEFT", c[2] + 1, 0)
      cb:SetScript("OnClick", function()
        local q = GPS().quick or {}
        GPS().quick = q
        if not ns.GPS.QuickFits({ t.id, c[1] }) then
          Warn(Format(L["No room for %s there at this map size (it would need %s). Make the map bigger (Map window: %s), or move or hide another one."],
            t.label, ns.GPS.QuickNeedText({ t.id, c[1] }), ns.GPS.FreeSize() and L["Height and Width"] or L["Size"]))
        else
          Warn(nil)
          q[t.id] = c[1]
        end
        Apply()
      end)
      boxes[c[1]] = cb
    end
    local on
    if t.key then
      on = CreateFrame("CheckButton", nil, row, "UICheckButtonTemplate")
      on:SetSize(22, 22)
      on:SetPoint("LEFT", row, "LEFT", ON_X + 1, 0)
      on:SetScript("OnClick", function(self)
        GPS()[t.key] = self:GetChecked() and true or false
        if t.route then ns.Nav.OptionsChanged() end
        Apply()
      end)
      on:SetScript("OnEnter", function(self)
        GameTooltip:SetOwner(self, "ANCHOR_RIGHT")
        GameTooltip:SetText(t.label, 1, 1, 1)
        GameTooltip:AddLine(t.tip, nil, nil, nil, true)
        GameTooltip:Show()
      end)
      on:SetScript("OnLeave", GameTooltip_Hide)
      Key(t.key) -- (its own checkbox is on its page: this one a second, kept beside the button's place)
      Track(on, true)
    end
    controls[#controls + 1] = function()
      local where = ns.GPS.QuickPlace(t.id)
      for id, cb in pairs(boxes) do cb:SetChecked(id == where) end
      if on then
        on:SetChecked(ns.GPS.QuickOn(t))
        on:SetEnabled(not t.needs or GPS()[t.needs] and true or false)
      end
    end
  end
  col.y = col.y - #slots * 24
  controls[#controls + 1] = OrderRows
  -- Searches (1.3.5, asked 2026-11-16): the account's, Quick Find's own among them (ns.Searches): a row each, its icon
  -- and name, where it goes (a dropdown) and small Edit and Remove buttons; Add Search and Restore Defaults above them.
  -- (asked 2026-11-16, "Buttons are cutoff, look terrible": every part of a row inside the page, O.SEARCH_ROW's)
  local Sx = ns.Searches
  header(L["Search buttons"], L["Each finds the nearest place for what it searches, from where you are, and makes it your destination: in Quick Find, or a button of its own in the map menu. For every character on this account."])
  local addBtn = Button(page, L["Add Search"], 120, function() Sx.Edit(nil) end)
  place(addBtn, 30, 4)
  local restoreBtn = Button(page, L["Restore Defaults"], 140, function() Sx.RestoreDefaults() end)
  restoreBtn:SetPoint("LEFT", addBtn, "RIGHT", 6, 0)
  also(restoreBtn)
  AddText(group, L["Add Search"], L["Restore Defaults"])
  O.searchRows = {}
  local R = O.SEARCH_ROW
  local function Tip(w, title, line)
    w:HookScript("OnEnter", function(self)
      GameTooltip:SetOwner(self, "ANCHOR_RIGHT")
      GameTooltip:SetText(title, 1, 1, 1)
      GameTooltip:AddLine(line, nil, nil, nil, true)
      GameTooltip:Show()
    end)
    w:HookScript("OnLeave", GameTooltip_Hide)
  end
  local function Small(row, part, up, down, disabled, highlight)
    local b = CreateFrame("Button", nil, row)
    b:SetSize(R[part][2], R[part][2])
    b:SetPoint("LEFT", row, "LEFT", R[part][1], 0)
    b:SetNormalTexture(up)
    b:SetPushedTexture(down)
    if disabled then b:SetDisabledTexture(disabled) end
    b:SetHighlightTexture(highlight, "ADD")
    return b
  end
  for i = 1, Sx.MAX do
    local row = CreateFrame("Frame", nil, page)
    row:SetSize(R.w, 26)
    row.icon = row:CreateTexture(nil, "ARTWORK")
    row.icon:SetSize(R.icon[2], R.icon[2])
    row.icon:SetPoint("LEFT", R.icon[1], 0)
    row.label = row:CreateFontString(nil, "ARTWORK", "GameFontHighlightSmall")
    row.label:SetPoint("LEFT", R.label[1], 0)
    row.label:SetWidth(R.label[2])
    row.label:SetJustifyH("LEFT")
    row.label:SetWordWrap(false)
    row.where = O.PadDropdown(row, R.where[2], Sx.PlaceOptions, function()
      local r = Sx.Get(row.id)
      return r and Sx.Place(r) or nil
    end, function(v)
      if row.id then Sx.SetPlace(row.id, v) end
    end)
    row.where:SetPoint("LEFT", row, "LEFT", R.where[1], 0)
    Tip(row.where, L["Where it goes"], L["In Quick Find, or a button in the map menu: in the menu or always shown, going up or right."])
    row.edit = Small(row, "edit", "Interface\\Buttons\\UI-GuildButton-PublicNote-Up",
      "Interface\\Buttons\\UI-GuildButton-PublicNote-Up", "Interface\\Buttons\\UI-GuildButton-PublicNote-Disabled",
      "Interface\\Buttons\\ButtonHilight-Square")
    row.edit:SetScript("OnClick", function(self) Sx.Edit(self:GetParent().id) end)
    Tip(row.edit, L["Edit"], L["Change its name, what it searches for, its description, icon or place."])
    row.remove = Small(row, "remove", "Interface\\Buttons\\UI-GroupLoot-Pass-Up",
      "Interface\\Buttons\\UI-GroupLoot-Pass-Down", nil, "Interface\\Buttons\\UI-GroupLoot-Pass-Highlight")
    row.remove:SetScript("OnClick", function(self) Sx.Remove(self:GetParent().id) end)
    Tip(row.remove, L["Remove"], L["Remove it from the list. Restore Defaults brings Quick Find's own back."])
    row:EnableMouse(true)
    row:SetScript("OnEnter", function(self)
      local r = Sx.Get(self.id)
      if not r then return end
      GameTooltip:SetOwner(self, "ANCHOR_RIGHT")
      GameTooltip:SetText(Sx.Name(r), 1, 1, 1)
      GameTooltip:AddLine(Format(L["Searches for: %s"], Sx.Text(r)), 0.8, 0.8, 0.8, true)
      GameTooltip:AddLine(Sx.Desc(r), nil, nil, nil, true)
      GameTooltip:Show()
    end)
    row:SetScript("OnLeave", GameTooltip_Hide)
    place(row, 26)
    O.searchRows[i] = row
  end
  controls[#controls + 1] = function()
    local list = Sx.List()
    for i, row in ipairs(O.searchRows) do
      local r = list[i]
      row:SetShown(r ~= nil)
      if r then
        row.id = r.id
        local on = Sx.Shown(r) -- (another class's built-in: dimmed)
        ns.SetIcon(row.icon, Sx.Icon(r), Sx.DEFAULT_ICON)
        if row.icon.SetDesaturated then row.icon:SetDesaturated(not on) end
        row.icon:SetAlpha(on and 1 or 0.5)
        row.label:SetText(on and Sx.Name(r) or ("|cff808080" .. Sx.Name(r) .. "|r"))
        row.where:Update(true)
      end
    end
    addBtn:SetEnabled(#list < Sx.MAX)
  end

  ---------------------------------------------------------------- Performance
  -- Controller (Pad.lua; asked 2026-11-16, "add a new Controller section and make a keybinding list for each map
  -- control for the controller there"): controller support, the right stick, and each of the map's pad buttons
  Page(L["Controller"], nil, "Controller")
  Key("padControl")
  check(L["Controller support"], L["With a controller active, the map's own buttons are on it while the map is open: A sets a stop at the crosshair (or routes to the icon under it), X removes the stop there, B goes back, the triggers zoom, the D-pad pans and the left stick press recenters on you. Out of combat only: in a fight the controller is the game's again."],
    function() return GPS().padControl ~= false end, function(v) GPS().padControl = v if ns.Pad then ns.Pad.Apply() end end)
  -- (asked 2026-11-16: "Have a option to show gamepad controls on the map and show them with a light tinted background")
  Key("padLegend")
  check(L["Show the controller's buttons on the map"], L["Lists the map's controller buttons on a dark box at the map's left, under the directions and above the map menu's buttons. Hidden while the map menu is open; with no room for it, they're on a line at the map's bottom instead."],
    function() return GPS().padLegend ~= false end, function(v) GPS().padLegend = v if ns.Pad then ns.Pad.ShowMarks(ns.Pad.marksOn) end end,
    function() return GPS().padControl ~= false end, INDENT)
  header(L["Buttons"], L["Click a button on the drawing to choose what it does: pressed, held, or with LT, RT, LB or RB."])
  -- (the controller drawn, each button's controls on its line: O.LayoutPadDiagram; the rows to change them under it)
  if ns.Pad and ns.Pad.DIAGRAM then
    local diag = O.MakePadDiagram(page, PAGE_W - 44, math.floor(ns.Pad.DIAGRAM.h * 1.15), true)
    place(diag, diag:GetHeight() + 6, 0)
    O.padDiagram = diag
    controls[#controls + 1] = function() O.LayoutPadDiagram(diag) end
  end
  -- (the list of controls under the drawing taken out: asked 2026-11-16, "with new layout don't need this bottom
  -- section"; each button's window sets them)
  -- (Options itself with a controller, PadOptions.lua: its buttons fixed)
  -- (the map's part in yellow: asked 2026-11-16, "Make the part here ... Bold and yellow"; a line can't be part bold)
  note(L["In Options a controller moves with the D-pad, A selects, B goes back and LB and RB change the page. These buttons are fixed: the buttons assigned above are for the |cffffd100GPS map view only|r."])
  local padReset = Button(page, L["Reset to defaults"], 140, function()
    local r, why = ns.Pad.ResetBinds()
    O.padResetNote:SetText(r == true and "" or (why or ""))
  end)
  place(padReset, 30, 4)
  O.padReset = padReset
  O.padResetNote = page:CreateFontString(nil, "ARTWORK", "GameFontDisableSmall")
  O.padResetNote:SetPoint("LEFT", padReset, "RIGHT", 8, 0)

  Page(L["Performance"], nil, "Performance")
  header(L["Lighter settings"], L["For a slower PC: the same routes, worked out and drawn less often."])
  -- the addon's work over the last few seconds, while this page is open
  local usage = page:CreateFontString(nil, "ARTWORK", "GameFontHighlightSmall")
  place(usage, 20, 4)
  local ticker = CreateFrame("Frame", nil, page)
  local lastMs, lastT, wait = nil, nil, 0
  ticker:SetScript("OnShow", function() lastMs, lastT, wait = nil, nil, 0 usage:SetText(O.UsageText()) end)
  ticker:SetScript("OnUpdate", function(_, dt)
    wait = wait - dt
    if wait > 0 then return end
    wait = 2
    local ms, t = ns.PerfTotal(), GetTime()
    if lastMs and ms >= lastMs then usage:SetText(O.UsageText(ms - lastMs, t - lastT)) end
    lastMs, lastT = ms, t
  end)
  if ns.TimeScript then ns.TimeScript(ticker, "OnUpdate", "options window") end
  local lowBtn = Button(page, L["Use Low-End Settings"], 170, O.UseLowEnd)
  place(lowBtn, 30, 4)
  local defBtn = Button(page, L["Restore Defaults"], 140, O.PerfDefaults)
  defBtn:SetPoint("LEFT", lowBtn, "RIGHT", 6, 0)
  also(defBtn)
  AddText(group, L["Restore Defaults"])
  controls[#controls + 1] = function() lowBtn:SetEnabled(not O.IsLowEnd()) end
  header(L["Map"])
  Key("hz")
  slider(L["Map redraws per second"], 5, 30, 1, "%d", function() return GPS().hz or 20 end, function(v) GPS().hz = v end)
  note(L["The setting that saves the most: at 10 the map needs about half the work it does at 20, and still follows you smoothly. Standing still, it only redraws when something changes."])
  header(L["Routes"])
  Key("rerouteSeconds")
  slider(L["Work out a route you've left at most every"], 2, 10, 1, L["%d s"], function() return GPS().rerouteSeconds or 2 end,
    function(v) GPS().rerouteSeconds = v end)
  note(L["Off the route (fighting, gathering, or going your own way), it's worked out again from where you are. Less often is less work; the route catches up with you a little later."])
  Key("stopsAhead")
  slider(L["Stops routed and drawn ahead"], 1, 8, 1, "%d", function() return GPS().stopsAhead or 3 end, O.SetStopsAhead)
  note(L["How many of the route's stops are worked out and drawn at a time; the next come in as you reach them. Every stop is still in the fastest order and on the map, and the ones further on are listed with an estimated distance until they're routed."])
  -- (asked 2026-11-16: routing paused when you're not following it; its own option, the low-end settings turn it on)
  Key("autoPauseRouting")
  check(L["Pause routing when you're not following it"], L["When the time to your stop keeps growing (you're going somewhere else), the route is paused: nothing worked out or drawn, the stops kept, the arrow as on a flight. Resume Routing in the map menu, or /agps pause. The low-end settings turn this on."],
    function() return GPS().autoPauseRouting == true end, function(v) GPS().autoPauseRouting = v and true or false end)
  Key("autoPauseSeconds")
  -- (a short title: the long one ran into its value, a screenshot 2026-11-16)
  slider(L["Pause when longer by"], 30, 900, 30, function(v) return ns.Nav.FormatTime(v) end,
    function() return GPS().autoPauseSeconds or 120 end, function(v) GPS().autoPauseSeconds = v end)
  note(L["Paused once the time to your stop has grown by this much."])
  Key("gentleBackground")
  check(L["Gentle background work"], L["Walks around obstacles and the road data (after a /reload) are worked out in smaller slices of each frame: fewer stutters on a slow PC. The first route after a /reload, and walks off the roads, take a little longer to appear."],
    function() return GPS().gentleBackground end, function(v) GPS().gentleBackground = v end)
  header(L["Direction arrow"])
  Key("arrowHz")
  check(L["Turn the arrow every frame"], L["On: the arrow turns with every frame, as smoothly as the game runs. Off: 20 times a second, less work at high frame rates."],
    function() return (GPS().arrowHz or 0) == 0 end, function(v) GPS().arrowHz = v and 0 or 20 end)
  header(L["Other settings to improve performance"])
  note(L["Fewer icons on the map (Map > Show on the map, or the round button at the map's bottom-left): herbs, ore, quests and points of interest; quest areas' outlines off; and a smaller map."])

  ---------------------------------------------------------------- Profiles
  -- (asked 2026-11-11: profiles, each character on the one picked for it; Core.lua's ns.UseProfile)
  Page(L["Profiles"], nil, "Profiles")
  note(L["A profile is a set of all the options. Every character uses Default until you pick another for it; changes are saved to the profile in use."])
  do
    local all, others = {}, {}
    local function Fill()
      for i = #all, 1, -1 do all[i] = nil end
      for i = #others, 1, -1 do others[i] = nil end
      local cur = ns.ProfileName() or ""
      all[1] = { value = "", text = L["Default"] }
      for _, n in ipairs(ns.ProfileNames()) do all[#all + 1] = { value = n, text = n } end
      for _, o in ipairs(all) do
        if o.value ~= cur then others[#others + 1] = o end
      end
    end
    Fill()
    controls[#controls + 1] = Fill -- (before the lists' own refresh: a profile made or deleted since)
    local function Free() return not O.ProfilesHeld() end
    O.profileOptions = all
    O.profileList = Dropdown(L["This character's profile"], all, function() return ns.ProfileName() or "" end,
      function(v) ns.UseProfile(v ~= "" and v or nil) end, Free)
    O.profileCopy = Dropdown(L["Copy from"], others, function() return nil end,
      function(v) O.AskCopyProfile(v ~= "" and v or nil) end, function() return Free() and #others > 0 end)
    note(L["Type a name, then click New Profile: a copy of the options as they are now, used by this character."])
    local box = CreateFrame("EditBox", nil, page, "InputBoxTemplate")
    box:SetSize(200, 20)
    place(box, 26, 10)
    box:SetAutoFocus(false)
    local function Make()
      if O.NewProfile(box:GetText()) then
        box:SetText("")
        if box.ClearFocus then box:ClearFocus() end
      end
    end
    box:SetScript("OnEscapePressed", function(self) self:ClearFocus() end)
    box:SetScript("OnEnterPressed", Make)
    O.profileBox = box
    place(Button(page, L["New Profile"], 150, Make), 28, 4)
    local del = Button(page, L["Delete Profile"], 150, function() O.AskDeleteProfile() end)
    place(del, 28, 4)
    controls[#controls + 1] = function()
      if del.SetEnabled then del:SetEnabled(ns.ProfileName() ~= nil and Free()) end
    end
    O.profileDelete = del
  end

  ---------------------------------------------------------------- Tools
  Page(L["Tools"], nil, "Tools")
  note(L["For fixing the map's data: roads the routes miss or that aren't there, and walls they walk through. Click |cffffd100Map Editing|r on the map for the tools: the roads and walls show while it's open (or /agps roads on, /agps walls on)."])
  Key("devTools")
  check(L["Map editing tools"], L["Adds the Map Editing button to the map's buttons: the road and wall tools, the magic eraser, Undo, Stairs and Record. Also /agps dev."],
    function() return GPS().devTools end, function(v)
      GPS().devTools = v
      if not v and ns.GPS.SetMapEditOpen then ns.GPS.SetMapEditOpen(false) end
      if ns.GPS.LayoutQuick then ns.GPS.LayoutQuick() end
    end)
  Key("mapEditIdle")
  slider(L["Map Editing closes after"], 1, 30, 1, function(v) return Format(L["%d min"], v) end,
    function() return tonumber(GPS().mapEditIdle) or 2 end,
    function(v) GPS().mapEditIdle = math.floor(v + 0.5) end, nil,
    L["How long the opened Map Editing menu stays open with the map unused (no click, drag, zoom or stroke on it). Then it closes, the roads and walls are hidden again and the tools turn off."])
  header(L["Roads"], L["The road network the routes use."])
  note(L["With the road tools on, on the map: left-drag along a road the routes miss, right-drag over a \"road\" that isn't there (red), middle-drag to pan. Routes use it right away. A drawn road joins the roads it meets; where it runs along one, that road stays."])
  place(Button(page, L["Road Tools On/Off"], 150, function() ns.GPS.ToggleRoadMode() end), 28, 4)
  Key("recordHint")
  check(L["Suggest Record when drawing roads"], L["Starting to draw a road by hand asks whether to Record it instead: walked, a road keeps the floors and stairs it goes over."],
    function() return GPS().recordHint ~= false end, function(v) GPS().recordHint = v end)
  -- (1.2.0: /agps roads on|off's setting; the map's Show Roads and Walls button sets both)
  Key("showRoads")
  check(L["Show the roads on the map"], L["Draws the road network the routes use on the map, with the road tools off too. Also /agps roads."],
    function() return GPS().showRoads and true or false end, function(v) GPS().showRoads = v end)
  header(L["Walls"], L["What routes can't walk through: a town's wall, a fence, a cliff edge."])
  note(L["With the wall tools on, on the map: left-drag along a wall the routes try to walk through, right-drag over a wall that isn't there, or a mountain edge that's really walkable (circle an area to open all of it), middle-drag to pan. Routes go around your walls right away, like a mountain, and a road a wall crosses is cut there: leave a gap for a gate. Flight paths still cross them. Shown in blood red: the edges of mountains and cliffs too steep to climb (the terrain data), buildings, and the walls drawn in (thicker)."])
  place(Button(page, L["Wall Tools On/Off"], 150, function() ns.GPS.ToggleWallMode() end), 28, 4)
  -- (1.2.0: /agps walls on|off's setting)
  Key("showWalls")
  check(L["Show the walls on the map"], L["Draws the walls routes go around on the map (blood red), with the wall tools off too. Also /agps walls."],
    function() return GPS().showWalls and true or false end, function(v) GPS().showWalls = v end)
  header(L["Both tools"], L["The magic eraser, Restore Zone and Restore Continent put the map's own roads or walls back where you changed them (those of the tools on). Undo puts them back."])
  Key("toolShiftClick")
  check(L["Shift-click drawing"], L["On: the tools draw and erase only with Shift held (Shift + left-drag, Shift + right-drag), and a plain click or drag is the map's own: left-drag pans it, as with the tools off. (Shown with the road or wall tools)"],
    function() return GPS().toolShiftClick and true or false end, function(v)
      GPS().toolShiftClick = v
      if ns.GPS.RoadHint and (ns.GPS.roadMode or ns.GPS.wallMode) then ns.GPS.RoadHint() end
      if ns.GPS.RefreshQuick then ns.GPS.RefreshQuick() end
    end)
  header(L["Pins"], L["Your own marks on the map: a name and an icon."])
  note(L["Shift + left-click on the map, then |cffffd100Create Pin|r: name it, pick an icon (any the game has, as for a macro) and, where floors lie over each other (a dungeon, Undercity, a cave), its floor. Double-click a pin for a stop there; right-click it to remove it. Pins are shared with your map data (Copy Map Data..., Help improve)."])
  Key("pinning")
  check(L["Pinning"], L["Shift + left-click on the map asks to create a pin there. Off: Shift + left-drag only moves the map's window."],
    function() return GPS().pinning ~= false end, function(v) GPS().pinning = v end)
  header(L["Your changes"], L["Roads and walls you draw or erase, in the order drawn."])
  local undoBtn = Button(page, L["Take Back the Last"], 150, function() ns.Record.Undo() end)
  local listBtn = Button(page, L["List Your Changes"], 150, function() ns.Record.List() end)
  place(undoBtn, 28, 4)
  listBtn:SetPoint("LEFT", undoBtn, "RIGHT", 6, 0)
  also(listBtn)
  AddText(group, L["List Your Changes"])
  controls[#controls + 1] = function()
    local any = ns.db and ns.db.tracks and #ns.db.tracks > 0
    undoBtn:SetEnabled(any and true or false)
  end

  ---------------------------------------------------------------- Help
  -- (1.2.0: what's new, the tutorial's own sections (O.RegisterHelpSection), where to get help, and what the Help
  -- improve page had; "Help improve" still opens it, O.PAGE_ALIASES.) Top to bottom: the news, `help.host` (the
  -- "Tutorial" header and a frame per registered section; hidden, no height, with none), then `help.rest` (all the
  -- rest, one frame hung under the host so sections can come, go and change height: LayoutHelp).
  Page(L["Help"], nil, "Help")
  pinfo.whole = true
  header(L["What's new in 1.2.0"])
  for _, line in ipairs(O.WHATS_NEW) do note(line) end
  help.page, help.top = page, col.y
  page.agpsOwnHeight = true -- (LayoutHelp sets it, not FinishPage)
  help.host = CreateFrame("Frame", nil, page)
  help.host:SetPoint("TOPLEFT", 0, col.y)
  help.host:SetSize(PAGE_W - 26, 1)
  help.headH = Into(help.host, -10, function() header(L["Tutorial"]) end)
  help.rest = CreateFrame("Frame", nil, page)
  help.rest:SetSize(PAGE_W - 26, 10)
  -- An address to copy (the game can't open links): selected when clicked, not editable.
  local function CopyBox(value)
    local box = CreateFrame("EditBox", nil, page, "InputBoxTemplate")
    box:SetSize(PAGE_W - 60, 20)
    place(box, 26, 10)
    box:SetAutoFocus(false)
    box:SetText(value)
    box:SetCursorPosition(0)
    box:SetScript("OnEditFocusGained", function(self) self:HighlightText() end)
    box:SetScript("OnMouseUp", function(self) self:HighlightText() end)
    box:SetScript("OnTextChanged", function(self, user)
      if user then
        self:SetText(value)
        self:HighlightText()
      end
    end)
    box:SetScript("OnEscapePressed", function(self) self:ClearFocus() end)
    return box
  end
  help.restH = Into(help.rest, -10, function()
    -- (the map's Search Places help, moved here from its button's tooltip: asked 2026-11-14, "too much text for a
    -- button hover"; not on General, which fits without scrolling)
    header(L["Search Places"])
    note(L["Type 2+ letters, then pick a place to add it as a stop (Enter takes the first)."])
    note(L["Finds: towns and places, zones, landmarks, flight masters, boat and zeppelin docks, your faction's trainers and services in the capitals and starting towns, every NPC of your faction or neutral by name, title or what they do (\"class trainer\", \"profession trainer\", \"weapon trainer\", \"flight master\", \"vendor\", \"repair\", \"innkeeper\", \"banker\": the nearest first), and your pins."])
    note(L["Pin beside an NPC or a city place pins it for good. A zone's result is the middle of the zone."])
    header(L["Commands and links"])
    place(Button(page, L["Show Commands"], 150, function() SlashCmdList.AZEROTHGPS("help") end), 28, 4)
    note(L["Lists the /agps commands in the chat window."])
    note(L["The AzerothGPS website and Discord. Click an address to select it, then Ctrl+C to copy it:"])
    O.siteBox = CopyBox(O.SITE_URL)
    O.discordBox = CopyBox(O.DISCORD_URL)
    -- (asked 2026-11-13: a player's own log of what went wrong, to send; ns.Debug, this session's only: no /reload)
    header(L["Debugging"], L["For a problem to report: a log of what AzerothGPS does while you show it."])
    note(L["Send the log on the website's feedback page. Click the address to select it, then Ctrl+C to copy it:"])
    O.feedbackBox = CopyBox(O.FEEDBACK_URL)
    note(L["1. Tick |cffffd100Debug log|r.\n2. Do what goes wrong (no /reload: it would clear the log).\n3. Click |cffffd100Export Debug Log...|r, press |cffffd100Ctrl+C|r and paste it in the Discord or the website's report form, with what went wrong."])
    O.debugCheck = check(L["Debug log"], L["Notes what AzerothGPS does from now until you untick it or /reload. Kept in memory only, never saved; no character or realm names."],
      function() return ns.Debug.On() end, function(v) ns.Debug.SetOn(v) end)
    place(Button(page, L["Export Debug Log..."], 170, function() ns.Debug.ShowExport() end), 28, 4)
    header(L["Help improve AzerothGPS"], L["Kept on your PC only; sharing it is a separate step."])
    local counts = page:CreateFontString(nil, "ARTWORK", "GameFontDisableSmall")
    place(counts, 18, 4)
    local howBtn = Button(page, L["How to share..."], 150, ShowShareInfo)
    place(howBtn, 28, 4)
    local copyBtn = Button(page, L["Copy Map Data..."], 150, ShowRoadsText)
    copyBtn:SetPoint("LEFT", howBtn, "RIGHT", 6, 0)
    note(L["Type |cffffd100/reload|r before |cffffd100Copy Map Data...|r: it saves all your road and wall edits and pins, so every one of them is in the copy."])
    header(L["What Copy Map Data... includes"], L["Untick what you'd rather keep to yourself: it's left out of the copy."])
    for _, k in ipairs(ns.Feedback.KINDS) do
      Key(k.key)
      check(k.label, string.format(L["%s Unticked: left out of the copy."], k.tip),
        function() return GPS()[k.key] ~= false end, function(v) GPS()[k.key] = v end)
    end
    controls[#controls + 1] = function()
      local _, t = ns.Feedback.Counts()
      local r, w = ns.Feedback.DrawnCounts()
      local pn = ns.Pins and #ns.Pins.ShareLines() or 0
      counts:SetText(Format(L["Waiting to be shared: %s, %s, %s, %s"],
        string.format(r == 1 and L["%d road"] or L["%d roads"], r), string.format(w == 1 and L["%d wall"] or L["%d walls"], w),
        string.format(pn == 1 and L["%d pin"] or L["%d pins"], pn), string.format(t == 1 and L["%d trip"] or L["%d trips"], t)))
    end
    -- (issue #91, 2026-10-17: the OpenMap style's credit, its link to copy)
    header(L["Thanks"])
    note(O.CREDIT_TEXT)
    O.creditBox = CopyBox(O.OPENMAP_URL)
  end)
  LayoutHelp()

  FinishPage()

  -- Companion addons' pages (AzerothGPS.AddOptionsPage, asked 2026-10-05 for a companion): after the built-in ones,
  -- each addon's under a section header of its own named after it (O.SectionName: "AzerothGPS_Example" -> "Example"),
  -- its pages ("General", ...) under it. Built with the same helpers (`ui`), in pcall (a plugin's error stays in its
  -- page); the same owner and title again replaces that page. Their controls refresh with the built-in ones, in pcall.
  local builtIn = #pages
  O.sectionHeaders = {}
  local function SectionHeader(owner)
    local h = O.sectionHeaders[owner]
    if not h then
      h = listChild:CreateFontString(nil, "ARTWORK", "GameFontNormalSmall")
      h:SetTextColor(1, 0.82, 0)
      h.line = listChild:CreateTexture(nil, "ARTWORK")
      h.line:SetColorTexture(1, 0.82, 0, 0.25)
      h.line:SetHeight(1)
      h.line:SetPoint("TOPLEFT", h, "BOTTOMLEFT", 0, -2)
      h.line:SetWidth(LIST_W - 20)
      O.sectionHeaders[owner] = h
    end
    h:SetText(O.SectionName(owner))
    return h
  end
  local function PlaceTab(t, y)
    t:ClearAllPoints()
    t:SetPoint("TOPLEFT", 4, y)
    t.listY = y
  end
  -- The list's length; longer than the window: the scroll bar, inside the list (the tabs narrowed for it).
  local function FitList(y)
    local full = -y + 6
    O.listFull = full
    listChild:SetHeight(full)
    local over = full > (listScroll:GetHeight() or 0) + 1
    local barW = over and listScroll.ScrollBar and 24 or 0
    listScroll:SetPoint("BOTTOMRIGHT", -barW, 0)
    listChild:SetWidth(LIST_W - barW)
    for _, t in ipairs(tabs) do t:SetWidth(LIST_W - 8 - barW) end
    for _, h in pairs(O.sectionHeaders) do h.line:SetWidth(LIST_W - 20 - barW) end
    if listScroll.ScrollBar then listScroll.ScrollBar:SetShown(over) end
    if not over then listScroll:SetVerticalScroll(0) end
  end
  local listEnd = -6
  local function LayoutTabs()
    local y = -6
    for i = 1, builtIn do
      PlaceTab(tabs[i], y)
      y = y - 26
    end
    for _, h in pairs(O.sectionHeaders) do
      h:Hide()
      h.line:Hide()
    end
    local owners, seen = {}, {}
    for _, e in ipairs(O.plugins) do
      if e.tab and not seen[e.owner] then
        seen[e.owner] = true
        owners[#owners + 1] = e.owner
      end
    end
    for _, owner in ipairs(owners) do
      local h = SectionHeader(owner)
      y = y - 8
      h:ClearAllPoints()
      h:SetPoint("TOPLEFT", 10, y)
      h:Show()
      h.line:Show()
      y = y - 20
      for _, e in ipairs(O.plugins) do
        if e.owner == owner and e.tab then
          PlaceTab(e.tab, y)
          y = y - 26
        end
      end
    end
    listEnd = y
    FitList(y)
  end
  LayoutTabs()
  local function LiveText(getText)
    local fs = page:CreateFontString(nil, "ARTWORK", "GameFontHighlightSmall")
    fs:SetWidth(PAGE_W - 48)
    fs:SetJustifyH("LEFT")
    place(fs, 18, 4)
    controls[#controls + 1] = function() fs:SetText(tostring(getText() or "")) end
    return fs
  end
  -- The helpers a companion's page (API.AddOptionsPage) and a Help section (O.RegisterHelpSection) are built with,
  -- for the page or frame being laid out now.
  local function MakeUI()
    return {
      page = page,
      place = function(frame, h, indent) place(frame, h, indent) end,
      header = header, note = note, check = check,
      slider = function(...) return slider(...) end,
      button = function(label, width, onClick)
        local b = Button(page, label, width or 150, onClick)
        place(b, 28, 4)
        return b
      end,
      choice = Choice, dropdown = Dropdown, text = LiveText,
    }
  end
  -- A section of the Help page's tutorial host (O.RegisterHelpSection): a frame of its own under the "Tutorial"
  -- header, laid out from its top with `ui` (as a companion's page; ui.page is the section's frame), as tall as what
  -- it placed. In pcall: an error stays in the section. The same id again builds it again (a list that changed).
  function O.BuildHelpSection(entry)
    if entry.frame then -- (built before: replaced)
      entry.frame:Hide()
      for i = #controls, 1, -1 do
        if entry.controls[controls[i]] then table.remove(controls, i) end
      end
    end
    local sec = CreateFrame("Frame", nil, help.host)
    sec:SetSize(PAGE_W - 26, 1)
    entry.frame = sec
    local first = #controls + 1
    local p, c = page, col
    page, col = sec, { x = 16, y = 0 }
    local ok, err = pcall(entry.build, MakeUI())
    entry.height = math.max(1, -col.y)
    page, col = p, c
    if not ok and ns.Print then ns.Print("|cffff6060" .. string.format(L["%s options failed:"], tostring(entry.id)) .. "|r " .. tostring(err)) end
    sec:SetHeight(entry.height)
    entry.controls = {}
    for i = first, #controls do
      local fn = controls[i]
      local safe = function() pcall(fn) end
      controls[i] = safe
      entry.controls[safe] = true
    end
    for fn in pairs(entry.controls) do fn() end
    LayoutHelp()
  end
  -- (the tutorial host's frame and whether it shows, for whoever fills it)
  function O.HelpHost() return help.host, help.page end
  function O.BuildPluginPage(entry)
    if entry.tab then -- (built before: replaced)
      entry.tab:Hide()
      entry.scroll:Hide()
      for i = #controls, 1, -1 do
        if entry.controls[controls[i]] then table.remove(controls, i) end
      end
    end
    Page(entry.title, O.SectionName(entry.owner) .. ": " .. entry.title)
    pinfo.whole = true
    local n = #pages
    entry.tab, entry.scroll, entry.index = tabs[n], pages[n], n
    local first = #controls + 1
    local ok, err = pcall(entry.build, MakeUI())
    if not ok and ns.Print then ns.Print("|cffff6060" .. string.format(L["%s options failed:"], tostring(entry.title)) .. "|r " .. tostring(err)) end
    FinishPage()
    -- (its controls' refreshes, each in pcall: a plugin's get() failing doesn't stop the others)
    entry.controls = {}
    for i = first, #controls do
      local fn = controls[i]
      local safe = function() pcall(fn) end
      controls[i] = safe
      entry.controls[safe] = true
    end
    for fn in pairs(entry.controls) do fn() end
    LayoutTabs()
  end
  -- The page titled `title`: a plugin's (`owner`'s) when given, else AzerothGPS's own, else the first plugin's.
  function O.ShowPageNamed(title, owner)
    if owner == nil then
      title = O.PAGE_ALIASES[title] or title -- (a page since merged into another)
      for i = 1, builtIn do
        if tabs[i].id == title or tabs[i].text:GetText() == title then
          ShowPage(i)
          return true
        end
      end
    end
    for _, e in ipairs(O.plugins) do
      if e.index and e.title == title and (owner == nil or e.owner == owner) then
        ShowPage(e.index)
        return true
      end
    end
    return false
  end
  O.builtInPages = builtIn
  for _, entry in ipairs(O.plugins) do O.BuildPluginPage(entry) end
  help.built = true
  for _, entry in ipairs(O.helpSections) do O.BuildHelpSection(entry) end

  -- footer
  -- (asked first, 2026-11-11: "add a confirm ... popup for resetting all options to defaults")
  local reset = Button(f, L["Reset to defaults"], 160, function() O.AskReset() end)
  reset:SetPoint("BOTTOMRIGHT", -12, 12)
  O.footerReset = reset
  local version = f:CreateFontString(nil, "ARTWORK", "GameFontDisableSmall")
  version:SetPoint("BOTTOMLEFT", 14, 18)
  version:SetText("AzerothGPS " .. (ns.VERSION or ""))
  O.versionText = version -- (hidden while a controller's hint shows there, PadOptions.lua)

  -- The search: which rows show, where, and which pages have any (O.search above).
  -- (a term is found however it's written: "mini-map", "mini map" and "minimap" all find the minimap's settings, and
  -- "worldmap" the world map's; asked 2026-11-11, "users may not know exact term ... Do this for all terms". Spaces,
  -- hyphens and other punctuation count for nothing on either side: the text is read without them, and so is each
  -- word typed.)
  local squashed = setmetatable({}, { __mode = "k" })
  local function Squash(text)
    local sq = squashed[text]
    if not sq then
      sq = text:gsub("|c%x%x%x%x%x%x%x%x", ""):gsub("|r", ""):gsub("[%s%p]+", "")
      squashed[text] = sq
    end
    return sq
  end
  local function Matches(text, words)
    local sq = Squash(text)
    for _, w in ipairs(words) do
      if not sq:find(w, 1, true) then return false end
    end
    return true
  end
  local function SetShownFor(w, on) -- (only what the search hid is shown again: not something hidden for its own reason)
    if on then
      if w.agpsSearchHid then
        w.agpsSearchHid = nil
        w:Show()
      end
    elseif not w.agpsSearchHid and (not w.IsShown or w:IsShown()) then
      w.agpsSearchHid = true
      w:Hide()
    end
  end
  -- The results: one list of every page's matches, whichever page was showing (asked 2026-11-11: "it should consider
  -- all tabs ... shouldn't matter the tab when searching"). The matching rows themselves are moved into it, under
  -- their page's name and their section's header, and put back in their pages when the box is emptied.
  local results = CreateFrame("ScrollFrame", nil, area, "UIPanelScrollFrameTemplate")
  results:SetPoint("TOPLEFT", area, "TOPLEFT", 0, -2)
  results:SetPoint("BOTTOMRIGHT", area, "BOTTOMRIGHT", -26, 4)
  results:Hide()
  local resultsChild = CreateFrame("Frame", nil, results)
  resultsChild:SetSize(PAGE_W - 26, 10)
  results:SetScrollChild(resultsChild)
  search.results, search.resultsChild = results, resultsChild
  local function MoveTo(w, parent)
    if w.SetParent then w:SetParent(parent) end
  end
  local function ShowResults(y)
    for _, pg in ipairs(pages) do pg:Hide() end
    for _, t in ipairs(tabs) do
      t.selected:Hide()
      t.text:SetFontObject(t.small and "GameFontNormalSmall" or "GameFontNormal")
    end
    search.none:Hide()
    results:Show()
    if results.ScrollBar then
      results.ScrollBar:SetShown(resultsChild:GetHeight() > results:GetHeight() + 1)
    end
    if results.SetVerticalScroll then
      local range = math.max(0, (search.height or 0) - (results:GetHeight() or 0))
      results:SetVerticalScroll(math.max(0, math.min(range, y or 0)))
    end
  end
  -- (a page's name clicked in the list while searching: the results at that page's part; a page laid out by hand,
  -- itself)
  function search.Pick(n)
    local p = search.pages[n]
    if p and p.whole then
      if p.hit then ShowPage(n) end
    elseif search.any then
      ShowResults(p and p.resY and -p.resY - 8 or 0)
    end
  end
  function O.Search(text)
    local words = {}
    for w in tostring(text or ""):lower():gmatch("%S+") do
      local word = w:gsub("%p+", "") -- (the loop's own variable is never set: an error under a newer Lua)
      if word ~= "" then words[#words + 1] = word end
    end
    local on = #words > 0
    search.on = on or nil
    local y, any, firstWhole = -12, false, nil
    for n = 1, #pages do
      local p = search.pages[n]
      if p then
        local pageHit = on and Matches(p.text, words)
        local hit = not on or pageHit
        p.resY = nil
        if p.heading then p.heading:Hide() end
        if p.whole then
          if on and not pageHit then
            local all = { p.text }
            for _, g in ipairs(p.groups) do all[#all + 1] = g.text end
            hit = Matches(table.concat(all, " "), words)
          end
          if on and hit and not firstWhole then firstWhole = n end
        else
          for _, g in ipairs(p.groups) do
            g.show = not on or pageHit or Matches(g.text, words) or (g.section ~= nil and Matches(g.section.text, words))
            g.some = nil
          end
          hit = not on
          for _, g in ipairs(p.groups) do
            if g.show and #g.rows > 0 then
              hit = true
              if g.section then g.section.some = true end
            end
          end
          if on and hit then -- (the page's name over its matches)
            if not p.heading then
              p.heading = resultsChild:CreateFontString(nil, "ARTWORK", "GameFontHighlightLarge")
              p.heading:SetText(p.name)
            end
            if any then y = y - 14 end
            p.heading:SetPoint("TOPLEFT", 16, y)
            p.heading:Show()
            p.resY = y
            y = y - 30
            any = true
          end
          local top = y
          for _, row in ipairs(p.rows) do
            local g = row.group
            local vis = g.show or (row.header and g.some) or false
            SetShownFor(row.w, vis)
            for _, e in ipairs(row.extras or {}) do SetShownFor(e, vis) end
            local to = on and vis and resultsChild or p.child
            if row.at ~= to then
              row.at = to
              MoveTo(row.w, to)
              for _, e in ipairs(row.extras or {}) do MoveTo(e, to) end
            end
            if not (on and vis) then
              row.w:SetPoint("TOPLEFT", row.x, row.y)
              row.w.padResY = nil
            else
              if row.header and y < top then y = y - 10 end
              row.w:SetPoint("TOPLEFT", row.x, y)
              row.w.padResY = y -- (its place in the results, for a controller: PadOptions' PO.Area)
              y = y - row.h
              if row.header then y = y - 2 end
            end
          end
        end
        p.hit = hit
        if p.tab and p.tab.SetAlpha then p.tab:SetAlpha(hit and 1 or 0.35) end
      end
    end
    search.any = on and any or nil
    search.height = -y + 16
    resultsChild:SetHeight(math.max(10, search.height))
    if not on then
      results:Hide()
      ShowPage(currentPage)
    elseif any then
      ShowResults(0)
    elseif firstWhole then
      results:Hide()
      ShowPage(firstWhole)
    else -- (nothing matches: no page, and a line saying so)
      results:Hide()
      for _, pg in ipairs(pages) do pg:Hide() end
      search.none:Show()
    end
    return not on or any or firstWhole ~= nil
  end
  search.none = area:CreateFontString(nil, "ARTWORK", "GameFontDisable")
  search.none:SetPoint("TOP", 0, -40)
  search.none:SetText(L["No settings found."])
  search.none:Hide()
  do -- (the box: the game's search box where the client has it, its "Search" in it while it's empty)
    local okB, box = pcall(CreateFrame, "EditBox", "AzerothGPSOptionsSearch", f, "SearchBoxTemplate")
    if not (okB and box) then box = CreateFrame("EditBox", "AzerothGPSOptionsSearch", f, "InputBoxTemplate") end
    box:SetSize(200, 20)
    box:SetPoint("TOPRIGHT", f, "TOPRIGHT", -14, -32)
    if box.SetAutoFocus then box:SetAutoFocus(false) end
    local function Changed(self)
      local ok, err = pcall(O.Search, self:GetText())
      if not ok and ns.Print then ns.Print(tostring(err)) end
    end
    if box.HookScript and box.GetScript and box:GetScript("OnTextChanged") then
      box:HookScript("OnTextChanged", Changed) -- (the template's own keeps its "Search" and its clear button right)
    else
      box:SetScript("OnTextChanged", Changed)
    end
    box:SetScript("OnEscapePressed", function(self)
      self:SetText("")
      self:ClearFocus()
    end)
    box:SetScript("OnEnterPressed", function(self) self:ClearFocus() end)
    search.box = box
  end

  f:SetScript("OnShow", function()
    ns.LiftPopup(f) -- (over the map opened out of the minimap square; this script replaced RegisterPopup's hook)
    FitList(listEnd) -- (the list's height is known once the window is laid out)
    if search.on then -- (opened again: everything, the box empty)
      if search.box.SetText then search.box:SetText("") end
      O.Search("")
    end
    for _, refresh in ipairs(controls) do refresh() end
    ShowPage(currentPage)
  end)
  ShowPage(currentPage)
  f:Hide()
  return f
end

-- Companion addons' option pages (API.AddOptionsPage): { owner, title, build }, in the order added; a page is its
-- owner's and title's (an addon can have several: "General", "History"...).
O.plugins = {}
-- An addon's section name: its name less "AzerothGPS" ("AzerothGPS_Example", "AzerothGPS Example" -> "Example").
function O.SectionName(owner)
  local s = tostring(owner or "?")
  local short = s:gsub("^AzerothGPS[%s_%-%.:]*", "")
  return short ~= "" and short or s
end
function O.AddPage(owner, title, build)
  if type(build) ~= "function" then return false end
  title = tostring(title or "General")
  local entry
  for _, e in ipairs(O.plugins) do
    if e.owner == owner and e.title == title then entry = e end
  end
  if entry then
    entry.build = build
  else
    entry = { owner = owner, title = title, build = build }
    O.plugins[#O.plugins + 1] = entry
  end
  if window and O.BuildPluginPage then O.BuildPluginPage(entry) end -- (the window built already: added now)
  return true
end
-- A section on the Help page, under its "Tutorial" header (1.2.0: the in-game tutorial's replay list): `id` a name of
-- your own ("tutorial"), build(ui) as a companion page's (ui.header, note, check, slider, button, choice, dropdown,
-- text, place; ui.page the section's own frame, laid out from its top). Built with the window, or at once when it's
-- built already; the same id again builds that section again. Sections show in the order first registered; the
-- "Tutorial" header shows while there's at least one.
O.helpSections = {}
function O.RegisterHelpSection(id, build)
  if type(build) ~= "function" then return false end
  id = tostring(id or "tutorial")
  local entry
  for _, e in ipairs(O.helpSections) do
    if e.id == id then entry = e end
  end
  if entry then
    entry.build = build
  else
    entry = { id = id, build = build }
    O.helpSections[#O.helpSections + 1] = entry
  end
  if window and O.BuildHelpSection then O.BuildHelpSection(entry) end -- (the window built already: added now)
  return true
end
-- Open the options at the page titled `title`: `owner`'s when given, else AzerothGPS's own, else a plugin's. False
-- when there's none.
function O.ShowPage(title, owner)
  window = window or BuildWindow()
  window:Show()
  return title == nil or O.ShowPageNamed(title, owner)
end

-- Every option back to its default (the window's Reset to defaults, once its question is answered Yes).
function O.ResetToDefaults()
  ns.settings.gps = CopyTable(ns.DEFAULTS.gps)
  Apply()
end
-- Profiles (Options > Profiles; Core.lua's ns.UseProfile). Not while the tutorial runs: it holds the options it found
-- to put them back after.
function O.ProfilesHeld()
  return ns.Tutorial ~= nil and ns.Tutorial.run ~= nil
end
-- A new profile from the options as they are, this character on it. False (and why, in chat) when the name is taken.
function O.NewProfile(name)
  name = (tostring(name or ""):gsub("^%s+", ""):gsub("%s+$", ""))
  if name == "" or O.ProfilesHeld() then return false end
  if name == "Default" or name == L["Default"] or (type(ns.db.profiles) == "table" and ns.db.profiles[name] ~= nil) then
    ns.Print(L["There's already a profile with that name."])
    return false
  end
  if not ns.NewProfile(name) then return false end
  Apply()
  return true
end
local function AskProfile(text, onYes)
  if not ns.Ask then onYes() return nil end
  O.profileAsk = ns.Ask("AzerothGPSProfileConfirm", text, nil, nil, onYes, nil, { strata = "FULLSCREEN_DIALOG" })
  return O.profileAsk
end
-- "Copy every option from <name> into this profile?" (`from` nil: Default)
function O.AskCopyProfile(from)
  if O.ProfilesHeld() then return nil end
  return AskProfile(Format(L["Copy every option from |cffffd100%s|r into this profile?"], from or L["Default"]), function()
    if ns.CopyProfile(from) then Apply() end
  end)
end
-- "Delete the profile <name>?": the one in use (never Default)
function O.AskDeleteProfile()
  local name = ns.ProfileName()
  if not name or O.ProfilesHeld() then return nil end
  return AskProfile(Format(L["Delete the profile |cffffd100%s|r? Characters using it go back to Default."], name), function()
    if ns.DeleteProfile(name) then Apply() end
  end)
end

-- "Reset all options to their defaults?" first: a click on the button alone changes nothing.
function O.AskReset()
  if not ns.Ask then return O.ResetToDefaults() end
  O.resetAsk = ns.Ask("AzerothGPSResetConfirm", L["Reset all options to their defaults?"], nil, nil,
    O.ResetToDefaults, nil, { strata = "FULLSCREEN_DIALOG" })
  return O.resetAsk
end

function O.CurrentPage() return currentPage end -- (the page showing, by its place in the list)
function O.Toggle()
  window = window or BuildWindow()
  window:SetShown(not window:IsShown())
end

function O.Show()
  window = window or BuildWindow()
  window:Show()
end

---------------------------------------------------------------------------
-- Minimap button
---------------------------------------------------------------------------

-- Round the minimap's edge at its angle, or a square minimap's (GPS.MinimapSquare). Only while it's the minimap's own:
-- a button drawer that took it (EllesmereUI's, a bug report 2026-10-30: it came back out over the map at every
-- options change, and was dragged round in front of it) places it itself.
function O.ButtonOwned()
  return O.button and O.button:GetParent() == Minimap
end
local function PlaceButton()
  if not O.ButtonOwned() then return end
  local a = math.rad(ns.settings.minimap.angle)
  local r = (Minimap:GetWidth() / 2) + 5
  local x, y = math.cos(a), math.sin(a)
  if ns.GPS and ns.GPS.MinimapSquare and ns.GPS.MinimapSquare() then -- (on the square's edge)
    local q = math.max(math.abs(x), math.abs(y))
    x, y = x / q, y / q
  end
  O.button:ClearAllPoints()
  O.button:SetPoint("CENTER", Minimap, "CENTER", x * r, y * r)
end

function O.UpdateButton()
  -- (shown or hidden only when the setting changes: a drawer shows and hides it as it opens and closes)
  local hide = ns.settings.minimap.hide and true or false
  if O.buttonHide ~= hide then
    O.buttonHide = hide
    O.button:SetShown(not hide)
  end
  PlaceButton()
end

local function BuildButton()
  local b = CreateFrame("Button", "AzerothGPSMinimapButton", Minimap)
  b:SetSize(31, 31)
  b:SetFrameStrata("MEDIUM")
  b:SetFrameLevel(8)
  b:RegisterForClicks("LeftButtonUp", "RightButtonUp")
  b:RegisterForDrag("LeftButton")
  b:SetHighlightTexture("Interface\\Minimap\\UI-Minimap-ZoomButton-Highlight")

  local bg = b:CreateTexture(nil, "BACKGROUND")
  bg:SetTexture("Interface\\Minimap\\UI-Minimap-Background")
  bg:SetSize(20, 20)
  bg:SetPoint("CENTER")
  local icon = b:CreateTexture(nil, "ARTWORK")
  icon:SetTexture("Interface\\AddOns\\AzerothGPS\\Media\\Device") -- the device from the logo
  icon:SetSize(20, 20)
  icon:SetPoint("CENTER")
  local border = b:CreateTexture(nil, "OVERLAY")
  border:SetTexture("Interface\\Minimap\\MiniMap-TrackingBorder")
  border:SetSize(52, 52)
  border:SetPoint("TOPLEFT")

  b:SetScript("OnClick", function(_, mouse)
    if mouse == "RightButton" then
      O.Toggle()
    else
      -- (the map as the minimap: the click opens the map out and sends it back, as the square's logo does; asked
      -- 2026-11-11, "add back the left click to open map function to the minimap AzerothGPS icon in addition to the
      -- logo". It hid the square before.)
      local G = ns.GPS
      if GPS().shown and G and G.mmState and G.mmState.on and G.SetMinimapExpanded then
        if G.WorldMapWanted and G.WorldMapWanted() then G.ToggleMapView()
        else G.SetMinimapExpanded(not G.mmState.expanded) end
        return
      end
      GPS().shown = not GPS().shown
      Apply()
    end
  end)
  b:SetScript("OnDragStart", function(self)
    if not O.ButtonOwned() then return end
    self:SetScript("OnUpdate", function()
      local mx, my = Minimap:GetCenter()
      local cx, cy = GetCursorPosition()
      local scale = Minimap:GetEffectiveScale()
      ns.settings.minimap.angle = math.deg(math.atan2(cy / scale - my, cx / scale - mx))
      PlaceButton()
    end)
  end)
  b:SetScript("OnDragStop", function(self) self:SetScript("OnUpdate", nil) end)
  b:SetScript("OnEnter", function(self)
    GameTooltip:SetOwner(self, "ANCHOR_LEFT")
    GameTooltip:SetText("AzerothGPS", 1, 1, 1)
    local G = ns.GPS
    if GPS().shown and G and G.mmState and G.mmState.on then
      GameTooltip:AddLine(G.WorldMapWanted and G.WorldMapWanted()
        and L["Left-click: the game's world map, with the GPS map in it."]
        or L["Left-click: the whole map window, to set a route."], nil, nil, nil, true)
    else
      GameTooltip:AddLine(L["Left-click: show/hide the GPS"], nil, nil, nil)
    end
    GameTooltip:AddLine(L["Right-click: options"], nil, nil, nil)
    if O.ButtonOwned() then GameTooltip:AddLine(L["Drag: move this button"], nil, nil, nil) end
    GameTooltip:Show()
  end)
  b:SetScript("OnLeave", GameTooltip_Hide)
  return b
end

---------------------------------------------------------------------------
-- Game options (Esc > Options > AddOns)
---------------------------------------------------------------------------

local function RegisterGameOptions()
  if not (Settings and Settings.RegisterCanvasLayoutCategory and Settings.RegisterAddOnCategory) then return end
  local panel = CreateFrame("Frame")
  panel.name = "AzerothGPS"
  local t = panel:CreateFontString(nil, "ARTWORK", "GameFontNormalLarge")
  t:SetPoint("TOPLEFT", 16, -16)
  t:SetText("AzerothGPS")
  local d = panel:CreateFontString(nil, "ARTWORK", "GameFontHighlight")
  d:SetPoint("TOPLEFT", t, "BOTTOMLEFT", 0, -8)
  d:SetText(L["Car-GPS style map and navigation. Settings are in the AzerothGPS window."])
  local open = CreateFrame("Button", nil, panel, "UIPanelButtonTemplate")
  open:SetSize(200, 24)
  open:SetPoint("TOPLEFT", d, "BOTTOMLEFT", 0, -12)
  open:SetText(L["Open AzerothGPS options"])
  open:SetWidth(math.max(200, (open:GetTextWidth() or 0) + 24))
  open:SetScript("OnClick", function()
    -- (not with the game's controller UI on: a game panel hidden by an addon is forbidden there, GPS.PanelsHeld)
    local held = ns.GPS and ns.GPS.PanelsHeld and ns.GPS.PanelsHeld(true)
    if not held and SettingsPanel and SettingsPanel:IsShown() then HideUIPanel(SettingsPanel) end
    O.Show()
  end)
  local category = Settings.RegisterCanvasLayoutCategory(panel, "AzerothGPS")
  Settings.RegisterAddOnCategory(category)
end

function O.Init()
  O.button = BuildButton()
  O.UpdateButton()
  pcall(RegisterGameOptions)
end
