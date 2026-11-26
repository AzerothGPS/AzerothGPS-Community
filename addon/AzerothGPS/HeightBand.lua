-- The player's height band from range checks (item 104, 1.4.1; Kooki3z 2026-11-26: "use spell/item range checks as
-- another reference for where the player is").
--
-- WoW Forever gives addons no height for the player (UnitPosition's z is always 0), but the game's range checks are in
-- 3D. An NPC that stands still at its one spawn nearby (Data/Npcs.lua's spawns; `ns.NpcsStill`: every spawn of it idle,
-- MovementType 0, so no wanderers or patrols) is at a known height, and the player names it to the client through a
-- unit token (target, mouseover, the soft interact or soft friend target, focus, the NPC whose window is open). In
-- range R of it at d yards across, the player is within sqrt(R^2 - d^2) of its height; out of range, farther than that.
-- Each reading cuts the heights the player may stand at; together they're a band (a list of { lo, hi }).
--
-- The band is extra evidence for the floor followed (Nav.TrackCityZ in buildings, capitals and Undercity; Nav.TrackGridZ
-- over the world grid's stacked surfaces; CityGrid.TrackFloor): floors out of it are dropped from the candidates, and
-- where that leaves one floor it's picked (after a login, a /reload, a teleport, a hearthstone, a lift, or wherever the
-- candidates disagree). Never the only source: it only ever chooses among the floors the roads or the grids have there,
-- and with no NPC in reach (no reading) nothing changes.
--
-- The calls, all read-only (nothing is targeted, cast or used), checked against the client's own API docs
-- (Blizzard_APIDocumentationGenerated in WoW Forever's CASC, 1.60.1): C_Spell.IsSpellInRange (true, false, or nil when
-- the spell can't be asked about that unit), C_Item.IsItemInRange, CheckInteractDistance; none has secret returns or
-- restrictions there, UnitGUID's is secret where unit identity is restricted (checked with ns.IsSecret). UnitInRange is
-- secret and party only; UnitPosition gives no height. No friendly nameplates on Forever, so no nameplate tokens. Asked
-- only out of combat, off flights and outside instances, at most every EVERY seconds, each call in a pcall.
local _, ns = ...
local HB = {}
ns.HeightBand = HB

local sqrt, max, min, huge = math.sqrt, math.max, math.min, math.huge

HB.UNITS = { "target", "mouseover", "softinteract", "softfriend", "focus", "npc" }
HB.SHORTEST_YD = 5 -- (5 yd and shorter ranges add both units' combat reach, which isn't known: left out)
HB.LONGEST_YD = 60
HB.RANGE_SLACK = 3 -- yards: in range means within the range and at most this more (the bodies' reach)
HB.WANDER_YD = 2 -- yards an NPC may stand off its spawn (the data's spot against the game's)
HB.SPAWN_YD = 60 -- an NPC's spawn this near the player is the one it stands at ...
HB.SPAWN_ALONE_YD = 40 -- ... when no other spawn of it is this near that one
HB.KEEP_SECONDS = 8 -- a reading counts this long ...
HB.KEEP_YD = 3 -- ... while the player is this near where it was taken
HB.EVERY = 0.25 -- seconds between looks
HB.SPELLS_SECONDS = 60 -- the spellbook's ranged spells looked at again this often
HB.ITEMS_SECONDS = 30 -- the bags' ranged items this often
HB.PER_RANGE = 2 -- spells (or items) asked at each range: one that can't be asked about the unit says nil
HB.RANGES = 6 -- distinct ranges asked, the shortest first (the long ones bound little)
HB.FLOOR_SLACK = 1 -- yards a floor may lie outside the band and still count as in it
-- CheckInteractDistance's yards by index: { in range of at most, out of range of at least }. The client doesn't say
-- them and the game's versions differ (trade 11.11 or 8, duel 9.9 or 7), so in range takes the larger and out of range
-- the smaller: the band is never narrower than the truth.
HB.INTERACT = { [2] = { 11.11, 7 }, [3] = { 9.9, 7 }, [4] = { 28, 28 } }
-- (without the spellbook's API: spells that may be cast on a friendly NPC, asked when known)
HB.FALLBACK_SPELLS = { 2050, 17, 1243, 635, 19740, 5185, 774, 1126, 331, 1459, 5697 }

HB.readings = {}

local function Dist(ax, ay, bx, by)
  local dx, dy = ax - bx, ay - by
  return sqrt(dx * dx + dy * dy)
end
local function Secret(v) return ns.IsSecret ~= nil and ns.IsSecret(v) end

---------------------------------------------------------------------------------------------------- the NPCs
-- Whether creature `id` stands still at its spawns (ns.NpcsStill, read the first time).
local still
function HB.Still(id)
  if not still then
    still = {}
    for s in tostring(ns.NpcsStill or ""):gmatch("%d+") do still[tonumber(s)] = true end
  end
  return still[id] == true
end
function HB.ResetStill() still = nil end -- (the tests)

-- Creature `id`'s shipped spawns, { level, x, y, z, ... }, or nil: its line found in ns.NpcsPacked (not the whole list
-- unpacked: Layers.ShippedNpcs is the search's, at its first use), kept per id.
local spawnCache = {}
function HB.Spawns(id)
  local c = spawnCache[id]
  if c ~= nil then return c or nil end
  local packed, out = ns.NpcsPacked, false
  if type(packed) == "string" and type(id) == "number" then
    local key = string.format("%d|", id)
    local s
    if packed:sub(1, #key) == key then
      s = 1
    else
      local a = packed:find("\n" .. key, 1, true)
      s = a and a + 1
    end
    if s then
      local e = packed:find("\n", s, true) or (#packed + 1)
      local spawns = packed:sub(s, e - 1):match("([^|]*)$")
      local list = {}
      for lv, x, y, z in (spawns or ""):gmatch("(%-?%d+) (%-?[%d.]+) (%-?[%d.]+) (%-?[%d.]+)") do
        list[#list + 1], list[#list + 2], list[#list + 3], list[#list + 4] =
          tonumber(lv), tonumber(x), tonumber(y), tonumber(z)
      end
      if list[1] then out = list end
    end
  end
  spawnCache[id] = out
  return out or nil
end
function HB.ResetSpawns() spawnCache = {} end -- (the tests)

-- The spawn of creature `id` the unit stands at, near (px, py) on `level`: x, y, z, or nil (it doesn't stand still,
-- none near, or two near each other: can't tell which).
function HB.SpawnOf(id, level, px, py)
  if not HB.Still(id) then return nil end
  local sp = HB.Spawns(id)
  if not sp then return nil end
  local best, bd, second
  for i = 1, #sp - 3, 4 do
    if sp[i] == level then
      local d = Dist(sp[i + 1], sp[i + 2], px, py)
      if d <= HB.SPAWN_YD then
        if not bd or d < bd then
          second = best
          best, bd = i, d
        elseif not second then second = i end
      end
    end
  end
  if not best then return nil end
  if second and Dist(sp[best + 1], sp[best + 2], sp[second + 1], sp[second + 2]) < HB.SPAWN_ALONE_YD then return nil end
  return sp[best + 1], sp[best + 2], sp[best + 3]
end

---------------------------------------------------------------------------------------------------- the checks
-- The ranges to ask, shortest first: { { r, ids = { spell, ... } } }, from `byRange` ([r] = { id, ... }).
local function Ladder(byRange)
  local rs = {}
  for r in pairs(byRange) do rs[#rs + 1] = r end
  table.sort(rs)
  local out = {}
  for i = 1, min(#rs, HB.RANGES) do out[i] = { r = rs[i], ids = byRange[rs[i]] } end
  return out
end
local function RangeOf(spell)
  local S = C_Spell
  local ok, info = pcall(S.GetSpellInfo, spell)
  local r = ok and type(info) == "table" and info.maxRange
  if type(r) ~= "number" or Secret(r) or r <= HB.SHORTEST_YD or r > HB.LONGEST_YD then return nil end
  return r
end

-- The player's spells with a range, by range (the spellbook's, not passive; a spell that can't be cast on the NPC
-- answers nil and the next of its range is asked). Looked at again every SPELLS_SECONDS.
function HB.SpellLadder()
  local now = GetTime()
  if HB.spells and now >= HB.spellsAt and now - HB.spellsAt < HB.SPELLS_SECONDS then return HB.spells end
  local byRange = {}
  local S, SB = C_Spell, C_SpellBook
  local function Add(id)
    local r = RangeOf(id)
    if not r then return end
    local l = byRange[r]
    if not l then l = {} byRange[r] = l end
    if #l < HB.PER_RANGE then l[#l + 1] = id end
  end
  if S and S.GetSpellInfo and S.IsSpellInRange then
    if SB and SB.GetNumSpellBookSkillLines and SB.GetSpellBookSkillLineInfo and SB.GetSpellBookItemInfo then
      local bank = Enum and Enum.SpellBookSpellBank and Enum.SpellBookSpellBank.Player or 0
      local ok, n = pcall(SB.GetNumSpellBookSkillLines)
      for li = 1, (ok and type(n) == "number" and not Secret(n)) and min(n, 20) or 0 do
        local ok2, line = pcall(SB.GetSpellBookSkillLineInfo, li)
        local cnt = ok2 and type(line) == "table" and line.numSpellBookItems
        local off = ok2 and type(line) == "table" and line.itemIndexOffset
        if type(cnt) == "number" and not Secret(cnt) and not Secret(off) then
          local first = (type(off) == "number" and off or 0) + 1
          for slot = first, first + min(cnt, 200) - 1 do
            local ok3, it = pcall(SB.GetSpellBookItemInfo, slot, bank)
            local id = ok3 and type(it) == "table" and it.isPassive == false and it.spellID
            if type(id) == "number" and not Secret(id) then Add(id) end
          end
        end
      end
    else
      for _, id in ipairs(HB.FALLBACK_SPELLS) do
        local ok, known = pcall(IsPlayerSpell or function() return false end, id)
        if ok and known and not Secret(known) then Add(id) end
      end
    end
  end
  HB.spells, HB.spellsAt = Ladder(byRange), now
  return HB.spells
end

-- The items in the bags whose use has a range (its spell's), by range. Looked at again every ITEMS_SECONDS.
function HB.ItemLadder()
  local now = GetTime()
  if HB.items and now >= HB.itemsAt and now - HB.itemsAt < HB.ITEMS_SECONDS then return HB.items end
  local byRange, seen = {}, {}
  local Cn, I, S = C_Container, C_Item, C_Spell
  if Cn and Cn.GetContainerNumSlots and Cn.GetContainerItemID and I and I.GetItemSpell and I.IsItemInRange
      and S and S.GetSpellInfo then
    for bag = 0, 4 do
      local ok, n = pcall(Cn.GetContainerNumSlots, bag)
      for slot = 1, (ok and type(n) == "number" and not Secret(n)) and n or 0 do
        local ok2, id = pcall(Cn.GetContainerItemID, bag, slot)
        if ok2 and type(id) == "number" and not Secret(id) and not seen[id] then
          seen[id] = true
          local ok3, _, spell = pcall(I.GetItemSpell, id)
          local r = ok3 and type(spell) == "number" and not Secret(spell) and RangeOf(spell)
          if r then
            local l = byRange[r]
            if not l then l = {} byRange[r] = l end
            if #l < HB.PER_RANGE then l[#l + 1] = id end
          end
        end
      end
    end
  end
  HB.items, HB.itemsAt = Ladder(byRange), now
  return HB.items
end
function HB.ResetLadders() HB.spells, HB.items = nil, nil end -- (the tests; a new spell or bag)

-- One range check's answer: true (in range), false (out of it), nil (none: it can't be asked about that unit).
local function Ask(fn, a, b)
  local ok, v = pcall(fn, a, b)
  if not ok or v == nil or Secret(v) then return nil end
  return v and true or false
end

-- A unit's checks now: { r, inside, src } each (one a range: the first spell or item there that answers).
function HB.Checks(unit)
  local out, have = {}, {}
  local S = C_Spell
  if S and S.IsSpellInRange then
    for _, rung in ipairs(HB.SpellLadder()) do
      for _, id in ipairs(rung.ids) do
        local inside = Ask(S.IsSpellInRange, id, unit)
        if inside ~= nil then
          out[#out + 1] = { r = rung.r, inside = inside, src = "spell" .. id }
          have[rung.r] = true
          break
        end
      end
    end
  end
  local I = C_Item
  if I and I.IsItemInRange then
    for _, rung in ipairs(HB.ItemLadder()) do
      if not have[rung.r] then
        for _, id in ipairs(rung.ids) do
          local inside = Ask(I.IsItemInRange, id, unit)
          if inside ~= nil then
            out[#out + 1] = { r = rung.r, inside = inside, src = "item" .. id }
            break
          end
        end
      end
    end
  end
  if CheckInteractDistance then
    for idx, yd in pairs(HB.INTERACT) do
      local inside = Ask(CheckInteractDistance, unit, idx)
      if inside ~= nil then
        out[#out + 1] = { r = inside and yd[1] or yd[2], inside = inside, src = "interact" .. idx }
      end
    end
  end
  return out
end

---------------------------------------------------------------------------------------------------- the readings
-- Whether the client may be asked now: out of combat, not on a flight, not in an instance.
function HB.CanLook()
  local ok, v = pcall(InCombatLockdown or function() return false end)
  if not ok or v ~= false and v ~= nil then return false end
  ok, v = pcall(UnitAffectingCombat or function() return false end, "player")
  if not ok or v ~= false and v ~= nil then return false end
  if UnitOnTaxi and UnitOnTaxi("player") then return false end
  if IsInInstance then
    local ok2, inst = pcall(IsInInstance)
    if not ok2 or inst ~= false and inst ~= nil then return false end
  end
  return true
end

-- The readings at (px, py) on `level`: new ones from the units the player names (every EVERY seconds), and those kept
-- (taken within KEEP_SECONDS, the player within KEEP_YD of where), one per NPC and check, the newest.
function HB.Look(level, px, py)
  local now = GetTime()
  if not (HB.lookAt and now >= HB.lookAt and now - HB.lookAt < HB.EVERY) and HB.CanLook() then
    HB.lookAt = now
    local seen = {}
    for _, unit in ipairs(HB.UNITS) do
      local ok, exists = pcall(UnitExists or function() return true end, unit)
      if ok and exists and not Secret(exists) then
        local okp, isPlayer = pcall(UnitIsPlayer or function() return false end, unit)
        local okg, guid = pcall(UnitGUID or function() return nil end, unit)
        local id = okp and not isPlayer and okg and type(guid) == "string" and not Secret(guid) and not seen[guid]
          and ns.Nav and ns.Nav.NpcOf and ns.Nav.NpcOf(guid)
        if id then
          seen[guid] = true
          local x, y, z = HB.SpawnOf(id, level, px, py)
          if x then
            for _, ck in ipairs(HB.Checks(unit)) do
              HB.readings[#HB.readings + 1] = { x = x, y = y, z = z, r = ck.r, inside = ck.inside, src = ck.src,
                at = now, px = px, py = py, npc = id, unit = unit, level = level }
            end
          end
        end
      end
    end
  end
  local kept, by = {}, {}
  for i = #HB.readings, 1, -1 do
    local rd = HB.readings[i]
    if rd.level == level and now >= rd.at and now - rd.at <= HB.KEEP_SECONDS
        and Dist(rd.px, rd.py, px, py) <= HB.KEEP_YD then
      local k = string.format("%.1f:%.1f:%s", rd.x, rd.y, rd.src)
      if not by[k] then
        by[k] = true
        table.insert(kept, 1, rd)
      end
    end
  end
  HB.readings = kept
  return kept
end
function HB.Reset() HB.readings, HB.lookAt, HB.last = {}, nil, nil end -- (the tests)

-- The band of heights the readings allow at (px, py): a list of { lo, hi } (nil: no reading, every height; empty:
-- the readings disagree).
function HB.Band(readings, px, py)
  if not (readings and readings[1]) then return nil end
  local band = { { -huge, huge } }
  local function Cut(lo, hi) -- (keep only [lo, hi])
    local out = {}
    for _, iv in ipairs(band) do
      local a, b = max(iv[1], lo), min(iv[2], hi)
      if a <= b then out[#out + 1] = { a, b } end
    end
    band = out
  end
  local function Hole(lo, hi) -- (take out (lo, hi))
    local out = {}
    for _, iv in ipairs(band) do
      if iv[2] <= lo or iv[1] >= hi then
        out[#out + 1] = iv
      else
        if iv[1] < lo then out[#out + 1] = { iv[1], lo } end
        if iv[2] > hi then out[#out + 1] = { hi, iv[2] } end
      end
    end
    band = out
  end
  for _, rd in ipairs(readings) do
    local d = Dist(rd.x, rd.y, px, py)
    if rd.inside then
      local R2 = rd.r + HB.RANGE_SLACK + HB.WANDER_YD
      local dd = max(0, d - HB.WANDER_YD)
      if dd < R2 then
        local hz = sqrt(R2 * R2 - dd * dd)
        Cut(rd.z - hz, rd.z + hz)
      end
    else
      local dd = d + HB.WANDER_YD
      if dd < rd.r then
        local hz = sqrt(rd.r * rd.r - dd * dd)
        Hole(rd.z - hz, rd.z + hz)
      end
    end
  end
  return band
end
-- Whether height z is in the band (within `slack`; no band: every height is).
function HB.InBand(band, z, slack)
  if not band then return true end
  slack = slack or HB.FLOOR_SLACK
  for _, iv in ipairs(band) do
    if z >= iv[1] - slack and z <= iv[2] + slack then return true end
  end
  return false
end

-- The band where the player stands at (px, py) on `level` (nil: no NPC in reach, or it says nothing; never errors).
-- Kept for the debug readout (HB.last).
function HB.Here(level, px, py)
  if not (level and px and py) then return nil end
  local ok, readings = pcall(HB.Look, level, px, py)
  if not ok then return nil end
  local band = HB.Band(readings, px, py)
  -- (the readings disagree, an empty band: bad data or an NPC off its spot; it says nothing)
  if band and not band[1] then band = nil end
  -- (a band of everything: no reading near enough to bound the height)
  if band and band[1][1] == -huge and band[#band][2] == huge and #band == 1 then band = nil end
  local last = HB.last
  HB.last = { level = level, x = px, y = py, band = band, readings = readings, at = GetTime(),
    pick = last and last.level == level and Dist(last.x, last.y, px, py) <= HB.KEEP_YD and last.pick or nil }
  return band
end

-- The heights of `list` in the band (each `list[i]` a number, or a table with `key`): a new list; nil when the band
-- leaves none of them (it's wrong there: none counts) or there's no band.
function HB.Keep(band, list, key)
  if not band then return nil end
  local out = {}
  for _, e in ipairs(list) do
    local z = key and e[key] or e
    if type(z) == "number" and HB.InBand(band, z) then out[#out + 1] = e end
  end
  return out[1] and out or nil
end

-- A floor picked or confirmed by the band (the debug readout's: HB.last.pick).
function HB.NotePick(z, by)
  local last = HB.last
  if not last then
    last = {}
    HB.last = last
  end
  last.pick = { z = z, by = by, at = GetTime() }
end
