-- The first-run setup and the first route's tips (1.3.10, Kooki3z: "A one-time popup that lets users choose cards for
-- major options ... One popup for setup on initial install. Then tutorials would not be a popup, just a dialog panel
-- message where route directions go, until the player does their first route").
--
-- THE SETUP: one window (ns.Window, its corner logo), a page a choice, each a row of big cards (a picture, a title, a
-- line); the card picked is lit. Shown once to a first install only (Kooki3z, 2026-11-25: "From here on new install
-- is setup page only and updates are What's New only"), some seconds after the world is entered: due while
-- `db.setup.fresh` (set by InitDB when there was no saved data at all) and the saved stamp `db.setup.shown` is under
-- S.VERSION. The stamp is set as it opens, so a /reload meanwhile doesn't bring it back. Any time again: Options > Help's Run Setup
-- Again, or /agps setup. It opens on the player's own settings (the cards lit to what they have) and every pick is
-- applied at once (a live preview: the GPS map takes the minimap's corner at the size picked as it's clicked); Finish
-- keeps them, Skip, the X and Escape put back what was there when it opened (S.before, saved in `db.setup.before`
-- while it's open: a /reload or a crash meanwhile puts them back at the next login, S.RestoreSaved). A controller
-- (Pad.Device) moves through the cards with the D-pad, A picks, B goes back; override bindings of our own owner frame,
-- out of combat, as Pad.lua's (nothing of Blizzard's touched).
--
-- THE PICTURES: a card shows Media/Setup/<art>.tga (or .blp) when the client has the file (S.ImageKnown), else its
-- drawing of plain color boxes (S.ART). Exact size, never filtered above LINEAR: the picture is S.IMAGE_PX[cards on
-- the page] pixels (the top left of a power-of-two canvas, the rest clear, as Media's CornerLogo files; the screenshot
-- cut out of the game world with a gold glow, drawn straight on the card: no screen box behind it), shown pixel
-- for pixel on a 1440-high screen at UI scale 1 (S.REF_PPU) and at the same size in UI units on any other.
--
-- THE POPUPS (Kooki3z, 2026-11-25): one at login at most. A first install gets this setup, its last page What's New
-- (WhatsNew.lua); a player updating gets What's New alone, once a version, never the setup. The tutorial is never
-- offered by a popup (Tutorial.lua): only Options > Help and /agps tutorial start it.
--
-- THE TIPS: until the first route is done (a trip's last stop reached, Nav's arrive hooks), a fresh install shows a
-- short tip at a time where the route's directions go (the map's route panel, on the map or detached: the same
-- place) while there's no route to show, Next / Got It and Hide Tips on it. A fresh install's only (`db.tips.due`):
-- a player who has done routes never sees them.
local _, ns = ...
local L = ns.L or setmetatable({}, { __index = function(_, k) return k end })
local Format = ns.Format or string.format

local S = {}
ns.Setup = S

