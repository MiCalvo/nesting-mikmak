"""Trazos (selección por aristas), reconocimiento de círculos y DXF con arcos."""
import math

import ezdxf
import pytest
from shapely.geometry import Point, Polygon, box

from nesting2d.engine.nester import Layout, Placement, nest
from nesting2d.engine.params import NestParams
from nesting2d.exporters.arcs import bulges_to_points, ring_circle, ring_to_bulges
from nesting2d.exporters.dxf_export import export_sheet
from nesting2d.importers.contours import ImportOptions
from nesting2d.importers.dxf_import import dxf_polylines, import_dxf
from nesting2d.importers.pdf_import import import_pdf, pdf_page_polylines
from nesting2d.importers.strokes import StrokeSet, classify

from .conftest import DATA


# --- clasificación ----------------------------------------------------------------------
def test_classify_line_arc_circle():
    assert classify([(0, 0), (10, 0), (20, 0)]).kind == "recta"
    circ = list(Point(5, 5).buffer(3, quad_segs=32).exterior.coords)
    s = classify(circ)
    assert s.kind == "circulo" and s.diameter == pytest.approx(6, abs=1e-3)
    arc = [(10 * math.cos(math.radians(a)), 10 * math.sin(math.radians(a))) for a in range(0, 91, 5)]
    s = classify(arc)
    assert s.kind == "arco" and s.radius == pytest.approx(10, abs=1e-6) and s.sweep == pytest.approx(90, abs=0.1)
    assert classify([(0, 0), (10, 0), (10, 10), (0, 12)]).kind == "polilinea"


def test_real_gasket_one_chain_plus_holes_equals_zone_import():
    """RIGCCP0019: un clic en el contorno (cadena) + sus círculos = la misma pieza que por zonas."""
    o = ImportOptions()
    pages, _ = pdf_page_polylines(DATA / "RIGCCP0019.pdf", o)
    ss = StrokeSet(pages[1], o)
    assert {round(c.diameter, 2) for c in ss.circles} == {4.49}
    outer_i = max(range(len(ss)), key=lambda i: ss.strokes[i].length)
    chain = ss.chain(outer_i)
    assert ss.open_ends(chain) == []
    outer = ss.outer_of(chain)
    holes = ss.circles_inside(outer)
    assert len(holes) == 15
    (part,) = ss.parts_from(sorted(set(chain) | {s for c in holes for s in c.strokes}))
    ref = import_pdf(DATA / "RIGCCP0019.pdf").parts[0].shape
    assert part.symmetric_difference(ref).area < 0.01
    assert len(part.interiors) == 15


def test_crossing_axis_does_not_split_and_is_ignored(tmp_path):
    """Un eje que cruza el taladro y una cota que cruza la placa: por zonas parten la
    pieza; por aristas no cuentan porque no se eligen."""
    doc = ezdxf.new("R2010")
    doc.units = 4
    m = doc.modelspace()
    m.add_lwpolyline([(0, 0), (100, 0), (100, 60), (0, 60)], close=True)
    m.add_circle((50, 30), 10)
    m.add_line((30, 30), (70, 30))       # eje horizontal que cruza el taladro
    m.add_line((-10, 45), (110, 45))     # "cota" que atraviesa la placa
    doc.saveas(tmp_path / "p.dxf")
    o = ImportOptions()
    pls, _ = dxf_polylines(tmp_path / "p.dxf", o)
    ss = StrokeSet(pls, o)
    assert sorted(s.kind for s in ss.strokes) == ["circulo", "polilinea", "recta", "recta"]   # el rectángulo NO es círculo
    plate = next(i for i, s in enumerate(ss.strokes) if s.kind == "polilinea")
    chain = ss.chain(plate)
    assert len(chain) == 1                      # el contorno de la placa es un único trazo
    circle = ss.circles[0]
    assert ss.same_diameter(circle.strokes[0]) == [circle]
    (part,) = ss.parts_from(chain + circle.strokes)
    assert part.area == pytest.approx(6000 - math.pi * 100, rel=1e-3)
    assert len(part.interiors) == 1


