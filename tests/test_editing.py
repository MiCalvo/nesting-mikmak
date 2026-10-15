import pytest
from shapely.geometry import box

from nesting2d import editing, project
from nesting2d.engine.nester import Layout, Placement, nest
from nesting2d.engine.params import NestParams
from nesting2d.geometry import Part
from nesting2d.validate import check_layout


def two_boxes(**kw):
    params = NestParams(sheet_width=200, sheet_height=100, separation=5, margin=5, **kw)
    return Layout(params, [Placement("a", 0, 0.0, box(5, 5, 25, 25)),
                           Placement("b", 0, 0.0, box(50, 5, 70, 25))], sheets=1)


def test_move_and_rotate_return_changes_without_touching_layout():
    L = two_boxes()
    ch = editing.moved(L, [0], 10, 2)
    assert L.placements[0].polygon.bounds == (5, 5, 25, 25)        # sin aplicar
    editing.apply(L, ch)
    assert L.placements[0].polygon.bounds == pytest.approx((15, 7, 35, 27))
    ch = editing.rotated(L, [1], 90)
    assert ch[1].angle == 90
    editing.apply(L, ch)
    assert L.placements[1].polygon.bounds == pytest.approx((50, 5, 70, 25))  # cuadrado: gira sobre su centro


def test_transformed_absolute_target_after_rotation():
    L = Layout(NestParams(), [Placement("r", 0, 0.0, box(100, 100, 140, 110))], sheets=1)
    editing.apply(L, editing.transformed(L, [0], angle=90, target=(10, 20)))
    q = L.placements[0]
    assert q.angle == 90
    assert q.polygon.bounds == pytest.approx((10, 20, 20, 60))


def test_inner_pieces_follow_their_host_and_detach_when_moved_alone():
    L = Layout(NestParams(), [Placement("host", 0, 0.0, box(0, 0, 100, 100).difference(box(20, 20, 80, 80))),
                              Placement("in", 0, 0.0, box(30, 30, 40, 40), host=0)], sheets=1)
    assert editing.with_inners(L, [0]) == [0, 1]
    ch = editing.moved(L, editing.with_inners(L, [0]), 5, 0)
    assert ch[1].host == 0                                   # se mueve con su contenedor
    ch = editing.moved(L, [1], 5, 0)
    assert ch[1].host is None                                # movida sola: se desliga


def test_snap_to_margin_and_to_neighbour_separation():
    L = two_boxes()
    # b (50..70) se acerca a a (5..25): a 2 mm de quedar a la separación (25 + 5 = 30)
    dx, dy = editing.snap_delta(L, [1], -18, 0, tol=3)
    assert dx == pytest.approx(-20)
    editing.apply(L, editing.moved(L, [1], dx, dy))
    assert check_layout(L) == []
    # cerca del margen derecho (200 − 5): engancha
    dx, _ = editing.snap_delta(L, [1], 143, 0, tol=3)     # b está en 30..50: borde derecho a 193
    assert L.placements[1].polygon.bounds[2] + dx == pytest.approx(195)
    # lejos de todo: no cambia
    assert editing.snap_delta(L, [1], 40, 30, tol=1) == (40, 30)


def test_rotation_warnings():
    L = two_boxes()
    parts = [Part("a", box(0, 0, 20, 20), rotations=[0.0]), Part("b", box(0, 0, 20, 20))]
    assert editing.rotation_warnings(L, parts, L.params) == []
    editing.apply(L, editing.rotated(L, [0, 1], 45))
    warn = editing.rotation_warnings(L, parts, L.params)
    assert [i for i, _ in warn] == [0, 1]                # a solo admite 0°; el proyecto, cada 90°
    assert editing.rotation_warnings(L, parts, NestParams(rotation_step=None)) == [(0, warn[0][1])]


def test_to_sheet():
    L = two_boxes()
    editing.apply(L, editing.to_sheet(L, [1], 1))
    assert [q.sheet for q in L.placements] == [0, 1]


def test_project_v2_keeps_engine_result_and_edits(gaskets, tmp_path):
    layout = nest(gaskets, NestParams(time_limit=2, seed=1, part_in_part=False))
    engine = Layout(layout.params, list(layout.placements), layout.sheets)
    editing.apply(layout, editing.moved(layout, [0], 3, 0))
    f = project.save(tmp_path / "p.json", gaskets, layout.params, layout, engine_layout=engine)
    d = project.load_project(f)
    assert d.layout.placements[0].polygon.equals_exact(layout.placements[0].polygon, 1e-6)
    assert d.engine_layout.placements[0].polygon.equals_exact(engine.placements[0].polygon, 1e-6)
    assert not d.layout.placements[0].polygon.equals_exact(d.engine_layout.placements[0].polygon, 1e-6)
