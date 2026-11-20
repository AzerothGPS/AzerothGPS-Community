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
        # (the kind picked: lit, never grayed out; every kind clickable, Kooki3z 2026-11-20)
        kinds = list(win.kinds.values())
        assert all(b._enabled is not False for b in kinds)
        assert [b.kind for b in kinds if b.picked] == ["bridge"]
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


def test_a_bridge_with_no_height_known_saves_and_stays_off_the_roads_under_it(game):
    # (Kooki3z 2026-11-20: Thousand Needles' rope bridges, no floors near to take a height from; "Give it a height." kept
    # it from saving, and the window closed threw the bridge away)
    lua, ns = game
    G, R = ns.GPS, ns.Router
    saved = ns.db.tracks
    try:
        ns.db.tracks = lua.table()
        R.Reset()
        G.roadMode = True
        G.FinishRoad(lua.table(pts=lua.table(2600.0, 900.0, 2615.0, 900.0, 2630.0, 900.0, 2645.0, 900.0), cont=0),
                     False, False)
        first = ns.db.tracks[1]
        G.SetEditRoadMode(True)
        assert G.EditRoadClick(0, 2615.0, 902.0)
        win = lua.globals().AzerothGPSRoadEdit
        click(lua, [b for b in win.kinds.values() if b.kind == "bridge"][0])
        win.height.box.SetText(win.height.box, "")
        click(lua, win.save)
        assert not win._shown and len(ns.db.tracks) == 2
        ed = ns.db.tracks[2]
        assert ed.kind == "bridge" and ed.zs is None and ed.replaces == first.time
        R.NearestEdges(0, 2615.0, 900.0)
        g = R.DebugGraph(0)
        mine = [ei for ei in range(1, len(g.e) + 1) if g.e[ei][4] == R.SOURCE_RECORDED
                and 2599 <= g.e[ei][5] <= 2646 and abs(g.e[ei][6] - 900) < 1]
        assert mine and all(g.kind[ei] == "bridge" and g.raised[ei] for ei in mine)
        # (a floor still needs its height)
        assert G.EditRoadClick(0, 2615.0, 901.0)
        click(lua, [b for b in win.kinds.values() if b.kind == "floor"][0])
        win.height.box.SetText(win.height.box, "")
        click(lua, win.save)
        assert win._shown and len(ns.db.tracks) == 2
        win.Hide(win)
    finally:
        G.SetEditRoadMode(False)
        G.roadMode = None
        ns.db.tracks = saved
        R.Reset()


