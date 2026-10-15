"""Importador DXF con archivos SINTÉTICOS (generados con ezdxf imitando lo que
exporta un CAD). Faltan DXF reales del CAD de Mikel."""
import math

import ezdxf
import pytest
from ezdxf import units

from nesting2d.importers.dxf_import import dxf_layers, import_dxf


def new_doc(u=units.MM):
    doc = ezdxf.new("R2010")
    doc.units = u
    return doc


def test_rounded_plate_with_bulges_and_circles(tmp_path):
    doc = new_doc()
    msp = doc.modelspace()
    r, b = 5, math.tan(math.radians(90) / 4)     # bulge de un arco de 90°
    pts = [(r, 0, 0), (100 - r, 0, b), (100, r, 0), (100, 60 - r, b), (100 - r, 60, 0), (r, 60, b),
           (0, 60 - r, 0), (0, r, b)]
    msp.add_lwpolyline(pts, format="xyb", close=True)
    msp.add_circle((20, 30), 4)
    msp.add_circle((80, 30), 4)
    doc.saveas(tmp_path / "placa.dxf")
    res = import_dxf(tmp_path / "placa.dxf")
    assert res.warnings == []
    p = res.parts[0]
    assert p.size == pytest.approx((100, 60), abs=1e-3)
    assert len(p.shape.interiors) == 2
    expected = 100 * 60 - (4 - math.pi) * r * r - 2 * math.pi * 4 ** 2
    assert p.area == pytest.approx(expected, rel=1e-3)


def test_nested_blocks_scaled_and_rotated(tmp_path):
    doc = new_doc()
    blk = doc.blocks.new("PIEZA")
    blk.add_lwpolyline([(0, 0), (30, 0), (30, 10), (0, 10)], close=True)
    blk.add_circle((5, 5), 2)
    outer = doc.blocks.new("CONJUNTO")
    outer.add_blockref("PIEZA", (0, 0), dxfattribs={"xscale": 2, "yscale": 2, "rotation": 90})
    doc.modelspace().add_blockref("CONJUNTO", (100, 100))
    doc.saveas(tmp_path / "anidado.dxf")
    res = import_dxf(tmp_path / "anidado.dxf")
    assert len(res.parts) == 1
    assert res.parts[0].size == pytest.approx((20, 60), abs=1e-3)   # 30×10, ×2 y girado 90°
    assert len(res.parts[0].shape.interiors) == 1


def test_minsert_grid(tmp_path):
    doc = new_doc()
    blk = doc.blocks.new("CUADRADO")
    blk.add_lwpolyline([(0, 0), (10, 0), (10, 10), (0, 10)], close=True)
    doc.modelspace().add_blockref("CUADRADO", (0, 0)).grid(size=(2, 3), spacing=(20, 20))
    doc.saveas(tmp_path / "minsert.dxf")
    assert len(import_dxf(tmp_path / "minsert.dxf").parts) == 6


def test_inches_are_converted(tmp_path):
    doc = new_doc(units.IN)
    doc.modelspace().add_lwpolyline([(0, 0), (2, 0), (2, 1), (0, 1)], close=True)
    doc.saveas(tmp_path / "in.dxf")
    assert import_dxf(tmp_path / "in.dxf").parts[0].size == pytest.approx((50.8, 25.4))


def test_unitless_imperial_warns(tmp_path):
    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = 0
    doc.header["$MEASUREMENT"] = 0
    doc.modelspace().add_lwpolyline([(0, 0), (2, 0), (2, 1), (0, 1)], close=True)
    doc.saveas(tmp_path / "x.dxf")
    w = import_dxf(tmp_path / "x.dxf").warnings
    assert len(w) == 1 and "pulgadas" in w[0]


def test_lines_arcs_spline_ellipse(tmp_path):
    doc = new_doc()
    msp = doc.modelspace()
    msp.add_line((0, 0), (50, 0))
    msp.add_arc((50, 20), 20, -90, 90)
    msp.add_line((50, 40), (0, 40))
    msp.add_line((0, 40), (0, 0))
    msp.add_ellipse((20, 20), major_axis=(8, 0), ratio=0.5)          # hueco elíptico
    msp.add_spline(fit_points=[(100, 0), (120, 20), (140, 0), (120, -20), (100, 0)])
    doc.saveas(tmp_path / "la.dxf")
    parts = import_dxf(tmp_path / "la.dxf").parts
    assert sorted((round(p.size[0]), round(p.size[1]), len(p.shape.interiors)) for p in parts) == \
        [(40, 40, 0), (70, 40, 1)]


def test_layers_and_layer0_inherits_insert_layer(tmp_path):
    doc = new_doc()
    blk = doc.blocks.new("P")
    blk.add_lwpolyline([(0, 0), (10, 0), (10, 10), (0, 10)], close=True)    # capa 0
    msp = doc.modelspace()
    msp.add_blockref("P", (0, 0), dxfattribs={"layer": "CORTE"})
    msp.add_lwpolyline([(-5, -5), (50, -5), (50, 50), (-5, 50)], close=True, dxfattribs={"layer": "MARCO"})
    msp.add_text("hola", dxfattribs={"layer": "TEXTO"})
    doc.saveas(tmp_path / "capas.dxf")
    assert dxf_layers(tmp_path / "capas.dxf") == {"CORTE": 1, "MARCO": 1}
    # con el marco, el cuadrado sería un hueco del marco: 1 pieza
    assert len(import_dxf(tmp_path / "capas.dxf").parts) == 1
    only = import_dxf(tmp_path / "capas.dxf", layers=["CORTE"]).parts
    assert len(only) == 1 and only[0].size == pytest.approx((10, 10))
