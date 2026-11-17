-- The seamless map's data (Atlas/Atlas.lua runs it only while the seamless map is on): generated numbers
-- and names, not edited by hand.
--
-- CityBanners[city] = { zone, x, y, width, height }: the zone art's name banner for a city (MapBanner/<city>),
-- at x, y in the zone's art px. BannerCutouts[zone]: that zone's art goes through MapBannerHole/<zone>.
-- CityPlans[city]: the city's map is cut to its plan (MapCityMask/<city>). CityTitled[city]: the cut keeps
-- its own title, so the zone's banner for it fades as the city comes in.
local _, ns = ...
ns.AtlasChunks = ns.AtlasChunks or {}
ns.AtlasChunks[#ns.AtlasChunks + 1] = { "data/CityBanners", function(D)
D.CityBanners = {
  [1454] = { 1411, 276, 7, 512, 128 },
  [1456] = { 1412, 306, 226, 256, 64 },
  [1457] = { 1438, 113, 427, 512, 64 },
  [1458] = { 1420, 484, 484, 512, 64 },
}
D.BannerCutouts = { [1411] = true, [1412] = true, [1420] = true, [1438] = true }
D.CityPlans = { [1454] = true, [1456] = true, [1458] = true }
D.CityTitled = { [1454] = true, [1456] = true, [1458] = true }
end }
