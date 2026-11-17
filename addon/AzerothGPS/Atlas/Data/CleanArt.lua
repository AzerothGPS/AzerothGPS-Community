-- The seamless map's data (Atlas/Atlas.lua runs it only while the seamless map is on): generated numbers
-- and names, not edited by hand.
--
-- CleanArt[uiMap] = { tile, ... }: base art tiles (row by row, from 1) drawn from MapArt/<uiMap>_<tile>,
-- cleaned of baked-in lettering, instead of the client's own file.
local _, ns = ...
ns.AtlasChunks = ns.AtlasChunks or {}
ns.AtlasChunks[#ns.AtlasChunks + 1] = { "data/CleanArt", function(D)
D.CleanArt = {
  [947] = { 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12 },
  [1414] = { 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12 },
  [1415] = { 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12 },
}
end }
