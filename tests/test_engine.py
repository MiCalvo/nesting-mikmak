from shapely.geometry import box

from nesting2d.engine.nester import nest
from nesting2d.engine.params import NestParams
from nesting2d.geometry import Part
from nesting2d.validate import check_layout

FAST = dict(time_limit=3, seed=1)


def test_project_fits_one_sheet_and_is_valid(gaskets):
    layout = nest(gaskets, NestParams(separation=5, margin=5, part_in_part=False, **FAST))
    assert layout.sheets == 1
    assert len(layout.placements) == 16
    assert layout.unplaced == {}
    assert check_layout(layout) == []
    # validado el 14/10/2026: ~170-195 mm de franja según separación y tiempo
    assert layout.stats(0)["used_length"] < 300


def test_restricted_rotation_respected_when_compacting_down(gaskets):
    for p in gaskets:
        p.rotations = [0.0]
    layout = nest(gaskets, NestParams(compact_side="abajo", part_in_part=False, **FAST))
    assert check_layout(layout) == []
    assert {round(q.angle) % 360 for q in layout.placements} == {0}


def test_several_sheets(gaskets):
    layout = nest(gaskets, NestParams(sheet_width=400, sheet_height=300, part_in_part=False, **FAST))
    assert layout.sheets >= 2
    assert layout.unplaced == {}
    assert len(layout.placements) == 16
    assert check_layout(layout) == []


def test_part_in_part_puts_0017_inside_0020_at_2mm(gaskets):
    layout = nest(gaskets, NestParams(separation=2, part_in_part=True, **FAST))
    assert check_layout(layout) == []
    inner = [q for q in layout.placements if q.host is not None]
    assert {q.part for q in inner} == {"RIGCCP0017"}
    assert all(layout.placements[q.host].part == "RIGCCP0020" for q in inner)
    assert len(layout.placements) == 16


def test_part_in_part_nothing_fits_at_3mm(gaskets):
    layout = nest(gaskets, NestParams(separation=3, part_in_part=True, **FAST))
    assert all(q.host is None for q in layout.placements)


def test_too_big_part_is_reported():
    big = Part("enorme", box(0, 0, 2000, 50), quantity=1)
    layout = nest([big], NestParams(**FAST))
    assert layout.unplaced == {"enorme": 1}
    assert layout.placements == []
