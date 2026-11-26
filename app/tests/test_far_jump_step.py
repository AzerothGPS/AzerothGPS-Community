"""A spell jump far ahead reads like any upcoming maneuver, with its distance (item 52, Kooki3z 2026-11-24 at Freewind
Post: "Jump, then cast Slow Fall just before you land" with the Un'Goro rim 3.6k yd away). The imperative only within
Turns.DROP_NOW_YD of the edge."""

from test_map_redraw import game  # noqa: F401


def test_a_jump_3k_yd_away_shows_its_distance_not_the_imperative(game):  # noqa: F811
    lua, ns = game
    FS, T = ns.FallSpells, ns.Turns
    lua.execute("""
      local FS = AGPS_NS.FallSpells
      AGPS_52 = { FS.Current, FS.InAir, FS.Needs, FS.Name, FS.RowCooldown }
      local c = { row = {}, up = nil, id = 130 }
      FS.Current = function() return c end
      FS.InAir = function() return true end
      FS.Needs = function() return true end
      FS.Name = function() return "Slow Fall" end
      FS.RowCooldown = function() return 0 end""")
    fmt = lua.eval("function(d) return string.format('%d yd', d) end")
    try:
        far = T.NowText(lua.eval("{ kind = 'drop', text = 'Jump down', dropYd = 213, dist = 3600 }"), fmt)
        assert "3600 yd" in far and "jump down" in far and "Slow Fall" in far and not far.startswith("Jump"), far
        near = T.NowText(lua.eval("{ kind = 'drop', text = 'Jump down', dropYd = 213, dist = 20 }"), fmt)
        assert near.startswith("Jump, then cast Slow Fall"), near
    finally:
        lua.execute("""local FS = AGPS_NS.FallSpells
          FS.Current, FS.InAir, FS.Needs, FS.Name, FS.RowCooldown = AGPS_52[1], AGPS_52[2], AGPS_52[3], AGPS_52[4], AGPS_52[5]
          FS.fallArm = nil""")
