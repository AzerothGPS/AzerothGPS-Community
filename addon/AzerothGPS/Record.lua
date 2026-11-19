-- The player's road fixes: roads drawn on the map where the road data misses one, and
-- stretches erased where it has one that isn't there (the road tools: "Draw a road" and
-- "Erase a road" on the map's buttons, or /agps draw). Saved in ns.db.tracks: routes use
-- them at once (Router.WithTracks), `agps roads` takes them into the road data, and they're
-- kept for sharing if the player opted in (Feedback). Once the addon's road data has one
-- (ns.RoadTracksIn, by its time), it moves to an archive (R.Archive): kept for good, never used.
local _, ns = ...
local L = ns.L or setmetatable({}, { __index = function(_, k) return k end }) -- (the game's language: Locales.lua)
local Format = ns.Format or string.format

local R = {}
ns.Record = R

local function Tracks()
  ns.db.tracks = ns.db.tracks or {}
  return ns.db.tracks
end
R.Tracks = Tracks

-- The fixes the road data has, kept for good (asked 2026-10-06, keep data forever): ns.db.tracksShipped, each as it
-- was with its points packed (`pk`, `zk`: ns.PackNumbers), never used by routes (the data's copy is) nor by Undo.
function R.Archive()
  ns.db.tracksShipped = ns.db.tracksShipped or {}
  return ns.db.tracksShipped
end
-- A copy of track `t` with its points packed, as the archive keeps it (Core.lua's ns.PackNumbers' format).
local function Pack(list)
  if ns.PackNumbers then return ns.PackNumbers(list) end
  local out = {}
  for i, v in ipairs(list) do out[i] = v == false and "-" or tostring(v) end
  return table.concat(out, " ")
end
function R.Packed(t)
  local c = {}
  for k, v in pairs(t) do c[k] = v end
  if type(c.pts) == "table" then c.pk, c.pts = Pack(c.pts), nil end
  if type(c.zs) == "table" then c.zk, c.zs = Pack(c.zs), nil end
  return c
end

-- At login: the fixes the road data now has go to the archive (R.Archive), out of the list routes and Undo go by.
-- (They were deleted before: a stroke set aside on purpose, or drawn in the same second as a shipped one, was lost.)
function R.Prune()
  local shipped = ns.RoadTracksIn
  if not shipped or not ns.db then return end
  local n = 0
  local archive = R.Archive()
  local have = {}
  for _, a in ipairs(archive) do have[tostring(a.time) .. ":" .. tostring(a.continent) .. ":" .. tostring(a.pk)] = true end
  local function prune(list, count)
    local moved = {}
    for i = #(list or {}), 1, -1 do
      if list[i].time and shipped[list[i].time] then
        table.insert(moved, 1, table.remove(list, i))
        if count then n = n + 1 end
      end
    end
    for _, t in ipairs(moved) do
      local c = R.Packed(t)
      local key = tostring(c.time) .. ":" .. tostring(c.continent) .. ":" .. tostring(c.pk)
      if not have[key] then -- (an older version's second copy of one: once)
        have[key] = true
        archive[#archive + 1] = c
      end
    end
  end
  prune(ns.db.tracks, true)
  -- (strokes saved on a city's level though drawn elsewhere, looking at another zone from down
  -- in the city: back on the continent)
  local P = ns.Passability
  for _, t in ipairs(ns.db.tracks or {}) do
    local lvl = ns.CityLevels and ns.CityLevels[t.continent]
    if lvl and P and P.InGrid and t.pts and t.pts[1] and not P.InGrid(t.continent, t.pts[1], t.pts[2]) then
      t.continent = lvl.base
    end
  end
  -- (and the copies kept for sharing: the data has them, nothing to share)
  prune(ns.db.feedback and ns.db.feedback.roads)
  if n > 0 then ns.Print(L["%d of your drawn roads and walls are in the map data now (kept in your saved data)"]:format(n)) end
end

-- Tracks changed: the walls at once, and the road network (it includes them) and the route rebuilt, after every
-- edit, the road and wall tools on or not (asked 2026-11-11: "make the route update immediately after a road or wall
-- is drawn, not after the tool is turned off"; until then the network waited for the tools to be turned off). The
-- network is rebuilt in the background; the map shows the edits over the roads as they were meanwhile (GPSFrame's
-- LayoutRoads).
function R.Changed()
  if ns.Passability and ns.Passability.RefreshWalls then ns.Passability.RefreshWalls() end
  if ns.GPS and ns.GPS.ClearEdges then ns.GPS.ClearEdges() end
  R.Apply()
end

-- The edits into the road network and the route.
function R.Apply()
  R.pending = nil
  if ns.Router and ns.Router.Reset then ns.Router.Reset() end
  if ns.Nav and ns.Nav.Invalidate then ns.Nav.Invalidate(true, true) end
  if ns.GPS and ns.GPS.Redraw then ns.GPS.Redraw() end
end

-- The tracks made this session (since the last /reload or login), the only ones Undo takes back (asked 2026-11-17:
-- "I accidently hit undo too many times and erased the path fix to stormwind bank, Undo on recorder should only be for
-- the current session reloaded"). By the track itself, never saved: a /reload starts it empty.
R.thisSession = setmetatable({}, { __mode = "k" })

-- A drawn road (op "add") or erased one ("remove"): saved; its number.
function R.Save(track)
  -- (the tutorial's practice, Tutorial.lua: R.practice = { list = {} } while its road section runs. A stroke or a
  -- recorded walk goes on that list, in memory only: never the saved tracks, the shared roads or the unsaved count)
  if R.practice then
    local list = R.practice.list
    list[#list + 1] = track
    if ns.GPS and ns.GPS.Redraw then ns.GPS.Redraw() end
    return #list
  end
  local t = Tracks()
  -- (a time of its own: it's the track's key)
  local used = {}
  for _, o in ipairs(t) do if o.time then used[o.time] = true end end
  while used[track.time] or (ns.RoadTracksIn and ns.RoadTracksIn[track.time]) do track.time = track.time + 1 end
  t[#t + 1] = track
  R.thisSession[track] = true
  if ns.Feedback then ns.Feedback.RoadRecorded(track) end
  if ns.MarkUnsaved then ns.MarkUnsaved("track:" .. tostring(track.time), "add") end
  R.Changed()
  return #t
end

-- Roads and walls someone shared, taken into the player's own (the dev tools' import of a Copy Map Data
-- text): kept with their times (their keys: one here already, or in the data, is left out), so routes use
-- them at once, Undo takes them back, and the road watcher puts them into the data as it does drawn ones.
-- `imported` (a player's import in the Import and Share window, asked 2026-10-06): marked `imported`, not `shared`,
-- and the road watcher leaves them out: the player's own data, never the addon's.
-- Each { op = "add"|"remove"|"wall"|"unwall", continent, time, pts, area, z, indoors, down, zs (a height per point),
-- stair }. How many added, how many were here already or in the data.
function R.AddShared(list, imported)
  local t = Tracks()
  local have = {}
  for _, o in ipairs(t) do
    if o.time then have[o.time] = true end
  end
  local n, had = 0, 0
  for _, s in ipairs(list or {}) do
    if s.time and not have[s.time] and not (ns.RoadTracksIn and ns.RoadTracksIn[s.time]) and s.pts and #s.pts >= 4 then
      t[#t + 1] = { op = s.op, drawn = true, shared = not imported or nil, imported = imported or nil,
        continent = s.continent, zone = s.zone or (imported and "imported" or "shared"), time = s.time, pts = s.pts,
        area = s.area or nil, z = s.z, indoors = s.indoors, down = s.down,
        zs = type(s.zs) == "table" and #s.zs == #s.pts / 2 and s.zs or nil, stair = s.stair or nil }
      R.thisSession[t[#t]] = true
      have[s.time] = true
      n = n + 1
      -- (a player's import: one unsaved change for all of it, the caller's)
      if ns.MarkUnsaved and not imported then ns.MarkUnsaved("track:" .. tostring(s.time), "add") end
    elseif s.time then
      had = had + 1
    end
  end
  if n > 0 then R.Changed() end
  return n, had
end

function R.Delete(i)
  local t = Tracks()
  if not (i and t[i]) then
    ns.Print(string.format(L["no drawn road #%s"], tostring(i)))
    return
  end
  local tr = table.remove(t, i)
  if ns.Feedback and ns.Feedback.RoadRemoved then ns.Feedback.RoadRemoved(tr) end
  local what = { remove = L["erased road"], wall = L["wall"], unwall = L["erased wall"] }
  ns.Print(L["took back #%d (%s)"]:format(i, what[tr.op] or L["drawn road"]))
  if ns.MarkUnsaved then ns.MarkUnsaved("track:" .. tostring(tr.time), "remove") end
  R.Changed()
end

-- The last one taken back: roads and walls (and their erasings) are one list, in the order drawn, so
-- Undo takes back whichever came last.
function R.Undo()
  if R.practice then -- (the tutorial's practice: its own last stroke, never a saved one)
    table.remove(R.practice.list)
    if ns.GPS and ns.GPS.Redraw then ns.GPS.Redraw() end
    return
  end
  if R.UndoRestore() then return end -- (a restore the last change: put back)
  local t = Tracks()
  local n = #t
  if n == 0 then
    ns.Print(L["no drawn road or wall to take back"])
    return
  end
  if not R.thisSession[t[n]] then -- (one from before this session: kept, R.thisSession)
    ns.Print(L["Undo takes back only what you changed since your last /reload or login. Older roads and walls stay: erase them with the road or wall tools instead."])
    return
  end
  R.Delete(n)
end

function R.List()
  local t = Tracks()
  if #t == 0 then ns.Print(L["no drawn roads waiting for the road data"]) end
  for i, tr in ipairs(t) do
    local what = { remove = L["erased road"], wall = L["wall"], unwall = L["erased wall"], add = L["road"] }
    ns.Print(Format(L["#%d %s %s, %d points, %s"], i, what[tr.op] or tr.op, tr.zone or "?",
      #tr.pts / 2, date("%Y-%m-%d %H:%M", tr.time)))
  end
end

-- Editing a road afterwards (asked 2026-11-18 for 1.3.10, issue #640: "Couldn't be provide tooling to change the drawn
-- data line by specifying the information afterwards? ... pick the floor level that would be on"). The road tools' Edit
-- Road picks a drawn or recorded road (R.TrackAt) and sets what it is: its floor or height, its kind (Router.TRACK_KINDS:
-- ground, floor, bridge, stairs, lift) and a stairs stretch on part of it. Saved as a new track (R.EditTrack) with the
-- same points and its `zs`, `kind`, `stairs`, that `replaces` the one edited (its time; `rpart`, a piece of a recorded
-- walk or an edit the data has): routes leave the old one out at once (Router.ExpandTracks), Undo takes the edit back,
-- and the road watcher ships it in the old one's place.
R.EDIT_PICK_YD = 12 -- yards: a click this near a road picks it

-- The roads that can be edited on `cont`: the player's own (drawn, recorded, those the data has from them: the archive)
-- and the data's with their heights (ns.FloorTracks), less those an edit replaced. Each { t, shipped, archived }.
function R.Editable(cont)
  local Rt = ns.Router
  local all, out = {}, {}
  local shipped = ns.RoadTracksIn or {}
  local function add(t, how)
    if t and t.continent == cont and (t.op == nil or t.op == "add") then all[#all + 1] = { t = t, how = how } end
  end
  for _, t in ipairs(Tracks()) do
    if not shipped[t.time or -1] then add(t, "own") end
  end
  for _, a in ipairs(R.Archive()) do
    if a.continent == cont and (a.op == nil or a.op == "add") and type(a.pk) == "string" and ns.UnpackNumbers then
      add({ op = "add", continent = a.continent, time = a.time, zone = a.zone, recorded = a.recorded,
        pts = ns.UnpackNumbers(a.pk), zs = type(a.zk) == "string" and ns.UnpackNumbers(a.zk) or nil, stair = a.stair,
        kind = a.kind }, "archived")
    end
  end
  for _, t in ipairs(ns.FloorTracks and ns.FloorTracks[cont] or {}) do
    if t.op == nil or t.op == "add" then
      local c = {}
      for k, v in pairs(t) do c[k] = v end
      c.continent = cont
      add(c, "shipped")
    end
  end
  local list = {}
  for _, a in ipairs(all) do list[#list + 1] = a.t end
  local gone = Rt and Rt.ReplacedSet and Rt.ReplacedSet(list) or {}
  local shippedTimes = {}
  for _, a in ipairs(all) do if a.how == "shipped" then shippedTimes[a.t.time or -1] = true end end
  for _, a in ipairs(all) do
    local t = a.t
    -- (an archived one the data ships with its heights: the data's copy, its pieces, not this one)
    local dup = a.how == "archived" and shippedTimes[t.time or -1]
    if not dup and not (Rt and Rt.Replaced and Rt.Replaced(gone, t)) and t.pts and #t.pts >= 4 then
      out[#out + 1] = { t = t, shipped = a.how == "shipped", archived = a.how == "archived" }
    end
  end
  return out
end

-- The editable road nearest (x, y) on `cont` within `reach` (EDIT_PICK_YD): { t, shipped, archived, d, i (its point
-- nearest), part }, or nil.
function R.TrackAt(cont, x, y, reach)
  reach = reach or R.EDIT_PICK_YD
  local best
  for _, c in ipairs(R.Editable(cont)) do
    local p = c.t.pts
    for k = 1, #p - 3, 2 do
      local ax, ay, bx, by = p[k], p[k + 1], p[k + 2], p[k + 3]
      local vx, vy = bx - ax, by - ay
      local L2 = vx * vx + vy * vy
      local f = L2 > 0 and math.max(0, math.min(1, ((x - ax) * vx + (y - ay) * vy) / L2)) or 0
      local d = math.sqrt((ax + vx * f - x) ^ 2 + (ay + vy * f - y) ^ 2)
      if d <= reach and (not best or d < best.d) then
        best = { t = c.t, shipped = c.shipped, archived = c.archived, d = d, i = f < 0.5 and (k + 1) / 2 or (k + 3) / 2,
          part = c.t.part }
      end
    end
  end
  return best
end

-- The point of track `t` nearest (x, y): its number (1 ..).
function R.NearestPoint(t, x, y)
  local best, bi = math.huge, 1
  for k = 1, #t.pts - 1, 2 do
    local d = (t.pts[k] - x) ^ 2 + (t.pts[k + 1] - y) ^ 2
    if d < best then best, bi = d, (k + 1) / 2 end
  end
  return bi
end

-- The heights for an edit of `n` points `pts`: `kind` (ground: none unless `z` given; stairs: from `z1` at the first
-- point to `z2` at the last; else `z` at every point, or the track's own `old` zs when no `z`), a stairs stretch
-- `stairs` = { i, j, z1, z2 } rising evenly by the yards along from i to j, the points before at z1, after at z2.
function R.EditHeights(pts, kind, z, old, stairs, z1, z2)
  local n = #pts / 2
  local Rt = ns.Router
  local function ramp(a, b, za, zb, out)
    local sub = {}
    for k = a, b do sub[#sub + 1], sub[#sub + 2] = pts[2 * k - 1], pts[2 * k] end
    local hs = Rt.RampHeights(sub, za, zb)
    for k = a, b do out[k] = hs[k - a + 1] end
  end
  if stairs then
    local i, j, a, b = stairs[1], stairs[2], tonumber(stairs[3]), tonumber(stairs[4])
    if not (i and j and a and b and i >= 1 and j <= n and j > i) then return nil end
    local out = {}
    for k = 1, n do out[k] = k < i and a or b end
    ramp(i, j, a, b, out)
    return out
  end
  if kind == "stairs" or kind == "lift" then
    z1, z2 = tonumber(z1), tonumber(z2)
    if not (z1 and z2) then return nil end
    local out = {}
    ramp(1, n, z1, z2, out)
    return out
  end
  z = tonumber(z)
  if z then
    local out = {}
    for k = 1, n do out[k] = z end
    return out
  end
  if kind == "ground" then return nil end
  if type(old) == "table" and #old == n then
    local out = {}
    for k = 1, n do out[k] = old[k] end
    return out
  end
  return nil
end

-- Save an edit of the road picked (`sel`, R.TrackAt's): { kind, z (its height), z1, z2 (a stairs' or lift's foot and
-- top), stairs = { i, j, z1, z2 } (a stairs stretch) }. Its number in the drawn roads, or nil and why.
function R.EditTrack(sel, edit)
  local t = sel and sel.t
  if not (t and t.pts and #t.pts >= 4 and edit) then return nil, "nothing" end
  local kind = edit.kind
  local known = false
  for _, k in ipairs(ns.Router and ns.Router.TRACK_KINDS or {}) do known = known or k == kind end
  if not known then return nil, "kind" end
  local function r1(v) return math.floor(v * 10 + 0.5) / 10 end
  local zs = R.EditHeights(t.pts, kind, edit.z, t.zs, edit.stairs, edit.z1, edit.z2)
  if not zs and kind ~= "ground" then return nil, "height" end
  if zs then for k = 1, #zs do zs[k] = r1(zs[k]) end end
  local pts = {}
  for k = 1, #t.pts do pts[k] = t.pts[k] end
  local track = { op = "add", drawn = true, edit = true, continent = t.continent, zone = t.zone or "?", time = time(),
    pts = pts, zs = zs, z = zs and zs[1] or nil, kind = kind, replaces = t.time,
    rpart = sel.shipped and t.part or nil, -- (a piece of a walk or an edit the data has: that piece; else all of it)
    stair = kind == "stairs" and zs ~= nil or nil,
    stairs = edit.stairs and { edit.stairs[1], edit.stairs[2] } or nil }
  return R.Save(track)
end

-- Restoring the map's own data (asked 2026-11-14: "a magic eraser ... that can be used to restore original road and
-- wall data", a zone's, a continent's): the player's own edits of one kind (the road tools': drawn roads, erased roads,
-- stairs, recorded walks; the wall tools': walls and wall erasers) taken out where they lie, so the data's roads and
-- walls are as shipped there again. A stroke that runs on past the area is cut there, the rest of it kept (as new
-- strokes, its parts); an erased area (a loop) or stairs the area touches go whole. Undo puts it all back.
R.RESTORE_OPS = { road = { add = true, remove = true }, wall = { wall = true, unwall = true } }
R.restores = {} -- (Undo's: each restore's tracks taken out and parts put in, the last on top; this session only)

-- Track `t`'s points, with points put in along a stretch longer than `step` that goes through the area (`inside`)
-- between two points outside it: { x, y, ... } and their heights (nil when it has none), and its own points' places.
local function Densified(t, inside, step)
  local pts, zs = t.pts, t.zs
  if not step or t.recorded then return pts, zs end -- (a recorded walk's points are 2 yd apart: as they are)
  local out, oz, n = {}, zs and {} or nil, #pts / 2
  for i = 1, n do
    local x, y = pts[2 * i - 1], pts[2 * i]
    out[#out + 1], out[#out + 2] = x, y
    if oz then oz[#oz + 1] = zs[i] end
    if i < n then
      local x2, y2 = pts[2 * i + 1], pts[2 * i + 2]
      local d = math.sqrt((x2 - x) ^ 2 + (y2 - y) ^ 2)
      local m = math.ceil(d / step)
      if m > 1 then
        local hit = false
        for k = 1, m - 1 do
          if inside(x + (x2 - x) * k / m, y + (y2 - y) * k / m) then hit = true break end
        end
        if hit then
          for k = 1, m - 1 do
            out[#out + 1], out[#out + 2] = x + (x2 - x) * k / m, y + (y2 - y) * k / m
            if oz then oz[#oz + 1] = k * 2 <= m and zs[i] or zs[i + 1] end
          end
        end
      end
    end
  end
  return out, oz
end

-- A part of track `t` (points `a` to `b` of `pts`/`zs`): a copy of it with those points; a recorded walk's notes
-- (indoors or not, the times, the rooms' names, the floors picked, its stairs marks) cut to them too.
local function Part(t, pts, zs, a, b)
  local c = {}
  for k, v in pairs(t) do c[k] = v end
  c.pts = {}
  for i = a, b do c.pts[#c.pts + 1], c.pts[#c.pts + 2] = pts[2 * i - 1], pts[2 * i] end
  if zs then
    c.zs = {}
    for i = a, b do c.zs[#c.zs + 1] = zs[i] end
    c.z = c.zs[1] or t.z
  end
  c.stairs = nil
  if t.recorded and type(t.rec) == "table" then -- (a recorded walk's points are its own: not densified)
    local r = t.rec
    local rec = {}
    if type(r.ind) == "string" then rec.ind = r.ind:sub(a, b) end
    if type(r.ts) == "string" then
      local ts = {}
      for v in r.ts:gmatch("[^,]+") do ts[#ts + 1] = v end
      local part = {}
      for i = a, b do part[#part + 1] = ts[i] or "0" end
      rec.ts = table.concat(part, ",")
    end
    -- ({ point, value, ... }: those in the part, numbered from its start; the one in effect at its start first)
    local function marks(list)
      if type(list) ~= "table" then return nil end
      local out, before = {}, nil
      for i = 1, #list - 1, 2 do
        local p = list[i]
        if p < a then before = list[i + 1]
        elseif p <= b then
          if p > a and before ~= nil and #out == 0 then out[1], out[2] = 1, before end
          out[#out + 1], out[#out + 2] = p - a + 1, list[i + 1]
        end
      end
      if #out == 0 and before ~= nil then out[1], out[2] = 1, before end
      return #out > 0 and out or nil
    end
    rec.zt, rec.pk = marks(r.zt), marks(r.pk)
    c.rec = rec
    if type(t.stairs) == "table" then
      local st = {}
      for i = 1, #t.stairs - 1, 2 do
        local s, e = t.stairs[i], t.stairs[i + 1]
        if s >= a and e <= b then st[#st + 1], st[#st + 2] = s - a + 1, e - a + 1 end
      end
      c.stairs = #st > 0 and st or nil
    end
  end
  return c
end

-- Track `t` restored where `inside(x, y)`: nil when it isn't there; else the parts of it left ({} for none).
-- `step`: the yards apart its points are looked at along a long stretch (nil: only at its points).
function R.CutTrack(t, inside, step)
  if type(t.pts) ~= "table" or #t.pts < 2 then return nil end
  local pts, zs = Densified(t, inside, step)
  local n = #pts / 2
  local inn, any = {}, false
  for i = 1, n do
    inn[i] = inside(pts[2 * i - 1], pts[2 * i]) and true or false
    any = any or inn[i]
  end
  if not any then return nil end
  if t.area or t.stair then return {} end -- (an erased area, stairs: whole)
  local parts, a = {}, nil
  for i = 1, n + 1 do
    if i <= n and not inn[i] then
      a = a or i
    elseif a then
      if i - 1 > a then parts[#parts + 1] = Part(t, pts, zs, a, i - 1) end
      a = nil
    end
  end
  return parts
end

-- Restores the data where `inside(x, y)` on continent `cont` (its city levels with it) for the `kind` of edits ("road"
-- or "wall"); `box` (minX, minY, maxX, maxY) the area's bounds, to skip strokes nowhere near (nil: any); `step` as
-- R.CutTrack's. How many edits went whole, how many were cut, how many parts were kept.
function R.Restore(kind, cont, inside, box, step)
  local ops = R.RESTORE_OPS[kind]
  if not ops then return 0, 0, 0 end
  if R.practice then -- (the tutorial's practice: its own strokes)
    local list = R.practice.list
    for i = #list, 1, -1 do
      local parts = ops[list[i].op] and R.CutTrack(list[i], inside, step)
      if parts then table.remove(list, i) end
    end
    if ns.GPS and ns.GPS.Redraw then ns.GPS.Redraw() end
    return 0, 0, 0
  end
  local Geo = ns.Geo
  local base = Geo and Geo.Base(cont) or cont
  local t = Tracks()
  local removed, added, whole, cut = {}, {}, 0, 0
  for i = 1, #t do
    local tr = t[i]
    local on = ops[tr.op] and tr.continent and (Geo and Geo.Base(tr.continent) or tr.continent) == base
    if on and box and type(tr.pts) == "table" then
      local x1, y1, x2, y2 = math.huge, math.huge, -math.huge, -math.huge
      for k = 1, #tr.pts - 1, 2 do
        local x, y = tr.pts[k], tr.pts[k + 1]
        if x < x1 then x1 = x end
        if x > x2 then x2 = x end
        if y < y1 then y1 = y end
        if y > y2 then y2 = y end
      end
      on = not (x2 < box[1] or x1 > box[3] or y2 < box[2] or y1 > box[4])
    end
    local parts = on and R.CutTrack(tr, inside, step)
    if parts then
      removed[#removed + 1] = { i = i, t = tr }
      if #parts == 0 then whole = whole + 1 else cut = cut + 1 end
      for _, p in ipairs(parts) do added[#added + 1] = p end
    end
  end
  if #removed == 0 then return 0, 0, 0 end
  for k = #removed, 1, -1 do
    local tr = table.remove(t, removed[k].i)
    if ns.Feedback and ns.Feedback.RoadRemoved then ns.Feedback.RoadRemoved(tr) end
    if ns.MarkUnsaved then ns.MarkUnsaved("track:" .. tostring(tr.time), "remove") end
  end
  -- (the parts kept: strokes of their own, each a time (its key) of its own)
  local used = {}
  for _, o in ipairs(t) do if o.time then used[o.time] = true end end
  for _, r in ipairs(removed) do if r.t.time then used[r.t.time] = true end end
  for _, p in ipairs(added) do
    p.time = (p.time or time()) + 1
    while used[p.time] or (ns.RoadTracksIn and ns.RoadTracksIn[p.time]) do p.time = p.time + 1 end
    used[p.time] = true
    t[#t + 1] = p
    if ns.Feedback then ns.Feedback.RoadRecorded(p) end
    if ns.MarkUnsaved then ns.MarkUnsaved("track:" .. tostring(p.time), "add") end
  end
  R.restores[#R.restores + 1] = { removed = removed, added = added, count = #t }
  R.Changed()
  return whole, cut, #added
end

-- Undo of the last restore, when it's the last change (nothing drawn since, or what was is taken back): true if so.
function R.UndoRestore()
  local t = Tracks()
  while #R.restores > 0 do
    local e = R.restores[#R.restores]
    if #t > e.count then return false end -- (something drawn since: that first)
    local ok = #t == e.count
    for k = 1, #e.added do
      if t[#t - #e.added + k] ~= e.added[k] then ok = false break end
    end
    table.remove(R.restores)
    if ok then
      for _ = 1, #e.added do
        local p = table.remove(t)
        if ns.Feedback and ns.Feedback.RoadRemoved then ns.Feedback.RoadRemoved(p) end
        if ns.MarkUnsaved then ns.MarkUnsaved("track:" .. tostring(p.time), "remove") end
      end
      for _, r in ipairs(e.removed) do
        table.insert(t, math.min(r.i, #t + 1), r.t)
        if ns.Feedback then ns.Feedback.RoadRecorded(r.t) end
        if ns.MarkUnsaved then ns.MarkUnsaved("track:" .. tostring(r.t.time), "add") end
      end
      ns.Print(Format(L["put back what was restored (%d of your changes)"], #e.removed))
      R.Changed()
      return true
    end
  end
  return false
end

-- The edits of `kind` on `cont` (its city levels too), and in the zone `zone` there when given (any of their points).
function R.CountEdits(kind, cont, zone)
  local ops = R.RESTORE_OPS[kind]
  local Geo, Ro = ns.Geo, ns.Router
  local base = Geo and Geo.Base(cont) or cont
  local n = 0
  for _, tr in ipairs(Tracks()) do
    if ops and ops[tr.op] and tr.continent and (Geo and Geo.Base(tr.continent) or tr.continent) == base then
      local hit = not zone
      if zone and type(tr.pts) == "table" then
        for k = 1, #tr.pts - 1, 2 do
          if Ro.ZoneAt(base, tr.pts[k], tr.pts[k + 1]) == zone then hit = true break end
        end
      end
      if hit then n = n + 1 end
    end
  end
  return n
end

-- Record (the road tools' pop-out, asked 2026-10-06: "a record button (pop out from road drawing tool) that will
-- capture this data automatically"): the player walks a road and it's saved as a drawn road (`recorded`), with what the
-- game tells of where they walked: a point every REC_STEP_YD and at the corners, indoors or not at each (`rec.ind`,
-- "1"/"0"/"?"), the minimap's zone text where it changed (`rec.zt` = { point, text, ... }: a building's or a cave's
-- rooms name themselves there), the tenths of a second between points (`rec.ts`), the floor picked with Shift + wheel
-- (`zs`, as a stroke's, for routes now; `rec.pk` = { point, height or false, ... } where the pick changed, for the
-- watcher), and their own Stairs Start / Stairs End marks (`stairs` = { first point, last point, ... }).
-- The game gives no height: the road watcher works each point's floor out (roads/recorded.py, the best path over the
-- floors under the whole walk). A new walk at a loading screen, a jump, a level change and REC_MAX_POINTS; paused in
-- combat, on a flight, a boat or a zeppelin, while dead, while the dev tools' simulated player is on, and where the game
-- hides the position (R.PauseReason). Kept going over a /reload (`recordOn`), not a logout.
R.REC_TICK = 0.1 -- seconds between samples
R.REC_STEP_YD = 2 -- a point at least this far from the last
R.REC_TURN = math.rad(25) -- and at a corner: the way turning this much there (its sample REC_TURN_MIN_YD on, at least)
R.REC_TURN_MIN_YD = 1
R.REC_JUMP_YD = 30 -- moved this far between two samples: a new walk (a teleport)
-- ... and a shorter hop onto where a portal puts you (ns.Transports' `land1`/`land2`): Stormwind's Wizard's Sanctum, the
-- tower's top and the trainers' room 9 yd apart on the map (2026-11-17: one walk, and its floors dropped into the room
-- halfway up the stairs)
R.REC_PORTAL_YD = 5
R.REC_PORTAL_LAND_YD = 4

-- Whether a hop of a sample from (ax, ay) to (x, y) on `level` was a portal's (R.REC_PORTAL_YD).
function R.PortalHop(level, ax, ay, x, y)
  if (x - ax) ^ 2 + (y - ay) ^ 2 < R.REC_PORTAL_YD ^ 2 then return false end
  local r2 = R.REC_PORTAL_LAND_YD ^ 2
  for _, t in pairs(ns.Transports or {}) do
    if type(t) == "table" and t[8] == "teleporter" then
      for side, l in ipairs({ t.land1 or false, t.land2 or false }) do
        if l and t[side == 1 and 1 or 4] == level and (x - l[1]) ^ 2 + (y - l[2]) ^ 2 <= r2 then return true end
      end
    end
  end
  return false
end
R.REC_RESUME_YD = 3 -- moved this far while paused: a new walk on going on (else the same one)
R.REC_MIN_YD = 8 -- a walk shorter than this isn't saved (as a stroke)
R.REC_MAX_POINTS = 1000 -- a walk this long is saved, and the next goes on from its last point

local function NewWalk(r)
  r.pts, r.ind, r.ts, r.zs, r.zt, r.stairs, r.pk = {}, {}, {}, {}, {}, {}, {}
  r.yd, r.lastT, r.lastZt, r.lastPk, r.cand, r.t0, r.g0 = 0, nil, nil, false, nil, nil, nil
end

-- The map's name where the player is (a walk's `zone`, as a stroke's).
local function ZoneName()
  local ok, info = pcall(function()
    local id = C_Map.GetBestMapForUnit("player")
    return id and C_Map.GetMapInfo(id)
  end)
  return ok and info and info.name or "?"
end

-- Why recording waits right now, or nil.
function R.PauseReason()
  local Geo = ns.Geo
  if Geo and Geo.Simulated and Geo.Simulated() then return "the simulated player is on" end
  if UnitIsDeadOrGhost and UnitIsDeadOrGhost("player") then return "dead" end
  if ns.inCombat or (UnitAffectingCombat and UnitAffectingCombat("player")) then return "in combat" end
  if UnitOnTaxi and UnitOnTaxi("player") then return "on a flight" end
  if ns.Taxi and ns.Taxi.Riding and ns.Taxi.Riding() then return "on a boat or zeppelin" end
  if not (Geo and Geo.RealPlayerWorld and Geo.RealPlayerWorld()) then return "no position here" end
  return nil
end

-- A sample kept as the walk's next point: s = { x, y, now, indoors, zone text, picked floor }.
local function AddPoint(r, s)
  local n = #r.pts / 2 + 1
  local x, y = math.floor(s[1] * 10 + 0.5) / 10, math.floor(s[2] * 10 + 0.5) / 10
  if n > 1 then
    local lx, ly = r.pts[#r.pts - 1], r.pts[#r.pts]
    if lx == x and ly == y then return end
    r.yd = r.yd + math.sqrt((x - lx) ^ 2 + (y - ly) ^ 2)
  end
  r.g0 = r.g0 or s[3]
  r.t0 = r.t0 or time()
  r.zone = n == 1 and ZoneName() or r.zone
  r.pts[#r.pts + 1], r.pts[#r.pts + 2] = x, y
  r.ind[n] = s[4] == true and "1" or s[4] == false and "0" or "?"
  local t = math.floor((s[3] - r.g0) * 10 + 0.5)
  r.ts[n] = math.max(0, t - (r.lastT or t))
  r.lastT = t
  r.zs[n] = s[6] or false
  -- (and where the floor picked changed, `rec.pk`: the watcher weighs what was picked, not `zs` filled in for routes)
  if (s[6] or false) ~= r.lastPk then
    r.pk[#r.pk + 1], r.pk[#r.pk + 2] = n, s[6] or false
    r.lastPk = s[6] or false
  end
  if s[5] ~= r.lastZt then
    r.zt[#r.zt + 1], r.zt[#r.zt + 2] = n, s[5] or ""
    r.lastZt = s[5]
  end
end

-- The walk so far saved (two points and REC_MIN_YD at least) as a drawn road; `goOn`: the next walk starts at its
-- last point (REC_MAX_POINTS, an open stairs mark carried on). Its number in the drawn roads, or nil.
function R.FinishWalk(goOn)
  local r = R.rec
  if not r then return nil end
  local n = #r.pts / 2
  local saved
  local stairs = {}
  for _, v in ipairs(r.stairs) do stairs[#stairs + 1] = v end
  if r.stairOpen and n > r.stairOpen then stairs[#stairs + 1], stairs[#stairs + 2] = r.stairOpen, n end
  if n >= 2 and r.yd >= R.REC_MIN_YD then
    local G = ns.GPS
    local zs = G and G.StrokeHeights and G.StrokeHeights(r.zs, n) or nil
    saved = R.Save({ op = "add", drawn = true, recorded = true, continent = r.level, zone = r.zone or "?",
      time = r.t0 or time(), pts = r.pts, zs = zs, z = zs and zs[1] or nil,
      rec = { ind = table.concat(r.ind), ts = table.concat(r.ts, ","), zt = r.zt, pk = #r.pk > 0 and r.pk or nil },
      stairs = #stairs > 0 and stairs or nil })
    r.saved = (r.saved or 0) + 1
  end
  local last
  if n > 0 then
    local indoors -- (as sampled: true, false, or nil when unknown)
    if r.ind[n] == "1" then indoors = true elseif r.ind[n] == "0" then indoors = false end
    last = { r.pts[2 * n - 1], r.pts[2 * n], r.g0 and (r.g0 + (r.lastT or 0) / 10) or 0, indoors, r.lastZt, r.zs[n] }
  end
  NewWalk(r)
  if goOn and last then
    AddPoint(r, last)
    r.stairOpen = r.stairOpen and 1 or nil
  else
    r.stairOpen = nil
  end
  return saved
end

-- A sample at (x, y) of `level` at `now` (GetTime), indoors or not (nil: unknown), the minimap's zone text, the floor
-- picked (or false): a point every REC_STEP_YD, the corner when the way turns, a new walk after a jump or onto another
-- level. `force`: a point here whatever (a stairs mark's).
function R.RecordSample(x, y, level, now, indoors, zt, fz, force)
  local r = R.rec
  if not (r and x and y) then return end
  local pts = r.pts
  local n = #pts / 2
  local s = { x, y, now, indoors, zt, fz }
  if n > 0 then
    local c = r.cand or { pts[2 * n - 1], pts[2 * n] }
    if level ~= r.level or (x - c[1]) ^ 2 + (y - c[2]) ^ 2 > R.REC_JUMP_YD ^ 2 or R.PortalHop(level, c[1], c[2], x, y) then
      R.FinishWalk()
      n = 0
    end
  end
  if n == 0 then
    r.level = level
    AddPoint(r, s)
    r.cand = nil
    return
  end
  local lx, ly = pts[2 * n - 1], pts[2 * n]
  local c = r.cand
  if c then
    -- (a corner: from the last point to the latest sample, then on to this one, the way turned)
    local ax, ay, bx, by = c[1] - lx, c[2] - ly, x - c[1], y - c[2]
    local la, lb = math.sqrt(ax * ax + ay * ay), math.sqrt(bx * bx + by * by)
    if la >= R.REC_TURN_MIN_YD and lb >= 0.3 and (ax * bx + ay * by) / (la * lb) < math.cos(R.REC_TURN) then
      AddPoint(r, c)
      lx, ly = c[1], c[2]
    end
  end
  if force or (x - lx) ^ 2 + (y - ly) ^ 2 >= R.REC_STEP_YD ^ 2 then
    AddPoint(r, s)
    r.cand = nil
  else
    r.cand = s
  end
  if #r.pts / 2 >= R.REC_MAX_POINTS then R.FinishWalk(true) end
end

-- A sample from the game now (R.REC_TICK apart while recording), or the pause it's in. `force`: a point here.
function R.RecordTick(now, force)
  local r = R.rec
  if not r then return end
  local why = r.userPaused and "paused" or R.PauseReason()
  if why then
    r.paused = why
    return
  end
  local Geo = ns.Geo
  local x, y, cont = Geo.RealPlayerWorld()
  local level = ns.Nav and ns.Nav.PlayerLevel and ns.Nav.PlayerLevel(cont) or cont
  if r.paused then
    -- (going on: the same walk while still where it stopped, else a new one)
    local n = #r.pts / 2
    if n > 0 and (level ~= r.level or (x - r.pts[2 * n - 1]) ^ 2 + (y - r.pts[2 * n]) ^ 2 > R.REC_RESUME_YD ^ 2) then
      R.FinishWalk()
    end
    r.paused, r.cand = nil, nil
  end
  local indoors
  if IsIndoors then
    local ok, v = pcall(IsIndoors)
    if ok and not (ns.IsSecret and ns.IsSecret(v)) then indoors = v and true or false end
  end
  local zt
  if GetMinimapZoneText then
    local ok, v = pcall(GetMinimapZoneText)
    if ok and type(v) == "string" and not (ns.IsSecret and ns.IsSecret(v)) then zt = v end
  end
  local G = ns.GPS
  local fz = G and G.editFloor and G.editFloor.z or false
  R.RecordSample(x, y, level, now, indoors, zt, fz, force)
end

-- Recording on: samples every REC_TICK (a frame of its own, shown only while recording).
function R.StartRecording(quiet)
  if R.rec then return end
  R.rec = { saved = 0 }
  NewWalk(R.rec)
  if not R.recFrame and CreateFrame then
    local f = CreateFrame("Frame")
    local acc = 0
    f:SetScript("OnUpdate", function(_, elapsed)
      acc = acc + (elapsed or 0)
      if acc < R.REC_TICK then return end
      acc = 0
      R.RecordTick(GetTime())
      R.RefreshWindow()
    end)
    if ns.TimeScript then ns.TimeScript(f, "OnUpdate", "recording") end
    R.recFrame = f
  end
  if R.recFrame then R.recFrame:Show() end
  R.RecordTick(GetTime())
  if not quiet then ns.Print(L["recording: walk the road, then Stop (Stairs Start and Stairs End at a staircase's foot and top)"]) end
  R.RefreshWindow()
  if ns.GPS and ns.GPS.RefreshQuick then ns.GPS.RefreshQuick() end
end

-- Recording off: the walk so far saved.
function R.StopRecording()
  local r = R.rec
  if not r then return end
  R.FinishWalk()
  R.rec = nil
  if R.recFrame then R.recFrame:Hide() end
  if R.practice then -- (the tutorial's practice walk: R.Save kept it in memory only)
    ns.Print(L["Practice: nothing was saved."])
  else
    ns.Print((r.saved or 0) == 1 and L["recording stopped: 1 walk saved as a drawn road (Undo takes the last back)"]
      or L["recording stopped: %d walks saved as drawn roads (Undo takes the last back)"]:format(r.saved or 0))
    -- (the game gives no height: a walk up stairs looks flat until it's imported, 2026-11-18)
    if (r.saved or 0) > 0 then ns.Print(L["Recorded walks show flat until they're added to the road data, which works out their heights and stairs."]) end
    R.lastSaved = r.saved
  end
  R.RefreshWindow()
  if ns.GPS and ns.GPS.RefreshQuick then ns.GPS.RefreshQuick() end
end

-- Pause (or go on), the player's own.
function R.TogglePause()
  local r = R.rec
  if not r then return end
  r.userPaused = not r.userPaused or nil
  R.RecordTick(GetTime())
  R.RefreshWindow()
end

-- Stairs Start, then Stairs End: the stretch between is stairs (the watcher lets its height climb there). A point where
-- the player stands first, so the mark is there. Whether it was marked.
function R.MarkStairs()
  local r = R.rec
  if not r then
    ns.Print(L["Record isn't on (the road tools' Record button)"])
    return false
  end
  R.RecordTick(GetTime(), true)
  local n = #r.pts / 2
  if r.paused or n == 0 then
    ns.Print(L["recording is paused: stairs not marked"])
    return false
  end
  if r.stairOpen then
    if n > r.stairOpen then r.stairs[#r.stairs + 1], r.stairs[#r.stairs + 2] = r.stairOpen, n end
    r.stairOpen = nil
    ns.Print(L["stairs end marked"])
  else
    r.stairOpen = n
    ns.Print(L["stairs start marked: Stairs End at their top"])
  end
  R.RefreshWindow()
  return true
end

-- A loading screen (PLAYER_ENTERING_WORLD): the walk so far is one walk. After a /reload, recording that was on goes on.
function R.OnEnteringWorld(isInitialLogin, isReloadingUi)
  local cdb = ns.CharDB and ns.CharDB()
  if R.rec then
    R.FinishWalk()
  elseif cdb and cdb.recordOn and isReloadingUi then
    R.StartRecording(true)
    ns.Print(L["still recording (the road tools' Record window)"])
    R.ShowWindow()
  end
  if cdb then cdb.recordOn = nil end
end

-- A /reload or logout (PLAYER_LOGOUT): the walk so far saved; recording goes on after a /reload.
function R.OnLogout()
  if R.practice then R.rec = nil end -- (the tutorial's practice walk: let go, not gone on with after a /reload)
  if not R.rec then return end
  R.FinishWalk()
  local cdb = ns.CharDB and ns.CharDB()
  if cdb then cdb.recordOn = true end
end

-- The Record window (an ns.Window): what's recorded, and Record / Pause, Stop, Stairs Start / End and Undo.
-- (the walks saved, a sentence of its own after the status)
local function WalksSaved(n)
  return n == 1 and L["1 walk saved."] or L["%d walks saved."]:format(n)
end
function R.RecordStatus()
  local r = R.rec
  if not r then
    local done = R.lastSaved and (" " .. WalksSaved(R.lastSaved)) or ""
    return L["Record, then walk the road."] .. done, L["Stairs Start at a staircase's foot, Stairs End at its top."]
  end
  local n = #r.pts / 2
  local s
  if r.paused then
    -- (r.paused is R.PauseReason's id, said in the game's language here)
    local why = { ["the simulated player is on"] = L["the simulated player is on"], dead = L["dead"],
      ["in combat"] = L["in combat"], ["on a flight"] = L["on a flight"],
      ["on a boat or zeppelin"] = L["on a boat or zeppelin"], ["no position here"] = L["no position here"] }
    s = r.paused == "paused" and L["Paused."] or L["Paused: %s."]:format(why[r.paused] or r.paused)
  else
    local points = n == 1 and L["1 point"] or L["%d points"]:format(n)
    local dist, zt = ns.Nav.FormatDistance(r.yd), r.lastZt and r.lastZt ~= "" and r.lastZt or nil
    if r.ind[n] == "1" then
      s = zt and Format(L["Recording: %s, %s, indoors, %s."], points, dist, zt)
        or Format(L["Recording: %s, %s, indoors."], points, dist)
    else
      s = zt and Format(L["Recording: %s, %s, %s."], points, dist, zt) or Format(L["Recording: %s, %s."], points, dist)
    end
  end
  if (r.saved or 0) > 0 then s = s .. " " .. WalksSaved(r.saved) end
  local key = GetBindingKey and GetBindingKey("AZEROTHGPS_RECORD_STAIRS")
  local st = r.stairOpen and L["On the stairs: Stairs End at their top."] or L["Stairs Start at a staircase's foot, Stairs End at its top."]
  return s, key and Format(L["%s (Key: %s)"], st, key) or st
end

function R.RefreshWindow()
  local f = R.window
  if not (f and f:IsShown()) then return end
  local s, st = R.RecordStatus()
  f.status:SetText(s)
  f.stairsText:SetText(st)
  local r = R.rec
  f.rec:SetText(not r and L["Record"] or r.userPaused and L["Resume"] or L["Pause"])
  f.stop:SetEnabled(r ~= nil)
  f.stairs:SetEnabled(r ~= nil)
  f.stairs:SetText(r and r.stairOpen and L["Stairs End"] or L["Stairs Start"])
end

function R.ShowWindow()
  local f = R.window
  if not f then
    f = ns.Window("AzerothGPSRecord", 360, 150, L["Record"])
    local function Text(font, y)
      local t = f:CreateFontString(nil, "ARTWORK", font)
      t:SetPoint("TOPLEFT", 14, f.top - y)
      t:SetPoint("RIGHT", -14, 0)
      t:SetJustifyH("LEFT")
      return t
    end
    f.status = Text("GameFontHighlight", 10)
    f.stairsText = Text("GameFontHighlightSmall", 32)
    local note = Text("GameFontDisableSmall", 52)
    note:SetText(L["Each walk is saved as a drawn road, with where you were indoors and the rooms' names, so its floors can be worked out."])
    local function Button(label, w, x, fn)
      local b = CreateFrame("Button", nil, f, "UIPanelButtonTemplate")
      b:SetSize(w, 22)
      b:SetPoint("BOTTOMLEFT", x, 10)
      b:SetText(label)
      b:SetScript("OnClick", fn)
      return b
    end
    f.rec = Button(L["Record"], 80, 12, function()
      if R.rec then R.TogglePause() else R.StartRecording() end
      R.RefreshWindow()
    end)
    f.stop = Button(L["Stop"], 64, 96, function() R.StopRecording() end)
    f.stairs = Button(L["Stairs Start"], 100, 164, function() R.MarkStairs() end)
    f.undo = Button(L["Undo"], 64, 268, function() R.Undo() end)
    R.window = f
  end
  f:Show()
  R.RefreshWindow()
  return f
end

function R.ToggleWindow()
  if R.window and R.window:IsShown() then
    R.window:Hide()
  else
    R.ShowWindow()
  end
end
