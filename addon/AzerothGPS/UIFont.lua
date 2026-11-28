-- The UI's text style on our HUD text (Kooki3z for 1.4.2: "can we by default for directions use the UI's themed text
-- style?"): with a full UI replacement loaded (DaylightUI, EllesmereUI), the directions (Arrow.lua's panel, the map's
-- route panel), the map's info line and the height strip's label take that UI's font face and its outline and shadow.
-- Their size stays ours (the font object's size, times Options > Directions' Text size on the directions): the
-- player's size slider keeps meaning what it says, and a UI's own scale is for its own windows. Colors stay ours: the
-- lines' color codes (red enemy territory, orange elite, blue swim...) are in the text, and a font string's own color is
-- kept. The options window and menus keep the game's font.
-- Read only, through each UI's own functions: DaylightUI.API (Font, GetSetting("general", "textOutline"/"textShadow"),
-- its StyleChanged event), EllesmereUI's GetFontPath/GetFontOutlineFlag/GetFontUseShadow (its global font, nil module
-- key), followed when it drops its font cache (InvalidateFontCache: a font picked, a profile switched). Nothing of
-- theirs is ever written. Option `dirTextStyle` (Options > Directions): "ui" (default) or "agps", the game's font.
-- A font that doesn't load (SetFont false) falls back to ours, and is not tried again until the UI's font changes.
local _, ns = ...

local U = {}
ns.UIFont = U