S.VERSION = 1 -- the setup shown once to a first install whose `db.setup.shown` is lower
S.DELAY = 6 -- seconds after the world is entered before the setup shows
S.W, S.H = 600, 380 -- the window
S.CARD_H = 176
S.PAD_OWNER = "AzerothGPSSetupPadOwner" -- (the controller's bindings' owner: never UIParent's)
S.PAD_KEYS = { PADDUP = "up", PADDDOWN = "down", PADDLEFT = "left", PADDRIGHT = "right", PAD1 = "a", PAD2 = "b",
  PADLSHOULDER = "lb", PADRSHOULDER = "rb" }
S.TIP_OWNER = "AzerothGPS tips" -- (Nav.arriveHooks)
-- The settings the setup can change: taken as it opens, put back by Skip / closing.
S.KEYS = { "replaceMinimap", "replaceMinimapSize", "useWorldMap",
  -- (and the What's New page's, WhatsNew.lua: item 34, a first install's last page)
  "useClassSpells", "expertJumper", "safeDropYd" }
S.SIZES = { { "small", L["Small"] }, { "medium", L["Medium"] }, { "large", L["Large"] } }

local function GPS() return ns.settings.gps end
local function DB() return ns.db end
local function InCombat() return (ns.inCombat or (InCombatLockdown and InCombatLockdown())) and true or false end
local function Call(f, script, ...)
  local fn = f and f.GetScript and f:GetScript(script)
  if fn then return pcall(fn, f, ...) end
  return false
end

---------------------------------------------------------------------------
-- The pages
---------------------------------------------------------------------------

-- A page: { id, title, key (the setting), cards = { { value, title, text, art, enabled() } }, sizes (the minimap
-- size row under the cards), when() (false: left out) }.
function S.BuildPages()
  S.PAGES = {
    { id = "minimap", title = L["Your minimap"], key = "replaceMinimap", sizes = true, cards = {
      { value = true, title = L["GPS minimap"], art = "gpsMinimap",
        text = L["The GPS map takes the minimap's corner, with the game's icons still on it."] },
      { value = false, title = L["The game's minimap"], art = "gameMinimap",
        text = L["Keep the game's own minimap as it is."] } } },
    { id = "map", title = L["Where the map opens"], key = "useWorldMap", cards = {
      { value = false, title = L["GPS map window"], art = "window",
        text = L["A window of its own that you can move and resize."] },
      { value = true, title = L["In the world map"], art = "worldMap",
        text = L["The GPS map shows inside the game's world map (M)."],
        -- (as Options' own: not with the game's controller UI on, GPSFrame's G.WorldMapWanted)
        enabled = function() return not (ns.GPS and ns.GPS.ControllerUI and ns.GPS.ControllerUI()) end } } },
    -- (item 34: the last page, What's New's picture and 1.4.0's new options live, WhatsNew.lua; Kooki3z: "new
    -- installs get the welcome only, and the What's New content becomes the welcome's last page")
    { id = "whatsnew", title = string.format(L["What's new in v%s"], ns.WhatsNew and ns.WhatsNew.VERSION or ""),
      whatsNew = true, cards = {}, when = function() return ns.WhatsNew ~= nil end },
  }
end
-- The pages shown this time (a page's `when()` false: left out).
function S.Pages()
  if not S.PAGES then S.BuildPages() end
  local out = {}
  for _, p in ipairs(S.PAGES) do
    if not p.when or p.when() then out[#out + 1] = p end
  end
  return out
end

---------------------------------------------------------------------------
-- The cards' pictures: a screenshot file where the client has one, else a drawing of plain color boxes
---------------------------------------------------------------------------

S.IMAGE_DIR = "Interface\\AddOns\\AzerothGPS\\Media\\Setup\\"
-- A card's picture in pixels, by the cards on its page (2: the minimap, where the map opens; the route directions and
-- icon size pages were taken out 2026-11-19). Made from in-game screenshots by `agps setup-art` (setupart.py).
S.IMAGE_PX = { [2] = { 300, 180 } }
S.REF_PPU = 1440 / 768 -- (screen pixels per UI unit the pictures are made for: ns.PixelsPerUnit, 1440 high, scale 1)
-- The picture's box on a card `w` wide with `n` on its page, in UI units (the drawing's too).
function S.ArtSize(n, w)
  local px = S.IMAGE_PX[n]
  if px then return px[1] / S.REF_PPU, px[2] / S.REF_PPU end
  local k = math.min((w - 16) / 100, 1.6)
  return 100 * k, 60 * k
end
-- Whether the client has the picture `art` (a file added since the last login hasn't: GetTextureFileID nil; anything
-- but a file's number: taken as not there, the drawing shown).
S.imageKnown = {}
function S.ImageKnown(art)
  local k = S.imageKnown[art]
  if k ~= nil then return k end
  if not S.probe then
    if not (UIParent and UIParent.CreateTexture) then return false end
    S.probe = UIParent:CreateTexture(nil, "BACKGROUND")
    S.probe:Hide()
  end
  S.probe:SetTexture(S.IMAGE_DIR .. art)
  k = false
  if S.probe.GetTextureFileID then
    local ok, id = pcall(S.probe.GetTextureFileID, S.probe)
    k = (ok and type(id) == "number") and true or false
  end
  S.imageKnown[art] = k
  return k
end
-- Card art frame `a` (S.ArtSize big) showing picture `art` from its file, pixel for pixel at S.REF_PPU: the
-- picture's pixels in the top left of its power-of-two canvas. False: no file (the drawing instead).
function S.ShowImage(a, art, n)
  local px = S.IMAGE_PX[n]
  if not (px and art and S.ImageKnown(art)) then return false end
  local t = a:CreateTexture(nil, "ARTWORK")
  t:SetAllPoints()
  t:SetTexture(S.IMAGE_DIR .. art)
  local pw, ph = 1, 1
  while pw < px[1] do pw = pw * 2 end
  while ph < px[2] do ph = ph * 2 end
  t:SetTexCoord(0, px[1] / pw, 0, px[2] / ph)
  if t.SetSnapToPixelGrid then t:SetSnapToPixelGrid(true) end
  a.image = t
  return true
end

local SCREEN = { 0.16, 0.17, 0.2, 1 }
local MAP = { 0.25, 0.42, 0.24, 1 }
local ROAD = { 0.95, 0.8, 0.25, 1 }
local DARK = { 0.03, 0.03, 0.04, 0.9 }
local FRAME = { 0.55, 0.5, 0.42, 1 }
local GAME = { 0.42, 0.45, 0.5, 1 }
local PARCH = { 0.62, 0.53, 0.36, 1 }
local WHITE = { 0.92, 0.92, 0.92, 1 }

-- a box at (x, y) from the drawing's top left, w x h, in a 100 x 60 drawing scaled to the card
local function Box(art, x, y, w, h, c)
  local t = art:CreateTexture(nil, "ARTWORK")
  local k = art.k
  t:SetPoint("TOPLEFT", art, "TOPLEFT", x * k, -y * k)
  t:SetSize(math.max(1, w * k), math.max(1, h * k))
  t:SetColorTexture(c[1], c[2], c[3], c[4] or 1)
  return t
end
S.ART = {
  gpsMinimap = function(a)
    Box(a, 72, 4, 24, 24, FRAME) Box(a, 73, 5, 22, 22, MAP)
    Box(a, 76, 15, 14, 2, ROAD) Box(a, 88, 9, 2, 8, ROAD)
  end,
  gameMinimap = function(a) Box(a, 74, 4, 22, 22, GAME) Box(a, 83, 13, 4, 4, WHITE) end,
  window = function(a)
    Box(a, 22, 8, 56, 44, FRAME) Box(a, 22, 8, 56, 5, DARK) Box(a, 24, 13, 52, 37, MAP)
    Box(a, 30, 30, 34, 2, ROAD) Box(a, 62, 20, 2, 12, ROAD)
  end,
  worldMap = function(a)
    Box(a, 4, 4, 92, 52, PARCH) Box(a, 4, 4, 92, 5, DARK) Box(a, 22, 14, 56, 36, MAP)
    Box(a, 30, 32, 34, 2, ROAD)
  end,
}

---------------------------------------------------------------------------
-- The window
---------------------------------------------------------------------------

local function PanelButton(parent, label, onClick)
  local ok, b = pcall(CreateFrame, "Button", nil, parent, "UIPanelButtonTemplate")
  if not ok or not b then b = CreateFrame("Button", nil, parent) end
  b:SetHeight(22)
  b:SetScript("OnClick", onClick)
  function b.Label(self, text) -- (as wide as its text, longer in some languages)
    self:SetText(text)
    self:SetWidth(math.max(90, (self.GetTextWidth and self:GetTextWidth() or 0) + 24))
  end
  b:Label(label)
  return b
end
-- an outline of four lines round `f` (a card lit, the controller's focus)
local function Outline(parent, c, thick)
  local o = CreateFrame("Frame", nil, parent)
  o.lines = {}
  for i, p in ipairs({ { "TOPLEFT", "TOPRIGHT" }, { "BOTTOMLEFT", "BOTTOMRIGHT" }, { "TOPLEFT", "BOTTOMLEFT" },
    { "TOPRIGHT", "BOTTOMRIGHT" } }) do
    local t = o:CreateTexture(nil, "OVERLAY")
    t:SetPoint(p[1])
    t:SetPoint(p[2])
    if i <= 2 then t:SetHeight(thick) else t:SetWidth(thick) end
    t:SetColorTexture(c[1], c[2], c[3], c[4] or 1)
    o.lines[i] = t
  end
  o:Hide()
  return o
end

local function Card(parent)
  local b = CreateFrame("Button", nil, parent)
  b.bg = b:CreateTexture(nil, "BACKGROUND")
  b.bg:SetAllPoints()
  b.bg:SetColorTexture(0, 0, 0, 0.45)
  b.hover = b:CreateTexture(nil, "BORDER")
  b.hover:SetAllPoints()
  b.hover:SetColorTexture(1, 1, 1, 0.06)
  b.hover:Hide()
  b.art = CreateFrame("Frame", nil, b)
  b.art:SetPoint("TOP", 0, -8)
  b.title = b:CreateFontString(nil, "ARTWORK", "GameFontNormal")
  b.title:SetPoint("TOPLEFT", b.art, "BOTTOMLEFT", 0, -6)
  b.title:SetPoint("TOPRIGHT", b.art, "BOTTOMRIGHT", 0, -6)
  b.title:SetJustifyH("CENTER")
  b.text = b:CreateFontString(nil, "ARTWORK", "GameFontHighlightSmall")
  b.text:SetPoint("TOPLEFT", b.title, "BOTTOMLEFT", 0, -4)
  b.text:SetPoint("TOPRIGHT", b.title, "BOTTOMRIGHT", 0, -4)
  b.text:SetJustifyH("CENTER")
  b.text:SetWordWrap(true)
  b.lit = Outline(b, { 1, 0.82, 0, 1 }, 2)
  b.lit:SetAllPoints()
  b:SetScript("OnEnter", function(self) self.hover:Show() end)
  b:SetScript("OnLeave", function(self) self.hover:Hide() end)
  b:SetScript("OnClick", function(self)
    if self.agpsOn == false then return end
    S.Pick(self.page.key, self.card.value)
  end)
  return b
end

function S.Window()
  if S.window then return S.window end
  local f = ns.Window("AzerothGPSSetup", S.W, S.H, L["Welcome to AzerothGPS"], "DIALOG")
  f.step = f:CreateFontString(nil, "ARTWORK", "GameFontDisableSmall")
  f.step:SetPoint("TOPLEFT", 18, f.top - 6)
  f.heading = f:CreateFontString(nil, "ARTWORK", "GameFontNormalLarge")
  f.heading:SetPoint("TOPLEFT", f.step, "BOTTOMLEFT", 0, -4)
  f.heading:SetPoint("RIGHT", f, "RIGHT", -18, 0)
  f.heading:SetJustifyH("LEFT")
  f.cards = {}
  f.sizeLabel = f:CreateFontString(nil, "ARTWORK", "GameFontHighlight")
  f.sizes = {}
  for i, s in ipairs(S.SIZES) do
    local b = PanelButton(f, s[2], function() S.Pick("replaceMinimapSize", s[1]) end)
    b.value = s[1]
    b.lit = Outline(b, { 1, 0.82, 0, 1 }, 2)
    b.lit:SetPoint("TOPLEFT", -2, 2)
    b.lit:SetPoint("BOTTOMRIGHT", 2, -2)
    f.sizes[i] = b
  end
  f.skip = PanelButton(f, L["Skip"], function() S.Close(false) end)
  f.back = PanelButton(f, L["Back"], function() S.Go(-1) end)
  f.next = PanelButton(f, L["Next"], function() S.Go(1) end)
  f.skip:SetPoint("BOTTOMLEFT", 16, 14)
  f.next:SetPoint("BOTTOMRIGHT", -16, 14)
  f.back:SetPoint("RIGHT", f.next, "LEFT", -6, 0)
  f.hint = f:CreateFontString(nil, "ARTWORK", "GameFontDisableSmall")
  f.hint:SetPoint("BOTTOM", 0, 40)
  f.focus = Outline(f, { 1, 1, 1, 0.9 }, 1)
  -- (closed any other way than Finish, the X and Escape too: what it found put back)
  f:SetScript("OnHide", function()
    if S.open then S.Close(false) end
  end)
  f:HookScript("OnShow", function() S.PadApply() end)
  S.window = f
  return f
end

-- The page `i` laid out: its cards in a row, the size row under the minimap's.
function S.ShowPage(i)
  local f = S.Window()
  local pages = S.pages
  i = math.max(1, math.min(#pages, i))
  S.at = i
  local page = pages[i]
  f.step:SetText(Format(L["Step %d of %d"], i, #pages))
  f.heading:SetText(page.title)
  -- (the last step's button says Done, set first; every other page's widgets hidden before this one's are laid out:
  -- item 64, Kooki3z on 1173b42f, step 3 of 3 with step 2's cards and the focus box over it and "Next")
  f.back:SetEnabled(i > 1)
  f.next:Label(i == #pages and L["Done"] or L["Next"])
  f.focus:Hide()
  for _, b in ipairs(f.cards) do b:Hide() end
  -- (What's New's page: its content in place of the cards, WhatsNew.lua; built under a guard, an error logged and the
  -- rest of the page still laid out)
  if page.whatsNew and ns.WhatsNew then
    local ok, err = pcall(function()
      f.whatsNew = f.whatsNew or ns.WhatsNew.Build(f, 18, f.top - 50, S.W - 36)
      f.whatsNew:Show()
      ns.WhatsNew.Refresh()
      -- (Reset Defaults at the window's bottom right, over Back and Next, clear of the controller's hint)
      local r = f.whatsNew.reset
      r:ClearAllPoints()
      r:SetPoint("BOTTOMRIGHT", f, "BOTTOMRIGHT", -16, 14 + 22 + 8)
      -- (its window as tall as the content, Reset Defaults and the buttons under it: item 37)
      f:SetHeight(math.max(S.H, -f.top + 50 + f.whatsNew.height + 16 + 22 + 8 + 22 + 14))
    end)
    if not ok and ns.GPS and ns.GPS.LogError then ns.GPS.LogError("setup what's new", err) end
  elseif f.whatsNew then
    f.whatsNew:Hide()
    f:SetHeight(S.H)
  end
  local n = #page.cards
  local x0, gap = 18, 12
  local w = n > 0 and math.floor((S.W - 2 * x0 - (n - 1) * gap) / n) or 0
  for ci = 1, math.max(n, #f.cards) do
    local b = f.cards[ci]
    if ci <= n then
      b = b or Card(f)
      f.cards[ci] = b
      local card = page.cards[ci]
      b.page, b.card = page, card
      b:ClearAllPoints()
      b:SetPoint("TOPLEFT", f, "TOPLEFT", x0 + (ci - 1) * (w + gap), f.top - 50)
      b:SetSize(w, S.CARD_H)
      -- the picture: made again for the page (its file, else the drawing: 100 x 60 scaled to the box)
      if b.drawn ~= card then
        local old = b.art
        if old then old:Hide() end
        b.art = CreateFrame("Frame", nil, b)
        local aw, ah = S.ArtSize(n, w)
        b.art.k = aw / 100
        b.art:SetSize(aw, ah)
        b.art:SetPoint("TOP", 0, -8)
        local bg = b.art:CreateTexture(nil, "BACKGROUND")
        bg:SetAllPoints()
        bg:SetColorTexture(SCREEN[1], SCREEN[2], SCREEN[3], SCREEN[4])
        b.art.screen = bg
        -- (a picture is cut out with a glow round it: on the card's own background, no screen box behind it)
        if S.ShowImage(b.art, card.art, n) then bg:Hide() elseif S.ART[card.art] then S.ART[card.art](b.art) end
        b.title:ClearAllPoints()
        b.title:SetPoint("TOPLEFT", b.art, "BOTTOMLEFT", -4, -6)
        b.title:SetPoint("TOPRIGHT", b.art, "BOTTOMRIGHT", 4, -6)
        b.drawn = card
      end
      b.title:SetText(card.title)
      b.text:SetText(card.text)
      b.agpsOn = not card.enabled or card.enabled() and true or false
      b:SetAlpha(b.agpsOn and 1 or 0.4)
      b:Show()
    elseif b then
      b:Hide()
    end
  end
  f.sizeLabel:ClearAllPoints()
  f.sizeLabel:SetPoint("TOPLEFT", f, "TOPLEFT", x0, f.top - 50 - S.CARD_H - 16)
  f.sizeLabel:SetText(L["Minimap size"])
  local prev
  for _, b in ipairs(f.sizes) do
    b:ClearAllPoints()
    if prev then b:SetPoint("LEFT", prev, "RIGHT", 6, 0) else b:SetPoint("LEFT", f.sizeLabel, "RIGHT", 12, 0) end
    prev = b
  end
  S.Refresh()
  S.FocusFirst()
end

-- The cards lit by the settings now, the size row shown with the GPS minimap picked.
function S.Refresh()
  local f, page = S.window, S.pages and S.pages[S.at]
  if not (f and page) then return end
  local st = GPS()
  for _, b in ipairs(f.cards) do
    if b:IsShown() then
      local on = b.page == page and S.Value(page.key) == b.card.value
      b.lit:SetShown(on)
      b.title:SetTextColor(on and 1 or 0.85, on and 0.82 or 0.85, on and 0 or 0.85)
    end
  end
  local sizes = page.sizes and st.replaceMinimap == true
  f.sizeLabel:SetShown(sizes and true or false)
  local cur = st.replaceMinimapSize or "small"
  for _, b in ipairs(f.sizes) do
    b:SetShown(sizes and true or false)
    b.lit:SetShown(sizes and b.value == cur or false)
  end
  f.hint:SetText(S.padBound and Format(L["%s: Move   %s: Pick   %s: Back"], L["D-pad"], ns.Pad.KeyLabel("PAD1"),
    ns.Pad.KeyLabel("PAD2")) or "")
end

-- A setting as the setup reads it (its default where unset: Core's DEFAULTS).
function S.Value(key)
  local v = GPS()[key]
  if v == nil and ns.DEFAULTS and ns.DEFAULTS.gps then v = ns.DEFAULTS.gps[key] end
  if key == "replaceMinimapSize" then return v or "small" end
  return v == true
end

-- A card picked: applied at once (the live preview).
function S.Pick(key, value)
  if not S.open then return false end
  GPS()[key] = value
  S.ApplyAll()
  S.Refresh()
  return true
end
function S.ApplyAll()
  local O = ns.Options
  if O and O.Apply then pcall(O.Apply) elseif ns.GPS and ns.GPS.ApplySettings then pcall(ns.GPS.ApplySettings) end
  if ns.Pad and ns.Pad.Apply then pcall(ns.Pad.Apply) end
end

-- Open it (Options' Run Setup Again, /agps setup, once by itself). Not in combat (the minimap can't be moved then).
function S.Open()
  if S.open then
    S.window:Raise()
    return true
  end
  if InCombat() then
    ns.Print(L["The setup can't open in combat. Try again after the fight."])
    return false
  end
  if ns.Tutorial and ns.Tutorial.run then
    ns.Print(L["The setup can't open while the tutorial runs."])
    return false
  end
  local st = GPS()
  S.before = {}
  for _, k in ipairs(S.KEYS) do S.before[k] = { v = st[k] } end
  local db = DB()
  if db and db.setup then
    db.setup.shown = math.max(tonumber(db.setup.shown) or 0, S.VERSION) -- (not by itself again, a /reload or not)
    db.setup.before = S.before -- (put back at the next login if it's never closed: S.RestoreSaved)
  end
  -- (What's New is its last page: never shown again on its own, WhatsNew.lua)
  if db and ns.WhatsNew then db.whatsNewSeen = ns.WhatsNew.VERSION end
  S.pages = S.Pages()
  S.open = true
  local f = S.Window()
  -- (Options shut: its own controller bindings and its window aren't over the setup)
  local ow = rawget(_G, "AzerothGPSOptions")
  if ow and ow:IsShown() then ow:Hide() end
  f:ClearAllPoints()
  f:SetPoint("CENTER", 0, 60)
  S.ShowPage(1)
  f:Show()
  f:Raise()
  S.PadApply()
  S.FocusFirst()
  return true
end
-- Shut it: kept (Finish) or put back as it was (Skip, the X, Escape). Never shown by itself again either way.
function S.Close(keep)
  if not S.open then return false end
  S.open = false
  if not keep and S.before then
    local st = GPS()
    local W = ns.WhatsNew
    for k, was in pairs(S.before) do
      local changed = st[k] ~= was.v
      st[k] = was.v
      if changed and W and W.Applied then W.Applied(k) end -- (the grids on or off again, rerouted: WhatsNew.lua)
    end
  end
  S.before = nil
  local db = DB()
  if db and db.setup then
    db.setup.shown = math.max(tonumber(db.setup.shown) or 0, S.VERSION)
    db.setup.done = ns.VERSION or true
    db.setup.before = nil
  end
  S.ApplyAll()
  if S.window and S.window:IsShown() then S.window:Hide() end
  S.PadApply()
  if keep then ns.Print(L["Setup done. Options > Help runs it again any time."]) end
  return true
end
-- At login (InitDB), before anything is applied: a setup left open by a /reload or a crash has its live preview
-- saved over the player's settings; put back what they had.
function S.RestoreSaved(db)
  local su = db and db.setup
  local before = su and su.before
  if type(before) ~= "table" then return false end
  su.before = nil
  local st = db.settings and db.settings.gps
  if type(st) ~= "table" then return false end
  for _, k in ipairs(S.KEYS) do
    local was = before[k]
    if type(was) == "table" then st[k] = was.v end
  end
  return true
end
function S.Go(dir)
  if not S.open then return false end
  local i = (S.at or 1) + dir
  if i > #S.pages then return S.Close(true) end
  if i < 1 then return false end
  S.ShowPage(i)
  return true
end
function S.Shown() return (S.open and S.window and S.window:IsShown()) and true or false end

-- Once, a first install's only (`fresh`; the stamp under S.VERSION), some seconds after the world is entered, out of
-- combat (else when the fight ends). A player updating never gets it by itself (What's New instead).
function S.Due()
  local db = DB()
  local su = db and db.setup
  return (su and su.fresh and (tonumber(su.shown) or 0) < S.VERSION) and true or false
end
function S.MaybeShow()
  if not S.Due() or S.open then return false end
  if InCombat() or (ns.Tutorial and ns.Tutorial.run) then
    S.waiting = true
    return false
  end
  S.waiting = nil
  return S.Open()
end
function S.OnEnteringWorld()
  if S.asked or not S.Due() or not (C_Timer and C_Timer.After) then return end
  S.asked = true
  C_Timer.After(S.DELAY, function() pcall(S.MaybeShow) end)
end


---------------------------------------------------------------------------
-- The controller in the setup: the D-pad through the cards and buttons, A picks, B back (first page: closes)
---------------------------------------------------------------------------

-- What can take the focus, row by row: the cards, the size row (when shown), the buttons.
function S.Rows()
  local f = S.window
  local rows = {}
  if not f then return rows end
  local cards = {}
  for _, b in ipairs(f.cards) do
    if b:IsShown() and b.agpsOn ~= false then cards[#cards + 1] = b end
  end
  if #cards > 0 then rows[#rows + 1] = cards end
  local sizes = {}
  for _, b in ipairs(f.sizes) do
    if b:IsShown() then sizes[#sizes + 1] = b end
  end
  if #sizes > 0 then rows[#rows + 1] = sizes end
  local btns = { f.skip }
  if f.back:IsEnabled() then btns[#btns + 1] = f.back end
  btns[#btns + 1] = f.next
  rows[#rows + 1] = btns
  return rows
end
function S.SetFocus(ri, ci)
  local rows = S.Rows()
  local f = S.window
  ri = math.max(1, math.min(#rows, ri or 1))
  local row = rows[ri]
  if not row then return nil end
  ci = math.max(1, math.min(#row, ci or 1))
  S.focusRow, S.focusCol, S.focus = ri, ci, row[ci]
  local o = f.focus
  o:SetParent(S.focus)
  o:ClearAllPoints()
  o:SetPoint("TOPLEFT", S.focus, "TOPLEFT", -4, 4)
  o:SetPoint("BOTTOMRIGHT", S.focus, "BOTTOMRIGHT", 4, -4)
  o:SetFrameLevel((S.focus:GetFrameLevel() or 1) + 5)
  o:SetShown(S.padBound and true or false)
  return S.focus
end
-- the focus on the card picked (else the first), as a page opens
function S.FocusFirst()
  local f = S.window
  local ci = 1
  local n = 0
  for _, b in ipairs(f.cards) do
    if b:IsShown() and b.agpsOn ~= false then
      n = n + 1
      if b.lit:IsShown() then ci = n end
    end
  end
  S.SetFocus(1, ci)
end
function S.PadDo(what)
  if not S.Shown() then return false end
  local ri, ci = S.focusRow or 1, S.focusCol or 1
  if what == "left" then S.SetFocus(ri, ci - 1)
  elseif what == "right" then S.SetFocus(ri, ci + 1)
  elseif what == "up" or what == "down" then
    local rows = S.Rows()
    local nr = ri + (what == "down" and 1 or -1)
    if rows[nr] then
      -- (to the next row's control nearest across: the cards' row is wider than the buttons')
      local nci = math.max(1, math.min(#rows[nr], math.floor((ci - 0.5) * #rows[nr] / math.max(1, #rows[ri]) + 0.5)))
      if what == "down" and nr == #rows then nci = #rows[nr] end -- (onto Next / Finish)
      S.SetFocus(nr, nci)
    end
  elseif what == "a" then
    local b = S.focus
    if b and b:IsShown() then
      local onPage = S.at
      Call(b, "OnClick", "LeftButton")
      if S.Shown() and S.at ~= onPage then return true end -- (Next / Back: the new page's own focus)
      if S.Shown() then S.SetFocus(S.focusRow, S.focusCol) end
    end
  elseif what == "b" then
    if (S.at or 1) > 1 then S.Go(-1) else S.Close(false) end
  elseif what == "lb" then S.Go(-1)
  elseif what == "rb" then S.Go(1)
  end
  return true
end

local owner
local padButtons = {}
local function Owner()
  if not owner then
    owner = CreateFrame("Frame", S.PAD_OWNER, UIParent)
    owner:Hide()
  end
  return owner
end
local function PadButton(key)
  local b = padButtons[key]
  if b then return b end
  b = CreateFrame("Button", "AzerothGPSSetupPad_" .. key, Owner())
  b:RegisterForClicks("AnyDown")
  b:SetScript("OnClick", function()
    if ns.Pad and ns.Pad.SawInput then pcall(ns.Pad.SawInput, true) end
    local ok, err = pcall(S.PadDo, S.PAD_KEYS[key])
    if not ok and ns.GPS and ns.GPS.LogError then ns.GPS.LogError("setup controller", err) end
  end)
  padButtons[key] = b
  return b
end
-- Bound while the setup shows with a controller in use (whatever the controller option says), out of combat.
function S.PadWanted()
  return S.Shown() and ns.Pad ~= nil and ns.Pad.Device() ~= nil and not InCombat()
end
S.padBound = false
function S.PadApply()
  if InCombatLockdown and InCombatLockdown() then return false end
  local want = S.PadWanted() and true or false
  if want ~= S.padBound then
    local o = Owner()
    if want then
      for key in pairs(S.PAD_KEYS) do
        PadButton(key)
        pcall(SetOverrideBindingClick, o, true, key, "AzerothGPSSetupPad_" .. key, "LeftButton")
      end
    else
      pcall(ClearOverrideBindings, o)
    end
    S.padBound = want
    -- (the map's and Options' own bindings off meanwhile, back after: Pad.Wanted, PadOptions' PO.Wanted)
    if ns.Pad and ns.Pad.Apply and not S.inPadApply then
      S.inPadApply = true
      pcall(ns.Pad.Apply)
      S.inPadApply = nil
    end
  end
  if S.window then
    S.window.focus:SetShown(want and S.focus ~= nil)
    if S.open then S.Refresh() end
  end
  return want
end
-- before combat's lockdown (Pad.Clear: PLAYER_REGEN_DISABLED, logout)
function S.PadClear()
  if owner and not (InCombatLockdown and InCombatLockdown()) then pcall(ClearOverrideBindings, owner) end
  S.padBound = false
  if S.window then S.window.focus:Hide() end
end

---------------------------------------------------------------------------
-- The first route's tips, in the route panel's place
---------------------------------------------------------------------------

function S.BuildTips()
  S.TIPS = {
    { L["Place a stop"], L["Double-click anywhere on the map to place a stop."] },
    { L["Start the route"], L["Click Confirm Route. It also starts by itself after 5 seconds of no further map activity."] },
    { L["Open the search"], L["Click the magnifier, Search Places, in the map menu."] },
    { L["Quest Route"], L["Click Quest Route in the map menu."] },
    { L["Create a pin"], L["Hold Shift and click a spot on the map, then click Create Pin."] },
  }
end
local function Tips() local db = DB() return db and db.tips end
-- The tips still to be shown: a fresh install's, until its first route is done or they're hidden.
function S.TipsOn()
  local t = Tips()
  return (t and t.due) and true or false
end
-- Shown now: on, no route in the panel, the map showing as a map (not the minimap square), nothing holding it, not
-- during the setup or the tutorial.
function S.TipsWanted(G)
  if not S.TipsOn() or not G or G.clone then return false end
  local nav = G.navPanel
  if not nav or nav:IsShown() then return false end
  if not (G.IsVisible and G.IsVisible()) then return false end
  if G.MinimapMode and G.MinimapMode() then return false end
  if G.Held and G.Held() then return false end
  if S.Shown() or (ns.Tutorial and ns.Tutorial.run) then return false end
  return true
end
function S.TipPanel()
  if S.tipPanel then return S.tipPanel end
  local p = CreateFrame("Frame", nil, UIParent, BackdropTemplateMixin and "BackdropTemplate" or nil)
  if p.SetBackdrop then
    p:SetBackdrop({ bgFile = "Interface\\Buttons\\WHITE8X8" })
    p:SetBackdropColor(0, 0, 0, 0.75)
  end
  p:EnableMouse(true)
  p.head = p:CreateFontString(nil, "ARTWORK", "GameFontNormal")
  p.head:SetPoint("TOPLEFT", 8, -6)
  p.head:SetPoint("TOPRIGHT", -8, -6)
  p.head:SetJustifyH("LEFT")
  p.text = p:CreateFontString(nil, "ARTWORK", "GameFontHighlightSmall")
  p.text:SetPoint("TOPLEFT", p.head, "BOTTOMLEFT", 0, -3)
  p.text:SetPoint("TOPRIGHT", p.head, "BOTTOMRIGHT", 0, -3)
  p.text:SetJustifyH("LEFT")
  p.text:SetWordWrap(true)
  p.next = PanelButton(p, L["Next"], function() S.NextTip() end)
  p.hide = PanelButton(p, L["Hide Tips"], function() S.HideTips() end)
  for _, b in ipairs({ p.next, p.hide }) do b:SetHeight(20) end
  p.next:SetPoint("BOTTOMRIGHT", -6, 6)
  p.hide:SetPoint("RIGHT", p.next, "LEFT", -4, 0)
  -- (the map hidden, a detached panel's place on the screen: gone with it)
  p:SetScript("OnUpdate", function(self)
    local G = ns.GPS
    if not S.TipsWanted(G) then self:Hide() end
  end)
  p:Hide()
  S.tipPanel = p
  return p
end
function S.FillTip()
  local p = S.tipPanel
  if not p then return end
  if not S.TIPS then S.BuildTips() end
  local t = Tips()
  local n = #S.TIPS
  local i = math.max(1, math.min(n, tonumber(t.at) or 1))
  p.head:SetText(Format(L["Tip %d of %d: %s"], i, n, S.TIPS[i][1]))
  p.text:SetText(S.TIPS[i][2])
  p.next:Label(i >= n and L["Got It"] or L["Next"])
  p:SetHeight(6 + (p.head:GetStringHeight() or 14) + 3 + (p.text:GetStringHeight() or 24) + 34)
end
-- From the map's route panel's update (GPSFrame's G.UpdateNavPanel): shown in the panel's place when wanted.
function S.RefreshTips(G)
  local want = S.TipsWanted(G)
  local p = S.tipPanel
  if not want then
    if p and p:IsShown() then p:Hide() end
    return false
  end
  p = S.TipPanel()
  local nav = G.navPanel
  local parent = nav:GetParent() or UIParent
  if p:GetParent() ~= parent then p:SetParent(parent) end
  p:SetFrameStrata(nav:GetFrameStrata() or "MEDIUM")
  local level = (nav:GetFrameLevel() or 1) + 2
  p:SetFrameLevel(level)
  -- (its buttons above it: made while it was on UIParent, they kept that low level when it was raised, and the
  -- panel's own mouse took their clicks: "Next" and "Hide Tips" did nothing, on the map and detached, 1.3.10)
  for _, b in ipairs({ p.next, p.hide }) do b:SetFrameLevel(level + 2) end
  p:ClearAllPoints()
  p:SetPoint("TOPLEFT", nav, "TOPLEFT", 0, 0)
  p:SetWidth(math.max(240, nav:GetWidth() or 0))
  S.FillTip()
  p:Show()
  return true
end
function S.NextTip()
  local t = Tips()
  if not t then return end
  if not S.TIPS then S.BuildTips() end
  local i = tonumber(t.at) or 1
  if i >= #S.TIPS then return S.HideTips() end -- (Got It on the last one)
  t.at = i + 1
  S.FillTip()
end
-- No more tips (Hide Tips, Got It on the last one, the first route done).
function S.HideTips()
  local t = Tips()
  if t then t.due, t.at = nil, nil end
  if S.tipPanel then S.tipPanel:Hide() end
end
-- A trip's last stop reached: the first route done, the tips with it.
function S.OnArrive(info)
  if info and info.last and S.TipsOn() then S.HideTips() end
end

function S.Init()
  if S.inited then return end
  S.inited = true
  S.BuildPages()
  S.BuildTips()
  if ns.Nav and ns.Nav.arriveHooks then ns.Nav.arriveHooks[S.TIP_OWNER] = S.OnArrive end
  local ev = CreateFrame("Frame")
  ev:RegisterEvent("PLAYER_REGEN_ENABLED")
  ev:SetScript("OnEvent", function()
    if S.waiting then pcall(S.MaybeShow) end
  end)
  S.events = ev
end
