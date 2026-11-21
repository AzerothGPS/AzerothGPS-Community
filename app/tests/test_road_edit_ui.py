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


def test_the_directions_say_cross_the_bridge_on_the_players_own_bridges(game):
    # (Kooki3z 2026-11-20: "doesn't say cross the bridge on drawn bridges ... or recorded")
    lua, ns = game
    G, R, Rec, T = ns.GPS, ns.Router, ns.Record, ns.Turns
    saved = ns.db.tracks
    try:
        ns.db.tracks = lua.table()
        R.Reset()
        G.roadMode = True
        G.FinishRoad(lua.table(pts=lua.table(2600.0, 2100.0, 2620.0, 2100.0, 2640.0, 2100.0, 2660.0, 2100.0), cont=0),
                     False, False)
        sel = Rec.TrackAt(0, 2630.0, 2101.0)
        assert sel and Rec.EditTrack(sel, lua.table(kind="bridge", z=20))
        G.roadMode = None
        R.NearestEdges(0, 2630.0, 2100.0)
        assert R.OnKindRoad(0, 2630.0, 2100.5, "bridge", 2) and not R.OnKindRoad(0, 2630.0, 2110.0, "bridge", 2)
        # a walk along the roads from 30 yd before it to 30 yd past it
        pts = lua.table(2570.0, 2100.0, 2600.0, 2100.0, 2660.0, 2100.0, 2690.0, 2100.0)
        path = T.Path(lua.table(parts=lua.table(lua.table(pts=pts, kinds=lua.table(0, 0, 0), cont=0, stop=1))))
        places = list(T.Places(path).values())
        br = [m for m in places if m.kind == "bridge"]
        assert len(br) == 1 and abs(br[0].dist - 30) <= 5 and abs(br[0].stop - 90) <= 5
        ms = T.Maneuvers(path, "the stop")
        assert any("cross the bridge" in str(ms[i].text).lower() for i in range(1, len(ms) + 1))
        # a plain road: nothing said
        ns.db.tracks = lua.table()
        R.Reset()
        R.NearestEdges(0, 2630.0, 2100.0)
        assert not [m for m in T.Places(path).values() if m.kind == "bridge"]
    finally:
        G.roadMode = None
        ns.db.tracks = saved
        R.Reset()


def test_a_road_erased_since_isnt_picked_where_its_gone(game):
    # (Kooki3z 2026-11-20: "cant delete stairs here, also seems like I can select phantom roads that aren't shown with the
    # road tool": a road erased since was still picked there, and Delete took out that one, not the road shown)
    lua, ns = game
    G, R, Rec = ns.GPS, ns.Router, ns.Record
    saved = ns.db.tracks
    try:
        ns.db.tracks = lua.table()
        R.Reset()
        G.roadMode = True
        G.FinishRoad(lua.table(pts=lua.table(2600.0, 1900.0, 2630.0, 1900.0, 2660.0, 1900.0), cont=0), False, False)
        old = ns.db.tracks[1]
        assert Rec.TrackAt(0, 2615.0, 1901.0).t.time == old.time
        # erased along its west half: gone there, still picked on the rest
        G.FinishRoad(lua.table(pts=lua.table(2598.0, 1900.0, 2628.0, 1900.0), cont=0), True, False)
        er = ns.db.tracks[2]
        assert er.op == "remove" and er.time > old.time
        assert Rec.TrackAt(0, 2610.0, 1901.0) is None
        assert Rec.TrackAt(0, 2655.0, 1901.0).t.time == old.time
        # a road drawn there after the erase: picked (the erase is older than it)
        G.FinishRoad(lua.table(pts=lua.table(2600.0, 1902.0, 2625.0, 1902.0), cont=0), False, False)
        new = ns.db.tracks[3]
        if new.time <= er.time:
            new.time = er.time + 1
        assert Rec.TrackAt(0, 2610.0, 1902.0).t.time == new.time
    finally:
        G.roadMode = None
        ns.db.tracks = saved
        R.Reset()


def test_on_a_lift_it_still_says_take_the_lift_then_whats_next(game):
    # (Kooki3z 2026-11-20: "while on the lift part of the path, it should still say take the lift then cross the bridge")
    lua, ns = game
    R, T = ns.Router, ns.Turns
    UP = R.KIND_LIFT_UP
    # the path from where the player is: halfway up a lift (10 yd), then 40 yd of road
    pts = lua.table(2600.0, 2400.0, 2605.0, 2400.0, 2610.0, 2400.0, 2650.0, 2400.0)
    path = T.Path(lua.table(parts=lua.table(lua.table(pts=pts, kinds=lua.table(UP, UP, 0), cont=0, stop=1))))
    ms = T.Maneuvers(path, "the stop")
    said = [(str(ms[i].kind), str(ms[i].text)) for i in range(1, len(ms) + 1)]
    assert said and said[0][0] == "lift" and "lift up" in said[0][1].lower(), said
    assert abs(ms[1].stop - 10) < 0.5


