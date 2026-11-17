"""Every caller of caves.cave_roads takes all it returns (nodes, edges, drops, heights).

Since #332 cave_roads returns four values; capitals.build_under and two other callers still took three, and
`agps capitals` failed on every capital with floors under its streets ("too many values to unpack", found
2026-11-17 looking into Stormwind's canal bridge, #560). instances.instance_roads returned five."""

import ast
from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "azerothgps"


def test_every_unpacking_of_cave_roads_takes_four_values():
    bad = []
    for path in APP.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Assign) or not isinstance(node.value, ast.Call):
                continue
            f = node.value.func
            name = f.id if isinstance(f, ast.Name) else f.attr if isinstance(f, ast.Attribute) else None
            if name != "cave_roads":
                continue
            for t in node.targets:
                if isinstance(t, ast.Tuple) and len(t.elts) != 4:
                    bad.append(f"{path.name}:{node.lineno} takes {len(t.elts)}")
    assert not bad, bad


def test_instance_roads_gives_four_values_without_layers(monkeypatch):
    from azerothgps import caves, instances

    monkeypatch.setattr(caves, "cave_roads", lambda u: ([(0.0, 0.0)], [], {}, [0.0]))
    out = instances.instance_roads({})
    assert len(out) == 4 and out[3] is None
