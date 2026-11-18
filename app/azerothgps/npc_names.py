"""The shipped NPCs' names in each client language (asked 2026-11-17: "All players should be able to search for NPCs
they haven't met yet"): Data/NpcNames/<locale>.lua, one file per language, each read only on a client of that
language (its first line returns on any other), so a client keeps its own language in memory and no other.

From AzerothCore's `creature_template_locale` (GPL-2, data/thirdparty/azerothcore, never committed): rows (entry,
locale, Name, Title) for deDE, esES, esMX, frFR, koKR, ruRU, zhCN and zhTW. Its entries are creature template ids,
Data/Npcs.lua's (checked against AzerothCore's own `creature_template` English names: an NPC whose English name
differs there is left out, it may not be the same NPC). itIT and ptBR have none: those clients show the English until
an NPC is met (Locales.lua's ns.LearnNpcName).

Kept small: a name only where it differs from the English, and the titles ("Waffenschmiedin") once each in a list,
the NPCs' rows pointing into it. `agps npc-names` reports; `--write` writes the files.
"""
from __future__ import annotations

import re
from pathlib import Path

from .paths import ADDON_DIR

NPCS_LUA = ADDON_DIR / "Data" / "Npcs.lua"
OUT_DIR = ADDON_DIR / "Data" / "NpcNames"
LOCALES = ("deDE", "esES", "esMX", "frFR", "koKR", "ruRU", "zhCN", "zhTW")
SOURCE = Path("thirdparty") / "azerothcore"

# a MySQL dump's value: a quoted string (backslash escapes), NULL, or a number
_VALUE = re.compile(r"'((?:[^'\\]|\\.)*)'|(NULL)|(-?[\d.]+)")
_ESCAPES = {"0": "\0", "n": "\n", "r": "\r", "t": "\t", "Z": "\x1a"}


def _unescape(s: str) -> str:
    return re.sub(r"\\(.)", lambda m: _ESCAPES.get(m.group(1), m.group(1)), s)


def _rows(path: Path, table: str, width: int | None = None):
    """Each row of `table`'s INSERTs in a mysqldump file (one row a line), as a list of values (str, None, or the
    number's text); only the first `width` values when given."""
    inside = False
    with open(path, encoding="utf-8") as f:
        for line in f:
            if line.startswith("INSERT INTO `"):
                inside = line.startswith(f"INSERT INTO `{table}`")
                continue
            if not inside or not line.startswith("("):
                if inside and not line.startswith("("):
                    inside = False
                continue
            vals, pos = [], 1
            while pos < len(line) and (width is None or len(vals) < width):
                m = _VALUE.match(line, pos)
                if not m:
                    break
                if m.group(1) is not None:
                    vals.append(_unescape(m.group(1)))
                elif m.group(2):
                    vals.append(None)
                else:
                    vals.append(m.group(3))
                pos = m.end()
                if pos < len(line) and line[pos] == ",":
                    pos += 1
            yield vals


def shipped(npcs_lua: Path = NPCS_LUA) -> dict[int, tuple[str, str]]:
    """Data/Npcs.lua's NPCs: { id: (name, subname) }."""
    text = npcs_lua.read_text(encoding="utf-8")
    body = text.split("[==[", 1)[1].split("]==]", 1)[0]
    out = {}
    for line in body.splitlines():
        parts = line.split("|")
        if len(parts) >= 3 and parts[0].isdigit():
            out[int(parts[0])] = (parts[1], parts[2])
    return out


def build(data_dir: Path, npcs_lua: Path = NPCS_LUA) -> tuple[dict, dict]:
    """{ locale: { id: (name or None, title or None) } } (only what differs from the English), and a report."""
    src = data_dir / SOURCE
    npcs = shipped(npcs_lua)
    english = {}
    for v in _rows(src / "creature_template.sql", "creature_template", 8):
        if v and v[0] and int(v[0]) in npcs:
            english[int(v[0])] = v[6] or ""
    same = {i for i, n in npcs.items() if english.get(i) == n[0]}
    report = {"shipped": len(npcs), "in AzerothCore": len(english), "same English name": len(same)}
    out = {loc: {} for loc in LOCALES}
    for v in _rows(src / "creature_template_locale.sql", "creature_template_locale", 4):
        if len(v) < 4 or not v[0]:
            continue
        i, loc, name, title = int(v[0]), v[1], v[2], v[3]
        if loc not in out or i not in same:
            continue
        en_name, en_title = npcs[i]
        name = (name or "").strip()
        title = (title or "").strip()
        n = name if name and name != en_name and "|" not in name and "]==]" not in name else None
        # (a title only where the shipped NPC has one: the data's English one is what's searched by kind)
        t = title if en_title and title and title != en_title and "|" not in title and "]==]" not in title else None
        if n or t:
            out[loc][i] = (n, t)
    return out, report


def lua_text(locale: str, names: dict) -> str:
    """Data/NpcNames/<locale>.lua: `ns.NpcNamesLoc` one line an NPC, `id|name|title`, the name empty where it's the
    English, the title the index of `ns.NpcTitlesLoc`'s (empty: the English)."""
    titles, index = [], {}
    lines = []
    for i in sorted(names):
        n, t = names[i]
        k = ""
        if t:
            if t not in index:
                titles.append(t)
                index[t] = len(titles)
            k = str(index[t])
        lines.append(f"{i}|{n or ''}|{k}")

    def q(s):
        return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'

    out = [f"-- GENERATED by `agps npc-names --write`. Do not edit by hand.",
           f"-- The shipped NPCs' names and titles ({locale}) from AzerothCore's creature_template_locale",
           "-- (https://github.com/azerothcore/azerothcore-wotlk, GPL-2): only where they differ from the English. Read on a",
           f"-- {locale} client only, at the first search (Locales.lua's ns.ShippedNpcName); one line an NPC, id|name|title,",
           "-- the title an index into ns.NpcTitlesLoc.",
           "local _, ns = ...",
           f'if not (GetLocale and GetLocale() == "{locale}") then return end',
           f'ns.NpcNamesLocale = "{locale}"',
           "ns.NpcTitlesLoc = {"]
    for k in range(0, len(titles), 6):
        out.append("  " + " ".join(q(t) + "," for t in titles[k:k + 6]))
    out += ["}", "ns.NpcNamesLoc = [==[", *lines, "]==]"]
    return "\n".join(out) + "\n"
