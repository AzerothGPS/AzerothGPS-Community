-- "What's new in v1.4.0" (item 34, Kooki3z 2026-11-24): a picture of a spell jump on the GPS map, a line on what changed,
-- and 1.4.0's new options live (the same settings as Options, applied at once), Reset Defaults (lit only while one of
-- them differs from its default; resets only these) and Close.
--
-- WHO SEES IT: a player updating gets this popup once, some seconds after the world is entered (the saved stamp
-- `db.whatsNewSeen` under W.VERSION; set as it opens, so a /reload meanwhile doesn't bring it back), and nothing else:
-- never the setup, never a tutorial offer (Kooki3z, 2026-11-25: "updates are What's New only"). A first install gets
-- the first-run setup (Setup.lua) instead, this as its last page (Kooki3z: "new installs get the welcome only, and the
-- What's New content becomes the welcome's last page"); the setup opening sets the stamp too: nobody sees it twice.
-- Any time again: Options > Help's What's New, or /agps whatsnew.
local _, ns = ...
local L = ns.L or setmetatable({}, { __index = function(_, k) return k end })

local W = {}
ns.WhatsNew = W

W.VERSION = "1.4.0"
W.DELAY = 6 -- seconds after the world is entered (as the setup's)
W.W, W.H = 580, 300 -- (the least; grown to the content, W.Window: wide enough for the picture at its own pixels)
W.IMAGE = "Interface\\AddOns\\AzerothGPS\\Media\\WhatsNew\\spellJump"
W.IMAGE_PX = { 512, 299 } -- (the picture's pixels, the top left of its W.IMAGE_CANVAS)
W.IMAGE_CANVAS = { 512, 512 } -- (item 94: Kooki3z's own shot, its tooltip readable at 1:1)
-- The new options shown, in order: { key, kind, label, tooltip }.
W.KEYS = { "useClassSpells", "expertJumper", "safeDropYd" } -- (the grids' Cities and World: gone, item 74)

local function GPS() return ns.settings.gps end
local function DB() return ns.db end
local function InCombat() return (ns.inCombat or (InCombatLockdown and InCombatLockdown())) and true or false end
local function Default(key)
  local d = ns.DEFAULTS and ns.DEFAULTS.gps
  return d and d[key]
end
-- A setting's value as the options read it (safeDropYd: Nav's clamp of it).
function W.Value(key)
  local st = GPS()
  if key == "safeDropYd" then return ns.Nav and ns.Nav.SafeDropSetting and ns.Nav.SafeDropSetting() or st.safeDropYd end
  if key == "useClassSpells" then return st.useClassSpells ~= false end
  return st[key] == true
end
-- A setting's side effects as Options' own (the grids on or off, the fall spells looked at again, rerouted), for the
-- value it has now; false for a key not of these.
function W.Applied(key)
  local st = GPS()
  if key == "useClassSpells" or key == "expertJumper" then
    if ns.FallSpells and ns.FallSpells.Refresh then ns.FallSpells.Refresh() end
    if ns.Nav and ns.Nav.OptionsChanged then ns.Nav.OptionsChanged() end
  elseif key == "safeDropYd" then
    if ns.Nav and ns.Nav.OptionsChanged then ns.Nav.OptionsChanged() end
  else
    return false
  end
  return true
end
-- Set as Options sets it, applied at once.
function W.Set(key, v)
  local st = GPS()
  if key == "safeDropYd" then
    st.safeDropYd = tonumber(v) or Default("safeDropYd")
  elseif key == "useClassSpells" or key == "expertJumper" then
    st[key] = v and true or false
  else
    return false
  end
  W.Applied(key)
  W.Refresh()
  if ns.Options and ns.Options.Refresh then pcall(ns.Options.Refresh) end
  return true
end
-- Whether one of these differs from its default (Reset Defaults lit then).
function W.Changed()
  for _, key in ipairs(W.KEYS) do
    local d = Default(key)
    if key == "safeDropYd" then
      if tonumber(W.Value(key)) ~= tonumber(d) then return true end
    elseif W.Value(key) ~= (d == true) then
      return true
    end
  end
  return false
end
-- These back to their defaults (only these).
function W.Reset()
  for _, key in ipairs(W.KEYS) do
    local d = Default(key)
    if key == "safeDropYd" then
      if tonumber(W.Value(key)) ~= tonumber(d) then W.Set(key, d) end
    elseif W.Value(key) ~= (d == true) then
      W.Set(key, d == true)
    end
  end
  W.Refresh()
end

---------------------------------------------------------------------------
-- The content: the line, the picture, the options and Reset Defaults; in the popup and on the setup's last page
---------------------------------------------------------------------------
W.contents = {}
local function Check(parent, key, label, tip, enabled)
  local cb = CreateFrame("CheckButton", nil, parent, "UICheckButtonTemplate")
  cb:SetSize(24, 24)
  cb.key = key
  cb.label = cb:CreateFontString(nil, "ARTWORK", "GameFontHighlight")
  cb.label:SetPoint("LEFT", cb, "RIGHT", 2, 0)
  cb.label:SetText(label)
  cb:SetScript("OnClick", function(self) W.Set(key, self:GetChecked() and true or false) end)
  cb:SetScript("OnEnter", function(self)
    GameTooltip:SetOwner(self, "ANCHOR_RIGHT")
    GameTooltip:SetText(label, 1, 1, 1)
    GameTooltip:AddLine(tip, nil, nil, nil, true)
    GameTooltip:Show()
  end)
  cb:SetScript("OnLeave", GameTooltip_Hide)
  if cb.SetMotionScriptsWhileDisabled then cb:SetMotionScriptsWhileDisabled(true) end
  cb.Sync = function()
    cb:SetChecked(W.Value(key))
    local on = not enabled or enabled()
    cb.agpsOn = on and true or false
    cb:SetEnabled(on and true or false)
    cb.label:SetFontObject(on and "GameFontHighlight" or "GameFontDisable")
  end
  return cb
end
local function DropSlider(parent)
  local N = ns.Nav
  local holder = CreateFrame("Frame", nil, parent)
  holder:SetSize(240, 40)
  holder.key = "safeDropYd"
  local title = holder:CreateFontString(nil, "ARTWORK", "GameFontNormalSmall")
  title:SetPoint("TOPLEFT")
  title:SetText(L["Safe drop"])
  local value = holder:CreateFontString(nil, "ARTWORK", "GameFontHighlightSmall")
  value:SetPoint("TOPRIGHT")
  holder.valueText = value
  local s = CreateFrame("Slider", nil, holder, "BackdropTemplate")
  s:SetOrientation("HORIZONTAL")
  s:SetHeight(17)
  s:SetPoint("TOPLEFT", 0, -16)
  s:SetPoint("TOPRIGHT", 0, -16)
  s:SetBackdrop({
    bgFile = "Interface\\Buttons\\UI-SliderBar-Background",
    edgeFile = "Interface\\Buttons\\UI-SliderBar-Border",
    tile = true, tileSize = 8, edgeSize = 8,
    insets = { left = 3, right = 3, top = 6, bottom = 6 },
  })
  s:SetThumbTexture("Interface\\Buttons\\UI-SliderBar-Button-Horizontal")
  s:SetMinMaxValues(N.SAFE_DROP_MIN, N.SAFE_DROP_MAX)
  s:SetValueStep(1)
  s:SetObeyStepOnDrag(true)
  holder.slider = s
  local updating = false
  local function Text(v) return tostring(N.FormatDistance and N.FormatDistance(v) or v) end
  s:SetScript("OnValueChanged", function(_, v)
    value:SetText(Text(v))
    if updating then return end
    W.Set("safeDropYd", math.floor(v + 0.5))
  end)
  s:EnableMouseWheel(true)
  s:SetScript("OnMouseWheel", function(self, d) self:SetValue(self:GetValue() + d) end)
  s:SetScript("OnEnter", function(self)
    GameTooltip:SetOwner(self, "ANCHOR_RIGHT")
    GameTooltip:SetText(L["Safe drop"], 1, 1, 1)
    GameTooltip:AddLine(L["How far routes may drop without a fall spell. Above about 39 yd a fall can kill a low-level character."], nil, nil, nil, true)
    GameTooltip:Show()
  end)
  s:SetScript("OnLeave", GameTooltip_Hide)
  holder.Sync = function()
    updating = true
    s:SetValue(W.Value("safeDropYd"))
    value:SetText(Text(W.Value("safeDropYd")))
    updating = false
  end
  return holder
end
-- The content in `parent`, from (x, y) (TOPLEFT offsets) `w` wide: { frame, controls, reset }. Item 37 (Kooki3z's
-- screenshot on 3c85cf49): the line, the picture centered under it in a gold edge and a soft glow (color textures,
-- no game art), the settings one centered block under it (the heading, then the options); c.height the content's
-- height for its window (W.Window, the setup's last page), Reset Defaults under it on the setup's page.
W.IMAGE_W = 512 -- (its own pixels where the content is wide enough: the tooltip's text stays sharp)
W.BLOCK_W = 300 -- (the settings' block, centered)
-- ({ pad, r, g, b, a }: the gold edge, then the glow. Its red was missing, { 1, 0.82, 0.25, 0.95 } read as magenta:
-- item 64, Kooki3z, "the picture's border is pink")
W.GLOW = { { 1, 1, 0.82, 0.25, 0.95 }, { 3, 0.95, 0.7, 0.2, 0.28 }, { 6, 0.95, 0.7, 0.2, 0.14 }, { 10, 0.95, 0.7, 0.2, 0.06 } }
local function Rect(f, layer, sub, r, g, b, a)
  local t = f:CreateTexture(nil, layer, nil, sub)
  t:SetColorTexture(r, g, b, a)
  return t
end
function W.Build(parent, x, y, w)
  local c = CreateFrame("Frame", nil, parent)
  c:SetPoint("TOPLEFT", parent, "TOPLEFT", x, y)
  c:SetWidth(w)
  c.line = c:CreateFontString(nil, "ARTWORK", "GameFontHighlight")
  c.line:SetPoint("TOPLEFT")
  c.line:SetPoint("TOPRIGHT")
  c.line:SetJustifyH("LEFT")
  c.line:SetWidth(w) -- (wrapped at the content's width, measured so: item 64, "...and can j..." cut off)
  if c.line.SetWordWrap then c.line:SetWordWrap(true) end
  c.line:SetText(L["Routes now walk the map's own ground in the open world and the capitals, and can jump down cliffs with a fall spell (the coiled line). Your settings for jumping:"])
  local iw = math.min(W.IMAGE_W, w - 24)
  local ih = math.floor(iw * W.IMAGE_PX[2] / W.IMAGE_PX[1] + 0.5)
  local lineH = (c.line.GetStringHeight and c.line:GetStringHeight()) or 0
  -- (at least the lines its length needs at about 6 pixels a letter: the client may not have laid it out yet)
  local text = c.line.GetText and c.line:GetText() or ""
  local need = math.ceil((#text * 6) / math.max(100, w)) * 14
  if lineH < need then lineH = need end
  if lineH < 28 then lineH = 28 end
  local glow = W.GLOW[#W.GLOW][1]
  local top = lineH + 10 + glow
  c.image = c:CreateTexture(nil, "ARTWORK")
  c.image:SetSize(iw, ih)
  c.image:SetPoint("TOP", c, "TOP", 0, -top)
  c.imageAt = { x = 0, y = -top, w = iw, h = ih } -- (the layout's numbers, for the tests)
  -- (the picture's own pixels of the canvas: exact, never filtered above LINEAR, the crash memory)
  c.image:SetTexture(W.IMAGE, nil, nil, "LINEAR")
  c.image:SetTexCoord(0, W.IMAGE_PX[1] / W.IMAGE_CANVAS[1], 0, W.IMAGE_PX[2] / W.IMAGE_CANVAS[2])
  -- (the gold edge, then the glow fading out round it: plain colored rectangles behind the picture, widest first)
  c.glow = {}
  for k = #W.GLOW, 1, -1 do
    local gl = W.GLOW[k]
    local pad = gl[1]
    local t = Rect(c, "BACKGROUND", k == 1 and 2 or 1, gl[2], gl[3], gl[4], gl[5])
    t:SetPoint("TOPLEFT", c.image, "TOPLEFT", -pad, pad)
    t:SetPoint("BOTTOMRIGHT", c.image, "BOTTOMRIGHT", pad, -pad)
    c.glow[#c.glow + 1] = t
  end
  -- (the settings: one block, centered under the picture)
  local blk = CreateFrame("Frame", nil, c)
  blk:SetWidth(W.BLOCK_W)
  blk:SetPoint("TOP", c.image, "BOTTOM", 0, -(glow + 14))
  c.blockAt = { x = 0, y = -(top + ih + glow + 14) }
  c.block = blk
  c.heading = blk:CreateFontString(nil, "ARTWORK", "GameFontNormal")
  c.heading:SetPoint("TOPLEFT")
  c.heading:SetText(L["Jumping"])
  local spells = function() return GPS().useClassSpells ~= false end
  c.controls = {
    Check(blk, "useClassSpells", L["Use class spells"], L["Spell jumping: with a spell or item that slows your fall ready (a mage's or priest's with its reagent in your bags, your race's own, a parachute cloak), routes may jump down drops too high to survive without it, as many as your cooldowns and reagents allow on the trip. The step before says to cast it, and a button beside the directions casts it when you click it."]),
    Check(blk, "expertJumper", L["Expert jumper"], L["Spell jumping off any ledge, however high: jump, fall, and cast your fall spell just before you land (the directions say when, and the button shows then). Casting it too early can run out before you land."] .. " " .. L["Can make routes take much longer to work out on long trips."], spells),
    DropSlider(blk),
  }
  local yy = -20
  for _, ctl in ipairs(c.controls) do
    ctl:ClearAllPoints()
    local indent = ctl.key == "expertJumper" and 20 or 0
    if ctl.key == "safeDropYd" then yy = yy - 6 end
    ctl:SetPoint("TOPLEFT", blk, "TOPLEFT", indent, yy)
    yy = yy - (ctl.key == "safeDropYd" and 40 or 26)
  end
  blk:SetHeight(-yy)
  local ok, b = pcall(CreateFrame, "Button", nil, c, "UIPanelButtonTemplate")
  if not ok or not b then b = CreateFrame("Button", nil, c) end
  b:SetHeight(22)
  b:SetText(L["Reset Defaults"])
  b:SetWidth(math.max(120, (b.GetTextWidth and b:GetTextWidth() or 0) + 24))
  b:SetScript("OnClick", function() W.Reset() end)
  b:SetPoint("TOPRIGHT", blk, "BOTTOMRIGHT", 0, -8) -- (the setup's page: under the settings; the popup's by Close)
  c.reset = b
  -- (the content's height: the line, the picture in its glow, the block; and Reset Defaults under it on the setup's)
  c.height = top + ih + glow + 14 + (-yy)
  c:SetHeight(c.height + 30)
  W.contents[#W.contents + 1] = c
  W.SyncContent(c)
  return c
end
function W.SyncContent(c)
  for _, ctl in ipairs(c.controls) do ctl.Sync() end
  local on = W.Changed()
  c.reset:SetEnabled(on)
  c.reset.agpsLit = on
end
-- Every content shown, its controls as the settings are (a change here or in Options).
function W.Refresh()
  for _, c in ipairs(W.contents) do W.SyncContent(c) end
end

---------------------------------------------------------------------------
-- The popup
---------------------------------------------------------------------------
function W.Window()
  if W.window then return W.window end
  local f = ns.Window("AzerothGPSWhatsNew", W.W, W.H, string.format(L["What's new in v%s"], W.VERSION), "DIALOG")
  f.content = W.Build(f, 18, f.top - 8, W.W - 36)
  -- (tall enough for the content and the buttons under it, in every language: item 37)
  f:SetHeight(math.max(W.H, -f.top + 8 + f.content.height + 16 + 22 + 14))
  local ok, b = pcall(CreateFrame, "Button", nil, f, "UIPanelButtonTemplate")
  if not ok or not b then b = CreateFrame("Button", nil, f) end
  b:SetHeight(22)
  b:SetText(L["Close"])
  b:SetWidth(math.max(90, (b.GetTextWidth and b:GetTextWidth() or 0) + 24))
  b:SetScript("OnClick", function() f:Hide() end)
  b:SetPoint("BOTTOMRIGHT", -16, 14)
  f.close = b
  local r = f.content.reset
  r:ClearAllPoints()
  r:SetPoint("RIGHT", b, "LEFT", -6, 0)
  f:SetScript("OnHide", function() W.open = nil end)
  W.window = f
  return f
end
-- Shown (by hand, or once to a player updating); the stamp set as it opens.
function W.Open()
  if InCombat() then
    ns.Print(L["What's New can't open in combat. Try again after the fight."])
    return false
  end
  local db = DB()
  if db then db.whatsNewSeen = W.VERSION end
  local f = W.Window()
  W.open = true
  W.Refresh()
  f:ClearAllPoints()
  f:SetPoint("CENTER", 0, 60)
  f:Show()
  f:Raise()
  return true
end
function W.Shown() return (W.window and W.window:IsShown()) and true or false end
-- Due: a player updating who hasn't seen it (a first install's setup shows it as its last page instead).
function W.Due()
  local db = DB()
  if not db or db.whatsNewSeen == W.VERSION then return false end
  if ns.Setup and ns.Setup.Due and ns.Setup.Due() then return false end
  return true
end
function W.MaybeShow()
  if not W.Due() or W.Shown() then return false end
  if InCombat() or (ns.Tutorial and ns.Tutorial.run) or (ns.Setup and ns.Setup.open) then
    W.waiting = true
    return false
  end
  W.waiting = nil
  return W.Open()
end
function W.OnEnteringWorld()
  if W.asked or not W.Due() or not (C_Timer and C_Timer.After) then return end
  W.asked = true
  C_Timer.After(W.DELAY, function() pcall(W.MaybeShow) end)
end
function W.Init()
  if W.inited then return end
  W.inited = true
  local ev = CreateFrame("Frame")
  ev:RegisterEvent("PLAYER_REGEN_ENABLED")
  ev:SetScript("OnEvent", function()
    if W.waiting then pcall(W.MaybeShow) end
  end)
  W.events = ev
end
