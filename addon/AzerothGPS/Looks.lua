-- The map window's own looks (Options > Window, asked 2026-11-04): a celebration when you arrive (confetti or
-- fireworks over the map), the window frame's tint and its buttons' and X's colors, the route's color (AzerothGPS's
-- blue or a rainbow), and a charm hanging on a string from the logo, swinging as you go. Only the map window: the
-- options and the popups keep the game's own look. Another addon's look (the API's SetFrameLook, SetRouteLook) shows
-- over these while it's set. Display only, and silent.
local _, ns = ...
local L = ns.L or setmetatable({}, { __index = function(_, k) return k end }) -- (the game's language: Locales.lua)

local LK = {}
ns.Looks = LK

local function S() return ns.settings.gps end
local function G() return ns.GPS end

-- A call that gives nil for anything the game hides (secret values) or fails on.
local function Safe(f, ...)
  if type(f) ~= "function" then return nil end
  local ok, a, b, c = pcall(f, ...)
  if not ok or ns.IsSecret(a) or ns.IsSecret(b) or ns.IsSecret(c) then return nil end
  return a, b, c
end

---------------------------------------------------------------------------
-- The window frame and the route
---------------------------------------------------------------------------

-- The frame's tints: `border` over its metal, `title` the title bar's, `text` the title's. "faction": Horde red or
-- Alliance blue by the character's.
LK.TINTS = {
  { key = "faction", name = L["Your faction"], tip = L["Horde red or Alliance blue, by your character's faction."] },
  { key = "gold", name = L["Gold"], border = { 1, 0.82, 0.45 }, title = { 0.16, 0.11, 0.03 }, text = { 1, 0.9, 0.6 } },
  { key = "bronze", name = L["Bronze"], border = { 0.85, 0.58, 0.35 }, title = { 0.13, 0.08, 0.04 }, text = { 1, 0.8, 0.6 } },
  { key = "darkiron", name = L["Dark iron"], border = { 0.42, 0.42, 0.48 }, title = { 0.03, 0.03, 0.04 } },
  { key = "horde", name = L["Horde red"], border = { 1, 0.42, 0.36 }, title = { 0.2, 0.03, 0.02 }, text = { 1, 0.8, 0.7 } },
  { key = "alliance", name = L["Alliance blue"], border = { 0.5, 0.65, 1 }, title = { 0.03, 0.06, 0.18 },
    text = { 0.85, 0.9, 1 } },
  { key = "moonsilver", name = L["Moonsilver"], border = { 0.82, 0.9, 1 }, title = { 0.08, 0.09, 0.13 },
    text = { 0.9, 0.95, 1 } },
  { key = "fel", name = L["Fel green"], border = { 0.55, 1, 0.42 }, title = { 0.03, 0.12, 0.02 }, text = { 0.75, 1, 0.6 } },
}

local function Find(list, key)
  for _, e in ipairs(list) do
    if e.key == key then return e end
  end
end

-- A tint by its key ("faction": the character's faction's), nil for "default" or one not known.
function LK.Tint(key)
  if key == "faction" then
    return Find(LK.TINTS, Safe(UnitFactionGroup, "player") == "Alliance" and "alliance" or "horde")
  end
  return Find(LK.TINTS, key)
end

-- A button color setting's color: nil for the game's own ("default"); "frame" the tint's border (none: the game's own).
function LK.ButtonColor(key)
  local t = LK.Tint(key == "frame" and S().windowTint or key)
  return t and t.border
end

-- The frame's look from the settings (GPSFrame's look record: border, title, text, buttons, close), or nil for the
-- game's own. The X "buttons" takes the buttons' color; "default" while the buttons are colored is white.
function LK.FrameLook()
  local st = S()
  local t = LK.Tint(st.windowTint)
  local buttons = LK.ButtonColor(st.windowButtons)
  local close
  if st.windowClose ~= "buttons" then
    close = LK.ButtonColor(st.windowClose) or (buttons and { 1, 1, 1 }) or nil
  end
  if not (t or buttons or close) then return nil end
  return { border = t and t.border, title = t and t.title, text = t and t.text, buttons = buttons, close = close }