def test_a_lift_goes_up_toward_its_top_by_its_heights_and_flip_lift_swaps_them(game):
    # (Kooki3z 2026-11-20: a lift drawn from its foot up said "Take the lift down"; "Need a way to be able to flip which
    # side of the lift says take lift up or down")
    lua, ns = game
    G, R = ns.GPS, ns.Router
    # by its ends' heights: toward the higher end up, either way it was drawn
    g = lua.eval("{ e = { { 1, 2, 30, 5, 0,0, 30,0 } }, nz = { 10, 50 } }")
    assert R.LiftKind(g, 1, True) == R.KIND_LIFT_UP and R.LiftKind(g, 1, False) == R.KIND_LIFT_DOWN
    g.nz = lua.eval("{ 50, 10 }")
    assert R.LiftKind(g, 1, True) == R.KIND_LIFT_DOWN and R.LiftKind(g, 1, False) == R.KIND_LIFT_UP
    # no heights (the data's lifts, laid from the top): forward is down, as before
    g.nz = None
    assert R.LiftKind(g, 1, True) == R.KIND_LIFT_DOWN and R.LiftKind(g, 1, False) == R.KIND_LIFT_UP
    # Edit Road on a lift: Flip Lift in Pick Foot's place, swapping Foot and Top
    saved = ns.db.tracks
    try:
        ns.db.tracks = lua.table()
        R.Reset()
        G.roadMode = True
        G.FinishRoad(lua.table(pts=lua.table(2600.0, 1500.0, 2615.0, 1500.0, 2630.0, 1500.0), cont=0), False, False)
        G.SetEditRoadMode(True)
        assert G.EditRoadClick(0, 2615.0, 1501.0)
        win = lua.globals().AzerothGPSRoadEdit
        assert not win.flip._shown and win.pickFoot._shown
        click(lua, [b for b in win.kinds.values() if b.kind == "lift"][0])
        assert win.flip._shown and not win.pickFoot._shown and not win.pickTop._shown
        win.height.box.SetText(win.height.box, "10")
        win.topRow.box.SetText(win.topRow.box, "50")
        click(lua, win.flip)
        assert str(win.height.box.GetText(win.height.box)) == "50" and str(win.topRow.box.GetText(win.topRow.box)) == "10"
        click(lua, win.save)
        ed = ns.db.tracks[2]
        assert ed.kind == "lift" and list(ed.zs.values())[0] == 50 and list(ed.zs.values())[-1] == 10
        # (the routes: its first node the higher, so along it is down)
        R.NearestEdges(0, 2615.0, 1500.0)
        gr = R.DebugGraph(0)
        mine = [ei for ei in range(1, len(gr.e) + 1) if gr.e[ei][4] == R.SOURCE_LIFT
                and 2599 <= gr.e[ei][5] <= 2631 and abs(gr.e[ei][6] - 1500) < 1]
        assert mine
        e = gr.e[mine[0]]
        fwd_up = R.LiftKind(gr, mine[0], True) == R.KIND_LIFT_UP
        hz = gr.z or gr.nz
        assert fwd_up == (hz[e[2]] > hz[e[1]])
    finally:
        G.SetEditRoadMode(False)
        G.roadMode = None
        ns.db.tracks = saved
        R.Reset()


def test_a_lift_with_no_heights_is_a_lift_ride_from_its_first_end_and_flips(game):
    # (Kooki3z 2026-11-20: "recorded lifts don't say take the lift": a lift with no heights was a plain road)
    lua, ns = game
    G, R, Rec = ns.GPS, ns.Router, ns.Record
    g = lua.eval("{ e = { { 1, 2, 30, 5, 0,0, 30,0 } }, kind = { 'lift' } }")
    assert R.LiftKind(g, 1, True) == R.KIND_LIFT_UP and R.LiftKind(g, 1, False) == R.KIND_LIFT_DOWN
    saved = ns.db.tracks
    try:
        ns.db.tracks = lua.table()
        R.Reset()
        Rec.Save(lua.table(op="add", drawn=True, recorded=True, continent=0, time=7777, kind="lift",
                           pts=lua.table(2600.0, 2300.0, 2604.0, 2300.0, 2608.0, 2300.0)))
        R.NearestEdges(0, 2604.0, 2300.0)
        gr = R.DebugGraph(0)
        mine = [ei for ei in range(1, len(gr.e) + 1) if 2599 <= gr.e[ei][5] <= 2609 and abs(gr.e[ei][6] - 2300) < 1]
        assert mine and all(gr.e[ei][4] == R.SOURCE_LIFT for ei in mine)
        # Flip Lift with no heights: saved turned round
        G.roadMode = True
        G.SetEditRoadMode(True)
        assert G.EditRoadClick(0, 2604.0, 2300.5)
        win = lua.globals().AzerothGPSRoadEdit
        assert G.roadEdit.kind == "lift" and win.flip._shown
        win.height.box.SetText(win.height.box, "")
        win.topRow.box.SetText(win.topRow.box, "")
        win.flip._scripts.OnClick(win.flip)
        win.save._scripts.OnClick(win.save)
        ed = ns.db.tracks[len(ns.db.tracks)]
        assert ed.kind == "lift" and ed.replaces == 7777 and (ed.pts[1], ed.pts[2]) == (2608.0, 2300.0)
    finally:
        G.SetEditRoadMode(False)
        G.roadMode = None
        ns.db.tracks = saved
        R.Reset()
