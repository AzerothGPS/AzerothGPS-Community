-- The seamless map's data (Atlas/Atlas.lua runs it only while the seamless map is on): generated numbers
-- and names, not edited by hand.
--
-- Lettering: the continents' and seas' names, set live in the client's font. `map`: the map whose art px the
-- lines are measured in; `name`: the client's name for a map or an area (`text` when it has none); `fade`:
-- "land" or "sea"; `ink`, `glow` 0-255 and `glowA` the halo's strength; `lines`: one a word, { left, right,
-- baseline, cap height [, true: all small capitals] }.
local _, ns = ...
ns.AtlasChunks = ns.AtlasChunks or {}
ns.AtlasChunks[#ns.AtlasChunks + 1] = { "data/Lettering", function(D)
D.Lettering = {
  {
    fade = "land",
    glow = { 243, 189, 81 },
    glowA = 0.7,
    ink = { 78, 44, 12 },
    lines = { { 112, 332, 330, 20 } },
    map = 947,
    name = { map = 1414, text = "Kalimdor" },
  },
  {
    fade = "land",
    glow = { 243, 189, 81 },
    glowA = 0.7,
    ink = { 78, 44, 12 },
    lines = { { 660, 800, 387, 14 }, { 641, 816, 411.5, 14.5 } },
    map = 947,
    name = { map = 1415, text = "Eastern Kingdoms" },
  },
  {
    fade = "sea",
    glow = { 168, 172, 152 },
    glowA = 0.35,
    ink = { 66, 60, 44 },
    lines = { { 251, 287, 161, 11.5, true }, { 225, 314, 185, 17 }, { 246, 293, 209, 17 } },
    map = 1414,
    name = { area = 457, text = "The Veiled Sea" },
  },
  {
    fade = "sea",
    glow = { 168, 172, 152 },
    glowA = 0.35,
    ink = { 66, 60, 44 },
    lines = { { 229, 271, 279, 13, true }, { 209, 293, 303, 17 }, { 227, 274, 327, 17 } },
    map = 1415,
    name = { area = 214, text = "The Great Sea" },
  },
  {
    fade = "sea",
    glow = { 168, 172, 152 },
    glowA = 0.35,
    ink = { 66, 60, 44 },
    lines = { { 730, 770, 243, 12.5, true }, { 677, 822, 269, 17 }, { 728, 771, 290, 17 } },
    map = 1415,
    name = { area = 308, text = "The Forbidding Sea" },
  },
}
end }
