"""Every client table the tools read has a layout to read it with: committed in extract/dbd/, or listed in
REF_DBD_TABLES as one that needs data/ref/dbd (which isn't in git: a PC without it can't build). LiquidType was in
neither, and every terrain build there failed (PR #273)."""

import re
from pathlib import Path

from azerothgps.extract.db2 import parse_dbd
from azerothgps.extract.spike import REF_DBD_TABLES

PKG = Path(__file__).resolve().parents[1] / "azerothgps"
COMMITTED = PKG / "extract" / "dbd"
TABLE_CALL = re.compile(r"""\.table\(\s*["']([A-Za-z0-9_]+)["']\s*\)""")


def tables_read() -> dict[str, list[str]]:
    """{table name: [the files reading it]} for every `.table("<name>")` in the app."""
    out: dict[str, list[str]] = {}
    for path in sorted(PKG.rglob("*.py")):
        for name in TABLE_CALL.findall(path.read_text(encoding="utf-8")):
            out.setdefault(name, []).append(str(path.relative_to(PKG)))
    return out


def test_the_scan_finds_the_tables_read():
    names = tables_read()
    assert {"Map", "AreaTable", "LiquidType", "AreaTrigger"} <= set(names)


def test_every_table_read_has_its_layout():
    committed = {p.stem for p in COMMITTED.glob("*.dbd")}
    missing = {n: files for n, files in tables_read().items() if n not in committed and n not in REF_DBD_TABLES}
    assert not missing, (
        f"no layout for {missing}: commit its .dbd in {COMMITTED} (this client's layout only), or add it to "
        "spike.REF_DBD_TABLES if it needs data/ref/dbd")


def test_the_ref_list_names_only_tables_read():
    assert not REF_DBD_TABLES - set(tables_read())


def test_the_committed_liquidtype_layout_is_the_clients():
    """WoW Forever 1.60.1.70938's LiquidType.db2: layout D1ECEEC9, 21 inline fields, the ID in the id list; and
    roads/terrain.py's sea_types reads ID, SoundBank and Name."""
    fields = parse_dbd(COMMITTED / "LiquidType.dbd", 0xD1ECEEC9)
    inline = [f for f in fields if not f.noninline]
    assert len(inline) == 21
    by = {f.name: f for f in fields}
    assert by["ID"].is_id and by["ID"].noninline
    assert by["Name"].kind == "string" and by["SoundBank"].kind == "int"
    assert [by[n].array for n in ("Texture", "FrameCountTexture", "Color", "Float", "Int", "Coefficient")] == \
        [6, 6, 3, 38, 4, 4]