def test_chain_stops_at_branches_and_reports_gaps():
    # dos tramos unidos (nudo de grado 2) y una rama en el otro extremo (grado 3)
    o = ImportOptions()
    ss = StrokeSet([[(0, 0), (10, 0)], [(10, 0), (10, 10)], [(0, 0), (-5, 0)], [(0, 0), (0, -5)]], o)
    assert ss.chain(0) == [0, 1]
    assert sorted(ss.open_ends([0, 1])) == [(0.0, 0.0), (10.0, 10.0)]


def test_arcs_grouped_into_full_circle():
    o = ImportOptions()
    quarters = [[(20 * math.cos(math.radians(a)), 20 * math.sin(math.radians(a))) for a in range(q, q + 91, 3)]
                for q in (0, 90, 180, 270)]
    ss = StrokeSet(quarters, o)
    assert len(ss.circles) == 1 and ss.circles[0].diameter == pytest.approx(40, abs=1e-3)
    assert sorted(ss.chain(0)) == [0, 1, 2, 3]


# --- arcos para el DXF ------------------------------------------------------------------
def test_ring_to_bulges_rounded_rectangle_exact():
    rr = box(0, 0, 100, 60).buffer(5, quad_segs=16)
    v = ring_to_bulges(list(rr.exterior.coords))
    angles = [math.degrees(4 * math.atan(b)) for *_, b in v if b]
    assert len(angles) == 4 and all(abs(abs(a) - 90) < 0.1 for a in angles)
    back = Polygon(bulges_to_points(v, 0.05))
    assert back.area == pytest.approx(100 * 60 + 2 * 5 * 160 + math.pi * 25, abs=0.05)
    assert rr.exterior.hausdorff_distance(back.exterior) <= 0.05


@pytest.mark.parametrize("name", ["RIGCCP0016", "RIGCCP0017", "RIGCCP0018", "RIGCCP0019", "RIGCCP0020"])
def test_ring_to_bulges_stays_within_tolerance_on_real_gaskets(name):
    g = import_pdf(DATA / f"{name}.pdf").parts[0].geometry()
    for ring in [g.exterior, *g.interiors]:
        coords = list(ring.coords)
        c = ring_circle(coords)
        if c is not None:
            assert Polygon(coords).exterior.hausdorff_distance(Point(c[0]).buffer(c[1], 256).exterior) <= 0.06
            continue
        back = Polygon(bulges_to_points(ring_to_bulges(coords), 0.05))
        assert Polygon(coords).exterior.hausdorff_distance(back.exterior) <= 0.05 + 0.01


def test_dxf_export_with_arcs_roundtrip(gaskets, tmp_path):
    layout = nest(gaskets, NestParams(time_limit=2, seed=1, part_in_part=False))
    f = export_sheet(layout, 0, tmp_path / "arcos.dxf", arcs=True)
    doc = ezdxf.readfile(f)
    kinds = {e.dxftype() for e in doc.modelspace() if e.dxf.layer == "CORTE"}
    assert "CIRCLE" in kinds                               # los taladros
    bulged = [e for e in doc.modelspace().query("LWPOLYLINE") if any(b for *_, b in e.get_points("xyb"))]
    assert bulged                                          # contornos con arcos
    back = import_dxf(f, layers=["CORTE"]).parts
    assert len(back) == 16
    # cada pieza reimportada no se aparta de la colocada más que la tolerancia de los
    # arcos (0,05 mm) más la discretización al reimportar
    for p in back:
        c = p.shape.centroid
        q = min(layout.placements, key=lambda q: q.polygon.centroid.distance(c))
        assert p.shape.exterior.hausdorff_distance(q.polygon.exterior) <= 0.06
        assert len(p.shape.interiors) == len(q.polygon.interiors)
