-- The addon's own text in the game's language (GetLocale()). `ns.L` is keyed by the English text: L["Quest Route"].
-- A key a language doesn't have (and every key on an English client, enUS/enGB) reads as the English itself.
-- Each Locales\<locale>.lua fills ns.L only when it is the client's language (ns.NewLocale), so only one is kept.
-- Names the game gives (zones, NPCs, items, spells) come already in the client's language and are never keys here.
-- Formatted text is one whole sentence per key ("%d stops added to the route (%d in all)"); a language that needs
-- its values in another order writes them "%2$s ... %1$s", and that key is formatted with ns.Format.
local _, ns = ...

ns.L = ns.L or setmetatable({}, { __index = function(_, key) return key end })
-- The languages there's text for; a player can pick one of them over the game's (`/agps language`, kept in
-- AzerothGPSDB.language: read here, as the files load, by the toc's LoadSavedVariablesFirst; a /reload applies it).
ns.LOCALES = { enUS = true, deDE = true, esES = true, esMX = true, frFR = true, itIT = true, koKR = true, ptBR = true,
  ruRU = true, zhCN = true, zhTW = true }
local picked = type(AzerothGPSDB) == "table" and AzerothGPSDB.language
ns.loadedLanguage = type(picked) == "string" and picked or "auto" -- (what a /reload would change: Options > General)
ns.LOCALE = (picked and ns.LOCALES[picked] and picked) or (GetLocale and GetLocale()) or "enUS"

-- The table to fill for `locale`, or nil when the client is in another language.
function ns.NewLocale(locale)
  if ns.LOCALE ~= locale then return nil end
  return ns.L
end

-- string.format that also takes positional values ("%2$s ... %1$s"), as some translations need.
function ns.Format(fmt, ...)
  if not fmt:find("%%%d+%$") then return string.format(fmt, ...) end
  local args, ordered, n = { ... }, {}, 0
  local plain = fmt:gsub("%%(%%?)(%d*)(%$?)", function(pct, num, dollar)
    if pct == "%" then return "%%" .. num .. dollar end
    n = n + 1
    ordered[n] = args[dollar == "$" and tonumber(num) or n]
    return dollar == "$" and "%" or ("%" .. num)
  end)
  return string.format(plain, (unpack or table.unpack)(ordered, 1, n))
end