end

-- The route's look from the settings: nil for AzerothGPS's blue, else the rainbow.
function LK.RouteLook()
  if S().routeColor ~= "rainbow" then return nil end
  return { rainbow = true, width = 1, dotted = false }
end

---------------------------------------------------------------------------
-- Pictures drawn pixel for pixel (the charms)
---------------------------------------------------------------------------

LK.ART_GAP = 1 -- art pixels between a picture's frames on its texture
LK.ART_SCALES = 3 -- textures at 1x, 2x and 3x (screen pixels an art pixel)
LK.MEDIA = "Interface\\AddOns\\AzerothGPS\\Media\\Charms\\"

-- Screen pixels per UI unit on a frame at effective scale `effScale`.
function LK.PixelsPerUnit(effScale)
  local _, h = Safe(GetPhysicalScreenSize)
  return (h and h > 0) and h / 768 * (effScale or 1) or 1
end

-- A picture's whole-pixel multiple k on such a frame (1 to 3: about a UI unit an art pixel) and the UI units an art
-- pixel then covers; a smooth one (one texture, `smooth` times its art pixels, the client's own LINEAR filtering):
-- that texture, at the size its art pixels would be.
function LK.ArtScale(art, effScale)
  local ppu = LK.PixelsPerUnit(effScale)
  local k = math.max(1, math.min(LK.ART_SCALES, math.floor(ppu + 0.5)))
  if art.smooth then return art.smooth, k / ppu end
  return k, k / ppu
end

-- Show frame `i` of charm `c` (its `art` and `file`) at scale k on texture `tex`, each art pixel `unit` UI units
-- across (`mirror`: flipped side to side).
function LK.ShowArt(tex, c, i, k, unit, mirror)
  local a = c.art
  local size = a.tex[k]
  local cols = a.cols or a.frames
  local x, y = (i - 1) % cols * (a.w + LK.ART_GAP) * k, math.floor((i - 1) / cols) * (a.h + LK.ART_GAP) * k
  local l, r, t, b = x / size[1], (x + a.w * k) / size[1], y / size[2], (y + a.h * k) / size[2]
  if mirror then l, r = r, l end
  local file = c.file .. "_" .. k .. "x"
  if tex.agpsFile ~= file then
    tex:SetTexture(file)
    tex.agpsFile = file
    if tex.SetSnapToPixelGrid then tex:SetSnapToPixelGrid(not a.smooth) end
    if tex.SetTexelSnappingBias then tex:SetTexelSnappingBias(0) end
  end
  tex:SetTexCoord(l, r, t, b)
  tex:SetSize(a.w * unit, a.h * unit)
end

---------------------------------------------------------------------------
-- The charm
---------------------------------------------------------------------------

-- The legendary weapons, our own small 3D models drawn as pixel art (Media\Charms\charm_<key>_s_<k>x: six frames of a
-- half turn on the string), in the list's order. `art`: the picture's cell in art pixels, its frames (`cols` a row),
-- the point it hangs by (from the cell's top left) and its textures' sizes at each scale.
LK.CHARMS = {
  { key = "ashbringer", name = L["Ashbringer"], tip = L["A broad pale cleaver, a golden sun in its spine."],
    art = { w = 25, h = 79, frames = 6, cols = 3, ax = 12.5, ay = 0, tex = { { 128, 256 }, { 256, 512 }, { 256, 512 } } } },
  { key = "frostmourne", name = L["Frostmourne"], tip = L["A long runed blade under a dark crowned skull."],
    art = { w = 25, h = 82, frames = 6, cols = 3, ax = 12.5, ay = 0, tex = { { 128, 256 }, { 256, 512 }, { 256, 512 } } } },
  { key = "warglaive", name = L["Warglaive of Azzinoth"], tip = L["Two fel crescents round a white-hot gem."],
    art = { w = 27, h = 78, frames = 6, cols = 3, ax = 13.5, ay = 0, tex = { { 128, 256 }, { 256, 512 }, { 256, 512 } } } },
  { key = "thoridal", name = L["Thori'dal, the Stars' Fury"], tip = L["A silver bow round a golden flame."],
    art = { w = 41, h = 81, frames = 6, cols = 1, ax = 20.5, ay = 0, tex = { { 64, 512 }, { 128, 1024 }, { 128, 2048 } } } },
  { key = "gorehowl", name = L["Gorehowl"], tip = L["A great steel axe, saw teeth down its back, a hide-bound head."],
    art = { w = 43, h = 81, frames = 6, cols = 3, ax = 21.5, ay = 0, tex = { { 256, 256 }, { 512, 512 }, { 512, 512 } } } },
  { key = "corruptedash", name = L["Corrupted Ashbringer"], tip = L["Green runes, a green-eyed skull in its spine."],
    art = { w = 25, h = 80, frames = 6, cols = 3, ax = 12.5, ay = 0, tex = { { 128, 256 }, { 256, 512 }, { 256, 512 } } } },
  { key = "quelserrar", name = L["Quel'Serrar"], tip = L["A silver sword with blue runes, a blue gem in its golden guard."],
    art = { w = 23, h = 79, frames = 6, cols = 3, ax = 11.5, ay = 0, tex = { { 128, 256 }, { 256, 512 }, { 256, 512 } } } },
  { key = "queldelar", name = L["Quel'Delar"], tip = L["A long pale blue sword, a blue gem in its golden guard."],
    art = { w = 25, h = 80, frames = 6, cols = 3, ax = 12.5, ay = 0, tex = { { 128, 256 }, { 256, 512 }, { 256, 512 } } } },
}
for _, c in ipairs(LK.CHARMS) do c.file = LK.MEDIA .. "charm_" .. c.key .. "_s" end
-- Charms other addons add (the API's AddCharm), after these: key -> its entry, and their order.
LK.added, LK.addedOrder = {}, {}

-- Every charm offered: ours, then the ones added.
function LK.Charms()
  local out = {}
  for _, c in ipairs(LK.CHARMS) do out[#out + 1] = c end
  for _, key in ipairs(LK.addedOrder) do
    if LK.added[key] then out[#out + 1] = LK.added[key] end
  end
  return out
end

function LK.Charm(key)
  if type(key) ~= "string" or key == "none" then return nil end
  return Find(LK.CHARMS, key) or LK.added[key]
end

-- Another addon's charm (API 19): `def` = { key, name, tip, file (its textures' path without "_<k>x"), art = { w, h,
-- frames, cols, ax, ay, tex = { [k] = { width, height } } (a pixel picture at k = 1 to 3), or smooth = k (one
-- texture, tex[k] only) }, scale (times its art pixels' size, 0.25 to 4; 1 unless given) }. Checked as data; false for one that isn't well made or whose key is ours.
local function Size(t) return type(t) == "table" and tonumber(t[1]) and tonumber(t[2]) and t[1] > 0 and t[2] > 0 end
function LK.AddCharm(owner, def)
  if owner == nil or type(def) ~= "table" or type(def.key) ~= "string" or Find(LK.CHARMS, def.key) then return false end
  local a = def.art
  if type(def.file) ~= "string" or type(a) ~= "table" or type(a.tex) ~= "table" then return false end
  for _, k in ipairs({ "w", "h", "frames" }) do
    if not (tonumber(a[k]) and a[k] > 0) then return false end
  end
  local smooth = tonumber(a.smooth)
  if smooth then
    if not Size(a.tex[smooth]) then return false end
  else
    for k = 1, LK.ART_SCALES do
      if not Size(a.tex[k]) then return false end
    end
  end
  local key = def.key
  if not LK.added[key] then
    LK.addedOrder[#LK.addedOrder + 1] = key
    if LK.charmOptions then LK.charmOptions[#LK.charmOptions + 1] = { value = key } end -- (the options' list, built)
  end
  LK.added[key] = { key = key, name = tostring(def.name or key), tip = type(def.tip) == "string" and def.tip or nil,
    file = def.file, owner = owner, scale = math.max(0.25, math.min(4, tonumber(def.scale) or 1)), art = { w = a.w, h = a.h, frames = a.frames, cols = tonumber(a.cols) or a.frames,
      ax = tonumber(a.ax) or a.w / 2, ay = tonumber(a.ay) or 0, tex = a.tex, smooth = smooth } }
  for _, o in ipairs(LK.charmOptions or {}) do
    if o.value == key then o.text, o.tip = LK.added[key].name, LK.added[key].tip end
  end
  if LK.started then LK.Apply() end
  return true
end

-- How the character moves, for the charm: its speed (yards a second) and how fast it turns (radians a second, positive
-- to the left), read ten times a second. The speed is the game's (GetUnitSpeed) or, when it's hidden (combat) or 0 on
-- a boat, how far the position moved. Unknown reads as still.
local M = { speed = 0, turn = 0, kick = 0, n = 0, acc = 0 }
LK.Motion = M
M.SAMPLE = 0.1 -- seconds between reads
M.MOVING = 0.5 -- yards a second: slower is standing still
M.GAP = 1 -- seconds without a read: the next starts afresh, without a jolt
M.MAX_SPEED = 80 -- (faster than any flight: a teleport or a loading screen)
M.SMOOTH = 0.5 -- how much of a new read goes in

local function Wrap(a)
  while a > math.pi do a = a - 2 * math.pi end
  while a <= -math.pi do a = a + 2 * math.pi end
  return a
end

function M.Sample(now)
  local x, y, cont = Safe(ns.Geo.RealPlayerWorld)
  local facing = Safe(GetPlayerFacing)
  local speed, turn = Safe(GetUnitSpeed, "player") or 0, 0
  local last = M.last
  local gap = last ~= nil and now - last.t > M.GAP
  if gap then last = nil end
  if last then
    local dt = now - last.t
    if dt > 0 then
      if x and last.x and cont == last.cont then
        local moved = math.sqrt((x - last.x) ^ 2 + (y - last.y) ^ 2) / dt
        if moved <= M.MAX_SPEED and moved > speed then speed = moved end
      end
      if facing and last.facing then turn = Wrap(facing - last.facing) / dt end
    end
  end
  local before = M.speed
  if gap then M.speed, M.turn, before = speed, 0, speed end
  M.speed = M.speed + (speed - M.speed) * M.SMOOTH
  if M.speed < 0.05 then M.speed = 0 end
  M.turn = M.turn + (turn - M.turn) * M.SMOOTH
  if math.abs(M.turn) < 0.01 then M.turn = 0 end
  M.kick = M.speed - before -- (setting off or stopping: a jolt)
  M.moving = M.speed >= M.MOVING
  M.n = M.n + 1
  M.last = { x = x, y = y, cont = cont, facing = facing, t = now }
end

-- The charm on its string: a pendulum. Turning swings it out of the turn, the road jostles it while the character
-- moves, setting off and stopping jolt it, and it settles when all is still; it twists on its string too (its frames
-- a half turn, mirrored for the other half) and untwists to face you. Swinging off: straight and still, facing you.
local C = { angle = 0, vel = 0, pose = 1, spin = 0, spinVel = 0, mirror = false }
LK.CharmState = C
C.PERIOD = 1.1 -- seconds a swing takes, there and back
C.DAMP = 2.2 -- how fast a swing dies down
C.TURN = 0.45 -- the turn's push: per yard a second of speed, per radian a second of turning
C.TURN_STILL = 2 -- (turning on the spot pushes as if moving this fast)
C.MAX_PUSH = 22
C.BUMPS = 1.2 -- bumps a second at a run, more when faster
C.BUMP = 0.5 -- radians a second, a bump at a run
C.KICK = 0.12 -- radians a second, per yard a second of setting off or stopping
C.MAX_ANGLE = 1.3
C.STEP = 1 / 60 -- worked out in steps no longer than this
C.REST = 0.004 -- radians: a swing this small, slowing, is over
C.TWIST = 1.2 -- the string untwisting it
C.SPIN_DAMP = 1.0
C.SWING_TWIST = 3.5 -- the swing twisting it
C.TURN_TWIST = 0.9 -- the character's turning twisting it
C.SPIN_BUMP = 2.5 -- a bump's twist at a run
local W0SQ = (2 * math.pi / C.PERIOD) ^ 2
-- Where the string hangs from, from the map window's top left (UI units, +y up): behind the logo's lower left (its
-- plate drawn over it); without the window frame, the map's top-left corner.
C.HANG_FRAMED = { 4, -6 }
C.HANG_PLAIN = { 6, 0 }
C.STRING_COLOR = { 0.93, 0.91, 0.86, 1 }
C.STRING = 10 -- its length (UI units)

LK.Random = math.random -- (the tests make it steady: Lua 5.1's math.random is the C library's rand, another
                        -- sequence on Windows than on Linux)
local function Rand() return LK.Random() end

local function Framed()
  local g = G()
  return S().windowFrame ~= false and g and g.chrome ~= nil and g.chrome:IsShown() and true or false
end

function C.Place()
  local a = C.def.art
  local u = C.unit
  local s, c = math.sin(C.angle), math.cos(C.angle)
  local hx, hy = C.hang[1], C.hang[2]
  local ex, ey = hx + C.STRING * s, hy - C.STRING * c -- (the string's end: the charm's loop)
  local dx, dy = (a.w / 2 - a.ax) * u, -(a.h / 2 - a.ay) * u -- (its middle from its loop, turned with it)
  C.tex:ClearAllPoints()
  C.tex:SetPoint("CENTER", C.frame, "TOPLEFT", ex + dx * c - dy * s, ey + dx * s + dy * c)
  C.tex:SetRotation(C.angle)
  C.line:SetStartPoint("TOPLEFT", C.frame, hx, hy)
  C.line:SetEndPoint("TOPLEFT", C.frame, ex, ey)
  C.drawn = C.angle
end

-- The frame for a twist of `spin` radians: its pose (1 to n, a half turn) and whether it's mirrored (the other half).
function C.SpinFrame(spin, n)
  local a = spin % (2 * math.pi)
  local mirror = a >= math.pi
  local i = math.floor((a % math.pi) / (math.pi / n) + 0.5)
  if i >= n then i, mirror = 0, not mirror end
  return i + 1, mirror
end

function C.Push()
  if M.turn == 0 then return 0 end
  local p = C.TURN * math.max(M.speed, C.TURN_STILL) * M.turn
  return math.max(-C.MAX_PUSH, math.min(C.MAX_PUSH, p))
end

function C.Twist(elapsed, pace)
  if M.moving and Rand() < elapsed * C.BUMPS * pace then
    C.spinVel = C.spinVel + (Rand() * 2 - 1) * C.SPIN_BUMP * pace
  end
  local t = math.min(elapsed, 0.25)
  while t > 0 do
    local dt = math.min(t, C.STEP)
    local acc = -C.TWIST * math.sin(C.spin) - C.SPIN_DAMP * C.spinVel + C.SWING_TWIST * C.vel + C.TURN_TWIST * M.turn
    C.spinVel = C.spinVel + acc * dt
    C.spin = (C.spin + C.spinVel * dt) % (2 * math.pi)
    t = t - dt
  end
  if not M.moving and M.turn == 0 and C.vel == 0 and math.abs(C.spinVel) < 0.05 and math.abs(math.sin(C.spin)) < 0.03 then
    C.spin, C.spinVel = 0, 0
  end
  local pose, mirror = C.SpinFrame(C.spin, C.def.art.frames)
  if pose ~= C.pose or mirror ~= C.mirror then
    C.pose, C.mirror = pose, mirror
    LK.ShowArt(C.tex, C.def, C.pose, C.k, C.unit, C.mirror)
  end
end

-- Every frame while the charm shows: the character's motion read, the swing worked out.
function C.Update(elapsed)
  M.acc = M.acc + elapsed
  if M.acc >= M.SAMPLE then
    M.acc = 0
    M.Sample(GetTime())
  end
  if not (C.def and S().charmSwing ~= false) then return end
  local pace = math.min(M.speed / 7, 2)
  if M.n ~= C.seen then
    C.seen = M.n
    if math.abs(M.kick) > 0.3 then C.vel = C.vel + C.KICK * M.kick * (Rand() < 0.5 and -1 or 1) end
  end
  if not M.moving and M.turn == 0 and C.angle == 0 and C.vel == 0 and C.spin == 0 and C.spinVel == 0 then
    return -- (hanging still: nothing to work out or draw)
  end
  if M.moving and Rand() < elapsed * C.BUMPS * pace then C.vel = C.vel + (Rand() * 2 - 1) * C.BUMP * pace end
  local push = C.Push()
  local t = math.min(elapsed, 0.25)
  while t > 0 do
    local dt = math.min(t, C.STEP)
    local acc = -W0SQ * math.sin(C.angle) - C.DAMP * C.vel + push * math.cos(C.angle)
    C.vel = C.vel + acc * dt
    C.angle = C.angle + C.vel * dt
    t = t - dt
  end
  if math.abs(C.angle) > C.MAX_ANGLE then
    C.angle = C.angle > 0 and C.MAX_ANGLE or -C.MAX_ANGLE
    C.vel = 0
  end
  if push == 0 and not M.moving and math.abs(C.angle) < C.REST and math.abs(C.vel) < C.REST * 4 then
    C.angle, C.vel = 0, 0
  end
  C.Twist(elapsed, pace)
  if C.angle ~= C.drawn then C.Place() end
end

-- Show the charm the settings pick, or hide it.
function C.Apply()
  if not C.frame then return end
  C.def = LK.Charm(S().charm)
  if not C.def then
    C.frame:Hide()
    return
  end
  -- (the map in the game's world map window meanwhile: the charm stays on the minimap square, where the logo is; with
  -- no square, none: asked 2026-11-10, "the charm is on the in game map, should stay on the minimap". The same while
  -- the map's grown out of the square kept as it is, GPSFrame's G.SquareKeptOut, asked 2026-11-15)
  local on
  do
    local g = G()
    local host = g and g.WorldMapHosted and g.WorldMapHosted()
    local kept = g and g.SquareKeptOut and g.SquareKeptOut()
    on = (host or kept) and g.mmState and g.mmState.on and g.mmAnchor or nil
    if host and not on then
      C.frame:Hide()
      return
    end
    local parent = on and UIParent or C.map
    if C.frame:GetParent() ~= parent then
      C.frame:SetParent(parent)
      if on then C.frame:SetFrameStrata("MEDIUM") end
    end
    C.frame:ClearAllPoints()
    C.frame:SetPoint("TOPLEFT", on or C.map, "TOPLEFT", 0, 0)
  end
  C.frame:Show()
  -- over the window frame's border, under the logo's plate: the string comes out from behind the logo
  local plate = not on and Framed() and G().mapButtons and G().mapButtons.logo
  C.frame:SetFrameLevel(plate and plate.GetFrameLevel and plate:GetFrameLevel() - 1 or C.map:GetFrameLevel() + 14)
  C.k, C.unit = LK.ArtScale(C.def.art, C.frame:GetEffectiveScale())
  C.unit = C.unit * (C.def.scale or 1)
  C.hang = (not on and Framed()) and C.HANG_FRAMED or C.HANG_PLAIN
  if S().charmSwing == false then C.angle, C.vel, C.spin, C.spinVel = 0, 0, 0, 0 end
  C.pose, C.mirror = C.SpinFrame(C.spin, C.def.art.frames)
  C.line:SetThickness(math.max(1, C.unit))
  LK.ShowArt(C.tex, C.def, C.pose, C.k, C.unit, C.mirror)
  C.Place()
end

function LK.ApplyCharm() C.Apply() end

---------------------------------------------------------------------------
-- Arriving: confetti or fireworks over the map at the trip's last stop
---------------------------------------------------------------------------

local E = { parts = {}, used = 0 }
LK.Effects = E
E.CONFETTI = { n = 70, life = 3.2, fall = 60, colors = { { 1, 0.25, 0.3 }, { 1, 0.85, 0.2 }, { 0.3, 0.85, 1 },
  { 0.4, 1, 0.4 }, { 1, 0.5, 0.95 }, { 1, 1, 1 } } }
E.FIREWORKS = { bursts = 4, every = 0.35, n = 28, life = 1.3, speed = { 45, 90 }, fall = 40,
  colors = { { 1, 0.35, 0.3 }, { 1, 0.85, 0.3 }, { 0.4, 0.8, 1 }, { 0.6, 1, 0.45 }, { 1, 0.55, 1 } } }
E.FADE = 0.6 -- seconds a part fades out at the end of its life
LK.EFFECTS = { { key = "confetti", name = L["Confetti"] }, { key = "fireworks", name = L["Fireworks"] } }

local function Part()
  E.used = E.used + 1
  local p = E.parts[E.used]
  if not p then
    p = { tex = E.frame:CreateTexture(nil, "OVERLAY") }
    E.parts[E.used] = p
  end
  p.tex:Show()
  return p
end

local function Pick(list) return list[math.floor(Rand() * #list) + 1] end

-- Scraps of color from above the map's top, fluttering down and spinning.
function E.Confetti(w, h)
  local K = E.CONFETTI
  for _ = 1, K.n do
    local p = Part()
    local c = Pick(K.colors)
    p.tex:SetColorTexture(c[1], c[2], c[3], 1)
    p.tex:SetSize(2 + 3 * Rand(), 2 + 2 * Rand())
    p.x, p.y = w * Rand(), h + 30 * Rand()
    p.vx, p.vy = (Rand() - 0.5) * 40, -(15 + 35 * Rand())
    p.fall, p.flutter, p.phase = K.fall * 0.5, 14, 6.28 * Rand()
    p.spin, p.turn = (Rand() - 0.5) * 12, 6.28 * Rand()
    p.age, p.life, p.delay = 0, K.life * (0.75 + 0.25 * Rand()), 0
  end
end

-- Bursts of sparks across the map's upper half, one after another.
function E.Fireworks(w, h)
  local F = E.FIREWORKS
  for b = 1, F.bursts do
    local cx, cy = w * (0.2 + 0.6 * Rand()), h * (0.5 + 0.35 * Rand())
    local c = Pick(F.colors)
    for i = 1, F.n do
      local p = Part()
      local white = i % 5 == 0
      p.tex:SetColorTexture(white and 1 or c[1], white and 1 or c[2], white and 1 or c[3], 1)
      p.tex:SetSize(3, 3)
      local angle, speed = 6.2832 * i / F.n, F.speed[1] + (F.speed[2] - F.speed[1]) * Rand()
      p.x, p.y, p.vx, p.vy = cx, cy, math.cos(angle) * speed, math.sin(angle) * speed
      p.fall, p.flutter, p.phase, p.spin, p.turn = F.fall, 0, 0, 0, 0
      p.age, p.life, p.delay = 0, F.life, (b - 1) * F.every
    end
  end
end

-- Start an effect ("confetti", "fireworks") over the map; false when there's none or nowhere to show it.
function LK.Play(effect)
  local maker = ({ confetti = E.Confetti, fireworks = E.Fireworks })[effect]
  if not (maker and E.frame) then return false end
  -- (measured on the canvas it covers: the effect frame is hidden until now, and in the game a hidden frame sized only
  -- by its anchors reads 0 x 0, so nothing ever played)
  local host = E.frame:GetParent() or E.frame
  local w, h = host:GetWidth() or 0, host:GetHeight() or 0
  if w <= 0 or h <= 0 then return false end
  maker(w, h)
  E.frame:Show()
  return true
end

-- A stop reached (Nav's arrival hooks): the effect picked at the trip's last stop.
function LK.OnArrive(info)
  if type(info) ~= "table" or not info.last then return end
  local e = S().arrivalEffect
  if e and e ~= "none" then LK.Play(e) end
end

-- Every frame while something's showing: each part moved, faded at its end, put away when done.
function E.Update(elapsed)
  local i = 1
  while i <= E.used do
    local p = E.parts[i]
    if p.delay > 0 then
      p.delay = p.delay - elapsed
      p.tex:SetAlpha(0)
      i = i + 1
    else
      p.age = p.age + elapsed
      if p.age >= p.life then
        p.tex:Hide()
        E.parts[i], E.parts[E.used] = E.parts[E.used], p -- (done: the last part in use takes its place)
        E.used = E.used - 1
      else
        p.vy = p.vy - p.fall * elapsed
        p.x = p.x + (p.vx + math.sin(p.age * 6 + p.phase) * p.flutter) * elapsed
        p.y = p.y + p.vy * elapsed
        p.turn = p.turn + p.spin * elapsed
        if p.spin ~= 0 then p.tex:SetRotation(p.turn) end
        p.tex:ClearAllPoints()
        p.tex:SetPoint("CENTER", E.frame, "BOTTOMLEFT", p.x, p.y)
        p.tex:SetAlpha(math.min(1, (p.life - p.age) / E.FADE))
        i = i + 1
      end
    end
  end
  if E.used == 0 then E.frame:Hide() end
end

---------------------------------------------------------------------------
-- Start and settings
---------------------------------------------------------------------------

-- The settings as the map shows them: the frame's and the route's looks (GPSFrame shows another addon's over them),
-- the charm.
function LK.Apply()
  local g = G()
  if not g then return end
  g.ownFrameLook, g.ownRouteLook = LK.FrameLook(), LK.RouteLook()
  if g.ApplyFrameLook then g.ApplyFrameLook() end
  if g.ApplyButtonLooks then g.ApplyButtonLooks() end
  if g.Redraw then g.Redraw() end
  C.Apply()
end

function LK.Init()
  local map = _G.AzerothGPSFrame
  local canvas = G() and G().Canvas and G().Canvas()
  if LK.started or not map or not canvas then return end
  LK.started = true
  local f = CreateFrame("Frame", nil, canvas) -- (in the map's clipped area, over the route and its icons)
  f:SetAllPoints(canvas)
  f:SetFrameLevel(canvas:GetFrameLevel() + 20)
  f:EnableMouse(false)
  f:Hide()
  f:SetScript("OnUpdate", function(_, elapsed) E.Update(elapsed) end)
  if ns.TimeScript then ns.TimeScript(f, "OnUpdate", "window looks") end
  E.frame = f
  local cf = CreateFrame("Frame", nil, map) -- (a child of the map: nothing read or drawn while it's hidden)
  cf:SetSize(1, 1)
  cf:SetPoint("TOPLEFT", map, "TOPLEFT", 0, 0)
  cf:EnableMouse(false)
  cf:Hide()
  C.map, C.frame = map, cf
  C.line = cf:CreateLine(nil, "ARTWORK", nil, -1)
  C.line:SetColorTexture(unpack(C.STRING_COLOR))
  C.tex = cf:CreateTexture(nil, "ARTWORK")
  cf:SetScript("OnUpdate", function(_, elapsed) C.Update(elapsed) end)
  if ns.TimeScript then ns.TimeScript(cf, "OnUpdate", "window looks") end
  ns.Nav.arriveHooks.AzerothGPS = LK.OnArrive
  LK.Apply()
end
