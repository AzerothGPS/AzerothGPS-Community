"""The whole addon run offline, as in the game: every file in the toc's order under Lua 5.1 (lupa's),
with a stand-in for the game's UI (wowmock.lua, next to this file), the start-up events fired. For
the tests (app/tests/test_map_redraw.py and the private dev repo's) and the trip sweep
(`agps trip-sweep`)."""

from __future__ import annotations

from pathlib import Path

from .paths import ADDON_DIR

MOCK = Path(__file__).resolve().parent / "wowmock.lua"

GLOBALS = """
  strsplit = function(sep, s, n)
    local out, pat = {}, "([^" .. sep .. "]*)"
    for part in (s .. sep):gmatch(pat .. sep) do out[#out + 1] = part end
    return unpack(out)
  end
  strtrim = function(s) return (s:gsub("^%s+", ""):gsub("%s+$", "")) end
  strjoin = function(sep, ...) return table.concat({ ... }, sep) end
  tinsert, tremove, wipe = table.insert, table.remove, function(t) for k in pairs(t) do t[k] = nil end return t end
  format = string.format
  date = os.date
  time = os.time
"""


def toc_files() -> list[str]:
    out = []
    for line in (ADDON_DIR / "AzerothGPS.toc").read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            out.append(line.replace("\\", "/"))
    return out


def start(replace: dict | None = None, saved: str | None = None, locale: str | None = None, pre: str | None = None,
          also: list | None = None):
    """(lua, ns): the addon loaded and started up (ADDON_LOADED, PLAYER_LOGIN), the player in Brill
    (AGPS_POS), GetTime from AGPS_T. Router: no background warm-up, walks searched at once (the
    tests' defaults; a caller sets WARM / SYNC_WALKS for the game's way). `replace`: a toc file's text to load
    instead of its own ({"Data/Indoors.lua": text}: data being checked before it's written). `saved`: a saved
    variables file's text (`AzerothGPSDB = { ... }`), run as the game does, after the files and before ADDON_LOADED.
    `locale`: what GetLocale() says (the game client's language, "deDE"...; the mock's "enUS" otherwise). `pre`: Lua run
    before the files load (game functions the files hook as they load: TakeTaxiNode...). `also`: other addons' folders
    (a Path each, its toc named as the folder) loaded after AzerothGPS, as the game does with an addon that depends on it
    (the dev addon's tests: its files load before AzerothGPS starts; a toc file not there, a generated one, is skipped)."""
    from lupa import lua51

    lua = lua51.LuaRuntime()
    lua.execute(MOCK.read_text(encoding="utf-8"))
    lua.execute(GLOBALS)
    if locale is not None:
        lua.globals().AGPS_LOCALE = locale
        lua.execute("GetLocale = function() return AGPS_LOCALE end")
    if pre is not None:
        lua.execute(pre)
    ns = lua.table()
    lua.globals().AGPS_NS = ns
    loader = lua.eval("function(src, name) return assert(loadstring(src, '@' .. name)) end")
    for name in toc_files():
        src = (replace or {}).get(name)
        loader(src if src is not None else (ADDON_DIR / name).read_text(encoding="utf-8"), name)("AzerothGPS", ns)
    for folder in also or []:
        folder = Path(folder)
        private = lua.table()
        for line in (folder / f"{folder.name}.toc").read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or not line.endswith(".lua"):
                continue
            f = folder / line.replace("\\", "/")
            if f.is_file():
                loader(f.read_text(encoding="utf-8"), line)(folder.name, private)
    if saved is not None:
        lua.execute(saved)
    fire = lua.eval("AGPS_FIRE")
    fire("ADDON_LOADED", "AzerothGPS")
    for folder in also or []:
        fire("ADDON_LOADED", Path(folder).name)
    fire("PLAYER_LOGIN")
    errors = list(ns.initErrors.values())
    if errors:
        raise RuntimeError(f"the addon failed to start: {errors}")
    ns.Router.WARM, ns.Router.SYNC_WALKS = False, True
    return lua, ns
