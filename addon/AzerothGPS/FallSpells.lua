-- Class spells for big drops (1.4.0, Kooki3z 2026-11-22: "if a class has like levitate or slow fall and they have the
-- necessary reagents on them and they could survive a fall, then use that by default. Add an option to turn it off
-- called 'Use class spells'"; option `useClassSpells`, Options > Routing, on by default). While one is ready the
-- routes' safe drop (Nav.SafeDrop) is the drop the spell makes safe, so they may go off ledges and cliffs bigger than
-- the player's own safe drop, always one way down; the step before such a drop says "Cast Slow Fall, then jump down"
-- (Turns.NowText, FS.DropText) and the use button beside the directions casts it (the player's own click: GPSFrame's
-- secure use button, FS.CastNow). AzerothGPS never casts anything by itself.
--
-- The spells, from this client's own data (Spell/SpellName, SpellReagents, SpellCooldowns, SpellMisc + SpellDuration,
-- SpellEffect's auras, SpellShapeshift; read 2026-11-22):
--   Slow Fall (130, mage): feather fall (aura 105), a Light Feather (17056) each cast, no cooldown. Its duration row (9)
--     isn't in the client's SpellDuration table: classic's 30 s.
--   Levitate (1706, priest): feather fall, hover and water walking, a Light Feather each cast, 120 s (duration row 4);
--     not in Shadowform (SpellShapeshift's exclude mask: form 28).
--   Gliding on Air (1271049 and 1271020, the Skyborne race's own: no reagent, 3 min cooldown; 1271020 is feather fall
--     for 10 s, duration row 1, and triggers 1271019): either id the character has.
--   Walk on Air (1259416, a racial, Kooki3z 2026-11-23 on a level 25 character: "Glide downward through the air for
--     10 sec while controlling your direction of travel", instant): feather fall (aura 105) for 10 s (duration row 1),
--     triggers 1259417, no reagent; its cooldown 2 min in game (the tooltip; this client's SpellCooldowns row says
--     90 s). The client's other "Walk on Air" (1308663: 60 s, no cooldown, no category) isn't the racial.
-- Not taken (found, not clean): the client's other "Slow Fall" (1317675) and "Levitate" (1270422) rows are passive
-- auras with no duration (scripts, not spells to cast); Noggenfogger's 16593 (the elixir's effect is random, its item
-- not tied to it); "Parachute" (1251394), with no duration and no item using it.
--
-- Items (1.4.0, Kooki3z 2026-11-23: "using spell or item (like parachutes)"), from the client's ItemEffect (an on-use
-- trigger) and ItemXItemEffect, their spells' feather fall aura (105) and durations as above, and Item's class and
-- slot (read 2026-11-23; their names are the game's, GetItemInfo, the spell's where it isn't cached):
--   items 10518, 213308 and 260810 (cloaks), 9404 (a shield): Slow Fall 12438, feather fall 10 s, a 30 min cooldown;
--     worn (IsEquippedItem: a "Use:" on gear needs it on).
--   item 10684 (a consumable): the same Slow Fall 12438, 10 s, from the bags.
--   items 21171 and 274616 (class 15, from the bags, a 5 s cooldown): Lightheaded 25851 (30 s) and 1307411 (45 s).
--   item 275729 (a two-handed weapon, worn): Propellerstorm 1297762, 15 s, a 15 min cooldown.
--   (Equipped passives with Safe Fall, aura 144, only lessen the damage: not a slower fall, not taken.)
--
-- Reach (Kooki3z 2026-11-23: "distance of the fall should be allowed up to the spell. Like the spell for skybourne
-- only lasts a few seconds while you can slow fall for 30s which would go much further"): each its own, FS.RowDrop, the
-- buff's seconds less CAST_MARGIN at FALL_YPS (the game's safe-fall terminal speed, 7 yd a second; a plain fall's is
-- about 60): Gliding on Air and the 10 s items 56 yd, Propellerstorm 91, Slow Fall and the 30 s mug 196, the 45 s one
-- 301, Levitate's 120 s capped at DROP_CAP (400). Across, the player runs on while slowed (FS.RowGlide, RUN_YPS a second
-- of the buff: 70 yd for Gliding on Air, 210 for Slow Fall); the routes take only the drops (no glide links yet).
--
-- Timing (Kooki3z 2026-11-22): the button shows only when casting now still has the buff up when the drop ends: the
-- way to the ledge at the player's speed (Nav.Speeds), the fall at FALL_YPS, and CAST_MARGIN seconds more within the
-- spell's duration; before that the step says "Cast Slow Fall at the ledge (in 40 yd)" and the button is hidden (a
-- grayed secure button only invites a wasted click). With the buff already up the step is a plain "Jump down here";
-- run out before the drop, the button shows again. In combat it's hidden (the secure button's rule).
--
-- Spell jumping (Kooki3z 2026-11-23, "with spell jumping really any ledge jump is possible no matter the distance
-- down"): option `expertJumper` ("Expert jumper", under "Use class spells", off): with a fall spell or item ready, any
-- drop is taken (RowDrop is EXPERT_DROP, not the buff's reach): the player jumps, falls at the game's own speed, and
-- casts just before landing (FS.FallCue: "Cast Slow Fall now!", the use button only then; the player's height isn't
-- given in this client, so the time since the fall began, FS.FallTime, says when). EXPERT_DROP is no game limit (feather
-- fall caught at any speed): a finite number keeps the grids' cache keys and the cliffs' sums plain; no ledge in the
-- data comes near it. A drop within the buff's own reach from the top (RowReach) is cast for at the ledge as before.
--
-- Each jump on the trip needs its own cast (Nav.CheckSpellJumps, FS.Budget): the jumps in order, each at the time the
-- player gets there, each taking a source ready by then with its reach: its own cooldown (`cd`), a shared item one
-- (`cat`, `catCd`), its uses (the Light Feathers in the bags, a consumed item's count, an item's charges). From the
-- client's SpellCooldowns and ItemEffect (2026-11-23): Slow Fall and Levitate no cooldown (the global one), a Light
-- Feather each; Gliding on Air 180 s; the parachute cloaks and the shield 30 min, sharing category 68002 (30 min) with
-- Propellerstorm (15 min, the category 15 min after it); item 213308 30 min of its own; 260810 three charges; 10684
-- used up; Lightheaded 60 s (its spell's category; the items' own 5 s). Mana isn't looked at (the costs are small, and
-- UnitPower is hidden from addons in places). A source on a cooldown ending within WAIT_MAX counts as ready: the trip
-- planner weighs waiting for it against the way round. A jump no source can take in time is walked round (or waited for,
-- whichever is faster: Nav.CheckSpellJumps).
--
-- What's ready is looked at again on the bags, the spells, a level, the cooldowns, the auras and combat (and every
-- TICK_SECONDS for a cooldown running out): a change (the last feather used, the racial on its cooldown, the option)
-- works the route out again (Nav.OptionsChanged), so a big drop is never kept without the spell. A buff up counts as
-- ready (the last feather spent on the cast itself doesn't drop the route under the player).
local _, ns = ...
local L = ns.L or setmetatable({}, { __index = function(_, k) return k end }) -- (the game's language: Locales.lua)
local Format = ns.Format or string.format

local FS = {}
ns.FallSpells = FS

FS.LIGHT_FEATHER = 17056
-- { ids (the first known is cast), its name in English (the game's own, ns.SpellName, when it has it), reagent, the
-- buff's seconds, its auras on the player, a form it can't be cast in, use: the step says "Use" (a racial) }
-- (an item's row: `item`, used from the bags or worn (`worn`); `name` its spell's in English, the game's own item name
-- shown when it has it, FS.Name)
FS.SPELLS = {
  { ids = { 130 }, name = "Slow Fall", reagent = FS.LIGHT_FEATHER, duration = 30, auras = { 130 } },
  { ids = { 1706 }, name = "Levitate", reagent = FS.LIGHT_FEATHER, duration = 120, auras = { 1706 }, noForm = 28 },
  { ids = { 1271049, 1271020 }, name = "Gliding on Air", duration = 10, auras = { 1271020, 1271019, 1271049 },
    use = true, cd = 180, endsOnLanding = true },
  { ids = { 1259416 }, name = "Walk on Air", duration = 10, auras = { 1259416, 1259417 }, use = true, cd = 120,
    endsOnLanding = true },
  { item = 10518, worn = true, name = "Slow Fall", duration = 10, auras = { 12438 }, use = true, cd = 1800,
    cat = 68002, catCd = 1800, endsOnLanding = true },
  { item = 213308, worn = true, name = "Slow Fall", duration = 10, auras = { 12438 }, use = true, cd = 1800,
    endsOnLanding = true },
  { item = 260810, worn = true, name = "Slow Fall", duration = 10, auras = { 12438 }, use = true, cd = 1800,
    cat = 68002, catCd = 1800, charges = 3, endsOnLanding = true },
  { item = 9404, worn = true, name = "Slow Fall", duration = 10, auras = { 12438 }, use = true, cd = 1800,
    cat = 68002, catCd = 1800, endsOnLanding = true },
  { item = 10684, name = "Slow Fall", duration = 10, auras = { 12438 }, use = true, consumed = true },
  { item = 21171, name = "Lightheaded", duration = 30, auras = { 25851 }, use = true, cd = 60 },
  { item = 274616, name = "Lightheaded", duration = 45, auras = { 1307411 }, use = true, cd = 60 },
  { item = 275729, worn = true, name = "Propellerstorm", duration = 15, auras = { 1297762 }, use = true, cd = 900,
    cat = 68002, catCd = 900, endsOnLanding = true },
}
-- A row's key (Nav.PickFallSpell's): its English name, an item's "item:<id>".
function FS.RowKey(row)
  return row.item and ("item:" .. row.item) or row.name
end
FS.FALL_YPS = 7 -- yards a second down under a slow fall (the game's safe-fall terminal speed)
FS.CAST_MARGIN = 2 -- seconds: the cast, the step off and the landing within the buff
FS.DROP_CAP = 400 -- yards: the most any spell's drop is taken as safe for
FS.EXPERT_DROP = 1000 -- yards: spell jumping's (option expertJumper) drop, any ledge in the data
FS.WAIT_MAX = 60 -- seconds: a source this near the end of its cooldown counts as ready (the planner weighs the wait)
-- (the fall: the game's gravity and a plain fall's terminal speed; the cue when CUE_SHARE of the buff's reach is left)
FS.GRAVITY, FS.TERMINAL_YPS, FS.CUE_SHARE = 19.2911, 60.148, 0.85
FS.TICK_SECONDS = 1

local function S() return ns.settings and ns.settings.gps end
local function Secret(v) return ns.IsSecret ~= nil and ns.IsSecret(v) end

-- The tutorial's spell-jump demo (Tutorial.lua's T.JumpDemoStart; Kooki3z 2026-11-25): while FS.demo is set, the
-- character is taken as a mage with Slow Fall known and FS.demo.feathers Light Feathers in the bags, nothing else
-- ready, the option on and Expert jumper off, whatever the real character has. In memory only, never read from or
-- written to the game: FS.demo = { row (FS.SPELLS' Slow Fall), feathers, castAt (the demo button clicked: the buff
-- "up" from then) }. The use button's row carries `demo`, so GPSFrame shows its insecure look-alike (G.DemoUseButton)
-- in the secure button's place: nothing is ever cast.
FS.demo = nil
FS.DEMO_SPELL = 130
function FS.DemoOn() return FS.demo ~= nil end

local function Known(id)
  if FS.demo then return id == FS.DEMO_SPELL end
  local f = IsPlayerSpell or IsSpellKnown
  if not f then return false end
  local ok, v = pcall(f, id)
  return ok and v == true
end
local function ItemCount(item)
  if FS.demo then return item == FS.LIGHT_FEATHER and (FS.demo.feathers or 0) or 0 end
  local get = (C_Item and C_Item.GetItemCount) or GetItemCount
  if not get then return 0 end
  local ok, n = pcall(get, item)
  return ok and type(n) == "number" and not Secret(n) and n or 0
end
-- Seconds left on a spell's cooldown (the global cooldown's counts as ready; hidden: ready).
local function CooldownLeft(id)
  if FS.demo then return 0 end
  local get = (C_Spell and C_Spell.GetSpellCooldown) or GetSpellCooldown
  if not get then return 0 end
  local ok, a, b = pcall(get, id)
  if not ok then return 0 end
  if type(a) == "table" then a, b = a.startTime, a.duration end
  if Secret(a) or Secret(b) or not a or a == 0 or (b or 0) <= 1.5 then return 0 end
  return math.max(0, a + b - GetTime())
end
FS.CooldownLeft = CooldownLeft
-- Seconds left on one of the row's buffs on the player (nil: none up; math.huge where it doesn't say).
local function BuffLeft(row)
  local demo = FS.demo
  if demo then -- (the demo's Slow Fall "cast" by its button: up for its duration from then)
    if row ~= demo.row or not demo.castAt then return nil end
    local left = row.duration - (GetTime() - demo.castAt)
    return left > 0 and left or nil
  end
  for _, id in ipairs(row.auras) do
    local ok, left = pcall(function()
      if C_UnitAuras and C_UnitAuras.GetPlayerAuraBySpellID then
        local a = C_UnitAuras.GetPlayerAuraBySpellID(id)
        if a then
          local e = a.expirationTime
          if Secret(e) or not e or e == 0 then return math.huge end
          return math.max(0, e - GetTime())
        end
      end
      if UnitBuff then
        for i = 1, 40 do
          local name, _, _, _, _, e, _, _, _, sid = UnitBuff("player", i)
          if not name then break end
          if sid == id then return (Secret(e) or not e or e == 0) and math.huge or math.max(0, e - GetTime()) end
        end
      end
      return nil
    end)
    if ok and left and left > 0 then return left end
  end
  return nil
end
FS.BuffLeft = BuffLeft

-- Seconds left on row's cooldown (an item's, its own or its category's as the game says; 0: ready).
function FS.RowCooldown(row)
  if row.item then
    local T = ns.Teleports
    local left = T and T.CooldownLeft and T.CooldownLeft({ item = row.item }) or 0
    return left > 1.5 and left or 0
  end
  local id = FS.KnownId(row)
  return id and CooldownLeft(id) or 0
end
-- The casts row has left (its reagent's count, a used-up item's, an item's charges; math.huge: no limit).
function FS.UsesLeft(row)
  if row.reagent then return ItemCount(row.reagent) end
  if row.consumed then return ItemCount(row.item) end
  if row.charges then
    local get = (C_Item and C_Item.GetItemCount) or GetItemCount
    local ok, n = pcall(get or error, row.item, false, true)
    n = ok and type(n) == "number" and not Secret(n) and n or 0
    return n > 0 and n or (row.worn and 0 or n)
  end
  return math.huge
end
-- The id of row's spell the character has, or nil.
function FS.KnownId(row)
  for _, id in ipairs(row.ids) do
    if Known(id) then return id end
  end
  return nil
end
local function Worn(item)
  if FS.demo then return false end
  local f = (C_Item and C_Item.IsEquippedItem) or IsEquippedItem
  if not f then return false end
  local ok, v = pcall(f, item)
  return ok and v == true
end
-- (an item's row: in the bags, or worn, and off its cooldown; or its buff up)
local function ItemReady(row)
  local up = BuffLeft(row)
  if up then return row.item, up end
  if row.worn then
    if not Worn(row.item) then return nil end
  elseif ItemCount(row.item) < 1 then
    return nil
  end
  if FS.RowCooldown(row) > FS.WAIT_MAX then return nil end
  return row.item
end
-- Whether row's spell can be cast now (known, its reagent in the bags, off its cooldown, not in a form it can't be cast
-- in); or its buff is up. The id (an item's row: the item's), and the buff's seconds left when it's up.
function FS.Ready(row)
  if row.item then return ItemReady(row) end
  local id = FS.KnownId(row)
  if not id then return nil end
  local up = BuffLeft(row)
  if up then return id, up end
  if row.reagent and ItemCount(row.reagent) < 1 then return nil end
  if CooldownLeft(id) > FS.WAIT_MAX then return nil end
  if row.noForm and GetShapeshiftFormID then
    local ok, form = pcall(GetShapeshiftFormID)
    if ok and form == row.noForm then return nil end
  end
  return id
end

-- The drop row's spell makes safe cast at the top: the buff's time less the margin, falling at FALL_YPS.
function FS.RowReach(row)
  return math.min(FS.DROP_CAP, math.max(0, row.duration - FS.CAST_MARGIN) * FS.FALL_YPS)
end
-- Spell jumping with no height limit (option expertJumper, under useClassSpells).
function FS.Expert()
  if FS.demo then return false end
  local st = S()
  return st ~= nil and st.useClassSpells ~= false and st.expertJumper == true
end
-- The drop row's spell makes safe: its reach; any (EXPERT_DROP) for an expert jumper, cast just before landing.
function FS.RowDrop(row)
  if FS.Expert() then return FS.EXPERT_DROP end
  return FS.RowReach(row)
end
-- Seconds a plain fall of `d` yards takes from rest (the game's gravity up to its terminal speed).
function FS.FallTime(d)
  d = math.max(0, d or 0)
  local tt = FS.TERMINAL_YPS / FS.GRAVITY
  local dt = 0.5 * FS.GRAVITY * tt * tt
  if d <= dt then return math.sqrt(2 * d / FS.GRAVITY) end
  return tt + (d - dt) / FS.TERMINAL_YPS
end
-- How far across the player can glide under it, running on while slowed (RUN_YPS a second of the buff).
FS.RUN_YPS = 7
function FS.RowGlide(row)
  return row.duration * FS.RUN_YPS
end

-- The fall spells ready now (the option on): each { row, id, drop, up (the buff's seconds left, when it's up) }, in
-- FS.SPELLS' order.
function FS.ReadyRows()
  local st = S()
  local out = {}
  if st and st.useClassSpells == false and not FS.demo then return out end
  for _, row in ipairs(FS.SPELLS) do
    local id, up = FS.Ready(row)
    if id then out[#out + 1] = { row = row, id = id, drop = FS.RowDrop(row), up = up } end
  end
  return out
end
-- The spell to use for big drops now: { row, id, drop, up }, or nil (none ready, or the option off). The one the trip
-- picked on a jump's right-click (Nav.PickFallSpell, by its row's name) while it's ready; else the one making the
-- biggest drop safe. Cached; FS.Refresh looks again.
local current, looked
function FS.Look()
  local N = ns.Nav
  if N and N.spellJumpsOff then return nil end -- (the trip is faster without: Nav.CheckSpellJumps)
  local pick = N and N.fallPick
  local best
  for _, c in ipairs(FS.ReadyRows()) do
    if pick and FS.RowKey(c.row) == pick then return c end
    if not best or c.drop > best.drop then best = c end
  end
  return best
end
function FS.Current()
  if not looked then
    current, looked = FS.Look(), true
  end
  return current
end
-- Kooki3z's rule (2026-11-23) for steep slopes: a lasting buff with no cooldown (Slow Fall, Levitate, the potions')
-- keeps going when the player touches the slope and slides, so a steep descent its time covers is survivable; a glide
-- or parachute that ends on landing (`endsOnLanding`: Walk on Air, Gliding on Air, the cooldown parachutes) ends at the
-- face, the rest a plain slide or fall. Those count only for a clean drop, the glide clearing the face to the bottom
-- (WorldGrid's FAR_DROP_CLEAN_SLOPE); on a steep slope no more than the Safe drop.
function FS.EndsOnLanding()
  local c = FS.Current()
  return c and c.row and c.row.endsOnLanding or false
end
-- The safe drop the spell ready now gives (0: none).
function FS.MaxDrop()
  local c = FS.Current()
  return c and c.drop or 0
end

-- Looked at again: a change in what's ready (another spell, none, the drop) works the route out again.
local function Key(c) return c and (c.id .. ":" .. c.drop) or "" end
FS.Key = Key
function FS.Refresh()
  local was = looked and Key(current) or nil
  current, looked = FS.Look(), true
  if was ~= nil and Key(current) ~= was then
    FS.changes = (FS.changes or 0) + 1
    -- (the step's spell used, FS.held: the route stays till the jump's done, its cooldown or the glide ended on landing
    -- no reason to work it out again; Kooki3z 2026-11-23, "no reroute after casting the jump spell". Said when the
    -- hold lets go, FS.Release)
    if FS.held then
      FS.held.changed = true
    else
      local N = ns.Nav
      if N and N.OptionsChanged then N.OptionsChanged() end
    end
  end
  return current
end

-- The spell's name as the game has it (the English where it hasn't); an item's, the item's (its spell's while the
-- game hasn't the item's name yet).
function FS.Name(c)
  if not c then return "" end
  if c.row.item then
    local ok, name = pcall(function()
      if C_Item and C_Item.GetItemNameByID then return C_Item.GetItemNameByID(c.row.item) end
      return GetItemInfo and (GetItemInfo(c.row.item)) or nil
    end)
    if ok and type(name) == "string" and name ~= "" then return name end
    return ns.SpellName and ns.SpellName(c.row.auras[1]) or c.row.name
  end
  return ns.SpellName and ns.SpellName(c.id) or c.row.name
end

-- The jumps a trip needs, each survivable with what the player has (spell jumping)? `jumps`: { { t = seconds from
-- now, dz = yards, key = }, ... } in order; `plain`: the player's own safe drop; `waits`: { [key] = true } jumps the
-- trip waits at for a source's cooldown. Each jump past `plain` takes a source with the reach, uses left and ready by
-- then (the one ready soonest; ties: no cooldown, then the trip's pick, then the most uses); using it starts its
-- cooldown (and its category's) and spends a use. Returns nil and the seconds waited in all when every one is; else k
-- (the first that isn't) and the wait it needs there (math.huge: no source left at all).
function FS.Budget(jumps, plain, waits)
  local N = ns.Nav
  local pick = N and N.fallPick
  local srcs = {}
  local st = S()
  if (FS.demo or not (st and st.useClassSpells == false)) and not (N and N.spellJumpsOff) then
    for _, row in ipairs(FS.SPELLS) do
      local owned
      if row.item then
        owned = BuffLeft(row) or (row.worn and Worn(row.item)) or (not row.worn and ItemCount(row.item) > 0)
      else
        owned = FS.KnownId(row) ~= nil
      end
      if owned then
        srcs[#srcs + 1] = { row = row, readyAt = FS.RowCooldown(row), uses = FS.UsesLeft(row), reach = FS.RowDrop(row) }
      end
    end
  end
  local catAt, shift, waited = {}, 0, 0
  for k, j in ipairs(jumps) do
    if j.dz and j.dz > plain + 0.5 then
      local t = j.t + shift
      local best, bw
      for _, s in ipairs(srcs) do
        if s.uses > 0 and s.reach + 0.5 >= j.dz then
          local at = math.max(s.readyAt, s.row.cat and catAt[s.row.cat] or 0)
          local w = math.max(0, at - t)
          local better = not best or w < bw - 0.01
          if not better and math.abs(w - bw) <= 0.01 then
            local a, b = (s.row.cd or 0) == 0, (best.row.cd or 0) == 0
            if a ~= b then
              better = a
            elseif pick and (FS.RowKey(s.row) == pick) ~= (FS.RowKey(best.row) == pick) then
              better = FS.RowKey(s.row) == pick
            else
              better = s.uses > best.uses
            end
          end
          if better then best, bw = s, w end
        end
      end
      if not best then return k, math.huge end
      if bw > 0.5 then
        if not (waits and j.key and waits[j.key]) then return k, bw end
        shift, waited, t = shift + bw, waited + bw, t + bw
      end
      best.uses = best.uses - 1
      best.readyAt = t + (best.row.cd or 0)
      if best.row.cat then catAt[best.row.cat] = t + (best.row.catCd or 0) end
    end
  end
  return nil, waited
end

-- The fall now under way at a drop needing a cast in the air (expert): FS.fall = { start, cueAt, landAt, row, name, use,
-- id }; armed at the ledge by FS.DropText (FS.fallArm), begun when IsFalling turns true within ARM_SECONDS of it.
FS.ARM_SECONDS = 5
local function Falling()
  if not IsFalling then return false end
  local ok, v = pcall(IsFalling)
  return ok and not Secret(v) and v == true
end
function FS.WatchFall()
  local arm, fall = FS.fallArm, FS.fall
  if not (arm or fall) then return end
  local now = GetTime()
  local falling = Falling()
  if fall then
    if not falling or now > fall.landAt + 3 then FS.fall = nil end
    return
  end
  if now - arm.at > FS.ARM_SECONDS then
    FS.fallArm = nil
    return
  end
  if falling then
    local reach = FS.RowReach(arm.c.row) * FS.CUE_SHARE
    FS.fall = { start = now, cueAt = now + FS.FallTime(arm.dz - reach), landAt = now + FS.FallTime(arm.dz), c = arm.c }
    FS.fallArm = nil
  end
end
-- "Cast Slow Fall now!" from the fall's cue to the landing, or nil.
function FS.FallCue()
  local f = FS.fall
  if not f or GetTime() < f.cueAt then return nil end
  return Format(f.c.row.use and L["Use %s now!"] or L["Cast %s now!"], FS.Name(f.c))
end
-- A drop of `dz` the cast for is made in the air (expert): past the buff's reach from the top.
function FS.InAir(c, dz)
  return c ~= nil and FS.Expert() and dz ~= nil and dz > FS.RowReach(c.row) + 0.5
end

-- A drop of `dz` yards needs the spell: more than the player's own safe drop.
function FS.Needs(dz)
  local N = ns.Nav
  local plain = N and N.PlainSafeDrop and N.PlainSafeDrop() or 14
  return dz ~= nil and dz > plain + 0.5
end

-- Whether casting now still has the buff up when a drop of `dz` yards `dist` yards ahead ends: the way there at the
-- player's speed, the fall, the margin, within the duration.
-- (`seconds`: the buff's time, its duration by default; its time left when it's up)
function FS.InTime(c, dist, dz, seconds)
  local N = ns.Nav
  local speed = 7
  if N and N.Speeds then
    local cur, walk, mount, mounted = N.Speeds()
    speed = (cur and cur > 0.5) and cur or (mounted and mount) or walk or speed
  end
  return (dist or 0) / math.max(speed, 1) + (dz or 0) / FS.FALL_YPS + FS.CAST_MARGIN <= (seconds or c.row.duration)
end

FS.ARM_YD = 15 -- yards from an expert drop's top: its fall is watched for (FS.WatchFall)
-- The next drop on the walk ahead needing the spell: its maneuver, or nil. (Turns.Ahead's maneuvers: `dropYd`)
FS.LOOK_AHEAD_YD = 400
function FS.NextDrop()
  local N = ns.Nav
  local r = N and N.route
  if not (r and N.dest and not r.flying and ns.Turns and ns.Turns.Ahead) then return nil end
  local ok, _, ms = pcall(ns.Turns.Ahead, r)
  if not ok or not ms then return nil end
  for _, m in ipairs(ms) do
    if m.dist and m.dist > FS.LOOK_AHEAD_YD then return nil end
    if m.kind == "drop" and FS.Needs(m.dropYd) then return m end
  end
  return nil
end

-- What the use button casts now (a row as Nav.UseNow's: { spell, [8] its name }), or nil: a drop ahead needs the
-- spell, its buff isn't up, and casting now lasts through the drop.
-- (Kooki3z 2026-11-23: "show the spell icon early, just tell the user to wait to cast it to survive the fall": shown
-- from when the jump is the next step; `early` (the button dimmed, still clickable) while casting now would wear off
-- before landing, the step saying to wait, FS.DropText)
-- Once shown, the button stays (Kooki3z 2026-11-23, by Bluefen: "can't take the button away mid jump like that"; a
-- reroute on the way down made the step "Jump down here" and Walk on Air's button went): the same spell or item kept,
-- whatever the next step now, while the player falls, till HOLD_SETTLE after landing, or till they've walked HOLD_YD
-- from where it was shown without falling. FS.held = { spell, item, name, x, y, fell, landedAt }.
FS.HOLD_YD, FS.HOLD_SETTLE = 25, 1.5
local function PlayerXY()
  local Geo = ns.Geo
  if not (Geo and Geo.PlayerWorld) then return nil end
  local x, y = Geo.PlayerWorld()
  return x, y
end
-- The hold let go: what's ready changed meanwhile (the spell used) works the route out again now, as FS.Refresh would
-- have; after the jump (landed and settled) the route below is worked out with it gone, as it should be.
function FS.Release()
  local h = FS.held
  FS.held = nil
  if h and h.changed then
    local N = ns.Nav
    if N and N.OptionsChanged then N.OptionsChanged() end
  end
end
local function Held(now)
  local h = FS.held
  if not h then return nil end
  local falling = Falling()
  -- (the buff seen up and gone again with no fall: cast, but the jump not made within it: let go, reroute)
  local up = h.row and BuffLeft(h.row)
  if up then h.buffSeen = true end
  if falling then
    h.fell, h.landedAt = true, nil
  elseif h.fell then
    h.landedAt = h.landedAt or now
    if now - h.landedAt >= FS.HOLD_SETTLE then FS.Release() return nil end -- (landed and settled)
  else
    if h.buffSeen and not up then FS.Release() return nil end
    local x, y = PlayerXY()
    if x and h.x and math.sqrt((x - h.x) ^ 2 + (y - h.y) ^ 2) > FS.HOLD_YD then FS.Release() return nil end
  end
  if h.item and not h.worn and ItemCount(h.item) < 1 and not h.buffSeen then FS.Release() return nil end
  FS.castRow = FS.castRow or {}
  local t = FS.castRow
  t.item, t.spell, t[8], t[10], t.fall, t.early, t.demo = h.item, h.spell, h.name, nil, true, nil, FS.demo and true or nil
  return t
end
function FS.CastNow()
  local now = GetTime()
  -- (the demo's button clicked: the glide shown by the tutorial, no button meanwhile)
  if FS.demo and FS.demo.castAt then
    FS.held = nil
    return nil
  end
  local f = FS.fall
  local t
  if f then -- (falling at an expert drop: dimmed till the cue, then lit)
    t = FS.CastRow(f.c)
    if t then t.early = now < f.cueAt or nil end
  else
    t = FS.CastFor(FS.NextDrop())
  end
  if t then
    local h = FS.held
    if not (h and h.spell == t.spell and h.item == t.item) then
      local x, y = PlayerXY()
      local src = f and f.c or FS.Current()
      FS.held = { spell = t.spell, item = t.item, name = t[8], x = x, y = y,
        worn = src and src.row and src.row.worn or nil, row = src and src.row or nil }
    else
      if h.row and BuffLeft(h.row) then h.buffSeen = true end -- (cast: FS.Held lets go when it ends with no fall)
      if Falling() then h.fell, h.landedAt = true, nil end
    end
    return t
  end
  return Held(now)
end
-- (... for the drop maneuver `m`: { dist, dropYd })
function FS.CastFor(m)
  local c = FS.Current()
  if not (c and m and m.dropYd and FS.Needs(m.dropYd)) then return nil end
  if c.up and FS.InTime(c, m.dist, m.dropYd, c.up) then return nil end -- (up long enough: just jump)
  local t = FS.CastRow(c)
  -- (too early: cast in the air (Expert jumper), or the buff would wear off before the landing)
  if t then t.early = (FS.InAir(c, m.dropYd) or not FS.InTime(c, m.dist, m.dropYd)) or nil end
  return t
end
-- The use button's row for source `c` (nil: none left).
function FS.CastRow(c)
  if c.row.reagent and ItemCount(c.row.reagent) < 1 then return nil end -- (the buff up spent the last one)
  if c.row.item and not c.row.worn and ItemCount(c.row.item) < 1 then return nil end -- (the last one used)
  FS.castRow = FS.castRow or {}
  local t = FS.castRow
  if c.row.item then
    t.item, t.spell = c.row.item, nil
  else
    t.item, t.spell = nil, c.id
  end
  t[8], t[10], t.fall, t.early = FS.Name(c), nil, true, nil
  t.demo = FS.demo and true or nil -- (the tutorial's demo: GPSFrame's insecure look-alike shows, G.DemoUseButton)
  return t
end

-- The words for a drop maneuver `m` (Turns.NowText): nil for the usual "Jump down here"; else the text with the
-- spell. `fmt(yards)` as NowText's.
function FS.DropText(m, fmt)
  if not (m and m.dropYd and FS.Needs(m.dropYd)) then return nil end
  local c = FS.Current()
  if c then
    local name = FS.Name(c)
    -- (on its cooldown still, the trip waiting for it: Nav.CheckSpellJumps)
    local cd = not c.up and FS.RowCooldown(c.row) or 0
    if cd > 0 then
      local T = ns.Teleports
      return Format(L["Wait %s for %s, then jump down"], T and T.FormatCooldown and T.FormatCooldown(cd) or
        tostring(math.ceil(cd)), name)
    end
    if FS.InAir(c, m.dropYd) then -- (spell jumping, any height: cast just before landing; armed for the fall's cue)
      if (m.dist or 0) <= FS.ARM_YD then FS.fallArm = { at = GetTime(), dz = m.dropYd, c = c } end
      return Format(c.row.use and L["Jump, then use %s just before you land"] or
        L["Jump, then cast %s just before you land"], name)
    end
    if c.up and FS.InTime(c, m.dist, m.dropYd, c.up) then return nil end -- (the buff up long enough: jump)
    if FS.InTime(c, m.dist, m.dropYd) then
      return Format(c.row.use and L["Use %s, then jump down"] or L["Cast %s, then jump down"], name)
    end
    return Format(c.row.use and L["Wait to use %s until the ledge (in %s)"] or L["Wait to cast %s until the ledge (in %s)"], name,
      fmt and fmt(m.dist or 0) or tostring(math.floor((m.dist or 0) + 0.5)))
  end
  return nil
end

-- `/agps castbutton` (debug, not translated): what the use buttons are set to and whether the game shows them, for a
-- report from the game (Kooki3z 2026-11-23: the step said to cast, no button seen).
function FS.DebugButtons()
  local out = {}
  local function Say(s) out[#out + 1] = s end
  local c = FS.Current()
  Say("fall source: " .. (c and (FS.RowKey(c.row) .. " id " .. tostring(c.id) .. " drop " .. tostring(c.drop)) or "none")
    .. " expert " .. tostring(FS.Expert()))
  local m = FS.NextDrop()
  Say("next drop: " .. (m and string.format("in %.0f yd, falls %.0f yd", m.dist or -1, m.dropYd or -1) or "none"))
  local t = FS.CastNow()
  Say("cast now: " .. (t and string.format("%s %s early %s", t.item and "item" or "spell", tostring(t.item or t.spell),
    tostring(t.early == true)) or "none") .. " combat " .. tostring(InCombatLockdown and InCombatLockdown() or false))
  local N = ns.Nav
  Say("use now (teleport): " .. tostring(N and N.UseNow and N.UseNow() ~= nil))
  local function Btn(label, b)
    if not b then
      Say(label .. ": none")
      return
    end
    local p = b.GetParent and b:GetParent()
    local pn = p and p.GetName and p:GetName() or tostring(p)
    Say(string.format("%s: key %s shown %s visible %s parent %s (shown %s) type %s spell %s item %s icon alpha %.2f size %.0f",
      label, tostring(b.key), tostring(b:IsShown()), tostring(b.IsVisible and b:IsVisible()), tostring(pn),
      tostring(p and p.IsShown and p:IsShown()), tostring(b:GetAttribute("type")), tostring(b:GetAttribute("spell")),
      tostring(b:GetAttribute("item")), b.icon and b.icon.GetAlpha and b.icon:GetAlpha() or -1,
      b.GetWidth and b:GetWidth() or -1))
  end
  Btn("map panel button", ns.GPS and ns.GPS.useBtn)
  Btn("arrow window button", rawget(_G, "AzerothGPSArrowUseButton"))
  for _, s in ipairs(out) do print("|cff33ff99AzerothGPS|r " .. s) end
  return out
end

-- (events: what's ready may have changed)
function FS.Init()
  if FS.frame or not CreateFrame then return end
  local ok, f = pcall(CreateFrame, "Frame")
  if not ok or not f then return end
  FS.frame = f
  for _, e in ipairs({ "BAG_UPDATE_DELAYED", "PLAYER_EQUIPMENT_CHANGED", "SPELLS_CHANGED", "LEARNED_SPELL_IN_TAB", "PLAYER_LEVEL_UP",
    "SPELL_UPDATE_COOLDOWN", "UPDATE_SHAPESHIFT_FORM", "PLAYER_REGEN_ENABLED", "PLAYER_REGEN_DISABLED",
    "PLAYER_ENTERING_WORLD" }) do
    pcall(f.RegisterEvent, f, e)
  end
  pcall(f.RegisterUnitEvent, f, "UNIT_AURA", "player")
  f:SetScript("OnEvent", function() FS.Refresh() end)
  -- (a fall at an expert drop: its cue timed every frame, only while one is armed or under way)
  f:SetScript("OnUpdate", function()
    if FS.fallArm or FS.fall then FS.WatchFall() end
  end)
  if C_Timer and C_Timer.NewTicker then FS.ticker = C_Timer.NewTicker(FS.TICK_SECONDS, function() FS.Refresh() end) end
end
FS.Init()