U.SHADOW = { 1, -1 } -- the drop shadow's offset, both UIs'
U.DUI_SHADOW_A = 0.6 -- DaylightUI's shadow alpha (its Style.TEXT_SHADOW)
U.EUI_SHADOW_A = 1 -- EllesmereUI's (its EllesmereUIShadowFont)
-- Languages the UI's font may lack the letters of: with our text in one of them and the client in another, the UI's
-- font (picked for the client's language) would show squares, so ours stays.
U.OWN_ALPHABET = { koKR = true, zhCN = true, zhTW = true, ruRU = true }

U.texts = {} -- our font strings that take the style, in order
U.base = setmetatable({}, { __mode = "k" }) -- fs -> its own font, kept from when it was registered
U.bad = {} -- font files that didn't load
U.shown = nil -- the style's key last put on the texts ("" for ours)
U.hooked = {}

local function S() return ns.settings and ns.settings.gps or {} end

local function Loaded(name)
  local G = ns.GPS
  if G and G.AddOnLoaded then return G.AddOnLoaded(name) end
  local fn = (C_AddOns and C_AddOns.IsAddOnLoaded) or rawget(_G, "IsAddOnLoaded")
  if not fn then return false end
  local ok, on = pcall(fn, name)
  return (ok and on) and true or false
end

local function Call(fn, ...)
  if type(fn) ~= "function" then return nil end
  local ok, v = pcall(fn, ...)
  if ok then return v end
  return nil
end

local function DaylightAPI()
  if not Loaded("DaylightUI") then return nil end
  local dui = rawget(_G, "DaylightUI")
  local api = type(dui) == "table" and rawget(dui, "API")
  if type(api) ~= "table" or type(api.Font) ~= "function" then return nil end
  return api
end

local function Ellesmere()
  if not Loaded("EllesmereUI") then return nil end
  local e = rawget(_G, "EllesmereUI")
  if type(e) ~= "table" or type(e.GetFontPath) ~= "function" then return nil end
  return e
end

-- The UI whose text style we can read, by name, else nil.
function U.Source()
  if DaylightAPI() then return "DaylightUI" end
  if Ellesmere() then return "EllesmereUI" end
  return nil
end

-- That UI's text style, read now: { file, flags, shadow (its alpha, 0 none), ui }, else nil.
function U.Read()
  local api = DaylightAPI()
  if api then
    local file = Call(api.Font)
    if type(file) ~= "string" or file == "" then return nil end
    local outline = type(api.GetSetting) == "function" and Call(api.GetSetting, "general", "textOutline")
    local shadow = type(api.GetSetting) == "function" and Call(api.GetSetting, "general", "textShadow")
    return { file = file, flags = type(outline) == "string" and outline or "OUTLINE",
      shadow = shadow == false and 0 or U.DUI_SHADOW_A, ui = "DaylightUI" }
  end
  local e = Ellesmere()
  if e then
    local file = Call(e.GetFontPath, nil)
    if type(file) ~= "string" or file == "" then return nil end
    local flags = Call(e.GetFontOutlineFlag, nil)
    local shadow = Call(e.GetFontUseShadow, nil)
    return { file = file, flags = type(flags) == "string" and flags or "",
      shadow = shadow == true and U.EUI_SHADOW_A or 0, ui = "EllesmereUI" }
  end
  return nil
end

-- The style our texts should have now, else nil (ours): the option, the UI's style, a font that loads, an alphabet it has.
function U.Wanted()
  if S().dirTextStyle == "agps" then return nil end
  local client = (GetLocale and GetLocale()) or "enUS"
  if ns.LOCALE and ns.LOCALE ~= client and U.OWN_ALPHABET[ns.LOCALE] then return nil end
  local st = U.Read()
  if not st or U.bad[st.file] then return nil end
  return st
end

local function Num(v) return type(v) == "number" and v or nil end

local function Keep(fs)
  if U.base[fs] then return U.base[fs] end
  local b = {}
  local ok, obj = pcall(fs.GetFontObject, fs)
  if ok and obj ~= nil then b.obj = obj end
  local okF, file, size, flags = pcall(fs.GetFont, fs)
  if okF then b.file, b.size, b.flags = file, Num(size), flags end
  local okO, x, y = pcall(fs.GetShadowOffset, fs)
  if okO and Num(x) and Num(y) then b.sx, b.sy = x, y end
  local okC, r, g, bl, a = pcall(fs.GetShadowColor, fs)
  if okC and Num(r) and Num(g) and Num(bl) then b.sc = { r, g, bl, Num(a) or 1 } end
  U.base[fs] = b
  return b
end

-- Back to its own font (its font object: SetFont with the object's file would lose its other alphabets, Arrow.lua's
-- ScaleText), its own shadow and the color it has now.
local function Restore(fs, b)
  if not fs.agpsUIStyled then return end
  fs.agpsUIStyled = nil
  local okT, r, g, bl, a = pcall(fs.GetTextColor, fs)
  if b.obj ~= nil and fs.SetFontObject then
    pcall(fs.SetFontObject, fs, b.obj)
  elseif b.file and b.size then
    pcall(fs.SetFont, fs, b.file, b.size, b.flags or "")
  end
  if b.sx then pcall(fs.SetShadowOffset, fs, b.sx, b.sy) end
  if b.sc then pcall(fs.SetShadowColor, fs, b.sc[1], b.sc[2], b.sc[3], b.sc[4]) end
  if okT and Num(r) and Num(g) and Num(bl) then pcall(fs.SetTextColor, fs, r, g, bl, Num(a) or 1) end
end

-- The style on one text; false when its font didn't load (the text back to its own).
local function Put(fs, st)
  local b = Keep(fs)
  if not st then
    Restore(fs, b)
    return true
  end
  local size = b.size or 12
  local ok, set = pcall(fs.SetFont, fs, st.file, size, st.flags or "")
  if not ok or set == false then
    fs.agpsUIStyled = true -- (whatever that SetFont left, put back)
    Restore(fs, b)
    return false
  end
  fs.agpsUIStyled = true
  pcall(fs.SetShadowOffset, fs, U.SHADOW[1], U.SHADOW[2])
  pcall(fs.SetShadowColor, fs, 0, 0, 0, st.shadow or 0)
  return true
end

local function Key(st)
  if not st then return "" end
  return st.ui .. "|" .. st.file .. "|" .. tostring(st.flags) .. "|" .. tostring(st.shadow)
end

-- Puts the style wanted now on every text (only when it changed, unless `force`).
function U.Refresh(force)
  local st = U.Wanted()
  local key = Key(st)
  if not force and key == U.shown then return end
  for _, fs in ipairs(U.texts) do
    if not Put(fs, st) then
      U.bad[st.file] = true -- (the UI's font doesn't load: ours, silently, till the UI's font changes)
      st, key = nil, ""
      for _, other in ipairs(U.texts) do Put(other, nil) end
      break
    end
  end
  U.shown = key
end

-- Our texts that take the style (the directions', the map's info line, the height strip's label), each styled now.
function U.Register(...)
  for i = 1, select("#", ...) do
    local fs = select(i, ...)
    if type(fs) == "table" and fs.SetFont and not U.base[fs] then
      Keep(fs)
      U.texts[#U.texts + 1] = fs
      local st = U.Wanted()
      if st and Key(st) == U.shown and not Put(fs, st) then
        U.bad[st.file] = true
        U.Refresh(true)
      end
    end
  end
  if U.shown == nil then U.Refresh(true) end
end

-- The UI's style changed (its settings applied, a profile switched): read it again on the next frame, once, after
-- that UI has finished (never inside its own call).
function U.OnUIChanged()
  if U.pending then return end
  U.pending = true
  local function Go()
    U.pending = nil
    U.Refresh()
  end
  if C_Timer and C_Timer.After then C_Timer.After(0, Go) else Go() end
end

-- Listens for each UI's style changes, once each.
function U.Hook()
  local api = DaylightAPI()
  if api and not U.hooked.DaylightUI and type(api.On) == "function" then
    if Call(api.On, "StyleChanged", U.OnUIChanged, "AzerothGPS") ~= nil then U.hooked.DaylightUI = true end
  end
  local e = Ellesmere()
  if e and not U.hooked.EllesmereUI and type(e.InvalidateFontCache) == "function" and hooksecurefunc then
    if pcall(hooksecurefunc, e, "InvalidateFontCache", U.OnUIChanged) then U.hooked.EllesmereUI = true end
  end
end

-- At login (after the map and the arrow made their texts) and at each loading screen (a UI picks its font at login).
function U.Init()
  U.Hook()
  U.Refresh(true)
end
function U.OnEnteringWorld()
  U.Hook()
  U.Refresh()
end

-- The option picked (Options > Directions).
function U.SetStyle(v)
  local st = ns.settings and ns.settings.gps
  if not st then return end
  st.dirTextStyle = (v == "agps") and "agps" or "ui"
  U.Refresh()
end