def test_a_road_end_picked_glows_and_a_road_drawn_from_it_goes_on_as_it_is(game):
    # (Kooki3z 2026-11-20: "click on the end of a road/bridge/lift/etc, this draws a glowing circle around it ... when
    # shift + left click is used on it, extend whatever that is at its defined height"; and the hover says its kind)
    lua, ns = game
    G, R, Rec = ns.GPS, ns.Router, ns.Record
    saved = ns.db.tracks
    try:
        ns.db.tracks = lua.table()
        R.Reset()
        G.roadMode = True
        G.FinishRoad(lua.table(pts=lua.table(2600.0, 1100.0, 2615.0, 1100.0, 2630.0, 1100.0, 2645.0, 1100.0), cont=0),
                     False, False)
        first = ns.db.tracks[1]
        sel = Rec.TrackAt(0, 2615.0, 1101.0)
        assert sel and Rec.EditTrack(sel, lua.table(kind="bridge", z=20))
        R.NearestEdges(0, 2645.0, 1100.0)
        # the hover: a bridge says so
        info = G.RoadHoverInfo(0, 2620.0, 1100.0, 5)
        assert info and str(info.title) == "Bridge", info and info.title
        # (a bridge rising between its ends, as a recorded one's heights from the ground: still a bridge, not Stairs;
        # Kooki3z 2026-11-20, "recorded bridge, mouse over says stairs")
        ns.Record.Save(lua.table(op="add", drawn=True, recorded=True, continent=0, time=4242, kind="bridge",
                                 pts=lua.table(2600.0, 1150.0, 2620.0, 1150.0, 2640.0, 1150.0),
                                 zs=lua.table(10, 15, 20)))
        R.NearestEdges(0, 2620.0, 1150.0)
        info = G.RoadHoverInfo(0, 2620.0, 1150.0, 5)
        assert info and str(info.title) == "Bridge", info and info.title
        # its end, picked by a click near it: kind and height
        en = G.RoadEndAt(0, 2645.5, 1100.0, 3)
        assert en and en.kind == "bridge" and abs(en.z - 20) < 0.01
        assert G.ToolClick(0, 2645.5, 1100.5, 2) and G.roadEnd and abs(G.roadEnd.x - 2645) < 0.01
        # (a click on it again lets it go; once more picks it)
        assert G.ToolClick(0, 2645.0, 1100.0, 2) and G.roadEnd is None
        assert G.ToolClick(0, 2645.0, 1100.0, 2) and G.roadEnd
        # glowing where it is on the map
        G.LayoutRoads(2645.0, 1100.0, 0, 0, 60, 200)
        assert G.roadEndScreen is not None
        G.PlaceRoadEndGlow()
        if G.roadEndGlow:
            assert G.roadEndGlow._shown and "UI-Taxi-Icon" in str(G.roadEndGlow._texture or G.ROAD_END_GLOW)
        # a road drawn from it (starting a little off): snapped on, a bridge at 20 all along; its far end picked next
        n0 = len(ns.db.tracks)
        G.FinishRoad(lua.table(pts=lua.table(2646.0, 1100.5, 2670.0, 1100.0, 2690.0, 1100.0), cont=0), False, False)
        assert len(ns.db.tracks) == n0 + 1
        t = ns.db.tracks[n0 + 1]
        assert t.kind == "bridge" and (t.pts[1], t.pts[2]) == (2645.0, 1100.0)
        assert list(t.zs.values()) == [20, 20, 20]
        assert G.roadEnd and abs(G.roadEnd.x - 2690) < 0.01
        # the tools off: none picked
        G.roadEnd = lua.table(level=0, x=2645.0, y=1100.0, z=20, kind="bridge")
        G.SetRoadMode(False)
        assert G.roadEnd is None
        # a road drawn away from any end picked: a plain road
        G.SetRoadMode(True)
        G.FinishRoad(lua.table(pts=lua.table(2600.0, 1300.0, 2650.0, 1300.0), cont=0), False, False)
        assert ns.db.tracks[len(ns.db.tracks)].kind is None
        # stairs and lifts go on as a floor at their end's height; a floor needs one
        assert tuple(G.RoadEndGoesOn(lua.table(kind="stairs", z=31.5))) == ("floor", 31.5)
        assert tuple(G.RoadEndGoesOn(lua.table(kind="lift", z=80))) == ("floor", 80)
        assert G.RoadEndGoesOn(lua.table(kind="floor"))[0] is None
        assert G.RoadEndGoesOn(lua.table(kind="ground"))[0] is None
    finally:
        G.roadEnd = None
        G.SetRoadMode(False)
        G.roadMode = None
        ns.db.tracks = saved
        R.Reset()
