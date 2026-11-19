"""Edit Road in the whole addon (the road tools, 1.3.10, issue #640): a road drawn, picked on the map, set to a bridge at
a height or a floor with stairs on part of it, saved as a track that replaces it; routes take the edit at once, the map
draws it in its kind's color, and Undo takes it back."""

import pytest


@pytest.fixture(scope="module")
def game():
    pytest.importorskip("lupa.lua51")
    from azerothgps.gameharness import start
    lua, ns = start()
    ns.Nav.FUN = False
    return lua, ns


def click(lua, b):
    b.GetScript(b, "OnClick")(b)


def test_a_drawn_road_edited_into_a_bridge_and_a_floor_with_stairs(game):
    lua, ns = game
    G, R, Rec = ns.GPS, ns.Router, ns.Record
    saved = ns.db.tracks
    try:
        ns.db.tracks = lua.table()
        R.Reset()
        G.roadMode = True
        G.FinishRoad(lua.table(pts=lua.table(2600.0, 700.0, 2615.0, 700.0, 2630.0, 700.0, 2645.0, 700.0), cont=0),
                     False, False)
        first = ns.db.tracks[1]
        assert first.zs is None and first.kind is None
        # Edit Road: the road picked by a click near it, its window opened
        G.SetEditRoadMode(True)
        assert G.editRoadMode and G.EditRoadClick(0, 2615.0, 702.0)
        win = lua.globals().AzerothGPSRoadEdit
        assert win._shown and G.roadEdit.sel.t.time == first.time
        assert G.roadEdit.kind == "ground", G.roadEdit.kind
        bridge = [b for b in win.kinds.values() if b.kind == "bridge"][0]
        click(lua, bridge)
        assert G.roadEdit.kind == "bridge"
        # no height: not saved, the window says so
        win.height.box.SetText(win.height.box, "")
        click(lua, win.save)
        assert len(ns.db.tracks) == 1 and win._shown
        win.height.box.SetText(win.height.box, "20")
        click(lua, win.save)
        assert not win._shown and len(ns.db.tracks) == 2
        ed = ns.db.tracks[2]
        assert ed.kind == "bridge" and ed.replaces == first.time and ed.rpart is None
        assert list(ed.zs.values()) == [20, 20, 20, 20] and list(ed.pts.values()) == list(first.pts.values())
        # routes: the old flat road gone, the bridge on its floor, raised, its kind kept
        R.NearestEdges(0, 2615.0, 700.0)
        g = R.DebugGraph(0)
        mine = [ei for ei in range(1, len(g.e) + 1) if g.e[ei][4] == R.SOURCE_RECORDED
                and 2599 <= g.e[ei][5] <= 2646 and abs(g.e[ei][6] - 700) < 1]
        assert mine and all(g.kind[ei] == "bridge" and g.raised[ei] for ei in mine)
        assert all(abs(g.nz[g.e[ei][1]] - 20) < 1 or abs(g.nz[g.e[ei][2]] - 20) < 1 for ei in mine)
        # the map: the tools on, drawn in the bridge's color
        segs = G.LayoutRoads(2615.0, 700.0, 0, 0, 60, 200)
        colors = [tuple(sg[5].values()) for sg in segs.values() if not isinstance(sg[5], (int, float))]
        assert tuple(G.KIND_COLORS.bridge.values()) in colors
        # (zoomed in: its connection points as dots, the network's ends and junctions)
        widths = {sg[7] for sg in segs.values()}
        assert G.END_DOT in widths or G.JUNCTION_DOT in widths
        G.roadMode = None
        plain = G.LayoutRoads(2615.0, 700.0, 0, 0, 60, 200)
        assert not {sg[7] for sg in plain.values()} - {None}  # (the tools off: as before, no dots or kinds)
        G.roadMode = True
        # picked again (the edit now: the old one is replaced), a floor at 34.5 with stairs up to 41.5 from point 2 to 3
        assert G.EditRoadClick(0, 2615.0, 701.0)
        assert G.roadEdit.sel.t.time == ed.time and G.roadEdit.kind == "bridge"
        click(lua, [b for b in win.kinds.values() if b.kind == "floor"][0])
        click(lua, win.pickFoot)
        assert G.roadEdit.pick == "foot"
        assert G.EditRoadClick(0, 2614.0, 700.0) and G.roadEdit.foot == 2
        click(lua, win.pickTop)
        assert G.EditRoadClick(0, 2631.0, 700.0) and G.roadEdit.top == 3
        win.height.box.SetText(win.height.box, "34.5")
        win.topRow.box.SetText(win.topRow.box, "41.5")
        click(lua, win.save)
        st = ns.db.tracks[3]
        assert st.kind == "floor" and st.replaces == ed.time and list(st.stairs.values()) == [2, 3]
        assert list(st.zs.values()) == [34.5, 34.5, 41.5, 41.5]
        ns.Record.Apply()
        R.NearestEdges(0, 2622.0, 700.0)
        g = R.DebugGraph(0)
        stairs = [ei for ei in range(1, len(g.e) + 1) if g.e[ei][4] == R.SOURCE_STAIR and abs(g.e[ei][6] - 700) < 1
                  and 2610 <= g.e[ei][5] <= 2632]
        assert stairs and all(g.kind[ei] == "stairs" for ei in stairs)
        assert not [ei for ei in range(1, len(g.e) + 1) if g.kind and g.kind[ei] == "bridge"]  # (replaced)
        # Undo: the last edit back, the bridge again
        Rec.Undo()
        assert len(ns.db.tracks) == 2
        R.NearestEdges(0, 2615.0, 700.0)
        g = R.DebugGraph(0)
        assert [ei for ei in range(1, len(g.e) + 1) if g.kind and g.kind[ei] == "bridge"]
        # nothing there: said, nothing picked
        assert G.EditRoadClick(0, 3000.0, 1000.0) and not win._shown
        G.SetEditRoadMode(False)
        assert not G.editRoadMode and G.roadEdit is None
    finally:
        ns.db.tracks = saved
        G.roadMode, G.editRoadMode, G.roadEdit = None, None, None
        R.Reset()
