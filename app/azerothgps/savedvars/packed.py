"""AzerothGPS's packed saved points (Core.lua ns.PackSaved, 1.1.6): a drawn road's and a faster trip's points are saved
as one string each (`pk`, and `zk` for a road's heights: numbers apart by spaces, "-" for none), not two values a
point, since WoW's Lua loads a saved file of at most 262,143 distinct values. In game they're lists again at load."""

from __future__ import annotations


def unpack_numbers(s) -> list:
    """A packed string's numbers (None for "-")."""
    out = []
    for w in str(s).split():
        try:
            out.append(None if w == "-" else float(w))
        except ValueError:
            out.append(None)
    return out


def unpacked(rec):
    """A saved road or trip with its points as the game keeps them: `pk`/`zk` back as `pts`/`zs` (a record saved
    before 1.1.6, with lists, as it is)."""
    if not isinstance(rec, dict):
        return rec
    out = dict(rec)
    if isinstance(out.get("pk"), str) and not out.get("pts"):
        out["pts"] = unpack_numbers(out.pop("pk"))
    if isinstance(out.get("zk"), str) and not out.get("zs"):
        out["zs"] = unpack_numbers(out.pop("zk"))
    return out
