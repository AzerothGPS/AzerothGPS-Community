-- Search Places with a controller: a legend of the search's buttons over its panel and an on-screen keyboard under it
-- (Kooki3z 2026-11-20: "How difficult would it be to add a qwerty keyboard to search for controller users? can we also
-- support keyboards in other languages?"; the layout from his screenshot: "legend for search controls in purple,
-- keyboard in green (X or open/close keyboard or something like that, A fading on highlighted letter, D-Pad also closes
-- keyboard and navigates the list)"); the Find Herbs and Ore window the same ("add D pad controller and keyboard
-- functions to this too"), one legend and one keyboard on whichever is up (K.Target). Only with the controller in use
-- (Pad.bound and Pad.used): a mouse and keyboard player sees nothing new.
--
-- With search open: the D-pad steps through the results (Pad.lua, the D-pad search), A picks one, X opens the keyboard,
-- B closes the search. The keyboard open: the D-pad moves between its keys, held repeating (never a stick: "We can't
-- take left stick unfortunately it moves the character", Kooki3z 2026-11-20), up from its top row back to the results
-- list (the keyboard closed, X opens it again on the key it was on), A types the key lit (the A button's icon pulsing on
-- it), B deletes a letter, X closes it.
--
-- The keys by the addon's language (ns.LOCALE: the game's, or /agps language), settings.gps.padKeyboard to pick another.
-- Text is UTF-8 throughout, a Delete takes a whole character; Korean is the 2-set (Dubeolsik) jamo keyboard composing
-- syllables as typed (K.HangulType / K.HangulBack). The key caps are our own pixel art (keyicons.py, Media\Keyboard),
-- the letters written over them as text so every layout shares the caps ("Keep keyboard themed with pixel art buttons
-- like the controller", Kooki3z 2026-11-20).
local _, ns = ...
local L = ns.L
local K = {}
ns.PadKeys = K

-- ---------------------------------------------------------------- UTF-8
-- (Lua 5.1 has no utf8 library: the box's text is UTF-8, and a key can be 2 or 3 bytes)
function K.Encode(cp)
  if cp < 0x80 then return string.char(cp) end
  if cp < 0x800 then return string.char(0xC0 + math.floor(cp / 0x40), 0x80 + cp % 0x40) end
  return string.char(0xE0 + math.floor(cp / 0x1000), 0x80 + math.floor(cp / 0x40) % 0x40, 0x80 + cp % 0x40)
end
-- the code point of the UTF-8 character `ch` (its first)
function K.CodePoint(ch)
  local b1, b2, b3 = ch:byte(1, 3)
  if not b1 then return nil end
  if b1 < 0x80 then return b1 end
  if b1 < 0xE0 then return (b1 - 0xC0) * 0x40 + (b2 or 0x80) - 0x80 end
  return (b1 - 0xE0) * 0x1000 + ((b2 or 0x80) - 0x80) * 0x40 + (b3 or 0x80) - 0x80
end
-- `s`'s characters, each a string
function K.Chars(s)
  local out = {}
  for ch in (s or ""):gmatch("[%z\1-\127\194-\244][\128-\191]*") do out[#out + 1] = ch end
  return out
end
function K.Len(s) return #K.Chars(s) end
-- `s` split before its last character: the text before, the character, its code point (nil, nil for "")
function K.LastChar(s)
  s = s or ""
  local i = #s
  if i == 0 then return "", nil, nil end
  while i > 1 do
    local b = s:byte(i)
    if b < 0x80 or b >= 0xC0 then break end
    i = i - 1
  end
  local ch = s:sub(i)
  return s:sub(1, i - 1), ch, K.CodePoint(ch)
end

-- ---------------------------------------------------------------- Hangul
-- Standard Unicode composition: a syllable is 0xAC00 + (initial * 21 + medial) * 28 + final; the keys are the
-- compatibility jamo (U+3131..U+3163). Worked out from the text itself, its last character, so nothing is kept between
-- presses: a consonant after a syllable with no final becomes its final (or a double final, ㄹ + ㄱ = ㄺ), a vowel after
-- a final takes it (or a double final's second half) as the next syllable's initial (한 + ㅏ = 하나), a vowel after a
-- lone consonant makes a syllable, two vowels a compound one (ㅗ + ㅏ = ㅘ). Delete takes the last jamo off.
local SBASE, VBASE = 0xAC00, 0x314F
local CHO = { 0x3131, 0x3132, 0x3134, 0x3137, 0x3138, 0x3139, 0x3141, 0x3142, 0x3143, 0x3145, 0x3146, 0x3147, 0x3148,
  0x3149, 0x314A, 0x314B, 0x314C, 0x314D, 0x314E }
local JONG = { 0x3131, 0x3132, 0x3133, 0x3134, 0x3135, 0x3136, 0x3137, 0x3139, 0x313A, 0x313B, 0x313C, 0x313D, 0x313E,
  0x313F, 0x3140, 0x3141, 0x3142, 0x3144, 0x3145, 0x3146, 0x3147, 0x3148, 0x314A, 0x314B, 0x314C, 0x314D, 0x314E }
local CHO_I, JONG_I = {}, {}
for i, cp in ipairs(CHO) do CHO_I[cp] = i - 1 end
for i, cp in ipairs(JONG) do JONG_I[cp] = i end
-- (two jamo making one: compound vowels, double finals; and each one's halves)
local VOWEL2 = { [0x3157] = { [0x314F] = 0x3158, [0x3150] = 0x3159, [0x3163] = 0x315A },
  [0x315C] = { [0x3153] = 0x315D, [0x3154] = 0x315E, [0x3163] = 0x315F }, [0x3161] = { [0x3163] = 0x3162 } }
local FINAL2 = { [0x3131] = { [0x3145] = 0x3133 }, [0x3134] = { [0x3148] = 0x3135, [0x314E] = 0x3136 },
  [0x3139] = { [0x3131] = 0x313A, [0x3141] = 0x313B, [0x3142] = 0x313C, [0x3145] = 0x313D, [0x314C] = 0x313E,
    [0x314D] = 0x313F, [0x314E] = 0x3140 }, [0x3142] = { [0x3145] = 0x3144 } }
local SPLIT = {}
for a, t in pairs(VOWEL2) do for b, c in pairs(t) do SPLIT[c] = { a, b } end end
for a, t in pairs(FINAL2) do for b, c in pairs(t) do SPLIT[c] = { a, b } end end
local function IsVowel(cp) return cp and cp >= VBASE and cp <= 0x3163 end
local function IsCons(cp) return cp and cp >= 0x3131 and cp < VBASE end
local function Syllable(cp)
  if not cp or cp < SBASE or cp > 0xD7A3 then return nil end
  local s = cp - SBASE
  return math.floor(s / 588), math.floor((s % 588) / 28), s % 28
end
local function Syl(l, v, t) return K.Encode(SBASE + (l * 21 + v) * 28 + (t or 0)) end
function K.HangulType(text, ch)
  text = text or ""
  local cp = K.CodePoint(ch)
  local pre, _, last = K.LastChar(text)
  local l, v, t = Syllable(last)
  if IsCons(cp) then
    if l and t == 0 and JONG_I[cp] then return pre .. Syl(l, v, JONG_I[cp]) end
    if l and t > 0 then
      local d = FINAL2[JONG[t]] and FINAL2[JONG[t]][cp]
      if d then return pre .. Syl(l, v, JONG_I[d]) end
    end
    return text .. ch
  end
  if IsVowel(cp) then
    if l and t == 0 then
      local c = VOWEL2[VBASE + v] and VOWEL2[VBASE + v][cp]
      if c then return pre .. Syl(l, c - VBASE, 0) end
      return text .. ch
    end
    if l then -- (its final moves on as the new syllable's initial; a double final's second half)
      local fin = JONG[t]
      local sp = SPLIT[fin]
      if sp then return pre .. Syl(l, v, JONG_I[sp[1]]) .. Syl(CHO_I[sp[2]], cp - VBASE, 0) end
      return pre .. Syl(l, v, 0) .. Syl(CHO_I[fin], cp - VBASE, 0)
    end
    if CHO_I[last] then return pre .. Syl(CHO_I[last], cp - VBASE, 0) end
    local c = VOWEL2[last] and VOWEL2[last][cp]
    if c then return pre .. K.Encode(c) end
  end
  return text .. ch
end
function K.HangulBack(text)
  local pre, ch, last = K.LastChar(text)
  if not ch then return "" end
  local l, v, t = Syllable(last)
  if l then
    if t > 0 then
      local sp = SPLIT[JONG[t]]
      return pre .. Syl(l, v, sp and JONG_I[sp[1]] or 0)
    end
    local sp = SPLIT[VBASE + v]
    if sp then return pre .. Syl(l, sp[1] - VBASE, 0) end
    return pre .. K.Encode(CHO[l + 1])
  end
  local sp = SPLIT[last]
  if sp then return pre .. K.Encode(sp[1]) end
  return pre
end

-- ---------------------------------------------------------------- layouts
-- Each row's keys, space-separated; the last row is always Space, Delete and Done. The accented letters a language
-- needs that its row keys don't have: an extra row.
K.LAYOUTS = {
  enUS = { "q w e r t y u i o p", "a s d f g h j k l '", "z x c v b n m -" },
  deDE = { "q w e r t z u i o p ü", "a s d f g h j k l ö ä", "y x c v b n m ß -" },
  frFR = { "a z e r t y u i o p", "q s d f g h j k l m", "w x c v b n ' -", "é è à ç ù ê â î ô" },
  esES = { "q w e r t y u i o p", "a s d f g h j k l ñ", "z x c v b n m ' -", "á é í ó ú ü" },
  itIT = { "q w e r t y u i o p", "a s d f g h j k l '", "z x c v b n m -", "à è é ì ò ù" },
  ptBR = { "q w e r t y u i o p", "a s d f g h j k l ç", "z x c v b n m ' -", "á â ã é ê í ó ô õ ú" },
  ruRU = { "й ц у к е н г ш щ з х ъ", "ф ы в а п р о л д ж э", "я ч с м и т ь б ю ё -" },
  -- (Dubeolsik: its shifted consonants and vowels an extra row)
  koKR = { "ㅂ ㅈ ㄷ ㄱ ㅅ ㅛ ㅕ ㅑ ㅐ ㅔ", "ㅁ ㄴ ㅇ ㄹ ㅎ ㅗ ㅓ ㅏ ㅣ", "ㅋ ㅌ ㅊ ㅍ ㅠ ㅜ ㅡ",
    "ㅃ ㅉ ㄸ ㄲ ㅆ ㅒ ㅖ", hangul = true },
}
K.LAYOUTS.enGB = K.LAYOUTS.enUS
K.LAYOUTS.esMX = K.LAYOUTS.esES
-- (Chinese is typed through an input method (pinyin or zhuyin to characters), which needs a dictionary and a candidate
-- list: not done yet, "all layouts except Chinese first". The Latin keys meanwhile, for the English names the search
-- also finds.)
K.LAYOUTS.zhCN = K.LAYOUTS.enUS
K.LAYOUTS.zhTW = K.LAYOUTS.enUS
function K.LayoutId()
  local gps = ns.settings and ns.settings.gps
  local pick = gps and gps.padKeyboard
  if pick and K.LAYOUTS[pick] then return pick end
  local loc = ns.LOCALE or (GetLocale and GetLocale()) or "enUS"
  return K.LAYOUTS[loc] and loc or "enUS"
end
-- the layout as rows of keys: { { ch = "q" } ..., { { kind = "space" }, { kind = "back" }, { kind = "done" } } }
K.WIDE = { space = 4, back = 2, done = 2 }
function K.Rows(id)
  local src = K.LAYOUTS[id or K.LayoutId()] or K.LAYOUTS.enUS
  local rows = {}
  for _, line in ipairs(src) do
    local row = {}
    -- (split at the spaces only, not %S: a UTF-8 byte such as à's 0xA0 can read as a space)
    for ch in line:gmatch("[^ ]+") do row[#row + 1] = { ch = ch, wide = 1 } end
    rows[#rows + 1] = row
  end
  rows[#rows + 1] = { { kind = "space", wide = 4 }, { kind = "back", wide = 2 }, { kind = "done", wide = 2 } }
  return rows, src.hangul and true or false
end

-- ---------------------------------------------------------------- typing
K.MAX_LETTERS = 40 -- (the box's own limit, characters)
-- `text` with key `ch` typed (Korean: composed)
function K.TypeText(text, ch, hangul)
  local out = hangul and K.HangulType(text, ch) or ((text or "") .. ch)
  if K.Len(out) > K.MAX_LETTERS then return text end
  return out
end
-- `text` with its last character (Korean: its last jamo) deleted
function K.BackText(text, hangul)
  if hangul then return K.HangulBack(text) end
  return (K.LastChar(text))
end

-- ---------------------------------------------------------------- the search boxes it serves
-- One legend and one keyboard for every search box of ours the controller can use (Kooki3z 2026-11-20, of Find Herbs
-- and Ore: "add D pad controller and keyboard functions to this too"): the map's Search Places panel and the Find Herbs
-- and Ore window. Each such frame (a "target") has `box` (its EditBox) and these: PadCount() (its rows), PadArrow(dir)
-- (the highlight a row "UP" or "DOWN", as its arrow keys), PadHighlight(i or nil), PadPick() (the highlighted row, as
-- Enter), PadSetText(text) (typed: its list follows), PadEnterList() (the row nearest the keyboard highlighted, coming
-- up off it), PadClose() (as Escape). GPSFrame's search panel and Layers.lua's finder set them.
local function G() return ns.GPS end
local Pad = function() return ns.Pad end
K.open = false
K.at = { 1, 1 } -- (the key lit: row, key; kept while closed, so X opens it on the same one)
K.KEY_UNITS, K.GAP, K.PAD = 20, 2, 6
K.ART_DIR = "Interface\\AddOns\\AzerothGPS\\Media\\Keyboard\\"
K.ART_PX = { 12, 14, 16, 18, 20, 24, 28, 32, 40 } -- (keyicons.py's ICON_PX)
K.ART_WIDE = { Key = 1, Key2 = 2, Key4 = 4 }
K.HINT_UNITS = 14 -- (the A button's icon on the lit key)
K.PULSE = 1.6 -- (seconds: the icon fades out and back in once)
K.LEGEND_PAD = 5

-- the search frames there are now, shown or not
function K.Candidates()
  local out = {}
  -- (Options' search box, PadOptions.lua's PO.KeysTarget: Options over everything, so first. Kooki3z 2026-11-20: "add
  -- the keyboard function to the search bar in Options to when controller is detected")
  local po = ns.Pad and ns.Pad.Opt
  if po and po.keysTarget then out[#out + 1] = po.keysTarget end
  local lay = ns.Layers
  if lay and lay.finder and lay.finder.PadCount then out[#out + 1] = lay.finder end -- (a window over the map: first)
  local g = G()
  if g and g.searchPanel and g.searchPanel.PadCount then out[#out + 1] = g.searchPanel end
  return out
end
-- The search the controller types into: the shown one whose box has the keys, else the first shown (the finder, a
-- window over the map, before the map's own panel).
function K.Target()
  local first
  for _, f in ipairs(K.Candidates()) do
    -- (a target can be up without being the controller's now: Options' search only while its box has the focus)
    if f:IsShown() and (not f.PadWanted or f.PadWanted()) then
      if f.box and f.box.HasFocus and f.box:HasFocus() == true then return f end
      first = first or f
    end
  end
  return first
end
function K.SearchShown() return K.Target() ~= nil end
-- The controller has a search: bound, in use, one open and no question of the map's in the way.
function K.Wants()
  local P = Pad()
  local t = K.Target()
  -- (the map's buttons ours, or the target's own: Options has bindings of its own while open, PadOptions.lua)
  if not (P and P.used and t and (P.bound or (t.PadBound and t.PadBound()))) then return false end
  local g = G()
  if P.Question() or (g and g.removeAsk and g.removeAsk:IsShown()) then return false end
  return true
end
local function Busy(t) if t then t.idle = 0 end end -- (the search panel's own timer: kept open while used)

-- the size drawn nearest the key's height on the screen, and the units it is pixel for pixel
function K.ArtPx(eff)
  local ppu = ns.PixelsPerUnit and ns.PixelsPerUnit(eff or 1) or 1
  local g = G()
  local px = g and g.NearestSize and g.NearestSize(K.ART_PX, K.KEY_UNITS * ppu) or K.KEY_UNITS
  return px, px / ppu
end
function K.ArtFile(name, px) return K.ART_DIR .. name .. "_" .. px end
local function Pot(v)
  local p = 1
  while p < v do p = p * 2 end
  return p
end
-- a key's cap drawn on texture `t` (its lit one or not): the art pixel for pixel, or a plain color till a relog makes
-- the new files known
function K.SetCap(t, wide, lit, px)
  local name = (wide == 4 and "Key4" or wide == 2 and "Key2" or "Key") .. (lit and "Lit" or "")
  local file = K.ArtFile(name, px)
  local g = G()
  t.name = name
  if g and g.ArtFileKnown and not g.ArtFileKnown(file) then
    t:SetTexCoord(0, 1, 0, 1)
    if lit then t:SetColorTexture(0.52, 0.41, 0.13, 1) else t:SetColorTexture(0.36, 0.36, 0.39, 1) end
    return
  end
  t:SetTexture(file)
  t:SetTexCoord(0, wide * px / Pot(wide * px), 0, px / Pot(px))
  if g and g.SnapTexture then g.SnapTexture(t) end
end
-- (the search panel's own look, for the keyboard and the legend: one piece with what they're on)
local function Look(f)
  if not f.SetBackdrop then return end
  f:SetBackdrop({ bgFile = "Interface\\Buttons\\WHITE8X8", edgeFile = "Interface\\Buttons\\WHITE8X8", edgeSize = 1 })
  f:SetBackdropColor(0.05, 0.05, 0.06, 0.95)
  f:SetBackdropBorderColor(0.3, 0.3, 0.3, 1)
end

local kb, legend
-- the keyboard's frame and keys on target `t` (under it: Kooki3z's "keyboard in green"), for the layout now (the keys
-- laid out again when the layout or the size changed)
function K.Build(t)
  if not t then return nil end
  if not kb then
    kb = CreateFrame("Frame", nil, t, "BackdropTemplate")
    Look(kb)
    kb:EnableMouse(true) -- (clicks on it don't fall through to the map)
    kb:Hide()
    kb.keys = {}
    kb.hint = CreateFrame("Frame", nil, kb)
    kb.hint:SetSize(K.HINT_UNITS, K.HINT_UNITS)
    kb.hint.text = kb.hint:CreateFontString(nil, "OVERLAY", "GameFontHighlight")
    kb.hint.text:SetPoint("CENTER")
    kb:SetScript("OnUpdate", function(_, dt) K.Pulse(dt) end)
    K.frame = kb
  end
  if kb.target ~= t then
    kb:SetParent(t)
    kb:ClearAllPoints()
    kb:SetPoint("TOPLEFT", t, "TOPLEFT", 0, 0) -- (placed for real just below, by its size)
    kb.target = t
    if not t.padHooked and t.HookScript then -- (the search closed: its keyboard too)
      t.padHooked = true
      t:HookScript("OnHide", function(self) if kb and kb.target == self then K.Close() end end)
    end
  end
  local eff = t.GetEffectiveScale and t:GetEffectiveScale() or 1
  local px, unit = K.ArtPx(eff)
  local id = K.LayoutId()
  if kb.id ~= id or kb.px ~= px then
    kb.id, kb.px, kb.unit = id, px, unit
    local rows, hangul = K.Rows(id)
    kb.rows, kb.hangul = rows, hangul
    for _, b in ipairs(kb.keys) do b:Hide() end
    local gap = K.GAP
    local widest = 0
    for _, row in ipairs(rows) do
      local w = -gap
      for _, key in ipairs(row) do w = w + key.wide * unit + gap end
      row.w = w
      widest = math.max(widest, w)
    end
    local n = 0
    for r, row in ipairs(rows) do
      local x = K.PAD + (widest - row.w) / 2
      local y = -K.PAD - (r - 1) * (unit + gap)
      for _, key in ipairs(row) do
        n = n + 1
        local b = kb.keys[n]
        if not b then
          b = CreateFrame("Frame", nil, kb)
          b.cap = b:CreateTexture(nil, "ARTWORK")
          b.cap:SetAllPoints()
          b.label = b:CreateFontString(nil, "OVERLAY", "GameFontHighlight")
          b.label:SetPoint("CENTER", 0, 1)
          kb.keys[n] = b
        end
        b:ClearAllPoints()
        b:SetPoint("TOPLEFT", kb, "TOPLEFT", x, y)
        b:SetSize(key.wide * unit, unit)
        key.button, key.x = b, x + key.wide * unit / 2
        b.key = key
        b.label:SetText(key.ch or (key.kind == "space" and L["Space"]) or (key.kind == "back" and L["Delete"])
          or L["Done"])
        b:Show()
        x = x + key.wide * unit + gap
      end
    end
    kb:SetSize(widest + 2 * K.PAD, #rows * (unit + gap) - gap + 2 * K.PAD)
    kb.w = widest + 2 * K.PAD
  end
  -- (under the search's left edge; a window wider than the keys: under its middle; a target placing it itself, its own
  -- place: Options', under its window, kept on the screen)
  kb:ClearAllPoints()
  if kb.SetClampedToScreen then kb:SetClampedToScreen(t.PadPlaceKeys ~= nil) end
  local tw = t.GetWidth and tonumber(t:GetWidth()) or 0
  if t.PadPlaceKeys then
    t.PadPlaceKeys(kb)
  elseif t == (G() and G().searchPanel) or tw <= (kb.w or 0) then
    kb:SetPoint("TOPLEFT", t, "BOTTOMLEFT", 0, -2)
  else
    kb:SetPoint("TOP", t, "BOTTOM", 0, -2)
  end
  K.Clamp()
  K.Light()
  return kb
end
function K.Clamp()
  local rows = kb and kb.rows
  if not rows then return end
  local r = math.max(1, math.min(#rows, K.at[1]))
  K.at = { r, math.max(1, math.min(#rows[r], K.at[2])) }
end
function K.Key()
  local row = kb and kb.rows and kb.rows[K.at[1]]
  return row and row[K.at[2]] or nil
end
-- the caps drawn, the lit one lit, the A button's icon on it
function K.Light()
  if not (kb and kb.rows) then return end
  for r, row in ipairs(kb.rows) do
    for i, key in ipairs(row) do
      local lit = r == K.at[1] and i == K.at[2]
      K.SetCap(key.button.cap, key.wide, lit, kb.px)
      key.button.lit = lit
    end
  end
  local key = K.Key()
  local P = Pad()
  local hint = kb.hint
  local icon = P and P.Key("select") and P.IconLabel(P.Key("select"), K.HINT_UNITS) or nil
  if key and icon then
    hint:SetParent(key.button)
    hint:ClearAllPoints()
    -- (over the key's bottom-right corner, so the letter under it still reads as the icon fades)
    hint:SetPoint("CENTER", key.button, "BOTTOMRIGHT", -3, 3)
    hint:SetFrameLevel((key.button:GetFrameLevel() or 1) + 5)
    hint.text:SetText(icon)
    hint:Show()
  else
    hint:Hide()
  end
end
-- the A icon's alpha `t` seconds in: a gentle pulse, never quite gone ("A fading on highlighted letter")
function K.PulseAlpha(t)
  return 0.3 + 0.7 * (0.5 + 0.5 * math.cos(2 * math.pi * ((t or 0) % K.PULSE) / K.PULSE))
end
function K.Pulse(dt)
  K.pulseT = (K.pulseT or 0) + (dt or 0)
  if kb and kb.hint then kb.hint:SetAlpha(K.PulseAlpha(K.pulseT)) end
end

function K.Open()
  local t = K.Target()
  if not t or not K.Build(t) then return false end
  K.open = true
  K.pulseT = 0
  K.SetButton(nil)
  kb:Show()
  t.PadHighlight(nil) -- (the D-pad is the keys' now, not the list's)
  Busy(t)
  K.Refresh()
  return true
end
function K.Close()
  K.open = false
  if kb then kb:Hide() end
  K.Refresh()
  return true
end
function K.Toggle()
  if K.open then return K.Close() end
  return K.Open()
end
-- The D-pad on the keys: `dir` "UP", "DOWN", "LEFT", "RIGHT". Left and right go round the row; up and down to the key
-- in the next row nearest above or below; up from the top row closes the keyboard into the list, on the row nearest it.
function K.Move(dir)
  if not (K.open and kb and kb.rows) then return false end
  local t = kb.target
  Busy(t)
  local rows = kb.rows
  local r, i = K.at[1], K.at[2]
  if dir == "LEFT" or dir == "RIGHT" then
    local n = #rows[r]
    i = ((i - 1 + (dir == "RIGHT" and 1 or -1)) % n) + 1
  else
    local to = r + (dir == "DOWN" and 1 or -1)
    if to < 1 then
      K.Close()
      if t and t.PadEnterList then t.PadEnterList() end
      return true
    end
    if to > #rows then return true end
    local x = rows[r][i].x
    local best, bd = 1, math.huge
    for k, key in ipairs(rows[to]) do
      local d = math.abs(key.x - x)
      if d < bd then best, bd = k, d end
    end
    r, i = to, best
  end
  K.at = { r, i }
  K.pulseT = 0
  K.Light()
  return true
end
-- A on the keys: the lit one typed into the box (as typing it: the list follows), Space a space, Delete a letter off,
-- Done the keyboard closed
function K.Press()
  local key = K.Key()
  local t = kb and kb.target
  if not (key and t and t.box) then return false end
  if key.kind == "done" then return K.Close() end
  if key.kind == "back" then return K.Back() end
  local ch = key.kind == "space" and " " or key.ch
  t.PadSetText(K.TypeText(t.box:GetText() or "", ch, kb.hangul))
  return true
end
function K.Back()
  local t = kb and kb.target
  if not (t and t.box) then return false end
  t.PadSetText(K.BackText(t.box:GetText() or "", kb.hangul))
  return true
end

-- A press on the pad with a search the controller's (K.Wants): true taken, nil left to Pad.Run (the D-pad, read each
-- frame by K.Tick; the zoom; the map menu's button)
function K.Run(has, down)
  if not down then return nil end
  local t = K.Target()
  if not t then return nil end
  if K.open and kb and kb.target ~= t then K.Close() end -- (another search came up: the keyboard goes with it)
  Busy(t)
  if has.select or has.yes then
    if K.open then return K.Press() end
    local b = K.Button()
    if b then -- (a window's button in focus: clicked, as the mouse does)
      local click = b:GetScript("OnClick")
      if click then click(b, "LeftButton") end
      -- (Show All grays itself out once clicked: the focus on the button before it)
      if not K.Button() then K.btn = nil K.StepButton(-1) else K.ShowButton() end
      return true
    end
    if t.PadCount() > 0 then
      t.PadPick()
      return true
    end
    return K.Open() -- (nothing to pick yet: the keys, to type something)
  end
  if has.remove then return K.Toggle() end
  if has.back then
    if K.open then return K.Back() end
    t.PadClose()
    return true
  end
  return nil
end

-- Each frame with a search the controller's: the D-pad held (`dx`, `dy`: -1, 0, 1) on the keys or the list, a step a
-- press and then repeating while held (Pad.SEARCH_REPEAT_FIRST, Pad.SEARCH_REPEAT). Returns whether the map's pan is
-- left the D-pad's left and right (the list only: up and down are its).
function K.Tick(dt, dx, dy)
  local P = Pad()
  local t = K.Target()
  local g = G()
  local dir
  local buttons = not K.open and t and t.PadButtons
  if K.open or buttons then
    dir = dy > 0 and "UP" or dy < 0 and "DOWN" or dx > 0 and "RIGHT" or dx < 0 and "LEFT" or nil
  else
    dir = dy > 0 and "UP" or dy < 0 and "DOWN" or nil
  end
  local function step()
    if K.open then K.Move(dir)
    elseif dir == "LEFT" or dir == "RIGHT" then K.StepButton(dir == "RIGHT" and 1 or -1)
    elseif t then
      if K.btn then -- (up or down off the buttons: back to the list, on its row from before, else the nearest)
        K.SetButton(nil)
        local back = K.listSel
        K.listSel = nil
        if back and back <= t.PadCount() then return t.PadHighlight(back) end
        if dir == "UP" and t.PadEnterList then return t.PadEnterList() end
        return t.PadArrow("DOWN")
      end
      t.PadArrow(dir)
    elseif g.SearchArrow then g.SearchArrow(dir) end
  end
  if not dir then
    P.searchDir = nil
  elseif P.searchDir ~= dir then
    P.searchDir, P.searchWait = dir, P.SEARCH_REPEAT_FIRST
    step()
  else
    P.searchWait = (P.searchWait or 0) - dt
    if P.searchWait <= 0 then
      P.searchWait = P.SEARCH_REPEAT
      step()
    end
  end
  return not (K.open or buttons)
end

-- A window's own buttons with the D-pad's left and right (Kooki3z 2026-11-20, Find Herbs and Ore's herbs and ore
-- buttons, Available and Show All: "Make D pad left and right on this screen toggle through these 4 options, fading
-- select button (A by default) to choose it"): the target's PadButtons() in order, round at the ends, a disabled or
-- hidden one skipped; the one in focus lit, the Select button's icon pulsing on it; A clicks it. Up or down: the list.
K.btn = nil -- (the button in focus, or nil)
function K.Buttons(t)
  local out = {}
  if not (t and t.PadButtons) then return out end
  for _, b in ipairs(t.PadButtons()) do
    if b and b:IsShown() and (not b.IsEnabled or b:IsEnabled()) then out[#out + 1] = b end
  end
  return out
end
function K.Button()
  local t = K.Target()
  if not K.btn then return nil end
  for _, b in ipairs(K.Buttons(t)) do
    if b == K.btn then return b end
  end
  return nil
end
function K.StepButton(step)
  local t = K.Target()
  local list = K.Buttons(t)
  if #list == 0 then return false end
  local at
  for i, b in ipairs(list) do if b == K.btn then at = i end end
  local i = at and ((at - 1 + step) % #list) + 1 or (step > 0 and 1 or #list)
  if not K.btn then K.listSel = t.sel or K.listSel end -- (the row it came from, for coming back)
  if t.PadHighlight then t.PadHighlight(nil) end -- (A is the button's now, not a row's)
  K.SetButton(list[i])
  return true
end
local mark
function K.SetButton(b)
  K.btn = b
  K.ShowButton()
end
-- the focus's look on its button: a soft gold wash over it and the Select button's icon pulsing at its middle (a wide
-- one: at its right end, clear of its text)
function K.ShowButton()
  local b = K.btn
  local P = Pad()
  if not b or not (b.IsShown and b:IsShown()) or K.open then
    if mark then mark:Hide() end
    return
  end
  if not mark then
    mark = CreateFrame("Frame", nil, b)
    mark.wash = mark:CreateTexture(nil, "OVERLAY")
    mark.wash:SetColorTexture(1, 0.82, 0.1, 0.25)
    mark.wash:SetBlendMode("ADD")
    mark.icon = CreateFrame("Frame", nil, mark)
    mark.icon:SetSize(K.HINT_UNITS, K.HINT_UNITS)
    mark.icon.text = mark.icon:CreateFontString(nil, "OVERLAY", "GameFontHighlight")
    mark.icon.text:SetPoint("CENTER")
    mark:SetScript("OnUpdate", function(self, dt)
      self.t = (self.t or 0) + (dt or 0)
      self.icon:SetAlpha(K.PulseAlpha(self.t))
    end)
    K.mark = mark
  end
  mark:SetParent(b)
  mark:ClearAllPoints()
  mark:SetAllPoints(b)
  mark:SetFrameLevel((b:GetFrameLevel() or 1) + 6)
  mark.wash:ClearAllPoints()
  mark.wash:SetAllPoints(mark)
  mark.icon:ClearAllPoints()
  local wide = P and P.HintWide and P.HintWide(b)
  if wide then mark.icon:SetPoint("CENTER", b, "RIGHT", -K.HINT_UNITS / 2 - 2, 0)
  else mark.icon:SetPoint("CENTER", b, "CENTER") end
  mark.icon.text:SetText(P and P.Key("select") and P.IconLabel(P.Key("select"), K.HINT_UNITS) or "")
  mark.t = 0
  mark:Show()
end

-- The legend over the search (Kooki3z's "legend for search controls in purple"): its buttons as the player has them
-- bound, their icons; the keyboard's own while it's open.
function K.LegendText()
  local P = Pad()
  local I = P.ActionIcon
  local dpad = P.Key("panUp") == "PADDUP" and P.Key("panDown") == "PADDDOWN" and P.KeyIcon("DPAD")
    or (I("panUp") .. "/" .. I("panDown"))
  if K.open then
    return string.format(L["%s: Move   %s: Type   %s: Close Keyboard   %s: Delete"], dpad, I("select"), I("remove"),
      I("back"))
  end
  local t = K.Target()
  if t and t.PadButtons then -- (a window with buttons: up and down the list, left and right its buttons)
    local ud = P.Key("panUp") == "PADDUP" and P.Key("panDown") == "PADDDOWN"
      and (P.KeyIcon("PADDUP") or I("panUp")) .. "/" .. (P.KeyIcon("PADDDOWN") or I("panDown"))
      or (I("panUp") .. "/" .. I("panDown"))
    local lr = P.Key("panLeft") == "PADDLEFT" and P.Key("panRight") == "PADDRIGHT"
      and (P.KeyIcon("PADDLEFT") or I("panLeft")) .. "/" .. (P.KeyIcon("PADDRIGHT") or I("panRight"))
      or (I("panLeft") .. "/" .. I("panRight"))
    return string.format(L["%s: Choose   %s: Buttons   %s: Pick   %s: Keyboard   %s: Close"], ud, lr, I("select"),
      I("remove"), I("back"))
  end
  return string.format(L["%s: Choose   %s: Pick   %s: Keyboard   %s: Close"], dpad, I("select"), I("remove"),
    I("back"))
end
function K.Refresh()
  local want = K.Wants()
  local t = want and K.Target() or nil
  if K.open and (not want or (kb and kb.target ~= t)) then
    K.open = false
    if kb then kb:Hide() end
  end
  if K.btn and (not want or K.open or not K.Button()) then K.SetButton(nil) end
  if want and not legend then
    legend = CreateFrame("Frame", nil, t, "BackdropTemplate")
    Look(legend)
    legend.text = legend:CreateFontString(nil, "ARTWORK", "GameFontHighlightSmall")
    legend.text:SetPoint("LEFT", K.LEGEND_PAD, 0)
    legend.text:SetJustifyH("LEFT")
    legend.text:SetWordWrap(false)
    K.legend = legend
  end
  if not legend then return end
  if want then
    if legend.target ~= t then
      legend:SetParent(t)
      legend:ClearAllPoints()
      if t.PadPlaceLegend then t.PadPlaceLegend(legend) -- (a target's own place for it: Options', beside its box)
      else legend:SetPoint("BOTTOMLEFT", t, "TOPLEFT", 0, 2) end -- (over it)
      legend.target = t
    end
    -- (a target's own buttons, where they aren't the map's: Options' fixed ones, PadOptions.lua)
    local text = t.PadLegend and t.PadLegend() or K.LegendText()
    if legend.shown ~= text then
      legend.text:SetText(text)
      legend.shown = text
      legend:SetSize((legend.text:GetStringWidth() or 200) + 2 * K.LEGEND_PAD, 22)
    end
  end
  legend:SetShown(want)
end
