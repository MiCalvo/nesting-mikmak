import pytest

from nesting2d import project
from nesting2d.engine.nester import nest
from nesting2d.engine.params import NestParams
from nesting2d.exporters.dxf_export import export_sheet
from nesting2d.importers.dxf_import import import_dxf


@pytest.fixture
def layout(gaskets):
    return nest(gaskets, NestParams(time_limit=3, seed=1, part_in_part=False))


def test_dxf_roundtrip(layout, tmp_path):
    f = export_sheet(layout, 0, tmp_path / "p1.dxf")
    res = import_dxf(f, layers=["CORTE"])
    assert len(res.parts) == 16
    got = sorted(round(p.area) for p in res.parts)
    want = sorted(round(q.polygon.area) for q in layout.placements)
    assert got == want


def test_project_save_load(layout, gaskets, tmp_path):
    f = project.save(tmp_path / "p.json", gaskets, layout.params, layout)
    parts, params, lay = project.load(f)
    assert [p.name for p in parts] == [p.name for p in gaskets]
    assert params == layout.params
    assert len(lay.placements) == len(layout.placements)
    assert lay.placements[0].polygon.equals_exact(layout.placements[0].polygon, 1e-6)
